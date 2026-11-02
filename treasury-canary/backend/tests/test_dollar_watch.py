"""Merge-blocking gate tests for GET /dollar-watch (studies/dollar-watch.md §5).

Offline. The assembly runs on the fetch_all() output captured 2026-11-02
(tests/fixtures/dollar_watch, FRED series other than the rule's three and SWPT
trimmed to 2019+). Gates:
  - the live frozen rule reproduces the reference's 7 re-arm / 6 unpatched
    firings, clause values included, on the fixture's full 2006+ history;
  - the reference is reproducible: re-running the study builder gives the
    committed bytes, and its input hashes match the committed study data;
  - the forward ledger is append-only and forward-only;
  - the scramble indicators exist only with the gate open, and are never summed;
  - forbidden language never appears in the payload or the tab's source;
  - the all-null payload ships every block (status "error") plus the frozen record;
  - payload json-serialisable, nulls never zeros, counts carry N and base rate.
"""
from __future__ import annotations

import gzip
import hashlib
import json
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

# memo §5: never on the panel
FORBIDDEN = ["probability of", "p(crisis", "chance of a crisis", "% chance", "crisis subsided", "subsided",
             "crisis over", "crisis is over", "all clear", "countdown", "next crisis in", "every crisis",
             "will crash", "imminent", "band breach", "ends in crisis", "leads the vix", "lamp"]


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


# ---------------------------------------------------------------------------- the frozen rule
def test_live_rule_reproduces_frozen_firings(inputs):
    ds, B, Y = dw.rule_index(inputs["fred"])
    re = dw.scramble_firings(ds, B, Y, True)
    un = dw.scramble_firings(ds, B, Y, False)
    frozen = dw.REF["scramble_rule"]["firings"]
    assert [f["date"] for f in re if f["date"] <= dw.FROZEN_ON] == [f["date"] for f in frozen]
    assert [f["date"] for f in un if f["date"] <= dw.FROZEN_ON] == dw.REF["scramble_rule"]["firings_unpatched"]
    assert len(frozen) == 7 and len(dw.REF["scramble_rule"]["firings_unpatched"]) == 6
    for live, ref in zip(re, frozen):
        for k in ("roc20_max_pct", "roc20_max_date", "roc20_now_pct", "dollar"):
            assert live[k] == ref[k], (live["date"], k)


def test_rule_index_is_the_frozen_one(inputs):
    ds, _, _ = dw.rule_index(inputs["fred"])
    have = {s: set(inputs["fred"][s]["dates"][i] for i, v in enumerate(inputs["fred"][s]["values"]) if v is not None)
            for s in ("DTWEXBGS", "DGS10", "VIXCLS")}
    assert set(ds) == have["DTWEXBGS"] & have["DGS10"] & have["VIXCLS"]
    assert "VIXCLS" in dw.RULE["index"] and "DGS10" in dw.RULE["index"]


