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

// Correlated indicators grouped into families so breadth isn't overstated when
// one causal channel (e.g. housing) lights up several series at once.
const FAMILIES = [
  {
    id: "housing_capex",
    label: "Housing/Capex",
    members: [
      "leading.permits_yoy",
      "leading.trucks_off_peak",
      "leading.core_capex_yoy",
    ],
  },
  { id: "credit", label: "Credit", members: ["leading.sloos"] },
  { id: "labor", label: "Labor", members: ["leading.temp_help_yoy"] },
  {
    id: "activity",
    label: "Broad activity",
    members: ["leading.cfnai_ma3", "leading.gdpnow", "leading.cp_prob", "leading.wei"],
  },
];

interface FamilyState {
  id: string;
  label: string;
  nLive: number;
  flashing: boolean;
  hasRed: boolean;
}

// A family is LIVE if >=1 member is included and non-STALE; it FLASHES if at
// least half of its included, non-STALE members are YELLOW/RED/CRITICAL.
function familyStates(live: Metric[]): FamilyState[] {
  const byId = new Map(live.map((m) => [m.metric_id, m]));
  const states: FamilyState[] = [];
  for (const fam of FAMILIES) {
    const members = fam.members
      .map((id) => byId.get(id))
      .filter((m): m is Metric => m !== undefined);
    if (members.length === 0) continue;
    const flashing = members.filter(
      (m) =>
        m.status === "YELLOW" || m.status === "RED" || m.status === "CRITICAL",
    );
    states.push({
      id: fam.id,
      label: fam.label,
      nLive: members.length,
      flashing: flashing.length >= members.length / 2 && flashing.length > 0,
      hasRed: flashing.some(
        (m) => m.status === "RED" || m.status === "CRITICAL",
      ),
    });
  }
  return states;
}

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

  // Effective breadth: same include/exclude state, collapsed to families.
  const families = familyStates(live);
  const nFamilies = families.length;
  const famFlashing = families.filter((f) => f.flashing).length;
  const famRed = families.filter((f) => f.flashing && f.hasRed).length;
  let famColor = "text-slate-300";
  if (nFamilies > 0) {
    const frac = famFlashing / nFamilies;
    if (famFlashing === 0) famColor = "text-emerald-400";
    else if (frac > 1 / 2) famColor = "text-red-400";
    else if (frac > 1 / 3) famColor = "text-amber-400";
    else famColor = famRed > 0 ? "text-amber-400" : "text-slate-300";
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
          <span className={`text-sm font-semibold ${famColor}`}>
            {nFamilies > 0
              ? `Effective: ${famFlashing} of ${nFamilies} families flashing`
              : "Effective: no live families"}
            <InfoTip term="effective_breadth" />
          </span>
        </div>
        {families.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {families.map((f) => (
              <span
                key={f.id}
                className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  f.flashing
                    ? f.hasRed
                      ? "border-red-600/60 bg-red-500/10 text-red-400"
                      : "border-amber-600/60 bg-amber-500/10 text-amber-400"
                    : "border-panelborder bg-slate-800/50 text-slate-400"
                }`}
              >
                {f.label} ({f.nLive})
              </span>
            ))}
          </div>
        )}
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
