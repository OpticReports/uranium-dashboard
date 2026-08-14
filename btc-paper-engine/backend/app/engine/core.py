"""Signal rules + execution simulator — ONE code path for replay and live.

Semantics decoded from the reference sim (btc_trades_limit_entry_reference.csv)
and spec §1; every rule that was ambiguous in prose is pinned here:

- Bar identity = its OPEN timestamp (UTC). Signals evaluate on CLOSED bars.
- Entry: limit at close(T) placed at signal close; fills during bar T+1 if it
  trades through (long: low < limit; short: high > limit). Unfilled -> cancel.
  entry_ts recorded = the FILL BAR's open timestamp.
- A_e = ATR(14) of the FILL bar (frozen). Stop = E -/+ 2.5*A_e, ACTIVE FROM THE
  BAR AFTER THE FILL BAR (reference log has no bars_held=0), filled exactly at
  stop (4h-bar intrabar semantics — matches the research backtest).
- Signal exit: closed bar's close reclaims SMA50 (long: close > SMA50); the
  fill bar's own close is NOT eligible. Execution at the NEXT bar's open.
- Time stop: >= 60 bars held at a close evaluation -> exit at next bar's open.
- Priority inside a bar: protective stop first, then close-based exits.
- Fees: maker 0 on entry; taker exits charge taker_bps on ENTRY notional
  (decoded from reference ret_pct = favorable-price-ratio - 6 bps exactly).
- Sizing (per book) at fill, using book equity at fill time; exposure capped;
  book equity compounds on dollar P&L (spec §3 accounting).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["L", "S"]

BAR_SECONDS = 4 * 3600


@dataclass(frozen=True)
class Bar:
    ts: int                     # open timestamp, unix UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Ind:
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    atr14: float | None
    vol_sma20: float | None
    hi20: float | None = None    # max high of PRIOR 20 bars (Donchian channel)
    lo20: float | None = None    # min low of PRIOR 20 bars


@dataclass(frozen=True)
class SignalCfg:
    rsi_long: float = 45.0
    rsi_short: float = 55.0
    depth_atr: float = 0.5
    vol_filter: bool = True


@dataclass(frozen=True)
class TradeCfg:
    stop_atr: float = 2.5
    time_stop_bars: int = 60
    taker_fee_bps: float = 6.0
    maker_fee_bps: float = 0.0


@dataclass(frozen=True)
class BookCfg:
    name: str
    sizing: Literal["vol_target", "fixed"]
    strategy: Literal["pullback", "donchian"] = "pullback"
    trail_atr: float = 5.0       # donchian only: chandelier trail multiple
    risk: float = 0.055          # vol_target: equity-risk fraction per trade
    leverage: float = 1.0        # fixed: notional multiple of equity
    long_mult: float = 1.0
    cap: float = 1.0             # hard notional cap, x equity
    start_equity: float = 100_000.0
    dd_halt: float = 0.30


@dataclass
class Position:
    side: Side
    entry_ts: int                # fill bar open ts
    entry_price: float
    qty: float
    notional: float
    stop_price: float
    atr_at_entry: float
    signal_ts: int               # signal bar open ts
    fee_bps: float = 6.0         # round-trip taker bps charged at exit
    trail: float | None = None   # donchian chandelier level (ratchets)


@dataclass
class Pending:
    side: Side
    limit: float
    signal_ts: int
    atr_signal: float


@dataclass
class ClosedTrade:
    book: str
    side: Side
    signal_ts: int
    entry_ts: int
    entry_price: float
    qty: float
    notional: float
    stop_price: float
    atr_at_entry: float
    exit_ts: int
    exit_price: float
    exit_reason: str             # SIGNAL | STOP | TIME
    bars_held: int
    fees_usd: float
    pnl_usd: float
    pnl_pct: float               # on notional
    equity_before: float
    equity_after: float


@dataclass
class Book:
    cfg: BookCfg
    equity: float = 0.0
    peak_equity: float = 0.0
    halted: bool = False
    position: Position | None = None
    pending: Pending | None = None
    trades: list[ClosedTrade] = field(default_factory=list)
    # Marked-to-market view, updated every closed bar (open positions valued
    # at the close). QA: exit-only DD flattered books vs the HOLD benchmark
    # by 1-4pp; /replay/compare uses these for a like-for-like basis. Not
    # persisted — meaningful only within one replay/process lifetime.
    mtm_equity: float = 0.0
    mtm_peak: float = 0.0
    mtm_max_dd: float = 0.0

    def __post_init__(self):
        if self.equity == 0.0:
            self.equity = self.cfg.start_equity
            self.peak_equity = self.cfg.start_equity
        if self.mtm_equity == 0.0:
            self.mtm_equity = self.equity
            self.mtm_peak = self.equity


def eval_signal(bar: Bar, ind: Ind, cfg: SignalCfg) -> Side | None:
    if None in (ind.sma50, ind.sma200, ind.rsi14, ind.atr14, ind.vol_sma20):
        return None
    c = bar.close
    if (c > ind.sma200 and ind.sma50 > ind.sma200 and c < ind.sma50
            and ind.rsi14 < cfg.rsi_long
            and (not cfg.vol_filter or bar.volume > ind.vol_sma20)
            and (ind.sma50 - c) >= cfg.depth_atr * ind.atr14):
        return "L"
    if (c < ind.sma200 and ind.sma50 < ind.sma200 and c > ind.sma50
            and ind.rsi14 > cfg.rsi_short
            and (not cfg.vol_filter or bar.volume > ind.vol_sma20)
            and (c - ind.sma50) >= cfg.depth_atr * ind.atr14):
        return "S"
    return None


def eval_donchian(bar: Bar, ind: Ind) -> Side | None:
    if ind.hi20 is None or ind.lo20 is None:
        return None
    if bar.close > ind.hi20:
        return "L"
    if bar.close < ind.lo20:
        return "S"
    return None


def _size(book: Book, side: Side, entry: float, a_e: float, tcfg: TradeCfg) -> tuple[float, float]:
    """(qty, notional) for a fill at `entry` with entry-bar ATR a_e."""
    cfg = book.cfg
    stop_dist = tcfg.stop_atr * a_e / entry
    if cfg.sizing == "vol_target":
        notional = book.equity * cfg.risk / stop_dist if stop_dist > 0 else 0.0
    else:
        notional = book.equity * cfg.leverage
    if side == "L":
        notional *= cfg.long_mult
    notional = min(notional, cfg.cap * book.equity)
    qty = round(notional / entry, 6)
    return qty, qty * entry


def _close_position(book: Book, pos: Position, exit_ts: int, exit_price: float,
                    reason: str, tcfg: TradeCfg) -> None:
    sgn = 1.0 if pos.side == "L" else -1.0
    fees = pos.notional * pos.fee_bps / 10_000.0
    pnl = pos.qty * (exit_price - pos.entry_price) * sgn - fees
    eq_before = book.equity
    book.equity += pnl
    book.peak_equity = max(book.peak_equity, book.equity)
    book.trades.append(ClosedTrade(
        book=book.cfg.name, side=pos.side, signal_ts=pos.signal_ts,
        entry_ts=pos.entry_ts, entry_price=pos.entry_price, qty=pos.qty,
        notional=pos.notional, stop_price=pos.stop_price,
        atr_at_entry=pos.atr_at_entry, exit_ts=exit_ts, exit_price=exit_price,
        exit_reason=reason, bars_held=(exit_ts - pos.entry_ts) // BAR_SECONDS,
        fees_usd=fees, pnl_usd=pnl,
        pnl_pct=pnl / pos.notional * 100 if pos.notional else 0.0,
        equity_before=eq_before, equity_after=book.equity))
    book.position = None
    dd = book.equity / book.peak_equity - 1
    if dd <= -book.cfg.dd_halt:
        book.halted = True


def _process_donchian(book: Book, bar: Bar, ind: Ind, tcfg: TradeCfg,
                      signal: Side | None) -> None:
    """S4 family: market entry at next open after a 20-bar channel break;
    exit ONLY via a ratcheting chandelier trail (cfg.trail_atr x rolling ATR).
    Round-trip taker fees (both sides) charged at exit on entry notional."""
    if book.pending is not None:
        p = book.pending
        book.pending = None
        if ind.atr14 is not None:
            qty, notional = _size(book, p.side, bar.open, ind.atr14, tcfg)
            if qty > 0:
                book.position = Position(
                    side=p.side, entry_ts=bar.ts, entry_price=bar.open,
                    qty=qty, notional=notional, stop_price=0.0,
                    atr_at_entry=ind.atr14, signal_ts=p.signal_ts,
                    fee_bps=2 * tcfg.taker_fee_bps)
    pos = book.position
    if pos is not None:
        if ind.atr14 is not None:
            lvl = (bar.close - book.cfg.trail_atr * ind.atr14 if pos.side == "L"
                   else bar.close + book.cfg.trail_atr * ind.atr14)
            pos.trail = (lvl if pos.trail is None else
                         (max(pos.trail, lvl) if pos.side == "L" else min(pos.trail, lvl)))
            pos.stop_price = pos.trail
        if pos.trail is not None and bar.ts > pos.entry_ts:
            hit = (bar.low <= pos.trail if pos.side == "L" else bar.high >= pos.trail)
            if hit:
                _close_position(book, pos, bar.ts, pos.trail, "STOP", tcfg)
    if (book.position is None and book.pending is None and not book.halted
            and signal is not None):
        book.pending = Pending(side=signal, limit=-1.0, signal_ts=bar.ts,
                               atr_signal=ind.atr14 or 0.0)


def _mark_to_market(book: Book, close: float) -> None:
    """Value the book at this bar's close, open position included."""
    unreal = 0.0
    pos = book.position
    if pos is not None:
        sgn = 1.0 if pos.side == "L" else -1.0
        unreal = pos.qty * (close - pos.entry_price) * sgn
    book.mtm_equity = book.equity + unreal
    book.mtm_peak = max(book.mtm_peak, book.mtm_equity)
    if book.mtm_peak > 0:
        book.mtm_max_dd = min(book.mtm_max_dd,
                              book.mtm_equity / book.mtm_peak - 1)


