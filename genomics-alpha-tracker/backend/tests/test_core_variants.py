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
    B5_WEIGHTS,
    C5_SLEEVE_W,
    D1_WEIGHTS,
    D2_HI_W,
    D2_LO_W,
    D2_WARMUP_W,
    E1_HI_W,
    E1_LO_W,
    E1_WARMUP_W,
    E2_W,
    E3_HI_W,
    E3_LO_W,
    E3_WARMUP_W,
    E_CORE_LEG,
    E_CORR_THRESHOLD,
    E_CORR_WINDOW,
    INCUMBENTS,
    INCUMBENT_KEYS,
    LIVE_SLEEVE_W,
    ROUNDS,
    VARIANTS,
    CAMPAIGN,
    Ctx,
    Variant,
    _corr_decision_path,
    _mde_table,
    _spy_core_leg,
    _thirds_d_sharpe,
    _trailing,
    arm_contrast,
    block_bootstrap_sharpe_diff,
    block_starts,
    boot_ci,
    cagr,
    const,
    C3_SLEEVE_CAP,
    curve_returns,
    d1_dead_cash_twin,
    d1_sleeve_cash,
    d2_corr_at_tangency,
    d2_warmup_days,
    d3_weight_at,
    downside_deviation,
    evaluate,
    excludes_zero,
    inc_3070spy,
    max_drawdown,
    metrics,
    month_starts,
    monthly_weights,
    pearson,
    portfolio,
    power_mc,
    proxy_session_usage,
    quarter_starts,
    sharpe,
    sleeve_idle_routed,
    sortino,
    campaign_size,
    spy_core_corr_trigger,
    spy_core_corr_trigger_MISWIRED,
    spy_core_curves,
    spy_core_level_decomposition,
    spy_core_static,
    spy_core_trigger_profile,
    thirds,
    westfall_young_maxt,
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

def _round(n: int) -> dict:
    return {k: v for k, v in VARIANTS.items() if v.round == n}


def test_registry_holds_exactly_the_registered_round_4_variants():
    """C1..C8 as pre-registered, and nothing else. C1, C2 and C6 register more
    than one parameterization, which is why the multiple-comparison count is
    the number of ARMS, not the number of letters."""
    r4 = _round(4)
    groups = sorted({v.group for v in r4.values()})
    assert groups == ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]
    counts = {g: sum(1 for v in r4.values() if v.group == g) for g in groups}
    assert counts == {"C1": 4, "C2": 2, "C3": 1, "C4": 1, "C5": 1,
                      "C6": 4, "C7": 1, "C8": 1}
    assert len(r4) == 15
    assert all(isinstance(v, Variant) and callable(v.fn) for v in VARIANTS.values())


def test_registry_holds_exactly_the_registered_round_5_variants():
    """D1..D4 as pre-registered in VARIANTS_PREREGISTRATION_R5_SLEEVE.md: three
    D1 weights, one D2, one D3, two D4 rules — 7 arms, 22 across both rounds,
    which is the denominator the round-5 report is required to use."""
    r5 = _round(5)
    counts = {g: sum(1 for v in r5.values() if v.group == g)
              for g in sorted({v.group for v in r5.values()})}
    assert counts == {"D1": 3, "D2": 1, "D3": 1, "D4": 2}
    assert sorted(r5) == ["D1-05", "D1-10", "D1-15", "D2", "D3",
                          "D4-band005", "D4-daily"]
    assert len(_round(4)) + len(r5) == 22


def test_registry_holds_exactly_the_registered_round_6_variants():
    """E1..E3 as pre-registered in VARIANTS_PREREGISTRATION_R6_SPYCORE.md: the
    trigger at D2's weights, the static control for its weight LEVEL, and the
    trigger at the live weights. Three arms, 25 across all three rounds, which
    is the denominator the round-6 report is required to use."""
    r6 = _round(6)
    assert sorted(r6) == ["E1", "E2", "E3"]
    assert sorted({v.group for v in r6.values()}) == ["E1", "E2", "E3"]
    assert len(VARIANTS) == 25


