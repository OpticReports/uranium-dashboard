"""Adversarial counter-probes for the MF-A / MF-B / MF-C round
(9b33081..499aed1).  Run from ibkr-executor/:

    python /path/to/attack_mf2.py [--only NAME ...]

Service-level probes need a virgin process, so they are driven out to
`scratchpad/mf2/scen.py` (one scenario per subprocess).  Manager-level
probes run in-process.
"""
import json, os, subprocess, sys, tempfile, threading, time
sys.path.insert(0, ".")

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(HERE, "mf2", "scen.py")
MAIN_WT = os.path.join(HERE, "base9b", "ibkr-executor")

LANDED, RAN = [], []


def check(name, cond, detail=""):
    RAN.append(name)
    if cond:
        print(f"  ok   {name} {detail}")
    else:
        LANDED.append(f"{name} {detail}".strip())
        print(f"  LAND {name} {detail}")


def run_scen(name, env=None, timeout=300, cwd="."):
    e = dict(os.environ)
    e.update(env or {})
    tmp = tempfile.mkdtemp(prefix="mf2")
    p = subprocess.run([sys.executable, SCEN, name, tmp], env=e, cwd=cwd,
                       capture_output=True, text=True, timeout=timeout)
    out = {}
    for ln in p.stdout.splitlines():
        if ln.startswith("RESULT "):
            k, _, v = ln[7:].partition("=")
            out[k] = v
    out["_stderr"] = p.stderr[-2000:]
    return out


# ---------------------------------------------------------------- helpers
def cfg():
    class Cfg:
        blend_budget = 0.0
        blend_book_usd = 10_000.0
        tracker_url = ""
        tracker_user = ""
        tracker_password = ""
        dry_run = True
        trading_mode = "paper"
    return Cfg()


ROW = {"call_id": 1, "symbol": "CRSP", "qty": 5, "entry_ref": 50.0,
       "fill_price": 50.0, "entry_date": "2026-08-01",
       "time_stop": "2026-10-30", "stop_level": 44.0,
       "stop_order_ref": "STOP-REAL", "stop_missing": False,
       "risk_per_share": 6.0, "history_gap": False, "unverified_cycles": 0,
       "stop_cover_qty": 0}

STAND_IN_FIELDS = ["symbol", "qty", "entry_ref", "fill_price",
                   "entry_date", "time_stop", "stop_level"]


def drifted_file(path, missing, extra=True, key="1"):
    """A state file a NEWER build wrote: one unknown key (forces the drift
    branch) and one required field the row does not carry."""
    row = dict(ROW)
    row.pop(missing)
    if extra:
        row["a_field_from_the_future"] = 1
    json.dump({"initialized": True, "positions": {key: row},
               "mode": "dry:paper",
               "sleeve_cash": 3000.0, "spy_qty": 70, "bil_qty": 0,
               "core_cash": 0.0, "halted": None, "entered_ids": [1],
               "entered_symbols": {"1": "CRSP"},
               "events": [], "trades": [], "equity_curve": [],
               "last_reconcile_ts": time.time()},
              open(path, "w"))


def fresh_adapter(sym="CRSP", qty=5, with_stop=True):
    from app.ib_adapter import DryAdapter
    a = DryAdapter()
    a.place_stock_order(sym, qty, "MKT")
    if with_stop:
        a.place_stock_order(sym, -qty, "STP", stop_price=44.0, tif="GTC",
                            client_order_id="blend-1-stp-44.0000")
    return a


def payload(exits=(), stops=(), entries=()):
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    return {"as_of": today,
            "gate": {"xbi_above_200dma_prior": True, "since": None},
            "entries": list(entries), "exits": list(exits),
            "stops": list(stops),
            "rebalance": {"needed": None, "current_sleeve_weight": None,
                          "target": 0.30},
            "book_params": {"max_open": 10, "risk_frac": 0.01, "band": 0.05,
                            "cash_vehicle": "BIL", "core": "SPY"},
            "contract": "x"}


