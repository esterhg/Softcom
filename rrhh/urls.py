from django.urls import path

from . import views

app_name = 'rrhh'

urlpatterns = [
    # Pantalla principal: tabla de horas extra (+ pestaña de reportes)
    path('', views.reportes_view, name='reportes'),
    path('reportes/excel/', views.export_reportes_excel, name='export_reportes_excel'),
    path('reportes/nuevo/', views.crear_reporte_view, name='crear_reporte'),
    path('categorias/nueva/', views.crear_categoria_view, name='crear_categoria'),
    path('reportes/<int:pk>/', views.detalle_reporte_view, name='detalle_reporte'),
    path('reportes/<int:pk>/excel/', views.export_reporte_excel, name='export_reporte_excel'),

    # Horas extra
    path('horas/nueva/', views.crear_hora_extra_general_view, name='crear_hora_extra_general'),
    path('reportes/<int:pk>/horas/nueva/', views.crear_hora_extra_view, name='crear_hora_extra'),
    path('horas/<int:pk>/editar/', views.editar_hora_extra_view, name='editar_hora_extra'),
    path('horas/<int:pk>/eliminar/', views.eliminar_hora_extra_view, name='eliminar_hora_extra'),
]
