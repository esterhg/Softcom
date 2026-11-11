"""Pruebas sin base de datos (SimpleTestCase) de las reglas de alta y validaciones."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase

from presupuestos import permissions, validaciones
from presupuestos.services import solicitudes_alta as svc


def _user(superuser=False, grupos=()):
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = superuser
    u.groups.filter.side_effect = lambda name__in: MagicMock(
        exists=lambda: any(g in name__in for g in grupos))
    return u


def _req(tipo='BIEN', proveedor_id=1, articulos=()):
    arts = MagicMock()
    arts.select_related.return_value.all.return_value = list(articulos)
    return SimpleNamespace(
        tipo=tipo, proveedor_id=proveedor_id, edificio_id=1, nivel_id=1,
        ubicacion_id=1, articulos=arts)


def _art(material_id=1, cantidad=1, nombre='Tornillo'):
    return SimpleNamespace(
        material_id=material_id, cr8ca_cantidad=Decimal(cantidad), cr8ca_articulo=nombre)


@patch('presupuestos.services.solicitudes_alta.bloqueos_de_requisicion', return_value=[])
class ErroresRequisicionTests(SimpleTestCase):
    def test_bien_completo_sin_errores(self, _):
        self.assertEqual(validaciones.errores_requisicion(_req(articulos=[_art()])), [])

    def test_bien_sin_proveedor_es_error(self, _):
        errores = validaciones.errores_requisicion(_req(proveedor_id=None, articulos=[_art()]))
        self.assertTrue(any('proveedor' in e.lower() for e in errores))

    def test_bien_sin_material_es_error(self, _):
        errores = validaciones.errores_requisicion(_req(articulos=[_art(material_id=None)]))
        self.assertTrue(any('catálogo' in e for e in errores))

    def test_servicio_sin_proveedor_ni_material_es_valido(self, _):
        req = _req(tipo='SERVICIO', proveedor_id=None, articulos=[_art(material_id=None)])
        self.assertEqual(validaciones.errores_requisicion(req), [])

    def test_servicio_exige_lugar(self, _):
        req = _req(tipo='SERVICIO', proveedor_id=None, articulos=[_art(material_id=None)])
        req.ubicacion_id = None
        errores = validaciones.errores_requisicion(req)
        self.assertTrue(any('ubicación' in e for e in errores))

    def test_servicio_sigue_exigiendo_cantidad(self, _):
        req = _req(tipo='SERVICIO', proveedor_id=None, articulos=[_art(material_id=None, cantidad=0)])
        self.assertTrue(validaciones.errores_requisicion(req))

    def test_sin_articulos_es_error(self, _):
        self.assertTrue(validaciones.errores_requisicion(_req(articulos=[])))


class BloqueoPorAltasPendientesTests(SimpleTestCase):
    def test_solicitud_pendiente_bloquea_el_envio(self):
        with patch('presupuestos.services.solicitudes_alta.bloqueos_de_requisicion',
                   return_value=['Proveedor "X": alta pendiente de aprobación de Procura.']):
            errores = validaciones.errores_requisicion(_req(articulos=[_art()]))
        self.assertIn('Proveedor "X": alta pendiente de aprobación de Procura.', errores)


class PermisosTests(SimpleTestCase):
    def test_procura_aprueba_proveedores_no_materiales(self):
        u = _user(grupos=('Procura',))
        self.assertTrue(permissions.puede_aprobar_proveedores(u))
        self.assertFalse(permissions.puede_aprobar_materiales(u))

    def test_variante_PROCURA(self):
        self.assertTrue(permissions.puede_aprobar_proveedores(_user(grupos=('PROCURA',))))

    def test_almacen_y_supervisor_aprueban_materiales(self):
        for grupo in ('Almacenes', 'Supervisor de Almacen'):
            u = _user(grupos=(grupo,))
            self.assertTrue(permissions.puede_aprobar_materiales(u), grupo)
            self.assertFalse(permissions.puede_aprobar_proveedores(u), grupo)

    def test_superusuario_solo_aprueba_materiales_si_no_esta_en_procura(self):
        u = _user(superuser=True)
        self.assertFalse(permissions.puede_aprobar_proveedores(u))
        self.assertTrue(permissions.puede_aprobar_materiales(u))

    def test_superusuario_en_procura_si_aprueba_proveedores(self):
        self.assertTrue(permissions.puede_aprobar_proveedores(_user(superuser=True, grupos=('Procura',))))

    def test_usuario_sin_grupo_no_accede_a_ninguna_tabla(self):
        u = _user()
        self.assertFalse(permissions.puede_aprobar_proveedores(u))
        self.assertFalse(permissions.puede_aprobar_materiales(u))

    def test_tablas_separadas_por_grupo(self):
        """Procura no ve la tabla de materiales y Almacén no ve la de proveedores (403)."""
        from django.test import RequestFactory
        rf = RequestFactory()

        def vista_ok(request):
            return 'ok'

        def probar(decorador, usuario):
            req = rf.get('/x')
            req.user = usuario
            return decorador(vista_ok)(req)

        self.assertEqual(probar(permissions.procura_required, _user(grupos=('Procura',))), 'ok')
        self.assertEqual(probar(permissions.procura_required, _user(grupos=('Almacenes',))).status_code, 403)
        self.assertEqual(probar(permissions.almacen_altas_required, _user(grupos=('Almacenes',))), 'ok')
        self.assertEqual(probar(permissions.almacen_altas_required, _user(grupos=('Procura',))).status_code, 403)

    def test_anonimo_sin_permisos(self):
        anon = MagicMock(is_authenticated=False)
        self.assertFalse(permissions.puede_aprobar_proveedores(anon))


class ServicesSinPermisoTests(SimpleTestCase):
    """El permiso se valida antes de tocar la base de datos."""

    def test_aprobar_proveedor_sin_permiso(self):
        with self.assertRaises(PermissionDenied):
            svc.aprobar_solicitud_proveedor(MagicMock(), _user())

    def test_rechazar_proveedor_sin_permiso(self):
        with self.assertRaises(PermissionDenied):
            svc.rechazar_solicitud_proveedor(MagicMock(), _user(grupos=('Almacenes',)), 'x')

    def test_aprobar_material_sin_permiso(self):
        with self.assertRaises(PermissionDenied):
            svc.aprobar_solicitud_material(MagicMock(), _user(grupos=('Procura',)), 'SKU1')

    def test_rechazar_material_sin_permiso(self):
        with self.assertRaises(PermissionDenied):
            svc.rechazar_solicitud_material(MagicMock(), _user(), 'x')

    def test_crear_proveedor_exige_nombre(self):
        with self.assertRaises(ValidationError):
            svc.crear_solicitud_proveedor(MagicMock(), _user(), {'nombre': '   '})

    def test_crear_material_exige_nombre(self):
        with self.assertRaises(ValidationError):
            svc.crear_solicitud_material(MagicMock(), _user(), {'nombre': ''})
