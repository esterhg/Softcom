"""
Pruebas del paso 1 de la arquitectura por capas: reportes de Movimientos y de
Pases pendientes de justificar (permissions, selectors, services, vistas, rutas).

Todas son ``SimpleTestCase``: NO usan base de datos, así que son seguras en
cualquier entorno (incluido el local, que apunta por túnel al servidor).
Las pruebas con base de datos están en ``test_reportes_bd.py``.
"""
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.http import QueryDict
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse
from django.utils import timezone

from core.test_filtros_columna import QSFalso
from inventarios import permissions, reportes
from inventarios.selectors import reportes as sel
from inventarios.services import reportes as svc


# ---------------------------------------------------------------------------
# Objetos de prueba
# ---------------------------------------------------------------------------

def usuario_falso(superuser=False, en_grupo=False, autenticado=True):
    grupos = mock.Mock()
    grupos.filter.return_value.exists.return_value = en_grupo
    return SimpleNamespace(is_authenticated=autenticado, is_superuser=superuser, groups=grupos)


def solicitante(nombre_depto=None):
    perfil = SimpleNamespace(departamento=SimpleNamespace(nombre=nombre_depto) if nombre_depto else None)
    return SimpleNamespace(perfil=perfil)


class IterQS(list):
    """Lista con .iterator() como un QuerySet (para los servicios de Excel)."""

    def iterator(self, chunk_size=None):
        return iter(self)


def leer_xlsx(response):
    import openpyxl
    return openpyxl.load_workbook(BytesIO(response.content)).active


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

class PermisosTests(SimpleTestCase):
    def test_superusuario_y_miembro_del_grupo(self):
        self.assertTrue(permissions.es_supervisor_almacen(usuario_falso(superuser=True)))
        u = usuario_falso(en_grupo=True)
        self.assertTrue(permissions.es_supervisor_almacen(u))
        u.groups.filter.assert_called_with(name='Supervisor de Almacen')

    def test_sin_permiso_o_anonimo(self):
        self.assertFalse(permissions.es_supervisor_almacen(usuario_falso()))
        self.assertFalse(permissions.es_supervisor_almacen(AnonymousUser()))

    def test_nombre_del_grupo_coincide_con_la_migracion(self):
        from importlib import import_module
        migracion = import_module('inventarios.migrations.0047_crear_grupo_supervisor_almacen')
        self.assertEqual(permissions.GRUPO_SUPERVISOR_ALMACEN, migracion.NOMBRE_GRUPO)


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

class PasesPendientesSelectorTests(SimpleTestCase):
    def test_regla_de_negocio_en_la_consulta_base(self):
        sql = str(sel.pases_pendientes_base().query)
        self.assertIn('NO_PROGRAMADA', sql)       # excluye OTNP
        self.assertIn('"ticket_id" IS NULL', sql)  # sin ticket
        self.assertIn('BORRADOR', sql)
        self.assertIn('RECHAZADO', sql)
        self.assertIn('COUNT(', sql)               # num_items
        self.assertIn('ORDER BY', sql)

    def _con_base_falsa(self, params):
        qs = QSFalso()
        with mock.patch.object(sel, 'pases_pendientes_base', return_value=qs):
            sel.pases_pendientes(params)
        return qs

    def test_filtro_departamento(self):
        qs = self._con_base_falsa({'departamento': '7'})
        self.assertEqual(qs.de('filter'), [((), {'usuario__perfil__departamento_id': 7})])

    def test_filtro_sin_departamento(self):
        qs = self._con_base_falsa({'departamento': 'none'})
        esperado = Q(usuario__perfil__isnull=True) | Q(usuario__perfil__departamento__isnull=True)
        self.assertEqual(qs.de('filter'), [((esperado,), {})])

    def test_departamento_invalido_se_ignora(self):
        self.assertEqual(self._con_base_falsa({'departamento': 'abc'}).llamadas, [])

    def test_fechas_y_filtro_por_columna(self):
        qs = self._con_base_falsa(QueryDict(
            'desde=2026-11-01&hasta=2026-11-09&op_comentarios=vacio'))
        filtros = qs.de('filter')
        self.assertIn('fecha_solicitud__gte', filtros[0][1])
        self.assertIn('fecha_solicitud__lte', filtros[1][1])
        self.assertEqual(filtros[1][1]['fecha_solicitud__lte'].hour, 23)  # fin del día
        self.assertEqual(qs.de('exclude'),
                         [((Q(comentarios_solicitud__isnull=False) & ~Q(comentarios_solicitud=''),), {})])

    def test_departamento_de(self):
        self.assertEqual(sel.departamento_de(SimpleNamespace(usuario=solicitante('Almacenes'))), 'Almacenes')
        self.assertEqual(sel.departamento_de(SimpleNamespace(usuario=solicitante())), 'Sin departamento')
        self.assertEqual(sel.departamento_de(SimpleNamespace(usuario=SimpleNamespace())), 'Sin departamento')


