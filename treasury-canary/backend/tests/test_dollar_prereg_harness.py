"""Gate G7 (SPEC v1 §3.7): the offline D-3 harness, studies/dollar_watch/prereg/d3.py.

  - the Poisson-binomial pmf, the one-sided bound delta_U and the exact alpha-spending recursion match
    brute-force enumeration for n <= 12;
  - p_u is ordered by drift (common random numbers) and reproducible from its seed;
  - pu-row reads only the archived firing bytes: appending data after k1 changes nothing, and a hash
    mismatch, a non-admitted row or an index mismatch is refused;
  - a look classifies PASS / continue by the recorded critical value and prints the placebo beside it.
Synthetic inputs only, except the freeze-vintage files used as an archive.
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os

import numpy as np
import pytest

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PREREG = os.path.join(ROOT, "studies", "dollar_watch", "prereg")
FREEZE = os.path.join(ROOT, "studies", "dollar_watch", "spec", "freeze.json")

_spec = importlib.util.spec_from_file_location("d3_harness", os.path.join(PREREG, "d3.py"))
d3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d3)


def _enum(ps):
    """brute force: P(S = s) over all 2^n outcomes."""
    out = np.zeros(len(ps) + 1)
    for bits in itertools.product((0, 1), repeat=len(ps)):
        out[sum(bits)] += np.prod([p if b else 1 - p for p, b in zip(ps, bits)])
    return out


def test_pb_and_delta_upper_match_brute_force():
    rng = np.random.default_rng(7)
    for n in range(1, 13):
        ps = rng.uniform(0.05, 0.95, n)
        assert np.allclose(d3.pb_pmf(ps), _enum(ps), atol=1e-12)
        S = int(rng.integers(0, n + 1))
        assert d3.p_plus(S, ps) == pytest.approx(_enum(ps)[S:].sum(), abs=1e-12)
        brute = max((i / 1000 for i in range(-1000, 1001)
                     if _enum(np.clip(ps + i / 1000, 0, 1))[: S + 1].sum() >= d3.FAIL_LEVEL), default=-1.0)
        assert d3.delta_upper(S, ps) == pytest.approx(brute, abs=1e-9)


def test_exact_spending_matches_enumeration():
    rng = np.random.default_rng(11)
    blocks = [list(rng.uniform(0.2, 0.6, 3)) for _ in range(3)]
    flat = [p for b in blocks for p in b]
    ends = [3, 6, 9]

    def brute(crit):
        tot = 0.0
        for bits in itertools.product((0, 1), repeat=9):
            pr = np.prod([p if b else 1 - p for p, b in zip(flat, bits)])
            if any(sum(bits[:e]) >= c for e, c in zip(ends, crit)):
                tot += pr
        return tot
    for crit in ([3, 4, 6], [2, 5, 7], [3, 7, 10]):
        assert d3.crossing_prob(blocks, crit) == pytest.approx(brute(crit), abs=1e-12)
    prev = []
    for j, a in enumerate([0.02, 0.06, 0.12]):
        c = d3.critical_value(blocks[: j + 1], prev, a)
        assert d3.crossing_prob(blocks[: j + 1], prev + [c]) <= a + 1e-15
        if c > 0:
            assert d3.crossing_prob(blocks[: j + 1], prev + [c - 1]) > a      # the smallest such c
        prev.append(c)


def test_p_u_ordered_by_drift_and_reproducible():
    params = json.load(open(FREEZE))["d3"]["garch_fit"]
    h_unc = params["omega"] / (1 - params["alpha"] - params["beta"])
    a = d3.p_u(params, 2 * h_unc, n_paths=4000, seed=20300102)
    b = d3.p_u(params, 2 * h_unc, n_paths=4000, seed=20300102)
    assert a == b
    p = {k: v["p_u"] for k, v in a["by_drift"].items()}
    assert p["minus1"] >= p["zero"] >= p["plus1"] and p["minus1"] > p["plus1"]


def _archive(tmp_path, through: str, extra_after: bool):
    """an archive holding the freeze-vintage DTWEXBGS/DGS10 bytes cut at `through` (optionally with later rows)."""
    arc = tmp_path / ("arc_extra" if extra_after else "arc")
    arc.mkdir()
    shas = {}
    for sid in ("DTWEXBGS", "DGS10"):
        lines = open(os.path.join(PREREG, "freeze_vintage", f"{sid}.csv"), encoding="utf-8").read().splitlines()
        keep = [lines[0]] + [x for x in lines[1:] if x[:10] <= through or extra_after]
        body = ("\n".join(keep) + "\n").encode()
        h = hashlib.sha256(body).hexdigest()
        (arc / h).write_bytes(body)
        shas[sid] = h
    return str(arc), shas


def _ledger(tmp_path, name, date, shas, k, **kw):
    row = {"kind": "scramble_rule", "date": date, "variants": ["unpatched"], "k": k, "d3_eligible": True, "unit_first": date,
           "inputs": {sid: {"sha256": h} for sid, h in shas.items()}, **kw}
    p = tmp_path / name
    p.write_text(json.dumps({"entries": [row]}))
    return str(p)


def test_pu_row_reads_only_the_archived_bytes(tmp_path):
    day = "2026-10-15"
    arc, shas = _archive(tmp_path, day, extra_after=False)
    ds, _ = d3.rule_calendar(os.path.join(arc, shas["DTWEXBGS"]), os.path.join(arc, shas["DGS10"]))
    k = ds.index(day)
    l1 = _ledger(tmp_path, "l1.json", day, shas, k)
    none = str(tmp_path / "none.json")
    rec = d3.pu_row(l1, arc, FREEZE, "scramble_rule", day, none, None, n_paths=3000)
    arc2, shas2 = _archive(tmp_path, day, extra_after=True)                  # the same vintage plus data after k1
    l2 = _ledger(tmp_path, "l2.json", day, shas2, k)
    rec2 = d3.pu_row(l2, arc2, FREEZE, "scramble_rule", day, none, None, n_paths=3000)
    assert rec["by_drift"] == rec2["by_drift"] and rec["h_next"] == rec2["h_next"] and rec["seed"] == 20261015
    assert rec["unit_members"] == []
    records = str(tmp_path / "records.json")
    d3.pu_row(l2, arc2, FREEZE, "scramble_rule", day, none, records, n_paths=500)
    assert len(json.load(open(records))["records"]) == 1
    with pytest.raises(SystemExit, match="computed once"):                    # M-B: once
        d3.pu_row(l2, arc2, FREEZE, "scramble_rule", day, none, records, n_paths=100)
    with pytest.raises(SystemExit, match="before maturity"):                  # M-B: before maturity
        d3.pu_row(_ledger(tmp_path, "l6.json", day, shas2, k, outcomes_250d={"hit": True}), arc2, FREEZE, "scramble_rule", day,
                  none, None, n_paths=100)
    with pytest.raises(SystemExit, match="index mismatch"):
        d3.pu_row(_ledger(tmp_path, "l5.json", day, shas2, k + 1), arc2, FREEZE, "scramble_rule", day, none, None, n_paths=100)
    with pytest.raises(SystemExit, match="not an admitted unit start"):
        d3.pu_row(_ledger(tmp_path, "l4.json", day, shas2, k, d3_eligible=False), arc2, FREEZE, "scramble_rule", day, none, None,
                  n_paths=100)
    open(os.path.join(arc, shas["DGS10"]), "ab").write(b"2026-10-16,9.99\n")   # tampered bytes: the row no longer resolves
    with pytest.raises(SystemExit, match="not an admitted unit start"):
        d3.pu_row(l1, arc, FREEZE, "scramble_rule", day, none, None, n_paths=100)
    assert d3.units(l1, none, arc, "scramble_rule")["unresolved"] == [day]


def test_harness_rule_is_the_panels_rule():
    import gzip
    from app.metrics import dollar_watch as dw
    inputs = json.load(gzip.open(os.path.join(HERE, "fixtures", "dollar_watch", "inputs_2026-11-02.json.gz"), "rt"))
    ds, B, Y = dw.rule_index(inputs["fred"])
    params = json.load(open(FREEZE))["rule_params"]
    assert d3.rule_firings(ds, B, Y, params) == [f["date"] for f in dw.scramble_firings(ds, B, Y, False)]
    assert d3.rule_firings(ds, B, Y, params, decel=False) == [f["date"] for f in dw.scramble_firings(ds, B, Y, False, decel=False)]


def _vintage(tmp_path, name: str, through: str):
    """a vintage cut at `through`, written outside the archive (as an ALFRED download would be)."""
    out = {}
    for sid in ("DTWEXBGS", "DGS10"):
        lines = open(os.path.join(PREREG, "freeze_vintage", f"{sid}.csv"), encoding="utf-8").read().splitlines()
        p = tmp_path / f"{name}_{sid}.csv"
        p.write_text("\n".join([lines[0]] + [x for x in lines[1:] if x[:10] <= through]) + "\n")
        out[sid] = str(p)
    return out


def test_admit_reruns_the_rule_on_the_first_vintage(tmp_path, monkeypatch):
    """re-check M-A: a row with an unknown first vintage is admitted (or not) by the rule on the vintage whose last day falls
    in the firing's H.10 week; a later vintage is refused; the record is written once."""
    fz = json.load(open(FREEZE))
    fz["freeze_date"] = "2008-01-01"                                       # pretend the freeze preceded 2008 (synthetic check)
    fzp = tmp_path / "freeze.json"
    fzp.write_text(json.dumps(fz))
    arc = tmp_path / "arc"
    arc.mkdir()
    led = tmp_path / "ledger.json"
    led.write_text(json.dumps({"entries": [{"kind": "scramble_rule", "date": "2008-09-22", "variants": ["unpatched"], "d3_eligible": None},
                                           {"kind": "placebo_rule", "date": "2008-09-22", "variants": ["unpatched"], "d3_eligible": None}]}))
    adm = str(tmp_path / "admissions.json")
    late = _vintage(tmp_path, "late", "2008-10-03")
    with pytest.raises(SystemExit, match="not the first vintage"):
        d3.admit(str(led), str(fzp), "scramble_rule", "2008-09-22", "2008-10-06", late["DTWEXBGS"], late["DGS10"], str(arc), adm)
    first = _vintage(tmp_path, "first", "2008-09-26")
    rec = d3.admit(str(led), str(fzp), "scramble_rule", "2008-09-22", "2008-09-29", first["DTWEXBGS"], first["DGS10"], str(arc), adm)
    assert rec["admitted"] is True and rec["vintage_last_day"] == "2008-09-26" and rec["vintage_date"] == "2008-09-29"
    assert all(os.path.exists(arc / v["sha256"]) for v in rec["inputs"].values()) and rec["repair"] is False
    plc = d3.admit(str(led), str(fzp), "placebo_rule", "2008-09-22", "2008-09-29", first["DTWEXBGS"], first["DGS10"], str(arc), adm)
    assert plc["admitted"] is False                                         # the placebo did not fire that day
    with pytest.raises(SystemExit, match="already has an admission"):
        d3.admit(str(led), str(fzp), "scramble_rule", "2008-09-22", "2008-09-29", first["DTWEXBGS"], first["DGS10"], str(arc), adm)
    u = d3.units(str(led), adm, str(arc), "scramble_rule")
    assert [x["first"] for x in u["units"]] == ["2008-09-22"] and u["unresolved"] == []
    # confirm pass M-1: an admitted row whose archived bytes are lost is repaired from the first vintage (other bytes)
    led2 = tmp_path / "ledger2.json"
    led2.write_text(json.dumps({"entries": [{"kind": "scramble_rule", "date": "2008-09-22", "variants": ["unpatched"], "d3_eligible": True,
                                             "inputs": {"DTWEXBGS": {"sha256": "0" * 64}, "DGS10": {"sha256": "1" * 64}}}]}))
    adm2 = str(tmp_path / "admissions2.json")
    assert d3.units(str(led2), adm2, str(arc), "scramble_rule")["unresolved"] == ["2008-09-22"]
    fix = d3.admit(str(led2), str(fzp), "scramble_rule", "2008-09-22", "2008-09-29", first["DTWEXBGS"], first["DGS10"], str(arc), adm2)
    assert fix["repair"] is True and fix["admitted"] is True
    u2 = d3.units(str(led2), adm2, str(arc), "scramble_rule")
    assert [x["first"] for x in u2["units"]] == ["2008-09-22"] and u2["unresolved"] == []


