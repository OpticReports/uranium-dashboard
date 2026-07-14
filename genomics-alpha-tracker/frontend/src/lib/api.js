// Thin REST client for the FastAPI backend.
// In dev, requests go through the Vite proxy (/api -> :8000). In prod set
// VITE_API_BASE to the backend origin.
// "/api" in dev (Vite proxy). For the single-service deploy, build with
// VITE_API_BASE="" so calls hit same-origin /universe, /scores, etc.
// (?? not || so an explicit empty string is respected.)
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => req("/health"),

  // Universe
  listUniverse: (includeInactive = true) =>
    req(`/universe?include_inactive=${includeInactive}`),
  subsectors: () => req("/universe/subsectors"),
  addTicker: (payload) =>
    req("/universe", { method: "POST", body: JSON.stringify(payload) }),
  updateTicker: (symbol, payload) =>
    req(`/universe/${symbol}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteTicker: (symbol) => req(`/universe/${symbol}`, { method: "DELETE" }),
  reloadUniverse: () => req("/universe/reload", { method: "POST" }),

  // Scores / flags
  scores: (activeOnly = true) => req(`/scores?active_only=${activeOnly}`),
  score: (symbol) => req(`/scores/${symbol}`),
  recompute: () => req("/scores/recompute", { method: "POST" }),
  flags: (days = 7) => req(`/flags?days=${days}`),

  // Catalysts
  catalysts: ({ days = 90, subsector, minImpact = 0 } = {}) => {
    const q = new URLSearchParams({ days, min_impact: minImpact });
    if (subsector) q.set("subsector", subsector);
    return req(`/catalysts?${q.toString()}`);
  },
  addCatalyst: (payload) =>
    req("/catalysts", { method: "POST", body: JSON.stringify(payload) }),
  updateCatalyst: (id, payload) =>
    req(`/catalysts/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  // Views
  heatmap: () => req("/views/heatmap"),
  treemap: () => req("/views/treemap"),
  movers: (limit = 10) => req(`/views/movers?limit=${limit}`),
  deepDive: (symbol, days = 365) => req(`/views/deep-dive/${symbol}?days=${days}`),
  today: () => req("/views/today"),
  regime: () => req("/views/regime"),

  // Signal track record (uncensored flag forward returns)
  flagTrackRecord: () => req("/flags/track-record"),

  // Decision journal (append-only)
  journal: (symbol) => req(`/journal${symbol ? `?symbol=${symbol}` : ""}`),
  addJournal: (payload) =>
    req("/journal", { method: "POST", body: JSON.stringify(payload) }),

  // Market
  refreshMarket: (symbol) =>
    req(`/market/refresh${symbol ? `?symbol=${symbol}` : ""}`, { method: "POST" }),

  // Chat analyst
  chatStatus: () => req("/chat/status"),
  chat: (payload) => req("/chat", { method: "POST", body: JSON.stringify(payload) }),

  // Trade calls (the tracker's own logged track record)
  calls: ({ status, symbol } = {}) => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (symbol) q.set("symbol", symbol);
    const qs = q.toString();
    return req(`/calls${qs ? `?${qs}` : ""}`);
  },
  callsScorecard: () => req("/calls/scorecard"),
  createCall: (payload) =>
    req("/calls", { method: "POST", body: JSON.stringify(payload) }),
  closeCall: (id, payload = {}) =>
    req(`/calls/${id}/close`, { method: "POST", body: JSON.stringify(payload) }),
  evaluateCalls: () => req("/calls/evaluate", { method: "POST" }),
  generateCalls: () => req("/calls/generate", { method: "POST" }),
};
