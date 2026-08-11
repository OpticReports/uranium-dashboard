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

from fastapi import FastAPI, HTTPException, Query, Header

from .config import settings
from .feed import EngineFeed
from .mirror import Executor


def _auth(x_exec_token: str | None, token_q: str | None) -> None:
    """Control/status endpoints share the EXEC_TOKEN secret. Header for
    tools, ?token= for a browser. No token configured -> open (dev only)."""
    if settings.exec_token and x_exec_token != settings.exec_token \
            and token_q != settings.exec_token:
        raise HTTPException(status_code=401, detail="bad exec token")

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

FEED = EngineFeed(settings.engine_url, settings.exec_token)
LAST: dict = {"target": None, "target_ts": 0, "loop_ok": 0}
EXEC: Executor | None = None


def _build_executor() -> Executor:
    import os
    inner = None
    LAST["venue_init_error"] = None
    LAST["venue_products"] = None
    if not (settings.cb_api_key_name and settings.cb_api_private_key):
        LAST["venue_init_error"] = "no CB_API_KEY_NAME / CB_API_PRIVATE_KEY set"
    else:
        try:
            from .cb import CoinbaseVenue
            inner = CoinbaseVenue(settings)
            LAST["venue_products"] = inner.list_perp_candidates()
            logger.info("BTC futures products visible to this key: %s",
                        LAST["venue_products"])
        except Exception as exc:  # noqa: BLE001
            LAST["venue_init_error"] = f"{type(exc).__name__}: {exc}"
            logger.error("coinbase venue init failed: %s", exc)
            inner = None
    if not settings.dry_run and inner is None:
        # LIVE mode must never silently demote to a shadow book: the old
        # fall-through ran DryRunVenue over a real account - synthetic $10k
        # equity, continuous fills, and NOBODY maintaining real positions or
        # stops, while /health stayed green (counter-agent find 2026-08-11,
        # same phenotype as the DRY_RUN blueprint incident). Alert and raise;
        # _loop retries with backoff so a transient Coinbase outage self-heals.
        from .alerts import send
        send("🔴 ACTION NEEDED (you) — executor venue_init_failed: LIVE mode "
             f"cannot connect to Coinbase ({LAST['venue_init_error']}). "
             "No orders are being managed; any open positions/stops are "
             "untouched on the venue. Retrying automatically - if this "
             "repeats, check Coinbase status and the API key in Render.")
        raise RuntimeError(f"live venue init failed: "
                           f"{LAST['venue_init_error']}")
    if settings.dry_run:
        from .cb import DryRunVenue
        venue = DryRunVenue(inner, persist_path=os.path.join(
            os.path.dirname(settings.state_path) or ".", "dryrun_book.json"))
        logger.warning("DRY RUN mode: no orders will be sent (inner=%s)",
                       type(inner).__name__ if inner else None)
    else:
        venue = inner
    LAST["venue_inner"] = type(inner).__name__ if inner else None
    LAST["_inner"] = inner
    LAST["venue_products_ts"] = time.time()
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


@app.get("/pulse")
def pulse():
    """Public minimal heartbeat for automated monitoring: state flags only —
    no equity, no position sizes, no order details."""
    if EXEC is None:
        return {"ready": False}
    st = EXEC.state
    now = time.time()
    red_24h = sum(1 for e in st.events
                  if e.get("level") == "RED" and now - e.get("ts", 0) < 86_400)
    return {"ready": True, "dry_run": settings.dry_run,
            "halted": st.halted, "red_events_24h": red_24h,
            "last_target_age_s": round(now - LAST["target_ts"], 1)
            if LAST["target_ts"] else None,
            "legs": {n: {"in_position": l.qty != 0.0,
                         "entry_open": l.entry_cloid is not None,
                         "stop_placed": l.stop_cloid is not None}
                     for n, l in st.legs.items()}}


@app.get("/status")
def status(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if EXEC is None:
        return {"ready": False}
    inner = LAST.get("_inner")
    if inner and time.time() - (LAST.get("venue_products_ts") or 0) > 600:
        # refresh discovery so newly-enabled products (e.g. after the
        # account's derivatives onboarding) show up without a restart
        try:
            LAST["venue_products"] = inner.list_perp_candidates()
        except Exception as exc:  # noqa: BLE001
            logger.warning("product re-discovery failed: %s", exc)
        LAST["venue_products_ts"] = time.time()
    st = EXEC.state
    venue = EXEC.venue
    dry_log = getattr(venue, "log", None)
    out = {"ready": True, "dry_run": settings.dry_run,
           "venue_inner": LAST.get("venue_inner"),
           "venue_init_error": LAST.get("venue_init_error"),
           "venue_products": LAST.get("venue_products"),
           "product": settings.cb_product_id,
           "kelly_m": settings.kelly_m,
           "sizing_config": {
               "sizing_base_usd": settings.sizing_base_usd or "account equity",
               "kelly_m": settings.kelly_m,
               "max_notional_usd": settings.max_notional_usd,
               "max_account_lev": settings.max_account_lev,
               "daily_loss_halt_pct": settings.daily_loss_halt_pct,
               "dd_halt_pct": settings.dd_halt_pct},
           "halted": st.halted,
           "day_start_equity": st.day_start_equity,
           "high_water": st.high_water,
           "legs": {n: vars(l) for n, l in st.legs.items()},
           "marks": st.marks[-30:],
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


@app.get("/test-alert")
def test_alert(x_exec_token: str | None = Header(default=None),
               token: str | None = Query(default=None)):
    """Browser-friendly Telegram wiring check (token-gated)."""
    _auth(x_exec_token, token)
    import os
    from .alerts import send
    configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                      and os.environ.get("TELEGRAM_CHAT_ID"))
    if configured:
        send("✅ test: btc-executor → Telegram wiring works")
    return {"telegram_configured": configured,
            "sent": configured,
            "hint": None if configured else
            "set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars"}


@app.api_route("/kill", methods=["GET", "POST"])
def kill(x_exec_token: str | None = Header(default=None),
         token: str | None = Query(default=None)):
    """GET allowed so the kill switch works from any browser (token-gated)."""
    _auth(x_exec_token, token)
    if EXEC is None:
        return {"ok": False}
    EXEC.halt("KILL", "manual kill switch")
    return {"ok": True, "halted": EXEC.state.halted}


@app.api_route("/resume", methods=["GET", "POST"])
def resume(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if EXEC is None:
        return {"ok": False}
    EXEC.resume()
    return {"ok": True, "halted": EXEC.state.halted}
