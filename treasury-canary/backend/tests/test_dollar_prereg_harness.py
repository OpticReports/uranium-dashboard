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
    rec = d3.pu_row(_ledger(tmp_path, "l1.json", day, shas, k), arc, FREEZE, "scramble_rule", day, n_paths=3000)
    arc2, shas2 = _archive(tmp_path, day, extra_after=True)                  # the same vintage plus data after k1
    rec2 = d3.pu_row(_ledger(tmp_path, "l2.json", day, shas2, k), arc2, FREEZE, "scramble_rule", day, n_paths=3000)
    assert rec["by_drift"] == rec2["by_drift"] and rec["h_next"] == rec2["h_next"] and rec["seed"] == 20261015
    bad = dict(shas)
    open(os.path.join(arc, shas["DGS10"]), "ab").write(b"2026-10-16,9.99\n")   # tampered bytes
    with pytest.raises(SystemExit, match="do not match"):
        d3.pu_row(_ledger(tmp_path, "l3.json", day, bad, k), arc, FREEZE, "scramble_rule", day, n_paths=100)
    with pytest.raises(SystemExit, match="not an admitted unit start"):
        d3.pu_row(_ledger(tmp_path, "l4.json", day, shas2, k, d3_eligible=False), arc2, FREEZE, "scramble_rule", day, n_paths=100)
    with pytest.raises(SystemExit, match="index mismatch"):
        d3.pu_row(_ledger(tmp_path, "l5.json", day, shas2, k + 1), arc2, FREEZE, "scramble_rule", day, n_paths=100)


def test_look_uses_the_recorded_critical_value_and_prints_the_placebo():
    unit = {"p_u": {"minus1": 0.35, "zero": 0.30, "plus1": 0.25}}
    units = [dict(unit, hit=1) for _ in range(7)] + [dict(unit, hit=0)]
    lk = d3.evaluate_look(0, units, [])
    assert lk["critical_value"] == 7 and lk["class"] == "PASS" and lk["null_crossing_prob"] <= 0.005
    assert lk["T"]["zero"] == pytest.approx((7 - 2.4) / 8)
    weak = d3.evaluate_look(0, [dict(unit, hit=int(i < 3)) for i in range(8)], [])
    assert weak["class"] == "continue"
    same = d3.placebo_beside(lk, [dict(unit, hit=1) for _ in range(5)])
    assert same["wording"] == "post-scramble reversal: not specific to deceleration"
    none = d3.placebo_beside(lk, [dict(unit, hit=0) for _ in range(5)])
    assert none["wording"] == "deceleration flag ON"
