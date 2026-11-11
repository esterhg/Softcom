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


class ExcelHorasExtraTests(SimpleTestCase):
    """Formato del Excel (sin BD): estructura de la plantilla de Instalaciones."""

    @staticmethod
    def _hora(dia, h1, h2, nombre='Ana Pérez', cena=False):
        from types import SimpleNamespace
        from django.utils import timezone
        tz = timezone.get_current_timezone()
        persona = SimpleNamespace(get_full_name=lambda: nombre, username='ana')
        return SimpleNamespace(
            entrada=datetime(2026, 10, dia, h1, 0, tzinfo=tz),
            salida=datetime(2026, 10, dia, h2, 0, tzinfo=tz),
            colaborador=persona, justificacion='Atención de averías', cena=cena)

    def test_estructura_de_la_plantilla(self):
        from rrhh.services import exportes
        horas = [self._hora(17, 10, 15), self._hora(21, 19, 22, cena=True)]
        ws = exportes.libro_excel_horas(
            horas, categoria='Bienes Afectos', periodo='DEL 17/10/2026 AL 21/10/2026').active
        self.assertEqual(ws['B9'].value, 'FECHA')
        self.assertEqual(ws['N9'].value, 'HORAS F:2.00')
        self.assertEqual(ws['E4'].value, 'CATEGORÍA: Bienes Afectos')
        self.assertEqual(ws['E7'].value, 'DEL 17/10/2026 AL 21/10/2026')
        self.assertEqual(ws['E10'].value, 'Ana Pérez')
        self.assertIsNone(ws['J10'].value)
        self.assertEqual(ws['J11'].value, 1)  # cena
        self.assertEqual(ws['I12'].value, '=SUBTOTAL(9,I10:I11)')
        self.assertTrue(ws['I10'].value.startswith('=MOD(H10-G10'))

    def test_sin_datos_deja_una_fila_vacia(self):
        from rrhh.services import exportes
        ws = exportes.libro_excel_horas([]).active
        self.assertEqual(ws['E4'].value, 'TODAS LAS CATEGORÍAS')
        self.assertEqual(ws['I11'].value, '=SUBTOTAL(9,I10:I10)')


class JornadaYDiaTests(SimpleTestCase):
    """Misma regla que la columna JORNADA del Excel de Instalaciones."""

    @staticmethod
    def _dt(dia, h, m=0):
        from django.utils import timezone
        return datetime(2026, 10, dia, h, m, tzinfo=timezone.get_current_timezone())

    def test_diurno(self):
        self.assertEqual(svc.jornada(self._dt(17, 10), self._dt(17, 15, 1)), 'DIURNO')

    def test_nocturno(self):
        self.assertEqual(svc.jornada(self._dt(21, 19), self._dt(21, 22, 2)), 'NOCTURNO')

    def test_nocturno_cruza_medianoche(self):
        self.assertEqual(svc.jornada(self._dt(21, 22), self._dt(22, 2)), 'NOCTURNO')

    def test_mixto(self):
        self.assertEqual(svc.jornada(self._dt(5, 16, 30), self._dt(5, 20, 17)), 'MIXTO')

    def test_dia_semana(self):
        # 17/10/2026 es sábado; 18/10/2026 domingo.
        self.assertEqual(svc.dia_semana(self._dt(17, 10)), 'Sábado')
        self.assertEqual(svc.dia_semana(self._dt(18, 10)), 'Domingo')


class EditarEliminarTests(SimpleTestCase):
    def test_actualizar_recalcula_horas(self):
        hora = MagicMock()
        svc.actualizar_hora_extra(
            hora, reporte='R', colaborador='C', categoria=None,
            entrada=datetime(2026, 1, 1, 18), salida=datetime(2026, 1, 1, 21, 15),
            cena=True, justificacion='  Revisión  ')
        self.assertEqual(hora.horas_total, Decimal('3.25'))
        self.assertEqual(hora.justificacion, 'Revisión')
        hora.save.assert_called_once()

    def test_actualizar_sin_justificacion_no_guarda(self):
        hora = MagicMock()
        with self.assertRaises(ValidationError):
            svc.actualizar_hora_extra(
                hora, reporte='R', colaborador='C', categoria=None,
                entrada=datetime(2026, 1, 1, 18), salida=datetime(2026, 1, 1, 19),
                cena=False, justificacion='')
        hora.save.assert_not_called()

    def test_eliminar(self):
        hora = MagicMock()
        svc.eliminar_hora_extra(hora)
        hora.delete.assert_called_once()


