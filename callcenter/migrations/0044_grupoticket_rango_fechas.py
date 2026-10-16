# Generated manually: add fecha_inicio / fecha_fin range to GrupoTicket

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('callcenter', '0043_auto_sync_dashboard'),
    ]

    operations = [
        migrations.AddField(
            model_name='grupoticket',
            name='fecha_inicio',
            field=models.DateField(blank=True, help_text='Fecha de solicitud inicial de los tickets incluidos en el cluster', null=True, verbose_name='Rango: Fecha Inicio'),
        ),
        migrations.AddField(
            model_name='grupoticket',
            name='fecha_fin',
            field=models.DateField(blank=True, help_text='Fecha de solicitud final de los tickets incluidos en el cluster', null=True, verbose_name='Rango: Fecha Fin'),
        ),
    ]
