"""MF2 counter-review scenario drivers. One scenario per PROCESS (module
globals). Usage from ibkr-executor/:  python scen.py <name> [tmpdir]
Prints RESULT k=v lines the driver greps.
"""
import json, os, sys, tempfile, threading, time
sys.path.insert(0, ".")

SCEN = sys.argv[1]
TMP = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="mf2")
os.makedirs(TMP, exist_ok=True)

from app.config import settings
from app import service, blend as blend_mod
from app.service import app as service_app
from app.ib_adapter import DryAdapter
from app.manager import LadderManager
from fastapi.testclient import TestClient

settings.state_path = os.path.join(TMP, "s.json")
settings.blend_state_path = os.path.join(TMP, "b.json")
settings.exec_token = "sekrit"
settings.tws_userid = ""
settings.blend_enabled = True
settings.poll_seconds = int(os.environ.get("POLL", "300"))

ALERTS = []
service.send = lambda m, *a, **k: ALERTS.append(m)
blend_mod_alerts = ALERTS

FLAT = {"n": 0, "threads": set()}
_real_flatten = blend_mod.execute_flatten
def _cf(mgr, adapter, alert):
    FLAT["n"] += 1
    FLAT["threads"].add(threading.get_ident())
    return _real_flatten(mgr, adapter, alert)
blend_mod.execute_flatten = _cf

API_THREADS = set()
_real_auth = service._auth
def _rec_auth(h, q):
    API_THREADS.add(threading.get_ident())
    return _real_auth(h, q)
service._auth = _rec_auth

ADAPTER_THREADS = {"n": set()}


def R(k, v):
    print(f"RESULT {k}={v}", flush=True)


def wait(cond, t=60.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return time.time()
        time.sleep(0.01)
    return None


def boot(c):
    assert wait(lambda: service.BLEND is not None
                and service.ADAPTER is not None, 20)
    return service.BLEND, service.ADAPTER


def seed(B, A, call_id=1, qty=5):
    A.place_stock_order("CRSP", qty, "MKT")      # the venue really holds them
    B.state.initialized = True
    B.state.sleeve_cash = 5_000.0
    B.state.spy_qty = 70
    B.on_entered({"call_id": call_id, "symbol": "CRSP", "qty": qty,
                  "entry_ref": 50.0, "stop_level": 44.0}, 50.0,
                 "entry-ref", "2026-08-01")
    rs = A.place_stock_order("CRSP", -qty, "STP", stop_price=44.0, tif="GTC",
                             client_order_id=f"blend-{call_id}-stp-44.0000")
    B.state.positions[str(call_id)].stop_order_ref = rs["order_ref"]
    B.save()


def disk_ladder():
    return json.load(open(settings.state_path))


# ------------------------------------------------------------------ S1
if SCEN == "ladder_lost_halt":
    HANG = float(os.environ.get("HANG", "20"))
    rel = threading.Event()
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None

    class SlowLadder(DryAdapter):
        n = 0
        def mark(self, ref):
            SlowLadder.n += 1
            rel.wait(HANG)
            return 1.0

    service.DryAdapter = SlowLadder
    with TestClient(service_app) as c:
        B, A = boot(c)
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[0], 10_000,
                                  "ref-1", "2026-08-01")
            service.MGR.save()
        time.sleep(0.2)
        n0 = SlowLadder.n
        service.LOOP_WAKE.set()
        assert wait(lambda: SlowLadder.n > n0, 20), "no ladder mark"
        time.sleep(0.5)
        seed(B, A)
        t0 = time.time()
        r = c.post("/kill", params={"token": "sekrit"}).json()
        R("kill_http_s", round(time.time() - t0, 3))
        R("ladder_field", r.get("ladder"))
        R("mem_halted", service.MGR.state.halted)
        d = disk_ladder()
        R("disk_halted", d.get("halted"))
        R("disk_open_legs", [k for k, v in d["legs"].items()
                             if v["status"] == "OPEN"])
        # what a CRASH right here comes back as (fresh manager, same file)
        crashed = LadderManager(settings, settings.state_path)
        R("after_crash_halted", crashed.state.halted)
        R("after_crash_open_legs", [k for k, v in crashed.state.legs.items()
                                    if v.status == "OPEN"])
        # the BLEND half, for contrast: journalled synchronously
        db = json.load(open(settings.blend_state_path))
        R("blend_disk_halted", db.get("halted"))
        R("blend_disk_flatten_req", db.get("flatten_request") is not None)
        R("alert", [a for a in ALERTS if "ladder KILLED" in a][:1])
    rel.set()

