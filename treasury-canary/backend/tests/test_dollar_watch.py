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
  - EM FX outcomes are shown (forward_only withdrew the test they could steer); forbidden language never appears;
  - the frozen pre-registration (SPEC v1): eligibility after the freeze date, units from the first firing, the
    placebo, one onset row per month at its close, revisions logged never re-dated, the Fed list and SPEC hashes;
  - the all-null payload ships every block plus the frozen record; nothing crashes on partial data;
  - the plain-language summaries cover every layer, restate the panel's own numbers, judge funding on the frozen
    SPEC v1 §5.3 lines, and degrade by dropping a sentence, never by printing a hole.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, timedelta

import pytest

from app.metrics import dollar_watch as dw
from app.sources import dollar_data, fred_csv

HERE = os.path.dirname(__file__)
FX = os.path.join(HERE, "fixtures", "dollar_watch", "inputs_2026-11-02.json.gz")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))            # treasury-canary/
STUDY = os.path.join(ROOT, "studies", "dollar_watch")
REF_FILE = os.path.join(ROOT, "backend", "app", "sources", "dollar_reference.json")
TAB_SOURCES = [os.path.join(ROOT, "frontend", "src", "components", "DollarTab.tsx"),
               os.path.join(ROOT, "frontend", "src", "lib", "dollarFixture.ts"),
               os.path.join(ROOT, "frontend", "src", "lib", "dollarGlossary.ts")]

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


def test_rule_calendar_drops_vix_with_identical_firings(inputs):
    """SPEC v1 §2 (stats review v1 S3): the live rule and D-3 run on DTWEXBGS & DGS10; the frozen script's calendar also
    required VIXCLS. The two give identical firings, both variants, on the whole record."""
    ds, B, Y = dw.rule_index(inputs["fred"])
    have = {s: set(inputs["fred"][s]["dates"][i] for i, v in enumerate(inputs["fred"][s]["values"]) if v is not None)
            for s in ("DTWEXBGS", "DGS10", "VIXCLS")}
    assert set(ds) == have["DTWEXBGS"] & have["DGS10"]
    old = sorted(have["DTWEXBGS"] & have["DGS10"] & have["VIXCLS"])
    b, y = dict(dw.pairs(inputs["fred"]["DTWEXBGS"])), dict(dw.pairs(inputs["fred"]["DGS10"]))
    Bo, Yo = [b[d] for d in old], [y[d] for d in old]
    assert 0 < len(ds) - len(old) <= 10                                    # Good Fridays only
    for rearm in (True, False):
        assert [f["date"] for f in dw.scramble_firings(ds, B, Y, rearm)] == [f["date"] for f in dw.scramble_firings(old, Bo, Yo, rearm)]


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
    assert len(pq) == 11 and pq[0]["rank"] == "P1"
    asked = [q for q in pq if q["status"] == "asked"]
    assert {q["first_asked"]: q["expires"] for q in asked} == {"2026-11-02": "2027-01-01"}                # 60 days from the first ask
    assert [q["status"] for q in pq].count("answered") == 6 and len(asked) == 3
    q19 = [q for q in pq if q["rank"] == "P1" and "drift" in q["q"]][0]
    assert q19["status"] == "answered" and q19["answered_on"] == "2026-11-03" and "keep the default" in q19["answer"]
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


def test_freeze_is_field_by_field(tmp_path):
    """data review v1 M4: a missing component waits on its own; the others freeze, and nothing is ever rewritten."""
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2027-03-01", "variants": ["unpatched"]},
                            {"kind": "onset_month", "date": "2027-03", "onset": False}], "2027-03-08")
    dw.freeze_matured(path, lambda e, last: {"3m": {"spx_pct": 1.0, "emfx_pct": None}, "6m": None, "12m": None}, "2027-07-01", "2027-07-01")
    rows = dw.load_ledger(path)["entries"]
    assert rows[0]["outcomes_frozen"] == {"3m": {"spx_pct": 1.0, "frozen_on": "2027-07-01"}}
    assert "outcomes_frozen" not in rows[1]                                # bookkeeping rows are never scored
    dw.freeze_matured(path, lambda e, last: {"3m": {"spx_pct": 5.0, "emfx_pct": -2.0}, "6m": None, "12m": None}, "2027-07-02", "2027-07-02")
    got = dw.load_ledger(path)["entries"][0]["outcomes_frozen"]["3m"]
    assert got == {"spx_pct": 1.0, "emfx_pct": -2.0, "frozen_on": "2027-07-01", "late_fields": {"emfx_pct": "2027-07-02"}}


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


