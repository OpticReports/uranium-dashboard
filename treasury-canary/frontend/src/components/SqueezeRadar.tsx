import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { SqueezeRadarData } from "../lib/api";
import { errorMessage } from "../lib/format";
import { InlineError, Loading, Panel } from "./ui";

// Pre-registered scorecard (docs/research/tlt-squeeze-2026, spec v2, frozen
// 2026-08-25). States are the registration's vocabulary, not the canary's
// GREEN/RED bands: a MET *trigger* is the event; MET *fuel* is convexity.
const STATE_STYLE: Record<string, { label: string; cls: string }> = {
  MET: { label: "MET", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40" },
  PARTIAL: { label: "PARTIAL", cls: "bg-amber-500/15 text-amber-300 border-amber-500/40" },
  NOT_MET: { label: "NOT MET", cls: "bg-rose-500/10 text-rose-300/80 border-rose-500/30" },
  UNVERIFIED: { label: "UNVERIFIED", cls: "bg-slate-500/15 text-slate-400 border-slate-500/40" },
  STALE: { label: "STALE", cls: "bg-slate-600/20 text-slate-500 border-slate-600/40" },
};

function ConditionRow({ c }: { c: SqueezeRadarData["fuel"][number] }) {
  const st = STATE_STYLE[c.state] ?? STATE_STYLE.STALE;
  return (
    <tr className="border-b border-panelborder/50 last:border-0">
      <td className="py-1.5 pr-2 font-mono text-xs text-slate-500">{c.id}</td>
      <td
        className="cursor-help py-1.5 pr-2 text-xs text-slate-200 underline decoration-dotted decoration-slate-600 underline-offset-2"
        title={`${c.threshold}. ${c.detail}`}
      >
        {c.label}
      </td>
      <td className="py-1.5 pr-2 text-right font-mono text-xs text-slate-300">
        {c.value !== null && c.value !== undefined ? `${c.value}${c.unit ? ` ${c.unit}` : ""}` : "—"}
      </td>
      <td className="py-1.5 pr-2 text-right text-[10px] text-slate-500">{c.asof ?? ""}</td>
      <td className="py-1.5 text-right">
        <span className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[10px] ${st.cls}`}>
          {st.label}
        </span>
      </td>
    </tr>
  );
}

export default function SqueezeRadar() {
  const [data, setData] = useState<SqueezeRadarData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .squeezeRadar()
        .then((d) => alive && (setData(d), setErr(null)))
        .catch((e) => alive && setErr(errorMessage(e)));
    load();
    const t = setInterval(load, 10 * 60 * 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (err) return <Panel title="Duration Squeeze Radar"><InlineError message={err} /></Panel>;
  if (!data) return <Panel title="Duration Squeeze Radar"><Loading /></Panel>;

  const scoreChip = (label: string, score: number, max: number, hot: boolean) => (
    <span
      className={`rounded border px-2 py-1 font-mono text-xs ${
        hot
          ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
          : "border-panelborder bg-panel text-slate-300"
      }`}
    >
      {label} {score}/{max}
    </span>
  );

  return (
    <Panel
      title="Duration Squeeze Radar"
      subtitle="Positioning is fuel, never ignition — pre-registered scorecard (spec v2, 2026-08-25); triggers ignite on scheduled dates"
      right={
        <div className="flex gap-2">
          {scoreChip("FUEL", data.fuel_score, 4, data.fuel_score >= 3)}
          {scoreChip("TRIGGERS", data.trigger_score, 5, data.trigger_score >= 2)}
        </div>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Fuel — how far a rally travels if ignited
          </h3>
          <table className="w-full">
            <tbody>{data.fuel.map((c) => <ConditionRow key={c.id} c={c} />)}</tbody>
          </table>
        </div>
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Triggers — what actually ignites
          </h3>
          <table className="w-full">
            <tbody>{data.triggers.map((c) => <ConditionRow key={c.id} c={c} />)}</tbody>
          </table>
        </div>
      </div>

      <div className="mt-3 border-t border-panelborder/50 pt-2">
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Trigger calendar (next 45d) — pre-briefs fire at T-3
        </h3>
        <div className="flex flex-wrap gap-2">
          {data.calendar.map((e) => (
            <span
              key={`${e.event}:${e.date}`}
              className="rounded border border-panelborder bg-panel px-2 py-1 font-mono text-[10px] text-slate-300"
            >
              {e.estimated ? "≈" : ""}{e.date} · {e.event}
            </span>
          ))}
          {data.calendar.length === 0 && (
            <span className="text-xs text-slate-500">nothing inside 45 days</span>
          )}
        </div>
      </div>

      <details className="mt-3 text-[11px] text-slate-500">
        <summary className="cursor-pointer select-none">Honesty box</summary>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {data.honesty.map((h, i) => <li key={i}>{h}</li>)}
        </ul>
      </details>
    </Panel>
  );
}
