from datetime import date

from app.metrics.base import MetricResult, Status
from app.metrics.curve import analyze_spread
from app.scoring import thresholds as T
from app.scoring.composite import compute_composite
from app.scoring.events import detect_band_cross, detect_curve_events, detect_metric_flip


def _m(mid, cat, value, status):
    return MetricResult(metric_id=mid, category=cat, label=mid, value=value, status=status)


def test_threshold_spread_classification():
    # 3m10y: GREEN > +0.50, YELLOW 0..+0.50, RED < 0 (lower is worse)
    assert T.classify("curve.3m10y", 0.80) is Status.GREEN
    assert T.classify("curve.3m10y", 0.25) is Status.YELLOW
    assert T.classify("curve.3m10y", -0.10) is Status.RED
    assert T.classify("curve.3m10y", None) is Status.STALE


def test_threshold_higher_is_worse():
    assert T.classify("funding.sofr_effr", 2.0) is Status.GREEN
    assert T.classify("funding.sofr_effr", 8.0) is Status.YELLOW
    assert T.classify("funding.sofr_effr", 20.0) is Status.RED
    assert T.classify("crossasset.hy_oas", 600) is Status.RED


def test_composite_reweights_over_available():
    # Only curve (A) live and RED -> score should be the RED points (90), full coverage
    # collapses onto the single available category.
    live = [_m("curve.3m10y", "A", -0.2, Status.RED),
            _m("vol.move", "B", None, Status.STALE)]
    r = compute_composite(live)
    assert r.category_scores == {"A": 90.0}
    assert r.score == 90.0            # reweighted onto the only live category
    assert r.coverage < 1.0          # but coverage flags the missing data
    assert r.n_red == 1


def test_composite_blended_and_explainable():
    metrics = [
        _m("curve.3m10y", "A", 0.6, Status.GREEN),
        _m("funding.sofr_effr", "D", 20, Status.RED),
        _m("vol.vix", "B", 35, Status.RED),
    ]
    r = compute_composite(metrics)
    assert r.category_scores == {"A": 0.0, "D": 90.0, "B": 90.0}
    # contributions sum to the score (explainability)
    assert round(sum(r.contributions.values()), 1) == r.score
    assert 0 <= r.score <= 100


def test_composite_no_data():
    r = compute_composite([_m("x", "A", None, Status.STALE)])
    assert r.score is None and r.band == "NO_DATA"


def test_resteepening_event_is_critical_and_deduped():
    from datetime import timedelta
    vals = [0.5] * 10 + [-0.3] * 15 + [0.4] * 5
    dts = [date(2020, 1, 1) + timedelta(days=i) for i in range(len(vals))]
    a = analyze_spread(dts, vals, min_inversion_days=5, steepen_persist_days=10)
    evs = detect_curve_events("3m10y", a, dts[-1], median_lag_months=8)
    crit = [e for e in evs if e.event_type == "curve_resteepening"]
    assert len(crit) == 1
    assert crit[0].severity == "CRITICAL"
    # dedup key is stable on the dis-inversion date
    assert crit[0].dedup_key == f"3m10y:{a.dis_inversion_date.isoformat()}"


def test_band_cross_event():
    e = detect_band_cross("ELEVATED", "HIGH", 55.0, date(2026, 1, 1))
    assert e is not None and e.severity == "RED"
    assert detect_band_cross("HIGH", "HIGH", 55.0, date(2026, 1, 1)) is None


def test_metric_flip_event():
    m = _m("funding.sofr_effr", "D", 20, Status.RED)
    assert detect_metric_flip(m, "GREEN", date(2026, 1, 1)) is not None
    assert detect_metric_flip(m, "RED", date(2026, 1, 1)) is None  # already red, no re-fire


# --- weight-sensitivity ensemble ---------------------------------------------

def _mixed_metrics():
    return [
        _m("curve.3m10y", "A", -0.2, Status.RED),
        _m("vol.vix", "B", 14, Status.GREEN),
        _m("premium.acm", "C", 0.5, Status.GREEN),
        _m("funding.sofr_effr", "D", 20, Status.RED),
        _m("crossasset.hy_oas", "H", 300, Status.YELLOW),
        _m("labor.sahm", "J", 0.1, Status.GREEN),
    ]


def test_ensemble_band_brackets_and_is_deterministic():
    from app.scoring.ensemble import weight_ensemble
    metrics = _mixed_metrics()
    e1 = weight_ensemble(metrics, n_draws=300)
    e2 = weight_ensemble(metrics, n_draws=300)
    assert e1 == e2                       # seeded -> no flicker between reloads
    assert e1["band_low"] <= e1["band_high"]
    # scores live in the convex hull of category scores (0..90 here)
    assert 0.0 <= e1["band_low"] and e1["band_high"] <= 90.0
    # equal-weight variant is a real composite over the same categories
    assert 0.0 <= e1["equal_weight_score"] <= 100.0
    assert e1["n_draws"] == 300
    assert e1["driver_category"] in {"A", "B", "C", "D", "H", "J"}
    assert e1["driver_direction"] in {"raises", "lowers"}


def test_ensemble_band_brackets_headline():
    from app.scoring.ensemble import weight_ensemble
    metrics = _mixed_metrics()
    headline = compute_composite(metrics).score
    e = weight_ensemble(metrics, n_draws=500)
    # the headline uses in-hull weights, so it must sit inside (or on) the band
    assert e["band_low"] - 0.51 <= headline <= e["band_high"] + 0.51


def test_ensemble_uniform_statuses_collapse_the_band():
    from app.scoring.ensemble import weight_ensemble
    metrics = [_m(f"m{i}", c, 1.0, Status.YELLOW)
               for i, c in enumerate("ABCDHJ")]
    e = weight_ensemble(metrics, n_draws=200)
    # every category scores 50 -> weights cannot matter at all
    assert e["band_low"] == e["band_high"] == 50.0
    assert e["spread"] == 0.0


def test_ensemble_none_when_no_data():
    from app.scoring.ensemble import weight_ensemble
    assert weight_ensemble([_m("x", "A", None, Status.STALE)]) is None
