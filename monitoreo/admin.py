from django.contrib import admin
from django.db.models import ProtectedError
from django.utils.html import format_html
from .models import (
    Elevador, ReporteElevador, FilaReporteElevador, FotoAnexoReporte,
    ReporteVerificacionAlarma, FilaVerificacionAlarma, FotoAnexoVerificacionAlarma,
    ReporteAccionamiento, FilaAccionamiento, FotoAnexoAccionamiento,
    ReporteAveria, FotoAveria,
)


@admin.register(Elevador)
class ElevadorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'ubicacion', 'activo', 'orden', 'reportes_asociados')
    list_editable = ('activo', 'orden')
    search_fields = ('nombre', 'codigo', 'ubicacion')
    list_filter = ('activo',)
    ordering = ('orden', 'nombre')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    def reportes_asociados(self, obj):
        count = FilaReporteElevador.objects.filter(elevador=obj).count()
        if count:
            return format_html(
                '<span style="color:#bb0000;font-weight:600;">{} reporte{}</span>',
                count, 's' if count != 1 else '',
            )
        return format_html('<span style="color:#107e3e;">0 reportes</span>')
    reportes_asociados.short_description = 'Reportes'

    def delete_model(self, request, obj):
        try:
            obj.delete()
        except ProtectedError:
            count = FilaReporteElevador.objects.filter(elevador=obj).count()
            self.message_user(
                request,
                f'No se puede eliminar "{obj}" porque está referenciado en {count} '
                f'reporte{"s" if count != 1 else ""}. '
                f'Elimine primero esos reportes o reasigne las filas.',
                level='error',
            )

    def delete_queryset(self, request, queryset):
        protected = []
        deleted = 0
        for obj in queryset:
            try:
                obj.delete()
                deleted += 1
            except ProtectedError:
                count = FilaReporteElevador.objects.filter(elevador=obj).count()
                protected.append(f'"{obj}" ({count} reporte{"s" if count != 1 else ""})')

        if deleted:
            self.message_user(
                request,
                f'{deleted} elevador{"es eliminados" if deleted != 1 else " eliminado"} correctamente.',
            )
        if protected:
            self.message_user(
                request,
                'No se pudieron eliminar los siguientes elevadores porque tienen reportes asociados: '
                + ', '.join(protected) + '. Elimine primero esos reportes.',
                level='error',
            )


class FilaInline(admin.TabularInline):
    model = FilaReporteElevador
    extra = 0
    fields = ('elevador', 'estado', 'clasificacion', 'descripcion_novedad', 'orden')
    ordering = ('orden',)


class FotoInline(admin.TabularInline):
    model = FotoAnexoReporte
    extra = 0
    fields = ('imagen', 'descripcion', 'subido_en')
    readonly_fields = ('subido_en',)


@admin.register(ReporteElevador)
class ReporteElevadorAdmin(admin.ModelAdmin):
    list_display = (
        'pk', 'fecha_hora', 'supervisor_display', 'tecnico_display',
        'conteo_elevadores', 'estado', 'creado_en',
    )
    list_filter = ('estado', 'fecha_hora')
    search_fields = (
        'supervisor__first_name', 'supervisor__last_name',
        'supervisor_nombre_manual', 'tecnico_nombre_manual',
    )
    readonly_fields = ('creado_por', 'creado_en', 'actualizado_en')
    inlines = [FilaInline, FotoInline]
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)

    def supervisor_display(self, obj):
        return obj.supervisor_display
    supervisor_display.short_description = 'Supervisor'

    def tecnico_display(self, obj):
        return obj.tecnico_display
    tecnico_display.short_description = 'Técnico'

    def conteo_elevadores(self, obj):
        n = obj.filas.count()
        return format_html('<span>{} elevador{}</span>', n, 'es' if n != 1 else '')
    conteo_elevadores.short_description = 'Elevadores'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


# ═══════════════════════════════════════════════════════════════════
#  VERIFICACIÓN DE ELEVADORES — ALARMA E INTERCOMUNICADOR
# ═══════════════════════════════════════════════════════════════════

class FilaVerificacionInline(admin.TabularInline):
    model = FilaVerificacionAlarma
    extra = 0
    fields = (
        'elevador', 'etiqueta_interna', 'alarma_suena', 'luz_enciende',
        'parlante_suena', 'telefono_etiqueta', 'telefono_suena',
        'hallazgos', 'orden',
    )
    ordering = ('orden',)


