/** django-allauth headless, browser client (session cookies). */
import { ApiError, apiFetch } from "./api";

const BASE = "/api/auth/browser/v1";

export interface SessionUser {
  id: string;
  email: string;
  display: string;
}

/** allauth answers 401 when signed out; that is a normal state, not an error. */
export async function getSession(): Promise<SessionUser | null> {
  try {
    const res = await apiFetch<{ data: { user: SessionUser } }>(`${BASE}/auth/session`);
    return res.data.user;
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 410)) return null;
    throw e;
  }
}

/**
 * allauth also answers 401 from login/signup when the account needs another
 * step (verify email, MFA). Phase 0 surfaces that as a message; the MFA step UI
 * comes with the account settings work.
 */
async function authStep(path: string, body: Record<string, string>): Promise<void> {
  try {
    await apiFetch(`${BASE}${path}`, { method: "POST", body });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      const flows = (e.data as { data?: { flows?: { id: string; is_pending?: boolean }[] } })?.data
        ?.flows;
      const pending = flows?.find((f) => f.is_pending)?.id;
      if (pending === "verify_email") throw new PendingStepError("verify_email");
      if (pending === "mfa_authenticate") throw new PendingStepError("mfa_authenticate");
    }
    throw e;
  }
}

export class PendingStepError extends Error {
  readonly step: "verify_email" | "mfa_authenticate";
  constructor(step: "verify_email" | "mfa_authenticate") {
    super(step);
    this.step = step;
  }
}

export const signIn = (email: string, password: string) =>
  authStep("/auth/login", { email, password });

export const signUp = (email: string, password: string) =>
  authStep("/auth/signup", { email, password });

export async function signOut(): Promise<void> {
  try {
    await apiFetch(`${BASE}/auth/session`, { method: "DELETE" });
  } catch (e) {
    // allauth answers 401 once the session is gone — which is the goal.
    if (!(e instanceof ApiError && e.status === 401)) throw e;
  }
}
