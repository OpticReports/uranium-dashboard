import { useEffect, useState } from "react";
import type { TrackRecord, TrackRecordRow } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage, formatDate } from "../lib/format";
import { InlineError, Loading, Panel } from "./ui";

// Colors for composite bands (mirrors StatusPill's palette semantics).
const BAND_COLOR: Record<string, string> = {
  LOW: "#10b981",
  ELEVATED: "#f59e0b",
  HIGH: "#ef4444",
  SEVERE: "#dc2626",
  NO_DATA: "#6b7280",
};

function fmt1(v: number | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(1);
}

function BandPill({ band }: { band: string | null }) {
  if (!band) return <span className="text-slate-600">—</span>;
  const color = BAND_COLOR[band] ?? "#6b7280";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
      style={{ borderColor: `${color}55`, color, backgroundColor: `${color}14` }}
    >
      {band}
    </span>
  );
}

function Outcome({ v }: { v: number | null }) {
  if (v === null || v === undefined || Number.isNaN(v)) {
    return <span className="text-slate-600">pending</span>;
  }
  return v > 0 ? (
    <span className="font-semibold text-red-400">✓ recession</span>
  ) : (
    <span className="text-emerald-400">✗ none</span>
  );
}

export default function TrackRecordTab() {
  const [data, setData] = useState<TrackRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .trackRecord()
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return <InlineError message={`Failed to load track record: ${error}`} />;
  }
  if (!data) {
    return <Loading label="Loading track record…" />;
  }

  // Newest first.
  const rows: TrackRecordRow[] = [...data.rows].sort((a, b) =>
    a.asof < b.asof ? 1 : a.asof > b.asof ? -1 : 0,
  );

  return (
    <div className="flex flex-col gap-5">
      <Panel
        title="Track record"
        subtitle="The dashboard's own predictions, logged daily and scored in arrears."
      >
        <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
          <Stat label="Predictions logged" value={String(data.n_total)} />
          <Stat label="Resolved (12m elapsed)" value={String(data.n_resolved)} />
          <div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              Brier score
            </div>
            {data.brier !== null ? (
              <div className="font-mono text-2xl font-bold text-slate-100">
                {data.brier.toFixed(3)}
              </div>
            ) : (
              <div className="text-xs italic text-slate-500">
                pending — resolves after 12 months of log
              </div>
            )}
          </div>
        </div>
        {data.brier_note && (
          <p className="mt-2 text-[10px] text-slate-500">{data.brier_note}</p>
        )}
        {data.caveat && (
          <p className="mt-1.5 text-[10px] text-amber-400/90">{data.caveat}</p>
        )}
      </Panel>

      <Panel title="Prediction log" subtitle="Newest first">
        {rows.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">
            No predictions logged yet — rows accrue on each scheduled refresh.
          </p>
        ) : (
          <div className="max-h-[32rem] overflow-auto">
            <table className="w-full min-w-[880px] text-left text-xs">
              <thead className="sticky top-0 z-10 bg-panel">
                <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-3 font-semibold">Date</th>
                  <th className="px-3 py-2 font-semibold">Composite</th>
                  <th className="px-3 py-2 text-right font-semibold">Coverage %</th>
                  <th className="px-3 py-2 text-right font-semibold">
                    Rec prob 12m
                  </th>
                  <th className="px-3 py-2 text-right font-semibold">TP-adj</th>
                  <th className="px-3 py-2 font-semibold">Curve state</th>
                  <th className="px-3 py-2 font-semibold">Pins</th>
                  <th className="px-3 py-2 text-right font-semibold">Sahm</th>
                  <th className="px-3 py-2 font-semibold">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.asof}
                    className="border-b border-panelborder/60 last:border-0 hover:bg-slate-800/30"
                  >
                    <td className="py-2 pr-3 font-mono text-slate-300">
                      {formatDate(r.asof)}
                    </td>
                    <td className="px-3 py-2">
                      <span className="mr-1.5 font-mono text-slate-200">
                        {fmt1(r.composite_score)}
                      </span>
                      <BandPill band={r.composite_band} />
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-400">
                      {fmt1(r.coverage)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">
                      {fmt1(r.rec_prob_12m)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-400">
                      {fmt1(r.rec_prob_adj_12m)}
                    </td>
                    <td className="px-3 py-2 text-slate-400">
                      {r.curve_state ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-400">
                      {r.pins_overall ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-400">
                      {fmt1(r.sahm)}
                    </td>
                    <td className="px-3 py-2">
                      <Outcome v={r.outcome_recession_12m} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="font-mono text-2xl font-bold text-slate-100">{value}</div>
    </div>
  );
}
