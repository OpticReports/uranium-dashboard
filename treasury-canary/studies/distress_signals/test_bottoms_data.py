"""Data gate for studies/distress-bottoms.md: the monthly D&B files against
HSUS annual totals, the 1898-06 correction, and the equity / claims loaders.

    python3 -m pytest -q test_bottoms_data.py
"""
from __future__ import annotations

from collections import defaultdict

import load as D
from engine import M


def _annual(s):
    o = defaultdict(list)
    for m, v in s.items():
        o[m // 12].append(v)
    return {y: sum(v) for y, v in o.items() if len(v) == 12}


def test_failure_counts_match_hsus_v24():
    hs = D.hsus_dnb_annual()
    a, b, c = D.dnb_count_segments()
    off = {}
    for seg, years in ((a, range(1894, 1933)), (b, range(1935, 1939)), (c, range(1939, 1965))):
        s = _annual(seg)
        off.update({y: s[y] / hs[y]["number"] - 1 for y in years})
    assert {y for y, r in off.items() if abs(r) > 0.005} == {1909}     # 1909 +0.8%, no single-month outlier
    assert abs(off[1898]) < 0.001                                        # after the 1898-06 fix
    assert _annual(D.dnb_count_segments(fix=False)[0])[1898] - hs[1898]["number"] == 300
    assert a[M(1898, 6)] == 1149


def test_failure_liabilities_match_hsus_v27():
    hs = D.hsus_dnb_annual()
    la, lc = D.dnb_liability_segments()
    off = {}
    for seg, years in ((la, range(1894, 1934)), (lc, range(1939, 1966))):
        s = _annual(seg)
        off.update({y: s[y] / hs[y]["liabilities"] - 1 for y in years})
    # 1894 +1.2%; 1943-46 are $30-67m totals rounded to $1m in HSUS
    assert {y for y, r in off.items() if abs(r) > 0.005} == {1894, 1943, 1944, 1945, 1946}
    assert max(lc) == M(1983, 12)                                        # ends before D&B's 1984 change


def test_equity_and_claims_loaders():
    p, _ = D.shiller_monthly()
    assert all(M(1914, mo) not in p for mo in range(8, 12)) and M(1914, 7) in p and M(1914, 12) in p
    tr = D.equity_total_return()
    assert tr[min(tr)] == 1.0 and max(tr) <= M(2024, 6)
    val, rel = D.claims_monthly_nsa()
    assert min(val) == M(1967, 1) and rel[M(1967, 1)] in (M(1967, 1), M(1967, 2))
    assert all(rel[m] - m in (0, 1) for m in val)
