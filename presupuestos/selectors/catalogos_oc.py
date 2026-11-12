"""Consultas de lectura de los catálogos de la Orden de Compra."""
from presupuestos.models import CentroCosto, TipoContrato


def centros_costo_activos():
    """Lista [{'id', 'nombre'}] de centros de costo activos."""
    return [{'id': cc.id, 'nombre': cc.nombre}
            for cc in CentroCosto.objects.filter(activo=True).order_by('nombre')]


def tipos_contrato_activos():
    """Lista [{'codigo', 'nombre'}] de tipos de contrato activos."""
    return [{'codigo': t.codigo, 'nombre': t.nombre}
            for t in TipoContrato.objects.filter(activo=True).order_by('nombre')]


def codigo_tipo_contrato_valido(codigo):
    """Devuelve el código si existe en el catálogo; si no, None."""
    if not codigo:
        return None
    return codigo if TipoContrato.objects.filter(codigo=codigo).exists() else None
