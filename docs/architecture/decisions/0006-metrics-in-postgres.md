# 0006. Store metrics in partitioned PostgreSQL until a measured limit says otherwise

- **Status:** Accepted
- **Date:** 2026-10-16

## Context
Commandr ingests health metrics and KPIs, not full observability data. Year-one
estimate: ~50M points/month across all tenants. RLS and tenant isolation already
live in Postgres.

## Decision
Use native PostgreSQL declarative partitioning (monthly) for raw points, with 1m
and 1h rollup tables maintained by workers. Dashboards read rollups; retention
drops partitions. Cardinality is capped per plan.

## Consequences
- One database to run, back up and secure; RLS covers metrics too.
- Heavy analytical queries are bounded by rollups and caps.
- Must watch table bloat, partition creation (a scheduled task creates the next
  months ahead) and query plans as volume grows.

## Alternatives considered
- **TimescaleDB** — good fit and a likely next step; deferred to keep the stack
  vanilla and licensing simple.
- **ClickHouse** — excellent at scale, but a second database to operate; premature.
- **Prometheus / VictoriaMetrics** — not multi-tenant with our RLS model, no KPI
  semantics.