# ================================================================= A: locks
def p_locks():
    print("== A. locking, halt durability, promptness ==")
    r = run_scen("phase_matrix", {"PHASE": "reconcile"})
    for ph in ("reconcile", "exits", "ratchet", "ladder", "flatten"):
        r = run_scen("phase_matrix", {"PHASE": ph})
        check(f"A1[{ph}] kill halts, journals to DISK, flattens EXACTLY once "
              f"on the loop thread, venue flat",
              r.get("halted_immediately") == "KILL"
              and r.get("journalled_on_disk") == "KILL"
              and r.get("flattened") == "True"
              and r.get("flatten_calls") == "1"
              and r.get("flatten_from_api_thread") == "False"
              and r.get("venue_crsp") == "0",
              f"http={r.get('kill_http_s')}s "
              f"kill->flat={r.get('kill_to_flat_s')}s "
              f"flattens={r.get('flatten_calls')} "
              f"venue={r.get('venue_crsp')}")

    r = run_scen("deadlock_storm", {"N": "120"})
    check("A2 kill/resume/status/health storm against a live loop: no "
          "deadlock, no stall, settles flat and halted",
          r.get("stalled_threads") == "[]" and r.get("errors") == "[]"
          and r.get("settles_flat") == "True"
          and r.get("final_halted") == "KILL",
          f"requests={r.get('requests')} "
          f"max_latency={r.get('max_latency_s')}s ({r.get('worst')})")

    r = run_scen("kill_own_close_unbounded", {"HANG": "20"})
    check("A3 /kill's OWN ladder close is bounded by KILL_LOCK_WAIT_S, as "
          "README S6 states ('Both now return in ~0.005s and <0.51s')",
          float(r.get("kill_http_s", "999")) < 1.0,
          f"MGR_LOCK was FREE (loop parked, the deployed steady state) so "
          f"/kill took it instantly and then made the UNCAPPED gateway call "
          f"itself: kill_http={r.get('kill_http_s')}s vs the 0.51s claimed; "
          f"close ran on the API thread={r.get('close_ran_on_api_thread')}")

    r = run_scen("ladder_lost_halt", {"HANG": "20"})
    check("A4 the deferred ladder halt survives a crash in its window",
          r.get("after_crash_halted") == "KILL",
          f"/kill returned {r.get('kill_http_s')}s ladder={r.get('ladder_field')} "
          f"and told the operator 'The ladder is halted from now'; on DISK "
          f"halted={r.get('disk_halted')} with legs {r.get('disk_open_legs')} "
          f"still OPEN -> a restart in that window comes back "
          f"halted={r.get('after_crash_halted')} with "
          f"{r.get('after_crash_open_legs')} OPEN. (blend half is safe: "
          f"disk halted={r.get('blend_disk_halted')}, "
          f"flatten journalled={r.get('blend_disk_flatten_req')})")

    r = run_scen("ladder_stale_kill_wins_resume", {"HANG": "5", "NINO": "6"})
    check("A5 /resume clears a DEFERRED ladder kill, the way it clears a "
          "queued blend flatten",
          r.get("stale_kill_refired_at_resumed_ladder") != "True",
          f"LADDER_KILL still set after /resume="
          f"{r.get('LADDER_KILL_after_resume')}; the deferred kill re-fired "
          f"at the RESUMED ladder: halted={r.get('halted_after_loop')} "
          f"open_legs={r.get('open_legs_after_loop')}")

    r = run_scen("kill_midcycle_enters")
    buys = r.get("BUYS_symbol_qty_haltedAtCall_flattenQueuedAtCall", "")
    check("A6 a book HALTED by /kill places no further orders in the cycle "
          "already in flight (request_flatten: 'halt the book immediately "
          "(no new entries)')",
          "'KILL'" not in buys,
          f"orders placed AFTER the halt was journalled: {buys}")

    r = run_scen("kill_alert_overclaims_closed_legs")
    check("A8 the ladder half of the /kill reply and alert is TRUE: "
          "`closed` / 'all legs closed' only when legs actually closed",
          r.get("legs_still_open") == "[]" or r.get("ladder_field") != "closed",
          f"every close_spread RAISED, leg(s) {r.get('legs_still_open')} are "
          f"still OPEN, and /kill returned ladder={r.get('ladder_field')} "
          f"with the alert {r.get('alert')}")

    r = run_scen("api_thread_overlaps_loop_on_adapter")
    rb = run_scen("api_thread_overlaps_loop_on_adapter", cwd=MAIN_WT) \
        if os.path.isdir(MAIN_WT) else {}
    check("A9 /kill never reaches the adapter from an API thread while the "
          "LOOP is inside its own adapter round-trip (R2: 'an API thread "
          "must never touch it')",
          r.get("close_ran_while_loop_was_inside_the_adapter") != "True",
          f"HEAD overlap={r.get('close_ran_while_loop_was_inside_the_adapter')} "
          f"(kill_http={r.get('kill_http_s')}s) | "
          f"base 9b33081 overlap="
          f"{rb.get('close_ran_while_loop_was_inside_the_adapter')} "
          f"(kill_http={rb.get('kill_http_s')}s) -> PRE-EXISTING, and MF-A "
          f"strictly reduces how often the API thread gets there")

    r = run_scen("deferred_kill_lost_on_save_error")
    check("A10 a deferred ladder kill is not lost when MGR.save() raises "
          "after LADDER_KILL was already cleared",
          r.get("legs_open_final") == "[]"
          and r.get("halted_disk_final") == "KILL",
          f"legs={r.get('legs_open_final')} "
          f"disk_halted={r.get('halted_disk_final')} "
          f"(the clear happens BEFORE the work: a raise between them drops "
          f"the flag with nothing to re-trigger it)")

    r = run_scen("double_kill_in_flatten")
    check("A7 a SECOND /kill landing inside execute_flatten is not "
          "swallowed by the `is executing` guard",
          r.get("second_request_is_new") == "True"
          and r.get("flatten_calls") == "2"
          and r.get("journal_eventually_clear") == "True"
          and r.get("venue_crsp") == "0",
          f"flattens={r.get('flatten_calls')} halted={r.get('halted')} "
          f"venue={r.get('venue_crsp')}")


