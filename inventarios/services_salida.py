"""
Reglas de inventario para los pases de salida (SolicitudMaterial):

- Al crear el pase: los movimientos SALIDA quedan PENDIENTE -> el material se
  considera RESERVADO (Disponible = Total - Reservado). El stock físico no baja.
- Al aprobar el pase: los movimientos se liquidan (APROBADO) -> baja el stock real.
- Al rechazar el pase (antes o después de aprobar): los movimientos pasan a
  RECHAZADO -> se libera la reserva o se devuelve el stock (la señal
  trigger_stock_recalculation reconstruye las existencias).
"""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction

# Estados del pase en los que un movimiento PENDIENTE cuenta como reserva
ESTADOS_RESERVA = ['PENDIENTE_AUTORIZACION']


def aprobar_salida(solicitud, usuario):
    """Descuenta el stock real de todos los movimientos SALIDA pendientes del pase."""
    with transaction.atomic():
        for mov in solicitud.items.filter(tipo='SALIDA', estado='PENDIENTE'):
            mov.liquidar(usuario)


def revertir_salida(solicitud, usuario=None, motivo='Pase rechazado'):
    """
    Libera la reserva / devuelve el stock: marca como RECHAZADO cada movimiento
    del pase que no lo esté. Se guarda uno a uno para que la señal recalcule.
    """
    from django.utils import timezone
    with transaction.atomic():
        for mov in solicitud.items.exclude(estado='RECHAZADO'):
            mov.estado = 'RECHAZADO'
            mov.comentarios = ((mov.comentarios or '') + f' | {motivo}').strip(' |')
            if usuario and not mov.aprobado_por_id:
                mov.aprobado_por = usuario
                mov.fecha_aprobacion = timezone.now()
            mov.save()


def reservado_por_material(material_ids, ubicacion_id=None):
    """{material_id: cantidad reservada} para una lista de materiales (una sola query)."""
    from django.db.models import Sum
    from .models import MovimientoInventario

    qs = MovimientoInventario.objects.filter(
        material_id__in=material_ids, tipo='SALIDA', estado='PENDIENTE',
        solicitud__estado__in=ESTADOS_RESERVA,
        material__no_afecta_stock=False,
    )
    if ubicacion_id:
        qs = qs.filter(ubicacion_origen_id=ubicacion_id)
    res = defaultdict(lambda: Decimal('0'))
    for row in qs.values('material_id').annotate(total=Sum('cantidad')):
        res[row['material_id']] = row['total'] or Decimal('0')
    return res
