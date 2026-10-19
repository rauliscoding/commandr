import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import axe from "axe-core";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";

/** Render a page at a route, with a fresh query client per test. */
export function renderAt(
  element: ReactElement,
  { path, url }: { path: string; url: string },
): RenderResult {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={path} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const REPLY = Symbol("reply");

interface Reply {
  [REPLY]: true;
  status: number;
  body: unknown;
}

/** A response with a status other than 200 (or no body). */
export function reply(status: number, body?: unknown): Reply {
  return { [REPLY]: true, status, body };
}

function isReply(value: unknown): value is Reply {
  return typeof value === "object" && value !== null && REPLY in value;
}

type Route = unknown | ((init: RequestInit | undefined) => unknown);

/**
 * Answer fetch() calls from a map of `"METHOD url"` (or just `url` for GET) →
 * JSON body, `reply(status, body)`, or a function of the request returning
 * either. Unknown URLs are a test bug. The CSRF bootstrap is answered for you.
 */
export function mockFetch(routes: Record<string, Route>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    if (url === "/api/csrf/") return new Response(null, { status: 204 });
    const route = routes[`${method} ${url}`] ?? (method === "GET" ? routes[url] : undefined);
    if (route === undefined) throw new Error(`Unexpected fetch: ${method} ${url}`);
    const value =
      typeof route === "function" ? (route as (i?: RequestInit) => unknown)(init) : route;
    const { status, body } = isReply(value) ? value : { status: 200, body: value };
    return new Response(status === 204 || body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

/**
 * Run axe on what is rendered. jsdom cannot compute colour contrast, so that
 * rule is checked with tokens (design-system.md) and in the Playwright suite.
 */
export async function axeViolations(container: Element = document.body): Promise<string[]> {
  const result = await axe.run(container, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
}