# ---------------------------------------------------------------------------- plain-language summaries (Casey, 2026-11-03)
SUMMARY_KEYS = ("state", "funding", "scramble", "slow", "ledger", "forward", "page")
HOLE = re.compile(r"\bNone\b(?! of\b)|\bnan\b|\binf\b|[{}]")          # a Python None/nan/inf or a stray f-string brace; "None of" is English


def _summary_lines(p):
    s = p.get("summaries") or {}
    assert set(SUMMARY_KEYS) <= set(s), set(SUMMARY_KEYS) - set(s)
    for k in SUMMARY_KEYS:
        assert isinstance(s[k], list) and s[k] and all(isinstance(x, str) and x.strip() for x in s[k]), k
    return [x for k in SUMMARY_KEYS for x in s[k]]


def test_summaries_cover_every_layer_restate_the_panel_and_never_print_a_hole(payload, inputs, tmp_path):
    lines = _summary_lines(payload)
    s, dx = payload["summaries"], payload["state"]["dxy"]
    assert f"{dx['latest']:.1f}" in s["state"][0] and dw._ord(dx["pct_own_history"]) + " percentile" in s["state"][0]
    cp = next(r for r in payload["funding"]["rows"] if r["id"] == "cp_fin")
    cpf = dw.spread(dw.pairs(inputs["fred"]["DCPF3M"]), dw.pairs(inputs["fred"]["DTB3"]))
    assert cp["mean_5d"] == dw.r(sum(v for _, v in cpf[-5:]) / 5, 2)          # SPEC v1 §5.3's line is on the 5-day mean
    assert f"{cp['latest']:.2f}pp" in s["funding"][0] and f"{cp['mean_5d']:.2f}pp" in s["funding"][1]
    assert f"{payload['scramble']['state']['roc20_max_60d_pct']:+.1f}%" in s["scramble"][0]
    assert s["page"][0].startswith("The dollar is ") and "not a forecast" in s["page"][1]
    null = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "n.json"))
    more = _summary_lines(null)
    assert null["summaries"]["page"][0].startswith("Live data unavailable")
    assert [x[:17] for x in null["summaries"]["funding"]] == ["What it tells you"]                       # no reading, no verdict
    # each source down in turn, and each series the summaries read: a sentence drops, nothing prints a hole
    for key in [k for k in inputs if not k.startswith("_")]:
        part = {k: v for k, v in inputs.items() if k != key}
        more += _summary_lines(dw.build_dollar_watch(part, today="2026-11-02", ledger_file=str(tmp_path / f"{key}.json")))
    for sid in ("DTWEXBGS", "DGS10", "DCPF3M", "DTB3", "SWPT", "WMTSECL1", "SOFR", "IORB"):
        part = {**inputs, "fred": {k: v for k, v in inputs["fred"].items() if k != sid}}
        more += _summary_lines(dw.build_dollar_watch(part, today="2026-11-02", ledger_file=str(tmp_path / f"{sid}.json")))
    for x in lines + more:
        assert not HOLE.search(x), x
        for phrase in FORBIDDEN:
            assert phrase not in x.lower(), (phrase, x)


def test_every_glossary_entry_is_wired_into_the_tab(payload):
    """Casey, 2026-11-03: a '?' on every indicator. Each dollarGlossary entry is used by the tab, directly or as a funding row's id."""
    gloss = open(TAB_SOURCES[2], encoding="utf-8").read()
    tab = open(TAB_SOURCES[0], encoding="utf-8").read()
    keys = re.findall(r"^  ([a-z0-9_]+): \{", gloss, re.M)
    row_ids = {r["id"] for r in payload["funding"]["rows"]}
    assert len(keys) >= 40 and row_ids <= set(keys), row_ids - set(keys)
    assert "DW[r.id]" in tab
    assert [k for k in keys if f"DW.{k}" not in tab and k not in row_ids] == []
    for k in re.findall(r"DW\.([a-z0-9_]+)", tab):
        assert k in keys, k


