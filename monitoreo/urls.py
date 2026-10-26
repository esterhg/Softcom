from django.urls import path
from . import views

app_name = 'monitoreo'

urlpatterns = [
    # Listado principal
    path('elevadores/', views.reportes_lista, name='reportes_lista'),
    # Historial completo (nueva pestaña)
    path('elevadores/historial/', views.historial_reportes, name='historial_reportes'),
    # Descarga ZIP por mes
    path('elevadores/historial/zip/', views.historial_descargar_zip, name='historial_zip'),
    # Crear reporte
    path('elevadores/nuevo/', views.reporte_crear, name='reporte_crear'),
    # Detalle
    path('elevadores/<int:pk>/', views.reporte_detalle, name='reporte_detalle'),
    # Editar
    path('elevadores/<int:pk>/editar/', views.reporte_editar, name='reporte_editar'),
    # Eliminar
    path('elevadores/<int:pk>/eliminar/', views.reporte_eliminar, name='reporte_eliminar'),
    # PDF (genera + guarda en storage)
    path('elevadores/<int:pk>/pdf/', views.reporte_pdf, name='reporte_pdf'),
    # API fotos
    path('elevadores/<int:pk>/fotos/subir/', views.foto_subir, name='foto_subir'),
    path('elevadores/fotos/<int:foto_pk>/eliminar/', views.foto_eliminar, name='foto_eliminar'),
    path('elevadores/fotos/<int:foto_pk>/descripcion/', views.foto_actualizar_descripcion, name='foto_descripcion'),

    # ── Verificación de Elevadores: Alarma e Intercomunicador ──
    path('verificacion-alarma/', views.verif_lista, name='verif_lista'),
    path('verificacion-alarma/historial/', views.verif_historial, name='verif_historial'),
    path('verificacion-alarma/historial/zip/', views.verif_historial_zip, name='verif_historial_zip'),
    path('verificacion-alarma/nuevo/', views.verif_crear, name='verif_crear'),
    path('verificacion-alarma/<int:pk>/', views.verif_detalle, name='verif_detalle'),
    path('verificacion-alarma/<int:pk>/editar/', views.verif_editar, name='verif_editar'),
    path('verificacion-alarma/<int:pk>/eliminar/', views.verif_eliminar, name='verif_eliminar'),
    path('verificacion-alarma/<int:pk>/pdf/', views.verif_pdf, name='verif_pdf'),
    path('verificacion-alarma/<int:pk>/fotos/subir/', views.verif_foto_subir, name='verif_foto_subir'),
    path('verificacion-alarma/fotos/<int:foto_pk>/eliminar/', views.verif_foto_eliminar, name='verif_foto_eliminar'),

    # ── Accionamiento Manual Mensual ──
    path('accionamiento/', views.acc_lista, name='acc_lista'),
    path('accionamiento/historial/', views.acc_historial, name='acc_historial'),
    path('accionamiento/historial/zip/', views.acc_historial_zip, name='acc_historial_zip'),
    path('accionamiento/nuevo/', views.acc_crear, name='acc_crear'),
    path('accionamiento/<int:pk>/', views.acc_detalle, name='acc_detalle'),
    path('accionamiento/<int:pk>/editar/', views.acc_editar, name='acc_editar'),
    path('accionamiento/<int:pk>/eliminar/', views.acc_eliminar, name='acc_eliminar'),
    path('accionamiento/<int:pk>/pdf/', views.acc_pdf, name='acc_pdf'),
    path('accionamiento/<int:pk>/fotos/subir/', views.acc_foto_subir, name='acc_foto_subir'),
    path('accionamiento/fotos/<int:foto_pk>/eliminar/', views.acc_foto_eliminar, name='acc_foto_eliminar'),
]
