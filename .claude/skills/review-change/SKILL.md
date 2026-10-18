---
name: review-change
description: Review the uncommitted working-tree changes in Commandr against the project's tenancy, security, reliability, accessibility and documentation checklists before the maintainer commits. Use when the user asks to review their changes, check before committing, or "is this ready".
---

# Review the working tree

1. `git status` and `git diff` (staged and unstaged). Read every changed file in
   full where the diff lacks context. Do not run any git command that changes
   state.
2. Check each lens; report only real findings, each with file:line, the concrete
   failure scenario, and the fix.

| Lens | Look for |
|---|---|
| Tenancy | Unscoped querysets; `objects.all()` on a tenant model; tasks without `organization_id`; raw SQL without the org predicate; cross-org foreign keys |
| Secrets | Secret fields in serializers, logs, exceptions, task args, fixtures; new env vars missing from `.env.example` |
| Outbound HTTP | Calls not via `core.http` / `safe_http`; missing timeouts; user URLs fetched directly; redirects followed blindly |
| Authz | Views without explicit permission classes; role checks done only in the UI; object-level permission missing |
| Input | Unvalidated JSON shapes; unbounded lists/strings; file uploads without type/size checks |
| Rate limits | New public endpoint without a per-key/per-user limit |
| Reliability | Non-idempotent tasks; retry without ceiling; `0` written where data is unknown |
| Accessibility | Missing accessible names; div-buttons; colour-only status; focus not managed in dialogs; raw colours instead of tokens |
| Tests | Happy path only; no 403/404 test; no cross-tenant test for a new endpoint |
| Docs | Practice/architecture doc, OpenAPI, ADR not updated for a behaviour change |

3. Finish with: what is ready, what must change before commit, and what could be
   a follow-up. Do not commit.
