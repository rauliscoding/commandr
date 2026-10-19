from __future__ import annotations

import importlib.util
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from commandr_django import _log, registry
from commandr_django.traffic import traffic
from commandr_django.transport import transport

REPO = Path(__file__).resolve().parents[4]
OPENAPI = REPO / "docs/architecture/openapi/ingest-v1.yaml"
SERVER_SIGNING = REPO / "backend/commandr/monitoring/signing.py"

SECRET = "test-signing-secret"


# --- The contract ------------------------------------------------------------

_formats = FormatChecker()


@_formats.checks("date-time", raises=ValueError)
def _date_time(value: object) -> bool:
    # What the server accepts (ingest.validation): ISO 8601 with a time zone.
    if not isinstance(value, str):
        return True
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None


def contract(name: str) -> Draft202012Validator:
    """A validator for one of the OpenAPI file's components.schemas."""
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    root = {"components": spec["components"], "$ref": f"#/components/schemas/{name}"}
    return Draft202012Validator(root, format_checker=_formats)


def assert_valid(name: str, document: Any) -> None:
    errors = [f"{list(e.absolute_path)}: {e.message}" for e in contract(name).iter_errors(document)]
    assert not errors, errors


def server_signing() -> ModuleType:
    """The server's own signing module, so the SDK verifies what Commandr actually sends."""
    spec = importlib.util.spec_from_file_location("server_signing", SERVER_SIGNING)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- A fake Commandr ingest server -------------------------------------------


@dataclass
class Received:
    path: str
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class FakeIngest:
    url: str = ""
    received: list[Received] = field(default_factory=list)
    statuses: list[int] = field(default_factory=list)  # answered in order, then 202
    delay: float = 0.0  # seconds before answering: a server that hangs
    lock: threading.Lock = field(default_factory=threading.Lock)

    def batches(self) -> list[dict[str, Any]]:
        with self.lock:
            return [r.json() for r in self.received if r.path == "/v1/ingest"]

    def wait_for(self, count: int, timeout: float = 5.0) -> list[Received]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if len(self.received) >= count:
                    return list(self.received)
            time.sleep(0.02)
        with self.lock:
            return list(self.received)


@pytest.fixture
def ingest() -> Iterator[FakeIngest]:
    fake = FakeIngest()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            with fake.lock:
                fake.received.append(Received(self.path, dict(self.headers.items()), body))
                status = fake.statuses.pop(0) if fake.statuses else None
            if fake.delay:
                time.sleep(fake.delay)
            if self.path == "/v1/ingest":
                status = status or 202
                payload = json.dumps({"accepted": 1, "rejected": []}).encode()
            else:
                status = status or 204
                payload = b""
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def pushing(settings: Any, ingest: FakeIngest) -> dict[str, Any]:
    """COMMANDR pointed at the fake ingest server. Mutate and reassign to change it."""
    config = {**settings.COMMANDR, "INGEST_URL": ingest.url}
    settings.COMMANDR = config
    return config


def _quiesce() -> None:
    """Wait for a send in flight on the background thread, so tests do not overlap."""
    if transport._send_lock.acquire(timeout=5):
        transport._send_lock.release()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    _quiesce()
    transport.reset()
    traffic.reset()
    registry.unregister_all()
    _log.reset()
    yield
    _quiesce()
    transport.reset()
    traffic.reset()
    registry.unregister_all()
