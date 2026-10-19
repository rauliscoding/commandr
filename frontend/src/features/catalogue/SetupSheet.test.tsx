import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { axeViolations, mockFetch, renderAt, reply } from "@/test/utils";

import { CataloguePage } from "./CataloguePage";
import type { Catalogue, ConnectorEntry, FirstData, SetupResponse } from "./types";

const ORG = "11111111-1111-7111-8111-111111111111";
const PROJECT = "22222222-2222-7222-8222-222222222222";
const BASE = `/api/orgs/${ORG}/projects/${PROJECT}`;
const CONN = "33333333-3333-7333-8333-333333333333";
const KEY = "cmdr_ingest_live_0123456789abcdefghijABCDEFGHIJ0123456789abc";

function connector(overrides: Partial<ConnectorEntry>): ConnectorEntry {
  return {
    slug: "x",
    name: "X",
    category: "app_health",
    auth: "ingest_key",
    unlocks: "Does a thing.",
    setup_minutes: 10,
    phase: 1,
    availability: "available",
    logo_text: "X",
    requirements: [],
    capabilities: [],
    steps: [{ title: "Create an ingest key", detail: "Write-only." }],
    fields: [],
    docs_path: "",
    state: "not_connected",
    recommended: false,
    ...overrides,
  };
}

const catalogue: Catalogue = {
  categories: [{ key: "app_health", label: "App health" }],
  recommended: [],
  connected_recommended: 0,
  connectors: [
    connector({
      slug: "push_api",
      name: "Push API",
      fields: [
        {
          name: "name",
          label: "Key name",
          kind: "text",
          help: "Where it will be used.",
          required: true,
          default: "",
          placeholder: "",
          options: [],
        },
        {
          name: "environment",
          label: "Environment",
          kind: "select",
          help: "",
          required: true,
          default: "live",
          placeholder: "",
          options: [
            { value: "live", label: "Live" },
            { value: "test", label: "Test" },
          ],
        },
      ],
    }),
    connector({
      slug: "uptime_probe",
      name: "Uptime probe",
      fields: [
        {
          name: "url",
          label: "Address to check",
          kind: "url",
          help: "",
          required: true,
          default: "",
          placeholder: "",
          options: [],
        },
      ],
    }),
  ],
};

const created: SetupResponse = {
  connection: {
    id: CONN,
    connector: "push_api",
    connector_name: "Push API",
    label: "Production",
    status: "pending",
    created_at: "2026-10-18T09:00:00Z",
    first_data_at: null,
    last_synced_at: null,
    last_error: "",
    details: [],
  },
  reveal: [{ label: "Ingest key", value: KEY, kind: "secret" }],
  snippets: [
    {
      label: "Send a test batch",
      code: "curl -sS https://ingest.test/v1/ingest",
      language: "bash",
    },
  ],
  notes: ["Keep the key server-side."],
};

const waiting: FirstData = {
  state: "waiting",
  received_at: null,
  status: "pending",
  last_error: "",
  summary: [],
};

const received: FirstData = {
  state: "received",
  received_at: "2026-10-18T09:01:00Z",
  status: "connected",
  last_error: "",
  summary: [
    { label: "Metric series", value: "2", kind: "text" },
    { label: "Errors", value: null, kind: "text" },
  ],
};

function render(routes: Record<string, unknown>) {
  const spy = mockFetch({ [`${BASE}/catalogue/`]: catalogue, ...routes });
  renderAt(<CataloguePage />, {
    path: "/o/:orgId/p/:projectId/integrations",
    url: `/o/${ORG}/p/${PROJECT}/integrations`,
  });
  return spy;
}

async function openForm(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("button", { name: `Connect: ${name}` }));
  const dialog = await screen.findByRole("dialog", { name: `Connect ${name}` });
  await user.click(within(dialog).getByRole("button", { name: "Start setup" }));
  return dialog;
}

