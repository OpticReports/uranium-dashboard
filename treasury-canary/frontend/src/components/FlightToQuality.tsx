import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  ReferenceLine,
  Tooltip,
} from "recharts";
import type { Metric, CorrPoint } from "../lib/api";
import { api } from "../lib/api";
import { Panel, StatusPill, InlineError } from "./ui";
import { formatValue, errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";

const CORR_ID = "crossasset.stock_bond_corr";
const FTQ_ID = "crossasset.flight_to_quality";

function findMetric(metrics: Metric[], id: string): Metric | undefined {
  return metrics.find((m) => m.metric_id === id);
}

export default function FlightToQuality({ metrics }: { metrics: Metric[] }) {
  const corr = findMetric(metrics, CORR_ID);
  const ftq = findMetric(metrics, FTQ_ID);

  // The computed rolling-60d correlation SERIES (~10y of daily data) — not the
  // snapshot log, which accrues one point per refresh day and resets on
  // free-tier redeploys (it rendered as a single dot).
  const [history, setHistory] = useState<CorrPoint[] | null>(null);
  const [histError, setHistError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .corrSeries()
      .then((h) => {
        if (alive) setHistory(h.series);
      })
      .catch((e) => {
        if (alive) setHistError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  const corrValue = corr?.value ?? null;
  const regime = interpretRegime(corrValue);

  const histData = history ?? [];

  return (
    <Panel
      title="Flight to Quality"
      subtitle="Stocks ↔ Treasuries — is the diversification hedge intact?"
    >
      <div
        className={`mb-4 rounded-lg border px-3 py-2 ${
          regime.break
            ? "border-canary-red/60 bg-canary-red/12"
            : "border-canary-green/40 bg-canary-green/10"
        }`}
      >
        <p
          className={`text-sm font-bold uppercase tracking-wide ${
            regime.break ? "text-red-300" : "text-emerald-300"
          }`}
        >
          {regime.title}
        </p>
        <p
          className={`mt-1 text-xs ${
            regime.break ? "text-red-200/90" : "text-emerald-200/80"
          }`}
        >
          {regime.detail}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <MetricCard
          metric={corr}
          label={
            <>
              60d stock-bond corr
              <InfoTip metricId="crossasset.stock_bond_corr" />
            </>
          }
        />
        <MetricCard
          metric={ftq}
          label={
            <>
              Flight-to-quality
              <InfoTip metricId="crossasset.flight_to_quality" />
            </>
          }
        />
      </div>

      <div className="mt-4">
        <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
          Correlation regime, rolling 60d (~10 years)
        </p>
        {histError ? (
          <InlineError message={histError} />
        ) : history === null ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : histData.length === 0 ? (
          <p className="text-xs text-slate-500">
            No series available (requires the FRED key).
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={130}>
            <LineChart data={histData} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fill: "#64748b" }}
                tickFormatter={(d: string) => String(d).slice(0, 4)}
                minTickGap={60}
              />
              <YAxis hide domain={[-1, 1]} />
              <ReferenceLine
                y={0}
                stroke="#f59e0b"
                strokeDasharray="3 3"
                label={{ value: "0 = regime line", fontSize: 9, fill: "#f59e0b", position: "insideTopRight" }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  border: "1px solid #1e293b",
                  borderRadius: 6,
                  fontSize: 11,
                }}
                labelFormatter={(l: string | number) => String(l).slice(0, 10)}
                formatter={(v: number | string) => [Number(v).toFixed(3), "corr"]}
              />
              <Line
                type="monotone"
                dataKey="corr"
                stroke="#38bdf8"
                dot={false}
                strokeWidth={1.4}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}

function MetricCard({
  metric,
  label,
}: {
  metric: Metric | undefined;
  label: ReactNode;
}) {
  return (
    <div className="rounded border border-panelborder bg-slate-900/40 px-3 py-2">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">
          {label}
        </p>
        {metric && <StatusPill status={metric.status} />}
      </div>
      <p className="mt-1 font-mono text-lg text-slate-100">
        {metric ? formatValue(metric.value, metric.unit) : "n/a"}
      </p>
      {metric?.note && (
        <p className="mt-0.5 text-[10px] text-slate-500">{metric.note}</p>
      )}
    </div>
  );
}

function interpretRegime(corr: number | null): {
  title: string;
  detail: string;
  break: boolean;
} {
  if (corr === null || Number.isNaN(corr)) {
    return {
      title: "Regime: unknown",
      detail:
        "Stock-bond correlation unavailable — cannot assess the diversification hedge.",
      break: false,
    };
  }
  if (corr > 0.2) {
    return {
      title: "⚠ Regime break — positive correlation",
      detail:
        "Stocks and bonds are selling off together; Treasuries are no longer hedging equity risk. This is the dangerous inflationary/liquidity regime.",
      break: true,
    };
  }
  if (corr > 0) {
    return {
      title: "Hedge weakening",
      detail:
        "Correlation has flipped mildly positive — the diversification benefit is eroding. Watch closely.",
      break: false,
    };
  }
  return {
    title: "Diversification intact",
    detail:
      "Negative stock-bond correlation: Treasuries still rally in equity stress (classic flight-to-quality). The 60/40 hedge is working.",
    break: false,
  };
}
