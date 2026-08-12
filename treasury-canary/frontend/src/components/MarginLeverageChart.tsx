import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  CartesianGrid,
} from "recharts";
import type { LeverageState, MarginLeverage } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";
import FastLeverageStrip from "./FastLeverageStrip";

interface ChartRow {
  ts: number;
  date: string;
  margin_yoy: number | null;
  excess_yoy: number | null;
  excess_nc: number | null;
  nc_lo: number | null;
  nc_hi: number | null;
  spx: number | null;
  btc: number | null;
  spx_idx: number | null;
  btc_idx: number | null;
}

const STATE_STYLE: Record<
  LeverageState,
  { color: string; bg: string; border: string }
> = {
  BLOWOFF: { color: "#f87171", bg: "rgba(248,113,113,0.10)", border: "rgba(248,113,113,0.5)" },
  ELEVATED: { color: "#fbbf24", bg: "rgba(251,191,36,0.10)", border: "rgba(251,191,36,0.5)" },
  NEUTRAL: { color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.4)" },
  SQUEEZE: { color: "#38bdf8", bg: "rgba(56,189,248,0.10)", border: "rgba(56,189,248,0.5)" },
  WASHOUT: { color: "#c084fc", bg: "rgba(192,132,252,0.10)", border: "rgba(192,132,252,0.5)" },
};

function NowcastChip({ nowcast }: { nowcast?: import("../lib/api").MarginNowcast | null }) {
  if (!nowcast?.months?.length) return null;
  const m = nowcast.months[nowcast.months.length - 1];
  if (m.excess_pp == null || !m.state_est) return null;
  const st = STATE_STYLE[m.state_est];
  const bt = nowcast.backtest as Record<string, number | string>;
  return (
    <div
      className="mt-2 rounded border px-3 py-2 text-xs"
      style={{ background: "rgba(125,211,252,0.06)", borderColor: "rgba(125,211,252,0.3)" }}
    >
      <span className="font-mono text-[10px] uppercase tracking-wide text-sky-300">
        Nowcast (est) · {m.month}
        {m.partial_month ? " · partial month" : ""} ·{" "}
        {m.basis.startsWith("schwab") ? "Schwab-anchored" : "price model"}
      </span>{" "}
      <span className="font-semibold" style={{ color: st.color }}>
        {m.state_est}
        {m.near_boundary ? " (near boundary)" : ""}
      </span>{" "}
      <span className="text-slate-300">
        est excess {m.excess_pp > 0 ? "+" : ""}
        {m.excess_pp.toFixed(1)}pp ±{(m.band_pp ?? 3.1).toFixed(1)}
        {m.yoy_pct != null ? ` · margin YoY ~${m.yoy_pct.toFixed(0)}%` : ""}
      </span>
      {nowcast.schwab?.yoy_pct != null && (
        <span className="text-slate-500">
          {" "}· Schwab client margin {nowcast.schwab.latest_month}: $
          {nowcast.schwab.margin_bn.toFixed(0)}B ({nowcast.schwab.yoy_pct > 0 ? "+" : ""}
          {nowcast.schwab.yoy_pct.toFixed(0)}% YoY, files ~3wk before FINRA)
        </span>
      )}
      <div className="mt-1 text-[10px] leading-relaxed text-slate-500">
        Estimate of the months FINRA hasn&apos;t printed — display-only, never feeds
        the composite or the corroboration flags. Backtest (pseudo-OOS, {String(bt.transitions)}
        {" "}transitions): direction {String(bt.direction_hit_pct)}% · state {String(bt.state_hit_pct)}%
        overall but regime-TURN months only {String(bt.transition_hit_pct)}% — it catches about half
        of state changes a month early; misses cluster at band boundaries. YoY error sd ±
        {String(bt.yoy_err_sd_pp)}pp.
      </div>
    </div>
  );
}

