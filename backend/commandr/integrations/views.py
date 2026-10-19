from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from commandr.accounts.reauth import RecentAuthForWrites
from commandr.audit.services import record
from commandr.tenancy.mixins import OrgScopedMixin
from commandr.tenancy.models import Project, Role
from commandr.tenancy.permissions import HasOrgRole

from . import registry
from .catalogue import build_catalogue
from .models import Connection
from .setup import Detail, get_setup


class CatalogueView(OrgScopedMixin):
    """GET the integration catalogue for one project: the project's home screen
    until something is connected (docs/product/onboarding-and-catalogue.md)."""

    permission_classes = [IsAuthenticated, HasOrgRole]

    def get(self, request: Request, org_id: Any, project_id: Any) -> Response:
        project = get_object_or_404(Project.objects.all(), pk=project_id)
        return Response(build_catalogue(project_id=project.id, project_kind=project.kind))


# --- Connections: generic setup for every available connector ----------------


def _details(details: list[Detail]) -> list[dict[str, Any]]:
    return [{"label": d.label, "value": d.value, "kind": d.kind} for d in details]


def connection_data(conn: Connection) -> dict[str, Any]:
    """A connection as the API shows it. Never includes credentials: details come
    from the connector's `describe()`, which only reports safe values."""
    setup = get_setup(conn.connector_slug)
    try:
        name = registry.get(conn.connector_slug).name
    except KeyError:
        name = conn.connector_slug
    return {
        "id": str(conn.id),
        "connector": conn.connector_slug,
        "connector_name": name,
        "label": conn.label,
        "status": conn.status,
        "created_at": conn.created_at.isoformat(),
        "first_data_at": conn.first_data_at.isoformat() if conn.first_data_at else None,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "last_error": conn.last_error,
        "details": _details(setup.describe(conn)) if setup else [],
    }


class _ProjectScoped(OrgScopedMixin):
    # Connecting and removing integrations handles credentials: admins only,
    # and only with a recent sign-in (security.md § Authentication).
    permission_classes = [IsAuthenticated, HasOrgRole, RecentAuthForWrites]
    write_role = Role.ADMIN

    def project(self) -> Project:
        project: Project = get_object_or_404(Project.objects.all(), pk=self.kwargs["project_id"])
        return project

    def connection(self, project: Project) -> Connection:
        conn: Connection = get_object_or_404(
            Connection.objects.select_related("project"),
            pk=self.kwargs["connection_id"],
            project=project,
        )
        return conn


class ConnectionListCreateView(_ProjectScoped):
    """GET the project's sources; POST `{connector, fields}` to set one up."""

    def get(self, request: Request, **kwargs: Any) -> Response:
        project = self.project()
        conns = Connection.objects.filter(project=project).order_by("created_at")
        return Response({"results": [connection_data(c) for c in conns]})

    def post(self, request: Request, **kwargs: Any) -> Response:
        project = self.project()
        body = request.data if isinstance(request.data, dict) else {}
        slug = body.get("connector")
        setup = get_setup(slug) if isinstance(slug, str) else None
        if setup is None:
            return Response(
                {"connector": ["This integration cannot be connected yet."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        fields = body.get("fields") or {}
        if not isinstance(fields, dict):
            return Response({"fields": ["Expected an object."]}, status=status.HTTP_400_BAD_REQUEST)
        data = setup.validate(fields, project)
        user = request.user
        result = setup.create(project=project, user=user, data=data)  # type: ignore[arg-type]
        record(
            "connection.created",
            actor=user,  # type: ignore[arg-type]
            organization=request.organization,  # type: ignore[attr-defined]
            target=result.connection,
            metadata={"connector": slug},
            request=request._request,
        )
        return Response(
            {
                "connection": connection_data(result.connection),
                # Shown once, here, and never stored in plaintext.
                "reveal": [
                    {"label": r.label, "value": r.value, "kind": r.kind} for r in result.reveal
                ],
                "snippets": [
                    {"label": s.label, "code": s.code, "language": s.language}
                    for s in result.snippets
                ],
                "notes": result.notes,
            },
            status=status.HTTP_201_CREATED,
        )


class ConnectionDetailView(_ProjectScoped):
    def get(self, request: Request, **kwargs: Any) -> Response:
        return Response(connection_data(self.connection(self.project())))

    def delete(self, request: Request, **kwargs: Any) -> Response:
        conn = self.connection(self.project())
        setup = get_setup(conn.connector_slug)
        if setup is not None:
            setup.disconnect(conn)
        record(
            "connection.removed",
            actor=request.user,  # type: ignore[arg-type]
            organization=request.organization,  # type: ignore[attr-defined]
            target=conn,
            metadata={"connector": conn.connector_slug},
            request=request._request,
        )
        conn.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FirstDataView(_ProjectScoped):
    """What the wizard polls while it says "waiting for first data"."""

    def get(self, request: Request, **kwargs: Any) -> Response:
        conn = self.connection(self.project())
        setup = get_setup(conn.connector_slug)
        first = setup.first_data(conn) if setup else None
        received = first.received_at if first else None
        return Response(
            {
                "state": "received" if received else "waiting",
                "received_at": received.isoformat() if received else None,
                "status": conn.status,
                "last_error": conn.last_error,
                "summary": _details(first.summary) if first and received else [],
            }
        )


class CheckNowView(_ProjectScoped):
    """Run a poll straight away (after fixing a problem the wizard showed)."""

    # Not a credential change: any member may ask for a fresh check.
    permission_classes = [IsAuthenticated, HasOrgRole]
    write_role = Role.MEMBER

    def post(self, request: Request, **kwargs: Any) -> Response:
        conn = self.connection(self.project())
        setup = get_setup(conn.connector_slug)
        if setup is None or not setup.check_now(conn):
            return Response(
                {"detail": "Commandr does not poll this integration; it sends data itself."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_202_ACCEPTED)
