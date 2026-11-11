"""Gate tests for mirror_transfer.py: the mirror leg of a POLICY capital move (no network: the feed
read and the POST are injected).

  T1  the arithmetic: the mirror moves the same FRACTION of its own FROM sleeve; the POST carries
      from / to / amount / note / book, to /mirror/transfer, with the transfer token
  T2  the fraction must be in (0, 0.5]; bad numbers and equal engines are refused before any read
  T3  the book: the one live book by default; none (or two) is refused, never guessed; --book names
      a paper book; a sleeve missing, frozen or without equity is refused
  T4  below $1 at the mirror's size: nothing is sent, exit 0
  T5  --dry-run reads the feed and posts nothing, and needs no transfer token
  T6  the executor's refusal is exit 1 with its own words; a POST that raised is 'unknown'; no token
      is ever in a line or in the ledger
  T7  configuration: https only (or localhost), tokens required; a feed that cannot be read is refused
  T8  one ledger row per call, sent or not, with the fields the report needs
  T9  the real HTTP helpers: the header that carries the token, and the URL; a redirect is never
      followed with the transfer token (or the attest token); a JSON answer is told from one that is not
  T10 a transfer already queued for the pair is not sent again (--again overrides); only an HTTP 4xx
      with a JSON body is "not queued", anything else after the request left is "unknown", and a
      re-run after an unknown is safe
  T11 --composer-from-value-after refuses a "before" that is the value after the move; the help and
      POLICY.md say to pass both, that the leg goes to the live book only, and when it is applied
  (T9's redirect gates, T10 and T11 are the independent review's findings: each failed at c740d160)

Run: python3 -m unittest tests.test_mirror_transfer -v
"""
import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import mirror_transfer as mt  # noqa: E402

NOW = datetime.datetime(2026, 11, 11, 21, 10, tzinfo=datetime.timezone.utc)      # 16:10 ET
TOKEN, READ = "transfer-token-AAAAAAAAAAAAAAAAAAAA", "read-token-BBBBBBBB"
ENV = {"MIRROR_EXECUTOR_URL": "https://exec.example", "MIRROR_READ_TOKEN": READ, "MIRROR_TRANSFER_TOKEN": TOKEN}
ARGS = ["--from", "HG", "--to", "SLEEVE", "--composer-amount", "5000", "--composer-from-value", "104827.05"]


def sleeves(**eq):
    return {k: {"equity": v, "cash": 1.0, "shares": {}, "frozen": False} for k, v in eq.items()}


def feed(live=None, dry=None):
    books = {}
    if live is not None:
        books["live"] = {"name": "live", "mode": "live", "book": {"sleeves": live}}
    if dry is not None:
        books["dry"] = {"name": "dry", "mode": "paper", "book": {"sleeves": dry}}
    return {"schema": 1, "kind": "composer-mirror-feed", "books": books}


FULL = sleeves(HG=2900.0, KMLM=2900.0, SLEEVE=2700.0, HARV=1500.0)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = os.path.join(self.tmp.name, "transfer-ledger.jsonl")
        self.posts, self.fetches = [], []
        self.answer = (200, {"ok": True, "book": "live", "request": {"id": "transfer-1-0", "kind": "transfer"}})
        self.feed = feed(live=FULL)

    def fetch(self, url, token):
        self.fetches.append((url, token))
        if isinstance(self.feed, Exception):
            raise self.feed
        return self.feed

    def send(self, url, token, body):
        self.posts.append((url, token, body))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def run_it(self, argv=ARGS, env=ENV):
        return mt.run(list(argv), env=dict(env), fetch=self.fetch, send=self.send, now=NOW, ledger_path=self.ledger)

    def rows(self):
        if not os.path.exists(self.ledger):
            return []
        with open(self.ledger) as f:
            return [json.loads(x) for x in f]


