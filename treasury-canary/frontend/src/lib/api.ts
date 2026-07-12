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
  informational: boolean;
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
  horizon_months?: number;
  ci_low_pct?: number | null;
  ci_high_pct?: number | null;
  auc?: number | null;
  n_obs?: number;
  fitted?: boolean;
}

export interface HorizonStat {
  probability_pct: number | null;
  ci_low_pct: number | null;
  ci_high_pct: number | null;
  auc: number | null;
  n_obs: number;
  n_pos: number;
  b0: number;
  b1: number;
}

export interface AdjustedHorizonStat {
  probability_pct: number | null;
  ci_low_pct: number | null;
  ci_high_pct: number | null;
  auc: number | null;
  n_obs: number;
}

export interface AdjustedModel {
  spread_minus_tp: number | null;
  acm_tp10: number | null;
  horizons: Record<string, AdjustedHorizonStat>;
  note: string;
}

export interface RecessionModel {
  spread_3m10y: number | null;
  default_horizon: number;
  horizons: Record<string, HorizonStat>;
  adjusted: AdjustedModel;
  spread_input: string;
  method: string;
  note: string;
}

export interface SahmPoint {
  date: string;
  value: number;
}

export interface SahmSeries {
  series: SahmPoint[];
  recessions: Recession[];
  trigger: number;
  current: number | null;
  triggered: boolean;
  source: string;
  note: string;
}

export interface FlowAsset {
  label: string;
  ret_pct?: number | null;
  chg_bps?: number | null;
  unit: string;
  role: string;
}

export interface FlowRegime {
  id: string;
  label: string;
  description: string;
  destinations: string[];
  severity: "INFO" | "WARN" | "RED" | "CRITICAL";
  inputs: Record<string, number | null>;
  missing_inputs: string[];
  window_days: number;
}

export interface FlowDestinations {
  window_days: number;
  assets: Record<string, FlowAsset>;
  regime: FlowRegime;
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

export type PinStatus = "GREEN" | "YELLOW" | "RED" | "STALE";

export interface PinPart {
  label: string;
  value: number | null;
  unit: string;
  status: string;
  detail: string;
}

export interface PinChannel {
  channel_id: string;
  label: string;
  status: PinStatus;
  parts: PinPart[];
  basis: string;
  certainty: string;
}

export interface PinBoard {
  channels: PinChannel[];
  overall: PinStatus;
  n_red: number;
  n_yellow: number;
  n_live: number;
  n_channels: number;
  framing: string;
}

export interface TrackRecordRow {
  asof: string;
  composite_score: number | null;
  composite_band: string | null;
  coverage: number | null;
  rec_prob_12m: number | null;
  rec_prob_adj_12m: number | null;
  curve_state: string | null;
  pins_overall: string | null;
  sahm: number | null;
  outcome_recession_12m: number | null;
}

export interface TrackRecord {
  rows: TrackRecordRow[];
  n_total: number;
  n_resolved: number;
  brier: number | null;
  brier_note: string;
  caveat: string;
}

export interface SeverityComponent {
  id: string;
  label: string;
  value: number | null;
  unit: string;
  score: number | null;
  note: string;
}

export interface SeverityBlock {
  id: string;
  label: string;
  score: number | null;
  components: SeverityComponent[];
}

export interface SeverityIndex {
  blocks: SeverityBlock[];
  severity_score: number | null;
  severity_class: "MILD" | "MODERATE" | "SEVERE" | null;
  formula: {
    base_amplifiers: number | null;
    policy_space_adj: number;
    dampener_adj: number;
    weights: Record<string, number>;
    text: string;
  };
  composition: {
    type_scores: Record<string, number | null>;
    matched_type: string | null;
  };
  note: string;
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
  recessionProb: (horizon?: number) =>
    getJson<RecessionProb>(
      horizon === undefined
        ? "/recession-prob"
        : `/recession-prob?horizon=${encodeURIComponent(horizon)}`,
    ),
  recessionModel: () => getJson<RecessionModel>("/recession-model"),
  laborSahm: () => getJson<SahmSeries>("/labor/sahm"),
  flowDestinations: () => getJson<FlowDestinations>("/flows/destinations"),
  curveCanary: (pair: string) =>
    getJson<CurveCanary>(`/curve/canary?pair=${encodeURIComponent(pair)}`),
  events: (limit = 100) => getJson<CanaryEvent[]>(`/events?limit=${limit}`),
  alerts: () => getJson<CanaryEvent[]>("/alerts"),
  news: (limit = 40) => getJson<NewsResponse>(`/news?limit=${limit}`),
  pins: () => getJson<PinBoard>("/pins"),
  trackRecord: () => getJson<TrackRecord>("/track-record"),
  severity: () => getJson<SeverityIndex>("/severity"),
  refresh: () =>
    getJson<unknown>("/refresh", { method: "POST" }),
};
