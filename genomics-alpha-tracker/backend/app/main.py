"""FastAPI application entrypoint.

On startup: create tables, sync the universe from watchlist.yaml (history-safe
upsert), and start the ingestion/scoring scheduler (unless RUN_SCHEDULER=false).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .config import settings
from .db import engine, init_db
from .models import ScoreSnapshot
from .routers import catalysts, market, scores, universe, views
from .scheduler import shutdown_scheduler, start_scheduler
from .universe.manager import sync_from_yaml

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        summary = sync_from_yaml(session)
    logger.info("Universe synced on startup: %s", summary)

    # On ephemeral-disk hosts, seed an initial dataset so the dashboard isn't
    # blank on first load. Best-effort: never block startup on it.
    if settings.backfill_on_startup:
        try:
            from .ingestion.runner import run_all
            from .scoring.engine import compute_scores

            with Session(engine) as session:
                already = session.exec(select(ScoreSnapshot).limit(1)).first()
                if already is None:
                    logger.info("Empty DB -> running startup backfill (best-effort)")
                    run_all(session)
                    compute_scores(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Startup backfill failed (non-fatal): %s", exc)

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

app.include_router(universe.router)
app.include_router(market.router)
app.include_router(catalysts.router)
app.include_router(scores.router)
app.include_router(views.router)


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


# Single-service deployment: if a built frontend is present, serve it at "/".
# (Mounted AFTER the API routers so /universe, /scores, /views, etc. win.)
if settings.frontend_dist and os.path.isdir(settings.frontend_dist):
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    logger.info("Serving frontend from %s", settings.frontend_dist)
else:
    @app.get("/", tags=["meta"])
    def root():
        return {"name": "Genomics Sector Alpha Tracker", "docs": "/docs", "health": "/health"}
