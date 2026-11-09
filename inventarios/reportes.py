"""
Reportes de Inventario: exportación a Excel de movimientos (entradas, salidas,
ajustes, traslados) con vínculos a Activo / OT / Devolución / Ingreso, y del
inventario actual (existencias por ubicación).
"""
from datetime import datetime, time as dtime
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import CharField, Q, Sum, Value
from django.db.models.functions import Cast, Concat, TruncDate
from django.http import HttpResponse, HttpResponseForbidden
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

# Grupo con acceso exclusivo (junto con superusuarios) a todos los reportes.
GRUPO_SUPERVISOR_ALMACEN = 'Supervisor de Almacen'


def es_supervisor_almacen(user):
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=GRUPO_SUPERVISOR_ALMACEN).exists())
    )


def supervisor_almacen_required(view):
    """Login + pertenencia al grupo 'Supervisor de Almacen' (o superusuario)."""
    @wraps(view)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not es_supervisor_almacen(request.user):
            return HttpResponseForbidden("Solo el Supervisor de Almacén puede ver los reportes.")
        return view(request, *args, **kwargs)
    return _wrapped

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

@supervisor_almacen_required
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

@supervisor_almacen_required
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

    # Mismos filtros por columna que la tabla de movimientos (op_<col>/val_<col>)
    qs = aplicar_filtros_columnas(qs, request.GET)

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

@supervisor_almacen_required
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

@supervisor_almacen_required
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


# ---------------------------------------------------------------------------
# Reporte: Pases de salida pendientes de justificar (sin OTNP ni Ticket)
# ---------------------------------------------------------------------------

def _pases_pendientes_qs(request):
    """
    Pases de salida (SolicitudMaterial) NO justificados: sin Ticket y sin una
    OT de tipo No Programada (OTNP). Se excluyen borradores y rechazados.
    """
    from .models import SolicitudMaterial
    from django.db.models import Count

    qs = (
        SolicitudMaterial.objects
        .exclude(estado__in=['BORRADOR', 'RECHAZADO'])
        .filter(ticket__isnull=True)
        .filter(Q(orden_trabajo__isnull=True) | ~Q(orden_trabajo__tipo='NO_PROGRAMADA'))
        .select_related(
            'usuario', 'usuario__perfil', 'usuario__perfil__departamento',
            'orden_trabajo', 'ubicacion_origen',
        )
        .annotate(num_items=Count('items'))
        .order_by('-fecha_solicitud')
    )

    depto = request.GET.get('departamento')
    if depto == 'none':
        qs = qs.filter(
            Q(usuario__perfil__isnull=True) | Q(usuario__perfil__departamento__isnull=True)
        )
    elif depto and depto.isdigit():
        qs = qs.filter(usuario__perfil__departamento_id=int(depto))

    desde = _parse_fecha(request.GET.get('desde'))
    hasta = _parse_fecha(request.GET.get('hasta'), fin=True)
    if desde:
        qs = qs.filter(fecha_solicitud__gte=desde)
    if hasta:
        qs = qs.filter(fecha_solicitud__lte=hasta)
    return qs


def _departamento_de(solicitud):
    perfil = getattr(solicitud.usuario, 'perfil', None)
    depto = getattr(perfil, 'departamento', None)
    return depto.nombre if depto else 'Sin departamento'


@supervisor_almacen_required
def reporte_pases_pendientes_view(request):
    """Pases de salida pendientes de justificar con OTNP o Ticket, de todos los departamentos."""
    from core.models import Departamento

    solicitudes = list(_pases_pendientes_qs(request))

    # Resumen por departamento
    resumen = {}
    for s in solicitudes:
        nombre = _departamento_de(s)
        r = resumen.setdefault(nombre, {'departamento': nombre, 'total': 0, 'items': 0})
        r['total'] += 1
        r['items'] += s.num_items
        s.departamento_nombre = nombre
    resumen = sorted(resumen.values(), key=lambda r: (-r['total'], r['departamento']))

    context = {
        'solicitudes': solicitudes,
        'resumen': resumen,
        'total': len(solicitudes),
        'departamentos': Departamento.objects.order_by('nombre'),
        'f_departamento': request.GET.get('departamento', ''),
        'f_desde': request.GET.get('desde', ''),
        'f_hasta': request.GET.get('hasta', ''),
        'title': 'Pases de salida pendientes de justificar',
        'active_tab': 'reportes',
    }
    return render(request, 'inventarios/reporte_pases_pendientes.html', context)


