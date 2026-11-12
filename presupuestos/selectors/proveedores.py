"""Consultas de lectura de proveedores (mantenimiento.Empresa)."""
from django.db.models import Count, F, Max, Sum

from mantenimiento.models import Empresa


def listar_proveedores(q='', estado='todos'):
    """Proveedores con métricas de requisiciones.

    ``estado``: 'todos' | 'activos' | 'inactivos'.
    Incluye los que no tienen requisiciones, para poder administrarlos.
    """
    qs = Empresa.objects.annotate(
        total_requisiciones=Count('requisiciones_asignadas', distinct=True),
        monto_total_solicitado=Sum('requisiciones_asignadas__cr8ca_totalenarticulos'),
        ultima_fecha_requisicion=Max('requisiciones_asignadas__fecha'),
    )
    q = (q or '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(nombre__icontains=q) | Q(rtn__icontains=q) | Q(numero_proveedor__icontains=q)
        )
    if estado == 'activos':
        qs = qs.filter(activo=True)
    elif estado == 'inactivos':
        qs = qs.filter(activo=False)
    return qs.order_by(F('monto_total_solicitado').desc(nulls_last=True), 'nombre')


def dependencias_proveedor(empresa):
    """Cantidad de registros que referencian al proveedor, por modelo.

    Devuelve [(nombre_plural, cantidad)] solo con los que tienen datos. Sirve para
    decidir si se puede eliminar sin dejar información huérfana.
    """
    resultado = []
    for rel in Empresa._meta.related_objects:
        modelo = rel.related_model
        cantidad = modelo._default_manager.filter(**{rel.field.name: empresa}).count()
        if cantidad:
            resultado.append((str(modelo._meta.verbose_name_plural), cantidad))
    return resultado