def test_summaries_judge_funding_on_the_frozen_subtype_lines():
    spec = open(os.path.join(STUDY, "spec", "SPEC_v1.md"), encoding="utf-8").read()
    assert "FRED SWPT > 50,000 ($m)" in spec and "trailing 5-observation mean of DCPF3M − DTB3" in spec and "> 1.00 on any day" in spec

    def rows(cp5, cp, sw, of):
        return {"cp_fin": {"latest": cp, "mean_5d": cp5, "median_1y": 0.2}, "swap_lines": {"latest": sw},
                "ofr_funding": {"latest": of, "median_1y": 0.0}}
    assert dw._funding_word(rows(1.01, 0.9, 0.1, -1)) == "strained"      # CP-bill 5-day mean past 1.00
    assert dw._funding_word(rows(1.00, 1.0, 0.1, -1)) == "firmer"        # at the line is not past it
    assert dw._funding_word(rows(0.1, 0.1, 50.01, -1)) == "strained"     # swap lines past $50bn
    assert dw._funding_word(rows(0.1, 0.1, 50.0, -1)) == "quiet"         # the gold note's test: both at or below their medians
    assert dw._funding_word(rows(0.1, 0.1, 0.1, 0.5)) == "firmer"        # OFR funding above its 1-year median
    assert dw._funding_word(rows(0.1, 0.1, 0.1, None)) is None           # not enough data to say
    row = lambda i, v, p, **k: {"id": i, "label": i, "latest": v, "pct_own_history": p, "history_from": "2019-01-02", **k}   # noqa: E731
    hot = dw.summaries({}, {"rows": [row("cp_fin", 1.3, 99, mean_5d=1.2, median_1y=0.2), row("swap_lines", 0.1, 10)]}, {}, {}, {}, {})
    assert hot["funding"][0].startswith("Dollar funding is under strain") and hot["funding"][1].endswith("past a line.")
    assert "dollar funding is under strain" in hot["page"][0].lower()


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
    assert all(a["url"].startswith("https://www.federalreserve.gov/") and a["verified"]["http_status"] == 200 for a in acts)
    assert hashlib.sha256(body).hexdigest() == dw.FED_SHA
    # the list grows append-only from the copy frozen with the SPEC (the monthly upkeep appends; nothing else changes)
    frozen_body = open(os.path.join(SPEC_DIR, "fed_emergency_actions_at_freeze.json"), "rb").read()
    assert hashlib.sha256(frozen_body).hexdigest() == dw.FREEZE["fed_emergency_actions_sha256"]
    frozen = json.loads(frozen_body)
    key = lambda a: json.dumps(a, sort_keys=True)                         # noqa: E731
    assert all(key(a) in {key(x) for x in acts} for a in frozen["actions"])
    assert [key(a) for a in acts if key(a) in {key(x) for x in frozen["actions"]}] == [key(a) for a in frozen["actions"]]
    assert all(a.get("added_on", "") > dw.FREEZE["freeze_date"] for a in acts if key(a) not in {key(x) for x in frozen["actions"]})
    assert all(key(x) in {key(y) for y in dw.FED["excluded_candidates"]} for x in frozen["excluded_candidates"])
    assert dw.FED["reviewed_through"] >= frozen["reviewed_through"] and dw.FED["definition"] == frozen["definition"]
    assert dw.FED["onset_check_list_sha256"] == dw.FREEZE["onset_check"]["fed_list_sha256"]     # the list the count ran on
    added = [a for a in acts if a.get("added_on")]
    assert [a["date"] for a in added] == ["2008-10-08", "2009-03-02"] and all("recount is unchanged" in a["added_note"] for a in added)
    exc = dw.FED["excluded_candidates"]
    assert len(exc) >= 10 and all(x["url"].startswith("https://www.federalreserve.gov/") and x["clause"] for x in exc)
    assert not {x["url"] for x in exc} & {a["url"] for a in acts}
    assert len(dw.FED["reviewed_through"]) == 7 and any("Reverse" in x for x in dw.FED["definition"]["rulings"])


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


def _months(a: str, b: str) -> list[str]:
    out = [a]
    while out[-1] < b:
        out.append(dw.add_months(out[-1] + "-01", 1)[:7])
    return out


