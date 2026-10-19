# SPDX-License-Identifier: AGPL-3.0-only
"""`@commandr.check`, `@commandr.kpi` and `@commandr.gauge`: what the status document reports."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from . import _log

Status = Literal["ok", "warn", "fail", "unknown"]
STATUSES: tuple[Status, ...] = ("ok", "warn", "fail", "unknown")
NAME_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
ATTR_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")

Number = int | float


@dataclass(frozen=True)
class Check:
    """What a check function returns: the app's own judgement of one thing."""

    status: Status
    summary: str = ""
    value: Number | None = None
    unit: str = ""

    @classmethod
    def ok(cls, summary: str = "", value: Number | None = None, unit: str = "") -> Check:
        return cls("ok", summary, value, unit)

    @classmethod
    def warn(cls, summary: str = "", value: Number | None = None, unit: str = "") -> Check:
        return cls("warn", summary, value, unit)

    @classmethod
    def fail(cls, summary: str = "", value: Number | None = None, unit: str = "") -> Check:
        return cls("fail", summary, value, unit)

    @classmethod
    def unknown(cls, summary: str = "") -> Check:
        return cls("unknown", summary)

    @classmethod
    def from_ratio(
        cls,
        ratio: float,
        *,
        warn: float,
        fail: float,
        unit: str = "ratio",
        summary: str | None = None,
    ) -> Check:
        """`fail` at or above `fail`, `warn` at or above `warn`, otherwise `ok`."""
        status: Status = "fail" if ratio >= fail else "warn" if ratio >= warn else "ok"
        return cls(status, f"{ratio:.1%}" if summary is None else summary, ratio, unit)


CheckFunc = Callable[[], "Check | bool | None"]
KpiFunc = Callable[[], "Number | None"]
GaugeFunc = Callable[[], "Number | None"]


@dataclass(frozen=True)
class CheckSpec:
    key: str
    name: str
    func: CheckFunc


@dataclass(frozen=True)
class KpiSpec:
    name: str
    label: str
    unit: str
    func: KpiFunc


@dataclass(frozen=True)
class GaugeSpec:
    name: str
    unit: str
    attrs: dict[str, str]
    func: GaugeFunc


_lock = threading.Lock()
_checks: dict[str, CheckSpec] = {}
_kpis: dict[str, KpiSpec] = {}
_gauges: dict[tuple[str, tuple[tuple[str, str], ...]], GaugeSpec] = {}

F = TypeVar("F", bound=Callable[..., object])


def _valid_name(kind: str, name: str) -> bool:
    if NAME_RE.match(name) and len(name) <= 120:
        return True
    # Registration happens at import time: a typo must not stop the app starting.
    _log.warn(
        f"name:{name}",
        "commandr: %s %r ignored: use lowercase.dot.separated names ([a-z0-9_.], at most 120).",
        kind,
        name,
    )
    return False


def check(key: str, *, name: str | None = None) -> Callable[[F], F]:
    """Register a check. The function returns a `Check`, `True` (ok) or `False` (fail).

    Returning `None` reports `unknown`; raising reports `fail` with the exception
    type (never its message, which may hold a connection string).
    """

    def decorator(func: F) -> F:
        if key and len(key) <= 200:
            with _lock:
                _checks[key] = CheckSpec(key, name or key, func)  # type: ignore[arg-type]
        else:
            _log.warn(f"check:{key}", "commandr: check key %r ignored: 1-200 characters.", key)
        return func

    return decorator


def kpi(name: str, *, label: str = "", unit: str = "") -> Callable[[F], F]:
    """Register a KPI. The function returns a number, or `None` when not available.

    A KPI whose function raises or times out is reported as `null` ("—"), never 0.
    """

    def decorator(func: F) -> F:
        if _valid_name("KPI", name):
            with _lock:
                _kpis[name] = KpiSpec(name, label, unit, func)  # type: ignore[arg-type]
        return func

    return decorator


def gauge(name: str, *, unit: str = "", attrs: dict[str, str] | None = None) -> Callable[[F], F]:
    """Register a gauge: a value right now (`queue.depth`). `None` leaves it out."""

    def decorator(func: F) -> F:
        clean = dict(attrs or {})
        if _valid_name("gauge", name):
            with _lock:
                _gauges[(name, tuple(sorted(clean.items())))] = GaugeSpec(
                    name,
                    unit,
                    clean,
                    func,  # type: ignore[arg-type]
                )
        return func

    return decorator


def checks() -> list[CheckSpec]:
    with _lock:
        return list(_checks.values())


def kpis() -> list[KpiSpec]:
    with _lock:
        return list(_kpis.values())


def gauges() -> list[GaugeSpec]:
    with _lock:
        return list(_gauges.values())


def unregister_all() -> None:
    """For tests."""
    with _lock:
        _checks.clear()
        _kpis.clear()
        _gauges.clear()
