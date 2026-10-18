import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from commandr.integrations import vault
from commandr.tenancy.context import tenant_context
from tests.factories import ConnectionFactory

SECRET = {"access_token": "EAAG-very-secret-token", "refresh_token": "r1"}


def test_seal_roundtrip_and_ciphertext_hides_plaintext() -> None:
    token = vault.seal(SECRET)
    assert b"very-secret" not in token
    assert vault.unseal(token) == SECRET


def test_rotation_reencrypts_with_newest_key_and_old_key_can_be_dropped() -> None:
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    with override_settings(VAULT_KEYS=[old_key]):
        sealed_old = vault.seal(SECRET)
    with override_settings(VAULT_KEYS=[new_key, old_key]):
        assert vault.unseal(sealed_old) == SECRET  # old data still opens
        rotated = vault.rotate(sealed_old)
    with override_settings(VAULT_KEYS=[new_key]):
        assert vault.unseal(rotated) == SECRET  # survives removing the old key
        with pytest.raises(vault.VaultError):
            vault.unseal(sealed_old)


def test_vault_error_never_carries_the_ciphertext_or_plaintext() -> None:
    with pytest.raises(vault.VaultError) as excinfo:
        vault.unseal(b"not-a-token")
    assert "not-a-token" not in str(excinfo.value)


@pytest.mark.django_db
def test_connection_stores_only_ciphertext(project_a) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(project_a.organization_id):
        conn = ConnectionFactory(project=project_a)
        conn.set_credentials(SECRET)
        conn.save()
        conn.refresh_from_db()
        assert b"very-secret" not in bytes(conn.credentials_encrypted)
        assert conn.get_credentials() == SECRET
