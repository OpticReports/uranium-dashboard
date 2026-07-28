import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FastLeverageState, LeverageState, MarginFast } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";
import { InlineError, Loading, Panel } from "./ui";

const FAST_STYLE: Record<
  FastLeverageState,
  { color: string; bg: string; border: string }
> = {
  FLUSH: { color: "#fb923c", bg: "rgba(251,146,60,0.10)", border: "rgba(251,146,60,0.5)" },
  WASHED_OUT: { color: "#c084fc", bg: "rgba(192,132,252,0.10)", border: "rgba(192,132,252,0.5)" },
  RISK_BUILD: { color: "#fbbf24", bg: "rgba(251,191,36,0.10)", border: "rgba(251,191,36,0.5)" },
  CALM: { color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.4)" },
};

// One shared sigma scale; each leg z-scored against its own served history.
const LEGS = {
  cot: { label: "Hedge-fund S&P futures", color: "#38bdf8", cadence: "weekly" },
  vix: { label: "VIX", color: "#fbbf24", cadence: "daily" },
  funding: { label: "BTC funding", color: "#f97316", cadence: "hourly" },
  hy: { label: "HY spread", color: "#f87171", cadence: "daily" },
} as const;
type LegKey = keyof typeof LEGS;

const RANGES = [
  { id: "2y", label: "2y", days: 730 },
  { id: "1y", label: "1y", days: 365 },
  { id: "6m", label: "6m", days: 183 },
  { id: "3m", label: "3m", days: 91 },
  { id: "1m", label: "1m", days: 31 },
  { id: "custom", label: "Custom", days: 0 },
] as const;

interface Row {
  ts: number;
  cot: number | null;
  vix: number | null;
  funding: number | null;
  hy: number | null;
  cot_native: number | null;
  vix_native: number | null;
  funding_native: number | null;
  hy_native: number | null;
}

