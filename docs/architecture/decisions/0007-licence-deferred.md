# 0007. Licence: AGPL-3.0, with a paid hosted service

- **Status:** Accepted
- **Date:** 2026-10-16, revised 2026-10-18, accepted 2026-10-18

## Context
The code is public on GitHub, and anyone may self-host it. The maintainer also
runs a paid hosted version for people who would rather not operate it, and that
revenue funds the project. The licence has to allow both, and must stop a third
party from taking the code, closing it, and selling a competing hosted service
without giving anything back.

Comparable open-source products sold as hosted services mostly use AGPL-3.0:
Plausible, Postiz, Listmonk, Keila and Cal.com.

## Decision
- The repository is licensed **AGPL-3.0-only** (`LICENSE`, verbatim from gnu.org).
- Contributions are accepted under the **Developer Certificate of Origin**: each
  commit carries a `Signed-off-by:` line (`git commit -s`). Contributors keep
  their copyright, and their contributions are AGPL-3.0 like the rest.
- New source files may carry `SPDX-License-Identifier: AGPL-3.0-only` as their
  first comment. Existing files are covered by `LICENSE` and are not mass-edited.

## What this means for the hosted service
- The maintainer may charge for a hosted Commandr. AGPL allows anyone, including
  the maintainer, to sell hosting or services built on the code.
- The obligation the AGPL adds is **source availability**: users of a network
  service running a modified Commandr must be able to get that modified source.
  The hosted service therefore runs code that is published in this repository,
  and links to it (an "Open source" link in the app footer and on the pricing page).
- What is sold is the **operation**: hosting, uptime, backups, upgrades, the
  approved platform apps for Meta, TikTok and Google (ADR 0004), and support.
  It is not exclusive code.
- Third parties can sell hosting too, but must publish their changes under AGPL.
  That is the protection this decision exists for.

## Consequences
- AGPL code from other projects (Postiz, Listmonk…) may now be reused, with
  attribution and only when the licences are compatible. SSPL and other
  non-OSI licences remain excluded (security.md § Supply chain).
- Some companies forbid AGPL software internally. That limits enterprise
  self-hosting, not the hosted service.
- **No proprietary relicensing.** With DCO and no CLA, code contributed by
  others cannot later be sold under a closed licence. If dual licensing (selling
  non-AGPL licences to companies) ever becomes a plan, it needs a CLA from that
  point on and a rewrite or permission for earlier contributions. Decide before
  external contributions grow.

## Alternatives considered
| Licence | Why not |
|---|---|
| MIT / Apache-2.0 | Anyone could sell a closed fork as a competing service. |
| FSL-1.1 / BUSL-1.1 | Strongest protection, but not open source by OSI's definition, which the project wants to be. |
| Open core (AGPL + proprietary `ee/`) | A second licence and a code boundary, with no paid-only features to justify them yet. Revisit if needed. |
| AGPL + CLA | Keeps the dual-licensing option open, but deters contributors. Not needed today. |
