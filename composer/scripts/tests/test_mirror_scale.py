"""Gate tests for mirror_scale.py: the read-only planner that scales the IBKR mirror's live book at
Composer's split (no network: the feed is injected, the snapshot is a temporary file).

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
      is the smallest); a slipped zero; bad numbers; missing env; a URL the line must not send a token
      to; a feed that cannot be read (no token in the line); nothing to send
  S6  the cap: funded estimate (seeds + operator credits in the session rows, de-duplicated; dividends
      and debits not counted; a published funded_usd wins); need x (1 + headroom) rounded UP to the
      next $500; against the executor's _over_cap semantics (smallest first, cumulative, cap + $1):
      every credit passes at the printed cap, the largest is the one refused just under the need; the
      executor's lines this relies on are pinned in its source; the account-cash figure
  S7  the pasted line: valid Python, run by the executor's own interpreter, the credit URL, the
      X-Exec-Token header, the four fields, safe shell quoting, no token anywhere; executed against
      fakes it POSTs the credits and prints each answer, stops at the first answer that is not 200,
      and sends NOTHING without EXEC_TOKEN, without the state file, with a credit already queued
      (state or inbox), or with a cap that does not cover the executor's own funded_usd + the credits
  S8  --json: the same plan as JSON; a refusal is still the one line
  S9  read-only: the planner reads only MIRROR_EXECUTOR_URL and MIRROR_READ_TOKEN from the env (never
      EXEC_TOKEN), opens no connection but the feed read (fetch_feed, full history), writes no file
  S10 the output: the steps in order with the cap, the deploy blackout and the half-days; the doc
      has "Scaling the live book" with the owner's gates and the steps

Run: python3 -m unittest tests.test_mirror_scale -v   (from composer/scripts)
"""
import builtins
import contextlib
import copy
import datetime
import io
import json
import os
import random
import re
import shlex
import sys
import tempfile
import types
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import mirror_scale as ms  # noqa: E402
import shadow_runner as sr  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
NOW = datetime.datetime(2026, 11, 12, 22, 0, tzinfo=datetime.timezone.utc)          # 17:00 ET, after the session
READ, EXEC = "read-token-BBBBBBBBBBBBBBBBBBBB", "exec-token-CANARY-never-read-by-the-planner"
ENV = {"MIRROR_EXECUTOR_URL": "https://exec.example", "MIRROR_READ_TOKEN": READ, "EXEC_TOKEN": EXEC}
IDS = {"HG": "mbkiXcuNDjueXpiox5Av", "KMLM": "YPTSJFJwD2ZKfAeYJUbW", "SLEEVE": "nNdBk7hc5NiBzeRvbI5T",
       "HARV": "ORQNCfZnA18wmsMWVhf8"}
