from typing import Any

from django.db import transaction

from commandr.accounts.models import User
from commandr.audit.services import record

from .context import tenant_context
from .models import Membership, Organization, Project, Role


@transaction.atomic
def create_organization(*, owner: User, data: dict[str, Any]) -> tuple[Organization, Project]:
    org = Organization.objects.create(
        name=data["name"].strip(),
        country=data.get("country", ""),
        currency=data.get("currency", "EUR"),
        timezone=data.get("timezone", "UTC"),
    )
    Membership.objects.create(organization=org, user=owner, role=Role.OWNER)
    with tenant_context(org.id):
        project = Project.objects.create(
            name=data["project_name"].strip(),
            url=data.get("project_url", ""),
            kind=data.get("project_kind", "web_app"),
            created_by=owner,
        )
    record("organization.created", actor=owner, organization=org, target=org)
    record("project.created", actor=owner, organization=org, target=project)
    return org, project
