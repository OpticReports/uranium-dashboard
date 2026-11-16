"""Gate tests for mirror_scale.py: the read-only planner that scales the IBKR mirror's live book at
Composer's split (no network but 127.0.0.1: the feed is injected, the snapshot is a temporary file, the
pasted line runs against a real HTTP server on this machine).

  S1  the arithmetic: weights from the four engines' values only (unallocated cash and other
      symphonies left out); target = round(to x weight, 2), credit = round(target - equity, 2); the
      credits sum to to - the book's equity within cents, and the plan says what rounding leaves
  S2  Composer's snapshot: refused when an engine is missing or its value is not a positive number,
      when the file is unreadable or not a snapshot, when taken_at cannot be read; more than 3 ET
      calendar days old is a WARNING naming its date, never a refusal; the ids are the approved manifest's
  S3  the book: the one live book; none or two are refused, never guessed; --book names one; a paper
      book or an unknown one is refused
  S4  health: halted, a flatten pending, an open run, unresolved orders, last_error, queued requests
      (named), a latched save, an archived state, an account check with problems, a sleeve missing /
      frozen / unvalued / extra, a book equity that does not add up: each refused, all named at once;
      what does not stop a scale-up (dividends open, a finished flatten's record, waiting_on) does not
  S5  the plan's refusals: --to not above the book; a negative credit names the smallest --to (and it
      is the smallest); a slipped zero; bad numbers; missing env; the read token only over https; a
      feed that cannot be read (no token in the line); nothing to send
  S6  the cap: funded estimate (seeds + operator credits in the session rows, de-duplicated; dividends
      and debits not counted; a published funded_usd wins); need x (1 + headroom) rounded UP to the
      next $500; against the executor's _over_cap semantics (smallest first, cumulative, cap + $1):
      every credit passes at the printed cap, the largest is the one refused just under the need; the
      executor's lines this relies on are pinned in its source, each pin unique there (item 11)
  S7  the pasted line's mechanics against a real HTTP server on 127.0.0.1: each credit POSTed with the
      X-Exec-Token header and the four fields, each answer printed, ALL QUEUED, exit 0; no token anywhere
  S8  --json: the same plan as JSON; a refusal is still the one line
  S9  read-only: the planner reads only MIRROR_EXECUTOR_URL and MIRROR_READ_TOKEN from the env (never
      EXEC_TOKEN), opens no connection but the feed read (fetch_feed, full history), writes no file
  S10 the output: the steps in order with the cap, the deploy blackout and the half-days; the doc
      has "Scaling the live book" with the owner's gates, the steps and the line's rules
  The second review's items (each gate failed at 6b122160):
  L1  item 1, SECURITY: the line sends EXEC_TOKEN to the executor in its own container only -
      http://127.0.0.1:$PORT (start.sh's ${PORT:-8000}) - never to MIRROR_EXECUTOR_URL; no proxy from the
      env is used and a redirect is never followed (both: a trap server receives nothing)
  L2  item 2: plain python3 and the standard library only (no httpx, no venv path); ONE physical line
      that compiles, fits a terminal line, and runs as printed under bash and sh
  L3  item 3: NOTHING SENT while ANY request is queued - the state's requests or the inbox, any kind -
      each one listed; an inbox that cannot be read sends nothing
  L4  item 4: NOTHING SENT on a weekday from 15:00 ET (12:00 on a half-day), with the reason; any time on
      a weekend is fine; the line expires at its session's cutoff; the windows across a DST change and
      without a tz database; the session the plan is for
  L5  item 5: the cap in integer cents with no $1 slack; MIRROR_MAX_BOOK_USD missing, not a number, not
      finite or not above 0 sends nothing and says what it means; funded_usd unusable sends nothing
  L6  item 6: each POST guarded: at the first error or answer that is not 200 it STOPS at once, exit 2,
      naming what answered 200, that the one not answered may have been queued, what was not sent, and
      to re-run the planner after the session; a re-paste then sends nothing (L3)
  P7  item 7: the planner refuses unless the post-trade check is of the last session, done, no problem
  P8  item 8: the cash minimum counts the dividend receivables due by the session and a margin of
      max($100, 0.5% of the credits); the one sentence about a $1 shortfall
  P9  item 9: malformed input is a refusal or a warning, never a traceback
  P10 item 10: the landing sentence
  The third review's items (each gate failed at 1de7535c; R11 and R12 are twins that pass there too):
  R0  pins: the executor's lines the new paste-time checks read (the state's book a LIST of named sleeve
      records, the frozen list, the halt file and its rules, the drain's order, the credit route's 4xx)
  R1  item 1(a): NOTHING SENT unless the post-trade check of the plan's last session is on record, done,
      with no problem (an applied /mirror/adjust clears it); twins: the plan's clean check sends
  R2  item 1(b): NOTHING SENT while <state>.halt says halted or a flatten is pending, or cannot be read or
      is not a record (a halt to the executor); twins: resumed, cancelled, finished, absent send
  R3  item 1(c): NOTHING SENT while a run is open
  R4  item 1(d): NOTHING SENT when a sleeve it credits is frozen or not in the book; twin: a frozen sleeve it
      does not credit
  R5  item 2: the planner refuses on a session day from its paste cutoff while that day's session has not
      run ("today's session has not run yet: re-run after it and its post-trade check"), the half-day too;
      twins: before the cutoff, after the session, a holiday, a weekend
  R6  item 3: a dollar figure that is not finite or is beyond $1e9 (seeds, credit rows, funded_usd, book
      cash, due dividends, --to) is a one-line refusal, never a traceback or an absurd plan; twins: large
      but plausible figures plan
  R7  item 5: the inbox is read before the state: a drain between the two reads cannot hide a request
  R8  item 5: an EXEC_TOKEN that is not printable ASCII sends nothing and is never printed
  R9  item 5: an error is printed as its type and message with the token masked, never its repr
  R10 item 5: STOPPED says NOT queued for an HTTP 4xx or a refused connection (and "nothing is queued: fix
      the cause and paste this line again" when nothing is); twins: a 5xx, a redirect, no answer
  R11 item 5, the surviving mutants: a state named live whose live flag is false sends nothing; a dividend
      with no pay date exactly PAY_DATE_GIVE_UP_DAYS after its ex-date is in the cash minimum
  R12 the hard limit: the line fits a terminal line (4,095 bytes) over a 45-day sweep of plan times; the
      longest and its margin are printed
  R13 the doc says the new rules
  The fourth review's NOTEs (R16-R18 and R5's words: each gate failed at 170191c0; R14, R15 and the twins pass there):
  R14 (its V2, a mutation pin: kills P13) funded_usd near $1e9 plus credits beyond it is the one refusal line
  R15 (its V3, a mutation pin: kills L10) a post-trade check whose done is truthy but not True sends nothing
  R16 the plan-time refusal says "(if the executor missed today's session, re-run after midnight ET)"; R5
      reads its new words; twin: after midnight a missed day plans for the next session
  R17 step (a) changes MIRROR_MAX_BOOK_USD only, not MIRROR_LIVE_ENGINES (the plan, the doc, the docstring);
      twin: the executor's lines it rests on
  R18 re-run the planner after ANY /mirror/adjust (the plan's step (b), the doc, the docstring); twin: the
      executor's lines it rests on

Run: python3 -m unittest tests.test_mirror_scale -v   (from composer/scripts)
"""
import builtins
import contextlib
import datetime
import http.server
import io
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import mirror_scale as ms  # noqa: E402
import shadow_runner as sr  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
NOW = datetime.datetime(2026, 11, 12, 22, 0, tzinfo=datetime.timezone.utc)          # Thu 17:00 ET, after the session
UTC = datetime.timezone.utc
FRI_10 = datetime.datetime(2026, 11, 13, 15, 0, tzinfo=UTC).timestamp()            # Fri 10:00 ET: in the line's window
READ, EXEC = "read-token-BBBBBBBBBBBBBBBBBBBB", "exec-token-CANARY-never-read-by-the-planner"
ENV = {"MIRROR_EXECUTOR_URL": "https://exec.example", "MIRROR_READ_TOKEN": READ, "EXEC_TOKEN": EXEC}
IDS = {"HG": "mbkiXcuNDjueXpiox5Av", "KMLM": "YPTSJFJwD2ZKfAeYJUbW", "SLEEVE": "nNdBk7hc5NiBzeRvbI5T",
       "HARV": "ORQNCfZnA18wmsMWVhf8"}
VALUES = {"HG": 104838.5, "KMLM": 87396.31, "SLEEVE": 81791.0, "HARV": 38395.76}           # Composer, 2026-11-12
EQUITY = {"HG": 3429.2, "KMLM": 2645.67, "SLEEVE": 2649.66, "HARV": 1241.32}              # the live book, 11-12
CREDITS = {"HG": 13349.17, "KMLM": 11341.25, "SLEEVE": 10440.19, "HARV": 4903.54}         # at $50,000
RERUN = "re-run mirror_scale.py --to 50000"
WIDE = ((0, 3600 * 2 ** 28),)                                        # a paste window open now (whole hours from 0)


def snapshot(**over):
    snap = {"taken_at": "2026-11-12T21:36:58+00:00",
            "total_stats": {"total_unallocated_cash": 102.27, "portfolio_value": 312523.84},
            "symphonies": {IDS[e]: {"name": e, "value": v, "deposit_adjusted_value": v / 3, "holdings": {}}
                           for e, v in VALUES.items()}}
    snap["symphonies"]["SomeOtherSymphony00"] = {"name": "not an engine", "value": 999999.0}
    snap.update(over)
    return snap


def sleeve(eq, cash=30.0, frozen=False):
    return {"equity": eq, "cash": cash, "shares": {"BIL": 1}, "weights": {}, "rule": "daily", "frozen": frozen}


def view(**over):
    v = {"name": "live", "mode": "live", "engines": ["HG", "KMLM", "SLEEVE", "HARV"],
         "book": {"equity": 9965.85, "cash": 108.52, "positions": {}, "marks_asof": "2026-11-12T20:54:00Z",
                  "sleeves": {"HG": sleeve(3429.2, 43.61), "KMLM": sleeve(2645.67, 30.25),
                              "SLEEVE": sleeve(2649.66, 31.22), "HARV": sleeve(1241.32, 3.45)}},
         "seeded": {"HG": {"amount": 3430.0000000000005, "utc": "x"}, "KMLM": {"amount": 2680.0, "utc": "x"},
                    "SLEEVE": {"amount": 2650.0, "utc": "x"}, "HARV": {"amount": 1240.0, "utc": "x"}},
         "last_session": "2026-11-12", "run": None,
         "check": {"done": True, "problems": [], "session": "2026-11-12", "strikes": 0, "utc": "2026-11-12T20:59:48Z"},
         "pending_requests": [], "commission_pending": 0, "dividends_open": [], "unresolved": [],
         "save_latched": None, "settings_clamped": [], "flatten": None, "halt": {}, "waiting_on": None,
         "last_error": None, "brain": {}, "archived_state": None,
         "history": [{"session": "2026-11-11", "outcome": "traded", "credits": []},
                     {"session": "2026-11-12", "outcome": "traded", "credits": []}],
         "last_run": {"session": "2026-11-12", "outcome": "traded", "credits": []}}
    v.update(over)
    return v


def feed(**books):
    return {"schema": 1, "kind": "composer-mirror-feed", "utc": "2026-11-12T21:36:52Z", "books": books}


def et(y, mo, d, h, mi=0):
    """an ET wall-clock instant as UTC epoch seconds (the tz database)"""
    import zoneinfo
    return datetime.datetime(y, mo, d, h, mi, tzinfo=zoneinfo.ZoneInfo("America/New_York")).timestamp()


