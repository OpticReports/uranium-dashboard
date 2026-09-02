"""FastAPI app — Tokenized Microcap Screener. KEYLESS; SCREEN-ONLY.

Separation of powers (CLAUDE.md): this service holds no credentials and has no
execution path. It names a ticker and a window; the trade is placed by a human
or, if it is ever automated, by ibkr-executor. Nothing here ever routes an
order.
"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session, select

from . import leadlag, scan
from . import scheduler as sched
from .config import screener_config, settings
from .db import engine as db_engine
from .db import get_session, init_db
from .models import Candidate, EquityToken, MemeLaunch, StageEvent
from .status_page import render_status_page

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_security = HTTPBasic(auto_error=False)


def require_auth(creds: HTTPBasicCredentials | None = Depends(_security)) -> None:
    """No-op unless DASHBOARD_USER/PASSWORD are both set (sibling convention)."""
    if not (settings.dashboard_user and settings.dashboard_password):
        return
    ok = creds is not None and (
        secrets.compare_digest(creds.username, settings.dashboard_user)
        and secrets.compare_digest(creds.password, settings.dashboard_password))
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="unauthorized",
                            headers={"WWW-Authenticate": "Basic"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.run_scheduler:
        sched.start_scheduler()
    yield
    sched.shutdown_scheduler()


app = FastAPI(
    title="Tokenized Microcap Screener", version="0.1.0",
    description="Keyless screen for memecoins pooled against tokenized equities",
    lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    with Session(db_engine) as s:
        registry_size = len(s.exec(select(EquityToken.id)).all())
        candidates = len(s.exec(select(Candidate.id)).all())
    return {"status": "ok", "registry_tokens": registry_size,
            "candidates": candidates, "jobs": sched.job_status(),
            "market_cap_enrichment": bool(settings.fmp_api_key),
            "alert_webhook": bool(settings.alert_webhook_url)}


@app.get("/candidates", dependencies=[Depends(require_auth)])
def candidates(stage: str | None = None, min_score: float = 0.0,
               limit: int = Query(100, le=500),
               session: Session = Depends(get_session)) -> list[dict]:
    q = select(Candidate).where(Candidate.alert_score >= min_score)
    if stage:
        q = q.where(Candidate.stage == stage.upper())
    rows = session.exec(q.order_by(Candidate.alert_score.desc()).limit(limit)).all()
    return [r.model_dump() for r in rows]


@app.get("/candidates/{ticker}", dependencies=[Depends(require_auth)])
def candidate(ticker: str, session: Session = Depends(get_session)) -> dict:
    row = session.exec(
        select(Candidate).where(Candidate.ticker == ticker.upper())).first()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown ticker")
    launches = session.exec(
        select(MemeLaunch).where(MemeLaunch.ticker == ticker.upper())
        .order_by(MemeLaunch.heat.desc())).all()
    events = session.exec(
        select(StageEvent).where(StageEvent.ticker == ticker.upper())
        .order_by(StageEvent.at)).all()
    return {"candidate": row.model_dump(),
            "launches": [l.model_dump() for l in launches],
            "ladder": [e.model_dump() for e in events]}


@app.get("/registry", dependencies=[Depends(require_auth)])
def registry_rows(limit: int = Query(500, le=2000),
                  session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(
        select(EquityToken).order_by(EquityToken.first_seen_at.desc()).limit(limit)).all()
    return [r.model_dump() for r in rows]


@app.get("/alerts", dependencies=[Depends(require_auth)])
def alerts(limit: int = Query(100, le=500),
           session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(
        select(StageEvent).where(StageEvent.stage.in_(("RAMPING", "CLUSTER")))
        .order_by(StageEvent.at.desc()).limit(limit)).all()
    return [r.model_dump() for r in rows]


@app.get("/leadlag", dependencies=[Depends(require_auth)])
def lead_lag(session: Session = Depends(get_session)) -> dict:
    return leadlag.measure(session)


@app.get("/config", dependencies=[Depends(require_auth)])
def config_dump() -> dict:
    return screener_config()


@app.post("/scan", dependencies=[Depends(require_auth)])
def run_scan(session: Session = Depends(get_session)) -> dict:
    return scan.full_scan(session)


@app.post("/scan/registry", dependencies=[Depends(require_auth)])
def run_registry_scan(session: Session = Depends(get_session)) -> dict:
    out = scan.registry_sweep(session)
    out["alerts"] = scan.rollup(session)
    return out


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def status_page(session: Session = Depends(get_session)) -> str:
    rows = session.exec(
        select(Candidate).order_by(Candidate.alert_score.desc()).limit(60)).all()
    registry_size = len(session.exec(select(EquityToken.id)).all())
    return render_status_page(rows, leadlag.measure(session), registry_size,
                              screener_config())
