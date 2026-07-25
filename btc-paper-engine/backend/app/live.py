"""Live paper engine — poll loop, bar finalization, restart-resume.

One Engine instance owns the in-memory bar window and the three books; ALL
trading decisions go through the same engine.core functions the replay harness
uses. Persistence: every processed bar writes new closed trades, signals, book
state (JSON incl. open position/pending/exit_flag) and equity snapshots, so a
restart rebuilds exactly and replays any bars missed while down.

Bar finalization: a 4h bar is processed once wall-clock passes its end
boundary AND it has been fetched from REST; late REST data therefore delays
processing rather than producing a signal on an incomplete bar.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict

from .config import load_strategy, settings
from .engine.core import (
    BAR_SECONDS, Bar, Book, Pending, Position,
    eval_donchian, eval_signal, process_closed_bar, resolve_open_exit,
)
from .engine.replay import book_stats, compute_indicators
from .sources.bitstamp import fetch_4h_bars, kraken_price, last_price
from .store.db import (
    BarRow, BookStateRow, EquitySnapRow, SignalRow, TradeRow,
    log_event, session_scope,
)

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self) -> None:
        self.books_cfg, self.scfg, self.tcfg, self.is_research = load_strategy()
        self.books: dict[str, Book] = {c.name: Book(cfg=c) for c in self.books_cfg}
        self.bars: list[Bar] = []
        self.last_processed: int = 0
        self.last_data_ok: float = 0.0
        self.degraded = False
        self.data_halt = False            # price-sanity halt (manual resume)
        self.cur_price: float | None = None
        self._persisted_trades: dict[str, int] = {c.name: 0 for c in self.books_cfg}
        self._blend_state: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ---------- persistence ----------

    def _serialize_book(self, b: Book) -> str:
        pos = None
        if b.position is not None:
            pos = asdict(b.position)
            pos["exit_flag"] = getattr(b.position, "exit_flag", None)
        return json.dumps({
            "equity": b.equity, "peak": b.peak_equity, "halted": b.halted,
            "position": pos,
            "pending": asdict(b.pending) if b.pending else None,
        })

    def _restore_book(self, b: Book, raw: str) -> None:
        d = json.loads(raw)
        b.equity, b.peak_equity, b.halted = d["equity"], d["peak"], d["halted"]
        if d.get("position"):
            p = dict(d["position"])
            flag = p.pop("exit_flag", None)
            b.position = Position(**p)
            if flag:
                b.position.exit_flag = flag  # type: ignore[attr-defined]
        if d.get("pending"):
            b.pending = Pending(**d["pending"])

    def _persist(self, s, snapshot_ts: int | None = None) -> None:
        for name, b in self.books.items():
            n0 = self._persisted_trades[name]
            for t in b.trades[n0:]:
                s.add(TradeRow(**{k: getattr(t, k) for k in (
                    "book", "side", "signal_ts", "entry_ts", "entry_price", "qty",
                    "notional", "stop_price", "atr_at_entry", "exit_ts", "exit_price",
                    "exit_reason", "bars_held", "fees_usd", "pnl_usd", "pnl_pct",
                    "equity_before", "equity_after")}))
            self._persisted_trades[name] = len(b.trades)
            s.merge(BookStateRow(book=name, state_json=self._serialize_book(b),
                                 last_processed_bar=self.last_processed))
            if snapshot_ts is not None:
                unreal = self._unrealized(b, self.bars[-1].close if self.bars else None)
                eq = b.equity + (unreal or 0.0)
                s.merge(EquitySnapRow(ts=snapshot_ts, book=name, equity=eq,
                                      unrealized=unreal or 0.0, peak_equity=b.peak_equity,
                                      drawdown=eq / b.peak_equity - 1 if b.peak_equity else 0.0))

    @staticmethod
    def _unrealized(b: Book, price: float | None) -> float | None:
        if b.position is None or price is None:
            return None
        sgn = 1.0 if b.position.side == "L" else -1.0
        return b.position.qty * (price - b.position.entry_price) * sgn

    # ---------- boot / catch-up ----------

    def boot(self) -> None:
        with session_scope() as s:
            db_bars = [Bar(ts=r.ts_open, open=r.open, high=r.high, low=r.low,
                           close=r.close, volume=r.volume)
                       for r in s.query(BarRow).order_by(BarRow.ts_open).all()]
            self.bars = db_bars[-settings.history_bars:]
            for name, b in self.books.items():
                row = s.get(BookStateRow, name)
                if row is not None:
                    self._restore_book(b, row.state_json)
                    self.last_processed = max(self.last_processed,
                                              row.last_processed_bar or 0)
                # hydrate closed trades so stats survive restarts
                from .engine.core import ClosedTrade
                for tr in (s.query(TradeRow).filter(TradeRow.book == name)
                           .order_by(TradeRow.entry_ts).all()):
                    b.trades.append(ClosedTrade(**{
                        k: getattr(tr, k) for k in (
                            "book", "side", "signal_ts", "entry_ts", "entry_price",
                            "qty", "notional", "stop_price", "atr_at_entry",
                            "exit_ts", "exit_price", "exit_reason", "bars_held",
                            "fees_usd", "pnl_usd", "pnl_pct", "equity_before",
                            "equity_after")}))
                self._persisted_trades[name] = len(b.trades)
            for bn in self.BLENDS:
                row = s.get(BookStateRow, bn)
                if row is not None:
                    self._blend_state[bn] = json.loads(row.state_json)
        self.refresh_bars()
        with session_scope() as s:
            self.catch_up(s)
            log_event(s, "INFO", "boot",
                      f"bars={len(self.bars)} last_processed={self.last_processed}")

    def refresh_bars(self) -> None:
        """Top up the bar window from REST (persist any new finalized bars)."""
        start = (self.bars[-1].ts - BAR_SECONDS if self.bars
                 else int(time.time()) - settings.history_bars * BAR_SECONDS)
        fetched = fetch_4h_bars(start)
        if not fetched:
            return
        self.last_data_ok = time.time()
        by_ts = {b.ts: b for b in self.bars}
        by_ts.update({b.ts: b for b in fetched})
        self.bars = [by_ts[t] for t in sorted(by_ts)][-max(settings.history_bars, 400):]
        with session_scope() as s:
            now = time.time()
            for b in fetched:
                if b.ts + BAR_SECONDS <= now:
                    s.merge(BarRow(ts_open=b.ts, open=b.open, high=b.high,
                                   low=b.low, close=b.close, volume=b.volume))

    def catch_up(self, s) -> None:
        """Process every fetched bar that is closed and newer than last_processed."""
        now = time.time()
        inds = None
        for i, bar in enumerate(self.bars):
            if bar.ts <= self.last_processed or bar.ts + BAR_SECONDS > now:
                continue
            if i < 1:
                continue
            if inds is None:
                inds = compute_indicators(self.bars)
            ind = inds[i]
            warm = i >= min(settings.warmup_bars, len(self.bars) - 1) or ind.sma200 is not None
            for b in self.books.values():
                resolve_open_exit(b, bar, self.tcfg)
            sigs = ({"pullback": eval_signal(bar, ind, self.scfg),
                     "donchian": eval_donchian(bar, ind)} if warm
                    else {"pullback": None, "donchian": None})
            if self.degraded or self.data_halt:
                sigs = {k: None for k in sigs}  # block NEW entries; exits still run
            sig = sigs["pullback"]
            if sig is not None:
                s.merge(SignalRow(ts_bar=bar.ts, direction=sig, close=bar.close,
                                  rsi=ind.rsi14, depth_atr=(
                                      abs(bar.close - ind.sma50) / ind.atr14
                                      if ind.atr14 else None),
                                  vol_ratio=(bar.volume / ind.vol_sma20
                                             if ind.vol_sma20 else None)))
            for b in self.books.values():
                process_closed_bar(b, bar, ind, self.scfg, self.tcfg,
                                   sigs[b.cfg.strategy])
            self.last_processed = bar.ts
            self._persist(s, snapshot_ts=bar.ts + BAR_SECONDS)
            self._blend_step(bar.ts + BAR_SECONDS, s)

    # ---------- poll ----------

    def poll(self) -> None:
        with self._lock:
            px = last_price()
            if px is not None:
                self.cur_price = px
                self.last_data_ok = time.time()
            stale = time.time() - self.last_data_ok > settings.stale_seconds
            if stale != self.degraded:
                self.degraded = stale
                with session_scope() as s:
                    log_event(s, "WARN" if stale else "INFO",
                              "degraded" if stale else "recovered",
                              f"last_data_ok={self.last_data_ok:.0f}")
            # secondary-source sanity (only when both quotes are live)
            if px is not None and not self.data_halt:
                kp = kraken_price()
                if kp and abs(px - kp) / kp * 100 > settings.price_sanity_pct:
                    self.data_halt = True
                    with session_scope() as s:
                        log_event(s, "RED", "price_sanity_halt",
                                  f"bitstamp={px} kraken={kp}")
            # intrabar protective stops at poll granularity (paper: fill AT stop)
            if px is not None:
                cur_bar_ts = int(time.time()) // BAR_SECONDS * BAR_SECONDS
                with session_scope() as s:
                    for b in self.books.values():
                        pos = b.position
                        if pos is None or getattr(pos, "exit_flag", None):
                            continue
                        hit = (px <= pos.stop_price if pos.side == "L"
                               else px >= pos.stop_price)
                        if hit and cur_bar_ts > pos.entry_ts:
                            from .engine.core import _close_position
                            _close_position(b, pos, cur_bar_ts, pos.stop_price,
                                            "STOP", self.tcfg)
                            log_event(s, "INFO", "stop_fill_live", b.cfg.name)
                    self._persist(s)
            # bar boundary: refresh + process newly closed bars
            if not self.bars or time.time() >= self.bars[-1].ts + BAR_SECONDS:
                self.refresh_bars()
                with session_scope() as s:
                    self.catch_up(s)

    def status(self) -> dict:
        return {
            "degraded": self.degraded, "data_halt": self.data_halt,
            "is_research_config": self.is_research,
            "last_processed_bar": self.last_processed,
            "bars_cached": len(self.bars),
            "price": self.cur_price,
            "books": {**self._blend_status(), **{n: {**book_stats(b),
                          "state": ("HALTED" if b.halted else
                                    b.position.side if b.position else
                                    "PENDING" if b.pending else "FLAT"),
                          "position": (asdict(b.position) if b.position else None),
                          "unrealized": self._unrealized(b, self.cur_price)}
                      for n, b in self.books.items()}},
        }

    # Derived blend books: continuously-rebalanced weighted mix of the 1x
    # pullback book (S3) and the 1x trend book (S4), levered. Weights/leverage
    # from the RESEARCH_S4.md sizing frontier (75/25 @ 1.5x dominates the pure
    # pullback at equal CAGR with half the DD; 2x is the aggressive seat).
    BLENDS = {"S5": (0.25, 1.5), "S6": (0.25, 2.0)}   # (w_trend, leverage)

    def _blend_step(self, snapshot_ts: int, s) -> None:
        """Advance blend equities one snapshot using S3/S4 marked returns."""
        s3, s4 = self.books.get("S3"), self.books.get("S4")
        if not s3 or not s4:
            return
        cur3 = s3.equity + (self._unrealized(s3, self.bars[-1].close if self.bars else None) or 0.0)
        cur4 = s4.equity + (self._unrealized(s4, self.bars[-1].close if self.bars else None) or 0.0)
        for name, (w, lev) in self.BLENDS.items():
            st = self._blend_state.setdefault(
                name, {"eq": 100_000.0, "peak": 100_000.0, "p3": cur3, "p4": cur4})
            r3 = cur3 / st["p3"] - 1 if st["p3"] else 0.0
            r4 = cur4 / st["p4"] - 1 if st["p4"] else 0.0
            st["eq"] *= 1 + lev * ((1 - w) * r3 + w * r4)
            st["p3"], st["p4"] = cur3, cur4
            st["peak"] = max(st["peak"], st["eq"])
            s.merge(BookStateRow(book=name, state_json=json.dumps(st),
                                 last_processed_bar=self.last_processed))
            s.merge(EquitySnapRow(ts=snapshot_ts, book=name, equity=st["eq"],
                                  unrealized=0.0, peak_equity=st["peak"],
                                  drawdown=st["eq"] / st["peak"] - 1))

    def _blend_status(self) -> dict:
        out = {}
        for name, (w, lev) in self.BLENDS.items():
            st = self._blend_state.get(name)
            if not st:
                continue
            out[name] = {
                "book": name, "synthetic": True, "equity": round(st["eq"], 2),
                "trades": len(self.books["S3"].trades) + len(self.books["S4"].trades),
                "win_rate": None, "profit_factor": None, "expectancy_pct": None,
                "total_return_pct": round(100 * (st["eq"] / 100_000.0 - 1), 1),
                "cagr_pct": None,
                "max_dd_pct": round(100 * (st["eq"] / st["peak"] - 1), 1),
                "exit_mix": {}, "fees_usd": None, "halted": False,
                "state": "BLEND", "position": None, "unrealized": None, "open": False,
            }
        return out


ENGINE = Engine()


def start_background_loop() -> None:
    def _loop():
        try:
            ENGINE.boot()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Engine boot failed: %s", exc)
        while True:
            try:
                ENGINE.poll()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Engine poll failed: %s", exc)
            time.sleep(settings.poll_seconds)

    threading.Thread(target=_loop, daemon=True).start()
