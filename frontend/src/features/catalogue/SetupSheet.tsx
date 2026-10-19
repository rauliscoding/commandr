import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, KeyRound, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import { Button } from "@/components/ui/Button";
import { CopyField } from "@/components/ui/CopyField";
import { DetailList } from "@/components/ui/DetailList";
import { FormError, SelectField, TextField } from "@/components/ui/Field";
import { useReauth } from "@/components/ui/ReauthDialog";
import { Sheet } from "@/components/ui/Sheet";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import { projectApi, queryKeys } from "@/lib/queryKeys";

import { setupTime } from "./ConnectorCard";
import type { ConnectorEntry, FirstData, SetupResponse } from "./types";

type Phase = "overview" | "form" | "reveal" | "waiting";

const FORM_ID = "connector-setup-form";
const POLL_MS = 3000;

/**
 * The setup wizard (docs/product/onboarding-and-catalogue.md): steps → form →
 * values shown once → "waiting for first data" → the first data. Everything it
 * renders comes from the registry and the connector's setup handler, so a new
 * connector needs no code here (CLAUDE.md invariant 7). Coming-soon connectors
 * show their steps and say plainly that connecting is not built yet.
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
  const { orgId = "", projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("overview");
  const [result, setResult] = useState<SetupResponse | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const { run, dialog } = useReauth();

  const connectionId = result?.connection.id ?? "";
  const firstData = useQuery({
    queryKey: queryKeys.firstData(orgId, projectId, connectionId),
    queryFn: () =>
      apiFetch<FirstData>(
        `${projectApi(orgId, projectId)}/connections/${connectionId}/first-data/`,
      ),
    enabled: open && phase === "waiting" && Boolean(connectionId),
    refetchInterval: (query) => (query.state.data?.state === "received" ? false : POLL_MS),
  });

  if (!connector) return null;
  const comingSoon = connector.availability === "coming_soon";
  const received = firstData.data?.state === "received";

  function handleOpenChange(next: boolean) {
    if (!next) {
      // Whatever was set up should show on the catalogue and Health page now.
      void queryClient.invalidateQueries({ queryKey: queryKeys.catalogue(orgId, projectId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.connections(orgId, projectId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.health(orgId, projectId) });
      setPhase("overview");
      setResult(null);
      setErrors({});
    }
    onOpenChange(next);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!connector) return;
    const form = new FormData(event.currentTarget);
    const fields = Object.fromEntries(connector.fields.map((f) => [f.name, form.get(f.name)]));
    setBusy(true);
    setErrors({});
    try {
      const created = await run(() =>
        apiFetch<SetupResponse>(`${projectApi(orgId, projectId)}/connections/`, {
          method: "POST",
          body: { connector: connector.slug, fields },
        }),
      );
      setResult(created);
      setPhase(created.reveal.length || created.snippets.length ? "reveal" : "waiting");
    } catch (e) {
      if (e instanceof ApiError) {
        const fieldErrors = e.fieldErrors();
        setErrors(Object.keys(fieldErrors).length ? fieldErrors : { form: t("setup.failed") });
      } else {
        setErrors({ form: t("auth.network_error") });
      }
    } finally {
      setBusy(false);
    }
  }

  async function checkAgain() {
    try {
      await apiFetch(`${projectApi(orgId, projectId)}/connections/${connectionId}/check-now/`, {
        method: "POST",
      });
      // The result arrives within seconds; polling picks it up.
    } catch {
      // Nothing to add: the problem shown already says what to fix.
    }
  }

  const footer = (() => {
    const close = (
      <Button variant="secondary" onClick={() => handleOpenChange(false)}>
        {t("common.close")}
      </Button>
    );
    if (comingSoon) {
      return (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">{t("setup.coming_soon", { phase: connector.phase })}</p>
          <div className="flex justify-end gap-2">
            {close}
            <Button disabled>{t("setup.start")}</Button>
          </div>
        </div>
      );
    }
    switch (phase) {
      case "overview":
        return (
          <div className="flex justify-end gap-2">
            {close}
            <Button onClick={() => setPhase("form")}>{t("setup.start")}</Button>
          </div>
        );
      case "form":
        return (
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setPhase("overview")}>
              {t("common.back")}
            </Button>
            <Button type="submit" form={FORM_ID} disabled={busy}>
              {busy ? t("common.working") : t("setup.connect")}
            </Button>
          </div>
        );
      case "reveal":
        return (
          <div className="flex justify-end gap-2">
            <Button onClick={() => setPhase("waiting")}>{t("setup.saved_continue")}</Button>
          </div>
        );
      case "waiting":
        return (
          <div className="flex flex-wrap justify-end gap-2">
            {received ? (
              <>
                <Button variant="secondary" onClick={() => setPhase("form")}>
                  {t("setup.connect_another")}
                </Button>
                <Link
                  to={`/o/${orgId}/p/${projectId}/health`}
                  onClick={() => handleOpenChange(false)}
                  className="inline-flex min-h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-contrast hover:bg-primary-hover"
                >
                  {t("setup.go_to_health")}
                </Link>
              </>
            ) : (
              close
            )}
          </div>
        );
    }
  })();

  return (
    <Sheet
      open={open}
      onOpenChange={handleOpenChange}
      title={t("setup.title", { name: connector.name })}
      description={connector.unlocks}
      footer={footer}
    >
      {dialog}
      {comingSoon || phase === "overview" ? (
        <Overview connector={connector} comingSoon={comingSoon} />
      ) : null}

      {!comingSoon && phase === "form" ? (
        <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4">
          <h3 className="text-sm font-semibold">{t("setup.form_heading")}</h3>
          <FormError message={errors.form ?? errors.connector ?? errors.detail} />
          {connector.fields.map((field) =>
            field.kind === "select" ? (
              <SelectField
                key={field.name}
                name={field.name}
                label={field.label}
                help={field.help || undefined}
                defaultValue={field.default}
                options={field.options}
                required={field.required}
                error={errors[field.name]}
              />
            ) : (
              <TextField
                key={field.name}
                name={field.name}
                label={field.label}
                help={field.help || undefined}
                defaultValue={field.default}
                placeholder={field.placeholder || undefined}
                type={field.kind === "url" ? "url" : field.kind === "number" ? "number" : "text"}
                inputMode={field.kind === "url" ? "url" : undefined}
                required={field.required}
                error={errors[field.name]}
              />
            ),
          )}
        </form>
      ) : null}

      {phase === "reveal" && result ? <Reveal result={result} /> : null}

      {phase === "waiting" && result ? (
        <section aria-labelledby="first-data-heading" className="space-y-4">
          <h3 id="first-data-heading" className="text-sm font-semibold">
            {received ? t("setup.first_data") : t("setup.waiting")}
          </h3>
          <div aria-live="polite" className="space-y-4">
            {received ? (
              <>
                <StatusBadge status="ok" label={t("catalogue.state.connected")} />
                <DetailList items={firstData.data?.summary ?? []} />
              </>
            ) : (
              <>
                <p className="flex items-center gap-2 text-sm text-muted">
                  <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
                  {t("setup.waiting_body")}
                </p>
                {result.notes.length ? (
                  <ul className="list-disc space-y-1 pl-5 text-sm">
                    {result.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
            {!received && firstData.data?.last_error ? (
              <div className="space-y-2 rounded-md border border-warn-border bg-warn-bg px-3 py-2 text-sm text-warn-fg">
                <p>
                  <span className="font-medium">{t("setup.last_problem")}</span>{" "}
                  {firstData.data.last_error}
                </p>
                <Button size="sm" variant="secondary" onClick={checkAgain}>
                  {t("setup.check_again")}
                </Button>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </Sheet>
  );
}

function Overview({ connector, comingSoon }: { connector: ConnectorEntry; comingSoon: boolean }) {
  return (
    <>
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
    </>
  );
}

function Reveal({ result }: { result: SetupResponse }) {
  const hasSecret = result.reveal.length > 0;
  return (
    <div className="space-y-5">
      <p className="flex items-center gap-2 text-sm font-medium">
        <CircleCheck aria-hidden="true" className="size-4 text-ok-fg" />
        {t("setup.created", { name: result.connection.connector_name })}
      </p>
      {hasSecret ? (
        <div className="flex gap-2 rounded-md border border-warn-border bg-warn-bg px-3 py-2 text-sm text-warn-fg">
          <KeyRound aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p>{t("setup.shown_once")}</p>
        </div>
      ) : null}
      {result.reveal.map((r) => (
        <CopyField key={r.label} label={r.label} value={r.value} />
      ))}
      {result.notes.length ? (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {result.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      {result.snippets.map((s) => (
        <CopyField key={s.label} label={s.label} value={s.code} multiline />
      ))}
    </div>
  );
}
