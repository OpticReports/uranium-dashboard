"""Round-4 core-variant harness: metric conventions, the portfolio engine and
the paired block bootstrap.

These are the merge-blocking gates on the machinery, not on the results. Every
assertion is a KNOWN ANSWER derived by hand or by an identity, so a convention
change (the counter-agent's Sortino objection is the live example) breaks a
test instead of silently moving a campaign verdict. Nothing here touches the
network or the price cache.
"""
from __future__ import annotations

import math

import pytest

from scripts.backtest_core_variants import (
    C5_SLEEVE_W,
    INCUMBENT_KEYS,
    LIVE_SLEEVE_W,
    VARIANTS,
    Ctx,
    Variant,
    _trailing,
    block_bootstrap_sharpe_diff,
    block_starts,
    boot_ci,
    cagr,
    const,
    curve_returns,
    downside_deviation,
    evaluate,
    excludes_zero,
    max_drawdown,
    metrics,
    month_starts,
    monthly_weights,
    pearson,
    portfolio,
    quarter_starts,
    sharpe,
    sleeve_idle_routed,
    sortino,
    thirds,
)

ANN = math.sqrt(252)


def _dates(n: int) -> list[str]:
    """n consecutive ISO dates (weekend-agnostic — the engine only orders)."""
    import datetime as dt
    d0 = dt.date(2021, 1, 4)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _curve(dates: list[str], rets: list[float], start: float = 1.0) -> dict[str, float]:
    out, lvl = {dates[0]: start}, start
    for d, r in zip(dates[1:], rets, strict=True):
        lvl *= 1 + r
        out[d] = lvl
    return out


# --- Sortino convention (counter-agent m1) -----------------------------------------

def test_downside_deviation_divides_by_N_not_by_negative_count():
    # One -10% day in five. Standard convention: sqrt(0.01 / 5) = 0.0447.
    # The convention the harness REJECTS divides by the 1 negative day and
    # would give 0.10 — a 2.24x difference that inflates Sortino.
    rets = [0.01, 0.02, -0.10, 0.03, 0.01]
    assert downside_deviation(rets) == pytest.approx(math.sqrt(0.01 / 5))
    wrong = math.sqrt(0.01 / 1)
    assert downside_deviation(rets) != pytest.approx(wrong)
    assert wrong / downside_deviation(rets) == pytest.approx(math.sqrt(5))


def test_downside_deviation_ignores_upside_and_is_zero_without_losses():
    assert downside_deviation([0.01, 0.02, 0.03]) == 0.0
    # a zero return is not a loss
    assert downside_deviation([0.0, 0.0, -0.02]) == pytest.approx(
        math.sqrt(0.02 ** 2 / 3))


def test_sortino_known_answer():
    rets = [0.01, 0.02, -0.10, 0.03, 0.01]
    mean = sum(rets) / 5
    assert sortino(rets) == pytest.approx(mean / math.sqrt(0.01 / 5) * ANN)


def test_sortino_and_sharpe_share_a_basis_when_rf_is_given():
    rets = [0.01, 0.02, -0.10, 0.03, 0.01]
    rf = [0.0002] * 5
    ex = [a - b for a, b in zip(rets, rf, strict=True)]
    assert sharpe(rets, rf) == pytest.approx(sharpe(ex))
    assert sortino(rets, rf) == pytest.approx(sortino(ex))
    # and the two bases genuinely differ, so labelling them matters
    assert sharpe(rets, rf) != pytest.approx(sharpe(rets))


# --- the rest of the metric set ----------------------------------------------------

def test_sharpe_known_answer_and_scale_invariance():
    rets = [0.01, -0.01, 0.02, 0.0, 0.01]
    mean = sum(rets) / 5
    sd = (sum((r - mean) ** 2 for r in rets) / 4) ** 0.5   # ddof=1
    assert sharpe(rets) == pytest.approx(mean / sd * ANN)


def test_sharpe_is_nan_on_a_constant_series():
    assert math.isnan(sharpe([0.01] * 10))


