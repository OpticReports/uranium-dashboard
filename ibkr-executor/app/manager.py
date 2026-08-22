"""El Nino ladder manager — the decision brain (venue-agnostic).

Manages the 3-leg options ladder from ELNINO.md as a state machine. Given
the current world state (date, Nino readings, spread marks), it emits ORDER
INTENTS; a venue adapter (IBKR via ib_async, or DryRun) executes them.
The manager never talks to a broker directly — same separation as
btc-executor's mirror.

Ladder (entries are TRIGGERED, never scheduled):
  leg 1 NG   : buy NG call spread when the Nov window opens AND event alive
  leg 2 SUGAR: buy SB put spread at leg-1 resolution (or window) if alive
  leg 3 SLV  : buy SLV call spread funded by ladder progress
Kill discipline (any leg, any time):
  - EVENT COLLAPSE: weekly Nino3.4 < +1.0 -> close everything, halt ladder
  - per-leg target hit -> close leg, bank
  - per-leg max-loss (premium is the floor; spreads can be exited early
    at SALVAGE_FRAC to recover time value)
  - window expiry -> close at market
House-money rule: leg N+1's budget = min(initial_budget, banked profits)
unless cfg.compound=True (then full banked amount rolls).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field, fields

logger = logging.getLogger(__name__)


@dataclass
class LegSpec:
    key: str
    description: str
    window_open: str            # ISO date: earliest entry
    window_close: str           # ISO date: forced exit
    structure: dict             # venue-agnostic spread description
    target_gain_frac: float     # close when spread value >= premium*(1+target)
    salvage_frac: float = 0.35  # exit early if value <= premium*salvage AND
                                # thesis degraded (nino weakening)


@dataclass
class LegState:
    status: str = "WAITING"     # WAITING|ARMED|OPEN|CLOSED|SKIPPED
    entry_premium: float = 0.0  # total paid (USD)
    entry_date: str | None = None
    close_date: str | None = None
    close_value: float = 0.0
    close_reason: str | None = None
    order_ref: str | None = None


LADDER = [
    LegSpec("NG", "NG H7 call spread 110%/145% of spot (Nov trigger)",
            "2026-11-01", "2027-02-20",
            {"venue": "NYMEX", "underlying": "NG", "kind": "call_spread",
             "expiry_hint": "2027-02", "lo_strike_pct": 1.10, "hi_strike_pct": 1.45},
            target_gain_frac=1.5),
    LegSpec("SB", "SB K7/N7 put spread 90%/75% of spot",
            "2026-11-15", "2027-05-15",
            {"venue": "ICE", "underlying": "SB", "kind": "put_spread",
             "expiry_hint": "2027-04", "lo_strike_pct": 0.90, "hi_strike_pct": 0.75},
            target_gain_frac=2.0),
    LegSpec("SLV", "SLV call spread 110%/135% of spot",
            "2026-12-01", "2027-06-18",
            {"venue": "SMART", "underlying": "SLV", "kind": "call_spread",
             "expiry_hint": "2027-06", "lo_strike_pct": 1.10, "hi_strike_pct": 1.35},
            target_gain_frac=2.0),
]

NINO_KILL = 1.0                 # weekly Nino3.4 anomaly below this = event dead
NINO_ARM = 2.0                  # entries require the event still at strength


@dataclass
class LadderState:
    legs: dict = field(default_factory=lambda: {s.key: LegState() for s in LADDER})
    banked: float = 0.0          # realized P&L across closed legs
    halted: str | None = None    # EVENT_COLLAPSE | KILL | None
    events: list = field(default_factory=list)


class LadderManager:
    def __init__(self, cfg, state_path: str):
        self.cfg = cfg
        self.state_path = state_path
        # Set by _load when an unreadable state file could not be parsed —
        # service startup turns it into a Telegram alert (the manager has no
        # alert channel at construction time), same doctrine as the blend
        # manager's mode-transition archive.
        self.archived_state: str | None = None
        # ZF-7: did the preserve rename actually SUCCEED? The Z-J boot save
        # below is conditional on it.
        self._evidence_preserved = False
        # MF2-2: an operator /kill whose leg closes have not completed yet
        # (the sentinel is still on disk). Set by _load; the service re-arms
        # the deferred close from it after a restart.
        self.kill_pending = False
        self.state = self._load()
        if self.archived_state and self._evidence_preserved:
            # Z-J: the corrupt/drift branches move the file aside and set
            # `halted` IN MEMORY; `_build` never saves, so a crash before
            # the loop's first save() lost the halt AND the preserved legs —
            # next boot came back `halted: None` with every leg WAITING,
            # precisely the y2 harm one crash earlier. Persist immediately;
            # on THIS path the original file is already archived, so nothing
            # is erased. When the rename FAILED the original is still the
            # only copy of the drift, so the halt stays in memory rather
            # than overwriting the evidence at boot (ZF-7).
            self.save()

    def _load(self) -> LadderState:
        st = self._load_book()
        # MF2-2: /kill journals its halt as a SEPARATE sentinel file, because
        # an API thread may not read-modify-write `legs` (x12) and so may not
        # call save() at all when the loop holds MGR_LOCK. Measured before
        # this: /kill answered "The ladder is halted from now" while the book
        # on disk said halted=None with the leg still OPEN, so a restart in
        # that window — the restart a wedged gateway invites — came back
        # UN-halted. An existing halt reason is more specific than KILL
        # (SCHEMA_DRIFT is a data-integrity halt), so it is kept; either way
        # nothing trades until the operator /resume-s.
        if os.path.exists(self.kill_sentinel):
            self.kill_pending = True
            st.halted = st.halted or "KILL"
        return st

    def _load_book(self) -> LadderState:
        try:
            raw = json.load(open(self.state_path))
        except FileNotFoundError:
            return LadderState()
        except Exception as exc:  # noqa: BLE001
            # x12: a corrupt file used to degrade SILENTLY to a fresh
            # LadderState() — open legs and `halted` forgotten, and the next
            # save() overwrote the evidence. Preserve the file and be loud;
            # a halted ladder that comes back un-halted is the dangerous
            # direction.
            archive = f"{self.state_path}.corrupt-{int(time.time())}"
            try:
                os.replace(self.state_path, archive)
                note = f"unreadable book preserved at {archive}"
                self._evidence_preserved = True
            except OSError as err:
                note = (f"PRESERVE FAILED ({err}) — the unreadable book will "
                        f"be OVERWRITTEN by the next save")
            self.archived_state = (f"ladder state unreadable ({exc}); "
                                   f"starting a FRESH ladder; {note}")
            logger.error("[ladder] %s", self.archived_state)
            return LadderState()
        st = LadderState(banked=raw.get("banked", 0.0),
                         halted=raw.get("halted"))
        try:
            st.legs = {k: LegState(**v) for k, v in raw.get("legs", {}).items()}
        except TypeError as exc:
            # y2: schema drift on a leg row — a deploy ROLLBACK reading rows
            # a newer build wrote. This branch used to reset every leg to
            # WAITING/order_ref=None and leave the file in place: the loop's
            # next save() destroyed the evidence, and a leg reset to WAITING
            # inside its window with nino34 >= NINO_ARM was re-OPENed by
            # step() — a DUPLICATE live spread with the real one orphaned at
            # the venue. Now, like the outer corrupt branch: PRESERVE the
            # file, keep every field this build still understands (an OPEN
            # leg's order_ref is the only handle on a live spread), and HALT
            # so step() cannot act before the operator looks. `banked` and
            # an existing `halted` reason are kept as they were.
            known = {f.name for f in fields(LegState)}
            st.legs = {k: LegState(**{kk: vv for kk, vv in v.items()
                                      if kk in known})
                       for k, v in (raw.get("legs") or {}).items()
                       if isinstance(v, dict)}
            archive = f"{self.state_path}.corrupt-{int(time.time())}"
            try:
                os.replace(self.state_path, archive)
                note = f"drifted book preserved at {archive}"
                self._evidence_preserved = True
            except OSError as err:
                note = (f"PRESERVE FAILED ({err}) — the drifted book will "
                        f"be OVERWRITTEN by the next save")
            st.halted = st.halted or "SCHEMA_DRIFT"
            self.archived_state = (f"ladder leg rows unreadable ({exc}); "
                                   f"ladder HALTED ({st.halted}) so no leg "
                                   f"can be opened or closed before you "
                                   f"look; banked/halted kept; {note}")
            logger.error("[ladder] %s", self.archived_state)
        for s in LADDER:
            st.legs.setdefault(s.key, LegState())
        st.events = raw.get("events", [])[-300:]
        return st

    @property
    def kill_sentinel(self) -> str:
        """MF2-2: the /kill journal, the ladder's answer to the blend's
        `flatten_request`. A file of its OWN, next to the book: writing it
        touches no field the loop thread is mutating, so /kill can make the
        halt DURABLE without MGR_LOCK and without the cross-thread
        read-modify-write of `legs` that save() performs (x12's law)."""
        return f"{self.state_path}.kill"

    def journal_kill(self, today: str) -> None:
        """Record an operator /kill on disk. Atomic (same mkstemp + fsync +
        rename as save()), takes NO lock, and is safe from any thread. The
        record is consumed by the loop once the legs are actually closed,
        and deleted by /resume."""
        directory = os.path.dirname(self.state_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=os.path.basename(self.kill_sentinel) + ".",
            suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump({"ts": int(time.time()), "date": today}, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.kill_sentinel)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        self.kill_pending = True

    def clear_kill(self) -> None:
        """Consume the sentinel: the kill has been executed (the loop closed
        what it could) or the operator has /resume-d. The halt itself lives
        in the book from here on."""
        try:
            os.unlink(self.kill_sentinel)
        except FileNotFoundError:
            pass
        self.kill_pending = False

    def save(self) -> None:
        """Atomic write with a UNIQUE temp file per writer (x12): the plain
        json.dump(open(path,"w")) this replaced published a truncated file
        on any interruption, and `_load` turned that into a fresh ladder —
        open legs and `halted` forgotten on live paper money. The temp file
        lives in the state directory so os.replace stays a same-filesystem
        rename. Callers still serialize their MUTATIONS (service.MGR_LOCK):
        this makes the WRITE safe, not the read-modify-write above it."""
        directory = os.path.dirname(self.state_path) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {"legs": {k: asdict(v) for k, v in self.state.legs.items()},
                   "banked": self.state.banked, "halted": self.state.halted,
                   "events": self.state.events[-300:]}
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=os.path.basename(self.state_path) + ".",
            suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh, indent=1)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.state_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _event(self, level: str, msg: str) -> None:
        last = self.state.events[-1] if self.state.events else None
        if last and last.get("msg") == msg:
            return
        self.state.events.append({"ts": int(time.time()), "level": level,
                                  "msg": msg})
        logger.info("[ladder] %s", msg)

    # ---------- budget ----------

    def leg_budget(self) -> float:
        base = self.cfg.leg_budget_usd
        if self.cfg.compound and self.state.banked > 0:
            return base + self.state.banked
        return base

    # ---------- the decision step ----------

    def step(self, today: str, nino34: float | None,
             marks: dict[str, float]) -> list[dict]:
        """One evaluation. `marks` = current value (USD) of each OPEN leg's
        spread. Returns order intents:
        [{action: OPEN|CLOSE, leg, structure?, budget?, reason}]."""
        intents: list[dict] = []
        st = self.state
        if st.halted:
            return intents

        # global kill: event collapse closes everything and halts the ladder
        if nino34 is not None and nino34 < NINO_KILL:
            for spec in LADDER:
                leg = st.legs[spec.key]
                if leg.status == "OPEN":
                    intents.append({"action": "CLOSE", "leg": spec.key,
                                    "reason": f"EVENT COLLAPSE nino34={nino34}"})
            st.halted = "EVENT_COLLAPSE"
            self._event("RED", f"event collapse (nino34 {nino34}) - ladder halted")
            return intents

        open_count = sum(1 for l in st.legs.values() if l.status == "OPEN")
        for i, spec in enumerate(LADDER):
            leg = st.legs[spec.key]
            if leg.status == "OPEN":
                mark = marks.get(spec.key)
                if mark is None:
                    continue
                if mark >= leg.entry_premium * (1 + spec.target_gain_frac):
                    intents.append({"action": "CLOSE", "leg": spec.key,
                                    "reason": f"target hit ({mark:.0f} vs "
                                              f"{leg.entry_premium:.0f} paid)"})
                elif today >= spec.window_close:
                    intents.append({"action": "CLOSE", "leg": spec.key,
                                    "reason": "window expiry"})
                elif (nino34 is not None and nino34 < NINO_ARM
                      and mark <= leg.entry_premium * spec.salvage_frac):
                    intents.append({"action": "CLOSE", "leg": spec.key,
                                    "reason": f"salvage (thesis weakening, "
                                              f"nino34 {nino34})"})
                continue
            if leg.status != "WAITING":
                continue
            # entry gates: window open, event at strength, prior leg resolved
            # (sequential ladder), respect max concurrent legs
            if today < spec.window_open or today >= spec.window_close:
                continue
            if nino34 is None or nino34 < NINO_ARM:
                continue
            opening_now = {o["leg"] for o in intents if o["action"] == "OPEN"}
            prior_key = LADDER[i - 1].key if i > 0 else None
            prior_ok = (i == 0
                        or st.legs[prior_key].status in ("OPEN", "CLOSED")
                        or prior_key in opening_now)
            if not prior_ok or open_count >= self.cfg.max_concurrent_legs:
                continue
            intents.append({"action": "OPEN", "leg": spec.key,
                            "structure": spec.structure,
                            "budget": round(self.leg_budget(), 2),
                            "reason": f"window open, nino34 {nino34} >= {NINO_ARM}"})
            open_count += 1
        return intents

    # ---------- execution callbacks (adapter reports results) ----------

    def on_opened(self, key: str, premium: float, order_ref: str,
                  today: str) -> None:
        leg = self.state.legs[key]
        leg.status, leg.entry_premium = "OPEN", premium
        leg.entry_date, leg.order_ref = today, order_ref
        self._event("INFO", f"{key} opened, premium ${premium:,.0f}")
        self.save()

    def on_closed(self, key: str, value: float, reason: str,
                  today: str) -> None:
        leg = self.state.legs[key]
        pnl = value - leg.entry_premium
        leg.status, leg.close_date = "CLOSED", today
        leg.close_value, leg.close_reason = value, reason
        self.state.banked += pnl
        self._event("INFO",
                    f"{key} closed ({reason}): ${value:,.0f} vs "
                    f"${leg.entry_premium:,.0f} paid -> P&L ${pnl:+,.0f}; "
                    f"banked ${self.state.banked:+,.0f}")
        self.save()
