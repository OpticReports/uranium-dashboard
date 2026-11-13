#!/usr/bin/env python3
"""Scale the IBKR mirror's live book to a new size at Composer's split: a read-only PLANNER
(composer/IBKR_MIRROR.md "Scaling the live book"; CLAUDE.md "ONE BRAIN, TWO BROKERS").

It sends nothing to the executor and holds no exec token. It reads Composer's split from the daily
monitor's snapshot and the live book from the executor's read-only feed (GET
{MIRROR_EXECUTOR_URL}/mirror/feed, header X-Read-Token = MIRROR_READ_TOKEN, through
mirror_parity.fetch_feed: https only, a redirect never followed), and prints the owner's steps: the
cap to set on the executor, then ONE line to paste into the executor's own Shell on Render. That line
is plain python3 and the standard library only; it reads EXEC_TOKEN inside the container and sends
it to the executor in that same container ONLY - http://127.0.0.1:$PORT/mirror/credit, no proxy, no
redirect followed - one cash credit per sleeve. The token never leaves the container.

  mirror_scale.py --to 50000 [--snapshot composer/results/monitor/last-snapshot.json] [--book live]
                  [--headroom 0.05] [--json]

1 Composer's split: the four engines' "value" in the snapshot, by symphony id; weight = value / the
  four's sum (unallocated cash and anything else left out). Refused unless all four are positive
  numbers summing to a finite one; a snapshot more than 3 calendar days old (ET) is warned about.
2 The mirror: the one book whose mode is "live" (--book names it). Refused unless it is not halted
  (no flatten pending), has no open run, no unresolved order, no last_error, no failed save, nothing
  queued (pending_requests), holds the four sleeves and no other, none frozen, each valued - and the
  account's post-trade check of its LAST session was made, is done and found no problem (mirror.py
  _post_check). The executor clears that check at the end of every run (_finish) and on
  /mirror/adjust (_adjust): a missing or stale one says to re-run after the next session's check.
  Re-run it after ANY /mirror/adjust and paste only the new line: an adjust on the evening of the
  book's last session is followed by that evening's tick making that session's check again (clean
  when the shares are as booked: it compares shares, not cash), so an older line would still send.
3 The plan: target = round(to x weight, 2); credit = round(target - the sleeve's equity, 2), the
  equity at the book's marks of its last decision. Refused when --to is not above the book's equity,
  is more than 10x it (a slipped zero), or any credit is negative (the line names the smallest --to
  at which none is, or says it is beyond 10x the book).
4 The session: the credits are applied at the first NYSE session after the book's last one that the
  line can still be pasted for. The planner computes, in UTC, the windows in which the line may be
  pasted until then: every hour but a weekday's from 15:00 ET (12:00 on a half-day) to midnight, up to
  that session's own cutoff - so the line itself needs no time zone, and expires with its session.
  Refused on a session day from its paste cutoff while that day's session has not run yet (the
  book's last session is before today): a line printed then would be for the NEXT session, and the
  session of today, run in between, would make it refuse; re-run after it and its post-trade check
  (if the executor missed today's session, re-run after midnight ET).
5 The cap: the executor refuses a credit that takes a live book's funded_usd (its seeds plus every
  positive credit and what /mirror/adjust added) above MIRROR_MAX_BOOK_USD + $1, credit by credit,
  smallest first, and drops it (ibkr-executor/app/mirror.py _over_cap, _apply_credits). The feed does
  not publish funded_usd (mirror.py _publish): it is estimated as the seeds the feed lists plus the
  operator credits in its session rows. Cap to set = (funded + the credits) x (1 + headroom), rounded
  up to the next $500. The pasted line checks the executor's OWN funded_usd against the cap it was
  deployed with, in cents and with no $1 slack, before it sends anything. That deploy changes
  MIRROR_MAX_BOOK_USD only, not MIRROR_LIVE_ENGINES: a sleeve it dropped stays in the book's state,
  not frozen, until the executor's first tick with the gateway logged in (mirror.py
  _reconcile_sleeves), so a line pasted before then would queue the others and stop at that one.
6 The cash: at the decision the executor credits the open dividend receivables that are due, then
  takes each credit only if the account's cash (IBKR's TotalCashValue) covers the book's cash plus it
  (within CASH_TOL_USD, $1), smallest first (mirror.py _dividends, _apply_credits). The plan prints the
  account's minimum: the book's cash + the dividends due by that session + the credits + a margin of
  max($100, 0.5% of the credits). Short by even $1 of the first three, the LARGEST credit is refused.

The pasted line sends NOTHING (one line starting "NOTHING SENT", exit 1) when EXEC_TOKEN is not there or
is not printable ASCII (it is never printed), the book's state is not there, PORT is not a port, it is
pasted outside its windows (a weekday from 15:00 ET, 12:00 on a half-day; after the cutoff of the
session it was planned for), the book has run a session since the plan, any request is queued (the
inbox, read first, or the state's requests, whatever its kind), the book is halted or a flatten is
pending (<state>.halt), a run is open, the post-trade check of the plan's last session is not done and
clean (an applied /mirror/adjust clears it), a sleeve it credits is frozen or no longer in the book,
MIRROR_MAX_BOOK_USD is not a number above 0, or it does not cover the book's funded_usd plus the
credits. Then one POST per credit, each answer printed; at the first error or answer that is not 200 it
stops ("STOPPED: <sleeve> <reason>", exit 2), names what answered 200 (queued: applied at the next
session, not to be withdrawn) and says whether the one that failed was NOT queued (an HTTP 4xx: the
executor's /mirror/credit refuses before it queues; connection refused: nothing listened) or may have
been (any other failure). Nothing queued at all: fix the cause and paste the line again; otherwise,
after that session, re-run this planner and paste its new line. All of it answered 200: exit 0. An
error is printed as its type and its message with EXEC_TOKEN masked, never as its repr.

Exit 0 with a plan (human text, or --json); 1 with one line starting "MIRROR SCALE REFUSED" - also for a
feed whose dollar figures are not finite or beyond MAX_USD ($1e9: a malformed feed, never planned on).
Env: MIRROR_EXECUTOR_URL (https), MIRROR_READ_TOKEN. Nothing is written anywhere.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import mirror_parity as mp  # noqa: E402  (fetch_feed: the one reader of the executor's feed)
import shadow_runner as sr  # noqa: E402  (et_now; HALF_DAYS; NYSE_HOLIDAYS)

# engine -> Composer symphony id, in the book's order (= composer/fixtures/approved/manifest.json: a gate pins it)
ENGINES = (("HG", "mbkiXcuNDjueXpiox5Av"), ("KMLM", "YPTSJFJwD2ZKfAeYJUbW"),
           ("SLEEVE", "nNdBk7hc5NiBzeRvbI5T"), ("HARV", "ORQNCfZnA18wmsMWVhf8"))
SNAPSHOT = os.path.join(HERE, "..", "results", "monitor", "last-snapshot.json")   # monitor.py writes it daily
STALE_DAYS = 3                   # a snapshot (or the book's marks) older than this many ET calendar days: warned
HEADROOM = 0.05
CAP_STEP_USD = 500               # the cap is rounded UP to a multiple of this
MAX_FACTOR = 10.0                # --to above this many times the book's equity: refused (a slipped zero)
SEED_TOL_USD = 1.0               # ibkr-executor/app/mirror.py SEED_TOL_USD: _over_cap allows the cap plus this
CASH_TOL_USD = 1.0               # ibkr-executor/app/mirror.py CASH_TOL_USD: _apply_credits allows the account this short
CASH_MARGIN_USD, CASH_MARGIN_FRAC = 100.0, 0.005   # the account's minimum: + max($100, 0.5% of the credits)
HISTORY = 120                    # session rows asked of the feed: its most (service.py; mirror.py HISTORY_KEEP)
EQUITY_TOL_USD = 0.05            # the book's equity vs the four sleeves' (each published rounded to cents)
MAX_USD = 1e9                    # a feed dollar figure (or --to) beyond this, or not finite: malformed, refused
# ibkr-executor/app/mirror_core.py receivable_pay_date: a receivable is due from its pay date; one whose pay
# date never became known is taken to pay ex + DEFAULT_PAY_LAG_DAYS once PAY_DATE_GIVE_UP_DAYS have passed
DEFAULT_PAY_LAG_DAYS, PAY_DATE_GIVE_UP_DAYS = 7, 10
# the pasted line: plain python3 (ibkr-executor/Dockerfile apt-installs it; the standard library only), posting
# to the executor in its own container. ibkr-executor/start.sh: uvicorn --host 0.0.0.0 --port "${PORT:-8000}"
# (Dockerfile: ENV PORT=8000; Render sets PORT): the line reads PORT the same way. A relative
# MIRROR_STATE_PATH is the executor's, from its working directory (Dockerfile WORKDIR, start.sh cd)
LINE_PY = "python3"
LINE_HOST = "127.0.0.1"
PORT_DEFAULT = "8000"
EXEC_DIR = "/opt/executor"
PASTE_CUTOFF, PASTE_CUTOFF_HALF = 15, 12   # ET hour from which a weekday paste is refused (a half-day: 13:00 close)
# a book -> (the env var naming its state file, the default): ibkr-executor/app/config.py; render.yaml sets
# MIRROR_STATE_PATH=/app/data/mirror_state.json. Its inbox is <state>.inbox.json, its halt file <state>.halt
# (mirror.py _inbox_path, _halt_path)
STATE_ENV = {"live": ("MIRROR_STATE_PATH", "./data/mirror_state.json")}
DEPLOY_QUIET = ("15:15", "16:05")          # no deploy then: the 15:15 attestation, the 15:54 decision, its orders
DEPLOY_QUIET_HALF = ("12:15", "13:05")     # ... on a 13:00 half-day
TTY_LINE_MAX = 4095                        # a canonical-mode terminal line (N_TTY_BUF_SIZE 4096, its newline)


def one_line(e, n=200):
    return " ".join(str(e).split())[:n]


def usd(x):
    return f"${x:,.2f}"


def num(x):
    """a finite number, or None (bools are not numbers here; nor is an integer too large for a float)"""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    try:
        return float(x) if math.isfinite(x) else None
    except OverflowError:
        return None


def plausible(x):
    """a number of dollars this planner can plan on: finite and within MAX_USD either way (bools are not)"""
    v = num(x)
    return v is not None and abs(v) <= MAX_USD


class Refused(Exception):
    """why there is no plan (exit 1)"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):                      # a bad command line is a refusal (exit 1), said on the one line
        raise Refused(f"bad arguments: {message}")


def parse(argv):
    p = _Parser(prog="mirror_scale.py", description="Plan scaling the IBKR mirror's live book at Composer's split "
                                                     "(read-only: it sends nothing).")
    p.add_argument("--to", type=float, required=True, help="the book's size after the credits, in dollars")
    p.add_argument("--snapshot", default=None, help="the monitor's snapshot (default: results/monitor/last-snapshot.json)")
    p.add_argument("--book", default=None, help="the executor's book; default: the one book whose mode is live")
    p.add_argument("--headroom", type=float, default=HEADROOM,
                   help="the cap's margin over what the credits need (default 0.05 = 5%%)")
    p.add_argument("--json", action="store_true", help="the plan as JSON")
    return p.parse_args(argv)


# ------------------------------------------------------------------ Composer's split
def parse_ts(text):
    """an ISO timestamp as an aware datetime (naive: UTC), or None"""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        t = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def et_date(t):
    """the US/Eastern date of an aware datetime, or None when it cannot be converted (out of range)"""
    try:
        return sr.et_now(t).date()
    except (OverflowError, ValueError):
        return None


def composer_split(path, now):
    """{"path", "taken_at", "date" (ET), "age_days", "values", "weights", "warnings"} from the monitor's
    snapshot, or raises Refused"""
    shown = rel(path)
    try:
        with open(path) as f:
            snap = json.load(f)
    except FileNotFoundError:
        raise Refused(f"Composer's snapshot {shown} is not there (the daily monitor writes it)") from None
    except Exception as e:  # noqa: BLE001
        raise Refused(f"Composer's snapshot {shown} cannot be read ({one_line(e, 120)})") from None
    if not isinstance(snap, dict) or not isinstance(snap.get("symphonies"), dict):
        raise Refused(f"{shown} is not a monitor snapshot (no \"symphonies\")")
    taken = parse_ts(snap.get("taken_at"))
    day = et_date(taken) if taken is not None else None
    if day is None:
        raise Refused(f"{shown} has no readable taken_at ({one_line(repr(snap.get('taken_at')), 60)}): the date of "
                      f"Composer's split cannot be told")
    values, bad = {}, []
    for eng, sid in ENGINES:
        row = snap["symphonies"].get(sid)
        v = num(row.get("value")) if isinstance(row, dict) else None
        if v is None or v <= 0:
            bad.append(f"{eng} ({sid}): " + ("missing" if not isinstance(row, dict) else
                                             f"value {one_line(repr(row.get('value')), 40)}"))
        else:
            values[eng] = v
    if bad:
        raise Refused(f"Composer's split cannot be read from {shown}: " + "; ".join(bad)
                      + " (each of the four engines needs a positive value)")
    total = sum(values.values())
    weights = {e: values[e] / total for e in values} if math.isfinite(total) and total > 0 else {}
    if not weights or not all(math.isfinite(w) and w > 0 for w in weights.values()):
        raise Refused(f"Composer's four values in {shown} do not sum to a finite positive number with every engine a "
                      f"share of it ({one_line(repr(total), 40)}): the split cannot be computed")
    age = (sr.et_now(now).date() - day).days
    warnings = []
    if age > STALE_DAYS:
        warnings.append(f"Composer's snapshot is {age} days old (taken {day.isoformat()}, {snap['taken_at']}): the split "
                        f"has moved since; run the monitor, or pass a newer --snapshot")
    elif age < 0:
        warnings.append(f"Composer's snapshot is dated in the future ({snap['taken_at']}): check the file and the clock")
    return {"path": shown, "taken_at": snap["taken_at"], "date": day.isoformat(), "age_days": age,
            "values": values, "weights": weights, "warnings": warnings}


def rel(path):
    a = os.path.abspath(path)
    return os.path.relpath(a, REPO) if a.startswith(REPO + os.sep) else path


