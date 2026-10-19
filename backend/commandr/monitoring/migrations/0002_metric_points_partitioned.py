"""Raw metric points: a table partitioned by month (ADR 0006).

Django cannot create a partitioned table, so the table is created in SQL and
the model state is declared alongside it (`SeparateDatabaseAndState`).

Partitions are created by `monitoring_ensure_point_partitions()`, a SECURITY
DEFINER function owned by the migration (owner) role: the app role has no
CREATE privilege on the schema, by design. Each partition gets its own RLS
policy, so querying a partition directly is filtered exactly like the parent.
"""

import django.db.models.deletion
import django.db.models.manager
from django.db import migrations, models

from commandr.tenancy.rls import CURRENT_ORG

CREATE_TABLE = """
CREATE TABLE monitoring_metricpoint (
    organization_id uuid NOT NULL
        REFERENCES tenancy_organization (id) DEFERRABLE INITIALLY DEFERRED,
    series_id uuid NOT NULL
        REFERENCES monitoring_metricseries (id) DEFERRABLE INITIALLY DEFERRED,
    ts timestamptz NOT NULL,
    value double precision NOT NULL,
    PRIMARY KEY (series_id, ts)
) PARTITION BY RANGE (ts);
CREATE INDEX monitoring_metricpoint_ts_brin ON monitoring_metricpoint USING brin (ts);
CREATE INDEX monitoring_metricpoint_org ON monitoring_metricpoint (organization_id);
ALTER TABLE monitoring_metricpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_metricpoint FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON monitoring_metricpoint
    USING (organization_id = {current_org})
    WITH CHECK (organization_id = {current_org});
""".format(current_org=CURRENT_ORG)

# Month arithmetic is done on UTC wall-clock timestamps, then converted, so the
# result never depends on the calling session's TimeZone.
ENSURE_FUNCTION = """
CREATE FUNCTION monitoring_ensure_point_partitions(months_back integer, months_ahead integer)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    i integer;
    month_utc timestamp;
    part text;
    created integer := 0;
BEGIN
    IF months_back NOT BETWEEN 0 AND 24 OR months_ahead NOT BETWEEN 0 AND 24 THEN
        RAISE EXCEPTION 'months_back and months_ahead must be between 0 and 24';
    END IF;
    -- One creator at a time: two beats racing would otherwise both try.
    PERFORM pg_advisory_xact_lock(hashtext('monitoring_metricpoint_partitions'));
    FOR i IN -months_back..months_ahead LOOP
        month_utc := date_trunc('month', now() AT TIME ZONE 'UTC') + make_interval(months => i);
        part := 'monitoring_metricpoint_p' || to_char(month_utc, 'YYYYMM');
        IF to_regclass(part) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF monitoring_metricpoint FOR VALUES FROM (%L) TO (%L)',
                part, month_utc AT TIME ZONE 'UTC',
                (month_utc + interval '1 month') AT TIME ZONE 'UTC');
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', part);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', part);
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I USING (organization_id = {current_org}) '
                'WITH CHECK (organization_id = {current_org})', part);
            created := created + 1;
        END IF;
    END LOOP;
    RETURN created;
END;
$fn$;
""".replace("{current_org}", CURRENT_ORG.replace("'", "''"))

DROP_FUNCTION = """
CREATE FUNCTION monitoring_drop_point_partitions(older_than timestamptz)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    child record;
    dropped integer := 0;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('monitoring_metricpoint_partitions'));
    FOR child IN
        SELECT c.relname
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = 'monitoring_metricpoint'::regclass
          AND c.relname ~ '^monitoring_metricpoint_p[0-9]{6}$'
    LOOP
        -- A partition goes only when ALL of its month is older than the cut-off.
        IF (to_date(substring(child.relname from '[0-9]{6}$'), 'YYYYMM')::timestamp
            + interval '1 month') AT TIME ZONE 'UTC' <= older_than THEN
            EXECUTE format('DROP TABLE %I', child.relname);
            dropped := dropped + 1;
        END IF;
    END LOOP;
    RETURN dropped;
END;
$fn$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0001_initial"),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(CREATE_TABLE, "DROP TABLE monitoring_metricpoint"),
                migrations.RunSQL(
                    ENSURE_FUNCTION,
                    "DROP FUNCTION monitoring_ensure_point_partitions(integer, integer)",
                ),
                migrations.RunSQL(
                    DROP_FUNCTION, "DROP FUNCTION monitoring_drop_point_partitions(timestamptz)"
                ),
                # Last month (late points), this month and two ahead. The beat
                # task `maintain_partitions` keeps three months ahead from now on.
                migrations.RunSQL(
                    "SELECT monitoring_ensure_point_partitions(1, 2)", migrations.RunSQL.noop
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='MetricPoint',
                    fields=[
                        ('pk', models.CompositePrimaryKey('series_id', 'ts', blank=True, editable=False, primary_key=True, serialize=False)),
                        ('ts', models.DateTimeField()),
                        ('value', models.FloatField()),
                        ('organization', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='tenancy.organization')),
                        ('series', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='monitoring.metricseries')),
                    ],
                    options={
                        'abstract': False,
                        'base_manager_name': 'all_tenants',
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('all_tenants', django.db.models.manager.Manager()),
                    ],
                ),
            ],
        ),
    ]
