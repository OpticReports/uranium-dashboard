"""Venue-agnostic execution mirror for the S5 blend.

The paper engine remains the single source of trading decisions; this module
reads its /exec/target desired state and reconciles a real venue to it, leg by
leg. It never invents a trade: every order maps to an engine-declared pending
entry, protective stop, or exit.

Leg model (mirrors engine semantics):
  pullback (S3, weight 1-w): limit entry at signal close, good for ONE bar,
    maker-flagged; fixed ATR stop placed on fill; signal/time exits appear as
    the engine position vanishing -> market close.
  trend (S4, weight w): market entry at the bar open after a channel break
    (engine pending -> we market immediately); chandelier trail -> venue stop,
    replaced when the engine's trail ratchets.

Safety: hard notional/leverage caps on every new order, daily-loss and
drawdown halts (flatten + block until manual resume), kill switch, engine
staleness blocks NEW entries only (protective exits always run), and a net
position drift check between our ledger and the venue.

All venue mutations flow through the Venue protocol; DRY_RUN wraps it with a
logger that simulates fills, so the full state machine runs against the real
account read-side without sending an order.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

BAR_SECONDS = 14_400
LEGS = ("pullback", "trend")


class Venue(Protocol):
    def equity(self) -> float: ...
    def position(self) -> float: ...          # signed base qty (BTC)
    def mid(self) -> float: ...
    def order_status(self, cloid: str) -> dict | None: ...
    def place_limit(self, side: str, qty: float, px: float, cloid: str,
                    post_only: bool = True) -> None: ...
    def place_stop(self, side: str, qty: float, trigger_px: float,
                   cloid: str) -> None: ...
    def place_market(self, side: str, qty: float, cloid: str) -> None: ...
    def cancel(self, cloid: str) -> None: ...
    def cancel_all(self) -> None: ...


@dataclass
class LegLedger:
    qty: float = 0.0                      # signed BTC we hold for this leg
    entry_cloid: str | None = None
    entry_side: str | None = None
    entry_qty: float = 0.0                # unsigned qty the entry order asked
    stop_cloid: str | None = None
    stop_px: float | None = None
    signal_ts: int | None = None


@dataclass
class ExecState:
    legs: dict = field(default_factory=lambda: {n: LegLedger() for n in LEGS})
    halted: str | None = None             # None | DAILY_LOSS | DRAWDOWN | KILL
    day_key: str = ""
    day_start_equity: float = 0.0
    high_water: float = 0.0
    events: list = field(default_factory=list)
    # one mark per UTC day: {d, equity, position_btc} — the raw series for
    # live-vs-paper tracking-error and funding-cost decomposition
    marks: list = field(default_factory=list)
    # per-order execution prices vs the engine's reference price — the raw
    # slippage dataset (previously never captured, so the ramp's slippage
    # gate was unfalsifiable)
    fills: list = field(default_factory=list)
    last_dry_run: bool | None = None      # detects silent mode flips


def _side_sign(side: str) -> float:
    return 1.0 if side == "L" else -1.0


def _order_side(side: str) -> str:
    return "BUY" if side == "L" else "SELL"


def _close_side(qty: float) -> str:
    return "SELL" if qty > 0 else "BUY"


class Executor:
    HALT_CONFIRM_POLLS = 3   # breach must persist this many polls (~1 min)
                             # so one bad balance read can't flatten the book

    def __init__(self, venue: Venue, cfg, state_path: str | None = None):
        self.venue = venue
        self.cfg = cfg
        self.state_path = state_path or cfg.state_path
        self.state = self._load_state()
        self._breach_count = 0
        self._last_flat_equity = None      # transfer-reconciliation baseline

    # ---------- persistence ----------

    def _load_state(self) -> ExecState:
        try:
            raw = json.load(open(self.state_path))
            st = ExecState(**{k: raw[k] for k in
                              ("halted", "day_key", "day_start_equity",
                               "high_water") if k in raw})
            st.legs = {n: LegLedger(**raw.get("legs", {}).get(n, {}))
                       for n in LEGS}
            st.events = raw.get("events", [])[-200:]
            st.marks = raw.get("marks", [])[-400:]
            st.fills = raw.get("fills", [])[-400:]
            st.last_dry_run = raw.get("last_dry_run")
            return st
        except Exception:  # noqa: BLE001
            return ExecState()

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        d = {"halted": self.state.halted, "day_key": self.state.day_key,
             "day_start_equity": self.state.day_start_equity,
             "high_water": self.state.high_water,
             "legs": {n: asdict(l) for n, l in self.state.legs.items()},
             "events": self.state.events[-200:],
             "marks": self.state.marks[-400:],
             "fills": getattr(self.state, "fills", [])[-400:],
             "last_dry_run": getattr(self.state, "last_dry_run", None)}
        tmp = self.state_path + ".tmp"
        json.dump(d, open(tmp, "w"))
        os.replace(tmp, self.state_path)

    def _event(self, level: str, kind: str, msg: str) -> None:
        last = self.state.events[-1] if self.state.events else None
        if last and last["kind"] == kind and last["msg"] == msg:
            return                       # dedupe: don't spam repeats every poll
        self.state.events.append(
            {"ts": int(time.time()), "level": level, "kind": kind, "msg": msg})
        logger.log(logging.WARNING if level in ("WARN", "RED") else logging.INFO,
                   "%s %s", kind, msg)
        # phone-worthy events only: halts and REDs, plus live trade entries/
        # exits (INFO order noise in dry-run stays out of Telegram).
        # Tier labels (Casey): 🔴 ACTION NEEDED = trading stays stopped or
        # misconfigured until YOU act; 🚨 forward-to-Claude = code/venue issue
        # that needs no user action beyond forwarding; ⚡/✅ informational.
        from .alerts import send
        ACTION = {
            "halt": "trading is STOPPED until you check /status and hit "
                    "/resume?token=YOUR_TOKEN (verify the cause first — "
                    "deposits/transfers can trip this falsely)",
            "halt_config": "fix the Render env (DD_HALT_PCT / "
                           "SIZING_BASE_USD) — as configured the halt line "
                           "can't work; trading logic continues but the "
                           "circuit breaker is miscalibrated",
            "mode_change": "if you did NOT change this, a blueprint sync "
                           "overwrote it - reset DRY_RUN in the Render "
                           "dashboard (it is sync:false now, so this should "
                           "not recur)",
            "halt_error": "closing positions during the halt FAILED — open "
                          "Coinbase NOW, check positions, flatten manually "
                          "if any remain",
        }
        if kind in ACTION:
            send(f"🔴 ACTION NEEDED (you) — executor {kind}: {msg}\n"
                 f"→ {ACTION[kind]}")
        elif level == "RED":
            send(f"🚨 executor {kind}: {msg}\n"
                 f"→ no action needed from you — forward this to Claude")
        elif kind in ("resume", "auto_rearm", "transfer_reconciled"):
            send(f"✅ executor {kind}: {msg} — no action needed")
        elif kind in ("entry_order", "leg_closed", "entry_chase") \
                and not getattr(self.cfg, "dry_run", True):
            send(f"⚡ executor {kind}: {msg}")

    # ---------- sizing ----------

    def _leg_frac(self, leg: str, blend: dict) -> float:
        w = blend.get("w_trend", 0.25)
        lev = blend.get("lev", 1.5)
        weight = w if leg == "trend" else 1.0 - w
        return self.cfg.kelly_m * lev * weight

    def _base(self, equity: float) -> float:
        """Sizing base: fixed SIZING_BASE_USD when configured, else account
        equity (the classic fully-funded construction)."""
        return getattr(self.cfg, "sizing_base_usd", 0.0) or equity

    def _leg_qty(self, leg: str, blend: dict, px: float, equity: float) -> float:
        """Unsigned BTC qty for a fresh leg entry, capped so the whole account
        stays inside max_notional_usd and max_account_lev (of the base)."""
        base = self._base(equity)
        want = self._leg_frac(leg, blend) * base / px
        other = sum(abs(l.qty) for n, l in self.state.legs.items() if n != leg)
        cap_notional = min(self.cfg.max_notional_usd,
                           self.cfg.max_account_lev * base)
        room = max(0.0, cap_notional / px - other)
        if want > room:
            self._event("RED", "cap_clamp",
                        f"{leg} qty {want:.5f}->{room:.5f} BTC (cap)")
            want = room
        return round(want, 5)

    # ---------- halts ----------

    def _roll_day(self, equity: float) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if day != self.state.day_key:
            # DAILY_LOSS is a rate limiter ("stop for today"), not a
            # model-falsification event: it re-arms itself at the UTC day
            # boundary. DRAWDOWN and KILL stay manual-resume by design —
            # the circuit breaker with automatic reset is a retry loop.
            if self.state.day_key and self.state.halted == "DAILY_LOSS":
                self.state.halted = None
                self._breach_count = 0
                self._event("INFO", "auto_rearm",
                            f"DAILY_LOSS cleared at UTC day rollover {day}")
            self.state.day_key = day
            self.state.day_start_equity = equity
            try:
                pos = self.venue.position()
            except Exception:  # noqa: BLE001
                pos = None
            self.state.marks.append(
                {"d": day, "equity": round(equity, 2),
                 "position_btc": round(pos, 5) if pos is not None else None})
        self.state.high_water = max(self.state.high_water, equity)

    def _reconcile_transfers(self, equity: float) -> None:
        """Deposits/withdrawals are not P&L. When the WHOLE book is flat (our
        ledger has no qty and no working orders), account equity can only
        move materially via a transfer — so shift the halt anchors
        (day-start, high-water) by the jump instead of letting it hit the
        halt math. This kills the false-halt category (the 2026-08 deposit
        halt) without touching genuine-loss detection: any move while a
        position is open, or while the venue still reports exposure, goes
        through the normal halt path untouched. Limitation: a transfer that
        lands during a restart window is seen as a baseline, not a jump."""
        prev = self._last_flat_equity
        flat = all(l.qty == 0 and not l.entry_cloid and not l.stop_cloid
                   for l in self.state.legs.values())
        if not flat:
            self._last_flat_equity = None
            return
        if prev is None or equity <= 0:
            self._last_flat_equity = equity if equity > 0 else None
            return
        delta = equity - prev
        floor = max(0.002 * self._base(equity), 50.0)
        if abs(delta) >= floor:
            try:                       # orphan guard: venue must agree we're flat
                if abs(self.venue.position() or 0.0) > 1e-6:
                    return             # exposure exists -> not a transfer
            except Exception:  # noqa: BLE001
                return                 # can't verify -> don't touch anchors
            if self.state.day_start_equity > 0:
                self.state.day_start_equity += delta
            if self.state.high_water > 0:
                self.state.high_water = max(self.state.high_water + delta, equity)
            self._breach_count = 0
            self._event("INFO", "transfer_reconciled",
                        f"flat-book equity moved {delta:+.0f} (no fills) - "
                        f"treated as transfer; halt anchors shifted, day start "
                        f"{self.state.day_start_equity:.0f}, HWM "
                        f"{self.state.high_water:.0f}")
        self._last_flat_equity = equity

    def _check_halts(self, equity: float) -> None:
        """Loss thresholds are percentages OF THE SIZING BASE: with a fixed
        base and a small account, a -6%-of-base day is the same dollar event
        it would be fully funded — anchoring to account equity instead would
        false-trigger on routine swings (or, worse, never trigger as the
        account shrinks)."""
        if self.state.halted:
            return
        st = self.state
        base_d = self._base(st.day_start_equity)
        base_h = self._base(st.high_water)
        # coherence guard: a DD halt deeper than ~80% of the account can
        # never fire before wipeout — the deposit/base ratio and DD_HALT_PCT
        # must be chosen together (see EXECUTOR.md funding phases)
        if 0 < equity < base_h and self.cfg.dd_halt_pct * base_h > 0.8 * equity:
            self._event("WARN", "halt_config",
                        f"DD halt {self.cfg.dd_halt_pct:.0%} of base "
                        f"{base_h:.0f} exceeds 80% of account {equity:.0f} - "
                        "lower DD_HALT_PCT or raise the deposit")
        breach = None
        if st.day_start_equity > 0 and \
                equity < st.day_start_equity - self.cfg.daily_loss_halt_pct * base_d:
            breach = ("DAILY_LOSS",
                      f"equity {equity:.0f} < day start {st.day_start_equity:.0f}"
                      f" - {self.cfg.daily_loss_halt_pct:.0%} of base {base_d:.0f}")
        elif st.high_water > 0 and \
                equity < st.high_water - self.cfg.dd_halt_pct * base_h:
            breach = ("DRAWDOWN",
                      f"equity {equity:.0f} < HWM {st.high_water:.0f}"
                      f" - {self.cfg.dd_halt_pct:.0%} of base {base_h:.0f}")
        if breach is None:
            self._breach_count = 0
            return
        # debounce: a real drawdown persists across polls; a transient bad
        # balance read (the 2026-08-06 false DRAWDOWN halt) does not
        self._breach_count += 1
        if self._breach_count == 1:
            self._event("WARN", "halt_pending",
                        f"{breach[0]} breach 1/{self.HALT_CONFIRM_POLLS}: {breach[1]}")
        if self._breach_count >= self.HALT_CONFIRM_POLLS:
            self.halt(*breach)

    def halt(self, reason: str, msg: str = "") -> None:
        """Cancel everything, flatten everything, block until resume()."""
        self.state.halted = reason
        self._event("RED", "halt", f"{reason} {msg}")
        try:
            self.venue.cancel_all()
            net = self.venue.position()
            if abs(net) > 1e-6:
                self.venue.place_market(_close_side(net), abs(net),
                                        f"halt-{int(time.time())}")
        except Exception as exc:  # noqa: BLE001
            self._event("RED", "halt_error", str(exc))
        for l in self.state.legs.values():
            l.qty = 0.0
            l.entry_cloid = l.stop_cloid = None
        self._save_state()

    def resume(self) -> None:
        self._event("INFO", "resume", f"cleared {self.state.halted}")
        self.state.halted = None
        self._save_state()

    # ---------- main step ----------

    def _check_mode_change(self) -> None:
        """A blueprint sync silently reset DRY_RUN to true on a LIVE account
        (2026-08-10) - the executor kept reporting healthy while placing
        nothing. Any mode flip now pages the operator."""
        cur = bool(getattr(self.cfg, "dry_run", True))
        prev = getattr(self.state, "last_dry_run", None)
        if prev is not None and prev != cur:
            self._event("RED", "mode_change",
                        f"DRY_RUN {prev} -> {cur}: trading is now "
                        f"{'SIMULATED (no real orders)' if cur else 'LIVE'} - "
                        f"verify this was intentional (a blueprint sync can "
                        f"reset it)")
        self.state.last_dry_run = cur

    def step(self, target: dict) -> None:
        self._check_mode_change()
        equity = self.venue.equity()
        self._reconcile_transfers(equity)
        self._roll_day(equity)
        self._check_halts(equity)
        if self.state.halted:
            self._save_state()
            return
        stale = (time.time() - (target.get("bar_ts") or 0)
                 > (self.cfg.stale_bars_max + 1) * BAR_SECONDS)
        entries_ok = not (stale or target.get("degraded")
                          or target.get("data_halt"))
        if not entries_ok:
            self._event("WARN", "entries_blocked",
                        f"stale={stale} degraded={target.get('degraded')} "
                        f"data_halt={target.get('data_halt')}")
        blend = target.get("blend", {})
        for leg in LEGS:
            tl = (target.get("legs") or {}).get(leg)
            if tl is None:
                continue
            try:
                self._sync_leg(leg, tl, blend, equity, entries_ok)
            except Exception as exc:  # noqa: BLE001
                # isolate: a venue error on one leg used to unwind the whole
                # step via the loop's bare except, silently skipping the other
                # leg on every poll it occurred (QA 2026-08-10).
                self._event("RED", "leg_sync_error", f"{leg}: {exc}")
        self._report_post_only_crosses()
        self._check_drift(equity)
        self._save_state()

    # ---------- per-leg reconciliation ----------

    def _sync_leg(self, leg: str, tl: dict, blend: dict,
                  equity: float, entries_ok: bool) -> None:
        led: LegLedger = self.state.legs[leg]
        pend, pos = tl.get("pending"), tl.get("position")

        # 1) engine has an open position
        if pos is not None:
            if led.qty == 0.0:
                self._enter_from_fill(leg, led, pos, blend, equity)
            if led.qty != 0.0:
                self._maintain_stop(leg, led, pos)
            return

        # 2) no position; engine holds a pending entry
        if pend is not None:
            cloid = f"{leg[0].upper()}-{pend['signal_ts']}-E"
            # Identity check FIRST. The trend leg fills at market and sets
            # led.qty immediately, but the engine keeps reporting `pending`
            # until its own next bar close. A qty check ahead of this one
            # read that as "engine flat but we still hold" and closed the
            # position on the very next poll — the trend leg could never
            # hold a position (live find, first trade 2026-08-10).
            if led.entry_cloid == cloid:
                return
            # Different signal: any qty here is from an older cycle. A fill
            # already carried in led.qty is closed by _close_leg — unwinding
            # it again in _cancel_entry would double-close and leave a naked
            # reverse position (QA rehearsal find, 2026-08-07).
            had_qty = led.qty != 0.0
            if had_qty:
                self._close_leg(leg, led, "engine_flat")
            if not entries_ok:
                return
            if led.entry_cloid:
                self._cancel_entry(led, filled_action="ignore" if had_qty
                                   else "flatten")
            limit_px = pend.get("limit")
            if not limit_px or limit_px <= 0:      # -1.0 = market-entry sentinel
                limit_px = self.venue.mid()
            qty = self._leg_qty(leg, blend, limit_px, equity)
            if qty <= 0:
                return
            side = _order_side(pend["side"])
            if leg == "pullback":
                self.venue.place_limit(side, qty, pend["limit"], cloid,
                                       post_only=True)
            else:
                self.venue.place_market(side, qty, cloid)
                led.qty = _side_sign(pend["side"]) * qty
            led.entry_cloid, led.entry_side = cloid, pend["side"]
            led.entry_qty, led.signal_ts = qty, pend["signal_ts"]
            self._event("INFO", "entry_order",
                        f"{leg} {side} {qty} @ {pend.get('limit') or 'mkt'}")
            return

        # 3) engine is flat with no pending
        if led.entry_cloid:
            # orphan-unwind ONLY for an unabsorbed fill (led.qty still 0):
            # a fill living in led.qty is closed once, below. The old
            # unconditional flatten double-closed trend exits — market entry
            # keeps entry_cloid for the position's life — leaving a naked
            # reverse position on the venue (QA rehearsal find, 2026-08-07).
            self._cancel_entry(led, filled_action="flatten" if led.qty == 0.0
                               else "ignore")
        if led.qty != 0.0:
            self._close_leg(leg, led, "engine_exit")

    def _enter_from_fill(self, leg: str, led: LegLedger, pos: dict,
                         blend: dict, equity: float) -> None:
        """Engine position appeared. If our entry order (partially) missed,
        chase the remainder at market so the legs stay in sync."""
        want = self._leg_qty(leg, blend, pos["entry_price"], equity)
        filled = 0.0
        if led.entry_cloid:
            st = self.venue.order_status(led.entry_cloid)
            filled = (st or {}).get("filled_qty", 0.0)
            if st and st.get("status") == "OPEN" and filled < want:
                self.venue.cancel(led.entry_cloid)
        missing = max(0.0, round(want - filled, 5))
        if missing > 0 and want > 0:
            side = _order_side(pos["side"])
            self.venue.place_market(side, missing,
                                    f"{leg[0].upper()}-{pos['entry_ts']}-C")
            self._event("WARN", "entry_chase",
                        f"{leg} missed {missing} of {want} BTC - chased at market")
        led.qty = _side_sign(pos["side"]) * want
        led.entry_cloid = None
        led.signal_ts = pos.get("signal_ts")

    def _maintain_stop(self, leg: str, led: LegLedger, pos: dict) -> None:
        trigger = pos.get("stop")
        if not trigger or led.qty == 0.0:
            return
        if led.stop_px and abs(trigger - led.stop_px) / led.stop_px \
                < self.cfg.stop_replace_bps / 10_000.0:
            return
        cloid = f"{leg[0].upper()}-{pos['entry_ts']}-S{int(trigger)}"
        if led.stop_cloid:
            st = self.venue.order_status(led.stop_cloid)
            if st and st.get("status") == "FILLED":
                # protective stop already fired on-venue; ledger goes flat and
                # the engine will catch up at its own stop logic
                self._event("INFO", "stop_filled_on_venue", f"{leg}")
                led.qty, led.stop_cloid, led.stop_px = 0.0, None, None
                return
            self.venue.cancel(led.stop_cloid)
        self.venue.place_stop(_close_side(led.qty), abs(led.qty), trigger, cloid)
        led.stop_cloid, led.stop_px = cloid, trigger

    def _cancel_entry(self, led: LegLedger, filled_action: str) -> None:
        st = self.venue.order_status(led.entry_cloid)
        if st and st.get("status") != "FILLED":
            self.venue.cancel(led.entry_cloid)
        filled = (st or {}).get("filled_qty", 0.0)
        if filled > 0 and filled_action == "flatten":
            side = "SELL" if led.entry_side == "L" else "BUY"
            self.venue.place_market(side, filled,
                                    f"{led.entry_cloid}-UNWIND")
            self._event("WARN", "orphan_fill_unwound",
                        f"{led.entry_cloid} filled {filled} but engine cancelled")
        led.entry_cloid = led.entry_side = None
        led.entry_qty = 0.0

    def _close_leg(self, leg: str, led: LegLedger, why: str) -> None:
        if led.stop_cloid:
            st = self.venue.order_status(led.stop_cloid)
            if st and st.get("status") == "FILLED":
                led.qty = 0.0          # stop beat the signal exit; already flat
            else:
                self.venue.cancel(led.stop_cloid)
            led.stop_cloid, led.stop_px = None, None
        if led.qty != 0.0:
            self.venue.place_market(_close_side(led.qty), abs(led.qty),
                                    f"{leg[0].upper()}-{int(time.time())}-X")
            self._event("INFO", "leg_closed", f"{leg} {why} qty={led.qty}")
            led.qty = 0.0

    def _report_post_only_crosses(self) -> None:
        """The engine prices signals off SPOT but we trade a FUTURE; at a
        positive basis short limits are marketable and post-only is rejected.
        cb.py retries them as marketable limits (fills at our price or better,
        taker fee). Surface each one: it is a maker->taker cost change and a
        tracking-error source, and it was previously invisible."""
        seen = getattr(self.venue, "post_only_crosses", None)
        if not seen:
            return
        for cloid in list(seen):
            self._event("WARN", "post_only_cross",
                        f"{cloid} rejected as marketable (spot/future basis) "
                        f"- refilled as taker")
        seen.clear()

    def _record_fill(self, leg: str, role: str, cloid: str, st: dict,
                     ref_px: float) -> None:
        """Persist execution prices so slippage is MEASURABLE. Before this the
        venue's average_filled_price was discarded and the ramp's slippage
        gate had a sample size of zero (QA 2026-08-10)."""
        px = (st or {}).get("avg_price")
        if not px or not ref_px:
            return
        sign = 1.0 if st.get("side_sign", 1) > 0 else 1.0
        bps = (px - ref_px) / ref_px * 10_000 * sign
        self.state.fills = (getattr(self.state, "fills", None) or [])[-400:]
        self.state.fills.append({"ts": int(time.time()), "leg": leg,
                                 "role": role, "cloid": cloid,
                                 "px": round(float(px), 2),
                                 "ref_px": round(float(ref_px), 2),
                                 "slip_bps": round(bps, 2)})

    # ---------- drift ----------

    def _check_drift(self, equity: float) -> None:
        if getattr(self.venue, "log", None) is not None:
            return          # dry-run venue: simulated fills, drift meaningless
        try:
            net = self.venue.position()
        except Exception:  # noqa: BLE001
            return
        want = sum(l.qty for l in self.state.legs.values())
        px = self.venue.mid()
        if abs(net - want) * px > self.cfg.drift_tol_frac * max(equity, 1.0):
            self._event("RED", "position_drift",
                        f"venue={net:.5f} ledger={want:.5f} BTC - investigate")
