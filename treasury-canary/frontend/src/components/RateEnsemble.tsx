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
              read: "Weights re-learn after every meeting resolves — a source that misprices meetings loses influence automatically. The sources column counts how many priced each meeting; hover it to see why any of them didn't.",
              caveat: "Display-only (never feeds the composite). The third source — the F: leg under each number — computes the FedWatch method from the fed-funds futures curve (CME's own published probabilities have no keyless feed). A contract price gives its month's AVERAGE rate, which splits into the rate before a decision and the rate after, so one side has to come from a neighbouring month and the other is solved: for a decision early in its month the month mostly measures the NEW rate, so the old one is taken from the prior month's contract (or the chain, or spot EFFR for the nearest meeting) and the new one solved; for a decision late in its month it is the other way round, and the new rate is read off the next month's contract when that month is verified to hold no decision of its own. Solving the small side would amplify quote error by 1 ÷ that side — about 10× for a meeting on the 28th of a 31-day month — so when the next month can't be used, the reading is either flagged or left unpriced. Hover the sources count to see why any source is dark. Prediction markets carry longshot bias at extreme prices; T-7d is one horizon, not a curve.",
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
                  <td
                    key={b}
                    className="px-2 py-1.5 text-right tabular-nums cursor-help"
                    title={[
                      ...srcs.map((s) => {
                        const w = data.weights[s]?.weight ?? 0;
                        const name = s === "futures" ? "Fed-funds futures" :
                          s.charAt(0).toUpperCase() + s.slice(1);
                        const priced = Object.keys(m.sources[s] ?? {}).length > 0;
                        // a source that priced the meeting but not this bucket
                        // is a real zero — the blend counts it as one. Only a
                        // source absent from the whole meeting gets a reason.
                        const v = priced ? m.sources[s]?.[b] ?? 0 : undefined;
                        return `${name}: ${v === undefined ?
                          (m.missing?.[s] ?? "not priced") :
                          `${(v * 100).toFixed(1)}%`}  (weight ${Math.round(w * 100)}%)`;
                      }),
                      ...(m.anchor ? [`futures: ${m.anchor}`] : []),
                      ...(m.soft ? [`futures: ${m.soft}`] : []),
                      `→ blend: ${m.blend[b] !== undefined ?
                        `${(m.blend[b] * 100).toFixed(1)}%` : "—"}  ` +
                      `(weighted avg over sources with a market, renormalized)`,
                    ].join("\n")}
                  >
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
                {(() => {
                  const priced = srcs.filter(
                    (s) => m.sources[s] && Object.keys(m.sources[s]).length > 0,
                  ).length;
                  const reasons = Object.entries(m.missing ?? {}).map(([s, why]) => {
                    const name = s === "futures" ? "Fed-funds futures" :
                      s.charAt(0).toUpperCase() + s.slice(1);
                    return `${name}: ${why}`;
                  });
                  // derive from the count actually shown: never claim every
                  // source priced the meeting when the count says otherwise
                  const tip = reasons.length > 0
                    ? reasons.join("\n")
                    : priced === srcs.length
                      ? "all sources priced this meeting"
                      : "a source did not price this meeting (no reason reported)";
                  return (
                    <td className="pl-3 py-1.5 text-right text-[9px] text-slate-600 cursor-help" title={tip}>
                      {priced}/{srcs.length}
                      {priced < srcs.length && <span className="sr-only"> — {tip}</span>}
                    </td>
                  );
                })()}
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
