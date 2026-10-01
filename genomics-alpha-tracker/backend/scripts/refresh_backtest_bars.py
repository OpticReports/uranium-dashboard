"""Rebuild the 10-year replay's two gitignored price caches on a
DIVIDEND-ADJUSTED basis, so scripts/backtest_summary.py can recompute the
dollar book and pass its V0 gate.

    python -m scripts.refresh_backtest_bars        # needs FMP_API_KEY

WHY A DEDICATED SCRIPT. The frozen call rows (entry, stop, risk) were
graded on dividend-adjusted bars. The app's FMP provider fetches
/historical-price-eod/full - UNADJUSTED - and labels adj_close = close, so
a cache built through it mis-marks every open position in a dividend payer
by the cumulative dividends since that bar: LLY alone moved the recomputed
Sharpe from 0.4156 to 0.409 and failed the gate. Nothing in the repo wrote
data/spy_bars_raw.json at all. This script uses the round-7 FMP lane
(scripts/lib/fmp_prices.fmp_bars: /stable/historical-price-eod/
dividend-adjusted, adjOpen/adjHigh/adjLow/adjClose) for every symbol and
writes both files in exactly the shapes load_market() and load_spy_curve()
read.

WHAT IT DOES NOT PROMISE. FMP's adjustment and Yahoo's can differ in
rounding and methodology. The V0 gate in backtest_summary.py decides
whether the result reproduces the documented book; this script only makes
the attempt possible on the right basis.

BASIS NORMALIZATION, AND WHY IT IS NOT A FUDGE. With dividends handled,
32 of 33 symbols land on the frozen basis to four decimals. ATAI does
not: this lane's series is a CONSTANT 0.0728x of the frozen entries on
every one of its calls - the signature of an adjustment convention (how a
reverse split or ratio change was applied), not of different data. A
constant factor leaves every daily return identical; it only changes the
units the marks are in, and the frozen entry/stop/risk are in the other
units. So: for each symbol, if the ratio of this lane's open to the frozen
entry is constant across its calls (max/min within 0.5%) and not 1, the
series is divided by that constant and the factor is written to
data/backtest_bars_basis.json for the summary to display. A ratio that is
NOT constant is left alone, so the V0 gate sees it and refuses. Nothing
here reads an outcome - entry prices are inputs - and the gate still
decides whether the result reproduces the documented book.

Caches go under data/bars_cache_fmp_adj/ (gitignored), NOT data/r7_cache/,
which is the frozen round-7 record.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.lib.fmp_prices import fmp_bars  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "data"
CALLS_RESULTS = DATA / "backtest_calls_10y_results.json"
BARS_CACHE = DATA / "backtest_bars.json"
BASIS_SIDECAR = DATA / "backtest_bars_basis.json"
SPY_RAW = DATA / "spy_bars_raw.json"
LANE_CACHE = DATA / "bars_cache_fmp_adj"
START = "2015-09-01"          # ATR warm-up before the replay's 2016-01-01 start
MIN_ENTRIES = 5               # fewer frozen entries than this: no inference
CONSTANT_TOL = 1.005          # max/min ratio inside this = "a constant factor"
UNITY_TOL = 0.005             # |factor - 1| inside this = already on the frozen basis


def frozen_entries() -> dict[str, list[tuple[str, float]]]:
    """Every replayed call's (entry_date, entry price), per symbol - the
    frozen basis the lane is compared against. Inputs, not outcomes."""
    res = json.loads(CALLS_RESULTS.read_text())
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for rows in res["call_rows"].values():
        for t in rows:
            out[t["symbol"]].append((t["entry_date"], float(t["entry"])))
    return out


def basis_factor(by_date: dict[str, dict], entries: list[tuple[str, float]]) -> dict | None:
    """The constant factor between this lane and the frozen basis, or None.

    None means either 'already on the frozen basis' or 'not a constant' -
    and the second case is deliberately NOT repaired: a drifting ratio is
    different data, and the V0 gate must be allowed to see it."""
    ratios = [by_date[d]["open"] / e for d, e in entries
              if d in by_date and by_date[d].get("open") and e]
    if len(ratios) < MIN_ENTRIES:
        return None
    med = statistics.median(ratios)
    if max(ratios) / min(ratios) > CONSTANT_TOL or abs(med - 1.0) <= UNITY_TOL:
        return None
    return {"factor": round(med, 6), "n": len(ratios),
            "spread": round(max(ratios) / min(ratios) - 1.0, 6)}


def normalize_basis(bars: dict[str, list[dict]]) -> dict[str, dict]:
    entries = frozen_entries()
    applied: dict[str, dict] = {}
    for sym, rows in bars.items():
        f = basis_factor({r["date"]: r for r in rows}, entries.get(sym, []))
        if not f:
            continue
        k = f["factor"]
        for r in rows:
            for key in ("open", "high", "low", "close", "adj_close"):
                if r.get(key) is not None:
                    r[key] = r[key] / k
        applied[sym] = {**f, "note": ("series divided by a constant factor to match the "
                                      "frozen entry basis; returns unchanged")}
        print(f"  basis: {sym} normalized by {k:.4f} over {f['n']} entries "
              f"(spread {f['spread']:.2%})")
    return applied


def to_cache_rows(rows: list[dict]) -> list[dict]:
    """FMP adjusted rows -> the provider record shape the replay reads.

    close == adj_close by construction here: the OHLC are already on the
    adjusted basis, so to_adjusted_barlikes's adj/close factor is 1 and the
    bars are used as delivered."""
    out = []
    for r in rows:
        c = r.get("adjClose")
        if c in (None, 0):
            continue
        out.append({"date": r["date"], "open": r.get("adjOpen"), "high": r.get("adjHigh"),
                    "low": r.get("adjLow"), "close": c, "adj_close": c,
                    "volume": r.get("volume")})
    return out


def universe() -> list[str]:
    res = json.loads(CALLS_RESULTS.read_text())
    return sorted(res["tiers"]) + ["XBI"]


def main() -> None:
    bars: dict[str, list[dict]] = {}
    for sym in universe():
        rows = to_cache_rows(fmp_bars(sym, start=START, cache_dir=LANE_CACHE))
        bars[sym] = rows
        print(f"  {sym}: {len(rows)} bars {rows[0]['date']}..{rows[-1]['date']}")
    applied = normalize_basis(bars)
    BARS_CACHE.write_text(json.dumps(bars))
    BASIS_SIDECAR.write_text(json.dumps({"lane": "fmp dividend-adjusted",
                                         "normalized": applied}, indent=1))

    spy = fmp_bars("SPY", start=START, cache_dir=LANE_CACHE)
    SPY_RAW.write_text(json.dumps({"data": [{"t": r["date"], "a": r["adjClose"]}
                                            for r in spy if r.get("adjClose")]}))
    print(f"wrote {BARS_CACHE.relative_to(BACKEND)} ({len(bars)} symbols) and "
          f"{SPY_RAW.relative_to(BACKEND)} ({len(spy)} rows), dividend-adjusted basis")
    print("next: python -m scripts.backtest_summary   (the V0 gate decides)")


if __name__ == "__main__":
    main()
