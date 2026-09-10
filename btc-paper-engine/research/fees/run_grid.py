"""Registered fee grid — see PREREG.md (committed dbab333, before any run).

    python3 research/fees/run_grid.py <bars_csv> <out_dir>

Injects fee_bps into the PULLBACK book's Position only. _process_donchian
passes fee_bps explicitly, so setdefault leaves the trend book untouched:
the fee channel is the ONLY thing that differs between arms, which is the
property the counter-agent pass is asked to check.
"""
from __future__ import annotations
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))

import app.engine.core as core                                   # noqa: E402
from app.engine.core import Bar                                  # noqa: E402
from app.engine.replay import run_replay, book_stats             # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,         # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE

# PRE-REGISTERED. Do not edit after 2026-09-10.
TAKER = RESEARCH_TRADE.taker_fee_bps          # 6.0, the model's own number
HL_TAKER = 4.32                               # measured on all 17 live fills
FRACS = [0.00, 0.25, 0.50, 0.66, 0.75, 1.00]
WINDOWS = {"full": 1640995200, "hl_era": 1683849600}   # 2022-01-01 / 2023-05-12

_OrigPosition = core.Position


def load(path):
    out = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            out.append(Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                           high=float(r["high"]), low=float(r["low"]),
                           close=float(r["close"]), volume=float(r["volume"])))
    return out


def with_pullback_fee(fee_bps):
    """Position factory that injects fee_bps ONLY where none was passed."""
    def _P(*a, **kw):
        kw.setdefault("fee_bps", fee_bps)
        return _OrigPosition(*a, **kw)
    return _P


def run(bars, fee_bps, start_ts):
    core.Position = with_pullback_fee(fee_bps)
    try:
        res = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE,
                         start_ts=start_ts, cash_apy=0.0)
    finally:
        core.Position = _OrigPosition          # never leak the patch
    out = {}
    for name in ("S1", "S2", "S3", "S5" if "S5" in res.books else "S3"):
        if name in res.books:
            out[name] = book_stats(res.books[name])
    for name, b in res.books.items():
        out[name] = book_stats(b)
        out[name]["mtm_max_dd_pct"] = round(100 * b.mtm_max_dd, 4)
        out[name]["_trades"] = [
            {"exit_ts": t.exit_ts, "pnl_pct": t.pnl_pct, "pnl_usd": t.pnl_usd,
             "reason": t.exit_reason, "notional": t.notional,
             "equity_before": t.equity_before, "equity_after": t.equity_after}
            for t in b.trades]
    return out


def main():
    bars = load(BARS_CSV)
    rows = []
    # 2 declared baseline reruns: prove the harness reproduces the committed
    # numbers BEFORE anything is changed.
    for wname, start in WINDOWS.items():
        base = run(bars, 6.0, start)
        rows.append({"arm": "baseline_6.0", "window": wname,
                     "fee_bps": 6.0, "frac": None, "stats": base})
        print(f"[baseline] {wname:7s} fee 6.00  S3 ret "
              f"{base['S3']['total_return_pct']:>7.1f}%  "
              f"CAGR {base['S3']['cagr_pct']}  n={base['S3']['trades']}")
    # 12 declared grid cells
    for wname, start in WINDOWS.items():
        for f in FRACS:
            fee = f * HL_TAKER + HL_TAKER      # entry share crossed + taker exit
            st = run(bars, fee, start)
            rows.append({"arm": f"frac_{f:.2f}", "window": wname,
                         "fee_bps": round(fee, 4), "frac": f, "stats": st})
            print(f"[grid]     {wname:7s} frac {f:.2f} fee {fee:5.2f}  "
                  f"S3 ret {st['S3']['total_return_pct']:>7.1f}%  "
                  f"CAGR {st['S3']['cagr_pct']}  "
                  f"MTM DD {st['S3']['mtm_max_dd_pct']:.2f}%")
    with open(os.path.join(OUT, "grid.json"), "w") as fh:
        json.dump(rows, fh)
    print(f"\nwrote {os.path.join(OUT, 'grid.json')}  ({len(rows)} arms)")


if __name__ == "__main__":
    main()
