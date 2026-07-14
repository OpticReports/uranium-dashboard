import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmtNum, fmtPct, fmtScore10, scoreColor, FLAG_LABELS } from "../lib/format";

// The landing view: what is this, what's actionable RIGHT NOW, and why —
// readable by someone who has never seen the dashboard before.

const pctColor = (v) =>
  v === null || v === undefined ? "text-gray-500" : v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-gray-300";

const TIER_BADGE = {
  A: "bg-emerald-600/20 text-emerald-300 border-emerald-700",
  B: "bg-amber-600/20 text-amber-300 border-amber-700",
  C: "bg-rose-600/20 text-rose-300 border-rose-700",
};

export default function Today({ onPick }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const load = () => api.today().then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  if (err) return <div className="text-rose-400">⚠ {err}</div>;
  if (!data) return <div className="text-gray-400">Loading today's picture…</div>;

  const { regime, actionable, open_calls, catalysts_7d, digest } = data;

  return (
    <div className="space-y-4">
      {/* Orientation: what is this + data freshness */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <p className="text-sm text-gray-300 max-w-3xl">{data.purpose}</p>
          <div className="text-right text-xs text-gray-500 shrink-0">
            <div>data through <b className="text-gray-300">{data.data_asof || "—"}</b> (daily bars)</div>
            <div className="max-w-[16rem]">{data.data_note}</div>
          </div>
        </div>
        <RegimeStrip regime={regime} />
      </div>

      {/* Actionable now */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <h3 className="font-semibold mb-1">⚡ Actionable now</h3>
        <p className="text-xs text-gray-500 mb-3">
          Names whose signals fired in the last 48 hours, packaged for a decision: why it
          fired, that signal's real track record, the catalyst, reference levels, and how
          much size the name can absorb.
        </p>
        {actionable.length ? (
          <div className="grid lg:grid-cols-2 gap-3">
            {actionable.map((c) => <ActionCard key={c.symbol} c={c} onPick={onPick} />)}
          </div>
        ) : (
          <EmptyActionable catalysts={catalysts_7d} openCalls={open_calls} />
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Open calls */}
        <div className="bg-panel border border-edge rounded-xl p-4">
          <h3 className="font-semibold mb-2">📒 Open calls ({open_calls.length})</h3>
          {open_calls.length ? (
            <div className="space-y-1.5">
              {open_calls.map((c) => (
                <button key={c.id} onClick={() => onPick?.(c.symbol)}
                  className="w-full text-left border border-edge rounded-lg p-2 hover:bg-ink text-sm">
                  <div className="flex justify-between">
                    <span className="font-semibold text-sky-400">{c.symbol}</span>
                    <span className={pctColor(c.unrealized_pct)}>{fmtPct(c.unrealized_pct)}</span>
                  </div>
                  <div className="text-xs text-gray-400 flex justify-between mt-0.5">
                    <span>{fmtNum(c.entry, 2)} → stop {fmtNum(c.stop, 2)} · tgt {fmtNum(c.target, 2)} · exit by {c.expires_on}</span>
                  </div>
                  {c.signal_decay !== null && c.signal_decay !== undefined && c.signal_decay < -10 && (
                    <div className="text-xs text-amber-300 mt-1">
                      ⚠ thesis eroding: score {fmtScore10(c.composite_at_call)} → {fmtScore10(c.composite_now)} since the call — consider an early exit
                    </div>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-500">No open calls. See the Calls Log tab for the graded history.</div>
          )}
        </div>

        {/* Catalysts this week */}
        <div className="bg-panel border border-edge rounded-xl p-4">
          <h3 className="font-semibold mb-2">📅 Catalysts in the next 7 days</h3>
          {catalysts_7d.length ? (
            <div className="space-y-1.5">
              {catalysts_7d.map((c, i) => (
                <button key={i} onClick={() => onPick?.(c.symbol)}
                  className="w-full text-left border border-edge rounded-lg p-2 hover:bg-ink text-sm">
                  <div className="flex justify-between">
                    <span><b className="text-sky-400">{c.symbol}</b> <span className="text-gray-400 text-xs">{c.event_type}</span></span>
                    <span className="text-xs text-gray-400">{c.days_until === 0 ? "today" : `in ${c.days_until}d`}</span>
                  </div>
                  <div className="text-xs text-gray-400 truncate">{c.title}</div>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-500">Nothing on the calendar this week.</div>
          )}
        </div>
      </div>

      {/* Digest */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <h3 className="font-semibold mb-1">🌅 Digest — since the prior close</h3>
        <p className="text-xs text-gray-500 mb-3">{digest.as_of_note} · {digest.new_flags_24h} new flag(s) in 24h</p>
        <div className="grid sm:grid-cols-2 gap-4">
          <MoverList title="Biggest up" rows={digest.biggest_up} onPick={onPick} />
          <MoverList title="Biggest down" rows={digest.biggest_down} onPick={onPick} />
        </div>
      </div>
    </div>
  );
}

function RegimeStrip({ regime }) {
  if (!regime?.benchmarks?.length) return null;
  const labelColor =
    regime.label === "risk-on" ? "text-emerald-300 border-emerald-700 bg-emerald-600/20"
    : regime.label === "risk-off" ? "text-rose-300 border-rose-700 bg-rose-600/20"
    : "text-gray-300 border-edge bg-ink";
  return (
    <div className="flex items-center gap-3 flex-wrap mt-3 pt-3 border-t border-edge/60">
      <span className={`text-xs px-2 py-1 rounded border ${labelColor}`}>
        sector regime: {regime.label || "unknown (need benchmark history)"}
      </span>
      {regime.benchmarks.map((b) => (
        <span key={b.symbol} className="text-xs text-gray-400">
          <b className="text-gray-200">{b.symbol}</b>{" "}
          <span className={pctColor(b.return_20d)}>{fmtPct(b.return_20d)}</span>
          <span className="text-gray-600"> 20d</span>
          {b.above_50dma !== null && (
            <span className={b.above_50dma ? "text-emerald-500" : "text-rose-500"}>
              {" "}{b.above_50dma ? "▲" : "▼"}50dma
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

function TrackRecordChip({ tr }) {
  if (!tr) return <span className="text-[10px] text-gray-600">no track record yet</span>;
  if (!tr.sufficient)
    return (
      <span className="text-[10px] text-gray-500">
        track record: n={tr.n_graded_1m ?? 0} graded — insufficient history, treat with caution
      </span>
    );
  const basis = tr.vs_benchmark ? "vs XBI" : "raw (no benchmark data)";
  return (
    <span className="text-[10px] text-gray-400">
      this signal (1m): <b className={tr.hit_rate_1m >= 0.5 ? "text-emerald-400" : "text-rose-400"}>
        {fmtPct(tr.hit_rate_1m, 0)}
      </b> hit rate {basis} · avg excess {fmtPct(tr.avg_excess_1m)} · n={tr.n_graded_1m}
    </span>
  );
}

function ActionCard({ c, onPick }) {
  const liq = c.liquidity || {};
  return (
    <div className="border border-edge rounded-xl p-3 hover:border-sky-800">
      <div className="flex items-start justify-between">
        <button onClick={() => onPick?.(c.symbol)} className="text-left">
          <span className="font-bold text-sky-400 text-lg">{c.symbol}</span>
          <span className="text-gray-400 text-sm ml-2">{c.name}</span>
        </button>
        <div className="text-right">
          <div className="text-2xl font-bold" style={{ color: scoreColor(c.composite) }}>
            {fmtScore10(c.composite)}<span className="text-xs text-gray-500">/10</span>
          </div>
          <div className="text-[10px] text-gray-500">signal vs universe</div>
        </div>
      </div>

      {/* Why it fired + that signal's honest track record */}
      <div className="mt-2 space-y-1.5">
        {c.flags.map((f, i) => (
          <div key={i} className="text-xs">
            <span className="text-gray-200">{FLAG_LABELS[f.type] || f.type}:</span>{" "}
            <span className="text-gray-400">{f.message}</span>
            <div><TrackRecordChip tr={f.track_record} /></div>
          </div>
        ))}
      </div>

      {/* The tradeable package */}
      <div className="mt-2 pt-2 border-t border-edge/60 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-gray-400">
          Last close <b className="text-gray-200">{fmtNum(c.last_price, 2)}</b>{" "}
          <span className={pctColor(c.price_change_1d)}>({fmtPct(c.price_change_1d)})</span>
        </span>
        <span className="text-gray-400">
          vs XBI 20d <b className={pctColor(c.relative_strength?.rs_20d)}>{fmtPct(c.relative_strength?.rs_20d)}</b>
        </span>
        {c.suggested_levels && (
          <span className="col-span-2 text-gray-400">
            Ref levels: entry <b className="text-gray-200">{c.suggested_levels.entry}</b> ·
            stop <b className="text-rose-300">{c.suggested_levels.stop}</b> ·
            target <b className="text-emerald-300">{c.suggested_levels.target}</b>
            <span className="text-gray-600"> (off {c.suggested_levels.anchored_on_close_of} close — not a logged call)</span>
          </span>
        )}
        {c.next_catalyst && (
          <span className="col-span-2 text-gray-400">
            Next catalyst: <b className="text-gray-200">{c.next_catalyst.event_type}</b>{" "}
            in {c.next_catalyst.days_until}d ({c.next_catalyst.date})
          </span>
        )}
        {c.binary_event && (
          <span className="col-span-2 text-amber-300/90">⚠ {c.binary_event.framing}</span>
        )}
        <span className="col-span-2 flex items-center gap-2">
          {liq.tier && (
            <span className={`px-1.5 py-0.5 rounded border text-[10px] ${TIER_BADGE[liq.tier] || ""}`}>
              liquidity {liq.tier}
            </span>
          )}
          {liq.warning && <span className="text-[10px] text-amber-300">{liq.warning}</span>}
          {c.sentiment_7d !== null && c.sentiment_7d !== undefined && (
            <span className="text-[10px] text-gray-500">
              7d social sentiment {fmtNum(c.sentiment_7d, 2)}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

function EmptyActionable({ catalysts, openCalls }) {
  return (
    <div className="text-sm text-gray-400 border border-edge rounded-lg p-3">
      <b className="text-gray-300">Nothing new fired in the last 48h — that's by design.</b>{" "}
      Flags are tuned to be trustworthy, not busy. Meanwhile:{" "}
      {catalysts.length
        ? `${catalysts.length} catalyst(s) land within 7 days (below)`
        : "no catalysts inside 7 days"}
      {" · "}
      {openCalls.length
        ? `${openCalls.length} open call(s) being tracked (below)`
        : "no open calls"}
      . The Watchlist and Heatmap tabs show the full universe ranking.
    </div>
  );
}

function MoverList({ title, rows, onPick }) {
  return (
    <div>
      <div className="text-xs text-gray-500 mb-1">{title}</div>
      <div className="space-y-1">
        {(rows || []).map((m) => (
          <button key={m.symbol} onClick={() => onPick?.(m.symbol)}
            className="w-full flex justify-between text-sm p-1.5 rounded hover:bg-ink">
            <span><b className="text-sky-400">{m.symbol}</b> <span className="text-gray-500 text-xs">{m.name}</span></span>
            <span className={pctColor(m.change)}>{fmtPct(m.change)}</span>
          </button>
        ))}
        {!rows?.length && <div className="text-xs text-gray-600">no price data yet</div>}
      </div>
    </div>
  );
}