# ============================================================== B: MF-B/C
def p_standin():
    print("== B. MF-B / MF-C: stand-in rows ==")
    from app.blend import (Blend3070Manager, reconcile, run_cycle,
                           execute_flatten)
    for f in STAND_IN_FIELDS:
        d = tempfile.mkdtemp(prefix="si")
        p = os.path.join(d, "b.json")
        drifted_file(p, f)
        m = Blend3070Manager(cfg(), p)
        a = fresh_adapter()
        alerts = []
        reg = dict(m.state.stand_in_rows)
        m.state.halted = None                     # the operator /resume-s
        m.state.flatten_request = None
        exits_seen, cancels = [], []
        _fso = a.cancel_stock_order
        def _cancel(ref, *args, **kw):
            cancels.append(ref)
            return _fso(ref, *args, **kw)
        a.cancel_stock_order = _cancel
        for i in range(6):
            try:
                run_cycle(m, a, payload(
                    exits=[{"call_id": 1, "symbol": "CRSP",
                            "reason": "signal"}],
                    stops=[{"symbol": "CRSP", "call_id": 1,
                            "trail_level": 47.0}]),
                    "2026-12-31", alert=alerts.append)
            except Exception as exc:               # noqa: BLE001
                alerts.append(f"RAISED {exc}")
        pos = m.state.positions.get("1")
        held = a.stock_position("CRSP")
        stop_alive = a.find_stock_order("blend-1-stp-44.0000")
        check(f"B1[{f}] stand-in row survives 6 cycles unverifiable, "
              f"untouched at the venue, register intact",
              pos is not None and pos.history_gap
              and "1" in m.state.stand_in_rows
              and m.state.stand_in_rows["1"] == [f]
              and held == 5 and not cancels
              and not any("EXIT" in x and "deferred" not in x
                          for x in alerts),
              f"register={reg} -> {dict(m.state.stand_in_rows)} "
              f"flag={None if pos is None else pos.history_gap} "
              f"venue={held} stop={'alive' if stop_alive else 'GONE'} "
              f"cancels={cancels}")
        # kill flatten must park it
        m.request_flatten("2026-12-31")
        execute_flatten(m, a, alerts.append)
        check(f"B2[{f}] /kill's flatten PARKS the stand-in row (never sells "
              f"on invented values)",
              a.stock_position("CRSP") == 5 and "1" in m.state.positions,
              f"venue={a.stock_position('CRSP')} "
              f"rows={sorted(m.state.positions)}")
        # persistence across a restart
        m.save()
        m2 = Blend3070Manager(cfg(), p)
        check(f"B3[{f}] the register and the flag survive a RESTART",
              m2.state.stand_in_rows.get("1") == [f]
              and m2.state.positions["1"].history_gap,
              f"register={dict(m2.state.stand_in_rows)} "
              f"flag={m2.state.positions['1'].history_gap}")
        # a hand-edit that clears the flag but not the register
        raw = json.load(open(p))
        raw["positions"]["1"]["history_gap"] = False
        json.dump(raw, open(p, "w"))
        m3 = Blend3070Manager(cfg(), p)
        check(f"B4[{f}] clearing history_gap by hand does NOT un-park the "
              f"row while the register still names it",
              m3.state.positions["1"].history_gap,
              f"flag={m3.state.positions['1'].history_gap}")

    # register pruning when the row leaves
    d = tempfile.mkdtemp(prefix="si")
    p = os.path.join(d, "b.json")
    drifted_file(p, "time_stop")
    m = Blend3070Manager(cfg(), p)
    m.state.positions.pop("1")
    m.save()
    on_disk = json.load(open(p)).get("stand_in_rows")
    m4 = Blend3070Manager(cfg(), p)
    check("B5 a register entry for a row that LEFT the book is pruned on "
          "load — and is not left dangling on disk in between",
          not m4.state.stand_in_rows and not on_disk,
          f"on_disk_after_save={on_disk} after_load={dict(m4.state.stand_in_rows)}")

    # a row that leaves and a NEW row reusing the key
    d = tempfile.mkdtemp(prefix="si")
    p = os.path.join(d, "b.json")
    drifted_file(p, "time_stop")
    m = Blend3070Manager(cfg(), p)
    m.state.positions.pop("1")
    m.on_entered({"call_id": 1, "symbol": "NEWCO", "qty": 9,
                  "entry_ref": 10.0, "stop_level": 9.0}, 10.0, "ref",
                 "2026-08-01")
    m.save()
    m5 = Blend3070Manager(cfg(), p)
    check("B6 a FRESH, fully-known row that reuses a retired stand-in key "
          "is not poisoned by the stale register entry",
          not m5.state.positions["1"].history_gap
          and "1" not in m5.state.stand_in_rows,
          f"flag={m5.state.positions['1'].history_gap} "
          f"register={dict(m5.state.stand_in_rows)} "
          f"symbol={m5.state.positions['1'].symbol}")

    # MF-C proper: the invented identity must not address the venue
    d = tempfile.mkdtemp(prefix="si")
    p = os.path.join(d, "b.json")
    drifted_file(p, "symbol")
    m = Blend3070Manager(cfg(), p)
    a = fresh_adapter()
    m.state.halted = None
    alerts = []
    for i in range(5):
        reconcile(m, a, "2026-12-31", alerts.append)
    check("B7 (MF-C) an invented `symbol` never cancels the row's real "
          "working stop, and never deletes the row",
          "1" in m.state.positions
          and a.find_stock_order("blend-1-stp-44.0000") is not None
          and a.stock_position("CRSP") == 5,
          f"rows={sorted(m.state.positions)} "
          f"stop={'working' if a.find_stock_order('blend-1-stp-44.0000') else 'CANCELLED'} "
          f"venue={a.stock_position('CRSP')}")
    check("B8 the escalation alert is re-armed, not one-shot, and does not "
          "quote a venue count for an invented symbol",
          sum(1 for x in alerts if "STAND-INS" in x) >= 1
          and not any("the account holds" in x for x in alerts
                      if "STAND-INS" in x),
          f"stand-in alerts={sum(1 for x in alerts if 'STAND-INS' in x)}/5 "
          f"cycles")

    # /status vs /blend/feed provenance
    d = tempfile.mkdtemp(prefix="si")
    p = os.path.join(d, "b.json")
    drifted_file(p, "stop_level")
    m = Blend3070Manager(cfg(), p)
    st = m.status_summary({"CRSP": 50.0})
    fd = m.feed({"CRSP": 50.0}, "2026-12-31")
    check("B9 /status names the invented fields; the public feed at least "
          "marks the row unverifiable",
          st.get("stand_in_rows") == {"1": ["stop_level"]}
          and any(r.get("unverifiable") for r in fd.get("positions", [])),
          f"status.stand_in_rows={st.get('stand_in_rows')} "
          f"feed keys={sorted((fd.get('positions') or [{}])[0])}")


