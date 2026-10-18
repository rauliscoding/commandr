# 0002. Shared-schema multi-tenancy enforced by scoped managers and Postgres RLS

- **Status:** Accepted
- **Date:** 2026-10-16

## Context
Commandr is SaaS from day one and stores customers' credentials and data. A
cross-tenant leak is the worst failure this product can have. Hundreds of small
tenants are expected, most with modest data.

## Decision
One database, one schema. Every tenant table carries `organization_id`.
Isolation is enforced twice:

1. **Application:** `TenantOwned` base model with a scoped default manager; the
   unscoped manager is explicitly named `all_tenants`.
2. **Database:** `ENABLE` + `FORCE ROW LEVEL SECURITY` with a policy on
   `current_setting('app.current_org_id')`, set per request / per task with
   `SET LOCAL`. The app's DB role does not own the tables and lacks `BYPASSRLS`.

## Consequences
- A forgotten filter returns nothing instead of another customer's rows.
- Every migration creating a tenant table must add the policy (a test checks all
  tenant tables have RLS enabled).
- Admin/support tooling must set the org context deliberately — useful friction.
- Connection pooling must use transaction-scoped settings (`SET LOCAL`), never
  session-level `SET`.

## Alternatives considered
- **Schema per tenant (django-tenants)** — strong isolation, but migrations scale
  with tenant count and cross-tenant operations (billing, platform metrics) get
  awkward.
- **Database per tenant** — too much operational cost for one person.
- **Application filtering only** — one bug away from a breach.
