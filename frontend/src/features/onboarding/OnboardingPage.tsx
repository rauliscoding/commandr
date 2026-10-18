import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/Button";
import { FormError, SelectField, TextField } from "@/components/ui/Field";
import { AuthLayout } from "@/features/auth/AuthLayout";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";

interface CreatedOrg {
  organization: { id: string };
  project: { id: string };
}

const KINDS = ["web_app", "mobile_app", "api", "shop"] as const;

/** Organization + first project in one step, then straight to the catalogue. */
export function OnboardingPage() {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setErrors({});
    try {
      const created = await apiFetch<CreatedOrg>("/api/organizations/", {
        method: "POST",
        body: {
          name: form.get("name"),
          country: String(form.get("country") ?? "").toUpperCase(),
          currency: form.get("currency"),
          project_name: form.get("project_name"),
          project_url: form.get("project_url"),
          project_kind: form.get("project_kind"),
        },
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
      navigate(`/o/${created.organization.id}/p/${created.project.id}/integrations`, {
        replace: true,
      });
    } catch (e) {
      setErrors(e instanceof ApiError ? e.fieldErrors() : { form: t("auth.network_error") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title={t("onboarding.title")}>
      <form onSubmit={handle} noValidate className="space-y-4">
        <FormError message={errors.form} />
        <TextField
          name="name"
          label={t("onboarding.org_name")}
          help={t("onboarding.org_help")}
          required
          error={errors.name}
        />
        <div className="grid grid-cols-2 gap-3">
          <TextField
            name="country"
            label={t("onboarding.country")}
            help={t("onboarding.country_help")}
            maxLength={2}
            autoComplete="country"
            error={errors.country}
          />
          <TextField
            name="currency"
            label={t("onboarding.currency")}
            defaultValue="EUR"
            maxLength={3}
            error={errors.currency}
          />
        </div>
        <TextField
          name="project_name"
          label={t("onboarding.project_name")}
          required
          error={errors.project_name}
        />
        <TextField
          name="project_url"
          type="url"
          label={t("onboarding.project_url")}
          placeholder="https://"
          error={errors.project_url}
        />
        <SelectField
          name="project_kind"
          label={t("onboarding.project_kind")}
          help={t("onboarding.project_kind_help")}
          options={KINDS.map((k) => ({ value: k, label: t(`kind.${k}`) }))}
          error={errors.project_kind}
        />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? t("common.working") : t("onboarding.submit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
