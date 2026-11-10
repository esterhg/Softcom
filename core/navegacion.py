"""
Estándar de navegación de Softcom.

- Las pantallas de consulta (listas, reportes) guardan su estado en la URL
  (GET): filtros, búsqueda y página. Así funcionan el historial, la recarga y
  los enlaces compartidos. ``querystring_sin`` arma esos enlaces.
- Las acciones que modifican datos usan POST y terminan con una redirección
  (Post/Redirect/Get). El destino puede venir en ``?next=``; ``url_retorno``
  lo valida para evitar redirecciones abiertas a otros dominios.
"""
from django.utils.http import url_has_allowed_host_and_scheme


def querystring_sin(params, *claves):
    """Querystring de ``params`` (QueryDict) sin las ``claves`` indicadas.

    Uso típico: enlaces de paginación que conservan los filtros actuales,
    ``querystring_sin(request.GET, 'page')``.
    """
    copia = params.copy()
    for clave in claves:
        copia.pop(clave, None)
    return copia.urlencode()


def url_retorno(request, default, param='next'):
    """URL de regreso segura para redirecciones (PRG) y botones "Volver".

    Usa ``request.POST[param]`` o ``request.GET[param]`` si apunta a este mismo
    sitio; en caso contrario devuelve ``default``.
    """
    destino = request.POST.get(param) or request.GET.get(param)
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return default
