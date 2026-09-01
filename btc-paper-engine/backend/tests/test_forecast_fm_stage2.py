"""Stage 2 gates: the adapter contract and the forward shadow record.

No torch, no weights, no network. A FakeAdapter stands in for Chronos-2 and
TimesFM-3 so the plumbing every real adapter inherits is gated here rather
than discovered on a box that has the weights.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from research.forecast_fm import data as D
from research.forecast_fm import fm as FM
from research.forecast_fm import shadow as S


class FakeAdapter(FM._HFAdapter):
    """Records the context it was handed, so a test can prove what the
    adapter could and could not see."""

    name = "Fake"

    def __init__(self, context=512):
        self.context = context
        self.seen = []

    def _forecast(self, ctx_batch, horizon):
        self.seen.extend([np.array(c) for c in ctx_batch])
        return [np.full(horizon, float(np.mean(c))) for c in ctx_batch]


def _series(n=2000, seed=3):
    rng = np.random.default_rng(seed)
    return np.abs(rng.normal(0.01, 0.003, n))


# ------------------------------------------------------------------ adapter

def test_gate_an_adapter_never_sees_past_its_own_index():
    """THE test in this file. An adapter that reads one bar beyond its
    index is reading the answer, and every number the study produces after
    that is fiction. Proven by planting an unmistakable value in the future
    and asserting it never appears in any context handed to the model."""
    s = _series()
    marker = 999.0
    idx = np.array([600, 900, 1200])
    s[idx.max() + 1:] = marker              # everything after the last index
    a = FakeAdapter()
    a.predict_sigma(s, idx, horizon=8)
    for ctx in a.seen:
        assert not np.any(ctx == marker), "the adapter saw a future bar"


def test_gate_the_context_includes_the_index_bar_itself():
    """The mirror of the above: data up to and INCLUDING t is legitimate,
    and an adapter that dropped it would be handicapped, not safe."""
    s = _series()
    s[900] = 0.5
    a = FakeAdapter()
    a.predict_sigma(s, np.array([900]), horizon=8)
    assert any(np.any(c == 0.5) for c in a.seen)


def test_gate_every_forecast_gets_the_same_context_length():
    """A forecast late in the sample must not get a 10,000-point history
    while an early one gets 200: a difference in context is a difference in
    model, and it would confound the comparison across the sample."""
    a = FakeAdapter(context=256)
    a.predict_sigma(_series(), np.array([400, 800, 1500]), horizon=8)
    assert {c.size for c in a.seen} == {256}


def test_gate_the_window_forecast_aggregates_variance_not_volatility():
    """Volatility does not add over a window; variance does. RMS of the
    path, never the mean."""
    path = np.array([0.01, 0.03])
    assert FM._rms(path) == pytest.approx(np.sqrt((0.0001 + 0.0009) / 2))
    assert FM._rms(path) > path.mean()


def test_gate_the_models_are_fed_range_data_not_closes():
    """Stage 1a finding 2: the same recursion on closes was 3.6% worse.
    Feeding these models closes would measure that handicap and report it
    as a model result."""
    bars = {"high": np.array([110.0, 101.0]), "low": np.array([90.0, 99.0]),
            "close": np.array([100.0, 100.0])}
    s = FM.input_series(bars)
    assert s[0] > s[1], "a wide bar must read as more volatile than a tight one"


def test_gate_a_missing_model_is_named_not_silently_skipped(capsys, monkeypatch):
    """A bake-off that quietly ran fewer models than it printed would be
    worse than one that failed."""
    def boom(self, device="cpu"):
        raise FM.AdapterUnavailable("install the thing")
    monkeypatch.setattr(FM.Chronos2, "__init__", boom)
    monkeypatch.setattr(FM.TimesFM3, "__init__", boom)
    assert FM.available() == []
    assert "SKIPPED" in capsys.readouterr().out


# ------------------------------------------------------------------- shadow

def _q(base=0.01):
    return np.array([base * (0.6 + 0.1 * i) for i in range(9)])


def test_gate_the_shadow_log_is_append_only(tmp_path):
    p = str(tmp_path / "s.jsonl")
    S.append_forecast(p, "m", 1_700_000_000, _q())
    S.append_forecast(p, "m", 1_700_100_000, _q())
    assert len(S.load(p)) == 2


def test_gate_a_forecast_cannot_choose_when_it_resolves(tmp_path):
    """A caller that could set its own resolve time could pick the window
    that flattered it. ts_resolve is derived from the horizon."""
    p = str(tmp_path / "s.jsonl")
    r = S.append_forecast(p, "m", 1_700_000_000, _q(), horizon=8)
    assert r["ts_resolve"] == 1_700_000_000 + 8 * D.BAR_SECONDS


def test_gate_non_monotonic_quantiles_are_refused(tmp_path):
    """q90 below q10 is not a forecast, it is a bug that would score well
    on coverage by accident."""
    p = str(tmp_path / "s.jsonl")
    bad = _q()[::-1]
    with pytest.raises(ValueError, match="monotonic"):
        S.append_forecast(p, "m", 1_700_000_000, bad)


def test_gate_a_window_that_has_not_closed_is_not_scored(tmp_path):
    """A partially observed window cannot yet contain its own worst move,
    so scoring it early would systematically understate realized vol."""
    n = 400
    ts = np.arange(n, dtype=np.int64) * D.BAR_SECONDS + 1_700_000_000
    c = 100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0, .01, n)))
    bars = {"ts": ts, "close": c, "high": c * 1.002, "low": c * .998}
    p = str(tmp_path / "s.jsonl")
    made = int(ts[100])
    S.append_forecast(p, "m", made, _q())
    assert S.resolve(p, bars, now=made + 4 * D.BAR_SECONDS) == 0   # mid-window
    assert S.resolve(p, bars, now=made + 8 * D.BAR_SECONDS) == 1   # closed
    assert S.load(p)[0]["y"] is not None


def test_gate_resolving_never_edits_the_forecast(tmp_path):
    """'We would have predicted that' is the easiest lie a study tells
    itself."""
    n = 400
    ts = np.arange(n, dtype=np.int64) * D.BAR_SECONDS + 1_700_000_000
    c = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, .01, n)))
    bars = {"ts": ts, "close": c, "high": c * 1.002, "low": c * .998}
    p = str(tmp_path / "s.jsonl")
    made = int(ts[50])
    before = S.append_forecast(p, "m", made, _q())
    S.resolve(p, bars, now=made + 99 * D.BAR_SECONDS)
    after = S.load(p)[0]
    assert after["q"] == before["q"] and after["ts_made"] == before["ts_made"]


def test_gate_unresolved_forecasts_are_counted_not_dropped(tmp_path):
    """A model whose forecasts mostly never resolve must not look good on
    the handful that did."""
    n = 400
    ts = np.arange(n, dtype=np.int64) * D.BAR_SECONDS + 1_700_000_000
    c = 100 * np.exp(np.cumsum(np.random.default_rng(2).normal(0, .01, n)))
    bars = {"ts": ts, "close": c, "high": c * 1.002, "low": c * .998}
    p = str(tmp_path / "s.jsonl")
    S.append_forecast(p, "m", int(ts[50]), _q())
    S.append_forecast(p, "m", int(ts[300]), _q())
    S.resolve(p, bars, now=int(ts[100]))
    out = S.score(p)
    assert out["n"] == 1 and out["pending"] == 1


def test_gate_the_schema_survives_a_round_trip(tmp_path):
    p = str(tmp_path / "s.jsonl")
    S.append_forecast(p, "Chronos-2", 1_700_000_000, _q())
    row = json.loads(open(p).read().strip())
    assert row["model"] == "Chronos-2" and len(row["q"]) == 9
    assert row["schema"] == S.SCHEMA and row["y"] is None
