"""Merge-blocking gates for GET /gdp-watch (studies/gdp-watch.md).

Offline: everything runs on the snapshot frozen with the study (sources/gdp_snapshot.json.gz). Gates:
  - the panel's projection is the study's rule, origin by origin, and the study's numbers reproduce;
  - the shipped record and snapshot are exactly the study's outputs;
  - per-capita growth is GDP growth deflated by population growth over the same four quarters;
  - the payload ships 20 economies, the 6 largest selected, projections four quarters past each one's last quarter,
    nested bands, aggregates never projected, and caveats whose numbers come from the frozen record;
  - every source down degrades to the snapshot, never to an empty tab; the language stays descriptive.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import math
import os

import pytest

from app.metrics import gdp_watch as gw
from app.sources import gdp_data

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))            # treasury-canary/
STUDY = os.path.join(ROOT, "studies", "gdp_watch")
SNAP = os.path.join(STUDY, "data", "snapshot_2026-11-16.json.gz")
KEYS = ("yoy", "qoq", "pop", "ngdpd", "weo_growth")
FORBIDDEN = ["will grow", "will be", "will fall", "will rise", "guarantee", "certain to", "sure to", "imminent",
             "will crash", "all clear", "probability of", "% chance"]


def _module(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(STUDY, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def snap():
    with gzip.open(SNAP, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def inputs(snap):
    return {**{k: snap[k] for k in KEYS}, "status": {k: "ok" for k in KEYS}, "snapshot_as_of": snap["as_of"]}


@pytest.fixture(scope="module")
def payload(inputs):
    return gw.build_gdp_watch(inputs, today="2026-11-16")


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


# ---------------------------------------------------------------------------- the rule is the study's
def test_the_projection_is_the_studys_rule_at_every_origin(snap):
    bt = _module("backtest_v1")
    assert (bt.WINDOW, bt.MIN_WINDOW, bt.MIN_PAIRS, bt.PANDEMIC) == (gw.WINDOW, gw.MIN_WINDOW, gw.MIN_PAIRS, gw.PANDEMIC)
    n = 0
    for c in snap["countries"]:
        y, q = snap["yoy"][c], snap["qoq"][c]
        for t in range(gw.qi("2000-Q1"), max(gw.qi(s) for s in y) + 1):
            mine, ref = gw.forecast_path(y, q, t)[0], bt.forecast(y, q, t, "A")
            assert (mine is None) == (ref is None), (c, gw.qs(t))
            if mine:
                n += 1
                assert all(abs(a - b) < 1e-12 for a, b in zip(mine, ref)), (c, gw.qs(t))
    assert n > 1500


def test_the_studys_numbers_reproduce_from_the_snapshot(snap):
    bt = _module("backtest_v1")
    rows = bt.errors(snap, snap["countries"])
    shipped = gw.BACKTEST["pooled_ex_pandemic"]
    for m in bt.METHODS:
        for h in bt.H:
            assert bt.summary(rows, m, h, True) == shipped[m][str(h)], (m, h)
    assert gw.BACKTEST["chosen"] == bt.choose(shipped) == "A"


def test_the_shipped_record_and_snapshot_are_the_studys():
    ship = _module("ship_v1")
    assert ship.record(os.path.join(STUDY, "out")) == json.load(open(gw.BACKTEST_FILE, encoding="utf-8"))
    assert open(gdp_data.SNAPSHOT, "rb").read() == open(SNAP, "rb").read()


# ---------------------------------------------------------------------------- per capita
def test_population_interpolates_through_the_mid_year_values():
    pop = gw.population_quarterly({"2020": 100.0, "2021": 101.0, "2022": 102.01}, "2020-Q1", "2023-Q4")
    assert math.isclose(math.sqrt(pop["2020-Q2"] * pop["2020-Q3"]), 100.0, rel_tol=1e-9)    # mid-2020 sits between Q2 and Q3
    assert all(pop[gw.qs(i)] < pop[gw.qs(i + 1)] for i in range(gw.qi("2020-Q1"), gw.qi("2023-Q4")))
    assert math.isclose(pop["2022-Q1"] / pop["2021-Q1"], 1.01, rel_tol=1e-9)


def test_per_capita_is_gdp_deflated_by_population_growth():
    pop = gw.population_quarterly({"2020": 100.0, "2021": 101.0, "2022": 102.01}, "2020-Q1", "2022-Q4")
    assert math.isclose(gw.per_capita(3.0, pop, "2021-Q3"), 100 * (1.03 / 1.01 - 1), rel_tol=1e-9)
    assert gw.per_capita(3.0, pop, "2020-Q1") is None and gw.per_capita(None, pop, "2021-Q3") is None


# ---------------------------------------------------------------------------- the payload
def test_payload_ships_twenty_economies_the_six_largest_selected(payload):
    cs = payload["countries"]
    assert [c["code"] for c in cs] == gdp_data.COUNTRIES and len(cs) == 20
    shares = sorted(((c["share_world_pct"] or 0), c["code"]) for c in cs)[::-1]
    assert {c["code"] for c in cs if c["default"]} == {code for _, code in shares[:6]} == {"USA", "CHN", "DEU", "JPN", "GBR", "IND"}
    assert 79 <= sum(c["share_world_pct"] for c in cs) <= 82                     # the 20 are ~80% of world GDP
    assert payload["as_of"] == "2026-Q3" and payload["status"]["overall"] == "ok"


def test_projections_run_four_quarters_past_each_last_quarter_with_nested_bands(payload):
    for c in payload["countries"]:
        f, s = c["forecast"], c["series"]
        assert f and f["from"] == c["last"] == s["quarters"][-1], c["code"]
        assert f["quarters"] == [gw.qs(gw.qi(c["last"]) + h) for h in (1, 2, 3, 4)]
        assert len(s["per_capita"]) == len(s["quarters"]) == len(s["gdp"])
        for m in ("gdp", "per_capita"):
            for b80, b50 in zip(f["band80"][m], f["band50"][m]):
                assert b80[0] <= b50[0] <= b50[1] <= b80[1], (c["code"], m)
        assert c["record"] and c["imf"] and set(c["imf"]) == {"2026", "2027"}
    for a in payload["aggregates"]:
        assert a["forecast"] is None and a["series"]["gdp"]


def test_band_shift_is_the_frozen_error_quantile(payload):
    us = next(c for c in payload["countries"] if c["code"] == "USA")
    q4 = gw.BACKTEST["bands"]["USA"]["4"]
    lo, hi = us["forecast"]["band80"]["gdp"][3]
    v = us["forecast"]["gdp"][3]                                   # rounded; the band was built on the unrounded value
    assert abs(lo - (v + q4["p10"])) < 0.011 and abs(hi - (v + q4["p90"])) < 0.011


def test_caveats_read_their_numbers_from_the_frozen_record(payload):
    text = " ".join(payload["honesty"])
    cov = gw.BACKTEST["coverage"]
    ex = [cov[h]["ex_pandemic"]["in_80"] for h in cov]
    assert f"{round(100 * min(ex))}-{round(100 * max(ex))}% of later outcomes without the pandemic" in text
    worst = min(gw.BACKTEST["recent_bias_h4_since_2023"].items(), key=lambda kv: kv[1]["mean_error"])
    assert f"{gw.NAMES[worst[0]]} {worst[1]['mean_error']:+.1f}" in text
    assert "not real-time vintages" in text and "not backtested here" in text
    flagged = [c["name"] for c in payload["countries"] if c["record"]["naive_better"]]
    assert flagged == ["China", "Indonesia"] and "China and Indonesia" in " ".join(payload["summaries"])


def test_language_stays_descriptive(payload):
    text = " ".join(_strings(payload)).lower()
    for p in FORBIDDEN:
        assert p not in text, p


# ---------------------------------------------------------------------------- degradation
def test_every_source_down_degrades_to_the_snapshot(monkeypatch):
    monkeypatch.setattr(gdp_data.fred_csv, "download_cached", lambda *a, **k: (None, "error"))
    inp = gdp_data.fetch_all()
    assert set(inp["status"].values()) == {"snapshot"}
    p = gw.build_gdp_watch(inp, today="2026-11-16")
    assert p["status"]["overall"] == "snapshot" and all(c["series"] and c["forecast"] for c in p["countries"])


def test_an_html_error_page_is_never_parsed_as_data():
    assert not gdp_data._ok_oecd(b"<html><body>Service unavailable</body></html>")
    assert gdp_data._ok_oecd(b"DATAFLOW,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\n")
    assert not gdp_data._ok_imf(b"<html>")
    body = b"DATAFLOW,REF_AREA,TIME_PERIOD,OBS_VALUE\nX,USA,2026-Q3,2.07\nX,USA,2026-Q2,\nX,ZZZ,2026-Q3,9\nX,USA,2026,1\n"
    assert gdp_data.parse_oecd(body, ["USA"]) == {"USA": {"2026-Q3": 2.07}}


def test_the_route_serves_a_snapshot_payload_cold_and_never_blocks_a_page_on_a_rebuild(monkeypatch):
    from app.api import routes_gdp as rg
    monkeypatch.setattr(rg, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rg, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    p = rg.warm_gdp_watch(force=True)
    assert "boom" in p["build_error"] and p["status"]["overall"] == "snapshot" and len(p["countries"]) == 20
    assert rg.gdp_watch_payload() is p


def test_the_tooltip_numbers_are_the_frozen_records(snap):
    """GdpTab.tsx's TIPS quote the study; this keeps the text and the record in step."""
    tab = open(os.path.join(ROOT, "frontend", "src", "components", "GdpTab.tsx"), encoding="utf-8").read()
    pooled = gw.BACKTEST["pooled_ex_pandemic"]
    assert f"about {pooled['A']['4']['mae']:.1f} points, against {pooled['N']['4']['mae']:.1f} for 'last value holds'" in tab
    cov = gw.BACKTEST["coverage"]
    span = lambda k: f"{round(100 * min(cov[h][k]['in_80'] for h in cov))}-{round(100 * max(cov[h][k]['in_80'] for h in cov))}%"  # noqa: E731
    assert f"about {span('ex_pandemic')} of outcomes outside the pandemic and about {span('all')} with it" in tab
    w = snap["ngdpd"]["WEOWORLD"]["2025"]
    share = sorted((100 * snap["ngdpd"][c]["2025"] / w for c in snap["countries"]), reverse=True)
    assert 100 * (snap["ngdpd"]["USA"]["2025"] + snap["ngdpd"]["CHN"]["2025"]) / w > 40
    assert round(sum(share[:6])) == 57 and round(sum(share)) == 79
    assert "the six largest about 57%, and these 20 about 79%" in tab and "alone are over 40%" in tab
    naive = sorted(gw.NAMES[c] for c, v in gw.BACKTEST["by_country_ex_pandemic"].items() if v["A"]["4"]["mae"] > v["N"]["4"]["mae"])
    assert naive == ["China", "Indonesia"] and "(China, Indonesia)" in tab
    jp, ind = snap["pop"]["JPN"], snap["pop"]["IND"]
    assert jp["2025"] < jp["2020"] and ind["2025"] > 1.03 * ind["2020"]          # "shrinking (Japan)", "grows fast (India)"
    assert "shrinking (Japan)" in tab and "grows fast (India)" in tab