# ------------------------------------------------------------------ the mirror
def pick_book(feed, name):
    """(name, view) of the book to scale, or raises Refused. No name: the ONE book whose mode is live;
    a paper book is never scaled here"""
    books = {k: v for k, v in (feed.get("books") or {}).items() if isinstance(v, dict)}
    have = ", ".join(f"{k} ({books[k].get('mode')})" for k in sorted(books)) or "none"
    if name is not None:
        if name not in books:
            raise Refused(f"the executor has no book {name!r} (it has: {have})")
        live = [name]
    else:
        live = sorted(k for k, v in books.items() if v.get("mode") == "live")
        if len(live) != 1:
            raise Refused(("the executor has no live book" if not live else f"the executor has {len(live)} live books")
                          + f" (books: {have})" + ("; name one with --book" if live else ""))
    view = books[live[0]]
    if "book" not in view and view.get("error"):
        raise Refused(f"the executor could not build book {live[0]}'s view: {one_line(view['error'], 160)}")
    if view.get("mode") != "live":
        raise Refused(f"book {live[0]!r} is {view.get('mode')!r}, not live: this planner scales the live book only")
    if live[0] not in STATE_ENV or not re.fullmatch(r"[A-Za-z0-9_-]+", live[0]):
        raise Refused(f"book {live[0]!r} is not one whose state file the pasted line knows ({', '.join(STATE_ENV)})")
    return live[0], view


RECHECK = ("re-run this planner after the next session's post-trade check (the executor clears the check at the end "
           "of every run and on /mirror/adjust, and makes it again after the session)")


def check_problem(view):
    """why the account's post-trade check does not clear this book for a scale-up, or None: it must be a
    record of the book's LAST session, done, with no problem (mirror.py _post_check writes
    {"session", "utc", "strikes", "problems", "done"}; _finish and _adjust reset it to None)"""
    chk, last = view.get("check"), view.get("last_session")
    if not isinstance(chk, dict):
        return (f"the account has not been checked against the book since its last session {last} (the post-trade "
                f"check is {'not on the feed' if chk is None else 'not a record: ' + one_line(repr(chk), 60)}): {RECHECK}")
    probs = chk.get("problems")
    if probs:
        probs = probs if isinstance(probs, list) else [probs]
        return (f"the account does not hold the book (check of {chk.get('session')}): "
                + "; ".join(one_line(p, 80) for p in probs[:3]) + f" - {RECHECK}")
    if chk.get("session") != last:
        return (f"the last post-trade check is of {chk.get('session')}, not of the book's last session {last}: "
                f"{RECHECK}")
    if chk.get("done") is not True:
        return f"the post-trade check of {chk.get('session')} is not done (done {chk.get('done')!r}): {RECHECK}"
    return None


def health_problems(view):
    """why this book must not be scaled now: [] when it may"""
    out = []
    halt = view.get("halt") if isinstance(view.get("halt"), dict) else {}
    if halt.get("halted"):
        out.append(f"it is HALTED ({one_line(halt.get('reason') or 'no reason recorded', 120)}; by "
                   f"{halt.get('by') or '?'} at {halt.get('ts') or '?'})")
    if halt.get("flatten") and not halt.get("flatten_done") and not halt.get("flatten_cancelled"):
        out.append("a flatten is in progress")
    run = view.get("run")
    if run:
        run = run if isinstance(run, dict) else {}
        out.append(f"a run is open (session {run.get('session')}, phase {run.get('phase')})")
    unresolved = view.get("unresolved")
    if unresolved:
        ids = [str(u.get("id")) for u in unresolved if isinstance(u, dict)] if isinstance(unresolved, list) else []
        out.append(f"{len(unresolved) if isinstance(unresolved, list) else 'some'} order(s) unresolved"
                   + (f" ({', '.join(ids[:4])})" if ids else "") + ": POST /mirror/resolve first")
    if view.get("last_error"):
        out.append(f"its last tick failed: {one_line(view['last_error'], 160)}")
    pend = view.get("pending_requests")
    if pend:
        rows = [r for r in pend if isinstance(r, dict)] if isinstance(pend, list) else []
        what = []
        for r in rows:
            who = (f"{r.get('from')} -> {r.get('to')}" if r.get("kind") == "transfer"
                   else str(r.get("sleeve") or r.get("order") or ""))
            amt = f" {usd(num(r.get('amount')))}" if num(r.get("amount")) is not None else ""
            what.append(f"{r.get('kind')} {who}{amt} ({r.get('id') or '?'})")
        out.append(f"{len(rows) or 'some'} request(s) queued and not yet applied"
                   + (": " + "; ".join(what[:6]) if what else "")
                   + " - a scale-up waits until a session has applied them")
    if view.get("save_latched"):
        out.append(f"a state save failed and the book is latched ({one_line(view['save_latched'], 120)})")
    if view.get("archived_state"):
        out.append(f"its state file was archived: {one_line(view['archived_state'], 160)}")
    chk = check_problem(view)
    if chk:
        out.append(chk)
    return out


def sleeve_equities(view):
    """({engine: equity}, the book's equity), or raises Refused: the four sleeves there, no other, none
    frozen, each valued; the book's equity their sum (within the cents each is rounded to)"""
    book = view.get("book") if isinstance(view.get("book"), dict) else {}
    sleeves = book.get("sleeves") if isinstance(book.get("sleeves"), dict) else {}
    names = [e for e, _ in ENGINES]
    missing = [e for e in names if not isinstance(sleeves.get(e), dict)]
    if missing:
        raise Refused(f"the book has no sleeve {', '.join(missing)} (it holds: {', '.join(sorted(sleeves)) or 'none'}): "
                      f"all four engines must be live in it")
    extra = sorted(set(sleeves) - set(names))
    if extra:
        raise Refused(f"the book also holds {', '.join(extra)}: a scale-up at Composer's split covers "
                      f"{', '.join(names)} only")
    frozen = [e for e in names if sleeves[e].get("frozen")]
    if frozen:
        raise Refused(f"the sleeve {', '.join(frozen)} is frozen on the executor")
    eq = {}
    for e in names:
        v = num(sleeves[e].get("equity"))
        if v is None or v <= 0:
            raise Refused(f"the sleeve {e} has no usable equity on the feed ({one_line(repr(sleeves[e].get('equity')), 40)}): "
                          f"a price is missing from the book's marks")
        eq[e] = v
    total = num(book.get("equity"))
    if total is None or total <= 0:
        raise Refused(f"the book has no usable equity on the feed ({one_line(repr(book.get('equity')), 40)})")
    if abs(sum(eq.values()) - total) > EQUITY_TOL_USD:
        raise Refused(f"the book's equity {usd(total)} is not its four sleeves' {usd(sum(eq.values()))}: the feed does "
                      f"not add up")
    return eq, total


