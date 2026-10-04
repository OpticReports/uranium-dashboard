"""The frozen-cache builder's basis normalization (scripts/refresh_backtest_bars.py).

Defects this guards against, all seen on 2026-10-04: a constant factor
applied to a series that changes basis mid-way (FMP applied ATAI's split
factor to history only, so dividing the whole series put the post-break rows
13.7x too high and flipped a survival verdict); a near-unity factor (ILMN,
0.999) being mistaken for a break on every ordinary trading day; and - the
adversarial reviewer's point - a break missed because the symbol also moved
on the split day, which would silently fall back to the whole-series rule
and recreate the cliff.
"""
from __future__ import annotations

from scripts import refresh_backtest_bars as R

F = 0.0728


def _rows(closes: list[float], start_day: int = 1) -> list[dict]:
    out = []
    for i, c in enumerate(closes):
        d = f"2026-01-{start_day + i:02d}"
        out.append({"date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "adj_close": c})
    return out


def _entries_on(rows, idx, factor=F):
    return [(rows[i]["date"], rows[i]["open"] / factor) for i in idx]


def test_break_detected_even_when_the_symbol_moved_on_the_split_day():
    """History at F x basis, then on basis - with a genuine +8% move on the
    break day on top of the 13.7x basis jump."""
    rows = _rows([0.50, 0.51, 0.52, 0.52 / F * 1.08, 7.70, 7.80])
    assert R.basis_breaks(rows, F) == [3]


def test_near_unity_factor_never_infers_a_break():
    rows = _rows([100.0, 100.1, 99.9, 100.2, 100.0])
    assert R.basis_breaks(rows, 0.999) == []


def test_segment_normalization_divides_only_the_entries_side(monkeypatch):
    rows = _rows([0.50, 0.51, 0.52, 0.52 / F * 1.02, 7.20, 7.30, 7.25, 7.40])
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": _entries_on(rows, [0, 1, 2, 0, 1])})
    applied = R.normalize_basis({"SYM": rows})
    assert applied["SYM"]["segment"] == f"rows before {rows[3]['date']}"
    assert applied["SYM"]["rows_divided"] == 3
    closes = [r["adj_close"] for r in rows]
    assert abs(closes[2] - 0.52 / F) < 1e-9             # history lifted onto the basis
    assert closes[4] == 7.20                            # post-break rows untouched
    assert max(closes) / min(closes) < 1.3              # no 13.7x cliff left in the series
    assert R.residual_cliff(rows, F) is None


def test_entries_straddling_a_break_are_left_alone(monkeypatch):
    rows = _rows([0.50, 0.51, 0.52, 0.52 / F, 7.20, 7.30])
    entries = _entries_on(rows, [0, 1, 2]) + [(rows[i]["date"], rows[i]["open"]) for i in (4, 5)]
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": entries})
    before = [r["adj_close"] for r in rows]
    assert "SYM" not in R.normalize_basis({"SYM": rows})
    assert [r["adj_close"] for r in rows] == before


def test_a_residual_cliff_reverts_the_normalization(monkeypatch):
    """Two basis breaks, but the entries' factor only explains one of them:
    whatever segment is divided, a 13.7x step remains. The series must be
    left exactly as delivered so the V0 gate refuses it loudly."""
    rows = _rows([0.50, 0.51, 0.52, 0.52 / F, 7.20, 7.20 * F, 0.53, 0.54])
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": _entries_on(rows, [0, 1, 2, 0, 1])})
    before = [r["adj_close"] for r in rows]
    applied = R.normalize_basis({"SYM": rows})
    assert "SYM" not in applied                          # two breaks: refused
    assert [r["adj_close"] for r in rows] == before
    # and the single-break path with a wrong-side result is also reverted
    rows2 = _rows([0.50, 0.51, 0.52, 0.52 / F, 7.20, 7.30, 7.25, 7.40])
    monkeypatch.setattr(R, "basis_breaks", lambda r, f: [3] if len(r) == 8 else [])
    monkeypatch.setattr(R, "residual_cliff", lambda r, f: r[3]["date"])
    before2 = [r["adj_close"] for r in rows2]
    assert "SYM" not in R.normalize_basis({"SYM": rows2})
    assert [r["adj_close"] for r in rows2] == before2


def test_whole_series_factor_still_applies_when_there_is_no_break(monkeypatch):
    rows = _rows([100.0, 101.0, 99.0, 102.0, 103.0, 101.5])
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": _entries_on(rows, range(5), 0.999)})
    applied = R.normalize_basis({"SYM": rows})
    assert applied["SYM"]["segment"] == "whole series"
    assert applied["SYM"]["rows_divided"] == len(rows)


def test_frozen_cache_ends_at_the_registered_window_end():
    """The committed cache must not run past END: with later bars present,
    round 2 graded exits outside the window and R2-A moved 6%."""
    import json

    bars = json.loads(R._input(R.BARS_CACHE).read_text())
    assert max(r["date"] for rows in bars.values() for r in rows) <= R.END
    spy = json.loads(R._input(R.SPY_RAW).read_text())["data"]
    assert max(r["t"] for r in spy) <= R.END
    sidecar = json.loads(R._input(R.BASIS_SIDECAR).read_text())
    assert sidecar["end"] == R.END
    assert sidecar["normalized"]["ATAI"]["segment"].startswith("rows before")
    atai = [r["adj_close"] for r in bars["ATAI"]]
    assert R.residual_cliff(bars["ATAI"], sidecar["normalized"]["ATAI"]["factor"]) is None
    assert max(b / a for a, b in zip(atai[:-1], atai[1:], strict=True)) < 2.0
