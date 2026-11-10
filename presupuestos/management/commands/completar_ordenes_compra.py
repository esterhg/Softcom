"""
Completa las Órdenes de Compra existentes para que lleven todo lo pedido en la requisición:

1. Cada línea de OC queda vinculada a su material/servicio (desde el artículo de requisición).
2. Los artículos de la requisición que no están en ninguna de sus OCs se agregan a la OC
   del mismo proveedor (si la requisición tiene una sola OC, se agregan a esa).

Uso:
    python manage.py completar_ordenes_compra --dry-run   # solo muestra lo que haría
    python manage.py completar_ordenes_compra             # aplica los cambios
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Completa las OCs existentes con material y artículos faltantes de su requisición.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='No guarda cambios, solo informa.')

    def handle(self, *args, **opts):
        from presupuestos.models import OrdenCompra, OrdenCompraArticulo, Requisicion

        dry = opts['dry_run']
        lineas_material = 0
        lineas_agregadas = 0
        sin_destino = []

        with transaction.atomic():
            # 1. Material en las líneas
            for linea in OrdenCompraArticulo.objects.filter(material__isnull=True, articulo_requisicion__material__isnull=False).select_related('articulo_requisicion'):
                lineas_material += 1
                if not dry:
                    OrdenCompraArticulo.objects.filter(pk=linea.pk).update(material_id=linea.articulo_requisicion.material_id)

            # 2. Artículos faltantes
            reqs = Requisicion.objects.filter(ordenes_compra__isnull=False).distinct().prefetch_related('ordenes_compra', 'articulos')
            for req in reqs:
                ocs = list(req.ordenes_compra.all())
                incluidos = set(
                    OrdenCompraArticulo.objects.filter(orden_compra__in=ocs, articulo_requisicion__isnull=False)
                    .values_list('articulo_requisicion_id', flat=True)
                )
                for art in req.articulos.all():
                    if art.pk in incluidos:
                        continue
                    destino = None
                    prov_id = art.proveedor_id or req.proveedor_id
                    if prov_id:
                        destino = next((oc for oc in ocs if oc.proveedor_id == prov_id), None)
                    if not destino and len(ocs) == 1:
                        destino = ocs[0]
                    if not destino:
                        sin_destino.append(f"{req.cr8ca_requisicion}: {art.cr8ca_articulo[:60]}")
                        continue
                    lineas_agregadas += 1
                    self.stdout.write(f"  + {destino.numero_oc} <- {art.cr8ca_articulo[:60]} x {art.cr8ca_cantidad}")
                    if not dry:
                        OrdenCompraArticulo.objects.create(
                            orden_compra=destino,
                            articulo_requisicion=art,
                            material=art.material,
                            descripcion=art.cr8ca_articulo or (art.material.nombre if art.material else ''),
                            cantidad=art.cr8ca_cantidad or 0,
                            costo_unitario=art.cr8ca_costoaproximado or 0,
                        )
                if not dry:
                    for oc in ocs:
                        oc.subtotal = sum(a.subtotal for a in oc.articulos.all())
                        oc.total = oc.subtotal + oc.impuestos
                        oc.save(update_fields=['subtotal', 'total'])

            if dry:
                transaction.set_rollback(True)

        modo = 'SIMULACIÓN (sin cambios)' if dry else 'APLICADO'
        self.stdout.write(self.style.SUCCESS(
            f"{modo}: {lineas_material} líneas con material vinculado, {lineas_agregadas} artículos agregados a OCs."))
        if sin_destino:
            self.stdout.write(self.style.WARNING(
                f"{len(sin_destino)} artículos sin OC de su proveedor (revisar a mano):"))
            for s in sin_destino:
                self.stdout.write(f"  - {s}")
