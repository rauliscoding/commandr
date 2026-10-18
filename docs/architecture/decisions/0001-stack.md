# 0001. Django, React, Postgres and Celery on Hetzner with Docker Compose

- **Status:** Accepted
- **Date:** 2026-10-16

## Context
One person builds and operates Commandr, on a near-zero budget, and already runs
Pantrini on Django 4.2 / Celery / Redis / Postgres / Caddy / Portainer on Hetzner.
The product is CRUD-heavy with background jobs (syncs, publishing, polling) and a
rich dashboard UI.

## Decision
- Backend: Python 3.13, **Django 5.2 LTS** (security support to April 2028),
  Django REST Framework, Celery 5 with Redis, PostgreSQL 17.
- Frontend: React 19 + TypeScript + Vite SPA, Tailwind + Radix primitives,
  TanStack Query.
- Runtime: Docker Compose, Caddy, Portainer, Hetzner Cloud (EU). Images built in
  CI and published to GHCR.
- A modular monolith: one image, several process types.

## Consequences
- Maximum reuse of the maintainer's skills and of Pantrini's proven ops patterns.
- Celery adds operational weight but is already understood; Temporal (as Postiz
  uses) is rejected for its footprint.
- Pantrini itself should move off Django 4.2, whose LTS ended in April 2026.

## Alternatives considered
- **Node/NestJS backend** — fine, but splits the maintainer's attention and loses
  Django admin, ORM migrations and allauth.
- **Next.js full-stack** — server components add complexity a dashboard SPA does
  not need; still two runtimes alongside a Python SDK.
- **Kubernetes** — unjustified for one server.
