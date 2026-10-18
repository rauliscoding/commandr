import contextvars
import uuid
from typing import Any

from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import context
from .models import Membership


class OrgScopedMixin(APIView):
    """Resolves `org_id` from the URL to the caller's membership and activates
    that tenant for the rest of the request.

    Not a member gets 404, never 403: we do not confirm that another customer's
    organization exists.
    """

    _tenant_token: contextvars.Token[uuid.UUID | None] | None = None

    def check_permissions(self, request: Request) -> None:
        if request.user and request.user.is_authenticated and not hasattr(request, "membership"):
            membership = (
                Membership.objects.select_related("organization")
                .filter(organization_id=self.kwargs.get("org_id"), user=request.user)
                .first()
            )
            if membership is None:
                raise NotFound()
            request.membership = membership  # type: ignore[attr-defined]
            request.organization = membership.organization  # type: ignore[attr-defined]
            self._tenant_token = context.activate(membership.organization_id)
        super().check_permissions(request)

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        token = getattr(self, "_tenant_token", None)
        if token is not None:
            context.deactivate(token)
            self._tenant_token = None
        return super().finalize_response(request, response, *args, **kwargs)
