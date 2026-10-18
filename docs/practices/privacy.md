# Privacy and GDPR

Commandr is operated from **Portugal** by a sole trader (trabalhador
independente) and hosted in the EU. The GDPR applies in full, supervised by the
**CNPD** (Comissão Nacional de Proteção de Dados).

> This document is an engineering guide, not legal advice. Have the privacy
> policy, terms and DPA reviewed by a lawyer before taking paying customers.

## Roles

| Data | Commandr is | Notes |
|---|---|---|
| Account data of our users (name, email, billing) | **Controller** | Our privacy policy applies |
| Data customers feed us (their app metrics, their audiences' email addresses, social comments, analytics) | **Processor** | Their instructions; a Data Processing Agreement (Art. 28) is part of the terms |

## Principles in the code

- **Minimisation.** Ingest metrics and events, not personal data. The ingestion
  contract tells developers not to send personal data in event properties, the
  SDK hashes user identifiers by default, and the server rejects obvious personal
  data patterns (emails, phone numbers) in metric attributes.
- **Purpose limitation.** Social and analytics data is used to show the customer
  their own figures — never aggregated across customers, never for training.
- **Retention.** Every data type has a retention period in settings, enforced by a
  nightly task: raw metric points 30 days (plan-dependent), rollups 13 months,
  error events 30 days, audit log 2 years, deleted organizations purged within
  30 days (backups age out within 30 more).
- **Security of processing** (Art. 32) — see [security.md](security.md).
- **Privacy by default.** New features ship with the least data collection that
  works; product analytics on Commandr itself is cookieless and self-hosted
  (no third-party trackers in the app).

## Data subject rights

- **Access / portability:** organization owners export all their data as JSON +
  CSV (async job, emailed link, expires in 7 days).
- **Erasure:** deleting a user or organization removes their data, revokes
  provider tokens, and cancels scheduled posts and emails.
- For data we process on a customer's behalf (their email audiences), requests are
  passed to the customer; tooling lets them delete a contact everywhere in one
  action.

## Sub-processors

Kept in a public list (`/legal/sub-processors`) and changed with 30 days' notice
to customers:

| Sub-processor | Purpose | Location |
|---|---|---|
| Hetzner Online GmbH | Hosting, object storage, backups | Germany / Finland (EU) |
| Resend | Commandr's own transactional email | USA (SCCs / DPF) — check current terms |
| Stripe | Billing | EU entity / USA |
| Cloudflare (if used) | DNS, access to admin tools | Global (DPF) |
| AI model provider (if enabled) | Drafting assistance | Per provider; zero-retention terms preferred |

Customers' own integrations (their Resend, Meta, Google accounts) are **their**
processors, connected at their instruction; we document what we read from each.

## Records and documents to prepare

- [ ] Privacy policy (PT + EN)
- [ ] Terms of service with DPA annex and sub-processor list
- [ ] Record of processing activities (Art. 30) — a simple table is enough
- [ ] Cookie notice: only strictly necessary cookies (session, CSRF) → no consent
      banner needed; revisit if anything else is added
- [ ] Breach procedure: assess, log, notify CNPD within 72h where required,
      notify customers without undue delay
- [ ] Data Protection Impact Assessment if we ever process sensitive categories
      or do large-scale profiling (not planned)

## Platform requirements that touch privacy

- Meta, TikTok and Google require a public privacy policy URL, a data deletion
  instructions URL (Meta) and an accurate description of data use before app
  review. Keep `/legal/privacy` and `/legal/data-deletion` live from day one.
- Google API Services User Data Policy (Limited Use) applies to GA4 and Google
  Ads data: use only to provide the user-facing feature, no transfer, no ads use.
