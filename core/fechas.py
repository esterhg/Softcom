"""Utilidades de fechas compartidas por todas las apps de Softcom."""
from datetime import datetime, time as dtime

from django.utils import timezone


def parse_fecha_iso(valor, fin=False):
    """Convierte 'AAAA-MM-DD' (p. ej. un <input type="date">) en datetime.

    ``fin=True`` devuelve el final del día (23:59:59.999999), útil para filtros
    "hasta". Si la zona horaria está activa, el resultado es aware.
    Devuelve None si el valor está vacío o no es válido.
    """
    if not valor:
        return None
    try:
        d = datetime.strptime(valor, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
    t = dtime.max if fin else dtime.min
    naive = datetime.combine(d, t)
    if timezone.is_aware(timezone.now()):
        return timezone.make_aware(naive)
    return naive
