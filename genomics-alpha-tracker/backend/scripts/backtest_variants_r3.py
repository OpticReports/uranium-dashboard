"""ROUND 3 of the pre-registered variant campaign
(docs/VARIANTS_PREREGISTRATION_R3.md — the contract; registered BEFORE any
round-3 variant was run).

Reuses the round-1/round-2 engines (scripts/backtest_variants_10y.py,
scripts/backtest_variants_r2.py) — functions are imported where mechanics are
unchanged and minimally copied ONLY where a registered delta requires a
parameter the earlier function hard-codes; NO convention is forked. The R2-A
sleeve is regenerated with the exact round-2 recipe (build_trailing_rows ->
200dma prior-close gate -> select_capped -> run_call_book) and asserted to
reproduce the stored $430,406.29 end value to $1 before anything else runs.

Judgment protocol (fixed by the round-3 pre-registration):
  Daily granularity, $100k, rf = 0 except where a variant IS the cash-yield /
  leverage mechanic. Baseline = the 30/70 R2-A/SPY daily-rebalanced return
  mix (H13; +15.89% CAGR / 29.3% maxDD / 1.02 Sharpe — reproduction asserted).
  SURVIVES = Sharpe AND Calmar beat the 30/70 baseline over the full period
  AND in >= 2 of 3 sub-periods. R3-F is a robustness MAP and R3-G is
  VALIDATION — neither is judged.

Usage:  python -m scripts.backtest_variants_r3
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_variants_10y import (  # noqa: E402
    CALLS_RESULTS,
    CAP,
    END,
    LIVE_SET_FLAGS,
    RISK_FRAC,
    START,
    START_EQUITY,
    SUB_PERIODS,
    TRADING_DAYS,
    all_stats,
    downsample,
    load_market,
    load_spy_curve,
    run_call_book,
    seg_stats,
    select_capped,
)
from scripts.backtest_variants_r2 import (  # noqa: E402
    RESULTS as R2_RESULTS,
    build_trailing_rows,
    load_bil_yield,
)
from scripts.backtest_calls import SLIPPAGE_BPS_BY_TIER  # noqa: E402
from scripts.backtest_signals import atr_series  # noqa: E402
from app.calls.rules import BarLike  # noqa: E402
from datetime import timedelta  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
SPY_RAW = DATA / "spy_bars_raw.json"
RESULTS = DATA / "backtest_variants_r3_results.json"
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_VARIANTS_R3.md"

# Round-3 fixed parameters (VARIANTS_PREREGISTRATION_R3.md — not tunable)
BASE_W = 0.30                      # the H13 baseline weight on R2-A
R3B_CLAMP = (0.15, 0.45)
R3B_VOL_WINDOW = 60                # trailing 60d realized, prior-close
R3C_L = 1.25
R3C_SPREAD_DAILY = 150 / 10_000 / TRADING_DAYS   # 150 bps/yr margin spread
R3C_GRID = [round(1.0 + 0.05 * i, 2) for i in range(13)]   # 1.00 .. 1.60
SPY_MAXDD = 0.337                  # SPY's ex-post maxDD (frontier target)
R3D_LOOKBACK_BARS = 252            # 12-month TSMOM, prior-close
R3E_RISK_BY_FLAG = {"rel_strength_60d_trail": 0.0125,
                    "volume_anomaly_trail": 0.0075}   # others: RISK_FRAC (1%)
R3F_TRAILS = (2.5, 3.0, 3.5)
R3F_STOPS = (60, 90, 120)
R3G_DRAWS = 2000
R3G_MEAN_BLOCK = 21
R3G_SEED = 20260820                # fixed; documented in the results JSON

# H13 baseline reproduction targets (the pre-registration's stated numbers;
# CAGR there is trading-day annualized (252/n) — asserted in main(), while
# the campaign tables keep the house calendar-day seg_stats convention)
H13 = {"cagr_td": 0.1589, "max_dd": 0.293, "sharpe": 1.02}
R2A_END = 430_406.29               # stored round-2 R2-A end value (to $1)


# --- R2-A book with daily invested-notional capture ---------------------------------
# Minimal copy of round-1's run_call_book (hedge/vol_target branches dropped —
# unused by R2-A) with TWO registered additions: (1) it records each day's
# invested MTM fraction of equity (sum over open calls of (risk$/risk)*price,
# / equity, clamped [0,1]) for R3-A's cash_frac; (2) an optional per-flag risk
# fraction map for R3-E's tilts. risk_by_flag=None reduces EXACTLY to
# run_call_book (asserted in main()).

def run_call_book_invested(taken: list[dict], mkt: dict,
                           risk_by_flag: dict[str, float] | None = None,
                           ) -> tuple[list[tuple[date, float]], dict[date, float]]:
    calendar, px = mkt["calendar"], mkt["px"]
    by_entry: dict[str, list[dict]] = {}
    for t in taken:
        by_entry.setdefault(t["entry_date"], []).append(t)

    cash = START_EQUITY
    open_pos: list[dict] = []
    curve: list[tuple[date, float]] = []
    inv_frac: dict[date, float] = {}
    prev_equity = START_EQUITY

    for d in calendar:
        ds = d.isoformat()
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
            frac = RISK_FRAC if risk_by_flag is None else \
                risk_by_flag.get(t["flag"], RISK_FRAC)
            rd = frac * prev_equity
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
        inv_frac[d] = min(max(invested / equity, 0.0), 1.0) if equity > 0 else 1.0
        prev_equity = equity
    return curve, inv_frac


# --- R3-F: parameterized trailing grade ----------------------------------------------
# Minimal copies of round-1's grade_trailing and round-2's build_trailing_rows
# with the two hard-coded parameters (V10_TRAIL_ATR_MULT, V10_TIME_STOP_DAYS)
# exposed — the r1/r2 scripts are NOT edited. (trail_mult=3.0, time_stop=90)
# reproduces build_trailing_rows row-for-row (asserted in main()).

def grade_trailing_param(bars: list[BarLike], atrs: list[float | None], j: int,
                         entry: float, expiry: date, trail_mult: float,
                         ) -> tuple[str, date, float] | None:
    peak: float | None = None
    prev: BarLike | None = None
    for k in range(j, len(bars)):
        b = bars[k]
        if b.low is None or b.high is None or b.close is None:
            continue
        if b.date > expiry:
            if prev is not None:
                return ("expired", prev.date, prev.close)
            return ("expired", b.date, b.open if b.open is not None else b.close)
        if peak is not None and atrs[k - 1] is not None:
            trail = peak - trail_mult * atrs[k - 1]
            if b.open is not None and b.open <= trail:
                return ("stopped", b.date, b.open)
            if b.low <= trail:
                return ("stopped", b.date, trail)
        if b.date == expiry:
            return ("expired", b.date, b.close)
        peak = b.close if peak is None else max(peak, b.close)
        prev = b
    return None


def build_trailing_rows_param(rows: list[dict], mkt: dict, tiers: dict[str, str],
                              trail_mult: float, time_stop_days: int,
                              ) -> tuple[list[dict], int]:
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
        entry = t["entry"]
        risk = t["risk"]
        expiry = date.fromisoformat(t["entry_date"]) + timedelta(days=time_stop_days)
        g = grade_trailing_param(bars, atr_cache[sym], j, entry, expiry, trail_mult)
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


# --- blend machinery -----------------------------------------------------------------

def sleeve_returns(curve_by: dict[date, float], dates: list[date]) -> list[float]:
    """Daily returns aligned to dates[1:] (index t = return over t-1 -> t)."""
    return [curve_by[dates[i]] / curve_by[dates[i - 1]] - 1
            for i in range(1, len(dates))]


def compound(dates: list[date], rets: list[float]) -> list[tuple[date, float]]:
    v = START_EQUITY
    curve = [(dates[0], v)]
    for i, r in enumerate(rets):
        v *= 1 + r
        curve.append((dates[i + 1], v))
    return curve


def month_first_indices(dates: list[date]) -> list[int]:
    out, seen = [], set()
    for i, d in enumerate(dates):
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            out.append(i)
    return out


def max_dd_of(vals: list[float]) -> float:
    peak, dd = -math.inf, 0.0
    for v in vals:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak) if peak > 0 else dd
    return dd


# --- judgment ------------------------------------------------------------------------

def beats(a: dict, b: dict) -> bool:
    return bool(a and b and a["sharpe"] > b["sharpe"] and a["calmar"] > b["calmar"])


def survives_vs_base(stats: dict, base: dict) -> bool:
    """The round-3 pre-registered bar: Sharpe AND Calmar beat the 30/70
    baseline over the full period AND in >= 2 of 3 sub-periods."""
    if not beats(stats["full"], base["full"]):
        return False
    wins = sum(1 for name, _, _ in SUB_PERIODS if beats(stats[name], base[name]))
    return wins >= 2


# --- main ----------------------------------------------------------------------------

def main() -> None:  # noqa: PLR0915
    res = json.loads(CALLS_RESULTS.read_text())
    call_rows: dict[str, list[dict]] = res["call_rows"]
    tiers: dict[str, str] = res["tiers"]
    r2 = json.loads(R2_RESULTS.read_text())
    mkt = load_market()
    calendar = mkt["calendar"]

    live_rows = [t for f in LIVE_SET_FLAGS for t in call_rows[f]]
    up200 = mkt["xbi_above_prior"][200]

    def gate(rows: list[dict]) -> list[dict]:
        # entry-date gate on the PRIOR trading day's close vs prior-day 200dma
        # (mandatory convention); a missing value drops the entry
        return [t for t in rows
                if up200.get(date.fromisoformat(t["entry_date"]), False)]

    # ---- MACHINERY CHECK 1: regenerate the R2-A sleeve with the exact round-2
    # recipe and reproduce the stored end value to $1 before anything else.
    trail_rows, a_open = build_trailing_rows(live_rows, mkt, tiers)
    ta, sa = select_capped(gate(trail_rows), CAP)
    r2a_curve = run_call_book(ta, mkt)
    r2a_stored = r2["variants"]["R2-A"]["stats"]["full"]
    r2a_full = seg_stats(r2a_curve, START, END)
    assert abs(r2a_full["end_value"] - r2a_stored["end_value"]) <= 1.0, \
        (f"R2-A reproduction FAILED: ${r2a_full['end_value']:,.2f} vs stored "
         f"${r2a_stored['end_value']:,.2f}")
    assert abs(r2a_full["end_value"] - R2A_END) <= 1.0, "R2-A != $430,406.29"
    # the invested-capture engine must reduce exactly to run_call_book
    r2a_curve_inv, inv_frac = run_call_book_invested(ta, mkt, None)
    assert r2a_curve_inv == r2a_curve, \
        "run_call_book_invested(None) diverged from run_call_book"
    print(f"Machinery check 1 PASSED: R2-A reproduces to "
          f"${r2a_full['end_value']:,.2f} (stored ${r2a_stored['end_value']:,.2f}, to $1); "
          f"invested-capture engine reduces exactly to run_call_book")

    # ---- sleeves on the intersection calendar
    spy_curve = load_spy_curve(calendar)
    spy_by = dict(spy_curve)
    r2a_by = dict(r2a_curve)
    inter = [d for d in calendar if d in spy_by and d in r2a_by]
    n = len(inter)
    rA = sleeve_returns(r2a_by, inter)
    rS = sleeve_returns(spy_by, inter)
    bil, proxy_days = load_bil_yield(calendar)
    rB = [bil.get(inter[i], 0.0) for i in range(1, n)]
    bil_ann = (math.prod(1 + bil[d] for d in calendar)) ** (
        365.25 / (calendar[-1] - calendar[0]).days) - 1
    rebals = month_first_indices(inter)
    reb_next = {rebals[k]: (rebals[k + 1] if k + 1 < len(rebals) else n)
                for k in range(len(rebals))}

    # ---- MACHINERY CHECK 2: the 30/70 baseline reproduces the H13 numbers.
    base_rets = [BASE_W * rA[t] + (1 - BASE_W) * rS[t] for t in range(n - 1)]
    base_curve = compound(inter, base_rets)
    base_stats = all_stats(base_curve)
    bf = base_stats["full"]
    cagr_td = (bf["end_value"] / START_EQUITY) ** (TRADING_DAYS / (n - 1)) - 1
    assert abs(cagr_td - H13["cagr_td"]) <= 5e-4, \
        f"30/70 trading-day CAGR {cagr_td:.4%} != registered {H13['cagr_td']:.2%}"
    assert abs(bf["max_dd"] - H13["max_dd"]) <= 5e-4, \
        f"30/70 maxDD {bf['max_dd']:.4%} != registered {H13['max_dd']:.1%}"
    assert abs(bf["sharpe"] - H13["sharpe"]) <= 5e-3, \
        f"30/70 Sharpe {bf['sharpe']:.4f} != registered {H13['sharpe']:.2f}"
    print(f"Machinery check 2 PASSED: 30/70 baseline reproduces H13 "
          f"({cagr_td:+.2%} trading-day CAGR / {bf['max_dd']:.1%} maxDD / "
          f"{bf['sharpe']:.2f} Sharpe vs registered +15.89% / 29.3% / 1.02); "
          f"tables below use the house calendar-day CAGR ({bf['cagr']:+.2%})")

    curves: dict[str, list[tuple[date, float]]] = {"BASE": base_curve}
    meta: dict[str, dict] = {}

    # R3-A — 30/70 blend, R2-A idle cash earns BIL (the R2-D mechanic inside
    # the blend): sleeve return r_R2A,t + cash_frac_t * r_BIL,t with
    # cash_frac = 1 - invested MTM fraction as of the PRIOR close (the R2-D
    # accrual convention: yesterday's idle cash earns today's BIL return)
    cash_frac = [1.0 - inv_frac[inter[t - 1]] for t in range(1, n)]
    a_rets = [BASE_W * (rA[t] + cash_frac[t] * rB[t]) + (1 - BASE_W) * rS[t]
              for t in range(n - 1)]
    curves["R3-A"] = compound(inter, a_rets)
    meta["R3-A"] = {
        "desc": "30/70 blend; R2-A sleeve's idle cash earns BIL total return",
        "avg_cash_frac": statistics.fmean(cash_frac),
        "all_cash_days_frac": sum(1 for c in cash_frac if c >= 1.0) / len(cash_frac),
        "bil_annualized": bil_ann, "proxy_days": len(proxy_days)}

    # R3-B — vol-scaled sleeve weights, monthly, prior-close 60d realized vols
    w_sched: list[float] = [BASE_W] * (n - 1)   # per return index t (1..n-1 -> 0..n-2)
    w_used: list[float] = []
    for i in rebals:
        # returns knowable at the prior close: indices t <= i-1 (ret t spans
        # closes t-1 -> t), i.e. base list positions < i - 1 + 1 = i
        avail = i - 1                     # count of sleeve returns with t <= i-1
        if avail >= R3B_VOL_WINDOW:
            sigA = statistics.stdev(rA[avail - R3B_VOL_WINDOW:avail])
            sigS = statistics.stdev(rS[avail - R3B_VOL_WINDOW:avail])
            if sigA > 0:
                w = min(max(BASE_W * sigS / sigA, R3B_CLAMP[0]), R3B_CLAMP[1])
            else:
                w = R3B_CLAMP[1] if sigS > 0 else BASE_W   # zero sleeve vol -> clamp top
        else:
            w = BASE_W                    # insufficient history: baseline weight
        w_used.append(w)
        # effective from the CLOSE of the rebalance day (round-2 momentum-book
        # execution convention): return indices t in [i+1, next rebalance]
        for t in range(i + 1, reb_next[i] + 1):
            if 1 <= t <= n - 1:
                w_sched[t - 1] = w
    b_rets = [w_sched[t] * rA[t] + (1 - w_sched[t]) * rS[t] for t in range(n - 1)]
    curves["R3-B"] = compound(inter, b_rets)
    meta["R3-B"] = {
        "desc": "monthly vol-scaled R2-A weight, clamp [0.15, 0.45], 60d prior-close vols",
        "rebalances": len(rebals), "avg_weight": statistics.fmean(w_used),
        "min_weight": min(w_used), "max_weight": max(w_used),
        "months_at_lower_clamp": sum(1 for w in w_used if w <= R3B_CLAMP[0]),
        "months_at_upper_clamp": sum(1 for w in w_used if w >= R3B_CLAMP[1])}

    # R3-C — 1.25x levered 30/70, daily reset, financed at BIL + 150 bps
    def lever(L: float) -> list[float]:
        return [L * base_rets[t] - (L - 1) * (rB[t] + R3C_SPREAD_DAILY)
                for t in range(n - 1)]

    curves["R3-C"] = compound(inter, lever(R3C_L))
    lever1_curve = compound(inter, lever(1.0))
    assert lever1_curve == base_curve, "L=1.0 must reduce exactly to the baseline"
    frontier = []
    for L in R3C_GRID:
        c = compound(inter, lever(L))
        s = seg_stats(c, START, END)
        frontier.append({"L": L, "cagr": s["cagr"], "max_dd": s["max_dd"],
                         "sharpe": s["sharpe"]})
    match = min(frontier, key=lambda f: abs(f["max_dd"] - SPY_MAXDD))
    meta["R3-C"] = {
        "desc": "1.25x daily-reset levered 30/70, financed at BIL + 150 bps on the borrowed fraction",
        "financing_bps_over_bil": 150, "bil_annualized": bil_ann,
        "frontier_grid": frontier,
        "dd_match": {"target_max_dd": SPY_MAXDD, **match}}

    # R3-D — TSMOM core: 70% leg -> BIL when SPY 12m total return (prior
    # close, 252 bars) is negative, checked at each monthly rebalance
    spy_rows = json.loads(SPY_RAW.read_text())["data"]
    spy_bars = sorted(((date.fromisoformat(r["t"]), r["a"]) for r in spy_rows
                       if r.get("a") not in (None, 0)), key=lambda x: x[0])
    spy_dates = [d for d, _ in spy_bars]
    spy_adj = [a for _, a in spy_bars]

    def spy_mom_12m(d: date) -> float | None:
        import bisect
        k = bisect.bisect_left(spy_dates, d) - 1   # last SPY bar strictly before d
        if k < R3D_LOOKBACK_BARS:
            return None
        return spy_adj[k] / spy_adj[k - R3D_LOOKBACK_BARS] - 1

    risk_on: list[bool] = [True] * (n - 1)
    off_months = 0
    states = []
    for i in rebals:
        m = spy_mom_12m(inter[i])
        on = True if m is None else (m >= 0)   # unknown history -> invested (never binds: SPY back to 1993)
        states.append({"date": inter[i].isoformat(), "mom_12m": m, "risk_on": on})
        if not on:
            off_months += 1
        for t in range(i + 1, reb_next[i] + 1):
            if 1 <= t <= n - 1:
                risk_on[t - 1] = on
    d_rets = [BASE_W * rA[t] + (1 - BASE_W) * (rS[t] if risk_on[t] else rB[t])
              for t in range(n - 1)]
    curves["R3-D"] = compound(inter, d_rets)
    meta["R3-D"] = {
        "desc": "30/70 blend; 70% leg in BIL when SPY 12m prior-close return < 0, monthly check",
        "rebalances": len(rebals), "risk_off_months": off_months,
        "risk_off_dates": [s["date"] for s in states if not s["risk_on"]]}

    # R3-E — flag-tilted R2-A sizing (tilts fixed from the 10y per-flag
    # expectancies), then the 30/70 blend; selection (cap 10) is unchanged
    r3e_book, _ = run_call_book_invested(ta, mkt, R3E_RISK_BY_FLAG)
    r3e_by = dict(r3e_book)
    rE = sleeve_returns(r3e_by, inter)
    e_rets = [BASE_W * rE[t] + (1 - BASE_W) * rS[t] for t in range(n - 1)]
    curves["R3-E"] = compound(inter, e_rets)
    n_by_flag = {f: sum(1 for t in ta if t["flag"] == f)
                 for f in sorted({t["flag"] for t in ta})}
    meta["R3-E"] = {
        "desc": "30/70 blend of the flag-tilted R2-A book (rel_strength 1.25%, volume_anomaly 0.75%, others 1.0%)",
        "n_taken": len(ta), "taken_by_flag": n_by_flag,
        "tilted_book_end": r3e_book[-1][1]}

    # R3-F [MAP] — trail/time-stop robustness grid on standalone R2-A
    grid: dict[str, dict] = {}
    for m_ in R3F_TRAILS:
        for ts_ in R3F_STOPS:
            rows_c, open_c = build_trailing_rows_param(live_rows, mkt, tiers, m_, ts_)
            if (m_, ts_) == (3.0, 90):
                assert rows_c == trail_rows and open_c == a_open, \
                    "param grade (3.0, 90) diverged from round-2 build_trailing_rows"
            taken_c, _ = select_capped(gate(rows_c), CAP)
            cell_curve = run_call_book(taken_c, mkt)
            s = seg_stats(cell_curve, START, END)
            grid[f"{m_}x{ts_}"] = {
                "trail_mult": m_, "time_stop_days": ts_,
                "n_rows": len(rows_c), "open_at_end_excluded": open_c,
                "n_taken": len(taken_c), "end_value": s["end_value"],
                "cagr": s["cagr"], "max_dd": s["max_dd"], "sharpe": s["sharpe"]}
    center = grid["3.0x90"]
    assert abs(center["end_value"] - r2a_full["end_value"]) <= 1.0, \
        "R3-F center cell must reproduce R2-A"

    # R3-G [VALIDATION] — stationary block bootstrap of the 30/70 daily returns
    rng = random.Random(R3G_SEED)
    N = len(base_rets)
    horizon_years = (inter[-1] - inter[0]).days / 365.25
    p_new = 1.0 / R3G_MEAN_BLOCK
    cagrs, dds = [], []
    for _ in range(R3G_DRAWS):
        i = rng.randrange(N)
        v, peak, dd = 1.0, 1.0, 0.0
        for _step in range(N):
            v *= 1 + base_rets[i]
            if v > peak:
                peak = v
            else:
                d_ = 1 - v / peak
                if d_ > dd:
                    dd = d_
            i = rng.randrange(N) if rng.random() < p_new else (i + 1) % N
        cagrs.append(v ** (1 / horizon_years) - 1)
        dds.append(dd)
    cagrs.sort()
    dds.sort()

    def pct(vals: list[float], p: float) -> float:
        return vals[min(len(vals) - 1, max(0, round(p / 100 * (len(vals) - 1))))]

    boot = {"draws": R3G_DRAWS, "mean_block_days": R3G_MEAN_BLOCK,
            "seed": R3G_SEED, "horizon_years": horizon_years,
            "wrap_around": True,
            "cagr_pct": {"p5": pct(cagrs, 5), "p50": pct(cagrs, 50),
                         "p95": pct(cagrs, 95)},
            "max_dd_pct": {"p5": pct(dds, 5), "p50": pct(dds, 50),
                           "p95": pct(dds, 95)},
            "prob_cagr_negative": sum(1 for c in cagrs if c < 0) / len(cagrs),
            "prob_dd_worse_than_spy": sum(1 for d_ in dds if d_ > SPY_MAXDD) / len(dds)}

    # ---- stats + verdicts (R3-F map and R3-G validation are NOT judged)
    judged = ["R3-A", "R3-B", "R3-C", "R3-D", "R3-E"]
    order = judged + ["BASE"]
    stats = {k: all_stats(curves[k]) for k in order}
    stats["R2-A"] = all_stats(r2a_curve)
    stats["SPY"] = all_stats(spy_curve)
    curves["R2-A"] = r2a_curve
    curves["SPY"] = spy_curve
    verdicts: dict[str, bool | None] = {
        k: (survives_vs_base(stats[k], base_stats) if k in judged else None)
        for k in order + ["R2-A", "SPY"]}

    # ---- sanity
    assert stats["R3-A"]["full"]["end_value"] >= bf["end_value"], \
        "R3-A (BIL on idle cash) must not end below the plain 30/70 blend"
    for k in order + ["R2-A", "SPY"]:
        vals = [v for _, v in curves[k]]
        assert len(vals) == n and min(vals) > 0, f"{k}: degenerate curve"
        assert len({round(v, 2) for v in vals}) > 100, f"{k}: flat curve"
        for seg in stats[k].values():
            for key, v in seg.items():
                assert not (isinstance(v, float) and math.isnan(v)), f"{k}.{key} NaN"
    assert 120 <= len(rebals) <= 130, f"monthly rebalances {len(rebals)} != ~128"
    print(f"Sanity PASSED: {len(order) + 2} curves x {n} days, no NaNs, "
          f"{len(rebals)} monthly rebalances, R3-A uplift ${stats['R3-A']['full']['end_value'] - bf['end_value']:,.0f} >= 0, "
          f"L=1.0 reduces to baseline, R3-F center cell == R2-A")

    _print_table(judged, stats, verdicts, grid, boot)
    _write_results(judged, stats, verdicts, curves, meta, grid, boot,
                   base_stats, cagr_td, bil_ann, proxy_days)
    _write_report(judged, stats, verdicts, meta, grid, boot, base_stats,
                  cagr_td, bil_ann)
    print(f"\nReport written to {REPORT}")
    print(f"Results JSON written to {RESULTS}")


def _sv(v: bool | None) -> str:
    return "—" if v is None else ("YES" if v else "no")


def _print_table(judged, stats, verdicts, grid, boot) -> None:
    print("\nvariant | end$ | CAGR | maxDD | Sharpe | Sortino | Calmar | SURVIVES (vs 30/70)")
    for k in judged + ["BASE", "R2-A", "SPY"]:
        f = stats[k]["full"]
        label = {"BASE": "30/70*", "R2-A": "R2-A*", "SPY": "SPY*"}.get(k, k)
        print(f"{label:7s} | ${f['end_value']:>9,.0f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} "
              f"| {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['calmar']:.2f} | {_sv(verdicts[k])}")
    print("(* = baseline / context rows, not round-3 variants)")
    print("\nR3-F map — standalone R2-A Sharpe (CAGR / maxDD) by trail x time stop:")
    for m_ in R3F_TRAILS:
        cells = []
        for ts_ in R3F_STOPS:
            c = grid[f"{m_}x{ts_}"]
            cells.append(f"{ts_}d: {c['sharpe']:.2f} ({c['cagr']:+.1%}/{c['max_dd']:.0%})")
        print(f"  trail {m_}xATR | " + " | ".join(cells))
    c, d_ = boot["cagr_pct"], boot["max_dd_pct"]
    print(f"\nR3-G bootstrap ({boot['draws']} draws, mean block {boot['mean_block_days']}d): "
          f"CAGR p5/p50/p95 = {c['p5']:+.1%} / {c['p50']:+.1%} / {c['p95']:+.1%}; "
          f"maxDD p5/p50/p95 = {d_['p5']:.1%} / {d_['p50']:.1%} / {d_['p95']:.1%}")


def _round(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    return obj


def _write_results(judged, stats, verdicts, curves, meta, grid, boot,
                   base_stats, cagr_td, bil_ann, proxy_days) -> None:
    RESULTS.write_text(json.dumps(_round({
        "generated": datetime.now(timezone.utc).isoformat(),
        "contract": "docs/VARIANTS_PREREGISTRATION_R3.md",
        "period": [START.isoformat(), END.isoformat()],
        "sub_periods": {n_: [lo.isoformat(), hi.isoformat()] for n_, lo, hi in SUB_PERIODS},
        "protocol": {
            "start_equity": START_EQUITY,
            "granularity": "daily, blends are daily-rebalanced return mixes on the R2-A/SPY intersection calendar",
            "rf": "0 except where a variant IS the cash-yield/leverage mechanic (R3-A/C/D use BIL)",
            "signals": "prior-close everywhere (gates, TSMOM, vols); monthly updates at each month's first trading day, effective from that day's close",
            "cagr_convention": ("tables use the house calendar-day convention "
                                "(365.25); the pre-registration's +15.89% is the "
                                "same baseline curve trading-day annualized "
                                "(252/n) — both asserted"),
            "bil": {"annualized_over_window": bil_ann, "proxy_days": len(proxy_days)},
            "curves_note": ("curve arrays are downsampled to ~400 pts for display "
                            "only — stats were computed from the full daily "
                            "curves; do not recompute maxDD from the stored points"),
            "survives": ("Sharpe AND Calmar > the 30/70 baseline, full period AND "
                         ">=2 of 3 sub-periods; R3-F is a MAP and R3-G is "
                         "VALIDATION — neither judged")},
        "baseline": {"name": "30/70 R2-A/SPY daily-rebalanced mix (H13)",
                     "stats": base_stats, "cagr_trading_day": cagr_td,
                     "registered": H13, "curve": downsample(curves["BASE"])},
        "variants": {k: {"meta": meta[k], "stats": stats[k],
                         "survives": verdicts[k],
                         "curve": downsample(curves[k])} for k in judged},
        "context": {k: {"stats": stats[k], "curve": downsample(curves[k]),
                        "source": "regenerated this run; R2-A asserted vs stored round-2 stats"}
                    for k in ("R2-A", "SPY")},
        "r3f_grid": grid,
        "r3g_bootstrap": boot,
    }), default=str))


def _write_report(judged, stats, verdicts, meta, grid, boot, base_stats,
                  cagr_td, bil_ann) -> None:
    bf = base_stats["full"]
    lines: list[str] = []
    w = lines.append
    w("# Variant Campaign ROUND 3 — pre-registered (VARIANTS_PREREGISTRATION_R3.md)")
    w("")
    w(f"_Generated by `scripts/backtest_variants_r3.py` · {START} → {END} · reuses the"
      f" round-1/2 engines; the R2-A sleeve is regenerated with the exact round-2"
      f" recipe and asserted to reproduce the stored $430,406.29 to $1; the 30/70"
      f" baseline is asserted to reproduce H13's +15.89% / 29.3% / 1.02_")
    w("")
    w("## Read this first")
    w("")
    w("Inherits EVERY caveat of BACKTEST_CALLS_10Y.md and rounds 1-2 — one line each:")
    w("")
    w("- **Survivorship**: today's universe; dead names absent — absolute numbers flattered.")
    w("- **Alias/universe hindsight**: today's aliases and membership applied across all 10 years.")
    w("- **PIT submit-date lag**: catalyst knowledge at CT.gov posting granularity.")
    w("- **No composite/confidence gates**: every suppressed fire trades at fixed fraction —")
    w("  the live engine would trade fewer, larger calls.")
    w("- **Unreplayable live triggers**: sentiment/revision/options lanes absent; this is the")
    w("  replayable shadow, not the live book.")
    w("- **R2-A exit-engine overfit risk**: the sleeve descends from V10 (flagged exploratory")
    w("  in round 1); R3-F's plateau map addresses exactly this and is reported below.")
    w("")
    w("Round-3 specific:")
    w("")
    w("- **Multiple comparisons now span THREE rounds: 21 judged variants cumulative**")
    w("  (11 + 5 + 5). The registered-consistency bar mitigates but cannot eliminate")
    w("  selection effects; survivors are HYPOTHESES, never conclusions.")
    w("- **The baseline is itself a survivor-of-survivors**: 30/70 was picked from an H13")
    w("  weight sweep on a backtested sleeve — round 3 measures deltas ON that construction,")
    w("  not the construction's own validity (that is H11/H13's live-shadow job).")
    w("- **R3-C leverage realism is partial**: daily reset at zero transaction cost, financing")
    w("  at BIL + 150 bps accrued daily, no margin calls / intraday liquidation / borrow")
    w("  limits modeled — a levered-ETF-style idealization, optimistic in crashes.")
    w("- **R3-E tilts were FIXED from the 10y per-flag expectancies** (rel_strength strongest,")
    w("  volume_anomaly weakest) — prior evidence, not fit this round; still in-sample to")
    w("  the decade the expectancies came from.")
    w("- **R3-F is a MAP, R3-G is VALIDATION — neither is judged**; any better R3-F cell")
    w("  goes to a round-4 registration, never adopted from this round (contract rule).")
    w("- **Blends are paper constructions**: daily-rebalanced return mixes with zero")
    w("  rebalancing cost between sleeves; a monthly-rebalanced implementation would differ.")
    w("- **Survivors are HYPOTHESES** (TUNING.md law): never direct config changes.")
    w("")
    w("## Protocol")
    w("")
    w("$100k start · daily granularity; blends are daily-rebalanced return mixes of the")
    w("regenerated R2-A sleeve, SPY (adjusted closes) and BIL (total return) on the")
    w("intersection calendar · ALL signals prior-close (200dma gate, TSMOM, 60d vols);")
    w("monthly updates at each month's first trading day, effective from that day's close")
    w("(round-2 momentum-book execution convention) · rf = 0 except where the variant IS")
    w("the cash-yield/leverage mechanic · Sharpe/Sortino annualized √252 · sub-period")
    w("stats on that segment of the same curve. Machinery checks: the R2-A sleeve")
    w("reproduces the stored round-2 end value to $1; the 30/70 baseline reproduces the")
    w("registered H13 numbers; the invested-capture engine reduces exactly to")
    w("run_call_book; L=1.0 reduces exactly to the baseline; the R3-F center cell")
    w("reproduces R2-A. CAGR in the tables is calendar-day annualized (house seg_stats")
    w(f"convention): the baseline reads {bf['cagr']:+.2%} here and {cagr_td:+.2%} under the")
    w("pre-registration's trading-day annualization (its registered +15.89%) — same")
    w("curve, both asserted.")
    w("")
    w("**SURVIVES** = Sharpe AND Calmar beat the 30/70 baseline over the full period AND")
    w("in ≥2 of 3 sub-periods (2016-2019 / 2020-2022 / 2023-2026).")
    w("")
    w("## Full period 2016-01-04 → 2026-08-19")
    w("")
    w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | SURVIVES |")
    w("|---|---|---|---|---|---|---|---|")
    for k in judged + ["BASE", "R2-A", "SPY"]:
        f = stats[k]["full"]
        label = {"BASE": "30/70*", "R2-A": "R2-A*", "SPY": "SPY*"}.get(k, k)
        w(f"| {label} | ${f['end_value']:,.0f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} "
          f"| {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['calmar']:.2f} | {_sv(verdicts[k])} |")
    w("")
    w("_* = baseline / context rows, not round-3 variants. The 30/70 row is the judged")
    w("baseline; R2-A and SPY are its sleeves._")
    w("")
    for name, _, _ in SUB_PERIODS:
        w(f"## Sub-period {name}")
        w("")
        w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | beats 30/70 (Sharpe&Calmar) |")
        w("|---|---|---|---|---|---|---|---|")
        bp = base_stats[name]
        for k in judged + ["BASE", "R2-A", "SPY"]:
            sp = stats[k][name]
            label = {"BASE": "30/70*", "R2-A": "R2-A*", "SPY": "SPY*"}.get(k, k)
            beat = "—" if k == "BASE" else ("yes" if beats(sp, bp) else "no")
            w(f"| {label} | ${sp['end_value']:,.0f} | {sp['cagr']:+.2%} | {sp['max_dd']:.1%} "
              f"| {sp['sharpe']:.2f} | {sp['sortino']:.2f} | {sp['calmar']:.2f} | {beat} |")
        w("")
    # R3-C frontier
    m = meta["R3-C"]["dd_match"]
    w("### R3-C — descriptive leverage frontier (NOT a judged variant)")
    w("")
    w("| L | CAGR | max DD | Sharpe |")
    w("|---|---|---|---|")
    for f in meta["R3-C"]["frontier_grid"]:
        mark = " ←" if f["L"] == m["L"] else ""
        w(f"| {f['L']:.2f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} | {f['sharpe']:.2f}{mark} |")
    w("")
    w(f"DESCRIPTIVE ex-post point, not a recommendation: L = {m['L']:.2f} brings the")
    w(f"levered blend's maxDD ({m['max_dd']:.1%}) closest to SPY's {SPY_MAXDD:.1%}, at")
    w(f"{m['cagr']:+.2%} CAGR / {m['sharpe']:.2f} Sharpe — chosen AFTER seeing the full")
    w("path (the drawdown-matching L is unknowable ex ante) and carrying R3-C's")
    w("idealized-financing caveat.")
    w("")
    w("## R3-F — trail/time-stop robustness MAP (standalone R2-A, not judged)")
    w("")
    w("| trail \\ time stop | 60d | 90d | 120d |")
    w("|---|---|---|---|")
    for m_ in R3F_TRAILS:
        cells = []
        for ts_ in R3F_STOPS:
            c = grid[f"{m_}x{ts_}"]
            cells.append(f"Sharpe {c['sharpe']:.2f} · {c['cagr']:+.1%} · DD {c['max_dd']:.0%}")
        w(f"| {m_}×ATR | " + " | ".join(cells) + " |")
    w("")
    shs = [grid[f"{m_}x{ts_}"]["sharpe"] for m_ in R3F_TRAILS for ts_ in R3F_STOPS]
    w(f"Sharpe range across the 9 cells: {min(shs):.2f}–{max(shs):.2f} (registered cell")
    w(f"3.0×ATR / 90d: {grid['3.0x90']['sharpe']:.2f}). The claim under test is")
    w("plateau-ness — a smooth surface says R2-A is not a knife-edge parameter pick; any")
    w("better cell is a ROUND-4 registration candidate, never adopted from a map.")
    w("")
    c, d_ = boot["cagr_pct"], boot["max_dd_pct"]
    w("## R3-G — stationary block bootstrap of the 30/70 daily returns (validation, not judged)")
    w("")
    w(f"{boot['draws']} draws · geometric block lengths, mean {boot['mean_block_days']}d ·")
    w(f"wrap-around · seed {boot['seed']} · horizon {boot['horizon_years']:.1f}y (the")
    w("actual window) · CAGR calendar-day annualized like the tables:")
    w("")
    w("| percentile | horizon CAGR | max DD |")
    w("|---|---|---|")
    w(f"| 5th | {c['p5']:+.2%} | {d_['p5']:.1%} |")
    w(f"| 50th | {c['p50']:+.2%} | {d_['p50']:.1%} |")
    w(f"| 95th | {c['p95']:+.2%} | {d_['p95']:.1%} |")
    w("")
    w(f"P(CAGR < 0) = {boot['prob_cagr_negative']:.1%}; P(maxDD worse than SPY's "
      f"{SPY_MAXDD:.1%}) = {boot['prob_dd_worse_than_spy']:.1%}. Read: the realized")
    w("path is ONE draw — the baseline's headline numbers sit inside a wide cone, and")
    w("resampling preserves 21-day clustering but NOT regime sequencing (a bootstrap")
    w("cannot manufacture crises longer than its blocks chain together).")
    w("")
    w("## Variant notes")
    w("")
    for k in judged:
        m2 = meta[k]
        extra = ", ".join(
            f"{kk}={vv:,.3f}" if isinstance(vv, float) else f"{kk}={vv}"
            for kk, vv in m2.items()
            if kk not in ("desc", "frontier_grid", "dd_match", "risk_off_dates",
                          "taken_by_flag"))
        w(f"- **{k}** — {m2['desc']}" + (f" ({extra})" if extra else ""))
    w("")
    w("## Ambiguity calls (most conservative reading, per contract)")
    w("")
    w("- The 30/70 baseline is the daily-rebalanced return mix 0.3·r_R2A + 0.7·r_SPY on")
    w("  the R2-A/SPY intersection calendar, compounded from $100k — the H13 construction;")
    w("  its registered CAGR (+15.89%) is trading-day annualized, the tables here use the")
    w("  house calendar-day convention (both reproductions asserted).")
    w("- R3-A applies the R2-D accrual convention inside the blend: the sleeve return")
    w("  becomes r_R2A,t + cash_frac_t·r_BIL,t with cash_frac_t = 1 − the R2-A book's")
    w("  invested MTM fraction as of the PRIOR close (Σ (risk$/risk)·price / equity,")
    w("  clamped [0,1]) — yesterday's idle cash earns today's BIL return, exactly as R2-D.")
    w("- R3-B/R3-D monthly updates: signals from PRIOR-close data at each month's first")
    w("  trading day, new weights/state effective from that day's CLOSE (the round-2")
    w("  momentum-book execution convention) — one conservative day at the old state.")
    w("- R3-B vols = sample stdev of each sleeve's trailing 60 daily returns ending at the")
    w("  prior close; <60 returns available → weight stays 0.30; σ_R2A = 0 (all-cash")
    w("  stretch) → weight at the 0.45 clamp (vol-scaling sends w→∞; the clamp binds).")
    w("- R3-C financing accrues daily on the borrowed fraction at r_BIL,t + 150/252 bps;")
    w("  leverage resets daily (no path-dependent margin); L = 1.0 reduces exactly to the")
    w("  baseline (asserted). The DD-matched L is descriptive/ex-post only.")
    w("- R3-D TSMOM = SPY adjusted close at the last bar BEFORE the rebalance day vs 252")
    w("  SPY bars earlier (prior-close 12-month total return); negative → the 70% leg")
    w("  earns r_BIL until the next monthly check. SPY history reaches 1993, so the")
    w("  lookback never truncates in-window.")
    w("- R3-E re-sizes only: the taken set (200dma gate + cap 10, round-2 selection) is")
    w("  unchanged; risk fraction per call = 1.25% (rel_strength_60d), 0.75%")
    w("  (volume_anomaly), 1.0% otherwise, of the previous close's equity.")
    w("- R3-F rebuilds trailing rows per cell with parameterized copies of the round-1/2")
    w("  graders (the r1/r2 scripts are untouched; the (3.0, 90) cell is asserted")
    w("  row-identical to round 2's build_trailing_rows). Open-at-end rows excluded per")
    w("  the round-1 convention; gate/cap/book mechanics identical across cells.")
    w("- R3-G resamples the BASELINE's daily returns (stationary bootstrap: geometric")
    w("  block lengths mean 21d, wrap-around at the series end, fixed seed), horizon =")
    w("  the actual window length; percentiles are empirical (no interpolation).")
    w("")
    w("## Verdict")
    w("")
    survivors = [k for k in judged if verdicts[k]]
    if survivors:
        w(f"Survivors under the round-3 bar (beat the 30/70 baseline on Sharpe AND Calmar,")
        w(f"full period and ≥2/3 sub-periods): **{', '.join(survivors)}**. Per the contract")
        w("these become HYPOTHESES.md entries / TUNING proposals — never direct config")
        w("changes.")
    else:
        w("**No round-3 variant survived** the pre-registered bar (Sharpe AND Calmar beat")
        w("the 30/70 baseline, full period and ≥2/3 sub-periods). Per the contract nothing")
        w("is promoted; refinements require a round-4 registration.")
    w("")
    w("R3-F (map) and R3-G (validation) are not judged: the map's reading is the Sharpe")
    w("plateau above; the bootstrap's reading is the cone around the baseline's headline")
    w("numbers. Counter-agent review before any of this is acted on, per standing")
    w("convention.")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
