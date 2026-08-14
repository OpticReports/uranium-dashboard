import React, { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../lib/api";
import { fmtNum, fmtPct, fmtMoney, FLAG_LABELS } from "../lib/format";
import InfoTip from "../components/InfoTip";

// Calls Log: every exact trade call the tracker (or the desk) has made, graded
// against what price actually did — the honest track record that tells us which
// signals carry alpha and which don't.

const STATUS_BADGE = {
  open: "bg-sky-600/20 text-sky-300 border-sky-700",
  target_hit: "bg-emerald-600/20 text-emerald-300 border-emerald-700",
  stopped: "bg-rose-600/20 text-rose-300 border-rose-700",
  expired: "bg-gray-600/20 text-gray-300 border-gray-600",
  closed_manual: "bg-amber-600/20 text-amber-300 border-amber-700",
};

const STATUS_LABEL = {
  open: "Open",
  target_hit: "Target hit",
  stopped: "Stopped out",
  expired: "Time-stop",
  closed_manual: "Closed manually",
};

const signalLabel = (c) =>
  c.flag_type ? FLAG_LABELS[c.flag_type] || c.flag_type : c.source;

// Confidence 0-100 -> a compact colored badge (how hard the book bets it).
function ConfidenceBadge({ value }) {
  if (value === null || value === undefined) return <span className="text-gray-600 text-xs">—</span>;
  const v = Math.round(value);
  const cls = v >= 75 ? "bg-emerald-600/20 text-emerald-300 border-emerald-700"
    : v >= 60 ? "bg-sky-600/20 text-sky-300 border-sky-700"
    : "bg-gray-600/20 text-gray-300 border-gray-600";
  return <span className={`text-xs px-1.5 py-0.5 rounded border font-semibold ${cls}`}>{v}</span>;
}

const retColor = (v) =>
  v === null || v === undefined ? "" : v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "";

export default function CallsLog({ onPick }) {
  const [calls, setCalls] = useState([]);
  const [card, setCard] = useState(null);
  const [perf, setPerf] = useState(null);
  const [paper, setPaper] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(() => {
    api.calls().then(setCalls).catch(() => setCalls([]));
    api.callsScorecard().then(setCard).catch(() => setCard(null));
    api.callsPerformance().then(setPerf).catch(() => setPerf(null));
    api.callsPaper().then(setPaper).catch(() => setPaper(null));
  }, []);
  useEffect(load, [load]);

  const run = async (fn, label) => {
    setBusy(true);
    setNote(null);
    try {
      const res = await fn();
      setNote(`${label}: ${res.length} call(s)`);
      load();
    } catch (e) {
      setNote(`${label} failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const closeCall = async (id) => {
    if (!window.confirm("Close this call at the latest price?")) return;
    try {
      await api.closeCall(id);
      load();
    } catch (e) {
      setNote(`Close failed: ${e.message}`);
    }
  };

  const open = calls.filter((c) => c.status === "open");
  const closed = calls.filter((c) => c.status !== "open");
  const pos = paper?.positions || {};

  return (
    <div className="space-y-4">
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="flex items-start justify-between flex-wrap gap-2">
          <div>
            <h2 className="font-semibold">📒 Calls Log — the tracker grades itself</h2>
            <p className="text-xs text-gray-400 mt-1 max-w-2xl">
              When a signal fires with conviction, the tracker logs an exact call — entry,
              stop, target, time-stop — and then grades it against what price actually did.
              Levels are frozen at fire-time and never edited, so the scorecard below is an
              honest record of which signals pay and which don't.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => run(api.evaluateCalls, "Checked exits")}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded border border-edge hover:bg-ink disabled:opacity-50"
            >
              Check exits now
            </button>
            <button
              onClick={() => run(api.generateCalls, "Scanned for new calls")}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded border border-edge hover:bg-ink disabled:opacity-50"
            >
              Scan for new calls
            </button>
            <button
              onClick={() => setShowForm((s) => !s)}
              className="text-xs px-3 py-1.5 rounded border border-sky-700 text-sky-300 hover:bg-ink"
            >
              {showForm ? "Cancel" : "Log a call"}
            </button>
          </div>
        </div>
        {note && <div className="text-xs text-gray-400 mt-2">{note}</div>}
        {showForm && (
          <ManualCallForm
            onDone={() => {
              setShowForm(false);
              load();
            }}
            onError={(msg) => setNote(msg)}
          />
        )}
      </div>

      {paper?.enabled && <PaperAccount paper={paper} />}

      {card && <Scorecard card={card} />}

      {perf && <PerformanceOverTime perf={perf} />}

      <div className="bg-panel border border-edge rounded-xl p-4">
        <h3 className="font-semibold mb-3">🔴 Open calls ({open.length})</h3>
        {open.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-400 border-b border-edge">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Signal</th>
                  <th className="py-2 pr-3 text-center">Conf<InfoTip term="confidence" /></th>
                  <th className="py-2 pr-3">Called</th>
                  <th className="py-2 pr-3 text-right">Size<InfoTip term="conviction_sizing" /></th>
                  <th className="py-2 pr-3 text-right">Entry</th>
                  <th className="py-2 pr-3 text-right">Stop</th>
                  <th className="py-2 pr-3 text-right">Target</th>
                  <th className="py-2 pr-3 text-right">Last</th>
                  <th className="py-2 pr-3 text-right">Unrealized<InfoTip term="avg_r" /></th>
                  <th className="py-2 pr-3">Exit by<InfoTip term="ref_levels" /></th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {open.map((c) => (
                  <tr key={c.id} className="border-b border-edge/50 hover:bg-ink/50" title={c.thesis}>
                    <td className="py-2 pr-3">
                      <button onClick={() => onPick?.(c.symbol)} className="font-semibold text-sky-400 hover:underline">
                        {c.symbol}
                      </button>
                      <span className="text-gray-500 text-xs ml-2">{c.direction}</span>
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-300">{signalLabel(c)}</td>
                    <td className="py-2 pr-3 text-center"><ConfidenceBadge value={c.confidence} /></td>
                    <td className="py-2 pr-3 text-xs text-gray-400">{c.call_date}</td>
                    <td className="py-2 pr-3 text-right text-xs">
                      {pos[c.id] ? (
                        <span title={`${pos[c.id].shares} sh · cost ${fmtMoney(pos[c.id].cost_basis)} · risk ${fmtMoney(pos[c.id].risk_at_stop)} at stop`}>
                          {fmtPct(pos[c.id].position_pct, 0)}<br />
                          <span className="text-gray-500">{fmtMoney(pos[c.id].market_value)}</span>
                        </span>
                      ) : "—"}
                    </td>
                    <td className="py-2 pr-3 text-right">{fmtNum(c.entry_price, 2)}</td>
                    <td className="py-2 pr-3 text-right text-rose-300">{fmtNum(c.stop_price, 2)}</td>
                    <td className="py-2 pr-3 text-right text-emerald-300">{fmtNum(c.target_price, 2)}</td>
                    <td className="py-2 pr-3 text-right">{fmtNum(c.last_price, 2)}</td>
                    <td className={`py-2 pr-3 text-right ${retColor(c.unrealized_pct)}`}>
                      {fmtPct(c.unrealized_pct)}
                      {c.unrealized_r !== null && c.unrealized_r !== undefined && (
                        <span className="text-xs text-gray-500 ml-1">({fmtNum(c.unrealized_r, 1)}R)</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-400">{c.expires_on}</td>
                    <td className="py-2 text-right">
                      <button
                        onClick={() => closeCall(c.id)}
                        className="text-xs px-2 py-1 rounded border border-edge hover:bg-ink text-gray-300"
                      >
                        Close
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-500 text-sm">
            No open calls. New calls appear automatically when a trigger signal fires with a
            composite score above the bar (tune in <code>config/calls.yaml</code>), or log one manually.
          </div>
        )}
      </div>

      <div className="bg-panel border border-edge rounded-xl p-4">
        <h3 className="font-semibold mb-3">✅ Closed calls ({closed.length})</h3>
        {closed.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-400 border-b border-edge">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Signal</th>
                  <th className="py-2 pr-3 text-center">Conf<InfoTip term="confidence" /></th>
                  <th className="py-2 pr-3">Called → Exited</th>
                  <th className="py-2 pr-3 text-right">Entry → Exit</th>
                  <th className="py-2 pr-3">Outcome</th>
                  <th className="py-2 pr-3 text-right">P&amp;L</th>
                  <th className="py-2 pr-3 text-right">Return</th>
                  <th className="py-2 text-right">R<InfoTip term="avg_r" /></th>
                </tr>
              </thead>
              <tbody>
                {closed.map((c) => (
                  <React.Fragment key={c.id}>
                    <tr className="border-b border-edge/30 hover:bg-ink/50" title={c.thesis}>
                      <td className="py-2 pr-3">
                        <button onClick={() => onPick?.(c.symbol)} className="font-semibold text-sky-400 hover:underline">
                          {c.symbol}
                        </button>
                      </td>
                      <td className="py-2 pr-3 text-xs text-gray-300">{signalLabel(c)}</td>
                      <td className="py-2 pr-3 text-center"><ConfidenceBadge value={c.confidence} /></td>
                      <td className="py-2 pr-3 text-xs text-gray-400">
                        {c.call_date} → {c.exit_date || "—"}
                      </td>
                      <td className="py-2 pr-3 text-right">
                        {fmtNum(c.entry_price, 2)} → {fmtNum(c.exit_price, 2)}
                      </td>
                      <td className="py-2 pr-3">
                        <span className={`text-xs px-2 py-0.5 rounded border ${STATUS_BADGE[c.status] || ""}`}>
                          {STATUS_LABEL[c.status] || c.status}
                        </span>
                      </td>
                      <td className={`py-2 pr-3 text-right ${retColor(pos[c.id]?.realized_pnl)}`}>
                        {pos[c.id] ? fmtMoney(pos[c.id].realized_pnl) : "—"}
                      </td>
                      <td className={`py-2 pr-3 text-right ${retColor(c.return_pct)}`}>{fmtPct(c.return_pct)}</td>
                      <td className={`py-2 text-right ${retColor(c.r_multiple)}`}>{fmtNum(c.r_multiple, 2)}</td>
                    </tr>
                    {c.postmortem?.summary && (
                      <tr className="border-b border-edge/50">
                        <td colSpan={9} className="pb-2 pl-3 pr-3">
                          <div className="text-xs text-gray-400 bg-ink/60 border border-edge/60 rounded px-2 py-1.5">
                            <span className="text-gray-500 uppercase text-[9px] tracking-wide mr-2">why</span>
                            {c.postmortem.summary}
                            {!c.postmortem.hindsight_complete && (
                              <span className="text-gray-600"> (hindsight verdict pending — needs ~10 more bars)</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-500 text-sm">
            Nothing graded yet — closed calls land here with their outcome, return, and R-multiple.
          </div>
        )}
      </div>
    </div>
  );
}

// Paper-trading account: the calls sized into a simulated $100k book so the
// desk can watch account value, not just win rates.
function PaperAccount({ paper }) {
  const rp = paper.total_return_pct;
  const col = (v) => (v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-gray-200");
  const heatHot = paper.portfolio_heat_pct > 0.85 * paper.max_portfolio_heat_pct;
  const tiles = [
    { label: "Realized P&L", value: fmtMoney(paper.realized_pnl), c: col(paper.realized_pnl) },
    { label: "Open P&L", value: fmtMoney(paper.open_pnl), c: col(paper.open_pnl) },
    { label: "Invested", value: fmtMoney(paper.invested) },
    { label: "Gross exposure", value: fmtPct(paper.gross_exposure_pct, 0),
      sub: `cap ${fmtPct(paper.max_gross_exposure_pct, 0)}` },
    { label: "Portfolio heat", value: fmtPct(paper.portfolio_heat_pct, 0),
      sub: `cap ${fmtPct(paper.max_portfolio_heat_pct, 0)}`, c: heatHot ? "text-amber-400" : "" },
    { label: "Open / Closed", value: `${paper.n_open} / ${paper.n_closed}` },
  ];
  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h3 className="font-semibold">💼 Paper account — conviction book</h3>
          <p className="text-xs text-gray-500 mt-1 max-w-xl">
            {fmtMoney(paper.starting_capital)} starting capital, concentrated by conviction: each
            call is sized by its <b>confidence score</b> (bigger positions on higher-confidence
            setups), capped by liquidity, a {fmtPct(paper.max_gross_exposure_pct, 0)} gross-exposure
            limit, and a {fmtPct(paper.max_portfolio_heat_pct, 0)} portfolio-heat limit
            (total risk if every stop hit at once). Not an index — capital piles onto the best
            bets. Simulated — no real orders.
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold">{fmtMoney(paper.account_value)}</div>
          <div className={`text-sm font-semibold ${col(rp)}`}>
            {rp >= 0 ? "+" : ""}{fmtPct(rp)} vs start
          </div>
          <div className="text-[10px] text-gray-500">account value</div>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 mt-3">
        {tiles.map((t) => (
          <div key={t.label} className="bg-ink border border-edge rounded-lg p-2 text-center">
            <div className={`text-sm font-bold ${t.c || "text-gray-200"}`}>{t.value}</div>
            <div className="text-[10px] uppercase tracking-wide text-gray-500">{t.label}</div>
            {t.sub && <div className="text-[9px] text-gray-600">{t.sub}</div>}
          </div>
        ))}
      </div>
      {paper.equity_curve?.length > 2 && (
        <div className="mt-3">
          <div className="text-xs text-gray-400 mb-1">Account value over time</div>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={paper.equity_curve} margin={{ left: 6, right: 10, top: 5 }}>
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} domain={["auto", "auto"]}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={40} />
              <Tooltip contentStyle={{ background: "#121826", border: "1px solid #1f2937", fontSize: 12 }}
                formatter={(v) => fmtMoney(v)} />
              <ReferenceLine y={paper.starting_capital} stroke="#4b5563" strokeDasharray="3 3" />
              <Line type="stepAfter" dataKey="equity" stroke="#38bdf8" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// The learning-loop instrument: is call quality actually improving over time?
// Equity curve (cumulative R) + rolling win rate/avg R, plus month-made
// cohorts — later cohorts beating earlier ones is what "learning" looks like.
function PerformanceOverTime({ perf }) {
  const tooltipStyle = { background: "#121826", border: "1px solid #1f2937", fontSize: 12 };
  const enough = (perf.closed_calls || 0) >= 5;
  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-1">
        <h3 className="font-semibold">📈 Call strength over time — is the loop learning?</h3>
        <span className="text-xs text-gray-500">
          {perf.closed_calls} closed call(s) · cumulative {fmtNum(perf.cum_r, 1)}R
        </span>
      </div>
      <p className="text-xs text-gray-500 mb-3">{perf.note}</p>

      {!enough ? (
        <div className="text-sm text-gray-500 border border-edge rounded-lg p-3">
          Fewer than 5 closed calls — the lines start drawing once the record exists.
          The flag-cohort table below moves first (flags accrue faster than calls).
        </div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-gray-400 mb-1">
              Equity curve (cumulative R by exit date)<InfoTip term="equity_curve" />
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={perf.equity_curve} margin={{ left: -20, right: 10, top: 5 }}>
                <CartesianGrid stroke="#1f2937" />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={40} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
                <Tooltip contentStyle={tooltipStyle} />
                <ReferenceLine y={0} stroke="#4b5563" />
                <Line type="stepAfter" dataKey="cum_r" name="cumulative R" stroke="#38bdf8" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">
              Rolling win rate & avg R (last {perf.rolling_window} calls)<InfoTip term="rolling_perf" />
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={perf.rolling} margin={{ left: -20, right: 10, top: 5 }}>
                <CartesianGrid stroke="#1f2937" />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={40} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
                <Tooltip contentStyle={tooltipStyle} />
                <ReferenceLine y={0} stroke="#4b5563" />
                <Line type="monotone" dataKey="win_rate" name="win rate" stroke="#34d399" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="avg_r" name="avg R" stroke="#f59e0b" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {(perf.monthly_cohorts?.length > 0 || perf.flag_cohorts?.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-4 mt-3 pt-3 border-t border-edge/60">
          <CohortTable
            title={<>Call cohorts by month made<InfoTip term="cohorts" /></>}
            rows={perf.monthly_cohorts}
            cols={[["n", (r) => r.n], ["win", (r) => fmtPct(r.win_rate, 0)], ["avg R", (r) => fmtNum(r.avg_r, 2)]]}
          />
          <CohortTable
            title={<>Flag cohorts by fire month (1-month result vs sector)<InfoTip term="signal_track_record" /></>}
            rows={perf.flag_cohorts}
            cols={[["n", (r) => r.n], ["hit", (r) => fmtPct(r.hit_rate, 0)], ["avg excess", (r) => fmtPct(r.avg_excess)]]}
          />
        </div>
      )}
    </div>
  );
}

function CohortTable({ title, rows, cols }) {
  if (!rows?.length) {
    return (
      <div>
        <div className="text-xs text-gray-400 mb-1">{title}</div>
        <div className="text-xs text-gray-600">no data yet</div>
      </div>
    );
  }
  return (
    <div>
      <div className="text-xs text-gray-400 mb-1">{title}</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-gray-500 border-b border-edge">
            <th className="py-1 pr-2">month</th>
            {cols.map(([label]) => <th key={label} className="py-1 pr-2 text-right">{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.month} className={`border-b border-edge/40 ${r.n < 10 ? "text-gray-600" : "text-gray-300"}`}>
              <td className="py-1 pr-2">{r.month}{r.n < 10 && <span className="text-gray-700"> (low n)</span>}</td>
              {cols.map(([label, fn]) => <td key={label} className="py-1 pr-2 text-right">{fn(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Scorecard({ card }) {
  const o = card.overall;
  const tiles = [
    { label: "Calls made", value: o.calls },
    { label: "Open", value: o.open },
    { label: "Closed", value: o.closed },
    { label: "Win rate", value: fmtPct(o.win_rate, 0), term: "win_rate" },
    { label: "Avg return", value: fmtPct(o.avg_return_pct) },
    { label: "Avg R", value: fmtNum(o.avg_r, 2), term: "avg_r" },
    { label: "Total R", value: fmtNum(o.total_r, 1), term: "total_r" },
  ];
  const signals = Object.entries(card.by_signal || {});
  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <h3 className="font-semibold mb-3">🎯 Scorecard</h3>
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
        {tiles.map((t) => (
          <div key={t.label} className="bg-ink border border-edge rounded-lg p-2 text-center">
            <div className="text-lg font-bold">{t.value}</div>
            <div className="text-[10px] uppercase tracking-wide text-gray-500">
              {t.label}{t.term && <InfoTip term={t.term} />}
            </div>
          </div>
        ))}
      </div>
      {signals.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-edge">
                <th className="py-1.5 pr-3">Signal</th>
                <th className="py-1.5 pr-3 text-right">Calls</th>
                <th className="py-1.5 pr-3 text-right">Closed</th>
                <th className="py-1.5 pr-3 text-right">Target hit</th>
                <th className="py-1.5 pr-3 text-right">Win rate</th>
                <th className="py-1.5 pr-3 text-right">Avg return</th>
                <th className="py-1.5 text-right">Avg R</th>
              </tr>
            </thead>
            <tbody>
              {signals.map(([sig, b]) => (
                <tr key={sig} className="border-b border-edge/50">
                  <td className="py-1.5 pr-3 text-xs text-gray-300">{FLAG_LABELS[sig] || sig}</td>
                  <td className="py-1.5 pr-3 text-right">{b.calls}</td>
                  <td className="py-1.5 pr-3 text-right">{b.closed}</td>
                  <td className="py-1.5 pr-3 text-right">{b.target_hit}</td>
                  <td className="py-1.5 pr-3 text-right">{fmtPct(b.win_rate, 0)}</td>
                  <td className={`py-1.5 pr-3 text-right ${retColor(b.avg_return_pct)}`}>{fmtPct(b.avg_return_pct)}</td>
                  <td className={`py-1.5 text-right ${retColor(b.avg_r)}`}>{fmtNum(b.avg_r, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-gray-500 mt-2">
            This table is the feedback loop: signals with a poor record get down-weighted (or
            their thresholds tightened) in config — evidence, not intuition.
          </p>
        </div>
      )}
    </div>
  );
}

function ManualCallForm({ onDone, onError }) {
  const [form, setForm] = useState({
    symbol: "", direction: "long", entry_price: "", stop_price: "",
    target_price: "", horizon_days: 30, thesis: "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        symbol: form.symbol.trim().toUpperCase(),
        direction: form.direction,
        horizon_days: Number(form.horizon_days) || 30,
        thesis: form.thesis,
        source: "manual",
      };
      for (const k of ["entry_price", "stop_price", "target_price"]) {
        if (form[k] !== "") payload[k] = Number(form[k]);
      }
      await api.createCall(payload);
      onDone();
    } catch (err) {
      onError(`Log call failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const input = "bg-ink border border-edge rounded px-2 py-1.5 text-sm w-full";
  return (
    <form onSubmit={submit} className="mt-3 border-t border-edge pt-3 grid sm:grid-cols-6 gap-2 items-end">
      <label className="text-xs text-gray-400">
        Symbol
        <input className={input} value={form.symbol} onChange={set("symbol")} placeholder="CRSP" required />
      </label>
      <label className="text-xs text-gray-400">
        Direction
        <select className={input} value={form.direction} onChange={set("direction")}>
          <option value="long">long</option>
          <option value="short">short</option>
        </select>
      </label>
      <label className="text-xs text-gray-400">
        Entry (blank = last)
        <input className={input} value={form.entry_price} onChange={set("entry_price")} type="number" step="any" />
      </label>
      <label className="text-xs text-gray-400">
        Stop (blank = auto)
        <input className={input} value={form.stop_price} onChange={set("stop_price")} type="number" step="any" />
      </label>
      <label className="text-xs text-gray-400">
        Target (blank = auto)
        <input className={input} value={form.target_price} onChange={set("target_price")} type="number" step="any" />
      </label>
      <label className="text-xs text-gray-400">
        Horizon (days)
        <input className={input} value={form.horizon_days} onChange={set("horizon_days")} type="number" min="1" max="365" />
      </label>
      <label className="text-xs text-gray-400 sm:col-span-5">
        Thesis
        <input className={input} value={form.thesis} onChange={set("thesis")} placeholder="Why this trade?" />
      </label>
      <button
        type="submit"
        disabled={saving}
        className="text-xs px-3 py-2 rounded bg-sky-700 hover:bg-sky-600 text-white disabled:opacity-50"
      >
        {saving ? "Logging…" : "Log call"}
      </button>
    </form>
  );
}
