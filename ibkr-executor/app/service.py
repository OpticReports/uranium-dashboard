"""IBKR executor service: decision loop + control surface.

Modes (auto-selected):
  OFFLINE : no TWS credentials -> DryAdapter, full logic, zero broker calls
  PAPER   : credentials + TRADING_MODE=paper -> real gateway, paper account
  LIVE    : TRADING_MODE=live AND DRY_RUN=false -> real orders (Nov gate)
DRY_RUN=true with credentials still routes everything (mutations AND reads)
through the DryAdapter; the paper-phase stock/ETF adapter has LANDED and is
exercised in PAPER mode (DRY_RUN=false, TRADING_MODE=paper).
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query

from .alerts import send
from .config import settings
from .ib_adapter import DryAdapter
from .manager import LadderManager
from .nino import FEED_TIMEOUT, nino34_weekly

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

MGR: LadderManager | None = None
MGR_LOCK = threading.Lock()        # x12: serializes LADDER state writes the
                                   # same way BLEND_LOCK does for the blend —
                                   # /kill and /resume mutate legs/halted on
                                   # API threads while _loop steps and saves
                                   # on the loop thread. NEVER hold this and
                                   # BLEND_LOCK at the same time (the two
                                   # sections are always disjoint): a fixed
                                   # order is not needed if they never nest.
BLEND = None                       # Blend3070Manager, ONLY when BLEND_ENABLED
BLEND_LOCK = threading.Lock()      # serializes a whole blend CYCLE (loop
                                   # thread) against /resume (API thread).
                                   # A cycle holds it across its venue
                                   # round-trips, so it is NOT a lock the
                                   # emergency stop may ever wait on — see
                                   # BLEND_HALT_LOCK.
BLEND_HALT_LOCK = threading.Lock()  # MF-A: the halt path's OWN lock, held
                                   # only for the /kill journal write and
                                   # the /resume clear — ONE atomic local
                                   # save each (fsync + rename: measured
                                   # 2.7-8.0ms on a 59 KB book, mf2-13),
                                   # never across a venue or network call
                                   # and never for a whole cycle. /kill
                                   # used to take
                                   # BLEND_LOCK, so its own halt queued
                                   # behind an in-flight run_cycle: measured
                                   # 19.505s with no halt, no ladder close,
                                   # no alert and no HTTP response for the
                                   # whole window, while the comment claimed
                                   # it "halts the book immediately". LOCK
                                   # ORDER, the only nesting that exists:
                                   # BLEND_LOCK -> BLEND_HALT_LOCK (/resume).
                                   # /kill takes BLEND_HALT_LOCK alone and
                                   # must NEVER take BLEND_LOCK.
LOOP_WAKE = threading.Event()      # /kill pokes the loop so a queued blend
                                   # flatten runs at the TOP of the next
                                   # iteration instead of a full poll
                                   # interval later (R2 + MF-1)
KILL_LOCK_WAIT_S = 0.5             # MF-A: how long /kill will wait for
                                   # MGR_LOCK to record its halt in the
                                   # BOOK as well as in the sentinel. Only
                                   # a cycle INSIDE the ladder section
                                   # holds it, and that section's gateway
                                   # round-trips are unbounded (measured
                                   # 19.4s with a 20s-hanging mark()), so
                                   # the wait is bounded and the sentinel
                                   # carries the halt when it expires. It
                                   # is NOT a bound on /kill's own work:
                                   # /kill makes no venue call at all
                                   # (MF2-1).
LADDER_KILL = threading.Event()    # MF-A/MF2-1: set by every /kill. The
                                   # ladder is halted at once (memory +
                                   # the on-disk sentinel); the LEG CLOSES
                                   # belong to the loop thread, which owns
                                   # the adapter (R2) and is the only
                                   # thread that may hold MGR_LOCK across
                                   # gateway I/O. It consumes this flag
                                   # either at the top of its next
                                   # iteration (a parked loop: the normal
                                   # case, ahead of both feeds) or at the
                                   # end of the ladder section that was
                                   # holding the lock. /resume clears it —
                                   # a queued kill must never fire at a
                                   # RESUMED ladder (MF2-3).
LOOP_GEN = 0                       # MF-2: loop LIFECYCLE. Every lifespan used
LOOP_GEN_LOCK = threading.Lock()   # to leak a daemon loop thread that never
                                   # exited and kept reading MGR/ADAPTER/BLEND
                                   # — a SUPERSEDED loop ran full cycles
                                   # against the CURRENT globals (it even
                                   # performed an emergency flatten in a
                                   # reviewer's reproduction) and its
                                   # LOOP_WAKE.clear() wiped the CURRENT
                                   # loop's wake event. Each loop captures its
                                   # generation at start and its OWN wake
                                   # event; a bumped generation means "you are
                                   # superseded: exit at the next checkpoint,
                                   # touch nothing".
ADAPTER = None
LAST: dict = {"loop_ok": 0.0, "nino34": None, "mode": "OFFLINE"}
# Last blend cycle outcome (feed's last_cycle + /health blend_loop): a
# silently failing blend loop must be visible from the outside.
BLEND_CYCLE: dict = {"date": None, "ok": None, "error": None,
                     "error_ts": None}


def _auth(hdr: str | None, q: str | None) -> None:
    if settings.exec_token and hdr != settings.exec_token and q != settings.exec_token:
        raise HTTPException(status_code=401, detail="bad exec token")


def _build():
    global MGR, ADAPTER, BLEND
    MGR = LadderManager(settings, settings.state_path)
    if MGR.archived_state:
        # x12: an unreadable ladder file used to become a fresh, un-halted
        # ladder in silence — open legs and `halted` forgotten.
        logger.error("ladder: %s", MGR.archived_state)
        send(f"🚨🚨 ibkr ladder: {MGR.archived_state} — verify open legs at "
             f"the venue before the ladder trades again")
    # blend3070 is opt-in: BLEND_ENABLED=false (the default) leaves the
    # service byte-for-byte as before — no manager, no polling, no /status
    # section, no state file.
    if settings.blend_enabled:
        from .blend import Blend3070Manager
        BLEND = Blend3070Manager(settings, settings.blend_state_path)
        if BLEND.archived_state:
            if BLEND.archived_state_critical:
                # y4: an UNREADABLE book is not a routine mode change —
                # open positions and `halted` were just forgotten. Same
                # severity as the ladder's sibling path.
                logger.error("blend: %s", BLEND.archived_state)
                send(f"🚨🚨 blend: {BLEND.archived_state} — verify open "
                     f"positions and resting stops at the venue")
            else:
                # Mode-transition guard: the previous book's fills belong to
                # another mode (e.g. DRY placeholder prices) — starting clean.
                logger.warning("blend: %s", BLEND.archived_state)
                send(f"⚠️ blend: starting a FRESH book — {BLEND.archived_state}")
    if not (settings.tws_userid and settings.tws_password):
        ADAPTER = DryAdapter()
        LAST["mode"] = "OFFLINE"
        logger.warning("OFFLINE mode: no TWS credentials; DryAdapter active")
        return
    if settings.dry_run:
        ADAPTER = DryAdapter()
        LAST["mode"] = f"DRY ({settings.trading_mode})"
        logger.warning("DRY_RUN with credentials: mutations stay simulated")
        return
    from .ib_adapter import IBAdapter
    ADAPTER = IBAdapter(settings)
    LAST["mode"] = settings.trading_mode.upper()


def _superseded(gen: int) -> bool:
    """MF-2: has a later lifespan (or shutdown) replaced this loop? A loop
    that answers True must not touch MGR/ADAPTER/BLEND again and must not
    clear the CURRENT loop's wake event — it exits at this checkpoint."""
    if gen == LOOP_GEN:
        return False
    logger.info("executor loop gen %s superseded by gen %s — exiting",
                gen, LOOP_GEN)
    return True