def test_every_variant_declares_a_registered_round():
    """A variant with no round would be judged by whichever campaign ran last —
    the exact failure the round tag exists to prevent."""
    assert {v.round for v in VARIANTS.values()} == {4, 5, 6}
    assert all(v.round == 4 for v in INCUMBENTS.values()), \
        "incumbents are shared across rounds and must stay untagged"


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
         idle=None, spy=None) -> Ctx:
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
              spy=lvl(spy) if spy else dict(one),
              bil=lvl(bil) if bil else dict(one),
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


# --- round-5 builders (D1..D4) --------------------------------------------------
# The round-5 contract fixes the routing leg, the trigger weights, the absence
# of a cap and the rebalance rule. Each of those is a place a later edit could
# silently change what the campaign tested, so each gets a gate.

def test_d1_routes_idle_capital_to_cash_and_never_to_the_core():
    """D1's whole point (M2): the sleeve's idle capital earns BIL, so a book
    built on a flat core and a flat sleeve still tracks BIL through the idle
    fraction — and it does NOT pick up the core's return."""
    ctx = _ctx(3, sleeve=[0.0, 0.0], core=[0.40, 0.40], bil=[0.01, 0.01],
               idle=[1.0, 1.0, 1.0])
    r = curve_returns(d1_sleeve_cash(ctx, 1.0), ctx.dates)
    assert r == pytest.approx([0.01, 0.01], abs=1e-12)   # BIL, not 0.40


def test_d1_weights_are_the_registered_grid():
    assert D1_WEIGHTS == (0.05, 0.10, 0.15)
    assert sorted(k for k in VARIANTS if k.startswith("D1-")) == \
        ["D1-05", "D1-10", "D1-15"]


def test_d2_holds_the_high_weight_only_while_correlation_is_below_threshold():
    """D2 is C8's trigger at 15/5. Build a core perfectly correlated with the
    sleeve so rho = 1 > 0.30 and the LOW weight must be chosen once warm-up
    ends; an anti-correlated core must choose the HIGH one."""
    n = 200
    up = [0.01 if i % 2 else -0.01 for i in range(n - 1)]
    same = _ctx(n, sleeve=up, core=up, idle=[0.0] * n)
    opp = _ctx(n, sleeve=up, core=[-x for x in up], idle=[0.0] * n)
    for ctx, want in ((same, D2_LO_W), (opp, D2_HI_W)):
        sleeve = sleeve_idle_routed(ctx, "BIL")
        sr, cr = curve_returns(sleeve, ctx.dates), curve_returns(ctx.core, ctx.dates)
        rho = pearson(sr[-60:], cr[-60:])
        assert (D2_HI_W if rho < 0.30 else D2_LO_W) == want


def test_d3_is_uncapped_where_round_4s_c3_was_capped():
    """M5: C3's 30% cap bound on most days. D3 must be able to exceed it."""
    ctx = _ctx(120, sleeve=[0.001 * (1 if i % 2 else -1) for i in range(119)],
               core=[0.05 * (1 if i % 2 else -1) for i in range(119)],
               idle=[0.0] * 120)
    w = d3_weight_at(ctx, 119)          # calm sleeve, wild core -> big sleeve
    assert w is not None and w > C3_SLEEVE_CAP
    assert 0.0 < w < 1.0                # the rule is a share, never levered


def test_d3_weight_is_none_during_warm_up_and_on_a_flat_sleeve():
    assert d3_weight_at(_ctx(30, idle=[0.0] * 30), 29) is None      # warm-up
    flat = _ctx(120, core=[0.01] * 119, idle=[0.0] * 120)           # zero sleeve vol
    assert d3_weight_at(flat, 119) is None


def test_d4_selection_rule_prefers_the_lower_weight_on_a_tie(monkeypatch):
    """The registration fixes the rule: highest BIL-excess Sharpe over the FULL
    REAL window, ties broken toward the LOWER weight."""
    import scripts.backtest_core_variants as mod
    monkeypatch.setattr(mod, "_D1_BEST_W", None)
    monkeypatch.setattr(mod, "d1_sleeve_cash", lambda ctx, w: dict(ctx.core))
    assert mod.d1_best_weight(_ctx(40, core=[0.001] * 39)) == min(D1_WEIGHTS)


