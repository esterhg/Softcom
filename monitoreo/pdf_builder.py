"""
Constructor del PDF de Monitoreo de Elevadores.
Usa Playwright — mismo patrón que mantenimiento.utils.pdf_utils.
"""
import base64
import logging
import os
from collections import OrderedDict, defaultdict

logger = logging.getLogger(__name__)

ORDEN_UBICACIONES = [
    'Conjunto', 'Sótanos', 'Cuerpo Bajo A', 'Cuerpo Bajo B',
    'Cuerpo Bajo C', 'Torre 1', 'Torre 2',
]


def build_pdf_bytes(reporte):
    from django.conf import settings
    from django.template.loader import render_to_string
    from playwright.sync_api import sync_playwright

    # ── Logo ──────────────────────────────────────────────────
    logo_b64 = ''
    path = os.path.join(settings.BASE_DIR, 'activos', 'static', 'activos', 'img', 'logo_operadora_cc.png')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    # ── Filas ──────────────────────────────────────────────────
    filas = list(reporte.filas.select_related('elevador').order_by('orden'))
    total = len(filas)
    novedades = [f for f in filas if f.estado not in ('operativo', 'sin_novedad')]
    buen_estado = total - len(novedades)

    # ── Grupos por ubicación (orden canónico) ──────────────────
    raw = defaultdict(list)
    for f in filas:
        raw[f.elevador.ubicacion or 'Sin ubicación'].append(f)

    grupos = OrderedDict()
    for ub in ORDEN_UBICACIONES:
        if ub in raw:
            grupos[ub] = raw.pop(ub)
    grupos.update(raw)

    grupos_ubicacion = []
    for ub, gfilas in grupos.items():
        con_nov = [f for f in gfilas if f.estado not in ('operativo', 'sin_novedad')]
        grupos_ubicacion.append({
            'ubicacion':          ub,
            'nombres':            ', '.join(f.elevador.nombre for f in gfilas),
            'total':              len(gfilas),
            'buen_estado':        len(gfilas) - len(con_nov),
            'con_novedad':        len(con_nov),
            'elevadores_novedad': ', '.join(f.elevador.nombre for f in con_nov),
        })

    # ── Fotos en base64 ────────────────────────────────────────
    fotos_b64 = []
    fotos_qs  = list(reporte.fotos.order_by('subido_en'))

    # Asociar primeras fotos a elevadores con novedad
    elev_foto_map = {}
    for i, fila in enumerate(novedades):
        if i < len(fotos_qs):
            elev_foto_map[i] = fila

    for idx, foto in enumerate(fotos_qs):
        try:
            foto.imagen.open('rb')
            data = foto.imagen.read()
            foto.imagen.close()
            ext  = os.path.splitext(str(foto.imagen))[-1].lower().strip('.')
            mime = {'jpg':'jpeg','jpeg':'jpeg','png':'png','gif':'gif','webp':'webp'}.get(ext,'jpeg')

            fila_rel = elev_foto_map.get(idx)
            if fila_rel:
                label    = f'{fila_rel.elevador.nombre} · {fila_rel.elevador.ubicacion}'
                sublabel = f'Foto {idx+1} de {len(fotos_qs)}'
            else:
                extra    = idx - len(elev_foto_map) + 1
                label    = f'Evidencia {extra}'
                sublabel = foto.descripcion or ''

            fotos_b64.append({
                'b64':  base64.b64encode(data).decode(),
                'mime': mime,
                'label': label,
                'sublabel': sublabel,
                'descripcion': foto.descripcion or '',
            })
        except Exception as exc:
            logger.warning('No se pudo leer foto %s: %s', foto.pk, exc)

    # Asignar conteo de fotos por novedad
    for fila in novedades:
        fila.fotos_count = sum(1 for v in elev_foto_map.values() if v == fila)

    html = render_to_string('monitoreo/reporte_pdf.html', {
        'reporte':           reporte,
        'logo_b64':          logo_b64,
        'fotos_b64':         fotos_b64,
        'total_elevadores':  total,
        'buen_estado_count': buen_estado,
        'novedades_count':   len(novedades),
        'novedades_list':    novedades,
        'grupos_ubicacion':  grupos_ubicacion,
    })

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-setuid-sandbox',
                  '--disable-gpu','--disable-dev-shm-usage','--single-process'],
        )
        page = browser.new_page()
        page.set_content(html, wait_until='load')
        pdf_bytes = page.pdf(
            format='A4', print_background=True,
            margin={'top':'12mm','bottom':'12mm','left':'12mm','right':'12mm'},
        )
        browser.close()

    return pdf_bytes
