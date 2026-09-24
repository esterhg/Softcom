import base64
import io
import json
import logging
import os
import zipfile
from collections import defaultdict

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, ExtractYear
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from .models import Elevador, FotoAnexoReporte, FilaReporteElevador, ReporteElevador

logger = logging.getLogger(__name__)

# Orden canónico de ubicaciones para el PDF
ORDEN_UBICACIONES = [
    'Conjunto', 'Sótanos', 'Cuerpo Bajo A', 'Cuerpo Bajo B',
    'Cuerpo Bajo C', 'Torre 1', 'Torre 2',
]

MESES = [
    (1,'Enero'),(2,'Febrero'),(3,'Marzo'),(4,'Abril'),
    (5,'Mayo'),(6,'Junio'),(7,'Julio'),(8,'Agosto'),
    (9,'Septiembre'),(10,'Octubre'),(11,'Noviembre'),(12,'Diciembre'),
]


# ─────────────────────────────────────────────────────────────
# Helpers de agrupación
# ─────────────────────────────────────────────────────────────

def _agrupar_elevadores(elevadores):
    """Devuelve OrderedDict {ubicacion: [elevador, ...]} en el orden canónico."""
    grupos = defaultdict(list)
    for e in elevadores:
        grupos[e.ubicacion or 'Sin ubicación'].append(e)
    # Ordenar según el orden canónico; ubicaciones desconocidas al final
    result = {}
    for ub in ORDEN_UBICACIONES:
        if ub in grupos:
            result[ub] = grupos.pop(ub)
    result.update(grupos)  # resto al final
    return result


def _agrupar_filas(filas):
    """Devuelve OrderedDict {ubicacion: [fila, ...]} en el orden canónico."""
    grupos = defaultdict(list)
    for f in filas:
        grupos[f.elevador.ubicacion or 'Sin ubicación'].append(f)
    result = {}
    for ub in ORDEN_UBICACIONES:
        if ub in grupos:
            result[ub] = grupos.pop(ub)
    result.update(grupos)
    return result


# ─────────────────────────────────────────────────────────────
# Listado
# ─────────────────────────────────────────────────────────────

@staff_member_required
def reportes_lista(request):
    qs = (ReporteElevador.objects
          .select_related('supervisor', 'tecnico', 'creado_por')
          .order_by('-fecha_hora'))

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(supervisor_nombre_manual__icontains=q) |
            Q(tecnico_nombre_manual__icontains=q) |
            Q(observaciones_generales__icontains=q)
        )

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'monitoreo/reportes_lista.html', {
        'title': 'Monitoreo de Elevadores',
        'page_obj': page_obj,
        'q': q,
        'total': qs.count(),
    })


# ─────────────────────────────────────────────────────────────
# Historial + ZIP
# ─────────────────────────────────────────────────────────────

@staff_member_required
def historial_reportes(request):
    anio_sel = request.GET.get('anio', '')
    mes_sel  = request.GET.get('mes', '')

    qs = (ReporteElevador.objects
          .select_related('supervisor', 'tecnico', 'creado_por')
          .order_by('-fecha_hora'))

    if anio_sel:
        try: qs = qs.filter(fecha_hora__year=int(anio_sel))
        except ValueError: pass
    if mes_sel:
        try: qs = qs.filter(fecha_hora__month=int(mes_sel))
        except ValueError: pass

    anios_disponibles = (
        ReporteElevador.objects
        .annotate(anio=ExtractYear('fecha_hora'))
        .values_list('anio', flat=True).distinct().order_by('-anio')
    )

    paginator = Paginator(qs, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'monitoreo/historial_reportes.html', {
        'title': 'Historial de Reportes — Elevadores',
        'page_obj': page_obj,
        'total': qs.count(),
        'anio_sel': anio_sel,
        'mes_sel':  mes_sel,
        'anios_disponibles': list(anios_disponibles),
        'MESES': MESES,
    })


