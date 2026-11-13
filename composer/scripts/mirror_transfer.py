#!/usr/bin/env python3
"""The mirror leg of a POLICY capital move (composer/POLICY.md "IBKR mirror"; composer/IBKR_MIRROR.md;
CLAUDE.md "ONE BRAIN, TWO BROKERS").

When a POLICY operation moves capital between two symphonies on Composer, the routine that executed
it runs this in the same run. It holds no Composer key and makes no Composer call. The mirror's book
is a different size, so it moves the same FRACTION of its own giving sleeve, not the same dollars:

    fraction = composer_amount / composer_from_value      (the giving symphony's value BEFORE the move)
    amount   = round(fraction x the FROM sleeve's equity on the executor, 2)

It reads the executor's read-only feed (GET {MIRROR_EXECUTOR_URL}/mirror/feed, header X-Read-Token =
MIRROR_READ_TOKEN) for the sleeve's equity, then POSTs {"from", "to", "amount", "note", "book"} to
{MIRROR_EXECUTOR_URL}/mirror/transfer with header X-Transfer-Token = MIRROR_TRANSFER_TOKEN: the
executor's transfer-only credential. It opens that one route, the executor caps what it moves per day
and alerts on every use; it cannot trade, halt, resume or read anything. The executor queues the
move and applies it with its next session's plan.

  mirror_transfer.py --from HG --to SLEEVE --composer-amount 5000 --composer-from-value 104827.05
                     --composer-from-value-after 99827.05 [--book live] [--note "..."] [--again] [--dry-run]

Pass BOTH values of the giving symphony, before and after the move: with --composer-from-value-after
the script refuses unless |before - amount - after| <= max($50, 1% of before), which catches the value
after the move passed as "before" (the fraction would be too large).

--book: the executor's book by name; default: the one book whose mode is "live" (none: refused, never
guessed - with no live book there is no mirror leg). --dry-run: everything but the POST. One summary
line on stdout starting "MIRROR TRANSFER". Exit 0 when the request was queued, when the move is below
$1 at the mirror's size (nothing is sent: the expected outcome on a small book) and on a dry run; 1
otherwise, the ledger's "outcome" saying which:

  refused    nothing was sent, or the executor answered an HTTP 4xx with a JSON body (its own words,
             never a token), or a redirect (never followed: the token goes to the one host only). Among
             the reasons nothing is sent: operator credits (kind "credit": POST /mirror/credit, e.g. a
             scale-up) still queued for either sleeve of the move - the FROM sleeve's equity it is sized on
             is pre-credit until the session applies them: size the move after the session applies them;
             re-run after that session
  duplicate  the book's pending_requests already hold a transfer by this token for the same from/to,
             OR this script's own ledger has a row of the same ET date, book, from and to that was
             sent or is unknown (a request sits in the executor's inbox for up to a minute before the
             feed lists it, and leaves the list once a plan takes it): nothing is sent unless --again
             says a second move of the pair is meant. A ledger that cannot be read refuses the same way
  unknown    the request left and what came back does not say whether it was queued (a 5xx, an answer
             that is not JSON, a 200 without "ok", a timeout, a dropped connection): do NOT simply
             re-run (a re-run is refused as a duplicate). Read the executor's feed - the book's
             pending_requests and today's session row - and re-send with --again only if the transfer
             is in neither

The executor applies a queued move at the mirror's next session: today's if the request is queued
before about 15:54 ET on a session day, otherwise the next trading day's.
One JSON line per call, sent or not, is appended to results/mirror/transfer-ledger.jsonl.

Env: MIRROR_EXECUTOR_URL (https; http only for localhost), MIRROR_READ_TOKEN, MIRROR_TRANSFER_TOKEN.
"""
import argparse
import datetime
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mirror_parity as mp  # noqa: E402  (fetch_feed: the one reader of the executor's feed; et_now)

LEDGER_PATH = os.path.join(HERE, "..", "results", "mirror", "transfer-ledger.jsonl")
MAX_FRACTION = 0.5               # a POLICY move never takes more than half of the giving symphony
MIN_AMOUNT = 1.00                # below this the mirror's own dust floors would drop it anyway
AFTER_TOL_USD, AFTER_TOL_FRAC = 50.0, 0.01     # --composer-from-value-after: |before - amount - after| allowed
TIMEOUT_S = 20
LOCAL = mp.LOCAL


def one_line(e, n=200):
    return " ".join(str(e).split())[:n]


