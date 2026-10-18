/** Every TanStack Query key comes from here, so invalidation is never a guess. */
export const queryKeys = {
  session: ["session"] as const,
  me: ["me"] as const,
  catalogue: (orgId: string, projectId: string) => ["catalogue", orgId, projectId] as const,
};
