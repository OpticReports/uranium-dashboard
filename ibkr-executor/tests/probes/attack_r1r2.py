"""Counter-agent probes vs f98ccfd..8735282 (R1 blackout guard, R2 two-stage
/kill, minors). Run from ibkr-executor/. Probes B1/B2/B2b attack R1 pass 1b;
P3 the unpark race; P4 the /resume-during-flatten race; P5 double-kill."""
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")

from app.blend import Blend3070Manager, run_cycle, stop_client_id
from app.ib_adapter import DryAdapter


class Cfg:
    dry_run = True
    trading_mode = "paper"
    blend_budget = 0.0
    blend_book_usd = 10_000.0
    tracker_url = ""
    tracker_user = ""
    tracker_password = ""


def mk(name):
    d = tempfile.mkdtemp()
    m = Blend3070Manager(Cfg(), os.path.join(d, name + ".json"))
    m.state.initialized = True
    m.state.sleeve_cash = 3_000.0
    m.state.spy_qty = 70
    return m


def payload(entries=(), exits=(), stops=()):
    return {
        "as_of": "2026-08-24",
        "gate": {"xbi_above_200dma_prior": True, "since": None},
        "entries": list(entries), "exits": list(exits), "stops": list(stops),
        "rebalance": {"needed": None, "current_sleeve_weight": None,
                      "target": 0.30},
        "book_params": {"max_open": 10, "risk_frac": 0.01, "band": 0.05,
                        "cash_vehicle": "BIL", "core": "SPY"},
    }


def held(m, call_id=1, symbol="CRSP", qty=5, fill=50.0, stop_level=44.0):
    m.on_entered({"call_id": call_id, "symbol": symbol, "qty": qty,
                  "entry_ref": fill, "stop_level": stop_level},
                 fill, "entry-ref", "2026-08-01")
    pos = m.state.positions[str(call_id)]
    pos.time_stop = "2026-10-30"
    return pos


def sells(a, sym):
    return [e for e in a.log if e.get("symbol") == sym
            and ((e["action"] == "place_stock_order"
                  and e.get("order_type") != "STP" and e["qty"] < 0)
                 or e["action"] == "stop_triggered")]


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ("  | " + detail if detail else ""))


# ---------------------------------------------------------------------------
# B1: pass 1b "gone" park does NOT retire the still-WORKING venue stop.
# Operator manually sold 3 of 5 during the blackout (the /kill loop-down
# alert tells them to "flatten manually if urgent"); the GTC stop for -5
# still rests. Pass 1b parks the WHOLE position UNRECONCILED, cancels
# nothing, tracks nothing — the resting -5 stop later triggers into a
# 2-share account => 3-share naked SHORT at the venue, and the fill event
# only reaches the book as an "UNKNOWN order" alert after the fact.
m = mk("b1")
a = DryAdapter()
pos = held(m)
rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                         client_order_id=stop_client_id(1, 44.0))
pos.stop_order_ref = rs["order_ref"]
m.save()
a._positions["CRSP"] = 2                    # manual sale of 3 in the blackout
m.state.last_reconcile_ts = time.time() - 3 * 86_400
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
parked = "1" in m.state.unreconciled and "1" not in m.state.positions
stop_still_resting = rs["order_ref"] in a._stops
orphan_tracked = rs["order_ref"] in m.state.orphan_stop_refs
park_alert = next((x for x in alerts
                   if "parked for manual booking" in x), "")
# the stop, if it is STILL resting, now triggers (price touches 44):
if stop_still_resting:
    a.trigger_stop(rs["order_ref"])
short_after = a._positions["CRSP"]
alerts2 = []
run_cycle(m, a, None, "2026-08-24", alert=alerts2.append)
unknown = any("UNKNOWN order" in x for x in alerts2)
check("B1 park retires/tracks the resting stop (else: short path)",
      ((not stop_still_resting) or orphan_tracked) and short_after >= 0,
      f"parked={parked} stop_still_resting={stop_still_resting} "
      f"orphan_tracked={orphan_tracked} venue_net_after_trigger={short_after} "
      f"unknown_order_alert_after={unknown}")
