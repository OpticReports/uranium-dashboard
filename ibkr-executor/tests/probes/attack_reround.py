"""Adversarial re-review attack probes against e3da227 (run from ibkr-executor/)."""
import sys, time, types, tempfile, os

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

import test_ib_stock_adapter as T
import app.ib_adapter as ib_mod
from app.ib_adapter import DryAdapter
from app.blend import Blend3070Manager, run_cycle, reconcile, HISTORY_HORIZON_S

# wire the fake venue
mod = types.ModuleType("ib_async")
mod.IB = T.FakeIB
mod.Stock = T.FakeStock
mod.Future = T.FakeStock
mod.MarketOrder = T.FakeMarketOrder
mod.StopOrder = T.FakeStopOrder
sys.modules["ib_async"] = mod
ib_mod.PLACE_ACK_TIMEOUT_S = 0.2
ib_mod.MKT_FILL_WAIT_S = 0.2
ib_mod.CANCEL_ACK_TIMEOUT_S = 0.2
ib_mod.WAIT_TICK_S = 0.0

class Cfg(T._Cfg):
    pass

def mk_adapter():
    a = ib_mod.IBAdapter(Cfg())
    a.ib.prices = {"SPY": 100.0, "BIL": 100.0, "CRSP": 50.0}
    return a

def mk_mgr(name):
    d = tempfile.mkdtemp()
    m = Blend3070Manager(Cfg(), os.path.join(d, name + ".json"))
    m.state.initialized = True
    m.state.sleeve_cash = 3000.0
    m.state.spy_qty = 70
    return m

PAYLOAD = dict(T._payload()) if hasattr(T, "_payload") else None

def payload(entries=(), stops=(), exits=()):
    return {
        "as_of": "2026-08-20",
        "gate": {"xbi_above_200dma_prior": True, "since": None},
        "entries": list(entries), "exits": list(exits), "stops": list(stops),
        "rebalance": {"needed": None, "current_sleeve_weight": None, "target": 0.30},
        "book_params": {"max_open": 10, "risk_frac": 0.01, "band": 0.05,
                        "cash_vehicle": "BIL", "core": "SPY"},
    }

ENTRY = {"symbol": "CRSP", "call_id": 1, "fire_date": "2026-08-19",
         "flag_type": "x", "risk_frac": 0.01, "entry_ref": 50.0, "note": ""}
STOP = {"symbol": "CRSP", "call_id": 1, "trail_level": 44.0}

results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ("  | " + detail if detail else ""))


# ---------------------------------------------------------------------------
# A1: blackout-horizon guard depth. Stop filled INSIDE a 3-day blackout is
# invisible to venue history forever. Cycle N (first post-recovery, tracker
# down): reconcile succeeds, stamps last_reconcile_ts. Cycle N+1: tracker
# exit arrives, gap is now small -> does the executor MKT-sell shares the
# venue no longer holds (short)?
# ---------------------------------------------------------------------------
def a1():
    a = mk_adapter()
    m = mk_mgr("a1")
    # enter CRSP x5 normally
    run_cycle(m, a, payload(entries=[ENTRY], stops=[STOP]), "2026-08-20",
              alert=lambda _: None)
    T._fill_working_mkt(a.ib)
    fake = a.ib
    moo = fake.trade_by_ref(a.find_stock_order("blend-1-entry")["order_ref"])
    fake.fill(moo, [(5, 50.0)])
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-20", alert=lambda _: None)
    assert "1" in m.state.positions, "setup failed"
    # BLACKOUT: gateway restarted; the stop FILLED during it and history is gone
    fake._trades = []                     # fresh session: no order history
    a._emitted_fill_keys = set()          # process restarted too (worst case)
    m2 = Blend3070Manager(Cfg(), m.state_path)   # state reloaded from disk
    m2.state.last_reconcile_ts = time.time() - 3 * 86400.0
    alerts = []
    # cycle N: tracker down -> reconcile-only
    run_cycle(m2, a, None, "2026-08-24", alert=alerts.append)
    still_held = "1" in m2.state.positions
    # cycle N+1: tracker back, publishes the exit for the pierced trail
    sells_before = [t for t in fake.trades() if t.order.action == "SELL"
                    and t.order.orderType == "MKT" and t.contract.symbol == "CRSP"]
    run_cycle(m2, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                     "reason": "trail", "trail_level": 47.0}],
                             stops=[STOP]),
              "2026-08-24", alert=alerts.append)
    sells = [t for t in fake.trades() if t.order.action == "SELL"
             and t.order.orderType == "MKT" and t.contract.symbol == "CRSP"]
    shorted = len(sells) > len(sells_before)
    check("A1 blackout guard survives past first post-recovery cycle",
          not shorted,
          f"held after cycle N={still_held}; MKT sells placed on cycle N+1={len(sells)-len(sells_before)}"
          f" (a sell here shorts already-stopped-out shares)")

