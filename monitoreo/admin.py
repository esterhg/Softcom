from django.contrib import admin
from django.db.models import ProtectedError
from django.utils.html import format_html
from .models import Elevador, ReporteElevador, FilaReporteElevador, FotoAnexoReporte


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
