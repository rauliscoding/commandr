import { Button } from "@/components/ui/Button";
import { StatusBadge, type Status } from "@/components/ui/StatusBadge";
import { t, type MessageKey } from "@/lib/i18n";

import type { ConnectorEntry, ConnectorState } from "./types";

const STATE: Record<ConnectorState, { status: Status; key: MessageKey } | null> = {
  not_connected: null,
  setting_up: { status: "info", key: "catalogue.state.setting_up" },
  connected: { status: "ok", key: "catalogue.state.connected" },
  needs_attention: { status: "fail", key: "catalogue.state.needs_attention" },
};

export function setupTime(minutes: number): string {
  return minutes < 1
    ? t("catalogue.setup_seconds", { n: Math.round(minutes * 60) })
    : t("catalogue.setup_minutes", { n: minutes });
}

export function ConnectorCard({
  connector,
  onOpen,
}: {
  connector: ConnectorEntry;
  onOpen: () => void;
}) {
  const state = STATE[connector.state];
  const action =
    connector.state === "not_connected"
      ? t("catalogue.connect")
      : connector.state === "needs_attention"
        ? t("catalogue.fix")
        : t("catalogue.manage");

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-surface-sunken font-mono text-xs font-medium"
        >
          {connector.logo_text}
        </span>
        <h3 className="min-w-0 text-base font-semibold">{connector.name}</h3>
      </div>
      <p className="min-h-[2.9em] text-sm text-muted">{connector.unlocks}</p>
      <ul
        className="flex flex-wrap gap-1.5"
        aria-label={t("catalogue.requirements_label", { name: connector.name })}
      >
        <li className="rounded-full border border-border px-2 py-0.5 font-mono text-[0.6875rem] text-muted">
          {setupTime(connector.setup_minutes)}
        </li>
        {connector.requirements.map((r) => (
          <li
            key={r.key}
            className="rounded-full border border-border px-2 py-0.5 font-mono text-[0.6875rem] text-muted"
          >
            {r.label}
          </li>
        ))}
      </ul>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
        {state ? <StatusBadge status={state.status} label={t(state.key)} /> : <span />}
        <Button
          variant={connector.state === "not_connected" ? "primary" : "secondary"}
          size="sm"
          onClick={onOpen}
          aria-label={`${action}: ${connector.name}`}
        >
          {action}
        </Button>
      </div>
    </li>
  );
}
