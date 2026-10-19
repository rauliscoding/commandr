/** Mirrors `commandr.integrations.catalogue.build_catalogue` — keep in step. */

export type ConnectorState = "not_connected" | "setting_up" | "connected" | "needs_attention";
export type Availability = "available" | "coming_soon";

/** One input of a connector's setup form (`registry.SetupField`). */
export interface SetupFieldDef {
  name: string;
  label: string;
  kind: "text" | "url" | "select" | "number";
  help: string;
  required: boolean;
  default: string;
  placeholder: string;
  options: { value: string; label: string }[];
}

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
  fields: SetupFieldDef[];
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

/** Mirrors `integrations.setup.Detail`: `null` renders as "—". */
export interface Detail {
  label: string;
  value: string | null;
  kind: "text" | "time" | "code";
}

/** Mirrors `integrations.views.connection_data`. */
export interface ConnectionInfo {
  id: string;
  connector: string;
  connector_name: string;
  label: string;
  status: "pending" | "connected" | "needs_reauth" | "error" | "disabled";
  created_at: string;
  first_data_at: string | null;
  last_synced_at: string | null;
  last_error: string;
  details: Detail[];
}

/** POST /connections/ answer. `reveal` values are shown once and never again. */
export interface SetupResponse {
  connection: ConnectionInfo;
  reveal: { label: string; value: string; kind: "secret" | "url" | "text" }[];
  snippets: { label: string; code: string; language: string }[];
  notes: string[];
}

export interface FirstData {
  state: "waiting" | "received";
  received_at: string | null;
  status: ConnectionInfo["status"];
  last_error: string;
  summary: Detail[];
}
