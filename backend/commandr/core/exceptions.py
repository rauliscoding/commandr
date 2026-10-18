import logging
from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger(__name__)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF's handler, plus: unexpected errors never leak internals to the client.

    `set_rollback()` matters: DRF turns the exception into a response, so the
    request transaction (ATOMIC_REQUESTS) would otherwise try to COMMIT whatever
    half-done work raised it.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        set_rollback()
        return Response(
            {"detail": "Something went wrong on our side. It has been logged."},
            status=500,
        )
    return response
