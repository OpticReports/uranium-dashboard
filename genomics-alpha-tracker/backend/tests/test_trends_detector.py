"""Google Trends attention-top detector gates (merge-blocking).

G1 frozen-fixture replay: the eleven real series in docs/trends_peak/fixtures
   must reproduce the study's flag dates. A detector change that moves them
   fails here and must re-freeze the study (and its honesty box) knowingly.
G2 no look-ahead: the flags at week t are identical whether the detector
   sees the series truncated at t or the full series.
G3 scale invariance: the 0-100 index is renormalised per request window;
   rescaling the series must not change a single flag.
G4 null calibration: on i.i.d. noise and on a shuffled real series the
   CLIMAX rate stays far below what the real tops produce.
G5 the frozen study mirror served to the container equals the docs copy.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

from app.trends.detector import PARAMS, compute, episodes, summary

DOCS = Path(__file__).resolve().parents[2] / "docs" / "trends_peak"
FIXTURES = DOCS / "fixtures"


def _load(name: str):
    fx = json.load(open(FIXTURES / f"{name}.json"))
    w = fx["weeks"]
    return [x["date"] for x in w], [x["interest"] for x in w], [x["close"] for x in w]


def _flag_dates(pts, flag):
    return [pts[i].date for i in episodes(pts, flag)]


# --- G1 frozen replay ---------------------------------------------------------
@pytest.mark.parametrize("name,climax,fading,divergence", [
    ("silver_2011", ["2011-04-17"], [], []),
    ("silver_2026", ["2025-10-12", "2025-12-21"], ["2025-11-09", "2026-02-22"], ["2025-11-09"]),
    ("bitcoin_2017", ["2017-05-07", "2017-10-29"], [], []),
    ("bitcoin_2021", ["2021-01-03"], [], ["2021-04-04"]),
    ("bitcoin_2025", [], [], ["2025-06-22"]),
    ("gme_2021", ["2021-01-24"], [], []),
    ("arkg_2021", ["2020-11-29"], [], []),
    ("gold_2026", ["2025-04-06", "2025-08-10", "2026-01-25"],
     ["2025-05-25", "2026-02-22"], ["2025-06-01", "2025-11-23", "2026-02-22"]),
    ("uranium_2024", ["2025-08-03", "2026-01-04"], ["2026-02-15"], []),
])
def test_g1_frozen_flags(name, climax, fading, divergence):
    d, i, c = _load(name)
    pts = compute(d, i, c)
    assert _flag_dates(pts, "climax") == climax
    assert _flag_dates(pts, "fading") == fading
    assert _flag_dates(pts, "divergence") == divergence


def test_g1_stage_labels_frozen():
    d, i, c = _load("gold_2026")
    pts = compute(d, i, c)
    stages = [pts[k].stage for k in episodes(pts, "climax")]
    assert stages == [1, 2, 3]
    d, i, c = _load("silver_2011")
    pts = compute(d, i, c)
    assert [pts[k].stage for k in episodes(pts, "climax")] == [1]


def test_g1_study_recall_and_pooled_numbers_match_frozen_json():
    sys.path.insert(0, str(DOCS))
    import run_study  # noqa: E402
    res = run_study.study()
    frozen = json.load(open(DOCS / "study_results.json"))
    assert res["pooled"]["recall"] == frozen["pooled"]["recall"]
    assert res["pooled"]["recall"]["with_climax_within_10wk"] == 8
    assert res["pooled"]["recall"]["price_peaks"] == 11
    for flag in ("climax", "climax_stage1", "climax_stage2plus", "fading", "divergence", "cooled"):
        assert res["pooled"][flag]["episodes"] == frozen["pooled"][flag]["episodes"], flag
        for h in ("r12", "r26", "dd26"):
            assert res["pooled"][flag][h] == frozen["pooled"][flag][h], (flag, h)
    assert res["pooled"]["base_rate"] == frozen["pooled"]["base_rate"]
    assert res["params"] == frozen["params"] == PARAMS


# --- G2 no look-ahead ---------------------------------------------------------
@pytest.mark.parametrize("name", ["silver_2011", "bitcoin_2017", "gold_2026"])
def test_g2_no_lookahead(name):
    d, i, c = _load(name)
    full = compute(d, i, c)
    for t in (60, 100, 150, 200, len(d) - 1):
        part = compute(d[:t + 1], i[:t + 1], c[:t + 1])
        a, b = full[t], part[-1]
        assert (a.climax, a.fading, a.divergence, a.cooled, a.state, a.stage) == \
               (b.climax, b.fading, b.divergence, b.cooled, b.state, b.stage), (name, t)


# --- G3 scale invariance ------------------------------------------------------
@pytest.mark.parametrize("name", ["silver_2026", "bitcoin_2021"])
def test_g3_window_renormalisation_invariance(name):
    d, i, c = _load(name)
    base = compute(d, i, c)
    # a different request window would show the same shape at a different
    # scale; only the noise floor is absolute, so keep the peak >= floor.
    scaled = compute(d, [v * 0.6 for v in i], c, params={"noise_floor": 6.0})
    for a, b in zip(base, scaled):
        assert (a.climax, a.fading, a.divergence, a.cooled) == (b.climax, b.fading, b.divergence, b.cooled)
    # price scale never matters
    scaled_px = compute(d, i, [None if x is None else x * 1000 for x in c])
    for a, b in zip(base, scaled_px):
        assert (a.climax, a.fading, a.divergence, a.cooled) == (b.climax, b.fading, b.divergence, b.cooled)


# --- G4 null calibration ------------------------------------------------------
def test_g4_iid_noise_rarely_climaxes():
    rng = random.Random(7)
    n = 520
    dates = [f"w{k:04d}" for k in range(n)]
    px = [100.0]
    for _ in range(n - 1):
        px.append(px[-1] * (1 + rng.gauss(0, 0.03)))
    rate = []
    for _ in range(20):
        interest = [max(0.0, rng.gauss(30, 8)) for _ in range(n)]
        pts = compute(dates, interest, px)
        rate.append(len(episodes(pts, "climax")))
    # Gaussian noise around a stable mean never doubles in 4 weeks AND doubles
    # its median AND sets a 3-year record: expect ~0 episodes per 10 years.
    assert sum(rate) / len(rate) <= 0.5, rate


def test_g4_shuffled_real_series_climaxes_less_than_real():
    d, i, c = _load("gold_2026")
    real = len(episodes(compute(d, i, c), "climax"))
    rng = random.Random(3)
    shuffled_counts = []
    for _ in range(30):
        s = list(i)
        rng.shuffle(s)
        shuffled_counts.append(len(episodes(compute(d, s, c), "climax")))
    assert real == 3
    assert sum(shuffled_counts) / len(shuffled_counts) < real


# --- misc contract ------------------------------------------------------------
def test_no_price_series_gives_climax_but_no_price_flags():
    d, i, c = _load("silver_2011")
    pts = compute(d, i, None)
    assert any(p.climax for p in pts)
    assert not any(p.fading or p.divergence or p.cooled for p in pts)
    s = summary(pts)
    assert s["weeks"] == len(d) and s["state"] in {"QUIET", "ELEVATED", "CLIMAX"}


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        compute(["a", "b"], [1.0], None)


def test_g5_container_mirror_of_study_is_identical():
    docs = json.load(open(DOCS / "study_results.json"))
    mirror = json.load(open(Path(__file__).resolve().parents[1] / "config" / "trends_study_frozen.json"))
    assert docs == mirror
