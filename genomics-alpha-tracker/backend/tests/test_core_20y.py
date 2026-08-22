"""Round-7 gates: the FMP data lane, the cross-validation gate itself, the
splice, the three treatments and the regime/recovery arithmetic.

Merge-blocking gates on the MACHINERY, not on the results. Every assertion is
a known answer derived by hand, so a convention change breaks a test instead of
silently moving a 20-year verdict. Nothing here touches the network: the single
HTTP seam (`fmp_prices._http_json`) is monkeypatched, and every study test runs
on hand-built series.

The registered contract is docs/VARIANTS_PREREGISTRATION_R7_20Y.md. The most
important test in this file is `test_gate_fails_*`: the round is only allowed
to produce numbers if the two price lanes agree, and a gate that cannot fail is
not a gate.
"""
from __future__ import annotations

import json
import math

import pytest

from scripts.backtest_core_20y import (
    B5_WEIGHTS,
    GAP_LEGS,
    PROXY_MAP,
    REGIMES,
    START,
    TREATMENTS,
    assumption_share,
    build_legs,
    first_covered,
    regime_stats,
    snap,
    splice_with_provenance,
    window_dates,
)
from scripts.lib import fmp_prices as fmp

# --- fixtures: a tiny synthetic universe --------------------------------------------

DATES = [f"2020-01-{d:02d}" for d in range(1, 11)]      # 10 "trading days"


def ramp(start: float, step: float, dates=DATES) -> dict[str, float]:
    return {d: start * (1 + step) ** i for i, d in enumerate(dates)}


# --- data lane: cache behaviour ------------------------------------------------------

def _rows(sym="ZZZ", n=4):
    return [{"symbol": sym, "date": f"2020-01-0{i + 1}", "adjClose": 100.0 + i}
            for i in range(n)]


def test_fmp_bars_caches_and_does_not_refetch(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("FMP_API_KEY", "TESTKEY")
    monkeypatch.setattr(fmp, "_http_json", lambda url, **kw: (calls.append(url),
                                                              list(reversed(_rows())))[1])
    first = fmp.fmp_bars("ZZZ", cache_dir=tmp_path, delay_s=0)
    assert len(calls) == 1
    assert [r["date"] for r in first] == sorted(r["date"] for r in first), "must be oldest-first"

    def boom(url, **kw):                      # a second network call is a bug
        raise AssertionError("cache miss: fmp_bars re-fetched a cached symbol")

    monkeypatch.setattr(fmp, "_http_json", boom)
    assert fmp.fmp_bars("ZZZ", cache_dir=tmp_path, delay_s=0) == first
    assert json.loads((tmp_path / "ZZZ_2006-01-01.json").read_text()) == first


def test_fmp_bars_never_writes_into_the_frozen_rounds_4_6_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "TESTKEY")
    monkeypatch.setattr(fmp, "_http_json", lambda url, **kw: list(reversed(_rows())))
    fmp.fmp_bars("ZZZ", cache_dir=tmp_path, delay_s=0)
    assert not (fmp.FROZEN_PX_CACHE / "ZZZ_2006-01-01.json").exists()
    assert fmp.FMP_CACHE != fmp.FROZEN_PX_CACHE


def test_fmp_bars_rejects_a_plan_error_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "TESTKEY")
    monkeypatch.setattr(fmp, "_http_json", lambda url, **kw: {"Error Message": "no plan"})
    with pytest.raises(fmp.DataLaneError):
        fmp.fmp_bars("ZZZ", cache_dir=tmp_path, delay_s=0)


def test_fmp_bars_requires_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(fmp, "_http_json", lambda url, **kw: _rows())
    with pytest.raises(fmp.DataLaneError):
        fmp.fmp_bars("ZZZ", cache_dir=tmp_path, delay_s=0)


# --- the cross-validation GATE -------------------------------------------------------

def test_compare_lanes_known_answer():
    a = dict(zip(DATES[:4], [100.0, 110.0, 121.0, 133.1]))
    # Lift every level from day 2 on by 1 bp: exactly ONE daily return differs,
    # by 1.1 bp (0.10 -> 0.10011), and the other two agree to the last bit.
    b = {d: (v * (1 + 1e-4) if i else v) for i, (d, v) in enumerate(a.items())}
    r = fmp.compare_lanes(a, b)
    assert r["n"] == 3
    assert r["max_bps"] == pytest.approx(1.1, rel=1e-3)
    assert r["worst_date"] == DATES[1]
    assert r["rms_bps"] == pytest.approx(1.1 / math.sqrt(3), rel=1e-3)


