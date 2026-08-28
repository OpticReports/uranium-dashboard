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
import threading
import os
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Protocol

logger = logging.getLogger(__name__)

BAR_SECONDS = 14_400
# RAMP v4 gate requirements that auto-drill must also respect. Single source
# of truth: main.py imports these, so the drill loop and the gate can never
# disagree about what "done" means (they did - auto-drill stopped at 3 cycles
# = 6 fills while slippage_sample needed 10, and reported "done").
DRILL_CYCLE_NEED = 3
SLIPPAGE_SAMPLE_NEED = 10
# A stop that keeps vanishing is a venue condition, not something to retry
# into: at poll_seconds=20 an unbounded replace loop placed 4,320 live orders
# and 4,320 pages per day (counter-agent 2026-08-24).
STOP_REPLACE_MAX = 3
# consecutive polls of a venue-CONFIRMED resting stop that clear the
# per-position failure count. ~20 polls is minutes, not months: long enough
# that a genuine accept-then-cancel storm never reaches it (every poll of a
# storm fails), short enough that isolated blips cannot accumulate across a
# multi-week position (re-gate 2026-08-27 N1).
STOP_OK_DECAY_POLLS = 20
# Hyperliquid agent (API) wallets expire on a date the venue tells us.
# Expiry is a TOTAL loss of write access, protective orders included, so the
# halt must fire while the key still WORKS - a halt at T-0 cannot flatten.
AGENT_WARN_DAYS = 14.0
AGENT_HALT_DAYS = 1.0
AGENT_CHECK_EVERY_S = 3600.0
AGENT_UNREADABLE_WARN_S = 6 * 3600.0
# Auto-drill's terminal condition is now a MEASUREMENT (live fill count) that
# drilling can fail to advance - e.g. the venue omits average_filled_price.
# Without this bound it drills the daily budget forever, unattended.
DRILL_NO_FILL_MAX = 3

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
    # Monotonic chase-attempt counter, persisted. The chase cloid used to be
    # deterministic per entry_ts, so the SECOND chase for the same engine
    # position (kill -> resume -> resume) re-used the first one's client
    # order id: Coinbase rejected it as a duplicate, the fill-watch then
    # polled the OLD order's FILLED status, and the ledger booked a fill
    # that never happened — the 2026-08-26 phantom position. Incremented
    # and persisted BEFORE the order is sent, so a crash between increment
    # and send burns a number instead of ever re-using one.
    chase_n: int = 0
    # Same counter, same reason, for PROTECTIVE STOPS (review of the first
    # hotfix cut, 2026-08-26): the stop cloid was still deterministic per
    # (entry_ts, trigger), so cancel-then-replace at an unchanged trail —
    # which is exactly what the boot reconcile and every kill->resume does —
    # re-sent a client order id the venue had already seen. Depending on the
    # venue's dup semantics that either leaves the position STOPLESS (reject)
    # or arms a stop mapped to a CANCELLED order (idempotent return): both
    # reproduce the incident's belief-vs-truth phenotype. Burned before
    # send, persisted, never reused.
    stop_n: int = 0
    # Same again for ENTRY orders (re-review 2026-08-26 binding 8): the
    # boot-mismatch resolution path re-sends an entry the venue already saw.
    entry_n: int = 0
    # entry_ts of an engine position whose protective stop FILLED on-venue.
    # While the engine (which only updates on 4h bar closes) keeps reporting
    # that position, case 1 must NOT re-enter from the stale entry order -
    # doing so resurrected a phantom ledger position and armed a live stop on
    # a flat venue (counter-agent find 2026-08-11, pre-existing FATAL class).
    stopped_entry_ts: int | None = None


