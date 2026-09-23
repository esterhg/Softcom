from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Requisicion, OrdenCompra
from notificaciones.utils import crear_notificacion
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Requisicion)
def capture_old_requisicion_status(sender, instance, **kwargs):
    try:
        if instance.pk:
            instance._old_estado = Requisicion.objects.get(pk=instance.pk).estado_requisicion
        else:
            instance._old_estado = None
    except Requisicion.DoesNotExist:
        instance._old_estado = None


@receiver(post_save, sender=Requisicion)
def handle_requisicion_notifications(sender, instance, created, **kwargs):
    req_url = f"/presupuestos/requisiciones/{instance.cr8ca_requisicionid}/pdf/"
    req_codigo = instance.cr8ca_requisicion or str(instance.cr8ca_requisicionid)[:8]
    old = getattr(instance, '_old_estado', None)

    # Nueva requisición pendiente de autorizar
    if created and instance.estado_requisicion == 'PENDIENTE' and instance.aprobador:
        crear_notificacion(
            user=instance.aprobador,
            titulo="Requisición Pendiente de Autorizar",
            mensaje=f"La requisición {req_codigo} está esperando tu autorización.",
            tipo='INFO',
            modulo='PRESUPUESTOS',
            enlace=req_url,
            icono='document-text-outline',
        )

    # Autorizada -> notificar al solicitante + enviar correo a Procura
    elif old != 'AUTORIZADO' and instance.estado_requisicion == 'AUTORIZADO' and instance.usuario_solicitante:
        crear_notificacion(
            user=instance.usuario_solicitante,
            titulo="Requisición Autorizada",
            mensaje=f"La requisición {req_codigo} ha sido autorizada.",
            tipo='SUCCESS',
            modulo='PRESUPUESTOS',
            enlace=req_url,
            icono='checkmark-circle-outline',
        )
        # Enviar correo a Procura
        _notificar_procura_requisicion_autorizada(instance, req_codigo)
        # Actualizar precios de materiales al autorizar
        _actualizar_precios_materiales(instance)

    # Rechazada -> notificar al solicitante
    elif old != 'RECHAZADO' and instance.estado_requisicion == 'RECHAZADO' and instance.usuario_solicitante:
        crear_notificacion(
            user=instance.usuario_solicitante,
            titulo="Requisición Rechazada",
            mensaje=f"La requisición {req_codigo} ha sido rechazada.",
            tipo='ERROR',
            modulo='PRESUPUESTOS',
            enlace=req_url,
            icono='close-circle-outline',
        )

    # Procesada a OC
    elif old != 'EN_ORDEN_COMPRA' and instance.estado_requisicion == 'EN_ORDEN_COMPRA' and instance.usuario_solicitante:
        crear_notificacion(
            user=instance.usuario_solicitante,
            titulo="Requisición Procesada a OC",
            mensaje=f"La requisición {req_codigo} ha sido procesada a Orden de Compra.",
            tipo='SUCCESS',
            modulo='PRESUPUESTOS',
            enlace=req_url,
            icono='receipt-outline',
        )


@receiver(pre_save, sender=OrdenCompra)
def capture_old_oc_status(sender, instance, **kwargs):
    try:
        if instance.pk:
            instance._old_estado = OrdenCompra.objects.get(pk=instance.pk).estado
        else:
            instance._old_estado = None
    except OrdenCompra.DoesNotExist:
        instance._old_estado = None


@receiver(post_save, sender=OrdenCompra)
def handle_oc_notifications(sender, instance, created, **kwargs):
    oc_url = f"/presupuestos/ordenes-compra/{instance.id}/detalle/"
    old = getattr(instance, '_old_estado', None)

    # OC creada
    if created:
        if instance.requisicion and instance.requisicion.usuario_solicitante:
            crear_notificacion(
                user=instance.requisicion.usuario_solicitante,
                titulo="Orden de Compra Generada",
                mensaje=f"La OC {instance.numero_oc} ha sido generada.",
                tipo='SUCCESS',
                modulo='PRESUPUESTOS',
                enlace=oc_url,
                icono='receipt-outline',
            )

    # OC confirmada
    if old != 'CONFIRMADA' and instance.estado == 'CONFIRMADA' and instance.creado_por:
        crear_notificacion(
            user=instance.creado_por,
            titulo="OC Confirmada",
            mensaje=f"La OC {instance.numero_oc} ha sido confirmada por el proveedor.",
            tipo='SUCCESS',
            modulo='PRESUPUESTOS',
            enlace=oc_url,
            icono='checkmark-circle-outline',
        )

    # OC recibida
    if old != 'RECIBIDA' and instance.estado == 'RECIBIDA' and instance.creado_por:
        crear_notificacion(
            user=instance.creado_por,
            titulo="OC Recibida",
            mensaje=f"La OC {instance.numero_oc} ha sido marcada como recibida.",
            tipo='SUCCESS',
            modulo='PRESUPUESTOS',
            enlace=oc_url,
            icono='archive-outline',
        )

    # OC cancelada
    if old != 'CANCELADA' and instance.estado == 'CANCELADA':
        if instance.creado_por:
            crear_notificacion(
                user=instance.creado_por,
                titulo="OC Cancelada",
                mensaje=f"La OC {instance.numero_oc} ha sido cancelada.",
                tipo='WARNING',
                modulo='PRESUPUESTOS',
                enlace=oc_url,
                icono='close-outline',
            )
        if instance.requisicion and instance.requisicion.usuario_solicitante:
            crear_notificacion(
                user=instance.requisicion.usuario_solicitante,
                titulo="OC Cancelada",
                mensaje=f"La OC {instance.numero_oc} asociada a tu requisición ha sido cancelada.",
                tipo='WARNING',
                modulo='PRESUPUESTOS',
                enlace=oc_url,
                icono='close-outline',
            )


