"""
Reportes de Inventario: exportación a Excel de movimientos (entradas, salidas,
ajustes, traslados) con vínculos a Activo / OT / Devolución / Ingreso, y del
inventario actual (existencias por ubicación).
"""
from datetime import datetime, time as dtime

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from activos.models import Ubicacion
from .models import (
    Material,
    MovimientoInventario,
    StockRecord,
    CategoriaMaterial,
    MaterialUtilizadoOT,
)

# ---------------------------------------------------------------------------
# Estilos reutilizables para openpyxl
# ---------------------------------------------------------------------------

def _estilos():
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    header_font = Font(name='Arial', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='0070F2', end_color='0070F2', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin', color='D9D9D9')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, header_align, border


def _escribir_headers(ws, headers):
    header_font, header_fill, header_align, border = _estilos()
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border
    ws.freeze_panes = 'A2'


def _autoajustar(ws, num_cols, max_width=55):
    from openpyxl.utils import get_column_letter
    for i in range(1, num_cols + 1):
        letter = get_column_letter(i)
        max_length = 0
        for cell in ws[letter]:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max_length + 2, max_width)


def _parse_fecha(valor, fin=False):
    """Convierte 'YYYY-MM-DD' en datetime aware. fin=True -> 23:59:59."""
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


# ---------------------------------------------------------------------------
# Página de Reportes
# ---------------------------------------------------------------------------

@login_required
def reporte_inventario_view(request):
    """Página con el centro de descargas de reportes de inventario."""
    ubicaciones = Ubicacion.objects.filter(
        Q(tipo='BODEGA') | Q(tipo='ALMACEN') | Q(es_almacen=True)
    ).order_by('nombre')
    categorias = CategoriaMaterial.objects.all().order_by('nombre')

    context = {
        'ubicaciones': ubicaciones,
        'categorias': categorias,
        'tipos_movimiento': MovimientoInventario.TIPO_MOVIMIENTO,
        'tipos_material': Material.TIPO_MATERIAL_CHOICES,
        'estados_movimiento': [
            ('PENDIENTE', 'Pendiente'),
            ('APROBADO', 'Aprobado / Liquidado'),
            ('RECHAZADO', 'Rechazado'),
        ],
        'title': 'Reportes de Inventario',
        'active_tab': 'reportes',
    }
    return render(request, 'inventarios/reporte_inventario.html', context)


# ---------------------------------------------------------------------------
# Export: Movimientos de Inventario
# ---------------------------------------------------------------------------

