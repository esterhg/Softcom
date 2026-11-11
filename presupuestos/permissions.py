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


def _en_grupos(user, nombres, permitir_superusuario=True):
    if not user.is_authenticated:
        return False
    if permitir_superusuario and user.is_superuser:
        return True
    return user.groups.filter(name__in=nombres).exists()


def puede_aprobar_proveedores(user):
    """Solo el grupo Procura aprueba altas de proveedor (ni el superusuario sin el grupo)."""
    return _en_grupos(user, GRUPOS_PROCURA, permitir_superusuario=False)


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
