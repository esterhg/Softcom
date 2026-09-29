from celery import shared_task
from django.db import transaction
import time
import os
import logging
from .services import WorkOrderService

logger = logging.getLogger(__name__)


def try_decode(content, encodings=['utf-8-sig', 'utf-8', 'windows-1252', 'iso-8859-1', 'utf-16', 'mac_roman']):
    """Intenta decodificar el contenido usando una lista de encodings prioritarios."""
    if not content:
        return ""
        
    for encoding in encodings:
        try:
            decoded = content.decode(encoding)
            if encoding in ['iso-8859-1', 'windows-1252', 'latin-1'] and '\x00' in decoded:
                continue
            return decoded
        except (UnicodeDecodeError, LookupError, AttributeError):
            continue
            
    # Último recurso: forzar utf-8 reemplazando caracteres inválidos para que no se pierda la fila
    # pero advirtiendo al menos en el log.
    return content.decode('utf-8', errors='replace')

@shared_task(bind=True, name='mantenimiento.tasks.import_pasos_task')
def import_pasos_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Pasos"):
    """
    Tarea Celery para importar o VERIFICAR PASOS DE RUTINA con seguimiento de progreso real.
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from .admin import PasoRutinaResource
    from django.core.cache import cache
    from .models import PasoRutina, Rutina
    from activos.models import RegistroImportacion
    from django.contrib.auth.models import User
    import sys

    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Pasos de Rutina',
            usuario=user,
            estado='PROCESANDO'
        )

    # Marcador de progreso en caché
    cache_key = f"import_pasos_progress_{user_id}" if user_id else "import_pasos_progress_system"

    # Inicializar resource
    resource = PasoRutinaResource()
    resource.celery_task = self
    resource.cache_key = cache_key
    resource.total_rows = 0 
    print(f"[DEBUG] [Pasos] Resource inicializado para {import_name}")

    # Leer archivo
    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    resource.total_rows = total_rows
    if registro:
        registro.total_filas = total_rows
        registro.save()

    missing_dataset = Dataset()
    missing_dataset.headers = dataset.headers
    
    # Estado inicial
    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Iniciando verificacion...' if verification_mode else 'Iniciando importacion...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'found': 0,
        'not_found': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)
    sys.stdout.flush()

    if verification_mode:
        results = []
        codes_seen = set()
        codes_duplicated = set()
        found_count = 0
        not_found_count = 0
        
        for i, row in enumerate(dataset.dict, start=1):
            obj_id = row.get('id')
            codigo_rutina = str(row.get('codigo_rutina') or '').strip()
            orden = str(row.get('orden') or '').strip()
            
            exists = False
            if obj_id:
                try:
                    exists = PasoRutina.objects.filter(id=obj_id).exists()
                except (ValueError, TypeError):
                    pass
            
            identifier = f"{codigo_rutina}-{orden}"
            if not obj_id and (not codigo_rutina or not orden):
                status = "SIN RUTINA O ORDEN"
                not_found_count += 1
                missing_dataset.append(dataset[i-1])
            else:
                if identifier in codes_seen and not obj_id:
                    codes_duplicated.add(identifier)
                    status = "REPETIDO EN ARCHIVO"
                else:
                    codes_seen.add(identifier)
                    if exists:
                        found_count += 1
                        status = f"EXISTE (ID {obj_id})"
                    else:
                        not_found_count += 1
                        status = "NUEVO PASO (Se creará)"
                        if not Rutina.objects.filter(codigo_rutina=codigo_rutina).exists():
                            status += f" - WARNING: La Rutina '{codigo_rutina}' NO EXISTE"
            
            results.append(f"Fila {i}: {codigo_rutina}(orden {orden}) -> {status}")
            
            if i % 10 == 0 or i == total_rows:
                progress_info.update({
                    'current': i,
                    'status': f'Verificando {i}/{total_rows}...',
                    'percent': int((i / total_rows) * 100),
                    'found': found_count,
                    'not_found': not_found_count,
                    'duplicates': len(codes_duplicated)
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'found': found_count,
            'not_found': not_found_count,
            'duplicates': len(codes_duplicated),
            'duplicate_list': list(codes_duplicated),
            'results': results,
            'verification_mode': True
        }
    else:
        # Modo IMPORTACIÓN real
        try:
            print(f"[DEBUG] [Actual Import Pasos] Iniciando import_data con {len(dataset)} filas...")
            sys.stdout.flush()
            result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False, use_transactions=False)
            
            # Recopilar errores
            detailed_errors = []
            for error in result.base_errors:
                detailed_errors.append(f"Error General: {str(error.error)}")
            
            for line, errors in result.row_errors():
                for error in errors:
                    detailed_errors.append(f"Fila {line}: {str(error.error)}")

            if registro:
                registro.filas_nuevas = result.totals.get('new', 0)
                registro.filas_actualizadas = result.totals.get('update', 0)
                registro.filas_omitidas = result.totals.get('skip', 0)
                registro.filas_error = len(detailed_errors)
                registro.estado = 'COMPLETADO'
                if detailed_errors:
                    registro.detalles_error = "\n".join(detailed_errors[:50])
                registro.save()

            final_res = {
                'status': 'completed',
                'status_code': 'completed',
                'total': total_rows,
                'new': result.totals.get('new', 0),
                'updated': result.totals.get('update', 0),
                'skipped': result.totals.get('skip', 0),
                'errors': len(detailed_errors),
                'error_list': detailed_errors,
                'verification_mode': False,
                'dry_run': dry_run,
                'file_path': file_path
            }
        except Exception as e:
            if registro:
                registro.estado = 'ERROR'
                registro.detalles_error = str(e)
                registro.save()
            error_msg = f"Error crítico en importación: {str(e)}"
            progress_info.update({'status': 'error', 'message': error_msg})
            cache.set(cache_key, progress_info, 3600)
            return {'status': 'error', 'message': error_msg}

    # Limpiar archivo original SOLO si no es dry_run
    if not dry_run:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except:
            pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res

@shared_task(bind=True, name='mantenimiento.tasks.import_rutinas_task')
def import_rutinas_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Rutinas"):
    """
    Tarea Celery para importar o VERIFICAR RUTINAS con seguimiento de progreso real.
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from .admin import RutinaResource
    from django.core.cache import cache
    from .models import Rutina
    from activos.models import RegistroImportacion
    from django.contrib.auth.models import User
    
    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Rutinas',
            usuario=user,
            estado='PROCESANDO'
        )

    # Marcador de progreso en caché
    cache_key = f"import_rutinas_progress_{user_id}" if user_id else "import_rutinas_progress_system"
    
    # Inicializar resource
    resource = RutinaResource()
    resource.celery_task = self
    resource.cache_key = cache_key
    resource.total_rows = 0 
    print(f"[DEBUG] Resource inicializado para {import_name}")

    # Leer archivo
    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    resource.total_rows = total_rows
    if registro:
        registro.total_filas = total_rows
        registro.save()

    missing_dataset = Dataset()
    missing_dataset.headers = dataset.headers
    
    # Estado inicial
    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Iniciando verificacion...' if verification_mode else 'Iniciando importacion...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'found': 0,
        'not_found': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)
    print(f"[DEBUG] [Task] Iniciando import_rutinas_task. verif={verification_mode}, dry={dry_run}, user={user_id}")
    import sys
    sys.stdout.flush()

    if verification_mode:
        results = []
        codes_seen = set()
        codes_duplicated = set()
        found_count = 0
        not_found_count = 0
        
        for i, row in enumerate(dataset.dict, start=1):
            obj_id = row.get('id')
            codigo = str(row.get('codigo_rutina') or '').strip()
            
            # 1. Identificar registro (ID prioritario)
            exists = False
            if obj_id:
                try:
                    exists = Rutina.objects.filter(id=obj_id).exists()
                except (ValueError, TypeError):
                    pass
            
            if not exists and codigo:
                exists = Rutina.objects.filter(codigo_rutina=codigo).exists()

            # 2. Determinar Estado
            if not obj_id and not codigo:
                status = "SIN IDENTIFICADOR"
                not_found_count += 1
                missing_dataset.append(dataset[i-1])
            else:
                if codigo and codigo in codes_seen and not obj_id:
                    codes_duplicated.add(codigo)
                    status = "REPETIDO EN ARCHIVO"
                else:
                    if codigo: codes_seen.add(codigo)
                    
                    if exists:
                        found_count += 1
                        status = "EXISTE"
                        if obj_id:
                            status += f" (ID {obj_id})"
                    else:
                        not_found_count += 1
                        status = "NO EXISTE"
                        missing_dataset.append(dataset[i-1])
            
            results.append(f"Fila {i}: {status}")
            print(f"[DEBUG] [Task] Verificando fila {i}: {codigo} -> {status}")
            
            if i % 10 == 0 or i == total_rows:
                progress_info.update({
                    'current': i,
                    'status': f'Verificando {i}/{total_rows}...',
                    'percent': int((i / total_rows) * 100),
                    'found': found_count,
                    'not_found': not_found_count,
                    'duplicates': len(codes_duplicated)
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'found': found_count,
            'not_found': not_found_count,
            'duplicates': len(codes_duplicated),
            'duplicate_list': list(codes_duplicated),
            'results': results,
            'verification_mode': True
        }
    else:
        # Modo IMPORTACIÓN real
        try:
            print(f"[DEBUG] [Actual Import Rutinas] Iniciando import_data con {len(dataset)} filas...")
            sys.stdout.flush()
            # Usar import_data (use_transactions=True en Meta ya maneja la transacción)
            result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False)
            print(f"[DEBUG] [Actual Import Rutinas] import_data finalizado. Resultado: {result.totals}")
            sys.stdout.flush()
            
            # Recopilar errores detallados de las filas
            detailed_errors = []
            for error in result.base_errors:
                detailed_errors.append(f"Error General: {str(error.error)}")
            
            for line, errors in result.row_errors():
                for error in errors:
                    # Incluimos el numero de fila para que el usuario sepa donde esta el fallo
                    detailed_errors.append(f"Fila {line}: {str(error.error)}")

            if registro:
                registro.filas_nuevas = result.totals.get('new', 0)
                registro.filas_actualizadas = result.totals.get('update', 0)
                registro.filas_omitidas = result.totals.get('skip', 0)
                registro.filas_error = len(detailed_errors)
                registro.estado = 'COMPLETADO'
                if detailed_errors:
                    registro.detalles_error = "\n".join(detailed_errors[:50])
                registro.save()

            final_res = {
                'status': 'completed',
                'status_code': 'completed',
                'total': total_rows,
                'new': result.totals.get('new', 0),
                'updated': result.totals.get('update', 0),
                'skipped': result.totals.get('skip', 0),
                'errors': len(detailed_errors),
                'error_list': detailed_errors,
                'verification_mode': False,
                'dry_run': dry_run,
                'file_path': file_path
            }
        except Exception as e:
            if registro:
                registro.estado = 'ERROR'
                registro.detalles_error = str(e)
                registro.save()
            error_msg = f"Error crítico en importación: {str(e)}"
            progress_info.update({'status': 'error', 'message': error_msg})
            cache.set(cache_key, progress_info, 3600)
            return {'status': 'error', 'message': error_msg}

    # Si estamos en verificacion y hay códigos faltantes, generar el archivo Excel
    if verification_mode and len(missing_dataset) > 0:
        try:
            from django.core.files.base import ContentFile
            missing_filename = f"imports/faltantes_rutinas_{user_id or 'anon'}_{int(time.time())}.xlsx"
            default_storage.save(missing_filename, ContentFile(missing_dataset.xlsx))
            final_res['missing_file_url'] = default_storage.url(missing_filename)
            final_res['missing_count'] = len(missing_dataset)
        except Exception as e:
            print(f"Error al generar archivo de faltantes: {str(e)}")

    # Limpiar archivo original SOLO si no es dry_run
    if not dry_run:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except:
            pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res
