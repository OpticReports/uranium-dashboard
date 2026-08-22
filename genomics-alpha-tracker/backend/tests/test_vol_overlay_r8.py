"""Round-8 gates: the vol models, the LOOK-AHEAD boundary, and the
MATCHED-EXPOSURE control the whole round is adjudicated against.

Merge-blocking gates on the MACHINERY, not on the results. Every assertion is a
known answer derived by hand or a structural invariant, so a convention change
breaks a test instead of silently moving a verdict. Nothing here touches the
network — the study reads its disk cache and every unit test runs on hand-built
series.

The registered contract is docs/VARIANTS_PREREGISTRATION_R8_VOL.md. The two
tests this round exists to have are:

  * `test_matched_control_is_actually_matched` — the round's PRIMARY BAR is a
    static book at the arm's own realized average exposure. If the control is
    not matched, every ΔSharpe and ΔCalmar in the report is measuring "holds
    less equity" instead of "times vol", which is precisely the error round 7's
    counter-agent caught.
  * `test_expanding_thresholds_do_not_see_the_future` (and its siblings for
    every estimator) — the registration forbids full-sample quantiles as
    look-ahead. Each of these mutates the series AFTER date i and asserts the
    quantity at i does not move; `test_full_sample_thresholds_DO_see_the_future`
    proves the instrument has teeth by showing the forbidden version fails it.
"""
from __future__ import annotations

import math
import random
import statistics

import pytest

from scripts.backtest_core_variants import (
    B5_BAND_REL,
    B5_CAL_FALLBACK_D,
    BOOT_SEED,
    LIVE_BAND,
    const,
    curve_returns,
    month_starts,
    portfolio,
)
from scripts.backtest_core_20y import build_legs, load_universe, window_dates
from scripts.backtest_vol_overlay_r8 import (
    BASE_COST_BPS,
    COST_LEVELS,
    EWMA_LAMBDA,
    GARCH_INIT_DAYS,
    V5_TARGETS,
    V6_CAP,
    V8_WINDOW,
    V_CAP,
    V_TARGET,
    V_WINDOW,
    arm_specs,
    build_books,
    build_cash,
    inverse_vol_pick,
    judge,
    matched_control,
    run_scale_arm,
    running_vol_mult,
    step_weights,
    survives,
    two_leg,
    vol_band_portfolio,
    vol_target_pick,
)
from scripts.lib import volmodels as vm

# --- hand-built series ----------------------------------------------------------------


def _dates(n: int) -> list[str]:
    """n consecutive business-ish dates. Only ordering and month boundaries
    matter to the engine, so a simple calendar walk is enough."""
    from datetime import date, timedelta

    out, d = [], date(2010, 1, 4)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _walk(rets: list[float], dates: list[str]) -> dict[str, float]:
    lvl, out = 1.0, {dates[0]: 1.0}
    for i, r in enumerate(rets):
        lvl *= 1 + r
        out[dates[i + 1]] = lvl
    return out


@pytest.fixture(scope="module")
def toy():
    rng = random.Random(11)
    dates = _dates(900)
    # A two-regime series: calm, then violent, then calm. Vol targeting has
    # something to bite on and the regime machinery has a real transition.
    rets = []
    for i in range(len(dates) - 1):
        sd = 0.004 if (i < 300 or i >= 600) else 0.025
        rets.append(rng.gauss(0.0004, sd))
    book = _walk(rets, dates)
    cash = _walk([0.00002] * (len(dates) - 1), dates)
    return {"dates": dates, "rets": rets, "book": book, "cash": cash}


@pytest.fixture(scope="module")
def real():
    """The real 20-year universe from the round-7 disk cache — no network."""
    raw = load_universe()
    dates = window_dates(raw)
    cash = build_cash(raw, dates)
    return {"raw": raw, "dates": dates, "cash": cash,
            "books": build_books(raw, dates, cash)}


# =====================================================================================
# THE MATCHED-EXPOSURE CONTROL — the round's primary bar
# =====================================================================================