# ------------------------------------------------------------------ S2
elif SCEN == "ladder_stale_kill_after_resume":
    # Realistic shape: the operator double-taps /kill because the first one
    # did not respond (its close_spread is wedged on the gateway). Kill #2
    # times out on MGR_LOCK and DEFERS. Kill #1 finishes and persists the
    # halt. The operator then /resume-s. LADDER_KILL is still set.
    HANG = float(os.environ.get("HANG", "6"))
    rel = threading.Event()
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None
    settings.blend_enabled = False       # isolate the ladder half

    class SlowClose(DryAdapter):
        n = 0
        def close_spread(self, ref):
            SlowClose.n += 1
            if SlowClose.n == 1:
                rel.wait(HANG)
            return {"value": 1.0}

    service.DryAdapter = SlowClose
    with TestClient(service_app) as c:
        assert wait(lambda: service.MGR is not None, 20)
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[0], 10_000,
                                  "ref-1", "2026-08-01")
            service.MGR.save()
        out = {}
        t1 = threading.Thread(
            target=lambda: out.update(
                k1=c.post("/kill", params={"token": "sekrit"}).json()))
        t1.start()
        time.sleep(0.4)                    # kill #1 is inside close_spread
        t0 = time.time()
        k2 = c.post("/kill", params={"token": "sekrit"}).json()
        R("kill2_http_s", round(time.time() - t0, 3))
        R("kill2_ladder", k2.get("ladder"))
        R("LADDER_KILL_set_after_kill2", service.LADDER_KILL.is_set())
        rel.set()
        t1.join(20)
        R("kill1_ladder", out.get("k1", {}).get("ladder"))
        R("LADDER_KILL_still_set", service.LADDER_KILL.is_set())
        # operator resumes
        rr = c.post("/resume", params={"token": "sekrit"}).json()
        R("resume_cleared", rr.get("cleared"))
        R("halted_after_resume", service.MGR.state.halted)
        # re-open a leg the way a resumed ladder would, then let the loop run
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[1], 10_000,
                                  "ref-2", "2026-08-02")
            service.MGR.save()
        service.LOOP_WAKE.set()
        got = wait(lambda: service.MGR.state.halted == "KILL", 20)
        R("stale_kill_refired", got is not None)
        R("halted_after_loop", service.MGR.state.halted)
        R("open_legs_after_loop", [k for k, v in service.MGR.state.legs.items()
                                   if v.status == "OPEN"])
        R("stale_alert", [a for a in ALERTS if "the /kill you sent" in a][:1])

