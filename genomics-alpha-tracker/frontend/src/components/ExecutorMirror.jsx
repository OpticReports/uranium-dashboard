import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../lib/api";
import { fmtNum, fmtPct, fmtMoney } from "../lib/format";
import InfoTip from "./InfoTip";

// Executor mirror backtest panel: the blend3070 book (ibkr-executor) replayed
// on the R2-A fire set with the executor's own mechanics. The numbers are
// produced on the host (needs the 10y bars cache); this panel renders whatever
// GET /blend3070/mirror-backtest returns, polls /status while a run is live,
// and shows a "not run yet" layout when the GET is a 404.
//
// Tolerant of two result layouts (the backend is built by another pass):
//   A) variants["0/100"].stats[window] + .curve [[date, value]] + .drawdown [[date, dd]]
//   B) variants.exec_t2_carry.windows[window] + .curves[window] [[date, equity, dd]]
// normalizeMirror() folds both into one shape so the JSX stays simple.

const WINDOWS = [
  { key: "2y", label: "2y", years: 2 },
  { key: "5y", label: "5y", years: 5 },
  { key: "full", label: "10y", years: null },
];
const WINDOW_KEYS = WINDOWS.map((w) => w.key);

const VARIANT_ALIASES = {
  primary: ["0/100", "exec_t2_carry"],
  t1: ["0/100 T+1", "exec_t1_carry"],
  nocarry: ["0/100 no-carry", "exec_t2_nocarry"],
  blend: ["30/70", "blend3070_t2_carry"],
  r2a: ["R2-A", "R2-A paper", "r2a_ref"],
};

const COLORS = { primary: "#38bdf8", blend: "#f59e0b", r2a: "#9ca3af" };
const TOOLTIP_STYLE = { background: "#121826", border: "1px solid #1f2937", fontSize: 12 };
const TICK = { fontSize: 9, fill: "#94a3b8" };

const num = (v) => (v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v));

function tri(obj, k) {
  if (!obj) return null;
  const inner = obj[k];
  const p5 = num(inner?.p5 ?? obj[`${k}_p5`]);
  const p50 = num(inner?.p50 ?? obj[`${k}_p50`]);
  const p95 = num(inner?.p95 ?? obj[`${k}_p95`]);
  if (p5 === null && p50 === null && p95 === null) return null;
  return { p5, p50, p95 };
}

function normStats(s, bootExt) {
  if (!s) return null;
  const uw = s.longest_underwater || null;
  const worstObj = s.worst_year && typeof s.worst_year === "object" ? s.worst_year : null;
  const b = s.bootstrap || bootExt || null;
  const boot = b
    ? { cagr: tri(b, "cagr"), max_dd: tri(b, "max_dd") || tri(b, "maxdd"),
        prob_neg: num(b.prob_cagr_negative) }
    : null;
  return {
    start: s.start ?? null,
    end: s.end ?? s.end_value ?? null,
    cagr: num(s.cagr),
    max_dd: num(s.max_dd),
    sharpe: num(s.sharpe),
    sortino: num(s.sortino),
    calmar: num(s.calmar),
    underwater_days: num(s.underwater_days ?? uw?.days_calendar),
    underwater_open: !!uw?.open,
    worst_year: worstObj ? worstObj.year : (s.worst_year ?? null),
    worst_year_ret: num(s.worst_year_ret ?? worstObj?.return),
    n_trades: num(s.n_trades),
    bootstrap: boot && (boot.cagr || boot.max_dd) ? boot : null,
  };
}

function normVariant(v) {
  if (!v) return null;
  const statsBy = v.stats || v.windows || {};
  const stats = {};
  for (const w of WINDOW_KEYS) stats[w] = normStats(statsBy[w], v.bootstrap?.[w]);
  let curve = null;
  let drawdown = null;
  let curvesByWindow = null;
  if (Array.isArray(v.curve)) {
    curve = v.curve.map((p) => (Array.isArray(p)
      ? { date: p[0], value: num(p[1]) }
      : { date: p.date, value: num(p.value ?? p.equity) }));
  }
  if (Array.isArray(v.drawdown)) {
    drawdown = v.drawdown.map((p) => (Array.isArray(p)
      ? { date: p[0], dd: num(p[1]) }
      : { date: p.date, dd: num(p.dd) }));
  }
  if (v.curves && typeof v.curves === "object") {
    curvesByWindow = {};
    for (const w of WINDOW_KEYS) {
      if (Array.isArray(v.curves[w])) {
        curvesByWindow[w] = v.curves[w].map((p) => (Array.isArray(p)
          ? { date: p[0], value: num(p[1]), dd: num(p[2]) }
          : { date: p.date, value: num(p.value ?? p.equity), dd: num(p.dd) }));
      }
    }
    if (!curve && curvesByWindow.full) curve = curvesByWindow.full;
  }
  return { stats, curve, drawdown, curvesByWindow };
}

