import type { MetricStatus, EventSeverity } from "./api";

const DISPLAY_TZ = "America/Puerto_Rico";

// Traffic-light hex colors.
export const STATUS_COLOR: Record<MetricStatus, string> = {
  GREEN: "#10b981",
  YELLOW: "#f59e0b",
  RED: "#ef4444",
  CRITICAL: "#dc2626",
  STALE: "#6b7280",
};

export const SEVERITY_COLOR: Record<EventSeverity, string> = {
  INFO: "#6b7280",
  WARN: "#f59e0b",
  RED: "#ef4444",
  CRITICAL: "#dc2626",
};

// Format a metric value with its unit; null -> "n/a".
export function formatValue(value: number | null, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const abs = Math.abs(value);
  let digits = 2;
  if (abs >= 1000) digits = 0;
  else if (abs >= 100) digits = 1;
  else if (abs < 1) digits = 3;
  const num = value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const u = unit?.trim() ?? "";
  if (u === "%" || u === "bps" || u === "$") return `${num}${u === "$" ? "" : ""}${u}`;
  return u ? `${num} ${u}` : num;
}

// Signed formatting for deltas.
export function formatDelta(value: number | null, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const digits = Math.abs(value) < 1 ? 3 : 2;
  const sign = value > 0 ? "+" : "";
  const num = value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const u = unit?.trim() ?? "";
  return `${sign}${num}${u && u !== "$" ? ` ${u}` : ""}`;
}

export function deltaColor(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "#6b7280";
  if (value > 0) return "#10b981";
  if (value < 0) return "#ef4444";
  return "#94a3b8";
}

export function formatPercentile(p: number | null): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "n/a";
  const v = p <= 1 ? p * 100 : p;
  return `${v.toFixed(0)}%`;
}

// Render a UTC ISO timestamp as a date+time in the display timezone.
export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: DISPLAY_TZ,
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

// Render a date-only string as-is (dates alone need no tz shift).
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  // If it already looks like a plain date, pass through.
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/;
  if (dateOnly.test(iso)) return iso;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

// mm/yyyy for compact episode callouts.
export function formatMonthYear(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${mm}/${d.getUTCFullYear()}`;
}

export function median(values: number[]): number | null {
  const nums = values.filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (nums.length === 0) return null;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

export const errorMessage = (err: unknown): string =>
  err instanceof Error ? err.message : "Unknown error";
