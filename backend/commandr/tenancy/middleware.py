from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from . import context


class TenantResetMiddleware:
    """Start every request with no tenant, whatever the worker thread last served."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        context.clear()
        try:
            return self.get_response(request)
        finally:
            context.clear()
