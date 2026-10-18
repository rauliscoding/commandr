import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useParams } from "react-router";

import { FormError } from "@/components/ui/Field";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/cn";
import { t } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";

import { ConnectorCard } from "./ConnectorCard";
import { SetupSheet } from "./SetupSheet";
import type { Catalogue, ConnectorEntry } from "./types";

const ALL = "all";

/**
 * The integration catalogue: a project's home until something is connected
 * (docs/product/onboarding-and-catalogue.md). Everything on it comes from the
 * connector registry — there is no per-connector code on this screen.
 */
export function CataloguePage() {
  const { orgId = "", projectId = "" } = useParams();
  const [category, setCategory] = useState(ALL);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<ConnectorEntry | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const searchId = useId();

  function openSheet(connector: ConnectorEntry) {
    setSelected(connector);
    setSheetOpen(true);
  }

  const { data, isPending, error } = useQuery({
    queryKey: queryKeys.catalogue(orgId, projectId),
    queryFn: () => apiFetch<Catalogue>(`/api/orgs/${orgId}/projects/${projectId}/catalogue/`),
  });

  const visible = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.connectors.filter(
      (c) =>
        (category === ALL || c.category === category) &&
        (!q || c.name.toLowerCase().includes(q) || c.unlocks.toLowerCase().includes(q)),
    );
  }, [data, category, query]);

  const recommended = useMemo(
    () =>
      data
        ? data.recommended
            .map((slug) => data.connectors.find((c) => c.slug === slug))
            .filter((c): c is ConnectorEntry => Boolean(c))
        : [],
    [data],
  );

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t("catalogue.title")}</h1>
          <p className="mt-1 max-w-prose text-muted">{t("catalogue.subtitle")}</p>
        </div>
        <div className="relative w-full sm:w-72">
          <label htmlFor={searchId} className="sr-only">
            {t("catalogue.search_label")}
          </label>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle"
          />
          <input
            id={searchId}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("catalogue.search_placeholder")}
            className="w-full rounded-md border border-border-strong bg-surface py-2 pr-3 pl-9 text-base"
          />
        </div>
      </header>

      {error ? <FormError message={t("catalogue.load_error")} /> : null}

      {isPending ? (
        <p aria-busy="true" className="py-16 text-center text-muted">
          {t("common.loading")}
        </p>
      ) : null}

      {data && recommended.length > 0 ? (
        <section aria-labelledby="recommended-heading" className="mb-10">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="recommended-heading" className="text-lg font-semibold">
              {t("catalogue.recommended")}
            </h2>
            <p className="text-sm text-muted">
              {t("catalogue.recommended_progress", {
                done: data.connected_recommended,
                total: recommended.length,
              })}
            </p>
          </div>
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
            {recommended.map((c) => (
              <ConnectorCard key={c.slug} connector={c} onOpen={() => openSheet(c)} />
            ))}
          </ul>
        </section>
      ) : null}

      {data ? (
        <section aria-labelledby="all-heading">
          <h2 id="all-heading" className="mb-3 text-lg font-semibold">
            {t("catalogue.all")}
          </h2>
          <div
            role="group"
            aria-label={t("catalogue.filter_label")}
            className="mb-4 flex flex-wrap gap-2"
          >
            {[{ key: ALL, label: t("catalogue.filter_all") }, ...data.categories].map((cat) => (
              <button
                key={cat.key}
                type="button"
                aria-pressed={category === cat.key}
                onClick={() => setCategory(cat.key)}
                className={cn(
                  "min-h-9 rounded-md border px-3 text-sm",
                  category === cat.key
                    ? "border-fg bg-fg text-canvas"
                    : "border-border bg-surface text-muted hover:text-fg",
                )}
              >
                {cat.label}
              </button>
            ))}
          </div>
          <p aria-live="polite" className="sr-only">
            {t("catalogue.results", { n: visible.length })}
          </p>
          {visible.length > 0 ? (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
              {visible.map((c) => (
                <ConnectorCard key={c.slug} connector={c} onOpen={() => openSheet(c)} />
              ))}
            </ul>
          ) : (
            <p className="py-10 text-center text-muted">{t("catalogue.no_results")}</p>
          )}
        </section>
      ) : null}

      <SetupSheet connector={selected} open={sheetOpen} onOpenChange={setSheetOpen} />
    </div>
  );
}
