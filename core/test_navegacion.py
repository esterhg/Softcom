"""Pruebas del estándar de navegación (core/navegacion.py). Sin base de datos."""
from django.http import QueryDict
from django.test import RequestFactory, SimpleTestCase

from core.navegacion import querystring_sin, url_retorno


class QuerystringSinTests(SimpleTestCase):
    def test_quita_claves_y_conserva_el_resto(self):
        params = QueryDict('tipo=SALIDA&page=3&op_producto=contiene&val_producto=foco')
        self.assertEqual(querystring_sin(params, 'page'),
                         'tipo=SALIDA&op_producto=contiene&val_producto=foco')

    def test_sin_claves_equivale_a_urlencode(self):
        params = QueryDict('departamento=none&desde=2026-11-01')
        self.assertEqual(querystring_sin(params), params.urlencode())

    def test_no_modifica_el_original(self):
        params = QueryDict('page=2&q=x')
        querystring_sin(params, 'page')
        self.assertEqual(params.get('page'), '2')


class UrlRetornoTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_next_interno_por_get(self):
        req = self.rf.get('/x/', {'next': '/inventarios/reportes/movimientos/?page=2'})
        self.assertEqual(url_retorno(req, '/inventarios/'), '/inventarios/reportes/movimientos/?page=2')

    def test_next_por_post(self):
        req = self.rf.post('/x/', {'next': '/inventarios/'})
        self.assertEqual(url_retorno(req, '/otro/'), '/inventarios/')

    def test_next_externo_se_rechaza(self):
        for destino in ('https://evil.example.com/', '//evil.example.com/x', 'javascript:alert(1)'):
            req = self.rf.get('/x/', {'next': destino})
            self.assertEqual(url_retorno(req, '/inventarios/'), '/inventarios/', destino)

    def test_sin_next_usa_default(self):
        self.assertEqual(url_retorno(self.rf.get('/x/'), '/inventarios/'), '/inventarios/')
