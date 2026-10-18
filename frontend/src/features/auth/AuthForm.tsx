import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/Button";
import { FormError, TextField } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import { PendingStepError } from "@/lib/auth";
import { t } from "@/lib/i18n";

/** Shared by sign-in and sign-up: same fields, different call and wording. */
export function AuthForm({
  submitLabel,
  passwordAutocomplete,
  passwordHelp,
  onSubmit,
}: {
  submitLabel: string;
  passwordAutocomplete: "current-password" | "new-password";
  passwordHelp?: string;
  onSubmit: (email: string, password: string) => Promise<void>;
}) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setErrors({});
    setNotice(undefined);
    try {
      await onSubmit(String(form.get("email")), String(form.get("password")));
      await queryClient.invalidateQueries();
      navigate("/", { replace: true });
    } catch (e) {
      if (e instanceof PendingStepError) {
        setNotice(e.step === "verify_email" ? t("auth.verify_email") : t("auth.mfa_pending"));
      } else if (e instanceof ApiError) {
        const fieldErrors = e.fieldErrors();
        setErrors(
          Object.keys(fieldErrors).length ? fieldErrors : { form: t("auth.generic_error") },
        );
        emailRef.current?.focus();
      } else {
        setErrors({ form: t("auth.network_error") });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handle} noValidate className="space-y-4">
      <FormError message={errors.form} />
      {notice ? (
        <div
          role="status"
          className="rounded-md border border-info-border bg-info-bg px-3 py-2 text-sm text-info-fg"
        >
          {notice}
        </div>
      ) : null}
      <TextField
        ref={emailRef}
        name="email"
        type="email"
        label={t("auth.email")}
        autoComplete="email"
        required
        error={errors.email}
      />
      <TextField
        name="password"
        type="password"
        label={t("auth.password")}
        autoComplete={passwordAutocomplete}
        help={passwordHelp}
        required
        error={errors.password}
      />
      <Button type="submit" className="w-full" disabled={busy}>
        {busy ? t("common.working") : submitLabel}
      </Button>
    </form>
  );
}