class T1Arithmetic(Case):
    def test_the_mirror_moves_the_same_fraction_of_its_own_sleeve(self):
        code, line = self.run_it()
        self.assertEqual(code, 0, line)
        self.assertTrue(line.startswith("MIRROR TRANSFER 2026-11-11 HG -> SLEEVE"), line)
        (url, token, body), = self.posts
        self.assertEqual(url, "https://exec.example/mirror/transfer")
        self.assertEqual(token, TOKEN)
        self.assertEqual(body["amount"], round(5000 / 104827.05 * 2900.0, 2))      # 138.32
        self.assertEqual(body["amount"], 138.32)
        self.assertEqual({k: body[k] for k in ("from", "to", "book")}, {"from": "HG", "to": "SLEEVE", "book": "live"})
        self.assertEqual(set(body), {"from", "to", "amount", "note", "book"})
        self.assertIn("POLICY mirror leg", body["note"])
        self.assertIn("transfer-1-0", line)
        self.assertEqual(self.fetches, [("https://exec.example", READ)])

    def test_a_note_given_is_the_note_sent_on_one_line(self):
        self.run_it(ARGS + ["--note", "op 1\nsleeve band " + "x" * 400])
        note = self.posts[0][2]["note"]
        self.assertTrue(note.startswith("op 1 sleeve band"))
        self.assertLessEqual(len(note), 200)

    def test_engine_names_are_upper_cased(self):
        code, _ = self.run_it(["--from", "hg", "--to", "sleeve", "--composer-amount", "5000", "--composer-from-value", "104827.05"])
        self.assertEqual(code, 0)
        self.assertEqual((self.posts[0][2]["from"], self.posts[0][2]["to"]), ("HG", "SLEEVE"))


class T2Fraction(Case):
    def bad(self, amount, value, src="HG", dst="SLEEVE"):
        code, line = self.run_it(["--from", src, "--to", dst, "--composer-amount", str(amount), "--composer-from-value", str(value)])
        self.assertEqual(code, 1, line)
        self.assertIn("REFUSED", line)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.fetches, [])          # refused before the executor is asked anything
        return line

    def test_more_than_half_is_refused_and_exactly_half_is_not(self):
        self.assertIn("outside 0 < fraction <= 50%", self.bad(50001, 100000))
        code, _ = self.run_it(["--from", "HG", "--to", "SLEEVE", "--composer-amount", "50000", "--composer-from-value", "100000"])
        self.assertEqual(code, 0)
        self.assertEqual(self.posts[0][2]["amount"], 1450.0)

    def test_zero_negative_and_not_numbers_are_refused(self):
        for amount, value in ((0, 100), (-5, 100), (5, 0), (5, -100), ("nan", 100), (5, "inf"), ("abc", 100)):
            self.bad(amount, value)

    def test_the_same_engine_twice_is_refused(self):
        self.bad(5, 100, src="HG", dst="hg")

    def test_a_missing_argument_is_a_refusal_not_a_crash(self):
        code, line = self.run_it(["--from", "HG"])
        self.assertEqual(code, 1)
        self.assertTrue(line.startswith("MIRROR TRANSFER"))
        self.assertIn("bad arguments", line)


class T3Book(Case):
    def refused(self, argv=ARGS):
        code, line = self.run_it(argv)
        self.assertEqual(code, 1, line)
        self.assertEqual(self.posts, [])
        return line

    def test_no_live_book_is_refused_never_guessed(self):
        self.feed = feed(dry=FULL)
        self.assertIn("no live book", self.refused())

    def test_book_names_the_paper_book(self):
        self.feed = feed(dry=FULL)
        code, _ = self.run_it(ARGS + ["--book", "dry"])
        self.assertEqual(code, 0)
        self.assertEqual(self.posts[0][2]["book"], "dry")

    def test_the_live_book_is_the_default_when_both_exist(self):
        self.feed = feed(live=sleeves(HG=1000.0, SLEEVE=500.0), dry=sleeves(HG=99999.0, SLEEVE=1.0))
        code, _ = self.run_it()
        self.assertEqual(code, 0)
        self.assertEqual((self.posts[0][2]["book"], self.posts[0][2]["amount"]), ("live", round(5000 / 104827.05 * 1000.0, 2)))

    def test_a_book_the_executor_does_not_have_is_refused(self):
        self.assertIn("no book 'nope'", self.refused(ARGS + ["--book", "nope"]))

    def test_a_sleeve_in_the_other_book_is_refused(self):
        self.feed = feed(live=sleeves(HG=2900.0), dry=sleeves(SLEEVE=2700.0))        # a staged rollout
        self.assertIn("no sleeve SLEEVE", self.refused())

    def test_a_frozen_sleeve_on_either_side_is_refused(self):
        for who in ("HG", "SLEEVE"):
            s = sleeves(HG=2900.0, SLEEVE=2700.0)
            s[who]["frozen"] = True
            self.feed = feed(live=s)
            self.assertIn(f"{who} is frozen", self.refused())

    def test_a_from_sleeve_without_equity_is_refused(self):
        for eq in (None, 0.0, -3.0, "12"):
            self.feed = feed(live=sleeves(HG=eq, SLEEVE=2700.0))
            self.assertIn("no usable equity", self.refused())


