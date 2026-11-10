"""Counter-agent probes vs cde6fb7 (N1 stop retirement + N2 order-scoped
blackout verification). Run from ibkr-executor/.  Each probe asserts the
SAFE contract the commit claims; a FAIL is a landed attack."""
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")

from app.blend import (Blend3070Manager, run_cycle, stop_client_id)
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
    m.state.sleeve_cash = 5_000.0
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


def rest_stop(m, a, call_id=1, symbol="CRSP", qty=5, level=44.0):
    rs = a.place_stock_order(symbol, -qty, "STP", stop_price=level, tif="GTC",
                             client_order_id=stop_client_id(call_id, level))
    m.state.positions[str(call_id)].stop_order_ref = rs["order_ref"]
    m.save()
    return rs["order_ref"]


def blackout(m):
    m.state.last_reconcile_ts = time.time() - 3 * 86_400


def mkt_sells(a, sym):
    return [e for e in a.log if e.get("symbol") == sym
            and e["action"] == "place_stock_order"
            and e.get("order_type") in ("MKT", "MOO") and e["qty"] < 0]


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name
          + ("\n     | " + detail if detail else ""))


# ===========================================================================
# C1 — MATRIX CELL "held > booked + WORKING stop": the commit unparks it.
# Scenario the guard cannot distinguish from a healthy book: the operator's
# own 10 CRSP sit in the account; the blend's 5 were SOLD manually inside
# the blackout (broker nets from the pool), and the blend's -5 GTC stop was
# never touched, so it is still WORKING. held(10) >= book(5) + working stop
# => "POSITIVELY verified ... the shares are held" => unparked => the very
# next tracker EXIT market-sells 5 of the OPERATOR's shares and books a
# phantom exit. This is the same harm class as the N2/B2b path the commit
# claims to close; only the cancelled-stop variant was actually closed.
# ===========================================================================
m = mk("c1")
a = DryAdapter()
pos = held(m)
ref = rest_stop(m, a)
a._positions["CRSP"] = 10          # 10 EXTERNAL shares; blend's 5 sold in the dark
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
unparked = ("1" in m.state.positions
            and not m.state.positions["1"].history_gap)
verified_alert = next((x for x in alerts if "POSITIVELY verified" in x), "")
# now the tracker publishes an exit for the (phantom) position
alerts2 = []
run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                "reason": "gate_off"}]),
          "2026-08-24", alert=alerts2.append)
sold = mkt_sells(a, "CRSP")
venue_after = a._positions["CRSP"]
check("C1 conflated rows + working stop must not license a MKT sell "
      "(shares may be external)",
      not sold,
      f"unparked={unparked} mkt_sells={len(sold)} venue_CRSP_after="
      f"{venue_after} (10 external, blend owned 0) "
      f"booked_exit={'1' not in m.state.positions} "
      f"verified_alert={verified_alert[:120]!r}")

# C1b — honesty of that same alert: it asserts "the shares are held" on
# evidence (account-wide rows) that cannot establish ownership.
check("C1b alert must not assert 'the shares are held' from conflated rows",
      not ("the shares are\nheld" in verified_alert
           or "shares are held" in verified_alert),
      f"alert={verified_alert[:200]!r}")