def _blend_cycle(payload: dict | None, today: str) -> None:
    """ONE blend cycle (reconcile-first, N14) with its outcome recorded for
    /health + the feed. Called at most twice per iteration: FIRST, with no
    payload, when a /kill flatten is journaled (MF-1 — the emergency stop
    must not queue behind a feed), then in the ordinary tracker-driven
    position."""
    from .blend import run_cycle
    try:
        with BLEND_LOCK:
            # The alert sink is resolved at EMIT time, like every other
            # alert in this module. MF-A made that matter: /kill journals
            # its flatten without waiting for BLEND_LOCK, so a cycle that
            # started BEFORE the request can now be the one that executes
            # it and reports what closed — binding `send` at call time
            # would send that completion report to whatever sink was
            # installed when the cycle began.
            run_cycle(BLEND, ADAPTER, payload, today,
                      alert=lambda msg: send(msg))
        BLEND_CYCLE.update({"date": today, "ok": True,
                            "error": None})
    except Exception as exc:  # noqa: BLE001
        logger.exception("blend cycle error: %s", exc)
        BLEND_CYCLE.update({"date": today, "ok": False,
                            "error": str(exc),
                            "error_ts": time.time()})
        if BLEND.state.flatten_request is not None:
            # R2: a queued kill-flatten must never fail
            # silently — loud every failing cycle until done.
            send(f"🚨🚨 blend: cycle FAILED with a /kill "
                 f"flatten QUEUED ({exc}) — nothing flattened "
                 f"yet; the loop retries next cycle, book "
                 f"stays halted")