class FotoVerificacionInline(admin.TabularInline):
    model = FotoAnexoVerificacionAlarma
    extra = 0
    fields = ('imagen', 'descripcion', 'subido_en')
    readonly_fields = ('subido_en',)


@admin.register(ReporteVerificacionAlarma)
class ReporteVerificacionAlarmaAdmin(admin.ModelAdmin):
    list_display = (
        'pk', 'fecha_hora', 'responsable_display', 'edificio',
        'conteo_elevadores', 'conteo_hallazgos', 'estado', 'creado_en',
    )
    list_filter = ('estado', 'fecha_hora')
    search_fields = (
        'responsable__first_name', 'responsable__last_name',
        'responsable_nombre_manual', 'elaborado_por', 'edificio',
    )
    readonly_fields = ('creado_por', 'creado_en', 'actualizado_en')
    inlines = [FilaVerificacionInline, FotoVerificacionInline]
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)

    def responsable_display(self, obj):
        return obj.responsable_display
    responsable_display.short_description = 'Responsable'

    def conteo_elevadores(self, obj):
        n = obj.filas.count()
        return format_html('<span>{} elevador{}</span>', n, 'es' if n != 1 else '')
    conteo_elevadores.short_description = 'Elevadores'

    def conteo_hallazgos(self, obj):
        n = sum(1 for f in obj.filas.all() if f.tiene_hallazgos)
        if n:
            return format_html('<span style="color:#bb0000;font-weight:600;">{} con hallazgos</span>', n)
        return format_html('<span style="color:#107e3e;">Sin hallazgos</span>')
    conteo_hallazgos.short_description = 'Hallazgos'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


# ═══════════════════════════════════════════════════════════════════
#  ACCIONAMIENTO MANUAL MENSUAL
# ═══════════════════════════════════════════════════════════════════

class FilaAccionamientoInline(admin.TabularInline):
    model = FilaAccionamiento
    extra = 0
    fields = ('edificio', 'revisado', 'motivo', 'orden')
    ordering = ('orden',)


class FotoAccionamientoInline(admin.TabularInline):
    model = FotoAnexoAccionamiento
    extra = 0
    fields = ('imagen', 'descripcion', 'subido_en')
    readonly_fields = ('subido_en',)


@admin.register(ReporteAccionamiento)
class ReporteAccionamientoAdmin(admin.ModelAdmin):
    list_display = (
        'pk', 'fecha_hora', 'responsable_display', 'conteo_edificios',
        'funciona_display', 'estado', 'creado_en',
    )
    list_filter = ('estado', 'funciona', 'fecha_hora')
    search_fields = (
        'responsable__first_name', 'responsable__last_name',
        'responsable_nombre_manual', 'observaciones_generales',
    )
    readonly_fields = ('creado_por', 'creado_en', 'actualizado_en')
    inlines = [FilaAccionamientoInline, FotoAccionamientoInline]
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)

    def responsable_display(self, obj):
        return obj.responsable_display
    responsable_display.short_description = 'Responsable'

    def funciona_display(self, obj):
        return obj.funciona_display
    funciona_display.short_description = '¿Funciona?'

    def conteo_edificios(self, obj):
        rev = obj.total_revisados
        tot = obj.total_edificios
        return format_html('<span>{} / {} revisados</span>', rev, tot)
    conteo_edificios.short_description = 'Edificios'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


class FotoAveriaInline(admin.TabularInline):
    model = FotoAveria
    extra = 0
    fields = ('imagen', 'descripcion', 'subido_por', 'subido_en')
    readonly_fields = ('subido_por', 'subido_en')


