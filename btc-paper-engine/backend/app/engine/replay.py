"""Replay harness — runs the identical engine code path over historical 4h
bars (no wall clock, no network). This is the §6 acceptance instrument AND the
state-rebuild routine used by the live engine on restart.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..indicators import atr, rsi, sma
from .core import (
    Bar, Book, BookCfg, Ind, SignalCfg, TradeCfg,
    eval_signal, process_closed_bar, resolve_open_exit,
)


@dataclass
class ReplayResult:
    books: dict[str, Book]
    signals: list[tuple[int, str]]          # (bar open ts, side)
    n_bars: int


def compute_indicators(bars: list[Bar]) -> list[Ind]:
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    vols = [b.volume for b in bars]
    s50, s200 = sma(closes, 50), sma(closes, 200)
    r14 = rsi(closes, 14)
    a14 = atr(highs, lows, closes, 14)
    v20 = sma(vols, 20)
    return [Ind(sma50=s50[i], sma200=s200[i], rsi14=r14[i], atr14=a14[i],
                vol_sma20=v20[i]) for i in range(len(bars))]


def run_replay(bars: list[Bar], books_cfg: list[BookCfg],
               scfg: SignalCfg, tcfg: TradeCfg,
               start_ts: int | None = None, end_ts: int | None = None,
               warmup_bars: int = 210) -> ReplayResult:
    """Process bars in order. Indicators use FULL history (so the first
    tradeable bar has a correct SMA200); trading is gated to
    [start_ts, end_ts] and to bars past the warmup."""
    inds = compute_indicators(bars)
    books = {c.name: Book(cfg=c) for c in books_cfg}
    signals: list[tuple[int, str]] = []
    n = 0
    for i, bar in enumerate(bars):
        if i < warmup_bars:
            continue
        if start_ts is not None and bar.ts < start_ts:
            continue
        if end_ts is not None and bar.ts > end_ts:
            break
        n += 1
        ind = inds[i]
        # 1) exits flagged at the previous close execute at THIS bar's open
        for book in books.values():
            resolve_open_exit(book, bar, tcfg)
        # 2) shared signal on this close (books act on it only if flat)
        sig = eval_signal(bar, ind, scfg)
        if sig is not None:
            signals.append((bar.ts, sig))
        for book in books.values():
            process_closed_bar(book, bar, ind, scfg, tcfg, sig)
    return ReplayResult(books=books, signals=signals, n_bars=n)


def research_basis_stats(trades, tcfg: TradeCfg, books_cfg: list[BookCfg],
                         from_ts: int | None = None) -> dict[str, dict]:
    """Reproduce the RESEARCH accounting for the §6 acceptance comparison.

    The reference sim compounds price-ratio returns (short ret = entry/exit-1,
    futures-style) with exposure = sized notional / equity, which for every
    book here is equity-independent, so equity = prod(1 + ret_i * expo_i).
    The live book instead uses spec §3 dollar accounting (short pnl =
    qty*(entry-exit)), which differs by ~ret^2 per short. Both are correct;
    this function exists so the acceptance table compares like with like.
    """
    out: dict[str, dict] = {}
    sel = [t for t in trades if from_ts is None or t.entry_ts >= from_ts]
    for cfg in books_cfg:
        eq, peak, mdd = 1.0, 1.0, 0.0
        for t in sel:
            gross = (t.exit_price / t.entry_price - 1 if t.side == "L"
                     else t.entry_price / t.exit_price - 1)
            ret = gross - tcfg.taker_fee_bps / 10_000.0
            stop_dist = tcfg.stop_atr * t.atr_at_entry / t.entry_price
            if cfg.sizing == "vol_target":
                expo = cfg.risk / stop_dist if stop_dist > 0 else 0.0
            else:
                expo = cfg.leverage
            if t.side == "L":
                expo *= cfg.long_mult
            expo = min(expo, cfg.cap)
            eq *= 1 + ret * expo
            peak = max(peak, eq)
            mdd = min(mdd, eq / peak - 1)
        years = ((sel[-1].exit_ts - sel[0].entry_ts) / (365.25 * 86400)) if len(sel) >= 2 else None
        out[cfg.name] = {
            "total_return_pct": round(100 * (eq - 1), 1),
            "cagr_pct": round(100 * (eq ** (1 / years) - 1), 1) if years and years > 0.2 else None,
            "max_dd_pct": round(100 * mdd, 1),
            "n": len(sel),
        }
    return out


def book_stats(book: Book) -> dict:
    ts = book.trades
    n = len(ts)
    wins = [t for t in ts if t.pnl_usd > 0]
    total_ret = book.equity / book.cfg.start_equity - 1
    # trade-close-basis equity curve for max DD (research basis)
    eq, peak, mdd = book.cfg.start_equity, book.cfg.start_equity, 0.0
    curve = []
    for t in ts:
        eq = t.equity_after
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        curve.append((t.exit_ts, eq))
    years = ((ts[-1].exit_ts - ts[0].entry_ts) / (365.25 * 86400)) if n >= 2 else None
    cagr = ((book.equity / book.cfg.start_equity) ** (1 / years) - 1
            if years and years > 0.2 else None)
    gross_w = sum(t.pnl_usd for t in wins)
    gross_l = -sum(t.pnl_usd for t in ts if t.pnl_usd <= 0)
    return {
        "book": book.cfg.name, "equity": round(book.equity, 2),
        "trades": n, "open": book.position is not None,
        "win_rate": round(100 * len(wins) / n, 1) if n else None,
        "profit_factor": round(gross_w / gross_l, 2) if gross_l > 0 else None,
        "expectancy_pct": round(sum(t.pnl_pct for t in ts) / n, 3) if n else None,
        "total_return_pct": round(100 * total_ret, 1),
        "cagr_pct": round(100 * cagr, 1) if cagr is not None else None,
        "max_dd_pct": round(100 * mdd, 1),
        "exit_mix": {r: sum(1 for t in ts if t.exit_reason == r)
                     for r in ("SIGNAL", "STOP", "TIME")},
        "fees_usd": round(sum(t.fees_usd for t in ts), 2),
        "halted": book.halted,
    }