class RecordingEnv(dict):
    """an env that remembers every key the planner looked at"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seen = set()

    def get(self, key, default=None):
        self.seen.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.seen.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.seen.add(key)
        return super().__contains__(key)


class Executor:
    """the executor's POST /mirror/credit on 127.0.0.1: a real HTTP server on a real socket. It records every
    request it gets and answers from `answers` in turn ((status, body); "drop": the connection closed with no
    answer; ("redirect", url): a 302 there), 200 after the list. Like the executor's request_credit ->
    _enqueue, every credit it answers 200 is appended to the inbox file (when given one)"""

    def __init__(self, inbox=None):
        self.requests, self.answers, self.inbox = [], [], inbox
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                outer.answer(self)

            do_GET = do_PUT = do_CONNECT = do_POST

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def answer(self, h):
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n) if n else b""
        self.requests.append({"method": h.command, "path": h.path, "headers": dict(h.headers), "body": body})
        k = len(self.requests) - 1
        ans = self.answers[k] if k < len(self.answers) else (200, None)
        if ans == "drop":
            return                                     # HTTP/1.0: the connection closes, unanswered
        if ans[0] == "redirect":
            h.send_response(302)
            h.send_header("Location", ans[1])
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        status, text = ans
        req = json.loads(body or b"{}")
        row = {"kind": "credit", "sleeve": req.get("sleeve"), "amount": req.get("amount"), "note": req.get("note"),
               "force": False, "id": f"credit-1794520000000-{k}", "utc": "2026-11-13T15:00:00Z"}
        if status == 200 and self.inbox:
            box = []
            if os.path.exists(self.inbox):
                with open(self.inbox) as f:
                    box = json.load(f)
            with open(self.inbox, "w") as f:
                json.dump(box + [row], f)
        out = (text if text is not None else json.dumps({"ok": True, "book": "live", "request": row,
                                                          "note": "queued; applied before the next session's plan"}))
        data = out.encode()
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snap = snapshot()
        self.feed = feed(live=view())
        self.fetches = []

    def snap_path(self):
        path = os.path.join(self.tmp.name, "last-snapshot.json")
        with open(path, "w") as f:
            json.dump(self.snap, f)
        return path

    def fetch(self, url, token):
        self.fetches.append((url, token))
        if isinstance(self.feed, Exception):
            raise self.feed
        return self.feed

    def run_it(self, *extra, to="50000", env=ENV, now=NOW):
        argv = ["--to", to, "--snapshot", self.snap_path()] + list(extra)
        return ms.run(argv, env=env if isinstance(env, RecordingEnv) else dict(env), fetch=self.fetch, now=now)

    def plan(self, *extra, **kw):
        code, text = self.run_it("--json", *extra, **kw)
        self.assertEqual(code, 0, text)
        return json.loads(text)

    def refused(self, *extra, **kw):
        code, text = self.run_it(*extra, **kw)
        self.assertEqual(code, 1, text)
        self.assertTrue(text.startswith("MIRROR SCALE REFUSED"), text)
        self.assertNotIn("\n", text)
        return text

    def live(self):
        return self.feed["books"]["live"]


# ------------------------------------------------------------------ S1 the arithmetic
class S1Arithmetic(Case):
    def test_weights_are_the_four_engines_values_over_their_sum_only(self):
        p = self.plan()
        total = sum(VALUES.values())
        for r in p["engines"]:
            self.assertEqual(r["symphony"], IDS[r["engine"]])
            self.assertAlmostEqual(r["weight"], VALUES[r["engine"]] / total, places=6)
            self.assertEqual(r["composer_value"], VALUES[r["engine"]])
        self.assertEqual([r["engine"] for r in p["engines"]], ["HG", "KMLM", "SLEEVE", "HARV"])
        self.assertAlmostEqual(sum(r["weight"] for r in p["engines"]), 1.0, places=5)
        self.assertEqual(p["total"]["composer_value"], round(total, 2))      # the other symphony and the cash: out

    def test_target_and_credit_are_rounded_as_specified(self):
        p = self.plan()
        total = sum(VALUES.values())
        for r in p["engines"]:
            e = r["engine"]
            self.assertEqual(r["target"], round(50000 * (VALUES[e] / total), 2))
            self.assertEqual(r["credit"], round(r["target"] - EQUITY[e], 2))
            self.assertEqual(r["equity"], EQUITY[e])
        self.assertEqual({r["engine"]: r["credit"] for r in p["engines"]}, CREDITS)
        self.assertEqual(p["total"]["credit"], 40034.15)
        self.assertEqual(p["residual"], 0.0)
        self.assertEqual(p["total"]["target"], 50000.0)

    def test_the_credits_sum_to_to_minus_the_book_within_cents_and_the_plan_says_what_rounding_leaves(self):
        code, text = self.run_it(to="50000.02")
        self.assertEqual(code, 0, text)
        self.assertIn("rounding each target and equity to cents adds $0.01", text)
        p = self.plan(to="50000.02")
        self.assertEqual(p["residual"], -0.01)
        self.assertEqual(round(p["to"] - p["total"]["book_equity"] - p["total"]["credit"], 2), p["residual"])
        self.assertIn("exactly", self.run_it()[1])

    def test_rounding_never_leaves_more_than_a_few_cents(self):
        rnd = random.Random(20261112)
        done = 0
        while done < 300:
            raw = {e: rnd.uniform(200, 9000) for e in EQUITY}
            v = view()
            for e, x in raw.items():
                v["book"]["sleeves"][e]["equity"] = round(x, 2)
            v["book"]["equity"] = round(sum(raw.values()), 2)                    # the executor rounds the SUM
            vals = {e: rnd.uniform(1000, 200000) for e in VALUES}
            w = {e: vals[e] / sum(vals.values()) for e in vals}
            lo = ms.smallest_to(w, {e: round(x, 2) for e, x in raw.items()}, v["book"]["equity"])
            if lo is None or lo >= 9 * v["book"]["equity"]:
                continue                                                         # no plan inside the 10x bound
            done += 1
            to = round(rnd.uniform(lo, 9 * v["book"]["equity"]), 2)
            for e, x in vals.items():
                self.snap["symphonies"][IDS[e]]["value"] = x
            self.feed = feed(live=v)
            p = self.plan(to=repr(to))
            self.assertLessEqual(abs(p["residual"]), 0.05, p)
            self.assertEqual(round(to - p["total"]["book_equity"] - p["total"]["credit"], 2), p["residual"])
            self.assertTrue(all(r["credit"] >= 0 for r in p["engines"]))

    def test_the_text_has_the_table_and_the_total(self):
        code, text = self.run_it()
        self.assertEqual(code, 0, text)
        self.assertTrue(text.startswith("MIRROR SCALE PLAN — book live: $9,965.85 -> $50,000.00 (x5.02) at Composer's "
                                        "split of 2026-11-12, for the session of 2026-11-13"), text[:200])
        for e, c in CREDITS.items():
            row = next(x for x in text.splitlines() if x.startswith(e + " "))
            self.assertIn(f"${c:,.2f}", row)
            self.assertIn(f"${EQUITY[e]:,.2f}", row)
            self.assertIn(f"${VALUES[e]:,.2f}", row)
        tot = next(x for x in text.splitlines() if x.startswith("total"))
        for s in ("$312,421.57", "100.000%", "$9,965.85", "$50,000.00", "$40,034.15"):
            self.assertIn(s, tot)


# ------------------------------------------------------------------ S2 Composer's snapshot
class S2Snapshot(Case):
    def test_a_missing_engine_is_refused(self):
        del self.snap["symphonies"][IDS["HARV"]]
        line = self.refused()
        self.assertIn("HARV (ORQNCfZnA18wmsMWVhf8): missing", line)
        self.assertEqual(self.fetches, [])                 # refused before the executor is asked anything

    def test_a_value_that_is_not_a_positive_number_is_refused(self):
        for bad in (0, -5.0, None, "104838.5", True, float("nan"), float("inf")):
            with self.subTest(value=bad):
                self.snap = snapshot()
                self.snap["symphonies"][IDS["KMLM"]]["value"] = bad
                self.assertIn("KMLM (YPTSJFJwD2ZKfAeYJUbW): value", self.refused())

    def test_a_file_that_is_not_there_or_not_a_snapshot_is_refused(self):
        line = ms.run(["--to", "50000", "--snapshot", os.path.join(self.tmp.name, "nope.json")], env=dict(ENV),
                      fetch=self.fetch, now=NOW)[1]
        self.assertIn("is not there", line)
        path = os.path.join(self.tmp.name, "bad.json")
        for content in ("{not json", "[]", json.dumps({"taken_at": "2026-11-12T21:36:58+00:00"})):
            with open(path, "w") as f:
                f.write(content)
            code, line = ms.run(["--to", "50000", "--snapshot", path], env=dict(ENV), fetch=self.fetch, now=NOW)
            self.assertEqual(code, 1)
            self.assertTrue(line.startswith("MIRROR SCALE REFUSED"), line)
        self.assertEqual(self.fetches, [])

    def test_a_taken_at_that_cannot_be_read_is_refused(self):
        for bad in (None, "", "yesterday", 1731446218):
            with self.subTest(taken_at=bad):
                self.snap = snapshot(taken_at=bad)
                self.assertIn("no readable taken_at", self.refused())

    def test_older_than_three_days_is_a_warning_with_its_date_never_a_refusal(self):
        self.snap = snapshot(taken_at="2026-11-08T21:36:58+00:00")
        p = self.plan()
        self.assertEqual(p["snapshot"]["age_days"], 4)
        self.assertTrue(any("4 days old" in w and "2026-11-08" in w for w in p["warnings"]), p["warnings"])
        code, text = self.run_it()
        self.assertEqual(code, 0)
        self.assertIn("WARNING: Composer's snapshot is 4 days old (taken 2026-11-08", text)
        self.assertIn("at Composer's split of 2026-11-08", text)
        self.snap = snapshot(taken_at="2026-11-09T21:36:58+00:00")               # exactly 3: no warning
        self.assertFalse([w for w in self.plan()["warnings"] if "days old" in w])

    def test_the_date_is_the_et_date_and_the_note_carries_it(self):
        self.snap = snapshot(taken_at="2026-11-13T01:30:00Z")                    # 20:30 ET on the 12th
        p = self.plan()
        self.assertEqual(p["snapshot"]["date"], "2026-11-12")
        self.assertEqual(p["note"], "scale-up to $50,000 at Composer's split of 2026-11-12")

    def test_a_snapshot_dated_in_the_future_is_warned(self):
        self.snap = snapshot(taken_at="2026-11-20T21:00:00+00:00")
        self.assertTrue(any("in the future" in w for w in self.plan()["warnings"]))

    def test_the_engines_are_the_approved_manifests(self):
        manifest = sr.load_manifest()
        self.assertEqual([e for e, _ in ms.ENGINES], list(sr.ORDER))
        self.assertEqual(dict(ms.ENGINES), {e: manifest[e]["symphony"] for e in sr.ORDER})
        self.assertEqual(dict(ms.ENGINES), IDS)

    def test_the_default_snapshot_is_the_monitors(self):
        self.assertEqual(os.path.abspath(ms.SNAPSHOT),
                         os.path.join(REPO, "composer", "results", "monitor", "last-snapshot.json"))


# ------------------------------------------------------------------ S3 the book
class S3Book(Case):
    def test_no_live_book_is_refused_never_guessed(self):
        self.feed = feed(dry=view(name="dry", mode="paper"))
        self.assertIn("the executor has no live book (books: dry (paper))", self.refused())

    def test_two_live_books_are_refused_unless_one_is_named(self):
        self.feed = feed(live=view(), other=view(name="other"))
        self.assertIn("the executor has 2 live books", self.refused())
        self.assertEqual(self.plan("--book", "live")["book"], "live")

    def test_the_live_book_is_found_beside_a_paper_book(self):
        self.feed = feed(live=view(), dry=view(name="dry", mode="paper"))
        self.assertEqual(self.plan()["book"], "live")

    def test_a_paper_or_unknown_book_is_refused(self):
        self.feed = feed(live=view(), dry=view(name="dry", mode="paper"))
        self.assertIn("is 'paper', not live", self.refused("--book", "dry"))
        self.assertIn("no book 'nope'", self.refused("--book", "nope"))

    def test_a_view_the_executor_could_not_build_is_refused(self):
        self.feed = feed(live={"name": "live", "error": "KeyError('book')"})
        self.assertIn("could not build book live's view", self.refused("--book", "live"))


# ------------------------------------------------------------------ S4 health
class S4Health(Case):
    CASES = (
        ("halt", {"halted": True, "reason": "operator halt", "by": "operator", "ts": "2026-11-12T15:00:00Z"},
         "it is HALTED (operator halt; by operator"),
        ("halt", {"halted": False, "flatten": True, "flatten_done": False}, "a flatten is in progress"),
        ("run", {"session": "2026-11-13", "phase": "buys", "orders": {}}, "a run is open (session 2026-11-13, phase buys)"),
        ("unresolved", [{"id": "mirror-2026-11-12-B-BIL", "symbol": "BIL"}], "1 order(s) unresolved (mirror-2026-11-12-B-BIL)"),
        ("last_error", "ConnectionError('gateway')", "its last tick failed: ConnectionError('gateway')"),
        ("pending_requests", [{"kind": "credit", "sleeve": "HG", "amount": 100.0, "id": "credit-1"}],
         "1 request(s) queued and not yet applied: credit HG $100.00 (credit-1)"),
        ("pending_requests", [{"kind": "transfer", "from": "HG", "to": "SLEEVE", "amount": 138.32, "id": "transfer-1",
                               "via": "transfer_token"}], "transfer HG -> SLEEVE $138.32 (transfer-1)"),
        ("pending_requests", [{"kind": "adjust", "sleeve": "KMLM", "shares": 1, "cash": 0.0, "id": "adjust-1"}],
         "adjust KMLM (adjust-1)"),
        ("save_latched", {"since": "2026-11-12T15:00:00Z", "error": "disk full"}, "a state save failed and the book is latched"),
        ("archived_state", "mirror[live] state file unreadable", "its state file was archived"),
        ("check", {"done": False, "problems": ["BIL: book 37, account 36"], "session": "2026-11-12", "strikes": 1},
         "the account does not hold the book (check of 2026-11-12): BIL: book 37, account 36"),
    )

    def test_each_unhealthy_state_is_refused_and_named(self):
        for key, value, words in self.CASES:
            with self.subTest(key=key, value=value):
                self.feed = feed(live=view(**{key: value}))
                line = self.refused()
                self.assertIn("book live is not in a state to scale", line)
                self.assertIn(words, line)

    def test_every_problem_is_named_at_once(self):
        self.feed = feed(live=view(halt={"halted": True, "reason": "x"}, last_error="boom",
                                   pending_requests=[{"kind": "credit", "sleeve": "HG", "amount": 5.0, "id": "c"}]))
        line = self.refused()
        for words in ("HALTED", "last tick failed: boom", "1 request(s) queued"):
            self.assertIn(words, line)

    def test_sleeves_missing_frozen_unvalued_or_extra_are_refused(self):
        v = view()
        del v["book"]["sleeves"]["KMLM"]
        self.feed = feed(live=v)
        self.assertIn("the book has no sleeve KMLM", self.refused())
        v = view()
        v["book"]["sleeves"]["HARV"]["frozen"] = True
        self.feed = feed(live=v)
        self.assertIn("the sleeve HARV is frozen", self.refused())
        for bad in (None, 0.0, -1.0, "3429.2", True):
            with self.subTest(equity=bad):
                v = view()
                v["book"]["sleeves"]["HG"]["equity"] = bad
                self.feed = feed(live=v)
                self.assertIn("the sleeve HG has no usable equity", self.refused())
        v = view()
        v["book"]["sleeves"]["GOLD"] = sleeve(10.0)
        v["book"]["equity"] = 9975.85
        self.feed = feed(live=v)
        self.assertIn("the book also holds GOLD", self.refused())

    def test_a_book_equity_that_does_not_add_up_is_refused(self):
        v = view()
        v["book"]["equity"] = 9965.95                                    # 10 cents off the four sleeves' sum
        self.feed = feed(live=v)
        self.assertIn("is not its four sleeves'", self.refused())
        v["book"]["equity"] = 9965.88                                    # 3 cents: the cents each is rounded to
        self.assertEqual(self.plan()["total"]["book_equity"], 9965.88)
        v["book"]["equity"] = None
        self.assertIn("the book has no usable equity", self.refused())

    def test_what_does_not_stop_a_scale_up_does_not(self):
        self.feed = feed(live=view(
            dividends_open=[{"id": "d1", "status": "open", "sleeve": "HG", "ticker": "BIL", "ex_date": "2026-11-12",
                             "pay_date": "2026-12-01", "shares": 37, "amount": 0.3, "total": 11.1}],
            commission_pending=2, waiting_on="the decision at 15:54",
            settings_clamped=["quote_band 0.2 -> 0.05"], brain={"session": {"ok": False}},
            flatten={"id": "20261111T150000", "round": 2, "orders": []},            # a finished flatten's record
            halt={"halted": False, "flatten": True, "flatten_done": True, "resumed_ts": "x"}))
        p = self.plan()
        self.assertIn("the account held the book at the post-trade check of 2026-11-12 (done, no problem)", p["health"])
        self.feed = feed(live=view(halt={"halted": False, "flatten": True, "flatten_done": False,
                                         "flatten_cancelled": True}))
        self.assertEqual(self.plan()["book"], "live")                            # a cancelled flatten (resumed)


# ------------------------------------------------------------------ P7 the post-trade check (item 7)
class P7PostTradeCheck(Case):
    """the account's post-trade check (mirror.py _post_check) must be the LAST session's, done, with no
    problem. At 6b122160 a missing or stale check passed, and the plan said the account held the book"""

    def test_a_missing_stale_or_unfinished_check_is_refused_and_says_when_to_re_run(self):
        cases = (
            (None, "the account has not been checked against the book since its last session 2026-11-12 (the "
                   "post-trade check is not on the feed)"),
            ("done", "the post-trade check is not a record: 'done'"),
            ({"done": True, "problems": [], "session": "2026-11-11", "strikes": 0},
             "the last post-trade check is of 2026-11-11, not of the book's last session 2026-11-12"),
            ({"done": False, "problems": [], "session": "2026-11-12", "strikes": 0},
             "the post-trade check of 2026-11-12 is not done (done False)"),
            ({"problems": [], "session": "2026-11-12"}, "the post-trade check of 2026-11-12 is not done (done None)"),
            ({"done": True, "problems": ["BIL: book 37, account 36"], "session": "2026-11-12", "strikes": 2},
             "the account does not hold the book (check of 2026-11-12): BIL: book 37, account 36"),
            ({"done": True, "problems": "BOXX off", "session": "2026-11-12"},
             "the account does not hold the book (check of 2026-11-12): BOXX off"),
        )
        for chk, words in cases:
            with self.subTest(check=chk):
                self.feed = feed(live=view(check=chk))
                line = self.refused()
                self.assertIn("book live is not in a state to scale", line)
                self.assertIn(words, line)
                self.assertIn("re-run this planner after the next session's post-trade check", line)

    def test_the_check_of_the_last_session_done_and_clean_passes_and_the_health_says_so(self):
        for chk in ({"done": True, "problems": [], "session": "2026-11-12", "strikes": 0},
                    {"done": True, "session": "2026-11-12"},
                    {"done": True, "problems": None, "session": "2026-11-12"}):
            with self.subTest(check=chk):
                self.feed = feed(live=view(check=chk))
                self.assertIn("post-trade check of 2026-11-12 (done, no problem)", self.plan()["health"])

    def test_the_executor_still_clears_and_makes_the_check_as_the_refusal_says(self):
        with open(os.path.join(REPO, "ibkr-executor", "app", "mirror.py")) as f:
            src = " ".join(f.read().split())
        for text in ('self.state["run"] = None self.state["check"] = None',          # _finish: every run's end
                     's.cash += cash self.state["check"] = None',                     # _adjust
                     'chk = {"session": session, "utc": _iso(now), "strikes": strikes, "problems": probs[:8], '
                     '"done": not probs or strikes >= CHECK_STRIKES}',
                     'if self.state.get("last_session") == session: self._post_check(ad, session, wake)',
                     '"last_run": self.state.get("last_run"), "check": self.state.get("check"),'):
            self.assertEqual(src.count(text), 1, text)


# ------------------------------------------------------------------ S5 the plan's refusals
class S5PlanRefusals(Case):
    def test_to_not_above_the_book_is_refused(self):
        for to in ("9965.85", "9000"):
            with self.subTest(to=to):
                self.assertIn("is not above it (this planner only scales up)", self.refused(to=to))

    def test_a_negative_credit_names_the_smallest_to_and_it_is_the_smallest(self):
        line = self.refused(to="10100")
        self.assertIn("HG is already above its Composer share (target $3,389.23, equity $3,429.20)", line)
        low = float(re.search(r"the smallest --to at which every credit is >= 0 is ([0-9.]+)", line).group(1))
        self.assertEqual(low, 10219.10)          # HG: round(10219.10 x weight, 2) = $3,429.20, its equity: credit $0
        p = self.plan(to=f"{low:.2f}")
        self.assertTrue(all(r["credit"] >= 0 for r in p["engines"]), p["engines"])
        self.assertIn("already above its Composer share", self.refused(to=f"{low - 0.01:.2f}"))

    def test_the_smallest_to_is_the_smallest_on_random_books(self):
        rnd = random.Random(7)
        beyond = 0
        for _ in range(300):
            eq = {e: round(rnd.uniform(200, 9000), 2) for e in EQUITY}
            vals = {e: rnd.uniform(1000, 200000) for e in VALUES}
            w = {e: vals[e] / sum(vals.values()) for e in vals}
            book = round(sum(eq.values()), 2)
            lo = ms.smallest_to(w, eq, book)
            if lo is None:                       # beyond 10x the book: there a credit is still negative
                beyond += 1
                self.assertTrue(any(c < 0 for _, c in ms.credits_at(10 * book, w, eq).values()), (eq, w))
                continue
            self.assertTrue(book < lo <= 10 * book and all(c >= 0 for _, c in ms.credits_at(lo, w, eq).values()))
            below = round(lo - 0.01, 2)
            self.assertTrue(below <= book or any(c < 0 for _, c in ms.credits_at(below, w, eq).values()), (lo, eq, w))
        self.assertGreater(beyond, 0)
        self.assertLess(beyond, 300)

    def test_a_slipped_zero_is_refused(self):
        self.assertIn("50.2x book live's $9,965.85: more than 10x is refused", self.refused(to="500000"))
        self.assertEqual(self.plan(to="99658.5")["factor"], 10.0)                # exactly 10x is allowed

    def test_bad_numbers_are_refused_before_anything_is_read(self):
        for to in ("abc", "nan", "inf", "-5", "0", "1e400"):
            with self.subTest(to=to):
                self.refused(to=to)
        for h in ("-0.1", "1.5", "nan", "x"):
            with self.subTest(headroom=h):
                self.refused("--headroom", h)
        self.assertIn("bad arguments", ms.run(["--snapshot", "x"], env=dict(ENV), fetch=self.fetch, now=NOW)[1])
        self.assertEqual(self.fetches, [])

    def test_the_env_must_name_the_executor_and_the_read_token(self):
        for env in ({"MIRROR_READ_TOKEN": READ}, {"MIRROR_EXECUTOR_URL": "https://exec.example"}, {}):
            with self.subTest(env=sorted(env)):
                self.assertIn("must both be set", self.refused(env=env))
        self.assertEqual(self.fetches, [])

    def test_the_read_token_goes_over_https_only_and_the_url_is_never_in_the_line(self):
        for url in ("http://exec.example", "ftp://exec.example", "http://10.0.0.5:8000"):
            with self.subTest(url=url):
                self.assertIn("MIRROR_EXECUTOR_URL must be https", self.refused(env=dict(ENV, MIRROR_EXECUTOR_URL=url)))
        self.assertEqual(self.fetches, [])
        for url in ("http://localhost:8000", "https://Exec.Example:8443/base/"):
            p = self.plan(env=dict(ENV, MIRROR_EXECUTOR_URL=url))
            self.assertNotIn("xec.", p["paste"].lower())
            self.assertNotIn("localhost", p["paste"])

    def test_a_feed_that_cannot_be_read_is_refused_without_the_token(self):
        self.feed = RuntimeError(f"HTTP 401: the read token was refused ({READ})")
        line = self.refused()
        self.assertIn("the executor's feed could not be read (HTTP 401", line)
        self.assertNotIn(READ, line)
        for bad in ([], {"books": None}, "x"):
            self.feed = bad
            self.assertIn("not a mirror feed", self.refused())

    def test_nothing_to_send_is_refused(self):
        for e in VALUES:
            self.snap["symphonies"][IDS[e]]["value"] = 1000.0
        v = view()
        for e in EQUITY:
            v["book"]["sleeves"][e]["equity"] = 2500.0
        v["book"]["equity"] = 10000.0
        self.feed = feed(live=v)
        self.assertIn("every credit rounds to $0.00: nothing to send", self.refused(to="10000.01"))


# ------------------------------------------------------------------ S6 the cap
def executor_applies(funded, cap, credits):
    """the executor's handling of positive operator credits on a live book (ibkr-executor/app/mirror.py
    _apply_credits + _over_cap + _book_cap_usd, pinned below): sorted by amount, smallest first; each
    taken iff funded + amount <= cap + SEED_TOL_USD; funded grows by each one taken; a refused one is
    dropped. -> (taken, refused, funded after)"""
    taken, refused = [], []
    for e, a in sorted(credits, key=lambda x: x[1]):
        if funded + a <= cap + ms.SEED_TOL_USD:
            funded = round(funded + a, 2)
            taken.append(e)
        else:
            refused.append(e)
    return taken, refused, funded


def flat(*path):
    with open(os.path.join(REPO, *path)) as f:
        return " ".join(f.read().split())


class S6Cap(Case):
    def test_the_cap_is_the_need_times_headroom_rounded_up_to_the_next_500(self):
        self.assertEqual(ms.cap_to_set(50034.15, 0.05), 53000)                  # 52,535.86 -> 53,000
        self.assertEqual(ms.cap_to_set(50000.0, 0.0), 50000)                    # already a multiple: kept
        self.assertEqual(ms.cap_to_set(50000.01, 0.0), 50500)
        self.assertEqual(ms.cap_to_set(47619.05, 0.05), 50000)                  # 50,000.0025 is 50,000.00 in cents
        p = self.plan()
        self.assertEqual(p["cap"], dict(p["cap"], headroom=0.05, need=50034.15, with_headroom=52535.86, set=53000))
        self.assertEqual(self.plan("--headroom", "0")["cap"]["set"], 50500)
        self.assertEqual(self.plan("--headroom", "0.10")["cap"]["set"], 55500)  # 55,037.57

    def test_funded_is_the_seeds_plus_the_operator_credits_in_the_rows(self):
        row = {"session": "2026-11-12", "outcome": "traded", "credits": [
            {"sleeve": "HG", "amount": 500.0, "kind": "credit", "id": "credit-1"},
            {"sleeve": "KMLM", "amount": 12.3, "kind": "dividend", "id": "div-1"},      # not counted by the cap
            {"sleeve": "HARV", "amount": -5.0, "kind": "credit", "id": "credit-2"}]}    # a debit: not counted
        self.feed = feed(live=view(history=[{"session": "2026-11-11", "credits": []}, row], last_run=row))
        p = self.plan()
        self.assertEqual(p["funded"]["now"], 10500.0)                           # the row twice: counted once
        self.assertIn("estimated: the seeds $10,000.00 + the operator credits in the feed's 2 session row(s) "
                      "(2026-11-11..2026-11-12) $500.00", p["funded"]["how"])
        self.assertEqual(p["cap"]["need"], round(10500.0 + 40034.15, 2))

    def test_a_published_funded_usd_is_used_as_it_is(self):
        self.feed = feed(live=view(funded_usd=12345.67))
        p = self.plan()
        self.assertEqual(p["funded"]["now"], 12345.67)
        self.assertIn("published on the feed", p["funded"]["how"])
        self.feed = feed(live=view(funded_usd="12345"))
        self.assertIn("funded_usd is not a number", self.refused())

    def test_no_seeds_on_the_feed_is_refused(self):
        for seeded in ({}, None, {"HG": {"amount": "x"}}, {"HG": 5}):
            with self.subTest(seeded=seeded):
                self.feed = feed(live=view(seeded=seeded))
                self.refused()

    def test_a_full_history_window_is_warned(self):
        rows = [{"session": f"2026-{(i // 28) + 6:02d}-{(i % 28) + 1:02d}", "credits": []} for i in range(ms.HISTORY)]
        self.feed = feed(live=view(history=rows))
        self.assertTrue(any("history is full" in w for w in self.plan()["warnings"]))

    def test_every_credit_passes_the_executors_check_at_the_cap_printed(self):
        p = self.plan()
        credits = [(r["engine"], r["credit"]) for r in p["engines"]]
        taken, refused, after = executor_applies(p["funded"]["now"], p["cap"]["set"], credits)
        self.assertEqual((taken, refused), (["HARV", "SLEEVE", "KMLM", "HG"], []))
        self.assertEqual(after, p["cap"]["need"])
        # the need itself is the edge: $1 under it still passes (the executor's tolerance), $2 under refuses
        # the LARGEST credit - the last one applied - and only it: a partly scaled, misweighted book
        self.assertEqual(executor_applies(p["funded"]["now"], p["cap"]["need"] - 1, credits)[1], [])
        self.assertEqual(executor_applies(p["funded"]["now"], p["cap"]["need"] - 2, credits)[1], ["HG"])
        # the cap does NOT protect the split from a second paste before the session: it takes some twice
        # and drops the largest - which is why the pasted line refuses when anything is already queued
        twice = executor_applies(p["funded"]["now"], p["cap"]["set"], credits + credits)
        self.assertEqual(twice[0], ["HARV", "HARV", "SLEEVE", "SLEEVE", "KMLM"])

    PINS = {
        ("ibkr-executor", "app", "mirror.py"): (
            "SEED_TOL_USD = 1.0",
            "CASH_TOL_USD = 1.0",
            "if funded + amount <= self._book_cap_usd() + SEED_TOL_USD: return None",
            "cap = _num(self.cfg.max_book_usd) return cap if cap is not None and cap > 0 else self._engines_capital_usd()",
            'rows.sort(key=lambda r: _num(r.get("amount")) if _num(r.get("amount")) is not None else 0.0)',
            "if have is None or self.book.cash() + amt > have + CASH_TOL_USD:",
            'if ok and self.cfg.live and amt > 0 and r.get("force") is not True and self._over_cap(amt):',
            'self.state["funded_usd"] = round(funded + amt, 2)',
            # a refused credit is not kept: the requests left are the other kinds only (item 11: a span that
            # is _apply_credits' alone; 'self.state["requests"] = keep' is also _apply_repairs')
            '(rows if r.get("kind") == "credit" else keep).append(r)',
            'self._journal("credit_refused", why=why, **r) self.state["requests"] = keep',
            # the dividends due are credited first, then the credits (the cash minimum counts both)
            "self._dividends(ad, payload, session, notes, credits) self._apply_credits(ad, notes, credits)",
            'arrived = have is not None and self.book.cash() + float(r["total"]) <= have + CASH_TOL_USD',
            'return f"{self.cfg.state_path}.inbox.json"',
            '"funded_usd": None, "seq": 0',
            '"pending_requests": list(self.state.get("requests") or [])',
            '"dividends_open": [r for r in self.state.get("dividends") or [] if r.get("status") == "open"]',
            '"seeded": self.state.get("seeded") or {}, "last_session": self.state.get("last_session"),',
            '"frozen": name in (self.state.get("frozen") or [])',
            '"credits": list(run.get("credits") or [])',
            'credits.append({"sleeve": name, "amount": amt, "kind": "credit", "id": r.get("id"), "note": r.get("note")})',
            "HISTORY_KEEP = 120",
            # what the pasted line reads in the state file
            'json.dump(obj, f, separators=(",", ":"), sort_keys=True)',
            'if raw.get("name") != self.cfg.name or bool(raw.get("live")) != self.cfg.live:',
            'self.state["last_session"] = max(self.state.get("last_session") or "", run["session"])',
        ),
        ("ibkr-executor", "app", "mirror_core.py"): (
            "DEFAULT_PAY_LAG_DAYS = 7",
            "PAY_DATE_GIVE_UP_DAYS = 10",
            "if ex is None or day is None or (day - ex).days < PAY_DATE_GIVE_UP_DAYS: return None "
            "return (ex + timedelta(days=DEFAULT_PAY_LAG_DAYS)).isoformat()",
            "MAX_IDLE_CASH_FRAC = 0.05",                                    # step (c): KMLM trades a credit
            "and idle <= MAX_IDLE_CASH_FRAC and gap <= sleeve.corridor:",
        ),
        ("ibkr-executor", "app", "service.py"): (
            '@app.post("/mirror/credit") def mirror_credit(body: dict = Depends(_mirror_body), '
            'x_exec_token: str | None = Header(default=None),',
            '_auth(x_exec_token, token) book = _mirror_book(body.get("book")) try: req = book.request_credit(',
            "if not 0 <= history <= 120:",
        ),
        ("ibkr-executor", "app", "config.py"): ('mirror_state_path: str = "./data/mirror_state.json"',),
        ("ibkr-executor", "start.sh"): ("cd /opt/executor",
                                        'exec ./venv/bin/uvicorn app.service:app --host 0.0.0.0 --port "${PORT:-8000}"'),
        ("ibkr-executor", "Dockerfile"): ("apt-get install -y --no-install-recommends python3 python3-venv",
                                          "WORKDIR /opt/executor", "ENV PORT=8000"),
        ("render.yaml",): ("- key: MIRROR_STATE_PATH value: /app/data/mirror_state.json",),
    }

    def test_the_executor_still_says_what_the_planner_relies_on(self):
        """the executor's own lines the cap rule, the cash minimum, the pasted line and step (c) depend on;
        a change to any of them fails here and the planner is to be re-read against it. EACH PIN IS UNIQUE in
        its file (item 11: a pin that also matches elsewhere pins nothing)"""
        if not os.path.isdir(os.path.join(REPO, "ibkr-executor")):
            self.skipTest("ibkr-executor/ is not in this checkout")
        for path, pins in self.PINS.items():
            src = flat(*path)
            for text in pins:
                with self.subTest(file="/".join(path), pin=text[:60]):
                    self.assertEqual(src.count(text), 1, f"{text!r} occurs {src.count(text)} times in {'/'.join(path)}")
        mirror = flat("ibkr-executor", "app", "mirror.py")
        body = mirror.split("def _apply_credits(")[1].split(" def ")[0]
        self.assertIn('self._journal("credit_refused", why=why, **r) self.state["requests"] = keep', body)
        self.assertNotIn('"funded_usd": ', mirror.split("def _publish")[1].split("def view")[0],
                         "the feed now publishes funded_usd: the planner uses it; drop the estimate's caveats")
        self.assertEqual((ms.DEFAULT_PAY_LAG_DAYS, ms.PAY_DATE_GIVE_UP_DAYS, ms.CASH_TOL_USD, ms.SEED_TOL_USD),
                         (7, 10, 1.0, 1.0))
        self.assertEqual((ms.LINE_PY, ms.LINE_HOST, ms.PORT_DEFAULT, ms.EXEC_DIR),
                         ("python3", "127.0.0.1", "8000", "/opt/executor"))

    def test_the_cash_the_account_must_hold(self):
        p = self.plan()
        self.assertEqual(p["cash"]["book_cash"], 108.52)
        self.assertEqual(p["cash"]["need"], round(108.52 + 40034.15 + 200.17, 2))
        self.assertIn("CASH: the account must hold at least $40,342.84 in cash at the decision of 2026-11-13", self.run_it()[1])
        v = view()
        v["book"]["cash"] = None
        self.feed = feed(live=v)
        self.assertIn("the book's cash on the feed is not a number", self.refused())


# ------------------------------------------------------------------ P8 the cash minimum (item 8)
def div(sleeve="HG", ticker="BIL", ex="2026-11-10", pay="2026-11-13", total=11.1, **kw):
    return dict({"id": f"div-{ticker}-{ex}-{sleeve}", "sleeve": sleeve, "ticker": ticker, "ex_date": ex,
                 "pay_date": pay, "shares": 37, "amount": 0.3, "total": total, "status": "open", "seen": ex,
                 "basis": "x", "waited": 0}, **kw)


class P8CashMinimum(Case):
    """at the decision the executor credits the dividends due, THEN each credit only if the account's cash
    covers the book's plus it (smallest first). At 6b122160 the minimum was the book's cash + the credits:
    a dividend due that day, or the account $1 short, refused the LARGEST credit whole"""

    def test_the_minimum_counts_the_dividends_due_by_the_session_and_a_margin(self):
        rows = [div(pay="2026-11-13", total=11.1),                                   # due on the session: counted
                div("KMLM", "PULS", pay="2026-11-10", total=4.25),                   # overdue, still open: counted
                div("HARV", "PULS", pay="2026-11-16", total=7.0),                    # after the session: not
                div("SLEEVE", "BOXX", ex="2026-11-01", pay=None, total=3.3),         # pay date never learnt, 12 days: ex + 7
                div("SLEEVE", "BIL", ex="2026-11-05", pay=None, total=2.0)]          # 8 days: not due yet
        self.feed = feed(live=view(dividends_open=rows))
        p = self.plan()
        c = p["cash"]
        self.assertEqual(p["session"], "2026-11-13")
        self.assertEqual(c["dividends"], round(11.1 + 4.25 + 3.3, 2))
        self.assertEqual([(r["sleeve"], r["due"]) for r in c["dividends_due"]],
                         [("HG", "2026-11-13"), ("KMLM", "2026-11-10"), ("SLEEVE", "2026-11-08")])
        self.assertEqual(c["margin"], round(0.005 * 40034.15, 2))                    # 0.5% of $40,034.15 > $100
        self.assertEqual(c["executor_need"], round(108.52 + 18.65 + 40034.15, 2))
        self.assertEqual(c["need"], round(108.52 + 18.65 + 40034.15 + 200.17, 2))
        text = self.run_it()[1]
        self.assertIn("CASH: the account must hold at least $40,361.49 in cash at the decision of 2026-11-13: the "
                      "book's $108.52 + the dividends due by then $18.65 + the credits $40,034.15 + a margin of $200.17 "
                      "(the larger of $100 and 0.5% of the credits)", text)
        self.assertIn("  dividend due 2026-11-13: HG BIL $11.10 (div-BIL-2026-11-10-HG)", text)
        self.assertIn("If the account's spare cash is short by even $1 (more than the executor's $1.00 tolerance below "
                      "the book's cash + the dividends due + the credits, $40,161.32), the executor refuses the LARGEST "
                      "credit whole and the book trades mis-split until a new plan lands.", text)

    def test_the_margin_is_at_least_100_dollars(self):
        p = self.plan(to="11000")
        self.assertEqual(p["cash"]["margin"], 100.0)
        self.assertEqual(p["cash"]["need"], round(108.52 + p["cash"]["credits"] + 100.0, 2))

    def test_the_minimum_is_what_the_executor_takes_all_the_credits_at_and_a_dollar_less_refuses_the_largest(self):
        """the executor's own order at the decision (mirror.py _dividends then _apply_credits, pinned in S6):
        each dividend credited lifts the book's cash; then each credit, smallest first, only while the book's
        cash plus it is within the account's + CASH_TOL_USD"""
        self.feed = feed(live=view(dividends_open=[div(total=11.1)]))
        p = self.plan()

        def executor(account):
            book = p["cash"]["book_cash"] + p["cash"]["dividends"]
            taken, refused = [], []
            for e, a in sorted(((r["engine"], r["credit"]) for r in p["engines"]), key=lambda x: x[1]):
                if book + a <= account + ms.CASH_TOL_USD:
                    book += a
                    taken.append(e)
                else:
                    refused.append(e)
            return taken, refused
        self.assertEqual(executor(p["cash"]["need"]), (["HARV", "SLEEVE", "KMLM", "HG"], []))
        self.assertEqual(executor(p["cash"]["executor_need"] - 0.99), (["HARV", "SLEEVE", "KMLM", "HG"], []))
        self.assertEqual(executor(p["cash"]["executor_need"] - 1.01), (["HARV", "SLEEVE", "KMLM"], ["HG"]))
        # without the dividend in it (the minimum at 6b122160), the account the owner was told to hold refuses HG
        self.assertEqual(executor(p["cash"]["book_cash"] + p["cash"]["credits"])[1], ["HG"])

    def test_dividends_that_cannot_be_read_are_warned_never_a_traceback(self):
        for rows in ("x", [5], [div(total="11.1")], [div(ex=None)], [div(total=10 ** 400)]):
            with self.subTest(rows=rows):
                self.feed = feed(live=view(dividends_open=rows))
                p = self.plan()
                self.assertEqual(p["cash"]["dividends"], 0.0)
                self.assertTrue(any("dividend" in w and "cash minimum" in w for w in p["warnings"]), p["warnings"])


