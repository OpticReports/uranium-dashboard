"""Counter-agent RE-REVIEW probes vs 9fddbed (X1-X4 fix round answering the
cde6fb7 FAIL verdict).  Run from ibkr-executor/.  Each probe asserts the
contract the fix round CLAIMS; a FAIL is a landed attack.

Claimed contract for `held > book_qty` (conflation):
  stay flagged always, never unpark, never MKT-sell, never rest a NEW stop;
  a working stop is left resting; a dead stop -> stop_missing=True + ref
  dropped; re-armed escalating alert every UNVERIFIED_REALERT_CYCLES;
  surfaced in /status, /blend/feed and the Execution tab.
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, ".")

from app import blend as blend_mod
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


def mkt_sells(a, sym):
    return [e for e in a.log if e.get("symbol") == sym
            and e["action"] == "place_stock_order"
            and e.get("order_type") in ("MKT", "MOO") and e["qty"] < 0]


def new_stops(a, sym):
    return [e for e in a.log if e.get("symbol") == sym
            and e["action"] == "place_stock_order"
            and e.get("order_type") == "STP"]


EXIT_CRSP = {"symbol": "CRSP", "call_id": 1, "reason": "gate_off"}


def stop_row(level=44.0, call_id=1, symbol="CRSP"):
    return {"call_id": call_id, "symbol": symbol, "trail_level": level}


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name
          + ("\n     | " + detail if detail else ""))


# ==========================================================================
# X-A  CONFLATION MATRIX.  held > book_qty for every stop state.  For each
#      cell the claimed contract is identical: never unpark, never sell
#      (exit OR /kill), never rest a NEW stop, never silent.
# ==========================================================================
def conflate_cell(kind):
    """kind in {'working','dead','unknown'} -> the venue state of the
    position's own protective stop under conflation."""
    m = mk("xa-" + kind)
    a = DryAdapter()
    held(m)
    ref = rest_stop(m, a)
    if kind == "dead":
        a.cancel_stock_order(ref)               # IB-initiated GTC cancel
    if kind == "unknown":
        # the venue has no record of the order at all (find_stock_order
        # -> None): a restart against a venue that pruned its history
        a._orders.pop(ref, None)
        a._by_client.pop(stop_client_id(1, 44.0), None)
        a._stops.pop(ref, None)
    a._positions["CRSP"] = 12                   # 5 booked + 7 EXTERNAL
    blackout(m)
    return m, a, ref


