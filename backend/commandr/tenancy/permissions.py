from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import Role


class HasOrgRole(BasePermission):
    """Role check against the membership `OrgScopedMixin` resolved.

    Views set `read_role` / `write_role` (defaults: viewer / member). The API is
    the boundary: the UI hiding a button is a convenience, this is the rule.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        if request.method in SAFE_METHODS:
            needed = getattr(view, "read_role", Role.VIEWER)
        else:
            needed = getattr(view, "write_role", Role.MEMBER)
        return bool(membership.has_role(needed))
