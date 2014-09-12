from django.conf import settings

from .. import register, Tags, Warning


W003 = Warning(
    "You don't appear to be using Django's built-in "
    "cross-site request forgery protection via the middleware "
    "('django.middleware.csrf.CsrfViewMiddleware' is not in your "
    "MIDDLEWARE_CLASSES). Enabling the middleware is the safest approach "
    "to ensure you don't leave any holes.",
    id='security.W003',
)

W016 = Warning(
    "You have 'django.middleware.csrf.CsrfViewMiddleware' in your "
    "MIDDLEWARE_CLASSES, but you have not set CSRF_COOKIE_SECURE to True. "
    "Using a secure-only CSRF cookie makes it more difficult for network "
    "traffic sniffers to steal the CSRF token.",
    id='security.W016',
)

W017 = Warning(
    "You have 'django.middleware.csrf.CsrfViewMiddleware' in your "
    "MIDDLEWARE_CLASSES, but you have not set CSRF_COOKIE_HTTPONLY to True. "
    "Using an HttpOnly CSRF cookie makes it more difficult for cross-site "
    "scripting attacks to steal the CSRF token.",
    id='security.W017',
)


def _csrf_middleware():
    return "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE_CLASSES


@register(Tags.security, deploy=True)
def check_csrf_middleware(app_configs, **kwargs):
    passed_check = _csrf_middleware()
    return [] if passed_check else [W003]


@register(Tags.security, deploy=True)
def check_csrf_cookie_secure(app_configs, **kwargs):
    passed_check = (
        not _csrf_middleware() or
        settings.CSRF_COOKIE_SECURE
    )
    return [] if passed_check else [W016]


@register(Tags.security, deploy=True)
def check_csrf_cookie_httponly(app_configs, **kwargs):
    passed_check = (
        not _csrf_middleware() or
        settings.CSRF_COOKIE_HTTPONLY
    )
    return [] if passed_check else [W017]