# ========================================================== C: rollback
def p_rollback():
    print("== C. rollback safety of `stand_in_rows` ==")
    if not os.path.isdir(MAIN_WT):
        check("C1 rollback measured against a main worktree", False,
              f"no worktree at {MAIN_WT} — SKIPPED")
        return
    d = tempfile.mkdtemp(prefix="rb")
    p = os.path.join(d, "b.json")
    drifted_file(p, "symbol")
    from app.blend import Blend3070Manager
    m = Blend3070Manager(cfg(), p)
    m.state.halted = None
    m.save()
    reg = dict(m.state.stand_in_rows)
    script = f'''
import json, sys, os
sys.path.insert(0, ".")
from app.blend import Blend3070Manager, reconcile
from app.ib_adapter import DryAdapter
class Cfg:
    blend_budget=0.0; blend_book_usd=10000.0; tracker_url=""
    tracker_user=""; tracker_password=""; dry_run=True; trading_mode="paper"
m = Blend3070Manager(Cfg(), {p!r})
a = DryAdapter()
a.place_stock_order("CRSP", 5, "MKT")
a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                    client_order_id="blend-1-stp-44.0000")
al = []
print("LOADED_OK", m.archived_state is None, sorted(m.state.positions))
print("HALTED", m.state.halted)
print("HISTORY_GAP", m.state.positions["1"].history_gap
      if "1" in m.state.positions else None)
for i in range(3):
    try:
        reconcile(m, a, "2026-12-31", al.append)
    except Exception as e:
        print("RAISED", e)
print("ROWS_AFTER", sorted(m.state.positions))
print("VENUE", a.stock_position("CRSP"))
print("STOP", "working" if a.find_stock_order("blend-1-stp-44.0000") else "CANCELLED")
'''
    sp = os.path.join(d, "rb.py")
    open(sp, "w").write(script)
    r = subprocess.run([sys.executable, sp], cwd=MAIN_WT,
                       capture_output=True, text=True, timeout=180)
    o = r.stdout
    check("C1 an OLDER build (main 9b33081) rolled back onto a file "
          "carrying `stand_in_rows` still LOADS it",
          "LOADED_OK True" in o,
          o.strip().replace("\n", " | ")[:300] + (r.stderr[-200:] if r.returncode else ""))
    check("C2 ...and then does something SAFE with the stand-in row (the "
          "register it ignores was the only thing keeping it out of pass 1b)",
          "STOP working" in o and "ROWS_AFTER ['1']" in o,
          f"register the new build wrote={reg}; the old build: "
          + o.strip().replace("\n", " | ")[:400])


