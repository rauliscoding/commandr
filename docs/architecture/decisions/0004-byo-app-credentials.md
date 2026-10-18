# 0004. Social connectors support customer-owned ("BYO") developer apps first

- **Status:** Accepted
- **Date:** 2026-10-16

## Context
Publishing to other people's Instagram/Facebook accounts through *our* Meta app
needs Advanced Access (App Review + Business Verification); TikTok public posting
needs an audit. Commandr is run by a sole trader with no registered company yet,
so verification may not be possible soon. Paid unified social APIs (Ayrshare from
~$149/month) are not affordable. Meta's development mode lets anyone with a role on
an app use it for their own accounts at no cost.

## Decision
Every social/ads connector has two modes sharing one code path:

- **BYO app** — the customer creates their own developer app, pastes App ID and
  Secret (stored in the vault), and connects their accounts through it.
- **Platform app** — Commandr's own approved app, enabled per provider once
  approved, then the default on the hosted service.

The self-hosted edition only ever uses BYO.

## Consequences
- Zero cost and zero approval dependency for launch; Pantrini works immediately.
- Setup is slower for customers (~15 min the first time), mitigated by a validated
  step-by-step wizard and docs. Acceptable for a developer audience.
- Each customer's app is subject to Meta/TikTok rules in its own name.
- TikTok in BYO mode before audit: upload-to-drafts, clearly labelled.

## Alternatives considered
- **Unified API (Ayrshare, bundle.social)** — fastest, but a monthly cost we cannot
  carry, and a dependency at the heart of the product.
- **Wait for platform approval** — blocks the product on paperwork.