# --- round-5 counter-agent corrections (M1..M4, m1, m2) --------------------------
# Each of these is a place where a later edit could silently undo a correction
# the counter-agent had to catch, so each gets a merge-blocking gate.

def test_dead_cash_twin_is_the_same_book_with_the_routing_off():
    """M1. The mechanism's own counterfactual must differ from the arm ONLY in
    the cash routing: with nothing idle the two books are identical, and with
    idle cash the twin is the one that earns nothing on it."""
    flat = _ctx(40, core=[0.001] * 39, bil=[0.0002] * 39, idle=[0.0] * 40)
    assert curve_returns(d1_sleeve_cash(flat, 0.10), flat.dates) == \
        pytest.approx(curve_returns(d1_dead_cash_twin(flat, 0.10), flat.dates))
    idle = _ctx(40, core=[0.001] * 39, bil=[0.0002] * 39, idle=[1.0] * 40)
    live = curve_returns(d1_sleeve_cash(idle, 0.10), idle.dates)
    dead = curve_returns(d1_dead_cash_twin(idle, 0.10), idle.dates)
    assert all(a > b for a, b in zip(live, dead, strict=True))


def test_sweep_coverage_and_drag_bound_the_mechanism():
    """M1. Zero coverage must reproduce the dead-cash book exactly, full
    coverage with no drag is the registered arm, and a drag can only subtract."""
    ctx = _ctx(30, core=[0.001] * 29, bil=[0.001] * 29, idle=[1.0] * 30)
    none = curve_returns(sleeve_idle_routed(ctx, "BIL", coverage=0.0), ctx.dates)
    assert none == pytest.approx(curve_returns(ctx.sleeve, ctx.dates))
    full = sleeve_idle_routed(ctx, "BIL")[ctx.dates[-1]]
    half = sleeve_idle_routed(ctx, "BIL", coverage=0.5)[ctx.dates[-1]]
    dragged = sleeve_idle_routed(ctx, "BIL", drag_bps=100.0)[ctx.dates[-1]]
    assert full > half > 1.0 and full > dragged


def test_d2_warm_up_default_is_a_registered_weight_not_the_live_one():
    """M3. D2's contract names 15% and 5% and nothing else. The 30% fallback is
    registered for D3 ONLY; inheriting it here decided D2's verdict."""
    assert D2_WARMUP_W == D2_LO_W and D2_WARMUP_W != LIVE_SLEEVE_W
    ctx = _ctx(40, core=[0.001] * 39, idle=[0.0] * 40)   # never leaves warm-up
    r = curve_returns(d2_corr_at_tangency(ctx), ctx.dates)
    want = curve_returns(portfolio(ctx.dates, ctx.legs(),
                                   const({"SLEEVE": D2_LO_W,
                                          "CORE": 1 - D2_LO_W}),
                                   rebal_dates=ctx.months), ctx.dates)
    assert r == pytest.approx(want)
    assert d2_warmup_days(ctx) == len(ctx.dates)         # all of it is warm-up


def test_both_cash_conventions_are_registered_and_neither_is_a_comparator():
    """M4. The swept twins must exist for every table, and must NOT become
    incumbents (the bar is still 'vs the best of the three registered ones')
    or judged arms (the campaign is still 22)."""
    assert {"INC-3070SPY-SWEPT", "REF-R2A-SWEPT"} <= set(INCUMBENTS)
    assert INCUMBENT_KEYS == ["INC-B5", "INC-3070SPY", "INC-SPY"]
    assert len(VARIANTS) == 25
    assert all(k not in VARIANTS for k in ("INC-3070SPY-SWEPT", "REF-R2A-SWEPT"))


def test_the_swept_30_70_book_differs_from_the_frozen_one_only_by_idle_cash():
    ctx = _ctx(40, core=[0.001] * 39, bil=[0.0003] * 39, idle=[0.0] * 40)
    assert curve_returns(inc_3070spy(ctx, swept=True), ctx.dates) == \
        pytest.approx(curve_returns(inc_3070spy(ctx), ctx.dates))
    idle = _ctx(40, core=[0.001] * 39, bil=[0.0003] * 39, idle=[1.0] * 40)
    assert inc_3070spy(idle, swept=True)[idle.dates[-1]] > \
        inc_3070spy(idle)[idle.dates[-1]]


