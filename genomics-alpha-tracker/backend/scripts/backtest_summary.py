"""Build the Calls Log backtest panel's data: app/calls/backtest_summary.json.

WHAT THIS IS. A compact, display-ready summary of the 10-year calls-engine
replay (docs/BACKTEST_CALLS_10Y.md) and its pre-registered dollar-book
protocol (docs/BACKTEST_VARIANTS_10Y.md), so the dashboard can answer
"what would the mechanical engine have done, and how deep was the hole"
without re-running anything at request time.

WHAT THIS IS NOT. It is not a new backtest. Every dollar statistic here is
COPIED from backend/data/backtest_variants_10y_results.json, where it was
computed on the FULL daily equity curves by scripts/backtest_variants_10y.py
(whose V0 machinery gate reproduces the documented addendum within +/-1%).
Nothing is recomputed from the stored, downsampled curves - their protocol
note says plainly: "do not recompute maxDD from the stored points".

THREE FRAMINGS, each labelled by its measurement basis on the page:
  windows_daily   full period + the three pre-registered sub-periods.
                  Dollars, daily mark-to-market, from full daily curves.
  trailing_r      2y / 5y / 10y windows ending at the replay's last bar.
                  R-units on the equal-risk sequential book, REALIZATION
                  basis (a call counts in the window it EXITS in). Computed
                  here from the complete per-call record, which is lossless.
  trailing_daily  the same 2y / 5y / 10y windows in DOLLARS with Sharpe -
                  needs the daily bar cache (backend/data/backtest_bars.json,
                  gitignored). Populated only when that file is present;
                  otherwise written as status=unavailable WITH the reason,
                  never silently dropped. The page shows the gap as a gap.

WHERE THE OUTPUT LIVES, AND WHY NOT data/. In production the Render disk is
mounted at /app/data and SHADOWS the image's data/ directory - a file
committed under backend/data/ does not exist at runtime there. The summary is
written into the app package instead, which the Dockerfile copies wholesale.

Usage:  python -m scripts.backtest_summary
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_variants_10y import (  # noqa: E402
    BARS_CACHE,
    CAP,
    END,
    LIVE_SET_FLAGS,
    SPY_RAW,
    START,
    START_EQUITY,
    buyhold_curve,
    load_market,
    load_spy_curve,
    run_call_book,
    seg_stats,
    select_capped,
)

BACKEND = Path(__file__).resolve().parent.parent
CALLS_RESULTS = BACKEND / "data" / "backtest_calls_10y_results.json"
VARIANTS_RESULTS = BACKEND / "data" / "backtest_variants_10y_results.json"
OUT = BACKEND / "app" / "calls" / "backtest_summary.json"

SCHEMA = 1
TRAILING_YEARS = (2, 5, 10)
# Books shown on the page. V0 is the engine; V5 the strongest single-signal
# variant from the pre-registered campaign; XBI and SPY are what a passive
# dollar would have done over the same calendar.
BOOKS = {
    "V0": {"label": "Combined replayable book", "sub": "1% risk/call, <=10 open",
           "kind": "engine"},
    "V5": {"label": "Rel-strength only", "sub": "1% risk/call, <=10 open, XBI>50dma gate",
           "kind": "variant"},
    "XBI": {"label": "XBI buy & hold", "sub": "sector benchmark", "kind": "benchmark"},
    "SPY": {"label": "SPY buy & hold", "sub": "market benchmark", "kind": "benchmark"},
}
STAT_KEYS = ("end_value", "cagr", "max_dd", "sharpe", "sortino", "calmar")

# The dollar-book addendum's sizing sensitivity (BACKTEST_CALLS_10Y.md). These
# three rows are DOC-FROZEN: only the 1% row is re-reproduced by the variants
# machinery gate (to $4). They answer one question - what risk/call buys -
# and the answer is almost entirely drawdown.
SIZING_SENSITIVITY = [
    {"risk_frac": 0.005, "end_value": 156_601, "cagr": 0.043, "max_dd": 0.401,
     "sharpe": 0.42, "sortino": 0.62, "calmar": 0.11},
    {"risk_frac": 0.01, "end_value": 208_764, "cagr": 0.072, "max_dd": 0.655,
     "sharpe": 0.42, "sortino": 0.61, "calmar": 0.11},
    {"risk_frac": 0.02, "end_value": 233_656, "cagr": 0.083, "max_dd": 0.899,
     "sharpe": 0.40, "sortino": 0.59, "calmar": 0.09},
]

CAVEATS = [
    "This is the MECHANICAL SHADOW of the engine, not the engine: the live "
    "composite>=55 gate, confidence sizing and the auto-trigger set "
    "(sentiment ramp / revision clusters / options+social) have no history and "
    "were not replayed. Every replayable fire became a fixed-size call.",
    "Survivorship: the replay trades TODAY'S universe. Names that died or "
    "delisted between 2016 and now are absent, which flatters every absolute "
    "number. XBI and SPY carry no such tailwind, so the comparison is unfair "
    "in the engine's favour.",
    "Sizing is fixed-fraction (risk f% of the previous close's equity per "
    "call), daily mark-to-market on adjusted closes forward-filled on the XBI "
    "calendar, tiered slippage (A=10 / B=40 / C=100 bps per side) inside the "
    "realized R, rf = 0 for Sharpe and Sortino.",
    "The replay ends 2026-08-19. The 2y and 5y windows are anchored to THAT "
    "date, not today. What the engine has done since lives in the live paper "
    "book above - the only honest measure of the full system.",
    "Read against the benchmark row: at mechanical sizing the replayable "
    "engine ~= sector beta over the decade, with a worse drawdown at 1% risk. "
    "Raising risk per call bought CAGR almost entirely with drawdown.",
]


def _trailing_start(end: date, years: int) -> date:
    """Calendar-year subtraction, with one rule: if the window would begin
    inside the replay's FIRST year, it begins at the replay start instead.

    So '2y' and '5y' are exact, and '10y' is the whole 10.6-year replay
    rather than a window that silently drops the first seven months of 2016
    (51 calls, -6.8R) while wearing a round label. The page prints the exact
    span next to every window, so the label never has to carry the truth
    alone. First draft used max(s, START), which did the silent-drop thing;
    the gate test caught it before it reached the page."""
    try:
        s = date(end.year - years, end.month, end.day)
    except ValueError:  # Feb 29
        s = date(end.year - years, end.month, 28)
    first_year_ends = date(START.year + 1, START.month, START.day)
    return START if s < first_year_ends else s


def trailing_r_stats(rows: list[dict], start: date, end: date) -> dict:
    """Equal-risk sequential book over [start, end], REALIZATION basis.

    A call is in the window iff it EXITED inside it: that is how a trade-close
    P&L record is cut, and it is the only cut that needs no daily marks. The
    path starts at 0 on the window's first exit; drawdown is measured from a
    peak that starts at 0 (an opening losing streak is a drawdown), the same
    convention as max_drawdown_r in scripts/backtest_calls_10y.py."""
    inwin = sorted(
        (t for t in rows if start <= date.fromisoformat(t["exit_date"]) <= end),
        key=lambda t: (t["exit_date"], t["symbol"], t.get("flag", "")),
    )
    cum, peak, dd = 0.0, 0.0, 0.0
    curve: list[list] = []
    wins = 0
    for t in inwin:
        cum += t["r_net"]
        wins += 1 if t["r_net"] > 0 else 0
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        curve.append([t["exit_date"], round(cum, 4)])
    n = len(inwin)
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "years": round((end - start).days / 365.25, 2),
        "n_calls": n,
        "total_r": round(cum, 4),
        "max_dd_r": round(dd, 4),
        "hit_rate": round(wins / n, 4) if n else None,
        "avg_r": round(cum / n, 4) if n else None,
        "curve": _thin(curve, 300),
    }


def _thin(curve: list[list], target: int) -> list[list]:
    if len(curve) <= target:
        return curve
    step = -(-len(curve) // target)
    pts = curve[::step]
    if pts[-1] != curve[-1]:
        pts.append(curve[-1])
    return pts


def _window_stats_from_variants(var: dict) -> dict:
    """Copy, never recompute: the stats in the variants file came from the
    full daily curves. Each window carries its own start/end so the page can
    state the exact span rather than a label."""
    out = {}
    for name in ("full", *var["sub_periods"].keys()):
        books = {}
        span = None
        for key in BOOKS:
            s = var["variants"].get(key, {}).get("stats", {}).get(name)
            if not s:
                continue
            books[key] = {k: s[k] for k in STAT_KEYS}
            span = span or (s["start"], s["end"])
        if books:
            out[name] = {"start": span[0], "end": span[1],
                         "years": round((date.fromisoformat(span[1])
                                         - date.fromisoformat(span[0])).days / 365.25, 2),
                         "books": books}
    return out


def _display_curves(var: dict) -> dict:
    """The variants file's ~400-point curves, merged by date. Display only -
    the drawdown the page draws from these is at display resolution and the
    page says so; the drawdown NUMBERS come from the full daily curves."""
    by_date: dict[str, dict] = {}
    for key in BOOKS:
        for d, v in var["variants"].get(key, {}).get("curve", []):
            by_date.setdefault(d, {"date": d})[key] = v
    rows = [by_date[d] for d in sorted(by_date)]
    return {"resolution": "display (~400 points, from the variants results); "
                          "stats were computed on the full daily curves",
            "start_equity": START_EQUITY, "rows": rows}


def trailing_daily(taken: list[dict]) -> dict:
    """2y/5y/10y dollar windows on the FULL daily curve. Needs the bar cache.

    Absent cache -> status=unavailable with the path named, so the gap is
    visible on the page instead of looking like a number that was never
    asked for."""
    missing = [p for p in (BARS_CACHE, SPY_RAW) if not p.exists()]
    if missing:
        return {"status": "unavailable",
                "reason": ("daily bar cache not present in this checkout: "
                           + ", ".join(str(p.relative_to(BACKEND)) for p in missing)
                           + ". Run `python -m scripts.backtest_summary` where "
                             "scripts/backtest_calls_10y.py last ran."),
                "windows": None}
    mkt = load_market()
    curve = run_call_book(taken, mkt)
    bench = {"XBI": buyhold_curve(mkt["px"]["XBI"], mkt["calendar"]),
             "SPY": load_spy_curve(mkt["calendar"])}
    windows = {}
    for yrs in TRAILING_YEARS:
        lo = _trailing_start(END, yrs)
        books = {"V0": seg_stats(curve, lo, END)}
        for k, c in bench.items():
            books[k] = seg_stats(c, lo, END)
        books = {k: {kk: v[kk] for kk in STAT_KEYS} for k, v in books.items() if v}
        windows[f"{yrs}y"] = {"start": lo.isoformat(), "end": END.isoformat(),
                              "years": round((END - lo).days / 365.25, 2),
                              "books": books}
    return {"status": "ok", "basis": "dollars, daily MTM, full daily curve",
            "windows": windows,
            "curve_daily": [[d.isoformat(), round(v, 2)] for d, v in curve]}


def build() -> dict:
    res = json.loads(CALLS_RESULTS.read_text())
    var = json.loads(VARIANTS_RESULTS.read_text())

    live_rows = [t for f in LIVE_SET_FLAGS for t in res["call_rows"][f]]
    taken, skipped = select_capped(live_rows, CAP)
    # The same drift gate the variants script applies: if the capped
    # selection no longer matches the replay's own book, nothing below is
    # about the documented book.
    n_doc = res["combined_book"]["summary"]["n"]
    if len(taken) != n_doc:
        raise SystemExit(f"combined-book selection drifted: {len(taken)} taken vs "
                         f"{n_doc} in the replay results")

    end = date.fromisoformat(res["period"][1])
    trailing_r = {
        "basis": ("R-units on the equal-risk sequential book (1R per call, "
                  "<=10 open). REALIZATION basis: a call counts in the window "
                  "it exited in. No daily marks, so no Sharpe here."),
        "windows": {f"{y}y": trailing_r_stats(taken, _trailing_start(end, y), end)
                    for y in TRAILING_YEARS},
    }

    return {
        "schema": SCHEMA,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "calls_results": {"path": "backend/data/backtest_calls_10y_results.json",
                              "generated": res["generated"]},
            "variants_results": {"path": "backend/data/backtest_variants_10y_results.json",
                                 "generated": var["generated"]},
            "reports": ["docs/BACKTEST_CALLS_10Y.md", "docs/BACKTEST_VARIANTS_10Y.md"],
        },
        "period": {"start": res["period"][0], "end": res["period"][1],
                   "years": round((end - date.fromisoformat(res["period"][0])).days / 365.25, 2),
                   "n_names": res["n_names"]},
        "protocol": {**var["protocol"], "cap_open_calls": CAP,
                     "slippage_bps_per_side": {"A": 10, "B": 40, "C": 100},
                     "machinery_gate": ("V0 reproduces the documented dollar-book "
                                        "addendum within +/-1% (asserted on every run "
                                        "of scripts/backtest_variants_10y.py)")},
        "books": BOOKS,
        "combined_book": {"n_calls": len(taken), "skipped_at_cap": skipped,
                          "hit_rate": res["combined_book"]["summary"]["hit_rate"],
                          "avg_r_net": res["combined_book"]["summary"]["avg_r"],
                          "total_r": res["combined_book"]["summary"]["total_r"],
                          "max_dd_r": res["combined_book"]["summary"]["max_dd_r"]},
        "windows_daily": _window_stats_from_variants(var),
        "trailing_r": trailing_r,
        "trailing_daily": trailing_daily(taken),
        "curves": _display_curves(var),
        "sizing_sensitivity": {"source": "docs/BACKTEST_CALLS_10Y.md dollar-book addendum "
                                         "(doc-frozen; the 1% row is the gate-reproduced one)",
                               "rows": SIZING_SENSITIVITY},
        "caveats": CAVEATS,
    }


def main() -> None:
    out = build()
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    v0 = out["windows_daily"]["full"]["books"]["V0"]
    td = out["trailing_daily"]["status"]
    print(f"wrote {OUT.relative_to(BACKEND)}")
    print(f"  full period V0: end ${v0['end_value']:,.0f} CAGR {v0['cagr']:+.2%} "
          f"maxDD {v0['max_dd']:.1%} Sharpe {v0['sharpe']:.2f}")
    for k, w in out["trailing_r"]["windows"].items():
        print(f"  trailing {k} (R, realization): n={w['n_calls']} total {w['total_r']:+.1f}R "
              f"maxDD {w['max_dd_r']:.1f}R hit {w['hit_rate']:.0%}")
    print(f"  trailing dollar windows: {td}"
          + ("" if td == "ok" else f" - {out['trailing_daily']['reason']}"))


if __name__ == "__main__":
    main()
