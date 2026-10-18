"""Test settings.

Tests run against a real PostgreSQL (row-level security is half of tenant
isolation, and SQLite has none), connected as a NON-superuser role: a superuser
bypasses RLS and every isolation test would pass for the wrong reason.
`tests/conftest.py` refuses to run as a superuser.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
os.environ.setdefault(
    "VAULT_KEYS",
    # Two fixed throwaway keys so rotation can be tested. Never used anywhere else.
    "M0pDTXhQdFNqVnBHcG1TNXRGc2tYc1pxbW1YbWlRbE4=,c2tVd3pCdkVqc3FsS3lRZ1dXRlhJb0Rxb1NkV3ZpTnU=",
)
os.environ.setdefault(
    # Port 5433, not 5432, so Commandr never touches another project's local
    # Postgres by accident. deploy/compose/docker-compose.dev.yml publishes it.
    "DATABASE_URL",
    "postgres://commandr_owner:commandr_owner@127.0.0.1:5433/commandr",
)

from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ACCOUNT_EMAIL_VERIFICATION = "optional"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
}
LOGGING = {"version": 1, "disable_existing_loggers": False}
