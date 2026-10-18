# AGENTS.md

Instructions for any AI coding agent (Claude Code, Codex, Cursor, Copilot…).

The canonical file is **[CLAUDE.md](CLAUDE.md)** — read it in full before making
changes. Everything there applies to every agent, not only Claude. This file
exists so tools that look for `AGENTS.md` find the same rules.

The three rules that matter most:

1. **Never commit, push, pull, rebase or change git config.** Leave changes in the
   working tree for the maintainer to review.
2. **Every query that touches tenant data is scoped to an organization.** See
   [docs/practices/security.md](docs/practices/security.md) § Tenant isolation.
3. **Secrets never enter the repository, logs, error messages or API responses.**