def test_max_drawdown_known_answer_and_no_phantom_peak():
    # 100 -> 120 -> 90: the trough is 25% below the 120 peak.
    assert max_drawdown([100.0, 120.0, 90.0, 110.0]) == pytest.approx(0.25)
    # The peak starts at the curve's OWN first value: a monotone rise from a
    # low start has no drawdown, even though earlier history was higher.
    assert max_drawdown([50.0, 60.0, 70.0]) == 0.0


def test_cagr_calendar_annualized():
    # exactly one 365.25-day year would double -> 100%; 365 days is a hair more
    got = cagr([1.0, 2.0], "2021-01-01", "2022-01-01")
    assert got == pytest.approx(2 ** (365.25 / 365) - 1)


def test_pearson_identity_and_inverse():
    a = [0.01, -0.02, 0.03, 0.005]
    assert pearson(a, a) == pytest.approx(1.0)
    assert pearson(a, [-x for x in a]) == pytest.approx(-1.0)


def test_metrics_bundle_reports_both_bases():
    dates = _dates(60)
    rets = [0.002 if i % 3 else -0.003 for i in range(59)]
    curve = _curve(dates, rets)
    bil = [0.0001] * 59
    m = metrics(curve, dates, bil, rets)
    for key in ("sharpe_rf0", "sharpe_bil", "sortino_rf0", "sortino_bil",
                "cagr", "max_dd", "vol", "calmar", "corr_spy"):
        assert key in m
    assert m["sharpe_rf0"] > m["sharpe_bil"]        # rf drag is positive
    assert m["corr_spy"] == pytest.approx(1.0)      # compared against itself


# --- calendar helpers ---------------------------------------------------------------

def test_month_and_quarter_starts():
    dates = ["2021-01-04", "2021-01-29", "2021-02-01", "2021-03-01",
             "2021-04-01", "2021-04-30", "2021-07-01"]
    assert month_starts(dates) == ["2021-02-01", "2021-03-01", "2021-04-01",
                                   "2021-07-01"]
    assert quarter_starts(dates) == ["2021-04-01", "2021-07-01"]
    # the first date is never a rebalance date — it is the initial purchase
    assert dates[0] not in month_starts(dates)


def test_thirds_are_equal_and_contiguous():
    dates = _dates(31)
    a, b, c = thirds(dates)
    # consecutive chunks share their boundary date so returns stay contiguous
    assert a[-1] == b[0] and b[-1] == c[0]
    assert a[0] == dates[0] and c[-1] == dates[-1]
    assert abs(len(a) - len(c)) <= 2


# --- portfolio engine ---------------------------------------------------------------

def test_flat_legs_produce_a_flat_book_and_charge_nothing():
    dates = _dates(50)
    flat = {d: 10.0 for d in dates}
    other = {d: 3.0 for d in dates}
    out = portfolio(dates, {"A": flat, "B": other},
                    const({"A": 0.5, "B": 0.5}), band=0.05)
    assert all(v == pytest.approx(1.0) for v in out.values())


def test_single_leg_book_tracks_that_leg_exactly():
    dates = _dates(40)
    curve = _curve(dates, [0.01, -0.005] * 19 + [0.02])
    out = portfolio(dates, {"A": curve}, const({"A": 1.0}), band=0.05)
    ratio = out[dates[-1]] / out[dates[0]]
    assert ratio == pytest.approx(curve[dates[-1]] / curve[dates[0]])


def test_rebalance_costs_are_charged_on_one_side_of_traded_notional():
    # Two legs, 50/50, band 0. A doubles on day 1, so pre-trade weights are
    # 2/3 and 1/3; traded notional is 0.5 * (|1/6| + |1/6|) = 1/6 of equity and
    # the 10bp charge is 1/6 * 10bp of the pre-cost equity.
    dates = _dates(2)
    a = {dates[0]: 1.0, dates[1]: 2.0}
    b = {dates[0]: 1.0, dates[1]: 1.0}
    out = portfolio(dates, {"A": a, "B": b}, const({"A": 0.5, "B": 0.5}), band=0.0)
    pre = 1.5
    assert out[dates[1]] == pytest.approx(pre - pre * (1 / 6) * 10.0 / 1e4)


