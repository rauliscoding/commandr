# Product requirements

- **Status:** Draft v1 · 16 Oct 2026
- **Owner:** Raúl Gomes
- **Customer #1:** Pantrini (pantrini.app)

## Vision

Indie founders and small product teams run their product from five tabs: an
uptime monitor, a social scheduler, an email tool, Google Analytics and a
spreadsheet of costs. None of them knows about the others, so nobody can answer
the questions that matter: *Is the app healthy? Did last week's posts bring
signups? What does a paying user cost me?*

**Commandr is one place for a product's health, audience and money**, set up in
minutes by connecting what you already use.

## Who it is for

| Persona | Situation | Main job |
|---|---|---|
| **Solo founder-developer** (Raúl at Pantrini) | Builds and markets alone, little budget, comfortable with APIs | "Tell me when something's wrong, help me post consistently, show me if marketing pays" |
| **Small product team** (2–10) | A developer or two plus someone doing marketing | Shared view of health and growth; a board for who does what |
| **Agency / freelancer** (later) | Runs several small clients' products | Multiple organizations, one login, client-ready reports |

## Positioning

- Not a Datadog: we ingest **health signals and KPIs**, not every log line.
- Not a Hootsuite: we publish to the networks that matter to small consumer
  products, priced for one person.
- The gap: **nobody joins app health + growth + marketing spend** for small teams.
  Closest all-in-one is Metricool (social + analytics + ads, ~€20/month/brand),
  which knows nothing about your app.

## Principles

1. **Catalogue first.** Users start by seeing what they can connect and what each
   unlocks; time to first useful data under 5 minutes.
2. **Bring your own accounts.** Customers connect their own Resend, Meta, TikTok
   and Google accounts; Commandr is the cockpit, not a reseller.
3. **Silence is a signal.** Daily digest whether or not anything is wrong.
4. **Human in the loop.** AI drafts; people approve anything that publishes,
   sends or spends.
5. **SaaS and self-host from one codebase.**

---

## Modules and phases

Phase **0** = foundations · **1** = MVP (Pantrini runs on it) · **2** = sellable
beta · **3** = growth.

### A. App health

| Req | Description | Phase |
|---|---|---|
| A1 | Uptime probe of any HTTPS URL from Commandr's network, with response time and TLS expiry | 1 |
| A2 | Heartbeat URLs for cron/scheduled jobs; alert when a beat is missed | 1 |
| A3 | Status endpoint polling (pull) per the [ingestion contract](../architecture/ingestion-contract.md), signed requests | 1 |
| A4 | Push ingestion API for events, metrics and errors | 1 |
| A5 | `commandr-django` SDK: status endpoint, per-route traffic, error capture, KPI registry, heartbeat helper | 1 |
| A6 | Alert rules (threshold, missing data, rate of change) with cooldown and recovery messages | 1 |
| A7 | Incidents: grouped alerts with timeline, acknowledge, resolve, link to board card | 2 |
| A8 | Daily digest email per project, with three verdicts: healthy / attention / nothing was checked | 1 |
| A9 | Notification channels: email (MVP), then Telegram, Slack, Discord, mobile push | 1 / 3 |
| A10 | OpenTelemetry (OTLP/HTTP) metrics + logs intake | 3 |
| A11 | Node/Express and FastAPI SDKs | 2 / 3 |
| A12 | Public status page per project | 3 |

### B. Business KPIs

| Req | Description | Phase |
|---|---|---|
| B1 | Customer-defined KPIs from status endpoint or push (users, signups, items, subscriptions…) | 1 |
| B2 | KPI tiles with period comparison, sparkline, goal | 1 |
| B3 | Funnel from events (visit → signup → activation → paid) joining GA4 + app events | 2 |
| B4 | Weekly growth report email | 2 |

### C. Social publishing

| Req | Description | Phase |
|---|---|---|
| C1 | Connect Facebook Pages and Instagram Business/Creator accounts (Meta) | 1 |
| C2 | Connect TikTok accounts; upload to TikTok inbox/drafts until our client is audited, then direct post | 1 |
| C3 | Composer: one post, per-network variants, media upload, alt text, character limits and format checks per network | 1 |
| C4 | Calendar (month/week/list) with drag-to-reschedule and keyboard alternative | 1 |
| C5 | Scheduled publishing with retries, failure reasons in plain language, and "needs reauth" handling | 1 |
| C6 | Approval workflow: draft → in review → approved → scheduled (optional per org) | 2 |
| C7 | Media library with tags, reuse, and image resizing per network | 2 |
| C8 | Templates and brand kit (colours, fonts, logo) for designing post images in-app | 2 |
| C9 | AI assist: caption drafts, variants per network, hashtag suggestions — draft only | 2 |
| C10 | Additional networks: LinkedIn, YouTube Shorts, Threads, Bluesky, X | 3 |

### D. Social analytics

| Req | Description | Phase |
|---|---|---|
| D1 | Per-post metrics: reach/views, likes, comments, shares, saves where the API provides them | 1 |
| D2 | Per-account trends: followers, reach, engagement rate | 1 |
| D3 | Best time to post from own history | 2 |
| D4 | Unified inbox for comments and DMs | 3 |

### E. Email

