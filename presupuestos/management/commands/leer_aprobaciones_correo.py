"""
Lee un buzón IMAP buscando correos de resultado de aprobación enviados por
Power Automate (sin necesidad de la acción HTTP premium) y actualiza las
requisiciones correspondientes.

Formato esperado del ASUNTO del correo que envía Power Automate:

    [REQ-RESULTADO] <NUMERO_REQUISICION> | <APROBAR|RECHAZAR> | <TOKEN>

Ejemplos:
    [REQ-RESULTADO] REQ-00123-2026 | APROBAR | mi-token-secreto
    [REQ-RESULTADO] REQ-00123-2026 | RECHAZAR | mi-token-secreto

El TOKEN es un secreto compartido (settings.REQ_APROBACION_TOKEN) para evitar
que un correo falsificado dispare cambios de estado.

Variables de entorno / settings usadas:
    REQ_IMAP_HOST        (ej. outlook.office365.com)
    REQ_IMAP_PORT        (por defecto 993)
    REQ_IMAP_USER        (usuario / correo del buzón)
    REQ_IMAP_PASSWORD    (contraseña o App Password)
    REQ_IMAP_FOLDER      (por defecto INBOX)
    REQ_APROBACION_TOKEN (secreto compartido con Power Automate)

Uso manual:
    python manage.py leer_aprobaciones_correo
    python manage.py leer_aprobaciones_correo --dry-run

Se recomienda ejecutarlo periódicamente con Celery Beat (cada 1-2 min).
"""

import email
import imaplib
import logging
import re
from email.header import decode_header

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from presupuestos.models import Requisicion, RequisicionHistorial
from presupuestos.views_import import _registrar_historial
from presupuestos.utils_documentos import generate_requisicion_pdf

logger = logging.getLogger(__name__)

# Regex del asunto: [REQ-RESULTADO] NUMERO | ACCION | TOKEN
_ASUNTO_RE = re.compile(
    r"\[REQ-RESULTADO\]\s*(?P<numero>[^|]+?)\s*\|\s*(?P<accion>APROBAR|RECHAZAR|DENEGAR)\s*(?:\|\s*(?P<token>\S+))?",
    re.IGNORECASE,
)


def _decode_subject(raw_subject):
    """Decodifica el asunto del correo (que puede venir codificado MIME)."""
    if not raw_subject:
        return ""
    partes = decode_header(raw_subject)
    resultado = ""
    for texto, charset in partes:
        if isinstance(texto, bytes):
            try:
                resultado += texto.decode(charset or "utf-8", errors="replace")
            except (LookupError, TypeError):
                resultado += texto.decode("utf-8", errors="replace")
        else:
            resultado += texto
    return resultado


class Command(BaseCommand):
    help = "Lee el buzón IMAP y procesa los correos de resultado de aprobación de requisiciones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo reporta lo que haría, sin cambiar estados ni marcar correos como leídos.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        host = getattr(settings, "REQ_IMAP_HOST", "")
        port = int(getattr(settings, "REQ_IMAP_PORT", 993))
        user = getattr(settings, "REQ_IMAP_USER", "")
        password = getattr(settings, "REQ_IMAP_PASSWORD", "")
        folder = getattr(settings, "REQ_IMAP_FOLDER", "INBOX")
        token_esperado = getattr(settings, "REQ_APROBACION_TOKEN", "")

        if not (host and user and password):
            self.stderr.write(
                "Faltan credenciales IMAP (REQ_IMAP_HOST / REQ_IMAP_USER / REQ_IMAP_PASSWORD). Abortando."
            )
            return

        try:
            conn = imaplib.IMAP4_SSL(host, port)
            conn.login(user, password)
        except Exception as e:
            self.stderr.write(f"No se pudo conectar/autenticar al buzón IMAP: {e}")
            logger.error(f"Error conexión IMAP aprobaciones: {e}")
            return

        procesados = 0
        ignorados = 0

        try:
            conn.select(folder)

            # Buscar correos NO leídos cuyo asunto contenga el marcador.
            # IMAP SEARCH no es muy potente con SUBJECT + texto con corchetes,
            # así que filtramos NO leídos y validamos el asunto con regex.
            status, data = conn.search(None, "UNSEEN")
            if status != "OK":
                self.stdout.write("No se pudieron buscar correos (SEARCH falló).")
                return

            ids = data[0].split()
            if not ids:
                self.stdout.write("No hay correos nuevos.")
                return

            for msg_id in ids:
                status, msg_data = conn.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                mensaje = email.message_from_bytes(msg_data[0][1])
                asunto = _decode_subject(mensaje.get("Subject"))
                remitente = mensaje.get("From", "")

                m = _ASUNTO_RE.search(asunto)
                if not m:
                    # No es un correo de resultado; lo dejamos como está.
                    ignorados += 1
                    continue

                numero = m.group("numero").strip()
                accion = m.group("accion").upper().strip()
                token = (m.group("token") or "").strip()

                # Validación de token (si hay token configurado)
                if token_esperado and token != token_esperado:
                    self.stderr.write(
                        f"Token inválido en correo para {numero} (de {remitente}). Ignorado."
                    )
                    logger.warning(
                        f"Correo de aprobación con token inválido para {numero} de {remitente}"
                    )
                    ignorados += 1
                    continue

                self.stdout.write(f"Procesando: {numero} -> {accion} (de {remitente})")

                if dry_run:
                    procesados += 1
                    continue

                aplicado = self._aplicar_resultado(numero, accion, remitente)

                if aplicado:
                    # Marcar como leído para no reprocesar
                    conn.store(msg_id, "+FLAGS", "\\Seen")
                    procesados += 1
                else:
                    ignorados += 1

        finally:
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn.logout()
            except Exception:
                pass

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY RUN] ' if dry_run else ''}Hecho. Procesados: {procesados}, ignorados: {ignorados}."
            )
        )

    def _aplicar_resultado(self, numero_requisicion, accion, remitente):
        """
        Aplica el resultado a la requisición. Reproduce la misma lógica del
        webhook requisicion_webhook_update (estado, historial, PDF, notificación).
        Devuelve True si se aplicó, False si no.
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

        # Idempotencia: si ya está en el estado final, no reprocesar
        if requisicion.estado_requisicion == nuevo_estado:
            logger.info(
                f"[correo-aprobacion] {numero_requisicion} ya estaba en {nuevo_estado}, ignorando."
            )
            return True  # marcar como leído igual

        # Solo permitir desde estados válidos
        if requisicion.estado_requisicion not in ("BORRADOR", "PENDIENTE", "EN_REVISION"):
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

        requisicion.save()

        # Generar PDF si se aprobó (dispara también la señal post_save -> Procura)
        if nuevo_estado == "AUTORIZADO":
            try:
                generate_requisicion_pdf(requisicion)
            except Exception as e:
                logger.error(f"[correo-aprobacion] Error generando PDF {numero_requisicion}: {e}")

        # Notificación flotante al solicitante
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
