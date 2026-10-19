/**
 * Formatting numbers and times for people. Unknown is "—", never 0
 * (CLAUDE.md invariant 5, design-system.md § Numbers are honest).
 */

export const UNKNOWN = "—";

const numberFormat = new Intl.NumberFormat("en", { maximumFractionDigits: 2 });

/** A metric value with its unit; `null`/`undefined` (not reported) is "—". */
export function formatMetric(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return UNKNOWN;
  if (unit === "ratio") return `${numberFormat.format(value * 100)}%`;
  const n = numberFormat.format(value);
  if (!unit || unit === "count") return n;
  return `${n} ${unit}`;
}

const absoluteFormat = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatAbsolute(iso: string): string {
  return absoluteFormat.format(new Date(iso));
}

/** "12 min ago" / "in 3 h" under a day; otherwise the absolute time. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const diff = new Date(iso).getTime() - now.getTime();
  const abs = Math.abs(diff);
  const past = diff <= 0;
  const minute = 60_000;
  const hour = 60 * minute;
  if (abs >= 24 * hour) return formatAbsolute(iso);
  let text: string;
  if (abs < minute) text = "less than a minute";
  else if (abs < hour) text = `${Math.round(abs / minute)} min`;
  else text = `${Math.round(abs / hour)} h`;
  if (text === "less than a minute") return past ? "just now" : "in under a minute";
  return past ? `${text} ago` : `in ${text}`;
}

/** Whole days from now until `iso` (derived at read time, never stored). */
export function daysUntil(iso: string, now: Date = new Date()): number {
  return Math.floor((new Date(iso).getTime() - now.getTime()) / 86_400_000);
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return UNKNOWN;
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 90) return `${numberFormat.format(s)} s`;
  return `${Math.round(s / 60)} min`;
}

export function formatEvery(seconds: number): string {
  if (seconds % 86400 === 0)
    return seconds === 86400 ? "every day" : `every ${seconds / 86400} days`;
  if (seconds % 3600 === 0) return seconds === 3600 ? "every hour" : `every ${seconds / 3600} h`;
  return seconds === 60 ? "every minute" : `every ${Math.round(seconds / 60)} min`;
}
