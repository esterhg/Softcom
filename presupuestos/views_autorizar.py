import json
import logging
from datetime import datetime

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

import requests
import traceback

from .models import Requisicion, RequisicionHistorial
from .views_import import _registrar_historial

logger = logging.getLogger(__name__)

# Palabras clave que identifican una aprobación parcial de Ricardo en el historial
_KEYWORDS_APROBACION_PARCIAL = ["Ricardo", "Zerrate", "[APROBACION_PARCIAL]", "Aprobación parcial"]


def _tiene_aprobacion_parcial_ricardo(requisicion):
    """
    Devuelve True si la requisición ya tiene al menos una entrada en el historial
    que corresponda a una aprobación parcial/intermedia de Ricardo Zerrate.
    """
    for kw in _KEYWORDS_APROBACION_PARCIAL:
        if requisicion.historial.filter(descripcion__icontains=kw).exists():
            return True
    return False


def _get_aprobador_config():
    """
    Lee el aprobador configurado desde ConfiguracionFlujoAprobacion.
    Fallback a Ricardo Zerrate si no existe fila.
    """
    from .models import ConfiguracionFlujoAprobacion
    cfg = ConfiguracionFlujoAprobacion.get_config()
    return cfg.aprobador_nombre, cfg.aprobador_email


def requisicion_autorizar(request, pk):
    try:
        if request.method != 'POST':
            return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)

        requisicion = get_object_or_404(Requisicion, pk=pk)

        # ── Atajo: si la requisición ya tiene aprobación parcial de Ricardo,
        #    autorizarla directamente sin volver a llamar a Power Automate.
        if (requisicion.estado_requisicion == 'PENDIENTE'
                and _tiene_aprobacion_parcial_ricardo(requisicion)):

            RequisicionHistorial.objects.create(
                requisicion=requisicion,
                estado_anterior='PENDIENTE',
                estado_nuevo='AUTORIZADO',
                usuario=request.user,
                descripcion=(
                    "Autorizado — aprobación de Ricardo Zerrate ya registrada. "
                    "No se requería segunda firma (flujo corregido)."
                ),
            )
            requisicion.estado_requisicion = 'AUTORIZADO'
            requisicion.fecha_aprobacion = requisicion.fecha_aprobacion or timezone.now()
            requisicion.save(update_fields=['estado_requisicion', 'fecha_aprobacion'])

            # Notificar al solicitante
            if requisicion.usuario_solicitante:
                try:
                    from mantenimiento.models import NotificacionMantenimiento
                    NotificacionMantenimiento.objects.create(
                        user=requisicion.usuario_solicitante,
                        mensaje=f"✅ Requisición {requisicion.cr8ca_requisicion} autorizada.",
                        tipo='SUCCESS',
                    )
                except Exception:
                    pass

            logger.info(
                f"Requisición {requisicion.cr8ca_requisicion} autorizada directamente "
                f"(tenía aprobación parcial de Ricardo)."
            )
            return JsonResponse({
                'success': True,
                'message': 'Requisición autorizada directamente. Ricardo Zerrate ya había aprobado.',
                'autorizado_directo': True,
            })

        # ── Flujo normal: enviar a Power Automate ──────────────────────────────

        # 1. Información del Solicitante, Responsable y Aprobador
        solicitante = requisicion.usuario_solicitante
        perfil_sol = getattr(solicitante, 'perfil', None) if solicitante else None
        responsable = perfil_sol.responsable if perfil_sol else None
        perfil_resp = getattr(responsable, 'perfil', None) if responsable else None
        aprobador = requisicion.aprobador
        perfil_aprobador = getattr(aprobador, 'perfil', None) if aprobador else None

        # 2. Artículos
        articulos_list = []
        for art in requisicion.articulos.all():
            articulos_list.append({
                "descripcion": art.cr8ca_articulo or "",
                "cantidad": float(art.cr8ca_cantidad),
                "costo_unitario": float(art.cr8ca_costoaproximado or 0),
                "subtotal": float(art.subtotal),
                "proveedor_sugerido": art.proveedor.nombre if art.proveedor else "",
            })

        # 3. Proveedores
        proveedores_nombres = []
        if requisicion.proveedor:
            proveedores_nombres.append(requisicion.proveedor.nombre)
        for ps in requisicion.proveedores_sugeridos.all():
            if ps.nombre not in proveedores_nombres:
                proveedores_nombres.append(ps.nombre)

        # 4. Aprobador configurado
        APROBADOR_NOMBRE, APROBADOR_EMAIL = _get_aprobador_config()

        payload = {
            "numero_requisicion": requisicion.cr8ca_requisicion,
            "asunto": requisicion.cr8ca_asunto,
            "motivo": requisicion.cr8ca_motivo or "",
            "costo_aproximado": float(requisicion.cr8ca_totalenarticulos or 0),
            "costo_total": float(requisicion.total_estimado or 0),
            "email_solicitante": (solicitante.email or "") if solicitante else "",
            "telefono_solicitante": (perfil_sol.telefono or "N/A") if perfil_sol else "N/A",
            "gerente_nombre": f"{responsable.first_name or ''} {responsable.last_name or ''}".strip() if responsable else "No asignado",
            "gerente_email": (responsable.email or "N/A") if responsable else "N/A",
            "gerente_telefono": (perfil_resp.telefono or "N/A") if perfil_resp else "N/A",
            "aprobador_nombre": APROBADOR_NOMBRE,
            "aprobador_email": APROBADOR_EMAIL,
            "aprobador_telefono": (perfil_aprobador.telefono or "N/A") if perfil_aprobador else "N/A",
            "proveedores": ", ".join(proveedores_nombres),
            "vinculo_aprobacion": f"{settings.SITE_URL}{reverse('presupuestos:requisicion_editar', kwargs={'pk': requisicion.pk})}?step=4",
            "articulos": articulos_list,
            "timestamp": datetime.now().isoformat(),
        }

        logger.error(f"PAYLOAD ENVIADO: {json.dumps(payload, indent=2, default=str)}")

        url = (
            "https://ce675e3ed2704594af019ed8d7d5f6.d7.environment.api.powerplatform.com:443"
            "/powerautomate/automations/direct/workflows/cc9e61ecc75f40e1bc6c502e14a7a47e"
            "/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
            "&sig=CpELVKybC1iwKmlr4qJXMHPgif2LoeH_mBgt902HbGI"
        )

        response = requests.post(url, json=payload)
        logger.error(f"PA RESPONSE: {response.status_code} - {response.text}")

        if response.status_code in [200, 202]:
            _registrar_historial(requisicion, 'PENDIENTE', usuario=request.user)
            requisicion.estado_requisicion = 'PENDIENTE'
            requisicion.save()
            return JsonResponse({'success': True, 'message': 'Autorización solicitada exitosamente.'})
        else:
            return JsonResponse(
                {'success': False, 'message': f'Error en Power Automate: {response.status_code}'},
                status=500,
            )

    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': f"Error interno: {str(e)}"}, status=500)


