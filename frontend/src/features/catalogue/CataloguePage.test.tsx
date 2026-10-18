import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { axeViolations, mockFetch, renderAt } from "@/test/utils";

import { CataloguePage } from "./CataloguePage";
import type { Catalogue, ConnectorEntry } from "./types";

const ORG = "11111111-1111-7111-8111-111111111111";
const PROJECT = "22222222-2222-7222-8222-222222222222";

function connector(overrides: Partial<ConnectorEntry>): ConnectorEntry {
  return {
    slug: "x",
    name: "X",
    category: "app_health",
    auth: "none",
    unlocks: "Does a thing.",
    setup_minutes: 2,
    phase: 1,
    availability: "coming_soon",
    logo_text: "X",
    requirements: [{ key: "free", label: "Free" }],
    capabilities: [],
    steps: [{ title: "Do the first thing", detail: "Like this." }],
    docs_path: "",
    state: "not_connected",
    recommended: false,
    ...overrides,
  };
}

const catalogue: Catalogue = {
  categories: [
    { key: "app_health", label: "App health" },
    { key: "social", label: "Social" },
  ],
  recommended: ["uptime_probe", "instagram"],
  connected_recommended: 1,
  connectors: [
    connector({
      slug: "uptime_probe",
      name: "Uptime probe",
      setup_minutes: 0.5,
      state: "connected",
      recommended: true,
    }),
    connector({
      slug: "instagram",
      name: "Instagram",
      category: "social",
      recommended: true,
      unlocks: "Schedule posts.",
    }),
    connector({ slug: "tiktok", name: "TikTok", category: "social", state: "needs_attention" }),
  ],
};

function renderCatalogue() {
  mockFetch({ [`/api/orgs/${ORG}/projects/${PROJECT}/catalogue/`]: catalogue });
  return renderAt(<CataloguePage />, {
    path: "/o/:orgId/p/:projectId/integrations",
    url: `/o/${ORG}/p/${PROJECT}/integrations`,
  });
}

describe("CataloguePage", () => {
  it("shows the recommended row with progress, in the server's order", async () => {
    renderCatalogue();
    const section = (await screen.findByRole("heading", { name: "Recommended first" })).closest(
      "section",
    )!;
    expect(within(section).getByText("1 of 2 connected")).toBeInTheDocument();
    const names = within(section)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(names).toEqual(["Uptime probe", "Instagram"]);
  });

  it("says each state in words, not just colour", async () => {
    renderCatalogue();
    const all = (await screen.findByRole("heading", { name: "All integrations" })).closest(
      "section",
    )!;
    expect(within(all).getByText("Connected")).toBeInTheDocument();
    expect(within(all).getByText("Needs attention")).toBeInTheDocument();
    expect(within(all).getByRole("button", { name: "Fix: TikTok" })).toBeInTheDocument();
    expect(within(all).getByText("~30 s")).toBeInTheDocument();
  });

  it("filters by category with pressed-state buttons", async () => {
    const user = userEvent.setup();
    renderCatalogue();
    const all = (await screen.findByRole("heading", { name: "All integrations" })).closest(
      "section",
    )!;
    const social = within(all).getByRole("button", { name: "Social" });
    await user.click(social);
    expect(social).toHaveAttribute("aria-pressed", "true");
    expect(within(all).queryByRole("heading", { name: "Uptime probe" })).not.toBeInTheDocument();
    expect(within(all).getByRole("heading", { name: "TikTok" })).toBeInTheDocument();
  });

  it("searches by name and by what it unlocks", async () => {
    const user = userEvent.setup();
    renderCatalogue();
    await user.type(
      await screen.findByRole("searchbox", { name: "Search integrations" }),
      "schedule",
    );
    const all = screen.getByRole("heading", { name: "All integrations" }).closest("section")!;
    expect(
      within(all)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(["Instagram"]);
  });

  it("opens the setup sheet with the steps, and is honest that connecting is not built yet", async () => {
    const user = userEvent.setup();
    renderCatalogue();
    const all = (await screen.findByRole("heading", { name: "All integrations" })).closest(
      "section",
    )!;
    await user.click(within(all).getByRole("button", { name: "Connect: Instagram" }));
    const dialog = await screen.findByRole("dialog", { name: "Connect Instagram" });
    expect(within(dialog).getByText("Do the first thing")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Start setup" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("returns focus to the button that opened the sheet", async () => {
    const user = userEvent.setup();
    renderCatalogue();
    const all = (await screen.findByRole("heading", { name: "All integrations" })).closest(
      "section",
    )!;
    const trigger = within(all).getByRole("button", { name: "Connect: Instagram" });
    await user.click(trigger);
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("has no axe violations, closed or with the sheet open", async () => {
    const user = userEvent.setup();
    renderCatalogue();
    const all = (await screen.findByRole("heading", { name: "All integrations" })).closest(
      "section",
    )!;
    expect(await axeViolations()).toEqual([]);
    await user.click(within(all).getByRole("button", { name: "Connect: Instagram" }));
    await screen.findByRole("dialog");
    expect(await axeViolations()).toEqual([]);
  });
});