def test_a_wide_band_never_trades_and_beats_a_zero_band_on_costs():
    dates = _dates(120)
    a = _curve(dates, [0.004] * 119)
    b = _curve(dates, [0.001] * 119)
    legs = {"A": a, "B": b}
    tight = portfolio(dates, legs, const({"A": 0.5, "B": 0.5}), band=0.0)
    wide = portfolio(dates, legs, const({"A": 0.5, "B": 0.5}), band=0.99)
    assert wide[dates[-1]] > tight[dates[-1]]


def test_scheduled_rebalance_dates_fire():
    dates = _dates(90)
    a = _curve(dates, [0.01] * 89)
    b = _curve(dates, [0.0] * 89)
    legs = {"A": a, "B": b}
    never = portfolio(dates, legs, const({"A": 0.5, "B": 0.5}))
    monthly = portfolio(dates, legs, const({"A": 0.5, "B": 0.5}),
                        rebal_dates=month_starts(dates))
    # rebalancing out of the winner must cost return AND trading fees here
    assert monthly[dates[-1]] < never[dates[-1]]


def test_time_varying_target_can_exit_a_leg_entirely():
    dates = _dates(30)
    a = _curve(dates, [0.05] * 29)          # a leg that rips
    b = {d: 1.0 for d in dates}             # and one that does nothing
    half = dates[15]

    def target(d: str) -> dict[str, float]:
        return {"A": 0.5, "B": 0.5} if d < half else {"A": 0.0, "B": 1.0}

    out = portfolio(dates, {"A": a, "B": b}, target, band=0.05)
    tail = [out[d] for d in dates if d >= half]
    assert tail[1:] == pytest.approx(tail[:-1])   # flat once fully in B


# --- paired block bootstrap ---------------------------------------------------------

def test_block_starts_cover_exactly_n_observations():
    import random
    rng = random.Random(1)
    for n in (100, 1432, 21, 20):
        blocks = block_starts(n, 21, rng)
        assert sum(ln for _, ln in blocks) == n
        assert all(0 <= s < n for s, _ in blocks)
        assert all(ln <= 21 for _, ln in blocks)


def test_identical_series_give_a_zero_centred_ci_containing_zero():
    """The known-answer test: two IDENTICAL series cannot differ under a PAIRED
    resample, so every draw is exactly 0, the CI is [0, 0], it contains zero and
    it is centred on zero. If the pairing is ever broken this test fails."""
    rets = [0.01, -0.02, 0.015, 0.0, -0.005] * 40
    boot = block_bootstrap_sharpe_diff(rets, list(rets), block=21, draws=500)
    lo, hi = boot_ci(boot)
    assert boot["point"] == pytest.approx(0.0, abs=1e-12)
    assert lo == pytest.approx(0.0, abs=1e-12)
    assert hi == pytest.approx(0.0, abs=1e-12)
    assert (lo + hi) / 2 == pytest.approx(0.0, abs=1e-12)
    assert not excludes_zero((lo, hi))
    assert boot["p_two_sided"] == pytest.approx(1.0)


def test_bootstrap_is_deterministic_under_a_fixed_seed():
    a = [0.01, -0.02, 0.015, 0.0, -0.005] * 40
    b = [0.008, -0.01, 0.02, 0.001, -0.004] * 40
    one = block_bootstrap_sharpe_diff(a, b, draws=300, seed=7)
    two = block_bootstrap_sharpe_diff(a, b, draws=300, seed=7)
    other = block_bootstrap_sharpe_diff(a, b, draws=300, seed=8)
    assert one["dist"] == two["dist"]
    assert one["dist"] != other["dist"]


def test_bootstrap_ci_brackets_the_point_estimate_and_widens_with_confidence():
    a = [0.01, -0.02, 0.015, 0.0, -0.005] * 40
    b = [0.008, -0.01, 0.02, 0.001, -0.004] * 40
    boot = block_bootstrap_sharpe_diff(a, b, draws=1000, seed=11)
    lo95, hi95 = boot_ci(boot, 0.95)
    lo99, hi99 = boot_ci(boot, 0.9967)          # the Bonferroni bar at N=15
    assert lo95 <= boot["point"] <= hi95
    assert lo99 <= lo95 and hi99 >= hi95         # adjusted bar is strictly harder
    assert len(boot["dist"]) == 1000


