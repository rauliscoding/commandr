# SPDX-License-Identifier: AGPL-3.0-only
"""`TrafficMiddleware`: counts requests per route template, sync and async."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponseBase

from . import _log
from .conf import get_config
from .traffic import UNMATCHED, route_template, traffic
from .transport import transport


def _collect() -> list[dict[str, Any]]:
    return traffic.collect(transport.ts_offset_us)


def route_of(request: HttpRequest) -> str:
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", None) if match is not None else None
    return route_template(route) if route is not None else UNMATCHED


class TrafficMiddleware:
    """Put it near the top of MIDDLEWARE so it times the whole request."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)
        transport.add_collector(_collect)

    def __call__(self, request: HttpRequest) -> Any:
        if self.is_async:
            return self._acall(request)
        started = time.perf_counter()
        response = self.get_response(request)
        self._record(request, response, started)
        return response

    async def _acall(self, request: HttpRequest) -> HttpResponseBase:
        started = time.perf_counter()
        get_response: Callable[[HttpRequest], Awaitable[HttpResponseBase]] = self.get_response
        response = await get_response(request)
        self._record(request, response, started)
        return response

    def _record(self, request: HttpRequest, response: HttpResponseBase, started: float) -> None:
        try:
            config = get_config()
            if not config.can_push or request.path.startswith(config.traffic_exclude):
                return
            duration_ms = (time.perf_counter() - started) * 1000
            traffic.record(route_of(request), response.status_code, duration_ms)
            transport.ensure_started(config)
        except Exception as exc:  # never into the host's request
            _log.warn("traffic", "commandr: traffic not recorded (%s).", type(exc).__name__)
