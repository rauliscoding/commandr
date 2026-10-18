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

/** Answer fetch() calls from a map of URL → JSON body. Unknown URLs are a test bug. */
export function mockFetch(routes: Record<string, unknown>): void {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!(url in routes)) throw new Error(`Unexpected fetch: ${url}`);
    return new Response(JSON.stringify(routes[url]), {
      status: 200,
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
