import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { t } from "@/lib/i18n";

import { homePath, useMe, useSession } from "./session";

function Loading() {
  return (
    <p aria-busy="true" className="py-24 text-center text-muted">
      {t("common.loading")}
    </p>
  );
}

/** Signed-out visitors go to sign-in; everyone else sees the page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  if (session.isPending) return <Loading />;
  if (!session.data) return <Navigate to="/sign-in" replace />;
  return children;
}

/** Signed-in visitors skip the sign-in pages. */
export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const session = useSession();
  if (session.isPending) return <Loading />;
  if (session.data) return <Navigate to="/" replace />;
  return children;
}

/** `/` decides: sign in, onboarding, or the first project's catalogue. */
export function HomeRedirect() {
  const session = useSession();
  const me = useMe(Boolean(session.data));
  if (session.isPending || (session.data && me.isPending)) return <Loading />;
  if (!session.data) return <Navigate to="/sign-in" replace />;
  if (!me.data) return <Loading />;
  return <Navigate to={homePath(me.data)} replace />;
}
