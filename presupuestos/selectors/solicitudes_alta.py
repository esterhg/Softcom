"""Consultas de lectura de las solicitudes de alta (proveedor / material)."""
from presupuestos.models import (
    ArticuloRequisicion,
    SolicitudAltaMaterial,
    SolicitudAltaProveedor,
)

ESTADOS_VALIDOS = {e for e, _ in SolicitudAltaProveedor.ESTADO_CHOICES}


def _filtrar_estado(qs, estado):
    if estado in ESTADOS_VALIDOS:
        return qs.filter(estado=estado)
    return qs


def solicitudes_proveedor(estado=None):
    qs = SolicitudAltaProveedor.objects.select_related(
        'requisicion', 'solicitante', 'revisado_por', 'proveedor')
    return _filtrar_estado(qs, estado)


def solicitudes_material(estado=None):
    qs = SolicitudAltaMaterial.objects.select_related(
        'requisicion', 'articulo', 'unidad_medida', 'solicitante', 'revisado_por', 'material')
    return _filtrar_estado(qs, estado)


def conteo_pendientes():
    """Pendientes por tipo, para los contadores de la bandeja."""
    return {
        'proveedores': SolicitudAltaProveedor.objects.filter(
            estado=SolicitudAltaProveedor.ESTADO_PENDIENTE).count(),
        'materiales': SolicitudAltaMaterial.objects.filter(
            estado=SolicitudAltaMaterial.ESTADO_PENDIENTE).count(),
    }


def proveedor_pendiente(requisicion):
    """Solicitudes de proveedor sin resolver de una requisición."""
    return requisicion.solicitudes_alta_proveedor.filter(
        estado=SolicitudAltaProveedor.ESTADO_PENDIENTE)


def materiales_pendientes(requisicion):
    return requisicion.solicitudes_alta_material.filter(
        estado=SolicitudAltaMaterial.ESTADO_PENDIENTE)


def solicitud_material_de_articulo(articulo: ArticuloRequisicion):
    """Última solicitud de material ligada a un artículo (o None)."""
    return articulo.solicitudes_alta_material.order_by('-creado_en').first()