def test_matched_control_is_actually_matched(toy):
    """THE test. The control's REALIZED average exposure must equal the arm's,
    not merely its static target — otherwise every delta in the report is
    contaminated by an exposure difference."""
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    for target in (0.08, 0.10, 0.15):
        vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
        pick = vol_target_pick(toy["rets"], lambda i: vol[i], target, V_CAP)
        w_at, _wbd, _dec = step_weights(d, months, pick, V_CAP)
        arm = two_leg(d, book, cash, w_at, months, 5.0)
        ctl = matched_control(d, book, cash, months, 5.0, arm["exposure"])
        assert abs(ctl["exposure"] - arm["exposure"]) < 1e-10, (
            f"control exposure {ctl['exposure']} != arm {arm['exposure']}")
        # And the arm really did vary its weight — a "matched" control against a
        # constant arm would be a tautology, not a test.
        ws = list(_wbd.values())
        assert max(ws) - min(ws) > 0.3


def test_matched_control_static_target_is_not_the_arms_mean_weight(toy):
    """The control is SOLVED, not set to the arm's mean weight: a static target
    drifts between rebalances so its realized average differs from its target.
    If these ever coincide the bisection has been silently replaced."""
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    pick = vol_target_pick(toy["rets"], lambda i: vol[i], 0.10, V_CAP)
    w_at, _wbd, _ = step_weights(d, months, pick, V_CAP)
    arm = two_leg(d, book, cash, w_at, months, 5.0)
    ctl = matched_control(d, book, cash, months, 5.0, arm["exposure"])
    naive = two_leg(d, book, cash, lambda _x: arm["exposure"], months, 5.0)
    assert abs(naive["exposure"] - arm["exposure"]) > 1e-9
    assert abs(ctl["exposure"] - arm["exposure"]) < 1e-10
    assert abs(ctl["static_w"] - arm["exposure"]) > 1e-9


def test_matched_control_holds_a_constant_target(toy):
    """A control that itself timed anything would not be a null."""
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    ctl = matched_control(d, book, cash, months, 5.0, 0.7)
    held = [ctl["held"][x] for x in d if x in months]
    assert max(held) - min(held) < 1e-12          # every rebalance restores one weight


def test_matched_control_on_the_real_book_matches_to_1e_10(real):
    """The same guarantee on the series the report actually publishes."""
    d, cash = real["dates"], real["cash"]
    book = real["books"]["SPY"]["curve"]
    rets, cash_rets = curve_returns(book, d), curve_returns(cash, d)
    est = {"trail20": vm.trailing_vol_series(rets, V_WINDOW)}
    spec = next(s for s in arm_specs("SPY") if s["key"] == "V1")
    arm = run_scale_arm(spec, d, book, cash, est, rets, cash_rets, 5.0)
    ctl = matched_control(d, book, cash, set(month_starts(d)), 5.0, arm["exposure"])
    assert abs(ctl["exposure"] - arm["exposure"]) < 1e-10
    assert 0.6 < arm["exposure"] < 0.85


def test_a_deliberately_unmatched_control_is_caught(toy):
    """The instrument has teeth: a fully-invested 'control' — the comparison
    the registration forbids — is NOT matched, by a wide margin."""
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    pick = vol_target_pick(toy["rets"], lambda i: vol[i], 0.10, V_CAP)
    w_at, _wbd, _ = step_weights(d, months, pick, V_CAP)
    arm = two_leg(d, book, cash, w_at, months, 5.0)
    fully = two_leg(d, book, cash, lambda _x: 1.0, months, 5.0)
    assert fully["exposure"] - arm["exposure"] > 0.05


# =====================================================================================
# LOOK-AHEAD — the registration forbids full-sample quantiles
# =====================================================================================


def _mutate_future(vals: list, i: int, factor: float = 50.0) -> list:
    out = list(vals)
    for k in range(i + 1, len(out)):
        if out[k] is not None:
            out[k] = out[k] * factor
    return out


def test_expanding_thresholds_do_not_see_the_future(toy):
    """Regime labels up to index i must not move when everything after i does."""
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    base = vm.expanding_regimes(vol, 1 / 3, 2 / 3, min_history=100)
    i = 500
    mutated = vm.expanding_regimes(_mutate_future(vol, i), 1 / 3, 2 / 3, min_history=100)
    assert base[:i + 1] == mutated[:i + 1]
    assert any(x is not None for x in base[:i + 1])