# ------------------------------------------------------------------ S7 the pasted line, run
class LineCase(Case):
    """the plan's line run as the owner runs it: in-process (exec of the -c code, the clock patched), or as
    a process; against a real HTTP server on 127.0.0.1 standing in for the executor's /mirror/credit"""

    def setUp(self):
        super().setUp()
        self.p = self.plan()
        self.state = os.path.join(self.tmp.name, "data", "mirror_state.json")
        os.makedirs(os.path.dirname(self.state))
        self.inbox = self.state + ".inbox.json"
        self.write_state()
        self.ex = Executor(inbox=self.inbox)
        self.addCleanup(self.ex.close)
        self.env = {"EXEC_TOKEN": "exec-in-the-container", "MIRROR_STATE_PATH": self.state,
                    "MIRROR_MAX_BOOK_USD": "53000", "PORT": str(self.ex.port)}

    def write_state(self, funded=10000.0, requests=(), inbox=None, last_session="2026-11-12", **over):
        """the executor's state file with the fields the line reads, as mirror.py writes them: its book is
        mirror_core.Book.to_dict() ("sleeves" a LIST of records, each with its "name"; pinned in S6), nothing
        frozen, no run open, and the post-trade check of its last session done and clean"""
        st = dict({"schema": 1, "name": "live", "live": True, "funded_usd": funded, "requests": list(requests),
                   "last_session": last_session, "seq": 42, "run": None, "frozen": [],
                   "check": {"session": last_session, "utc": "2026-11-12T21:10:00Z", "strikes": 0, "problems": [],
                             "done": True},
                   "book": {"schema": 1, "sleeves": [{"name": e, "cash": 30.0, "shares": {"BIL": 1}, "rule": "daily",
                                                      "corridor": None, "version": None, "last_trade": None}
                                                     for e in CREDITS]}}, **over)
        with open(self.state, "w") as f:
            json.dump(st, f)
        if inbox is not None:
            with open(self.inbox, "w") as f:
                json.dump(inbox, f)

    def exec_line(self, env=None, at=FRI_10, code=None):
        """(exit code, stdout) of the line's -c code run here, at UTC epoch `at`"""
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, self.env if env is None else env, clear=True), \
                unittest.mock.patch.object(time, "time", lambda: at), contextlib.redirect_stdout(out):
            try:
                exec(compile(code or self.p["code"], "<pasted line>", "exec"), {"__name__": "__main__"})
                rc = 0
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue()

    def posts(self):
        return [r for r in self.ex.requests if r["path"] == "/mirror/credit"]


