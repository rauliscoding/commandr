import re
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .ids import uuid7
from .logging import request_id_var

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    """Gives every request an id, accepted from Caddy if well-formed, echoed back."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-Id", "")
        rid = incoming if _SAFE_ID.match(incoming) else uuid7().hex
        token = request_id_var.set(rid)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-Id"] = rid
        return response
