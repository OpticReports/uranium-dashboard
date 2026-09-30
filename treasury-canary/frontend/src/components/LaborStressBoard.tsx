import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LaborBoard, LaborBoardState, LaborStripItem } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";
import { InlineError, Loading, Panel } from "./ui";

/* Labor Stress Board — studies/labor-stress-board.md.
   Board state: is a LAYOFF-DRIVEN downturn confirmed? (a separations rule AND a
   slack rule lit together). Strip: is the headline unemployment rate too good?
   The two can disagree — today's weakness is on the hiring side. */

const STATE_STYLE: Record<LaborBoardState, { color: string; bg: string; label: string }> = {
  CLEAR: { color: "#34d399", bg: "rgba(52,211,153,0.08)", label: "CLEAR" },
  WATCH: { color: "#fbbf24", bg: "rgba(251,191,36,0.10)", label: "WATCH" },
  ALERT: { color: "#f87171", bg: "rgba(248,113,113,0.12)", label: "ALERT — layoffs confirmed by slack" },
  INCOMPLETE: { color: "#fbbf24", bg: "rgba(251,191,36,0.10)", label: "INCOMPLETE — cannot confirm CLEAR" },
};

const TREND_COLOR = { worse: "#fca5a5", better: "#86efac", flat: "#94a3b8" } as const;

// categorical slots, fixed order (never cycled); A = layoffs, B/C = slack
const RULE_COLOR: Record<string, string> = {
  A1: "#2a78d6", A2: "#1baf7a", A3: "#4a3aa7",
  B1: "#eb6834", B2: "#e87ba4", C1: "#94a3b8",
};

function fmt(v: number | null, unit: string, d = 2): string {
  if (v == null) return "—";
  const s = unit === "%" && Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(d);
  return `${v > 0 && unit !== "%" ? "+" : ""}${s}${unit === "%" ? "%" : unit === "pp" ? "pp" : ""}`;
}

function StripRow({ it, boardMonth }: { it: LaborStripItem; boardMonth: string | null }) {
  return (
    <tr className="border-b border-panelborder/50 last:border-0 align-top">
      <td className="py-1.5 pr-3 text-slate-300">
        {it.label}
        {boardMonth && it.month !== boardMonth && (
          <span className="ml-1 font-mono text-[10px] text-slate-500">({it.month})</span>
        )}
        {it.note && <div className="text-[10px] leading-snug text-slate-500">{it.note}</div>}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-200">
        {it.value != null ? `${it.value}${it.unit === "%" ? "%" : ` ${it.unit}`}` : "—"}
      </td>
      <td
        className="px-2 py-1.5 text-right font-mono tabular-nums"
        style={{ color: it.trend ? TREND_COLOR[it.trend] : "#64748b" }}
      >
        {it.chg_12m != null ? `${it.chg_12m > 0 ? "+" : ""}${it.chg_12m}` : "—"}
      </td>
      <td className="pl-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
        {it.percentile != null ? `${it.percentile}${it.pct_from ? `*` : ""}` : "—"}
      </td>
    </tr>
  );
}

