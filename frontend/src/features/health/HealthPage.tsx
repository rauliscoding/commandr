import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { Button } from "@/components/ui/Button";
import { DetailList } from "@/components/ui/DetailList";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/Field";
import { useReauth } from "@/components/ui/ReauthDialog";
import { StatusBadge, type Status } from "@/components/ui/StatusBadge";
import { Time } from "@/components/ui/Time";
import type { ConnectionInfo } from "@/features/catalogue/types";
import { apiFetch } from "@/lib/api";
import { daysUntil, formatDuration, formatEvery, formatMetric, UNKNOWN } from "@/lib/format";
import { t, type MessageKey } from "@/lib/i18n";
import { projectApi, queryKeys } from "@/lib/queryKeys";

import type { CheckStatus, Health, HealthCheck, VerdictState } from "./types";

const REFRESH_MS = 30_000;

const STATUS_KEY: Record<CheckStatus, MessageKey> = {
  ok: "health.status.ok",
  warn: "health.status.warn",
  fail: "health.status.fail",
  unknown: "health.status.unknown",
};

const VERDICT: Record<VerdictState, { status: Status; key: MessageKey; body: MessageKey }> = {
  healthy: { status: "ok", key: "health.verdict.healthy", body: "health.verdict.healthy_body" },
  attention: {
    status: "warn",
    key: "health.verdict.attention",
    body: "health.verdict.attention_body",
  },
  nothing_checked: {
    status: "unknown",
    key: "health.verdict.nothing_checked",
    body: "health.verdict.nothing_checked_body",
  },
};

const SOURCE_KEY: Record<HealthCheck["source"], MessageKey> = {
  uptime: "health.source.uptime",
  heartbeat: "health.source.heartbeat",
  status_endpoint: "health.source.status_endpoint",
  rule: "health.source.rule",
};

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mb-8">
      <h2 id={id} className="mb-3 text-lg font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

const th = "px-3 py-2 text-left text-xs font-medium tracking-wide text-muted uppercase";
const td = "px-3 py-2 align-top";

