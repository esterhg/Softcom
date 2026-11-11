"""Pruebas sin BD (SimpleTestCase): permisos y cálculo de horas."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from rrhh import permissions
from rrhh.services import horas as svc


def _user(superuser=False, en_grupo=False, autenticado=True):
    u = MagicMock()
    u.is_authenticated = autenticado
    u.is_superuser = superuser
    u.groups.filter.return_value.exists.return_value = en_grupo
    return u


class PermisosTests(SimpleTestCase):
    def test_miembro_del_grupo_entra(self):
        self.assertTrue(permissions.es_instalaciones(_user(en_grupo=True)))

    def test_superusuario_sin_grupo_no_entra(self):
        self.assertFalse(permissions.es_instalaciones(_user(superuser=True, en_grupo=False)))

    def test_anonimo_no_entra(self):
        self.assertFalse(permissions.es_instalaciones(_user(autenticado=False, en_grupo=True)))

    def test_decorador_403_sin_grupo(self):
        vista = permissions.instalaciones_required(lambda r: HttpResponse('ok'))
        req = RequestFactory().get('/')
        req.user = _user(superuser=True, en_grupo=False)
        self.assertEqual(vista(req).status_code, 403)

    def test_decorador_200_con_grupo(self):
        vista = permissions.instalaciones_required(lambda r: HttpResponse('ok'))
        req = RequestFactory().get('/')
        req.user = _user(en_grupo=True)
        self.assertEqual(vista(req).status_code, 200)


class CalcularHorasTests(SimpleTestCase):
    def test_horas_simples(self):
        self.assertEqual(
            svc.calcular_horas(datetime(2026, 1, 1, 18, 0), datetime(2026, 1, 1, 21, 30)),
            Decimal('3.50'))

    def test_cruza_medianoche(self):
        self.assertEqual(
            svc.calcular_horas(datetime(2026, 1, 1, 22, 0), datetime(2026, 1, 2, 2, 0)),
            Decimal('4.00'))

    def test_salida_anterior_es_error(self):
        with self.assertRaises(ValidationError):
            svc.calcular_horas(datetime(2026, 1, 1, 20, 0), datetime(2026, 1, 1, 19, 0))

    def test_justificacion_vacia_es_error(self):
        with self.assertRaises(ValidationError):
            svc.registrar_hora_extra(
                reporte=None, colaborador=None, categoria=None,
                entrada=datetime(2026, 1, 1, 18), salida=datetime(2026, 1, 1, 20),
                cena=False, justificacion='   ', creado_por=None)
