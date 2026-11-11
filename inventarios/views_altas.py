"""
Tabla de aprobación de altas de MATERIAL pedidas desde Requisiciones.

Solo Almacén / Supervisor de Almacén. La tabla de proveedores (Procura) vive en
``presupuestos``; las reglas de negocio están en
``presupuestos.services.solicitudes_alta``.
"""
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from presupuestos import permissions
from presupuestos.models import SolicitudAltaMaterial
from presupuestos.selectors import solicitudes_alta as sel
from presupuestos.services import solicitudes_alta as svc
from presupuestos.views_altas import ejecutar_y_volver

from .models import UnidadMedida


@permissions.almacen_altas_required
def bandeja_materiales(request):
    estado = request.GET.get('estado', SolicitudAltaMaterial.ESTADO_PENDIENTE)
    if estado == 'TODAS':
        estado = None
    return render(request, 'inventarios/altas_material.html', {
        'estado': estado or 'TODAS',
        'solicitudes': sel.solicitudes_material(estado)[:300],
        'pendientes': sel.conteo_pendientes()['materiales'],
        'unidades': UnidadMedida.objects.all(),
        'estados': SolicitudAltaMaterial.ESTADO_CHOICES,
        'active_tab': 'dashboard',
        'title': 'Solicitudes de alta de material',
    })


@require_POST
@permissions.almacen_altas_required
def material_aprobar(request, pk):
    s = get_object_or_404(SolicitudAltaMaterial, pk=pk)
    datos = {c: request.POST.get(c) for c in ('unidad_medida', 'precio_estimado', 'descripcion')}

    def accion():
        svc.aprobar_solicitud_material(s, request.user, request.POST.get('sku'), datos)
        return f'Material "{s.nombre}" dado de alta.'
    return ejecutar_y_volver(request, accion, reverse('inventarios:altas_material'))


@require_POST
@permissions.almacen_altas_required
def material_rechazar(request, pk):
    s = get_object_or_404(SolicitudAltaMaterial, pk=pk)

    def accion():
        svc.rechazar_solicitud_material(s, request.user, request.POST.get('motivo'))
        return f'Solicitud de "{s.nombre}" rechazada.'
    return ejecutar_y_volver(request, accion, reverse('inventarios:altas_material'))
