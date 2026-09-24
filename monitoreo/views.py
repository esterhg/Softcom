import base64
import io
import json
import logging
import os
import zipfile

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Elevador, FotoAnexoReporte, FilaReporteElevador, ReporteElevador

logger = logging.getLogger(__name__)


# ============================================================================
# Listado principal
# ============================================================================

@staff_member_required
def reportes_lista(request):
    qs = (
        ReporteElevador.objects
        .select_related('supervisor', 'tecnico', 'creado_por')
        .order_by('-fecha_hora')
    )

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(supervisor__first_name__icontains=q) |
            Q(supervisor__last_name__icontains=q) |
            Q(supervisor_nombre_manual__icontains=q) |
            Q(tecnico__first_name__icontains=q) |
            Q(tecnico_nombre_manual__icontains=q) |
            Q(observaciones_generales__icontains=q)
        )

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'monitoreo/reportes_lista.html', {
        'title': 'Monitoreo de Elevadores',
        'page_obj': page_obj,
        'q': q,
        'total': qs.count(),
    })


# ============================================================================
# Historial de reportes (con filtro por mes y descarga ZIP)
# ============================================================================

@staff_member_required
def historial_reportes(request):
    """
    Vista de historial: tabla con todos los reportes, filtro por mes/año,
    descarga individual de PDF y descarga masiva en ZIP por mes.
    """
    # --- Rango de años disponibles ---
    from django.db.models.functions import TruncMonth
    from django.db.models import Count

    anio_sel  = request.GET.get('anio', '')
    mes_sel   = request.GET.get('mes', '')

    qs = (
        ReporteElevador.objects
        .select_related('supervisor', 'tecnico', 'creado_por')
        .order_by('-fecha_hora')
    )

    if anio_sel:
        try:
            qs = qs.filter(fecha_hora__year=int(anio_sel))
        except ValueError:
            pass
    if mes_sel:
        try:
            qs = qs.filter(fecha_hora__month=int(mes_sel))
        except ValueError:
            pass

    # Años disponibles para el selector
    from django.db.models import ExtractYear
    anios_disponibles = (
        ReporteElevador.objects
        .annotate(anio=ExtractYear('fecha_hora'))
        .values_list('anio', flat=True)
        .distinct()
        .order_by('-anio')
    )

    MESES = [
        (1,'Enero'),(2,'Febrero'),(3,'Marzo'),(4,'Abril'),
        (5,'Mayo'),(6,'Junio'),(7,'Julio'),(8,'Agosto'),
        (9,'Septiembre'),(10,'Octubre'),(11,'Noviembre'),(12,'Diciembre'),
    ]

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'monitoreo/historial_reportes.html', {
        'title': 'Historial de Reportes — Elevadores',
        'page_obj': page_obj,
        'total': qs.count(),
        'anio_sel': anio_sel,
        'mes_sel': mes_sel,
        'anios_disponibles': list(anios_disponibles),
        'MESES': MESES,
    })


# ============================================================================
# Descarga ZIP de PDFs por mes
# ============================================================================