# ---------------------------------------------------------------------------
# A1b: same but the exit arrives on the FIRST post-recovery cycle (the fix's
# claimed closure) -> must park, never sell.
# ---------------------------------------------------------------------------
def a1b():
    a = mk_adapter()
    m = mk_mgr("a1b")
    run_cycle(m, a, payload(entries=[ENTRY], stops=[STOP]), "2026-08-20",
              alert=lambda _: None)
    fake = a.ib
    moo = fake.trade_by_ref(a.find_stock_order("blend-1-entry")["order_ref"])
    fake.fill(moo, [(5, 50.0)])
    T._fill_working_mkt(fake)
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-20", alert=lambda _: None)
    fake._trades = []
    a._emitted_fill_keys = set()
    m2 = Blend3070Manager(Cfg(), m.state_path)
    m2.state.last_reconcile_ts = time.time() - 3 * 86400.0
    alerts = []
    run_cycle(m2, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                     "reason": "trail", "trail_level": 47.0}],
                             stops=[STOP]),
              "2026-08-24", alert=alerts.append)
    sells = [t for t in fake.trades() if t.order.action == "SELL"
             and t.order.orderType == "MKT" and t.contract.symbol == "CRSP"]
    parked = "1" in m2.state.unreconciled
    check("A1b blackout exit on FIRST post-recovery cycle parks (claimed closure)",
          parked and not sells,
          f"parked={parked}, MKT sells={len(sells)}")

# ---------------------------------------------------------------------------
# A2: M4 alert-once — quiet book: outage 1 alerts; recovery; outage 2 later.
# Does outage 2 re-alert?
# ---------------------------------------------------------------------------
def a2():
    m = mk_mgr("a2")
    d = DryAdapter()
    alerts = []
    # outage 1: no SPY quote (prices dict missing SPY)
    bad = {"BIL": 100.0}
    m.step("2026-08-20", payload(), bad)
    n1 = len([e for e in m.state.events if "SKIPPED" in e["msg"]])
    # next cycle, still out: deduped (alert-once) -- expected
    m.step("2026-08-20", payload(), bad)
    # recovery: quotes back, quiet book, nothing logs an event
    m.step("2026-08-21", payload(), {"SPY": 100.0, "BIL": 100.0})
    # outage 2, days later
    newly = m._event.__self__  # noqa
    intents = m.step("2026-08-24", payload(), bad)
    alerted_again = any(i["action"] == "ALERT" for i in intents)
    check("A2 M4 re-alerts on a NEW outage after quiet recovery",
          alerted_again,
          "second outage's WARN was deduped against the first (last-event-only dedup)"
          if not alerted_again else "")

