#!/bin/sh
# Runs once, when the Postgres data directory is first created.
#
# Two roles, because row-level security only protects you from a role that is
# subject to it (ADR 0002):
#   commandr_owner  owns the schema and tables; runs migrations. Not a superuser.
#   commandr_app    what the running app connects as. Can read and write rows,
#                   cannot alter tables, cannot bypass RLS, cannot touch the
#                   audit log beyond INSERT/SELECT (audit migration 0002).
# The `postgres` superuser is used only here and for maintenance.
set -eu

: "${COMMANDR_OWNER_PASSWORD:?set COMMANDR_OWNER_PASSWORD}"
: "${COMMANDR_APP_PASSWORD:?set COMMANDR_APP_PASSWORD}"

psql -v ON_ERROR_STOP=1 \
     -v owner_pw="$COMMANDR_OWNER_PASSWORD" \
     -v app_pw="$COMMANDR_APP_PASSWORD" \
     -v db="$POSTGRES_DB" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE commandr_owner LOGIN CREATEDB PASSWORD :'owner_pw';
CREATE ROLE commandr_app LOGIN PASSWORD :'app_pw';

ALTER DATABASE :"db" OWNER TO commandr_owner;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO commandr_app;

ALTER SCHEMA public OWNER TO commandr_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO commandr_app;

-- Everything the owner creates from now on is usable (not alterable) by the app.
ALTER DEFAULT PRIVILEGES FOR ROLE commandr_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO commandr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE commandr_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO commandr_app;
EOSQL
