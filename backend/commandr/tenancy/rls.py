"""Migration operation that puts a tenant table under row-level security.

Every migration that creates a `TenantOwned` table must add
`EnableRowLevelSecurity("<model>")` after the `CreateModel`.
`tests/test_rls.py::test_every_tenant_table_has_rls` fails if one is missing.
"""

from typing import Any

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import ProjectState

POLICY_NAME = "tenant_isolation"
CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


class EnableRowLevelSecurity(migrations.operations.base.Operation):
    reversible = True
    reduces_to_sql = True

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        pass

    def _table(self, app_label: str, state: ProjectState, editor: BaseDatabaseSchemaEditor) -> str:
        model = state.apps.get_model(app_label, self.model_name)
        return editor.quote_name(model._meta.db_table)

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, to_state, schema_editor)
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE: the table owner is subject to the policy too.
        schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            f"USING (organization_id = {CURRENT_ORG}) "
            f"WITH CHECK (organization_id = {CURRENT_ORG})"
        )

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, from_state, schema_editor)
        schema_editor.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    def describe(self) -> str:
        return f"Enable row-level security on {self.model_name}"

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__qualname__, [self.model_name], {})
