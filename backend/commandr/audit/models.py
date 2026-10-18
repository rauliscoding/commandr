from typing import Any

from django.conf import settings
from django.db import models

from commandr.core.ids import uuid7


class AuditEvent(models.Model):
    """Append-only record of a security-relevant action.

    Never updated or deleted by the application: `save()` refuses updates, and
    migration 0002 revokes UPDATE and DELETE from the app database role, so even
    a bug cannot rewrite history. Retention is enforced by a separate job running
    as the owner role.

    `organization` is nullable because some events (sign-in, MFA changes) belong
    to a person rather than a tenant; reads always filter by organization or by
    the actor, so it is not under RLS.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.CASCADE, null=True, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} at {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise RuntimeError("Audit events are append-only.")
        super().save(*args, **kwargs)
