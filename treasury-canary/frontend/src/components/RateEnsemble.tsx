import { useEffect, useState } from "react";
import type { RateEnsemble as RateEnsembleData } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";

/** Fed-decision probability table: Polymarket + Kalshi blended with
 * accuracy-earned weights (Brier-scored at T-7d on resolved meetings). */

const BUCKET_COLOR: Record<string, string> = {
  cut50p: "text-emerald-300",
  cut25: "text-emerald-400",
  hold: "text-slate-200",
  hike25p: "text-rose-300",
};

function Pct({ v, bucket, strong }: { v: number | undefined; bucket: string; strong?: boolean }) {
  if (v === undefined || Number.isNaN(v)) {
    return <span className="text-slate-600">—</span>;
  }
  const pct = Math.round(v * 100);
  const dim = pct < 5 ? "opacity-40" : "";
  return (
    <span className={`${BUCKET_COLOR[bucket] ?? ""} ${dim} ${strong ? "font-semibold" : ""}`}>
      {pct}%
    </span>
  );
}

function meetingLabel(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit", timeZone: "UTC" });
}

export default function RateEnsemble() {
  const [data, setData] = useState<RateEnsembleData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      api
        .rateEnsemble()
        .then((d) => live && setData(d))
        .catch((e) => live && setError(errorMessage(e)));
    void load();
    const t = setInterval(load, 10 * 60 * 1000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  if (error) return <Panel title="Rate-path odds"><InlineError message={error} /></Panel>;
  if (!data) return <Panel title="Rate-path odds"><Loading /></Panel>;

  const srcs = Object.keys(data.weights);
  const wPm = data.weights.polymarket;
  const wKa = data.weights.kalshi;

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          RATE-PATH ODDS — NEXT FOMC MEETINGS
          <InfoTip
            entry={{
              title: "Rate-path odds (accuracy-weighted ensemble)",
              what: "Blend of prediction-market prices for each upcoming FOMC decision, weighted by each source's BACKTESTED forecast accuracy — the weights are earned from history, not assigned.",
              calc: `Each source is scored by the Brier score of its price one week before every resolved FOMC meeting vs the actual outcome (lower = sharper). Weights ∝ 1/Brier with small-sample shrinkage. Current: Polymarket ${Math.round((wPm?.weight ?? 0) * 100)}% (Brier ${wPm?.brier}, n=${wPm?.n}) · Kalshi ${Math.round((wKa?.weight ?? 0) * 100)}% (Brier ${wKa?.brier}, n=${wKa?.n}).`,
              read: "Weights re-learn after every meeting resolves — a source that misprices meetings loses influence automatically.",
              caveat: "Display-only (never feeds the composite). CME FedWatch has no keyless feed and is not yet a column. Prediction markets carry longshot bias at extreme prices; T-7d is one horizon, not a curve.",
            }}
          />
        </span>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
              <th className="py-1.5 pr-3 text-left">Meeting</th>
              {data.buckets.map((b) => (
                <th key={b} className="px-2 py-1.5 text-right">{data.labels[b] ?? b}</th>
              ))}
              <th className="pl-3 py-1.5 text-right text-slate-600">sources</th>
            </tr>
          </thead>
          <tbody>
            {data.meetings.map((m) => (
              <tr key={m.date} className="border-b border-panelborder/50 last:border-0">
                <td className="py-1.5 pr-3 font-medium text-slate-300">{meetingLabel(m.date)}</td>
                {data.buckets.map((b) => (
                  <td key={b} className="px-2 py-1.5 text-right tabular-nums">
                    <Pct v={m.blend[b]} bucket={b} strong />
                    <div className="text-[9px] leading-tight text-slate-500 tabular-nums">
                      {srcs.map((s) => {
                        const v = m.sources[s]?.[b];
                        const letter =
                          s === "polymarket" ? "P" : s === "kalshi" ? "K" :
                          s === "futures" ? "F" : s[0].toUpperCase();
                        return (
                          <span key={s} className="ml-1">
                            {letter}:{v === undefined ? "—" : `${Math.round(v * 100)}`}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                ))}
                <td className="pl-3 py-1.5 text-right text-[9px] text-slate-600">
                  {srcs.filter((s) => m.sources[s] && Object.keys(m.sources[s]).length > 0).length}/{srcs.length}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
        Accuracy-weighted blend:{" "}
        {srcs.map((s, i) => {
          const w = data.weights[s];
          const name = s === "futures" ? "Fed-funds futures (FedWatch-style)"
            : s.charAt(0).toUpperCase() + s.slice(1);
          return (
            <span key={s}>
              {i > 0 && " · "}
              {name}{" "}
              <span className="text-slate-300">{Math.round((w?.weight ?? 0) * 100)}%</span>{" "}
              ({w?.brier != null ? `Brier ${w.brier}, n=${w.n}` : "no history yet — prior weight, earns in"})
            </span>
          );
        })}{" "}
        — scored at T-7d vs resolved outcomes; weights re-learn after each
        meeting. Small print under each number = per-source % (P/K/F).
        Display-only.
      </p>
    </Panel>
  );
}
