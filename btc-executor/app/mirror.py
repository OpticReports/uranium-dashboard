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
    def quantize(self, qty: float) -> float: ...   # -> tradable size, rounds DOWN
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
    # entry_ts of an engine position whose protective stop FILLED on-venue.
    # While the engine (which only updates on 4h bar closes) keeps reporting
    # that position, case 1 must NOT re-enter from the stale entry order -
    # doing so resurrected a phantom ledger position and armed a live stop on
    # a flat venue (counter-agent find 2026-08-11, pre-existing FATAL class).
    stopped_entry_ts: int | None = None


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
    last_config: dict | None = None       # detects silent sizing/risk resets


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
        self._fill_watch: list[dict] = []  # orders pending a fill-price read
        self._sent_at: dict[str, float] = {}   # per-kind Telegram cooldown
        self._migrate_ledger_granularity()

    def _migrate_ledger_granularity(self) -> None:
        """Persisted state written before 8e27c01 recorded REQUESTED sizes
        (e.g. -0.01466 BTC) while the venue holds whole contracts. Snap each
        leg to the venue's granularity once at load, so every later stop /
        close / cap computation matches reality. A residue that quantizes to
        zero is dust the venue cannot hold - zero it and say so."""
        for name, led in self.state.legs.items():
            if led.qty == 0.0:
                continue
            try:
                q = self.venue.quantize(abs(led.qty))
            except Exception:  # noqa: BLE001
                continue
            snapped = q if led.qty > 0 else -q
            if snapped != led.qty:
                self._event("WARN", "ledger_migrated",
                            f"{name} qty {led.qty} -> {snapped} "
                            f"(venue granularity)")
                led.qty = snapped

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
            st.last_config = raw.get("last_config")
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
             "last_dry_run": getattr(self.state, "last_dry_run", None),
             "last_config": getattr(self.state, "last_config", None)}
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
            "config_change": "sizing/risk config changed - if this was you "
                             "(ramp step, base change), ignore; if NOT, a "
                             "sync or fat-finger altered live risk limits - "
                             "check the Render env vars now",
        }
        # Per-kind Telegram cooldown for conditions that persist across polls
        # (their msg embeds a changing float, so kind+msg dedupe never fires).
        # halt_config alone was ~180 pages/hour while equity sat below the
        # miscalibration line (counter-agent find 2026-08-11). Events are all
        # still LOGGED - only the phone pings are rate-limited. Halts, mode
        # changes and live-trade events are never suppressed.
        RATE_LIMITED = {"halt_config", "cap_clamp", "leg_sync_error",
                        "position_drift", "entries_blocked", "sub_min_size"}
        if kind in RATE_LIMITED:
            now = time.time()
            if now - self._sent_at.get(kind, 0.0) < 1800:
                return
            self._sent_at[kind] = now
        if kind in ACTION:
            send(f"🔴 ACTION NEEDED (you) — executor {kind}: {msg}\n"
                 f"→ {ACTION[kind]}")
        elif level == "RED":
            send(f"🚨 executor {kind}: {msg}\n"
                 f"→ no action needed from you — forward this to Claude")
        elif kind in ("resume", "auto_rearm", "transfer_reconciled"):
            send(f"✅ executor {kind}: {msg} — no action needed")
        elif kind in ("entry_order", "leg_closed", "entry_chase",
                      "stop_filled_on_venue", "orphan_fill_unwound") \
                and not getattr(self.cfg, "dry_run", True):
            # stop_filled_on_venue is a REAL money exit and orphan_fill_unwound
            # places a real order - both were log-only while routine engine
            # exits pinged the phone (counter-agent find 2026-08-11)
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
        # Quantize to the venue's tradable increment (whole 0.01-BTC contracts
        # on CDE) BEFORE the ledger sees it. Ordering in continuous BTC while
        # the venue fills in contracts made led.qty drift from the real
        # position on every entry (live find, 2026-08-10).
        qty = self.venue.quantize(round(want, 8))
        if qty <= 0.0 and want > 0.0:
            # RED, not WARN: a leg silently never trading is the "healthy
            # while doing nothing" phenotype - it must reach the phone
            # (rate-limited to one ping per 30 min)
            self._event("RED", "sub_min_size",
                        f"{leg} target {want:.5f} BTC is below the venue "
                        f"minimum - leg not entered this cycle")
        return round(qty, 8)

    # ---------- halts ----------

    def _roll_day(self, equity: float) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if day != self.state.day_key:
            # DAILY_LOSS is a rate limiter ("stop for today"), not a
            # model-falsification event: it re-arms itself at the UTC day
            # boundary. DRAWDOWN and KILL stay manual-resume by design —
            # the circuit breaker with automatic reset is a retry loop.
            # ABOVE KELLY_M 0.30 the rule flips to manual (EXECUTOR.md ramp
            # v3): at that size a breach is meaningful evidence and auto-
            # rearm would clear the only breaker reachable during the ramp,
            # granting a fresh full budget at 00:00 UTC mid-move. This rule
            # was doc-only until 2026-08-11 (counter-agent find).
            if self.state.day_key and self.state.halted == "DAILY_LOSS":
                if getattr(self.cfg, "kelly_m", 0.0) > 0.30:
                    self._event("RED", "halt",
                                f"DAILY_LOSS held through UTC rollover {day}: "
                                f"KELLY_M {self.cfg.kelly_m} > 0.30 requires "
                                f"MANUAL resume (ramp v3 rule)")
                else:
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
            # NOTE: deliberately NOT resetting _breach_count here - a flat-book
            # equity wobble must not cancel a halt confirmation in progress
            # (counter-agent find 2026-08-11)
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
            for l in self.state.legs.values():
                l.qty = 0.0
                l.entry_cloid = l.stop_cloid = None
        except Exception as exc:  # noqa: BLE001
            # Flatten FAILED: keep the ledger as-is - it is the only record
            # of what we believe we hold. Zeroing it here made the transfer
            # reconciler read a naked position's bleed as withdrawals
            # (counter-agent find 2026-08-11). halt_error already pages.
            self._event("RED", "halt_error", str(exc))
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
        # Same incident class, other variables: a blueprint sync can reset any
        # literal-valued env silently (they are sync:false now, but belt AND
        # suspenders - a dashboard fat-finger pages too). Snapshot the whole
        # sizing config and page on ANY change (counter-agent find 2026-08-11).
        snap = {k: getattr(self.cfg, k, None) for k in
                ("kelly_m", "sizing_base_usd", "max_notional_usd",
                 "max_account_lev", "dd_halt_pct", "daily_loss_halt_pct",
                 "cb_product_id")}
        prev_snap = getattr(self.state, "last_config", None)
        if prev_snap is not None and prev_snap != snap:
            diffs = [f"{k}: {prev_snap.get(k)} -> {v}"
                     for k, v in snap.items() if prev_snap.get(k) != v]
            self._event("RED", "config_change", "; ".join(diffs))
        self.state.last_config = snap

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
            # RED: a stale/degraded engine feed silently stopping all entries
            # for days while /health stays green is the DRY_RUN-incident
            # phenotype (rate-limited to one ping per 30 min)
            self._event("RED", "entries_blocked",
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
        self._poll_fill_watch()
        self._check_drift(equity)
        self._save_state()

    # ---------- per-leg reconciliation ----------

    def _sync_leg(self, leg: str, tl: dict, blend: dict,
                  equity: float, entries_ok: bool) -> None:
        led: LegLedger = self.state.legs[leg]
        pend, pos = tl.get("pending"), tl.get("position")

        # 1) engine has an open position
        if pos is not None:
            if led.stopped_entry_ts == pos.get("entry_ts"):
                # our venue stop already closed THIS position; the engine just
                # hasn't seen it yet (it updates on 4h closes). Re-entering
                # from the stale entry order here resurrected a phantom
                # position (counter-agent find 2026-08-11). Wait it out.
                return
            led.stopped_entry_ts = None
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
            self._watch_fill(leg, "entry", cloid, limit_px, side)
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
        # A remainder below one contract is NOT chaseable — the old code sent
        # it anyway and the venue rounded it up to a full contract, overshooting
        # the target (live find, 2026-08-10). Round the shortfall down and
        # accept the tracking error instead.
        missing = self.venue.quantize(max(0.0, round(want - filled, 8)))
        if missing > 0:
            side = _order_side(pos["side"])
            self.venue.place_market(side, missing,
                                    f"{leg[0].upper()}-{pos['entry_ts']}-C")
            self._watch_fill(leg, "chase", f"{leg[0].upper()}-{pos['entry_ts']}-C",
                             pos["entry_price"], side)
            self._event("WARN", "entry_chase",
                        f"{leg} missed {missing} of {want} BTC - chased at market")
        # Record what the venue HOLDS (filled + whatever we could chase), not
        # the target. Anything else desynchronises stops and exits.
        led.qty = _side_sign(pos["side"]) * round(filled + missing, 8)
        led.entry_cloid = None
        led.signal_ts = pos.get("signal_ts")

    def _maintain_stop(self, leg: str, led: LegLedger, pos: dict) -> None:
        trigger = pos.get("stop")
        if not trigger or led.qty == 0.0:
            return
        # Check for an on-venue stop FILL before the churn guard: the old
        # order hid a fired stop for as long as the trail moved < 5bp, then
        # the flat ledger + engine-still-reports-position window resurrected
        # the position from the stale entry order and armed a live stop on a
        # flat venue (counter-agent find 2026-08-11, reproduced end-to-end).
        if led.stop_cloid:
            st = self.venue.order_status(led.stop_cloid)
            if st and st.get("status") == "FILLED":
                # protective stop fired on-venue; ledger goes flat, and
                # stopped_entry_ts blocks re-entry from this same engine
                # position until the engine catches up at its own stop logic
                self._event("INFO", "stop_filled_on_venue", f"{leg}")
                led.qty, led.stop_cloid, led.stop_px = 0.0, None, None
                led.stopped_entry_ts = pos.get("entry_ts")
                # the entry order is consumed - its fill was closed BY the
                # stop. Trend keeps entry_cloid for the position's life, so
                # without this, case 3's orphan-flatten would re-close the
                # filled entry and open a naked reverse position.
                led.entry_cloid = led.entry_side = None
                led.entry_qty = 0.0
                return
        if led.stop_px and abs(trigger - led.stop_px) / led.stop_px \
                < self.cfg.stop_replace_bps / 10_000.0:
            return
        cloid = f"{leg[0].upper()}-{pos['entry_ts']}-S{int(trigger)}"
        if led.stop_cloid:
            self.venue.cancel(led.stop_cloid)
        self.venue.place_stop(_close_side(led.qty), abs(led.qty), trigger, cloid)
        self._watch_fill(leg, "stop", cloid, trigger, _close_side(led.qty))
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
            # Quantize the close: a stale sub-contract residue (old-format
            # persisted state) would make place_market raise AFTER the stop
            # was already cancelled - a permanent naked, stopless loop
            # (counter-agent find 2026-08-11). A residue the venue cannot
            # hold is ledger dust, not a position: zero it and say so.
            qty = abs(led.qty)
            try:
                qty = self.venue.quantize(qty)
            except Exception:  # noqa: BLE001
                pass
            if qty <= 0.0:
                self._event("RED", "ledger_dust_cleared",
                            f"{leg} qty {led.qty} below venue minimum - "
                            f"cleared without an order (verify flat on venue)")
                led.qty = 0.0
                return
            cloid = f"{leg[0].upper()}-{int(time.time())}-X"
            try:
                ref = self.venue.mid()
            except Exception:  # noqa: BLE001
                ref = 0.0
            self.venue.place_market(_close_side(led.qty), qty, cloid)
            self._watch_fill(leg, "close", cloid, ref, _close_side(led.qty))
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

    def _watch_fill(self, leg: str, role: str, cloid: str, ref_px: float,
                    side: str) -> None:
        """Queue an order for fill-price capture. _record_fill existed since
        9fd498f but had ZERO call sites - the ramp's primary 'fill quality'
        criterion ran on a dataset of size zero (counter-agent find
        2026-08-11). Every order placed now enters this queue; _poll_fill_watch
        drains it as statuses resolve."""
        if not ref_px or ref_px <= 0:
            return
        self._fill_watch.append({"ts": time.time(), "leg": leg, "role": role,
                                 "cloid": cloid, "ref_px": float(ref_px),
                                 "side": side})
        del self._fill_watch[:-64]

    def _poll_fill_watch(self) -> None:
        keep = []
        for w in self._fill_watch:
            st = None
            try:
                st = self.venue.order_status(w["cloid"])
            except Exception:  # noqa: BLE001
                pass
            if st is None or st.get("status") == "OPEN":
                if time.time() - w["ts"] < 48 * 3600:
                    keep.append(w)
                continue
            if st.get("status") == "FILLED":
                self._record_fill(w["leg"], w["role"], w["cloid"], st,
                                  w["ref_px"], w["side"])
        self._fill_watch = keep

    def _record_fill(self, leg: str, role: str, cloid: str, st: dict,
                     ref_px: float, side: str) -> None:
        """Persist execution prices so slippage is MEASURABLE. slip_bps is
        signed ADVERSE-POSITIVE: paying up on a BUY and getting hit down on a
        SELL are both positive. (The original expression evaluated to +1.0 on
        both branches, which would have sign-flipped every SELL - counter-agent
        find 2026-08-11.)"""
        px = (st or {}).get("avg_price")
        if not px or not ref_px:
            return
        sign = 1.0 if side == "BUY" else -1.0
        bps = (float(px) - ref_px) / ref_px * 10_000 * sign
        self.state.fills = (getattr(self.state, "fills", None) or [])[-400:]
        self.state.fills.append({"ts": int(time.time()), "leg": leg,
                                 "role": role, "cloid": cloid, "side": side,
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
