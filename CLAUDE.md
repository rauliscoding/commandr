# Commandr — Claude Code reference

Commandr is a multi-tenant SaaS (and self-hostable product) that gives an indie
product team one place for **app health, social media, email, analytics, ads,
money and tasks**. It is open source under AGPL-3.0 (ADR 0007) and also sold
as a hosted service. Customer #1 is Pantrini, whose `apps/ops` module is the
prototype for Commandr's monitoring and Django SDK.

Read [docs/README.md](docs/README.md) for the map. This file holds the rules that
apply to **every** change; the practice docs hold the detail.

---

## Git — hands off

**Do not run `git commit`, `git push`, `git pull`, `git rebase`, `git merge`,
`git stash`, `git reset`, or `git config`** unless the maintainer explicitly asks
for that operation in the current conversation. By default, make changes in the
working tree and leave them for the maintainer to review and commit. Read-only
git (`status`, `diff`, `log`, `blame`, `show`) is always fine.

When asked to commit: sign off (`git commit -s`, the DCO, ADR 0007), use
Conventional Commits, and add **no** `Co-Authored-By` or other AI attribution
trailers.

This repository is **public and personal**:

- The commit identity is set per repository in `.git/config`, never globally.
  Do not read it into, or write it out of, any tracked file.
- Never commit anything from the maintainer's employer, any machine-specific
  path, or any personal contact detail: everything here is public.

Branching, commit messages and review: [docs/practices/git-process.md](docs/practices/git-process.md).

---

## Status

**Phase 0 built** (18 Oct 2026). Working:
- sign-up and sign-in (allauth headless, session cookies, MFA configured);
- organizations, memberships, roles and projects, with tenant isolation enforced
  by scoped managers AND Postgres RLS;
- the credential vault, `safe_http`, audit log, and request IDs with redacted JSON logs;
- the connector registry (16 v1 connectors declared, all "coming soon") and the
  catalogue API + screen;
- the SPA shell, onboarding, and placeholders for every product area;
- dev and prod Docker Compose, and the Caddy edge.

**Phase 1 app-health slice built** (19 Oct 2026):
- `ingest`: write-only ingest keys (SHA-256 + last 4, shown once, revocable,
  last used/IP), `POST /v1/ingest` (JSON-schema validation, partial
  acceptance, Idempotency-Key, per-key rate limits) → Redis stream →
  `drain_ingest`; heartbeat URLs (success/start/fail, hashed tokens). Tenant
  found via the hash-only `ingest_credentiallookup` (ADR 0008).
- `monitoring`: metric series, monthly-partitioned points with per-partition
  RLS, 1m/1h rollups; checks (ok/warn/fail/unknown), alert rules (threshold,
  absence), outbox notifications with cooldown and recovery, daily digest with
  three verdicts; email via Django SMTP (Resend).
- Uptime probe and signed status-endpoint polling on the `egress` queue
  (`poller`, no DB route), through `safe_http`.
- `uptime_probe`, `heartbeat`, `status_endpoint`, `push_api` are available:
  the setup wizard is generic (fields declared in the registry, handlers in
  `connectors/<slug>/setup.py`); connecting needs a recent sign-in. Health page.

**`commandr-django` SDK built** (19 Oct 2026), in `sdks/python/commandr-django/`:
signed status endpoint with database, cache, Celery and disk checks,
`@commandr.check` / `@commandr.kpi` / `@commandr.gauge`, per-route-template
traffic middleware, error logging handler with fingerprints,
`@commandr.heartbeat`, `commandr.event`. Contract-tested against the OpenAPI
file and the server's signing code; tox matrix Django 5.2/6.0/6.1 × Python
3.10–3.14. The `django_sdk` connector is available (ingest key + polled status
endpoint on one connection). Pantrini is not migrated yet.

Not yet: signing-secret rotation, alert-rule UI,
incidents, the `watchdog` process, social, email, finance, board. No CI
workflow yet.

## Commands

```bash
docker compose -f deploy/compose/docker-compose.dev.yml up -d db redis   # Postgres :5433, Redis :6380
cd backend  && ruff check . && ruff format --check . && mypy commandr config && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd sdks/python/commandr-django && ruff check . && mypy src tests && pytest   # tox -p auto: version matrix
```