class Refused(Exception):
    """why nothing is sent (exit 1)"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):                      # a bad command line is a refusal (exit 1), said on the one line
        raise Refused(f"bad arguments: {message}")


def parse(argv):
    p = _Parser(prog="mirror_transfer.py", add_help=True)
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--composer-amount", type=float, required=True, help="the dollars Composer moved")
    p.add_argument("--composer-from-value", type=float, required=True,
                   help="the giving symphony's value BEFORE the move")
    p.add_argument("--composer-from-value-after", type=float, default=None,
                   help="the giving symphony's value AFTER the move. Pass it as well: the script then refuses unless "
                        "|before - amount - after| <= max($50, 1%% of before), which catches the value after the move "
                        "passed as --composer-from-value")
    p.add_argument("--book", default=None, help="the executor's book; default: the one live book")
    p.add_argument("--note", default=None)
    p.add_argument("--again", action="store_true",
                   help="send although a transfer by this token for the same from/to is already queued, or this "
                        "script's ledger says one was sent (or may have been) today")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def fraction_of(amount, value):
    """composer_amount / composer_from_value, or raises Refused: both finite and positive, 0 < f <= 0.5"""
    for name, x in (("--composer-amount", amount), ("--composer-from-value", value)):
        if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or x <= 0:
            raise Refused(f"{name} must be a positive number")
    f = amount / value
    if not 0 < f <= MAX_FRACTION:
        raise Refused(f"the move is {f:.2%} of the giving symphony: outside 0 < fraction <= {MAX_FRACTION:.0%} "
                      f"(check the amount and the symphony's value BEFORE the move)")
    return f


def check_after(amount, before, after):
    """raises Refused unless the giving symphony's value after the move is what before - amount leaves,
    within max($50, 1% of before) (the market moves it a little between the two readings)"""
    if not isinstance(after, (int, float)) or isinstance(after, bool) or not math.isfinite(after) or after < 0:
        raise Refused("--composer-from-value-after must be a number, 0 or more")
    gap, tol = abs(before - amount - after), max(AFTER_TOL_USD, AFTER_TOL_FRAC * before)
    if gap > tol:
        raise Refused(f"the giving symphony's values do not fit the move: ${before:,.2f} before - ${amount:,.2f} moved "
                      f"is ${before - amount:,.2f}, not the ${after:,.2f} given as after (off by ${gap:,.2f}, allowed "
                      f"${tol:,.2f}): --composer-from-value must be the value BEFORE the move")


def queued_already(view, src, dst):
    """the transfers by the transfer token for this from/to that the book still holds (pending_requests),
    or raises Refused when the feed's list cannot be read as one"""
    pend = view.get("pending_requests")
    if pend is None:
        return []
    if not isinstance(pend, list):
        raise Refused("the book's pending_requests on the feed is not a list: whether this transfer is already "
                      "queued cannot be told")
    return [r for r in pend if isinstance(r, dict) and r.get("kind", "transfer") == "transfer"
            and r.get("from") == src and r.get("to") == dst and r.get("via") == "transfer_token"]


def credits_queued(view, src, dst):
    """the operator credits (kind "credit": POST /mirror/credit, a fee debit included) the book still holds
    for either sleeve of the move (pending_requests), or raises Refused when the feed's list cannot be read
    as one. Until a session applies them the sleeves' equity on the feed is pre-credit, and the move is a
    fraction of the FROM sleeve's equity"""
    pend = view.get("pending_requests")
    if pend is None:
        return []
    if not isinstance(pend, list):
        raise Refused("the book's pending_requests on the feed is not a list: whether operator credits are queued "
                      "cannot be told")
    return [r for r in pend if isinstance(r, dict) and r.get("kind") == "credit" and r.get("sleeve") in (src, dst)]


CREDITS_NEXT = "size the move after the session applies them; re-run after that session"


UNKNOWN_NEXT = ("do NOT simply re-run: read the executor's feed (the book's pending_requests and today's session "
                "row) and re-send with --again only if the transfer is in neither")


