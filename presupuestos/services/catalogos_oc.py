"""Reglas de negocio para ampliar los catálogos de la Orden de Compra."""
from django.utils.text import slugify

from presupuestos.models import CentroCosto, TipoContrato


class CatalogoError(ValueError):
    """Dato inválido al crear una opción de catálogo."""


def _limpiar_nombre(nombre, maximo):
    nombre = ' '.join((nombre or '').split())
    if not nombre:
        raise CatalogoError('El nombre es obligatorio.')
    if len(nombre) > maximo:
        raise CatalogoError(f'El nombre no puede superar {maximo} caracteres.')
    return nombre


def crear_centro_costo(nombre):
    """Crea (o reactiva) un centro de costo. Devuelve (centro, creado)."""
    nombre = _limpiar_nombre(nombre, 200)
    existente = CentroCosto.objects.filter(nombre__iexact=nombre).first()
    if existente:
        if not existente.activo:
            existente.activo = True
            existente.save(update_fields=['activo'])
        return existente, False
    return CentroCosto.objects.create(nombre=nombre), True


def _codigo_unico(nombre):
    base = (slugify(nombre).replace('-', '_').upper() or 'TIPO')[:26]
    codigo, n = base, 2
    while TipoContrato.objects.filter(codigo=codigo).exists():
        codigo = f'{base}_{n}'
        n += 1
    return codigo


def crear_tipo_contrato(nombre):
    """Crea (o reactiva) un tipo de contrato. Devuelve (tipo, creado)."""
    nombre = _limpiar_nombre(nombre, 100)
    existente = TipoContrato.objects.filter(nombre__iexact=nombre).first()
    if existente:
        if not existente.activo:
            existente.activo = True
            existente.save(update_fields=['activo'])
        return existente, False
    return TipoContrato.objects.create(codigo=_codigo_unico(nombre), nombre=nombre), True