Full setup: [docs/development.md](docs/development.md). Tests need the dev
Postgres and run as `commandr_owner`; `tests/conftest.py` refuses a superuser.

## Repository layout

```
backend/                 Django project (Python 3.13, Django 5.2 LTS)
  config/                settings/{base,dev,test,prod}.py, urls, celery, asgi/wsgi
  commandr/              Django apps, one per bounded context:
    accounts/            users, auth (django-allauth headless), MFA
    tenancy/             Organization, Membership, Project, roles, scoping
    integrations/        connector registry, credential vault, sync engine
    connectors/          declarations.py (the catalogue); later one sub-package per connector
    ingest/              public ingestion API (/v1/ingest, heartbeats, status polling)
    monitoring/          checks, alert rules, incidents, digest
    social/              posts, media, schedule, publish, engagement metrics
    email/               audiences, campaigns, schedule (via customer's Resend)
    finance/             ledger, categories, imports, unit economics
    boards/              Kanban boards, cards, links to other objects
    audit/               append-only audit log
  tests/                 mirrors commandr/ (pytest)
frontend/                React 19 + TypeScript + Vite SPA
  src/
    app/                 routes, providers, layout shell
    features/<area>/     one folder per product area (catalogue, health, social…)
    components/ui/       design-system primitives (Radix + Tailwind), owned here
    lib/                 api client, query keys, formatting, a11y helpers
    styles/tokens.css    design tokens — the ONLY place raw colours live
sdks/
  python/commandr-django/   the installable agent (status endpoint, traffic, errors, KPIs);
                            its own pyproject, tests and tox matrix
deploy/
  compose/               docker-compose.{dev,prod}.yml, Caddyfile
docs/                    product, architecture (+ ADRs, OpenAPI), practices
.claude/skills/          project skills for Claude Code
```

---

## The invariants

Each of these exists because getting it wrong is silent. Do not "simplify" them.

### 1. Tenant isolation is enforced twice