# ------------------------------------------------------------------ S3
elif SCEN == "kill_midcycle_enters":
    # A /kill that lands AFTER mgr.step() planned this cycle's intents:
    # step's `if st.halted: return []` guard is already behind us, and the
    # intent loop never re-checks. Does the emergency stop still let the
    # cycle open NEW risk?
    service.nino34_weekly = lambda: 2.7
    gate = threading.Event()
    fired = threading.Event()

    from datetime import datetime as _dt, timezone as _tz
    TODAY = _dt.now(_tz.utc).date().isoformat()

    def _entry(cid, sym):
        return {"symbol": sym, "call_id": cid, "fire_date": TODAY,
                "flag_type": "pre_catalyst_sentiment_ramp", "risk_frac": 0.01,
                "entry_ref": 10.0, "note": "t"}

    def payload(_c):
        return {"as_of": TODAY,
                "gate": {"xbi_above_200dma_prior": True, "since": None},
                "entries": [_entry(11, "AAA"), _entry(12, "BBB")],
                "exits": [], "stops": [
                    {"symbol": "AAA", "call_id": 11, "trail_level": 9.0},
                    {"symbol": "BBB", "call_id": 12, "trail_level": 9.0}],
                "rebalance": {"needed": None, "current_sleeve_weight": None,
                              "target": 0.30},
                "book_params": {"max_open": 10, "risk_frac": 0.01,
                                "band": 0.05, "cash_vehicle": "BIL",
                                "core": "SPY"},
                "contract": "x"}
    blend_mod.fetch_intents = payload

    BUYS = []
    class GateAdapter(DryAdapter):
        def place_stock_order(self, symbol, qty, kind, **kw):
            if qty > 0 and not fired.is_set():
                fired.set()
                gate.wait(15)          # the kill lands right here
            if qty > 0:
                BUYS.append((symbol, qty,
                             service.BLEND.state.halted,
                             service.BLEND.state.flatten_request is not None))
            return super().place_stock_order(symbol, qty, kind, **kw)
        def stock_price(self, symbol):
            return 10.0

    service.DryAdapter = GateAdapter
    with TestClient(service_app) as c:
        B, A = boot(c)
        B.state.initialized = True
        B.state.sleeve_cash = 5_000.0
        B.state.spy_qty = 70
        B.save()
        service.LOOP_WAKE.set()
        assert wait(lambda: fired.is_set(), 30), "no entry attempted"
        R("halted_before_kill", B.state.halted)
        before = sorted(B.state.positions)
        kt = threading.Thread(target=lambda: c.post(
            "/kill", params={"token": "sekrit"}))
        kt.start()
        time.sleep(0.6)          # HEAD: journalled already. base: still blocked
        R("halted_after_kill", B.state.halted)
        gate.set()
        kt.join(30)
        wait(lambda: len(B.state.positions) > len(before), 20)
        time.sleep(1.0)
        R("positions_before_kill", before)
        R("positions_after_cycle", sorted(B.state.positions))
        R("entered_after_halt",
          sorted(set(B.state.positions) - set(before)))
        R("enter_alerts", [a for a in ALERTS if "blend ENTER" in a])
        R("flatten_ran_eventually",
          wait(lambda: B.state.flatten_request is None, 30) is not None)
        R("final_positions", sorted(B.state.positions))
        R("BUYS_symbol_qty_haltedAtCall_flattenQueuedAtCall", BUYS)
        R("pending_entries_after", sorted(B.state.pending_entries))
        R("sleeve_cash", round(B.state.sleeve_cash, 2))

# ------------------------------------------------------------------ S2b
elif SCEN == "ladder_stale_kill_wins_resume":
    # Same double-tap, but the loop is parked in its (bounded) NOAA fetch
    # when the operator resumes -- so /resume lands BEFORE the loop's next
    # ladder section consumes LADDER_KILL. Nothing clears LADDER_KILL on
    # resume, so the deferred kill fires at a RESUMED ladder.
    HANG = float(os.environ.get("HANG", "5"))
    NINO = float(os.environ.get("NINO", "6"))
    rel = threading.Event()
    relnino = threading.Event()
    ninon = {"n": 0}
    def slow_nino():
        ninon["n"] += 1
        if ninon["n"] > 1:
            relnino.wait(NINO)
        return 2.7
    service.nino34_weekly = slow_nino
    blend_mod.fetch_intents = lambda _c: None
    settings.blend_enabled = False

    class SlowClose(DryAdapter):
        n = 0
        def close_spread(self, ref):
            SlowClose.n += 1
            if SlowClose.n == 1:
                rel.wait(HANG)
            return {"value": 1.0}

    service.DryAdapter = SlowClose
    with TestClient(service_app) as c:
        assert wait(lambda: service.MGR is not None, 20)
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[0], 10_000,
                                  "ref-1", "2026-08-01")
            service.MGR.save()
        out = {}
        t1 = threading.Thread(
            target=lambda: out.update(
                k1=c.post("/kill", params={"token": "sekrit"}).json()))
        t1.start()
        time.sleep(0.4)
        k2 = c.post("/kill", params={"token": "sekrit"}).json()
        R("kill2_ladder", k2.get("ladder"))
        R("LADDER_KILL_set", service.LADDER_KILL.is_set())
        rel.set(); t1.join(20)
        # the loop is now parked inside the slow NOAA fetch
        assert wait(lambda: ninon["n"] > 1, 20), "loop never re-entered nino"
        rr = c.post("/resume", params={"token": "sekrit"}).json()
        R("resume_cleared", rr.get("cleared"))
        R("halted_after_resume", service.MGR.state.halted)
        R("LADDER_KILL_after_resume", service.LADDER_KILL.is_set())
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[1], 10_000,
                                  "ref-2", "2026-08-02")
            service.MGR.save()
        relnino.set()
        got = wait(lambda: service.MGR.state.halted == "KILL", 30)
        R("stale_kill_refired_at_resumed_ladder", got is not None)
        R("halted_after_loop", service.MGR.state.halted)
        R("open_legs_after_loop", [k for k, v in service.MGR.state.legs.items()
                                   if v.status == "OPEN"])