# ===========================================================================
# C2 — SAME-SYMBOL PEERS. The commit claims resolving filled stops first
# "removes the old same-symbol-peer ambiguity branch". It does so only when
# the vanished position's stop actually FILLED. Here three same-symbol
# positions are flagged; the LAST one's shares left the account inside the
# blackout by another route (manual sale) while all three stops still rest.
# held < sum(book) is evaluated against a book_qty that mixes peers, so the
# FIRST position in dict order is sacrificed: its healthy working stop is
# CANCELLED and its real shares parked UNRECONCILED, while the position
# whose shares are actually gone is UNPARKED as verified.
# ===========================================================================
m = mk("c2")
a = DryAdapter()
p1 = held(m, call_id=1, qty=5, stop_level=44.0)
p2 = held(m, call_id=2, qty=4, stop_level=43.0)
p3 = held(m, call_id=3, qty=3, stop_level=42.0)
r1 = rest_stop(m, a, call_id=1, qty=5, level=44.0)
r2 = rest_stop(m, a, call_id=2, qty=4, level=43.0)
r3 = rest_stop(m, a, call_id=3, qty=3, level=42.0)
a._positions["CRSP"] = 9           # call 3's 3 shares sold manually in the dark
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
p1_parked = "1" in m.state.unreconciled
p3_unparked = ("3" in m.state.positions
               and not m.state.positions["3"].history_gap)
r1_gone = r1 not in a._stops
check("C2 same-symbol peers: the guard must not park/strip the WRONG "
      "position (order-dependent sacrifice)",
      not (p1_parked and p3_unparked),
      f"call1_parked_UNRECONCILED={p1_parked} call1_stop_cancelled={r1_gone} "
      f"call3_(actually_gone)_unparked={p3_unparked} "
      f"positions_left={sorted(m.state.positions)}")

# C2b — the park alert's UNPROTECTED count is book-wide `held`, not the
# shares actually left unprotected by the retire.
park = next((x for x in alerts if "parked for manual booking" in x), "")
check("C2b park alert's UNPROTECTED share count must not overstate",
      "9 share(s) remain at the venue UNPROTECTED" not in park,
      f"alert={park[:220]!r}")

# ===========================================================================
# C3 — N1 orphan lifetime. The commit's contract: an AMBIGUOUS (False)
# cancel "goes to orphan_stop_refs so pass 3 retries and a later fill
# routes to the RED 'retired stop FILLED — possible short' branch". But
# pass 3 runs in the SAME reconcile, pops the ref whenever cancel does not
# RAISE (its return value is ignored) and logs "cancelled on retry" — so
# the tracking survives zero cycles and the later fill lands in the plain
# UNKNOWN-order branch with no unreconciled record.
# ===========================================================================
class FalseCancel(DryAdapter):
    """Venue answers 'not found / already cancelled' (False) while the stop
    in fact keeps resting — precisely the ambiguity the contract cites."""

    def cancel_stock_order(self, ref):
        rec = self._orders.get(ref)
        if rec is not None and rec["status"] == "filled":
            raise RuntimeError(f"cannot cancel {ref}: order already FILLED")
        self._rec("cancel_stock_order", ref=ref, found=False)
        return False


m = mk("c3")
a = FalseCancel()
pos = held(m)
ref = rest_stop(m, a)
a._positions["CRSP"] = 2           # manual sale of 3 inside the blackout
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
tracked_after_cycle = ref in m.state.orphan_stop_refs
false_retry_claim = any("cancelled on retry" in e["msg"]
                        for e in m.state.events)
# the abandoned stop now triggers into a 2-share account
a.trigger_stop(ref)
alerts2 = []
run_cycle(m, a, None, "2026-08-25", alert=alerts2.append)
red = any("RETIRED stop" in x and "possible short" in x for x in alerts2)
unknown = any("UNKNOWN order" in x for x in alerts2)
check("C3 ambiguous cancel stays orphan-tracked so a later fill alerts RED",
      tracked_after_cycle and red,
      f"orphan_tracked_after_cycle={tracked_after_cycle} "
      f"'cancelled on retry'_logged={false_retry_claim} "
      f"RED_possible_short={red} plain_UNKNOWN_alert={unknown} "
      f"venue_net_after_trigger={a._positions['CRSP']} "
      f"unreconciled_keys={sorted(m.state.unreconciled)}")

# ===========================================================================
# C4 — the park alert claims "resting stop retired" UNCONDITIONALLY, even
# when the cancel raised and the stop demonstrably still rests.
# ===========================================================================
class RaisingCancel(DryAdapter):
    def cancel_stock_order(self, ref):
        raise RuntimeError("cancel unavailable (simulated network)")


