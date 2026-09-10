"""How much did the exit_flag lag cost, and what does closing early change?

The engine flags a close-based exit at bar N's close and books the fill at
bar N+1's OPEN. Until 2026-09-09 the executor ignored that flag and closed
only once the engine reported FLAT - which happens when bar N+1 CLOSES, a
full 4h later. So:

    engine's booked exit   = open(N+1)
    executor BEFORE the fix = market at the close of bar N+1
    executor AFTER  the fix = market at the close of bar N  ~= open(N+1)

The fix is therefore a TRACKING-ERROR correction, not an alpha claim: it
moves our fill onto the engine's own reference. Per trade the change is
sign * (open(N+1) - close(N+1)) / entry_price, and its sign is a coin flip
by construction - one bar of unhedged, unmodelled market exposure removed.

Only the PULLBACK leg is affected. S4/donchian exits only via its chandelier
trail, booked "STOP" and filled in-bar by a resting venue stop order, so it
never sets exit_flag (core.py _process_donchian).

    python3 research/exit_lag/measure.py <bars_csv> [out_dir]

Honest about what is NOT modelled: fees on both legs are identical either
way and cancel; slippage is assumed equal at both times (it is not - the
4h boundary is a liquidity peak, which if anything favours the OLD fill);
funding for one extra hour of exposure is ignored (~0.00125%/hr, an order
of magnitude below the price term).
"""
from __future__ import annotations

import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "..", "..", "..", "btc-paper-engine", "backend")
sys.path.insert(0, ENGINE)

from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,           # noqa: E402
                        RESEARCH_TRADE)

BAR_S = 4 * 3600
LIVE_START = 1640995200          # 2022-01-01, the window the S6 blend claims
SIZING_BASE = 25_000.0
KELLY_M = 0.135
PULLBACK_W = 0.75                # S6 = 75% S3 + 25% S4
LEV = 1.5
PULLBACK_NOTIONAL = KELLY_M * LEV * PULLBACK_W * SIZING_BASE


def load(path: str) -> list[Bar]:
    out = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            out.append(Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                           high=float(r["high"]), low=float(r["low"]),
                           close=float(r["close"]), volume=float(r["volume"])))
    return out


def main() -> None:
    bars_csv = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else HERE
    bars = load(bars_csv)
    by_ts = {b.ts: b for b in bars}
    s3 = next(b for b in RESEARCH_BOOKS if b.name == "S3")
    res = run_replay(bars, [s3], RESEARCH_SIGNAL, RESEARCH_TRADE,
                     start_ts=LIVE_START, cash_apy=0.0)
    trades = res.books["S3"].trades
    span_years = (bars[-1].ts - max(LIVE_START, bars[0].ts)) / (365.25 * 86400)

    rows = []
    for t in trades:
        if t.exit_reason not in ("SIGNAL", "TIME"):
            continue                       # STOP fills are resting venue orders
        bar = by_ts.get(t.exit_ts)         # the bar we book the exit AT
        if bar is None:
            continue
        # self-check: the engine really did book this exit at the bar's OPEN
        assert abs(t.exit_price - bar.open) < 1e-6, (
            f"exit {t.exit_ts} booked at {t.exit_price}, bar open {bar.open}")
        sgn = 1.0 if t.side == "L" else -1.0
        # AFTER the fix we exit at ~open(N+1); BEFORE, at close(N+1).
        delta_pct = sgn * (bar.open - bar.close) / t.entry_price * 100.0
        rows.append({"exit_ts": t.exit_ts, "side": t.side,
                     "reason": t.exit_reason, "delta_pct": delta_pct,
                     "usd": delta_pct / 100.0 * PULLBACK_NOTIONAL})

    n_all, n_hit = len(trades), len(rows)
    d = [r["delta_pct"] for r in rows]
    better = sum(1 for x in d if x > 0)
    total = sum(d)

    # Is the mean distinguishable from zero? A stationary bootstrap would be
    # overkill on 124 independent per-trade deltas; an ordinary percentile
    # bootstrap on the mean is the honest instrument here.
    import random
    random.seed(20260909)
    means = sorted(sum(random.choice(d) for _ in range(n_hit)) / n_hit
                   for _ in range(20_000))
    lo, hi = means[int(0.025 * len(means))], means[int(0.975 * len(means))]

    print(f"bars                 {len(bars)}  "
          f"{bars[0].ts} .. {bars[-1].ts}  ({span_years:.2f}y from {LIVE_START})")
    print(f"S3 trades            {n_all}")
    print(f"  affected (SIGNAL/TIME) {n_hit}  ({100*n_hit/n_all:.1f}%)")
    print(f"  unaffected (STOP)      {n_all-n_hit}")
    print(f"per affected trade, change in exit price vs the old late fill:")
    print(f"  mean               {statistics.mean(d):+.4f}%")
    print(f"  median             {statistics.median(d):+.4f}%")
    print(f"  stdev              {statistics.stdev(d):.4f}%")
    print(f"  mean 95% CI        [{lo:+.4f}%, {hi:+.4f}%]  "
          f"{'INCLUDES ZERO' if lo <= 0 <= hi else 'excludes zero'}")
    print(f"  better             {better}/{n_hit} ({100*better/n_hit:.1f}%)")
    print(f"  worse              {n_hit-better}/{n_hit} "
          f"({100*(n_hit-better)/n_hit:.1f}%)")
    print(f"  best / worst       {max(d):+.3f}% / {min(d):+.3f}%")
    print(f"total over the window {total:+.3f}% of leg notional "
          f"= {total/span_years:+.3f}%/yr")
    print(f"at base ${SIZING_BASE:,.0f} (pullback leg ${PULLBACK_NOTIONAL:,.0f}): "
          f"{total/span_years/100*PULLBACK_NOTIONAL:+,.0f}/yr")
    print()
    print("READ THIS AS: one bar of unmodelled exposure removed, not a "
          "money-maker. The mean is a rounding error against its own stdev.")

    with open(os.path.join(out_dir, "measure.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {os.path.join(out_dir, 'measure.csv')}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