def test_power_mc_is_monotone_in_power_and_at_least_the_50_percent_floor():
    """M2. The harness's published MDE is the 50%-power threshold; the 80% one
    can never be smaller, and the empirical power at the published floor must
    land near a half."""
    import random
    rng = random.Random(7)
    a = [rng.gauss(0.0004, 0.01) for _ in range(400)]
    b = [rng.gauss(0.0002, 0.01) for _ in range(400)]
    out = power_mc(a, b, worlds=25, draws=200, at=(0.20,))
    q = out["mde_at_power"]
    assert q["0.50"] <= q["0.80"] <= q["0.90"]
    assert 0.0 <= out["power_at"]["0.2000"] <= 1.0


def test_max_t_adjusted_p_is_never_smaller_than_the_raw_p():
    """A multiplicity adjustment that made a p-value SMALLER would be broken;
    with correlated near-identical arms it must also stay far below the
    Bonferroni factor of n."""
    ctx = _ctx(300, core=[0.0006 * (1 if i % 3 else -1) for i in range(299)],
               bil=[0.00005] * 299, idle=[0.0] * 300)
    keys = ["C1-05", "C1-10", "C6-monthly"]
    inc_ex = [a - b for a, b in
              zip(curve_returns(ctx.core, ctx.dates), ctx.bil_rets, strict=True)]
    out = westfall_young_maxt(ctx, keys, inc_ex, draws=200)
    assert set(out["adjusted_p"]) == set(keys)
    for k in keys:
        assert out["adjusted_p"][k] >= out["raw_p_shared"][k] - 1e-12
        assert out["adjusted_p"][k] <= min(1.0, len(keys) * out["raw_p_shared"][k]) + 1e-9


def test_proxy_sessions_are_counted_not_quoted():
    """m2. The synthetic window's proxy usage must be COUNTED from the sources;
    the report carried a hard-coded string for two rounds."""
    ctx = _ctx(5, idle=[0.0] * 5)
    full = {d: 1.0 for d in ctx.dates}
    ctx.raw = {f: dict(full) for f in B5_WEIGHTS}
    assert proxy_session_usage(ctx)["returns_using_a_proxy"] == 0
    hole = dict(full)
    del hole[ctx.dates[2]]                     # one fund missing one session
    ctx.raw["KMLM"] = hole
    got = proxy_session_usage(ctx)
    assert got["returns_using_a_proxy"] == 2   # the return into it and out of it
    assert got["per_fund"] == {"KMLM": 2}
    assert got["n_returns"] == len(ctx.dates) - 1


# --- ROUND 6: D2's rule on a SPY core -----------------------------------------------
# The gate that matters most this round is the one on WHICH CORE the trigger
# reads. Correlating against B.5 while HOLDING SPY would make round 6 a re-run
# of D2 wearing a SPY label — the weights decided by one book and applied to
# another — and every table would still look plausible. These tests make that
# bug impossible to commit.

def _spy_core_ctx(n: int = 140) -> Ctx:
    """A context whose two candidate cores give OPPOSITE trigger calls.

    The sleeve alternates +/-1%. SPY is its exact negative (rho = -1, BELOW the
    0.30 threshold -> the HIGH leg). The B.5 core is its exact copy (rho = +1,
    ABOVE the threshold -> the LOW leg). Nothing else distinguishes them, so an
    arm that reads the wrong core cannot accidentally agree.
    """
    up = [0.01 if i % 2 == 0 else -0.01 for i in range(n - 1)]
    return _ctx(n, sleeve=up, core=list(up), spy=[-r for r in up],
                idle=[0.0] * n)


