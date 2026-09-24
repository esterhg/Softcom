from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Elevador(models.Model):
    """Representa un elevador físico del edificio."""
    nombre = models.CharField(max_length=100, verbose_name="Nombre / Identificador")
    codigo = models.CharField(max_length=30, unique=True, verbose_name="Código interno")
    ubicacion = models.CharField(max_length=200, blank=True, verbose_name="Ubicación")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    orden = models.PositiveSmallIntegerField(default=0, verbose_name="Orden de visualización")

    class Meta:
        verbose_name = "Elevador"
        verbose_name_plural = "Elevadores"
        ordering = ['orden', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class ReporteElevador(models.Model):
    """Reporte de monitoreo diario / por turno de todos los elevadores."""
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('archivado', 'Archivado'),
    ]

    supervisor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reportes_elevadores_supervisados',
        verbose_name="Supervisor OCC",
    )
    supervisor_nombre_manual = models.CharField(
        max_length=200, blank=True,
        verbose_name="Supervisor (texto libre)",
        help_text="Usado si el supervisor no está en el sistema.",
    )
    tecnico = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reportes_elevadores_tecnicos',
        verbose_name="Técnico responsable",
    )
    tecnico_nombre_manual = models.CharField(
        max_length=200, blank=True,
        verbose_name="Técnico (texto libre)",
    )
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name="Fecha y hora del reporte")
    observaciones_generales = models.TextField(blank=True, verbose_name="Observaciones generales")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador', verbose_name="Estado")
    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='reportes_elevadores_creados',
        verbose_name="Creado por",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    # PDF generado y guardado
    pdf_archivo = models.FileField(
        upload_to='monitoreo/reportes/pdfs/',
        null=True, blank=True,
        verbose_name="PDF generado",
    )
    imagen_archivo = models.FileField(
        upload_to='monitoreo/reportes/imagenes/',
        null=True, blank=True,
        verbose_name="Imagen generada",
    )

    class Meta:
        verbose_name = "Reporte de Elevadores"
        verbose_name_plural = "Reportes de Elevadores"
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"Reporte #{self.pk} — {self.fecha_hora.strftime('%d/%m/%Y %H:%M')}"

    @property
    def supervisor_display(self):
        if self.supervisor:
            return self.supervisor.get_full_name() or self.supervisor.username
        return self.supervisor_nombre_manual or "—"

    @property
    def tecnico_display(self):
        if self.tecnico:
            return self.tecnico.get_full_name() or self.tecnico.username
        return self.tecnico_nombre_manual or "—"


class FilaReporteElevador(models.Model):
    """Una fila de la tabla del reporte: estado de un elevador en este reporte."""
    ESTADO_CHOICES = [
        ('operativo', 'Operativo'),
        ('fuera_servicio', 'Fuera de Servicio'),
        ('en_mantenimiento', 'En Mantenimiento'),
        ('falla_parcial', 'Falla Parcial'),
        ('sin_novedad', 'Sin Novedad'),
    ]
    CLASIFICACION_CHOICES = [
        ('', '—'),
        ('mecanica', 'Mecánica'),
        ('electrica', 'Eléctrica'),
        ('electronica', 'Electrónica'),
        ('hidraulica', 'Hidráulica'),
        ('externa', 'Externa'),
        ('n_a', 'N/A'),
    ]

    reporte = models.ForeignKey(
        ReporteElevador, on_delete=models.CASCADE,
        related_name='filas',
        verbose_name="Reporte",
    )
    elevador = models.ForeignKey(
        Elevador, on_delete=models.PROTECT,
        verbose_name="Elevador",
    )
    estado = models.CharField(
        max_length=30, choices=ESTADO_CHOICES, default='operativo',
        verbose_name="Estado",
    )
    clasificacion = models.CharField(
        max_length=30, choices=CLASIFICACION_CHOICES, blank=True, default='',
        verbose_name="Clasificación",
    )
    descripcion_novedad = models.TextField(blank=True, verbose_name="Descripción de la novedad")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Fila de reporte"
        verbose_name_plural = "Filas de reporte"
        ordering = ['orden', 'elevador__orden']
        unique_together = [('reporte', 'elevador')]

    def __str__(self):
        return f"{self.elevador.nombre} — {self.get_estado_display()}"

    @property
    def estado_badge_class(self):
        mapping = {
            'operativo': 'badge-operativo',
            'fuera_servicio': 'badge-fuera',
            'en_mantenimiento': 'badge-mantenimiento',
            'falla_parcial': 'badge-falla',
            'sin_novedad': 'badge-sin-novedad',
        }
        return mapping.get(self.estado, '')


class FotoAnexoReporte(models.Model):
    """Foto adjunta a un reporte de elevadores."""
    reporte = models.ForeignKey(
        ReporteElevador, on_delete=models.CASCADE,
        related_name='fotos',
        verbose_name="Reporte",
    )
    imagen = models.ImageField(
        upload_to='monitoreo/reportes/fotos/',
        verbose_name="Imagen",
    )
    descripcion = models.CharField(max_length=300, blank=True, verbose_name="Descripción")
    subido_en = models.DateTimeField(auto_now_add=True)
    subido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        verbose_name="Subido por",
    )

    class Meta:
        verbose_name = "Foto anexa"
        verbose_name_plural = "Fotos anexas"
        ordering = ['subido_en']

    def __str__(self):
        return f"Foto #{self.pk} — Reporte #{self.reporte_id}"