VALUES = {"HG": 104838.5, "KMLM": 87396.31, "SLEEVE": 81791.0, "HARV": 38395.76}           # Composer, 2026-11-12
EQUITY = {"HG": 3429.2, "KMLM": 2645.67, "SLEEVE": 2649.66, "HARV": 1241.32}              # the live book, 11-12
CREDITS = {"HG": 13349.17, "KMLM": 11341.25, "SLEEVE": 10440.19, "HARV": 4903.54}         # at $50,000


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
         "check": {"done": True, "problems": [], "session": "2026-11-12", "strikes": 0},
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
        for _ in range(300):
            raw = {e: rnd.uniform(200, 9000) for e in EQUITY}
            v = view()
            for e, x in raw.items():
                v["book"]["sleeves"][e]["equity"] = round(x, 2)
            v["book"]["equity"] = round(sum(raw.values()), 2)                    # the executor rounds the SUM
            vals = {e: rnd.uniform(1000, 200000) for e in VALUES}
            w = {e: vals[e] / sum(vals.values()) for e in vals}
            lo = ms.smallest_to(w, {e: round(x, 2) for e, x in raw.items()}, v["book"]["equity"])
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
                                        "split of 2026-11-12"), text[:200])
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
            dividends_open=[{"id": "d1", "status": "open"}], commission_pending=2, waiting_on="the decision at 15:54",
            settings_clamped=["quote_band 0.2 -> 0.05"], brain={"session": {"ok": False}},
            flatten={"id": "20261111T150000", "round": 2, "orders": []},            # a finished flatten's record
            halt={"halted": False, "flatten": True, "flatten_done": True, "resumed_ts": "x"},
            check=None))
        p = self.plan()
        self.assertIn("no account check on the feed yet", p["health"])
        self.feed = feed(live=view(halt={"halted": False, "flatten": True, "flatten_done": False,
                                         "flatten_cancelled": True}))
        self.assertEqual(self.plan()["book"], "live")                            # a cancelled flatten (resumed)


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
        self.assertEqual(low, 10219.11)
        p = self.plan(to=f"{low:.2f}")
        self.assertTrue(all(r["credit"] >= 0 for r in p["engines"]), p["engines"])
        self.assertIn("already above its Composer share", self.refused(to=f"{low - 0.01:.2f}"))

    def test_a_slipped_zero_is_refused(self):
        self.assertIn("50.2x book live's $9,965.85: more than 10x is refused", self.refused(to="500000"))
        self.assertEqual(self.plan(to="99658.5")["factor"], 10.0)                # exactly 10x is allowed

    def test_bad_numbers_are_refused_before_anything_is_read(self):
        for to in ("abc", "nan", "inf", "-5", "0"):
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

    def test_a_url_the_line_must_not_send_the_exec_token_to_is_refused(self):
        for url in ("http://exec.example", "http://localhost:8000", "https://user:pw@exec.example",
                    "https://exec.example/?x=1", "https://exec.example/'a", "ftp://exec.example"):
            with self.subTest(url=url):
                self.assertIn("must be a plain https URL", self.refused(env=dict(ENV, MIRROR_EXECUTOR_URL=url)))
        self.assertEqual(self.fetches, [])
        self.assertEqual(self.plan(env=dict(ENV, MIRROR_EXECUTOR_URL="https://Exec.Example:8443/base/"))["url"],
                         "https://exec.example:8443/base/mirror/credit")

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
        # and drops the largest - which is why the pasted line refuses when credits are already queued
        twice = executor_applies(p["funded"]["now"], p["cap"]["set"], credits + credits)
        self.assertEqual(twice[0], ["HARV", "HARV", "SLEEVE", "SLEEVE", "KMLM"])

    def test_the_executor_still_says_what_the_planner_relies_on(self):
        """the executor's own lines the cap rule, the pasted line and step (c) depend on; a change to any of
        them fails here and the planner is to be re-read against it"""
        ex = os.path.join(REPO, "ibkr-executor")
        if not os.path.isdir(ex):
            self.skipTest("ibkr-executor/ is not in this checkout")

        def src(*path):
            with open(os.path.join(REPO, *path)) as f:
                return " ".join(f.read().split())

        mirror, service, config = (src("ibkr-executor", "app", "mirror.py"), src("ibkr-executor", "app", "service.py"),
                                   src("ibkr-executor", "app", "config.py"))
        for text in (
                "SEED_TOL_USD = 1.0",
                "CASH_TOL_USD = 1.0",
                "if funded + amount <= self._book_cap_usd() + SEED_TOL_USD: return None",
                "cap = _num(self.cfg.max_book_usd) return cap if cap is not None and cap > 0 else self._engines_capital_usd()",
                'rows.sort(key=lambda r: _num(r.get("amount")) if _num(r.get("amount")) is not None else 0.0)',
                "if have is None or self.book.cash() + amt > have + CASH_TOL_USD:",
                'if ok and self.cfg.live and amt > 0 and r.get("force") is not True and self._over_cap(amt):',
                'self.state["funded_usd"] = round(funded + amt, 2)',
                'self.state["requests"] = keep',                             # a refused credit is not kept
                "self._apply_credits(ad, notes, credits)",
                'return f"{self.cfg.state_path}.inbox.json"',
                '"funded_usd": None, "seq": 0',
                '"pending_requests": list(self.state.get("requests") or [])',
                '"seeded": self.state.get("seeded") or {}',
                '"frozen": name in (self.state.get("frozen") or [])',
                '"credits": list(run.get("credits") or [])',
                'credits.append({"sleeve": name, "amount": amt, "kind": "credit", "id": r.get("id"), "note": r.get("note")})',
                'HISTORY_KEEP = 120'):
            self.assertIn(text, mirror)
        self.assertNotIn('"funded_usd": ', mirror.split("def _publish")[1].split("def view")[0],
                         "the feed now publishes funded_usd: the planner uses it; drop the estimate's caveats")
        for text in ('@app.post("/mirror/credit") def mirror_credit(body: dict = Depends(_mirror_body), '
                     'x_exec_token: str | None = Header(default=None),',
                     '_auth(x_exec_token, token) book = _mirror_book(body.get("book"))',
                     'req = book.request_credit(body.get("sleeve"), body.get("amount"), body.get("note") or "",',
                     "if not 0 <= history <= 120:"):
            self.assertIn(text, service)
        self.assertIn('mirror_state_path: str = "./data/mirror_state.json"', config)
        render = src("render.yaml")
        self.assertIn("- key: MIRROR_STATE_PATH value: /app/data/mirror_state.json", render)
        docker = src("ibkr-executor", "Dockerfile")
        self.assertIn("WORKDIR /opt/executor", docker)
        self.assertIn("python3 -m venv venv && ./venv/bin/pip install", docker)
        self.assertTrue(ms.EXEC_PY.startswith("/opt/executor/venv/bin/"))
        self.assertIn("httpx", src("ibkr-executor", "requirements.txt"))
        core = src("ibkr-executor", "app", "mirror_core.py")
        self.assertIn("MAX_IDLE_CASH_FRAC = 0.05", core)                            # step (c): KMLM trades a credit
        self.assertIn("and idle <= MAX_IDLE_CASH_FRAC and gap <= sleeve.corridor:", core)

    def test_the_cash_the_account_must_hold(self):
        p = self.plan()
        self.assertEqual(p["cash"]["book_cash"], 108.52)
        self.assertEqual(p["cash"]["need"], round(108.52 + 40034.15, 2))
        self.assertIn("CASH: the account must hold at least $40,142.67 in cash at the decision", self.run_it()[1])
        v = view()
        v["book"]["cash"] = None
        self.feed = feed(live=v)
        self.assertIn("the book's cash on the feed is not a number", self.refused())


