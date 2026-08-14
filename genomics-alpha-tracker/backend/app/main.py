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
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .config import settings
from .db import engine, init_db
from .models import ScoreSnapshot
from .routers import (
    calls,
    catalysts,
    chat,
    journal,
    market,
    scores,
    social,
    today,
    tuning,
    universe,
    views,
)
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


# Canonical domain: this hub answers on several custom domains; redirect the
# aliases to CANONICAL_HOST so bookmarks and the relative OpticNav links all
# consolidate on one address. Registered after basic_auth so it runs FIRST
# (Starlette middleware is LIFO) — no login prompt on a non-canonical host.
_CANONICAL_HOST = os.environ.get("CANONICAL_HOST", "research.optic.capital")
_REDIRECT_HOSTS = {h.strip().lower() for h in os.environ.get(
    "REDIRECT_HOSTS", "genomics.optic.capital").split(",") if h.strip()}


@app.middleware("http")
async def canonical_host(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0].lower()
    if host in _REDIRECT_HOSTS and request.url.path != "/health":
        return RedirectResponse(
            url=str(request.url.replace(netloc=_CANONICAL_HOST)), status_code=308)
    return await call_next(request)

app.include_router(universe.router)
app.include_router(market.router)
app.include_router(catalysts.router)
app.include_router(scores.router)
app.include_router(views.router)
app.include_router(chat.router)
app.include_router(social.router)
app.include_router(calls.router)
app.include_router(today.router)
app.include_router(journal.router)
app.include_router(tuning.router)


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
            "llm_backend": ("anthropic" if settings.anthropic_api_key else
                            "openrouter" if settings.openrouter_api_key else None),
        },
        "openrouter_key": _openrouter_key_diag(),
    }


def _openrouter_key_diag() -> dict:
    """Same partial fingerprint OpenRouter shows on its own keys page (first
    12 + last 3 chars) — enough to match a key by eye, never the key itself."""
    from .utils.openrouter import _key
    raw = settings.openrouter_api_key or ""
    clean = _key()
    if not clean:
        return {"present": False}
    return {
        "present": True,
        "raw_length": len(raw),
        "clean_length": len(clean),
        "prefix_ok": clean.startswith("sk-or-"),
        "had_whitespace_or_quotes": raw != clean,
        "fingerprint": f"{clean[:12]}…{clean[-3:]}",
    }


# --- Sibling-service reverse proxies ------------------------------------------
# This service is the GATE HUB for research.optic.capital: sibling Render
# services are exposed under path prefixes here so they all sit behind the one
# login gate above. The prefix is stripped before forwarding, so upstreams
# serve from "/" (SPAs that need absolute asset paths must be built with the
# matching base, as the Canary is with "/canary/").
_HOP_HEADERS = {"content-encoding", "transfer-encoding", "connection", "content-length"}


def _mount_proxy(prefix: str, upstream_env: str, default_upstream: str, label: str) -> None:
    upstream = os.environ.get(upstream_env, default_upstream).rstrip("/")

    @app.get(f"/{prefix}", include_in_schema=False)
    def _root():
        return RedirectResponse(url=f"/{prefix}/")

    @app.api_route(f"/{prefix}/{{path:path}}", methods=["GET", "POST", "HEAD"],
                   include_in_schema=False)
    async def _proxy(path: str, request: Request):
        url = f"{upstream}/{path}"
        body = await request.body()
        fwd = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "authorization", "content-length", "accept-encoding")}
        # Request an uncompressed upstream response so we never forward compressed
        # bytes with the encoding header stripped (renders as garbage otherwise),
        # and so streamed chunks pass through unbuffered.
        fwd["accept-encoding"] = "identity"
        # Stream the upstream response through instead of buffering it: the
        # barbell analyst chat holds requests open for minutes and emits
        # NDJSON progress events; buffering would both time out and destroy
        # the live feedback. read=600s tolerates long LLM turns.
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0),
            follow_redirects=True)
        try:
            up = await client.send(
                client.build_request(request.method, url,
                                     params=dict(request.query_params),
                                     content=body, headers=fwd),
                stream=True)
        except Exception as exc:  # noqa: BLE001
            await client.aclose()
            return Response(f"{label} upstream unavailable: {exc}", status_code=502,
                            media_type="text/plain")
        headers = {k: v for k, v in up.headers.items() if k.lower() not in _HOP_HEADERS}
        # Never let browsers cache the HTML shell: after a redeploy a cached
        # index.html keeps serving the OLD app (hashed .js assets stay cacheable).
        ctype = up.headers.get("content-type", "")
        if ctype.startswith("text/html"):
            headers["cache-control"] = "no-cache"

        async def _relay():
            try:
                async for chunk in up.aiter_bytes():
                    yield chunk
            finally:
                await up.aclose()
                await client.aclose()

        return StreamingResponse(_relay(), status_code=up.status_code,
                                 headers=headers, media_type=ctype or None)


# research.optic.capital/canary — Treasury Market Health Monitor
_mount_proxy("canary", "CANARY_UPSTREAM",
             "https://treasury-canary.onrender.com", "Canary")
# research.optic.capital/portfolio-optimizer — Barbell Lab quant platform
_mount_proxy("portfolio-optimizer", "BARBELL_UPSTREAM",
             "https://barbell-lab.onrender.com", "Barbell Lab")
# research.optic.capital/btc — BTC Pullback Paper Engine
_mount_proxy("btc", "BTC_UPSTREAM",
             "https://btc-paper-engine.onrender.com", "BTC Paper Engine")
_mount_proxy("exit", "EWM_UPSTREAM",
              "https://treasury-canary.onrender.com/ewm", "Exit Window Monitor")

# research.optic.capital/deals — Venture Deal Analyzer ledger dashboard.
# Self-contained static page. CANONICAL copy: venture-deal-analyzer/
# dashboard.html at the repo root; app/deal_analyzer.html is its mirror
# inside this service's Docker context (see that file's header comment).
# Update both in the same commit.
_DEALS_HTML = os.path.join(os.path.dirname(__file__), "deal_analyzer.html")


@app.get("/deals", include_in_schema=False)
def _deals_noslash():
    return RedirectResponse(url="/deals/")


@app.get("/deals/", include_in_schema=False)
def _deals_page():
    with open(_DEALS_HTML, encoding="utf-8") as fh:
        return Response(fh.read(), media_type="text/html",
                        headers={"cache-control": "no-cache"})


# Single-service deployment: if a built frontend is present, serve it under
# /genomics/ (research.optic.capital/genomics), with "/" redirecting there. The
# SPA's API calls stay at the root paths (/universe, /scores, ...), so the
# routers above are unaffected. The frontend must be built with
# VITE_BASE="/genomics/" (see Dockerfile) so its hashed assets resolve.
if settings.frontend_dist and os.path.isdir(settings.frontend_dist):
    @app.get("/", include_in_schema=False)
    def _root_to_genomics():
        return RedirectResponse(url="/genomics/")

    @app.get("/genomics", include_in_schema=False)
    def _genomics_trailing_slash():
        return RedirectResponse(url="/genomics/")

    app.mount("/genomics", StaticFiles(directory=settings.frontend_dist, html=True),
              name="frontend")
    logger.info("Serving frontend at /genomics/ from %s", settings.frontend_dist)
else:
    @app.get("/", tags=["meta"])
    def root():
        return {"name": "Genomics Sector Alpha Tracker", "docs": "/docs", "health": "/health"}
