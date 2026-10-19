# Testing

Tests exist to let us change code without fear and to prove the invariants in
[CLAUDE.md](../../CLAUDE.md) hold. Coverage percentage is a signal, not a goal;
the goal is that every rule we care about has a test that fails when it breaks.

## The pyramid

| Layer | Tool | Scope | Speed |
|---|---|---|---|
| Unit | pytest / Vitest | Pure functions: parsers, rollups, signature checks, money maths, formatters | ms |
| Integration (backend) | pytest + pytest-django + real Postgres (RLS on) + fakeredis/real Redis | API endpoints, permissions, tenancy, tasks, migrations | s |
| Contract | JSON Schema / OpenAPI validation | Ingest payloads, status documents, SDK output | ms |
| Component | Vitest + Testing Library | React components and hooks, queried by role/name | ms |
| End to end | Playwright | A few critical journeys in a real browser against a seeded stack | min |

## Backend rules

- **Postgres, not SQLite.** RLS, `timestamptz`, partial indexes and JSONB behave
  differently; tests run against Postgres 17 in Docker locally and as a CI service.
- Fixtures with **factory_boy**; no inline `objects.create` chains. Factories
  create a fresh organization per test unless the test is about sharing.
- Every endpoint test covers: success, unauthenticated (401), wrong role (403),
  other tenant's object (404), invalid input (400/422).
- **Cross-tenant test** for every new tenant model and endpoint — and one test
  that runs a raw unscoped query with the RLS session variable set to org B and
  asserts org A's rows are invisible.
- A test walks the URLconf and fails if any view lacks explicit
  `permission_classes`.
- A test fails if any serializer exposes a field ending `_encrypted`, `_secret`,
  `token` or `key_hash`.
- External APIs are mocked at the HTTP layer (`responses` / `respx`) with
  **recorded, scrubbed** fixtures. No live network in the test suite; a separate,
  manually-run `pytest -m live` suite checks real sandbox accounts.
- Celery tasks run eagerly in tests; each task also has an idempotency test (run it
  twice, assert one effect).
- Time is frozen with `time-machine` wherever behaviour depends on it.
- Migrations: CI applies all migrations to an empty database and runs
  `makemigrations --check`. Data migrations get a test.

## Frontend rules

- Query by role and accessible name; `getByTestId` only as a last resort.
- Mock the network with **MSW**, using handlers generated from (or checked
  against) the OpenAPI types.
- Every feature folder tests its empty state, loading state, error state and one
  happy path.
- Playwright journeys (smoke, run on every PR):
  1. Sign up → create organization → land on the integration catalogue.
  2. Connect a heartbeat → send a ping → see it on the health page.
  3. Create, schedule and cancel a post (social connector mocked).
  4. Kanban: create a card, move it with the keyboard.
- Playwright also runs axe on each journey's screens in light and dark themes.

## SDK (`commandr-django`)

- Tested against a matrix of supported Django and Python versions in a throwaway
  project: `tox -p auto` in `sdks/python/commandr-django/` runs Django 5.2 on
  Python 3.10–3.14 and Django 6.0 and 6.1 on 3.12–3.14, each installing the
  built wheel and running the tests against `tests/testproject`.
- Its status document and every pushed batch are validated against the
  contract schemas in `docs/architecture/openapi/ingest-v1.yaml`, and its tests
  sign polls with the server's own `backend/commandr/monitoring/signing.py`, so
  the SDK and the server can never disagree silently. (The backend's contract
  test keeps `ingest/schemas.py` equal to the same file.)
- Sending is tested against a local fake ingest server: retries keep the
  Idempotency-Key, a hanging server never blocks the app, buffers stay bounded.

## What "green" means

Lint, types, unit, integration, contract, component and the e2e smoke all pass;
axe reports zero violations. A flaky test is a bug: quarantine it with an issue
link within a day, never just re-run until green.