def _kill_ladder(today: str) -> tuple[list[str], list[str]]:
    """Close every OPEN ladder leg and HALT the ladder. Returns (closed,
    still_open) BY OUTCOME, not by intent — MF2-4: `_kill_ladder` swallowed
    every per-leg failure with a log line, and /kill answered
    `ladder: "closed"` / "all legs closed" with the leg still OPEN at the
    venue after every close_spread RAISED. What a leg ended up as in the
    book is the honest answer (a close that booked but could not be SAVED
    is still closed), and the caller says exactly that.

    THE CALLER MUST HOLD MGR_LOCK, and the caller is always the LOOP
    thread: it owns the adapter's ib_async event loop (R2) and it is the
    only thread allowed to hold MGR_LOCK across gateway I/O (MF2-1)."""
    closed: list[str] = []
    still_open: list[str] = []
    for key, leg in MGR.state.legs.items():
        if leg.status != "OPEN":
            continue
        if leg.order_ref:
            try:
                r = ADAPTER.close_spread(leg.order_ref)
                MGR.on_closed(key, r["value"], "manual kill", today)
            except Exception as exc:  # noqa: BLE001
                logger.exception("kill close %s failed: %s", key, exc)
        else:
            # An OPEN leg with no order_ref cannot be closed from here at
            # all (a y2 drift can produce one). It used to be skipped in
            # silence; it is REPORTED now, like any other leg the kill
            # could not close.
            logger.error("kill close %s: no order_ref in the book", key)
        (closed if MGR.state.legs[key].status != "OPEN"
         else still_open).append(key)
    MGR.state.halted = "KILL"
    MGR.save()
    return closed, still_open


def _consume_ladder_kill(today: str) -> str:
    """Execute the kill /kill handed to this thread and return the alert
    that reports what ACTUALLY happened. THE CALLER MUST HOLD MGR_LOCK.

    The kill is consumed only when every open leg is actually closed —
    otherwise the flag and the disk sentinel BOTH stay set and the loop
    retries it every cycle, alerting every time, exactly as a failing blend
    kill-flatten does (R2: an emergency stop may not fail quietly). Same
    for a raise: the halt could not be persisted, so nothing is consumed
    (mf2-8 — the clear used to happen BEFORE the work, so a raise dropped
    the flag with nothing left to re-trigger it)."""
    closed, still_open = _kill_ladder(today)
    if still_open:
        return ("🚨🚨 ACTION NEEDED (you) — ibkr ladder: the /kill you sent "
                f"could NOT close leg(s) {', '.join(still_open)} (the "
                f"gateway refused, or the book carries no order reference "
                f"for them — see the service log)"
                + (f"; leg(s) {', '.join(closed)} did close" if closed else "")
                + ". They are STILL OPEN at the venue — close them by hand "
                  "in TWS. The ladder is halted, and the loop retries the "
                  "close every cycle until it lands or you /resume")
    MGR.clear_kill()            # MF2-2: the kill is executed — consume the
    LADDER_KILL.clear()         # on-disk sentinel, then the in-memory flag
    if closed:
        return (f"🔴 ibkr ladder: the /kill you sent has now closed leg(s) "
                f"{', '.join(closed)}; the ladder stays halted until "
                f"/resume")
    return ("🔴 ibkr ladder: the /kill you sent found no OPEN legs to close; "
            "the ladder stays halted until /resume")