def test_a_dominating_series_gives_a_positive_ci_that_excludes_zero():
    """A series that beats its comparator on EVERY day must survive resampling:
    the difference is positive in every block, so the CI cannot straddle zero.
    This is the counterpart to the identical-series test."""
    base = [0.01, -0.02, 0.015, 0.0, -0.005] * 40
    better = [r + 0.01 for r in base]           # same shape, higher mean
    boot = block_bootstrap_sharpe_diff(better, base, draws=500, seed=3)
    lo, hi = boot_ci(boot)
    assert boot["point"] > 0
    assert excludes_zero((lo, hi))
    assert lo > 0
    assert boot["p_two_sided"] < 0.05


def test_sign_flips_when_the_arguments_are_swapped():
    a = [0.01, -0.02, 0.015, 0.0, -0.005] * 40
    b = [r + 0.004 for r in a]
    fwd = block_bootstrap_sharpe_diff(a, b, draws=400, seed=5)
    rev = block_bootstrap_sharpe_diff(b, a, draws=400, seed=5)
    assert fwd["point"] == pytest.approx(-rev["point"])
    assert boot_ci(fwd)[0] == pytest.approx(-boot_ci(rev)[1])


def test_paired_bootstrap_rejects_mismatched_lengths():
    with pytest.raises(AssertionError):
        block_bootstrap_sharpe_diff([0.01] * 10, [0.01] * 9)


# --- registry -----------------------------------------------------------------------

def test_registry_holds_exactly_the_registered_round_4_variants():
    """C1..C8 as pre-registered, and nothing else. C1, C2 and C6 register more
    than one parameterization, which is why the multiple-comparison count is
    the number of ARMS, not the number of letters."""
    groups = sorted({v.group for v in VARIANTS.values()})
    assert groups == ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]
    counts = {g: sum(1 for v in VARIANTS.values() if v.group == g) for g in groups}
    assert counts == {"C1": 4, "C2": 2, "C3": 1, "C4": 1, "C5": 1,
                      "C6": 4, "C7": 1, "C8": 1}
    assert len(VARIANTS) == 15
    assert all(isinstance(v, Variant) and callable(v.fn) for v in VARIANTS.values())


def test_incumbents_are_the_three_registered_ones():
    assert INCUMBENT_KEYS == ["INC-B5", "INC-3070SPY", "INC-SPY"]


def test_curve_returns_matches_a_hand_computed_series():
    dates = _dates(4)
    curve = {dates[0]: 100.0, dates[1]: 110.0, dates[2]: 99.0, dates[3]: 99.0}
    assert curve_returns(curve, dates) == pytest.approx([0.1, -0.1, 0.0])


# --- the survival bar itself ---------------------------------------------------
# The round-4 counter-agent's m6: the ONE function that produces a verdict had
# no test. These are known-answer gates on `evaluate`, built from hand-made
# metric dicts so no price data is touched.

def _m(sharpe_bil: float, sortino_bil: float) -> dict:
    """The only fields `evaluate` reads, plus rf=0 copies for the flag."""
    return {"sharpe_bil": sharpe_bil, "sortino_bil": sortino_bil,
            "sharpe_rf0": sharpe_bil, "sortino_rf0": sortino_bil}


def _boot(lo: float, hi: float, point: float) -> dict:
    """A bootstrap result whose percentile interval is exactly [lo, hi]."""
    n = 4001
    dist = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    le = sum(1 for d in dist if d <= 0) / n
    ge = sum(1 for d in dist if d >= 0) / n
    return {"point": point, "dist": dist, "draws": n, "block": 21, "seed": 0,
            "p_two_sided": min(1.0, 2 * min(le, ge))}


def _bar(*, v=1.10, i=1.00, wins=3, synth_v=1.0, synth_i=1.0,
         ci=(0.05, 0.20), point=0.10) -> dict:
    subs_v = [_m(v, v)] * 3
    subs_i = [_m(i, i)] * 3
    for k in range(3 - wins):                 # turn the last `3-wins` into losses
        subs_v[2 - k] = _m(i - 0.5, i - 0.5)
    return evaluate(_m(v, v), subs_v, _m(synth_v, synth_v),
                    _m(i, i), subs_i, _m(synth_i, synth_i),
                    _boot(ci[0], ci[1], point))


