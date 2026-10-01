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
    V0_EXPECTED,
    V0_TOL,
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
    # V5 is the pre-registered single-signal variant (rel-strength fires gated
    # on XBI>50dma). It did NOT survive its campaign (Sharpe 0.34 vs V0's 0.42);
    # it is shown because it is the only single-signal book the variants run
    # computed on full daily curves, not because it is better.
    "V5": {"label": "Rel-strength only, gated", "sub": "1% risk/call, <=10 open, XBI>50dma gate",
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
    {"label": "combined book @ 0.5%", "risk_frac": 0.005, "end_value": 156_601,
     "cagr": 0.043, "max_dd": 0.401, "sharpe": 0.42, "sortino": 0.62, "calmar": 0.11},
    {"label": "combined book @ 1%", "risk_frac": 0.01, "end_value": 208_764,
     "cagr": 0.072, "max_dd": 0.655, "sharpe": 0.42, "sortino": 0.61, "calmar": 0.11},
    {"label": "combined book @ 2%", "risk_frac": 0.02, "end_value": 233_656,
     "cagr": 0.083, "max_dd": 0.899, "sharpe": 0.40, "sortino": 0.59, "calmar": 0.09},
    # The one single-signal book in the addendum that beats both V0 and XBI on
    # Sharpe. Doc-frozen like the rows above; the ungated rel-strength book
    # was never a pre-registered variant, so no full-daily-curve stats exist.
    {"label": "rel-strength only, ungated @ 1%", "risk_frac": 0.01, "end_value": 246_236,
     "cagr": 0.089, "max_dd": 0.512, "sharpe": 0.48, "sortino": 0.70, "calmar": 0.17},
]

CAVEATS = [
    "This is the MECHANICAL SHADOW of the engine, not the engine: the live "
    "composite>=55 gate, confidence sizing and the auto-trigger set "
    "(sentiment ramp / revision clusters / options+social) have no history and "
    "were not replayed. Every replayable fire became a fixed-size call, and "
    "the book held at most 10 at once - 3,872 of 5,008 fires were skipped at "
    "that cap, and the price-only pullback row is excluded to avoid "
    "double-counting its own superset flag.",
    "Survivorship: the replay trades TODAY'S universe. Names that died or "
    "delisted between 2016 and now are absent, which flatters every absolute "
    "number. XBI and SPY carry no such tailwind, so the comparison is unfair "
    "in the engine's favour.",
    "The catalyst calendar is point-in-time but not perfectly so: it uses the "
    "sponsor's SUBMIT dates, which precede public posting by a median of 2 "
    "days (p90 5, max 92). Rebuilding on true post dates moved the "
    "catalyst flags' excess UP, so the lead hurt rather than helped, and no "
    "verdict changed - measured, not assumed.",
    "A catalyst's primary-completion date is an ESTIMATE of when a trial "
    "finishes, not a readout date; data often lands months either side. The "
    "catalyst windows approximate event proximity, nothing more.",
    "Sizing is fixed-fraction (risk f% of the previous close's equity per "
    "call), daily mark-to-market on adjusted closes forward-filled on the XBI "
    "calendar, tiered slippage (A=10 / B=40 / C=100 bps per side) inside the "
    "realized R, rf = 0 for Sharpe and Sortino. 'Book value at end' is the "
    "running book, not re-based per window.",
    "The replay ends 2026-08-19. The 2y and 5y windows are anchored to THAT "
    "date, not today, and the 10y window is the whole 10.6-year replay. What "
    "the engine has done since lives in the live paper book above - the only "
    "honest measure of the full system.",
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


HINT = ("Run `python -m scripts.backtest_summary` with backend/data/"
        "backtest_bars.json and spy_bars_raw.json present (refetch them with "
        "`python -m scripts.backtest_calls_10y --refresh`), then commit the JSON.")


def v0_mismatch(full: dict) -> str | None:
    """The same machinery gate scripts/backtest_variants_10y.py applies on
    every run, applied to a RECOMPUTED book before any of its numbers are
    allowed onto the page.

    A bar cache fetched later, from another lane or with a different
    adjustment basis, would otherwise put trailing-window Sharpe and %-DD on
    the page that silently disagree with the copied full-period row beside
    them. Either the cache reproduces the documented book, or nothing from
    it is shown."""
    got = {"end": full["end_value"], "cagr": full["cagr"],
           "max_dd": full["max_dd"], "sharpe": full["sharpe"]}
    bad = [f"{k} {got[k]:.4g} vs documented {exp}"
           for k, exp in V0_EXPECTED.items()
           if abs(got[k] - exp) > max(0.01 * abs(exp), V0_TOL[k])]
    return "; ".join(bad) or None


def trailing_daily(taken: list[dict]) -> dict:
    """2y/5y/10y dollar windows on the FULL daily curve. Needs the bar cache.

    Absent cache -> status=unavailable with the path named, so the gap is
    visible on the page instead of looking like a number that was never
    asked for. Cache present but failing the V0 gate -> the same, with the
    mismatch named: a wrong number is worse than a gap."""
    missing = [p for p in (BARS_CACHE, SPY_RAW) if not p.exists()]
    if missing:
        return {"status": "unavailable",
                "reason": ("needs the daily price cache the replay was built "
                           "from, which this build did not have"),
                "detail": "missing: " + ", ".join(str(p.relative_to(BACKEND)) for p in missing),
                "hint": HINT, "windows": None}
    mkt = load_market()
    curve = run_call_book(taken, mkt)
    full = seg_stats(curve, START, END)
    bad = v0_mismatch(full)
    if bad:
        return {"status": "unavailable",
                "reason": ("the daily price cache present at build time did not "
                           "reproduce the documented book, so nothing computed "
                           "from it is shown"),
                "detail": f"V0 gate failed: {bad}", "hint": HINT, "windows": None}
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
            "v0_gate": {"end_value": full["end_value"], "cagr": full["cagr"],
                        "max_dd": full["max_dd"], "sharpe": full["sharpe"],
                        "passed": True},
            "windows": windows,
            "curve_daily": [[d.isoformat(), round(v, 2)] for d, v in curve]}


def with_full_as_10y(td: dict, windows_daily: dict) -> dict:
    """The 10y window IS the full replay, and the full replay's dollar stats
    exist whether or not the bar cache does. Without this the page claimed
    a gap on the 10y tab that the Full tab had already filled."""
    if td["status"] == "ok" or "full" not in windows_daily:
        return td
    full = windows_daily["full"]
    td = {**td, "status": "partial",
          "windows": {"10y": {**full, "note": ("the 10y window is the full replay; "
                                               "copied from the full-period row")}}}
    return td


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

    windows_daily = _window_stats_from_variants(var)
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
        "windows_daily": windows_daily,
        "trailing_r": trailing_r,
        "trailing_daily": with_full_as_10y(trailing_daily(taken), windows_daily),
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
          + ("" if td == "ok" else f" - {out['trailing_daily']['reason']} "
                                   f"({out['trailing_daily'].get('detail', '')})"))
    if td == "ok":
        for k, w in out["trailing_daily"]["windows"].items():
            v = w["books"]["V0"]
            print(f"    {k}: CAGR {v['cagr']:+.2%} maxDD {v['max_dd']:.1%} "
                  f"Sharpe {v['sharpe']:.2f}  (XBI {w['books']['XBI']['sharpe']:.2f})")


if __name__ == "__main__":
    main()