export default function LaborStressBoard() {
  const [data, setData] = useState<LaborBoard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .laborBoard()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);

  const title = (
    <span className="flex items-center gap-2">
      Labor Stress Board
      <InfoTip term="labor_board" />
    </span>
  );
  if (error) return <Panel title={title}><InlineError message={error} /></Panel>;
  if (!data) return <Panel title={title}><Loading /></Panel>;

  const st = data.state ? STATE_STYLE[data.state] : null;
  return (
    <Panel
      title={title}
      subtitle="Layoffs confirmed by slack, beyond the headline rate — plus the hidden-slack strip"
    >
      <div
        className="rounded-lg border px-4 py-3"
        style={st ? { backgroundColor: st.bg, borderColor: `${st.color}80` } : { borderColor: "#334155" }}
      >
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-sm font-bold tracking-wide" style={{ color: st?.color ?? "#94a3b8" }}>
            {st?.label ?? "UNAVAILABLE"}
          </span>
          <span className="text-xs text-slate-300">
            {data.state == null
              ? "no data — the jobs-report month cannot be set (no CPS series available)"
              : data.missing.length > 0
                ? `${data.n_lit} of ${data.n_evaluated} available rules lit — ${data.missing.join(", ")} not yet available for ${data.month}`
                : `${data.n_lit} of ${data.n_rules} rules lit`}
          </span>
          <span className="ml-auto font-mono text-[11px] text-slate-400">jobs data {data.month}</span>
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
          Backtest record: {data.record.text}
        </p>
        <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
          {data.rules.map((r) => (
            <div key={r.id} className="flex items-baseline gap-2 text-xs">
              <span
                className="inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: RULE_COLOR[r.id] }}
                aria-hidden
              />
              <span className="text-slate-300">
                <span className="font-mono text-slate-500">{r.id}</span> {r.label}
                {r.id === "C1" && <span className="text-slate-500"> ({data.c1_source})</span>}
              </span>
              <span
                className="ml-auto whitespace-nowrap font-mono tabular-nums"
                style={{ color: r.lit ? "#f87171" : r.lit == null ? "#94a3b8" : "#cbd5e1" }}
              >
                {fmt(r.value, r.unit, r.unit === "pp" ? 3 : 2)} / {r.threshold}
                {r.unit === "%" ? "%" : ""}
                {r.lit ? " · LIT" : ""}
                {!r.lit && r.watch != null && r.value != null && r.value >= r.watch
                  ? ` · watch ${r.watch} crossed`
                  : ""}
                {r.stale && r.month ? ` · ${r.month}, not yet for ${data.month ?? "the Board month"}` : ""}
                {r.value == null ? " · no data" : ""}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 h-44" aria-label="Each rule's value divided by its trigger; 1.0 is the trigger line">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.history} margin={{ top: 6, right: 12, bottom: 2, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis dataKey="month" stroke="#475569" tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis
              stroke="#475569"
              tick={{ fontSize: 10 }}
              width={36}
              domain={[-1, 2]}
              allowDataOverflow
              tickFormatter={(v: number) => `${v}×`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", borderRadius: 6, fontSize: 11 }}
              formatter={(v: number, name: string) => [`${Number(v).toFixed(2)}× of trigger`, name]}
            />
            <ReferenceLine
              y={1}
              stroke="#f87171"
              strokeDasharray="5 4"
              label={{ value: "trigger", position: "insideTopRight", style: { fill: "#f87171", fontSize: 9 } }}
            />
            <ReferenceLine y={0} stroke="#475569" />
            {data.rules.map((r) => (
              <Line
                key={r.id}
                dataKey={r.id}
                name={`${r.id} ${r.label}`}
                stroke={RULE_COLOR[r.id]}
                dot={false}
                strokeWidth={r.leg === "C" ? 1.2 : 1.6}
                strokeDasharray={r.leg === "C" ? "3 3" : undefined}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
        Each line is a rule's value divided by its trigger, so all share one scale: crossing 1.0 lights
        the rule. Layoff rules (A) must light together with a slack rule (B or the Sahm rule C) for ALERT.
      </p>

      <p className={`mt-2 text-[11px] ${data.ledger.length > 0 ? "text-amber-300" : "text-slate-500"}`}>
        Out-of-sample since {data.ledger_from} data:{" "}
        {data.ledger.length > 0
          ? data.ledger.map((l) => `${l.event} ${l.month}`).join(" · ")
          : "no onsets yet"}
      </p>

      <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Is the headline rate too good? — hidden-slack strip
      </h3>
      {data.strip_verdict && (
        <p className="mt-1 text-[11px] leading-relaxed text-slate-300">{data.strip_verdict}</p>
      )}
      <div className="mt-1 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
              <th className="py-1.5 pr-3 text-left">Measure</th>
              <th className="px-2 py-1.5 text-right">Latest</th>
              <th className="px-2 py-1.5 text-right">12m chg</th>
              <th className="pl-2 py-1.5 text-right">Pctile</th>
            </tr>
          </thead>
          <tbody>
            {data.strip.map((it) => (
              <StripRow key={it.key} it={it} boardMonth={data.month} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
        12-month change colored red when it moves the worse way, green the better way, grey when under
        ±0.05. Percentile of the latest value in the series' own history (* = since 1994, after the CPS
        redesign). A month in brackets = that measure's latest month differs from the Board month
        {data.month ? ` (${data.month})` : ""}. {data.note}
      </p>
    </Panel>
  );
}
