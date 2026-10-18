from typing import TYPE_CHECKING, Any

from django.db import models
from django.http import HttpRequest

from .models import AuditEvent

if TYPE_CHECKING:
    from commandr.accounts.models import User
    from commandr.tenancy.models import Organization

# Never put secrets, tokens or message bodies in `metadata`.
_FORBIDDEN_METADATA_KEYS = {"password", "secret", "token", "api_key", "credentials"}


def record(
    action: str,
    *,
    actor: "User | None",
    organization: "Organization | None" = None,
    target: models.Model | None = None,
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    """Write one audit event. `action` is `<noun>.<past-tense verb>`."""
    metadata = metadata or {}
    leaked = _FORBIDDEN_METADATA_KEYS & {k.lower() for k in metadata}
    if leaked:
        raise ValueError(f"Audit metadata must not contain {sorted(leaked)}.")
    return AuditEvent.objects.create(
        action=action,
        actor=actor if actor is not None and actor.is_authenticated else None,
        organization=organization,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        metadata=metadata,
        ip_address=request.META.get("REMOTE_ADDR") if request is not None else None,
    )
