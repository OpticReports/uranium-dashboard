import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

interface BookStatus {
  equity: number; trades: number; win_rate: number | null;
  profit_factor: number | null; total_return_pct: number; max_dd_pct: number;
  expectancy_pct: number | null; exit_mix: Record<string, number>;
  state: string; unrealized: number | null;
  position: { side: string; entry_price: number; stop_price: number; qty: number } | null;
  halted: boolean;
}
interface Status {
  degraded: boolean; data_halt: boolean; is_research_config: boolean;
  price: number | null; last_processed_bar: number;
  books: Record<string, BookStatus>;
}
interface Conditions {
  ready: boolean; forming?: boolean; close?: number; regime?: string;
  rsi?: number | null; dist_sma50_atr?: number | null; vol_ratio?: number | null;
  long?: Record<string, boolean>; short?: Record<string, boolean>;
}
interface TradeRow2 {
  id: number; book: string; side: string; entry_iso: string; exit_iso: string;
  entry_price: number; exit_price: number; exit_reason: string;
  bars_held: number; pnl_usd: number; pnl_pct: number;
}
interface EqPoint { ts: number; equity: number }

const BOOK_COLORS: Record<string, string> = { S1: "#38bdf8", S2: "#f97316", S3: "#94a3b8", S4: "#c084fc", S5: "#34d399" };
const BOOK_LABEL: Record<string, string> = {
  S1: "S1 · vol-target 5.5%", S2: "S2 · 1.95x aggressive", S3: "S3 · 1x control",
  S4: "S4 · Donchian trend", S5: "S5 · blend S1+S4",
};