function toTs(dateStr: string): number {
  const d = new Date(dateStr);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

// Pre-1997 margin data is quarterly Z.1; FINRA monthly after. BTC exists 2014+.
// Data is MONTHLY, so 1y (~12 points + nowcast) is the useful floor; custom
// covers anything tighter.
const YEAR_MS = 365.25 * 864e5;
const RANGES: Array<{ id: string; label: string; fromTs: () => number | null }> = [
  { id: "all", label: "All (1927+)", fromTs: () => null },
  { id: "1971", label: "1971+", fromTs: () => Date.UTC(1971, 0, 1) },
  { id: "1997", label: "1997+", fromTs: () => Date.UTC(1997, 0, 1) },
  { id: "10y", label: "10y", fromTs: () => Date.now() - 10 * YEAR_MS },
  { id: "3y", label: "3y", fromTs: () => Date.now() - 3 * YEAR_MS },
  { id: "1y", label: "1y", fromTs: () => Date.now() - 1 * YEAR_MS },
];

export default function MarginLeverageChart() {
  const [data, setData] = useState<MarginLeverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSpx, setShowSpx] = useState(false);
  const [showBtc, setShowBtc] = useState(false);
  const [range, setRange] = useState("1997");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .marginLeverage()
      .then((d) => {
        if (alive) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(errorMessage(e));
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  const rows: ChartRow[] = useMemo(() => {
    if (!data?.series) return [];
    let minTs = -Infinity;
    let maxTs = Infinity;
    if (range === "custom") {
      if (customFrom) minTs = toTs(`${customFrom}-01`);
      if (customTo) maxTs = toTs(`${customTo}-28`);
    } else {
      minTs = RANGES.find((r) => r.id === range)?.fromTs() ?? -Infinity;
    }
    const win = data.series
      .map((p) => ({
        ts: toTs(p.date),
        date: p.date,
        margin_yoy: p.margin_yoy,
        excess_yoy: p.excess_yoy,
        excess_nc: null as number | null,
        nc_lo: null as number | null,
        nc_hi: null as number | null,
        spx: p.spx,
        btc: p.btc,
        spx_idx: null as number | null,
        btc_idx: null as number | null,
      }))
      .filter((r) => r.ts >= minTs && r.ts <= maxTs);
    // Nowcast (display-only estimate): dashed extension of the excess line
    // over the months FINRA hasn't printed, anchored at the last real point.
    if (data.nowcast?.months?.length) {
      const lastReal = [...win].reverse().find((r) => r.excess_yoy != null);
      if (lastReal) lastReal.excess_nc = lastReal.excess_yoy;
      for (const m of data.nowcast.months) {
        if (m.excess_pp == null) continue;
        const ts = Date.UTC(+m.month.slice(0, 4), +m.month.slice(5, 7) - 1, 1);
        if (ts < minTs || ts > maxTs) continue;
        win.push({
          ts, date: `${m.month}-01 (est)`,
          margin_yoy: null, excess_yoy: null,
          excess_nc: m.excess_pp,
          nc_lo: m.excess_pp - (m.band_pp ?? 3.1),
          nc_hi: m.excess_pp + (m.band_pp ?? 3.1),
          spx: null, btc: null, spx_idx: null, btc_idx: null,
        });
      }
    }
    // Re-index overlays to 100 at their first point INSIDE the selected window
    // so every range starts comparably at 100.
    let spxBase: number | null = null;
    let btcBase: number | null = null;
    for (const r of win) {
      if (r.spx != null && spxBase === null) spxBase = r.spx;
      if (r.btc != null && btcBase === null) btcBase = r.btc;
      r.spx_idx =
        r.spx != null && spxBase ? Math.round((1000 * r.spx) / spxBase) / 10 : null;
      r.btc_idx =
        r.btc != null && btcBase ? Math.round((1000 * r.btc) / btcBase) / 10 : null;
    }
    return win;
  }, [data, range, customFrom, customTo]);

  const domain: [number, number] | undefined =
    rows.length > 0 ? [rows[0].ts, rows[rows.length - 1].ts] : undefined;

  return (
    <div className="space-y-4">
    {/* fast nowcast strip rides above the slow monthly chart so the two
        leverage clocks read as one unit; it needs the slow state for the
        cross-reading line */}
    <FastLeverageStrip slowState={data?.current.state} />
    <Panel
      title={
        <>
          Leverage Cycle — FINRA Margin Debt
          <InfoTip term="margin_leverage" />
        </>
      }
      subtitle="Blowoff warns over 12 months; squeeze-out marks the post-crash reset"
    >
      {loading && <Loading label="Loading margin series…" />}
      {!loading && error && <InlineError message={error} />}

      {!loading && !error && data && (
        <>
          <StateBanner data={data} />
          <NowcastChip nowcast={data.nowcast} />

          {rows.length === 0 ? (
            <div className="mt-4 flex h-56 items-center justify-center rounded border border-dashed border-panelborder text-center text-sm text-slate-500">
              <div>
                <p className="font-semibold text-slate-400">
                  Margin series unavailable
                </p>
                <p className="mt-1 text-xs">
                  FINRA fetch may have failed — it retries on the next refresh.
                </p>
              </div>
            </div>
          ) : (
            <>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] uppercase tracking-wide text-slate-500">
                  range
                </span>
                {RANGES.map((r) => (
                  <ToggleChip
                    key={r.id}
                    label={r.label}
                    color="#38bdf8"
                    active={range === r.id}
                    onClick={() => setRange(r.id)}
                  />
                ))}
                <ToggleChip
                  label="custom"
                  color="#34d399"
                  active={range === "custom"}
                  onClick={() => setRange("custom")}
                />
                {range === "custom" && (
                  <span className="flex items-center gap-1 text-[10px] text-slate-400">
                    <input
                      type="month"
                      value={customFrom}
                      onChange={(e) => setCustomFrom(e.target.value)}
                      className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-200"
                    />
                    &ndash;
                    <input
                      type="month"
                      value={customTo}
                      onChange={(e) => setCustomTo(e.target.value)}
                      className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-200"
                    />
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                price overlay
              </span>
              <ToggleChip
                label="S&P 500"
                color="#fbbf24"
                active={showSpx}
                onClick={() => setShowSpx((v) => !v)}
              />
              <ToggleChip
                label="BTC"
                color="#f97316"
                active={showBtc}
                onClick={() => setShowBtc((v) => !v)}
              />
              </div>
            </div>
            <div className="mt-2 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={rows}
                  margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
                >
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  {data.recessions.map((r) => (
                    <ReferenceArea
                      key={r.start}
                      x1={toTs(r.start)}
                      x2={toTs(r.end)}
                      fill="#64748b"
                      fillOpacity={0.12}
                      ifOverflow="hidden"
                    />
                  ))}
                  <XAxis
                    dataKey="ts"
                    type="number"
                    scale="time"
                    domain={domain}
                    tickFormatter={(t: number) => {
                      const d = new Date(t);
                      const spanYears = domain
                        ? (domain[1] - domain[0]) / YEAR_MS
                        : 99;
                      return spanYears <= 4
                        ? d.toLocaleDateString("en-US", {
                            month: "short",
                            year: "2-digit",
                            timeZone: "UTC",
                          })
                        : d.getFullYear().toString();
                    }}
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                    width={38}
                    tickFormatter={(v: number) => `${v}`}
                    label={{
                      value: "% / pp",
                      angle: -90,
                      position: "insideLeft",
                      style: { fill: "#475569", fontSize: 10 },
                    }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 6,
                      fontSize: 11,
                    }}
                    labelFormatter={(t) =>
                      new Date(Number(t)).toISOString().slice(0, 7)
                    }
                    formatter={(v: number, name: string, item: { payload?: ChartRow }) => {
                      if (name === "excess_yoy")
                        return [`${Number(v).toFixed(1)}pp`, "Excess growth (vs S&P)"];
                      if (name === "excess nowcast (est)") {
                        const row = item.payload as any;
                        const band = row?.nc_hi != null && row?.nc_lo != null
                          ? ` (band ${Number(row.nc_lo).toFixed(1)}–${Number(row.nc_hi).toFixed(1)})`
                          : "";
                        return [
                          `${Number(v).toFixed(1)}pp est${band}`,
                          "NOWCAST — months FINRA hasn't printed yet: price-model estimate ±3.1pp, display-only (never feeds the composite or flags); replaced by the real print when FINRA files",
                        ];
                      }
                      if (name === "nowcast band hi" || name === "nowcast band lo")
                        return [`${Number(v).toFixed(1)}pp`, name === "nowcast band hi" ? "nowcast upper (±1sd)" : "nowcast lower (±1sd)"];
                      if (name === "margin_yoy")
                        return [`${Number(v).toFixed(1)}%`, "Margin debt YoY"];
                      if (name === "spx_idx") {
                        const raw = item.payload?.spx;
                        return [
                          raw != null
                            ? `${Math.round(raw).toLocaleString()} (idx ${Number(v).toFixed(0)})`
                            : `idx ${Number(v).toFixed(0)}`,
                          "S&P 500",
                        ];
                      }
                      if (name === "btc_idx") {
                        const raw = item.payload?.btc;
                        return [
                          raw != null
                            ? `$${Math.round(raw).toLocaleString()} (idx ${Number(v).toFixed(0)})`
                            : `idx ${Number(v).toFixed(0)}`,
                          "BTC",
                        ];
                      }
                      return [String(v), name];
                    }}
                  />
                  {/* Blowoff / elevated bands on the EXCESS scale */}
                  <ReferenceLine
                    y={data.thresholds.blowoff_excess}
                    stroke="#f87171"
                    strokeDasharray="5 4"
                    label={{
                      value: "blowoff +25pp",
                      position: "insideTopRight",
                      style: { fill: "#f87171", fontSize: 9 },
                    }}
                  />
                  <ReferenceLine
                    y={data.thresholds.washout_yoy}
                    stroke="#c084fc"
                    strokeDasharray="5 4"
                    label={{
                      value: "washout −15%",
                      position: "insideBottomRight",
                      style: { fill: "#c084fc", fontSize: 9 },
                    }}
                  />
                  <ReferenceLine y={0} stroke="#475569" />
                  <Line
                    dataKey="margin_yoy"
                    name="margin_yoy"
                    stroke="#64748b"
                    dot={false}
                    strokeWidth={1.2}
                    connectNulls
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="excess_yoy"
                    name="excess_yoy"
                    stroke="#38bdf8"
                    dot={rows.length < 48 ? { r: 2.5, fill: "#38bdf8" } : false}
                    strokeWidth={2}
                    connectNulls
                    isAnimationActive={false}
                  />
                  {/* nowcast: dashed estimate + band over unprinted months */}
                  <Line
                    dataKey="excess_nc"
                    name="excess nowcast (est)"
                    stroke="#7dd3fc"
                    strokeDasharray="6 4"
                    dot={{ r: 3, fill: "#7dd3fc" }}
                    strokeWidth={2}
                    connectNulls
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="nc_hi"
                    name="nowcast band hi"
                    stroke="rgba(125,211,252,0.35)"
                    strokeDasharray="2 4"
                    dot={false}
                    strokeWidth={1}
                    connectNulls
                    isAnimationActive={false}
                    legendType="none"
                  />
                  <Line
                    dataKey="nc_lo"
                    name="nowcast band lo"
                    stroke="rgba(125,211,252,0.35)"
                    strokeDasharray="2 4"
                    dot={false}
                    strokeWidth={1}
                    connectNulls
                    isAnimationActive={false}
                    legendType="none"
                  />
                  {(showSpx || showBtc) && (
                    <YAxis
                      yAxisId="price"
                      orientation="right"
                      scale="log"
                      domain={["auto", "auto"]}
                      stroke="#475569"
                      tick={{ fontSize: 10 }}
                      width={42}
                      tickFormatter={(v: number) =>
                        v >= 1000
                          ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`
                          : `${Math.round(v)}`
                      }
                      label={{
                        value: "start = 100 (log)",
                        angle: 90,
                        position: "insideRight",
                        style: { fill: "#475569", fontSize: 9 },
                      }}
                    />
                  )}
                  {showSpx && (
                    <Line
                      yAxisId="price"
                      dataKey="spx_idx"
                      name="spx_idx"
                      stroke="#fbbf24"
                      dot={false}
                      strokeWidth={1.4}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  {showBtc && (
                    <Line
                      yAxisId="price"
                      dataKey="btc_idx"
                      name="btc_idx"
                      stroke="#f97316"
                      dot={false}
                      strokeWidth={1.4}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            </>
          )}

          <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
            <span className="text-sky-400">Blue</span>: excess growth (margin YoY
            − S&P YoY, the scored signal; spans FRED's ~10y S&P history).{" "}
            <span className="text-slate-400">Grey</span>: raw margin YoY —
            FINRA monthly from 1997, spliced onto quarterly Fed Z.1 security
            credit before that (context, not part of the backtest; the two track
            near-1:1 at the splice). Shaded bands: NBER recessions. Yearly
            margin contraction below zero = the squeeze; watch it after a crash
            to see the leverage reset complete. BTC data exists from 2014 — no
            earlier price exists to show.
            {(showSpx || showBtc) && (
              <>
                {" "}Overlays (<span className="text-amber-400">S&P</span>
                {showBtc && (
                  <>
                    , <span className="text-orange-400">BTC</span>
                  </>
                )}
                ): month-end prices indexed to 100 at their first charted month,
                log scale on the right axis — shapes are comparable, levels are
                not. Leverage blowoffs and crypto blowoffs share the same
                risk-appetite cycle; watch them peak and unwind together.
              </>
            )}
          </p>
        </>
      )}
    </Panel>
    </div>
  );
}

function ToggleChip({
  label,
  color,
  active,
  onClick,
}: {
  label: string;
  color: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold transition-colors ${
        active ? "" : "border-panelborder text-slate-500 hover:text-slate-300"
      }`}
      style={
        active
          ? { color, borderColor: color, backgroundColor: `${color}1a` }
          : undefined
      }
    >
      {label}
    </button>
  );
}

function StateBanner({ data }: { data: MarginLeverage }) {
  const state = data.current.state;
  if (!state) {
    return (
      <div className="rounded border border-panelborder bg-slate-900/50 px-3 py-2 text-xs text-slate-500">
        Leverage state unavailable (FINRA series missing).
      </div>
    );
  }
  const pb = data.playbook[state];
  const st = STATE_STYLE[state];
  const s12 = pb.stats.fwd12;
  const higher = 100 - s12.pct_lower;
  return (
    <div
      className="rounded-lg border px-4 py-3"
      style={{ backgroundColor: st.bg, borderColor: st.border }}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className="text-sm font-bold tracking-wide"
          style={{ color: st.color }}
        >
          {state}
        </span>
        <span className="text-xs text-slate-300">{pb.label}</span>
        <span className="ml-auto font-mono text-[11px] text-slate-400">
          excess{" "}
          {data.current.excess_yoy != null
            ? `${data.current.excess_yoy > 0 ? "+" : ""}${data.current.excess_yoy.toFixed(1)}pp`
            : "—"}{" "}
          · YoY{" "}
          {data.current.margin_yoy != null
            ? `${data.current.margin_yoy > 0 ? "+" : ""}${data.current.margin_yoy.toFixed(1)}%`
            : "—"}{" "}
          · {data.current.date?.slice(0, 7) ?? ""}
        </span>
      </div>
      {/* The prescriptive line: what this level meant historically */}
      <p className="mt-1.5 text-xs leading-relaxed text-slate-300">
        <span className="font-semibold" style={{ color: st.color }}>
          {s12.n - Math.round((s12.pct_lower / 100) * s12.n)} of {s12.n}
        </span>{" "}
        months in this state ({higher}%) saw the S&amp;P HIGHER 12 months later
        — median {s12.median > 0 ? "+" : ""}
        {s12.median.toFixed(1)}%, worst {s12.worst.toFixed(1)}%.{" "}
        {pb.read}
      </p>
      <p className="mt-1 text-xs font-medium leading-relaxed text-slate-200">
        → {pb.action}
      </p>
      {pb.evidence && (
        <p className="mt-1 text-[10px] leading-relaxed text-amber-400/80">
          Evidence: {pb.evidence}
        </p>
      )}
      <p className="mt-1 text-[10px] text-slate-500">
        Stats: monthly states in the FINRA era (1997–2026, ~3 independent
        blowoff episodes) — fixed by design; the separate 75y blowoff-peak
        study (8 bears / 16 peaks) feeds the corroboration line below. The
        range chips window the chart only; sub-window stats would rest on 1–2
        episodes and mislead.
      </p>
      {data.corroboration && (
        <CorroborationLine
          c={data.corroboration}
          prominent={state === "BLOWOFF" || state === "ELEVATED"}
        />
      )}
    </div>
  );
}

const FLAG_LABELS: Record<string, string> = {
  flat_curve: "flat curve",
  fed_tightened: "Fed tightened",
  late_expansion: "late expansion",
  low_unemployment: "low unemployment",
  extended_market: "extended market",
  high_excess: "high excess",
};

function CorroborationLine({
  c,
  prominent,
}: {
  c: NonNullable<MarginLeverage["corroboration"]>;
  prominent: boolean;
}) {
  if (c.n_known === 0) return null;
  const stats =
    c.n_true >= 4
      ? c.stats.high_flags
      : c.n_true <= 2
        ? c.stats.low_flags
        : c.stats.unconditional;
  const countColor =
    c.n_true >= 4 ? "#f87171" : c.n_true <= 2 ? "#34d399" : "#fbbf24";
  return (
    <div className="mt-2 border-t border-slate-700/50 pt-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          True bear or false positive?
        </span>
        <InfoTip term="leverage_corroboration" />
        <span
          className="font-mono text-[11px] font-bold"
          style={{ color: countColor }}
        >
          {c.n_true}/{c.n_known} late-cycle flags
        </span>
        <span className="flex flex-wrap gap-1">
          {Object.entries(c.flags).map(([k, v]) =>
            v === null ? null : (
              <span
                key={k}
                className="rounded-full border px-1.5 py-px text-[9px]"
                style={
                  v
                    ? {
                        color: countColor,
                        borderColor: `${countColor}80`,
                        backgroundColor: `${countColor}14`,
                      }
                    : {
                        color: "#64748b",
                        borderColor: "#33415580",
                        textDecoration: "line-through",
                      }
                }
              >
                {FLAG_LABELS[k] ?? k}
              </span>
            ),
          )}
        </span>
      </div>
      <p
        className={`mt-1 text-[11px] leading-relaxed ${
          prominent ? "text-slate-300" : "text-slate-400"
        }`}
      >
        Only ~half of historical blowoffs preceded a major bear — the rest
        fizzled. Today reads as a{" "}
        <span className="font-semibold" style={{ color: countColor }}>
          {c.reading}
        </span>
        . Historically, {stats.label}: {stats.prob_note}.
      </p>
    </div>
  );
}