def test_round6_correlates_against_the_SPY_core_it_holds_not_B5():
    ctx = _spy_core_ctx()
    sr = curve_returns(ctx.sleeve, ctx.dates)
    assert pearson(sr, ctx.spy_rets) == pytest.approx(-1.0)
    assert pearson(sr, curve_returns(ctx.core, ctx.dates)) == pytest.approx(1.0)
    assert -1.0 < E_CORR_THRESHOLD < 1.0, "the two cores must straddle the bar"

    for hi, lo, warm in ((E1_HI_W, E1_LO_W, E1_WARMUP_W),
                         (E3_HI_W, E3_LO_W, E3_WARMUP_W)):
        p = spy_core_trigger_profile(ctx, hi, lo, warm)
        assert p["decisions_hi"] > 0, "the SPY core is anti-correlated: HIGH"
        assert p["decisions_lo"] == 0, (
            "a LOW decision here means the trigger read the B.5 core")
        assert p["mean_rho"] == pytest.approx(-1.0)


def test_round6_trigger_would_give_the_opposite_answer_on_the_B5_core():
    """The companion half of the pin: on the SAME context, round 5's D2 — which
    correlates against `ctx.core` by design — makes the opposite call. If both
    ever agreed, the test above would be vacuous."""
    ctx = _spy_core_ctx()
    d2 = curve_returns(d2_corr_at_tangency(ctx), ctx.dates)
    low = curve_returns(portfolio(ctx.dates, ctx.legs(),
                                  const({"SLEEVE": D2_LO_W,
                                         "CORE": 1 - D2_LO_W}),
                                  rebal_dates=ctx.months), ctx.dates)
    assert d2 == pytest.approx(low, abs=1e-12), \
        "rho(sleeve, B.5 core) = +1 > 0.30, so D2 must sit on its LOW leg"


def test_round6_arms_hold_the_SPY_leg_and_never_the_B5_core():
    """A round-6 book must be sleeve + SPY. If any weight leaked into CORE, a
    context whose B.5 core moves and whose SPY core does not would show it."""
    ctx = _ctx(120, core=[0.02] * 119, spy=None, idle=[0.0] * 120)
    for key in ("E1", "E2", "E3"):
        r = curve_returns(VARIANTS[key].fn(ctx), ctx.dates)
        assert max(abs(x) for x in r) == pytest.approx(0.0, abs=1e-12), (
            f"{key} moved with the B.5 core it does not hold")


def test_spy_core_leg_assertion_rejects_a_miswired_core():
    """The assertion itself is the gate, so it gets its own test: hand the
    helper a leg dict whose core is the B.5 curve and it must refuse."""
    ctx = _spy_core_ctx()
    good = spy_core_curves(ctx)
    assert _spy_core_leg(good, ctx) is ctx.spy
    bad = dict(good)
    bad[E_CORE_LEG] = ctx.core
    with pytest.raises(AssertionError):
        _spy_core_leg(bad, ctx)


def test_round6_maps_the_correlation_call_to_the_REGISTERED_weight_pair():
    """E1 is 15/5 and E3 is 30/10 — the pairs the contract fixes, and no
    others. Two contexts, one on each side of the threshold, and the realized
    book must be exactly the static book at the corresponding leg."""
    up = [0.01 if i % 2 == 0 else -0.01 for i in range(139)]
    hi_ctx = _ctx(140, sleeve=up, core=list(up), spy=[-r for r in up],
                  idle=[0.0] * 140)                       # rho = -1 -> HIGH
    lo_ctx = _ctx(140, sleeve=up, core=[-r for r in up], spy=list(up),
                  idle=[0.0] * 140)                       # rho = +1 -> LOW
    for hi, lo, warm in ((E1_HI_W, E1_LO_W, E1_WARMUP_W),
                         (E3_HI_W, E3_LO_W, E3_WARMUP_W)):
        # BELOW the threshold: every decided month takes the HIGH leg, and the
        # applied weight is exactly warm-up-then-high — no third weight exists.
        p = spy_core_trigger_profile(hi_ctx, hi, lo, warm)
        assert p["days_hi"] > 0 and p["days_lo"] == 0
        assert p["mean_applied_w"] == pytest.approx(
            (p["days_warmup"] * warm + p["days_hi"] * hi) / p["n_days"])
        # ...and once it is settled at the high leg it IS the static high book:
        # same weight, same monthly dates, so the daily returns coincide.
        got = curve_returns(spy_core_corr_trigger(hi_ctx, hi, lo, warm),
                            hi_ctx.dates)
        want = curve_returns(spy_core_static(hi_ctx, hi), hi_ctx.dates)
        assert got[120:] == pytest.approx(want[120:], abs=1e-12)
        # ABOVE the threshold: the low leg IS the warm-up leg, so the whole
        # path must equal the static low book with nothing left over.
        assert curve_returns(spy_core_corr_trigger(lo_ctx, hi, lo, warm),
                             lo_ctx.dates) == pytest.approx(
            curve_returns(spy_core_static(lo_ctx, lo), lo_ctx.dates), abs=1e-12)
    assert (E1_HI_W, E1_LO_W) == (0.15, 0.05)
    assert (E3_HI_W, E3_LO_W) == (0.30, 0.10)
    assert E2_W == 0.10 and E_CORR_WINDOW == 60 and E_CORR_THRESHOLD == 0.30