def test_onset_close_and_deadline():
    # 2026-11: the H.10 carrying Mon 11-30 comes out Mon 12-07 at 4:15pm ET, the same day as 11-30 + 5 business days, so the
    # close is the day after (data re-check S-1); a build at 00:05 UTC on 12-07 must not date the month
    assert dw.h10_release("2026-11-30") == "2026-12-07" and dw.onset_close("2026-11") == "2026-12-08"
    assert dw.onset_close("2026-12") == "2027-01-08"          # New Year's Day off: 5 business days after 12-31 = 01-08
    assert dw._covers([("2026-11-27", 1.0)], "2026-11") is False and dw._covers([("2026-11-30", 1.0)], "2026-11") is True
    assert dw._covers([("2026-11-25", 1.0)], "2026-11", weekly=True) is True       # SWPT: the month's last Wednesday
    assert dw.onset_deadline("2026-12") == "2027-01-31" and dw.onset_deadline("2027-01") == "2027-02-28"


def test_onset_months_evaluated_once_point_in_time(inputs, tmp_path, monkeypatch):
    """data review v1 S2: the 2020 shock replayed in 2028. Every month gets one row at its close (onset or not); the onset
    is dated once; its subtype freezes after m+2's close; a later revision is logged, never re-dates or adds an onset."""
    shifted = _shift(inputs, 8, cut="2020-12-31")
    path = str(tmp_path / "ledger.json")
    p = dw.build_dollar_watch(shifted, today="2028-07-01", ledger_file=path)
    rows = [e for e in dw.load_ledger(path)["entries"] if e["kind"] == "onset_month"]
    assert [e["date"] for e in rows] == _months("2026-11", "2028-05")     # 2028-06 closes after 07-01 and waits
    assert [e["date"] for e in rows if e["onset"]] == ["2028-03"]
    on = [e for e in rows if e["onset"]][0]
    assert {"1_vix", "4_spx"} <= set(on["markers"]) and "5_fed" not in on["markers"]      # Fed list dates are not shifted
    assert on["fed_list"] == {"sha256": dw.FED_SHA, "reviewed_through": dw.FED["reviewed_through"], "current": False}
    assert on["ofr_fsi"]["sha256"] is None or len(on["ofr_fsi"]["sha256"]) == 64
    assert on["subtype"]["dollar_funding"] is True and on["recorded_on"] == "2028-07-01"
    assert all(e["evaluated_on"] == "2028-07-01" and set(e["inputs"]) == set(dw.ONSET_FRED) for e in rows)
    assert [e["date"] for e in rows if e["n_markers"] >= 2 and not e["onset"]] == [e["date"] for e in rows if e["excluded_by"]]
    assert p["forward"]["onsets"]["live"][0]["date"] == "2028-03"
    assert all(e["late_evaluation"] for e in rows) and p["forward"]["status"] == "error"     # first run years late: flagged
    assert any("dated after their deadline" in x for x in p["forward"]["problems"])
    assert p["forward"]["onsets"]["next_month"] == "2028-06" and p["forward"]["onsets"]["months_evaluated"] == len(rows)
    blob = gzip.decompress(open(os.path.join(tmp_path, "archive", on["ofr_fsi"]["sha256"] + ".gz"), "rb").read()).decode()
    assert blob.startswith("date,OFR FSI\n") and blob.splitlines()[-1][:10] <= "2028-03-31" and len(blob.splitlines()) < 1600
    # a later vintage gives 2028-01 two markers: logged in revision_checks, never an onset
    rev = json.loads(json.dumps(shifted))
    vx = rev["fred"]["VIXCLS"]
    vx["values"][vx["dates"].index(next(d for d in vx["dates"] if d.startswith("2028-01")))] = 45.0
    sp = rev["fred"]["SP500"]
    i = sp["dates"].index(next(d for d in sp["dates"] if d.startswith("2028-01-1")))
    sp["values"][i] = 0.7 * max(v for v in sp["values"][:i] if v is not None)
    dw.build_dollar_watch(rev, today="2028-07-02", ledger_file=path)
    rows2 = {e["date"]: e for e in dw.load_ledger(path)["entries"] if e["kind"] == "onset_month"}
    assert len(rows2) == len(rows) and [m for m, e in rows2.items() if e["onset"]] == ["2028-03"]
    assert rows2["2028-01"]["revision_checks"][-1]["markers_now"] == ["1_vix", "4_spx"] and rows2["2028-01"]["onset"] is False
    assert rows2["2028-01"]["markers"] == rows[[e["date"] for e in rows].index("2028-01")]["markers"]   # the evaluation is untouched


