# 0005. Ingestion offers both a signed pull endpoint and a push API

- **Status:** Accepted
- **Date:** 2026-10-16

## Context
Customers' apps must feed Commandr health and business data with minimal effort.
State ("disk is 86% full", "412 users") and events ("a signup happened", "an
exception was raised") have different natural shapes. Some apps sit behind
networks we cannot reach.

## Decision
Offer four entry points with one storage path: uptime probes, heartbeat URLs, a
**signed status endpoint the customer exposes and we poll** (HMAC-SHA256 with a
timestamp), and a **push API** with write-only ingest keys. SDKs combine pull and
push. OTLP/HTTP intake is added later for teams already on OpenTelemetry.

## Consequences
- Pull gives liveness for free and needs only a shared secret on the customer's
  side; push covers events and unreachable networks.
- Polling customer URLs makes SSRF our problem: every fetch goes through
  `safe_http` from an isolated `poller` container.
- Two code paths to maintain in each SDK.

## Alternatives considered
- **Push only** — the app's silence would be ambiguous (down, or just quiet?).
- **OTLP only** — the standard, but heavyweight for a small Django app and says
  nothing about business KPIs.
- **Prometheus scrape format** — familiar to some, but no checks/KPI semantics and
  no signing convention.