# ------------------------------------------------------------------ S7 the pasted line
class S7PastedLine(Case):
    def setUp(self):
        super().setUp()
        self.p = self.plan()
        self.state = os.path.join(self.tmp.name, "mirror_state.json")
        self.write_state(funded=10000.0)
        self.env = {"EXEC_TOKEN": "exec-in-the-container", "MIRROR_STATE_PATH": self.state,
                    "MIRROR_MAX_BOOK_USD": "53000"}
        self.answers = [(200, '{"ok": true}')]

    def write_state(self, funded=10000.0, requests=(), inbox=None, drop_funded=False):
        st = {"funded_usd": funded, "requests": list(requests), "seq": 42}
        if drop_funded:
            del st["funded_usd"]
        with open(self.state, "w") as f:
            json.dump(st, f)
        if inbox is not None:
            with open(self.state + ".inbox.json", "w") as f:
                json.dump(inbox, f)

    def exec_line(self, env=None):
        posts = []

        def post(url, json=None, headers=None, timeout=None, **kw):
            posts.append({"url": url, "json": json, "headers": dict(headers or {}), "timeout": timeout, "kw": kw})
            status, body = self.answers[min(len(posts), len(self.answers)) - 1]
            return types.SimpleNamespace(status_code=status, text=body)

        fake = types.ModuleType("httpx")
        fake.post = post
        out = io.StringIO()
        with unittest.mock.patch.dict(sys.modules, {"httpx": fake}), \
                unittest.mock.patch.dict(os.environ, self.env if env is None else env, clear=True), \
                contextlib.redirect_stdout(out):
            exec(compile(self.p["code"], "<pasted line>", "exec"), {"__name__": "__main__"})
        return posts, out.getvalue()

    def test_the_line_is_the_executors_python_running_valid_code(self):
        argv = shlex.split(self.p["paste"])
        self.assertEqual(argv, ["/opt/executor/venv/bin/python3", "-c", self.p["code"]])
        compile(self.p["code"], "<pasted line>", "exec")
        self.assertNotIn("'", self.p["code"])                                    # the shell's single quotes hold
        self.assertTrue(self.p["paste"].startswith("/opt/executor/venv/bin/python3 -c '"))
        self.assertTrue(self.p["paste"].endswith("'"))
        self.assertNotIn("\n", self.p["paste"])

    def test_the_line_has_the_url_the_header_the_fields_the_book_and_the_note(self):
        code = self.p["code"]
        self.assertEqual(self.p["url"], "https://exec.example/mirror/credit")
        for text in ('U="https://exec.example/mirror/credit"', 'B="live"', 'headers={"X-Exec-Token":T}',
                     'json={"sleeve":s,"amount":a,"note":N,"book":B}', 'T=E.get("EXEC_TOKEN")',
                     'N="scale-up to $50,000 at Composer\\x27s split of 2026-11-12"',
                     'A=(("HG",13349.17),("KMLM",11341.25),("SLEEVE",10440.19),("HARV",4903.54),)', "D=40034.15",
                     'P=E.get("MIRROR_STATE_PATH") or "./data/mirror_state.json"'):
            self.assertIn(text, code)

    def test_no_token_anywhere(self):
        for argv in ((), ("--json",)):
            code, text = self.run_it(*argv)
            self.assertEqual(code, 0)
            for tok in (READ, EXEC):
                self.assertNotIn(tok, text)
        self.assertNotIn("exec-in-the-container", self.p["code"])

    def test_the_line_posts_each_credit_and_prints_each_answer(self):
        posts, out = self.exec_line()
        self.assertEqual([x["url"] for x in posts], ["https://exec.example/mirror/credit"] * 4)
        self.assertEqual([x["json"] for x in posts],
                         [{"sleeve": e, "amount": a, "note": "scale-up to $50,000 at Composer's split of 2026-11-12",
                           "book": "live"} for e, a in CREDITS.items()])
        self.assertTrue(all(x["headers"] == {"X-Exec-Token": "exec-in-the-container"} for x in posts))
        self.assertTrue(all(x["timeout"] == 30 and not x["kw"] for x in posts))     # no redirect following asked for
        lines = out.strip().splitlines()
        self.assertEqual(lines[:4], [f'{e} {a} 200 {{"ok": true}}' for e, a in CREDITS.items()])
        self.assertEqual(lines[4], "ALL 4 CREDITS QUEUED: the executor applies them at its next session")
        self.assertNotIn("exec-in-the-container", out)

    def test_the_line_stops_at_the_first_answer_that_is_not_200(self):
        self.answers = [(200, '{"ok": true}'), (401, '{"detail": "bad exec token"}'), (200, "{}")]
        posts, out = self.exec_line()
        self.assertEqual(len(posts), 2)
        self.assertIn('KMLM 11341.25 401 {"detail": "bad exec token"}', out)
        self.assertIn("STOPPED at the first answer that is not 200", out)
        self.assertIn("do NOT paste this line again", out)

    def test_the_line_sends_nothing_without_the_token_or_the_state(self):
        env = dict(self.env)
        del env["EXEC_TOKEN"]
        posts, out = self.exec_line(env)
        self.assertEqual(posts, [])
        self.assertIn("NOTHING SENT: EXEC_TOKEN is not set here", out)
        posts, out = self.exec_line(dict(self.env, MIRROR_STATE_PATH=os.path.join(self.tmp.name, "nope.json")))
        self.assertEqual(posts, [])
        self.assertIn("NOTHING SENT: no book state at", out)

    def test_the_line_sends_nothing_when_a_credit_is_already_queued(self):
        queued = {"kind": "credit", "sleeve": "HG", "amount": 13349.17, "id": "credit-1"}
        for where in ("state", "inbox"):
            with self.subTest(where=where):
                self.write_state(requests=[queued] if where == "state" else [], inbox=[queued] if where == "inbox" else [])
                posts, out = self.exec_line()
                self.assertEqual(posts, [])
                self.assertIn("NOTHING SENT: 1 credit(s) already queued, so this line was sent before", out)
                self.assertIn("credit-1", out)
        self.write_state(requests=[{"kind": "transfer", "from": "HG", "to": "SLEEVE", "amount": 5.0}], inbox=[])
        self.assertEqual(len(self.exec_line()[0]), 4)                            # only a credit blocks it

    def test_the_line_sends_nothing_unless_the_cap_covers_the_executors_own_funded_plus_the_credits(self):
        for cap in (None, "", "0", "10000", "50032.15"):
            with self.subTest(cap=cap):
                env = dict(self.env)
                if cap is None:
                    del env["MIRROR_MAX_BOOK_USD"]
                else:
                    env["MIRROR_MAX_BOOK_USD"] = cap
                posts, out = self.exec_line(env)
                self.assertEqual(posts, [])
                self.assertIn("set the cap (step a) and deploy first", out)
        posts, out = self.exec_line(dict(self.env, MIRROR_MAX_BOOK_USD="50033.15"))     # funded + credits = cap + $1
        self.assertEqual(len(posts), 4, out)
        self.write_state(funded=13500.0)                     # the executor has taken more than the feed showed
        posts, out = self.exec_line()
        self.assertEqual(posts, [])
        self.assertIn("the book has taken 13500.00 and these credits add 40034.15, 53534.15 in all", out)
        self.write_state(funded=50034.15)                    # pasted again after the session applied them
        self.assertEqual(self.exec_line()[0], [])

    def test_the_line_fails_closed_on_a_state_without_funded_usd(self):
        self.write_state(drop_funded=True)
        with self.assertRaises(KeyError):
            self.exec_line()

    def test_the_line_names_only_the_engines_with_a_credit(self):
        line, code = ms.paste_line("https://exec.example/mirror/credit", "live", [("HG", 10.5), ("HARV", 0.01)],
                                   "scale-up to $10,000 at Composer's split of 2026-11-12")
        self.assertIn('A=(("HG",10.5),("HARV",0.01),)', code)
        self.assertIn("D=10.51", code)
        self.assertEqual(shlex.split(line)[2], code)


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
        self.assertEqual(set(p), {"ok", "book", "to", "factor", "note", "snapshot", "feed_utc", "marks_asof",
                                  "last_session", "health", "engines", "total", "residual", "funded", "cap", "cash",
                                  "url", "paste", "code", "steps", "warnings"})
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
                                      "(b) When the executor is back", "/opt/executor/venv/bin/python3 -c '",
                                      "(c) The executor applies them at its next session's decision (15:54 ET",
                                      "(d) That night's parity check against Composer (mirror_parity.py) removes "
                                      "the operator credits")]
        self.assertEqual(at, sorted(at))
        self.assertIn("Never between 15:15 and 16:05 ET (12:15-13:05 ET on a half-day: 2026-11-27, 2026-12-24)", text)
        self.assertIn("NOT retried", text)
        self.assertIn("approve the IB Key push", text)

    def test_the_half_days_named_are_the_coming_ones(self):
        later = datetime.datetime(2026, 12, 1, 15, 0, tzinfo=datetime.timezone.utc)
        self.assertIn("half-day: 2026-12-24, 2027-11-26)", ms.quiet_window(later))

    def test_the_doc_has_the_scaling_section(self):
        with open(os.path.join(REPO, "composer", "IBKR_MIRROR.md")) as f:
            doc = f.read()
        self.assertIn("## Scaling the live book", doc)
        sec = doc.split("## Scaling the live book")[1].split("\n## ")[0]
        flat = " ".join(sec.split())
        for text in ("scripts/mirror_scale.py --to", "MIRROR_MAX_BOOK_USD", "connection fix", "two clean sessions",
                     "sell-then-buy", "15:15", "16:05", "Shell", "EXEC_TOKEN", "NOT retried", "15:54", "parity",
                     "read-only"):
            self.assertIn(text, flat)


if __name__ == "__main__":
    unittest.main()
