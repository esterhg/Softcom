"""
Permisos de la app Inventarios.

Centraliza las reglas de acceso (grupos de Django) para que vistas, plantillas
y servicios usen la misma definición.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

# Grupo con acceso exclusivo (junto con superusuarios) a los reportes de inventario.
# Lo crea la migración inventarios/0047_crear_grupo_supervisor_almacen.
GRUPO_SUPERVISOR_ALMACEN = 'Supervisor de Almacen'


def es_supervisor_almacen(user):
    """True si el usuario es superusuario o pertenece al grupo Supervisor de Almacén."""
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=GRUPO_SUPERVISOR_ALMACEN).exists())
    )


def supervisor_almacen_required(view):
    """Login + pertenencia al grupo 'Supervisor de Almacen' (o superusuario).

    Sin sesión redirige al login (``login_required``); con sesión pero sin
    permiso responde 403.
    """
    @wraps(view)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not es_supervisor_almacen(request.user):
            return HttpResponseForbidden("Solo el Supervisor de Almacén puede ver los reportes.")
        return view(request, *args, **kwargs)
    return _wrapped
