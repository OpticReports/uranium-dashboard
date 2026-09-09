"""Merge-blocking gate tests for the M&A cycle-phase indicator.

Gate philosophy: this module may only ship a reading if (1) no
statistic it computes can see data dated after the reading it
produces, (2) the phase label is stable under the arbitrary constants
we declared, (3) the regime seam is actually honoured, and (4) the
refusals hold - it must decline to read when coverage is thin and must
never present itself as a forecast.

Gate (1) is the reason this file exists. Every other property is
recoverable by inspection; look-ahead leakage is not, and it is the
failure mode that makes a cycle indicator look excellent in backtest
and useless live.
"""

import ma_cycle as mc


# --- GATE 1: the look-ahead invariant ------------------------------

def test_percentile_rank_cannot_see_the_future():
    """THE load-bearing gate.

    Append arbitrary future data and every PAST reading must be
    byte-identical. Orphanides & van Norden (2002) showed the damage in
    real-time cycle estimates comes from the trend being redrawn as the
    sample grows - clean, never-revised inputs do not save you. This
    test is what makes that structurally impossible here rather than
    merely intended.
    """
    base = [3, 1, 4, 1, 5, 9, 2, 6]
    futures = [
        base + [100, 200, 300],       # extreme upside
        base + [-50, -60],            # extreme downside
        base + [3, 1, 4],             # repeats
    ]
    for i in range(len(base)):
        want = mc.percentile_rank_expanding(base, i)
        for f in futures:
            got = mc.percentile_rank_expanding(f, i)
            assert got == want, (
                f"look-ahead leak at i={i}: {want} -> {got} after "
                f"appending {f[len(base):]}")


def test_hamilton_difference_cannot_see_the_future():
    base = [10, 11, 12, 13, 14, 15, 16, 17]
    ext = base + [999, -999]
    for i in range(len(base)):
        assert mc.hamilton_difference(base, i, h=3) == \
               mc.hamilton_difference(ext, i, h=3)


def test_hamilton_difference_refuses_before_enough_history():
    """No backfill, no padding, no seeding. Until h periods exist there
    is no momentum reading, and we say None rather than invent one."""
    s = list(range(30))
    for i in range(mc.MOMENTUM_H_QUARTERS):
        assert mc.hamilton_difference(s, i) is None
    assert mc.hamilton_difference(s, mc.MOMENTUM_H_QUARTERS) is not None


def test_diffusion_cannot_see_the_future():
    comps = [[1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1], [1, 1, 2, 2, 3, 3]]
    ext = [c + [1000] for c in comps]
    for i in range(6):
        assert mc.diffusion(comps, i) == mc.diffusion(ext, i)


# --- GATE 2: stability under the declared arbitrary constant --------

def test_neutral_band_sensitivity_is_published():
    """NEUTRAL_BAND = 0.15 is arbitrary and declared as such. This gate
    does not assert the label is INVARIANT to it - that would be false,
    a wider band by construction converts more readings to
    'transitional'. It asserts the direction is monotone, so the
    constant cannot silently flip a call from (say) late to early.
    """
    for level, mom in [(0.5, 0.4), (-0.3, 0.25), (0.12, 0.9), (0.9, 0.12)]:
        labels = [mc.classify_phase(level, mom, nb) for nb in (0.10, 0.15, 0.20)]
        non_transitional = [l for l in labels if l != "transitional"]
        assert len(set(non_transitional)) <= 1, (
            f"neutral band flips the LABEL, not just to transitional: "
            f"{labels} at level={level} mom={mom}")


def test_transitional_is_reachable_and_used():
    assert mc.classify_phase(0.01, 0.9) == "transitional"
    assert mc.classify_phase(0.9, 0.01) == "transitional"
    assert mc.classify_phase(0.9, 0.9) == "mid"


def test_all_four_phases_reachable():
    got = {
        mc.classify_phase(-0.5, 0.5),
        mc.classify_phase(0.5, 0.5),
        mc.classify_phase(0.5, -0.5),
        mc.classify_phase(-0.5, -0.5),
    }
    assert got == {"early", "mid", "late", "bust"}, got


# --- GATE 3: the regime seam is real -------------------------------

def test_regime_split_actually_isolates_regimes():
    """The HSR threshold moved $15M -> $50M on 2001-02-01. A count just
    after the break must be ranked against post-break history only. If
    this gate fails, every post-2001 month reads as a historic collapse
    and the indicator is measuring a legislative change.
    """
    # high regime, then a definitional step down to a low regime
    series = [900, 950, 1000, 880, 920] + [300, 310, 290, 305, 295]
    starts = [5]
    # last point is mid-pack WITHIN its own regime -> near zero
    within = mc.percentile_rank_within_regime(series, 9, starts)
    # against the whole history it would be pinned to the floor
    naive = mc.percentile_rank_expanding(series, 9)
    assert within > -0.5, f"regime split not applied: {within}"
    assert naive < -0.5, f"control failed, naive should be near floor: {naive}"


