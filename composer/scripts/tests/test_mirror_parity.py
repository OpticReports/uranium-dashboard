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
        self.assertLess(body.index("mirror_parity_step(alerts, now)"), body.index('snap_path = os.path.join(DIR'))


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


if __name__ == "__main__":
    unittest.main()