def test_full_sample_thresholds_DO_see_the_future(toy):
    """The forbidden version fails the same test — which is why it is forbidden
    and why the test above is meaningful."""
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    base = vm.full_sample_regimes(vol, 1 / 3, 2 / 3)
    i = 500
    mutated = vm.full_sample_regimes(_mutate_future(vol, i), 1 / 3, 2 / 3)
    assert base[:i + 1] != mutated[:i + 1]


def test_fixed_thresholds_do_not_see_the_future(toy):
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    base = vm.fixed_regimes(vol, 0.20, 0.80, train_days=200)
    i = 600
    mutated = vm.fixed_regimes(_mutate_future(vol, i), 0.20, 0.80, train_days=200)
    assert base[:i + 1] == mutated[:i + 1]


def test_trailing_vol_uses_only_the_past(toy):
    r = toy["rets"]
    i = 400
    mutated = _mutate_future(r, i - 1)      # everything from index i onward
    assert vm.trailing_vol(r, i, V_WINDOW) == vm.trailing_vol(mutated, i, V_WINDOW)


def test_ewma_uses_only_the_past(toy):
    r = toy["rets"]
    i = 400
    a = vm.ewma_var_series(r, EWMA_LAMBDA, V_WINDOW)
    b = vm.ewma_var_series(_mutate_future(r, i - 1), EWMA_LAMBDA, V_WINDOW)
    assert a[:i + 1] == b[:i + 1]


def test_garch_walk_forward_uses_only_the_past(toy):
    """The forecast for date i must not move when returns from i onward move —
    parameters included, since the refits are on an expanding history."""
    r, d = toy["rets"], toy["dates"]
    i = 700
    a = vm.garch_walk_forward(r, d, init_days=300)["var"]
    b = vm.garch_walk_forward(_mutate_future(r, i - 1, 3.0), d, init_days=300)["var"]
    assert a[i] is not None
    for k in range(300, i + 1):
        assert a[k] == pytest.approx(b[k], rel=1e-12)


def test_vol_scaled_band_multiplier_uses_an_expanding_mean(toy):
    """V7's band multiplier divides by an EXPANDING mean. A full-sample mean
    would put tomorrow's vol into today's band."""
    mult = running_vol_mult(V_WINDOW)
    seen = []
    rets = toy["rets"]
    for i in range(1, 200):
        seen.append(mult(i, rets[:i]))
    # Early multipliers are ~1 (the expanding mean is dominated by the few
    # observations so far); a full-sample normalisation would not be.
    assert seen[V_WINDOW + 2] == pytest.approx(1.0, abs=0.35)
    assert any(abs(x - 1.0) > 0.05 for x in seen)


# =====================================================================================
# ENGINE EQUIVALENCE — round 8 must not have quietly changed the frozen engine
# =====================================================================================


def test_two_leg_reproduces_the_frozen_portfolio_engine(toy):
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    mine = two_leg(d, book, cash, lambda _x: 0.63, months, 7.0)
    theirs = portfolio(d, {"BOOK": book, "CASH": cash},
                       const({"BOOK": 0.63, "CASH": 0.37}),
                       rebal_dates=months, cost_bps=7.0)
    for x in d:
        assert mine["curve"][x] == theirs[x]


def test_vol_band_portfolio_reduces_to_the_frozen_engine(real):
    """With `vol_mult=None` the V7 engine must BE the frozen band engine, so the
    arm and its control differ in exactly one thing."""
    d = real["dates"]
    legs = build_legs(real["raw"], d, "T1")
    mine = vol_band_portfolio(d, legs["curves"], legs["target_at"],
                              band_rel=B5_BAND_REL,
                              cal_fallback_days=B5_CAL_FALLBACK_D,
                              cost_bps=BASE_COST_BPS, vol_mult=None)
    theirs = portfolio(d, legs["curves"], legs["target_at"], band_rel=B5_BAND_REL,
                       cal_fallback_days=B5_CAL_FALLBACK_D, cost_bps=BASE_COST_BPS)
    for x in d:
        assert mine["curve"][x] == theirs[x]