@staff_member_required
@require_POST
def corregir_pendientes_aprobacion_parcial(request):
    """
    Vista de acción admin (POST) que busca todas las requisiciones en PENDIENTE
    con aprobación parcial de Ricardo Zerrate y las mueve a AUTORIZADO.

    Acepta ?dry_run=1 para solo reportar sin modificar.
    """
    dry_run = request.GET.get('dry_run', '0') == '1'

    pendientes = Requisicion.objects.filter(estado_requisicion='PENDIENTE')
    autorizadas = []
    omitidas = []

    for req in pendientes:
        if _tiene_aprobacion_parcial_ricardo(req):
            if not dry_run:
                RequisicionHistorial.objects.create(
                    requisicion=req,
                    estado_anterior='PENDIENTE',
                    estado_nuevo='AUTORIZADO',
                    usuario=request.user,
                    descripcion=(
                        f"Autorizado retroactivamente — Ricardo Zerrate ya había aprobado. "
                        f"Corregido el {timezone.now().strftime('%d/%m/%Y %H:%M')} "
                        f"por {request.user.get_full_name() or request.user.username}."
                    ),
                )
                req.estado_requisicion = 'AUTORIZADO'
                req.fecha_aprobacion = req.fecha_aprobacion or timezone.now()
                req.save(update_fields=['estado_requisicion', 'fecha_aprobacion'])

                # Notificar al solicitante
                if req.usuario_solicitante:
                    try:
                        from mantenimiento.models import NotificacionMantenimiento
                        NotificacionMantenimiento.objects.create(
                            user=req.usuario_solicitante,
                            mensaje=f"✅ Requisición {req.cr8ca_requisicion} fue autorizada.",
                            tipo='SUCCESS',
                        )
                    except Exception:
                        pass

            autorizadas.append(req.cr8ca_requisicion)
        else:
            omitidas.append(req.cr8ca_requisicion)

    return JsonResponse({
        'success': True,
        'dry_run': dry_run,
        'autorizadas': autorizadas,
        'autorizadas_count': len(autorizadas),
        'omitidas_count': len(omitidas),
        'message': (
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"{len(autorizadas)} requisiciones {'serían autorizadas' if dry_run else 'autorizadas'}, "
            f"{len(omitidas)} omitidas (sin aprobación de Ricardo en historial)."
        ),
    })
