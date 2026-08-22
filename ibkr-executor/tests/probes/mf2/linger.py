"""Can a loop thread from an EARLIER lifespan outlive _stop_loop's 1.0s join
and then make ONE more call into a LATER test's monkeypatched
service.nino34_weekly?  That single call is the pre-increment the MF-1 gate
needs to fail structurally."""
import sys, threading, time, os
sys.path.insert(0, ".")
from app.config import settings
from app import service
from app.service import app as service_app
from app import blend as blend_mod
from fastapi.testclient import TestClient

tmp = sys.argv[1]
settings.state_path = os.path.join(tmp, "s.json")
settings.blend_state_path = os.path.join(tmp, "b.json")
settings.exec_token = "sekrit"
settings.tws_userid = ""
settings.blend_enabled = True
settings.poll_seconds = 300
service.ADAPTER = None; service.BLEND = None; service.MGR = None

# LIFESPAN 1: its blend cycle is slow, so the loop is BUSY (not parked) when
# the lifespan exits -- exactly what a CPU-starved full-suite run produces.
gate = threading.Event()
real_run = blend_mod.run_cycle
def slow_cycle(*a, **k):
    gate.wait(2.5)                       # busy through _stop_loop's join
    return real_run(*a, **k)
blend_mod.run_cycle = slow_cycle
service.nino34_weekly = lambda: 2.7

c1 = TestClient(service_app)
with c1:
    for _ in range(200):
        if service.BLEND is not None:
            break
        time.sleep(0.02)
    time.sleep(0.3)
# lifespan 1 is OVER.  _stop_loop joined 1.0s and gave up.
alive = [t.name for t in threading.enumerate() if t.name.startswith("exec-loop")]
print("after lifespan-1 exit, loop threads alive:", alive)

# The next test installs ITS stub now:
calls = {"nino": 0}
def stub():
    calls["nino"] += 1
    return 2.7
service.nino34_weekly = stub
blend_mod.run_cycle = real_run
gate.set()                                # let the stale cycle finish
time.sleep(2.0)
print("RESULT stale_loop_calls_into_next_tests_stub =", calls["nino"],
      "| still alive:", [t.name for t in threading.enumerate()
                         if t.name.startswith("exec-loop")])
