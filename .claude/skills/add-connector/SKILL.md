---
name: add-connector
description: Add a new Commandr integration (connector) end to end - registry entry, credential vault, auth flow, sync task, catalogue card, setup wizard, tests and docs. Use when the user asks to add, integrate or connect a third-party service or data source.
---

# Add a connector

A connector is how Commandr talks to one outside system. The catalogue, setup
wizard and dashboards are all generated from the registry, so a connector is
complete only when every step below is done. Read
`docs/architecture/overview.md` § Connector framework first.

## 0. Gather (ask if not given)

- **Service** and the exact API(s) and version.
- **Category**: `app_health` · `analytics` · `social` · `email` · `ads` · `finance` · `work`.
- **Auth type**: `oauth2_platform` (our app) · `oauth2_byo_app` (customer's own app
  credentials) · `api_key` · `ingest_key` · `none`.
- **Capabilities**: which of `read_metrics`, `read_content`, `publish`, `schedule`,
  `read_spend`, `read_revenue`, `webhook`.
- **What it unlocks** for the user, in one sentence of plain language.
- **Cost / approval**: does the provider charge, rate-limit or require app review?
  Record it in the catalogue entry's `requirements`.

## 1. Registry entry

`backend/commandr/connectors/<slug>/connector.py`: subclass `Connector`, fill the
metadata, register it. The slug is lowercase, stable forever (it is stored on
rows).

## 2. Credentials

- Store everything secret through `integrations.vault`. Never on the model as
  plaintext, never in a Celery argument, never logged.
- OAuth: authorization code + PKCE, `state` bound to user + org + nonce (single
  use, 10 min TTL). Request the minimum scopes; verify granted scopes after the
  exchange — users can untick them.
- Map the provider's "revoked/expired grant" error to `ConnectionStatus.NEEDS_REAUTH`.

## 3. Outbound calls

- Only through the connector's client built on `commandr.core.http` (timeouts,
  retries with backoff + jitter, ceiling). Customer-supplied URLs go through
  `safe_http`.
- Respect provider quotas: per-connection concurrency limit, cache what is
  immutable, and record the quota response headers if the provider sends them.

## 4. Sync

- A Celery task per sync kind, taking `connection_id` (and setting the tenant
  context from it). Idempotent: upsert by provider id + time bucket.
- Store metrics with `null` for "not reported", never `0`.
- Record `last_synced_at`, `last_error` (sanitised) on the connection.

## 5. UI

- Catalogue card comes from metadata — check it renders (logo, category, unlocks,
  requirements, estimated setup time).
- Setup wizard steps declared in metadata; any step needing provider-side work
  (e.g. "create a Meta app") links to our docs page for it.
- A **first-data** state: after connecting, show the first values arriving, or a
  clear "waiting for first sync" with what happens next.

## 6. Tests

- Unit: response parsing with recorded fixtures (scrub tokens and personal data).
- Auth: state mismatch refused, missing scope refused, revoked → `needs_reauth`.
- Tenancy: a connection from org A is invisible to org B (API + task).
- Use `responses`/`respx` — no live network in tests.

## 7. Docs

- `docs/product/onboarding-and-catalogue.md` connector table.
- `.env.example` if a platform-level credential is needed.
- A user help page under `docs/connectors/<slug>.md` with setup steps and what
  data is read.
- ADR if you chose something non-obvious (e.g. BYO app only).

## Done when

The connector appears in the catalogue, can be connected and disconnected,
produces data within one sync, survives a revoked token gracefully, and passes
the tenancy test. Do not commit.
