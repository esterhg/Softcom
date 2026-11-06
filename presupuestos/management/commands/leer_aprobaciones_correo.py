"""
Lee un buzón de Microsoft 365 vía Microsoft Graph buscando correos de
resultado de aprobación enviados por Power Automate (alternativa gratuita a
la acción HTTP premium) y actualiza las requisiciones correspondientes.

Se usa Graph (OAuth2 client credentials) porque Microsoft 365 tiene la
autenticación básica de IMAP deshabilitada.

Formato esperado del ASUNTO del correo que envía Power Automate:

    [REQ-RESULTADO] <NUMERO_REQUISICION> | <APROBAR|RECHAZAR> | <TOKEN>

Ejemplo:
    [REQ-RESULTADO] REQ-INST-163-2026 | APROBAR | mi-token

El TOKEN es un secreto compartido (settings.REQ_APROBACION_TOKEN) para evitar
que un correo falsificado dispare cambios de estado.

Settings / variables de entorno:
    REQ_GRAPH_TENANT_ID      (fallback: DYNAMICS_TENANT_ID)
    REQ_GRAPH_CLIENT_ID      (fallback: DYNAMICS_CLIENT_ID)
    REQ_GRAPH_CLIENT_SECRET  (fallback: DYNAMICS_CLIENT_SECRET)
    REQ_GRAPH_MAILBOX        buzón a leer (ej. iem.occ@doih.hn)
    REQ_APROBACION_TOKEN     secreto compartido con Power Automate

Permisos requeridos en la app de Azure (tipo Aplicación, con consentimiento
de administrador):  Mail.ReadWrite  (para leer y marcar como leído).

Uso manual:
    python manage.py leer_aprobaciones_correo
    python manage.py leer_aprobaciones_correo --dry-run
"""

import logging
import re

import msal
import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from presupuestos.models import Requisicion
from presupuestos.utils_documentos import generate_requisicion_pdf
from presupuestos.views_import import _registrar_historial

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

# Regex del asunto: [REQ-RESULTADO] NUMERO | ACCION | TOKEN
_ASUNTO_RE = re.compile(
    r"\[REQ-RESULTADO\]\s*(?P<numero>[^|]+?)\s*\|\s*(?P<accion>APROBAR|RECHAZAR|DENEGAR)\s*(?:\|\s*(?P<token>\S+))?",
    re.IGNORECASE,
)


class GraphError(Exception):
    pass


def _get_graph_token(tenant_id, client_id, client_secret):
    """Obtiene un access token de Graph con client credentials."""
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise GraphError(
            f"No se obtuvo token de Graph: {result.get('error')} - {result.get('error_description')}"
        )
    return result["access_token"]


