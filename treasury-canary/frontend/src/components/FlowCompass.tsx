import { useEffect, useState } from "react";
import { api, ApiError, type FlowDestinations } from "../lib/api";
import { InlineError, Loading, Panel } from "./ui";
import InfoTip from "./InfoTip";

// Where is the money going? 20-day drifts across the candidate havens + a
// transparent rule-based regime call (growth scare / rates shock / debasement /
// liquidity crunch). The destination of the haven bid IS the regime.

const SEVERITY_STYLE: Record<string, { border: string; text: string; pulse?: boolean }> = {
  INFO: { border: "border-slate-700", text: "text-slate-300" },
  WARN: { border: "border-amber-600", text: "text-amber-400" },
  RED: { border: "border-red-700", text: "text-red-400" },
  CRITICAL: { border: "border-red-600", text: "text-red-400", pulse: true },
};

// Order + which glossary entry each tile explains itself with.
const TILE_ORDER: { key: string; tip?: string }[] = [
  { key: "stocks" },
  { key: "treasuries_10y", tip: "curve_pair" },
  { key: "bills_3m", tip: "flow_bills" },
  { key: "usd", tip: "flow_usd" },
  { key: "gold", tip: "flow_gold" },
  { key: "oil", tip: "flow_oil" },
  { key: "btc", tip: "flow_btc" },
];

function fmtMove(a: { ret_pct?: number | null; chg_bps?: number | null }): string {
  if (a.ret_pct !== undefined && a.ret_pct !== null) {
    return `${a.ret_pct > 0 ? "+" : ""}${a.ret_pct.toFixed(1)}%`;
  }
  if (a.chg_bps !== undefined && a.chg_bps !== null) {
    return `${a.chg_bps > 0 ? "+" : ""}${a.chg_bps.toFixed(0)} bps`;
  }
  return "n/a";
}

function moveColor(a: { ret_pct?: number | null; chg_bps?: number | null }): string {
  const v = a.ret_pct ?? (a.chg_bps !== undefined && a.chg_bps !== null ? a.chg_bps : null);
  if (v === null || v === undefined) return "text-slate-500";
  if (v > 0) return "text-emerald-400";
  if (v < 0) return "text-red-400";
  return "text-slate-300";
}

export default function FlowCompass() {
  const [data, setData] = useState<FlowDestinations | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .flowDestinations()
      .then((d) => alive && setData(d))
      .catch((e: unknown) =>
        alive && setError(e instanceof ApiError ? e.message : "failed to load flows"),
      );
    return () => {
      alive = false;
    };
  }, []);

  const title = (
    <>
      Where is the money going?
      <InfoTip term="flow_compass" />
    </>
  );

  if (error) {
    return (
      <Panel title={title} subtitle="Flow compass — haven destinations classify the regime">
        <InlineError message={error} />
      </Panel>
    );
  }
  if (!data) {
    return (
      <Panel title={title} subtitle="Flow compass — haven destinations classify the regime">
        <Loading />
      </Panel>
    );
  }

  const { regime, assets, window_days } = data;
  const sev = SEVERITY_STYLE[regime.severity] ?? SEVERITY_STYLE.INFO;
  const destinationSet = new Set(regime.destinations);
  const goldMissing = regime.missing_inputs.includes("gold_pct");

  return (
    <Panel
      title={title}
      subtitle={`Flow compass — ${window_days}-day drifts across the candidate havens`}
    >
      {/* Regime banner */}
      <div className={`mb-4 rounded-lg border ${sev.border} bg-slate-900/60 p-3 ${sev.pulse ? "animate-pulse" : ""}`}>
        <div className={`text-sm font-semibold uppercase tracking-wide ${sev.text}`}>
          {regime.severity === "CRITICAL" ? "⚠ " : ""}
          {regime.label}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-300">{regime.description}</p>
        {regime.destinations.length > 0 && (
          <p className="mt-1.5 text-[11px] text-slate-400">
            Money flowing to:{" "}
            <span className="text-slate-200">
              {regime.destinations.map((d) => d.replace(/_/g, " ")).join(" · ")}
            </span>
          </p>
        )}
      </div>

      {/* Asset tiles */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {TILE_ORDER.map(({ key, tip }) => {
          const a = assets[key];
          if (!a) return null;
          const isDest = destinationSet.has(key);
          return (
            <div
              key={key}
              className={`rounded-lg border p-2.5 ${
                isDest ? "border-sky-600 bg-sky-950/30" : "border-slate-800 bg-slate-900/40"
              }`}
            >
              <div className="text-[10px] uppercase tracking-wide text-slate-400">
                {a.label}
                {tip && <InfoTip term={tip} />}
              </div>
              <div className={`mt-1 font-mono text-lg ${moveColor(a)}`}>{fmtMove(a)}</div>
              <div className="mt-1 text-[10px] leading-snug text-slate-500">{a.role}</div>
              {isDest && (
                <div className="mt-1 text-[10px] font-semibold text-sky-400">← haven bid</div>
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-3 text-[11px] text-slate-500">
        Rule-based drift classifier, fully transparent — not a prediction.
        {goldMissing &&
          " Gold requires the FMP key on the canary service (FMP_API_KEY) — currently n/a."}
      </p>
    </Panel>
  );
}