@supervisor_almacen_required
def export_pases_pendientes_excel(request):
    """Exporta a Excel los pases de salida pendientes de justificar (mismos filtros que la vista)."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pases sin justificar"
    headers = [
        'Pase #', 'Fecha', 'Departamento', 'Solicitante', 'Estado',
        'Orden de Trabajo', 'Tipo OT', 'Ubicación Origen', 'Artículos',
        'Días sin justificar', 'Comentarios',
    ]
    _escribir_headers(ws, headers)
    _, _, _, border = _estilos()

    ahora = timezone.now()
    row = 2
    for s in _pases_pendientes_qs(request).iterator(chunk_size=1000):
        ot = s.orden_trabajo
        valores = [
            s.id,
            timezone.localtime(s.fecha_solicitud).strftime('%d/%m/%Y %H:%M'),
            _departamento_de(s),
            s.solicitante_nombre,
            s.get_estado_display(),
            (ot.codigo_de_orden or f'OT-{ot.id}') if ot else '',
            ot.get_tipo_display() if ot else '',
            s.ubicacion_origen.nombre if s.ubicacion_origen else '',
            s.num_items,
            (ahora - s.fecha_solicitud).days,
            (s.comentarios_solicitud or '')[:500],
        ]
        for col, val in enumerate(valores, 1):
            ws.cell(row=row, column=col, value=val).border = border
        row += 1
    _autoajustar(ws, len(headers))

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    stamp = timezone.localtime(ahora).strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="pases_pendientes_justificar_{stamp}.xlsx"'
    wb.save(response)
    return response


# ---------------------------------------------------------------------------
# Tabla de movimientos (producto, quién registró, quién aprobó, estado)
# ---------------------------------------------------------------------------

def _nombre_usuario(u):
    return (u.get_full_name() or u.username) if u else ''


# ---------------------------------------------------------------------------
# Filtros por columna de la tabla de movimientos
#   GET: op_<columna>=<operador>  y  val_<columna>=<texto>
# ---------------------------------------------------------------------------

OP_TEXTO = [
    ('contiene', 'Contiene'), ('no_contiene', 'No contiene'), ('igual', 'Es igual a'),
    ('tiene', 'Solo con datos'), ('vacio', 'Solo sin datos'),
]
OP_ELECCION = [('contiene', 'Contiene'), ('no_contiene', 'No contiene'), ('igual', 'Es igual a')]
OP_NUMERO = [('igual', 'Es igual a'), ('mayor', 'Mayor que'), ('menor', 'Menor que')]
OP_FECHA = [
    ('igual', 'Es igual a'), ('contiene', 'Contiene'), ('mayor', 'Desde'), ('menor', 'Hasta'),
]

_OPS_SIN_VALOR = ('tiene', 'vacio')


def _anotaciones_texto():
    """Anotaciones auxiliares (texto) usadas por los filtros de columna."""
    nombre = lambda base: Concat(
        f'{base}__first_name', Value(' '), f'{base}__last_name', output_field=CharField()
    )
    return {
        'ann_fecha': Cast(TruncDate('fecha_movimiento'), CharField()),
        'ann_sol': Cast('solicitud_id', CharField()),
        'ann_ing': Cast('ingreso_id', CharField()),
        'ann_registro': nombre('usuario'),
        'ann_aprobo': nombre('aprobado_por'),
        'ann_entrego': nombre('solicitud__entregado_por'),
    }


def _persona(base, ann):
    return {
        'kind': 'texto', 'ops': OP_TEXTO,
        'campos': [f'{base}__username', f'{base}__first_name', f'{base}__last_name', ann],
        'anotar': [ann], 'presencia': Q(**{f'{base}__isnull': False}),
    }


COLUMNAS_MOVIMIENTOS = [
    {'key': 'fecha', 'label': 'Fecha', 'kind': 'fecha', 'ops': OP_FECHA,
     'campos': ['ann_fecha'], 'anotar': ['ann_fecha'], 'placeholder': 'AAAA-MM-DD o DD/MM/AAAA'},
    {'key': 'tipo', 'label': 'Tipo', 'kind': 'eleccion', 'ops': OP_ELECCION,
     'campo': 'tipo', 'opciones': MovimientoInventario.TIPO_MOVIMIENTO},
    {'key': 'estado', 'label': 'Estado', 'kind': 'eleccion', 'ops': OP_ELECCION,
     'campo': 'estado', 'opciones': [('PENDIENTE', 'Pendiente'), ('APROBADO', 'Aprobado / Liquidado'), ('RECHAZADO', 'Rechazado')]},
    {'key': 'producto', 'label': 'Producto', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['material__nombre', 'material__sku'], 'anotar': [],
     'presencia': Q(material__isnull=False)},
    {'key': 'cantidad', 'label': 'Cantidad', 'kind': 'numero', 'ops': OP_NUMERO,
     'campo': 'cantidad', 'placeholder': 'Número'},
    {'key': 'pase', 'label': 'Pase / Ingreso', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ann_sol', 'ann_ing'], 'anotar': ['ann_sol', 'ann_ing'],
     'presencia': Q(solicitud__isnull=False) | Q(ingreso__isnull=False), 'placeholder': 'N° de pase o ingreso'},
    {'key': 'ot', 'label': 'OT', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['orden_trabajo__codigo_de_orden'], 'anotar': [],
     'presencia': Q(orden_trabajo__isnull=False)},
    dict(key='registro', label='Registró / Solicitó', **_persona('usuario', 'ann_registro')),
    dict(key='aprobo', label='Aprobó', **_persona('aprobado_por', 'ann_aprobo')),
    dict(key='entrego', label='Entregó', **_persona('solicitud__entregado_por', 'ann_entrego')),
    {'key': 'origen', 'label': 'Origen', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ubicacion_origen__nombre'], 'anotar': [],
     'presencia': Q(ubicacion_origen__isnull=False)},
    {'key': 'destino', 'label': 'Destino', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ubicacion_destino__nombre'], 'anotar': [],
     'presencia': Q(ubicacion_destino__isnull=False)},
]


def _parse_fecha_flexible(valor):
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(valor.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _q_campos(campos, lookup, valor):
    q = Q()
    for c in campos:
        q |= Q(**{f'{c}__{lookup}': valor})
    return q


def aplicar_filtros_columnas(qs, params):
    """Aplica a `qs` los filtros por columna recibidos en `params` (request.GET)."""
    anotaciones = _anotaciones_texto()
    for col in COLUMNAS_MOVIMIENTOS:
        op = (params.get(f"op_{col['key']}") or '').strip()
        valor = (params.get(f"val_{col['key']}") or '').strip()
        if not op or op not in dict(col['ops']):
            continue
        if op not in _OPS_SIN_VALOR and not valor:
            continue  # operador sin texto: no filtra

        for nombre in col.get('anotar', []):
            qs = qs.annotate(**{nombre: anotaciones[nombre]})

        kind = col['kind']
        if op == 'tiene':
            qs = qs.filter(col['presencia'])
        elif op == 'vacio':
            qs = qs.exclude(col['presencia'])
        elif kind == 'texto':
            if op == 'contiene':
                qs = qs.filter(_q_campos(col['campos'], 'icontains', valor))
            elif op == 'no_contiene':
                qs = qs.exclude(_q_campos(col['campos'], 'icontains', valor))
            elif op == 'igual':
                qs = qs.filter(_q_campos(col['campos'], 'iexact', valor))
        elif kind == 'eleccion':
            v = valor.lower()
            if op == 'igual':
                codigos = [c for c, l in col['opciones'] if v in (c.lower(), l.lower())]
            else:
                codigos = [c for c, l in col['opciones'] if v in c.lower() or v in l.lower()]
            if op == 'no_contiene':
                qs = qs.exclude(**{f"{col['campo']}__in": codigos})
            else:
                qs = qs.filter(**{f"{col['campo']}__in": codigos})
        elif kind == 'numero':
            try:
                num = Decimal(valor.replace(',', '.'))
            except InvalidOperation:
                continue
            lookup = {'igual': 'exact', 'mayor': 'gt', 'menor': 'lt'}[op]
            qs = qs.filter(**{f"{col['campo']}__{lookup}": num})
        elif kind == 'fecha':
            if op == 'contiene':
                qs = qs.filter(ann_fecha__icontains=valor)
                continue
            dia = _parse_fecha_flexible(valor)
            if not dia:
                continue
            if op == 'igual':
                qs = qs.filter(fecha_movimiento__date=dia)
            elif op == 'mayor':
                qs = qs.filter(fecha_movimiento__date__gte=dia)
            elif op == 'menor':
                qs = qs.filter(fecha_movimiento__date__lte=dia)
    return qs


def columnas_con_estado(params):
    """Columnas con el operador/valor actuales (para repintar los filtros en la tabla)."""
    placeholders = {'texto': 'Texto a buscar', 'eleccion': 'Texto a buscar', 'numero': 'Número', 'fecha': 'AAAA-MM-DD'}
    resultado = []
    for col in COLUMNAS_MOVIMIENTOS:
        op = (params.get(f"op_{col['key']}") or '').strip()
        resultado.append({
            'key': col['key'], 'label': col['label'], 'ops': col['ops'],
            'op': op, 'val': (params.get(f"val_{col['key']}") or '').strip(),
            'placeholder': col.get('placeholder') or placeholders[col['kind']],
            'sin_valor': op in _OPS_SIN_VALOR,
        })
    return resultado


@supervisor_almacen_required
def tabla_movimientos_view(request):
    """Tabla paginada de movimientos con responsables y estado, solo para el Supervisor de Almacén."""
    from django.core.paginator import Paginator

    qs = MovimientoInventario.objects.select_related(
        'material', 'material__unidad_medida', 'usuario', 'aprobado_por',
        'ubicacion_origen', 'ubicacion_destino', 'orden_trabajo',
        'solicitud', 'solicitud__entregado_por', 'solicitud__usuario',
        'ingreso',
    ).order_by('-fecha_movimiento')

    tipo = request.GET.get('tipo', '')
    estado = request.GET.get('estado', '')
    q = (request.GET.get('q') or '').strip()
    desde = _parse_fecha(request.GET.get('desde'))
    hasta = _parse_fecha(request.GET.get('hasta'), fin=True)

    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if desde:
        qs = qs.filter(fecha_movimiento__gte=desde)
    if hasta:
        qs = qs.filter(fecha_movimiento__lte=hasta)
    if q:
        qs = qs.filter(
            Q(material__nombre__icontains=q) | Q(material__sku__icontains=q)
            | Q(usuario__username__icontains=q) | Q(usuario__first_name__icontains=q)
            | Q(usuario__last_name__icontains=q)
            | Q(aprobado_por__username__icontains=q)
            | Q(orden_trabajo__codigo_de_orden__icontains=q)
        )

    qs = aplicar_filtros_columnas(qs, request.GET)

    page = Paginator(qs, 50).get_page(request.GET.get('page') or 1)

    # Parámetros de filtro sin 'page' para los links de paginación
    params = request.GET.copy()
    params.pop('page', None)

    context = {
        'page': page,
        'tipos_movimiento': MovimientoInventario.TIPO_MOVIMIENTO,
        'estados_movimiento': [
            ('PENDIENTE', 'Pendiente'),
            ('APROBADO', 'Aprobado / Liquidado'),
            ('RECHAZADO', 'Rechazado'),
        ],
        'f_tipo': tipo, 'f_estado': estado, 'f_q': q,
        'f_desde': request.GET.get('desde', ''), 'f_hasta': request.GET.get('hasta', ''),
        'querystring': params.urlencode(),
        'columnas': columnas_con_estado(request.GET),
        'hay_filtros_columna': any(c['op'] for c in columnas_con_estado(request.GET)),
        'title': 'Movimientos de Inventario',
        'active_tab': 'movimientos',
    }
    return render(request, 'inventarios/tabla_movimientos.html', context)
