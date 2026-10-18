"""The current tenant, in Python and in Postgres at the same time.

Two layers enforce isolation (ADR 0002), and both read the tenant set here:

* `TenantScopedManager` filters on the context variable;
* Postgres row-level security filters on `app.current_org_id`, set with
  `set_config(..., is_local => true)` so it lives only as long as the current
  transaction (safe with connection pooling — it cannot leak into the next
  request that reuses the connection).

With no tenant set, both layers return **nothing**. Never the other way round.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction

_current_org: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "commandr_current_org", default=None
)


class TenantContextError(RuntimeError):
    pass


def current_org_id() -> uuid.UUID | None:
    return _current_org.get()


def _set_db_org(org_id: uuid.UUID | None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org_id', %s, true)",
            [str(org_id) if org_id else ""],
        )


def activate(org_id: uuid.UUID) -> contextvars.Token[uuid.UUID | None]:
    """Set the tenant for the rest of the current transaction (request scope).

    Must be called inside a transaction — `ATOMIC_REQUESTS` provides one for
    views. Returns a token for `deactivate`.
    """
    if not connection.in_atomic_block:
        raise TenantContextError("activate() must run inside a transaction.")
    token = _current_org.set(org_id)
    _set_db_org(org_id)
    return token


def deactivate(token: contextvars.Token[uuid.UUID | None]) -> None:
    """Undo `activate` in both layers.

    In production the request transaction ends right after, taking the database
    setting with it; resetting it here as well means nothing later in the same
    transaction (a test, a nested call) can quietly inherit this tenant. A
    transaction already marked for rollback cannot run the reset, and does not
    need to: the rollback discards the setting.
    """
    _current_org.reset(token)
    if connection.in_atomic_block and not connection.needs_rollback:
        _set_db_org(_current_org.get())


def clear() -> None:
    """Forget any tenant (start of every request, as a belt-and-braces reset)."""
    _current_org.set(None)


@contextmanager
def tenant_context(org_id: uuid.UUID) -> Iterator[None]:
    """Run a block as one tenant. For tasks, commands and tests.

    Opens a transaction (or savepoint), so the database setting is scoped to it.
    On normal exit the previous tenant is restored in both layers; on an
    exception the savepoint rollback undoes the database setting by itself.
    """
    with transaction.atomic():
        previous = _current_org.get()
        token = _current_org.set(org_id)
        _set_db_org(org_id)
        try:
            yield
        except BaseException:
            _current_org.reset(token)
            raise
        _set_db_org(previous)
        _current_org.reset(token)
