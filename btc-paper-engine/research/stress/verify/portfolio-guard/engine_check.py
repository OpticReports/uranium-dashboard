"""Re-run harness.leg_trades on the REBUILT spliced bars (COVID, offset 0) and
compare with the engine trade lists stress.py saved; inspect both books' state
at the seam (the live trend long 80,702.77 / trail 83,274.67; S3 LONG vs PENDING)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
CAGR = os.path.abspath(os.path.join(STRESS, "..", "cagr"))
BACKEND = os.path.abspath(os.path.join(STRESS, "..", "..", "backend"))
for p in (STRESS, CAGR, BACKEND, HERE):
    sys.path.insert(0, p)
import verify as V
import harness as H
from app.engine import core
from app.engine.core import Bar, Book, BookCfg, TradeCfg, eval_signal, process_closed_bar, resolve_open_exit

scen = sys.argv[1] if len(sys.argv) > 1 else "COVID"
R = json.load(open(os.path.join(STRESS, "runs", f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carry.json")))
now = R["now_used"]
btc = V.read_bars(os.path.join(CAGR, "data", "bars_4h_btcusd.csv"), now)
hist, path, scale, today_close = V.splice(btc, R["anchor_ts"], R["t0"], R["n_path_bars"], R["last_real_ts"])
print(f"{scen}: history {len(hist)} real bars (seam index {len(hist)} vs builder seam {R['seam']}), path {len(path)}, scale {scale:.9f} vs {R['scale']:.9f}")
bars = [Bar(ts=b[0], open=b[1], high=b[2], low=b[3], close=b[4], volume=b[5]) for b in hist + path]
t0 = R["t0"]

def as_dict(t):
    return dict(leg=t.leg, side=t.side, entry_ts=t.entry_ts, entry_price=t.entry_price,
                exit_ts=t.exit_ts, exit_price=t.exit_price, reason=t.reason)

mine = {"pullback": [as_dict(t) for t in H.leg_trades(bars, "pullback", leg="pullback")],
        "trend": [as_dict(t) for t in H.leg_trades(bars, "donchian", trail_atr=5.0, leg="trend")]}
for leg in ("pullback", "trend"):
    theirs = R["engine_trades"][leg]
    # keep the trades that touch the path (exit at/after t0, or still open)
    keep = [t for t in mine[leg] if t["exit_ts"] is None or t["exit_ts"] >= t0]
    print(f"\n{leg}: my full-history trades {len(mine[leg])}, touching the path {len(keep)}; builder saved {len(theirs)}")
    ok = len(keep) == len(theirs)
    for a, b in zip(keep, theirs):
        same = (a["side"] == b["side"] and a["entry_ts"] == b["entry_ts"] and a["exit_ts"] == b["exit_ts"]
                and abs(a["entry_price"] - b["entry_price"]) < 1e-6
                and ((a["exit_price"] is None and b["exit_price"] is None) or abs(a["exit_price"] - b["exit_price"]) < 1e-6)
                and a["reason"] == b["reason"])
        if not same:
            ok = False
            print("  DIFF mine", a, "\n       theirs", b)
    print(f"  trade lists {'IDENTICAL' if ok else 'DIFFER'}")
    print("  first:", keep[0])

# ---- state of both books at the seam, from the REAL bars only ----
def book_state(strategy, trail_atr=5.0, name="x"):
    inds = H.compute_indicators(bars)
    cfg = BookCfg(name=name, sizing="fixed", strategy=strategy, trail_atr=trail_atr,
                  leverage=1.0, cap=1.0, start_equity=1.0, dd_halt=1e9)
    book = Book(cfg=cfg)
    tcfg = TradeCfg(taker_fee_bps=H.LIVE_TAKER_BPS)
    scfg = core.SignalCfg()
    for i, bar in enumerate(bars):
        if i < 210:
            continue
        if bar.ts >= t0:
            break
        resolve_open_exit(book, bar, tcfg)
        sig = core.eval_donchian(bar, inds[i]) if strategy == "donchian" else eval_signal(bar, inds[i], scfg)
        process_closed_bar(book, bar, inds[i], scfg, tcfg, sig)
    return book

tb = book_state("donchian", name="trend")
p = tb.position
print(f"\nTREND book at the seam (after the last real bar {V.utc(hist[-1][0])}): position "
      f"{None if p is None else (p.side, V.utc(p.entry_ts), round(p.entry_price, 2), 'trail', round(p.trail, 2), 'signal', V.utc(p.signal_ts))}")
print("   live snapshot: LONG from 80,702.77 trail 83,274.67 ->",
      "MATCH" if p and p.side == "L" and abs(p.entry_price - 80702.77) < 0.01 and abs(p.trail - 83274.67) < 0.01 else "MISMATCH")
pb = book_state("pullback", name="pullback")
p = pb.position
print(f"PULLBACK book at the seam: position {None if p is None else (p.side, V.utc(p.entry_ts), round(p.entry_price, 2), 'stop', round(p.stop_price, 2), 'signal', V.utc(p.signal_ts))}"
      f" pending {None if pb.pending is None else (pb.pending.side, pb.pending.limit, V.utc(pb.pending.signal_ts))}")
b00 = [b for b in hist if b[0] == 1791331200][0]; b04 = [b for b in hist if b[0] == 1791345600][0]
print(f"   real 00:00 bar close (the limit) {b00[4]:.2f}; real 04:00 bar low {b04[3]:.2f} -> fill rule bar.low < limit: {b04[3] < b00[4]}")
print(f"   live snapshot said S3 PENDING a long limit; the CSV path says LONG from {b00[4]:.2f} entered 04:00 (seam discrepancy the builder flagged)")
# trail at the seam vs the first path bar's open for each scenario's first bar
print(f"\nfirst path bar open {path[0][1]:.2f} (trail 83,274.67 -> {'stopped at the open' if path[0][1] < 83274.67 else 'stop at the trail if low <= trail'})")
