"""carry-executor: executes the ETH funding-carry sleeve the paper engine's
funding monitor decides. Holds a Hyperliquid AGENT key (cannot withdraw).
DRY_RUN defaults ON. Endpoints:
  GET  /health        liveness
  GET  /pulse         public summary (no balances beyond leg sizes)
  GET  /status        full state (EXEC_TOKEN or EXEC_READ_TOKEN)
  POST /halt, /resume EXEC_TOKEN only
"""
from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import FastAPI, Header, HTTPException

from . import alerts
from .carry import CarryExecutor
from .config import settings
from .feed import btc_executor_ready, get_carry_target

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
BUILD = os.environ.get("RENDER_GIT_COMMIT", "dev")[:7]

EXEC: CarryExecutor | None = None
app = FastAPI(title="carry-executor", version="0.1.0")


def _auth(token: str | None, read_ok: bool = False) -> None:
    ok = {settings.exec_token} | ({settings.exec_read_token} if read_ok else set())
    ok.discard("")
    if not ok:
        raise HTTPException(status_code=403, detail="no token configured")
    if token not in ok:
        raise HTTPException(status_code=401, detail="bad token")


def _loop() -> None:
    while True:
        try:
            EXEC.step(get_carry_target(settings.engine_url,
                                       settings.engine_read_token))
        except Exception as exc:  # noqa: BLE001
            logger.exception("carry pass failed: %s", exc)
        time.sleep(settings.poll_seconds)


@app.on_event("startup")
def _boot() -> None:
    global EXEC
    if os.environ.get("CARRY_NO_LOOP"):
        return
    from .venue import HLCarryVenue
    EXEC = CarryExecutor(HLCarryVenue(settings), settings, settings.state_path,
                         preflight_fn=lambda: btc_executor_ready(settings.btc_executor_url))
    alerts.send(f"carry-executor {BUILD} booted: dry_run={settings.dry_run} "
                f"enabled={settings.carry_enabled} notional=${settings.carry_notional_usd:,.0f}")
    threading.Thread(target=_loop, daemon=True).start()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/pulse")
def pulse():
    if EXEC is None:
        return {"ready": False, "build": BUILD}
    return {"ready": True, "build": BUILD, **EXEC.pulse()}


@app.get("/status")
def status(x_exec_token: str | None = Header(default=None)):
    _auth(x_exec_token, read_ok=True)
    if EXEC is None:
        raise HTTPException(status_code=503, detail="not booted")
    from dataclasses import asdict
    return {"build": BUILD, "dry_run": settings.dry_run,
            "notional_usd": settings.carry_notional_usd,
            "state": asdict(EXEC.state)}


@app.post("/halt")
def halt(reason: str = "MANUAL", x_exec_token: str | None = Header(default=None)):
    _auth(x_exec_token)
    if EXEC is None:
        raise HTTPException(status_code=503, detail="not booted")
    EXEC.halt(reason)
    return {"halted": EXEC.state.halted}


@app.post("/resume")
def resume(x_exec_token: str | None = Header(default=None)):
    _auth(x_exec_token)
    if EXEC is None:
        raise HTTPException(status_code=503, detail="not booted")
    EXEC.resume()
    return {"halted": EXEC.state.halted}
