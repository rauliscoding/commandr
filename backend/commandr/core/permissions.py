from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

if TYPE_CHECKING:  # DRF settings import this module while rest_framework.views loads
    from rest_framework.request import Request
    from rest_framework.views import APIView


class DenyAll(BasePermission):
    """The DRF default. A view that forgets its permission classes refuses everyone."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return False
