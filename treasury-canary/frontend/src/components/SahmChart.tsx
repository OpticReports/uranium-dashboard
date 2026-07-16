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
import type { SahmSeries } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";

interface ChartRow {
  ts: number;
  date: string;
  value: number;
}

function toTs(dateStr: string): number {
  const d = new Date(dateStr);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

export default function SahmChart() {
  const [data, setData] = useState<SahmSeries | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .laborSahm()
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

  const chartRows: ChartRow[] = useMemo(() => {
    if (!data?.series) return [];
    return data.series.map((p) => ({
      ts: toTs(p.date),
      date: p.date,
      value: p.value,
    }));
  }, [data]);

  const domain: [number, number] | undefined =
    chartRows.length > 0
      ? [chartRows[0].ts, chartRows[chartRows.length - 1].ts]
      : undefined;

  return (
    <Panel
      title={
        <>
          Sahm Rule — Real-Time Recession Indicator
          <InfoTip term="labor.sahm" />
        </>
      }
      subtitle="Unemployment momentum; confirms what the curve leads"
    >
      {loading && <Loading label="Loading Sahm series…" />}

      {!loading && error && <InlineError message={error} />}

      {!loading && !error && data && (
        <>
          <StateBanner data={data} />

          {chartRows.length === 0 ? (
            <div className="mt-4 flex h-56 items-center justify-center rounded border border-dashed border-panelborder text-center text-sm text-slate-500">
              <div>
                <p className="font-semibold text-slate-400">
                  Sahm series unavailable
                </p>
                <p className="mt-1 text-xs">
                  No series returned — a FRED_API_KEY may be required for labor
                  data.
                </p>
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <ResponsiveContainer width="100%" height={280}>
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
                    formatter={(value: number | string) => [
                      `${Number(value).toFixed(2)} pp`,
                      "Sahm",
                    ]}
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

                  <ReferenceLine
                    y={data.trigger}
                    stroke="#f59e0b"
                    strokeDasharray="4 3"
                    label={{
                      value: `Sahm trigger (${data.trigger.toFixed(2)})`,
                      position: "insideTopRight",
                      fill: "#f59e0b",
                      fontSize: 10,
                    }}
                  />

                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#38bdf8"
                    dot={false}
                    strokeWidth={1.4}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>

              <div className="mt-1 flex flex-wrap gap-4 px-1 text-[10px] text-slate-500">
                <LegendSwatch color="#38bdf8" label="Sahm value" />
                <LegendSwatch color="#f59e0b" label="Trigger (0.50)" dot />
                <LegendSwatch color="#94a3b8" label="NBER recession" faded />
              </div>
            </div>
          )}

          {data.note && (
            <p className="mt-4 rounded border border-panelborder bg-slate-900/50 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
              {data.note}
            </p>
          )}
          {data.source && (
            <p className="mt-2 text-[10px] text-slate-600">
              Source: {data.source}
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

function StateBanner({ data }: { data: SahmSeries }) {
  const current =
    data.current === null || Number.isNaN(data.current)
      ? "n/a"
      : data.current.toFixed(2);

  if (data.triggered) {
    return (
      <div className="animate-pulse rounded-lg border border-canary-critical bg-canary-critical/15 px-4 py-3">
        <p className="text-sm font-bold uppercase tracking-wide text-red-300">
          ⚠ Sahm Rule triggered (current {current})
        </p>
        <p className="mt-1 text-xs text-red-200/90">
          The indicator is at or above its {data.trigger.toFixed(2)}pp trigger —
          historically consistent with recession onset.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-canary-green/50 bg-canary-green/12 px-4 py-3">
      <p className="text-sm font-bold uppercase tracking-wide text-emerald-300">
        Below trigger (current {current})
      </p>
      <p className="mt-1 text-xs text-emerald-200/80">
        Sahm indicator under its {data.trigger.toFixed(2)}pp threshold; no active
        labor-market recession signal.
      </p>
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
