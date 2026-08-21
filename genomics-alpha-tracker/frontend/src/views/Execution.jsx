import React, { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../lib/api";
import { fmtMoney, fmtNum } from "../lib/format";

// Execution: the ibkr-executor's blend3070 book (H13 30/70) made visible —
// trade log, P&L curve, open positions, budget headroom. READ-ONLY: this tab
// can never place, cancel, or kill anything (that surface is EXEC_TOKEN-gated
// on the executor itself). Data arrives via the tracker's server-side proxy
// (/api/execution/feed), so the executor's read token never reaches the
// browser. Until Casey sets the tokens the feed 404s and the "not connected"
// card below explains exactly which env vars are missing.

const SIDE_CLS = {
  BUY: "text-emerald-400",
  SELL: "text-rose-400",
};

const KIND_LABEL = {
  entry: "Entry (MOO)",
  stop_filled: "Stop filled",
  time_stop: "Time stop",
  trail: "Trail exit",
  core: "Core (SPY)",
  sweep: "Cash sweep (BIL)",
};

const pnlCls = (v) =>
  v === null || v === undefined ? "text-gray-500" : v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-gray-300";

export default function Execution() {
  const [feed, setFeed] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api
      .executionFeed()
      .then((f) => {
        setFeed(f);
        setError(null);
      })
      .catch((err) => setError(err.message || "unreachable"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  if (loading && !feed) {
    return <div className="text-gray-500 text-sm">Loading execution feed…</div>;
  }
  if (error || !feed) {
    return <NotConnected error={error} onRetry={load} />;
  }

  const book = feed.book || {};
  const curve = (feed.equity_curve || []).map(([date, value]) => ({ date, value }));
  const trades = [...(feed.trades || [])].reverse(); // newest first
  const positions = feed.positions || [];
  const util = book.budget_utilization; // fraction of BLEND_BUDGET or null
  const lastCycle = feed.last_cycle || {};

  return (
    <div className="space-y-4">
      {/* strategy identity: what this book is actually running */}
      <StrategyCard />

      {/* mode / gate / halt banner */}
      {feed.halted ? (
        <div className="bg-rose-900/30 border border-rose-800 rounded-xl px-4 py-2 text-sm">
          <span className="text-rose-300 font-bold">⛔ HALTED ({feed.halted})</span>{" "}
          <span className="text-gray-400">
            — the book is stopped; it stays halted until /resume on the executor.
          </span>
        </div>
      ) : (
        <div className="bg-panel border border-edge rounded-xl px-4 py-2 text-sm flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>
            <span className="text-gray-500">mode</span>{" "}
            <ModeBadge mode={feed.mode} />
          </span>
          <span>
            <span className="text-gray-500">XBI gate</span>{" "}
            {feed.gate === true ? (
              <span className="text-emerald-400 font-semibold">ON</span>
            ) : feed.gate === false ? (
              <span className="text-amber-400 font-semibold">OFF — no new entries</span>
            ) : (
              <span className="text-gray-500">unknown (no cycle yet)</span>
            )}
          </span>
          {feed.unreconciled > 0 && (
            <span className="text-xs border border-rose-800 bg-rose-900/30 text-rose-300 rounded-full px-2 py-0.5 font-semibold">
              {feed.unreconciled} unreconciled — manual review
            </span>
          )}
        </div>
      )}

      {/* book tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        <Tile label="Book value" value={book.equity_estimate != null ? fmtMoney(book.equity_estimate) : "n/a"} />
        <Tile label="Sleeve cash" value={fmtMoney(book.sleeve_cash)} />
        <Tile label="SPY core" value={`${book.core_qty ?? 0} sh`} />
        <Tile label="BIL parked" value={`${book.bil_qty ?? 0} sh`} />
        <Tile label="Open positions" value={positions.length} />
      </div>

      {/* equity curve */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="text-xs text-gray-400 mb-1">
          Book equity (daily cycle snapshots; dashed line = initial BLEND_BOOK_USD)
        </div>
        {curve.length > 1 ? (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={curve} margin={{ left: 6, right: 10, top: 5 }}>
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} domain={["auto", "auto"]}
                tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} width={46} />
              <Tooltip contentStyle={{ background: "#121826", border: "1px solid #1f2937", fontSize: 12 }}
                formatter={(v) => fmtMoney(v)} />
              {book.initial_book_usd != null && (
                <ReferenceLine y={book.initial_book_usd} stroke="#4b5563" strokeDasharray="3 3" />
              )}
              <Line type="stepAfter" dataKey="value" stroke="#38bdf8" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-gray-600 text-sm py-6 text-center">
            Not enough cycle days yet — the curve appears after two daily snapshots.
          </div>
        )}
      </div>

      {/* budget utilization */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="text-xs text-gray-400 mb-2">
          Budget utilization (gross notional vs BLEND_BUDGET; alert crosses at the 85% mark)
        </div>
        {util != null ? (
          <div className="relative h-5 bg-ink border border-edge rounded overflow-hidden">
            <div
              className={`h-full ${util >= 0.85 ? "bg-rose-600/70" : util >= 0.7 ? "bg-amber-500/60" : "bg-sky-600/60"}`}
              style={{ width: `${Math.min(util * 100, 100)}%` }}
            />
            <div className="absolute inset-y-0 border-l-2 border-dashed border-gray-300/60" style={{ left: "85%" }} />
            <div className="absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-gray-200">
              {(util * 100).toFixed(1)}%
            </div>
          </div>
        ) : (
          <div className="text-gray-600 text-sm">
            No BLEND_BUDGET cap set on the executor (utilization unavailable).
          </div>
        )}
      </div>

      {/* open positions */}
      <div className="overflow-x-auto bg-panel border border-edge rounded-xl">
        <div className="px-3 pt-3 text-xs text-gray-400">Open positions (sleeve)</div>
        <table className="w-full text-sm">
          <thead className="text-gray-400 border-b border-edge">
            <tr>
              <Th>Symbol</Th>
              <Th>Qty</Th>
              <Th>Entry</Th>
              <Th>Trail stop</Th>
              <Th>Days held</Th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={`${p.symbol}-${p.entry_date}`} className="border-b border-edge/50">
                <td className="px-3 py-2 font-semibold">{p.symbol}</td>
                <td className="px-3 py-2">{p.qty}</td>
                <td className="px-3 py-2">
                  ${fmtNum(p.entry, 2)} <span className="text-gray-500 text-xs">({p.entry_date})</span>
                </td>
                <td className="px-3 py-2">${fmtNum(p.trail_level, 2)}</td>
                <td className="px-3 py-2">{p.days_held != null ? `${p.days_held} / 90` : "—"}</td>
              </tr>
            ))}
            {!positions.length && (
              <tr>
                <td colSpan={5} className="px-3 py-5 text-center text-gray-500">
                  No open sleeve positions — entries appear when the tracker fires with the gate on.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* trade log */}
      <div className="overflow-x-auto bg-panel border border-edge rounded-xl">
        <div className="px-3 pt-3 text-xs text-gray-400">Trade log (last {trades.length}, newest first)</div>
        <table className="w-full text-sm">
          <thead className="text-gray-400 border-b border-edge">
            <tr>
              <Th>Date</Th>
              <Th>Symbol</Th>
              <Th>Side</Th>
              <Th>Qty</Th>
              <Th>Fill</Th>
              <Th>Kind</Th>
              <Th>R</Th>
              <Th>P&L</Th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-edge/50">
                <td className="px-3 py-1.5 text-gray-400 text-xs">{t.date}</td>
                <td className="px-3 py-1.5 font-semibold">{t.symbol}</td>
                <td className={`px-3 py-1.5 font-semibold ${SIDE_CLS[t.side] || ""}`}>{t.side}</td>
                <td className="px-3 py-1.5">{t.qty}</td>
                <td className="px-3 py-1.5">${fmtNum(t.fill_price, 2)}</td>
                <td className="px-3 py-1.5 text-xs text-gray-400">{KIND_LABEL[t.kind] || t.kind}</td>
                <td className={`px-3 py-1.5 ${pnlCls(t.r_multiple)}`}>
                  {t.r_multiple != null ? `${t.r_multiple > 0 ? "+" : ""}${fmtNum(t.r_multiple, 2)}R` : "—"}
                </td>
                <td className={`px-3 py-1.5 ${pnlCls(t.pnl)}`}>
                  {t.pnl != null ? `${t.pnl > 0 ? "+" : ""}${fmtMoney(t.pnl)}` : "—"}
                </td>
              </tr>
            ))}
            {!trades.length && (
              <tr>
                <td colSpan={8} className="px-3 py-5 text-center text-gray-500">
                  No trades booked yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* last-cycle footer */}
      <div className="text-xs text-gray-500 flex items-center gap-2">
        <span>
          Last cycle:{" "}
          {lastCycle.date ? (
            <>
              {lastCycle.date} ·{" "}
              {lastCycle.ok ? (
                <span className="text-emerald-400">ok</span>
              ) : (
                <span className="text-rose-400">FAILED{lastCycle.error ? ` — ${lastCycle.error}` : ""}</span>
              )}
            </>
          ) : (
            "no cycle recorded yet (executor may have just booted)"
          )}
        </span>
        <button onClick={load} className="border border-edge rounded px-2 py-0.5 hover:text-gray-200">
          Refresh
        </button>
      </div>
    </div>
  );
}