class S7PastedLine(LineCase):
    def test_the_line_posts_each_credit_with_the_token_and_prints_each_answer(self):
        rc, out = self.exec_line()
        self.assertEqual(rc, 0, out)
        posts = self.posts()
        self.assertEqual([x["method"] for x in posts], ["POST"] * 4)
        self.assertEqual([json.loads(x["body"]) for x in posts],
                         [{"sleeve": e, "amount": a, "note": "scale-up to $50,000 at Composer's split of 2026-11-12",
                           "book": "live"} for e, a in CREDITS.items()])
        self.assertTrue(all(x["headers"]["X-Exec-Token"] == "exec-in-the-container" for x in posts))
        self.assertTrue(all(x["headers"]["Content-Type"] == "application/json" for x in posts))
        lines = out.strip().splitlines()
        self.assertEqual([ln.split(" ", 3)[:3] for ln in lines[:4]], [[e, repr(a), "200"] for e, a in CREDITS.items()])
        self.assertEqual(lines[4], "ALL 4 CREDITS QUEUED (HG 13349.17, KMLM 11341.25, SLEEVE 10440.19, HARV 4903.54) "
                                   "for the session of 2026-11-13")
        self.assertNotIn("exec-in-the-container", out)
        with open(self.inbox) as f:
            self.assertEqual([r["sleeve"] for r in json.load(f)], list(CREDITS))

    def test_no_token_anywhere_in_the_plan(self):
        for argv in ((), ("--json",)):
            code, text = self.run_it(*argv)
            self.assertEqual(code, 0)
            for tok in (READ, EXEC):
                self.assertNotIn(tok, text)
        self.assertNotIn("exec-in-the-container", self.p["code"])

    def test_the_line_sends_nothing_without_the_token_or_the_state(self):
        env = dict(self.env)
        del env["EXEC_TOKEN"]
        rc, out = self.exec_line(env)
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn("NOTHING SENT: EXEC_TOKEN is not set: paste this in the Shell of ibkr-executor", out)
        nope = os.path.join(self.tmp.name, "nope.json")
        rc, out = self.exec_line(dict(self.env, MIRROR_STATE_PATH=nope))
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn(f"NOTHING SENT: {nope} is not there", out)
        self.write_state(name="dry", live=False)                                 # the paper book's state
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn(f"{self.state} is not the live book", out)
        with open(self.state, "w") as f:
            f.write("{torn")
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn(f"{self.state} unreadable", out)

    def test_a_relative_state_path_is_the_executors_working_directory(self):
        self.assertIn('P=os.path.join("/opt/executor",E.get("MIRROR_STATE_PATH")or"./data/mirror_state.json")',
                      self.p["program"])
        env = dict(self.env)
        del env["MIRROR_STATE_PATH"]
        rc, out = self.exec_line(env)
        self.assertEqual(rc, 1)
        self.assertIn("/opt/executor/./data/mirror_state.json is not there", out)

    def test_the_line_sends_nothing_when_the_book_ran_a_session_since_the_plan(self):
        self.write_state(last_session="2026-11-13")
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn(f"the book ran a session (2026-11-13) after the plan: {RERUN}", out)

    def test_the_line_names_only_the_engines_with_a_credit(self):
        line, code, program = ms.paste_line("live", [("HG", 10.5), ("HARV", 0.01)],
                                            "scale-up to $10,000 at Composer's split of 2026-11-12", "2026-11-13",
                                            "2026-11-12", WIDE, "15:00 ET on Fri 2026-11-13",
                                            "mirror_scale.py --to 10000")
        self.assertIn('A=(("HG",10.5),("HARV",0.01));D=1051;', program)
        self.assertEqual(shlex.split(line)[2], code)


