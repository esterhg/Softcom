"""Armado del Excel "Reporte de Horas Extras" (sin request).

Replica el formato de REPORTE_DE_HORAS_EXTRAS_INSTALACIONES.xlsx: logo, cuadro
de fecha/periodo, tabla con jornada y recargos (F:1.25 / 1.50 / 1.75 / 2.00)
calculados con las MISMAS fórmulas de la plantilla, fila de subtotales y firmas.
Las fórmulas se calculan al abrir el archivo en Excel.
"""
from datetime import date, time
from pathlib import Path

from django.utils import timezone

LOGO = Path(__file__).resolve().parent.parent / 'static' / 'rrhh' / 'img' / 'logo_reporte.png'

FUENTE = 'Aptos'
AZUL_ENCABEZADO = 'B7D4EF'
GRIS_SUBTOTAL = 'D8D8D8'
VERDE_CENA = 'C6EFCE'
FMT_CONTABLE = '_-* #,##0.00_-;\\-* #,##0.00_-;_-* \\-??_-;_-@_-'

PRIMERA_FILA = 10
ENCABEZADOS = ['FECHA', 'DIA', 'JORNADA', 'COLABORADOR', 'ACTIVIDAD', 'HORA INICIO',
               'HORA FIN', 'TOTAL HORAS', 'CENA', 'HORAS F:1.25', 'HORAS F:1.50',
               'HORAS F:1.75', 'HORAS F:2.00']
# Ancho de columnas A..O, igual que la plantilla.
ANCHOS = {'A': 2.3, 'B': 13.3, 'C': 18.6, 'D': 13.7, 'E': 37.7, 'F': 64.9, 'G': 8.7,
          'H': 18.3, 'I': 11.7, 'J': 10.0, 'K': 9.3, 'L': 9.4, 'M': 9.9, 'N': 9.9, 'O': 3.3}


def nombre_persona(u):
    return (u.get_full_name() or u.username) if u else ''


def texto_periodo(horas, desde=None, hasta=None):
    """'DEL dd/mm/aaaa AL dd/mm/aaaa' con el filtro o, si no hay, con las fechas de los datos."""
    if not desde or not hasta:
        fechas = [timezone.localtime(h.entrada).date() for h in horas]
        if not fechas:
            return ''
        desde, hasta = desde or min(fechas), hasta or max(fechas)
    return f'DEL {desde:%d/%m/%Y} AL {hasta:%d/%m/%Y}'


def _formulas_fila(r):
    """Fórmulas de la plantilla para la fila ``r`` (C, D, I, K, L, M, N)."""
    return {
        'C': (f'=CHOOSE(WEEKDAY(B{r}),"DOMINGO","LUNES","MARTES","MIÉRCOLES",'
              f'"JUEVES","VIERNES","SÁBADO")'),
        'D': (f'=IF(AND(G{r}>=TIME(5,0,0),G{r}<TIME(19,0,0),H{r}>G{r},H{r}<=TIME(19,0,0)),'
              f'"DIURNO",IF(OR(AND(G{r}>=TIME(19,0,0),OR(H{r}>G{r},H{r}<=TIME(5,0,0))),'
              f'AND(G{r}<TIME(5,0,0),H{r}>G{r},H{r}<=TIME(5,0,0))),"NOCTURNO","MIXTO"))'),
        'I': f'=MOD(H{r}-G{r},1)*24',
        'K': (f'=IF(C{r}="DOMINGO",0,IF(D{r}="DIURNO",I{r}-M{r}-L{r},'
              f'IF(I{r}-L{r}-M{r}<0,0,I{r}-L{r}-M{r}-N{r})))'),
        'L': (f'=IF(C{r}="DOMINGO",0,IF(C{r}="SÁBADO",IF(H{r}>$L$6,(H{r}-G{r})*24-M{r},0),'
              f'IF(H{r}>$L$7,(H{r}-$L$7)*24-M{r},0)))'),
        'M': (f'=IF(C{r}="DOMINGO",0,IF(C{r}="SÁBADO",IF(H{r}>$M$6,(H{r}-$M$6)*24,0),'
              f'IF(H{r}>$M$7,(H{r}-$M$7)*24,0)))'),
        'N': f'=IF(C{r}="DOMINGO",(H{r}-G{r})*24,0)',
    }