class T4BelowADollar(Case):
    def test_below_one_dollar_nothing_is_sent_and_the_exit_is_zero(self):
        self.feed = feed(live=sleeves(HG=20.0, SLEEVE=20.0))                         # 4.77% of $20 = $0.95
        code, line = self.run_it()
        self.assertEqual(code, 0, line)
        self.assertIn("below $1", line)
        self.assertIn("nothing sent", line)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows()[0]["outcome"], "below_min")

    def test_one_dollar_exactly_is_sent(self):
        self.feed = feed(live=sleeves(HG=100.0, SLEEVE=20.0))
        code, _ = self.run_it(["--from", "HG", "--to", "SLEEVE", "--composer-amount", "1", "--composer-from-value", "100"])
        self.assertEqual(code, 0)
        self.assertEqual(self.posts[0][2]["amount"], 1.0)


class T5DryRun(Case):
    def test_dry_run_reads_and_posts_nothing_and_needs_no_transfer_token(self):
        env = {k: v for k, v in ENV.items() if k != "MIRROR_TRANSFER_TOKEN"}
        code, line = self.run_it(ARGS + ["--dry-run"], env=env)
        self.assertEqual(code, 0, line)
        self.assertEqual(self.posts, [])
        self.assertEqual(len(self.fetches), 1)
        self.assertIn("dry run: not sent", line)
        self.assertIn('"amount": 138.32', line)
        self.assertEqual(self.rows()[0]["outcome"], "dry_run")


class T6Refusals(Case):
    def test_the_executors_refusal_is_exit_1_with_its_words_and_no_token(self):
        self.answer = (400, {"detail": f"over the day's cap for transfers by the transfer token: $138.32 asked ({TOKEN} {READ})"})
        code, line = self.run_it()
        self.assertEqual(code, 1)
        self.assertIn("HTTP 400", line)
        self.assertIn("over the day's cap", line)
        with open(self.ledger) as f:
            ledger = f.read()
        for text in (line, ledger):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn(READ, text)
        self.assertEqual(self.rows()[0]["outcome"], "refused")

    def test_a_bad_token_answer_is_exit_1(self):
        self.answer = (401, {"detail": "bad exec token"})
        code, line = self.run_it()
        self.assertEqual(code, 1)
        self.assertIn("HTTP 401: bad exec token", line)

    def test_a_200_that_is_not_ok_is_exit_1(self):
        self.answer = (200, {})
        self.assertEqual(self.run_it()[0], 1)

    def test_a_post_that_raised_is_unknown_and_says_to_check_before_resending(self):
        self.answer = TimeoutError(f"timed out talking with {TOKEN}")
        code, line = self.run_it()
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN whether the executor queued it", line)
        self.assertNotIn(TOKEN, line)
        self.assertEqual(self.rows()[0]["outcome"], "unknown")


