/** Every TanStack Query key comes from here, so invalidation is never a guess. */
export const queryKeys = {
  session: ["session"] as const,
  me: ["me"] as const,
  catalogue: (orgId: string, projectId: string) => ["catalogue", orgId, projectId] as const,
  connections: (orgId: string, projectId: string) => ["connections", orgId, projectId] as const,
  firstData: (orgId: string, projectId: string, connectionId: string) =>
    ["first-data", orgId, projectId, connectionId] as const,
  health: (orgId: string, projectId: string) => ["health", orgId, projectId] as const,
};

/** The API prefix for one project. */
export const projectApi = (orgId: string, projectId: string) =>
  `/api/orgs/${orgId}/projects/${projectId}`;
