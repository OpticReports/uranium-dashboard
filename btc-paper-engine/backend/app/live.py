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
from .engine.replay import accrue_cash_yield, book_stats, compute_indicators
from .sources.bitstamp import fetch_4h_bars, kraken_price, last_price
from .store.db import (
    BarRow, BookStateRow, EquitySnapRow, SignalRow, TradeRow,
    log_event, session_scope,
)

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self) -> None:
        self.books_cfg, self.scfg, self.tcfg, self.is_research = load_strategy()
        self.start_capital: float = self.books_cfg[0].start_equity
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

    def _apply_capital(self, capital: float) -> None:
        """Rebuild book configs at a chosen starting capital (percent-based
        sizing makes this a clean linear rescale of every book)."""
        from dataclasses import replace as _replace
        self.start_capital = capital
        self.books_cfg = [_replace(c, start_equity=capital) for c in self.books_cfg]
        for name, b in self.books.items():
            b.cfg = next(c for c in self.books_cfg if c.name == name)

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
            meta = s.get(BookStateRow, "_meta")
            if meta is not None:
                cap = json.loads(meta.state_json).get("capital")
                if cap:
                    self._apply_capital(cap)
        self.refresh_bars()
        with session_scope() as s:
            self.catch_up(s)
            # Seed blend books immediately so S5/S6 show up on the dashboard
            # from first boot rather than waiting for the next 4h bar close.
            if self.bars:
                self._blend_step(self.bars[-1].ts + BAR_SECONDS, s)
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
                accrue_cash_yield(b, settings.cash_apy)
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

    def reset_books(self, start_ts: int, capital: float | None = None) -> dict:
        """Re-baseline ALL books from one common inception: wipe state, replay
        start_ts -> now through the identical engine code path, install the
        resulting books (open positions included), and continue live. The
        fixture provides deep history; DB bars supply the live tail."""
        import csv as _csv
        import os as _os
        from .engine.core import Bar as _Bar
        from .engine.replay import run_replay
        with self._lock:
            fix = _os.path.join(_os.path.dirname(__file__), "..", "tests",
                                "fixtures", "bars_4h_btcusd.csv")
            by_ts = {}
            for r in _csv.DictReader(open(fix)):
                t = int(r["ts_open_unix"])
                by_ts[t] = _Bar(ts=t, open=float(r["open"]), high=float(r["high"]),
                                low=float(r["low"]), close=float(r["close"]),
                                volume=float(r["volume"]))
            with session_scope() as s:
                for row in s.query(BarRow).all():
                    by_ts[row.ts_open] = _Bar(ts=row.ts_open, open=row.open,
                                              high=row.high, low=row.low,
                                              close=row.close, volume=row.volume)
            all_bars = [by_ts[t] for t in sorted(by_ts)]
            now = time.time()
            closed = [b for b in all_bars if b.ts + BAR_SECONDS <= now]
            if capital:
                self._apply_capital(capital)
            res = run_replay(closed, self.books_cfg, self.scfg, self.tcfg,
                             start_ts=start_ts, cash_apy=settings.cash_apy)
            with session_scope() as s:
                s.query(TradeRow).delete()
                s.query(EquitySnapRow).delete()
                s.query(BookStateRow).delete()
                s.merge(BookStateRow(book="_meta",
                                     state_json=json.dumps({"capital": self.start_capital}),
                                     last_processed_bar=0))
                self.books = res.books
                self.bars = all_bars[-max(settings.history_bars, 400):]
                self.last_processed = closed[-1].ts if closed else 0
                self._persisted_trades = {n: 0 for n in self.books}
                self._blend_state = {}
                # seed equity snapshots at each trade exit for the curves
                for name, b in self.books.items():
                    for t in b.trades:
                        s.merge(EquitySnapRow(ts=t.exit_ts, book=name,
                                              equity=t.equity_after, unrealized=0.0,
                                              peak_equity=t.equity_after,
                                              drawdown=0.0))
                self._persist(s, snapshot_ts=self.last_processed + BAR_SECONDS)
                # blends: step through merged ingredient exits from inception
                s3b, s4b = self.books.get("S3"), self.books.get("S4")
                if s3b and s4b:
                    evs = sorted(
                        [(t.exit_ts, "P", t.equity_after / s3b.cfg.start_equity)
                         for t in s3b.trades]
                        + [(t.exit_ts, "T", t.equity_after / s4b.cfg.start_equity)
                           for t in s4b.trades])
                    for bn, (w, lev) in self.BLENDS.items():
                        p3 = p4 = 1.0
                        eq = peak = self.start_capital
                        nw = nl = 0
                        sw = sl = 0.0
                        for ts_, which, ratio in evs:
                            if which == "P":
                                r = (ratio / p3 - 1) * (1 - w)
                                p3 = ratio
                            else:
                                r = (ratio / p4 - 1) * w
                                p4 = ratio
                            step = lev * r
                            eq *= 1 + step
                            peak = max(peak, eq)
                            if step > 0:
                                nw += 1
                                sw += step
                            elif step < 0:
                                nl += 1
                                sl -= step
                            s.merge(EquitySnapRow(ts=ts_, book=bn, equity=eq,
                                                  unrealized=0.0, peak_equity=peak,
                                                  drawdown=eq / peak - 1))
                        # prev marks = ingredients' current closed equity; the
                        # next live _blend_step continues from here
                        self._blend_state[bn] = {"eq": eq, "peak": peak,
                                                 "p3": s3b.equity, "p4": s4b.equity,
                                                 "nw": nw, "nl": nl, "sw": sw, "sl": sl}
                        s.merge(BookStateRow(book=bn,
                                             state_json=json.dumps(self._blend_state[bn]),
                                             last_processed_bar=self.last_processed))
                log_event(s, "INFO", "books_reset",
                          f"inception={start_ts} trades={ {n: len(b.trades) for n, b in self.books.items()} }")
            return {"inception": start_ts,
                    "books": {n: {"equity": round(b.equity, 2), "trades": len(b.trades)}
                              for n, b in self.books.items()}}

    def status(self) -> dict:
        return {
            "degraded": self.degraded, "data_halt": self.data_halt,
            "is_research_config": self.is_research,
            "cash_apy": settings.cash_apy,
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
                name, {"eq": self.start_capital, "peak": self.start_capital,
                       "p3": cur3, "p4": cur4})
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
        px = self.cur_price
        s3b, s4b = self.books.get("S3"), self.books.get("S4")
        evs = []
        if s3b and s4b:
            evs = sorted(
                [(t.exit_ts, "P", t.equity_after / s3b.cfg.start_equity)
                 for t in s3b.trades]
                + [(t.exit_ts, "T", t.equity_after / s4b.cfg.start_equity)
                   for t in s4b.trades])
        for name, (w, lev) in self.BLENDS.items():
            st = self._blend_state.get(name)
            if not st:
                continue
            # STRICT per-trade win rate: every ingredient trade the blend
            # participates in counts once; profitable is profitable regardless
            # of weight (weights scale P&L size, never the win/loss sign).
            p3m = p4m = 1.0
            nw = nl = 0
            sw = sl = 0.0
            for _, which, ratio in evs:
                if which == "P":
                    r = (ratio / p3m - 1) * (1 - w)
                    p3m = ratio
                else:
                    r = (ratio / p4m - 1) * w
                    p4m = ratio
                if r > 0:
                    nw += 1
                    sw += lev * r
                elif r < 0:
                    nl += 1
                    sl -= lev * r
            s3, s4 = self.books.get("S3"), self.books.get("S4")
            u3 = (self._unrealized(s3, px) or 0.0) if s3 else 0.0
            u4 = (self._unrealized(s4, px) or 0.0) if s4 else 0.0
            unreal = None
            if s3 and s4 and (u3 or u4):
                unreal = round(st["eq"] * lev * (
                    (1 - w) * u3 / s3.equity + w * u4 / s4.equity), 2)
            out[name] = {
                "book": name, "synthetic": True, "equity": round(st["eq"], 2),
                "trades": len(self.books["S3"].trades) + len(self.books["S4"].trades),
                "win_rate": round(100 * nw / (nw + nl), 1) if nw + nl else None,
                "profit_factor": round(sw / sl, 2) if sl > 1e-12 else None,
                "expectancy_pct": None,
                "total_return_pct": round(100 * (st["eq"] / self.start_capital - 1), 1),
                "cagr_pct": None,
                "max_dd_pct": round(100 * (st["eq"] / st["peak"] - 1), 1),
                "exit_mix": {}, "fees_usd": None, "halted": False,
                "state": "BLEND", "position": None, "unrealized": unreal,
                "blend_desc": f"{int((1-w)*100)}% S3 + {int(w*100)}% S4 @ {lev}x",
                "open": False,
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
