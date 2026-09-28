from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('monitoreo', '0005_elevadores_actualizados'),
    ]

    operations = [
        migrations.AlterField(
            model_name='filareporteelevador',
            name='elevador',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to='monitoreo.elevador',
                verbose_name='Elevador',
            ),
        ),
    ]