class MovimientosSelectorTests(SimpleTestCase):
    def _con_manager_falso(self, funcion, params):
        qs = QSFalso()
        with mock.patch.object(sel.MovimientoInventario, 'objects') as manager:
            manager.select_related.return_value.order_by.return_value = qs
            funcion(params)
        return qs, manager

    def test_tabla_filtros_de_pantalla(self):
        qs, manager = self._con_manager_falso(sel.movimientos_tabla, QueryDict(
            'tipo=SALIDA&estado=APROBADO&q=foco&desde=2026-11-01'))
        manager.select_related.return_value.order_by.assert_called_with('-fecha_movimiento')
        filtros = qs.de('filter')
        self.assertEqual(filtros[0], ((), {'tipo': 'SALIDA'}))
        self.assertEqual(filtros[1], ((), {'estado': 'APROBADO'}))
        self.assertIn('fecha_movimiento__gte', filtros[2][1])
        busqueda = filtros[3][0][0]  # Q con OR de los campos de búsqueda libre
        self.assertIn(('material__nombre__icontains', 'foco'), busqueda.children)
        self.assertIn(('orden_trabajo__codigo_de_orden__icontains', 'foco'), busqueda.children)

    def test_tabla_filtro_por_columna_sin_aprobador(self):
        qs, _ = self._con_manager_falso(sel.movimientos_tabla, {'op_aprobo': 'vacio'})
        self.assertEqual(qs.de('exclude'), [((Q(aprobado_por__isnull=False),), {})])

    def test_tabla_sin_parametros_no_filtra(self):
        qs, _ = self._con_manager_falso(sel.movimientos_tabla, {})
        self.assertEqual(qs.llamadas, [])

    def test_export_filtros_y_columnas(self):
        qs, _ = self._con_manager_falso(sel.movimientos_export, QueryDict(
            'ubicacion=3&categoria=5&op_producto=contiene&val_producto=foco&q=no_aplica'))
        filtros = qs.de('filter')
        self.assertEqual(filtros[0], ((Q(ubicacion_origen_id='3') | Q(ubicacion_destino_id='3'),), {}))
        self.assertEqual(filtros[1], ((), {'material__categoria_id': '5'}))
        self.assertEqual(filtros[2], ((Q(material__nombre__icontains='foco') | Q(material__sku__icontains='foco'),), {}))
        self.assertEqual(len(filtros), 3)  # la búsqueda libre 'q' no aplica al export (comportamiento previo)

    def test_columnas_declaradas(self):
        self.assertEqual([c['key'] for c in sel.COLUMNAS_MOVIMIENTOS],
                         ['fecha', 'tipo', 'estado', 'producto', 'cantidad', 'pase', 'ot',
                          'registro', 'aprobo', 'entrego', 'origen', 'destino'])
        self.assertEqual([c['key'] for c in sel.COLUMNAS_PASES],
                         ['pase', 'fecha', 'departamento', 'solicitante', 'estado', 'ot',
                          'articulos', 'comentarios'])
        estados_pases = dict(next(c for c in sel.COLUMNAS_PASES if c['key'] == 'estado')['opciones'])
        self.assertNotIn('BORRADOR', estados_pases)
        self.assertNotIn('RECHAZADO', estados_pases)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def pase_falso(id_, depto, items, dias=0, ot=None, comentarios='Uso en obra'):
    return SimpleNamespace(
        id=id_, usuario=solicitante(depto), num_items=items, orden_trabajo=ot,
        fecha_solicitud=timezone.now() - timedelta(days=dias),
        solicitante_nombre='Ana Pérez', get_estado_display=lambda: 'Pendiente',
        ubicacion_origen=SimpleNamespace(nombre='Bodega 1'), comentarios_solicitud=comentarios,
    )