def test_rule_evaluates_the_latest_day():
    """the study code skipped the final index day; the live rule must not."""
    import math
    n = 200
    ds = [f"2030-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    B = [100.0] * 100 + [100.0 * math.exp(0.003 * j) for j in range(1, 81)]            # a 20-day climb near +6%
    B += [B[-1] * (1 + 0.0002 * j) for j in range(1, 21)]                                # then a crawl: deceleration
    Y = [3.0] * 100 + [3.0 - 0.01 * j for j in range(1, 101)]                            # yields falling
    fires = dw.scramble_firings(ds, B, Y, True)
    assert fires, "synthetic scramble must fire"
    k = fires[0]["k"]
    assert dw.scramble_firings(ds[:k + 1], B[:k + 1], Y[:k + 1], True)[-1]["k"] == k   # fires ON its last day


# ---------------------------------------------------------------------------- provenance of the reference
def test_reference_rebuilds_byte_identical(tmp_path):
    out = tmp_path / "ref.json"
    subprocess.run([sys.executable, "-I", os.path.join(STUDY, "code", "build_reference.py"), os.path.join(STUDY, "data"), str(out)],
                   check=True, capture_output=True, cwd=ROOT)
    assert out.read_bytes() == open(REF_FILE, "rb").read()


def test_reference_input_hashes_match_committed_data():
    ref = json.load(open(REF_FILE))
    for rel, want in ref["provenance"]["inputs_sha256"].items():
        got = hashlib.sha256(open(os.path.join(STUDY, "data", rel), "rb").read()).hexdigest()
        assert got == want, rel


def test_reference_numbers_the_memo_cites():
    ref = dw.REF
    a, c = ref["band"]["by_list"]["A25"], ref["band"]["by_list"]["C16"]
    assert ref["band"]["by_list"]["A25"]["n_excursions"] == 17
    assert (a["hits_12m"], a["hits_24m"], c["hits_12m"], c["hits_24m"]) == (8, 12, 4, 8)
    assert ref["quadrant"]["by_list"]["C16"]["counts"] == {"usd_up_yld_down": 9, "usd_up_yld_up": 2, "usd_down_yld_up": 3, "usd_down_yld_down": 2}
    assert abs(sum(ref["quadrant"]["base_all_months"]["shares"].values()) - 1) < 0.002
    assert (ref["gold"]["ended_higher"], ref["gold"]["n_with_end"]) == (14, 25)
    assert ref["dollar_fell_at_peak_stress"]["fell"] == 9
    mn = ref["scramble_rule"]["monthly_null"]
    assert (mn["firings"], mn["dollar_peak_within_3m"], mn["spx_up_12m"]) == (10, 3, 6)
    rd = ref["redollarisation"]
    assert (rd["corr_yoy_contemporaneous"], rd["corr_yoy_dollar_leads_1q"]) == (-0.5, -0.55)
    for key in ("A25", "C16", "N5"):          # every count carries its N and base rate
        assert {"rate_12m", "base_12m", "n_excursions"} <= set(ref["band"]["by_list"][key])
        assert {"episodes", "base_12m", "signal_months"} <= set(ref["momentum"]["by_list"][key])


# ---------------------------------------------------------------------------- live payload on the fixture
def test_payload_ok_and_serialisable(payload):
    json.dumps(payload)
    assert payload["mode"] == "descriptive"
    assert payload["status"]["overall"] == "ok", payload["status"]
    for b in ("state", "funding", "scramble", "slow", "ledger"):
        assert payload[b]["status"] in ("ok", "stale", "error")
    assert payload["scramble"]["live_check"]["reproduces_frozen_rearm"] is True
    assert payload["scramble"]["live_check"]["reproduces_frozen_unpatched"] is True


def test_payload_values_on_the_fixture(payload, inputs):
    st = payload["state"]
    assert st["dxy"]["latest"] == 101.72 and st["dxy"]["asof"] == "2026-11-02"
    assert st["dxy"]["band_position"].startswith("inside the band")
    assert st["dxy"]["monthly"]["splice_check"]["max_abs_diff_pct"] <= 0.1
    assert st["broad"]["broad"]["latest"] == 121.32
    rows = {r["id"]: r for r in payload["funding"]["rows"]}
    f = inputs["fred"]
    cpf = dict(zip(f["DCPF3M"]["dates"], f["DCPF3M"]["values"]))
    tb = dict(zip(f["DTB3"]["dates"], f["DTB3"]["values"]))
    last = max(d for d in cpf if cpf[d] is not None and tb.get(d) is not None)
    assert rows["cp_fin"]["latest"] == round(cpf[last] - tb[last], 2) and rows["cp_fin"]["asof"] == last
    assert rows["swap_lines"]["unit"] == "$bn" and rows["swap_lines"]["latest"] == 0.16
    assert rows["emb"]["pct_own_history"] is None              # two-year feed: no percentile claimed
    sc = payload["scramble"]
    assert sc["state"]["gate_open"] is False and sc["indicators"] is None and sc["confirmations"] is None
    uc = payload["slow"]["usd_credit"]
    assert (uc["quarter"], uc["total_tn"], uc["yoy_pct"]) == ("2026-Q2", 15.133, 8.1)
    assert uc["label"].startswith("re-dollarising")
    assert payload["slow"]["fx_swaps"]["all_tn"] == 129.3 and payload["slow"]["fx_swaps"]["usd_leg_tn"] == 113.5
    q = st["quadrant"]
    assert q["month"] == "2026-10" and q["quadrant"] == "usd_up_yld_up"


def test_nulls_never_zero(tmp_path):
    p = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "l.json"))
    assert p["state"]["dxy"]["latest"] is None and p["state"]["broad"]["broad"]["latest"] is None
    assert all(r["latest"] is None for r in p["funding"]["rows"])
    assert p["scramble"]["state"] is None