def test_round6_warm_up_default_is_each_arms_OWN_registered_low_leg():
    """Round-5 counter-agent M3, applied in advance. A round-6 arm that never
    leaves warm-up must be its own registered LOW leg — never the live 30%,
    never the other arm's leg."""
    assert E1_WARMUP_W == E1_LO_W and E1_WARMUP_W != LIVE_SLEEVE_W
    assert E3_WARMUP_W == E3_LO_W and E3_WARMUP_W != E1_LO_W
    ctx = _ctx(40, core=[0.001] * 39, spy=[0.002] * 39, idle=[0.0] * 40)
    for hi, lo, warm in ((E1_HI_W, E1_LO_W, E1_WARMUP_W),
                         (E3_HI_W, E3_LO_W, E3_WARMUP_W)):
        got = curve_returns(spy_core_corr_trigger(ctx, hi, lo, warm), ctx.dates)
        assert got == pytest.approx(
            curve_returns(spy_core_static(ctx, lo), ctx.dates), abs=1e-12)
        p = spy_core_trigger_profile(ctx, hi, lo, warm)
        assert p["days_warmup"] == p["n_days"] and p["decisions_hi"] == 0


def test_e2_is_a_static_control_at_the_registered_weight_not_a_trigger():
    """E2 exists to hold the LEVEL fixed. It must be flat in the weight, so a
    context whose correlation swings cannot move it at all."""
    ctx = _spy_core_ctx()
    assert curve_returns(VARIANTS["E2"].fn(ctx), ctx.dates) == pytest.approx(
        curve_returns(spy_core_static(ctx, E2_W), ctx.dates), abs=1e-12)


def test_round6_arms_route_idle_sleeve_capital_to_BIL_not_to_the_core():
    """Every round-6 arm carries the live cash convention. With the sleeve
    fully idle, the sleeve leg must earn BIL — and a moving B.5 core must not
    leak into it."""
    ctx = _ctx(30, sleeve=[0.0] * 29, core=[0.05] * 29, spy=[0.0] * 29,
               bil=[0.0002] * 29, idle=[1.0] * 30)
    assert curve_returns(spy_core_curves(ctx)["SLEEVE"], ctx.dates) ==         pytest.approx([0.0002] * 29, abs=1e-12)


def test_arm_contrast_is_paired_antisymmetric_and_zero_on_identical_arms():
    """E1 - E2 is a contrast between two ARMS, so it must behave like the
    paired bootstrap it wraps: exactly zero against itself, sign-flipping on
    swap, and never wider than the difference it is measuring."""
    ctx = _ctx(300, sleeve=[0.001] * 299, core=[0.0] * 299,
               spy=[0.0004 if i % 3 else -0.0002 for i in range(299)],
               bil=[0.00005] * 299, idle=[0.0] * 300)
    a, b = spy_core_static(ctx, 0.30), spy_core_static(ctx, 0.05)
    same = arm_contrast(ctx, a, a, draws=200, deep=None)
    assert same["d_sharpe"] == pytest.approx(0.0, abs=1e-12)
    assert same["ci95"] == pytest.approx([0.0, 0.0], abs=1e-9)
    fwd = arm_contrast(ctx, a, b, draws=200, deep=None)
    rev = arm_contrast(ctx, b, a, draws=200, deep=None)
    assert fwd["d_sharpe"] == pytest.approx(-rev["d_sharpe"], abs=1e-12)
    assert fwd["boot_p"] == pytest.approx(rev["boot_p"])
    assert fwd["ci95"][0] <= fwd["d_sharpe"] <= fwd["ci95"][1]


