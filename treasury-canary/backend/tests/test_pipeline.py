"""End-to-end compute_all: synthetic bundle -> metrics + composite + events."""
from datetime import date, timedelta

from app.jobs.refresh import compute_all
from app.metrics.base import Status


def _dates(n):
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


def test_compute_all_flags_resteepening_as_critical():
    # 3m constant at 3.0; 10y walks so 3m10y goes +0.6 -> -0.3 (sustained) -> +0.4 (recent)
    v10 = [3.6] * 12 + [2.7] * 15 + [3.4] * 5
    d = _dates(len(v10))
    bundle = {"3mo": (d, [3.0] * len(v10)), "10y": (d, v10)}

    metrics, analyses, composite, _ = compute_all(bundle)
    by_id = {m.metric_id: m for m in metrics}

    # 3m10y should be RE_STEEPENING -> CRITICAL override
    assert analyses["3m10y"].state.value == "RE_STEEPENING"
    assert by_id["curve.3m10y"].status is Status.CRITICAL
    assert "RE-STEEPENING" in by_id["curve.3m10y"].note

    # recession probability computed from the latest (positive) spread
    rec = by_id["recession.prob"]
    assert rec.value is not None and 0 <= rec.value <= 100

    # composite exists and is decomposable; pairs without tenors are STALE
    assert composite.score is not None
    assert by_id["curve.2s10s"].status is Status.STALE  # no 2y/... in bundle
    assert composite.n_critical >= 1


def test_compute_all_all_stale_is_safe():
    metrics, analyses, composite, _ = compute_all({})
    assert all(m.status is Status.STALE for m in metrics)
    assert composite.score is None and composite.band == "NO_DATA"