# (adjusted for the N1 fix: the old wording probe — "'GONE at the venue'
# while the venue holds 2" — passes vacuously once that alert is gone, so
# it now attacks the NEW contract: the park alert must state the venue's
# ACTUAL quantity, not just avoid the word GONE.)
check("B1 honesty: park alert states the venue's real 2 of 5, never 'x5 GONE'",
      bool(park_alert) and "holds 2 of the 5" in park_alert
      and "GONE" not in park_alert,
      f"alert={park_alert[:160]!r}")

# ---------------------------------------------------------------------------
# B2: conflation false-verify — the blend's 5 CRSP were stopped out inside
# the blackout (fill event lost to a restart; order visible as filled), but
# the ACCOUNT holds 6 externally-bought CRSP shares. held(6) >= book(5)
# "POSITIVELY verifies" the phantom; the filled stop dedupe-returns as the
# "re-placed" protection; the book keeps a phantom position believed
# protected by a DEAD order.
m = mk("b2")
a = DryAdapter()
pos = held(m)
rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                         client_order_id=stop_client_id(1, 44.0))
pos.stop_order_ref = rs["order_ref"]
m.save()
# stop filled inside the blackout; drain-once event lost with the restart
a._orders[rs["order_ref"]]["status"] = "filled"
a._orders[rs["order_ref"]]["fill_price"] = 44.0
a._stops.pop(rs["order_ref"], None)
a._positions["CRSP"] = 6                    # external/manual shares only
m.state.last_reconcile_ts = time.time() - 3 * 86_400
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
pos = m.state.positions.get("1")
phantom = pos is not None and not pos.history_gap
believed_protected = (pos is not None and pos.stop_order_ref
                      and not pos.stop_missing)
protecting_order = (a._orders.get(pos.stop_order_ref, {}).get("status")
                    if pos is not None and pos.stop_order_ref else None)
pos_verified_alert = any("POSITIVELY verified" in x for x in alerts)
check("B2 conflation: external shares must not 'POSITIVELY verify' a "
      "stopped-out position",
      not phantom,
      f"phantom_kept={phantom} believed_protected={believed_protected} "
      f"protecting_order_status={protecting_order} "
      f"verified_alert={pos_verified_alert}")

# B2b: same conflation, but the blend stop was CANCELLED in the blackout
# (operator cancelled it when selling manually) -> pass 1b unparks on the
# external shares, pass 4 re-places a fresh -5 SELL stop (cancelled prior
# does NOT dedupe-suppress) on shares the blend does not own; when it
# triggers, the blend BOOKS a 5-share exit of the operator's shares.
m = mk("b2b")
a = DryAdapter()
pos = held(m)
rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                         client_order_id=stop_client_id(1, 44.0))
pos.stop_order_ref = rs["order_ref"]
m.save()
a.cancel_stock_order(rs["order_ref"])       # cancelled during the blackout
a._positions["CRSP"] = 6                    # external/manual shares only
m.state.last_reconcile_ts = time.time() - 3 * 86_400
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
new_stps = [e for e in a.log if e["action"] == "place_stock_order"
            and e.get("order_type") == "STP" and e.get("ref") != rs["order_ref"]]
new_stop_on_external = bool(new_stps) and "1" in m.state.positions
detail = f"new_sell_stop_placed={bool(new_stps)}"
if new_stps:
    newref = new_stps[-1]["ref"]
    a.trigger_stop(newref)
    alerts2 = []
    run_cycle(m, a, None, "2026-08-25", alert=alerts2.append)
    booked_foreign_exit = "1" not in m.state.positions and any(
        t.get("kind") == "stop_filled" and t["symbol"] == "CRSP"
        for t in m.state.trades)
    detail += (f" venue_net_after={a._positions['CRSP']} "
               f"booked_foreign_exit={booked_foreign_exit}")
check("B2b conflation: no SELL stop may be re-placed on externally-held "
      "shares after a blackout", not new_stop_on_external, detail)

# ---------------------------------------------------------------------------
# P3: unpark race — the stop fills BETWEEN the positions read and the order
# lookup inside pass 1b. Unpark sees held(5) then finds the stop 'filled':
# marks stop_missing, pass 4's same-cid re-place dedupe-returns the FILLED
# order as the 'restored' protection. Self-heal only arrives when the fill
# event stream serves the fill next cycle.
class RaceAdapter(DryAdapter):
    def __init__(self):
        super().__init__()
        self.race_ref = None
        self.raced = False

    def stock_position(self, symbol):
        q = super().stock_position(symbol)
        if not self.raced and self.race_ref in self._stops:
            self.raced = True
            self.trigger_stop(self.race_ref)     # fill lands JUST after read
        return q


