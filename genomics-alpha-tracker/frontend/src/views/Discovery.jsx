import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtMoney, fmtNum, scoreColor } from "../lib/format";

const STATUSES = ["all", "new", "watch", "promoted", "dismissed"];

const STATUS_BADGE = {
  new: "bg-sky-600/20 text-sky-300 border-sky-700",
  watch: "bg-amber-600/20 text-amber-300 border-amber-700",
  promoted: "bg-emerald-600/20 text-emerald-300 border-emerald-700",
  dismissed: "bg-gray-600/20 text-gray-400 border-gray-700",
};

// Discovery panel: the candidate queue produced by the dynamic-universe
// pipeline (Nasdaq healthcare census movers + rotating CT.gov catalyst sweep).
// Every row shows its evidence; Promote adds to the live universe (same path
// as auto-promote), Dismiss records an auditable reason.
export default function Discovery({ onPick }) {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const [cands, sum] = await Promise.all([
        api.discoveryCandidates(),
        api.discoverySummary(),
      ]);
      setRows(cands);
      setSummary(sum);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(
    () => rows.filter((r) => filter === "all" || r.status === filter),
    [rows, filter]
  );

  const runSweep = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.runDiscovery();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const promote = async (symbol) => {
    if (!confirm(`Promote ${symbol} into the live universe?`)) return;
    try {
      await api.promoteCandidate(symbol);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const dismiss = async (symbol) => {
    const reason = prompt(`Dismiss ${symbol} — why? (recorded, auditable)`);
    if (!reason || !reason.trim()) return;
    try {
      await api.dismissCandidate(symbol, reason.trim());
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-4">
      {/* Auto-promote banner: visible whenever the gate is armed */}
      {summary?.auto_promote && (
        <div className="bg-emerald-900/20 border border-emerald-800 rounded-xl px-4 py-2 text-sm">
          <span className="text-emerald-300 font-medium">Auto-promote ON</span>{" "}
          <span className="text-gray-400">
            (hard-gated, max {summary.auto_promote_per_week}/week) · this week:{" "}
          </span>
          {summary.promoted_this_week?.length ? (
            <span className="text-emerald-200 font-semibold">
              {summary.promoted_this_week.join(", ")}
            </span>
          ) : (
            <span className="text-gray-500">no promotions yet</span>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <div className="flex gap-1">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded border ${
                filter === s
                  ? "border-sky-600 bg-sky-700/30 text-sky-200"
                  : "border-edge text-gray-400 hover:text-gray-200"
              }`}
            >
              {s}
              {summary && s !== "all" ? ` (${summary.counts?.[s] ?? 0})` : ""}
            </button>
          ))}
        </div>
        <button
          onClick={runSweep}
          disabled={busy}
          className="bg-sky-700 hover:bg-sky-600 disabled:opacity-50 rounded px-3 py-1"
        >
          {busy ? "Sweeping…" : "Run discovery sweep"}
        </button>
        {summary?.last_run && (
          <span className="text-xs text-gray-500">
            last run: census {summary.last_run.census}, movers {summary.last_run.movers},
            CT.gov checked {summary.last_run.catalyst_checked}, new{" "}
            {summary.last_run.candidates_new}
          </span>
        )}
      </div>
      {error && <div className="text-rose-400 text-sm">⚠ {error}</div>}

      <div className="overflow-x-auto bg-panel border border-edge rounded-xl">
        <table className="w-full text-sm">
          <thead className="text-gray-400 border-b border-edge">
            <tr>
              <Th>Symbol</Th>
              <Th>Name</Th>
              <Th>Score</Th>
              <Th>Mkt cap</Th>
              <Th>Tags</Th>
              <Th>Sources</Th>
              <Th>Evidence</Th>
              <Th>Status</Th>
              <Th>Controls</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.symbol} className="border-b border-edge/50 align-top">
                <td className="px-3 py-2 font-semibold">
                  {r.status === "promoted" ? (
                    <button
                      className="text-sky-400 hover:underline"
                      onClick={() => onPick?.(r.symbol)}
                    >
                      {r.symbol}
                    </button>
                  ) : (
                    r.symbol
                  )}
                </td>
                <td className="px-3 py-2 text-gray-300">{r.name}</td>
                <td className="px-3 py-2 font-bold" style={{ color: scoreColor(r.score) }}>
                  {fmtNum(r.score, 0)}
                </td>
                <td className="px-3 py-2">{fmtMoney(r.market_cap)}</td>
                <td className="px-3 py-2 text-xs text-gray-400">
                  {(r.genomics_tags || []).join(", ") || "—"}
                </td>
                <td className="px-3 py-2 text-xs text-gray-400">
                  {(r.sources || []).join(", ")}
                </td>
                <td className="px-3 py-2 text-xs text-gray-400">
                  <EvidenceCell evidence={r.evidence} />
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`text-xs border rounded-full px-2 py-0.5 ${STATUS_BADGE[r.status] || ""}`}
                    title={r.status_reason || ""}
                  >
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {(r.status === "new" || r.status === "watch") && (
                    <>
                      <button
                        onClick={() => promote(r.symbol)}
                        className="text-xs border border-emerald-800 text-emerald-400 rounded px-2 py-0.5 mr-1 hover:bg-emerald-900/30"
                      >
                        Promote
                      </button>
                      <button
                        onClick={() => dismiss(r.symbol)}
                        className="text-xs border border-rose-800 text-rose-400 rounded px-2 py-0.5 hover:bg-rose-900/30"
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-gray-500">
                  No candidates{filter !== "all" ? ` with status "${filter}"` : ""} —
                  the daily sweep proposes names here (or run one now).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-500">
        Candidates are found automatically (healthcare-census movers + rotating
        ClinicalTrials.gov sweep) so the universe never depends on a human
        remembering a company exists. Promote adds a name to the live universe
        (reversible — deactivate retains history); Dismiss records a reason and
        suppresses re-entry for a config window. Auto-promote gates and caps
        live in <span className="text-gray-400">config/discovery.yaml</span>.
      </p>
    </div>
  );
}

function EvidenceCell({ evidence }) {
  const ev = evidence || {};
  const bits = [];
  if (ev.move_pct !== undefined && ev.move_pct !== null) {
    bits.push(
      <span key="move" className={ev.move_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
        {ev.move_pct >= 0 ? "+" : ""}
        {fmtNum(ev.move_pct, 1)}% on {ev.date}
      </span>
    );
  }
  if (ev.nearest_pcd) {
    bits.push(
      <span key="pcd" className="text-amber-300">
        phase-3 PCD {ev.nearest_pcd}
      </span>
    );
  }
  if (ev.trials?.length) {
    bits.push(
      <span key="trials" title={ev.trials.map((t) => `${t.nct} ${t.phase}: ${t.title}`).join("\n")}>
        {ev.trials.length} trial{ev.trials.length > 1 ? "s" : ""} (hover)
      </span>
    );
  }
  if (!bits.length) return <span>—</span>;
  return (
    <div className="flex flex-col gap-0.5">
      {bits}
    </div>
  );
}

function Th({ children }) {
  return <th className="px-3 py-2 text-left font-medium">{children}</th>;
}