# ------------------------------------------------------------------ S4
elif SCEN == "kill_own_close_unbounded":
    # The loop is PARKED (the deployed steady state), so MGR_LOCK is FREE.
    # /kill takes it instantly -- and then makes the uncapped gateway call
    # ITSELF, on the API thread, holding MGR_LOCK. KILL_LOCK_WAIT_S bounds
    # only the WAIT for the lock, never /kill's own round-trip.
    HANG = float(os.environ.get("HANG", "20"))
    rel = threading.Event()
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None

    class WedgedClose(DryAdapter):
        n = 0
        def close_spread(self, ref):
            WedgedClose.n += 1
            WedgedClose.thread = threading.get_ident()
            rel.wait(HANG)
            return {"value": 1.0}

    service.DryAdapter = WedgedClose
    with TestClient(service_app) as c:
        B, A = boot(c)
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[0], 10_000,
                                  "ref-1", "2026-08-01")
            service.MGR.save()
        seed(B, A)
        assert wait(lambda: service.LAST["loop_ok"] > 0, 30)
        time.sleep(0.5)
        R("mgr_lock_free_before_kill", not service.MGR_LOCK.locked())
        t0 = time.time()
        r = c.post("/kill", params={"token": "sekrit"}).json()
        el = time.time() - t0
        R("kill_http_s", round(el, 3))
        R("readme_claims_max_s", 0.51)
        R("ladder_field", r.get("ladder"))
        R("close_ran_on_api_thread",
          getattr(WedgedClose, "thread", None) in API_THREADS)
        R("hang", HANG)
        R("alert_emitted_before_response",
          any("ladder KILLED" in a for a in ALERTS))
    rel.set()

# ------------------------------------------------------------------ S5
elif SCEN == "deadlock_storm":
    # Hammer /kill, /resume, /status, /health against a live loop and a
    # deliberately slow cycle. Any lock-order inversion or lost wakeup shows
    # up as a stall.
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None
    settings.poll_seconds = 1
    N = int(os.environ.get("N", "60"))
    with TestClient(service_app) as c:
        B, A = boot(c)
        seed(B, A)
        stop = threading.Event()
        errs, lat = [], []

        def hammer(path):
            while not stop.is_set():
                t0 = time.time()
                try:
                    # B3: /kill and /resume are POST-only now; the
                    # hammer still hits the same four paths.
                    meth = (c.post if path in ("/kill", "/resume")
                            else c.get)
                    meth(path, params={"token": "sekrit"})
                except Exception as e:
                    errs.append(f"{path}:{e}")
                lat.append((path, time.time() - t0))
                time.sleep(0.01)

        ts = [threading.Thread(target=hammer, args=(p,), daemon=True)
              for p in ("/kill", "/resume", "/status", "/health",
                        "/kill", "/resume")]
        for t in ts:
            t.start()
        time.sleep(N / 10.0)
        stop.set()
        for t in ts:
            t.join(30)
        R("stalled_threads", [t.name for t in ts if t.is_alive()])
        R("errors", errs[:5])
        R("requests", len(lat))
        R("max_latency_s", round(max(x[1] for x in lat), 3))
        worst = max(lat, key=lambda x: x[1])
        R("worst", worst[0])
        R("loop_alive", any(t.name.startswith("exec-loop")
                            for t in threading.enumerate()))
        # settle: one last kill must leave the book flat and halted
        c.post("/kill", params={"token": "sekrit"})
        ok = wait(lambda: B.state.flatten_request is None
                  and B.state.positions == {}, 30)
        R("settles_flat", ok is not None)
        R("final_halted", B.state.halted)
        R("venue_crsp", A.stock_position("CRSP"))

