"""The notification state machine, as pure functions (no database, no clock).

Per check (the pattern proven in Pantrini's `apps/ops`):

* ok → fail: alert straight away;
* fail → fail: stay quiet, then a "still failing" reminder once per cooldown;
* fail → ok, or the check disappears: one "passing again" message;
* warn: shown in the digest, never emailed on its own;
* unknown: holds the current state. "We could not check" is never treated as
  "it recovered" — invariant 5, unknown is not ok.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from .models import AlertState, CheckStatus


class Action(StrEnum):
    ALERT = "alert"
    REMINDER = "reminder"
    RECOVERY = "recovery"


def transition(
    *,
    alert_state: str,
    last_notified_at: datetime | None,
    status: str,
    now: datetime,
    cooldown: timedelta,
) -> tuple[str, Action | None]:
    """Return the new alert state and what to send, if anything."""
    if status == CheckStatus.FAIL:
        if alert_state != AlertState.ALERTING:
            return AlertState.ALERTING, Action.ALERT
        if last_notified_at is None or now - last_notified_at >= cooldown:
            return AlertState.ALERTING, Action.REMINDER
        return AlertState.ALERTING, None
    if status == CheckStatus.OK and alert_state == AlertState.ALERTING:
        return AlertState.OK, Action.RECOVERY
    return alert_state, None


def on_disappear(alert_state: str) -> Action | None:
    """A check that is no longer reported counts as recovered (ingestion contract)."""
    return Action.RECOVERY if alert_state == AlertState.ALERTING else None
