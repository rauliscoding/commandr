"""Encryption for customer credentials (OAuth tokens, API keys, app secrets).

MultiFernet over `settings.VAULT_KEYS` (newest first): new data is always sealed
with the newest key, and any listed key can open old data. The keys live in the
environment, never in the database or its backups — a stolen dump is ciphertext.

Rules (CLAUDE.md invariant 2): decrypt only inside the call that needs the
secret; never put plaintext in a log, an exception, a Celery argument or an API
response.
"""

import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class VaultError(Exception):
    """Ciphertext could not be opened. Never carries the plaintext or the key."""


@lru_cache(maxsize=4)
def _cipher(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise ImproperlyConfigured("VAULT_KEYS is empty.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except ValueError as exc:
        raise ImproperlyConfigured("VAULT_KEYS contains an invalid Fernet key.") from exc


def _current() -> MultiFernet:
    return _cipher(tuple(settings.VAULT_KEYS))


def seal(data: dict[str, Any]) -> bytes:
    return _current().encrypt(json.dumps(data, separators=(",", ":")).encode())


def unseal(token: bytes | memoryview) -> dict[str, Any]:
    try:
        raw = _current().decrypt(bytes(token))
    except InvalidToken as exc:
        raise VaultError("Stored credentials could not be decrypted.") from exc
    result: dict[str, Any] = json.loads(raw)
    return result


def rotate(token: bytes | memoryview) -> bytes:
    """Re-encrypt with the newest key. Idempotent."""
    try:
        return _current().rotate(bytes(token))
    except InvalidToken as exc:
        raise VaultError("Stored credentials could not be decrypted.") from exc