@staff_member_required
def historial_descargar_zip(request):
    anio = request.GET.get('anio', '')
    mes  = request.GET.get('mes', '')

    if not anio or not mes:
        messages.error(request, 'Selecciona mes y año.')
        return redirect('monitoreo:historial_reportes')
    try:
        anio_int, mes_int = int(anio), int(mes)
    except ValueError:
        messages.error(request, 'Período inválido.')
        return redirect('monitoreo:historial_reportes')

    qs = (ReporteElevador.objects
          .prefetch_related('filas__elevador', 'fotos')
          .select_related('supervisor', 'tecnico', 'creado_por')
          .filter(fecha_hora__year=anio_int, fecha_hora__month=mes_int)
          .order_by('fecha_hora'))

    if not qs.exists():
        messages.warning(request, 'No hay reportes para ese período.')
        return redirect('monitoreo:historial_reportes')

    NOMBRES_MES = dict(MESES)
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rpt in qs:
            try:
                pdf_bytes = _obtener_o_generar_pdf(rpt)
                zf.writestr(f'Reporte_{rpt.pk}_{rpt.fecha_hora.strftime("%Y-%m-%d_%H%M")}.pdf', pdf_bytes)
            except Exception as exc:
                logger.error('ZIP: error en reporte %s: %s', rpt.pk, exc)

    zip_buf.seek(0)
    nombre_zip = f'Reportes_Elevadores_{NOMBRES_MES.get(mes_int, mes)}_{anio}.zip'
    resp = HttpResponse(zip_buf.read(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{nombre_zip}"'
    return resp


# ─────────────────────────────────────────────────────────────
# Crear reporte
# ─────────────────────────────────────────────────────────────

@staff_member_required
def reporte_crear(request):
    elevadores       = Elevador.objects.filter(activo=True).order_by('orden', 'nombre')
    grupos_elevadores = _agrupar_elevadores(elevadores)

    if request.method == 'POST':
        try:
            reporte = _procesar_form_reporte(request, instance=None)
            # Disparar generación de PDF en background (igual que OTs)
            try:
                from .tasks import task_generar_reporte_pdf
                task_generar_reporte_pdf.delay(reporte.pk)
            except Exception as exc:
                logger.warning('No se pudo encolar PDF para reporte %s: %s', reporte.pk, exc)
            messages.success(request, f'Reporte #{reporte.pk} creado. El PDF se genera en segundo plano.')
            return redirect('monitoreo:reporte_detalle', pk=reporte.pk)
        except Exception as exc:
            logger.exception('Error creando reporte')
            messages.error(request, f'Error: {exc}')

    return render(request, 'monitoreo/reporte_form.html', {
        'title': 'Nuevo Reporte de Elevadores',
        'grupos_elevadores': grupos_elevadores,
        'now': timezone.now(),
        'modo': 'crear',
        'filas_dict': {},
    })


# ─────────────────────────────────────────────────────────────
# Editar reporte
# ─────────────────────────────────────────────────────────────

@staff_member_required
def reporte_editar(request, pk):
    reporte          = get_object_or_404(ReporteElevador, pk=pk)
    elevadores       = Elevador.objects.filter(activo=True).order_by('orden', 'nombre')
    grupos_elevadores = _agrupar_elevadores(elevadores)

    if request.method == 'POST':
        try:
            reporte = _procesar_form_reporte(request, instance=reporte)
            # Invalidar PDF guardado y regenerar
            if reporte.pdf_archivo:
                try: reporte.pdf_archivo.delete(save=False)
                except Exception: pass
                reporte.pdf_archivo = None
                reporte.save(update_fields=['pdf_archivo'])
            try:
                from .tasks import task_generar_reporte_pdf
                task_generar_reporte_pdf.delay(reporte.pk)
            except Exception as exc:
                logger.warning('No se pudo encolar PDF: %s', exc)
            messages.success(request, f'Reporte #{reporte.pk} actualizado.')
            return redirect('monitoreo:reporte_detalle', pk=reporte.pk)
        except Exception as exc:
            logger.exception('Error editando reporte')
            messages.error(request, f'Error: {exc}')

    filas_dict = {f.elevador_id: f for f in reporte.filas.select_related('elevador').order_by('orden')}

    return render(request, 'monitoreo/reporte_form.html', {
        'title': f'Editar Reporte #{reporte.pk}',
        'reporte': reporte,
        'grupos_elevadores': grupos_elevadores,
        'filas_dict': filas_dict,
        'now': reporte.fecha_hora,
        'modo': 'editar',
    })


# ─────────────────────────────────────────────────────────────
# Detalle
# ─────────────────────────────────────────────────────────────

@staff_member_required
def reporte_detalle(request, pk):
    reporte = get_object_or_404(
        ReporteElevador.objects
            .select_related('supervisor', 'tecnico', 'creado_por')
            .prefetch_related('filas__elevador', 'fotos'),
        pk=pk,
    )
    filas = list(reporte.filas.select_related('elevador').order_by('orden'))
    grupos_filas = _agrupar_filas(filas)
    novedades    = [f for f in filas if f.estado not in ('operativo', 'sin_novedad')]

    return render(request, 'monitoreo/reporte_detalle.html', {
        'title': f'Reporte #{reporte.pk}',
        'reporte': reporte,
        'grupos_filas': grupos_filas,
        'novedades': novedades,
        'pdf_disponible': bool(reporte.pdf_archivo),
    })


# ─────────────────────────────────────────────────────────────
# Eliminar
# ─────────────────────────────────────────────────────────────

@staff_member_required
@require_POST
def reporte_eliminar(request, pk):
    reporte = get_object_or_404(ReporteElevador, pk=pk)
    if reporte.pdf_archivo:
        try: reporte.pdf_archivo.delete(save=False)
        except Exception: pass
    reporte.delete()
    messages.success(request, 'Reporte eliminado.')
    return redirect('monitoreo:reportes_lista')


# ─────────────────────────────────────────────────────────────
# PDF — sirve el guardado o genera al vuelo
# ─────────────────────────────────────────────────────────────

@staff_member_required
def reporte_pdf(request, pk):
    reporte = get_object_or_404(
        ReporteElevador.objects
            .select_related('supervisor', 'tecnico', 'creado_por')
            .prefetch_related('filas__elevador', 'fotos'),
        pk=pk,
    )
    try:
        pdf_bytes = _obtener_o_generar_pdf(reporte)
        resp = HttpResponse(pdf_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = f'inline; filename="Reporte_Elevadores_{reporte.pk}.pdf"'
        return resp
    except Exception as exc:
        logger.exception('Error PDF reporte %s', pk)
        messages.error(request, f'Error al generar PDF: {exc}')
        return redirect('monitoreo:reporte_detalle', pk=pk)


# ─────────────────────────────────────────────────────────────
# API fotos
# ─────────────────────────────────────────────────────────────

@staff_member_required
@require_POST
def foto_subir(request, pk):
    reporte  = get_object_or_404(ReporteElevador, pk=pk)
    imagenes = request.FILES.getlist('imagenes')
    if not imagenes:
        return JsonResponse({'success': False, 'error': 'Sin imágenes.'}, status=400)
    fotos = []
    for img in imagenes:
        f = FotoAnexoReporte.objects.create(
            reporte=reporte, imagen=img,
            descripcion=request.POST.get('descripcion', ''),
            subido_por=request.user,
        )
        fotos.append({'id': f.pk, 'url': f.imagen.url, 'descripcion': f.descripcion})
    return JsonResponse({'success': True, 'fotos': fotos})


@staff_member_required
@require_POST
def foto_eliminar(request, foto_pk):
    foto = get_object_or_404(FotoAnexoReporte, pk=foto_pk)
    try: foto.imagen.delete(save=False)
    except Exception: pass
    foto.delete()
    return JsonResponse({'success': True})


@staff_member_required
@require_POST
def foto_actualizar_descripcion(request, foto_pk):
    foto = get_object_or_404(FotoAnexoReporte, pk=foto_pk)
    data = json.loads(request.body)
    foto.descripcion = data.get('descripcion', '')
    foto.save(update_fields=['descripcion'])
    return JsonResponse({'success': True})


# ─────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────

def _obtener_o_generar_pdf(reporte):
    """Sirve el PDF guardado en storage. Si no existe lo genera y guarda."""
    if reporte.pdf_archivo:
        try:
            reporte.pdf_archivo.open('rb')
            data = reporte.pdf_archivo.read()
            reporte.pdf_archivo.close()
            if data:
                return data
        except Exception as exc:
            logger.warning('PDF corrupto reporte %s: %s', reporte.pk, exc)
            reporte.pdf_archivo = None
            reporte.save(update_fields=['pdf_archivo'])

    # Generar y guardar (igual que WorkOrderService)
    from .pdf_builder import build_pdf_bytes
    pdf_bytes = build_pdf_bytes(reporte)

    try:
        nombre = f'Reporte_Elevadores_{reporte.pk}_{reporte.fecha_hora.strftime("%Y%m%d_%H%M%S")}.pdf'
        reporte.pdf_archivo.save(nombre, ContentFile(pdf_bytes), save=True)
        logger.info('PDF reporte %s guardado: %s', reporte.pk, nombre)
    except Exception as exc:
        logger.error('Error guardando PDF reporte %s: %s', reporte.pk, exc)

    return pdf_bytes


def _procesar_form_reporte(request, instance):
    """Guarda cabecera + filas (elevadores de BD) + fotos."""
    post    = request.POST
    reporte = instance if instance is not None else ReporteElevador(creado_por=request.user)

    reporte.supervisor_id            = None
    reporte.supervisor_nombre_manual = post.get('supervisor_manual', '').strip()
    reporte.tecnico_id               = None
    reporte.tecnico_nombre_manual    = post.get('tecnico_manual', '').strip()

    fh = post.get('fecha_hora', '').strip()
    if fh:
        dt = parse_datetime(fh)
        if dt:
            reporte.fecha_hora = timezone.make_aware(dt) if timezone.is_naive(dt) else dt

    reporte.observaciones_generales = post.get('observaciones_generales', '').strip()
    reporte.estado = post.get('estado', 'borrador')
    reporte.save()

    # Filas — el formulario envía elevador_id[], estado[], clasificacion[], descripcion_novedad[]
    elev_ids      = post.getlist('elevador_id[]')
    estados       = post.getlist('estado[]')
    clasificaciones = post.getlist('clasificacion[]')
    descripciones = post.getlist('descripcion_novedad[]')

    with transaction.atomic():
        reporte.filas.all().delete()
        vistos = set()
        for idx, eid in enumerate(elev_ids):
            if not eid or eid in vistos:
                continue
            vistos.add(eid)
            FilaReporteElevador.objects.create(
                reporte=reporte,
                elevador_id=int(eid),
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

    # Fotos eliminadas
    for fid in post.getlist('fotos_eliminar[]'):
        if not fid:
            continue
        try:
            f = FotoAnexoReporte.objects.get(pk=int(fid), reporte=reporte)
            try: f.imagen.delete(save=False)
            except Exception: pass
            f.delete()
        except FotoAnexoReporte.DoesNotExist:
            pass

    return reporte
