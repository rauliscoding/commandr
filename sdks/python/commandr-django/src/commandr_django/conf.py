# SPDX-License-Identifier: AGPL-3.0-only
"""The `COMMANDR` settings dict, with defaults.

Read on every use rather than cached at import, so `override_settings` works in
the host app's tests and nothing touches settings before Django is set up.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

DEFAULT_INGEST_URL = "https://ingest.commandr.app"
STATUS_PATH = ".well-known/commandr/status"
BUILTINS = ("database", "cache", "celery", "disk", "system")


@dataclass(frozen=True)
class Config:
    ingest_key: str = ""
    signing_secret: str = ""
    service: str = ""
    version: str = ""
    environment: str = ""
    ingest_url: str = DEFAULT_INGEST_URL
    # `prj_…` from the status endpoint's setup. When set, a poll for another
    # project is refused, so one secret leaking cannot read a second app.
    project: str = ""
    # Name -> heartbeat token or full heartbeat URL, for `@commandr.heartbeat`.
    heartbeats: Mapping[str, str] = field(default_factory=dict)
    builtins: tuple[str, ...] = BUILTINS  # "system": CPU load and memory gauges
    # Label -> path. The first one is reported as `disk`, others as `disk:<label>`.
    disk_paths: Mapping[str, str] = field(default_factory=lambda: {"Disk": "/"})
    disk_warn: float = 0.85
    disk_fail: float = 0.95
    celery_app: str = ""  # dotted path; defaults to Celery's current app
    capture_errors: bool = True
    traffic_exclude: tuple[str, ...] = ("/.well-known/commandr/",)
    flush_interval: float = 60.0
    check_timeout: float = 5.0  # the poller waits 10 s for the whole document
    send_timeout: float = 10.0
    max_buffer: int = 2000  # items waiting to be sent; beyond this, new ones are dropped
    enabled: bool = True

    @property
    def can_push(self) -> bool:
        return self.enabled and bool(self.ingest_key and self.ingest_url)


_KEYS = {
    "INGEST_KEY": "ingest_key",
    "SIGNING_SECRET": "signing_secret",
    "SERVICE": "service",
    "VERSION": "version",
    "ENVIRONMENT": "environment",
    "INGEST_URL": "ingest_url",
    "PROJECT": "project",
    "HEARTBEATS": "heartbeats",
    "BUILTINS": "builtins",
    "DISK_PATHS": "disk_paths",
    "DISK_WARN": "disk_warn",
    "DISK_FAIL": "disk_fail",
    "CELERY_APP": "celery_app",
    "CAPTURE_ERRORS": "capture_errors",
    "TRAFFIC_EXCLUDE": "traffic_exclude",
    "FLUSH_INTERVAL": "flush_interval",
    "CHECK_TIMEOUT": "check_timeout",
    "SEND_TIMEOUT": "send_timeout",
    "MAX_BUFFER": "max_buffer",
    "ENABLED": "enabled",
}
_TUPLES = {"builtins", "traffic_exclude"}


def get_config() -> Config:
    raw: Mapping[str, Any] = getattr(settings, "COMMANDR", None) or {}
    values: dict[str, Any] = {}
    for key, attr in _KEYS.items():
        if key in raw and raw[key] is not None:
            value = raw[key]
            values[attr] = tuple(value) if attr in _TUPLES else value
    config = Config(**values)
    if config.ingest_url.endswith("/"):
        config = Config(**{**values, "ingest_url": config.ingest_url.rstrip("/")})
    return config


def unknown_keys() -> list[str]:
    raw: Mapping[str, Any] = getattr(settings, "COMMANDR", None) or {}
    return sorted(set(raw) - set(_KEYS))
