"""
Utilidades compartidas para exportar a Excel (openpyxl) con el estilo Softcom
(encabezado azul Fiori #0070F2, bordes #D9D9D9).
"""
from django.http import HttpResponse
from django.utils import timezone

XLSX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def estilos():
    """(header_font, header_fill, header_align, border) del estilo Softcom."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    header_font = Font(name='Arial', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='0070F2', end_color='0070F2', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin', color='D9D9D9')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, header_align, border


def escribir_headers(ws, headers):
    """Escribe la fila 1 con estilo de encabezado y congela el panel."""
    header_font, header_fill, header_align, border = estilos()
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border
    ws.freeze_panes = 'A2'


def autoajustar(ws, num_cols, max_width=55):
    """Ajusta el ancho de las columnas al contenido (con tope ``max_width``)."""
    from openpyxl.utils import get_column_letter
    for i in range(1, num_cols + 1):
        letter = get_column_letter(i)
        max_length = 0
        for cell in ws[letter]:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max_length + 2, max_width)


def respuesta_xlsx(wb, nombre_base, momento=None):
    """HttpResponse de descarga: '<nombre_base>_<AAAAMMDD_HHMM>.xlsx'."""
    momento = momento or timezone.now()
    response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
    stamp = timezone.localtime(momento).strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="{nombre_base}_{stamp}.xlsx"'
    wb.save(response)
    return response
