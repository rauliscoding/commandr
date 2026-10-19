# SPDX-License-Identifier: AGPL-3.0-only
"""`CommandrHandler`: sends ERROR (and above) log records as errors, with fingerprints.

The fingerprint groups occurrences of the same problem: the exception type,
its culprit (the innermost frame in the app's own code) and the stack's frames
without line numbers, so a deploy that shifts lines keeps the group.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sysconfig
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from types import TracebackType
from typing import Any

from . import _log
from .transport import transport

MAX_MESSAGE = 2000
MAX_STACK = 65_536
PER_FINGERPRINT_PER_MINUTE = 10

_LIBRARY_DIRS = tuple(
    os.path.normcase(os.path.realpath(p))
    for p in {sysconfig.get_paths()[k] for k in ("stdlib", "platstdlib", "purelib", "platlib")}
)
_guard = threading.local()


def _is_library(filename: str) -> bool:
    path = os.path.normcase(os.path.realpath(filename))
    return path.startswith(_LIBRARY_DIRS) or "site-packages" in path


def _normalise(filename: str) -> str:
    """A path that is the same on every machine: from `site-packages` or the app's root."""
    path = filename.replace("\\", "/")
    for marker in ("/site-packages/", "/dist-packages/"):
        if marker in path:
            return path.split(marker, 1)[1]
    cwd = os.getcwd().replace("\\", "/").rstrip("/") + "/"
    return path[len(cwd) :] if path.startswith(cwd) else os.path.basename(path)


def _culprit(tb: TracebackType | None) -> str:
    """`module.qualname` of the innermost frame in app code (else the innermost frame)."""
    innermost = app = None
    while tb is not None:
        innermost = tb
        if not _is_library(tb.tb_frame.f_code.co_filename):
            app = tb
        tb = tb.tb_next
    chosen = app or innermost
    if chosen is None:
        return ""
    code = chosen.tb_frame.f_code
    module = chosen.tb_frame.f_globals.get("__name__", "")
    name = getattr(code, "co_qualname", code.co_name)  # co_qualname: 3.11+
    return f"{module}.{name}" if module else name


def fingerprint(kind: str, culprit: str, frames: list[str]) -> str:
    raw = "\n".join([kind, culprit, *frames])
    return "sha1:" + hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()


def _level(levelno: int) -> str:
    if levelno >= logging.CRITICAL:
        return "critical"
    return "error" if levelno >= logging.ERROR else "warning"


def build_error(record: logging.LogRecord) -> dict[str, Any]:
    exc_type = exc = tb = None
    if record.exc_info and record.exc_info[0] is not None:
        exc_type, exc, tb = record.exc_info
    item: dict[str, Any] = {
        "id": f"err_{uuid.uuid4().hex}",
        "ts": datetime.fromtimestamp(record.created, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "level": _level(record.levelno),
    }
    if exc_type is not None:
        kind = exc_type.__name__
        culprit = _culprit(tb)
        frames = [f"{_normalise(f.filename)}:{f.name}" for f in traceback.extract_tb(tb)]
        message = str(exc) or record.getMessage()
        stack = "".join(traceback.format_exception(exc_type, exc, tb))
        item["type"] = kind[:200]
        item["stack"] = stack[-MAX_STACK:]  # the innermost frames are at the end
    else:
        # No exception: group by where it was logged and the message *template*,
        # so "Order %s failed" is one group however many orders fail.
        kind = "log"
        culprit = f"{record.name}.{record.funcName}"
        frames = [str(record.msg)[:500]]
        message = record.getMessage()
    item["fingerprint"] = fingerprint(kind, culprit, frames)
    item["message"] = (message or kind)[:MAX_MESSAGE]
    if culprit:
        item["culprit"] = culprit[:500]
    attrs = {"logger": record.name[:128]}
    request = getattr(record, "request", None)
    if request is not None:
        from .middleware import route_of

        attrs["route"] = route_of(request)
    item["attrs"] = attrs
    return item


class CommandrHandler(logging.Handler):
    """Add to LOGGING, or let the app add it to the root logger (CAPTURE_ERRORS)."""

    def __init__(self, level: int = logging.ERROR) -> None:
        super().__init__(level)
        self._seen: dict[str, tuple[float, int]] = {}
        self._seen_lock = threading.Lock()

    def _allow(self, fp: str) -> bool:
        """At most PER_FINGERPRINT_PER_MINUTE of one group a minute: a loop must not flood."""
        now = time.monotonic()
        with self._seen_lock:
            if len(self._seen) > 1000:
                self._seen.clear()
            started, count = self._seen.get(fp, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            self._seen[fp] = (started, count + 1)
            return count < PER_FINGERPRINT_PER_MINUTE

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("commandr_django") or getattr(_guard, "active", False):
            return  # never report our own warnings, never recurse
        _guard.active = True
        try:
            item = build_error(record)
            if self._allow(item["fingerprint"]):
                transport.enqueue("errors", item)
        except Exception as exc:
            _log.warn("handler", "commandr: error not captured (%s).", type(exc).__name__)
        finally:
            _guard.active = False
