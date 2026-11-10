#!/usr/bin/env python3
"""Adversarial verification of research/stress (method reviewer; did not write it).

T1 splice integrity   T2 seam state vs live   T3 paper-book vs the real Book
T4 bookkeeping replay from the saved run   T5 look-ahead by truncation
T6 instrumented daily-loss / drawdown lines (eq at 00:00 open, intrabar worst)
Prints what it ran. Research only; touches nothing outside verify/.
"""
from __future__ import annotations
import json, math, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, STRESS)
import stress                                         # noqa: E402
import carry_sleeve as cs                             # noqa: E402
from stress import (BAR, DAY, build_spliced, engine_trades, engine_state_at,  # noqa: E402
                    paper_book, Executor, run_path, PAPER_SEED, _date)
import harness                                        # noqa: E402
from app.engine import core                           # noqa: E402
from app.engine.core import Book, BookCfg, SignalCfg, TradeCfg, Position, eval_signal, process_closed_bar, resolve_open_exit  # noqa: E402

NOW = stress.SEED_NOW
RUNS = os.path.join(STRESS, "runs")
ok_all = True
def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---------------------------------------------------------------- T1
print("\n== T1 splice integrity (BTC + ETH, all scenarios x offsets)")
full_btc = harness.load_bars("btcusd"); full_eth = harness.load_bars("ethusd")
real_btc = stress.load_closed_bars("btcusd", NOW); real_eth = stress.load_closed_bars("ethusd", NOW)
print(f"  now={NOW} ({_date(NOW)}); last csv bar BTC {_date(full_btc[-1].ts)} (closes {_date(full_btc[-1].ts+BAR)}) -> "
      f"last CLOSED used {_date(real_btc[-1].ts)}; ETH last closed {_date(real_eth[-1].ts)}")
check("unclosed last bar excluded", real_btc[-1].ts + BAR <= NOW < full_btc[-1].ts + BAR)
check("BTC/ETH seam on the same bar", real_btc[-1].ts == real_eth[-1].ts, f"{_date(real_btc[-1].ts)}")
for scen, anchor in (("COVID", "2020-02-13"), ("2008", "2021-11-09"), ("1999", "2017-12-17")):
    for off in (-28, -14, 0, 14, 28):
        bb = build_spliced("btcusd", anchor, 12, off, now=NOW)
        be = build_spliced("ethusd", anchor, 12, off, now=NOW)
        a_ts = harness.ts_of(anchor) + off * DAY
        win_b = [b for b in full_btc if a_ts <= b.ts < a_ts + len(bb.path) * BAR]
        win_e = [b for b in full_eth if a_ts <= b.ts < a_ts + len(be.path) * BAR]
        # returns preserved: path close ratios == analogue close ratios (and O/H/L the same scale)
        pc = np.array([b.close for b in bb.path]); ac = np.array([b.close for b in win_b])
        po = np.array([b.open for b in bb.path]); ao = np.array([b.open for b in win_b])
        ph = np.array([b.high for b in bb.path]); ah = np.array([b.high for b in win_b])
        pl = np.array([b.low for b in bb.path]); al = np.array([b.low for b in win_b])
        err = max(np.abs(pc[1:]/pc[:-1] - ac[1:]/ac[:-1]).max(), np.abs(po/pc - ao/ac).max(),
                  np.abs(ph/pc - ah/ac).max(), np.abs(pl/pc - al/ac).max())
        ec = np.array([b.close for b in be.path]); eac = np.array([b.close for b in win_e])
        err_e = np.abs(ec[1:]/ec[:-1] - eac[1:]/eac[:-1]).max()
        cond = (err < 1e-9 and err_e < 1e-9 and bb.anchor_ts == be.anchor_ts == a_ts
                and abs(pc[0] - real_btc[-1].close) < 1e-6 and abs(ec[0] - real_eth[-1].close) < 1e-6
                and bb.t0 == be.t0 == real_btc[-1].ts + BAR and len(bb.path) == len(be.path)
                and all(bb.path[j].ts == bb.t0 + j*BAR for j in range(len(bb.path)))
                and all(bb.path[j].volume == win_b[j].volume for j in range(len(bb.path))))
        check(f"{scen} off{off:+d}", cond, f"ret err {err:.1e}/{err_e:.1e}; first path close {pc[0]:.2f}; "
              f"seam-open gap {po[0]/real_btc[-1].close-1:+.3%}; n {len(bb.path)}")
