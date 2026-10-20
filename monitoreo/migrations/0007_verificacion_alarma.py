import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('monitoreo', '0006_filareporteelevador_cascade'),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # ReporteVerificacionAlarma                                           #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='ReporteVerificacionAlarma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('responsable_nombre_manual', models.CharField(blank=True, help_text='Usado si el responsable no está en el sistema.', max_length=200, verbose_name='Responsable OCC (texto libre)')),
                ('elaborado_por', models.CharField(blank=True, max_length=200, verbose_name='Elaborado por')),
                ('edificio', models.CharField(blank=True, max_length=200, verbose_name='Edificio')),
                ('fecha_hora', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha y hora del reporte')),
                ('observaciones_generales', models.TextField(blank=True, verbose_name='Comentarios y observaciones adicionales')),
                ('estado', models.CharField(choices=[('borrador', 'Borrador'), ('enviado', 'Enviado'), ('archivado', 'Archivado')], default='borrador', max_length=20, verbose_name='Estado')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('pdf_archivo', models.FileField(blank=True, null=True, upload_to='monitoreo/verif_alarma/pdfs/', verbose_name='PDF generado')),
                ('creado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verif_alarma_creados', to=settings.AUTH_USER_MODEL, verbose_name='Creado por')),
                ('responsable', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verif_alarma_responsable', to=settings.AUTH_USER_MODEL, verbose_name='Responsable OCC')),
            ],
            options={
                'verbose_name': 'Verificación de Elevadores (Alarma/Intercom.)',
                'verbose_name_plural': 'Verificaciones de Elevadores (Alarma/Intercom.)',
                'ordering': ['-fecha_hora'],
            },
        ),
        # ------------------------------------------------------------------ #
        # FilaVerificacionAlarma                                              #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='FilaVerificacionAlarma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etiqueta_interna', models.BooleanField(default=True, verbose_name='Etiqueta identif. interna')),
                ('alarma_suena', models.BooleanField(default=True, verbose_name='Alarma suena')),
                ('luz_enciende', models.BooleanField(default=True, verbose_name='Luz indicadora enciende')),
                ('parlante_suena', models.BooleanField(default=True, verbose_name='Parlante suena')),
                ('telefono_etiqueta', models.BooleanField(default=True, verbose_name='Teléfono etiquetado')),
                ('telefono_suena', models.BooleanField(default=True, verbose_name='Teléfono suena')),
                ('hallazgos', models.TextField(blank=True, help_text='Motivo / explicación cuando algún elemento no cumple.', verbose_name='Hallazgos')),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('elevador', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='monitoreo.elevador', verbose_name='Elevador')),
                ('reporte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='filas', to='monitoreo.reporteverificacionalarma', verbose_name='Reporte')),
            ],
            options={
                'verbose_name': 'Fila de verificación',
                'verbose_name_plural': 'Filas de verificación',
                'ordering': ['orden', 'elevador__orden'],
                'unique_together': {('reporte', 'elevador')},
            },
        ),
        # ------------------------------------------------------------------ #
        # FotoAnexoVerificacionAlarma                                         #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='FotoAnexoVerificacionAlarma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(upload_to='monitoreo/verif_alarma/fotos/', verbose_name='Imagen')),
                ('descripcion', models.CharField(blank=True, max_length=300, verbose_name='Descripción')),
                ('subido_en', models.DateTimeField(auto_now_add=True)),
                ('reporte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fotos', to='monitoreo.reporteverificacionalarma', verbose_name='Reporte')),
                ('subido_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Subido por')),
            ],
            options={
                'verbose_name': 'Foto anexa (verificación)',
                'verbose_name_plural': 'Fotos anexas (verificación)',
                'ordering': ['subido_en'],
            },
        ),
    ]