function Table({
  caption,
  head,
  children,
}: {
  caption: string;
  head: string[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-border bg-surface-sunken">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className={th}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  );
}

/**
 * The project's health: verdict, checks, scheduled jobs, KPIs and the sources
 * feeding them. Unknown is shown as unknown, and missing numbers as "—"
 * (CLAUDE.md invariant 5).
 */
export function HealthPage() {
  const { orgId = "", projectId = "" } = useParams();
  const base = projectApi(orgId, projectId);
  const health = useQuery({
    queryKey: queryKeys.health(orgId, projectId),
    queryFn: () => apiFetch<Health>(`${base}/health/`),
    refetchInterval: REFRESH_MS,
  });
  const connections = useQuery({
    queryKey: queryKeys.connections(orgId, projectId),
    queryFn: () => apiFetch<{ results: ConnectionInfo[] }>(`${base}/connections/`),
    refetchInterval: REFRESH_MS,
  });

  const title = <h1 className="text-2xl font-semibold">{t("nav.health")}</h1>;

  if (health.isPending || connections.isPending) {
    return (
      <div className="mx-auto max-w-6xl">
        {title}
        <p aria-busy="true" className="py-16 text-center text-muted">
          {t("common.loading")}
        </p>
      </div>
    );
  }
  if (health.error || connections.error || !health.data || !connections.data) {
    return (
      <div className="mx-auto max-w-6xl space-y-4">
        {title}
        <FormError message={t("health.load_error")} />
      </div>
    );
  }

  const data = health.data;
  const sources = connections.data.results;
  if (sources.length === 0 && data.checks.length === 0) {
    return (
      <>
        <h1 className="sr-only">{t("nav.health")}</h1>
        <EmptyState
          icon={Activity}
          title={t("nav.health")}
          body={t("placeholder.health")}
          action={
            <Link
              to={`/o/${orgId}/p/${projectId}/integrations`}
              className="inline-flex min-h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-contrast hover:bg-primary-hover"
            >
              {t("placeholder.go_to_integrations")}
            </Link>
          }
        />
      </>
    );
  }

  const verdict = VERDICT[data.verdict.state];
  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">{title}</header>

      <section
        aria-labelledby="verdict-heading"
        className="mb-8 rounded-lg border border-border bg-surface p-4"
      >
        <h2 id="verdict-heading" className="sr-only">
          {t("health.overall")}
        </h2>
        <StatusBadge status={verdict.status} label={t(verdict.key)} className="text-sm" />
        <p className="mt-1 text-sm text-muted">{t(verdict.body)}</p>
        <p className="mt-2 text-sm">
          {t("health.verdict.counts", {
            ok: data.verdict.ok,
            fail: data.verdict.failing,
            warn: data.verdict.warning,
            unknown: data.verdict.unknown,
          })}{" "}
          · {t("health.last_checked")} <Time iso={data.verdict.last_checked_at} />
        </p>
      </section>

      {data.checks.length > 0 ? (
        <Section id="checks-heading" title={t("health.checks")}>
          <Table
            caption={t("health.checks")}
            head={[
              t("health.col.check"),
              t("health.col.status"),
              t("health.col.detail"),
              t("health.col.checked"),
            ]}
          >
            {data.checks.map((c) => (
              <tr key={c.id}>
                <td className={td}>
                  <span className="font-medium">{c.name}</span>
                  <span className="block text-xs text-muted">{t(SOURCE_KEY[c.source])}</span>
                </td>
                <td className={td}>
                  <StatusBadge status={c.status} label={t(STATUS_KEY[c.status])} />
                </td>
                <td className={td}>
                  {c.summary || (c.value !== null ? formatMetric(c.value, c.unit) : UNKNOWN)}
                </td>
                <td className={td}>
                  <Time iso={c.last_run_at} />
                </td>
              </tr>
            ))}
          </Table>
        </Section>
      ) : null}

      {data.heartbeats.length > 0 ? (
        <Section id="heartbeats-heading" title={t("health.heartbeats")}>
          <Table
            caption={t("health.heartbeats")}
            head={[
              t("health.col.job"),
              t("health.col.status"),
              t("health.col.expected"),
              t("health.col.last_ping"),
              t("health.col.took"),
            ]}
          >
            {data.heartbeats.map((h) => (
              <tr key={h.id}>
                <td className={`${td} font-medium`}>{h.name}</td>
                <td className={td}>
                  <StatusBadge status={h.status} label={t(STATUS_KEY[h.status])} />
                  <span className="mt-1 block text-xs text-muted">{h.summary}</span>
                </td>
                <td className={td}>{formatEvery(h.period_seconds)}</td>
                <td className={td}>
                  <Time iso={h.last_ping_at} />
                </td>
                <td className={`${td} font-mono tabular-nums`}>
                  {formatDuration(h.last_duration_ms)}
                </td>
              </tr>
            ))}
          </Table>
        </Section>
      ) : null}

      {data.kpis.length > 0 ? (
        <Section id="kpis-heading" title={t("health.kpis")}>
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-3">
            {data.kpis.map((k) => (
              <li key={k.name} className="rounded-lg border border-border bg-surface p-4">
                <p className="text-sm text-muted">{k.label}</p>
                <p className="mt-1 font-mono text-2xl tabular-nums">
                  {formatMetric(k.value, k.unit)}
                </p>
                <p className="mt-1 text-xs text-muted">
                  {k.value === null ? t("health.kpi_not_available") : t("health.as_of")}{" "}
                  {k.value === null ? null : <Time iso={k.as_of} />}
                </p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {data.uptime.length > 0 ? (
        <Section id="uptime-heading" title={t("health.uptime")}>
          <Table
            caption={t("health.uptime")}
            head={[
              t("health.col.address"),
              t("health.col.result"),
              t("health.col.response"),
              t("health.col.tls"),
            ]}
          >
            {data.uptime.map((u) => (
              <tr key={u.id}>
                <td className={`${td} font-mono text-xs break-all`}>{u.url}</td>
                <td className={td}>
                  {u.last_error ||
                    (u.last_status_code !== null ? `HTTP ${u.last_status_code}` : UNKNOWN)}
                </td>
                <td className={`${td} font-mono tabular-nums`}>
                  {formatDuration(u.last_response_ms)}
                </td>
                <td className={td}>
                  {u.tls_expires_at
                    ? t("health.tls_days", { n: daysUntil(u.tls_expires_at) })
                    : UNKNOWN}
                </td>
              </tr>
            ))}
          </Table>
        </Section>
      ) : null}

      <Section id="sources-heading" title={t("health.sources")}>
        <ul className="grid gap-3 md:grid-cols-2">
          {sources.map((s) => (
            <SourceCard key={s.id} source={s} />
          ))}
        </ul>
        <p className="mt-3 text-sm">
          <Link to={`/o/${orgId}/p/${projectId}/integrations`} className="text-link underline">
            {t("health.add_source")}
          </Link>
        </p>
      </Section>
    </div>
  );
}

const CONNECTION_STATUS: Record<ConnectionInfo["status"], { status: Status; key: MessageKey }> = {
  pending: { status: "info", key: "catalogue.state.setting_up" },
  connected: { status: "ok", key: "catalogue.state.connected" },
  needs_reauth: { status: "fail", key: "catalogue.state.needs_attention" },
  error: { status: "fail", key: "catalogue.state.needs_attention" },
  disabled: { status: "unknown", key: "health.source_disabled" },
};

function SourceCard({ source }: { source: ConnectionInfo }) {
  const { orgId = "", projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string>();
  const { run, dialog } = useReauth();
  const state = CONNECTION_STATUS[source.status];
  const name = source.label || source.connector_name;

  async function remove() {
    setError(undefined);
    try {
      await run(() =>
        apiFetch(`${projectApi(orgId, projectId)}/connections/${source.id}/`, { method: "DELETE" }),
      );
      setConfirming(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.connections(orgId, projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.health(orgId, projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.catalogue(orgId, projectId) }),
      ]);
    } catch {
      setError(t("health.remove_failed"));
    }
  }

  return (
    <li className="rounded-lg border border-border bg-surface p-4">
      {dialog}
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold break-words">{name}</h3>
          <p className="text-sm text-muted">{source.connector_name}</p>
        </div>
        <StatusBadge status={state.status} label={t(state.key)} />
      </div>
      {source.last_error ? <p className="mb-3 text-sm text-fail-fg">{source.last_error}</p> : null}
      <DetailList items={source.details} />
      <div className="mt-3 flex justify-end">
        <Dialog.Root open={confirming} onOpenChange={setConfirming}>
          <Dialog.Trigger asChild>
            <Button variant="danger" size="sm">
              {t("health.remove")}
              <span className="sr-only">: {name}</span>
            </Button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay" />
            <Dialog.Content className="fixed inset-x-4 top-1/2 z-50 mx-auto max-w-md -translate-y-1/2 rounded-lg bg-surface p-5 shadow-overlay">
              <Dialog.Title className="text-lg font-semibold">
                {t("health.remove_title", { name })}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted">
                {t("health.remove_body")}
              </Dialog.Description>
              <div className="mt-4">
                <FormError message={error} />
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <Dialog.Close asChild>
                  <Button variant="secondary">{t("common.cancel")}</Button>
                </Dialog.Close>
                <Button variant="danger" onClick={remove}>
                  {t("health.remove_confirm")}
                </Button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    </li>
  );
}