def process_closed_bar(book: Book, bar: Bar, ind: Ind,
                       scfg: SignalCfg, tcfg: TradeCfg,
                       signal: Side | None) -> None:
    """Advance one book through one newly-closed bar. `signal` is THIS BOOK'S
    strategy signal evaluated on this bar's close (None if rules not met)."""
    if book.cfg.strategy == "donchian":
        _process_donchian(book, bar, ind, tcfg, signal)
    else:
        _process_pullback(book, bar, ind, scfg, tcfg, signal)
    _mark_to_market(book, bar.close)


def _process_pullback(book: Book, bar: Bar, ind: Ind,
                      scfg: SignalCfg, tcfg: TradeCfg,
                      signal: Side | None) -> None:
    # 1) pending limit entry resolves against this bar
    if book.pending is not None:
        p = book.pending
        filled = (bar.low < p.limit) if p.side == "L" else (bar.high > p.limit)
        book.pending = None
        if filled and ind.atr14 is not None:
            a_e = ind.atr14                       # ATR of the FILL bar
            qty, notional = _size(book, p.side, p.limit, a_e, tcfg)
            if qty > 0:
                stop = (p.limit - tcfg.stop_atr * a_e if p.side == "L"
                        else p.limit + tcfg.stop_atr * a_e)
                book.position = Position(
                    side=p.side, entry_ts=bar.ts, entry_price=p.limit,
                    qty=qty, notional=notional, stop_price=stop,
                    atr_at_entry=a_e, signal_ts=p.signal_ts)
            # Stop is NOT active on the fill bar itself (reference log has no
            # bars_held=0 trades) and the fill bar's close is exit-ineligible.
            return
        # unfilled -> cancelled; we are FLAT at this close, so a fresh signal
        # on this same close may fire (falls through to step 3)

    # 2) manage open position
    pos = book.position
    if pos is not None and bar.ts > pos.entry_ts:
        # 2a. protective stop, intrabar, first priority
        if pos.side == "L" and bar.low <= pos.stop_price:
            _close_position(book, pos, bar.ts, pos.stop_price, "STOP", tcfg)
        elif pos.side == "S" and bar.high >= pos.stop_price:
            _close_position(book, pos, bar.ts, pos.stop_price, "STOP", tcfg)
        else:
            # 2b. close-based exits -> execute at NEXT bar's open; we model
            # that by flagging and letting the caller pass next bar's open.
            bars_held = (bar.ts - pos.entry_ts) // BAR_SECONDS
            want_exit = None
            if ind.sma50 is not None:
                if pos.side == "L" and bar.close > ind.sma50:
                    want_exit = "SIGNAL"
                elif pos.side == "S" and bar.close < ind.sma50:
                    want_exit = "SIGNAL"
            if want_exit is None and bars_held >= tcfg.time_stop_bars:
                want_exit = "TIME"
            if want_exit:
                pos.exit_flag = want_exit  # type: ignore[attr-defined]
            return
    # 3) if flat after exits resolved, place entry on this close
    if book.position is None and book.pending is None and not book.halted \
            and signal is not None and ind.atr14 is not None:
        book.pending = Pending(side=signal, limit=bar.close,
                               signal_ts=bar.ts, atr_signal=ind.atr14)


def resolve_open_exit(book: Book, next_bar: Bar, tcfg: TradeCfg) -> None:
    """If the previous close flagged a SIGNAL/TIME exit, fill it at this bar's
    open (backtest semantics), BEFORE this bar is otherwise processed."""
    pos = book.position
    flag = getattr(pos, "exit_flag", None) if pos is not None else None
    if pos is not None and flag:
        _close_position(book, pos, next_bar.ts, next_bar.open, flag, tcfg)
