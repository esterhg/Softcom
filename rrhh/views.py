"""Vistas HTTP de RRHH. Toda la app es exclusiva del grupo Instalaciones."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.excel import respuesta_xlsx
from core.filtros_columna import columnas_con_estado
from core.navegacion import querystring_sin, url_retorno
from rrhh.forms import CategoriaForm, HoraExtraForm, ReporteHorasForm
from rrhh.permissions import instalaciones_required
from rrhh.selectors import horas as sel
from rrhh.services import exportes, horas as svc

POR_PAGINA = 50


def _errores_form(form):
    partes = []
    for campo, errores in form.errors.items():
        etiqueta = form.fields[campo].label if campo in form.fields else ''
        partes.extend(f'{etiqueta}: {e}' if etiqueta else str(e) for e in errores)
    return ' '.join(partes)


def _columnas(params):
    """Estado de los filtros por columna, indexado por key (para colocarlos en la tabla)."""
    return {c['key']: c for c in columnas_con_estado(params, sel.COLUMNAS_HORAS)}


def _contexto_horas(request, reporte_id=None):
    """Contexto común de la tabla de horas extra (lista principal y detalle)."""
    qs = sel.horas_listado(request.GET, reporte_id)
    categoria, desde, hasta = sel.filtros_horas(request.GET)
    return {
        'page': Paginator(qs, POR_PAGINA).get_page(request.GET.get('page')),
        'total_horas': sel.total_horas(qs),
        'col': _columnas(request.GET),
        'querystring': querystring_sin(request.GET, 'page'),
        # Para el menú "Exportar Excel": mismos filtros, pero la categoría la elige el menú.
        'qs_export': querystring_sin(request.GET, 'page', 'page_r', 'categoria', 'agrupar'),
        'categorias': sel.todas_las_categorias(),
        'f_categoria': categoria,
        'f_desde': request.GET.get('desde', '') if desde else '',
        'f_hasta': request.GET.get('hasta', '') if hasta else '',
        'form_hora': HoraExtraForm(),
        'form_reporte': ReporteHorasForm(),
        'next_url': request.get_full_path(),
    }


def _respuesta_excel(horas, params, *, reporte=None):
    """Excel de horas extra según los filtros recibidos.

    ``?agrupar=categoria`` genera una hoja por categoría; si no, una sola hoja
    (filtrada por ``?categoria=<id>`` cuando viene).
    """
    horas = list(horas)
    categoria = sel.categoria_por_id(params.get('categoria'))
    _, desde, hasta = sel.filtros_horas(params)
    if params.get('agrupar') == 'categoria' and not categoria:
        wb = exportes.libro_excel_por_categorias(
            horas, reporte=reporte.codigo if reporte else None, desde=desde, hasta=hasta)
        return respuesta_xlsx(wb, 'REPORTE_DE_HORAS_EXTRAS_INSTALACIONES_POR_CATEGORIA')
    wb = exportes.libro_excel_horas(
        horas,
        categoria=categoria.nombre if categoria else None,
        reporte=reporte.codigo if reporte else None,
        periodo=exportes.texto_periodo(horas, desde, hasta),
    )
    nombre = 'REPORTE_DE_HORAS_EXTRAS_INSTALACIONES'
    if categoria:
        nombre += '_' + ''.join(ch if ch.isalnum() else '_' for ch in categoria.nombre.upper())
    return respuesta_xlsx(wb, nombre)


def _guardar_hora(request, *, hora=None, reporte_fijo=None, destino):
    """Procesa el POST de crear/editar hora extra y responde con redirect (PRG)."""
    datos = request.POST.copy()
    if reporte_fijo is not None:
        datos['reporte'] = str(reporte_fijo.pk)
    form = HoraExtraForm(datos)
    if not form.is_valid():
        messages.error(request, _errores_form(form))
        return redirect(destino)
    try:
        if hora is None:
            svc.registrar_hora_extra(creado_por=request.user, **form.cleaned_data)
            messages.success(request, 'Hora extra registrada.')
        else:
            svc.actualizar_hora_extra(hora, **form.cleaned_data)
            messages.success(request, 'Hora extra actualizada.')
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
    return redirect(destino)


# ---------------------------------------------------------------------------
# Consultas (GET)
# ---------------------------------------------------------------------------

@instalaciones_required
def reportes_view(request):
    """Pantalla principal: crear reporte, lista de reportes y exportar Excel."""
    return render(request, 'rrhh/reportes.html', {
        'reportes': Paginator(sel.reportes_listado({}), POR_PAGINA).get_page(request.GET.get('page')),
        'form_reporte': ReporteHorasForm(),
        'categorias': sel.todas_las_categorias(),
        'querystring': '',
        'qs_export': '',
    })


@instalaciones_required
def detalle_reporte_view(request, pk):
    reporte = sel.reporte_con_totales(pk)
    if reporte is None:
        raise Http404
    ctx = _contexto_horas(request, reporte_id=pk)
    ctx['reporte'] = reporte
    ctx['form_hora'] = HoraExtraForm(initial={'reporte': pk, 'colaborador': reporte.colaborador_id})
    return render(request, 'rrhh/detalle_reporte.html', ctx)


@instalaciones_required
def export_reportes_excel(request):
    """Excel de las horas extra que cumplen los filtros de la tabla."""
    return _respuesta_excel(sel.horas_para_exportar(request.GET), request.GET)


@instalaciones_required
def export_reporte_excel(request, pk):
    """Excel de un solo reporte (opcionalmente filtrado por categoría / fechas)."""
    reporte = sel.reporte_con_totales(pk)
    if reporte is None:
        raise Http404
    return _respuesta_excel(
        sel.horas_para_exportar(request.GET, reporte_id=pk), request.GET, reporte=reporte)


# ---------------------------------------------------------------------------
# Acciones (POST + Post/Redirect/Get)
# ---------------------------------------------------------------------------

@instalaciones_required
@require_POST
def crear_reporte_view(request):
    form = ReporteHorasForm(request.POST)
    if not form.is_valid():
        messages.error(request, _errores_form(form))
        return redirect('rrhh:reportes')
    try:
        reporte = svc.crear_reporte(creado_por=request.user, **form.cleaned_data)
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
        return redirect('rrhh:reportes')
    messages.success(request, f'Reporte {reporte.codigo} creado.')
    return redirect('rrhh:detalle_reporte', pk=reporte.pk)


@instalaciones_required
@require_POST
def crear_categoria_view(request):
    """Crea una categoría y vuelve a la pantalla de origen (?next= validado)."""
    destino = url_retorno(request, default=reverse('rrhh:reportes'))
    form = CategoriaForm(request.POST)
    if not form.is_valid():
        messages.error(request, _errores_form(form))
        return redirect(destino)
    try:
        categoria = svc.crear_categoria(form.cleaned_data['nombre'])
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
        return redirect(destino)
    messages.success(request, f'Categoría "{categoria.nombre}" creada.')
    return redirect(destino)


@instalaciones_required
@require_POST
def crear_hora_extra_general_view(request):
    """Crea una hora extra eligiendo el reporte en el formulario."""
    destino = url_retorno(request, default=reverse('rrhh:reportes'))
    return _guardar_hora(request, destino=destino)


@instalaciones_required
@require_POST
def crear_hora_extra_view(request, pk):
    """Crea una hora extra dentro de un reporte concreto."""
    reporte = sel.reporte_con_totales(pk)
    if reporte is None:
        raise Http404
    destino = url_retorno(request, default=reverse('rrhh:detalle_reporte', args=[pk]))
    return _guardar_hora(request, reporte_fijo=reporte, destino=destino)


@instalaciones_required
@require_POST
def editar_hora_extra_view(request, pk):
    hora = sel.hora_por_id(pk)
    if hora is None:
        raise Http404
    destino = url_retorno(request, default=reverse('rrhh:reportes'))
    return _guardar_hora(request, hora=hora, destino=destino)


@instalaciones_required
@require_POST
def eliminar_hora_extra_view(request, pk):
    hora = sel.hora_por_id(pk)
    if hora is None:
        raise Http404
    destino = url_retorno(request, default=reverse('rrhh:reportes'))
    svc.eliminar_hora_extra(hora)
    messages.success(request, 'Hora extra eliminada.')
    return redirect(destino)