class ResumenPorDepartamentoTests(SimpleTestCase):
    def test_agrupa_ordena_y_marca_cada_pase(self):
        pases = [pase_falso(1, 'Almacenes', 2), pase_falso(2, 'Mantenimiento', 1),
                 pase_falso(3, 'Almacenes', 4), pase_falso(4, None, 3)]
        resumen = svc.resumen_por_departamento(pases)
        self.assertEqual(resumen, [
            {'departamento': 'Almacenes', 'total': 2, 'items': 6},
            {'departamento': 'Mantenimiento', 'total': 1, 'items': 1},
            {'departamento': 'Sin departamento', 'total': 1, 'items': 3},
        ])
        self.assertEqual([p.departamento_nombre for p in pases],
                         ['Almacenes', 'Mantenimiento', 'Almacenes', 'Sin departamento'])

    def test_lista_vacia(self):
        self.assertEqual(svc.resumen_por_departamento([]), [])


class ExcelPasesTests(SimpleTestCase):
    def test_fila_con_y_sin_ot(self):
        ot = SimpleNamespace(id=9, codigo_de_orden=None, get_tipo_display=lambda: 'Preventiva')
        pase = pase_falso(5, 'Almacenes', 2, dias=3, ot=ot)
        ahora = timezone.now()  # después de crear el pase: exactamente >= 3 días
        fila = svc.fila_pase(pase, ahora)
        self.assertEqual(len(fila), len(svc.HEADERS_PASES))
        self.assertEqual(fila[0], 5)
        self.assertEqual(fila[2], 'Almacenes')
        self.assertEqual(fila[5:7], ['OT-9', 'Preventiva'])
        self.assertEqual(fila[9], 3)  # días sin justificar
        sin_ot = svc.fila_pase(pase_falso(6, None, 1, comentarios=None), ahora)
        self.assertEqual(sin_ot[5:7], ['', ''])
        self.assertEqual(sin_ot[10], '')

    def test_libro_y_respuesta(self):
        from core.excel import XLSX_CONTENT_TYPE, respuesta_xlsx
        ahora = timezone.now()
        wb = svc.libro_excel_pases(IterQS([pase_falso(1, 'Almacenes', 2), pase_falso(2, None, 1)]), ahora)
        resp = respuesta_xlsx(wb, 'pases_pendientes_justificar', ahora)
        self.assertEqual(resp['Content-Type'], XLSX_CONTENT_TYPE)
        self.assertRegex(resp['Content-Disposition'],
                         r'attachment; filename="pases_pendientes_justificar_\d{8}_\d{4}\.xlsx"')
        ws = leer_xlsx(resp)
        self.assertEqual(ws.title, 'Pases sin justificar')
        self.assertEqual([c.value for c in ws[1]], svc.HEADERS_PASES)
        self.assertEqual(ws.max_row, 3)
        self.assertEqual(ws.freeze_panes, 'A2')


def movimiento_falso(id_, aprobado=True):
    user = SimpleNamespace(get_full_name=lambda: 'Ana Pérez', username='aperez')
    return SimpleNamespace(
        id=id_, fecha_movimiento=timezone.now(), tipo='SALIDA', get_estado_display=lambda: 'Pendiente',
        material=SimpleNamespace(sku='SKU1', nombre='Foco LED', categoria=SimpleNamespace(nombre='Eléctrico'),
                                 unidad_medida=SimpleNamespace(abreviatura='u')),
        lote=None, cantidad=2, cantidad_solicitada=3,
        ubicacion_origen=SimpleNamespace(nombre='Bodega 1'), ubicacion_destino=None, ubicacion_especifica='',
        orden_trabajo=SimpleNamespace(codigo_de_orden='OT-000000001'),
        solicitud_id=10, ingreso_id=None, devolucion_id=None,
        usuario=user, aprobado_por=user if aprobado else None,
        fecha_aprobacion=timezone.now() if aprobado else None,
        es_inconsistente=False, comentarios=None,
    )


