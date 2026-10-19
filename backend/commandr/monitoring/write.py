"""The one write path for metrics, events and errors.

Used by the ingest drainer (push API), the status-endpoint poller and the
uptime probe. Must run with the tenant active. Every write is idempotent:

* points are keyed `(series, ts)` and inserted `ON CONFLICT DO NOTHING`;
* rollups are updated only for the points that insert actually added
  (`RETURNING`), so replaying a batch changes nothing;
* events and error occurrences are de-duplicated by their client id.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, connection, transaction
from django.db.models import Q

from commandr.core.logging import redact
from commandr.tenancy.context import TenantContextError, current_org_id

from .models import (
    ErrorGroup,
    ErrorOccurrence,
    Event,
    MetricKind,
    MetricSeries,
)

_CHUNK = 500
MAX_STACK = 65_536


@dataclass(frozen=True)
class MetricIn:
    """One value for one series. `value=None` means "reported as not available"."""

    name: str
    kind: str
    value: float | None
    ts: datetime
    attrs: dict[str, str] = field(default_factory=dict)
    unit: str = ""
    label: str = ""


def attrs_hash(attrs: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(attrs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _org() -> UUID:
    org = current_org_id()
    if org is None:
        raise TenantContextError("Metric writes need an active tenant.")
    return org


def ensure_partitions(months_back: int = 1, months_ahead: int = 3) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT monitoring_ensure_point_partitions(%s, %s)", [months_back, months_ahead]
        )
        created: int = cursor.fetchone()[0]
    return created


def _series_ids(project_id: UUID, metrics: Sequence[MetricIn]) -> dict[tuple[str, str], UUID]:
    org = _org()
    wanted: dict[tuple[str, str], MetricIn] = {}
    for m in metrics:
        wanted.setdefault((m.name, attrs_hash(m.attrs)), m)
    # bulk_create skips TenantOwned.save(), so organization is set explicitly;
    # RLS's WITH CHECK refuses any other value anyway.
    MetricSeries.objects.bulk_create(
        [
            MetricSeries(
                organization_id=org,
                project_id=project_id,
                name=name,
                kind=m.kind,
                unit=m.unit,
                label=m.label,
                attrs=m.attrs,
                attrs_hash=h,
            )
            for (name, h), m in wanted.items()
        ],
        ignore_conflicts=True,
    )
    rows = MetricSeries.objects.filter(
        project_id=project_id, name__in={n for n, _ in wanted}
    ).values_list("id", "name", "attrs_hash", "label", "unit")
    ids: dict[tuple[str, str], UUID] = {}
    for sid, name, h, label, unit in rows:
        if (name, h) not in wanted:
            continue
        ids[(name, h)] = sid
        m = wanted[(name, h)]
        # KPIs carry their display label and unit with every report; keep them current.
        if (m.label and m.label != label) or (m.unit and m.unit != unit):
            MetricSeries.objects.filter(id=sid).update(label=m.label or label, unit=m.unit or unit)
    return ids


def _insert_points(rows: list[tuple[UUID, UUID, datetime, float]]) -> list[tuple[Any, ...]]:
    """INSERT … ON CONFLICT DO NOTHING RETURNING: the points that are new."""
    inserted: list[tuple[Any, ...]] = []
    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start : start + _CHUNK]
        values = ", ".join(["(%s, %s, %s, %s)"] * len(chunk))
        params = [v for row in chunk for v in row]
        # Raw SQL (reviewed): parameterised; the ORM cannot express RETURNING
        # on a conflict-ignoring multi-row insert into a partitioned table.
        sql = (
            "INSERT INTO monitoring_metricpoint (organization_id, series_id, ts, value) "  # noqa: S608
            f"VALUES {values} ON CONFLICT DO NOTHING RETURNING series_id, ts, value"
        )
        for attempt in (1, 2):
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    inserted.extend(cursor.fetchall())
                break
            except IntegrityError as exc:
                # "no partition of relation … found for row": the scheduled task
                # fell behind. Create the missing month and try once more.
                if attempt == 2 or "partition" not in str(exc):
                    raise
                ensure_partitions()
    return inserted


def _bucket(ts: datetime, width: timedelta) -> datetime:
    seconds = int(width.total_seconds())
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=ts.tzinfo)


def _upsert_rollups(table: str, width: timedelta, points: Iterable[tuple[Any, ...]]) -> None:
    org = _org()
    agg: dict[tuple[UUID, datetime], list[Any]] = {}
    for series_id, ts, value in points:
        key = (series_id, _bucket(ts, width))
        a = agg.get(key)
        if a is None:
            agg[key] = [value, value, value, 1, value, ts]
        else:
            a[0] = min(a[0], value)
            a[1] = max(a[1], value)
            a[2] += value
            a[3] += 1
            if ts >= a[5]:
                a[4], a[5] = value, ts
    if not agg:
        return
    rows = [(org, sid, bucket, *a) for (sid, bucket), a in agg.items()]
    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start : start + _CHUNK]
        values = ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(chunk))
        # Raw SQL (reviewed): `table` is one of two constants, values are parameters.
        sql = (
            f"INSERT INTO {table} AS r "  # noqa: S608
            "(organization_id, series_id, bucket, min, max, sum, count, last, last_ts) "
            f"VALUES {values} ON CONFLICT (series_id, bucket) DO UPDATE SET "
            "min = LEAST(r.min, EXCLUDED.min), max = GREATEST(r.max, EXCLUDED.max), "
            "sum = r.sum + EXCLUDED.sum, count = r.count + EXCLUDED.count, "
            "last = CASE WHEN EXCLUDED.last_ts >= r.last_ts THEN EXCLUDED.last ELSE r.last END, "
            "last_ts = GREATEST(r.last_ts, EXCLUDED.last_ts)"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, [v for row in chunk for v in row])


def write_metrics(project_id: UUID, metrics: Sequence[MetricIn]) -> set[str]:
    """Store points and keep rollups and each series' latest value. Returns the
    names of the metrics that got new data (for rule evaluation)."""
    if not metrics:
        return set()
    org = _org()
    ids = _series_ids(project_id, metrics)

    rows = [
        (org, ids[(m.name, attrs_hash(m.attrs))], m.ts, float(m.value))
        for m in metrics
        if m.value is not None
    ]
    inserted = _insert_points(rows)
    _upsert_rollups("monitoring_metricrollup1m", timedelta(minutes=1), inserted)
    _upsert_rollups("monitoring_metricrollup1h", timedelta(hours=1), inserted)

    # Latest report per series, including "not available" (value None).
    latest: dict[UUID, MetricIn] = {}
    for m in metrics:
        sid = ids[(m.name, attrs_hash(m.attrs))]
        if sid not in latest or m.ts >= latest[sid].ts:
            latest[sid] = m
    for sid, m in latest.items():
        MetricSeries.objects.filter(Q(last_at__isnull=True) | Q(last_at__lte=m.ts), id=sid).update(
            last_value=m.value, last_at=m.ts
        )
    return {m.name for m in metrics}


def write_events(project_id: UUID, events: Sequence[dict[str, Any]]) -> int:
    """`ts` must already be a datetime (see `with_datetimes`)."""
    org = _org()
    created = Event.objects.bulk_create(
        [
            Event(
                organization_id=org,
                project_id=project_id,
                name=e["name"],
                ts=e["ts"],
                props=e.get("props") or {},
                client_id=e.get("id") or "",
            )
            for e in events
        ],
        ignore_conflicts=True,
    )
    return len(created)


def write_errors(project_id: UUID, errors: Sequence[dict[str, Any]]) -> int:
    """Group by fingerprint; store each occurrence once (by client id).

    `ts` must already be a datetime (see `with_datetimes`).
    """
    org = _org()
    ids = [e["id"] for e in errors if e.get("id")]
    seen = set(
        ErrorOccurrence.objects.filter(project_id=project_id, client_id__in=ids).values_list(
            "client_id", flat=True
        )
    )
    by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in errors:
        if e.get("id") and e["id"] in seen:
            continue
        by_fingerprint[e["fingerprint"]].append(e)

    stored = 0
    for fingerprint, items in by_fingerprint.items():
        items.sort(key=lambda e: e["ts"])
        last = items[-1]
        group, _ = ErrorGroup.objects.select_for_update().get_or_create(
            project_id=project_id,
            fingerprint=fingerprint,
            defaults={
                "type": last.get("type", ""),
                "message": redact(last["message"])[:2000],
                "culprit": last.get("culprit", ""),
                "level": last["level"],
                "first_seen": items[0]["ts"],
                "last_seen": last["ts"],
            },
        )
        occurrences = ErrorOccurrence.objects.bulk_create(
            [
                ErrorOccurrence(
                    organization_id=org,
                    group=group,
                    project_id=project_id,
                    ts=e["ts"],
                    level=e["level"],
                    # Second line of defence: scrub token-shaped strings server-side.
                    message=redact(e["message"])[:2000],
                    stack=redact(e.get("stack", ""))[:MAX_STACK],
                    attrs=e.get("attrs") or {},
                    client_id=e.get("id") or "",
                )
                for e in items
            ],
            ignore_conflicts=True,
        )
        group.count += len(occurrences)
        group.last_seen = max(group.last_seen, last["ts"])
        group.message = redact(last["message"])[:2000]
        group.level = last["level"]
        group.save(update_fields=["count", "last_seen", "message", "level"])
        stored += len(occurrences)
    return stored


def with_datetimes(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stream entries carry ISO timestamps; the writers want datetimes."""
    return [{**item, "ts": datetime.fromisoformat(item["ts"])} for item in items]


def metrics_from_push(items: Iterable[dict[str, Any]]) -> list[MetricIn]:
    return [
        MetricIn(
            name=m["name"],
            kind=MetricKind.COUNTER if m["type"] == "counter" else MetricKind.GAUGE,
            value=float(m["value"]),
            ts=datetime.fromisoformat(m["ts"]),
            attrs=m.get("attrs") or {},
            unit=m.get("unit", ""),
        )
        for m in items
    ]