class Command(BaseCommand):
    help = "Lee el buzón (Microsoft Graph) y procesa los correos de resultado de aprobación de requisiciones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo reporta lo que haría, sin cambiar estados ni marcar correos como leídos.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        tenant_id = getattr(settings, "REQ_GRAPH_TENANT_ID", "")
        client_id = getattr(settings, "REQ_GRAPH_CLIENT_ID", "")
        client_secret = getattr(settings, "REQ_GRAPH_CLIENT_SECRET", "")
        mailbox = getattr(settings, "REQ_GRAPH_MAILBOX", "")
        token_esperado = getattr(settings, "REQ_APROBACION_TOKEN", "")

        if not (tenant_id and client_id and client_secret and mailbox):
            self.stderr.write(
                "Faltan credenciales de Graph (REQ_GRAPH_TENANT_ID / REQ_GRAPH_CLIENT_ID / "
                "REQ_GRAPH_CLIENT_SECRET / REQ_GRAPH_MAILBOX). Abortando."
            )
            return

        try:
            access_token = _get_graph_token(tenant_id, client_id, client_secret)
        except Exception as e:
            self.stderr.write(f"No se pudo autenticar contra Microsoft Graph: {e}")
            logger.error(f"[correo-aprobacion] Error token Graph: {e}")
            return

        headers = {"Authorization": f"Bearer {access_token}"}

        # Correos NO leídos de la bandeja de entrada
        url = (
            f"{GRAPH_BASE}/users/{mailbox}/mailFolders/inbox/messages"
            "?$filter=isRead eq false"
            "&$select=id,subject,from"
            "&$top=50"
        )

        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            self.stderr.write(f"Error de red consultando Graph: {e}")
            logger.error(f"[correo-aprobacion] Error red Graph: {e}")
            return

        if resp.status_code != 200:
            self.stderr.write(f"Graph respondió {resp.status_code}: {resp.text[:500]}")
            logger.error(f"[correo-aprobacion] Graph {resp.status_code}: {resp.text[:500]}")
            return

        mensajes = resp.json().get("value", [])
        if not mensajes:
            self.stdout.write("No hay correos nuevos.")
            return

        procesados = 0
        ignorados = 0

        for msg in mensajes:
            asunto = msg.get("subject") or ""
            remitente = (
                (msg.get("from") or {}).get("emailAddress", {}).get("address", "")
            )

            m = _ASUNTO_RE.search(asunto)
            if not m:
                # No es un correo de resultado; no lo tocamos.
                ignorados += 1
                continue

            numero = m.group("numero").strip()
            accion = m.group("accion").upper().strip()
            token = (m.group("token") or "").strip()

            if token_esperado and token != token_esperado:
                self.stderr.write(
                    f"Token inválido en correo para {numero} (de {remitente}). Ignorado."
                )
                logger.warning(
                    f"[correo-aprobacion] Token inválido para {numero} de {remitente}"
                )
                ignorados += 1
                continue

            self.stdout.write(f"Procesando: {numero} -> {accion} (de {remitente})")

            if dry_run:
                procesados += 1
                continue

            aplicado = self._aplicar_resultado(numero, accion, remitente)

            if aplicado:
                self._marcar_leido(mailbox, msg["id"], headers)
                procesados += 1
            else:
                ignorados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY RUN] ' if dry_run else ''}Hecho. Procesados: {procesados}, ignorados: {ignorados}."
            )
        )

    def _marcar_leido(self, mailbox, message_id, headers):
        """Marca el correo como leído para no reprocesarlo."""
        try:
            r = requests.patch(
                f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}",
                headers={**headers, "Content-Type": "application/json"},
                json={"isRead": True},
                timeout=30,
            )
            if r.status_code not in (200, 204):
                logger.warning(
                    f"[correo-aprobacion] No se pudo marcar como leído ({r.status_code}): {r.text[:300]}"
                )
        except requests.RequestException as e:
            logger.warning(f"[correo-aprobacion] Error marcando como leído: {e}")

    def _aplicar_resultado(self, numero_requisicion, accion, remitente):
        """
        Aplica el resultado a la requisición. Reproduce la lógica del webhook
        requisicion_webhook_update (estado, historial, PDF, notificación).
        Devuelve True si se aplicó (o no hay nada más que hacer), False si no.
        """
        requisicion = Requisicion.objects.filter(
            cr8ca_requisicion=numero_requisicion
        ).first()
        if not requisicion:
            self.stderr.write(f"Requisición {numero_requisicion} no encontrada. Ignorada.")
            logger.warning(f"[correo-aprobacion] {numero_requisicion} no existe")
            return False

        if accion == "APROBAR":
            nuevo_estado = "AUTORIZADO"
        elif accion in ("RECHAZAR", "DENEGAR"):
            nuevo_estado = "RECHAZADO"
        else:
            self.stderr.write(f"Acción desconocida '{accion}' para {numero_requisicion}.")
            return False

        # Idempotencia: ya está en el estado final
        if requisicion.estado_requisicion == nuevo_estado:
            logger.info(
                f"[correo-aprobacion] {numero_requisicion} ya estaba en {nuevo_estado}, ignorando."
            )
            return True

        # Solo desde estados válidos
        if requisicion.estado_requisicion not in ("BORRADOR", "PENDIENTE", "EN_REVISION"):
            self.stdout.write(
                f"{numero_requisicion} está en {requisicion.estado_requisicion}; no se puede {accion}."
            )
            logger.warning(
                f"[correo-aprobacion] {numero_requisicion} en estado "
                f"{requisicion.estado_requisicion}, no se puede {accion}."
            )
            return True  # marcar como leído para no insistir

        estado_anterior = requisicion.estado_requisicion
        descripcion = f"Correo Power Automate: {accion} (remitente {remitente})"

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
                logger.error(f"[correo-aprobacion] Error generando PDF {numero_requisicion}: {e}")

        if requisicion.usuario_solicitante:
            try:
                from mantenimiento.models import NotificacionMantenimiento
                msj = "aprobada" if nuevo_estado == "AUTORIZADO" else "rechazada"
                tipo = "SUCCESS" if nuevo_estado == "AUTORIZADO" else "ERROR"
                NotificacionMantenimiento.objects.create(
                    user=requisicion.usuario_solicitante,
                    mensaje=f"Tu requisición {numero_requisicion} ha sido {msj}.",
                    tipo=tipo,
                )
            except Exception as e:
                logger.error(f"[correo-aprobacion] Error notificación {numero_requisicion}: {e}")

        logger.info(
            f"[correo-aprobacion] {numero_requisicion}: {estado_anterior} -> {nuevo_estado}"
        )
        return True
