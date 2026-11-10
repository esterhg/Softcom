"""
Permisos de la app Presupuestos.

Centraliza quién puede aprobar las solicitudes de alta que nacen en una
requisición: proveedores (Procura) y materiales (Almacén / Supervisor de Almacén).
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from inventarios.permissions import GRUPO_SUPERVISOR_ALMACEN

# En producción existen ambas variantes de mayúsculas del grupo Procura.
GRUPOS_PROCURA = ('Procura', 'PROCURA')
GRUPOS_ALMACEN = (GRUPO_SUPERVISOR_ALMACEN, 'Almacenes')


def _en_grupos(user, nombres):
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name__in=nombres).exists())
    )


def puede_aprobar_proveedores(user):
    """Procura (o superusuario) aprueba altas de proveedor."""
    return _en_grupos(user, GRUPOS_PROCURA)


def puede_aprobar_materiales(user):
    """Almacén / Supervisor de Almacén (o superusuario) aprueba altas de material."""
    return _en_grupos(user, GRUPOS_ALMACEN)


def puede_ver_bandeja_altas(user):
    return puede_aprobar_proveedores(user) or puede_aprobar_materiales(user)


def bandeja_altas_required(view):
    """Login + pertenecer a Procura o Almacén. Sin permiso responde 403."""
    @wraps(view)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not puede_ver_bandeja_altas(request.user):
            return HttpResponseForbidden(
                "Solo Procura o Almacén pueden ver las solicitudes de alta.")
        return view(request, *args, **kwargs)
    return _wrapped
