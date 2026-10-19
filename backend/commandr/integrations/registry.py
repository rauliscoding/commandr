"""The connector registry: one declaration per integration.

The catalogue screen, the setup wizard and (later) the dashboard are generated
from these declarations, so adding an integration never means editing a screen
(CLAUDE.md invariant 7). Use the `/add-connector` skill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Category(StrEnum):
    APP_HEALTH = "app_health"
    ANALYTICS = "analytics"
    SOCIAL = "social"
    EMAIL = "email"
    ADS = "ads"
    MONEY = "money"
    WORK = "work"


CATEGORY_LABELS = {
    Category.APP_HEALTH: "App health",
    Category.ANALYTICS: "Analytics",
    Category.SOCIAL: "Social",
    Category.EMAIL: "Email",
    Category.ADS: "Ads",
    Category.MONEY: "Money",
    Category.WORK: "Work",
}


class AuthType(StrEnum):
    NONE = "none"
    INGEST_KEY = "ingest_key"
    HMAC_SECRET = "hmac_secret"  # noqa: S105 -- an auth type name, not a secret
    API_KEY = "api_key"
    OAUTH_PLATFORM = "oauth_platform"
    OAUTH_BYO_APP = "oauth_byo_app"  # ADR 0004
    UPLOAD = "upload"
    BUILT_IN = "built_in"


class Capability(StrEnum):
    READ_METRICS = "read_metrics"
    READ_CONTENT = "read_content"
    PUBLISH = "publish"
    SCHEDULE = "schedule"
    READ_SPEND = "read_spend"
    READ_REVENUE = "read_revenue"
    WEBHOOK = "webhook"


class Requirement(StrEnum):
    FREE = "free"
    NEEDS_META_APP = "needs_meta_app"
    NEEDS_TIKTOK_APP = "needs_tiktok_app"
    BUSINESS_ACCOUNT = "business_account"
    API_KEY = "api_key"
    PAID_API = "paid_api"
    CODE_CHANGE = "code_change"


REQUIREMENT_LABELS = {
    Requirement.FREE: "Free",
    Requirement.NEEDS_META_APP: "Needs a Meta app",
    Requirement.NEEDS_TIKTOK_APP: "Needs a TikTok app",
    Requirement.BUSINESS_ACCOUNT: "Business account",
    Requirement.API_KEY: "API key",
    Requirement.PAID_API: "Paid API",
    Requirement.CODE_CHANGE: "Code change",
}


class Availability(StrEnum):
    AVAILABLE = "available"
    COMING_SOON = "coming_soon"


@dataclass(frozen=True)
class SetupStep:
    title: str
    detail: str
    # Phase 1+: a validator id the wizard calls before letting the user continue.
    validator: str | None = None


class FieldKind(StrEnum):
    TEXT = "text"
    URL = "url"
    SELECT = "select"
    NUMBER = "number"


@dataclass(frozen=True)
class SetupField:
    """One input the setup wizard asks for. The SPA renders it generically, and
    the connector's own serializer is the authority on what is valid."""

    name: str
    label: str
    kind: FieldKind = FieldKind.TEXT
    help: str = ""
    required: bool = True
    default: str = ""
    options: tuple[tuple[str, str], ...] = ()  # (value, label) for SELECT
    placeholder: str = ""


@dataclass(frozen=True)
class ConnectorMeta:
    slug: str  # stable forever: stored on Connection rows
    name: str
    category: Category
    auth: AuthType
    unlocks: str  # one sentence, in the user's words
    setup_minutes: float
    phase: int
    capabilities: frozenset[Capability] = frozenset()
    requirements: tuple[Requirement, ...] = ()
    logo_text: str = ""  # monogram shown until official logos are added
    docs_path: str = ""
    availability: Availability = Availability.COMING_SOON
    steps: tuple[SetupStep, ...] = field(default_factory=tuple)
    # What the wizard's form asks for once the connector is available.
    fields: tuple[SetupField, ...] = field(default_factory=tuple)


_REGISTRY: dict[str, ConnectorMeta] = {}
# Project kind -> ordered slugs for the "Recommended first" row: the connections
# that produce useful data fastest for that kind of project.
_RECOMMENDED: dict[str, tuple[str, ...]] = {}


def register(meta: ConnectorMeta) -> ConnectorMeta:
    if meta.slug in _REGISTRY:
        raise ValueError(f"Connector {meta.slug!r} is registered twice.")
    _REGISTRY[meta.slug] = meta
    return meta


def recommend(project_kind: str, slugs: tuple[str, ...]) -> None:
    unknown = [s for s in slugs if s not in _REGISTRY]
    if unknown:
        raise ValueError(f"Recommending unregistered connectors: {unknown}")
    _RECOMMENDED[project_kind] = slugs


def recommended_for(project_kind: str) -> tuple[str, ...]:
    return _RECOMMENDED.get(project_kind, ())


def get(slug: str) -> ConnectorMeta:
    return _REGISTRY[slug]


def all_connectors() -> list[ConnectorMeta]:
    return list(_REGISTRY.values())
