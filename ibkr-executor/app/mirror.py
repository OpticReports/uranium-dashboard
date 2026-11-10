"""Composer mirror: the executor strategy (composer/IBKR_MIRROR.md).

One brain, two brokers. The keyless brain (composer/scripts/mirror_brain.py) publishes, at the
decision minute, the target weights each approved symphony tree holds and the prices it was
evaluated on. This module turns them into whole-share orders on the IBKR account through the
existing adapter contract (place_stock_order MKT DAY, find_stock_order, cancel_stock_order), with
the accounting in app/mirror_core.py: virtual sleeves, Composer's daily / threshold rule,
cross-sleeve netting, sells booked before buys are sized from the cash actually held.

A MirrorManager is ONE book. The service builds up to two: a DRY book (its own private DryAdapter:
no venue, no account reads; fills at the brain's reference price) for every engine not yet live,
and a LIVE book for the engines named in MIRROR_LIVE_ENGINES. MIRROR_ENABLED=false (the default)
builds neither.

Threads
- the LOOP thread alone calls tick(): it owns the book, the state file and every adapter call
- API threads call halt() / resume() (the halt file, under halt_lock), request_transfer() /
  request_credit() (the inbox file, under inbox_lock) and view() / health() (a published snapshot)

A session, in the loop thread
  1 the brain's clock (/mirror/session) says when the decision bar ends and when the session closes
  2 at decision + offset: the pre-trade gates (live: the account must hold exactly the book, the
    account's cash must cover the book's, the blend must be off), then the intents, which must be
    for today, computed after the decision bar closed, and fresh
  3 the plan (mirror_core.build_plan); live: every symbol it would trade is cross-checked against
    the venue's own quote, and a symbol that fails takes its sleeves out of the plan
  4 SELLS, each under a deterministic id written to disk BEFORE the venue sees it; booked once, at
    the terminal state; then transfers, then BUYS sized from actual cash; leftovers cancelled
    before the close and booked at what filled
  5 afterwards the account is compared with the book; a mismatch that persists halts the book

Nothing here trades for Composer, and nothing here reads Composer.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import mirror_core as mc
from .feeds import FeedDeadline, with_deadline

logger = logging.getLogger(__name__)

SCHEMA = 1
INTENTS_KIND = "composer-mirror-intents"
SESSION_KIND = "composer-mirror-session"
ET = ZoneInfo("America/New_York")

SESSION_TTL_S = 600.0          # the brain's clock is re-read this often
SESSION_FAIL_TTL_S = 20.0      # ... and this soon after a failed read
SESSION_DEADLINE_S = 6.0       # total deadline of one clock read
INTENTS_DEADLINE_S = 25.0      # total deadline of one intents read (the brain rebuilds in ~6-10 s)
INTENTS_RETRY_S = 3.0
INTENTS_MAX_AGE_S = 90.0       # a payload older than this when it is validated is not acted on
CLOCK_SKEW_S = 60.0            # the brain's clock and this one may differ by at most this
ORDER_POLL_S = 1.5
TICK_BUDGET_S = 150.0          # one tick never waits longer than this in total
PLAN_MIN_LEFT_S = 60.0         # no plan is started with less than this left before the cancel instant
PLACE_TRIES = 3
STUCK_FAST_S = 300.0           # an unresolved order is re-asked every 2 s for this long past the cancel instant
STUCK_SLOW_WAIT_S = 60.0       # ... and this often afterwards
QUOTE_BUDGET_S = 45.0          # the venue cross-check of one plan never takes longer than this
TRUE_UP_EVERY_S = 600.0        # late commissions are asked for at most this often
CASH_TOL_USD = 1.0             # the book's cash may exceed the account's by at most this
CHECK_GAP_S = 30.0             # the post-session account check: two strikes this far apart halt
CHECK_STRIKES = 2
HISTORY_KEEP = 120
QUOTE_SOURCES = ("live", "last", "bid", "ask")   # a venue quote from the previous close is no cross-check
_UNKNOWN = object()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(text) -> datetime | None:
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def one_line(e, n: int = 200) -> str:
    return " ".join(str(e).split())[:n]


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def atomic_write(path: str, obj) -> None:
    """write-then-rename with an fsync: a reader sees the old file or the new one, never a torn one"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@dataclass
class MirrorConfig:
    name: str                              # "live" | "dry": the label in alerts, files and feeds
    live: bool                             # True: the service's venue adapter; False: a private DryAdapter
    engines: tuple                         # the sleeves this book runs
    capital: dict                          # {engine: cash a new sleeve is seeded with}
    state_path: str
    decide_offset_s: float = 5.0           # act this long after the decision bar ends
    cancel_before_close_s: float = 60.0    # leftovers are cancelled this long before the close
    quote_band: float = 0.015              # live: venue quote vs the brain's price
    est_quote_band: float = 0.05           # ... when the brain's price is itself an estimate
    blend_enabled: bool = False            # live: no trading while the blend runs in the same account
    core: mc.Config = field(default_factory=mc.Config)


# ------------------------------------------------------------------ the brain's HTTP surface
def _reason(exc: Exception) -> str:
    if isinstance(exc, FeedDeadline):
        return "deadline"
    if isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol)):
        return "bad_url"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return "auth" if code in (401, 403) else f"http_{code}"
    if isinstance(exc, ValueError):
        return "decode"
    return "transport"


class HttpBrain:
    """GET /mirror/session and /mirror/intents with X-API-Token, each under a TOTAL deadline. One
    object is shared by the service's books, so a payload one of them just read is not asked for
    twice. Answers (payload | None, reason)."""

    def __init__(self, url: str, token: str):
        self.base = (url or "").strip().rstrip("/")
        self.token = (token or "").strip()
        self._last: tuple | None = None        # (after, payload, monotonic)
        self._lock = threading.Lock()

    def _get(self, path: str, deadline: float, params: dict | None = None) -> tuple:
        if not self.base:
            return None, "no_url"
        try:
            r = with_deadline(deadline, httpx.get, f"{self.base}{path}", params=params,
                              headers={"X-API-Token": self.token}, timeout=deadline)
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                raise ValueError(f"payload is {type(payload).__name__}, not an object")
            return payload, "ok"
        except Exception as exc:  # noqa: BLE001
            logger.warning("mirror brain %s failed: %s", path, one_line(exc))
            return None, _reason(exc)

    def session(self) -> tuple:
        return self._get("/mirror/session", SESSION_DEADLINE_S)

    def intents(self, after: str) -> tuple:
        with self._lock:
            if self._last and self._last[0] == after and time.monotonic() - self._last[2] < 20.0:
                return self._last[1], "ok"
        payload, reason = self._get("/mirror/intents", INTENTS_DEADLINE_S, {"after": after})
        if payload is not None and str(payload.get("asof_utc") or "") >= after:
            with self._lock:
                self._last = (after, payload, time.monotonic())
        return payload, reason


