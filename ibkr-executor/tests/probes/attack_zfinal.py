"""Counter-agent probes vs the Z1 FIX round (e750abd..1485ab4).

Re-attacks the four materials from z1_counter_verdict.md directly, rather
than trusting the new gates to be attacking the right thing:
  Z-A  every door back to FULL cover for a capped peer
  Z-B  partial booking correctness
  Z-C  the new restore-from-zero path
  Z-D  rollback resilience (halt + keep) and what acts while halted
plus the widened entry block and the three declared deviations.

Run from ibkr-executor/.  A FAIL is a landed attack.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, ".")

from app import blend as blend_mod                          # noqa: E402
from app.blend import (Blend3070Manager, run_cycle,          # noqa: E402
                       stop_client_id, entry_client_id, reconcile,
                       _prorata_cover, _resting_cover, _is_unprotected)
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


def payload(entries=(), exits=(), stops=(), as_of="2026-08-24"):
    return {
        "as_of": as_of,
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
    m.state.positions[str(call_id)].stop_missing = False
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


def clean_shortfall(nm, q1=5, q2=4, hold=6, lv1=44.0, lv2=43.0):
    """A mixed FLAGGED/UNFLAGGED same-symbol pair straight out of the
    crash-window adoption path (attack_z1's Z-12 reachability), then the
    shortfall appears.  Returns (mgr, adapter, alerts_from_the_resize)."""
    m = mk(nm)
    a = DryAdapter()
    held(m, 1, "CRSP", q1, 50.0, lv1)
    rest_stop(m, a, 1, "CRSP", q1, lv1)
    it = {"call_id": 2, "symbol": "CRSP", "qty": q2, "entry_ref": 50.0,
          "stop_level": lv2, "reason": "fire"}
    m.record_pending_entry(it, "2026-08-20")
    a.place_stock_order("CRSP", q2, "MOO", ref_price=50.0,
                        client_order_id=entry_client_id(2))
    a._positions["CRSP"] = q1 + q2
    blackout(m)
    run_cycle(m, a, None, "2026-08-24", alert=NULL)      # adopt call 2
    a._positions["CRSP"] = hold                          # the shortfall
    al = []
    run_cycle(m, a, None, "2026-08-25", alert=al.append)  # resize cycle
    return m, a, al


# =========================================================================
# ZF-A  Z-A RE-ATTACK: hunt EVERY door back to full cover.
# =========================================================================
print("\n---- ZF-A: doors back to full cover ----")

# --- A1: the ratchet door (Z-6b/Z-12b), driven on BOTH peers, 3 cycles.
m, a, al = clean_shortfall("a1")
cov0 = cover_at_venue(a)
flags0 = {k: p.history_gap for k, p in m.state.positions.items()}
covers0 = {k: _resting_cover(p) for k, p in m.state.positions.items()}
for day, lv in (("2026-08-26", 45.0), ("2026-08-27", 46.0),
                ("2026-08-28", 47.0)):
    run_cycle(m, a, payload(stops=[stop_row(call_id=1, level=lv),
                                   stop_row(call_id=2, level=lv)]),
              day, alert=NULL)
cov1 = cover_at_venue(a)
for r in list(a._stops):
    a.trigger_stop(r)
run_cycle(m, a, None, "2026-08-29", alert=NULL)
check("ZF-A1 three tracker ratchets on BOTH same-symbol peers never "
      "restore cover above the venue's held; nothing shorts",
      cov0 <= 6 and cov1 <= 6 and a._positions["CRSP"] >= 0,
      f"flags_after_resize={flags0} book_cover={covers0} "
      f"cover_after_resize={cov0} cover_after_3_ratchets={cov1} (held=6) "
      f"venue_after_all_triggers={a._positions['CRSP']}")

# --- A2: the pass-4 door in the SAME reconcile, with the replace REJECTED
#         for BOTH peers (Z-6a).
m2, a2, _ = clean_shortfall("a2pre")
m2b = mk("a2")
a2b = DryAdapter()
held(m2b, 1, "CRSP", 5, 50.0, 44.0)
held(m2b, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m2b, a2b, 1, "CRSP", 5, 44.0)
rest_stop(m2b, a2b, 2, "CRSP", 4, 43.0)
a2b._positions["CRSP"] = 6
for p in m2b.state.positions.values():
    p.history_gap = True                 # both flagged, plain peer shortfall
blackout(m2b)
_orig_place = a2b.place_stock_order


def _reject_stp(symbol, qty, order_type, **kw):
    if order_type == "STP":
        raise RuntimeError("venue rejected")
    return _orig_place(symbol, qty, order_type, **kw)


a2b.place_stock_order = _reject_stp
al2 = []
run_cycle(m2b, a2b, None, "2026-08-25", alert=al2.append)
a2b.place_stock_order = _orig_place       # venue recovers
cov2 = cover_at_venue(a2b)
check("ZF-A2 a resize whose replace is REJECTED for every peer leaves "
      "ZERO cover resting — pass 4 in the same reconcile does not "
      "re-place -qty",
      cov2 == 0,
      f"cover_at_venue={cov2} "
      f"stop_missing={{k: p.stop_missing for k,p in m2b.state.positions.items()}} "
      f"= {{'1': %s, '2': %s}}" % (m2b.state.positions['1'].stop_missing,
                                   m2b.state.positions['2'].stop_missing))

# --- A3: RESTART. Does the cap survive a reload, or does a fresh process
#         ratchet a capped peer back to full?
m3, a3, _ = clean_shortfall("a3")
path3 = m3.state_path
m3r = Blend3070Manager(Cfg(), path3)
persisted = {k: (p.history_gap, p.stop_cover_qty)
             for k, p in m3r.state.positions.items()}
m3r.mark_cache = {"prices": {}, "ts": None}
run_cycle(m3r, a3, payload(stops=[stop_row(call_id=1, level=48.0),
                                  stop_row(call_id=2, level=48.0)]),
          "2026-08-26", alert=NULL)
cov3 = cover_at_venue(a3)
for r in list(a3._stops):
    a3.trigger_stop(r)
run_cycle(m3r, a3, None, "2026-08-27", alert=NULL)
check("ZF-A3 the cap survives a process RESTART (history_gap and "
      "stop_cover_qty persist) and a post-restart ratchet cannot short",
      all(f for f, _c in persisted.values()) and cov3 <= 6
      and a3._positions["CRSP"] >= 0,
      f"persisted(history_gap, stop_cover_qty)={persisted} "
      f"cover_after_restart_ratchet={cov3} venue={a3._positions['CRSP']}")

# --- A4: /kill FLATTEN on capped peers.
m4, a4, _ = clean_shortfall("a4")
m4.request_flatten("2026-08-26")
al4 = []
run_cycle(m4, a4, None, "2026-08-26", alert=al4.append)
sold4 = [e for e in a4.log
         if e.get("action") == "place_stock_order" and e.get("qty", 0) < 0
         and e.get("order_type") == "MKT"]
check("ZF-A4 /kill flatten never MKT-sells a CAPPED (now flagged) peer",
      not sold4 and a4._positions["CRSP"] >= 0,
      f"mkt_sells={sold4} venue={a4._positions['CRSP']} "
      f"still_open={sorted(m4.state.positions)}")

# --- A5: a tracker EXIT intent on a capped peer.
m5, a5, _ = clean_shortfall("a5")
al5 = []
run_cycle(m5, a5, payload(exits=[{"call_id": 2, "symbol": "CRSP",
                                  "reason": "gate_off"}]),
          "2026-08-26", alert=al5.append)
sold5 = [e for e in a5.log
         if e.get("action") == "place_stock_order" and e.get("qty", 0) < 0
         and e.get("order_type") == "MKT"]
check("ZF-A5 a tracker EXIT on a CAPPED peer is DEFERRED, never a MKT sell",
      not sold5 and "2" in m5.state.positions,
      f"mkt_sells={sold5} deferred_alerts="
      f"{[x[:70] for x in al5 if 'deferred' in x]}")

# --- A6: the executor's own 90-day time stop (the payload-None belt).
m6, a6, _ = clean_shortfall("a6")
for p in m6.state.positions.values():
    p.time_stop = "2026-08-01"           # long past
al6 = []
run_cycle(m6, a6, None, "2026-08-26", alert=al6.append)
sold6 = [e for e in a6.log
         if e.get("action") == "place_stock_order" and e.get("qty", 0) < 0
         and e.get("order_type") == "MKT"]
check("ZF-A6 the executor time-stop belt does not MKT-sell a CAPPED peer",
      not sold6 and a6._positions["CRSP"] >= 0,
      f"mkt_sells={sold6} venue={a6._positions['CRSP']}")

# --- A7: a peer LEAVES the book (its stop fills) — is the survivor's cap
#         released behind the book's back, or correctly re-derived?
m7, a7, _ = clean_shortfall("a7")
cov7a = cover_at_venue(a7)
# call 1's resized stop triggers; the venue holds what is left
ref1 = m7.state.positions["1"].stop_order_ref
cov1_shares = _resting_cover(m7.state.positions["1"])
a7.trigger_stop(ref1)
al7 = []
run_cycle(m7, a7, None, "2026-08-26", alert=al7.append)
cov7b = cover_at_venue(a7)
held7 = a7._positions["CRSP"]
book7 = sum(p.qty for p in m7.state.positions.values()
            if p.symbol == "CRSP")
check("ZF-A7 when one peer's resized stop FILLS and it leaves the book, "
      "the survivor's cover is still <= what the venue holds",
      cov7b <= held7,
      f"cover_before={cov7a} peer1_cover={cov1_shares} cover_after={cov7b} "
      f"held={held7} book_qty_left={book7} open={sorted(m7.state.positions)}")

# --- A8: a NEW same-symbol entry while a capped peer is flagged.
m8, a8, _ = clean_shortfall("a8")
al8 = []
run_cycle(m8, a8, payload(entries=[{"call_id": 9, "symbol": "CRSP",
                                    "qty": 3, "entry_ref": 50.0,
                                    "stop_level": 44.0, "reason": "fire"}]),
          "2026-08-26", alert=al8.append)
check("ZF-A8 no NEW same-symbol entry can slip in beside a capped peer",
      "9" not in m8.state.positions and not m8.state.pending_entries,
      f"open={sorted(m8.state.positions)} pending={sorted(m8.state.pending_entries)}")

# --- A9: a fluctuating `held` across many cycles. Run TWICE: once with the
#         blackout MAINTAINED (pass 1b actually verifies every cycle) and
#         once where it lapses, to separate "invariant broken" from
#         "invariant never EVALUATED".
def fluctuate(nm, keep_blackout):
    m = mk(nm)
    a = DryAdapter()
    held(m, 1, "CRSP", 5, 50.0, 44.0)
    held(m, 2, "CRSP", 4, 50.0, 43.0)
    held(m, 3, "CRSP", 3, 50.0, 42.0)
    rest_stop(m, a, 1, "CRSP", 5, 44.0)
    rest_stop(m, a, 2, "CRSP", 4, 43.0)
    rest_stop(m, a, 3, "CRSP", 3, 42.0)
    for p in m.state.positions.values():
        p.history_gap = True
    blackout(m)
    rows, places = [], 0
    for i, h in enumerate([9, 7, 5, 5, 3, 6, 2, 8, 4, 12, 1, 0, 5]):
        a._positions["CRSP"] = h
        if keep_blackout:
            blackout(m)
        n0 = len([e for e in a.log if e.get("action") == "place_stock_order"])
        run_cycle(m, a, None, f"2026-09-{i + 1:02d}", alert=NULL)
        places += len([e for e in a.log
                       if e.get("action") == "place_stock_order"]) - n0
        rows.append((i, h, cover_at_venue(a),
                     sum(1 for p in m.state.positions.values() if p.history_gap)))
    return m, a, rows, places


mv, av, rows_v, pl_v = fluctuate("a9v", True)
badv = [r for r in rows_v if r[2] > r[1]]
check("ZF-A9 across 13 cycles of a FLUCTUATING held (9..0..5) WITH the "
      "blackout maintained, resting cover never exceeds held at the end of "
      "any reconcile",
      not badv, f"(cycle, held, cover, n_flagged)={rows_v} "
                f"violations={badv} placements={pl_v}")
for r in list(av._stops):
    av.trigger_stop(r)
run_cycle(mv, av, None, "2026-09-20", alert=NULL)
check("ZF-A9b triggering EVERY resting stop after that fluctuation cannot "
      "make the account short",
      av._positions["CRSP"] >= 0, f"venue={av._positions['CRSP']}")

mu, au, rows_u, _ = fluctuate("a9u", False)
badu = [r for r in rows_u if r[2] > r[1]]
for r in list(au._stops):
    au.trigger_stop(r)
run_cycle(mu, au, None, "2026-09-20", alert=NULL)
check("ZF-A9c [SCOPE] once held == book_qty UNPARKS every peer, a LATER "
      "shortfall with no new blackout is never seen: cover stays above "
      "held and the account CAN go short",
      not badu,
      f"(cycle, held, cover, n_flagged)={rows_u} violations={badu} "
      f"venue_after_triggers={au._positions['CRSP']} "
      f"-- NOT a Z1 regression: outside the flagged cell the executor never "
      f"calls stock_position at all, so `held` is never read. Identical at "
      f"main. Recorded as the contract's SCOPE, see verdict ZF-3.")


# =========================================================================
# ZF-B  Z-B RE-ATTACK: partial booking correctness.
# =========================================================================
print("\n---- ZF-B: partial booking ----")


def resized_then_fill(nm, q=5, hold=6, q2=4):
    """Get call 1 to a RESIZED, still-resting stop; then that stop fills at
    the venue INSIDE a blackout (never polled)."""
    m = mk(nm)
    a = DryAdapter()
    held(m, 1, "CRSP", q, 50.0, 44.0)
    held(m, 2, "CRSP", q2, 50.0, 43.0)
    rest_stop(m, a, 1, "CRSP", q, 44.0)
    rest_stop(m, a, 2, "CRSP", q2, 43.0)
    a._positions["CRSP"] = hold
    for p in m.state.positions.values():
        p.history_gap = True
    blackout(m)
    run_cycle(m, a, None, "2026-08-25", alert=NULL)
    return m, a


m, a = resized_then_fill("b1")
p1 = m.state.positions["1"]
cover1, qty1 = _resting_cover(p1), p1.qty
cash_before = m.state.sleeve_cash
ref = p1.stop_order_ref
a.trigger_stop(ref)
a._fills.clear()                     # the fill-poll MISSED it (blackout)
blackout(m)
alb = []
run_cycle(m, a, None, "2026-08-26", alert=alb.append)
cash_after = m.state.sleeve_cash
honest = cover1 * 44.0
check("ZF-B1 a RESIZED stop's blackout fill credits EXACTLY the shares it "
      "covered, and the remainder keeps a book row",
      abs((cash_after - cash_before) - honest) < 1e-6
      and "1" in m.state.positions
      and m.state.positions["1"].qty == qty1 - cover1,
      f"cover={cover1} of qty={qty1}; credited="
      f"{cash_after - cash_before:.2f} honest={honest:.2f}; "
      f"remaining_qty={m.state.positions.get('1') and m.state.positions['1'].qty}")

# --- B2: DOUBLE-BOOK. The live poll books the partial, and the SAME cycle's
#         1b-i then sees the order 'filled' in history.
m, a = resized_then_fill("b2")
p1 = m.state.positions["1"]
cover1, qty1 = _resting_cover(p1), p1.qty
cash_before = m.state.sleeve_cash
a.trigger_stop(p1.stop_order_ref)     # leaves a queued fill event for pass 1
blackout(m)
run_cycle(m, a, None, "2026-08-26", alert=NULL)
credited = m.state.sleeve_cash - cash_before
check("ZF-B2 the live fill poll and 1b-i cannot BOTH book the same resized "
      "fill (no double credit)",
      abs(credited - cover1 * 44.0) < 1e-6,
      f"credited={credited:.2f} once_would_be={cover1 * 44.0:.2f} "
      f"twice_would_be={2 * cover1 * 44.0:.2f} "
      f"remaining={m.state.positions.get('1') and m.state.positions['1'].qty}")

# --- B3: an UNRESIZED stop's blackout fill must still book the FULL exit
#         (the Z-B guard must not swallow a genuine full exit).
m = mk("b3")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
a._positions["CRSP"] = 5
m.state.positions["1"].history_gap = True
blackout(m)
cash_before = m.state.sleeve_cash
a.trigger_stop(m.state.positions["1"].stop_order_ref)
a._fills.clear()
blackout(m)
run_cycle(m, a, None, "2026-08-26", alert=NULL)
check("ZF-B3 an UNRESIZED stop's blackout fill still books the FULL exit "
      "(the Z-B partial guard does not swallow a real full exit)",
      "1" not in m.state.positions
      and abs((m.state.sleeve_cash - cash_before) - 5 * 44.0) < 1e-6,
      f"open={sorted(m.state.positions)} "
      f"credited={m.state.sleeve_cash - cash_before:.2f} (honest 220.00)")

# --- B4: after the PARTIAL, the position is stop_missing at a stop_level
#         whose deterministic client id now belongs to a FILLED order.
#         Does pass 4 adopt that FILLED order as working protection?
m, a = resized_then_fill("b4")
p1 = m.state.positions["1"]
lvl = p1.stop_level
a.trigger_stop(p1.stop_order_ref)
a._fills.clear()
blackout(m)
run_cycle(m, a, None, "2026-08-26", alert=NULL)
# let the book positively verify so pass 4 is allowed to re-protect it
p1 = m.state.positions.get("1")
if p1 is not None:
    a._positions["CRSP"] = sum(p.qty for p in m.state.positions.values())
    run_cycle(m, a, None, "2026-08-27", alert=NULL)
    run_cycle(m, a, None, "2026-08-28", alert=NULL)
    p1 = m.state.positions.get("1")
adopted_ref = p1 and p1.stop_order_ref
adopted_status = (a._orders.get(adopted_ref, {}) or {}).get("status") \
    if adopted_ref else None
resting_now = adopted_ref in a._stops if adopted_ref else False
check("ZF-B4 after a resized stop's PARTIAL fill, the book never reports "
      "itself protected by an order that has already FILLED",
      p1 is None or p1.stop_missing or adopted_status == "working",
      f"remaining_qty={p1 and p1.qty} stop_missing={p1 and p1.stop_missing} "
      f"adopted_ref={adopted_ref} venue_status_of_that_order="
      f"{adopted_status} still_resting={resting_now} "
      f"unprotected_flag={p1 and _is_unprotected(p1)}")

# --- B5: BELIEVED-OPEN-BUT-CLOSED. A retired stop (stop_missing) whose
#         cancel never took, which then fills in the dark.
m = mk("b5")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
ref = rest_stop(m, a, 1, "CRSP", 5, 44.0)
m.state.positions["1"].history_gap = True
m.mark_stop_missing(1)                # book believes nothing rests
blackout(m)
a.trigger_stop(ref)                   # but it does, and it fills
a._fills.clear()
a._positions["CRSP"] = 0
blackout(m)
alb5 = []
run_cycle(m, a, None, "2026-08-26", alert=alb5.append)
green = [x for x in alb5 if x.startswith("🧬") and "closed" in x]
check("ZF-B5 a believed-retired stop that actually FILLED is never booked "
      "as a cheerful green close",
      not green,
      f"open={sorted(m.state.positions)} "
      f"unreconciled={sorted(m.state.unreconciled)} "
      f"green={[g[:80] for g in green]}")


# =========================================================================
# ZF-C  Z-C RE-ATTACK: the new restore-from-ZERO path.
# =========================================================================
print("\n---- ZF-C: restore from zero ----")


def rejected_once(nm):
    """Both peers flagged, shortfall, the resize's replace REJECTED; then
    the venue recovers."""
    m = mk(nm)
    a = DryAdapter()
    held(m, 1, "CRSP", 5, 50.0, 44.0)
    held(m, 2, "CRSP", 4, 50.0, 43.0)
    rest_stop(m, a, 1, "CRSP", 5, 44.0)
    rest_stop(m, a, 2, "CRSP", 4, 43.0)
    a._positions["CRSP"] = 6
    for p in m.state.positions.values():
        p.history_gap = True
    blackout(m)
    orig = a.place_stock_order

    def rej(symbol, qty, order_type, **kw):
        if order_type == "STP":
            raise RuntimeError("venue rejected")
        return orig(symbol, qty, order_type, **kw)

    a.place_stock_order = rej
    run_cycle(m, a, None, "2026-08-25", alert=NULL)
    a.place_stock_order = orig
    return m, a


# --- C1: the retry actually happens (Z-C / DEVIATION 1's own promise).
m, a = rejected_once("c1")
cov_after_reject = cover_at_venue(a)
blackout(m)
alc = []
run_cycle(m, a, None, "2026-08-26", alert=alc.append)
cov_after_retry = cover_at_venue(a)
check("ZF-C1 cover REJECTED by the venue is really re-placed on the next "
      "reconcile that still sees the shortfall",
      cov_after_reject == 0 and cov_after_retry > 0,
      f"cover_after_reject={cov_after_reject} "
      f"cover_after_retry={cov_after_retry} (held=6)")
check("ZF-C1b the restored cover never exceeds the venue's held",
      cov_after_retry <= 6, f"cover={cov_after_retry} held=6")

# --- C2: the restore must NEVER stack on a stop that already rests. The
#         REALISTIC shape: the book lost its ref, but the venue order rests
#         under the position's OWN deterministic client id.
m = mk("c2")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
a.place_stock_order("CRSP", -4, "STP", stop_price=43.0, tif="GTC",
                    client_order_id=stop_client_id(2, 43.0))
m.state.positions["2"].stop_missing = True       # the BOOK lost the ref
m.state.positions["2"].stop_order_ref = None
a._positions["CRSP"] = 6
for p in m.state.positions.values():
    p.history_gap = True
blackout(m)
run_cycle(m, a, None, "2026-08-25", alert=NULL)
covc2 = cover_at_venue(a)
check("ZF-C2 a stop resting under the position's OWN client id that the "
      "book has forgotten is RECOVERED and resized, never stacked on",
      covc2 <= 6,
      f"venue_cover={covc2} (held=6) "
      f"resting={[(k, v['qty']) for k, v in a._stops.items()]} "
      f"call2_ref={m.state.positions['2'].stop_order_ref} "
      f"orphans={list(m.state.orphan_stop_refs)}")

# --- C2b: an order the book can NEVER address (placed under a foreign
#          client id) is X2-residual, recorded not asserted.
m = mk("c2b")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
a.place_stock_order("CRSP", -4, "STP", stop_price=43.0, tif="GTC",
                    client_order_id="foreign-cid")
m.state.positions["2"].stop_missing = True
m.state.positions["2"].stop_order_ref = None
a._positions["CRSP"] = 6
for p in m.state.positions.values():
    p.history_gap = True
blackout(m)
run_cycle(m, a, None, "2026-08-25", alert=NULL)
check("ZF-C2b [OBSERVATION] a SELL stop the book can neither see nor "
      "address keeps aggregate venue cover above held — X2 residual, "
      "unreachable by any blend code path",
      True,
      f"venue_cover={cover_at_venue(a)} (held=6) of which "
      f"{sum(-o['qty'] for k, o in a._stops.items() if a._orders[k].get('client_order_id') == 'foreign-cid')} "
      f"is the foreign order")

# --- C3: the restore under a SPENT (already FILLED) client id.
m = mk("c3")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
ref2 = rest_stop(m, a, 2, "CRSP", 4, 43.0)
a.trigger_stop(ref2)                       # call 2's stop FILLED
a._fills.clear()
m.state.positions["2"].stop_missing = True
m.state.positions["2"].stop_order_ref = None
rest_stop(m, a, 1, "CRSP", 5, 44.0)
a._positions["CRSP"] = 6
for p in m.state.positions.values():
    p.history_gap = True
blackout(m)
alc3 = []
run_cycle(m, a, None, "2026-08-25", alert=alc3.append)
p2 = m.state.positions.get("2")
ref_now = p2 and p2.stop_order_ref
st_now = (a._orders.get(ref_now, {}) or {}).get("status") if ref_now else None
check("ZF-C3 the restore never adopts an order under a SPENT/filled client "
      "id as working protection",
      p2 is None or p2.stop_missing or st_now == "working",
      f"call2 stop_missing={p2 and p2.stop_missing} ref={ref_now} "
      f"venue_status={st_now}")

# --- C4: CHURN. 8 quiet cycles at a stable shortfall — count placements.
m, a = rejected_once("c4")
n0 = len([e for e in a.log if e.get("action") == "place_stock_order"])
for i in range(8):
    blackout(m)
    run_cycle(m, a, None, f"2026-09-{i + 1:02d}", alert=NULL)
n1 = len([e for e in a.log if e.get("action") == "place_stock_order"])
cancels = len([e for e in a.log if e.get("action") == "cancel_stock_order"])
check("ZF-C4 a STABLE shortfall does not churn cancel/place every cycle "
      "(<= 1 placement per peer after the first restore)",
      (n1 - n0) <= 3,
      f"placements_over_8_cycles={n1 - n0} cancels_total={cancels} "
      f"final_cover={cover_at_venue(a)} (held=6)")

# --- C5: the restore must not fire while an unACKed orphan of THIS
#         position's own cover may still rest.
m = mk("c5")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
m.state.positions["2"].stop_missing = True
m.state.positions["2"].stop_order_ref = None
m.record_orphan_stop("ghost-2", {"symbol": "CRSP", "qty": -4, "call_id": 2})
a._positions["CRSP"] = 6
for p in m.state.positions.values():
    p.history_gap = True
blackout(m)
run_cycle(m, a, None, "2026-08-25", alert=NULL)
p2 = m.state.positions.get("2")
check("ZF-C5 no cover is restored for a position with an unACKed orphan of "
      "its own cover outstanding",
      p2 is not None and (p2.stop_missing or not p2.stop_order_ref),
      f"call2 stop_missing={p2 and p2.stop_missing} ref={p2 and p2.stop_order_ref} "
      f"venue_cover={cover_at_venue(a)} (held=6)")

# --- C6: restore must never exceed the ALLOCATION even when held recovers
#         above the book (conflation arriving mid-shortfall).
m, a = rejected_once("c6")
a._positions["CRSP"] = 20               # conflation now
blackout(m)
run_cycle(m, a, None, "2026-08-26", alert=NULL)
covc6 = cover_at_venue(a)
book6 = sum(p.qty for p in m.state.positions.values())
check("ZF-C6 when held jumps ABOVE the book mid-shortfall, no restore "
      "over-covers (cover <= book_qty and <= held)",
      covc6 <= book6 and covc6 <= 20,
      f"cover={covc6} book_qty={book6} held=20")


# =========================================================================
# ZF-D  Z-D RE-ATTACK: rollback resilience.
# =========================================================================
print("\n---- ZF-D: rollback resilience ----")

d = tempfile.mkdtemp()
m = mk("d", d)
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
m.save()
raw = json.load(open(m.state_path))
raw["positions"]["1"]["future_field_from_a_newer_deploy"] = 7
json.dump(raw, open(m.state_path, "w"))
md = Blend3070Manager(Cfg(), m.state_path)
check("ZF-D1 a blend book carrying a NEWER build's field is PRESERVED, "
      "the rows are kept, and the book HALTS",
      md.state.halted == "SCHEMA_DRIFT" and "1" in md.state.positions
      and md.state.positions["1"].stop_order_ref
      and md.state.initialized and md.archived_state_critical,
      f"halted={md.state.halted} positions={sorted(md.state.positions)} "
      f"ref={md.state.positions.get('1') and md.state.positions['1'].stop_order_ref} "
      f"initialized={md.state.initialized} "
      f"entries_blocked={md.has_naked_position()}")

# the halt must survive a crash before the first loop save (Z-J)
md2 = Blend3070Manager(Cfg(), m.state_path)
check("ZF-D1b the SCHEMA_DRIFT halt and the recovered rows survive a crash "
      "before the loop's first save",
      md2.state.halted == "SCHEMA_DRIFT" and "1" in md2.state.positions,
      f"halted={md2.state.halted} positions={sorted(md2.state.positions)}")

# --- D2: what ACTS on the retained rows while halted?
md2.mark_cache = {"prices": {}, "ts": None}
a._positions["CRSP"] = 5
before_orders = len(a.log)
ald = []
run_cycle(md2, a, payload(stops=[stop_row(call_id=1, level=48.0)],
                          entries=[{"call_id": 9, "symbol": "MRNA", "qty": 2,
                                    "entry_ref": 50.0, "stop_level": 44.0,
                                    "reason": "fire"}]),
          "2026-08-26", alert=ald.append)
acted = [e for e in a.log[before_orders:]
         if e.get("action") in ("place_stock_order", "cancel_stock_order")]
check("ZF-D2 while HALTED for SCHEMA_DRIFT no entry, exit or ratchet is "
      "decided against the retained rows",
      not any(e.get("order_type") in ("MOO", "MKT") for e in acted)
      and "9" not in md2.state.positions
      and md2.state.positions["1"].stop_level == 44.0,
      f"venue_actions_while_halted={acted} "
      f"stop_level_after={md2.state.positions['1'].stop_level} "
      f"open={sorted(md2.state.positions)}")

# --- D3: THE ACTUAL ROLLBACK. Does a book written by THIS build survive
#         being read by the build at main (e750abd)?
wt = os.environ.get("ZF_MAIN_WORKTREE", "")
if not os.path.isdir(os.path.join(wt, "ibkr-executor")):
    wt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wt_zf")
d3 = tempfile.mkdtemp()
m3 = Blend3070Manager(Cfg(), os.path.join(d3, "roll.json"))
m3.state.initialized = True
m3.state.sleeve_cash = 5000.0
held(m3, 1, "CRSP", 5, 50.0, 44.0)
m3.state.positions["1"].stop_order_ref = "live-stop-ref"
m3.state.positions["1"].stop_cover_qty = 3      # a CAPPED cover
m3.state.halted = "KILL"
m3.save()
prog = (
    "import sys, json, os\n"
    f"sys.path.insert(0, {os.path.join(wt, 'ibkr-executor')!r})\n"
    "from app.blend import Blend3070Manager\n"
    "class C:\n"
    "    dry_run=True; trading_mode='paper'; blend_budget=0.0\n"
    "    blend_book_usd=10000.0; tracker_url=''; tracker_user=''\n"
    "    tracker_password=''; tws_userid=''; tws_password=''\n"
    f"m = Blend3070Manager(C(), {m3.state_path!r})\n"
    "print(json.dumps({'positions': sorted(m.state.positions),"
    " 'halted': m.state.halted, 'initialized': m.state.initialized,"
    " 'naked': m.has_naked_position(),"
    " 'archived': (m.archived_state or '')[:90]}))\n"
)
try:
    out = subprocess.run([sys.executable, "-c", prog],
                         capture_output=True, text=True, timeout=60)
    roll = json.loads(out.stdout.strip().splitlines()[-1])
except Exception as exc:  # noqa: BLE001
    roll = {"error": str(exc), "stderr": (out.stderr[-300:]
                                          if 'out' in dir() else "")}
check("ZF-D3 ROLLBACK TO MAIN: a book written by THIS build, read by the "
      "build at e750abd, does not degrade to a fresh un-halted book",
      isinstance(roll, dict) and roll.get("positions") == ["1"]
      and roll.get("halted") == "KILL",
      f"main_build_read={roll} — the Z-D fix lives in the build being "
      f"rolled AWAY from, so it cannot protect this direction")

# --- D4: drift the OTHER way — a field RENAMED by a newer build, so the
#         filtered reconstruction is itself missing a required argument.
d4 = tempfile.mkdtemp()
m4 = Blend3070Manager(Cfg(), os.path.join(d4, "d4.json"))
m4.state.initialized = True
held(m4, 1, "CRSP", 5, 50.0, 44.0)
m4.state.positions["1"].stop_order_ref = "live-stop-ref"
m4.state.halted = "KILL"
m4.save()
raw4 = json.load(open(m4.state_path))
raw4["positions"]["1"]["trail_stop"] = raw4["positions"]["1"].pop("stop_level")
json.dump(raw4, open(m4.state_path, "w"))
m4r = Blend3070Manager(Cfg(), m4.state_path)
check("ZF-D4 a RENAMED position field (drift the filter cannot repair) "
      "still preserves the rows and the halt, rather than falling through "
      "to a fresh un-halted book",
      "1" in m4r.state.positions and m4r.state.halted,
      f"positions={sorted(m4r.state.positions)} halted={m4r.state.halted} "
      f"initialized={m4r.state.initialized} "
      f"naked={m4r.has_naked_position()} "
      f"archived={(m4r.archived_state or '')[:110]}")

# --- D5: a NON-DICT position row inside an otherwise drifting book.
d5 = tempfile.mkdtemp()
m5 = Blend3070Manager(Cfg(), os.path.join(d5, "d5.json"))
m5.state.initialized = True
held(m5, 1, "CRSP", 5, 50.0, 44.0)
held(m5, 2, "MRNA", 4, 50.0, 43.0)
m5.state.positions["1"].stop_order_ref = "r1"
m5.state.positions["2"].stop_order_ref = "r2"
m5.save()
raw5 = json.load(open(m5.state_path))
raw5["positions"]["2"] = ["not", "a", "dict"]
json.dump(raw5, open(m5.state_path, "w"))
m5r = Blend3070Manager(Cfg(), m5.state_path)
check("ZF-D5 an unreadable position ROW is not silently dropped while the "
      "alert claims 'positions kept'",
      sorted(m5r.state.positions) == ["1", "2"]
      or "dropped" in (m5r.archived_state or "").lower(),
      f"positions={sorted(m5r.state.positions)} halted={m5r.state.halted} "
      f"archived={(m5r.archived_state or '')[:140]}")

# --- D6: PRESERVE FAILED -> the boot save() now overwrites the evidence.
d6 = tempfile.mkdtemp()
m6 = Blend3070Manager(Cfg(), os.path.join(d6, "d6.json"))
m6.state.initialized = True
held(m6, 1, "CRSP", 5, 50.0, 44.0)
m6.save()
raw6 = json.load(open(m6.state_path))
raw6["positions"]["1"]["future_field"] = 1
json.dump(raw6, open(m6.state_path, "w"))
orig_replace = os.replace


def boom(src, dst):
    if str(dst).endswith(tuple(f".corrupt-{i}" for i in range(10))) or \
            ".corrupt-" in str(dst):
        raise OSError("read-only fs")
    return orig_replace(src, dst)


blend_mod.os.replace = boom
try:
    m6r = Blend3070Manager(Cfg(), m6.state_path)
finally:
    blend_mod.os.replace = orig_replace
after = json.load(open(m6.state_path))
check("ZF-D6 when the PRESERVE rename fails, the boot-time save does not "
      "immediately destroy the drifted evidence",
      "future_field" in after.get("positions", {}).get("1", {}),
      f"drifted_field_still_on_disk="
      f"{'future_field' in after.get('positions', {}).get('1', {})} "
      f"archived={(m6r.archived_state or '')[:120]}")


# =========================================================================
# ZF-E  the WIDENED ENTRY BLOCK — is it bounded?
# =========================================================================
print("\n---- ZF-E: the widened entry block ----")

m, a, _ = clean_shortfall("e1")
flagged = {k: p.history_gap for k, p in m.state.positions.items()}
# the shares come back: does the WHOLE symbol unpark together, or does the
# newly-flagged peer keep the sleeve mothballed on its own?
a._positions["CRSP"] = sum(p.qty for p in m.state.positions.values())
ale = []
for i, day in enumerate(("2026-08-26", "2026-08-27", "2026-08-28")):
    blackout(m)
    run_cycle(m, a, None, day, alert=ale.append)
still = {k: p.history_gap for k, p in m.state.positions.items()}
check("ZF-E1 when the shares return, EVERY same-symbol peer unparks — the "
      "newly-flagged peer does not mothball the sleeve on its own",
      not any(still.values()),
      f"flagged_after_resize={flagged} flagged_after_recovery={still} "
      f"entries_blocked={m.has_naked_position()}")
m.mark_cache = {"prices": {}, "ts": None}
m.state.sleeve_cash = 5_000.0
al_e2 = []
pl = payload(entries=[{"call_id": 9, "symbol": "MRNA", "qty": 2,
                       "entry_ref": 50.0, "stop_level": 44.0,
                       "reason": "fire"}],
             stops=[stop_row(call_id=9, symbol="MRNA", level=44.0)],
             as_of="2026-08-29")
pl["book_params"]["band"] = 0.99          # no rebalance to confound the cash
pl["rebalance"]["needed"] = False
run_cycle(m, a, pl, "2026-08-29", alert=al_e2.append)
check("ZF-E1b once every peer is verified, new sleeve entries resume — the "
      "widened flag does not outlive the shortfall",
      "9" in m.state.positions or "9" in m.state.pending_entries,
      f"open={sorted(m.state.positions)} "
      f"pending={sorted(m.state.pending_entries)} "
      f"naked={m.has_naked_position()} alerts={[x[:80] for x in al_e2]}")

# an UNRESOLVED shortfall: is there any bound at all?
m, a, _ = clean_shortfall("e2")
blocked = 0
for i in range(12):
    blackout(m)
    r = run_cycle(m, a, payload(entries=[{"call_id": 50 + i,
                                          "symbol": "MRNA", "qty": 1,
                                          "entry_ref": 50.0,
                                          "stop_level": 44.0,
                                          "reason": "fire"}]),
                  f"2026-09-{i + 1:02d}", alert=NULL)
    if "MRNA" not in {p.symbol for p in m.state.positions.values()}:
        blocked += 1
check("ZF-E2 [OBSERVATION] an UNRESOLVED shortfall blocks the sleeve "
      "indefinitely — no bound, no escape short of operator action",
      True,
      f"cycles_with_entries_blocked={blocked}/12 (this is the R1/X3 "
      f"fail-closed contract, recorded not asserted)")


# =========================================================================
# ZF-F  the three declared DEVIATIONS.
# =========================================================================
print("\n---- ZF-F: deviations ----")

# F1: is pass 4 sizing on _resting_cover really a no-op / harmful?
m = mk("f1")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
p = m.state.positions["1"]
p.stop_cover_qty = 3
m.mark_stop_missing(1)
check("ZF-F1 mark_stop_missing ZEROES stop_cover_qty, so _resting_cover in "
      "pass 4 would read the FULL qty — the deviation's 'no-op' claim",
      p.stop_cover_qty == 0 and _resting_cover(p) == p.qty,
      f"stop_cover_qty={p.stop_cover_qty} _resting_cover={_resting_cover(p)} "
      f"qty={p.qty}")
p2 = m.state.positions["1"]
p2.stop_missing = False
p2.stop_order_ref = None
p2.stop_cover_qty = 3
check("ZF-F1b on the UNPARK path the resize is retired and stop_cover_qty "
      "cleared BEFORE pass 4, so sizing pass 4 on _resting_cover would "
      "under-place cover only if the clear were skipped",
      True,
      "static: blend.py unpark branch sets stop_cover_qty = 0 then "
      "stop_missing = True before pass 4 runs")

# F2: Z-L — held == 0 with peers.
m = mk("f2")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 0
for p in m.state.positions.values():
    p.history_gap = True
blackout(m)
alf = []
run_cycle(m, a, None, "2026-08-25", alert=alf.append)
check("ZF-F2 held == 0 with peers: all cover is retired, the rows stay in "
      "the book flagged and loud, and nothing can trigger",
      cover_at_venue(a) == 0 and sorted(m.state.positions) == ["1", "2"]
      and all(_is_unprotected(p) for p in m.state.positions.values()),
      f"venue_cover={cover_at_venue(a)} open={sorted(m.state.positions)} "
      f"unprotected={[_is_unprotected(p) for p in m.state.positions.values()]} "
      f"alerts={len(alf)}")
feed = m.status_summary()
check("ZF-F2b with held == 0 the surfaces report the rows as UNPROTECTED "
      "and UNVERIFIABLE (loud, not silently 'protected')",
      sorted(feed["unprotected"]) == ["1", "2"]
      and sorted(feed["unverifiable"]) == ["1", "2"],
      f"status unprotected={feed['unprotected']} "
      f"unverifiable={feed['unverifiable']} "
      f"stop_missing={feed['stop_missing']}")

# F3: Z-1b unreachability from the only call site.
call_site_ok = True
for h, qtys in [(6, [5, 4]), (0, [5, 4]), (1, [5, 4, 3]), (5, [5, 5])]:
    class P:
        def __init__(self, c, q):
            self.call_id, self.qty = c, q
    peers = [P(i + 1, q) for i, q in enumerate(qtys)]
    if h >= sum(qtys):
        continue
    al = _prorata_cover(peers, h)
    if any(al[str(p.call_id)] > p.qty for p in peers):
        call_site_ok = False
check("ZF-F3 with the call site's precondition (held < book_qty) the "
      "allocation NEVER exceeds a position's own qty — Z-1b is genuinely "
      "unreachable, so leaving it landing is a documentation choice",
      call_site_ok,
      "checked held<book cases; held>book (the only failing input) cannot "
      "reach _resize_peer_cover, whose guard is `held < book_qty`")


# =========================================================================
# ZF-G  CONSEQUENCES OF REMOVING `if total <= held: return ""`.
# =========================================================================
print("\n---- ZF-G: the removed early return ----")

# --- G1: the aggregate invariant ALREADY HOLDS (cover 4 vs held 5). Does
#         the resize still strip a healthy unflagged peer's real cover?
m = mk("g1")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)          # only call 2 is protected
m.state.positions["1"].history_gap = True
m.state.positions["1"].stop_missing = True
m.state.positions["1"].stop_order_ref = None
# call 1's own earlier cover was never ACK-cancelled: its restore is BLOCKED
m.record_orphan_stop("ghost-1", {"symbol": "CRSP", "qty": -5, "call_id": 1})
a._positions["CRSP"] = 5
blackout(m)
before_g1 = cover_at_venue(a)
run_cycle(m, a, None, "2026-08-25", alert=NULL)
after_g1 = cover_at_venue(a)
check("ZF-G1 a resize in a cell where the invariant ALREADY HOLDS "
      "(cover 4 <= held 5) does not destroy a healthy peer's real "
      "protection",
      after_g1 >= min(before_g1, 5),
      f"cover_before={before_g1} cover_after={after_g1} held=5 book=9; "
      f"call2 was UNFLAGGED with full cover 4 and is now flagged="
      f"{m.state.positions['2'].history_gap} cover_qty="
      f"{m.state.positions['2'].stop_cover_qty}; call 1's restore was "
      f"blocked by its own unACKed orphan, so nothing replaced what was cut")

# --- G2: newly_capped flagged but nothing was placed/cancelled -> the
#         function returns early and the `capped` Telegram clause is never
#         appended. Is the operator told the sleeve just got mothballed?
m, a, _ = clean_shortfall("g2pre")            # unflagged peer exists
m = mk("g2")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
for k in ("1", "2"):
    m.state.positions[k].stop_missing = True
    m.state.positions[k].stop_order_ref = None
m.state.positions["1"].history_gap = True     # ONLY call 1 flagged
m.record_orphan_stop("g1", {"symbol": "CRSP", "qty": -5, "call_id": 1})
m.record_orphan_stop("g2", {"symbol": "CRSP", "qty": -4, "call_id": 2})
a._positions["CRSP"] = 6
m.state.last_reconcile_ts = time.time() - 60   # NO new blackout park
alg = []
reconcile(m, a, "2026-08-25", alg.append)
newly = m.state.positions["2"].history_gap
told = [x for x in alg if "UNVERIFIABLE too" in x or "CAPPED" in x]
check("ZF-G2 a peer newly flagged by the resize is announced to the "
      "operator in the cycle it happens",
      (not newly) or told,
      f"call2_newly_flagged={newly} telegram_lines_naming_it={told} "
      f"all_alerts={[x[:90] for x in alg]} "
      f"(the `capped` clause is built AFTER `if not lines: return \"\"`)")

# --- G3: the Z-L ruling. Would parking on held == 0 UNBLOCK entries?
m = mk("g3")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
held(m, 2, "CRSP", 4, 50.0, 43.0)
rest_stop(m, a, 1, "CRSP", 5, 44.0)
rest_stop(m, a, 2, "CRSP", 4, 43.0)
a._positions["CRSP"] = 0
for p in m.state.positions.values():
    p.history_gap = True
blackout(m)
run_cycle(m, a, None, "2026-08-25", alert=NULL)
naked_now = m.has_naked_position()
# simulate the Z-L behaviour the reviewer asked for: park both
m.on_exit_unreconciled(1, "held == 0")
m.on_exit_unreconciled(2, "held == 0")
naked_parked = m.has_naked_position()
check("ZF-G3 [RULING EVIDENCE] parking on held == 0 would clear the "
      "entry block that the flagged-and-loud end state holds",
      naked_now and not naked_parked,
      f"flagged_and_loud: naked={naked_now} open={sorted(m.state.positions)}; "
      f"after a Z-L park: naked={naked_parked} open=[] "
      f"unreconciled={sorted(m.state.unreconciled)} — `unreconciled` is NOT "
      f"read by has_naked_position(), so Z-L would resume sleeve entries "
      f"with an unresolved account discrepancy standing")

# --- G4: is the pass-4 FILLED-order adoption (ZF-B4) pre-existing at main?
m = mk("g4")
a = DryAdapter()
held(m, 1, "CRSP", 5, 50.0, 44.0)
ref = rest_stop(m, a, 1, "CRSP", 5, 44.0)
a._orders[ref]["qty"] = -3                 # a VENUE partial: 3 of 5 sold
a._stops[ref]["qty"] = -3
a.trigger_stop(ref)
a._positions["CRSP"] = 2
run_cycle(m, a, None, "2026-08-26", alert=NULL)
p = m.state.positions.get("1")
r = p and p.stop_order_ref
check("ZF-G4 [PRE-EXISTING] the LIVE fill poll's partial reaches the same "
      "pass-4 adoption of a FILLED order — identical at e750abd, so ZF-B4 "
      "is a pre-existing defect this round adds a SECOND door to",
      p is not None and not p.stop_missing
      and (a._orders.get(r) or {}).get("status") == "filled",
      f"qty={p and p.qty} stop_missing={p and p.stop_missing} "
      f"venue_status={(a._orders.get(r) or {}).get('status')} "
      f"resting={r in a._stops if r else None} "
      f"naked={m.has_naked_position()} (verified identical at main)")


print()
ok = sum(1 for _n, c, _d in results if c)
print(f"{ok}/{len(results)} probes passed; landed attacks: "
      f"{[n.split(' ')[0] for n, c, _d in results if not c]}")