def test_onset_waits_for_the_fed_list_review_until_the_deadline(inputs, tmp_path, monkeypatch):
    shifted = _shift(inputs, 8, cut="2020-12-31")
    path = str(tmp_path / "ledger.json")
    src = tmp_path / "cached.csv"                              # the fetch caches exist in production; archiving must succeed
    src.write_bytes(b"observation_date,X\n2026-11-30,1.0\n")
    monkeypatch.setattr(dw, "_source_file", lambda name: str(src))
    dw.build_dollar_watch(shifted, today="2026-12-08", ledger_file=path)           # 2026-11 closed 12-07; list reviewed through 2026-10
    assert not [e for e in dw.load_ledger(path)["entries"] if e["kind"] == "onset_month"]
    monkeypatch.setitem(dw.FED, "reviewed_through", "2026-11")
    dw.build_dollar_watch(shifted, today="2026-12-09", ledger_file=path)
    p = dw.build_dollar_watch(shifted, today="2026-12-09", ledger_file=path)
    rows = [e for e in dw.load_ledger(path)["entries"] if e["kind"] == "onset_month"]
    assert [e["date"] for e in rows] == ["2026-11"] and rows[0]["fed_list"]["current"] is True
    assert rows[0]["late_evaluation"] is False and rows[0]["inputs_missing"] is None and p["forward"]["status"] == "ok"


def test_momentum_rows_mature_after_every_month_and_subtype(tmp_path):
    """data review v1 M2: the onset record waits for every month m+1..m+12 and for each onset's subtype."""
    path = str(tmp_path / "ledger.json")
    months = [{"kind": "onset_month", "date": m, "onset": m == "2027-06"} for m in _months("2026-11", "2027-12")]
    months[[x["date"] for x in months].index("2027-06")]["subtype"] = {"dollar_funding": True}
    dw.append_ledger(path, [{"kind": "momentum", "date": "2027-01", "dxy_12m_pct": 10.5}] + months, "2027-02-03")
    dw.mature_momentum({"fred": {}}, path, "2028-03-01")                  # 2028-01 not evaluated yet
    assert "onset_within_12m" not in dw.load_ledger(path)["entries"][0]
    dw.append_ledger(path, [{"kind": "onset_month", "date": "2028-01", "onset": True}], "2028-02-10")   # its subtype is pending
    dw.mature_momentum({"fred": {}}, path, "2028-03-01")
    assert "onset_within_12m" not in dw.load_ledger(path)["entries"][0]
    dw._write_once(path, "onset_month", "subtype", lambda e: {"dollar_funding": False} if e["date"] == "2028-01" else None, "2028-04-08")
    dw.mature_momentum({"fred": {}}, path, "2028-04-09")
    got = dw.load_ledger(path)["entries"][0]["onset_within_12m"]
    assert got["onsets"] == ["2027-06", "2028-01"] and got["dollar_funding"] == ["2027-06"]
    assert "emfx_12m" not in dw.load_ledger(path)["entries"][0]          # no basket: that field waits on its own


def test_firing_rows_carry_the_point_in_time_record(inputs, tmp_path, monkeypatch):
    monkeypatch.setitem(dw.FREEZE, "freeze_date", "2026-11-03")
    path = str(tmp_path / "ledger.json")
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-09-19"), today="2028-09-20", ledger_file=path)   # before the firing
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-09-24"), today="2028-09-26", ledger_file=path)   # the week's release
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-11-06"), today="2028-11-07", ledger_file=path)
    led = dw.load_ledger(path)["entries"]
    rows = {e["date"]: e for e in led if e["kind"] == "scramble_rule"}
    a, b = rows["2028-09-22"], rows["2028-11-06"]
    assert a["first_vintage_contains_date"] is True and a["d3_eligible"] is True and a["unit_first"] == "2028-09-22"
    assert b["first_vintage_contains_date"] is True and b["unit_first"] is None    # re-arm-only rows are never units
    assert a["h10_release"] == "2028-09-25" and b["h10_release"] == "2028-11-13"
    for e in (a, b):
        assert isinstance(e["k"], int) and e["y10_now"] < e["y10_ref"] and 0.97 <= e["near_high_ratio"] <= 1.0
        assert set(e["inputs"]) == {"DTWEXBGS", "DGS10"} and e["calendar"] == "DTWEXBGS & DGS10"
    assert a["revision_checks"][0]["still_fires"] == {"re-arm": True, "unpatched": True}
    plc = [e for e in led if e["kind"] == "placebo_rule"]
    assert plc and all(e["variants"] == ["unpatched"] and "inputs" in e for e in plc)
    assert plc[0]["date"] < a["date"]                                     # the placebo fires on the climb, before the deceleration
    p = dw.build_dollar_watch(_shift(inputs, 20, cut="2008-11-06"), today="2028-11-08", ledger_file=path)
    assert all(e["kind"] in dw.LEDGER_VIEW_KINDS for e in p["ledger"]["live"])
    assert p["forward"]["d3"]["decel"]["units"] == 1 and p["forward"]["d3"]["placebo"]["rows"] == len(plc)


