import { PLAYBOOK_DATA } from "../lib/playbookData";
import { Panel } from "./ui";

// ---------------------------------------------------------------------------
// Loosened view of the generated `as const` data so we can index dynamically.
// ---------------------------------------------------------------------------

interface AggCell {
  median: number | null;
  n: number;
  min: number | null;
  max: number | null;
}

interface EventData {
  episodes: Array<{ date: string } & Record<string, unknown>>;
  aggregate: Record<string, Record<string, AggCell>>;
}

interface PlaybookShape {
  generated: string;
  horizons: number[];
  events: Record<string, EventData>;
  baseline: Record<string, Record<string, { median: number | null; n: number }>>;
}

const DATA = PLAYBOOK_DATA as unknown as PlaybookShape;

const ASSETS: Array<{ key: string; label: string }> = [
  { key: "equities", label: "Equities (price-only)" },
  { key: "treasury_10y", label: "10y Treasury (approx TR)" },
  { key: "cash", label: "Cash (T-bills)" },
];

const EVENTS: Array<{ key: string; title: string; prescription: string }> = [
  {
    key: "INVERSION_START",
    title: "Sustained inversion begins",
    prescription:
      "Reposition over 1–2 quarters, don't panic-sell: trim equity beta 20–30% of strategic weight (3–6m returns are still flat-positive), park in the front end (cash yields peak by construction), and BEGIN staging into duration. Respect the 1966/2022 failure modes — size so being wrong costs basis points.",
  },
  {
    key: "DIS_INVERSION",
    title: "Re-steepening (the canary)",
    prescription:
      "Maximum defensiveness, with a clock: the next ~6 months are historically the worst equity window (median −5.6%); onset followed at 3/8/5 months in the modern era. Hold maximum permitted duration; check the CAUSE first — a bear steepener (term premium jumping, debasement regime) argues for LESS duration, not more. Write the staged re-entry plan the day this fires: the +19.9%/24m equity number is earned by buying during the recession.",
  },
  {
    key: "SAHM_TRIGGER",
    title: "Sahm trigger",
    prescription:
      "Too late to de-risk (12m forward equities are POSITIVE — you're nearer the bottom than the top). Use it as confirmation, the starting gun for staged equity re-entry (e.g. thirds over two quarters), and the point to harvest duration gains. 1970s caveat: unanchored breakevens void the duration prescription.",
  },
  {
    key: "BREADTH_ALARM",
    title: "Leading-stack majority alarm",
    prescription:
      "Freeze net risk additions; build the defensive book while momentum is still friendly (3m median +8.6%). The reason to act is the 24-month asymmetry: equities −2.7% vs duration +21.9%. N=5 — humility required; demand credit confirmation (HY OAS widening) before conviction.",
  },
];

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function signColor(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "text-slate-500";
  if (v > 0) return "text-emerald-400";
  if (v < 0) return "text-red-400";
  return "text-slate-300";
}

function baselineMedian(asset: string, horizon: string): number | null {
  const cell = DATA.baseline[String(asset)]?.[String(horizon)];
  return cell && typeof cell.median === "number" ? cell.median : null;
}

