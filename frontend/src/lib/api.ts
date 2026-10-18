/**
 * The one way the SPA talks to the API.
 *
 * Same origin, session cookie, CSRF header on unsafe methods (ADR 0003). No
 * token is ever stored in JavaScript-readable storage.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly data: unknown;

  constructor(status: number, data: unknown, message?: string) {
    super(message ?? `Request failed with status ${status}`);
    this.status = status;
    this.data = data;
  }

  /** Field errors from DRF (`{field: [msg]}`) or allauth (`{errors: [{param, message}]}`). */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    const d = this.data as Record<string, unknown> | null;
    if (!d || typeof d !== "object") return out;
    if (Array.isArray(d.errors)) {
      for (const e of d.errors as { param?: string; message: string }[]) {
        out[e.param ?? "form"] ??= e.message;
      }
      return out;
    }
    for (const [key, value] of Object.entries(d)) {
      if (Array.isArray(value) && typeof value[0] === "string") out[key] = value[0];
      else if (typeof value === "string") out[key === "detail" ? "form" : key] = value;
    }
    return out;
  }
}

const CSRF_COOKIES = ["__Host-csrftoken", "csrftoken"];

export function csrfToken(): string | undefined {
  const cookies = Object.fromEntries(
    document.cookie
      .split(";")
      .map((c) => c.trim().split("="))
      .filter((pair): pair is [string, string] => pair.length === 2)
      .map(([k, v]) => [k, decodeURIComponent(v)]),
  );
  for (const name of CSRF_COOKIES) if (cookies[name]) return cookies[name];
  return undefined;
}

let csrfReady: Promise<void> | null = null;

/** Make sure Django has set the CSRF cookie before the first unsafe request. */
export function ensureCsrf(): Promise<void> {
  if (csrfToken()) return Promise.resolve();
  csrfReady ??= fetch("/api/csrf/", { credentials: "same-origin" }).then(() => undefined);
  return csrfReady;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function apiFetch<T>(
  path: string,
  { method = "GET", body }: { method?: Method; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    await ensureCsrf();
    const token = csrfToken();
    if (token) headers["X-CSRFToken"] = token;
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}
