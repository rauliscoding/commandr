# SPDX-License-Identifier: AGPL-3.0-only
"""Checks and gauges every Django app gets without writing code.

Chosen with `COMMANDR["BUILTINS"]`: database, cache, celery, disk, system.
"""

from __future__ import annotations

import os
import shutil
import uuid
from functools import partial
from typing import Any

from django.conf import settings
from django.db import connections
from django.utils.module_loading import import_string

from .conf import Config
from .registry import Check, CheckSpec, GaugeSpec


def database(alias: str) -> Check:
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    # No latency in the summary: it would change the document (and its ETag) every poll.
    return Check.ok("reachable")


def cache(alias: str) -> Check:
    from django.core.cache import caches

    backend = caches[alias]
    key = f"commandr:check:{uuid.uuid4().hex}"
    backend.set(key, "1", timeout=30)
    value = backend.get(key)
    backend.delete(key)
    if value != "1":
        return Check.fail("wrote a value but could not read it back")
    return Check.ok("reachable")


def celery_app(config: Config) -> Any | None:
    """The host's Celery app, or None when there is none to check."""
    if config.celery_app:
        return import_string(config.celery_app)
    try:
        from celery import current_app
    except ImportError:
        return None
    # Celery's fallback app is named "default" and points at a broker nobody
    # runs; pinging it would only ever time out.
    if getattr(current_app, "main", None) in (None, "", "default"):
        return None
    return current_app


def celery_workers(config: Config) -> Check:
    app = celery_app(config)
    if app is None:
        return Check.unknown("no Celery app found; set COMMANDR['CELERY_APP']")
    replies = app.control.ping(timeout=1.0) or []
    if not replies:
        return Check.fail("no worker answered within 1 s")
    count = len(replies)
    return Check.ok(f"{count} worker{'s' if count != 1 else ''} answered")


def disk(path: str, config: Config) -> Check:
    if not os.path.exists(path):
        return Check.fail(f"{path} is not mounted")
    usage = shutil.disk_usage(path)
    if usage.total <= 0:
        return Check.unknown("size not reported")
    ratio = usage.used / usage.total
    return Check.from_ratio(
        ratio,
        warn=config.disk_warn,
        fail=config.disk_fail,
        summary=f"{usage.used / 1e9:.1f} / {usage.total / 1e9:.0f} GB",
    )


def load_per_core() -> float | None:
    getloadavg = getattr(os, "getloadavg", None)  # not on Windows
    cpus = os.cpu_count()
    if getloadavg is None or not cpus:
        return None
    return float(round(getloadavg()[0] / cpus, 3))


def memory_used_ratio() -> float | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:  # Linux only
            info = {line.split(":")[0]: int(line.split()[1]) for line in fh if line.count(" ") >= 1}
    except (OSError, ValueError, IndexError):
        return None
    total, available = info.get("MemTotal"), info.get("MemAvailable")
    if not total or available is None:
        return None
    return round(1 - available / total, 3)


def check_specs(config: Config) -> list[CheckSpec]:
    wanted = set(config.builtins)
    specs: list[CheckSpec] = []
    if "database" in wanted:
        for alias in settings.DATABASES:
            key = "database" if alias == "default" else f"database:{alias}"
            vendor = connections[alias].display_name
            name = vendor if alias == "default" else f"{vendor} ({alias})"
            specs.append(CheckSpec(key, name, partial(database, alias)))
    if "cache" in wanted:
        for alias, options in getattr(settings, "CACHES", {}).items():
            if str(options.get("BACKEND", "")).endswith("DummyCache"):
                continue  # stores nothing by design
            key = "cache" if alias == "default" else f"cache:{alias}"
            name = "Cache" if alias == "default" else f"Cache ({alias})"
            specs.append(CheckSpec(key, name, partial(cache, alias)))
    if "celery" in wanted and _has_celery(config):
        specs.append(CheckSpec("celery", "Celery workers", partial(celery_workers, config)))
    if "disk" in wanted:
        for index, (label, path) in enumerate(config.disk_paths.items()):
            key = "disk" if index == 0 else f"disk:{label}"
            specs.append(CheckSpec(key, label, partial(disk, path, config)))
    return specs


def gauge_specs(config: Config) -> list[GaugeSpec]:
    if "system" not in config.builtins:
        return []
    return [
        GaugeSpec("system.cpu.load_per_core", "", {}, load_per_core),
        GaugeSpec("system.memory.used_ratio", "ratio", {}, memory_used_ratio),
    ]


def _has_celery(config: Config) -> bool:
    if config.celery_app:
        return True  # a bad path is then reported by the check itself, not here
    try:
        return celery_app(config) is not None
    except Exception:
        return False