class PlantillasTests(SimpleTestCase):
    """Las plantillas compilan (sin BD) y extienden el admin."""

    def test_compilan(self):
        from django.template.loader import get_template
        for nombre in ('rrhh/reportes.html', 'rrhh/detalle_reporte.html',
                       'rrhh/includes/tabla_horas.html', 'rrhh/includes/modal_hora.html',
                       'rrhh/includes/modal_reporte.html', 'rrhh/includes/modal_categoria.html',
                       'rrhh/includes/js_horas.html', 'rrhh/includes/menu_admin.html'):
            get_template(nombre)

    def test_base_extiende_admin(self):
        from django.template.loader import get_template
        origen = get_template('rrhh/base_rrhh.html').template.source
        self.assertIn('{% extends "admin/base_site.html" %}', origen)


class ExcelPorCategoriaTests(SimpleTestCase):
    @staticmethod
    def _hora(dia, categoria):
        from types import SimpleNamespace
        from django.utils import timezone
        tz = timezone.get_current_timezone()
        cat = SimpleNamespace(nombre=categoria) if categoria else None
        return SimpleNamespace(
            entrada=datetime(2026, 10, dia, 18, 0, tzinfo=tz),
            salida=datetime(2026, 10, dia, 20, 0, tzinfo=tz),
            colaborador=SimpleNamespace(get_full_name=lambda: 'Ana', username='ana'),
            categoria=cat, justificacion='Actividad', cena=False)

    def test_una_hoja_por_categoria(self):
        from rrhh.services import exportes
        horas = [self._hora(17, 'Instalaciones'), self._hora(18, 'Bienes Afectos'),
                 self._hora(19, 'Instalaciones'), self._hora(20, None)]
        wb = exportes.libro_excel_por_categorias(horas)
        self.assertEqual(wb.sheetnames, ['Bienes Afectos', 'Instalaciones', 'Sin categoría'])
        ws = wb['Instalaciones']
        self.assertEqual(ws['E4'].value, 'CATEGORÍA: Instalaciones')
        self.assertEqual(ws['I12'].value, '=SUBTOTAL(9,I10:I11)')  # 2 filas propias
        self.assertEqual(ws['E7'].value, 'DEL 17/10/2026 AL 19/10/2026')

    def test_sin_datos_una_hoja(self):
        from rrhh.services import exportes
        self.assertEqual(exportes.libro_excel_por_categorias([]).sheetnames, ['Reporte HE'])

    def test_nombre_hoja_valido_y_unico(self):
        from rrhh.services import exportes
        usados = set()
        self.assertEqual(exportes.nombre_hoja('A/B: [x]', usados), 'A B   x')
        largo = 'X' * 40
        self.assertEqual(len(exportes.nombre_hoja(largo, usados)), 31)
        self.assertTrue(exportes.nombre_hoja(largo, usados).endswith('(2)'))

    def test_plantilla_menu_exportar_compila(self):
        from django.template.loader import get_template
        get_template('rrhh/includes/menu_exportar.html')


class MenuExportarTests(SimpleTestCase):
    def _render(self, **ctx):
        from types import SimpleNamespace
        from django.template.loader import render_to_string
        base = {'url_export': '/rrhh/reportes/excel/', 'qs_export': '', 'querystring': '',
                'categorias': [SimpleNamespace(pk=3, nombre='Bienes Afectos', activa=True)]}
        base.update(ctx)
        return render_to_string('rrhh/includes/menu_exportar.html', base)

    def test_no_usa_dropdown_de_bootstrap(self):
        # El admin no carga Popper.js: data-toggle="dropdown" no abre el menú.
        self.assertNotIn('data-toggle="dropdown"', self._render())

    def test_enlaces_por_categoria_sin_filtros(self):
        html = self._render()
        self.assertIn('href="/rrhh/reportes/excel/"', html)
        self.assertIn('href="/rrhh/reportes/excel/?agrupar=categoria"', html)
        self.assertIn('href="/rrhh/reportes/excel/?categoria=3"', html)
        self.assertNotIn('Con los filtros actuales', html)

    def test_enlaces_conservan_filtros(self):
        html = self._render(qs_export='desde=2026-10-01', querystring='desde=2026-10-01&categoria=3')
        self.assertIn('?desde=2026-10-01&amp;categoria=3', html)
        self.assertIn('?desde=2026-10-01&agrupar=categoria', html)
        self.assertIn('Con los filtros actuales', html)

    def test_pantalla_principal_sin_crear_horas(self):
        from django.template.loader import get_template
        origen = get_template('rrhh/reportes.html').template.source
        self.assertNotIn('js-crear-hora', origen)
        self.assertNotIn('tabla_horas.html', origen)
        self.assertIn('modalReporte', origen)