def test_evaluate_survives_only_when_all_four_criteria_hold():
    good = _bar()
    assert good["survives"] is True
    assert (good["c1_sharpe_and_sortino"], good["c2_ci_excludes_zero"],
            good["c3_subperiods"], good["c4_synthetic"]) == (True, True, True, True)
    assert good["c3_wins"] == 3


@pytest.mark.parametrize("kw", [
    {"v": 0.90},                     # criterion 1: loses on Sharpe/Sortino
    {"ci": (-0.05, 0.20)},           # criterion 2: interval spans zero
    {"wins": 1},                     # criterion 3: only 1 of 3 sub-periods
    {"synth_v": 0.80, "synth_i": 1.00},   # criterion 4: loses synth by 0.20
])
def test_evaluate_fails_when_any_single_criterion_fails(kw):
    assert _bar(**kw)["survives"] is False


def test_criterion_1_needs_sharpe_AND_sortino_not_either():
    """A variant that wins Sharpe but loses Sortino does NOT clear criterion 1."""
    v = evaluate(_m(1.10, 0.90), [_m(1.10, 0.90)] * 3, _m(1.0, 1.0),
                 _m(1.00, 1.00), [_m(1.00, 1.00)] * 3, _m(1.0, 1.0),
                 _boot(0.05, 0.20, 0.10))
    assert v["c1_sharpe_and_sortino"] is False and v["survives"] is False


def test_criterion_3_needs_two_of_three_and_counts_them():
    assert _bar(wins=2)["c3_subperiods"] is True
    assert _bar(wins=2)["c3_wins"] == 2
    assert _bar(wins=1)["c3_subperiods"] is False


def test_criterion_4_tolerates_a_0_10_synthetic_loss_but_not_more():
    assert _bar(synth_v=0.90, synth_i=1.00)["c4_synthetic"] is True
    assert _bar(synth_v=0.89, synth_i=1.00)["c4_synthetic"] is False


def test_evaluate_reports_the_rf0_flip_without_letting_it_move_the_bar():
    """rf=0 is reported alongside; the verdict stays on the BIL basis."""
    v_real = {"sharpe_bil": 0.90, "sortino_bil": 0.90,
              "sharpe_rf0": 1.10, "sortino_rf0": 1.10}
    i_real = _m(1.00, 1.00)
    v = evaluate(v_real, [v_real] * 3, _m(1.0, 1.0), i_real, [i_real] * 3,
                 _m(1.0, 1.0), _boot(0.05, 0.20, 0.10))
    assert v["c1_sharpe_and_sortino"] is False    # adjudicated on BIL
    assert v["c1_on_rf0"] is True                 # and the flip is disclosed
    assert v["survives"] is False


# --- C5's gate, the idle-cash router, monthly weights, _trailing ----------------

def _ctx(n: int, *, sleeve=None, core=None, bil=None, gate=None,
         idle=None) -> Ctx:
    """A minimal Ctx with hand-made legs — no network, no price cache."""
    dates = _dates(n)
    one = {d: 1.0 for d in dates}

    def lvl(rets):
        out, v = {dates[0]: 1.0}, 1.0
        for d, r in zip(dates[1:], rets):
            v *= 1 + r
            out[d] = v
        return out

    ctx = Ctx("real", "TEST", dates, {},
              core=lvl(core) if core else dict(one),
              sleeve=lvl(sleeve) if sleeve else dict(one),
              spy=dict(one), bil=lvl(bil) if bil else dict(one),
              gate={d: (gate[i] if gate else True) for i, d in enumerate(dates)},
              idle_frac={d: (idle[i] if idle else 0.0)
                         for i, d in enumerate(dates)})
    ctx.bil_rets = curve_returns(ctx.bil, dates)
    ctx.spy_rets = curve_returns(ctx.spy, dates)
    ctx.months = month_starts(dates)
    ctx.quarters = quarter_starts(dates)
    return ctx


