"""
Consultas de los reportes de inventario: movimientos y pases de salida
pendientes de justificar.

Trasladado sin cambios de comportamiento desde ``inventarios/reportes.py``.
"""
from django.db.models import Count, Q

from core.fechas import parse_fecha_iso
from core.filtros_columna import (
    OP_BASICO, OP_FECHA, OP_NUMERO, OP_TEXTO,
    a_texto, aplicar_filtros, fecha_texto, no_vacio, persona,
)
from inventarios.models import MaterialUtilizadoOT, MovimientoInventario, SolicitudMaterial

# ---------------------------------------------------------------------------
# Definición de columnas filtrables (ver core.filtros_columna)
# ---------------------------------------------------------------------------

ESTADOS_MOVIMIENTO = [
    ('PENDIENTE', 'Pendiente'),
    ('APROBADO', 'Aprobado / Liquidado'),
    ('RECHAZADO', 'Rechazado'),
]

COLUMNAS_MOVIMIENTOS = [
    {'key': 'fecha', 'label': 'Fecha', 'kind': 'fecha', 'ops': OP_FECHA,
     'campo': 'fecha_movimiento', 'ann': 'ann_fecha',
     'anotar': {'ann_fecha': fecha_texto('fecha_movimiento')}},
    {'key': 'tipo', 'label': 'Tipo', 'kind': 'eleccion', 'ops': OP_BASICO,
     'campo': 'tipo', 'opciones': MovimientoInventario.TIPO_MOVIMIENTO},
    {'key': 'estado', 'label': 'Estado', 'kind': 'eleccion', 'ops': OP_BASICO,
     'campo': 'estado', 'opciones': ESTADOS_MOVIMIENTO},
    {'key': 'producto', 'label': 'Producto', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['material__nombre', 'material__sku'], 'presencia': Q(material__isnull=False)},
    {'key': 'cantidad', 'label': 'Cantidad', 'kind': 'numero', 'ops': OP_NUMERO, 'campo': 'cantidad'},
    {'key': 'pase', 'label': 'Pase / Ingreso', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ann_sol', 'ann_ing'],
     'anotar': {'ann_sol': a_texto('solicitud_id'), 'ann_ing': a_texto('ingreso_id')},
     'presencia': Q(solicitud__isnull=False) | Q(ingreso__isnull=False), 'placeholder': 'N° de pase o ingreso'},
    {'key': 'ot', 'label': 'OT', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['orden_trabajo__codigo_de_orden'], 'presencia': Q(orden_trabajo__isnull=False)},
    dict(key='registro', label='Registró / Solicitó', **persona('usuario', 'ann_registro')),
    dict(key='aprobo', label='Aprobó', **persona('aprobado_por', 'ann_aprobo')),
    dict(key='entrego', label='Entregó', **persona('solicitud__entregado_por', 'ann_entrego')),
    {'key': 'origen', 'label': 'Origen', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ubicacion_origen__nombre'], 'presencia': Q(ubicacion_origen__isnull=False)},
    {'key': 'destino', 'label': 'Destino', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ubicacion_destino__nombre'], 'presencia': Q(ubicacion_destino__isnull=False)},
]

# Columnas del reporte de pases pendientes (modelo SolicitudMaterial).
# 'num_items' es una anotación Count definida en pases_pendientes().
COLUMNAS_PASES = [
    {'key': 'pase', 'label': 'Pase #', 'kind': 'texto', 'ops': OP_BASICO,
     'campos': ['ann_pase'], 'anotar': {'ann_pase': a_texto('id')}, 'placeholder': 'N° de pase'},
    {'key': 'fecha', 'label': 'Fecha', 'kind': 'fecha', 'ops': OP_FECHA,
     'campo': 'fecha_solicitud', 'ann': 'ann_fecha',
     'anotar': {'ann_fecha': fecha_texto('fecha_solicitud')}},
    {'key': 'departamento', 'label': 'Departamento', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['usuario__perfil__departamento__nombre'],
     'presencia': Q(usuario__perfil__departamento__isnull=False)},
    dict(key='solicitante', label='Solicitante', **persona('usuario', 'ann_solicitante')),
    {'key': 'estado', 'label': 'Estado', 'kind': 'eleccion', 'ops': OP_BASICO, 'campo': 'estado',
     'opciones': [(c, l) for c, l in SolicitudMaterial.ESTADO_CHOICES if c not in ('BORRADOR', 'RECHAZADO')]},
    {'key': 'ot', 'label': 'OT vinculada', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['orden_trabajo__codigo_de_orden'], 'presencia': Q(orden_trabajo__isnull=False)},
    {'key': 'articulos', 'label': 'Artículos', 'kind': 'numero', 'ops': OP_NUMERO, 'campo': 'num_items'},
    {'key': 'comentarios', 'label': 'Comentarios', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['comentarios_solicitud'], 'presencia': no_vacio('comentarios_solicitud')},
]


# ---------------------------------------------------------------------------
# Pases de salida pendientes de justificar
# ---------------------------------------------------------------------------

def pases_pendientes_base():
    """Pases de salida NO justificados, sin filtros de pantalla.

    Regla de negocio: sin Ticket y sin una OT de tipo No Programada (OTNP).
    Se excluyen borradores y rechazados. Anota ``num_items``.
    """
    return (
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


def pases_pendientes(params):
    """Pases pendientes con los filtros de la pantalla aplicados.

    ``params`` (dict/QueryDict): departamento (<id> | 'none'), desde, hasta
    (AAAA-MM-DD) y filtros por columna op_<key>/val_<key> de COLUMNAS_PASES.
    """
    qs = pases_pendientes_base()

    depto = params.get('departamento')
    if depto == 'none':
        qs = qs.filter(
            Q(usuario__perfil__isnull=True) | Q(usuario__perfil__departamento__isnull=True)
        )
    elif depto and depto.isdigit():
        qs = qs.filter(usuario__perfil__departamento_id=int(depto))

    desde = parse_fecha_iso(params.get('desde'))
    hasta = parse_fecha_iso(params.get('hasta'), fin=True)
    if desde:
        qs = qs.filter(fecha_solicitud__gte=desde)
    if hasta:
        qs = qs.filter(fecha_solicitud__lte=hasta)
    # Filtros por columna (panel "Filtrar por" de cada encabezado)
    return aplicar_filtros(qs, params, COLUMNAS_PASES)


def departamento_de(solicitud):
    """Nombre del departamento del solicitante, o 'Sin departamento'."""
    perfil = getattr(solicitud.usuario, 'perfil', None)
    depto = getattr(perfil, 'departamento', None)
    return depto.nombre if depto else 'Sin departamento'


# ---------------------------------------------------------------------------
# Movimientos de inventario
# ---------------------------------------------------------------------------

def movimientos_tabla(params):
    """Movimientos para la tabla en pantalla.

    ``params``: tipo, estado, q (búsqueda libre), desde, hasta y filtros por
    columna op_<key>/val_<key> de COLUMNAS_MOVIMIENTOS.
    """
    qs = MovimientoInventario.objects.select_related(
        'material', 'material__unidad_medida', 'usuario', 'aprobado_por',
        'ubicacion_origen', 'ubicacion_destino', 'orden_trabajo',
        'solicitud', 'solicitud__entregado_por', 'solicitud__usuario',
        'ingreso',
    ).order_by('-fecha_movimiento')

    tipo = params.get('tipo', '')
    estado = params.get('estado', '')
    q = (params.get('q') or '').strip()
    desde = parse_fecha_iso(params.get('desde'))
    hasta = parse_fecha_iso(params.get('hasta'), fin=True)

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

    return aplicar_filtros(qs, params, COLUMNAS_MOVIMIENTOS)


def movimientos_export(params):
    """Movimientos para la exportación a Excel.

    ``params``: desde, hasta, tipo, estado, ubicacion (<id>, origen o destino),
    categoria (<id> del material) y filtros por columna de COLUMNAS_MOVIMIENTOS.
    Nota: la búsqueda libre ``q`` de la tabla no se aplica aquí (comportamiento
    previo conservado).
    """
    qs = MovimientoInventario.objects.select_related(
        'material', 'material__categoria', 'material__unidad_medida',
        'lote', 'ubicacion_origen', 'ubicacion_destino',
        'orden_trabajo', 'usuario', 'aprobado_por',
        'solicitud', 'ingreso', 'devolucion',
    ).order_by('-fecha_movimiento')

    desde = parse_fecha_iso(params.get('desde'))
    hasta = parse_fecha_iso(params.get('hasta'), fin=True)
    tipo = params.get('tipo')
    estado = params.get('estado')
    ubicacion_id = params.get('ubicacion')
    categoria_id = params.get('categoria')

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
    return aplicar_filtros(qs, params, COLUMNAS_MOVIMIENTOS)


def activos_por_movimiento(movimientos_qs):
    """{movimiento_id: ['Activo (código)', ...]} para los movimientos dados.

    Se construye desde TODOS los movimientos del queryset (sin límite), vía
    MaterialUtilizadoOT.
    """
    resultado = {}
    usos = MaterialUtilizadoOT.objects.filter(
        movimiento__in=movimientos_qs, activo__isnull=False
    ).select_related('activo').values_list(
        'movimiento_id', 'activo__nombre', 'activo__codigo_interno', 'activo_id'
    )
    for mov_id, act_nombre, act_codigo, act_id in usos.iterator(chunk_size=2000):
        resultado.setdefault(mov_id, []).append(f"{act_nombre} ({act_codigo or act_id})")
    return resultado