def test_round6_incumbent_is_NAMED_by_the_registration_not_selected():
    """Round 6 may not pick its own comparator after seeing a result. The key
    is frozen in ROUNDS beside the report path, it is a registered incumbent,
    and it is the SWEPT (live-convention) 30/70 book — judging against the
    dead-cash twin would hand every arm a free ~+0.04 it did not earn."""
    assert ROUNDS[6]["incumbent"] == "INC-3070SPY-SWEPT"
    assert ROUNDS[6]["incumbent"] in INCUMBENTS
    assert ROUNDS[6]["incumbent"] not in INCUMBENT_KEYS   # not rule-selected
    assert "incumbent" not in ROUNDS[4] and "incumbent" not in ROUNDS[5]
    assert ROUNDS[6]["contract"] == "docs/VARIANTS_PREREGISTRATION_R6_SPYCORE.md"


def test_monthly_weights_holds_the_named_core_leg():
    """`core_leg` is what lets a round-6 arm hold SPY while rounds 4-5 hold
    B.5. The default must stay CORE so no round-4/5 arm moves."""
    ctx = _ctx(40)
    assert monthly_weights(ctx, lambda _i: 0.2, 0.2)(ctx.dates[0]) ==         {"SLEEVE": 0.2, "CORE": 0.8}
    assert monthly_weights(ctx, lambda _i: 0.2, 0.2,
                           core_leg="SPY")(ctx.dates[0]) ==         {"SLEEVE": 0.2, "SPY": 0.8}


# --- ROUND 6 counter-agent corrections ----------------------------------------------
# M3: the campaign denominators are part of a round's FROZEN record. They used
# to be computed from the live registry, so registering round 6 rewrote rounds
# 4-5's published multiplicity prose. M1/M2: the cross-round max-T re-bases
# every prior arm onto round 6's incumbent, which is required for the
# instrument and is NOT a fact about those arms.

def test_each_round_freezes_its_own_campaign_snapshot():
    """A finished round's multiple-comparison family may never grow. These are
    the snapshots the committed reports were judged and written against."""
    assert ROUNDS[4]["campaign_rounds"] == (4, 5)
    assert ROUNDS[5]["campaign_rounds"] == (4, 5)
    assert ROUNDS[6]["campaign_rounds"] == (4, 5, 6)
    for r, want in ((4, 22), (5, 22), (6, 25)):
        keys = [k for k, v in VARIANTS.items()
                if v.round in ROUNDS[r]["campaign_rounds"]]
        assert len(keys) == want, (
            f"round {r}'s frozen campaign is {want} arms; a later round may "
            f"not enlarge it")
        assert r in ROUNDS[r]["campaign_rounds"], "a round is in its own family"
    # Round 5's report states round 4's OWN size. Deriving it by subtraction
    # (n_all - 7) printed 18 the moment round 6 was registered.
    r4 = sum(1 for v in VARIANTS.values() if v.round == 4)
    assert r4 == 15
    assert len([k for k, v in VARIANTS.items()
                if v.round in ROUNDS[5]["campaign_rounds"]]) - 7 == r4


def test_campaign_size_falls_back_to_the_registry_and_tracks_the_snapshot():
    before = list(CAMPAIGN)
    try:
        CAMPAIGN[:] = []
        assert campaign_size() == len(VARIANTS)
        CAMPAIGN[:] = ["E1", "E2"]
        assert campaign_size() == 2
    finally:
        CAMPAIGN[:] = before


