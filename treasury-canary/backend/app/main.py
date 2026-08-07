"""FastAPI app — Treasury Canary. Serves the API and (in the single-service image)
the built React SPA. Lifespan: init DB, optional startup backfill (background),
and the refresh scheduler.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .sources.fred import fred_key_error
from .store.db import init_db, session_scope

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
# httpx logs full request URLs at INFO — which include the FMP apikey query
# param. Silence to WARNING so secrets never land in stdout/host logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _background_backfill() -> None:
    try:
        from .jobs.refresh import run_backfill
        with session_scope() as s:
            summary = run_backfill(s)
        logger.info("Startup backfill complete: %s", summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Startup backfill failed (non-fatal): %s", exc)


def _start_scheduler(app: FastAPI) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    sched = BackgroundScheduler(timezone="UTC")

    def _job():
        try:
            from .jobs.refresh import run_refresh
            with session_scope() as s:
                logger.info("Scheduled refresh: %s", run_refresh(s))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scheduled refresh failed: %s", exc)

    from datetime import datetime, timedelta, timezone
    sched.add_job(_job, IntervalTrigger(minutes=settings.refresh_interval_minutes),
                  next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
                  id="refresh", max_instances=1, coalesce=True)
    sched.start()
    app.state.scheduler = sched
    logger.info("Scheduler started (every %d min)", settings.refresh_interval_minutes)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.backfill_on_startup:
        threading.Thread(target=_background_backfill, daemon=True).start()
    if settings.run_scheduler:
        _start_scheduler(app)
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=false)")
    from .telegram_chat import register_webhook
    threading.Thread(target=register_webhook, daemon=True).start()
    yield


app = FastAPI(title="Treasury Canary", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"],
    allow_headers=["*"], allow_credentials=True,
)

from .api import (  # noqa: E402
    routes_composite, routes_cycle, routes_events, routes_flows, routes_labor, routes_margin,
    routes_margin_fast, routes_rate_ensemble, routes_rates, routes_shock_sim,
    routes_metrics, routes_news, routes_pins, routes_severity, routes_statregime,
    routes_track,
)

app.include_router(routes_metrics.router)
app.include_router(routes_composite.router)
app.include_router(routes_cycle.router)
app.include_router(routes_events.router)
app.include_router(routes_news.router)
app.include_router(routes_labor.router)
app.include_router(routes_margin.router)
app.include_router(routes_margin_fast.router)
app.include_router(routes_rates.router)
app.include_router(routes_rate_ensemble.router)
app.include_router(routes_shock_sim.router)
from .ewm.api import router as ewm_router  # noqa: E402
app.include_router(ewm_router)
app.include_router(routes_flows.router)
app.include_router(routes_pins.router)
app.include_router(routes_track.router)
app.include_router(routes_severity.router)
app.include_router(routes_statregime.router)


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Inbound Telegram messages -> canary analyst replies. Authenticity via
    the secret token Telegram echoes back; non-owner chats are ignored."""
    from .telegram_chat import handle_update, webhook_secret
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != webhook_secret():
        raise HTTPException(status_code=403, detail="bad webhook secret")
    update = await request.json()
    threading.Thread(target=handle_update, args=(update,), daemon=True).start()
    return {"ok": True}


_TEST_ALERT_TS = {"t": 0.0}


@app.get("/alerts/test")
def alerts_test():
    """Browser-friendly Telegram wiring check. Fixed message + 60s rate limit
    (worst-case abuse on this open endpoint = one canned ping a minute)."""
    import os
    import time as _t

    from .alerts import send
    if _t.time() - _TEST_ALERT_TS["t"] < 60:
        return {"rate_limited": True, "retry_in_s": 60}
    configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                      and os.environ.get("TELEGRAM_CHAT_ID"))
    if configured:
        _TEST_ALERT_TS["t"] = _t.time()
        send("✅ test: treasury-canary → Telegram wiring works")
    return {"telegram_configured": configured, "sent": configured,
            "hint": None if configured else
            "set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars"}


@app.get("/health")
def health():
    return {
        "status": "ok", "service": "treasury-canary",
        "fred_key_present": bool(settings.fred_api_key),
        "fred_key_error": fred_key_error(),
        "scheduler": bool(settings.run_scheduler),
        "display_tz": settings.display_tz,
        "storage": _storage_status(),
    }


def _storage_status() -> dict:
    """Is the DB directory a real mounted disk (persists across deploys) or the
    container's ephemeral filesystem? A mount has a different st_dev than /."""
    import os
    url = settings.database_url
    if not url.startswith("sqlite"):
        return {"backend": "external-db", "persistent": True}
    db_path = url.replace("sqlite:///", "")
    db_dir = os.path.dirname(os.path.abspath(db_path)) or "/"
    try:
        mounted = os.stat(db_dir).st_dev != os.stat("/").st_dev
        writable = os.access(db_dir, os.W_OK)
        db_exists = os.path.exists(db_path)
        size_kb = round(os.path.getsize(db_path) / 1024) if db_exists else 0
    except OSError:
        return {"backend": "sqlite", "persistent": False, "error": "stat failed"}
    return {
        "backend": "sqlite", "dir": db_dir, "mounted_disk": mounted,
        "writable": writable, "db_exists": db_exists, "db_size_kb": size_kb,
        "persistent": mounted,
        "note": ("DB directory is a mounted disk — history survives redeploys."
                 if mounted else
                 "DB directory is on the container's EPHEMERAL filesystem — "
                 "history resets on every deploy. Attach a Render disk at this path."),
    }


@app.post("/refresh")
def manual_refresh():
    from .jobs.refresh import run_refresh
    with session_scope() as s:
        return run_refresh(s)


@app.post("/backfill")
def manual_backfill():
    """Rebuild metric HISTORY from source archives (z-scores/percentiles need
    it). Previously backfill only ran at startup — a quiet boot-time failure
    (or an ephemeral-disk wipe on redeploy) left the service healthy but the
    dashboard empty, with no way to recover short of another deploy. Runs
    synchronously; can take a couple of minutes."""
    from .jobs.refresh import run_backfill
    with session_scope() as s:
        return run_backfill(s)


# --- Single-service SPA serving (set FRONTEND_DIST in the deploy image) --------
if settings.frontend_dist:
    import os
    from fastapi.staticfiles import StaticFiles
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="spa")
