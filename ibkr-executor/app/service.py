"""IBKR executor service: decision loop + control surface.

Modes (auto-selected):
  OFFLINE : no TWS credentials -> DryAdapter, full logic, zero broker calls
  PAPER   : credentials + TRADING_MODE=paper -> real gateway, paper account
  LIVE    : TRADING_MODE=live AND DRY_RUN=false -> real orders (Nov gate)
DRY_RUN=true with credentials still routes all mutations to the DryAdapter
while using real market reads once the paper-phase adapter lands.
"""
from __future__ import annotations

import logging
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
ADAPTER = None
LAST: dict = {"loop_ok": 0.0, "nino34": None, "mode": "OFFLINE"}


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
                        logger.warning("blend: tracker unreachable; cycle skipped")
                    else:
                        run_cycle(BLEND, ADAPTER, payload, today, alert=send)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("blend cycle error: %s", exc)
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
    return {"status": "ok", "service": "ibkr-executor", "mode": LAST["mode"],
            "loop_age_s": round(time.time() - LAST["loop_ok"], 1)
            if LAST["loop_ok"] else None}


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
        for key in list(BLEND.state.positions):
            pos = BLEND.state.positions[key]
            try:
                if pos.stop_order_ref:
                    ADAPTER.cancel_stock_order(pos.stop_order_ref)
                r = ADAPTER.place_stock_order(pos.symbol, -pos.qty, "MKT")
                BLEND.on_exited(pos.call_id, r.get("fill_price", 0.0),
                                "manual kill")
            except Exception as exc:  # noqa: BLE001
                logger.exception("kill blend close %s failed: %s", key, exc)
        BLEND.halt("KILL")
    send("🔴 ACTION NEEDED (you) — ibkr ladder KILLED: all legs closed, "
         "ladder halted\n→ it stays halted until you hit /resume?token=YOUR_TOKEN")
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
