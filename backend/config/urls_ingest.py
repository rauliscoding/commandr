"""Ingestion API URLs, served by the separate `ingest` process.

Per docs/architecture/ingestion-contract.md. Nothing app-facing is mounted on
this URLconf — no sessions, no admin, no auth endpoints.
"""

from django.urls import path

from commandr.core.views import healthz
from commandr.ingest import views
from commandr.ingest.models import PingKind

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("v1/ingest", views.ingest, name="ingest"),
    path("v1/heartbeat/<str:token>", views.heartbeat, name="heartbeat"),
    path(
        "v1/heartbeat/<str:token>/start",
        views.heartbeat,
        {"kind": PingKind.START},
        name="heartbeat-start",
    ),
    path(
        "v1/heartbeat/<str:token>/fail",
        views.heartbeat,
        {"kind": PingKind.FAIL},
        name="heartbeat-fail",
    ),
]
