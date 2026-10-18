"""Re-encrypt every stored credential with the newest vault key.

Rotation: prepend a new key to VAULT_KEYS and deploy, run this, then remove the
old key and deploy again. Runs tenant by tenant: there is no cross-tenant
query, so this goes through the same RLS as everything else.
"""

from typing import Any

from django.core.management.base import BaseCommand

from commandr.integrations import vault
from commandr.integrations.models import Connection
from commandr.tenancy.context import tenant_context
from commandr.tenancy.models import Organization


class Command(BaseCommand):
    help = "Re-encrypt all stored credentials with the newest VAULT_KEYS entry."

    def handle(self, *args: Any, **options: Any) -> None:
        total = 0
        for org_id in Organization.objects.values_list("id", flat=True).iterator():
            with tenant_context(org_id):
                for conn in Connection.objects.select_for_update().iterator():
                    if conn.credentials_encrypted is not None:
                        conn.credentials_encrypted = vault.rotate(conn.credentials_encrypted)
                    if conn.app_credentials_encrypted is not None:
                        conn.app_credentials_encrypted = vault.rotate(
                            conn.app_credentials_encrypted
                        )
                    conn.save(update_fields=["credentials_encrypted", "app_credentials_encrypted"])
                    total += 1
        self.stdout.write(self.style.SUCCESS(f"Rotated credentials on {total} connection(s)."))