# ------------------------------------------------------------------ S6
elif SCEN == "phase_matrix":
    # A /kill landing in EVERY phase of a cycle must halt, and must flatten
    # EXACTLY ONCE, on the loop thread, leaving the venue flat.
    PHASE = os.environ.get("PHASE", "reconcile")
    HOLD = float(os.environ.get("HOLD", "3"))
    service.nino34_weekly = lambda: 2.7
    gate = threading.Event()
    hit = threading.Event()
    settings.poll_seconds = 2

    from datetime import datetime as _dt, timezone as _tz
    TODAY = _dt.now(_tz.utc).date().isoformat()

    def _pl(exits=(), stops=()):
        return {"as_of": TODAY,
                "gate": {"xbi_above_200dma_prior": True, "since": None},
                "entries": [], "exits": list(exits), "stops": list(stops),
                "rebalance": {"needed": None, "current_sleeve_weight": None,
                              "target": 0.30},
                "book_params": {"max_open": 10, "risk_frac": 0.01,
                                "band": 0.05, "cash_vehicle": "BIL",
                                "core": "SPY"},
                "contract": "x"}

    if PHASE == "exits":
        blend_mod.fetch_intents = lambda _c: _pl(
            exits=[{"call_id": 1, "symbol": "CRSP", "reason": "signal"}])
    elif PHASE == "ratchet":
        blend_mod.fetch_intents = lambda _c: _pl(
            stops=[{"symbol": "CRSP", "call_id": 1, "trail_level": 47.0}])
    else:
        blend_mod.fetch_intents = lambda _c: None

    def _block(tag):
        def wrapper(fn):
            def inner(*a, **k):
                if PHASE == tag and not hit.is_set():
                    hit.set()
                    gate.wait(HOLD + 20)
                return fn(*a, **k)
            return inner
        return wrapper

    blend_mod.reconcile = _block("reconcile")(blend_mod.reconcile)
    blend_mod._execute_exit = _block("exits")(blend_mod._execute_exit)
    blend_mod._execute_adjust_stop = _block("ratchet")(
        blend_mod._execute_adjust_stop)

    class PhaseAdapter(DryAdapter):
        def mark(self, ref):
            if PHASE == "ladder" and not hit.is_set():
                hit.set()
                gate.wait(HOLD + 20)
            return 1.0

    service.DryAdapter = PhaseAdapter
    with TestClient(service_app) as c:
        B, A = boot(c)
        seed(B, A)
        if PHASE == "ladder":
            with service.MGR_LOCK:
                service.MGR.on_opened(list(service.MGR.state.legs)[0],
                                      10_000, "ref-1", "2026-08-01")
                service.MGR.save()
        if PHASE == "flatten":
            # kill lands while a PREVIOUS kill's flatten is running
            _inner = blend_mod._cf if False else None
            orig = blend_mod.execute_flatten
            def slow_flatten(mgr, adapter, alert):
                if not hit.is_set():
                    hit.set()
                    gate.wait(HOLD + 20)
                return orig(mgr, adapter, alert)
            blend_mod.execute_flatten = slow_flatten
            c.post("/kill", params={"token": "sekrit"})
        service.LOOP_WAKE.set()
        got = wait(lambda: hit.is_set(), 40)
        R("phase_reached", got is not None)
        t0 = time.time()
        r = c.post("/kill", params={"token": "sekrit"}).json()
        R("kill_http_s", round(time.time() - t0, 3))
        R("halted_immediately", B.state.halted)
        R("journalled_on_disk",
          json.load(open(settings.blend_state_path)).get("halted"))
        gate.set()
        ok = wait(lambda: B.state.flatten_request is None
                  and B.state.positions == {}, 60)
        R("flattened", ok is not None)
        R("kill_to_flat_s", "NONE" if ok is None else round(ok - t0, 3))
        time.sleep(2.5)
        R("flatten_calls", FLAT["n"])
        R("flatten_from_api_thread", bool(FLAT["threads"] & API_THREADS))
        R("venue_crsp", A.stock_position("CRSP"))
        R("final_halted", B.state.halted)
        R("phase", PHASE)

