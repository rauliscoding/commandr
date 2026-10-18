from typing import Any, TypeVar

from django.conf import settings
from django.db import models

from commandr.core.ids import uuid7

from .context import TenantContextError, current_org_id


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"
    VIEWER = "viewer", "Viewer"


ROLE_RANK: dict[str, int] = {Role.VIEWER: 1, Role.MEMBER: 2, Role.ADMIN: 3, Role.OWNER: 4}


class Organization(models.Model):
    """The tenant and the billing unit.

    Not itself under RLS: a user must be able to list the organizations they
    belong to before any tenant is active. Every query on it goes through the
    user's memberships (see `tenancy.views`).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    currency = models.CharField(max_length=3, default="EUR", help_text="ISO 4217")
    timezone = models.CharField(max_length=64, default="UTC")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    """A user's role in one organization. Only ever queried with the user's id."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="uniq_membership"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.organization_id} as {self.role}"

    def has_role(self, minimum: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


_M = TypeVar("_M", bound=models.Model)


class TenantScopedManager(models.Manager[_M]):
    """Default manager for tenant data: filtered to the active tenant, or empty.

    The unscoped manager is `all_tenants`, so every bypass is greppable. Even
    that one is still filtered by Postgres RLS.
    """

    def get_queryset(self) -> models.QuerySet[_M]:
        qs = super().get_queryset()
        org_id = current_org_id()
        if org_id is None:
            return qs.none()
        return qs.filter(organization_id=org_id)


class TenantOwned(models.Model):
    """Base for every tenant-owned model. Its migration must enable RLS."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="+", editable=False
    )

    objects = TenantScopedManager()
    # Declared after `objects` so `objects` stays the default manager (ruff misreads
    # this second manager as a field).
    all_tenants = models.Manager()  # noqa: DJ012

    class Meta:
        abstract = True
        base_manager_name = "all_tenants"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Rows are written for the active tenant only — never across tenants."""
        active = current_org_id()
        if active is None:
            raise TenantContextError(f"Cannot save {type(self).__name__} with no tenant active.")
        if self.organization_id is None:
            self.organization_id = active
        elif self.organization_id != active:
            raise TenantContextError(
                f"Refusing to save {type(self).__name__} for another organization."
            )
        super().save(*args, **kwargs)


class ProjectKind(models.TextChoices):
    WEB_APP = "web_app", "Web app"
    MOBILE_APP = "mobile_app", "Mobile app"
    API = "api", "API"
    SHOP = "shop", "Shop"


class Project(TenantOwned):
    """One product (e.g. Pantrini). Integrations, metrics and boards hang off it."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=120)
    url = models.URLField(blank=True)
    kind = models.CharField(max_length=16, choices=ProjectKind.choices, default=ProjectKind.WEB_APP)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uniq_project_name"),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.name
