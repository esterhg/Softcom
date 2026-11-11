from django.urls import path

from . import views

app_name = 'rrhh'

urlpatterns = [
    path('', views.reportes_view, name='reportes'),
    path('reportes/excel/', views.export_reportes_excel, name='export_reportes_excel'),
    path('reportes/nuevo/', views.crear_reporte_view, name='crear_reporte'),
    path('reportes/<int:pk>/', views.detalle_reporte_view, name='detalle_reporte'),
    path('reportes/<int:pk>/horas/nueva/', views.crear_hora_extra_view, name='crear_hora_extra'),
]
