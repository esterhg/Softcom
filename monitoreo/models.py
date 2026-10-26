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
        Elevador, on_delete=models.CASCADE,
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


# ═══════════════════════════════════════════════════════════════════
#  VERIFICACIÓN DE ELEVADORES — ALARMA E INTERCOMUNICADOR
#  Checklist OCC-INST-FOR-0X_INSPECCION_ELEVADORES
#  Cada elemento se verifica por elevador. Todos marcados OK por
#  defecto; al desmarcar un ítem se registra el motivo en "hallazgos".
# ═══════════════════════════════════════════════════════════════════

class ReporteVerificacionAlarma(models.Model):
    """Checklist de verificación de alarma, intercomunicador, luz
    indicadora y etiquetado de los elevadores (formato OCC)."""
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('archivado', 'Archivado'),
    ]

    responsable = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verif_alarma_responsable',
        verbose_name="Responsable OCC",
    )
    responsable_nombre_manual = models.CharField(
        max_length=200, blank=True,
        verbose_name="Responsable OCC (texto libre)",
        help_text="Usado si el responsable no está en el sistema.",
    )
    elaborado_por = models.CharField(
        max_length=200, blank=True,
        verbose_name="Elaborado por",
    )
    edificio = models.CharField(
        max_length=200, blank=True,
        verbose_name="Edificio",
    )
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name="Fecha y hora del reporte")
    observaciones_generales = models.TextField(
        blank=True, verbose_name="Comentarios y observaciones adicionales")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador', verbose_name="Estado")
    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='verif_alarma_creados',
        verbose_name="Creado por",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    pdf_archivo = models.FileField(
        upload_to='monitoreo/verif_alarma/pdfs/',
        null=True, blank=True,
        verbose_name="PDF generado",
    )

    class Meta:
        verbose_name = "Verificación de Elevadores (Alarma/Intercom.)"
        verbose_name_plural = "Verificaciones de Elevadores (Alarma/Intercom.)"
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"Verificación #{self.pk} — {self.fecha_hora.strftime('%d/%m/%Y %H:%M')}"

    @property
    def responsable_display(self):
        if self.responsable:
            return self.responsable.get_full_name() or self.responsable.username
        return self.responsable_nombre_manual or "—"


class FilaVerificacionAlarma(models.Model):
    """Una fila del checklist: verificación de un elevador.

    Cada campo booleano representa un elemento de verificación y se marca
    como True (correcto) por defecto. Si algún elemento está en False se
    debe registrar el motivo en `hallazgos`.
    """
    reporte = models.ForeignKey(
        ReporteVerificacionAlarma, on_delete=models.CASCADE,
        related_name='filas',
        verbose_name="Reporte",
    )
    elevador = models.ForeignKey(
        Elevador, on_delete=models.CASCADE,
        verbose_name="Elevador",
    )

    # ── Elementos de verificación (True = correcto / marcado) ──
    etiqueta_interna = models.BooleanField(
        default=True, verbose_name="Etiqueta identif. interna")
    alarma_suena = models.BooleanField(
        default=True, verbose_name="Alarma suena")
    luz_enciende = models.BooleanField(
        default=True, verbose_name="Luz indicadora enciende")
    parlante_suena = models.BooleanField(
        default=True, verbose_name="Parlante suena")
    telefono_etiqueta = models.BooleanField(
        default=True, verbose_name="Teléfono etiquetado")
    telefono_suena = models.BooleanField(
        default=True, verbose_name="Teléfono suena")

    hallazgos = models.TextField(
        blank=True,
        verbose_name="Hallazgos",
        help_text="Motivo / explicación cuando algún elemento no cumple.")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Fila de verificación"
        verbose_name_plural = "Filas de verificación"
        ordering = ['orden', 'elevador__orden']
        unique_together = [('reporte', 'elevador')]

    def __str__(self):
        return f"{self.elevador.nombre} — Verificación #{self.reporte_id}"

    # Lista canónica de (atributo, etiqueta) para iterar en plantillas/PDF
    ELEMENTOS = [
        ('etiqueta_interna',  'Etiqueta identif. interna'),
        ('alarma_suena',      'Alarma'),
        ('luz_enciende',      'Luz indicadora'),
        ('parlante_suena',    'Parlante'),
        ('telefono_etiqueta', 'Teléfono (etiqueta)'),
        ('telefono_suena',    'Teléfono (suena)'),
    ]

    @property
    def tiene_hallazgos(self):
        """True si algún elemento de verificación no cumple."""
        return not all([
            self.etiqueta_interna, self.alarma_suena, self.luz_enciende,
            self.parlante_suena, self.telefono_etiqueta, self.telefono_suena,
        ])

    @property
    def elementos_no_cumplen(self):
        """Lista de etiquetas de los elementos marcados como No."""
        return [lbl for attr, lbl in self.ELEMENTOS if not getattr(self, attr)]

    @property
    def total_ok(self):
        return sum(1 for attr, _ in self.ELEMENTOS if getattr(self, attr))


