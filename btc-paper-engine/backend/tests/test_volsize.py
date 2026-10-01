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
    .median(); m for an entry on bar j+1 uses index j (the signal bar).
    The constants are LITERALS, not V.*: a reference that reads the module
    under test follows a mutated constant (review 2026-10-01 M3)."""
    c = np.array(CL)
    lr = np.full(len(c), np.nan)
    lr[1:] = np.diff(np.log(c))
    s_now = pd.Series(lr).rolling(180).std(ddof=0)
    s_ref = s_now.rolling(2190).median()
    a, b = s_ref.iloc[j], s_now.iloc[j]
    return min(1.0, max(0.5, a / b))


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


def test_registered_constants_are_pinned():
    assert (V.VOL_WIN, V.VOL_REF, V.M_LO, V.M_HI) == (180, 2190, 0.5, 1.0)


def test_lower_clip_binds_on_a_volatility_spike():
    """The fixture's minimum ratio is 0.556, so the 0.5 floor never binds
    there (review M3). Inject a spike into the last 180 bars."""
    j = 6000
    spiky = dict(CLOSES)
    for k, t in enumerate(TS[j - 179:j + 1]):
        spiky[t] = CLOSES[t] * (1.08 if k % 2 else 0.93)
    got = V.size_mult(spiky, TS[j])
    assert got["basis"] == "vol_target" and got["m"] == 0.5


def _engine_target(monkeypatch, s3pend=None, s4pos=None):
    from app.config import settings
    from app.live import ENGINE
    from app.main import app
    monkeypatch.setattr(settings, "run_engine", False)
    monkeypatch.setattr(settings, "run_funding_monitor", False)
    ENGINE.booted = True
    s3, s4 = ENGINE.books["S3"], ENGINE.books["S4"]
    old = ((s3.pending, s3.position, s3.halted), (s4.pending, s4.position, s4.halted),
           (ENGINE._vol_closes, ENGINE._vol_key, dict(ENGINE._vol_cache)))
    try:
        s3.pending, s3.position, s3.halted = s3pend, None, False
        s4.pending, s4.position, s4.halted = None, s4pos, False
        with TestClient(app) as c:
            return c.get("/exec/target")
    finally:
        (s3.pending, s3.position, s3.halted) = old[0]
        (s4.pending, s4.position, s4.halted) = old[1]
        ENGINE._vol_closes, ENGINE._vol_key, ENGINE._vol_cache = old[2]


def test_position_path_is_keyed_on_the_signal_bar(monkeypatch):
    """Mutation (d) - position keyed on entry_ts - survived (review M3)."""
    from app.engine.core import Position
    from app.live import ENGINE
    ENGINE._vol_closes, ENGINE._vol_key = CLOSES, ENGINE.last_processed
    ENGINE._vol_cache = {}
    pos = Position(side="L", entry_ts=TS[6001], entry_price=60_000.0, qty=1.0,
                   notional=60_000.0, stop_price=0.0, atr_at_entry=800.0,
                   signal_ts=TS[6000])
    r = _engine_target(monkeypatch, s4pos=pos)
    tr = r.json()["legs"]["trend"]
    assert tr["size_mult"] == V.size_mult(CLOSES, TS[6000])["m"]
    assert tr["size_mult"] != V.size_mult(CLOSES, TS[6001])["m"]


def test_vol_history_reads_the_real_fixture(monkeypatch):
    """_vol_history was bypassed by every test (review M3). Through it, from
    a cold cache, m matches the pure function on the fixture."""
    from app.live import ENGINE
    monkeypatch.setattr(ENGINE, "last_processed", TS[6000])
    ENGINE._vol_closes, ENGINE._vol_key, ENGINE._vol_cache = {}, None, {}
    got = ENGINE.size_mult_for(TS[6000])
    assert got["basis"] == "vol_target"
    assert got["m"] == V.size_mult(CLOSES, TS[6000])["m"]
    assert max(ENGINE._vol_closes) <= TS[6000]           # nothing newer


def test_a_pending_older_than_last_processed_is_not_starved(monkeypatch):
    """Review M1: a pending created just before last_processed advances must
    still see its own signal bar."""
    from app.live import ENGINE
    monkeypatch.setattr(ENGINE, "last_processed", TS[5999])   # not yet advanced
    ENGINE._vol_closes, ENGINE._vol_key, ENGINE._vol_cache = {}, None, {}
    got = ENGINE.size_mult_for(TS[6000])
    assert got["basis"] == "vol_target"


def test_an_exception_fails_to_todays_size_not_a_500(monkeypatch):
    """Review S1: a DB error inside vol sizing returned 500 from
    /exec/target, and the executor skips its whole step on a failed fetch."""
    from app import live
    from app.engine.core import Pending
    from app.live import ENGINE

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(live, "size_mult", boom)
    ENGINE._vol_cache = {}
    r = _engine_target(monkeypatch, s3pend=Pending(
        side="L", limit=59_000.0, signal_ts=TS[6000], atr_signal=800.0))
    assert r.status_code == 200
    pl = r.json()["legs"]["pullback"]
    assert pl["size_mult"] == 1.0 and pl["size_mult_basis"] == "error"