@staff_member_required
def historial_descargar_zip(request):
    """
    Genera y descarga un ZIP con todos los PDFs del mes/año indicado.
    Si el PDF ya está guardado en storage lo usa; si no, lo genera al vuelo.
    """
    anio = request.GET.get('anio', '')
    mes  = request.GET.get('mes', '')

    if not anio or not mes:
        messages.error(request, 'Debes seleccionar mes y año para descargar.')
        return redirect('monitoreo:historial_reportes')

    try:
        anio_int = int(anio)
        mes_int  = int(mes)
    except ValueError:
        messages.error(request, 'Mes o año inválido.')
        return redirect('monitoreo:historial_reportes')

    qs = (
        ReporteElevador.objects
        .prefetch_related('filas__elevador', 'fotos')
        .select_related('supervisor', 'tecnico', 'creado_por')
        .filter(fecha_hora__year=anio_int, fecha_hora__month=mes_int)
        .order_by('fecha_hora')
    )

    if not qs.exists():
        messages.warning(request, 'No hay reportes para el período seleccionado.')
        return redirect('monitoreo:historial_reportes')

    NOMBRES_MES = {
        1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',
        7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre',
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for reporte in qs:
            try:
                pdf_bytes = _obtener_o_generar_pdf(reporte, request)
                fecha_str = reporte.fecha_hora.strftime('%Y-%m-%d_%H%M')
                nombre_archivo = f'Reporte_{reporte.pk}_{fecha_str}.pdf'
                zf.writestr(nombre_archivo, pdf_bytes)
            except Exception as exc:
                logger.error('Error al incluir reporte %s en ZIP: %s', reporte.pk, exc)

    zip_buffer.seek(0)
    nombre_zip = f'Reportes_Elevadores_{NOMBRES_MES.get(mes_int, mes)}_{anio}.zip'
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{nombre_zip}"'
    return response


# ============================================================================
# Crear reporte
# ============================================================================

@staff_member_required
def reporte_crear(request):
    elevadores = Elevador.objects.filter(activo=True).order_by('orden', 'nombre')
    usuarios   = User.objects.filter(is_active=True).order_by('first_name', 'last_name')

    if request.method == 'POST':
        try:
            reporte = _procesar_form_reporte(request, instance=None)
            messages.success(request, f'Reporte #{reporte.pk} creado correctamente.')
            return redirect('monitoreo:reporte_detalle', pk=reporte.pk)
        except Exception as exc:
            logger.exception('Error creando reporte de elevadores')
            messages.error(request, f'Error al guardar el reporte: {exc}')

    return render(request, 'monitoreo/reporte_form.html', {
        'title': 'Nuevo Reporte de Elevadores',
        'elevadores': elevadores,
        'usuarios': usuarios,
        'now': timezone.now(),
        'modo': 'crear',
    })


# ============================================================================
# Editar reporte
# ============================================================================

@staff_member_required
def reporte_editar(request, pk):
    reporte    = get_object_or_404(ReporteElevador, pk=pk)
    elevadores = Elevador.objects.filter(activo=True).order_by('orden', 'nombre')
    usuarios   = User.objects.filter(is_active=True).order_by('first_name', 'last_name')

    if request.method == 'POST':
        try:
            reporte = _procesar_form_reporte(request, instance=reporte)
            # Invalidar PDF guardado al editar
            if reporte.pdf_archivo:
                try:
                    reporte.pdf_archivo.delete(save=False)
                except Exception:
                    pass
                reporte.pdf_archivo = None
                reporte.save(update_fields=['pdf_archivo'])
            messages.success(request, f'Reporte #{reporte.pk} actualizado correctamente.')
            return redirect('monitoreo:reporte_detalle', pk=reporte.pk)
        except Exception as exc:
            logger.exception('Error editando reporte de elevadores')
            messages.error(request, f'Error al guardar el reporte: {exc}')

    filas_dict = {f.elevador_id: f for f in reporte.filas.select_related('elevador').order_by('orden')}

    return render(request, 'monitoreo/reporte_form.html', {
        'title': f'Editar Reporte #{reporte.pk}',
        'reporte': reporte,
        'elevadores': elevadores,
        'usuarios': usuarios,
        'filas_dict': filas_dict,
        'now': reporte.fecha_hora,
        'modo': 'editar',
    })


# ============================================================================
# Detalle del reporte
# ============================================================================

@staff_member_required
def reporte_detalle(request, pk):
    reporte = get_object_or_404(
        ReporteElevador.objects
            .select_related('supervisor', 'tecnico', 'creado_por')
            .prefetch_related('filas__elevador', 'fotos'),
        pk=pk,
    )
    return render(request, 'monitoreo/reporte_detalle.html', {
        'title': f'Reporte #{reporte.pk}',
        'reporte': reporte,
        'pdf_disponible': bool(reporte.pdf_archivo),
    })


# ============================================================================
# Eliminar reporte
# ============================================================================

@staff_member_required
@require_POST
def reporte_eliminar(request, pk):
    reporte = get_object_or_404(ReporteElevador, pk=pk)
    # Limpiar archivos guardados
    if reporte.pdf_archivo:
        try:
            reporte.pdf_archivo.delete(save=False)
        except Exception:
            pass
    reporte.delete()
    messages.success(request, 'Reporte eliminado.')
    return redirect('monitoreo:reportes_lista')


# ============================================================================
# PDF del reporte (genera + guarda en storage)
# ============================================================================

@staff_member_required
def reporte_pdf(request, pk):
    reporte = get_object_or_404(
        ReporteElevador.objects
            .select_related('supervisor', 'tecnico', 'creado_por')
            .prefetch_related('filas__elevador', 'fotos'),
        pk=pk,
    )
    try:
        pdf_bytes = _obtener_o_generar_pdf(reporte, request)
        filename  = f'Reporte_Elevadores_{reporte.pk}.pdf'
        response  = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception as exc:
        logger.exception('Error generando PDF del reporte %s', pk)
        messages.error(request, f'Error al generar el PDF: {exc}')
        return redirect('monitoreo:reporte_detalle', pk=pk)


# ============================================================================
# API: subir foto anexa (AJAX)
# ============================================================================

@staff_member_required
@require_POST
def foto_subir(request, pk):
    reporte   = get_object_or_404(ReporteElevador, pk=pk)
    imagenes  = request.FILES.getlist('imagenes')
    if not imagenes:
        return JsonResponse({'success': False, 'error': 'No se recibieron imágenes.'}, status=400)

    fotos_creadas = []
    for img in imagenes:
        foto = FotoAnexoReporte.objects.create(
            reporte=reporte,
            imagen=img,
            descripcion=request.POST.get('descripcion', ''),
            subido_por=request.user,
        )
        fotos_creadas.append({'id': foto.pk, 'url': foto.imagen.url, 'descripcion': foto.descripcion})

    return JsonResponse({'success': True, 'fotos': fotos_creadas})


# ============================================================================
# API: eliminar foto
# ============================================================================

@staff_member_required
@require_POST
def foto_eliminar(request, foto_pk):
    foto       = get_object_or_404(FotoAnexoReporte, pk=foto_pk)
    reporte_pk = foto.reporte_id
    try:
        foto.imagen.delete(save=False)
    except Exception:
        pass
    foto.delete()
    return JsonResponse({'success': True, 'reporte_pk': reporte_pk})


# ============================================================================
# API: actualizar descripción de foto
# ============================================================================

@staff_member_required
@require_POST
def foto_actualizar_descripcion(request, foto_pk):
    foto = get_object_or_404(FotoAnexoReporte, pk=foto_pk)
    data = json.loads(request.body)
    foto.descripcion = data.get('descripcion', '')
    foto.save(update_fields=['descripcion'])
    return JsonResponse({'success': True})


# ============================================================================
# Helpers privados
# ============================================================================

def _obtener_o_generar_pdf(reporte, request):
    """
    Devuelve los bytes del PDF del reporte.
    - Si ya existe en storage lo lee y devuelve (cache).
    - Si no existe lo genera con Playwright, lo guarda en storage y lo devuelve.
    """
    # ── 1. Servir desde storage si ya existe ──────────────────────────────
    if reporte.pdf_archivo:
        try:
            reporte.pdf_archivo.open('rb')
            data = reporte.pdf_archivo.read()
            reporte.pdf_archivo.close()
            if data:
                return data
        except Exception as exc:
            logger.warning('PDF guardado no legible para reporte %s: %s', reporte.pk, exc)
            # Limpia la referencia rota y regenera
            reporte.pdf_archivo = None
            reporte.save(update_fields=['pdf_archivo'])

    # ── 2. Generar con Playwright ─────────────────────────────────────────
    pdf_bytes = _generar_pdf_bytes(reporte, request)

    # ── 3. Guardar en storage ─────────────────────────────────────────────
    try:
        fecha_str   = reporte.fecha_hora.strftime('%Y%m%d_%H%M%S')
        nombre_file = f'Reporte_Elevadores_{reporte.pk}_{fecha_str}.pdf'
        reporte.pdf_archivo.save(nombre_file, ContentFile(pdf_bytes), save=True)
        logger.info('PDF reporte %s guardado en storage como %s', reporte.pk, nombre_file)
    except Exception as exc:
        logger.error('Error guardando PDF en storage para reporte %s: %s', reporte.pk, exc)

    return pdf_bytes


def _generar_pdf_bytes(reporte, request):
    """Genera el PDF usando Playwright y devuelve los bytes."""
    from django.conf import settings as django_settings
    from django.template.loader import render_to_string
    from playwright.sync_api import sync_playwright

    # Logo en base64
    logo_b64  = ''
    logo_path = os.path.join(
        django_settings.BASE_DIR, 'activos', 'static', 'activos', 'img', 'logo_operadora_cc.png'
    )
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode('utf-8')

    # Fotos en base64
    fotos_b64 = []
    for foto in reporte.fotos.all():
        try:
            foto.imagen.open('rb')
            data = foto.imagen.read()
            foto.imagen.close()
            ext  = os.path.splitext(str(foto.imagen))[-1].lower().strip('.')
            mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'gif': 'gif', 'webp': 'webp'}.get(ext, 'jpeg')
            fotos_b64.append({
                'b64': base64.b64encode(data).decode('utf-8'),
                'mime': mime,
                'descripcion': foto.descripcion,
            })
        except Exception as exc:
            logger.warning('No se pudo leer foto %s: %s', foto.pk, exc)

    html_content = render_to_string('monitoreo/reporte_pdf.html', {
        'reporte':  reporte,
        'logo_b64': logo_b64,
        'fotos_b64': fotos_b64,
    }, request=request)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu',
                  '--disable-dev-shm-usage', '--single-process'],
        )
        page = browser.new_page()
        page.set_content(html_content, wait_until='load')
        pdf_bytes = page.pdf(
            format='A4',
            print_background=True,
            margin={'top': '15mm', 'bottom': '15mm', 'left': '12mm', 'right': '12mm'},
        )
        browser.close()

    return pdf_bytes


