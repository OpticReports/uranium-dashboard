import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ReferenceDot,
  CartesianGrid,
} from "recharts";
import type { CurveCanary } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import {
  errorMessage,
  formatDate,
  formatMonthYear,
  median,
} from "../lib/format";
import InfoTip from "./InfoTip";

const DEFAULT_PAIR = "3m10y";

interface ChartRow {
  ts: number;
  date: string;
  spread: number;
  negative: number | null; // spread when inverted, else null (for shaded fill)
}

function toTs(dateStr: string): number {
  const d = new Date(dateStr);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

export default function ReSteepenAlert() {
  const [pair, setPair] = useState<string>(DEFAULT_PAIR);
  const [data, setData] = useState<CurveCanary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .curveCanary(pair)
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
  }, [pair]);

  const chartRows: ChartRow[] = useMemo(() => {
    if (!data?.series) return [];
    return data.series.map((p) => ({
      ts: toTs(p.date),
      date: p.date,
      spread: p.spread,
      negative: p.spread < 0 ? p.spread : null,
    }));
  }, [data]);

  const medianLag = useMemo(() => {
    if (!data?.episodes) return null;
    const lags = data.episodes
      .filter((e) => e.sustained && e.lag_to_recession_months !== null)
      .map((e) => e.lag_to_recession_months as number);
    return median(lags);
  }, [data]);

  const availablePairs = useMemo(() => {
    const set = new Set<string>(data?.available_pairs ?? []);
    set.add("3m10y");
    set.add("2s10s");
    set.add(pair);
    return Array.from(set);
  }, [data, pair]);

  const domain: [number, number] | undefined =
    chartRows.length > 0
      ? [chartRows[0].ts, chartRows[chartRows.length - 1].ts]
      : undefined;

  return (
    <Panel
      title={
        <>
          Yield-Curve Canary — Inversion & Re-Steepening
          <InfoTip term="resteepening" />
        </>
      }
      subtitle="The signal that has preceded every modern U.S. recession"
      right={
        <div className="flex flex-wrap gap-1">
          {availablePairs.map((p) => (
            <button
              key={p}
              onClick={() => setPair(p)}
              className={`rounded border px-2 py-1 text-[11px] font-mono transition-colors ${
                p === pair
                  ? "border-sky-500 bg-sky-500/15 text-sky-300"
                  : "border-panelborder text-slate-400 hover:text-slate-200"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      }
    >
      {loading && <Loading label="Loading curve history…" />}

      {!loading && error && <InlineError message={error} />}

      {!loading && !error && data && (
        <>
          <StateBanner data={data} medianLag={medianLag} />

          <ReadoutRow data={data} />

          {data.error || chartRows.length === 0 ? (
            <div className="mt-4 flex h-56 items-center justify-center rounded border border-dashed border-panelborder text-center text-sm text-slate-500">
              <div>
                <p className="font-semibold text-slate-400">
                  Curve history unavailable
                </p>
                <p className="mt-1 text-xs">
                  {data.error ??
                    "No spread series returned — a FRED_API_KEY may be required for curve data."}
                </p>
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart
                  data={chartRows}
                  margin={{ top: 8, right: 16, bottom: 4, left: 0 }}
                >
                  <CartesianGrid stroke="#1e293b" strokeDasharray="2 4" />
                  <XAxis
                    dataKey="ts"
                    type="number"
                    scale="time"
                    domain={domain ?? ["auto", "auto"]}
                    tick={{ fill: "#64748b", fontSize: 10 }}
                    tickFormatter={(t: number) =>
                      new Date(t).getUTCFullYear().toString()
                    }
                    minTickGap={40}
                  />
                  <YAxis
                    tick={{ fill: "#64748b", fontSize: 10 }}
                    width={44}
                    tickFormatter={(v: number) => v.toFixed(1)}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #1e293b",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                    labelFormatter={(t: number | string) =>
                      new Date(Number(t)).toISOString().slice(0, 10)
                    }
                    formatter={(value: number | string, name: string) => {
                      if (name === "negative") return [null, null] as [null, null];
                      return [`${Number(value).toFixed(2)} pp`, "Spread"];
                    }}
                  />

                  {/* NBER recession bands */}
                  {data.recessions.map((r, i) => (
                    <ReferenceArea
                      key={`rec-${i}`}
                      x1={toTs(r.start)}
                      x2={toTs(r.end)}
                      fill="#94a3b8"
                      fillOpacity={0.12}
                      stroke="none"
                    />
                  ))}

                  <ReferenceLine y={0} stroke="#f59e0b" strokeDasharray="4 3" />

                  {/* Full spread line */}
                  <Line
                    type="monotone"
                    dataKey="spread"
                    stroke="#38bdf8"
                    dot={false}
                    strokeWidth={1.4}
                    isAnimationActive={false}
                  />
                  {/* Inverted (negative) region emphasized in red */}
                  <Area
                    type="monotone"
                    dataKey="negative"
                    stroke="#ef4444"
                    strokeWidth={1.4}
                    fill="#ef4444"
                    fillOpacity={0.25}
                    connectNulls={false}
                    isAnimationActive={false}
                  />

                  {/* Dis-inversion markers for sustained episodes */}
                  {data.episodes
                    .filter((e) => e.dis_inversion)
                    .map((e, i) => (
                      <ReferenceDot
                        key={`dis-${i}`}
                        x={toTs(e.dis_inversion as string)}
                        y={0}
                        r={e.sustained ? 5 : 3}
                        fill={e.sustained ? "#dc2626" : "#f59e0b"}
                        stroke="#020617"
                        strokeWidth={1}
                        isFront
                      />
                    ))}
                </ComposedChart>
              </ResponsiveContainer>

              <div className="mt-1 flex flex-wrap gap-4 px-1 text-[10px] text-slate-500">
                <LegendSwatch color="#38bdf8" label="Spread" />
                <LegendSwatch color="#ef4444" label="Inverted (spread < 0)" />
                <LegendSwatch color="#94a3b8" label="NBER recession" faded />
                <LegendSwatch color="#dc2626" label="Dis-inversion (sustained)" dot />
                <LegendSwatch color="#f59e0b" label="Dis-inversion (brief)" dot />
              </div>
            </div>
          )}

          <EpisodeCallouts data={data} />

          <p className="mt-4 rounded border border-panelborder bg-slate-900/50 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
            Historically, recession onset has tended to follow re-steepening after
            a sustained inversion; this is an <em>association, not causation</em>.
            Post-2000 lead times have been longer and noisier (2022–24 was
            unusually protracted). Treat as one input among many.
          </p>
        </>
      )}
    </Panel>
  );
}

function StateBanner({
  data,
  medianLag,
}: {
  data: CurveCanary;
  medianLag: number | null;
}) {
  const state = data.state;

  if (state === "RE_STEEPENING") {
    return (
      <div className="animate-pulse rounded-lg border border-canary-critical bg-canary-critical/15 px-4 py-3">
        <p className="text-sm font-bold uppercase tracking-wide text-red-300">
          ⚠ Re-steepening in progress
        </p>
        <p className="mt-1 text-xs text-red-200/90">
          Curve dis-inverted on{" "}
          <span className="font-mono">{formatDate(data.dis_inversion_date)}</span>{" "}
          after <span className="font-mono">{data.days_inverted}</span> days
          inverted; historically recession onset followed prior dis-inversions by
          a median of{" "}
          <span className="font-mono">
            {medianLag === null ? "—" : `~${Math.round(medianLag)}`}
          </span>{" "}
          months.
        </p>
      </div>
    );
  }

  if (state === "INVERTED") {
    return (
      <div className="rounded-lg border border-canary-yellow/60 bg-canary-yellow/12 px-4 py-3">
        <p className="text-sm font-bold uppercase tracking-wide text-amber-300">
          Curve inverted
        </p>
        <p className="mt-1 text-xs text-amber-200/90">
          Depth{" "}
          <span className="font-mono">
            {data.current_depth_bps === null
              ? "—"
              : `${Math.round(data.current_depth_bps)} bps`}
          </span>{" "}
          · inverted for{" "}
          <span className="font-mono">{data.days_inverted}</span> days. Watch for
          dis-inversion — that is the historical trigger to monitor.
        </p>
      </div>
    );
  }

  if (state === "NORMAL") {
    return (
      <div className="rounded-lg border border-canary-green/50 bg-canary-green/12 px-4 py-3">
        <p className="text-sm font-bold uppercase tracking-wide text-emerald-300">
          Curve normal (upward-sloping)
        </p>
        <p className="mt-1 text-xs text-emerald-200/80">
          Spread positive; no active inversion signal on this pair.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-panelborder bg-slate-800/40 px-4 py-3">
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        State unavailable
      </p>
    </div>
  );
}

function ReadoutRow({ data }: { data: CurveCanary }) {
  const spread = data.current_value;
  const bps = data.current_depth_bps;
  return (
    <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat
        label={
          <>
            Current spread
            <InfoTip term="curve_pair" />
          </>
        }
        value={
          spread === null
            ? "n/a"
            : `${spread.toFixed(2)} pp${
                bps === null ? "" : ` (${Math.round(bps)} bps)`
              }`
        }
      />
      <Stat
        label={
          <>
            Days inverted
            <InfoTip term="days_inverted" />
          </>
        }
        value={String(data.days_inverted)}
      />
      <Stat label="Last state change" value={formatDate(data.last_change)} />
      <Stat
        label={
          <>
            Recession prob.
            <InfoTip term="recession_prob" />
          </>
        }
        value={
          data.recession_probability_pct === null
            ? "n/a"
            : `${data.recession_probability_pct.toFixed(1)}%`
        }
      />
    </div>
  );
}

function Stat({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div className="rounded border border-panelborder bg-slate-900/40 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-sm text-slate-100">{value}</p>
    </div>
  );
}

function EpisodeCallouts({ data }: { data: CurveCanary }) {
  const sustained = data.episodes.filter(
    (e) => e.sustained && e.lag_to_recession_months !== null && e.dis_inversion,
  );
  if (sustained.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Prior sustained episodes — dis-inversion to recession lag
      </p>
      <div className="flex flex-wrap gap-2">
        {sustained.map((e, i) => (
          <span
            key={i}
            className="rounded border border-panelborder bg-slate-900/50 px-2.5 py-1 font-mono text-[11px] text-slate-300"
          >
            dis-inverted {formatMonthYear(e.dis_inversion)} → recession +
            {e.lag_to_recession_months} mo
          </span>
        ))}
      </div>
    </div>
  );
}

function LegendSwatch({
  color,
  label,
  faded = false,
  dot = false,
}: {
  color: string;
  label: string;
  faded?: boolean;
  dot?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={dot ? "h-2 w-2 rounded-full" : "h-2 w-3 rounded-sm"}
        style={{ backgroundColor: color, opacity: faded ? 0.35 : 1 }}
      />
      {label}
    </span>
  );
}
