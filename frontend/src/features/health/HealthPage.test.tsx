import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ConnectionInfo } from "@/features/catalogue/types";
import { axeViolations, mockFetch, renderAt, reply } from "@/test/utils";

import { HealthPage } from "./HealthPage";
import type { Health } from "./types";

const ORG = "11111111-1111-7111-8111-111111111111";
const PROJECT = "22222222-2222-7222-8222-222222222222";
const BASE = `/api/orgs/${ORG}/projects/${PROJECT}`;
const recent = new Date(Date.now() - 3 * 60_000).toISOString();

const empty: Health = {
  generated_at: recent,
  verdict: {
    state: "nothing_checked",
    failing: 0,
    warning: 0,
    unknown: 0,
    ok: 0,
    last_checked_at: null,
  },
  checks: [],
  heartbeats: [],
  kpis: [],
  uptime: [],
};

const health: Health = {
  generated_at: recent,
  verdict: {
    state: "attention",
    failing: 1,
    warning: 0,
    unknown: 1,
    ok: 1,
    last_checked_at: recent,
  },
  checks: [
    {
      id: "c1",
      name: "Nightly backup",
      key: "heartbeat",
      source: "heartbeat",
      status: "fail",
      summary: "Last ping 26 h ago; expected every day.",
      value: null,
      unit: "",
      last_run_at: recent,
      changed_at: recent,
    },
    {
      id: "c2",
      name: "PostgreSQL",
      key: "database",
      source: "status_endpoint",
      status: "ok",
      summary: "reachable",
      value: null,
      unit: "",
      last_run_at: recent,
      changed_at: recent,
    },
    {
      id: "c3",
      name: "Queue backed up",
      key: "rule",
      source: "rule",
      status: "unknown",
      summary: "",
      value: null,
      unit: "",
      last_run_at: null,
      changed_at: null,
    },
  ],
  heartbeats: [
    {
      id: "h1",
      name: "Nightly backup",
      period_seconds: 86400,
      grace_seconds: 3600,
      status: "fail",
      summary: "Last ping 26 h ago; expected every day.",
      last_ping_at: recent,
      last_fail_at: null,
      last_duration_ms: 42_000,
      next_due_at: recent,
    },
  ],
  kpis: [
    { name: "user.total", label: "Users", unit: "count", value: 412, as_of: recent },
    { name: "revenue.mrr", label: "MRR", unit: "EUR", value: null, as_of: recent },
  ],
  uptime: [
    {
      id: "u1",
      url: "https://pantrini.app/healthz/",
      interval_seconds: 300,
      last_run_at: recent,
      last_status_code: 200,
      last_response_ms: 120,
      tls_expires_at: new Date(Date.now() + 40 * 86_400_000 + 3_600_000).toISOString(),
      last_error: "",
    },
  ],
};

const source: ConnectionInfo = {
  id: "s1",
  connector: "push_api",
  connector_name: "Push API",
  label: "Production",
  status: "connected",
  created_at: recent,
  first_data_at: recent,
  last_synced_at: recent,
  last_error: "",
  details: [
    { label: "Key", value: "cmdr_ingest_live_…abcd", kind: "code" },
    { label: "Last used", value: recent, kind: "time" },
    { label: "Last used from", value: "203.0.113.9", kind: "text" },
  ],
};

function render(routes: Record<string, unknown>) {
  const spy = mockFetch(routes);
  renderAt(<HealthPage />, {
    path: "/o/:orgId/p/:projectId/health",
    url: `/o/${ORG}/p/${PROJECT}/health`,
  });
  return spy;
}

describe("HealthPage", () => {
  it("shows a loading state", () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));
    renderAt(<HealthPage />, {
      path: "/o/:orgId/p/:projectId/health",
      url: `/o/${ORG}/p/${PROJECT}/health`,
    });
    expect(screen.getByText("Loading…")).toHaveAttribute("aria-busy", "true");
  });

  it("points to the catalogue when nothing is connected", async () => {
    render({ [`${BASE}/health/`]: empty, [`${BASE}/connections/`]: { results: [] } });
    expect(await screen.findByRole("link", { name: "Go to integrations" })).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });

  it("says when it cannot load", async () => {
    render({ [`${BASE}/health/`]: reply(500, {}), [`${BASE}/connections/`]: { results: [] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("could not load");
  });

  it("lists checks, jobs, numbers and sources, with unknown shown as unknown", async () => {
    render({ [`${BASE}/health/`]: health, [`${BASE}/connections/`]: { results: [source] } });
    expect(await screen.findByText("Needs attention")).toBeInTheDocument();
    expect(
      screen.getByText(/1 passing · 1 failing · 0 warning · 1 not reporting/),
    ).toBeInTheDocument();

    const checks = screen.getByRole("table", { name: "Checks" });
    const rows = within(checks).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[1]!.textContent)).toEqual([
      "Failing",
      "OK",
      "Unknown",
    ]);
    // A rule that never ran says so: "—", not "ok" or "0".
    expect(within(rows[2]!).getAllByText("—")).toHaveLength(2);

    const jobs = screen.getByRole("table", { name: "Scheduled jobs" });
    expect(within(jobs).getByText("every day")).toBeInTheDocument();
    expect(within(jobs).getByText("42 s")).toBeInTheDocument();

    const numbers = screen.getByRole("region", { name: "Numbers" });
    expect(within(numbers).getByText("412")).toBeInTheDocument();
    expect(within(numbers).getByText("—")).toBeInTheDocument();
    expect(within(numbers).getByText(/Not available/)).toBeInTheDocument();
    expect(within(numbers).queryByText("0")).not.toBeInTheDocument();

    expect(screen.getByText("Expires in 40 days")).toBeInTheDocument();
    const sources = screen.getByRole("region", { name: "Data sources" });
    expect(within(sources).getByText("cmdr_ingest_live_…abcd")).toBeInTheDocument();
    expect(within(sources).getByText("203.0.113.9")).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });

  it("removes a source after confirming", async () => {
    const user = userEvent.setup();
    let removed = false;
    render({
      [`${BASE}/health/`]: health,
      [`${BASE}/connections/`]: () => ({ results: removed ? [] : [source] }),
      [`DELETE ${BASE}/connections/s1/`]: () => {
        removed = true;
        return reply(204);
      },
    });
    await user.click(await screen.findByRole("button", { name: "Remove: Production" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Production?" });
    expect(await axeViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(removed).toBe(true);
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Remove: Production" })).not.toBeInTheDocument(),
    );
  });
});
