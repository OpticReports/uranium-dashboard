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
    assert f"{gw.NAMES[worst[0]]} {gw._f(worst[1]['mean_error'], sign=True)}" in text
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


def test_the_route_serves_a_labelled_snapshot_payload_cold(monkeypatch):
    from app.api import routes_gdp as rg
    monkeypatch.setattr(rg, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rg, "_building", {"on": False})
    monkeypatch.setattr(rg, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    p = rg.warm_gdp_watch(force=True)
    assert "boom" in p["build_error"] and p["status"]["overall"] == "snapshot" and len(p["countries"]) == 20
    assert p["build_fallback"] == "snapshot" and rg.gdp_watch_payload() is p
    again = rg.warm_gdp_watch(force=True)                     # a second failure: still the snapshot, still said so
    assert again["status"]["overall"] == "snapshot" and again["build_fallback"] == "snapshot"


def test_a_failure_after_a_live_build_serves_it_as_stale(monkeypatch, inputs):
    from app.api import routes_gdp as rg
    live = gw.build_gdp_watch(inputs, today="2026-11-16")
    monkeypatch.setattr(rg, "_cache", {"ts": 0.0, "data": live, "retry_after": 0.0})
    monkeypatch.setattr(rg, "_building", {"on": False})
    monkeypatch.setattr(rg, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    p = rg.warm_gdp_watch(force=True)
    assert p["status"]["overall"] == "stale" and p["build_fallback"] == "previous" and p["countries"] == live["countries"]


def test_an_expired_cache_is_served_at_once_and_rebuilt_once_in_the_background(monkeypatch, inputs):
    import types
    from app.api import routes_gdp as rg
    p0 = gw.build_gdp_watch(inputs, today="2026-11-16")
    monkeypatch.setattr(rg, "_cache", {"ts": 0.0, "data": p0, "retry_after": 0.0})      # long expired
    monkeypatch.setattr(rg, "_building", {"on": False})
    started: list[str] = []

    class _Thread:
        def __init__(self, target, name, daemon):
            started.append(name)

        def start(self):
            pass                                                # the rebuild is still "running"
    monkeypatch.setattr(rg, "threading", types.SimpleNamespace(Thread=_Thread))
    assert rg.gdp_watch_payload() is p0 and rg.gdp_watch_payload() is p0
    assert started == ["gdp-watch-rebuild"]


def test_a_forced_warm_up_waits_for_a_running_build_instead_of_starting_another(monkeypatch, inputs):
    import threading
    import time
    from app.api import routes_gdp as rg
    p0 = gw.build_gdp_watch(inputs, today="2026-11-16")
    p1 = dict(p0, generated="later")
    monkeypatch.setattr(rg, "_cache", {"ts": 0.0, "data": p0, "retry_after": 0.0})
    monkeypatch.setattr(rg, "_building", {"on": True})                                 # a page-started build runs
    fetches: list[int] = []
    monkeypatch.setattr(rg, "fetch_all", lambda: fetches.append(1) or inputs)

    def finish():
        time.sleep(0.7)
        with rg._lock:
            rg._cache.update(ts=time.time(), data=p1)
            rg._building["on"] = False
    threading.Thread(target=finish, daemon=True).start()
    assert rg.warm_gdp_watch(force=True) is p1 and fetches == []


def test_the_tooltip_numbers_are_the_frozen_records(snap):
    """GdpTab.tsx's TIPS quote the study; this keeps the text and the record in step."""
    tab = open(os.path.join(ROOT, "frontend", "src", "components", "GdpTab.tsx"), encoding="utf-8").read()
    pooled = gw.BACKTEST["pooled_ex_pandemic"]
    assert f"about {gw._f(pooled['A']['4']['mae'])} points, against {gw._f(pooled['N']['4']['mae'])} for 'last value holds'" in tab
    assert gw._f(2.25) == "2.3" and gw._f(1.285, 2) == "1.29" and gw._f(-1.148, sign=True) == "-1.1"   # half-up, once
    cov = gw.BACKTEST["coverage"]
    span = lambda k: f"{round(100 * min(cov[h][k]['in_80'] for h in cov))}-{round(100 * max(cov[h][k]['in_80'] for h in cov))}%"  # noqa: E731
    assert f"about {span('ex_pandemic')} of outcomes outside the pandemic and about {span('all')} with it" in tab
    untested = [gw.NAMES[c] for c in gw.gw_untested(gw.BACKTEST["coverage_tested"])]
    assert untested == ["China", "Saudi Arabia"] and len(gw.BACKTEST["coverage_tested"]) == 18
    assert "tested on 18 economies; China's and Saudi Arabia's bands are in-sample only" in tab
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


# ---------------------------------------------------------------------------- the review's fixes (2026-11-16)
def test_a_line_outside_its_own_band_is_flagged_with_its_record(payload):
    """counter-agent SERIOUS: China's dashed line sat above its own band with no word on why."""
    for c in payload["countries"]:
        f = c["forecast"]
        v, (lo, hi) = f["gdp"][3], f["band50"]["gdp"][3]
        assert f["line_vs_band"] == ("above" if v > hi else "below" if v < lo else None), c["code"]
    flagged = {c["code"]: c for c in payload["countries"] if c["forecast"]["line_vs_band"]}
    assert list(flagged) == ["CHN"] and flagged["CHN"]["forecast"]["line_vs_band"] == "above"
    r = flagged["CHN"]["record"]
    assert (r["n_over_h4"], r["n_h4"]) == (31, 32) and r["median_miss_h4"] == gw.BACKTEST["bias_h4"]["CHN"]["median"]
    assert ("For China the line sits above its band: the rule over-projected it in 31 of 32 backtests (median miss "
            f"{gw._f(r['median_miss_h4'], sign=True)} points)") in " ".join(payload["summaries"])
    tab = open(os.path.join(ROOT, "frontend", "src", "components", "GdpTab.tsx"), encoding="utf-8").read()
    assert "line_vs_band" in tab and "its own band" in tab


def test_the_rule_vs_trend_choice_is_recorded_as_fragile():
    """review MINOR: the margin over trend is inside the noise, and the pandemic-in choice would have been trend."""
    ch = gw.BACKTEST["choice"]
    assert ch["pick_if_pandemic_in"] == "T" and 0.025 < ch["margin_if_pandemic_in"] < 0.035
    assert len(ch["t_better_in"]) == 12 and ch["t_vs_a_bootstrap"]["lo"] < 0 < ch["t_vs_a_bootstrap"]["hi"]


def test_india_imf_figures_are_labelled_fiscal_years(payload):
    basis = {c["code"]: c["imf_basis"] for c in payload["countries"]}
    assert basis.pop("IND").startswith("fiscal years (April-March)") and set(basis.values()) == {"calendar years"}
    tab = open(os.path.join(ROOT, "frontend", "src", "components", "GdpTab.tsx"), encoding="utf-8").read()
    assert "India's, which are fiscal years (April-March)" in tab


def test_population_breaks_are_noted_and_the_note_matches_the_series(snap, payload):
    notes = {c["code"]: c["pop_note"] for c in payload["countries"] if c["pop_note"]}
    assert set(notes) == {"SAU", "POL"}
    g = {c: {y: 100 * (p[str(y)] / p[str(y - 1)] - 1) for y in range(2011, 2027)} for c, p in snap["pop"].items()
         if c in ("SAU", "POL")}
    sau = [g["SAU"][y] for y in range(2018, 2023)]
    assert f"({min(sau):+.1f}% to {max(sau):+.1f}%)" in notes["SAU"]
    assert f"drops {-g['POL'][2021]:.1f}% in 2021" in notes["POL"]
    assert abs(g["POL"][2020]) < 0.5 and abs(g["POL"][2022]) < 0.5


# ---------------------------------------------------------------------------- the build review's fixes (2026-11-16)
def test_the_imf_years_follow_the_data_never_the_clock(monkeypatch, inputs):
    """review SERIOUS: the IMF columns took their years from the wall clock, so they moved on 1 January."""
    import datetime as real

    class _Late(real.datetime):
        @classmethod
        def now(cls, tz=None):
            return real.datetime(2027, 1, 2, tzinfo=tz)
    monkeypatch.setattr(gw, "datetime", _Late)
    p = gw.build_gdp_watch(inputs, today="2026-11-16")
    assert {tuple(c["imf"]) for c in p["countries"]} == {("2026", "2027")}      # the years 2026-Q4..2027-Q3 reach
    later = json.loads(json.dumps(inputs))
    for c in later["yoy"]:
        later["yoy"][c]["2026-Q4"] = later["yoy"][c].get("2026-Q3")            # one more quarter published
    assert {tuple(c["imf"]) for c in gw.build_gdp_watch(later, today="2027-02-20")["countries"]} == {("2027",)}


def test_an_unparseable_reply_falls_back_and_a_missing_economy_keeps_its_snapshot(monkeypatch):
    monkeypatch.setattr(gdp_data.fred_csv, "download_cached",
                        lambda name, *a, **k: (b"DATAFLOW,REF_AREA,TIME_PERIOD,OBS_VALUE\n\xff\xfe", "ok")
                        if name.startswith("gdp_oecd_") else (None, "error"))
    inp = gdp_data.fetch_all()                                  # passes validation, fails to decode: never cached as data
    assert inp["status"]["yoy"] == inp["status"]["qoq"] == "snapshot"
    usa_only = b"DATAFLOW,REF_AREA,TIME_PERIOD,OBS_VALUE\nX,USA,2026-Q3,2.07\n"
    monkeypatch.setattr(gdp_data.fred_csv, "download_cached",
                        lambda name, *a, **k: (usa_only, "ok") if name.startswith("gdp_oecd_") else (None, "error"))
    inp = gdp_data.fetch_all()
    assert inp["status"]["yoy"] == "partial" and "CHN" in inp["filled"]["yoy"] and inp["yoy"]["CHN"]
    p = gw.build_gdp_watch(inp, today="2026-11-16")
    assert p["status"]["inputs"]["yoy"] == "partial" and p["status"]["filled"]["yoy"] == inp["filled"]["yoy"]
    assert p["status"]["overall"] != "ok"                       # never "live" while part of it is the snapshot


def test_no_projection_means_no_word_about_one(inputs):
    q = {k: v for k, v in inputs.items()}
    q["qoq"] = {}                                                # yoy and q/q out of step: nothing can be projected
    p = gw.build_gdp_watch(q, today="2026-11-16")
    assert all(c["forecast"] is None for c in p["countries"])
    assert not any("dashed projection" in s for s in p["summaries"])


def test_the_honesty_box_says_what_is_in_sample_and_what_was_not_tested(payload):
    text = " ".join(payload["honesty"])
    assert "The rule was chosen in-sample, on the same data" in text
    assert "The bands drawn use every backtest miss from 2006-Q1 on, so they are in-sample too" in text
    assert "on the origins both windows share, 2016-Q4 on" in text
    assert "the per-person version was not backtested on its own" in text


def test_the_tab_source_keeps_to_descriptive_language():
    """the "?" cards render only on hover, outside the smoke's render: scan the source too."""
    tab = open(os.path.join(ROOT, "frontend", "src", "components", "GdpTab.tsx"), encoding="utf-8").read().lower()
    for p in FORBIDDEN:
        assert p not in tab, p