# ------------------------------------------------------------------ L1 / L2 where the token goes; plain python3 (items 1, 2)
class L1L2TokenStaysInTheContainer(LineCase):
    """item 1: at 6b122160 the line POSTed EXEC_TOKEN over the internet to MIRROR_EXECUTOR_URL (the planner
    machine's), with httpx from the executor's venv. Now it goes to the executor in the same container only"""

    def test_the_only_place_the_token_is_sent_is_127_0_0_1_on_the_executors_port(self):
        prog = self.p["program"]
        self.assertEqual(prog.count("HTTPConnection("), 1)
        self.assertIn('h=hc.HTTPConnection("127.0.0.1",int(O),timeout=30)', prog)
        self.assertIn('O=E.get("PORT")or"8000"', prog)                         # start.sh: --port "${PORT:-8000}"
        self.assertIn('h.request("POST","/mirror/credit",', prog)
        self.assertEqual(prog.count("X-Exec-Token"), 1)
        for word in ("exec.example", "http://", "https://", "urlopen", "MIRROR_EXECUTOR_URL", "Proxy", "proxy"):
            self.assertNotIn(word, prog, word)
        self.assertTrue(self.p["post_to"].startswith("http://127.0.0.1:$PORT/mirror/credit"))
        rc, out = self.exec_line()
        self.assertEqual(rc, 0, out)
        self.assertEqual({x["headers"]["Host"] for x in self.posts()}, {f"127.0.0.1:{self.ex.port}"})

    def test_port_unset_is_8000_and_a_bad_port_sends_nothing(self):
        seen = []

        class Conn:
            def __init__(self, host, port, timeout=None):
                seen.append((host, port, timeout))

            def request(self, *a, **kw):
                pass

            def getresponse(self):
                return type("R", (), {"status": 200, "read": lambda self: b"{}"})()

            def close(self):
                pass
        env = dict(self.env)
        del env["PORT"]
        with unittest.mock.patch("http.client.HTTPConnection", Conn):
            rc, out = self.exec_line(env)
        self.assertEqual((rc, seen), (0, [("127.0.0.1", 8000, 30)] * 4))
        for bad in ("abc", "0", "65536", "-1", "80a", "8000 "):
            with self.subTest(port=bad):
                rc, out = self.exec_line(dict(self.env, PORT=bad))
                self.assertEqual((rc, self.posts()), (1, []))
                self.assertIn(f"PORT {bad!r} is not a port", out)

    def test_a_proxy_in_the_env_is_never_used_and_a_redirect_never_followed(self):
        trap = Executor()
        self.addCleanup(trap.close)
        proxy = f"http://127.0.0.1:{trap.port}"
        env = dict(self.env, HTTP_PROXY=proxy, http_proxy=proxy, HTTPS_PROXY=proxy, https_proxy=proxy,
                   ALL_PROXY=proxy, all_proxy=proxy)
        rc, out = self.exec_line(env)
        self.assertEqual((rc, len(self.posts()), trap.requests), (0, 4, []))
        os.remove(self.inbox)
        self.ex.requests.clear()
        self.ex.answers = [("redirect", f"http://127.0.0.1:{trap.port}/mirror/credit")]
        rc, out = self.exec_line(env)
        self.assertEqual((rc, len(self.posts()), trap.requests), (2, 1, []))
        self.assertIn("STOPPED: HG answered HTTP 302", out)

    def test_the_line_is_plain_python3_and_the_standard_library_on_one_line(self):
        """item 2: at 6b122160 the line was /opt/executor/venv/bin/python3 with httpx"""
        line, code, prog = self.p["paste"], self.p["code"], self.p["program"]
        self.assertEqual(shlex.split(line), ["python3", "-c", code])
        self.assertTrue(line.startswith("python3 -c 'exec(") and line.endswith(")'"))
        self.assertNotIn("\n", line)
        self.assertNotIn("'", code)                                              # the shell's single quotes hold
        self.assertLessEqual(len(line.encode()), ms.TTY_LINE_MAX)                # a canonical-mode terminal line
        compile(code, "<pasted line>", "exec")
        compile(prog, "<the line's program>", "exec")
        self.assertEqual(eval(code[len("exec("):-1]), prog)                      # the literal is the program
        imports = re.findall(r"^import (.+)$", prog, re.M)
        self.assertEqual(imports, ["http.client as hc,json,os,sys,time"])
        for name in ("http", "json", "os", "sys", "time"):
            self.assertIn(name, sys.stdlib_module_names)
        for word in ("httpx", "venv", "/opt/executor/venv", "pathlib", "import requests"):
            self.assertNotIn(word, line)
        self.assertNotIn("import ", prog.split("\n", 1)[1].replace("import http.client", ""))  # nothing imported later

    def test_the_printed_line_runs_as_printed_under_bash_and_sh(self):
        """the exact bytes of a line, run by bash and by sh (dash) as a separate python3 process, with the
        proxy env set to a trap: four POSTs here, nothing to the trap. The windows are open (the clock is
        not this test's: L4 is)"""
        trap = Executor()
        self.addCleanup(trap.close)
        for shell in ("bash", "sh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                if os.path.exists(self.inbox):
                    os.remove(self.inbox)
                self.ex.requests.clear()
                line, code, prog = ms.paste_line("live", list(CREDITS.items()), self.p["note"], "2026-11-13", "2026-11-12",
                                                 WIDE, "15:00 ET on Fri 2026-11-13",
                                                 "mirror_scale.py --to 50000")
                proxy = f"http://127.0.0.1:{trap.port}"
                env = dict(self.env, PATH=os.environ.get("PATH", "/usr/bin:/bin"), HTTP_PROXY=proxy, http_proxy=proxy)
                r = subprocess.run([shell, "-c", line], env=env, capture_output=True, text=True, timeout=120,
                                   cwd=self.tmp.name)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(r.stderr, "")
                self.assertIn("ALL 4 CREDITS QUEUED", r.stdout)
                self.assertEqual([json.loads(x["body"])["sleeve"] for x in self.posts()], list(CREDITS))
                self.assertEqual(trap.requests, [])
                self.assertNotIn("exec-in-the-container", r.stdout)
                r = subprocess.run([shell, "-c", line], env=env, capture_output=True, text=True, timeout=120,
                                   cwd=self.tmp.name)                            # pasted again: the inbox holds them
                self.assertEqual((r.returncode, len(self.posts())), (1, 4))
                self.assertIn("NOTHING SENT: 4 request(s) queued", r.stdout)


# ------------------------------------------------------------------ L3 anything queued (item 3)
class L3AnythingQueued(LineCase):
    """item 3: at 6b122160 only a queued CREDIT stopped the line; a transfer, an adjust or a resolve let it
    send. Now any request in the state's requests or the inbox sends nothing, and each is listed"""
    ROWS = {"credit": {"kind": "credit", "sleeve": "HG", "amount": 13349.17, "id": "credit-1"},
            "transfer": {"kind": "transfer", "from": "HG", "to": "SLEEVE", "amount": 138.32, "id": "transfer-7",
                         "via": "transfer_token"},
            "adjust": {"kind": "adjust", "sleeve": "KMLM", "symbol": "PULS", "shares": 1, "cash": 0.0, "id": "adjust-3"},
            "resolve": {"kind": "resolve", "order": "mirror-2026-11-12-B-BIL", "filled": 3, "id": "resolve-2"}}

    def test_any_request_in_the_state_or_the_inbox_sends_nothing_and_is_listed(self):
        for kind, row in self.ROWS.items():
            for where in ("state", "inbox"):
                with self.subTest(kind=kind, where=where):
                    self.write_state(requests=[row] if where == "state" else [], inbox=[row] if where == "inbox" else [])
                    rc, out = self.exec_line()
                    self.assertEqual((rc, self.posts()), (1, []))
                    self.assertTrue(out.startswith("NOTHING SENT: 1 request(s) queued, not yet applied: "), out)
                    self.assertIn(f"{kind} {row.get('sleeve') or row.get('order') or row.get('from')} {row['id']}", out)

    def test_every_queued_request_is_listed(self):
        self.write_state(requests=[self.ROWS["transfer"], self.ROWS["adjust"]], inbox=[self.ROWS["credit"], "junk"])
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn("4 request(s) queued, not yet applied: credit HG credit-1; 'junk'; transfer HG transfer-7; "
                      "adjust KMLM adjust-3", out)

    def test_an_inbox_that_cannot_be_read_or_is_not_a_list_sends_nothing(self):
        with open(self.inbox, "w") as f:
            f.write("[{torn")
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn(f"{self.inbox} unreadable", out)
        self.write_state(inbox={"kind": "credit"})
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn("1 request(s) queued", out)
        self.write_state(requests="junk", inbox=[])
        self.assertEqual(self.exec_line()[0], 1)

    def test_an_empty_queue_sends(self):
        self.write_state(requests=[], inbox=[])
        self.assertEqual(self.exec_line()[0], 0)
        self.assertEqual(len(self.posts()), 4)


# ------------------------------------------------------------------ L4 when it may be pasted (item 4)
class L4PasteWindows(LineCase):
    """item 4: at 6b122160 the line queued credits at any hour, so a paste after a session's decision
    left that evening's POLICY routine sizing a transfer on pre-credit equity. The plan (NOW: Thu 2026-11-12
    17:00 ET, after the session) is for Fri 2026-11-13, pasteable until 15:00 ET that day"""

    REASON = "it is a weekday from 15:00 ET (12:00 on a half-day): paste on a morning or a weekend"

    def at(self, ts):
        if os.path.exists(self.inbox):
            os.remove(self.inbox)
        self.ex.requests.clear()
        return self.exec_line(at=ts)

    def test_a_weekday_afternoon_or_evening_sends_nothing_and_says_why(self):
        for ts in (et(2026, 11, 12, 15, 0), et(2026, 11, 12, 16, 0), et(2026, 11, 12, 23, 59)):
            with self.subTest(et=datetime.datetime.fromtimestamp(ts, UTC)):
                rc, out = self.at(ts)
                self.assertEqual((rc, self.posts()), (1, []))
                self.assertEqual(out.strip(), "NOTHING SENT: " + self.REASON)
        for ts in (et(2026, 11, 13, 0, 0), et(2026, 11, 13, 9, 30), et(2026, 11, 13, 14, 59)):
            with self.subTest(et=datetime.datetime.fromtimestamp(ts, UTC)):
                rc, out = self.at(ts)
                self.assertEqual((rc, len(self.posts())), (0, 4), out)

    def test_after_its_sessions_cutoff_the_line_has_expired(self):
        for ts in (et(2026, 11, 13, 15, 0), et(2026, 11, 14, 10, 0), et(2026, 11, 16, 9, 0)):
            with self.subTest(et=datetime.datetime.fromtimestamp(ts, UTC)):
                rc, out = self.at(ts)
                self.assertEqual((rc, self.posts()), (1, []))
                self.assertIn("this line was for the session of 2026-11-13 (paste by 15:00 ET on Fri 2026-11-13): "
                              + RERUN, out)

    def test_a_weekend_is_any_time_and_a_half_day_closes_at_noon(self):
        sat = datetime.datetime(2026, 11, 14, 15, 0, tzinfo=UTC)                  # Sat 10:00 ET
        self.feed = feed(live=view(last_session="2026-11-13", check=dict(view()["check"], session="2026-11-13")))
        self.p = self.plan(now=sat)
        self.write_state(last_session="2026-11-13")
        self.assertEqual((self.p["session"], self.p["paste_until"]), ("2026-11-16", "15:00 ET on Mon 2026-11-16"))
        for ts in (et(2026, 11, 14, 16, 0), et(2026, 11, 14, 23, 30), et(2026, 11, 15, 3, 0), et(2026, 11, 16, 14, 0)):
            with self.subTest(et=datetime.datetime.fromtimestamp(ts, UTC)):
                self.assertEqual(self.at(ts)[0], 0)
        self.assertIn("paste by 15:00 ET on Mon 2026-11-16", self.at(et(2026, 11, 16, 15, 0))[1])
        # Thanksgiving (a weekday holiday): the session is the next day, a half-day, pasteable until 12:00 ET
        thu = datetime.datetime(2026, 11, 26, 15, 0, tzinfo=UTC)                  # Thu 10:00 ET
        self.feed = feed(live=view(last_session="2026-11-25", check=dict(view()["check"], session="2026-11-25")))
        self.p = self.plan(now=thu)
        self.write_state(last_session="2026-11-25")
        self.assertEqual((self.p["session"], self.p["paste_until"]), ("2026-11-27", "12:00 ET on Fri 2026-11-27"))
        self.assertEqual(self.at(et(2026, 11, 26, 11, 0))[0], 0)
        self.assertEqual(self.at(et(2026, 11, 26, 16, 0))[1].strip(), "NOTHING SENT: " + self.REASON)
        self.assertEqual(self.at(et(2026, 11, 27, 11, 59))[0], 0)
        self.assertIn("paste by 12:00 ET on Fri 2026-11-27", self.at(et(2026, 11, 27, 12, 0))[1])

    def test_the_session_the_plan_is_for(self):
        def session(last, *ymdhm):
            return ms.credit_session(last, datetime.datetime.fromtimestamp(et(*ymdhm), UTC))
        self.assertEqual(session("2026-11-12", 2026, 11, 12, 17, 0), "2026-11-13")   # after the session: the next
        self.assertEqual(session("2026-11-11", 2026, 11, 12, 10, 0), "2026-11-12")   # the morning: today's
        self.assertEqual(session("2026-11-11", 2026, 11, 12, 15, 30), "2026-11-13")  # past today's cutoff: tomorrow's
        self.assertEqual(session("2026-11-13", 2026, 11, 14, 10, 0), "2026-11-16")   # a weekend: Monday's
        self.assertEqual(session("2026-11-25", 2026, 11, 25, 16, 0), "2026-11-27")   # over Thanksgiving
        self.assertEqual(session("2026-11-26", 2026, 11, 27, 11, 0), "2026-11-27")   # a half-day morning
        self.assertEqual(session("2026-11-26", 2026, 11, 27, 12, 0), "2026-11-30")   # a half-day past noon

    def test_the_windows_are_exact_across_a_dst_change_and_without_a_tz_database(self):
        def hours(windows):
            out = set()
            for a, b in windows:
                out |= set(range(a, b, 3600))
            return out
        for now, session in ((datetime.datetime(2027, 3, 12, 22, 0, tzinfo=UTC), "2027-03-15"),    # EST -> EDT
                             (datetime.datetime(2026, 10, 30, 21, 0, tzinfo=UTC), "2026-11-02"),   # EDT -> EST
                             (NOW, "2026-11-13")):
            with self.subTest(now=now):
                got, until = ms.paste_windows(now, session)
                start = int(now.replace(minute=0).timestamp()) - 86400
                for h in range(start, got[-1][1] + 3 * 3600, 3600):
                    e = sr.et_now(datetime.datetime.fromtimestamp(h, UTC))
                    cut = 12 if e.date().isoformat() in sr.HALF_DAYS else 15
                    before = (e.date().isoformat(), e.hour) < (session, cut)
                    ok = before and not (e.weekday() < 5 and e.hour >= cut)
                    self.assertEqual(h in hours(got), ok, e)
                self.assertEqual(until, f"15:00 ET on {datetime.date.fromisoformat(session):%a} {session}")
                with unittest.mock.patch.object(sr, "et_now", sr._et_fallback):
                    self.assertEqual(ms.paste_windows(now, session), (got, until))
        spring, _ = ms.paste_windows(datetime.datetime(2027, 3, 12, 22, 0, tzinfo=UTC), "2027-03-15")
        self.assertEqual(spring[-1][1], int(datetime.datetime(2027, 3, 15, 19, 0, tzinfo=UTC).timestamp()))  # 15:00 EDT
        self.assertIn((int(datetime.datetime(2027, 3, 13, 5, 0, tzinfo=UTC).timestamp()),                     # Sat 00:00 EST
                       int(datetime.datetime(2027, 3, 15, 19, 0, tzinfo=UTC).timestamp())), spring)


# ------------------------------------------------------------------ L5 the cap, in cents (item 5)
class L5Cap(LineCase):
    """item 5: at 6b122160 the line allowed funded + credits up to the cap + $1 (in floats) and read an
    unset MIRROR_MAX_BOOK_USD as 0. Now integer cents, no slack, and a cap that is not a number above 0
    sends nothing and says that the executor would then cap the book at MIRROR_CAPITAL_USD"""

    def test_the_cap_is_compared_in_cents_with_no_slack(self):
        rc, out = self.exec_line(dict(self.env, MIRROR_MAX_BOOK_USD="50034.15"))   # 10,000.00 + 40,034.15 exactly
        self.assertEqual((rc, len(self.posts())), (0, 4), out)
        for cap in ("50034.14", "50033.15", "50033.16"):                         # the old line sent these
            with self.subTest(cap=cap):
                if os.path.exists(self.inbox):
                    os.remove(self.inbox)
                self.ex.requests.clear()
                rc, out = self.exec_line(dict(self.env, MIRROR_MAX_BOOK_USD=cap))
                self.assertEqual((rc, self.posts()), (1, []))
                self.assertIn(f"MIRROR_MAX_BOOK_USD {float(cap):.2f} is below funded_usd 10000.00 + these credits "
                              f"40034.15 = 50034.15: the largest would be DROPPED; set the cap (step a), deploy first", out)
        self.write_state(funded=13500.0)                     # the executor has taken more than the feed showed
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn("below funded_usd 13500.00 + these credits 40034.15 = 53534.15", out)

    def test_a_cap_that_is_not_a_number_above_zero_sends_nothing_and_says_what_it_means(self):
        for cap in (None, "", "  ", "0", "-5", "nan", "inf", "-inf", "1e400", "abc", "53,000"):
            with self.subTest(cap=cap):
                env = dict(self.env)
                if cap is None:
                    del env["MIRROR_MAX_BOOK_USD"]
                else:
                    env["MIRROR_MAX_BOOK_USD"] = cap
                rc, out = self.exec_line(env)
                self.assertEqual((rc, self.posts()), (1, []))
                self.assertIn(f"MIRROR_MAX_BOOK_USD {(cap or '').strip()!r} is not above 0: set it (step a), deploy first",
                              out)

    def test_a_funded_usd_that_is_not_an_amount_sends_nothing(self):
        for funded in (None, "10000", True, -1.0, float("nan"), float("inf")):
            with self.subTest(funded=funded):
                self.write_state(funded=funded)
                rc, out = self.exec_line()
                self.assertEqual((rc, self.posts()), (1, []))
                self.assertIn("the book state has no funded_usd", out)
        self.write_state()
        st = json.load(open(self.state))
        del st["funded_usd"]
        json.dump(st, open(self.state, "w"))
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []))
        self.assertIn("the book state has no funded_usd (None)", out)

    def test_the_cents_are_the_credits_total(self):
        self.assertIn(";D=4003415;", self.p["program"])
        self.assertEqual(sum(int(round(a * 100)) for a in CREDITS.values()), 4003415)


# ------------------------------------------------------------------ L6 a POST that fails (item 6)
class L6Stops(LineCase):
    """item 6: at 6b122160 a POST that raised escaped as a traceback with no word on what was queued. Now
    every POST is guarded and the line stops at the first error or answer that is not 200"""

    def test_an_answer_that_is_not_200_stops_at_once_and_says_what_was_queued(self):
        self.ex.answers = [(200, None), (500, '{"detail": "Internal Server Error"}'), (200, None)]
        rc, out = self.exec_line()
        self.assertEqual((rc, len(self.posts())), (2, 2))
        self.assertIn('KMLM 11341.25 500 {"detail": "Internal Server Error"}', out)
        self.assertIn("STOPPED: KMLM answered HTTP 500. Queued: HG 13349.17. KMLM may have been queued anyway; not sent: "
                      f"SLEEVE, HARV. What is queued applies at the next session and cannot be withdrawn: after it, {RERUN}",
                      out)
        self.assertNotIn("ALL", out)
        rc, out = self.exec_line()                           # pasted again: HG is in the inbox
        self.assertEqual((rc, len(self.posts())), (1, 2))
        self.assertIn("NOTHING SENT: 1 request(s) queued, not yet applied: credit HG credit-1794520000000-0", out)

    def test_no_answer_stops_at_once_too(self):
        self.ex.answers = [(200, None), (200, None), "drop"]
        rc, out = self.exec_line()
        self.assertEqual((rc, len(self.posts())), (2, 3))
        self.assertIn("STOPPED: SLEEVE got no answer (RemoteDisconnected(", out)
        self.assertIn("Queued: HG 13349.17, KMLM 11341.25. SLEEVE may have been queued anyway; not sent: HARV.", out)
        self.ex.close()                                      # the executor is not there at all: nothing was queued
        os.remove(self.inbox)
        rc, out = self.exec_line()
        self.assertEqual(rc, 2)
        self.assertIn("STOPPED: HG got no answer (ConnectionRefusedError(", out)
        self.assertIn("Queued: none. HG was NOT queued; not sent: KMLM, SLEEVE, HARV. Nothing is queued: fix the cause "
                      "and paste this line again", out)                # R10: a refused connection queued nothing

    def test_an_error_inside_a_post_is_caught_and_stops(self):
        def boom(*a, **kw):
            raise KeyboardInterrupt
        with unittest.mock.patch("http.client.HTTPConnection.getresponse", boom):
            rc, out = self.exec_line()
        self.assertEqual(rc, 2)
        self.assertIn("STOPPED: HG got no answer (KeyboardInterrupt(''))", out)
        for _ in range(200):                                 # the request left before the answer was asked for:
            if self.posts():                                 # the executor gets it (and queues it) all the same
                break
            time.sleep(0.01)
        self.assertEqual(len(self.posts()), 1)