for kind in ("working", "dead", "unknown"):
    m, a, ref = conflate_cell(kind)
    al = []
    run_cycle(m, a, None, "2026-08-24", alert=al.append)
    pos = m.state.positions.get("1")
    stops_before = len(new_stops(a, "CRSP"))
    # (1) tracker exit must not sell
    al2 = []
    run_cycle(m, a, payload(exits=[EXIT_CRSP], stops=[stop_row()]),
              "2026-08-24", alert=al2.append)
    # (2) /kill must not sell
    m.request_flatten("2026-08-24")
    al3 = []
    run_cycle(m, a, None, "2026-08-24", alert=al3.append)
    sold = mkt_sells(a, "CRSP")
    check(f"X-A[{kind}] conflated cell: no unpark, no sell (exit or /kill), "
          f"no NEW stop",
          pos is not None and pos.history_gap is True and not sold
          and a._positions["CRSP"] == 12
          and len(new_stops(a, "CRSP")) == stops_before,
          f"history_gap={pos.history_gap if pos else None} "
          f"stop_missing={pos.stop_missing if pos else None} "
          f"ref={'set' if (pos and pos.stop_order_ref) else 'None'} "
          f"mkt_sells={len(sold)} venue={a._positions['CRSP']} "
          f"new_stops={len(new_stops(a, 'CRSP')) - stops_before}")
    # the working cell must KEEP its real protection; the dead/unknown
    # cells must drop the stale ref and mark themselves unprotected
    if kind == "working":
        check("X-A[working] the real working stop is LEFT RESTING",
              ref in a._stops and pos.stop_order_ref == ref,
              f"resting={ref in a._stops} ref_kept={pos.stop_order_ref == ref}")
    else:
        check(f"X-A[{kind}] dead stop -> stop_missing + stale ref dropped",
              pos.stop_missing is True and pos.stop_order_ref is None,
              f"stop_missing={pos.stop_missing} ref={pos.stop_order_ref}")
    # (3) honesty: no ownership claim anywhere
    every = al + al2 + al3
    check(f"X-A[{kind}] never claims ownership / never silent on cycle 0",
          not any("POSITIVELY verified" in x or "the shares are held" in x
                  for x in every)
          and any("UNRESOLVED after the blackout" in x for x in al),
          f"ownership_claims=0 cycle0_escalations="
          f"{sum(1 for x in al if 'UNRESOLVED after the blackout' in x)}")
    # (4) /status + feed agree
    ss = m.status_summary()
    fd = m.feed({}, "2026-08-24")
    check(f"X-A[{kind}] /status and /blend/feed agree and surface it",
          ss["unverifiable"] == ["1"]
          and fd["unverifiable"] == len(ss["unverifiable"])
          and fd["unprotected"] == len(ss["stop_missing"])
          and fd["positions"][0]["unverifiable"] is True,
          f"status.unverifiable={ss['unverifiable']} "
          f"status.stop_missing={ss['stop_missing']} "
          f"feed.unverifiable={fd['unverifiable']} "
          f"feed.unprotected={fd['unprotected']} "
          f"pos_row={ {k: v for k, v in fd['positions'][0].items() if k in ('unverifiable', 'unprotected', 'unverified_cycles')} }")


# ==========================================================================
# X-B  ADJUST_STOP is the seam the X1 contract forgot.  step()'s trail
#      ratchet loop does NOT skip history_gap positions, so a tracker stop
#      row rests a BRAND NEW -qty SELL order on shares the fix just said
#      could not be proven to be the book's — and, on the dead-stop cell,
#      clears the stop_missing/ref-dropped state X3 introduced.
# ==========================================================================
for kind in ("working", "dead"):
    m, a, ref = conflate_cell("xb-" + kind if False else kind)
    al = []
    run_cycle(m, a, None, "2026-08-24", alert=al.append)
    before = len(new_stops(a, "CRSP"))
    pos_before = dict(stop_missing=m.state.positions["1"].stop_missing,
                      ref=m.state.positions["1"].stop_order_ref)
    al2 = []
    run_cycle(m, a, payload(stops=[stop_row(level=47.0)]), "2026-08-24",
              alert=al2.append)
    pos = m.state.positions["1"]
    placed = new_stops(a, "CRSP")[before:]
    check(f"X-B[{kind}] a trail ratchet must NOT rest a new SELL stop on "
          f"conflated (unproven) shares",
          not placed,
          f"new_stops_placed={len(placed)} qty={[p['qty'] for p in placed]} "
          f"stop_level_now={pos.stop_level} "
          f"stop_missing {pos_before['stop_missing']}->{pos.stop_missing} "
          f"ref {'set' if pos_before['ref'] else 'None'}->"
          f"{'set' if pos.stop_order_ref else 'None'} "
          f"feed.unprotected={m.feed({}, '2026-08-24')['unprotected']} "
          f"resting_at_venue={len(a._stops)}")

# and the consequence: that new stop can TRIGGER into the external shares
m, a, ref = conflate_cell("working")
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
run_cycle(m, a, payload(stops=[stop_row(level=47.0)]), "2026-08-24",
          alert=lambda _x: None)
new_ref = m.state.positions["1"].stop_order_ref
venue_before = a._positions["CRSP"]
triggered = False
if new_ref in a._stops:
    a.trigger_stop(new_ref)
    triggered = True
