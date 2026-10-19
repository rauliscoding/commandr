# SPDX-License-Identifier: AGPL-3.0-only
"""`@commandr.heartbeat("nightly-prune")`: tells Commandr a scheduled job ran.

The token comes from `COMMANDR["HEARTBEATS"]["nightly-prune"]` (a token or the
whole URL shown at setup). Pings go through the background sender: the job
never waits on Commandr, and a job's own exception is re-raised untouched.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar, cast

from . import _log
from .conf import get_config
from .transport import transport

F = TypeVar("F", bound=Callable[..., Any])
MAX_FAIL_MESSAGE = 1000


def _url(name: str) -> str | None:
    config = get_config()
    value = config.heartbeats.get(name, "")
    if not value:
        _log.warn(
            f"heartbeat:{name}",
            "commandr: no heartbeat named %r in COMMANDR['HEARTBEATS']; not pinged.",
            name,
        )
        return None
    if value.startswith(("https://", "http://")):
        return value.rstrip("/")
    return f"{config.ingest_url}/v1/heartbeat/{value}"


def ping(name: str, outcome: str = "success", message: str = "") -> None:
    """Ping by hand: `outcome` is "success", "start" or "fail"."""
    try:
        url = _url(name)
        if url is None:
            return
        if outcome == "start":
            transport.ping(f"{url}/start")
        elif outcome == "fail":
            body = message[:MAX_FAIL_MESSAGE].encode() if message else None
            transport.ping(f"{url}/fail", body)
        else:
            transport.ping(url)
    except Exception as exc:
        _log.warn("heartbeat", "commandr: heartbeat not sent (%s).", type(exc).__name__)


def _failure(exc: BaseException) -> str:
    # Type and message: the server truncates to 1,000 characters and scrubs tokens.
    text = str(exc)
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


@contextmanager
def _beat(name: str) -> Iterator[None]:
    ping(name, "start")
    try:
        yield
    except BaseException as exc:
        ping(name, "fail", _failure(exc))
        raise
    ping(name)


def heartbeat(name: str) -> Callable[[F], F]:
    """Decorate a job (sync or async): start, then success or fail with the error."""

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with _beat(name):
                    return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _beat(name):
                return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator
