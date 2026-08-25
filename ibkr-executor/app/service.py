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

import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query

from .alerts import send
from .outages import OutageLog
from .config import settings
from .ib_adapter import DryAdapter
from .manager import LadderManager
from .nino import nino34_weekly

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
BLEND_LOCK = threading.Lock()      # serializes blend state writes: /kill's
                                   # request_flatten (API thread) vs
                                   # run_cycle (loop thread)
LOOP_WAKE = threading.Event()      # /kill pokes the loop so a queued blend
                                   # flatten runs within seconds, not a
                                   # full poll interval (R2)
ADAPTER = None
LAST: dict = {"loop_ok": 0.0, "nino34": None, "mode": "OFFLINE"}
# Last blend cycle outcome (feed's last_cycle + /health blend_loop): a
# silently failing blend loop must be visible from the outside.
BLEND_CYCLE: dict = {"date": None, "ok": None, "error": None,
                     "error_ts": None}
# Persisted gateway-outage ledger (built with the live adapter only).
OUTAGES = None


def _gateway_restarts(limit: int = 20) -> dict:
    """Restart records written by start.sh's supervisor. A gateway that keeps
    dying is a different problem from IBKR being unreachable, and the two used
    to be indistinguishable."""
    path = getattr(settings, "gateway_restart_log", "")
    out: list[dict] = []
    try:
        # seek to the tail: /health is probed every few seconds and used to
        # slurp the entire unrotated file (counter-agent measured 7.5 MB per
        # call on a one-year log)
        WINDOW = 256 * 1024
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - WINDOW))
            blob = fh.read().decode("utf-8", "replace")
        lines = blob.splitlines()
        if size > WINDOW:
            lines = lines[1:]      # only THEN is the first line partial
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(rec, dict):
                out.append(rec)
    except Exception:  # noqa: BLE001
        pass
    day = time.time() - 86400
    # count over EVERYTHING in the tail, then truncate for display: applying
    # the limit first made last_24h saturate at exactly the storm it exists
    # to reveal
    last_24h = sum(1 for r in out if _num_ts(r) >= day)
    return {"recent_shown": min(len(out), limit),
            "last_24h": last_24h,
            # the breaker deliberately recreates a dead-gateway steady state
            # (stops hammering IBKR logins); it must be NAMED, not buried in
            # the last record's reason field (counter-agent 2026-08-24 F3)
            "circuit_open": bool(out) and out[-1].get("reason") == "circuit_open",
            "last": out[-1] if out else None}


def _num_ts(rec: dict) -> float:
    try:
        return float(rec.get("ts") or 0)
    except (TypeError, ValueError):
        return 0.0


def _auth(hdr: str | None, q: str | None) -> None:
    if settings.exec_token and hdr != settings.exec_token and q != settings.exec_token:
        raise HTTPException(status_code=401, detail="bad exec token")


def _build():
    global MGR, ADAPTER, BLEND, OUTAGES
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
        # the gateway + supervisor run in DRY too (creds exist) - without a
        # ledger the /health gateway block was dark in exactly the rehearsal
        # mode that precedes live (counter-agent 2026-08-24 F6-ii). The
        # DryAdapter never calls the hooks, so this records restarts only.
        global OUTAGES
        OUTAGES = OutageLog(settings.outage_log_path)
        return
    from .ib_adapter import IBAdapter
    OUTAGES = OutageLog(settings.outage_log_path)
    if OUTAGES.history and OUTAGES.history[-1].get("ended_by") == "process_restart":
        # the previous process died mid-outage: it did NOT self-heal, and
        # that is precisely the case supervision is meant to eliminate
        logger.warning("previous gateway outage ended by process restart, "
                       "not by reconnect: %s", OUTAGES.history[-1])
    ADAPTER = IBAdapter(settings, outage_log=OUTAGES)
    LAST["mode"] = settings.trading_mode.upper()


def _loop():
    global LOOP_WAKE
    # Fresh wake event per loop thread: a superseded loop from an earlier
    # lifespan (tests spawn several; daemon threads never die) keeps
    # waiting on its OLD event, so /kill only ever wakes the CURRENT loop.
    LOOP_WAKE = threading.Event()
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
         + (f"ladder legs {[k for k in MGR.state.legs]}"
            if settings.ladder_enabled else "ladder DISABLED (LADDER_ENABLED "
            "unset; blend unaffected)"))
    while True:
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            nino = nino34_weekly()
            LAST["nino34"] = nino
            marks = {}
            # x12: the ladder block mutates and persists MGR — /kill and
            # /resume do the same from API threads. Serialize them exactly
            # as BLEND_LOCK serializes the blend (alerts are sent outside
            # the lock so a slow Telegram call never holds it).
            ladder_alerts: list[str] = []
            # ladder gate below: when disabled, no marks, no step(), no
            # intents - nothing can open or close. State untouched; /kill
            # still works on any previously-open leg (MGR stays built).
            with MGR_LOCK:
              if settings.ladder_enabled:
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
                MGR.save()
            for msg in ladder_alerts:
                send(msg)
            if BLEND is not None:
                try:
                    from .blend import fetch_intents, run_cycle
                    payload = fetch_intents(settings)
                    if payload is None:
                        # Tracker outage: the cycle STILL runs — reconcile
                        # (stop-fill ingestion, orphan cancel retries,
                        # STOP_MISSING re-placement) and the local 90-day
                        # belt are unconditional; only tracker-dependent
                        # decisions are skipped (counter-agent N13).
                        logger.warning("blend: tracker unreachable; "
                                       "reconcile-only cycle (no new "
                                       "decisions)")
                    with BLEND_LOCK:
                        run_cycle(BLEND, ADAPTER, payload, today, alert=send)
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
            LAST["loop_ok"] = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("loop error: %s", exc)
        LOOP_WAKE.wait(settings.poll_seconds)   # /kill sets it to skip the
        LOOP_WAKE.clear()                       # wait (queued flatten)


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_loop, daemon=True).start()
    yield


app = FastAPI(title="IBKR Executor", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    # Gateway reliability, deliberately NOT part of the health verdict:
    # tying it to `status` would make Render restart the whole container -
    # executor included, possibly mid-order - on every routine gateway blip,
    # including its mandatory daily restart. Supervision restarts the gateway
    # process alone; this block only reports.
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
    if OUTAGES is not None:
        # Guarded: healthCheckPath is /health, so a raise here 500s the probe
        # and Render restarts the WHOLE container - executor included,
        # possibly mid-order. That is the exact outcome the comment above
        # says this block avoids, reached by another route (counter-agent
        # 2026-08-24, CRITICAL). Reporting must never fail the verdict.
        try:
            summ = OUTAGES.summary() or {}
            body["gateway"] = {
                "down_since": summ.get("currently_down_since"),
                "outages_30d": summ.get("outages"),
                "self_healed_30d": summ.get("self_healed"),
                "needed_a_restart_30d": summ.get("needed_a_restart"),
                "restarts_24h": (_gr := _gateway_restarts()).get("last_24h"),
                "circuit_open": _gr.get("circuit_open")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("gateway health block failed (ignored): %s", exc)
            body["gateway"] = {"error": "unavailable"}
    return body


@app.get("/status")
def status(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ready": False}
    body = {"ready": True, "mode": LAST["mode"], "dry_run": settings.dry_run,
            "nino34_weekly": LAST["nino34"],
            "ladder_enabled": settings.ladder_enabled,
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
    # /status is the operator's incident endpoint - it was the one place
    # blind to gateway state (counter-agent 2026-08-24)
    body.update(_gateway_report())
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
    body.update(_gateway_report())
    return body


def _gateway_report() -> dict:
    """Gateway reliability for operator endpoints. Never raises."""
    if OUTAGES is None:
        return {}
    try:
        return {"gateway_outages": OUTAGES.summary(),
                "gateway_restarts": _gateway_restarts()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("gateway report failed (ignored): %s", exc)
        return {"gateway_outages": {"error": "unavailable"}}


@app.api_route("/kill", methods=["GET", "POST"])
def kill(x_exec_token: str | None = Header(default=None),
         token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ok": False}
    blend_note = ""
    # The BLEND halt runs FIRST: it is the cheapest and most urgent action
    # here (a journal write under BLEND_LOCK), and putting the ladder's
    # adapter round-trips ahead of it would let a slow spread close delay
    # halting the book (x12 added MGR_LOCK below — never let it gate this).
    if BLEND is not None:
        # R2 (two-stage kill): this handler runs on a FastAPI worker
        # thread, but ib_async binds its event loop to the thread that owns
        # the connection — the blend loop thread. An API-thread flatten
        # pumps a FRESH loop against the shared transport: every wait times
        # out, healthy stops get mis-parked as "likely filled", and
        # cross-thread writes risk session corruption. So /kill only
        # JOURNALS the flatten request (persisted — survives a restart) and
        # halts the book immediately; the loop thread executes the flatten
        # on its next iteration (woken right away below) with
        # reconcile-first semantics (N14) and alerts what actually closed
        # vs parked — the summary here claims only what is true NOW.
        today = datetime.now(timezone.utc).date().isoformat()
        with BLEND_LOCK:
            BLEND.request_flatten(today)
        LOOP_WAKE.set()                 # flatten runs within seconds
        loop_age = (time.time() - LAST["loop_ok"]) if LAST["loop_ok"] else None
        loop_warn = ""
        if loop_age is None or loop_age > 2 * settings.poll_seconds:
            loop_warn = (" ⚠️ the execution loop looks DOWN (see /health) "
                         "— the flatten will NOT run until it recovers; "
                         "flatten manually if urgent")
        blend_note = (" + blend HALTED, flatten QUEUED for the execution "
                      "loop (it owns the venue connection); a completion "
                      "alert will state what closed vs parked" + loop_warn)
    # x12: mutating legs/halted from this API thread must not interleave
    # with the loop thread's own ladder step + save (they raced with no
    # lock at all). MGR_LOCK is taken only AFTER the blend section above
    # released BLEND_LOCK — the two locks are never held together.
    with MGR_LOCK:
        for key, leg in MGR.state.legs.items():
            if leg.status == "OPEN" and leg.order_ref:
                try:
                    r = ADAPTER.close_spread(leg.order_ref)
                    MGR.on_closed(key, r["value"], "manual kill",
                                  datetime.now(timezone.utc).date().isoformat())
                except Exception as exc:  # noqa: BLE001
                    logger.exception("kill close %s failed: %s", key, exc)
        MGR.state.halted = "KILL"
        MGR.save()
    send(f"🔴 ACTION NEEDED (you) — ibkr ladder KILLED: all legs closed, "
         f"ladder halted{blend_note}\n→ it stays halted until you hit "
         f"/resume?token=YOUR_TOKEN")
    return {"ok": True, "halted": "KILL",
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
        MGR.save()
    blend_prior = None
    if BLEND is not None:
        # N3: /resume must not race the loop thread's cycle (a resume
        # interleaved with execute_flatten un-halts a book that is being
        # sold and lets the same cycle place fresh entries). BLEND_LOCK
        # serializes it behind any in-flight cycle, flatten included.
        with BLEND_LOCK:
            blend_prior = BLEND.state.halted
            BLEND.resume()
    drift = "SCHEMA_DRIFT" in (prior, blend_prior)
    send("ibkr ladder resumed"
         + (f" (cleared halt: {prior})" if prior else " (was not halted)")
         + (f"; blend book resumed (cleared halt: {blend_prior})"
            if blend_prior else "")
         + ("\n→ SCHEMA_DRIFT was a data-integrity halt, not a kill: those "
            "rows came from a build this one does not fully understand. "
            "Every field this build knows was kept and nothing live was "
            "re-opened — confirm the venue matches the book before trusting "
            "the next cycle." if drift else ""))
    return {"ok": True, "cleared": prior, "blend_cleared": blend_prior}
