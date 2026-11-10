from django.db import migrations, models
import django.db.models.deletion


def backfill_material_oc(apps, schema_editor):
    """Copia el material del artículo de requisición a las líneas de OC existentes."""
    OrdenCompraArticulo = apps.get_model('presupuestos', 'OrdenCompraArticulo')
    for linea in OrdenCompraArticulo.objects.filter(material__isnull=True, articulo_requisicion__isnull=False).select_related('articulo_requisicion'):
        mat_id = linea.articulo_requisicion.material_id
        if mat_id:
            OrdenCompraArticulo.objects.filter(pk=linea.pk).update(material_id=mat_id)


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0083_add_moneda_req_to_requisicion'),
        ('activos', '0075_add_codigo_exoneracion_fk_categoria'),
        ('inventarios', '0046_solicitudmaterial_foto_entrega_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='requisicion',
            name='edificio',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requisiciones_edificio', to='activos.ubicacion', verbose_name='Edificio'),
        ),
        migrations.AddField(
            model_name='requisicion',
            name='nivel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requisiciones_nivel', to='activos.ubicacion', verbose_name='Nivel'),
        ),
        migrations.AddField(
            model_name='requisicion',
            name='ubicacion',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requisiciones_ubicacion', to='activos.ubicacion', verbose_name='Ubicación'),
        ),
        migrations.AddField(
            model_name='ordencompraarticulo',
            name='material',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ordenes_compra_articulos', to='inventarios.material', verbose_name='Material / Servicio'),
        ),
        migrations.RunPython(backfill_material_oc, migrations.RunPython.noop),
    ]
