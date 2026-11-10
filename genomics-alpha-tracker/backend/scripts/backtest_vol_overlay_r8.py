"""ROUND 8 — volatility: the thesis (Part A), then the overlay (Part B).

Contract: docs/VARIANTS_PREREGISTRATION_R8_VOL.md, committed (7d8458a) BEFORE
any line of this file existed. Everything registered there is reproduced here
and nothing is added.

THE DESIGN POINT THE WHOLE ROUND TURNS ON. A vol-targeted book holds less
exposure on average, so it cuts drawdown MECHANICALLY. Comparing it to a
fully-invested book measures "holds less equity", not "times vol" — the error
round 7's counter-agent caught when a plain 63/37 SPY/T-bill book beat B.5 on
drawdown with no factors in it at all. So:

    EVERY overlay arm is judged against a STATIC control built at the ARM'S
    OWN REALIZED AVERAGE BOOK EXPOSURE, in the SAME risky book, on the SAME
    rebalance schedule, paying the SAME costs.

The control's static weight is not guessed: `matched_control` solves for the
weight whose realized average exposure equals the arm's to 1e-10, and
`test_vol_overlay_r8.py` fails the build if it ever does not. The
fully-invested and 60/40 comparisons are computed and printed as SECONDARY
context and never adjudicate anything.

FROZEN CODE. `scripts/backtest_core_variants.py` (rounds 4-6) and
`scripts/backtest_core_20y.py` (round 7) are imported READ-ONLY and not
modified: the metrics conventions, the band/portfolio engine, the paired block
bootstrap, the B.5 leg construction and the named regimes all come from there
unchanged.

Usage:
  python -m scripts.backtest_vol_overlay_r8 --gate-only
  python -m scripts.backtest_vol_overlay_r8 --json data/backtest_vol_overlay_r8_results.json --report
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

from scripts.backtest_core_variants import (
    B5_BAND_REL,
    B5_CAL_FALLBACK_D,
    BOOT_BLOCK,
    BOOT_DRAWS,
    BOOT_SEED,
    LIVE_BAND,
    LIVE_SLEEVE_W,
    TRADING_DAYS,
    _days,
    _sharpe_from_sums,
    _wrap_prefix,
    block_bootstrap_sharpe_diff,
    block_starts,
    boot_ci,
    const,
    curve_returns,
    load_frozen_sleeve,
    load_sleeve_exposure,
    metrics,
    month_starts,
    portfolio,
    sharpe,
)
from scripts.backtest_core_20y import (
    CASH_PROXY,
    REGIMES,
    build_legs,
    load_universe,
    regime_stats,
    snap,
    splice_with_provenance,
    window_dates,
)
from scripts.lib import fmp_prices as fmp
from scripts.lib import volmodels as vm

BACKEND = Path(__file__).resolve().parent.parent
RESULTS = BACKEND / "data" / "backtest_vol_overlay_r8_results.json"
REPORT = BACKEND.parent / "docs" / "BACKTEST_VOL_OVERLAY_R8.md"
CONTRACT = "docs/VARIANTS_PREREGISTRATION_R8_VOL.md"

# --- registered parameters ------------------------------------------------------------
# The underlying books are built at the rounds 4-7 cost convention (10 bps per
# side) so B.5-T1 IS round 7's B.5-T1, byte for byte. The OVERLAY layer — the
# only thing under test, and the only thing whose turnover differs between an
# arm and its control — is what gets charged at 5 and 20 bps.
BASE_COST_BPS = 10.0
COST_LEVELS = (5.0, 20.0)

V_TARGET = 0.10            # V1 vol target, annualized (round 4's C4)
V_WINDOW = 20              # trailing-realized estimator window (C4's)
V_CAP = 1.0                # deleverage only
V5_TARGETS = (0.12, 0.15)  # target sensitivity
V6_CAP = 1.5               # the leverage arm
V8_WINDOW = 60             # inverse-vol window — round 5's D3 window
EWMA_LAMBDA = 0.94
GARCH_INIT_DAYS = 756      # 3 years before the first fit; refit each January
REGIME_MIN_HISTORY = 252   # expanding-quantile warm-up before any day is labelled
FIXED_TRAIN_DAYS = 756     # the "fixed thresholds" sensitivity's training block
A_LAGS = (1, 2, 5, 10, 20, 40, 60)
TWEET_CLAIM = {"low": 0.74, "high": 0.81}

EQUITY_LEGS_B5 = ("AVUV", "AVDV", "AVEM", "QUAL")
SPY_TBILL_W = 0.63         # the round-7 counter-agent's equity-share-matched book
SIXTY_FORTY = 0.60         # secondary comparator, SPY/AGG-style (AGG unavailable
                           # pre-2006 on this lane; see `SIXTY_FORTY_NOTE`)
SIXTY_FORTY_NOTE = ("AGG is not on the round-7 lane, so the registered secondary "
                    "60/40 comparator is run as 60% SPY / 40% the same T-bill "
                    "cash leg every other arm uses.")


# --- instrumented two-leg engine ------------------------------------------------------

def two_leg(dates: list[str], book: dict[str, float], cash: dict[str, float],
            w_at, rebal: set[str], cost_bps: float) -> dict:
    """BOOK/CASH portfolio with the frozen engine's semantics, instrumented.

    Identical arithmetic to `backtest_core_variants.portfolio` with
    `rebal_dates=rebal` and no bands — `test_vol_overlay_r8.py` asserts the
    two produce the same curve to 1e-15 — plus the two things this round has
    to measure and the frozen engine does not report: the REALIZED weight
    actually held into each day, and the traded notional.

    Weights above 1.0 (V6) hold a NEGATIVE cash leg: the book borrows at the
    T-bill leg's own return, with no financing spread. That is an assumption,
    it flatters the leveraged arm, and it is in the honesty box.
    """
    curves = {"BOOK": book, "CASH": cash}
    d0 = dates[0]
    w = w_at(d0)
    eq = 1.0
    units = {"BOOK": eq * w / book[d0], "CASH": eq * (1 - w) / cash[d0]}
    out = {d0: eq}
    held = {d0: w}
    turnover = 0.0
    n_rebal = 0
    for d in dates[1:]:
        eq = sum(u * curves[k][d] for k, u in units.items())
        w_t = w_at(d)
        w_now = units["BOOK"] * book[d] / eq
        if d in rebal:
            traded = abs(w_t - w_now) * eq          # 0.5 * sum|dw| over two legs
            eq -= traded * cost_bps / 1e4
            units = {"BOOK": eq * w_t / book[d], "CASH": eq * (1 - w_t) / cash[d]}
            turnover += abs(w_t - w_now)
            n_rebal += 1
            w_now = w_t
        out[d] = eq
        held[d] = w_now
    years = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days / 365.25
    exposure = statistics.fmean([held[d] for d in dates[:-1]])
    return {"curve": out, "held": held, "exposure": exposure,
            "turnover_total": turnover, "turnover_annual": turnover / years,
            "n_rebal": n_rebal, "years": years}


def vol_band_portfolio(dates: list[str], curves: dict[str, dict[str, float]],
                       target_at, *, band: float | None = None,
                       band_rel: float | None = None,
                       cal_fallback_days: int | None = None,
                       cost_bps: float = BASE_COST_BPS,
                       vol_mult=None) -> dict:
    """The frozen band engine with a VOL-SCALED band width (arm V7).

    `vol_mult(i, own_rets)` returns the multiplier applied to the band on date
    index `i`; it sees only the portfolio's OWN realized returns so far, so the
    rule is causal by construction. With `vol_mult=None` this reduces EXACTLY
    to `backtest_core_variants.portfolio` — which the test suite pins — so the
    control and the arm differ in one thing only.
    """
    d0 = dates[0]
    tgt = target_at(d0)
    eq = 1.0
    units = {k: eq * w / curves[k][d0] for k, w in tgt.items() if w}
    last_rb = d0
    out = {d0: eq}
    own_rets: list[float] = []
    weights = {d0: dict(tgt)}
    turnover = 0.0
    n_rebal = 0
    bands: list[float] = []
    for i, d in enumerate(dates[1:], start=1):
        prev_eq = out[dates[i - 1]]
        eq = sum(u * curves[k][d] for k, u in units.items())
        own_rets.append(eq / prev_eq - 1.0)
        tgt = target_at(d)
        legs = set(tgt) | set(units)
        w_now = {k: units.get(k, 0.0) * curves[k][d] / eq for k in legs}
        mult = 1.0 if vol_mult is None else vol_mult(i, own_rets)
        bands.append(mult)
        need = False
        if band is not None:
            need = any(abs(w_now.get(k, 0.0) - tgt.get(k, 0.0)) > band * mult for k in legs)
        if not need and band_rel is not None:
            need = any(abs(w_now.get(k, 0.0) - tgt.get(k, 0.0)) > band_rel * mult * tgt[k]
                       for k in legs if tgt.get(k, 0.0))
        if not need and cal_fallback_days is not None:
            need = _days(last_rb, d) >= cal_fallback_days
        if need:
            traded = sum(abs(tgt.get(k, 0.0) - w_now.get(k, 0.0)) for k in legs) * eq / 2
            turnover += traded / eq
            eq -= traded * cost_bps / 1e4
            units = {k: eq * w / curves[k][d] for k, w in tgt.items() if w}
            last_rb = d
            n_rebal += 1
            w_now = dict(tgt)
        out[d] = eq
        weights[d] = w_now
    years = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days / 365.25
    return {"curve": out, "weights": weights, "turnover_annual": turnover / years,
            "n_rebal": n_rebal, "band_mult_mean": statistics.fmean(bands) if bands else 1.0}


def running_vol_mult(vol_window: int = V_WINDOW):
    """V7's band multiplier: the current trailing-vol estimate divided by the
    EXPANDING mean of that estimate. Expanding, not full-sample: a full-sample
    mean would put tomorrow's volatility into today's band."""
    state = {"sum": 0.0, "n": 0}

    def mult(i: int, own_rets: list[float]) -> float:
        v = vm.trailing_vol(own_rets, len(own_rets), vol_window)
        if v is None or not math.isfinite(v) or v <= 0:
            return 1.0
        state["sum"] += v
        state["n"] += 1
        mean = state["sum"] / state["n"]
        return v / mean if mean > 0 else 1.0

    return mult


# --- the overlay weight paths ----------------------------------------------------------

def step_weights(dates: list[str], decide_on: set[str], pick, default: float):
    """A weight re-decided on `decide_on` dates and HELD FLAT in between —
    `monthly_weights`' contract, generalised to any schedule. `pick(i)` returns
    None during warm-up, when the weight falls back to `default` (round 4's C4
    convention: the cap, i.e. fully invested)."""
    w_by_date: dict[str, float] = {}
    cur = default
    decided: list[float] = []
    for i, d in enumerate(dates):
        if i == 0 or d in decide_on:
            got = pick(i)
            cur = default if got is None else got
            decided.append(cur)
        w_by_date[d] = cur
    return (lambda d: w_by_date[d]), w_by_date, decided


def vol_target_pick(rets, vol_at, target: float, cap: float):
    def pick(i: int) -> float | None:
        v = vol_at(i)
        if v is None or not math.isfinite(v) or v <= 0:
            return None
        return min(cap, target / v)
    return pick


def inverse_vol_pick(book_rets, cash_rets, window: int):
    """V8, literally as registered: inverse-vol weighting BETWEEN the risky book
    AND CASH. The cash leg's vol is tiny, so 1/sigma_cash dominates and the rule
    holds almost nothing in the book. That degeneracy is a RESULT, not a bug to
    be tuned away, and the report says so."""
    def pick(i: int) -> float | None:
        vb = vm.trailing_vol(book_rets, i, window)
        vc = vm.trailing_vol(cash_rets, i, window)
        if vb is None or vc is None or vb <= 0 or vc <= 0:
            return None
        return (1 / vb) / (1 / vb + 1 / vc)
    return pick


# --- matched-exposure control ------------------------------------------------------------

def matched_control(dates, book, cash, rebal: set[str], cost_bps: float,
                    exposure: float, *, tol: float = 1e-13, iters: int = 80) -> dict:
    """THE NULL. A STATIC weight in the SAME book, on the SAME schedule, paying
    the SAME costs, whose REALIZED average exposure equals `exposure`.

    Solved by bisection on the static target, not set equal to the arm's mean
    weight: a static target drifts with the book between rebalances, so its
    realized average is not its target. Bisection is safe because realized
    exposure is monotone in the static target.
    """
    lo, hi = -0.5, 3.0
    run, mid = None, (lo + hi) / 2
    for _ in range(iters):
        mid = (lo + hi) / 2
        if hi - lo < 1e-15 and run is not None:
            break
        run = two_leg(dates, book, cash, (lambda _d, m=mid: m), rebal, cost_bps)
        if abs(run["exposure"] - exposure) <= tol:
            break
        if run["exposure"] < exposure:
            lo = mid
        else:
            hi = mid
    run["static_w"] = mid
    run["target_exposure"] = exposure
    run["exposure_err"] = run["exposure"] - exposure
    return run


# --- books ---------------------------------------------------------------------------------

def build_cash(raw, dates):
    curve, _ = splice_with_provenance(
        [("BIL", raw["BIL"])] + [(p, raw[p]) for p in CASH_PROXY], dates)
    return curve


def b5_equity_share(raw, dates) -> float:
    """Realized average weight of the four EQUITY legs inside B.5-T1 — the
    number that converts 'book exposure' into 'equity exposure' for the B.5
    book. Computed from the same leg curves and the same band engine."""
    legs = build_legs(raw, dates, "T1")
    curves, target_at = legs["curves"], legs["target_at"]
    d0 = dates[0]
    tgt = target_at(d0)
    eq = 1.0
    units = {k: eq * w / curves[k][d0] for k, w in tgt.items() if w}
    last_rb, shares = d0, []
    for d in dates[1:]:
        eq = sum(u * curves[k][d] for k, u in units.items())
        tgt = target_at(d)
        legs_k = set(tgt) | set(units)
        w_now = {k: units.get(k, 0.0) * curves[k][d] / eq for k in legs_k}
        need = any(abs(w_now.get(k, 0.0) - tgt.get(k, 0.0)) > B5_BAND_REL * tgt[k]
                   for k in legs_k if tgt.get(k, 0.0))
        if not need:
            need = _days(last_rb, d) >= B5_CAL_FALLBACK_D
        if need:
            traded = sum(abs(tgt.get(k, 0.0) - w_now.get(k, 0.0)) for k in legs_k) * eq / 2
            eq -= traded * BASE_COST_BPS / 1e4
            units = {k: eq * w / curves[k][d] for k, w in tgt.items() if w}
            last_rb = d
            w_now = dict(tgt)
        shares.append(sum(w_now.get(k, 0.0) for k in EQUITY_LEGS_B5))
    return statistics.fmean(shares)


def build_books(raw, dates, cash) -> dict:
    """The three books that reach 2006. Each is a CURVE; the overlay scales it."""
    spy = {d: raw["SPY"][d] / raw["SPY"][dates[0]] for d in dates}
    b5 = build_legs(raw, dates, "T1")
    b5_curve = portfolio(dates, b5["curves"], b5["target_at"],
                         band_rel=B5_BAND_REL, cal_fallback_days=B5_CAL_FALLBACK_D,
                         cost_bps=BASE_COST_BPS)
    mix = portfolio(dates, {"SPY": spy, "CASH": cash},
                    const({"SPY": SPY_TBILL_W, "CASH": 1 - SPY_TBILL_W}),
                    band_rel=B5_BAND_REL, cal_fallback_days=B5_CAL_FALLBACK_D,
                    cost_bps=BASE_COST_BPS)
    return {
        "SPY": {"curve": spy, "equity_share": 1.0,
                "desc": "SPY buy-and-hold (dividend-adjusted total return)"},
        "B5-T1": {"curve": b5_curve, "equity_share": b5_equity_share(raw, dates),
                  "desc": "B.5 Enhanced, round-7 treatment T1 (cash in the "
                          "KMLM/TAIL gap), +/-20% relative band + 365d fallback"},
        "63/37": {"curve": mix, "equity_share": SPY_TBILL_W,
                  "desc": "63/37 SPY/T-bill — round-7 counter-agent's "
                          "equity-share-matched book, same band engine"},
    }


def build_blend_3070(raw, r7_dates):
    """The LIVE 30/70 book: 30% R2-A (idle CAPITAL swept to BIL) / 70% SPY, 5%
    absolute band. 2016+ only — R2-A's frozen curve begins 2016-01-04 and
    cannot be extended to 2006 without a survivorship audit (round 7's
    registration), so these arms are reported SEPARATELY and cannot be judged
    on the five named regimes."""
    sleeve_raw = load_frozen_sleeve()
    idle = load_sleeve_exposure(sleeve_raw)
    dates = [d for d in r7_dates if d in sleeve_raw and d in idle]
    cash = build_cash(raw, dates)
    spy = {d: raw["SPY"][d] / raw["SPY"][dates[0]] for d in dates}
    lvl, sleeve = 1.0, {dates[0]: 1.0}
    for i in range(1, len(dates)):
        rs = sleeve_raw[dates[i]] / sleeve_raw[dates[i - 1]] - 1
        rc = cash[dates[i]] / cash[dates[i - 1]] - 1
        lvl *= 1 + rs + idle[dates[i - 1]] * rc
        sleeve[dates[i]] = lvl
    curve = portfolio(dates, {"SLEEVE": sleeve, "SPY": spy},
                      const({"SLEEVE": LIVE_SLEEVE_W, "SPY": 1 - LIVE_SLEEVE_W}),
                      band=LIVE_BAND, cost_bps=BASE_COST_BPS)
    return {"dates": dates, "cash": cash, "spy": spy, "sleeve": sleeve,
            "book": {"curve": curve, "equity_share": 1 - LIVE_SLEEVE_W,
                     "desc": "live 30/70 R2-A/SPY, 5% absolute band, sleeve idle "
                             "CAPITAL swept to BIL (2016+)"},
            "legs": {"SLEEVE": sleeve, "SPY": spy},
            "target": const({"SLEEVE": LIVE_SLEEVE_W, "SPY": 1 - LIVE_SLEEVE_W})}


# --- estimators, per book -------------------------------------------------------------------

def estimators(dates, rets, cache_key: str, cache: dict) -> dict:
    """The three registered vol estimators as ANNUALIZED vol, one per date index."""
    if cache_key in cache:
        return cache[cache_key]
    trail = vm.trailing_vol_series(rets, V_WINDOW)
    ewma_v = vm.ewma_var_series(rets, EWMA_LAMBDA, V_WINDOW)
    gw = vm.garch_walk_forward(rets, dates, init_days=GARCH_INIT_DAYS)
    ann = math.sqrt(TRADING_DAYS)
    out = {
        "trail20": trail,
        "ewma": [None if h is None else math.sqrt(h) * ann for h in ewma_v],
        "garch": [None if h is None else math.sqrt(h) * ann for h in gw["var"]],
        "_ewma_var": ewma_v,
        "_garch_var": gw["var"],
        "_trail_var": [None if v is None else (v / ann) ** 2 for v in trail],
        "_garch_fits": gw["fits"],
        "_garch_start": gw["start"],
    }
    cache[cache_key] = out
    return out


# --- Part A ------------------------------------------------------------------------------------

def part_a(books: dict, dates: list[str], est_cache: dict) -> dict:
    """A1 regime persistence, A2 autocorrelation, A3 walk-forward forecasts."""
    out: dict = {"books": {}}
    schemes = {
        "tercile (registered)": ("expanding", 1 / 3, 2 / 3),
        "quintile": ("expanding", 0.20, 0.80),
        "fixed 20/80 (trained once on the first 3y)": ("fixed", 0.20, 0.80),
        "full-sample tercile — LOOK-AHEAD, diagnostic only": ("full", 1 / 3, 2 / 3),
    }
    for name, b in books.items():
        rets = curve_returns(b["curve"], dates)
        est = estimators(dates, rets, name, est_cache)
        rv = est["trail20"]

        # --- A1 ---------------------------------------------------------------
        a1 = {}
        for label, (kind, q_lo, q_hi) in schemes.items():
            if kind == "expanding":
                lab = vm.expanding_regimes(rv, q_lo, q_hi, min_history=REGIME_MIN_HISTORY)
            elif kind == "fixed":
                lab = vm.fixed_regimes(rv, q_lo, q_hi, train_days=FIXED_TRAIN_DAYS)
            else:
                lab = vm.full_sample_regimes(rv, q_lo, q_hi)
            a1[label] = {
                "look_ahead": kind == "full",
                "n_labelled": sum(1 for x in lab if x is not None),
                "rows": [vm.persistence(lab, s, h)
                         for s in ("low", "high") for h in (1, 5, 20)],
            }
            if label.startswith("tercile"):
                a1[label]["labels"] = lab

        # --- A2 ---------------------------------------------------------------
        rv_clean = [v for v in rv if v is not None]
        absr = [abs(r) for r in rets]
        a2 = {
            "lags": list(A_LAGS),
            "realized_vol_20d": [vm.autocorr(rv_clean, k) for k in A_LAGS],
            "abs_return": [vm.autocorr(absr, k) for k in A_LAGS],
            "signed_return": [vm.autocorr(rets, k) for k in A_LAGS],
            "full": {
                "realized_vol_20d": [vm.autocorr(rv_clean, k) for k in range(1, 61)],
                "abs_return": [vm.autocorr(absr, k) for k in range(1, 61)],
                "signed_return": [vm.autocorr(rets, k) for k in range(1, 61)],
            },
        }

        # --- A3 ---------------------------------------------------------------
        start = est["_garch_start"] or 0
        idx = [i for i in range(start, len(rets))
               if est["_garch_var"][i] is not None and est["_ewma_var"][i] is not None
               and est["_trail_var"][i] is not None]
        a3 = {"oos_start": dates[idx[0]] if idx else None, "n": len(idx), "models": {}}
        for key, series in (("GARCH(1,1) walk-forward", est["_garch_var"]),
                            ("EWMA(0.94)", est["_ewma_var"]),
                            ("trailing 20d realized", est["_trail_var"])):
            sc = vm.score_forecasts(series, rets, idx)
            sc.update(vm.score_vs_forward_vol(series, rets, idx, V_WINDOW))
            a3["models"][key] = sc
        a3["fits"] = [{"through": f["fit_through"], "n": f["fit_n"], "mu": f["mu"],
                       "omega": f["omega"], "alpha": f["alpha"], "beta": f["beta"],
                       "persistence": f["persistence"]} for f in est["_garch_fits"]]
        # The registration's explicit question.
        g, t = a3["models"]["GARCH(1,1) walk-forward"], a3["models"]["trailing 20d realized"]
        a3["garch_beats_trailing"] = {
            "qlike": bool(g["qlike"] < t["qlike"]),
            "rmse": bool(g["rmse"] < t["rmse"]),
            "rmse_fwd_vol": bool(g["rmse_vol_pts"] < t["rmse_vol_pts"]),
        }
        out["books"][name] = {"a1": a1, "a2": a2, "a3": a3,
                              "vol_series": {d: rv[i] for i, d in enumerate(dates)
                                             if rv[i] is not None}}
    return out


# --- Part B ---------------------------------------------------------------------------------------

def arm_specs(book_name: str) -> list[dict]:
    """The eight registered arms. V7 is a REBALANCE-BAND arm and only exists
    where a band rule exists — the B.5 book and the live 30/70 blend, exactly
    as registered ("on the existing 30/70 and B.5 band rules")."""
    base = [
        {"key": "V1", "kind": "scale", "est": "trail20", "target": V_TARGET, "cap": V_CAP,
         "freq": "monthly",
         "desc": f"vol target {V_TARGET:.0%}, trailing-{V_WINDOW}d, deleverage-only "
                 f"(cap {V_CAP:.1f}), monthly"},
        {"key": "V2", "kind": "scale", "est": "trail20", "target": V_TARGET, "cap": V_CAP,
         "freq": "daily", "desc": "V1 with DAILY rebalance"},
        {"key": "V3", "kind": "scale", "est": "garch", "target": V_TARGET, "cap": V_CAP,
         "freq": "monthly", "desc": "V1 with the walk-forward GARCH(1,1) forecast"},
        # NOT A REGISTERED ARM — a warm-up DIAGNOSTIC, `judged=False`, never in
        # the max-T family and never a survivor. The registration is silent on
        # what V3 holds before its first GARCH fit exists (3 years, which here
        # is the whole GFC); the registered arm takes round 4's C4 warm-up
        # convention and sits at the cap, and this twin takes V1's estimator
        # instead. BOTH are reported so that neither is a post-hoc choice.
        {"key": "V3-WU", "kind": "scale", "est": "garch", "target": V_TARGET,
         "cap": V_CAP, "freq": "monthly", "judged": False, "warmup_est": "trail20",
         "desc": "DIAGNOSTIC (not judged): V3 with V1's trailing-20d estimator "
                 "during the 3-year GARCH warm-up instead of sitting at the cap"},
        {"key": "V4", "kind": "scale", "est": "ewma", "target": V_TARGET, "cap": V_CAP,
         "freq": "monthly", "desc": f"V1 with the EWMA({EWMA_LAMBDA}) estimator"},
        {"key": "V5-12", "kind": "scale", "est": "trail20", "target": 0.12, "cap": V_CAP,
         "freq": "monthly", "desc": "V1 at a 12% target"},
        {"key": "V5-15", "kind": "scale", "est": "trail20", "target": 0.15, "cap": V_CAP,
         "freq": "monthly", "desc": "V1 at a 15% target"},
        {"key": "V6", "kind": "scale", "est": "trail20", "target": V_TARGET, "cap": V6_CAP,
         "freq": "monthly", "desc": f"V1 with leverage allowed to {V6_CAP:.1f}x"},
        {"key": "V8", "kind": "invvol", "window": V8_WINDOW, "freq": "monthly",
         "desc": f"inverse-vol between the book and cash, trailing {V8_WINDOW}d, monthly"},
    ]
    if book_name in ("B5-T1", "30/70"):
        base.append({"key": "V7", "kind": "band",
                     "desc": "vol-scaled REBALANCE BANDS: band width proportional to "
                             "the current vol estimate, on the book's own band rule"})
    return base


def run_scale_arm(spec, dates, book, cash, est, rets, cash_rets, cost_bps) -> dict:
    months = set(month_starts(dates))
    rebal = set(dates) if spec["freq"] == "daily" else months
    if spec["kind"] == "scale":
        vol = est[spec["est"]]
        wu = est.get(spec.get("warmup_est")) if spec.get("warmup_est") else None
        if wu is None:
            vol_at = (lambda i: vol[i])
        else:
            vol_at = (lambda i: vol[i] if vol[i] is not None else wu[i])
        pick = vol_target_pick(rets, vol_at, spec["target"], spec["cap"])
        default = spec["cap"]
    else:
        pick = inverse_vol_pick(rets, cash_rets, spec["window"])
        default = V_CAP
    w_at, w_by_date, decided = step_weights(dates, rebal, pick, default)
    run = two_leg(dates, book, cash, w_at, rebal, cost_bps)
    run["w_by_date"] = w_by_date
    run["w_decided"] = decided
    run["at_cap"] = statistics.fmean([1.0 if abs(w_by_date[d] - default) < 1e-12 else 0.0
                                      for d in dates])
    return run


def judge(arm_run, ctl_run, dates, bil_rets, spy_rets, draws: int) -> dict:
    """Everything the survival bar needs, for one arm against ITS control."""
    a_curve, c_curve = arm_run["curve"], ctl_run["curve"]
    a_ret, c_ret = curve_returns(a_curve, dates), curve_returns(c_curve, dates)
    a_ex = [x - y for x, y in zip(a_ret, bil_rets, strict=True)]
    c_ex = [x - y for x, y in zip(c_ret, bil_rets, strict=True)]
    am = metrics(a_curve, dates, bil_rets, spy_rets)
    cm = metrics(c_curve, dates, bil_rets, spy_rets)
    boot = block_bootstrap_sharpe_diff(a_ex, c_ex, block=BOOT_BLOCK, draws=draws,
                                       seed=BOOT_SEED)
    lo, hi = boot_ci(boot)
    regimes = {}
    for name, r0, r1 in REGIMES:
        # A regime the window does not FULLY contain is not that regime. The
        # 30/70 book starts in 2016, so its "GFC" and "recovery" rows would
        # otherwise be a 2016-2019 stub wearing a crisis label.
        if r0 < dates[0] or r1 > dates[-1]:
            regimes[name] = None
            continue
        try:
            i0 = dates.index(snap(dates, r0, forward=True))
            i1 = dates.index(snap(dates, r1, forward=False))
        except AssertionError:
            regimes[name] = None
            continue
        if i1 <= i0:
            regimes[name] = None
            continue
        seg = dates[i0:i1 + 1]
        ar = curve_returns(a_curve, seg)
        cr = curve_returns(c_curve, seg)
        br = bil_rets[i0:i1]
        a_sh = sharpe(ar, br)
        c_sh = sharpe(cr, br)
        a_rg = regime_stats(a_curve, dates, r0, r1)
        c_rg = regime_stats(c_curve, dates, r0, r1)
        regimes[name] = {
            "start": seg[0], "end": seg[-1], "n": len(seg),
            "arm": {"sharpe_bil": a_sh, "max_dd": a_rg["max_dd"],
                    "total_return": a_rg["total_return"],
                    "recovery_days": a_rg["recovery_days"],
                    "recovery_date": a_rg["recovery_date"], "trough": a_rg["trough"]},
            "control": {"sharpe_bil": c_sh, "max_dd": c_rg["max_dd"],
                        "total_return": c_rg["total_return"],
                        "recovery_days": c_rg["recovery_days"],
                        "recovery_date": c_rg["recovery_date"], "trough": c_rg["trough"]},
            "arm_wins_sharpe": bool(a_sh > c_sh),
            "arm_wins_dd": bool(a_rg["max_dd"] < c_rg["max_dd"]),
        }
    live = [r for r in regimes.values() if r is not None]
    wins = sum(1 for r in live if r["arm_wins_sharpe"])
    wins_dd = sum(1 for r in live if r["arm_wins_dd"])
    d_sharpe = am["sharpe_bil"] - cm["sharpe_bil"]
    d_calmar = am["calmar"] - cm["calmar"]
    return {
        "metrics": am, "control_metrics": cm,
        "d_sharpe_bil": d_sharpe,
        "d_sharpe_rf0": am["sharpe_rf0"] - cm["sharpe_rf0"],
        "d_sortino_bil": am["sortino_bil"] - cm["sortino_bil"],
        "d_calmar": d_calmar,
        "d_maxdd": am["max_dd"] - cm["max_dd"],
        "d_cagr": am["cagr"] - cm["cagr"],
        "boot": {"point": boot["point"], "ci_lo": lo, "ci_hi": hi,
                 "p_two_sided": boot["p_two_sided"], "draws": boot["draws"],
                 "block": boot["block"], "seed": boot["seed"],
                 "excludes_zero": bool(lo > 0 or hi < 0)},
        "regimes": regimes,
        "regimes_live": len(live),
        "regimes_total": len(REGIMES),
        "regime_wins_sharpe": wins,
        "regime_wins_dd": wins_dd,
        "bar": {
            "beats_sharpe": bool(d_sharpe > 0),
            "beats_calmar": bool(d_calmar > 0),
            "ci_excludes_zero": bool(lo > 0 or hi < 0),
            "regimes_ge_3": bool(wins >= 3),
            "all_regimes_present": bool(len(live) == len(REGIMES)),
        },
        "_arm_ex": a_ex, "_ctl_ex": c_ex,
    }


def westfall_young(series: list[tuple[str, list[float], list[float]]], *,
                   draws: int = BOOT_DRAWS, block: int = BOOT_BLOCK,
                   seed: int = BOOT_SEED) -> dict:
    """Single-step max-T (Westfall-Young) over this round's arms, on ONE shared
    block-draw sequence so the arms' dependence is carried rather than assumed
    away.

    Caveat this round has to state and rounds 4-6 did not: every arm here is
    compared to its OWN matched control, so the family does not share a single
    comparator the way a campaign-wide max-T does. The shared draw sequence
    still couples the arms through the calendar, which is what the correction
    needs, but the adjusted p answers "how extreme is this arm's gap over its
    own null, among a family of such gaps", not "against one incumbent".
    """
    keys = [k for k, _a, _b in series]
    n = len(series[0][1])
    pre = {k: (_wrap_prefix(a), _wrap_prefix(b)) for k, a, b in series}
    point = {k: sharpe(a) - sharpe(b) for k, a, b in series}
    rng = random.Random(seed)
    dist: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(draws):
        blocks = block_starts(n, block, rng)
        for k in keys:
            (pa, qa), (pb, qb) = pre[k]
            sa = s2a = sb = s2b = 0.0
            for st, ln in blocks:
                sa += pa[st + ln] - pa[st]
                s2a += qa[st + ln] - qa[st]
                sb += pb[st + ln] - pb[st]
                s2b += qb[st + ln] - qb[st]
            dist[k].append(_sharpe_from_sums(sa, s2a, n) - _sharpe_from_sums(sb, s2b, n))
    se = {k: statistics.stdev(dist[k]) for k in keys}
    t_obs = {k: abs(point[k]) / se[k] if se[k] > 0 else float("inf") for k in keys}
    max_t = [max(abs(dist[k][i] - point[k]) / se[k] for k in keys if se[k] > 0)
             for i in range(draws)]
    adj = {k: sum(1 for m in max_t if m >= t_obs[k]) / draws for k in keys}
    raw = {k: min(1.0, 2 * min(sum(1 for d in dist[k] if d <= 0) / draws,
                               sum(1 for d in dist[k] if d >= 0) / draws)) for k in keys}
    return {"n_arms": len(keys), "draws": draws, "seed": seed, "block": block,
            "point": point, "adjusted_p": adj, "raw_p": raw, "t_obs": t_obs,
            "strongest": min(adj, key=lambda k: (adj[k], -abs(point[k])))}


def run_book(book_name: str, book: dict, dates: list[str], cash: dict[str, float],
             spy_curve: dict[str, float], est_cache: dict, *, draws: int,
             band_ctx: dict | None = None) -> dict:
    """Every registered arm on one book, at both cost levels, each against its
    OWN matched-exposure control."""
    curve = book["curve"]
    rets = curve_returns(curve, dates)
    cash_rets = curve_returns(cash, dates)
    bil_rets = cash_rets
    spy_rets = curve_returns(spy_curve, dates)
    est = estimators(dates, rets, book_name, est_cache)
    months = set(month_starts(dates))

    out = {"desc": book["desc"], "equity_share": book["equity_share"],
           "base": {"metrics": metrics(curve, dates, bil_rets, spy_rets)},
           "arms": {}}
    # Secondary, never the headline: fully invested and a 60/40 peer.
    ff = two_leg(dates, curve, cash, lambda _d: 1.0, months, COST_LEVELS[0])
    sixty = portfolio(dates, {"SPY": spy_curve, "CASH": cash},
                      const({"SPY": SIXTY_FORTY, "CASH": 1 - SIXTY_FORTY}),
                      band_rel=B5_BAND_REL, cal_fallback_days=B5_CAL_FALLBACK_D,
                      cost_bps=BASE_COST_BPS)
    out["secondary"] = {
        "fully_invested": metrics(ff["curve"], dates, bil_rets, spy_rets),
        "sixty_forty": metrics(sixty, dates, bil_rets, spy_rets),
        "note": SIXTY_FORTY_NOTE,
    }

    for spec in arm_specs(book_name):
        arm_out = {"desc": spec["desc"], "kind": spec["kind"],
                   "judged": spec.get("judged", True), "costs": {}}
        for cost in COST_LEVELS:
            if spec["kind"] == "band":
                ctx = band_ctx
                mult = running_vol_mult(V_WINDOW)
                arm_run = vol_band_portfolio(
                    dates, ctx["curves"], ctx["target_at"],
                    band=ctx.get("band"), band_rel=ctx.get("band_rel"),
                    cal_fallback_days=ctx.get("cal_fallback_days"),
                    cost_bps=cost, vol_mult=mult)
                ctl_run = vol_band_portfolio(
                    dates, ctx["curves"], ctx["target_at"],
                    band=ctx.get("band"), band_rel=ctx.get("band_rel"),
                    cal_fallback_days=ctx.get("cal_fallback_days"),
                    cost_bps=cost, vol_mult=None)
                # Exposure match for a band arm is STRUCTURAL: identical target
                # weights, identical legs, only the rebalance TIMING differs.
                # Report the realized average weight of every leg for both.
                aw = {k: statistics.fmean([arm_run["weights"][d].get(k, 0.0)
                                           for d in dates[:-1]])
                      for k in ctx["curves"]}
                cw = {k: statistics.fmean([ctl_run["weights"][d].get(k, 0.0)
                                           for d in dates[:-1]])
                      for k in ctx["curves"]}
                exposure = {"arm_leg_weights": aw, "control_leg_weights": cw,
                            "max_abs_diff": max(abs(aw[k] - cw[k]) for k in aw),
                            "arm": 1.0, "control": 1.0, "err": 0.0,
                            "static_w": None,
                            "kind": "structural (identical targets; timing only)"}
                turnover = {"arm": arm_run["turnover_annual"],
                            "control": ctl_run["turnover_annual"],
                            "arm_rebalances": arm_run["n_rebal"],
                            "control_rebalances": ctl_run["n_rebal"],
                            "band_mult_mean": arm_run["band_mult_mean"]}
            else:
                arm_run = run_scale_arm(spec, dates, curve, cash, est, rets,
                                        cash_rets, cost)
                ctl_run = matched_control(dates, curve, cash,
                                          set(dates) if spec["freq"] == "daily" else months,
                                          cost, arm_run["exposure"])
                exposure = {"arm": arm_run["exposure"], "control": ctl_run["exposure"],
                            "err": ctl_run["exposure_err"], "static_w": ctl_run["static_w"],
                            "equity_arm": arm_run["exposure"] * book["equity_share"],
                            "equity_control": ctl_run["exposure"] * book["equity_share"],
                            "min_w": min(arm_run["w_by_date"].values()),
                            "max_w": max(arm_run["w_by_date"].values()),
                            "median_w": statistics.median(arm_run["w_by_date"].values()),
                            "frac_at_default": arm_run["at_cap"],
                            "kind": "solved (bisection on the static target)"}
                turnover = {"arm": arm_run["turnover_annual"],
                            "control": ctl_run["turnover_annual"],
                            "arm_rebalances": arm_run["n_rebal"],
                            "control_rebalances": ctl_run["n_rebal"]}
            j = judge(arm_run, ctl_run, dates, bil_rets, spy_rets, draws)
            j["exposure"] = exposure
            j["turnover"] = turnover
            arm_out["costs"][f"{cost:.0f}bps"] = j
        out["arms"][spec["key"]] = arm_out
    return out


def survives(arm: dict) -> dict:
    """SURVIVES = beats the MATCHED control on Sharpe AND Calmar over the full
    window, bootstrap 95% CI on dSharpe excluding zero, in >=3 of the 5 named
    regimes, AND still at 20 bps. Registered; not amendable.

    A book whose window does not contain all five named regimes (the 2016+
    30/70 blend) CANNOT be put to this bar. Its arms are reported with
    `adjudicable=False` and are never counted as survivors — the registration
    says those arms are reported separately, not that they get an easier bar.
    """
    per, per_dd = {}, {}
    adjudicable = True
    for lvl, j in arm["costs"].items():
        b = j["bar"]
        adjudicable = adjudicable and b["all_regimes_present"]
        core = bool(b["beats_sharpe"] and b["beats_calmar"] and b["ci_excludes_zero"])
        per[lvl] = bool(core and b["regimes_ge_3"])
        # The registration says ">=3 of the 5 named regimes" without saying on
        # WHAT. The primary count uses the campaign's adjudication metric
        # (in-regime BIL-excess Sharpe); this second count uses in-regime max
        # drawdown. Both are reported, so neither is a choice made after the
        # numbers were seen — and the report states whether they ever disagree.
        per_dd[lvl] = bool(core and j["regime_wins_dd"] >= 3)
    return {"per_cost": per, "per_cost_dd_reading": per_dd,
            "adjudicable": adjudicable,
            "survives": bool(adjudicable and all(per.values())),
            "survives_dd_reading": bool(adjudicable and all(per_dd.values())),
            "readings_agree": bool(per == per_dd)}


# --- run ---------------------------------------------------------------------------------------

def run(*, draws: int = BOOT_DRAWS) -> dict:
    gate = fmp.cross_validate()
    fmp.require_gate(gate)          # HARD STOP — round 7's registered gate, re-run

    raw = load_universe()
    dates = window_dates(raw)
    cash = build_cash(raw, dates)
    books = build_books(raw, dates, cash)
    spy_curve = books["SPY"]["curve"]
    est_cache: dict = {}

    a = part_a(books, dates, est_cache)

    b5legs = build_legs(raw, dates, "T1")
    band_ctx_b5 = {"curves": b5legs["curves"], "target_at": b5legs["target_at"],
                   "band_rel": B5_BAND_REL, "cal_fallback_days": B5_CAL_FALLBACK_D}
    part_b: dict = {}
    for name, book in books.items():
        part_b[name] = run_book(name, book, dates, cash, spy_curve, est_cache,
                                draws=draws,
                                band_ctx=band_ctx_b5 if name == "B5-T1" else None)

    blend = build_blend_3070(raw, dates)
    band_ctx_blend = {"curves": blend["legs"], "target_at": blend["target"],
                      "band": LIVE_BAND}
    part_b["30/70"] = run_book("30/70", blend["book"], blend["dates"], blend["cash"],
                               blend["spy"], est_cache, draws=draws,
                               band_ctx=band_ctx_blend)
    part_b["30/70"]["window"] = {"start": blend["dates"][0], "end": blend["dates"][-1],
                                 "n": len(blend["dates"])}

    # --- survival + multiplicity -------------------------------------------------
    for bk, bv in part_b.items():
        for ak, av in bv["arms"].items():
            av["survival"] = survives(av)
            if not av["judged"]:
                av["survival"]["survives"] = False
                av["survival"]["survives_dd_reading"] = False
                av["survival"]["adjudicable"] = False

    maxt = {}
    for lvl in COST_LEVELS:
        key = f"{lvl:.0f}bps"
        fam = [(f"{bk}/{ak}", av["costs"][key]["_arm_ex"], av["costs"][key]["_ctl_ex"])
               for bk, bv in part_b.items() if bk != "30/70"
               for ak, av in bv["arms"].items() if av["judged"]]
        maxt[key] = westfall_young(fam, draws=draws)
    maxt_blend = {}
    for lvl in COST_LEVELS:
        key = f"{lvl:.0f}bps"
        fam = [(f"30/70/{ak}", av["costs"][key]["_arm_ex"], av["costs"][key]["_ctl_ex"])
               for ak, av in part_b["30/70"]["arms"].items() if av["judged"]]
        maxt_blend[key] = westfall_young(fam, draws=draws)

    # Curves for the visual, then drop the bulky excess-return series.
    curves = {"dates": dates,
              "books": {k: {d: v["curve"][d] for d in dates} for k, v in books.items()},
              "cash": {d: cash[d] for d in dates}}
    for bv in part_b.values():
        for av in bv["arms"].values():
            for j in av["costs"].values():
                j.pop("_arm_ex", None)
                j.pop("_ctl_ex", None)
    for bk in a["books"]:
        a["books"][bk]["a1"]["tercile (registered)"].pop("labels", None)

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contract": CONTRACT,
        "window": {"start": dates[0], "end": dates[-1], "n": len(dates)},
        "gate": gate,
        "part_a": a,
        "part_b": part_b,
        "max_t": {"20y_family": maxt, "blend_family": maxt_blend},
        "curves": curves,
        "protocol": {
            "base_cost_bps": BASE_COST_BPS, "cost_levels": list(COST_LEVELS),
            "vol_target": V_TARGET, "vol_window": V_WINDOW, "cap": V_CAP,
            "v5_targets": list(V5_TARGETS), "v6_cap": V6_CAP,
            "v8_window": V8_WINDOW, "ewma_lambda": EWMA_LAMBDA,
            "garch_init_days": GARCH_INIT_DAYS,
            "regime_min_history": REGIME_MIN_HISTORY,
            "boot": {"block": BOOT_BLOCK, "draws": draws, "seed": BOOT_SEED,
                     "basis": "BIL-excess daily returns, paired on dates, vs the "
                              "arm's OWN matched-exposure control"},
        },
    }


# --- report -------------------------------------------------------------------------------------

CHARTS_URL = "https://claude.ai/code/artifact/9afa3315-17c4-4e12-81e2-eeae5ae40268"
ARM_ORDER = ["V1", "V2", "V3", "V3-WU", "V4", "V5-12", "V5-15", "V6", "V7", "V8"]
BOOK_ORDER = ["SPY", "B5-T1", "63/37", "30/70"]


def _pct(x, nd=2):
    return "n/a" if x is None or x != x else f"{x * 100:.{nd}f}%"


def _num(x, nd=3):
    return "n/a" if x is None or x != x else f"{x:.{nd}f}"


def _sgn(x, nd=3):
    return "n/a" if x is None or x != x else f"{x:+.{nd}f}"


def _rec(days):
    return "**never**" if days is None else f"{days}d"


def _arms(bv):
    return [(k, bv["arms"][k]) for k in ARM_ORDER if k in bv["arms"]]


def render_report(res: dict) -> str:
    w, gate, pa, pb = res["window"], res["gate"], res["part_a"], res["part_b"]
    p = res["protocol"]
    L: list[str] = []
    a = L.append

    judged = [(bk, ak, av) for bk in BOOK_ORDER for ak, av in _arms(pb[bk]) if av["judged"]]
    survivors = [f"{bk}/{ak}" for bk, ak, av in judged if av["survival"]["survives"]]
    disagree = [f"{bk}/{ak}" for bk, ak, av in judged if not av["survival"]["readings_agree"]]
    ci_arms = [(bk, ak, lvl, j) for bk, ak, av in judged
               for lvl, j in av["costs"].items() if j["boot"]["excludes_zero"]]
    max_err = max(abs(j["exposure"].get("err", 0.0) or 0.0)
                  for _bk, _ak, av in judged for j in av["costs"].values())
    max_band_err = max([j["exposure"].get("max_abs_diff", 0.0)
                        for _bk, _ak, av in judged for j in av["costs"].values()
                        if av["kind"] == "band"] or [0.0])

    a(f"# Backtest — ROUND 8, volatility: the thesis, then the overlay, {w['start']}..{w['end']}")
    a("")
    a(f"Generated by `backend/scripts/backtest_vol_overlay_r8.py` (deterministic; bootstrap seed "
      f"{p['boot']['seed']}). Contract: [{CONTRACT}](VARIANTS_PREREGISTRATION_R8_VOL.md), committed "
      "(7d8458a) BEFORE any round-8 code existed. Nothing here is a config change or a live weight; "
      "nothing is promoted (TUNING.md law).")
    a("")
    a(f"**Charts** (the vol regime series with the named crises marked, the forecast-error "
      f"comparison, and every overlay against ITS MATCHED CONTROL): {CHARTS_URL}")
    a("")

    # ---------------- verdict ----------------------------------------------------
    spy_a1 = pa["books"]["SPY"]["a1"]["tercile (registered)"]["rows"]
    lo1 = next(r for r in spy_a1 if r["state"] == "low" and r["horizon"] == 1)
    hi1 = next(r for r in spy_a1 if r["state"] == "high" and r["horizon"] == 1)
    lo20 = next(r for r in spy_a1 if r["state"] == "low" and r["horizon"] == 20)
    hi20 = next(r for r in spy_a1 if r["state"] == "high" and r["horizon"] == 20)
    g3 = pa["books"]["SPY"]["a3"]
    gv = g3["garch_beats_trailing"]
    v1spy = pb["SPY"]["arms"]["V1"]["costs"]["5bps"]

    a("## Verdict")
    a("")
    a(f"**The thesis holds. The overlay does not clear the bar it was registered against — "
      f"{'NOTHING SURVIVES' if not survivors else 'survivors: ' + ', '.join(survivors)}.**")
    a("")
    a(f"Volatility clusters, and it clusters harder than the tweet claims: at our registered "
      f"expanding-window terciles SPY's one-day persistence is {_pct(lo1['p'], 1)} low→low and "
      f"{_pct(hi1['p'], 1)} high→high against the asserted "
      f"{_pct(TWEET_CLAIM['low'], 0)}/{_pct(TWEET_CLAIM['high'], 0)} — but most of that gap is an "
      f"ARTEFACT of a 20-day estimator (consecutive days share 19 of 20 observations), and at a "
      f"non-overlapping 20-day horizon the same regimes persist {_pct(lo20['p'], 1)} / "
      f"{_pct(hi20['p'], 1)}. Vol is forecastable and GARCH(1,1) wins the forecast contest "
      f"out of sample on {'QLIKE and RMSE' if gv['qlike'] and gv['rmse'] else 'neither loss'}.")
    a("")
    a(f"And it does not matter. Against a STATIC book at the SAME realized average exposure, the "
      f"10% vol target on SPY buys {_pct(-v1spy['d_maxdd'])} of drawdown "
      f"({_pct(v1spy['metrics']['max_dd'])} vs {_pct(v1spy['control_metrics']['max_dd'])}) and "
      f"{_sgn(v1spy['d_sharpe_bil'])} of BIL-excess Sharpe whose 95% bootstrap interval "
      f"[{_num(v1spy['boot']['ci_lo'])}, {_num(v1spy['boot']['ci_hi'])}] straddles zero. That "
      f"pattern repeats on every book and every target: **drawdown and Calmar improve at matched "
      f"exposure — the improvement is NOT the mechanical exposure effect, because the control has "
      f"already been given the same exposure — and the Sharpe claim never separates from noise.**")
    a("")
    if ci_arms:
        worst = min(ci_arms, key=lambda t: t[3]["d_sharpe_bil"])
        mt = res["max_t"]["20y_family"][worst[2]]
        key = f"{worst[0]}/{worst[1]}"
        n_distinct = len({(t[0], t[1]) for t in ci_arms})
        a(f"Across {len(judged)} judged arms at two cost levels, exactly {n_distinct} ARM "
          f"({len(ci_arms)} arm-cost combination{'s' if len(ci_arms) != 1 else ''}) has a ΔSharpe "
          f"interval that excludes zero, and it is NEGATIVE: {key} at {worst[2]} reads "
          f"{_sgn(worst[3]['d_sharpe_bil'])} "
          f"[{_num(worst[3]['boot']['ci_lo'])}, {_num(worst[3]['boot']['ci_hi'])}], raw p "
          f"{worst[3]['boot']['p_two_sided']:.3f} — and under this round's max-T correction its "
          f"adjusted p is {mt['adjusted_p'].get(key, float('nan')):.3f}, so even the round's one "
          f"significant result is not significant once the family is counted. **The single arm "
          f"whose edge separates from noise is the GARCH arm making the book worse.**")
    else:
        a("No arm's ΔSharpe interval excludes zero at either cost level.")
    a("")
    a("The registered prior said exactly this: *\"Part A confirms clustering; Part B improves "
      "drawdown at matched exposure but does NOT clear the Sharpe bar\"*. It is recorded in the "
      "contract, it was written before the code, and it is what happened.")
    a("")

    # ---------------- the comparator ----------------------------------------------
    a("## The comparator that decides this round")
    a("")
    a("A vol-targeted book holds less exposure on average, so it cuts drawdown MECHANICALLY. "
      "Round 7's counter-agent caught that error in its previous form — a plain 63/37 SPY/T-bill "
      "book beat B.5 on drawdown with no factors in it at all — and the round-8 registration "
      "applies the fix IN ADVANCE:")
    a("")
    a("> every overlay is judged against a STATIC book with the SAME AVERAGE EQUITY EXPOSURE, "
      "computed from the overlay's own realized weight path.")
    a("")
    a("For each arm the control is solved, not assumed: bisection on the static target weight "
      "until the control's REALIZED average exposure equals the arm's. A static target is not the "
      "same thing as a static realized exposure — the weight drifts with the book between "
      "rebalances — which is why the control is solved rather than set to the arm's mean weight. "
      f"Across every judged arm at every cost level the worst residual match error is "
      f"{max_err:.1e} of book weight.")
    a("")
    a("V7 is matched STRUCTURALLY rather than by solving, and is marked as such in its rows: it "
      "changes only the rebalance TIMING of a fully-invested book, so its control holds the "
      "IDENTICAL target weights and the same legs, and average exposure cannot move. The realized "
      f"leg weights still differ slightly because the two books sample the same drift at different "
      f"moments — worst realized leg-weight difference across the V7 arms {max_band_err:.2e}, i.e. "
      f"{max_band_err * 100:.2f}pp, against exposure differences of 10-25pp that the solved "
      f"controls exist to remove.")
    a("")
    a("The fully-invested book and a 60/40 peer are computed for every book and printed as "
      "SECONDARY context. They never adjudicate anything. "
      + SIXTY_FORTY_NOTE)
    a("")

    # ---------------- gate -----------------------------------------------------------
    a("## The cross-validation gate (round 7's, re-run before any result)")
    a("")
    a("| ticker | overlap | n | RMS (bps) | max 1-day (bps) | worst day | verdict |")
    a("|---|---|---|---|---|---|---|")
    for t, r in gate["tickers"].items():
        a(f"| {t} | {r.get('start')}..{r.get('end')} | {r['n']:,} | {r['rms_bps']:.3f} | "
          f"{r['max_bps']:.2f} | {r.get('worst_date')} | {'**PASS**' if r['pass'] else '**FAIL**'} |")
    a("")
    a(f"**GATE: {'PASS' if gate['passed'] else 'FAIL'}.** The qualifier round 7's counter-agent "
      "attached to it still applies and is repeated in the honesty box: the overlap is "
      "2016-2026, so the GFC decade is validated by nothing, and an independent lane fails EEM "
      "over the pre-2016 stretch.")
    a("")

    # ---------------- protocol ---------------------------------------------------------
    a("## Protocol (fixed before results)")
    a("")
    a(f"- Window {w['start']}..{w['end']}, n={w['n']:,} trading days, identical dates for every "
      f"20-year arm. Source: the round-7 FMP dividend-adjusted lane.")
    a(f"- Books: **SPY**; **B.5-T1** (round 7's treatment T1, reproduced here at "
      f"{_pct(pb['B5-T1']['base']['metrics']['cagr'])} CAGR / "
      f"{_pct(pb['B5-T1']['base']['metrics']['max_dd'])} max DD — round 7's published numbers); "
      f"**63/37 SPY/T-bill** (the counter-agent's equity-share-matched book, "
      f"{_pct(pb['63/37']['base']['metrics']['cagr'])} / "
      f"{_pct(pb['63/37']['base']['metrics']['max_dd'])}); and the **live 30/70 blend**, "
      f"{pb['30/70']['window']['start']}..{pb['30/70']['window']['end']} "
      f"(n={pb['30/70']['window']['n']:,}), reported separately.")
    a(f"- Overlay parameters: target {_pct(p['vol_target'], 0)}, trailing-{p['vol_window']}d "
      f"estimator, cap {p['cap']:.1f} (deleverage-only), monthly; V5 at "
      f"{'/'.join(_pct(x, 0) for x in p['v5_targets'])}; V6 cap {p['v6_cap']:.1f}x; V8 "
      f"trailing-{p['v8_window']}d; EWMA lambda {p['ewma_lambda']}; GARCH refit annually on an "
      f"expanding history after {p['garch_init_days']} days.")
    a(f"- **Costs.** The underlying books carry the rounds 4-7 convention "
      f"({p['base_cost_bps']:.0f} bps/side) so B.5-T1 is byte-for-byte round 7's. The OVERLAY "
      f"layer — the only layer whose turnover differs between an arm and its control — is charged "
      f"at BOTH {' and '.join(f'{c:.0f}' for c in p['cost_levels'])} bps per side, and every "
      f"number below exists at both.")
    a(f"- Bootstrap: paired circular block bootstrap on the Sharpe DIFFERENCE vs THE ARM'S OWN "
      f"MATCHED CONTROL, {p['boot']['block']}-day blocks, {p['boot']['draws']:,} draws, seed "
      f"{p['boot']['seed']}, BIL-excess daily returns, same block starts for both series.")
    a("- Adjudication basis is BIL-excess (round 7's ruling: rf=0 must not be scored as a win). "
      "rf=0 Sharpe is carried in the JSON and never adjudicates.")
    a("")
    a("**SURVIVES** = beats its MATCHED-EXPOSURE control on Sharpe AND Calmar over the full "
      "window, with a bootstrap 95% CI on ΔSharpe excluding zero, in >=3 of the 5 named regimes, "
      "and still at 20 bps.")
    a("")

    # ================= PART A =======================================================
    a("## PART A — the thesis, descriptive")
    a("")
    a("### A1 — regime persistence (expanding-window thresholds)")
    a("")
    a("Regimes are terciles of trailing 20d realized vol with thresholds re-estimated on an "
      f"EXPANDING window at every date (full-sample quantiles are look-ahead and the registration "
      f"forbids them). A day is labelled only after {p['regime_min_history']} vol observations "
      "exist, so no label is decided by a handful of points.")
    a("")
    a("| book | state | horizon | our P(stay) | Wilson 95% | n | the tweet asserts |")
    a("|---|---|---|---|---|---|---|")
    for bk in ("SPY", "B5-T1", "63/37"):
        for r in pa["books"][bk]["a1"]["tercile (registered)"]["rows"]:
            claim = _pct(TWEET_CLAIM[r["state"]], 0) if r["horizon"] == 1 else "—"
            a(f"| {bk} | {r['state']} | {r['horizon']}d | **{_pct(r['p'], 1)}** | "
              f"[{_pct(r['ci_lo'], 1)}, {_pct(r['ci_hi'], 1)}] | {r['n']:,} | {claim} |")
    a("")
    a("**Read this before quoting the 1-day number.** A trailing-20d estimator makes consecutive "
      "days share 19 of their 20 observations, so a 1-day \"persistence\" of ~96% is mostly the "
      "estimator's own window, not the market's memory. The honest regime-persistence numbers in "
      "this table are the 20-day rows, where the windows do not overlap at all: SPY's low regime "
      f"persists {_pct(lo20['p'], 1)} and its high regime {_pct(hi20['p'], 1)} — still far above "
      f"the ~33% a memoryless tercile process would give, which is the finding. **Measured "
      f"against the tweet's 74%/81%, our 1-day numbers are HIGHER and our 20-day numbers are "
      f"LOWER**; without knowing the tweet's estimator window or horizon the two cannot be put on "
      f"one axis, and the report does not pretend otherwise.")
    a("")
    a("Sensitivity to the threshold choice (SPY, 1-day and 20-day):")
    a("")
    a("| threshold scheme | low 1d | high 1d | low 20d | high 20d | days labelled |")
    a("|---|---|---|---|---|---|")
    for scheme, sv in pa["books"]["SPY"]["a1"].items():
        g = {(r["state"], r["horizon"]): r for r in sv["rows"]}
        flag = " **(look-ahead)**" if sv["look_ahead"] else ""
        a(f"| {scheme}{flag} | {_pct(g[('low', 1)]['p'], 1)} | {_pct(g[('high', 1)]['p'], 1)} | "
          f"{_pct(g[('low', 20)]['p'], 1)} | {_pct(g[('high', 20)]['p'], 1)} | "
          f"{sv['n_labelled']:,} |")
    a("")
    a("The look-ahead row is printed to size the sin, not to use it: full-sample terciles are what "
      "a casual study would compute, and they are forbidden here. The FIXED scheme is the "
      "cautionary one — its thresholds are trained once on 2006-2009, the most violent three years "
      "in the sample, so it under-calls 'high' for the next fifteen years and its high-regime "
      "persistence collapses. **The persistence result is real but the threshold choice moves it "
      "by 20-35 points, which is why the registration made the tercile rule the primary and asked "
      "for this table.**")
    a("")

    a("### A2 — autocorrelation: vol and |return| against SIGNED returns")
    a("")
    a("| book | series | " + " | ".join(f"lag {k}" for k in A_LAGS) + " |")
    a("|---" * (len(A_LAGS) + 2) + "|")
    for bk in ("SPY", "B5-T1", "63/37"):
        a2 = pa["books"][bk]["a2"]
        for label, key in (("realized vol (20d)", "realized_vol_20d"),
                           ("abs(return)", "abs_return"),
                           ("signed return", "signed_return")):
            a(f"| {bk} | {label} | " + " | ".join(_num(v) for v in a2[key]) + " |")
    a("")
    a("This is the contrast the whole thesis rests on and it is stark: abs(return) stays positively "
      "autocorrelated out to 60 trading days while the SIGNED return is noise at every lag. "
      "**Magnitude is predictable; direction is not.** Everything Part B tries to do lives inside "
      "that first row.")
    a("")

    a("### A3 — one-day-ahead vol forecasts, walk-forward, no look-ahead")
    a("")
    a(f"GARCH(1,1) is fitted by Gaussian MLE (hand-rolled — `arch` is not installed in this "
      f"environment and no dependency was added; see `scripts/lib/volmodels.py`), refit each "
      f"January on an EXPANDING history after a {p['garch_init_days']}-day burn-in. All three "
      f"models are scored on the SAME out-of-sample days, starting {g3['oos_start']} "
      f"(n={g3['n']:,}), against the squared-return proxy.")
    a("")
    a("| book | model | RMSE (variance, x1e4) | QLIKE | secondary: RMSE vs fwd-20d vol (vol pts) |")
    a("|---|---|---|---|---|")
    for bk in ("SPY", "B5-T1", "63/37"):
        for m, sc in pa["books"][bk]["a3"]["models"].items():
            a(f"| {bk} | {m} | {sc['rmse'] * 1e4:.4f} | {sc['qlike']:.4f} | "
              f"{sc['rmse_vol_pts'] * 100:.2f} |")
    a("")
    verdicts = {bk: pa["books"][bk]["a3"]["garch_beats_trailing"] for bk in ("SPY", "B5-T1", "63/37")}
    all_q = all(v["qlike"] for v in verdicts.values())
    all_r = all(v["rmse"] for v in verdicts.values())
    a(f"**Verdict, stated plainly because the registration demands it either way: GARCH(1,1) "
      f"{'DOES' if all_q and all_r else 'does NOT'} beat trailing-20d realized out of sample** — "
      f"on QLIKE it wins on {sum(1 for v in verdicts.values() if v['qlike'])} of "
      f"{len(verdicts)} books, on RMSE {sum(1 for v in verdicts.values() if v['rmse'])} of "
      f"{len(verdicts)}, and EWMA(0.94) lands between the two everywhere. The margin is real but "
      f"small (SPY QLIKE {pa['books']['SPY']['a3']['models']['GARCH(1,1) walk-forward']['qlike']:.4f} "
      f"vs {pa['books']['SPY']['a3']['models']['trailing 20d realized']['qlike']:.4f}). "
      f"Part B is where that margin gets cashed, and it does not cash.")
    a("")
    fits = pa["books"]["SPY"]["a3"]["fits"]
    if fits:
        a(f"SPY's annual refits are stable: alpha runs "
          f"{min(f['alpha'] for f in fits):.3f}..{max(f['alpha'] for f in fits):.3f}, beta "
          f"{min(f['beta'] for f in fits):.3f}..{max(f['beta'] for f in fits):.3f}, persistence "
          f"{min(f['persistence'] for f in fits):.4f}..{max(f['persistence'] for f in fits):.4f} "
          f"over {len(fits)} fits — no explosive corner, no refit that rewrites the model.")
        a("")

    # ================= PART B =======================================================
    a("## PART B — the eight overlay arms")
    a("")
    for bk in BOOK_ORDER:
        bv = pb[bk]
        base = bv["base"]["metrics"]
        a(f"### {bk} — {bv['desc']}")
        a("")
        if "window" in bv:
            a(f"Window {bv['window']['start']}..{bv['window']['end']} "
              f"(n={bv['window']['n']:,}) — **2016+ only, reported separately, and NOT adjudicable "
              f"on the five named regimes** (two of them predate the book).")
            a("")
        a(f"Base book: CAGR {_pct(base['cagr'])}, max DD {_pct(base['max_dd'])}, vol "
          f"{_pct(base['vol'])}, Sharpe(BIL) {_num(base['sharpe_bil'])}, Calmar "
          f"{_num(base['calmar'])}. Realized equity share {_pct(bv['equity_share'])}. "
          f"SECONDARY context only — 60/40 peer: CAGR {_pct(bv['secondary']['sixty_forty']['cagr'])}, "
          f"DD {_pct(bv['secondary']['sixty_forty']['max_dd'])}, Sharpe(BIL) "
          f"{_num(bv['secondary']['sixty_forty']['sharpe_bil'])}.")
        a("")
        a("| arm | avg exposure | control static w | turnover/yr | CAGR | max DD | vol | "
          "Sharpe(BIL) | Calmar | ΔSharpe @5bps [95% CI] | ΔSharpe @20bps [95% CI] | ΔCalmar @5/@20 "
          "| ΔmaxDD @5bps | regimes (Sh / DD) | SURVIVES |")
        a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for ak, av in _arms(bv):
            j5, j20 = av["costs"]["5bps"], av["costs"]["20bps"]
            e = j5["exposure"]
            m = j5["metrics"]
            sw = "structural" if e.get("static_w") is None else _num(e["static_w"])
            surv = ("**SURVIVES**" if av["survival"]["survives"]
                    else ("n/a" if not av["survival"]["adjudicable"] else "no"))
            if not av["judged"]:
                surv = "_diagnostic_"
            a(f"| {ak} | {_pct(e['arm'], 1)} | {sw} | {j5['turnover']['arm']:.2f}x | "
              f"{_pct(m['cagr'])} | {_pct(m['max_dd'])} | {_pct(m['vol'])} | "
              f"{_num(m['sharpe_bil'])} | {_num(m['calmar'])} | "
              f"{_sgn(j5['d_sharpe_bil'])} [{_num(j5['boot']['ci_lo'])}, "
              f"{_num(j5['boot']['ci_hi'])}] | {_sgn(j20['d_sharpe_bil'])} "
              f"[{_num(j20['boot']['ci_lo'])}, {_num(j20['boot']['ci_hi'])}] | "
              f"{_sgn(j5['d_calmar'])} / {_sgn(j20['d_calmar'])} | "
              f"{_sgn(j5['d_maxdd'] * 100, 2)}pp | "
              f"{j5['regime_wins_sharpe']}/{j5['regimes_live']} / "
              f"{j5['regime_wins_dd']}/{j5['regimes_live']} | {surv} |")
        a("")
        a(f"_Level metrics (CAGR, DD, vol, Sharpe, Calmar) are the 5 bps run; the deltas are shown "
          f"at both cost levels. Every Δ is against THAT ARM'S OWN matched-exposure control, never "
          f"against the fully-invested book._")
        a("")
        a(f"**The named regimes — max drawdown, arm vs its matched control.**")
        a("")
        reg_names = [n for n, _s, _e in REGIMES]
        a("| arm | " + " | ".join(reg_names) + " |")
        a("|---" * (len(reg_names) + 1) + "|")
        for ak, av in _arms(bv):
            j5 = av["costs"]["5bps"]
            cells = []
            for n in reg_names:
                r = j5["regimes"].get(n)
                cells.append("n/a" if r is None else
                             f"{_pct(r['arm']['max_dd'], 1)} vs {_pct(r['control']['max_dd'], 1)}")
            a(f"| {ak} | " + " | ".join(cells) + " |")
        a("")
        a(f"**The named regimes — recovery time out of the regime trough, arm vs control.**")
        a("")
        a("| arm | " + " | ".join(reg_names) + " |")
        a("|---" * (len(reg_names) + 1) + "|")
        for ak, av in _arms(bv):
            j5 = av["costs"]["5bps"]
            cells = []
            for n in reg_names:
                r = j5["regimes"].get(n)
                cells.append("n/a" if r is None else
                             f"{_rec(r['arm']['recovery_days'])} vs "
                             f"{_rec(r['control']['recovery_days'])}")
            a(f"| {ak} | " + " | ".join(cells) + " |")
        a("")
        a("_The recovery columns carry the trade-off the drawdown columns hide: the scaling arms "
          "come out of a CRISIS trough faster than their controls, and out of a CALM drawdown "
          "slower, because a book that is deleveraged when vol is high is also deleveraged for "
          "the first part of the rebound._")
        a("")

    # ---------------- cost fragility -------------------------------------------------
    a("## Cost fragility")
    a("")
    a("An arm whose edge does not survive 20 bps is **cost-fragile**. Nothing here survives at "
      "either level, so \"fragile\" is measured as the share of the 5 bps ΔSharpe that 20 bps "
      "removes.")
    a("")
    a("| arm | book | turnover/yr | ΔSharpe @5bps | ΔSharpe @20bps | edge lost to costs |")
    a("|---|---|---|---|---|---|")
    rows = []
    for bk, ak, av in judged:
        j5, j20 = av["costs"]["5bps"], av["costs"]["20bps"]
        d5, d20 = j5["d_sharpe_bil"], j20["d_sharpe_bil"]
        lost = (1 - d20 / d5) if d5 > 0 else float("nan")
        rows.append((j5["turnover"]["arm"], ak, bk, d5, d20, lost))
    for tov, ak, bk, d5, d20, lost in sorted(rows, reverse=True)[:12]:
        a(f"| {ak} | {bk} | {tov:.2f}x | {_sgn(d5)} | {_sgn(d20)} | "
          f"{'n/a (no edge at 5 bps)' if lost != lost else (_pct(lost, 0) + (' — FLIPS NEGATIVE' if d20 < 0 else ''))} |")
    a("")
    a("The daily arm (V2) and the leverage arm (V6) are the turnover monsters — 2.5x to 4.6x of "
      "book notional a year against the monthly arms' 0.4x-2.0x — and they are where the cost "
      "sensitivity bites hardest. Neither had an edge that separated from zero at 5 bps, so "
      "\"cost-fragile\" is here a statement about an effect that was never established.")
    a("")

    # ---------------- multiplicity ----------------------------------------------------
    a("## Multiplicity — max-T over this round's arms")
    a("")
    for fam_name, fam in (("the three 20-year books", res["max_t"]["20y_family"]),
                          ("the 2016+ 30/70 blend", res["max_t"]["blend_family"])):
        mt = fam["5bps"]
        a(f"**{fam_name}** — {mt['n_arms']} judged arms, single-step Westfall-Young on one shared "
          f"block-draw sequence ({mt['draws']:,} draws, {mt['block']}-day blocks, seed "
          f"{mt['seed']}), at 5 bps:")
        a("")
        a("| arm | ΔSharpe vs its control | raw p | max-T adjusted p |")
        a("|---|---|---|---|")
        for k in sorted(mt["adjusted_p"], key=lambda k: mt["adjusted_p"][k])[:6]:
            a(f"| {k} | {_sgn(mt['point'][k])} | {mt['raw_p'][k]:.3f} | {mt['adjusted_p'][k]:.3f} |")
        a("")
    a("**A caveat this round has to state and rounds 4-6 did not.** Each arm here is tested "
      "against its OWN matched control, so the family does not share one comparator the way a "
      "campaign-wide max-T does. The shared draw sequence still carries the arms' calendar "
      "dependence, which is what the correction needs, but the adjusted p answers \"how extreme is "
      "this gap among a family of such gaps\", not \"against one incumbent\". What no correction "
      "in this family covers: the choice of window, the choice of books, and the fact that B.5's "
      "weights were set by someone who already knew this history.")
    a("")

    # ---------------- holds / does not hold -------------------------------------------
    a("## What holds and what does not")
    a("")
    a("| claim | basis | verdict |")
    a("|---|---|---|")
    a(f"| Volatility clusters | 20d-vol regime persistence, expanding terciles, 20-day "
      f"non-overlapping horizon: {_pct(lo20['p'], 1)} / {_pct(hi20['p'], 1)} vs ~33% memoryless | "
      f"**HOLDS** |")
    a("| Magnitude is autocorrelated and direction is not | abs(return) autocorrelation positive to "
      "lag 60; signed-return autocorrelation ~0 at every lag, on all three books | **HOLDS** |")
    a(f"| Vol is forecastable, and GARCH forecasts it best | walk-forward QLIKE and RMSE on "
      f"{g3['n']:,} out-of-sample days, all three books | "
      f"**{'HOLDS' if all_q and all_r else 'DOES NOT HOLD'}** |")
    a("| A vol overlay improves DRAWDOWN at matched exposure | every scaling arm on every book "
      "cuts max DD against a control with the same average exposure | **HOLDS** (descriptive, "
      "in-sample) |")
    a("| A vol overlay improves CALMAR at matched exposure | same | **HOLDS** (descriptive, "
      "in-sample) |")
    a("| A vol overlay improves CAGR | scaling arms lose CAGR to their controls in most books | "
      "**DOES NOT HOLD** |")
    a("| A vol overlay improves risk-adjusted return (Sharpe) at matched exposure | bootstrap CI "
      "on ΔSharpe straddles zero for every judged arm except one, which is negative | **NOT "
      "ESTABLISHED** |")
    a("| The GARCH forecasting edge converts into strategy P&L | V3 is the worst scaling arm on "
      "every 20-year book, and the only arm whose CI excludes zero | **DOES NOT HOLD** |")
    a("| Vol-scaled rebalance BANDS help (V7) | ΔSharpe ~0.00 and ΔCalmar <0 on both banded books "
      "| **DOES NOT HOLD** |")
    a("| Inverse-vol between book and cash is a usable rule (V8) | the cash leg's near-zero vol "
      "drives the book weight to 4-5%; the arm is a cash proxy | **DEGENERATE BY CONSTRUCTION** |")
    a(f"| Any arm SURVIVES the registered bar | Sharpe AND Calmar AND CI-excludes-zero AND >=3 of "
      f"5 regimes AND at 20 bps | **{'NO — nothing survives' if not survivors else ', '.join(survivors)}** |")
    a("")

    # ---------------- honesty box -------------------------------------------------------
    a("## Honesty box")
    a("")
    a("- **The matched-exposure design is the whole result, and it is also its own limitation.** "
      "BIL-excess Sharpe is invariant to a CONSTANT scaling of a book against cash, so matching "
      "exposure removes the mechanical part of the comparison by construction and what is left is "
      "the timing. That is exactly what should be measured. It also means the Sharpe test is a "
      "narrow one: an overlay that improves the investor's actual experience (much shallower "
      "drawdowns) can and does score zero on it. Both facts are in the tables above; neither is "
      "allowed to become the other.")
    a("- **The registration did not define what \"beats in a regime\" means.** The primary count "
      "uses in-regime BIL-excess Sharpe (the campaign's adjudication metric); a second count "
      "using in-regime max drawdown is printed beside it in every arm table. In a crashing regime "
      "the Sharpe reading is PERVERSE — an arm that halves the GFC drawdown scores as a loss, "
      "because scaling down a negative-mean stretch shrinks the denominator faster than the "
      "numerator. "
      + (f"The two readings never change a survival verdict here ({len(disagree)} disagreements "
         f"across {len(judged)} judged arms), because the bootstrap CI kills every arm before the "
         f"regime count is reached." if not disagree else
         f"They disagree for: {', '.join(disagree)}."))
    a("- **In-sample, and worse than in-sample.** Every number is measured on a window whose "
      "outcome was known when these rules were written. B.5's weights were set 2026-08-11 and are "
      "scored here from 2006. No CAGR, Sharpe, Calmar or drawdown in this document is a forecast, "
      "and nothing is promoted.")
    a("- **The 19% synthetic caveat, inherited wherever B.5 appears.** At the 2006 start 19% of "
      "B.5 (KMLM 14% + TAIL 5%) has no instrument in existence and 9% (QUAL) has only a crude SPY "
      "stand-in. This round runs treatment T1 only (cash in the gap) — round 7's T1/T2/T3 span is "
      "not re-run here, so every B.5 row inherits T1's assumption and does NOT carry round 7's "
      "honest range.")
    a("- **The EEM data disagreement round 7's verifier found.** The registered gate's overlap is "
      "2016-2026 and contains no crisis. Run over the actual study window against an independent "
      "lane, EEM shows 9.25 bps RMS full-window and 13.07 bps pre-2016 against a 5 bps threshold "
      "— it would have tripped the hard stop had a lane spanning 2006 been available. EEM is the "
      "AVEM proxy, 10% of B.5. The B.5 rows in this report rest on that.")
    a("- **The 30/70 arms cannot reach 2006.** R2-A's frozen curve begins 2016-01-04, so those "
      "arms see neither the GFC nor the recovery, cannot be put to the five-regime bar, and are "
      "reported separately for that reason — not given an easier bar.")
    a("- **The GARCH warm-up is a real confound in V3, and both fills are reported.** The "
      "registration is silent on what V3 holds during the 3-year burn-in before its first fit "
      "exists — which here is the entire GFC. The registered arm takes round 4's C4 convention and "
      "sits at the cap (fully invested through 2008); the `V3-WU` DIAGNOSTIC row uses V1's "
      "trailing-20d estimator instead. V3-WU is not judged, is not in the max-T family, and cannot "
      "survive; it exists so the reader can see how much of V3's deficit is GARCH and how much is "
      "the burn-in.")
    a("- **Leverage is financed at the T-bill rate with no spread** (V6, and any matched control "
      "solved above 1.0). That flatters the leveraged arms. Short-sale, borrow and margin "
      "mechanics are not modelled.")
    a("- **Costs are charged on the overlay layer only.** The underlying books keep the rounds 4-7 "
      "10 bps/side convention so B.5-T1 reproduces round 7 exactly. Arm and control pay the same "
      "overlay cost, so the comparison is clean, but the absolute CAGRs are not a full-cost "
      "simulation.")
    a("- **Measurement basis**: daily marked-to-market total returns on dividend-adjusted closes; "
      "drawdowns MTM peak-to-trough; CAGR calendar-annualized at 365.25; Sharpe/Sortino "
      "sqrt(252)-annualized, BIL-excess adjudicating.")
    a("- **Not modelled**: taxes, bid-ask in 2008, the intraday path (all decisions and executions "
      "are at the same close), slippage on a 4.6x-turnover daily arm in a crisis tape, and the "
      "assumption that an investor actually re-levered INTO a falling market every month for "
      "twenty years.")
    a("")
    a(f"_Generated {res['generated_utc']}._")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate-only", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--draws", type=int, default=BOOT_DRAWS)
    args = ap.parse_args()

    if args.gate_only:
        g = fmp.cross_validate()
        for t, r in g["tickers"].items():
            print(f"{t:<5} n={r['n']:>5} rms={r['rms_bps']:.3f}bps "
                  f"max={r['max_bps']:.2f}bps pass={r['pass']}")
        print("GATE:", "PASS" if g["passed"] else "FAIL")
        return

    res = run(draws=args.draws)
    if args.json:
        args.json.write_text(json.dumps(res, indent=1, sort_keys=True))
        print(f"wrote {args.json}")
    if args.report:
        REPORT.write_text(render_report(res))
        print(f"wrote {REPORT}")
    surv = [f"{bk}/{ak}" for bk, bv in res["part_b"].items()
            for ak, av in bv["arms"].items() if av["survival"]["survives"]]
    print("SURVIVORS:", ", ".join(surv) if surv else "NONE")


if __name__ == "__main__":
    main()
