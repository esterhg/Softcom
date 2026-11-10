"""
Vistas de los reportes de inventario.

Capa de vistas (HTTP): leen ``request.GET``, delegan las consultas a
``inventarios.selectors.reportes`` y la lógica/armado de Excel a
``inventarios.services.reportes``, y devuelven la respuesta.

Rutas: ``inventarios/urls_reportes.py``.
Permisos: ``inventarios/permissions.py``.

Pendiente de migrar a capas (fuera del paso 1): centro de reportes,
inventario actual y catálogo completo; por eso siguen aquí con su lógica.
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from activos.models import Ubicacion
from core import filtros_columna
from core.excel import autoajustar, escribir_headers, estilos, respuesta_xlsx
from core.fechas import parse_fecha_iso
from core.navegacion import querystring_sin
from .models import (
    Material,
    MovimientoInventario,
    StockRecord,
    CategoriaMaterial,
)
from .permissions import (  # noqa: F401  (reexportados por compatibilidad)
    GRUPO_SUPERVISOR_ALMACEN,
    es_supervisor_almacen,
    supervisor_almacen_required,
)
from .selectors import reportes as sel
from .services import reportes as svc

# ---------------------------------------------------------------------------
# Compatibilidad: nombres que existían en este módulo antes de separar capas.
# Los usan los exports que aún no se migran (inventario actual, catálogo).
# ---------------------------------------------------------------------------
_estilos = estilos
_escribir_headers = escribir_headers
_autoajustar = autoajustar
_parse_fecha = parse_fecha_iso

COLUMNAS_MOVIMIENTOS = sel.COLUMNAS_MOVIMIENTOS
COLUMNAS_PASES = sel.COLUMNAS_PASES
aplicar_filtros = filtros_columna.aplicar_filtros


def aplicar_filtros_columnas(qs, params):
    """Compatibilidad: filtros por columna de la tabla de movimientos."""
    return filtros_columna.aplicar_filtros(qs, params, sel.COLUMNAS_MOVIMIENTOS)


def columnas_con_estado(params, columnas=None):
    """Compatibilidad: por defecto usa las columnas de movimientos."""
    columnas = sel.COLUMNAS_MOVIMIENTOS if columnas is None else columnas
    return filtros_columna.columnas_con_estado(params, columnas)


def _pases_pendientes_qs(request):
    """Compatibilidad: ver ``inventarios.selectors.reportes.pases_pendientes``."""
    return sel.pases_pendientes(request.GET)


_departamento_de = sel.departamento_de


def _nombre_usuario(u):
    return (u.get_full_name() or u.username) if u else ''

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
      - op_<col>/val_<col>  (filtros por columna de la tabla de movimientos)
    """
    qs = sel.movimientos_export(request.GET)
    wb = svc.libro_excel_movimientos(qs, sel.activos_por_movimiento(qs))
    return respuesta_xlsx(wb, 'movimientos_inventario')


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

@supervisor_almacen_required
def reporte_pases_pendientes_view(request):
    """Pases de salida pendientes de justificar con OTNP o Ticket, de todos los departamentos."""
    from core.models import Departamento

    solicitudes = list(sel.pases_pendientes(request.GET))
    resumen = svc.resumen_por_departamento(solicitudes)

    context = {
        'solicitudes': solicitudes,
        'resumen': resumen,
        'total': len(solicitudes),
        'departamentos': Departamento.objects.order_by('nombre'),
        'f_departamento': request.GET.get('departamento', ''),
        'f_desde': request.GET.get('desde', ''),
        'f_hasta': request.GET.get('hasta', ''),
        'columnas': filtros_columna.columnas_con_estado(request.GET, sel.COLUMNAS_PASES),
        # Estado completo de la pantalla para el enlace de exportación
        'querystring': querystring_sin(request.GET),
        'title': 'Pases de salida pendientes de justificar',
        'active_tab': 'reportes',
    }
    return render(request, 'inventarios/reporte_pases_pendientes.html', context)


@supervisor_almacen_required
def export_pases_pendientes_excel(request):
    """Exporta a Excel los pases de salida pendientes de justificar (mismos filtros que la vista)."""
    ahora = timezone.now()
    wb = svc.libro_excel_pases(sel.pases_pendientes(request.GET), ahora)
    return respuesta_xlsx(wb, 'pases_pendientes_justificar', ahora)


# ---------------------------------------------------------------------------
# Tabla de movimientos (producto, quién registró, quién aprobó, estado)
# ---------------------------------------------------------------------------

@supervisor_almacen_required
def tabla_movimientos_view(request):
    """Tabla paginada de movimientos con responsables y estado, solo para el Supervisor de Almacén."""
    qs = sel.movimientos_tabla(request.GET)
    page = Paginator(qs, 50).get_page(request.GET.get('page') or 1)

    context = {
        'page': page,
        'tipos_movimiento': MovimientoInventario.TIPO_MOVIMIENTO,
        'estados_movimiento': sel.ESTADOS_MOVIMIENTO,
        'f_tipo': request.GET.get('tipo', ''),
        'f_estado': request.GET.get('estado', ''),
        'f_q': (request.GET.get('q') or '').strip(),
        'f_desde': request.GET.get('desde', ''), 'f_hasta': request.GET.get('hasta', ''),
        # Filtros actuales sin 'page' para los enlaces de paginación y exportación
        'querystring': querystring_sin(request.GET, 'page'),
        'columnas': filtros_columna.columnas_con_estado(request.GET, sel.COLUMNAS_MOVIMIENTOS),
        'title': 'Movimientos de Inventario',
        'active_tab': 'movimientos',
    }
    return render(request, 'inventarios/tabla_movimientos.html', context)
