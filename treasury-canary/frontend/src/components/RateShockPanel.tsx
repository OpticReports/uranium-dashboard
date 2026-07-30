import { useEffect, useState } from "react";
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
import type { RateShock, RateShockState } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";
import { InlineError, Loading, Panel } from "./ui";

const STATE_STYLE: Record<
  RateShockState,
  { color: string; bg: string; border: string }
> = {
  SPIKE: { color: "#fbbf24", bg: "rgba(251,191,36,0.10)", border: "rgba(251,191,36,0.5)" },
  PLUNGE: { color: "#38bdf8", bg: "rgba(56,189,248,0.10)", border: "rgba(56,189,248,0.5)" },
  NEUTRAL: { color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.4)" },
};

const REGIME_LABEL: Record<string, string> = {
  POS: "no hedge (corr +)",
  NEG: "hedge intact (corr −)",
  MIXED: "mixed",
};

export default function RateShockPanel() {
  const [data, setData] = useState<RateShock | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .ratesShock()
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

  const st = data?.current.state ? STATE_STYLE[data.current.state] : null;

  return (
    <Panel
      title={
        <>
          Rate Shock — Long Yield × Hedge Regime
          <InfoTip term="rate_shock" />
        </>
      }
      subtitle="Does this 30y move matter for stocks and recession odds? 1977–2026, regime-aware"
    >
      {loading && <Loading label="Loading rate-shock study…" />}
      {!loading && error && <InlineError message={error} />}

      {!loading && !error && data && (
        <>
          <div
            className="rounded-lg border px-4 py-3"
            style={
              st
                ? { backgroundColor: st.bg, borderColor: st.border }
                : { borderColor: "#334155" }
            }
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span
                className="text-sm font-bold tracking-wide"
                style={{ color: st?.color ?? "#94a3b8" }}
              >
                {data.current.state ?? "UNAVAILABLE"}
              </span>
              {data.current.regime && (
                <span className="text-xs text-slate-300">
                  × {REGIME_LABEL[data.current.regime]}
                </span>
              )}
              <span className="ml-auto font-mono text-[11px] text-slate-400">
                30y{" "}
                {data.current.yield_30y != null
                  ? `${data.current.yield_30y.toFixed(2)}%`
                  : "—"}{" "}
                · Δ60d{" "}
                {data.current.d60_bp != null
                  ? `${data.current.d60_bp > 0 ? "+" : ""}${data.current.d60_bp}bp`
                  : "—"}{" "}
                · corr {data.current.corr ?? "—"} ·{" "}
                {data.current.date?.slice(0, 10) ?? ""}
              </span>
            </div>
            {/* The written analytic, generated server-side from the frozen study */}
            {data.summary.map((p, i) => (
              <p
                key={i}
                className={`mt-1.5 text-xs leading-relaxed ${
                  i === data.summary.length - 1
                    ? "text-slate-400"
                    : "text-slate-300"
                }`}
              >
                {p}
              </p>
            ))}
            {data.cell && (
              <p className="mt-1 text-[10px] leading-relaxed text-amber-400/80">
                Evidence: {data.cell.evidence}
              </p>
            )}
          </div>

          {data.series.length > 1 && (
            <div className="mt-3 h-40">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={data.series}
                  margin={{ top: 6, right: 12, bottom: 2, left: 0 }}
                >
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(d: string) => d.slice(0, 7)}
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                    minTickGap={40}
                  />
                  <YAxis
                    yAxisId="bp"
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                    width={40}
                    tickFormatter={(v: number) => `${v}`}
                    label={{
                      value: "Δ60d bp",
                      angle: -90,
                      position: "insideLeft",
                      style: { fill: "#475569", fontSize: 9 },
                    }}
                  />
                  <YAxis
                    yAxisId="y"
                    orientation="right"
                    stroke="#475569"
                    tick={{ fontSize: 10 }}
                    width={36}
                    domain={["auto", "auto"]}
                    tickFormatter={(v: number) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 6,
                      fontSize: 11,
                    }}
                    formatter={(v: number, name: string) =>
                      name === "d60_bp"
                        ? [`${v > 0 ? "+" : ""}${v}bp`, "Δ60 trading days"]
                        : [`${Number(v).toFixed(2)}%`, "30y yield"]
                    }
                  />
                  <ReferenceLine
                    yAxisId="bp"
                    y={data.thresholds.spike_bp}
                    stroke="#fbbf24"
                    strokeDasharray="5 4"
                    label={{
                      value: "spike +75bp",
                      position: "insideTopRight",
                      style: { fill: "#fbbf24", fontSize: 9 },
                    }}
                  />
                  <ReferenceLine
                    yAxisId="bp"
                    y={data.thresholds.plunge_bp}
                    stroke="#38bdf8"
                    strokeDasharray="5 4"
                    label={{
                      value: "plunge −75bp",
                      position: "insideBottomRight",
                      style: { fill: "#38bdf8", fontSize: 9 },
                    }}
                  />
                  <ReferenceLine yAxisId="bp" y={0} stroke="#475569" />
                  <Line
                    yAxisId="y"
                    dataKey="yield"
                    name="yield"
                    stroke="#64748b"
                    dot={false}
                    strokeWidth={1.2}
                    connectNulls
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="bp"
                    dataKey="d60_bp"
                    name="d60_bp"
                    stroke={st?.color ?? "#94a3b8"}
                    dot={false}
                    strokeWidth={1.8}
                    connectNulls
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
            Colored line: 30y yield change over 60 trading days (the shock
            gauge). Grey: 30y level (right axis). Crossing +75bp = SPIKE
            (recession odds double to 44% vs 21% baseline; NOT a validated
            stock-sell signal). Crossing −75bp = PLUNGE (the study's strongest
            validated equity BUY configuration: 97% of weeks higher 12 months
            later). Regime from the stock-bond correlation tile decides how a
            move transmits. {data.note}
          </p>
        </>
      )}
    </Panel>
  );
}