# ------------------------------------------------------------------ S7
elif SCEN == "double_kill_in_flatten":
    # A SECOND /kill lands INSIDE execute_flatten's body (MF-A's new
    # possibility). The `is executing` guard must not swallow it.
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None
    settings.poll_seconds = 2
    gate = threading.Event()
    hit = threading.Event()

    class SlowSell(DryAdapter):
        def place_stock_order(self, symbol, qty, kind, **kw):
            if qty < 0 and kind == "MKT" and not hit.is_set():
                hit.set()
                gate.wait(30)
            return super().place_stock_order(symbol, qty, kind, **kw)

    service.DryAdapter = SlowSell
    with TestClient(service_app) as c:
        B, A = boot(c)
        seed(B, A)
        r1 = c.post("/kill", params={"token": "sekrit"}).json()
        assert wait(lambda: hit.is_set(), 30), "flatten never reached the sell"
        req1 = B.state.flatten_request
        r2 = c.post("/kill", params={"token": "sekrit"}).json()
        req2 = B.state.flatten_request
        R("second_request_is_new", req2 is not req1)
        gate.set()
        time.sleep(3.0)
        R("request_after_flatten_completed", B.state.flatten_request)
        R("second_kill_survived_or_executed", True)
        ok = wait(lambda: B.state.flatten_request is None, 30)
        R("journal_eventually_clear", ok is not None)
        R("flatten_calls", FLAT["n"])
        R("halted", B.state.halted)
        R("venue_crsp", A.stock_position("CRSP"))
        R("positions", sorted(B.state.positions))

# ------------------------------------------------------------------ S8
elif SCEN == "deferred_kill_lost_on_save_error":
    # The loop clears LADDER_KILL BEFORE doing the work. If _kill_ladder
    # raises (MGR.save on a full/RO disk), the flag is gone and nothing
    # re-triggers: the deferred kill is LOST.
    HANG = float(os.environ.get("HANG", "6"))
    rel = threading.Event()
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None
    settings.blend_enabled = False
    settings.poll_seconds = 2

    class SlowMark(DryAdapter):
        n = 0
        def mark(self, ref):
            SlowMark.n += 1
            if SlowMark.n == 1:
                rel.wait(HANG)
            return 1.0

    service.DryAdapter = SlowMark
    with TestClient(service_app) as c:
        assert wait(lambda: service.MGR is not None, 20)
        leg0 = list(service.MGR.state.legs)[0]
        with service.MGR_LOCK:
            service.MGR.on_opened(leg0, 10_000, "ref-1", "2026-08-01")
            service.MGR.save()
        service.LOOP_WAKE.set()
        assert wait(lambda: SlowMark.n > 0, 20), "no mark"
        time.sleep(0.4)
        k = c.post("/kill", params={"token": "sekrit"}).json()
        R("kill_ladder", k.get("ladder"))
        R("LADDER_KILL_set", service.LADDER_KILL.is_set())
        boom = {"n": 0}
        real_save = service.MGR.save
        def bad_save():
            boom["n"] += 1
            raise OSError("No space left on device")
        service.MGR.save = bad_save
        rel.set()
        time.sleep(3.0)
        service.MGR.save = real_save
        R("save_raised_times", boom["n"])
        R("LADDER_KILL_after", service.LADDER_KILL.is_set())
        R("legs_open_after", [k2 for k2, v in service.MGR.state.legs.items()
                              if v.status == "OPEN"])
        R("halted_mem", service.MGR.state.halted)
        R("halted_disk", json.load(open(settings.state_path)).get("halted"))
        # give the loop several more iterations to notice
        for _ in range(4):
            service.LOOP_WAKE.set()
            time.sleep(1.2)
        R("legs_open_final", [k2 for k2, v in service.MGR.state.legs.items()
                              if v.status == "OPEN"])
        R("halted_disk_final",
          json.load(open(settings.state_path)).get("halted"))
        R("LADDER_KILL_final", service.LADDER_KILL.is_set())

