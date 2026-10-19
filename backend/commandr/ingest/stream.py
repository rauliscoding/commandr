"""The ingest stream: accept fast at the edge, write in batches behind it.

`POST /v1/ingest` validates and `XADD`s the accepted items to a Redis stream;
the `drainer` process reads them with a consumer group and writes them through
`monitoring.write`. Redis Streams give back-pressure and replay: an entry is
acknowledged only after its write commits, and entries a crashed drainer left
pending are reclaimed after `CLAIM_IDLE_MS`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

import redis
from django.conf import settings
from django.utils import timezone

from commandr.integrations.models import Connection
from commandr.integrations.services import mark_data_received
from commandr.monitoring import rules, write
from commandr.tenancy.context import tenant_context
from commandr.tenancy.models import Project

logger = logging.getLogger(__name__)

GROUP = "writers"
CLAIM_IDLE_MS = 60_000
# An entry that fails this many times is parked in the dead-letter stream so it
# cannot block the ones behind it forever.
MAX_DELIVERIES = 5


class StreamUnavailable(Exception):
    """Redis could not take the batch; the client should retry (503)."""


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.INGEST_STREAM_URL, socket_connect_timeout=2, socket_timeout=5
    )


# Tests swap this for a fakeredis client.
get_client: Callable[[], redis.Redis] = _client


def publish(
    *, organization_id: UUID, project_id: UUID, connection_id: UUID, body: dict[str, Any]
) -> str:
    try:
        entry_id = get_client().xadd(
            settings.INGEST_STREAM_KEY,
            {
                "org": str(organization_id),
                "project": str(project_id),
                "connection": str(connection_id),
                "received_at": timezone.now().isoformat(),
                "body": json.dumps(body, separators=(",", ":")),
            },
            maxlen=settings.INGEST_STREAM_MAXLEN,
            approximate=True,
        )
    except redis.RedisError as exc:
        raise StreamUnavailable from exc
    return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)


def ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(settings.INGEST_STREAM_KEY, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def process(fields: dict[str, str]) -> None:
    """Write one stream entry. Idempotent: replaying it changes nothing."""
    org_id = UUID(fields["org"])
    project_id = UUID(fields["project"])
    body = json.loads(fields["body"])
    with tenant_context(org_id):
        project = Project.objects.filter(id=project_id).first()
        if project is None:
            return  # deleted since: nothing to write to
        now = timezone.now()
        touched = write.write_metrics(project.id, write.metrics_from_push(body.get("metrics", [])))
        write.write_events(project.id, write.with_datetimes(body.get("events", [])))
        write.write_errors(project.id, write.with_datetimes(body.get("errors", [])))
        connection = Connection.objects.filter(id=fields["connection"]).first()
        if connection is not None:
            mark_data_received(connection, at=now)
        rules.evaluate_for_metrics(project, touched, now)


def _decode(raw: dict[bytes, bytes]) -> dict[str, str]:
    return {k.decode(): v.decode() for k, v in raw.items()}


def drain_once(client: redis.Redis, consumer: str, *, count: int = 50, block_ms: int = 0) -> int:
    """Read, write and acknowledge up to `count` entries. Returns how many."""
    ensure_group(client)
    stream = settings.INGEST_STREAM_KEY
    entries: list[tuple[bytes, dict[bytes, bytes]]] = []
    # Entries another (crashed) drainer read but never acknowledged.
    # redis-py types sync and async clients together; this one is sync.
    claimed = cast(
        Any, client.xautoclaim(stream, GROUP, consumer, CLAIM_IDLE_MS, "0-0", count=count)
    )
    entries.extend(claimed[1])
    if len(entries) < count:
        response = cast(
            Any,
            client.xreadgroup(
                GROUP, consumer, {stream: ">"}, count=count - len(entries), block=block_ms or None
            ),
        )
        for _, items in response or []:
            entries.extend(items)
    done = 0
    for entry_id, raw in entries:
        if not raw:  # trimmed away by MAXLEN while pending
            client.xack(stream, GROUP, entry_id)
            continue
        try:
            process(_decode(raw))
        except Exception:
            # Logged without the payload, which is customer data.
            logger.exception("Ingest entry %s failed", entry_id.decode())
            pending = cast(Any, client.xpending_range(stream, GROUP, entry_id, entry_id, 1))
            if pending and pending[0]["times_delivered"] >= MAX_DELIVERIES:
                client.xadd(f"{stream}:dead", cast(Any, raw), maxlen=10_000, approximate=True)
                client.xack(stream, GROUP, entry_id)
            continue  # otherwise left pending: retried after CLAIM_IDLE_MS
        client.xack(stream, GROUP, entry_id)
        done += 1
    return done
