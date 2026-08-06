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

export interface WeightEnsemble {
  band_low: number;
  band_high: number;
  equal_weight_score: number | null;
  n_draws: number;
  spread: number;
  driver_category: string | null;
  driver_direction: "raises" | "lowers" | null;
  note: string;
}

export interface Composite {
  score: number | null;
  band: CompositeBand;
  coverage: number;
  category_scores: Record<string, number>;
  contributions: Record<string, number>;
  n_red: number;
  n_critical: number;
  ensemble?: WeightEnsemble | null;
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

export interface TransmissionNote {
  active: boolean;
  fast_red_channels: string[];
  prob_12m_pct: number | null;
  prob_threshold_pct: number;
  message: string;
}

export interface RecessionModel {
  spread_3m10y: number | null;
  default_horizon: number;
  horizons: Record<string, HorizonStat>;
  transmission?: TransmissionNote;
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
  score: number | null;
}

export interface PinChannel {
  channel_id: string;
  label: string;
  status: PinStatus;
  parts: PinPart[];
  basis: string;
  certainty: string;
  mass: string;
  speed: string;
  kill_rate: string;
  score: number | null;
  mass_trillions: number | null;
  leverage: string;
}

export interface PinAccidentGauge {
  status: "GREEN" | "YELLOW" | "RED" | "STALE";
  fast_red: boolean | null; // null = no fast channel reporting (unknown)
  fast_red_channels: string[];
  curve_flat: boolean | null; // null = no fresh curve tape (unknown)
  unknown: string[];
  curve_threshold_pp: number;
  spread_3m10y_now: number | null;
  spread_3m10y_min_6m: number | null;
  basis: string;
}

export interface PinExposure {
  red_trillions: number;
  yellow_trillions: number;
  green_trillions: number;
  monitored_trillions: number;
  unsized: string[];
  note: string;
}

export interface PinBoard {
  channels: PinChannel[];
  exposure?: PinExposure;
  accident_gauge?: PinAccidentGauge;
  overall: PinStatus;
  n_red: number;
  n_yellow: number;
  n_live: number;
  n_channels: number;
  pressure: number | null;
  hottest: { channel_id: string; label: string; score: number } | null;
  framing: string;
}

export interface PinHistoryEpisode {
  start: string;
  end: string;
  peak_date: string;
  peak_score: number;
  window_start: string;
  window_end: string;
  outcome?: "hit_recession" | "hit_drawdown" | "miss" | "open";
}

export interface PinHistoryChannel {
  channel_id: string;
  lag_months: [number, number];
  lag_basis: string;
  series: { date: string; score: number }[];
  episodes: PinHistoryEpisode[];
  note: string | null;
  outcomes?: { hit: number; miss: number; open: number } | null;
}

export interface PinCollectivePoint {
  date: string;
  n_red: number | null;
  pressure: number | null;
  windows_open: number;
  window_channels: string[];
  projected: boolean;
}

export interface PinOverlapValidation {
  n_months: number;
  n_onsets_covered: number;
  base_rate: number;
  horizon_months: number;
  thresholds: { k: number; n_months: number; hit_rate: number }[];
}

export interface PinConfluence {
  open_now: number;
  channels_now: string[];
  peak_ahead: number;
  peak_window: [string, string] | null;
  peak_channels: string[];
  validation: PinOverlapValidation | null;
  caveat: string;
}

export interface RecessionSpan {
  start: string;
  end: string;
}

export interface DrawdownSpan {
  start: string;
  trough: string;
  depth_pct: number;
}

export interface PinHistory {
  channels: PinHistoryChannel[];
  collective: { series: PinCollectivePoint[]; last_data_month: string | null };
  confluence: PinConfluence | null;
  recessions: RecessionSpan[];
  drawdowns: DrawdownSpan[];
  framing?: string;
  measured_roles?: string;
}

export interface StatRegimeCurrent {
  state: "CALM" | "ELEVATED" | "STRESS";
  direction: "selloff" | "rally" | "";
  confidence: number;
  asof: string;
  n_obs: number;
}

export interface StatRegimeMonth {
  month: string;
  state: "CALM" | "ELEV" | "STRESS";
  dir: string;
  conf: number;
}

export interface StatRegime {
  current: StatRegimeCurrent | null;
  hindcast: StatRegimeMonth[];
  validated: string;
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

export type LeverageState =
  | "BLOWOFF"
  | "ELEVATED"
  | "NEUTRAL"
  | "SQUEEZE"
  | "WASHOUT";

export interface MarginPoint {
  date: string;
  margin_yoy: number | null;
  excess_yoy: number | null;
  coverage: number | null;
  spx: number | null;
  btc: number | null;
  spx_idx: number | null;
  btc_idx: number | null;
}

export interface LeverageStats {
  n: number;
  mean: number;
  median: number;
  pct_lower: number;
  worst: number;
}

export interface LeveragePlaybookEntry {
  label: string;
  evidence?: string;
  stats: { fwd3: LeverageStats; fwd6: LeverageStats; fwd12: LeverageStats };
  read: string;
  action: string;
}

export interface LeverageCorroboration {
  flags: Record<string, boolean | null>;
  n_true: number;
  n_known: number;
  values: Record<string, number | null>;
  stats: Record<string, { label: string; bears: number; n: number; prob_note: string }>;
  reading: string;
}

export interface MarginNowcastMonth {
  month: string;
  margin_bn: number;
  basis: string;
  yoy_pct?: number;
  excess_pp?: number;
  band_pp?: number;
  state_est?: LeverageState;
  near_boundary?: boolean;
  partial_month?: boolean;
}

export interface MarginNowcast {
  months: MarginNowcastMonth[];
  last_print: string;
  schwab: { latest_month: string; margin_bn: number; yoy_pct: number | null } | null;
  backtest: Record<string, string | number>;
  display_only: string;
}

export interface MarginLeverage {
  series: MarginPoint[];
  nowcast?: MarginNowcast | null;
  corroboration?: LeverageCorroboration;
  recessions: Array<{ start: string; end: string }>;
  current: {
    date: string | null;
    margin_yoy: number | null;
    excess_yoy: number | null;
    coverage: number | null;
    state: LeverageState | null;
  };
  playbook: Record<LeverageState, LeveragePlaybookEntry>;
  thresholds: Record<string, number>;
  source: string;
  note: string;
}

export type FastLeverageState = "FLUSH" | "WASHED_OUT" | "RISK_BUILD" | "CALM";

export interface FastStats {
  n: number;
  median: number;
  pct_pos: number;
  worst: number;
}

export interface FastPlaybookEntry {
  label: string;
  evidence?: string;
  stats: { fwd1m: FastStats; fwd3m: FastStats; fwd12m: FastStats };
  episodes: number;
  read: string;
  action: string;
}

export type StressState = "SHOCK" | "AFTERSHOCK" | "COMPLACENT" | "NORMAL";

export interface DeepCell {
  n: number;
  episodes: number;
  evidence?: string;
  fwd3m: { median: number; pct_pos: number; worst: number };
  fwd12m: { median: number; pct_pos: number; worst: number };
}

export interface MarginFastDeep {
  live: {
    state: StressState;
    rvol: number;
    vz: number;
    dv20: number;
    date: string;
  } | null;
  states: Record<
    StressState,
    {
      label: string;
      episodes: number;
      fwd1m: { median: number; pct_pos: number; worst: number };
      fwd12m: { median: number; pct_pos: number; worst: number };
    }
  >;
  matrix: Record<StressState, Record<LeverageState, DeepCell>>;
  baseline: {
    n: number;
    fwd1m: { median: number; pct_pos: number };
    fwd3m: { median: number; pct_pos: number };
    fwd12m: { median: number; pct_pos: number };
  };
  thresholds: Record<string, number>;
  note: string;
}

export interface MarginFast {
  state: FastLeverageState | null;
  state_series: Array<{ date: string; state: FastLeverageState }>;
  playbook: Record<FastLeverageState, FastPlaybookEntry>;
  cross_read: Record<FastLeverageState, Record<LeverageState, string>>;
  deep: MarginFastDeep;
  relationship: string;
  thresholds: Record<string, number>;
  cot: {
    series: Array<{ date: string; pct: number; z: number | null }>;
    z: number | null;
    dz4: number | null;
    pct: number | null;
    date: string | null;
    cadence: string;
  };
  vix: {
    series: Array<{ date: string; vix: number; z: number | null }>;
    d20: number | null;
    current: number | null;
    date: string | null;
    cadence: string;
  };
  hy: {
    series: Array<{ date: string; bp: number; z: number | null }>;
    d20_bp: number | null;
    current_bp: number | null;
    date: string | null;
    cadence: string;
  };
  btc: {
    perp: {
      mark_price: number;
      oi_usd: number;
      funding_8h: number;
      funding_ann_pct: number;
    } | null;
    funding_series: Array<{ date: string; ann_pct: number; z: number | null }>;
    oi_series: Array<{ date: string; oi_usd: number | null }>;
    cadence: string;
  };
  baseline: Record<string, { median: number; pct_pos: number }>;
  note: string;
}

export type RateShockState = "SPIKE" | "PLUNGE" | "NEUTRAL";
export type CorrRegime = "POS" | "MIXED" | "NEG";

export interface RateShockCell {
  n: number;
  episodes: number;
  rec_12m_pct: number;
  fwd12m: { median: number; pct_pos: number; worst: number };
  evidence: string;
}

export interface RateShock {
  current: {
    yield_30y: number | null;
    d60_bp: number | null;
    state: RateShockState | null;
    corr: number | null;
    regime: CorrRegime | null;
    date: string | null;
  };
  cell: RateShockCell | null;
  summary: string[];
  series: Array<{ date: string; yield: number; d60_bp: number | null }>;
  baseline: {
    n: number;
    rec_12m_pct: number;
    fwd12m: { median: number; pct_pos: number; worst: number };
  };
  shock_stats: Record<RateShockState, RateShockCell & { label: string }>;
  matrix: Record<RateShockState, Record<CorrRegime, RateShockCell>>;
  thresholds: Record<string, number>;
  note: string;
}

export interface ShockScenarios {
  span: [number, number];
  meetings: Array<{ date: string; idx: number }>;
  implied: Record<string, number>;
  live_inputs: Record<string, number | null>;
  note: string;
}

export type ShockAsset = "SPX" | "QQQ" | "SOXX" | "HYG";

export interface ShockRun {
  months: string[];
  bands: Record<ShockAsset, Record<"5" | "25" | "50" | "75" | "95", number[]>>;
  probs: Record<ShockAsset, { dd_gt_10: number; dd_gt_20: number; dd_gt_10_touch_est: number; dd_gt_20_touch_est: number; basis: string }>;
  terminal: Record<ShockAsset, { counts: number[]; edges: number[] }>;
  stress_prob: number[];
  rate_path: {
    implied_bp: number[];
    scenario_bp: number[];
    cum_surprise_bp: number[];
    dy10_pp: number[];
  };
  meta: {
    kappa_used: number;
    seed: number;
    n_paths: number;
    canary01: number;
    oas0: number;
    hikes: number;
    params_used: Record<string, number>;
    override_warnings: string[];
  };
}

export interface ShockCalibration {
  params: Record<
    string,
    { default: number; range: [number, number]; source: string; note: string; high_sensitivity?: boolean }
  >;
  amendments: string[];
  estimation_windows: Record<string, string>;
  epistemic_note: string;
}

export interface CorrPoint {
  date: string;
  corr: number;
}

export interface CorrSeries {
  series: CorrPoint[];
  current: number | null;
  note: string;
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

export interface RateEnsembleSource {
  weight: number;
  n: number;
  brier: number | null;
}

export interface RateEnsembleMeeting {
  date: string;
  sources: Record<string, Record<string, number>>;
  blend: Record<string, number>;
}

export interface RateEnsemble {
  meetings: RateEnsembleMeeting[];
  weights: Record<string, RateEnsembleSource>;
  buckets: string[];
  labels: Record<string, string>;
  backtest: Record<string, unknown> & { asof?: string; basis?: string };
  display_only: boolean;
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
  marginLeverage: () => getJson<MarginLeverage>("/margin/leverage"),
  marginFast: () => getJson<MarginFast>("/margin/fast"),
  ratesShock: () => getJson<RateShock>("/rates/shock"),
  rateEnsemble: () => getJson<RateEnsemble>("/rates/ensemble"),
  shockScenarios: () => getJson<ShockScenarios>("/shock-sim/scenarios"),
  shockRun: (body: { hikes: number; seed?: number; overrides?: Record<string, number>; implied_baseline?: boolean }) =>
    getJson<ShockRun>("/shock-sim/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  shockCalibration: () => getJson<ShockCalibration>("/shock-sim/calibration"),
  flowDestinations: () => getJson<FlowDestinations>("/flows/destinations"),
  corrSeries: () => getJson<CorrSeries>("/crossasset/corr"),
  curveCanary: (pair: string) =>
    getJson<CurveCanary>(`/curve/canary?pair=${encodeURIComponent(pair)}`),
  events: (limit = 100) => getJson<CanaryEvent[]>(`/events?limit=${limit}`),
  alerts: () => getJson<CanaryEvent[]>("/alerts"),
  news: (limit = 40) => getJson<NewsResponse>(`/news?limit=${limit}`),
  pins: () => getJson<PinBoard>("/pins"),
  statRegime: () => getJson<StatRegime>("/stat-regime"),
  pinsHistory: () => getJson<PinHistory>("/pins/history"),
  trackRecord: () => getJson<TrackRecord>("/track-record"),
  severity: () => getJson<SeverityIndex>("/severity"),
  refresh: () =>
    getJson<unknown>("/refresh", { method: "POST" }),
};
