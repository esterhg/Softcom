"""
Pruebas del motor genérico de filtros por columna (core/filtros_columna.py).

No usan base de datos: se verifica qué filtros/anotaciones se aplican sobre un
QuerySet simulado que registra las llamadas.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core import filtros_columna as fc


class QSFalso:
    """Imita filter/exclude/annotate y registra cada llamada."""

    def __init__(self):
        self.llamadas = []

    def _registrar(self, metodo, args, kwargs):
        self.llamadas.append((metodo, args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        return self._registrar('filter', args, kwargs)

    def exclude(self, *args, **kwargs):
        return self._registrar('exclude', args, kwargs)

    def annotate(self, *args, **kwargs):
        return self._registrar('annotate', args, kwargs)

    def de(self, metodo):
        return [(a, k) for m, a, k in self.llamadas if m == metodo]


COL_TEXTO = {'key': 'producto', 'label': 'Producto', 'kind': 'texto', 'ops': fc.OP_TEXTO,
             'campos': ['material__nombre', 'material__sku'], 'presencia': Q(material__isnull=False)}
COL_ELECCION = {'key': 'estado', 'label': 'Estado', 'kind': 'eleccion', 'ops': fc.OP_BASICO,
                'campo': 'estado', 'opciones': [('PENDIENTE', 'Pendiente'), ('APROBADO', 'Aprobado / Liquidado'),
                                                ('RECHAZADO', 'Rechazado')]}
COL_NUMERO = {'key': 'cantidad', 'label': 'Cantidad', 'kind': 'numero', 'ops': fc.OP_NUMERO, 'campo': 'cantidad'}
COL_FECHA = {'key': 'fecha', 'label': 'Fecha', 'kind': 'fecha', 'ops': fc.OP_FECHA,
             'campo': 'fecha_movimiento', 'ann': 'ann_fecha',
             'anotar': {'ann_fecha': fc.fecha_texto('fecha_movimiento')}}
COLS = [COL_TEXTO, COL_ELECCION, COL_NUMERO, COL_FECHA]


def aplicar(params):
    qs = QSFalso()
    fc.aplicar_filtros(qs, params, COLS)
    return qs


class ParseFechaFlexibleTests(SimpleTestCase):
    def test_formatos_validos(self):
        self.assertEqual(fc.parse_fecha_flexible('2026-11-09'), date(2026, 11, 9))
        self.assertEqual(fc.parse_fecha_flexible(' 09/11/2026 '), date(2026, 11, 9))

    def test_invalidos(self):
        self.assertIsNone(fc.parse_fecha_flexible('9-11-26'))
        self.assertIsNone(fc.parse_fecha_flexible(''))
        self.assertIsNone(fc.parse_fecha_flexible(None))


class AplicarFiltrosTextoTests(SimpleTestCase):
    def test_sin_parametros_no_filtra(self):
        self.assertEqual(aplicar({}).llamadas, [])

    def test_operador_desconocido_o_sin_valor_se_ignora(self):
        self.assertEqual(aplicar({'op_producto': 'hackear', 'val_producto': 'x'}).llamadas, [])
        self.assertEqual(aplicar({'op_producto': 'contiene', 'val_producto': '  '}).llamadas, [])

    def test_contiene_combina_campos_con_or(self):
        qs = aplicar({'op_producto': 'contiene', 'val_producto': ' foco '})
        esperado = Q(material__nombre__icontains='foco') | Q(material__sku__icontains='foco')
        self.assertEqual(qs.de('filter'), [((esperado,), {})])

    def test_no_contiene_usa_exclude(self):
        qs = aplicar({'op_producto': 'no_contiene', 'val_producto': 'foco'})
        esperado = Q(material__nombre__icontains='foco') | Q(material__sku__icontains='foco')
        self.assertEqual(qs.de('exclude'), [((esperado,), {})])

    def test_igual_usa_iexact(self):
        qs = aplicar({'op_producto': 'igual', 'val_producto': 'Foco'})
        esperado = Q(material__nombre__iexact='Foco') | Q(material__sku__iexact='Foco')
        self.assertEqual(qs.de('filter'), [((esperado,), {})])

    def test_con_y_sin_datos_no_requieren_valor(self):
        self.assertEqual(aplicar({'op_producto': 'tiene'}).de('filter'),
                         [((Q(material__isnull=False),), {})])
        self.assertEqual(aplicar({'op_producto': 'vacio'}).de('exclude'),
                         [((Q(material__isnull=False),), {})])


class AplicarFiltrosEleccionTests(SimpleTestCase):
    def test_igual_por_codigo_o_etiqueta(self):
        self.assertEqual(aplicar({'op_estado': 'igual', 'val_estado': 'pendiente'}).de('filter'),
                         [((), {'estado__in': ['PENDIENTE']})])
        self.assertEqual(aplicar({'op_estado': 'igual', 'val_estado': 'Aprobado / Liquidado'}).de('filter'),
                         [((), {'estado__in': ['APROBADO']})])

    def test_contiene_y_no_contiene(self):
        self.assertEqual(aplicar({'op_estado': 'contiene', 'val_estado': 'ado'}).de('filter'),
                         [((), {'estado__in': ['APROBADO', 'RECHAZADO']})])
        self.assertEqual(aplicar({'op_estado': 'no_contiene', 'val_estado': 'rech'}).de('exclude'),
                         [((), {'estado__in': ['RECHAZADO']})])


class AplicarFiltrosNumeroTests(SimpleTestCase):
    def test_operadores_y_coma_decimal(self):
        self.assertEqual(aplicar({'op_cantidad': 'mayor', 'val_cantidad': '2,5'}).de('filter'),
                         [((), {'cantidad__gt': Decimal('2.5')})])
        self.assertEqual(aplicar({'op_cantidad': 'menor', 'val_cantidad': '10'}).de('filter'),
                         [((), {'cantidad__lt': Decimal('10')})])
        self.assertEqual(aplicar({'op_cantidad': 'igual', 'val_cantidad': '3'}).de('filter'),
                         [((), {'cantidad__exact': Decimal('3')})])

    def test_numero_invalido_se_ignora(self):
        self.assertEqual(aplicar({'op_cantidad': 'igual', 'val_cantidad': 'abc'}).de('filter'), [])


class AplicarFiltrosFechaTests(SimpleTestCase):
    def test_igual_desde_hasta(self):
        self.assertEqual(aplicar({'op_fecha': 'igual', 'val_fecha': '09/11/2026'}).de('filter'),
                         [((), {'fecha_movimiento__date': date(2026, 11, 9)})])
        self.assertEqual(aplicar({'op_fecha': 'mayor', 'val_fecha': '2026-11-01'}).de('filter'),
                         [((), {'fecha_movimiento__date__gte': date(2026, 11, 1)})])
        self.assertEqual(aplicar({'op_fecha': 'menor', 'val_fecha': '2026-11-30'}).de('filter'),
                         [((), {'fecha_movimiento__date__lte': date(2026, 11, 30)})])

    def test_contiene_usa_anotacion_de_texto(self):
        qs = aplicar({'op_fecha': 'contiene', 'val_fecha': '2026-11'})
        self.assertEqual([list(k) for _, k in qs.de('annotate')], [['ann_fecha']])
        self.assertEqual(qs.de('filter'), [((), {'ann_fecha__icontains': '2026-11'})])

    def test_fecha_invalida_no_filtra(self):
        self.assertEqual(aplicar({'op_fecha': 'igual', 'val_fecha': 'ayer'}).de('filter'), [])


class AplicarFiltrosCombinadosTests(SimpleTestCase):
    def test_querydict_y_varias_columnas(self):
        params = QueryDict('op_producto=contiene&val_producto=foco&op_estado=igual&val_estado=Pendiente')
        qs = aplicar(params)
        self.assertEqual(len(qs.de('filter')), 2)


class ColumnasConEstadoTests(SimpleTestCase):
    def test_refleja_operador_valor_y_placeholder(self):
        estado = fc.columnas_con_estado(
            {'op_producto': 'contiene', 'val_producto': ' foco ', 'op_estado': 'invalido'}, COLS)
        por_key = {c['key']: c for c in estado}
        self.assertEqual(por_key['producto']['op'], 'contiene')
        self.assertEqual(por_key['producto']['val'], 'foco')
        self.assertEqual(por_key['estado']['op'], '')  # operador no permitido se descarta
        self.assertEqual(por_key['cantidad']['placeholder'], 'Número')
        self.assertEqual(por_key['fecha']['placeholder'], fc.PLACEHOLDERS['fecha'])
        self.assertEqual([c['key'] for c in estado], ['producto', 'estado', 'cantidad', 'fecha'])


class FabricasTests(SimpleTestCase):
    def test_persona_y_no_vacio(self):
        col = fc.persona('usuario', 'ann_usuario')
        self.assertEqual(col['campos'], ['usuario__username', 'usuario__first_name',
                                         'usuario__last_name', 'ann_usuario'])
        self.assertEqual(col['presencia'], Q(usuario__isnull=False))
        self.assertIn('ann_usuario', col['anotar'])
        self.assertEqual(fc.no_vacio('comentarios'),
                         Q(comentarios__isnull=False) & ~Q(comentarios=''))


class ComponenteFiltroThTests(SimpleTestCase):
    """El componente compartido renderiza los campos que viajan por GET."""

    def test_render_componente_core(self):
        c = fc.columnas_con_estado({'op_producto': 'contiene', 'val_producto': 'foco'}, [COL_TEXTO])[0]
        html = render_to_string('core/includes/filtro_th.html', {'c': c})
        self.assertIn('name="op_producto" value="contiene"', html)
        self.assertIn('name="val_producto" value="foco"', html)
        self.assertIn('fc-activo', html)
        self.assertIn('Filtrar por', html)

    def test_alias_de_compatibilidad_en_inventarios(self):
        c = fc.columnas_con_estado({}, [COL_TEXTO])[0]
        html = render_to_string('inventarios/includes/filtro_th.html', {'c': c})
        self.assertIn('name="op_producto"', html)
        self.assertNotIn('fc-activo', html)

    def test_assets_incluyen_css_y_js(self):
        html = render_to_string('core/includes/filtros_columna_assets.html')
        self.assertIn('.fc-pop', html)
        self.assertIn("getElementById('filtros-form')", html)
