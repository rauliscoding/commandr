"""Celery tasks for monitoring.

Two kinds, kept apart on purpose:

* **egress** (`fetch_status`, `probe_uptime`) run in the `poller` container,
  which can reach the broker and the internet but not Postgres. They take
  everything as arguments — a URL and pre-computed headers; never a secret —
  fetch through `safe_http`, and hand a plain dict to a default-queue task.
* **default** tasks touch the database. Each takes `organization_id`
  explicitly and runs inside `tenant_context` (RLS), and is safe to run twice.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from celery import shared_task
from django.conf import settings
from django.db import connection
from django.utils import timezone

from commandr.core.safe_http import SafeHttpClient, SafeHttpError
from commandr.ingest import heartbeats as hb_state
from commandr.ingest.models import Heartbeat, SigningSecret
from commandr.tenancy.context import tenant_context
from commandr.tenancy.models import Organization, Project

from . import checks, digest, notify, polling, rules, signing
from .models import (
    ErrorOccurrence,
    Event,
    MetricRollup1h,
    MetricRollup1m,
    Notification,
    StatusEndpoint,
    UptimeMonitor,
)

logger = logging.getLogger(__name__)

# A signature is valid for 300 s; a fetch still queued after this is dropped
# rather than sent stale. The next scheduled poll replaces it.
EGRESS_EXPIRES = 240
STATUS_MAX_BYTES = 1_000_000
STATUS_TIMEOUT = 10.0
BATCH = 200


def make_client(**kwargs: Any) -> SafeHttpClient:
    """Indirection so tests can inject an `httpx.MockTransport`."""
    return SafeHttpClient(**kwargs)


def _jitter(interval: int) -> timedelta:
    # Spread polls so a thousand monitors created on the hour do not fire together.
    return timedelta(seconds=random.uniform(0, min(30.0, interval * 0.1)))  # noqa: S311


def _org_ids() -> list[UUID]:
    # Organization is not under RLS; everything per tenant runs in its context.
    return list(Organization.objects.values_list("id", flat=True))


# --- Scheduling (default queue, beat) ---------------------------------------


def status_request(endpoint: StatusEndpoint, secret: str, now: int) -> tuple[str, dict[str, str]]:
    headers = {
        "Accept": "application/json",
        "User-Agent": settings.STATUS_POLLER_USER_AGENT,
        "X-Commandr-Signature": signing.sign(secret, "GET", signing.signed_path(endpoint.url), now),
        "X-Commandr-Project": f"prj_{endpoint.project_id.hex}",
    }
    if endpoint.etag:
        headers["If-None-Match"] = endpoint.etag
    return endpoint.url, headers


def enqueue_status_poll(endpoint: StatusEndpoint) -> None:
    # Also called from on_commit hooks, after the request's tenant is gone.
    with tenant_context(endpoint.organization_id):
        signing_secret = SigningSecret.objects.filter(project_id=endpoint.project_id).first()
        if signing_secret is None:
            return
        # The secret is decrypted here, used, and dropped: only the signature
        # (valid for 300 s) goes into the task message (invariant 2).
        url, headers = status_request(endpoint, signing_secret.get_secret(), int(time.time()))
    fetch_status.apply_async(
        args=[str(endpoint.id), str(endpoint.organization_id), url, headers],
        expires=EGRESS_EXPIRES,
    )


def enqueue_uptime_probe(monitor: UptimeMonitor) -> None:
    probe_uptime.apply_async(
        args=[str(monitor.id), str(monitor.organization_id), monitor.url],
        expires=EGRESS_EXPIRES,
    )


@shared_task(ignore_result=True)
def schedule_polls() -> int:
    """Claim what is due and hand it to the egress queue.

    `select_for_update(skip_locked)` plus moving `next_run_at` before
    enqueueing: two schedulers running at once never enqueue the same poll.
    """
    enqueued = 0
    now = timezone.now()
    for org_id in _org_ids():
        with tenant_context(org_id):
            for monitor in UptimeMonitor.objects.select_for_update(skip_locked=True).filter(
                next_run_at__lte=now
            )[:BATCH]:
                monitor.next_run_at = (
                    now
                    + timedelta(seconds=monitor.interval_seconds)
                    + _jitter(monitor.interval_seconds)
                )
                monitor.save(update_fields=["next_run_at"])
                enqueue_uptime_probe(monitor)
                enqueued += 1
            for endpoint in StatusEndpoint.objects.select_for_update(skip_locked=True).filter(
                next_run_at__lte=now
            )[:BATCH]:
                endpoint.next_run_at = (
                    now
                    + timedelta(seconds=endpoint.interval_seconds)
                    + _jitter(endpoint.interval_seconds)
                )
                endpoint.save(update_fields=["next_run_at"])
                enqueue_status_poll(endpoint)
                enqueued += 1
    return enqueued


# --- Egress (poller container: no database) ----------------------------------


@shared_task(ignore_result=True)
def probe_uptime(monitor_id: str, organization_id: str, url: str) -> None:
    started = time.monotonic()
    result: dict[str, Any] = {"status_code": None, "response_ms": None, "tls_not_after": None}
    try:
        with make_client(allow_http=url.startswith("http://"), max_redirects=3) as client:
            response = client.get(url)
        result["status_code"] = response.status_code
        result["tls_not_after"] = (
            response.tls_not_after.isoformat() if response.tls_not_after else None
        )
        result["error"] = ""
    except SafeHttpError as exc:
        result["error"] = str(exc)  # written to be shown to the customer
    result["response_ms"] = int((time.monotonic() - started) * 1000)
    record_uptime_result.delay(monitor_id, organization_id, result, timezone.now().isoformat())


@shared_task(ignore_result=True)
def fetch_status(endpoint_id: str, organization_id: str, url: str, headers: dict[str, str]) -> None:
    result: dict[str, Any] = {"status_code": None, "etag": "", "body": "", "error": ""}
    try:
        with make_client(
            max_redirects=0, total_timeout=STATUS_TIMEOUT, max_bytes=STATUS_MAX_BYTES
        ) as client:
            response = client.get(url, headers=headers)
        result["status_code"] = response.status_code
        result["etag"] = response.headers.get("etag", "")
        if response.status_code == 200:
            result["body"] = response.content.decode("utf-8", errors="replace")
    except SafeHttpError as exc:
        result["error"] = str(exc)
    record_status_result.delay(endpoint_id, organization_id, result, timezone.now().isoformat())


# --- Recording results (default queue) ---------------------------------------


@shared_task(ignore_result=True)
def record_uptime_result(
    monitor_id: str, organization_id: str, result: dict[str, Any], checked_at: str
) -> None:
    with tenant_context(UUID(organization_id)):
        monitor = (
            UptimeMonitor.objects.select_for_update(of=("self",))
            .select_related("project", "connection")
            .filter(id=monitor_id)
            .first()
        )
        if monitor is None:
            return  # removed while the probe was in flight
        polling.record_uptime(monitor, result, datetime.fromisoformat(checked_at))


@shared_task(ignore_result=True)
def record_status_result(
    endpoint_id: str, organization_id: str, result: dict[str, Any], polled_at: str
) -> None:
    with tenant_context(UUID(organization_id)):
        endpoint = (
            StatusEndpoint.objects.select_for_update(of=("self",))
            .select_related("project", "connection")
            .filter(id=endpoint_id)
            .first()
        )
        if endpoint is None:
            return
        polling.record_status(endpoint, result, datetime.fromisoformat(polled_at))


# --- Time-driven evaluation ----------------------------------------------------


def evaluate_project(project: Project, now: datetime) -> None:
    for hb in Heartbeat.objects.filter(project=project).select_related("project"):
        hb_state.refresh_check(hb, now)
    rules.evaluate_all(project, now)
    checks.mark_stale(project.id, now)


@shared_task(ignore_result=True)
def evaluate() -> None:
    """Every minute: heartbeat deadlines, absence rules, and sources gone quiet."""
    now = timezone.now()
    for org_id in _org_ids():
        with tenant_context(org_id):
            for project in Project.objects.all():
                evaluate_project(project, now)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@shared_task(ignore_result=True)
def send_due_digests() -> int:
    """Each project's digest once per local day, from the digest hour on.

    Idempotent through the notification's `dedupe_key`; "from the hour on"
    (not "at the hour") means a beat outage delays a digest, never skips it.
    """
    sent = 0
    now = timezone.now()
    for org in Organization.objects.all():
        local = now.astimezone(_zone(org.timezone))
        if local.hour < settings.MONITORING_DIGEST_HOUR:
            continue
        with tenant_context(org.id):
            for project in Project.objects.all():
                if digest.send(project, now, local.date()) is not None:
                    sent += 1
    return sent


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError,),  # SMTP and socket errors
    retry_backoff=30,
    retry_backoff_max=1800,
    retry_jitter=True,
    max_retries=8,
)
def send_notification(self: Any, notification_id: str, organization_id: str) -> None:
    with tenant_context(UUID(organization_id)):
        notification = Notification.objects.select_for_update().filter(id=notification_id).first()
        if notification is None or notification.sent_at is not None:
            return  # already sent: running twice sends once
        notify.send(notification)


# --- Housekeeping --------------------------------------------------------------


@shared_task(ignore_result=True)
def maintain_partitions() -> dict[str, int]:
    """Keep three months of point partitions ahead; drop those past retention."""
    cutoff = timezone.now() - timedelta(days=settings.METRICS_RAW_RETENTION_DAYS)
    with connection.cursor() as cursor:
        cursor.execute("SELECT monitoring_ensure_point_partitions(1, 3)")
        created = cursor.fetchone()[0]
        cursor.execute("SELECT monitoring_drop_point_partitions(%s)", [cutoff])
        dropped = cursor.fetchone()[0]
    return {"created": created, "dropped": dropped}


@shared_task(ignore_result=True)
def prune() -> None:
    now = timezone.now()
    for org_id in _org_ids():
        with tenant_context(org_id):
            MetricRollup1m.objects.filter(
                bucket__lt=now - timedelta(days=settings.METRICS_ROLLUP_1M_RETENTION_DAYS)
            ).delete()
            MetricRollup1h.objects.filter(
                bucket__lt=now - timedelta(days=settings.METRICS_ROLLUP_1H_RETENTION_DAYS)
            ).delete()
            old = now - timedelta(days=settings.EVENTS_RETENTION_DAYS)
            Event.objects.filter(ts__lt=old).delete()
            ErrorOccurrence.objects.filter(ts__lt=old).delete()