describe("SetupSheet", () => {
  it("sets up a key, shows it once, then shows the first data", async () => {
    const user = userEvent.setup();
    const spy = render({
      [`POST ${BASE}/connections/`]: reply(201, created),
      [`${BASE}/connections/${CONN}/first-data/`]: received,
    });
    const dialog = await openForm(user, "Push API");
    await user.type(within(dialog).getByRole("textbox", { name: /Key name/ }), "Production");
    await user.selectOptions(within(dialog).getByRole("combobox", { name: /Environment/ }), "test");
    await user.click(within(dialog).getByRole("button", { name: "Connect" }));

    expect(await within(dialog).findByRole("textbox", { name: "Ingest key" })).toHaveValue(KEY);
    expect(within(dialog).getByText(/shown only once/)).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Copy Send a test batch" }),
    ).toBeInTheDocument();
    const post = spy.mock.calls.find(([, init]) => init?.method === "POST" && init.body);
    expect(JSON.parse(String(post![1]!.body))).toEqual({
      connector: "push_api",
      fields: { name: "Production", environment: "test" },
    });
    expect(await axeViolations()).toEqual([]);

    await user.click(within(dialog).getByRole("button", { name: "I have saved them — continue" }));
    expect(await within(dialog).findByText("First data received")).toBeInTheDocument();
    expect(within(dialog).getByText("2")).toBeInTheDocument();
    expect(within(dialog).getByText("—")).toBeInTheDocument(); // unknown, not 0
    expect(within(dialog).getByRole("link", { name: "Go to Health" })).toBeInTheDocument();
    expect(screen.queryByDisplayValue(KEY)).not.toBeInTheDocument();
  });

  it("says it is waiting, and shows the last problem with a way to check again", async () => {
    const user = userEvent.setup();
    render({
      [`POST ${BASE}/connections/`]: reply(201, { ...created, reveal: [], snippets: [] }),
      [`${BASE}/connections/${CONN}/first-data/`]: {
        ...waiting,
        last_error: "Your app refused our signature (HTTP 401).",
      },
      [`POST ${BASE}/connections/${CONN}/check-now/`]: reply(202),
    });
    const dialog = await openForm(user, "Uptime probe");
    await user.type(within(dialog).getByRole("textbox", { name: /Address/ }), "https://x.test/");
    await user.click(within(dialog).getByRole("button", { name: "Connect" }));
    expect(await within(dialog).findByText(/Waiting for the first data/)).toBeInTheDocument();
    expect(await within(dialog).findByText(/refused our signature/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Check again" }));
    expect(await axeViolations()).toEqual([]);
  });

  it("shows the server's field errors next to the field", async () => {
    const user = userEvent.setup();
    render({
      [`POST ${BASE}/connections/`]: reply(400, { url: ["Use an https:// address."] }),
    });
    const dialog = await openForm(user, "Uptime probe");
    await user.click(within(dialog).getByRole("button", { name: "Connect" }));
    const field = within(dialog).getByRole("textbox", { name: /Address/ });
    expect(await within(dialog).findByText("Use an https:// address.")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
  });

  it("asks for the password when the API wants a recent sign-in, then retries", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    render({
      [`POST ${BASE}/connections/`]: () =>
        ++attempts === 1
          ? reply(401, { detail: "Enter your password again.", code: "reauthentication_required" })
          : reply(201, created),
      "POST /api/auth/browser/v1/auth/reauthenticate": reply(200, { status: 200 }),
    });
    const dialog = await openForm(user, "Push API");
    await user.type(within(dialog).getByRole("textbox", { name: /Key name/ }), "Production");
    await user.click(within(dialog).getByRole("button", { name: "Connect" }));

    const reauth = await screen.findByRole("dialog", { name: "Confirm it is you" });
    await user.type(within(reauth).getByLabelText(/Password/), "correct horse battery");
    await user.click(within(reauth).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("textbox", { name: "Ingest key" })).toHaveValue(KEY);
    expect(attempts).toBe(2);
  });
});