m = mk("c4")
a = RaisingCancel()
pos = held(m)
ref = rest_stop(m, a)
a._positions["CRSP"] = 2
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
park = next((x for x in alerts if "parked for manual booking" in x), "")
could_not = any("could NOT be cancelled" in x for x in alerts)
check("C4 park alert must not claim 'resting stop retired' when the cancel "
      "failed",
      "resting\nstop retired" not in park and "stop retired" not in park,
      f"contradicting_alert_present={could_not} park={park[:230]!r}")

# C4b — the same raising cancel is retried by pass 3 in the SAME cycle,
# producing a second, differently-worded alert about the same order, and
# then every cycle forever (the pinned reading of a raise is "the stop
# FILLED", which can never be cancelled).
n_still = sum(1 for x in alerts if "STILL uncancelled" in x)
alerts_c2, alerts_c3 = [], []
run_cycle(m, a, None, "2026-08-25", alert=alerts_c2.append)
run_cycle(m, a, None, "2026-08-26", alert=alerts_c3.append)
check("C4b unretirable stop does not alert every cycle forever "
      "(bounded escalation)",
      not (any("STILL uncancelled" in x for x in alerts_c2)
           and any("STILL uncancelled" in x for x in alerts_c3)),
      f"same_cycle_duplicate_alerts={n_still} "
      f"cycle2={sum(1 for x in alerts_c2 if 'STILL uncancelled' in x)} "
      f"cycle3={sum(1 for x in alerts_c3 if 'STILL uncancelled' in x)} "
      f"orphans={sorted(m.state.orphan_stop_refs)}")

# ===========================================================================
# C5 — MATRIX CELL "positions UNAVAILABLE + working stop": the commit's
# declared deliberate deviation (stays flagged). Verify.
# ===========================================================================
class NoPositions(DryAdapter):
    def stock_position(self, symbol):
        raise RuntimeError("positions unavailable (simulated)")


m = mk("c5")
a = NoPositions()
pos = held(m)
ref = rest_stop(m, a)
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
still_flagged = m.state.positions["1"].history_gap
stop_kept = ref in a._stops
check("C5 positions unavailable keeps the flag AND keeps the stop working",
      still_flagged and stop_kept,
      f"history_gap={still_flagged} stop_still_resting={stop_kept}")

# ===========================================================================
# C6 — MATRIX CELL "held == booked, stop cancelled": unpark + pass 4 must
# re-place a stop for the RIGHT quantity in the SAME cycle, and the state
# must be left consistent (stop_missing cleared once placed).
# ===========================================================================
m = mk("c6")
a = DryAdapter()
pos = held(m)
ref = rest_stop(m, a)
a.cancel_stock_order(ref)          # IB-initiated GTC cancel in the blackout
a._positions["CRSP"] = 5           # exactly the booked shares
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
p = m.state.positions.get("1")
new_stops = [e for e in a.log if e["action"] == "place_stock_order"
             and e.get("order_type") == "STP" and e["ref"] != ref]
qty_ok = bool(new_stops) and new_stops[-1]["qty"] == -5
check("C6 held==booked + dead stop -> unparked and RE-PROTECTED this cycle",
      p is not None and not p.history_gap and not p.stop_missing
      and p.stop_order_ref and qty_ok,
      f"history_gap={getattr(p, 'history_gap', None)} "
      f"stop_missing={getattr(p, 'stop_missing', None)} "
      f"new_stop_qty={new_stops[-1]['qty'] if new_stops else None}")

