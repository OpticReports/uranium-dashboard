"""The frozen-cache builder's basis normalization (scripts/refresh_backtest_bars.py).

Two defects this guards against, both seen on 2026-10-04: a constant factor
applied to a series that changes basis mid-way (FMP applied ATAI's split
factor to history only, so dividing the whole series put the post-break rows
13.7x too high and flipped a survival verdict), and a near-unity factor
(ILMN, 0.999) being mistaken for a break on every ordinary trading day.
"""
from __future__ import annotations

from scripts import refresh_backtest_bars as R


def _rows(closes: list[float], start_day: int = 1) -> list[dict]:
    out = []
    for i, c in enumerate(closes):
        d = f"2026-01-{start_day + i:02d}"
        out.append({"date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "adj_close": c})
    return out


def test_break_detected_where_the_series_jumps_by_the_factor():
    f = 0.0728
    rows = _rows([0.50, 0.51, 0.52, 0.52 / f, 7.20, 7.30])      # history at f x basis, then on basis
    assert R.basis_breaks(rows, f) == [3]


def test_near_unity_factor_never_infers_a_break():
    rows = _rows([100.0, 100.1, 99.9, 100.2, 100.0])
    assert R.basis_breaks(rows, 0.999) == []


def test_segment_normalization_divides_only_the_entries_side(monkeypatch):
    f = 0.0728
    rows = _rows([0.50, 0.51, 0.52, 0.52 / f, 7.20, 7.30, 7.25, 7.40])
    # five frozen entries, all on the history side, all at f x the lane's open
    entries = [(rows[i]["date"], rows[i]["open"] / f) for i in range(3)] + \
              [(rows[i]["date"], rows[i]["open"] / f) for i in range(2)]
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": entries})
    applied = R.normalize_basis({"SYM": rows})
    assert applied["SYM"]["segment"] == f"rows before {rows[3]['date']}"
    assert applied["SYM"]["rows_divided"] == 3
    closes = [r["adj_close"] for r in rows]
    assert abs(closes[2] - 0.52 / f) < 1e-9          # history lifted onto the basis
    assert closes[3] == 0.52 / f and closes[4] == 7.20  # post-break rows untouched
    assert max(closes) / min(closes) < 1.2            # no 13.7x cliff left in the series


def test_entries_straddling_a_break_are_left_alone(monkeypatch):
    f = 0.0728
    rows = _rows([0.50, 0.51, 0.52, 0.52 / f, 7.20, 7.30])
    entries = [(rows[i]["date"], rows[i]["open"] / f) for i in (0, 1, 2)] + \
              [(rows[i]["date"], rows[i]["open"]) for i in (4, 5)]
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": entries})
    before = [r["adj_close"] for r in rows]
    applied = R.normalize_basis({"SYM": rows})
    assert "SYM" not in applied
    assert [r["adj_close"] for r in rows] == before


def test_whole_series_factor_still_applies_when_there_is_no_break(monkeypatch):
    rows = _rows([100.0, 101.0, 99.0, 102.0, 103.0, 101.5])
    entries = [(r["date"], r["open"] / 0.999) for r in rows[:5]]
    monkeypatch.setattr(R, "frozen_entries", lambda: {"SYM": entries})
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
    assert "ATAI" in sidecar["normalized"] and sidecar["normalized"]["ATAI"]["segment"].startswith("rows before")