def test_compare_lanes_ignores_dates_only_one_lane_has():
    """A calendar hole must not become a two-day return and a fake disagreement."""
    a = ramp(100.0, 0.01)
    b = {d: v for d, v in a.items() if d != DATES[5]}
    r = fmp.compare_lanes(a, b)
    assert r["n"] == len(DATES) - 2            # one shared date lost, one return lost
    assert r["rms_bps"] == pytest.approx(0.0, abs=1e-9)


def _lanes(rms_target_bps: float):
    a = ramp(100.0, 0.001)
    bump = rms_target_bps / 1e4
    b = {d: v * (1 + (bump if i % 2 else 0.0)) for i, (d, v) in enumerate(a.items())}
    return a, b


def test_gate_passes_when_every_ticker_agrees():
    a = ramp(100.0, 0.002)
    res = fmp.cross_validate(("SPY", "GLD"), fmp_loader=lambda t: a, sa_loader=lambda t: dict(a))
    assert res["passed"] and all(r["pass"] for r in res["tickers"].values())
    fmp.require_gate(res)                      # must not raise


def test_gate_fails_and_names_the_ticker_when_one_lane_disagrees():
    good = ramp(100.0, 0.002)
    bad = {d: v * (1 + (0.01 if i % 2 else 0.0)) for i, (d, v) in enumerate(good.items())}
    res = fmp.cross_validate(
        ("SPY", "DLS"),
        fmp_loader=lambda t: good,
        sa_loader=lambda t: dict(good) if t == "SPY" else bad)
    assert res["tickers"]["SPY"]["pass"] and not res["tickers"]["DLS"]["pass"]
    assert not res["passed"]
    with pytest.raises(fmp.DataLaneError, match="DLS"):
        fmp.require_gate(res)


def test_gate_treats_an_empty_overlap_as_failure_not_a_skip():
    a = ramp(100.0, 0.002)
    b = {f"2019-01-{i:02d}": 1.0 + i for i in range(1, 6)}
    res = fmp.cross_validate(("SPY",), fmp_loader=lambda t: a, sa_loader=lambda t: b)
    assert res["tickers"]["SPY"]["n"] == 0 and not res["passed"]


def test_gate_treats_a_loader_error_as_failure_not_a_skip():
    def blow(_t):
        raise RuntimeError("network down")

    res = fmp.cross_validate(("SPY",), fmp_loader=blow, sa_loader=lambda t: ramp(1.0, 0.0))
    assert not res["passed"] and "network down" in res["tickers"]["SPY"]["error"]


def test_gate_threshold_is_the_registered_five_bps():
    assert fmp.GATE_RMS_BPS == 5.0
    assert set(fmp.GATE_TICKERS) == {"SPY", "GLD", "EEM", "IWN", "DLS", "XBI"}


# --- splice --------------------------------------------------------------------------

def test_splice_prefers_the_real_fund_and_falls_back_in_order():
    fund = {d: 10.0 * (1 + 0.02) ** i for i, d in enumerate(DATES[5:])}   # exists late only
    proxy = ramp(50.0, 0.01)
    curve, used = splice_with_provenance([("F", fund), ("P", proxy)], DATES)
    assert curve[DATES[0]] == 1.0
    assert used == {"P": 5, "F": 4}            # 9 returns: 5 proxy, then 4 real
    assert curve[DATES[3]] == pytest.approx(1.01 ** 3)
    assert curve[DATES[-1]] == pytest.approx(1.01 ** 5 * 1.02 ** 4)


def test_splice_is_unadjusted_no_alpha_and_scale_free():
    proxy = ramp(50.0, 0.01)
    scaled = {d: v * 7.3 for d, v in proxy.items()}
    assert (splice_with_provenance([("P", proxy)], DATES)[0]
            == pytest.approx(splice_with_provenance([("P", scaled)], DATES)[0]))