def test_vol_scaled_bands_actually_change_the_rebalance_schedule(real):
    d = real["dates"]
    legs = build_legs(real["raw"], d, "T1")
    scaled = vol_band_portfolio(d, legs["curves"], legs["target_at"],
                                band_rel=B5_BAND_REL,
                                cal_fallback_days=B5_CAL_FALLBACK_D,
                                cost_bps=BASE_COST_BPS, vol_mult=running_vol_mult())
    flat = vol_band_portfolio(d, legs["curves"], legs["target_at"], band_rel=B5_BAND_REL,
                              cal_fallback_days=B5_CAL_FALLBACK_D,
                              cost_bps=BASE_COST_BPS, vol_mult=None)
    assert scaled["n_rebal"] != flat["n_rebal"], "V7 would be a copy of its control"


def test_turnover_equals_the_traded_weight(toy):
    """Recomputed from an independent re-implementation of the drift, so the
    turnover figures the report prints are not the engine marking its own
    homework."""
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    pick = vol_target_pick(toy["rets"], lambda i: vol[i], 0.10, V_CAP)
    w_at, wbd, _ = step_weights(d, months, pick, V_CAP)
    run = two_leg(d, book, cash, w_at, months, 0.0)     # zero cost isolates the count

    manual, w = 0.0, wbd[d[0]]
    for a, b in zip(d[:-1], d[1:], strict=True):
        rb = book[b] / book[a] - 1
        rc = cash[b] / cash[a] - 1
        grown = w * (1 + rb) + (1 - w) * (1 + rc)
        w = w * (1 + rb) / grown                        # drifted weight at b
        if b in months:
            manual += abs(wbd[b] - w)
            w = wbd[b]
    assert run["turnover_total"] == pytest.approx(manual, rel=1e-9)
    assert run["n_rebal"] == len([x for x in d[1:] if x in months])


def test_zero_cost_and_high_cost_bracket_the_curve(toy):
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    pick = vol_target_pick(toy["rets"], lambda i: vol[i], 0.10, V_CAP)
    w_at, _wbd, _ = step_weights(d, months, pick, V_CAP)
    cheap = two_leg(d, book, cash, w_at, months, 5.0)["curve"][d[-1]]
    dear = two_leg(d, book, cash, w_at, months, 20.0)["curve"][d[-1]]
    assert dear < cheap


# =====================================================================================
# THE REGISTERED RULES — parameters, arm list, survival bar
# =====================================================================================


def test_registered_parameters_are_pinned():
    """These are the contract. A change here is a registration violation, not a
    refactor."""
    assert (V_TARGET, V_WINDOW, V_CAP) == (0.10, 20, 1.0)
    assert V5_TARGETS == (0.12, 0.15)
    assert V6_CAP == 1.5
    assert V8_WINDOW == 60
    assert EWMA_LAMBDA == 0.94
    assert COST_LEVELS == (5.0, 20.0)
    assert BASE_COST_BPS == 10.0
    assert BOOT_SEED == 20260822
    assert GARCH_INIT_DAYS == 756


def test_the_eight_registered_arms_exist_and_v7_only_where_a_band_rule_does():
    scale = {"V1", "V2", "V3", "V4", "V5-12", "V5-15", "V6", "V8"}
    for book in ("SPY", "B5-T1", "63/37", "30/70"):
        keys = {s["key"] for s in arm_specs(book)}
        assert scale <= keys, f"{book} is missing a registered arm"
        assert ("V7" in keys) == (book in ("B5-T1", "30/70")), (
            "V7 is registered on the 30/70 and B.5 band rules only")
    judged = {s["key"] for s in arm_specs("SPY") if s.get("judged", True)}
    assert "V3-WU" not in judged, "the warm-up twin is a diagnostic, never judged"


