# Contributing to Commandr

Thanks for helping. Commandr is small and opinionated; these notes save you a
round trip.

## Before you start

- **Bugs:** open an issue with what you did, what you expected and what happened.
  Never paste real tokens, API keys or customer data, even partly redacted.
- **Features and integrations:** open an issue first to agree the shape. A new
  integration is welcome; the `/add-connector` checklist
  (`.claude/skills/add-connector/SKILL.md`) is what a complete one looks like,
  whether or not you use Claude Code.
- **Security issues:** never in a public issue. See [SECURITY.md](SECURITY.md).

## Setting up

Follow [docs/development.md](docs/development.md). About fifteen minutes from
clone to a running app with green tests.

## Making a change

1. Branch from `main`: `feat/…`, `fix/…`, `docs/…` ([git process](docs/practices/git-process.md)).
2. Read the rules your change touches. The short list is in [CLAUDE.md](CLAUDE.md)
   ("The invariants") and applies to humans too:
   - tenant data is scoped twice (manager + Postgres RLS), with a cross-tenant test;
   - secrets go through the vault and never into logs, responses or task arguments;
   - customer URLs are fetched only through `safe_http`;
   - unknown is shown as unknown, never as 0 or "healthy".
3. Write tests for the happy path **and** the failure paths (401, 403, 404, bad
   input, another tenant's object).
4. Run the checks in [docs/development.md § Checking your change](docs/development.md#checking-your-change-what-ci-runs).
5. Update docs in the same pull request: the affected practice or architecture
   doc, the OpenAPI file if an API changed, `.env.example` if a setting changed,
   an ADR if you made a decision.

## Pull requests

- Title in [Conventional Commits](https://www.conventionalcommits.org/) form:
  `feat(catalogue): filter by requirement`.
- Say what and why, how you tested it, and include screenshots (light and dark)
  for UI changes.
- Keep it small; split large work behind a feature flag.
- UI changes must pass the [accessibility checklist](docs/practices/accessibility.md#component-checklist).

## Licence of contributions

Commandr is licensed under the [GNU AGPL-3.0](LICENSE), and contributions are
accepted under the same licence through the
[Developer Certificate of Origin](https://developercertificate.org/). Sign off
every commit to certify you wrote it, or otherwise have the right to submit it:

```bash
git commit -s -m "fix(catalogue): keep focus on the opener"
```

That adds a `Signed-off-by: Your Name <email>` line. Use the email you are happy
to publish: commits on a public repository are public.

New source files may start with `SPDX-License-Identifier: AGPL-3.0-only`.
Background: [ADR 0007](docs/architecture/decisions/0007-licence-deferred.md).
