import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activos', '0075_add_codigo_exoneracion_fk_categoria'),
        ('monitoreo', '0010_menu_averias'),
    ]

    operations = [
        migrations.AddField(
            model_name='reporteaveria',
            name='activo',
            field=models.ForeignKey(help_text='Equipo (elevador) con la avería.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='averias_elevador', to='activos.activo', verbose_name='Activo'),
        ),
        migrations.AddField(
            model_name='reporteaveria',
            name='unidad_funcional',
            field=models.ForeignKey(blank=True, help_text='Se toma automáticamente de la ubicación del activo.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='averias_elevador', to='activos.ubicacion', verbose_name='Unidad funcional'),
        ),
        migrations.AlterField(
            model_name='reporteaveria',
            name='elevador',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='averias', to='monitoreo.elevador', verbose_name='Elevador (catálogo monitoreo)'),
        ),
        migrations.AddField(
            model_name='reporteaveria',
            name='materiales_utilizados',
            field=models.TextField(blank=True, verbose_name='Materiales / repuestos utilizados'),
        ),
        migrations.AddField(
            model_name='reporteaveria',
            name='operativo_salida',
            field=models.BooleanField(blank=True, null=True, verbose_name='¿Quedó operativo?'),
        ),
        migrations.AddField(
            model_name='reporteaveria',
            name='fecha_inicio',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Inicio de atención'),
        ),
        migrations.AddField(
            model_name='reporteaveria',
            name='resuelto_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='averias_elevador_resueltas', to=settings.AUTH_USER_MODEL, verbose_name='Resuelto por'),
        ),
    ]
