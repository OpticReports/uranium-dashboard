#!/usr/bin/env python3
"""Scale the IBKR mirror's live book to a new size at Composer's split: a read-only PLANNER
(composer/IBKR_MIRROR.md "Scaling the live book"; CLAUDE.md "ONE BRAIN, TWO BROKERS").

It sends nothing to the executor and holds no exec token. It reads Composer's split from the daily
monitor's snapshot and the live book from the executor's read-only feed (GET
{MIRROR_EXECUTOR_URL}/mirror/feed, header X-Read-Token = MIRROR_READ_TOKEN, through
mirror_parity.fetch_feed: https only, a redirect never followed), and prints the owner's steps: the
cap to set on the executor, then ONE line to paste into the executor's own Shell on Render, which
reads EXEC_TOKEN inside the container and queues one cash credit per sleeve (POST /mirror/credit).

  mirror_scale.py --to 50000 [--snapshot composer/results/monitor/last-snapshot.json] [--book live]
                  [--headroom 0.05] [--json]

1 Composer's split: the four engines' "value" in the snapshot, by symphony id; weight = value / the
  four's sum (unallocated cash and anything else left out). Refused unless all four are positive
  numbers; a snapshot more than 3 calendar days old (ET) is warned about, not refused.
2 The mirror: the one book whose mode is "live" (--book names it). Refused unless it is not halted
  (no flatten pending), has no open run, no unresolved order, no last_error, no failed save, nothing
  queued (pending_requests), no account-versus-book problem, and holds the four sleeves and no other,
  none frozen, each valued.
3 The plan: target = round(to x weight, 2); credit = round(target - the sleeve's equity, 2), the
  equity at the book's marks of its last decision. Refused when --to is not above the book's equity,
  is more than 10x it (a slipped zero), or any credit is negative (the line names the smallest --to
  at which none is).
4 The cap: the executor refuses a credit that takes a live book's funded_usd (its seeds plus every
  positive credit and what /mirror/adjust added) above MIRROR_MAX_BOOK_USD + $1, credit by credit,
  smallest first, and drops it (ibkr-executor/app/mirror.py _over_cap, _apply_credits). The feed does
  not publish funded_usd (mirror.py _publish): it is estimated as the seeds the feed lists plus the
  operator credits in its session rows. Cap to set = (funded + the credits) x (1 + headroom), rounded
  up to the next $500. The pasted line checks the executor's OWN funded_usd against the cap it was
  deployed with before it sends anything.

Exit 0 with a plan (human text, or --json); 1 with one line starting "MIRROR SCALE REFUSED".
Env: MIRROR_EXECUTOR_URL (https), MIRROR_READ_TOKEN. Nothing is written anywhere.
"""
import argparse
import datetime
import json
import math
import os
import re
import shlex
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import mirror_parity as mp  # noqa: E402  (fetch_feed: the one reader of the executor's feed)
import shadow_runner as sr  # noqa: E402  (et_now; HALF_DAYS)

# engine -> Composer symphony id, in the book's order (= composer/fixtures/approved/manifest.json: a gate pins it)
ENGINES = (("HG", "mbkiXcuNDjueXpiox5Av"), ("KMLM", "YPTSJFJwD2ZKfAeYJUbW"),
           ("SLEEVE", "nNdBk7hc5NiBzeRvbI5T"), ("HARV", "ORQNCfZnA18wmsMWVhf8"))
SNAPSHOT = os.path.join(HERE, "..", "results", "monitor", "last-snapshot.json")   # monitor.py writes it daily
STALE_DAYS = 3                   # a snapshot (or the book's marks) older than this many ET calendar days: warned
HEADROOM = 0.05
CAP_STEP_USD = 500               # the cap is rounded UP to a multiple of this
MAX_FACTOR = 10.0                # --to above this many times the book's equity: refused (a slipped zero)
SEED_TOL_USD = 1.0               # ibkr-executor/app/mirror.py SEED_TOL_USD: _over_cap allows the cap plus this
HISTORY = 120                    # session rows asked of the feed: its most (service.py; mirror.py HISTORY_KEEP)
EQUITY_TOL_USD = 0.05            # the book's equity vs the four sleeves' (each published rounded to cents)
# the executor's own interpreter (ibkr-executor/Dockerfile: WORKDIR /opt/executor, python3 -m venv venv): it has
# httpx with its CA bundle, the client the executor itself uses for https (app/alerts.py). The image's system
# python3 is installed --no-install-recommends and is not known to have a CA store
EXEC_PY = "/opt/executor/venv/bin/python3"
# a book -> (the env var naming its state file, the default): ibkr-executor/app/config.py; render.yaml sets
# MIRROR_STATE_PATH=/app/data/mirror_state.json. Its inbox is <state>.inbox.json (mirror.py _inbox_path)
STATE_ENV = {"live": ("MIRROR_STATE_PATH", "./data/mirror_state.json")}
DEPLOY_QUIET = ("15:15", "16:05")          # no deploy then: the 15:15 attestation, the 15:54 decision, its orders
DEPLOY_QUIET_HALF = ("12:15", "13:05")     # ... on a 13:00 half-day


