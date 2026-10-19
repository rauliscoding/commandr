"""Settings, system checks and the signing module's agreement with the server."""

from __future__ import annotations

import time
from typing import Any

import pytest
from django.core.checks import run_checks

from commandr_django import signing

from .conftest import server_signing


def ids(settings: Any) -> set[str]:
    return {m.id for m in run_checks() if m.id and m.id.startswith("commandr_django")}


def test_complete_settings_give_no_warnings(settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": "https://ingest.example.com"}
    assert ids(settings) == set()


def test_missing_settings_are_warnings(settings: Any) -> None:
    settings.COMMANDR = {"INGEST_URL": "http://ingest.example.com", "TYPO": 1}
    assert ids(settings) == {
        "commandr_django.W002",
        "commandr_django.W003",
        "commandr_django.W004",
        "commandr_django.W005",
        "commandr_django.W006",
    }


def test_no_settings_at_all(settings: Any) -> None:
    del settings.COMMANDR
    assert ids(settings) == {"commandr_django.W001"}


@pytest.mark.parametrize("path", ["/.well-known/commandr/status", "/x/y%20z", "/"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_sdk_accepts_exactly_what_the_server_signs(path: str, method: str) -> None:
    server = server_signing()
    now = int(time.time())
    header = server.sign("s3cret", method, path, now)
    assert signing.verify("s3cret", header, method, path, now)
    assert server.verify("s3cret", header, method, path, now)
    for other in (
        ("other", header, method, path, now),
        ("s3cret", header, "POST", path, now),
        ("s3cret", header, method, path + "x", now),
        ("s3cret", header, method, path, now + 301),
    ):
        assert signing.verify(*other) is False
        assert server.verify(*other) is False


def test_empty_secret_never_verifies() -> None:
    server = server_signing()
    header = server.sign("", "GET", "/", 100)
    assert signing.verify("", header, "GET", "/", 100) is False
