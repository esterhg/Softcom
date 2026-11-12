"""Reglas de negocio del CRUD de proveedores (mantenimiento.Empresa)."""
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from mantenimiento.models import Empresa
from presupuestos.selectors.proveedores import dependencias_proveedor

CAMPOS_TEXTO = ('numero_proveedor', 'rtn', 'domicilio', 'contacto', 'telefono')


class ProveedorError(ValueError):
    """Dato inválido o regla de negocio incumplida."""


def serializar(empresa):
    return {
        'id': empresa.id,
        'nombre': empresa.nombre,
        'numero_proveedor': empresa.numero_proveedor or '',
        'rtn': empresa.rtn or '',
        'domicilio': empresa.domicilio or '',
        'contacto': empresa.contacto or '',
        'telefono': empresa.telefono or '',
        'email': empresa.email or '',
        'activo': empresa.activo,
    }


def _validar(datos, excluir_pk=None):
    nombre = ' '.join((datos.get('nombre') or '').split())
    if not nombre:
        raise ProveedorError('El nombre del proveedor es obligatorio.')
    if len(nombre) > 200:
        raise ProveedorError('El nombre no puede superar 200 caracteres.')
    duplicado = Empresa.objects.filter(nombre__iexact=nombre)
    if excluir_pk:
        duplicado = duplicado.exclude(pk=excluir_pk)
    if duplicado.exists():
        raise ProveedorError('Ya existe otro proveedor con ese nombre.')

    limpio = {'nombre': nombre}
    for campo in CAMPOS_TEXTO:
        limpio[campo] = (datos.get(campo) or '').strip() or None
    if limpio['numero_proveedor'] and len(limpio['numero_proveedor']) > 50:
        raise ProveedorError('El número de proveedor no puede superar 50 caracteres.')
    if limpio['rtn'] and len(limpio['rtn']) > 30:
        raise ProveedorError('El R.T.N. no puede superar 30 caracteres.')
    if limpio['telefono'] and len(limpio['telefono']) > 50:
        raise ProveedorError('El teléfono no puede superar 50 caracteres.')
    if limpio['contacto'] and len(limpio['contacto']) > 200:
        raise ProveedorError('El contacto no puede superar 200 caracteres.')

    email = (datos.get('email') or '').strip() or None
    if email:
        try:
            validate_email(email)
        except ValidationError:
            raise ProveedorError('El correo electrónico no es válido.')
    limpio['email'] = email
    limpio['activo'] = bool(datos.get('activo', True))
    return limpio


def crear_proveedor(datos):
    return Empresa.objects.create(**_validar(datos))


def actualizar_proveedor(empresa, datos):
    for campo, valor in _validar(datos, excluir_pk=empresa.pk).items():
        setattr(empresa, campo, valor)
    empresa.save()
    return empresa


def eliminar_proveedor(empresa):
    """Elimina el proveedor solo si nada lo referencia; si no, sugiere desactivarlo."""
    deps = dependencias_proveedor(empresa)
    if deps:
        detalle = ', '.join(f'{n}: {c}' for n, c in deps)
        raise ProveedorError(
            f'No se puede eliminar "{empresa.nombre}" porque tiene información asociada '
            f'({detalle}). Puedes desactivarlo editando el proveedor.'
        )
    nombre = empresa.nombre
    empresa.delete()
    return nombre