@dataclass
class ExecState:
    legs: dict = field(default_factory=lambda: {n: LegLedger() for n in LEGS})
    # None | DAILY_LOSS | DRAWDOWN | KILL | LEDGER_DIVERGENCE |
    # STOP_UNPLACEABLE | VENUE_CHANGED | AGENT_EXPIRED  (AGENT_EXPIRED means
    # the signing key is about to stop working, so it fires at T-1 day while
    # the flatten can still execute; /resume alone does not fix it — a new
    # API wallet must be approved and HL_SECRET_KEY updated first.)
    # (all but DAILY_LOSS require a MANUAL
    # /resume regardless of KELLY_M. LEDGER_DIVERGENCE and STOP_UNPLACEABLE
    # are protection failures - the book stops because a position cannot be
    # kept protected. VENUE_CHANGED means the ledger describes a different
    # exchange, and is the only one /resume alone must never clear.)
    halted: str | None = None
    # unix ts of the last SUCCESSFUL venue position read. /pulse publishes
    # its age so an external monitor can see venue blindness — every other
    # /pulse field reads from the ledger, which is belief, not truth
    # (2026-08-26 incident: 3 days blind, nothing external could tell).
    last_venue_read_ts: int = 0
    # epoch seconds the signing key stops working (Hyperliquid agent
    # wallets expire). None = unknown yet, or a key that cannot expire.
    # Deliberately NOT persisted: a saved copy would outlive the fact.
    agent_valid_until: float | None = None
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
    # RAMP v4: event-class counters incremented INSIDE the real code paths
    # (never by hand) + the drill audit trail. See RAMP_V4.md.
    # `coverage` is the ALL-MODES total; `coverage_live` counts only events
    # produced with DRY_RUN=false. The ramp gate reads coverage_live ONLY:
    # a dry-run event exercises the state machine against DryRunVenue and
    # proves nothing about the venue, which is the entire point of the gate.
    # Counts persisted before this split have unknown provenance and stay
    # OUT of coverage_live (surfaced as `unattributed`, never silently
    # promoted).
    coverage: dict = field(default_factory=dict)
    coverage_live: dict = field(default_factory=dict)
    # counts promoted by a one-shot operator attestation rather than earned
    # under the guard. Kept SEPARATE forever: "attested live" is weaker
    # evidence than "observed live" and the matrix must keep saying so.
    coverage_attested: dict = field(default_factory=dict)
    # per-position stop-vanish counts ("leg:entry_ts" -> n). Persisted:
    # in-memory it reset on every restart, so under a crash-loop the
    # STOP_REPLACE_MAX bound never tripped and the 4,320-order storm it
    # exists to prevent came back (whole-chain counter-agent 2026-08-24).
    # Top-level, NOT a LegLedger field: older loaders cherry-pick keys, so
    # this stays rollback-safe.
    stop_vanish: dict = field(default_factory=dict)
    # WHICH VENUE this ledger belongs to. A ledger is a claim about
    # positions ON A SPECIFIC EXCHANGE; carrying it across a VENUE switch
    # would have the mirror believe it holds, on the new venue, whatever it
    # held on the old one - and would silently ABANDON the real position on
    # the old one. Recorded on first save, checked at every boot.
    venue: str | None = None
    attestation: dict | None = None
    # monotonic DRY_RUN flip counter. A safety invariant must NOT live in a
    # rotating buffer: the event log holds 200 entries and rate-limited
    # conditions fire every poll, so a mode_change ages out in ~67 minutes
    # of ordinary operation (counter-agent find 2026-08-21).
    mode_flips: int = 0
    # When durable witnessing began. Counts that already existed at that
    # moment are UNWITNESSED: mode_flips was not being recorded and fills
    # were not mode-tagged while they accrued, so no durable evidence about
    # them can ever exist. Attesting those requires explicit operator
    # acknowledgement (counter-agent A1: the first migration is precisely
    # the case the durable witnesses cannot cover).
    witnessing_since: int | None = None
    unwitnessed_coverage: dict = field(default_factory=dict)
    drills: list = field(default_factory=list)
    # auto-drill circuit breaker: reason string once ANY auto drill fails;
    # no further auto drills until a human clears it (manual /drill still
    # works). Never set by refusals - only by a drill that ran and failed.
    auto_drill_off: str | None = None


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
        # one-time backup of the pre-hotfix state file: this build adds
        # schema fields, and a rollback past it must have something to
        # restore (review of first hotfix cut, 2026-08-26)
        try:
            bak = f"{self.state_path}.pre-phantom-fix.bak"
            if os.path.exists(self.state_path) and not os.path.exists(bak):
                import shutil
                shutil.copyfile(self.state_path, bak)
        except Exception:  # noqa: BLE001
            pass
        self._breach_count = 0
        self._last_flat_equity = None      # transfer-reconciliation baseline
        self._fill_watch: list[dict] = []  # orders pending a fill-price read
        self._sent_at: dict[str, float] = {}   # per-kind Telegram cooldown
        # step() and drill() must never interleave venue mutations: a drill
        # mid-step (or vice versa) would trip the drift check and could
        # entangle drill orders with leg management (RAMP v4)
        self._venue_lock = threading.RLock()   # reentrant: halt() runs
        # inside _step_locked's _check_halts AND from the /kill API thread
        self._cov_since_boot: dict[str, int] = {}
        self._venue_read_failed_at = 0.0   # append-side cooldown for the RED
        self._boot_mismatch = False        # venue-vs-ledger unresolved at boot
        # agent-wallet expiry rail. 0 forces a check on the FIRST step of
        # every process, so a restart cannot postpone the warning; both are
        # in-memory because the answer is a venue fact, and a persisted copy
        # could only ever be a staler version of it.
        self._agent_checked_ts = 0.0
        self._agent_unreadable_since: float | None = None
        # live diagnostic (not persisted): why auto-drill last declined to
        # run. It used to `return  # quietly wait`, so "armed and waiting"
        # and "broken" were indistinguishable from outside.
        self._auto_drill_wait: str | None = None
        # consecutive fill-less drills. In-memory reset across restarts is
        # acceptable here: the cost is bounded by drill_max_per_day and
        # auto_drill_off persists once latched. The stop-vanish counter, by
        # contrast, lives in ExecState (a restart must not re-arm the
        # replacement loop - counter-agent 2026-08-24).
        self._drill_no_fill: int = 0
        # in-memory per-position count of consecutive confirmed-resting stop
        # observations; feeds _decay_stop_vanish. Not persisted: a restart
        # only makes the decay SLOWER, never the cap weaker.
        self._stop_ok_polls: dict[str, int] = {}
        self._stamp_witnessing()
        self._check_dry_run_flip()
        self._migrate_ledger_granularity()
        self._warn_unattributed_coverage()
        self._void_absurd_fills()
        self._check_venue_continuity()
        self._check_product_tradable()
        self._reconcile_boot()
        if any(l.qty != 0.0 for l in self.state.legs.values()):
            self._cov("restart_with_position")

    def _check_venue_continuity(self) -> None:
        """A ledger belongs to ONE exchange. Refuse to run it against another.

        The ledger is a claim about positions on a specific venue. Carried
        across a VENUE switch it would make the mirror believe it holds, on
        the NEW venue, whatever it held on the old one - and boot reconcile
        would then "helpfully" resolve the difference: a real Coinbase
        position silently abandoned, or a phantom one adopted onto
        Hyperliquid. Neither is recoverable by anything downstream, because
        every later check compares the ledger against the WRONG exchange.

        So: stamp the venue on first save, and on any later boot where it
        disagrees, HALT before _reconcile_boot can touch anything. Clearing
        it is deliberately manual - flatten on the old venue, confirm it,
        then start the new one from a clean state file."""
        cur = str(getattr(self.cfg, "venue", "coinbase") or "coinbase").lower()
        prev = getattr(self.state, "venue", None)
        if prev is None:
            # UNSTAMPED = written before this field existed, and the only
            # venue that existed then was Coinbase. Adopting `cur` here would
            # silently bless a Coinbase ledger as Hyperliquid's on the very
            # first boot after VENUE is switched - which is exactly the
            # deploy this guard is for (2026-08-28: VENUE=hyperliquid was set
            # in Render while the state file was still Coinbase's).
            prev = "coinbase"
        if prev == cur:
            self.state.venue = cur
            return
        held = {n: l.qty for n, l in self.state.legs.items() if l.qty != 0.0}
        refs = {n: l.stop_cloid or l.entry_cloid
                for n, l in self.state.legs.items()
                if l.stop_cloid or l.entry_cloid}
        if not held and not refs:
            # An EMPTY ledger carries nothing across. The danger is
            # positions and order refs that mean something on the old venue
            # and nothing on the new one; with neither, a switch is clean and
            # halting would be pure friction on an operator who did the right
            # thing (flatten first, then switch).
            self.state.venue = cur
            self._event("WARN", "venue_switched",
                        f"venue {prev} -> {cur} with an EMPTY ledger (no "
                        f"positions, no order refs) - adopted cleanly. "
                        f"Confirm {prev.upper()} really is flat and has no "
                        f"resting orders; this check reads the LEDGER, not "
                        f"the old venue.")
            self._save_state()
            return
        self._event("RED", "venue_changed",
                    f"state file belongs to venue '{prev}' but VENUE is now "
                    f"'{cur}'. Ledger positions {held or 'none'} and order "
                    f"refs {refs or 'none'} refer to {prev.upper()} and mean "
                    f"NOTHING on {cur.upper()}. Halting before boot reconcile "
                    f"can adopt or abandon anything.")
        self.state.halted = "VENUE_CHANGED"
        self._save_state()

    def _check_product_tradable(self) -> None:
        """Boot page when the CONFIGURED product cannot actually trade.

        A view_only or trading_disabled product passes the meta call in
        CoinbaseVenue.__init__ fine, so the executor booted "ready" into a
        book where every placement would be rejected one order at a time —
        which for a protective stop is the naked-position phenotype again,
        discovered only when protection was already owed (2026-08-27
        finding, from the live product-config diagnosis). DryRunVenue wraps
        the real venue, so flags are read through `inner` when present."""
        flags = (getattr(self.venue, "product_flags", None)
                 or getattr(getattr(self.venue, "inner", None),
                            "product_flags", None))
        if not flags:
            return
        if flags.get("view_only") or flags.get("trading_disabled"):
            why = " ".join(k for k in ("view_only", "trading_disabled")
                           if flags.get(k))
            self._event("RED", "product_untradable",
                        f"configured product is {why} on venue "
                        f"{flags.get('venue')} - every order will be "
                        f"rejected; fix CB_PRODUCT_ID before trusting any "
                        f"'ready' signal")

    def _check_agent_expiry(self) -> None:
        """Halt BEFORE the signing key dies, not after.

        A Hyperliquid agent wallet has a hard expiry (ours: 2027-02-24).
        Past it every order is rejected — entries AND stops — so a position
        open at expiry is naked, and the executor cannot flatten itself out
        of it because flattening is also an order. That is the phantom
        incident with a known date on it, which makes tolerating it a
        choice rather than an accident.

        So the halt fires at T-1 DAY, while the credentials still work and
        _halt_locked's flatten can actually execute. Warnings start at
        T-14 days so the renewal is routine rather than an emergency.

        Unreadable expiry is a WARN, never a halt: the info endpoint being
        down says nothing about whether our key can still sign, and halting
        a healthy book on a read failure would be self-inflicted damage of
        exactly the kind the halt exists to prevent. Venue-agnostic by duck
        type — Coinbase has no such method and is untouched. DryRunVenue
        wraps the real venue, so look through `inner` as well."""
        fn = (getattr(self.venue, "agent_valid_until", None)
              or getattr(getattr(self.venue, "inner", None),
                         "agent_valid_until", None))
        if fn is None:
            return
        now = time.time()
        if now - self._agent_checked_ts < AGENT_CHECK_EVERY_S:
            return
        self._agent_checked_ts = now
        try:
            vu = fn()
        except Exception as exc:  # noqa: BLE001
            if self._agent_unreadable_since is None:
                self._agent_unreadable_since = now
            blind = now - self._agent_unreadable_since
            if blind > AGENT_UNREADABLE_WARN_S:
                self._event("WARN", "agent_expiry_unreadable",
                            f"cannot read agent wallet expiry for "
                            f"{blind / 3600:.0f}h ({exc}) - the key may "
                            f"still sign fine, but the expiry rail is dark")
            return
        self._agent_unreadable_since = None
        self.state.agent_valid_until = vu
        if vu is None:                      # main-account key: never expires
            return
        days = (vu - now) / 86400.0
        if days <= AGENT_HALT_DAYS:
            # includes the revoked/not-approved case, which the adapter
            # reports as valid_until=0 (definitively expired, not unread).
            # Already halted: do NOT re-halt — _halt_locked flattens, and
            # re-running that hourly against a book someone is manually
            # working would fight the operator.
            if self.state.halted:
                return
            # A NOT-APPROVED key and an EXPIRING one both arrive here, but
            # they are different operator problems and the arithmetic alone
            # cannot tell them apart ("expires in -496648h" is a description
            # of the sentinel, not of the fault). The adapter names the
            # mismatch when it knows it; prefer that over the date.
            note = (getattr(self.venue, "agent_note", None)
                    or getattr(getattr(self.venue, "inner", None),
                               "agent_note", None))
            self._halt_locked(
                "AGENT_EXPIRED",
                note or (f"agent wallet expires in {days * 24:.1f}h - halting "
                         f"NOW while it can still cancel and flatten; approve "
                         f"a new API wallet, set HL_SECRET_KEY, then /resume"))
        elif days <= AGENT_WARN_DAYS:
            self._event("RED", "agent_expiring",
                        f"agent wallet expires in {days:.1f} days "
                        f"({time.strftime('%Y-%m-%d', time.gmtime(vu))}) - "
                        f"the executor HALTS at T-1 day; approve a new API "
                        f"wallet and update HL_SECRET_KEY before then")

    def _void_absurd_fills(self) -> None:
        """One-time hygiene at boot: a recorded |slip_bps| > 500 is not a
        fill measurement, it is a broken reference (2026-08-26: two chase
        fills carried 1320bps because ref_px was the engine's days-stale
        entry price — and one of them never happened at all). Void them so
        they stop gating the ramp, and keep them in the record for audit.
        HONESTY: voiding here does NOT clean the edge-monitor - barbell-lab
        ingests fills separately and its adapter must filter void rows and
        purge what it already ingested (tracked follow-up); until then its
        slip verdict is contaminated and must not authorize sizing."""
        changed = 0
        for f in (self.state.fills or []):
            if isinstance(f, dict) and not f.get("void") \
                    and abs(f.get("slip_bps") or 0) > 500:
                f["void"] = True
                changed += 1
        if changed:
            self._event("WARN", "fills_voided",
                        f"{changed} fill(s) with |slip|>500bps marked void "
                        f"(broken reference, not execution) - excluded from "
                        f"slippage sampling, kept for audit")
            self._save_state()

    def _reconcile_boot(self) -> None:
        """Venue-vs-ledger truth check at boot (2026-08-26 phantom incident:
        the ledger claimed a 0.01 BTC long for three days while the venue was
        flat, with a resting stop that would have OPENED a naked short).

        Rules, deliberately asymmetric:
        - read fails -> RED page, adopt nothing. The fixed position() only
          raises on genuine API failure now, so this is loud and rare.
        - venue FLAT while the ledger claims positions -> the position was
          closed outside our sight (external cancel/close, or a booked fill
          that never happened). Adopt the venue: zero the legs and clear the
          order refs. The normal mirror loop will then re-enter per the
          engine if it still wants the position - re-entering is CORRECT
          mirroring; believing you hold what you do not is the failure.
        - any OTHER mismatch (venue holds more/less/opposite) -> RED
          ACTION page only, adopt nothing: partial states are ambiguous and
          a wrong auto-fix at boot compounds silently. The operator decides.

        SKIPPED ENTIRELY on a VENUE_CHANGED halt. The ledger then describes
        a DIFFERENT exchange, so every rule above would compare it against
        the wrong venue and "resolve" the difference by abandoning a real
        position or adopting a phantom one.
        Runs only against a real venue (dry-run venues simulate fills).
        """
        if getattr(self.venue, "log", None) is not None:
            return
        if self.state.halted == "VENUE_CHANGED":
            return          # the ledger describes another exchange entirely
        ledger_net = sum(l.qty for l in self.state.legs.values())
        net = None
        for attempt in range(3):       # one boot-time blip must not disarm
            try:                       # BOTH the mismatch block and the
                net = self.venue.position()   # phantom-clear (re-review)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    self._event("RED", "venue_read_failed",
                                f"boot reconcile blind: {exc}")
                    return
                time.sleep(2)
        self.state.last_venue_read_ts = int(time.time())
        if abs(ledger_net) < 1e-12:
            # Review of the first cut: this side was never checked. A crash
            # after an order was sent but before the ledger booked it mints
            # exactly this state, and blindly re-entering on top of it
            # doubles the venue position. Adopt nothing, page, and block new
            # entries until the mismatch is resolved.
            if abs(net) > 1e-9:
                self._boot_mismatch = True
                self._event("RED", "position_drift",
                            f"boot: venue holds {net:.5f} BTC but the ledger "
                            f"is FLAT - NOT auto-fixed; new entries BLOCKED "
                            f"until this reconciles. Verify on Coinbase.")
            return
        if abs(net) < 1e-9:
            for name, l in self.state.legs.items():
                if l.qty == 0.0:
                    continue
                self._event("RED", "phantom_position_cleared",
                            f"{name}: ledger claimed {l.qty} BTC but the "
                            f"venue is FLAT - adopting venue truth. Any "
                            f"resting stop for this leg is being cancelled; "
                            f"the mirror will re-enter if the engine still "
                            f"holds the position.")
                if l.stop_cloid:
                    try:
                        self.venue.cancel(l.stop_cloid)
                    except Exception:  # noqa: BLE001
                        pass
                l.qty = 0.0
                l.entry_cloid = l.stop_cloid = None
                l.stop_px = None
                l.entry_side, l.entry_qty = None, 0.0
            self._save_state()
        elif abs(net - ledger_net) > 1e-9:
            self._event("RED", "position_drift",
                        f"boot: venue={net:.5f} ledger={ledger_net:.5f} BTC "
                        f"- NOT auto-fixed (ambiguous); verify on Coinbase")

    def attest_coverage(self, note: str = "",
                        acknowledge_unwitnessed: bool = False) -> dict:
        """ONE-SHOT operator attestation: promote pre-split coverage counts
        to live-attributed (RAMP_V4.md).

        A deliberate hole in the mode guard, so every bound is enforced here
        and none is operator-overridable. The bounds read DURABLE state, not
        the event log: the log holds 200 entries and rotates in ~67 minutes
        of ordinary operation, so a flip-detection check that only scanned
        events self-cleared on a timer (counter-agent 2026-08-21, FATAL).
        """
        if not self._venue_lock.acquire(timeout=30):
            return {"ok": False, "refused": "executor busy (step running)"}
        try:
            return self._attest_locked(note, acknowledge_unwitnessed)
        finally:
            self._venue_lock.release()

    def _attest_locked(self, note: str, ack_unwitnessed: bool = False) -> dict:
        st = self.state
        if getattr(st, "attestation", None) is not None:
            return {"ok": False, "refused": "already_attributed",
                    "detail": "attestation is one-shot and cannot top up "
                              "later evidence",
                    "attested_at": st.attestation.get("ts")}
        cov = dict(getattr(st, "coverage", None) or {})
        live = dict(getattr(st, "coverage_live", None) or {})
        if not cov:
            return {"ok": False, "refused": "nothing_to_attest"}
        if not self._is_live():
            return {"ok": False, "refused": "not_live",
                    "detail": "executor is in DRY_RUN (or on a shadow "
                              "venue); cannot attest live provenance"}
        # --- durable flip witnesses (none of these rotate) ---------------
        if getattr(st, "mode_flips", 0):
            return {"ok": False, "refused": "mode_flips_recorded",
                    "detail": f"{st.mode_flips} DRY_RUN flip(s) recorded: a "
                              f"window of unknown mode existed and counts "
                              f"carry no timestamps. Re-earn live."}
        if any(isinstance(f, dict) and f.get("live") is False
               for f in (getattr(st, "fills", None) or [])):
            return {"ok": False, "refused": "dryrun_fills_in_state",
                    "detail": "state contains fills recorded against a "
                              "shadow venue - this executor has run in "
                              "DRY_RUN since the counts began"}
        flips = [e for e in (st.events or [])
                 if e.get("kind") == "mode_change"]
        if flips:
            return {"ok": False, "refused": "mode_change_in_log",
                    "detail": "DRY_RUN flip(s) in the retained log",
                    "flips": [e.get("msg", "")[:160] for e in flips[-5:]]}
        # Live counts from a PRIOR process mean this is no longer the
        # migration boot - attesting then would grant the unattributed
        # delta accrued since. Counts from THIS process are fine: an open
        # position at deploy fires _cov("restart_with_position") inside
        # __init__, before the operator can call (counter-agent A5).
        since_boot = getattr(self, "_cov_since_boot", None) or {}
        stale = {k: v for k, v in live.items() if v > since_boot.get(k, 0)}
        if stale:
            return {"ok": False, "refused": "live_evidence_predates_call",
                    "detail": "coverage_live holds counts from an earlier "
                              "process; the provenance migration window has "
                              "passed",
                    "rows": sorted(stale)}

        def _pos_int(v):
            return v if isinstance(v, int) and v > 0 else 0

        promote = {k: _pos_int(v) for k, v in cov.items() if _pos_int(v)}
        # only the DELTA is attested; anything already observed live this
        # boot stays observed
        attested = {k: v - live.get(k, 0) for k, v in promote.items()
                    if v - live.get(k, 0) > 0}
        n = sum(attested.values())
        if not n:
            return {"ok": False, "refused": "nothing_to_attest"}
        unwit = {k: v for k, v in attested.items()
                 if k in (getattr(st, "unwitnessed_coverage", None) or {})}
        if unwit and not ack_unwitnessed:
            return {"ok": False,
                    "refused": "unwitnessed_history_requires_acknowledgement",
                    "detail": "these counts accrued BEFORE durable "
                              "witnessing began: mode_flips was not tracked "
                              "and fills were not mode-tagged while they "
                              "were earned, so no durable evidence about "
                              "them can exist. The refusals above cannot "
                              "see that period. Re-send with "
                              "acknowledge_unwitnessed=true only if you can "
                              "personally attest DRY_RUN was false "
                              "throughout; the acknowledgement is recorded "
                              "permanently.",
                    "unwitnessed_rows": sorted(unwit),
                    "witnessing_since": getattr(st, "witnessing_since", None)}
        limitation = ("event log retains 200 entries; durable witnesses "
                      "(mode_flips, dry-run fill tags) only cover the period "
                      "since witnessing_since - counts older than that rest "
                      "on the operator's acknowledgement, not on evidence")
        snap = (dict(live), dict(getattr(st, "coverage_attested", None) or {}),
                getattr(st, "attestation", None))
        st.coverage_live = {k: max(promote.get(k, 0), live.get(k, 0))
                            for k in set(promote) | set(live)}
        st.coverage_attested = attested
        st.attestation = {"ts": int(time.time()), "events": n,
                          "rows": sorted(attested), "note": note[:200],
                          "limitation": limitation,
                          "unwitnessed_rows": sorted(unwit),
                          "operator_acknowledged_unwitnessed": bool(unwit)}
        try:
            self._save_state()
        except Exception as exc:  # noqa: BLE001
            # never burn the one-shot in memory only
            st.coverage_live, st.coverage_attested, st.attestation = snap
            return {"ok": False, "refused": f"persist_failed:{exc}",
                    "detail": "attestation rolled back; safe to retry"}
        self._event("WARN", "coverage_attested",
                    f"operator attested {n} pre-split coverage events as "
                    f"live across {len(attested)} rows - these rows now "
                    f"satisfy the ramp gate on ATTESTED, not observed, "
                    f"evidence" + (f" (note: {note[:120]})" if note else ""))
        return {"ok": True, "attested_events": n, "rows": sorted(attested),
                "basis": "no DRY_RUN flip recorded (durable counter), no "
                         "dry-run fills in state, executor live at "
                         "attestation time",
                "limitation": limitation,
                "still_required": "attestation cannot satisfy "
                                  "slippage_sample: 10 genuinely live fills "
                                  "are still needed to complete the matrix"}

    def _warn_unattributed_coverage(self) -> None:
        """Pre-split counts have no provenance, so the ramp matrix drops to
        0/13 on the deploy that introduces the mode guard. Every other
        surprising transition here pages; this one must too, or it reads as
        data loss to whoever is watching (counter-agent find 2026-08-21)."""
        cov = getattr(self.state, "coverage", None) or {}
        live = getattr(self.state, "coverage_live", None) or {}
        if not cov or live:
            return
        n = sum(v for v in cov.values() if isinstance(v, int))
        self._event("WARN", "coverage_provenance_reset",
                    f"{n} pre-split coverage events carry no DRY_RUN "
                    f"provenance and are now UNATTRIBUTED - the ramp matrix "
                    f"reads 0 until they are re-earned live. This is not "
                    f"data loss: the totals remain in /status.coverage")

    def _is_live(self) -> bool:
        """Is evidence produced right now real venue evidence?

        Belt AND suspenders: the flag says "live", the venue object proves
        it. _build_executor raises rather than demoting a live account to
        DryRunVenue, but that invariant lives in another module - if it ever
        regresses, live-tagged evidence must NOT accrue against a shadow
        book (counter-agent find 2026-08-21).
        """
        return (not bool(getattr(self.cfg, "dry_run", True))
                and type(self.venue).__name__ != "DryRunVenue")

    def _cov(self, key: str) -> None:
        """RAMP v4 coverage counter (RAMP_V4.md) — persisted with state.

        Counted twice: once in the all-modes total, and — only when
        DRY_RUN is false — once in coverage_live, which is what the ramp
        gate actually reads. Without this split a full coverage matrix
        could be accumulated against DryRunVenue, reporting
        `coverage_complete: true` having never touched Coinbase. The
        2026-08-10 blueprint sync (DRY_RUN silently reset to true on a
        live account) is exactly the flip that would produce it.
        """
        cov = getattr(self.state, "coverage", None)
        if cov is None:
            cov = self.state.coverage = {}
        cov[key] = cov.get(key, 0) + 1
        if not self._is_live():
            return
        live = getattr(self.state, "coverage_live", None)
        if live is None:
            live = self.state.coverage_live = {}
        live[key] = live.get(key, 0) + 1
        sb = getattr(self, "_cov_since_boot", None)
        if sb is not None:
            sb[key] = sb.get(key, 0) + 1

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
                               "high_water", "venue") if k in raw})
            # Filter unknown keys: a state file written by a NEWER build
            # carries fields this LegLedger lacks, and the bare except below
            # would discard the entire state - un-halting a killed executor
            # and zeroing the ledger under a live position (counter-agent
            # 2026-08-24). Forward-compatible by construction.
            _fields = set(LegLedger.__dataclass_fields__)
            st.legs = {}
            for n in LEGS:
                raw_leg = raw.get("legs", {}).get(n, {}) or {}
                extra = set(raw_leg) - _fields
                if extra:
                    logger.warning("state leg %s: dropping unknown keys %s",
                                   n, sorted(extra))
                st.legs[n] = LegLedger(**{k: v for k, v in raw_leg.items()
                                          if k in _fields})
            st.events = raw.get("events", [])[-200:]
            st.marks = raw.get("marks", [])[-400:]
            st.fills = raw.get("fills", [])[-400:]
            st.last_dry_run = raw.get("last_dry_run")
            st.last_config = raw.get("last_config")
            st.coverage = raw.get("coverage", {})
            # absent on state written before the mode split -> stays empty,
            # so pre-split counts read as unattributed rather than live
            st.coverage_live = raw.get("coverage_live", {})
            st.coverage_attested = raw.get("coverage_attested", {})
            st.stop_vanish = raw.get("stop_vanish", {}) \
                if isinstance(raw.get("stop_vanish"), dict) else {}
            st.attestation = raw.get("attestation")
            st.mode_flips = raw.get("mode_flips", 0)
            st.witnessing_since = raw.get("witnessing_since")
            st.unwitnessed_coverage = raw.get("unwitnessed_coverage", {})
            st.drills = raw.get("drills", [])[-50:]
            st.auto_drill_off = raw.get("auto_drill_off")
            st.last_venue_read_ts = raw.get("last_venue_read_ts", 0)
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
             "last_config": getattr(self.state, "last_config", None),
             "coverage": getattr(self.state, "coverage", {}),
             "coverage_live": getattr(self.state, "coverage_live", {}),
             "coverage_attested": getattr(self.state, "coverage_attested", {}),
             "stop_vanish": getattr(self.state, "stop_vanish", {}),
             "venue": getattr(self.state, "venue", None),
             "attestation": getattr(self.state, "attestation", None),
             "mode_flips": getattr(self.state, "mode_flips", 0),
             "witnessing_since": getattr(self.state, "witnessing_since", None),
             "unwitnessed_coverage": getattr(self.state,
                                             "unwitnessed_coverage", {}),
             "drills": getattr(self.state, "drills", [])[-50:],
             "auto_drill_off": getattr(self.state, "auto_drill_off", None),
             "last_venue_read_ts": getattr(self.state,
                                           "last_venue_read_ts", 0)}
        # per-thread tmp: a shared tmp path was safe only while every writer
        # sat behind _venue_lock (counter-agent 2026-08-21). Auto-drill adds
        # another writer, so this matters more, not less.
        tmp = f"{self.state_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        json.dump(d, open(tmp, "w"))
        os.replace(tmp, self.state_path)

    def _ostat(self, cloid: str, retry: bool = True) -> str:
        """Order status as a 4-state string: OPEN | FILLED | CANCELLED |
        UNKNOWN. UNKNOWN (API error or no handle) is retried once — a single
        429/timeout must never be read as a terminal state (re-review
        2026-08-26: every verification site was collapsing unknown into
        whichever answer let it proceed)."""
        st = self.venue.order_status(cloid)
        stat = (st or {}).get("status", "UNKNOWN") if st else "UNKNOWN"
        if stat == "UNKNOWN" and retry:
            time.sleep(1)
            st = self.venue.order_status(cloid)
            stat = (st or {}).get("status", "UNKNOWN") if st else "UNKNOWN"
        return stat

    def _event(self, level: str, kind: str, msg: str) -> None:
        last = self.state.events[-1] if self.state.events else None
        # dedupe only SPAM: identical kind+msg within 10 minutes. An
        # unconditional match muted every cooldown-spaced RED after the
        # first (venue_read_failed, leg_sync_error) - one page per multi-day
        # blindness spell (review of first hotfix cut, 2026-08-26).
        if last and last["kind"] == kind and last["msg"] == msg \
                and time.time() - last.get("ts", 0) < 600:
            return
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
            "venue_changed": "the state file was written by a DIFFERENT "
                             "venue. Its ledger positions and order refs "
                             "mean nothing here. Flatten and cancel on the "
                             "OLD venue, confirm it is empty, then start "
                             "this one from a clean state file (delete "
                             "executor_state.json) - do NOT /resume into a "
                             "ledger that describes another exchange",
            "product_untradable": "CB_PRODUCT_ID points at a product this "
                                  "key cannot trade (view_only/disabled) - "
                                  "every order will be rejected. Check "
                                  "/status venue_products for the entry "
                                  "marked (configured) and fix the Render "
                                  "env var",
            "stop_ref_unverified": "a /resume found a stop the venue would "
                                   "not confirm AND could not read the "
                                   "position - open Coinbase, confirm the "
                                   "stop is really resting against the "
                                   "position, and place one manually if it "
                                   "is not; the executor deliberately did "
                                   "NOT re-place it blind",
            "entry_unconfirmed": "an entry order could not be verified - "
                                 "check Coinbase OPEN ORDERS for the cloid "
                                 "named above if this repeats; the ref is "
                                 "kept so the executor will not re-send",
            "config_change": "sizing/risk config changed - if this was you "
                             "(ramp step, base change), ignore; if NOT, a "
                             "sync or fat-finger altered live risk limits - "
                             "check the Render env vars now",
            # Someone with the exec token promoted unverified evidence into
            # the scaling gate. Same shape as config_change: harmless if it
            # was you, serious if it was not.
            "coverage_attested": "if this was you, ignore; if NOT, someone "
                                 "with the exec token promoted unverified "
                                 "evidence into the ramp gate - rotate "
                                 "EXEC_TOKEN and re-check /status.ramp_v4",
        }
        # Per-kind Telegram cooldown for conditions that persist across polls
        # (their msg embeds a changing float, so kind+msg dedupe never fires).
        # halt_config alone was ~180 pages/hour while equity sat below the
        # miscalibration line (counter-agent find 2026-08-11). Events are all
        # still LOGGED - only the phone pings are rate-limited. Halts, mode
        # changes and live-trade events are never suppressed.
        RATE_LIMITED = {"halt_config", "cap_clamp", "leg_sync_error",
                        "stop_unconfirmed", "entry_unconfirmed",
                        "stop_ref_cleared",
                        "position_drift", "entries_blocked", "sub_min_size",
                        # a persistent accept-then-cancel venue condition
                        # paged 4,320x/day before this (2026-08-24)
                        "stop_vanished"}
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
        elif kind in ("resume", "auto_rearm", "transfer_reconciled",
                      # the provenance reset was WARN-with-no-send-branch:
                      # logged, never phoned, i.e. silent exactly where the
                      # operator looks. That defeated its whole purpose.
                      "coverage_provenance_reset", "auto_drill_rearmed"):
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
                    self._verify_stop_refs()
                    # _verify_stop_refs can HALT (LEDGER_DIVERGENCE). Emitting
                    # the ✅ "cleared" page unconditionally put "cleared" and
                    # "halted" on the operator's phone in the same minute
                    # (re-gate 2026-08-26 N3).
                    if self.state.halted:
                        self._event("RED", "auto_rearm_blocked",
                                    f"DAILY_LOSS would have cleared at {day} "
                                    f"but stop-ref hygiene halted the book "
                                    f"({self.state.halted}) - it is NOT "
                                    f"resumed")
                    else:
                        self._event("INFO", "auto_rearm",
                                    f"DAILY_LOSS cleared at UTC day rollover "
                                    f"{day}")
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
        # /kill arrives on the API thread: serialize behind any in-flight
        # drill/step (referee: an unserialized kill mid-drill left a naked
        # short on a HALTED book, undetected until manual resume)
        with self._venue_lock:
            self._halt_locked(reason, msg)

    def _halt_locked(self, reason: str, msg: str = "") -> None:
        self._cov("halt")
        """Cancel everything, flatten everything, block until resume().

        HARDENED after the 2026-08-26 diagnosis (the worst finding of the
        incident): the old sequence was cancel_all -> position() -> flatten
        inside one try. With the position read broken, cancel_all SUCCEEDED
        and then position() raised — so the protective stop was already
        cancelled, no flatten was ever sent, and the halted flag blocked the
        step loop from ever re-placing anything. A halt on an unreadable
        venue stripped the position's only protection and left it naked.

        Invariant now: PROBE the venue BEFORE touching any order. If the
        position cannot be read, cancel NOTHING — the resting stop stays
        alive, trading still stops (halted is set), and the operator is
        paged to flatten manually. Only a successful probe may proceed to
        cancel; the flatten then works off a SECOND read taken after the
        cancels, never off the ledger (a blind market close against a wrong
        ledger can open a reverse naked position).
        """
        self.state.halted = reason
        self._event("RED", "halt", f"{reason} {msg}")
        try:
            self.venue.position()          # probe: readable at all?
        except Exception as exc:  # noqa: BLE001
            self._event("RED", "halt_blind",
                        f"halt requested but the venue position is "
                        f"UNREADABLE ({exc}) - no orders were cancelled, "
                        f"the protective stop is still resting. Flatten "
                        f"and cancel MANUALLY on Coinbase, then /resume.")
            self._save_state()
            return
        try:
            self.venue.cancel_all()
            # FLATTEN BEFORE VERIFYING (re-gate 2026-08-27 B3). The terminal
            # verify used to run FIRST and raise, which meant a venue where
            # cancel_all WORKS but order_status reads UNKNOWN - the exact
            # 2026-08-26 shape - had its orders stripped and then never got
            # flattened: 0.34 BTC live, unprotected, un-flattened, behind a
            # halt that blocks re-placement. Causation was confirmed by
            # mutation. Cancelling protection and then declining to close
            # the position is the worst of both; the flatten is the whole
            # point of a halt and must not be hostage to a read.
            net = None                     # re-read AFTER cancels, with retry:
            for attempt in range(3):       # one transient must not strip the
                try:                       # stop and skip the flatten
                    net = self.venue.position()
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 2:
                        raise
                    time.sleep(2)
            if abs(net) > 1e-6:
                self.venue.place_market(_close_side(net), abs(net),
                                        f"halt-{int(time.time())}")
            # cancel_all is best-effort inside the adapter, so VERIFY: every
            # order the ledger believes in must be terminal before we zero
            # the refs - a silently-failed cancel would otherwise leave an
            # armed orphan stop on a flat, halted, unwatched book (review of
            # first hotfix cut, 2026-08-26). This now governs ONLY whether
            # the LEDGER is zeroed; the flatten above has already happened.
            for name, l in self.state.legs.items():
                for cloid in (l.entry_cloid, l.stop_cloid):
                    if not cloid:
                        continue
                    stat = self._ostat(cloid)
                    if stat == "OPEN":
                        time.sleep(2)          # CANCEL_QUEUED settles
                        stat = self._ostat(cloid)
                    if stat in ("OPEN", "UNKNOWN"):
                        # UNKNOWN raises too: an order we CANNOT VERIFY
                        # terminal must be treated as possibly armed - a
                        # correlated outage broke cancel_all and this read
                        # together, and the old check passed vacuously,
                        # zeroing refs past a live orphan stop (re-review
                        # 2026-08-26)
                        raise RuntimeError(
                            f"{name} order {cloid} not confirmed terminal "
                            f"after cancel_all (status={stat}) - flatten was "
                            f"sent; NOT zeroing the ledger")
            for l in self.state.legs.values():
                l.qty = 0.0
                l.entry_cloid = l.stop_cloid = None
                # stop_px MUST die with the order (live find 2026-08-23):
                # leaving it set made _maintain_stop's churn guard read the
                # stale price as "the stop is already where it belongs" and
                # return without placing anything. After /kill -> /resume the
                # leg re-entered and sat UNPROTECTED, with the ledger
                # claiming a stop price that no venue order backed, until the
                # engine's trail happened to move >stop_replace_bps.
                l.stop_px = None
                l.entry_side, l.entry_qty = None, 0.0
        except Exception as exc:  # noqa: BLE001
            # Flatten FAILED: keep the ledger as-is - it is the only record
            # of what we believe we hold. Zeroing it here made the transfer
            # reconciler read a naked position's bleed as withdrawals
            # (counter-agent find 2026-08-11). halt_error already pages.
            self._event("RED", "halt_error", str(exc))
        self._save_state()

    def resume(self, adopt_venue: bool = False) -> bool:
        """Returns whether an adopt, if requested, actually happened."""
        with self._venue_lock:
            return self._resume_locked(adopt_venue)

    def _resume_locked(self, adopt_venue: bool = False) -> bool:
        # The outcome is plumbed back to /resume (re-gate 2026-08-27 N3):
        # the endpoint echoed the QUERY PARAMETER, so a refused adopt on a
        # blind venue returned a body byte-identical to a successful one -
        # concealing that the cancel-before-forget loop never ran, i.e. that
        # a stop the operator now believes is cancelled is still armed.
        if adopt_venue and not self._adopt_venue_locked():
            return False
        self._cov("resume")
        self._event("INFO", "resume", f"cleared {self.state.halted}")
        self.state.halted = None
        self._verify_stop_refs()
        # Re-arm the expiry rail IMMEDIATELY (2026-08-28, found on the first
        # live HL boot). The check is hourly, and boot had already spent this
        # process's slot — so a /resume landed in a window of up to an hour
        # with the rail asleep. In that window the book trades against a key
        # the venue will not accept: every order rejected one at a time, a
        # rejection storm instead of the one clean AGENT_EXPIRED halt the
        # operator was supposed to get. Re-checking here means /resume can
        # hand the halt straight back, which is the honest answer.
        self._agent_checked_ts = 0.0
        self._check_agent_expiry()
        self._save_state()
        return True

    def _adopt_venue_locked(self) -> bool:
        """Operator-invoked ledger reset to venue truth. Returns False if the
        venue could not be read (nothing is changed).

        WHY THIS EXISTS (re-gate 2026-08-26 N2): a halt whose flatten FAILED
        deliberately keeps the ledger - it is the only record of what we
        believe we hold - so the leg keeps its qty and a dead stop ref. Every
        subsequent /resume then re-ran _verify_stop_refs, found the same
        divergence, and halted LEDGER_DIVERGENCE again. Unrecoverable in
        band: even after the operator does exactly what the halt_error page
        told them to do (flatten manually on Coinbase), the ledger still
        claims the position, so /resume still deadlocks. The only escape was
        a redeploy, via _reconcile_boot.

        This is the SAME reconciliation _reconcile_boot performs, made
        reachable without a redeploy. It is deliberately NOT automatic: the
        whole point of keeping a divergent ledger is that a machine cannot
        tell "the venue is right and our belief is stale" from "the read is
        lying to us again". A human who has just looked at Coinbase can."""
        net = None
        for attempt in range(3):
            try:
                net = self.venue.position()
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    self._event("RED", "adopt_venue_blind",
                                f"adopt refused: the venue position is "
                                f"UNREADABLE ({type(exc).__name__}) - the "
                                f"ledger is unchanged and the halt stands")
                    self._save_state()
                    return False
                time.sleep(2)
        self.state.last_venue_read_ts = int(time.time())
        before = {n: l.qty for n, l in self.state.legs.items()}
        want = round(sum(before.values()), 8)
        if abs(net) <= 1e-9:
            # Cancel every stop we still believe in BEFORE zeroing the refs:
            # a ledger reset must not strand an armed order the ledger then
            # forgets about (that is how the trap stop survived the
            # incident). ONLY on the flat branch (re-gate 2026-08-27 B4):
            # cancelling unconditionally stripped the protection off a leg
            # whose qty then SURVIVED the partial branch below - the real
            # leg's only stop, killed by the repair.
            for name, l in self.state.legs.items():
                if l.stop_cloid:
                    try:
                        self.venue.cancel(l.stop_cloid)
                    except Exception:  # noqa: BLE001
                        self._event("WARN", "adopt_cancel_failed",
                                    f"{name} stop {l.stop_cloid} could not be "
                                    f"cancelled - CHECK COINBASE OPEN ORDERS")
            for l in self.state.legs.values():
                l.qty = 0.0
                l.entry_cloid = l.stop_cloid = l.entry_side = None
                l.entry_qty, l.stop_px = 0.0, None
            self._event("RED", "adopt_venue",
                        f"operator adopted venue truth: venue is FLAT, ledger "
                        f"claimed {before} (sum {want}) - all legs zeroed, "
                        f"stops cancelled")
        else:
            # The venue holds something the ledger cannot attribute to a
            # leg. Adopting a NUMBER without knowing whose it is would let
            # the mirror manage a position it never opened, so we refuse the
            # split and block entries exactly as boot does.
            # DO NOT UN-HALT (re-gate 2026-08-27 B4). Returning True here
            # cleared `halted` while the ledger still claimed an
            # unattributable position AND the refs had just been wiped -
            # so the next poll's _close_leg market-closed a leg the venue
            # did not hold and opened a naked, stopless position OUT OF A
            # FLAT VENUE, by the operator obeying this very message.
            # `_boot_mismatch` does not save us: it gates entries only, not
            # _maintain_stop or _close_leg. A divergent ledger and a running
            # book is the one combination that cannot be made safe, so the
            # halt stands until the venue is genuinely flat and adopt is run
            # again (the message already asks for exactly that).
            self._event("RED", "adopt_venue_partial",
                        f"operator adopted: venue holds {net} but the ledger "
                        f"claimed {before} (sum {want}) - the ledger cannot "
                        f"be attributed to legs, so the HALT STANDS and no "
                        f"stop was cancelled. Flatten manually on Coinbase, "
                        f"then run adopt again to go clean and resume.")
            self._boot_mismatch = True
            self._save_state()
            return False
        self._save_state()
        return True

    def _verify_stop_refs(self) -> None:
        """A halt that failed mid-way (halt_error / halt_blind) leaves stop
        refs the venue may no longer honour; the churn guard would then
        suppress re-placement against a dead order. Verify each ref; clear
        anything not confirmed working so the next step re-places under a
        fresh salt. UNKNOWN is CANCELLED-first-then-cleared - clearing a ref
        whose order might genuinely rest would arm a duplicate on re-place
        (re-review 2026-08-26 blocking find). Also runs on the DAILY_LOSS
        auto-rearm, which previously bypassed this hygiene entirely.

        CORROBORATED on legs the ledger believes HOLD (fusion gate
        2026-08-26): clearing the ref hands _maintain_stop a placement path,
        and place_stop is not reduce-only, so on a venue that is actually
        flat - precisely the state a failed halt leaves behind - that arms a
        full-size NAKED stop: the incident's own phenotype, re-created by
        its own repair. A held leg's ref is cleared only once the venue
        BACKS the ledger.

        ORDER MATTERS (re-gate 2026-08-26 B2). The cancel-on-UNKNOWN must
        come AFTER the decision to clear, never before it. Cancelling first
        meant that in a CORRELATED outage - status UNKNOWN *and* position
        unreadable, which is one API failure and is exactly what 2026-08-26
        looked like (reads down, writes up) - we sent the cancel and then
        kept the ref. That killed a live stop and went on believing in it,
        and the churn guard then suppressed replacement forever because a
        fixed ATR trigger never moves 5bps: a real position left
        permanently unprotected while /pulse reported it protected. Now the
        blind path touches nothing at all."""
        for name, l in self.state.legs.items():
            if not l.stop_cloid:
                continue
            stat = self._ostat(l.stop_cloid)
            if stat in ("OPEN", "FILLED"):
                continue
            if l.qty != 0.0:
                verdict, net, want = self._stop_backing()
                if verdict == "blind":
                    # Touch NOTHING: do not cancel protection we would then
                    # be unable to replace, and do not clear a ref whose
                    # order may genuinely rest.
                    self._event("RED", "stop_ref_unverified",
                                f"{name} stop {l.stop_cloid} not confirmed "
                                f"(status={stat}) and the venue position is "
                                f"UNREADABLE - left strictly alone (neither "
                                f"cancelled nor cleared); the position may "
                                f"be UNPROTECTED, verify on Coinbase")
                    continue
                if verdict == "diverged":
                    self._event("RED", "ledger_divergence",
                                f"{name} stop ref is dead and the venue does "
                                f"not back the ledger (venue net {net}, "
                                f"ledger sum {want}) - clearing would arm a "
                                f"NAKED stop, halting instead")
                    self.halt("LEDGER_DIVERGENCE",
                              f"{name}: venue net {net} vs ledger sum {want}")
                    return
            # Decided to clear. NOW the best-effort cancel is safe: an
            # UNKNOWN ref might still rest, and clearing it without
            # cancelling would arm a duplicate on the next placement.
            if stat == "UNKNOWN":
                try:
                    self.venue.cancel(l.stop_cloid)
                except Exception:  # noqa: BLE001
                    pass
            self._event("WARN", "stop_ref_cleared",
                        f"{name} stop {l.stop_cloid} not confirmed working "
                        f"(status={stat}) - cancelled best-effort and "
                        f"cleared; will re-place if needed")
            l.stop_cloid, l.stop_px = None, None

    # ---------- main step ----------

    def _stamp_witnessing(self) -> None:
        """Mark when durable provenance witnessing began, and freeze the
        counts that already existed at that instant. Stamped once, then
        persisted forever, so a restart cannot quietly convert unwitnessed
        history into witnessed history."""
        st = self.state
        if getattr(st, "witnessing_since", None) is not None:
            return
        st.witnessing_since = int(time.time())
        st.unwitnessed_coverage = dict(getattr(st, "coverage", None) or {})

    def _check_dry_run_flip(self) -> None:
        """A blueprint sync silently reset DRY_RUN to true on a LIVE account
        (2026-08-10) - the executor kept reporting healthy while placing
        nothing. Any mode flip pages the operator AND bumps the durable
        mode_flips counter.

        Called at __init__ as well as from step(): a flip that happens
        across a redeploy would otherwise never be recorded, because step()
        may not run before an operator acts (counter-agent 2026-08-21).
        """
        cur = bool(getattr(self.cfg, "dry_run", True))
        prev = getattr(self.state, "last_dry_run", None)
        if prev is not None and prev != cur:
            self.state.mode_flips = getattr(self.state, "mode_flips", 0) + 1
            self._event("RED", "mode_change",
                        f"DRY_RUN {prev} -> {cur}: trading is now "
                        f"{'SIMULATED (no real orders)' if cur else 'LIVE'} - "
                        f"verify this was intentional (a blueprint sync can "
                        f"reset it)")
        self.state.last_dry_run = cur

    def _check_mode_change(self) -> None:
        self._check_dry_run_flip()
        # Same incident class, other variables: a blueprint sync can reset any
        # literal-valued env silently (they are sync:false now, but belt AND
        # suspenders - a dashboard fat-finger pages too). Snapshot the whole
        # sizing config and page on ANY change (counter-agent find 2026-08-11).
        snap = {k: getattr(self.cfg, k, None) for k in
                ("kelly_m", "sizing_base_usd", "max_notional_usd",
                 "max_account_lev", "dd_halt_pct", "daily_loss_halt_pct",
                 "cb_product_id", "auto_drill")}
        prev_snap = getattr(self.state, "last_config", None)
        if prev_snap is not None and prev_snap != snap:
            diffs = [f"{k}: {prev_snap.get(k)} -> {v}"
                     for k, v in snap.items() if prev_snap.get(k) != v]
            self._event("RED", "config_change", "; ".join(diffs))
            self._cov("config_change")
        self.state.last_config = snap

    def step(self, target: dict) -> None:
        with self._venue_lock:
            self._step_locked(target)

    def _step_locked(self, target: dict) -> None:
        self._check_mode_change()
        equity = self.venue.equity()
        self._reconcile_transfers(equity)
        self._roll_day(equity)
        self._check_agent_expiry()
        self._check_halts(equity)
        if self.state.halted:
            self._save_state()
            return
        stale = (time.time() - (target.get("bar_ts") or 0)
                 > (self.cfg.stale_bars_max + 1) * BAR_SECONDS)
        entries_ok = not (stale or target.get("degraded")
                          or target.get("data_halt")
                          # boot found the venue holding what the ledger does
                          # not know about: no NEW risk until that resolves
                          or self._boot_mismatch)
        if not entries_ok:
            # RED: a stale/degraded engine feed silently stopping all entries
            # for days while /health stays green is the DRY_RUN-incident
            # phenotype (rate-limited to one ping per 30 min)
            self._event("RED", "entries_blocked",
                        f"stale={stale} degraded={target.get('degraded')} "
                        f"data_halt={target.get('data_halt')}")
        blend = target.get("blend", {})
        for leg in LEGS:
            # A halt can now fire MID-LOOP (_handle_stop_vanished halts on
            # ledger divergence / unplaceable stops). Without this check the
            # loop kept iterating: pullback halted and flattened the book,
            # then trend's _sync_leg saw qty==0 and RE-ENTERED AT MARKET on
            # the halted book in the same step - an open, unmanaged position
            # behind a halt page saying the book was flat (whole-chain
            # counter-agent 2026-08-24, CONFIRMED; missed by every per-change
            # review because their tests used the LAST leg in this order).
            if self.state.halted:
                break
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
        if self.state.halted:
            # same discipline as the top-of-step check: nothing places or
            # chases on a halted book; fill bookkeeping alone is safe
            self._poll_fill_watch()
            self._save_state()
            return
        self._report_post_only_crosses()
        self._poll_fill_watch()
        self._check_drift(equity)
        self._maybe_auto_drill(entries_ok)
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
                self._enter_from_fill(leg, led, pos, blend, equity,
                                      entries_ok)
            if led.qty != 0.0:
                self._maintain_stop(leg, led, pos)
            return

        # 2) no position; engine holds a pending entry
        if pend is not None:
            # Identity check FIRST. The trend leg fills at market and sets
            # led.qty immediately, but the engine keeps reporting `pending`
            # until its own next bar close. A qty check ahead of this one
            # read that as "engine flat but we still hold" and closed the
            # position on the very next poll — the trend leg could never
            # hold a position (live find, first trade 2026-08-10).
            # Identity is the SIGNAL, not the cloid string: entry cloids are
            # salted now (re-review 2026-08-26 binding 8), so the same
            # signal produces different ids across attempts.
            if led.entry_cloid and led.signal_ts == pend["signal_ts"]:
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
            led.entry_n += 1
            self._save_state()         # burn the salt BEFORE the order
            cloid = f"{leg[0].upper()}-{pend['signal_ts']}-E{led.entry_n}"
            if leg == "pullback":
                self.venue.place_limit(side, qty, pend["limit"], cloid,
                                       post_only=True)
                # BELIEF IS RECORDED BEFORE THE CONFIRM (round-3 review
                # BLOCKING find): returning on UNKNOWN without the ref let
                # the identity dedupe miss the live order and re-send full
                # size on every 20s poll - on a marketable limit that was a
                # real taker fill per poll, ledger booking nothing. An
                # unverifiable order is treated as POSSIBLY LIVE: keep the
                # ref (the dedupe then suppresses re-sends; the fill-watch
                # resolves it), and clear only on a venue-CONFIRMED
                # terminal-and-unfilled read.
                led.entry_cloid, led.entry_side = cloid, pend["side"]
                led.entry_qty, led.signal_ts = qty, pend["signal_ts"]
                stat = self._ostat(cloid)
                if stat == "CANCELLED":
                    # C1 (final gate): the RE-READ must itself be a venue-
                    # confirmed terminal-and-unfilled answer. A blipped
                    # re-read (UNKNOWN/None) has falsy filled_qty too, and
                    # clearing on it violated the very invariant this block
                    # exists for. Anything unconfirmed keeps the ref.
                    st_c = self.venue.order_status(cloid)
                    if (st_c or {}).get("status") == "CANCELLED" \
                            and not (st_c or {}).get("filled_qty"):
                        led.entry_cloid = led.entry_side = None
                        led.entry_qty = 0.0
                        self._event("RED", "entry_unconfirmed",
                                    f"{leg} entry {cloid} venue-confirmed "
                                    f"terminal and unfilled - will retry "
                                    f"while the signal stands")
                        return
                    stat = "UNKNOWN"
                if stat == "UNKNOWN":
                    self._event("RED", "entry_unconfirmed",
                                f"{leg} entry {cloid} unverifiable - ref "
                                f"KEPT as possibly live; verify the order "
                                f"under Coinbase open orders if this "
                                f"persists")
            else:
                self.venue.place_market(side, qty, cloid)
                led.qty = _side_sign(pend["side"]) * qty
                # trend's organic entry IS the market path - count it here
                # (referee 2026-08-15: _enter_from_fill never runs for trend)
                self._cov("entry_long" if pend["side"] == "L"
                          else "entry_short")
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
                         blend: dict, equity: float,
                         entries_ok: bool = True) -> None:
        """Engine position appeared. If our entry order (partially) missed,
        chase the remainder at market so the legs stay in sync.

        2026-08-26 hardening, three changes from the diagnosis:
        - sizing and the slippage reference use the venue mid at SEND time,
          not the engine's entry-bar price. The engine price can be days
          stale (the position it reports opened bars ago), which both
          oversized the chase and made `_leg_qty`'s notional/leverage caps
          admit proportionally more — and recorded 1320bps of fictitious
          "slippage" that poisoned the ramp gate's sample.
        - the chase cloid carries a persisted attempt counter (see
          LegLedger.chase_n) so it can never collide with a prior attempt.
        - a market chase is NEW RISK, so it obeys entries_ok: with the feed
          stale or degraded we book only what verifiably filled and do not
          buy more (the old code market-bought during blindness).
        """
        px_ref = self.venue.mid()
        want = self._leg_qty(leg, blend, px_ref, equity)
        filled = 0.0
        if led.entry_cloid:
            # When a real entry order exists, chase ITS shortfall — not a
            # re-target computed at the live mid, which on any adverse move
            # sent a spurious market top-up the old code never sent (review
            # of first hotfix cut, 2026-08-26). The mid stays the SLIPPAGE
            # reference; the entry order's own size is the quantity truth.
            if led.entry_qty and led.entry_qty > 0:
                want = min(want, led.entry_qty)
            st = self.venue.order_status(led.entry_cloid)
            filled = (st or {}).get("filled_qty", 0.0)
            if st and st.get("status") == "OPEN" and filled < want:
                self.venue.cancel(led.entry_cloid)
        # A remainder below one contract is NOT chaseable — the old code sent
        # it anyway and the venue rounded it up to a full contract, overshooting
        # the target (live find, 2026-08-10). Round the shortfall down and
        # accept the tracking error instead.
        missing = self.venue.quantize(max(0.0, round(want - filled, 8)))
        if missing > 0 and not entries_ok:
            self._event("RED", "entries_blocked",
                        f"{leg} chase of {missing} BTC suppressed: feed "
                        f"stale/degraded - will not add risk while blind")
            missing = 0.0
        if missing > 0:
            side = _order_side(pos["side"])
            led.chase_n += 1
            self._save_state()     # burn the number BEFORE the order exists
            cloid = f"{leg[0].upper()}-{pos['entry_ts']}-C{led.chase_n}"
            self.venue.place_market(side, missing, cloid)
            self._watch_fill(leg, "chase", cloid, px_ref, side)
            self._event("WARN", "entry_chase",
                        f"{leg} missed {missing} of {want} BTC - chased at market")
        # Record what the venue HOLDS (filled + whatever we could chase), not
        # the target. Anything else desynchronises stops and exits.
        led.qty = _side_sign(pos["side"]) * round(filled + missing, 8)
        if led.qty != 0.0:
            self._cov("entry_long" if pos["side"] == "L" else "entry_short")
        if missing > 0:
            self._cov("chase")
        led.entry_cloid = None
        led.signal_ts = pos.get("signal_ts")

    def _bump_stop_vanish(self, leg: str, pos: dict) -> int:
        """Failed stop-protection attempts on THIS position, keyed by
        entry_ts and pruned when the position changes.

        SHARED by the two paths that can each spin forever on their own
        (fusion gate 2026-08-26, BLOCKING): a stop the venue confirms and
        then kills, and a stop the venue never confirms at all. Only the
        first was bounded, so a venue that accepts-then-cancels inside the
        ~1s confirm window - or that simply reads UNKNOWN forever - produced
        one fresh salted placement per poll, 4,320/day, with no cap and no
        halt. One counter, one cap: whichever way protection keeps failing,
        it fails at most STOP_REPLACE_MAX times before STOP_UNPLACEABLE."""
        key = f"{leg}:{pos.get('entry_ts')}"
        sv = getattr(self.state, "stop_vanish", None)
        if sv is None:
            sv = self.state.stop_vanish = {}
        n = sv.get(key, 0) + 1
        sv[key] = n
        # bounded growth: keep only this position's key per leg
        for k in [k for k in sv if k.startswith(f"{leg}:") and k != key]:
            del sv[k]
        return n

    def _stop_vanish_n(self, leg: str, pos: dict) -> int:
        """Read the counter WITHOUT bumping. One poll may fail protection
        through both doors (the old stop vanished AND its replacement never
        confirmed); that is ONE failed attempt, not two. Double-bumping cut
        the effective allowance from 3 to 2 (re-gate 2026-08-26 N1)."""
        sv = getattr(self.state, "stop_vanish", None) or {}
        return sv.get(f"{leg}:{pos.get('entry_ts')}", 0)

    def _decay_stop_vanish(self, leg: str, pos: dict) -> None:
        """Forget failures a working stop has outlived.

        The reset on a confirmed PLACEMENT is unreachable for the pullback
        leg (re-gate 2026-08-27 N1): its engine stop is a fixed ATR level
        set once and never trailed, so the churn guard returns before any
        placement happens and `_clear_stop_vanish` never runs. Four isolated
        cancellations - each fully recovered, spread over hundreds of polls
        - therefore accumulated into a false STOP_UNPLACEABLE that
        force-flattened a healthy book (and the other leg with it).

        A cap on CONSECUTIVE failures is what the storm needs; unrelated
        failures months apart are not a storm. So a stop the venue confirms
        is resting, for STOP_OK_DECAY_POLLS in a row, clears the count."""
        key = f"{leg}:{pos.get('entry_ts')}"
        sv = getattr(self.state, "stop_vanish", None) or {}
        if not sv.get(key):
            self._stop_ok_polls.pop(key, None)
            return
        n = self._stop_ok_polls.get(key, 0) + 1
        self._stop_ok_polls[key] = n
        if n >= STOP_OK_DECAY_POLLS:
            sv.pop(key, None)
            self._stop_ok_polls.pop(key, None)
            self._event("INFO", "stop_vanish_decayed",
                        f"{leg} stop has rested confirmed for "
                        f"{STOP_OK_DECAY_POLLS} polls - clearing the failure "
                        f"count so isolated blips cannot accumulate")

    def _clear_stop_vanish(self, leg: str, pos: dict) -> None:
        """Reset after protection that actually WORKED, so isolated
        transients cannot accumulate into a halt across a long position
        (re-gate 2026-08-26 N1: four read blips spread over twenty healthy
        ratchets halted a winning trade out of a stop that was working).

        Called ONLY from the confirmed-placement path AND only when this
        poll did not itself record a failure. That second condition is what
        keeps the reset from re-opening the bug the counter exists for: in
        the accept-then-cancel storm EVERY poll vanishes and re-places, so
        every poll would otherwise reset and the cap would never trip."""
        sv = getattr(self.state, "stop_vanish", None) or {}
        sv.pop(f"{leg}:{pos.get('entry_ts')}", None)

    def _stop_backing(self) -> tuple[str, float, float]:
        """May we place a protective stop at all? -> (verdict, net, want)
        where verdict is "ok" | "diverged" | "blind".

        `place_stop` is NOT reduce-only on this venue, so a stop the venue
        cannot back OPENS a position instead of closing one. That is the
        entire 2026-08-26 incident, and it is why every placement path has
        to ask this question.

        AGGREGATE, not per-leg (re-gate 2026-08-26 B1): pullback and trend
        trade the SAME product, so `venue.position()` returns their NET.
        Comparing that net to ONE leg's qty was wrong in both directions —
        it false-halted an ordinary S3-long/S4-short book (net 0 read as
        "venue holds nothing"), and it let a phantom leg hide behind a real
        one (ledger 0.01 real + 0.01 phantom vs venue 0.01: same sign,
        non-zero, so it passed, and 0.02 of stops went out against 0.01 of
        position). Both reconcilers in this file already compare against the
        ledger SUM; this now matches them.

        The predicate: the venue must hold at least what the ledger claims,
        in the same direction.

        THE SURPLUS RELAXATION IS CONDITIONAL (re-gate 2026-08-27 B1). The
        earlier form said flatly "holding MORE is fine - a reduce-sized stop
        still reduces". That is FALSE whenever a leg's sign opposes the
        net, because the stop's side is _close_side(led.qty): it moves the
        net AWAY from zero, so it OPENS size instead of closing it. And the
        stop is sized abs(led.qty) - ONE leg - while this compares against
        the SUM, so on an opposite-signed book |leg| can exceed |sum| with
        nothing constraining it. Reproduced: venue +0.34 real, ledger
        {pullback +0.34, trend -0.14 phantom}, sum +0.20 -> "ok" -> a
        "protective" BUY stop armed 0.14 BTC (~$10k) of unmanaged long on
        trigger. That band has want != 0, so the DISCLOSED LIMIT below never
        covered it.

        So the relaxation applies ONLY when every non-zero leg shares the
        sum's sign. If any leg opposes, the venue must AGREE with the ledger
        within one contract - a surplus can no longer vouch for a leg
        pointing the other way.

        want == 0 IS NOT VACUOUSLY SAFE (same finding). The old early return
        skipped the check entirely in both directions: it masked net > 0,
        and `(want > 0)` being False at zero masked net < 0. A flat ledger
        against a venue holding anything is a contradiction like any other.

        DISCLOSED LIMIT (unchanged, and now the ONLY hole): on a netted
        venue a ledger whose legs cancel AND whose venue really is flat
        (pullback +0.01, trend -0.01, net 0) is indistinguishable from a
        wholly phantom ledger. Both read 0 and both pass. Per-leg stops on
        an opposite-side book therefore still rest on ledger belief alone -
        and firing one genuinely does open the other side. No position read
        can separate these; it needs the open-orders sweep (F1). Do not let
        EXECUTOR.md claim more than this."""
        legs = [l.qty for l in self.state.legs.values() if abs(l.qty) > 1e-9]
        want = round(sum(legs), 8)
        try:
            net = self.venue.position()
        except Exception:  # noqa: BLE001
            return "blind", 0.0, want
        self.state.last_venue_read_ts = int(time.time())
        # net and want are both whole multiples of the venue's contract size,
        # so agreement is exact up to float noise - no contract-width slack,
        # which would silently re-admit exactly the surplus this refuses.
        tol = 1e-9
        opposed = any((q > 0) != (want > 0) for q in legs) if want else bool(legs)
        if abs(want) <= 1e-9:
            # flat (or exactly cancelling) ledger: the venue must be flat too
            if abs(net) > tol:
                return "diverged", net, want
            return "ok", net, want
        if opposed:
            # no surplus credit: a leg pointing the other way is only backed
            # by the venue AGREEING with the ledger, not by exceeding it
            if abs(net - want) > tol:
                return "diverged", net, want
            return "ok", net, want
        if abs(net) + 1e-9 < abs(want) or (net > 0) != (want > 0):
            return "diverged", net, want
        return "ok", net, want

    def _handle_stop_vanished(self, leg: str, led: LegLedger, pos: dict,
                              st: dict | None) -> bool:
        """A venue stop reported CANCELLED/EXPIRED/FAILED. Returns False if
        the caller must stop (position consumed, halted, or unverifiable).

        Three things this must NOT do, each a counter-agent find:
        - re-arm the FULL size when the stop was partially filled before it
          died (Coinbase reports EXPIRED with filled_size > 0);
        - place a stop the venue cannot back: place_stop is NOT reduce-only,
          so replacing against a flat or opposite venue OPENS a position;
        - retry forever into a venue that keeps cancelling.
        """
        done = float((st or {}).get("filled_qty") or 0.0)
        led.stop_cloid, led.stop_px = None, None
        if done > 0:
            sgn = 1.0 if led.qty > 0 else -1.0
            led.qty = round(led.qty - sgn * min(done, abs(led.qty)), 8)
            # ramp evidence only when the fill fully consumed the leg: a
            # partial on a stop the venue KILLED is simultaneously evidence
            # the venue's stop handling misbehaved, and the row exists to
            # prove the clean fill path (counter-agent 2026-08-24 F3)
            if led.qty == 0.0:
                self._cov("stop_filled")
            self._event("RED", "stop_partial_fill",
                        f"{leg} stop died having filled {done} - ledger now "
                        f"{led.qty}; re-arming only the remainder")
        if led.qty == 0.0:
            led.stopped_entry_ts = pos.get("entry_ts")
            led.entry_cloid = led.entry_side = None
            led.entry_qty = 0.0
            return False
        n = self._bump_stop_vanish(leg, pos)
        # Backing is deliberately NOT checked here any more (re-gate
        # 2026-08-26 B1/B3). This door used its own copy of the per-leg
        # predicate and carried both of its bugs, and - worse - it is only
        # ONE of the ways execution reaches a placement: the trail-ratchet
        # path replaces stops without ever passing through here, which is
        # how three full-size naked stops went out against a flat venue with
        # position() raising on every call. The check now lives at the
        # single placement choke point in _maintain_stop that EVERY path
        # must cross. This function keeps only what is its own: partial-fill
        # accounting, the attempt counter, and the cap.
        if n > STOP_REPLACE_MAX:
            self._event("RED", "stop_unplaceable",
                        f"{leg} venue stop has vanished {n} times on this "
                        f"position - not retrying into it")
            self.halt("STOP_UNPLACEABLE", f"{leg} after {n} vanishes")
            return False
        self._event("RED", "stop_vanished",
                    f"{leg} venue stop was no longer working (position "
                    f"UNPROTECTED) - replacing, occurrence {n}")
        return True

    def _maintain_stop(self, leg: str, led: LegLedger, pos: dict) -> None:
        trigger = pos.get("stop")
        if not trigger or led.qty == 0.0:
            return
        bumped = False                      # this poll already counted a miss
        # Check for an on-venue stop FILL before the churn guard: the old
        # order hid a fired stop for as long as the trail moved < 5bp, then
        # the flat ledger + engine-still-reports-position window resurrected
        # the position from the stale entry order and armed a live stop on a
        # flat venue (counter-agent find 2026-08-11, reproduced end-to-end).
        if led.stop_cloid:
            st = self.venue.order_status(led.stop_cloid)
            status = (st or {}).get("status")
            # A stop no longer working at the venue is NOT protection, but the
            # ledger kept advertising it: only FILLED was handled, so a
            # CANCELLED/EXPIRED stop left stop_cloid set, the churn guard
            # suppressed the replacement, and /pulse still read
            # stop_placed=true. Self-repair needed a >5bp trail move, and the
            # chandelier only ratchets UP - silent exactly in a falling market
            # (found 2026-08-24, reproduced end-to-end).
            #
            # Only the venue's TERMINAL bucket counts: cb.order_status maps
            # QUEUED/PENDING/CANCEL_QUEUED to OPEN and returns None on an API
            # failure, and neither may ever provoke a duplicate stop.
            if status == "CANCELLED":
                if self._handle_stop_vanished(leg, led, pos, st) is False:
                    return
                bumped = True
            elif st and status == "FILLED":
                # protective stop fired on-venue; ledger goes flat, and
                # stopped_entry_ts blocks re-entry from this same engine
                # position until the engine catches up at its own stop logic
                self._event("INFO", "stop_filled_on_venue", f"{leg}")
                self._cov("stop_filled")
                led.qty, led.stop_cloid, led.stop_px = 0.0, None, None
                led.stopped_entry_ts = pos.get("entry_ts")
                # the entry order is consumed - its fill was closed BY the
                # stop. Trend keeps entry_cloid for the position's life, so
                # without this, case 3's orphan-flatten would re-close the
                # filled entry and open a naked reverse position.
                led.entry_cloid = led.entry_side = None
                led.entry_qty = 0.0
                return
            elif status == "OPEN":
                self._decay_stop_vanish(leg, pos)
        # The churn guard may only suppress a REPLACEMENT, never the first
        # placement: with no stop_cloid there is no venue order to churn, so
        # a stale stop_px must not be able to talk us out of protecting a
        # live position (live find 2026-08-23, /kill -> /resume).
        if led.stop_cloid and led.stop_px \
                and abs(trigger - led.stop_px) / led.stop_px \
                < self.cfg.stop_replace_bps / 10_000.0:
            return
        # ---- THE PLACEMENT CHOKE POINT (re-gate 2026-08-26 B1a/B3) -------
        # Every path that sends a stop passes through here: first placement,
        # trail-ratchet replacement, and post-vanish re-arm alike. It has to
        # be here rather than in _handle_stop_vanished, because that door
        # only opens on a literal "CANCELLED" status - a BLIND read returns
        # None/UNKNOWN, falls through to the churn guard, and once the
        # chandelier ratchets past stop_replace_bps (5bp of $74k is $37, which
        # a trend leg clears routinely) went straight to place_stop with no
        # position read at all. Reproduced: three full-size naked stops
        # against a flat venue with position() raising on every call.
        verdict, net, want = self._stop_backing()
        if verdict == "blind":
            self._event("RED", "stop_backing_blind",
                        f"{leg} needs a stop but the venue position is "
                        f"UNREADABLE - placing NOTHING (place_stop is not "
                        f"reduce-only, so a blind placement can OPEN a "
                        f"position); position may be UNPROTECTED, retrying "
                        f"next poll")
            return
        if verdict == "diverged":
            self._event("RED", "ledger_divergence",
                        f"{leg} needs a stop but the venue does not back the "
                        f"ledger (venue net {net}, ledger sum {want}) - "
                        f"placing would arm a NAKED stop, halting instead")
            self.halt("LEDGER_DIVERGENCE",
                      f"{leg}: venue net {net} vs ledger sum {want}")
            return
        # ------------------------------------------------------------------
        # Every attempt is salted with a PERSISTED burned-before-send counter
        # (this branch's review chain), which supersedes main's conditional
        # -R nonce: the id can never repeat, crash included, so the
        # dup-reject/idempotent-dedupe class is closed unconditionally.
        led.stop_n += 1
        self._save_state()                 # burn the number BEFORE the order
        cloid = f"{leg[0].upper()}-{pos['entry_ts']}-S{int(trigger)}-{led.stop_n}"
        if led.stop_cloid:
            self.venue.cancel(led.stop_cloid)
        self.venue.place_stop(_close_side(led.qty), abs(led.qty), trigger, cloid)
        # A protective stop the ledger BELIEVES in but the venue does not
        # hold is the incident's exact phenotype, so belief is set only
        # after the venue confirms the order is genuinely working. A venue
        # that deduped/rejected/failed the place leaves refs clear, pages,
        # and the next step retries under a fresh salt.
        stat = self._ostat(cloid)
        if stat not in ("OPEN", "FILLED"):
            # BOUNDED (fusion gate 2026-08-26): this branch used to return
            # unbounded. STOP_REPLACE_MAX only ever covered the
            # confirmed-then-vanished path, so the fast accept-then-cancel and
            # the persistent-UNKNOWN variants both re-placed forever - the
            # exact order storm the cap exists to stop, arriving through the
            # door the cap did not watch. Same counter, same cap, same halt.
            #
            # ONCE per poll (re-gate N1): if _handle_stop_vanished already
            # counted this poll, the replacement failing is the SAME failed
            # attempt, not a second one. Double-bumping cut the allowance
            # from 3 to 2.
            n = (self._stop_vanish_n(leg, pos) if bumped
                 else self._bump_stop_vanish(leg, pos))
            if n > STOP_REPLACE_MAX:
                self._event("RED", "stop_unplaceable",
                            f"{leg} stop placement has failed to confirm {n} "
                            f"times on this position - not retrying into it")
                # HALT WITH THE CLOID STILL IN THE LEDGER (re-gate B4).
                # _halt_locked verifies every LEDGER-known order is terminal
                # before it zeroes anything; clearing the refs first made
                # that loop vacuous, so when both cancel paths silently
                # failed - cb.cancel_all swallows every exception, and the
                # cancel below is try/except/pass - the halt flattened and
                # zeroed the ledger UNDER four armed SELL stops, on a flat
                # book, reporting success. This order may or may not be
                # live; handing it over is the only way the halt can find
                # out. Belief asymmetry is not violated: we are halting, and
                # _halt_locked either verifies it terminal or refuses to
                # zero and pages halt_error.
                led.stop_cloid, led.stop_px = cloid, trigger
                self.halt("STOP_UNPLACEABLE",
                          f"{leg} after {n} unconfirmed placements")
                return
            # CANCEL BEFORE CLEARING (re-review 2026-08-26 blocking find):
            # an UNKNOWN here can be a read blip over a stop that genuinely
            # rests. Clearing the ref without cancelling armed a SECOND
            # full-size stop on the next poll - both fill on trigger and
            # REVERSE the position. The write path tends to work while
            # reads are down, so a best-effort cancel caps stacking at
            # zero-or-one resting stop, never two.
            try:
                self.venue.cancel(cloid)
            except Exception:  # noqa: BLE001
                pass
            led.stop_cloid, led.stop_px = None, None
            self._event("RED", "stop_unconfirmed",
                        f"{leg} stop {cloid} not confirmed working "
                        f"(status={stat}) - cancelled best-effort; position "
                        f"may be UNPROTECTED; attempt {n}")
            return
        self._watch_fill(leg, "stop", cloid, trigger, _close_side(led.qty))
        led.stop_cloid, led.stop_px = cloid, trigger
        # Protection that WORKED resets the counter - but only if this poll
        # did not itself record a failure (re-gate N1). Without the reset,
        # four isolated read blips spread over twenty healthy ratchets
        # accumulated into a STOP_UNPLACEABLE halt that force-flattened a
        # winning position out of a stop that was working fine. Without the
        # `not bumped` condition the reset would instead re-open the bug the
        # counter exists for: in an accept-then-cancel storm every poll
        # vanishes AND re-places successfully, so every poll would reset and
        # the cap would never trip.
        if not bumped:
            self._clear_stop_vanish(leg, pos)
        self._cov("stop_placed")

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
        # NOTE (merge 2026-08-26): an earlier hotfix cut accidentally
        # duplicated the _maintain_stop CANCELLED-page block here via an
        # unanchored replace. Restored to the simple form: on a close we
        # cancel whatever ref exists and clear it - CANCELLED needs no page
        # here because the leg is being closed anyway, and FILLED means the
        # stop beat the signal exit.
        # DUST FIRST, before any venue question is asked. A residue the
        # venue cannot even represent is ledger noise, not a position, and
        # clearing it sends NO order - so it cannot open anything and must
        # not be able to trip the divergence halt below. (Regression caught
        # by test_gate_close_dust_cleared_not_looped: 0.004 BTC of unholdable
        # dust against a flat venue is numerically a mismatch, and halting
        # the whole book over it would be a false halt on sub-contract noise.)
        if led.qty != 0.0:
            try:
                holdable = self.venue.quantize(abs(led.qty))
            except Exception:  # noqa: BLE001
                holdable = abs(led.qty)
            if holdable <= 0.0:
                if led.stop_cloid:
                    try:
                        self.venue.cancel(led.stop_cloid)
                    except Exception:  # noqa: BLE001
                        pass
                    led.stop_cloid, led.stop_px = None, None
                self._event("RED", "ledger_dust_cleared",
                            f"{leg} qty {led.qty} below venue minimum - "
                            f"cleared without an order (verify flat on venue)")
                led.qty = 0.0
                return
        # CORROBORATE BEFORE TOUCHING ANYTHING (re-gate 2026-08-27 B2). This
        # was the one write path that never asked the venue: side AND size
        # came straight off the ledger, and the only reads were
        # order_status() and mid(). Reproduced with reads fully HEALTHY -
        # position closed outside our sight (an operator flatten on
        # Coinbase, which halt_error's own ACTION page instructs), venue
        # flat, ledger still +0.34 - the exit path sent MARKET SELL 0.34 and
        # opened a naked, stopless SHORT of ~$25k with halted=None.
        # _halt_locked's docstring already forbids exactly this: "a blind
        # market close against a wrong ledger can open a reverse naked
        # position". The exit path is not exempt from its own rule.
        verdict, net, want = self._stop_backing()
        if verdict == "blind":
            self._event("RED", "close_backing_blind",
                        f"{leg} exit requested but the venue position is "
                        f"UNREADABLE - cancelling nothing and closing "
                        f"nothing; the stop stays armed and this retries "
                        f"next poll")
            return
        if verdict == "diverged":
            self._event("RED", "ledger_divergence",
                        f"{leg} exit requested but the venue does not back "
                        f"the ledger (venue net {net}, ledger sum {want}) - "
                        f"closing off the ledger would open a REVERSE naked "
                        f"position, halting instead")
            self.halt("LEDGER_DIVERGENCE",
                      f"{leg} close: venue net {net} vs ledger sum {want}")
            return
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
            # CLAMP TO THE VENUE (re-gate 2026-08-27 B2). Corroboration says
            # the ledger is backed in aggregate; it does not bound THIS leg
            # against the net. Never send a close larger than the venue
            # actually holds, and never one pointing the wrong way - either
            # overshoots through flat and opens the reverse side.
            if abs(net) <= 1e-9 or (net > 0) != (led.qty > 0):
                self._event("RED", "close_refused_unbacked",
                            f"{leg} exit wants {led.qty} but the venue net is "
                            f"{net} - closing would OPEN the reverse side; "
                            f"leaving the ledger for the drift check and "
                            f"boot reconcile to resolve")
                return
            qty = min(abs(led.qty), abs(net))
            try:
                qty = self.venue.quantize(qty)
            except Exception:  # noqa: BLE001
                pass
            if qty <= 0.0:
                # not dust (that was handled above) but a net too small to
                # close against - leave the ledger for the reconcilers
                self._event("RED", "close_refused_unbacked",
                            f"{leg} exit wants {led.qty} but the venue net "
                            f"{net} quantizes to nothing closeable")
                return
            cloid = f"{leg[0].upper()}-{int(time.time())}-X"
            try:
                ref = self.venue.mid()
            except Exception:  # noqa: BLE001
                ref = 0.0
            self.venue.place_market(_close_side(led.qty), qty, cloid)
            self._watch_fill(leg, "close", cloid, ref, _close_side(led.qty))
            self._event("INFO", "leg_closed", f"{leg} {why} qty={led.qty}")
            self._cov("signal_exit")
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
            self._cov("post_only_cross")
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
            if st is None or st.get("status") in ("OPEN", "UNKNOWN"):
                # UNKNOWN keeps the watch: a truthy UNKNOWN dict used to
                # fall through and silently DROP it, starving the ramp's
                # slippage sample on one API blip (round-3 review)
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
                                 "slip_bps": round(bps, 2),
                                 # a DryRunVenue "fill" is a synthetic price:
                                 # it must not feed the slippage sample
                                 "live": self._is_live()})

    # ---------- drift ----------

    # ---------- RAMP v4 drills (RAMP_V4.md, frozen 2026-08-15) ----------

    def _min_contract(self) -> float:
        """Smallest tradable size: first candidate the venue quantizes to a
        nonzero amount (quantize floors to contract multiples)."""
        for x in (1e-6, 1e-5, 1e-4, 1e-3, 0.005, 0.01, 0.02, 0.05, 0.1):
            try:
                q = self.venue.quantize(x * 1.0000001)
            except Exception:  # noqa: BLE001
                continue
            if q and q > 0:
                return q
        return 0.0

    def _drill_refusal(self) -> str | None:
        if self.state.halted:
            return f"halted:{self.state.halted}"
        for name, led in self.state.legs.items():
            if led.qty != 0.0 or led.entry_cloid or led.stop_cloid:
                return f"leg_not_flat:{name}"
        try:
            pos = self.venue.position()
        except Exception as exc:  # noqa: BLE001
            return f"position_unreadable:{exc}"
        if abs(pos) > 1e-9:
            return f"venue_not_flat:{pos}"
        day = time.strftime("%Y-%m-%d", time.gmtime())
        rec = [d for d in self.state.drills if d.get("day") == day]
        if len(rec) >= getattr(self.cfg, "drill_max_per_day", 6):
            return "daily_budget_exhausted"
        if self.state.drills and time.time() - self.state.drills[-1]["ts"] \
                < getattr(self.cfg, "drill_cooldown_s", 300):
            return "cooldown"
        return None

    def drill(self, kind: str) -> dict:
        """One deliberate min-size round trip through the REAL live order
        paths. Size is ALWAYS one venue contract - no parameter can raise
        it. Endpoint-only (token-gated); never called by any scheduler.
        Fills are recorded (leg='drill') so they feed slippage stats, and
        are excluded from every P&L metric by that tag."""
        if kind not in ("cycle", "stopfill"):
            return {"ok": False, "refused": f"unknown kind {kind}"}
        if not self._venue_lock.acquire(timeout=30):
            return {"ok": False, "refused": "executor busy (step running)"}
        try:
            return self._drill_locked(kind)
        finally:
            self._venue_lock.release()

    def _drill_locked(self, kind: str) -> dict:
        refusal = self._drill_refusal()
        if refusal:
            return {"ok": False, "refused": refusal}
        q = self._min_contract()
        if q <= 0:
            return {"ok": False, "refused": "no tradable minimum size"}
        ts = int(time.time())
        # ns-unique cloid base: second-resolution collided when two drills ran
        # inside one second (dup client order ids — Coinbase rejects them, and
        # the DryRun book silently overwrote, orphaning the repair order)
        base = f"D-{time.time_ns()}"
        steps: dict = {"qty": q}
        ok = True
        # coverage is credited only AFTER the repair tail confirms the drill
        # fully verified — a failed drill advancing ramp-authorizing rows let
        # broken mechanics count as proven (referee 2026-08-17)
        covs: list[str] = []
        try:
            mid = self.venue.mid()
            self.venue.place_market("BUY", q, f"{base}-E")
            self._watch_fill("drill", "drill_entry", f"{base}-E", mid, "BUY")
            steps["entry"] = "sent"
            if kind == "cycle":
                trig = mid * 0.99
                self.venue.place_stop("SELL", q, trig, f"{base}-S")
                covs.append("stop_placed")
                st = self.venue.order_status(f"{base}-S")
                steps["stop_open"] = bool(st and st.get("status") == "OPEN")
                self.venue.cancel(f"{base}-S")
                st2 = self.venue.order_status(f"{base}-S")
                steps["stop_cancelled"] = bool(
                    st2 and st2.get("status") != "FILLED")
                # exit ONLY if the stop did not fill in the cancel window -
                # unconditional exit after a filled stop sold us short
                # (referee 2026-08-15, executed repro)
                if steps["stop_cancelled"]:
                    self.venue.place_market("SELL", q, f"{base}-X")
                    self._watch_fill("drill", "drill_exit", f"{base}-X",
                                     mid, "SELL")
                    steps["exit"] = "sent"
                else:
                    steps["exit"] = "skipped_stop_filled"
                ok = steps["stop_open"] and steps["stop_cancelled"]
                if ok:
                    covs.append("drill_cycle")
            else:  # stopfill: trigger just above market -> fires immediately
                trig = mid * 1.005
                filled = False
                try:
                    self.venue.place_stop("SELL", q, trig, f"{base}-S")
                    covs.append("stop_placed")
                    self._watch_fill("drill", "drill_stop", f"{base}-S",
                                     trig, "SELL")
                    for _ in range(6):
                        st = self.venue.order_status(f"{base}-S")
                        if st and st.get("status") == "FILLED":
                            filled = True
                            break
                        time.sleep(2)
                except Exception as exc:  # noqa: BLE001
                    steps["stop_error"] = str(exc)[:120]
                steps["stop_filled"] = filled
                if filled:
                    covs.extend(("stop_filled", "drill_stopfill"))
                else:
                    # never leave a drill position open: cancel + flatten
                    try:
                        self.venue.cancel(f"{base}-S")
                    except Exception:  # noqa: BLE001
                        pass
                    self.venue.place_market("SELL", q, f"{base}-X")
                    self._watch_fill("drill", "drill_exit", f"{base}-X",
                                     mid, "SELL")
                    steps["fallback_flatten"] = True
                    ok = False
        except Exception as exc:  # noqa: BLE001
            ok = False
            steps["error"] = str(exc)[:200]
        # AUTO-REPAIR (referee 2026-08-15, mandatory): a drill must NEVER
        # leave exposure. Fill-beats-cancel races and any exception path land
        # here; residual position is flattened with a reducing market order,
        # recorded, and the drill escalates to RED (which pages).
        try:
            pos_end = self.venue.position()
            if abs(pos_end) > 1e-9:
                rq = 0.0
                try:
                    rq = self.venue.quantize(abs(pos_end))
                except Exception:  # noqa: BLE001
                    pass
                rq = rq or abs(pos_end)
                self.venue.place_market(_close_side(pos_end), rq, f"{base}-R")
                steps["auto_repair"] = pos_end
                ok = False
                pos_end = self.venue.position()
            steps["venue_flat_end"] = abs(pos_end) <= 1e-9
            ok = ok and bool(steps["venue_flat_end"])
        except Exception as exc:  # noqa: BLE001
            steps["venue_flat_end"] = None
            steps["repair_error"] = str(exc)[:200]
            ok = False
        if ok:
            for k in covs:
                self._cov(k)
            # a SUCCESSFUL drill is the re-arm path for the auto-drill
            # breaker: a human ran /drill supervised and the mechanics
            # verified end-to-end (referee 2026-08-17 - there was no way
            # to clear auto_drill_off short of editing the state file)
            if getattr(self.state, "auto_drill_off", None):
                self.state.auto_drill_off = None
                self._event("INFO", "auto_drill_rearmed",
                            f"breaker cleared by verified {kind} drill")
        rec = {"ts": ts, "day": time.strftime("%Y-%m-%d", time.gmtime(ts)),
               "kind": kind, "ok": ok, "steps": steps}
        self.state.drills = (self.state.drills or [])[-49:] + [rec]
        self._event("INFO" if ok else "RED", "drill",
                    f"{kind} {'ok' if ok else 'UNVERIFIED - check venue'} q={q}")
        self._poll_fill_watch()
        self._save_state()
        return rec

    def _needed_auto_drill(self) -> str | None:
        """Next drill kind auto-drill may run: CYCLES ONLY. stopfill is
        deliberately excluded (referee 2026-08-17): Coinbase maps a SELL
        stop to STOP_DOWN and preview-rejects an above-market trigger, so
        an auto stopfill would fail deterministically and latch the
        breaker. The stop_filled row is satisfied organically (S4 stops
        fill in the normal course) or by a supervised manual stopfill
        after redesign."""
        # MUST read coverage_live, not the all-modes total: after the
        # provenance split (2026-08-21) the total still carries pre-split
        # counts, so reading it made auto-drill see drill_cycle as already
        # satisfied and return None forever - auto-drill silently stopped
        # advancing the ramp gate, with no error anywhere. Read the same
        # source the gate reads.
        cov = getattr(self.state, "coverage_live", {}) or {}
        if cov.get("drill_cycle", 0) < DRILL_CYCLE_NEED:
            return "cycle"
        # slippage_sample ALSO gates coverage_complete, and one cycle drill
        # yields exactly 2 live fills (market entry + market flatten; the stop
        # is cancelled, not filled). Stopping at drill_cycle left the gate
        # stuck at 6/10 while this returned None - which reads as "drills
        # complete", so the ramp could never close on its own. Organic fills
        # count too, so this self-limits once trading resumes.
        if self._live_fill_count() < SLIPPAGE_SAMPLE_NEED:
            return "cycle"
        return None

    def _live_fill_count(self) -> int:
        """Fills counting toward the slippage sample: live venue fills only
        (a DryRunVenue price is synthetic), voids excluded.

        The void filter must match main.py's `n_live` EXACTLY (fusion gate
        2026-08-26): it did not, so at the first boot after _void_absurd_fills
        the two 1320bps phantom fills counted here but not there - auto-drill
        read the sample as complete and stopped at a real 8/10, while /pulse
        correctly showed 8. A ramp gate whose two readers disagree is not a
        gate."""
        return sum(1 for f in (getattr(self.state, "fills", None) or [])
                   if isinstance(f, dict) and f.get("live") is True
                   and not f.get("void"))

    def _maybe_auto_drill(self, entries_ok: bool) -> None:
        """RAMP_V4.md amendment 2026-08-17 (Casey: zero-touch drill QA):
        in a flat window the executor runs its OWN drills - one per spacing
        interval - until the drill coverage rows are met. Runs inside the
        step lock; every manual-drill hard bound still applies via
        _drill_locked (size, flat-book refusals, daily budget, cooldown,
        auto-repair tail). LIVE only: dry-run drills would mark live
        coverage rows met with simulated fills. One failed auto drill trips
        auto_drill_off (persisted) - it never retries into a venue that
        just failed; manual /drill remains for the re-run."""
        # _is_live() rather than the dry_run flag alone: it also rejects a
        # shadow venue. Without it, evidence would never reach coverage_live
        # while _needed_auto_drill kept asking for more, so auto-drill would
        # spend real drills into a gate that can never advance.
        if not getattr(self.cfg, "auto_drill", False):
            self._auto_drill_wait = "disarmed"
            return
        if not self._is_live():
            self._auto_drill_wait = "not_live"
            return
        if not entries_ok:
            self._auto_drill_wait = "feed_degraded"
            return
        if getattr(self.state, "auto_drill_off", None):
            self._auto_drill_wait = "breaker_latched"
            return
        kind = self._needed_auto_drill()
        if kind is None:
            self._auto_drill_wait = "complete"
            return
        last = self.state.drills[-1]["ts"] if self.state.drills else 0
        if time.time() - last < getattr(self.cfg, "auto_drill_spacing_s", 3600):
            self._auto_drill_wait = "spacing"
            return
        refusal = self._drill_refusal()
        if refusal:
            # Record WHY. This used to `return  # quietly wait`, so an
            # auto-drill blocked for days behind an open position looked
            # exactly like a broken one from outside (2026-08-24: the book
            # had been non-flat since 08-19 and nothing said so anywhere).
            self._auto_drill_wait = refusal
            return
        fills_before = self._live_fill_count()
        rec = self._drill_locked(kind)
        if rec.get("refused"):
            self._auto_drill_wait = rec["refused"]
            return
        self._auto_drill_wait = None
        from .alerts import send
        # DEF-5/6: the terminal condition is now a MEASUREMENT (live fill
        # count), and a drill can fail to advance it (venue omits
        # average_filled_price, or mid() is 0 so _watch_fill never queues).
        # Without this bound auto-drill burns the daily budget forever.
        if rec["ok"]:
            if self._live_fill_count() <= fills_before:
                self._drill_no_fill += 1
                if self._drill_no_fill >= DRILL_NO_FILL_MAX:
                    self.state.auto_drill_off = (
                        f"{self._drill_no_fill} drills produced no slippage "
                        f"sample - fills are not being recorded")
                    send("🔴 ACTION NEEDED (you) — auto-drill disabled: "
                         f"{self._drill_no_fill} consecutive drills verified "
                         "OK but recorded NO fills, so the slippage row can "
                         "never close. Drilling further just spends money — "
                         "check the venue's average_filled_price reporting.")
                    return
            else:
                self._drill_no_fill = 0
        if rec["ok"]:
            # gate-relevant counts, not the all-modes total: reporting
            # "3/3" while the ramp gate reads 0/3 is worse than silence
            cov = getattr(self.state, "coverage_live", {}) or {}
            send(f"✅ auto-drill {kind} ok "
                 f"(cycle {cov.get('drill_cycle', 0)}/{DRILL_CYCLE_NEED}, "
                 f"slippage {self._live_fill_count()}/{SLIPPAGE_SAMPLE_NEED}, "
                 f"stop_filled {cov.get('stop_filled', 0)}/1)"
                 + ("" if self._needed_auto_drill()
                    else " — auto-drill cycles COMPLETE (stop_filled row "
                         "fills organically from a real S4 stop)"))
        else:
            self.state.auto_drill_off = f"{kind} failed at {rec['day']}"
            if rec["steps"].get("venue_flat_end") is True:
                send(f"🚨 auto-drill {kind} FAILED - auto-drill disabled "
                     "until reviewed (book verified flat by auto-repair; "
                     "forward the drill record to Claude)")
            else:
                send(f"🔴 ACTION NEEDED (you) — auto-drill {kind} FAILED and "
                     "flatness could NOT be verified: open Coinbase NOW and "
                     "check for a residual position; then forward the drill "
                     "record to Claude. Auto-drill is disabled.")

    def _check_drift(self, equity: float) -> None:
        if getattr(self.venue, "log", None) is not None:
            # DRY-RUN: drift itself is meaningless against simulated fills,
            # but the _boot_mismatch CLEAR must still be reachable (re-gate
            # 2026-08-27 N4). _adopt_venue_locked has no dry-run guard, so
            # an adopt in shadow mode latched _boot_mismatch with no in-band
            # way to clear it - entries, chase and auto-drill dead for the
            # process life, in the very stage whose purpose is exercising
            # those paths, and the page's own remedy ("adopt again") could
            # not clear it either.
            if self._boot_mismatch:
                self._boot_mismatch = False
                self._event("INFO", "boot_mismatch_resolved",
                            "dry-run: boot/adopt mismatch cleared (no venue "
                            "truth to reconcile against in shadow mode)")
            return
        try:
            net = self.venue.position()
        except Exception as exc:  # noqa: BLE001
            # 2026-08-26 incident: this was a bare `return` — the single
            # mechanism that compares venue truth to the ledger disabled
            # itself, silently, on exactly the failure that makes it
            # essential. Three days of blindness, zero pages. Now it is a
            # RED with its own append-side cooldown (the event log holds 200
            # entries and rotates in ~67 min of normal traffic, so flooding
            # it would also destroy the forensic record).
            now = time.time()
            if now - self._venue_read_failed_at >= 1800:
                self._venue_read_failed_at = now
                self._event("RED", "venue_read_failed",
                            f"cannot verify the venue position ({exc}) - "
                            f"drift check is BLIND until this clears")
            return
        self.state.last_venue_read_ts = int(time.time())
        self._venue_read_failed_at = 0.0
        want = sum(l.qty for l in self.state.legs.values())
        px = self.venue.mid()
        if self._boot_mismatch and abs(net - want) < 1e-9:
            # GENUINE agreement only - the dollar drift tolerance let a
            # sub-tolerance orphan unblock entries while it still rested
            # (re-review 2026-08-26; benign at $50k, armed at ramp size)
            self._boot_mismatch = False
            self._event("INFO", "boot_mismatch_resolved",
                        "venue and ledger agree exactly - entries unblocked")
        if abs(net - want) * px > self.cfg.drift_tol_frac * max(equity, 1.0):
            self._event("RED", "position_drift",
                        f"venue={net:.5f} ledger={want:.5f} BTC - investigate")