def sent_already(path, day, book, src, dst):
    """this script's own ledger rows of the same ET date, book, from and to that left for the executor
    (outcome "sent" or "unknown", not a dry run), or raises Refused when the ledger cannot be read as
    one (never taken as empty). A ledger that does not exist yet is empty. The feed alone cannot tell:
    a request waits in the executor's inbox until its loop's next tick before pending_requests lists
    it, and leaves pending_requests once a plan has taken it"""
    path = path or LEDGER_PATH
    try:
        with open(path) as f:
            rows = [json.loads(x) for x in f if x.strip()]
        if not all(isinstance(r, dict) for r in rows):
            raise ValueError("a line is not a JSON object")
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        raise Refused(f"the transfer ledger cannot be read ({one_line(e, 120)}): whether this transfer was already "
                      f"sent today cannot be told. Check the executor's feed (pending_requests and today's session "
                      f"row) and pass --again only if the transfer is in neither") from None
    # an "intent" row is written BEFORE the POST and answered by the call's final row (same "call"):
    # an intent whose call HAS a final row is settled and is never itself a reason - the final row says
    # what happened (refused: nothing blocks; sent or unknown: that row blocks, and is the ONE row the
    # refusal names); an intent with NO final row (the process died after the POST) blocks like an unknown
    settled = {r["call"] for r in rows if isinstance(r.get("call"), str) and not r.get("intent")}
    return [r for r in rows if r.get("date") == day and r.get("book") == book and r.get("from") == src
            and r.get("to") == dst and r.get("outcome") in ("sent", "unknown") and not r.get("dry_run")
            and not (r.get("intent") and isinstance(r.get("call"), str) and r["call"] in settled)]


def transfer_url(base):
    """the transfer endpoint, or raises Refused: a token is only ever sent over https (or to localhost)"""
    base = (base or "").strip().rstrip("/")
    u = urllib.parse.urlparse(base)
    if u.scheme != "https" and not (u.scheme == "http" and (u.hostname or "") in LOCAL):
        raise Refused("MIRROR_EXECUTOR_URL must be https (a token is never sent over plain http)")
    return f"{base}/mirror/transfer"


def pick_book(feed, name):
    """(name, view) of the book to move in, or raises Refused. No name: the ONE book whose mode is live"""
    books = {k: v for k, v in (feed.get("books") or {}).items() if isinstance(v, dict)}
    if name is not None:
        if name not in books:
            raise Refused(f"the executor has no book {name!r} (it has: {', '.join(sorted(books)) or 'none'})")
        return name, books[name]
    live = sorted(k for k, v in books.items() if v.get("mode") == "live")
    if len(live) != 1:
        have = ", ".join(k + " " + str(books[k].get("mode")) for k in sorted(books)) or "none"
        raise Refused(("the executor has no live book" if not live else f"the executor has {len(live)} live books")
                      + f" (books: {have}); name one with --book if a paper book is meant")
    return live[0], books[live[0]]


def sleeve_equity(view, src, dst):
    """the FROM sleeve's equity in this book, or raises Refused: both sleeves there, neither frozen"""
    sleeves = ((view.get("book") or {}).get("sleeves")) or {}
    for s in (src, dst):
        row = sleeves.get(s)
        if not isinstance(row, dict):
            raise Refused(f"the book has no sleeve {s} (it holds: {', '.join(sorted(sleeves)) or 'none'}): "
                          f"no mirror leg is possible in this book")
        if row.get("frozen"):
            raise Refused(f"the sleeve {s} is frozen on the executor")
    eq = sleeves[src].get("equity")
    if not isinstance(eq, (int, float)) or isinstance(eq, bool) or not math.isfinite(eq) or eq <= 0:
        raise Refused(f"the sleeve {src} has no usable equity on the executor ({eq!r})")
    return float(eq)


def post(url, token, body, timeout=TIMEOUT_S):
    """(HTTP status, the answer's JSON object, or None when it is not one). A redirect is never
    followed: the token would be re-sent to wherever it points (its 3xx is the status)"""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Transfer-Token": token,
                                          "user-agent": "composer-mirror-transfer/1.0"})
    try:
        with mp.urlopen_no_redirect(req, timeout=timeout) as r:
            code, text = r.status, r.read()
    except urllib.error.HTTPError as e:
        with e:
            code, text = e.code, e.read()
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    return code, data if isinstance(data, dict) else None


