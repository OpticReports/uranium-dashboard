import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Distress, DistressBank, DistressRuleState } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";
import { InlineError, Loading, Panel } from "./ui";

/* Bankruptcy & credit distress — studies/distress-signals.md.
   Display only: no series passed the pre-registered test as a recession
   warning. Each row carries its measured role (leads / confirms / does not
   lead); the readings are recomputed live with the study's rule. */

const ROLE_STYLE: Record<string, { color: string; bg: string }> = {
  leads: { color: "#f87171", bg: "rgba(248,113,113,0.12)" },
  confirms: { color: "#fbbf24", bg: "rgba(251,191,36,0.10)" },
};
const NEUTRAL = { color: "#94a3b8", bg: "rgba(148,163,184,0.08)" };

function RoleChip({ role }: { role: string }) {
  const st = ROLE_STYLE[role] ?? NEUTRAL;
  return (
    <span
      className="whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color: st.color, backgroundColor: st.bg, borderColor: `${st.color}55` }}
    >
      {role}
    </span>
  );
}

function pct(v: number | null | undefined, d = 1): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${(100 * v).toFixed(d)}%`;
}

function ruleText(r: DistressRuleState): string {
  if (r.g == null) return "not computable (masked)";
  if (!r.on) return `below the +10% line`;
  return r.fresh_onset ? "NEW crossing of the +10% line this quarter" : "above the +10% line (not a fresh crossing)";
}

const TILES: Record<string, [number, number]> = {
  AK: [0, 0], ME: [0, 10], VT: [1, 9], NH: [1, 10], WA: [2, 1], ID: [2, 2], MT: [2, 3], ND: [2, 4],
  MN: [2, 5], IL: [2, 6], WI: [2, 7], MI: [2, 8], NY: [2, 9], MA: [2, 10], OR: [3, 1], NV: [3, 2],
  WY: [3, 3], SD: [3, 4], IA: [3, 5], IN: [3, 6], OH: [3, 7], PA: [3, 8], NJ: [3, 9], CT: [3, 10],
  RI: [3, 11], CA: [4, 1], UT: [4, 2], CO: [4, 3], NE: [4, 4], MO: [4, 5], KY: [4, 6], WV: [4, 7],
  VA: [4, 8], MD: [4, 9], DE: [4, 10], AZ: [5, 2], NM: [5, 3], KS: [5, 4], AR: [5, 5], TN: [5, 6],
  NC: [5, 7], SC: [5, 8], DC: [5, 9], OK: [6, 4], LA: [6, 5], MS: [6, 6], AL: [6, 7], GA: [6, 8],
  HI: [7, 0], TX: [7, 4], FL: [7, 9],
};

function StateMap({ data }: { data: Distress["states"] }) {
  const vals = data.rows.map((r) => r.per_1000 ?? 0);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  return (
    <div className="grid gap-[3px]" style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))" }}>
      {Array.from({ length: 8 * 12 }).map((_, i) => {
        const r = Math.floor(i / 12);
        const c = i % 12;
        const st = Object.keys(TILES).find((k) => TILES[k][0] === r && TILES[k][1] === c);
        const row = st ? data.rows.find((x) => x.state === st) : undefined;
        if (!row) return <div key={i} />;
        const t = hi > lo ? ((row.per_1000 ?? 0) - lo) / (hi - lo) : 0;
        return (
          <div
            key={i}
            className="rounded-sm px-0.5 py-0.5 text-center leading-tight"
            style={{ backgroundColor: `rgba(235,104,52,${0.15 + 0.75 * t})` }}
            title={`${row.state}: ${row.per_1000?.toFixed(2)} consumer filings per 1,000 (12 months), ${pct(row.consumer_yoy, 0)} vs a year earlier; business Ch 7 ${pct(row.business_ch7_yoy, 0)}`}
          >
            <div className="text-[9px] font-bold text-slate-100">{row.state}</div>
            <div className="font-mono text-[9px] text-slate-200">{row.per_1000?.toFixed(1)}</div>
            <div className="font-mono text-[8px] text-slate-300">{pct(row.consumer_yoy, 0)}</div>
          </div>
        );
      })}
    </div>
  );
}

function BankRow({ b }: { b: DistressBank }) {
  return (
    <tr className="border-b border-panelborder/50 align-top last:border-0">
      <td className="py-1.5 pr-3 text-slate-300">
        {b.label}
        <div className="text-[10px] leading-snug text-slate-500">
          {b.per_peak.join(" · ")} ·{" "}
          {b.false_alarms.length
            ? `false alarms ${b.false_alarms.map((x) => x.slice(0, 4)).join(", ")}`
            : "no false alarms"}
        </div>
        {b.variant_note && (
          <div className="text-[10px] leading-snug text-slate-500">Variant: {b.variant_note}.</div>
        )}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-200">
        {b.latest.toFixed(2)}%
        <div className="text-[10px] text-slate-500">{b.asof}</div>
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">{pct(b.rule.g)}</td>
      <td className="pl-2 py-1.5 text-right">
        <RoleChip role={b.role} />
        {b.qualifiers.length > 0 && (
          <div className="mt-0.5 text-[9px] uppercase tracking-wide text-slate-500">{b.qualifiers.join(", ")}</div>
        )}
      </td>
    </tr>
  );
}

export default function DistressPanel() {
  const [data, setData] = useState<Distress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .distress()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);

  const title = (
    <span className="flex items-center gap-2">
      Bankruptcy &amp; credit distress
      <InfoTip term="distress_panel" />
    </span>
  );
  if (error) return <Panel title={title}><InlineError message={error} /></Panel>;
  if (!data) return <Panel title={title}><Loading /></Panel>;

  const c = data.national.consumer;
  const b = data.national.business;
  const perYear = Object.entries(c.per_1000_by_year).map(([y, v]) => ({ y, v }));
  perYear.push({ y: `${c.asof} (12m)`, v: c.per_1000 });
  const gPath = b.g_path.map((p) => ({ q: p.q, g: p.g == null ? null : 100 * p.g }));
  const stale = data.live_quarters.length === 0;

  return (
    <Panel
      title={title}
      subtitle="Do rising bankruptcies warn before recessions? In the tested record, no: filings rose with them or after"
    >
      <div className="rounded-lg border border-slate-600/60 bg-slate-500/5 px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-sm font-bold tracking-wide text-slate-300">
            NO ALERT — no series passed the pre-registered test
          </span>
          <span className="text-xs text-slate-400">{data.headline}</span>
          <span className="ml-auto font-mono text-[11px] text-slate-500">
            court data {c.asof}
            {stale ? " (study snapshot)" : ""}
          </span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">
              Consumer filings per 1,000 residents (50 states + DC)
              <span className="ml-2 font-mono text-slate-200">{c.per_1000.toFixed(2)}</span>
              <span className="ml-2 font-mono text-slate-400">{pct(c.yoy_12m)} y/y</span>
            </span>
            <RoleChip role={c.role} />
          </div>
          <div className="h-36">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={perYear} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="y" tick={{ fontSize: 9, fill: "#64748b" }} interval={9} />
                <YAxis tick={{ fontSize: 9, fill: "#64748b" }} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 11 }} />
                <Bar dataKey="v" name="per 1,000" fill="#2a78d6" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] leading-snug text-slate-500">{c.record.summary}</p>
        </div>
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">
              Business filings, 4-quarter sum vs a year earlier
              <span className="ml-2 font-mono text-slate-200">{pct(b.rule.g)}</span>
            </span>
            <RoleChip role={b.role} />
          </div>
          <div className="h-36">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={gPath} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="q" tick={{ fontSize: 9, fill: "#64748b" }} interval={23} />
                <YAxis tick={{ fontSize: 9, fill: "#64748b" }} domain={[-60, 60]} allowDataOverflow />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 11 }} />
                <ReferenceLine y={10} stroke="#f87171" strokeDasharray="4 3" />
                <Line
                  dataKey="g"
                  name="% y/y"
                  stroke="#eb6834"
                  dot={false}
                  strokeWidth={1.5}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] leading-snug text-slate-500">
            {b.record.summary} Now: {ruleText(b.rule)} ({b.rule.asof}). Gaps = masked (2005 law change,
            2020-21 support). Business Chapter 11: {pct(data.national.chapter11.rule.g)} (display only, untested).
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-1 text-xs text-slate-300">Bank loan stress (Fed, all commercial banks)</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-slate-500">
              <th className="py-1 pr-3 text-left font-normal">series · record at 1990 / 2001 / 2007</th>
              <th className="px-2 py-1 text-right font-normal">latest</th>
              <th className="px-2 py-1 text-right font-normal">4Q avg y/y</th>
              <th className="pl-2 py-1 text-right font-normal">role</th>
            </tr>
          </thead>
          <tbody>
            {data.bank.map((x) => (
              <BankRow key={x.id} b={x} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <span className="text-xs text-slate-300">
            Consumer filings per 1,000 by state, 12 months to {data.states.asof} (and change vs a year earlier)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-500">consumer</span>
            <RoleChip role={data.states.role} />
            {data.states.business_role && (
              <>
                <span className="text-[10px] text-slate-500">business Ch 7</span>
                <RoleChip role={data.states.business_role} />
              </>
            )}
          </span>
        </div>
        <StateMap data={data.states} />
        <p className="mt-1 text-[10px] leading-snug text-slate-500">{data.states.summary}</p>
      </div>

      <p className="mt-3 text-[10px] leading-snug text-slate-500">
        Failing-firm liabilities (Dun &amp; Bradstreet, discontinued 1997): {data.failure_liabilities.summary}{" "}
        Record from {data.study.doc} ({data.study.spec}, run {data.study.run}).
      </p>
    </Panel>
  );
}