def test_d3_eligibility_starts_after_the_freeze(tmp_path, monkeypatch):
    """data review v1 S1: a pre-freeze firing is in-sample and never starts or absorbs a unit; a firing that appears
    only after a revision is logged and never scored; an unknown first vintage is flagged, not scored."""
    monkeypatch.setitem(dw.FREEZE, "freeze_date", "2030-03-01")
    path = str(tmp_path / "ledger.json")
    ds = [f"2030-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(330)]
    B = [100.0 + 0.01 * i for i in range(330)]
    Y = [3.0] * 330

    def firing(i):
        return {ds[i]: {"kind": "scramble_rule", "date": ds[i], "variants": ["unpatched"], "roc20_max_date": ds[i - 5],
                        "roc20_max_pct": 4.5, "roc20_now_pct": 1.0, "dollar": B[i]}}
    pre = dw.enrich_firings(firing(40), ds, B, Y, path, ds[39], b_last=ds[40])     # 2030-02-13: before the freeze
    assert pre[0]["d3_eligible"] is False and pre[0]["unit_first"] is None and "in-sample" in pre[0]["d3_note"]
    dw.append_ledger(path, pre, "2030-02-20")
    post = dw.enrich_firings(firing(170), ds, B, Y, path, ds[169], b_last=ds[170])  # 130 index days later, after the freeze
    assert post[0]["d3_eligible"] is True and post[0]["unit_first"] == ds[170]      # not absorbed by the pre-freeze row
    dw.append_ledger(path, post, "2030-07-20")
    late = dw.enrich_firings(firing(300), ds, B, Y, path, ds[310], b_last=ds[310])  # first seen on a vintage that already held its date
    assert late[0]["first_vintage_contains_date"] is False and late[0]["d3_eligible"] is False and late[0]["unit_first"] is None
    unknown = dw.enrich_firings(firing(320), ds, B, Y, path, None, b_last=ds[320])
    assert unknown[0]["d3_eligible"] is None and unknown[0]["unit_first"] is None
    outage = dw.enrich_firings(firing(322), ds, B, Y, path, ds[321], b_last=ds[329])   # a later release is being read
    assert outage[0]["first_vintage_contains_date"] is None and outage[0]["d3_eligible"] is None
    monkeypatch.setitem(dw.FREEZE, "freeze_date", "TO_FILL")
    assert dw.enrich_firings(firing(321), ds, B, Y, path, ds[320], b_last=ds[321])[0]["d3_eligible"] is False   # no freeze record


def test_units_run_from_the_first_firing_never_chained(tmp_path, monkeypatch):
    """SPEC v1 §3.1 (stats review v1 minor 5): k - k1 < 250 merges, measured from the unit's FIRST firing."""
    monkeypatch.setitem(dw.FREEZE, "freeze_date", "2029-12-31")
    path = str(tmp_path / "ledger.json")
    ds, d0 = [], date(2030, 1, 1)
    while len(ds) < 420:
        ds += [d0.isoformat()] if d0.weekday() < 5 else []
        d0 += timedelta(days=1)
    B = [100.0 + 0.01 * i for i in range(420)]
    Y = [3.0] * 420

    def add(i):
        rows = dw.enrich_firings({ds[i]: {"kind": "scramble_rule", "date": ds[i], "variants": ["unpatched"], "roc20_max_date": ds[i - 5],
                                          "roc20_max_pct": 4.5, "roc20_now_pct": 1.0, "dollar": B[i]}}, ds, B, Y, path, ds[i - 1],
                                  b_last=ds[i])
        dw.append_ledger(path, rows, ds[i])
        return rows[0]
    assert add(100)["unit_first"] == ds[100]
    second = add(230)
    assert second["unit_first"] == ds[100] and second["index_gap_to_unit_first"] == 130
    third = add(360)                                                       # 130 after the second, 260 after the first
    assert third["unit_first"] == ds[360] and third["index_gap_to_unit_first"] == 0


def test_placebo_is_the_rule_without_the_deceleration_clause():
    n = 200
    ds = [f"2030-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    B = [100.0] * 100 + [100.0 * math.exp(0.003 * j) for j in range(1, 81)]
    B += [B[-1] * (1 + 0.0002 * j) for j in range(1, 21)]
    Y = [3.0] * 100 + [3.0 - 0.01 * j for j in range(1, 101)]
    dec = dw.scramble_firings(ds, B, Y, False)
    plc = dw.scramble_firings(ds, B, Y, False, decel=False)
    assert dec and plc and plc[0]["k"] < dec[0]["k"]
    assert plc[0]["roc20_now_pct"] >= 4.0 > 0.5 * plc[0]["roc20_max_pct"] or plc[0]["roc20_now_pct"] == plc[0]["roc20_max_pct"]


def test_emfx_basket_withheld_when_a_leg_goes_stale(inputs, tmp_path):
    """data review v1 M4: a leg 15 business days behind withholds the basket (state issue, no marker 3)."""
    stale = json.loads(json.dumps(inputs))
    leg = stale["fred"]["DEXMAUS"]
    keep = len(leg["dates"]) - 15
    leg["dates"], leg["values"] = leg["dates"][:keep], leg["values"][:keep]
    assert dw.emfx_stale(stale["fred"]) and dw.emfx_basket(stale["fred"]) == ([], None)
    assert dw.emfx_stale(inputs["fred"]) is None
    p = dw.build_dollar_watch(stale, today="2026-11-02", ledger_file=str(tmp_path / "l.json"))
    assert any("EM FX basket is withheld" in x for x in p["state"]["issues"]) and p["state"]["emfx"]["latest"] is None
    assert "3_emfx" not in dw.onset_markers(stale, ["2020-03"])["2020-03"]


def test_units_merge_within_250_index_days(tmp_path, monkeypatch):
    monkeypatch.setitem(dw.FREEZE, "freeze_date", "2029-12-31")
    path = str(tmp_path / "ledger.json")
    ds = [f"2030-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(330)]
    B = [100.0 + 0.01 * i for i in range(330)]
    Y = [3.0] * 330
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": ds[100], "variants": ["unpatched"], "k": 100, "d3_eligible": True,
                             "unit_first": ds[100], "index_gap_to_unit_first": 0}], "2030-04-20")
    new = {ds[300]: {"kind": "scramble_rule", "date": ds[300], "variants": ["unpatched"], "roc20_max_date": ds[290],
                     "roc20_max_pct": 4.5, "roc20_now_pct": 1.0, "dollar": B[300]}}
    rows = dw.enrich_firings(new, ds, B, Y, path, ds[299], b_last=ds[300])
    assert rows[0]["unit_first"] == ds[100] and rows[0]["index_gap_to_unit_first"] == 200


