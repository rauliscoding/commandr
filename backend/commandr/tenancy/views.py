from typing import Any, cast

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from commandr.accounts.models import User
from commandr.audit.services import record

from .context import tenant_context
from .mixins import OrgScopedMixin
from .models import Membership, Project, Role
from .permissions import HasOrgRole
from .serializers import OrganizationCreateSerializer, OrganizationSerializer, ProjectSerializer
from .services import create_organization


class MeView(APIView):
    """Who am I, and where can I go? Drives the SPA's first routing decision."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        organizations = []
        memberships = Membership.objects.filter(user=user).select_related("organization")
        for m in memberships.order_by("created_at"):
            # Projects live under RLS, so each organization is read in its own
            # tenant context; there is no cross-tenant query to write.
            with tenant_context(m.organization_id):
                projects = [
                    {"id": str(p["id"]), "name": p["name"], "kind": p["kind"]}
                    for p in Project.objects.values("id", "name", "kind")
                ]
            organizations.append(
                {
                    **OrganizationSerializer(m.organization).data,
                    "role": m.role,
                    "projects": projects,
                }
            )
        return Response(
            {
                "user": {
                    "id": str(user.pk),
                    "email": user.email,
                    "display_name": user.display_name,
                },
                "organizations": organizations,
            }
        )


class OrganizationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org, project = create_organization(
            owner=request.user,  # type: ignore[arg-type]
            data=serializer.validated_data,
        )
        return Response(
            {"organization": OrganizationSerializer(org).data, "project": {"id": str(project.id)}},
            status=status.HTTP_201_CREATED,
        )


class ProjectListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasOrgRole]
    serializer_class = ProjectSerializer
    write_role = Role.ADMIN

    def get_queryset(self) -> Any:
        return Project.objects.all()

    def perform_create(self, serializer: Any) -> None:
        project = serializer.save(created_by=self.request.user)
        record(
            "project.created",
            actor=self.request.user,  # type: ignore[arg-type]
            organization=self.request.organization,  # type: ignore[attr-defined]
            target=project,
        )


class ProjectDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasOrgRole]
    serializer_class = ProjectSerializer
    lookup_url_kwarg = "project_id"
    write_role = Role.ADMIN

    def get_queryset(self) -> Any:
        return Project.objects.all()

    def perform_destroy(self, instance: Project) -> None:
        record(
            "project.deleted",
            actor=self.request.user,  # type: ignore[arg-type]
            organization=self.request.organization,  # type: ignore[attr-defined]
            target=instance,
        )
        instance.delete()