Every tenant-owned model has a non-null `organization` FK and uses
`TenantScopedManager`; views obtain querysets only through
`request.tenant`-scoped helpers. Postgres **row-level security** is the second
layer: the request sets `app.current_org_id` and RLS policies refuse rows from
any other org. A query that forgets the scope must return **nothing**, never
another customer's data. Background tasks take `organization_id` explicitly and
set the same session variable. Details: [security.md § Tenant isolation](docs/practices/security.md#tenant-isolation).

### 2. Credentials live only in the vault

OAuth tokens, API keys, app secrets and HMAC secrets are stored encrypted
(`integrations.vault`, MultiFernet with rotation) and decrypted only inside the
connector call that needs them. They are never serialised to an API response,
logged, put in a Celery message, or included in an exception. Ingest keys are
stored **hashed** (we show them once).

### 3. Commandr fetches customer-supplied URLs — every fetch goes through `safe_http`

Status-endpoint polling, uptime probes, webhooks and media downloads all hit URLs
a customer typed. All of them must use `commandr.core.safe_http`, which resolves
DNS once, refuses private / loopback / link-local / metadata addresses, pins the
resolved IP, disallows redirects to refused addresses, and caps time and body
size. A raw `requests.get(user_url)` is an SSRF hole into our own network.

### 4. Every rate limit is keyed per tenant

Per ingest key, per user, per organization — never a single global bucket, and
never per-IP alone behind the proxy. One noisy customer must not be able to
throttle every other one. Caddy's `trusted_proxies` and Django's
`X-Forwarded-For` handling must agree.

### 5. Unknown is not zero

A metric that was not reported is `null`, rendered as "—" or "No data", never
`0`. A check that did not run is **unknown**, not **ok**. "Nothing was checked"
is never presented as healthy (lesson carried over from Pantrini's digest).

### 6. Nothing is published on a user's behalf without an explicit human action

AI may draft posts, emails and replies. Scheduling or publishing requires a
person to approve that specific item. There is no "auto-publish AI content"
setting.

### 7. Connectors are declared, not hard-coded into screens

Every integration is a `Connector` registered in `integrations.registry` with
its metadata (category, auth type, capabilities, setup steps, data it unlocks).
The catalogue, the setup wizard and the dashboard read the registry. Adding a
connector must not require editing the catalogue UI. Use the
`/add-connector` skill.

### 8. External calls are bounded and idempotent

Every outbound HTTP call has a connect and read timeout. Every Celery task is
safe to run twice (idempotency key or upsert). Retries use exponential backoff
with jitter and a ceiling. A third-party 4xx that means "revoked" marks the
connection `needs_reauth` and tells the user; it is not retried forever.

---

## Backend conventions

- **Ruff** (lint + format, line length 100), **mypy** on `commandr/` (strict on new
  modules). Type hints on every public function; built-in generics (`list[str]`).
- Google-style docstrings on public classes/functions; comments say **why**, not what.
- DRF: viewsets for resources, explicit `permission_classes` on every view
  (default deny), serializers never expose secret fields, pagination on every list.
- Migrations: one concern per migration; data migrations are reversible or say
  why not; never edit an applied migration. Large tables: create indexes
  `CONCURRENTLY` in a separate migration with `atomic = False`.
- Time: store UTC (`timestamptz`), convert at the edge. Never store a countdown
  ("days left") — derive it at read time.
- Money: `Decimal` + ISO 4217 currency code, never floats. Display in the
  organization's currency.
- Settings come from the environment (`django-environ`); every new variable goes in
  `.env.example` with a comment, in the same change.

## Frontend conventions

- TypeScript strict. No `any` without a comment explaining it.
- Server state with **TanStack Query**; query keys from `lib/queryKeys.ts` only.
- Forms with React Hook Form + Zod; the Zod schema mirrors the API contract.
- Styling with Tailwind utilities that reference **tokens** only. No raw hex
  colours, no arbitrary pixel values in components. See
  [design-system.md](docs/practices/design-system.md).
- Every interactive component is keyboard operable and has an accessible name.
  See [accessibility.md](docs/practices/accessibility.md).

### Typechecking: make sure the command checks files

Vite strips types without checking them, so the build passes regardless. If
`tsconfig.json` is solution-style (`"files": []` + references), `tsc -p
tsconfig.json` compiles **zero files** and always exits 0. Typecheck with the
config that includes `src/` (`tsc --noEmit -p tsconfig.app.json`), redirect output
to a file rather than piping it (a pipe reports the pager's exit code), and
compare error counts before and after your change.

---

## Definition of done

A change is done when:

1. Tests cover the happy path and the main failure paths (401/403/404/422, a
   revoked token, a timeout) — see [testing.md](docs/practices/testing.md).
2. Lint, format, typecheck and tests pass locally.
3. New UI passes the accessibility checklist and an axe scan with zero violations.
4. Security-relevant changes (auth, tenancy, secrets, outbound HTTP, file upload,
   permissions) were checked against [security.md](docs/practices/security.md).
5. Docs updated **in the same change**: the affected practice/architecture doc,
   the OpenAPI file if the API changed, `.env.example` if config changed, and an
   ADR if a decision was made or reversed.
6. Nothing was committed — the maintainer reviews and commits.

## Documentation map

| Topic | File |
|---|---|
| Development setup | [docs/development.md](docs/development.md) |
| Self-hosting | [docs/self-hosting.md](docs/self-hosting.md) |
| Product requirements & phases | [docs/product/requirements.md](docs/product/requirements.md) |
| Catalogue-first onboarding & connector list | [docs/product/onboarding-and-catalogue.md](docs/product/onboarding-and-catalogue.md) |
| Architecture | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Ingestion contract (+ OpenAPI) | [docs/architecture/ingestion-contract.md](docs/architecture/ingestion-contract.md), [openapi/ingest-v1.yaml](docs/architecture/openapi/ingest-v1.yaml) |
| Decisions | [docs/architecture/decisions/](docs/architecture/decisions/) |
| Design system | [docs/practices/design-system.md](docs/practices/design-system.md) |
| Security | [docs/practices/security.md](docs/practices/security.md) |
| Git process | [docs/practices/git-process.md](docs/practices/git-process.md) |
| Accessibility | [docs/practices/accessibility.md](docs/practices/accessibility.md) |
| Testing | [docs/practices/testing.md](docs/practices/testing.md) |
| Privacy & GDPR | [docs/practices/privacy.md](docs/practices/privacy.md) |
