"""FastAPI app — BTC Pullback Paper Engine. Paper only; no exchange keys."""
from __future__ import annotations

import csv
import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .live import ENGINE, start_background_loop
from .store.db import (
    BarRow, EquitySnapRow, EventRow, SignalRow, TradeRow, init_db, session_scope,
)

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.run_engine:
        start_background_loop()
    yield


app = FastAPI(title="BTC Paper Engine", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list,
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)


def _iso(ts: int | None) -> str | None:
    return (datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts is not None else None)


@app.get("/health")
def health():
    return {"status": "ok", "service": "btc-paper-engine",
            "engine": settings.run_engine}


@app.get("/status")
def status():
    return ENGINE.status()


@app.get("/books")
def books():
    return {n: b for n, b in ENGINE.status()["books"].items()}


@app.get("/books/{book}/trades")
def trades(book: str, limit: int = 100):
    with session_scope() as s:
        rows = (s.query(TradeRow).filter(TradeRow.book == book)
                .order_by(TradeRow.entry_ts.desc()).limit(limit).all())
        return [{**{c.name: getattr(r, c.name) for c in TradeRow.__table__.columns},
                 "entry_iso": _iso(r.entry_ts), "exit_iso": _iso(r.exit_ts)}
                for r in rows]


@app.get("/books/{book}/equity")
def equity(book: str, limit: int = 3000):
    with session_scope() as s:
        rows = (s.query(EquitySnapRow).filter(EquitySnapRow.book == book)
                .order_by(EquitySnapRow.ts.desc()).limit(limit).all())
        return [{"ts": r.ts, "iso": _iso(r.ts), "equity": r.equity,
                 "drawdown": r.drawdown} for r in reversed(rows)]


@app.get("/signals")
def signals(limit: int = 200):
    with session_scope() as s:
        rows = (s.query(SignalRow).order_by(SignalRow.ts_bar.desc())
                .limit(limit).all())
        return [{"ts": r.ts_bar, "iso": _iso(r.ts_bar), "direction": r.direction,
                 "close": r.close, "rsi": r.rsi, "depth_atr": r.depth_atr,
                 "vol_ratio": r.vol_ratio} for r in rows]


@app.get("/bars")
def bars(limit: int = 500):
    with session_scope() as s:
        rows = (s.query(BarRow).order_by(BarRow.ts_open.desc()).limit(limit).all())
        return [{"ts": r.ts_open, "iso": _iso(r.ts_open), "open": r.open,
                 "high": r.high, "low": r.low, "close": r.close,
                 "volume": r.volume} for r in reversed(rows)]


@app.get("/events")
def events(limit: int = 100):
    with session_scope() as s:
        rows = s.query(EventRow).order_by(EventRow.id.desc()).limit(limit).all()
        return [{"ts": _iso(r.ts), "level": r.level, "book": r.book,
                 "event": r.event, "detail": r.detail} for r in rows]


@app.get("/conditions")
def conditions():
    """Live proximity to a setup — the 'conditions met: n/6' strip."""
    from .engine.replay import compute_indicators
    bars_ = ENGINE.bars
    if len(bars_) < 210:
        return {"ready": False}
    inds = compute_indicators(bars_)
    b, d = bars_[-1], inds[-1]     # last bar may still be forming — labelled so
    forming = b.ts + 4 * 3600 > datetime.now(timezone.utc).timestamp()
    def checks(side: str) -> dict[str, bool]:
        if None in (d.sma50, d.sma200, d.rsi14, d.atr14, d.vol_sma20):
            return {}
        if side == "L":
            return {"close>sma200": b.close > d.sma200, "sma50>sma200": d.sma50 > d.sma200,
                    "close<sma50": b.close < d.sma50, "rsi<45": d.rsi14 < 45,
                    "vol>sma20": b.volume > d.vol_sma20,
                    "depth>=0.5atr": (d.sma50 - b.close) >= 0.5 * d.atr14}
        return {"close<sma200": b.close < d.sma200, "sma50<sma200": d.sma50 < d.sma200,
                "close>sma50": b.close > d.sma50, "rsi>55": d.rsi14 > 55,
                "vol>sma20": b.volume > d.vol_sma20,
                "depth>=0.5atr": (b.close - d.sma50) >= 0.5 * d.atr14}
    regime = ("UP" if d.sma50 and d.sma200 and d.sma50 > d.sma200 else
              "DOWN" if d.sma50 and d.sma200 else "?")
    return {"ready": True, "bar_ts": b.ts, "forming": forming, "close": b.close,
            "regime": regime, "rsi": d.rsi14,
            "dist_sma50_atr": ((b.close - d.sma50) / d.atr14
                               if d.sma50 and d.atr14 else None),
            "vol_ratio": (b.volume / d.vol_sma20 if d.vol_sma20 else None),
            "long": checks("L"), "short": checks("S")}


@app.post("/books/{book}/halt")
def halt(book: str):
    b = ENGINE.books.get(book)
    if not b:
        raise HTTPException(404)
    b.halted = True
    return {"book": book, "halted": True}


@app.post("/books/{book}/resume")
def resume(book: str):
    b = ENGINE.books.get(book)
    if not b:
        raise HTTPException(404)
    b.halted = False
    b.peak_equity = b.equity          # manual reset re-anchors the dd baseline
    return {"book": book, "halted": False}


@app.post("/resume-data")
def resume_data():
    ENGINE.data_halt = False
    return {"data_halt": False}


@app.post("/replay")
def replay():
    """Run the §6 acceptance replay on the persisted+fixture bar history."""
    import os
    from .engine.core import Bar
    from .engine.replay import book_stats, research_basis_stats, run_replay
    fix = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures",
                       "bars_4h_btcusd.csv")
    rows = list(csv.DictReader(open(fix)))
    bars_ = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                 high=float(r["high"]), low=float(r["low"]),
                 close=float(r["close"]), volume=float(r["volume"])) for r in rows]
    start = int(datetime(2024, 7, 24, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 7, 24, tzinfo=timezone.utc).timestamp())
    res = run_replay(bars_, ENGINE.books_cfg, ENGINE.scfg, ENGINE.tcfg,
                     start_ts=start, end_ts=end)
    tr = res.books[ENGINE.books_cfg[-1].name].trades
    out = {"dollar_basis": {n: book_stats(b) for n, b in res.books.items()},
           "research_basis": research_basis_stats(tr, ENGINE.tcfg, ENGINE.books_cfg)}
    if not ENGINE.is_research:
        out["warning"] = ("Active strategy config differs from research defaults — "
                          "§6 expectations do not apply to these numbers.")
    return out


@app.get("/export/trades.csv")
def export_trades():
    with session_scope() as s:
        rows = s.query(TradeRow).order_by(TradeRow.entry_ts).all()
        buf = io.StringIO()
        cols = [c.name for c in TradeRow.__table__.columns]
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([getattr(r, c) for c in cols])
        buf.seek(0)
        return StreamingResponse(iter([buf.read()]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          "attachment; filename=trades.csv"})


if settings.frontend_dist:
    import os
    from fastapi.staticfiles import StaticFiles
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True),
                  name="spa")
