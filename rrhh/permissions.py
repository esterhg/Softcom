"""
Permisos de la app RRHH.

Acceso EXCLUSIVO al grupo 'Instalaciones'. Los superusuarios no tienen
excepción: si no pertenecen al grupo, no entran.
El grupo lo crea la migración rrhh/0001_initial (o 0002).
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

GRUPO_INSTALACIONES = 'Instalaciones'


def es_instalaciones(user):
    """True solo si el usuario autenticado pertenece al grupo Instalaciones."""
    return bool(
        user.is_authenticated
        and user.groups.filter(name__iexact=GRUPO_INSTALACIONES).exists()
    )


def instalaciones_required(view):
    """Login + pertenencia al grupo 'Instalaciones'.

    Sin sesión redirige al login; con sesión pero sin el grupo responde 403.
    """
    @wraps(view)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not es_instalaciones(request.user):
            return HttpResponseForbidden(
                "Solo el grupo Instalaciones puede acceder a este módulo.")
        return view(request, *args, **kwargs)
    return _wrapped
