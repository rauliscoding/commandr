"""Connection lifecycle helpers shared by every connector."""

from datetime import datetime

from django.utils import timezone

from .models import Connection, ConnectionStatus


def mark_data_received(connection: Connection, *, at: datetime | None = None) -> None:
    """Record that data arrived through `connection`.

    The first time, this is what moves the setup wizard from "waiting for first
    data" to "first data", and the catalogue card from "setting up" to
    "connected". Cheap to call on every write: it only saves when something
    changes, at most once a minute for `last_synced_at`.
    """
    now = at or timezone.now()
    fields: list[str] = []
    if connection.first_data_at is None:
        connection.first_data_at = now
        fields.append("first_data_at")
    if connection.status in (ConnectionStatus.PENDING, ConnectionStatus.ERROR):
        connection.status = ConnectionStatus.CONNECTED
        connection.last_error = ""
        fields += ["status", "last_error"]
    if connection.last_synced_at is None or (now - connection.last_synced_at).total_seconds() >= 60:
        connection.last_synced_at = now
        fields.append("last_synced_at")
    if fields:
        connection.save(update_fields=[*fields, "updated_at"])


def mark_error(connection: Connection, message: str) -> None:
    """Show a sanitised, user-facing problem on the connection.

    A connection that never produced data stays `pending` (the wizard shows the
    error while it waits); one that did turns `error`.
    """
    message = message[:500]
    status = (
        ConnectionStatus.PENDING if connection.first_data_at is None else ConnectionStatus.ERROR
    )
    if connection.last_error != message or connection.status != status:
        connection.last_error = message
        if connection.status != ConnectionStatus.DISABLED:
            connection.status = status
        connection.save(update_fields=["last_error", "status", "updated_at"])
