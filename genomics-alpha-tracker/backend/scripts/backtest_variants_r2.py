"""ROUND 2 of the pre-registered variant campaign
(docs/VARIANTS_PREREGISTRATION_R2.md — the contract; registered BEFORE any
round-2 variant was run).

Reuses the round-1 engine (scripts/backtest_variants_10y.py) — its functions
are imported where the mechanics are unchanged and minimally copied where a
registered delta requires a parameter the round-1 function hard-codes; NO
convention is forked. Baselines (V0 and the RESTATED V2) are read from
backend/data/backtest_variants_10y_results.json, never recomputed by hand;
machinery checks reproduce V2 and V6b against those stored stats before any
round-2 variant is graded.

Judgment protocol (fixed by the round-2 pre-registration):
  $100k book, prior-close gates everywhere, daily MTM, rf = 0 except where a
  variant IS the cash-yield fix (R2-D). SURVIVES = Sharpe AND Calmar beat
  BOTH baselines (V0 and restated V2) over the full period AND in >=2 of 3
  sub-periods (both baselines beaten in the same sub-period). R2-D is a
  realism restatement of round-1 survivors, not a new strategy: SURVIVES n/a.

Usage:  python -m scripts.backtest_variants_r2
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calls.rules import BarLike  # noqa: E402
from scripts.backtest_calls import (  # noqa: E402
    SLIPPAGE_BPS_BY_TIER,
    to_adjusted_barlikes,
)
from scripts.backtest_signals import atr_series  # noqa: E402
from scripts.backtest_variants_10y import (  # noqa: E402
    BARS_CACHE,
    CALLS_RESULTS,
    CAP,
    END,
    LIVE_SET_FLAGS,
    RESULTS as R1_RESULTS,
    RISK_FRAC,
    START,
    START_EQUITY,
    SUB_PERIODS,
    TRADING_DAYS,
    V6_LOOKBACK_BARS,
    V6_SLIPPAGE_PER_SIDE,
    V10_TIME_STOP_DAYS,
    V10_TRAIL_ATR_MULT,
    all_stats,
    downsample,
    grade_trailing,
    load_market,
    run_call_book,
    seg_stats,
    select_capped,
)

DATA = Path(__file__).resolve().parent.parent / "data"
BIL_RAW = DATA / "bil_bars_raw.json"
RESULTS = DATA / "backtest_variants_r2_results.json"
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_VARIANTS_R2.md"

# Round-2 fixed parameters (VARIANTS_PREREGISTRATION_R2.md — not tunable)
R2B_TOP_N = 10
R2C_PIT_FLOOR_DOLLARS = 2_000_000.0   # trailing 60d median dollar volume
BIL_PROXY_ANNUAL = 0.02               # flat proxy where BIL data is missing
BIL_PROXY_DAILY = (1 + BIL_PROXY_ANNUAL) ** (1 / TRADING_DAYS) - 1


# --- R2-A: trailing-ATR re-grade of the COMBINED live-flag fires -------------------
# Minimal copy of round-1's build_v10_rows: identical mechanics (grade_trailing
# is IMPORTED — trail from prior-bar peak close minus 3.0xATR14 through the
# prior bar, open-first gap fills, 90 calendar-day time stop, initial risk =
# the stored build_levels risk, tiered slippage). The only delta: it takes ANY
# call rows (not just rel_strength) and keeps each row's own flag (+"_trail")
# so select_capped's (entry_date, symbol, flag) ordering stays per-flag.

def build_trailing_rows(rows: list[dict], mkt: dict,
                        tiers: dict[str, str]) -> tuple[list[dict], int]:
    bars_by_sym = mkt["bars"]
    atr_cache: dict[str, list[float | None]] = {}
    idx_cache: dict[str, dict[date, int]] = {}
    out: list[dict] = []
    open_at_end = 0
    for t in rows:
        sym = t["symbol"]
        bars = bars_by_sym[sym]
        if sym not in idx_cache:
            idx_cache[sym] = {b.date: i for i, b in enumerate(bars)}
            atr_cache[sym] = atr_series(bars)
        j = idx_cache[sym].get(date.fromisoformat(t["entry_date"]))
        if j is None:
            continue
        entry = t["entry"]                       # next open after fire (stored row)
        risk = t["risk"]                         # INITIAL 3xATR14 risk unit (build_levels)
        expiry = date.fromisoformat(t["entry_date"]) + timedelta(days=V10_TIME_STOP_DAYS)
        g = grade_trailing(bars, atr_cache[sym], j, entry, expiry)
        if g is None:
            open_at_end += 1
            continue
        status, exit_date, exit_px = g
        bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(sym, "C"), 100) / 10_000
        out.append({
            "fire_date": t["fire_date"], "entry_date": t["entry_date"],
            "symbol": sym, "flag": t["flag"] + "_trail",
            "entry": entry, "risk": risk, "exit": exit_px,
            "exit_date": exit_date.isoformat(), "status": status,
            "r": (exit_px - entry) / risk,
            "r_net": (exit_px * (1 - bps) - entry * (1 + bps)) / risk,
            "hold_days": (exit_date - date.fromisoformat(t["entry_date"])).days,
            "regime_up": t.get("regime_up"),
        })
    return out, open_at_end


# --- R2-D: dollar book with idle cash earning BIL's total return --------------------
# Minimal copy of round-1's run_call_book (hedge/vol_target branches dropped —
# unused by V2) plus ONE addition: each day, the PRIOR close's idle cash
# (equity minus open positions' notional MTM value, clamped to [0, equity])
# accrues that day's BIL total return before exits/entries. cash_yield=None
# reduces EXACTLY to run_call_book (asserted in main()).

def run_call_book_yield(taken: list[dict], mkt: dict,
                        cash_yield: dict[date, float] | None) -> list[tuple[date, float]]:
    calendar, px = mkt["calendar"], mkt["px"]
    by_entry: dict[str, list[dict]] = {}
    for t in taken:
        by_entry.setdefault(t["entry_date"], []).append(t)

    cash = START_EQUITY
    open_pos: list[dict] = []
    curve: list[tuple[date, float]] = []
    prev_equity = START_EQUITY
    prev_idle = START_EQUITY  # day 1: the whole book is idle cash

    for d in calendar:
        ds = d.isoformat()
        # 0. idle cash (as of the PRIOR close) earns today's BIL total return
        if cash_yield is not None:
            cash += prev_idle * cash_yield.get(d, 0.0)

        # 1. realize exits due today (r_net includes tiered slippage)
        still = []
        for p in open_pos:
            if p["row"]["exit_date"] <= ds:
                cash += p["rd"] * p["row"]["r_net"]
            else:
                still.append(p)
        open_pos = still

        # 2. open entries (sized on the previous close's equity)
        for t in by_entry.get(ds, []):
            rd = RISK_FRAC * prev_equity
            if t["exit_date"] <= ds:  # same-bar exit: realize immediately
                cash += rd * t["r_net"]
            else:
                open_pos.append({"row": t, "rd": rd})

        # 3. mark to market on adjusted closes
        mtm = 0.0
        invested = 0.0
        for p in open_pos:
            t = p["row"]
            c = px[t["symbol"]][d]
            mtm += ((c - t["entry"]) / t["risk"]) * p["rd"]   # identical fp order to round 1
            invested += (p["rd"] / t["risk"]) * c  # notional MTM value (share-equiv x price)
        equity = cash + mtm
        curve.append((d, equity))
        prev_idle = min(max(equity - invested, 0.0), max(equity, 0.0))
        prev_equity = equity
    return curve


# --- R2-B/C/E + R2-D(V6b): parameterized momentum book ------------------------------
# Minimal copy of round-1's run_v6 with the registered deltas exposed as
# parameters: top_n (R2-B), gate SMA window (R2-E), a point-in-time liquidity
# floor replacing the tier filter (R2-C), and an optional BIL cash yield
# (R2-D). Everything else is byte-for-byte round-1 mechanics: monthly
# first-trading-day rebalance, trailing 60-bar return vs XBI through the
# rebalance close, 7-day bar-staleness exclusion, equal weight, 10 bps/side
# turnover cost, gate on the PRIOR trading day's close vs prior-day SMA.
# top_n=5/gate=50/tier-filter/no-yield reproduces stored V6b (asserted).

def run_momentum_book(mkt: dict, tiers: dict[str, str], universe: list[str], *,
                      top_n: int, gate_window: int, use_pit_floor: bool = False,
                      volumes: dict[str, list[float | None]] | None = None,
                      cash_yield: dict[date, float] | None = None,
                      ) -> tuple[list[tuple[date, float]], int, int]:
    calendar, px, bars = mkt["calendar"], mkt["px"], mkt["bars"]
    idx_by_date = {sym: {b.date: i for i, b in enumerate(bs)}
                   for sym, bs in bars.items()}
    if use_pit_floor:
        eligible = [s for s in universe if s in bars]   # NO tier filter (R2-C)
    else:
        eligible = [s for s in universe if tiers.get(s) in ("A", "B") and s in bars]

    rebal_days = []
    seen = set()
    for d in calendar:
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            rebal_days.append(d)
    rebal_set = set(rebal_days)

    def bar_at(sym: str, d: date) -> int | None:
        bs = bars[sym]
        i = idx_by_date[sym].get(d)
        if i is None:  # no bar today: use the last bar before d
            lo = [k for k, b in enumerate(bs) if b.date <= d]
            if not lo:
                return None
            i = lo[-1]
            if (d - bs[i].date).days > 7:
                return None  # stale — excluded this month
        return i

    def ret60(sym: str, d: date) -> float | None:
        i = bar_at(sym, d)
        if i is None or i < V6_LOOKBACK_BARS:
            return None
        bs = bars[sym]
        c0, c1 = bs[i - V6_LOOKBACK_BARS].close, bs[i].close
        if not c0 or not c1:
            return None
        return c1 / c0 - 1

    def pit_floor_ok(sym: str, d: date) -> bool:
        # trailing 60 bars ending at the PRIOR bar (prior-close convention —
        # the level knowable before the rebalance), adjusted close x volume
        # (the repo's median_addv dollar-volume convention)
        i = bar_at(sym, d)
        if i is None or i < V6_LOOKBACK_BARS:
            return False
        vols = volumes[sym]
        dollars = [b.close * v for b, v in
                   zip(bars[sym][i - V6_LOOKBACK_BARS:i], vols[i - V6_LOOKBACK_BARS:i])
                   if b.close is not None and v]
        return bool(dollars) and statistics.median(dollars) >= R2C_PIT_FLOOR_DOLLARS

    cash = START_EQUITY
    shares: dict[str, float] = {}
    curve: list[tuple[date, float]] = []
    n_rebal = 0
    n_floor_excl = 0
    for d in calendar:
        # idle cash (carried from the prior close) earns today's BIL return
        if cash_yield is not None and cash > 0:
            cash += cash * cash_yield.get(d, 0.0)
        pos_val = {s: sh * px[s][d] for s, sh in shares.items()}
        equity = cash + sum(pos_val.values())
        if d in rebal_set:
            n_rebal += 1
            picks: list[str] = []
            if mkt["xbi_above_prior"][gate_window].get(d, False):
                xbi_r = ret60("XBI", d)
                scored = []
                for s in eligible:
                    r = ret60(s, d)
                    if r is None or xbi_r is None or not px[s][d]:
                        continue
                    if use_pit_floor and not pit_floor_ok(s, d):
                        n_floor_excl += 1
                        continue
                    scored.append((r - xbi_r, s))
                scored.sort(key=lambda x: (-x[0], x[1]))
                picks = [s for _, s in scored[:top_n]]
            target_each = (equity / len(picks)) if picks else 0.0
            turnover = sum(abs((target_each if s in picks else 0.0) - pos_val.get(s, 0.0))
                           for s in set(picks) | set(pos_val))
            cost = V6_SLIPPAGE_PER_SIDE * turnover
            equity -= cost
            target_each = (equity / len(picks)) if picks else 0.0
            shares = {s: target_each / px[s][d] for s in picks}
            cash = equity - target_each * len(picks)
        curve.append((d, equity))
    return curve, n_rebal, n_floor_excl


# --- BIL total-return series ---------------------------------------------------------

def load_bil_yield(calendar: list[date]) -> tuple[dict[date, float], list[date]]:
    """Daily BIL total return (adjusted-close field 'a') mapped onto the XBI
    calendar. A calendar day with no BIL bar earns the flat 2.0%/yr proxy and
    is returned in proxy_days (dated and flagged per the contract). The first
    calendar day accrues nothing (no prior close)."""
    rows = json.loads(BIL_RAW.read_text())["data"]
    by = {date.fromisoformat(r["t"]): r["a"] for r in rows
          if r.get("a") not in (None, 0)}
    y: dict[date, float] = {}
    proxy_days: list[date] = []
    prev_a = None
    for d in calendar:
        a = by.get(d)
        if a is None:
            y[d] = BIL_PROXY_DAILY
            proxy_days.append(d)
            continue
        y[d] = (a / prev_a - 1) if prev_a is not None else 0.0
        prev_a = a
    return y, proxy_days


# --- judgment ------------------------------------------------------------------------

def beats(a: dict, b: dict) -> bool:
    return bool(a and b and a["sharpe"] > b["sharpe"] and a["calmar"] > b["calmar"])


def survives_double(stats: dict, v0: dict, v2: dict) -> bool:
    """The round-2 pre-registered bar: Sharpe AND Calmar beat BOTH baselines
    (V0 and restated V2) over the full period AND in >=2 of 3 sub-periods
    (both baselines beaten within the same sub-period)."""
    if not (beats(stats["full"], v0["full"]) and beats(stats["full"], v2["full"])):
        return False
    wins = sum(1 for name, _, _ in SUB_PERIODS
               if beats(stats[name], v0[name]) and beats(stats[name], v2[name]))
    return wins >= 2


def assert_close(name: str, got: dict, exp: dict, rel: float = 2e-3) -> None:
    for key in ("end_value", "cagr", "max_dd", "sharpe"):
        g, e = got[key], exp[key]
        assert abs(g - e) <= max(rel * abs(e), 1e-4), \
            f"{name} machinery check FAILED: {key} {g} vs stored {e}"


# --- main ----------------------------------------------------------------------------

def main() -> None:  # noqa: PLR0915
    res = json.loads(CALLS_RESULTS.read_text())
    call_rows: dict[str, list[dict]] = res["call_rows"]
    tiers: dict[str, str] = res["tiers"]
    r1 = json.loads(R1_RESULTS.read_text())
    mkt = load_market()
    calendar = mkt["calendar"]
    universe = sorted(tiers)

    live_rows = [t for f in LIVE_SET_FLAGS for t in call_rows[f]]
    up200 = mkt["xbi_above_prior"][200]

    # volumes aligned with the adjusted bars (for R2-C's PIT floor)
    raw_bars = json.loads(BARS_CACHE.read_text())
    volumes: dict[str, list[float | None]] = {}
    for sym in raw_bars:
        bs, vols = to_adjusted_barlikes(raw_bars[sym])
        assert len(bs) == len(mkt["bars"][sym]), f"{sym}: volume/bar misalignment"
        volumes[sym] = vols

    def gate(rows: list[dict], above: dict[date, bool]) -> list[dict]:
        # entry-date gate on the PRIOR trading day's close vs prior-day SMA
        # (round-1 counter-agent convention); a missing value drops the entry
        return [t for t in rows
                if above.get(date.fromisoformat(t["entry_date"]), False)]

    # BASELINES — read from the round-1 restated results, never recomputed
    v0s = r1["variants"]["V0"]["stats"]
    v2s = r1["variants"]["V2"]["stats"]
    v6bs = r1["variants"]["V6b"]["stats"]

    # MACHINERY CHECKS — the round-2 engine must reproduce the stored restated
    # V2 (call book + 200dma prior-close gate) and V6b (momentum book) before
    # any round-2 variant is graded.
    t2, _ = select_capped(gate(live_rows, up200), CAP)
    v2_curve = run_call_book(t2, mkt)
    assert_close("V2 (run_call_book)", seg_stats(v2_curve, START, END), v2s["full"])
    v2_curve_y0 = run_call_book_yield(t2, mkt, None)
    assert v2_curve_y0 == v2_curve, \
        "run_call_book_yield(None) diverged from run_call_book"
    v6b_curve, n_reb_v6b, _ = run_momentum_book(
        mkt, tiers, universe, top_n=5, gate_window=50)
    assert_close("V6b (run_momentum_book)", seg_stats(v6b_curve, START, END), v6bs["full"])
    assert n_reb_v6b == r1["variants"]["V6b"]["meta"]["rebalances"], "V6b rebalance drift"
    print(f"Machinery checks PASSED: restated V2 (${seg_stats(v2_curve, START, END)['end_value']:,.0f})"
          f" and V6b (${seg_stats(v6b_curve, START, END)['end_value']:,.0f}) reproduce the"
          " stored round-1 restated stats; yield engine reduces exactly to round-1 at rf=0")

    curves: dict[str, list[tuple[date, float]]] = {}
    meta: dict[str, dict] = {}

    # R2-A — V2 gate (200dma prior-close) + V10 trailing exits on the COMBINED
    # live-flag fires, cap 10
    trail_rows, a_open = build_trailing_rows(live_rows, mkt, tiers)
    ta, sa = select_capped(gate(trail_rows, up200), CAP)
    curves["R2-A"] = run_call_book(ta, mkt)
    meta["R2-A"] = {
        "desc": "combined live-flag fires, 3xATR trailing stop, 90d time stop, 200dma gate, <=10 open",
        "n_regraded": len(trail_rows), "open_at_end_excluded": a_open,
        "n_taken": len(ta), "skipped_at_cap": sa,
        "avg_r_net": statistics.fmean([t["r_net"] for t in trail_rows]),
        "stop_rate": sum(1 for t in trail_rows if t["status"] == "stopped") / len(trail_rows),
        "avg_hold_days": statistics.fmean([t["hold_days"] for t in trail_rows])}

    # R2-B — momentum book top-10, 50dma gate, tier A/B
    curves["R2-B"], n_reb_b, _ = run_momentum_book(
        mkt, tiers, universe, top_n=R2B_TOP_N, gate_window=50)
    meta["R2-B"] = {"desc": "monthly top-10 60-bar RS-vs-XBI book, tier A/B, 50dma gate",
                    "rebalances": n_reb_b}

    # R2-C — momentum book top-5, 50dma gate, PIT $2M floor replacing tiers
    curves["R2-C"], n_reb_c, c_floor_excl = run_momentum_book(
        mkt, tiers, universe, top_n=5, gate_window=50,
        use_pit_floor=True, volumes=volumes)
    meta["R2-C"] = {"desc": "monthly top-5 RS-vs-XBI book, 50dma gate, "
                            "PIT floor: trailing 60d median $vol >= $2M (no tier filter)",
                    "rebalances": n_reb_c, "floor_exclusions": c_floor_excl}

    # R2-E — momentum book top-5, 200dma gate, tier A/B
    curves["R2-E"], n_reb_e, _ = run_momentum_book(
        mkt, tiers, universe, top_n=5, gate_window=200)
    meta["R2-E"] = {"desc": "monthly top-5 RS-vs-XBI book, tier A/B, 200dma gate",
                    "rebalances": n_reb_e}

    # R2-D — cash-yield realism: restated V2 and V6b with idle cash earning
    # BIL's daily total return (flat 2.0%/yr proxy on missing days, flagged)
    bil, proxy_days = load_bil_yield(calendar)
    bil_ann = (math.prod(1 + bil[d] for d in calendar)) ** (365.25 / (calendar[-1] - calendar[0]).days) - 1
    curves["R2-D-V2"] = run_call_book_yield(t2, mkt, bil)
    meta["R2-D-V2"] = {"desc": "restated V2 with idle cash earning BIL total return",
                       "n_taken": len(t2), "bil_annualized": bil_ann,
                       "proxy_days": len(proxy_days),
                       "proxy_dates": [d.isoformat() for d in proxy_days]}
    curves["R2-D-V6b"], n_reb_d, _ = run_momentum_book(
        mkt, tiers, universe, top_n=5, gate_window=50, cash_yield=bil)
    meta["R2-D-V6b"] = {"desc": "restated V6b with idle cash earning BIL total return",
                        "rebalances": n_reb_d, "bil_annualized": bil_ann,
                        "proxy_days": len(proxy_days),
                        "proxy_dates": [d.isoformat() for d in proxy_days]}

    # Stats + verdicts (R2-D is a realism restatement: SURVIVES n/a)
    order = ["R2-A", "R2-B", "R2-C", "R2-E", "R2-D-V2", "R2-D-V6b"]
    judged = ["R2-A", "R2-B", "R2-C", "R2-E"]
    stats = {k: all_stats(curves[k]) for k in order}
    verdicts: dict[str, bool | None] = {
        k: (survives_double(stats[k], v0s, v2s) if k in judged else None)
        for k in order}

    # Sanity
    for k in order:
        vals = [v for _, v in curves[k]]
        assert len(vals) == len(calendar) and min(vals) > 0, f"{k}: degenerate curve"
        assert len({round(v, 2) for v in vals}) > 100, f"{k}: flat curve"
        for seg in stats[k].values():
            for key, v in seg.items():
                assert not (isinstance(v, float) and math.isnan(v)), f"{k}.{key} NaN"
    assert 120 <= n_reb_b <= 130 and n_reb_b == n_reb_c == n_reb_e == n_reb_d, \
        f"momentum rebalances {n_reb_b}/{n_reb_c}/{n_reb_e}/{n_reb_d} != ~128"
    d_v2_end = stats["R2-D-V2"]["full"]["end_value"]
    d_v6b_end = stats["R2-D-V6b"]["full"]["end_value"]
    assert d_v2_end > v2s["full"]["end_value"], "R2-D V2+BIL must exceed plain V2"
    assert d_v6b_end > v6bs["full"]["end_value"], "R2-D V6b+BIL must exceed plain V6b"
    print(f"Sanity PASSED: {len(order)} curves x {len(calendar)} days, no NaNs, "
          f"momentum rebalances {n_reb_b}, BIL annualized {bil_ann:+.2%} "
          f"({len(proxy_days)} proxy days), R2-D uplifts positive")

    # Baselines carried through for charting (stats + curves copied verbatim
    # from the round-1 restated results JSON)
    baselines = {k: {"meta": r1["variants"][k]["meta"],
                     "stats": r1["variants"][k]["stats"],
                     "curve": r1["variants"][k]["curve"],
                     "source": "backtest_variants_10y_results.json (restated round 1)"}
                 for k in ("V0", "V2", "V6b", "XBI", "SPY")}

    _print_table(order, stats, verdicts, r1)
    _write_results(order, stats, verdicts, curves, meta, baselines, bil_ann, proxy_days)
    _write_report(order, stats, verdicts, meta, r1, bil_ann, proxy_days)
    print(f"\nReport written to {REPORT}")
    print(f"Results JSON written to {RESULTS}")


def _sv(verdict: bool | None, k: str = "") -> str:
    if verdict is None:
        return "n/a (realism restatement)" if k.startswith("R2-D") else "—"
    return "YES" if verdict else "no"


def _baseline_rows(r1: dict) -> list[tuple[str, dict]]:
    return [(f"{k}*", r1["variants"][k]["stats"]) for k in ("V0", "V2", "V6b", "XBI", "SPY")]


def _print_table(order, stats, verdicts, r1) -> None:
    print("\nvariant | end$ | CAGR | maxDD | Sharpe | Sortino | Calmar | SURVIVES (double baseline)")
    rows = [(k, stats[k], verdicts[k]) for k in order] + \
           [(k, s, None) for k, s in _baseline_rows(r1)]
    for k, s, v in rows:
        f = s["full"]
        print(f"{k:9s} | ${f['end_value']:>9,.0f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} "
              f"| {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['calmar']:.2f} | {_sv(v, k)}")
    print("(* = round-1 restated baseline, carried through — not a round-2 variant)")


def _round(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    return obj


def _write_results(order, stats, verdicts, curves, meta, baselines,
                   bil_ann, proxy_days) -> None:
    RESULTS.write_text(json.dumps(_round({
        "generated": datetime.now(timezone.utc).isoformat(),
        "contract": "docs/VARIANTS_PREREGISTRATION_R2.md",
        "period": [START.isoformat(), END.isoformat()],
        "sub_periods": {n: [lo.isoformat(), hi.isoformat()] for n, lo, hi in SUB_PERIODS},
        "protocol": {"start_equity": START_EQUITY, "risk_frac": RISK_FRAC,
                     "sizing_basis": "previous close equity",
                     "rf": "0 except R2-D (idle cash earns BIL total return)",
                     "mtm": "adjusted closes, forward-filled on the XBI calendar",
                     "regime_gates": "PRIOR trading day's close vs prior-day SMA (round-1 counter-agent convention, mandatory everywhere)",
                     "bil": {"source": "stockanalysis.com BIL adjusted closes (data/bil_bars_raw.json)",
                             "annualized_over_window": bil_ann,
                             "proxy": "flat 2.0%/yr where BIL bar missing",
                             "proxy_days": [d.isoformat() for d in proxy_days]},
                     "curves_note": ("curve arrays are downsampled to ~400 pts for "
                                     "display only — stats were computed from the "
                                     "full daily curves; do not recompute maxDD "
                                     "from the stored points"),
                     "survives": ("Sharpe AND Calmar > BOTH V0 and restated V2, "
                                  "full period AND >=2 of 3 sub-periods (both "
                                  "baselines beaten in the same sub-period); "
                                  "R2-D judged for reporting honesty only (n/a)")},
        "baselines": baselines,
        "variants": {k: {"meta": meta[k], "stats": stats[k],
                         "survives": verdicts[k],
                         "curve": downsample(curves[k])} for k in order},
    }), default=str))


def _write_report(order, stats, verdicts, meta, r1, bil_ann, proxy_days) -> None:
    v2s = r1["variants"]["V2"]["stats"]
    v6bs = r1["variants"]["V6b"]["stats"]
    lines: list[str] = []
    w = lines.append
    w("# Variant Campaign ROUND 2 — pre-registered (VARIANTS_PREREGISTRATION_R2.md)")
    w("")
    w(f"_Generated by `scripts/backtest_variants_r2.py` · {START} → {END} · reuses the"
      f" round-1 engine and per-call rows; baselines (V0, restated V2) read from"
      f" the round-1 restated results, never recomputed_")
    w("")
    w("## Read this first")
    w("")
    w("Inherits EVERY caveat of BACKTEST_CALLS_10Y.md and round 1 — one line each:")
    w("")
    w("- **Survivorship**: today's universe; dead names absent — absolute numbers flattered.")
    w("- **Alias/universe hindsight**: today's aliases and membership applied across all 10 years.")
    w("- **PIT submit-date lag**: catalyst knowledge at CT.gov posting granularity.")
    w("- **No composite/confidence gates**: every suppressed fire trades at fixed fraction —")
    w("  the live engine would trade fewer, larger calls.")
    w("- **Unreplayable live triggers**: sentiment/revision/options lanes absent; this is the")
    w("  replayable shadow, not the live book.")
    w("- **Multiple comparisons**: 5 registered variants; consistency is the bar; no")
    w("  re-parameterization after seeing results.")
    w("- **Momentum books are a different engine shape** (monthly, always-in, no stops) and")
    w("  top-5 books carry round 1's concentration warning; the bar is applied anyway.")
    w("")
    w("Round-2 specific:")
    w("")
    w("- **The bar is DOUBLE**: round 2 must beat BOTH V0 and the restated V2 — the best")
    w("  clean round-1 survivor — not just the broken baseline. XBI/SPY rows stay context.")
    w("- **R2-C's PIT floor removes the tier hindsight but NOT universe-membership")
    w("  survivorship**: the $2M floor is computable as-of each rebalance, but the names it")
    w("  filters are still drawn from a universe known TODAY to have survived and mattered —")
    w("  momentum-on-survivors remains the worst case of that bias; absolute CAGR still unusable.")
    w("- **R2-D changes reporting realism only**: idle cash earning BIL is an accounting fix")
    w("  to round-1 survivors, not a new strategy — its SURVIVES column is n/a by contract.")
    w("- **Survivors are HYPOTHESES** (TUNING.md law): never direct config changes.")
    w("")
    w("## Protocol")
    w("")
    w("$100k start · risk 1% of the previous close's equity per call (momentum books fully")
    w("invested) · daily MTM on adjusted closes · realized r_net (tiered slippage")
    w("A=10/B=40/C=100 bps per side) on the exit date · momentum books: monthly")
    w("first-trading-day rebalance, trailing 60-bar return vs XBI, equal weight, 10 bps/side")
    w("turnover cost, 7-day bar-staleness exclusion · ALL regime gates test the PRIOR")
    w("trading day's close vs prior-day SMA (round-1 counter-agent convention, mandatory) ·")
    w("rf = 0 except R2-D · Sharpe/Sortino annualized √252 · sub-period stats on that")
    w("segment of the same curve. Machinery checks: this engine reproduces the stored")
    w("restated V2 and V6b before any round-2 variant is graded, and the R2-D engine at")
    w("zero yield reduces exactly to the round-1 engine.")
    w("")
    w("**SURVIVES** = Sharpe AND Calmar beat BOTH baselines (V0 AND restated V2) over the")
    w("full period AND in ≥2 of 3 sub-periods (both baselines beaten in the same")
    w("sub-period). R2-D: n/a (realism restatement of round-1 survivors).")
    w("")
    w("## Full period 2016-01-04 → 2026-08-19")
    w("")
    w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | SURVIVES |")
    w("|---|---|---|---|---|---|---|---|")
    rows = [(k, stats[k], verdicts[k]) for k in order] + \
           [(k, s, None) for k, s in _baseline_rows(r1)]
    for k, s, v in rows:
        f = s["full"]
        w(f"| {k} | ${f['end_value']:,.0f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} "
          f"| {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['calmar']:.2f} | {_sv(v, k)} |")
    w("")
    w("_* = round-1 restated baseline carried through for comparison/charting — not a")
    w("round-2 variant. V6b* is context for R2-D-V6b._")
    w("")
    d_v2 = stats["R2-D-V2"]["full"]
    d_v6b = stats["R2-D-V6b"]["full"]
    w("### R2-D — the cash-yield uplift (reporting realism, not alpha)")
    w("")
    w(f"- BIL total return annualized {bil_ann:+.2%} over the window "
      f"({len(proxy_days)} days on the flat 2.0%/yr proxy"
      + (": " + ", ".join(d.isoformat() for d in proxy_days) if proxy_days else "") + ").")
    w(f"- **V2**: ${v2s['full']['end_value']:,.0f} → ${d_v2['end_value']:,.0f} "
      f"(+${d_v2['end_value'] - v2s['full']['end_value']:,.0f}); CAGR "
      f"{v2s['full']['cagr']:+.2%} → {d_v2['cagr']:+.2%}; Sharpe "
      f"{v2s['full']['sharpe']:.2f} → {d_v2['sharpe']:.2f}.")
    w(f"- **V6b**: ${v6bs['full']['end_value']:,.0f} → ${d_v6b['end_value']:,.0f} "
      f"(+${d_v6b['end_value'] - v6bs['full']['end_value']:,.0f}); CAGR "
      f"{v6bs['full']['cagr']:+.2%} → {d_v6b['cagr']:+.2%}; Sharpe "
      f"{v6bs['full']['sharpe']:.2f} → {d_v6b['sharpe']:.2f}.")
    w("- Direction confirms the round-1 counter-agent's minor: rf=0 understated the gated")
    w("  books. Idle cash earning T-bills only ADDS — these are the honest magnitudes for")
    w("  V2/V6b going forward; the strategy content is unchanged.")
    w("")
    for name, _, _ in SUB_PERIODS:
        w(f"## Sub-period {name}")
        w("")
        w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | beats BOTH (Sharpe&Calmar) |")
        w("|---|---|---|---|---|---|---|---|")
        v0p = r1["variants"]["V0"]["stats"][name]
        v2p = r1["variants"]["V2"]["stats"][name]
        for k, s, v in rows:
            sp = s[name]
            if v is None and k not in ("V0*",):
                beat = "n/a" if k.startswith("R2-D") else "—"
            else:
                beat = "—"
            if k in ("R2-A", "R2-B", "R2-C", "R2-E", "XBI*", "SPY*", "V6b*"):
                beat = "yes" if (beats(sp, v0p) and beats(sp, v2p)) else "no"
            w(f"| {k} | ${sp['end_value']:,.0f} | {sp['cagr']:+.2%} | {sp['max_dd']:.1%} "
              f"| {sp['sharpe']:.2f} | {sp['sortino']:.2f} | {sp['calmar']:.2f} | {beat} |")
        w("")
    w("## Variant notes")
    w("")
    for k in order:
        m = meta[k]
        extra = ", ".join(f"{kk}={vv:,.3f}" if isinstance(vv, float) else f"{kk}={vv}"
                          for kk, vv in m.items() if kk not in ("desc", "proxy_dates"))
        w(f"- **{k}** — {m['desc']}" + (f" ({extra})" if extra else ""))
    w("")
    w("## Ambiguity calls (most conservative reading, per contract)")
    w("")
    w("- ALL regime gates (R2-A entries; R2-B/C/E and R2-D-V6b rebalances) test the PRIOR")
    w("  trading day's close vs the prior-day SMA — the round-1 counter-agent convention,")
    w("  applied everywhere; an undefined SMA drops the entry/rebalance (never binds).")
    w("- R2-A re-grades EVERY live-flag row with the round-1 V10 mechanics unchanged")
    w("  (trail = prior-bar peak close − 3.0×ATR14 through the prior bar, recomputed daily;")
    w("  open-first gap fills; 90 CALENDAR-day time stop; initial risk unit = the stored")
    w("  build_levels risk; tiered slippage). Rows still open at data end are excluded")
    w("  (round-1 convention); duplicate same-day fires from different flags remain")
    w("  distinct calls at the cap, exactly as in V0.")
    w("- R2-C's PIT floor = median of (adjusted close × volume) over the 60 bars ending at")
    w("  the PRIOR bar (knowable before the rebalance; the repo's median_addv dollar-volume")
    w("  convention) ≥ $2M; a name failing the floor or lacking 60 bars is excluded that")
    w("  month; NO tier filter — the whole 32-name universe is eligible.")
    w("- Momentum ranking still uses the rebalance day's own close (round-1 disclosed")
    w("  convention; the round-1 counter-agent showed a 1-day delay does not drive results);")
    w("  only GATES are prior-close.")
    w("- R2-D accrues yesterday's idle cash at today's BIL total return: for call books,")
    w("  idle = equity − Σ(risk$/risk × price) (position notional MTM), clamped to")
    w("  [0, equity]; for the momentum book, idle = the tracked cash balance (full equity")
    w("  when the gate is off). Yield feeds back into sizing (1% of the higher equity).")
    w("- BIL daily total return from stockanalysis.com adjusted closes (field 'a'),")
    w(f"  cached at data/bil_bars_raw.json; {len(proxy_days)} calendar days lacked a BIL")
    w("  bar in-window" + (" — proxied at flat 2.0%/yr on: "
      + ", ".join(d.isoformat() for d in proxy_days) if proxy_days
      else ", so the flat 2.0%/yr proxy was never used") + ".")
    w("- Baselines for the double bar are the STORED restated round-1 stats")
    w("  (backtest_variants_10y_results.json), not recomputations; the round-2 engine's")
    w("  reproduction of V2 and V6b is asserted before grading.")
    w("")
    w("## Verdict")
    w("")
    survivors = [k for k in ("R2-A", "R2-B", "R2-C", "R2-E") if verdicts[k]]
    if survivors:
        w(f"Survivors under the round-2 double-baseline bar: **{', '.join(survivors)}**.")
        w("Per the contract these become HYPOTHESES.md entries / TUNING proposals — never")
        w("direct config changes.")
    else:
        w("**No round-2 strategy variant survived** the double-baseline bar (beat BOTH V0")
        w("and the restated V2 on Sharpe AND Calmar, full period and ≥2/3 sub-periods).")
        w("Per the contract nothing is promoted; refinements require a round-3 registration.")
    w("")
    w("R2-D (n/a by contract) stands as the reporting-honesty restatement: the V2 and V6b")
    w("numbers above under R2-D-V2 / R2-D-V6b are the honest magnitudes for those round-1")
    w("survivors with cash earning its real yield; strategy content unchanged.")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