def test_regime_split_matches_plain_rank_when_no_break():
    series = [5, 3, 8, 1, 9, 4]
    for i in range(len(series)):
        assert mc.percentile_rank_within_regime(series, i, []) == \
               mc.percentile_rank_expanding(series, i)


# --- GATE 4: the refusals hold -------------------------------------

def test_coverage_rule_refuses_thin_readings():
    """OECD 60% rule. A reading built from 1 of 4 components is not a
    composite, it is that one component wearing a hat."""
    score, cov = mc.composite([0.5, None, None, None], [0, 0, 0, 0])
    assert score is None and cov == 0.25
    score, cov = mc.composite([0.5, 0.3, 0.4, None], [0, 0, 0, 0])
    assert score is not None and cov == 0.75


def test_reading_declares_itself_not_a_forecast():
    """Structural, not decorative. The whole defence of this indicator
    is that it makes a claim checkable TODAY rather than in 18 months.
    If this flag ever goes True, the honesty box is a lie."""
    r = mc.reading([0.5, 0.4], [0.3, 0.2], [[1, 2], [2, 3]], 1)
    assert r["is_forecast"] is False


def test_reading_publishes_what_undercuts_it():
    r = mc.reading([0.5, 0.4], [0.3, 0.2], [[1, 2], [2, 3]], 1)
    for k in ("coverage", "diffusion", "breadth", "level", "momentum",
              "neutral_band"):
        assert k in r, f"reading hides {k}"


def test_exit_exposure_refuses_beyond_horizon():
    """A seed position resolving in the 2030s is NOT exposed to a 2026
    reading, and the module must say so rather than quietly applying
    one."""
    assert mc.exit_exposure(12) == "exposed"
    assert mc.exit_exposure(mc.EXPOSURE_HORIZON_YEARS * 12) == "exposed"
    assert mc.exit_exposure(mc.EXPOSURE_HORIZON_YEARS * 12 + 1) == "unexposed"
    assert mc.exit_exposure(120) == "unexposed"
    assert mc.exit_exposure(None) == "unknown"


def test_ties_do_not_drift():
    """A flat series must read 0.0, not wander with tie-break order."""
    flat = [7] * 10
    for i in range(1, 10):
        assert mc.percentile_rank_expanding(flat, i) == 0.0


# --- GATE 5: the two clock axes must not be the same variable -------

def test_momentum_is_not_the_cycle_horizon():
    """Regression gate for a real defect.

    The clock's momentum axis was originally the Hamilton 5-year
    difference. That is a CYCLICAL-COMPONENT horizon - "how far from a
    full cycle-length ago" - which is a level-like question. Using it as
    momentum made both axes measure the same thing: measured
    corr(level, momentum) = +0.822 on real data, collapsing the clock
    onto its diagonal and leaving "early" occupied ONCE in 123
    quarters. Switching momentum to a year-on-year change dropped it to
    +0.478 and repopulated the quadrants.

    This gate pins the two horizons apart so they cannot be silently
    reunified by someone tidying up the constants.
    """
    assert mc.MOMENTUM_LOOKBACK_QUARTERS < mc.CYCLE_H_QUARTERS
    assert mc.MOMENTUM_LOOKBACK_QUARTERS <= 8, (
        "momentum horizon has drifted toward the cycle horizon; the "
        "clock axes will re-correlate")


def test_momentum_change_cannot_see_the_future():
    base = [1, 4, 2, 8, 5, 7, 3, 9, 6]
    ext = base + [500, -500]
    for i in range(len(base)):
        assert mc.momentum_change(base, i, h=4) == \
               mc.momentum_change(ext, i, h=4)


def test_momentum_change_refuses_before_enough_history():
    s = list(range(20))
    for i in range(mc.MOMENTUM_LOOKBACK_QUARTERS):
        assert mc.momentum_change(s, i) is None
    assert mc.momentum_change(s, mc.MOMENTUM_LOOKBACK_QUARTERS) is not None


def test_momentum_horizon_sensitivity_is_monotone():
    """Direction must not flip with the declared lookback. A series
    rising throughout must read positive momentum at every horizon."""
    rising = list(range(40))
    falling = list(range(40, 0, -1))
    for h in (2, 4, 8):
        assert mc.momentum_change(rising, 30, h) > 0
        assert mc.momentum_change(falling, 30, h) < 0
