"""Consultas de lectura de reportes de horas (no escribe en BD)."""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum

from core.fechas import parse_fecha_iso
from core.filtros_columna import (
    OP_FECHA, OP_NUMERO, OP_TEXTO, aplicar_filtros, fecha_texto, no_vacio, persona,
)
from rrhh.models import CategoriaHoraExtra, HoraExtra, ReporteHoras

COLUMNAS_REPORTES = [
    {'key': 'codigo', 'label': 'ID de reporte', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['codigo'], 'presencia': Q(codigo__gt='')},
    dict(key='colaborador', label='Colaborador', **persona('colaborador', 'ann_colaborador')),
    dict(key='autorizado', label='Autorizado por', **persona('autorizado_por', 'ann_autorizado')),
    dict(key='solicitado', label='Solicitado por', **persona('solicitado_por', 'ann_solicitado')),
    {'key': 'fecha', 'label': 'Creado', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['ann_fecha'], 'anotar': {'ann_fecha': fecha_texto('creado_en')},
     'presencia': Q(creado_en__isnull=False)},
    {'key': 'horas', 'label': 'Horas', 'kind': 'numero', 'ops': OP_NUMERO,
     'campo': 'total_horas', 'presencia': Q(total_horas__isnull=False)},
]


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def filtros_horas(params):
    """Filtros simples de la pantalla: (categoria_id, desde, hasta) ya validados.

    ``desde`` / ``hasta`` son ``date`` (fecha de la entrada) o None.
    """
    return (_entero(params.get('categoria')),
            _fecha(params.get('desde')), _fecha(params.get('hasta')))


def _fecha(valor):
    dt = parse_fecha_iso(valor)
    return dt.date() if dt else None


def _q_horas(params, prefijo=''):
    """Q sobre HoraExtra (``prefijo`` = 'horas_extra__' desde ReporteHoras)."""
    categoria, desde, hasta = filtros_horas(params)
    q = Q()
    if categoria:
        q &= Q(**{f'{prefijo}categoria_id': categoria})
    if desde:
        q &= Q(**{f'{prefijo}entrada__date__gte': desde})
    if hasta:
        q &= Q(**{f'{prefijo}entrada__date__lte': hasta})
    return q


def reportes_listado(params):
    """Reportes con total de horas y registros, filtrados por columna.

    Si hay filtro de categoría o fechas, los totales y los reportes mostrados
    consideran solo las horas extra que cumplen ese filtro.
    """
    q = _q_horas(params, 'horas_extra__')
    qs = (ReporteHoras.objects
          .select_related('colaborador', 'autorizado_por', 'solicitado_por')
          .annotate(total_horas=Sum('horas_extra__horas_total', filter=q),
                    num_registros=Count('horas_extra', filter=q)))
    if q:
        qs = qs.filter(num_registros__gt=0)
    return aplicar_filtros(qs, params, COLUMNAS_REPORTES)


COLUMNAS_HORAS = [
    {'key': 'fecha', 'label': 'Fecha', 'kind': 'fecha', 'ops': OP_FECHA, 'campo': 'entrada',
     'ann': 'ann_fecha_he', 'anotar': {'ann_fecha_he': fecha_texto('entrada')},
     'presencia': Q(entrada__isnull=False)},
    dict(key='colaborador', label='Colaborador', **persona('colaborador', 'ann_colab_he')),
    {'key': 'categoria', 'label': 'Categoría', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['categoria__nombre'], 'presencia': Q(categoria__isnull=False)},
    {'key': 'actividad', 'label': 'Actividad', 'kind': 'texto', 'ops': OP_TEXTO,
     'campos': ['justificacion'], 'presencia': no_vacio('justificacion')},
    {'key': 'total', 'label': 'Total horas', 'kind': 'numero', 'ops': OP_NUMERO,
     'campo': 'horas_total', 'presencia': Q(horas_total__isnull=False)},
]


def _horas_base():
    return HoraExtra.objects.select_related('colaborador', 'categoria', 'reporte')


def horas_listado(params, reporte_id=None):
    """Horas extra para la tabla: filtros simples (categoría, fechas) + filtros por columna."""
    qs = _horas_base()
    if reporte_id is not None:
        qs = qs.filter(reporte_id=reporte_id)
    qs = qs.filter(_q_horas(params))
    return aplicar_filtros(qs, params, COLUMNAS_HORAS).order_by('-entrada', '-pk')


def horas_para_exportar(params, reporte_id=None):
    """Horas extra a exportar a Excel: las mismas de la tabla, en orden cronológico."""
    return horas_listado(params, reporte_id).order_by('entrada', 'pk')


def total_horas(qs):
    """Suma de horas de un queryset de HoraExtra."""
    return qs.aggregate(t=Sum('horas_total'))['t'] or 0


def hora_por_id(pk):
    return _horas_base().filter(pk=pk).first()


def reportes_recientes():
    """Reportes para elegir al crear/editar una hora extra."""
    return ReporteHoras.objects.select_related('colaborador').order_by('-creado_en')


def categoria_por_id(pk):
    pk = _entero(pk)
    return CategoriaHoraExtra.objects.filter(pk=pk).first() if pk else None


def todas_las_categorias():
    return CategoriaHoraExtra.objects.all()


def reporte_con_totales(pk):
    return (ReporteHoras.objects
            .select_related('colaborador', 'autorizado_por', 'solicitado_por')
            .annotate(total_horas=Sum('horas_extra__horas_total'))
            .filter(pk=pk).first())


def horas_de_reporte(reporte):
    return (HoraExtra.objects.filter(reporte=reporte)
            .select_related('colaborador', 'categoria'))


def usuarios_activos():
    return (get_user_model().objects.filter(is_active=True)
            .order_by('first_name', 'last_name', 'username'))


def categorias_activas():
    return CategoriaHoraExtra.objects.filter(activa=True)
