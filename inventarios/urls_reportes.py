"""
Rutas de los reportes de inventario.

Se incluyen desde ``inventarios/urls.py`` con ``include()`` sin namespace
propio, así que los nombres siguen siendo ``inventarios:<nombre>`` y las URLs
quedan bajo ``/inventarios/reportes/...`` (sin cambios para el usuario).

Convención de Softcom:
- Pantallas de consulta: GET, con filtros/página en la URL (historial y recarga).
- Exportaciones: GET ``.../excel/`` con los mismos parámetros de la pantalla.
"""
from django.urls import path

from .reportes import (
    export_catalogo_excel,
    export_inventario_actual_excel,
    export_movimientos_excel,
    export_pases_pendientes_excel,
    reporte_inventario_view,
    reporte_pases_pendientes_view,
    tabla_movimientos_view,
)

urlpatterns = [
    # Centro de reportes
    path('reportes/', reporte_inventario_view, name='reportes'),

    # Movimientos
    path('reportes/movimientos/', tabla_movimientos_view, name='tabla_movimientos'),
    path('reportes/movimientos/excel/', export_movimientos_excel, name='export_movimientos_excel'),

    # Pases de salida pendientes de justificar
    path('reportes/pases-pendientes/', reporte_pases_pendientes_view, name='reporte_pases_pendientes'),
    path('reportes/pases-pendientes/excel/', export_pases_pendientes_excel, name='export_pases_pendientes_excel'),

    # Exportaciones (pendientes de migrar a capas)
    path('reportes/inventario/excel/', export_inventario_actual_excel, name='export_inventario_actual_excel'),
    path('reportes/catalogo/excel/', export_catalogo_excel, name='export_catalogo_excel'),
]
