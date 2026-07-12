import { useMemo, useState } from "react";
import type { Metric } from "../lib/api";
import { Panel, StatusPill } from "./ui";
import { formatValue } from "../lib/format";
import InfoTip from "./InfoTip";

// Leading stack — independent validated leading indicators tracked for breadth.
// Deliberately NOT a fitted model: each indicator is a separate causal channel,
// and the readout is a simple count of how many are flashing. The user can
// include/exclude indicators; exclusions persist in localStorage.

const STORAGE_KEY = "canary.leading.excluded";

function readExcluded(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((v): v is string => typeof v === "string"));
    }
  } catch {
    // Corrupt storage or blocked localStorage — fall back to all-included.
  }
  return new Set();
}

function writeExcluded(excluded: Set<string>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...excluded]));
  } catch {
    // Storage may be unavailable (private mode); toggle still works in-session.
  }
}

export default function LeadingStack({ metrics }: { metrics: Metric[] }) {
  const stack = useMemo(
    () => metrics.filter((m) => m.category === "K"),
    [metrics],
  );
  const [excluded, setExcluded] = useState<Set<string>>(() => readExcluded());

  const toggle = (metricId: string) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(metricId)) next.delete(metricId);
      else next.add(metricId);
      writeExcluded(next);
      return next;
    });
  };

  const title = (
    <>
      Leading stack
      <InfoTip term="leading_stack" />
    </>
  );
  const subtitle =
    "Independent validated indicators — additive breadth, never a fitted model";

  if (stack.length === 0) {
    return (
      <Panel title={title} subtitle={subtitle}>
        <p className="py-4 text-center text-xs text-slate-500">
          No leading-stack indicators reported by the backend.
        </p>
      </Panel>
    );
  }

  // Breadth: among INCLUDED, non-STALE indicators, YELLOW+RED count as flashing.
  const included = stack.filter((m) => !excluded.has(m.metric_id));
  const live = included.filter((m) => m.status !== "STALE");
  const nRed = live.filter(
    (m) => m.status === "RED" || m.status === "CRITICAL",
  ).length;
  const nYellow = live.filter((m) => m.status === "YELLOW").length;
  const flashing = nRed + nYellow;
  const denom = live.length;

  let breadthColor = "text-slate-300";
  if (denom > 0) {
    const frac = flashing / denom;
    if (flashing === 0) breadthColor = "text-emerald-400";
    else if (frac > 1 / 2) breadthColor = "text-red-400";
    else if (frac > 1 / 3) breadthColor = "text-amber-400";
    else breadthColor = nRed > 0 ? "text-amber-400" : "text-slate-300";
  }

  return (
    <Panel title={title} subtitle={subtitle}>
      {/* Breadth readout */}
      <div className="mb-4 rounded-lg border border-panelborder bg-slate-900/50 px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={`text-lg font-bold tracking-tight ${breadthColor}`}>
            {denom > 0
              ? `${flashing} of ${denom} included indicators flashing`
              : "No live included indicators"}
          </span>
          <span className="font-mono text-xs text-slate-400">
            {nRed} red · {nYellow} yellow
          </span>
        </div>
        <p className="mt-1 text-[11px] text-slate-500">
          Breadth across independent causal channels — no weights, no fitted
          model.
        </p>
      </div>

      {/* Indicator rows */}
      <ul className="divide-y divide-panelborder/60">
        {stack.map((m) => {
          const isIncluded = !excluded.has(m.metric_id);
          return (
            <li
              key={m.metric_id}
              className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-1 py-2 sm:flex-nowrap ${
                isIncluded ? "" : "opacity-40"
              }`}
            >
              <input
                type="checkbox"
                checked={isIncluded}
                onChange={() => toggle(m.metric_id)}
                aria-label={`Include ${m.label} in breadth`}
                className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-sky-500"
              />
              <span className="min-w-[180px] text-sm text-slate-200">
                {m.label}
                <InfoTip metricId={m.metric_id} />
              </span>
              <span className="w-24 shrink-0 text-right font-mono text-sm text-slate-100">
                {m.status === "STALE" ? "n/a" : formatValue(m.value, m.unit)}
              </span>
              <span className="shrink-0">
                <StatusPill status={m.status} />
              </span>
              <span className="min-w-0 flex-1 text-[11px] leading-snug text-slate-500">
                {m.note}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