def append_ledger(row, path=None):
    path = path or LEDGER_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lead = ""
    try:                                       # a ledger left without its last newline: never write onto that line
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            lead = "" if f.read(1) == b"\n" else "\n"
    except (FileNotFoundError, OSError):
        pass
    with open(path, "a") as f:
        f.write(lead + json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


class ledger_lock:
    """one transfer run at a time on this machine (flock on <ledger>.lock): the check of the ledger and
    the intent row that follows it are one step, so two runs started together cannot both send"""

    def __init__(self, path=None):
        self.path = (path or LEDGER_PATH) + ".lock"

    def __enter__(self):
        import fcntl
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.f = open(self.path, "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl
        try:
            fcntl.flock(self.f, fcntl.LOCK_UN)
        finally:
            self.f.close()
        return False


def run(argv=None, env=None, fetch=None, send=None, now=None, ledger_path=None):
    """(exit code, the summary line). fetch(url, read_token) -> feed and send(url, token, body) ->
    (status, dict, or None for an answer that is not a JSON object) are the test seams; the ledger row
    is written whatever the outcome"""
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    now = now or datetime.datetime.now(datetime.timezone.utc)
    day = mp.sr.et_now(now).date().isoformat()
    secrets_ = [t for t in (env.get("MIRROR_TRANSFER_TOKEN", ""), env.get("MIRROR_READ_TOKEN", "")) if t]

    def clean(text, n=300):
        text = str(text)
        for t in secrets_:
            text = text.replace(t, "***")
        return one_line(text, n)

    locked = []
    led = {"call": os.urandom(6).hex(), "date": day, "utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "from": None, "to": None, "book": None,
           "composer_amount": None, "composer_from_value": None, "fraction": None, "sleeve_equity": None,
           "amount": None, "outcome": None, "request_id": None, "dry_run": False}
    head = f"MIRROR TRANSFER {day}"
    code = 1
    try:
        a = parse(argv)
        src, dst = a.src.strip().upper(), a.dst.strip().upper()
        led.update({"from": src, "to": dst, "composer_amount": a.composer_amount,
                    "composer_from_value": a.composer_from_value, "dry_run": bool(a.dry_run), "book": a.book})
        head = f"MIRROR TRANSFER {day} {src} -> {dst}"
        if not src or not dst or src == dst:
            raise Refused("--from and --to must be two different engines")
        frac = fraction_of(a.composer_amount, a.composer_from_value)
        led["fraction"] = round(frac, 10)
        if a.composer_from_value_after is not None:
            led["composer_from_value_after"] = a.composer_from_value_after
            check_after(a.composer_amount, a.composer_from_value, a.composer_from_value_after)
        url = transfer_url(env.get("MIRROR_EXECUTOR_URL", ""))
        read_token, token = env.get("MIRROR_READ_TOKEN", ""), env.get("MIRROR_TRANSFER_TOKEN", "")
        if not read_token:
            raise Refused("MIRROR_READ_TOKEN not set")
        if not token and not a.dry_run:
            raise Refused("MIRROR_TRANSFER_TOKEN not set")
        try:
            feed = (fetch or (lambda u, t: mp.fetch_feed(u, t, history=0)))(env.get("MIRROR_EXECUTOR_URL", ""), read_token)
        except Exception as e:  # noqa: BLE001
            raise Refused(f"the executor's feed could not be read ({clean(e, 160)})") from None
        if not isinstance(feed, dict):
            raise Refused("the executor's feed is not a feed")
        name, view = pick_book(feed, a.book)
        led["book"] = name
        eq = sleeve_equity(view, src, dst)
        amount = round(frac * eq, 2)
        led.update({"sleeve_equity": eq, "amount": amount})
        what = (f"Composer moved ${a.composer_amount:,.2f} of ${a.composer_from_value:,.2f} ({frac:.4%}); the mirror's "
                f"{src} sleeve (book {name}) is ${eq:,.2f}: ${amount:,.2f}")
        pending = credits_queued(view, src, dst)
        if pending:
            raise Refused(f"{what} | NOT SENT: operator credit(s) are queued on the executor for "
                          + "; ".join(f"{r.get('sleeve')} "
                                      + (f"${r['amount']:,.2f}" if isinstance(r.get("amount"), (int, float))
                                         and not isinstance(r.get("amount"), bool) else repr(r.get("amount")))
                                      + f" as {r.get('id') or '?'}" for r in pending[:4])
                          + f" - the {src} sleeve's equity is pre-credit: {CREDITS_NEXT}")
        if amount < MIN_AMOUNT:
            led["outcome"] = "below_min"
            code, line = 0, f"{head}: {what} is below $1 at the mirror's size — nothing sent"
        else:
            note = one_line(a.note, 200) if a.note else one_line(
                f"POLICY mirror leg {day}: Composer {src} -> {dst} ${a.composer_amount:,.2f} of "
                f"${a.composer_from_value:,.2f} ({frac:.4%})", 200)
            body = {"from": src, "to": dst, "amount": amount, "note": note, "book": name}
            held = queued_already(view, src, dst)
            if held and not a.again:
                led["outcome"] = "duplicate"
                raise Refused(f"{what} | NOT SENT: a transfer for this pair is already queued on the executor ("
                              + "; ".join(f"${r['amount']:,.2f} as {r.get('id') or '?'}" if isinstance(r.get("amount"), (int, float))
                                          else f"{r.get('amount')!r} as {r.get('id') or '?'}" for r in held[:3])
                              + "). Pass --again only if a second move of the same pair is meant")
            lock = ledger_lock(ledger_path)
            try:
                lock.__enter__()
            except Exception as e:  # noqa: BLE001  a refusal with its line, never a traceback
                raise Refused(f"{what} | NOT SENT: the transfer ledger cannot be locked ({clean(e, 120)}), so "
                              f"whether this transfer was already sent cannot be told") from None
            locked.append(lock)
            if not a.again:
                try:
                    mine = sent_already(ledger_path, day, name, src, dst)
                except Refused:
                    led["outcome"] = "duplicate"
                    raise
                if mine:
                    led["outcome"] = "duplicate"
                    raise Refused(f"{what} | NOT SENT: this script's ledger already has this pair for {day} in book "
                                  f"{name} (" + "; ".join(f"{r.get('outcome')} at {r.get('utc') or '?'}"
                                                         + (f" as {r['request_id']}" if r.get("request_id") else "")
                                                         for r in mine[:3])
                                  + "). Read the executor's feed (pending_requests and today's session row); pass "
                                    "--again only if that transfer is in neither, or a second move of the pair is meant")
            if a.dry_run:
                led["outcome"] = "dry_run"
                code, line = 0, f"{head}: {what} | dry run: not sent; would POST {json.dumps(body, sort_keys=True)}"
            else:
                # T3 D2: the intent is on disk BEFORE the token leaves. A run killed after the POST, or
                # one whose final row cannot be written, still leaves a row that blocks the re-run.
                try:
                    append_ledger(dict(led, outcome="unknown", intent=True,
                                       why="written before the POST; the call's final row follows"), ledger_path)
                except Exception as e:  # noqa: BLE001
                    raise Refused(f"{what} | NOT SENT: the transfer ledger cannot be written ({clean(e, 120)}), so "
                                  f"a re-run could not tell this transfer had been sent") from None
                try:
                    status, data = (send or post)(url, token, body)
                except Exception as e:  # noqa: BLE001
                    led["outcome"] = "unknown"
                    raise Refused(f"{what} | the POST failed ({clean(e, 160)}): UNKNOWN whether the executor queued it — "
                                  f"{UNKNOWN_NEXT}") from None
                said = data if isinstance(data, dict) else {}
                if 300 <= status < 400:
                    raise Refused(f"{what} | NOT QUEUED (HTTP {status}: the executor's URL answered with a redirect, "
                                  f"which is never followed with the token; fix MIRROR_EXECUTOR_URL)")
                if 400 <= status < 500 and isinstance(data, dict):
                    raise Refused(f"{what} | NOT QUEUED (HTTP {status}: "
                                  f"{clean(said.get('detail') or said.get('error') or 'no reason given')})")
                if status != 200 or not said.get("ok"):
                    led["outcome"] = "unknown"
                    raise Refused(f"{what} | HTTP {status} "
                                  + ("without \"ok\"" if isinstance(data, dict) else "and an answer that is not JSON")
                                  + f": UNKNOWN whether the executor queued it — {UNKNOWN_NEXT}")
                data = said
                req = data.get("request") if isinstance(data.get("request"), dict) else {}
                led.update({"outcome": "sent", "request_id": req.get("id")})
                code, line = 0, (f"{head}: {what} queued as {req.get('id') or '?'}; the executor applies it at the "
                                 f"mirror's next session (today's if this is before about 15:54 ET on a session day, "
                                 f"otherwise the next trading day's)")
    except Refused as e:
        led["outcome"] = led["outcome"] or "refused"
        led["why"] = clean(e)
        code, line = 1, f"{head}: REFUSED — {clean(e, 600)}"
    try:
        append_ledger(led, ledger_path)
    except Exception as e:  # noqa: BLE001
        line += f" | the ledger row was NOT written ({clean(e, 120)})"
        code = 1                               # T3 D2: never a clean exit without the record
    finally:
        for lock in locked:
            lock.__exit__(None, None, None)
    return code, line


def main():
    code, line = run()
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