# ------------------------------------------------------------------ P9 malformed input (item 9)
class P9Malformed(Case):
    """item 9: at 6b122160 an integer too large for a float (json reads one), a "credits" that is not a list
    or values summing to infinity crashed the planner, and smallest_to could scan without bound"""

    def test_num_takes_an_integer_too_large_for_a_float_as_no_number(self):
        self.assertIsNone(ms.num(10 ** 400))
        self.assertIsNone(ms.num(-10 ** 400))
        self.assertEqual(ms.num(10 ** 15), 1e15)

    def test_huge_numbers_in_the_snapshot_or_the_feed_are_refusals(self):
        self.snap["symphonies"][IDS["KMLM"]]["value"] = 10 ** 400
        self.assertIn("KMLM (YPTSJFJwD2ZKfAeYJUbW): value 1000000", self.refused())
        self.snap = snapshot()
        v = view()
        v["book"]["sleeves"]["HG"]["equity"] = 10 ** 400
        self.feed = feed(live=v)
        self.assertIn("the sleeve HG has no usable equity", self.refused())
        self.feed = feed(live=view(funded_usd=10 ** 400))
        self.assertIn("the feed's funded_usd is not a number", self.refused())
        self.feed = feed(live=view(seeded={"HG": {"amount": 10 ** 400}}))
        self.assertIn("the feed's seed of HG is not an amount", self.refused())

    def test_values_that_do_not_sum_to_a_finite_positive_number_are_refused(self):
        for e in VALUES:
            self.snap["symphonies"][IDS[e]]["value"] = 1e308                        # each finite, the sum infinite
        self.assertIn("do not sum to a finite positive number", self.refused())
        self.snap = snapshot()
        self.snap["symphonies"][IDS["HG"]]["value"] = 1e300
        self.snap["symphonies"][IDS["HARV"]]["value"] = 1e-300                       # a share of nothing
        self.assertIn("do not sum to a finite positive number with every engine a share of it", self.refused())

    def test_credits_that_are_not_a_list_are_skipped(self):
        rows = [{"session": "2026-11-10", "credits": 5}, {"session": "2026-11-11", "credits": "HG 500"},
                {"session": "2026-11-12", "credits": {"sleeve": "HG", "amount": 500.0, "kind": "credit"}},
                {"session": "2026-11-12", "credits": [{"sleeve": ["HG"], "amount": 7.0, "kind": "credit", "id": ["x"]},
                                                     {"sleeve": "HG", "amount": "500", "kind": "credit"},
                                                     "junk", None]}]
        self.feed = feed(live=view(history=rows, last_run=None))
        p = self.plan()
        self.assertEqual(p["funded"]["now"], 10007.0)                                # the seeds + the one readable credit

    def test_a_smallest_to_beyond_ten_times_the_book_is_said_and_bounded(self):
        for e in VALUES:
            self.snap["symphonies"][IDS[e]]["value"] = 1.0
        self.snap["symphonies"][IDS["HARV"]]["value"] = 0.0001                       # HARV: 0.003% of Composer
        line = self.refused(to="20000")
        self.assertIn("HARV is already above its Composer share", line)
        self.assertIn("the smallest --to at which every credit is >= 0 is beyond 10x the book ($99,658.50), more than "
                      "this planner takes", line)
        w = {"HG": 1 - 3e-12, "KMLM": 1e-12, "SLEEVE": 1e-12, "HARV": 1e-12}
        t0 = time.monotonic()
        self.assertIsNone(ms.smallest_to(w, EQUITY, 9965.85))
        self.assertLess(time.monotonic() - t0, 1.0)

    def test_dates_out_of_range_are_refusals_or_warnings(self):
        self.snap = snapshot(taken_at="9999-12-31T23:59:59-12:00")
        self.assertIn("no readable taken_at", self.refused())
        self.snap = snapshot()
        v = view()
        v["book"]["marks_asof"] = "9999-12-31T23:59:59-12:00"
        self.feed = feed(live=v)
        self.assertTrue(any("marks have no readable date" in w for w in self.plan()["warnings"]))
        self.feed = feed(live=view(last_session=None, check=dict(view()["check"], session=None)))
        self.assertIn("the book's last session on the feed is not a date (None)", self.refused())


# ------------------------------------------------------------------ P10 the landing sentence (item 10)
class P10Landing(Case):
    def test_the_book_lands_at_the_size_plus_what_its_holdings_move_less_commissions(self):
        code, text = self.run_it()
        self.assertEqual(code, 0)
        self.assertIn("the credits are fixed dollars: the book lands at $50,000.00 plus whatever its current $9,857.33 "
                      "of holdings moves before the session, less that session's commissions", text)
        self.assertEqual(self.plan()["holdings"], round(9965.85 - 108.52, 2))


# ------------------------------------------------------------------ S8 --json
class S8Json(Case):
    def test_json_is_the_same_plan_as_the_text(self):
        p = self.plan()
        code, text = self.run_it()
        self.assertEqual(code, 0)
        self.assertIn(f"CAP: MIRROR_MAX_BOOK_USD = {p['cap']['set']}", text)
        self.assertIn(p["paste"], text.splitlines())
        for r in p["engines"]:
            self.assertIn(f"${r['credit']:,.2f}", text)
        for step in p["steps"]:
            self.assertIn(step, text)
        self.assertEqual(set(p), {"ok", "book", "to", "factor", "note", "session", "paste_until", "paste_windows",
                                  "snapshot", "feed_utc", "marks_asof", "last_session", "health", "engines", "total",
                                  "residual", "holdings", "funded", "cap", "cash", "post_to", "paste", "code", "program",
                                  "steps", "warnings"})
        self.assertIs(p["ok"], True)

    def test_a_refusal_with_json_is_still_the_one_line(self):
        self.feed = feed(live=view(halt={"halted": True}))
        line = self.refused("--json")
        self.assertTrue(line.startswith("MIRROR SCALE REFUSED — book live is not in a state to scale"))


# ------------------------------------------------------------------ S9 read-only
class S9ReadOnly(Case):
    def test_only_the_executor_url_and_the_read_token_are_read_from_the_env(self):
        env = RecordingEnv(ENV)
        code, text = self.run_it(env=env)
        self.assertEqual(code, 0, text)
        self.assertEqual(env.seen, {"MIRROR_EXECUTOR_URL", "MIRROR_READ_TOKEN"})
        self.assertEqual(self.fetches, [("https://exec.example", READ)])

    def test_the_default_reader_is_fetch_feed_asking_the_whole_history(self):
        calls = []

        def fake_fetch(url, token, history=30, **kw):
            calls.append((url, token, history))
            return self.feed

        with unittest.mock.patch.object(ms.mp, "fetch_feed", fake_fetch):
            code, text = ms.run(["--to", "50000", "--snapshot", self.snap_path()], env=dict(ENV), now=NOW)
        self.assertEqual(code, 0, text)
        self.assertEqual(calls, [("https://exec.example", READ, 120)])

    def test_no_connection_and_no_file_written(self):
        import http.client
        import socket
        import urllib.request

        def no(*a, **kw):
            raise AssertionError("the planner opened a connection")

        real_open = builtins.open

        def read_only_open(file, mode="r", *a, **kw):
            if any(c in mode for c in "wax+"):
                raise AssertionError(f"the planner wrote {file}")
            return real_open(file, mode, *a, **kw)

        path = self.snap_path()
        with unittest.mock.patch.object(urllib.request, "urlopen", no), \
                unittest.mock.patch.object(http.client.HTTPConnection, "connect", no), \
                unittest.mock.patch.object(socket, "create_connection", no), \
                unittest.mock.patch.object(builtins, "open", read_only_open):
            code, text = ms.run(["--to", "50000", "--snapshot", path], env=dict(ENV), fetch=self.fetch, now=NOW)
        self.assertEqual(code, 0, text)


# ------------------------------------------------------------------ S10 the output and the doc
class S10OutputAndDoc(Case):
    def test_the_steps_come_in_order_with_the_cap_and_the_blackout(self):
        code, text = self.run_it()
        self.assertEqual(code, 0)
        at = [text.index(x) for x in ("STEPS, in order:", "(a) Render -> ibkr-executor -> Environment: set "
                                      "MIRROR_MAX_BOOK_USD = 53000, then \"Save, rebuild and deploy\"",
                                      "(b) When the executor is back", "\npython3 -c 'exec(",
                                      "(c) The executor applies them at the decision of 2026-11-13 (15:54 ET",
                                      "(d) That night's parity check against Composer (mirror_parity.py) removes "
                                      "the operator credits")]
        self.assertEqual(at, sorted(at))
        self.assertIn("Never between 15:15 and 16:05 ET (12:15-13:05 ET on a half-day: 2026-11-27, 2026-12-24)", text)
        self.assertIn("NOT retried", text)
        self.assertIn("approve the IB Key push", text)
        self.assertIn("paste this ONE line, ONCE, before 15:00 ET on a weekday (12:00 on a half-day: 2026-11-27, "
                      "2026-12-24) or any time on a weekend, by 15:00 ET on Fri 2026-11-13, for the session of 2026-11-13",
                      text)
        self.assertIn("sends it ONLY to the executor in that same container (http://127.0.0.1:$PORT/mirror/credit", text)

    def test_the_half_days_named_are_the_coming_ones(self):
        later = datetime.datetime(2026, 12, 1, 15, 0, tzinfo=datetime.timezone.utc)
        self.assertIn("half-day: 2026-12-24, 2027-11-26)", ms.quiet_window(later))

    def test_the_doc_has_the_scaling_section(self):
        with open(os.path.join(REPO, "composer", "IBKR_MIRROR.md")) as f:
            doc = f.read()
        self.assertTrue("\n## Scaling the live book\n" in doc, "IBKR_MIRROR.md has no section \"Scaling the live book\"")
        sec = doc.split("## Scaling the live book")[1].split("\n## ")[0]
        text = " ".join(sec.split())
        for words in ("scripts/mirror_scale.py --to", "MIRROR_MAX_BOOK_USD", "connection fix", "two clean sessions",
                      "sell-then-buy", "15:15", "16:05", "Shell", "EXEC_TOKEN", "NOT retried", "15:54", "parity",
                      "read-only",
                      # the line's rules (the second review)
                      "plain python3", "http://127.0.0.1:$PORT/mirror/credit", "never leaves the container",
                      "before 15:00 ET on a weekday", "12:00 on a half-day", "any time on a weekend",
                      "the evening POLICY routine never sizes a transfer on pre-credit equity", "NOTHING SENT",
                      "any request is queued", "to the cent", "STOPPED", "cannot be withdrawn",
                      "re-run the planner", "post-trade check",
                      "the dividends due", "max($100, 0.5% of the credits)", "LARGEST credit"):
            self.assertIn(words, text, words)
        for stale in ("/opt/executor/venv/bin/python3", "httpx", "https://<executor>/mirror/credit"):
            self.assertNotIn(stale, text, stale)


# ------------------------------------------------------------------ the third review (R1-R12; R11, R12: twins)
class R0WhatTheLineReads(unittest.TestCase):
    """the executor's lines the new paste-time checks read, pinned (each unique in its file): the state file's
    book layout, the frozen list, the halt file and its rules, the drain's order, and the credit route, whose
    every 4xx is raised before the request is queued (R10's 'NOT queued')"""
    PINS = {
        ("ibkr-executor", "app", "mirror.py"): (
            '"seeded": {}, "frozen": [], "run": None,',
            'return f"{self.cfg.state_path}.halt"',
            'self._halt = h if isinstance(h, dict) else {"halted": True, "reason": "unreadable halt file"}',
            'self._halt = {"halted": True, "reason": f"unreadable halt file: {one_line(exc)}", "ts": _iso(self.clock())}',
            'return bool(h.get("flatten") and not h.get("flatten_done") and not h.get("flatten_cancelled"))',
            'self._save() # on disk in the state BEFORE the inbox forgets them',
            's.cash += cash self.state["check"] = None',
            'self.state["frozen"] = list(self.state.get("frozen") or []) + [name]',
            'if sleeve not in self.cfg.engines: raise ValueError(f"{sleeve!r} is not a sleeve of the {self.cfg.name} book")',
        ),
        ("ibkr-executor", "app", "mirror_core.py"): (
            'return {"schema": SCHEMA, "sleeves": [s.to_dict() for s in self.sleeves.values()]}',
            'return {"name": self.name, "cash": self.cash, "shares": dict(self.shares), "rule": self.rule,',
        ),
        ("ibkr-executor", "app", "service.py"): (
            '_mirror_off_404() _auth(x_exec_token, token) book = _mirror_book(body.get("book")) try: req = book.request_credit(',
            'except (ValueError, TypeError) as exc: raise HTTPException(status_code=400, detail=str(exc)) return {"ok": True, '
            '"book": book.cfg.name, "request": req, "note": "queued; applied before the next session\'s plan"}',
            'raise HTTPException(status_code=401, detail="bad exec token")',
        ),
    }

    def test_the_executor_still_writes_what_the_line_reads(self):
        if not os.path.isdir(os.path.join(REPO, "ibkr-executor")):
            self.skipTest("ibkr-executor/ is not in this checkout")
        for path, pins in self.PINS.items():
            src = flat(*path)
            for text in pins:
                with self.subTest(file="/".join(path), pin=text[:60]):
                    self.assertEqual(src.count(text), 1, f"{text!r} occurs {src.count(text)} times in {'/'.join(path)}")


class R1PostTradeCheckAtPaste(LineCase):
    """item 1(a): at 1de7535c the line never read the post-trade check: an /mirror/adjust applied between the
    plan and the paste (it clears the check: mirror.py _adjust) still let it queue all four (the e2e run's K5:
    HG landed $499 above its target)"""

    def test_a_check_that_is_not_the_plans_done_and_clean_sends_nothing(self):
        for chk in (None, {"session": "2026-11-11", "done": True, "problems": []},
                    {"session": "2026-11-12", "done": False, "problems": []},
                    {"session": "2026-11-12", "problems": []},
                    {"session": "2026-11-12", "done": True, "problems": ["BIL: book 37, account 36"]},
                    {"session": "2026-11-12", "done": True, "problems": "BOXX off"}, "done"):
            with self.subTest(check=chk):
                self.write_state(check=chk)
                rc, out = self.exec_line()
                self.assertEqual((rc, self.posts()), (1, []), out)
                self.assertTrue(out.startswith("NOTHING SENT: "), out)
                if not isinstance(chk, str):
                    self.assertIn(f"no clean post-trade check of 2026-11-12: {RERUN} after the next session", out)

    def test_the_twins_the_plans_check_done_and_clean_sends(self):
        for chk in ({"session": "2026-11-12", "done": True, "problems": []}, {"session": "2026-11-12", "done": True},
                    {"session": "2026-11-12", "done": True, "problems": None, "strikes": 1}):
            with self.subTest(check=chk):
                if os.path.exists(self.inbox):
                    os.remove(self.inbox)
                self.ex.requests.clear()
                self.write_state(check=chk)
                self.assertEqual(self.exec_line()[0], 0)
                self.assertEqual(len(self.posts()), 4)