class T10DoubleSend(Case):
    """review items 6 and 7: a re-run never sends the same leg twice, and only an HTTP 4xx with a JSON
    body is "not queued" - anything else after the request left is UNKNOWN"""
    def held(self, **over):
        row = dict({"kind": "transfer", "from": "HG", "to": "SLEEVE", "amount": 138.32, "note": "POLICY mirror leg",
                    "via": "transfer_token", "id": "transfer-1794435400000-0", "utc": "2026-11-11T21:05:00Z"}, **over)
        self.feed = feed(live=FULL)
        self.feed["books"]["live"]["pending_requests"] = [row]
        return row

    def test_a_transfer_already_queued_for_the_pair_is_not_sent_again(self):
        self.held()
        code, line = self.run_it()
        self.assertEqual((code, self.posts), (1, []))
        self.assertIn("a transfer for this pair is already queued", line)
        self.assertIn("$138.32 as transfer-1794435400000-0", line)
        self.assertIn("--again", line)
        self.assertEqual(self.rows()[0]["outcome"], "duplicate")
        self.assertEqual(self.run_it(ARGS + ["--dry-run"])[0], 1)             # a dry run says what a run would do
        code, line = self.run_it(ARGS + ["--again"])                         # a second move of the pair, meant
        self.assertEqual((code, len(self.posts)), (0, 1))
        self.assertEqual(self.rows()[-1]["outcome"], "sent")

    def test_the_twins_other_pairs_other_authors_and_other_requests_are_not_duplicates(self):
        for over in ({"from": "SLEEVE", "to": "HG"}, {"to": "HARV"}, {"via": None}, {"kind": "credit", "sleeve": "HG"}):
            self.posts = []
            row = self.held(**over)
            if over.get("via", 1) is None:
                del row["via"]                            # the operator's own transfer (EXEC_TOKEN): not this script's
            self.assertEqual((self.run_it()[0], len(self.posts)), (0, 1), over)
        self.feed = feed(live=FULL)
        self.feed["books"]["live"]["pending_requests"] = []
        self.assertEqual(self.run_it()[0], 0)
        self.feed["books"]["live"]["pending_requests"] = "none"                # cannot be told: nothing is sent
        code, line = self.run_it()
        self.assertEqual(code, 1)
        self.assertIn("pending_requests", line)
        self.assertEqual(len(self.posts), 2)

    def test_only_a_4xx_with_a_json_body_is_not_queued_everything_else_is_unknown(self):
        for answer in ((502, None), (500, {"detail": "Internal Server Error"}), (503, {}), (200, None), (200, {}),
                       (200, {"ok": False}), (404, None), (429, None), (204, None), ConnectionResetError("reset"),
                       TimeoutError("timed out")):
            self.answer = answer
            code, line = self.run_it()
            self.assertEqual(code, 1, answer)
            self.assertIn("UNKNOWN whether the executor queued it", line, answer)
            self.assertIn("check pending_requests before re-sending", line, answer)
            self.assertNotIn("NOT QUEUED", line, answer)
            self.assertEqual(self.rows()[-1]["outcome"], "unknown", answer)   # at c740d160: "refused" / NOT QUEUED
        for answer in ((400, {"detail": "refused: over the day's transfer allowance"}), (401, {"detail": "bad exec token"}),
                       (404, {"detail": "Not Found"}), (422, {}), (302, None), (307, {})):
            self.answer = answer
            code, line = self.run_it()
            self.assertEqual(code, 1, answer)
            self.assertIn(f"NOT QUEUED (HTTP {answer[0]}", line, answer)
            self.assertNotIn("UNKNOWN", line, answer)
            self.assertEqual(self.rows()[-1]["outcome"], "refused", answer)

    def test_after_an_unknown_a_re_run_is_safe_either_way(self):
        self.answer = (502, None)
        self.assertEqual(self.run_it()[0], 1)             # unknown ...
        self.held()                                       # ... and the executor HAD queued it
        self.answer = (200, {"ok": True, "request": {"id": "transfer-2"}})
        self.assertEqual(self.run_it()[0], 1)
        self.assertEqual(len(self.posts), 1)              # not sent a second time
        self.assertEqual([r["outcome"] for r in self.rows()], ["unknown", "duplicate"])
        self.feed = feed(live=FULL)                       # the twin: it had NOT queued it
        self.assertEqual(self.run_it()[0], 0)
        self.assertEqual(len(self.posts), 2)