def libro_excel_horas(horas, *, titulo='REPORTE DE HORAS EXTRAS', categoria=None,
                      reporte=None, periodo=''):
    """Libro con una hoja 'Reporte HE'.

    ``horas``: iterable de HoraExtra (con colaborador/categoria). ``categoria``:
    nombre mostrado en el encabezado (None = todas). ``reporte``: ID del reporte
    si se exporta uno solo.
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = 'Reporte HE'
    escribir_hoja_horas(ws, horas, titulo=titulo, categoria=categoria,
                        reporte=reporte, periodo=periodo)
    return wb


SIN_CATEGORIA = 'Sin categoría'


def nombre_hoja(nombre, usados):
    """Nombre de hoja válido para Excel (≤31 caracteres, sin []:*?/\\) y único."""
    limpio = ''.join(' ' if ch in '[]:*?/\\' else ch for ch in (nombre or '')).strip() or 'Hoja'
    base = limpio[:31]
    final, n = base, 2
    while final.lower() in usados:
        sufijo = f' ({n})'
        final = base[:31 - len(sufijo)] + sufijo
        n += 1
    usados.add(final.lower())
    return final


def agrupar_por_categoria(horas):
    """[(nombre_categoria, [horas...]), ...] ordenado por nombre; 'Sin categoría' al final."""
    grupos = {}
    for h in horas:
        nombre = h.categoria.nombre if h.categoria else SIN_CATEGORIA
        grupos.setdefault(nombre, []).append(h)
    return sorted(grupos.items(), key=lambda kv: (kv[0] == SIN_CATEGORIA, kv[0].lower()))


def libro_excel_por_categorias(horas, *, titulo='REPORTE DE HORAS EXTRAS', reporte=None,
                               desde=None, hasta=None):
    """Libro con una hoja por categoría (mismo formato que ``libro_excel_horas``).

    Cada hoja tiene su propio periodo y subtotales. Sin datos: una hoja vacía.
    """
    from openpyxl import Workbook

    horas = list(horas)
    wb = Workbook()
    grupos = agrupar_por_categoria(horas)
    if not grupos:
        ws = wb.active
        ws.title = 'Reporte HE'
        escribir_hoja_horas(ws, [], titulo=titulo, reporte=reporte,
                            periodo=texto_periodo([], desde, hasta))
        return wb

    usados = set()
    for i, (nombre, items) in enumerate(grupos):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = nombre_hoja(nombre, usados)
        escribir_hoja_horas(ws, items, titulo=titulo, categoria=nombre, reporte=reporte,
                            periodo=texto_periodo(items, desde, hasta))
    return wb


def escribir_hoja_horas(ws, horas, *, titulo='REPORTE DE HORAS EXTRAS', categoria=None,
                        reporte=None, periodo=''):
    """Escribe en ``ws`` el reporte con el formato de la plantilla de Instalaciones."""
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.properties import PageSetupProperties

    horas = list(horas)
    ws.sheet_view.showGridLines = False

    fino = Side(style='thin')
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    centro = Alignment(horizontal='center', vertical='center')
    izq = Alignment(horizontal='left', vertical='center')

    def fuente(sz=12, b=False, color='000000'):
        return Font(name=FUENTE, size=sz, bold=b, color=color)

    for col, ancho in ANCHOS.items():
        ws.column_dimensions[col].width = ancho

    # --- Logo ---
    if LOGO.exists():
        try:
            from openpyxl.drawing.image import Image
            ws.add_image(Image(str(LOGO)), 'B1')
        except Exception:  # Pillow ausente o imagen ilegible: el reporte sale sin logo
            pass

    # --- Títulos (a la derecha del logo) ---
    ws['E3'], ws['E4'], ws['E5'] = (
        titulo,
        f'CATEGORÍA: {categoria}' if categoria else 'TODAS LAS CATEGORÍAS',
        f'REPORTE: {reporte}' if reporte else '',
    )
    for fila in (3, 4, 5):
        ws.merge_cells(f'E{fila}:M{fila}')
        ws[f'E{fila}'].font = fuente(b=True)
        ws[f'E{fila}'].alignment = centro

    # --- Fecha y periodo ---
    ws['B6'], ws['B7'] = 'FECHA', 'PERIODO'
    for c in ('B6', 'B7'):
        ws[c].font = fuente(b=True)
        ws[c].alignment = izq
    ws['E6'] = '=TODAY()'
    ws['E6'].number_format = 'm/d/yyyy'
    ws['E6'].font = fuente(b=True)
    ws['E6'].alignment = centro
    ws['E7'] = periodo
    ws['E7'].font = fuente(b=True)

    # --- Parámetros de recargo (celdas J6:M7, texto blanco como en la plantilla) ---
    #            J6           K6           L6 (sáb.)    M6 (sáb.)
    parametros = {'J6': time(12), 'K6': time(12), 'L6': time(12), 'M6': time(17),
                  'J7': time(19), 'K7': time(17), 'L7': time(19), 'M7': time(21)}
    for ref, valor in parametros.items():
        ws[ref] = valor
        ws[ref].number_format = 'h:mm:ss'
        ws[ref].font = fuente(color='FFFFFF')
        ws[ref].alignment = centro

    # --- Encabezado de la tabla (fila 9) ---
    ws.row_dimensions[9].height = 30
    relleno = PatternFill('solid', start_color=AZUL_ENCABEZADO, end_color=AZUL_ENCABEZADO)
    for i, texto in enumerate(ENCABEZADOS):
        c = ws.cell(row=9, column=2 + i, value=texto)
        c.font = fuente(11, True)
        c.fill = relleno
        c.border = borde
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # --- Filas de datos ---
    n_filas = max(len(horas), 1)
    ultima = PRIMERA_FILA + n_filas - 1
    for i in range(n_filas):
        r = PRIMERA_FILA + i
        h = horas[i] if i < len(horas) else None
        if h is not None:
            ent, sal = timezone.localtime(h.entrada), timezone.localtime(h.salida)
            ws[f'B{r}'] = date(ent.year, ent.month, ent.day)
            ws[f'E{r}'] = nombre_persona(h.colaborador)
            ws[f'F{r}'] = h.justificacion
            ws[f'G{r}'] = time(ent.hour, ent.minute)
            ws[f'H{r}'] = time(sal.hour, sal.minute)
            if h.cena:
                ws[f'J{r}'] = 1
        for col, formula in _formulas_fila(r).items():
            ws[f'{col}{r}'] = formula

        ws[f'B{r}'].number_format = 'm/d/yyyy'
        ws[f'G{r}'].number_format = ws[f'H{r}'].number_format = 'h:mm'
        ws[f'I{r}'].number_format = '0.00'
        ws[f'J{r}'].number_format = '0'
        for col in 'KLMN':
            ws[f'{col}{r}'].number_format = FMT_CONTABLE
        for col in 'BCDEFGHIJKLMN':
            c = ws[f'{col}{r}']
            c.font = fuente()
            c.border = borde
            c.alignment = centro if col in 'BGHIJKLMN' else izq
        ws[f'F{r}'].alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

    # Cena = 1 resaltada en verde (igual que la plantilla).
    ws.conditional_formatting.add(
        f'J{PRIMERA_FILA}:J{ultima}',
        CellIsRule(operator='equal', formula=['1'],
                   fill=PatternFill('solid', start_color=VERDE_CENA, end_color=VERDE_CENA,
                                    bgColor=VERDE_CENA)))

    # --- Fila de subtotales ---
    sub = ultima + 1
    gris = PatternFill('solid', start_color=GRIS_SUBTOTAL, end_color=GRIS_SUBTOTAL)
    ws.merge_cells(f'B{sub}:H{sub}')
    for col in 'BCDEFGHIJKLMN':
        c = ws[f'{col}{sub}']
        c.fill = gris
        c.border = borde
        c.font = fuente(b=True)
        c.alignment = centro
    for col in 'IJKLMN':
        ws[f'{col}{sub}'] = f'=SUBTOTAL(9,{col}{PRIMERA_FILA}:{col}{ultima})'
        ws[f'{col}{sub}'].number_format = '0' if col == 'J' else FMT_CONTABLE

    # --- Firmas ---
    firma = sub + 9
    ws.merge_cells(f'B{firma}:E{firma}')
    ws.merge_cells(f'F{firma}:K{firma}')
    ws.merge_cells(f'B{firma + 1}:E{firma + 1}')
    ws.merge_cells(f'F{firma + 1}:K{firma + 1}')
    ws[f'B{firma}'], ws[f'F{firma}'] = 'Coordinador de ', 'Gerente de'
    ws[f'B{firma + 1}'], ws[f'F{firma + 1}'] = 'Ing. ', 'Ing.'
    for col in 'BCDEFGHIJK':
        ws[f'{col}{firma}'].border = Border(top=fino)
    for ref in (f'B{firma}', f'F{firma}', f'B{firma + 1}', f'F{firma + 1}'):
        ws[ref].font = fuente(14, True)
        ws[ref].alignment = centro

    # --- Impresión ---
    ws.print_area = f'A1:O{firma + 1}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    return ws