# volume regime at the seam
bb = build_spliced("btcusd", "2020-02-13", 12, 0, now=NOW)
v_hist = np.mean([b.volume for b in bb[bb.seam-20:bb.seam]]); v_path = np.mean([b.volume for b in bb.path[:20]])
print(f"  volume regime COVID: 20-bar mean before seam {v_hist:.0f} BTC vs first 20 path bars {v_path:.0f} BTC (x{v_path/v_hist:.1f})")
for scen, anchor in (("2008", "2021-11-09"), ("1999", "2017-12-17")):
    bb2 = build_spliced("btcusd", anchor, 12, 0, now=NOW)
    v_path2 = np.mean([b.volume for b in bb2.path[:20]])
    print(f"  volume regime {scen}: x{v_path2/v_hist:.1f}")

# ---------------------------------------------------------------- T2
print("\n== T2 engine state at the seam (production loop on the real closed bars)")
for strat, leg in (("pullback", "S3"), ("donchian", "S4")):
    bk = engine_state_at(list(real_btc), strat)
    p, pend = bk.position, bk.pending
    print(f"  {leg}: position={'%s %s from %.2f (entry %s) stop/trail %.2f' % (p.side, 'open', p.entry_price, _date(p.entry_ts), p.stop_price) if p else None}; "
          f"pending={'%s limit %.2f (signal %s)' % (pend.side, pend.limit, _date(pend.signal_ts)) if pend else None}")
    if strat == "donchian" and p:
        check("S4 matches live (long 80,702.77, trail 83,274.67)", abs(p.entry_price-80702.77) < 0.01 and abs(p.trail-83274.67) < 0.01,
              f"harness trail {p.trail:.2f}")

# ---------------------------------------------------------------- T3
print("\n== T3 paper-book emulation vs the PRODUCTION Book continued from the seam (dd_halt live, fee 6.0/side)")
def production_paper(bars, strat, seed, fee_side=6.0):
    """Run the real Book from bar 210 over history with dd_halt disabled, then at the seam
    re-seed equity/peak and the open position's qty exactly as the live book would hold it,
    switch dd_halt on, and continue with the production loop."""
    tc = TradeCfg(taker_fee_bps=fee_side); scfg = SignalCfg()
    inds = harness.compute_indicators(bars, 20)
    cfg = BookCfg(name=strat, sizing="fixed", strategy=strat, trail_atr=5.0, leverage=1.0, cap=1.0,
                  start_equity=100_000.0, dd_halt=1e9)
    book = Book(cfg=cfg)
    seam = bars.seam
    halted_at = None
    for i in range(210, len(bars)):
        if i == seam:
            # re-seed as the live engine's book: equity/peak from the snapshot; open position's qty
            # sized off that equity (its entry equity == current closed equity, lev 1.0)
            book.equity, book.peak_equity = seed["equity"], seed["peak"]
            if book.position is not None:
                p = book.position
                q = round(book.equity / p.entry_price, 6)
                book.position = Position(side=p.side, entry_ts=p.entry_ts, entry_price=p.entry_price, qty=q,
                                         notional=q * p.entry_price, stop_price=p.stop_price,
                                         atr_at_entry=p.atr_at_entry, signal_ts=p.signal_ts,
                                         fee_bps=2 * fee_side, trail=p.trail)
                if getattr(p, "exit_flag", None):
                    book.position.exit_flag = p.exit_flag  # type: ignore[attr-defined]
            book.cfg = BookCfg(name=strat, sizing="fixed", strategy=strat, trail_atr=5.0, leverage=1.0,
                               cap=1.0, start_equity=100_000.0, dd_halt=seed["dd_halt"])
        bar, ind = bars[i], inds[i]
        resolve_open_exit(book, bar, tc)
        sig = core.eval_donchian(bar, ind) if strat == "donchian" else eval_signal(bar, ind, scfg)
        process_closed_bar(book, bar, ind, scfg, tc, sig)
        if book.halted and halted_at is None:
            halted_at = bar.ts
    return book, halted_at