def _loop(gen: int, wake: threading.Event):
    # `wake` is THIS loop's own event (created by _start_loop, which also
    # published it as LOOP_WAKE for /kill). A superseded loop waits on and
    # clears its OWN event, never the current loop's (MF-2).
    try:
        _build()
    except Exception as exc:  # noqa: BLE001
        # A constructor raise (gateway auth, ib_async loop binding) must
        # never kill the loop thread SILENTLY (adapter review M2 sub-note):
        # alert loudly and stop — /health then shows loop_age_s as None.
        logger.exception("executor build failed: %s", exc)
        send(f"🚨🚨 ibkr-executor FAILED TO BUILD ({exc}) — NO trading "
             f"loop is running; fix config/gateway and redeploy")
        return
    send(f"🌊 ibkr-executor up — mode {LAST['mode']}, "
         f"ladder legs {[k for k in MGR.state.legs]}")
    if MGR.kill_pending:
        # MF2-2: a /kill whose leg closes had not completed when the
        # service went down. The halt came back with the book (the
        # sentinel re-asserts it); the CLOSES are re-armed here so the
        # promise the operator was given survives the restart.
        LADDER_KILL.set()
        send("🔴 ibkr ladder: a /kill from before this restart is still "
             "in force — the ladder is HALTED and its open legs are "
             "closed as the first act of this loop\'s first iteration")
    while True:
        if _superseded(gen):
            return
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            # MF-1: a journaled /kill flatten is the FIRST thing an
            # iteration does — ahead of the NOAA fetch, the ladder's
            # gateway round-trips and the tracker poll. It used to run at
            # the END of the iteration, so kill-to-flatten was exactly the
            # loop's feed latency (measured: a 3s feed -> 3.01s, an 8s feed
            # -> 8.01s, a 25s feed -> no flatten at all inside 20s) while
            # the comment and the operator alert promised "within seconds".
            # Reconcile-first (N14) is preserved: run_cycle still reconciles
            # before it flattens, so stop fills book before anything sells.
            # No payload is fetched for this pass — the emergency stop takes
            # no tracker decisions, so it waits on no feed.
            flatten_ran = False
            if BLEND is not None and BLEND.state.flatten_request is not None:
                _blend_cycle(None, today)
                flatten_ran = True
            kill_handled = False
            if LADDER_KILL.is_set():
                # MF2-1: EVERY ladder leg close is this thread's job now.
                # /kill used to make the close_spread call itself whenever
                # MGR_LOCK happened to be free — which is the deployed
                # steady state — and that call carries no timeout: measured
                # 20.008s of dead air on a wedged gateway, with no halt on
                # disk, no Telegram and no HTTP response, the exact shape
                # MF-A was created to eliminate. The closes run HERE,
                # ahead of the NOAA fetch and the tracker poll (MF-1's
                # order, real shares first), so they wait on no feed.
                kill_handled = True
                try:
                    with MGR_LOCK:
                        kill_msg = _consume_ladder_kill(today)
                    send(kill_msg)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("deferred ladder kill failed: %s", exc)
                    send(f"🚨🚨 ibkr ladder: the /kill you sent could not be "
                         f"completed ({exc}) — the ladder is HALTED, the "
                         f"kill stays queued and the loop retries it every "
                         f"cycle until it lands")
            nino = nino34_weekly()
            if _superseded(gen):
                return          # the feed call is the long park (MF-2)
            LAST["nino34"] = nino
            if (not flatten_ran and BLEND is not None
                    and BLEND.state.flatten_request is not None):
                # A /kill that landed while this iteration was parked inside
                # the feed call above must not ALSO wait for the ladder's
                # gateway round-trips and the tracker poll (MF-1). What it
                # does wait for is the rest of that feed call — and MF-A
                # made FEED_TIMEOUT a real bound on it (feeds.with_deadline;
                # the httpx timeout it also passes is per-operation and a
                # trickling server walked straight through it). What is NOT
                # bounded is the ladder section below, so a kill landing
                # THERE waits on a gateway with no deadline — said plainly
                # in the /kill alert and README §6, never as a number.
                _blend_cycle(None, today)
            marks = {}
            # x12: the ladder block mutates and persists MGR — /kill and
            # /resume do the same from API threads. Serialize them exactly
            # as BLEND_LOCK serializes the blend (alerts are sent outside
            # the lock so a slow Telegram call never holds it).
            ladder_alerts: list[str] = []
            with MGR_LOCK:
                for key, leg in MGR.state.legs.items():
                    if leg.status == "OPEN" and leg.order_ref:
                        try:
                            marks[key] = ADAPTER.mark(leg.order_ref)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("mark %s failed: %s", key, exc)
                intents = MGR.step(today, nino, marks)
                for it in intents:
                    try:
                        if it["action"] == "OPEN":
                            r = ADAPTER.open_spread(it["structure"], it["budget"])
                            MGR.on_opened(it["leg"], r["premium"], r["order_ref"], today)
                            ladder_alerts.append(
                                f"⚡ ibkr ladder OPEN {it['leg']}: {it['reason']} "
                                f"(premium ${r['premium']:,.0f}, mode {LAST['mode']})")
                        elif it["action"] == "CLOSE":
                            leg = MGR.state.legs[it["leg"]]
                            r = ADAPTER.close_spread(leg.order_ref)
                            MGR.on_closed(it["leg"], r["value"], it["reason"], today)
                            ladder_alerts.append(
                                f"⚡ ibkr ladder CLOSE {it['leg']}: {it['reason']} "
                                f"-> ${r['value']:,.0f}")
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("intent %s failed: %s", it, exc)
                        ladder_alerts.append(
                            f"🚨 ibkr intent failed ({it['action']} {it['leg']}): {exc}\n"
                            f"→ no action needed from you — forward this to Claude "
                            f"(if it repeats, gateway/credentials may need you)")
                if LADDER_KILL.is_set() and not kill_handled:
                    # MF-A: a /kill landed while THIS section held MGR_LOCK.
                    # The ladder was halted the instant the operator hit
                    # /kill; closing the legs is ours to do, here, before
                    # this section releases the lock (the top-of-iteration
                    # pass above cannot have run for a kill that landed
                    # after it — and when it DID run, `kill_handled` keeps
                    # this from being a second attempt in one iteration).
                    ladder_alerts.append(_consume_ladder_kill(today))
                MGR.save()
            for msg in ladder_alerts:
                send(msg)
            if BLEND is not None:
                from .blend import fetch_intents
                try:
                    payload = fetch_intents(settings)
                except Exception as exc:  # noqa: BLE001
                    # fetch_intents already swallows transport errors; if it
                    # ever raises anyway the CYCLE must still run (reconcile
                    # + a queued flatten are unconditional) and be recorded.
                    logger.exception("blend intents fetch raised: %s", exc)
                    payload = None
                if payload is None:
                    # Tracker outage: the cycle STILL runs — reconcile
                    # (stop-fill ingestion, orphan cancel retries,
                    # STOP_MISSING re-placement) and the local 90-day
                    # belt are unconditional; only tracker-dependent
                    # decisions are skipped (counter-agent N13).
                    logger.warning("blend: tracker unreachable; "
                                   "reconcile-only cycle (no new "
                                   "decisions)")
                if _superseded(gen):
                    return      # the tracker poll is the other park (MF-2)
                _blend_cycle(payload, today)
            LAST["loop_ok"] = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("loop error: %s", exc)
        wake.wait(settings.poll_seconds)        # /kill sets it to skip the
        wake.clear()                            # wait (queued flatten)


