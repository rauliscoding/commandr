/** Mirrors `commandr.monitoring.health.snapshot` — keep in step. */

export type CheckStatus = "ok" | "warn" | "fail" | "unknown";
export type VerdictState = "healthy" | "attention" | "nothing_checked";

export interface HealthCheck {
  id: string;
  name: string;
  key: string;
  source: "uptime" | "heartbeat" | "status_endpoint" | "rule";
  status: CheckStatus;
  summary: string;
  value: number | null;
  unit: string;
  last_run_at: string | null;
  changed_at: string | null;
}

export interface HealthHeartbeat {
  id: string;
  name: string;
  period_seconds: number;
  grace_seconds: number;
  status: CheckStatus;
  summary: string;
  last_ping_at: string | null;
  last_fail_at: string | null;
  last_duration_ms: number | null;
  next_due_at: string | null;
}

export interface HealthKpi {
  name: string;
  label: string;
  unit: string;
  /** null = not reported / not available. Rendered "—", never 0. */
  value: number | null;
  as_of: string | null;
}

export interface HealthUptime {
  id: string;
  url: string;
  interval_seconds: number;
  last_run_at: string | null;
  last_status_code: number | null;
  last_response_ms: number | null;
  tls_expires_at: string | null;
  last_error: string;
}

export interface Health {
  generated_at: string;
  verdict: {
    state: VerdictState;
    failing: number;
    warning: number;
    unknown: number;
    ok: number;
    last_checked_at: string | null;
  };
  checks: HealthCheck[];
  heartbeats: HealthHeartbeat[];
  kpis: HealthKpi[];
  uptime: HealthUptime[];
}
