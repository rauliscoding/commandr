# Development setup

Everything you need to run Commandr on your machine, change it, and check your
change the way CI will. Tested on Windows 11, macOS and Linux.

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker Desktop (or Docker Engine + Compose v2) | recent | Postgres and Redis, and the full stack if you prefer containers |
| Python | **3.13+** (3.14 works) | the backend |
| Node.js | **22+** (24 recommended) | the frontend |
| Git | any | |

## 1. Clone and start the services

```bash
git clone https://github.com/rauliscoding/commandr.git
cd commandr
docker compose -f deploy/compose/docker-compose.dev.yml up -d db redis
```

The dev Postgres listens on **127.0.0.1:5433** and Redis on **127.0.0.1:6380**, not
the default ports, so Commandr never collides with another project's database on
your machine. On first start Postgres creates the two roles Commandr uses
(`deploy/compose/postgres/init/01-roles.sh`):

| Role | Used for | Can |
|---|---|---|
| `commandr_owner` | migrations, and the test suite | own and alter tables; **not** a superuser |
| `commandr_app` | the running app | read and write rows; cannot alter tables, cannot bypass row-level security |

That split is what makes tenant isolation real — see
[ADR 0002](architecture/decisions/0002-shared-schema-tenancy-with-rls.md).

## 2. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

Run the tests (they create and destroy their own `test_commandr` database):

```bash
pytest
```

Run the API against the dev database. Migrations run as the **owner**, the server
as the **app** role, exactly as in production:

```bash
# macOS / Linux
export DJANGO_SECRET_KEY=dev VAULT_KEYS=M0pDTXhQdFNqVnBHcG1TNXRGc2tYc1pxbW1YbWlRbE4=
DATABASE_URL=postgres://commandr_owner:commandr_owner@127.0.0.1:5433/commandr python manage.py migrate
DATABASE_URL=postgres://commandr_app:commandr_app@127.0.0.1:5433/commandr \
  REDIS_URL=redis://127.0.0.1:6380/0 python manage.py runserver
```

```powershell
# Windows PowerShell
$env:DJANGO_SECRET_KEY="dev"; $env:VAULT_KEYS="M0pDTXhQdFNqVnBHcG1TNXRGc2tYc1pxbW1YbWlRbE4="
$env:DATABASE_URL="postgres://commandr_owner:commandr_owner@127.0.0.1:5433/commandr"; python manage.py migrate
$env:DATABASE_URL="postgres://commandr_app:commandr_app@127.0.0.1:5433/commandr"; $env:REDIS_URL="redis://127.0.0.1:6380/0"; python manage.py runserver
```

Use `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and
Docker publishes on IPv4, which makes connections hang.

The vault key above is a **public development key** — never use it anywhere real.

## 3. Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api`, `/accounts`, `/healthz` and
`/admin` to the backend on port 8000, so the SPA and the API share an origin as
they do in production (session cookies, [ADR 0003](architecture/decisions/0003-session-auth-for-spa.md)).

Sign up, create an organization and a product, and you land on the integration
catalogue. In development, email verification is optional and emails print to
the backend's console.

### App health locally (ingest, drainer, poller, beat)

The Phase 1 health features need four more processes. With the same
environment variables as `runserver` above (app role, Redis on 6380):

```bash
# The ingestion API on :8001 (heartbeat URLs and /v1/ingest)
DJANGO_ROOT_URLCONF=config.urls_ingest python manage.py runserver 127.0.0.1:8001
# Writes push batches from the Redis stream to Postgres
python manage.py drain_ingest
# Fetches status endpoints and uptime probes (the `egress` queue), and schedules them
celery -A config worker -Q default,egress -l info
celery -A config beat -l info
```

Set `INGEST_ORIGIN=http://127.0.0.1:8001` so the setup wizard shows working
heartbeat URLs. `python manage.py drain_ingest --once` drains what is queued and
exits, which is handy when testing a single `curl`.

Uptime probes and status endpoints refuse private and loopback addresses
(that is the SSRF guard working), so a status endpoint served from your own
machine cannot be polled. Point them at something public, or test the
document shape with the unit tests instead.

### The Django SDK (`sdks/python/commandr-django/`)

The SDK has its own environment. It needs no database: its tests use SQLite
and a fake ingest server.

```bash
cd sdks/python/commandr-django
python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy src tests && pytest
tox -p auto   # Django 5.2 / 6.0 / 6.1 on every supported Python found
```

To try it against a local Commandr, set `"INGEST_URL": "http://127.0.0.1:8001"`
in the throwaway project's `COMMANDR`. Traffic and errors arrive through the
drainer; polling a local status endpoint is refused, as described above.

## Or: everything in containers

```bash
docker compose -f deploy/compose/docker-compose.dev.yml up
```

Starts Postgres, Redis, migrations (as owner), the API (as app) on :8000, the
ingestion API on :8001, a Celery worker, the poller, beat, the ingest drainer
and Vite. Code is bind-mounted, so edits reload.

## Pre-commit hooks

Once per clone, from the repository root (with the backend virtualenv active, or
any Python):

```bash
pip install pre-commit
pre-commit install
```

Every `git commit` then runs, on the staged files only: ruff (lint with fixes,
and format) on `backend/` and `sdks/`, prettier on `frontend/`, gitleaks,
trailing-whitespace and end-of-file fixers, and a 500 KB large-file guard
(`.pre-commit-config.yaml`). A hook that fixes a file stops the commit; review
the fix, `git add` it and commit again. `pre-commit run --all-files` checks the
whole tree.

The first run downloads each hook's tooling (gitleaks builds with Go, which
pre-commit fetches itself); later runs take a second or two.

## Checking your change (what CI runs)

```bash
# backend/
ruff check . && ruff format --check . && mypy commandr config
python manage.py makemigrations --check --dry-run --settings=config.settings.test
pytest

# frontend/
npm run lint && npm run typecheck && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs these on every pull request and push to
`main`, against a fresh `postgres:17` with the same roles as the dev database,
plus the SDK's checks above and its tox matrix (one job per environment), a
security job (gitleaks over the full history, `pip-audit`,
`npm audit --omit=dev`) and, on pull requests, a check that every commit is
signed off by its author (`git commit -s`).

`npm run typecheck` uses `tsconfig.app.json`. **Never typecheck with
`tsc -p tsconfig.json`**: that file is solution-style and compiles zero files,
so it always "passes".

## Adding things

| To add | Read first |
|---|---|
| An integration | the `/add-connector` skill, `.claude/skills/add-connector/SKILL.md` |
| A tenant-owned model | [security.md § Tenant isolation](practices/security.md#tenant-isolation) — inherit `TenantOwned`, add `EnableRowLevelSecurity` to the migration |
| A setting | add it to `.env.example` in the same change |
| A UI component | [design-system.md § Adding a component](practices/design-system.md#adding-a-component) |
| A decision | the `/adr` skill |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tests exit with "must connect as a non-superuser" | `DATABASE_URL` points at a superuser | use `commandr_owner`; RLS does not apply to superusers, so the isolation tests would pass for the wrong reason |
| Connection hangs | `localhost` on Windows | use `127.0.0.1` |
| `permission denied for table …` running the server | migrations ran as `commandr_app` | run `migrate` with the owner URL |
| Port 5433 or 6380 in use | another stack | change the left side of `ports:` in the dev compose file |
| CI's "DCO sign-off" job fails | a commit has no `Signed-off-by` matching its author | `git rebase --signoff main` on your branch, then force-push it |
| Roles missing after changing the init script | it only runs on an empty data volume | `docker compose -f deploy/compose/docker-compose.dev.yml down -v` (deletes dev data) |