from contextlib import asynccontextmanager


def _start_loop() -> tuple[threading.Thread, threading.Event, int]:
    """Start THE loop thread for this lifespan and publish its wake event."""
    global LOOP_WAKE, LOOP_GEN
    LADDER_KILL.clear()         # MF-A: never inherit a previous lifespan's
                                # in-memory flag. The DISK sentinel is the
                                # record that outlives a restart, and the
                                # new loop re-arms from it after _build
                                # (MF2-2) — this only stops a superseded
                                # lifespan's flag from riding along.
    wake = threading.Event()
    with LOOP_GEN_LOCK:
        LOOP_GEN += 1
        gen = LOOP_GEN
        # mf-8: published INSIDE the lock. Two concurrent starts could
        # otherwise publish in reverse order and leave LOOP_WAKE owned by
        # the already-superseded loop — reproduced with a widened window
        # (live_gen=2, LOOP_WAKE belongs to gen 1), and /kill would then
        # wake nobody and the queued flatten wait a full poll interval.
        LOOP_WAKE = wake        # /kill wakes the CURRENT loop only
    t = threading.Thread(target=_loop, args=(gen, wake), daemon=True,
                         name=f"exec-loop-{gen}")
    t.start()
    return t, wake, gen


def _stop_loop(t: threading.Thread, wake: threading.Event, gen: int) -> None:
    """MF-2: supersede this lifespan's loop and wait briefly for it to go.
    Bumping the generation is what actually ends it — the join only avoids
    an overlap window; a loop parked in a feed call exits at its next
    checkpoint and touches nothing after that.

    The bump happens ONLY while this loop is still the current one: if a
    newer lifespan has already started its loop, this one is superseded
    already and bumping again would supersede the LIVE loop instead."""
    global LOOP_GEN
    with LOOP_GEN_LOCK:
        if LOOP_GEN == gen:
            LOOP_GEN += 1
    wake.set()                  # skip the poll wait, exit now
    t.join(timeout=1.0)         # courtesy only: the generation bump is what
                                # ends it, and a parked loop exits in <1ms
    if t.is_alive():
        logger.warning("executor loop %s still finishing its cycle at "
                       "shutdown; it exits at its next checkpoint", t.name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    t, wake, gen = _start_loop()
    try:
        yield
    finally:
        _stop_loop(t, wake, gen)


app = FastAPI(title="IBKR Executor", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    body = {"status": "ok", "service": "ibkr-executor", "mode": LAST["mode"],
            "loop_age_s": round(time.time() - LAST["loop_ok"], 1)
            if LAST["loop_ok"] else None}
    # The blend_loop section exists ONLY when BLEND_ENABLED (same doctrine as
    # /status's blend section): a cycle that keeps raising is caught by the
    # main loop and would otherwise fail silently — surface it here.
    if BLEND is not None:
        err_ts = BLEND_CYCLE.get("error_ts")
        body["blend_loop"] = {
            "ok": BLEND_CYCLE["ok"] is not False,
            "last_error_age_s": round(time.time() - err_ts, 1)
            if err_ts else None}
    return body


@app.get("/status")
def status(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ready": False}
    body = {"ready": True, "mode": LAST["mode"], "dry_run": settings.dry_run,
            "nino34_weekly": LAST["nino34"],
            "ladder": {k: vars(v) for k, v in MGR.state.legs.items()},
            "banked": MGR.state.banked, "halted": MGR.state.halted,
            "leg_budget": MGR.leg_budget(),
            "events": MGR.state.events[-40:],
            "dry_intents": getattr(ADAPTER, "log", [])[-40:]}
    # The "blend" section exists ONLY when BLEND_ENABLED: with the flag off,
    # /status is byte-identical to the pre-blend service.
    if BLEND is not None:
        # M2 (thread-safety): this handler runs on a FastAPI worker thread;
        # the ib_async event loop belongs to the service loop thread. Serve
        # the loop-thread-refreshed mark cache — NEVER call the adapter
        # from here. Staleness is shown (marks_age_s), not hidden.
        marks = BLEND.mark_cache
        body["blend"] = BLEND.status_summary(marks.get("prices") or None)
        ts = marks.get("ts")
        body["blend"]["marks_age_s"] = (round(time.time() - ts, 1)
                                        if ts else None)
    return body


@app.get("/blend/feed")
def blend_feed(x_read_token: str | None = Header(default=None)):
    """READ-ONLY public-safe blend feed (the research site's Execution tab,
    reverse-proxied by the tracker). Gated by READ_TOKEN via X-Read-Token —
    a separate, weaker credential than EXEC_TOKEN: it can only read book
    state, never kill/resume or see exec surfaces. Empty READ_TOKEN (the
    default) or BLEND_ENABLED=false keeps the endpoint a 404 — nothing is
    exposed until Casey explicitly sets the token."""
    if BLEND is None or not settings.read_token:
        raise HTTPException(status_code=404, detail="not found")
    supplied = x_read_token or ""
    if not secrets.compare_digest(supplied.encode("utf-8"),
                                  settings.read_token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="bad read token")
    # M2 (thread-safety): serve the loop-thread-refreshed mark cache only —
    # this handler runs on a FastAPI worker thread and must NEVER touch the
    # adapter/ib_async loop. Staleness is shown (marks_age_s), not hidden.
    marks = BLEND.mark_cache
    prices: dict = marks.get("prices") or {}
    today = datetime.now(timezone.utc).date().isoformat()
    body = BLEND.feed(prices, today)
    ts = marks.get("ts")
    body["marks_age_s"] = round(time.time() - ts, 1) if ts else None
    body["mode"] = LAST["mode"]
    body["last_cycle"] = {"date": BLEND_CYCLE["date"], "ok": BLEND_CYCLE["ok"],
                          "error": BLEND_CYCLE["error"]}
    return body


@app.api_route("/kill", methods=["GET", "POST"])
def kill(x_exec_token: str | None = Header(default=None),
         token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ok": False}
    blend_note = ""
    today = datetime.now(timezone.utc).date().isoformat()
    # The BLEND halt runs FIRST: real shares are what it protects, and it
    # is the cheapest action here (one journal write under
    # BLEND_HALT_LOCK). Neither stage reaches the venue from this thread
    # any more (MF2-1), but this order is still the law: nothing the ladder
    # does may delay halting the book.
    if BLEND is not None:
        # R2 (two-stage kill): this handler runs on a FastAPI worker
        # thread, but ib_async binds its event loop to the thread that owns
        # the connection — the blend loop thread. An API-thread flatten
        # pumps a FRESH loop against the shared transport: every wait times
        # out, healthy stops get mis-parked as "likely filled", and
        # cross-thread writes risk session corruption. So /kill only
        # JOURNALS the flatten request (persisted — survives a restart) and
        # halts the book immediately; the loop thread executes the flatten
        # as the FIRST act of its next iteration (woken right away below),
        # ahead of the NOAA fetch, the ladder and the tracker poll (MF-1),
        # with reconcile-first semantics (N14) and alerts what actually
        # closed vs parked — the summary here claims only what is true NOW.
        #
        # MF-A: "immediately" is now true of the HALT itself. This used to
        # take BLEND_LOCK, which an in-flight run_cycle holds across its
        # venue round-trips: measured, the whole handler blocked 19.505s —
        # no halt, no ladder close, no Telegram, no HTTP response — while
        # this comment said it halted the book immediately. The journal
        # write has its own lock now, held for ONE atomic local save
        # (fsync + rename, measured 2.7-8.0ms on a 59 KB book — never a
        # venue call, never a whole cycle: mf2-13), so the halt and this
        # response never queue behind a cycle. What still waits for the
        # loop is the FLATTEN, because only
        # the loop thread may touch the adapter; the bound on THAT is
        # whatever remains of a cycle already in flight — its feeds carry a
        # total deadline (nino.FEED_TIMEOUT / blend.FEED_TIMEOUT) but its
        # IB gateway round-trips carry none, so no honest number can be
        # promised for a wedged gateway. The alert below says exactly that.
        from .blend import FEED_TIMEOUT as BLEND_FEED_TIMEOUT
        with BLEND_HALT_LOCK:
            BLEND.request_flatten(today)
        LOOP_WAKE.set()                 # skip the poll wait; flatten first
        loop_age = (time.time() - LAST["loop_ok"]) if LAST["loop_ok"] else None
        loop_warn = ""
        if loop_age is None or loop_age > 2 * settings.poll_seconds:
            loop_warn = (" ⚠️ the execution loop looks DOWN (see /health) "
                         "— the flatten will NOT run until it recovers; "
                         "flatten manually if urgent")
        blend_note = (" + blend HALTED (journalled the moment you hit "
                      "/kill — the halt takes no lock a cycle can hold), "
                      "flatten QUEUED for the execution loop (it owns the "
                      "venue connection) and it runs FIRST in the loop's "
                      "next iteration — immediately when the loop is idle, "
                      "which is the normal case. If a cycle is already in "
                      "flight the flatten waits that cycle out: its feeds "
                      f"are capped at {FEED_TIMEOUT:.0f}s (NOAA) and "
                      f"{BLEND_FEED_TIMEOUT:.0f}s (tracker) TOTAL, but its "
                      "IB gateway round-trips are NOT bounded, so a wedged "
                      "gateway can stretch that wait with no bound this "
                      "code can state — watch /health and flatten manually "
                      "if nothing lands. A completion alert will state "
                      "what closed vs parked" + loop_warn)
    # The LADDER halt is TWO-STAGE too, for the same reason the blend one
    # is (MF2-1/MF2-2). This handler used to call close_spread ITSELF
    # whenever MGR_LOCK happened to be free — the deployed steady state, a
    # parked loop — and that call carries no timeout: measured, /kill
    # blocked 20.008s on a wedged gateway with one OPEN leg, with no halt
    # on disk, no Telegram and no HTTP response for the whole window.
    # KILL_LOCK_WAIT_S never bounded that: it bounds the WAIT for the lock,
    # never /kill's own round-trip. So:
    #   stage 1 (here): journal the kill, halt the ladder, answer;
    #   stage 2 (the loop): close the legs, FIRST thing in its next
    #                       iteration, on the thread that owns the adapter.
    # x12 is untouched — the read-modify-write of `legs` (MGR.save) still
    # happens only under MGR_LOCK, and the sentinel is a file of its own.
    ladder_note, ladder_state = "", "close_queued"
    durability_warn = ""
    try:
        MGR.state.halted = "KILL"       # in memory the instant you hit /kill
        LADDER_KILL.set()               # ...and the closes are the loop's
        LOOP_WAKE.set()
        try:
            MGR.journal_kill(today)     # durable BEFORE the response, and
                                        # before the lock: no cycle can gate
                                        # it and a restart re-asserts it
        except Exception as exc:  # noqa: BLE001
            logger.exception("kill: journalling the ladder halt failed: %s",
                             exc)
            durability_warn = (f" ⚠️ the ladder halt could NOT be written to "
                               f"disk ({exc}): it holds while this process "
                               f"lives, but a RESTART would lose it — halt "
                               f"by hand at the venue if the service "
                               f"restarts")
        open_legs: list[str] | None = None
        # MGR_LOCK is taken only AFTER the blend section above released
        # BLEND_HALT_LOCK — no two of these locks are ever held together.
        # It is wanted, not needed: with it the halt lands in the book file
        # too, and the legs can be counted safely. Without it (a cycle is
        # inside the ladder section) the sentinel above has already made
        # the halt durable and the legs are the loop's to read.
        if MGR_LOCK.acquire(timeout=KILL_LOCK_WAIT_S):
            try:
                open_legs = [k for k, leg in MGR.state.legs.items()
                             if leg.status == "OPEN"]
                MGR.save()              # local write; no gateway call here
            except Exception as exc:  # noqa: BLE001
                # The sentinel is what makes the halt durable; this write
                # only mirrors it into the book. Degrade, never 500.
                logger.exception("kill: ladder book save failed: %s", exc)
                open_legs = None
            finally:
                MGR_LOCK.release()
        if open_legs == []:
            LADDER_KILL.clear()
            MGR.clear_kill()
            ladder_note = "no legs were open"
            ladder_state = "closed"
        else:
            ladder_note = (
                ("leg(s) " + ", ".join(open_legs) + " are"
                 if open_legs else "any open legs are")
                + " NOT closed yet — only the execution loop may talk to "
                  "the gateway (it owns the connection), so it closes them "
                  "as the FIRST thing it does, ahead of both feeds, and "
                  "alerts what actually closed. A wedged gateway has no "
                  "bound this code can state, so watch /status and close by "
                  "hand in TWS if nothing lands. The ladder is halted from "
                  "now"
                + ("" if durability_warn else
                   " — on disk, so a restart keeps it"))
    except Exception as exc:  # noqa: BLE001
        # mf2-11: this used to 500 with no Telegram at all, leaving the
        # operator with no word that the BLEND book above is already
        # halted with its flatten queued.
        logger.exception("kill: ladder halt failed: %s", exc)
        ladder_note = (f"the ladder halt FAILED ({exc}) — HALT THE LADDER "
                       f"BY HAND at the venue")
        ladder_state = "halt_failed"
    send(f"🔴 ACTION NEEDED (you) — ibkr ladder KILLED: {ladder_note}, "
         f"ladder halted{durability_warn}{blend_note}\n→ it stays halted "
         f"until you hit /resume?token=YOUR_TOKEN")
    return {"ok": True, "halted": "KILL", "ladder": ladder_state,
            "blend": "flatten_queued" if BLEND is not None else None}


@app.api_route("/resume", methods=["GET", "POST"])
def resume(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ok": False}
    with MGR_LOCK:                  # x12: same serialization as /kill
        # Z-K: /resume clears EVERY halt, a data-integrity SCHEMA_DRIFT
        # exactly like a KILL. That is deliberate — y2 keeps every leg field
        # this build understands across a drifted load, so a resumed ladder
        # re-opens only genuinely WAITING legs and an OPEN leg keeps its
        # order_ref — but the operator must be told WHICH halt they just
        # cleared, or "resumed" reads like an ordinary un-kill.
        prior = MGR.state.halted
        MGR.state.halted = None
        # MF2-3: a QUEUED ladder kill must never fire at a RESUMED ladder —
        # the blend half has had exactly this guard since R2 ("a stale kill
        # must never flatten a resumed book"). Measured without it: the
        # operator re-opened a leg after resuming and the deferred kill
        # CLOSED it. Both halves of the record go: the flag the loop reads
        # and the sentinel a restart would read it back from.
        ladder_kill_dropped = LADDER_KILL.is_set() or MGR.kill_pending
        LADDER_KILL.clear()
        MGR.clear_kill()
        MGR.save()
    blend_prior = None
    if BLEND is not None:
        # N3: /resume must not race the loop thread's cycle (a resume
        # interleaved with execute_flatten un-halts a book that is being
        # sold and lets the same cycle place fresh entries). BLEND_LOCK
        # serializes it behind any in-flight cycle, flatten included.
        # MF-A: BLEND_HALT_LOCK on top, so a /kill journalling a flatten
        # (which no longer takes BLEND_LOCK) cannot interleave with the
        # clear. Lock order is always BLEND_LOCK -> BLEND_HALT_LOCK.
        with BLEND_LOCK, BLEND_HALT_LOCK:
            blend_prior = BLEND.state.halted
            BLEND.resume()
    drift = "SCHEMA_DRIFT" in (prior, blend_prior)
    send("ibkr ladder resumed"
         + (f" (cleared halt: {prior})" if prior else " (was not halted)")
         + ("; a /kill whose leg closes had not run yet was CANCELLED — "
            "any leg still OPEN stays open (check /status)"
            if ladder_kill_dropped else "")
         + (f"; blend book resumed (cleared halt: {blend_prior})"
            if blend_prior else "")
         + ("\n→ SCHEMA_DRIFT was a data-integrity halt, not a kill: those "
            "rows came from a build this one does not fully understand. "
            "Every field this build knows was kept and nothing live was "
            "re-opened — confirm the venue matches the book before trusting "
            "the next cycle. Any row whose missing fields had to be STOOD "
            "IN for stays UNVERIFIABLE through this resume (MF-B): it is "
            "never exited, re-stopped or flattened and no reconcile clears "
            "it — see `stand_in_rows` on /status." if drift else ""))
    return {"ok": True, "cleared": prior, "blend_cleared": blend_prior}
