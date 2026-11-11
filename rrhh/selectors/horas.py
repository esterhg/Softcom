"""Consultas de lectura de reportes de horas (no escribe en BD)."""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum

from core.filtros_columna import (
    OP_NUMERO, OP_TEXTO, aplicar_filtros, fecha_texto, persona,
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


def reportes_listado(params):
    """Reportes con total de horas y cantidad de registros, filtrados por columna."""
    qs = (ReporteHoras.objects
          .select_related('colaborador', 'autorizado_por', 'solicitado_por')
          .annotate(total_horas=Sum('horas_extra__horas_total'),
                    num_registros=Count('horas_extra')))
    return aplicar_filtros(qs, params, COLUMNAS_REPORTES)


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