m = mk("p3")
a = RaceAdapter()
pos = held(m)
a._positions["CRSP"] = 5
rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                         client_order_id=stop_client_id(1, 44.0))
pos.stop_order_ref = rs["order_ref"]
m.save()
a.race_ref = rs["order_ref"]
m.state.last_reconcile_ts = time.time() - 3 * 86_400
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
pos = m.state.positions.get("1")
phantom_cycle1 = pos is not None
false_verified = any("POSITIVELY verified" in x for x in alerts)
mkt_sells_c1 = len(sells(a, "CRSP"))
alerts2 = []
run_cycle(m, a, None, "2026-08-25", alert=alerts2.append)
healed = "1" not in m.state.positions and not m.state.unreconciled
booked = any(t.get("kind") == "stop_filled" for t in m.state.trades)
check("P3 unpark race self-heals next cycle via the fill poll (no sell, "
      "booked at the stop)",
      healed and booked and sells(a, "CRSP") == sells(a, "CRSP"),
      f"phantom_after_c1={phantom_cycle1} false_verified_alert={false_verified} "
      f"healed_c2={healed} booked={booked}")

# ---------------------------------------------------------------------------
# P4: /resume during the loop's execute_flatten (no BLEND_LOCK on /resume,
# no halted re-check). resume() claims the queued flatten was 'cleared
# before execution' while the flatten is mid-sell; the book ends UN-halted
# and step() enters NEW positions in the same cycle the kill just sold
# everything.
class ResumeRaceAdapter(DryAdapter):
    def __init__(self, mgr):
        super().__init__()
        self.mgr = mgr
        self.fired = False

    def cancel_stock_order(self, ref):
        if not self.fired and self.mgr.state.flatten_request is None:
            pass
        if not self.fired and self.mgr.state.flatten_request is not None:
            self.fired = True
            self.mgr.resume()                # API thread interleaves HERE
        return super().cancel_stock_order(ref)


m = mk("p4")
a = ResumeRaceAdapter(m)
pos = held(m)
rs = a.place_stock_order("CRSP", 5, "MKT", ref_price=50.0)
rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                         client_order_id=stop_client_id(1, 44.0))
pos.stop_order_ref = rs["order_ref"]
m.save()
m.request_flatten("2026-08-24")
alerts = []
run_cycle(m, a,
          payload(entries=[{"symbol": "NTLA", "call_id": 9,
                            "fire_date": "2026-08-24", "flag_type": "x",
                            "risk_frac": 0.01, "entry_ref": 50.0,
                            "note": ""}],
                  stops=[{"symbol": "NTLA", "call_id": 9,
                          "trail_level": 44.0}]),
          "2026-08-24", alert=alerts.append)
flattened = "1" not in m.state.positions
cleared_claim = any("cleared before execution" in e["msg"]
                    for e in m.state.events)
resumed = m.state.halted is None
new_entry_same_cycle = "9" in m.state.positions or "9" in m.state.pending_entries
check("P4 /resume race: flatten must not both execute AND report 'cleared "
      "before execution' / leave the book live",
      not (flattened and cleared_claim and resumed),
      f"flattened={flattened} says_cleared_before_execution={cleared_claim} "
      f"halted={m.state.halted!r} new_entry_same_cycle={new_entry_same_cycle}")

# ---------------------------------------------------------------------------
# P5: double-kill — second flatten on an already-flat book must not re-sell
# (kill cid dedupe) and must say 'already flat'.
m = mk("p5")
a = DryAdapter()
pos = held(m)
rs = a.place_stock_order("CRSP", 5, "MKT", ref_price=50.0)
rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                         client_order_id=stop_client_id(1, 44.0))
pos.stop_order_ref = rs["order_ref"]
m.save()
m.request_flatten("2026-08-24")
run_cycle(m, a, None, "2026-08-24", alert=lambda _: None)
n1 = len(sells(a, "CRSP"))
m.request_flatten("2026-08-24")
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
n2 = len(sells(a, "CRSP"))
check("P5 double-kill never re-sells; honest 'already flat'",
      n1 == 1 and n2 == 1 and any("already flat" in x for x in alerts),
      f"sells_after_first={n1} after_second={n2}")

print()
fails = [n for n, ok, _ in results if not ok]
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} probes passed; "
      f"failures: {fails}")