class ExcelMovimientosTests(SimpleTestCase):
    def test_fila(self):
        tipos = dict(sel.MovimientoInventario.TIPO_MOVIMIENTO)
        fila = svc.fila_movimiento(movimiento_falso(1), {1: ['Bomba (B-01)', 'Motor (7)']}, tipos)
        self.assertEqual(len(fila), len(svc.HEADERS_MOVIMIENTOS))
        self.assertEqual(fila[2], tipos['SALIDA'])
        self.assertEqual(fila[9:11], [2.0, 3.0])
        self.assertEqual(fila[15], 'Bomba (B-01), Motor (7)')
        self.assertEqual(fila[16], '10')
        self.assertEqual(fila[19:21], ['Ana Pérez', 'Ana Pérez'])
        self.assertEqual(fila[22], 'No')
        sin_aprobar = svc.fila_movimiento(movimiento_falso(2, aprobado=False), {}, tipos)
        self.assertEqual(sin_aprobar[15], '')
        self.assertEqual(sin_aprobar[20:22], ['', ''])

    def test_libro(self):
        wb = svc.libro_excel_movimientos(IterQS([movimiento_falso(1), movimiento_falso(2)]), {})
        ws = wb.active
        self.assertEqual(ws.title, 'Movimientos')
        self.assertEqual([c.value for c in ws[1]], svc.HEADERS_MOVIMIENTOS)
        self.assertEqual(ws.max_row, 3)


# ---------------------------------------------------------------------------
# Vistas (sin BD: selectors y render simulados)
# ---------------------------------------------------------------------------

class VistasReportesTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _get(self, url, user):
        req = self.rf.get(url)
        req.user = user
        return req

    def test_anonimo_redirige_al_login(self):
        for vista in (reportes.tabla_movimientos_view, reportes.reporte_pases_pendientes_view,
                      reportes.export_movimientos_excel, reportes.export_pases_pendientes_excel):
            resp = vista(self._get('/inventarios/reportes/movimientos/', AnonymousUser()))
            self.assertEqual(resp.status_code, 302, vista.__name__)
            self.assertIn('next=', resp['Location'])

    def test_sin_permiso_403(self):
        for vista in (reportes.tabla_movimientos_view, reportes.reporte_pases_pendientes_view,
                      reportes.export_movimientos_excel, reportes.export_pases_pendientes_excel):
            resp = vista(self._get('/inventarios/reportes/movimientos/', usuario_falso()))
            self.assertEqual(resp.status_code, 403, vista.__name__)

    def test_tabla_movimientos_contexto(self):
        url = '/inventarios/reportes/movimientos/?tipo=SALIDA&page=2&op_producto=contiene&val_producto=foco'
        with mock.patch.object(sel, 'movimientos_tabla', return_value=[]) as consulta, \
                mock.patch.object(reportes, 'render') as render:
            reportes.tabla_movimientos_view(self._get(url, usuario_falso(superuser=True)))
        self.assertEqual(consulta.call_args[0][0].get('tipo'), 'SALIDA')
        plantilla, ctx = render.call_args[0][1], render.call_args[0][2]
        self.assertEqual(plantilla, 'inventarios/tabla_movimientos.html')
        self.assertEqual(ctx['querystring'], 'tipo=SALIDA&op_producto=contiene&val_producto=foco')
        self.assertEqual(ctx['f_tipo'], 'SALIDA')
        self.assertEqual(ctx['active_tab'], 'movimientos')
        self.assertEqual(ctx['estados_movimiento'], sel.ESTADOS_MOVIMIENTO)
        producto = next(c for c in ctx['columnas'] if c['key'] == 'producto')
        self.assertEqual((producto['op'], producto['val']), ('contiene', 'foco'))
        self.assertEqual(ctx['page'].number, 1)  # página fuera de rango -> última válida

    def test_pases_pendientes_contexto(self):
        url = '/inventarios/reportes/pases-pendientes/?departamento=none&op_comentarios=vacio'
        pases = [pase_falso(1, None, 2)]
        with mock.patch.object(sel, 'pases_pendientes', return_value=pases), \
                mock.patch.object(reportes, 'render') as render:
            reportes.reporte_pases_pendientes_view(self._get(url, usuario_falso(superuser=True)))
        plantilla, ctx = render.call_args[0][1], render.call_args[0][2]
        self.assertEqual(plantilla, 'inventarios/reporte_pases_pendientes.html')
        self.assertEqual(ctx['total'], 1)
        self.assertEqual(ctx['resumen'], [{'departamento': 'Sin departamento', 'total': 1, 'items': 2}])
        self.assertEqual(ctx['querystring'], 'departamento=none&op_comentarios=vacio')
        self.assertEqual(ctx['f_departamento'], 'none')
        self.assertEqual(ctx['active_tab'], 'reportes')

    def test_exports_devuelven_excel(self):
        user = usuario_falso(superuser=True)
        with mock.patch.object(sel, 'pases_pendientes', return_value=IterQS([pase_falso(1, 'A', 1)])):
            resp = reportes.export_pases_pendientes_excel(self._get('/x/', user))
        self.assertIn('pases_pendientes_justificar_', resp['Content-Disposition'])
        self.assertEqual(leer_xlsx(resp).max_row, 2)

        with mock.patch.object(sel, 'movimientos_export', return_value=IterQS([movimiento_falso(1)])), \
                mock.patch.object(sel, 'activos_por_movimiento', return_value={}):
            resp = reportes.export_movimientos_excel(self._get('/x/', user))
        self.assertIn('movimientos_inventario_', resp['Content-Disposition'])
        self.assertEqual(leer_xlsx(resp).max_row, 2)