class R2HaltAtPaste(LineCase):
    """item 1(b): at 1de7535c the line never read <state>.halt: it queued the credits on a halted book (the e2e
    run's HALT1), which runs no session until /mirror/resume. A halt file that cannot be read, or is not a
    record, is a halt to the executor (mirror.py _load), so to the line too"""

    def halt(self, h):
        with open(self.state + ".halt", "w") as f:
            f.write(h if isinstance(h, str) else json.dumps(h))

    def test_a_halt_or_a_flatten_pending_sends_nothing(self):
        for h in ({"halted": True, "reason": "operator halt", "by": "operator", "ts": "2026-11-13T14:00:00Z"},
                  {"halted": True, "flatten": True, "flatten_done": False, "flatten_cancelled": False},
                  {"halted": False, "flatten": True, "flatten_done": False},          # a flatten still wanted
                  "[not json", [1], None):
            with self.subTest(halt=h):
                self.halt(h)
                rc, out = self.exec_line()
                self.assertEqual((rc, self.posts()), (1, []), out)
                self.assertIn(f"the book is halted or flattening: {RERUN} after it resumes", out)

    def test_the_twins_resumed_cancelled_or_finished_sends(self):
        for h in ({"halted": False, "resumed_ts": "2026-11-13T14:30:00Z"},
                  {"halted": False, "flatten": True, "flatten_done": False, "flatten_cancelled": True},
                  {"halted": False, "flatten": True, "flatten_done": True}, {}):
            with self.subTest(halt=h):
                if os.path.exists(self.inbox):
                    os.remove(self.inbox)
                self.ex.requests.clear()
                self.halt(h)
                rc, out = self.exec_line()
                self.assertEqual((rc, len(self.posts())), (0, 4), out)


class R3RunAtPaste(LineCase):
    """item 1(c): at 1de7535c an open run (a stuck one keeps last_session where the plan saw it) let the line
    queue behind it"""

    def test_an_open_run_sends_nothing(self):
        self.write_state(run={"session": "2026-11-13", "phase": "buys", "orders": {}})
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []), out)
        self.assertIn(f"a run is open: {RERUN} after it", out)


class R4FrozenAtPaste(LineCase):
    """item 1(d): at 1de7535c a sleeve frozen or dropped after the deploy of step (a) (taken out of
    MIRROR_LIVE_ENGINES: mirror.py _reconcile_sleeves) got the first credits queued and the next one refused
    400 - a 3-of-4 set that cannot be withdrawn (the e2e run's FROZEN)"""

    def test_a_sleeve_it_credits_frozen_or_gone_sends_nothing(self):
        self.write_state(frozen=["HARV"])
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []), out)
        self.assertIn(f"HARV frozen or not in the book: {RERUN}", out)
        self.write_state()
        st = json.load(open(self.state))
        st["book"]["sleeves"] = [r for r in st["book"]["sleeves"] if r["name"] != "KMLM"]
        json.dump(st, open(self.state, "w"))
        rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []), out)
        self.assertIn(f"KMLM frozen or not in the book: {RERUN}", out)

    def test_the_twin_a_frozen_sleeve_it_does_not_credit_sends(self):
        line, code, _ = ms.paste_line("live", [("HG", 10.5)], "scale-up to $10,000 at Composer's split of 2026-11-12",
                                      "2026-11-13", "2026-11-12", WIDE, "15:00 ET on Fri 2026-11-13",
                                      "mirror_scale.py --to 10000")
        self.write_state(frozen=["KMLM"])
        rc, out = self.exec_line(code=code)
        self.assertEqual((rc, len(self.posts())), (0, 1), out)


class R5TodaysSessionStillToRun(Case):
    """item 2: at 1de7535c a plan made on a session day from its paste cutoff, before that day's session ran,
    was printed for the NEXT session: its line was blocked until midnight and then refused, because today's
    session ran in between (the e2e run's T-dead; on the half-day, credit_session(last 11-25, Fri 11-27
    12:30 ET) gave Mon 11-30 while Friday's 12:54 session was still to run)"""

    def at(self, last, *ymdhm):
        self.feed = feed(live=view(last_session=last, check=dict(view()["check"], session=last)))
        return datetime.datetime.fromtimestamp(et(*ymdhm), UTC)

    def test_a_plan_past_the_cutoff_before_that_days_session_is_refused(self):
        for last, when in (("2026-11-11", (2026, 11, 12, 15, 0)), ("2026-11-11", (2026, 11, 12, 15, 30)),
                           ("2026-11-11", (2026, 11, 12, 16, 0)), ("2026-11-11", (2026, 11, 12, 23, 59)),
                           ("2026-11-10", (2026, 11, 12, 15, 30)),                 # a session missed before: today's still runs
                           ("2026-11-25", (2026, 11, 27, 12, 30)),                 # the half-day (13:00 close; Thanksgiving before)
                           ("2026-11-25", (2026, 11, 27, 12, 0)),
                           ("2026-12-23", (2026, 12, 24, 12, 59))):               # Christmas Eve, a half-day
            with self.subTest(last=last, et=when):
                line = self.refused(now=self.at(last, *when))
                self.assertIn("MIRROR SCALE REFUSED — today's session has not run yet: re-run after it and its post-trade "
                              "check (if the executor missed today's session, re-run after midnight ET). "
                              f"It is {when[3]:02d}:{when[4]:02d} ET on {when[0]}-{when[1]:02d}-{when[2]:02d}", line)
                self.assertIn(f"the book's last session is {last}", line)
        self.assertIsNone(ms.session_still_to_run("2026-11-12", datetime.datetime.fromtimestamp(et(2026, 11, 12, 15, 30), UTC)))
        self.assertEqual(ms.session_still_to_run("2026-11-25", datetime.datetime.fromtimestamp(et(2026, 11, 27, 12, 30), UTC)),
                         "2026-11-27")

    def test_the_twins_plan_for_the_session_that_comes_next(self):
        for last, when, session in (("2026-11-11", (2026, 11, 12, 14, 59), "2026-11-12"),   # before the cutoff: today's
                                    ("2026-11-12", (2026, 11, 12, 17, 0), "2026-11-13"),    # today's ran
                                    ("2026-11-25", (2026, 11, 26, 16, 0), "2026-11-27"),    # Thanksgiving: no session that day
                                    ("2026-11-25", (2026, 11, 27, 11, 59), "2026-11-27"),   # the half-day's morning
                                    ("2026-11-27", (2026, 11, 27, 13, 30), "2026-11-30"),   # the half-day's session ran
                                    ("2026-11-13", (2026, 11, 14, 10, 0), "2026-11-16")):   # a weekend
            with self.subTest(last=last, et=when):
                self.assertEqual(self.plan(now=self.at(last, *when))["session"], session)


class R6MalformedDollars(Case):
    """item 3: at 1de7535c a finite but absurd dollar figure on the feed (1e308) made need x (1 + headroom) x 100
    infinite: int(round(inf)) raised an OverflowError that run() did not catch - a traceback, not the one
    refusal line; a book cash or a due dividend of 1e308 printed an exit-0 plan with a $1e308 cash minimum"""

    def test_implausible_dollar_figures_are_one_line_refusals_never_a_traceback(self):
        def due(total):
            return div(ex="2026-11-10", pay="2026-11-12", total=total)
        cases = (
            ("a seed of 1e308", dict(seeded=dict(view()["seeded"], HG={"amount": 1e308, "utc": "x"})),
             "the feed's seed of HG is not an amount from 0 to $1,000,000,000.00"),
            ("two seeds of 1e308 (an infinite sum)", dict(seeded=dict(view()["seeded"], HG={"amount": 1e308},
                                                                     KMLM={"amount": 1e308})), "the feed's seed of"),
            ("seeds within $1e9 each that sum beyond it", dict(seeded={"HG": {"amount": 9e8}, "KMLM": {"amount": 9e8}}),
             "the feed's seeds and operator credits total 1800000000.0: not a plausible amount"),
            ("a published funded_usd of 1e308", dict(funded_usd=1e308),
             "the feed's funded_usd is not a number of dollars from 0 to $1,000,000,000.00 (1e+308)"),
            ("an operator credit of 1e308 in a session row",
             dict(last_run={"session": "2026-11-12", "credits": [{"kind": "credit", "sleeve": "HG", "amount": 1e308,
                                                                   "id": "c1"}]}),
             "an operator credit in the feed's session row of 2026-11-12 is not a plausible amount (1e+308)"),
            ("an operator credit too large for a float", dict(last_run={"session": "2026-11-12", "credits": [
                {"kind": "credit", "sleeve": "HG", "amount": 10 ** 400}]}), "is not a plausible amount (1000000"),
            ("an operator debit of -1e308", dict(last_run={"session": "2026-11-12", "credits": [
                {"kind": "credit", "sleeve": "HG", "amount": -1e308}]}), "is not a plausible amount (-1e+308)"),
            ("a due dividend of 1e308", dict(dividends_open=[due(1e308)]),
             "the dividends due on the feed by 2026-11-13 total 1e+308: not a plausible amount"),
            ("two due dividends of 1e308 (an infinite sum)", dict(dividends_open=[due(1e308), due(1e308)]),
             "the dividends due on the feed by 2026-11-13 total inf: not a plausible amount"),
        )
        for why, over, words in cases:
            with self.subTest(why=why):
                self.feed = feed(live=view(**over))
                self.assertIn(words, self.refused())
        for cash in (1e308, -1e308):
            with self.subTest(book_cash=cash):
                v = view()
                v["book"]["cash"] = cash
                self.feed = feed(live=v)
                self.assertIn("the book's cash on the feed is not a number of dollars within $1,000,000,000.00", self.refused())
        self.feed = feed(live=view())
        self.assertIn("--to must be a positive number of dollars up to $1,000,000,000.00", self.refused(to="1e10"))
        with self.assertRaises(ms.Refused):
            ms.cap_to_set(float("inf"), 0.05)
        self.assertTrue(ms.plausible(1e9) and ms.plausible(-1e9) and not ms.plausible(1e9 + 1) and not ms.plausible(True))

    def test_the_twins_large_but_plausible_figures_plan(self):
        self.feed = feed(live=view(funded_usd=123456.78))
        self.assertEqual(self.plan()["funded"]["now"], 123456.78)
        self.feed = feed(live=view(last_run={"session": "2026-11-12", "credits": [
            {"kind": "credit", "sleeve": "HG", "amount": 5000.0, "id": "c1"}]}))
        self.assertEqual(self.plan()["funded"]["now"], 15000.0)


class R7InboxReadFirst(LineCase):
    """item 5: at 1de7535c the line read the state, then the inbox. _drain_inbox saves the state with a request
    BEFORE it rewrites the inbox without it (mirror.py, pinned in R0): a drain between the two reads hid the
    request from both, and the line sent while it was queued"""

    def test_a_drain_between_the_two_reads_cannot_hide_a_request(self):
        req = {"kind": "credit", "sleeve": "HG", "amount": 5.0, "note": "a refund", "id": "credit-9"}
        self.write_state(inbox=[req])
        real_open, seen = builtins.open, []

        def drain():                                   # the executor's order: the state first, then the inbox
            st = json.load(real_open(self.state))
            st["requests"] = [req]
            with real_open(self.state, "w") as f:
                json.dump(st, f)
            with real_open(self.inbox, "w") as f:
                json.dump([], f)

        def opener(file, *a, **kw):
            if file in (self.state, self.inbox):
                seen.append(file)
                if len(seen) == 2:
                    drain()                            # lands between the line's two reads
            return real_open(file, *a, **kw)

        with unittest.mock.patch.object(builtins, "open", opener):
            rc, out = self.exec_line()
        self.assertEqual(seen[:2], [self.inbox, self.state])
        self.assertEqual((rc, self.posts()), (1, []), out)
        self.assertIn("credit HG credit-9", out)


class R8R9TokenNeverOnScreen(LineCase):
    """item 5: at 1de7535c a token http.client could not put in a header (a character outside Latin-1, a CR or
    LF) was printed in full in the STOPPED line (repr(e) of the error carries the header value); now such a
    token sends nothing and is never printed, and every error is printed as its type and message with the
    token masked"""
    CANARY = "EXEC-CANARY-q7Zp9xV2"

    def test_a_token_that_is_not_printable_ascii_sends_nothing_and_is_never_printed(self):
        for tok in (self.CANARY + "€", self.CANARY + "\r\n", self.CANARY + "\n", "\t" + self.CANARY, self.CANARY + "é"):
            with self.subTest(token=tok[-3:]):
                rc, out = self.exec_line(dict(self.env, EXEC_TOKEN=tok))
                self.assertEqual((rc, self.posts()), (1, []), out)
                self.assertIn("NOTHING SENT: EXEC_TOKEN is not printable ASCII", out)
                self.assertNotIn(self.CANARY, out)
        if shutil.which("bash"):                       # as pasted: the shell, a separate python3
            env = dict(self.env, PATH=os.environ.get("PATH", "/usr/bin:/bin"), EXEC_TOKEN=self.CANARY + "€")
            line, _, _ = ms.paste_line("live", list(CREDITS.items()), self.p["note"], "2026-11-13", "2026-11-12", WIDE,
                                       "15:00 ET on Fri 2026-11-13", "mirror_scale.py --to 50000")
            r = subprocess.run(["bash", "-c", line], env=env, capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
            self.assertEqual((r.returncode, self.posts()), (1, []), r.stdout + r.stderr)
            self.assertNotIn(self.CANARY, r.stdout + r.stderr)

    def test_an_error_that_carries_the_token_is_printed_with_it_masked(self):
        tok = self.env["EXEC_TOKEN"]

        def boom(*a, **kw):
            raise ValueError(f"Invalid header value b'{tok}'")
        with unittest.mock.patch("http.client.HTTPConnection.request", boom):
            rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (2, []), out)
        self.assertIn("STOPPED: HG got no answer (ValueError(\"Invalid header value b'***'\"))", out)
        self.assertNotIn(tok, out)

        def bad_load(f, *a, **kw):                     # a reader error that would carry it
            raise ValueError(f"cannot parse {tok}")
        with unittest.mock.patch("json.load", bad_load):
            rc, out = self.exec_line()
        self.assertEqual((rc, self.posts()), (1, []), out)
        self.assertIn(f"{self.state} unreadable (ValueError('cannot parse ***'))", out)
        self.assertNotIn(tok, out)