function toTs(s: string): number {
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

export default function FastLeverageStrip({
  slowState,
}: {
  slowState: LeverageState | null | undefined;
}) {
  const [data, setData] = useState<MarginFast | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [on, setOn] = useState<Record<LegKey, boolean>>({
    cot: true,
    vix: true,
    funding: true,
    hy: true,
  });
  const [range, setRange] = useState<string>("6m");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .marginFast()
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

  // Merge the four legs into one time-indexed table (σ values + natives).
  const rows: Row[] = useMemo(() => {
    if (!data) return [];
    const by = new Map<number, Row>();
    const row = (ts: number): Row => {
      let r = by.get(ts);
      if (!r) {
        r = {
          ts,
          cot: null, vix: null, funding: null, hy: null,
          cot_native: null, vix_native: null, funding_native: null, hy_native: null,
        };
        by.set(ts, r);
      }
      return r;
    };
    for (const p of data.cot.series) {
      if (p.z != null) {
        const r = row(toTs(p.date));
        r.cot = p.z;
        r.cot_native = p.pct;
      }
    }
    for (const p of data.vix.series) {
      if (p.z != null) {
        const r = row(toTs(p.date));
        r.vix = p.z;
        r.vix_native = p.vix;
      }
    }
    for (const p of data.btc.funding_series) {
      if (p.z != null) {
        const r = row(toTs(p.date));
        r.funding = p.z;
        r.funding_native = p.ann_pct;
      }
    }
    for (const p of data.hy.series) {
      if (p.z != null) {
        const r = row(toTs(p.date));
        r.hy = p.z;
        r.hy_native = p.bp;
      }
    }
    return [...by.values()].sort((a, b) => a.ts - b.ts);
  }, [data]);

  const win: Row[] = useMemo(() => {
    if (rows.length === 0) return [];
    let minTs: number;
    let maxTs = Infinity;
    if (range === "custom") {
      minTs = from ? Date.parse(from) : -Infinity;
      maxTs = to ? Date.parse(to) + 86_400_000 : Infinity;
      if (Number.isNaN(minTs)) minTs = -Infinity;
      if (Number.isNaN(maxTs)) maxTs = Infinity;
    } else {
      const days = RANGES.find((r) => r.id === range)?.days ?? 183;
      minTs = rows[rows.length - 1].ts - days * 86_400_000;
    }
    return rows.filter((r) => r.ts >= minTs && r.ts <= maxTs);
  }, [rows, range, from, to]);

  const domain: [number, number] | undefined =
    win.length > 1 ? [win[0].ts, win[win.length - 1].ts] : undefined;

  return (
    <Panel
      title={
        <>
          Fast Leverage — Nowcast
          <InfoTip term="fast_leverage" />
        </>
      }
      subtitle="Is leverage being forced out RIGHT NOW? Weekly / daily / hourly legs — the monthly chart below is the slow confirmation"
    >
      {loading && <Loading label="Loading fast-leverage legs…" />}
      {!loading && error && <InlineError message={error} />}

      {!loading && !error && data && (
        <>
          <FastBanner data={data} slowState={slowState} />

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
              {range === "custom" && (
                <span className="flex items-center gap-1">
                  <DateInput value={from} onChange={setFrom} />
                  <span className="text-[10px] text-slate-500">→</span>
                  <DateInput value={to} onChange={setTo} />
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {(Object.keys(LEGS) as LegKey[]).map((k) => (
                <ToggleChip
                  key={k}
                  label={`${LEGS[k].label} ${legValue(data, k)}`}
                  color={LEGS[k].color}
                  active={on[k]}
                  onClick={() => setOn((o) => ({ ...o, [k]: !o[k] }))}
                />
              ))}
            </div>
          </div>

          {win.length < 2 ? (
            <div className="mt-2 flex h-56 items-center justify-center rounded border border-dashed border-panelborder text-xs text-slate-500">
              No data in this window — widen the range.
            </div>
          ) : (
            <div className="mt-2 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={win}
                  margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
                >
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="ts"
                    type="number"
                    scale="time"
                    domain={domain}
                    tickFormatter={(t: number) => {
                      const d = new Date(t);
                      return win[win.length - 1].ts - win[0].ts > 400 * 86_400_000
                        ? String(d.getFullYear())
                        : d.toISOString().slice(5, 10);
                    }}
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                    width={34}
                    tickFormatter={(v: number) => `${v}σ`}
                    label={{
                      value: "σ vs each leg's own history",
                      angle: -90,
                      position: "insideLeft",
                      style: { fill: "#475569", fontSize: 9 },
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
                      new Date(Number(t)).toISOString().slice(0, 10)
                    }
                    formatter={(v: number, name: string, item: { payload?: Row }) => {
                      const p = item.payload;
                      const sig = `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(1)}σ`;
                      if (name === "cot")
                        return [
                          p?.cot_native != null
                            ? `${p.cot_native}% of OI (${sig})`
                            : sig,
                          "Hedge-fund S&P futures",
                        ];
                      if (name === "vix")
                        return [
                          p?.vix_native != null
                            ? `${p.vix_native.toFixed(1)} (${sig})`
                            : sig,
                          "VIX",
                        ];
                      if (name === "funding")
                        return [
                          p?.funding_native != null
                            ? `${p.funding_native > 0 ? "+" : ""}${p.funding_native}%/yr (${sig})`
                            : sig,
                          "BTC funding",
                        ];
                      if (name === "hy")
                        return [
                          p?.hy_native != null ? `${p.hy_native}bp (${sig})` : sig,
                          "HY spread",
                        ];
                      return [String(v), name];
                    }}
                  />
                  <ReferenceLine y={0} stroke="#475569" />
                  <ReferenceLine y={2} stroke="#334155" strokeDasharray="4 4" />
                  <ReferenceLine y={-2} stroke="#334155" strokeDasharray="4 4" />
                  {(Object.keys(LEGS) as LegKey[]).map(
                    (k) =>
                      on[k] && (
                        <Line
                          key={k}
                          dataKey={k}
                          name={k}
                          stroke={LEGS[k].color}
                          dot={false}
                          strokeWidth={k === "cot" ? 2 : 1.3}
                          connectNulls
                          isAnimationActive={false}
                        />
                      ),
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
            One σ scale, four clocks: each leg is z-scored against its own
            served history (
            <span className="text-sky-400">futures positioning</span> vs 3y
            trailing — the actual signal z;{" "}
            <span className="text-amber-400">VIX</span> and{" "}
            <span className="text-red-400">HY spread</span> vs ~3y;{" "}
            <span className="text-orange-400">BTC funding</span> vs ~6m).
            Hover for native values. Below −2σ on positioning = flushed; above
            +2σ on VIX/HY = active stress. Legs update at different speeds —
            that ordering (funding → futures → spreads → monthly FINRA) IS the
            signal.
            {data.btc.perp && (
              <>
                {" "}BTC perp now: ${(data.btc.perp.oi_usd / 1e9).toFixed(2)}B
                open interest at $
                {Math.round(data.btc.perp.mark_price).toLocaleString()}.
              </>
            )}{" "}
            {data.relationship}
          </p>
        </>
      )}
    </Panel>
  );
}

function legValue(data: MarginFast, k: LegKey): string {
  if (k === "cot") return data.cot.z != null ? `z ${fmtSigned(data.cot.z)}` : "—";
  if (k === "vix")
    return data.vix.current != null ? data.vix.current.toFixed(1) : "—";
  if (k === "funding")
    return data.btc.perp ? `${fmtSigned(data.btc.perp.funding_ann_pct)}%/yr` : "—";
  return data.hy.current_bp != null ? `${data.hy.current_bp}bp` : "—";
}

function fmtSigned(v: number): string {
  return `${v > 0 ? "+" : ""}${v}`;
}

function DateInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type="date"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded border border-panelborder bg-slate-900/60 px-1.5 py-0.5 font-mono text-[10px] text-slate-300 [color-scheme:dark]"
    />
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

function FastBanner({
  data,
  slowState,
}: {
  data: MarginFast;
  slowState: LeverageState | null | undefined;
}) {
  const state = data.state;
  if (!state) {
    return (
      <div className="rounded border border-panelborder bg-slate-900/50 px-3 py-2 text-xs text-slate-500">
        Fast-leverage state unavailable (COT or VIX source missing) — the chart
        below still shows whatever legs are live.
      </div>
    );
  }
  const pb = data.playbook[state];
  const st = FAST_STYLE[state];
  const s12 = pb.stats.fwd12m;
  const s1 = pb.stats.fwd1m;
  const cross = slowState ? data.cross_read[state]?.[slowState] : null;
  return (
    <div
      className="rounded-lg border px-4 py-3"
      style={{ backgroundColor: st.bg, borderColor: st.border }}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm font-bold tracking-wide" style={{ color: st.color }}>
          {state.replace("_", " ")}
        </span>
        <span className="text-xs text-slate-300">{pb.label}</span>
        <span className="ml-auto font-mono text-[11px] text-slate-400">
          COT {data.cot.date?.slice(5) ?? "—"} · VIX {data.vix.date?.slice(5) ?? "—"}
        </span>
      </div>
      {/* Prescriptive line: frozen 2006-2026 study stats for THIS state */}
      <p className="mt-1.5 text-xs leading-relaxed text-slate-300">
        <span className="font-semibold" style={{ color: st.color }}>
          {s12.pct_pos}% of {s12.n}
        </span>{" "}
        weeks in this state saw the S&amp;P HIGHER 12 months later (median{" "}
        {s12.median > 0 ? "+" : ""}
        {s12.median}%, worst {s12.worst}%); 1 month out: {s1.pct_pos}% higher,
        median {s1.median > 0 ? "+" : ""}
        {s1.median}%. {pb.episodes} distinct episodes since 2006. {pb.read}
      </p>
      <p className="mt-1 text-xs font-medium leading-relaxed text-slate-200">
        → {pb.action}
      </p>
      {cross && (
        <p className="mt-1.5 border-t border-slate-700/50 pt-1.5 text-xs leading-relaxed text-slate-300">
          <span
            className="font-semibold uppercase tracking-wide text-[10px]"
            style={{ color: st.color }}
          >
            × monthly {slowState}:
          </span>{" "}
          {cross}
        </p>
      )}
      <DeepLine deep={data.deep} slowState={slowState} />

      <p className="mt-1 text-[10px] text-slate-500">
        Stats frozen from one pre-registered evaluation (2006–2026, weekly obs
        overlap — episode counts are the honest n). Composite state = COT + VIX;
        BTC funding and HY spread are faster confirmation legs, not scored.
      </p>
    </div>
  );
}

const STRESS_COLOR: Record<string, string> = {
  SHOCK: "#fb923c",
  AFTERSHOCK: "#c084fc",
  COMPLACENT: "#fbbf24",
  NORMAL: "#34d399",
};

/** The 75-year line: live realized-vol stress state crossed with the monthly
 *  leverage state, with the frozen 1951-2026 matrix stats for that cell. */
function DeepLine({
  deep,
  slowState,
}: {
  deep: MarginFast["deep"];
  slowState: LeverageState | null | undefined;
}) {
  const live = deep?.live;
  if (!live) return null;
  const color = STRESS_COLOR[live.state] ?? "#94a3b8";
  const cell = slowState ? deep.matrix[live.state]?.[slowState] : null;
  const solo = deep.states[live.state];
  const b12 = deep.baseline.fwd12m;
  return (
    <p className="mt-1.5 border-t border-slate-700/50 pt-1.5 text-xs leading-relaxed text-slate-300">
      <span className="font-semibold uppercase tracking-wide text-[10px] text-slate-400">
        75y record (1951–2026):
      </span>{" "}
      vol stress-cycle now reads{" "}
      <span className="font-semibold" style={{ color }}>
        {live.state}
      </span>{" "}
      ({solo.label}; realized vol {live.rvol}%, z {live.vz > 0 ? "+" : ""}
      {live.vz}, Δ20d {live.dv20 > 0 ? "+" : ""}
      {live.dv20}pts).{" "}
      {cell && slowState ? (
        <>
          In {live.state} × monthly {slowState} weeks (
          {cell.episodes} episodes, n={cell.n}):{" "}
          <span className="font-semibold" style={{ color }}>
            {cell.fwd12m.pct_pos}% saw the S&amp;P higher 12 months later
          </span>{" "}
          — median {cell.fwd12m.median > 0 ? "+" : ""}
          {cell.fwd12m.median}%, worst {cell.fwd12m.worst}%; 3 months out:{" "}
          {cell.fwd3m.pct_pos}% higher, median{" "}
          {cell.fwd3m.median > 0 ? "+" : ""}
          {cell.fwd3m.median}%. Baseline all-weeks: {b12.pct_pos}% /{" "}
          {b12.median > 0 ? "+" : ""}
          {b12.median}%.
        </>
      ) : (
        <>
          This state alone: {solo.fwd12m.pct_pos}% of weeks higher 12 months
          later (median {solo.fwd12m.median > 0 ? "+" : ""}
          {solo.fwd12m.median}%, {solo.episodes} episodes) vs baseline{" "}
          {b12.pct_pos}% / {b12.median > 0 ? "+" : ""}
          {b12.median}%.
        </>
      )}
    </p>
  );
}
