"""Vol-targeted entry size (app/volsize.py, RESEARCH_SHARPE.md H1 down-only).

The live multiplier must equal the backtest's: research/sharpe/sharpe_lib.py
computes it with pandas rolling windows over contiguous Bitstamp bars; this
re-derives it the same way here and demands equality on the repo fixture."""
import csv
import math
import os

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import volsize as V

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "bars_4h_btcusd.csv")
ROWS = list(csv.DictReader(open(FIX)))
TS = [int(r["ts_open_unix"]) for r in ROWS]
CL = [float(r["close"]) for r in ROWS]
CLOSES = dict(zip(TS, CL))


def _research_m(j):
    """sharpe_lib.World: lr -> rolling(180).std(ddof=0) -> rolling(2190)
    .median(); m for an entry on bar j+1 uses index j (the signal bar)."""
    c = np.array(CL)
    lr = np.full(len(c), np.nan)
    lr[1:] = np.diff(np.log(c))
    s_now = pd.Series(lr).rolling(V.VOL_WIN).std(ddof=0)
    s_ref = s_now.rolling(V.VOL_REF).median()
    a, b = s_ref.iloc[j], s_now.iloc[j]
    return min(V.M_HI, max(V.M_LO, a / b))


@pytest.mark.parametrize("j", [2400, 3100, 4777, 6000, 8123, len(TS) - 1])
def test_matches_the_backtest_formula_exactly(j):
    got = V.size_mult(CLOSES, TS[j])
    assert got["basis"] == "vol_target"
    assert got["m"] == pytest.approx(_research_m(j), abs=1e-4)
    assert V.M_LO <= got["m"] <= V.M_HI


def test_both_regimes_occur_on_the_fixture():
    ms = [V.size_mult(CLOSES, TS[j])["m"] for j in range(2400, len(TS), 97)]
    assert min(ms) < 0.9 and max(ms) == 1.0      # it does shrink, and caps at 1


def test_only_bars_at_or_before_the_signal_bar_matter():
    j = 5000
    base = V.size_mult(CLOSES, TS[j])
    future = dict(CLOSES)
    for t in TS[j + 1:j + 50]:
        future[t] *= 3.0
    assert V.size_mult(future, TS[j]) == base
    moved = dict(CLOSES)
    moved[TS[j]] *= 1.2                           # the signal bar's own close counts
    assert V.size_mult(moved, TS[j])["sigma_now"] != base["sigma_now"]


def test_short_history_falls_back_to_todays_size():
    got = V.size_mult(CLOSES, TS[1000])           # < 2,370 bars behind it
    assert got == {"m": 1.0, "basis": "insufficient_history",
                   "sigma_now": got["sigma_now"], "sigma_ref": None}
    assert V.size_mult(CLOSES, None)["m"] == 1.0
    assert V.size_mult(CLOSES, 123)["m"] == 1.0   # unknown bar


def test_a_few_missing_bars_still_compute_many_do_not():
    j = 6000
    few = dict(CLOSES)
    for t in TS[j - 40:j - 35]:
        del few[t]
    assert V.size_mult(few, TS[j])["basis"] == "vol_target"
    many = dict(CLOSES)
    for t in TS[j - 400:j - 100]:
        del many[t]
    got = V.size_mult(many, TS[j])
    assert got["basis"] == "insufficient_history" and got["m"] == 1.0  # ref window <90% valid
    hole = dict(CLOSES)
    for t in TS[j - 100:j]:                       # sigma_now window mostly gone
        del hole[t]
    assert V.size_mult(hole, TS[j])["m"] == 1.0


def test_exec_target_publishes_a_leg_level_size_mult(monkeypatch):
    from app.config import settings
    from app.engine.core import Pending
    monkeypatch.setattr(settings, "run_engine", False)
    monkeypatch.setattr(settings, "run_funding_monitor", False)
    from app.live import ENGINE
    from app.main import app
    ENGINE.booted = True
    s3, s4 = ENGINE.books["S3"], ENGINE.books["S4"]
    old3 = (s3.pending, s3.position, s3.halted)
    old4 = (s4.pending, s4.position, s4.halted)
    oldv = (ENGINE._vol_closes, ENGINE._vol_key, dict(ENGINE._vol_cache))
    try:
        s3.position, s3.halted = None, False
        s4.pending, s4.position, s4.halted = None, None, False
        s3.pending = Pending(side="L", limit=59_000.0, signal_ts=TS[6000],
                             atr_signal=800.0)
        ENGINE._vol_closes, ENGINE._vol_key = CLOSES, ENGINE.last_processed
        ENGINE._vol_cache = {}
        with TestClient(app) as c:
            d = c.get("/exec/target").json()
        pl, tr = d["legs"]["pullback"], d["legs"]["trend"]
        assert pl["size_mult"] == V.size_mult(CLOSES, TS[6000])["m"]
        assert pl["size_mult_basis"] == "vol_target"
        assert pl["pending"] == {"side": "L", "limit": 59_000.0,
                                 "signal_ts": TS[6000]}   # shape unchanged
        assert tr["size_mult"] == 1.0 and tr["size_mult_basis"] == "no_signal"
    finally:
        s3.pending, s3.position, s3.halted = old3
        s4.pending, s4.position, s4.halted = old4
        ENGINE._vol_closes, ENGINE._vol_key, ENGINE._vol_cache = oldv