def test_arm_estimators_are_the_registered_ones():
    by = {s["key"]: s for s in arm_specs("B5-T1")}
    assert by["V1"]["est"] == "trail20" and by["V1"]["freq"] == "monthly"
    assert by["V2"]["freq"] == "daily"
    assert by["V3"]["est"] == "garch"
    assert by["V4"]["est"] == "ewma"
    assert by["V5-12"]["target"] == 0.12 and by["V5-15"]["target"] == 0.15
    assert by["V6"]["cap"] == V6_CAP
    assert by["V8"]["kind"] == "invvol"
    assert by["V7"]["kind"] == "band"


def _bar(sharpe=True, calmar=True, ci=True, reg=True, all_reg=True, wins_dd=5):
    return {"bar": {"beats_sharpe": sharpe, "beats_calmar": calmar,
                    "ci_excludes_zero": ci, "regimes_ge_3": reg,
                    "all_regimes_present": all_reg},
            "regime_wins_dd": wins_dd}


def test_survival_needs_every_condition_at_every_cost_level():
    good = {"costs": {"5bps": _bar(), "20bps": _bar()}}
    assert survives(good)["survives"] is True
    for kw in ("sharpe", "calmar", "ci", "reg"):
        bad = {"costs": {"5bps": _bar(), "20bps": _bar(**{kw: False})}}
        assert survives(bad)["survives"] is False, f"{kw} at 20 bps must be fatal"
        bad5 = {"costs": {"5bps": _bar(**{kw: False}), "20bps": _bar()}}
        assert survives(bad5)["survives"] is False


def test_a_book_missing_named_regimes_cannot_survive():
    """The 2016+ blend gets reported, not a softer bar."""
    part = {"costs": {"5bps": _bar(all_reg=False), "20bps": _bar(all_reg=False)}}
    out = survives(part)
    assert out["adjudicable"] is False
    assert out["survives"] is False


def test_both_regime_readings_are_reported():
    part = {"costs": {"5bps": _bar(reg=False, wins_dd=5), "20bps": _bar(reg=False, wins_dd=5)}}
    out = survives(part)
    assert out["survives"] is False
    assert out["survives_dd_reading"] is True
    assert out["readings_agree"] is False


# =====================================================================================
# THE VOL MODELS
# =====================================================================================


def test_trailing_vol_is_the_c4_rule():
    """`trailing_vol(rets, i, w)` is stdev(rets[i-w:i]) * sqrt(252) — the same
    window C4 used, ending with the return INTO dates[i]."""
    r = [0.01, -0.02, 0.03, -0.01, 0.005, 0.02]
    got = vm.trailing_vol(r, 4, 4)
    want = statistics.stdev(r[0:4]) * math.sqrt(252)
    assert got == pytest.approx(want)
    assert vm.trailing_vol(r, 2, 5) is None


def test_ewma_recursion_by_hand():
    r = [0.01] * 25
    out = vm.ewma_var_series(r, 0.94, 20)
    seed = statistics.pvariance(r[:20])
    assert out[20] == pytest.approx(seed)
    assert out[21] == pytest.approx(0.94 * seed + 0.06 * r[20] ** 2)
    assert out[19] is None


def test_garch_recovers_known_parameters():
    """Simulate from a known GARCH(1,1) and check the hand-rolled MLE finds it.
    Loose tolerances — this is a sanity gate on the optimiser, not a claim
    about estimator efficiency."""
    rng = random.Random(7)
    omega, alpha, beta = 2e-6, 0.09, 0.88
    h = omega / (1 - alpha - beta)
    rets = []
    for _ in range(4000):
        e = rng.gauss(0.0, 1.0) * math.sqrt(h)
        rets.append(e)
        h = omega + alpha * e * e + beta * h
    f = vm.garch_fit(rets)
    assert 0.03 < f["alpha"] < 0.18
    assert 0.78 < f["beta"] < 0.95
    assert 0.93 < f["persistence"] < 1.0


def test_garch_fit_is_deterministic(toy):
    a = vm.garch_fit(toy["rets"][:400])
    b = vm.garch_fit(toy["rets"][:400])
    assert a == b


