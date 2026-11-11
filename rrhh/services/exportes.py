"""Armado de libros Excel de RRHH (sin request)."""
from django.utils import timezone

from core import excel

HEADERS = ['ID de reporte', 'Colaborador', 'Autorizado por', 'Solicitado por',
           'Creado', 'Registros', 'Horas totales']


def _nombre(u):
    return (u.get_full_name() or u.username) if u else ''


def libro_excel_reportes(reportes):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Reportes de horas'
    excel.escribir_headers(ws, HEADERS)
    for r in reportes:
        ws.append([
            r.codigo, _nombre(r.colaborador), _nombre(r.autorizado_por),
            _nombre(r.solicitado_por),
            timezone.localtime(r.creado_en).strftime('%d/%m/%Y %H:%M'),
            r.num_registros, float(r.total_horas or 0),
        ])
    excel.autoajustar(ws, len(HEADERS))
    return wb
