from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
import mimetypes
import logging

logger = logging.getLogger(__name__)

@login_required
def media_proxy(request, path):
    """
    Proxy de medios usando el motor de storage de Django.
    Usa automáticamente las credenciales de MinIO (boto3)
    para saltarse el error 403 Forbidden.
    """
    clean_path = path.lstrip('/')

    try:
        # Abrir directamente sin exists() previo — más rápido y evita
        # doble llamada a MinIO que puede causar timeouts.
        file_obj = default_storage.open(clean_path)

        # Detectar Content-Type por extensión para que el navegador
        # muestre imágenes correctamente en lugar de descargarlas.
        content_type, _ = mimetypes.guess_type(clean_path)
        content_type = content_type or 'application/octet-stream'

        response = FileResponse(file_obj, content_type=content_type)
        # Cache en el navegador por 1 hora para no recargar en cada visita
        response['Cache-Control'] = 'private, max-age=3600'
        return response

    except FileNotFoundError:
        logger.warning(f"Archivo no encontrado en MinIO: {clean_path}")
        return HttpResponseNotFound("Archivo no encontrado.")
    except Exception as e:
        logger.error(f"Error fatal en MinIO Proxy [{clean_path}]: {str(e)}")
        return HttpResponseNotFound(f"Error al acceder al archivo.")