def test_all_null_payload_ships_every_block_and_the_frozen_record(tmp_path):
    p = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "l.json"))
    json.dumps(p)
    assert p["status"]["overall"] == "error"
    for b in ("state", "funding", "scramble", "slow"):
        assert p[b]["status"] == "error"
    assert len(p["scramble"]["history"]) == 7 and p["scramble"]["monthly_null"]["firings"] == 10
    assert p["state"]["band"]["excursions"] and p["state"]["counter_examples"]
    assert "unavailable" in p["headline"]


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
    assert ofr["Volatility"] == [None, None]                   # absent column -> None, never 0
    with pytest.raises(ValueError):
        dollar_data.parse_ofr_columns(b"<html>maintenance</html>")
    bis = dollar_data.parse_bis_csv(b"FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,US,2026-09,3.875\nM,US,2026-08,3.625\nM,XM,2026-09,\n", "REF_AREA")
    assert bis["US"] == [("2026-08", 3.625), ("2026-09", 3.875)] and bis["XM"] == [("2026-09", None)]
    with pytest.raises(ValueError):
        dollar_data.parse_bis_csv(b"<html/>")


# ---------------------------------------------------------------------------- the gauge with the gate open
def _open_gate_inputs(inputs):
    """the fixture cut at 2008-11-06 (the re-arm firing): a real open gate."""
    cut = json.loads(json.dumps(inputs))
    for s in list(cut["fred"].values()) + [cut["dxy"], cut["gold"], cut["emb"]]:
        keep = [i for i, d in enumerate(s["dates"]) if d <= "2008-11-06"]
        s["dates"] = [s["dates"][i] for i in keep]
        s["values"] = [s["values"][i] for i in keep]
    return cut


def test_indicators_only_with_gate_open_never_summed(inputs, tmp_path):
    p = dw.build_dollar_watch(_open_gate_inputs(inputs), today="2008-11-06", ledger_file=str(tmp_path / "l.json"))
    sc = p["scramble"]
    assert sc["state"]["asof"] == "2008-11-06" and sc["gate_open"] is True
    assert sc["fires_today"]["re-arm"] is True and sc["fires_today"]["unpatched"] is False
    ind = sc["indicators"]
    assert set(ind) == {"a_deceleration", "b_funding_easing", "c_risk_turn", "note"}
    assert ind["a_deceleration"]["met"] is True
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
    dw.append_ledger(path, [dict(e1, variants=["re-arm", "unpatched"])], "2027-03-15")     # same key: never edited
    led = dw.load_ledger(path)
    assert led["entries"] == [dict(e1, recorded_on="2027-03-08")]
    dw.append_ledger(path, [{"kind": "momentum", "date": "2027-05", "dxy_12m_pct": 10.4}], "2027-06-02")
    assert [e["kind"] for e in dw.load_ledger(path)["entries"]] == ["scramble_rule", "momentum"]
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert dw.append_ledger(str(bad), [e1], "2027-03-08").get("_unreadable")
    assert bad.read_text() == "{not json"                      # an unreadable ledger is never overwritten


def test_frozen_history_never_enters_the_live_ledger(payload, tmp_path):
    assert payload["ledger"]["live"] == [] and payload["scramble"]["live_firings"] == []
    assert not os.path.exists(tmp_path / "ledger.json")         # nothing after the freeze fired: nothing written


def test_live_firing_after_freeze_is_recorded_once(inputs, tmp_path):
    """replay the 2008-11-06 shape after the freeze date: the rule fires, the ledger records it once."""
    shifted = _open_gate_inputs(inputs)
    for s in shifted["fred"].values():
        s["dates"] = [f"{int(d[:4]) + 20}{d[4:]}" for d in s["dates"]]       # 2008 -> 2028 (leap years line up)
    path = str(tmp_path / "ledger.json")
    p1 = dw.build_dollar_watch(shifted, today="2028-11-06", ledger_file=path)
    live = [e for e in p1["scramble"]["live_firings"] if e["kind"] == "scramble_rule"]
    assert [e["date"] for e in live] == ["2028-09-22", "2028-11-06"]
    assert live[1]["variants"] == ["re-arm"] and live[0]["variants"] == ["re-arm", "unpatched"]
    assert all(e["recorded_on"] == "2028-11-06" for e in live)
    p2 = dw.build_dollar_watch(shifted, today="2028-11-07", ledger_file=path)
    assert len([e for e in p2["scramble"]["live_firings"] if e["kind"] == "scramble_rule"]) == 2


# ---------------------------------------------------------------------------- language
def test_forbidden_language_absent(payload, tmp_path):
    null = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=str(tmp_path / "n.json"))
    text = " ".join(list(_strings(payload)) + list(_strings(null))).lower()
    for phrase in FORBIDDEN:
        assert phrase not in text, phrase
    for path in TAB_SOURCES:
        if os.path.exists(path):
            src = open(path, encoding="utf-8").read().lower()
            for phrase in FORBIDDEN:
                assert phrase not in src, (os.path.basename(path), phrase)


def test_tab_sources_exist():
    for path in TAB_SOURCES:
        assert os.path.exists(path), path
