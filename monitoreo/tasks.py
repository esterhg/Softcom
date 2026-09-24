"""
Tareas Celery para el módulo Monitoreo de Elevadores.
Patrón idéntico a mantenimiento.tasks.task_generar_ot_pdf
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='monitoreo.tasks.task_generar_reporte_pdf')
def task_generar_reporte_pdf(reporte_id):
    """
    Tarea asíncrona: genera y guarda el PDF del reporte de elevadores.
    Se dispara en background al crear/editar un reporte.
    """
    try:
        logger.info('Iniciando generación de PDF para Reporte Elevadores #%s', reporte_id)
        from .services import MonitoreoService
        MonitoreoService.save_reporte_pdf(reporte_id)
        logger.info('PDF Reporte Elevadores #%s generado exitosamente.', reporte_id)
        return {'status': 'success', 'reporte_id': reporte_id}
    except Exception as exc:
        logger.error('Error generando PDF Reporte Elevadores #%s: %s', reporte_id, exc, exc_info=True)
        return {'status': 'error', 'message': str(exc)}
