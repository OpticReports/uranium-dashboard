import { useEffect, useState } from "react";
import { api, type StatRegime } from "../lib/api";
import { Panel } from "./ui";

// Statistical regime strip — the board's one hypothesis-free lens (validated
// walk-forward 1977-2026; see backend metrics/stat_regime.py). EXPERIMENTAL,
// descriptive only: never feeds alerts, severity, or the accident composite.

const STATE_COLOR: Record<string, string> = {
  CALM: "#334155",      // recessive slate — calm is the background state
  ELEV: "#f59e0b",
  ELEVATED: "#f59e0b",
  STRESS: "#ef4444",
};

function CurrentChip({ sr }: { sr: StatRegime }) {
  const c = sr.current;
  if (!c) {
    return (
      <span className="rounded border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[11px] text-slate-500">
        current state unavailable (needs FRED 10y tape + model deps)
      </span>
    );
  }
  const col = STATE_COLOR[c.state] ?? "#64748b";
  return (
    <span className="flex items-center gap-2 text-[11px]">
      <span
        className="rounded px-2 py-0.5 font-mono font-bold"
        style={{ color: c.state === "CALM" ? "#94a3b8" : col,
                 backgroundColor: `${col}22`, border: `1px solid ${col}66` }}
      >
        {c.state}
        {c.direction ? ` · ${c.direction === "selloff" ? "▲ yields (selloff)" : "▼ yields (rally)"}` : ""}
      </span>
      <span className="text-slate-500">
        confidence {(c.confidence * 100).toFixed(0)}% · as of {c.asof}
      </span>
    </span>
  );
}

export default function StatRegimeStrip() {
  const [sr, setSr] = useState<StatRegime | null>(null);

  useEffect(() => {
    let alive = true;
    api.statRegime().then((d) => alive && setSr(d)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  if (!sr || sr.hindcast.length === 0) return null;

  const months = sr.hindcast;
  const years: number[] = [];
  for (const m of months) {
    const y = parseInt(m.month.slice(0, 4), 10);
    if (y % 10 === 0 && m.month.endsWith("-01") && !years.includes(y)) years.push(y);
  }

  return (
    <Panel
      title={
        <>
          Statistical regime — Treasury market{" "}
          <span className="ml-1 rounded border border-amber-700/60 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-400">
            experimental
          </span>
        </>
      }
      subtitle="Unsupervised 3-state model on 10y-yield behavior — the hypothesis-free lens. Descriptive only; never feeds alerts."
    >
      <div className="mb-2">
        <CurrentChip sr={sr} />
      </div>
      {/* 49-year monthly strip */}
      <div className="flex h-6 w-full overflow-hidden rounded-sm">
        {months.map((m) => (
          <div
            key={m.month}
            className="h-full grow"
            style={{
              backgroundColor: STATE_COLOR[m.state] ?? "#1e293b",
              opacity: m.state === "CALM" ? 0.55 : 0.9,
              minWidth: 0,
            }}
            title={`${m.month}: ${m.state}${m.dir ? "/" + m.dir : ""}`}
          />
        ))}
      </div>
      <div className="mt-0.5 flex justify-between text-[9px] text-slate-600">
        <span>{months[0].month.slice(0, 4)}</span>
        {years.slice(1, -1).map((y) => (
          <span key={y}>{y}</span>
        ))}
        <span>{months[months.length - 1].month.slice(0, 4)}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: STATE_COLOR.CALM, opacity: 0.55 }} /> calm
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: STATE_COLOR.ELEV }} /> elevated
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: STATE_COLOR.STRESS }} /> stress (hover: selloff vs rally flavor)
        </span>
      </div>
      <p className="mt-2 text-[10px] leading-snug text-slate-500">{sr.validated}</p>
      <p className="mt-1 text-[10px] italic leading-snug text-slate-600">{sr.framing}</p>
    </Panel>
  );
}