export default function PlaybookTab() {
  const horizons = DATA.horizons.map((h) => String(h));
  const eqBase = baselineMedian("equities", "12");
  const tyBase = baselineMedian("treasury_10y", "12");
  const cashBase = baselineMedian("cash", "12");

  return (
    <div className="flex flex-col gap-5">
      <Panel
        title="Playbook — what each state has historically meant"
        subtitle={`Event study over monthly data, 1957–2026 · generated ${DATA.generated}`}
      >
        <div className="space-y-2 text-xs leading-relaxed text-slate-400">
          <p>
            For each dashboard state below we measure median forward returns
            across every historical episode, at 3/6/12/24-month horizons.
            Equities are <span className="font-semibold text-slate-300">price-only</span>{" "}
            (dividends omitted on both sides of the comparison); the 10y
            Treasury uses a total-return approximation; gold is omitted (no
            clean free long series).
          </p>
          <p>
            Each state has only 5–10 historical events, so these are{" "}
            <span className="font-semibold text-slate-300">
              medians with wide ranges — priors, not laws
            </span>
            . Compare against the unconditional baseline per 12 months:
            equities {fmtPct(eqBase)} / 10y Treasury {fmtPct(tyBase)} / cash{" "}
            {fmtPct(cashBase)}.
          </p>
        </div>
      </Panel>

      {EVENTS.map((ev) => {
        const data = DATA.events[String(ev.key)];
        if (!data) return null;
        return (
          <Panel key={ev.key} title={ev.title} subtitle={ev.key}>
            {/* Median forward-return table */}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead>
                  <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-3 font-semibold">Asset</th>
                    {horizons.map((h) => (
                      <th key={h} className="px-3 py-2 text-right font-semibold">
                        {h}m fwd
                      </th>
                    ))}
                    <th className="px-3 py-2 text-right font-semibold text-slate-600">
                      baseline 12m
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ASSETS.map((asset) => {
                    const row = data.aggregate[String(asset.key)] ?? {};
                    const base = baselineMedian(asset.key, "12");
                    return (
                      <tr
                        key={asset.key}
                        className="border-b border-panelborder/60 last:border-0"
                      >
                        <td className="py-2 pr-3 text-slate-300">{asset.label}</td>
                        {horizons.map((h) => {
                          const cell = row[String(h)];
                          const med =
                            cell && typeof cell.median === "number"
                              ? cell.median
                              : null;
                          return (
                            <td
                              key={h}
                              className={`px-3 py-2 text-right font-mono ${signColor(med)}`}
                            >
                              {fmtPct(med)}
                              {cell ? (
                                <span className="ml-1 text-[10px] text-slate-600">
                                  (n={cell.n})
                                </span>
                              ) : null}
                            </td>
                          );
                        })}
                        <td className="px-3 py-2 text-right font-mono text-slate-500">
                          {fmtPct(base)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Episodes detail */}
            <details className="mt-3 rounded border border-panelborder bg-slate-900/40 px-3 py-2">
              <summary className="cursor-pointer text-xs font-semibold text-slate-400 hover:text-sky-300">
                Episodes ({data.episodes.length})
              </summary>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-[11px]">
                  <thead>
                    <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
                      <th className="py-1.5 pr-3 font-semibold">Episode</th>
                      {ASSETS.map((a) => (
                        <th key={a.key} className="px-3 py-1.5 font-semibold">
                          {a.label} · {horizons.map((h) => `${h}m`).join(" / ")}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.episodes.map((ep) => (
                      <tr
                        key={ep.date}
                        className="border-b border-panelborder/50 last:border-0"
                      >
                        <td className="py-1.5 pr-3 font-mono text-slate-300">
                          {ep.date}
                        </td>
                        {ASSETS.map((a) => {
                          const raw = ep[String(a.key)];
                          const perH =
                            raw && typeof raw === "object"
                              ? (raw as Record<string, unknown>)
                              : {};
                          return (
                            <td key={a.key} className="px-3 py-1.5 font-mono">
                              {horizons.map((h, i) => {
                                const v = perH[String(h)];
                                const num =
                                  typeof v === "number" && !Number.isNaN(v)
                                    ? v
                                    : null;
                                return (
                                  <span key={h}>
                                    {i > 0 && (
                                      <span className="text-slate-700"> / </span>
                                    )}
                                    <span className={signColor(num)}>
                                      {fmtPct(num)}
                                    </span>
                                  </span>
                                );
                              })}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>

            {/* Prescription */}
            <div className="mt-3 rounded border-l-4 border-amber-500/70 bg-amber-500/5 px-3 py-2.5">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-400">
                Prescription
              </div>
              <p className="text-xs leading-relaxed text-amber-100/90">
                {ev.prescription}
              </p>
            </div>
          </Panel>
        );
      })}

      <p className="text-center text-[10px] text-slate-600">
        Full study with methodology and limitations: PLAYBOOK.md in the repo.
        Research, not investment advice.
      </p>
    </div>
  );
}