al = []
run_cycle(m, a, None, "2026-08-25", alert=al.append)
check("X-B[consequence] no blend stop may fill against externally-held "
      "shares after a conflated blackout",
      not triggered or a._positions["CRSP"] == venue_before,
      f"new_stop_placed_and_triggered={triggered} "
      f"venue {venue_before}->{a._positions['CRSP']} "
      f"booked_exit={'1' not in m.state.positions} "
      f"alerts={[x[:70] for x in al][:3]}")


# ==========================================================================
# X-C  X2 end to end: the ambiguous `False` cancel must reach the RED
#      "retired stop FILLED — possible short" branch, and the venue's
#      resulting NET must be reported.  (The short itself is not
#      preventable — the venue will not ACK the cancel — so the contract
#      is honesty, and the alert must say so.)
# ==========================================================================
class FalseCancel(DryAdapter):
    def cancel_stock_order(self, ref):
        rec = self._orders.get(ref)
        if rec is not None and rec["status"] == "filled":
            raise RuntimeError(f"cannot cancel {ref}: order already FILLED")
        self._rec("cancel_stock_order", ref=ref, found=False)
        return False


m = mk("xc")
a = FalseCancel()
held(m)
ref = rest_stop(m, a)
a._positions["CRSP"] = 2                 # manual sale of 3 in the blackout
blackout(m)
al = []
run_cycle(m, a, None, "2026-08-24", alert=al.append)
tracked = ref in m.state.orphan_stop_refs
park_alert = next((x for x in al if "parked for manual booking" in x), "")
a.trigger_stop(ref)                       # the abandoned stop triggers
al2 = []
run_cycle(m, a, None, "2026-08-25", alert=al2.append)
red = [x for x in al2 if "RETIRED stop" in x and "possible short" in x]
check("X-C X2: a False cancel stays tracked across the SAME reconcile and "
      "its later fill alerts RED (not the generic UNKNOWN-order line)",
      tracked and red and not any("UNKNOWN order" in x for x in al2)
      and f"orphan-{ref}" in m.state.unreconciled,
      f"tracked_after_recording_cycle={tracked} RED={bool(red)} "
      f"unknown_order_alert={any('UNKNOWN order' in x for x in al2)} "
      f"venue_net={a._positions['CRSP']} "
      f"unreconciled={sorted(m.state.unreconciled)}")
check("X-C(b) the park alert must not claim the stop was retired when the "
      "venue would not ACK",
      "would not ACK the cancel" in park_alert
      and "may still rest" in park_alert
      and "nothing sold" in park_alert
      and "was CANCELLED at the venue" not in park_alert,
      f"park='{park_alert[-160:]}'")
check("X-C(c) HONESTY: the RED alert names the resulting venue short",
      any(("short" in x.lower()) for x in red),
      f"venue_net_after_fill={a._positions['CRSP']} "
      f"red='{(red or [''])[0][:150]}'")


# ==========================================================================
# X-D  orphan lifecycle: a definitively ACKed cancel drains; a permanently
#      False one stays; and a stuck ref must not wedge the drainable one.
# ==========================================================================
class OneStickyCancel(DryAdapter):
    """`sticky` never ACKs; every other ref cancels normally."""
    sticky = None

    def cancel_stock_order(self, ref):
        if ref == self.sticky:
            self._rec("cancel_stock_order", ref=ref, found=False)
            return False
        return super().cancel_stock_order(ref)


m = mk("xd")
a = OneStickyCancel()
p1 = held(m, call_id=1, symbol="CRSP", qty=5, stop_level=44.0)
p2 = held(m, call_id=2, symbol="MRNA", qty=4, fill=60.0, stop_level=52.0)
r1 = rest_stop(m, a, 1, "CRSP", 5, 44.0)
r2 = rest_stop(m, a, 2, "MRNA", 4, 52.0)
a.sticky = r1
m.record_orphan_stop(r1, {"symbol": "CRSP", "qty": -5, "call_id": 1})
m.record_orphan_stop(r2, {"symbol": "MRNA", "qty": -4, "call_id": 2})
al = []
run_cycle(m, a, None, "2026-08-24", alert=al.append)
check("X-D a permanently-False orphan does not wedge a drainable peer",
      r2 not in m.state.orphan_stop_refs and r1 in m.state.orphan_stop_refs,
      f"orphans_after={sorted(m.state.orphan_stop_refs)}")

