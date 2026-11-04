from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mantenimiento', '0094_ot_firmas_cierre'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordentrabajo',
            name='fecha_finalizacion',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Fecha de finalización'),
        ),
    ]
