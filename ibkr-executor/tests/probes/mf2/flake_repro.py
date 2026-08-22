"""Determine the MF-1 flake: CPU starvation, or structural?

Runs the EXACT body of test_gate_mf1_a_queued_kill_flatten_never_waits_for_a
_SLOW_FEED, but with the two cross-test module globals it depends on set the
way a FULL-SUITE run leaves them:
  * service.LAST["loop_ok"]  -- non-zero from an earlier test (the fixture
    clears MGR/BLEND/ADAPTER but NOT LAST), which makes the test's
    "cycle 1 complete -> the loop is parked" guard VACUOUS;
  * calls["nino"] -- pre-incremented by ONE, which is what a superseded loop
    thread from an earlier test does when it makes its last feed call into
    THIS test's monkeypatched stub.
argv[1]: 'clean' | 'stale_last' | 'preinc' | 'both'
"""
import sys, threading, time, os
sys.path.insert(0, ".")

MODE = sys.argv[1] if len(sys.argv) > 1 else "clean"
tmp = sys.argv[2]

from app.config import settings
from app import service
from app.service import app as service_app
from fastapi.testclient import TestClient
from app import blend as blend_mod

FEED_HANG = 6.0
release = threading.Event()
calls = {"nino": 0, "intents": 0}

def _hang(which):
    calls[which] += 1
    if calls[which] > 1:
        release.wait(FEED_HANG)

def slow_nino():
    _hang("nino"); return 2.7

def slow_intents(_cfg):
    _hang("intents"); return None

settings.state_path = os.path.join(tmp, "s.json")
settings.blend_state_path = os.path.join(tmp, "b.json")
settings.exec_token = "sekrit"
settings.tws_userid = ""
settings.blend_enabled = True
service.nino34_weekly = slow_nino
blend_mod.fetch_intents = slow_intents
service.ADAPTER = None; service.BLEND = None; service.MGR = None

if MODE in ("stale_last", "both"):
    service.LAST["loop_ok"] = time.time() - 1.0   # earlier test's timestamp
else:
    service.LAST["loop_ok"] = 0.0
if MODE in ("preinc", "both"):
    calls["nino"] = 1        # a superseded loop's last call landed here
if MODE == "stale_last_slow":
    # the kill lands while iteration 1 is STILL RUNNING (its last blend
    # cycle), which the vacuous loop_ok guard permits
    service.LAST["loop_ok"] = time.time() - 1.0
    from app import blend as _bm
    _real = _bm.run_cycle
    _seen = {"n": 0}
    def _slow(*a, **k):
        _seen["n"] += 1
        if _seen["n"] == 1:
            time.sleep(2.0)
        return _real(*a, **k)
    _bm.run_cycle = _slow

def _wait_until(fn, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fn():
            return True
        time.sleep(0.01)
    return False

def seed(B, A):
    B.state.initialized = True
    B.state.sleeve_cash = 2750.0
    B.state.spy_qty = 70
    B.on_entered({"call_id": 1, "symbol": "CRSP", "qty": 5,
                  "entry_ref": 50.0, "stop_level": 44.0}, 50.0,
                 "entry-ref", "2026-08-01")
    rs = A.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                             client_order_id="blend-1-stp-44.0000")
    B.state.positions["1"].stop_order_ref = rs["order_ref"]
    B.save()

client = TestClient(service_app)
out = {}
try:
    with client as c:
        for _ in range(200):
            if service.BLEND is not None and service.ADAPTER is not None:
                break
            time.sleep(0.05)
        B, A = service.BLEND, service.ADAPTER
        g1 = _wait_until(lambda: service.LAST["loop_ok"] > 0)
        g2 = _wait_until(lambda: calls["nino"] >= 1)
        seed(B, A)
        t0 = time.time()
        r = c.get("/kill", params={"token": "sekrit"})
        done = _wait_until(lambda: B.state.flatten_request is None
                           and B.state.positions == {}, timeout=20.0)
        latency = time.time() - t0
        out = {"mode": MODE, "guard_loop_ok": g1, "guard_nino": g2,
               "flatten_done": done, "latency": round(latency, 3),
               "assert_lt": FEED_HANG / 2,
               "PASSES": bool(done and latency < FEED_HANG / 2),
               "nino_calls": calls["nino"]}
finally:
    release.set()
    service.BLEND = None; service.MGR = None
out["nino_after_lifespan"] = calls["nino"]
out["FINAL_TEST_PASSES"] = bool(out.get("PASSES") and calls["nino"] >= 2)
print("RESULT", out)
