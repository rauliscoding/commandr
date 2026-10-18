"""Make the audit log append-only at the database level.

The app connects as the `commandr_app` role (deploy/compose/postgres/init). It
keeps INSERT and SELECT on the audit table and loses UPDATE and DELETE, so not
even a bug in the application can rewrite history. Skipped when the role does
not exist (e.g. a self-hosted install that chose one database role), which is
documented in docs/self-hosting.md.
"""

from django.db import migrations

APP_ROLE = "commandr_app"

FORWARD = f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditevent FROM {APP_ROLE};
  END IF;
END $$;
"""

BACKWARD = f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
    GRANT UPDATE, DELETE ON audit_auditevent TO {APP_ROLE};
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