def test_units_rebuild_from_the_rows(tmp_path):
    """SPEC v1 §3.1: units run 250 index days from their FIRST firing, counted on each later firing's own vintage."""
    full, _ = d3.rule_calendar(os.path.join(PREREG, "freeze_vintage", "DTWEXBGS.csv"), os.path.join(PREREG, "freeze_vintage", "DGS10.csv"))
    i0 = full.index("2019-01-02")
    days = [full[i0], full[i0 + 130], full[i0 + 260]]
    arc = tmp_path / "arc"
    arc.mkdir()
    rows = []
    for d in days:
        v = _vintage(tmp_path, d, d)
        shas = {}
        for sid, src in v.items():
            body = open(src, "rb").read()
            h = hashlib.sha256(body).hexdigest()
            (arc / h).write_bytes(body)
            shas[sid] = {"sha256": h}
        rows.append({"kind": "scramble_rule", "date": d, "variants": ["unpatched"], "d3_eligible": True, "inputs": shas,
                     "unit_first": days[0] if d != days[2] else days[2]})
    rows[1]["unit_first"] = days[1]                                         # a wrong panel field, to be reported
    led = tmp_path / "ledger.json"
    led.write_text(json.dumps({"entries": rows}))
    out = d3.units(str(led), str(tmp_path / "none.json"), str(arc), "scramble_rule")
    assert [u["first"] for u in out["units"]] == [days[0], days[2]]
    assert out["units"][0]["members"] == [{"date": days[1], "gap": 130}]
    assert out["mismatches_with_panel"] == [{"date": days[1], "panel": days[1], "rebuilt": days[0]}]
    # confirm pass M-1: a lost archive makes its row unresolved (listed, skipped, never fatal) until admit restores the bytes
    lost = rows[0]["inputs"]["DTWEXBGS"]["sha256"]
    os.remove(arc / lost)
    out = d3.units(str(led), str(tmp_path / "none.json"), str(arc), "scramble_rule")
    assert out["unresolved"] == [days[0]] and [u["first"] for u in out["units"]] == [days[1]]
    fz = json.load(open(FREEZE))
    fz["freeze_date"] = "2018-12-31"
    fzp = tmp_path / "freeze_2018.json"
    fzp.write_text(json.dumps(fz))
    v = _vintage(tmp_path, "alfred_" + days[0], days[0])
    adm = str(tmp_path / "adm.json")
    rec = d3.admit(str(led), str(fzp), "scramble_rule", days[0], "2019-01-07", v["DTWEXBGS"], v["DGS10"], str(arc), adm)
    assert rec["repair"] is True
    out = d3.units(str(led), adm, str(arc), "scramble_rule")
    assert out["unresolved"] == [] and [u["first"] for u in out["units"]] == [days[0], days[2]]