def one_line(e, n=200):
    return " ".join(str(e).split())[:n]


def usd(x):
    return f"${x:,.2f}"


def num(x):
    """a finite number, or None (bools are not numbers here)"""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


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
    if taken is None:
        raise Refused(f"{shown} has no readable taken_at ({one_line(repr(snap.get('taken_at')), 60)}): the date of "
                      f"Composer's split cannot be told")
    values, bad = {}, []
    for eng, sid in ENGINES:
        row = snap["symphonies"].get(sid)
        v = num(row.get("value")) if isinstance(row, dict) else None
        if v is None or v <= 0:
            bad.append(f"{eng} ({sid}): " + ("missing" if not isinstance(row, dict) else f"value {row.get('value')!r}"))
        else:
            values[eng] = v
    if bad:
        raise Refused(f"Composer's split cannot be read from {shown}: " + "; ".join(bad)
                      + " (each of the four engines needs a positive value)")
    total = sum(values.values())
    day = sr.et_now(taken).date()
    age = (sr.et_now(now).date() - day).days
    warnings = []
    if age > STALE_DAYS:
        warnings.append(f"Composer's snapshot is {age} days old (taken {day.isoformat()}, {snap['taken_at']}): the split "
                        f"has moved since; run the monitor, or pass a newer --snapshot")
    elif age < 0:
        warnings.append(f"Composer's snapshot is dated in the future ({snap['taken_at']}): check the file and the clock")
    return {"path": shown, "taken_at": snap["taken_at"], "date": day.isoformat(), "age_days": age,
            "values": values, "weights": {e: values[e] / total for e in values}, "warnings": warnings}


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
    chk = view.get("check") if isinstance(view.get("check"), dict) else {}
    if chk.get("problems"):
        probs = chk["problems"] if isinstance(chk["problems"], list) else [chk["problems"]]
        out.append(f"the account does not hold the book (check of {chk.get('session')}): "
                   + "; ".join(one_line(p, 80) for p in probs[:3]))
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
            raise Refused(f"the sleeve {e} has no usable equity on the feed ({sleeves[e].get('equity')!r}): a price "
                          f"is missing from the book's marks")
        eq[e] = v
    total = num(book.get("equity"))
    if total is None or total <= 0:
        raise Refused(f"the book has no usable equity on the feed ({book.get('equity')!r})")
    if abs(sum(eq.values()) - total) > EQUITY_TOL_USD:
        raise Refused(f"the book's equity {usd(total)} is not its four sleeves' {usd(sum(eq.values()))}: the feed does "
                      f"not add up")
    return eq, total


def funded_estimate(view):
    """(funded_usd now, how it was found, warnings), or raises Refused. funded_usd is what the executor's
    cap counts (mirror.py _over_cap): the seeds, plus every positive operator credit (_apply_credits),
    plus what /mirror/adjust added. Taken from the feed when it publishes it; otherwise the seeds the
    feed lists plus the operator credits in its session rows (dividends are not counted: the cap does
    not count them either)"""
    pub = view.get("funded_usd")
    if pub is not None:
        v = num(pub)
        if v is None or v < 0:
            raise Refused(f"the feed's funded_usd is not a number ({pub!r})")
        return round(v, 2), "the executor's funded_usd, published on the feed", []
    seeded = view.get("seeded")
    if not isinstance(seeded, dict) or not seeded:
        raise Refused("the feed lists no seeds for the book: the capital its cap counts cannot be estimated")
    seeds = 0.0
    for name, row in seeded.items():
        a = num(row.get("amount")) if isinstance(row, dict) else None
        if a is None or a < 0:
            raise Refused(f"the feed's seed of {name} is not an amount ({row!r})")
        seeds += a
    history = view.get("history") if isinstance(view.get("history"), list) else []
    rows = [r for r in history + [view.get("last_run")] if isinstance(r, dict)]
    taken = {}
    for r in rows:
        for c in r.get("credits") or []:
            a = num(c.get("amount")) if isinstance(c, dict) else None
            if a is None or a <= 0 or c.get("kind") != "credit":
                continue
            taken[c.get("id") or (r.get("session"), c.get("sleeve"), a)] = a
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
    return round(seeds + credits, 2), how, warnings


