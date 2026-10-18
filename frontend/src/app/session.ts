import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { queryKeys } from "@/lib/queryKeys";

export interface MeProject {
  id: string;
  name: string;
  kind: string;
}

export interface MeOrganization {
  id: string;
  name: string;
  role: "owner" | "admin" | "member" | "viewer";
  projects: MeProject[];
}

export interface Me {
  user: { id: string; email: string; display_name: string };
  organizations: MeOrganization[];
}

export function useSession() {
  return useQuery({ queryKey: queryKeys.session, queryFn: getSession, staleTime: 60_000 });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => apiFetch<Me>("/api/me/"),
    enabled,
    staleTime: 30_000,
  });
}

/** Where a signed-in person should land: their first project, or onboarding. */
export function homePath(me: Me): string {
  const org = me.organizations[0];
  const project = org?.projects[0];
  if (!org || !project) return "/onboarding";
  return `/o/${org.id}/p/${project.id}/integrations`;
}