# ===========================================================================
# C7 — MATRIX CELL "stop filled + UNPRICED while the venue still holds
# shares". 1b-i parks the whole position without ever looking at the venue
# quantity, and the alert never states it — the operator is not told that
# shares remain (unprotected) at the venue, unlike the held<booked branch
# which does say so.
# ===========================================================================
m = mk("c7")
a = DryAdapter()
pos = held(m)
ref = rest_stop(m, a)
a._orders[ref]["status"] = "filled"        # filled, price unknown
a._stops.pop(ref, None)
a._positions["CRSP"] = 3                   # 3 shares STILL at the venue
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
park = next((x for x in alerts if "NO fill price" in x), "")
check("C7 filled+unpriced park states the shares still at the venue",
      "3" in park and ("UNPROTECTED" in park or "holds" in park),
      f"venue_still_holds={a._positions['CRSP']} alert={park[:230]!r}")

# ===========================================================================
# C8 — cid scoping: _retire_blackout_stop must never touch a peer's stop
# THROUGH THE WRONG CLIENT ID.  Two same-symbol positions, same stop LEVEL,
# different call ids; the account holds 5 of the 10 booked.
#
# REWRITTEN for the Z1 contract (this is the peer-shortfall cell, x5).  The
# old assertion — "r2 must still be resting" — pinned a mechanic Z1 legally
# replaces: leaving 5+5 = 10 shares of SELL stops against 5 held is exactly
# the venue short Z1 closes, so BOTH stops are resized pro rata.  The
# cid-scoping property C8 exists to protect is asserted directly instead,
# and harder: each position's OWN order is the one cancelled, each keeps a
# distinct order of its own allocated size, the tie is broken by lowest
# call_id (3/2, never 2/2 or 3/3), aggregate cover == held, and triggering
# everything cannot short the account.
# ===========================================================================
m = mk("c8")
a = DryAdapter()
held(m, call_id=1, qty=5, stop_level=44.0)
held(m, call_id=2, qty=5, stop_level=44.0)
r1 = rest_stop(m, a, call_id=1, qty=5, level=44.0)
r2 = rest_stop(m, a, call_id=2, qty=5, level=44.0)
a._positions["CRSP"] = 5
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=lambda _: None)
p1 = m.state.positions.get("1")
p2 = m.state.positions.get("2")
covers = {k: -a._stops[p.stop_order_ref]["qty"]
          for k, p in (("1", p1), ("2", p2))
          if p is not None and p.stop_order_ref in a._stops}
# each position's own cid still addresses its own order — never the peer's
own = {k: a.find_stock_order(stop_client_id(int(k), 44.0)) for k in ("1", "2")}
cid_scoped = all(own[k] is not None
                 and own[k]["order_ref"] == m.state.positions[k].stop_order_ref
                 for k in ("1", "2") if k in m.state.positions)
distinct = (p1 is not None and p2 is not None
            and p1.stop_order_ref != p2.stop_order_ref)
retired_own = (r1 not in a._stops and r2 not in a._stops
               and a._orders[r1]["status"] == "cancelled"
               and a._orders[r2]["status"] == "cancelled")
before = a._positions["CRSP"]
for ref in list(a._stops):
    a.trigger_stop(ref)
run_cycle(m, a, None, "2026-08-25", alert=lambda _: None)
check("C8 retire is cid-scoped: a peer's stop is never cancelled through "
      "the wrong client id, and the resize cannot short the account",
      covers == {"1": 3, "2": 2} and cid_scoped and distinct and retired_own
      and sum(covers.values()) == 5 and a._positions["CRSP"] >= 0,
      f"covers={covers} cid_scoped={cid_scoped} distinct={distinct} "
      f"retired_own={retired_own} "
      f"venue {before} -> {a._positions['CRSP']} "
      f"positions={sorted(m.state.positions)} "
      f"unreconciled={sorted(m.state.unreconciled)}")

