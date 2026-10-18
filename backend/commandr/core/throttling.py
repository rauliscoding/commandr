from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.throttling import UserRateThrottle

if TYPE_CHECKING:  # DRF settings import this module while rest_framework.views loads
    from rest_framework.request import Request
    from rest_framework.views import APIView


class PerUserThrottle(UserRateThrottle):
    """Keyed per authenticated user; anonymous callers fall back to the client IP.

    Never key a limit globally: one noisy caller must not throttle everyone else.
    """

    scope = "user"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        if request.user and request.user.is_authenticated:
            ident = str(request.user.pk)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