def test_splice_hole_is_an_assertion_not_a_silent_zero():
    partial = {d: 1.0 for d in DATES[:3]}
    with pytest.raises(AssertionError, match="splice hole"):
        splice_with_provenance([("P", partial)], DATES)


def test_first_covered_needs_the_prior_day_too():
    s = {d: 1.0 for d in DATES[4:]}
    assert first_covered(s, DATES) == DATES[5]
    assert first_covered({}, DATES) is None


# --- treatments ----------------------------------------------------------------------

def _raw():
    """Every leg + proxy + cash on the synthetic calendar. KMLM/TAIL start late,
    mirroring the real inception gaps the treatments exist for."""
    raw = {"BIL": ramp(90.0, 0.0001), "SHY": ramp(80.0, 0.0001)}
    for leg in B5_WEIGHTS:
        raw[leg] = {} if leg in GAP_LEGS else ramp(20.0, 0.003)
        for p in PROXY_MAP[leg]:
            raw[p] = ramp(30.0, 0.002)
    raw["WTMF"] = {d: 12.0 * 1.005 ** i for i, d in enumerate(DATES[6:])}   # KMLM proxy, late
    raw["TAIL"] = {d: 5.0 * 0.99 ** i for i, d in enumerate(DATES[8:])}     # no proxy at all
    return raw


def test_t1_pays_cash_in_the_gap_and_the_proxy_after_it():
    legs = build_legs(_raw(), DATES, "T1")
    assert legs["provenance"]["KMLM"]["CASH"] == 6      # returns before WTMF's first
    assert legs["provenance"]["KMLM"]["WTMF"] == 3
    assert legs["provenance"]["TAIL"]["CASH"] == 8 and legs["provenance"]["TAIL"]["TAIL"] == 1
    # the whole book is held from day one — nothing is reallocated under T1
    assert legs["target_at"](DATES[0]) == pytest.approx(B5_WEIGHTS)


def test_t3_holds_cash_for_the_whole_leg_across_the_whole_window():
    legs = build_legs(_raw(), DATES, "T3")
    for leg in GAP_LEGS:
        assert legs["curves"][leg] == legs["cash"]
        assert list(legs["provenance"][leg]) == ["CASH (whole leg, T3)"]
    assert legs["target_at"](DATES[-1]) == pytest.approx(B5_WEIGHTS)


def test_t2_drops_the_missing_leg_and_reallocates_pro_rata():
    legs = build_legs(_raw(), DATES, "T2")
    assert legs["entry"]["KMLM"] == DATES[7]     # WTMF's first payable day
    assert legs["entry"]["TAIL"] == DATES[9]
    early = legs["target_at"](DATES[0])
    assert set(early) == set(B5_WEIGHTS) - set(GAP_LEGS)
    assert sum(early.values()) == pytest.approx(1.0)
    # pro-rata: the surviving legs keep their RATIOS
    assert early["AVUV"] / early["AVDV"] == pytest.approx(
        B5_WEIGHTS["AVUV"] / B5_WEIGHTS["AVDV"])
    assert early["AVUV"] == pytest.approx(B5_WEIGHTS["AVUV"] / (1 - 0.19))
    mid = legs["target_at"](DATES[8])            # KMLM in, TAIL not yet
    assert "KMLM" in mid and "TAIL" not in mid
    assert sum(mid.values()) == pytest.approx(1.0)
    assert legs["target_at"](DATES[9]) == pytest.approx(B5_WEIGHTS)


def test_t2_gap_curve_is_flat_and_never_held():
    legs = build_legs(_raw(), DATES, "T2")
    assert legs["provenance"]["KMLM"]["FLAT"] == 6
    for d in DATES[:7]:
        assert "KMLM" not in legs["target_at"](d)


def test_qual_sensitivity_drops_the_spy_stand_in():
    base = build_legs(_raw(), DATES, "T1")
    qr = build_legs(_raw(), DATES, "T1", qual_realloc=True)
    assert base["provenance"]["QUAL"].get("SPY", 0) >= 0        # baseline may use the proxy
    assert "SPY" not in qr["provenance"]["QUAL"]                # sensitivity must not
    assert qr["entry"]["QUAL"] == DATES[1]                      # this synthetic QUAL is real
    assert base["target_at"](DATES[0]) == pytest.approx(B5_WEIGHTS)


