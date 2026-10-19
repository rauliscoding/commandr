"""Generating and hashing the credentials customers' apps hold."""

import hashlib
import math
import secrets
import string

_BASE62 = string.digits + string.ascii_letters
KEY_PREFIX = "cmdr_ingest_"


def _base62(n_bytes: int) -> str:
    """Base62 of `n_bytes` random bytes: 32 bytes → 43 characters, 256 bits."""
    value = int.from_bytes(secrets.token_bytes(n_bytes), "big")
    width = math.ceil(n_bytes * 8 / math.log2(62))  # fixed length, so no length leak
    out = []
    while value:
        value, rem = divmod(value, 62)
        out.append(_BASE62[rem])
    return "".join(reversed(out)).rjust(width, "0")


def generate_ingest_key(environment: str) -> str:
    """`cmdr_ingest_<env>_<43 base62>`. The prefix lets secret scanners spot it."""
    return f"{KEY_PREFIX}{environment}_{_base62(32)}"


def generate_heartbeat_token() -> str:
    """43 URL-safe characters: unguessable, and short enough for a crontab line."""
    return secrets.token_urlsafe(32)


def generate_signing_secret() -> str:
    return f"cmdr_sign_{_base62(32)}"


def digest(credential: str) -> str:
    """SHA-256 hex. Credentials have 256 bits of entropy, so no salt or KDF is needed."""
    return hashlib.sha256(credential.encode()).hexdigest()