# cadence: loud on record, then every ORPHAN_REALERT_CYCLES, never silent,
# never per-cycle spam, and never a same-cycle duplicate.
m = mk("xd2")
a = OneStickyCancel()
held(m)
r1 = rest_stop(m, a)
a.sticky = r1
m.record_orphan_stop(r1, {"symbol": "CRSP", "qty": -5, "call_id": 1})
per = []
N = 3 * blend_mod.ORPHAN_REALERT_CYCLES
for c in range(N):
    al = []
    m.state.last_reconcile_ts = time.time()
    run_cycle(m, a, None, "2026-08-%02d" % (24 + c), alert=al.append)
    per.append(sum(1 for x in al if ("retired stop" in x
                                     and "TRACKED" in x)))
check("X-D(b) orphan escalation: never silent over 3 windows, never spam, "
      "never a same-cycle duplicate",
      max(per) <= 1 and sum(per) == N // blend_mod.ORPHAN_REALERT_CYCLES
      and all(any(per[i:i + blend_mod.ORPHAN_REALERT_CYCLES])
              for i in range(0, N, blend_mod.ORPHAN_REALERT_CYCLES)),
      f"per_cycle={per} total={sum(per)} expected="
      f"{N // blend_mod.ORPHAN_REALERT_CYCLES}")

# never drains -> unbounded growth with no manual clear endpoint
check("X-D(c) declared accepted cost: orphan_stop_refs never drains and no "
      "endpoint clears it",
      r1 in m.state.orphan_stop_refs,
      f"still_tracked_after_{N}_cycles={r1 in m.state.orphan_stop_refs}; "
      f"clear-endpoint in service.py="
      f"{'orphan' in open('app/service.py').read()}")


# ==========================================================================
# X-E  _flag_unverified cadence over many cycles: never double, never
#      silent, never spam; the counter must not be resettable by a
#      partial resolution that leaves the position flagged.
# ==========================================================================
m, a, ref = conflate_cell("working")
per = []
N = 5 * blend_mod.UNVERIFIED_REALERT_CYCLES
for c in range(N):
    al = []
    run_cycle(m, a, None, "2026-08-%02d" % (24 + (c % 6)), alert=al.append)
    per.append(sum(1 for x in al if "UNRESOLVED after the blackout" in x))
    m.state.last_reconcile_ts = time.time()
gaps_ok = all(any(per[i:i + blend_mod.UNVERIFIED_REALERT_CYCLES])
              for i in range(0, N, blend_mod.UNVERIFIED_REALERT_CYCLES))
check("X-E _flag_unverified: exactly one alert per window over 5 windows, "
      "no duplicates, no silent window",
      max(per) <= 1 and gaps_ok
      and sum(per) == N // blend_mod.UNVERIFIED_REALERT_CYCLES,
      f"per_cycle={per} total={sum(per)} "
      f"unverified_cycles={m.state.positions['1'].unverified_cycles}")

# a /kill flatten in the same cycle must not double-count the cadence
m, a, ref = conflate_cell("working")
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
before = m.state.positions["1"].unverified_cycles
m.request_flatten("2026-08-24")
m.state.last_reconcile_ts = time.time()
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
check("X-E(b) a /kill flatten in the same cycle does not double-increment "
      "the cadence counter",
      m.state.positions["1"].unverified_cycles == before + 1,
      f"{before} -> {m.state.positions['1'].unverified_cycles}")

# the counter survives a restart (persisted) so the cadence is not reset
# by a redeploy loop
m, a, ref = conflate_cell("working")
for c in range(3):
    run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
    m.state.last_reconcile_ts = time.time()
