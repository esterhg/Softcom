import unicodedata

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect


def _norm(text):
    """Minúsculas y sin acentos, para comparar nombres de grupo sin errores de tipeo."""
    text = unicodedata.normalize('NFD', str(text))
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn').casefold().strip()


class AppOnlyUsersMiddleware:
    """
    Usuarios "solo app" (p.ej. técnicos): su único destino es /app/.

    - Cualquier intento de entrar a /admin/ los redirige a /app/.
    - Si caen en la landing (/) o en /inicio/, también van a /app/.

    Un usuario es "solo app" si NO es superusuario y pertenece a alguno de los
    grupos listados en settings.APP_ONLY_GROUPS. Si la lista está vacía, no se
    bloquea a nadie.

    Quedan exentas las rutas de login, logout y recuperación de contraseña, para
    que puedan iniciar y cerrar sesión (el login de la app usa /admin/login/).
    """
    APP_URL = '/app/'
    LANDING_PATHS = ('/', '/inicio/')
    ADMIN_PREFIX = '/admin/'
    ADMIN_PUBLIC_PREFIXES = (
        '/admin/login/',
        '/admin/logout/',
        '/admin/password_reset/',
        '/admin/reset/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_redirect(request):
            return HttpResponseRedirect(self.APP_URL)
        return self.get_response(request)

    def _should_redirect(self, request):
        path = request.path
        in_admin = path == '/admin' or path.startswith(self.ADMIN_PREFIX)
        if in_admin:
            if path.startswith(self.ADMIN_PUBLIC_PREFIXES):
                return False
        elif path not in self.LANDING_PATHS:
            return False
        # Solo ahora (ruta relevante) se consulta al usuario y sus grupos.
        return self._is_app_only(request.user)

    @staticmethod
    def _is_app_only(user):
        if not user.is_authenticated or user.is_superuser:
            return False
        configured = {_norm(n) for n in getattr(settings, 'APP_ONLY_GROUPS', [])}
        if not configured:
            return False
        user_groups = user.groups.values_list('name', flat=True)
        return any(_norm(name) in configured for name in user_groups)


class ImpersonateMiddleware(MiddlewareMixin):

    STOP_PATHS = ('/admin/logout/', '/logout/', '/core/impersonate/stop/', '/admin/login/')

    def _stop_impersonation(self, request):
        """Stop impersonation and re-login as superuser."""
        impersonator_id = request.session.get('impersonator_id')
        request.session.pop('impersonate_as_id', None)
        request.session.pop('impersonator_id', None)
        if impersonator_id:
            try:
                from django.contrib.auth import login as auth_login
                superuser = User.objects.get(pk=impersonator_id, is_superuser=True)
                auth_login(request, superuser, backend='django.contrib.auth.backends.ModelBackend')
            except User.DoesNotExist:
                pass

    def process_request(self, request):
        impersonate_as_id = request.session.get('impersonate_as_id')
        if not impersonate_as_id:
            request.is_impersonating = False
            return

        if not request.user.is_authenticated:
            # Session has impersonate keys but user not authenticated — clean up
            request.session.pop('impersonate_as_id', None)
            request.session.pop('impersonator_id', None)
            request.is_impersonating = False
            return

        # If hitting stop/logout/login paths, stop impersonation and redirect to admin
        if request.path in self.STOP_PATHS:
            self._stop_impersonation(request)
            request._impersonate_redirect = redirect('/admin/')
            return

        # Impersonate the user
        try:
            impersonated_user = User.objects.get(pk=impersonate_as_id)
            request.user = impersonated_user
            request.impersonator_id = request.session.get('impersonator_id')
            request.is_impersonating = True
        except User.DoesNotExist:
            request.session.pop('impersonate_as_id', None)
            request.session.pop('impersonator_id', None)
            request.is_impersonating = False

    def process_response(self, request, response):
        if hasattr(request, '_impersonate_redirect'):
            return request._impersonate_redirect
        # If a view redirected to login while impersonating, intercept
        if (getattr(request, 'is_impersonating', False) and
                response.status_code == 302 and
                '/login/' in response.get('Location', '')):
            self._stop_impersonation(request)
            return redirect('/admin/')
        return response
