"""Composer mirror: the executor strategy (composer/IBKR_MIRROR.md).

One brain, two brokers. The keyless brain (composer/scripts/mirror_brain.py) publishes, pinned to the
decision instant, the target weights each approved symphony tree holds and the prices it was
evaluated on (contract schema 2). This module turns them into whole-share orders on the IBKR account
through the adapter contract (SELLS: place_stock_order MKT DAY; BUYS: place_limit_order DAY;
find_stock_order, cancel_stock_order, stock_order_fills), with the accounting in app/mirror_core.py:
virtual sleeves, Composer's daily / threshold rule, cross-sleeve netting, sells booked before buys are
sized from the cash actually held, dividend receivables and splits.

A MirrorManager is ONE book. The service builds up to two: a DRY book (its own private DryAdapter:
no venue, no account reads; fills at the brain's reference price) for every engine not yet live,
and a LIVE book for the engines named in MIRROR_LIVE_ENGINES. MIRROR_ENABLED=false (the default)
builds neither.

Threads
- the LOOP thread alone calls tick(): it owns the book, the state file and every adapter call
- API threads call halt() / resume() (the halt file, under halt_lock), the request_*() methods (the
  inbox file, under inbox_lock; the loop thread applies them) and view() / health() (a published
  snapshot)

A session, in the loop thread
  1 the brain's clock (/mirror/session) says when the decision bar ENDS (decide_utc, used as given)
    and when the session closes. An unreadable clock is never a silent day: the loop is asked back
    every minute (a PAPER book: every five, it shares the loop with a live strategy), it is said
    after ten, and a recorded NO TRADE is written at 16:00 ET. The brain is asked only over https
    (or on this machine): the API token never rides plain http
  2 at decision + offset: the intents (schema 2: PINNED to the decision instant, its bar complete,
    built after that instant and not in the future). A pinned payload is immutable - the brain
    caches it by its instant and never rebuilds it - so its AGE is no test: a restart at 15:57 is
    given the payload built at 15:54:32 and trades it. Lateness is bounded by plan_by, price drift by
    the venue quote band and by the fresh quote the limit buys are priced on. Until the decision bar
    is published the brain answers 503: a transient reason (its body's error and detail are carried
    into the day's record), retried every 3 s inside the tick (a PAPER book: once more after 10 s,
    then through the loop). Then the splits the
    payload lists (sleeve shares rescaled), then the pre-trade gates (live: the account must hold
    exactly the book, the account's cash must cover the book's, the blend must be off). A refusal
    that cannot change inside the window (the blend on, no sleeve) is a NO TRADE at once; the others
    are retried
  3 dividends: a receivable per sleeve from the shares it held at the close before the ex-date
    (the history also records every change of shares OUTSIDE a run: a flatten, a split, an
    adjustment), settled from the pay date - left open while the brain does not know that date,
    ex + 7 assumed only ten days after the ex-date; then the plan (mirror_core.build_plan). A LIVE
    sleeve is planned only when the payload's own sync row attests its tree (state "ok"); a paper
    book trades regardless and notes it. Live: every symbol it would
    trade is cross-checked against the venue's own quote, and a symbol that fails takes its sleeves
    out of the plan. Everything up to here is undone in memory if a halt, a wake or an error lands
    before the run is on disk
  4 SELLS (market DAY), each under a deterministic id written to disk BEFORE the venue sees it;
    booked once, at the terminal state; then transfers; then BUYS: the venue quote of each is read
    again and the order is a LIMIT at quote x (1 + buy_cushion), sized AT that limit from actual
    cash, so a buy can never cost more than it was sized at; leftovers cancelled before the close
    and booked at what filled. The halt is re-read before every order and no order is sent after the
    cancel instant
  5 afterwards the account is compared with the book; a mismatch that persists halts the book.
    The session's closing line is RED (paper: a warning) whenever an active sleeve was not traded

What is never guessed
- "the venue has no such order" proves nothing unless the order is from today (ET) AND either the
  adapter's order history is complete or the venue shows it neither open nor executed today (both
  requests answered): otherwise the order is UNRESOLVED - never booked as zero, said once a day -
  until the venue answers or the operator states what it did (POST /mirror/resolve)
- the operator's statement is taken only where the book has no better source: only for an order
  flagged UNRESOLVED, after the venue was asked once more (its own answer wins), never a buy above
  its limit or a price more than 20% from the order's reference; an adjustment or a debit that would
  put a sleeve in debt needs "force": true
- a fill the venue reports no price for is booked at the most it can have cost (a buy: its limit;
  a sell: its reference), flagged and said in red
- a cancelled order's executed quantity that cannot be read is UNRESOLVED too
- a state file that cannot be written latches the book: no run order is placed until a save succeeds
- any share-count divergence (a manual trade, a split the brain listed late) is repaired by the
  operator through POST /mirror/adjust, never by the book on its own

/kill's flatten runs in ROUNDS under one id: what its orders did is settled first, whatever the halt
file says; while the halt still wants it and both the book and the account still hold shares, the
remainder is sold again, at widening gaps (5 s, 15 s, 60 s, then every 5 minutes) for up to 30 minutes
of OPEN session; a symbol with an unresolved run order is held back and named, the others are sold.
When it ends it reads the ACCOUNT: it says "complete" only if the account holds no stock at all.

KNOWN LIMITS, recorded by the second review round (not built)
- The live "has the dividend's cash arrived" guard is the account's cash covering the book's plus
  the amount: ANY surplus cash in the account satisfies it (an unrelated deposit, another dividend
  left unallocated), so a dividend that never arrives can be credited from it. The pre-trade cash
  gate still holds (the book never claims more than the account has).
- A threshold sleeve whose target holds a share worth more than 5% of the sleeve can trade inside
  its corridor through the idle-cash rule (mirror_core's docstring has the measured frequency).
- The 0.1% cash reserve is below IBKR's $0.005 a share for a name under about $5; the cheapest
  holdable names today are above $6.

OWNER QUESTIONS, still open (rollout notes, not built here)
- The account is believed to be a CASH account. The buys are marketable limits sized inside the
  sleeve's cash, so IBKR's credit check sees a known price (app/blend.py records market buys sized
  within a share of available cash coming back Inactive). Whether this account can fund a buy from
  SAME-MINUTE sale proceeds is not known: it is to be probed with the first live engine. If it
  cannot, the buys of a rotating sleeve are refused, the book records them as unfilled, and the
  sleeve trades again the next session.
- Reviewer B's M2: a threshold sleeve seeded from cash buys its target on its first session, while
  Composer's may be sitting inside its corridor on other holdings. Start such an engine on a session
  Composer's own symphony trades; nothing here aligns the two.

Nothing here trades for Composer, and nothing here reads Composer.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import mirror_core as mc
from .feeds import FeedDeadline, with_deadline
from .ib_adapter import round_limit_to_tick

logger = logging.getLogger(__name__)

SCHEMA = 2                     # the brain's payloads (contract_v2)
STATE_SCHEMA = 1               # this module's own state file
INTENTS_KIND = "composer-mirror-intents"
SESSION_KIND = "composer-mirror-session"
ET = ZoneInfo("America/New_York")

SESSION_TTL_S = 600.0          # the brain's clock is re-read this often
SESSION_FAIL_TTL_S = 20.0      # ... and this soon after a failed read
SESSION_DEADLINE_S = 6.0       # total deadline of one clock read
INTENTS_DEADLINE_S = 25.0      # total deadline of one intents read (the brain builds in ~6-10 s)
INTENTS_RETRY_S = 3.0
CLOCK_SKEW_S = 60.0            # the brain's clock and this one may differ by at most this (also the allowance on built_utc)
ORDER_POLL_S = 1.5
TICK_BUDGET_S = 150.0          # one tick never waits longer than this in total
PLAN_MIN_LEFT_S = 60.0         # no plan is started with less than this left before the cancel instant
PLACE_TRIES = 3
STUCK_FAST_S = 300.0           # an unresolved order is re-asked every 2 s for this long past the cancel instant
QUOTE_BUDGET_S = 45.0          # the venue cross-check of one plan never takes longer than this
QUOTE_PASSES = 3               # a rebuilt plan that adds symbols is cross-checked again at most this often
BUY_QUOTE_BUDGET_S = 20.0      # the quote re-read before the buys are sized never takes longer than this
TRUE_UP_EVERY_S = 600.0        # late commissions are asked for at most this often
COMMISSION_GIVE_UP_S = 3 * 86400.0
TERMS_TRIES = 3                # a fill whose price lookup RAISES is retried this often before the reference is used
CASH_TOL_USD = 1.0             # the book's cash may exceed the account's by at most this
CHECK_GAP_S = 30.0             # the post-session account check: two strikes this far apart halt
CHECK_STRIKES = 2
HISTORY_KEEP = 120
FLATTEN_OPEN_BUDGET_S = 1800.0 # a /kill flatten keeps selling what is still held for this much OPEN-session time
FLATTEN_GAPS_S = (5.0, 15.0, 60.0)   # ... a new round no sooner than this after the 1st, 2nd, 3rd was built,
FLATTEN_GAP_LATE_S = 300.0     # ... and this after every later one
FLATTEN_SEEN_CAP_S = 600.0     # two looks at a flatten further apart than this (or 2 x the loop cadence) count no open time
FLATTEN_WAIT_S = 5.0           # the loop cadence of a flatten while the session is open
PAPER_TICK_BUDGET_S = 20.0     # a PAPER tick never waits longer than this (it shares the loop with a live strategy)
PAPER_RETRY_S = 10.0           # ... and asks the brain again this often
PAPER_UNKNOWN_WAIT_S = 300.0   # session unknown: a paper book asks for the loop this often (UNKNOWN_WAIT_S from 15:30 ET)
RESOLVE_MAX_OFF_REF = 0.20     # an operator's resolve price further than this from the order's reference is refused
RESOLVE_MAX_COMM_USD = 5.0     # C-01: an operator's resolve commission above max(this, RESOLVE_MAX_COMM_FRAC x quantity
RESOLVE_MAX_COMM_FRAC = 0.01   # ... x price) is refused without "force": true
SEED_TOL_USD = 1.0             # D-05 / D-04: the capital caps are checked with this tolerance
LATCH_RETRY_S = 20.0           # a failed state save is retried this often
LATCH_ALERT_EVERY_S = 600.0    # ... and said again this often while it fails
UNKNOWN_WAIT_S = 60.0          # session unknown on a weekday 09:25-16:05 ET: ask for the loop this often
UNKNOWN_WAIT_LATE_S = 20.0     # ... and this often from 15:30 ET
UNKNOWN_ALERT_AFTER_S = 600.0
TRANSFER_TRIES = 3             # a transfer that moved less than asked is re-queued up to this many plans
DIVIDEND_ALERT_SESSIONS = 7    # a receivable unpaid this many sessions after its pay date is said once
QUOTE_SOURCES = ("live", "last", "bid", "ask")   # a venue quote from the previous close is no cross-check
LIMITS = {"cancel_before_close_s": (20.0, 120.0), "decide_offset_s": (0.0, 120.0), "quote_band": (0.001, 0.05)}
_UNKNOWN = object()
_WOKEN = object()


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
    decide_offset_s: float = 25.0          # act this long after the decision bar ends (FMP publishes it 10-25 s late)
    cancel_before_close_s: float = 60.0    # leftovers are cancelled this long before the close
    quote_band: float = 0.015              # live: venue quote vs the brain's price
    est_quote_band: float = 0.05           # ... when the brain's price is itself an estimate
    blend_enabled: bool = False            # live: no trading while the blend runs in the same account
    dividend_rule: str = "composer"        # "composer": credit only a sleeve that still holds the payer; "holder": always
    poll_s: float = 300.0                  # the service loop's ordinary cadence (bounds an off-hours flatten wait)
    max_book_usd: float = 0.0              # live: seeded + credited capital may not pass this without force (0: sum of capital)
    core: mc.Config = field(default_factory=mc.Config)


def clamp_config(cfg: MirrorConfig) -> list:
    """bring the three timing / band settings inside the range the book is built for; returns what it
    changed (a setting outside its range silently disables the book: A-19)"""
    changed = []
    for key, (lo, hi) in LIMITS.items():
        raw = _num(getattr(cfg, key))
        val = min(max(raw if raw is not None else lo, lo), hi)
        if raw is None or val != raw:
            changed.append(f"{key} {getattr(cfg, key)!r} -> {val:g} (allowed {lo:g}..{hi:g})")
            logger.warning("mirror[%s]: %s is %r, outside %g..%g: using %g", cfg.name, key, getattr(cfg, key), lo, hi, val)
        setattr(cfg, key, val)
    return changed


# ------------------------------------------------------------------ the brain's HTTP surface
def _reason(exc: Exception) -> str:
    if isinstance(exc, FeedDeadline):
        return "deadline"
    if isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol)):
        return "bad_url"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 503:                            # the brain says WHY it is not ready: carried, still transient
            try:
                body = exc.response.json()
                said = " — ".join(one_line(body[k], 160) for k in ("error", "detail") if isinstance(body, dict) and body.get(k))
            except Exception:  # noqa: BLE001
                said = ""
            return "http_503" + (f": {said}" if said else "")
        return "auth" if code in (401, 403) else f"http_{code}"
    if isinstance(exc, ValueError):
        return "decode"
    return "transport"


class HttpBrain:
    """GET /mirror/session and /mirror/intents with X-API-Token, each under a TOTAL deadline. One
    object is shared by the service's books. A PINNED payload is the decision as of its instant and
    never changes (the brain caches it by that instant), so the first complete one received for an
    instant is kept and the second book is given the SAME object, without a second request.
    Answers (payload | None, reason); the brain's 503 while the decision bar is not yet published
    is the reason "http_503", which the manager retries."""

    def __init__(self, url: str, token: str):
        self.base = (url or "").strip().rstrip("/")
        self.token = (token or "").strip()
        self._pinned: dict = {}                # {after: payload}: one decision instant at a time
        self._lock = threading.Lock()

    def secure(self) -> bool:
        """the token is sent only over https - or to this machine (localhost / 127.0.0.1)"""
        try:
            u = httpx.URL(self.base)
            return u.scheme == "https" or (u.scheme == "http" and u.host in ("localhost", "127.0.0.1"))
        except Exception:  # noqa: BLE001
            return False

    def _get(self, path: str, deadline: float, params: dict | None = None) -> tuple:
        if not self.base:
            return None, "no_url"
        if not self.secure():
            return None, "insecure_url"            # nothing is sent: the token never rides plain http
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
            hit = self._pinned.get(after)
        if hit is not None:
            return hit, "ok"
        payload, reason = self._get("/mirror/intents", INTENTS_DEADLINE_S, {"after": after})
        bar = payload.get("decision_bar") if payload is not None else None
        if payload is not None and payload.get("pinned") is True and payload.get("asof_utc") == after \
                and isinstance(bar, dict) and bar.get("complete") is True:
            with self._lock:
                if after not in self._pinned:
                    self._pinned = {after: payload}
                payload = self._pinned[after]
        return payload, reason


# ------------------------------------------------------------------ the manager
class MirrorManager:
    def __init__(self, cfg: MirrorConfig, brain=None, alert=None, clock=None, sleep=None, trading_day=None):
        self.cfg = cfg
        self._trading_day = trading_day        # date -> bool: the service's holiday calendar (None: weekdays)
        self._budget_s = TICK_BUDGET_S if cfg.live else PAPER_TICK_BUDGET_S
        self._retry_s = INTENTS_RETRY_S if cfg.live else PAPER_RETRY_S
        self.clamped = clamp_config(cfg)
        if cfg.dividend_rule not in mc.DIVIDEND_RULES:
            raise ValueError(f"MIRROR_DIVIDEND_RULE must be one of {mc.DIVIDEND_RULES}, not {cfg.dividend_rule!r}")
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
        self._why_day: str | None = None
        self._said: set = set()
        self._trued_at: datetime | None = None
        self._latched: dict | None = None      # a state save failed: {"since", "error", "said"}
        self._held: tuple | None = None        # (session, decide_utc, payload): today's validated intents
        self._unknown: dict | None = None      # {"day", "since"}: today's session is unknown
        self._prechecked: str | None = None
        self._seed_why: str | None = None
        self._deferred: list | None = None     # journal lines and alerts of a plan not yet on disk
        self._view: dict = {}
        self._halt: dict = {}
        self._dry = None
        self.state = self._fresh()
        self.book = mc.Book()
        self._load()
        if _num(self.state.get("funded_usd")) is None:
            # a state file written before D-04 carries no total: the seeds it records are what is known
            self.state["funded_usd"] = round(sum(_num((v or {}).get("amount")) or 0.0
                                                 for v in (self.state.get("seeded") or {}).values()
                                                 if isinstance(v, dict)), 2)
        if not cfg.live:
            from .ib_adapter import DryAdapter
            self._dry = DryAdapter()
            self._rebuild_paper()
        self._publish()

    # -------------------------------------------------------------- files
    def _fresh(self) -> dict:
        return {"schema": STATE_SCHEMA, "name": self.cfg.name, "live": self.cfg.live, "book": mc.Book().to_dict(),
                "seeded": {}, "frozen": [], "run": None, "last_run": None, "last_session": None, "history": [],
                "requests": [], "seen_requests": [], "flatten": None, "marks": {"prices": {}, "asof": None},
                "check": None, "commission_pending": [], "dividends": [], "div_seen": [], "splits_applied": [],
                "funded_usd": None, "seq": 0, "saved_utc": None}

    def _capital_usd(self) -> float:
        """MIRROR_CAPITAL_USD: the capital of every configured sleeve (the weights sum to 1)"""
        return sum(v for v in (_num(x) for x in (self.cfg.capital or {}).values()) if v is not None and v > 0)

    def _book_cap_usd(self) -> float:
        """D-04: the most capital (seeded + credited) a LIVE book takes without force: MIRROR_MAX_BOOK_USD,
        or MIRROR_CAPITAL_USD when that is 0 / unset"""
        cap = _num(self.cfg.max_book_usd)
        return cap if cap is not None and cap > 0 else self._capital_usd()

    def _seeded_usd(self) -> float:
        """what the sleeves the book holds now were seeded with"""
        seeded = self.state.get("seeded") or {}
        return sum(_num((seeded.get(n) or {}).get("amount")) or 0.0 for n in self.book.sleeves)

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
            if not isinstance(raw, dict) or raw.get("schema") != STATE_SCHEMA:
                raise ValueError(f"schema {raw.get('schema') if isinstance(raw, dict) else None!r} is not {STATE_SCHEMA}")
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

    def _save(self) -> bool:
        """Write the state. NEVER raises: a write that fails LATCHES the book (memory is now ahead of
        the disk; no run order is placed until a save succeeds) and answers False."""
        self.state["book"] = self.book.to_dict()
        self.state["seq"] = int(self.state.get("seq") or 0) + 1
        self.state["saved_utc"] = _iso(self.clock())
        try:
            atomic_write(self.cfg.state_path, self.state)
        except Exception as exc:  # noqa: BLE001
            self._latch(exc)
            self._publish()
            return False
        if self._latched:
            since = self._latched.get("since")
            self._latched = None
            self._say("warn", f"the state file is being written again (it could not be since {since}): the book "
                              f"carries on from what it holds in memory")
        self._publish()
        return True

    def _latch(self, exc: Exception) -> None:
        now = self.clock()
        if not self._latched:
            self._latched = {"since": _iso(now), "error": one_line(repr(exc), 200), "said": None}
        self._latched["error"] = one_line(repr(exc), 200)
        said = _parse(self._latched.get("said"))
        if said is None or (now - said).total_seconds() >= LATCH_ALERT_EVERY_S:
            self._latched["said"] = _iso(now)
            logger.error("mirror[%s] state save failed: %s", self.cfg.name, self._latched["error"])
            self._say("red", f"the state file CANNOT BE WRITTEN ({self._latched['error']}) since "
                             f"{self._latched['since']}. What the book did since then exists in memory only: NO order "
                             f"of a run is placed until a save succeeds (a /kill flatten still goes out). Free the "
                             f"disk; do not restart before /status shows save_latched false.")

    def _retry_save(self) -> None:
        if self._latched:
            self._save()

    def _journal(self, event: str, **kw) -> None:
        """the audit trail (append-only); the state file, not this, is what a restart reads"""
        if self._deferred is not None:             # a plan not yet on disk: written when it is
            self._deferred.append(("journal", event, kw))
            return
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

    def _rebuild_paper(self) -> None:
        """the private paper adapter holds exactly the book (after a boot, a dropped sleeve, a split, a
        repair). Reset in place: the tick in flight keeps the object it was given."""
        if self._dry is None:
            return
        self._dry.__init__()
        for sym, q in self.book.positions().items():
            self._dry.seed_position(sym, q)

    # -------------------------------------------------------------- alerts
    def _say(self, level: str, msg: str, key: str | None = None) -> None:
        """level: info | warn | red. key: said at most once per process for that key"""
        if self._deferred is not None:
            self._deferred.append(("say", level, msg, key))
            return
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

    def _loud(self) -> str:
        return "red" if self.cfg.live else "warn"

    def _set_why(self, why: str | None) -> None:
        self._why = why
        self._why_day = self.clock().astimezone(ET).date().isoformat()

    # -------------------------------------------------------------- halt / resume (any thread)
    def halt(self, reason: str, flatten: bool = False, by: str = "operator") -> dict:
        """Stop trading. flatten (live books only): also sell every share the book holds, on the loop
        thread, as soon as the session is open. Idempotent; a second call can add the flatten. A
        flatten that is not finished is CARRIED OVER whatever happened to the halt in between: a
        re-kill un-cancels the SAME flatten (never a second one over the same shares) and a plain halt
        keeps the cancelled record, so the loop still settles the orders it has at the venue.
        Answers the halt record plus "persisted": False when it binds this process only (the halt
        file could not be written: a restart would forget it)."""
        with self.halt_lock:
            h = dict(self._halt or {})
            now = _iso(self.clock())
            unfinished = bool(h.get("flatten") and not h.get("flatten_done"))
            if not h.get("halted"):
                new = {"halted": True, "reason": one_line(reason, 300), "ts": now, "by": by}
                if unfinished:
                    for k in ("flatten", "flatten_done", "flatten_cancelled", "flatten_ts", "flatten_id"):
                        if k in h:
                            new[k] = h[k]
                h = new
            if flatten and self.cfg.live:
                if unfinished:
                    h["flatten_cancelled"] = False
                else:
                    h.pop("account_flat", None)    # the last flatten's account reading is not this one's
                    h.update(flatten=True, flatten_done=False, flatten_cancelled=False, flatten_ts=now,
                             flatten_id=self.clock().strftime("%Y%m%dT%H%M%S"))
            ok = self._write_halt(h)
            return dict(h, persisted=ok)

    def resume(self) -> dict:
        """Clear the halt. A flatten not yet finished is cancelled: no new flatten order is sent, and
        the ones already at the venue are settled before the book trades again. Answers which halt it
        lifted ("lifted": {"reason", "by", "ts"} or None) and "persisted"."""
        with self.halt_lock:
            h = dict(self._halt or {})
            was = bool(h.get("halted"))
            lifted = {k: h.get(k) for k in ("reason", "by", "ts")} if was else None
            h["halted"] = False
            h["resumed_ts"] = _iso(self.clock())
            if h.get("flatten") and not h.get("flatten_done"):
                h["flatten_cancelled"] = True
            ok = self._write_halt(h)
            return {"was_halted": was, "lifted": lifted, **h, "persisted": ok}

    def _write_halt(self, h: dict) -> bool:
        self._halt = h
        try:
            atomic_write(self._halt_path(), h)
            return True
        except Exception as exc:  # noqa: BLE001  the in-memory halt still binds this process
            logger.error("mirror[%s] halt file write failed: %s", self.cfg.name, exc)
            return False

    def halt_state(self) -> dict:
        with self.halt_lock:
            return dict(self._halt or {})

    def _halted(self) -> bool:
        return bool(self.halt_state().get("halted"))

    @staticmethod
    def _woken(wake) -> bool:
        return wake is not None and wake.is_set()

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

    def request_credit(self, sleeve: str, amount, note: str = "", force: bool = False) -> dict:
        """queue a cash adjustment of one sleeve (cash the account received for it: +; a fee: -).
        Applied before the next plan, debits first; a live book takes a credit only from cash the
        account holds beyond the book. (Dividends the brain lists are booked by the book itself.)"""
        amt = _num(amount)
        if amt is None or amt == 0:
            raise ValueError("a credit needs a non-zero amount")
        if sleeve not in self.cfg.engines:
            raise ValueError(f"{sleeve!r} is not a sleeve of the {self.cfg.name} book")
        # force: a DEBIT that would take the sleeve's cash below zero is refused without it (a slipped decimal
        # would otherwise put the sleeve 'in debt' and the next session would sell it out to repair that)
        return self._request({"kind": "credit", "sleeve": sleeve, "amount": amt, "note": one_line(note, 200),
                              "force": force is True})

    def request_resolve(self, order_id: str, filled, price=None, commission=0.0, note: str = "",
                        force: bool = False) -> dict:
        """queue the operator's statement of what an UNRESOLVED order did: `filled` shares at `price`
        (commission optional). The loop thread takes it only for an order of the open run or flatten
        that is flagged unresolved, asks the venue once more first (an order still working is
        refused; one the venue now answers for is booked at the VENUE's answer) and refuses a price
        that cannot be true (_resolve). The repair for an order the venue can no longer answer for
        (an overnight outage, an unreadable execution)."""
        qty = _num(filled)
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("a resolve needs the order id")
        if qty is None or qty < 0 or qty != int(qty):
            raise ValueError("filled must be a whole number of shares, 0 or more")
        px = _num(price) if price is not None else None
        if qty > 0 and (px is None or px <= 0):
            raise ValueError("a filled quantity needs the price it filled at")
        comm = _num(commission if commission is not None else 0.0)
        if comm is None or comm < 0:
            raise ValueError("commission must be 0 or more")
        # force: a commission above max($5, 1% of quantity x price) is refused without it (C-01; _resolve)
        return self._request({"kind": "resolve", "order": order_id.strip(), "filled": int(qty), "price": px,
                              "commission": comm, "note": one_line(note, 200), "force": force is True})

    def request_adjust(self, sleeve: str, symbol, shares_delta, cash_delta, note: str = "", force: bool = False) -> dict:
        """queue a signed correction of ONE sleeve: shares of one symbol (shares_delta) and / or its
        cash (cash_delta). Applied by the loop thread, only while no run is open and no flatten order
        is in flight; a sleeve's shares can never go negative. The repair for any share-count
        divergence (a manual trade, a split the brain listed late, an order resolved wrongly)."""
        shares = _num(shares_delta if shares_delta is not None else 0)
        cash = _num(cash_delta if cash_delta is not None else 0.0)
        if shares is None or shares != int(shares) or cash is None:
            raise ValueError("shares must be a whole number and cash a finite amount")
        if not shares and not cash:
            raise ValueError("an adjustment needs a non-zero shares or cash delta")
        if shares and (not isinstance(symbol, str) or not symbol.strip()):
            raise ValueError("a share adjustment needs the symbol")
        if not isinstance(sleeve, str) or (sleeve not in self.cfg.engines and sleeve not in self.book.sleeves):
            raise ValueError(f"{sleeve!r} is not a sleeve of the {self.cfg.name} book")
        if not one_line(note):
            raise ValueError("an adjustment needs a note saying why (it is the audit trail)")
        return self._request({"kind": "adjust", "sleeve": sleeve, "symbol": symbol.strip() if isinstance(symbol, str) else None,
                              "shares": int(shares), "cash": cash, "note": one_line(note, 200), "force": force is True})

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
        if self._latched:
            return                                 # the disk does not hold them yet: the inbox keeps them
        ids = {r.get("id") for r in box if isinstance(r, dict)}
        with self.inbox_lock:
            left = [r for r in self._read_inbox() if not (isinstance(r, dict) and r.get("id") in ids)]
            atomic_write(self._inbox_path(), left)

    # -------------------------------------------------------------- operator repairs (loop thread)
    def _apply_repairs(self, ad) -> None:
        keep, changed = [], False
        for r in list(self.state.get("requests") or []):
            kind = r.get("kind")
            if kind not in ("resolve", "adjust"):
                keep.append(r)
                continue
            try:
                done = self._resolve(ad, r) if kind == "resolve" else self._adjust(r)
            except mc.MirrorError as exc:
                done = True
                self._refuse(r, f"the book refused it: {one_line(exc, 200)}")
            if done:
                changed = True
            else:
                keep.append(r)
        if changed:
            self.state["requests"] = keep
            self._save()

    def _refuse(self, r: dict, why: str) -> None:
        self._journal("request_refused", why=why, **r)
        self._say("red", f"{r.get('kind')} request {r.get('id')} REFUSED: {why}")

    def _open_orders(self) -> list:
        """[(order, recs dict, where)] of every order of the open run or flatten not yet booked"""
        out = []
        run = self.state.get("run")
        if run:
            for o in run["plan"]["sells"] + (run["plan"].get("buys") or []):
                if not o.get("applied"):
                    out.append((o, run["orders"], "run"))
        fl = self.state.get("flatten") or {}
        for o in fl.get("orders") or []:
            if not o.get("applied"):
                out.append((o, fl.setdefault("recs", {}), "flatten"))
        return out

    def _resolve(self, ad, r: dict) -> bool:
        """True: the request is consumed (applied or refused); False: it stays queued. N-01: an
        operator's statement is taken only where the book has no better source - the order must be
        flagged UNRESOLVED, the venue is asked once more and its own terminal answer wins, and a price
        that cannot be true (a buy above its limit, anything more than 20% from the reference) is
        refused. Every refusal is journaled and alerted."""
        oid = r.get("order")
        hit = next(((o, recs, where) for o, recs, where in self._open_orders() if o["id"] == oid), None)
        if hit is None:
            self._refuse(r, f"no unbooked order {oid!r} in the open run or flatten")
            return True
        o, recs, where = hit
        rec = recs.setdefault(oid, {"state": "new", "tries": 0})
        qty, px, comm = int(r.get("filled") or 0), _num(r.get("price")), _num(r.get("commission")) or 0.0
        if not rec.get("stuck"):
            self._refuse(r, f"order {oid} is not UNRESOLVED (state {rec.get('state')!r}): the book follows the venue "
                            f"for it; only an order the venue cannot answer for is resolved by hand")
            return True
        if qty > int(o["qty"]):
            self._refuse(r, f"order {oid} asked for {o['qty']} shares, not {qty}")
            return True
        if qty and (px is None or px <= 0):
            self._refuse(r, f"{qty} shares need the price they filled at")
            return True
        limit, ref = _num(o.get("limit")), _num(o.get("ref"))
        if qty and o["side"] == mc.BUY and limit is not None and px > limit + 1e-9:
            self._refuse(r, f"a BUY cannot have filled at {px:g}: order {oid} is a limit order at {limit:g}")
            return True
        if qty and ref is not None and ref > 0 and abs(px / ref - 1.0) > RESOLVE_MAX_OFF_REF:
            self._refuse(r, f"{px:g} is more than {RESOLVE_MAX_OFF_REF:.0%} from order {oid}'s reference {ref:g}: "
                            f"check the price (a slipped decimal?)")
            return True
        if qty and r.get("force") is not True:
            most = max(RESOLVE_MAX_COMM_USD, RESOLVE_MAX_COMM_FRAC * qty * px)
            if comm > most + 1e-9:                 # C-01: a slipped decimal here debits the sleeves like a price would
                self._refuse(r, f"a commission of ${comm:,.2f} on {qty} {o['symbol']} @{px:g} is more than "
                                f"${most:,.2f} (the larger of ${RESOLVE_MAX_COMM_USD:g} and "
                                f"{RESOLVE_MAX_COMM_FRAC:.0%} of the trade): check the amount (a slipped decimal?); "
                                f"send it with \"force\": true if it is meant")
                return True
        if self._dry is None:
            if ad is None:
                return False                       # the venue cannot be asked now: it stays queued
            res = self._find(ad, oid, rec)         # ... asked ONCE MORE: its own answer wins
            if res is _UNKNOWN:
                # C-02: a lookup that RAISED is not an answer: nothing is booked on the operator's word
                # while the venue may still hold the order. The request stays queued and is asked again.
                self._say("red", f"resolve request {r.get('id')} of order {oid} is NOT booked: the venue could not "
                                 f"be asked about it ({rec.get('find_error') or 'the lookup failed'}). It stays "
                                 f"queued and is applied (or refused) as soon as the venue answers.",
                          key=f"resolve-noask:{r.get('id')}")
                return False
            if res is not None:
                if res.get("status") == "working":
                    self._refuse(r, f"the venue still holds order {oid} as WORKING: cancel it at the venue first")
                    return True
                if res.get("status") in ("filled", "cancelled") and self._settle(ad, o, rec, res, past=True):
                    self._journal("resolve_from_venue", where=where, venue=res.get("status"), **r)
                    self._say("warn", f"resolve of order {oid}: the VENUE answers for it now ({res.get('status')}): "
                                      f"booked {o.get('filled', 0)} of {o['qty']} {o['symbol']} from the venue's own "
                                      f"record, NOT the {qty} stated in the request")
                    return True
                if res.get("status") == "filled":
                    # the venue says FILLED and only its terms cannot be read on this pass: its quantity
                    # still wins. A statement of the SAME quantity supplies the price; any other is refused
                    got = int(o["qty"]) if res.get("filled_qty") is None else max(0, min(int(o["qty"]), int(res["filled_qty"])))
                    if qty != got:
                        self._refuse(r, f"the venue answers that order {oid} FILLED {got} of {o['qty']} (only its price "
                                        f"cannot be read yet); the request states {qty}. State the venue's quantity "
                                        f"with the price from the statement, or wait: the book keeps asking")
                        return True
        snap = self.book.to_dict()
        try:
            self._book(o, rec, qty, px if qty else None, comm if qty else 0.0,
                       "resolved by the operator" + (f" ({r['note']})" if r.get("note") else ""))
        except mc.MirrorError:
            self.book = mc.Book.from_dict(snap)
            raise
        self._journal("resolve", where=where, **r)
        self._say("warn", f"order {oid} RESOLVED by the operator: {qty} of {o['qty']} {o['symbol']}"
                          + (f" @{px:.4f}" if qty else "") + (f" — {r['note']}" if r.get("note") else ""))
        return True

    def _adjust(self, r: dict) -> bool:
        if self.state.get("run") or any(where == "flatten" for _, _, where in self._open_orders()):
            self._say("info", f"adjustment {r.get('id')} waits: it is applied when no run is open and no flatten "
                              f"order is in flight", key=f"adjust-wait:{r.get('id')}")
            return False
        name, sym = r.get("sleeve"), r.get("symbol")
        shares, cash = int(r.get("shares") or 0), _num(r.get("cash")) or 0.0
        s = self.book.sleeves.get(name)
        if s is None:
            self._refuse(r, f"the book has no sleeve {name!r}")
            return True
        have = s.shares.get(sym, 0) if sym else 0
        if shares and have + shares < 0:
            self._refuse(r, f"{name} holds {have} {sym}: it cannot be adjusted by {shares:+d}")
            return True
        if cash < 0 and s.cash + cash < -mc.DEBT_TOL_USD and r.get("force") is not True:
            self._refuse(r, f"{name} has ${s.cash:,.2f} in cash: an adjustment of {cash:+,.2f} would put it IN DEBT "
                            f"(the next session would sell holdings to repair it). Check the amount; send it with "
                            f"\"force\": true if it is meant")
            return True
        if shares:
            if have + shares:
                s.shares[sym] = have + shares
            else:
                s.shares.pop(sym, None)
        s.cash += cash
        self.state["check"] = None                 # the account is compared with the book again
        if shares:
            self._holdings_row(self.clock().astimezone(ET).date().isoformat(), "adjust")
        self._rebuild_paper()
        self._journal("adjust", **r)
        self._say("warn", f"sleeve {name} ADJUSTED by the operator: "
                          + (f"{shares:+d} {sym} (now {s.shares.get(sym, 0)}) " if shares else "")
                          + (f"cash {cash:+,.2f} (now ${s.cash:,.2f}) " if cash else "") + f"— {r.get('note')}")
        return True

    def _holdings_row(self, day: str, why: str, from_open: bool = False) -> None:
        """V2-B2: shares changed OUTSIDE a run (a flatten, a split, an adjustment). The history gets a
        row of what every sleeve holds from `day` on, so a later dividend reads its entitlement from
        the shares really held at the close before its ex-date, not from the last PLANNED session.
        from_open: the change took effect at the OPEN of `day` (a split): the row also answers for a
        dividend whose ex-date IS that day, as the plan of that day itself would (it sees the sleeves
        after the split). A flatten or an adjustment happened DURING its day: only later ex-dates."""
        row = {"session": day, "outcome": "holdings", "reason": why, "utc": _iso(self.clock()),
               "from_open": bool(from_open),
               "sleeves": {n: {"shares": dict(sorted(x.shares.items())), "cash": round(x.cash, 4)}
                           for n, x in self.book.sleeves.items()}}
        self.state["history"] = (list(self.state.get("history") or []) + [row])[-HISTORY_KEEP:]

    # -------------------------------------------------------------- the tick (loop thread only)
    def tick(self, adapter=None, wake=None, stop=None) -> None:
        """One pass. adapter: the service's venue adapter (ignored by a DRY book). wake: the loop's
        wake event. Nothing in here holds the loop thread behind a set `wake` except a venue call
        already in flight: a brain read runs on a worker while this thread waits on `wake`; the wake
        is looked at between quotes and between orders; a decision not yet on disk is dropped (and
        retried by the next tick), a run on disk is left for the next tick. The /kill flatten itself
        is not interrupted. stop: () -> True when this loop has been superseded. Never raises."""
        ad = self._dry if self._dry is not None else adapter
        with self.tick_lock:
            try:
                self._tick(ad, wake, stop)
                self.last_error = None
            except mc.MirrorError as exc:          # the book refused a booking: the book and the venue disagree
                self._deferred = None
                self.last_error = one_line(exc, 300)
                logger.exception("mirror[%s] book error", self.cfg.name)
                self.halt(f"book error: {self.last_error}", by="mirror")
                self._say("red", f"HALTED — the book refused a booking ({self.last_error}). Nothing more is "
                                 f"traded until /resume; compare the account with /status first.",
                          key=f"bookerr:{self.last_error}")
            except Exception as exc:  # noqa: BLE001
                self._deferred = None
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
        if self.clock() + timedelta(seconds=seconds) >= until:
            return True
        if self._sleep is not None:
            return bool(self._sleep(seconds))
        if wake is not None:
            return bool(wake.wait(seconds))
        time.sleep(seconds)
        return False

    def _brain_call(self, fn, wake, deadline_s: float):
        """One brain read. With a wake event it runs on a worker and THIS thread waits on the wake
        (A-23: /kill is never queued behind a 25 s read); _WOKEN when the wake won. Without one (the
        test seam) it runs inline."""
        if wake is None:
            return fn()
        box: dict = {}
        done = threading.Event()

        def run() -> None:
            try:
                box["v"] = fn()
            except BaseException as exc:  # noqa: BLE001
                box["v"] = (None, _reason(exc) if isinstance(exc, Exception) else "transport")
            finally:
                done.set()
        threading.Thread(target=run, daemon=True, name="mirror-brain").start()
        end = time.monotonic() + deadline_s + 5.0
        while not done.wait(0.05):
            if wake.is_set():
                return _WOKEN
            if time.monotonic() > end:
                return None, "deadline"
        return box["v"]

    def _tick(self, ad, wake, stop) -> None:
        self._deferred = None
        today = self.clock().astimezone(ET).date().isoformat()
        if self._why_day != today:
            self._why, self._why_day = None, today
        self._retry_save()                         # D4: memory may be ahead of the disk
        for step in (self._drain_inbox, lambda: self._apply_repairs(ad)):
            try:                                   # neither may ever stand between a /kill and its flatten
                step()
            except Exception as exc:  # noqa: BLE001
                logger.exception("mirror[%s] request handling failed", self.cfg.name)
                self._say("red", f"the request inbox could not be processed ({one_line(repr(exc), 160)}); queued "
                                 f"transfers, credits and repairs wait. The halt and flatten path carries on.",
                          key=f"inbox:{one_line(repr(exc), 80)}")
        if not self._flatten_tick(ad):
            return
        if self._halted():
            self._abort_run(ad, "halted")
            return
        if ad is None:
            return
        if not self.state.get("run"):
            self._reconcile_sleeves(ad)
        until = self.clock() + timedelta(seconds=self._budget_s)
        if self.state.get("run"):
            self._drive(ad, wake, stop, until)
            self._lost_behind_run(wake)
            return
        if self._latched:
            self._set_why(f"the state file cannot be written ({self._latched.get('error')})")
            return
        info = self._session(wake)
        now = self.clock()
        if info is None:
            self._unknown_session(now)
            return
        self._unknown = None
        if not info.get("session"):
            if info.get("reason"):
                self._say("red", f"the brain's clock says there is NO session today and gives a reason: "
                                 f"{one_line(info['reason'], 200)}. If today is a session, nothing will be traded.",
                          key=f"nosession:{today}")
            return
        session = info["session"]
        if self.state.get("last_session") == session:
            self._post_check(ad, session, wake)
            return
        if now < info["decide_at"]:
            self._morning_check(ad, info, now)
            return
        if now >= info["plan_by"]:
            self._skip(session, "missed the decision window: " + (self._why or "the executor was not ready in time"))
            return
        self._decide(ad, info, wake, stop, until)

    def next_wait(self) -> float | None:
        """seconds until this book next needs the loop, or None when the ordinary cadence will do
        (loop thread; reads only what the last tick left)"""
        try:
            now = self.clock()
            h = self._halt or {}
            fl = self.state.get("flatten") or {}
            in_flight = any(not o.get("applied") for o in fl.get("orders") or [])
            pending = bool(h.get("flatten") and not h.get("flatten_done"))
            if in_flight or pending:
                if not (pending and not h.get("flatten_cancelled")):
                    return FLATTEN_WAIT_S          # being cancelled and settled: no session is needed for that
                if self._rth(now):
                    nxt = _parse(fl.get("next_round_utc")) if not in_flight else None
                    if nxt is None or nxt <= now:
                        return FLATTEN_WAIT_S
                    return min(max((nxt - now).total_seconds(), FLATTEN_WAIT_S), max(float(self.cfg.poll_s), FLATTEN_WAIT_S))
                # the session is shut: nothing can be sold before the next open (A-20: never spin the
                # whole service loop every 5 s through a night or a weekend)
                return min(max(self._to_next_open(now), FLATTEN_WAIT_S), max(float(self.cfg.poll_s), FLATTEN_WAIT_S))
            if self._latched:
                return LATCH_RETRY_S
            run = self.state.get("run")
            if run:
                over = _parse(run.get("cancel_utc"))
                # fast until the session has closed and its DAY orders have had time to die; an order still
                # unresolved after that waits for the operator: the ordinary cadence will do (A-20)
                return 2.0 if not over or (now - over).total_seconds() < STUCK_FAST_S else None
            if h.get("halted"):
                return None
            e = now.astimezone(ET)
            s = self._sess
            known = s is not None and s["day"] == e.date().isoformat() and (s["info"] if s.get("ok") else s.get("kept")) is not None
            if not known:
                # D6: an unreadable clock must not park the loop for 300 s against a 3-minute window
                if e.weekday() < 5 and (9, 25) <= (e.hour, e.minute) < (16, 5):
                    late = (e.hour, e.minute) >= (15, 30)
                    if not self.cfg.live:          # a paper book shares the loop with a live strategy (N-09)
                        return UNKNOWN_WAIT_S if late else PAPER_UNKNOWN_WAIT_S
                    return UNKNOWN_WAIT_LATE_S if late else UNKNOWN_WAIT_S
                return None
            info = s["info"] if s.get("ok") else s.get("kept")
            if not info.get("session") or self.state.get("last_session") == info["session"]:
                return None
            left = (info["decide_at"] - now).total_seconds()
            return max(left, 0.0) + 0.2 if left > 0 else 2.0
        except Exception:  # noqa: BLE001
            return None

    # -------------------------------------------------------------- the brain's clock
    def _session(self, wake=None) -> dict | None:
        """today's session from the brain's clock, parsed and cached: {"session", "decide_at",
        "cancel_at", "plan_by", "close_at", "open_at"} or {"session": None, "reason"}; None when unknown"""
        now = self.clock()
        day = now.astimezone(ET).date().isoformat()
        c = self._sess
        if c and c["day"] == day and (now - c["at"]).total_seconds() < (SESSION_TTL_S if c["ok"] else SESSION_FAIL_TTL_S):
            return c["info"] if c["ok"] else c.get("kept")
        got = self._brain_call(self.brain.session, wake, SESSION_DEADLINE_S) if self.brain is not None else (None, "no_brain")
        if got is _WOKEN:                          # no answer is not a failed read: what is known stands
            return (c["info"] if c["ok"] else c.get("kept")) if c and c["day"] == day else None
        raw, reason = got
        info, why = self._read_session(raw, day, now) if raw is not None else (None, reason)
        self.brain_status["session"] = {"ok": info is not None, "reason": why, "utc": _iso(now)}
        if info is None:
            kept = None                            # today's last good read survives a failed one
            if c and c["day"] == day:
                kept = c["info"] if c["ok"] else c.get("kept")
            self._sess = {"day": day, "info": None, "kept": kept, "at": now, "ok": False}
            self._set_why(f"the brain's clock is unreadable ({why})")
            if why == "insecure_url":
                self._say("red", "MIRROR_BRAIN_URL is not https (and not localhost): the brain is NOT asked, because "
                                 "the API token would travel in the clear. Nothing is traded until the URL is https.",
                          key="insecure-url")
            return kept
        self._sess = {"day": day, "info": info, "at": now, "ok": True}
        return info

    def _read_session(self, raw: dict, day: str, now: datetime) -> tuple:
        if raw.get("kind") != SESSION_KIND or raw.get("schema") != SCHEMA:
            return None, f"not a mirror session payload (schema {SCHEMA})"
        theirs = _parse(raw.get("now_utc"))
        if theirs is None or abs((theirs - now).total_seconds()) > CLOCK_SKEW_S:
            return None, f"the brain's clock reads {raw.get('now_utc')!r}, this one {_iso(now)}"
        if raw.get("session") is None:
            why = raw.get("reason")
            return {"session": None, "reason": one_line(why, 300) if why else None}, "ok" if not why else f"no session: {one_line(why, 120)}"
        if raw.get("session") != day:
            return None, f"the brain's session {raw.get('session')!r} is not today's {day}"
        decide, close, opn = _parse(raw.get("decide_utc")), _parse(raw.get("close_utc")), _parse(raw.get("open_utc"))
        if not (decide and close and opn) or not (opn < decide < close):
            return None, "the session times do not parse"
        cancel = close - timedelta(seconds=self.cfg.cancel_before_close_s)
        # decide_utc is the END of the decision bar, exactly as the brain gives it (contract v2: no "+ 1 minute")
        return {"session": day, "decide_utc": _iso(decide), "open_at": opn, "close_at": close,
                "decide_at": decide + timedelta(seconds=self.cfg.decide_offset_s), "cancel_at": cancel,
                "plan_by": cancel - timedelta(seconds=PLAN_MIN_LEFT_S)}, "ok"

    def _today_info(self, now: datetime) -> dict | None:
        s = self._sess
        if not s or s["day"] != now.astimezone(ET).date().isoformat():
            return None
        return s.get("info") or s.get("kept")

    def _rth(self, now: datetime) -> bool:
        """is the regular session open now: the brain's clock when it KNOWS today, else the plain
        weekday 09:30-16:00 ET (the kill path must not depend on the brain; a "no session" that
        comes with a reason is the brain not knowing)"""
        info = self._today_info(now)
        if info and info.get("session"):
            return info["open_at"] <= now < info["close_at"]
        if info is not None and not info.get("reason"):
            return False
        e = now.astimezone(ET)
        return self._is_day(e.date()) and (9, 30) <= (e.hour, e.minute) < (16, 0)

    def _is_day(self, d) -> bool:
        """a trading day by the service's own calendar when it was given one (a weekday holiday is not
        a session: no flatten order is sent into it), else any weekday"""
        if d.weekday() >= 5:
            return False
        if self._trading_day is None:
            return True
        try:
            return bool(self._trading_day(d))
        except Exception:  # noqa: BLE001
            return True

    def _to_next_open(self, now: datetime) -> float:
        info = self._today_info(now)
        if info and info.get("session") and info["open_at"] > now:
            return (info["open_at"] - now).total_seconds()
        e = now.astimezone(ET)
        for k in range(0, 8):
            cand = datetime.combine(e.date() + timedelta(days=k), dtime(9, 30), tzinfo=ET)
            if self._is_day(cand.date()) and cand > e:
                return (cand - e).total_seconds()
        return 3600.0

    def _unknown_session(self, now: datetime) -> None:
        """D6: today's session cannot be read. Never a silent day."""
        e = now.astimezone(ET)
        day, hm = e.date().isoformat(), (e.hour, e.minute)
        if e.weekday() >= 5 or hm < (9, 25):
            return
        u = self._unknown
        if not u or u["day"] != day:
            u = self._unknown = {"day": day, "since": now}
        why = (self.brain_status.get("session") or {}).get("reason") or "no answer"
        if hm < (16, 5) and (now - u["since"]).total_seconds() >= UNKNOWN_ALERT_AFTER_S:
            self._say("red", f"the brain's clock has been unreadable since {u['since'].astimezone(ET).strftime('%H:%M')} ET "
                             f"({why}): the book does not know whether today is a session or when to decide. "
                             f"Nothing is traded until it answers; it keeps being asked.", key=f"clock:{day}")
        if hm >= (16, 0) and (self.state.get("last_session") or "") < day:
            self._skip(day, f"the brain's clock was unreadable all session (since "
                            f"{u['since'].astimezone(ET).strftime('%H:%M')} ET: {why}); if today was a session, no "
                            f"trade was made")

    # -------------------------------------------------------------- sleeves
    def _reconcile_sleeves(self, ad) -> None:
        """seed the sleeves the config names and the book lacks; freeze (live) or drop (dry) the ones
        the book has and the config no longer names"""
        changed = dropped = False
        for name in [n for n in self.book.sleeves if n not in self.cfg.engines]:
            s = self.book.sleeves[name]
            if not self.cfg.live or not s.shares:
                del self.book.sleeves[name]
                self.state["frozen"] = [x for x in self.state.get("frozen") or [] if x != name]
                self._journal("sleeve_dropped", sleeve=name, cash=s.cash, shares=dict(s.shares))
                self._say("warn", f"sleeve {name} is no longer configured for this book: dropped "
                                  f"(cash ${s.cash:,.2f} leaves the book)")
                changed = dropped = True
            elif name not in (self.state.get("frozen") or []):
                self.state["frozen"] = list(self.state.get("frozen") or []) + [name]
                self._say("red", f"sleeve {name} holds {dict(s.shares)} but is no longer in MIRROR_LIVE_ENGINES: "
                                 f"FROZEN (kept, never traded). Re-add it, or /kill to sell the book.")
                changed = True
        if dropped:
            self._rebuild_paper()                  # A-08: the paper account holds the book, not the sleeve that left
        want = [e for e in self.cfg.engines if e not in self.book.sleeves]
        self._seed_why = None
        if want:
            avail = None
            if self.cfg.live:
                cash = ad.account_cash()
                if not cash or _num(cash.get("total_cash")) is None:
                    self._say("warn", f"cannot seed {', '.join(want)}: the account reports no cash claim",
                              key=f"seed-noclaim:{','.join(want)}")
                    self._seed_why = "the account reports no cash claim to seed from"
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
                    self._seed_why = "no capital configured (MIRROR_CAPITAL_USD)"
                    continue
                if avail is not None and self.book.cash() + amt > avail + CASH_TOL_USD:
                    self._say("red", f"cannot seed {name} with ${amt:,.2f}: the account has ${avail:,.2f} in cash "
                                     f"and the book already claims ${self.book.cash():,.2f}", key=f"seed-short:{name}")
                    self._seed_why = "the account's cash does not cover the sleeves' capital"
                    continue
                if self.cfg.live and self._seeded_usd() + amt > self._capital_usd() + SEED_TOL_USD:
                    # D-05: each seed is capital x the weight OF THAT DAY; a staged rollout with the weights
                    # edited in between must still never seed more than the capital in total
                    self._say("red", f"cannot seed {name} with ${amt:,.2f}: the sleeves this book holds were seeded "
                                     f"with ${self._seeded_usd():,.2f} and MIRROR_CAPITAL_USD is "
                                     f"${self._capital_usd():,.2f} (were MIRROR_WEIGHTS changed after a sleeve was "
                                     f"funded?). Nothing is seeded beyond the capital.", key=f"seed-cap:{name}:{amt:.2f}")
                    self._seed_why = "seeding the remaining sleeves would exceed MIRROR_CAPITAL_USD"
                    continue
                self.book.sleeves[name] = mc.Sleeve(name=name, cash=amt)
                self.state.setdefault("seeded", {})[name] = {"amount": amt, "utc": _iso(self.clock())}
                self.state["funded_usd"] = round((_num(self.state.get("funded_usd")) or 0.0) + amt, 2)
                self._journal("sleeve_seeded", sleeve=name, amount=amt)
                # a LIVE sleeve claiming real cash is a warning, never a line that scrolls by
                self._say("warn" if self.cfg.live else "info", f"sleeve {name} seeded with ${amt:,.2f} in cash"
                          + (f" of the ACCOUNT's (the live book has now taken ${self.state['funded_usd']:,.2f} in "
                             f"seeds and credits)" if self.cfg.live else ""))
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

    def _pretrade_static(self) -> str | None:
        """a reason this book cannot trade that nothing inside the decision window can change (A-12)"""
        if not self._active():
            return "the book has no sleeve to trade" + (f" ({self._seed_why})" if self._seed_why else "")
        if self.cfg.live and self.cfg.blend_enabled:
            return "the blend strategy is still enabled in this account (the mirror observes only)"
        return None

    def _pretrade_account(self, ad) -> str | None:
        """why the ACCOUNT stops this book now, or None (it can clear: retried inside the window)"""
        probs = self._venue_problems(ad)
        if probs:
            return ("the account does not hold exactly the mirror book: " + "; ".join(probs[:5])
                    + " (repair a real divergence with POST /mirror/adjust)")
        if self.cfg.live:
            cash = ad.account_cash()
            have = _num((cash or {}).get("total_cash"))
            if have is None:
                return "the account reports no cash claim"
            # the book as the plan will see it: a queued DEBIT (a fee the account already paid) is applied
            # before anything is planned, so it must be able to clear this gate - not be locked out by it
            mine = self.book.cash() + sum(amt for _, amt in self._debits_that_apply())
            if mine > have + CASH_TOL_USD:
                return (f"the book's cash ${mine:,.2f} exceeds the account's ${have:,.2f} (a fee the account paid is "
                        f"debited with POST /mirror/credit, a negative amount)")
        return None

    def _pretrade(self, ad) -> str | None:
        return self._pretrade_static() or self._pretrade_account(ad)

    def _debits_that_apply(self) -> list:
        """[(request, amount)] of the queued DEBITS the next plan will apply, in the order it applies
        them (ascending): one that would take its sleeve's cash below zero is refused unless forced"""
        cash = {n: x.cash for n, x in self.book.sleeves.items()}
        out = []
        rows = [r for r in self.state.get("requests") or [] if r.get("kind") == "credit" and r.get("sleeve") in cash]
        for r in sorted(rows, key=lambda r: _num(r.get("amount")) if _num(r.get("amount")) is not None else 0.0):
            amt = _num(r.get("amount"))
            if amt is None or amt >= 0:
                continue
            if cash[r["sleeve"]] + amt < -mc.DEBT_TOL_USD and r.get("force") is not True:
                continue
            cash[r["sleeve"]] += amt
            out.append((r, amt))
        return out

    def _morning_check(self, ad, info: dict, now: datetime) -> None:
        """once per session, on the first tick of the open session before the decision: the pre-trade
        gates, read-only, so a refusal is learnt in the morning and not at 15:58"""
        session = info["session"]
        if self._prechecked == session or now < info["open_at"]:
            return
        self._prechecked = session
        try:
            why = self._pretrade(ad)
        except Exception as exc:  # noqa: BLE001
            why = f"the pre-trade gates could not be read ({one_line(exc, 160)})"
        if why:
            self._say(self._loud(), f"{session}: today's decision will be refused unless fixed: {why}",
                      key=f"precheck:{session}")

    # -------------------------------------------------------------- the decision
    def _validate(self, p, info: dict, now: datetime) -> str | None:
        """contract_v2 'Executor checks' (as clarified once the brain side was finished): schema, kind,
        pinned, not a replay, today's session, asof_utc == decide_utc exactly, the decision bar
        complete, built_utc not in the future and not before the instant it decides (each within the
        clock-skew allowance), engines and prices present. NOT the payload's age: a pinned payload
        is immutable, and a restart late in the window must be able to trade the one built at 15:54."""
        if not isinstance(p, dict) or p.get("kind") != INTENTS_KIND or p.get("schema") != SCHEMA:
            return f"not a mirror intents payload (schema {SCHEMA})"
        if p.get("pinned") is not True:
            return "the payload is not pinned to the decision instant"
        if p.get("replay") is not False:
            return "the brain answered with a replay"
        if p.get("session") != info["session"]:
            why = "; ".join(map(str, (p.get("problems") or [])[:2]))
            return f"the payload's session is {p.get('session')!r}, not {info['session']}" + (f" ({why})" if why else "")
        asof = _parse(p.get("asof_utc"))
        if asof is None or _iso(asof) != info["decide_utc"]:
            return f"decided as of {p.get('asof_utc')!r}, not the decision instant {info['decide_utc']}"
        bar = p.get("decision_bar")
        if not isinstance(bar, dict) or bar.get("complete") is not True:
            return "the decision bar is not complete"
        built = _parse(p.get("built_utc"))
        if built is None:
            return "the payload has no built_utc"
        if (built - now).total_seconds() > CLOCK_SKEW_S:
            return f"built {(built - now).total_seconds():.0f} s in the future"
        if (asof - built).total_seconds() > CLOCK_SKEW_S:
            return f"built at {p.get('built_utc')}, before the instant it decides ({info['decide_utc']})"
        if not isinstance(p.get("engines"), dict) or not isinstance(p.get("prices"), dict):
            return "the payload has no engines or no prices"
        return None

    def _intents(self, info: dict, wake) -> tuple:
        """(payload, None) | (None, why) | (_WOKEN, None). A pinned payload that passed is held for the
        session: the decision as of that instant does not change, so the pre-trade gates are retried
        without asking for it again. Anything else - the brain's 503 while the decision bar is being
        published included - is a reason to ask again in INTENTS_RETRY_S."""
        held = self._held
        if held and held[0] == info["session"] and held[1] == info["decide_utc"]:
            return held[2], None
        after = info["decide_utc"]
        got = self._brain_call(lambda: self.brain.intents(after), wake, INTENTS_DEADLINE_S) \
            if self.brain is not None else (None, "no_brain")
        if got is _WOKEN:
            return _WOKEN, None
        payload, reason = got
        now = self.clock()
        why = self._validate(payload, info, now) if payload is not None else (
            f"the brain is not ready (503{reason[len('http_503'):] or ': no reason given'})"
            if str(reason).startswith("http_503") else f"no intents ({reason})")
        self.brain_status["intents"] = {"ok": why is None, "reason": why or "ok", "utc": _iso(now)}
        if why is not None:
            return None, why
        self._held = (info["session"], after, payload)
        return payload, None

    def _decide(self, ad, info: dict, wake, stop, until: datetime) -> None:
        session = info["session"]
        while True:
            now = self.clock()
            if now >= info["plan_by"]:
                self._skip(session, f"nothing usable before {_iso(info['plan_by'])}: {self._why}")
                return
            if self._halted():                     # D1
                return
            static = self._pretrade_static()
            if static:                             # A-12: retrying cannot change it; the loop is not held for it
                self._skip(session, static)
                return
            payload, why = self._intents(info, wake)
            if payload is _WOKEN:
                return
            if why is None:
                self._apply_splits(payload, session)
                why = self._pretrade_account(ad)
            if why is None:
                break
            self._set_why(why)
            if self._pause(self._retry_s, wake, stop, until):
                return
        self._set_why(None)
        if self._halted():                         # D1: the halt is re-read wherever an order can originate
            return
        if self._start(ad, info, payload, wake) == "started":
            self._drive(ad, wake, stop, until)

    def _skip(self, session: str, reason: str) -> None:
        row = {"session": session, "outcome": "skipped", "reason": one_line(reason, 400), "utc": _iso(self.clock())}
        self.state["history"] = (list(self.state.get("history") or []) + [row])[-HISTORY_KEEP:]
        self.state["last_session"] = max(self.state.get("last_session") or "", session)
        self.state["last_run"] = row
        self._held = None
        self._save()
        self._journal("session_skipped", **row)
        self._say(self._loud(), f"{session}: NO TRADE — {row['reason']}. The sleeves keep "
                  f"yesterday's holdings; Composer rebalanced on its own.", key=f"skip:{session}")

    def _lost_behind_run(self, wake) -> None:
        """a session that passes while an older run is still open is a recorded NO TRADE, not a gap"""
        run = self.state.get("run")
        if not run:
            return
        info = self._session(wake)
        if not info or not info.get("session"):
            return
        session = info["session"]
        if session <= run["session"] or (self.state.get("last_session") or "") >= session or self.clock() < info["plan_by"]:
            return
        stuck = sorted(k for k, v in (run.get("orders") or {}).items() if v.get("state") != "booked")
        self._skip(session, f"the run of {run['session']} is still open on {', '.join(stuck) or 'its orders'}: nothing "
                            f"new is planned until it is resolved (POST /mirror/resolve)")

    def _targets(self, payload: dict, notes: list | None = None) -> dict:
        """the plan's targets for the active sleeves; Composer's rebalance rule rides on the payload.
        R3: a LIVE sleeve trades only on a tree the payload's own `sync` row says is Composer's live
        one (state "ok"). A missing row or any other state is a SKIP here, whatever the brain's engine
        status says and however the brain is configured: fail-closed for real money. A paper book
        trades regardless and notes it."""
        out = {}
        sync = payload.get("sync") if isinstance(payload.get("sync"), dict) else {}
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
            srow = sync.get(name)
            state = srow.get("state") if isinstance(srow, dict) else None
            if state != "ok":
                said = (f"sync state {state!r}: approved version {srow.get('approved_version')!r}, Composer's live "
                        f"version {srow.get('live_version')!r}" if isinstance(srow, dict) else "no sync row in the payload")
                if self.cfg.live:
                    also = "" if row.get("status") == "ok" else \
                        f"; the brain also says: {one_line(row.get('note') or row.get('status') or 'no target published', 160)}"
                    out[name] = {"status": "unavailable", "version": row.get("version"),
                                 "skip_reason": f"LIVE tree gate: {name}'s tree is not attested as Composer's live one "
                                                f"({said}): not traded{also}"}
                elif notes is not None and row.get("status") == "ok":
                    notes.append(f"paper: {name} traded although its tree is not attested ({said}); a live book refuses this")
        return out

    def _venue_prices(self, ad, symbols, prices: dict, notes: dict, wake=None):
        """live only: every symbol the plan would trade against the venue's own quote. Returns (prices
        with the failures removed and the brain's estimates replaced by the venue's quote, {symbol:
        why it failed}, {symbol: the accepted quote}); None when a halt or a wake landed between two
        symbols (nothing is decided on half a check)."""
        out, bad, quotes = dict(prices), {}, {}
        t0 = time.monotonic()
        for sym in sorted(symbols):
            if self._woken(wake) or self._halted():
                return None
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
            quotes[sym] = px
            if sym in notes:
                out[sym] = px                       # the brain's price was an estimate: size on the quote
        return out, bad, quotes

    @staticmethod
    def _plan_symbols(plan: dict) -> set:
        syms = {o["symbol"] for o in plan["sells"]} | {c["symbol"] for c in plan["crosses"]}
        for asks in plan["buy_asks"].values():
            syms |= set(asks)
        return syms

    # -------------------------------------------------------------- splits, dividends, credits
    def _apply_splits(self, payload: dict, session: str) -> None:
        """every split the brain lists that this book has not applied: sleeve shares rescaled
        (mirror_core.apply_split) BEFORE the pre-trade gate, which then decides whether the account
        agrees. Applied only to a book that has not yet run a session on post-split prices."""
        rows = payload.get("splits")
        if not isinstance(rows, list):
            return
        done = list(self.state.get("splits_applied") or [])
        marks = self.state.get("marks") or {}
        asof = _parse(marks.get("asof"))
        marks_day = asof.astimezone(ET).date().isoformat() if asof else None
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker, day, ratio = row.get("ticker"), row.get("date"), _num(row.get("ratio"))
            if not isinstance(ticker, str) or not ticker or mc.parse_day(day) is None or ratio is None or ratio <= 0:
                continue
            day = mc.parse_day(day).isoformat()
            key = mc.split_key(ticker, day)
            if day > session or key in done:
                continue
            done.append(key)
            changed = True
            held = self.book.positions().get(ticker, 0)
            if not held or abs(ratio - 1.0) < 1e-9:
                self._journal("split_seen", id=key, ticker=ticker, ratio=ratio, held=held, applied=False)
                continue
            if marks_day is not None and marks_day >= day:
                self._journal("split_late", id=key, ticker=ticker, ratio=ratio, held=held, marks_day=marks_day)
                self._say("red", f"split {ticker} x{ratio:g} dated {day} was published after this book had already "
                                 f"run a session on post-split prices ({marks_day}): it is NOT applied. The book "
                                 f"holds {held} {ticker}; compare with the account and repair with POST /mirror/adjust.")
                continue
            res = mc.apply_split(self.book, ticker, ratio)
            self._holdings_row(day, f"split {ticker} x{ratio:g}", from_open=True)
            px = _num((payload.get("prices") or {}).get(ticker))
            old = _num((marks.get("prices") or {}).get(ticker))
            if old is not None:
                marks.setdefault("prices", {})[ticker] = old / ratio
            owed = round(res["fraction"] * px, 2) if px is not None else None
            self._journal("split", id=key, date=day, cash_in_lieu_owed=owed, price=px, **res)
            self._say("warn", f"split {ticker} x{ratio:g} ({day}): the book's {res['total_before']} shares are now "
                              f"{res['total_after']} ({res['before']} -> {res['after']})"
                              + (f"; {res['fraction']:.4f} of a share is owed as cash in lieu"
                                 + (f" (about ${owed:,.2f})" if owed is not None else "")
                                 + ": NOT booked - credit it with POST /mirror/credit when the account receives it"
                                 if res["fraction"] > 1e-9 else ""))
        if changed:
            self.state["splits_applied"] = done[-300:]
            self._rebuild_paper()
            self._save()

    def _holdings_before(self, ex_date: str) -> dict:
        """{sleeve: {ticker: shares}} at the last close before `ex_date` that the history records for
        each sleeve (a skipped session records none); a sleeve with no such row has no entitlement.
        The LATEST row written that is dated before the ex-date counts - a session's own row, or a
        holdings row for shares that changed outside a run (_holdings_row); a split's row counts
        for an ex-date on its own day too (the shares were rescaled at that day's open)."""
        out: dict = {}
        for row in reversed(self.state.get("history") or []):
            if not isinstance(row, dict):
                continue
            day = str(row.get("session") or "")
            if day > ex_date or (day == ex_date and not (row.get("outcome") == "holdings" and row.get("from_open") is True)):
                continue
            for name, d in (row.get("sleeves") or {}).items():
                if name not in out and isinstance(d, dict) and isinstance(d.get("shares"), dict):
                    out[name] = dict(d["shares"])
        return out

    def _dividends(self, ad, payload: dict, session: str, notes: list, credits: list) -> None:
        """the receivables of every dividend not seen before, then the settlement of the ones due
        (mirror_core does the accounting; this is the I/O around it)"""
        recs = [dict(r) for r in self.state.get("dividends") or []]
        seen = list(self.state.get("div_seen") or [])
        rows = payload.get("dividends")
        for row in rows if isinstance(rows, list) else []:
            d = mc.clean_dividend(row)
            if d is None or d["ex_date"] > session:
                continue
            key = mc.dividend_key(d["ticker"], d["ex_date"])
            if key in seen:
                if d["pay_date"]:                  # a LATER listing carries the pay date an earlier one lacked
                    for r in recs:
                        if r.get("status") == "open" and not r.get("pay_date") and r.get("ticker") == d["ticker"] \
                                and r.get("ex_date") == d["ex_date"]:
                            r["pay_date"] = d["pay_date"]
                            self._journal("dividend_pay_date", id=r["id"], pay_date=d["pay_date"], learnt=session)
                continue
            seen.append(key)
            if d["ex_date"] == session:
                holdings, basis = {n: dict(s.shares) for n, s in self.book.sleeves.items()}, "holdings before this session's plan"
            else:
                holdings, basis = self._holdings_before(d["ex_date"]), "the last recorded close before the ex-date"
            new = mc.dividend_receivables(holdings, d)
            for r in new:
                r.update(status="open", seen=session, basis=basis, waited=0)
                recs.append(r)
            self._journal("dividend", id=key, dividend=d, basis=basis, receivables=new)
            if new:
                notes.append(f"dividend {d['ticker']} ex {d['ex_date']} ${d['amount']:g}/sh, pay "
                             + (d["pay_date"] or "date NOT KNOWN YET (left open)") + ": receivable "
                             + ", ".join(f"{r['sleeve']} ${r['total']:,.2f} ({r['shares']} sh)" for r in new))
        have = _UNKNOWN
        for r in recs:
            due = mc.receivable_pay_date(r, session) if r.get("status") == "open" else None
            if due is None or due > session:
                continue
            if not r.get("pay_date"):              # never learnt: ex + 7 days is assumed, ten days after the ex-date
                r.update(pay_date=due, pay_date_assumed=True)
                self._journal("dividend_pay_date", id=r["id"], pay_date=due, assumed=True)
            arrived = True
            if self.cfg.live:
                if have is _UNKNOWN:
                    have = _num((ad.account_cash() or {}).get("total_cash"))
                arrived = have is not None and self.book.cash() + float(r["total"]) <= have + CASH_TOL_USD
            out = mc.settle_receivable(self.book, r, session, self.cfg.dividend_rule, cash_arrived=arrived)
            act = out["action"]
            if isinstance(out.get("held"), bool):
                r["held"] = out["held"]
            if act == "credited":
                r.update(status="credited", settled=session)
                credits.append({"sleeve": r["sleeve"], "amount": r["total"], "kind": "dividend", "id": r["id"]})
                notes.append(f"{r['sleeve']} credited ${r['total']:,.2f}: dividend {r['ticker']} ex {r['ex_date']} "
                             f"({r['shares']} sh)")
                self._journal("dividend_credited", **r)
            elif act == "leaked":
                r.update(status="leaked", settled=session)
                notes.append(f"dividend {r['ticker']} ex {r['ex_date']} ${r['total']:,.2f}: {r['sleeve']} no longer "
                             f"holds it on the pay date - left unallocated in the account (Composer's rule)")
                self._journal("dividend_leaked", **r)
            elif act == "void":
                r.update(status="void", settled=session)
                self._journal("dividend_void", **r)
            elif act == "expired":
                r.update(status="expired", settled=session)
                self._journal("dividend_expired", **r)
                self._say("red", f"dividend receivable {r['id']} (${r['total']:,.2f}) is CLOSED as expired: "
                                 f"{mc.RECEIVABLE_EXPIRE_DAYS} days after its pay date {r['pay_date']} the account's "
                                 f"cash still does not cover it. If it was paid, credit it with POST /mirror/credit.")
            elif act == "wait":
                if r.get("last_wait") != session:
                    r["last_wait"] = session
                    r["waited"] = int(r.get("waited") or 0) + 1
                if r["waited"] >= DIVIDEND_ALERT_SESSIONS and not r.get("alerted"):
                    r["alerted"] = True
                    self._say("red", f"dividend receivable {r['id']} (${r['total']:,.2f}, pay date {r['pay_date']}) is "
                                     f"still unpaid after {r['waited']} sessions: the account's cash does not cover the "
                                     f"book's plus it. Check the account's dividend postings.")
        closed = [r for r in recs if r.get("status") != "open"]
        self.state["dividends"] = [r for r in recs if r.get("status") == "open"] + closed[-200:]
        self.state["div_seen"] = seen[-500:]

    def _apply_credits(self, ad, notes: list, credits: list) -> None:
        """the queued cash adjustments, DEBITS FIRST (ascending amount): a fee and the dividend that
        offsets it both apply, whatever order they were sent in"""
        keep, rows = [], []
        for r in self.state.get("requests") or []:
            (rows if r.get("kind") == "credit" else keep).append(r)
        rows.sort(key=lambda r: _num(r.get("amount")) if _num(r.get("amount")) is not None else 0.0)
        for r in rows:
            name, amt = r.get("sleeve"), _num(r.get("amount"))
            ok = name in self.book.sleeves and amt is not None
            why = None if ok else "unknown sleeve or amount"
            if ok and amt < 0 and self.book.sleeves[name].cash + amt < -mc.DEBT_TOL_USD and r.get("force") is not True:
                ok, why = False, (f"{name} has ${self.book.sleeves[name].cash:,.2f} in cash: a debit of ${-amt:,.2f} "
                                  f"would put it IN DEBT (check the amount; \"force\": true if it is meant)")
            if ok and self.cfg.live and amt > 0:
                have = _num((ad.account_cash() or {}).get("total_cash"))
                if have is None or self.book.cash() + amt > have + CASH_TOL_USD:
                    ok, why = False, f"the account's cash ({have!r}) does not cover the book's plus the credit"
            funded = _num(self.state.get("funded_usd")) or 0.0
            if ok and self.cfg.live and amt > 0 and r.get("force") is not True \
                    and funded + amt > self._book_cap_usd() + SEED_TOL_USD:
                # D-04: the account's spare cash is no bound on a typo; the capital the book was given is
                ok, why = False, (f"the live book has taken ${funded:,.2f} in seeds and credits; ${amt:,.2f} more "
                                  f"would pass its cap of ${self._book_cap_usd():,.2f} (MIRROR_MAX_BOOK_USD, or "
                                  f"MIRROR_CAPITAL_USD when that is unset). Check the amount (a slipped decimal?); "
                                  f"raise the cap, or send it with \"force\": true if it is meant")
            if ok:
                if amt > 0:
                    self.state["funded_usd"] = round(funded + amt, 2)
                if self.cfg.live:                  # every credit a live book takes is said (deferred until the plan is on disk)
                    self._say("warn", f"sleeve {name} {'CREDITED' if amt > 0 else 'DEBITED'} ${abs(amt):,.2f} by the "
                                      f"operator ({r.get('note') or 'no note'})"
                                      + (" [FORCED]" if r.get("force") is True else "")
                                      + f": seeds and credits now total ${_num(self.state.get('funded_usd')) or 0.0:,.2f} "
                                        f"of a cap of ${self._book_cap_usd():,.2f}")
                self.book.sleeves[name].cash += amt
                notes.append(f"{name} {'credited' if amt > 0 else 'debited'} ${abs(amt):,.2f} ({r.get('note') or 'no note'})")
                credits.append({"sleeve": name, "amount": amt, "kind": "credit", "id": r.get("id"), "note": r.get("note")})
                self._journal("credit", **r)
            else:
                notes.append(f"credit {r.get('id')} REFUSED: {why}")
                self._say("red", f"credit of ${amt!r} to {name} refused: {why}. Re-submit when it holds.")
                self._journal("credit_refused", why=why, **r)
        self.state["requests"] = keep

    # -------------------------------------------------------------- the plan
    def _start(self, ad, info: dict, payload: dict, wake) -> str:
        """Build the session's plan and put the run on disk: "started". ATOMIC in memory: a halt or a
        wake seen before the save, a save that fails, or ANY exception restores the book and the
        state (queued requests included) to what they were - "dropped" (the next tick tries again) or
        "skipped" (a recorded NO TRADE)."""
        snap_book = self.book.to_dict()
        snap_state = {k: copy.deepcopy(v) for k, v in self.state.items() if k != "history"}
        self._deferred = []
        try:
            out = self._plan(ad, info, payload, wake)
        except Exception:
            self._rollback(snap_book, snap_state)
            raise
        if out != "started":
            self._rollback(snap_book, snap_state)
            if out.startswith("skip:"):
                self._skip(info["session"], out[5:])
                return "skipped"
            return "dropped"
        later, self._deferred = self._deferred, None
        for item in later:
            if item[0] == "journal":
                self._journal(item[1], **item[2])
            else:
                self._say(item[1], item[2], item[3])
        return "started"

    def _rollback(self, snap_book: dict, snap_state: dict) -> None:
        self._deferred = None
        self.book = mc.Book.from_dict(snap_book)
        self.state.update(snap_state)
        self._publish()

    def _plan(self, ad, info: dict, payload: dict, wake) -> str:
        session, now = info["session"], self.clock()
        prices = {s: p for s, p in ((s, _num(p)) for s, p in payload["prices"].items()) if p is not None and p > 0}
        price_notes = {s: str(n) for s, n in (payload.get("price_notes") or {}).items() if s in prices}
        notes, credits = [], []
        self._dividends(ad, payload, session, notes, credits)
        self._apply_credits(ad, notes, credits)
        transfers = [r for r in self.state.get("requests") or [] if r.get("kind") == "transfer"]
        self.state["requests"] = [r for r in self.state.get("requests") or [] if r.get("kind") != "transfer"]
        asks = [{"from": r.get("from"), "to": r.get("to"), "amount": r.get("amount")} for r in transfers]
        targets = self._targets(payload, notes)
        pre = {}
        for name, s in self.book.sleeves.items():
            try:
                pre[name] = round(mc.equity(s, prices), 2)
            except mc.MirrorError:
                pre[name] = None
        plan = mc.build_plan(self.book, targets, prices, session, self.cfg.core, asks)
        dropped, quotes = {}, {}
        if self.cfg.live:
            checked: set = set()
            for _ in range(QUOTE_PASSES):          # A-14: a rebuilt plan can ADD symbols; check those too
                need = self._plan_symbols(plan) - checked
                if not need:
                    break
                got = self._venue_prices(ad, need, prices, price_notes, wake)
                if got is None:
                    return "dropped"
                prices, bad, seen = got
                checked |= need
                dropped.update(bad)
                quotes.update(seen)
                plan = mc.build_plan(self.book, targets, prices, session, self.cfg.core, asks)
            extra = self._plan_symbols(plan) - checked
            if extra:                              # never trade a symbol the venue check has not seen; never halt for it
                return (f"skip:the plan kept adding symbols the venue cross-check had not seen ({sorted(extra)}) "
                        f"after {QUOTE_PASSES} passes")
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
                self._say("red", f"transfer {r.get('id')} of ${r.get('amount')!r} {r.get('from')} -> {r.get('to')} was "
                                 f"REFUSED by {session}'s plan (a sleeve is out of it, or the amount exceeds the "
                                 f"giver's equity): re-submit it.")
        if payload.get("actions_complete") is False:
            self._say("warn", f"{session}: the brain's dividend and split lists are INCOMPLETE today (it could not read "
                              f"them all): a dividend or a split may be missing from this session; pay dates not yet "
                              f"known are left open", key=f"actions:{session}")
        if self._halted() or self._woken(wake):    # D1: the last look before the run exists
            return "dropped"
        mc.apply_crosses(self.book, plan)
        labels = {n: (payload["engines"].get(n) or {}).get("label") for n in targets}
        self.state["run"] = {"session": session, "phase": "sells", "started_utc": _iso(now),
                             "decide_utc": info["decide_utc"], "cancel_utc": _iso(info["cancel_at"]),
                             "close_utc": _iso(info["close_at"]), "intents_asof": payload.get("asof_utc"),
                             "built_utc": payload.get("built_utc"), "decision_bar": payload.get("decision_bar"),
                             "sync": payload.get("sync"), "actions_complete": payload.get("actions_complete"),
                             "problems": [one_line(x, 200) for x in (payload.get("problems") or [])[:4]]
                             if isinstance(payload.get("problems"), list) else [],
                             "labels": labels, "pre_equity": pre, "plan": plan, "orders": {}, "notes": notes,
                             "credits": credits, "transfer_reqs": transfers, "venue_quotes": quotes,
                             "price_notes": {s: n for s, n in price_notes.items() if s in plan["prices"]},
                             "price_times": {s: t for s, t in (payload.get("price_times") or {}).items()
                                             if s in plan["prices"]} if isinstance(payload.get("price_times"), dict) else {},
                             "dropped": dropped, "quotes": payload.get("quotes")}
        marks = dict((self.state.get("marks") or {}).get("prices") or {})
        marks.update(prices)
        self.state["marks"] = {"prices": marks, "asof": payload.get("asof_utc")}
        self._deferred, later = None, self._deferred
        saved = self._save()
        self._deferred = later
        if not saved:
            return "dropped"                       # D4: nothing reaches the venue without its record on disk
        self._journal("plan", session=session, intents_asof=payload.get("asof_utc"),
                      decision_bar=payload.get("decision_bar"), sync=payload.get("sync"),
                      sleeves={n: {k: d.get(k) for k in ("action", "reason", "gap", "deltas", "target", "version")}
                               for n, d in plan["sleeves"].items()},
                      crosses=plan["crosses"], sells=[{k: o[k] for k in ("id", "symbol", "qty", "asks", "ref")} for o in plan["sells"]],
                      buy_asks=plan["buy_asks"], transfers=plan["transfers"], notes=notes)
        return "started"

    # -------------------------------------------------------------- orders
    def _drive(self, ad, wake, stop, until: datetime) -> None:
        while True:
            if self._advance(ad, wake=wake):
                self._finish(ad)
                return
            if self._halted():
                return                              # the halt path settles what is in flight
            if self._woken(wake):
                return                              # A-23: the run is on disk; the next tick carries on
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

    def _advance(self, ad, abort: bool = False, wake=None) -> bool:
        """work the run's orders once; True when every order is booked"""
        run = self.state["run"]
        plan = run["plan"]
        cancel_at = _parse(run["cancel_utc"]) or self.clock()
        if run["phase"] == "sells":
            if not self._work_all(ad, plan["sells"], run["orders"], cancel_at, abort, wake):
                return False
            past = abort or self.clock() >= cancel_at
            limits = None
            if not past:
                if self._halted():                 # D1: before any buy is sized
                    return False
                limits = self._buy_limits(ad, run, wake)
                if limits is None:
                    return False                   # woken or halted between two quotes: nothing was changed
            if any(t["status"] == "planned" for t in plan["transfers"]) and not plan.get("transfers_applied"):
                mc.apply_transfers(self.book, plan)
            unfunded = None if past else self._buys_unfunded(ad, run)
            if past or unfunded:
                plan["buys"] = []
                if plan["buy_asks"]:
                    run.setdefault("notes", []).append("buys NOT sent: " + (unfunded or run.get("aborted") or
                                                       "the window closed before the sells were booked"))
            else:
                mc.size_buys(self.book, plan, None, self.cfg.core, limits=limits)
            run["phase"] = "buys"
            self._save()
        if run["phase"] == "buys":
            return self._work_all(ad, plan["buys"], run["orders"], cancel_at, abort, wake)
        return True

    def _buys_unfunded(self, ad, run: dict) -> str | None:
        """C-52 (live): the sells are booked and the buys are about to be sized from the BOOK's cash. On a
        margin account the venue lends whatever the book over-counts (a sell booked at its reference
        with no price reported, a fee the book does not know), so the ACCOUNT's cash is read first: the
        buys go only if it covers the book's (within CASH_TOL_USD). Why not, or None. A paper book
        has no account to read."""
        if self._dry is not None or not any(int(q) > 0 for asks in run["plan"]["buy_asks"].values() for q in asks.values()):
            return None
        try:
            have = _num((ad.account_cash() or {}).get("total_cash"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("mirror[%s] account cash unreadable before the buys: %s", self.cfg.name, one_line(exc))
            have = None
        mine = self.book.cash()
        if have is None:
            why = "the account's cash cannot be read, so nothing proves it covers the buys"
        elif mine > have + CASH_TOL_USD:
            why = (f"the book's cash ${mine:,.2f} exceeds the account's ${have:,.2f} (by ${mine - have:,.2f}): "
                   f"buying from the book's figure would borrow on margin")
        else:
            return None
        self._say("red", f"{run['session']}: NO BUYS are sent this session — {why}. The sells are booked; the "
                         f"sleeves keep the cash until the next session. Compare the account with /status (a fee is "
                         f"debited with POST /mirror/credit).", key=f"buys-unfunded:{run['session']}")
        return why

    def _work_all(self, ad, orders: list, recs: dict, cancel_at, abort: bool, wake) -> bool:
        waiting = False
        for o in orders:
            if o.get("applied"):
                continue
            if not abort and self._woken(wake):
                return False                        # A-23: between two orders the loop is handed back
            if not self._work(ad, o, recs, cancel_at, abort=abort):
                waiting = True
        return not waiting

    def _buy_limits(self, ad, run: dict, wake) -> dict | None:
        """{symbol: limit} for the buys about to be sized: live, the venue's quote of each is read
        AGAIN (the sells took time) and the limit is that quote x (1 + buy_cushion), floored to the
        venue's grid; a quote that cannot be read, or has left the band since the plan's check, falls
        back to the higher of the brain's price and the quote read at plan time. Paper: {} - the core
        sizes at reference x (1 + cushion) and the paper adapter fills at the reference. None when a
        halt or a wake landed between two quotes."""
        plan = run["plan"]
        syms = sorted({s for asks in plan["buy_asks"].values() for s, q in asks.items() if int(q) > 0})
        if self._dry is not None or not syms:
            return {}
        seen, notes = run.get("venue_quotes") or {}, run.get("price_notes") or {}
        out, log, t0 = {}, {}, time.monotonic()
        for sym in syms:
            if self._woken(wake) or self._halted():
                return None
            ref = _num(plan["prices"].get(sym))
            base = max([x for x in (ref, _num(seen.get(sym))) if x is not None and x > 0], default=None)
            if base is None:
                continue                            # cannot happen (the plan priced it): the core's default applies
            px, how = base, "fallback"
            if time.monotonic() - t0 <= BUY_QUOTE_BUDGET_S:
                try:
                    q, source = ad.spot_ex(sym)
                    q = _num(q)
                    band = self.cfg.est_quote_band if sym in notes else self.cfg.quote_band
                    if q is not None and q > 0 and source in QUOTE_SOURCES and abs(q / base - 1.0) <= band:
                        px, how = q, "quote"
                    else:
                        how = f"fallback ({q!r} from {source})"
                except Exception as exc:  # noqa: BLE001
                    how = f"fallback ({one_line(exc, 60)})"
            else:
                how = "fallback (out of time)"
            try:
                out[sym] = round_limit_to_tick(mc.buy_limit(px, self.cfg.core), "BUY")
            except ValueError:
                pass
            log[sym] = {"px": px, "how": how, "limit": out.get(sym)}
        run["buy_quotes"] = log
        return out

    def _may_place(self, emergency: bool) -> bool:
        """may a NEW order go to the venue right now? Re-read for every order (D1, D4)."""
        if emergency:
            return True                             # a flatten order: its caller re-reads whether it is still wanted
        return not self._latched and not self._halted()

    def _none_is_conclusive(self, ad, rec: dict, oid: str) -> tuple:
        """D3: is 'the venue has no such order' proof? Only for an order of TODAY (ET), and then only
        when the adapter's order history is complete OR it can show the order is neither open nor
        executed today (order_absent_today: both requests answered - N-04, the gateway that never
        answers for completed orders). (True, the proof) | (False, why not)"""
        if self._dry is not None:
            return True, "the paper adapter holds no such order"
        at = _parse(rec.get("intent_utc"))
        today = self.clock().astimezone(ET).date()
        if at is None or at.astimezone(ET).date() != today:
            return False, f"it was sent on {at.astimezone(ET).date().isoformat() if at else 'an unknown day'}, and the venue only answers for today"
        try:
            if ad.history_complete() is True:
                return True, "today's complete order history holds no trace of it"
        except Exception as exc:  # noqa: BLE001
            rec["find_error"] = one_line(exc, 160)
        try:
            absent = ad.order_absent_today(oid) if hasattr(ad, "order_absent_today") else None
        except Exception as exc:  # noqa: BLE001
            rec["find_error"] = one_line(exc, 160)
            absent = None
        if absent is True:
            return True, "it is neither among the venue's open orders nor among today's executions"
        return False, ("the venue's completed-order history is unavailable, and its open orders and today's "
                       "executions did not both answer" if absent is None else
                       "the venue's completed-order history is unavailable and it shows the order open or executed")

    def _work(self, ad, o: dict, recs: dict, cancel_at, abort: bool = False, emergency: bool = False) -> bool:
        """advance one venue order; True once it is booked. cancel_at: the instant after which nothing
        new is sent and what works is cancelled, looked at for THIS order (A-17). abort: stopped (a
        halt, or a flatten no longer wanted): send nothing, cancel what works. emergency: a flatten
        order (it goes out under a halt and under a save latch)."""
        if o.get("applied"):
            return True
        oid = o["id"]
        rec = recs.setdefault(oid, {"state": "new", "tries": 0})
        past = abort or (cancel_at is not None and self.clock() >= cancel_at)
        res = None
        if rec["state"] == "new":
            if past:
                return self._book(o, rec, 0, None, 0.0, "not sent: " + ("stopped" if abort else "the window closed"))
            if not self._may_place(emergency):
                return False
            if emergency and self._dry is None:
                # D-01: a flatten order goes out even when its write-ahead cannot be saved, so after a
                # restart on a stale file "new" does NOT prove it was never sent. The venue is asked first
                # (find_stock_order also reads today's executions) and its answer is settled, not repeated.
                res = self._find(ad, oid, rec)
                if res is _UNKNOWN:
                    self._say("red", f"flatten order {oid} is NOT sent yet: the venue could not be asked whether it "
                                     f"already holds it ({rec.get('find_error')}); asked again on the next step",
                              key=f"flat-noask:{oid}:{one_line(rec.get('find_error'), 60)}")
                    return False
                if res is not None:
                    rec.update(state="placed", order_ref=res.get("order_ref"), found_at_venue=_iso(self.clock()))
                    self._say("red", f"flatten order {oid} was ALREADY at the venue ({res.get('status')}) though "
                                     f"the state file did not know it (a save had failed before a restart): it is "
                                     f"settled from the venue's record, not sent again", key=f"flat-found:{oid}")
                    return self._settle(ad, o, rec, res, past)
            if emergency and not self._flatten_cap(ad, o, rec):
                return bool(o.get("applied"))
            if not self._write_ahead(o, rec, emergency):
                return False
            res = self._place(ad, o, rec)
        elif rec["state"] == "intent":
            # a placement whose outcome was never recorded (a crash, a raise): the venue is asked first
            res = self._find(ad, oid, rec)
            if res is _UNKNOWN:
                return False
            if res is None:
                ok, why = self._none_is_conclusive(ad, rec, oid)
                if not ok:
                    self._stuck(rec, oid, f"its placement was never confirmed and the venue now has no record of "
                                          f"it, which proves nothing: {why}")
                    return False
                if past or rec.get("tries", 0) >= PLACE_TRIES:
                    return self._book(o, rec, 0, None, 0.0, "never reached the venue"
                                      + (f" ({rec['error']})" if rec.get("error") else ""))
                if not self._may_place(emergency):
                    return False
                if emergency and not self._flatten_cap(ad, o, rec):
                    return bool(o.get("applied"))
                res = self._place(ad, o, rec)
            else:
                rec.update(state="placed", order_ref=res.get("order_ref"))
        else:
            res = self._find(ad, oid, rec)
            if res is _UNKNOWN:
                return False
            if res is None:
                if self._dry is not None:           # a paper adapter forgets its orders on a restart
                    if past or not self._may_place(emergency):
                        return self._book(o, rec, 0, None, 0.0, "not sent: the paper adapter restarted")
                    res = self._place(ad, o, rec)
                else:
                    ok, why = self._none_is_conclusive(ad, rec, oid)
                    if not ok:
                        self._stuck(rec, oid, f"the venue has no record of an order it acknowledged, which proves "
                                              f"nothing: {why}")
                        return False
                    return self._book(o, rec, 0, None, 0.0, f"gone from the venue unfilled (acknowledged; {why})")
        if res is None:
            return False
        return self._settle(ad, o, rec, res, past)

    def _flatten_cap(self, ad, o: dict, rec: dict) -> bool:
        """D-01: the last look before a flatten SELL goes to the venue of a live book. The account's
        positions are read again and the order is cut to what the account holds NOW: a flatten can
        never take a position below zero, whatever the state file believes (a restart on a stale
        file, a sale by hand since the round was built). True: send o (its qty may have been cut).
        False: nothing is sent - the order was booked at zero (the account holds none: o is applied),
        or the positions could not be read (said in red; asked again on the next step)."""
        if self._dry is not None or o.get("side") != mc.SELL:
            return True
        oid, sym = o["id"], o["symbol"]
        try:
            snap = ad.positions_snapshot()
            held = int((snap.get("stocks") or {}).get(sym, 0) or 0)
        except Exception as exc:  # noqa: BLE001
            rec["positions_error"] = one_line(exc, 160)
            self._say("red", f"flatten order {oid} is NOT sent: the account's positions cannot be read "
                             f"({rec['positions_error']}), and a sell that is not checked against them could take "
                             f"{sym} short. Tried again on the next step.",
                      key=f"flat-cap-nopos:{oid}:{one_line(exc, 60)}")
            return False
        want = int(o["qty"])
        if held <= 0:
            self._say("red", f"flatten order {oid} is NOT sent: the account holds {held} {sym} (the book asked to "
                             f"sell {want}). Nothing is sold below zero; the book still shows the shares - compare "
                             f"the account with /status.", key=f"flat-cap-zero:{oid}")
            self._book(o, rec, 0, None, 0.0, f"not sent: the account holds {held} {sym}")
            return False
        if held < want:
            o["qty"], rec["cut_from"] = held, want
            self._say("red", f"flatten order {oid} cut from {want} to {held} {sym}: that is all the account holds "
                             f"now", key=f"flat-cap-cut:{oid}:{held}")
        return True

    def _write_ahead(self, o: dict, rec: dict, emergency: bool) -> bool:
        """WRITE-AHEAD: the id is on disk before the venue sees it. 'intent' stands only if the save
        succeeded; a flatten order (the emergency stop) goes out regardless, loudly."""
        prev = dict(rec)
        rec.update(state="intent", intent_utc=_iso(self.clock()))
        if self._save():
            return True
        if emergency:
            self._say("red", f"flatten order {o['id']} is being sent with NO record on disk (the state file cannot "
                             f"be written): if this process restarts, compare the account with /status by hand.",
                      key=f"flat-nodisk:{o['id']}")
            return True
        rec.clear()
        rec.update(prev)
        return False

    def _place(self, ad, o: dict, rec: dict):
        rec["tries"] = int(rec.get("tries") or 0) + 1
        try:
            if o["side"] == mc.BUY:                 # D5: a buy is a LIMIT at the price it was sized at
                limit = _num(o.get("limit"))
                if limit is None or limit <= 0:
                    raise ValueError(f"buy {o['id']} has no limit price")
                res = ad.place_limit_order(o["symbol"], int(o["qty"]), limit, tif="DAY", ref_price=o.get("ref"),
                                           client_order_id=o["id"])
            else:
                res = ad.place_stock_order(o["symbol"], -int(o["qty"]), "MKT", tif="DAY", ref_price=o.get("ref"),
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
        """the order is UNRESOLVED: nothing is booked for it. Said when it starts, when the reason
        changes, and once a day while it stays so."""
        day = self.clock().astimezone(ET).date().isoformat()
        new = rec.get("stuck") != why
        if new:
            rec["stuck"] = why
            rec.setdefault("stuck_since", _iso(self.clock()))
        if new or rec.get("stuck_said") != day:
            rec["stuck_said"] = day
            self._save()
            self._say("red", f"order {oid} is UNRESOLVED (since {rec.get('stuck_since')}): {why}. The book is not "
                             f"updated for it and nothing new is planned until it resolves; check the account, then "
                             f"state what it did with POST /mirror/resolve.")

    def _cancelled_fills(self, ad, o: dict, rec: dict, res: dict):
        """for an order the venue answers 'cancelled': (the answer to book, what it executed), or None
        while that is not known. An order the venue holds as INACTIVE is cancelled first and read
        again (it is not dead: it can go live later). An unreadable executed quantity is never zero."""
        oid = o["id"]
        if not hasattr(ad, "stock_order_fills"):
            if res.get("filled_qty") is None:
                self._stuck(rec, oid, "cancelled at the venue, and this adapter cannot say what it executed")
                return None
            return res, {}
        for _ in range(2):
            try:
                f = ad.stock_order_fills(oid) or {}
            except Exception as exc:  # noqa: BLE001
                rec["fills_error"] = one_line(exc, 160)
                self._stuck(rec, oid, f"cancelled at the venue, but what it executed cannot be read "
                                      f"({rec['fills_error']})")
                return None
            if f.get("venue_status") == "Inactive" and not rec.get("inactive_cancel"):
                try:
                    sent = bool(ad.cancel_inactive_stock_order(oid))
                except Exception as exc:  # noqa: BLE001
                    rec["cancel_error"] = one_line(exc, 240)
                    self._stuck(rec, oid, f"INACTIVE at the venue (it can go live later) and the cancel could not "
                                          f"be sent ({rec['cancel_error']})")
                    return None
                rec["inactive_cancel"] = _iso(self.clock())
                self._save()
                logger.warning("mirror[%s] order %s was Inactive at the venue: cancel %s", self.cfg.name, oid,
                               "sent" if sent else "not needed")
                again = self._find(ad, oid, rec)
                if again is _UNKNOWN or again is None:
                    self._stuck(rec, oid, "INACTIVE at the venue; after the cancel it cannot be read")
                    return None
                if again.get("status") == "working":
                    return None                     # it went live: the next pass works it like any order
                res = again
                if res.get("status") == "filled":
                    return res, None
                continue                            # read again what it executed
            if res.get("filled_qty") is None and f.get("filled_qty") is None:
                self._stuck(rec, oid, "cancelled at the venue, but neither its record nor the executions say how "
                                      "many shares it filled")
                return None
            return res, f
        return res, f

    def _fill_terms(self, ad, o: dict, res: dict, rec: dict, fills: dict | None = None):
        """(price, commission) of what an order executed; the reference price, flagged, when the venue
        reports none (never zero, never a guess that is not on the record). None: not readable on
        this pass, ask again."""
        price, comm = _num(res.get("fill_price")), _num(res.get("commission"))
        if price is None or comm is None:
            f = fills
            if f is None and hasattr(ad, "stock_order_fills"):
                try:
                    f = ad.stock_order_fills(o["id"]) or {}
                except Exception as exc:  # noqa: BLE001
                    rec["fills_error"] = one_line(exc, 160)
                    rec["terms_tries"] = int(rec.get("terms_tries") or 0) + 1
                    if price is None and rec["terms_tries"] < TERMS_TRIES:
                        return None
                    f = {}
            f = f or {}
            price = price if price is not None else _num(f.get("avg_price"))
            comm = comm if comm is not None else _num(f.get("commission"))
        if price is None or price <= 0:
            # no price from the venue: a BUY is booked at its LIMIT (the most it can have cost: the book's
            # cash can then never exceed the account's), a sell at its reference. Flagged and said either way.
            limit = _num(o.get("limit")) if o.get("side") == mc.BUY else None
            price = limit if limit is not None and limit > 0 else _num(o.get("ref"))
            rec["price_estimated"] = "limit" if limit is not None and limit > 0 else "reference"
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
        fills = None
        if status == "cancelled":
            got = self._cancelled_fills(ad, o, rec, res)
            if got is None:
                return False
            res, fills = got
            status = res.get("status")
        if status == "filled":
            qty = int(o["qty"])
            if res.get("filled_qty") is not None:   # resolved from execution reports: completeness unproven
                qty = max(0, min(qty, int(res["filled_qty"])))
            how = "filled"
        elif status == "cancelled":
            known = [int(x) for x in (res.get("filled_qty"), (fills or {}).get("filled_qty")) if x is not None]
            qty = max(0, min(max(known), int(o["qty"])))
            how = "cancelled" + (f" ({one_line(res['reason'], 120)})" if res.get("reason") else "") \
                + (" [was Inactive at the venue: cancel sent]" if rec.get("inactive_cancel") else "")
        else:
            self._stuck(rec, o["id"], f"the venue answered status {status!r}")
            return False
        price, comm = (None, 0.0)
        if qty:
            terms = self._fill_terms(ad, o, res, rec, fills)
            if terms is None:
                return False
            price, comm = terms
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
                      ref=o.get("ref"), limit=o.get("limit"), commission=comm, split=split, how=how,
                      price_estimated=bool(rec.get("price_estimated")))
        if qty and rec.get("price_estimated"):
            self._say("red", f"order {o['id']}: {qty} {o['symbol']} booked at its "
                             f"{'LIMIT' if rec['price_estimated'] == 'limit' else 'REFERENCE'} price {price} because the "
                             f"venue reported no fill price. The book's cash is off by the difference; compare with the "
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
                           "limit": o.get("limit"),
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
        return {"session": run["session"], "outcome": outcome, "utc": _iso(self.clock()), "intents_asof": run.get("intents_asof"),
                "built_utc": run.get("built_utc"), "decision_bar": run.get("decision_bar"), "sync": run.get("sync"),
                "actions_complete": run.get("actions_complete"), "problems": list(run.get("problems") or []),
                "sleeves": sleeves,
                "orders": orders, "crosses": plan["crosses"], "transfers": plan["transfers"],
                "credits": list(run.get("credits") or []),
                "notes": list(run.get("notes") or []), "price_notes": run.get("price_notes") or {},
                "price_times": run.get("price_times") or {},
                "dropped": run.get("dropped") or {}, "prices": plan.get("prices") or {}}

    def _transfer_followups(self, run: dict) -> None:
        """A-09: a transfer that moved less than it was asked to is said, and its remainder rides the
        next plan (at most TRANSFER_TRIES plans in all)"""
        reqs = run.get("transfer_reqs") or []
        for t, r in zip(run["plan"]["transfers"], reqs):
            if t.get("status") not in ("partial", "planned"):
                continue
            amount, moved = float(t.get("amount") or 0.0), float(t.get("moved") or 0.0)
            left = round(amount - moved, 2)
            tries = int(r.get("tries") or 1)
            base = r.get("of") or r.get("id")
            if left < 0.01:
                continue
            again = tries < TRANSFER_TRIES
            line = (f"transfer {r.get('id')} {t.get('from')} -> {t.get('to')}: ${moved:,.2f} of ${amount:,.2f} moved "
                    f"(the giver's sells did not raise the rest"
                    + (" - the run was aborted" if run.get("aborted") else "") + "); "
                    + (f"${left:,.2f} is queued again for the next plan (try {tries + 1} of {TRANSFER_TRIES})" if again
                       else f"${left:,.2f} was NOT moved after {TRANSFER_TRIES} plans: re-submit it"))
            run.setdefault("notes", []).append(line)
            self._say("red", line)
            if again:
                nxt = {"kind": "transfer", "from": t.get("from"), "to": t.get("to"), "amount": left,
                       "note": r.get("note") or "", "id": f"{base}-r{tries + 1}", "of": base, "tries": tries + 1,
                       "utc": _iso(self.clock())}
                self.state["requests"] = list(self.state.get("requests") or []) + [nxt]
                self._journal("transfer_requeued", **nxt)

    def _finish(self, ad) -> None:
        run = self.state["run"]
        mc.finish(self.book, run["plan"])
        self._transfer_followups(run)
        row = self._summary(run)
        self.state["history"] = (list(self.state.get("history") or []) + [row])[-HISTORY_KEEP:]
        self.state["last_session"] = max(self.state.get("last_session") or "", run["session"])
        self.state["last_run"] = row
        self.state["run"] = None
        self.state["check"] = None
        self._held = None
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
        # R4: a sleeve that was held back is never an info line - RED on a live book, WARN on paper
        active = set(self._active())
        held_back = sorted(n for n, d in row["sleeves"].items() if n in active and d["action"] == "skip")
        loud = bool(held_back) or row["outcome"] == "no-targets"
        self._say(self._loud() if loud else "info",
                  (f"{', '.join(held_back) or 'EVERY sleeve'} NOT TRADED — " if loud else "")
                  + f"{row['session']} {row['outcome']}: " + " · ".join(parts)
                  + (" | " + ", ".join(fills) if fills else "")
                  + (f" | cost vs the decision price {sum(cost) / len(cost):+.1f} bps avg" if cost and self.cfg.live else "")
                  + (" | NOTES: " + "; ".join(row["notes"]) if row["notes"] else "")
                  + (" | THE BRAIN'S PROBLEMS: " + "; ".join(row["problems"][:3]) if loud and row["problems"] else ""),
                  key=f"done:{row['session']}")

    def _post_check(self, ad, session: str, wake=None) -> None:
        """after the session's run: the account must hold the book. A mismatch seen CHECK_STRIKES times,
        CHECK_GAP_S apart, halts the book (one read can catch a position report in flight)."""
        self._true_up(ad, wake)
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
                      + (". HALTED until /resume (repair a real divergence with POST /mirror/adjust first)."
                         if self.cfg.live else ""), key=f"mismatch:{session}")

    def _true_up(self, ad, wake=None) -> None:
        """commissions the venue had not reported when their fills were booked"""
        pend = list(self.state.get("commission_pending") or [])
        if not pend or not hasattr(ad, "stock_order_fills"):
            return
        if self._trued_at is not None and (self.clock() - self._trued_at).total_seconds() < TRUE_UP_EVERY_S:
            return
        self._trued_at = self.clock()
        left, changed = [], False
        for p in pend:
            if self._woken(wake):                  # A-23: one venue read per order; a woken loop gets the thread back
                left.append(p)
                continue
            try:
                comm = _num((ad.stock_order_fills(p["id"]) or {}).get("commission"))
            except Exception:  # noqa: BLE001
                comm = None
            split = {k: int(v) for k, v in (p.get("split") or {}).items() if k in self.book.sleeves and int(v) > 0}
            if comm is None or not split:
                booked = _parse(p.get("utc"))
                if split and booked and (self.clock() - booked).total_seconds() < COMMISSION_GIVE_UP_S:
                    left.append(p)                  # still unreported: asked again for three days
                    continue
                self._journal("commission_dropped", id=p.get("id"), split=p.get("split"), booked_utc=p.get("utc"))
                self._say("warn", f"the commission of order {p.get('id')} was never reported by the venue "
                                  f"({COMMISSION_GIVE_UP_S / 86400:.0f} days): it is no longer asked for. If the "
                                  f"account was charged one, the book's cash is too high by it - debit it with POST "
                                  f"/mirror/credit (a negative amount).", key=f"comm-drop:{p.get('id')}")
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
    def _flatten_wanted(self) -> bool:
        h = self.halt_state()
        return bool(h.get("flatten") and not h.get("flatten_done") and not h.get("flatten_cancelled"))

    def _flatten_tick(self, ad) -> bool:
        """The flatten, first thing in a tick. The STATE's flatten orders are the truth for what is in
        flight: whatever the halt file says they are settled first (worked while a flatten is still
        wanted, cancelled and booked at what filled when it is not), and state['flatten'] is never
        replaced while one of them is unbooked. Then, while the halt wants a flatten, the next round
        is built for what the book and the account both still hold. True: nothing is pending (the
        tick carries on); False: the tick ends here."""
        fl = self.state.get("flatten") or {}
        live = [o for o in fl.get("orders") or [] if not o.get("applied")]
        h = self.halt_state()
        if not live and not (h.get("flatten") and not h.get("flatten_done")):
            return True
        if ad is None:
            return False
        for _ in range(3):
            fl = self.state.get("flatten") or {}
            live = [o for o in fl.get("orders") or [] if not o.get("applied")]
            if live:
                waiting = False
                for o in live:                      # D1: 'still wanted' is re-read for every order
                    if not self._work(ad, o, fl.setdefault("recs", {}), None, abort=not self._flatten_wanted(),
                                      emergency=True):
                        waiting = True
                if waiting:
                    # C-10: the budget bounds REFUSALS (open time between rounds). While an order is
                    # working (a halted symbol, a venue that cannot be read) no open time is counted:
                    # the clock starts again at the first look after they are all booked.
                    fl["seen_utc"] = None
                    return False
            self._flatten_tally(fl)
            h = self.halt_state()
            if not (h.get("flatten") and not h.get("flatten_done")):
                return True
            if h.get("flatten_cancelled"):
                return self._flatten_finish(ad, True, "cancelled" if fl.get("id") == h.get("flatten_id") and fl.get("orders")
                                            else "cancelled before any order was sent")
            step = self._flatten_round(ad, h)
            if step == "done":
                return True
            if step == "wait":
                return False
        return False

    def _flatten_tally(self, fl: dict) -> None:
        """once per round: what its orders sold, kept for the closing line; and (V2-B2) a holdings row,
        because the sleeves' shares just changed with no planned session to record them"""
        if not fl or fl.get("tallied") or any(not o.get("applied") for o in fl.get("orders") or []):
            return
        fl["tallied"] = True
        fl["sold"] = list(fl.get("sold") or []) + [
            f"{o.get('filled', 0)}/{o['qty']} {o['symbol']}" + (f" @{o['price']:.2f}" if o.get("price") else "")
            for o in fl.get("orders") or []]
        if any(o.get("filled") for o in fl.get("orders") or []):
            self._holdings_row(self.clock().astimezone(ET).date().isoformat(), "flatten")
        self._save()

    def _flatten_clock(self, fl: dict) -> float:
        """N-08: the OPEN-session seconds this flatten has been at it. Time is counted only between two
        looks at it inside a session, no further apart than the loop can legitimately be (a night, a
        weekend or an outage adds nothing)."""
        now = self.clock()
        open_s = float(fl.get("open_s") or 0.0)
        if not self._rth(now):
            return open_s
        seen = _parse(fl.get("seen_utc"))
        cap = max(FLATTEN_SEEN_CAP_S, 2.0 * float(self.cfg.poll_s))
        if seen is not None and 0 < (now - seen).total_seconds() <= cap:
            open_s += (now - seen).total_seconds()
        fl["open_s"], fl["seen_utc"] = open_s, _iso(now)
        return open_s

    @staticmethod
    def _flatten_gap(n: int) -> float:
        """the wait after round n (1-based) before round n + 1 may be built"""
        return FLATTEN_GAPS_S[n - 1] if 1 <= n <= len(FLATTEN_GAPS_S) else FLATTEN_GAP_LATE_S

    def _flatten_round(self, ad, h: dict) -> str:
        """build the next round of a wanted flatten: "built" | "wait" | "done" """
        fid = h.get("flatten_id") or "x"
        fl = self.state.get("flatten") or {}
        mine = fl.get("id") == fid
        n = int(fl.get("round") or (1 if fl.get("orders") is not None else 0)) if mine else 0
        blocked: dict = {}
        if self.state.get("run"):
            self._abort_run(ad, "kill")
            run = self.state.get("run")
            if run:                                 # unresolved orders: flatten AROUND them (A-02)
                for o in run["plan"]["sells"] + (run["plan"].get("buys") or []):
                    if not o.get("applied"):
                        blocked[o["symbol"]] = o["id"]
                self._say("red", f"flatten: {', '.join(sorted(blocked))} held back — the run of {run['session']} has "
                                 f"unresolved order(s) on them ({', '.join(sorted(blocked.values()))}). Every other "
                                 f"symbol is being sold. State what those orders did (POST /mirror/resolve) and the "
                                 f"flatten takes these too; or sell them by hand.",
                          key=f"flat-blocked:{fid}:{','.join(sorted(blocked))}")
        now = self.clock()
        if not self._rth(now):
            self._say("warn", "flatten queued: the session is shut; the sells go at the next open", key=f"flat-wait:{fid}")
            return "wait"
        # N-08: the flatten is bounded by OPEN-session time, not by a count of rounds: time is only
        # counted between two looks at it inside a session (a night or a weekend adds nothing)
        open_s = self._flatten_clock(fl) if mine else 0.0
        venue = None
        if hasattr(ad, "positions_snapshot"):
            try:
                venue = ad.positions_snapshot().get("stocks") or {}
            except Exception as exc:  # noqa: BLE001
                self._say("red", f"flatten: the account's positions cannot be read ({one_line(exc, 120)}); it is "
                                 f"tried again every {FLATTEN_WAIT_S:.0f} s", key=f"flat-nopos:{fid}:{one_line(exc, 60)}")
                return "wait"
        marks = (self.state.get("marks") or {}).get("prices") or {}
        orders = []
        for sym, total in self.book.positions().items():
            if sym in blocked:
                continue
            asks = {name: s.shares[sym] for name, s in self.book.sleeves.items() if s.shares.get(sym)}
            qty = total
            if venue is not None:
                qty = min(total, max(int(venue.get(sym, 0) or 0), 0))   # never sell more than the account holds
                if qty < total:
                    self._say("red", f"flatten: the book holds {total} {sym}, the account {venue.get(sym, 0)}: "
                                     f"selling {qty}", key=f"flat-short:{fid}:{sym}:{qty}")
                    asks = mc.allocate(qty, asks)
            if qty > 0:
                oid = f"mirror-flat-{fid}-{sym}" if n == 0 else f"mirror-flat-{fid}-r{n + 1}-{sym}"
                orders.append({"id": oid, "side": mc.SELL, "symbol": sym, "qty": qty,
                               "asks": {k: v for k, v in asks.items() if v}, "ref": _num(marks.get(sym)), "applied": False})
        if not orders:
            if any(self.book.positions().get(s) for s in blocked):
                return "wait"                       # the held-back symbols are still to come
            return "done" if self._flatten_finish(ad, False, None) else "wait"
        if open_s >= FLATTEN_OPEN_BUDGET_S:
            return "done" if self._flatten_finish(ad, False, f"GAVE UP after {open_s / 60:.0f} minutes of open "
                                                             f"session and {n} rounds") else "wait"
        last = _parse(fl.get("started_utc")) if mine else None
        if n >= 1 and last is not None:
            due = last + timedelta(seconds=self._flatten_gap(n))
            if now < due:
                fl["next_round_utc"] = _iso(due)
                return "wait"
        self.state["flatten"] = {"id": fid, "round": n + 1, "orders": orders, "recs": {}, "started_utc": _iso(now),
                                 "open_s": open_s, "seen_utc": _iso(now),
                                 "sold": list(fl.get("sold") or []) if mine else []}
        self._save()
        self._journal("flatten", id=fid, round=n + 1,
                      orders=[{k: o[k] for k in ("id", "symbol", "qty", "asks")} for o in orders])
        if n >= 1:
            self._say("red", f"flatten round {n + 1} ({open_s / 60:.1f} of {FLATTEN_OPEN_BUDGET_S / 60:.0f} open-session "
                             f"minutes used): the book and the account still hold "
                             f"{ {o['symbol']: o['qty'] for o in orders} } after round {n}; selling again")
        return "built"

    def _flatten_finish(self, ad, cancelled: bool, note: str | None) -> bool:
        """mark the halt's flatten done - only if it is still what this step saw (a re-kill or a
        resume from an API thread in between is left for the next tick). True when marked. N-02: a
        flatten that ran reads the ACCOUNT before it says anything: "complete" is said only when the
        account holds no stock at all; anything left is named in red, and the halt record carries
        account_flat false (None: the account could not be read) for /status."""
        acct, flat = None, None
        if not cancelled and ad is not None and hasattr(ad, "positions_snapshot"):
            try:
                snap = ad.positions_snapshot()
                acct = {k: v for k, v in (snap.get("stocks") or {}).items() if v}
                if snap.get("other"):              # a fractional share, an option: not a whole lot, still not flat
                    acct["other"] = [one_line(x, 60) for x in list(snap["other"])[:6]]
                flat = not acct
            except Exception as exc:  # noqa: BLE001
                acct = {"?": one_line(exc, 80)}
        with self.halt_lock:
            cur = dict(self._halt or {})
            if not (cur.get("flatten") and not cur.get("flatten_done")) or bool(cur.get("flatten_cancelled")) != cancelled:
                return False
            cur["flatten_done"] = True
            if not cancelled:
                cur["account_flat"] = flat
            self._write_halt(cur)
        fl = self.state.get("flatten") or {}
        sold = list(fl.get("sold") or []) if fl.get("id") == cur.get("flatten_id") else []
        left = self.book.positions()
        self._journal("flatten_done", id=cur.get("flatten_id"), note=note, sold=sold, left=left, account=acct,
                      account_flat=flat, cash=self.book.cash())
        clean = cancelled or (flat is True and not left and not note)
        head = (f"flatten {note}" if cancelled else "flatten complete" if clean else
                "flatten NOT complete" + (f" ({note})" if note else ""))
        self._say("info" if clean else "red",
                  f"{head}: " + (", ".join(sold) or "nothing was sent")
                  + f" | book cash ${self.book.cash():,.2f}"
                  + (f" | the book STILL HELD {left}" if left else "")
                  + ("" if cancelled or flat is True else
                     f" | the ACCOUNT still holds {acct} — the flatten sells only what the book knows: sell these by hand"
                     if flat is False else f" | the ACCOUNT could not be read ({acct}): check it by hand")
                  + ("" if clean or cancelled else " — /kill again re-arms the flatten"),
                  key=f"flat-done:{cur.get('flatten_id')}:{cur.get('flatten_ts')}:{note}")
        return True

    # -------------------------------------------------------------- what the API reads
    def _unresolved(self) -> list:
        out = []
        for o, recs, where in self._open_orders():
            rec = recs.get(o["id"]) or {}
            if rec.get("stuck"):
                out.append({"id": o["id"], "where": where, "symbol": o["symbol"], "side": o["side"], "qty": o["qty"],
                            "why": rec.get("stuck"), "since": rec.get("stuck_since")})
        return out

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
        fl = self.state.get("flatten")
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
            "dividends_open": [r for r in self.state.get("dividends") or [] if r.get("status") == "open"],
            "unresolved": self._unresolved(),
            "save_latched": dict(self._latched) if self._latched else None,
            "settings_clamped": list(self.clamped),
            "flatten": None if not fl else
            {"id": fl.get("id"), "round": fl.get("round"),
             "orders": [{k: o.get(k) for k in ("id", "symbol", "qty", "filled", "price", "applied")}
                        for o in fl.get("orders") or []]},
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
        """for the UNAUTHENTICATED /health: configuration, enumerated states and booleans only - never
        a sentence that can carry the account's positions or cash (A-15; the text is on /status)"""
        try:
            h = self.halt_state()
            run = self._view.get("run")
            return {"mode": "live" if self.cfg.live else "paper", "engines": list(self.cfg.engines),
                    "halted": bool(h.get("halted")), "flatten_pending": bool(h.get("flatten") and not h.get("flatten_done")),
                    "last_session": self._view.get("last_session"), "run_phase": (run or {}).get("phase"),
                    "last_outcome": (self._view.get("last_run") or {}).get("outcome"),
                    "waiting": bool(self._why), "error": bool(self.last_error),
                    "unresolved": bool(self._view.get("unresolved")), "save_latched": bool(self._latched),
                    "brain_ok": bool((self.brain_status.get("session") or {}).get("ok"))}
        except Exception:  # noqa: BLE001
            return {"error": True}


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


def build(settings, alert=None, brain=None, trading_day=None) -> dict:
    """{"live": MirrorManager, "dry": MirrorManager} per the settings (either may be absent). An engine
    is LIVE only when it is named in MIRROR_LIVE_ENGINES AND the service itself trades for real (TWS
    credentials, DRY_RUN off); every other engine runs in the paper book. The timing and band settings
    are clamped to the range the book is built for (MirrorManager, with a log line)."""
    weights = parse_weights(settings.mirror_weights)
    capital = {e: float(settings.mirror_capital_usd) * w for e, w in weights.items()}
    asked = [e.strip() for e in (settings.mirror_live_engines or "").split(",") if e.strip()]
    unknown = [e for e in asked if e not in weights]
    if unknown:
        raise ValueError(f"MIRROR_LIVE_ENGINES names {unknown}, which MIRROR_WEIGHTS does not")
    rule = str(getattr(settings, "mirror_dividend_rule", "composer") or "composer").strip().lower()
    if rule not in mc.DIVIDEND_RULES:
        raise ValueError(f"MIRROR_DIVIDEND_RULE must be one of {mc.DIVIDEND_RULES}, not {rule!r}")
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
                            blend_enabled=bool(settings.blend_enabled), dividend_rule=rule,
                            poll_s=float(getattr(settings, "poll_seconds", 300) or 300),
                            max_book_usd=float(getattr(settings, "mirror_max_book_usd", 0.0) or 0.0), core=core)
    if live:
        out["live"] = MirrorManager(cfg("live", True, live, settings.mirror_state_path), brain=brain, alert=alert,
                                    trading_day=trading_day)
    if paper:
        out["dry"] = MirrorManager(cfg("dry", False, paper, settings.mirror_dry_state_path), brain=brain, alert=alert,
                                   trading_day=trading_day)
    for book in out.values():
        if book.clamped:
            book._say("warn", "settings outside their range were clamped: " + "; ".join(book.clamped))
    if "live" not in out:
        _abandoned_live_state(settings, alert, asked, real)
    return out


def _abandoned_live_state(settings, alert, asked: list, real: bool) -> None:
    """D-03: no live book is built (MIRROR_LIVE_ENGINES names nothing, or the service is not trading
    for real) while the LIVE state file still holds shares: nobody trades them, nobody checks them
    and /kill has no book to flatten. Said in red at every boot, naming the holdings. Never raises."""
    path = getattr(settings, "mirror_state_path", None)
    if not path or not os.path.exists(path):
        return
    try:
        with open(path) as f:
            raw = json.load(f)
        if not isinstance(raw, dict) or not raw.get("live"):
            return
        book = mc.Book.from_dict(raw["book"])
        held, cash = book.positions(), book.cash()
        if not held:
            return
        what = f"holds {held} and ${cash:,.2f} in cash (last saved {raw.get('saved_utc')})"
    except Exception as exc:  # noqa: BLE001
        what = f"cannot be read ({one_line(exc, 160)}) and may hold positions"
    why = ("MIRROR_LIVE_ENGINES names no engine" if not asked else
           "the service is not trading for real (DRY_RUN, or no TWS credentials)" if not real else
           "no live engine is configured")
    text = (f"🚨 mirror: NO LIVE BOOK is built ({why}) but the live book's state file {path} {what}. These are "
            f"REAL positions in the account that nothing trades, nothing checks and /kill will NOT sell. Restore "
            f"MIRROR_LIVE_ENGINES / DRY_RUN=false to manage them, or sell them by hand.")
    logger.error(text)
    try:
        (alert or (lambda msg: None))(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mirror alert failed: %s", exc)
