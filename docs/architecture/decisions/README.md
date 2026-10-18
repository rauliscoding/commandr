# Architecture decision records

One decision per file, numbered. Accepted ADRs are never rewritten — a change of
mind is a new ADR that supersedes the old one. Use the `/adr` skill.

| # | Decision | Status |
|---|---|---|
| [0001](0001-stack.md) | Django + React + Postgres + Celery on Hetzner with Docker Compose | Accepted |
| [0002](0002-shared-schema-tenancy-with-rls.md) | Shared-schema multi-tenancy enforced by scoped managers and Postgres RLS | Accepted |
| [0003](0003-session-auth-for-spa.md) | Same-origin session cookies for the SPA, not JWTs in browser storage | Accepted |
| [0004](0004-byo-app-credentials.md) | Social connectors support customer-owned ("BYO") developer apps first | Accepted |
| [0005](0005-pull-and-push-ingestion.md) | Ingestion offers both a signed pull endpoint and a push API | Accepted |
| [0006](0006-metrics-in-postgres.md) | Store metrics in partitioned PostgreSQL until a measured limit says otherwise | Accepted |
| [0007](0007-licence-deferred.md) | Licence: AGPL-3.0, alongside a paid hosted service | Accepted |
