// Display helpers. Crucially, null is rendered as "n/a" (no data) — never 0 —
// to preserve the no-data-vs-zero distinction the backend is careful about.

export const naIfNull = (v, fmt = (x) => x) =>
  v === null || v === undefined ? "n/a" : fmt(v);

export const fmtNum = (v, dp = 1) =>
  v === null || v === undefined ? "n/a" : Number(v).toFixed(dp);

export const fmtPct = (v, dp = 1) =>
  v === null || v === undefined ? "n/a" : `${(Number(v) * 100).toFixed(dp)}%`;

export const fmtMoney = (v) => {
  if (v === null || v === undefined) return "n/a";
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
};

// Composite 0-100 -> color. Diverging red(low)->amber(mid)->green(high).
export function scoreColor(v) {
  if (v === null || v === undefined) return "#374151"; // gray = no data
  const t = Math.max(0, Math.min(100, v)) / 100;
  const r = t < 0.5 ? 220 : Math.round(220 - (t - 0.5) * 2 * 180);
  const g = t < 0.5 ? Math.round(t * 2 * 190) : 190;
  return `rgb(${r}, ${g}, 70)`;
}

// Composite is stored 0-100 (cross-sectional vs the universe) but displayed
// as 0-10 with one decimal — the desk's preferred granularity. Render-layer
// conversion ONLY: configs, APIs and stored values stay 0-100.
export const fmtScore10 = (v) =>
  v === null || v === undefined ? "n/a" : (Number(v) / 10).toFixed(1);

export const severityColor = {
  high: "bg-emerald-600/20 text-emerald-300 border-emerald-700",
  warn: "bg-amber-600/20 text-amber-300 border-amber-700",
  info: "bg-sky-600/20 text-sky-300 border-sky-700",
};

// Catalyst event codes -> plain English. Never show a raw code to the desk.
export const EVENT_LABELS = {
  pdufa: "FDA decision (PDUFA)",
  adcom: "FDA advisory committee",
  phase3_readout: "Phase 3 trial results",
  phase2_readout: "Phase 2 trial results",
  phase1_readout: "Phase 1 trial results",
  data_presentation: "Data presentation (medical conference)",
  earnings: "Earnings report",
  conference: "Investor conference",
  other: "Corporate event",
};

export const eventLabel = (t) =>
  t ? EVENT_LABELS[t] || t.replace(/_/g, " ") : "event";

export const FLAG_LABELS = {
  pre_catalyst_sentiment_ramp: "Pre-catalyst sentiment ramp",
  analyst_revision_cluster: "Analyst revision cluster",
  unusual_options_social_spike: "Unusual options + social spike",
  runway_cliff_approaching: "Runway cliff approaching",
  binary_event_within_n_days: "Binary event imminent",
  pullback_into_catalyst: "Pullback into catalyst",
  volume_anomaly: "Volume anomaly",
  insider_buying_cluster: "Insider buying cluster",
};
