import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('monitoreo', '0008_accionamiento_manual'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReporteAveria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(blank=True, db_index=True, max_length=20, null=True, unique=True, verbose_name='Correlativo')),
                ('fecha_hora', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha y hora de la avería')),
                ('reportado_por_nombre', models.CharField(blank=True, help_text='Quien detectó o avisó la avería.', max_length=200, verbose_name='Reportado por (texto libre)')),
                ('prioridad', models.CharField(choices=[('baja', 'Baja'), ('media', 'Media'), ('alta', 'Alta'), ('critica', 'Crítica')], db_index=True, default='media', max_length=10)),
                ('clasificacion', models.CharField(blank=True, choices=[('', '—'), ('mecanica', 'Mecánica'), ('electrica', 'Eléctrica'), ('electronica', 'Electrónica'), ('hidraulica', 'Hidráulica'), ('externa', 'Externa'), ('n_a', 'N/A')], default='', max_length=30)),
                ('equipo_parado', models.BooleanField(default=False, verbose_name='¿Elevador fuera de servicio?')),
                ('descripcion', models.TextField(verbose_name='Descripción de la avería')),
                ('fecha_asignacion', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de asignación')),
                ('diagnostico', models.TextField(blank=True, verbose_name='Diagnóstico')),
                ('acciones_realizadas', models.TextField(blank=True, verbose_name='Acciones realizadas')),
                ('fecha_resolucion', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de resolución')),
                ('estado', models.CharField(choices=[('abierta', 'Abierta'), ('asignada', 'Asignada'), ('en_proceso', 'En proceso'), ('resuelta', 'Resuelta'), ('cancelada', 'Cancelada')], db_index=True, default='abierta', max_length=15)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('asignado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='averias_elevador_asignadas_por', to=settings.AUTH_USER_MODEL, verbose_name='Asignado por')),
                ('creado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='averias_elevador_creadas', to=settings.AUTH_USER_MODEL, verbose_name='Creado por')),
                ('elevador', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='averias', to='monitoreo.elevador', verbose_name='Elevador')),
                ('tecnico_principal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='averias_elevador_lider', to=settings.AUTH_USER_MODEL, verbose_name='Técnico responsable')),
                ('tecnicos', models.ManyToManyField(blank=True, related_name='averias_elevador_apoyo', to=settings.AUTH_USER_MODEL, verbose_name='Técnicos de apoyo')),
            ],
            options={
                'verbose_name': 'Reporte de Avería',
                'verbose_name_plural': 'Reportes de Avería',
                'ordering': ['-fecha_hora', '-id'],
            },
        ),
        migrations.CreateModel(
            name='FotoAveria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(upload_to='monitoreo/averias/fotos/', verbose_name='Imagen')),
                ('descripcion', models.CharField(blank=True, max_length=300, verbose_name='Descripción')),
                ('subido_en', models.DateTimeField(auto_now_add=True)),
                ('averia', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fotos', to='monitoreo.reporteaveria', verbose_name='Avería')),
                ('subido_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Subido por')),
            ],
            options={
                'verbose_name': 'Foto de avería',
                'verbose_name_plural': 'Fotos de avería',
                'ordering': ['subido_en'],
            },
        ),
    ]