def funded_estimate(view):
    """(funded_usd now, how it was found, warnings), or raises Refused. funded_usd is what the executor's
    cap counts (mirror.py _over_cap): the seeds, plus every positive operator credit (_apply_credits),
    plus what /mirror/adjust added. Taken from the feed when it publishes it; otherwise the seeds the
    feed lists plus the operator credits in its session rows (dividends are not counted: the cap does
    not count them either). A row whose "credits" is not a list, an entry that is not a record and an
    amount that is not a number are skipped; an operator credit whose amount is a number but not a
    plausible one (not finite, or beyond MAX_USD), like such a seed or funded_usd, is refused, and so is
    an estimate beyond MAX_USD"""
    pub = view.get("funded_usd")
    if pub is not None:
        v = num(pub)
        if v is None or v < 0 or not plausible(v):
            raise Refused(f"the feed's funded_usd is not a number of dollars from 0 to {usd(MAX_USD)} "
                          f"({one_line(repr(pub), 40)})")
        return round(v, 2), "the executor's funded_usd, published on the feed", []
    seeded = view.get("seeded")
    if not isinstance(seeded, dict) or not seeded:
        raise Refused("the feed lists no seeds for the book: the capital its cap counts cannot be estimated")
    seeds = 0.0
    for name, row in seeded.items():
        a = num(row.get("amount")) if isinstance(row, dict) else None
        if a is None or a < 0 or not plausible(a):
            raise Refused(f"the feed's seed of {name} is not an amount from 0 to {usd(MAX_USD)} "
                          f"({one_line(repr(row), 80)})")
        seeds += a
    history = view.get("history") if isinstance(view.get("history"), list) else []
    rows = [r for r in history + [view.get("last_run")] if isinstance(r, dict)]
    taken = {}
    for r in rows:
        cs = r.get("credits")
        if not isinstance(cs, list):
            continue
        for c in cs:
            if not isinstance(c, dict) or c.get("kind") != "credit":
                continue
            raw = c.get("amount")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and not plausible(raw):
                raise Refused(f"an operator credit in the feed's session row of {one_line(r.get('session'), 20)} is not "
                              f"a plausible amount ({one_line(repr(raw), 40)}): the capital the cap counts cannot be "
                              f"estimated")
            a = num(raw)
            if a is None or a <= 0:
                continue
            cid = c.get("id")
            key = ("id", cid) if isinstance(cid, str) and cid else ("row", str(r.get("session")), str(c.get("sleeve")), a)
            taken[key] = a
    credits = sum(taken.values())
    sessions = sorted({r.get("session") for r in rows if isinstance(r.get("session"), str)})
    span = f"{sessions[0]}..{sessions[-1]}" if sessions else "none"
    how = (f"not published on the feed; estimated: the seeds {usd(seeds)} + the operator credits in the feed's "
           f"{len(sessions)} session row(s) ({span}) {usd(credits)}. Not visible on the feed: cash or shares added by "
           f"/mirror/adjust, and a sleeve seeded twice")
    warnings = []
    if len(history) >= HISTORY:
        warnings.append(f"the feed's history is full ({len(history)} rows from {sessions[0] if sessions else '?'}): an "
                        f"operator credit older than that is not in the cap estimate; the pasted line checks the "
                        f"executor's own total before it sends")
    if not plausible(seeds + credits):
        raise Refused(f"the feed's seeds and operator credits total {one_line(repr(seeds + credits), 40)}: not a "
                      f"plausible amount (more than {usd(MAX_USD)}, or not finite)")
    return round(seeds + credits, 2), how, warnings


# ------------------------------------------------------------------ the session and the cash
def trading_day(d):
    return d.weekday() < 5 and d.isoformat() not in sr.NYSE_HOLIDAYS


def paste_cutoff(day_iso):
    """the ET hour from which a paste on that weekday is refused: 15, 12 on a half-day"""
    return PASTE_CUTOFF_HALF if day_iso in sr.HALF_DAYS else PASTE_CUTOFF


def credit_session(last_session, now):
    """the session the credits are applied at when the line is pasted at the earliest it may be: the
    first NYSE session after the book's last one that is today (ET) - when it is still before today's
    paste cutoff - or later (weekdays less shadow_runner.NYSE_HOLIDAYS)"""
    et = sr.et_now(now)
    first = et.date()
    if trading_day(first) and et.hour >= paste_cutoff(first.isoformat()):
        first += datetime.timedelta(days=1)
    try:
        after = datetime.date.fromisoformat(last_session) + datetime.timedelta(days=1)
    except (TypeError, ValueError):
        after = first
    d = max(first, after)
    while not trading_day(d):
        d += datetime.timedelta(days=1)
    return d.isoformat()


def session_still_to_run(last_session, now):
    """today (ET) when it is a session day, at or past its paste cutoff (15:00 ET, 12:00 on a half-day),
    whose session has not run yet (the book's last session is before it); else None. A plan then is for
    the NEXT session (credit_session), and its line can never send: blocked until midnight, then refused
    because today's session ran after the plan (the line's last-session check)"""
    et = sr.et_now(now)
    today = et.date().isoformat()
    if trading_day(et.date()) and et.hour >= paste_cutoff(today) and isinstance(last_session, str) \
            and last_session < today:
        return today
    return None


def _date(text):
    try:
        return datetime.date.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None


def dividends_due(view, session):
    """(total, [rows due], warnings): the open dividend receivables (the feed's dividends_open) the executor
    credits to the sleeves at `session` BEFORE it takes the credits (mirror.py _plan: _dividends, then
    _apply_credits): those due on or before it - from the pay date, or, when the pay date never became
    known, ex + DEFAULT_PAY_LAG_DAYS once PAY_DATE_GIVE_UP_DAYS have passed since the ex-date
    (mirror_core.receivable_pay_date). Every one is counted: whether its sleeve still holds the payer, and
    whether the account received it, the cash minimum does not guess"""
    rows = view.get("dividends_open")
    if rows is None:
        return 0.0, [], []
    if not isinstance(rows, list):
        return 0.0, [], [f"the feed's dividends_open is not a list ({one_line(repr(rows), 60)}): the cash minimum "
                         f"does not count the dividends due"]
    day = _date(session)
    due, warn = [], []
    for r in rows:
        total = num(r.get("total")) if isinstance(r, dict) else None
        ex = _date(r.get("ex_date")) if isinstance(r, dict) else None
        if total is None or total <= 0 or ex is None:
            warn.append(f"a dividend receivable on the feed cannot be read ({one_line(repr(r), 80)}): it is not in "
                        f"the cash minimum")
            continue
        pay = _date(r.get("pay_date"))
        if pay is None and (day - ex).days >= PAY_DATE_GIVE_UP_DAYS:
            pay = ex + datetime.timedelta(days=DEFAULT_PAY_LAG_DAYS)
        if pay is not None and pay <= day:
            due.append({"id": r.get("id"), "sleeve": r.get("sleeve"), "ticker": r.get("ticker"),
                        "total": round(total, 2), "due": pay.isoformat()})
    return round(sum(r["total"] for r in due), 2), due, warn


# ------------------------------------------------------------------ the plan
def credits_at(to, weights, equities):
    """{engine: (target, credit)}: target = round(to x weight, 2), credit = round(target - equity, 2)"""
    out = {}
    for e, _ in ENGINES:
        target = round(to * weights[e], 2)
        out[e] = (target, round(target - equities[e], 2))
    return out


def _first_cent(eq, w):
    """the smallest whole-cent --to, in cents, at which round(to x w, 2) >= eq (round is monotone in to),
    or None"""
    try:
        c = math.floor((eq - 0.005) / w * 100)
    except (ZeroDivisionError, OverflowError, ValueError):
        return None
    for _ in range(1000):                          # down while it already holds ...
        if round(c / 100 * w, 2) < eq:
            break
        c -= 1
    else:
        return None
    for _ in range(1000):                          # ... then up to the first cent where it does
        c += 1
        if round(c / 100 * w, 2) >= eq:
            return c
    return None


def smallest_to(weights, equities, book_equity):
    """the smallest --to, in cents, at which every credit is >= 0 and the book grows, or None when that is
    beyond MAX_FACTOR x the book's equity (no --to this planner takes would do). Per engine the first cent
    at which round(to x weight, 2) reaches its equity; the answer is the largest of those and the first
    cent above the book"""
    limit = MAX_FACTOR * book_equity
    cents = [_first_cent(equities[e], weights[e]) for e, _ in ENGINES]
    if any(c is None for c in cents):
        return None
    above = int(round(book_equity * 100))
    if above / 100 <= book_equity:
        above += 1
    best = max(cents + [above])
    for _ in range(100):                           # float rounding: confirm on the planner's own arithmetic
        to = best / 100
        if to > limit:
            return None
        if to > book_equity and all(c >= 0 for _, c in credits_at(to, weights, equities).values()):
            return to
        best += 1
    return None


