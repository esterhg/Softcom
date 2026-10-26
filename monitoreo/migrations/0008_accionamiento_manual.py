import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('monitoreo', '0007_verificacion_alarma'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReporteAccionamiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('responsable_nombre_manual', models.CharField(blank=True, help_text='Usado si el responsable no está en el sistema.', max_length=200, verbose_name='Responsable (texto libre)')),
                ('fecha_hora', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha del reporte')),
                ('funciona', models.BooleanField(blank=True, help_text='Resultado global del accionamiento manual.', null=True, verbose_name='¿Funciona?')),
                ('observaciones_generales', models.TextField(blank=True, verbose_name='Notas / observaciones')),
                ('estado', models.CharField(choices=[('borrador', 'Borrador'), ('enviado', 'Enviado'), ('archivado', 'Archivado')], default='borrador', max_length=20, verbose_name='Estado')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('pdf_archivo', models.FileField(blank=True, null=True, upload_to='monitoreo/accionamiento/pdfs/', verbose_name='PDF generado')),
                ('creado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='accionamiento_creados', to=settings.AUTH_USER_MODEL, verbose_name='Creado por')),
                ('responsable', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='accionamiento_responsable', to=settings.AUTH_USER_MODEL, verbose_name='Responsable')),
            ],
            options={
                'verbose_name': 'Accionamiento Manual Mensual',
                'verbose_name_plural': 'Accionamientos Manuales Mensuales',
                'ordering': ['-fecha_hora'],
            },
        ),
        migrations.CreateModel(
            name='FilaAccionamiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('edificio', models.CharField(max_length=120, verbose_name='Edificio / zona')),
                ('revisado', models.BooleanField(default=True, verbose_name='Revisado (accionado)')),
                ('motivo', models.TextField(blank=True, help_text='Obligatorio cuando el edificio no se revisó.', verbose_name='Motivo')),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('reporte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='filas', to='monitoreo.reporteaccionamiento', verbose_name='Reporte')),
            ],
            options={
                'verbose_name': 'Fila de accionamiento',
                'verbose_name_plural': 'Filas de accionamiento',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.CreateModel(
            name='FotoAnexoAccionamiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(upload_to='monitoreo/accionamiento/fotos/', verbose_name='Imagen')),
                ('descripcion', models.CharField(blank=True, max_length=300, verbose_name='Descripción')),
                ('subido_en', models.DateTimeField(auto_now_add=True)),
                ('reporte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fotos', to='monitoreo.reporteaccionamiento', verbose_name='Reporte')),
                ('subido_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Subido por')),
            ],
            options={
                'verbose_name': 'Foto anexa (accionamiento)',
                'verbose_name_plural': 'Fotos anexas (accionamiento)',
                'ordering': ['subido_en'],
            },
        ),
    ]