def test_look_uses_the_recorded_critical_value_and_prints_the_placebo():
    unit = {"p_u": {"minus1": 0.35, "zero": 0.30, "plus1": 0.25}}
    units = [dict(unit, hit=1) for _ in range(7)] + [dict(unit, hit=0)]
    lk = d3.evaluate_look(0, units, [])
    assert lk["critical_value"] == 7 and lk["class"] == "PASS" and lk["null_crossing_prob"] <= 0.005
    assert lk["T"]["zero"] == pytest.approx((7 - 2.4) / 8)
    weak = d3.evaluate_look(0, [dict(unit, hit=int(i < 3)) for i in range(8)], [])
    assert weak["class"] == "continue"
    same = d3.placebo_beside(lk, [dict(unit, hit=1) for _ in range(5)])
    none = d3.placebo_beside(lk, [dict(unit, hit=0) for _ in range(5)])
    assert same["matches_or_beats_rule"] is True and none["matches_or_beats_rule"] is False
    # stats re-check S2: the placebo is printed beside a PASS and never changes its wording
    assert same["wording"] == none["wording"] == d3.PASS_WORDING and "deceleration-specific: not tested" in d3.PASS_WORDING
    assert d3.placebo_beside(weak, [])["wording"] is None and set(lk["tail_p"]) == {"minus1", "zero", "plus1"}
