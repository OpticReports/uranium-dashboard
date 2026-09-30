import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SeverityHistory } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { InlineError, Loading, Panel } from "./ui";

/* Severity over time (studies/severity-history.md). Each point re-runs today's
   index code on what was published by that month; early points use fewer
   inputs. Recession starts and the nearest past readings are the analogs. */

const LINE = "#38bdf8";
const SEVERE = "#f87171";
const MILD = "#fbbf24";

function fmtMonth(m: string): string {
  const [y, mo] = m.split("-");
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(mo) - 1]} ${y}`;
}

export default function SeverityHistoryPanel() {
  const [data, setData] = useState<SeverityHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .severityHistory()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);

  const rows = useMemo(
    () =>
      (data?.series ?? []).map((r) => ({
        month: r.month,
        score: r.drawn ? r.score : null,
        live: r.live,
        total: r.total,
      })),
    [data],
  );

  const title = "Severity over time";
  if (error) return <Panel title={title}><InlineError message={`Failed to load /severity/history: ${error}`} /></Panel>;
  if (!data) return <Panel title={title}><Loading label="Rebuilding severity history…" /></Panel>;

  const last = rows[rows.length - 1];
  const yearAgo = rows[rows.length - 13];
  const threeAgo = rows[rows.length - 37];
  // like for like: the rebuilt current month vs rebuilt months back
  const trend = (a?: { score: number | null }) =>
    a && a.score != null && last?.score != null
      ? `${last.score - a.score >= 0 ? "+" : ""}${(last.score - a.score).toFixed(0)}`
      : "—";
  const starts = data.analogs.recession_starts;
  const s2007 = starts.find((s) => s.peak.startsWith("2007"));
  const s2001 = starts.find((s) => s.peak.startsWith("2001"));
  const calm = data.analogs.nearest.filter((n) => !n.already_in_recession && !n.recession_within_24m);

  return (
    <Panel
      title={title}
      subtitle="Is the gun getting bigger? The index replayed month by month since 1986, with past recessions as analogs"
    >
      <div className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-300">
        <span>
          Today <span className="font-mono text-slate-100">{data.today.score?.toFixed(1)}</span>{" "}
          {data.today.class}
        </span>
        <span>
          vs 1 year ago <span className="font-mono">{trend(yearAgo)}</span> · vs 3 years ago{" "}
          <span className="font-mono">{trend(threeAgo)}</span>
        </span>
        {data.pctile_all_inputs != null && (
          <span>
            at or above {data.pctile_all_inputs}% of months since {data.all_inputs_from?.slice(0, 4)} (all inputs
            live; SEVERE in {data.share_severe_all_inputs}% of them)
          </span>
        )}
        {data.today_pctile != null && (
          <span className="text-slate-400">
            {data.today_pctile}% since {data.pctile_from?.slice(0, 4)} on ≥¾ of inputs (SEVERE in{" "}
            {data.share_severe}%)
          </span>
        )}
      </div>

      <div className="h-64" aria-label="Severity index by month since 1986 with NBER recessions shaded">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 2, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis dataKey="month" stroke="#475569" tick={{ fontSize: 10 }} minTickGap={48}
              tickFormatter={(m: string) => m.slice(0, 4)} />
            <YAxis stroke="#475569" tick={{ fontSize: 10 }} width={30} domain={[20, 100]} />
            {data.recessions.map((r) => (
              <ReferenceArea key={r.start} x1={r.start} x2={r.end} fill="#94a3b8" fillOpacity={0.12}
                ifOverflow="extendDomain" />
            ))}
            <ReferenceLine y={data.bands.severe_above} stroke={SEVERE} strokeDasharray="5 4"
              label={{ value: "SEVERE above 60", position: "insideTopLeft", fill: SEVERE, fontSize: 9 }} />
            <ReferenceLine y={data.bands.mild_below} stroke={MILD} strokeDasharray="5 4"
              label={{ value: "MILD below 35", position: "insideBottomLeft", fill: MILD, fontSize: 9 }} />
            <Tooltip
              contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", borderRadius: 6, fontSize: 11 }}
              labelFormatter={(m: string) => fmtMonth(m)}
              formatter={(v: number, _n: string, item: { payload?: { live: number; total: number } }) => [
                `${Number(v).toFixed(1)} (${item.payload?.live} of ${item.payload?.total} components)`,
                "severity",
              ]}
            />
            <Line dataKey="score" stroke={LINE} strokeWidth={1.8} dot={false} isAnimationActive={false}
              connectNulls={false} />
            {data.analogs.recession_starts
              .filter((s) => s.reading != null)
              .map((s) => {
                const [y, m] = s.peak.split("-").map(Number);
                const prev = `${m === 1 ? y - 1 : y}-${String(m === 1 ? 12 : m - 1).padStart(2, "0")}`;
                return (
                  <ReferenceDot key={s.peak} x={prev} y={s.reading as number} r={4} fill={SEVERE}
                    stroke="#0f172a" label={{ value: s.peak.slice(0, 4), position: "top", fill: "#cbd5e1", fontSize: 9 }} />
                );
              })}
            {last && data.today.score != null && (
              <ReferenceDot x={last.month} y={data.today.score} r={5} fill={LINE} stroke="#0f172a"
                label={{ value: "today", position: "top", fill: LINE, fontSize: 9 }} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
        Grey = NBER recessions; red dots = the reading the month before each began. {data.method}
      </p>

      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Recession starts — reading vs what followed
          </h3>
          <table className="mt-1 w-full text-xs">
            <thead>
              <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2 text-left">Began</th>
                <th className="px-2 py-1 text-right">Reading</th>
                <th className="px-2 py-1 text-right">Months</th>
                <th className="px-2 py-1 text-right">Unemp. rise</th>
                <th className="pl-2 py-1 text-right">Real GDP drawdown</th>
              </tr>
            </thead>
            <tbody>
              {data.analogs.recession_starts.map((s) => (
                <tr key={s.peak} className="border-b border-panelborder/50 last:border-0">
                  <td className="py-1 pr-2 text-slate-300">
                    {fmtMonth(s.peak)}
                    {s.exogenous && <span className="text-slate-500"> (pandemic — outside the index)</span>}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-slate-200">
                    {s.reading?.toFixed(0) ?? "—"}
                    <span className="text-[10px] text-slate-500"> {s.live}/{s.total}</span>
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-slate-300">{s.months}</td>
                  <td className="px-2 py-1 text-right font-mono text-slate-300">+{s.unemployment_rise_pp}pp</td>
                  <td className="pl-2 py-1 text-right font-mono text-slate-300">{s.real_gdp_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[10px] text-slate-500">
            These readings use {Math.min(...starts.filter((s) => !s.exogenous).map((s) => s.live ?? 0))}-
            {Math.max(...starts.filter((s) => !s.exogenous).map((s) => s.live ?? 0))} of 23 components (no debt-service
            ratio before 2015); three data points do not show the reading predicts depth.
          </p>
        </div>
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Past stretches within ±{data.analogs.band} of today
          </h3>
          <table className="mt-1 w-full text-xs">
            <thead>
              <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2 text-left">Period</th>
                <th className="px-2 py-1 text-right">Avg</th>
                <th className="px-2 py-1 text-left">During or ≤24m after</th>
                <th className="pl-2 py-1 text-right">Unemp. +24m</th>
              </tr>
            </thead>
            <tbody>
              {data.analogs.nearest.map((n) => (
                <tr key={n.from} className="border-b border-panelborder/50 last:border-0">
                  <td className="py-1 pr-2 text-slate-300">
                    {fmtMonth(n.from)} – {fmtMonth(n.to)}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-slate-200">
                    {n.mean_reading.toFixed(0)}
                    <span className="text-[10px] text-slate-500"> {n.live}/{n.total}</span>
                  </td>
                  <td className="px-2 py-1 text-slate-300">
                    {n.already_in_recession
                      ? "already in recession"
                      : n.recession_within_24m
                        ? `recession began ${fmtMonth(n.recession_within_24m)}`
                        : "no recession"}
                  </td>
                  <td className="pl-2 py-1 text-right font-mono text-slate-300">
                    {n.unemployment_chg_24m == null ? "—" : `${n.unemployment_chg_24m > 0 ? "+" : ""}${n.unemployment_chg_24m}pp`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
        Descriptive only: three recessions the index is built for since 1986 cannot validate it. Household
        debt/GDP is extended back to 1976 with the Fed&apos;s Z.1; the debt-service ratio starts in 2005 on FRED, so
        readings before 2015 run without it and use fewer components than today&apos;s.
        {s2007?.reading != null && s2001?.reading != null
          ? ` The highest pre-recession reading (${s2007.peak.slice(0, 4)}, ${s2007.reading.toFixed(0)}) came before the deepest recession, but ${s2001.peak.slice(0, 4)} read ${s2001.reading.toFixed(0)} and was mild.`
          : ""}
        {calm.map((n) => ` ${n.from.slice(0, 4)}-${n.to.slice(0, 4)} averaged ${n.mean_reading.toFixed(0)} with no recession.`).join("")}
        {" "}Current-vintage data; the weights were set in 2026 with this history in view.
      </p>
    </Panel>
  );
}
