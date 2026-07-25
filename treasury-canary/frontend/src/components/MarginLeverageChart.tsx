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

interface ChartRow {
  ts: number;
  date: string;
  margin_yoy: number | null;
  excess_yoy: number | null;
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

function toTs(dateStr: string): number {
  const d = new Date(dateStr);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

// Pre-1997 margin data is quarterly Z.1; FINRA monthly after. BTC exists 2014+.
const RANGES: Array<{ id: string; label: string; from: number | null }> = [
  { id: "all", label: "All (1946+)", from: null },
  { id: "1971", label: "1971+", from: 1971 },
  { id: "1997", label: "1997+", from: 1997 },
  { id: "10y", label: "10y", from: new Date().getFullYear() - 10 },
];

export default function MarginLeverageChart() {
  const [data, setData] = useState<MarginLeverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSpx, setShowSpx] = useState(false);
  const [showBtc, setShowBtc] = useState(false);
  const [range, setRange] = useState("1997");

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
    const fromYear = RANGES.find((r) => r.id === range)?.from ?? null;
    const minTs = fromYear === null ? -Infinity : Date.UTC(fromYear, 0, 1);
    const win = data.series
      .map((p) => ({
        ts: toTs(p.date),
        date: p.date,
        margin_yoy: p.margin_yoy,
        excess_yoy: p.excess_yoy,
        spx: p.spx,
        btc: p.btc,
        spx_idx: null as number | null,
        btc_idx: null as number | null,
      }))
      .filter((r) => r.ts >= minTs);
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
  }, [data, range]);

  const domain: [number, number] | undefined =
    rows.length > 0 ? [rows[0].ts, rows[rows.length - 1].ts] : undefined;

  return (
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
                    tickFormatter={(t: number) =>
                      new Date(t).getFullYear().toString()
                    }
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
                    dot={false}
                    strokeWidth={2}
                    connectNulls
                    isAnimationActive={false}
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
    </div>
  );
}
