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


# --------------------------------------------------------------- shadow CLI

def _live_bars(n=600, end=None, seed=9):
    import time as _t
    end = int(_t.time()) if end is None else end
    ts = end - np.arange(n)[::-1] * D.BAR_SECONDS
    c = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, .01, n)))
    return {"ts": ts.astype(np.int64), "open": c, "close": c,
            "high": c * 1.004, "low": c * 0.996}


def test_gate_the_shadow_never_forecasts_a_bar_whose_answer_is_known():
    """The single easiest way for a forward record to quietly become a
    backtest: stand on an old bar whose window has already closed."""
    from research.forecast_fm import shadow_cli as C
    now = 1_800_000_000
    bars = _live_bars(end=now)
    i = C.latest_open_index(bars, D.HORIZON_BARS, now)
    assert bars["ts"][i] + D.HORIZON_BARS * D.BAR_SECONDS > now
    assert i == bars["ts"].size - 1 or \
        bars["ts"][i - 1] + D.HORIZON_BARS * D.BAR_SECONDS <= now


def test_gate_a_stale_feed_fails_loudly():
    """Every window closed means the feed stopped. Logging a forecast from
    stale bars would poison the record silently."""
    from research.forecast_fm import shadow_cli as C
    bars = _live_bars(end=1_700_000_000)
    with pytest.raises(RuntimeError, match="stale"):
        C.latest_open_index(bars, D.HORIZON_BARS, now=1_800_000_000)


def test_gate_out_of_order_bars_from_the_feed_are_refused(monkeypatch):
    from research.forecast_fm import shadow_cli as C
    import json as _j, io

    payload = [{"ts": 200, "open": 1, "high": 1, "low": 1, "close": 1},
               {"ts": 100, "open": 1, "high": 1, "low": 1, "close": 1}]

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(C.urllib.request, "urlopen",
                        lambda *a, **k: R(_j.dumps(payload).encode()))
    with pytest.raises(RuntimeError, match="out of order"):
        C.fetch_bars()


def test_gate_the_incumbent_is_always_shadowed_too():
    """The question is not 'is the model good' but 'is it better than what
    we already run'. A record of only the challengers cannot answer it."""
    from research.forecast_fm import shadow_cli as C
    bars = _live_bars(n=700)
    got = C.forecasts_at(bars, i=650, horizon=D.HORIZON_BARS)
    assert "ATR14 (incumbent)" in got
    for name, q in got.items():
        assert len(q) == 9 and np.all(np.diff(np.sort(q)) >= 0)


def test_gate_rerunning_the_same_bar_logs_nothing_twice(tmp_path, monkeypatch):
    """A timer that fires twice, or a manual run after one, must not double
    the record - duplicate forecasts at one bar would weight that bar twice
    in every score."""
    from research.forecast_fm import shadow_cli as C
    now = 1_800_000_000
    bars = _live_bars(end=now, n=700)
    monkeypatch.setattr(C, "fetch_bars", lambda **k: bars)
    monkeypatch.setattr(C.time, "time", lambda: now)
    p = str(tmp_path / "s.jsonl")
    C.main(["--log", p])
    first = len(S.load(p))
    C.main(["--log", p])
    assert first > 0 and len(S.load(p)) == first


def test_gate_the_live_spread_is_fitted_only_on_the_past():
    """Found by a surviving mutant, not by review. The shadow fits its
    quantile spread on history each run; if that fit reaches bars at or
    after the forecast bar, the LIVE record leaks the future - the one
    failure the forward shadow exists to be immune to.

    Proven by making the future violent and asserting the forecast does not
    move: a spread that saw it would widen."""
    from research.forecast_fm import shadow_cli as C
    i, n = 500, 700
    rng = np.random.default_rng(11)
    r = rng.normal(0, 0.01, n)

    calm, wild = r.copy(), r.copy()
    wild[i + 1:] = rng.normal(0, 0.20, n - i - 1)      # future only

    def mk(rr):
        c = 100 * np.exp(np.cumsum(rr))
        return {"ts": np.arange(n, dtype=np.int64) * D.BAR_SECONDS + 1_700_000_000,
                "open": c, "close": c, "high": c * 1.004, "low": c * 0.996}

    a = C.forecasts_at(mk(calm), i=i, horizon=D.HORIZON_BARS)
    b = C.forecasts_at(mk(wild), i=i, horizon=D.HORIZON_BARS)
    key = "ATR14 (incumbent)"
    assert np.allclose(a[key], b[key]), (
        "the forecast changed when only FUTURE bars changed - the spread "
        "is being fitted on data at or after the forecast bar")
