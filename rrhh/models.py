from django.conf import settings
from django.db import models


class CategoriaHoraExtra(models.Model):
    """Catálogo de categorías de hora extra (p. ej. nocturna, feriado)."""
    nombre = models.CharField(max_length=80, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría de hora extra'
        verbose_name_plural = 'Categorías de hora extra'

    def __str__(self):
        return self.nombre


class ReporteHoras(models.Model):
    """Reporte que agrupa las horas extra de un colaborador."""
    codigo = models.CharField('ID de reporte', max_length=20, unique=True, editable=False)
    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reportes_horas')
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reportes_horas_autorizados')
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reportes_horas_solicitados')
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Reporte de horas'
        verbose_name_plural = 'Reportes de horas'

    def __str__(self):
        return self.codigo


class HoraExtra(models.Model):
    """Registro de horas extra trabajadas, ligado a un reporte."""
    reporte = models.ForeignKey(
        ReporteHoras, on_delete=models.CASCADE, related_name='horas_extra')
    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='horas_extra')
    categoria = models.ForeignKey(
        CategoriaHoraExtra, on_delete=models.PROTECT, null=True, blank=True,
        related_name='horas_extra')
    entrada = models.DateTimeField()
    salida = models.DateTimeField()
    horas_total = models.DecimalField(max_digits=6, decimal_places=2, editable=False)
    cena = models.BooleanField(default=False)
    justificacion = models.TextField('Justificación (actividad realizada)')
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-entrada']
        verbose_name = 'Hora extra'
        verbose_name_plural = 'Horas extra'

    def __str__(self):
        return f'{self.colaborador} {self.entrada:%d/%m/%Y} ({self.horas_total} h)'
