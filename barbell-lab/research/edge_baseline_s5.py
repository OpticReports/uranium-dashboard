#!/usr/bin/env python3
"""EDGE-MONITOR baseline generator: S5 blend daily backtest returns.

Replays the paper engine's S3/S4 books through the REAL engine code path
(btc-paper-engine replay harness, 4h fixture bars) and composes the S5 blend
per bar with the live engine's exact formula
(live.py::_blend_step: r5 = 1.5*(0.75*r3_mtm + 0.25*r4_mtm), mtm = equity +
unrealized), then samples the last bar of each UTC day -> daily returns.

Frozen output: research/fixtures/s5_backtest_daily.json (provenance inside).
Run from repo root:  python barbell-lab/research/edge_baseline_s5.py
"""
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.normpath(os.path.join(HERE, "..", "..", "btc-paper-engine", "backend"))
sys.path.insert(0, ENG)

from app import config as ecfg                                    # noqa: E402
from app.engine.core import Bar, Book, eval_donchian, eval_signal, \
    process_closed_bar, resolve_open_exit                         # noqa: E402
from app.engine.replay import accrue_cash_yield, compute_indicators  # noqa: E402

FIX = os.path.join(ENG, "tests", "fixtures", "bars_4h_btcusd.csv")
OUT = os.path.join(HERE, "fixtures", "s5_backtest_daily.json")
W_TREND, LEV = 0.25, 1.5                     # live.py BLENDS["S5"]
CASH_APY = 0.04                              # research config basis
START = int(datetime(2024, 7, 24, tzinfo=timezone.utc).timestamp())
END = int(datetime(2026, 7, 24, tzinfo=timezone.utc).timestamp())
WARMUP = 210


def unrealized(b: Book, price: float) -> float:
    if b.position is None:
        return 0.0
    sgn = 1.0 if b.position.side == "L" else -1.0
    return b.position.qty * (price - b.position.entry_price) * sgn


def main() -> None:
    rows = list(csv.DictReader(open(FIX)))
    bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"])) for r in rows]
    inds = compute_indicators(bars)
    cfgs = {c.name: c for c in ecfg.RESEARCH_BOOKS if c.name in ("S3", "S4")}
    assert set(cfgs) == {"S3", "S4"}, f"engine config missing books: {cfgs}"
    books = {n: Book(cfg=c) for n, c in cfgs.items()}
    scfg, tcfg = ecfg.RESEARCH_SIGNAL, ecfg.RESEARCH_TRADE

    eq5, p3, p4 = 1.0, None, None
    daily: dict[str, float] = {}             # UTC date -> S5 eq at last bar
    for i, bar in enumerate(bars):
        if i < WARMUP or bar.ts < START:
            continue
        if bar.ts > END:
            break
        for b in books.values():
            resolve_open_exit(b, bar, tcfg)
        sigs = {"pullback": eval_signal(bar, inds[i], scfg),
                "donchian": eval_donchian(bar, inds[i])}
        for b in books.values():
            process_closed_bar(b, bar, inds[i], scfg, tcfg,
                               sigs[b.cfg.strategy])
            accrue_cash_yield(b, CASH_APY)
        cur3 = books["S3"].equity + unrealized(books["S3"], bar.close)
        cur4 = books["S4"].equity + unrealized(books["S4"], bar.close)
        if p3 is not None:
            r3, r4 = cur3 / p3 - 1.0, cur4 / p4 - 1.0
            eq5 *= 1.0 + LEV * ((1.0 - W_TREND) * r3 + W_TREND * r4)
        p3, p4 = cur3, cur4
        day = datetime.fromtimestamp(bar.ts, tz=timezone.utc).date().isoformat()
        daily[day] = eq5

    n_trades = sum(len(b.trades) for b in books.values())
    days = sorted(daily)
    rets = [daily[days[i]] / daily[days[i - 1]] - 1.0 for i in range(1, len(days))]
    bars_hash = hashlib.sha256(open(FIX, "rb").read()).hexdigest()[:16]
    out = {"strategy": "S5-live", "generated": "frozen at registration",
           "provenance": {"engine": "btc-paper-engine replay (real code path)",
                          "bars_fixture_sha256_16": bars_hash,
                          "blend": f"{1-W_TREND:.0%} S3 + {W_TREND:.0%} S4 @ {LEV}x, mtm per 4h bar",
                          "cash_apy": CASH_APY, "warmup_bars": WARMUP,
                          "window": [START, END]},
           "n_trades": n_trades,
           "expected_trades_per_day": round(n_trades / max(len(days) - 1, 1), 4),
           "dates": days[1:], "returns": rets}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"))
    tot = 1.0
    for r in rets:
        tot *= 1 + r
    print(f"S5 daily baseline: {len(rets)} days {days[0]}..{days[-1]}, "
          f"total {tot - 1:+.1%}")


if __name__ == "__main__":
    main()