def cap_to_set(need, headroom):
    """need x (1 + headroom), rounded UP to the next multiple of CAP_STEP_USD (in whole cents: exact); raises
    Refused when that is not a finite number (build bounds the need first)"""
    x = need * (1.0 + headroom) * 100
    if not math.isfinite(x):
        raise Refused(f"the cap cannot be computed from a need of {one_line(repr(need), 40)}: the feed is malformed")
    cents = int(round(x))
    step = CAP_STEP_USD * 100
    return ((cents + step - 1) // step) * CAP_STEP_USD


def feed_url_ok(base):
    """mirror_parity.fetch_feed's rule, said before anything is fetched: the READ token goes over https
    only (plain http to this machine only)"""
    u = urllib.parse.urlparse(base)
    if u.scheme != "https" and not (u.scheme == "http" and (u.hostname or "") in mp.LOCAL):
        raise Refused("MIRROR_EXECUTOR_URL must be https (the read token is never sent over plain http)")


def _py(x):
    """a Python literal of a str, a number or a tuple of them, strings in double quotes"""
    if isinstance(x, str):
        return json.dumps(x, ensure_ascii=True)
    if isinstance(x, tuple):
        return "(" + ",".join(_py(v) for v in x) + ("," if len(x) == 1 else "") + ")"
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return repr(x)
    raise TypeError(f"no literal for {x!r}")


# The pasted line's program. It runs in the executor's container under plain python3 and reads the executor's own
# files and env; nothing here is filled in but the first line's constants (G is the whole "re-run mirror_scale.py
# --to ..." phrase). The state file's book is mirror_core.Book.to_dict(): its "sleeves" a LIST of sleeve records,
# each with its "name". Every check comes before the first POST; the POSTs go to the executor in the same container
# only. The inbox is read BEFORE the state: _drain_inbox saves a request into the state before it takes it out of
# the inbox (mirror.py), so a drain between the two reads cannot hide it. The halt file, the open run, the
# post-trade check and the frozen sleeves are the planner's own preconditions (health_problems, check_problem,
# sleeve_equities), re-read here because an operator or the executor can change them between the plan and the paste.
# X() prints an error as its type and message with EXEC_TOKEN masked (never its repr: http.client's would carry the
# header value). A failed POST is "NOT queued" only where that is proven: an HTTP 4xx (/mirror/credit raises every
# one before request_credit queues: service.py _mirror_off_404, _auth, _mirror_book, request_credit's ValueError;
# _mirror_body's 422) or a refused connection (nothing listened); any other failure may have queued it. Kept under a
# terminal line (TTY_LINE_MAX): a gate in test_mirror_scale pins the longest line of a 45-day sweep of plan times.
LINE_PROGRAM = r'''W=[];L=W.append;ok=[];T=E.get("EXEC_TOKEN")or""
def X(e):s=str(e);return"%s(%r)"%(type(e).__name__,T and s.replace(T,"***")or s)
def R(f,z):
 try:return json.load(open(f))
 except FileNotFoundError:return z
 except Exception as e:L("%s unreadable (%s)"%(f,X(e)));return False
try:
 O=E.get("PORT")or"8000";t=(time.time()-K)/3600;c=(E.get("MIRROR_MAX_BOOK_USD")or"").strip()
 if not T:L("EXEC_TOKEN is not set: paste this in the Shell of ibkr-executor")
 elif not(T.isascii()and T.isprintable()):L("EXEC_TOKEN is not printable ASCII")
 if not(O.isdigit()and 0<int(O)<65536):L("PORT %r is not a port"%O)
 if t>=Z[-1][1]:L("this line was for the session of %s (paste by %s): "%(V,Y)+G)
 elif not any(a<=t<b for a,b in Z):L("it is a weekday from 15:00 ET (12:00 on a half-day): paste on a morning or a weekend")
 P=os.path.join("/opt/executor",E.get("MIRROR_STATE_PATH")or"./data/mirror_state.json");I=R(P+".inbox.json",[]);S=R(P,None);H=R(P+".halt",{})
 if S is not False and not(type(S)==dict and S.get("name")==B and S.get("live")):L(P+(" is not there"if S is None else" is not the live book"));S=0
 if type(H)!=dict or H.get("halted")or H.get("flatten")and not(H.get("flatten_done")or H.get("flatten_cancelled")):L("the book is halted or flattening: "+G+" after it resumes")
 if S:
  g=S.get;q=g("requests")or[];Q=(I if type(I)==list else[]if I is False else[I])+(q if type(q)==list else[q]);k=g("check")or{};f=g("funded_usd")
  if g("last_session")!=M:L("the book ran a session (%s) after the plan: "%g("last_session")+G)
  if Q:L("%d request(s) queued, not yet applied: %s"%(len(Q),"; ".join("%s %s %s"%(r.get("kind"),r.get("sleeve")or r.get("order")or r.get("from"),r.get("id"))if type(r)==dict else repr(r)[:60]for r in Q[:8])))
  if g("run"):L("a run is open: "+G+" after it")
  if not(k.get("session")==M and k.get("done")is True and not k.get("problems")):L("no clean post-trade check of %s: "%M+G+" after the next session")
  x=[s for s,a in A if s in(g("frozen")or[])or s not in[v["name"]for v in g("book")["sleeves"]]]
  if x:L(", ".join(x)+" frozen or not in the book: "+G)
 try:C=float(c)
 except ValueError:C=0
 if not 0<C<1e999:L("MIRROR_MAX_BOOK_USD %r is not above 0: set it (step a), deploy first"%c)
 elif S:
  if type(f)not in(int,float)or not 0<=f<1e999:L("the book state has no funded_usd (%r)"%(f,))
  elif round(f*100)+D>round(C*100):L("MIRROR_MAX_BOOK_USD %.2f is below funded_usd %.2f + these credits %.2f = %.2f: the largest would be DROPPED; set the cap (step a), deploy first"%(C,f,D/100,f+D/100))
except Exception as e:L("the checks failed (%s)"%X(e))
if W:print("NOTHING SENT: "+"; ".join(W));sys.exit(1)
for i,(s,a)in enumerate(A):
 w=u=0
 try:
  h=hc.HTTPConnection("127.0.0.1",int(O),timeout=30);h.request("POST","/mirror/credit",json.dumps({"sleeve":s,"amount":a,"note":N,"book":B}),{"Content-Type":"application/json","X-Exec-Token":T});y=h.getresponse();c=y.status;print(s,a,c,y.read().decode("utf-8","replace")[:300])
  if c!=200:w="answered HTTP %s"%c;u=399<c<500
 except ConnectionRefusedError as e:w,u="got no answer (%s)"%X(e),1
 except BaseException as e:w="got no answer (%s)"%X(e)
 if w:print("STOPPED: %s %s. Queued: %s. %s %s; not sent: %s. "%(s,w,", ".join(ok)or"none",s,"was NOT queued"if u else"may have been queued anyway",", ".join(z for z,_ in A[i+1:])or"none")+("Nothing is queued: fix the cause and paste this line again"if u and not ok else"What is queued applies at the next session and cannot be withdrawn: after it, "+G));sys.exit(2)
 ok.append("%s %.2f"%(s,a))
print("ALL %d CREDITS QUEUED (%s) for the session of %s"%(len(A),", ".join(ok),V))'''


def paste_windows(now, session):
    """(windows, until): the UTC epoch-second intervals [start, end) in which the line may be pasted, from a
    day before `now` (clock skew) up to the paste cutoff of `session` - every hour but a weekday's from its
    cutoff (15:00 ET, 12:00 on a half-day) to midnight - and that last cutoff as the owner reads it. ET
    offsets are whole hours, so UTC hours classify exactly (shadow_runner.et_now, with its no-tz-database
    fallback)"""
    h = now.astimezone(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)
    windows, open_at = [], None
    for _ in range(24 * 40):
        e = sr.et_now(h)
        day = e.date().isoformat()
        if day > session or (day == session and e.hour >= paste_cutoff(day)):
            break
        ok = not (e.weekday() < 5 and e.hour >= paste_cutoff(day))
        if ok and open_at is None:
            open_at = h
        elif not ok and open_at is not None:
            windows.append((int(open_at.timestamp()), int(h.timestamp())))
            open_at = None
        h += datetime.timedelta(hours=1)
    else:
        raise Refused(f"internal: the session of {session} is more than 40 days away")
    if open_at is None:
        raise Refused(f"internal: no paste window before the session of {session}")
    windows.append((int(open_at.timestamp()), int(h.timestamp())))
    until = f"{paste_cutoff(session)}:00 ET on {datetime.date.fromisoformat(session).strftime('%a')} {session}"
    return tuple(windows), until


def paste_program(book, credits, note, session, last_session, windows, until, rerun):
    """the line's program: the constants, then LINE_PROGRAM. credits: [(engine, amount)], amounts > 0
    rounded to cents; D is their total in whole cents; Z the paste windows [start, end) in whole hours from the
    epoch second K (paste_windows cuts them on whole UTC hours), Y their end as the owner reads it; V the session the credits are for; M the book's last session the plan was made after; G what to do
    then: "re-run <rerun>" (rerun: "mirror_scale.py --to <to>") """
    var, default = STATE_ENV[book]
    if (var, default) != ("MIRROR_STATE_PATH", "./data/mirror_state.json"):
        raise Refused(f"internal: the pasted line reads MIRROR_STATE_PATH, not {var}")
    cents = sum(int(round(a * 100)) for _, a in credits)
    base = int(windows[0][0])                      # Z: each window in whole hours from K (the line: t = (now - K) / 3600)
    if any((x - base) % 3600 for w in windows for x in w):
        raise Refused("internal: a paste window does not start and end on a whole hour")
    hours = tuple(((a - base) // 3600, (b - base) // 3600) for a, b in windows)
    head = (f"import http.client as hc,json,os,sys,time\n"
            f"E=os.environ;B={_py(book)};N={_py(note)};A={_py(tuple((e, a) for e, a in credits))};D={cents};"
            f"K={base};Z={_py(hours)};Y={_py(until)};V={_py(session)};M={_py(last_session)};"
            f"G={_py('re-run ' + rerun)}\n")
    return head + LINE_PROGRAM


def exec_literal(program):
    """the program as ONE Python string literal on one line, with no single quote in it: triple-double-quoted
    (a double quote needs no escape there), every backslash doubled, every newline as \\n, every single quote
    as \\x27; json-escaped instead when it holds a triple quote, ends in a quote or holds a character outside
    printable ASCII"""
    body = program.replace("\\", "\\\\").replace("\n", "\\n").replace("'", "\\x27")
    if '"""' in body or body.endswith('"') or any(not 32 <= ord(ch) <= 126 for ch in body):
        return json.dumps(program, ensure_ascii=True).replace("'", "\\x27")
    return '"""' + body + '"""'


def paste_line(book, credits, note, session, last_session, windows, until, rerun):
    """(the shell line, its python3 -c code, the program the code runs). ONE physical line the owner
    pastes into the executor's Shell: python3 -c 'exec(<the program as one literal>)' (exec_literal), so
    the shell's single quotes hold"""
    program = paste_program(book, credits, note, session, last_session, windows, until, rerun)
    code = "exec(" + exec_literal(program) + ")"
    if "'" in code or "\n" in code:                # never: the escaping above; the shell quoting depends on it
        raise Refused("internal: the pasted line would not be quoted safely")
    line = f"{LINE_PY} -c '{code}'"
    if len(line.encode()) > TTY_LINE_MAX:
        raise Refused(f"internal: the pasted line is {len(line.encode())} bytes, more than a terminal line holds "
                      f"({TTY_LINE_MAX})")
    return line, code, program


def quiet_window(now):
    """the deploy blackout text, naming the coming half-days"""
    today = sr.et_now(now).date().isoformat()
    half = sorted(d for d in getattr(sr, "HALF_DAYS", {}) if d >= today)[:2]
    return (f"Never between {DEPLOY_QUIET[0]} and {DEPLOY_QUIET[1]} ET"
            + (f" ({DEPLOY_QUIET_HALF[0]}-{DEPLOY_QUIET_HALF[1]} ET on a half-day: {', '.join(half)})" if half else ""))


def build(a, env, fetch, now):
    """the plan as a dict for the parsed arguments `a`, or raises Refused"""
    to, headroom = num(a.to), num(a.headroom)
    if to is None or to <= 0 or not plausible(to):
        raise Refused(f"--to must be a positive number of dollars up to {usd(MAX_USD)} ({a.to!r})")
    if headroom is None or not 0 <= headroom <= 1:
        raise Refused(f"--headroom must be a fraction from 0 to 1 ({a.headroom!r})")
    comp = composer_split(a.snapshot or SNAPSHOT, now)
    base = (env.get("MIRROR_EXECUTOR_URL") or "").strip()
    token = (env.get("MIRROR_READ_TOKEN") or "").strip()
    if not base or not token:
        raise Refused("MIRROR_EXECUTOR_URL and MIRROR_READ_TOKEN must both be set (the executor's read-only feed)")
    feed_url_ok(base)
    try:
        feed = (fetch or (lambda u, t: mp.fetch_feed(u, t, history=HISTORY)))(base, token)
    except Exception as e:  # noqa: BLE001
        raise Refused(f"the executor's feed could not be read ({one_line(e, 160)})") from None
    if not isinstance(feed, dict) or not isinstance(feed.get("books"), dict):
        raise Refused("the executor's answer is not a mirror feed")
    name, view = pick_book(feed, a.book)
    problems = health_problems(view)
    if problems:
        raise Refused(f"book {name} is not in a state to scale: " + "; ".join(problems))
    last = view.get("last_session")
    if not isinstance(last, str) or _date(last) is None:
        raise Refused(f"the book's last session on the feed is not a date ({one_line(repr(last), 40)})")
    today_left = session_still_to_run(last, now)
    if today_left:
        raise Refused(f"today's session has not run yet: re-run after it and its post-trade check (if the executor "
                      f"missed today's session, re-run after midnight ET). It is {sr.et_now(now):%H:%M} ET on "
                      f"{today_left}, a session day past its {paste_cutoff(today_left)}:00 paste cutoff, and the "
                      f"book's last session is {last}: a line printed now would be for the session after today's, "
                      f"which runs first and voids it")
    eq, book_eq = sleeve_equities(view)
    if to <= book_eq:
        raise Refused(f"book {name} is already {usd(book_eq)}: --to {usd(to)} is not above it (this planner only "
                      f"scales up)")
    if to > MAX_FACTOR * book_eq:
        raise Refused(f"--to {usd(to)} is {to / book_eq:.1f}x book {name}'s {usd(book_eq)}: more than {MAX_FACTOR:g}x "
                      f"is refused as a likely slipped zero")
    w = comp["weights"]
    at = credits_at(to, w, eq)
    neg = [e for e, _ in ENGINES if at[e][1] < 0]
    if neg:
        low = smallest_to(w, eq, book_eq)
        raise Refused(f"at {usd(to)} " + "; ".join(f"{e} is already above its Composer share (target {usd(at[e][0])}, "
                                                    f"equity {usd(eq[e])})" for e in neg)
                      + (f": the smallest --to at which every credit is >= 0 is {low:.2f}" if low is not None else
                         f": the smallest --to at which every credit is >= 0 is beyond {MAX_FACTOR:g}x the book "
                         f"({usd(MAX_FACTOR * book_eq)}), more than this planner takes - Composer's split and the "
                         f"book's are too far apart (check the snapshot)"))
    sent = [(e, at[e][1]) for e, _ in ENGINES if at[e][1] > 0]
    zero = [e for e, _ in ENGINES if at[e][1] == 0]
    if not sent:
        raise Refused(f"at {usd(to)} every credit rounds to $0.00: nothing to send")
    credit_total = round(sum(c for _, c in at.values()), 2)
    sent_total = round(sum(c for _, c in sent), 2)
    residual = round(to - book_eq - credit_total, 2)
    funded, how, more = funded_estimate(view)
    need = round(funded + sent_total, 2)
    if not plausible(need):
        raise Refused(f"funded_usd {one_line(repr(funded), 40)} + the credits {usd(sent_total)} is not a plausible "
                      f"amount (more than {usd(MAX_USD)}): the cap cannot be computed")
    cap = cap_to_set(need, headroom)
    book = view.get("book") or {}
    book_cash = num(book.get("cash"))
    if book_cash is None or not plausible(book_cash):
        raise Refused(f"the book's cash on the feed is not a number of dollars within {usd(MAX_USD)} "
                      f"({one_line(repr(book.get('cash')), 40)})")
    session = credit_session(last, now)
    div_total, div_rows, div_warn = dividends_due(view, session)
    if not plausible(div_total):
        raise Refused(f"the dividends due on the feed by {session} total {one_line(repr(div_total), 40)}: not a "
                      f"plausible amount (more than {usd(MAX_USD)}, or not finite): a receivable on the feed is malformed")
    margin = round(max(CASH_MARGIN_USD, CASH_MARGIN_FRAC * sent_total), 2)
    cash_exec = round(book_cash + div_total + sent_total, 2)
    cash_need = round(cash_exec + margin, 2)
    to_text = f"{to:,.0f}" if to == int(to) else f"{to:,.2f}"
    note = one_line(f"scale-up to ${to_text} at Composer's split of {comp['date']}", 200)
    to_arg = f"{to:.2f}"
    rerun = f"mirror_scale.py --to {to_arg[:-3] if to_arg.endswith('.00') else to_arg}"
    today = sr.et_now(now).date().isoformat()
    half_days = tuple(sorted(d for d in sr.HALF_DAYS if d >= today))
    windows, until = paste_windows(now, session)
    line, code, program = paste_line(name, sent, note, session, last, windows, until, rerun)
    chk = view["check"]
    health = ("not halted, no open run, no unresolved order, no error, nothing queued, the four sleeves present and "
              f"not frozen; the account held the book at the post-trade check of {chk.get('session')} (done, no "
              f"problem)")
    marks = book.get("marks_asof")
    warnings = list(comp["warnings"]) + more + div_warn
    m = parse_ts(marks)
    mday = et_date(m) if m is not None else None
    if mday is None:
        warnings.append(f"the book's marks have no readable date ({one_line(repr(marks), 40)}): its equity is of an "
                        f"unknown day")
    elif (sr.et_now(now).date() - mday).days > STALE_DAYS:
        warnings.append(f"the book's equity is valued at the marks of {marks} (its last decision, "
                        f"{view.get('last_session')}): it has not run a session since")
    if zero:
        warnings.append(f"{', '.join(zero)} is exactly at its target: no credit is sent for it")
    holdings = round(book_eq - book_cash, 2)
    rows = [{"engine": e, "symphony": sid, "composer_value": round(comp["values"][e], 2), "weight": round(w[e], 6),
             "equity": round(eq[e], 2), "target": at[e][0], "credit": at[e][1]} for e, sid in ENGINES]
    cut = (f"before {PASTE_CUTOFF}:00 ET on a weekday ({PASTE_CUTOFF_HALF}:00 on a half-day"
           + (f": {', '.join(half_days[:2])}" if half_days else "") + ") or any time on a weekend, by " + until)
    steps = [
        f"(a) Render -> ibkr-executor -> Environment: set MIRROR_MAX_BOOK_USD = {cap}, then \"Save, rebuild and "
        f"deploy\". Change only MIRROR_MAX_BOOK_USD in that deploy, not MIRROR_LIVE_ENGINES: a sleeve it drops stays "
        f"in the book's state, not frozen, until the executor's first tick with the IB gateway logged in, so a line "
        f"pasted before then queues the other credits and stops at that one. {quiet_window(now)}: the attestation, "
        f"the decision and its orders run then. The restart logs the IB gateway in again: approve the IB Key push on "
        f"your phone.",
        f"(b) When the executor is back (the deploy live, /health answering), open Render -> ibkr-executor -> Shell and "
        f"paste this ONE line, ONCE, {cut}, for the session of {session}: the credits must be queued before the "
        f"session that applies them, so the evening POLICY routine never sizes a transfer on pre-credit equity. It is "
        f"plain python3 (the standard library only); it reads EXEC_TOKEN inside the container and sends it ONLY to the "
        f"executor in that same container (http://{LINE_HOST}:$PORT/mirror/credit, no proxy, no redirect followed): the "
        f"token never leaves the container and never appears on screen. It sends NOTHING (a line starting NOTHING "
        f"SENT) outside those hours or after {until}, once the book has run a session since this plan, while any "
        f"request is queued (whatever its kind), while the book is halted or a flatten is pending, a run is open or "
        f"a sleeve it credits is frozen or gone, unless the account's post-trade check of {last} is still on record "
        f"done and clean (an applied /mirror/adjust clears it), and unless MIRROR_MAX_BOOK_USD there covers the "
        f"book's own funded_usd plus these credits to the cent; then it queues the {len(sent)} credit(s) and prints "
        f"each answer. At the first error or answer that is not 200 it STOPS and says which were queued (they apply "
        f"at the next session and cannot be withdrawn) and whether the one that failed was NOT queued (an HTTP 4xx, "
        f"or nothing listening) or may have been. Nothing queued at all: fix the cause and paste the line again; "
        f"otherwise, after that session, re-run this planner and paste its new line (the line sends nothing while "
        f"anything is queued). After any /mirror/adjust, re-run this planner and paste only its new line: an adjust "
        f"on the evening of {last} is followed by a new post-trade check of {last}, clean when the shares are as "
        f"booked, so this line would still send, sized on the book before the adjust:",
        f"(c) The executor applies them at the decision of {session} (15:54 ET, 12:54 on a half-day): first the "
        f"dividends due, then the credits, smallest first, each only if the account's cash covers the book's cash "
        f"plus it (the CASH minimum above) and the cap holds, and invests them in the same plan (the daily sleeves go "
        f"to target; KMLM trades too: idle cash above 5% of a threshold sleeve overrides its corridor). Every credit "
        f"taken is alerted. A refused one is alerted in red and dropped, NOT retried: fix the cause, re-run this "
        f"planner and paste its new line.",
        "(d) That night's parity check against Composer (mirror_parity.py) removes the operator credits from that day's "
        "return, so the scale-up is not read as a gain.",
    ]
    return {
        "ok": True, "book": name, "to": round(to, 2), "factor": round(to / book_eq, 4), "note": note,
        "session": session, "paste_until": until, "paste_windows": windows,
        "snapshot": {k: comp[k] for k in ("path", "taken_at", "date", "age_days")},
        "feed_utc": feed.get("utc"), "marks_asof": marks, "last_session": view.get("last_session"),
        "health": health, "engines": rows,
        "total": {"composer_value": round(sum(comp["values"].values()), 2), "weight": 1.0,
                  "equity": round(sum(eq.values()), 2), "book_equity": round(book_eq, 2),
                  "target": round(sum(r["target"] for r in rows), 2), "credit": credit_total},
        "residual": residual, "holdings": holdings,
        "funded": {"now": funded, "how": how, "credits": round(need - funded, 2), "after": need},
        "cap": {"headroom": headroom, "need": need, "with_headroom": round(need * (1 + headroom), 2), "set": cap,
                "rule": "the executor refuses a credit to a live book that takes funded_usd above MIRROR_MAX_BOOK_USD "
                        "+ $1, credit by credit, smallest first, and drops it (ibkr-executor/app/mirror.py _over_cap, "
                        "_book_cap_usd, _apply_credits); the pasted line refuses unless the cap covers funded_usd plus "
                        "the credits to the cent"},
        "cash": {"book_cash": round(book_cash, 2), "dividends": div_total, "dividends_due": div_rows,
                 "credits": sent_total, "executor_need": cash_exec, "margin": margin, "need": cash_need,
                 "rule": "at the decision the executor credits the dividends due, then refuses a credit the account's "
                         "cash (IBKR's TotalCashValue) does not cover on top of the book's cash within $1, credit by "
                         "credit, smallest first (mirror.py _dividends, _apply_credits). The feed does not show the "
                         "account's cash: check it at IBKR before (b)",
                 "short": f"If the account's spare cash is short by even $1 (more than the executor's $1.00 tolerance "
                          f"below the book's cash + the dividends due + the credits, {usd(cash_exec)}), the executor "
                          f"refuses the LARGEST credit whole and the book trades mis-split until a new plan lands."},
        "post_to": f"http://{LINE_HOST}:$PORT/mirror/credit (the executor in its own container; PORT as start.sh "
                   f"reads it, {PORT_DEFAULT} when unset)",
        "paste": line, "code": code, "program": program, "steps": steps, "warnings": warnings,
    }


def render(p):
    """the plan as the owner reads it"""
    out = [f"MIRROR SCALE PLAN — book {p['book']}: {usd(p['total']['book_equity'])} -> {usd(p['to'])} "
           f"(x{p['factor']:.2f}) at Composer's split of {p['snapshot']['date']}, for the session of {p['session']}",
           f"Composer: {p['snapshot']['path']}, taken {p['snapshot']['taken_at']} ({p['snapshot']['age_days']} day(s) old); "
           f"unallocated cash left out",
           f"mirror: the executor's feed of {p['feed_utc']}, equity at the marks of {p['marks_asof']} (last session "
           f"{p['last_session']}); {p['health']}"]
    for w in p["warnings"]:
        out.append(f"WARNING: {w}")
    out.append("")
    out.append(f"{'engine':<7}{'Composer':>14}{'weight':>10}{'mirror now':>13}{'target':>13}{'credit':>13}")
    for r in p["engines"]:
        out.append(f"{r['engine']:<7}{usd(r['composer_value']):>14}{r['weight']:>10.3%}{usd(r['equity']):>13}"
                   f"{usd(r['target']):>13}{usd(r['credit']):>13}")
    t = p["total"]
    out.append(f"{'total':<7}{usd(t['composer_value']):>14}{t['weight']:>10.3%}{usd(t['equity']):>13}"
               f"{usd(t['target']):>13}{usd(t['credit']):>13}")
    out.append(f"the credits {usd(t['credit'])} = {usd(p['to'])} - the book's {usd(t['book_equity'])}"
               + (" exactly" if not p["residual"] else
                  f" - {usd(p['residual'])} (rounding each target and equity to cents leaves {usd(p['residual'])} "
                  f"unallocated)" if p["residual"] > 0 else
                  f" + {usd(-p['residual'])} (rounding each target and equity to cents adds {usd(-p['residual'])})"))
    out.append(f"the credits are fixed dollars: the book lands at {usd(p['to'])} plus whatever its current "
               f"{usd(p['holdings'])} of holdings moves before the session, less that session's commissions")
    c, f, k = p["cap"], p["funded"], p["cash"]
    out += ["", f"CAP: MIRROR_MAX_BOOK_USD = {c['set']}",
            f"  {c['rule']}",
            f"  funded_usd now {usd(f['now'])}: {f['how']}",
            f"  after the credits {usd(f['now'])} + {usd(f['credits'])} = {usd(c['need'])}; x {1 + c['headroom']:g} = "
            f"{usd(c['with_headroom'])}; up to the next ${CAP_STEP_USD}",
            f"CASH: the account must hold at least {usd(k['need'])} in cash at the decision of {p['session']}: the "
            f"book's {usd(k['book_cash'])} + the dividends due by then {usd(k['dividends'])} + the credits "
            f"{usd(k['credits'])} + a margin of {usd(k['margin'])} (the larger of ${CASH_MARGIN_USD:,.0f} and "
            f"{CASH_MARGIN_FRAC:.1%} of the credits)"]
    for r in k["dividends_due"]:
        out.append(f"  dividend due {r['due']}: {r['sleeve']} {r['ticker']} {usd(r['total'])} ({r['id']})")
    out += [f"  {k['short']}",
            f"  {k['rule']}",
            "", "STEPS, in order:", p["steps"][0], p["steps"][1], "", p["paste"], "", p["steps"][2], p["steps"][3]]
    return "\n".join(out)


def run(argv=None, env=None, fetch=None, now=None):
    """(exit code, text). fetch(url, read_token) -> feed is the test seam; nothing is ever sent"""
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    now = now or datetime.datetime.now(datetime.timezone.utc)
    secret = (env.get("MIRROR_READ_TOKEN") or "").strip()

    def clean(text, n=900):
        text = str(text)
        if secret:
            text = text.replace(secret, "***")
        return one_line(text, n)

    try:
        a = parse(list(argv))
        p = build(a, env, fetch, now)
    except Refused as e:
        return 1, f"MIRROR SCALE REFUSED — {clean(e)}"
    text = json.dumps(p, indent=1) if a.json else render(p)
    if secret and secret in text:                  # never: nothing read from the feed carries it
        return 1, "MIRROR SCALE REFUSED — internal: the plan would print the read token"
    return 0, text


def main():
    code, text = run()
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