def test_qlike_is_minimised_at_the_true_variance():
    true_var = 4e-4
    losses = {h: statistics.fmean([vm.qlike(h, true_var * z) for z in (0.5, 1.0, 1.5, 2.0)])
              for h in (1e-4, 2e-4, 4e-4, 8e-4, 1.6e-3)}
    assert min(losses, key=losses.get) == 4e-4


def test_score_forecasts_arithmetic():
    rets = [0.01, -0.02, 0.03]
    var_hat = [1e-4, 4e-4, 9e-4, None]
    sc = vm.score_forecasts(var_hat, rets, [0, 1, 2])
    want_rmse = math.sqrt(statistics.fmean(
        [(1e-4 - 1e-4) ** 2, (4e-4 - 4e-4) ** 2, (9e-4 - 9e-4) ** 2]))
    assert sc["n"] == 3
    assert sc["rmse"] == pytest.approx(want_rmse)


def test_wilson_interval_known_values():
    lo, hi = vm.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=5e-4)
    assert hi == pytest.approx(0.5962, abs=5e-4)
    assert vm.wilson(0, 0) != vm.wilson(0, 0) or True     # nan-safe, does not raise
    lo2, hi2 = vm.wilson(10, 10)
    assert hi2 == pytest.approx(1.0, abs=1e-9)
    assert lo2 > 0.6


def test_persistence_counting_by_hand():
    labels = ["low", "low", "high", "low", "low", "low", None, "low"]
    p1 = vm.persistence(labels, "low", 1)
    # index 0->1 low (hit), 1->2 high (miss), 3->4 low (hit), 4->5 low (hit),
    # 5->6 None (excluded), 7 has no i+1.
    assert (p1["k"], p1["n"]) == (3, 4)
    assert p1["p"] == pytest.approx(0.75)


def test_autocorr_of_a_constant_period_signal():
    x = [math.sin(i) for i in range(300)]
    assert vm.autocorr(x, 0) == pytest.approx(1.0)
    assert abs(vm.autocorr([1.0, -1.0] * 150, 1) + 1.0) < 0.02


def test_expanding_regimes_respect_min_history(toy):
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    lab = vm.expanding_regimes(vol, 1 / 3, 2 / 3, min_history=300)
    labelled = [i for i, x in enumerate(lab) if x is not None]
    assert labelled and labelled[0] >= 300
    assert set(x for x in lab if x) <= {"low", "mid", "high"}


# =====================================================================================
# WEIGHT RULES
# =====================================================================================


def test_step_weights_hold_flat_between_decisions(toy):
    d = toy["dates"]
    months = set(month_starts(d))
    calls = []

    def pick(i):
        calls.append(i)
        return 0.1 * (len(calls) % 5)

    w_at, wbd, decided = step_weights(d, months, pick, 0.5)
    assert len(calls) == 1 + len(months)          # day 0 plus every scheduled date
    assert len(decided) == len(calls)
    for a, b in zip(d[:-1], d[1:], strict=True):
        if b not in months:
            assert wbd[a] == wbd[b]


def test_step_weights_fall_back_to_the_registered_default(toy):
    d = toy["dates"]
    w_at, wbd, _ = step_weights(d, set(month_starts(d)), lambda _i: None, V_CAP)
    assert set(wbd.values()) == {V_CAP}


def test_vol_target_rule_is_min_cap_target_over_vol():
    r = [0.0] * 30
    vol = {5: 0.20, 6: 0.05, 7: None}
    pick = vol_target_pick(r, lambda i: vol.get(i), 0.10, 1.0)
    assert pick(5) == pytest.approx(0.5)          # 0.10 / 0.20
    assert pick(6) == pytest.approx(1.0)          # capped, not 2.0
    assert pick(7) is None
    lev = vol_target_pick(r, lambda i: vol.get(i), 0.10, 1.5)
    assert lev(6) == pytest.approx(1.5)


