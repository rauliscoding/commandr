"""The public ingestion API (docs/architecture/ingestion-contract.md).

Plain Django views on their own URLconf, served by the `ingest` process: no
sessions, no cookies, no CSRF (server-to-server with bearer credentials), and
full control over the order of the cheap checks before the expensive ones.
Errors are RFC 9457 problem documents.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from commandr.core.net import client_ip
from commandr.tenancy.context import tenant_context

from . import cardinality, heartbeats, lookup, ratelimit, stream
from .models import CredentialKind, Heartbeat, IngestKey, PingKind
from .validation import EnvelopeError, Rejection, TooManyItems, validate_batch

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL = 24 * 3600
LAST_USED_EVERY = 60
MAX_FAIL_BODY = 10_000


def problem(
    status: int, title: str, detail: str = "", *, code: str = "", retry_after: int | None = None
) -> JsonResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    if code:
        body["code"] = code
    response = JsonResponse(body, status=status, content_type="application/problem+json")
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    return response


def _bearer(request: HttpRequest) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _too_large(request: HttpRequest) -> bool:
    try:
        length = int(request.headers.get("Content-Length") or 0)
    except ValueError:
        return True
    return length > settings.INGEST_MAX_BODY_BYTES


def _touch_key(key: IngestKey, request: HttpRequest) -> None:
    """Record last use for the UI, at most once a minute per key."""
    if not cache.add(f"ingest:touch:{key.id}", 1, LAST_USED_EVERY):
        return
    key.last_used_at = timezone.now()
    key.last_used_ip = client_ip(request)
    key.save(update_fields=["last_used_at", "last_used_ip"])


@csrf_exempt
@require_http_methods(["POST"])
@transaction.non_atomic_requests
def ingest(request: HttpRequest) -> HttpResponse:
    if _too_large(request):
        return problem(413, "Request too large", "The body must be at most 1 MB.", code="too_large")

    credential = _bearer(request)
    found = lookup.find(credential, CredentialKind.INGEST_KEY) if credential else None
    if found is None:
        return problem(401, "Unauthorized", "Missing or invalid ingest key.", code="invalid_key")

    retry = ratelimit.hit(f"key:{found.target_id}", settings.INGEST_RATE_LIMIT_PER_MINUTE)
    if retry is not None:
        return problem(429, "Too many requests", code="rate_limited", retry_after=retry)

    idem_header = request.headers.get("Idempotency-Key", "")
    if len(idem_header) > 128:
        return problem(400, "Bad request", "Idempotency-Key is at most 128 characters.")
    idem_key = (
        f"ingest:idem:{found.target_id}:{hashlib.sha256(idem_header.encode()).hexdigest()}"
        if idem_header
        else None
    )
    if idem_key:
        previous = cache.get(idem_key)
        if previous is not None:
            return JsonResponse(previous, status=202)

    if len(request.body) > settings.INGEST_MAX_BODY_BYTES:  # chunked: no Content-Length
        return problem(413, "Request too large", "The body must be at most 1 MB.", code="too_large")
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return problem(400, "Bad request", "The body is not valid JSON.", code="malformed")

    now = timezone.now()
    try:
        batch = validate_batch(payload, now=now, max_items=settings.INGEST_MAX_ITEMS)
    except TooManyItems as exc:
        return problem(413, "Request too large", str(exc), code="too_many_items")
    except EnvelopeError as exc:
        return problem(400, "Bad request", str(exc), code="malformed")

    with tenant_context(found.organization_id):
        key = (
            IngestKey.objects.select_related("connection")
            .filter(id=found.target_id, revoked_at__isnull=True)
            .first()
        )
        if key is None:
            return problem(
                401, "Unauthorized", "Missing or invalid ingest key.", code="invalid_key"
            )
        for index, message in cardinality.check(key.project_id, batch.metrics).items():
            batch.rejected.append(Rejection("metrics", index, "cardinality_limit", message))
        refused = {r.index for r in batch.rejected if r.section == "metrics"}
        batch.metrics = [(i, m) for i, m in batch.metrics if i not in refused]
        _touch_key(key, request)

    body = {
        "resource": batch.resource,
        "metrics": [m for _, m in batch.metrics],
        "events": [e for _, e in batch.events],
        "errors": [e for _, e in batch.errors],
    }
    if batch.accepted:
        try:
            stream.publish(
                organization_id=found.organization_id,
                project_id=key.project_id,
                connection_id=key.connection_id,
                body=body,
            )
        except stream.StreamUnavailable:
            logger.warning("Ingest stream unavailable; asking the client to retry")
            return problem(503, "Temporarily unavailable", code="unavailable", retry_after=30)

    result = {
        "accepted": batch.accepted,
        "rejected": [
            r.as_dict() for r in sorted(batch.rejected, key=lambda r: (r.section, r.index))
        ],
    }
    if idem_key:
        cache.set(idem_key, result, IDEMPOTENCY_TTL)
    return JsonResponse(result, status=202)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@transaction.non_atomic_requests
def heartbeat(request: HttpRequest, token: str, kind: str = PingKind.SUCCESS) -> HttpResponse:
    found = lookup.find(token, CredentialKind.HEARTBEAT)
    if found is None:
        return problem(404, "Not found", "Unknown or revoked heartbeat URL.")
    retry = ratelimit.hit(f"hb:{found.target_id}", settings.HEARTBEAT_RATE_LIMIT_PER_MINUTE)
    if retry is not None:
        return problem(429, "Too many requests", code="rate_limited", retry_after=retry)

    message = ""
    if kind == PingKind.FAIL and request.method == "POST":
        message = request.body[:MAX_FAIL_BODY].decode("utf-8", errors="replace").strip()

    with tenant_context(found.organization_id):
        hb = (
            Heartbeat.objects.select_for_update(of=("self",))
            .select_related("project", "connection")
            .filter(id=found.target_id)
            .first()
        )
        if hb is None:
            return problem(404, "Not found", "Unknown or revoked heartbeat URL.")
        heartbeats.record_ping(hb, kind, timezone.now(), message)
    return HttpResponse(status=204)
