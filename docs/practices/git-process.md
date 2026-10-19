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

`.github/workflows/ci.yml` runs on every pull request and every push to `main`.
A newer push to the same pull request cancels the run in flight. Make each job
below a required status check in the branch protection for `main`.

| Job | Runs |
|---|---|
| **Backend** | Python 3.13 and a `postgres:17` service with the same roles as dev and prod (`deploy/compose/postgres/init/01-roles.sh`); tests connect as the non-superuser `commandr_owner`, so RLS is on. `ruff check`, `ruff format --check`, `mypy commandr config`, `makemigrations --check --dry-run`, `pytest` (which also applies every migration to an empty database) |
| **Frontend** | Node 24. `npm ci`, `npm run lint` (eslint), `npm run typecheck` (`tsc --noEmit -p tsconfig.app.json`), `npm test` (vitest, with axe), `npm run build` |
| **SDK** | Python 3.13, from `sdks/python/commandr-django/` with the whole repository checked out (the contract tests read the OpenAPI file and the server's signing code). `pip install -e ".[dev]"`, `ruff check`, `ruff format --check`, `mypy src tests`, `pytest`, and a check that **SDK &lt;env&gt;** below lists every `tox.ini` environment |
| **SDK &lt;env&gt;** | one job per `tox.ini` environment: Django 5.2 on Python 3.10–3.14, Django 6.0 and 6.1 on 3.12–3.14, each `tox -e <env>` installing the built wheel |
| **Security** | gitleaks over the full history, `pip-audit` on everything the backend installs, `npm audit --omit=dev` |
| **DCO sign-off** | pull requests only: every non-merge commit carries `Signed-off-by:` matching its author. Dependabot's PRs are exempt (a bot cannot certify the DCO) |

How the workflow is kept trustworthy:

- Every action is pinned to a full commit SHA with the version in a comment;
  tags can be moved, SHAs cannot. Release binaries (gitleaks) are
  checksum-verified.
- `permissions: contents: read` for the whole workflow; a job that needs more
  must widen it for itself only. Checkouts do not persist the token.
- Dependabot (`.github/dependabot.yml`) opens one grouped PR a week each for the
  backend's and the SDK's pip dependencies, npm and the action pins. The SDK's
  ranges are widened, not raised: they are what customers' apps resolve against.

Planned, not yet in CI: `pip-audit` on the SDK's dependencies, Playwright smoke
and axe on key routes, migrations reversing cleanly, prettier `--check`, Trivy
image scan, CodeQL, and OpenAPI / ingest-example validation.

Local pre-commit (`pre-commit` framework, `.pre-commit-config.yaml`): ruff lint
and format on `backend/` and `sdks/`, prettier on `frontend/`, gitleaks,
trailing whitespace, end-of-file fixer, large-file guard. Setup: [development.md § Pre-commit hooks](../development.md#pre-commit-hooks).

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
