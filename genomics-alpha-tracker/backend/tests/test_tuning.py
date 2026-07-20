"""Tests for the tuning loop: gate math, promotion rules, evidence bundle."""
from __future__ import annotations

from datetime import date, timedelta

from evals.replay import recompute_composite, spearman, wilson_bounds
from app.models import FlagOutcome, PriceBar, ScoreSnapshot, Security, TradeCall


# --- gate math -------------------------------------------------------------------

def test_spearman_perfect_and_inverse():
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-9


def test_spearman_handles_ties_and_degenerate():
    r = spearman([1, 1, 2, 3], [5, 5, 6, 7])
    assert r is not None and r > 0.9
    assert spearman([1, 1, 1], [1, 2, 3]) is None  # zero variance in ranks
    assert spearman([1, 2], [1, 2]) is None        # too short


def test_wilson_bounds_shrink_with_n():
    lo_small, _ = wilson_bounds(6, 10)     # 60% on n=10
    lo_big, _ = wilson_bounds(60, 100)     # 60% on n=100
    assert lo_small < 0.5 < lo_big         # small n cannot clear the bar
    lo, hi = wilson_bounds(0, 0)
    assert (lo, hi) == (0.0, 1.0)


def test_promotion_bar_needs_real_evidence():
    # The TUNING.md promotion rule: Wilson 90% lower bound > 0.50.
    # 12/20 (60%) is NOT enough; 15/20 (75%) is.
    lo_60, _ = wilson_bounds(12, 20)
    lo_75, _ = wilson_bounds(15, 20)
    assert lo_60 < 0.50 < lo_75


def test_recompute_composite_matches_engine_semantics():
    comps = {"a": 80.0, "b": 40.0, "c": None}
    w = {"a": 0.3, "b": 0.1, "c": 0.6}  # c missing -> excluded from denominator
    got = recompute_composite(comps, w)
    assert abs(got - (80 * 0.3 + 40 * 0.1) / 0.4) < 1e-9
    assert recompute_composite({"a": None}, {"a": 1.0}) is None
    assert recompute_composite({}, {}) is None


def test_reweighting_changes_ranking():
    # Two names, two components: flipping the dominant weight flips the ranking —
    # exactly what the ic gate replays at scale.
    x = {"rev": 90.0, "cat": 10.0}
    y = {"rev": 10.0, "cat": 90.0}
    w_rev = {"rev": 0.9, "cat": 0.1}
    w_cat = {"rev": 0.1, "cat": 0.9}
    assert recompute_composite(x, w_rev) > recompute_composite(y, w_rev)
    assert recompute_composite(x, w_cat) < recompute_composite(y, w_cat)


# --- evidence bundle ---------------------------------------------------------------

def _seed_calls(session, rs_by_band):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    d = date(2026, 5, 1)
    i = 0
    for comp, rs in rs_by_band:
        for r in rs:
            i += 1
            session.add(TradeCall(
                symbol="CRSP", call_date=d + timedelta(days=i),
                direction="long", source="auto_flag", entry_price=100.0,
                stop_price=94.0, target_price=118.0,
                expires_on=d + timedelta(days=i + 45), composite_at_call=comp,
                status="expired", exit_date=d + timedelta(days=i + 10),
                exit_price=100.0 + r * 6.0, return_pct=r * 0.06, r_multiple=r,
            ))
    session.commit()


def test_conviction_bands(session):
    from app.routers.tuning import _conviction_bands

    _seed_calls(session, [(60.0, [1.0, -1.0]), (80.0, [2.0, 3.0, 2.0])])
    bands = {b["band"]: b for b in _conviction_bands(session)}
    assert bands["55-64"]["n"] == 2 and abs(bands["55-64"]["avg_r"]) < 1e-9
    assert bands["75-100"]["n"] == 3 and bands["75-100"]["avg_r"] > 2.0


def test_evidence_endpoint_shape(session):
    from app.routers.tuning import tuning_evidence

    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    session.add(FlagOutcome(flag_id=1, symbol="CRSP", flag_type="volume_anomaly",
                            fired_on=date(2026, 5, 1), price_at_fire=100.0, fwd_1m=0.05))
    session.commit()
    ev = tuning_evidence(session=session)
    assert ev["counts"]["flag_outcomes_graded_1m"] == 1
    assert "flag_track_record" in ev and "configs" in ev
    assert ev["configs"]["scoring_weights"]  # echoes the tunable surface


def test_lane_verdicts_insufficient_by_default(session):
    from app.routers.tuning import tuning_evidence
    from scripts.tune_proposal import lane_verdicts

    ev = tuning_evidence(session=session)
    v = lane_verdicts(ev)
    assert not v["trigger_promotion_demotion"]["sufficient"]
    assert not v["exit_params"]["sufficient"]
    assert not v["conviction_gate"]["sufficient"]


def test_lane_verdicts_trigger_ready_at_min_n(session):
    from app.routers.tuning import tuning_evidence
    from scripts.tune_proposal import lane_verdicts

    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    for i in range(20):
        session.add(FlagOutcome(flag_id=i + 1, symbol="CRSP",
                                flag_type="pre_catalyst_sentiment_ramp",
                                fired_on=date(2026, 1, 1) + timedelta(days=i * 3),
                                price_at_fire=100.0, fwd_1m=0.02, excess_1m=0.01))
    session.commit()
    v = lane_verdicts(tuning_evidence(session=session))
    assert v["trigger_promotion_demotion"]["sufficient"]
    assert "pre_catalyst_sentiment_ramp" in v["trigger_promotion_demotion"]["detail"]
