"""
Servicio: aplicar el resultado de una aprobación de requisición.

Lo usa el lector de correos de Power Automate (management command
leer_aprobaciones_correo). Reproduce la lógica del webhook
requisicion_webhook_update: estado, historial, fecha de aprobación, PDF y
notificación al solicitante. El correo a Procura / Procura_Tecnica lo envía la
señal post_save de Requisicion al pasar a AUTORIZADO.

No recibe `request`.
"""

import logging

from django.utils import timezone

from presupuestos.models import Requisicion

logger = logging.getLogger(__name__)

ACCION_A_ESTADO = {
    "APROBAR": "AUTORIZADO",
    "RECHAZAR": "RECHAZADO",
    "DENEGAR": "RECHAZADO",
}

ESTADOS_PERMITIDOS = ("BORRADOR", "PENDIENTE", "EN_REVISION")


def aplicar_resultado_aprobacion(numero_requisicion, accion, origen=""):
    """
    Aplica APROBAR / RECHAZAR a la requisición indicada.

    Devuelve (consumido, mensaje):
      - consumido=True  -> el resultado ya no requiere reintento (se aplicó, ya
        estaba aplicado o el estado actual no lo permite). El correo puede
        marcarse como leído.
      - consumido=False -> no se pudo aplicar (requisición inexistente o acción
        desconocida).
    """
    from presupuestos.utils_documentos import generate_requisicion_pdf
    from presupuestos.views_import import _registrar_historial

    accion = (accion or "").upper().strip()
    nuevo_estado = ACCION_A_ESTADO.get(accion)
    if not nuevo_estado:
        return False, f"Acción desconocida '{accion}' para {numero_requisicion}."

    requisicion = Requisicion.objects.filter(cr8ca_requisicion=numero_requisicion).first()
    if not requisicion:
        logger.warning(f"[aprobacion] {numero_requisicion} no existe")
        return False, f"Requisición {numero_requisicion} no encontrada."

    # Idempotencia
    if requisicion.estado_requisicion == nuevo_estado:
        return True, f"{numero_requisicion} ya estaba en {nuevo_estado}."

    if requisicion.estado_requisicion not in ESTADOS_PERMITIDOS:
        logger.warning(
            f"[aprobacion] {numero_requisicion} en estado "
            f"{requisicion.estado_requisicion}, no se puede {accion}."
        )
        return True, (
            f"{numero_requisicion} está en {requisicion.estado_requisicion}; "
            f"no se puede {accion}."
        )

    estado_anterior = requisicion.estado_requisicion
    descripcion = f"Power Automate: {accion}"
    if origen:
        descripcion += f" (remitente {origen})"

    _registrar_historial(requisicion, nuevo_estado, descripcion=descripcion)
    requisicion.estado_requisicion = nuevo_estado
    if nuevo_estado == "AUTORIZADO":
        requisicion.fecha_aprobacion = timezone.now()

    # save() dispara la señal post_save -> correo a Procura / Procura_Tecnica
    requisicion.save()

    if nuevo_estado == "AUTORIZADO":
        try:
            generate_requisicion_pdf(requisicion)
        except Exception as e:
            logger.error(f"[aprobacion] Error generando PDF {numero_requisicion}: {e}")

    if requisicion.usuario_solicitante:
        try:
            from mantenimiento.models import NotificacionMantenimiento
            aprobada = nuevo_estado == "AUTORIZADO"
            NotificacionMantenimiento.objects.create(
                user=requisicion.usuario_solicitante,
                mensaje=(
                    f"Tu requisición {numero_requisicion} ha sido "
                    f"{'aprobada' if aprobada else 'rechazada'}."
                ),
                tipo="SUCCESS" if aprobada else "ERROR",
            )
        except Exception as e:
            logger.error(f"[aprobacion] Error notificación {numero_requisicion}: {e}")

    logger.info(f"[aprobacion] {numero_requisicion}: {estado_anterior} -> {nuevo_estado}")
    return True, f"{numero_requisicion}: {estado_anterior} -> {nuevo_estado}"