@shared_task(bind=True, name='mantenimiento.tasks.import_ordenes_task')
def import_ordenes_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación OTs"):
    """
    Tarea Celery para importar o VERIFICAR OTs con seguimiento de progreso real.
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from .admin import OrdenTrabajoResource
    from django.core.cache import cache
    from .models import OrdenTrabajo
    from activos.models import RegistroImportacion
    from django.contrib.auth.models import User
    import sys

    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Ordenes Trabajo',
            usuario=user,
            estado='PROCESANDO'
        )

    # Marcador de progreso en caché
    cache_key = f"import_ordenes_progress_{user_id}" if user_id else "import_ordenes_progress_system"

    # Inicializar resource
    resource = OrdenTrabajoResource()
    resource.celery_task = self
    resource.cache_key = cache_key
    resource.total_rows = 0
    # No usamos bulk para OTs porque after_import necesita los IDs individuales generados inmediatamente
    resource._meta.use_bulk = False

    # Leer archivo
    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    resource.total_rows = total_rows
    if registro:
        registro.total_filas = total_rows
        registro.save()
        
    missing_dataset = Dataset()
    missing_dataset.headers = dataset.headers
    
    # Estado inicial
    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Iniciando verificacion...' if verification_mode else 'Iniciando importacion...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'found': 0,
        'not_found': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)
    print(f"[DEBUG] [Task] Iniciando import_ordenes_task. verif={verification_mode}, dry={dry_run}, user={user_id}")
    sys.stdout.flush()

    if verification_mode:
        results = []
        codes_seen = set()
        codes_duplicated = set()
        found_count = 0
        not_found_count = 0
        
        for i, row in enumerate(dataset.dict, start=1):
            codigo = str(row.get('codigo_de_orden') or '').strip()
            
            if not codigo or codigo.lower() in ['none', 'nan', 'null', '']:
                status = "SIN CODIGO"
                not_found_count += 1
                missing_dataset.append(dataset[i-1])
            else:
                if codigo in codes_seen:
                    codes_duplicated.add(codigo)
                    status = "REPETIDO EN ARCHIVO"
                else:
                    codes_seen.add(codigo)
                    exists = OrdenTrabajo.objects.filter(codigo_de_orden=codigo).exists()
                    if exists:
                        found_count += 1
                        status = "EXISTE (Se actualizará)"
                    else:
                        not_found_count += 1
                        status = "NO EXISTE (Se creará)"
            
            results.append(f"Fila {i}: Codigo '{codigo}' -> {status}")
            
            if i % 10 == 0 or i == total_rows:
                progress_info.update({
                    'current': i,
                    'status': f'Verificando {i}/{total_rows}...',
                    'percent': int((i / total_rows) * 100),
                    'found': found_count,
                    'not_found': not_found_count,
                    'duplicates': len(codes_duplicated)
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'found': found_count,
            'not_found': not_found_count,
            'duplicates': len(codes_duplicated),
            'duplicate_list': list(codes_duplicated),
            'results': results,
            'verification_mode': True
        }
    else:
        # Modo IMPORTACIÓN real o Dry Run
        resource.before_import(dataset)
        try:
            print(f"[DEBUG] [Task] Ejecutando resource.import_data. dry_run={dry_run}")
            # Usar import_data con transacciones y bulk
            result = resource.import_data(
                dataset, 
                dry_run=dry_run, 
                raise_errors=False,
                use_transactions=True
            )
            print(f"[DEBUG] [Task] import_data finalizado. Totals: {result.totals}")
            
            # Recopilar errores
            detailed_errors = []
            for error in result.base_errors:
                detailed_errors.append(f"Error General: {str(error.error)}")
            
            for line, errors in result.row_errors():
                for error in errors:
                    detailed_errors.append(f"Fila {line}: {str(error.error)}")
                    
            if result.invalid_rows:
                for row in result.invalid_rows:
                    error_msg = f"Fila {row.number} (Invalid): {str(row.error)}"
                    detailed_errors.append(error_msg)
                    # Force print to stdout for capturing in logs
                    print(f"[DEBUG] [Task] INVALID ROW DETECTED: {error_msg}")
                    print(f"[DEBUG] [Task] Row Values: {row.values}")
            
            if detailed_errors:
                print(f"[DEBUG] [Task] Errores encontrados: {detailed_errors}")

            if registro:
                registro.filas_nuevas = result.totals.get('new', 0)
                registro.filas_actualizadas = result.totals.get('update', 0)
                registro.filas_omitidas = result.totals.get('skip', 0)
                registro.filas_error = len(detailed_errors)
                registro.estado = 'COMPLETADO'
                if detailed_errors:
                    registro.detalles_error = "\n".join(detailed_errors[:50])
                registro.save()

            final_res = {
                'status': 'completed',
                'status_code': 'completed',
                'total': total_rows,
                'new': result.totals.get('new', 0),
                'updated': result.totals.get('update', 0),
                'skipped': result.totals.get('skip', 0),
                'errors': len(detailed_errors),
                'error_list': detailed_errors,
                'verification_mode': False,
                'dry_run': dry_run,
                'file_path': file_path
            }
        except Exception as e:
            if registro:
                registro.estado = 'ERROR'
                registro.detalles_error = str(e)
                registro.save()
            error_msg = f"Error crítico en importación: {str(e)}"
            progress_info.update({'status': 'error', 'message': error_msg})
            cache.set(cache_key, progress_info, 3600)
            return {'status': 'error', 'message': error_msg}

    # Limpiar archivo original SOLO si no es dry_run
    if not dry_run:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except:
            pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res


@shared_task(bind=True, name='mantenimiento.tasks.import_avisos_task')
def import_avisos_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Avisos"):
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from .admin import AvisoResource
    from django.core.cache import cache
    from .models import Aviso
    from activos.models import RegistroImportacion
    from django.contrib.auth.models import User
    import sys

    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Avisos',
            usuario=user,
            estado='PROCESANDO'
        )

    resource = AvisoResource()
    cache_key = f"import_avisos_progress_{user_id}" if user_id else "import_avisos_progress_system"

    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    missing_dataset = Dataset()
    missing_dataset.headers = dataset.headers
    
    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Iniciando verificacion...' if verification_mode else 'Iniciando importacion...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'found': 0,
        'not_found': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)
    sys.stdout.flush()

    if verification_mode:
        results = []
        codes_seen = set()
        codes_duplicated = set()
        found_count = 0
        not_found_count = 0
        
        # En Avisos, identificamos por id o descripción+fecha (aquí no suele haber update masivo, 
        # pero asumimos import id = id o un nuevo aviso)
        for i, row in enumerate(dataset.dict, start=1):
            aviso_id = str(row.get('id') or '').strip()
            
            identifier = aviso_id
            
            if not aviso_id:
                status = "NUEVO REGISTRO (Se creará)"
                not_found_count += 1
            else:
                if identifier in codes_seen:
                    codes_duplicated.add(identifier)
                    status = "REPETIDO EN ARCHIVO"
                else:
                    codes_seen.add(identifier)
                    exists = Aviso.objects.filter(id=aviso_id).exists()
                    if exists:
                        found_count += 1
                        status = "EXISTE (Se actualizará)"
                    else:
                        not_found_count += 1
                        status = "ID NO EXISTE (Error posible)"
            
            results.append(f"Fila {i}: ID '{aviso_id}' -> {status}")
            
            if i % 10 == 0 or i == total_rows:
                progress_info.update({
                    'current': i,
                    'status': f'Verificando {i}/{total_rows}...',
                    'percent': int((i / total_rows) * 100),
                    'found': found_count,
                    'not_found': not_found_count,
                    'duplicates': len(codes_duplicated)
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'found': found_count,
            'not_found': not_found_count,
            'duplicates': len(codes_duplicated),
            'duplicate_list': list(codes_duplicated),
            'results': results,
            'verification_mode': True
        }
    else:
        # Ya creado arriba si corresponde
        resource.before_import(dataset)
        try:
            result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False)
            
            detailed_errors = []
            for error in result.base_errors:
                detailed_errors.append(f"Error General: {str(error.error)}")
            
            for line, errors in result.row_errors():
                for error in errors:
                    detailed_errors.append(f"Fila {line}: {str(error.error)}")

            final_res = {
                'status': 'completed',
                'status_code': 'completed',
                'total': total_rows,
                'new': result.totals.get('new', 0),
                'updated': result.totals.get('update', 0),
                'skipped': result.totals.get('skip', 0),
                'errors': len(detailed_errors),
                'error_list': detailed_errors,
                'verification_mode': False,
                'dry_run': dry_run,
                'file_path': file_path
            }

            if registro:
                registro.filas_nuevas = final_res.get('new', 0)
                registro.filas_actualizadas = final_res.get('updated', 0)
                registro.filas_omitidas = final_res.get('skipped', 0)
                registro.filas_error = final_res.get('errors', 0)
                registro.estado = 'COMPLETADO'
                if final_res.get('error_list'):
                    registro.detalles_error = "\n".join(final_res['error_list'][:10])
                registro.save()
        except Exception as e:
            error_msg = f"Error crítico en importación: {str(e)}"
            progress_info.update({'status': 'error', 'message': error_msg})
            cache.set(cache_key, progress_info, 3600)
            return {'status': 'error', 'message': error_msg}

    if not dry_run:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except:
            pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res
@shared_task(bind=True, name='mantenimiento.tasks.import_personal_task')
def import_personal_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Personal"):
    """
    Tarea Celery para importar o VERIFICAR PERSONAL (Técnicos) con seguimiento de progreso real.
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from .admin import TecnicoPuestoResource
    from django.core.cache import cache
    from .models import TecnicoPuesto
    from django.contrib.auth.models import User
    from activos.models import RegistroImportacion
    import sys

    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Personal',
            usuario=user,
            estado='PROCESANDO'
        )

    # Inicializar resource
    resource = TecnicoPuestoResource()
    
    # Marcador de progreso en caché
    cache_key = f"import_personal_progress_{user_id}" if user_id else "import_personal_progress_system"

    # Leer archivo
    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    if registro:
        registro.total_filas = total_rows
        registro.save()

    missing_dataset = Dataset()
    missing_dataset.headers = dataset.headers
    
    # Estado inicial
    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Iniciando verificacion...' if verification_mode else 'Iniciando importacion...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'found': 0,
        'not_found': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)
    print(f"[DEBUG] [Task] Iniciando import_personal_task. verif={verification_mode}, dry={dry_run}, user={user_id}")
    sys.stdout.flush()

    if verification_mode:
        results = []
        codes_seen = set()
        codes_duplicated = set()
        found_count = 0
        not_found_count = 0
        
        for i, row in enumerate(dataset.dict, start=1):
            dni = str(row.get('dni') or '').strip()
            username = str(row.get('username') or '').strip()
            
            identifier = dni if dni else username
            
            if not identifier:
                status = "SIN DNI NI USERNAME"
                not_found_count += 1
                missing_dataset.append(dataset[i-1])
            else:
                if identifier in codes_seen:
                    codes_duplicated.add(identifier)
                    status = "REPETIDO EN ARCHIVO"
                else:
                    codes_seen.add(identifier)
                    
                    exists = False
                    if dni:
                        exists = TecnicoPuesto.objects.filter(dni=dni).exists()
                    elif username:
                        exists = TecnicoPuesto.objects.filter(user__username=username).exists()
                        
                    if exists:
                        found_count += 1
                        status = "EXISTE (Se actualizará)"
                    else:
                        not_found_count += 1
                        status = "NO EXISTE (Se creará)"
            
            results.append(f"Fila {i}: '{identifier}' -> {status}")
            
            if i % 10 == 0 or i == total_rows:
                progress_info.update({
                    'current': i,
                    'status': f'Verificando {i}/{total_rows}...',
                    'percent': int((i / total_rows) * 100),
                    'found': found_count,
                    'not_found': not_found_count,
                    'duplicates': len(codes_duplicated)
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'found': found_count,
            'not_found': not_found_count,
            'duplicates': len(codes_duplicated),
            'duplicate_list': list(codes_duplicated),
            'results': results,
            'verification_mode': True
        }
    else:
        # Modo IMPORTACIÓN real o Dry Run
        resource.before_import(dataset) # Normaliza headers si fuera necesario
        try:
            print(f"[DEBUG] [Task] Ejecutando resource.import_data. dry_run={dry_run}")
            result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False)
            
            # Recopilar errores
            detailed_errors = []
            for error in result.base_errors:
                detailed_errors.append(f"Error General: {str(error.error)}")
            
            for line, errors in result.row_errors():
                for error in errors:
                    detailed_errors.append(f"Fila {line}: {str(error.error)}")
            
            if result.invalid_rows:
                for row in result.invalid_rows:
                    detailed_errors.append(f"Fila {row.number} (Invalid): {str(row.error)}")

            if registro:
                registro.filas_nuevas = result.totals.get('new', 0)
                registro.filas_actualizadas = result.totals.get('update', 0)
                registro.filas_omitidas = result.totals.get('skip', 0)
                registro.filas_error = len(detailed_errors)
                registro.estado = 'COMPLETADO'
                if detailed_errors:
                    registro.detalles_error = "\n".join(detailed_errors[:10])
                registro.save()

            final_res = {
                'status': 'completed',
                'status_code': 'completed',
                'total': total_rows,
                'new': result.totals.get('new', 0),
                'updated': result.totals.get('update', 0),
                'skipped': result.totals.get('skip', 0),
                'errors': len(detailed_errors),
                'error_list': detailed_errors,
                'verification_mode': False,
                'dry_run': dry_run,
                'file_path': file_path
            }
        except Exception as e:
            if registro:
                registro.estado = 'ERROR'
                registro.detalles_error = str(e)
                registro.save()
            error_msg = f"Error crítico en importación: {str(e)}"
            progress_info.update({'status': 'error', 'message': error_msg})
            cache.set(cache_key, progress_info, 3600)
            return {'status': 'error', 'message': error_msg}

    # Limpiar archivo original SOLO si no es dry_run
    if not dry_run:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except:
            pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res
