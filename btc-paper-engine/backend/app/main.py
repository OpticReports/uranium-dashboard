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


@app.post("/books/reset")
def books_reset(window: str = "2y", start: str | None = None,
                capital: float | None = None):
    """Re-baseline ALL books from one common inception (2y|1y|6m|3m|1m or
    custom start=YYYY-MM-DD), replaying history through the live code path;
    live trading continues from now. Destructive: wipes current book state."""
    spans = {"2y": 730, "1y": 365, "6m": 182, "3m": 91, "1m": 30}
    if start:
        t0 = int(datetime.strptime(start, "%Y-%m-%d")
                 .replace(tzinfo=timezone.utc).timestamp())
    else:
        t0 = int(datetime.now(timezone.utc).timestamp()) - spans.get(window, 730) * 86400
    if capital is not None:
        capital = max(1_000.0, min(100_000_000.0, capital))
    return ENGINE.reset_books(t0, capital=capital)


@app.post("/resume-data")
def resume_data():
    ENGINE.data_halt = False
    return {"data_halt": False}


def _risk_stats(steps: list[float], years: float | None, total_ret: float,
                max_dd: float) -> dict:
    """Sharpe/Sortino annualized from per-step returns (steps-per-year pace),
    rf=0; MAR = CAGR/|maxDD|. Trade-step basis — consistent across real books
    and blends (both step at trade exits)."""
    out = {"sharpe": None, "sortino": None, "mar": None, "cagr_pct": None}
    n = len(steps)
    if n < 8 or not years or years <= 0.15:
        return out
    per_year = n / years
    mean = sum(steps) / n
    var = sum((x - mean) ** 2 for x in steps) / n
    dvar = sum(min(x, 0.0) ** 2 for x in steps) / n
    cagr = (1 + total_ret) ** (1 / years) - 1
    out["cagr_pct"] = round(100 * cagr, 1)
    if var > 0:
        out["sharpe"] = round(mean / var ** 0.5 * per_year ** 0.5, 2)
    if dvar > 0:
        out["sortino"] = round(mean / dvar ** 0.5 * per_year ** 0.5, 2)
    if max_dd < -0.005:
        out["mar"] = round(cagr / abs(max_dd), 2)
    return out


def _blend_stats(name: str, b3, b4, w_trend: float, lev: float) -> dict:
    """Continuously-rebalanced levered blend of the 1x books, stepped through
    time-ordered trade exits (approximates the frontier's daily rebalance)."""
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity) for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity) for t in b4.trades])
    p3 = p4 = 1.0
    eq = peak = 1.0
    mdd = 0.0
    steps = []
    day_pnl: dict = {}
    for ts_, which, ratio in evs:
        if which == "P":
            r = (ratio / p3 - 1) * (1 - w_trend)
            p3 = ratio
        else:
            r = (ratio / p4 - 1) * w_trend
            p4 = ratio
        steps.append(lev * r)
        day_pnl[ts_ // 86400] = day_pnl.get(ts_ // 86400, 0.0) + lev * r
        eq *= 1 + lev * r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    # win rate/PF on DAILY basis: share of active days positive (per-event
    # counting double-weights the trend sleeve's many small losers)
    wins = [v for v in day_pnl.values() if v > 0]
    losses = [-v for v in day_pnl.values() if v < 0]
    years = ((evs[-1][0] - evs[0][0]) / (365.25 * 86400)) if len(evs) >= 2 else None
    return {"book": name, "synthetic": True, "trades": len(evs),
            "total_return_pct": round(100 * (eq - 1), 1),
            "max_dd_pct": round(100 * mdd, 1),
            "win_rate": (round(100 * len(wins) / (len(wins) + len(losses)), 1)
                         if wins or losses else None),
            "profit_factor": (round(sum(wins) / sum(losses), 2)
                              if losses and sum(losses) > 0 else None),
            "exit_mix": {}, "equity": round(100000 * eq, 2),
            **_risk_stats(steps, years, eq - 1, mdd)}


@app.get("/replay/compare")
def replay_compare(window: str = "2y", start: str | None = None,
                   end: str | None = None):
    """All books replayed over one window: 2y|1y|6m|3m|1m or custom start/end
    (YYYY-MM-DD). Bars = repo fixture merged with DB-accumulated live bars."""
    import os
    from .engine.core import Bar
    from .engine.replay import book_stats, run_replay
    fix = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures",
                       "bars_4h_btcusd.csv")
    by_ts = {}
    for r in csv.DictReader(open(fix)):
        by_ts[int(r["ts_open_unix"])] = Bar(
            ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
    with session_scope() as s:
        for r in s.query(BarRow).all():
            by_ts[r.ts_open] = Bar(ts=r.ts_open, open=r.open, high=r.high,
                                   low=r.low, close=r.close, volume=r.volume)
    bars_ = [by_ts[t] for t in sorted(by_ts)]
    now = bars_[-1].ts
    spans = {"2y": 730, "1y": 365, "6m": 182, "3m": 91, "1m": 30}
    if start:
        t0 = int(datetime.strptime(start, "%Y-%m-%d")
                 .replace(tzinfo=timezone.utc).timestamp())
    else:
        t0 = now - spans.get(window, 730) * 86400
    t1 = (int(datetime.strptime(end, "%Y-%m-%d")
              .replace(tzinfo=timezone.utc).timestamp()) if end else now)
    res = run_replay(bars_, ENGINE.books_cfg, ENGINE.scfg, ENGINE.tcfg,
                     start_ts=t0, end_ts=t1)
    out = {}
    for n, b in res.books.items():
        st = book_stats(b)
        steps = [(t.equity_after / t.equity_before - 1) for t in b.trades
                 if t.equity_before]
        yrs = ((b.trades[-1].exit_ts - b.trades[0].entry_ts) / (365.25 * 86400)
               if len(b.trades) >= 2 else None)
        st.update(_risk_stats(steps, yrs, b.equity / b.cfg.start_equity - 1,
                              st["max_dd_pct"] / 100.0))
        out[n] = st
    if "S3" in res.books and "S4" in res.books:
        out["S5"] = _blend_stats("S5", res.books["S3"], res.books["S4"], 0.25, 1.5)
        out["S6"] = _blend_stats("S6", res.books["S3"], res.books["S4"], 0.25, 2.0)
    i0 = next((i for i, b in enumerate(bars_) if b.ts >= t0), 0)
    bh = bars_[-1].close / bars_[i0].close - 1 if bars_ else 0
    return {"window": {"from": _iso(t0), "to": _iso(t1)},
            "books": out, "buy_hold_pct": round(100 * bh, 1)}


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