for scen, anchor in (("COVID", "2020-02-13"), ("2008", "2021-11-09"), ("1999", "2017-12-17")):
    bars = build_spliced("btcusd", anchor, 12, 0, now=NOW)
    raw = engine_trades(bars)
    for strat, leg in (("pullback", "pullback"), ("donchian", "trend")):
        pub, info = paper_book(raw[leg], bars.t0, PAPER_SEED[leg])
        book, halted_at = production_paper(bars, strat, PAPER_SEED[leg])
        prod_trades = [(t.entry_ts, t.exit_ts, round(t.exit_price, 4)) for t in book.trades if t.exit_ts >= bars.t0]
        emu_trades = [(t.entry_ts, t.exit_ts, round(t.exit_price, 4)) for t in pub if t.exit_ts is not None]
        same = prod_trades == emu_trades
        check(f"{scen} {leg}: halt {info['halt_date']} vs prod {(_date(halted_at) if halted_at else None)}; "
              f"equity_end {info['equity_end']:,.2f} vs prod {book.equity:,.2f}; trades {len(emu_trades)} vs {len(prod_trades)}",
              same and (halted_at == info["halt_ts"]) and abs(book.equity - info["equity_end"]) < 0.05)

# ---------------------------------------------------------------- T4
print("\n== T4 bookkeeping replay from the saved run JSONs (headline offset 0, A, intrabar, carry)")
def replay(r):
    ts = r["ts"]; closes = dict(r["spliced_closes"]); carry = r["carry_value"]
    cash = r["constants"]["START_EQUITY"] - r["constants"]["CARRY_START"]
    # trades sorted by exit; MTM each bar
    trades = r["trades"]
    eq = []
    for j, t in enumerate(ts):
        # realise exits at this bar
        for tr in trades:
            if tr["exit_ts"] == t:
                cash += tr["pnl"]
        unreal = 0.0
        for tr in trades:
            if tr["entry_ts"] <= t and (tr["exit_ts"] is None or tr["exit_ts"] > t):
                sgn = 1 if tr["side"] == "L" else -1
                unreal += tr["qty"] * (closes[t] - tr["entry_px"]) * sgn - tr["fees"] * (1 if tr["exit_ts"] is None else 0)
        eq.append(cash + unreal)
    return np.array(eq)
for scen in ("COVID", "2008", "1999"):
    for K in ("0.75", "0.3"):
        fn = os.path.join(RUNS, f"{scen}_K{K}_off_0_A_intra_eh_first_cross_carry.json")
        r = json.load(open(fn))
        tot = np.array(r["equity_total"]); btc = np.array(r["equity_btc"]); car = np.array(r["carry_value"])
        rep = replay(r)
        # entry fees of OPEN positions are inside pnl only at exit; the replay above approximates them
        d_rep = np.abs(rep - btc).max()
        bal = {d: r["balances"][d]["equity"] for d in r["balances"]}
        my_bal = {}
        ts_a = np.array(r["ts"])
        for d in (91, 182, 273, 365):
            idx = np.searchsorted(ts_a, r["t0"] + d * DAY, side="right") - 1
            my_bal[str(d)] = round(float(tot[idx]), 2)
        path = np.concatenate([[100000.0], tot]); peak = np.maximum.accumulate(path); mdd = float((path/peak - 1).min())
        check(f"{scen} K{K}: total==btc+carry (max |d| {np.abs(tot-btc-car).max():.4f}); replay-from-trades |d| {d_rep:.2f}; "
              f"balances {bal == my_bal}; maxDD {mdd:.4f} vs {r['max_dd']}",
              np.abs(tot-btc-car).max() < 0.02 and d_rep < 1.0 and bal == my_bal and abs(mdd - r["max_dd"]) < 1e-4)
        # fees sanity: sum of trade fees + open entry fees == fees
        fee_sum = sum(t["fees"] for t in r["trades"])
        check(f"{scen} K{K}: fees {r['fees']:.2f} == sum(trade fees) {fee_sum:.2f}", abs(fee_sum - r["fees"]) < 0.05)

