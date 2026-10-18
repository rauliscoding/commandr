import { Link } from "react-router";

import { signUp } from "@/lib/auth";
import { t } from "@/lib/i18n";

import { AuthForm } from "./AuthForm";
import { AuthLayout } from "./AuthLayout";

export function SignUpPage() {
  return (
    <AuthLayout
      title={t("auth.sign_up_title")}
      footer={
        <>
          {t("auth.have_account")}{" "}
          <Link className="font-medium text-link underline" to="/sign-in">
            {t("auth.sign_in")}
          </Link>
        </>
      }
    >
      <AuthForm
        submitLabel={t("auth.create_account")}
        passwordAutocomplete="new-password"
        passwordHelp={t("auth.password_help")}
        onSubmit={signUp}
      />
    </AuthLayout>
  );
}
