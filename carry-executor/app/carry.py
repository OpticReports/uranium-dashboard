"""ETH funding-carry sleeve: long spot UETH, short ETH perp, same quantity.

The ENGINE decides on/off (btc-paper-engine funding monitor, GET
/carry/target: ARM when HL ETH 30d funding >= 8%/yr, DISARM < 5%). This
service only executes. Each pass:

  1. read the decision; a stale, unknown or malformed one HOLDS the current
     state - it never opens a new sleeve and never closes a hedged one;
  2. read both legs from the venue (unreadable -> do nothing);
  3. pick the target spot quantity: notional / spot mid on a fresh open, the
     persisted target while on (re-sized at a UTC month start if it has
     drifted > RESIZE_DRIFT), 0 when off;
  4. move SPOT toward the target with one IOC, re-read, then move the PERP to
     -(spot actually held) with one IOC. The perp always hedges what the
     spot leg really holds, so a partial spot fill can never leave a naked
     short, and an unwind sells spot first and buys back only what is left;
  5. check the hedge: a residual gap over HEDGE_TOL_USD for 2 passes pages.

Delta-neutral by construction: price P&L of the two legs cancels (to the
spot-vs-perp basis); the sleeve earns funding on the short.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field

from . import alerts

logger = logging.getLogger(__name__)

# HARD CEILING, a repo constant like btc-executor's KELLY_M_CAP: the env sets
# the size, the repo bounds it. Casey approved $30k (2026-10-01).
CARRY_MAX_NOTIONAL_USD = 50_000.0
MIN_ORDER_USD = 11.0          # HL rejects orders under $10 notional
HEDGE_TOL_USD = 50.0          # residual |spot + perp| x px tolerated
HEDGE_GAP_PAGE_POLLS = 2
VENUE_FAIL_PAGE_POLLS = 3
SIGNAL_GRACE_S = 3600         # past 2 x the monitor's check interval
GUARD_COOLDOWN_S = 24 * 3600  # after a margin-guard unwind, stay flat this long


@dataclass
class CarryState:
    on: bool = False
    target_qty: float = 0.0
    opened_ts: int | None = None
    last_resize_month: str = ""
    halted: str | None = None
    guard_until: float = 0.0
    hedge_gap_polls: int = 0
    venue_fail_polls: int = 0
    last_read: dict = field(default_factory=dict)
    last_signal: dict = field(default_factory=dict)
    last_step_ts: int | None = None
    events: list = field(default_factory=list)


class CarryExecutor:
    def __init__(self, venue, cfg, state_path: str, alert_fn=None, clock=None,
                 preflight_fn=None):
        self.venue = venue
        self.cfg = cfg
        self.state_path = state_path
        self.alert_fn = alert_fn or alerts.send
        self.clock = clock or time.time
        self.lock = threading.Lock()
        self.state = self._load()
        self._sent_at: dict[str, float] = {}
        self._last_intent: str | None = None
        self._cross_ok = False
        # (ok, why) - may risk be ADDED? Default allows; main.py wires the
        # btc-executor capability check (review SERIOUS-3)
        self.preflight_fn = preflight_fn or (lambda: (True, "no preflight"))

    # ---------- persistence / events ----------

    def _load(self) -> CarryState:
        try:
            raw = json.load(open(self.state_path))
            known = set(CarryState.__dataclass_fields__)
            return CarryState(**{k: v for k, v in raw.items() if k in known})
        except FileNotFoundError:
            return CarryState()
        except Exception as exc:  # noqa: BLE001
            # an unreadable state file must not silently forget a live sleeve:
            # HOLD until a human looks (the venue still holds the truth)
            logger.error("carry state unreadable (%s) - starting HALTED", exc)
            return CarryState(halted="STATE_UNREADABLE")

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        tmp = f"{self.state_path}.tmp"
        with open(tmp, "w") as fh:
            json.dump(asdict(self.state), fh)
        os.replace(tmp, self.state_path)

    def _event(self, level: str, kind: str, msg: str, rate_limit: bool = False) -> None:
        now = self.clock()
        self.state.events = (self.state.events + [
            {"ts": int(now), "level": level, "kind": kind, "msg": msg}])[-200:]
        logger.log(logging.ERROR if level == "RED" else logging.INFO,
                   "%s %s: %s", level, kind, msg)
        if rate_limit and now - self._sent_at.get(kind, 0.0) < 1800:
            return
        self._sent_at[kind] = now
        if level == "RED":
            self.alert_fn(f"🚨 carry {kind}: {msg}")
        elif level == "ACTION":
            self.alert_fn(f"🔴 ACTION NEEDED (you) — carry {kind}: {msg}")
        elif level == "INFO" and kind in ("opened", "adopted", "closed", "resized", "resumed"):
            self.alert_fn(f"✅ carry {kind}: {msg}")

    # ---------- the decision ----------

    def _signal(self, target) -> tuple[bool | None, str]:
        """(armed?, why). None = do not act on it (hold)."""
        if not isinstance(target, dict):
            return None, "no target from the engine"
        if target.get("venue") != "HL_ETH" or target.get("coin") != self.cfg.perp_coin:
            return None, f"target is for {target.get('venue')}/{target.get('coin')}"
        if target.get("known") is not True:
            return None, "engine has no trustworthy funding reading"
        armed = target.get("armed")
        if not isinstance(armed, bool):
            return None, f"armed={armed!r} is not a bool"
        lc, cs = target.get("last_checked"), target.get("check_seconds")
        try:
            age = self.clock() - float(lc)
            max_age = 2 * float(cs) + SIGNAL_GRACE_S
        except (TypeError, ValueError):
            return None, "signal carries no usable timestamp"
        if age > max_age:
            return None, f"signal is {age / 3600:.1f}h old (max {max_age / 3600:.1f}h)"
        return armed, f"engine {'ARMED' if armed else 'DISARMED'} at {target.get('mean_ann_pct')}%/yr"

    def _notional(self) -> float:
        n = float(self.cfg.carry_notional_usd or 0.0)
        if n != n or n < 0:
            return 0.0
        if n > CARRY_MAX_NOTIONAL_USD:
            self._event("RED", "notional_over_cap",
                        f"CARRY_NOTIONAL_USD {n:,.0f} is over the repo cap "
                        f"{CARRY_MAX_NOTIONAL_USD:,.0f} - sizing at the cap",
                        rate_limit=True)
            return CARRY_MAX_NOTIONAL_USD
        return n

    # ---------- orders ----------

    def _order(self, market: str, is_buy: bool, qty: float, px: float,
               reduce_only: bool = False) -> float:
        """Send (or, in DRY_RUN, describe) one IOC. Returns qty filled."""
        side = "BUY" if is_buy else "SELL"
        what = f"{market} {side} {qty:.4f} @~{px:,.2f}" + (" reduce-only" if reduce_only else "")
        if self.cfg.dry_run:
            if self._last_intent != what:
                self._event("INFO", "dry_run_intent", f"would send {what}")
                self._last_intent = what
            return 0.0
        r = self.venue.ioc(market, is_buy, qty, px, self.cfg.max_slip_bps,
                           reduce_only=reduce_only)
        self._event("INFO", "order", f"{what}: filled {r['filled']:.4f}"
                    + (f" @ {r['avg_px']:,.2f}" if r.get("avg_px") else ""))
        return float(r["filled"])

    # ---------- one pass ----------

    def step(self, target) -> None:
        with self.lock:
            try:
                self._step(target)
            except Exception as exc:  # noqa: BLE001
                # an order or re-read failure mid-pass: the next pass re-reads
                # the venue and repairs toward the target. The hedge check
                # MUST still run (review 2026-10-01 SERIOUS-1: a perp leg that
                # kept failing after the spot buy filled left ~$30k naked with
                # the unhedged counter never incrementing) - on a FRESH read,
                # since last_read may predate the fill.
                self._event("RED", "step_error", f"{type(exc).__name__}: {exc}",
                            rate_limit=True)
                try:
                    v = self.venue.read()
                    self.state.last_read = v
                    self._check_hedge(v)
                except Exception:  # noqa: BLE001
                    pass
            finally:
                self.state.last_step_ts = int(self.clock())
                self._save()

    def _step(self, target) -> None:
        armed, why = self._signal(target)
        self.state.last_signal = {"armed": armed, "why": why,
                                  "mean_ann_pct": (target or {}).get("mean_ann_pct")
                                  if isinstance(target, dict) else None}
        if armed is None:
            self._event("RED", "signal_unusable", f"holding: {why}", rate_limit=True)
        try:
            v = self.venue.read()
        except Exception as exc:  # noqa: BLE001
            self.state.venue_fail_polls += 1
            if self.state.venue_fail_polls >= VENUE_FAIL_PAGE_POLLS:
                self._event("RED", "venue_unreadable",
                            f"{self.state.venue_fail_polls} passes: {exc}", rate_limit=True)
            return
        self.state.venue_fail_polls = 0
        self.state.last_read = v
        if self.state.halted:
            self._check_hedge(v)
            return

        S, P = v["spot_qty"], v["perp_qty"]
        px_s, px_p = v["spot_mid"], v["perp_mid"]
        if not (px_s > 0 and px_p > 0):
            self._event("RED", "bad_price", f"spot {px_s} perp {px_p}", rate_limit=True)
            return

        # ---- desired state ----
        held_on = self.state.on or S * px_s >= MIN_ORDER_USD
        desired = held_on if armed is None else armed
        if not self.cfg.carry_enabled:
            desired = False
        notional = self._notional()
        if desired and notional <= 0 and not held_on:
            # 0 = never OPEN. A held sleeve keeps its size (review MINOR-5;
            # held_on, not state.on, so a lost state file can't unwind it -
            # re-review MINOR-C); CARRY_ENABLED=false is the close switch.
            desired = False
        now = self.clock()
        liq = v.get("liq_px")
        if P < 0 and liq:
            if liq <= px_p:
                # a short's liquidation price sits ABOVE the mark; one at or
                # below it is not a number to act on (review SERIOUS-2:
                # liquidationPx under a unified account is unverified)
                self._event("RED", "margin_guard_unreliable",
                            f"venue reports liquidation {liq:,.2f} at/below "
                            f"ETH {px_p:,.2f} for a short - ignoring it",
                            rate_limit=True)
            elif px_p >= liq * (1 - self.cfg.liq_buffer):
                self.state.guard_until = now + GUARD_COOLDOWN_S
                self._event("RED", "margin_guard",
                            f"ETH {px_p:,.2f} is within {self.cfg.liq_buffer:.0%} "
                            f"of the short's liquidation {liq:,.2f} - unwinding; "
                            f"no re-open for {GUARD_COOLDOWN_S // 3600}h",
                            rate_limit=True)
        if now < self.state.guard_until:
            # LATCHED: without it an armed sleeve re-opened on the next pass
            # and unwound again every 5 minutes (review SERIOUS-2)
            desired = False

        # ---- target spot quantity ----
        was_on = self.state.on
        resized = False
        resize_month = None
        sent = 0
        if armed is None and desired:
            # HOLD means hold THE VENUE: spot stays exactly where it is (no
            # open, no close, no re-size, no re-buying a sleeve that the
            # account no longer holds); only the hedge below is kept, since
            # matching the short to the spot can only reduce risk. The kill
            # switch and the margin guard still act - they made desired False.
            q = S
        elif desired:
            if self.state.on and self.state.target_qty > 0:
                q = self.state.target_qty
                month = time.strftime("%Y-%m", time.gmtime(now))
                if month != self.state.last_resize_month and notional > 0:
                    # recorded only once the pass completes (review MINOR-4:
                    # a failed resize order used to consume the month)
                    resize_month = month
                    if abs(q * px_s / notional - 1.0) > self.cfg.resize_drift:
                        q = notional / px_s
                        resized = True
            elif notional <= 0:
                q = S                     # held sleeve, size 0: keep it as is
            else:
                # OPEN toward the notional. dS = q - S, so whatever the account
                # already holds (a lost state file, a stub left by a partial
                # close) is counted, never bought on top (review MINOR-3:
                # adopting S here stuck an armed sleeve at a stub size)
                q = notional / px_s
            q = min(q, CARRY_MAX_NOTIONAL_USD / px_s)
        else:
            q = 0.0

        # ---- cross margin BEFORE any risk-adding order (review SERIOUS-1:
        # it ran after the spot buy, so a leverage failure stranded spot) ----
        # what to PERSIST as the target. HOLD and a blocked preflight change
        # this pass's orders, never the sleeve's intended size (re-review
        # MINOR-A/B: both wrote a stub size into target_qty for a month). An
        # adoption under HOLD persists 0, so the next armed pass OPENS.
        q_persist = q
        if armed is None:
            q_persist = self.state.target_qty if was_on else 0.0
        dS = q - S
        if dS * px_s >= MIN_ORDER_USD:
            # run in DRY_RUN too, so the rehearsal exercises it (NOTE-F)
            ok, pf_why = self.preflight_fn()
            if not ok:
                # adding spot is blocked; closes, reductions and the hedge of
                # what is already held still run
                self._event("RED", "open_blocked", pf_why, rate_limit=True)
                q = S
                dS = 0.0
        opening = (dS * px_s >= MIN_ORDER_USD
                   or (-S - P) * px_p <= -MIN_ORDER_USD)
        if opening and not self.cfg.dry_run and not self._cross_ok:
            self.venue.ensure_cross(self.cfg.cross_leverage)
            self._cross_ok = True

        # ---- spot leg toward the target ----
        if abs(dS) * px_s >= MIN_ORDER_USD:
            if dS > 0:
                self._order("spot", True, dS, px_s)
                sent += 1
            else:
                avail = max(0.0, S - v.get("spot_hold", 0.0))
                if avail * px_s >= MIN_ORDER_USD:
                    self._order("spot", False, min(-dS, avail), px_s)
                    sent += 1
                if avail + 1e-12 < -dS:
                    self._event("RED", "spot_locked",
                                f"{v.get('spot_hold', 0.0):.4f} UETH is held by a "
                                f"resting spot order - can only sell {avail:.4f} "
                                f"of {-dS:.4f}; cancel it on the HL UI",
                                rate_limit=True)
            if not self.cfg.dry_run:
                v = self._reread(v)
                S, P = v["spot_qty"], v["perp_qty"]

        # ---- perp leg hedges what spot ACTUALLY holds ----
        dP = -S - P
        if abs(dP) * px_p >= MIN_ORDER_USD:
            is_buy = dP > 0
            reduce_only = (is_buy and P < 0 and dP <= -P + 1e-12) or \
                          (not is_buy and P > 0 and -dP <= P + 1e-12)
            self._order("perp", is_buy, abs(dP), px_p, reduce_only=reduce_only)
            sent += 1
            if not self.cfg.dry_run:
                v = self._reread(v)
                S, P = v["spot_qty"], v["perp_qty"]

        # ---- state + pages (only on what the venue now confirms) ----
        if not self.cfg.dry_run:
            self.state.target_qty = q_persist
            now_on = desired and S * px_s >= MIN_ORDER_USD
            if resize_month:
                self.state.last_resize_month = resize_month
            if now_on and not was_on:
                self.state.opened_ts = int(self.clock())
                self.state.last_resize_month = time.strftime("%Y-%m", time.gmtime(self.clock()))
                liq_note = (f"; venue liquidation px {v.get('liq_px')}"
                            if v.get("liq_px") else "; venue reports no liquidation px")
                self._event("INFO", "opened" if sent else "adopted",
                            f"long {S:.4f} UETH / short {-P:.4f} ETH "
                            f"(~${S * px_s:,.0f}); {why}{liq_note}")
            elif was_on and not desired and S * px_s < MIN_ORDER_USD:
                self._event("INFO", "closed", f"sleeve flat (spot {S:.4f}, perp {P:.4f}); {why}")
            elif resized:
                self._event("INFO", "resized", f"target {q:.4f} UETH (~${q * px_s:,.0f})")
            self.state.on = now_on
            if not now_on:
                self.state.target_qty = 0.0 if not desired else q_persist
        self._check_hedge(v)

    def _reread(self, prev: dict) -> dict:
        try:
            v = self.venue.read()
            self.state.last_read = v
            return v
        except Exception as exc:  # noqa: BLE001
            self._event("RED", "venue_unreadable", f"re-read after an order failed: {exc}",
                        rate_limit=True)
            raise

    def _check_hedge(self, v: dict) -> None:
        gap_usd = abs(v["spot_qty"] + v["perp_qty"]) * max(v.get("perp_mid") or 0.0, 0.0)
        if gap_usd > HEDGE_TOL_USD:
            self.state.hedge_gap_polls += 1
            if self.state.hedge_gap_polls >= HEDGE_GAP_PAGE_POLLS:
                self._event("RED", "unhedged",
                            f"spot {v['spot_qty']:.4f} UETH vs perp {v['perp_qty']:.4f} "
                            f"ETH: ${gap_usd:,.0f} of naked exposure for "
                            f"{self.state.hedge_gap_polls} passes", rate_limit=True)
        else:
            self.state.hedge_gap_polls = 0

    # ---------- operator ----------

    def halt(self, reason: str) -> None:
        with self.lock:
            self.state.halted = reason or "MANUAL"
            self._event("RED", "halted", f"{self.state.halted}: no orders until /resume "
                        f"(legs are left as they are - hedged)")
            self._save()

    def resume(self) -> None:
        with self.lock:
            self.state.halted = None
            self._event("INFO", "resumed", "carry loop trading again")
            self._save()

    def pulse(self) -> dict:
        v = self.state.last_read or {}
        gap = None
        if v:
            gap = round(abs(v.get("spot_qty", 0.0) + v.get("perp_qty", 0.0))
                        * (v.get("perp_mid") or 0.0), 2)
        red = [e for e in self.state.events
               if e["level"] == "RED" and e["ts"] >= self.clock() - 86400]
        kinds: dict[str, int] = {}
        for e in red:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        return {"dry_run": bool(self.cfg.dry_run), "enabled": bool(self.cfg.carry_enabled),
                "on": self.state.on, "halted": self.state.halted,
                "spot_qty": v.get("spot_qty"), "perp_qty": v.get("perp_qty"),
                "hedge_gap_usd": gap, "signal": self.state.last_signal,
                # margin-guard latch (unix ts; 0 = none). /resume does NOT
                # lift it - the guard fired on the venue's own numbers
                "guard_until": self.state.guard_until or None,
                "last_step_ts": self.state.last_step_ts,
                "red_kinds_24h": kinds}
