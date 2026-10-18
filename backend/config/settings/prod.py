"""Production (and staging). Same image; only the environment differs."""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

# Caddy terminates TLS and sets X-Forwarded-Proto. Trust it only because Caddy is
# the only thing that can reach the app (internal Docker network).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = False  # Caddy redirects; Django redirecting too loops health checks
SECURE_HSTS_SECONDS = 63072000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# __Host- cookies: Secure, path=/, no Domain — cannot be set by a subdomain.
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-sessionid"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_NAME = "__Host-csrftoken"

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
