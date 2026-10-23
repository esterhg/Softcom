# -*- coding: utf-8 -*-
"""
Generación del PDF de mantenimiento de ASCENSORES (formato estilo TKE, SIN logo TKE).
Usa Playwright (mismo motor que pdf_utils.generate_ot_pdf_bytes).
"""
import base64
import logging
import os

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from playwright.sync_api import sync_playwright

from .pdf_utils import _optimize_image
from ..models import ValorPasoOrden, ArchivoOrdenTrabajo

logger = logging.getLogger(__name__)


# Tabla AST (Análisis Seguro de Trabajo) estándar — igual al formato de ejemplo.
AST_RIESGOS = [
    {"riesgo": "Caída de altura", "peligro": "Alto", "controlado": "Medio", "medidas": [
        "Realizar procedimiento estándar de trabajo",
        "Confirmar existencia de barandas en techo de cabina",
        "Cinturón de posicionamiento",
        "Uso de EPP conforme proceso",
    ]},
    {"riesgo": "Choque eléctrico", "peligro": "Alto", "controlado": "Medio", "medidas": [
        "Realizar procedimiento estándar de trabajo",
        "Uso de EPP conforme proceso",
    ]},
    {"riesgo": "Atrapamiento", "peligro": "Alto", "controlado": "Medio", "medidas": [
        "Realizar procedimiento estándar de trabajo",
        "Realizar acceso seguro al foso y techo de cabina",
        "Uso de EPP conforme proceso",
    ]},
    {"riesgo": "Machucón / Corte", "peligro": "Alto", "controlado": "Medio", "medidas": [
        "Realizar procedimiento estándar de trabajo",
        "Uso de EPP conforme proceso",
    ]},
    {"riesgo": "Golpeado por / Golpear un objeto", "peligro": "Alto", "controlado": "Medio", "medidas": [
        "Realizar procedimiento estándar de trabajo",
        "Uso de EPP conforme proceso",
    ]},
    {"riesgo": "Tropezar / caída mismo nivel", "peligro": "Alto", "controlado": "Medio", "medidas": [
        "Realizar procedimiento estándar de trabajo",
        "Uso de EPP conforme proceso",
    ]},
]


def _logo_b64():
    logo_path = os.path.join(settings.BASE_DIR, "activos", "static", "activos", "img", "logo_operadora_cc.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""


def generate_ascensor_pdf_bytes(ot, request=None):
    # 1) Checklist: unir pasos con resultados
    pasos = ot.rutina.pasos.all().order_by("orden") if ot.rutina else []
    results = {r.paso_id: r for r in ValorPasoOrden.objects.filter(orden_trabajo=ot).select_related("paso")}

    checklist_items = []
    for paso in pasos:
        res = results.get(paso.id)
        checklist_items.append({
            "paso": paso,
            "valor_bool": getattr(res, "valor_bool", None),
            "valor_numerico": getattr(res, "valor_numerico", None),
            "valor_texto": getattr(res, "valor_texto", None),
            "no_aplica": getattr(res, "no_aplica", False),
            "comentarios": getattr(res, "comentarios", "") or "",
        })

    # 2) Datos de cabecera
    activo = ot.activos.first()
    edificio = ot.ubicacion.get_root() if ot.ubicacion else (activo.ubicacion.get_root() if activo and activo.ubicacion else None)

    supervisor_nombre = ""
    if ot.supervisor:
        supervisor_nombre = ot.supervisor.get_full_name() or ot.supervisor.username

    tecnico_perfil = ot.tecnico_puesto
    if not tecnico_perfil and ot.tecnico and hasattr(ot.tecnico, "perfil_tecnico"):
        tecnico_perfil = ot.tecnico.perfil_tecnico
    if tecnico_perfil:
        tecnico_nombre = (f"{tecnico_perfil.nombre or ''} {tecnico_perfil.apellido or ''}".strip()
                          or (tecnico_perfil.user.get_full_name() if tecnico_perfil.user else ""))
    elif ot.tecnico:
        tecnico_nombre = ot.tecnico.get_full_name() or ot.tecnico.username
    else:
        tecnico_nombre = ot.firma_tecnico_nombre or "N/A"

    empresa_nombre = "Operadora de Infraestructura de Honduras, S.A. de C.V."
    if ot.empresa_responsable:
        empresa_nombre = ot.empresa_responsable.nombre

    # 3) Fotos (anexos)
    fotos = []
    for archivo in ArchivoOrdenTrabajo.objects.filter(orden_trabajo=ot, tipo="IMAGEN").select_related("paso").order_by("creado_en"):
        try:
            data = archivo.archivo.read()
            b64 = base64.b64encode(_optimize_image(data)).decode("utf-8")
            fotos.append({
                "nombre": (archivo.paso.descripcion if archivo.paso else archivo.nombre) or "Evidencia",
                "data_uri": f"data:image/jpeg;base64,{b64}",
            })
        except Exception as e:  # noqa
            logger.warning("No se pudo leer la foto %s: %s", archivo.id, e)

    context = {
        "ot": ot,
        "checklist_items": checklist_items,
        "logo_b64": _logo_b64(),
        "empresa_nombre": empresa_nombre,
        "edificio_nombre": edificio.nombre if edificio else "N/A",
        "ubicacion_completa": ot.ubicacion.get_ruta_completa() if ot.ubicacion else "N/A",
        "activo": activo,
        "activo_nombre": activo.nombre if activo else "N/A",
        "activo_codigo": (activo.codigo_interno if activo else "") or "",
        "supervisor_nombre": supervisor_nombre or "N/A",
        "tecnico_nombre": tecnico_nombre,
        "fotos": fotos,
        "ast_riesgos": AST_RIESGOS,
        "ahora": timezone.now(),
    }

    html = render_to_string("mantenimiento/ascensores_pdf.html", context, request=request)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu",
                  "--disable-dev-shm-usage", "--single-process"],
        )
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        pdf_bytes = page.pdf(format="A4", print_background=True,
                             margin={"top": "0.6cm", "bottom": "0.6cm", "left": "0.6cm", "right": "0.6cm"})
        browser.close()

    return pdf_bytes
