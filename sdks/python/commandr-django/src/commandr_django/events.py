# SPDX-License-Identifier: AGPL-3.0-only
"""`commandr.event("user.signup", plan="trial")`: something that happened, pushed later."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import _log
from .conf import get_config
from .registry import ATTR_KEY_RE, NAME_RE
from .transport import transport

MAX_PROPS = 16
MAX_STRING = 256

# The server rejects a whole event whose property names personal data
# (ingestion contract § Attributes). Dropping just that property here keeps the
# event, and the warning tells the developer which one.
PERSONAL_KEYS = frozenset(
    {
        "address",
        "email",
        "e_mail",
        "first_name",
        "full_name",
        "ip",
        "ip_address",
        "last_name",
        "name",
        "phone",
        "phone_number",
        "user",
        "user_id",
        "userid",
        "username",
    }
)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")


def looks_personal(key: str, value: object) -> bool:
    """The server's test (ingest.validation): a personal key, an email or an IP address."""
    if key.lower() in PERSONAL_KEYS:
        return True
    if not isinstance(value, str):
        return False
    if _EMAIL.search(value):
        return True
    try:
        ipaddress.ip_address(value.strip("[]"))
    except ValueError:
        return False
    return True


def user_ref(user_id: object) -> str:
    """A pseudonymous, per-project reference: the same user gives the same value.

    Keyed with the project's secret, so it cannot be reversed by hashing every
    possible id (privacy.md: the SDK hashes user identifiers by default).
    """
    config = get_config()
    key = (config.signing_secret or config.ingest_key).encode()
    return hmac.new(key, str(user_id).encode(), hashlib.sha256).hexdigest()[:32]


def _prop(value: object) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value if math.isfinite(value) else None
    if value is None:
        return None
    return str(value)[:MAX_STRING]


def event(name: str, *, user_id: object = None, **props: object) -> None:
    """Record an event. Never blocks, never raises; sent with the next batch.

    `user_id`, if given, is sent only as `user_ref`, a keyed hash.
    """
    try:
        if not NAME_RE.match(name) or len(name) > 120:
            _log.warn(f"event:{name}", "commandr: event name %r is not valid; dropped.", name)
            return
        clean: dict[str, Any] = {}
        for key, value in props.items():
            if looks_personal(key, value):
                _log.warn(
                    f"personal:{key}",
                    "commandr: event property %r looks like personal data; left out.",
                    key,
                )
                continue
            prop = _prop(value)
            if prop is not None and ATTR_KEY_RE.match(key):
                clean[key] = prop
        if user_id is not None:
            clean["user_ref"] = user_ref(user_id)
        item: dict[str, Any] = {
            "id": f"evt_{uuid.uuid4().hex}",
            "name": name,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        if clean:
            item["props"] = dict(list(clean.items())[:MAX_PROPS])
        transport.enqueue("events", item)
    except Exception as exc:
        _log.warn("event", "commandr: event not recorded (%s).", type(exc).__name__)
