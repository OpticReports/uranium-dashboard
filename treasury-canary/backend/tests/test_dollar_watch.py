"""Merge-blocking gate tests for GET /dollar-watch (studies/dollar-watch.md §5, §9).

Offline. The assembly runs on the fetch_all() output captured 2026-11-02
(tests/fixtures/dollar_watch, FRED series other than the rule's three and SWPT
trimmed to 2019+). Gates:
  - the live rule reproduces the reference's 7 re-arm / 6 unpatched firings, clause
    values included, and the reference agrees with the study's own rule outputs;
  - the reference rebuilds byte-identical and carries the numbers the memo cites;
  - percentiles are tie-safe; monthly changes use calendar keys, and a gap is an error;
  - the forward ledger is append-only, forward-only, point-in-time, and freezes outcomes once;
  - the scramble indicators exist only with the gate open and are never summed;
  - EM FX outcomes are withheld; forbidden language never appears;
  - the all-null payload ships every block plus the frozen record; nothing crashes on partial data.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import subprocess
import sys

import pytest

from app.metrics import dollar_watch as dw
from app.sources import dollar_data, fred_csv

HERE = os.path.dirname(__file__)
FX = os.path.join(HERE, "fixtures", "dollar_watch", "inputs_2026-11-02.json.gz")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))            # treasury-canary/
STUDY = os.path.join(ROOT, "studies", "dollar_watch")
REF_FILE = os.path.join(ROOT, "backend", "app", "sources", "dollar_reference.json")
TAB_SOURCES = [os.path.join(ROOT, "frontend", "src", "components", "DollarTab.tsx"),
               os.path.join(ROOT, "frontend", "src", "lib", "dollarFixture.ts")]

# memo §5 and the wording review: never on the panel
FORBIDDEN = ["probability of", "p(crisis", "chance of a crisis", "% chance", "crisis subsided", "subsided",
             "crisis over", "crisis is over", "all clear", "countdown", "next crisis in", "every crisis",
             "will crash", "imminent", "band breach", "ends in crisis", "leads the vix", "lamp",
             "points below the top", "dates the end of"]


@pytest.fixture(scope="module")
def inputs():
    with gzip.open(FX, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def payload(inputs, tmp_path):
    return dw.build_dollar_watch(inputs, today="2026-11-02", ledger_file=str(tmp_path / "ledger.json"))


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def _cut(inputs, day: str):
    out = json.loads(json.dumps(inputs))
    for s in list(out["fred"].values()) + [out["dxy"], out["gold"], out["emb"]]:
        keep = [i for i, d in enumerate(s["dates"]) if d <= day]
        s["dates"] = [s["dates"][i] for i in keep]
        s["values"] = [s["values"][i] for i in keep]
    return out


# ---------------------------------------------------------------------------- the frozen rule
def test_live_rule_reproduces_frozen_firings(inputs):
    ds, B, Y = dw.rule_index(inputs["fred"])
    re = dw.scramble_firings(ds, B, Y, True)
    un = dw.scramble_firings(ds, B, Y, False)
    frozen = dw.REF["scramble_rule"]["firings"]
    assert [f["date"] for f in re if f["date"] <= dw.LAST_INDEX_DAY] == [f["date"] for f in frozen]
    assert [f["date"] for f in un if f["date"] <= dw.LAST_INDEX_DAY] == dw.REF["scramble_rule"]["firings_unpatched"]
    assert len(frozen) == 7 and len(dw.REF["scramble_rule"]["firings_unpatched"]) == 6
    for live, ref in zip(re, frozen):
        for k in ("roc20_max_pct", "roc20_max_date", "roc20_now_pct", "dollar"):
            assert live[k] == ref[k], (live["date"], k)


def test_reference_matches_the_studys_own_rule_outputs():
    """anchor to the study's committed decel_realtime*.json, not only to the builder's copy of the rule."""
    for name, frozen in (("decel_realtime_rearm.json", dw.REF["scramble_rule"]["firings"]),
                         ("decel_realtime.json", [f for f in dw.REF["scramble_rule"]["firings"]
                                                  if f["date"] in dw.REF["scramble_rule"]["firings_unpatched"]])):
        study = json.load(open(os.path.join(STUDY, "data", name)))
        assert [s["fire"] for s in study] == [f["date"] for f in frozen]
        for s, f in zip(study, frozen):
            assert (s["roc20_max_pct"], s["roc_max_day"], s["roc20_now_pct"], s["dollar_more_rise_pct"], s["dollar_peak_next250"]) == \
                   (f["roc20_max_pct"], f["roc20_max_date"], f["roc20_now_pct"], f["dollar_further_rise_pct"], f["dollar_peak_date"])
            assert s["vix_fwd60_chg"] == f["vix_change_60d"]


def test_rule_params_are_the_frozen_ones():
    assert dw.REF["scramble_rule"]["params"] == dw.RULE_FROZEN
    assert dw.LAST_INDEX_DAY == "2026-10-23" and dw.LAST_FROZEN_MONTH == "2026-10"


def test_rule_index_is_the_frozen_one(inputs):
    ds, _, _ = dw.rule_index(inputs["fred"])
    have = {s: set(inputs["fred"][s]["dates"][i] for i, v in enumerate(inputs["fred"][s]["values"]) if v is not None)
            for s in ("DTWEXBGS", "DGS10", "VIXCLS")}
    assert set(ds) == have["DTWEXBGS"] & have["DGS10"] & have["VIXCLS"]


def test_rule_evaluates_the_latest_day():
    """the study code skipped the final index day; the live rule must not."""
    n = 200
    ds = [f"2030-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    B = [100.0] * 100 + [100.0 * math.exp(0.003 * j) for j in range(1, 81)]
    B += [B[-1] * (1 + 0.0002 * j) for j in range(1, 21)]
    Y = [3.0] * 100 + [3.0 - 0.01 * j for j in range(1, 101)]
    fires = dw.scramble_firings(ds, B, Y, True)
    assert fires, "synthetic scramble must fire"
    k = fires[0]["k"]
    assert dw.scramble_firings(ds[:k + 1], B[:k + 1], Y[:k + 1], True)[-1]["k"] == k


def test_h10_release_is_the_monday_after_the_week():
    assert dw.h10_release("2008-11-06") == "2008-11-10"       # Thursday -> next Monday
    assert dw.h10_release("2026-11-02") == "2026-11-09"       # Monday -> the following Monday
    assert dw.h10_release("2026-10-30") == "2026-11-02"       # Friday -> next Monday


# ---------------------------------------------------------------------------- provenance of the reference
def test_reference_rebuilds_byte_identical(tmp_path):
    out = tmp_path / "ref.json"
    subprocess.run([sys.executable, "-I", os.path.join(STUDY, "code", "build_reference.py"), os.path.join(STUDY, "data"), str(out)],
                   check=True, capture_output=True, cwd=ROOT)
    assert out.read_bytes() == open(REF_FILE, "rb").read()


def test_reference_numbers_the_memo_cites():
    ref = dw.REF
    bl = ref["band"]["by_list"]
    assert bl["A25"]["n_excursions"] == 17
    assert [(bl[k]["hits_12m"], bl[k]["hits_24m"]) for k in ("A25", "C16", "N5")] == [(8, 12), (4, 8), (1, 3)]
    assert [(bl[k]["base_12m"], bl[k]["base_24m"]) for k in ("A25", "C16", "N5")] == [(0.421, 0.693), (0.283, 0.536), (0.091, 0.186)]
    q = ref["quadrant"]
    assert q["by_list"]["C16"]["counts"] == {"usd_up_yld_down": 9, "usd_up_yld_up": 2, "usd_down_yld_up": 3, "usd_down_yld_down": 2}
    assert q["base_all_months"]["shares"] == {"usd_down_yld_down": 0.264, "usd_down_yld_up": 0.234, "usd_up_yld_down": 0.216, "usd_up_yld_up": 0.285}
    g = ref["gold"]
    assert (g["ended_higher"], g["n_with_end"], g["ended_higher_gt_1pct"], g["base_share"]) == (14, 24, 12, 0.61)
    assert g["open_episodes"][0]["id"] == "C26"
    assert [(d["episode"], d.get("intraday_pct"), d.get("close_pct")) for d in g["drawdowns"][:3]] == \
           [("GFC 2008", -32.9, -29.7), ("COVID 2020", -14.7, -11.8), ("2022", -22.0, -20.1)]
    f = ref["dollar_fell_at_peak_stress"]
    assert (f["fell"], f["n_crises"], f["base_share"]) == (9, 24, 0.5) and f["open_episodes"][0]["id"] == "C26"
    mo = ref["momentum"]
    assert (len(mo["episodes"]), mo["episodes_began_in_a25_crisis"]) == (11, 8)
    assert [(mo["by_list"][k]["episodes_followed_12m"], mo["by_list"][k]["signal_months_followed_12m"]) for k in ("A25", "C16", "N5")] == [(5, 37), (5, 41), (1, 19)]
    fire = {x["date"]: x for x in ref["scramble_rule"]["firings"]}
    assert fire["2022-07-28"]["dollar_further_rise_pct"] == 5.2 and fire["2008-09-22"]["dollar_further_rise_pct"] == 17.7
    vs = ref["scramble_rule"]["vspike_timing"][0]
    assert (vs["climb_peak"], vs["climb_peak_pct"], vs["index_days_climb_to_dollar_peak"]) == ("2008-10-27", 12.9, 84)
    mn = ref["scramble_rule"]["monthly_null"]
    assert (mn["firings"], mn["dollar_peak_within_3m"], mn["spx_up_12m"]) == (10, 3, 6)
    rd = ref["redollarisation"]
    assert (rd["corr_yoy_contemporaneous"], rd["corr_yoy_dollar_leads_1q"], rd["corr_qoq_contemporaneous"], rd["corr_qoq_dollar_leads_1q"]) == (-0.5, -0.55, -0.36, -0.29)
    assert (rd["quarters"], rd["quarters_credit_growing"], rd["n_down"], rd["n_up"]) == (102, 93, 50, 52)
    assert all(r["label"] for r in ref["funding_leadlag"]["rows"]) and "calendar days" in ref["funding_leadlag"]["basis"].lower()


def test_emfx_outcomes_restored_after_the_freeze(payload):
    """withheld while a cross-section of these currencies was a candidate test; the freeze (forward_only) withdrew it."""
    fire = {x["date"]: x for x in dw.REF["scramble_rule"]["firings"]}
    assert fire["2008-11-06"]["outcomes"]["12m"]["emfx_pct"] == -8.7
    assert all("emfx_pct" in (r["outcomes"]["12m"] or {}) for r in dw.REF["momentum_ledger"] if r["outcomes"]["12m"])
    assert "emfx_withheld" not in payload["ledger"] and not any("withheld" in h for h in payload["honesty"])


# ---------------------------------------------------------------------------- live payload on the fixture
def test_payload_ok_and_serialisable(payload):
    json.dumps(payload)
    assert payload["mode"] == "descriptive"
    assert payload["status"]["overall"] == "ok", payload["status"]
    for b in ("state", "funding", "scramble", "slow", "ledger"):
        assert payload[b]["status"] in ("ok", "stale", "error")
    assert payload["scramble"]["live_check"]["reproduces_frozen_rearm"] is True
    assert payload["scramble"]["live_check"]["reproduces_frozen_unpatched"] is True
    assert {h["variant"] for h in payload["scramble"]["history"]} == {"both", "re-arm only"}
    pq = payload["pending_questions"]
    assert len(pq) == 10 and all(q["expires"] == "2027-01-01" for q in pq if q["status"] == "asked")
    assert [q["status"] for q in pq].count("answered") == 5 and [q["status"] for q in pq].count("asked") == 3
    assert [q["status"] for q in pq].count("open") == 2 and all(q["expires"] is None for q in pq if q["status"] != "asked")


def test_payload_values_on_the_fixture(payload, inputs):
    st = payload["state"]
    assert st["dxy"]["latest"] == 101.72 and st["dxy"]["asof"] == "2026-11-02"
    assert st["dxy"]["band_position"] == "inside Johnson's ad hoc 85-105 band (no edge found)"
    assert st["dxy"]["monthly"]["splice_check"]["ok"] and st["dxy"]["monthly"]["gaps"] == []
    assert st["broad"]["broad"]["latest"] == 121.32
    rows = {r["id"]: r for r in payload["funding"]["rows"]}
    f = inputs["fred"]
    cpf = dict(zip(f["DCPF3M"]["dates"], f["DCPF3M"]["values"]))
    tb = dict(zip(f["DTB3"]["dates"], f["DTB3"]["values"]))
    last = max(d for d in cpf if cpf[d] is not None and tb.get(d) is not None)
    assert rows["cp_fin"]["latest"] == round(cpf[last] - tb[last], 2) and rows["cp_fin"]["asof"] == last
    assert rows["swap_lines"]["unit"] == "$bn" and rows["swap_lines"]["latest"] == 0.16 and rows["swap_lines"]["history_from"] == "2007-12-12"
    assert rows["emb"]["pct_own_history"] is None and rows["emb"]["n_10y"] is None
    sc = payload["scramble"]
    assert sc["state"]["gate_open"] is False and sc["indicators"] is None and sc["confirmations"] is None
    uc = payload["slow"]["usd_credit"]
    assert (uc["quarter"], uc["total_tn"], uc["yoy_pct"]) == ("2026-Q2", 15.133, 8.1)
    assert uc["label"].startswith("re-dollarising") and "93 of 102" in uc["label"]
    assert payload["slow"]["fx_swaps"]["all_tn"] == 129.3 and payload["slow"]["fx_swaps"]["usd_leg_tn"] == 113.5
    q = st["quadrant"]
    assert q["month"] == "2026-10" and q["quadrant"] == "usd_up_yld_up"
    assert "no better than gold's own drift" in st["safe_haven"]["note"] and "No edge on any list" in st["band"]["note"]


def test_percentiles_are_tie_safe():
    a = [("2026-01-0%d" % i, v) for i, v in enumerate([4.05, 4.10, 4.20, 4.30, 4.40], start=1)]
    b = [("2026-01-0%d" % i, v) for i, v in enumerate([4.00, 4.05, 4.15, 4.25, 4.35], start=1)]
    s = dw.spread(a, b)
    assert [v for _, v in s] == [0.05] * 5                     # 4.05-4.00 and 4.10-4.05 tie exactly
    hist = [(f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", 0.05 if i % 2 else 0.10) for i in range(40)] + [("2026-02-01", round(4.05 - 4.00, 6))]
    p, n, _ = dw.pct_rank(hist)
    assert n == 41 and p == round(100 * 21 / 41)                  # at or below: the 20 tied 0.05s + today


def test_monthly_changes_use_calendar_keys_and_flag_gaps(inputs, tmp_path):
    """a live window that no longer reaches the frozen series must not produce 13-month 'changes' or ledger rows."""
    shifted = json.loads(json.dumps(inputs))
    dx = shifted["dxy"]
    keep = [i for i, d in enumerate(dx["dates"]) if d >= "2025-11-01"]
    dx["dates"] = [f"{int(dx['dates'][i][:4]) + 2}{dx['dates'][i][4:]}" for i in keep]     # 2025-11.. -> 2027-11..: 2026-11..2027-10 missing
    dx["values"] = [None if dx["values"][i] is None else dx["values"][i] * (1.3 if dx["dates"][j][:7] <= "2028-03" else 1.0)
                    for j, i in enumerate(keep)]
    path = str(tmp_path / "l.json")
    p = dw.build_dollar_watch(shifted, today="2028-11-02", ledger_file=path)
    st = p["state"]
    assert st["dxy"]["monthly"]["gaps"][:2] == ["2026-11", "2026-12"]
    assert st["status"] == "error" and st["momentum"]["signal"] is None and st["issues"]
    assert all(m <= dw.LAST_FROZEN_MONTH or m >= "2028-11" for m in st["momentum"]["signal_months"])   # no 12m change spans the hole
    assert [e for e in p["ledger"]["live"] if e["kind"] == "momentum"] == []


def test_nulls_never_zero(tmp_path):
    p = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "l.json"))
    assert p["state"]["dxy"]["latest"] is None and p["state"]["broad"]["broad"]["latest"] is None
    assert all(r["latest"] is None for r in p["funding"]["rows"])
    assert p["scramble"]["state"] is None and p["slow"]["us2y_vs_funds"]["reading"] is None


def test_all_null_payload_ships_every_block_and_the_frozen_record(tmp_path):
    p = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "l.json"))
    json.dumps(p)
    assert p["status"]["overall"] == "error"
    for b in ("state", "funding", "scramble", "slow"):
        assert p[b]["status"] == "error"
    assert len(p["scramble"]["history"]) == 7 and p["scramble"]["monthly_null"]["firings"] == 10
    assert p["state"]["band"]["excursions"] and p["state"]["counter_examples"]
    assert "unavailable" in p["headline"]


def test_partial_data_never_crashes(inputs, tmp_path):
    part = json.loads(json.dumps(inputs))
    part["bis"]["gli_total"]["series"]["_"] = [x for x in part["bis"]["gli_total"]["series"]["_"] if x[0] != "2025-Q2"]   # yoy missing
    part["bis"]["gli_total"]["series"]["_"].append(["2026Q3", 1.0])                                                       # format drift
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"entries": [{"kind": "scramble_rule"}]}))                                                   # a row with no date
    p = dw.build_dollar_watch(part, today="2026-11-02", ledger_file=str(bad))
    assert p["slow"]["usd_credit"]["yoy_pct"] is None and p["slow"]["usd_credit"]["quarter"] == "2026-Q2"
    assert p["ledger"]["status"] == "error" and json.loads(bad.read_text()) == {"entries": [{"kind": "scramble_rule"}]}
    assert p["headline"].endswith("(2026-Q2).")


def test_policy_rates_compare_the_same_month():
    bis = {"cbpol": {"status": "ok", "series": {"US": [("2026-06", 4.375), ("2026-09", 3.875)], "BR": [("2026-06", 14.0)]}}}
    rows = {x["area"]: x for x in dw.slow_block({"bis": bis})["policy_rates"]["rows"]}
    assert rows["BR"]["vs_fed_pp"] == round(14.0 - 4.375, 2)


def test_fetch_all_never_raises_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(fred_csv.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(fred_csv, "_fetch_text", lambda *a, **k: None)
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda *a, **k: None)
    monkeypatch.setattr(dollar_data.fmp, "fetch_gold", lambda *a, **k: ([], []))
    inp = dollar_data.fetch_all()
    assert all(s["status"] == "error" for s in inp["fred"].values())
    assert inp["dxy"]["status"] == "error" and inp["ofr"]["status"] == "error"
    p = dw.build_dollar_watch(inp, today="2026-11-02", ledger_file=str(tmp_path / "l.json"))
    assert p["status"]["overall"] == "error"


def test_parsers():
    ofr = dollar_data.parse_ofr_columns(b"\xef\xbb\xbfDate,OFR FSI,Credit,Safe assets,Funding,Emerging markets\n"
                                        b"2026-10-28,-1.2,0.1,-0.3,-0.15,-0.5\n2026-10-29,-1.1,,-0.29,-0.151,-0.499\n")
    assert ofr["dates"] == ["2026-10-28", "2026-10-29"] and ofr["Funding"] == [-0.15, -0.151] and ofr["Credit"] == [0.1, None]
    assert ofr["Volatility"] == [None, None]
    with pytest.raises(ValueError):
        dollar_data.parse_ofr_columns(b"<html>maintenance</html>")
    bis = dollar_data.parse_bis_csv(b"FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,US,2026-09,3.875\nM,US,2026-08,3.625\nM,XM,2026-09,\n", "REF_AREA")
    assert bis["US"] == [("2026-08", 3.625), ("2026-09", 3.875)] and bis["XM"] == [("2026-09", None)]
    with pytest.raises(ValueError):
        dollar_data.parse_bis_csv(b"<html/>")
    assert dw._q_end("2026-Q2") == "2026-06" and dw._q_end("2026Q2") is None


def _meta(t, start, end):
    return json.dumps({"chart": {"result": [{"meta": {"regularMarketTime": t, "currentTradingPeriod": {"regular": {"start": start, "end": end}}}}]}}).encode()


def test_yahoo_intraday_flag():
    S = 1793595600                                     # 2026-11-02 00:00 ET: the DXY's Yahoo session runs midnight to midnight
    assert dollar_data.yahoo_intraday(_meta(S + 15 * 3600, S, S + 86340), settle_hours=17) is True     # 15:00 ET, before settlement
    assert dollar_data.yahoo_intraday(_meta(S + 20 * 3600, S, S + 86340), settle_hours=17) is False    # 20:00 ET, after the 17:00 settle
    O = S + 9 * 3600 + 1800                            # EMB: 09:30-16:00 ET
    assert dollar_data.yahoo_intraday(_meta(O - 3600, O, O + 23400)) is False    # pre-open: the last bar is yesterday's close
    assert dollar_data.yahoo_intraday(_meta(O + 3600, O, O + 23400)) is True     # in session
    assert dollar_data.yahoo_intraday(_meta(O + 23400, O, O + 23400)) is False   # at the close


# ---------------------------------------------------------------------------- the gauge with the gate open
def test_indicators_only_with_gate_open_never_summed(inputs, tmp_path):
    p = dw.build_dollar_watch(_cut(inputs, "2008-11-06"), today="2008-11-06", ledger_file=str(tmp_path / "l.json"))
    sc = p["scramble"]
    assert sc["state"]["asof"] == "2008-11-06" and sc["gate_open"] is True
    assert sc["fires_today"]["re-arm"] is True and sc["fires_today"]["unpatched"] is False
    ind = sc["indicators"]
    assert set(ind) == {"a_deceleration", "b_funding_easing", "c_risk_turn", "note"}
    assert ind["a_deceleration"]["met"] is True
    assert ind["b_funding_easing"]["met"] is None                 # its inputs are missing on this cut: unknown, not "not met"
    for k in ("score", "total", "sum", "count_met", "composite"):
        assert k not in ind and k not in sc
    assert sc["confirmations"]["episode_start"] <= sc["state"]["roc20_max_date"]
    assert sc["wording"] == "dollar scramble peaking"


# ---------------------------------------------------------------------------- the forward ledger
def test_ledger_append_only_forward_only(tmp_path):
    path = str(tmp_path / "ledger.json")
    e1 = {"kind": "scramble_rule", "date": "2027-03-01", "variants": ["re-arm"]}
    led = dw.append_ledger(path, [e1], "2027-03-08")
    assert led["entries"] == [dict(e1, recorded_on="2027-03-08")]
    dw.append_ledger(path, [dict(e1, variants=["re-arm", "unpatched"])], "2027-03-15")
    assert dw.load_ledger(path)["entries"] == [dict(e1, recorded_on="2027-03-08")]
    dw.append_ledger(path, [{"kind": "momentum", "date": "2027-05", "dxy_12m_pct": 10.4}], "2027-06-02")
    assert [e["kind"] for e in dw.load_ledger(path)["entries"]] == ["scramble_rule", "momentum"]
    for junk in ("{not json", json.dumps({"entries": "x"}), json.dumps([1, 2])):
        bad = tmp_path / "bad.json"
        bad.write_text(junk)
        assert dw.append_ledger(str(bad), [e1], "2027-03-08").get("_unreadable")
        assert bad.read_text() == junk                            # never overwritten


def test_outcomes_freeze_once_at_maturity(tmp_path):
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2027-03-01", "variants": ["unpatched"]}], "2027-03-08")
    calls = {"v": 1.0}

    def compute(e, last):
        return {"3m": {"spx_pct": calls["v"]}, "6m": None, "12m": None}

    dw.freeze_matured(path, compute, "2027-07-01", "2027-07-01")
    calls["v"] = 99.0                                             # a later data revision
    dw.freeze_matured(path, compute, "2027-07-02", "2027-07-02")
    e = dw.load_ledger(path)["entries"][0]
    assert e["outcomes_frozen"] == {"3m": {"spx_pct": 1.0, "frozen_on": "2027-07-01"}}


def test_freeze_skips_incomplete_horizons(tmp_path):
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2027-03-01", "variants": ["unpatched"]}], "2027-03-08")
    dw.freeze_matured(path, lambda e, last: {"3m": {"spx_pct": 1.0, "baa10y_pp": None}, "6m": None, "12m": None}, "2027-07-01", "2027-07-01")
    assert dw.load_ledger(path)["entries"][0].get("outcomes_frozen", {}) == {}  # a missing component is retried, not frozen
    dw.freeze_matured(path, lambda e, last: {"3m": {"spx_pct": 1.0, "baa10y_pp": 0.1}, "6m": None, "12m": None}, "2027-07-02", "2027-07-02")
    assert dw.load_ledger(path)["entries"][0]["outcomes_frozen"]["3m"]["frozen_on"] == "2027-07-02"


def test_late_recorded_rows_anchor_at_recording(inputs, tmp_path):
    """a firing first seen after an outage is scored from the first close after the panel recorded it."""
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2025-03-03", "variants": ["unpatched"], "h10_release": "2025-03-10"}], "2025-06-02")
    p = dw.build_dollar_watch(inputs, today="2026-11-02", ledger_file=path)
    row = p["ledger"]["live"][0]
    assert row["anchor_close"] > "2025-06-02"
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2025-04-01", "variants": ["unpatched"], "h10_release": "2025-04-07"}], "2025-04-07")
    p = dw.build_dollar_watch(inputs, today="2026-11-02", ledger_file=path)
    on_time = [r for r in p["ledger"]["live"] if r["date"] == "2025-04-01"][0]
    assert on_time["anchor_close"] == "2025-04-08"


def test_failed_ledger_write_is_reported(inputs, tmp_path, monkeypatch):
    shifted = _cut(inputs, "2008-11-06")
    for s in list(shifted["fred"].values()):
        s["dates"] = [f"{int(d[:4]) + 20}{d[4:]}" for d in s["dates"]]
    from app.sources import fred_csv as fc

    def boom(*a, **k):
        raise OSError("No space left on device")
    monkeypatch.setattr(fc, "_write_atomic", boom)
    p = dw.build_dollar_watch(shifted, today="2028-11-06", ledger_file=str(tmp_path / "l.json"))
    assert p["ledger"]["status"] == "error" and "No space left" in (p["ledger"]["problem"] or "") + str(p["scramble"]["ledger_status"])
    assert p["status"]["overall"] == "error"


def test_gold_note_requires_quiet_funding(payload, inputs, tmp_path):
    g = payload["state"]["safe_haven"]["gold"]
    cp = {r["id"]: r for r in payload["funding"]["rows"]}["cp_fin"]
    assert g["off_52w_high_pct"] <= -15 and g["note"] == (f"with dollar funding quiet (financial CP minus bill at its {dw._ord(cp['pct_own_history'])} "
                                                           "percentile): outside the crisis pattern below")
    stressed = json.loads(json.dumps(inputs))
    stressed["fred"]["DCPF3M"]["values"][-1] = (stressed["fred"]["DTB3"]["values"][-1] or 4.0) + 3.05     # CP-bill at a Lehman-sized print
    p = dw.build_dollar_watch(stressed, today="2026-11-02", ledger_file=str(tmp_path / "s.json"))
    assert p["state"]["safe_haven"]["gold"]["note"] is None


def test_frozen_history_never_enters_the_live_ledger(payload, tmp_path):
    assert payload["ledger"]["live"] == [] and payload["scramble"]["live_firings"] == []
    assert not os.path.exists(tmp_path / "ledger.json")


def test_live_firing_after_cutoff_is_recorded_once_point_in_time(inputs, tmp_path):
    """replay the 2008 shape in 2028: the rule fires, the ledger records it once, stamped with its H.10 release."""
    shifted = _cut(inputs, "2008-11-06")
    for s in list(shifted["fred"].values()):
        s["dates"] = [f"{int(d[:4]) + 20}{d[4:]}" for d in s["dates"]]       # 2008 -> 2028 (leap years line up)
    path = str(tmp_path / "ledger.json")
    p1 = dw.build_dollar_watch(shifted, today="2028-11-06", ledger_file=path)
    live = [e for e in p1["scramble"]["live_firings"] if e["kind"] == "scramble_rule"]
    assert [e["date"] for e in live] == ["2028-09-22", "2028-11-06"]
    assert live[1]["variants"] == ["re-arm"] and live[0]["variants"] == ["re-arm", "unpatched"]
    assert [e["h10_release"] for e in live] == ["2028-09-25", "2028-11-13"]
    assert all(e["recorded_on"] == "2028-11-06" for e in live)
    p2 = dw.build_dollar_watch(shifted, today="2028-11-07", ledger_file=path)
    assert len([e for e in p2["scramble"]["live_firings"] if e["kind"] == "scramble_rule"]) == 2


def test_failed_build_is_served_stale_not_ok(monkeypatch):
    from app.api import routes_dollar as rd
    good = {"status": {"overall": "ok", "blocks": {}}, "headline": "x"}
    monkeypatch.setitem(rd._cache, "data", good)
    monkeypatch.setattr(rd, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    out = rd._rebuild()
    assert out["status"]["overall"] == "stale" and "boom" in out["build_error"] and good["status"]["overall"] == "ok"


def test_broken_reference_fails_the_route_not_the_app(monkeypatch):
    monkeypatch.setattr(dw, "REF_ERROR", "JSONDecodeError: x")
    with pytest.raises(RuntimeError):
        dw.build_dollar_watch({}, today="2026-11-02", ledger_file="/nonexistent/l.json")


# ---------------------------------------------------------------------------- language
def test_forbidden_language_absent(payload, tmp_path):
    null = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "n.json"))
    text = " ".join(list(_strings(payload)) + list(_strings(null))).lower()
    for phrase in FORBIDDEN:
        assert phrase not in text, phrase
    for path in TAB_SOURCES:
        src = open(path, encoding="utf-8").read().lower()
        for phrase in FORBIDDEN:
            assert phrase not in src, (os.path.basename(path), phrase)


# ============================================================================ the frozen pre-registration (SPEC v1)
SPEC_DIR = os.path.join(STUDY, "spec")


def test_freeze_record_shipped_and_rule_matches():
    assert open(os.path.join(ROOT, "backend", "app", "sources", "dollar_freeze.json"), "rb").read() == \
        open(os.path.join(SPEC_DIR, "freeze.json"), "rb").read()
    fz = dw.FREEZE
    assert fz["route"] == "forward_only" and fz["decel_primary_variant"] == "unpatched" and fz["primary_crisis_list"].startswith("C16")
    assert fz["forward_onset_rule"] == "mechanical_2_of_5" and fz["answered_by"] == "Casey"
    for k, v in fz["rule_params"].items():
        if k in dw.RULE_FROZEN and k != "index":
            assert dw.RULE_FROZEN[k] == v, k


def test_fed_actions_list_is_valid_and_frozen():
    import hashlib
    shipped = os.path.join(ROOT, "backend", "app", "sources", "dollar_fed_actions.json")
    body = open(shipped, "rb").read()
    assert body == open(os.path.join(SPEC_DIR, "fed_emergency_actions.json"), "rb").read()
    acts = dw.FED["actions"]
    assert len(acts) == dw.FED["n"] and [a["date"] for a in acts] == sorted(a["date"] for a in acts)
    assert all(a["url"].startswith("https://www.federalreserve.gov/") for a in acts)
    assert hashlib.sha256(body).hexdigest() == dw.FREEZE["fed_emergency_actions_sha256"]


def test_h10_release_moves_off_federal_holidays():
    assert dw.h10_release("2026-09-02") == "2026-09-08"      # Labor Day Monday 2026-09-07
    assert dw.h10_release("2027-01-14") == "2027-01-19"      # MLK Day Monday 2027-01-18
    assert dw.h10_release("2028-11-06") == "2028-11-13"
    assert "2026-11-26" in dw.us_federal_holidays(2026) and "2027-07-05" in dw.us_federal_holidays(2027)   # Thanksgiving; observed July 4


def test_onset_markers_on_2020(inputs):
    trip = dw.onset_markers(inputs, ["2020-03"])["2020-03"]
    assert {"1_vix", "4_spx", "5_fed"} <= set(trip) and len(trip) >= 4


def _shift(inputs, years: int, cut: str | None = None):
    out = json.loads(json.dumps(inputs))
    for s in list(out["fred"].values()) + [out["dxy"], out["gold"], out["emb"]]:
        keep = [i for i, d in enumerate(s["dates"]) if cut is None or d <= cut]
        s["dates"] = [f"{int(s['dates'][i][:4]) + years}{s['dates'][i][4:]}" for i in keep]
        s["values"] = [s["values"][i] for i in keep]
    o = out["ofr"]
    keep = [i for i, d in enumerate(o["dates"]) if cut is None or d <= cut]
    for c in [k for k in o if isinstance(o[k], list) and len(o[k]) == len(o["dates"])]:
        o[c] = [o[c][i] for i in keep]
    o["dates"] = [f"{int(d[:4]) + years}{d[4:]}" for d in o["dates"]]
    return out


def test_live_onset_recorded_once_with_frozen_subtype(inputs, tmp_path):
    """the 2020 shock replayed in 2028 (leap years line up): an onset row is appended once, its subtype frozen after m+2."""
    shifted = _shift(inputs, 8, cut="2020-12-31")
    path = str(tmp_path / "ledger.json")
    p = dw.build_dollar_watch(shifted, today="2028-07-01", ledger_file=path)
    on = [e for e in dw.load_ledger(path)["entries"] if e["kind"] == "onset"]
    assert [e["date"] for e in on] == ["2028-03"]
    assert {"1_vix", "4_spx"} <= set(on[0]["markers"]) and "5_fed" not in on[0]["markers"]      # Fed list dates are not shifted
    assert on[0]["subtype"]["dollar_funding"] is True and on[0]["recorded_on"] == "2028-07-01"
    dw.build_dollar_watch(shifted, today="2028-07-02", ledger_file=path)
    assert len([e for e in dw.load_ledger(path)["entries"] if e["kind"] == "onset"]) == 1
    assert p["forward"]["onsets"]["live"][0]["date"] == "2028-03" and p["forward"]["status"] == "ok"


def test_firing_rows_carry_the_point_in_time_record(inputs, tmp_path):
    first = _shift(inputs, 20, cut="2008-09-30")          # first vintage: through 2008-09-30 -> 2028-09-29
    path = str(tmp_path / "ledger.json")
    dw.build_dollar_watch(first, today="2028-10-01", ledger_file=path)
    second = _shift(inputs, 20, cut="2008-11-06")
    dw.build_dollar_watch(second, today="2028-11-07", ledger_file=path)
    rows = {e["date"]: e for e in dw.load_ledger(path)["entries"] if e["kind"] == "scramble_rule"}
    a, b = rows["2028-09-22"], rows["2028-11-06"]
    assert a["first_vintage_contains_date"] is None                       # nothing seen before the first build
    assert b["first_vintage_contains_date"] is True                       # 2028-11-06 > the last day of the first vintage
    assert a["unit_first"] == "2028-09-22" and b["unit_first"] is None    # re-arm-only rows are never units
    assert a["h10_release"] == "2028-09-25" and b["h10_release"] == "2028-11-13"
    for e in (a, b):
        assert isinstance(e["k"], int) and e["y10_now"] < e["y10_ref"] and 0.97 <= e["near_high_ratio"] <= 1.0
        assert set(e["inputs"]) == {"DTWEXBGS", "DGS10", "VIXCLS"}
    assert a["revision_checks"][0]["still_fires"] == {"re-arm": True, "unpatched": True}


def test_units_merge_within_250_index_days(tmp_path):
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2030-01-10", "variants": ["unpatched"], "k": 100,
                             "unit_first": "2030-01-10", "index_gap_to_unit_first": 0}], "2030-01-20")
    ds = [f"2030-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(330)]
    B = [100.0 + 0.01 * i for i in range(330)]
    Y = [3.0] * 330
    new = {ds[300]: {"kind": "scramble_rule", "date": ds[300], "variants": ["unpatched"], "roc20_max_date": ds[290],
                     "roc20_max_pct": 4.5, "roc20_now_pct": 1.0, "dollar": B[300]}}
    rows = dw.enrich_firings(new, ds, B, Y, path, None)
    assert rows[0]["unit_first"] == "2030-01-10" and rows[0]["index_gap_to_unit_first"] == 200


def test_revision_checks_append_never_delete(tmp_path):
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2030-02-01", "variants": ["unpatched"]}], "2030-02-10")
    dw.revision_checks(path, set(), {"2030-02-01"}, "2030-02-10")
    dw.revision_checks(path, set(), {"2030-02-01"}, "2030-02-17")       # unchanged: no new entry
    dw.revision_checks(path, set(), set(), "2030-03-01")                # a revision removes the firing
    e = dw.load_ledger(path)["entries"][0]
    assert [c["still_fires"]["unpatched"] for c in e["revision_checks"]] == [True, False] and e["date"] == "2030-02-01"


def test_maturity_block_written_once(inputs, tmp_path):
    ds, B, _ = dw.rule_index(inputs["fred"])
    path = str(tmp_path / "ledger.json")
    d = "2020-04-09"                                                      # an in-sample firing with 250 index days after it
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": d, "variants": ["unpatched"]}], "2020-04-20")
    dw._write_once(path, "scramble_rule", "outcomes_250d", lambda e: dw.maturity_250d(e, ds, B, inputs, path), "2026-11-02")
    blk = dw.load_ledger(path)["entries"][0]["outcomes_250d"]
    frozen = {x["date"]: x for x in dw.REF["scramble_rule"]["firings"]}[d]
    assert blk["further_rise_pct"] == pytest.approx(frozen["dollar_further_rise_pct"], abs=0.06) and blk["hit"] is True
    assert blk["max_date"] == frozen["dollar_peak_date"] and blk["frozen_on"] == "2026-11-02"
    dw._write_once(path, "scramble_rule", "outcomes_250d", lambda e: {"hit": False}, "2026-11-03")
    assert dw.load_ledger(path)["entries"][0]["outcomes_250d"]["hit"] is True        # never rewritten


def test_momentum_rows_mature_with_the_onset_record(tmp_path):
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "momentum", "date": "2027-01", "dxy_12m_pct": 10.5},
                            {"kind": "onset", "date": "2027-06", "markers": {}, "subtype": {"dollar_funding": True}}], "2027-02-03")
    dw.mature_momentum({"fred": {}}, path, "2028-01-15")                  # m+12 = 2028-01 has not closed
    assert "onset_within_12m" not in dw.load_ledger(path)["entries"][0]
    dw.mature_momentum({"fred": {}}, path, "2028-02-02")
    got = dw.load_ledger(path)["entries"][0]["onset_within_12m"]
    assert got["onsets"] == ["2027-06"] and got["dollar_funding"] == ["2027-06"]
