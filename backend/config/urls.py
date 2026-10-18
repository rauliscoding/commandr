"""App URLs, served by the `web` process behind Caddy on the app origin.

The ingestion API has its own URLconf (`config.urls_ingest`) and its own process,
so a flood of customer telemetry can never slow the app down.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from commandr.core.views import csrf, healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("api/csrf/", csrf, name="csrf"),
    # allauth headless: /api/auth/browser/v1/... (session-based, ADR 0003)
    path("api/auth/", include("allauth.headless.urls")),
    # allauth's own views are still needed for OAuth provider callbacks.
    path("accounts/", include("allauth.urls")),
    path("api/", include("commandr.tenancy.urls")),
    path("api/", include("commandr.integrations.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Never exposed publicly in production: Caddy only routes /admin/ from the
    # private tunnel. See docs/practices/security.md § Infrastructure.
    path("admin/", admin.site.urls),
]
