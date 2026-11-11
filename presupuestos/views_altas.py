"""Bandeja de aprobación de solicitudes de alta (proveedor / material)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.navegacion import url_retorno
from inventarios.models import UnidadMedida
from . import permissions
from .models import Requisicion, SolicitudAltaMaterial, SolicitudAltaProveedor
from .selectors import solicitudes_alta as sel
from .services import solicitudes_alta as svc


@permissions.bandeja_altas_required
def bandeja_altas(request):
    """Tabla de solicitudes. Cada grupo ve solo el tipo que puede resolver."""
    user = request.user
    ve_proveedores = permissions.puede_aprobar_proveedores(user)
    ve_materiales = permissions.puede_aprobar_materiales(user)

    tab = request.GET.get('tab')
    if tab not in ('proveedores', 'materiales'):
        tab = 'materiales' if ve_materiales and not ve_proveedores else 'proveedores'
    if tab == 'proveedores' and not ve_proveedores:
        tab = 'materiales'
    if tab == 'materiales' and not ve_materiales:
        tab = 'proveedores'

    estado = request.GET.get('estado', SolicitudAltaProveedor.ESTADO_PENDIENTE)
    if estado == 'TODAS':
        estado = None

    if tab == 'proveedores':
        solicitudes = sel.solicitudes_proveedor(estado)
    else:
        solicitudes = sel.solicitudes_material(estado)

    pendientes = sel.conteo_pendientes()
    return render(request, 'presupuestos/altas/bandeja.html', {
        'tab': tab,
        'estado': estado or 'TODAS',
        'solicitudes': solicitudes[:300],
        've_proveedores': ve_proveedores,
        've_materiales': ve_materiales,
        'pendientes': pendientes,
        'unidades': UnidadMedida.objects.all() if tab == 'materiales' else [],
        'estados': SolicitudAltaProveedor.ESTADO_CHOICES,
        'title': 'Solicitudes de alta',
    })


# Estados en los que el solicitante todavía puede editar la requisición
_ESTADOS_EDITABLES = ('BORRADOR', 'SOLICITUD_INFORMACION', 'RECHAZADO')


def _puede_solicitar(user, requisicion):
    """Dueño de la requisición (o quien la crea en nombre de otro), Procura o superusuario."""
    if requisicion.estado_requisicion not in _ESTADOS_EDITABLES and not user.is_superuser:
        return False
    return bool(
        user.is_superuser
        or permissions.puede_aprobar_proveedores(user)
        or requisicion.usuario_solicitante_id == user.id
        or requisicion.usuario_en_nombre_de_id == user.id
    )


def _solicitar(request, pk, crear):
    """Crea una solicitud desde la requisición y responde JSON (la usa un modal)."""
    requisicion = get_object_or_404(Requisicion, pk=pk)
    if not _puede_solicitar(request.user, requisicion):
        return JsonResponse(
            {'success': False, 'message': 'No puede solicitar altas en esta requisición.'}, status=403)
    try:
        solicitud = crear(requisicion)
    except ValidationError as e:
        return JsonResponse({'success': False, 'message': ' '.join(e.messages)}, status=400)
    return JsonResponse({'success': True, 'id': solicitud.pk,
                         'message': f'Solicitud enviada: {solicitud.nombre}.'})


@require_POST
@login_required
def solicitar_proveedor(request, pk):
    """Solicita a Procura el alta de un proveedor; el solicitante solo indica el nombre."""
    return _solicitar(request, pk, lambda req: svc.crear_solicitud_proveedor(
        req, request.user, {'nombre': request.POST.get('nombre')}))


@require_POST
@login_required
def solicitar_material(request, pk):
    """Solicita a Almacén el alta de un material; el solicitante solo indica el nombre."""
    return _solicitar(request, pk, lambda req: svc.solicitar_material_nuevo(
        req, request.user,
        request.POST.get('nombre'),
        descripcion=request.POST.get('descripcion', ''),
        precio=request.POST.get('precio') or 0))


def _volver(request, tab):
    destino = reverse('presupuestos:bandeja_altas') + f'?tab={tab}'
    return redirect(url_retorno(request, default=destino))


def _ejecutar(request, tab, accion):
    """Ejecuta un service y traduce errores a mensajes (Post/Redirect/Get)."""
    try:
        resultado = accion()
    except PermissionDenied as e:
        messages.error(request, str(e) or 'No tiene permiso para esta acción.')
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
    else:
        messages.success(request, resultado)
    return _volver(request, tab)


@require_POST
@permissions.bandeja_altas_required
def proveedor_aprobar(request, pk):
    s = get_object_or_404(SolicitudAltaProveedor, pk=pk)
    campos = ('numero_proveedor', 'rtn', 'contacto', 'telefono', 'email', 'domicilio')
    datos = {c: request.POST.get(c) for c in campos}

    def accion():
        svc.aprobar_solicitud_proveedor(s, request.user, datos)
        return f'Proveedor "{s.nombre}" dado de alta.'
    return _ejecutar(request, 'proveedores', accion)


@require_POST
@permissions.bandeja_altas_required
def proveedor_rechazar(request, pk):
    s = get_object_or_404(SolicitudAltaProveedor, pk=pk)

    def accion():
        svc.rechazar_solicitud_proveedor(s, request.user, request.POST.get('motivo'))
        return f'Solicitud de "{s.nombre}" rechazada.'
    return _ejecutar(request, 'proveedores', accion)


@require_POST
@permissions.bandeja_altas_required
def material_aprobar(request, pk):
    s = get_object_or_404(SolicitudAltaMaterial, pk=pk)

    def accion():
        datos = {c: request.POST.get(c) for c in ('unidad_medida', 'precio_estimado', 'descripcion')}
        svc.aprobar_solicitud_material(s, request.user, request.POST.get('sku'), datos)
        return f'Material "{s.nombre}" dado de alta.'
    return _ejecutar(request, 'materiales', accion)


@require_POST
@permissions.bandeja_altas_required
def material_rechazar(request, pk):
    s = get_object_or_404(SolicitudAltaMaterial, pk=pk)

    def accion():
        svc.rechazar_solicitud_material(s, request.user, request.POST.get('motivo'))
        return f'Solicitud de "{s.nombre}" rechazada.'
    return _ejecutar(request, 'materiales', accion)
