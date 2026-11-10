"""
Lee un buzón buscando correos de resultado de aprobación enviados por
Power Automate (alternativa gratuita a la acción HTTP premium) y actualiza
las requisiciones correspondientes.

Dos backends, se elige automáticamente según las variables configuradas:
  - Microsoft Graph (si hay REQ_GRAPH_*): para buzones de Microsoft 365,
    que tienen la autenticación básica de IMAP deshabilitada.
  - IMAP (si hay REQ_IMAP_*): para buzones que sí la permiten, por ejemplo
    Gmail con contraseña de aplicación (imap.gmail.com).

Formato esperado del ASUNTO del correo que envía Power Automate:

    [REQ-RESULTADO] <NUMERO_REQUISICION> | <APROBAR|RECHAZAR> | <TOKEN>

Ejemplo:
    [REQ-RESULTADO] REQ-INST-163-2026 | APROBAR | mi-token

El TOKEN es un secreto compartido (settings.REQ_APROBACION_TOKEN) para evitar
que un correo falsificado dispare cambios de estado.

Settings / variables de entorno (IMAP):
    REQ_IMAP_HOST            ej. imap.gmail.com
    REQ_IMAP_PORT            por defecto 993
    REQ_IMAP_USER            dirección del buzón
    REQ_IMAP_PASSWORD        contraseña de aplicación
    REQ_IMAP_FOLDER          por defecto INBOX

Settings / variables de entorno (Graph):
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

from presupuestos.services.aprobaciones import aplicar_resultado_aprobacion

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

        graph_ok = bool(tenant_id and client_id and client_secret and mailbox)
        imap_ok = bool(
            getattr(settings, "REQ_IMAP_HOST", "")
            and getattr(settings, "REQ_IMAP_USER", "")
            and getattr(settings, "REQ_IMAP_PASSWORD", "")
        )

        if graph_ok:
            self._handle_graph(tenant_id, client_id, client_secret, mailbox, token_esperado, dry_run)
        elif imap_ok:
            self._handle_imap(token_esperado, dry_run)
        else:
            self.stderr.write(
                "Faltan credenciales. Configura IMAP (REQ_IMAP_HOST / REQ_IMAP_USER / "
                "REQ_IMAP_PASSWORD) o Graph (REQ_GRAPH_TENANT_ID / REQ_GRAPH_CLIENT_ID / "
                "REQ_GRAPH_CLIENT_SECRET / REQ_GRAPH_MAILBOX). Abortando."
            )

    # ------------------------------------------------------------------ #
    # Backend IMAP (ej. Gmail con contraseña de aplicación)
    # ------------------------------------------------------------------ #
    def _handle_imap(self, token_esperado, dry_run):
        import email
        import imaplib
        from email.header import decode_header

        host = settings.REQ_IMAP_HOST
        port = int(getattr(settings, "REQ_IMAP_PORT", 993))
        user = settings.REQ_IMAP_USER
        password = settings.REQ_IMAP_PASSWORD
        folder = getattr(settings, "REQ_IMAP_FOLDER", "INBOX") or "INBOX"

        def decode_subject(raw):
            if not raw:
                return ""
            out = ""
            for texto, charset in decode_header(raw):
                if isinstance(texto, bytes):
                    try:
                        out += texto.decode(charset or "utf-8", errors="replace")
                    except (LookupError, TypeError):
                        out += texto.decode("utf-8", errors="replace")
                else:
                    out += texto
            return out

        try:
            conn = imaplib.IMAP4_SSL(host, port)
            conn.login(user, password)
        except Exception as e:
            self.stderr.write(f"No se pudo conectar/autenticar al buzón IMAP: {e}")
            logger.error(f"[correo-aprobacion] Error conexión IMAP: {e}")
            return

        procesados = ignorados = 0
        try:
            conn.select(folder)
            status, data = conn.search(None, "UNSEEN")
            if status != "OK":
                self.stdout.write("No se pudieron buscar correos (SEARCH falló).")
                return
            ids = data[0].split()
            if not ids:
                self.stdout.write("No hay correos nuevos.")
                return

            for msg_id in ids:
                # BODY.PEEK no marca el correo como leído al descargarlo
                status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER])")
                if status != "OK":
                    continue
                mensaje = email.message_from_bytes(msg_data[0][1])
                asunto = decode_subject(mensaje.get("Subject"))
                remitente = mensaje.get("From", "")

                resultado = self._procesar_asunto(asunto, remitente, token_esperado, dry_run)
                if resultado == "procesado":
                    if not dry_run:
                        conn.store(msg_id, "+FLAGS", "\\Seen")
                    procesados += 1
                else:
                    ignorados += 1
        finally:
            for fn in (conn.close, conn.logout):
                try:
                    fn()
                except Exception:
                    pass

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY RUN] ' if dry_run else ''}Hecho (IMAP). Procesados: {procesados}, ignorados: {ignorados}."
        ))

    def _procesar_asunto(self, asunto, remitente, token_esperado, dry_run):
        """Valida el asunto y aplica el resultado. Devuelve 'procesado' o 'ignorado'."""
        m = _ASUNTO_RE.search(asunto or "")
        if not m:
            return "ignorado"

        numero = m.group("numero").strip()
        accion = m.group("accion").upper().strip()
        token = (m.group("token") or "").strip()

        if token_esperado and token != token_esperado:
            self.stderr.write(f"Token inválido en correo para {numero} (de {remitente}). Ignorado.")
            logger.warning(f"[correo-aprobacion] Token inválido para {numero} de {remitente}")
            return "ignorado"

        self.stdout.write(f"Procesando: {numero} -> {accion} (de {remitente})")
        if dry_run:
            return "procesado"
        return "procesado" if self._aplicar_resultado(numero, accion, remitente) else "ignorado"

    # ------------------------------------------------------------------ #
    # Backend Microsoft Graph
    # ------------------------------------------------------------------ #
    def _handle_graph(self, tenant_id, client_id, client_secret, mailbox, token_esperado, dry_run):
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

            resultado = self._procesar_asunto(asunto, remitente, token_esperado, dry_run)
            if resultado == "procesado":
                if not dry_run:
                    self._marcar_leido(mailbox, msg["id"], headers)
                procesados += 1
            else:
                ignorados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY RUN] ' if dry_run else ''}Hecho (Graph). Procesados: {procesados}, ignorados: {ignorados}."
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
        """Delegar en el service; aquí solo se reporta en consola."""
        consumido, mensaje = aplicar_resultado_aprobacion(
            numero_requisicion, accion, origen=remitente
        )
        (self.stdout if consumido else self.stderr).write(mensaje)
        return consumido
