import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { t } from "@/lib/i18n";

import { setupTime } from "./ConnectorCard";
import type { ConnectorEntry } from "./types";

/**
 * The setup wizard's frame. In Phase 0 every connector is "coming soon": the
 * sheet shows the real steps so people know what is involved, and says plainly
 * that connecting arrives with its phase — it never pretends to connect.
 */
export function SetupSheet({
  connector,
  open,
  onOpenChange,
}: {
  /** The last connector opened. Kept while closed so the dialog can close
   * properly: unmounting it outright skips Radix's focus return. */
  connector: ConnectorEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!connector) return null;
  const comingSoon = connector.availability === "coming_soon";

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title={t("setup.title", { name: connector.name })}
      description={connector.unlocks}
      footer={
        <div className="flex flex-col gap-3">
          {comingSoon ? (
            <p className="text-sm text-muted">
              {t("setup.coming_soon", { phase: connector.phase })}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              {t("common.close")}
            </Button>
            <Button disabled={comingSoon}>{t("setup.start")}</Button>
          </div>
        </div>
      }
    >
      <div className="mb-5 flex flex-wrap items-center gap-2">
        {comingSoon ? (
          <StatusBadge status="info" label={t("setup.phase_badge", { phase: connector.phase })} />
        ) : null}
        <span className="text-sm text-muted">{setupTime(connector.setup_minutes)}</span>
      </div>

      {connector.steps.length > 0 ? (
        <>
          <h3 className="mb-3 text-sm font-semibold">{t("setup.steps_heading")}</h3>
          <ol className="space-y-0">
            {connector.steps.map((step, index) => (
              <li
                key={step.title}
                className="grid grid-cols-[2rem_1fr] gap-3 border-t border-border py-3"
              >
                <span
                  aria-hidden="true"
                  className="inline-flex size-7 items-center justify-center rounded-full border border-primary font-mono text-xs text-primary"
                >
                  {index + 1}
                </span>
                <div>
                  <p className="font-medium">{step.title}</p>
                  <p className="text-sm text-muted">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="text-sm text-muted">{t("setup.no_steps_yet")}</p>
      )}

      {connector.requirements.length > 0 ? (
        <>
          <h3 className="mt-6 mb-2 text-sm font-semibold">{t("setup.needs_heading")}</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {connector.requirements.map((r) => (
              <li key={r.key}>{r.label}</li>
            ))}
          </ul>
        </>
      ) : null}
    </Sheet>
  );
}
