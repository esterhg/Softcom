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
]
