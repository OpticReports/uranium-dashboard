import React, { useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtNum, fmtPct, fmtMoney } from "../lib/format";
import InfoTip from "../components/InfoTip";

// The 10-year replay of the calls engine, on the page where the live record
// lives — so "how deep was the hole" sits next to "what has it done lately".
//
// Two measurement bases are shown and NEVER mixed in one table:
//   dollars, daily mark-to-market  — full period + pre-registered sub-periods,
//                                    and the trailing windows where the daily
//                                    bar cache reproduced the documented book
//   R-units, realization basis     — trailing 2y / 5y / 10y from the complete
//                                    call record (no daily marks, so no Sharpe)
// The payload says which is which; this component just refuses to blur them.

const TOOLTIP = { background: "#121826", border: "1px solid #1f2937", fontSize: 12 };
const COLORS = { V0: "#38bdf8", V5: "#a78bfa", XBI: "#f59e0b", SPY: "#9ca3af" };

const ddColor = (v) => (v >= 0.5 ? "text-rose-400" : v >= 0.3 ? "text-amber-400" : "text-gray-200");
const signColor = (v) => (v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-gray-200");

const tabLabel = (mode, key, bt) => {
  if (mode === "d") return key === "full" ? "Full period" : key;
  if (key === "10y") return "10y (= full replay)";
  return `Trailing ${key} to ${bt.period.end}`;
};

export default function BacktestPanel({ bt }) {
  const daily = bt.windows_daily || {};
  const trailingR = bt.trailing_r?.windows || {};
  const trailingD = bt.trailing_daily;
  const tabs = [
    ...Object.keys(daily).map((k) => ({ id: `d:${k}`, label: tabLabel("d", k, bt) })),
    ...Object.keys(trailingR).map((k) => ({ id: `t:${k}`, label: tabLabel("t", k, bt) })),
  ];
  const [tab, setTab] = useState(tabs[0]?.id);

  const [mode, key] = (tab || "d:full").split(":");
  const win = mode === "d" ? daily[key] : null;
  const winR = mode === "t" ? trailingR[key] : null;
  const winD = mode === "t" ? trailingD?.windows?.[key] : null;

  const v0 = daily.full?.books?.V0;
  const xbi = daily.full?.books?.XBI;
  const cb = bt.combined_book || {};
  const fires = (cb.n_calls || 0) + (cb.skipped_at_cap || 0);

  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h3 className="font-semibold">
            📊 10-year replay — what the mechanical engine would have done
            <InfoTip term="backtest_replay" />
          </h3>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl">
            Every replayable signal fired over {bt.period.start} → {bt.period.end} on
            today's {bt.period.n_names}-name universe, graded with the production exit
            rules. A {fmtMoney(bt.protocol.start_equity)} book holding at most{" "}
            {bt.protocol.cap_open_calls} calls took <b>{cb.n_calls?.toLocaleString()}</b> of
            those {fires.toLocaleString()} fires ({cb.skipped_at_cap?.toLocaleString()} skipped
            at the cap). This is the engine's <b>mechanical shadow</b> — the live gates and
            triggers have no history and were not replayed — and it trades <b>survivors
            only</b>. The live paper book above is the honest measure of the full system.
          </p>
        </div>
        {v0 && (
          <div className="text-right">
            <div className={`text-3xl font-bold ${ddColor(v0.max_dd)}`}>{fmtPct(v0.max_dd, 1)}</div>
            <div className="text-[10px] uppercase tracking-wide text-gray-500">
              max drawdown, full period<InfoTip term="max_drawdown" />
            </div>
            <div className="text-xs text-gray-400 mt-1">
              Sharpe {fmtNum(v0.sharpe, 2)} · CAGR {fmtPct(v0.cagr, 1)}
            </div>
            {xbi && (
              <div className="text-[11px] text-gray-500">
                XBI buy &amp; hold: max DD {fmtPct(xbi.max_dd, 1)} · Sharpe {fmtNum(xbi.sharpe, 2)} · CAGR {fmtPct(xbi.cagr, 1)}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-1 mt-3">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-xs px-2.5 py-1 rounded border ${
              tab === t.id ? "border-sky-700 text-sky-300 bg-ink" : "border-edge text-gray-400 hover:bg-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {win && <DollarTable win={win} books={bt.books} />}
      {winR && (
        <>
          {winD ? (
            <>
              <DollarTable
                win={winD}
                books={bt.books}
                note={winD.note ? `dollars, daily mark-to-market — ${winD.note}` : "dollars, daily mark-to-market — full daily curve"}
              />
              {trailingD?.status === "ok" && trailingD.v0_gate && (
                <div className="text-[10px] text-gray-600 mt-1">
                  Recomputed from a {trailingD.basis?.lane || "refetched"} price cache that reproduces the
                  documented book (gate: max DD {fmtPct(trailingD.v0_gate.max_dd, 1)}, Sharpe{" "}
                  {fmtNum(trailingD.v0_gate.sharpe, 3)} vs documented {fmtPct(trailingD.v0_gate.expected?.max_dd, 1)} /{" "}
                  {fmtNum(trailingD.v0_gate.expected?.sharpe, 2)}).
                  {trailingD.basis?.normalized && Object.keys(trailingD.basis.normalized).length > 0 && (
                    <> Basis normalized by a constant factor for:{" "}
                      {Object.entries(trailingD.basis.normalized).map(([s, f]) => `${s} (×${(1 / f.factor).toFixed(2)})`).join(", ")}
                      {" "}— returns unchanged, units matched to the frozen entries.</>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="mt-3 text-xs text-amber-300/90 bg-amber-900/10 border border-amber-800/40 rounded-lg px-3 py-2">
              Dollar stats (Sharpe, max DD in %) for this window are <b>not available</b> —{" "}
              {trailingD?.reason || "this build did not have the daily price cache the replay was built from"}.
              The same window is shown below in R-units from the complete call record.
            </div>
          )}
          <RTable w={winR} />
        </>
      )}

      <div className="grid lg:grid-cols-2 gap-4 mt-4">
        <EquityChart curves={bt.curves} books={bt.books} />
        <DrawdownChart curves={bt.curves} books={bt.books} />
      </div>

      <SizingSensitivity s={bt.sizing_sensitivity} />

      <div className="mt-4 pt-3 border-t border-edge/60">
        <div className="text-xs text-gray-400 mb-1">Read honestly</div>
        <ul className="text-[11px] text-gray-500 space-y-1 list-disc pl-4">
          {bt.caveats.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
        <div className="text-[10px] text-gray-600 mt-2">
          How these are known: every dollar figure in the window tables is copied from the full
          daily curves of the variants run, whose machinery gate re-asserts the documented book
          within ±1% on every run; a test freezes the same numbers here. The sizing table is the
          replay report's own addendum. Source: {bt.sources.reports.join(", ")} ·
          results generated {bt.sources.variants_results.generated?.slice(0, 10)} ·
          summary built {bt.generated?.slice(0, 10)}
        </div>
      </div>
    </div>
  );
}

function DollarTable({ win, books, note }) {
  const order = ["V0", "V5", "XBI", "SPY"].filter((k) => win.books?.[k]);
  return (
    <div className="mt-3 overflow-x-auto">
      <div className="text-xs text-gray-400 mb-1">
        {win.start} → {win.end} ({win.years}y) · {note || "dollars, daily mark-to-market"}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-400 border-b border-edge">
            <th className="py-1.5 pr-3">Book</th>
            <th className="py-1.5 pr-3 text-right">CAGR</th>
            <th className="py-1.5 pr-3 text-right">Max DD<InfoTip term="max_drawdown" /></th>
            <th className="py-1.5 pr-3 text-right">Sharpe<InfoTip term="sharpe" /></th>
            <th className="py-1.5 pr-3 text-right">Sortino<InfoTip term="sortino" /></th>
            <th className="py-1.5 pr-3 text-right">Calmar<InfoTip term="calmar" /></th>
            <th className="py-1.5 text-right whitespace-nowrap">Book value at end
              <span className="block text-[9px] normal-case text-gray-600">running, not re-based</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {order.map((k) => {
            const s = win.books[k];
            const b = books[k] || {};
            return (
              <tr key={k} className={`border-b border-edge/50 ${b.kind === "benchmark" ? "text-gray-400" : ""}`}>
                <td className="py-1.5 pr-3 whitespace-nowrap">
                  <span className="inline-block w-2 h-2 rounded-sm mr-2" style={{ background: COLORS[k] }} />
                  <span className={b.kind === "engine" ? "font-semibold text-gray-200" : ""}>{b.label || k}</span>
                  {b.sub && <span className="hidden sm:inline text-xs text-gray-500 ml-2">{b.sub}</span>}
                </td>
                <td className={`py-1.5 pr-3 text-right ${signColor(s.cagr)}`}>{fmtPct(s.cagr, 1)}</td>
                <td className={`py-1.5 pr-3 text-right ${ddColor(s.max_dd)}`}>{fmtPct(s.max_dd, 1)}</td>
                <td className="py-1.5 pr-3 text-right">{fmtNum(s.sharpe, 2)}</td>
                <td className="py-1.5 pr-3 text-right">{fmtNum(s.sortino, 2)}</td>
                <td className="py-1.5 pr-3 text-right">{fmtNum(s.calmar, 2)}</td>
                <td className="py-1.5 text-right">{fmtMoney(Math.round(s.end_value))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RTable({ w }) {
  const tiles = [
    { label: "Calls exited", value: w.n_calls?.toLocaleString() },
    { label: "Total R", value: fmtNum(w.total_r, 1), c: signColor(w.total_r) },
    { label: "Max DD (R)", value: fmtNum(w.max_dd_r, 1), c: w.max_dd_r > 0 ? "text-rose-300" : "" },
    { label: "Hit rate", value: fmtPct(w.hit_rate, 0) },
    { label: "Avg R / call", value: fmtNum(w.avg_r, 3), c: signColor(w.avg_r) },
  ];
  return (
    <div className="mt-3">
      <div className="text-xs text-gray-400 mb-1">
        {w.start} → {w.end} ({w.years}y) · <b>R-units, realization basis</b> — a call counts in the
        window it exited in; 1R risked per call, ≤10 open; slippage inside R
        <InfoTip term="r_window" />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {tiles.map((t) => (
          <div key={t.label} className="bg-ink border border-edge rounded-lg p-2 text-center">
            <div className={`text-lg font-bold ${t.c || "text-gray-200"}`}>{t.value}</div>
            <div className="text-[10px] uppercase tracking-wide text-gray-500">{t.label}</div>
          </div>
        ))}
      </div>
      {w.curve?.length > 2 && (
        <>
          <div className="text-[10px] text-gray-600 mt-2">
            Cumulative R by exit date — display resolution ({w.curve.length} of {w.n_calls} exits drawn);
            the Max DD (R) tile is from every exit
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={w.curve.map(([date, cum_r]) => ({ date, cum_r }))} margin={{ left: -20, right: 10, top: 8 }}>
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={40} />
              <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
              <Tooltip contentStyle={TOOLTIP} formatter={(v) => `${fmtNum(v, 1)}R`} />
              <Line type="stepAfter" dataKey="cum_r" name="cumulative R" stroke={COLORS.V0} dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}

function EquityChart({ curves, books }) {
  const rows = curves?.rows || [];
  const keys = ["V0", "XBI", "SPY"].filter((k) => rows.some((r) => r[k] !== undefined));
  if (rows.length < 3) return null;
  return (
    <div>
      <div className="text-xs text-gray-400 mb-1">
        Equity, {fmtMoney(curves.start_equity)} start (log scale)
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={rows} margin={{ left: 6, right: 10, top: 5 }}>
          <CartesianGrid stroke="#1f2937" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={50} />
          <YAxis scale="log" domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "#94a3b8" }}
            tickFormatter={(v) => `$${Math.round(v / 1000)}k`} width={44} />
          <Tooltip contentStyle={TOOLTIP} formatter={(v, name) => [fmtMoney(Math.round(v)), books[name]?.label || name]} />
          {keys.map((k) => (
            <Line key={k} type="monotone" dataKey={k} stroke={COLORS[k]} dot={false}
              strokeWidth={k === "V0" ? 2 : 1.25} strokeDasharray={books[k]?.kind === "benchmark" ? "4 3" : undefined} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Drawdown profile from the display-resolution curve. The NUMBERS in the
// tables come from the full daily curves; this picture is coarser and can
// only understate a trough, never invent one — said in the caption.
function DrawdownChart({ curves, books }) {
  const rows = curves?.rows || [];
  const data = useMemo(() => {
    const keys = ["V0", "XBI"].filter((k) => rows.some((r) => r[k] !== undefined));
    const peak = {};
    return rows.map((r) => {
      const o = { date: r.date };
      for (const k of keys) {
        if (r[k] === undefined) continue;
        peak[k] = Math.max(peak[k] ?? -Infinity, r[k]);
        o[k] = peak[k] > 0 ? r[k] / peak[k] - 1 : 0;
      }
      return o;
    });
  }, [rows]);
  if (rows.length < 3) return null;
  const keys = ["V0", "XBI"].filter((k) => k in (data[0] || {}));
  return (
    <div>
      <div className="text-xs text-gray-400 mb-1">
        Drawdown from peak <span className="text-gray-600">(display resolution — tables use the full daily curves)</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ left: -14, right: 10, top: 5 }}>
          <CartesianGrid stroke="#1f2937" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={50} />
          <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} tickFormatter={(v) => `${Math.round(v * 100)}%`} domain={["auto", 0]} />
          <Tooltip contentStyle={TOOLTIP} formatter={(v, name) => [fmtPct(v, 1), books[name]?.label || name]} />
          {keys.map((k) => (
            <Area key={k} type="monotone" dataKey={k} stroke={COLORS[k]} fill={COLORS[k]}
              fillOpacity={k === "V0" ? 0.25 : 0.08} strokeWidth={k === "V0" ? 1.5 : 1} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function SizingSensitivity({ s }) {
  if (!s?.rows?.length) return null;
  return (
    <div className="mt-4 overflow-x-auto">
      <div className="text-xs text-gray-400 mb-1">
        What risk per call buys — full period<InfoTip term="sizing_sensitivity" />
      </div>
      <table className="text-xs">
        <thead>
          <tr className="text-left text-gray-500 border-b border-edge">
            <th className="py-1 pr-4">book</th>
            <th className="py-1 pr-4 text-right">CAGR</th>
            <th className="py-1 pr-4 text-right">max DD</th>
            <th className="py-1 pr-4 text-right">Sharpe</th>
            <th className="py-1 text-right">end value</th>
          </tr>
        </thead>
        <tbody>
          {s.rows.map((r) => (
            <tr key={r.label || r.risk_frac} className="border-b border-edge/40 text-gray-300">
              <td className="py-1 pr-4 whitespace-nowrap">{r.label || fmtPct(r.risk_frac, 1)}</td>
              <td className="py-1 pr-4 text-right">{fmtPct(r.cagr, 1)}</td>
              <td className={`py-1 pr-4 text-right ${ddColor(r.max_dd)}`}>{fmtPct(r.max_dd, 1)}</td>
              <td className="py-1 pr-4 text-right">{fmtNum(r.sharpe, 2)}</td>
              <td className="py-1 text-right">{fmtMoney(r.end_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[10px] text-gray-600 mt-1">
        {s.source} — a separate run from the tables above, hence the few dollars' difference on the 1% row.
      </div>
    </div>
  );
}
