// Typed fetch client for the Treasury Canary backend.
// All endpoints are same-origin; VITE_API_BASE can override for non-proxied deploys.

const BASE = import.meta.env.VITE_API_BASE ?? "";

// ---------------------------------------------------------------------------
// Shared enums / literals
// ---------------------------------------------------------------------------

export type MetricStatus = "GREEN" | "YELLOW" | "RED" | "CRITICAL" | "STALE";
export type CompositeBand = "LOW" | "ELEVATED" | "HIGH" | "SEVERE" | "NO_DATA";
export type EventSeverity = "INFO" | "WARN" | "RED" | "CRITICAL";
export type CurveState = "NORMAL" | "INVERTED" | "RE_STEEPENING" | null;
export type NewsTag = "FED" | "AUCTION" | "DATA" | "GEO" | "OTHER";

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

export interface Health {
  status: string;
  service: string;
  fred_key_present: boolean;
  scheduler: boolean;
  display_tz: string;
}

export interface Metric {
  metric_id: string;
  category: string;
  label: string;
  value: number | null;
  status: MetricStatus;
  asof: string | null;
  unit: string;
  delta_1d: number | null;
  delta_5d: number | null;
  delta_20d: number | null;
  percentile: number | null;
  note: string;
  source_series: string;
  extra: Record<string, unknown>;
}

export interface Composite {
  score: number | null;
  band: CompositeBand;
  coverage: number;
  category_scores: Record<string, number>;
  contributions: Record<string, number>;
  n_red: number;
  n_critical: number;
}

export type Categories = Record<string, string>;

export interface MetricsResponse {
  categories: Categories;
  metrics: Metric[];
  composite: Composite;
}

export interface HistoryPoint {
  asof: string;
  value: number | null;
  status: string;
  percentile: number | null;
}

export interface RecessionProb {
  spread_3m10y: number | null;
  probability_pct: number | null;
  model: string;
}

export interface CurveSeriesPoint {
  date: string;
  spread: number;
}

export interface CurveEpisode {
  start: string;
  trough: string;
  max_depth_bps: number;
  days_inverted: number;
  sustained: boolean;
  dis_inversion: string | null;
  lag_to_recession_months: number | null;
}

export interface Recession {
  start: string;
  end: string;
}

export interface CurveCanary {
  pair: string;
  state: CurveState;
  current_value: number | null;
  current_depth_bps: number | null;
  days_inverted: number;
  dis_inversion_date: string | null;
  last_change: string | null;
  recession_probability_pct: number | null;
  series: CurveSeriesPoint[];
  episodes: CurveEpisode[];
  recessions: Recession[];
  available_pairs: string[];
  error?: string;
}

export interface CanaryEvent {
  id: number;
  type: string;
  severity: EventSeverity;
  asof: string;
  rationale: string;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface NewsItem {
  source: string;
  title: string;
  link: string;
  published: string | null;
  tag: NewsTag;
}

export interface NewsResponse {
  items: NewsItem[];
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Free-tier hosting spins the service down after idle; the waking request 502/503s
// for ~20s while the container boots. Retry those (and transient network errors) so
// a cold start looks like a slow load, not an error.
const RETRY_STATUSES = new Set([502, 503, 504]);
const MAX_RETRIES = 4;

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  let lastErr = new ApiError("unknown error", 0);
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let res: Response;
    try {
      res = await fetch(`${BASE}${path}`, { headers: { Accept: "application/json" }, ...init });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "network error";
      lastErr = new ApiError(`Request failed: ${msg}`, 0);
      if (attempt < MAX_RETRIES) { await sleep(2000 * (attempt + 1)); continue; }
      throw lastErr;
    }
    if (res.ok) {
      try {
        return (await res.json()) as T;
      } catch {
        throw new ApiError(`Malformed JSON from ${path}`, res.status);
      }
    }
    lastErr = new ApiError(`HTTP ${res.status} for ${path}`, res.status);
    if (RETRY_STATUSES.has(res.status) && attempt < MAX_RETRIES) {
      await sleep(3000 * (attempt + 1)); // 3s, 6s, 9s, 12s — covers a cold boot
      continue;
    }
    throw lastErr;
  }
  throw lastErr;
}

// ---------------------------------------------------------------------------
// Endpoint bindings
// ---------------------------------------------------------------------------

export const api = {
  health: () => getJson<Health>("/health"),
  metrics: () => getJson<MetricsResponse>("/metrics"),
  metricHistory: (metricId: string) =>
    getJson<HistoryPoint[]>(`/metrics/${encodeURIComponent(metricId)}/history`),
  composite: () => getJson<Composite>("/composite"),
  recessionProb: () => getJson<RecessionProb>("/recession-prob"),
  curveCanary: (pair: string) =>
    getJson<CurveCanary>(`/curve/canary?pair=${encodeURIComponent(pair)}`),
  events: (limit = 100) => getJson<CanaryEvent[]>(`/events?limit=${limit}`),
  alerts: () => getJson<CanaryEvent[]>("/alerts"),
  news: (limit = 40) => getJson<NewsResponse>(`/news?limit=${limit}`),
  refresh: () =>
    getJson<unknown>("/refresh", { method: "POST" }),
};
