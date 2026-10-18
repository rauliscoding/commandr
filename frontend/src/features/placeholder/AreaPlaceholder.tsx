import type { LucideIcon } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/ui/EmptyState";
import { t, type MessageKey } from "@/lib/i18n";

/**
 * Areas that arrive in later phases. Each says what will be here and points at
 * the integration that fills it, rather than showing an empty dashboard.
 */
export function AreaPlaceholder({
  icon,
  titleKey,
  bodyKey,
}: {
  icon: LucideIcon;
  titleKey: MessageKey;
  bodyKey: MessageKey;
}) {
  const { orgId, projectId } = useParams();
  return (
    <>
      <h1 className="sr-only">{t(titleKey)}</h1>
      <EmptyState
        icon={icon}
        title={t(titleKey)}
        body={t(bodyKey)}
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
