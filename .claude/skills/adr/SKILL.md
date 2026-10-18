---
name: adr
description: Record an architecture decision record (ADR) in docs/architecture/decisions/. Use when a technical or product decision is made, reversed, or needs writing down, or when the user says "write an ADR" or "record this decision".
---

# Write an ADR

1. List `docs/architecture/decisions/` and take the next 4-digit number.
2. File name: `NNNN-short-kebab-title.md`.
3. Use this template, kept to one screen where possible:

```markdown
# NNNN. Title in sentence case

- **Status:** Proposed | Accepted | Superseded by NNNN | Deprecated
- **Date:** YYYY-MM-DD

## Context
What forces are at play. Facts, constraints, numbers. Link sources.

## Decision
What we will do, stated plainly.

## Consequences
What becomes easier, what becomes harder, what we must now watch.

## Alternatives considered
Each with the reason it lost.
```

4. Never rewrite an **Accepted** ADR's decision. To change it, write a new ADR and
   set the old one's status to `Superseded by NNNN` (the only edit allowed).
5. Add the ADR to the index in `docs/architecture/decisions/README.md`.
6. If the decision changes a rule in `CLAUDE.md` or a practice doc, update that
   file in the same change.
