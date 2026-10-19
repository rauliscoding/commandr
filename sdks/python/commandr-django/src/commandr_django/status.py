# SPDX-License-Identifier: AGPL-3.0-only
"""Builds the `commandr.status/v1` document (ingestion contract § 1).

Each check, KPI and gauge runs in its own thread with a shared deadline, so one
slow dependency costs that one check, not the whole answer (the poller gives up
after 10 s and then marks the app unreachable). A check that hangs is not
started again while its previous run is still going, so a stuck dependency
cannot pile up threads.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from django.db import connections

from . import builtin, registry
from .conf import Config
from .registry import ATTR_KEY_RE, STATUSES, Check

SCHEMA = "commandr.status/v1"
MAX_CHECKS, MAX_GAUGES, MAX_KPIS = 500, 500, 100

_running_lock = threading.Lock()
_running: set[str] = set()


@dataclass
class _Job:
    key: str
    func: Callable[[], object]
    result: object = None
    error: BaseException | None = None
    busy: bool = False

    def __post_init__(self) -> None:
        self.done = threading.Event()

    def run(self) -> None:
        try:
            self.result = self.func()
        except Exception as exc:
            self.error = exc
        finally:
            # Database connections are per thread; this one's die with it.
            connections.close_all()
            with _running_lock:
                _running.discard(self.key)
            self.done.set()


def _run_all(jobs: list[_Job], timeout: float) -> None:
    for job in jobs:
        with _running_lock:
            if job.key in _running:
                job.busy = True
                job.done.set()
                continue
            _running.add(job.key)
        threading.Thread(target=job.run, name=f"commandr-{job.key}"[:60], daemon=True).start()
    deadline = time.monotonic() + timeout
    for job in jobs:
        job.done.wait(max(0.0, deadline - time.monotonic()))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def number(value: object) -> int | float | None:
    """A JSON-safe number, or None. Booleans and NaN are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _check_entry(key: str, name: str, job: _Job, timeout: float) -> dict[str, Any]:
    entry: dict[str, Any] = {"key": key[:200], "name": name[:200]}
    if job.busy:
        return {**entry, "status": "fail", "summary": "still running since an earlier poll"}
    if not job.done.is_set():
        return {**entry, "status": "fail", "summary": f"did not finish within {timeout:g} s"}
    if job.error is not None:
        # The type only: messages can carry hosts, user names or connection strings.
        return {**entry, "status": "fail", "summary": f"raised {type(job.error).__name__}"}
    result = job.result
    if result is True:
        return {**entry, "status": "ok"}
    if result is False:
        return {**entry, "status": "fail"}
    if result is None:
        return {**entry, "status": "unknown", "summary": "no result"}
    if not isinstance(result, Check) or result.status not in STATUSES:
        return {**entry, "status": "unknown", "summary": "the check returned something else"}
    entry["status"] = result.status
    if result.summary:
        entry["summary"] = str(result.summary)[:500]
    value = number(result.value)
    if value is not None:
        entry["value"] = value
    if result.unit:
        entry["unit"] = str(result.unit)[:32]
    return entry


def _attrs(attrs: dict[str, str]) -> dict[str, str]:
    clean = {
        k: str(v)[:128] for k, v in attrs.items() if isinstance(k, str) and ATTR_KEY_RE.match(k)
    }
    return dict(list(clean.items())[:8])


def build(config: Config) -> dict[str, Any]:
    timeout = config.check_timeout
    check_specs: dict[str, registry.CheckSpec] = {}
    for spec in builtin.check_specs(config):
        check_specs[spec.key] = spec
    for spec in registry.checks():  # the app's own check wins over a built-in one
        check_specs[spec.key] = spec
    checks = list(check_specs.values())[:MAX_CHECKS]
    kpis = registry.kpis()[:MAX_KPIS]
    gauges = [*builtin.gauge_specs(config), *registry.gauges()][:MAX_GAUGES]

    check_jobs = [_Job(f"check:{c.key}", c.func) for c in checks]
    kpi_jobs = [_Job(f"kpi:{k.name}", k.func) for k in kpis]
    gauge_jobs = [_Job(f"gauge:{g.name}:{sorted(g.attrs.items())}", g.func) for g in gauges]
    _run_all([*check_jobs, *kpi_jobs, *gauge_jobs], timeout)

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "service": (config.service or "django")[:120],
        "generated_at": now_iso(),
    }
    if config.version:
        document["version"] = str(config.version)[:64]
    if config.environment:
        document["environment"] = str(config.environment)[:32]
    document["checks"] = [
        _check_entry(spec.key, spec.name, job, timeout)
        for spec, job in zip(checks, check_jobs, strict=True)
    ]

    gauge_entries: list[dict[str, Any]] = []
    for gspec, job in zip(gauges, gauge_jobs, strict=True):
        value = number(job.result) if job.done.is_set() and not job.busy else None
        if value is None:
            continue  # a gauge with no value is left out, never sent as 0
        gentry: dict[str, Any] = {"name": gspec.name, "value": value}
        if gspec.unit:
            gentry["unit"] = gspec.unit[:32]
        if gspec.attrs:
            gentry["attrs"] = _attrs(gspec.attrs)
        gauge_entries.append(gentry)
    document["gauges"] = gauge_entries

    kpi_entries: list[dict[str, Any]] = []
    for kspec, job in zip(kpis, kpi_jobs, strict=True):
        ok = job.done.is_set() and not job.busy and job.error is None
        kentry: dict[str, Any] = {
            "name": kspec.name,
            "value": number(job.result) if ok else None,  # null: "—", never 0
        }
        if kspec.label:
            kentry["label"] = kspec.label[:120]
        if kspec.unit:
            kentry["unit"] = kspec.unit[:32]
        kpi_entries.append(kentry)
    document["kpis"] = kpi_entries
    return document


def etag(document: dict[str, Any]) -> str:
    """Changes only when the content does, so an unchanged app can answer 304."""
    content = {k: v for k, v in document.items() if k != "generated_at"}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    return f'"{digest[:32]}"'
