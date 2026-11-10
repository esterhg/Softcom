"""
Pruebas CON base de datos del paso 1 (selectors de reportes de inventario).

Por seguridad se SALTAN por defecto: Django crearía una base ``test_*`` en el
servidor al que apunta ``DATABASES`` y, en local, ese servidor es el mismo de
producción (túnel). Ejecutarlas solo contra un PostgreSQL de desarrollo con la
extensión pgvector:

    $env:SOFTCOM_TEST_DB = "1"
    $env:DATABASE_URL = "postgresql://usuario:clave@host:5432/softcom_dev"
    python manage.py test inventarios.test_reportes_bd

Se usan ``bulk_create`` para OT, Ticket, Material y Movimiento: no disparan
señales (notificaciones push, recálculo de stock) ni salen a la red.
"""
import os
import unittest
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from callcenter.models import SolicitudTicket
from core.models import Departamento, PerfilUsuario
from inventarios.models import Material, MovimientoInventario, SolicitudMaterial
from inventarios.selectors import reportes as sel
from inventarios.services import reportes as svc
from mantenimiento.models import OrdenTrabajo

HABILITADO = os.environ.get('SOFTCOM_TEST_DB') == '1'
MOTIVO = 'Pruebas con BD desactivadas (definir SOFTCOM_TEST_DB=1 con una BD de desarrollo).'

# Importante: si están desactivadas, las clases heredan de SimpleTestCase
# (databases vacío). Un simple @skip sobre TestCase NO basta: el runner de
# Django igual crearía la base test_* porque cuenta las clases saltadas.
BaseBD = TestCase if HABILITADO else SimpleTestCase


@unittest.skipUnless(HABILITADO, MOTIVO)
class PasesPendientesBDTests(BaseBD):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.depto = Departamento.objects.create(nombre='Almacenes Test')
        cls.ana = User.objects.create_user('ana_test', first_name='Ana', last_name='Pérez')
        PerfilUsuario.objects.filter(usuario=cls.ana).update(departamento=cls.depto)
        cls.luis = User.objects.create_user('luis_test')  # sin departamento

        ahora = timezone.now()
        otnp, preventiva = OrdenTrabajo.objects.bulk_create([
            OrdenTrabajo(tipo='NO_PROGRAMADA', codigo_de_orden='OTNP-T-1',
                         inicio_programado=ahora, fin_programado=ahora + timedelta(hours=1)),
            OrdenTrabajo(tipo='PREVENTIVA', codigo_de_orden='OT-T-2',
                         inicio_programado=ahora, fin_programado=ahora + timedelta(hours=1)),
        ])
        ticket = SolicitudTicket.objects.bulk_create([SolicitudTicket(id_solicitud=999000111)])[0]

        crear = SolicitudMaterial.objects.create
        cls.sin_justificar = crear(usuario=cls.ana, estado='PENDIENTE', comentarios_solicitud='Uso en obra')
        cls.con_preventiva = crear(usuario=cls.luis, estado='ENTREGADO', orden_trabajo=preventiva)
        crear(usuario=cls.ana, estado='PENDIENTE', orden_trabajo=otnp)       # justificado por OTNP
        crear(usuario=cls.ana, estado='PENDIENTE', ticket=ticket)            # justificado por ticket
        crear(usuario=cls.ana, estado='BORRADOR')                            # borrador: no cuenta
        crear(usuario=cls.ana, estado='RECHAZADO')                           # rechazado: no cuenta

    def ids(self, params):
        return set(sel.pases_pendientes(params).values_list('id', flat=True))

    def test_regla_de_negocio(self):
        self.assertEqual(self.ids({}), {self.sin_justificar.id, self.con_preventiva.id})

    def test_filtros_de_departamento(self):
        self.assertEqual(self.ids({'departamento': str(self.depto.id)}), {self.sin_justificar.id})
        self.assertEqual(self.ids({'departamento': 'none'}), {self.con_preventiva.id})

    def test_filtros_por_columna(self):
        self.assertEqual(self.ids({'op_comentarios': 'vacio'}), {self.con_preventiva.id})
        self.assertEqual(self.ids({'op_ot': 'tiene'}), {self.con_preventiva.id})
        self.assertEqual(self.ids({'op_solicitante': 'contiene', 'val_solicitante': 'ana p'}),
                         {self.sin_justificar.id})
        self.assertEqual(self.ids({'op_estado': 'igual', 'val_estado': 'Pendiente'}), {self.sin_justificar.id})

    def test_resumen_por_departamento(self):
        resumen = svc.resumen_por_departamento(list(sel.pases_pendientes({})))
        self.assertEqual({r['departamento']: r['total'] for r in resumen},
                         {'Almacenes Test': 1, 'Sin departamento': 1})


@unittest.skipUnless(HABILITADO, MOTIVO)
class MovimientosBDTests(BaseBD):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ana = User.objects.create_user('ana_mov_test')
        foco, cable = Material.objects.bulk_create([
            Material(nombre='Foco LED Test', sku='T-FOCO-1'),
            Material(nombre='Cable Test', sku='T-CABLE-1'),
        ])
        cls.aprobado, cls.pendiente = MovimientoInventario.objects.bulk_create([
            MovimientoInventario(material=foco, tipo='SALIDA', cantidad=Decimal('2'), estado='APROBADO',
                                 usuario=cls.ana, aprobado_por=cls.ana),
            MovimientoInventario(material=cable, tipo='ENTRADA', cantidad=Decimal('10'), estado='PENDIENTE',
                                 usuario=cls.ana),
        ])

    def ids(self, funcion, params):
        return set(funcion(params).values_list('id', flat=True))

    def test_tabla_y_export_aplican_los_mismos_filtros_por_columna(self):
        for funcion in (sel.movimientos_tabla, sel.movimientos_export):
            self.assertEqual(self.ids(funcion, {'op_aprobo': 'vacio'}), {self.pendiente.id})
            self.assertEqual(self.ids(funcion, {'op_producto': 'contiene', 'val_producto': 'foco'}),
                             {self.aprobado.id})
            self.assertEqual(self.ids(funcion, {'op_cantidad': 'mayor', 'val_cantidad': '5'}),
                             {self.pendiente.id})
            self.assertEqual(self.ids(funcion, {'op_tipo': 'igual', 'val_tipo': 'SALIDA'}), {self.aprobado.id})

    def test_busqueda_libre_solo_en_tabla(self):
        self.assertEqual(self.ids(sel.movimientos_tabla, {'q': 'T-CABLE'}), {self.pendiente.id})
        self.assertEqual(self.ids(sel.movimientos_export, {'q': 'T-CABLE'}),
                         {self.aprobado.id, self.pendiente.id})
