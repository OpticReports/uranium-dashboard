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
  movers: (limit = 10) => req(`/views/movers?limit=${limit}`),
  deepDive: (symbol, days = 365) => req(`/views/deep-dive/${symbol}?days=${days}`),

  // Market
  refreshMarket: (symbol) =>
    req(`/market/refresh${symbol ? `?symbol=${symbol}` : ""}`, { method: "POST" }),
};