n_before = m.state.positions["1"].unverified_cycles
m2 = Blend3070Manager(Cfg(), m.state_path)
check("X-E(c) unverified_cycles survives a restart (a redeploy loop cannot "
      "silence the escalation by resetting it)",
      m2.state.positions["1"].unverified_cycles == n_before
      and m2.state.positions["1"].history_gap is True,
      f"before={n_before} after_reload="
      f"{m2.state.positions['1'].unverified_cycles}")


# ==========================================================================
# X-F  x5 "sacrifice nobody": nothing is sold, nobody is parked, everything
#      stays loud, and entries are blocked for the whole sleeve indefinitely.
#
#      REWRITTEN for the Z1 contract.  The old assertion counted the three
#      ORIGINAL order refs still resting — a mechanic Z1 legally replaces:
#      12 shares of SELL stops against 9 held is the venue short Z1 closes
#      (see X-K(d)), so every stop is resized PRO RATA instead.  "Sacrifice
#      nobody" is asserted directly and harder: nobody parked, nobody left
#      with ZERO cover, the superseded orders CANCELLED rather than
#      abandoned, aggregate cover == held, the pro-rata split exact
#      (4/3/2), and triggering everything cannot short the account.
# ==========================================================================
m = mk("xf")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
held(m, 3, "CRSP", 3, 50.0, 42.0)
r1 = rest_stop(m, a, 1, "CRSP", 5, 44.0)
r2 = rest_stop(m, a, 2, "CRSP", 4, 43.0)
r3 = rest_stop(m, a, 3, "CRSP", 3, 42.0)
a._positions["CRSP"] = 9                 # 12 booked, 3 sold by another route
blackout(m)
al = []
run_cycle(m, a, None, "2026-08-24", alert=al.append)
covered = [-a._stops[p.stop_order_ref]["qty"]
           for p in m.state.positions.values()
           if p.stop_order_ref in a._stops]
superseded = [a._orders[r]["status"] for r in (r1, r2, r3)]
venue_before = a._positions["CRSP"]
for ref in list(a._stops):
    a.trigger_stop(ref)
run_cycle(m, a, None, "2026-08-25", alert=lambda _x: None)
check("X-F x5: no peer is sacrificed — none parked, none stripped of cover, "
      "all stay flagged and loud, and cover can never short the account",
      len(covered) == 3 and sorted(covered) == [2, 3, 4]
      and sum(covered) == 9
      and superseded == ["cancelled"] * 3
      and not m.state.orphan_stop_refs
      and a._positions["CRSP"] >= 0
      and len(m.state.positions) == 3
      and not m.state.unreconciled
      and all(p.history_gap for p in m.state.positions.values())
      and sum(1 for x in al if "UNRESOLVED after the blackout" in x) == 3,
      f"positions={sorted(m.state.positions)} covers={sorted(covered)} "
      f"superseded={superseded} venue {venue_before} -> "
      f"{a._positions['CRSP']} orphans={sorted(m.state.orphan_stop_refs)} "
      f"unreconciled={sorted(m.state.unreconciled)} "
      f"escalations={sum(1 for x in al if 'UNRESOLVED' in x)}")
check("X-F(b) declared accepted cost: an unresolved conflation/shortfall "
      "blocks ALL new sleeve entries indefinitely",
      m.has_naked_position() is True,
      f"has_naked_position={m.has_naked_position()} (entries blocked while "
      f"any position is history_gap)")


# ==========================================================================
# X-G  ladder corrupt-preservation: fires on a genuinely unreadable file,
#      NEVER on a healthy or absent one, and never loses a good book.
# ==========================================================================
from app.manager import LadderManager           # noqa: E402


class LCfg:
    dry_run = True
    trading_mode = "paper"


def ladder(path):
    return LadderManager(LCfg(), path)


d = tempfile.mkdtemp()
p = os.path.join(d, "ladder.json")
L = ladder(p)                                   # absent file
absent_quiet = L.archived_state is None
L.state.banked = 1234.0
L.state.halted = "KILL"
L.save()
L2 = ladder(p)                                  # healthy file
healthy_quiet = (L2.archived_state is None and L2.state.banked == 1234.0
                 and L2.state.halted == "KILL")