| Req | Description | Phase |
|---|---|---|
| E1 | Connect the customer's **Resend** account (restricted API key) | 1 |
| E2 | Audiences/contacts sync, segments | 1 |
| E3 | Compose (blocks editor producing accessible HTML + plain text), preview, test send | 1 |
| E4 | Schedule broadcasts via Resend (`scheduled_at`), cancel/reschedule | 1 |
| E5 | Delivery, open and click stats via Resend webhooks | 2 |
| E6 | Unsubscribe and consent handling compliant with GDPR/ePrivacy | 1 |
| E7 | Other providers (SES, Postmark, SMTP) | 3 |

### F. Analytics and ads

| Req | Description | Phase |
|---|---|---|
| F1 | GA4 via OAuth: users, sessions, top pages, sources, conversions | 2 |
| F2 | Google Ads: spend, clicks, conversions, CPA (developer token, Basic access) | 2 |
| F3 | Meta Ads: spend and results from the customer's ad account | 2 |
| F4 | Play Console / App Store installs and revenue reports | 3 |

### G. Money

| Req | Description | Phase |
|---|---|---|
| G1 | Ledger of income and expenses with categories, notes, receipts | 1 |
| G2 | Recurring entries (hosting, domains, subscriptions) | 1 |
| G3 | Automatic imports: ad spend (F2, F3), Stripe revenue and fees | 2 |
| G4 | Bank/CSV import with column mapping and duplicate detection | 2 |
| G5 | Unit economics: CAC, ARPU, payback, break-even conversion rate — computed live | 2 |
| G6 | Multi-currency with daily ECB rates; reporting currency per org | 2 |
| G7 | Export for the accountant (CSV per period). **Not** an accounting or invoicing system | 2 |

### H. Board

| Req | Description | Phase |
|---|---|---|
| H1 | Kanban boards per project: columns, cards, labels, assignees, due dates, checklists | 1 |
| H2 | Create a card from an alert, a post, a campaign or an expense; card shows the linked object's live status | 1 |
| H3 | Keyboard-operable drag and drop, comments, @mentions | 2 |
| H4 | Due-date reminders in the digest | 2 |

### I. Platform (SaaS)

| Req | Description | Phase |
|---|---|---|
| I1 | Organizations, projects, roles (owner/admin/member/viewer), invitations | 0 |
| I2 | Sign-in: email+password, Google, MFA (TOTP, passkeys) | 0 |
| I3 | Tenant isolation (scoped managers + Postgres RLS) | 0 |
| I4 | Credential vault with key rotation | 0 |
| I5 | Audit log visible to owners | 0 |
| I6 | Integration catalogue and setup wizard generated from the connector registry | 0 |
| I7 | Billing with Stripe: plans, trials, limits enforced server-side | 2 |
| I8 | Self-hosted edition: same Docker Compose, licence key, BYO-app connectors only | 2 |
| I9 | i18n: English, then Portuguese | 1 / 2 |
| I10 | Data export and deletion (GDPR) | 1 |
| I11 | Command palette (`Ctrl K`), global search | 2 |

---

## Non-functional requirements

| Area | Requirement |
|---|---|
| Time to value | New user connects one source and sees real data in < 5 min |
| Availability | 99.5% monthly for the app; ingestion accepts and queues even when downstream is degraded |
| Freshness | Status polls every 1–5 min (plan); push data visible < 60 s; social metrics hourly; GA/ads daily + on-demand |
| Performance | p95 API < 300 ms for dashboard reads; ingest p95 < 100 ms to accept |
| Scale (year 1) | 500 organizations, 2k projects, 50M metric points/month on one server class |
| Security | OWASP ASVS L2 — see [security.md](../practices/security.md) |
| Accessibility | WCAG 2.2 AA — see [accessibility.md](../practices/accessibility.md) |
| Privacy | GDPR, EU hosting — see [privacy.md](../practices/privacy.md) |
| Cost | Single-founder budget: production runs on one Hetzner server (+ a backup box) until revenue justifies more |

## Platform constraints we design around

| Provider | Constraint | Our approach |
|---|---|---|
| Meta (FB/IG) | Development mode works only for people with a role on the app; other users need Advanced Access via App Review + **Business Verification** | **BYO app** connectors first (customer's own Meta app); apply for our platform app once a verifiable business entity exists (open question for a sole trader — see below) |
| TikTok | Unaudited clients post private only | Inbox/draft upload mode until audited; the UI says so plainly |
| Instagram | Business or Creator account required; per-account publishing cap per 24h | Setup wizard checks account type; composer shows remaining quota |
| Google Ads | Developer token needs Basic access to touch production accounts | Apply early; GA4 needs no special access |
| X | Pay-per-use API (~$0.015/post, ~$0.20 with a link) | Phase 3, opt-in, cost shown per post |

## Open questions

1. **Meta Business Verification as a sole trader in Portugal.** Meta accepts
   business documents; whether an *empresário em nome individual* / atividade
   aberta in Finanças qualifies needs checking. If not, the hosted "one-click
   Meta connect" waits for a company (Unipessoal Lda) — BYO app covers us until then.
2. Pricing and plan limits (proposal in a later doc once MVP costs are measured).
3. Licence for the self-hosted edition — [ADR 0007](../architecture/decisions/0007-licence-deferred.md).
4. Whether the AI drafting provider runs per-customer keys (BYO) or ours.

## Success measures

- Pantrini runs entirely on Commandr (its `apps/ops` emails replaced by Commandr
  alerts and digest) by end of Phase 1.
- Median time to first data < 5 min in beta.
- 20 external beta organizations with ≥ 3 connections each by end of Phase 2.
