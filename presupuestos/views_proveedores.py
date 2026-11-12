"""Endpoints JSON del CRUD de proveedores (solo HTTP; la lógica vive en services)."""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from mantenimiento.models import Empresa

from .permissions import puede_gestionar_proveedores
from .services import proveedores as svc


def _payload(request):
    try:
        return json.loads(request.body or '{}')
    except ValueError:
        raise svc.ProveedorError('Datos inválidos.')


def _responder(request, accion):
    """Valida permiso, ejecuta ``accion(payload)`` y traduce errores a JSON."""
    if not puede_gestionar_proveedores(request.user):
        return JsonResponse(
            {'success': False, 'message': 'Solo usuarios del grupo Procura pueden gestionar proveedores.'},
            status=403)
    try:
        return JsonResponse({'success': True, **accion(_payload(request))})
    except svc.ProveedorError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_POST
def proveedor_crear(request):
    def accion(datos):
        empresa = svc.crear_proveedor(datos)
        return {'message': f'Proveedor "{empresa.nombre}" creado.', 'proveedor': svc.serializar(empresa)}
    return _responder(request, accion)


@login_required
@require_POST
def proveedor_editar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)

    def accion(datos):
        svc.actualizar_proveedor(empresa, datos)
        return {'message': f'Proveedor "{empresa.nombre}" actualizado.', 'proveedor': svc.serializar(empresa)}
    return _responder(request, accion)


@login_required
@require_POST
def proveedor_eliminar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)

    def accion(_datos):
        nombre = svc.eliminar_proveedor(empresa)
        return {'message': f'Proveedor "{nombre}" eliminado.'}
    return _responder(request, accion)
