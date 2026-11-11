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
             never a token), or a redirect (never followed: the token goes to the one host only)
  duplicate  the book's pending_requests already hold a transfer by this token for the same from/to:
             nothing is sent unless --again says a second move of the pair is meant
  unknown    the request left and what came back does not say whether it was queued (a 5xx, an answer
             that is not JSON, a 200 without "ok", a timeout, a dropped connection): check
             pending_requests before re-sending - and running this again does exactly that (it sends
             only when the executor does not hold the transfer)

The executor applies a queued move with its NEXT session's plan (15:54 ET on the next trading day).
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
                   help="send although a transfer by this token for the same from/to is already queued")
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
    with open(path, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


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

    led = {"date": day, "utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "from": None, "to": None, "book": None,
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
            if a.dry_run:
                led["outcome"] = "dry_run"
                code, line = 0, f"{head}: {what} | dry run: not sent; would POST {json.dumps(body, sort_keys=True)}"
            else:
                try:
                    status, data = (send or post)(url, token, body)
                except Exception as e:  # noqa: BLE001
                    led["outcome"] = "unknown"
                    raise Refused(f"{what} | the POST failed ({clean(e, 160)}): UNKNOWN whether the executor queued it — "
                                  f"check pending_requests before re-sending (running this again does: it sends only "
                                  f"when the executor does not hold the transfer)") from None
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
                                  + ": UNKNOWN whether the executor queued it — check pending_requests before re-sending "
                                    "(running this again does: it sends only when the executor does not hold the transfer)")
                data = said
                req = data.get("request") if isinstance(data.get("request"), dict) else {}
                led.update({"outcome": "sent", "request_id": req.get("id")})
                code, line = 0, (f"{head}: {what} queued as {req.get('id') or '?'}; the executor applies it with its "
                                 f"NEXT session's plan (15:54 ET on the next trading day)")
    except Refused as e:
        led["outcome"] = led["outcome"] or "refused"
        led["why"] = clean(e)
        code, line = 1, f"{head}: REFUSED — {clean(e, 600)}"
    try:
        append_ledger(led, ledger_path)
    except Exception as e:  # noqa: BLE001
        line += f" | the ledger row was NOT written ({clean(e, 120)})"
    return code, line


def main():
    code, line = run()
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
