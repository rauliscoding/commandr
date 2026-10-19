# 0008. Resolve ingest credentials through a hash-only lookup table, and poll with no database access

- **Status:** Accepted
- **Date:** 2026-10-19

## Context
Two Phase 1 paths start with no tenant:

1. `POST /v1/ingest` and `/v1/heartbeat/<token>` carry only a credential.
   Postgres RLS hides every tenant row until `app.current_org_id` is set
   ([ADR 0002](0002-shared-schema-tenancy-with-rls.md)), so the view cannot find
   the `IngestKey` or `Heartbeat` that would tell it the tenant.
2. Status-endpoint and uptime polls fetch customer-typed URLs. If `safe_http`
   were ever bypassed, the process making the request should not be able to
   reach Postgres (security.md § Outbound HTTP), yet a poll needs the project's
   signing secret, which lives in the database.

## Decision
1. **`ingest_credentiallookup`**: one table that is deliberately not
   tenant-owned and not under RLS, mapping `sha256(credential)` →
   `(kind, organization_id, target_id)`. The view hashes the presented
   credential, finds the organization (cached 60 s, misses included), activates
   that tenant, and loads the real row under RLS. Revocation deletes the
   lookup row and its cache entry. It holds no secret; without the credential a
   row says nothing usable.
2. **The `poller` has no database route.** A default-queue task (DB access)
   decides what is due, decrypts the signing secret, signs the request and
   enqueues only `(url, headers)` on the `egress` queue with a 240 s expiry;
   the signature itself is valid for 300 s. The egress task fetches through
   `safe_http` and hands a plain result to a default-queue task that writes it.

## Consequences
- RLS stays strict everywhere else: no `BYPASSRLS` role, no SECURITY DEFINER
  lookup function that could be called with any input.
- `tests/test_rls.py` checks every `TenantOwned` model; the lookup table is the
  documented exception and must stay hash-only.
- A queue backlog longer than 240 s drops polls instead of sending stale
  signatures; the next scheduled poll replaces them.
- Poll results (≤ 1 MB status documents) travel through the broker.

## Alternatives considered
- **A SECURITY DEFINER function returning the org for a hash** — FORCE RLS
  applies to the owner too, so it would need RLS disabled inside the function;
  harder to review than a table with no secret in it.
- **Organization id embedded in the key** — leaks tenant identifiers in every
  key and still needs a lookup to validate.
- **Poller reads the vault itself** — puts the database on the network the
  SSRF guard is meant to protect.