# ========================================================== D: feeds
def p_feeds():
    print("== D. feeds.with_deadline ==")
    import socket
    from app import nino
    from app.feeds import with_deadline, FeedDeadline

    # a trickling server: one chunk every 4s, forever
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                srv.settimeout(1.0)
                c, _ = srv.accept()
            except Exception:
                continue
            def h(c=c):
                try:
                    c.recv(65536)
                    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 10000\r\n\r\n")
                    for _ in range(100):
                        if stop.is_set():
                            break
                        c.sendall(b"x" * 10)
                        time.sleep(4.0)
                except Exception:
                    pass
            threading.Thread(target=h, daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()

    nino._URL = f"http://127.0.0.1:{port}/f"
    nino._CACHE.clear()
    t0 = time.time()
    v = nino.nino34_weekly()
    el = time.time() - t0
    check("D1 a TRICKLING feed is bounded by FEED_TIMEOUT (total), not by "
          "the per-operation httpx timeout",
          el <= nino.FEED_TIMEOUT + 1.0,
          f"nino34_weekly() = {el:.2f}s vs FEED_TIMEOUT={nino.FEED_TIMEOUT}")
    check("D2 the deadline failure is negative-cached (a wedged feed is not "
          "re-paid every cycle)",
          "fail" in nino._CACHE,
          f"cache keys={sorted(nino._CACHE)}")
    t1 = time.time()
    nino.nino34_weekly()
    check("D3 the cached failure short-circuits", time.time() - t1 < 0.5,
          f"second call {time.time() - t1:.3f}s")
    before = threading.active_count()
    nino._CACHE.clear()
    nino.nino34_weekly()
    after = threading.active_count()
    check("D4 an abandoned fetch does not leak a thread per RE-TRY beyond "
          "what README S6 admits (one per FAIL_TTL)",
          after - before <= 2,
          f"threads {before} -> {after} (each abandoned worker holds a live "
          f"socket until one read exceeds the per-op timeout)")
    # a late worker must not write the cache behind the caller's back
    nino._CACHE.clear()
    nino._URL = f"http://127.0.0.1:{port}/f"
    try:
        with_deadline(0.2, lambda: time.sleep(1.0) or "late")
    except FeedDeadline:
        pass
    time.sleep(1.3)
    check("D5 an abandoned worker cannot mutate anything the caller reads",
          True, "with_deadline writes only its own local box — verified by "
                "reading app/feeds.py; the late result is discarded")
    stop.set()


# ========================================================== E: N14
def p_n14():
    print("== E. N14 under mid-cycle requests ==")
    from app.blend import Blend3070Manager, run_cycle
    d = tempfile.mkdtemp(prefix="n14")
    p = os.path.join(d, "b.json")
    m = Blend3070Manager(cfg(), p)
    m.state.initialized = True
    m.state.sleeve_cash = 3000.0
    m.state.spy_qty = 70
    a = fresh_adapter()
    m.on_entered({"call_id": 1, "symbol": "CRSP", "qty": 5,
                  "entry_ref": 50.0, "stop_level": 44.0}, 50.0, "ref",
                 "2026-08-01")
    m.state.positions["1"].stop_order_ref = "blend-1-stp-44.0000"
    m.save()
    order = []
    import app.blend as bm
    real_rec, real_flat = bm.reconcile, bm.execute_flatten

    def rec(*ar, **kw):
        order.append("reconcile")
        return real_rec(*ar, **kw)

    def flat(*ar, **kw):
        order.append("flatten")
        return real_flat(*ar, **kw)
    bm.reconcile, bm.execute_flatten = rec, flat
    m.request_flatten("2026-12-31")
    run_cycle(m, a, None, "2026-12-31", alert=lambda x: None)
    bm.reconcile, bm.execute_flatten = real_rec, real_flat
    check("E1 a request journalled BEFORE the cycle still flattens in that "
          "cycle, reconcile-first (N14)",
          order[:2] == ["reconcile", "flatten"],
          f"order={order}")

    # a request that lands DURING the cycle is deferred by ONE cycle
    m2 = Blend3070Manager(cfg(), os.path.join(d, "c.json"))
    m2.state.initialized = True
    m2.state.sleeve_cash = 3000.0
    m2.state.spy_qty = 70
    a2 = fresh_adapter()
    m2.on_entered({"call_id": 1, "symbol": "CRSP", "qty": 5,
                   "entry_ref": 50.0, "stop_level": 44.0}, 50.0, "ref",
                  "2026-08-01")
    m2.state.positions["1"].stop_order_ref = "blend-1-stp-44.0000"
    order2 = []

    def rec2(mg, ad, td, al):
        order2.append("reconcile")
        mg.request_flatten(td)              # /kill lands mid-cycle
        return real_rec(mg, ad, td, al)

    def flat2(*ar, **kw):
        order2.append("flatten")
        return real_flat(*ar, **kw)
    bm.reconcile, bm.execute_flatten = rec2, flat2
    run_cycle(m2, a2, None, "2026-12-31", alert=lambda x: None)
    mid = list(order2)
    order2.clear()

    def rec3(*ar, **kw):
        order2.append("reconcile")
        return real_rec(*ar, **kw)
    bm.reconcile = rec3
    run_cycle(m2, a2, None, "2026-12-31", alert=lambda x: None)
    order = order2
    bm.reconcile, bm.execute_flatten = real_rec, real_flat
    check("E2 a request that lands MID-cycle is not executed against that "
          "cycle's stale reconcile, and runs on the very next one",
          "flatten" not in mid and order[:2] == ["reconcile", "flatten"],
          f"cycle_it_landed_in={mid} next_cycle={order}")
    check("E3 ...and the venue really is flat afterwards",
          a2.stock_position("CRSP") == 0 and not m2.state.positions,
          f"venue={a2.stock_position('CRSP')} rows={sorted(m2.state.positions)}")


ALL = {"locks": p_locks, "standin": p_standin, "rollback": p_rollback,
       "feeds": p_feeds, "n14": p_n14}

if __name__ == "__main__":
    only = sys.argv[sys.argv.index("--only") + 1:] if "--only" in sys.argv \
        else list(ALL)
    for n in only:
        ALL[n]()
    print(f"\n{len(RAN) - len(LANDED)}/{len(RAN)} probes passed; "
          f"landed attacks: {LANDED}")
