"""
Servicios de negocio para el módulo Monitoreo de Elevadores.
Patrón idéntico al WorkOrderService de mantenimiento.
"""
import base64
import logging
import os
from collections import defaultdict

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


class MonitoreoService:

    @staticmethod
    def save_reporte_pdf(reporte_id):
        """
        Genera el PDF del reporte y lo guarda en el campo pdf_archivo del modelo.
        Si ya existe lo sobreescribe (igual que OTs).
        Devuelve los bytes del PDF.
        """
        from .models import ReporteElevador
        from .pdf_builder import build_pdf_bytes

        reporte = (
            ReporteElevador.objects
            .select_related('supervisor', 'tecnico', 'creado_por')
            .prefetch_related('filas__elevador', 'fotos')
            .get(pk=reporte_id)
        )

        pdf_bytes = build_pdf_bytes(reporte)

        filename = f'Reporte_Elevadores_{reporte.pk}.pdf'

        # Borrar anterior si existe
        if reporte.pdf_archivo:
            try:
                reporte.pdf_archivo.delete(save=False)
            except Exception:
                pass

        reporte.pdf_archivo.save(filename, ContentFile(pdf_bytes), save=True)
        logger.info('PDF reporte %s guardado como %s', reporte.pk, filename)
        return pdf_bytes


    @staticmethod
    def save_verif_pdf(reporte_id):
        """
        Genera el PDF de la verificación de alarma/intercomunicador y lo
        guarda en el campo pdf_archivo del modelo. Devuelve los bytes.
        """
        from .models import ReporteVerificacionAlarma
        from .pdf_builder_verif import build_verif_pdf_bytes

        reporte = (
            ReporteVerificacionAlarma.objects
            .select_related('responsable', 'creado_por')
            .prefetch_related('filas__elevador', 'fotos')
            .get(pk=reporte_id)
        )

        pdf_bytes = build_verif_pdf_bytes(reporte)
        filename = f'Verificacion_Elevadores_{reporte.pk}.pdf'

        if reporte.pdf_archivo:
            try:
                reporte.pdf_archivo.delete(save=False)
            except Exception:
                pass

        reporte.pdf_archivo.save(filename, ContentFile(pdf_bytes), save=True)
        logger.info('PDF verificación %s guardado como %s', reporte.pk, filename)
        return pdf_bytes


    @staticmethod
    def save_acc_pdf(reporte_id):
        """
        Genera el PDF del accionamiento manual mensual y lo guarda en el
        campo pdf_archivo del modelo. Devuelve los bytes.
        """
        from .models import ReporteAccionamiento
        from .pdf_builder_acc import build_acc_pdf_bytes

        reporte = (
            ReporteAccionamiento.objects
            .select_related('responsable', 'creado_por')
            .prefetch_related('filas', 'fotos')
            .get(pk=reporte_id)
        )

        pdf_bytes = build_acc_pdf_bytes(reporte)
        filename = f'Accionamiento_Manual_{reporte.pk}.pdf'

        if reporte.pdf_archivo:
            try:
                reporte.pdf_archivo.delete(save=False)
            except Exception:
                pass

        reporte.pdf_archivo.save(filename, ContentFile(pdf_bytes), save=True)
        logger.info('PDF accionamiento %s guardado como %s', reporte.pk, filename)
        return pdf_bytes
