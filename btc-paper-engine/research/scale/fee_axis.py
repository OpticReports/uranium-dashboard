"""Re-establish the governing Kelly envelope for S5 - the frozen one cannot be
reproduced, and the harness that produced it is now a no-op.

WHY THIS SCRIPT EXISTS (found while answering the scale question):
  refit_kelly.py overrides the fee by monkeypatching core.Position with
      kw.setdefault("fee_bps", fee)
  Commit 132e0a6 ("pullback books now charge the configured fee") changed BOTH
  Position construction sites (core.py:261 donchian, core.py:337 pullback) to
  pass  fee_bps=2 * tcfg.taker_fee_bps  as an explicit KEYWORD. setdefault
  therefore never fires, and the baseline_6.0 and live_8.64 arms of
  RESEARCH_FEES.md now produce BYTE-IDENTICAL streams. Measured below.

  So the fee axis must be driven through TradeCfg.taker_fee_bps (per side;
  both sites charge 2x, so round trip = 2 x taker_fee_bps).

Fee levels that matter:
   3.00 per side ->  6.00 rt : what the pullback books ACTUALLY charged when
                              the frozen numbers were produced (they were
                              pinned at the 6.0 dataclass default = round trip)
   4.32 per side ->  8.64 rt : the MEASURED live round trip (RESEARCH_FEES.md,
                              4 of 4 intended-maker entries crossed)
   6.00 per side -> 12.00 rt : the CURRENT engine default; deliberately left
                              here as "the registered objective" that
                              reproduces the reference backtest

Run: python3 research/scale/fee_axis.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                                # noqa: E402
import app.engine.core as core                                    # noqa: E402
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze                              # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")

def load(p):
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(p))]

def blend_steps(b3, b4, w_trend, lev):
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity)
                  for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity)
                    for t in b4.trades])
    p3 = p4 = 1.0
    out = []
    for _, which, ratio in evs:
        if which == "P":
            out.append(lev * (ratio / p3 - 1) * (1 - w_trend)); p3 = ratio
        else:
            out.append(lev * (ratio / p4 - 1) * w_trend); p4 = ratio
    return out

bars = load(BARS)
last = bars[-1].ts
START2Y = last - 730 * 86400

# ---- first: PROVE the old override is dead -------------------------------
_O = core.Position
def old_style(fee):
    def _P(*a, **kw):
        kw.setdefault("fee_bps", fee)
        return _O(*a, **kw)
    core.Position = _P
    try:
        r = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE,
                       start_ts=START2Y, cash_apy=0.0)
    finally:
        core.Position = _O
    return blend_steps(r.books["S3"], r.books["S4"], 0.25, 1.5)

a, b = old_style(6.0), old_style(8.64)
print("=" * 78)
print("A. IS refit_kelly.py's FEE OVERRIDE STILL LIVE?")
print("=" * 78)
print(f"  setdefault-style override, fee 6.00 vs 8.64 round trip:")
print(f"    streams identical: {np.allclose(a, b)}   (n={len(a)})")
print(f"    sum|diff| = {float(np.abs(np.array(a)-np.array(b)).sum()):.12f}")
print("  -> the override is a NO-OP. RESEARCH_FEES.md's two arms are now the")
print("     same experiment, and its headline (S5 0.48->0.30) cannot be re-run")
print("     by its own runner. The fee axis must go through TradeCfg.")

# ---- the real fee axis ----------------------------------------------------
def cell(taker_per_side, cash_apy, lev, book_lbl):
    tcfg = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=taker_per_side)
    r = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, tcfg,
                   start_ts=START2Y, cash_apy=cash_apy)
    s = blend_steps(r.books["S3"], r.books["S4"], 0.25, lev)
    return analyze(s, book_lbl), r

FEES = [(3.00, "6.00 rt  (what frozen run actually charged pullback)"),
        (4.32, "8.64 rt  (MEASURED live round trip)"),
        (6.00, "12.00 rt (current engine default = registered objective)")]
BOOKS = [("S5", 1.5), ("S6", 2.0)]
OUT = {"override_dead": bool(np.allclose(a, b))}

for cash in (0.00, 0.04):
    print()
    print("=" * 78)
    print(f"B. GOVERNING ENVELOPE, 2y window, cash_apy {cash:.2f}")
    print("=" * 78)
    print(f"  {'book':<4} {'rt bps':>7} {'n':>4} {'mean%':>7} {'m*':>6} {'half':>6} "
          f"{'p10':>6} {'c*m*':>7} {'dd30':>6} {'REC':>6}  binding term")
    for lbl, lev in BOOKS:
        for taker, desc in FEES:
            A, _ = cell(taker, cash, lev, lbl)
            terms = {"half_kelly": A["half_kelly_m"],
                     "p10": A["bootstrap"]["p10"],
                     "c*xm*": round(A["shrinkage_c_star"] * A["kelly_m"], 2),
                     "dd30": A["dd_constrained"]["p_maxdd30_le_10pct"]}
            bind = min(terms.items(), key=lambda t: t[1])
            print(f"  {lbl:<4} {2*taker:>7.2f} {A['n']:>4} {A['mean_pct']:>7.3f} "
                  f"{A['kelly_m']:>6.2f} {terms['half_kelly']:>6.2f} "
                  f"{terms['p10']:>6.2f} {terms['c*xm*']:>7.2f} {terms['dd30']:>6.2f} "
                  f"{A['recommended_m']:>6.2f}  {bind[0]} @ {bind[1]}")
            OUT[f"{lbl}_rt{2*taker:.2f}_cash{cash:.2f}"] = {
                "analyze": A, "terms": terms, "binding": bind}
    print(f"  FROZEN for comparison (cash0.00): S5 rec 0.30 (p10), S6 rec 0.22 (p10)")

json.dump(OUT, open(os.path.join(HERE, "fee_axis.json"), "w"), indent=1, default=str)
print()
print(f"frozen -> {os.path.join(HERE, 'fee_axis.json')}")
