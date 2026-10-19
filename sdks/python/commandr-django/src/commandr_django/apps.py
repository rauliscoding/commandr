# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import logging

from django.apps import AppConfig


class CommandrConfig(AppConfig):
    name = "commandr_django"
    label = "commandr_django"
    verbose_name = "Commandr"

    def ready(self) -> None:
        from . import system_checks  # noqa: F401  registers the settings checks
        from .conf import get_config
        from .handler import CommandrHandler

        config = get_config()
        if config.enabled and config.capture_errors:
            # Logging is configured before apps are ready, so this survives
            # LOGGING. django.request propagates here unless LOGGING stops it.
            root = logging.getLogger()
            if not any(isinstance(h, CommandrHandler) for h in root.handlers):
                root.addHandler(CommandrHandler())