function StrategyCard() {
  return (
    <div className="bg-panel border border-edge rounded-xl px-4 py-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-gray-100 font-bold">Blend 30/70</span>
        <span className="text-xs text-gray-500 uppercase tracking-wide">
          R2-A genomics sleeve / SPY core · H13
        </span>
      </div>
      <div className="text-sm text-gray-400 mt-1">
        70% SPY held as the core · 30% sleeve trading the tracker's live
        signal fires, entries allowed only while XBI is above its 200-day
        average (prior close) · exits by 3×ATR trailing stop or 90-day time
        stop · max 10 open, 1% of book risked per position · idle cash
        parked in BIL · rebalanced on a 5% band.
      </div>
      <details className="mt-1">
        <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300">
          evidence & caveats
        </summary>
        <div className="text-xs text-gray-500 mt-1 space-y-1">
          <div>
            Backtest 2016–2026: ~15.9% CAGR, −29.3% max drawdown, 1.02
            Sharpe vs SPY's 15.4% / −33.7% / 0.89 (daily MTM, slippage
            modeled). These are IN-SAMPLE numbers, not a forecast — the
            live shadow-grader (H11) is accruing the out-of-sample record
            that decides real sizing.
          </div>
          <div>
            Full construction &amp; review trail: BACKTEST_VARIANTS_R2/R3 +
            HYPOTHESES.md (H11/H13) in the repo.
          </div>
        </div>
      </details>
    </div>
  );
}

