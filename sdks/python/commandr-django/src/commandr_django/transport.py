# SPDX-License-Identifier: AGPL-3.0-only
"""Sends to the push API on one background thread per process.

Nothing here may block or raise into the host app:

* `enqueue_*` only append to bounded buffers under a lock; when a buffer is
  full the new item is dropped and counted;
* the thread is a daemon started lazily, and again after a fork (gunicorn and
  Celery prefork children inherit the buffers but not the thread);
* a failed send is retried with backoff and the same Idempotency-Key, then
  dropped; problems are logged at WARNING at most once a minute.
"""

from __future__ import annotations

import atexit
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import _log
from .conf import Config, get_config

SCHEMA = "commandr.ingest/v1"
MAX_ITEMS = 1000  # per request (contract)
MAX_ERRORS = 200
MAX_BODY = 900_000  # under the 1 MB limit, with room for headers and rounding
MAX_ATTEMPTS = 5
MAX_PINGS = 100
USER_AGENT = "commandr-django/0.1.0"

Collector = Callable[[], list[dict[str, Any]]]


@dataclass
class _Batch:
    body: bytes
    count: int
    key: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0


@dataclass
class _Ping:
    url: str
    body: bytes | None
    attempts: int = 0


class Transport:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._wake = threading.Event()
        self._metrics: deque[dict[str, Any]] = deque()
        self._events: deque[dict[str, Any]] = deque()
        self._errors: deque[dict[str, Any]] = deque()
        self._pings: deque[_Ping] = deque()
        self._collectors: list[Collector] = []
        self._retry: _Batch | None = None
        self._retry_at = 0.0
        self._dropped = 0
        self._thread: threading.Thread | None = None
        self._pid = 0
        self._next_flush = 0.0
        self._stopping = False
        self.ts_offset_us = 0

    # --- called from the host app's threads ---------------------------------

    def add_collector(self, collector: Collector) -> None:
        """`collector()` is called at each flush and returns metrics to send."""
        with self._lock:
            if collector not in self._collectors:
                self._collectors.append(collector)

    def enqueue(self, section: str, item: dict[str, Any]) -> None:
        config = get_config()
        if not config.can_push:
            return
        self._ensure_thread(config)
        buffer = {"metrics": self._metrics, "events": self._events, "errors": self._errors}[section]
        with self._lock:
            if self._buffered() >= config.max_buffer:
                self._dropped += 1
                return
            buffer.append(item)
            full = self._buffered() >= MAX_ITEMS
        if full:
            self._wake.set()

    def ensure_started(self, config: Config) -> None:
        if config.can_push:
            self._ensure_thread(config)

    def ping(self, url: str, body: bytes | None = None) -> None:
        """A heartbeat ping: sent straight away, not at the next flush."""
        config = get_config()
        if not config.enabled:
            return
        self._ensure_thread(config)
        with self._lock:
            if len(self._pings) >= MAX_PINGS:
                self._dropped += 1
                return
            self._pings.append(_Ping(url, body))
        self._wake.set()

    def flush(self, timeout: float | None = None) -> None:
        """Send everything now, from the calling thread. For shutdown and tests."""
        config = get_config()
        deadline = time.monotonic() + (timeout if timeout is not None else config.send_timeout)
        # The sender thread may be mid-send to a server that hangs: wait for it
        # only until the deadline, so shutdown is never held up for long.
        if not self._send_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            return
        try:
            self._send_pings(config, deadline)
            self._send_data(config, deadline, force=True)
        finally:
            self._send_lock.release()

    # --- the background thread ----------------------------------------------

    def _buffered(self) -> int:
        return len(self._metrics) + len(self._events) + len(self._errors)

    def _ensure_thread(self, config: Config) -> None:
        pid = os.getpid()
        if self._pid == pid and self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._pid != pid:
                # A forked child: what is buffered belongs to the parent, which sends it.
                self._metrics.clear()
                self._events.clear()
                self._errors.clear()
                self._pings.clear()
                self._retry = None
                self._pid = pid
                # Points are de-duplicated by (series, ts) on the server, so every
                # process stamps its windows with its own sub-second offset:
                # several workers' counters for the same minute all count.
                self.ts_offset_us = random.randrange(1, 1_000_000)  # noqa: S311 not security
                self._thread = None
            if self._thread is not None and self._thread.is_alive():
                return
            self._next_flush = time.monotonic() + config.flush_interval
            self._thread = threading.Thread(target=self._run, name="commandr-sender", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stopping:
            wait = max(
                0.0, min(self._next_flush, self._retry_at or self._next_flush) - time.monotonic()
            )
            self._wake.wait(wait)
            self._wake.clear()
            if self._stopping:
                return
            config = get_config()  # read after waking: settings may have changed
            try:
                with self._send_lock:
                    deadline = time.monotonic() + config.send_timeout * 3
                    self._send_pings(config, deadline)
                    due = time.monotonic() >= self._next_flush or self._buffered() >= MAX_ITEMS
                    if due:
                        self._next_flush = time.monotonic() + config.flush_interval
                    self._send_data(config, deadline, force=due)
            except Exception as exc:  # the thread must survive anything
                _log.warn(
                    "sender", "commandr: sender error (%s); will try again.", type(exc).__name__
                )

    def _send_pings(self, config: Config, deadline: float) -> None:
        while time.monotonic() < deadline:
            with self._lock:
                if not self._pings:
                    return
                ping = self._pings.popleft()
            status = _post(ping.url, ping.body, {"Content-Type": "text/plain"}, config, deadline)
            if status is None or status >= 500 or status == 429:
                ping.attempts += 1
                if ping.attempts < 3:
                    with self._lock:
                        self._pings.append(ping)
                    return  # try again at the next wake-up rather than spin
                _log.warn("ping", "commandr: a heartbeat ping could not be sent; dropped.")
            elif status == 404:
                _log.warn(
                    "ping-404",
                    "commandr: Commandr does not know a heartbeat token (removed?); "
                    "check COMMANDR['HEARTBEATS'].",
                )

    def _collect(self) -> None:
        for collector in list(self._collectors):
            try:
                for item in collector():
                    self.enqueue("metrics", item)
            except Exception as exc:
                _log.warn("collector", "commandr: collector failed (%s).", type(exc).__name__)

    def _send_data(self, config: Config, deadline: float, *, force: bool) -> None:
        if not config.can_push:
            return
        if force:
            self._collect()
        if self._retry is not None:
            if time.monotonic() < self._retry_at and not self._stopping:
                return
            if not self._deliver(self._retry, config, deadline):
                return
            self._retry = None
        while time.monotonic() < deadline:
            if not force and self._buffered() < MAX_ITEMS:
                return
            batch = self._next_batch(config)
            if batch is None:
                return
            if not self._deliver(batch, config, deadline):
                return

    def _next_batch(self, config: Config) -> _Batch | None:
        with self._lock:
            if not self._buffered():
                if self._dropped:
                    _log.warn(
                        "dropped",
                        "commandr: %s items were dropped because the buffer was full.",
                        self._dropped,
                    )
                    self._dropped = 0
                return None
            errors = [self._errors.popleft() for _ in range(min(len(self._errors), MAX_ERRORS))]
            room = MAX_ITEMS - len(errors)
            events = [self._events.popleft() for _ in range(min(len(self._events), room))]
            room -= len(events)
            metrics = [self._metrics.popleft() for _ in range(min(len(self._metrics), room))]
        while True:
            payload: dict[str, Any] = {
                "schema": SCHEMA,
                "sent_at": _now_iso(),
                "resource": _resource(config),
            }
            for name, items in (("metrics", metrics), ("events", events), ("errors", errors)):
                if items:
                    payload[name] = items
            body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
            count = len(metrics) + len(events) + len(errors)
            if len(body) <= MAX_BODY or count <= 1:
                return _Batch(body, count)
            # Too big (long stacks): send half now, put the rest back in front.
            back_m, back_e, back_r = (
                metrics[len(metrics) // 2 :],
                events[len(events) // 2 :],
                errors[len(errors) // 2 :],
            )
            metrics, events, errors = (
                metrics[: len(metrics) // 2],
                events[: len(events) // 2],
                errors[: len(errors) // 2],
            )
            with self._lock:
                self._metrics.extendleft(reversed(back_m))
                self._events.extendleft(reversed(back_e))
                self._errors.extendleft(reversed(back_r))

    def _deliver(self, batch: _Batch, config: Config, deadline: float) -> bool:
        """True when the batch is finished with (sent or given up); False to retry later."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.ingest_key}",
            "Idempotency-Key": batch.key,
        }
        status = _post(f"{config.ingest_url}/v1/ingest", batch.body, headers, config, deadline)
        if status == 202:
            return True
        if status in (400, 401, 403, 413):
            reason = {
                401: "the ingest key was refused (revoked, or from another project?)",
                403: "the ingest key was refused",
                413: "the batch was too large",
            }.get(status, "the batch was malformed")
            _log.warn(
                "refused", "commandr: %s items dropped: %s (HTTP %s).", batch.count, reason, status
            )
            return True
        batch.attempts += 1
        if batch.attempts >= MAX_ATTEMPTS:
            _log.warn(
                "gave-up",
                "commandr: %s items dropped after %s attempts.",
                batch.count,
                batch.attempts,
            )
            return True
        _log.warn(
            "send",
            "commandr: could not reach %s (%s); retrying in the background.",
            config.ingest_url,
            f"HTTP {status}" if status else "no answer",
        )
        backoff = min(300.0, 5.0 * 2**batch.attempts)
        self._retry = batch
        self._retry_at = time.monotonic() + backoff * random.uniform(0.5, 1.0)  # noqa: S311
        return False

    def shutdown(self, timeout: float = 2.0) -> None:
        if self._pid != os.getpid() or self._thread is None:
            return
        try:
            self.flush(timeout)
        except Exception:  # interpreter shutdown: nothing useful left to do
            return

    def reset(self) -> None:
        """For tests: forget everything, stop nothing (the thread is a daemon)."""
        with self._lock:
            self._metrics.clear()
            self._events.clear()
            self._errors.clear()
            self._pings.clear()
            self._retry = None
            self._retry_at = 0.0
            self._dropped = 0

    def pending(self) -> dict[str, int]:
        with self._lock:
            return {
                "metrics": len(self._metrics),
                "events": len(self._events),
                "errors": len(self._errors),
                "pings": len(self._pings),
            }


def _resource(config: Config) -> dict[str, str]:
    resource = {"service": (config.service or "django")[:120]}
    if config.version:
        resource["version"] = str(config.version)[:64]
    if config.environment:
        resource["environment"] = str(config.environment)[:32]
    return resource


def _now_iso() -> str:
    from .status import now_iso

    return now_iso()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # a redirect would resend the ingest key somewhere else


_opener = urllib.request.build_opener(_NoRedirect)


def _post(
    url: str, body: bytes | None, headers: dict[str, str], config: Config, deadline: float
) -> int | None:
    """The HTTP status, or None when there was no answer."""
    if not url.startswith(("https://", "http://")):
        return None
    timeout = min(config.send_timeout, deadline - time.monotonic())
    if timeout <= 0:
        return None
    request = urllib.request.Request(  # noqa: S310 scheme checked above
        url, data=body or b"", headers={**headers, "User-Agent": USER_AGENT}, method="POST"
    )
    try:
        with _opener.open(request, timeout=timeout) as response:
            response.read(65_536)
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:  # DNS, refused, TLS, timeout: all "no answer"
        return None


transport = Transport()
atexit.register(transport.shutdown)