open(p, "w").write('{"legs": {"a"')             # truncated
L3 = ladder(p)
corrupt_loud = L3.archived_state is not None
preserved = [f for f in os.listdir(d) if ".corrupt-" in f]
check("X-G ladder corrupt-preservation is loud on a torn file, silent on a "
      "healthy or absent one, and preserves the evidence",
      absent_quiet and healthy_quiet and corrupt_loud and preserved,
      f"absent_quiet={absent_quiet} healthy_quiet={healthy_quiet} "
      f"corrupt_loud={corrupt_loud} preserved={preserved}")

# schema drift on a LEG ROW: legs are silently RESET and the file is NOT
# preserved -> the very next save() overwrites the evidence
d2 = tempfile.mkdtemp()
p2 = os.path.join(d2, "ladder.json")
La = ladder(p2)
k0 = sorted(La.state.legs)[0]
La.state.legs[k0].status = "OPEN"
La.state.legs[k0].order_ref = "live-spread-ref"
La.state.banked = 999.0
La.save()
raw = json.load(open(p2))
raw["legs"][k0]["future_field_from_a_newer_deploy"] = 1     # rollback
json.dump(raw, open(p2, "w"))
Lb = ladder(p2)
lost = Lb.state.legs[k0].order_ref is None
Lb.save()                                        # the loop's next save
after = json.load(open(p2))
check("X-G(b) a leg-row schema drift must not silently forget OPEN legs "
      "and overwrite the evidence",
      not lost,
      f"leg_status={Lb.state.legs[k0].status} "
      f"order_ref={Lb.state.legs[k0].order_ref!r} "
      f"archived_state={(Lb.archived_state or '')[:60]!r} "
      f"file_preserved={[f for f in os.listdir(d2) if '.corrupt-' in f]} "
      f"evidence_after_next_save={after['legs'][k0]}")


# ==========================================================================
# X-H  blend corrupt-preservation (G3): loud on a torn file, never on a
#      healthy one, and it must not eat a good book.
# ==========================================================================
d3 = tempfile.mkdtemp()
mb = mk("xh", d3)
held(mb, 1, "CRSP", 5)
mb.save()
mb2 = mk("xh", d3)
healthy = (mb2.archived_state is None and "1" in mb2.state.positions)
open(mb.state_path, "w").write('{"initialized": true, "posi')
mb3 = mk("xh", d3)
loud = mb3.archived_state is not None
kept = [f for f in os.listdir(d3) if ".corrupt-" in f]
check("X-H blend corrupt-preservation: silent on a healthy book, loud + "
      "preserved on a torn one",
      healthy and loud and kept and mb3.state.positions == {},
      f"healthy_quiet={healthy} loud={loud} preserved={kept}")

# a NEW field in the position row (forward-compat / rollback) throws the
# WHOLE book away -- how loud is it, and is it recoverable?
d4 = tempfile.mkdtemp()
mc = mk("xh2", d4)
held(mc, 1, "CRSP", 5)
mc.save()
raw = json.load(open(mc.state_path))
raw["positions"]["1"]["field_from_a_newer_deploy"] = 1
json.dump(raw, open(mc.state_path, "w"))
md = mk("xh2", d4)
check("X-H(b) a position-row schema drift preserves the book and alerts "
      "(rollback safety)",
      md.archived_state is not None
      and [f for f in os.listdir(d4) if ".corrupt-" in f],
      f"archived_state={(md.archived_state or '')[:80]!r} "
      f"preserved={[f for f in os.listdir(d4) if '.corrupt-' in f]} "
      f"positions_now={sorted(md.state.positions)}")


