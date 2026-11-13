"""Gate tests for mirror_parity.py: the daily check of the EXECUTOR's mirror books against Composer.

Each behavioural gate has a broken twin that must land on the other side.

  P1  same holdings: no alert, a report line, one ledger row per engine, idempotent on a re-run
  P2  different holdings alert; a knife-edge or no-rebalance day in the shadow ledger explains them
  P3  whole shares on a small sleeve are not a mismatch; the same gap on a large sleeve is
  P4  the executor's own state is relayed: halted, a run still open, the account check, a session that
      did not run or did not trade, a sleeve left out, an unfilled live buy, a tick error
  P5  the day's return is read at the official closes; a gap is alarmed only when both books went
      into the day holding the same
  P6  configuration and the read: nothing set = nothing said; the token only over https (or
      localhost) and never in a message; a refused or failed read is an alert, not a silent day
  P7  it can never stop the monitor, and the monitor calls it after the paper book
  P9  a POLICY transfer applied that session is not a return: the day's return is transfer-adjusted
      (no false RETURN GAP on flat prices); a real gap that day still alarms; a session row that does
      not say what it moved gets no return comparison, and the line says so
  P10 the read token is never re-sent to where a redirect points
  P11 an operator's credit or debit (POST /mirror/credit; the session row's "credits", kind "credit")
      is not a return: the scale-up day reads ~0 bps, not +400%; a real move that day is compared as
      the true return (the credited dollars' own move after the plan's prices goes out with them); a
      real gap still alarms; a dividend the book credited (kind "dividend") stays in; a fee debit is
      taken out; with a transfer the same day both come out; credits that cannot be read get no
      return comparison, and the line says why
  P12 a day without credits reads byte for byte as before the credits were read; so does one whose
      credits net to zero in floats (0.1 + 0.2 - 0.3: rounded to the cent before it is read)
  P13 the second review (each gate failed at 6b122160 or on the mutant it names): the chained basis only
      when the sleeve's credited buys FILLED (a venue BUY whose split gives it shares and that filled, or a
      cross it bought in); a sleeve whose buys were rejected or never filled, or that only sold, is taken
      out at face value - chained, its cash diluted the old capital's move into a false RETURN GAP; a
      chained day whose old capital is worth nothing at the session's prices (V - flows <= 0) falls back
      to face value
  P8  a real feed (a $10k paper book on the executor's own code, real brain decisions of 2026-11-06
      and 11-09) reads end to end: the fields this script needs are the fields the executor writes

Run: python3 -m unittest tests.test_mirror_parity -v
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
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import mirror_parity as mp  # noqa: E402
import monitor  # noqa: E402

D0, D = "2026-11-09", "2026-11-10"
NOW = datetime.datetime(2026, 11, 10, 21, 40, tzinfo=datetime.timezone.utc)
PX = {"BIL": 91.5, "PULS": 49.5, "SOXL": 40.0, "TECL": 100.0, "BOXX": 113.0, "ZVOL": 7.0}


def sleeve(shares, cash=10.0, action="trade", reason="to target"):
    return {"action": action, "reason": reason, "shares": dict(shares), "cash": cash, "version": "v1", "target": None}


def row(session, sleeves, orders=(), outcome="traded", **kw):
    return dict({"session": session, "outcome": outcome, "sleeves": sleeves, "orders": list(orders), "prices": dict(PX),
                 "notes": [], "problems": []}, **kw)


def book(rows, mode="live", **kw):
    v = {"name": mode, "mode": mode, "history": list(rows), "last_run": rows[-1] if rows else None,
         "last_session": rows[-1]["session"] if rows else None, "run": None, "halt": {}, "check": None,
         "last_error": None, "waiting_on": None, "archived_state": None}
    v.update(kw)
    return v


def feed(**books):
    return {"schema": 1, "kind": mp.FEED_KIND, "mode": "LIVE", "books": books}


BIG = {"HG": sleeve({"BIL": 370}), "HARV": sleeve({"PULS": 355})}          # ~$34k and ~$17.6k
COMP = {"HG": {"holdings": {"BIL": 1.0}, "ret": 0.001, "basis": "dav", "kind": "close", "taken_at": "x"},
        "HARV": {"holdings": {"PULS": 1.0}, "ret": 0.0005, "basis": "dav", "kind": "close", "taken_at": "x"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmp, "parity.jsonl")
        self.comp = {D: json.loads(json.dumps(COMP)), D0: json.loads(json.dumps(COMP))}
        self.shadow = {}
        for p in (unittest.mock.patch.object(mp.md, "composer_day", side_effect=lambda d, cal, directory=None, *a, **k: self.comp.get(d, {})),
                  unittest.mock.patch.object(mp.md, "read_shadow", side_effect=lambda path=None: dict(self.shadow))):
            p.start()
            self.addCleanup(p.stop)

    def run_check(self, fd, closes=False, date=D, now=NOW):
        return mp.check(now, feed=fd, date=date, ledger_path=self.ledger, closes=closes or (lambda day, syms: None), env={})

    def rows(self):
        if not os.path.isfile(self.ledger):
            return []
        with open(self.ledger) as f:
            return [json.loads(x) for x in f]


class P1Same(Base):
    def test_same_holdings_are_a_quiet_line_and_a_ledger_row_each(self):
        lines, alerts = self.run_check(feed(live=book([row(D, BIG)])))
        self.assertEqual(alerts, [])
        self.assertIn("2 of 2 engines hold the same", "\n".join(lines))
        self.assertEqual({(r["engine"], r["parity"]) for r in self.rows()}, {("HG", "same"), ("HARV", "same")})
        self.run_check(feed(live=book([row(D, BIG)])))
        self.assertEqual(len(self.rows()), 2)                               # a re-run replaces, never appends


class P2Mismatch(Base):
    def test_a_difference_alerts_unless_the_shadow_ledger_explains_it(self):
        off = dict(BIG, HARV=sleeve({"PULS": 230, "ZVOL": 900}))            # ~64 / 36
        lines, alerts = self.run_check(feed(live=book([row(D, off)])))
        self.assertEqual(len(alerts), 1)
        self.assertIn("MIRROR LIVE MISMATCH — HARV", alerts[0])
        self.assertIn("ZVOL", alerts[0])
        self.assertIn("1 of 2 engines hold the same", "\n".join(lines))
        for status in ("knife-edge", "no-rebalance"):
            self.shadow = {(D, "HARV"): {"status": status}}
            _, alerts = self.run_check(feed(live=book([row(D, off)])))
            self.assertEqual(alerts, [], status)                            # explained: said in the ledger, not alarmed
            self.assertEqual(next(r for r in self.rows() if r["engine"] == "HARV")["parity"], f"explained ({status})")
        self.shadow = {(D, "HARV"): {"status": "agree"}}
        self.assertEqual(len(self.run_check(feed(live=book([row(D, off)])))[1]), 1)      # the twin

    def test_a_paper_book_is_labelled_paper(self):
        off = dict(BIG, HARV=sleeve({"ZVOL": 2500}))
        _, alerts = self.run_check(feed(dry=book([row(D, off)], mode="paper")))
        self.assertTrue(alerts[0].startswith("MIRROR PAPER MISMATCH"))


class P3SmallSleeves(Base):
    def test_one_share_of_rounding_is_not_a_mismatch_on_a_small_sleeve(self):
        self.comp[D] = {"KMLM": {"holdings": {"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25}, "ret": None, "basis": None,
                                 "kind": "close", "taken_at": "x"}}
        small = {"KMLM": sleeve({"SOXL": 10, "TECL": 4, "PULS": 6}, cash=43.0)}        # $1,140: TECL 35.1%, off by rounding
        _, alerts = self.run_check(feed(live=book([row(D, small)])))
        self.assertEqual(alerts, [])
        rec = self.rows()[0]
        self.assertGreater(rec["tol"], mp.TOL)
        big = {"KMLM": sleeve({"SOXL": 300, "TECL": 104, "PULS": 180}, cash=1290.0)}   # the same weights at $34k: a real gap
        _, alerts = self.run_check(feed(live=book([row(D, big)])))
        rec = self.rows()[0]
        self.assertEqual(rec["tol"], mp.TOL + 0.0) if rec["tol"] == mp.TOL else self.assertLess(rec["tol"], 0.035)
        self.assertTrue((rec["parity"] == "MISMATCH") == (rec["dist"] > rec["tol"]))


class P4Health(Base):
    def test_the_executors_own_state_is_relayed(self):
        ok = [row(D, BIG)]
        cases = {
            "HALTED": dict(halt={"halted": True, "reason": "the account does not hold the mirror book: TECL", "by": "mirror", "ts": "t"}),
            "RUN STILL OPEN": dict(run={"session": D, "phase": "buys", "orders": {"mirror-x-B-TECL": {"state": "placed", "stuck": "still working"}}}),
            "ACCOUNT CHECK": dict(check={"session": D, "problems": ["TECL: the book holds 108, the venue 103"]}),
            "ERROR": dict(last_error="RuntimeError('boom')"),
            "STATE FILE": dict(archived_state="mirror[live] state file unreadable"),
        }
        for word, kw in cases.items():
            _, alerts = self.run_check(feed(live=book(ok, **kw)))
            self.assertTrue(any(f"MIRROR LIVE {word}" in a for a in alerts), word)
        self.assertEqual(self.run_check(feed(live=book(ok)))[1], [])        # the twin: a healthy book says nothing

    def test_a_session_that_did_not_run_or_did_not_trade(self):
        _, alerts = self.run_check(feed(live=book([row(D0, BIG)], waiting_on="no intents (transport)")))
        self.assertTrue(any("DID NOT RUN" in a and "no intents" in a for a in alerts))
        skipped = {"session": D, "outcome": "skipped", "reason": "missed the decision window: the brain's clock is unreadable"}
        _, alerts = self.run_check(feed(live=book([row(D0, BIG), skipped])))
        self.assertTrue(any("MIRROR LIVE NO TRADE" in a and "clock" in a for a in alerts))
        self.assertFalse(any("DID NOT RUN" in a for a in alerts))            # it ran; it did not trade
        # asked about an older session than the book's last: not "did not run"
        _, alerts = self.run_check(feed(live=book([row(D0, BIG), row(D, BIG)])), date=D0)
        self.assertFalse(any("DID NOT RUN" in a for a in alerts))

    def test_a_sleeve_left_out_and_an_unfilled_live_buy(self):
        out = dict(BIG, HARV=sleeve({"PULS": 355}, action="skip", reason="tree not attested (sync state 'none')"))
        _, alerts = self.run_check(feed(live=book([row(D, out)])))
        self.assertTrue(any("SLEEVE LEFT OUT — HARV" in a and "not attested" in a for a in alerts))
        orders = [{"symbol": "BIL", "qty": 370, "filled": 200, "side": "BUY", "cost_bps": 1.5}]
        lines, alerts = self.run_check(feed(live=book([row(D, BIG, orders)])))
        self.assertTrue(any("UNFILLED" in a and "BIL 200/370" in a for a in alerts))
        self.assertIn("+1.5 bps vs the decision price", "\n".join(lines))
        _, alerts = self.run_check(feed(dry=book([row(D, BIG, orders)], mode="paper")))
        self.assertFalse(any("UNFILLED" in a for a in alerts))               # paper: a line, not an alert


class P5Returns(Base):
    def closes(self, day, syms):
        px = dict(PX, PULS=49.5 if day == D0 else 49.5 * 1.02)               # PULS +2% on the day
        return {s: px[s] for s in syms}

    def test_the_days_return_is_read_at_the_closes_and_alarmed_only_on_like_for_like(self):
        self.comp[D]["HARV"]["ret"] = 0.0
        fd = feed(live=book([row(D0, BIG), row(D, BIG)]))
        lines, alerts = self.run_check(fd, closes=self.closes)
        rec = next(r for r in self.rows() if r["engine"] == "HARV")
        self.assertAlmostEqual(rec["ret"], 0.02, places=3)
        self.assertAlmostEqual(rec["diff_bps"], 200, delta=2)
        self.assertTrue(rec["carried_same"])
        self.assertTrue(any("RETURN GAP — HARV" in a for a in alerts))
        # the twin: yesterday the two books held different things, so today's gap is yesterday's mismatch
        self.comp[D0]["HARV"]["holdings"] = {"PULS": 0.64, "ZVOL": 0.36}
        lines, alerts = self.run_check(fd, closes=self.closes)
        self.assertFalse(any("RETURN GAP" in a for a in alerts))
        self.assertIn("different holdings into the day", "\n".join(lines))
        # no closes: no return, no alarm, holdings still compared
        lines, alerts = self.run_check(fd)
        self.assertNotIn("day return", "\n".join(lines))
        self.assertIn("2 of 2 engines hold the same", "\n".join(lines))


class P9TransferDay(Base):
    """the independent review's finding: on the session a POLICY transfer is applied, the giver's equity
    falls and the taker's rises by the moved dollars with prices FLAT - at c740d160 that was a false
    "RETURN GAP - HG -4.77%" (and the taker's twin)"""
    MOVED = 18 * 91.5                                                          # 18 BIL sold by HG: $1,647.00
    AFTER = {"HG": sleeve({"BIL": 352}), "HARV": sleeve({"PULS": 388}, cash=23.5)}     # HARV bought 33 PULS with it

    def flat(self, day, syms):
        return {s: PX[s] for s in syms}

    def fd(self, transfers="absent", after=None):
        kw = {} if transfers == "absent" else {"transfers": transfers}
        return feed(live=book([row(D0, BIG), row(D, after or self.AFTER, **kw)]))

    def setUp(self):
        super().setUp()
        for d in (D0, D):
            for e in ("HG", "HARV"):
                self.comp[d][e]["ret"] = 0.0

    def test_a_policy_move_is_not_a_return(self):
        t = [{"from": "HG", "to": "HARV", "amount": self.MOVED, "status": "moved", "moved": self.MOVED}]
        lines, alerts = self.run_check(self.fd(t), closes=self.flat)
        self.assertEqual(alerts, [])
        recs = {r["engine"]: r for r in self.rows()}
        self.assertAlmostEqual(recs["HG"]["diff_bps"], 0.0, delta=0.5)
        self.assertAlmostEqual(recs["HARV"]["diff_bps"], 0.0, delta=0.5)
        self.assertEqual((recs["HG"]["transfer_in"], recs["HARV"]["transfer_in"]), (-self.MOVED, self.MOVED))
        self.assertIn("HG +0 bps", "\n".join(lines).replace("-0 bps", "+0 bps"))
        # a partial move is adjusted by what MOVED, not by what was asked
        t = [{"from": "HG", "to": "HARV", "amount": 5000.0, "status": "partial", "moved": self.MOVED},
             {"from": "HARV", "to": "HG", "amount": 9.0, "status": "refused"}]
        self.assertEqual(self.run_check(self.fd(t), closes=self.flat)[1], [])

    def test_the_twins_the_same_change_with_no_transfer_and_a_real_gap_on_a_transfer_day_still_alarm(self):
        for transfers in ("absent", [], [{"from": "KMLM", "to": "SLEEVE", "amount": 9.0, "status": "moved", "moved": 9.0}]):
            _, alerts = self.run_check(self.fd(transfers), closes=self.flat)
            self.assertEqual(sorted(a.split(" on ")[0] for a in alerts),
                             ["MIRROR LIVE RETURN GAP — HARV", "MIRROR LIVE RETURN GAP — HG"], transfers)
        self.assertIn("-4.86%", self.run_check(self.fd([]), closes=self.flat)[1][0])   # what c740d160 said of the move
        # the move is taken out, and the 3% the giver ALSO lost that day is still a gap
        t = [{"from": "HG", "to": "HARV", "amount": self.MOVED, "status": "moved", "moved": self.MOVED}]
        lost = dict(self.AFTER, HG=sleeve({"BIL": 341}))
        _, alerts = self.run_check(self.fd(t, lost), closes=self.flat)
        self.assertEqual(len(alerts), 1)
        self.assertIn("RETURN GAP — HG", alerts[0])
        self.assertIn("-2.97%", alerts[0])

    def test_a_row_that_does_not_say_what_it_moved_gets_no_return_comparison_and_says_so(self):
        for t in ([{"from": "HG", "to": "HARV", "amount": self.MOVED, "status": "moved"}],
                  [{"from": "HG", "to": "HARV", "amount": self.MOVED, "status": "moved", "moved": "1647"}],
                  [{"from": "HG", "to": "HARV", "amount": self.MOVED, "status": "moved", "moved": float("nan")}],
                  [{"from": "HG", "to": "HARV", "amount": self.MOVED, "status": "?", "moved": self.MOVED}],
                  ["HG->HARV"], {"HG": "HARV"}):
            lines, alerts = self.run_check(self.fd(t), closes=self.flat)
            self.assertEqual(alerts, [], t)
            text = "\n".join(lines)
            self.assertIn("day return NOT compared for HG, HARV", text)
            self.assertIn("does not say what it moved", text)
            recs = {r["engine"]: r for r in self.rows()}
            self.assertNotIn("ret", recs["HG"])
            self.assertIn("ret_skipped", recs["HARV"])
            self.assertEqual(recs["HG"]["parity"], "same")                     # the holdings are still compared
        # only the sleeves the unreadable transfer touched lose the comparison
        self.assertEqual(mp.moved_in({"transfers": [{"from": "HG", "to": "HARV", "status": "moved"}]}, "KMLM"), 0.0)
        self.assertIsNone(mp.moved_in({"transfers": [{"from": "HG", "to": "HARV", "status": "moved"}]}, "HARV"))
        self.assertEqual(mp.moved_in({"transfers": [{"from": "HG", "to": "HARV", "status": "planned", "moved": 0.0}]}, "HG"), 0.0)


class P10NoRedirect(unittest.TestCase):
    def test_the_read_token_is_never_sent_on_to_where_a_redirect_points(self):
        import http.server
        import threading
        got = []

        class Other(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                got.append(self.headers.get("X-Read-Token"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(feed()).encode())

            def log_message(self, *a):
                pass

        class Executor(Other):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{other.server_port}/mirror/feed")
                self.end_headers()

        other = http.server.HTTPServer(("127.0.0.1", 0), Other)
        executor = http.server.HTTPServer(("127.0.0.1", 0), Executor)
        for srv in (other, executor):
            threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
        with self.assertRaises(RuntimeError) as cm:
            mp.fetch_feed(f"http://127.0.0.1:{executor.server_port}", "s3cret-read")
        self.assertIn("HTTP 302", str(cm.exception))
        self.assertIn("redirect", str(cm.exception))
        self.assertEqual(got, [])                                            # at c740d160: ["s3cret-read"]
        self.assertEqual(mp.fetch_feed(f"http://127.0.0.1:{other.server_port}", "s3cret-read")["kind"], mp.FEED_KIND)   # the twin
        self.assertEqual(got, ["s3cret-read"])


class P6Config(unittest.TestCase):
    def test_nothing_set_is_nothing_said(self):
        self.assertEqual(mp.check(NOW, env={}), ([], []))
        lines, alerts = mp.check(NOW, env={"MIRROR_EXECUTOR_URL": "https://x.example"})
        self.assertEqual(alerts, [])
        self.assertIn("token missing", lines[0])

    def test_the_token_goes_only_over_https_or_to_localhost_and_never_into_a_message(self):
        seen = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=None):
            seen.append((req.full_url, req.get_header("X-read-token")))
            return Resp(json.dumps(feed()).encode())
        with self.assertRaises(RuntimeError) as cm:
            mp.fetch_feed("http://executor.example", "s3cret", opener=opener)
        self.assertEqual(seen, [])                                           # nothing was sent
        self.assertNotIn("s3cret", str(cm.exception))
        mp.fetch_feed("https://executor.example/", "s3cret", opener=opener)
        mp.fetch_feed("http://127.0.0.1:8000", "s3cret", opener=opener)
        self.assertEqual(seen, [("https://executor.example/mirror/feed?history=30", "s3cret"),
                                ("http://127.0.0.1:8000/mirror/feed?history=30", "s3cret")])

        def refuse(code):
            def opener(req, timeout=None):
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
            return opener
        for code, word in ((401, "token was refused"), (404, "not there")):
            with self.assertRaises(RuntimeError) as cm:
                mp.fetch_feed("https://e.example", "s3cret", opener=refuse(code))
            self.assertIn(word, str(cm.exception))

        def boom(req, timeout=None):
            raise OSError("connect to e.example failed with header s3cret")
        with self.assertRaises(RuntimeError) as cm:
            mp.fetch_feed("https://e.example", "s3cret", opener=boom)
        self.assertNotIn("s3cret", str(cm.exception))

    def test_a_feed_that_cannot_be_read_is_an_alert_not_a_silent_day(self):
        with unittest.mock.patch.object(mp, "fetch_feed", side_effect=RuntimeError("HTTP 401: the read token was refused")):
            lines, alerts = mp.check(NOW, env={"MIRROR_EXECUTOR_URL": "https://e.example", "MIRROR_READ_TOKEN": "t"})
        self.assertTrue(alerts and "MIRROR FEED UNREADABLE" in alerts[0] and "401" in alerts[0])


class P7NeverFatal(unittest.TestCase):
    def test_check_never_raises(self):
        with unittest.mock.patch.object(mp.md, "read_shadow", side_effect=RuntimeError("disk")):
            lines, alerts = mp.check(NOW, feed=feed(live=book([row(D, BIG)])), date=D, env={})
        self.assertTrue(alerts and "MIRROR PARITY FAILED" in alerts[0])
        self.assertEqual(mp.check(NOW, feed={"kind": mp.FEED_KIND, "books": {}}, date=D, env={})[1], [])

    def test_the_monitor_hook_is_never_fatal_and_runs_after_the_paper_book(self):
        def run(check):
            alerts, out = ["earlier"], io.StringIO()
            with contextlib.redirect_stdout(out):
                monitor.mirror_parity_step(alerts, NOW, check=check)
            return alerts, out.getvalue()
        self.assertEqual(run(lambda now=None: ([], [])), (["earlier"], ""))             # not deployed: silent
        alerts, text = run(lambda now=None: (["mirror live live 2026-11-10: HG trade"], ["MIRROR LIVE MISMATCH — HG"]))
        self.assertEqual(alerts, ["earlier", "MIRROR LIVE MISMATCH — HG"])
        self.assertIn("HG trade", text)
        for boom in (RuntimeError("x"), SystemExit(2)):
            def check(now=None, boom=boom):
                raise boom
            alerts, text = run(check)
            self.assertEqual(alerts, ["earlier"])
            self.assertIn("mirror parity unavailable", text)
        with open(os.path.join(HERE, "..", "monitor.py")) as f:
            src = f.read()
        body = src[src.index("def main():"):]
        self.assertEqual(body.count("mirror_parity_step(alerts, now)"), 1)
        self.assertLess(body.index("mirror_dry_step(alerts, now)"), body.index("mirror_parity_step(alerts, now)"))
        self.assertLess(body.index("json.dump(snap, f, indent=2)"), body.index("mirror_parity_step(alerts, now)"))


class P8RealFeed(Base):
    def test_a_real_executor_feed_reads_end_to_end(self):
        with open(os.path.join(HERE, "fixtures", "mirror-feed-2026-11.json")) as f:
            fd = json.load(f)
        view = fd["books"]["dry"]
        rows = {r["session"]: r for r in mp._rows(view)}
        self.assertEqual(sorted(rows), ["2026-11-06", "2026-11-09"])
        last = rows["2026-11-09"]
        self.assertEqual(set(last["sleeves"]), {"HG", "KMLM", "SLEEVE", "HARV"})
        held = {e: mp.weights_of(s, last["prices"])[0] for e, s in last["sleeves"].items()}
        self.assertEqual({e: sorted(w) for e, w in held.items()},
                         {"HG": ["BIL"], "KMLM": ["PULS", "SOXL", "TECL"], "SLEEVE": ["BOXX"], "HARV": ["PULS"]})
        # what Composer held after 2026-11-09 (the monitor's snapshot that day)
        self.comp["2026-11-09"] = {e: {"holdings": h, "ret": None, "basis": None, "kind": "close", "taken_at": "x"} for e, h in {
            "HG": {"BIL": 1.0}, "KMLM": {"SOXL": 0.38, "TECL": 0.37, "PULS": 0.25}, "SLEEVE": {"BOXX": 1.0},
            "HARV": {"PULS": 1.0}}.items()}
        lines, alerts = self.run_check(fd, date="2026-11-09", now=datetime.datetime(2026, 11, 9, 21, 40, tzinfo=datetime.timezone.utc))
        self.assertEqual(alerts, [])
        self.assertIn("4 of 4 engines hold the same", "\n".join(lines))
        self.assertIn("mirror paper dry 2026-11-09", lines[0])
        # the knife-edge day: the 15:54 decision was not Composer's, and it is said
        self.comp["2026-11-06"] = {e: {"holdings": h, "ret": None, "basis": None, "kind": "close", "taken_at": "x"} for e, h in {
            "HG": {"TECL": 1.0}, "KMLM": {"TECL": 0.76, "ZVOL": 0.14, "PULS": 0.10}, "SLEEVE": {"BOXX": 1.0},
            "HARV": {"PULS": 0.64, "ZVOL": 0.36}}.items()}
        _, alerts = self.run_check(fd, date="2026-11-06", now=datetime.datetime(2026, 11, 6, 21, 40, tzinfo=datetime.timezone.utc))
        self.assertEqual(sorted(a.split(" on ")[0] for a in alerts), ["MIRROR PAPER MISMATCH — HARV", "MIRROR PAPER MISMATCH — KMLM"])


CREDIT = 13021.40                                                          # the operator scales HG up


def cr(amount=CREDIT, sleeve="HG", kind="credit", **kw):
    """one entry of a session row's "credits", as ibkr-executor's mirror._apply_credits writes it"""
    return dict({"sleeve": sleeve, "amount": amount, "kind": kind, "id": f"{kind}-{sleeve}", "note": "scale to $50k"}, **kw)


UP = dict(BIG, HG=sleeve({"BIL": 370 + 142}, cash=10.0 + CREDIT - 142 * 91.5))   # HG bought 142 BIL ($12,993.00) with it


def buy(eng, sym, qty, filled=None, price=None):
    """one venue BUY of a session row's "orders", as ibkr-executor's mirror._summary writes it: its split is
    of the FILLED quantity (mirror_core.book_fill)"""
    f = qty if filled is None else filled
    px = price if price is not None else PX[sym]
    return {"id": f"mirror-{D}-B-{sym}", "side": "BUY", "symbol": sym, "qty": qty, "filled": f, "price": px if f else None,
            "ref": PX[sym], "limit": round(PX[sym] * 1.005, 2), "commission": 0.0, "cost_bps": 0.0 if f else None,
            "how": "filled" if f == qty else "cancelled", "split": {eng: f} if f else {}}


def buys(before, after, prices=None):
    """the BUYs, filled in full, of a session that took the sleeves from `before` to `after`"""
    out = []
    for eng, sl in after.items():
        for sym, q in sl["shares"].items():
            d = q - (before.get(eng) or {}).get("shares", {}).get(sym, 0)
            if d > 0:
                out.append(buy(eng, sym, d, price=(prices or PX)[sym]))
    return out


class CreditRows:
    """the rows of a credit day (P11, P13)"""

    def flat(self, day, syms):
        return {s: PX[s] for s in syms}

    @staticmethod
    def moved(sym, by):
        """closes with `sym` up `by` on D, after the plan's prices (the row's "prices" are PX)"""
        return lambda day, syms: {s: PX[s] * (1 + by if day == D and s == sym else 1.0) for s in syms}

    def fd(self, credits="absent", after=None, before=None, **kw):
        if credits != "absent":
            kw["credits"] = credits
        kw.setdefault("orders", buys(before or BIG, after or UP, kw.get("prices")))   # what the session's buys were
        return feed(live=book([row(D0, before or BIG), row(D, after or UP, **kw)]))

    def recs(self):
        return {r["engine"]: r for r in self.rows()}

    @staticmethod
    def text(lines):
        return "\n".join(lines).replace("-0 bps", "+0 bps")


class P11CreditDay(CreditRows, Base):
    """the scale-up: POST /mirror/credit queues a credit, the executor applies it to the sleeve's cash
    before that session's plan and lists it in the session row's "credits". Before the credits were
    read, the credit was the sleeve's return: on the executor's own code, $10k credited to $50k was four
    false "RETURN GAP +400.00%" alerts"""

    def setUp(self):
        super().setUp()
        for d in (D0, D):
            for e in ("HG", "HARV"):
                self.comp[d][e]["ret"] = 0.0

    def test_a_scale_up_credit_is_not_a_return(self):
        lines, alerts = self.run_check(self.fd([cr()]), closes=self.flat)
        self.assertEqual(alerts, [])
        recs = self.recs()
        self.assertAlmostEqual(recs["HG"]["diff_bps"], 0.0, delta=0.05)
        self.assertEqual((recs["HG"]["credit_in"], recs["HG"]["credit_basis"]), (CREDIT, "chained"))
        self.assertNotIn("credit_in", recs["HARV"])
        self.assertIn("day return, mirror - Composer: HG +0 bps ($13,021.40 credited by the operator removed from the "
                      "day's return), HARV +0 bps", self.text(lines))
        # the twin: the same day with no record of the credit reads it as a +38% day (what every credit read as before)
        _, alerts = self.run_check(self.fd(), closes=self.flat)
        self.assertEqual([a.split(" on ")[0] for a in alerts], ["MIRROR LIVE RETURN GAP — HG"])
        self.assertIn("+38.45% against Composer's +0.00%", alerts[0])

    def test_a_real_move_on_the_scale_up_day_is_compared_as_the_true_return(self):
        up = self.moved("BIL", 0.01)                                     # BIL +1% between the plan's prices and the close
        self.comp[D]["HG"]["ret"] = 0.01
        lines, alerts = self.run_check(self.fd([cr()]), closes=up)
        self.assertEqual(alerts, [])
        hg = self.recs()["HG"]
        self.assertAlmostEqual(hg["ret"], 0.01, delta=0.0001)          # removed at face value it read +1.38%: the credited
        self.assertAlmostEqual(hg["diff_bps"], 0.0, delta=1.0)         # $13k's own +1% counted as the old $34k's
        # a real gap on a credit day still alarms, and says the credit was taken out
        self.comp[D]["HG"]["ret"] = -0.01
        _, alerts = self.run_check(self.fd([cr()]), closes=up)
        self.assertEqual(len(alerts), 1)
        self.assertIn("RETURN GAP — HG", alerts[0])
        self.assertIn("+1.00% against Composer's -1.00% though both went into the day holding the same ($13,021.40 "
                      "credited by the operator removed from the day's return): look at", alerts[0])
        # the move came BEFORE the plan (its prices are the closes): the credit bought at the moved price, and the chained
        # return is the face-value one, to the cent
        px = dict(PX, BIL=91.5 * 1.01)
        after = dict(BIG, HG=sleeve({"BIL": 370 + 140}, cash=10.0 + CREDIT - 140 * px["BIL"]))
        self.comp[D]["HG"]["ret"] = 0.01
        _, alerts = self.run_check(feed(live=book([row(D0, BIG), row(D, after, buys(BIG, after, px), prices=px,
                                                            credits=[cr()])])), closes=up)
        self.assertEqual(alerts, [])
        e0, e1 = 370 * 91.5 + 10.0, 510 * px["BIL"] + after["HG"]["cash"]
        hg = self.recs()["HG"]
        self.assertEqual(hg["credit_basis"], "chained")
        self.assertAlmostEqual(hg["ret"], (e1 - CREDIT) / e0 - 1, delta=1e-6)
        self.assertAlmostEqual(hg["ret"], 0.01, delta=0.0001)

    def test_the_credited_dollars_own_move_into_the_close_goes_out_with_them(self):
        """at the live book's size: a $2,650 sleeve in SOXL credited 4.5x ($11,850, the $50k scale-up), SOXL +0.4% between the
        plan's prices and the close. At face value the $11,850's own +0.4% reads as +179 bps on the old $2,650: a false gap"""
        f = 11850.0
        self.comp = {d: {"KMLM": {"holdings": {"SOXL": 1.0}, "ret": 0.0, "basis": "dav", "kind": "close", "taken_at": "x"}}
                     for d in (D0, D)}
        self.comp[D]["KMLM"]["ret"] = 0.004
        late = self.moved("SOXL", 0.004)
        before = {"KMLM": sleeve({"SOXL": 66})}                                              # $2,650.00
        traded = {"KMLM": sleeve({"SOXL": 66 + 296}, cash=10.0 + f - 296 * 40.0)}           # it bought 296 SOXL with it
        _, alerts = self.run_check(self.fd([cr(f, "KMLM")], traded, before), closes=late)
        self.assertEqual(alerts, [])
        rec = self.recs()["KMLM"]
        self.assertEqual(rec["credit_basis"], "chained")
        self.assertAlmostEqual(rec["ret"], 0.004, delta=0.0001)
        self.assertAlmostEqual(rec["diff_bps"], 0.0, delta=1.0)
        e0, e1 = 66 * 40.0 + 10.0, 362 * 40.0 * 1.004 + traded["KMLM"]["cash"]
        self.assertGreater(((e1 - f) / e0 - 1 - 0.004) * 1e4, mp.RETURN_ALARM_BPS)        # what face value alarms on
        # the twin: a sleeve that sat out kept the credit as cash, which earned nothing: face value is exact for it (chained,
        # the cash would dilute the old SOXL's move)
        out = {"KMLM": sleeve({"SOXL": 66}, cash=10.0 + f, action="skip", reason="tree not attested")}
        _, alerts = self.run_check(self.fd([cr(f, "KMLM")], out, before), closes=late)
        self.assertFalse(any("RETURN GAP" in a for a in alerts))
        rec = self.recs()["KMLM"]
        self.assertEqual(rec["credit_basis"], "face")
        self.assertAlmostEqual(rec["ret"], 66 * 40.0 * 0.004 / e0, delta=1e-6)             # the old SOXL's +0.4%, on the old $

    def test_the_credit_goes_in_at_the_fills_not_at_the_plans_price(self):
        """the same sleeve's buys fill 0.3% above the plan's price (the market moved between the quote and the fill) and
        SOXL closes there. Chained at the plan's price, that 0.3% on the credited $11,850 is charged to the old $2,650:
        -134 bps. The old SOXL earned +0.3%, as Composer did"""
        f = 11850.0
        self.comp = {d: {"KMLM": {"holdings": {"SOXL": 1.0}, "ret": 0.0, "basis": "dav", "kind": "close", "taken_at": "x"}}
                     for d in (D0, D)}
        self.comp[D]["KMLM"]["ret"] = 0.003
        fill = 40.0 * 1.003
        before = {"KMLM": sleeve({"SOXL": 66})}
        traded = {"KMLM": sleeve({"SOXL": 66 + 295}, cash=10.0 + f - 295 * fill)}
        buy = {"id": "mirror-x-B-SOXL", "side": "BUY", "symbol": "SOXL", "qty": 295, "filled": 295, "price": fill, "ref": 40.0,
               "limit": 40.2, "commission": 0.0, "cost_bps": 30.0, "how": "filled", "split": {"KMLM": 295}}
        _, alerts = self.run_check(self.fd([cr(f, "KMLM")], traded, before, orders=[buy]), closes=self.moved("SOXL", 0.003))
        self.assertEqual(alerts, [])
        rec = self.recs()["KMLM"]
        self.assertEqual(rec["credit_basis"], "chained")
        self.assertAlmostEqual(rec["diff_bps"], 0.0, delta=0.5)
        self.assertEqual(mp.session_prices({"prices": dict(PX), "orders": [buy, dict(buy, filled=0, price=None, symbol="BIL")]}),
                         dict(PX, SOXL=fill))                                           # an unfilled order keeps the plan's

    def test_a_dividend_stays_in_the_return(self):
        div = {"sleeve": "HG", "amount": 55.5, "kind": "dividend", "id": "dividend-BIL-2026-11-03-HG"}
        both = dict(BIG, HG=sleeve({"BIL": 512}, cash=10.0 + 55.5 + CREDIT - 142 * 91.5))
        lines, alerts = self.run_check(self.fd([cr(), div], both), closes=self.flat)
        self.assertEqual(alerts, [])
        hg = self.recs()["HG"]
        self.assertEqual(hg["credit_in"], CREDIT)                                            # the dividend is not a credit
        self.assertAlmostEqual(hg["diff_bps"], 55.5 / (370 * 91.5 + 10.0) * 1e4, delta=0.1)  # +16.4 bps: it is the return
        self.assertIn("HG +16 bps ($13,021.40 credited by the operator removed from the day's return)", self.text(lines))
        # a dividend alone reads exactly as a day the row lists no credits at all
        paid = dict(BIG, HG=sleeve({"BIL": 370}, cash=10.0 + 55.5))
        lines, alerts = self.run_check(self.fd([div], paid), closes=self.flat)
        led = self.rows()
        self.assertEqual((lines, alerts, led), self.run_check(self.fd(after=paid), closes=self.flat) + (self.rows(),))
        self.assertIn("HG +16 bps, HARV +0 bps", self.text(lines))
        self.assertNotIn("credit_in", led[0])

    def test_a_fee_debit_is_taken_out(self):
        before = dict(BIG, HG=sleeve({"BIL": 370}, cash=100.0))
        fee = dict(BIG, HG=sleeve({"BIL": 370}, cash=75.0, action="hold", reason="at target"))
        lines, alerts = self.run_check(self.fd([cr(-25.0, note="IBKR market data fee")], fee, before), closes=self.flat)
        self.assertEqual(alerts, [])
        hg = self.recs()["HG"]
        self.assertAlmostEqual(hg["diff_bps"], 0.0, delta=0.05)                             # before: -7.4 bps
        self.assertEqual((hg["credit_in"], hg["credit_basis"]), (-25.0, "face"))
        self.assertIn("HG +0 bps ($25.00 debited by the operator removed from the day's return)", self.text(lines))
        # a fee and a credit the same session: their net comes out, and the line says it is a net
        both = dict(BIG, HG=sleeve({"BIL": 370}, cash=575.0, action="hold", reason="at target"))
        lines, alerts = self.run_check(self.fd([cr(-25.0), cr(500.0)], both, before), closes=self.flat)
        self.assertEqual(alerts, [])
        self.assertEqual(self.recs()["HG"]["credit_in"], 475.0)
        self.assertIn("HG +0 bps ($475.00 net credited by the operator removed from the day's return)", self.text(lines))

    def test_a_credit_and_a_transfer_on_the_same_day(self):
        moved = 18 * 91.5                                                                   # HG sells 18 BIL for HARV
        t = [{"from": "HG", "to": "HARV", "amount": moved, "status": "moved", "moved": moved}]
        c = [cr(), cr(6000.0, "HARV")]
        after = {"HG": sleeve({"BIL": 370 - 18 + 142}, cash=10.0 + CREDIT - 142 * 91.5),
                 "HARV": sleeve({"PULS": 355 + 154}, cash=10.0 + 6000.0 + moved - 154 * 49.5)}
        _, alerts = self.run_check(self.fd(c, after, transfers=t), closes=self.flat)
        self.assertEqual(alerts, [])
        recs = self.recs()
        for e, tin, cin in (("HG", -moved, CREDIT), ("HARV", moved, 6000.0)):
            self.assertAlmostEqual(recs[e]["diff_bps"], 0.0, delta=0.05, msg=e)
            self.assertEqual((recs[e]["transfer_in"], recs[e]["credit_in"]), (tin, cin), e)
        # PULS +1% after the plan's prices: both flows go out with what they earned, the old $17.6k earned 1%
        self.comp[D]["HARV"]["ret"] = 0.01
        _, alerts = self.run_check(self.fd(c, after, transfers=t), closes=self.moved("PULS", 0.01))
        self.assertEqual(alerts, [])
        self.assertAlmostEqual(self.recs()["HARV"]["ret"], 0.01, delta=0.0002)

    def test_credits_that_cannot_be_read_get_no_return_comparison_and_say_why(self):
        no_amount = "a credit to the sleeve has no finite amount: "
        bad_hg = [(no_amount + "'13021.40'", [cr("13021.40")]),
                  (no_amount + "nan", [cr(float("nan"))]),
                  (no_amount + "inf", [cr(float("inf"))]),
                  (no_amount + "True", [cr(True)]),
                  (no_amount + "None", [cr(None)]),
                  (no_amount + "1000000000", [cr(10 ** 400)]),                         # no float holds it
                  (no_amount + "nan", [cr(), cr(float("nan"), kind="dividend")]),        # a dividend's amount too
                  ("a credit to the sleeve does not say its kind", [{k: v for k, v in cr().items() if k != "kind"}]),
                  ("a credit to the sleeve does not say its kind", [cr(kind=None)]),
                  ("a credit to the sleeve is of kind 'bonus', neither an operator credit nor a dividend", [cr(kind="bonus")])]
        bad_row = [("the session row's credits are not a list", {"HG": CREDIT}),
                   ("the session row's credits are not a list", "HG +13021.40"),
                   ("a credits entry is not a record", [cr(), "HG +13021.40"]),
                   ("a credits entry does not name its sleeve", [{"amount": CREDIT, "kind": "credit"}]),
                   ("a credits entry does not name its sleeve", [cr(sleeve=None)])]
        cases = [(why, c, "HG") for why, c in bad_hg] + [(why, c, "HG, HARV") for why, c in bad_row]
        for why, credits, who in cases:
            lines, alerts = self.run_check(self.fd(credits), closes=self.flat)
            self.assertEqual(alerts, [], why)                                                # never alarmed on
            text = "\n".join(lines)
            self.assertIn("2 of 2 engines hold the same", text)                              # the holdings are still compared
            self.assertIn(f"; day return NOT compared for {who} ({why}", text, why)
            recs = self.recs()
            self.assertNotIn("ret", recs["HG"], why)
            self.assertTrue(recs["HG"]["ret_skipped"].startswith(why), why)
            self.assertEqual("ret" in recs["HARV"], who == "HG", why)                       # only the sleeves it may touch
        # an unreadable entry for a sleeve this book does not hold stops nobody
        lines, alerts = self.run_check(self.fd([cr(), cr(float("nan"), "KMLM")]), closes=self.flat)
        self.assertEqual(alerts, [])
        self.assertNotIn("NOT compared", "\n".join(lines))
        self.assertEqual(mp.credited_in({"credits": [cr(float("nan"), "KMLM"), cr(5.0)]}, "HG"), (5.0, None))
        self.assertEqual(mp.credited_in({}, "HG"), (0.0, None))
        self.assertEqual(mp.credited_in({"credits": [cr(1e300)]}, "HG"), (1e300, None))
        self.assertEqual(mp.credited_in({"credits": [cr(1e308), cr(1e308)]}, "HG"),
                         (None, "the credits to the sleeve do not add up to a finite amount"))


GOLDEN_Y = {"HG": sleeve({"BIL": 370}), "HARV": sleeve({"PULS": 355}), "SLEEVE": sleeve({"BOXX": 30}, cash=25.0),
            "KMLM": sleeve({"SOXL": 30, "TECL": 12, "PULS": 20}, cash=40.0)}
GOLDEN_T = {"HG": sleeve({"BIL": 352}), "HARV": sleeve({"PULS": 388}, cash=23.5),
            "KMLM": sleeve({"SOXL": 30, "TECL": 12, "PULS": 20}, cash=40.0, action="hold",
                           reason="inside the corridor: largest gap 2.0% vs 10%"),
            "SLEEVE": sleeve({"BOXX": 30}, cash=25.0, action="hold", reason="at target")}
# what mirror_parity.book_parity printed for this day before it read credits (its code of 6b7d4683, unchanged to b7c0849d)
GOLDEN_LINES = [
    "mirror live live 2026-11-10: HG trade | HARV trade | KMLM hold | SLEEVE hold; 0 order(s)",
    "  parity vs Composer: 3 of 4 engines hold the same; day return, mirror - Composer: HG -1 bps, HARV +218 bps, KMLM +43 bps "
    "(different holdings into the day), SLEEVE -2 bps (yesterday not comparable)"]
GOLDEN_ALERTS = [
    "MIRROR LIVE RETURN GAP — HARV on 2026-11-10 (book live): +2.18% against Composer's +0.00% though both went into the day "
    "holding the same: look at the fills and the booking.",
    "MIRROR LIVE MISMATCH — KMLM on 2026-11-10 (book live): the mirror holds SOXL 35%, TECL 35%, PULS 29%; Composer holds SOXL "
    "38%, TECL 38%, PULS 25% (half-L1 4.4%, allowed 3.8%). The shadow ledger says nothing for this session. The sleeve held "
    "(inside the corridor: largest gap 2.0% vs 10%): the two books may be on different corridor paths."]
GOLDEN_LEDGER = (
    '[{"action":"trade","book":"live","carried_same":true,"cash":10.0,"composer":{"BIL":1.0},"composer_ret":0.0001,'
    '"date":"2026-11-10","diff_bps":-1.0,"dist":0.0002,"engine":"HG","equity":32218.0,"mode":"live","parity":"same",'
    '"reason":"to target","ret":0.0,"shadow":null,"shares":{"BIL":352},"tol":0.03,"transfer_in":-1647.0,"version":"v1",'
    '"weights":{"BIL":0.9996896145012105}},{"action":"trade","book":"live","carried_same":true,"cash":23.5,'
    '"composer":{"PULS":1.0},"composer_ret":0.0,"date":"2026-11-10","diff_bps":218.5,"dist":0.0006,"engine":"HARV",'
    '"equity":19229.5,"mode":"live","parity":"same","reason":"to target","ret":0.021847,"shadow":null,'
    '"shares":{"PULS":388},"tol":0.03,"transfer_in":1647.0,"version":"v1","weights":{"PULS":0.9987779193426766}},'
    '{"action":"hold","book":"live","carried_same":false,"cash":40.0,"composer":{"PULS":0.25,"SOXL":0.375,"TECL":0.375},'
    '"composer_ret":0.0123,"date":"2026-11-10","diff_bps":43.2,"dist":0.0445,"engine":"KMLM","equity":3430.0,'
    '"mode":"live","parity":"MISMATCH","reason":"inside the corridor: largest gap 2.0% vs 10%","ret":0.016618,'
    '"shadow":null,"shares":{"PULS":20,"SOXL":30,"TECL":12},"tol":0.0376,"version":"v1","weights":'
    '{"PULS":0.2886297376093295,"SOXL":0.3498542274052478,"TECL":0.3498542274052478}},{"action":"hold","book":"live",'
    '"carried_same":null,"cash":25.0,"composer":{"BOXX":1.0},"composer_ret":0.0002,"date":"2026-11-10","diff_bps":-2.0,'
    '"dist":0.0037,"engine":"SLEEVE","equity":3415.0,"mode":"live","parity":"same","reason":"at target","ret":0.0,'
    '"shadow":null,"shares":{"BOXX":30},"tol":0.03,"version":"v1","weights":{"BOXX":0.9926793557833089}}]')


class P12NoCreditsUnchanged(unittest.TestCase):
    def test_a_day_without_credits_reads_exactly_as_before(self):
        """a transfer, a +2% / +3.1% move, every suffix of the line, a RETURN GAP and a MISMATCH: lines, alerts and ledger
        rows equal what the parity monitor wrote before it read credits - with no "credits" in the row, an empty list, a
        dividend (a return: not read into the number), a credit to a sleeve this book does not hold, a credit and its undo"""
        comp = {"HG": {"holdings": {"BIL": 1.0}, "ret": 0.0001, "kind": "close"},
                "HARV": {"holdings": {"PULS": 1.0}, "ret": 0.0, "kind": "close"},
                "KMLM": {"holdings": {"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25}, "ret": 0.0123, "kind": "close"},
                "SLEEVE": {"holdings": {"BOXX": 1.0}, "ret": 0.0002, "kind": "close"}}
        comp_prev = {"HG": {"holdings": {"BIL": 1.0}}, "HARV": {"holdings": {"PULS": 1.0}},
                     "KMLM": {"holdings": {"SOXL": 0.75, "PULS": 0.25}}}

        def closes(day, syms):
            p = dict(PX, PULS=49.5 * 1.02, SOXL=40.0 * 1.031) if day == D else dict(PX)
            return {s: p[s] for s in syms}
        t = [{"from": "HG", "to": "HARV", "amount": 1647.0, "status": "moved", "moved": 1647.0}]
        for credits in ("absent", [], [cr(12.5, "HARV", "dividend")], [cr(500.0, "ZZZ")], [cr(500.0), cr(-500.0)],
                        [cr(0.1), cr(0.2), cr(-0.3)]):                              # 5.55e-17 in floats: rounded, 0
            kw = {"transfers": t} if credits == "absent" else {"transfers": t, "credits": credits}
            view = book([row(D0, GOLDEN_Y), row(D, GOLDEN_T, **kw)])
            lines, alerts, led = mp.book_parity("live", view, D, comp, {}, closes, D0, comp_prev)
            self.assertEqual(lines, GOLDEN_LINES, credits)
            self.assertEqual(alerts, GOLDEN_ALERTS, credits)
            self.assertEqual(json.dumps(led, sort_keys=True, separators=(",", ":")), GOLDEN_LEDGER, credits)



class P13ChainedOnlyWhenTheBuysFilled(CreditRows, Base):
    """item 12: at 6b122160 a sleeve that TRADED was chained even when none of its buys filled (the deposit not
    usable yet: every buy rejected; or the buy rested and was cancelled). Its credit stayed cash, and chained
    through the close that cash diluted the old capital's move: a false RETURN GAP. The executor's own
    verification run (scenario E18) read KMLM -123 bps against a no-credit twin's -7"""
    F = 11850.0

    def setUp(self):
        super().setUp()
        self.comp = {d: {"KMLM": {"holdings": {"SOXL": 1.0}, "ret": 0.0, "basis": "dav", "kind": "close", "taken_at": "x"}}
                     for d in (D0, D)}
        self.comp[D]["KMLM"]["ret"] = 0.02                                       # SOXL +2% after the plan's prices
        self.before = {"KMLM": sleeve({"SOXL": 66})}                            # $2,650.00
        self.e0 = 66 * 40.0 + 10.0

    def kmlm(self, after, orders, **kw):
        lines, alerts = self.run_check(self.fd([cr(self.F, "KMLM")], after, self.before, orders=orders, **kw),
                                       closes=self.moved("SOXL", 0.02))
        return lines, alerts, self.recs()["KMLM"]

    def test_a_sleeve_whose_buys_never_filled_is_taken_out_at_face_value(self):
        kept = {"KMLM": sleeve({"SOXL": 66}, cash=10.0 + self.F)}                # the plan traded; the cash is all there
        for why, orders in (("every buy rejected", [buy("KMLM", "SOXL", 296, filled=0)]),
                            ("no order at all", []),
                            ("a buy of another sleeve filled", [buy("HG", "SOXL", 296)]),
                            ("a sell of this sleeve filled", [dict(buy("KMLM", "SOXL", 5), side="SELL")]),
                            ("a buy whose split cannot be read", [dict(buy("KMLM", "SOXL", 296), split="KMLM")]),
                            ("a buy that says it filled none", [dict(buy("KMLM", "SOXL", 296), filled=0)]),
                            ("orders that are not a list", "SOXL 296")):
            with self.subTest(why=why):
                lines, alerts, rec = self.kmlm(kept, orders)
                self.assertEqual(rec["credit_basis"], "face", why)
                self.assertAlmostEqual(rec["ret"], 66 * 40.0 * 0.02 / self.e0, delta=1e-6)   # the old SOXL's +2%
                self.assertAlmostEqual(rec["diff_bps"], -0.8, delta=0.1)                      # its $10 of cash
                self.assertFalse([a for a in alerts if "RETURN GAP" in a], alerts)
        # what 6b122160 read: chained, the $11,850 of cash dilutes the old $2,650's +2% to +0.36%: -164 bps, alarmed
        v = 66 * 40.0 + 10.0 + self.F
        chained = (v - self.F) / self.e0 * ((66 * 40.0 * 1.02 + 10.0 + self.F) / v) - 1
        self.assertLess((chained - 0.02) * 1e4, -mp.RETURN_ALARM_BPS)

    def test_a_sleeve_whose_buys_filled_is_chained_even_partly(self):
        full = {"KMLM": sleeve({"SOXL": 66 + 296}, cash=10.0 + self.F - 296 * 40.0)}
        lines, alerts, rec = self.kmlm(full, [buy("KMLM", "SOXL", 296)])
        self.assertEqual(rec["credit_basis"], "chained")
        self.assertAlmostEqual(rec["diff_bps"], 0.0, delta=1.0)
        self.assertEqual(alerts, [])
        part = {"KMLM": sleeve({"SOXL": 66 + 10}, cash=10.0 + self.F - 10 * 40.0)}   # 10 of 296 filled at the cancel
        lines, alerts, rec = self.kmlm(part, [buy("KMLM", "SOXL", 296, filled=10)])
        self.assertEqual(rec["credit_basis"], "chained")
        # a netted buy of two sleeves: its split names this one
        both = [dict(buy("KMLM", "SOXL", 296), qty=300, filled=300, split={"KMLM": 296, "HG": 4})]
        self.assertEqual(self.kmlm(full, both)[2]["credit_basis"], "chained")

    def test_a_cross_it_bought_in_is_a_filled_buy(self):
        full = {"KMLM": sleeve({"SOXL": 66 + 296}, cash=10.0 + self.F - 296 * 40.0)}
        cross = [{"symbol": "SOXL", "qty": 296, "price": 40.0, "sellers": {"HG": 296}, "buyers": {"KMLM": 296}}]
        lines, alerts, rec = self.kmlm(full, [], crosses=cross)
        self.assertEqual(rec["credit_basis"], "chained")
        self.assertAlmostEqual(rec["diff_bps"], 0.0, delta=1.0)
        sold = [dict(cross[0], sellers={"KMLM": 296}, buyers={"HG": 296})]       # it SOLD in the cross: no buy of it
        self.assertEqual(self.kmlm({"KMLM": sleeve({"SOXL": 66}, cash=10.0 + self.F)}, [], crosses=sold)[2]["credit_basis"],
                         "face")

    def test_bought_in_reads_only_what_the_row_says(self):
        self.assertTrue(mp.bought_in({"orders": [buy("KMLM", "SOXL", 3)]}, "KMLM"))
        self.assertFalse(mp.bought_in({"orders": [buy("KMLM", "SOXL", 3)]}, "HG"))
        for orders in (None, "x", [None, 5, "BUY"], [dict(buy("KMLM", "SOXL", 3), filled=float("nan"))],
                       [dict(buy("KMLM", "SOXL", 3), split={"KMLM": True})], [dict(buy("KMLM", "SOXL", 3), side=None)]):
            self.assertFalse(mp.bought_in({"orders": orders}, "KMLM"), orders)
        for crosses in (None, "x", [None], [{"buyers": "KMLM"}], [{"buyers": {"KMLM": 0}}]):
            self.assertFalse(mp.bought_in({"crosses": crosses}, "KMLM"), crosses)
        self.assertTrue(mp.bought_in({"crosses": [{"buyers": {"KMLM": 2}}]}, "KMLM"))

    def test_v_minus_the_flows_at_or_below_zero_falls_back_to_face(self):
        """item 13: no test failed with the guard v - flows > 0 dropped (a surviving mutant). Chained, an old
        capital worth nothing at the session's prices divides nothing by e0 and multiplies it out"""
        s = sleeve({"SOXL": 24}, cash=0.0)                                      # after the session: $960 at 40.0
        px = {"SOXL": 40.0}
        for cred, net in ((960.0, 0.0), (1000.0, 0.0), (900.0, 60.0), (900.0, 100.0)):
            with self.subTest(cred=cred, net=net):
                ret, basis = mp.day_return(10.0, 1005.0, net, cred, s, px, bought=True)
                self.assertEqual((ret, basis), ((1005.0 - net - cred) / 10.0 - 1, "face"))
        ret, basis = mp.day_return(10.0, 1005.0, 0.0, 900.0, s, px, bought=True)                # $60 of old capital
        self.assertEqual(basis, "chained")
        self.assertAlmostEqual(ret, (960.0 - 900.0) / 10.0 * (1005.0 / 960.0) - 1, places=12)
        self.assertEqual(mp.day_return(10.0, 1005.0, 0.0, 900.0, s, px)[1], "face")             # bought defaults to no

    def test_the_credit_rounded_to_the_cent_before_it_is_read(self):
        """item 13: no test failed with credited_in's round(net, 2) dropped (a surviving mutant): 0.1 + 0.2 - 0.3
        is 5.55e-17 in floats, a 'credit' that changed the ledger row and the line (P12 holds it byte for byte)"""
        self.assertEqual(mp.credited_in({"credits": [cr(0.1), cr(0.2), cr(-0.3)]}, "HG"), (0.0, None))
        self.assertEqual(mp.credited_in({"credits": [cr(0.105), cr(0.2)]}, "HG"), (0.3, None))


if __name__ == "__main__":
    unittest.main()
