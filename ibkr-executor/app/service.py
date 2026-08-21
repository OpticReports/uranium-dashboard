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
from .nino import nino34_weekly

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

MGR: LadderManager | None = None
BLEND = None                       # Blend3070Manager, ONLY when BLEND_ENABLED
BLEND_LOCK = threading.Lock()      # /kill (API thread) vs run_cycle (loop
                                   # thread) share per-position stock orders
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
    # blend3070 is opt-in: BLEND_ENABLED=false (the default) leaves the
    # service byte-for-byte as before — no manager, no polling, no /status
    # section, no state file.
    if settings.blend_enabled:
        from .blend import Blend3070Manager
        BLEND = Blend3070Manager(settings, settings.blend_state_path)
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


def _loop():
    _build()
    send(f"🌊 ibkr-executor up — mode {LAST['mode']}, "
         f"ladder legs {[k for k in MGR.state.legs]}")
    while True:
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            nino = nino34_weekly()
            LAST["nino34"] = nino
            marks = {}
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
                        send(f"⚡ ibkr ladder OPEN {it['leg']}: {it['reason']} "
                             f"(premium ${r['premium']:,.0f}, mode {LAST['mode']})")
                    elif it["action"] == "CLOSE":
                        leg = MGR.state.legs[it["leg"]]
                        r = ADAPTER.close_spread(leg.order_ref)
                        MGR.on_closed(it["leg"], r["value"], it["reason"], today)
                        send(f"⚡ ibkr ladder CLOSE {it['leg']}: {it['reason']} "
                             f"-> ${r['value']:,.0f}")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("intent %s failed: %s", it, exc)
                    send(f"🚨 ibkr intent failed ({it['action']} {it['leg']}): {exc}\n"
                         f"→ no action needed from you — forward this to Claude "
                         f"(if it repeats, gateway/credentials may need you)")
            MGR.save()
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
            LAST["loop_ok"] = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("loop error: %s", exc)
        time.sleep(settings.poll_seconds)


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_loop, daemon=True).start()
    yield


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
        from .blend import reference_prices
        try:
            prices = reference_prices(ADAPTER, BLEND, None)
        except Exception:  # noqa: BLE001
            prices = None
        body["blend"] = BLEND.status_summary(prices)
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
    from .blend import reference_prices
    prices: dict = {}
    if ADAPTER is not None:
        try:
            prices = reference_prices(ADAPTER, BLEND, None)
        except Exception:  # noqa: BLE001
            prices = {}
    today = datetime.now(timezone.utc).date().isoformat()
    body = BLEND.feed(prices, today)
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
    if BLEND is not None:
        from .blend import _ingest_fills, reconcile as blend_reconcile
        today = datetime.now(timezone.utc).date().isoformat()
        with BLEND_LOCK:
            # RECONCILE FIRST (counter-agent N14): a stop that already
            # filled at the venue must be booked BEFORE flattening — the
            # kill then closes only positions still actually held, never
            # selling a position twice. If venue truth is unavailable the
            # flatten is refused (fail closed): blind MKT sells against an
            # unreconciled book are exactly the double-sell this guards.
            blend_reconcile_ok = True
            try:
                blend_reconcile(BLEND, ADAPTER, today, send)
            except Exception as exc:  # noqa: BLE001
                blend_reconcile_ok = False
                logger.exception("kill: blend reconcile failed: %s", exc)
                send(f"🚨🚨 blend kill: reconcile FAILED ({exc}) — venue "
                     f"state unverifiable, positions NOT auto-flattened; "
                     f"book halted, flatten manually")
            if blend_reconcile_ok:
                for key in list(BLEND.state.positions):
                    pos = BLEND.state.positions.get(key)
                    if pos is None:
                        continue
                    if pos.stop_order_ref:
                        stop_ref = pos.stop_order_ref
                        cancel_raised = False
                        try:
                            cancelled = ADAPTER.cancel_stock_order(stop_ref)
                        except Exception as exc:  # noqa: BLE001
                            # Pinned adapter contract: a RAISING cancel means
                            # the stop FILLED. This must never fall through
                            # to the MKT sell (final-review K-d).
                            logger.exception("kill: stop cancel %s raised "
                                             "(stop likely FILLED): %s",
                                             key, exc)
                            cancel_raised = True
                            cancelled = False
                        if not cancelled:
                            # Ambiguous "already gone"/failed cancel: the
                            # stop may have JUST filled — verify before
                            # selling (idempotent with the stop fill).
                            verify_ok = True
                            try:
                                _ingest_fills(BLEND, ADAPTER, send)
                            except Exception as exc:  # noqa: BLE001
                                verify_ok = False
                                logger.exception("kill: fill verify failed: "
                                                 "%s", exc)
                            if key not in BLEND.state.positions:
                                continue     # settled by its stop fill
                            if cancel_raised or not verify_ok:
                                # FAIL CLOSED (K-d): the stop signalled
                                # FILLED and/or venue truth is unverifiable
                                # — a MKT sell here risks the double-sell
                                # this whole path exists to prevent. Park
                                # it loudly; reconcile settles it.
                                BLEND.record_orphan_stop(
                                    stop_ref, {"symbol": pos.symbol,
                                               "qty": -pos.qty,
                                               "call_id": pos.call_id})
                                send(f"🚨🚨 blend kill: {pos.symbol} NOT "
                                     f"flattened — stop cancel "
                                     f"{'raised (likely filled)' if cancel_raised else 'unverifiable'}; "
                                     f"position parked for reconcile, "
                                     f"verify manually")
                                continue
                            # Verified still held with a possibly-resting
                            # stop: track it so a later fill alerts RED and
                            # the cancel is retried every reconcile pass.
                            BLEND.record_orphan_stop(
                                stop_ref, {"symbol": pos.symbol,
                                           "qty": -pos.qty,
                                           "call_id": pos.call_id})
                    try:
                        r = ADAPTER.place_stock_order(
                            pos.symbol, -pos.qty, "MKT",
                            client_order_id=f"blend-{pos.call_id}-kill")
                        fill = r.get("fill_price")
                        if fill is None:
                            # Repo law: never book at a silent 0.0.
                            BLEND.on_exit_unreconciled(
                                pos.call_id, "manual kill: venue ack without "
                                             "a fill price")
                            send(f"🚨 blend kill close {pos.symbol} "
                                 f"x{pos.qty} UNRECONCILED: no fill price — "
                                 f"proceeds NOT booked, manual "
                                 f"reconciliation needed")
                        else:
                            BLEND.on_exited(pos.call_id, fill, "manual kill")
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("kill blend close %s failed: %s",
                                         key, exc)
            BLEND.halt("KILL")
    blend_note = ""
    if BLEND is not None:
        blend_note = (" + blend book closed & halted" if blend_reconcile_ok
                      else " + blend HALTED but NOT flattened (reconcile "
                           "failed — manual action needed)")
    send(f"🔴 ACTION NEEDED (you) — ibkr ladder KILLED: all legs closed, "
         f"ladder halted{blend_note}\n→ it stays halted until you hit "
         f"/resume?token=YOUR_TOKEN")
    return {"ok": True, "halted": "KILL"}


@app.api_route("/resume", methods=["GET", "POST"])
def resume(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ok": False}
    MGR.state.halted = None
    MGR.save()
    if BLEND is not None:
        BLEND.resume()
    send("ibkr ladder resumed")
    return {"ok": True}
