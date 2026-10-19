import { describe, expect, it } from "vitest";

import { daysUntil, formatDuration, formatEvery, formatMetric, formatRelative } from "./format";

describe("format", () => {
  it("never turns unknown into zero", () => {
    expect(formatMetric(null)).toBe("—");
    expect(formatMetric(undefined, "ms")).toBe("—");
    expect(formatMetric(0)).toBe("0");
    expect(formatDuration(null)).toBe("—");
  });

  it("formats values with their unit", () => {
    expect(formatMetric(18734, "count")).toBe("18,734");
    expect(formatMetric(0.862, "ratio")).toBe("86.2%");
    expect(formatMetric(120, "ms")).toBe("120 ms");
    expect(formatDuration(42_000)).toBe("42 s");
    expect(formatEvery(86400)).toBe("every day");
    expect(formatEvery(300)).toBe("every 5 min");
  });

  it("is relative under a day and derives days left at read time", () => {
    const now = new Date("2026-10-18T09:00:00Z");
    expect(formatRelative("2026-10-18T08:48:00Z", now)).toBe("12 min ago");
    expect(formatRelative("2026-10-18T08:59:40Z", now)).toBe("just now");
    expect(formatRelative("2026-10-18T12:00:00Z", now)).toBe("in 3 h");
    expect(daysUntil("2026-10-28T10:00:00Z", now)).toBe(10);
  });
});
