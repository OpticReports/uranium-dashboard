"""Statistical regime: static hindcast, current-state fit, guardrails."""
import datetime

from app.metrics.stat_regime import build_stat_regime, load_hindcast


def test_hindcast_ships_and_covers_history():
    h = load_hindcast()
    assert len(h) > 500
    months = [r["month"] for r in h]
    assert months[0] <= "1978-01" and months[-1] >= "2026-01"
    # the validated calls are baked into the shipped timeline
    tl = {r["month"]: r for r in h}
    assert tl["2008-11"]["state"] == "STRESS"
    assert tl["2022-09"]["state"] == "STRESS" and tl["2022-09"]["dir"] == "selloff"
    assert tl["2020-03"]["state"] == "STRESS" and tl["2020-03"]["dir"] == "rally"


def test_empty_bundle_degrades_to_stale_current():
    out = build_stat_regime({})
    assert out["current"] is None          # STALE, never a fabricated state
    assert len(out["hindcast"]) > 500      # history still served
    assert "never feed alerts" in out["framing"]


def test_current_fit_labels_a_stressed_tape():
    # 8 years of calm 10y tape, then 3 months of violent selloff
    import random
    rng = random.Random(3)
    days, vals, y = [], [], 4.0
    d = datetime.date(2018, 1, 1)
    for i in range(2100):
        d += datetime.timedelta(days=1)
        step = rng.gauss(0, 0.015 if i < 2040 else 0.14)   # bp storm at the end
        y = max(0.5, y + step + (0.004 if i >= 2040 else 0))
        days.append(d)
        vals.append(round(y, 4))
    out = build_stat_regime({"10y": (days, vals)})
    cur = out["current"]
    assert cur is not None
    assert cur["state"] in ("ELEVATED", "STRESS")
    if cur["state"] == "STRESS":
        assert cur["direction"] in ("selloff", "rally")
    assert 0.0 <= cur["confidence"] <= 1.0
