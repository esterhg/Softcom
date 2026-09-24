import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # Elevador                                                             #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='Elevador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, verbose_name='Nombre / Identificador')),
                ('codigo', models.CharField(max_length=30, unique=True, verbose_name='Código interno')),
                ('ubicacion', models.CharField(blank=True, max_length=200, verbose_name='Ubicación')),
                ('descripcion', models.TextField(blank=True, verbose_name='Descripción')),
                ('activo', models.BooleanField(default=True, verbose_name='Activo')),
                ('orden', models.PositiveSmallIntegerField(default=0, verbose_name='Orden de visualización')),
            ],
            options={
                'verbose_name': 'Elevador',
                'verbose_name_plural': 'Elevadores',
                'ordering': ['orden', 'nombre'],
            },
        ),
        # ------------------------------------------------------------------ #
        # ReporteElevador                                                      #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='ReporteElevador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supervisor_nombre_manual', models.CharField(
                    blank=True, max_length=200,
                    verbose_name='Supervisor (texto libre)',
                    help_text='Usado si el supervisor no está en el sistema.',
                )),
                ('tecnico_nombre_manual', models.CharField(
                    blank=True, max_length=200,
                    verbose_name='Técnico (texto libre)',
                )),
                ('fecha_hora', models.DateTimeField(
                    default=django.utils.timezone.now,
                    verbose_name='Fecha y hora del reporte',
                )),
                ('observaciones_generales', models.TextField(blank=True, verbose_name='Observaciones generales')),
                ('estado', models.CharField(
                    choices=[
                        ('borrador', 'Borrador'),
                        ('enviado', 'Enviado'),
                        ('archivado', 'Archivado'),
                    ],
                    default='borrador',
                    max_length=20,
                    verbose_name='Estado',
                )),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('pdf_archivo', models.FileField(
                    blank=True, null=True,
                    upload_to='monitoreo/reportes/pdfs/',
                    verbose_name='PDF generado',
                )),
                ('imagen_archivo', models.FileField(
                    blank=True, null=True,
                    upload_to='monitoreo/reportes/imagenes/',
                    verbose_name='Imagen generada',
                )),
                ('supervisor', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reportes_elevadores_supervisados',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Supervisor OCC',
                )),
                ('tecnico', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reportes_elevadores_tecnicos',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Técnico responsable',
                )),
                ('creado_por', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reportes_elevadores_creados',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Creado por',
                )),
            ],
            options={
                'verbose_name': 'Reporte de Elevadores',
                'verbose_name_plural': 'Reportes de Elevadores',
                'ordering': ['-fecha_hora'],
            },
        ),
        # ------------------------------------------------------------------ #
        # FilaReporteElevador                                                  #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='FilaReporteElevador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(
                    choices=[
                        ('operativo', 'Operativo'),
                        ('fuera_servicio', 'Fuera de Servicio'),
                        ('en_mantenimiento', 'En Mantenimiento'),
                        ('falla_parcial', 'Falla Parcial'),
                        ('sin_novedad', 'Sin Novedad'),
                    ],
                    default='operativo',
                    max_length=30,
                    verbose_name='Estado',
                )),
                ('clasificacion', models.CharField(
                    blank=True,
                    choices=[
                        ('', '—'),
                        ('mecanica', 'Mecánica'),
                        ('electrica', 'Eléctrica'),
                        ('electronica', 'Electrónica'),
                        ('hidraulica', 'Hidráulica'),
                        ('externa', 'Externa'),
                        ('n_a', 'N/A'),
                    ],
                    default='',
                    max_length=30,
                    verbose_name='Clasificación',
                )),
                ('descripcion_novedad', models.TextField(blank=True, verbose_name='Descripción de la novedad')),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('reporte', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='filas',
                    to='monitoreo.reporteelevador',
                    verbose_name='Reporte',
                )),
                ('elevador', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='monitoreo.elevador',
                    verbose_name='Elevador',
                )),
            ],
            options={
                'verbose_name': 'Fila de reporte',
                'verbose_name_plural': 'Filas de reporte',
                'ordering': ['orden', 'elevador__orden'],
                'unique_together': {('reporte', 'elevador')},
            },
        ),
        # ------------------------------------------------------------------ #
        # FotoAnexoReporte                                                     #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='FotoAnexoReporte',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(upload_to='monitoreo/reportes/fotos/', verbose_name='Imagen')),
                ('descripcion', models.CharField(blank=True, max_length=300, verbose_name='Descripción')),
                ('subido_en', models.DateTimeField(auto_now_add=True)),
                ('reporte', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fotos',
                    to='monitoreo.reporteelevador',
                    verbose_name='Reporte',
                )),
                ('subido_por', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Subido por',
                )),
            ],
            options={
                'verbose_name': 'Foto anexa',
                'verbose_name_plural': 'Fotos anexas',
                'ordering': ['subido_en'],
            },
        ),
    ]