function pickVariant(variants, aliases) {
  for (const a of aliases) if (variants[a]) return normVariant(variants[a]);
  return null;
}

export function normalizeMirror(raw) {
  if (!raw || typeof raw !== "object") return null;
  const variants = raw.variants || {};
  const out = {};
  for (const [k, aliases] of Object.entries(VARIANT_ALIASES)) out[k] = pickVariant(variants, aliases);
  const caveats = raw.contract?.caveats || raw.honesty || raw.protocol?.honesty || raw.meta?.caveats || [];
  const cacheVerified = raw.protocol?.cache_verified ?? raw.meta?.cache_verified ?? null;
  const cacheExact = raw.protocol?.cache_exact ?? null;
  const basisLane = raw.protocol?.cache_basis?.lane ?? null;
  const drift = raw.protocol?.r2a_reproduction?.abs_diff ?? raw.meta?.r2a_drift ?? null;
  const driftRel = raw.protocol?.r2a_reproduction?.rel_diff ?? null;
  const mach = raw.machinery || {};
  const machineryFacts = {
    coverage: mach.bar_coverage_matches_stored ?? null,
    rowsGot: mach.rows?.got ?? null,
    rowsStored: mach.rows?.stored ?? null,
    maxDdGot: mach.curve?.max_dd_got ?? null,
    maxDdStored: mach.curve?.max_dd_stored ?? null,
    sharpeGot: mach.curve?.sharpe_got ?? null,
    sharpeStored: mach.curve?.sharpe_stored ?? null,
  };
  return {
    generated: raw.generated || null,
    period: Array.isArray(raw.period) ? raw.period.join(" → ") : (raw.period || null),
    variants: out,
    caveats: Array.isArray(caveats) ? caveats : [],
    cacheVerified,
    cacheExact,
    basisLane,
    drift,
    driftRel,
    machineryFacts,
    servedFrom: raw.served_from || null,
  };
}

