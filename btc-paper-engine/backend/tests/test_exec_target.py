"""/exec/target contract: shape, auth, and leg-state mapping."""
from fastapi.testclient import TestClient

from app.config import settings
from app.engine.core import Pending, Position
from app.live import ENGINE
from app.main import app


def test_exec_target_shape_and_states():
    with TestClient(app) as c:
        r = c.get("/exec/target")
        assert r.status_code == 200
        d = r.json()
        assert set(d) >= {"bar_ts", "price", "degraded", "data_halt",
                          "blend", "legs"}
        assert d["blend"] == {"w_trend": 0.25, "lev": 1.5}
        assert set(d["legs"]) == {"pullback", "trend"}

        # inject a pending on S3 and a trailed position on S4
        s3, s4 = ENGINE.books["S3"], ENGINE.books["S4"]
        old3, old4 = (s3.pending, s3.position), (s4.pending, s4.position)
        try:
            s3.pending = Pending(side="L", limit=59_000.0,
                                 signal_ts=1_700_000_000, atr_signal=800.0)
            s4.position = Position(side="S", entry_ts=1_700_000_000,
                                   entry_price=60_000.0, qty=1.0,
                                   notional=60_000.0, stop_price=0.0,
                                   atr_at_entry=800.0,
                                   signal_ts=1_700_000_000 - 14_400,
                                   trail=63_210.123)
            d = c.get("/exec/target").json()
            pl = d["legs"]["pullback"]
            assert pl["state"] == "PENDING"
            assert pl["pending"] == {"side": "L", "limit": 59_000.0,
                                     "signal_ts": 1_700_000_000}
            tr = d["legs"]["trend"]
            assert tr["state"] == "S"
            assert tr["position"]["stop"] == 63_210.12   # trail wins over stop_price
        finally:
            s3.pending, s3.position = old3
            s4.pending, s4.position = old4


def test_exec_target_token_auth():
    old = settings.exec_token
    try:
        settings.exec_token = "sekrit"
        with TestClient(app) as c:
            assert c.get("/exec/target").status_code == 401
            assert c.get("/exec/target",
                         headers={"X-Exec-Token": "wrong"}).status_code == 401
            assert c.get("/exec/target",
                         headers={"X-Exec-Token": "sekrit"}).status_code == 200
    finally:
        settings.exec_token = old