# ---------------------------------------------------------------------------
# A3: alert interleaving — pending book order + missing quote: does the M4
# WARN alert fire EVERY cycle (dedup broken by alternating messages)?
# ---------------------------------------------------------------------------
def a3():
    m = mk_mgr("a3")
    m.state.pending_book_orders["blend-sweep-x-1"] = {
        "kind": "sweep", "symbol": "BIL", "qty": 10, "date": "2026-08-20",
        "ref_price": 100.0}
    bad = {}
    n = 0
    for _ in range(4):
        intents = m.step("2026-08-20", payload(), bad)
        n += sum(1 for i in intents if i["action"] == "ALERT")
    check("A3 interleaved events keep M4 alert-once semantics",
          n <= 1, f"ALERT intents over 4 cycles={n} (expected 1)")

# ---------------------------------------------------------------------------
# A4: reserved-cash: pending sweep BUY fills ABOVE ref_price -> sleeve cash
# negative leak?
# ---------------------------------------------------------------------------
def a4():
    a = mk_adapter()
    fake = a.ib
    m = mk_mgr("a4")
    m.state.sleeve_cash = 3000.0
    m.state.spy_qty = 70
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)  # sweep 30 BIL working
    # fill above ref
    for t in fake.trades():
        if t.order.orderType == "MKT" and t.orderStatus.status not in ("Filled",):
            fake.fill(t, [(t.order.totalQuantity, 100.9)])
    run_cycle(m, a, payload(), "2026-08-21", alert=lambda _: None)
    check("A4 sweep slippage above ref_price leaves cash >= -slippage bound",
          m.state.sleeve_cash > -50.0,
          f"sleeve_cash={m.state.sleeve_cash:.2f} (slippage-magnitude negative only)")

# ---------------------------------------------------------------------------
# A5: permanently-working book order: exits + stop ratchets must still run;
# how loud is the freeze?
# ---------------------------------------------------------------------------
def a5():
    a = mk_adapter()
    fake = a.ib
    m = mk_mgr("a5")
    run_cycle(m, a, payload(entries=[ENTRY], stops=[STOP]), "2026-08-20",
              alert=lambda _: None)
    moo = fake.trade_by_ref(a.find_stock_order("blend-1-entry")["order_ref"])
    fake.fill(moo, [(5, 50.0)])
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-20", alert=lambda _: None)
    # the sweep MKT stays working FOREVER (venue never fills, never cancels)
    pend0 = set(m.state.pending_book_orders)
    assert pend0, "expected a pending sweep"
    # stop ratchet + exit must both still execute across frozen cycles
    run_cycle(m, a, payload(stops=[{"symbol": "CRSP", "call_id": 1,
                                    "trail_level": 47.0}]),
              "2026-08-21", alert=lambda _: None)
    ratcheted = m.state.positions["1"].stop_level == 47.0

    def sync_fill(t):
        if t.order.orderType == "MKT" and t.order.tif == "DAY" \
                and t.contract.symbol == "CRSP":
            fake.fill(t, [(t.order.totalQuantity, 47.0)])
    fake.on_place = sync_fill
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 47.0}]),
              "2026-08-22", alert=lambda _: None)
    exited = "1" not in m.state.positions and "1" not in m.state.unreconciled
    check("A5 stuck book order never blocks exits/ratchets",
          ratcheted and exited, f"ratcheted={ratcheted} exited={exited}, "
          f"pending still={set(m.state.pending_book_orders) == pend0}")

