/** Mirrors `commandr.integrations.catalogue.build_catalogue` — keep in step. */

export type ConnectorState = "not_connected" | "setting_up" | "connected" | "needs_attention";
export type Availability = "available" | "coming_soon";

export interface ConnectorEntry {
  slug: string;
  name: string;
  category: string;
  auth: string;
  unlocks: string;
  setup_minutes: number;
  phase: number;
  availability: Availability;
  logo_text: string;
  requirements: { key: string; label: string }[];
  capabilities: string[];
  steps: { title: string; detail: string }[];
  docs_path: string;
  state: ConnectorState;
  recommended: boolean;
}

export interface Catalogue {
  categories: { key: string; label: string }[];
  recommended: string[];
  connected_recommended: number;
  connectors: ConnectorEntry[];
}
