"""
Servicios de los reportes de inventario (movimientos y pases pendientes):
agregaciones y construcción de los libros de Excel.

Trasladado sin cambios de comportamiento desde ``inventarios/reportes.py``.
"""
from django.utils import timezone

from core.excel import autoajustar, escribir_headers, estilos
from inventarios.models import MovimientoInventario
from inventarios.selectors.reportes import departamento_de

# ---------------------------------------------------------------------------
# Pases de salida pendientes de justificar
# ---------------------------------------------------------------------------

def resumen_por_departamento(solicitudes):
    """Agrupa los pases por departamento del solicitante.

    Devuelve una lista de dicts ``{'departamento', 'total', 'items'}`` ordenada
    por total descendente y nombre. Además asigna ``departamento_nombre`` a cada
    solicitud (lo usa la plantilla).
    """
    resumen = {}
    for s in solicitudes:
        nombre = departamento_de(s)
        r = resumen.setdefault(nombre, {'departamento': nombre, 'total': 0, 'items': 0})
        r['total'] += 1
        r['items'] += s.num_items
        s.departamento_nombre = nombre
    return sorted(resumen.values(), key=lambda r: (-r['total'], r['departamento']))


HEADERS_PASES = [
    'Pase #', 'Fecha', 'Departamento', 'Solicitante', 'Estado',
    'Orden de Trabajo', 'Tipo OT', 'Ubicación Origen', 'Artículos',
    'Días sin justificar', 'Comentarios',
]


def fila_pase(s, ahora):
    """Valores de una fila del Excel de pases pendientes."""
    ot = s.orden_trabajo
    return [
        s.id,
        timezone.localtime(s.fecha_solicitud).strftime('%d/%m/%Y %H:%M'),
        departamento_de(s),
        s.solicitante_nombre,
        s.get_estado_display(),
        (ot.codigo_de_orden or f'OT-{ot.id}') if ot else '',
        ot.get_tipo_display() if ot else '',
        s.ubicacion_origen.nombre if s.ubicacion_origen else '',
        s.num_items,
        (ahora - s.fecha_solicitud).days,
        (s.comentarios_solicitud or '')[:500],
    ]


def libro_excel_pases(pases_qs, ahora):
    """Workbook de openpyxl con los pases pendientes de justificar."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pases sin justificar"
    escribir_headers(ws, HEADERS_PASES)
    _, _, _, border = estilos()

    row = 2
    for s in pases_qs.iterator(chunk_size=1000):
        for col, val in enumerate(fila_pase(s, ahora), 1):
            ws.cell(row=row, column=col, value=val).border = border
        row += 1
    autoajustar(ws, len(HEADERS_PASES))
    return wb


# ---------------------------------------------------------------------------
# Movimientos de inventario
# ---------------------------------------------------------------------------

HEADERS_MOVIMIENTOS = [
    'ID', 'Fecha', 'Tipo', 'Estado', 'SKU', 'Material', 'Categoría',
    'Unidad', 'Lote', 'Cantidad', 'Cant. Solicitada',
    'Ubicación Origen', 'Ubicación Destino', 'Ubic. Específica',
    'Orden de Trabajo', 'Activo(s) Vinculado(s)', 'Solicitud',
    'Ingreso', 'Devolución', 'Usuario', 'Aprobado Por',
    'Fecha Aprobación', 'Inconsistente', 'Comentarios',
]


def fila_movimiento(m, activos_por_mov, tipo_display):
    """Valores de una fila del Excel de movimientos."""
    activos = ', '.join(activos_por_mov.get(m.id, []))
    return [
        m.id,
        timezone.localtime(m.fecha_movimiento).strftime('%d/%m/%Y %H:%M') if m.fecha_movimiento else '',
        tipo_display.get(m.tipo, m.tipo),
        m.get_estado_display(),
        m.material.sku if m.material else '',
        m.material.nombre if m.material else '',
        m.material.categoria.nombre if m.material and m.material.categoria else '',
        (m.material.unidad_medida.abreviatura if m.material and m.material.unidad_medida else ''),
        m.lote.codigo if m.lote else '',
        float(m.cantidad) if m.cantidad is not None else 0,
        float(m.cantidad_solicitada) if m.cantidad_solicitada is not None else 0,
        m.ubicacion_origen.nombre if m.ubicacion_origen else '',
        m.ubicacion_destino.nombre if m.ubicacion_destino else '',
        m.ubicacion_especifica or '',
        m.orden_trabajo.codigo_de_orden if m.orden_trabajo else '',
        activos,
        str(m.solicitud_id) if m.solicitud_id else '',
        str(m.ingreso_id) if m.ingreso_id else '',
        str(m.devolucion_id) if m.devolucion_id else '',
        m.usuario.get_full_name() or m.usuario.username if m.usuario else '',
        m.aprobado_por.get_full_name() or m.aprobado_por.username if m.aprobado_por else '',
        timezone.localtime(m.fecha_aprobacion).strftime('%d/%m/%Y %H:%M') if m.fecha_aprobacion else '',
        'Sí' if m.es_inconsistente else 'No',
        (m.comentarios or '')[:500],
    ]


def libro_excel_movimientos(movimientos_qs, activos_por_mov):
    """Workbook de openpyxl con los movimientos de inventario."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    escribir_headers(ws, HEADERS_MOVIMIENTOS)
    _, _, _, border = estilos()
    tipo_display = dict(MovimientoInventario.TIPO_MOVIMIENTO)

    row = 2
    for m in movimientos_qs.iterator(chunk_size=1000):
        for col, val in enumerate(fila_movimiento(m, activos_por_mov, tipo_display), 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = border
        row += 1

    autoajustar(ws, len(HEADERS_MOVIMIENTOS))
    return wb
