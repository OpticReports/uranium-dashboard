import type { Health } from "./api";

// The header's FRED dot (2026-11-21). Amber while a keyed FRED API call has failed within the last
// hour with no good fetch since: the series is served from its last good copy, or (past the 72 h cap,
// or never cached) not served at all. The keyless fredgraph CSV path (Dollar, AI-debt, GDP and other
// tabs) does not feed this dot; those tabs show their own staleness.

const MAX_ROWS = 5;   // an outage fails every series at once: name a few, count the rest

export function fredDotWarn(h: Health): boolean {
  return Object.keys(h.fred_stale_series ?? {}).length > 0 || Object.keys(h.fred_failing_series ?? {}).length > 0;
}

/** hover text: a rejected key, then the failing series and what each is served from */
export function fredDotTitle(h: Health): string | undefined {
  if (h.fred_key_error) return `FRED rejected the API key: ${h.fred_key_error}`;
  const failing = Object.entries(h.fred_failing_series ?? {});
  const stale = h.fred_stale_series ?? {};
  if (!failing.length && !Object.keys(stale).length) return undefined;
  const rows = (failing.length ? failing : Object.keys(stale).map((s) => [s, 0] as [string, number]))
    .map(([s, hrs]) => `${s}${hrs ? ` failing ${hrs} h` : ""}: ${s in stale ? `last good copy (${stale[s]} h old)` : "no usable copy, STALE"}`);
  const more = rows.length > MAX_ROWS ? `; and ${rows.length - MAX_ROWS} more` : "";
  return `FRED calls failing (${rows.length}): ${rows.slice(0, MAX_ROWS).join("; ")}${more}`;
}
