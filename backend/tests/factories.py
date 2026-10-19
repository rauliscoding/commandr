from typing import Any

import factory
from factory.django import DjangoModelFactory

from commandr.accounts.models import User
from commandr.integrations.models import Connection, ConnectionMode, ConnectionStatus
from commandr.tenancy.context import tenant_context
from commandr.tenancy.models import Membership, Organization, Project, Role

TEST_PASSWORD = "correct horse battery staple"


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"person{n}@example.test")
    password = factory.django.Password(TEST_PASSWORD)


class OrganizationFactory(DjangoModelFactory[Organization]):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Organization {n}")


class MembershipFactory(DjangoModelFactory[Membership]):
    class Meta:
        model = Membership

    organization = factory.SubFactory(OrganizationFactory)
    user = factory.SubFactory(UserFactory)
    role = Role.MEMBER


class _TenantFactory(DjangoModelFactory[Any]):
    """Tenant rows can only be written with their tenant active (RLS + save())."""

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class: type, *args: Any, **kwargs: Any) -> Any:
        org = kwargs["organization"]
        with tenant_context(org.id):
            return super()._create(model_class, *args, **kwargs)


class ProjectFactory(_TenantFactory):
    class Meta:
        model = Project

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Project {n}")
    kind = "web_app"


class ConnectionFactory(_TenantFactory):
    class Meta:
        model = Connection

    project = factory.SubFactory(ProjectFactory)
    organization = factory.LazyAttribute(lambda o: o.project.organization)
    connector_slug = "uptime_probe"
    mode = ConnectionMode.NONE
    status = ConnectionStatus.CONNECTED


def setup_connection(project: Project, user: User, slug: str, **fields: Any) -> Any:
    """Run a connector's real setup handler, as the connections API does."""
    from commandr.integrations.setup import get_setup

    setup = get_setup(slug)
    assert setup is not None
    with tenant_context(project.organization_id):
        data = setup.validate(fields, project)
        return setup.create(project=project, user=user, data=data)
