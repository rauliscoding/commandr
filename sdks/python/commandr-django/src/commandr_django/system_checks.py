# SPDX-License-Identifier: AGPL-3.0-only
"""`manage.py check` warnings for a half-configured SDK. Warnings only: never stop a deploy."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Tags, Warning, register

from .conf import get_config, unknown_keys


@register(Tags.compatibility)
def check_settings(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    if not hasattr(settings, "COMMANDR"):
        return [
            Warning(
                "COMMANDR is not set, so nothing is sent to Commandr.",
                hint="Add COMMANDR = {'INGEST_KEY': ..., 'SIGNING_SECRET': ..., 'SERVICE': ...}.",
                id="commandr_django.W001",
            )
        ]
    config = get_config()
    messages: list[CheckMessage] = []
    if not config.service:
        messages.append(
            Warning(
                "COMMANDR['SERVICE'] is not set; it names this app in Commandr.",
                id="commandr_django.W002",
            )
        )
    if not config.signing_secret:
        messages.append(
            Warning(
                "COMMANDR['SIGNING_SECRET'] is not set; the status endpoint will answer 401.",
                id="commandr_django.W003",
            )
        )
    if not config.ingest_key:
        messages.append(
            Warning(
                "COMMANDR['INGEST_KEY'] is not set; traffic, errors and events are not sent.",
                id="commandr_django.W004",
            )
        )
    if not config.ingest_url.startswith("https://"):
        messages.append(
            Warning(
                "COMMANDR['INGEST_URL'] is not https://; the ingest key would travel unencrypted.",
                id="commandr_django.W005",
            )
        )
    for key in unknown_keys():
        messages.append(
            Warning(f"COMMANDR[{key!r}] is not a setting the SDK knows.", id="commandr_django.W006")
        )
    return messages