# ------------------------------------------------------------------ the plan
def credits_at(to, weights, equities):
    """{engine: (target, credit)}: target = round(to x weight, 2), credit = round(target - equity, 2)"""
    out = {}
    for e, _ in ENGINES:
        target = round(to * weights[e], 2)
        out[e] = (target, round(target - equities[e], 2))
    return out


def smallest_to(weights, equities, book_equity):
    """the smallest --to, in cents, at which every credit is >= 0 and the book grows. A credit is >= 0
    once round(to x weight, 2) reaches the equity, i.e. from about (equity - half a cent) / weight: the
    scan starts a cent below that bound and walks up a cent at a time (credits never fall as --to rises)"""
    start = max((equities[e] - 0.01) / weights[e] for e, _ in ENGINES)
    to = math.floor(max(start, book_equity) * 100) / 100
    for _ in range(100000):
        if to > book_equity and all(c >= 0 for _, c in credits_at(to, weights, equities).values()):
            return to
        to = round(to + 0.01, 2)
    return to


def cap_to_set(need, headroom):
    """need x (1 + headroom), rounded UP to the next multiple of CAP_STEP_USD (in whole cents: exact)"""
    cents = int(round(need * (1.0 + headroom) * 100))
    step = CAP_STEP_USD * 100
    return ((cents + step - 1) // step) * CAP_STEP_USD


def credit_url(base):
    """https://<host of MIRROR_EXECUTOR_URL>/mirror/credit, or raises Refused: the pasted line sends
    EXEC_TOKEN, so https only, and nothing in it that could leave the line's quotes"""
    u = urllib.parse.urlparse((base or "").strip())
    host = u.hostname or ""
    if (u.scheme != "https" or not re.fullmatch(r"[a-z0-9.-]+", host) or u.username or u.password or u.query
            or u.fragment or not re.fullmatch(r"[A-Za-z0-9/_.-]*", u.path)):
        raise Refused("MIRROR_EXECUTOR_URL must be a plain https URL of the executor (the pasted line sends EXEC_TOKEN "
                      "to it)")
    try:
        port = u.port
    except ValueError:
        raise Refused("MIRROR_EXECUTOR_URL has a bad port") from None
    return f"https://{host}{f':{port}' if port else ''}{u.path.rstrip('/')}/mirror/credit"


def _lit(s):
    """a Python string literal with no single quote in it (the line is single-quoted for the shell)"""
    return json.dumps(str(s), ensure_ascii=True).replace("'", "\\x27")


def paste_line(url, book, credits, note):
    """(the shell line, its Python code). The code runs in the executor's container with the executor's
    own Python: it reads EXEC_TOKEN there and sends NOTHING unless the token is set, the book's state
    file is there, no credit is already queued (the state's requests and its inbox: the line was pasted
    before), and MIRROR_MAX_BOOK_USD covers the book's own funded_usd plus these credits (the executor's
    _over_cap: funded + amount <= cap + $1). Then one POST per credit, each answer printed, stopping at
    the first that is not 200. credits: [(engine, amount)], amounts > 0"""
    var, default = STATE_ENV[book]
    total = round(sum(a for _, a in credits), 2)
    pairs = "".join(f"({_lit(e)},{a!r})," for e, a in credits)
    code = ";".join([
        "import os,json,pathlib,httpx",
        "E=os.environ",
        'T=E.get("EXEC_TOKEN") or ""',
        f"P=E.get({_lit(var)}) or {_lit(default)}",
        f"U={_lit(url)}",
        f"B={_lit(book)}",
        f"N={_lit(note)}",
        f"A=({pairs})",
        f"D={total!r}",
        "X=os.path.exists",
        "R=lambda f:json.loads(pathlib.Path(f).read_text())",
        'I=R(P+".inbox.json") if X(P+".inbox.json") else []',                     # the inbox first: a request moves
        "S=R(P) if X(P) else None",                                                 # from it into the state
        'Q=[r for r in list(I)+list((S or {}).get("requests") or []) if isinstance(r,dict) and r.get("kind")=="credit"]',
        'C=float(E.get("MIRROR_MAX_BOOK_USD") or 0)',
        'F=float((S or {"funded_usd":0})["funded_usd"])',              # none in the state: an error, nothing sent
        'W="NOTHING SENT: EXEC_TOKEN is not set here (paste this line in the Shell of ibkr-executor on Render)" if not T '
        'else "NOTHING SENT: no book state at %s (paste this line in the Shell of ibkr-executor on Render)"%P if S is None '
        'else "NOTHING SENT: %d credit(s) already queued, so this line was sent before: %r"%(len(Q),[(r.get("sleeve"),'
        'r.get("amount"),r.get("id")) for r in Q]) if Q '
        'else "NOTHING SENT: MIRROR_MAX_BOOK_USD here is %.2f; the book has taken %.2f and these credits add %.2f, '
        '%.2f in all: set the cap (step a) and deploy first"%(C,F,D,F+D) if F+D>C+1 else ""',
        'print(W) if W else print("ALL %d CREDITS QUEUED: the executor applies them at its next session"%len(A) '
        'if all((lambda r:(print(s,a,r.status_code,r.text),r.status_code==200)[1])(httpx.post(U,json={"sleeve":s,'
        '"amount":a,"note":N,"book":B},headers={"X-Exec-Token":T},timeout=30)) for s,a in A) '
        'else "STOPPED at the first answer that is not 200: the lines above show what was queued; do NOT paste '
        'this line again")',
    ])
    if "'" in code:                                # never: _lit escapes it; the shell quoting depends on it
        raise Refused("internal: the pasted line would not be quoted safely")
    return f"{EXEC_PY} -c {shlex.quote(code)}", code


def quiet_window(now):
    """the deploy blackout text, naming the coming half-days"""
    today = sr.et_now(now).date().isoformat()
    half = sorted(d for d in getattr(sr, "HALF_DAYS", {}) if d >= today)[:2]
    return (f"Never between {DEPLOY_QUIET[0]} and {DEPLOY_QUIET[1]} ET"
            + (f" ({DEPLOY_QUIET_HALF[0]}-{DEPLOY_QUIET_HALF[1]} ET on a half-day: {', '.join(half)})" if half else ""))


def build(a, env, fetch, now):
    """the plan as a dict for the parsed arguments `a`, or raises Refused"""
    to, headroom = num(a.to), num(a.headroom)
    if to is None or to <= 0:
        raise Refused(f"--to must be a positive number of dollars ({a.to!r})")
    if headroom is None or not 0 <= headroom <= 1:
        raise Refused(f"--headroom must be a fraction from 0 to 1 ({a.headroom!r})")
    comp = composer_split(a.snapshot or SNAPSHOT, now)
    base = (env.get("MIRROR_EXECUTOR_URL") or "").strip()
    token = (env.get("MIRROR_READ_TOKEN") or "").strip()
    if not base or not token:
        raise Refused("MIRROR_EXECUTOR_URL and MIRROR_READ_TOKEN must both be set (the executor's read-only feed)")
    url = credit_url(base)
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
                      + f": the smallest --to at which every credit is >= 0 is {low:.2f}")
    sent = [(e, at[e][1]) for e, _ in ENGINES if at[e][1] > 0]
    zero = [e for e, _ in ENGINES if at[e][1] == 0]
    if not sent:
        raise Refused(f"at {usd(to)} every credit rounds to $0.00: nothing to send")
    credit_total = round(sum(c for _, c in at.values()), 2)
    residual = round(to - book_eq - credit_total, 2)
    funded, how, more = funded_estimate(view)
    need = round(funded + sum(c for _, c in sent), 2)
    cap = cap_to_set(need, headroom)
    to_text = f"{to:,.0f}" if to == int(to) else f"{to:,.2f}"
    note = one_line(f"scale-up to ${to_text} at Composer's split of {comp['date']}", 200)
    line, code = paste_line(url, name, sent, note)
    book_cash = num((view.get("book") or {}).get("cash"))
    if book_cash is None:
        raise Refused(f"the book's cash on the feed is not a number ({(view.get('book') or {}).get('cash')!r})")
    cash_need = round(book_cash + sum(c for _, c in sent), 2)
    chk = view.get("check") if isinstance(view.get("check"), dict) else {}
    health = ("not halted, no open run, no unresolved order, no error, nothing queued, the four sleeves present and "
              "not frozen; " + (f"the account held the book at the check of {chk.get('session')}" if chk.get("session")
                                else "no account check on the feed yet"))
    book = view.get("book") or {}
    marks = book.get("marks_asof")
    warnings = list(comp["warnings"]) + more
    m = parse_ts(marks)
    if m is None:
        warnings.append(f"the book's marks have no readable date ({marks!r}): its equity is of an unknown day")
    elif (sr.et_now(now).date() - sr.et_now(m).date()).days > STALE_DAYS:
        warnings.append(f"the book's equity is valued at the marks of {marks} (its last decision, "
                        f"{view.get('last_session')}): it has not run a session since")
    if zero:
        warnings.append(f"{', '.join(zero)} is exactly at its target: no credit is sent for it")
    rows = [{"engine": e, "symphony": sid, "composer_value": round(comp["values"][e], 2), "weight": round(w[e], 6),
             "equity": round(eq[e], 2), "target": at[e][0], "credit": at[e][1]} for e, sid in ENGINES]
    steps = [
        f"(a) Render -> ibkr-executor -> Environment: set MIRROR_MAX_BOOK_USD = {cap}, then \"Save, rebuild and "
        f"deploy\". {quiet_window(now)}: the attestation, the decision and its orders run then. The "
        f"restart logs the IB gateway in again: approve the IB Key push on your phone.",
        f"(b) When the executor is back (the deploy live, /health answering), open Render -> ibkr-executor -> Shell and "
        f"paste this ONE line, ONCE. It runs with the executor's own Python and reads EXEC_TOKEN inside the container "
        f"(it never appears on screen); it sends NOTHING unless MIRROR_MAX_BOOK_USD there covers the book's own "
        f"funded_usd plus these credits and no credit is already queued; then it queues the {len(sent)} credit(s) and "
        f"prints each answer, stopping at the first that is not 200:",
        f"(c) The executor applies them at its next session's decision (15:54 ET, 12:54 on a half-day; queued after the "
        f"decision on a session day: the next session's), smallest first, each only if the account's cash covers the "
        f"book's cash plus it and the cap holds, and invests them in the same plan (the daily sleeves go to target; "
        f"KMLM trades too: idle cash above 5% of a threshold sleeve overrides its corridor). Every credit taken is "
        f"alerted. A refused one is alerted in red and dropped, NOT retried: fix the cause, re-run this planner and "
        f"paste its new line.",
        "(d) That night's parity check against Composer (mirror_parity.py) removes the operator credits from that day's "
        "return, so the scale-up is not read as a gain.",
    ]
    return {
        "ok": True, "book": name, "to": round(to, 2), "factor": round(to / book_eq, 4), "note": note,
        "snapshot": {k: comp[k] for k in ("path", "taken_at", "date", "age_days")},
        "feed_utc": feed.get("utc"), "marks_asof": marks, "last_session": view.get("last_session"),
        "health": health, "engines": rows,
        "total": {"composer_value": round(sum(comp["values"].values()), 2), "weight": 1.0,
                  "equity": round(sum(eq.values()), 2), "book_equity": round(book_eq, 2),
                  "target": round(sum(r["target"] for r in rows), 2), "credit": credit_total},
        "residual": residual,
        "funded": {"now": funded, "how": how, "credits": round(need - funded, 2), "after": need},
        "cap": {"headroom": headroom, "need": need, "with_headroom": round(need * (1 + headroom), 2), "set": cap,
                "rule": "the executor refuses a credit to a live book that takes funded_usd above MIRROR_MAX_BOOK_USD "
                        "+ $1, credit by credit, smallest first, and drops it (ibkr-executor/app/mirror.py _over_cap, "
                        "_book_cap_usd, _apply_credits)"},
        "cash": {"book_cash": round(book_cash, 2), "need": cash_need,
                 "rule": "the executor also refuses a credit the account's cash (IBKR's TotalCashValue) does not cover "
                         "on top of the book's cash, read at the decision, credit by credit (mirror.py _apply_credits). "
                         "The feed does not show the account's cash: check it at IBKR before (b)"},
        "url": url, "paste": line, "code": code, "steps": steps, "warnings": warnings,
    }


def render(p):
    """the plan as the owner reads it"""
    out = [f"MIRROR SCALE PLAN — book {p['book']}: {usd(p['total']['book_equity'])} -> {usd(p['to'])} "
           f"(x{p['factor']:.2f}) at Composer's split of {p['snapshot']['date']}",
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
    out.append(f"the credits are fixed dollars and the sleeves move until the session applies them: the book lands "
               f"within that move of its {usd(t['book_equity'])}, not on {usd(p['to'])} to the cent")
    c, f = p["cap"], p["funded"]
    out += ["", f"CAP: MIRROR_MAX_BOOK_USD = {c['set']}",
            f"  {c['rule']}",
            f"  funded_usd now {usd(f['now'])}: {f['how']}",
            f"  after the credits {usd(f['now'])} + {usd(f['credits'])} = {usd(c['need'])}; x {1 + c['headroom']:g} = "
            f"{usd(c['with_headroom'])}; up to the next ${CAP_STEP_USD}",
            f"CASH: the account must hold at least {usd(p['cash']['need'])} in cash at the decision (the book's "
            f"{usd(p['cash']['book_cash'])} + the credits)",
            f"  {p['cash']['rule']}",
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
