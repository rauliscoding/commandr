# SPDX-License-Identifier: AGPL-3.0-only
"""Per-route traffic, aggregated in process and flushed with each batch.

Keyed by route *template* (`api/pantries/{pk}/items/`), never the concrete
path: paths carry ids, which would be both personal data and unbounded
cardinality. Each window becomes, per route and status class, one
`http.server.requests` counter (a delta, with `interval_s`) and per route two
`http.server.duration_ms` gauges (`quantile` p50 and p95).
"""

from __future__ import annotations

import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

MAX_ROUTES = 200  # per window; further routes are counted as "other"
SAMPLES_PER_ROUTE = 256  # reservoir for the duration quantiles
UNMATCHED = "unmatched"
OTHER = "other"

_CONVERTER = re.compile(r"<(?:[^>:]+:)?([^>]+)>")
_NAMED_GROUP = re.compile(r"\(\?P<([^>]+)>[^)]*\)")


def route_template(route: str) -> str:
    """`api/<int:pk>/` -> `api/{pk}/`; `^api/(?P<pk>\\d+)/$` -> `api/{pk}/`."""
    route = _NAMED_GROUP.sub(r"{\1}", route)  # first: both forms contain <name>
    route = _CONVERTER.sub(r"{\1}", route)
    route = route.replace("^", "").replace("$", "").replace("\\", "")
    return (route or "/")[:128]


@dataclass
class _Route:
    counts: dict[str, int] = field(default_factory=dict)
    seen: int = 0
    samples: list[float] = field(default_factory=list)


class Traffic:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._routes: dict[str, _Route] = {}
        self._started = time.time()

    def record(self, route: str, status_code: int, duration_ms: float) -> None:
        status_class = f"{status_code // 100}xx" if 100 <= status_code < 600 else "other"
        with self._lock:
            if route not in self._routes and len(self._routes) >= MAX_ROUTES:
                route = OTHER
            entry = self._routes.setdefault(route, _Route())
            entry.counts[status_class] = entry.counts.get(status_class, 0) + 1
            entry.seen += 1
            if len(entry.samples) < SAMPLES_PER_ROUTE:
                entry.samples.append(duration_ms)
            else:
                slot = random.randrange(entry.seen)  # noqa: S311 sampling, not security
                if slot < SAMPLES_PER_ROUTE:
                    entry.samples[slot] = duration_ms

    def collect(self, ts_offset_us: int = 0) -> list[dict[str, Any]]:
        """Metrics for the window that just ended; starts a new window."""
        now = time.time()
        with self._lock:
            routes, self._routes = self._routes, {}
            started, self._started = self._started, now
        if not routes:
            return []
        interval = max(1, min(86_400, round(now - started)))
        stamp = datetime.fromtimestamp(int(now), timezone.utc).replace(microsecond=ts_offset_us)
        ts = stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        metrics: list[dict[str, Any]] = []
        for route, entry in routes.items():
            for status_class, count in sorted(entry.counts.items()):
                metrics.append(
                    {
                        "name": "http.server.requests",
                        "type": "counter",
                        "value": count,
                        "ts": ts,
                        "interval_s": interval,
                        "attrs": {"route": route, "status_class": status_class},
                    }
                )
            samples = sorted(entry.samples)
            for quantile, q in (("p50", 0.5), ("p95", 0.95)):
                value = samples[min(len(samples) - 1, int(q * len(samples)))]
                metrics.append(
                    {
                        "name": "http.server.duration_ms",
                        "type": "gauge",
                        "value": round(value, 1),
                        "unit": "ms",
                        "ts": ts,
                        "attrs": {"route": route, "quantile": quantile},
                    }
                )
        return metrics

    def reset(self) -> None:
        with self._lock:
            self._routes = {}
            self._started = time.time()


traffic = Traffic()
if hasattr(os, "register_at_fork"):
    # A forked worker starts with no counts: its parent's belong to the parent.
    os.register_at_fork(after_in_child=traffic.reset)