@shared_task(bind=True, name='mantenimiento.tasks.import_procedimientos_task')
def import_procedimientos_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Procedimientos"):
    """
    Tarea Celery para importar PROCEDIMIENTOS y PASOS.
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from .admin import PasoProcedimientoResource
    from django.core.cache import cache
    from .models import Procedimiento
    from activos.models import RegistroImportacion
    from django.contrib.auth.models import User
    import sys

    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Procedimientos',
            usuario=user,
            estado='PROCESANDO'
        )

    resource = PasoProcedimientoResource()
    cache_key = f"import_procedimientos_progress_{user_id}" if user_id else "import_procedimientos_progress_system"

    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    if registro:
        registro.total_filas = total_rows
        registro.save()

    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Procesando archivo...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)

    try:
        # Usamos PasoProcedimientoResource porque permite crear Procedimiento y Pasos
        result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False)
        
        detailed_errors = []
        for error in result.base_errors:
            detailed_errors.append(f"Error General: {str(error.error)}")
        for line, errors in result.row_errors():
            for error in errors:
                detailed_errors.append(f"Fila {line}: {str(error.error)}")

        if registro:
            registro.filas_nuevas = result.totals.get('new', 0)
            registro.filas_actualizadas = result.totals.get('update', 0)
            registro.filas_omitidas = result.totals.get('skip', 0)
            registro.filas_error = len(detailed_errors)
            registro.estado = 'COMPLETADO'
            if detailed_errors:
                registro.detalles_error = "\n".join(detailed_errors[:10])
            registro.save()

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'new': result.totals.get('new', 0),
            'updated': result.totals.get('update', 0),
            'skipped': result.totals.get('skip', 0),
            'errors': len(detailed_errors),
            'error_list': detailed_errors,
            'verification_mode': False,
            'dry_run': dry_run,
            'file_path': file_path
        }
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_msg = f"Error crítico: {str(e)}"
        cache.set(cache_key, {'status': 'error', 'message': error_msg}, 3600)
        return {'status': 'error', 'message': error_msg}

    if not dry_run:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except: pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res

@shared_task(bind=True, name='mantenimiento.tasks.import_tipos_task')
def import_tipos_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Tipos Mantenimiento"):
    """
    Tarea Celery para importar o VERIFICAR TIPOS de mantenimiento con seguimiento de progreso real.
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from django.core.cache import cache
    from .admin import TipoResource
    from .models import Tipo
    from activos.models import RegistroImportacion
    from django.contrib.auth.models import User
    import sys
    
    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Tipos (Mantenimiento)',
            usuario=user,
            estado='PROCESANDO'
        )
    
    # Marcador de progreso en caché
    cache_key = f"import_tipos_progress_{user_id}" if user_id else "import_tipos_progress_system"
    
    # Inicializar resource
    resource = TipoResource()
    resource.celery_task = self
    resource.cache_key = cache_key
    resource.total_rows = 0 # Se actualizará al cargar dataset

    # Leer archivo (con reintentos por caídas transitorias de conexión a MinIO/túnel)
    from botocore.exceptions import BotoCoreError, ClientError
    max_intentos = 4
    dataset = None
    ultimo_error = None
    for intento in range(1, max_intentos + 1):
        try:
            with default_storage.open(file_path, 'rb') as f:
                file_content = f.read()
                if file_format == 'csv':
                    dataset = Dataset().load(try_decode(file_content), format='csv')
                elif file_format in ['xls', 'xlsx']:
                    dataset = Dataset().load(file_content, format=file_format)
                else:
                    raise ValueError(f"Formato no soportado: {file_format}")
            break
        except ValueError:
            # Error de formato: no tiene sentido reintentar
            ultimo_error = sys.exc_info()[1]
            break
        except ClientError as e:
            status = (e.response or {}).get('ResponseMetadata', {}).get('HTTPStatusCode')
            ultimo_error = e
            if status == 404:
                # El objeto no existe: no reintentar
                break
            if intento < max_intentos:
                print(f"[DEBUG] [Task] Intento {intento} falló al leer archivo (conexión): {e}. Reintentando...")
                time.sleep(intento * 2)
        except (BotoCoreError, ConnectionError, OSError) as e:
            ultimo_error = e
            if intento < max_intentos:
                print(f"[DEBUG] [Task] Intento {intento} falló al leer archivo (conexión): {e}. Reintentando...")
                time.sleep(intento * 2)
        except Exception as e:
            ultimo_error = e
            break

    if dataset is None:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(ultimo_error)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(ultimo_error)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    resource.total_rows = total_rows
    if registro:
        registro.total_filas = total_rows
        registro.save()
    
    missing_dataset = Dataset()
    missing_dataset.headers = dataset.headers
    
    # Estado inicial
    progress_info = {
        'current': 0, 
        'total': total_rows, 
        'status': 'Iniciando verificacion...' if verification_mode else 'Iniciando importacion...', 
        'percent': 0,
        'new': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'found': 0,
        'not_found': 0,
        'verification_mode': verification_mode
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)

    if verification_mode:
        results = []
        codes_seen = set()
        codes_duplicated = set()
        found_count = 0
        not_found_count = 0
        
        for i, row in enumerate(dataset.dict, start=1):
            obj_id = str(row.get('id') or '').strip()
            codigo = str(row.get('codigo') or '').strip()
            
            exists = False
            match_info = ""
            
            # 1. Intentar buscar por ID (si es numérico)
            if obj_id and obj_id.isdigit():
                exists = Tipo.objects.filter(id=obj_id).exists()
                if exists:
                    match_info = f"ID {obj_id}"
            
            # 2. Si no se encontró por ID, intentar por Código
            if not exists and codigo:
                if codigo in codes_seen:
                    codes_duplicated.add(codigo)
                    status = "REPETIDO EN ARCHIVO"
                else:
                    codes_seen.add(codigo)
                    exists = Tipo.objects.filter(codigo=codigo).exists()
                    if exists:
                        match_info = f"Código {codigo}"
            
            if exists:
                found_count += 1
                status = f"EXISTE ({match_info})"
            elif not obj_id and not codigo:
                status = "SIN IDENTIFICADOR (ID o Código)"
                not_found_count += 1
                missing_dataset.append(dataset[i-1])
            else:
                status = "NO EXISTE (Nuevo)"
                not_found_count += 1
                missing_dataset.append(dataset[i-1])
            
            results.append(f"Fila {i}: {status}")
            
            if i % 10 == 0 or i == total_rows:
                progress_info.update({
                    'current': i,
                    'status': f'Verificando {i}/{total_rows}...',
                    'percent': int((i / total_rows) * 100),
                    'found': found_count,
                    'not_found': not_found_count,
                    'duplicates': len(codes_duplicated)
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        final_res = {
            'status': 'completed',
            'status_code': 'completed',
            'total': total_rows,
            'found': found_count,
            'not_found': not_found_count,
            'duplicates': len(codes_duplicated),
            'duplicate_list': list(codes_duplicated),
            'results': results,
            'verification_mode': True
        }
    else:
        # Modo IMPORTACIÓN real o Dry Run
        resource.before_import(dataset)
        try:
            print(f"[DEBUG] [Actual Import Tipos] Iniciando import_data con {len(dataset)} filas")
            # Usar import_data (use_transactions=True en Meta ya maneja la transacción)
            result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False)
            print(f"[DEBUG] [Actual Import Tipos] import_data finalizado: {result.totals}")
            
            detailed_errors = []
            for error in result.base_errors:
                detailed_errors.append(f"Error General: {str(error.error)}")
            for line, errors in result.row_errors():
                for error in errors:
                    detailed_errors.append(f"Fila {line}: {str(error.error)}")

            if registro:
                registro.filas_nuevas = result.totals.get('new', 0)
                registro.filas_actualizadas = result.totals.get('update', 0)
                registro.filas_omitidas = result.totals.get('skip', 0)
                registro.filas_error = len(detailed_errors)
                registro.estado = 'COMPLETADO'
                if detailed_errors:
                    registro.detalles_error = "\n".join(detailed_errors[:50])
                registro.save()

            final_res = {
                'status': 'completed',
                'status_code': 'completed',
                'total': total_rows,
                'new': result.totals.get('new', 0),
                'updated': result.totals.get('update', 0),
                'skipped': result.totals.get('skip', 0),
                'errors': len(detailed_errors),
                'error_list': detailed_errors,
                'verification_mode': False,
                'dry_run': dry_run,
                'file_path': file_path
            }
        except Exception as e:
            if registro:
                registro.estado = 'ERROR'
                registro.detalles_error = str(e)
                registro.save()
            error_msg = f"Error crítico en importación: {str(e)}"
            print(f"[ERROR] [Pasos] {error_msg}")
            progress_info.update({'status': 'error', 'message': error_msg})
            cache.set(cache_key, progress_info, 3600)
            return {'status': 'error', 'message': error_msg}

    # Limpiar archivo original SOLO si no es dry_run y no es verificacion o si falló
    if not dry_run and not verification_mode:
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        except:
            pass
        
    cache.set(cache_key, final_res, 3600)
    return final_res



@shared_task(name='mantenimiento.tasks.task_generar_ot_pdf')
def task_generar_ot_pdf(ot_id):
    """
    Tarea asíncrona para generar y guardar el PDF de una OT.
    """
    try:
        logger.info(f"Iniciando generación de PDF para OT #{ot_id}")
        WorkOrderService.save_ot_pdf_as_attachment(ot_id)
        logger.info(f"PDF para OT #{ot_id} generado exitosamente.")
        return {'status': 'success', 'ot_id': ot_id}
    except Exception as e:
        logger.error(f"Error generando PDF para OT #{ot_id}: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

@shared_task(name='mantenimiento.tasks.notify_responsible_n8n')
def notify_responsible_n8n(aviso_id):
    """
    Envía una notificación al responsable de un aviso vía n8n.
    """
    from .models import Aviso
    import requests
    from django.conf import settings
    
    try:
        aviso = Aviso.objects.select_related('responsable', 'ubicacion', 'solicitante').get(id=aviso_id)
        
        if not aviso.responsable:
            return {"status": "error", "message": "El aviso no tiene un responsable asignado."}
            
        n8n_url = getattr(settings, 'N8N_AVISOS_WEBHOOK_URL', None)
        
        # Si estamos en local y la URL no contiene 'webhook-test', la ajustamos para pruebas
        if settings.IS_LOCAL and n8n_url and '/webhook/' in n8n_url:
            n8n_url = n8n_url.replace('/webhook/', '/webhook-test/')
            
        # Generar reporte PDF
        pdf_base64 = ""
        try:
            from django.template.loader import get_template
            from xhtml2pdf import pisa
            from io import BytesIO
            import base64
            from django.utils import timezone
            
            template = get_template('mantenimiento/pdf/aviso_report.html')
            context = {'aviso': aviso, 'hoy': timezone.now()}
            html = template.render(context)
            
            result = BytesIO()
            pisa_status = pisa.CreatePDF(html, dest=result)
            
            if not pisa_status.err:
                pdf_base64 = base64.b64encode(result.getvalue()).decode('utf-8')
        except Exception as pdf_err:
            print(f"[ERROR] [PDF] Fallo al generar reporte: {str(pdf_err)}")

        payload = {
            'aviso_id': aviso.id,
            'titulo': f"AV-{aviso.id}",
            'descripcion': aviso.descripcion,
            'prioridad': aviso.prioridad,
            'ubicacion': aviso.ubicacion.nombre if aviso.ubicacion else "No especificada",
            'solicitante': aviso.solicitante.get_full_name() or aviso.solicitante.username if aviso.solicitante else "Sistema",
            'responsable_email': aviso.responsable.email,
            'responsable_nombre': aviso.responsable.get_full_name() or aviso.responsable.username,
            'responsable_telefono': aviso.responsable.perfil.telefono if hasattr(aviso.responsable, 'perfil') else '',
            'creado_en': aviso.creado_en.isoformat(),
            'url_detalle': f"{settings.SITE_URL}/admin/mantenimiento/aviso/{aviso.id}/change/",
            'pdf_report': pdf_base64, # PDF en base64 para que n8n lo procese
            'has_images': bool(aviso.foto or aviso.fotos.exists()),
            'foto_principal': f"{settings.SITE_URL}{aviso.foto.url}" if aviso.foto else ""
        }

        # Intentar primero con localhost, si falla o es 404, intentar con la IP de la captura
        urls_a_probar = [n8n_url]
        public_ip_url = n8n_url.replace('localhost', '181.115.47.107')
        if public_ip_url not in urls_a_probar:
            urls_a_probar.append(public_ip_url)

        last_error = ""
        for current_url in urls_a_probar:
            try:
                print(f"[DEBUG] [N8N] Intentando notificación a: {current_url}")
                response = requests.post(current_url, json=payload, timeout=5)
                if response.status_code in [200, 201]:
                    return {"status": "success", "message": f"Notificación enviada a {payload['responsable_nombre']} vía {current_url}"}
                last_error = f"Error {response.status_code} en {current_url}"
            except Exception as e:
                last_error = f"Fallo de conexión a {current_url}: {str(e)}"

        return {
            "status": "error", 
            "message": f"No se pudo conectar con n8n después de varios intentos. Último error: {last_error}",
            "urls_intentadas": urls_a_probar
        }
            
    except Exception as e:
        return {"status": "error", "message": str(e)}


@shared_task(bind=True, name='mantenimiento.tasks.generar_embeddings_ordenes')
def generar_embeddings_ordenes(self, batch_size=100):
    """
    Genera embeddings para todas las OrdenTrabajo que no tengan embedding.
    Usa Ollama local (nomic-embed-text) para velocidad sin rate limits.
    """
    import requests as http_requests
    from .models import OrdenTrabajo

    OLLAMA_URL = "http://localhost:11434"
    OLLAMA_MODEL = "nomic-embed-text"

    # Verificar Ollama
    try:
        r = http_requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if r.status_code != 200:
            logger.error("Ollama no disponible.")
            return {'status': 'error', 'message': 'Ollama no disponible'}
    except Exception:
        logger.error("Ollama no disponible.")
        return {'status': 'error', 'message': 'Ollama no disponible'}

    ordenes = list(OrdenTrabajo.objects.filter(embedding__isnull=True).select_related(
        'rutina', 'ubicacion', 'falla', 'aviso'
    ).prefetch_related('activos')[:5000])

    total = len(ordenes)
    if total == 0:
        return {'current': 0, 'total': 0, 'percent': 100, 'status': 'Todas las OTs ya tienen embedding.'}

    self.update_state(state='PROGRESS', meta={
        'current': 0, 'total': total, 'percent': 0,
        'status': f'Iniciando... {total} OTs pendientes'
    })

    procesados = 0

    for i in range(0, total, batch_size):
        batch = ordenes[i:i + batch_size]
        textos = [ot.texto_para_embedding() for ot in batch]

        try:
            response = http_requests.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": OLLAMA_MODEL, "input": textos},
                timeout=120
            )

            if response.status_code == 200:
                embeddings = response.json()['embeddings']
                for ot, emb in zip(batch, embeddings):
                    ot.embedding = emb
                OrdenTrabajo.objects.bulk_update(batch, ['embedding'], batch_size=100)
                procesados += len(batch)
            else:
                logger.error(f"Error Ollama ({response.status_code}): {response.text[:200]}")
                procesados += len(batch)
        except Exception as e:
            logger.error(f"Error generando embeddings OTs: {e}")
            procesados += len(batch)

        percent = int((procesados / total) * 100)
        self.update_state(state='PROGRESS', meta={
            'current': procesados, 'total': total, 'percent': percent,
            'status': f'Procesados {procesados}/{total} OTs ({percent}%)'
        })

    return {'current': procesados, 'total': total, 'percent': 100,
            'status': f'✅ {procesados}/{total} OTs vectorizadas.'}


# =============================================================================
# IMPORTACIÓN UNIFICADA (ÁRBOL): Categorías -> Rutinas -> Actividades (Pasos)
# =============================================================================

def _parse_duracion_flexible(value):
    """Convierte HH:MM, HH:MM:SS, time, decimal (horas) o timedelta a timedelta."""
    import datetime as _dt
    if value is None:
        return None
    if isinstance(value, _dt.timedelta):
        return value
    if isinstance(value, _dt.time):
        return _dt.timedelta(hours=value.hour, minutes=value.minute, seconds=value.second)
    val_str = str(value).strip()
    if not val_str or val_str.lower() in ('none', 'nan', 'null'):
        return None
    if val_str.count(':') == 1:
        try:
            h, m = val_str.split(':')
            return _dt.timedelta(hours=int(h), minutes=int(m))
        except (ValueError, TypeError):
            pass
    if val_str.count(':') == 2:
        try:
            h, m, s = val_str.split(':')
            return _dt.timedelta(hours=int(h), minutes=int(m), seconds=int(s))
        except (ValueError, TypeError):
            pass
    try:
        return _dt.timedelta(hours=float(val_str.replace(',', '.')))
    except (ValueError, TypeError):
        return None


def _clean_str(value):
    """Normaliza un valor de celda a string limpio o None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ('none', 'nan', 'null'):
        return None
    return s


# Mapeo de etiquetas amigables -> claves internas de tipo_respuesta
TIPO_RESPUESTA_MAP = {
    'instruccion': 'INSTRUCCION', 'instrucción': 'INSTRUCCION', 'solo lectura': 'INSTRUCCION',
    'check': 'CHECK', 'si/no': 'CHECK', 'si/no/na': 'CHECK',
    'numerico': 'NUMERICO', 'numérico': 'NUMERICO', 'valor numerico': 'NUMERICO', 'valor numérico': 'NUMERICO',
    'texto': 'TEXTO', 'texto libre': 'TEXTO',
    'medicion': 'MEDICION', 'medición': 'MEDICION', 'punto de medicion': 'MEDICION', 'sap': 'MEDICION',
    'foto': 'FOTO', 'registro fotografico': 'FOTO', 'registro fotográfico': 'FOTO',
    'header': 'HEADER', 'encabezado': 'HEADER', 'grupo': 'HEADER', 'encabezado / grupo': 'HEADER',
}


def _normalizar_tipo_respuesta(value):
    s = _clean_str(value)
    if not s:
        return 'INSTRUCCION'
    return TIPO_RESPUESTA_MAP.get(s.lower(), s.upper())


@shared_task(bind=True, name='mantenimiento.tasks.import_arbol_task')
def import_arbol_task(self, file_path, file_format, user_id=None, verification_mode=False, dry_run=False, import_name="Importación Árbol"):
    """
    Importación jerárquica UNIFICADA en un solo archivo.

    Cada fila representa una ACTIVIDAD (paso) y arrastra el contexto de su
    categoría y rutina. Las columnas de categoría/rutina pueden repetirse o
    dejarse vacías (se hereda de la fila anterior con el mismo agrupador).

    Columnas soportadas (ver plantilla):
      - categoria_ruta      : Ruta completa separada por ">" (ej: "Eléctrica > Motores")
      - categoria_codigo    : (Opcional) Código único de la categoría hoja
      - rutina_codigo       : Código único de la rutina (identificador para upsert)
      - rutina_nombre       : Nombre de la rutina (opcional, autogenerado si vacío)
      - frecuencia          : Nombre de frecuencia existente (ej: "Mensual")
      - tiempo_estimado     : HH:MM / HH:MM:SS / horas decimales
      - cantidad_tecnicos   : Entero
      - rutina_descripcion  : Texto
      - paso_orden          : Orden del paso (entero)
      - paso_descripcion    : Descripción de la actividad/paso
      - paso_tipo           : INSTRUCCION / CHECK / NUMERICO / TEXTO / MEDICION / FOTO / HEADER
      - paso_verificacion   : Qué verificar
      - paso_unidad         : Unidad de medida
      - paso_valor_objetivo : Valor ideal (numérico)
      - paso_rango_min      : Rango mínimo (numérico)
      - paso_rango_max      : Rango máximo (numérico)
    """
    from tablib import Dataset
    from django.core.files.storage import default_storage
    from django.core.cache import cache
    from django.contrib.auth.models import User
    from django.db import transaction
    from .models import Tipo, Rutina, PasoRutina, Frecuencia
    from activos.models import RegistroImportacion
    import sys

    user = User.objects.get(id=user_id) if user_id else None
    registro = None
    if not verification_mode and not dry_run:
        registro = RegistroImportacion.objects.create(
            nombre=import_name,
            tipo='Árbol (Cat+Rutinas+Pasos)',
            usuario=user,
            estado='PROCESANDO'
        )

    cache_key = f"import_arbol_progress_{user_id}" if user_id else "import_arbol_progress_system"

    # Leer archivo
    try:
        with default_storage.open(file_path, 'rb') as f:
            file_content = f.read()
            if file_format == 'csv':
                dataset = Dataset().load(try_decode(file_content), format='csv')
            elif file_format in ['xls', 'xlsx']:
                dataset = Dataset().load(file_content, format=file_format)
            else:
                raise ValueError(f"Formato no soportado: {file_format}")
    except Exception as e:
        if registro:
            registro.estado = 'ERROR'
            registro.detalles_error = str(e)
            registro.save()
        error_res = {'status': 'error', 'message': f'Error al leer archivo: {str(e)}'}
        cache.set(cache_key, error_res, 3600)
        return error_res

    total_rows = len(dataset)
    if registro:
        registro.total_filas = total_rows
        registro.save()

    progress_info = {
        'current': 0, 'total': total_rows,
        'status': 'Iniciando verificación...' if verification_mode else 'Iniciando importación...',
        'percent': 0,
        'cats_new': 0, 'rutinas_new': 0, 'rutinas_updated': 0, 'pasos_new': 0, 'pasos_updated': 0,
        'errors': 0, 'verification_mode': verification_mode,
    }
    cache.set(cache_key, progress_info, 3600)
    self.update_state(state='PROGRESS', meta=progress_info)
    sys.stdout.flush()

    rows = list(dataset.dict)

    # ------------------------------------------------------------------
    # MODO VERIFICACIÓN / DRY RUN (solo análisis, sin escribir)
    # ------------------------------------------------------------------
    if verification_mode or dry_run:
        results = []
        cats_a_crear = set()
        cats_existentes = set()
        rutinas_a_crear = set()
        rutinas_a_actualizar = set()
        pasos_count = 0
        errores = []
        frecuencias_faltantes = set()

        # Cache de rutas de categorías existentes
        tipos_qs = list(Tipo.objects.all())
        tipos_por_id = {t.id: t for t in tipos_qs}

        def ruta_de(t):
            path = [t.nombre]
            cur = t.padre_id
            while cur and cur in tipos_por_id:
                p = tipos_por_id[cur]
                path.append(p.nombre)
                cur = p.padre_id
            return ' > '.join(reversed(path)).lower()

        rutas_existentes = {ruta_de(t) for t in tipos_qs}
        codigos_rutina_existentes = set(
            Rutina.objects.exclude(codigo_rutina__isnull=True).values_list('codigo_rutina', flat=True)
        )
        frecuencias_existentes = {f.nombre.lower() for f in Frecuencia.objects.all()}

        rutas_vistas_archivo = set()

        for i, row in enumerate(rows, start=1):
            cat_ruta = _clean_str(row.get('categoria_ruta'))
            rutina_codigo = _clean_str(row.get('rutina_codigo'))
            frecuencia = _clean_str(row.get('frecuencia'))
            paso_desc = _clean_str(row.get('paso_descripcion'))

            fila_msgs = []

            # Categorías (por ruta)
            if cat_ruta:
                partes = [p.strip() for p in cat_ruta.replace('→', '>').split('>') if p.strip()]
                acumulada = []
                for parte in partes:
                    acumulada.append(parte.lower())
                    clave = ' > '.join(acumulada)
                    if clave in rutas_existentes or clave in rutas_vistas_archivo:
                        pass
                    else:
                        cats_a_crear.add(clave)
                        rutas_vistas_archivo.add(clave)
                if ' > '.join([p.lower() for p in partes]) in rutas_existentes:
                    cats_existentes.add(cat_ruta.lower())
                fila_msgs.append(f"Cat '{cat_ruta}'")
            else:
                errores.append(f"Fila {i}: sin 'categoria_ruta'")

            # Frecuencia
            if frecuencia and frecuencia.lower() not in frecuencias_existentes:
                frecuencias_faltantes.add(frecuencia)

            # Rutina
            if rutina_codigo:
                if rutina_codigo in codigos_rutina_existentes:
                    rutinas_a_actualizar.add(rutina_codigo)
                else:
                    rutinas_a_crear.add(rutina_codigo)
                fila_msgs.append(f"Rutina '{rutina_codigo}'")

            # Paso
            if paso_desc:
                pasos_count += 1
                fila_msgs.append(f"Paso '{paso_desc[:30]}'")

            results.append(f"Fila {i}: " + " | ".join(fila_msgs) if fila_msgs else f"Fila {i}: (vacía)")

            if i % 20 == 0 or i == total_rows:
                progress_info.update({
                    'current': i, 'percent': int((i / total_rows) * 100) if total_rows else 100,
                    'status': f'Analizando {i}/{total_rows}...',
                })
                cache.set(cache_key, progress_info, 3600)
                self.update_state(state='PROGRESS', meta=progress_info)

        if frecuencias_faltantes:
            errores.append("Frecuencias inexistentes (créalas primero): " + ", ".join(sorted(frecuencias_faltantes)))

        final_res = {
            'status': 'completed', 'status_code': 'completed',
            'total': total_rows,
            'cats_new': len(cats_a_crear),
            'rutinas_new': len(rutinas_a_crear),
            'rutinas_updated': len(rutinas_a_actualizar),
            'pasos_new': pasos_count,
            'errors': len(errores),
            'error_list': errores,
            'results': results,
            'verification_mode': verification_mode,
            'dry_run': dry_run,
            'file_path': file_path,
        }
        cache.set(cache_key, final_res, 3600)
        return final_res

    # ------------------------------------------------------------------
    # MODO IMPORTACIÓN REAL
    # ------------------------------------------------------------------
    cats_new = 0
    rutinas_new = 0
    rutinas_updated = 0
    pasos_new = 0
    pasos_updated = 0
    errores = []

    # Cache de frecuencias por nombre (case-insensitive)
    frecuencias_map = {f.nombre.lower(): f for f in Frecuencia.objects.all()}

    # Cache de categorías por ruta (case-insensitive)
    tipos_qs = list(Tipo.objects.all())
    tipos_por_id = {t.id: t for t in tipos_qs}

    def _ruta_key(t):
        path = [t.nombre]
        cur = t.padre_id
        while cur and cur in tipos_por_id:
            p = tipos_por_id[cur]
            path.append(p.nombre)
            cur = p.padre_id
        return ' > '.join(reversed(path)).lower()

    tipo_por_ruta = {_ruta_key(t): t for t in tipos_qs}

    def obtener_o_crear_tipo(cat_ruta, codigo_hoja=None):
        """Resuelve/crea toda la cadena de categorías por su ruta y devuelve la hoja."""
        nonlocal cats_new
        partes = [p.strip() for p in cat_ruta.replace('→', '>').split('>') if p.strip()]
        padre = None
        acumulada = []
        nodo = None
        for idx, parte in enumerate(partes):
            acumulada.append(parte.lower())
            clave = ' > '.join(acumulada)
            nodo = tipo_por_ruta.get(clave)
            if not nodo:
                nodo = Tipo.objects.create(nombre=parte, padre=padre)
                cats_new += 1
                tipo_por_ruta[clave] = nodo
                tipos_por_id[nodo.id] = nodo
            padre = nodo
        # Asignar código a la hoja si viene y no lo tenía
        if nodo and codigo_hoja and not nodo.codigo:
            try:
                nodo.codigo = codigo_hoja
                nodo.save(update_fields=['codigo'])
            except Exception:
                pass
        return nodo

    for i, row in enumerate(rows, start=1):
        try:
            with transaction.atomic():
                cat_ruta = _clean_str(row.get('categoria_ruta'))
                if not cat_ruta:
                    errores.append(f"Fila {i}: sin 'categoria_ruta', se omite")
                    continue

                cat_codigo = _clean_str(row.get('categoria_codigo'))
                tipo_obj = obtener_o_crear_tipo(cat_ruta, cat_codigo)

                # ---- RUTINA ----
                rutina_codigo = _clean_str(row.get('rutina_codigo'))
                rutina_obj = None
                if rutina_codigo:
                    rutina_obj = Rutina.objects.filter(codigo_rutina=rutina_codigo).first()
                    frecuencia_nombre = _clean_str(row.get('frecuencia'))
                    frecuencia_obj = frecuencias_map.get(frecuencia_nombre.lower()) if frecuencia_nombre else None

                    defaults = {
                        'tipo': tipo_obj,
                    }
                    nombre = _clean_str(row.get('rutina_nombre'))
                    if nombre:
                        defaults['nombre'] = nombre
                    if frecuencia_obj:
                        defaults['frecuencia'] = frecuencia_obj
                    tiempo = _parse_duracion_flexible(row.get('tiempo_estimado'))
                    if tiempo is not None:
                        defaults['tiempo_estimado'] = tiempo
                    cant = _clean_str(row.get('cantidad_tecnicos'))
                    if cant:
                        try:
                            defaults['cantidad_tecnicos'] = int(float(cant))
                        except (ValueError, TypeError):
                            pass
                    desc = _clean_str(row.get('rutina_descripcion'))
                    if desc:
                        defaults['descripcion'] = desc

                    if rutina_obj:
                        for k, v in defaults.items():
                            setattr(rutina_obj, k, v)
                        rutina_obj.save()
                        rutinas_updated += 1
                    else:
                        rutina_obj = Rutina.objects.create(codigo_rutina=rutina_codigo, **defaults)
                        rutinas_new += 1

                # ---- PASO (ACTIVIDAD) ----
                paso_desc = _clean_str(row.get('paso_descripcion'))
                if paso_desc and rutina_obj:
                    orden_raw = _clean_str(row.get('paso_orden'))
                    try:
                        orden = int(float(orden_raw)) if orden_raw else 0
                    except (ValueError, TypeError):
                        orden = 0

                    def _num(key):
                        v = _clean_str(row.get(key))
                        if v is None:
                            return None
                        try:
                            return float(v.replace(',', '.'))
                        except (ValueError, TypeError):
                            return None

                    paso_defaults = {
                        'descripcion': paso_desc,
                        'tipo_respuesta': _normalizar_tipo_respuesta(row.get('paso_tipo')),
                        'verificacion': _clean_str(row.get('paso_verificacion')),
                        'unidad_medida': _clean_str(row.get('paso_unidad')),
                        'valor_objetivo': _num('paso_valor_objetivo'),
                        'rango_min': _num('paso_rango_min'),
                        'rango_max': _num('paso_rango_max'),
                    }

                    paso_existente = PasoRutina.objects.filter(rutina=rutina_obj, orden=orden).first()
                    if paso_existente:
                        for k, v in paso_defaults.items():
                            setattr(paso_existente, k, v)
                        paso_existente.save()
                        pasos_updated += 1
                    else:
                        PasoRutina.objects.create(rutina=rutina_obj, orden=orden, **paso_defaults)
                        pasos_new += 1
                elif paso_desc and not rutina_obj:
                    errores.append(f"Fila {i}: hay paso pero no hay 'rutina_codigo' para vincularlo")

        except Exception as e:
            errores.append(f"Fila {i}: {str(e)}")

        if i % 10 == 0 or i == total_rows:
            progress_info.update({
                'current': i, 'percent': int((i / total_rows) * 100) if total_rows else 100,
                'status': f'Importando {i}/{total_rows}...',
                'cats_new': cats_new, 'rutinas_new': rutinas_new, 'rutinas_updated': rutinas_updated,
                'pasos_new': pasos_new, 'pasos_updated': pasos_updated, 'errors': len(errores),
            })
            cache.set(cache_key, progress_info, 3600)
            self.update_state(state='PROGRESS', meta=progress_info)

    if registro:
        registro.filas_nuevas = rutinas_new + pasos_new + cats_new
        registro.filas_actualizadas = rutinas_updated + pasos_updated
        registro.filas_error = len(errores)
        registro.estado = 'COMPLETADO'
        if errores:
            registro.detalles_error = "\n".join(errores[:50])
        registro.save()

    # Limpiar archivo temporal
    try:
        if default_storage.exists(file_path):
            default_storage.delete(file_path)
    except Exception:
        pass

    final_res = {
        'status': 'completed', 'status_code': 'completed',
        'total': total_rows,
        'cats_new': cats_new,
        'rutinas_new': rutinas_new,
        'rutinas_updated': rutinas_updated,
        'pasos_new': pasos_new,
        'pasos_updated': pasos_updated,
        'errors': len(errores),
        'error_list': errores,
        'verification_mode': False,
        'dry_run': False,
    }
    cache.set(cache_key, final_res, 3600)
    return final_res