function NotConnected({ error, onRetry }) {
  return (
    <div className="bg-panel border border-edge rounded-xl p-6 max-w-2xl">
      <div className="text-gray-200 font-semibold mb-1">⚡ Execution feed not connected</div>
      <p className="text-sm text-gray-400 mb-3">
        The blend3070 book lives on the ibkr-executor; this tab reads its read-only feed
        through a server-side proxy. To connect it, set:
      </p>
      <ul className="text-sm text-gray-300 space-y-1 mb-3 list-disc list-inside">
        <li>
          <code className="text-sky-300">READ_TOKEN</code> on <span className="text-gray-400">ibkr-executor</span>{" "}
          (any long random string; empty keeps its feed disabled) — plus{" "}
          <code className="text-sky-300">BLEND_ENABLED=true</code>
        </li>
        <li>
          <code className="text-sky-300">BLEND_UPSTREAM</code> on <span className="text-gray-400">genomics-alpha-tracker</span>{" "}
          (the executor's base URL)
        </li>
        <li>
          <code className="text-sky-300">BLEND_READ_TOKEN</code> on <span className="text-gray-400">genomics-alpha-tracker</span>{" "}
          (the same READ_TOKEN value — injected server-side, never sent to the browser)
        </li>
      </ul>
      <p className="text-xs text-gray-500 mb-3">
        {error ? `Feed says: ${error}` : "Feed unreachable."} This tab is read-only either
        way — kill/resume stay on the executor's EXEC_TOKEN surface.
      </p>
      <button onClick={onRetry} className="text-sm border border-edge rounded px-3 py-1 hover:text-gray-200">
        Retry
      </button>
    </div>
  );
}

function ModeBadge({ mode }) {
  const m = mode || "OFFLINE";
  const cls = m === "LIVE"
    ? "bg-rose-600/20 text-rose-300 border-rose-700"
    : m === "PAPER"
      ? "bg-emerald-600/20 text-emerald-300 border-emerald-700"
      : "bg-gray-600/20 text-gray-300 border-gray-600";
  return <span className={`text-xs border rounded-full px-2 py-0.5 font-semibold ${cls}`}>{m}</span>;
}

function Tile({ label, value }) {
  return (
    <div className="bg-panel border border-edge rounded-lg p-2 text-center">
      <div className="text-sm font-bold text-gray-200">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
    </div>
  );
}

function Th({ children }) {
  return <th className="px-3 py-2 text-left font-medium">{children}</th>;
}
