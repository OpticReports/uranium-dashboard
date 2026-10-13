"""End-to-end dry run of bottoms.run() on SYNTHETIC stand-ins for every
failure, filing and claims series (the real ones are scored once, in the run).
Equity prices (the targets) are real.

    python3 -m pytest -q test_bottoms_dryrun.py
"""
from __future__ import annotations

import datetime as dt
import json
import os

import numpy as np
import pytest

import bottoms as BT
import bottoms_power as BP
import load as D
from engine import M

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture()
def synthetic(monkeypatch):
    if not os.path.exists(os.path.join(HERE, "bottoms_power.json")):
        pytest.skip("bottoms_power.json not built yet")
    rng = np.random.default_rng(7)
    segs = BP.synth_segments(rng, "inf", 0, 4)
    monkeypatch.setattr(D, "dnb_count_segments", lambda fix=True: [dict(s) for s in segs])
    lev = {m: 300 * np.exp(0.1 * np.sin(m / 9)) for m in range(M(1894, 1), M(1983, 12) + 1)}
    monkeypatch.setattr(D, "dnb_liability_segments",
                        lambda: [{m: v for m, v in lev.items() if m <= M(1938, 8)},
                                 {m: v for m, v in lev.items() if m >= M(1939, 1)}])
    q = {D.qi(y, k): 15000 * np.exp(0.2 * np.sin((4 * y + k) / 7)) for y in range(1980, 2026) for k in (1, 2, 3, 4)}
    monkeypatch.setattr(D, "abi_quarterly_business", lambda: dict(q))
    monkeypatch.setattr(D, "f2_national", lambda kind, col: {D.qi(2026, 1): 16000, D.qi(2026, 2): 16500})
    weeks = {}
    d = dt.date(1967, 1, 7)
    while d <= dt.date(2026, 10, 3):
        weeks[d] = 300000 * np.exp(0.3 * np.sin(d.toordinal() / 400))
        d += dt.timedelta(days=7)
    monkeypatch.setattr(D, "claims_weekly", lambda sa=True: dict(weeks))
    monkeypatch.setattr(BT, "PERMS", 99)
    yield


def test_the_run_completes_on_synthetic_inputs(synthetic):
    res = BT.run()
    json.dumps(res, default=lambda o: None)
    assert set(res["P"]["shots"]) == set(BT.SHOTS)
    for s, r in res["P"]["shots"].items():
        assert r["n"] == (16 if "trough" in s else r["n"]) and len(r["episodes"]) == r["n"]
        assert set(r["grid"]) == {"3", "12"}
    assert set(res["P"]["sensitivities"]) == {"release_plus2", "1898_06_masked", "1933_straight_across",
                                             "1937_on_A", "theta10_from_1918", "theta10_from_1918_timing",
                                             "theta20_from_1918_timing"}
    # nothing is graded: every shot was out of reach before the run
    assert res["P"]["grade"]["tested"] == [] and res["P"]["grade"]["status"].startswith("NOT TESTED")
    for s, t in res["P"]["timing"].items():
        assert {"n", "median", "n_miss", "n_censored", "by_era"} <= set(t)
        assert t["n"] + t["n_censored"] == res["P"]["shots"][s]["n"]
    assert "n_peaked_before_p" in res["P"]["g_peak"]
    assert set(res["P"]["romer"]) == {"MARKS-trough", "CONFIRMS-trough"}
    assert res["P"]["false_bottoms"]["decades_observed"] > 5
    assert {"primary", "mask_1980Q1", "release_plus2", "1995_in_Q1", "1995_in_Q2", "1995_in_Q3"} == set(res["R"])
    assert "excluding_war_years" in res["P"]["false_bottoms"]
    assert "without_war" in res["P"]["timing"]["CONFIRMS-trough"]
    assert "valid_only" in res["P"]["timing"]["MARKS-equity"]
    assert res["R"]["primary"]["live"]["asof"] == "2026Q2"
    assert "1990-07" in res["claims"] and "1981-07" in res["liabilities"] and "1990-07" not in res["liabilities"]
    assert res["trader"]["median"]["rollover_P"]["episodes"] == 16
