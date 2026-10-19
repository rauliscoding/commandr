# Commandr documentation

Getting started: [development.md](development.md) (run and change it) ·
[self-hosting.md](self-hosting.md) (operate your own instance).

| Folder | What's there | Authority |
|---|---|---|
| [product/](product/) | What we build and for whom: [requirements](product/requirements.md), [onboarding and the integration catalogue](product/onboarding-and-catalogue.md) | What the product should do |
| [architecture/](architecture/) | How it is built: [overview](architecture/overview.md), [ingestion contract](architecture/ingestion-contract.md) + [OpenAPI](architecture/openapi/ingest-v1.yaml), [decisions (ADRs)](architecture/decisions/) | How and why |
| [practices/](practices/) | How we work: [design system](practices/design-system.md), [security](practices/security.md), [git process](practices/git-process.md), [accessibility](practices/accessibility.md), [testing](practices/testing.md), [privacy](practices/privacy.md) | Rules every change follows |
| [connectors/](connectors/) | User-facing setup guide per integration: [uptime probe](connectors/uptime-probe.md), [heartbeat](connectors/heartbeat.md), [status endpoint](connectors/status-endpoint.md), [push API](connectors/push-api.md) | Help content |
| `runbooks/` *(to come)* | Operating production: deploy, restore, rotate keys, incident steps | Operations |

## Keeping docs true

- Code and configuration win over docs for **current behaviour**; when they
  disagree, fix the doc in the same change.
- ADRs win for **why**. Never infer rationale from code when an ADR exists.
- Mark proposals as proposals. A doc describing something not yet built says so
  at the top (`Status: Draft` / `Proposed`).
- Dates are absolute (`16 Oct 2026`), never "last week".
