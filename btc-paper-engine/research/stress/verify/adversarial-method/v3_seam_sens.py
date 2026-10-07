#!/usr/bin/env python3
"""T11 S3 seam state: production Book continued with the LIVE snapshot (S3 PENDING a long limit at the
    08:00Z close) instead of the CSV's LONG from 84,121.28 - does the COVID / 1999 S3 halt survive?
T12 paper-book fee basis 6.0 vs 4.32 per side - same question.
T13 1999 funding: mean XBTUSD rate over the stamps the trend leg actually held (cross-check of T7).
T14 claims: BTC-book arrays identical carry vs no-carry; worst-day claim; 12m range claim.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, STRESS)
import stress, run_all, harness                                   # noqa: E402
from stress import BAR, DAY, build_spliced, run_path, _date, PAPER_SEED, paper_book, engine_trades, Executor  # noqa: E402
from harness import Trade                                         # noqa: E402
from app.engine import core                                       # noqa: E402
from app.engine.core import Book, BookCfg, SignalCfg, TradeCfg, Position, Pending, eval_signal, process_closed_bar, resolve_open_exit  # noqa: E402
NOW = stress.SEED_NOW
RUNS = os.path.join(STRESS, "runs")

def prod_book(bars, strat, seed, fee_side=6.0, seam_override=None):
    tc = TradeCfg(taker_fee_bps=fee_side); scfg = SignalCfg()
    inds = harness.compute_indicators(bars, 20)
    cfg = BookCfg(name=strat, sizing="fixed", strategy=strat, trail_atr=5.0, leverage=1.0, cap=1.0,
                  start_equity=100_000.0, dd_halt=1e9)
    book = Book(cfg=cfg); halted_at = None
    for i in range(210, len(bars)):
        if i == bars.seam:
            book.equity, book.peak_equity = seed["equity"], seed["peak"]
            if seam_override == "pending_at_close":
                # the LIVE snapshot: no position, a long limit resting at the last closed bar's close
                last = bars[bars.seam - 1]; ind_last = inds[bars.seam - 1]
                book.position = None
                book.pending = Pending(side="L", limit=last.close, signal_ts=last.ts, atr_signal=ind_last.atr14 or 0.0)
            elif book.position is not None:
                p = book.position; q = round(book.equity / p.entry_price, 6)
                book.position = Position(side=p.side, entry_ts=p.entry_ts, entry_price=p.entry_price, qty=q,
                                         notional=q * p.entry_price, stop_price=p.stop_price, atr_at_entry=p.atr_at_entry,
                                         signal_ts=p.signal_ts, fee_bps=2 * fee_side, trail=p.trail)
            book.cfg = BookCfg(name=strat, sizing="fixed", strategy=strat, trail_atr=5.0, leverage=1.0, cap=1.0,
                               start_equity=100_000.0, dd_halt=seed["dd_halt"])
        bar, ind = bars[i], inds[i]
        resolve_open_exit(book, bar, tc)
        sig = core.eval_donchian(bar, ind) if strat == "donchian" else eval_signal(bar, ind, scfg)
        process_closed_bar(book, bar, ind, scfg, tc, sig)
        if book.halted and halted_at is None:
            halted_at = bar.ts
    return book, halted_at

def trades_of(book, leg):
    out = [Trade(leg, t.side, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price, t.exit_reason) for t in book.trades]
    if book.position is not None:
        p = book.position; out.append(Trade(leg, p.side, p.entry_ts, p.entry_price, None, None, "OPEN"))
    return out

print("== T11/T12 S3 seam-state and fee-basis sensitivity of the engine-book halt and the 12m balance (K 0.75, offset 0)")
for scen, anchor in (("COVID", "2020-02-13"), ("1999", "2017-12-17"), ("2008", "2021-11-09")):
    bars = build_spliced("btcusd", anchor, 12, 0, now=NOW); bars_e = build_spliced("ethusd", anchor, 12, 0, now=NOW)
    n = len(bars.path); fund, _ = run_all.funding_for(bars.anchor_ts, n, bars.t0); cr = run_all.run_carry(bars_e, fund)
    raw = engine_trades(bars)
    base_pub = {leg: paper_book(raw[leg], bars.t0, PAPER_SEED[leg])[0] for leg in stress.LEGS}
    for label, fee, ovr in (("CSV state (as run), fee 6.0", 6.0, None), ("LIVE state: S3 PENDING limit at 08:00Z close, fee 6.0", 6.0, "pending_at_close"),
                            ("CSV state, paper fee 4.32", 4.32, None)):
        bk, h = prod_book(bars, "pullback", PAPER_SEED["pullback"], fee_side=fee, seam_override=ovr)
        pub = dict(base_pub); pub["pullback"] = [t for t in trades_of(bk, "pullback") if t.exit_ts is None or t.exit_ts >= bars.t0]
        ex = Executor(bars, pub, 0.75, carry_value=cr.value); ex.run()
        tot = np.array(ex.eq_tot_out); ts = np.array(ex.ts_out)
        idx = np.searchsorted(ts, bars.t0 + 365 * DAY, side="right") - 1
        line = PAPER_SEED["pullback"]["peak"] * 0.7
        closes = [(t.exit_ts, round(t.equity_after, 0)) for t in bk.trades if t.exit_ts >= bars.t0][:3]
        print(f"  {scen:5s} {label:55s}: S3 halt {(_date(h) if h else None)}, S3 equity at/after halt {bk.equity:,.0f} (line {line:,.0f}); "
              f"first S3 trades {[(_date(a), b) for a, b in closes]}; 12m {tot[idx]:,.0f}; maxDD {harness.max_dd(np.concatenate([[1e5], tot])):.1%}")

print("\n== T13 XBTUSD funding during the stamps the 1999 trend leg held (sanity of -5.0k)")
bars = build_spliced("btcusd", "2017-12-17", 12, 0, now=NOW)
fund, _ = run_all.funding_for(bars.anchor_ts, len(bars.path), bars.t0, force="XBTUSD")
stamps = sorted((k // 1000, v) for k, v in fund.items() if k // 1000 >= bars.t0)
r = json.load(open(os.path.join(RUNS, "1999_K0.75_off_0_A_intra_eh_first_cross_carry.json")))
held_short, held_long = [], []
for s, rate in stamps:
    for tr in r["trades"]:
        if tr["leg"] == "trend" and tr["entry_ts"] < s and (tr["exit_ts"] is None or tr["exit_ts"] + BAR > s):
            (held_short if tr["side"] == "S" else held_long).append(rate)
print(f"  trend short stamps {len(held_short)} mean {np.mean(held_short)*1095*100:+.1f}%/yr (shorts PAY when negative); "
      f"long stamps {len(held_long)} mean {np.mean(held_long)*1095*100 if held_long else 0:+.1f}%/yr; "
      f"min stamp {min(v for _, v in stamps)*100:.3f}% / max {max(v for _, v in stamps)*100:.3f}% per 8h")

print("\n== T14 claims")
for scen in ("COVID", "2008", "1999"):
    a = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carry.json")))
    b = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_nocarry.json")))
    print(f"  {scen}: BTC-book equity carry vs nocarry identical: {a['equity_btc'] == b['equity_btc']}")
res = json.load(open(os.path.join(STRESS, "results.json")))
wd = {}
for scen in ("COVID", "2008", "1999"):
    S = res["scenarios"][scen]
    for off, s in S["runs"]["K0.75"].items():
        wd[(scen, off)] = s["worst_day"]["usd"]
    rg = S["range_12m"]["K0.75"]; rg3 = S["range_12m"]["K0.3"]
    print(f"  {scen}: 12m range K0.75 {rg['min']:,.0f}..{rg['max']:,.0f}, K0.3 {rg3['min']:,.0f}..{rg3['max']:,.0f}; "
          f"maxDD range K0.75 {min(rg['max_dd_by_offset'].values()):.1%}..{max(rg['max_dd_by_offset'].values()):.1%}; "
          f"worst day by offset {{{', '.join(f'{o}:{v:,.0f}' for o, v in [(k[1], v) for k, v in wd.items() if k[0] == scen])}}}")
print("  table in results.json:"); print("\n".join("    " + l for l in res["table"][:9]))