def _procesar_form_reporte(request, instance):
    """Parsea el POST y guarda/actualiza un ReporteElevador + filas + fotos."""
    post = request.POST

    reporte = instance if instance is not None else ReporteElevador(creado_por=request.user)

    # Supervisor y Técnico — siempre texto libre (sin catálogo)
    reporte.supervisor_id            = None
    reporte.supervisor_nombre_manual = post.get('supervisor_manual', '').strip()
    reporte.tecnico_id               = None
    reporte.tecnico_nombre_manual    = post.get('tecnico_manual', '').strip()

    # Fecha/hora
    fh_str = post.get('fecha_hora', '').strip()
    if fh_str:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(fh_str)
        if dt:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            reporte.fecha_hora = dt

    reporte.observaciones_generales = post.get('observaciones_generales', '').strip()
    reporte.estado = post.get('estado', 'borrador')
    reporte.save()

    # Filas de elevadores (texto libre — sin catálogo)
    elevador_nombres = post.getlist('elevador_nombre[]')
    estados          = post.getlist('estado[]')
    clasificaciones  = post.getlist('clasificacion[]')
    descripciones    = post.getlist('descripcion_novedad[]')

    reporte.filas.all().delete()
    for idx, nombre in enumerate(elevador_nombres):
        nombre = nombre.strip()
        if not nombre:
            continue
        # Buscar o crear el elevador por nombre
        from .models import Elevador
        elevador, _ = Elevador.objects.get_or_create(
            nombre=nombre,
            defaults={'codigo': f'ELV-{nombre[:20].upper().replace(" ","-")}', 'activo': True},
        )
        FilaReporteElevador.objects.create(
            reporte=reporte,
            elevador=elevador,
            estado=estados[idx] if idx < len(estados) else 'operativo',
            clasificacion=clasificaciones[idx] if idx < len(clasificaciones) else '',
            descripcion_novedad=descripciones[idx] if idx < len(descripciones) else '',
            orden=idx,
        )

    # Fotos nuevas
    for img in request.FILES.getlist('fotos_nuevas'):
        FotoAnexoReporte.objects.create(
            reporte=reporte, imagen=img, descripcion='', subido_por=request.user,
        )

    # Fotos marcadas para eliminar
    for foto_id in post.getlist('fotos_eliminar[]'):
        if not foto_id:
            continue
        try:
            foto = FotoAnexoReporte.objects.get(pk=int(foto_id), reporte=reporte)
            try:
                foto.imagen.delete(save=False)
            except Exception:
                pass
            foto.delete()
        except FotoAnexoReporte.DoesNotExist:
            pass

    return reporte