// --- window slicing (client-side, on the stored full curve) -----------------
const DAY_MS = 86_400_000;
function windowCutoff(curve, years) {
  if (!years || !curve?.length) return null;
  const last = Date.parse(curve[curve.length - 1].date);
  if (Number.isNaN(last)) return null;
  return last - years * 365.25 * DAY_MS;
}
function sliceCurve(curve, years) {
  if (!curve?.length) return [];
  const cut = windowCutoff(curve, years);
  if (cut === null) return curve;
  return curve.filter((p) => Date.parse(p.date) >= cut);
}
// Drawdown from the window's own running peak when the backend did not ship one.
function withDrawdown(points, ddLookup) {
  let peak = -Infinity;
  return points.map((p) => {
    let dd = ddLookup ? ddLookup.get(p.date) : p.dd;
    if (dd === null || dd === undefined) {
      if (p.value !== null && p.value > peak) peak = p.value;
      dd = peak > 0 && p.value !== null ? (p.value - peak) / peak : 0;
    }
    return { ...p, dd: -Math.abs(dd) };
  });
}
// Re-base every series to 100 at the window start: the stored curves are
// absolute dollars, so in a trailing window the lines would otherwise enter at
// different wealth levels and the gap between them would be eight years old.
function rebased(points) {
  const first = points.find((p) => p.value !== null && p.value > 0);
  if (!first) return points;
  return points.map((p) => ({ ...p, value: p.value === null ? null : (p.value / first.value) * 100 }));
}
export function windowSeries(variant, win) {
  if (!variant) return [];
  const w = WINDOWS.find((x) => x.key === win);
  if (variant.curvesByWindow?.[win]) return rebased(withDrawdown(variant.curvesByWindow[win], null));
  const pts = sliceCurve(variant.curve, w?.years);
  // a stored full-curve drawdown is only valid for the full window; a trailing
  // window recomputes from its own running peak
  const ddLookup = (!w?.years && variant.drawdown) ? new Map(variant.drawdown.map((d) => [d.date, d.dd])) : null;
  return rebased(withDrawdown(pts, ddLookup));
}
export function mergeSeries(seriesByKey) {
  const byDate = new Map();
  for (const [k, pts] of Object.entries(seriesByKey)) {
    for (const p of pts) {
      const row = byDate.get(p.date) || { date: p.date };
      row[k] = p.value;
      row[`${k}_dd`] = p.dd;
      byDate.set(p.date, row);
    }
  }
  return [...byDate.values()].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

// --- formatting ---------------------------------------------------------------
const DASH = "—";
const pct = (v, dp = 1) => (v === null || v === undefined ? DASH : fmtPct(v, dp));
const signedPct = (v, dp = 1) =>
  v === null || v === undefined ? DASH : `${v > 0 ? "+" : ""}${fmtPct(v, dp)}`;
const pp = (v, dp = 1) =>
  v === null || v === undefined ? DASH : `${v > 0 ? "+" : ""}${(v * 100).toFixed(dp)} pp`;
const n2 = (v) => (v === null || v === undefined ? DASH : fmtNum(v, 2));
const days = (v, open) => (v === null || v === undefined ? DASH : `${Math.round(v)}d${open ? "*" : ""}`);
const tone = (v) => (v === null || v === undefined ? "text-gray-200" : v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-gray-200");
const diff = (a, b, k) => (a?.[k] === null || a?.[k] === undefined || b?.[k] === null || b?.[k] === undefined ? null : a[k] - b[k]);

const fmtStamp = (s) => {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleString();
};

// --- component ----------------------------------------------------------------
export default function ExecutorMirror({ data, onReload, loadError }) {
  const m = useMemo(() => normalizeMirror(data), [data]);
  const [win, setWin] = useState("full");
  const [status, setStatus] = useState(null);
  const [runNote, setRunNote] = useState(null);
  const [starting, setStarting] = useState(false);

  const refreshStatus = useCallback(
    () => api.mirrorBacktestStatus().then(setStatus).catch(() => {}),
    [],
  );
  useEffect(() => { refreshStatus(); }, [refreshStatus]);

  // Poll every 10s while a replay is running; refetch results when it ends.
  const running = !!status?.running;
  useEffect(() => {
    if (!running) return undefined;
    const id = window.setInterval(async () => {
      try {
        const s = await api.mirrorBacktestStatus();
        setStatus(s);
        if (!s?.running) {
          setRunNote(s?.error ? "Replay finished with an error — see below." : "Replay finished — results reloaded.");
          onReload?.();
        }
      } catch { /* keep polling */ }
    }, 10_000);
    return () => window.clearInterval(id);
  }, [running, onReload]);

  const run = async () => {
    setStarting(true);
    setRunNote(null);
    try {
      const res = await api.runMirrorBacktest();
      if (res && res.started === false) {
        setRunNote(`Not started: ${res.reason || "already running"}`);
        refreshStatus();
      } else {
        setRunNote("Replay started on the host — polling status every 10s.");
        setStatus((s) => ({ ...(s || {}), running: true, error: null,
          started_at: res?.started_at || new Date().toISOString() }));
      }
    } catch (e) {
      setRunNote(`Run failed: ${e.message}`);
      refreshStatus();
    } finally {
      setStarting(false);
    }
  };

  const v = m?.variants || {};
  const primary = v.primary;
  const blend = v.blend;
  const r2a = v.r2a;
  const sel = (variant) => variant?.stats?.[win] || null;

  const chartData = useMemo(() => {
    if (!m) return [];
    return mergeSeries({
      primary: windowSeries(primary, win),
      blend: windowSeries(blend, win),
      r2a: windowSeries(r2a, win),
    });
  }, [m, primary, blend, r2a, win]);
  const hasChart = chartData.length > 2;

  const errText = Array.isArray(status?.error) ? status.error.join("\n") : status?.error;
  const lastRun = status?.last_run || status?.finished_at || m?.generated;

  const pS = sel(primary);
  const t1S = sel(v.t1);
  const ncS = sel(v.nocarry);
  const r2S = sel(r2a);
  const boot = pS?.bootstrap;

  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h3 className="font-semibold">
            🪞 Executor mirror backtest<InfoTip term="mirror_backtest" />
          </h3>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl">
            The blend3070 book replayed with the executor&apos;s own mechanics on the 10-year
            R2-A fire set: T+2 market-on-open fills, whole shares clipped to cash, ratchet-up-only
            3×ATR stop placed at fill, fire-anchored 90-day time stop, IBKR commissions, idle cash
            in BIL. Primary = sleeve-only (0/100); 30/70 beneath for comparison.
          </p>
        </div>
        <div className="text-right">
          <button
            onClick={run}
            disabled={running || starting}
            className="text-xs px-3 py-1.5 rounded border border-sky-700 text-sky-300 hover:bg-ink disabled:opacity-50"
          >
            {running ? "Replay running…" : "Run 10-year replay"}
          </button>
          <div className="text-[10px] text-gray-500 mt-1">
            {running
              ? `running since ${fmtStamp(status?.started_at) || "now"}`
              : lastRun ? `last run ${fmtStamp(lastRun)}` : "not run yet"}
            {m?.servedFrom && <span> · served from {m.servedFrom}</span>}
          </div>
        </div>
      </div>
      {runNote && <div className="text-xs text-gray-400 mt-2">{runNote}</div>}
      {!running && errText && (
        <pre className="text-[10px] text-rose-300 bg-ink border border-rose-900 rounded p-2 mt-2 overflow-x-auto whitespace-pre-wrap max-h-40">
          {errText}
        </pre>
      )}
      {m?.cacheVerified === false && (
        <div className="text-xs text-rose-200 bg-rose-900/40 border border-rose-700 rounded px-3 py-2 mt-2">
          <div className="font-semibold">Bars are the {m.basisLane || "rebuilt"} lane, NOT the campaign cache — absolute levels are not the R2 / R3 docs' numbers.</div>
          <div className="mt-1">
            R2-A replays {m.driftRel !== null && m.driftRel !== undefined ? `${(m.driftRel * 100).toFixed(2)}% ` : ""}
            {m.drift !== null && m.drift !== undefined ? `(${fmtMoney(m.drift)}) ` : ""}from the stored end value.
            {m.machineryFacts?.rowsGot && m.machineryFacts?.rowsStored && (
              <> Bar coverage {m.machineryFacts.coverage ? "identical" : "DIFFERS"} ({m.machineryFacts.rowsGot.n_regraded} regraded,
              {" "}{m.machineryFacts.rowsGot.open_at_end_excluded} open at data end); trade set {m.machineryFacts.rowsGot.n_taken} taken /
              {" "}{m.machineryFacts.rowsGot.skipped_at_cap} skipped vs stored {m.machineryFacts.rowsStored.n_taken} / {m.machineryFacts.rowsStored.skipped_at_cap}.</>
            )}
            {m.machineryFacts?.maxDdGot != null && m.machineryFacts?.maxDdStored != null && (
              <> Max DD {(m.machineryFacts.maxDdGot * 100).toFixed(2)}% vs stored {(m.machineryFacts.maxDdStored * 100).toFixed(2)}%;
              Sharpe {m.machineryFacts.sharpeGot?.toFixed(3)} vs {m.machineryFacts.sharpeStored?.toFixed(3)}.</>
            )}
            {" "}The executor deltas and the drawdown profile are measured within this run and stand on their own.
          </div>
        </div>
      )}
      {m?.cacheVerified === true && m?.cacheExact === false && (
        <div className="text-xs text-amber-200 bg-amber-900/30 border border-amber-700 rounded px-3 py-2 mt-2">
          Bars are the {m.basisLane || "rebuilt"} lane, not the August campaign cache: R2-A reproduces
          within the ±1% V0 machinery tolerance
          {m.driftRel !== null && m.driftRel !== undefined ? ` (${(m.driftRel * 100).toFixed(3)}% off` : ""}
          {m.drift !== null && m.drift !== undefined ? `, ${fmtMoney(m.drift)})` : (m.driftRel != null ? ")" : "")}
          {" "}but not to the dollar. Absolute levels match the R2 / R3 docs within that tolerance; the executor
          deltas are measured inside this run.
        </div>
      )}

      {!m && loadError && !/not run yet/i.test(loadError) && (
        <div className="text-xs text-rose-300 border border-rose-900/60 rounded-lg p-3 mt-3">
          Could not load the replay results: {loadError}
        </div>
      )}
      {!m && !(loadError && !/not run yet/i.test(loadError)) && (
        <div className="text-xs text-gray-500 border border-edge rounded-lg p-3 mt-3">
          Not run yet — the replay needs the 10-year bars cache on the host
          (<code>backend/data/backtest_bars.json</code>). Press <b>Run 10-year replay</b> there, or
          commit <code>backend/data/backtest_executor_mirror_results.json</code>. The layout below
          fills in once results exist.
        </div>
      )}

      {/* Tiles: one column per window; 0/100 rows, then a compact 30/70 row. */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3">
        {WINDOWS.map((w) => {
          const s = primary?.stats?.[w.key] || null;
          const b = blend?.stats?.[w.key] || null;
          const active = w.key === win;
          return (
            <div
              role="button"
              tabIndex={0}
              key={w.key}
              onClick={() => setWin(w.key)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setWin(w.key); } }}
              className={`bg-ink border rounded-lg p-2 text-left cursor-pointer focus:outline-none focus:ring-1 focus:ring-sky-700 ${active ? "border-sky-700" : "border-edge hover:border-gray-600"}`}
            >
              <div className="flex items-baseline justify-between">
                <div className="text-[10px] uppercase tracking-wide text-gray-500">{w.label}</div>
                <div className="text-[9px] text-gray-600">0/100</div>
              </div>
              <div className={`text-lg font-bold ${tone(s?.cagr)}`}>{signedPct(s?.cagr)}</div>
              <div className="text-[9px] uppercase tracking-wide text-gray-500">CAGR</div>
              <dl className="mt-1.5 space-y-0.5 text-xs">
                <Row k={<>max DD<InfoTip term="max_drawdown" /></>} v={pct(s?.max_dd)} cls="text-rose-300" />
                <Row k="Sharpe" v={n2(s?.sharpe)} />
                <Row k={<>underwater<InfoTip term="underwater" /></>} v={days(s?.underwater_days, s?.underwater_open)} />
                <Row k="worst yr" v={s?.worst_year ? `${s.worst_year} ${signedPct(s.worst_year_ret, 0)}` : DASH} cls="text-gray-400" />
              </dl>
              <div className="border-t border-edge/60 mt-1.5 pt-1 text-[10px] text-gray-400">
                <div className="flex justify-between">
                  <span className="text-amber-300/80">30/70</span>
                  <span className={tone(b?.cagr)}>{signedPct(b?.cagr)}</span>
                </div>
                <div className="flex justify-between text-gray-500">
                  <span>DD {pct(b?.max_dd, 0)}</span>
                  <span>Sh {n2(b?.sharpe)}</span>
                  <span>{days(b?.underwater_days, b?.underwater_open)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="text-[10px] text-gray-600 mt-1">
        Trailing 2y/5y are slices of the same 10y curve (positions carry in), not fresh books.
        Click a column to chart that window. * = underwater at window end.
      </div>

      {/* Window toggle + charts */}
      <div className="flex items-center justify-between flex-wrap gap-2 mt-4">
        <div className="text-xs text-gray-400">
          Equity (log) and drawdown — {WINDOWS.find((w) => w.key === win)?.label}
        </div>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              type="button"
              key={w.key}
              onClick={() => setWin(w.key)}
              className={`text-xs px-2 py-0.5 rounded border ${w.key === win ? "border-sky-700 text-sky-300 bg-ink" : "border-edge text-gray-400 hover:bg-ink"}`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>
      {hasChart ? (
        <div className="mt-2">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ left: 4, right: 10, top: 5 }} syncId="mirror">
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="date" tick={TICK} minTickGap={50} />
              <YAxis
                scale="log"
                domain={["auto", "auto"]}
                tick={TICK}
                width={44}
                tickFormatter={(x) => `${Math.round(x)}`}
                label={{ value: "index, 100 at window start", angle: -90, position: "insideLeft", fontSize: 9, fill: "#6b7280" }}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(x) => (x === null || x === undefined ? "—" : x.toFixed(1))} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line type="monotone" dataKey="primary" name="0/100 executor (T+2, BIL carry)"
                stroke={COLORS.primary} dot={false} strokeWidth={2} connectNulls />
              {blend && (
                <Line type="monotone" dataKey="blend" name="30/70 executor"
                  stroke={COLORS.blend} dot={false} strokeWidth={2} connectNulls />
              )}
              {r2a && (
                <Line type="monotone" dataKey="r2a" name="R2-A paper (reference)"
                  stroke={COLORS.r2a} strokeDasharray="4 3" dot={false} strokeWidth={1.5} connectNulls />
              )}
            </LineChart>
          </ResponsiveContainer>
          <ResponsiveContainer width="100%" height={110}>
            <AreaChart data={chartData} margin={{ left: 4, right: 10, top: 5 }} syncId="mirror">
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="date" tick={TICK} minTickGap={50} />
              <YAxis tick={TICK} width={44} tickFormatter={(x) => `${(x * 100).toFixed(0)}%`} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(x) => fmtPct(x)} />
              <Area type="monotone" dataKey="primary_dd" name="0/100 drawdown"
                stroke={COLORS.primary} fill={COLORS.primary} fillOpacity={0.18} dot={false} connectNulls />
              {blend && (
                <Area type="monotone" dataKey="blend_dd" name="30/70 drawdown"
                  stroke={COLORS.blend} fill={COLORS.blend} fillOpacity={0.12} dot={false} connectNulls />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="mt-2 h-24 border border-dashed border-edge rounded-lg flex items-center justify-center text-xs text-gray-600">
          {m ? "no curve in the results file" : "equity and drawdown curves appear here after the replay runs"}
        </div>
      )}

      {/* Delta chips */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
        <Chip
          label="T+2 vs T+1 fill"
          main={pp(diff(pS, t1S, "cagr"))}
          sub={`CAGR · max DD ${pp(diff(pS, t1S, "max_dd"))}`}
          hint="primary (T+2 open, the executor's real fill) minus the T+1 variant R2-A assumes"
        />
        <Chip
          label="BIL carry on vs off"
          main={pp(diff(pS, ncS, "cagr"))}
          sub={`CAGR · max DD ${pp(diff(pS, ncS, "max_dd"))}`}
          hint="idle sleeve cash earning BIL total return vs rf = 0"
        />
        <Chip
          label="vs paper R2-A"
          main={pp(diff(pS, r2S, "cagr"))}
          sub={`CAGR · max DD ${pp(diff(pS, r2S, "max_dd"))}`}
          hint="all executor mechanics + costs + carry vs the paper backtest"
        />
        <Chip
          label={<>bootstrap p5 / p50 / p95<InfoTip term="block_bootstrap" /></>}
          main={boot?.cagr ? `${signedPct(boot.cagr.p5, 0)} / ${signedPct(boot.cagr.p50, 0)} / ${signedPct(boot.cagr.p95, 0)}` : DASH}
          sub={boot?.max_dd
            ? `max DD ${pct(boot.max_dd.p5, 0)} / ${pct(boot.max_dd.p50, 0)} / ${pct(boot.max_dd.p95, 0)}${boot.prob_neg !== null && boot.prob_neg !== undefined ? ` · P(CAGR<0) ${fmtPct(boot.prob_neg, 0)}` : ""}`
            : "CAGR cone · 2,000 draws, 21d blocks"}
          hint="stationary block bootstrap of the window's daily returns (0/100 book)"
        />
      </div>

      {/* Honesty block */}
      <div className="mt-3 pt-3 border-t border-edge/60">
        <div className="text-xs text-gray-400 mb-1">Read this first — what these numbers are not</div>
        {m?.caveats?.length ? (
          <ul className="text-[11px] text-gray-500 space-y-0.5 list-disc pl-4">
            {m.caveats.map((c, i) => <li key={i}>{typeof c === "string" ? c : JSON.stringify(c)}</li>)}
          </ul>
        ) : (
          <ul className="text-[11px] text-gray-500 space-y-0.5 list-disc pl-4">
            <li>Replayable shadow of the live book, not the live book: hindsight-tiered 32-name universe (survivorship), in-sample thresholds, live sentiment/revision/options lanes absent.</li>
            <li>Costs are assumed (IBKR fixed schedule, $1 BIL orders, tiered slippage 10/40/100 bps, SPY 10 bps), not measured; 21 prior judged variants mean selection effects.</li>
            <li>Max DD and Sharpe are on the daily marked-to-market curve, rf = 0. Not a forecast.</li>
          </ul>
        )}
        {m?.period && <div className="text-[10px] text-gray-600 mt-1">period {m.period}{m.generated ? ` · generated ${fmtStamp(m.generated)}` : ""}</div>}
      </div>
    </div>
  );
}

function Row({ k, v, cls }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-gray-500 whitespace-nowrap">{k}</dt>
      <dd className={`font-semibold ${cls || "text-gray-200"}`}>{v}</dd>
    </div>
  );
}

function Chip({ label, main, sub, hint }) {
  return (
    <div className="bg-ink border border-edge rounded-lg p-2" title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="text-sm font-bold text-gray-200">{main}</div>
      {sub && <div className="text-[10px] text-gray-500">{sub}</div>}
    </div>
  );
}
