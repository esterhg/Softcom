"""
Constructor del PDF de Verificación de Elevadores (Alarma e Intercomunicador).
Replica el formato OCC-INST-FOR-0X_INSPECCION_ELEVADORES.
Usa Playwright — mismo patrón que monitoreo.pdf_builder.
"""
import base64
import logging
import os

logger = logging.getLogger(__name__)


def build_verif_pdf_bytes(reporte):
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
    con_hallazgos = [f for f in filas if f.tiene_hallazgos]

    # ── Fotos en base64 ────────────────────────────────────────
    fotos_b64 = []
    for idx, foto in enumerate(reporte.fotos.order_by('subido_en')):
        try:
            foto.imagen.open('rb')
            data = foto.imagen.read()
            foto.imagen.close()
            ext  = os.path.splitext(str(foto.imagen))[-1].lower().strip('.')
            mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'gif': 'gif', 'webp': 'webp'}.get(ext, 'jpeg')
            fotos_b64.append({
                'b64': base64.b64encode(data).decode(),
                'mime': mime,
                'descripcion': foto.descripcion or '',
            })
        except Exception as exc:
            logger.warning('No se pudo leer foto verif %s: %s', foto.pk, exc)

    html = render_to_string('monitoreo/reporte_verif_pdf.html', {
        'reporte':           reporte,
        'logo_b64':          logo_b64,
        'fotos_b64':         fotos_b64,
        'filas':             filas,
        'total_elevadores':  total,
        'con_hallazgos':     con_hallazgos,
        'hallazgos_count':   len(con_hallazgos),
    })

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-gpu', '--disable-dev-shm-usage', '--single-process'],
        )
        page = browser.new_page()
        page.set_content(html, wait_until='load')
        pdf_bytes = page.pdf(
            format='A4', print_background=True, landscape=True,
            margin={'top': '10mm', 'bottom': '10mm', 'left': '8mm', 'right': '8mm'},
        )
        browser.close()

    return pdf_bytes
