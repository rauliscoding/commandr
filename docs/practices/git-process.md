# Git process

Trunk-based development with short-lived branches, reviewed pull requests and
automated checks. Simple enough for one person, ready for a team.

## Identity — this is a personal repository

Configured per repository, never globally:

```bash
git config --local user.name "Your Name"
git config --local user.email "ID+username@users.noreply.github.com"
```

The repository is public, so every commit's email is public too. Use your
GitHub **noreply** address (Settings > Emails > "Keep my email addresses
private") rather than a personal inbox.

Remote uses the personal SSH host alias from `~/.ssh/config`:

```bash
git remote add origin git@github.com-personal:rauliscoding/commandr.git
```

Before the first push of any session, check `git config user.email` prints the
address you intend to publish. Signed commits (SSH signing with the personal key) are
recommended: `git config --local gpg.format ssh` +
`git config --local user.signingkey ~/.ssh/id_personal.pub` +
`git config --local commit.gpgsign true`.

> **AI assistants commit, push or pull only when the maintainer explicitly asks**
> in the conversation; `.claude/settings.json` makes Claude Code ask before each
> one, and denies rebase, merge, reset and config outright. Their commits are
> signed off (DCO) and carry **no** AI co-author trailer.

## Branches

| Branch | Purpose | Lifetime |
|---|---|---|
| `main` | Always releasable. Protected: no direct pushes, PR + green CI required, linear history | Permanent |
| `feat/<short-desc>` | New capability | ≤ 3 days ideally |
| `fix/<short-desc>` | Bug fix | Hours |
| `chore/…`, `docs/…`, `refactor/…` | Everything else | Short |
| `hotfix/<desc>` | Urgent production fix, branched from the deployed tag | Hours |

Big features land in small PRs behind a **feature flag** rather than on a long
branch. Rebase your branch on `main` before opening the PR (locally — never
rebase shared history).

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <imperative summary, ≤ 72 chars>

<why this change, what was wrong before, anything surprising>

Refs: #123
```

Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`,
`security`. Scope is the app or area: `ingest`, `social`, `catalogue`, `vault`…
Breaking changes: `feat(ingest)!:` plus a `BREAKING CHANGE:` footer.

One logical change per commit. The body explains **why**; the diff shows what.

## Pull requests

- Title in Conventional Commit form (it becomes the squash commit).
- Description: what and why, screenshots for UI (light + dark), how it was tested,
  the security checklist from [security.md](security.md#review-checklist-copy-into-pr-descriptions)
  when relevant, and doc/ADR links.
- Small: aim for under ~400 changed lines excluding generated files and tests.
- **Squash merge** into `main`; delete the branch.
- Solo phase: self-review the diff in GitHub after a break, run `/review-change`,
  and let CI be the second reviewer. With a team: one approving review required,
  CODEOWNERS for `ingest/`, `integrations/vault`, `tenancy/` and `deploy/`.

## Automated checks (CI, required on `main`)

| Check | Tooling |
|---|---|
| Lint & format | ruff, eslint, prettier |
| Types | mypy, `tsc --noEmit -p tsconfig.app.json` |
| Tests | pytest (with Postgres service, RLS on), vitest, Playwright smoke |
| Accessibility | axe via Playwright on key routes |
| Migrations | `makemigrations --check`, migrations apply on an empty DB |
| Security | gitleaks, pip-audit, npm audit, Trivy image scan, CodeQL |
| Contract | OpenAPI file validates; ingest schema examples validate |

Local pre-commit (`pre-commit` framework): ruff, prettier, eslint on staged files,
gitleaks, trailing whitespace, large-file guard.

## Releases and deploys

- **Semantic versioning**, tags `vMAJOR.MINOR.PATCH` on `main`; changelog
  generated from Conventional Commits (release-please or git-cliff).
- CI builds images on tag, pushes to GHCR (`ghcr.io/rauliscoding/commandr-*`),
  tagged with the version and the commit SHA.
- Environments: `local` → `staging` (auto-deploy from `main`) → `production`
  (deploy a **tag**, manually approved). Staging and production run the **same
  image**; only configuration differs.
- Deploy via Portainer stack webhook or a CI job over the private tunnel;
  migrations run as a one-off job **before** the new app containers start, and
  must be backwards compatible with the previous release (expand → migrate →
  contract) so a rollback is always possible.
- Rollback = redeploy the previous tag. Never "fix forward" under pressure without
  a rollback option.

## Housekeeping

- `.gitignore` covers secrets and build output; check `git status` before every
  commit for anything unexpected.
- Never commit generated files except lockfiles and the OpenAPI spec.
- If a secret is ever committed: **rotate it first**, then remove it from history.
  Removing it without rotating protects nothing.