def test_inverse_vol_is_the_two_asset_rule_and_is_degenerate_against_cash():
    """V8 as registered. The cash leg's vol is ~0, so the rule holds almost
    nothing in the book — a RESULT the report states, pinned here so nobody
    'fixes' it into something else."""
    rng = random.Random(3)
    book = [rng.gauss(0, 0.012) for _ in range(200)]
    cash = [0.00002 + rng.gauss(0, 2e-6) for _ in range(200)]
    pick = inverse_vol_pick(book, cash, 60)
    w = pick(100)
    vb = vm.trailing_vol(book, 100, 60)
    vc = vm.trailing_vol(cash, 100, 60)
    assert w == pytest.approx((1 / vb) / (1 / vb + 1 / vc))
    assert w < 0.10
    assert pick(10) is None


# =====================================================================================
# JUDGMENT
# =====================================================================================


def test_judge_scores_an_arm_against_the_control_it_is_given(toy):
    d, book, cash = toy["dates"], toy["book"], toy["cash"]
    months = set(month_starts(d))
    bil = curve_returns(cash, d)
    spy = curve_returns(book, d)
    vol = vm.trailing_vol_series(toy["rets"], V_WINDOW)
    pick = vol_target_pick(toy["rets"], lambda i: vol[i], 0.10, V_CAP)
    w_at, _wbd, _ = step_weights(d, months, pick, V_CAP)
    arm = two_leg(d, book, cash, w_at, months, 5.0)
    ctl = matched_control(d, book, cash, months, 5.0, arm["exposure"])
    j = judge(arm, ctl, d, bil, spy, draws=60)
    assert j["d_sharpe_bil"] == pytest.approx(
        j["metrics"]["sharpe_bil"] - j["control_metrics"]["sharpe_bil"])
    assert j["d_calmar"] == pytest.approx(j["metrics"]["calmar"] - j["control_metrics"]["calmar"])
    assert j["boot"]["ci_lo"] <= j["boot"]["ci_hi"]
    # This toy window contains none of the named 2006-2026 regimes.
    assert j["regimes_live"] == 0
    assert j["bar"]["all_regimes_present"] is False


def test_regimes_outside_the_window_are_not_truncated_into_the_window(real):
    """A 2016+ book must report the GFC as absent, never as a 2016-2019 stub
    wearing a crisis label."""
    d = [x for x in real["dates"] if x >= "2016-01-04"]
    book = {x: real["books"]["SPY"]["curve"][x] for x in d}
    cash = {x: real["cash"][x] for x in d}
    bil = curve_returns(cash, d)
    months = set(month_starts(d))
    arm = two_leg(d, book, cash, lambda _x: 0.8, months, 5.0)
    ctl = matched_control(d, book, cash, months, 5.0, arm["exposure"])
    j = judge(arm, ctl, d, bil, curve_returns(book, d), draws=40)
    assert j["regimes"]["GFC"] is None
    assert j["regimes"]["recovery"] is None
    assert j["regimes"]["COVID"] is not None
    assert j["regimes_live"] == 3


# =====================================================================================
# THE BOOKS
# =====================================================================================


def test_the_three_books_reproduce_round_7(real):
    """B.5-T1 and SPY must be round 7's published series to the printed
    precision, or round 8 is measuring a different book than it claims."""
    from scripts.backtest_core_variants import metrics

    d, cash = real["dates"], real["cash"]
    bil = curve_returns(cash, d)
    spy_r = curve_returns(real["books"]["SPY"]["curve"], d)
    m_spy = metrics(real["books"]["SPY"]["curve"], d, bil, spy_r)
    m_b5 = metrics(real["books"]["B5-T1"]["curve"], d, bil, spy_r)
    assert round(m_spy["cagr"] * 100, 2) == 11.16
    assert round(m_spy["max_dd"] * 100, 2) == 55.19
    assert round(m_b5["cagr"] * 100, 2) == 8.89
    assert round(m_b5["max_dd"] * 100, 2) == 38.97


def test_the_63_37_book_is_equity_share_matched(real):
    assert real["books"]["63/37"]["equity_share"] == pytest.approx(0.63)
    assert real["books"]["B5-T1"]["equity_share"] == pytest.approx(0.63, abs=0.02)
    assert real["books"]["SPY"]["equity_share"] == 1.0


def test_the_live_blend_uses_the_live_rule():
    assert LIVE_BAND == 0.05