def test_revision_checks_append_never_delete(tmp_path):
    path = str(tmp_path / "ledger.json")
    dw.append_ledger(path, [{"kind": "scramble_rule", "date": "2030-02-01", "variants": ["unpatched"]},
                            {"kind": "placebo_rule", "date": "2030-01-20", "variants": ["unpatched"]}], "2030-02-10")
    dw.revision_checks(path, set(), {"2030-02-01"}, "2030-02-10", placebo_dates={"2030-01-20"})
    dw.revision_checks(path, set(), {"2030-02-01"}, "2030-02-17", placebo_dates={"2030-01-20"})     # unchanged: no new entry
    dw.revision_checks(path, set(), set(), "2030-03-01", placebo_dates=set())                       # a revision removes both
    e, pl = dw.load_ledger(path)["entries"]
    assert [c["still_fires"]["unpatched"] for c in e["revision_checks"]] == [True, False] and e["date"] == "2030-02-01"
    assert [c["still_fires"]["unpatched"] for c in pl["revision_checks"]] == [True, False]


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
    short = dw.maturity_250d({"date": d}, ds, B, inputs, path, full=False)
    assert set(short) == {"hit", "dollar_at_firing", "max_b", "max_date", "further_rise_pct", "maturity_date", "maturity_vintage"}