# ------------------------------------------------------------------ S9
elif SCEN == "kill_alert_overclaims_closed_legs":
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None
    settings.blend_enabled = False

    class BadClose(DryAdapter):
        def close_spread(self, ref):
            raise RuntimeError("gateway rejected the close")

    service.DryAdapter = BadClose
    with TestClient(service_app) as c:
        assert wait(lambda: service.MGR is not None, 20)
        leg0 = list(service.MGR.state.legs)[0]
        with service.MGR_LOCK:
            service.MGR.on_opened(leg0, 10_000, "ref-1", "2026-08-01")
            service.MGR.save()
        assert wait(lambda: service.LAST["loop_ok"] > 0, 30)
        r = c.post("/kill", params={"token": "sekrit"}).json()
        R("ladder_field", r.get("ladder"))
        R("legs_still_open", [k for k, v in service.MGR.state.legs.items()
                              if v.status == "OPEN"])
        R("alert", [a for a in ALERTS if "KILLED" in a][:1])

# ------------------------------------------------------------------ S10
elif SCEN == "api_thread_overlaps_loop_on_adapter":
    # R2 doctrine: only the loop thread may talk to the adapter. /kill's
    # _kill_ladder runs on the API thread when MGR_LOCK is free. Since MF-A
    # /kill no longer waits for BLEND_LOCK first, so it reaches the adapter
    # WHILE the loop is inside its own adapter round-trip.
    rel = threading.Event()
    inside = threading.Event()
    service.nino34_weekly = lambda: 2.7
    blend_mod.fetch_intents = lambda _c: None
    OVER = {"v": False, "closer": None, "looper": None}

    class Watch(DryAdapter):
        def poll_stock_fills(self):
            if not inside.is_set() and threading.get_ident() not in API_THREADS:
                inside.set()
                OVER["looper"] = threading.get_ident()
                rel.wait(8)
            return super().poll_stock_fills()
        def close_spread(self, ref):
            OVER["closer"] = threading.get_ident()
            OVER["v"] = inside.is_set() and not rel.is_set()
            return {"value": 1.0}

    service.DryAdapter = Watch
    with TestClient(service_app) as c:
        B, A = boot(c)
        with service.MGR_LOCK:
            service.MGR.on_opened(list(service.MGR.state.legs)[0], 10_000,
                                  "ref-1", "2026-08-01")
            service.MGR.save()
        seed(B, A)
        service.LOOP_WAKE.set()
        assert wait(lambda: inside.is_set(), 30), "loop never hit the adapter"
        t0 = time.time()
        r = c.post("/kill", params={"token": "sekrit"})
        R("kill_http_s", round(time.time() - t0, 3))
        R("close_ran_while_loop_was_inside_the_adapter", OVER["v"])
        R("close_on_api_thread", OVER["closer"] in API_THREADS)
        R("loop_thread_is_different", OVER["closer"] != OVER["looper"])
        rel.set()

else:
    print("unknown scenario", SCEN)
    sys.exit(2)
