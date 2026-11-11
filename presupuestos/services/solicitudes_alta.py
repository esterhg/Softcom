"""
Reglas de negocio de las solicitudes de alta (proveedor / material).

Nunca reciben ``request``: las vistas pasan el usuario y datos simples.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from inventarios.models import Material, UnidadMedida
from mantenimiento.models import Empresa
from presupuestos import permissions
from presupuestos.models import SolicitudAltaMaterial, SolicitudAltaProveedor
from presupuestos.selectors import solicitudes_alta as sel

logger = logging.getLogger(__name__)


def _limpio(valor, maximo=None):
    valor = (valor or '').strip()
    return valor[:maximo] if maximo else valor


# ---------------------------------------------------------------- proveedor --

def crear_solicitud_proveedor(requisicion, usuario, datos):
    """Crea una solicitud de alta de proveedor para una requisición."""
    nombre = _limpio(datos.get('nombre'), 200)
    if not nombre:
        raise ValidationError('Indique el nombre del proveedor.')

    existente = Empresa.objects.filter(nombre__iexact=nombre).first()
    if existente:
        raise ValidationError(
            f'El proveedor "{existente.nombre}" ya está dado de alta. Selecciónelo de la lista.')

    if SolicitudAltaProveedor.objects.filter(
            nombre__iexact=nombre, estado=SolicitudAltaProveedor.ESTADO_PENDIENTE).exists():
        raise ValidationError('Ya existe una solicitud pendiente para ese proveedor.')

    return SolicitudAltaProveedor.objects.create(
        requisicion=requisicion,
        solicitante=usuario,
        nombre=nombre,
        rtn=_limpio(datos.get('rtn'), 30),
        contacto=_limpio(datos.get('contacto'), 200),
        telefono=_limpio(datos.get('telefono'), 50),
        email=_limpio(datos.get('email')),
        justificacion=_limpio(datos.get('justificacion')),
    )


def aprobar_solicitud_proveedor(solicitud, revisor, datos=None):
    """Da de alta el proveedor y lo asigna a la requisición si no tenía uno."""
    if not permissions.puede_aprobar_proveedores(revisor):
        raise PermissionDenied('Solo Procura puede aprobar altas de proveedor.')
    with transaction.atomic():
        return _aprobar_proveedor(solicitud, revisor, datos)


def _aprobar_proveedor(solicitud, revisor, datos):
    solicitud = type(solicitud).objects.select_for_update().get(pk=solicitud.pk)
    if not solicitud.esta_pendiente:
        raise ValidationError('La solicitud ya fue resuelta.')

    datos = datos or {}
    nombre = _limpio(datos.get('nombre'), 200) or solicitud.nombre
    proveedor = Empresa.objects.filter(nombre__iexact=nombre).first()
    if not proveedor:
        proveedor = Empresa.objects.create(
            nombre=nombre,
            numero_proveedor=_limpio(datos.get('numero_proveedor'), 50) or None,
            rtn=(_limpio(datos.get('rtn'), 30) or solicitud.rtn) or None,
            contacto=(_limpio(datos.get('contacto'), 200) or solicitud.contacto) or None,
            telefono=(_limpio(datos.get('telefono'), 50) or solicitud.telefono) or None,
            email=(_limpio(datos.get('email')) or solicitud.email) or None,
            domicilio=_limpio(datos.get('domicilio')) or None,
            activo=True,
        )

    solicitud.proveedor = proveedor
    solicitud.estado = SolicitudAltaProveedor.ESTADO_APROBADA
    solicitud.revisado_por = revisor
    solicitud.revisado_en = timezone.now()
    solicitud.save()

    req = solicitud.requisicion
    if not req.proveedor_id:
        req.proveedor = proveedor
        req.save(update_fields=['proveedor'])
        req.articulos.filter(proveedor__isnull=True).update(proveedor=proveedor)
    return solicitud


def rechazar_solicitud_proveedor(solicitud, revisor, motivo):
    if not permissions.puede_aprobar_proveedores(revisor):
        raise PermissionDenied('Solo Procura puede rechazar altas de proveedor.')
    with transaction.atomic():
        return _rechazar(solicitud, revisor, motivo)


# ----------------------------------------------------------------- material --

def crear_solicitud_material(requisicion, usuario, datos, articulo=None):
    """Crea una solicitud de alta de material (opcionalmente ligada a un artículo)."""
    nombre = _limpio(datos.get('nombre'), 200)
    if not nombre:
        raise ValidationError('Indique el nombre del material.')

    existente = Material.objects.filter(nombre__iexact=nombre).first()
    if existente:
        raise ValidationError(
            f'El material "{existente.nombre}" (SKU {existente.sku}) ya existe. Selecciónelo del catálogo.')

    if articulo is not None and articulo.solicitudes_alta_material.filter(
            estado=SolicitudAltaMaterial.ESTADO_PENDIENTE).exists():
        raise ValidationError('Ese artículo ya tiene una solicitud pendiente.')

    try:
        precio = Decimal(str(datos.get('precio_estimado') or 0).replace(',', ''))
    except InvalidOperation:
        raise ValidationError('El precio estimado no es válido.')
    if precio < 0:
        raise ValidationError('El precio estimado no puede ser negativo.')

    unidad = None
    unidad_id = datos.get('unidad_medida')
    if unidad_id:
        unidad = UnidadMedida.objects.filter(pk=unidad_id).first()

    return SolicitudAltaMaterial.objects.create(
        requisicion=requisicion,
        articulo=articulo,
        solicitante=usuario,
        nombre=nombre,
        descripcion=_limpio(datos.get('descripcion')),
        unidad_medida=unidad,
        precio_estimado=precio,
        justificacion=_limpio(datos.get('justificacion')),
    )


def aprobar_solicitud_material(solicitud, revisor, sku, datos=None):
    """Crea el material con el SKU indicado y lo liga al artículo de la requisición.

    ``datos`` (opcional): unidad_medida (id), precio_estimado y descripcion que
    Almacén completa al aprobar.
    """
    if not permissions.puede_aprobar_materiales(revisor):
        raise PermissionDenied('Solo Almacén puede aprobar altas de material.')
    with transaction.atomic():
        return _aprobar_material(solicitud, revisor, sku, datos or {})


def _aprobar_material(solicitud, revisor, sku, datos):
    solicitud = type(solicitud).objects.select_for_update().get(pk=solicitud.pk)
    if not solicitud.esta_pendiente:
        raise ValidationError('La solicitud ya fue resuelta.')

    sku = _limpio(sku, 50)
    if not sku:
        raise ValidationError('Asigne un SKU para aprobar el material.')
    if Material.objects.filter(sku__iexact=sku).exists():
        raise ValidationError(f'El SKU "{sku}" ya existe.')

    unidad = solicitud.unidad_medida
    if datos.get('unidad_medida'):
        unidad = UnidadMedida.objects.filter(pk=datos['unidad_medida']).first() or unidad

    precio = solicitud.precio_estimado
    if str(datos.get('precio_estimado') or '').strip():
        try:
            precio = Decimal(str(datos['precio_estimado']).replace(',', ''))
        except InvalidOperation:
            raise ValidationError('El precio estimado no es válido.')
        if precio < 0:
            raise ValidationError('El precio estimado no puede ser negativo.')

    material = Material.objects.create(
        nombre=solicitud.nombre,
        sku=sku,
        descripcion=(_limpio(datos.get('descripcion')) or solicitud.descripcion) or None,
        unidad_medida=unidad,
        precio_estimado=precio,
    )

    solicitud.material = material
    solicitud.estado = SolicitudAltaMaterial.ESTADO_APROBADA
    solicitud.revisado_por = revisor
    solicitud.revisado_en = timezone.now()
    solicitud.save()

    art = solicitud.articulo
    if art is not None and not art.material_id:
        art.material = material
        art.save()
    return solicitud


def rechazar_solicitud_material(solicitud, revisor, motivo):
    if not permissions.puede_aprobar_materiales(revisor):
        raise PermissionDenied('Solo Almacén puede rechazar altas de material.')
    with transaction.atomic():
        return _rechazar(solicitud, revisor, motivo)


def solicitar_material_nuevo(requisicion, usuario, nombre, descripcion='', precio=0):
    """Pide a Almacén el alta de un material que no existe en el catálogo.

    Solo registra la solicitud: el producto NO se agrega a la requisición hasta
    que Almacén lo apruebe (entonces existe en el catálogo y se selecciona normal).
    """
    return crear_solicitud_material(
        requisicion, usuario,
        {'nombre': nombre, 'descripcion': descripcion, 'precio_estimado': precio})


# ------------------------------------------------------------------ común ---

def _rechazar(solicitud, revisor, motivo):
    motivo = _limpio(motivo)
    if not motivo:
        raise ValidationError('Indique el motivo del rechazo.')
    solicitud = type(solicitud).objects.select_for_update().get(pk=solicitud.pk)
    if not solicitud.esta_pendiente:
        raise ValidationError('La solicitud ya fue resuelta.')
    solicitud.estado = solicitud.ESTADO_RECHAZADA
    solicitud.motivo_rechazo = motivo
    solicitud.revisado_por = revisor
    solicitud.revisado_en = timezone.now()
    solicitud.save()
    return solicitud


def bloqueos_de_requisicion(requisicion):
    """Mensajes que impiden enviar la requisición por solicitudes de alta sin resolver."""
    mensajes = []
    for s in sel.proveedor_pendiente(requisicion):
        mensajes.append(
            f'Proveedor "{s.nombre}": alta pendiente de aprobación de Procura.')
    for s in sel.materiales_pendientes(requisicion):
        mensajes.append(
            f'Material "{s.nombre}": alta pendiente de aprobación de Almacén.')
    return mensajes
