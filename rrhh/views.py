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
from core.navegacion import querystring_sin
from rrhh.forms import HoraExtraForm, ReporteHorasForm
from rrhh.permissions import instalaciones_required
from rrhh.selectors import horas as sel
from rrhh.services import exportes, horas as svc


def _errores_form(form):
    partes = []
    for campo, errores in form.errors.items():
        etiqueta = form.fields[campo].label if campo in form.fields else ''
        partes.extend(f'{etiqueta}: {e}' if etiqueta else str(e) for e in errores)
    return ' '.join(partes)


@instalaciones_required
def reportes_view(request):
    page = Paginator(sel.reportes_listado(request.GET), 50).get_page(request.GET.get('page'))
    return render(request, 'rrhh/reportes.html', {
        'page': page,
        'columnas': columnas_con_estado(request.GET, sel.COLUMNAS_REPORTES),
        'querystring': querystring_sin(request.GET, 'page'),
        'form': ReporteHorasForm(),
    })


@instalaciones_required
def export_reportes_excel(request):
    wb = exportes.libro_excel_reportes(sel.reportes_listado(request.GET))
    return respuesta_xlsx(wb, 'reportes_horas')


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
def detalle_reporte_view(request, pk):
    reporte = sel.reporte_con_totales(pk)
    if reporte is None:
        raise Http404
    return render(request, 'rrhh/detalle_reporte.html', {
        'reporte': reporte,
        'horas': sel.horas_de_reporte(reporte),
        'form': HoraExtraForm(initial={'colaborador': reporte.colaborador_id}),
    })


@instalaciones_required
@require_POST
def crear_hora_extra_view(request, pk):
    reporte = sel.reporte_con_totales(pk)
    if reporte is None:
        raise Http404
    destino = reverse('rrhh:detalle_reporte', args=[pk])
    form = HoraExtraForm(request.POST)
    if not form.is_valid():
        messages.error(request, _errores_form(form))
        return redirect(destino)
    try:
        svc.registrar_hora_extra(reporte=reporte, creado_por=request.user, **form.cleaned_data)
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
        return redirect(destino)
    messages.success(request, 'Hora extra registrada.')
    return redirect(destino)