def test_ledger_and_archive_are_downloadable_by_hash_only(tmp_path, monkeypatch):
    """C12: the harness downloads the ledger and the archived bytes; nothing but a sha256 name is ever served."""
    from fastapi import HTTPException
    from app.api import routes_dollar as rd
    path = tmp_path / "ledger" / "dollar_ledger.json"
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(path))
    assert rd.dollar_watch_ledger() == {"entries": []}
    src = tmp_path / "x.csv"
    src.write_bytes(b"observation_date,DTWEXBGS\n2030-01-02,120.0\n")
    rec = dw.archive_bytes(str(path), str(src))
    dw.append_ledger(str(path), [{"kind": "scramble_rule", "date": "2030-01-02", "variants": ["unpatched"]}], "2030-01-10")
    assert rd.dollar_watch_ledger().path == str(path)
    assert rd.dollar_watch_archive(rec["sha256"]).path.endswith(rec["sha256"])
    gz = dw.archive_bytes(str(path), str(src), compress=True)
    assert gz["sha256"] == rec["sha256"] and gzip.decompress(open(rd.dollar_watch_archive(gz["sha256"] + ".gz").path, "rb").read()) == src.read_bytes()
    for bad in ("../dollar_ledger.json", "dollar_ledger.json", rec["sha256"][:63], "0" * 64):
        with pytest.raises(HTTPException):
            rd.dollar_watch_archive(bad)


def test_spec_text_is_the_frozen_one():
    """the pre-committed §5.1-5.4 text is unchanged, and freeze.json carries the sha256 of the SPEC as frozen."""
    import hashlib
    body = open(os.path.join(SPEC_DIR, "SPEC_v1.md"), "rb").read()
    s = body.decode("utf-8")
    sec5 = s[s.index("## 5."):s.index("### 5.5")]
    assert hashlib.sha256(sec5.encode()).hexdigest() == dw.FREEZE["onset_check"]["precommit_sha256_section5"]
    assert dw.FREEZE["status"] == "FROZEN" and dw.FREEZE["freeze_date"] == "2026-11-03"
    assert hashlib.sha256(body).hexdigest() == dw.FREEZE["spec_sha256"]
    assert "TO_FILL" not in json.dumps(dw.FREEZE) and "G6_TABLE" not in s and "RECHECK_VERDICT" not in s
    fit = dw.FREEZE["d3"]["garch_fit"]
    for sid, h in fit["inputs_sha256"].items():
        assert hashlib.sha256(open(os.path.join(STUDY, "prereg", "freeze_vintage", f"{sid}.csv"), "rb").read()).hexdigest() == h


def test_failed_write_keeps_a_firing_first_vintage(inputs, tmp_path, monkeypatch):
    """a firing whose row could not be saved must still read as first-vintage on the next build (the rule state
    advances only after a successful write, and never backwards)."""
    monkeypatch.setitem(dw.FREEZE, "freeze_date", "2026-11-03")
    path = str(tmp_path / "dollar_ledger.json")
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-09-19"), today="2028-09-20", ledger_file=path)
    from app.sources import fred_csv as fc
    real = fc._write_atomic

    def boom(p, body):
        if p.endswith("dollar_ledger.json"):
            raise OSError("No space left on device")
        return real(p, body)
    monkeypatch.setattr(fc, "_write_atomic", boom)
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-09-24"), today="2028-09-26", ledger_file=path)
    assert dw._rule_state(path)["last_index_day"] < "2028-09-22"
    monkeypatch.setattr(fc, "_write_atomic", real)
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-09-24"), today="2028-09-27", ledger_file=path)
    row = [e for e in dw.load_ledger(path)["entries"] if e["kind"] == "scramble_rule"][0]
    assert row["date"] == "2028-09-22" and row["first_vintage_contains_date"] is True and row["d3_eligible"] is True
    dw.build_dollar_watch(_shift(inputs, 20, cut="2008-09-19"), today="2028-09-28", ledger_file=path)   # an older vintage
    assert dw._rule_state(path)["last_index_day"] >= "2028-09-24"