class FotoAnexoVerificacionAlarma(models.Model):
    """Foto adjunta a un reporte de verificación de alarma/intercom."""
    reporte = models.ForeignKey(
        ReporteVerificacionAlarma, on_delete=models.CASCADE,
        related_name='fotos',
        verbose_name="Reporte",
    )
    imagen = models.ImageField(
        upload_to='monitoreo/verif_alarma/fotos/',
        verbose_name="Imagen",
    )
    descripcion = models.CharField(max_length=300, blank=True, verbose_name="Descripción")
    subido_en = models.DateTimeField(auto_now_add=True)
    subido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        verbose_name="Subido por",
    )

    class Meta:
        verbose_name = "Foto anexa (verificación)"
        verbose_name_plural = "Fotos anexas (verificación)"
        ordering = ['subido_en']

    def __str__(self):
        return f"Foto #{self.pk} — Verificación #{self.reporte_id}"


# ═══════════════════════════════════════════════════════════════════
#  ACCIONAMIENTO MANUAL MENSUAL
#  Reporte mensual del accionamiento manual de los elevadores por
#  edificio / zona. Cada edificio se marca como "revisado" (accionado)
#  o no; si no se revisó, se registra el motivo (obligatorio).
#  Incluye un resultado global ¿Funciona? Sí/No, foto y notas.
# ═══════════════════════════════════════════════════════════════════

class ReporteAccionamiento(models.Model):
    """Reporte mensual de accionamiento manual de elevadores."""
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('archivado', 'Archivado'),
    ]

    responsable = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='accionamiento_responsable',
        verbose_name="Responsable",
    )
    responsable_nombre_manual = models.CharField(
        max_length=200, blank=True,
        verbose_name="Responsable (texto libre)",
        help_text="Usado si el responsable no está en el sistema.",
    )
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name="Fecha del reporte")
    funciona = models.BooleanField(
        null=True, blank=True,
        verbose_name="¿Funciona?",
        help_text="Resultado global del accionamiento manual.",
    )
    observaciones_generales = models.TextField(blank=True, verbose_name="Notas / observaciones")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador', verbose_name="Estado")
    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='accionamiento_creados',
        verbose_name="Creado por",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    pdf_archivo = models.FileField(
        upload_to='monitoreo/accionamiento/pdfs/',
        null=True, blank=True,
        verbose_name="PDF generado",
    )

    class Meta:
        verbose_name = "Accionamiento Manual Mensual"
        verbose_name_plural = "Accionamientos Manuales Mensuales"
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"Accionamiento #{self.pk} — {self.fecha_hora.strftime('%d/%m/%Y')}"

    @property
    def responsable_display(self):
        if self.responsable:
            return self.responsable.get_full_name() or self.responsable.username
        return self.responsable_nombre_manual or "—"

    @property
    def funciona_display(self):
        if self.funciona is True:
            return "Sí"
        if self.funciona is False:
            return "No"
        return "Sin indicar"

    @property
    def total_revisados(self):
        return sum(1 for f in self.filas.all() if f.revisado)

    @property
    def total_edificios(self):
        return self.filas.count()


class FilaAccionamiento(models.Model):
    """Una fila del reporte: estado de accionamiento de un edificio / zona."""
    reporte = models.ForeignKey(
        ReporteAccionamiento, on_delete=models.CASCADE,
        related_name='filas',
        verbose_name="Reporte",
    )
    edificio = models.CharField(max_length=120, verbose_name="Edificio / zona")
    revisado = models.BooleanField(default=True, verbose_name="Revisado (accionado)")
    motivo = models.TextField(
        blank=True,
        verbose_name="Motivo",
        help_text="Obligatorio cuando el edificio no se revisó.")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Fila de accionamiento"
        verbose_name_plural = "Filas de accionamiento"
        ordering = ['orden', 'id']

    def __str__(self):
        return f"{self.edificio} — {'Revisado' if self.revisado else 'No revisado'}"


class FotoAnexoAccionamiento(models.Model):
    """Foto adjunta a un reporte de accionamiento manual mensual."""
    reporte = models.ForeignKey(
        ReporteAccionamiento, on_delete=models.CASCADE,
        related_name='fotos',
        verbose_name="Reporte",
    )
    imagen = models.ImageField(
        upload_to='monitoreo/accionamiento/fotos/',
        verbose_name="Imagen",
    )
    descripcion = models.CharField(max_length=300, blank=True, verbose_name="Descripción")
    subido_en = models.DateTimeField(auto_now_add=True)
    subido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        verbose_name="Subido por",
    )

    class Meta:
        verbose_name = "Foto anexa (accionamiento)"
        verbose_name_plural = "Fotos anexas (accionamiento)"
        ordering = ['subido_en']

    def __str__(self):
        return f"Foto #{self.pk} — Accionamiento #{self.reporte_id}"