class R10StoppedSaysWhatWasNotQueued(LineCase):
    """item 5: at 1de7535c the STOPPED line said the failed credit 'may have been queued anyway' even when the
    cause proves it was not - a 4xx (the credit route raises every one before request_credit queues: pinned in
    R0) or a refused connection - and sent the owner to wait for a session with nothing queued"""

    def fresh(self, answers):
        if os.path.exists(self.inbox):
            os.remove(self.inbox)
        self.ex.requests.clear()
        self.ex.answers = answers

    def test_a_4xx_or_a_refused_connection_is_not_queued(self):
        for status in (401, 400, 404, 422):
            with self.subTest(status=status):
                self.fresh([(status, '{"detail": "no"}')])
                rc, out = self.exec_line()
                self.assertEqual((rc, len(self.posts())), (2, 1), out)
                self.assertIn(f"STOPPED: HG answered HTTP {status}. Queued: none. HG was NOT queued; not sent: KMLM, SLEEVE, "
                              f"HARV. Nothing is queued: fix the cause and paste this line again", out)
        self.fresh([])                                 # ... and it is so: the same line, pasted again, sends
        self.assertEqual(self.exec_line()[0], 0)
        self.assertEqual(len(self.posts()), 4)
        self.fresh([(200, None)] * 3 + [(400, '{"detail": "\'HARV\' is not a sleeve of the live book"}')])
        rc, out = self.exec_line()
        self.assertEqual((rc, len(self.posts())), (2, 4), out)
        self.assertIn("STOPPED: HARV answered HTTP 400. Queued: HG 13349.17, KMLM 11341.25, SLEEVE 10440.19. HARV was NOT "
                      f"queued; not sent: none. What is queued applies at the next session and cannot be withdrawn: after "
                      f"it, {RERUN}", out)
        self.fresh([])
        rc, out = self.exec_line(dict(self.env, PORT=str(self._dead_port())))
        self.assertEqual(rc, 2, out)
        self.assertIn("STOPPED: HG got no answer (ConnectionRefusedError(", out)
        self.assertIn("HG was NOT queued; not sent: KMLM, SLEEVE, HARV. Nothing is queued: fix the cause and paste this "
                      "line again", out)

    def test_the_twins_a_5xx_a_redirect_or_no_answer_may_have_been_queued(self):
        for answers, why in (([(500, '{"detail": "x"}')], "answered HTTP 500"), ([(503, "")], "answered HTTP 503"),
                             ([("redirect", "http://127.0.0.1:9/")], "answered HTTP 302"),
                             (["drop"], "got no answer (RemoteDisconnected(")):
            with self.subTest(why=why):
                self.fresh(answers)
                rc, out = self.exec_line()
                self.assertEqual(rc, 2, out)
                self.assertIn(f"STOPPED: HG {why}", out)                 # (in the words 1de7535c used too)
                self.assertIn("HG may have been queued anyway; not sent: KMLM, SLEEVE, HARV.", out)
                self.assertIn("applies at the next session and cannot be withdrawn: after it, re-run", out)

    @staticmethod
    def _dead_port():
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port


class R11MutationGaps(LineCase):
    """item 5, the reviewers' surviving mutants (twins: these pass at 1de7535c and fail on the mutant): dropping
    the line's live-flag check, and the give-up boundary of a dividend with no pay date (>= made >)"""

    def test_a_state_named_live_whose_live_flag_is_false_sends_nothing(self):
        for flag in (False, None, 0):
            with self.subTest(live=flag):
                self.write_state(live=flag)
                rc, out = self.exec_line()
                self.assertEqual((rc, self.posts()), (1, []), out)
                self.assertIn(f"{self.state} is not the live book", out)

    def test_a_receivable_with_no_pay_date_exactly_the_give_up_days_after_its_ex_date_is_in_the_cash_minimum(self):
        ex = (datetime.date(2026, 11, 13) - datetime.timedelta(days=ms.PAY_DATE_GIVE_UP_DAYS)).isoformat()
        self.feed = feed(live=view(dividends_open=[div(ex=ex, pay=None, total=3.3)]))
        c = self.plan()["cash"]
        self.assertEqual((c["dividends"], [r["due"] for r in c["dividends_due"]]), (3.3, ["2026-11-10"]))
        self.feed = feed(live=view(dividends_open=[div(ex="2026-11-04", pay=None, total=3.3)]))   # a day short of it
        self.assertEqual(self.plan()["cash"]["dividends"], 0.0)


class R12LineLength(Case):
    """the hard limit (a twin: it holds at 1de7535c too): the printed line stays under a canonical terminal
    line, TTY_LINE_MAX bytes, for every plan of a 45-day sweep of plan times (every hour at :10 from Fri
    2026-11-13 00:10 ET: Thanksgiving and its half-day, Christmas Eve's half-day, Christmas, New Year's Day),
    the book's last session the latest one finished by then; at $50,000 and at just under 10x the book (the
    longest note and amounts), and for a book five times larger at just under 10x it (a later scale-up)"""

    @staticmethod
    def last_session_at(now):
        e = sr.et_now(now)
        d = e.date()
        while True:
            if d.weekday() < 5 and d.isoformat() not in sr.NYSE_HOLIDAYS:
                end = (13, 5) if d.isoformat() in sr.HALF_DAYS else (16, 5)
                if d < e.date() or (e.hour, e.minute) >= end:
                    return d.isoformat()
            d -= datetime.timedelta(days=1)

    @staticmethod
    def scaled(k, **over):
        v = view(**over)
        for s in v["book"]["sleeves"].values():
            s["equity"], s["cash"] = round(s["equity"] * k, 2), round(s["cash"] * k, 2)
        v["book"]["equity"], v["book"]["cash"] = round(v["book"]["equity"] * k, 2), round(v["book"]["cash"] * k, 2)
        v["seeded"] = {e: dict(r, amount=r["amount"] * k) for e, r in v["seeded"].items()}
        return v

    def test_the_longest_line_of_a_45_day_sweep_fits_a_terminal_line(self):
        start = datetime.datetime(2026, 11, 13, 5, 10, tzinfo=UTC)
        worst, n = (0, None), 0
        for k in range(45 * 24):
            now = start + datetime.timedelta(hours=k)
            last = self.last_session_at(now)
            over = dict(last_session=last, check=dict(view()["check"], session=last),
                        history=[{"session": last, "outcome": "traded", "credits": []}],
                        last_run={"session": last, "outcome": "traded", "credits": []})
            for book, to in ((view(**over), "50000"), (view(**over), "99658.49"), (self.scaled(5, **over), "498292.49")):
                self.feed = feed(live=book)
                code, text = self.run_it("--json", to=to, now=now)
                if code:
                    self.assertIn("today's session has not run yet", text)
                    continue
                p = json.loads(text)
                n += 1
                size = len(p["paste"].encode())
                if size > worst[0]:
                    worst = (size, f"{sr.et_now(now):%a %Y-%m-%d %H:%M} ET, --to {to}, {len(p['paste_windows'])} window(s)")
        margin = ms.TTY_LINE_MAX - worst[0]
        sys.stderr.write(f"\n  R12: {n} plans; the longest pasted line is {worst[0]} bytes ({worst[1]}): {margin} bytes "
                         f"under the {ms.TTY_LINE_MAX}-byte terminal line\n")
        self.assertGreater(n, 3000)
        self.assertLessEqual(worst[0], ms.TTY_LINE_MAX)
        self.assertGreaterEqual(margin, 32, "keep a margin for longer amounts: compact the line, never drop a check")


class R13DocSaysIt(unittest.TestCase):
    def test_the_scaling_section_has_the_third_reviews_rules(self):
        with open(os.path.join(REPO, "composer", "IBKR_MIRROR.md")) as f:
            sec = " ".join(f.read().split("## Scaling the live book")[1].split("\n## ")[0].split())
        for words in ("today's session has not run yet: re-run after it and its post-trade check",
                      "not finite or is beyond $1,000,000,000", "not printable ASCII (it is never printed)",
                      "its inbox, read first", "while the book is halted or a flatten is pending (its halt file), a run "
                      "is open, or a sleeve it credits is frozen or no longer in the book",
                      "post-trade check of the plan's last session is still on record, done and clean",
                      "whether the one that failed was NOT queued (an HTTP 4xx", "or nothing listening on PORT",
                      "Nothing queued at all: fix the cause and paste the line again",
                      "printed as its type and message with the token masked",
                      "the credited cash was only partly invested", "the holdings still are compared",
                      "A leg below $1 even once they are applied is below $1 at the mirror's size: nothing is sent, exit 0"):
            self.assertIn(words, sec, words)


# ------------------------------------------------------------------ the fourth review (2026-11-13; R14, R15: pins)
class R14NeedBeyondTheBound(Case):
    """its V2 - a MUTATION PIN, not a regression gate (it passes at 170191c0; it kills mutant P13, the need's
    bound removed): funded_usd within $1e9 plus credits that take the need beyond it is the one refusal line,
    never a plan carrying a ~$2e9 cap"""

    def test_funded_near_the_bound_plus_the_credits_is_refused(self):
        v = R12LineLength.scaled(12000.0)                    # a book of ~$119.6M: --to up to 10x it is accepted
        v["funded_usd"] = 9.9e8
        self.feed = feed(live=v)
        text = self.refused(to="999000000")
        self.assertIn("is not a plausible amount (more than $1,000,000,000.00): the cap cannot be computed", text)


class R15DoneMustBeTrue(LineCase):
    """its V3 - a MUTATION PIN (passes at 170191c0; kills mutant L10, the line's `done is True` relaxed to truthy):
    a post-trade check whose done is truthy but not True sends nothing - the line is exactly as strict as the
    planner (check_problem: done is not True -> refused). The executor writes a bool (mirror.py _post_check)"""

    def test_a_truthy_done_that_is_not_true_sends_nothing(self):
        for done in (1, "yes", [1]):
            with self.subTest(done=done):
                self.write_state(check={"session": "2026-11-12", "done": done, "problems": []})
                rc, out = self.exec_line()
                self.assertEqual((rc, self.posts()), (1, []), out)
                self.assertIn("no clean post-trade check of 2026-11-12", out)


def scaling_section():
    with open(os.path.join(REPO, "composer", "IBKR_MIRROR.md")) as f:
        return " ".join(f.read().split("## Scaling the live book")[1].split("\n## ")[0].split())


class R16MissedSessionRefusal(Case):
    """its NOTE 1 (a GATE: fails at 170191c0): the plan-time refusal also fires on a session day whose decision
    window passed without the executor recording the session (its gateway down through it: mirror.py returns on
    `ad is None` before _session and _skip), when no session will run today: the refusal says to re-run after
    midnight ET then. The twin: after midnight such a day plans for the next session"""

    def test_the_refusal_says_what_to_do_when_the_executor_missed_todays_session(self):
        for last, when in (("2026-11-13", (2026, 11, 16, 16, 30)),          # Mon: its session was missed
                           ("2026-11-12", (2026, 11, 13, 15, 0)),           # Fri, before its session
                           ("2026-11-25", (2026, 11, 27, 12, 30))):         # the half-day
            with self.subTest(last=last, et=when):
                self.feed = feed(live=view(last_session=last, check=dict(view()["check"], session=last)))
                line = self.refused(now=datetime.datetime.fromtimestamp(et(*when), UTC))
                self.assertIn("MIRROR SCALE REFUSED — today's session has not run yet: re-run after it and its "
                              "post-trade check (if the executor missed today's session, re-run after midnight ET). "
                              f"It is {when[3]:02d}:{when[4]:02d} ET on {when[0]}-{when[1]:02d}-{when[2]:02d}", line)
        self.assertIn("(\"today's session has not run yet: re-run after it and its post-trade check (if the executor "
                      "missed today's session, re-run after midnight ET)\"", scaling_section())
        self.assertIn("(if the executor missed today's session, re-run after midnight ET)", " ".join(ms.__doc__.split()))

    def test_the_twin_after_midnight_the_missed_day_plans_for_the_next_session(self):
        self.feed = feed(live=view(last_session="2026-11-13", check=dict(view()["check"], session="2026-11-13")))
        p = self.plan(now=datetime.datetime.fromtimestamp(et(2026, 11, 17, 0, 30), UTC))      # Tue 00:30 ET
        self.assertEqual((p["session"], p["last_session"]), ("2026-11-17", "2026-11-13"))


class R17StepAChangesOnlyTheCap(Case):
    """its NOTE 4 (a GATE: fails at 170191c0): step (a)'s deploy changes MIRROR_MAX_BOOK_USD only. A sleeve it drops
    from MIRROR_LIVE_ENGINES stays in the book's state, not frozen, until the executor's first tick with the IB
    gateway logged in (mirror.py _reconcile_sleeves, after `ad is None`), and /mirror/credit refuses it (400): a line
    pasted before then queues only the credits before that sleeve in the line's order (HG, KMLM, SLEEVE, HARV) and
    stops there, the ones after it not sent (the e2e runs' FRZ2, HARV dropped, and FRZ3, each sleeve dropped in
    turn). The twin pins the executor's lines this rests on"""
    STOPS = ("so a line pasted before then queues only the credits before that sleeve in the line's order (HG, KMLM, "
             "SLEEVE, HARV) and stops there; the ones after it are not sent.")
    WORDS = ("Change only MIRROR_MAX_BOOK_USD in that deploy, not MIRROR_LIVE_ENGINES: a sleeve it drops stays in the "
             "book's state, not frozen, until the executor's first tick with the IB gateway logged in")

    def test_the_plan_and_the_doc_say_to_change_only_the_cap(self):
        step = self.plan()["steps"][0]
        self.assertTrue(step.startswith("(a) Render -> ibkr-executor -> Environment: set MIRROR_MAX_BOOK_USD = 53000, "
                                        "then \"Save, rebuild and deploy\". " + self.WORDS + ", " + self.STOPS
                                        + " Never between"), step)
        self.assertNotIn("queues the other credits", step)
        code, text = self.run_it()
        self.assertEqual(code, 0)
        self.assertIn(self.WORDS, text)
        a = scaling_section().split("(a) The cap.")[1].split("(b) The credits.")[0]
        self.assertIn(self.WORDS + " (mirror.py _reconcile_sleeves), " + self.STOPS, a)
        self.assertNotIn("queues the other credits", " ".join(ms.__doc__.split()))
        self.assertIn("would queue only the credits before that sleeve in the line's order (HG, KMLM, SLEEVE, HARV) and "
                      "stop there; the ones after it would not be sent.", " ".join(ms.__doc__.split()))
        self.assertIn("That deploy changes MIRROR_MAX_BOOK_USD only, not MIRROR_LIVE_ENGINES", " ".join(ms.__doc__.split()))

    def test_the_twin_the_executor_freezes_a_dropped_sleeve_only_in_a_tick_with_the_gateway(self):
        with open(os.path.join(REPO, "ibkr-executor", "app", "mirror.py")) as f:
            src = f.read()
        for pin in ('        if ad is None:\n            return\n        if not self.state.get("run"):\n'
                    '            self._reconcile_sleeves(ad)\n',
                    '            raise ValueError("a credit needs a non-zero amount")\n        if sleeve not in '
                    'self.cfg.engines:\n            raise ValueError(f"{sleeve!r} is not a sleeve of the {self.cfg.name} '
                    'book")\n'):
            self.assertEqual(src.count(pin), 1, pin)


class R18ReRunAfterAnyAdjust(Case):
    """its NOTE 5 (a GATE: fails at 170191c0): re-run the planner after ANY /mirror/adjust. A cash adjust applied on
    the evening of the plan's last session is followed by that evening's tick making that session's post-trade
    check again, clean (it compares shares, not cash), so an older line would still send, its credits sized on
    the book before the adjust (the e2e run's ADJ1). The plan's step (b), the module's docstring and
    IBKR_MIRROR.md say it; the twin pins the executor's lines this rests on"""

    def test_the_plan_and_the_doc_say_to_re_run_after_any_adjust(self):
        step = self.plan()["steps"][1]
        self.assertIn("After any /mirror/adjust, re-run this planner and paste only its new line: an adjust on the "
                      "evening of 2026-11-12 is followed by a new post-trade check of 2026-11-12, clean when the shares "
                      "are as booked, so this line would still send, sized on the book before the adjust:", step)
        self.assertIn("Re-run the planner after ANY /mirror/adjust and paste only its new line: an adjust on the evening "
                      "of the plan's last session is followed by that evening's tick making that session's post-trade "
                      "check again - clean when the shares are as booked (it compares shares, not cash) - so an older "
                      "line would still send, its credits sized on the book before the adjust.", scaling_section())
        self.assertIn("Re-run it after ANY /mirror/adjust and paste only the new line", " ".join(ms.__doc__.split()))

    def test_the_twin_the_executor_clears_the_check_on_an_adjust_and_makes_it_again_that_day(self):
        with open(os.path.join(REPO, "ibkr-executor", "app", "mirror.py")) as f:
            src = f.read()
        for pin in ('        s.cash += cash\n        self.state["check"] = None ',
                    '        if self.state.get("last_session") == session:\n            self._post_check(ad, session, wake)\n',
                    '        if chk.get("session") == session and chk.get("done"):\n            return\n'):
            self.assertEqual(src.count(pin), 1, pin)


if __name__ == "__main__":
    unittest.main()