@login_required
def export_movimientos_excel(request):
    """
    Exporta todos los movimientos de inventario a Excel.

    Filtros soportados (GET):
      - desde=YYYY-MM-DD, hasta=YYYY-MM-DD  (fecha_movimiento)
      - tipo=ENTRADA|SALIDA|AJUSTE|TRASLADO
      - estado=PENDIENTE|APROBADO|RECHAZADO
      - ubicacion=<id>  (origen o destino)
      - categoria=<id>  (categoría del material)
    """
    import openpyxl

    qs = MovimientoInventario.objects.select_related(
        'material', 'material__categoria', 'material__unidad_medida',
        'lote', 'ubicacion_origen', 'ubicacion_destino',
        'orden_trabajo', 'usuario', 'aprobado_por',
        'solicitud', 'ingreso', 'devolucion',
    ).order_by('-fecha_movimiento')

    desde = _parse_fecha(request.GET.get('desde'))
    hasta = _parse_fecha(request.GET.get('hasta'), fin=True)
    tipo = request.GET.get('tipo')
    estado = request.GET.get('estado')
    ubicacion_id = request.GET.get('ubicacion')
    categoria_id = request.GET.get('categoria')

    if desde:
        qs = qs.filter(fecha_movimiento__gte=desde)
    if hasta:
        qs = qs.filter(fecha_movimiento__lte=hasta)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if ubicacion_id:
        qs = qs.filter(Q(ubicacion_origen_id=ubicacion_id) | Q(ubicacion_destino_id=ubicacion_id))
    if categoria_id:
        qs = qs.filter(material__categoria_id=categoria_id)

    # Mapa de activos aplicados por movimiento (vía MaterialUtilizadoOT).
    # Se construye desde TODOS los movimientos del queryset filtrado (sin límite).
    activos_por_mov = {}
    usos = MaterialUtilizadoOT.objects.filter(
        movimiento__in=qs, activo__isnull=False
    ).select_related('activo').values_list(
        'movimiento_id', 'activo__nombre', 'activo__codigo_interno', 'activo_id'
    )
    for mov_id, act_nombre, act_codigo, act_id in usos.iterator(chunk_size=2000):
        activos_por_mov.setdefault(mov_id, []).append(
            f"{act_nombre} ({act_codigo or act_id})"
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimientos"

    headers = [
        'ID', 'Fecha', 'Tipo', 'Estado', 'SKU', 'Material', 'Categoría',
        'Unidad', 'Lote', 'Cantidad', 'Cant. Solicitada',
        'Ubicación Origen', 'Ubicación Destino', 'Ubic. Específica',
        'Orden de Trabajo', 'Activo(s) Vinculado(s)', 'Solicitud',
        'Ingreso', 'Devolución', 'Usuario', 'Aprobado Por',
        'Fecha Aprobación', 'Inconsistente', 'Comentarios',
    ]
    _escribir_headers(ws, headers)

    _, _, _, border = _estilos()
    tipo_display = dict(MovimientoInventario.TIPO_MOVIMIENTO)

    row = 2
    for m in qs.iterator(chunk_size=1000):
        activos = ', '.join(activos_por_mov.get(m.id, []))
        valores = [
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
        for col, val in enumerate(valores, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = border
        row += 1

    _autoajustar(ws, len(headers))

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    stamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="movimientos_inventario_{stamp}.xlsx"'
    wb.save(response)
    return response


# ---------------------------------------------------------------------------
# Export: Inventario Actual (existencias)
# ---------------------------------------------------------------------------

@login_required
def export_inventario_actual_excel(request):
    """
    Exporta el inventario actual (existencias por ubicación) a Excel.

    Filtros soportados (GET):
      - ubicacion=<id>
      - categoria=<id>
      - con_stock=1  (solo cantidad distinta de cero)
    """
    import openpyxl

    qs = StockRecord.objects.select_related(
        'material', 'material__categoria', 'material__unidad_medida',
        'material__marca', 'lote', 'ubicacion',
    ).order_by('material__nombre', 'ubicacion__nombre')

    ubicacion_id = request.GET.get('ubicacion')
    categoria_id = request.GET.get('categoria')
    con_stock = request.GET.get('con_stock')

    if ubicacion_id:
        qs = qs.filter(ubicacion_id=ubicacion_id)
    if categoria_id:
        qs = qs.filter(material__categoria_id=categoria_id)
    if con_stock in ('1', 'true', 'on'):
        qs = qs.exclude(cantidad=0)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventario Actual"

    headers = [
        'SKU', 'Material', 'Categoría', 'Tipo', 'Marca', 'Unidad',
        'Ubicación', 'Ubic. Específica', 'Lote', 'Vencimiento',
        'Cantidad', 'Stock Mínimo', 'Precio Estimado', 'Valor Total',
        'Actualizado',
    ]
    _escribir_headers(ws, headers)

    _, _, _, border = _estilos()

    row = 2
    total_valor = 0.0
    for s in qs.iterator(chunk_size=1000):
        mat = s.material
        precio = float(mat.precio_estimado or 0) if mat else 0
        cantidad = float(s.cantidad or 0)
        valor = precio * cantidad
        total_valor += valor
        valores = [
            mat.sku if mat else '',
            mat.nombre if mat else '',
            mat.categoria.nombre if mat and mat.categoria else '',
            mat.get_tipo_material_display() if mat and mat.tipo_material else '',
            mat.marca.nombre if mat and mat.marca else '',
            mat.unidad_medida.abreviatura if mat and mat.unidad_medida else '',
            s.ubicacion.nombre if s.ubicacion else '',
            s.ubicacion_especifica or '',
            s.lote.codigo if s.lote else '',
            s.lote.fecha_vencimiento.strftime('%d/%m/%Y') if s.lote and s.lote.fecha_vencimiento else '',
            cantidad,
            float(mat.stock_minimo or 0) if mat else 0,
            precio,
            round(valor, 2),
            timezone.localtime(s.actualizado_en).strftime('%d/%m/%Y %H:%M') if s.actualizado_en else '',
        ]
        for col, val in enumerate(valores, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = border
        row += 1

    # Fila de total
    if row > 2:
        from openpyxl.styles import Font
        ws.cell(row=row, column=13, value='TOTAL:').font = Font(bold=True)
        total_cell = ws.cell(row=row, column=14, value=round(total_valor, 2))
        total_cell.font = Font(bold=True)

    _autoajustar(ws, len(headers))

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    stamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="inventario_actual_{stamp}.xlsx"'
    wb.save(response)
    return response


# ---------------------------------------------------------------------------
# Export: Catálogo Completo (todos los materiales, con o sin stock)
# ---------------------------------------------------------------------------

@login_required
def export_catalogo_excel(request):
    """
    Exporta TODO el catálogo de materiales a Excel, aparezcan o no en
    existencias o movimientos. Incluye el stock total consolidado y la(s)
    ubicación(es)/bodega(s) donde el material tiene existencia.

    La relación material↔ubicación se obtiene de StockRecord. Un material que
    no está asignado a ninguna ubicación deja la columna "Ubicaciones" vacía.

    Filtros soportados (GET):
      - ubicacion=<id>  (solo materiales con existencia en esa ubicación)
      - categoria=<id>
      - tipo=<tipo_material>
    """
    import openpyxl
    from django.db.models import Sum, OuterRef, Subquery, DecimalField
    from django.db.models.functions import Coalesce
    from decimal import Decimal

    ubicacion_id = request.GET.get('ubicacion')
    categoria_id = request.GET.get('categoria')
    tipo = request.GET.get('tipo')

    # Stock total por material (suma de existencias)
    stock_sub = StockRecord.objects.filter(material=OuterRef('pk')).values(
        'material'
    ).annotate(total=Sum('cantidad')).values('total')

    qs = Material.objects.select_related(
        'categoria', 'unidad_medida', 'marca'
    ).annotate(
        stock_total=Coalesce(
            Subquery(stock_sub, output_field=DecimalField()), Decimal('0.00')
        )
    ).order_by('nombre')

    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if tipo:
        qs = qs.filter(tipo_material=tipo)

    # Si se filtra por ubicación, limitar a materiales con existencia ahí.
    ubicacion_sel = None
    if ubicacion_id:
        qs = qs.filter(existencias__ubicacion_id=ubicacion_id).distinct()
        ubicacion_sel = Ubicacion.objects.filter(pk=ubicacion_id).first()

    material_ids = list(qs.values_list('id', flat=True))

    # Mapa de ubicaciones por material desde StockRecord.
    # - Sin filtro: lista de todas las bodegas donde hay existencia.
    # - Con filtro: datos específicos (ubic. específica y cantidad) de esa ubicación.
    ubic_por_material = {}          # id -> set de nombres de ubicación
    detalle_por_material = {}       # id -> dict con esp/cantidad (solo con filtro)

    sr_qs = StockRecord.objects.filter(material_id__in=material_ids).select_related('ubicacion')
    if ubicacion_id:
        sr_qs = sr_qs.filter(ubicacion_id=ubicacion_id)

    for sr in sr_qs.iterator(chunk_size=2000):
        if sr.ubicacion_id and sr.ubicacion:
            ubic_por_material.setdefault(sr.material_id, set()).add(sr.ubicacion.nombre)
        if ubicacion_id:
            d = detalle_por_material.setdefault(
                sr.material_id, {'esp': set(), 'cantidad': Decimal('0')}
            )
            if sr.ubicacion_especifica:
                d['esp'].add(sr.ubicacion_especifica)
            d['cantidad'] += (sr.cantidad or Decimal('0'))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catálogo"

    headers = [
        'SKU', 'Código de Barras', 'Material', 'Descripción', 'Categoría',
        'Tipo', 'Marca', 'Unidad', 'Precio Estimado', 'Stock Total',
        'Stock Mínimo', 'Valor Total', 'Ubicaciones',
    ]
    if ubicacion_id:
        headers += ['Ubic. Específica', f'Cantidad en {ubicacion_sel.nombre if ubicacion_sel else "Ubicación"}']
    headers += ['No Afecta Stock', 'Técnico', 'Creado']

    _escribir_headers(ws, headers)

    _, _, _, border = _estilos()

    row = 2
    total_valor = 0.0
    for m in qs.iterator(chunk_size=1000):
        precio = float(m.precio_estimado or 0)
        stock = float(m.stock_total or 0)
        valor = precio * stock
        total_valor += valor

        ubicaciones_txt = ', '.join(sorted(ubic_por_material.get(m.id, [])))

        valores = [
            m.sku or '',
            m.codigo_barras or '',
            m.nombre or '',
            (m.descripcion or '')[:300],
            m.categoria.nombre if m.categoria else '',
            m.get_tipo_material_display() if m.tipo_material else '',
            m.marca.nombre if m.marca else '',
            m.unidad_medida.abreviatura if m.unidad_medida else '',
            precio,
            stock,
            float(m.stock_minimo or 0),
            round(valor, 2),
            ubicaciones_txt,  # vacío si no está asignado a ninguna ubicación
        ]

        if ubicacion_id:
            det = detalle_por_material.get(m.id, {})
            esp = ', '.join(sorted(det.get('esp', []))) if det else ''
            cant = float(det.get('cantidad', 0)) if det else 0
            valores += [esp, cant]

        valores += [
            'Sí' if m.no_afecta_stock else 'No',
            'Sí' if m.es_tecnico else 'No',
            timezone.localtime(m.creado_en).strftime('%d/%m/%Y') if m.creado_en else '',
        ]

        for col, val in enumerate(valores, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = border
        row += 1

    # Fila de total (columna "Valor Total" = índice 12)
    if row > 2:
        from openpyxl.styles import Font
        ws.cell(row=row, column=11, value='TOTAL:').font = Font(bold=True)
        total_cell = ws.cell(row=row, column=12, value=round(total_valor, 2))
        total_cell.font = Font(bold=True)

    _autoajustar(ws, len(headers))

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    stamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    sufijo = ''
    if ubicacion_sel:
        import re
        safe = re.sub(r'[^A-Za-z0-9_-]+', '_', ubicacion_sel.nombre).strip('_')
        sufijo = f'_{safe}'
    response['Content-Disposition'] = f'attachment; filename="catalogo_completo{sufijo}_{stamp}.xlsx"'
    wb.save(response)
    return response
