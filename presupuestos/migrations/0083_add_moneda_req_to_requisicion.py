from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0082_configuracionflujoaprobacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='requisicion',
            name='moneda_req',
            field=models.ForeignKey(
                blank=True,
                help_text='Moneda en la que se expresan los montos de esta requisición (Lempiras o Dólares).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='requisiciones_directas',
                to='presupuestos.moneda',
                verbose_name='Moneda',
            ),
        ),
    ]
