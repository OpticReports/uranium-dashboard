import type { Health } from "./api";

// The header's FRED dot (2026-11-21). Amber whenever a FRED call is failing: served from the last good
// copy, or (past the 72 h cap, or never cached) not served at all. Green only when nothing is failing.

export function fredDotWarn(h: Health): boolean {
  return Object.keys(h.fred_stale_series ?? {}).length > 0 || Object.keys(h.fred_failing_series ?? {}).length > 0;
}

/** hover text: a rejected key, then each failing series and what it is served from */
export function fredDotTitle(h: Health): string | undefined {
  if (h.fred_key_error) return `FRED rejected the API key: ${h.fred_key_error}`;
  const failing = Object.entries(h.fred_failing_series ?? {});
  const stale = h.fred_stale_series ?? {};
  if (!failing.length && !Object.keys(stale).length) return undefined;
  const rows = (failing.length ? failing : Object.keys(stale).map((s) => [s, 0] as [string, number]))
    .map(([s, hrs]) => `${s}${hrs ? ` failing ${hrs} h` : ""}: ${s in stale ? `last good copy (${stale[s]} h old)` : "no usable copy, STALE"}`);
  return `FRED calls failing: ${rows.join("; ")}`;
}
