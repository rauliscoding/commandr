from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from commandr.tenancy.mixins import OrgScopedMixin
from commandr.tenancy.models import Project
from commandr.tenancy.permissions import HasOrgRole

from .catalogue import build_catalogue


class CatalogueView(OrgScopedMixin):
    """GET the integration catalogue for one project: the project's home screen
    until something is connected (docs/product/onboarding-and-catalogue.md)."""

    permission_classes = [IsAuthenticated, HasOrgRole]

    def get(self, request: Request, org_id: Any, project_id: Any) -> Response:
        project = get_object_or_404(Project.objects.all(), pk=project_id)
        return Response(build_catalogue(project_id=project.id, project_kind=project.kind))
