import { Link } from "react-router";

import { signIn } from "@/lib/auth";
import { t } from "@/lib/i18n";

import { AuthForm } from "./AuthForm";
import { AuthLayout } from "./AuthLayout";

export function SignInPage() {
  return (
    <AuthLayout
      title={t("auth.sign_in_title")}
      footer={
        <>
          {t("auth.no_account")}{" "}
          <Link className="font-medium text-link underline" to="/sign-up">
            {t("auth.create_account")}
          </Link>
        </>
      }
    >
      <AuthForm
        submitLabel={t("auth.sign_in")}
        passwordAutocomplete="current-password"
        onSubmit={signIn}
      />
    </AuthLayout>
  );
}
