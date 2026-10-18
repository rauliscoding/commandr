import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Home,
  KanbanSquare,
  LogOut,
  Mail,
  Menu,
  Plug,
  Settings,
  Share2,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router";

import { signOut } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { t, type MessageKey } from "@/lib/i18n";

import { useMe } from "./session";

const SOURCE_URL = "https://github.com/rauliscoding/commandr";

const NAV: { to: string; key: MessageKey; icon: LucideIcon }[] = [
  { to: "home", key: "nav.home", icon: Home },
  { to: "health", key: "nav.health", icon: Activity },
  { to: "social", key: "nav.social", icon: Share2 },
  { to: "email", key: "nav.email", icon: Mail },
  { to: "analytics", key: "nav.analytics", icon: BarChart3 },
  { to: "money", key: "nav.money", icon: Wallet },
  { to: "board", key: "nav.board", icon: KanbanSquare },
  { to: "integrations", key: "nav.integrations", icon: Plug },
  { to: "settings", key: "nav.settings", icon: Settings },
];

export function AppShell() {
  const { orgId, projectId } = useParams();
  const { data: me } = useMe();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const org = me?.organizations.find((o) => o.id === orgId);
  const project = org?.projects.find((p) => p.id === projectId);
  const base = `/o/${orgId}/p/${projectId}`;

  async function handleSignOut() {
    await signOut();
    queryClient.clear();
    navigate("/sign-in", { replace: true });
  }

  const nav = (
    <>
      <nav aria-label={t("nav.label")}>
        <ul className="space-y-0.5">
          {NAV.map(({ to, key, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={`${base}/${to}`}
                onClick={() => setDrawerOpen(false)}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-10 items-center gap-3 rounded-md px-3 text-sm",
                    isActive
                      ? "bg-primary-soft font-medium text-fg"
                      : "text-muted hover:bg-surface-sunken hover:text-fg",
                  )
                }
              >
                <Icon aria-hidden="true" className="size-4" />
                {t(key)}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {/* AGPL-3.0 section 13: users of the hosted service can get its source. */}
      <a
        href={SOURCE_URL}
        target="_blank"
        rel="noreferrer"
        className="mt-6 block px-3 text-xs text-muted underline hover:text-fg"
      >
        {t("nav.source")}
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    </>
  );

  return (
    <div className="min-h-dvh bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        {t("nav.skip")}
      </a>

      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface px-4">
        <button
          type="button"
          className="inline-flex size-9 items-center justify-center rounded-md hover:bg-surface-sunken lg:hidden"
          aria-label={drawerOpen ? t("nav.close_menu") : t("nav.open_menu")}
          aria-expanded={drawerOpen}
          aria-controls="mobile-nav"
          onClick={() => setDrawerOpen((v) => !v)}
        >
          {drawerOpen ? (
            <X aria-hidden="true" className="size-5" />
          ) : (
            <Menu aria-hidden="true" className="size-5" />
          )}
        </button>
        <span className="font-mono text-sm font-medium">
          <span className="text-primary" aria-hidden="true">
            &gt;_
          </span>{" "}
          Commandr
        </span>
        <span className="hidden text-border-strong sm:inline" aria-hidden="true">
          /
        </span>
        <span className="hidden min-w-0 truncate text-sm text-muted sm:inline">
          {org?.name}
          {project ? <> · {project.name}</> : null}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-sm text-muted md:inline">{me?.user.email}</span>
          <button
            type="button"
            onClick={handleSignOut}
            className="inline-flex min-h-9 items-center gap-2 rounded-md px-3 text-sm text-muted hover:bg-surface-sunken hover:text-fg"
          >
            <LogOut aria-hidden="true" className="size-4" />
            {t("nav.sign_out")}
          </button>
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-56 shrink-0 overflow-y-auto border-r border-border bg-surface p-3 lg:block">
          {nav}
        </aside>
        {drawerOpen ? (
          <div
            id="mobile-nav"
            className="fixed inset-x-0 top-14 bottom-0 z-20 overflow-y-auto bg-surface p-3 lg:hidden"
          >
            {nav}
          </div>
        ) : null}
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