export default function App() {
  const [st, setSt] = useState<Status | null>(null);
  const [cond, setCond] = useState<Conditions | null>(null);
  const [trades, setTrades] = useState<TradeRow2[]>([]);
  const [eq, setEq] = useState<Record<string, EqPoint[]>>({});
  const [events, setEvents] = useState<Array<{ ts: string; level: string; event: string; detail: string }>>([]);
  const [err, setErr] = useState<string | null>(null);
  const [bookFilter, setBookFilter] = useState("S1");

  const load = useCallback(async () => {
    try {
      const [s, c, ev] = await Promise.all([
        get<Status>("/status"), get<Conditions>("/conditions"),
        get<typeof events>("/events?limit=30"),
      ]);
      setSt(s); setCond(c); setEvents(ev); setErr(null);
      const eqs: Record<string, EqPoint[]> = {};
      for (const b of Object.keys(s.books)) {
        eqs[b] = await get<EqPoint[]>(`/books/${b}/equity?limit=2000`);
      }
      setEq(eqs);
    } catch (e) { setErr(String(e)); }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    get<TradeRow2[]>(`/books/${bookFilter}/trades?limit=60`).then(setTrades).catch(() => {});
  }, [bookFilter, st]);

  const merged: Array<Record<string, number>> = (() => {
    const byTs: Record<number, Record<string, number>> = {};
    for (const [b, pts] of Object.entries(eq)) {
      for (const p of pts) {
        (byTs[p.ts] ??= { ts: p.ts })[b] = p.equity;
      }
    }
    return Object.values(byTs).sort((a, b) => a.ts - b.ts);
  })();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <div className="mx-auto max-w-7xl px-4 py-6 flex flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-slate-100">₿ BTC Pullback Paper Engine</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Three validated books · replay-verified vs research · paper only
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Badge ok={!st?.degraded} okText="DATA LIVE" badText="DEGRADED" />
            <Badge ok={!st?.data_halt} okText="PRICE SANE" badText="PRICE HALT" />
            {st?.price != null && (
              <span className="font-mono text-sky-300 text-sm">
                ${st.price.toLocaleString()}
              </span>
            )}
          </div>
        </header>

        {err && <div className="rounded border border-red-500/50 bg-red-500/10 px-3 py-2 text-xs text-red-300">{err}</div>}

        {/* Conditions strip */}
        <Panel title="Setup proximity — conditions met per side">
          {cond?.ready ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {(["long", "short"] as const).map((side) => {
                const checks = cond[side] ?? {};
                const n = Object.values(checks).filter(Boolean).length;
                const tot = Object.keys(checks).length || 6;
                return (
                  <div key={side} className="rounded border border-panelborder bg-slate-900/40 p-3">
                    <div className="flex items-baseline justify-between">
                      <span className={`text-sm font-bold ${side === "long" ? "text-emerald-400" : "text-red-400"}`}>
                        {side.toUpperCase()} {n}/{tot}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        regime {cond.regime} · RSI {cond.rsi?.toFixed(1)} ·
                        dist {cond.dist_sma50_atr?.toFixed(2)} ATR · vol {cond.vol_ratio?.toFixed(2)}x
                        {cond.forming ? " · (bar forming)" : ""}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {Object.entries(checks).map(([k, v]) => (
                        <span key={k}
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-mono ${
                            v ? "border-emerald-500/60 text-emerald-300 bg-emerald-500/10"
                              : "border-slate-700 text-slate-500"}`}>
                          {k}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : <p className="text-xs text-slate-500">Warming up…</p>}
        </Panel>

        {/* Books table */}
        <Panel title="Books">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-panelborder">
                  {["book", "state", "equity", "unreal P&L", "return", "max DD", "trades",
                    "win rate", "PF", "position"].map((h) => (
                    <th key={h} className="py-1.5 pr-4 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {st && Object.entries(st.books).map(([name, b]) => (
                  <tr key={name} className="border-b border-panelborder/50">
                    <td className="py-2 pr-4 font-semibold" style={{ color: BOOK_COLORS[name] }}>
                      {BOOK_LABEL[name] ?? name}
                    </td>
                    <td className="pr-4">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        b.state === "HALTED" ? "bg-red-500/20 text-red-300"
                        : b.state === "FLAT" || b.state === "BLEND" ? "bg-slate-700/50 text-slate-300"
                        : "bg-sky-500/20 text-sky-300"}`}>{b.state}</span>
                    </td>
                    <td className="pr-4 font-mono">${b.equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                    <td className={`pr-4 font-mono ${((b.unrealized ?? 0) >= 0) ? "text-emerald-400" : "text-red-400"}`}>
                      {b.unrealized != null ? `${b.unrealized >= 0 ? "+" : ""}$${Math.round(b.unrealized).toLocaleString()}` : "—"}
                    </td>
                    <td className={`pr-4 font-mono ${b.total_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {b.total_return_pct >= 0 ? "+" : ""}{b.total_return_pct}%
                    </td>
                    <td className="pr-4 font-mono text-slate-400">{b.max_dd_pct}%</td>
                    <td className="pr-4 font-mono">{b.trades}</td>
                    <td className="pr-4 font-mono">{b.win_rate ?? "—"}%</td>
                    <td className="pr-4 font-mono">{b.profit_factor ?? "—"}</td>
                    <td className="pr-4 font-mono text-[10px] text-slate-400">
                      {b.position
                        ? `${b.position.side} @ ${b.position.entry_price.toLocaleString()} stop ${b.position.stop_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Equity curves */}
        <Panel title="Equity curves (paper, $100k start each)">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={merged} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis dataKey="ts" type="number" scale="time"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={(t: number) => new Date(t * 1000).toISOString().slice(5, 10)}
                  stroke="#475569" tick={{ fontSize: 10 }} />
                <YAxis stroke="#475569" tick={{ fontSize: 10 }} width={56}
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", borderRadius: 6, fontSize: 11 }}
                  labelFormatter={(t) => new Date(Number(t) * 1000).toISOString().slice(0, 16)}
                  formatter={(v: number, name: string) => [`$${Math.round(v).toLocaleString()}`, name]} />
                {Object.keys(BOOK_COLORS).map((b) => (
                  <Line key={b} dataKey={b} stroke={BOOK_COLORS[b]} dot={false}
                    strokeWidth={b === "S3" ? 1.2 : 1.8} connectNulls isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <ComparePanel />

        {/* Trade log */}
        <Panel title={
          <span>Trade log
            <span className="ml-3 inline-flex gap-1">
              {Object.keys(BOOK_COLORS).map((b) => (
                <button key={b} onClick={() => setBookFilter(b)}
                  className={`rounded-full border px-2 py-0.5 text-[10px] ${
                    bookFilter === b ? "border-sky-500 text-sky-300 bg-sky-500/10"
                    : "border-panelborder text-slate-500"}`}>{b}</button>
              ))}
            </span>
          </span>}>
          <div className="overflow-x-auto max-h-80 scroll-thin overflow-y-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-slate-500 border-b border-panelborder sticky top-0 bg-slate-950">
                  {["side", "entry", "exit", "entry px", "exit px", "reason", "bars", "P&L"].map((h) => (
                    <th key={h} className="py-1 pr-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-panelborder/40 font-mono">
                    <td className={`py-1 pr-3 font-bold ${t.side === "L" ? "text-emerald-400" : "text-red-400"}`}>{t.side}</td>
                    <td className="pr-3 text-slate-400">{t.entry_iso?.slice(0, 16)}</td>
                    <td className="pr-3 text-slate-400">{t.exit_iso?.slice(0, 16)}</td>
                    <td className="pr-3">{t.entry_price?.toLocaleString()}</td>
                    <td className="pr-3">{t.exit_price?.toLocaleString()}</td>
                    <td className="pr-3">{t.exit_reason}</td>
                    <td className="pr-3">{t.bars_held}</td>
                    <td className={`pr-3 ${t.pnl_usd >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {t.pnl_usd >= 0 ? "+" : ""}{Math.round(t.pnl_usd).toLocaleString()} ({t.pnl_pct?.toFixed(2)}%)
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Events */}
        <Panel title="Engine events">
          <ul className="text-[11px] font-mono space-y-1 max-h-40 overflow-y-auto scroll-thin">
            {events.map((e, i) => (
              <li key={i} className="text-slate-400">
                <span className="text-slate-600">{e.ts?.slice(0, 16)}</span>{" "}
                <span className={e.level === "RED" ? "text-red-400" : e.level === "WARN" ? "text-amber-400" : "text-slate-300"}>
                  {e.event}
                </span>{" "}{e.detail}
              </li>
            ))}
          </ul>
        </Panel>

        <footer className="border-t border-panelborder pt-3 text-center text-[10px] text-slate-600">
          Paper execution only. Research basis: 2024-07→2026-07 Bitstamp backtest; forward
          performance is expected BELOW backtest — measuring that gap is this engine's purpose.
        </footer>
      </div>
    </div>
  );
}

function ComparePanel() {
  const [win, setWin] = useState("2y");
  const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const [data, setData] = useState<any>(null);
  const load = useCallback((q: string) => {
    get<any>(`/replay/compare?${q}`).then(setData).catch(() => {});
  }, []);
  useEffect(() => { load(`window=${win}`); }, [win, load]);
  const rows = data ? Object.entries(data.books) as Array<[string, any]> : [];
  return (
    <Panel title="Backtest comparison — all books, same window">
      <div className="mb-3 flex flex-wrap items-center gap-1.5 text-[10px]">
        {["2y", "1y", "6m", "3m", "1m"].map((w) => (
          <button key={w} onClick={() => setWin(w)}
            className={`rounded-full border px-2.5 py-0.5 font-semibold ${
              win === w ? "border-sky-500 text-sky-300 bg-sky-500/10"
              : "border-panelborder text-slate-500"}`}>{w}</button>
        ))}
        <span className="ml-2 text-slate-500">custom:</span>
        <input value={from} onChange={(e) => setFrom(e.target.value)} placeholder="YYYY-MM-DD"
          className="w-24 rounded border border-panelborder bg-slate-900 px-1.5 py-0.5 font-mono" />
        <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="YYYY-MM-DD"
          className="w-24 rounded border border-panelborder bg-slate-900 px-1.5 py-0.5 font-mono" />
        <button onClick={() => from && load(`start=${from}${to ? `&end=${to}` : ""}`)}
          className="rounded border border-sky-500/60 bg-sky-500/10 px-2 py-0.5 text-sky-300">run</button>
        {data && <span className="ml-auto text-slate-500">
          {data.window.from.slice(0, 10)} → {data.window.to.slice(0, 10)} · B&H {data.buy_hold_pct >= 0 ? "+" : ""}{data.buy_hold_pct}%</span>}
      </div>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-slate-500 border-b border-panelborder">
          {["book", "return", "max DD", "trades", "win rate"].map((h) => (
            <th key={h} className="py-1 pr-4 font-medium">{h}</th>))}
        </tr></thead>
        <tbody>{rows.map(([n, b]) => (
          <tr key={n} className="border-b border-panelborder/40">
            <td className="py-1.5 pr-4 font-semibold" style={{ color: BOOK_COLORS[n] }}>{BOOK_LABEL[n] ?? n}</td>
            <td className={`pr-4 font-mono ${b.total_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {b.total_return_pct >= 0 ? "+" : ""}{b.total_return_pct}%</td>
            <td className="pr-4 font-mono text-slate-400">{b.max_dd_pct}%</td>
            <td className="pr-4 font-mono">{b.trades}</td>
            <td className="pr-4 font-mono">{b.win_rate ?? "—"}</td>
          </tr>))}
        </tbody>
      </table>
    </Panel>
  );
}

function Panel({ title, children }: { title: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-panelborder bg-panel/60 p-4">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-400">{title}</h2>
      {children}
    </section>
  );
}

function Badge({ ok, okText, badText }: { ok: boolean | undefined; okText: string; badText: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
      ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>
      {ok ? okText : badText}
    </span>
  );
}