# ==========================================================================
# X-I  MGR_LOCK / BLEND_LOCK: no nesting anywhere (static), and no lost
#      mutation under contention (runtime).
# ==========================================================================
src = open("app/service.py").read()
nested = []
lines = src.split("\n")
for i, ln in enumerate(lines):
    if "with MGR_LOCK" in ln or "with BLEND_LOCK" in ln:
        indent = len(ln) - len(ln.lstrip())
        other = "BLEND_LOCK" if "MGR_LOCK" in ln else "MGR_LOCK"
        for ln2 in lines[i + 1:]:
            if ln2.strip() and (len(ln2) - len(ln2.lstrip())) <= indent:
                break
            if f"with {other}" in ln2:
                nested.append((i + 1, ln2.strip()))
check("X-I no lexical nesting of MGR_LOCK inside BLEND_LOCK or vice versa "
      "(a fixed order is unnecessary only if they never nest)",
      not nested, f"nested_sites={nested}")

import app.service as svc                        # noqa: E402

lost = []
svc.MGR = ladder(os.path.join(tempfile.mkdtemp(), "l.json"))
stop_evt = threading.Event()
writes = {"loop": 0, "api": 0}


def loop_thread():
    while not stop_evt.is_set():
        with svc.MGR_LOCK:
            svc.MGR.state.banked += 1.0
            writes["loop"] += 1
            svc.MGR.save()


def api_thread():
    for _ in range(300):
        with svc.MGR_LOCK:
            svc.MGR.state.banked += 1.0
            writes["api"] += 1
            svc.MGR.save()


ts = [threading.Thread(target=api_thread) for _ in range(3)]
lt = threading.Thread(target=loop_thread, daemon=True)
lt.start()
[t.start() for t in ts]
[t.join(30) for t in ts]
stop_evt.set()
lt.join(5)
final = json.load(open(svc.MGR.state_path))
check("X-I(b) MGR_LOCK serializes the read-modify-write: no lost mutation, "
      "no torn file, no deadlock under contention",
      abs(final["banked"] - svc.MGR.state.banked) < 1e-9
      and svc.MGR.state.banked == writes["loop"] + writes["api"],
      f"banked={svc.MGR.state.banked} writes={writes} file={final['banked']}")


# ==========================================================================
# X-J  feed hygiene: the new fields must not leak credentials/account data
#      and the book-level counts must agree with /status.
# ==========================================================================
m, a, ref = conflate_cell("dead")
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
fd = m.feed({"CRSP": 50.0, "SPY": 500.0, "BIL": 91.0}, "2026-08-24")
blob = json.dumps(fd).lower()
banned = [w for w in ("token", "password", "userid", "user_id", "account",
                      "secret", "apikey", "api_key", "tws", "credential")
          if w in blob]
ss = m.status_summary()
check("X-J /blend/feed leaks no credential/account keys and its counts "
      "agree with /status",
      not banned
      and fd["unverifiable"] == len(ss["unverifiable"])
      and fd["unprotected"] == len(ss["stop_missing"]),
      f"banned_substrings={banned} feed=({fd['unverifiable']}, "
      f"{fd['unprotected']}) status=({len(ss['unverifiable'])}, "
      f"{len(ss['stop_missing'])})")

jsx = open("../genomics-alpha-tracker/frontend/src/views/Execution.jsx").read()
emitted = set(fd["positions"][0])
readers = {f for f in ("unverifiable", "unprotected", "unverified_cycles")
           if f"p.{f}" in jsx}
check("X-J(b) the Execution tab reads only fields the feed actually emits",
      readers and readers <= emitted,
      f"jsx_reads={sorted(readers)} feed_emits={sorted(emitted)} "
      f"missing={sorted(readers - emitted)}")



# ==========================================================================
# X-K  is the ADJUST_STOP seam specific to conflation, or does it bypass
#      EVERY fail-closed cell the guard defines?
# ==========================================================================
class NoPositions(DryAdapter):
    def stock_position(self, symbol):
        raise RuntimeError("positions unavailable (simulated)")


