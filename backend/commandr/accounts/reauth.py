"""Recent authentication for sensitive actions (security.md § Authentication).

Connecting or removing an integration and creating keys require that the
person signed in, or re-entered their password, within
`ACCOUNT_REAUTHENTICATION_TIMEOUT`. Otherwise the API answers 401 with
`code: reauthentication_required`; the SPA asks for the password (allauth
headless `auth/reauthenticate`) and retries.
"""

from __future__ import annotations

import time

from allauth.account.authentication import get_authentication_records
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

CODE = "reauthentication_required"


class ReauthenticationRequired(APIException):
    # Not NotAuthenticated: DRF would turn that into a 403 for session auth.
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = CODE

    def __init__(self) -> None:
        super().__init__({"detail": "Enter your password again to do this.", "code": CODE})


def recently_authenticated(request: Request) -> bool:
    records = get_authentication_records(request._request)
    if not records:
        return False
    latest = max(float(r.get("at", 0)) for r in records)
    return time.time() - latest < settings.ACCOUNT_REAUTHENTICATION_TIMEOUT


class RecentAuthForWrites(BasePermission):
    """Unsafe methods need a recent sign-in or password re-entry."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if not recently_authenticated(request):
            raise ReauthenticationRequired()
        return True
