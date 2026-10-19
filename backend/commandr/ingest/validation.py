"""Validating a push batch: strict about shape, forgiving about items.

A malformed envelope rejects the whole request (400). Inside a valid envelope,
each metric, event and error stands alone: a bad one is listed in `rejected`
with a code from the contract, and the rest are accepted (partial acceptance,
docs/architecture/ingestion-contract.md § Push API).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from jsonschema import ValidationError
from jsonschema.exceptions import best_match

from .schemas import validator

MAX_AGE = timedelta(hours=24)
MAX_AHEAD = timedelta(minutes=5)
SECTIONS = ("metrics", "events", "errors")
_ITEM_SCHEMA = {"metrics": "Metric", "events": "Event", "errors": "ErrorEvent"}
_ATTR_FIELD = {"metrics": "attrs", "events": "props", "errors": "attrs"}

# Keys that name personal data. Contract: no emails, names, IPs or user ids in
# attributes or event properties.
_PERSONAL_KEYS = {
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
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")


class EnvelopeError(Exception):
    """The request as a whole is malformed (400). The message is safe to return."""


class TooManyItems(Exception):
    """More items than one request may carry (413)."""


@dataclass(frozen=True)
class Rejection:
    section: str
    index: int
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "index": self.index,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ValidatedBatch:
    """Accepted items keep their original index so later rejections can cite it."""

    resource: dict[str, Any]
    metrics: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    events: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    errors: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)

    def section(self, name: str) -> list[tuple[int, dict[str, Any]]]:
        items: list[tuple[int, dict[str, Any]]] = getattr(self, name)
        return items

    @property
    def accepted(self) -> int:
        return len(self.metrics) + len(self.events) + len(self.errors)


def _envelope_validator() -> Any:
    # The envelope schema with the item schemas removed: items are checked one
    # by one below, so a single bad item cannot fail the whole batch.
    from .schemas import SCHEMAS

    props = dict(SCHEMAS["IngestBatch"]["properties"])
    for name in SECTIONS:
        props[name] = {"type": "array", "maxItems": props[name]["maxItems"]}
    return validator("IngestBatch", properties=props)


_ENVELOPE = _envelope_validator()
_ITEMS = {section: validator(schema) for section, schema in _ITEM_SCHEMA.items()}


def _message(error: ValidationError) -> str:
    where = ".".join(str(p) for p in error.absolute_path)
    return f"{where}: {error.message}" if where else error.message


def parse_ts(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None  # a time without a zone is ambiguous: refuse rather than guess
    return parsed.astimezone(UTC)


def _looks_personal(key: str, value: object) -> bool:
    if key.lower() in _PERSONAL_KEYS:
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


def _check_item(section: str, item: dict[str, Any], now: datetime) -> tuple[str, str] | None:
    """(code, message) if the item is refused, else None. Normalises `ts` in place."""
    errors = list(_ITEMS[section].iter_errors(item))
    if errors:
        best = best_match(errors)
        return "invalid", _message(best if best is not None else errors[0])

    raw_ts = item.get("ts")
    if raw_ts is None:
        ts = now  # contract: metric `ts` defaults to receipt time
    else:
        parsed = parse_ts(raw_ts)
        if parsed is None:
            return "invalid", "ts: must be an RFC 3339 date-time with a time zone"
        ts = parsed
    if ts < now - MAX_AGE:
        return "too_old", "ts is more than 24 hours in the past."
    if ts > now + MAX_AHEAD:
        return "in_future", "ts is more than 5 minutes in the future."
    item["ts"] = ts.isoformat()

    attrs = item.get(_ATTR_FIELD[section]) or {}
    for key, value in attrs.items():
        if _looks_personal(key, value):
            return (
                "personal_data",
                f"'{key}' looks like personal data. Do not send emails, names, IP "
                "addresses or user ids; hash or drop them.",
            )
    return None


def validate_batch(payload: Any, *, now: datetime, max_items: int) -> ValidatedBatch:
    """Raise `EnvelopeError` / `TooManyItems`, or return what was accepted."""
    if not isinstance(payload, dict):
        raise EnvelopeError("The body must be a JSON object.")
    total = sum(len(v) for k, v in payload.items() if k in SECTIONS and isinstance(v, list))
    if total > max_items:
        raise TooManyItems(f"At most {max_items} items per request; this one has {total}.")
    errors = list(_ENVELOPE.iter_errors(payload))
    if errors:
        best = best_match(errors)
        raise EnvelopeError(_message(best if best is not None else errors[0]))

    batch = ValidatedBatch(resource=payload.get("resource") or {})
    for section in SECTIONS:
        seen_ids: set[str] = set()
        for index, item in enumerate(payload.get(section) or []):
            if not isinstance(item, dict):
                batch.rejected.append(Rejection(section, index, "invalid", "must be an object"))
                continue
            problem = _check_item(section, item, now)
            if problem is None and "id" in item:
                if item["id"] in seen_ids:
                    problem = ("duplicate", "The same id appears twice in this request.")
                seen_ids.add(item["id"])
            if problem is None:
                batch.section(section).append((index, item))
            else:
                batch.rejected.append(Rejection(section, index, *problem))
    return batch
