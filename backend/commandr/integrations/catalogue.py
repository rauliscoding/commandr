"""Builds the catalogue a project sees: registry metadata + its connection states."""

from typing import Any

from .models import Connection, ConnectionStatus
from .registry import (
    CATEGORY_LABELS,
    REQUIREMENT_LABELS,
    Category,
    ConnectorMeta,
    all_connectors,
    recommended_for,
)

# What the card's state chip says. "needs_attention" folds the two failure states:
# both mean "open this and do something".
_STATE_FROM_STATUS = {
    ConnectionStatus.PENDING: "setting_up",
    ConnectionStatus.CONNECTED: "connected",
    ConnectionStatus.NEEDS_REAUTH: "needs_attention",
    ConnectionStatus.ERROR: "needs_attention",
    ConnectionStatus.DISABLED: "not_connected",
}

RECOMMENDED_LIMIT = 4


def _entry(meta: ConnectorMeta, state: str, recommended: bool) -> dict[str, Any]:
    return {
        "slug": meta.slug,
        "name": meta.name,
        "category": meta.category.value,
        "auth": meta.auth.value,
        "unlocks": meta.unlocks,
        "setup_minutes": meta.setup_minutes,
        "phase": meta.phase,
        "availability": meta.availability.value,
        "logo_text": meta.logo_text or meta.name[:2],
        "requirements": [
            {"key": r.value, "label": REQUIREMENT_LABELS[r]} for r in meta.requirements
        ],
        "capabilities": sorted(c.value for c in meta.capabilities),
        "steps": [{"title": s.title, "detail": s.detail} for s in meta.steps],
        "docs_path": meta.docs_path,
        "state": state,
        "recommended": recommended,
    }


def build_catalogue(*, project_id: Any, project_kind: str) -> dict[str, Any]:
    """Must run with the project's tenant active (connections are under RLS)."""
    connections = Connection.objects.filter(project_id=project_id).values_list(
        "connector_slug", "status"
    )
    # A connector may have several connections (two Instagram accounts): the
    # card shows the worst state, so a broken one is never hidden by a good one.
    severity = ["connected", "setting_up", "not_connected", "needs_attention"]
    states: dict[str, str] = {}
    for slug, status_value in connections:
        state = _STATE_FROM_STATUS[ConnectionStatus(status_value)]
        if slug not in states or severity.index(state) > severity.index(states[slug]):
            states[slug] = state

    metas = all_connectors()
    recommended = list(recommended_for(project_kind))[:RECOMMENDED_LIMIT]
    entries = [_entry(m, states.get(m.slug, "not_connected"), m.slug in recommended) for m in metas]
    return {
        "categories": [{"key": c.value, "label": CATEGORY_LABELS[c]} for c in Category],
        "recommended": recommended,
        "connected_recommended": sum(1 for slug in recommended if states.get(slug) == "connected"),
        "connectors": entries,
    }
