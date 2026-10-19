"""Alert rules: turning a metric into a check."""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from uuid import UUID

from commandr.tenancy.models import Project

from . import checks
from .models import AlertRule, Check, CheckSource, CheckStatus, MetricPoint, MetricSeries, RuleKind

_COMPARE: dict[str, Callable[[float, float], bool]] = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}
_SYMBOL = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}


def _series(rule: AlertRule) -> list[UUID]:
    qs = MetricSeries.objects.filter(project_id=rule.project_id, name=rule.metric)
    if rule.attrs:
        qs = qs.filter(attrs__contains=rule.attrs)
    return list(qs.values_list("id", flat=True))


def _window(seconds: int) -> str:
    return f"{seconds // 60} min" if seconds >= 60 else f"{seconds} s"


def evaluate_rule(rule: AlertRule, now: datetime) -> checks.Result:
    """Pure-ish: reads points, returns the result. Does not write."""
    since = now - timedelta(seconds=rule.window_seconds)
    series = _series(rule)
    points = MetricPoint.objects.filter(series_id__in=series, ts__gte=since, ts__lte=now)
    if rule.kind == RuleKind.ABSENCE:
        if points.exists():
            return checks.Result(
                "rule",
                rule.name,
                CheckStatus.OK,
                f"Data in the last {_window(rule.window_seconds)}.",
            )
        return checks.Result(
            "rule",
            rule.name,
            rule.severity,
            f"No {rule.metric} data in the last {_window(rule.window_seconds)}.",
        )

    latest = points.order_by("-ts").values_list("value", flat=True).first()
    if latest is None or rule.threshold is None:
        # No data is not "below the threshold": it is unknown (invariant 5).
        return checks.Result(
            "rule", rule.name, CheckStatus.UNKNOWN, f"No {rule.metric} data to compare."
        )
    breached = _COMPARE[rule.comparator](latest, rule.threshold)
    verb = "breached" if breached else "not breached"
    summary = f"{rule.metric} = {latest:g} ({_SYMBOL[rule.comparator]} {rule.threshold:g} {verb})"
    return checks.Result(
        "rule", rule.name, rule.severity if breached else CheckStatus.OK, summary, value=latest
    )


def apply(rule: AlertRule, project: Project, now: datetime) -> Check | None:
    if not rule.enabled:
        existing = Check.objects.filter(
            project=project, source=CheckSource.RULE, source_id=rule.id
        ).first()
        if existing is not None:
            checks.retire(existing, now)
        return None
    return checks.record(
        project=project,
        source=CheckSource.RULE,
        source_id=rule.id,
        result=evaluate_rule(rule, now),
        now=now,
    )


def evaluate_for_metrics(project: Project, names: Iterable[str], now: datetime) -> None:
    """After a write: re-check threshold rules on the metrics that got data."""
    names = set(names)
    if not names:
        return
    for rule in AlertRule.objects.filter(
        project=project, metric__in=names, kind=RuleKind.THRESHOLD, enabled=True
    ):
        apply(rule, project, now)


def evaluate_all(project: Project, now: datetime) -> None:
    """Every minute: absence rules need a clock, not a write, to fire."""
    for rule in AlertRule.objects.filter(project=project):
        apply(rule, project, now)