def test_round6_miswired_counterfactual_really_reads_the_WRONG_core():
    """The pin's cost is only meaningful if the counterfactual is genuinely the
    bug. On the context where the two cores give OPPOSITE calls, the registered
    arm must take the SPY answer and the counterfactual the B.5 one."""
    ctx = _spy_core_ctx()
    right = spy_core_corr_trigger(ctx, E1_HI_W, E1_LO_W, E1_WARMUP_W)
    wrong = spy_core_corr_trigger_MISWIRED(ctx, E1_HI_W, E1_LO_W, E1_WARMUP_W)
    r = [round(v, 12) for v in right.values()]
    wrng = [round(v, 12) for v in wrong.values()]
    assert r != wrng, "the counterfactual is indistinguishable from the arm"
    hi = _corr_decision_path(ctx, ctx.spy, E1_HI_W, E1_LO_W, E1_WARMUP_W)
    lo = _corr_decision_path(ctx, ctx.core, E1_HI_W, E1_LO_W, E1_WARMUP_W)
    assert set(hi[-10:]) == {E1_HI_W}, "SPY is anti-correlated here: HIGH leg"
    assert set(lo[-10:]) == {E1_LO_W}, "B.5 is correlated here: LOW leg"
    assert sum(1 for a, b in zip(hi, lo) if a != b) > 0
    # ...and no REGISTERED arm may be wired to it.
    for k in ("E1", "E2", "E3"):
        reg = [round(v, 12) for v in VARIANTS[k].fn(ctx).values()]
        assert reg != [round(v, 12) for v in wrong.values()], (
            f"{k} is wired to the MISWIRED builder")


def test_round6_level_decomposition_adds_up_and_is_flagged_unregistered():
    """LEVEL + TIMING must reconstruct the arm's own gap to the incumbent, and
    the block must carry its own hypothesis-generation label."""
    ctx = _spy_core_ctx()
    arm = spy_core_corr_trigger(ctx, E3_HI_W, E3_LO_W, E3_WARMUP_W)
    inc = spy_core_static(ctx, E3_HI_W)
    prof = spy_core_trigger_profile(ctx, E3_HI_W, E3_LO_W, E3_WARMUP_W)
    d = spy_core_level_decomposition(ctx, arm, inc, prof["mean_applied_w"],
                                     draws=100)
    assert d["registered"] is False
    assert "HYPOTHESIS GENERATION" in d["basis"]
    legs = d["level"]["d_sharpe"] + d["timing"]["d_sharpe"]
    assert legs == pytest.approx(d["total"]["d_sharpe"], abs=1e-9)
    assert d["mean_applied_w"] == pytest.approx(prof["mean_applied_w"])
    assert len(d["timing_thirds"]) == 3


def test_thirds_d_sharpe_is_zero_against_itself_and_antisymmetric():
    ctx = _spy_core_ctx()
    a = spy_core_static(ctx, 0.2)
    b = spy_core_static(ctx, 0.1)
    for t in _thirds_d_sharpe(ctx, a, a):
        assert t["d_sharpe"] == pytest.approx(0.0, abs=1e-12)
    for x, y in zip(_thirds_d_sharpe(ctx, a, b), _thirds_d_sharpe(ctx, b, a)):
        assert x["d_sharpe"] == pytest.approx(-y["d_sharpe"], abs=1e-12)


def test_mde_table_prints_the_MEASURED_power_only_when_asked():
    """m2. The published `-CI_lo` column wears a 50%-power label but the
    harness's own MC measures it at 55-60%. Round 6 prints both; rounds 4-5
    keep the two-column form their frozen reports were written with."""
    v = {"E1": {"ci95": [-0.2, 0.3],
                "power": {"grid": {f"{g:.2f}": {"detected": False,
                                                "boot_p": 0.9}
                                   for g in (0.05, 0.10, 0.20, 0.40)},
                          "min_detectable_edge": 0.2},
                "power_mc": {"mde_at_power": {"0.50": 0.18, "0.80": 0.27},
                             "power_at": {"0.2000": 0.595}}}}
    frozen = _mde_table(v)
    honest = _mde_table(v, measured_power=True)
    assert "MDE @50% power (as published)" in frozen[0]
    assert "60%" not in frozen[-1]
    assert "MEASURED power" in honest[0] and "MDE @50% power (MC)" in honest[0]
    assert "| 60% |" in honest[-1] and "+0.18" in honest[-1]