class T11BeforeAndAfter(Case):
    """review item 9: the value AFTER the move passed as "before" moves too large a fraction, silently"""
    def test_the_after_value_passed_as_before_is_refused_when_both_are_given(self):
        code, line = self.run_it(ARGS + ["--composer-from-value-after", "99827.05"])
        self.assertEqual((code, self.posts[0][2]["amount"]), (0, 138.32))
        self.assertEqual(self.rows()[0]["composer_from_value_after"], 99827.05)
        wrong = ["--from", "HG", "--to", "SLEEVE", "--composer-amount", "5000", "--composer-from-value", "99827.05"]
        code, line = self.run_it(wrong + ["--composer-from-value-after", "99827.05"])
        self.assertEqual((code, len(self.posts)), (1, 1))
        self.assertIn("BEFORE the move", line)
        self.assertEqual(self.rows()[-1]["outcome"], "refused")
        self.assertEqual(self.run_it(wrong)[0], 0)        # the twin, and why both should be passed: alone it goes ...
        self.assertEqual(self.posts[-1][2]["amount"], 145.25)                 # ... 5.0% of the sleeve, not 4.77%

    def test_the_tolerance_is_fifty_dollars_or_one_percent_of_before(self):
        def go(amount, before, after):
            return self.run_it(["--from", "HG", "--to", "SLEEVE", "--composer-amount", str(amount),
                                "--composer-from-value", str(before), "--composer-from-value-after", str(after)])[0]
        self.assertEqual(go(100, 1000, 850), 0)           # off by $50: the floor
        self.assertEqual(go(100, 1000, 849), 1)
        self.assertEqual(go(100, 1000, 950), 0)
        self.assertEqual(go(100, 1000, 951), 1)
        self.assertEqual(go(5000, 100000, 94000), 0)      # off by $1,000 = 1% of before
        self.assertEqual(go(5000, 100000, 93999), 1)
        self.assertEqual(go(5000, 100000, 96001), 1)
        self.assertEqual(go(100, 1000, -1), 1)
        self.assertEqual(go(100, 1000, "nan"), 1)

    def test_the_help_and_the_policy_say_to_pass_both_and_where_the_leg_goes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            mt.parse(["--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("--composer-from-value-after", text)
        self.assertIn("value AFTER the move. Pass it as well", text)
        with open(os.path.join(HERE, "..", "..", "POLICY.md")) as f:
            policy = " ".join(f.read().split())
        para = policy[policy.index("**IBKR mirror.**"):policy.index("## Pre-authorized operation 1")]
        for part in ("--composer-from-value-after", "LIVE book only", "no live book", "exits 1", "NEXT session",
                     "15:54 ET", "next trading day", "--again", "UNKNOWN"):
            self.assertIn(part, para, part)


class T7Configuration(Case):
    def refused(self, env, argv=ARGS):
        code, line = self.run_it(argv, env=env)
        self.assertEqual(code, 1, line)
        self.assertEqual(self.posts, [])
        return line

    def test_plain_http_is_refused_before_any_token_leaves(self):
        line = self.refused(dict(ENV, MIRROR_EXECUTOR_URL="http://exec.example"))
        self.assertIn("must be https", line)
        self.assertEqual(self.fetches, [])
        self.refused(dict(ENV, MIRROR_EXECUTOR_URL=""))

    def test_localhost_over_http_is_accepted(self):
        code, _ = self.run_it(env=dict(ENV, MIRROR_EXECUTOR_URL="http://127.0.0.1:8000/"))
        self.assertEqual(code, 0)
        self.assertEqual(self.posts[0][0], "http://127.0.0.1:8000/mirror/transfer")

    def test_the_tokens_are_required(self):
        self.assertIn("MIRROR_READ_TOKEN not set", self.refused({k: v for k, v in ENV.items() if k != "MIRROR_READ_TOKEN"}))
        self.assertIn("MIRROR_TRANSFER_TOKEN not set", self.refused({k: v for k, v in ENV.items() if k != "MIRROR_TRANSFER_TOKEN"}))
        self.assertEqual(self.fetches, [])

    def test_a_feed_that_cannot_be_read_is_refused(self):
        self.feed = RuntimeError(f"HTTP 401: the read token was refused {READ}")
        line = self.refused(ENV)
        self.assertIn("feed could not be read", line)
        self.assertNotIn(READ, line)


class T8Ledger(Case):
    def test_one_row_per_call_sent_or_not(self):
        self.run_it()
        self.run_it(ARGS + ["--dry-run"])
        self.run_it(["--from", "HG", "--to", "SLEEVE", "--composer-amount", "9", "--composer-from-value", "10"])
        rows = self.rows()
        self.assertEqual([r["outcome"] for r in rows], ["sent", "dry_run", "refused"])
        sent = rows[0]
        self.assertEqual({k: sent[k] for k in ("date", "from", "to", "composer_amount", "composer_from_value", "sleeve_equity",
                                               "amount", "request_id", "book")},
                         {"date": "2026-11-11", "from": "HG", "to": "SLEEVE", "composer_amount": 5000.0,
                          "composer_from_value": 104827.05, "sleeve_equity": 2900.0, "amount": 138.32,
                          "request_id": "transfer-1-0", "book": "live"})
        self.assertAlmostEqual(sent["fraction"], 5000 / 104827.05, places=9)
        self.assertIsNone(rows[2]["amount"])
        self.assertIn("why", rows[2])

    def test_a_ledger_that_cannot_be_written_never_hides_the_outcome(self):
        blocker = os.path.join(self.tmp.name, "a-file")
        with open(blocker, "w"):
            pass
        code, line = mt.run(list(ARGS), env=dict(ENV), fetch=self.fetch, send=self.send, now=NOW,
                            ledger_path=os.path.join(blocker, "transfer-ledger.jsonl"))     # a directory that cannot be
        self.assertEqual(code, 0)
        self.assertIn("ledger row was NOT written", line)
        self.assertEqual(len(self.posts), 1)

    def test_the_default_ledger_is_in_results_mirror(self):
        self.assertTrue(os.path.normpath(mt.LEDGER_PATH).endswith(os.path.join("composer", "results", "mirror", "transfer-ledger.jsonl")))


class T9Http(unittest.TestCase):
    def test_post_sends_the_token_in_the_header_only(self):
        seen = {}

        class Resp:
            status = 200

            def read(self):
                return b'{"ok": true, "request": {"id": "transfer-9"}}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            seen["req"] = req
            return Resp()

        with unittest.mock.patch.object(mt.mp, "urlopen_no_redirect", fake):
            code, data = mt.post("https://exec.example/mirror/transfer", TOKEN, {"from": "HG"})
        self.assertEqual((code, data["request"]["id"]), (200, "transfer-9"))
        req = seen["req"]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "https://exec.example/mirror/transfer")          # no token in the URL
        self.assertEqual(req.get_header("X-transfer-token"), TOKEN)
        self.assertEqual(json.loads(req.data), {"from": "HG"})

    def _servers(self, status=302, body=b""):
        """a local 'executor' answering `status` (a 3xx points at another local server); what that other
        server was sent lands in the returned list"""
        import http.server
        import threading
        got = []

        class Other(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                got.append((self.command, self.headers.get("X-Transfer-Token"), self.headers.get("X-Attest-Token")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true, "request": {"id": "stolen"}}')
            do_POST = do_GET

            def log_message(self, *a):
                pass

        class Executor(Other):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(status)
                if 300 <= status < 400:
                    self.send_header("Location", f"http://127.0.0.1:{other.server_port}/steal")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        other = http.server.HTTPServer(("127.0.0.1", 0), Other)
        executor = http.server.HTTPServer(("127.0.0.1", 0), Executor)
        for srv in (other, executor):
            threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{executor.server_port}", got

    def test_a_redirect_is_never_followed_with_the_transfer_token(self):
        for status in (301, 302, 303, 307, 308):
            base, got = self._servers(status)
            self.assertEqual(mt.post(base + "/mirror/transfer", TOKEN, {"from": "HG"}), (status, None))
            self.assertEqual(got, [], status)             # at c740d160 a 302: [("GET", TOKEN, None)] and "(200, {})"

    def test_a_redirect_is_never_followed_with_the_attest_token(self):
        import mirror_attest as ma
        base, got = self._servers(302)
        self.assertEqual(ma.post(base + "/mirror/attest", "attest-token-CCCC", {"session": "x"}), (302, {}))
        self.assertEqual(got, [])                         # at c740d160: [("GET", None, "attest-token-CCCC")]

    def test_post_tells_a_json_answer_from_one_that_is_not(self):
        for status, body, want in ((400, b'{"detail": "refused: not a valid transfer"}', {"detail": "refused: not a valid transfer"}),
                                   (502, b"<html>Bad Gateway</html>", None), (200, b"ok", None), (200, b"[1]", None),
                                   (200, b'{"ok": true}', {"ok": True})):
            base, _ = self._servers(status, body)
            self.assertEqual(mt.post(base + "/mirror/transfer", TOKEN, {"from": "HG"}), (status, want))

    def test_a_redirecting_executor_end_to_end_is_refused_and_nothing_leaves(self):
        base, got = self._servers(307)
        with tempfile.TemporaryDirectory() as tmp:
            code, line = mt.run(list(ARGS), env=dict(ENV, MIRROR_EXECUTOR_URL=base), fetch=lambda u, t: feed(live=FULL),
                                now=NOW, ledger_path=os.path.join(tmp, "l.jsonl"))
            with open(os.path.join(tmp, "l.jsonl")) as f:
                self.assertEqual(json.loads(f.read())["outcome"], "refused")
        self.assertEqual(code, 1)
        self.assertIn("NOT QUEUED (HTTP 307", line)
        self.assertIn("redirect", line)
        self.assertEqual(got, [])

    def test_transfer_url(self):
        self.assertEqual(mt.transfer_url("https://e.example/"), "https://e.example/mirror/transfer")
        self.assertEqual(mt.transfer_url("http://localhost:8000"), "http://localhost:8000/mirror/transfer")
        for bad in ("http://e.example", "ftp://e.example", "", "e.example"):
            with self.assertRaises(mt.Refused):
                mt.transfer_url(bad)


if __name__ == "__main__":
    unittest.main()