def test_c5_gate_holds_the_sleeve_when_ON_and_drops_it_to_zero_when_OFF():
    """The gate is a hard 20%/0% switch and OFF sends the proceeds to the CORE.
    With a flat core: an ON day carries exactly C5_SLEEVE_W of the sleeve's
    move, and once the gate has been OFF through a rebalance the book is pure
    core, so a later sleeve move cannot touch it at all."""
    ctx = _ctx(5, sleeve=[0.0, -0.10, -0.10, -0.10],
               gate=[True, True, True, False, False])
    r = curve_returns(VARIANTS["C5"].fn(ctx), ctx.dates)
    assert r[1] == pytest.approx(-0.10 * C5_SLEEVE_W, abs=1e-12)   # ON, no breach
    assert r[2] < 0                                    # OFF: sells into the core
    assert r[3] == pytest.approx(0.0, abs=1e-12)       # and is then immune


def test_sleeve_idle_routed_credits_the_prior_close_idle_fraction():
    """r_sleeve + idle_frac[prior] * r_route, compounded — nothing else."""
    ctx = _ctx(4, sleeve=[0.0, 0.10, 0.0], core=[0.20, 0.20, 0.20],
               idle=[1.0, 0.5, 0.0, 0.0])
    r = curve_returns(sleeve_idle_routed(ctx, "CORE"), ctx.dates)
    assert r == pytest.approx([0.0 + 1.0 * 0.20, 0.10 + 0.5 * 0.20,
                               0.0 + 0.0 * 0.20], abs=1e-12)


def test_sleeve_idle_routed_to_BIL_uses_the_cash_leg_not_the_core():
    ctx = _ctx(3, sleeve=[0.0, 0.0], core=[0.20, 0.20], bil=[0.01, 0.01],
               idle=[1.0, 1.0, 1.0])
    assert curve_returns(sleeve_idle_routed(ctx, "BIL"), ctx.dates) == \
        pytest.approx([0.01, 0.01], abs=1e-12)


def test_sleeve_idle_routed_is_the_identity_when_nothing_is_idle():
    ctx = _ctx(5, sleeve=[0.03, -0.02, 0.01, 0.0], core=[0.5] * 4,
               idle=[0.0] * 5)
    assert curve_returns(sleeve_idle_routed(ctx, "CORE"), ctx.dates) == \
        pytest.approx(curve_returns(ctx.sleeve, ctx.dates), abs=1e-12)


def test_monthly_weights_redecides_only_on_month_starts_and_holds_between():
    ctx = _ctx(70)
    calls: list[int] = []

    def pick(i: int) -> float:
        calls.append(i)
        return 0.10 + 0.01 * len(calls)

    target = monthly_weights(ctx, pick, LIVE_SLEEVE_W)
    seen = [target(d)["SLEEVE"] for d in ctx.dates]
    # one decision on day 0 plus one per month start, and the weight is
    # piecewise-constant with exactly that many distinct steps
    assert len(calls) == 1 + len(ctx.months)
    steps = sum(1 for a, b in zip(seen, seen[1:]) if a != b)
    assert steps == len(ctx.months)
    assert all(d in (ctx.dates[0], *ctx.months)
               for d, a, b in zip(ctx.dates[1:], seen, seen[1:]) if a != b)


def test_monthly_weights_falls_back_to_the_default_during_warm_up():
    ctx = _ctx(30)
    target = monthly_weights(ctx, lambda _i: None, LIVE_SLEEVE_W)
    assert {target(d)["SLEEVE"] for d in ctx.dates} == {LIVE_SLEEVE_W}
    assert all(target(d)["CORE"] == 1 - LIVE_SLEEVE_W for d in ctx.dates)


def test_trailing_window_ends_with_the_return_INTO_dates_i():
    """The docstring convention, pinned: rets[i-window:i], so the last element
    is the return into dates[i] itself (the engine's same-close convention),
    and the window is None until `window` returns exist."""
    rets = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert _trailing(rets, 3, 3) == [0.0, 1.0, 2.0]
    assert _trailing(rets, 5, 2) == [3.0, 4.0]
    assert _trailing(rets, 2, 3) is None
    assert _trailing(rets, 3, 3)[-1] == rets[2]   # the return INTO dates[3]
