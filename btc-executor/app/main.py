"""Executor service: background mirror loop + status/control API.

Control surface:
  GET  /health   - liveness
  GET  /status   - full executor state (mode, ledger, events, last target)
  POST /kill     - cancel everything, flatten, halt until /resume
  POST /resume   - clear a halt (manual operator action)
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .feed import EngineFeed
from .mirror import Executor

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

FEED = EngineFeed(settings.engine_url, settings.exec_token)
LAST: dict = {"target": None, "target_ts": 0, "loop_ok": 0}
EXEC: Executor | None = None


def _build_executor() -> Executor:
    inner = None
    if settings.cb_api_key_name and settings.cb_api_private_key:
        try:
            from .cb import CoinbaseVenue
            inner = CoinbaseVenue(settings)
            cands = inner.list_perp_candidates()
            logger.info("BTC futures products visible to this key: %s", cands)
        except Exception as exc:  # noqa: BLE001
            logger.error("coinbase venue init failed: %s", exc)
            inner = None
    if settings.dry_run or inner is None:
        from .cb import DryRunVenue
        venue = DryRunVenue(inner)
        logger.warning("DRY RUN mode: no orders will be sent (inner=%s)",
                       type(inner).__name__ if inner else None)
    else:
        venue = inner
    return Executor(venue, settings)


def _loop() -> None:
    global EXEC
    EXEC = _build_executor()
    while True:
        try:
            target = FEED.get_target()
            if target is not None:
                LAST["target"] = target
                LAST["target_ts"] = time.time()
                EXEC.step(target)
            LAST["loop_ok"] = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("executor loop error: %s", exc)
        time.sleep(settings.poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_loop, daemon=True).start()
    yield


app = FastAPI(title="S5 Executor", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "btc-executor",
            "dry_run": settings.dry_run,
            "loop_age_s": round(time.time() - LAST["loop_ok"], 1)
            if LAST["loop_ok"] else None}


@app.get("/status")
def status():
    if EXEC is None:
        return {"ready": False}
    st = EXEC.state
    venue = EXEC.venue
    dry_log = getattr(venue, "log", None)
    out = {"ready": True, "dry_run": settings.dry_run,
           "product": settings.cb_product_id,
           "kelly_m": settings.kelly_m,
           "halted": st.halted,
           "day_start_equity": st.day_start_equity,
           "high_water": st.high_water,
           "legs": {n: vars(l) for n, l in st.legs.items()},
           "events": st.events[-50:],
           "last_target": LAST["target"],
           "last_target_age_s": round(time.time() - LAST["target_ts"], 1)
           if LAST["target_ts"] else None}
    try:
        out["equity"] = venue.equity()
        out["venue_position_btc"] = venue.position()
    except Exception as exc:  # noqa: BLE001
        out["venue_error"] = str(exc)
    if dry_log is not None:
        out["dry_run_intents"] = dry_log[-50:]
    return out


@app.post("/kill")
def kill():
    if EXEC is None:
        return {"ok": False}
    EXEC.halt("KILL", "manual kill switch")
    return {"ok": True, "halted": EXEC.state.halted}


@app.post("/resume")
def resume():
    if EXEC is None:
        return {"ok": False}
    EXEC.resume()
    return {"ok": True}
