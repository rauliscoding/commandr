"""Credentials customer apps use to send data in: ingest keys, heartbeat tokens,
and the per-project signing secret Commandr uses to sign its status polls.

Ingest keys and heartbeat tokens are stored only as SHA-256 hashes and shown
once (security.md § Ingest keys). The signing secret must be readable to sign
requests, so it is sealed by the vault instead.
"""

from django.conf import settings
from django.db import models

from commandr.core.ids import uuid7
from commandr.integrations import vault
from commandr.integrations.models import Connection
from commandr.tenancy.models import Organization, Project, TenantOwned


class KeyEnvironment(models.TextChoices):
    LIVE = "live", "Live"
    TEST = "test", "Test"


class IngestKey(TenantOwned):
    """A write-only key: it can submit data for one project and nothing else."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ingest_keys")
    connection = models.OneToOneField(
        Connection, on_delete=models.CASCADE, related_name="ingest_key"
    )
    name = models.CharField(max_length=120)
    environment = models.CharField(
        max_length=8, choices=KeyEnvironment.choices, default=KeyEnvironment.LIVE
    )
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    last4 = models.CharField(max_length=4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta(TenantOwned.Meta):
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.name} (…{self.last4})"


class Heartbeat(TenantOwned):
    """A scheduled job that calls its URL after each run.

    Missed = no successful ping within `period_seconds + grace_seconds` of the
    last one. A heartbeat that has never pinged is *waiting*, which the checks
    show as unknown, never as ok.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="heartbeats")
    connection = models.OneToOneField(
        Connection, on_delete=models.CASCADE, related_name="heartbeat"
    )
    name = models.CharField(max_length=120)
    period_seconds = models.PositiveIntegerField()
    grace_seconds = models.PositiveIntegerField()
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    last_ping_at = models.DateTimeField(null=True, blank=True)  # last success
    last_start_at = models.DateTimeField(null=True, blank=True)
    last_fail_at = models.DateTimeField(null=True, blank=True)
    last_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    last_message = models.CharField(max_length=1000, blank=True)  # redacted
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PingKind(models.TextChoices):
    SUCCESS = "success", "Success"
    START = "start", "Start"
    FAIL = "fail", "Fail"


class HeartbeatPing(TenantOwned):
    """One call to a heartbeat URL. No IP address is kept: we do not need it."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    heartbeat = models.ForeignKey(Heartbeat, on_delete=models.CASCADE, related_name="pings")
    kind = models.CharField(max_length=8, choices=PingKind.choices)
    ts = models.DateTimeField()
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    message = models.CharField(max_length=1000, blank=True)

    class Meta(TenantOwned.Meta):
        indexes = [models.Index(fields=["heartbeat", "-ts"])]

    def __str__(self) -> str:
        return f"{self.kind} at {self.ts:%Y-%m-%d %H:%M}"


class SigningSecret(TenantOwned):
    """The project's secret for signing status-endpoint polls (HMAC-SHA256).

    One per project, as the ingestion contract says: the customer's app holds
    the same value. Vault-sealed because we need the plaintext to sign.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="signing")
    secret_encrypted = models.BinaryField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"signing secret for {self.project_id}"

    def set_secret(self, secret: str) -> None:
        self.secret_encrypted = vault.seal({"secret": secret})

    def get_secret(self) -> str:
        return str(vault.unseal(self.secret_encrypted)["secret"])


class CredentialKind(models.TextChoices):
    INGEST_KEY = "ingest_key", "Ingest key"
    HEARTBEAT = "heartbeat", "Heartbeat token"


class CredentialLookup(models.Model):
    """Hash → tenant, for credentials presented with no tenant active.

    Deliberately NOT tenant-owned and not under RLS (ADR 0008): a request to
    `/v1/ingest` or a heartbeat URL carries only its credential, and RLS hides
    every row until a tenant is set. This table maps the credential's SHA-256
    to the organization, so the view can activate that tenant and load the
    real `IngestKey` / `Heartbeat` under RLS. It holds no secret: without the
    credential itself, a row says nothing usable. Revoking deletes the row.
    """

    digest = models.CharField(max_length=64, primary_key=True)
    kind = models.CharField(max_length=16, choices=CredentialKind.choices)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    target_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.kind} {self.target_id}"
