"""Rebuild R2-A's daily book from the ROUND-2 pipeline, recording the daily
INVESTED notional alongside equity.

Why this exists: the round-4 counter-agent's finding M1. The round-4 harness
believed R2-A's idle cash was observable only on days whose return was exactly
zero (424/1432 = 29.6% of the real window) because the frozen sleeve is a
dollar CURVE. That is false about this repo — `backtest_variants_r2.py`'s
`run_call_book_yield` already computes `equity - invested` every day, so the
idle CAPITAL fraction is recoverable exactly. It averages 63.3% of the sleeve
in the real window, roughly twice what the harness was crediting.

This script re-runs the same selection and the same book, adds the invested
column, and asserts the rebuilt equity matches BOTH `run_call_book` and the
frozen `data/r2a_daily.json` curve to the cent on every day. It writes
`data/r2a_exposure.json`: [[date, equity, invested, open_positions], ...].

Usage:  cd genomics-alpha-tracker/backend && python -m scripts.build_r2a_exposure
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from scripts.backtest_variants_10y import (  # noqa: E402
    CALLS_RESULTS,
    CAP,
    LIVE_SET_FLAGS,
    RISK_FRAC,
    START_EQUITY,
    load_market,
    run_call_book,
    select_capped,
)
from scripts.backtest_variants_r2 import build_trailing_rows  # noqa: E402

DATA = BACKEND / "data"
FROZEN = DATA / "r2a_daily.json"
OUT = DATA / "r2a_exposure.json"
REAL_START, REAL_END = "2020-12-03", "2026-08-19"


def run_call_book_exposure(taken: list[dict], mkt: dict) -> list[list]:
    """`run_call_book` with the invested notional recorded.

    Byte-for-byte the round-2 engine's arithmetic in the same floating-point
    order (`run_call_book_yield` at cash_yield=None, whose equivalence to
    `run_call_book` that script already asserts); the only addition is that
    the `invested` accumulator it computes internally is kept.
    """
    calendar, px = mkt["calendar"], mkt["px"]
    by_entry: dict[str, list[dict]] = {}
    for t in taken:
        by_entry.setdefault(t["entry_date"], []).append(t)
    cash = START_EQUITY
    open_pos: list[dict] = []
    rows: list[list] = []
    prev_equity = START_EQUITY
    for d in calendar:
        ds = d.isoformat()
        still = []
        for p in open_pos:                       # 1. exits due today
            if p["row"]["exit_date"] <= ds:
                cash += p["rd"] * p["row"]["r_net"]
            else:
                still.append(p)
        open_pos = still
        for t in by_entry.get(ds, []):           # 2. entries, sized on prior close
            rd = RISK_FRAC * prev_equity
            if t["exit_date"] <= ds:
                cash += rd * t["r_net"]
            else:
                open_pos.append({"row": t, "rd": rd})
        mtm = invested = 0.0                     # 3. mark to market
        for p in open_pos:
            t = p["row"]
            c = px[t["symbol"]][d]
            mtm += ((c - t["entry"]) / t["risk"]) * p["rd"]
            invested += (p["rd"] / t["risk"]) * c
        equity = cash + mtm
        rows.append([ds, equity, invested, len(open_pos)])
        prev_equity = equity
    return rows


def main() -> None:
    res = json.loads(CALLS_RESULTS.read_text())
    mkt = load_market()
    live_rows = [t for f in LIVE_SET_FLAGS for t in res["call_rows"][f]]
    up200 = mkt["xbi_above_prior"][200]
    trail_rows, _ = build_trailing_rows(live_rows, mkt, res["tiers"])
    taken, skipped = select_capped(
        [t for t in trail_rows
         if up200.get(date.fromisoformat(t["entry_date"]), False)], CAP)
    print(f"R2-A rebuilt: {len(taken)} taken, {skipped} skipped at the {CAP} cap")

    rows = run_call_book_exposure(taken, mkt)
    ref = run_call_book(taken, mkt)
    assert len(rows) == len(ref), "calendar length drift vs run_call_book"
    drift = max(abs(r[1] - v) for r, (_d, v) in zip(rows, ref, strict=True))
    assert drift == 0.0, f"equity diverged from run_call_book by {drift}"

    frozen = {d: v for d, v in json.loads(FROZEN.read_text())}
    assert len(frozen) == len(rows), "frozen curve length != rebuilt length"
    gap = max(abs(r[1] - frozen[r[0]]) for r in rows)
    assert gap < 1e-6, f"rebuilt curve differs from the FROZEN curve by {gap}"
    print(f"Frozen-curve gate PASSED: all {len(rows)} days match to {gap:.1e}")

    idle = [(e - i) / e for d, e, i, _n in rows if REAL_START <= d <= REAL_END]
    print(f"Real-window idle CAPITAL: mean {statistics.fmean(idle):.1%}, "
          f"median {statistics.median(idle):.1%}, fully idle "
          f"{sum(1 for x in idle if x > 0.9999)}/{len(idle)} days")
    OUT.write_text(json.dumps([[d, round(e, 6), round(i, 6), n]
                               for d, e, i, n in rows]))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
