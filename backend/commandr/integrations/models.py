from typing import Any

from django.conf import settings
from django.db import models

from commandr.core.ids import uuid7
from commandr.tenancy.models import Project, TenantOwned

from . import vault


class ConnectionMode(models.TextChoices):
    PLATFORM = "platform", "Commandr's app"
    BYO_APP = "byo_app", "Your own app"  # ADR 0004
    KEY = "key", "API key"
    NONE = "none", "No credentials"


class ConnectionStatus(models.TextChoices):
    PENDING = "pending", "Setting up"
    CONNECTED = "connected", "Connected"
    NEEDS_REAUTH = "needs_reauth", "Needs reconnecting"
    ERROR = "error", "Error"
    DISABLED = "disabled", "Disabled"


class Connection(TenantOwned):
    """One project's link to one connector.

    Secrets live only in the two `*_encrypted` columns, sealed by the vault. No
    serializer may expose them (tests/test_serializers_hide_secrets.py).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="connections")
    connector_slug = models.CharField(max_length=64)
    mode = models.CharField(max_length=16, choices=ConnectionMode.choices)
    status = models.CharField(
        max_length=16, choices=ConnectionStatus.choices, default=ConnectionStatus.PENDING
    )
    label = models.CharField(max_length=120, blank=True)
    config = models.JSONField(default=dict, blank=True)  # non-secret settings only
    scopes = models.JSONField(default=list, blank=True)
    credentials_encrypted = models.BinaryField(null=True, editable=False)
    app_credentials_encrypted = models.BinaryField(null=True, editable=False)  # BYO app
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)  # sanitised, user-facing
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwned.Meta):
        indexes = [models.Index(fields=["project", "connector_slug"])]

    def __str__(self) -> str:
        return f"{self.connector_slug} for {self.project_id}"

    def set_credentials(self, data: dict[str, Any]) -> None:
        self.credentials_encrypted = vault.seal(data)

    def get_credentials(self) -> dict[str, Any] | None:
        if self.credentials_encrypted is None:
            return None
        return vault.unseal(self.credentials_encrypted)

    def set_app_credentials(self, data: dict[str, Any]) -> None:
        self.app_credentials_encrypted = vault.seal(data)

    def get_app_credentials(self) -> dict[str, Any] | None:
        if self.app_credentials_encrypted is None:
            return None
        return vault.unseal(self.app_credentials_encrypted)
