"""Per-connector setup handlers, looked up by slug.

The registry (`registry.py`) says what a connector *is*; a setup handler says
how to create, describe, check and remove one connection of it. The generic
connections API (`views.py`) dispatches here, so the SPA never needs code for
a particular connector (CLAUDE.md invariant 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from commandr.accounts.models import User
    from commandr.tenancy.models import Project

    from .models import Connection


@dataclass(frozen=True)
class Reveal:
    """A value shown exactly once, straight after setup. Never stored in plaintext."""

    label: str
    value: str
    kind: Literal["secret", "url", "text"] = "secret"


@dataclass(frozen=True)
class Snippet:
    label: str
    code: str
    language: str = "bash"


@dataclass
class SetupResult:
    connection: Connection
    reveal: list[Reveal] = field(default_factory=list)
    snippets: list[Snippet] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Detail:
    """One label/value line describing a connection, safe to show (no secrets)."""

    label: str
    value: str | None  # None renders as "—": unknown is not zero (invariant 5)
    kind: Literal["text", "time", "code"] = "text"  # "time": ISO 8601, formatted by the UI


@dataclass
class FirstData:
    received_at: datetime | None
    summary: list[Detail] = field(default_factory=list)


class ConnectorSetup(Protocol):
    slug: str

    def validate(self, data: dict[str, Any], project: Project) -> dict[str, Any]:
        """Return cleaned fields or raise `rest_framework.ValidationError`."""

    def create(self, *, project: Project, user: User, data: dict[str, Any]) -> SetupResult:
        """Create the connection and whatever it needs. Runs in the tenant's context."""

    def describe(self, connection: Connection) -> list[Detail]: ...

    def first_data(self, connection: Connection) -> FirstData: ...

    def disconnect(self, connection: Connection) -> None:
        """Revoke credentials and stop schedules. The connection row is deleted after."""

    def check_now(self, connection: Connection) -> bool:
        """Run a check straight away if this connector polls; False if it cannot."""


_SETUPS: dict[str, ConnectorSetup] = {}


def register(setup: ConnectorSetup) -> ConnectorSetup:
    from .registry import Availability, get

    meta = get(setup.slug)  # KeyError if the connector is not declared
    if meta.availability is not Availability.AVAILABLE:
        raise ValueError(f"{setup.slug} has a setup handler but is not marked available.")
    if setup.slug in _SETUPS:
        raise ValueError(f"Setup for {setup.slug!r} is registered twice.")
    _SETUPS[setup.slug] = setup
    return setup


def get_setup(slug: str) -> ConnectorSetup | None:
    return _SETUPS.get(slug)


def all_setups() -> dict[str, ConnectorSetup]:
    return dict(_SETUPS)
