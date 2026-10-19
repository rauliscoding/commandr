"""Turning fetch results into checks and metrics (the database side of polling).

The fetch itself happens in an `egress` task with no database access
(`tasks.fetch_status`, `tasks.probe_uptime`); it hands back a plain dict,
which the functions here write. They must run with the tenant active.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from commandr.ingest.schemas import validator
from commandr.integrations.services import mark_data_received, mark_error

from . import checks, rules, write
from .models import Check, CheckSource, CheckStatus, MetricKind, StatusEndpoint, UptimeMonitor

REACHABILITY = "commandr.reachability"
TLS_WARN = timedelta(days=14)
TLS_FAIL = timedelta(days=3)

_STATUS_DOCUMENT = validator("StatusDocument")


def _host(url: str) -> str:
    return urlsplit(url).hostname or url


# --- Uptime ------------------------------------------------------------------


def record_uptime(monitor: UptimeMonitor, result: dict[str, Any], now: datetime) -> None:
    project = monitor.project
    error = result.get("error") or ""
    code = result.get("status_code")
    up = not error and code is not None and code < 400
    tls_not_after = (
        datetime.fromisoformat(result["tls_not_after"]) if result.get("tls_not_after") else None
    )
    response_ms = result.get("response_ms")

    monitor.last_run_at = now
    monitor.last_status_code = code
    monitor.last_response_ms = response_ms if not error else None
    monitor.last_error = error[:500]
    if tls_not_after is not None:
        monitor.tls_expires_at = tls_not_after
    monitor.save()

    if up:
        summary = f"HTTP {code} in {response_ms} ms"
    elif error:
        summary = error
    else:
        summary = f"HTTP {code}"
    checks.record(
        project=project,
        source=CheckSource.UPTIME,
        source_id=monitor.id,
        result=checks.Result(
            "uptime",
            f"{_host(monitor.url)} is up",
            CheckStatus.OK if up else CheckStatus.FAIL,
            summary,
        ),
        now=now,
        expected_every_seconds=monitor.interval_seconds,
    )
    if tls_not_after is not None:
        left = tls_not_after - now
        days = left.days
        if left < TLS_FAIL:
            tls_status = CheckStatus.FAIL
        elif left < TLS_WARN:
            tls_status = CheckStatus.WARN
        else:
            tls_status = CheckStatus.OK
        checks.record(
            project=project,
            source=CheckSource.UPTIME,
            source_id=monitor.id,
            result=checks.Result(
                "tls",
                f"TLS certificate for {_host(monitor.url)}",
                tls_status,
                f"Expires {tls_not_after:%Y-%m-%d} (in {days} days)",
            ),
            now=now,
            expected_every_seconds=monitor.interval_seconds,
        )

    attrs = {"monitor": str(monitor.id)}
    points = [write.MetricIn("uptime.up", MetricKind.GAUGE, 1.0 if up else 0.0, now, attrs)]
    if up and response_ms is not None:
        points.append(
            write.MetricIn(
                "uptime.response_ms", MetricKind.GAUGE, float(response_ms), now, attrs, unit="ms"
            )
        )
    if tls_not_after is not None:
        # A timestamp, never a countdown: "days left" is derived when read.
        points.append(
            write.MetricIn(
                "uptime.tls_expires_at",
                MetricKind.GAUGE,
                tls_not_after.timestamp(),
                now,
                attrs,
                unit="s",
            )
        )
    touched = write.write_metrics(project.id, points)
    rules.evaluate_for_metrics(project, touched, now)
    # A probe that ran is data, even if the site is down: that is what it reports.
    mark_data_received(monitor.connection, at=now)


# --- Status endpoint ---------------------------------------------------------


def _reachability(endpoint: StatusEndpoint, status: str, summary: str, now: datetime) -> None:
    checks.record(
        project=endpoint.project,
        source=CheckSource.STATUS_ENDPOINT,
        source_id=endpoint.id,
        result=checks.Result(REACHABILITY, f"{_host(endpoint.url)} answers", status, summary),
        now=now,
        expected_every_seconds=endpoint.interval_seconds,
    )


def _failure_message(result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])
    code = result.get("status_code")
    if code == 401:
        return (
            "Your app refused our signature (HTTP 401). Check that it uses this "
            "project's signing secret and that its clock is correct."
        )
    return f"Expected HTTP 200, got {code}."


def record_status(endpoint: StatusEndpoint, result: dict[str, Any], now: datetime) -> None:
    endpoint.last_run_at = now
    code = result.get("status_code")
    error = ""
    document: dict[str, Any] | None = None

    if result.get("error") or code not in (200, 304):
        error = _failure_message(result)
    elif code == 200:
        try:
            parsed = json.loads(result.get("body") or "")
        except ValueError:
            parsed = None
            error = "The status document is not valid JSON."
        if parsed is not None:
            problems = sorted(_STATUS_DOCUMENT.iter_errors(parsed), key=lambda e: list(e.path))
            if problems:
                where = ".".join(str(p) for p in problems[0].absolute_path)
                error = (
                    "The status document does not match the contract: "
                    f"{where or 'document'}: {problems[0].message}"
                )
            else:
                document = parsed

    if error:
        endpoint.last_error = error[:500]
        endpoint.save(update_fields=["last_run_at", "last_error"])
        _reachability(endpoint, CheckStatus.FAIL, error, now)
        mark_error(endpoint.connection, error)
        return

    endpoint.last_error = ""
    endpoint.last_ok_at = now
    if code == 304:
        # Nothing changed: the checks we have are current again.
        Check.objects.filter(
            project_id=endpoint.project_id,
            source=CheckSource.STATUS_ENDPOINT,
            source_id=endpoint.id,
        ).update(last_run_at=now)
    else:
        endpoint.etag = (result.get("etag") or "")[:200]
        if document is not None:  # always, when there is no error and the code is 200
            apply_document(endpoint, document, now)
    endpoint.save(update_fields=["last_run_at", "last_error", "last_ok_at", "etag"])
    _reachability(endpoint, CheckStatus.OK, f"HTTP {code}", now)
    mark_data_received(endpoint.connection, at=now)


def apply_document(endpoint: StatusEndpoint, document: dict[str, Any], now: datetime) -> None:
    project = endpoint.project
    reported: dict[str, dict[str, Any]] = {}
    for item in document.get("checks", []):
        reported[item["key"]] = item  # a repeated key: the last one wins
    for key, item in reported.items():
        if key == REACHABILITY:
            continue  # ours; the app cannot set it
        checks.record(
            project=project,
            source=CheckSource.STATUS_ENDPOINT,
            source_id=endpoint.id,
            result=checks.Result(
                key,
                item.get("name") or key,
                item["status"],
                item.get("summary", ""),
                item.get("value"),
                item.get("unit", ""),
            ),
            now=now,
            expected_every_seconds=endpoint.interval_seconds,
        )
    # Absent from this poll = recovered (contract), so a check that only exists
    # while failing works naturally.
    for gone in (
        Check.objects.filter(
            project=project, source=CheckSource.STATUS_ENDPOINT, source_id=endpoint.id
        )
        .exclude(key__in=[*reported, REACHABILITY])
        .select_for_update()
        .select_related("project")
    ):
        checks.retire(gone, now)

    points = [
        write.MetricIn(
            g["name"],
            MetricKind.GAUGE,
            float(g["value"]),
            now,
            g.get("attrs") or {},
            g.get("unit", ""),
        )
        for g in document.get("gauges", [])
    ]
    points += [
        write.MetricIn(
            k["name"],
            MetricKind.KPI,
            None if k.get("value") is None else float(k["value"]),  # null: not available, never 0
            now,
            {},
            k.get("unit", ""),
            k.get("label", ""),
        )
        for k in document.get("kpis", [])
    ]
    touched = write.write_metrics(project.id, points)
    rules.evaluate_for_metrics(project, touched, now)
