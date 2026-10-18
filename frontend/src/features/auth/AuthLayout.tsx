import type { ReactNode } from "react";

import { t } from "@/lib/i18n";

export function AuthLayout({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main id="main" className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-12">
      <div className="w-full max-w-sm">
        <p className="mb-8 text-center font-mono text-sm text-muted" aria-hidden="true">
          <span className="text-primary">&gt;_</span> Commandr
        </p>
        <div className="rounded-lg border border-border bg-surface p-6 shadow-raised">
          <h1 className="mb-1 text-xl font-semibold">{title}</h1>
          <p className="mb-6 text-sm text-muted">{t("auth.tagline")}</p>
          {children}
        </div>
        {footer ? <div className="mt-6 text-center text-sm text-muted">{footer}</div> : null}
      </div>
    </main>
  );
}
