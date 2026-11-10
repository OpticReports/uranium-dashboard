"""Counter-agent probes vs the Z1/Z2/y2 round (e750abd..98ffe0d).

Contract under attack (from x1x4_counter_verdict.md ADDENDUM):
  INVARIANT: at the end of every reconcile, per symbol, total blend-placed
  RESTING SELL cover must not exceed venue-verified `held`, and the executor
  must never CHOOSE to leave cover > held.
  Allocation: floor(held*qty/book_qty), remainder by largest fractional part
  then lowest call_id; 0 -> retire + stop_missing; strictly-reducing resizes
  carved out of Y1; reduction order cancel-old-then-place-smaller; do not
  enforce through a venue that will not ACK.

Run from ibkr-executor/.  A FAIL is a landed attack.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")

from app import blend as blend_mod                          # noqa: E402
from app.blend import (Blend3070Manager, run_cycle,          # noqa: E402
                       stop_client_id, reconcile,
                       _prorata_cover, _resting_cover)
from app.ib_adapter import DryAdapter                        # noqa: E402


class Cfg:
    dry_run = True
    trading_mode = "paper"
    blend_budget = 0.0
    blend_book_usd = 10_000.0
    tracker_url = ""
    tracker_user = ""
    tracker_password = ""
    tws_userid = ""
    tws_password = ""


def mk(name, d=None):
    d = d or tempfile.mkdtemp()
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
                 fill, f"entry-ref-{call_id}", "2026-08-01")
    pos = m.state.positions[str(call_id)]
    pos.time_stop = "2026-12-30"
    return pos


def rest_stop(m, a, call_id=1, symbol="CRSP", qty=5, level=44.0):
    rs = a.place_stock_order(symbol, -qty, "STP", stop_price=level, tif="GTC",
                             client_order_id=stop_client_id(call_id, level))
    m.state.positions[str(call_id)].stop_order_ref = rs["order_ref"]
    m.save()
    return rs["order_ref"]


def blackout(m):
    m.state.last_reconcile_ts = time.time() - 3 * 86_400


def stop_row(level=44.0, call_id=1, symbol="CRSP"):
    return {"call_id": call_id, "symbol": symbol, "trail_level": level}


def cover_at_venue(a, sym="CRSP"):
    return sum(-o["qty"] for o in a._stops.values() if o["symbol"] == sym)


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name
          + ("\n     | " + detail if detail else ""))


NULL = lambda *_a, **_k: None                                # noqa: E731


# =========================================================================
# Z-1  PURE ALLOCATION: re-derive the pro-rata table by hand.
# =========================================================================
class P:
    def __init__(self, cid, q):
        self.call_id, self.qty = cid, q


def alloc(pairs, h):
    return _prorata_cover([P(c, q) for c, q in pairs], h)


cases = [
    # (peers, held, expected)  -- hand-derived
    ([(1, 5), (2, 4)], 6, {"1": 3, "2": 3}),      # .333/.667 -> 2 gets rem
    ([(1, 5), (2, 4), (3, 3)], 9, {"1": 4, "2": 3, "3": 2}),   # x5 gate
    ([(1, 5), (2, 5)], 5, {"1": 3, "2": 2}),      # .5/.5 tie -> lowest cid
    ([(1, 5), (2, 4)], 0, {"1": 0, "2": 0}),      # held == 0
    ([(1, 5), (2, 4), (3, 3)], 1, {"1": 1, "2": 0, "3": 0}),   # 1 / 3 peers
    ([(1, 1), (2, 1), (3, 1), (4, 1)], 2, {"1": 1, "2": 1, "3": 0, "4": 0}),
    ([(1, 1), (2, 1), (3, 1)], 5, {"1": 2, "2": 2, "3": 1}),   # held > book!
]
bad = []
for pairs, h, exp in cases:
    got = alloc(pairs, h)
    if got != exp:
        bad.append((pairs, h, exp, got))
check("Z-1 pro-rata table matches a hand derivation (incl. held=0, "
      "held=1/3 peers, more peers than shares, exact ties)",
      not bad, f"mismatches={bad}")

check("Z-1b allocation NEVER sums above held and never exceeds a "
      "position's own qty",
      all(sum(alloc(p, h).values()) <= h
          and all(alloc(p, h)[str(c)] <= q for c, q in p)
          for p, h in [(c[0], c[1]) for c in cases] + [([(1, 5), (2, 4)], 3)]),
      f"held>book case sums to {sum(alloc([(1,1),(2,1),(3,1)],5).values())} "
      f"for held=5 book=3 -> allocation EXCEEDS each position's qty "
      f"({alloc([(1,1),(2,1),(3,1)],5)})")

check("Z-1c qty 0 / negative in the peer list cannot produce negative or "
      "runaway cover",
      alloc([(1, 0), (2, 4)], 2) == {"1": 0, "2": 2}
      and all(v >= 0 for v in alloc([(1, -3), (2, 4)], 2).values()),
      f"zero_qty={alloc([(1,0),(2,4)],2)} neg_qty={alloc([(1,-3),(2,4)],2)}")


# =========================================================================
# Z-2  BASELINE: the prescribed repro (book 9 / held 6, two flagged peers).
# =========================================================================
m = mk("z2")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
o1 = rest_stop(m, a, 1, "CRSP", 5, 44.0)
o2 = rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6
blackout(m)
al = []
run_cycle(m, a, None, "2026-08-24", alert=al.append)
c1 = cover_at_venue(a)
for r in list(a._stops):
    a.trigger_stop(r)
run_cycle(m, a, None, "2026-08-25", alert=NULL)
check("Z-2 baseline repro: cover resized to held, triggering everything "
      "cannot short the account",
      c1 == 6 and a._positions["CRSP"] >= 0,
      f"cover_after_resize={c1} venue_after_triggers={a._positions['CRSP']}")


# =========================================================================
# Z-3  RATCHET-DOWN MONOTONICITY over a FLUCTUATING held (churn hunt).
#      held: 6 -> 5 -> 6 -> 4 -> 7 -> 4 .  Cover must never creep UP while
#      the position stays flagged, and the executor must not cancel/place
#      every cycle when nothing changed.
# =========================================================================
m = mk("z3")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 44.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 44.0)
blackout(m)
seq = [6, 5, 6, 4, 7, 4]
covers, places = [], []
for i, h in enumerate(seq):
    a._positions["CRSP"] = h
    n0 = len([e for e in a.log if e["action"] == "place_stock_order"])
    run_cycle(m, a, None, f"2026-08-{24 + i}", alert=NULL)
    places.append(len([e for e in a.log
                       if e["action"] == "place_stock_order"]) - n0)
    covers.append(cover_at_venue(a))
mono = all(covers[i + 1] <= covers[i] for i in range(len(covers) - 1))
never_above = all(c <= h for c, h in zip(covers, seq))
check("Z-3 cover ratchets DOWN monotonically under a fluctuating held and "
      "never creeps up; no cancel/place churn on an unchanged shortfall",
      mono and never_above and places[2] == 0 and places[4] == 0,
      f"held_seq={seq} cover_seq={covers} places_per_cycle={places}")


# =========================================================================
# Z-4  PARTIALLY-FILLED PEER: a resized stop that fills at its RESIZED size
#      must book a PARTIAL, never the whole position.
# =========================================================================
m = mk("z4")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=NULL)
p1 = m.state.positions["1"]
cash0 = m.state.sleeve_cash
ref1 = p1.stop_order_ref
cov1 = p1.stop_cover_qty
a.trigger_stop(ref1)                       # the RESIZED stop fills in full
run_cycle(m, a, None, "2026-08-25", alert=NULL)
p1b = m.state.positions.get("1")
check("Z-4 a resized stop that fills books ONLY the shares it covered "
      "(partial), never the full position",
      p1b is not None and p1b.qty == 5 - cov1,
      f"cover_was={cov1} qty_after={getattr(p1b, 'qty', 'GONE')} "
      f"(expected {5 - cov1}) cash {cash0:.2f} -> {m.state.sleeve_cash:.2f}")


# =========================================================================
# Z-5  THE 1b-i GUARD IS KEYED ON THE WRONG FIELD.
#      A RESIZED stop that fills INSIDE a blackout (fill poll misses it, the
#      exact premise 1b-i exists for) still has stop_order_ref set and
#      stop_missing False -> the guard lets it through and on_exited books
#      the FULL pos.qty.  That is "credit proceeds for shares the venue
#      never sold" -- the very thing the implementer said they fixed.
# =========================================================================
m = mk("z5")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=NULL)
p1 = m.state.positions["1"]
cov = p1.stop_cover_qty
cash0 = m.state.sleeve_cash
a.trigger_stop(p1.stop_order_ref)          # fills `cov` shares
a._fills.clear()                           # ...and the poll NEVER sees it
blackout(m)                                # second gap: 1b-i is the path
al5 = []
run_cycle(m, a, None, "2026-08-26", alert=al5.append)
booked = m.state.sleeve_cash - cash0
gone = "1" not in m.state.positions
check("Z-5 a blackout-window fill of a RESIZED stop is not booked as a "
      "FULL exit (no proceeds for shares the venue never sold)",
      not gone and booked <= cov * 44.0 + 1e-6,
      f"cover_was={cov} of qty 5; position_removed={gone} "
      f"sleeve_cash credited={booked:.2f} (venue sold {cov} @ 44.00 = "
      f"{cov * 44.0:.2f}); "
      f"alerts={[x[:110] for x in al5 if 'CRSP' in x][:3]}")


# =========================================================================
# Z-6  DURABILITY vs AN UNFLAGGED PEER.  The resize spans unflagged peers
#      (deviation 2) but nothing keeps their cover reduced: pass 4 and the
#      daily ratchet both re-place pos.qty.
#      Z-6a: replace rejected for the UNFLAGGED peer -> pass 4 restores FULL
#            cover in the SAME reconcile.
#      Z-6b: replace succeeds -> the next trail ratchet restores FULL cover.
# =========================================================================
class _RejectOnce(DryAdapter):
    """Reject exactly the resize replacement for call 2 (the unflagged peer)."""
    def __init__(self):
        super().__init__()
        self.armed = False

    def place_stock_order(self, symbol, qty, order_type, **kw):
        if (self.armed and order_type == "STP"
                and kw.get("client_order_id") == stop_client_id(2, 43.0)):
            self.armed = False
            raise RuntimeError("resize replace rejected (simulated)")
        return super().place_stock_order(symbol, qty, order_type, **kw)


def mixed_book(adapter):
    """pos1 CRSP x5 FLAGGED, pos2 CRSP x4 UNFLAGGED (the state pass 2 leaves
    behind when a crash-window entry is adopted while a peer is parked)."""
    mm = mk("z6", tempfile.mkdtemp())
    held(mm, 1, "CRSP", 5, 50.0, 44.0)
    held(mm, 2, "CRSP", 4, 50.0, 43.0)
    rest_stop(mm, adapter, 1, "CRSP", 5, 44.0)
    rest_stop(mm, adapter, 2, "CRSP", 4, 43.0)
    mm.state.positions["1"].history_gap = True        # only pos1 is flagged
    mm.state.last_reconcile_ts = time.time()          # NO fresh blackout
    mm.save()
    return mm


a = _RejectOnce()
m = mixed_book(a)
a._positions["CRSP"] = 6
a.armed = True
al6 = []
reconcile(m, a, "2026-08-24", al6.append)
cov_a = cover_at_venue(a)
check("Z-6a a rejected resize replace on an UNFLAGGED peer is undone by "
      "pass 4 in the SAME reconcile (cover back above held)",
      cov_a <= 6,
      f"venue_held=6 cover_after_reconcile={cov_a} "
      f"stops={[(o['qty'], o['stop_price']) for o in a._stops.values()]} "
      f"restored_alert={any('protective stop restored' in x for x in al6)}")

a = DryAdapter()
m = mixed_book(a)
a._positions["CRSP"] = 6
run_cycle(m, a, None, "2026-08-24", alert=NULL)
cov_b0 = cover_at_venue(a)
# day 2: the tracker publishes a normal ratchet for the UNFLAGGED peer
run_cycle(m, a, payload(stops=[stop_row(call_id=2, level=45.0)]),
          "2026-08-25", alert=NULL)
cov_b1 = cover_at_venue(a)
venue_before = a._positions["CRSP"]
for r in list(a._stops):
    a.trigger_stop(r)
run_cycle(m, a, None, "2026-08-26", alert=NULL)
check("Z-6b the daily trail ratchet on an UNFLAGGED peer restores FULL "
      "cover and re-opens the naked short Z1 closed",
      cov_b1 <= 6 and a._positions["CRSP"] >= 0,
      f"cover_after_resize={cov_b0} cover_after_ratchet={cov_b1} "
      f"(held=6) venue {venue_before} -> {a._positions['CRSP']}")


# =========================================================================
# Z-7  UNCOVERED WINDOW.  cancel ACKs, then the replace fails.
#      Z-7a: replace RAISES -> position uncovered, loud, and RETRIED.
#      Z-7b: replace returns `duplicate` -> not adopted, tracked, loud.
#      Z-7c: cancel returns False -> a smaller stop must NOT be placed.
# =========================================================================
class _RaiseReplace(DryAdapter):
    def place_stock_order(self, symbol, qty, order_type, **kw):
        if order_type == "STP" and kw.get("client_order_id", "").startswith(
                stop_client_id(1, 44.0)):
            if getattr(self, "_seeded", False):
                raise RuntimeError("replace rejected (simulated)")
        return super().place_stock_order(symbol, qty, order_type, **kw)


a = _RaiseReplace()
m = mk("z7a")
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._seeded = True
a._positions["CRSP"] = 6
blackout(m)
al7 = []
run_cycle(m, a, None, "2026-08-24", alert=al7.append)
p1 = m.state.positions["1"]
naked_c1 = p1.stop_missing and not p1.stop_order_ref
loud = any("UNPROTECTED" in x for x in al7)
# next cycle: is the protection ever retried?
a._seeded = False                      # the venue would accept it now
run_cycle(m, a, None, "2026-08-25", alert=NULL)
p1 = m.state.positions["1"]
retried = bool(p1.stop_order_ref) and not p1.stop_missing
check("Z-7a cancel ACKed + replace REJECTED leaves the position bare AND "
      "LOUD (accepted), and the alert text is honest",
      naked_c1 and loud,
      f"stop_missing={p1.stop_missing} loud={loud}")
check("Z-7a(retry) the README claims 'retried next cycle' — verify the "
      "protection is actually restored once the venue would accept it",
      retried,
      f"cycle2 stop_order_ref={p1.stop_order_ref} "
      f"stop_missing={p1.stop_missing} cover_at_venue={cover_at_venue(a)} "
      f"(held=6) -- DEVIATION 1: there is NO retry while flagged")


class _DupReplace(DryAdapter):
    def place_stock_order(self, symbol, qty, order_type, **kw):
        if (order_type == "STP" and getattr(self, "_seeded", False)
                and kw.get("client_order_id") == stop_client_id(1, 44.0)):
            return {"order_ref": "ghost-existing", "status": "working",
                    "duplicate": True}
        return super().place_stock_order(symbol, qty, order_type, **kw)


a = _DupReplace()
m = mk("z7b")
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._seeded = True
a._positions["CRSP"] = 6
blackout(m)
al7b = []
run_cycle(m, a, None, "2026-08-24", alert=al7b.append)
p1 = m.state.positions["1"]
check("Z-7b a `duplicate` answer to the resize replace is NOT adopted: "
      "tracked as an orphan, position left UNPROTECTED and loud",
      p1.stop_order_ref != "ghost-existing"
      and "ghost-existing" in m.state.orphan_stop_refs
      and any("UNKNOWN size" in x for x in al7b),
      f"ref={p1.stop_order_ref} orphans={sorted(m.state.orphan_stop_refs)}")


class _NoAckCancel(DryAdapter):
    def cancel_stock_order(self, order_ref):
        rec = self._orders.get(order_ref)
        if rec is not None and rec.get("client_order_id") == \
                stop_client_id(1, 44.0):
            self._rec("cancel_stock_order", ref=order_ref, found=False)
            return False               # "already gone" -- but it still rests
        return super().cancel_stock_order(order_ref)


a = _NoAckCancel()
m = mk("z7c")
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
old1 = rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6
blackout(m)
al7c = []
run_cycle(m, a, None, "2026-08-24", alert=al7c.append)
placed_for_1 = [e for e in a.log if e["action"] == "place_stock_order"
                and e.get("order_type") == "STP" and e.get("ref") != old1]
p1_7c = m.state.positions["1"]
head7c = [x for x in al7c if "RESIZED" in x and "cover" in x]
check("Z-7c a cancel the venue will NOT ACK must never be followed by a "
      "smaller stop stacked on top of it, and the headline must not claim "
      "a cover the venue refused to release",
      p1_7c.stop_order_ref is None and p1_7c.stop_missing
      and old1 in m.state.orphan_stop_refs
      and head7c and "may STILL rest" in head7c[0],
      f"call1 ref={p1_7c.stop_order_ref} missing={p1_7c.stop_missing} "
      f"orphans={sorted(m.state.orphan_stop_refs)} "
      f"places={[(e['qty'], e['ref']) for e in placed_for_1]} "
      f"headline={head7c[0][:330] if head7c else 'NONE'!r}")


# =========================================================================
# Z-8  CRASH BETWEEN CANCEL AND PLACE.  stop_cover_qty / stop_missing must
#      persist and the reload must not believe the position is covered.
# =========================================================================
class _DieAfterCancel(DryAdapter):
    def place_stock_order(self, symbol, qty, order_type, **kw):
        if (order_type == "STP" and getattr(self, "_seeded", False)
                and kw.get("client_order_id") == stop_client_id(1, 44.0)):
            raise SystemExit("process died between cancel and place")
        return super().place_stock_order(symbol, qty, order_type, **kw)


a = _DieAfterCancel()
d = tempfile.mkdtemp()
m = mk("z8", d)
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._seeded = True
a._positions["CRSP"] = 6
blackout(m)
died = False
try:
    run_cycle(m, a, None, "2026-08-24", alert=NULL)
except SystemExit:
    died = True
m2 = Blend3070Manager(Cfg(), os.path.join(d, "z8.json"))
p1r = m2.state.positions.get("1")
check("Z-8 a crash between the cancel and the place persists the naked "
      "state (stop_missing) — the reload never believes it is covered",
      died and p1r is not None and p1r.stop_missing
      and not p1r.stop_order_ref,
      f"died={died} reloaded stop_missing={getattr(p1r,'stop_missing',None)} "
      f"ref={getattr(p1r,'stop_order_ref',None)} "
      f"cover_qty={getattr(p1r,'stop_cover_qty',None)}")

# ...and does the restart RECOVER protection?
a._seeded = False
m2.state.last_reconcile_ts = m.state.last_reconcile_ts
run_cycle(m2, a, None, "2026-08-25", alert=NULL)
p1r = m2.state.positions.get("1")
check("Z-8b restart reconcile RESTORES cover for the position left bare by "
      "the crash",
      bool(p1r.stop_order_ref) and not p1r.stop_missing,
      f"after_restart_cycle ref={p1r.stop_order_ref} "
      f"missing={p1r.stop_missing} cover_at_venue={cover_at_venue(a)}")


# =========================================================================
# Z-9  SCHEMA DRIFT ON THE BLEND BOOK.  Z1 added `stop_cover_qty` to
#      BlendPosition.  y2's own premise (a deploy ROLLBACK reads rows a
#      newer build wrote) applies verbatim here — and _load has no field
#      filter and does NOT halt.
# =========================================================================
d = tempfile.mkdtemp()
m = mk("z9", d)
held(m, 1, "CRSP", 5, 50.0, 44.0)
m.save()
raw = json.load(open(m.state_path))
raw["positions"]["1"]["a_field_a_newer_build_wrote"] = 1
json.dump(raw, open(m.state_path, "w"))
m3 = Blend3070Manager(Cfg(), os.path.join(d, "z9.json"))
check("Z-9 a blend-book row written by a NEWER build does not silently "
      "vaporize open positions (y2's fix applied to the ladder; the blend "
      "book gained a new field in the same round)",
      bool(m3.state.positions) or m3.state.halted,
      f"positions_after_rollback={sorted(m3.state.positions)} "
      f"halted={m3.state.halted!r} initialized={m3.state.initialized} "
      f"archived={str(m3.archived_state)[:90]!r} "
      f"entries_blocked={m3.has_naked_position()}")


# =========================================================================
# Z-10 CONFLATION AFTER A RESIZE: the escalation alert must not claim the
#      stop covers the position when it only covers part of it.
# =========================================================================
m = mk("z10")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=NULL)
a._positions["CRSP"] = 20                     # external shares arrive
al10 = []
for i in range(6):                            # ride out the re-arm cadence
    run_cycle(m, a, None, f"2026-08-{25 + i}", alert=al10.append)
esc = [x for x in al10 if "UNRESOLVED after the blackout" in x
       and "call 1)" in x]
p1 = m.state.positions["1"]
check("Z-10 once conflated, an escalation about a RESIZED stop must not "
      "read as full protection",
      p1.stop_cover_qty and esc
      and all("RESIZED protective stop" in x for x in esc),
      f"cover_qty={p1.stop_cover_qty} of qty={p1.qty}; "
      f"esc={[x[:250] for x in esc][:1]}")


# =========================================================================
# Z-11 Z2 HONESTY: every alert string the round touched.
# =========================================================================
m = mk("z11")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
r = rest_stop(m, a, 1, "CRSP", 5, 44.0)
m.state.positions["1"].history_gap = True
m.state.last_reconcile_ts = time.time()
a._positions["CRSP"] = 5
m.save()
a.trigger_stop_partial(r, 2)
al11 = []
run_cycle(m, a, None, "2026-08-25", alert=al11.append)
part = [x for x in al11 if "PARTIAL fill" in x]
check("Z-11 the partial-fill alert on an UNVERIFIABLE position tells the "
      "operator what happens to the remaining shares and flags the "
      "conflation risk",
      part and "NO stop will be re-placed" in part[0]
      and "UNVERIFIABLE" in part[0],
      f"alert={part[0][:340] if part else 'NONE'!r}")

# full stop fill on an UNVERIFIABLE position: never a plain green close
m = mk("z11b")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
r = rest_stop(m, a, 1, "CRSP", 5, 44.0)
m.state.positions["1"].history_gap = True
m.state.last_reconcile_ts = time.time()
a._positions["CRSP"] = 5
m.save()
a.trigger_stop(r)
al11b = []
run_cycle(m, a, None, "2026-08-25", alert=al11b.append)
fill = [x for x in al11b if "FILLED" in x.upper() and "CRSP" in x]
check("Z-11b a full stop fill on an UNVERIFIABLE position is never a plain "
      "green 'position closed'",
      fill and "UNVERIFIABLE" in fill[0] and not fill[0].startswith("🧬"),
      f"alert={fill[0][:300] if fill else 'NONE'!r}")


# =========================================================================
# Z-12 REACHABILITY of the mixed flagged/unflagged same-symbol pair that
#      Z-6 needs.  Pass 2 adopts a crash-window entry as a BRAND NEW
#      position with history_gap=False while a same-symbol peer is still
#      parked -- no hand-editing of state required.
# =========================================================================
m = mk("z12")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
# a journaled MOO for call 2 that FILLED at the venue during the blackout
it = {"call_id": 2, "symbol": "CRSP", "qty": 4, "entry_ref": 50.0,
      "stop_level": 43.0, "reason": "fire"}
m.record_pending_entry(it, "2026-08-20")
from app.blend import entry_client_id                       # noqa: E402
a.place_stock_order("CRSP", 4, "MOO", ref_price=50.0,
                    client_order_id=entry_client_id(2))
a._positions["CRSP"] = 9
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=NULL)
flags = {k: p.history_gap for k, p in m.state.positions.items()}
check("Z-12 a mixed FLAGGED/UNFLAGGED same-symbol pair arises with no "
      "hand-editing (crash-window entry adoption, reconcile pass 2)",
      flags == {"1": True, "2": False},
      f"history_gap by call = {flags}")
# ...and now the shortfall appears, with the unflagged peer in the blend
a._positions["CRSP"] = 6                    # 3 sold by hand
al12 = []
run_cycle(m, a, None, "2026-08-25", alert=al12.append)
cov12 = cover_at_venue(a)
run_cycle(m, a, payload(stops=[stop_row(call_id=2, level=45.0)]),
          "2026-08-26", alert=NULL)
cov12b = cover_at_venue(a)
for r in list(a._stops):
    a.trigger_stop(r)
run_cycle(m, a, None, "2026-08-27", alert=NULL)
check("Z-12b END TO END from a clean book: shortfall -> resize -> one "
      "ordinary ratchet -> the account is SHORT again",
      cov12b <= 6 and a._positions["CRSP"] >= 0,
      f"cover_after_resize={cov12} cover_after_ratchet={cov12b} (held=6) "
      f"venue_after_all_triggers={a._positions['CRSP']}")


print()
ok = sum(1 for _n, c, _d in results if c)
print(f"{ok}/{len(results)} probes passed; landed attacks: "
      f"{[n for n, c, _d in results if not c]}")