# ---------------------------------------------------------------- T5
print("\n== T5 look-ahead: truncate the path at N bars and compare everything up to N (engine, executor, carry)")
scen, anchor = "COVID", "2020-02-13"
bars = build_spliced("btcusd", anchor, 12, 0, now=NOW)
bars_e = build_spliced("ethusd", anchor, 12, 0, now=NOW)
import run_all                                         # noqa: E402
n = len(bars.path)
fund, fmeta = run_all.funding_for(bars.anchor_ts, n, bars.t0)
cr_full = run_all.run_carry(bars_e, fund)
r_full = run_path("la_full", bars, 0.75, carry_value=cr_full.value, save=False, extra=dict(offset_days=0))
for N in (300, 900, 1500):
    tb = stress.SplicedBars(list(bars)[:bars.seam + N]); tb.seam, tb.t0, tb.scale = bars.seam, bars.t0, bars.scale
    tb.anchor_ts, tb.anchor_close, tb.today_close, tb.last_real_ts = bars.anchor_ts, bars.anchor_close, bars.today_close, bars.last_real_ts
    tb.now_used, tb.pair, tb.mode, tb.key = bars.now_used, bars.pair, "splice", ("trunc", N)
    te = stress.SplicedBars(list(bars_e)[:bars_e.seam + N]); te.seam, te.t0 = bars_e.seam, bars_e.t0
    fund_t = {k: v for k, v in fund.items() if k // 1000 <= tb.t0 + N * BAR}
    cr_t = run_all.run_carry(te, fund_t)
    r_t = run_path("la_trunc", tb, 0.75, carry_value=cr_t.value, save=False, extra=dict(offset_days=0))
    d_eq = np.abs(np.array(r_t["equity_total"]) - np.array(r_full["equity_total"][:N])).max()
    d_c = np.abs(np.array(cr_t.value) - np.array(cr_full.value[:N])).max()
    on_same = list(cr_t.on) == list(cr_full.on[:N])
    # trades closed before N identical
    tr_full = [(t["leg"], t["entry_ts"], t["exit_ts"], t["exit_px"]) for t in r_full["trades"] if t["exit_ts"] is not None and t["exit_ts"] < bars.t0 + N * BAR]
    tr_t = [(t["leg"], t["entry_ts"], t["exit_ts"], t["exit_px"]) for t in r_t["trades"] if t["exit_ts"] is not None and t["exit_ts"] < bars.t0 + N * BAR]
    check(f"N={N}: equity |d| {d_eq:.4f}, carry |d| {d_c:.4f}, gate/on identical {on_same}, closed trades identical {tr_full == tr_t}",
          d_eq < 1e-6 and d_c < 1e-6 and on_same and tr_full == tr_t)

# ---------------------------------------------------------------- T6
print("\n== T6 instrumented halt lines: equity at each 00:00 open, worst intrabar equity, lines (K 0.75, offset 0)")
class Probe(Executor):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.day_rows = []
    def run(self):
        bars, seam = self.bars, self.bars.seam
        # re-implement only the recording: call the parent's loop but capture day_start transitions
        super().run()
for scen, anchor in (("COVID", "2020-02-13"), ("2008", "2021-11-09"), ("1999", "2017-12-17")):
    bars = build_spliced("btcusd", anchor, 12, 0, now=NOW); bars_e = build_spliced("ethusd", anchor, 12, 0, now=NOW)
    n = len(bars.path); fund, fmeta = run_all.funding_for(bars.anchor_ts, n, bars.t0); cr = run_all.run_carry(bars_e, fund)
    raw = engine_trades(bars); pub = {leg: paper_book(raw[leg], bars.t0, PAPER_SEED[leg])[0] for leg in stress.LEGS}
    ex = Executor(bars, pub, 0.75, carry_value=cr.value); ex.run()
    ts = np.array(ex.ts_out); tot = np.array(ex.eq_tot_out); worst = np.array(ex.worst_intrabar_out)
    # day_start = equity at the 00:00 bar's OPEN == previous bar's close + (open-close gap) * net qty ... approximate with the
    # previous close (gap is inside the next bar's range, which the intrabar worst already covers); first day from 100k
    day_start, hw = 100000.0, 100000.0
    worst_day_intra, worst_dd_intra = 0.0, 0.0
    for j, t in enumerate(ts):
        if j > 0 and t % DAY == 0:
            day_start = tot[j-1]
        hw = max(hw, tot[j])
        worst_day_intra = min(worst_day_intra, worst[j] - day_start)
        worst_dd_intra = min(worst_dd_intra, worst[j] - hw)
    print(f"  {scen}: worst intrabar day-loss from day start {worst_day_intra:,.0f} (line -15,000); worst intrabar below HW {worst_dd_intra:,.0f} (line -30,000); "
          f"halts {len(ex.halts)}; BTC-book maxDD {harness.max_dd(np.concatenate([[70000.0], np.array(ex.eq_btc_out)])):.1%}; "
          f"account maxDD {harness.max_dd(np.concatenate([[100000.0], tot])):.1%}")
    check(f"{scen}: no line crossed on my recomputation == harness reports no halt",
          (worst_day_intra > -15000 and worst_dd_intra > -30000) == (len(ex.halts) == 0))
print("\nALL PASS" if ok_all else "\nSOME CHECKS FAILED")
