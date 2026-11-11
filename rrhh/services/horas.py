"""Reglas de negocio de reportes de horas y horas extra (sin request)."""
from datetime import time
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from rrhh.models import CategoriaHoraExtra, HoraExtra, ReporteHoras

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


def crear_categoria(nombre):
    """Crea una categoría de hora extra. No permite duplicados (sin distinguir mayúsculas)."""
    nombre = ' '.join((nombre or '').split())
    if not nombre:
        raise ValidationError('El nombre de la categoría es obligatorio.')
    if len(nombre) > 80:
        raise ValidationError('El nombre de la categoría no puede pasar de 80 caracteres.')
    existente = CategoriaHoraExtra.objects.filter(nombre__iexact=nombre).first()
    if existente:
        if not existente.activa:
            existente.activa = True
            existente.save(update_fields=['activa'])
            return existente
        raise ValidationError(f'La categoría "{existente.nombre}" ya existe.')
    return CategoriaHoraExtra.objects.create(nombre=nombre)


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


def actualizar_hora_extra(hora, *, reporte, colaborador, categoria, entrada, salida,
                          cena, justificacion):
    """Edita una hora extra y recalcula las horas totales."""
    justificacion = (justificacion or '').strip()
    if not justificacion:
        raise ValidationError('La justificación es obligatoria.')
    hora.horas_total = calcular_horas(entrada, salida)
    hora.reporte, hora.colaborador, hora.categoria = reporte, colaborador, categoria
    hora.entrada, hora.salida, hora.cena = entrada, salida, cena
    hora.justificacion = justificacion
    hora.save()
    return hora


def eliminar_hora_extra(hora):
    """Elimina una hora extra."""
    hora.delete()


# ---------------------------------------------------------------------------
# Datos derivados para la tabla (misma lógica que las fórmulas del Excel)
# ---------------------------------------------------------------------------

DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
_H5, _H19 = time(5, 0), time(19, 0)


def dia_semana(entrada):
    """Nombre del día (en hora local) de una entrada."""
    return DIAS[timezone.localtime(entrada).weekday()]


def jornada(entrada, salida):
    """DIURNO / NOCTURNO / MIXTO, igual que la columna JORNADA del Excel.

    Usa solo la hora del día (local) de la entrada y la salida.
    """
    ini = timezone.localtime(entrada).time().replace(second=0, microsecond=0)
    fin = timezone.localtime(salida).time().replace(second=0, microsecond=0)
    if _H5 <= ini < _H19 and fin > ini and fin <= _H19:
        return 'DIURNO'
    if (ini >= _H19 and (fin > ini or fin <= _H5)) or (ini < _H5 and fin > ini and fin <= _H5):
        return 'NOCTURNO'
    return 'MIXTO'