@admin.register(ReporteAveria)
class ReporteAveriaAdmin(admin.ModelAdmin):
    """El supervisor crea la avería aquí y la asigna a los técnicos.
    El técnico la ve y la resuelve desde /app/ (Mis Averías)."""
    list_display = ('codigo', 'activo', 'unidad_funcional_col', 'prioridad_badge_col',
                    'estado_badge_col', 'tecnico_principal', 'fecha_hora')
    list_display_links = ('codigo', 'activo')
    list_filter = ('estado', 'prioridad', 'equipo_parado', 'tecnico_principal')
    search_fields = ('codigo', 'descripcion', 'activo__nombre', 'activo__codigo_interno',
                     'unidad_funcional__nombre')
    list_select_related = ('activo', 'unidad_funcional', 'tecnico_principal')
    autocomplete_fields = ('activo', 'tecnico_principal', 'tecnicos')
    readonly_fields = ('codigo', 'unidad_funcional_ruta', 'fecha_asignacion', 'asignado_por',
                       'resuelto_por',
                       'creado_por', 'creado_en', 'actualizado_en')
    date_hierarchy = 'fecha_hora'
    inlines = [FotoAveriaInline]
    fieldsets = (
        ('Avería', {
            'fields': ('codigo', 'activo', 'unidad_funcional_ruta', 'fecha_hora',
                       'reportado_por_nombre', 'prioridad', 'clasificacion',
                       'equipo_parado', 'descripcion'),
        }),
        ('Asignación (como una OT)', {
            'fields': ('tecnico_principal', 'tecnicos', 'fecha_asignacion', 'asignado_por'),
        }),
        ('Resolución (la completa el técnico desde la app)', {
            'fields': ('estado', 'fecha_inicio', 'diagnostico', 'acciones_realizadas',
                       'materiales_utilizados', 'operativo_salida',
                       'fecha_resolucion', 'resuelto_por'),
        }),
        ('Auditoría', {
            'classes': ('collapse',),
            'fields': ('creado_por', 'creado_en', 'actualizado_en'),
        }),
    )

    class Media:
        js = ('monitoreo/js/averia_admin.js',)

    @admin.display(description='Unidad funcional')
    def unidad_funcional_ruta(self, obj):
        texto = obj.unidad_funcional_display if obj and obj.pk else 'Se completa al elegir el activo'
        return format_html('<span id="av-unidad-funcional">{}</span>', texto)

    @admin.display(description='Unidad funcional', ordering='unidad_funcional__nombre')
    def unidad_funcional_col(self, obj):
        return obj.unidad_funcional or '—'

    @admin.display(description='Prioridad', ordering='prioridad')
    def prioridad_badge_col(self, obj):
        colores = {'baja': ('#f1f5f9', '#475569'), 'media': ('#eff6ff', '#1d4ed8'),
                   'alta': ('#fef3c7', '#92400e'), 'critica': ('#fee2e2', '#991b1b')}
        bg, fg = colores.get(obj.prioridad, ('#f1f5f9', '#475569'))
        return format_html('<span style="background:{};color:{};padding:2px 8px;border-radius:3px;font-weight:600;">{}</span>',
                           bg, fg, obj.get_prioridad_display())

    @admin.display(description='Estado', ordering='estado')
    def estado_badge_col(self, obj):
        colores = {'abierta': ('#fee2e2', '#991b1b'), 'asignada': ('#eff6ff', '#1d4ed8'),
                   'en_proceso': ('#fef3c7', '#92400e'), 'resuelta': ('#dcfce7', '#166534'),
                   'cancelada': ('#f1f5f9', '#475569')}
        bg, fg = colores.get(obj.estado, ('#f1f5f9', '#475569'))
        return format_html('<span style="background:{};color:{};padding:2px 8px;border-radius:3px;font-weight:600;">{}</span>',
                           bg, fg, obj.get_estado_display())

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'activo' in form.base_fields:
            form.base_fields['activo'].required = True
        if 'reportado_por_nombre' in form.base_fields and obj is None:
            form.base_fields['reportado_por_nombre'].initial = request.user.get_full_name() or request.user.username
        return form

    def save_model(self, request, obj, form, change):
        from django.utils import timezone
        if not obj.pk:
            obj.creado_por = request.user
        if 'tecnico_principal' in form.changed_data and obj.tecnico_principal_id:
            obj.fecha_asignacion = timezone.now()
            obj.asignado_por = request.user
            if obj.estado == 'abierta':
                obj.estado = 'asignada'
        if obj.estado == 'resuelta' and not obj.fecha_resolucion:
            obj.fecha_resolucion = timezone.now()
            obj.resuelto_por = obj.resuelto_por or request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Solo apoyo asignado (sin responsable) también cuenta como asignada
        if obj.estado == 'abierta' and obj.tecnicos.exists():
            obj.estado = 'asignada'
            obj.fecha_asignacion = obj.fecha_asignacion or obj.actualizado_en
            obj.asignado_por = obj.asignado_por or request.user
            obj.save(update_fields=['estado', 'fecha_asignacion', 'asignado_por'])

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            if isinstance(inst, FotoAveria) and not inst.subido_por_id:
                inst.subido_por = request.user
            inst.save()
        for inst in formset.deleted_objects:
            inst.delete()
        formset.save_m2m()