# ------------------------------------------------------------------ the manager
class MirrorManager:
    def __init__(self, cfg: MirrorConfig, brain=None, alert=None, clock=None, sleep=None):
        self.cfg = cfg
        self.brain = brain
        self._alert = alert or (lambda msg: None)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep                    # test seam: sleep(seconds) -> True when interrupted
        self.tick_lock = threading.Lock()      # a whole tick (two loop generations can overlap briefly)
        self.halt_lock = threading.Lock()      # the halt file
        self.inbox_lock = threading.Lock()     # the inbox file
        self.archived_state: str | None = None
        self.last_error: str | None = None
        self.brain_status: dict = {"session": None, "intents": None}
        self._sess: dict | None = None         # {"day", "info", "at", "ok"}
        self._why: str | None = None           # why today's decision has not started yet
        self._said: set = set()
        self._trued_at: datetime | None = None
        self._view: dict = {}
        self._halt: dict = {}
        self._dry = None
        self.state = self._fresh()
        self.book = mc.Book()
        self._load()
        if not cfg.live:
            from .ib_adapter import DryAdapter
            self._dry = DryAdapter()
            for sym, q in self.book.positions().items():
                self._dry.seed_position(sym, q)
        self._publish()

    # -------------------------------------------------------------- files
    def _fresh(self) -> dict:
        return {"schema": SCHEMA, "name": self.cfg.name, "live": self.cfg.live, "book": mc.Book().to_dict(),
                "seeded": {}, "frozen": [], "run": None, "last_run": None, "last_session": None, "history": [],
                "requests": [], "seen_requests": [], "flatten": None, "marks": {"prices": {}, "asof": None},
                "check": None, "commission_pending": [], "seq": 0, "saved_utc": None}

    def _load(self) -> None:
        path = self.cfg.state_path
        try:
            with open(self._halt_path()) as f:
                h = json.load(f)
            self._halt = h if isinstance(h, dict) else {"halted": True, "reason": "unreadable halt file"}
        except FileNotFoundError:
            self._halt = {}
        except Exception as exc:  # noqa: BLE001
            self._halt = {"halted": True, "reason": f"unreadable halt file: {one_line(exc)}", "ts": _iso(self.clock())}
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                raw = json.load(f)
            if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
                raise ValueError(f"schema {raw.get('schema') if isinstance(raw, dict) else None!r} is not {SCHEMA}")
            if raw.get("name") != self.cfg.name or bool(raw.get("live")) != self.cfg.live:
                raise ValueError(f"the file is the book {raw.get('name')!r} (live={raw.get('live')!r}), "
                                 f"not {self.cfg.name!r} (live={self.cfg.live!r})")
            book = mc.Book.from_dict(raw["book"])
            state = self._fresh()
            state.update(raw)
            self.state, self.book = state, book
        except Exception as exc:  # noqa: BLE001
            # never a fresh book in silence where a file existed: positions and cash would be forgotten
            kept = f"{path}.unreadable-{int(time.time())}"
            try:
                os.replace(path, kept)
            except OSError:
                kept = path
            self.archived_state = f"mirror[{self.cfg.name}] state file unreadable ({one_line(exc)}); kept as {kept}"
            self.halt(self.archived_state, by="mirror")

    def _save(self) -> None:
        self.state["book"] = self.book.to_dict()
        self.state["seq"] = int(self.state.get("seq") or 0) + 1
        self.state["saved_utc"] = _iso(self.clock())
        atomic_write(self.cfg.state_path, self.state)
        self._publish()

    def _journal(self, event: str, **kw) -> None:
        """the audit trail (append-only); the state file, not this, is what a restart reads"""
        try:
            path = f"{self.cfg.state_path}.journal.jsonl"
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps({"utc": _iso(self.clock()), "book": self.cfg.name, "event": event, **kw},
                                   separators=(",", ":"), sort_keys=True, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("mirror[%s] journal write failed: %s", self.cfg.name, exc)

    def _halt_path(self) -> str:
        return f"{self.cfg.state_path}.halt"

    def _inbox_path(self) -> str:
        return f"{self.cfg.state_path}.inbox.json"

    # -------------------------------------------------------------- alerts
    def _say(self, level: str, msg: str, key: str | None = None) -> None:
        """level: info | warn | red. key: said at most once per process for that key"""
        if key is not None:
            if key in self._said:
                return
            self._said.add(key)
        icon = {"info": "🪞", "warn": "⚠️", "red": "🚨"}.get(level, "🪞")
        text = f"{icon} mirror[{self.cfg.name}{'' if self.cfg.live else ' · paper'}] {msg}"
        (logger.error if level == "red" else logger.warning if level == "warn" else logger.info)(text)
        try:
            self._alert(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mirror alert failed: %s", exc)

    # -------------------------------------------------------------- halt / resume (any thread)
    def halt(self, reason: str, flatten: bool = False, by: str = "operator") -> dict:
        """Stop trading. flatten (live books only): also sell every share the book holds, on the loop
        thread, as soon as the session is open. Idempotent; a second call can add the flatten."""
        with self.halt_lock:
            h = dict(self._halt or {})
            now = _iso(self.clock())
            if not h.get("halted"):
                h = {"halted": True, "reason": one_line(reason, 300), "ts": now, "by": by}
            if flatten and self.cfg.live and not (h.get("flatten") and not h.get("flatten_done")):
                h.update(flatten=True, flatten_done=False, flatten_cancelled=False, flatten_ts=now,
                         flatten_id=self.clock().strftime("%Y%m%dT%H%M%S"))
            self._write_halt(h)
            return dict(h)

    def resume(self) -> dict:
        """Clear the halt. A flatten not yet finished is cancelled: no new flatten order is sent, and
        the ones already at the venue are settled before the book trades again."""
        with self.halt_lock:
            h = dict(self._halt or {})
            was = bool(h.get("halted"))
            h["halted"] = False
            h["resumed_ts"] = _iso(self.clock())
            if h.get("flatten") and not h.get("flatten_done"):
                h["flatten_cancelled"] = True
            self._write_halt(h)
            return {"was_halted": was, **h}

    def _write_halt(self, h: dict) -> None:
        self._halt = h
        try:
            atomic_write(self._halt_path(), h)
        except Exception as exc:  # noqa: BLE001  the in-memory halt still binds this process
            logger.error("mirror[%s] halt file write failed: %s", self.cfg.name, exc)

    def halt_state(self) -> dict:
        with self.halt_lock:
            return dict(self._halt or {})

    # -------------------------------------------------------------- requests (any thread)
    def _request(self, row: dict) -> dict:
        with self.inbox_lock:
            box = self._read_inbox()
            row = dict(row, id=f"{row['kind']}-{int(time.time() * 1000)}-{len(box)}", utc=_iso(self.clock()))
            box.append(row)
            atomic_write(self._inbox_path(), box)
        return row

    def _read_inbox(self) -> list:
        try:
            with open(self._inbox_path()) as f:
                box = json.load(f)
            return box if isinstance(box, list) else []
        except FileNotFoundError:
            return []
        except Exception as exc:  # noqa: BLE001
            logger.error("mirror[%s] inbox unreadable: %s", self.cfg.name, exc)
            return []

    def request_transfer(self, src: str, dst: str, amount, note: str = "") -> dict:
        """queue a move of capital between two sleeves; it rides the next session's plan (the giver's
        sells fund it, the taker's buys invest it). Raises ValueError on a request that cannot be."""
        amt = _num(amount)
        if src == dst or amt is None or amt <= 0:
            raise ValueError("a transfer needs two different sleeves and a positive amount")
        for s in (src, dst):
            if s not in self.cfg.engines:
                raise ValueError(f"{s!r} is not a sleeve of the {self.cfg.name} book")
        return self._request({"kind": "transfer", "from": src, "to": dst, "amount": amt, "note": one_line(note, 200)})

    def request_credit(self, sleeve: str, amount, note: str = "") -> dict:
        """queue a cash adjustment of one sleeve (a dividend the account received for its shares: +;
        a fee: -). Applied before the next plan; a live book takes a credit only from cash the account
        holds beyond the book."""
        amt = _num(amount)
        if amt is None or amt == 0:
            raise ValueError("a credit needs a non-zero amount")
        if sleeve not in self.cfg.engines:
            raise ValueError(f"{sleeve!r} is not a sleeve of the {self.cfg.name} book")
        return self._request({"kind": "credit", "sleeve": sleeve, "amount": amt, "note": one_line(note, 200)})

    def _drain_inbox(self) -> None:
        with self.inbox_lock:
            box = self._read_inbox()
        if not box:
            return
        seen = set(self.state.get("seen_requests") or [])
        fresh = [r for r in box if isinstance(r, dict) and r.get("id") and r["id"] not in seen]
        if fresh:
            self.state["requests"] = list(self.state.get("requests") or []) + fresh
            self.state["seen_requests"] = (list(self.state.get("seen_requests") or []) + [r["id"] for r in fresh])[-500:]
            self._save()                           # on disk in the state BEFORE the inbox forgets them
            for r in fresh:
                self._journal("request", **r)
        ids = {r.get("id") for r in box if isinstance(r, dict)}
        with self.inbox_lock:
            left = [r for r in self._read_inbox() if not (isinstance(r, dict) and r.get("id") in ids)]
            atomic_write(self._inbox_path(), left)

    # -------------------------------------------------------------- the tick (loop thread only)
    def tick(self, adapter=None, wake=None, stop=None) -> None:
        """One pass. adapter: the service's venue adapter (ignored by a DRY book). wake: the loop's
        wake event (a set event interrupts every wait in here, so /kill is never queued behind a
        retry). stop: () -> True when this loop has been superseded. Never raises."""
        ad = self._dry if self._dry is not None else adapter
        with self.tick_lock:
            try:
                self._tick(ad, wake, stop)
                self.last_error = None
            except mc.MirrorError as exc:          # the book refused a booking: the book and the venue disagree
                self.last_error = one_line(exc, 300)
                logger.exception("mirror[%s] book error", self.cfg.name)
                self.halt(f"book error: {self.last_error}", by="mirror")
                self._say("red", f"HALTED — the book refused a booking ({self.last_error}). Nothing more is "
                                 f"traded until /resume; compare the account with /status first.",
                          key=f"bookerr:{self.last_error}")
            except Exception as exc:  # noqa: BLE001
                self.last_error = one_line(repr(exc), 300)
                logger.exception("mirror[%s] tick failed", self.cfg.name)
                self._say("red", f"tick failed: {self.last_error}", key=f"tick:{self.last_error}")
            finally:
                try:
                    self._publish()
                except Exception:  # noqa: BLE001
                    logger.exception("mirror[%s] publish failed", self.cfg.name)

    def _pause(self, seconds: float, wake, stop, until: datetime) -> bool:
        """wait; True when the tick must return now (woken, superseded, or out of budget)"""
        if stop is not None and stop():
            return True
        if self.clock() + timedelta(seconds=seconds) > until:
            return True
        if self._sleep is not None:
            return bool(self._sleep(seconds))
        if wake is not None:
            return bool(wake.wait(seconds))
        time.sleep(seconds)
        return False

    def _tick(self, ad, wake, stop) -> None:
        self._drain_inbox()
        h = self.halt_state()
        if h.get("flatten") and not h.get("flatten_done"):
            if not self._flatten_step(ad, h):
                return
            h = self.halt_state()
        if h.get("halted"):
            self._abort_run(ad, "halted")
            return
        if ad is None:
            return
        self._reconcile_sleeves(ad)
        until = self.clock() + timedelta(seconds=TICK_BUDGET_S)
        run = self.state.get("run")
        if run:
            self._drive(ad, wake, stop, until)
            return
        info = self._session()
        if not info or not info.get("session"):
            return
        session = info["session"]
        now = self.clock()
        if self.state.get("last_session") == session:
            self._post_check(ad, session)
            return
        if now < info["decide_at"]:
            return
        if now >= info["plan_by"]:
            self._skip(session, "missed the decision window: " + (self._why or "the executor was not ready in time"))
            return
        self._decide(ad, info, wake, stop, until)

    def next_wait(self) -> float | None:
        """seconds until this book next needs the loop, or None when the ordinary cadence will do
        (loop thread; reads only what the last tick left)"""
        try:
            h = self._halt or {}
            if h.get("flatten") and not h.get("flatten_done"):
                return 5.0
            if h.get("halted"):
                return None
            now = self.clock()
            run = self.state.get("run")
            if run:
                over = _parse(run.get("cancel_utc"))
                return 2.0 if not over or (now - over).total_seconds() < STUCK_FAST_S else STUCK_SLOW_WAIT_S
            s = self._sess
            if not s or s["day"] != now.astimezone(ET).date().isoformat():
                return None
            info = s["info"] if s.get("ok") else s.get("kept")
            if not info or not info.get("session") or self.state.get("last_session") == info["session"]:
                return None
            left = (info["decide_at"] - now).total_seconds()
            return max(left, 0.0) + 0.2 if left > 0 else 2.0
        except Exception:  # noqa: BLE001
            return None

    # -------------------------------------------------------------- the brain's clock
    def _session(self) -> dict | None:
        """today's session from the brain's clock, parsed and cached: {"session", "decide_at",
        "cancel_at", "plan_by", "close_at", "open_at"} or {"session": None}; None when unknown"""
        now = self.clock()
        day = now.astimezone(ET).date().isoformat()
        c = self._sess
        if c and c["day"] == day and (now - c["at"]).total_seconds() < (SESSION_TTL_S if c["ok"] else SESSION_FAIL_TTL_S):
            return c["info"] if c["ok"] else c.get("kept")
        raw, reason = self.brain.session() if self.brain is not None else (None, "no_brain")
        info, why = self._read_session(raw, day, now) if raw is not None else (None, reason)
        self.brain_status["session"] = {"ok": info is not None, "reason": why, "utc": _iso(now)}
        if info is None:
            kept = None                            # today's last good read survives a failed one
            if c and c["day"] == day:
                kept = c["info"] if c["ok"] else c.get("kept")
            self._sess = {"day": day, "info": None, "kept": kept, "at": now, "ok": False}
            self._why = f"the brain's clock is unreadable ({why})"
            return kept
        self._sess = {"day": day, "info": info, "at": now, "ok": True}
        return info

    def _read_session(self, raw: dict, day: str, now: datetime) -> tuple:
        if raw.get("kind") != SESSION_KIND or raw.get("schema") != SCHEMA:
            return None, "not a mirror session payload"
        theirs = _parse(raw.get("now_utc"))
        if theirs is None or abs((theirs - now).total_seconds()) > CLOCK_SKEW_S:
            return None, f"the brain's clock reads {raw.get('now_utc')!r}, this one {_iso(now)}"
        if raw.get("session") is None:
            return {"session": None}, "ok"
        if raw.get("session") != day:
            return None, f"the brain's session {raw.get('session')!r} is not today's {day}"
        decide, close, opn = _parse(raw.get("decide_utc")), _parse(raw.get("close_utc")), _parse(raw.get("open_utc"))
        if not (decide and close and opn) or not (opn < decide < close):
            return None, "the session times do not parse"
        cancel = close - timedelta(seconds=self.cfg.cancel_before_close_s)
        return {"session": day, "decide_utc": raw["decide_utc"], "open_at": opn, "close_at": close,
                "decide_at": decide + timedelta(seconds=self.cfg.decide_offset_s), "cancel_at": cancel,
                "plan_by": cancel - timedelta(seconds=PLAN_MIN_LEFT_S)}, "ok"

    def _rth(self, now: datetime) -> bool:
        """is the regular session open now: the brain's clock when it is known for today, else the
        plain weekday 09:30-16:00 ET (the kill path must not depend on the brain)"""
        s = self._sess
        day = now.astimezone(ET).date().isoformat()
        info = (s.get("info") or s.get("kept")) if s and s["day"] == day else None
        if info and info.get("session"):
            return info["open_at"] <= now < info["close_at"]
        if info is not None:
            return False
        e = now.astimezone(ET)
        return e.weekday() < 5 and (9, 30) <= (e.hour, e.minute) < (16, 0)

    # -------------------------------------------------------------- sleeves
    def _reconcile_sleeves(self, ad) -> None:
        """seed the sleeves the config names and the book lacks; freeze (live) or drop (dry) the ones
        the book has and the config no longer names"""
        changed = False
        for name in [n for n in self.book.sleeves if n not in self.cfg.engines]:
            s = self.book.sleeves[name]
            if not self.cfg.live or not s.shares:
                del self.book.sleeves[name]
                self.state["frozen"] = [x for x in self.state.get("frozen") or [] if x != name]
                self._journal("sleeve_dropped", sleeve=name, cash=s.cash, shares=dict(s.shares))
                self._say("warn", f"sleeve {name} is no longer configured for this book: dropped "
                                  f"(cash ${s.cash:,.2f} leaves the book)")
                changed = True
            elif name not in (self.state.get("frozen") or []):
                self.state["frozen"] = list(self.state.get("frozen") or []) + [name]
                self._say("red", f"sleeve {name} holds {dict(s.shares)} but is no longer in MIRROR_LIVE_ENGINES: "
                                 f"FROZEN (kept, never traded). Re-add it, or /kill to sell the book.")
                changed = True
        want = [e for e in self.cfg.engines if e not in self.book.sleeves]
        if want:
            avail = None
            if self.cfg.live:
                cash = ad.account_cash()
                if not cash or _num(cash.get("total_cash")) is None:
                    self._say("warn", f"cannot seed {', '.join(want)}: the account reports no cash claim",
                              key=f"seed-noclaim:{','.join(want)}")
                    want = []
                else:
                    avail = float(cash["total_cash"])
                    funds = _num(cash.get("available_funds"))
                    if funds is not None:
                        avail = min(avail, funds)
            for name in want:
                amt = _num(self.cfg.capital.get(name))
                if amt is None or amt <= 0:
                    self._say("warn", f"cannot seed {name}: no capital configured (MIRROR_CAPITAL_USD and "
                                      f"MIRROR_WEIGHTS)", key=f"seed-nocap:{name}")
                    continue
                if avail is not None and self.book.cash() + amt > avail + CASH_TOL_USD:
                    self._say("red", f"cannot seed {name} with ${amt:,.2f}: the account has ${avail:,.2f} in cash "
                                     f"and the book already claims ${self.book.cash():,.2f}", key=f"seed-short:{name}")
                    continue
                self.book.sleeves[name] = mc.Sleeve(name=name, cash=amt)
                self.state.setdefault("seeded", {})[name] = {"amount": amt, "utc": _iso(self.clock())}
                self._journal("sleeve_seeded", sleeve=name, amount=amt)
                self._say("info", f"sleeve {name} seeded with ${amt:,.2f} in cash")
                changed = True
        if changed:
            self._save()

    def _active(self) -> list:
        frozen = set(self.state.get("frozen") or [])
        return [n for n in self.book.sleeves if n in self.cfg.engines and n not in frozen]

    # -------------------------------------------------------------- the account
    def _venue_problems(self, ad) -> list:
        """what the account holds versus the book; [] when they are the same thing"""
        if not hasattr(ad, "positions_snapshot"):
            return ["the adapter cannot list the account's positions"]
        snap = ad.positions_snapshot()
        probs = mc.check(self.book, snap.get("stocks") or {}, exact=True)
        if snap.get("other"):
            probs.append("positions that are not whole stock lots: " + ", ".join(map(str, snap["other"][:5])))
        return probs

    def _pretrade(self, ad) -> str | None:
        """why this book must not trade now, or None"""
        if not self._active():
            return "the book has no sleeve to trade"
        if self.cfg.live and self.cfg.blend_enabled:
            return "the blend strategy is still enabled in this account (the mirror observes only)"
        probs = self._venue_problems(ad)
        if probs:
            return "the account does not hold exactly the mirror book: " + "; ".join(probs[:5])
        if self.cfg.live:
            cash = ad.account_cash()
            have = _num((cash or {}).get("total_cash"))
            if have is None:
                return "the account reports no cash claim"
            if self.book.cash() > have + CASH_TOL_USD:
                return f"the book's cash ${self.book.cash():,.2f} exceeds the account's ${have:,.2f}"
        return None

    # -------------------------------------------------------------- the decision
    def _validate(self, p, info: dict, now: datetime) -> str | None:
        if not isinstance(p, dict) or p.get("kind") != INTENTS_KIND or p.get("schema") != SCHEMA:
            return "not a mirror intents payload"
        if p.get("replay"):
            return "the brain answered with a replay"
        if p.get("session") != info["session"]:
            why = "; ".join(map(str, (p.get("problems") or [])[:2]))
            return f"the payload's session is {p.get('session')!r}, not {info['session']}" + (f" ({why})" if why else "")
        asof = _parse(p.get("asof_utc"))
        if asof is None:
            return "the payload has no asof_utc"
        if _iso(asof) < info["decide_utc"]:
            return f"computed at {p['asof_utc']}, before the decision bar closed ({info['decide_utc']})"
        age = (now - asof).total_seconds()
        if age < -CLOCK_SKEW_S:
            return f"stamped {-age:.0f} s in the future"
        if age > INTENTS_MAX_AGE_S:
            return f"{age:.0f} s old"
        if not isinstance(p.get("engines"), dict) or not isinstance(p.get("prices"), dict):
            return "the payload has no engines or no prices"
        return None

    def _decide(self, ad, info: dict, wake, stop, until: datetime) -> None:
        session = info["session"]
        while True:
            now = self.clock()
            if now >= info["plan_by"]:
                self._skip(session, f"nothing usable before {_iso(info['plan_by'])}: {self._why}")
                return
            why = self._pretrade(ad)
            payload = None
            if why is None:
                payload, reason = self.brain.intents(info["decide_utc"]) if self.brain is not None else (None, "no_brain")
                now = self.clock()
                why = self._validate(payload, info, now) if payload is not None else f"no intents ({reason})"
                self.brain_status["intents"] = {"ok": why is None, "reason": why or "ok", "utc": _iso(now)}
            if why is None:
                break
            self._why = why
            if self._pause(INTENTS_RETRY_S, wake, stop, until):
                return
        self._why = None
        self._start(ad, info, payload)
        self._drive(ad, wake, stop, until)

    def _skip(self, session: str, reason: str) -> None:
        row = {"session": session, "outcome": "skipped", "reason": one_line(reason, 400), "utc": _iso(self.clock())}
        self.state["history"] = (list(self.state.get("history") or []) + [row])[-HISTORY_KEEP:]
        self.state["last_session"] = session
        self.state["last_run"] = row
        self._save()
        self._journal("session_skipped", **row)
        self._say("red" if self.cfg.live else "warn", f"{session}: NO TRADE — {row['reason']}. The sleeves keep "
                  f"yesterday's holdings; Composer rebalanced on its own.", key=f"skip:{session}")

    def _targets(self, payload: dict) -> dict:
        """the plan's targets for the active sleeves; Composer's rebalance rule rides on the payload"""
        out = {}
        for name in self._active():
            row = (payload.get("engines") or {}).get(name)
            if not isinstance(row, dict):
                continue
            s = self.book.sleeves[name]
            rule, corridor = row.get("rule"), _num(row.get("corridor"))
            if rule == mc.RULE_DAILY:
                s.rule, s.corridor = mc.RULE_DAILY, None
            elif rule == mc.RULE_THRESHOLD and corridor is not None and 0 < corridor < 1:
                s.rule, s.corridor = mc.RULE_THRESHOLD, corridor
            else:
                out[name] = {"status": "unavailable", "note": f"unknown rebalance rule {rule!r} / corridor {row.get('corridor')!r}"}
                continue
            out[name] = {"status": row.get("status"), "target": row.get("target"), "version": row.get("version"),
                         "note": row.get("note")}
        return out

    def _venue_prices(self, ad, symbols, prices: dict, notes: dict) -> tuple:
        """live only: every symbol the plan would trade against the venue's own quote. Returns (prices
        with the failures removed and the brain's estimates replaced by the venue's quote, {symbol:
        why it failed})."""
        out, bad = dict(prices), {}
        t0 = time.monotonic()
        for sym in sorted(symbols):
            ref = _num(prices.get(sym))
            if time.monotonic() - t0 > QUOTE_BUDGET_S:
                bad[sym] = f"no venue quote (the cross-check ran past {QUOTE_BUDGET_S:.0f} s)"
                out.pop(sym, None)
                continue
            try:
                px, source = ad.spot_ex(sym)
            except Exception as exc:  # noqa: BLE001
                bad[sym] = f"no venue quote ({one_line(exc, 80)})"
                out.pop(sym, None)
                continue
            px = _num(px)
            if px is None or px <= 0 or source not in QUOTE_SOURCES:
                bad[sym] = f"venue quote unusable ({px!r} from {source})"
                out.pop(sym, None)
                continue
            band = self.cfg.est_quote_band if sym in notes else self.cfg.quote_band
            if ref is None or abs(px / ref - 1.0) > band:
                bad[sym] = f"the venue quotes {px:.4f}, the brain {ref!r} (band {band:.1%})"
                out.pop(sym, None)
                continue
            if sym in notes:
                out[sym] = px                       # the brain's price was an estimate: size on the quote
        return out, bad

    @staticmethod
    def _plan_symbols(plan: dict) -> set:
        syms = {o["symbol"] for o in plan["sells"]} | {c["symbol"] for c in plan["crosses"]}
        for asks in plan["buy_asks"].values():
            syms |= set(asks)
        return syms

    def _apply_credits(self, ad) -> list:
        notes, keep = [], []
        for r in self.state.get("requests") or []:
            if r.get("kind") != "credit":
                keep.append(r)
                continue
            name, amt = r.get("sleeve"), _num(r.get("amount"))
            ok = name in self.book.sleeves and amt is not None
            why = None if ok else "unknown sleeve or amount"
            if ok and self.cfg.live and amt > 0:
                have = _num((ad.account_cash() or {}).get("total_cash"))
                if have is None or self.book.cash() + amt > have + CASH_TOL_USD:
                    ok, why = False, f"the account's cash ({have!r}) does not cover the book's plus the credit"
            if ok:
                self.book.sleeves[name].cash += amt
                notes.append(f"{name} {'credited' if amt > 0 else 'debited'} ${abs(amt):,.2f} ({r.get('note') or 'no note'})")
                self._journal("credit", **r)
            else:
                notes.append(f"credit {r.get('id')} REFUSED: {why}")
                self._say("red", f"credit of ${amt!r} to {name} refused: {why}. Re-submit when it holds.")
                self._journal("credit_refused", why=why, **r)
        self.state["requests"] = keep
        return notes

    def _start(self, ad, info: dict, payload: dict) -> None:
        session, now = info["session"], self.clock()
        prices = {s: p for s, p in ((s, _num(p)) for s, p in payload["prices"].items()) if p is not None and p > 0}
        price_notes = {s: str(n) for s, n in (payload.get("price_notes") or {}).items() if s in prices}
        notes = self._apply_credits(ad)
        transfers = [r for r in self.state.get("requests") or [] if r.get("kind") == "transfer"]
        self.state["requests"] = [r for r in self.state.get("requests") or [] if r.get("kind") != "transfer"]
        asks = [{"from": r.get("from"), "to": r.get("to"), "amount": r.get("amount")} for r in transfers]
        targets = self._targets(payload)
        pre = {}
        for name, s in self.book.sleeves.items():
            try:
                pre[name] = round(mc.equity(s, prices), 2)
            except mc.MirrorError:
                pre[name] = None
        plan = mc.build_plan(self.book, targets, prices, session, self.cfg.core, asks)
        dropped = {}
        if self.cfg.live:
            checked = self._plan_symbols(plan)
            prices, dropped = self._venue_prices(ad, checked, prices, price_notes)
            if dropped or any(s in price_notes for s in checked):
                plan = mc.build_plan(self.book, targets, prices, session, self.cfg.core, asks)
                extra = self._plan_symbols(plan) - checked
                if extra:                          # cannot happen (a rebuilt plan only loses sleeves); never trade unchecked
                    raise mc.MirrorError(f"the rebuilt plan trades unchecked symbols {sorted(extra)}")
            for sym, why in sorted(dropped.items()):
                notes.append(f"{sym}: {why}; the sleeves that hold or want it sit this session out")
        elif price_notes:
            used = sorted(self._plan_symbols(plan) & set(price_notes))
            if used:
                notes.append("paper fills at the brain's ESTIMATED price for " + ", ".join(used))
        for t, r in zip(plan["transfers"], transfers):
            if t["status"] == "refused":
                notes.append(f"transfer {r.get('id')} of ${r.get('amount')!r} {r.get('from')} -> {r.get('to')} REFUSED "
                             f"(a sleeve is out of this plan, or the amount exceeds the giver's equity): re-submit")
        mc.apply_crosses(self.book, plan)
        labels = {n: (payload["engines"].get(n) or {}).get("label") for n in targets}
        self.state["run"] = {"session": session, "phase": "sells", "started_utc": _iso(now),
                             "decide_utc": info["decide_utc"], "cancel_utc": _iso(info["cancel_at"]),
                             "close_utc": _iso(info["close_at"]), "intents_asof": payload.get("asof_utc"),
                             "labels": labels, "pre_equity": pre, "plan": plan, "orders": {}, "notes": notes,
                             "price_notes": {s: n for s, n in price_notes.items() if s in plan["prices"]},
                             "dropped": dropped, "quotes": payload.get("quotes")}
        marks = dict((self.state.get("marks") or {}).get("prices") or {})
        marks.update(prices)
        self.state["marks"] = {"prices": marks, "asof": payload.get("asof_utc")}
        self._save()
        self._journal("plan", session=session, intents_asof=payload.get("asof_utc"),
                      sleeves={n: {k: d.get(k) for k in ("action", "reason", "gap", "deltas", "target", "version")}
                               for n, d in plan["sleeves"].items()},
                      crosses=plan["crosses"], sells=[{k: o[k] for k in ("id", "symbol", "qty", "asks", "ref")} for o in plan["sells"]],
                      buy_asks=plan["buy_asks"], transfers=plan["transfers"], notes=notes)

    # -------------------------------------------------------------- orders
    def _drive(self, ad, wake, stop, until: datetime) -> None:
        while True:
            if self._advance(ad):
                self._finish(ad)
                return
            if self.halt_state().get("halted"):
                return                              # the halt path settles what is in flight
            if self._pause(ORDER_POLL_S, wake, stop, until):
                return

    def _abort_run(self, ad, why: str) -> None:
        """halted with a run in flight: send nothing new, cancel what works, book what filled"""
        run = self.state.get("run")
        if not run or ad is None:
            return
        if not run.get("aborted"):
            run["aborted"] = why
            run.setdefault("notes", []).append(f"run aborted: {why}")
            self._save()
        if self._advance(ad, abort=True):
            self._finish(ad)

    def _advance(self, ad, abort: bool = False) -> bool:
        """work the run's orders once; True when every order is booked"""
        run = self.state["run"]
        plan = run["plan"]
        past = abort or self.clock() >= (_parse(run["cancel_utc"]) or self.clock())
        if run["phase"] == "sells":
            waiting = [o for o in plan["sells"] if not self._work(ad, o, run["orders"], past, place=not abort)]
            if waiting:
                return False
            if any(t["status"] == "planned" for t in plan["transfers"]) and not plan.get("transfers_applied"):
                mc.apply_transfers(self.book, plan)
            if past:
                plan["buys"] = []
                if plan["buy_asks"]:
                    run.setdefault("notes", []).append("buys NOT sent: " + (run.get("aborted") or "the window closed "
                                                       "before the sells were booked"))
            else:
                mc.size_buys(self.book, plan, None, self.cfg.core)
            run["phase"] = "buys"
            self._save()
        if run["phase"] == "buys":
            past = abort or self.clock() >= (_parse(run["cancel_utc"]) or self.clock())
            waiting = [o for o in plan["buys"] if not self._work(ad, o, run["orders"], past, place=not abort)]
            return not waiting
        return True

    def _work(self, ad, o: dict, recs: dict, past: bool, place: bool = True) -> bool:
        """advance one venue order; True once it is booked. past: the window is over (cancel what still
        works, send nothing). place: new orders may be sent."""
        if o.get("applied"):
            return True
        oid = o["id"]
        rec = recs.setdefault(oid, {"state": "new", "tries": 0})
        res = None
        if rec["state"] == "new":
            if past or not place:
                return self._book(o, rec, 0, None, 0.0, "not sent: " + ("the window closed" if place else "stopped"))
            rec.update(state="intent", intent_utc=_iso(self.clock()))
            self._save()                           # WRITE-AHEAD: the id is on disk before the venue sees it
            res = self._place(ad, o, rec)
        elif rec["state"] == "intent":
            # a placement whose outcome was never recorded (a crash, a raise): the venue is asked first
            res = self._find(ad, oid, rec)
            if res is _UNKNOWN:
                return False
            if res is None:
                if past or not place or rec.get("tries", 0) >= PLACE_TRIES:
                    return self._book(o, rec, 0, None, 0.0, "never reached the venue"
                                      + (f" ({rec['error']})" if rec.get("error") else ""))
                res = self._place(ad, o, rec)
            else:
                rec.update(state="placed", order_ref=res.get("order_ref"))
        else:
            res = self._find(ad, oid, rec)
            if res is _UNKNOWN:
                return False
            if res is None and self._dry is not None and place and not past:
                res = self._place(ad, o, rec)      # a paper adapter forgets its orders on a restart
            elif res is None:
                if self._dry is not None:
                    return self._book(o, rec, 0, None, 0.0, "not sent: the paper adapter restarted")
                self._stuck(rec, oid, "the venue has no record of an order it acknowledged")
                return False
        if res is None:
            return False
        return self._settle(ad, o, rec, res, past)

    def _place(self, ad, o: dict, rec: dict):
        rec["tries"] = int(rec.get("tries") or 0) + 1
        qty = int(o["qty"]) if o["side"] == mc.BUY else -int(o["qty"])
        try:
            res = ad.place_stock_order(o["symbol"], qty, "MKT", tif="DAY", ref_price=o.get("ref"),
                                       client_order_id=o["id"])
        except Exception as exc:  # noqa: BLE001  rejected, or no ack: the next pass asks the venue what happened
            rec["error"] = one_line(exc, 240)
            logger.warning("mirror[%s] order %s placement raised: %s", self.cfg.name, o["id"], rec["error"])
            self._save()
            return None
        rec.update(state="placed", order_ref=res.get("order_ref"), placed_utc=_iso(self.clock()))
        self._save()
        return res

    def _find(self, ad, oid: str, rec: dict):
        try:
            return ad.find_stock_order(oid)
        except Exception as exc:  # noqa: BLE001
            rec["find_error"] = one_line(exc, 240)
            return _UNKNOWN

    def _stuck(self, rec: dict, oid: str, why: str) -> None:
        if rec.get("stuck") != why:
            rec["stuck"] = why
            self._save()
        self._say("red", f"order {oid} is UNRESOLVED: {why}. The book is not updated for it and nothing new is "
                         f"planned until it resolves; check the account.", key=f"stuck:{oid}:{why}")

    def _fill_terms(self, ad, o: dict, res: dict, rec: dict) -> tuple:
        """(price, commission) of what an order executed; the reference price, flagged, when the venue
        reports none (never zero, never a guess that is not on the record)"""
        price, comm = _num(res.get("fill_price")), _num(res.get("commission"))
        if (price is None or comm is None) and hasattr(ad, "stock_order_fills"):
            try:
                f = ad.stock_order_fills(o["id"]) or {}
            except Exception as exc:  # noqa: BLE001
                f = {}
                rec["fills_error"] = one_line(exc, 160)
            price = price if price is not None else _num(f.get("avg_price"))
            comm = comm if comm is not None else _num(f.get("commission"))
        if price is None or price <= 0:
            price = _num(o.get("ref"))
            rec["price_estimated"] = True
        if comm is None:
            comm = 0.0
            rec["commission_unreported"] = True
        return price, max(comm, 0.0)

    def _settle(self, ad, o: dict, rec: dict, res: dict, past: bool) -> bool:
        status = res.get("status")
        if status == "working":
            if not past:
                return False
            try:
                ad.cancel_stock_order(rec.get("order_ref") or res.get("order_ref"))
            except Exception as exc:  # noqa: BLE001  filled first, or an ambiguous ack: the venue decides
                rec["cancel_error"] = one_line(exc, 240)
            res = self._find(ad, o["id"], rec)
            if res is _UNKNOWN or res is None or res.get("status") not in ("filled", "cancelled"):
                self._stuck(rec, o["id"], "still working (or unreadable) after the cancel"
                            + (f": {rec['cancel_error']}" if rec.get("cancel_error") else ""))
                return False
            status = res.get("status")
        if status == "filled":
            qty = int(o["qty"])
            if res.get("filled_qty") is not None:   # resolved from execution reports: completeness unproven
                qty = max(0, min(qty, int(res["filled_qty"])))
            how = "filled"
        elif status == "cancelled":
            qty = int(res.get("filled_qty") or 0)
            if qty <= 0 and hasattr(ad, "stock_order_fills"):
                try:                                # a cancelled row can lack the executions it carries
                    qty = int((ad.stock_order_fills(o["id"]) or {}).get("filled_qty") or 0)
                except Exception as exc:  # noqa: BLE001
                    rec["fills_error"] = one_line(exc, 160)
            qty = max(0, min(qty, int(o["qty"])))
            how = "cancelled" + (f" ({one_line(res['reason'], 120)})" if res.get("reason") else "")
        else:
            self._stuck(rec, o["id"], f"the venue answered status {status!r}")
            return False
        price, comm = (None, 0.0)
        if qty:
            price, comm = self._fill_terms(ad, o, res, rec)
            if price is None:
                self._stuck(rec, o["id"], f"{qty} filled with no price from the venue and no reference")
                return False
        return self._book(o, rec, qty, price, comm, how)

    def _book(self, o: dict, rec: dict, qty: int, price, comm: float, how: str) -> bool:
        split = mc.book_fill(self.book, o, qty, price if qty else None, comm if qty else 0.0)
        rec.update(state="booked", how=how, booked_utc=_iso(self.clock()))
        rec.pop("stuck", None)
        if qty and self._dry is None and rec.get("commission_unreported"):
            self.state["commission_pending"] = list(self.state.get("commission_pending") or []) + [
                {"id": o["id"], "split": split, "utc": rec["booked_utc"]}]
        self._save()
        self._journal("fill", id=o["id"], side=o["side"], symbol=o["symbol"], asked=o["qty"], filled=qty, price=price,
                      ref=o.get("ref"), commission=comm, split=split, how=how,
                      price_estimated=bool(rec.get("price_estimated")))
        if qty and rec.get("price_estimated"):
            self._say("red", f"order {o['id']}: {qty} {o['symbol']} booked at the REFERENCE price {price} because the "
                             f"venue reported no fill price. The book's cash is off by the slippage; compare with the "
                             f"account.", key=f"est:{o['id']}")
        if qty < int(o["qty"]) and not how.startswith("not sent"):
            self._say("warn", f"order {o['id']}: {qty} of {o['qty']} {o['symbol']} filled ({how})", key=f"short:{o['id']}")
        return True

    # -------------------------------------------------------------- the end of a run
    def _summary(self, run: dict) -> dict:
        plan = run["plan"]
        orders = []
        for o in plan["sells"] + (plan.get("buys") or []):
            rec = (run.get("orders") or {}).get(o["id"]) or {}
            slip = None
            if o.get("filled") and o.get("price") and o.get("ref"):
                slip = round((o["price"] / o["ref"] - 1.0) * (1 if o["side"] == mc.BUY else -1) * 1e4, 2)
            orders.append({"id": o["id"], "side": o["side"], "symbol": o["symbol"], "qty": o["qty"],
                           "filled": o.get("filled", 0), "price": o.get("price"), "ref": o.get("ref"),
                           "commission": o.get("commission", 0.0), "cost_bps": slip, "how": rec.get("how"),
                           "split": o.get("split") or {}})
        sleeves = {}
        for name, d in plan["sleeves"].items():
            s = self.book.sleeves.get(name)
            sleeves[name] = {"action": d.get("action"), "reason": d.get("reason"), "gap": d.get("gap"),
                             "target": d.get("target"), "version": d.get("version"),
                             "label": (run.get("labels") or {}).get(name),
                             "pre_equity": (run.get("pre_equity") or {}).get(name),
                             "cash": round(s.cash, 4) if s else None, "shares": dict(sorted(s.shares.items())) if s else {}}
        acts = {d.get("action") for d in plan["sleeves"].values()}
        outcome = ("aborted" if run.get("aborted") else "traded" if orders or plan["crosses"] else
                   "no-targets" if acts <= {"skip"} else "held")
        return {"session": run["session"], "outcome": outcome, "utc": _iso(self.clock()), "intents_asof": run.get("intents_asof"), "sleeves": sleeves,
                "orders": orders, "crosses": plan["crosses"], "transfers": plan["transfers"],
                "notes": list(run.get("notes") or []), "price_notes": run.get("price_notes") or {},
                "dropped": run.get("dropped") or {}, "prices": plan.get("prices") or {}}

    def _finish(self, ad) -> None:
        run = self.state["run"]
        mc.finish(self.book, run["plan"])
        row = self._summary(run)
        self.state["history"] = (list(self.state.get("history") or []) + [row])[-HISTORY_KEEP:]
        self.state["last_session"] = run["session"]
        self.state["last_run"] = row
        self.state["run"] = None
        self.state["check"] = None
        self._save()
        self._journal("session", **row)
        parts = []
        for name, d in row["sleeves"].items():
            if d["action"] == "trade":
                parts.append(f"{name} → " + " ".join(f"{t} {w:.0%}" for t, w in (d["target"] or {}).items()))
            else:
                parts.append(f"{name} {d['action']} ({d['reason']})")
        fills = [f"{'sold' if o['side'] == mc.SELL else 'bought'} {o['filled']}/{o['qty']} {o['symbol']}"
                 + (f" @{o['price']:.2f}" if o.get("price") else "") for o in row["orders"]]
        cost = [o["cost_bps"] for o in row["orders"] if o.get("cost_bps") is not None]
        self._say("info", f"{row['session']} {row['outcome']}: " + " · ".join(parts)
                  + (" | " + ", ".join(fills) if fills else "")
                  + (f" | cost vs the decision price {sum(cost) / len(cost):+.1f} bps avg" if cost and self.cfg.live else "")
                  + (" | NOTES: " + "; ".join(row["notes"]) if row["notes"] else ""), key=f"done:{row['session']}")

    def _post_check(self, ad, session: str) -> None:
        """after the session's run: the account must hold the book. A mismatch seen CHECK_STRIKES times,
        CHECK_GAP_S apart, halts the book (one read can catch a position report in flight)."""
        self._true_up(ad)
        chk = self.state.get("check") or {}
        if chk.get("session") == session and chk.get("done"):
            return
        now = self.clock()
        last = _parse(chk.get("utc")) if chk.get("session") == session else None
        if last and (now - last).total_seconds() < CHECK_GAP_S:
            return
        probs = self._venue_problems(ad)
        strikes = (int(chk.get("strikes") or 0) + 1) if (probs and chk.get("session") == session) else (1 if probs else 0)
        chk = {"session": session, "utc": _iso(now), "strikes": strikes, "problems": probs[:8],
               "done": not probs or strikes >= CHECK_STRIKES}
        self.state["check"] = chk
        self._save()
        if probs and chk["done"]:
            self._journal("account_mismatch", session=session, problems=probs)
            if self.cfg.live:
                self.halt("the account does not hold the mirror book: " + "; ".join(probs[:4]), by="mirror")
            self._say("red", f"{session}: the account does NOT hold the mirror book — " + "; ".join(probs[:6])
                      + (". HALTED until /resume." if self.cfg.live else ""), key=f"mismatch:{session}")

    def _true_up(self, ad) -> None:
        """commissions the venue had not reported when their fills were booked"""
        pend = list(self.state.get("commission_pending") or [])
        if not pend or not hasattr(ad, "stock_order_fills"):
            return
        if self._trued_at is not None and (self.clock() - self._trued_at).total_seconds() < TRUE_UP_EVERY_S:
            return
        self._trued_at = self.clock()
        left, changed = [], False
        for p in pend:
            try:
                comm = _num((ad.stock_order_fills(p["id"]) or {}).get("commission"))
            except Exception:  # noqa: BLE001
                comm = None
            split = {k: int(v) for k, v in (p.get("split") or {}).items() if k in self.book.sleeves and int(v) > 0}
            if comm is None or not split:
                booked = _parse(p.get("utc"))
                if split and booked and (self.clock() - booked).total_seconds() < 3 * 86400:
                    left.append(p)                  # still unreported: asked again for three days
                continue
            total = sum(split.values())
            for name, q in split.items():
                self.book.sleeves[name].cash -= comm * q / total
            self._journal("commission_true_up", id=p["id"], commission=comm, split=split)
            changed = True
        if changed or len(left) != len(pend):
            self.state["commission_pending"] = left
            self._save()

    # -------------------------------------------------------------- flatten (live; loop thread)
    def _flatten_step(self, ad, h: dict) -> bool:
        """work a requested flatten; True when it is finished (or cancelled and settled)"""
        fid = h.get("flatten_id")
        cancelled = bool(h.get("flatten_cancelled"))
        if ad is None:
            return False
        if self.state.get("run"):
            self._abort_run(ad, "kill")
            if self.state.get("run"):
                return False
        fl = self.state.get("flatten")
        if not fl or fl.get("id") != fid:
            if cancelled:
                return self._flatten_done(h, "cancelled before any order was sent")
            if not self._rth(self.clock()):
                self._say("warn", "flatten queued: the session is shut; the sells go at the next open", key=f"flat-wait:{fid}")
                return False
            venue = (ad.positions_snapshot().get("stocks") or {}) if hasattr(ad, "positions_snapshot") else None
            marks = (self.state.get("marks") or {}).get("prices") or {}
            orders = []
            for sym, total in self.book.positions().items():
                asks = {n: s.shares[sym] for n, s in self.book.sleeves.items() if s.shares.get(sym)}
                qty = total
                if venue is not None:
                    qty = min(total, max(int(venue.get(sym, 0) or 0), 0))   # never sell more than the account holds
                    if qty < total:
                        self._say("red", f"flatten: the book holds {total} {sym}, the account {venue.get(sym, 0)}: "
                                         f"selling {qty}", key=f"flat-short:{fid}:{sym}")
                        asks = mc.allocate(qty, asks)
                if qty > 0:
                    orders.append({"id": f"mirror-flat-{fid}-{sym}", "side": mc.SELL, "symbol": sym, "qty": qty,
                                   "asks": {k: v for k, v in asks.items() if v}, "ref": _num(marks.get(sym)), "applied": False})
            fl = {"id": fid, "orders": orders, "recs": {}, "started_utc": _iso(self.clock())}
            self.state["flatten"] = fl
            self._save()
            self._journal("flatten", id=fid, orders=[{k: o[k] for k in ("id", "symbol", "qty", "asks")} for o in orders])
        waiting = [o for o in fl["orders"] if not self._work(ad, o, fl["recs"], past=cancelled, place=not cancelled)]
        if waiting:
            return False
        return self._flatten_done(h, "cancelled" if cancelled else None)

    def _flatten_done(self, h: dict, note: str | None) -> bool:
        fl = self.state.get("flatten") or {}
        sold = [f"{o.get('filled', 0)}/{o['qty']} {o['symbol']}" + (f" @{o['price']:.2f}" if o.get("price") else "")
                for o in fl.get("orders") or []]
        with self.halt_lock:
            cur = dict(self._halt or {})
            if cur.get("flatten_id") == h.get("flatten_id"):
                cur["flatten_done"] = True
                self._write_halt(cur)
        left = self.book.positions()
        self._journal("flatten_done", id=h.get("flatten_id"), note=note, sold=sold, left=left, cash=self.book.cash())
        self._say("red" if left and not note else "info",
                  f"flatten {note or 'complete'}: " + (", ".join(sold) or "nothing was sent")
                  + f" | book cash ${self.book.cash():,.2f}" + (f" | STILL HELD {left}" if left else ""),
                  key=f"flat-done:{h.get('flatten_id')}")
        return True

    # -------------------------------------------------------------- what the API reads
    def _publish(self) -> None:
        marks = self.state.get("marks") or {}
        sleeves, total = {}, 0.0
        for name, s in self.book.sleeves.items():
            try:
                eq = mc.equity(s, marks.get("prices") or {})
                w = mc.weights(s, marks.get("prices") or {})
            except mc.MirrorError:
                eq, w = None, None
            total = None if (eq is None or total is None) else total + eq
            sleeves[name] = {"equity": None if eq is None else round(eq, 2), "cash": round(s.cash, 2),
                             "shares": dict(sorted(s.shares.items())),
                             "weights": None if w is None else {k: round(v, 5) for k, v in w.items()},
                             "rule": s.rule, "corridor": s.corridor, "version": s.version, "last_trade": s.last_trade,
                             "frozen": name in (self.state.get("frozen") or [])}
        run = self.state.get("run")
        self._view = {
            "name": self.cfg.name, "mode": "live" if self.cfg.live else "paper", "engines": list(self.cfg.engines),
            "book": {"equity": None if total is None else round(total, 2), "cash": round(self.book.cash(), 2),
                     "positions": self.book.positions(), "sleeves": sleeves, "marks_asof": marks.get("asof")},
            "seeded": self.state.get("seeded") or {}, "last_session": self.state.get("last_session"),
            "run": None if not run else {"session": run["session"], "phase": run["phase"], "aborted": run.get("aborted"),
                                         "orders": {k: {x: v.get(x) for x in ("state", "how", "stuck", "error", "tries")}
                                                    for k, v in (run.get("orders") or {}).items()}},
            "last_run": self.state.get("last_run"), "check": self.state.get("check"),
            "pending_requests": list(self.state.get("requests") or []),
            "commission_pending": len(self.state.get("commission_pending") or []),
            "flatten": None if not self.state.get("flatten") else
            {"id": self.state["flatten"].get("id"),
             "orders": [{k: o.get(k) for k in ("id", "symbol", "qty", "filled", "price", "applied")}
                        for o in self.state["flatten"].get("orders") or []]},
            "saved_utc": self.state.get("saved_utc"), "seq": self.state.get("seq"),
        }

    def view(self, history: int = 0) -> dict:
        """the book as last saved, plus the halt and the brain's status (any thread; never raises)"""
        try:
            out = dict(self._view)
            out["halt"] = self.halt_state()
            out["waiting_on"] = self._why
            out["last_error"] = self.last_error
            out["brain"] = dict(self.brain_status)
            out["archived_state"] = self.archived_state
            if history:
                out["history"] = list(self.state.get("history") or [])[-history:]
            return out
        except Exception as exc:  # noqa: BLE001
            return {"name": self.cfg.name, "error": one_line(repr(exc))}

    def health(self) -> dict:
        try:
            h = self.halt_state()
            run = self._view.get("run")
            return {"mode": "live" if self.cfg.live else "paper", "engines": list(self.cfg.engines),
                    "halted": bool(h.get("halted")), "flatten_pending": bool(h.get("flatten") and not h.get("flatten_done")),
                    "last_session": self._view.get("last_session"), "run_phase": (run or {}).get("phase"),
                    "last_outcome": (self._view.get("last_run") or {}).get("outcome"),
                    "waiting_on": self._why, "last_error": self.last_error,
                    "brain_ok": bool((self.brain_status.get("session") or {}).get("ok"))}
        except Exception as exc:  # noqa: BLE001
            return {"error": one_line(repr(exc))}


# ------------------------------------------------------------------ building the books from settings
def parse_weights(text: str) -> dict:
    """'HG:0.29,KMLM:0.29,...' -> {name: weight}; ValueError unless every weight is positive and they
    sum to 1"""
    out = {}
    for part in (text or "").split(","):
        if not part.strip():
            continue
        name, _, w = part.partition(":")
        out[name.strip()] = float(w)
    if not out or any((not math.isfinite(w)) or w <= 0 for w in out.values()) or abs(sum(out.values()) - 1.0) > 1e-6:
        raise ValueError(f"MIRROR_WEIGHTS must be positive and sum to 1: {text!r}")
    return out


def build(settings, alert=None, brain=None) -> dict:
    """{"live": MirrorManager, "dry": MirrorManager} per the settings (either may be absent). An engine
    is LIVE only when it is named in MIRROR_LIVE_ENGINES AND the service itself trades for real (TWS
    credentials, DRY_RUN off); every other engine runs in the paper book."""
    weights = parse_weights(settings.mirror_weights)
    capital = {e: float(settings.mirror_capital_usd) * w for e, w in weights.items()}
    asked = [e.strip() for e in (settings.mirror_live_engines or "").split(",") if e.strip()]
    unknown = [e for e in asked if e not in weights]
    if unknown:
        raise ValueError(f"MIRROR_LIVE_ENGINES names {unknown}, which MIRROR_WEIGHTS does not")
    real = bool(settings.tws_userid and settings.tws_password) and not settings.dry_run
    live = tuple(e for e in weights if e in asked) if real else ()
    if asked and not real:
        logger.warning("mirror: MIRROR_LIVE_ENGINES=%s ignored - the service is not trading for real (no TWS "
                       "credentials, or DRY_RUN): every engine runs in the paper book", asked)
    paper = tuple(e for e in weights if e not in live)
    brain = brain or HttpBrain(settings.mirror_brain_url, settings.mirror_api_token)
    core = mc.Config()
    out = {}

    def cfg(name, is_live, engines, path):
        return MirrorConfig(name=name, live=is_live, engines=engines, capital=capital, state_path=path,
                            decide_offset_s=float(settings.mirror_decide_offset_s),
                            cancel_before_close_s=float(settings.mirror_cancel_before_close_s),
                            quote_band=float(settings.mirror_quote_band),
                            blend_enabled=bool(settings.blend_enabled), core=core)
    if live:
        out["live"] = MirrorManager(cfg("live", True, live, settings.mirror_state_path), brain=brain, alert=alert)
    if paper:
        out["dry"] = MirrorManager(cfg("dry", False, paper, settings.mirror_dry_state_path), brain=brain, alert=alert)
    return out
