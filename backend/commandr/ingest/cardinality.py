"""Cardinality caps, checked at the door so the rejection can say why.

A soft cap: two concurrent requests for the same project can each see room
for the last series and both be accepted. That overshoot is bounded by one
request's worth and is preferable to a lock on every ingest.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from django.conf import settings

from commandr.monitoring.models import MetricSeries
from commandr.monitoring.write import attrs_hash


def check(project_id: UUID, metrics: list[tuple[int, dict[str, Any]]]) -> dict[int, str]:
    """Return {index: message} for the metrics that would exceed a cap."""
    if not metrics:
        return {}
    max_series = settings.INGEST_MAX_SERIES_PER_PROJECT
    max_values = settings.INGEST_MAX_ATTR_VALUES
    names = {m["name"] for _, m in metrics}

    known: set[tuple[str, str]] = set()
    values: dict[tuple[str, str], set[str]] = defaultdict(set)
    for name, h, attrs in MetricSeries.objects.filter(
        project_id=project_id, name__in=names
    ).values_list("name", "attrs_hash", "attrs"):
        known.add((name, h))
        for key, value in (attrs or {}).items():
            values[(name, key)].add(value)
    total = MetricSeries.objects.filter(project_id=project_id).count()

    refused: dict[int, str] = {}
    for index, m in metrics:
        attrs = m.get("attrs") or {}
        ident = (m["name"], attrs_hash(attrs))
        if ident in known:
            continue
        for key, value in attrs.items():
            seen = values[(m["name"], key)]
            if value not in seen and len(seen) >= max_values:
                refused[index] = (
                    f"Attribute '{key}' has more than {max_values} distinct values for "
                    "this metric. Use a lower-cardinality value (a route template, not a URL)."
                )
                break
        else:
            if total >= max_series:
                refused[index] = (
                    f"This project has reached its limit of {max_series} metric series."
                )
            else:
                known.add(ident)
                total += 1
                for key, value in attrs.items():
                    values[(m["name"], key)].add(value)
    return refused
