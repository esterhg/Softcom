import time
import os
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from celery.result import AsyncResult
from django.views.decorators.csrf import csrf_exempt

from ..tasks import import_arbol_task


# Columnas de la plantilla unificada (orden importa para la exportación)
TEMPLATE_HEADERS = [
    'categoria_ruta',
    'categoria_codigo',
    'rutina_codigo',
    'rutina_nombre',
    'frecuencia',
    'tiempo_estimado',
    'cantidad_tecnicos',
    'rutina_descripcion',
    'paso_orden',
    'paso_descripcion',
    'paso_tipo',
    'paso_verificacion',
    'paso_unidad',
    'paso_valor_objetivo',
    'paso_rango_min',
    'paso_rango_max',
]

# Filas de ejemplo para orientar al usuario
TEMPLATE_EXAMPLES = [
    # cat_ruta, cat_codigo, rut_codigo, rut_nombre, frec, tiempo, cant, rut_desc, orden, paso_desc, paso_tipo, paso_verif, unidad, obj, min, max
    ['Eléctrica > Transformadores', 'CAT-TR', 'RUT-TR-001', 'Inspección mensual de transformadores', 'Mensual', '01:00:00', 1, 'Inspección visual y de temperatura', 1, 'Verificar nivel de aceite', 'CHECK', '¿Nivel dentro de rango?', '', '', '', ''],
    ['Eléctrica > Transformadores', 'CAT-TR', 'RUT-TR-001', '', '', '', '', '', 2, 'Medir temperatura del devanado', 'NUMERICO', 'Temperatura', '°C', 65, 0, 90],
    ['Eléctrica > Transformadores', 'CAT-TR', 'RUT-TR-001', '', '', '', '', '', 3, 'Tomar foto de la placa', 'FOTO', 'Placa legible', '', '', '', ''],
    ['Climatización > Aires Acondicionados', 'CAT-AA', 'RUT-AA-001', 'Limpieza de filtros', 'Semanal', '00:30:00', 2, 'Limpieza y revisión de filtros', 1, 'Retirar y limpiar filtros', 'INSTRUCCION', '', '', '', '', ''],
]


@staff_member_required
def import_arbol_background(request):
    """Renderiza el formulario de carga masiva unificada (Categorías + Rutinas + Actividades)."""
    from django.contrib import admin
    context = {
        **admin.site.each_context(request),
        'title': 'Carga Masiva Unificada (Categorías + Rutinas + Actividades)',
    }
    return render(request, 'admin/mantenimiento/arbol/import_background.html', context)


@staff_member_required
@csrf_exempt
def import_arbol_process(request):
    """Dispara la tarea Celery de importación jerárquica unificada."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    is_confirm = request.POST.get('confirm', '').lower() in ['true', 'on', '1']
    existing_path = request.POST.get('file_path')
    import_file = request.FILES.get('import_file')

    if not is_confirm:
        if not import_file:
            return JsonResponse({'error': 'No se subió ningún archivo'}, status=400)
        file_ext = import_file.name.split('.')[-1].lower()
        temp_name = f'tmp/import_arbol_{request.user.id}_{int(time.time())}.{file_ext}'
        try:
            path = default_storage.save(temp_name, import_file)
        except Exception as e:
            return JsonResponse({'error': f'Error al guardar archivo: {str(e)}'}, status=500)
    else:
        if not existing_path:
            return JsonResponse({'error': 'Falta la ruta del archivo para confirmar'}, status=400)
        path = existing_path
        file_ext = path.split('.')[-1].lower()

    cache_key = f"import_arbol_progress_{request.user.id}"
    cache.delete(cache_key)

    verification_mode = request.POST.get('verification_mode', '').lower() in ['true', 'on', '1']
    # Dry run solo en el primer paso (preview), no en verificación ni confirmación
    dry_run = (not verification_mode) and (not is_confirm)

    import_name = request.POST.get('name') or f"Árbol: {import_file.name if import_file else os.path.basename(path)}"

    task = import_arbol_task.delay(
        path,
        file_ext,
        user_id=request.user.id,
        verification_mode=verification_mode,
        dry_run=dry_run,
        import_name=import_name,
    )

    return JsonResponse({
        'status': 'started',
        'task_id': task.id,
        'dry_run': dry_run,
        'verification_mode': verification_mode,
    })


@staff_member_required
def import_arbol_progress(request):
    """API de sondeo del progreso de la importación unificada."""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'Falta task_id'}, status=400)

    cache_key = f"import_arbol_progress_{request.user.id}"
    progress = cache.get(cache_key, {'status': 'pending', 'percent': 0})

    res = AsyncResult(task_id)
    if res.state == 'SUCCESS':
        if isinstance(res.result, dict):
            progress.update(res.result)
        progress['state'] = 'COMPLETED'
        progress['percent'] = 100
    elif res.state == 'FAILURE':
        progress['error'] = str(res.result)
        progress['message'] = f"Error crítico en Celery: {str(res.result)}"
        progress['state'] = 'FAILURE'
    elif res.state == 'PROGRESS':
        if isinstance(res.info, dict):
            progress.update(res.info)
        progress['state'] = 'PROGRESS'
    else:
        progress['state'] = res.state if res else 'PENDING'

    return JsonResponse(progress)


@staff_member_required
def download_arbol_template(request):
    """Genera y descarga la plantilla unificada con encabezados y filas de ejemplo."""
    from tablib import Dataset

    export_format = request.GET.get('format', 'xlsx')
    incluir_ejemplos = request.GET.get('ejemplos', '1') != '0'

    dataset = Dataset()
    dataset.headers = TEMPLATE_HEADERS
    if incluir_ejemplos:
        for row in TEMPLATE_EXAMPLES:
            dataset.append(row)

    if export_format == 'csv':
        response = HttpResponse(dataset.csv, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="plantilla_arbol_mantenimiento.csv"'
    else:
        response = HttpResponse(
            dataset.xlsx,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_arbol_mantenimiento.xlsx"'

    return response