# (a) "positions unanswerable" cell (the C5 deliberate deviation)
m = mk("xk-a")
a = NoPositions()
held(m)
ref = rest_stop(m, a)
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
before = len(new_stops(a, "CRSP"))
run_cycle(m, a, payload(stops=[stop_row(level=47.0)]), "2026-08-24",
          alert=lambda _x: None)
check("X-K(a) 'positions unanswerable' cell: a ratchet must not rest a new "
      "stop while the guard cannot corroborate anything",
      len(new_stops(a, "CRSP")) == before,
      f"new_stops={len(new_stops(a, 'CRSP')) - before} "
      f"history_gap={m.state.positions['1'].history_gap}")

# (b) x5 same-symbol-peer shortfall cell
m = mk("xk-b")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6                # 9 booked, 3 gone
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
before = len(new_stops(a, "CRSP"))
run_cycle(m, a, payload(stops=[stop_row(level=47.0, call_id=1),
                               stop_row(level=46.0, call_id=2)]),
          "2026-08-24", alert=lambda _x: None)
check("X-K(b) x5 shortfall cell: a ratchet must not rest new stops on a "
      "book the venue already contradicts",
      len(new_stops(a, "CRSP")) == before,
      f"new_stops={len(new_stops(a, 'CRSP')) - before} venue=6 booked=9")

# (c) does the same seam exist at the merge base? (regression vs new hole)
check("X-K(c) provenance: the trail-ratchet loop has no history_gap guard "
      "at the merge base either (pre-existing, NOT introduced here)",
      True,
      "4afda54 step() adjust loop: no `if pos.history_gap: continue` — the "
      "hole predates this branch, but this branch is the one that DOCUMENTS "
      "the contract it breaks (README: 'no new protective stop is placed "
      "for the position')")

# (d) the consequence in the x5 cell: total resting SELL qty now EXCEEDS
#     what the account holds -> a guaranteed short when both trigger.
m = mk("xk-d")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 6
blackout(m)
run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
run_cycle(m, a, payload(stops=[stop_row(level=47.0, call_id=1),
                               stop_row(level=46.0, call_id=2)]),
          "2026-08-24", alert=lambda _x: None)
resting = list(a._stops)
before = a._positions["CRSP"]
for r in resting:
    a.trigger_stop(r)
al = []
run_cycle(m, a, None, "2026-08-25", alert=al.append)
check("X-K(d) CONSEQUENCE: ratcheted stops on a contradicted book must not "
      "be able to short the account",
      a._positions["CRSP"] >= 0,
      f"venue {before} -> {a._positions['CRSP']} (NEGATIVE = naked short) "
      f"resting_stops_after_ratchet={len(resting)} booked_qty=9 "
      f"alerts={[x[:60] for x in al][:3]}")


# ==========================================================================
# X-L  is the "wedged sleeve" actually resolvable in band?  The operator's
#      only lever is the ACCOUNT: once the external shares leave (held ==
#      booked) the cell must resolve itself without a hand-edited book.
# ==========================================================================
for kind in ("working", "dead"):
    m, a, ref = conflate_cell(kind)
    run_cycle(m, a, None, "2026-08-24", alert=lambda _x: None)
    a._positions["CRSP"] = 5              # operator moves the external shares out
    m.state.last_reconcile_ts = time.time()
    al = []
    run_cycle(m, a, None, "2026-08-25", alert=al.append)
    pos = m.state.positions["1"]
    check(f"X-L[{kind}] the wedge is resolvable in band: restoring the "
          f"account to exactly the booked shares unparks and re-protects",
          pos.history_gap is False and pos.unverified_cycles == 0
          and pos.stop_order_ref and not m.has_naked_position(),
          f"history_gap={pos.history_gap} stop_missing={pos.stop_missing} "
          f"ref={'set' if pos.stop_order_ref else 'None'} "
          f"cycles={pos.unverified_cycles} "
          f"entries_unblocked={not m.has_naked_position()}")

# ==========================================================================
print()
bad = [n for n, ok, _ in results if not ok]
print(f"{len(results) - len(bad)}/{len(results)} probes passed; "
      f"landed attacks: {bad}")
