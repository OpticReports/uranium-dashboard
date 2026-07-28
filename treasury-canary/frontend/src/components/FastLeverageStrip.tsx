import { useEffect, useState } from "react";
import { Line, LineChart, ReferenceLine, ResponsiveContainer, YAxis } from "recharts";
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

export default function FastLeverageStrip({
  slowState,
}: {
  slowState: LeverageState | null | undefined;
}) {
  const [data, setData] = useState<MarginFast | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

          <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <GaugeTile
              label="Hedge-fund S&P futures"
              cadence="weekly · 3d lag"
              value={
                data.cot.z != null
                  ? `z ${data.cot.z > 0 ? "+" : ""}${data.cot.z.toFixed(2)}`
                  : "—"
              }
              sub={
                data.cot.pct != null
                  ? `net ${data.cot.pct}% of OI · Δ4w z ${
                      data.cot.dz4 != null && data.cot.dz4 > 0 ? "+" : ""
                    }${data.cot.dz4 ?? "—"}`
                  : "unavailable"
              }
              tone={tone(data.cot.z, -1, 1)}
              data={data.cot.series
                .filter((p) => p.z != null)
                .map((p) => ({ x: p.date, y: p.z as number }))}
              zeroLine
            />
            <GaugeTile
              label="VIX 20-day change"
              cadence="daily"
              value={
                data.vix.d20 != null
                  ? `${data.vix.d20 > 0 ? "+" : ""}${data.vix.d20.toFixed(1)} pts`
                  : "—"
              }
              sub={
                data.vix.current != null
                  ? `VIX ${data.vix.current.toFixed(1)}`
                  : "unavailable"
              }
              tone={tone(data.vix.d20, null, 8, true)}
              data={data.vix.series.map((p) => ({ x: p.date, y: p.vix }))}
            />
            <GaugeTile
              label="BTC perp funding"
              cadence="hourly"
              value={
                data.btc.perp
                  ? `${data.btc.perp.funding_ann_pct > 0 ? "+" : ""}${data.btc.perp.funding_ann_pct}%/yr`
                  : "—"
              }
              sub={
                data.btc.perp
                  ? `OI $${(data.btc.perp.oi_usd / 1e9).toFixed(2)}B · $${Math.round(
                      data.btc.perp.mark_price,
                    ).toLocaleString()}`
                  : "unavailable"
              }
              tone={
                data.btc.perp == null
                  ? "muted"
                  : data.btc.perp.funding_ann_pct < -5
                    ? "hot"
                    : data.btc.perp.funding_ann_pct > 15
                      ? "warm"
                      : "ok"
              }
              data={data.btc.funding_series.map((p) => ({
                x: p.date,
                y: p.ann_pct,
              }))}
              zeroLine
            />
            <GaugeTile
              label="HY credit spread"
              cadence="daily"
              value={data.hy.current_bp != null ? `${data.hy.current_bp}bp` : "—"}
              sub={
                data.hy.d20_bp != null
                  ? `${data.hy.d20_bp > 0 ? "+" : ""}${data.hy.d20_bp}bp / 20d`
                  : "unavailable"
              }
              tone={tone(data.hy.d20_bp, null, 50, true)}
              data={data.hy.series.map((p) => ({ x: p.date, y: p.bp }))}
            />
          </div>

          <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
            {data.relationship}
          </p>
        </>
      )}
    </Panel>
  );
}

/** muted = no data · ok = benign · warm = watch · hot = stress */
function tone(
  v: number | null | undefined,
  lowHot: number | null,
  hiWarm: number,
  hiIsHot = false,
): "muted" | "ok" | "warm" | "hot" {
  if (v == null) return "muted";
  if (lowHot != null && v <= lowHot) return "hot";
  if (v >= hiWarm) return hiIsHot ? "hot" : "warm";
  return "ok";
}

const TONE_COLOR = {
  muted: "#475569",
  ok: "#34d399",
  warm: "#fbbf24",
  hot: "#fb923c",
} as const;

function GaugeTile({
  label,
  cadence,
  value,
  sub,
  tone,
  data,
  zeroLine,
}: {
  label: string;
  cadence: string;
  value: string;
  sub: string;
  tone: keyof typeof TONE_COLOR;
  data: Array<{ x: string; y: number }>;
  zeroLine?: boolean;
}) {
  const color = TONE_COLOR[tone];
  return (
    <div className="rounded border border-panelborder bg-slate-900/40 px-2.5 py-2">
      <div className="flex items-baseline justify-between gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          {label}
        </span>
        <span className="whitespace-nowrap text-[9px] text-slate-600">{cadence}</span>
      </div>
      <div className="mt-0.5 font-mono text-sm font-bold" style={{ color }}>
        {value}
      </div>
      <div className="text-[10px] text-slate-500">{sub}</div>
      <div className="mt-1 h-9">
        {data.length > 1 && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <YAxis hide domain={["auto", "auto"]} />
              {zeroLine && (
                <ReferenceLine y={0} stroke="#334155" strokeDasharray="2 2" />
              )}
              <Line
                dataKey="y"
                stroke={color}
                dot={false}
                strokeWidth={1.2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
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
        Fast-leverage state unavailable (COT or VIX source missing) — the tiles
        below still show whatever legs are live.
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
      <p className="mt-1 text-[10px] text-slate-500">
        Stats frozen from one pre-registered evaluation (2006–2026, weekly obs
        overlap — episode counts are the honest n). Composite state = COT + VIX;
        BTC funding and HY spread are faster confirmation legs, not scored.
      </p>
    </div>
  );
}