def _notificar_procura_requisicion_autorizada(requisicion, req_codigo):
    """
    Envía correo al grupo Procura (y a PROCURA_EMAIL si está configurado)
    cuando una requisición cambia a estado AUTORIZADO.
    Falla silenciosamente para no bloquear el flujo principal.
    """
    from django.core.mail import send_mail, BadHeaderError
    from django.contrib.auth.models import Group
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    try:
        # Recolectar destinatarios: grupo Procura en Django
        destinatarios = set()
        grupo = Group.objects.filter(name__in=['Procura', 'PROCURA']).first()
        if grupo:
            emails_grupo = grupo.user_set.filter(
                is_active=True
            ).exclude(email='').values_list('email', flat=True)
            destinatarios.update(emails_grupo)

        # También incluir PROCURA_EMAIL del settings (puede ser una lista separada por comas)
        procura_email_setting = getattr(settings, 'PROCURA_EMAIL', '')
        if procura_email_setting:
            for addr in procura_email_setting.split(','):
                addr = addr.strip()
                if addr:
                    destinatarios.add(addr)

        if not destinatarios:
            logger.info(
                f"No hay destinatarios Procura configurados, omitiendo correo para {req_codigo}"
            )
            return

        solicitante_nombre = ''
        if requisicion.usuario_solicitante:
            solicitante_nombre = (
                requisicion.usuario_solicitante.get_full_name()
                or requisicion.usuario_solicitante.username
            )

        site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
        link_req = f"{site_url}/presupuestos/requisiciones/{requisicion.cr8ca_requisicionid}/"

        asunto = f"✅ Requisición Aprobada: {req_codigo}"

        # Construir cuerpo HTML
        html_message = f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Outfit', Arial, sans-serif; background: #eff2f5; margin: 0; padding: 24px; }}
    .card {{ background: #fff; border: 1px solid #d9d9d9; border-radius: 8px;
             max-width: 560px; margin: 0 auto; padding: 32px;
             box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
    .badge {{ display: inline-block; background: #dcfce7; color: #166534;
              padding: 4px 12px; border-radius: 4px; font-size: 13px; font-weight: 600; }}
    h2 {{ color: #32363a; margin-top: 0; }}
    .field {{ margin: 8px 0; font-size: 14px; color: #32363a; }}
    .field span {{ color: #6a6d70; }}
    .btn {{ display: inline-block; margin-top: 20px; padding: 10px 20px;
            background: #0070f2; color: #fff; text-decoration: none;
            border-radius: 4px; font-size: 14px; font-weight: 600; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #6a6d70; border-top: 1px solid #d9d9d9; padding-top: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">Aprobada</span>
    <h2 style="margin-top:16px">Requisición lista para procesar</h2>
    <div class="field"><span>Número:</span> <strong>{req_codigo}</strong></div>
    <div class="field"><span>Asunto:</span> {requisicion.cr8ca_asunto or '—'}</div>
    <div class="field"><span>Solicitante:</span> {solicitante_nombre or '—'}</div>
    <div class="field"><span>Fecha aprobación:</span> {requisicion.fecha_aprobacion.strftime('%d/%m/%Y %H:%M') if requisicion.fecha_aprobacion else '—'}</div>
    <a class="btn" href="{link_req}">Ver Requisición</a>
    <div class="footer">Este correo fue generado automáticamente por SoftCom CCG.</div>
  </div>
</body>
</html>
"""
        texto_plano = (
            f"Requisición Aprobada: {req_codigo}\n"
            f"Asunto: {requisicion.cr8ca_asunto or '—'}\n"
            f"Solicitante: {solicitante_nombre or '—'}\n"
            f"Ver: {link_req}"
        )

        send_mail(
            subject=asunto,
            message=texto_plano,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(destinatarios),
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(
            f"Correo de requisición autorizada enviado a Procura ({len(destinatarios)} destinatarios) "
            f"para {req_codigo}"
        )
    except BadHeaderError:
        logger.error(f"BadHeaderError al enviar correo Procura para {req_codigo}")
    except Exception as e:
        logger.error(f"Error enviando correo a Procura para {req_codigo}: {e}")



    """
    Actualiza el precio_estimado de cada Material vinculado a los artículos
    de la requisición aprobada (EN_ORDEN_COMPRA).
    Solo actualiza si el artículo tiene material vinculado y precio > 0.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from .models import ArticuloRequisicion

        articulos = ArticuloRequisicion.objects.filter(
            requisicion=requisicion,
            material__isnull=False,
        ).exclude(
            cr8ca_costoaproximado__isnull=True
        ).exclude(
            cr8ca_costoaproximado=0
        ).select_related('material')

        materiales_actualizados = 0
        for articulo in articulos:
            material = articulo.material
            nuevo_precio = articulo.cr8ca_costoaproximado

            if nuevo_precio and nuevo_precio > 0:
                material.precio_estimado = nuevo_precio
                material.save(update_fields=['precio_estimado', 'actualizado_en'])
                materiales_actualizados += 1

        if materiales_actualizados:
            logger.info(
                f"Precios actualizados: {materiales_actualizados} materiales "
                f"desde requisición {requisicion.cr8ca_requisicion}"
            )
    except Exception as e:
        logger.warning(f"Error actualizando precios desde requisición: {e}")
