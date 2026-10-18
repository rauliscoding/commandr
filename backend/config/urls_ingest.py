"""Ingestion API URLs, served by the separate `ingest` process.

Phase 1 adds /v1/ingest and /v1/heartbeat/<token> here, per
docs/architecture/ingestion-contract.md. Nothing app-facing is mounted on this
URLconf — no sessions, no admin, no auth endpoints.
"""

from django.urls import path

from commandr.core.views import healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
]
