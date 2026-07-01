"""FastAPI application entrypoint.

On startup: create tables, sync the universe from watchlist.yaml (history-safe
upsert), and start the ingestion/scoring scheduler (unless RUN_SCHEDULER=false).
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .config import settings
from .db import engine, init_db
from .models import ScoreSnapshot
from .routers import catalysts, chat, market, scores, social, universe, views
from .scheduler import shutdown_scheduler, start_scheduler
from .universe.manager import sync_from_yaml

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx logs full request URLs at INFO — which include the FMP apikey query param.
# Silence it to WARNING so secrets never land in stdout/host logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        summary = sync_from_yaml(session)
    logger.info("Universe synced on startup: %s", summary)

    # Seed an initial dataset so the dashboard isn't blank on first load.
    # MUST run in a background thread: a synchronous backfill (32 names x network)
    # would block the ASGI startup, so the app never opens its port and the host's
    # health check times out / crash-loops before any data is fetched.
    if settings.backfill_on_startup:
        import threading

        def _startup_backfill() -> None:
            try:
                from .ingestion.runner import run_all
                from .scoring.engine import compute_scores

                with Session(engine) as session:
                    if session.exec(select(ScoreSnapshot).limit(1)).first() is not None:
                        logger.info("DB already seeded -> skipping startup backfill")
                        return
                    logger.info("Empty DB -> background startup backfill begun")
                    run_all(session)
                    compute_scores(session)
                    logger.info("Background startup backfill complete")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Startup backfill failed (non-fatal): %s", exc)

        threading.Thread(target=_startup_backfill, daemon=True, name="startup-backfill").start()
        logger.info("Startup backfill dispatched to background thread")

    if settings.run_scheduler:
        start_scheduler()
        logger.info("Scheduler started")
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=false)")
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Genomics Sector Alpha Tracker",
    description="Local-first analytics that surface forward-looking alpha in the genomics sector.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Optional HTTP Basic auth gate (active only when creds are configured).

    /health is always exempt so platform health checks pass. Constant-time
    comparison avoids leaking credential length via timing.
    """
    user = settings.dashboard_user
    pwd = settings.dashboard_password
    if user and pwd and request.url.path != "/health":
        header = request.headers.get("authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                got_user, _, got_pwd = decoded.partition(":")
                ok = secrets.compare_digest(got_user, user) and secrets.compare_digest(
                    got_pwd, pwd
                )
            except (ValueError, UnicodeDecodeError):
                ok = False
        if not ok:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Genomics Alpha Tracker"'},
            )
    return await call_next(request)

app.include_router(universe.router)
app.include_router(market.router)
app.include_router(catalysts.router)
app.include_router(scores.router)
app.include_router(views.router)
app.include_router(chat.router)
app.include_router(social.router)


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "market_provider": settings.market_provider,
        "scheduler": settings.run_scheduler,
        "optional_keys": {
            "polygon": bool(settings.polygon_api_key),
            "fmp": bool(settings.fmp_api_key),
            "tiingo": bool(settings.tiingo_api_key),
            "x_twitter": bool(settings.x_bearer_token),
            "reddit": bool(settings.reddit_client_id),
            "anthropic_sentiment": bool(settings.anthropic_api_key),
        },
    }


# --- Treasury Canary reverse proxy -------------------------------------------
# Serve the separate Treasury Canary service under this domain at /canary/* so it
# lives at genomics.optic.capital/canary. Sits behind the same login gate above.
# The Canary's SPA is built with base "/canary/" + API base "/canary", so browser
# requests arrive under /canary and we strip that prefix before forwarding.
_CANARY_UPSTREAM = os.environ.get(
    "CANARY_UPSTREAM", "https://treasury-canary.onrender.com").rstrip("/")
_CANARY_HOP_HEADERS = {"content-encoding", "transfer-encoding", "connection", "content-length"}


@app.get("/canary", include_in_schema=False)
def _canary_root():
    return RedirectResponse(url="/canary/")


@app.api_route("/canary/{path:path}", methods=["GET", "POST", "HEAD"], include_in_schema=False)
async def _canary_proxy(path: str, request: Request):
    url = f"{_CANARY_UPSTREAM}/{path}"
    body = await request.body()
    fwd = {k: v for k, v in request.headers.items()
           if k.lower() not in ("host", "authorization", "content-length", "accept-encoding")}
    # Request an uncompressed upstream response so we never forward compressed bytes
    # with the encoding header stripped (which renders as garbage in the browser).
    fwd["accept-encoding"] = "identity"
    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            up = await client.request(request.method, url,
                                      params=dict(request.query_params), content=body, headers=fwd)
    except Exception as exc:  # noqa: BLE001
        return Response(f"Canary upstream unavailable: {exc}", status_code=502)
    headers = {k: v for k, v in up.headers.items() if k.lower() not in _CANARY_HOP_HEADERS}
    return Response(content=up.content, status_code=up.status_code, headers=headers,
                    media_type=up.headers.get("content-type"))


# Single-service deployment: if a built frontend is present, serve it at "/".
# (Mounted AFTER the API routers so /universe, /scores, /views, etc. win.)
if settings.frontend_dist and os.path.isdir(settings.frontend_dist):
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    logger.info("Serving frontend from %s", settings.frontend_dist)
else:
    @app.get("/", tags=["meta"])
    def root():
        return {"name": "Genomics Sector Alpha Tracker", "docs": "/docs", "health": "/health"}