# ---------------------------------------------------------------------------
# Rutas, plantillas y compatibilidad
# ---------------------------------------------------------------------------

class RutasTests(SimpleTestCase):
    RUTAS = {
        'inventarios:reportes': ('/inventarios/reportes/', 'reporte_inventario_view'),
        'inventarios:tabla_movimientos': ('/inventarios/reportes/movimientos/', 'tabla_movimientos_view'),
        'inventarios:export_movimientos_excel': ('/inventarios/reportes/movimientos/excel/', 'export_movimientos_excel'),
        'inventarios:reporte_pases_pendientes': ('/inventarios/reportes/pases-pendientes/', 'reporte_pases_pendientes_view'),
        'inventarios:export_pases_pendientes_excel': ('/inventarios/reportes/pases-pendientes/excel/', 'export_pases_pendientes_excel'),
        'inventarios:export_inventario_actual_excel': ('/inventarios/reportes/inventario/excel/', 'export_inventario_actual_excel'),
        'inventarios:export_catalogo_excel': ('/inventarios/reportes/catalogo/excel/', 'export_catalogo_excel'),
    }

    def test_nombres_paths_y_vistas_sin_cambios(self):
        for nombre, (path, vista) in self.RUTAS.items():
            self.assertEqual(reverse(nombre), path, nombre)
            match = resolve(path)
            self.assertEqual(match.func.__name__, vista, nombre)
            self.assertEqual(match.namespace, 'inventarios', nombre)

    def test_rutas_vecinas_siguen_funcionando(self):
        self.assertEqual(reverse('inventarios:dashboard'), '/inventarios/')
        self.assertEqual(reverse('inventarios:solicitud_nuevos_materiales'), '/inventarios/nuevos-materiales/')


class PlantillasTests(SimpleTestCase):
    def test_compilan(self):
        for nombre in ('inventarios/tabla_movimientos.html', 'inventarios/reporte_pases_pendientes.html',
                       'inventarios/dashboard.html', 'inventarios/base_inventarios.html'):
            get_template(nombre)


class CompatibilidadTests(SimpleTestCase):
    """Los nombres antiguos de inventarios/reportes.py siguen disponibles."""

    def test_alias(self):
        self.assertIs(reportes.supervisor_almacen_required, permissions.supervisor_almacen_required)
        self.assertIs(reportes.es_supervisor_almacen, permissions.es_supervisor_almacen)
        self.assertIs(reportes.COLUMNAS_PASES, sel.COLUMNAS_PASES)
        self.assertIs(reportes._departamento_de, sel.departamento_de)
        self.assertEqual([c['key'] for c in reportes.columnas_con_estado({})],
                         [c['key'] for c in sel.COLUMNAS_MOVIMIENTOS])
        for nombre in ('_estilos', '_escribir_headers', '_autoajustar', '_parse_fecha',
                       'aplicar_filtros', 'aplicar_filtros_columnas', '_pases_pendientes_qs', '_nombre_usuario'):
            self.assertTrue(callable(getattr(reportes, nombre)), nombre)

    def test_pases_pendientes_qs_delega_en_el_selector(self):
        req = RequestFactory().get('/x/', {'departamento': '3'})
        with mock.patch.object(sel, 'pases_pendientes', return_value='qs') as consulta:
            self.assertEqual(reportes._pases_pendientes_qs(req), 'qs')
        self.assertIs(consulta.call_args[0][0], req.GET)