# ---------------------------------------------------------------------------
# A6: partial stop fill booked exactly once + remainder re-protected across
# the NEXT cycle (pass 4 re-place under the same cid as the cancelled stop).
# ---------------------------------------------------------------------------
def a6():
    a = mk_adapter()
    fake = a.ib
    m = mk_mgr("a6")
    run_cycle(m, a, payload(entries=[ENTRY], stops=[STOP]), "2026-08-20",
              alert=lambda _: None)
    moo = fake.trade_by_ref(a.find_stock_order("blend-1-entry")["order_ref"])
    fake.fill(moo, [(5, 50.0)])
    T._fill_working_mkt(fake)
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-20", alert=lambda _: None)
    pos = m.state.positions["1"]
    st = fake.trade_by_ref(pos.stop_order_ref)
    # venue: 3 of 5 fill, remainder cancelled BY THE VENUE (no exit intent)
    st.fills.append(T.FakeFill(T.FakeExec(3, 44.0, "SLD")))
    st.orderStatus.status = "Cancelled"
    cash0 = m.state.sleeve_cash + m.state.bil_qty * 100.0
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-21", alert=lambda _: None)
    pos = m.state.positions.get("1")
    booked = (m.state.sleeve_cash + m.state.bil_qty * 100.0) - cash0
    reprotected = pos is not None and pos.qty == 2 and pos.stop_order_ref \
        and not pos.stop_missing
    stop_trades = [t for t in fake.trades() if t.order.orderType == "STP"
                   and t.orderStatus.status == "Submitted"]
    right_qty = stop_trades and stop_trades[-1].order.totalQuantity == 2
    # second cycle: no double booking
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-22", alert=lambda _: None)
    booked2 = (m.state.sleeve_cash + m.state.bil_qty * 100.0) - cash0
    check("A6 venue-initiated partial stop: booked once, remainder re-protected",
          abs(booked - 3 * 44.0) < 1e-6 and reprotected and right_qty
          and abs(booked2 - booked) < 1e-6,
          f"booked={booked:.2f} reprotected={reprotected} stop_qty_ok={right_qty} "
          f"booked_after_2nd_cycle={booked2:.2f}")

# ---------------------------------------------------------------------------
# A7: 3b churn — venue-history lag: find returns None transiently. Healthy
# stop must NOT be demoted / cancel-replaced.
# ---------------------------------------------------------------------------
def a7():
    a = mk_adapter()
    fake = a.ib
    m = mk_mgr("a7")
    run_cycle(m, a, payload(entries=[ENTRY], stops=[STOP]), "2026-08-20",
              alert=lambda _: None)
    moo = fake.trade_by_ref(a.find_stock_order("blend-1-entry")["order_ref"])
    fake.fill(moo, [(5, 50.0)])
    T._fill_working_mkt(fake)
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-20", alert=lambda _: None)
    pos = m.state.positions["1"]
    ref0 = pos.stop_order_ref
    # transient history lag: hide the trades list for one cycle
    saved = fake._trades
    fake._trades = [t for t in saved if t.order.orderType != "STP"]
    run_cycle(m, a, payload(stops=[STOP]), "2026-08-21", alert=lambda _: None)
    fake._trades = saved
    pos = m.state.positions["1"]
    stp_count = len([t for t in saved if t.order.orderType == "STP"])
    check("A7 transient history lag never demotes/replaces a healthy stop",
          pos.stop_order_ref == ref0 and not pos.stop_missing and stp_count == 1,
          f"ref same={pos.stop_order_ref == ref0}, missing={pos.stop_missing}, "
          f"stp_orders={stp_count}")

# ---------------------------------------------------------------------------
# A8: mark cache staleness across a failing cycle: cache must keep OLD ts
# (age grows), never a fresh ts with stale prices.
# ---------------------------------------------------------------------------
def a8():
    a = mk_adapter()
    m = mk_mgr("a8")
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    ts0 = m.mark_cache["ts"]
    a.ib.connected = False
    a.ib.connect_fails = True
    try:
        run_cycle(m, a, payload(), "2026-08-21", alert=lambda _: None)
        raised = False
    except Exception:
        raised = True
    check("A8 failed cycle leaves mark cache honestly stale",
          raised and m.mark_cache["ts"] == ts0,
          f"raised={raised}, ts unchanged={m.mark_cache['ts'] == ts0}")

a1(); a1b(); a2(); a3(); a4(); a5(); a6(); a7(); a8()
print()
fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} probes passed; failures: "
      f"{[r[0] for r in fails]}")
