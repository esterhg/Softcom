from django import template

from rrhh.permissions import es_instalaciones
from rrhh.services import horas as horas_svc

register = template.Library()


@register.filter(name='dia_he')
def dia_he(hora):
    """Día de la semana de una HoraExtra."""
    return horas_svc.dia_semana(hora.entrada)


@register.filter(name='jornada_he')
def jornada_he(hora):
    """DIURNO / NOCTURNO / MIXTO de una HoraExtra."""
    return horas_svc.jornada(hora.entrada, hora.salida)


@register.filter(name='es_instalaciones')
def es_instalaciones_filter(user):
    """Misma regla que protege las vistas de RRHH (solo grupo Instalaciones)."""
    return es_instalaciones(user)
