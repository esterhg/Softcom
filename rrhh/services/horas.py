"""Reglas de negocio de reportes de horas y horas extra (sin request)."""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from rrhh.models import HoraExtra, ReporteHoras

PREFIJO = 'RH'


def calcular_horas(entrada, salida):
    """Horas (Decimal, 2 decimales) entre ``entrada`` y ``salida``.

    Como ambas son fecha+hora, un turno que cruza medianoche es válido.
    Lanza ValidationError si la salida no es posterior a la entrada.
    """
    if salida <= entrada:
        raise ValidationError('La salida debe ser posterior a la entrada.')
    segundos = Decimal(str((salida - entrada).total_seconds()))
    return (segundos / Decimal(3600)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def siguiente_codigo(anio=None):
    """Siguiente ID de reporte del año: RH-AAAA-NNNN."""
    anio = anio or timezone.localdate().year
    prefijo = f'{PREFIJO}-{anio}-'
    ultimo = (ReporteHoras.objects.filter(codigo__startswith=prefijo)
              .aggregate(m=Max('codigo'))['m'])
    n = int(ultimo.rsplit('-', 1)[1]) + 1 if ultimo else 1
    return f'{prefijo}{n:04d}'


def crear_reporte(*, colaborador, autorizado_por, solicitado_por, creado_por):
    """Crea un reporte con ID automático. Reintenta si hay colisión de código."""
    for _ in range(3):
        try:
            with transaction.atomic():
                return ReporteHoras.objects.create(
                    codigo=siguiente_codigo(), colaborador=colaborador,
                    autorizado_por=autorizado_por, solicitado_por=solicitado_por,
                    creado_por=creado_por)
        except IntegrityError:
            continue
    raise ValidationError('No se pudo generar el ID del reporte. Intenta de nuevo.')


def registrar_hora_extra(*, reporte, colaborador, categoria, entrada, salida,
                         cena, justificacion, creado_por):
    """Crea una hora extra en ``reporte`` calculando las horas totales."""
    justificacion = (justificacion or '').strip()
    if not justificacion:
        raise ValidationError('La justificación es obligatoria.')
    horas = calcular_horas(entrada, salida)
    return HoraExtra.objects.create(
        reporte=reporte, colaborador=colaborador, categoria=categoria,
        entrada=entrada, salida=salida, horas_total=horas, cena=cena,
        justificacion=justificacion, creado_por=creado_por)
