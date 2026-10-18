import { describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./api";

describe("apiFetch", () => {
  it("sends the CSRF token on unsafe methods and uses the session cookie", async () => {
    document.cookie = "csrftoken=abc123";
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 201 }));
    await apiFetch("/api/organizations/", { method: "POST", body: { name: "x" } });
    const [, init] = fetchSpy.mock.calls[0]!;
    expect(init?.credentials).toBe("same-origin");
    expect((init?.headers as Record<string, string>)["X-CSRFToken"]).toBe("abc123");
  });

  it("turns DRF and allauth error shapes into field errors", () => {
    expect(new ApiError(400, { name: ["Give it a name."] }).fieldErrors()).toEqual({
      name: "Give it a name.",
    });
    expect(
      new ApiError(400, { errors: [{ param: "password", message: "Too short." }] }).fieldErrors(),
    ).toEqual({ password: "Too short." });
    expect(new ApiError(403, { detail: "No." }).fieldErrors()).toEqual({ form: "No." });
  });
});
