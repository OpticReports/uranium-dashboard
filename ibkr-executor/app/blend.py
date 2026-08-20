"""blend3070 manager — the H13 30/70 book's execution brain (venue-agnostic).

Runs the R2-A 30/70 construction validated in replay (genomics-alpha-tracker
docs/BACKTEST_VARIANTS_R2.md + HYPOTHESES.md H11/H13):
  30% sleeve : the tracker's gate-on auto-call fires, 1% of SLEEVE equity
               risked per call, <=10 open, exits by 3.0xATR trailing stop
               (daily GTC cancel/replace) or 90-calendar-day time stop;
               idle sleeve cash parked in BIL.
  70% core   : SPY buy-and-hold.
  Rebalance  : back to 30/70 when the sleeve weight drifts beyond +-5pp.

Separation of powers (CLAUDE.md law): the TRACKER is the keyless decision
brain — it publishes fires, gate state, and per-call R2-A trail levels at
GET {TRACKER_URL}/blend3070/intents. THIS manager owns the book: positions,
sleeve equity, SPY/BIL holdings, and all dollar sizing live here and are
never sent back to the tracker (the poll is a bare GET). The tracker's
login gate is HTTP Basic, so the poll authenticates with the dashboard
credentials TRACKER_USER / TRACKER_PASSWORD (dashboard login only — no
broker credential is read anywhere in this module).

Same state-machine idioms as LadderManager: persisted JSON state, step()
emitting order intents, on_* execution callbacks, deduped event log. The
adapter executes; run_cycle() is the loop body service.py calls.

SIZING REFERENCE (documented decision): shares = floor(risk$ / per-share
risk) where risk$ = risk_frac x sleeve equity and per-share risk =
entry_ref - trail_level, with entry_ref = the FIRE-DAY CLOSE the tracker
published (the R2-A entry convention) and trail_level = the tracker's
day-one trail (entry - 3xATR14 through the fire day). The MOO fill may
differ from entry_ref; the risk unit stays frozen at the reference, exactly
as the replay accounted entries at fire-day closes.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field

import httpx

logger = logging.getLogger(__name__)

CORE = "SPY"
CASH_VEHICLE = "BIL"
TARGET_SLEEVE = 0.30
BAND = 0.05
MAX_OPEN = 10
RISK_FRAC = 0.01
TIME_STOP_DAYS = 90
MIN_ORDER_USD = 50.0        # dust guard: never emit orders smaller than this
STOP_EPS = 1e-6             # stop cancel/replace only on a real level change


@dataclass
class BlendPosition:
    call_id: int
    symbol: str
    qty: int
    entry_ref: float            # fire-day close (sizing reference)
    fill_price: float           # actual MOO fill
    entry_date: str             # ISO
    time_stop: str              # ISO, entry_date + 90 CALENDAR days
    stop_level: float
    stop_order_ref: str | None = None


@dataclass
class BlendState:
    initialized: bool = False
    positions: dict = field(default_factory=dict)   # str(call_id) -> BlendPosition
    entered_ids: list = field(default_factory=list)  # every call_id ever entered
    sleeve_cash: float = 0.0
    bil_qty: int = 0
    spy_qty: int = 0
    core_cash: float = 0.0
    halted: str | None = None   # KILL | None
    events: list = field(default_factory=list)


class Blend3070Manager:
    def __init__(self, cfg, state_path: str):
        self.cfg = cfg
        self.state_path = state_path
        self.state = self._load()

    # ---------- persistence (LadderManager pattern) ----------

    def _load(self) -> BlendState:
        try:
            raw = json.load(open(self.state_path))
            st = BlendState(
                initialized=raw.get("initialized", False),
                entered_ids=raw.get("entered_ids", []),
                sleeve_cash=raw.get("sleeve_cash", 0.0),
                bil_qty=raw.get("bil_qty", 0),
                spy_qty=raw.get("spy_qty", 0),
                core_cash=raw.get("core_cash", 0.0),
                halted=raw.get("halted"),
            )
            st.positions = {k: BlendPosition(**v)
                            for k, v in raw.get("positions", {}).items()}
            st.events = raw.get("events", [])[-300:]
            return st
        except Exception:  # noqa: BLE001
            return BlendState()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        json.dump({"initialized": self.state.initialized,
                   "positions": {k: asdict(v)
                                 for k, v in self.state.positions.items()},
                   "entered_ids": self.state.entered_ids,
                   "sleeve_cash": self.state.sleeve_cash,
                   "bil_qty": self.state.bil_qty,
                   "spy_qty": self.state.spy_qty,
                   "core_cash": self.state.core_cash,
                   "halted": self.state.halted,
                   "events": self.state.events[-300:]},
                  open(self.state_path, "w"), indent=1)

    def _event(self, level: str, msg: str) -> None:
        last = self.state.events[-1] if self.state.events else None
        if last and last.get("msg") == msg:
            return
        self.state.events.append({"ts": int(time.time()), "level": level,
                                  "msg": msg})
        logger.info("[blend] %s", msg)

    # ---------- valuation (executor-side only; never leaves this service) ----

    def sleeve_value(self, prices: dict[str, float]) -> float:
        v = self.state.sleeve_cash + self.state.bil_qty * prices.get(CASH_VEHICLE, 0.0)
        for pos in self.state.positions.values():
            v += pos.qty * prices.get(pos.symbol, pos.entry_ref)
        return v

    def core_value(self, prices: dict[str, float]) -> float:
        return self.state.core_cash + self.state.spy_qty * prices.get(CORE, 0.0)

    def book_value(self, prices: dict[str, float]) -> float:
        return self.sleeve_value(prices) + self.core_value(prices)

    def gross_exposure(self, prices: dict[str, float]) -> float:
        """Everything at risk in the market (holdings, ex-cash) — what the
        BLEND_BUDGET cap binds on."""
        v = self.state.bil_qty * prices.get(CASH_VEHICLE, 0.0)
        v += self.state.spy_qty * prices.get(CORE, 0.0)
        for pos in self.state.positions.values():
            v += pos.qty * prices.get(pos.symbol, pos.entry_ref)
        return v

    # ---------- the decision step ----------

    def step(self, today: str, payload: dict | None,
             prices: dict[str, float]) -> list[dict]:
        """One evaluation against the tracker's intent payload. Returns order
        intents; state changes only via the on_* callbacks (plus first-boot
        seeding and halt bookkeeping, mirroring LadderManager)."""
        intents: list[dict] = []
        st = self.state
        if st.halted or payload is None:
            return intents

        params = payload.get("book_params") or {}
        max_open = min(MAX_OPEN, params.get("max_open", MAX_OPEN))
        risk_frac = params.get("risk_frac", RISK_FRAC)
        band = params.get("band", BAND)
        target = (payload.get("rebalance") or {}).get("target", TARGET_SLEEVE)
        budget = getattr(self.cfg, "blend_budget", 0.0) or 0.0

        if not st.initialized:
            book = getattr(self.cfg, "blend_book_usd", 10_000.0)
            if budget > 0:
                book = min(book, budget)
            st.sleeve_cash = target * book
            st.core_cash = (1.0 - target) * book
            st.initialized = True
            self._event("INFO", f"book initialized: ${book:,.0f} "
                                f"({target:.0%} sleeve / {1 - target:.0%} core)")

        stops_by_id = {s["call_id"]: s for s in payload.get("stops", [])}
        exiting: set[str] = set()
        projected_sleeve_cash = st.sleeve_cash

        # 1) exits the tracker signalled (trail pierced / time stop reached),
        #    reconciled against OUR book: act only on call_ids we hold.
        for ex in payload.get("exits", []):
            key = str(ex["call_id"])
            pos = st.positions.get(key)
            if pos is None or key in exiting:
                continue
            intents.append({"action": "EXIT", "call_id": pos.call_id,
                            "symbol": pos.symbol, "qty": pos.qty,
                            "stop_order_ref": pos.stop_order_ref,
                            "reason": ex.get("reason", "trail")})
            exiting.add(key)
            projected_sleeve_cash += pos.qty * prices.get(pos.symbol, pos.entry_ref)

        # 2) executor-side time-stop belt: our own 90-calendar-day clock —
        #    the backstop the intents contract names (a tracker outage or a
        #    reconciliation gap must never leave a position open past day 90).
        for key, pos in st.positions.items():
            if key in exiting or today <= pos.time_stop:
                continue
            intents.append({"action": "EXIT", "call_id": pos.call_id,
                            "symbol": pos.symbol, "qty": pos.qty,
                            "stop_order_ref": pos.stop_order_ref,
                            "reason": "time_stop"})
            exiting.add(key)
            projected_sleeve_cash += pos.qty * prices.get(pos.symbol, pos.entry_ref)

        # 3) daily GTC stop adjustment (cancel/replace). The trail RATCHETS UP
        #    ONLY — a published level below the working stop is never applied.
        for key, pos in st.positions.items():
            if key in exiting:
                continue
            s = stops_by_id.get(pos.call_id)
            if s is None:
                continue
            if s["trail_level"] > pos.stop_level + STOP_EPS:
                intents.append({"action": "ADJUST_STOP", "call_id": pos.call_id,
                                "symbol": pos.symbol, "qty": pos.qty,
                                "old_ref": pos.stop_order_ref,
                                "stop_level": s["trail_level"],
                                "reason": f"trail ratchet {pos.stop_level:.2f}"
                                          f" -> {s['trail_level']:.2f}"})

        # 4) entries: gate-on candidate fires, sized in dollars HERE.
        gate_on = (payload.get("gate") or {}).get("xbi_above_200dma_prior") is not False
        sleeve_eq = self.sleeve_value(prices)
        open_count = len(st.positions) - len(exiting)
        gross = self.gross_exposure(prices)
        if gate_on:
            for e in payload.get("entries", []):
                key = str(e["call_id"])
                if key in st.positions or e["call_id"] in st.entered_ids:
                    continue
                if open_count >= max_open:
                    self._event("INFO", f"cap {max_open} open: skipping "
                                        f"{e['symbol']} (call {e['call_id']})")
                    continue
                entry_ref = e.get("entry_ref")
                trail = stops_by_id.get(e["call_id"], {}).get("trail_level")
                if not entry_ref or trail is None or entry_ref <= trail:
                    self._event("WARN", f"no sizing reference for {e['symbol']} "
                                        f"(call {e['call_id']}): skipped")
                    continue
                risk_usd = risk_frac * sleeve_eq
                qty = int(risk_usd // (entry_ref - trail))
                avail = projected_sleeve_cash + st.bil_qty * prices.get(CASH_VEHICLE, 0.0)
                qty = min(qty, int(avail // entry_ref)) if entry_ref > 0 else 0
                if qty <= 0:
                    self._event("INFO", f"{e['symbol']} sized to zero: skipped")
                    continue
                cost = qty * entry_ref
                if budget > 0 and gross + cost > budget:
                    self._event("WARN", f"BLEND_BUDGET ${budget:,.0f} would be "
                                        f"exceeded: {e['symbol']} entry blocked")
                    continue
                intents.append({"action": "ENTER", "call_id": e["call_id"],
                                "symbol": e["symbol"], "qty": qty,
                                "entry_ref": entry_ref, "stop_level": trail,
                                "time_stop_days": TIME_STOP_DAYS,
                                "reason": f"gate-on fire {e.get('flag_type')} "
                                          f"({e.get('fire_date')}), risk "
                                          f"${risk_usd:,.0f} @ "
                                          f"{entry_ref - trail:.2f}/sh"})
                open_count += 1
                gross += cost
                projected_sleeve_cash -= cost

        # 5) band rebalance (~1x/year expected): executor-side weights.
        book = self.book_value(prices)
        if book > 0:
            w = self.sleeve_value(prices) / book
            if abs(w - target) > band:
                usd = round(abs(w - target) * book, 2)
                direction = "core_to_sleeve" if w < target else "sleeve_to_core"
                intents.append({"action": "REBALANCE", "direction": direction,
                                "usd": usd,
                                "reason": f"sleeve weight {w:.1%} outside "
                                          f"{target:.0%} +-{band:.0%} band"})
                if direction == "core_to_sleeve":
                    # SPY sale proceeds land in sleeve cash -> swept to BIL.
                    projected_sleeve_cash += usd
                else:
                    # sleeve_to_core spends idle sleeve cash first and
                    # self-funds the remainder from BIL inside the rebalance
                    # execution — never leave a SWEEP to double-sell BIL.
                    projected_sleeve_cash -= min(
                        usd, max(projected_sleeve_cash, 0.0))

        # 6) core: idle core cash is always fully in SPY (buy-and-hold).
        spy_px = prices.get(CORE, 0.0)
        core_cash = st.core_cash + sum(
            i["usd"] for i in intents
            if i["action"] == "REBALANCE" and i["direction"] == "sleeve_to_core")
        if spy_px > 0 and core_cash > max(MIN_ORDER_USD, spy_px):
            intents.append({"action": "CORE_BUY", "symbol": CORE,
                            "qty": int(core_cash // spy_px),
                            "reason": "invest idle core cash"})

        # 7) BIL sweep of idle sleeve cash (buy), or raise cash for pending
        #    entries/rebalance (sell), from the projected cash position.
        bil_px = prices.get(CASH_VEHICLE, 0.0)
        if bil_px > 0:
            if projected_sleeve_cash > max(MIN_ORDER_USD, bil_px):
                intents.append({"action": "SWEEP", "symbol": CASH_VEHICLE,
                                "qty": int(projected_sleeve_cash // bil_px),
                                "reason": "sweep idle sleeve cash to BIL"})
            elif projected_sleeve_cash < -MIN_ORDER_USD and st.bil_qty > 0:
                need = min(st.bil_qty, math.ceil(-projected_sleeve_cash / bil_px))
                intents.append({"action": "SWEEP", "symbol": CASH_VEHICLE,
                                "qty": -need,
                                "reason": "sell BIL to fund sleeve orders"})
        return intents

    # ---------- execution callbacks (run_cycle reports results) ----------

    def on_entered(self, intent: dict, fill_price: float, order_ref: str,
                   today: str) -> None:
        from datetime import date, timedelta

        d = date.fromisoformat(today)
        pos = BlendPosition(
            call_id=intent["call_id"], symbol=intent["symbol"],
            qty=intent["qty"], entry_ref=intent["entry_ref"],
            fill_price=fill_price, entry_date=today,
            time_stop=(d + timedelta(days=intent.get("time_stop_days",
                                                     TIME_STOP_DAYS))).isoformat(),
            stop_level=intent["stop_level"])
        self.state.positions[str(pos.call_id)] = pos
        self.state.entered_ids.append(pos.call_id)
        self.state.sleeve_cash -= pos.qty * fill_price
        self._event("INFO", f"ENTER {pos.symbol} x{pos.qty} @ {fill_price:.2f} "
                            f"(call {pos.call_id}, stop {pos.stop_level:.2f})")
        self.save()

    def on_stop_placed(self, call_id: int, order_ref: str, level: float) -> None:
        pos = self.state.positions.get(str(call_id))
        if pos is not None:
            pos.stop_order_ref = order_ref
            pos.stop_level = level
            self.save()

    def on_exited(self, call_id: int, fill_price: float, reason: str) -> None:
        pos = self.state.positions.pop(str(call_id), None)
        if pos is None:
            return
        pnl = (fill_price - pos.fill_price) * pos.qty
        self.state.sleeve_cash += pos.qty * fill_price
        self._event("INFO", f"EXIT {pos.symbol} x{pos.qty} @ {fill_price:.2f} "
                            f"({reason}) -> P&L ${pnl:+,.0f}")
        self.save()

    def on_core_trade(self, qty_delta: int, price: float) -> None:
        self.state.spy_qty += qty_delta
        self.state.core_cash -= qty_delta * price
        self.save()

    def on_sweep(self, qty_delta: int, price: float) -> None:
        self.state.bil_qty += qty_delta
        self.state.sleeve_cash -= qty_delta * price
        self.save()

    def on_transfer(self, usd: float) -> None:
        """+usd moves core -> sleeve; -usd moves sleeve -> core."""
        self.state.sleeve_cash += usd
        self.state.core_cash -= usd
        self.save()

    # ---------- control ----------

    def halt(self, reason: str = "KILL") -> None:
        self.state.halted = reason
        self._event("RED", f"blend halted ({reason})")
        self.save()

    def resume(self) -> None:
        self.state.halted = None
        self._event("INFO", "blend resumed")
        self.save()

    def status_summary(self, prices: dict[str, float] | None = None) -> dict:
        st = self.state
        out = {
            "enabled": True,
            "halted": st.halted,
            "initialized": st.initialized,
            "positions": {k: asdict(v) for k, v in st.positions.items()},
            "open_count": len(st.positions),
            "sleeve_cash": round(st.sleeve_cash, 2),
            "bil_qty": st.bil_qty,
            "spy_qty": st.spy_qty,
            "core_cash": round(st.core_cash, 2),
            "budget_cap": getattr(self.cfg, "blend_budget", 0.0) or None,
            "events": st.events[-40:],
        }
        if prices:
            out["sleeve_value"] = round(self.sleeve_value(prices), 2)
            out["core_value"] = round(self.core_value(prices), 2)
            book = self.book_value(prices)
            out["book_value"] = round(book, 2)
            out["sleeve_weight"] = round(self.sleeve_value(prices) / book, 4) if book else None
        return out


# ---------- tracker poll + cycle execution ------------------------------------

def fetch_intents(cfg) -> dict | None:
    """GET the tracker's intent set. A bare authenticated GET: no params, no
    body — the tracker never learns positions or account equity. None on any
    failure (a dead tracker blocks NEW actions; resting GTC stops and the
    time-stop belt still protect the book)."""
    base = (getattr(cfg, "tracker_url", "") or "").rstrip("/")
    if not base:
        return None
    auth = None
    if getattr(cfg, "tracker_user", ""):
        auth = (cfg.tracker_user, cfg.tracker_password)
    try:
        r = httpx.get(f"{base}/blend3070/intents", auth=auth, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("blend intents fetch failed: %s", exc)
        return None


def reference_prices(adapter, mgr: Blend3070Manager, payload: dict | None) -> dict:
    """Reference prices for every symbol the cycle can touch, via the
    adapter (DryAdapter returns synthetic quotes offline)."""
    symbols = {CORE, CASH_VEHICLE}
    symbols.update(p.symbol for p in mgr.state.positions.values())
    if payload:
        symbols.update(e["symbol"] for e in payload.get("entries", []) if e.get("symbol"))
    prices: dict[str, float] = {}
    for s in symbols:
        try:
            prices[s] = adapter.spot(s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("spot %s failed: %s", s, exc)
    return prices


def run_cycle(mgr: Blend3070Manager, adapter, payload: dict | None,
              today: str, alert=None) -> list[dict]:
    """One blend cycle: step -> execute intents on the adapter -> callbacks.
    Every action alerts; any single intent failing never blocks the rest."""
    from .alerts import send as _send
    alert = alert or _send

    prices = reference_prices(adapter, mgr, payload)
    intents = mgr.step(today, payload, prices)
    for it in intents:
        try:
            act = it["action"]
            if act == "ENTER":
                r = adapter.place_stock_order(it["symbol"], it["qty"], "MOO",
                                              tif="OPG",
                                              ref_price=it["entry_ref"])
                mgr.on_entered(it, r.get("fill_price", it["entry_ref"]),
                               r["order_ref"], today)
                rs = adapter.place_stock_order(it["symbol"], -it["qty"], "STP",
                                               stop_price=it["stop_level"],
                                               tif="GTC")
                mgr.on_stop_placed(it["call_id"], rs["order_ref"],
                                   it["stop_level"])
                alert(f"🧬 blend ENTER {it['symbol']} x{it['qty']} MOO "
                      f"(stop {it['stop_level']:.2f}): {it['reason']}")
            elif act == "ADJUST_STOP":
                if it.get("old_ref"):
                    adapter.cancel_stock_order(it["old_ref"])
                rs = adapter.place_stock_order(it["symbol"], -it["qty"], "STP",
                                               stop_price=it["stop_level"],
                                               tif="GTC")
                mgr.on_stop_placed(it["call_id"], rs["order_ref"],
                                   it["stop_level"])
                alert(f"🧬 blend STOP {it['symbol']}: {it['reason']}")
            elif act == "EXIT":
                if it.get("stop_order_ref"):
                    adapter.cancel_stock_order(it["stop_order_ref"])
                r = adapter.place_stock_order(it["symbol"], -it["qty"], "MKT",
                                              ref_price=prices.get(it["symbol"]))
                mgr.on_exited(it["call_id"], r.get("fill_price", 0.0),
                              it["reason"])
                alert(f"🧬 blend EXIT {it['symbol']} x{it['qty']} "
                      f"({it['reason']})")
            elif act == "REBALANCE":
                _execute_rebalance(mgr, adapter, it, prices)
                alert(f"🧬 blend REBALANCE {it['direction']} "
                      f"${it['usd']:,.0f}: {it['reason']}")
            elif act == "CORE_BUY":
                r = adapter.place_stock_order(CORE, it["qty"], "MKT",
                                              ref_price=prices.get(CORE))
                mgr.on_core_trade(it["qty"], r.get("fill_price",
                                                   prices.get(CORE, 0.0)))
                alert(f"🧬 blend CORE buy {CORE} x{it['qty']}")
            elif act == "SWEEP":
                r = adapter.place_stock_order(CASH_VEHICLE, it["qty"], "MKT",
                                              ref_price=prices.get(CASH_VEHICLE))
                mgr.on_sweep(it["qty"], r.get("fill_price",
                                              prices.get(CASH_VEHICLE, 0.0)))
                alert(f"🧬 blend SWEEP {CASH_VEHICLE} "
                      f"{'+' if it['qty'] > 0 else ''}{it['qty']}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("blend intent %s failed: %s", it, exc)
            alert(f"🚨 blend intent failed ({it.get('action')} "
                  f"{it.get('symbol')}): {exc}\n→ no action needed from you — "
                  f"forward this to Claude")
    mgr.save()
    return intents


def _execute_rebalance(mgr: Blend3070Manager, adapter, it: dict,
                       prices: dict[str, float]) -> None:
    usd = it["usd"]
    spy_px = prices.get(CORE, 0.0)
    bil_px = prices.get(CASH_VEHICLE, 0.0)
    if it["direction"] == "core_to_sleeve":
        # Sell SPY for ~usd, move the proceeds to the sleeve (BIL sweep
        # picks the cash up next cycle).
        if spy_px <= 0:
            return
        qty = min(mgr.state.spy_qty, int(round(usd / spy_px)))
        if qty <= 0:
            return
        r = adapter.place_stock_order(CORE, -qty, "MKT", ref_price=spy_px)
        fill = r.get("fill_price", spy_px)
        mgr.on_core_trade(-qty, fill)
        mgr.on_transfer(qty * fill)
    else:
        # Raise sleeve cash from BIL, move it to the core (invested into SPY
        # by the CORE_BUY step next cycle).
        if bil_px > 0 and mgr.state.bil_qty > 0:
            need = max(0.0, usd - mgr.state.sleeve_cash)
            qty = min(mgr.state.bil_qty, math.ceil(need / bil_px))
            if qty > 0:
                r = adapter.place_stock_order(CASH_VEHICLE, -qty, "MKT",
                                              ref_price=bil_px)
                mgr.on_sweep(-qty, r.get("fill_price", bil_px))
        moved = min(usd, mgr.state.sleeve_cash)
        if moved > 0:
            mgr.on_transfer(-moved)