# ===========================================================================
# C9 — RACE: the stop fills BETWEEN the 1b-i order lookup and the 1b-ii
# positions read. gap_stops holds a stale 'working'; positions already show
# the sale. Must fail closed (no sell, no fresh stop) and must not leave a
# phantom believed protected.
# ===========================================================================
class RaceBetweenSubPasses(DryAdapter):
    def __init__(self):
        super().__init__()
        self.race_ref = None
        self.raced = False

    def stock_position(self, symbol):
        if not self.raced and self.race_ref in self._stops:
            self.raced = True
            self.trigger_stop(self.race_ref)   # fills AFTER the order lookup
        return super().stock_position(symbol)


m = mk("c9")
a = RaceBetweenSubPasses()
pos = held(m)
a._positions["CRSP"] = 5
ref = rest_stop(m, a)
a.race_ref = ref
blackout(m)
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
c1_state = ("held" if "1" in m.state.positions else
            ("unreconciled" if "1" in m.state.unreconciled else "closed"))
alerts2 = []
run_cycle(m, a, None, "2026-08-25", alert=alerts2.append)
booked = any(t.get("kind") == "stop_filled" for t in m.state.trades)
check("C9 stop filling between the two sub-passes: no sell, resolves to a "
      "booked exit or an honest park",
      not mkt_sells(a, "CRSP")
      and ("1" not in m.state.positions)
      and (booked or "1" in m.state.unreconciled),
      f"after_c1={c1_state} booked_at_stop={booked} "
      f"unreconciled={sorted(m.state.unreconciled)} "
      f"mkt_sells={len(mkt_sells(a, 'CRSP'))}")

# ===========================================================================
# C10 — /kill on a conflated-but-"verified" position (C1 state): once
# unparked the kill path MKT-sells shares whose ownership was never proven.
# ===========================================================================
m = mk("c10")
a = DryAdapter()
pos = held(m)
ref = rest_stop(m, a)
a._positions["CRSP"] = 10          # all external; blend's 5 gone in the dark
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=lambda _: None)
m.request_flatten("2026-08-24")
alerts = []
run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
check("C10 /kill must not flatten a position verified only by conflated "
      "account rows",
      not mkt_sells(a, "CRSP"),
      f"kill_sells={len(mkt_sells(a, 'CRSP'))} "
      f"venue_CRSP_after={a._positions['CRSP']} "
      f"summary={next((x for x in alerts if 'kill flatten' in x), '')[:140]!r}")

# ===========================================================================
# C11 — LIVENESS/LAW-3: the new fail-closed cell (conflated rows + a stop
# that no longer works) leaves a REAL position with NO stop at the venue,
# stop_missing=False, a stale stop_order_ref, and ZERO alerts after the
# first cycle — indefinitely. Order-safety law #3 says a position without
# a working protective stop is STOP_MISSING: "alerted loudly, retried
# every cycle". Trigger is ONE extra same-symbol share in the account.
# ===========================================================================
m = mk("c11")
a = DryAdapter()
pos = held(m)
ref = rest_stop(m, a)
a.cancel_stock_order(ref)          # IB-initiated GTC cancel inside the blackout
a._positions["CRSP"] = 6           # the book's 5 + ONE external share
blackout(m)
cycle_alerts = []
for c in range(6):
    al = []
    run_cycle(m, a, None, "2026-08-%02d" % (24 + c), alert=al.append)
    cycle_alerts.append(len(al))
    m.state.last_reconcile_ts = time.time()      # normal cadence from here
p = m.state.positions.get("1")
check("C11 a real position left with no working stop must stay LOUD "
      "(law #3: STOP_MISSING, alerted every cycle)",
      p is None or len(a._stops) > 0 or sum(cycle_alerts[1:]) > 0,
      f"history_gap={getattr(p, 'history_gap', None)} "
      f"stop_missing={getattr(p, 'stop_missing', None)} "
      f"stale_stop_ref={bool(getattr(p, 'stop_order_ref', None))} "
      f"stops_resting_at_venue={len(a._stops)} "
      f"alerts_per_cycle={cycle_alerts}")

print()
fails = [n for n, ok, _ in results if not ok]
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} probes passed; "
      f"landed attacks: {fails}")
