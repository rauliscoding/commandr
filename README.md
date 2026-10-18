# Commandr

**One place for an indie product's health, audience and money.**

Commandr is a multi-tenant SaaS (also installable on your own server) for small
product teams and solo founders. It brings together what is usually spread over
four or five tools:

| Area | What Commandr does |
|---|---|
| **App health** | Uptime, health checks, error alerts, resource trends and business KPIs fed from your own app through a small, published contract |
| **Social** | Connect Instagram, Facebook and TikTok; design, schedule and publish posts; see reach and engagement |
| **Email** | Schedule newsletters and announcements through your own Resend account |
| **Analytics & ads** | Google Analytics 4 and Google Ads / Meta Ads in the same view as your app's own numbers |
| **Money** | A simple ledger that pulls ad spend and revenue automatically, so cost per acquisition is live, not a spreadsheet |
| **Work** | A Kanban board whose cards link to the alerts, posts and campaigns they are about |

The first screen a new user sees is the **integration catalogue**: everything that
can feed Commandr, what each one unlocks, and how long it takes to connect. You
connect one thing, data arrives within minutes, and the dashboard builds itself
from what is connected. See [docs/product/onboarding-and-catalogue.md](docs/product/onboarding-and-catalogue.md).

> **Status:** Phase 0. Accounts, organizations, projects, tenant isolation and
> the integration catalogue work end to end; the integrations themselves arrive in
> Phase 1. Customer #1 is [Pantrini](https://pantrini.app).

## Run it, use it, host it

| You want to | Go to |
|---|---|
| Run it locally and change the code | [docs/development.md](docs/development.md) |
| Host your own instance | [docs/self-hosting.md](docs/self-hosting.md) |
| Not run anything | the hosted version, which funds the project (coming with Phase 1) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Report a vulnerability | [SECURITY.md](SECURITY.md), privately |

Quick start (Docker, Python 3.13+, Node 22+):

```bash
docker compose -f deploy/compose/docker-compose.dev.yml up
```

Then open <http://localhost:5173>, create an account, and you land on the catalogue.

## Stack

Python 3.13 · Django 5.2 LTS · Django REST Framework · Celery + Redis ·
PostgreSQL 17 · React 19 + TypeScript + Vite · Tailwind CSS + Radix primitives ·
Caddy · Docker Compose · Portainer · Hetzner Cloud (EU).

## Documentation

Start at [docs/README.md](docs/README.md). The short version:

| Read | For |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Rules for AI-assisted work in this repo (and a good summary for humans) |
| [SKILLS.md](SKILLS.md) | How to ask an AI assistant for help here, and the conventions it follows |
| [docs/product/requirements.md](docs/product/requirements.md) | What we are building and in what order |
| [docs/architecture/overview.md](docs/architecture/overview.md) | How it fits together |
| [docs/architecture/ingestion-contract.md](docs/architecture/ingestion-contract.md) | How other developers' apps feed Commandr |
| [docs/practices/](docs/practices/) | Design system, security, git, accessibility, testing, privacy |

## Licence

[GNU AGPL-3.0](LICENSE). You may use, self-host, modify and even sell services
built on Commandr. If you offer a modified version as a network service, you must
make your modified source available to its users. Why this licence:
[ADR 0007](docs/architecture/decisions/0007-licence-deferred.md).