def test_qual_sensitivity_reallocates_when_qual_does_not_exist_yet():
    raw = _raw()
    raw["QUAL"] = {d: v for d, v in raw["QUAL"].items() if d >= DATES[5]}
    qr = build_legs(raw, DATES, "T1", qual_realloc=True)
    assert qr["entry"]["QUAL"] == DATES[6]
    early = qr["target_at"](DATES[0])
    assert "QUAL" not in early and sum(early.values()) == pytest.approx(1.0)


def test_every_treatment_is_registered_and_targets_always_sum_to_one():
    assert set(TREATMENTS) == {"T1", "T2", "T3"}
    for t in TREATMENTS:
        for qr in (False, True):
            legs = build_legs(_raw(), DATES, t, qual_realloc=qr)
            for d in DATES:
                assert sum(legs["target_at"](d).values()) == pytest.approx(1.0)


def test_build_legs_rejects_an_unregistered_treatment():
    with pytest.raises(AssertionError):
        build_legs(_raw(), DATES, "T4")


# --- regimes / recovery --------------------------------------------------------------

def test_regime_stats_known_answer_drawdown_trough_and_recovery():
    #            0    1    2    3    4    5    6    7    8    9
    vals = [100, 110, 88, 80, 90, 100, 105, 111, 120, 130]
    curve = dict(zip(DATES, [float(v) for v in vals]))
    r = regime_stats(curve, DATES, DATES[0], DATES[5])
    assert r["max_dd"] == pytest.approx(1 - 80 / 110)      # peak 110 -> trough 80
    assert r["trough"] == DATES[3]
    # recovery is scanned through the FULL series, past the regime's own end
    assert r["recovery_days"] == 4 and r["recovery_date"] == DATES[7]
    assert r["total_return"] == pytest.approx(0.0)


def test_regime_recovery_is_none_when_it_never_comes_back():
    curve = dict(zip(DATES, [100.0, 120.0] + [50.0] * 8))
    r = regime_stats(curve, DATES, DATES[0], DATES[4])
    assert r["max_dd"] == pytest.approx(1 - 50 / 120)
    assert r["recovery_days"] is None and r["recovery_date"] is None


def test_regime_peak_starts_inside_the_window_no_phantom_peak():
    curve = dict(zip(DATES, [200.0] + [100.0, 99.0] + [100.0] * 7))
    r = regime_stats(curve, DATES, DATES[1], DATES[4])
    assert r["max_dd"] == pytest.approx(0.01)              # not 1 - 99/200


def test_snap_moves_forward_and_backward():
    assert snap(DATES, "2019-12-31", forward=True) == DATES[0]
    assert snap(DATES, "2020-01-04", forward=False) == DATES[3]
    assert snap(DATES, "2020-01-04", forward=True) == DATES[3]
    with pytest.raises(AssertionError):
        snap(DATES, "2030-01-01", forward=True)


def test_registered_regimes_are_the_ones_the_contract_names():
    assert [n for n, _, _ in REGIMES] == ["GFC", "recovery", "COVID", "2022",
                                          "round-4/5 window"]
    assert dict((n, (a, b)) for n, a, b in REGIMES)["GFC"] == ("2007-10-09", "2009-03-09")
    assert dict((n, (a, b)) for n, a, b in REGIMES)["round-4/5 window"] == ("2020-12-03",
                                                                           "2026-08-19")


# --- window / assumption share -------------------------------------------------------

def test_window_dates_asserts_the_registered_endpoints():
    raw = {s: ramp(1.0, 0.0) for s in ("SPY", "SLYV", "DLS", "EEM", "GLD", "SHY")}
    assert window_dates(raw, DATES[0], DATES[-1]) == DATES
    with pytest.raises(AssertionError):
        window_dates(raw, "2019-01-01", DATES[-1])


def test_assumption_share_partitions_the_whole_book():
    raw = _raw()
    for m in assumption_share(raw, DATES):
        assert m["real"] + m["proxied"] + m["missing"] == pytest.approx(1.0)


def test_registered_window_start_is_the_five_thousand_row_cap():
    assert START == "2006-10-05"
    assert fmp.FMP_ROW_CAP == 5000
