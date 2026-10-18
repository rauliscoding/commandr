# SKILLS.md — working with an AI assistant on Commandr

How Claude Code (or any assistant) can help most effectively here, what it will
check without being asked, and how to phrase a request so the result is right the
first time. Rules live in [CLAUDE.md](CLAUDE.md); this file is about
**collaboration**.

---

## Project skills (`.claude/skills/`)

Invoke with `/<name>` in Claude Code.

| Skill | Use it to |
|---|---|
| `/add-connector` | Add an integration end to end: registry entry, vault usage, sync task, catalogue card, setup wizard, tests, docs |
| `/adr` | Record an architecture decision in `docs/architecture/decisions/` |
| `/review-change` | Review the working-tree diff against the security, tenancy, accessibility and docs checklists before you commit |

Built-in skills worth using: `/code-review` for bugs, `/security-review` for the
pending changes, `/simplify` for clean-up passes.

---

## What the assistant can do here

### Build

- Django apps, models, migrations (including safe data migrations and
  `CONCURRENTLY` indexes), DRF viewsets, serializers, permissions.
- Connectors to third-party APIs with OAuth 2.0 + PKCE, token refresh, revocation
  handling and quota-aware syncing.
- Celery tasks that are idempotent, bounded and observable.
- React features: routes, TanStack Query hooks, forms with Zod, design-system
  components on Radix primitives.
- The `commandr-django` SDK and its tests against a throwaway Django project.
- Docker Compose, Caddy, GitHub Actions.

### Review (always applied, unasked)

| Lens | What is checked |
|---|---|
| **Tenancy** | Every query scoped to an organization; RLS session variable set in tasks; no cross-tenant joins |
| **Security** | Authz on every view, secrets never serialised/logged, SSRF via `safe_http`, input validation, rate limits keyed per tenant, OWASP ASVS L2 items |
| **Reliability** | Timeouts on outbound calls, idempotent tasks, retries with backoff and a ceiling, revoked-token handling |
| **Accessibility** | Keyboard path, focus, names/roles, contrast via tokens, non-colour status cues |
| **Data truth** | `null` vs `0`, unknown vs ok, UTC storage, `Decimal` money |
| **Docs** | The affected docs, OpenAPI and `.env.example` updated in the same change |

### Write

- ADRs, contract docs, OpenAPI, runbooks, user-facing help copy.
- Copy follows the voice in [design-system.md § Voice](docs/practices/design-system.md#voice-and-copy).

---

## How to ask

### Add a feature

Give the assistant:

1. **Who** does it (role: owner / admin / member / viewer) and **where** (screen).
2. **What** they get, and what they see when there is no data yet.
3. **Rules** — limits, permissions, edge cases.
4. **Done when** — the observable outcome.

> "Members can create a Kanban card from a failing check. From the incident
> panel, 'Create card' opens a dialog pre-filled with the check name and a link
> back to the incident. Viewers do not see the button. Done when the card appears
> on the project's default board and the incident shows a link to it."

### Add a connector

> "/add-connector Resend — API key auth, read audiences and broadcasts, schedule
> broadcasts. Unlocks: email campaigns. Setup: paste a restricted key."

### Investigate a bug

Paste the error, say where it happened (environment, organization if relevant —
never a customer's secret), and what you expected. The assistant will reproduce it
in a test before fixing it.

### Ask for a review

> "Review my working tree for tenancy and SSRF issues."

---

## What the assistant will not do

- Commit, push, pull, rebase, or change git configuration, unless you ask for it
  explicitly in the conversation. Commits it makes are signed off and carry no
  AI co-author trailer.
- Paste real customer data or credentials into tests, fixtures or docs.
- Add a dependency without saying why, what it costs (size, licence, maintenance)
  and what the alternative was. Dependencies must be AGPL-3.0-compatible
  ([ADR 0007](docs/architecture/decisions/0007-licence-deferred.md)).
- Turn off a check, a test or a lint rule to make something pass.

---

## Prompting tips

- Name the file or feature folder when you know it — it saves a search.
- Say "plan first" for anything crossing more than one app; the assistant will
  propose before editing.
- If a rule in CLAUDE.md is wrong, say so and ask the assistant to update the rule
  in the same change — do not just override it for one task.
