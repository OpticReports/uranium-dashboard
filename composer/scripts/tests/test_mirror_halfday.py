"""Gate tests for the mirror brain on NYSE HALF-DAYS (a 13:00 close; the decision instant 12:54:00 ET), on
REAL data: fixtures/mirror-halfday-2025.json.gz holds FMP's raw 1-minute rows (close AND volume) for the
three 13:00 closes of 2025 (07-03, 11-28, 12-24) and the regular session 2025-07-02, from 12:20 ET (plus each
ticker's last trade before), and Yahoo's daily charts 2024-06..2025-12 for the 62 tickers the brain reads.
FMP's rows reach the brain through the REAL shadow_runner.fetch_minutes (urllib's urlopen is the stand-in);
the static calendar is told those dates (it starts in 2026), and the approved trees in use today are
evaluated, as mirror_brain.era_of does for a date before the first era. No network, no key.

In FMP's archive of these half-days the volume after 12:45 falls to about a third of the 12:30-12:44
rate and 5-13 tickers (SPY on 11-28) carry no volume at all; the bars themselves keep coming.

  H1  the three half-days SETTLE through the live pinned path at T+30 s: the decision bar complete, every
      engine ok, each decision that of the same approved tree on the day's OFFICIAL close; the twin
      (FMP's bars without volume never seen, i.e. what the brain read before) refuses 07-03 (the feed
      looks dead) and 11-28 (SPY's last traded bar ends 12:46) for as long as it is asked
  H2  the rule never reaches a full day: 07-03's bars on a 16:00 calendar still refuse; on the regular
      session 2025-07-02 the payload is the same byte for byte with and without the bars without
      volume, which a half-day's calendar would have counted
  H3  dead or stale data on a half-day is still refused: no bars near the instant; bars without volume
      over trades more than 15 minutes old (SPY's too); SPY's 12:54 minute not published yet, its last trade 8
      minutes old, or 1 or 2 minutes old with an earlier bar without volume that day (only the bar's end at the
      instant tells 'published without volume' from 'not published' there); the 15-minute boundary, to the bar
  H4  one brain: the composer-side paper book (mirror_dry.Minutes, its disk cache included) and the
      `--at` path reach the pinned path's decision on a half-day; fetch_minutes(quiet=True) lists exactly
      the bars without volume and changes nothing else
  H5  the paper book's half-day clock: a buy left unfilled at 12:54 can fill until the bar ending 12:59:00
      (the executor cancels at the close minus 60 s), never on the bar ending 13:00; its disk cache is final
      from 13:30; a Composer snapshot after 13:00 is the half-day's close for the parity record
  H6  the half-day preview routine's attestation (12:15 ET routine, ~12:16) counts at 12:54; one made over
      an hour before the instant does not
  H7  a FROZEN feed (bars without volume at the last trade's price, from 12:44 or 12:38) is refused: SPY
      alone, the whole book, all but SPY, on the pinned path, the `--at` path and the paper book; the
      tickers the rule leans on frozen, the real trades untouched, are not counted; twin: half the book
      without volume from 12:44 with FMP's real, moving closes settles, the same bars frozen do not; any bar
      moved counts, not only the bar at the instant. SPY, whose bar is the decision bar, is held to more on
      every path when its last trade is older than 2 minutes: a constant price off its trade's, a tick off, a
      stuck half-cent, moved once then back, 3 in a row at one price up to the instant are refused, each named
      in the breadth's NOT-counted line in SPY's own words; oscillating between two prices, 2 in a row, the
      real days settle. SPY's trade 1 or 2 minutes old (its volume gone from the last 1 or 2 bars) needs no
      such evidence while another ticker of the trees traded in the bar ending 12:54: one close, two equal
      closes, frozen at the trade's price or a tick off all settle on every path, and the same shapes 3
      minutes old are refused. With no such trade (round 7) its tests apply: the whole book frozen after the
      bar stamped 12:52 or 12:51, or muted after 12:52, is refused on every path; twins: muted after 12:51
      (two moving SPY closes) settles, and 11-28 frozen late (SPY's trade 8 minutes old, its bars moved before)
      settles, recorded; `problems` says which rule took SPY. The book is not held to SPY's rule (a ticker
      stuck a tick off is still counted). Units: the 2-minute boundary in FMP's bar stamps, the book's trade
      at the instant, QUIET_MOVE_TOL (one price within it), the residual shapes the rule lets through by design
  H8  the floor of REAL trades: no trade after 12:40 (or 12:44) anywhere, prices moving, is refused as the
      full-day rule refuses it, word for word; so is every ticker but SPY without a trade after 12:40 (the
      build's own floor; the `--at` path and the paper book too); a frozen tail; half the trees' tickers
      really trading settles, one fewer is refused; bars without volume 12 minutes before the instant are
      no evidence, with the floor held; SPY's trade 1 or 2 minutes old, SPY's exemption, does not lift the
      floor on any path
  H9  quotes.breadth gives the real trades and the leaned ones apart, the leaned named in `problems`
  H10 the brain's calendar and the executor's (blend.py, read with ast) agree on every date both cover; the
      executor's bound on SPY before the instant (mirror.py, read with ast by the executor's E11 evaluator: an
      equivalent expression such as 15 * 60.0 reads the same) is this side's QUIET_TRADE_MAX_S; a change made
      on both sides passes, on one side fails
  H11 below the floor the brain has read the whole book: its refusal is held REBUILD_EVERY_S (a book asking
      every 3 s gets one read in four, not 63 FMP calls each time), and says "FMP has not answered" when
      unanswered tickers of the trees are why (a sibling no tree reads, unanswered, never is); so does SPY's
      recent trade refused for want of a trade of the book at the instant (round 7)

The whole book without volume from 12:44 with moving prices (a reviewer's twin) is REFUSED here: no
ticker really traded within 2 minutes of the instant, below the floor (H8). The twin kept is half the
book (H7).

Run: python3 -m unittest composer.scripts.tests.test_mirror_halfday -v
"""
import ast
import contextlib
import copy
import datetime
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import unittest.mock
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.pop("FMP_API_KEY", None)
import mirror_brain as mb  # noqa: E402
import mirror_dry as md  # noqa: E402
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

UTC = datetime.timezone.utc
FIXTURE = os.path.join(HERE, "fixtures", "mirror-halfday-2025.json.gz")
HALF = ("2025-07-03", "2025-11-28", "2025-12-24")
REGULAR = "2025-07-02"
HOLIDAYS = {"2025-07-04", "2025-11-27", "2025-12-25"}        # NYSE 2025: the sessions before these half-days are right
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
FROZEN = "half-day, a frozen feed: "     # the words that lead SPY's refusal under its rule (mirror_brain.FROZEN_FEED)
SEC = datetime.timedelta(seconds=1)
LEANED = {                      # the tickers the rule counts on bars without volume at 12:54 on the real days (each moved)
    "2025-07-03": ["CORP", "HYG", "KIE", "LABU", "LQD", "PEJ", "PULS", "SVXY", "UDOW"],
    "2025-11-28": ["CORP", "KMLM", "QLD", "SOXS", "SPY", "SVIX", "TMF", "TMV", "USD", "VIXM", "VOOV"],
    "2025-12-24": ["BIL", "HYG", "KIE", "KMLM", "TMV", "VIXM"]}


def statuses(p):
    return {e: r["status"] for e, r in p["engines"].items()}


def targets(p):
    return {e: r.get("target") for e, r in p["engines"].items()}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class HalfDay(unittest.TestCase):
    """the fixture behind the brain's seams; FMP's rows can be edited per test (self.rows)"""
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE) as f:
            cls.fx = json.load(f)

    def setUp(self):
        self.rows = copy.deepcopy(self.fx["minutes"])
        self.calls = []
        self.fmp_times_out = None                 # (ticker, day) -> True: FMP's answer for it times out (a seam)
        era_for = sr.era_for
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(unittest.mock.patch("urllib.request.urlopen", self.urlopen))
        stack.enter_context(unittest.mock.patch.dict(sr.HALF_DAYS, {d: "13:00" for d in HALF}))
        stack.enter_context(unittest.mock.patch.object(sr, "NYSE_HOLIDAYS", sr.NYSE_HOLIDAYS | HOLIDAYS))
        stack.enter_context(unittest.mock.patch.object(sr, "era_for", lambda cfg, d: era_for(cfg, d) or cfg["eras"][-1]))
        for k in ("MIRROR_REQUIRE_ATTESTATION", "MIRROR_ATTEST_MAX_AGE_S"):
            stack.enter_context(unittest.mock.patch.dict(os.environ, {k: ""}))
        self.yh = md.Yahoo(fetch=lambda t: copy.deepcopy(self.fx["yahoo"][t]), actions=lambda t: None)

    # ---- the seams
    def urlopen(self, req, timeout=None):
        u = urllib.parse.urlparse(req.full_url if hasattr(req, "full_url") else str(req))
        if not u.path.endswith("/historical-chart/1min"):
            raise RuntimeError(f"no network in this test: {u.netloc}")
        q = urllib.parse.parse_qs(u.query)
        t, d = q["symbol"][0], q["from"][0]
        self.calls.append((t, d))
        if self.fmp_times_out is not None and self.fmp_times_out(t, d):
            raise TimeoutError("timed out")
        rows = (self.rows.get(d) or {}).get(t)
        if rows is None:
            raise RuntimeError(f"FMP {t} {d}: not in the fixture")
        return Resp(json.dumps([{"date": f"{d} {hm}:00", "close": c, "volume": v} for hm, c, v in reversed(rows)]).encode())

    def history(self, d):
        return lambda t: self.yh.live(t, asof=d)

    def instant(self, d):
        return mb.parse_at(f"{d} 12:54")

    def pinned(self, d, waits=(30,)):
        """the live path: pinned_attempt at T + each wait (s) until it settles -> (payload or None, the last 503)"""
        T = self.instant(d)
        clock = {"now": T}
        hist = mb.History(fetch=self.history(d), wall=lambda: clock["now"])
        att = mb.pinned_attempt(hist, key="k", wall=lambda: clock["now"])
        err = None
        for w in waits:
            clock["now"] = T + w * SEC
            try:
                return att(T), None
            except mb.NotPublished as exc:
                err = exc
        return None, err

    def at_path(self, d):
        """the `--at` path: mirror_brain.build(pinned=True) reading FMP itself (a dummy key: FMP is the fixture)"""
        T = self.instant(d)
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "k"}):
            return mb.build(T, fetch=self.history(d), pinned=True, wall=lambda: T + 30 * SEC, budget=600)

    def paper_path(self, d):
        """the composer-side paper book: mirror_dry.brain_payload through its own Minutes store"""
        T = self.instant(d)
        mn = md.Minutes(key="k", rate=1e9, sleep=lambda s: None, now=lambda: T + 86400 * SEC)
        with unittest.mock.patch.object(mb, "_utcnow", lambda: T + 30 * SEC):
            return md.brain_payload(d, "12:54", self.yh, mn)

    @staticmethod
    def named(p, says):
        """the tickers the `problems` line containing `says` lists after its last ': ' ([] when there is no such line)"""
        line = next((x for x in p["problems"] if says in x), None)
        return [] if line is None else [y.split()[0] for y in line.rsplit(": ", 1)[1].split(", ")]

    def close_targets(self, d):
        """each approved tree on the day's OFFICIAL close (the shadow runner's own evaluation)"""
        out = {}
        for e, cfg in sr.load_manifest().items():
            tree = sr.load_tree(cfg["eras"][-1])
            prices = {t: self.yh.live(t, asof=d)[0] for t in sr.tree_tickers(tree)}
            out[e] = sr.run_engine(prices, tree, d)[1]
        return out

    # ---- edits of FMP's rows
    def without_volume_bars(self, d):
        """what the brain read before: FMP's bars without volume never seen (fetch_minutes(traded=True) dropped them)"""
        self.rows[d] = {t: [r for r in rows if isinstance(r[2], (int, float)) and r[2] > 0] for t, rows in self.rows[d].items()}

    def cut(self, d, after, keep=("SPY",)):
        """FMP stopped publishing every ticker but `keep` after the bar starting `after`"""
        self.rows[d] = {t: (rows if t in keep else [r for r in rows if r[0] <= after]) for t, rows in self.rows[d].items()}

    def mute(self, d, after, tickers=None):
        """the bars after `after` keep coming, without volume (quotes only): every trade after it gone"""
        for t, rows in self.rows[d].items():
            if tickers is None or t in tickers:
                self.rows[d][t] = [[hm, c, 0 if hm > after else v] for hm, c, v in rows]

    def freeze(self, d, after, tickers=None):
        """a FROZEN feed: the bars after `after` keep coming without volume, at the ticker's last traded close up
        to `after` (a stuck cache replaying the last print)"""
        for t, rows in self.rows[d].items():
            if tickers is None or t in tickers:
                last, new = None, []
                for hm, c, v in rows:
                    if hm <= after:
                        last = c if v else last
                        new.append([hm, c, v])
                    else:
                        new.append([hm, c if last is None else last, 0])
                self.rows[d][t] = new

    def spy_quiet(self, d, after, close):
        """SPY's trades after the bar starting `after` gone (FMP's bars keep coming, without volume), and each of its
        bars without volume up to the instant closing at close(i, n, trade, real): i its place among them (0 the
        first), n how many there are, trade the close of SPY's last trade, real FMP's own close for that bar"""
        rows = self.rows[d]["SPY"]
        trade = [c for hm, c, v in rows if v and hm <= after][-1]
        quiet = [k for k, (hm, c, v) in enumerate(rows) if after < hm < "12:54"]
        new = [[hm, c, v if hm <= after else 0] for hm, c, v in rows]
        for i, k in enumerate(quiet):
            new[k][1] = close(i, len(quiet), trade, rows[k][1])
        self.rows[d]["SPY"] = new
        return trade

    def freeze_tail(self, d, tickers):
        """each of `tickers` frozen from its own last trade before the instant: every later bar up to the instant
        (they carry no volume already) at that trade's close; the trade, its time and its price unchanged"""
        for t in tickers:
            rows = self.rows[d][t]
            k = max(i for i, (hm, c, v) in enumerate(rows) if v and hm < "12:54")
            self.rows[d][t] = rows[:k + 1] + [[hm, rows[k][1] if hm < "12:54" else c, v] for hm, c, v in rows[k + 1:]]

    def universe(self, d):
        """the trees' tickers on d and SPY: the breadth's 'of' (preclose.preview's 'tick')"""
        out = {"SPY"}
        for cfg in sr.load_manifest().values():
            out |= sr.tree_tickers(sr.load_tree(sr.era_for(cfg, d)))
        return out

    def really_traded(self, d, at="12:54", within=2):
        """the fixture's tickers with a bar WITH volume ending within `within` minutes of `at` (the floor's real trades)"""
        lo = sr._hm(sr._min(at) - within - 1)
        return {t for t, rows in self.rows[d].items() if any(v and lo <= hm < at for hm, c, v in rows)}

    def book_at(self, d, at="12:54"):
        """how many of the trees' tickers other than SPY have a bar WITH volume ending AT `at` in the rows as edited
        (what mirror_brain.book_trades_at counts: SPY's recent-trade exemption needs one)"""
        start = sr._hm(sr._min(at) - 1)
        return sum(1 for t in self.universe(d) - {"SPY"} if any(v and hm == start for hm, c, v in self.rows[d].get(t, [])))

    def full_day_answer(self, d, waits=(30, 130, 200)):
        """the pinned path's answer with the half-day rule switched off (mirror_brain.half_day False, the 13:00 clock
        kept): what the full-day rule says of the same bars at the same instant"""
        with unittest.mock.patch.object(mb, "half_day", lambda day: False):
            return self.pinned(d, waits)


class H1Settles(HalfDay):
    def test_h1_the_three_2025_half_days_settle_with_the_close_decisions(self):
        for d in HALF:
            with self.subTest(d):
                p, err = self.pinned(d)
                self.assertIsNone(err)
                self.assertEqual((p["session"], p["close_et"], p["asof_et"]), (d, "13:00", "12:54:00"))
                self.assertTrue(p["decision_bar"]["complete"])
                self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                self.assertGreaterEqual(p["quotes"]["breadth"]["share"], mb.BREADTH_MIN)
                self.assertEqual(targets(p), self.close_targets(d))       # the decision the tree takes on the close
        p, _ = self.pinned("2025-11-28")
        self.assertEqual(p["decision_bar"], {"end_utc": "2025-11-28T17:54:00Z", "spy_utc": "2025-11-28T17:46:00Z",
                                             "complete": True})              # SPY at its own last trade, named
        self.assertEqual(p["prices"]["SPY"], 682.02)
        said = " ".join(p["problems"])
        self.assertIn("FMP's SPY bar ending 12:54:00 ET has no volume", said)
        self.assertIn("11 ticker(s) counted as trading on a bar FMP published without volume", said)
        self.assertEqual(targets(p), {"HG": {"TNA": 1.0}, "KMLM": {"PULS": 0.12, "TLT": 0.75, "VXZ": 0.13},
                                      "SLEEVE": {"BOXX": 1.0}, "HARV": {"PULS": 0.48, "VXZ": 0.52}})

    def test_h1_twin_without_the_bars_without_volume_two_of_three_refuse_for_good(self):
        self.without_volume_bars("2025-07-03")
        p, err = self.pinned("2025-07-03", waits=(30, 130, 200))
        self.assertIsNone(p)
        self.assertEqual(err.error, "decision not settled yet")
        self.assertIn("the feed looks dead: 37 of 48 tickers traded", err.detail)
        self.without_volume_bars("2025-11-28")
        p, err = self.pinned("2025-11-28", waits=(30, 130, 200))
        self.assertIsNone(p)
        self.assertEqual((err.error, err.detail), ("decision bar not published yet", "SPY's last traded bar ends 12:46:00 ET"))
        self.without_volume_bars("2025-12-24")
        p, _ = self.pinned("2025-12-24")
        self.assertEqual(p["quotes"]["breadth"]["recent"], 39)                 # it passed, by one ticker


class H2FullDays(HalfDay):
    def test_h2_the_same_bars_on_a_full_day_calendar_still_refuse(self):
        with unittest.mock.patch.dict(sr.HALF_DAYS, {}, clear=False):
            del sr.HALF_DAYS["2025-07-03"]
            p, err = self.pinned("2025-07-03", waits=(30, 130))
        self.assertIsNone(p)
        self.assertIn("the feed looks dead: 37 of 48 tickers traded", err.detail)

    def test_h2_a_regular_session_is_byte_identical_with_and_without_the_bars_without_volume(self):
        p1, _ = self.pinned(REGULAR)
        self.rows = copy.deepcopy(self.fx["minutes"])
        self.without_volume_bars(REGULAR)
        p2, _ = self.pinned(REGULAR)
        self.assertEqual(statuses(p1), dict.fromkeys(ENGINES, "ok"))
        self.assertEqual(json.dumps(p1, sort_keys=True), json.dumps(p2, sort_keys=True))
        self.assertFalse(any("half-day" in x for x in p1["problems"]))
        self.assertEqual(p1["decision_bar"]["spy_utc"], p1["decision_bar"]["end_utc"])     # a full day: SPY AT the instant
        self.assertEqual(sorted(p1["quotes"]["breadth"]), ["min_share", "of", "recent", "share", "within_s"])
        # ... and not for lack of material: called a half-day, the same bars count five more tickers, apart
        self.rows = copy.deepcopy(self.fx["minutes"])
        with unittest.mock.patch.dict(sr.HALF_DAYS, {REGULAR: "13:00"}):
            p3, _ = self.pinned(REGULAR)
        b1, b3 = p1["quotes"]["breadth"], p3["quotes"]["breadth"]
        self.assertEqual((b1["recent"], b3["recent"], b3["leaned"], b3["counted"]), (41, 41, 5, 46))


class H3StillRefuses(HalfDay):
    def test_h3_a_feed_that_stopped_is_refused_on_a_half_day(self):
        self.cut("2025-07-03", "12:40")                                        # nothing at all after 12:41 but SPY
        p, err = self.pinned("2025-07-03", waits=(30, 130, 200))
        self.assertIsNone(p)
        self.assertEqual(err.error, "decision not settled yet")
        self.assertIn("the feed looks dead", err.detail)

    def test_h3_quotes_over_stale_trades_are_refused(self):
        self.mute("2025-11-28", "12:37", tickers=set(self.rows["2025-11-28"]) - {"SPY"})   # every trade after 12:38 gone
        p, err = self.pinned("2025-11-28", waits=(30, 130, 200))
        self.assertIsNone(p)
        # nothing really traded in the 2 minutes (SPY's own last trade is 12:45): below the floor the half-day rule is
        # off, and the answer is the full-day one, word for word
        self.assertEqual((err.error, err.detail), ("decision bar not published yet", "SPY's last traded bar ends 12:46:00 ET"))
        self.rows = copy.deepcopy(self.fx["minutes"])
        self.mute("2025-11-28", "12:37")                                       # ... SPY's too: its last trade 16 min old
        p, err = self.pinned("2025-11-28", waits=(30, 130, 200))
        self.assertIsNone(p)
        self.assertEqual((err.error, err.detail), ("decision bar not published yet", "SPY's last traded bar ends 12:38:00 ET"))

    def test_h3_the_minute_must_be_published(self):
        rows = self.rows["2025-11-28"]["SPY"]
        rows[:] = [r for r in rows if r[0] < "12:53"]                          # FMP has not published SPY's 12:53 bar yet
        p, err = self.pinned("2025-11-28")
        self.assertIsNone(p)
        self.assertEqual((err.error, err.detail), ("decision bar not published yet", "SPY's last traded bar ends 12:46:00 ET"))
        self.rows["2025-11-28"]["SPY"] = copy.deepcopy(self.fx["minutes"]["2025-11-28"]["SPY"])
        p, err = self.pinned("2025-11-28")                                     # published (without volume): in
        self.assertIsNone(err)
        self.assertTrue(p["decision_bar"]["complete"])

    def test_h3_a_recent_spy_trade_whose_bar_at_the_instant_is_not_published_is_not_taken(self):
        """SPY's trade 60 or 120 s old (07-03 and 12-24: its rows after the bar stamped 12:52 or 12:51 not published yet,
        so no SPY bar ends at 12:54 at all) with an EARLIER SPY bar without volume that day (10:00): SPY has evidence,
        but its last bar without volume ends hours before the instant. The pinned path answers 503 'decision bar not
        published yet' with the full-day words, and the `--at` path and the paper book do not take the decision bar,
        the book trading at the instant as on the real day. For a trade that recent only Bars.load's ev[0] == T and
        build's sq[0] == now tell 'published without volume' from 'not published yet' (the round-6 review's mutants n16
        and n17, the exemption granted without SPY's bar at the instant, survived every committed gate; the case above,
        SPY's trade 8 minutes old, never reaches it). A pin: 952177fa passes it too"""
        for d in ("2025-07-03", "2025-12-24"):
            for last in ("12:52", "12:51"):
                with self.subTest(d=d, last=last):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    rows = self.rows[d]["SPY"]
                    rows[:] = [["10:00", rows[0][1], 0]] + [r for r in rows if not last < r[0] < "12:54"]
                    self.assertGreater(self.book_at(d), 0)                     # the book trades at 12:54
                    end = sr._hm(sr._min(last) + 1)                            # SPY's trade: the bar ending `end`
                    p, err = self.pinned(d, waits=(30, 130))
                    self.assertIsNone(p, p and p["decision_bar"])
                    self.assertEqual((err.error, err.detail), ("decision bar not published yet",
                                                               f"SPY's last traded bar ends {end}:00 ET"))
                    for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                        self.assertEqual(q["decision_bar"], {"end_utc": mb._iso(self.instant(d)), "complete": False,
                                                             "spy_utc": mb._iso(mb.parse_at(f"{d} {end}"))}, path)
                        self.assertEqual(set(statuses(q).values()), {"unavailable"}, path)

    def test_h3_the_fifteen_minute_boundary(self):
        d = "2025-07-03"
        # UDOW, an HG decision ticker: its last trade is the bar ending 12:46, and bars without volume follow
        self.assertEqual([r[0] for r in self.rows[d]["UDOW"] if r[0] >= "12:45" and r[2]], ["12:45"])
        p, _ = self.pinned(d)
        self.assertIn("UDOW 12:46", " ".join(p["problems"]))
        n = p["quotes"]["breadth"]["counted"]
        for last, counted in (("12:38", True), ("12:37", False)):              # its last trade 15 min / 16 min old
            with self.subTest(last=last):
                self.rows = copy.deepcopy(self.fx["minutes"])
                for r in self.rows[d]["UDOW"]:
                    if r[0] >= "12:20":
                        r[2] = 9184 if r[0] == last else 0
                p, err = self.pinned(d, waits=(30, 130))
                self.assertIsNone(err)
                said = " ".join(p["problems"])
                self.assertEqual(p["quotes"]["breadth"]["counted"], n if counted else n - 1)
                self.assertEqual(f"UDOW {sr._hm(sr._min(last) + 1)}" in said, counted)
                # the price follows the same 15 minutes (the preview's freshness): older is an estimate from DIA,
                # and HG, which decides on UDOW, sits the session out
                self.assertEqual(p["engines"]["HG"]["status"], "ok" if counted else "unavailable")
                self.assertEqual("UDOW" in p["price_notes"], not counted)


class H4OneBrain(HalfDay):
    def test_h4_the_paper_book_and_the_at_path_decide_as_the_live_path(self):
        d = "2025-11-28"
        live, _ = self.pinned(d)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        T = self.instant(d)
        for cache in (None, tmp, tmp):                                         # the third reads the disk cache back
            with self.subTest(cache=cache):
                n = len(self.calls)
                mn = md.Minutes(key="k", cache_dir=cache, rate=1e9, sleep=lambda s: None, now=lambda: T + 86400 * SEC)
                with unittest.mock.patch.object(mb, "_utcnow", lambda: T + 30 * SEC):
                    p = md.brain_payload(d, "12:54", self.yh, mn)
                self.assertTrue(p["decision_bar"]["complete"])
                self.assertEqual((targets(p), p["prices"]), (targets(live), live["prices"]))
        self.assertEqual(len(self.calls), n)                                   # ... from the disk: no FMP call
        with open(os.path.join(tmp, "fmp", d, "SPY.json")) as f:
            rec = json.load(f)
        self.assertEqual(rec["quiet"]["12:53"],                                # the bar without volume, WITH its close
                         next(c for hm, c, v in self.fx["minutes"][d]["SPY"] if hm == "12:53"))
        with open(os.path.join(tmp, "fmp", d, "SPY.json"), "w") as f:          # a cache in the earlier form: bar starts,
            json.dump(dict(rec, quiet=sorted(rec["quiet"])), f)                 # no closes -> no evidence of movement
        mn = md.Minutes(key="k", cache_dir=tmp, rate=1e9, sleep=lambda s: None, now=lambda: T + 86400 * SEC)
        with unittest.mock.patch.object(mb, "_utcnow", lambda: T + 30 * SEC):
            self.assertFalse(md.brain_payload(d, "12:54", self.yh, mn)["decision_bar"]["complete"])
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "k"}):      # the `--at` path reads FMP itself
            p = mb.build(T, fetch=self.history(d), pinned=True, wall=lambda: T + 30 * SEC, budget=600)
        self.assertEqual((targets(p), p["prices"], p["decision_bar"]), (targets(live), live["prices"], live["decision_bar"]))
        # the twin: a paper book that never kept the bars without volume (what it read before) refuses the day
        mn = md.Minutes(key="k", rate=1e9, sleep=lambda s: None,
                        fetch=lambda t, dd, k: {h: v for h, v in sr.fetch_minutes(t, dd, k, traded=True).items()})
        with unittest.mock.patch.object(mb, "_utcnow", lambda: T + 30 * SEC):
            p = md.brain_payload(d, "12:54", self.yh, mn)
        self.assertFalse(p["decision_bar"]["complete"])
        self.assertEqual(set(statuses(p).values()), {"unavailable"})

    def test_h4_fetch_minutes_quiet_lists_the_bars_without_volume_and_nothing_else_changes(self):
        d = "2025-11-28"
        plain = sr.fetch_minutes("SPY", d, "k", tries=1, traded=True)
        quiet = sr.fetch_minutes("SPY", d, "k", tries=1, traded=True, quiet=True)
        rows = self.fx["minutes"][d]["SPY"]
        self.assertEqual(quiet.pop("_quiet"), {hm: c for hm, c, v in rows if not v})   # each bar's close rides along
        self.assertEqual(quiet, plain)
        self.assertEqual(max(plain), "12:45")                                  # SPY's last bar WITH volume
        self.assertNotIn("_quiet", sr.fetch_minutes("SPY", d, "k", tries=1, traded=False, quiet=True))
        self.assertEqual(sr.fetch_minutes("SPY", d, "k", tries=1), sr.fetch_minutes("SPY", d, "k", tries=1, quiet=True))
        self.assertEqual(pc.minute_quotes({"SPY"}, self.instant(d), "k",
                                          fetch=lambda t, dd, k: dict(quiet, _quiet={"12:53": 999.0}))[0],
                         pc.minute_quotes({"SPY"}, self.instant(d), "k", fetch=lambda t, dd, k: dict(quiet))[0])


class H7Frozen(HalfDay):
    """a FROZEN feed (bars without volume at the last trade's price) is refused; bars without volume whose price
    moves are what the rule counts (the reviewers' V5 family, on this fixture)"""

    def test_h7_a_frozen_feed_is_refused_spy_alone_the_whole_book_all_but_spy(self):
        """on every path: the live pinned path refuses it; the `--at` path and the paper book (mirror_dry), which read
        no Bars (build() is their only guard), publish nothing tradeable, and a frozen SPY's bar is never taken as
        the decision bar (a reviewer's R2 on this fixture); the breadth's NOT-counted line names SPY's own reason"""
        everyone = set(self.fx["minutes"][HALF[0]])
        for d in HALF:
            for who, tickers in (("SPY alone", {"SPY"}), ("the whole book", None), ("all but SPY", everyone - {"SPY"})):
                for after in ("12:44", "12:38"):                               # the last trade 9 and 15 minutes old
                    with self.subTest(d=d, who=who, after=after):
                        self.rows = copy.deepcopy(self.fx["minutes"])
                        self.freeze(d, after, tickers)
                        p, err = self.pinned(d)
                        self.assertIsNone(p, p and f"settled on a frozen feed: SPY {p['prices']['SPY']} from "
                                                   f"{p['price_times']['SPY']}, breadth {p['quotes']['breadth']}")
                        if who != "all but SPY":                              # SPY frozen: never its decision bar
                            self.assertEqual(err.error, "decision bar not published yet")
                            self.assertIn("none of SPY's bars without volume since that trade moved", err.detail)
                        for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                            if who != "all but SPY":
                                self.assertFalse(q["decision_bar"]["complete"], f"{path}: a frozen SPY bar taken as the "
                                                                                f"decision bar {q['decision_bar']}")
                                # SPY not counted, in SPY's own words (spy_frozen's), not the book's generic ones
                                line = next(x for x in q["problems"] if "NOT counted: " in x)
                                self.assertIn("SPY", self.named(q, "NOT counted: "), path)
                                self.assertIn("NOT counted: a frozen feed (none of SPY's bars without volume since that "
                                              "trade moved off its price", line, path)
                            self.assertEqual(set(statuses(q).values()), {"unavailable"}, f"{path}: tradeable on a frozen "
                                                                                       f"feed: {statuses(q)}")

    def test_h7_spy_is_held_to_more_than_moved_on_every_path(self):
        """SPY's bar is the decision bar: when its last trade is older than 2 minutes, its bars without volume since
        that trade must close at 2 or more different prices, fewer than 3 in a row at one price up to the instant. On
        11-28 (SPY leaning for real: its 8 bars 12:46-12:53 after its 12:45 trade at 682.02) and on 07-03 and 12-24 with
        SPY's trades after 12:44 gone: constant at a price off the trade's (682.361 on 11-28), one tick off, a stuck
        half-cent, moved once and then back at the trade's price, FMP's own closes with the last 3 at the trade's price
        -> refused on the pinned path, the `--at` path and the paper book, saying why, and the breadth's NOT-counted
        line names SPY in the same words. Twins that settle on all three: SPY oscillating between two prices; FMP's own
        closes with only the last 2 at the trade's price; two bars at two prices; two bars a tick off (SPY's trades after
        12:51 gone: its trade 2 minutes old is not tested, round 6)"""
        one = "every one of SPY's bars without volume since that trade closed at one price, not the trade's"
        run = "of SPY's bars without volume, up to the instant, closed at one price"
        cases = (  # (SPY's bars without volume, its trades gone after the bar starting (07-03, 12-24), close,
                   #  why | None: it settles)
            ("a constant price off the trade's", "12:44", lambda i, n, tr, c: round(tr + 0.341, 4), one),
            ("one tick off", "12:44", lambda i, n, tr, c: round(tr + 0.01, 2), one),
            ("a stuck half-cent", "12:44", lambda i, n, tr, c: round(tr + 0.005, 3), one),
            ("moved once, then the trade's price", "12:44", lambda i, n, tr, c: round(tr + 0.341, 4) if i == 0 else tr, run),
            ("FMP's own closes, the last 3 at the trade's price", "12:44", lambda i, n, tr, c: tr if i >= n - 3 else c,
             "the last 3 " + run),
            ("two bars, one tick off", "12:51", lambda i, n, tr, c: round(tr + 0.01, 2), None),  # its trade 120 s old
            ("oscillating between two prices", "12:44", lambda i, n, tr, c: tr if i % 2 else round(tr + 0.01, 2), None),
            ("FMP's own closes, the last 2 at the trade's price", "12:44", lambda i, n, tr, c: tr if i >= n - 2 else c, None),
            ("two bars, two prices off the trade's", "12:51", lambda i, n, tr, c: round(tr + 0.01 * (i + 1), 2), None))
        for d in HALF:
            for name, cut, close, why in cases:
                if d == "2025-11-28" and cut != "12:44":
                    continue                                                   # SPY's own last trade there is 12:45
                with self.subTest(d=d, spy=name):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    trade = self.spy_quiet(d, "12:45" if d == "2025-11-28" else cut, close)
                    if d == "2025-11-28" and name.startswith("a constant"):                         # the reviewer's shape
                        self.assertEqual((trade, {c for hm, c, v in self.rows[d]["SPY"] if "12:45" < hm < "12:54"}),
                                         (682.02, {682.361}))
                    p, err = self.pinned(d)
                    if why is None:
                        self.assertIsNone(err, err and err.detail)
                        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                        self.assertNotEqual(p["decision_bar"]["spy_utc"], p["decision_bar"]["end_utc"])   # SPY leaned
                        for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                            self.assertEqual((targets(q), q["prices"], q["decision_bar"]),
                                             (targets(p), p["prices"], p["decision_bar"]), path)
                        continue
                    self.assertTrue(p is None, p and f"settled with SPY {name}: {p['decision_bar']}")
                    self.assertEqual(err.error, "decision bar not published yet")
                    self.assertIn("(half-day, a frozen feed: ", err.detail)
                    self.assertIn(why, err.detail[:160])                       # the executor keeps 160 characters of it
                    for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                        self.assertFalse(q["decision_bar"]["complete"], f"{path}: SPY {name} taken as the decision bar")
                        self.assertEqual(set(statuses(q).values()), {"unavailable"}, path)
                        said = " ".join(q["problems"])
                        self.assertIn("half-day, a frozen feed: ", said)
                        self.assertIn(why, said)
                        self.assertIn("FMP's SPY bar ending 12:54:00 ET has no volume): not taken as the decision bar", said)
                        # ... and its breadth says the same: SPY is not counted on those bars (unless it really traded),
                        # in the same words (spy_frozen's), never the book's 'none of their bars ... moved'
                        self.assertNotIn("SPY", self.named(q, "counted as trading on a bar FMP published without volume"))
                        if cut == "12:44":
                            self.assertIn("SPY", self.named(q, "with bars without volume near 12:54:00 ET NOT counted"))
                            self.assertGreaterEqual(q["quotes"]["breadth"]["frozen"], 1, path)
                            line = next(x for x in q["problems"] if "NOT counted: " in x)
                            self.assertIn("NOT counted: a frozen feed (", line, path)
                            self.assertIn(why, line, path)
        # the margin on the real day: SPY's 8 bars without volume closed at 8 different prices, the last one unrepeated
        d = "2025-11-28"
        self.rows = copy.deepcopy(self.fx["minutes"])
        T = self.instant(d)
        ev = mb.quiet_evidence(sr.fetch_minutes("SPY", d, "k", tries=1, traded=True, quiet=True), d, sr.et_now(T).tzinfo, T)
        self.assertEqual(ev, (T, True, 8, 1))
        self.assertIsNone(mb.spy_frozen(ev))

    def test_h7_spys_trade_one_or_two_minutes_old_needs_no_evidence_on_every_path(self):
        """FMP's volume gone from SPY's last 1 or 2 bars only (07-03 and 12-24, where SPY really trades to the instant:
        its trades after the bar starting 12:52 or 12:51 gone), its trade 60 or 120 s old - what the full-day rule and
        the floor count as REALLY trading, the 120 s included - and the rest of the book as it was (31 and 34 of the
        trees' other tickers trading in the bar ending 12:54, which the exemption needs since round 7): whatever those
        bars close at (one close or two equal ones, frozen at the trade's price, a tick off) the day settles on the
        pinned path, the `--at` path and the paper book with one decision, SPY priced at that trade and counted as a
        real trade (33850e01 refused every one of them: one close is one price). Twins (pins, refused before and
        after): the same shapes with SPY's trade 3 minutes old"""
        shapes = (("equal closes (FMP's own close of the first)", None),
                  ("frozen at the trade's price", lambda i, n, tr, c: tr),
                  ("one tick off", lambda i, n, tr, c: round(tr + 0.01, 2)))
        why = {"equal closes (FMP's own close of the first)": "every one of SPY's bars without volume since that trade "
                                                              "closed at one price, not the trade's",
               "frozen at the trade's price": "none of SPY's bars without volume since that trade moved off its price",
               "one tick off": "every one of SPY's bars without volume since that trade closed at one price, not the "
                               "trade's"}
        for d in ("2025-07-03", "2025-12-24"):
            T = self.instant(d)
            for k, cut in ((1, "12:52"), (2, "12:51"), (3, "12:50")):
                first = sr._hm(sr._min(cut) + 1)                               # the first bar without volume
                for name, close in shapes:
                    with self.subTest(d=d, k=k, spy=name):
                        self.rows = copy.deepcopy(self.fx["minutes"])
                        c0 = next(c for hm, c, v in self.rows[d]["SPY"] if hm == first)
                        trade = self.spy_quiet(d, cut, close or (lambda i, n, tr, c: c0))
                        quiet = [c for hm, c, v in self.rows[d]["SPY"] if cut < hm < "12:54"]
                        self.assertEqual((len(quiet), len(set(quiet))), (k, 1))          # k bars, one price
                        p, err = self.pinned(d, waits=(30, 60))
                        if k == 3:                                             # older than 120 s: SPY's rule applies
                            self.assertIsNone(p, p and p["decision_bar"])
                            self.assertEqual(err.error, "decision bar not published yet")
                            self.assertIn(f"{FROZEN}{why[name]}", err.detail[:160])
                            for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                                self.assertFalse(q["decision_bar"]["complete"], path)
                                self.assertEqual(set(statuses(q).values()), {"unavailable"}, path)
                                self.assertIn(f"{FROZEN}{why[name]}", " ".join(q["problems"]), path)
                            continue
                        self.assertIsNone(err, err and err.detail)
                        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                        self.assertEqual(p["decision_bar"], {"end_utc": mb._iso(T), "complete": True,
                                                             "spy_utc": mb._iso(T - datetime.timedelta(minutes=k))})
                        self.assertEqual(p["prices"]["SPY"], trade)                   # priced at that trade
                        said = " ".join(p["problems"])
                        self.assertIn(f"SPY is priced at its own last trade (bar ending {sr._hm(sr._min('12:54') - k)}:00 ET; "
                                      f"within the 2 minutes the full-day rule counts a trade as recent: its bars without "
                                      f"volume since are not tested)", said)
                        self.assertNotIn(FROZEN, said)
                        self.assertNotIn("SPY", self.named(p, "counted as trading on a bar FMP published without volume"))
                        self.assertNotIn("SPY", self.named(p, "NOT counted: "))          # a real trade, counted as one
                        for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                            self.assertEqual((targets(q), q["prices"], q["decision_bar"], statuses(q)),
                                             (targets(p), p["prices"], p["decision_bar"], statuses(p)), path)

    def test_h7_the_whole_book_frozen_in_the_last_two_minutes_is_refused_on_every_path(self):
        """round 7 (the round-6 review's first MINOR): the whole book, SPY included, FROZEN after the bar stamped 12:52 or
        12:51 (every ticker's bars since its last trade published without volume at that trade's price), or MUTED after
        12:52 (FMP's own closes, one SPY bar), on 07-03 and 12-24 where SPY trades to the instant: SPY's trade is 60 or
        120 s old, but no other ticker of the trees traded in the bar ending 12:54, so SPY's exemption does not apply
        and its tests do (the round-5 rule): refused on the pinned path, the `--at` path and the paper book, each saying
        why (952177fa traded all six on every path; 33850e01 refused them). The book is the trees' tickers, the set the
        floor counts: frozen after 12:52 with only the tickers no current tree reads (same-index siblings, an older
        era's holdings) still trading at 12:54, it is refused the same (952177fa traded it)"""
        still = "none of SPY's bars without volume since that trade moved off its price"
        for d in ("2025-07-03", "2025-12-24"):
            outside = set(self.rows[d]) - self.universe(d)                     # siblings and older eras' tickers
            for how, after in (("frozen", "12:52"), ("frozen", "12:51"), ("muted", "12:52"), ("frozen but outside", "12:52")):
                with self.subTest(d=d, book=how, after=after):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    if how == "frozen but outside":
                        self.freeze(d, after, set(self.rows[d]) - outside)
                        self.assertTrue(any(v and hm == "12:53" for t in outside for hm, c, v in self.rows[d][t]))
                    else:
                        (self.freeze if how == "frozen" else self.mute)(d, after)
                    self.assertEqual(self.book_at(d), 0)                       # no trade of the book at 12:54 ...
                    self.assertTrue(len(self.really_traded(d) & self.universe(d)) >= len(self.universe(d)) / 2)  # floor
                    spy = sr._hm(sr._min(after) + 1)                           # SPY's last trade: the bar ending `spy`
                    p, err = self.pinned(d, waits=(30, 130))
                    self.assertIsNone(p, p and f"settled on a book frozen from {after}: {p['decision_bar']}")
                    self.assertEqual(err.error, "decision bar not published yet")
                    self.assertTrue(err.detail.startswith(f"SPY's last traded bar ends {spy}:00 ET ({FROZEN}"), err.detail)
                    self.assertTrue(how == "muted" or err.detail.startswith(
                        f"SPY's last traded bar ends {spy}:00 ET ({FROZEN}{still}"), err.detail)
                    self.assertIn("FMP's SPY bar ending at the instant has no volume, nor did any other ticker of the trees "
                                  "trade in it)", err.detail)
                    for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                        self.assertFalse(q["decision_bar"]["complete"], f"{path}: {q['decision_bar']}")
                        self.assertEqual(set(statuses(q).values()), {"unavailable"}, path)
                        line = next((x for x in q["problems"] if x.startswith(FROZEN)), None)
                        self.assertIsNotNone(line, (path, q["problems"]))
                        self.assertIn(f"(its last trade: the bar ending {spy}:00 ET, within the 2 minutes, but no other "
                                      f"ticker of the trees traded in the bar ending 12:54:00 ET; FMP's SPY bar ending "
                                      f"12:54:00 ET has no volume): not taken as the decision bar", line, path)

    def test_h7_twins_the_whole_book_muted_from_12_52_and_11_28_frozen_late_settle(self):
        """pins (pass before and after round 7), no other ticker of the trees trading in the bar ending 12:54 in any:
        (a) the whole book MUTED after the bar stamped 12:51 (FMP's own, moving closes) on 07-03 and 12-24: SPY's two
        closes since its trade 120 s old pass its tests (they moved, at two prices), so the day settles on every path
        with one decision, as under the round-5 rule; (b) 2025-11-28 FROZEN across the whole book after the bar stamped
        12:51 or 12:52: SPY's own last trade is 8 minutes old (no exemption involved) and its bars without volume moved
        before the freeze (a run of 1 or 2 at the instant), so SPY's rule takes it, the book priced at its real trades
        at most 2 minutes old: recorded in spy_frozen's docstring and IBKR_MIRROR.md, traded since round 5"""
        cases = [(d, "muted", "12:51") for d in ("2025-07-03", "2025-12-24")] + \
                [("2025-11-28", "frozen", after) for after in ("12:51", "12:52")]
        for d, how, after in cases:
            with self.subTest(d=d, book=how, after=after):
                self.rows = copy.deepcopy(self.fx["minutes"])
                (self.freeze if how == "frozen" else self.mute)(d, after)
                self.assertEqual(self.book_at(d), 0)
                p, err = self.pinned(d, waits=(30, 60, 130))       # frozen after 12:52 every last trade ends 12:53: the
                self.assertIsNone(err, err and err.detail)         # bar reads as still publishing until SETTLE_S
                self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                self.assertNotEqual(p["decision_bar"]["spy_utc"], p["decision_bar"]["end_utc"])   # SPY leaned
                for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                    self.assertEqual((targets(q), q["prices"], q["decision_bar"], statuses(q)),
                                     (targets(p), p["prices"], p["decision_bar"], statuses(p)), path)

    def test_h7_the_taken_line_says_whether_the_book_traded_at_the_instant(self):
        """which rule took SPY's recent trade is in `problems`: with the book trading at 12:54 (07-03, SPY's volume gone
        from its last bar only, that bar at the trade's price) SPY's bars are not tested and the line gives how many of
        the trees' other tickers traded in the bar ending 12:54 (31 in FMP's archive of that minute); with the whole
        book muted after the bar stamped 12:51 (no trade at 12:54) SPY's two moving closes were tested, in round 5's
        words (952177fa said 'not tested' for both)"""
        d = "2025-07-03"
        self.spy_quiet(d, "12:52", lambda i, n, tr, c: tr)
        self.assertEqual(self.book_at(d), 31)
        p, err = self.pinned(d)
        self.assertIsNone(err, err and err.detail)
        self.assertIn("SPY is priced at its own last trade (bar ending 12:53:00 ET; within the 2 minutes the full-day rule "
                      "counts a trade as recent: its bars without volume since are not tested); 31 of the trees' other "
                      "tickers traded in the bar ending 12:54:00 ET (the exemption needs one)", " ".join(p["problems"]))
        self.rows = copy.deepcopy(self.fx["minutes"])
        self.mute(d, "12:51")
        p, err = self.pinned(d)
        self.assertIsNone(err, err and err.detail)
        said = " ".join(p["problems"])
        self.assertIn("SPY is priced at its own last trade (bar ending 12:52:00 ET; a bar without volume since moved off "
                      "that price)", said)
        self.assertNotIn("not tested", said)

    def test_h7_the_book_is_not_held_to_spys_rule(self):
        """twin (passes before and after the SPY rule): the tickers the rule leans on for real, SPY aside, each with its
        bars without volume since its last trade stuck at ONE price a tick off that trade's -> still counted, the day
        settles: the book's own guard is the floor and the 15-minute age (on 18 real days 18.4% of the ticker-minutes
        the rule counts have a single close)"""
        for d in HALF:
            with self.subTest(d=d):
                self.rows = copy.deepcopy(self.fx["minutes"])
                live, _ = self.pinned(d)
                for t in set(LEANED[d]) - {"SPY"}:
                    rows = self.rows[d][t]
                    k = max(i for i, (hm, c, v) in enumerate(rows) if v and hm < "12:54")
                    self.rows[d][t] = rows[:k + 1] + [[hm, round(rows[k][1] + 0.01, 4) if hm < "12:54" else c, v]
                                                      for hm, c, v in rows[k + 1:]]
                p, err = self.pinned(d)
                self.assertIsNone(err, err and err.detail)
                self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                b, b0 = p["quotes"]["breadth"], live["quotes"]["breadth"]
                self.assertEqual((b["leaned"], b["frozen"], b["counted"]), (b0["leaned"], 0, b0["counted"]))

    def test_h7_the_real_half_days_settle_on_every_path(self):
        """twin of the two above (passes before and after them): the three real half-days, SPY leaning on 11-28,
        settle on the pinned path, the `--at` path and the paper book with the same decision, every engine ok"""
        for d in HALF:
            with self.subTest(d=d):
                p, err = self.pinned(d)
                self.assertIsNone(err, err and err.detail)
                self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                self.assertTrue(p["decision_bar"]["complete"])
                for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                    self.assertEqual((targets(q), q["prices"], q["decision_bar"], statuses(q)),
                                     (targets(p), p["prices"], p["decision_bar"], statuses(p)), path)

    def test_h7_the_tickers_the_rule_leans_on_frozen_are_not_counted(self):
        """the real trades untouched (the floor holds), SPY's own bars untouched: only the tickers the rule counts on
        the real day are frozen from their own last trade (same trade, same price)"""
        for d, gives in (("2025-07-03", "refused"), ("2025-11-28", "refused"), ("2025-12-24", "settles")):
            with self.subTest(d=d):
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.freeze_tail(d, set(LEANED[d]) - {"SPY"})
                p, err = self.pinned(d, waits=(30, 130, 200))
                if gives == "refused":
                    self.assertIsNone(p)
                    self.assertIn("the feed looks dead", err.detail)
                    continue
                b = p["quotes"]["breadth"]                                     # 12-24 passes on its real trades (39 of 48)
                self.assertEqual((b["recent"], b["leaned"], b["frozen"], b["counted"]), (39, 0, 6, 39))
                self.assertIn("6 ticker(s) with bars without volume near 12:54:00 ET NOT counted", " ".join(p["problems"]))
                self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.assertEqual(targets(p), targets(self.pinned(d)[0]))        # the same trades, the same prices

    def test_h7_twin_bars_without_volume_that_move_settle_and_the_same_bars_frozen_do_not(self):
        """half the trees' tickers (the floor) keep trading; every other one, SPY included, goes without volume from
        12:44 with FMP's real, moving closes -> settles, every engine ok; the same bars frozen -> refused"""
        for d in HALF:
            tick = self.universe(d)
            keep = sorted(self.really_traded(d) & (tick - {"SPY"}))[:len(tick) // 2]
            with self.subTest(d=d, prices="moving"):
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.mute(d, "12:44", set(self.rows[d]) - set(keep))
                p, err = self.pinned(d, waits=(30,))
                self.assertIsNone(err, err and err.detail)
                self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
                self.assertEqual(p["quotes"]["breadth"]["recent"], len(tick) // 2)
                self.assertGreaterEqual(p["quotes"]["breadth"]["share"], mb.BREADTH_MIN)
                self.assertEqual(p["decision_bar"]["spy_utc"], mb._iso(mb.parse_at(f"{d} 12:45")))   # SPY at its 12:44 trade
            with self.subTest(d=d, prices="frozen"):
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.freeze(d, "12:44", set(self.rows[d]) - set(keep))
                p, err = self.pinned(d)
                self.assertIsNone(p)

    def test_h7_any_bar_moved_not_the_bar_at_the_instant(self):
        """11-28: SPY's last trade is 12:45 (682.02); FMP's SPY bar at the instant closing at exactly that price does
        not make a live feed frozen: its earlier bars without volume moved"""
        d = "2025-11-28"
        live, _ = self.pinned(d)
        for r in self.rows[d]["SPY"]:
            if r[0] == "12:53":
                r[1] = 682.02
        p, err = self.pinned(d, waits=(30,))
        self.assertIsNone(err, err and err.detail)
        self.assertEqual((p["decision_bar"], targets(p)), (live["decision_bar"], targets(live)))


class H7Units(unittest.TestCase):
    """SPY's rule and its evidence as units, on hand-built FMP answers (no fixture): the 2-minute boundary of the trade
    that needs no evidence (round 6), QUIET_MOVE_TOL (closes within it of each other are one price), and the shapes
    the rule lets through by design (recorded in spy_frozen's docstring)"""
    D = "2026-11-27"                                    # a half-day of the static calendar (13:00)

    def setUp(self):
        self.T = mb.parse_at(f"{self.D} 12:54")
        self.tz = sr.et_now(self.T).tzinfo

    def ev(self, trade_hm, trade_px, closes, start):
        """quiet_evidence at 12:54 of an answer: SPY's trade in the bar starting trade_hm, then a bar without volume a
        minute from `start` for each close"""
        m0 = sr._min(start)
        bars = {trade_hm: trade_px, "_quiet": {sr._hm(m0 + i): c for i, c in enumerate(closes)}}
        return mb.quiet_evidence(bars, self.D, self.tz, self.T)

    def test_h7_units_a_recent_trade_is_not_tested_while_the_book_trades_the_boundary_in_bar_ends(self):
        """spy_frozen(ev, age, book): every frozen-feed shape passes when SPY's last trade ends 60 or 120 s before the
        instant AND at least one of the trees' other tickers traded in the bar ending at the instant (book >= 1, round 7);
        with no such trade (book 0, the default, or no count at all: None, text, a negative number) the tests apply at
        every age, as they do at 180 s, a hair past 120 s, an unknown age, a bool, a negative age or text whatever the
        book; no evidence at all is refused whatever the age and the book. The boundary in bar-END terms (FMP stamps a
        minute bar by its START): 120 s is a trade in the bar ending exactly BREADTH_AGE_S before the instant, the side
        real() and the floor count as REALLY trading; on 2026-11-27 (the instant 12:54:00) the bar stamped 12:51 (ending
        12:52:00) is exempt and the bar stamped 12:50 (ending 12:51:00) is not"""
        one = "every one of SPY's bars without volume since that trade closed at one price, not the trade's"
        still = "none of SPY's bars without volume since that trade moved off its price"
        shapes = {"one bar at the trade's price": (self.ev("12:52", 682.02, [682.02], "12:53"), still),
                  "one bar off the trade's price": (self.ev("12:52", 682.02, [682.03], "12:53"), one),
                  "two equal closes": (self.ev("12:51", 682.02, [682.03, 682.03], "12:52"), one),
                  "two at the trade's price": (self.ev("12:51", 682.02, [682.02, 682.02], "12:52"), still)}
        self.assertEqual(mb.BREADTH_AGE_S, 120)
        for name, (ev, why) in shapes.items():
            with self.subTest(name):
                self.assertEqual(ev[0], self.T)
                for age in (60, 60.0, 120, 120.0, 0):
                    for book in (1, 31):
                        self.assertIsNone(mb.spy_frozen(ev, age, book), (age, book))
                        self.assertIsNone(mb.spy_frozen(ev, age=age, book=book), (age, book))
                    for book in (0, None, -1, "31"):                           # no trade of the book at the instant
                        self.assertEqual(mb.spy_frozen(ev, age, book), why, (age, book))
                    self.assertEqual(mb.spy_frozen(ev, age), why, age)        # the default: fail-closed
                for age in (180, 180.0, 120.001, None, True, -60, "60"):
                    self.assertEqual(mb.spy_frozen(ev, age, 31), why, age)
                self.assertEqual(mb.spy_frozen(ev), why)
        for bad in (None, (self.T, True), [self.T, True, 1, 1], "x"):
            self.assertEqual(mb.spy_frozen(bad, 60, 31), "no evidence that SPY's bars without volume move")
        self.assertEqual((mb.spy_trade_recent(120), mb.spy_trade_recent(120.5), mb.spy_trade_recent(None)), (True, False, False))
        # FMP's stamps on 2026-11-27: SPY's last trade in the bar stamped hh:mm, a bar without volume at its price after
        for stamp, age, exempt in (("12:52", 60, True), ("12:51", 120, True), ("12:50", 180, False)):
            with self.subTest(stamp=stamp):
                self.assertEqual((self.T - pc.bar_end(self.D, stamp, self.tz)).total_seconds(), age)
                ev = self.ev(stamp, 682.02, [682.02] * (sr._min("12:53") - sr._min(stamp)), sr._hm(sr._min(stamp) + 1))
                self.assertEqual(ev[0], self.T)
                self.assertEqual(mb.spy_frozen(ev, age, 31), None if exempt else still)

    def test_h7_units_book_trades_at_counts_the_trees_other_tickers_trading_at_the_instant(self):
        """book_trades_at (round 7): the tickers other than SPY whose last traded bar ends AT the instant; SPY's own, a bar
        ending a minute earlier and anything that is not a time do not count"""
        minute = datetime.timedelta(minutes=1)
        ends = {"SPY": self.T, "TQQQ": self.T, "TLT": self.T, "UPRO": self.T - minute, "PEJ": None, "BIL": "x"}
        self.assertEqual(mb.book_trades_at(ends, self.T), 2)
        self.assertEqual(mb.book_trades_at(ends, self.T - minute), 1)
        self.assertEqual((mb.book_trades_at({"SPY": self.T}, self.T), mb.book_trades_at({}, self.T)), (0, 0))

    def test_h7_units_closes_within_quiet_move_tol_are_one_price(self):
        """QUIET_MOVE_TOL (1e-9 of the price): closes within it of each other are ONE price for the distinct count and
        for the run at the instant, and a close within it of the trade's has not moved; 1e-8 apart they are two (pins,
        passing before and after: an exact comparison in one() or in the distinct count fails them)"""
        p = 100.0
        hair, apart = 101.0 * (1 + 1e-10), 101.0 * (1 + 1e-8)
        for closes, want in (([101.0, hair, 101.0], (True, 1, 3)), ([101.0, 101.0, hair], (True, 1, 3)),
                             ([hair, 101.0, 101.0], (True, 1, 3)), ([101.0, apart, 101.0], (True, 2, 1)),
                             ([101.0, 101.0, apart], (True, 2, 1))):
            with self.subTest(closes=closes):
                self.assertEqual(self.ev("12:45", p, closes, "12:51"), (self.T,) + want)
        self.assertFalse(self.ev("12:45", p, [p * (1 + 1e-10)] * 3, "12:51")[1])          # within it: not moved
        self.assertTrue(self.ev("12:45", p, [p * (1 + 1e-8)] * 3, "12:51")[1])

    def test_h7_units_the_shapes_let_through_by_design(self):
        """recorded in spy_frozen's docstring and pinned here (pass before and after): with SPY's trade 8 minutes old,
        SPY frozen at that trade's price but for one bar among the last three (a one-tick blip: the run at the instant is
        then at most 2), and two stale prices alternating, read as a live feed; the blip one bar earlier (a run of 3 at
        the instant) does not"""
        tr, n = 682.02, 8

        def frozen_but(j):                              # bar j (0 the first) a tick off
            return [round(tr + 0.01, 2) if i == j else tr for i in range(n)]
        for name, closes in (("blip_last", frozen_but(n - 1)), ("blip_second_last", frozen_but(n - 2)),
                             ("blip_third_last", frozen_but(n - 3)),
                             ("two_stale_alt", [round(tr + (0.11 if i % 2 else 0.12), 2) for i in range(n)])):
            with self.subTest(name):
                ev = self.ev("12:45", tr, closes, "12:46")
                self.assertEqual(ev[0], self.T)
                self.assertIsNone(mb.spy_frozen(ev), (name, ev))
        self.assertEqual(mb.spy_frozen(self.ev("12:45", tr, frozen_but(n - 4), "12:46")),
                         "the last 3 of SPY's bars without volume, up to the instant, closed at one price")


class H8Floor(HalfDay):
    """the floor of REAL trades: the rule applies only while at least HALF_DAY_REAL_MIN of the trees' tickers traded
    within BREADTH_AGE_S; below it the full-day rule decides, word for word"""

    def test_h8_no_real_trade_near_the_instant_is_refused_as_on_a_full_day(self):
        """every trade after 12:40 gone, the bars still coming with FMP's real, moving closes (halfday_b's D1); and
        after 12:44 - the whole book without volume, prices moving: below the floor too"""
        for d in HALF:
            for after in ("12:40", "12:44"):
                with self.subTest(d=d, after=after):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    self.mute(d, after)
                    p, err = self.pinned(d)
                    self.assertIsNone(p, p and f"settled with no trade after {after}: breadth {p['quotes']['breadth']}")
                    _, full = self.full_day_answer(d)
                    self.assertEqual((err.error, err.detail), (full.error, full.detail))

    def test_h8_the_floor_holds_with_spy_trading_and_on_every_path(self):
        """every ticker but SPY without a trade after 12:40 while SPY trades to the instant (07-03, 12-24): refused as on
        a full day, by the build itself (the pinned path's early SPY check has nothing to lean on); and D1's bars through
        the `--at` path and the paper book, which read no Bars: not a tradeable decision"""
        everyone = set(self.fx["minutes"][HALF[0]])
        for d in ("2025-07-03", "2025-12-24"):
            with self.subTest(d=d, path="pinned"):
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.mute(d, "12:40", everyone - {"SPY"})
                p, err = self.pinned(d)
                self.assertIsNone(p, p and f"settled: breadth {p['quotes']['breadth']}")
                _, full = self.full_day_answer(d)
                self.assertEqual((err.error, err.detail), (full.error, full.detail))
                self.assertIn("the feed looks dead: 1 of 48 tickers traded", err.detail)
        d = "2025-11-28"
        self.rows = copy.deepcopy(self.fx["minutes"])
        self.mute(d, "12:40")
        T = self.instant(d)
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "k"}):
            at = mb.build(T, fetch=self.history(d), pinned=True, wall=lambda: T + 30 * SEC, budget=600)
        mn = md.Minutes(key="k", rate=1e9, sleep=lambda s: None, now=lambda: T + 86400 * SEC)
        with unittest.mock.patch.object(mb, "_utcnow", lambda: T + 30 * SEC):
            dry = md.brain_payload(d, "12:54", self.yh, mn)
        for path, p in (("--at", at), ("paper", dry)):
            with self.subTest(d=d, path=path):
                self.assertFalse(p["decision_bar"]["complete"])
                self.assertEqual(set(statuses(p).values()), {"unavailable"})
                self.assertIn("the feed looks dead: 0 of 48 tickers traded", " ".join(p["problems"]))
                self.assertIn("below the 50% the half-day rule needs", " ".join(p["problems"]))

    def test_h8_the_floor_holds_for_spys_trade_one_or_two_minutes_old(self):
        """round 6's exemption is SPY's, never the floor's: SPY's trades after the bar starting 12:52 or 12:51 gone (its
        trade 60 or 120 s old; its bars without volume frozen at that trade's price, or FMP's own closes) while every
        other ticker has no trade after 12:40 (prices moving) -> refused on the pinned path exactly as the full-day rule
        refuses the same bars, and not tradeable on the `--at` path and the paper book: the decision bar not complete,
        below the 50% the half-day rule needs (33850e01 refused these too, the one-bar ones and those frozen at the
        trade's price at SPY's own check, in the frozen-feed words). No other ticker trades at 12:54 here either: the
        floor is weighed first (round 7), so the answer stays the full-day one"""
        d = "2025-07-03"
        everyone = set(self.fx["minutes"][d])
        for k, cut in ((1, "12:52"), (2, "12:51")):
            for shape, close in (("frozen at the trade's price", lambda i, n, tr, c: tr), ("FMP's own closes", None)):
                with self.subTest(k=k, spy=shape):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    self.mute(d, "12:40", everyone - {"SPY"})
                    self.spy_quiet(d, cut, close or (lambda i, n, tr, c: c))
                    p, err = self.pinned(d, waits=(30, 130))
                    self.assertIsNone(p, p and f"settled below the floor: breadth {p['quotes']['breadth']}")
                    _, full = self.full_day_answer(d)
                    self.assertEqual((err.error, err.detail), (full.error, full.detail))
                    self.assertEqual(err.detail, f"SPY's last traded bar ends {sr._hm(sr._min('12:54') - k)}:00 ET")
                    for path, q in (("--at", self.at_path(d)), ("paper", self.paper_path(d))):
                        self.assertFalse(q["decision_bar"]["complete"], path)
                        self.assertEqual(set(statuses(q).values()), {"unavailable"}, path)
                        self.assertIn("below the 50% the half-day rule needs", " ".join(q["problems"]), path)

    def test_h8_a_frozen_tail_is_refused(self):
        """halfday_b's D2: every bar after 12:40 without volume at the last traded close"""
        self.freeze("2025-11-28", "12:40")
        p, err = self.pinned("2025-11-28")
        self.assertIsNone(p)

    def test_h8_the_floor_to_the_ticker(self):
        """exactly half the trees' tickers really trading in the 2 minutes: the rule applies and the day settles; one
        fewer: refused, exactly as the full-day rule refuses the same bars"""
        for d in HALF:
            tick = self.universe(d)
            real = sorted(self.really_traded(d) & (tick - {"SPY"}))
            for n, settles in ((len(tick) // 2, True), (len(tick) // 2 - 1, False)):
                with self.subTest(d=d, real=n):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    self.mute(d, "12:44", set(self.rows[d]) - set(real[:n]))
                    p, err = self.pinned(d)
                    if settles:
                        self.assertIsNone(err, err and err.detail)
                        self.assertEqual((p["quotes"]["breadth"]["recent"], p["quotes"]["breadth"]["real_share"]), (n, 0.5))
                        continue
                    self.assertIsNone(p)
                    _, full = self.full_day_answer(d)
                    self.assertEqual((err.error, err.detail), (full.error, full.detail))
                    self.assertEqual(err.detail, "SPY's last traded bar ends 12:45:00 ET")

    def test_h8_the_bars_without_volume_must_be_near_the_instant(self):
        """V4b: every ticker but SPY without volume after 12:39 and no bar at all after 12:41 -> refused (on both
        rules); and the same done only to the tickers that do not really trade, so the floor holds: still refused,
        their last bar 12 minutes before the instant (the 120 s bound alone)"""
        for d in ("2025-07-03", "2025-11-28"):
            for who in ("all but SPY", "the not really trading"):
                with self.subTest(d=d, who=who):
                    self.rows = copy.deepcopy(self.fx["minutes"])
                    tickers = set(self.rows[d]) - {"SPY"}
                    if who != "all but SPY":
                        tickers -= self.really_traded(d)
                    self.mute(d, "12:39", tickers)
                    self.rows[d] = {t: (rows if t not in tickers else [r for r in rows if r[0] <= "12:41"])
                                    for t, rows in self.rows[d].items()}
                    p, err = self.pinned(d)
                    self.assertIsNone(p, p and f"settled: breadth {p['quotes']['breadth']}")


class H9Breadth(HalfDay):
    def test_h9_real_and_leaned_counts_apart(self):
        """quotes.breadth on a half-day the rule counts on: 'recent' the REAL trades within 120 s, 'leaned' the
        tickers counted on bars without volume (named in `problems`), share = counted / of"""
        for d, (real, leaned) in (("2025-07-03", (37, 9)), ("2025-11-28", (36, 11)), ("2025-12-24", (39, 6))):
            with self.subTest(d=d):
                p, _ = self.pinned(d)
                b = p["quotes"]["breadth"]
                self.assertEqual(b, {"recent": real, "of": 48, "share": round((real + leaned) / 48, 4),
                                     "min_share": mb.BREADTH_MIN, "within_s": mb.BREADTH_AGE_S, "leaned": leaned,
                                     "counted": real + leaned, "frozen": 0, "real_share": round(real / 48, 4),
                                     "real_min_share": 0.5})
                line = next(x for x in p["problems"] if "counted as trading on a bar FMP published without volume" in x)
                self.assertEqual(sorted(x.split()[0] for x in line.split(" really traded in the 2 minutes: ")[1].split(", ")),
                                 LEANED[d])


class _NoSleep:
    """shadow_runner's `time`, its sleep a no-op (fetch_minutes sleeps a second after a failed attempt)"""

    def __getattr__(self, name):
        return getattr(time, name)

    @staticmethod
    def sleep(s):
        return None


class H11FloorHeld(HalfDay):
    """the floor's refusal comes after the whole book was read: it is held REBUILD_EVERY_S like any unsettled answer,
    so a book asking every 3 s (the executor's INTENTS_RETRY_S) does not have the brain read FMP's whole book every
    3 s; and below the floor while FMP has not answered for a tree's ticker, the 503 says that"""

    def ask(self, d, start=25, until=200, every=3, slow=None):
        """Pinned.get as the HTTP handler calls it, from T + start to T + until every `every` s or until it settles;
        slow: (tickers, s) -> FMP's answers for those tickers time out until T + s -> ([(s after T, FMP calls made by
        that ask, the 503 body or None, the hold the ask left in s or None)], the payload or None)"""
        T = self.instant(d)
        clock = {"now": T}
        if slow:
            self.fmp_times_out = lambda t, dd: t in slow[0] and clock["now"] < T + slow[1] * SEC
        hist = mb.History(fetch=self.history(d), wall=lambda: clock["now"])
        pin = mb.Pinned(mb.pinned_attempt(hist, key="k", wall=lambda: clock["now"]), wall=lambda: clock["now"])
        out, s = [], start
        try:
            with unittest.mock.patch.object(sr, "time", _NoSleep()):
                while s <= until:
                    clock["now"] = T + s * SEC
                    n = len(self.calls)
                    p, err = pin.get(T)
                    held = pin.hold.get(mb._iso(T))
                    out.append((s, len(self.calls) - n, err, (held[0] - clock["now"]).total_seconds() if held else None))
                    if p is not None:
                        return out, p
                    s += every
            return out, None
        finally:
            self.fmp_times_out = None

    def test_h11_the_floors_refusal_is_held(self):
        """no trade after 12:40 anywhere, prices moving (D1), asked from 12:54:25 to 12:57:20 every 3 s: the 503 is the
        full-day one word for word every time; an attempt reads at most the whole book (63 FMP answers), is then held
        REBUILD_EVERY_S, and an ask inside the hold reads nothing (on the round-4 code: 59 attempts, 3,717 FMP calls)"""
        whole = 1 + len(mb.feed_tickers(sr.load_manifest(), HALF[0]))           # SPY first, then the whole book
        for d in HALF:
            with self.subTest(d=d):
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.mute(d, "12:40")
                asks, p = self.ask(d)
                self.assertIsNone(p)
                _, full = self.full_day_answer(d)
                self.assertEqual({tuple(sorted(a[2].items())) for a in asks},
                                 {(("detail", full.detail), ("error", full.error))})     # the full-day answer, every time
                made = [a for a in asks if a[1]]
                self.assertTrue(made and all(n <= whole for _, n, _, _ in made), [n for _, n, _, _ in made])
                self.assertEqual([h for _, _, _, h in made], [mb.REBUILD_EVERY_S] * len(made))   # each attempt held
                self.assertEqual(len(made), len(range(25, 201, 12)))           # one attempt in four asks: 15, not 59
                self.assertLessEqual(sum(n for _, n, _, _ in asks), whole * len(made))

    def test_h11_a_sibling_unanswered_keeps_the_floors_own_answer(self):
        """below the floor (D1: no trade after 12:40 anywhere, prices moving) with FMP not answering, all along, for a
        SIBLING only (a ticker no tree reads or can hold, asked only to rebuild a stale price from): every 503 is still
        the floor's own, the full-day answer word for word, never 'FMP has not answered' (a pin, passing before and
        after: the floor's unanswered check run over every ticker instead of the trees' fails it)"""
        cfg = sr.load_manifest()
        for d in HALF:
            sib = sorted(mb.feed_tickers(cfg, d) - mb.era_tickers(cfg) - mb.tree_universe(cfg, d))
            with self.subTest(d=d, sibling=sib[:1]):
                self.assertTrue(sib)
                self.rows = copy.deepcopy(self.fx["minutes"])
                self.mute(d, "12:40")
                _, full = self.full_day_answer(d)
                n = len(self.calls)
                asks, p = self.ask(d, slow=({sib[0]}, 10 ** 6))
                self.assertIsNone(p)
                self.assertIn((sib[0], d), self.calls[n:])                    # asked, and FMP never answered it
                self.assertEqual({tuple(sorted(a[2].items())) for a in asks},
                                 {(("detail", full.detail), ("error", full.error))})

    def test_h11_below_the_floor_while_fmp_has_not_answered_the_503_says_so(self):
        """the real 11-28 (SPY leaning on the half-day rule), 30 of FMP's 62 answers timing out until 12:55:00: below
        the floor only for want of answers -> 'decision not settled yet: FMP has not answered for ...' (as before the
        floor), held REBUILD_EVERY_S; the answers in, it settles on the day's own decision"""
        d = "2025-11-28"
        live, _ = self.pinned(d)
        slow = set(sorted(t for t in self.rows[d] if t != "SPY")[:30])
        asks, p = self.ask(d, slow=(slow, 60))
        self.assertIsNotNone(p, asks[-1])
        before = [a for a in asks if a[0] < 60]
        self.assertTrue(before)
        for s, n, err, hold in before:
            self.assertEqual(err["error"], "decision not settled yet", (s, err))
            self.assertTrue(err["detail"].startswith("FMP has not answered for "), (s, err))
            if n:
                self.assertEqual(hold, mb.REBUILD_EVERY_S)
        self.assertEqual(asks[-1][0], 61)                                       # the first attempt after the answers
        self.assertEqual((targets(p), p["prices"], p["decision_bar"]), (targets(live), live["prices"], live["decision_bar"]))

    def test_h11_a_book_frozen_late_while_fmp_has_not_answered_says_so_then_refuses_held(self):
        """round 7: the whole book frozen after the bar stamped 12:52 (07-03: SPY's trade 60 s old, no ticker trading at
        12:54, the floor held) while FMP's answers for 5 of the trees' tickers time out until 12:55:00: whether the book
        traded at the instant is not known, so 'decision not settled yet: FMP has not answered for ...' (they may have);
        the answers in, the frozen-feed refusal, to the end; never a decision, and each attempt held REBUILD_EVERY_S
        (the book is read whole). 952177fa settled it once the answers were in"""
        d = "2025-07-03"
        self.freeze(d, "12:52")
        slow = set(sorted(mb.tree_universe(sr.load_manifest(), d) - {"SPY"})[:5])
        asks, p = self.ask(d, slow=(slow, 60))
        self.assertIsNone(p, p and p["decision_bar"])
        made = [a for a in asks if a[1]]
        self.assertTrue(made)
        self.assertEqual([h for _, _, _, h in made], [mb.REBUILD_EVERY_S] * len(made))     # each attempt held
        for s, n, err, hold in asks:
            if s < 60:
                self.assertEqual(err["error"], "decision not settled yet", (s, err))
                self.assertTrue(err["detail"].startswith("FMP has not answered for "), (s, err))
            else:
                self.assertEqual(err["error"], "decision bar not published yet", (s, err))
                self.assertTrue(err["detail"].startswith(f"SPY's last traded bar ends 12:53:00 ET ({FROZEN}"), (s, err))
        self.assertTrue(any(s >= 60 for s, _, _, _ in made))


class H5PaperClock(unittest.TestCase):
    def test_h5_a_late_fill_ends_with_the_executors_cancel_instant(self):
        d = "2026-11-27"
        self.assertEqual((sr.session_close(d), md.decide_at(d)), ("13:00", "12:54"))

        class Mkt:
            def traded_factor(self, t, dd):
                return 1.0

        class Mins:
            def __init__(self, bars):
                self.bars = bars

            def get(self, t, dd):
                return self.bars
        # a buy limited at 50.00, left unfilled on the bar starting 12:54
        self.assertEqual(md.later_fill("X", d, "12:54", 50.0, Mins({"12:56": 50.2, "12:58": 49.9}), Mkt()),
                         {"at": "12:59", "px": 49.9})                         # the bar ending 12:59:00 still counts
        self.assertIsNone(md.later_fill("X", d, "12:54", 50.0, Mins({"12:56": 50.2, "12:59": 49.9}), Mkt()))  # 13:00: no
        mn = md.Minutes(key="k", now=lambda: datetime.datetime(2026, 11, 27, 18, 29, tzinfo=UTC))
        self.assertFalse(mn._final(d))                                         # 13:29 ET: not yet written to disk
        mn = md.Minutes(key="k", now=lambda: datetime.datetime(2026, 11, 27, 18, 30, tzinfo=UTC))
        self.assertTrue(mn._final(d))
        # the parity record (mirror_dry.snapshot_session, read by mirror_parity too): a Composer snapshot taken
        # after the 13:00 close carries the half-day's closing values; one taken at 12:30 is intraday
        cal = ["2026-11-25", d]
        self.assertEqual(md.snapshot_session("2026-11-27T18:30:00+00:00", cal), (d, "close"))
        self.assertEqual(md.snapshot_session("2026-11-27T17:30:00+00:00", cal), ("2026-11-25", "next-day"))


class H6Attestation(unittest.TestCase):
    def test_h6_the_half_day_routines_attestation_counts_at_12_54(self):
        """the half-day preview routine runs at 12:15 ET (17:15Z) and attests a minute or two later; the brain
        counts an ok only within MIRROR_ATTEST_MAX_AGE_S (3600 s) before the instant"""
        cfg, d = sr.load_manifest(), "2026-11-27"
        T = datetime.datetime(2026, 11, 27, 17, 54, tzinfo=UTC)                 # 12:54:00 ET
        body = {"session": d, "engines": {e: {"version": mb.era_of(c, d)["version"],
                                              "tree_sha1": mb.approved_sha1(mb.era_of(c, d))} for e, c in cfg.items()}}
        with unittest.mock.patch.dict(os.environ, {"MIRROR_ATTEST_MAX_AGE_S": ""}):
            for at, state in ((datetime.datetime(2026, 11, 27, 17, 16, 30, tzinfo=UTC), "ok"),     # 12:16:30 ET
                              (datetime.datetime(2026, 11, 27, 16, 53, 59, tzinfo=UTC), "none")):  # 11:53:59: over an hour
                a = mb.Attestations()
                a.put(body, at, cfg)
                self.assertEqual({r["state"] for r in mb.sync_block(cfg, d, a, T).values()}, {state}, at)


class H10Calendars(unittest.TestCase):
    def test_h10_the_brains_calendar_and_the_executors_agree_on_every_date_both_cover(self):
        """shadow_runner.HALF_DAYS / NYSE_HOLIDAYS against the executor's own (ibkr-executor/app/blend.py
        NYSE_EARLY_CLOSES / NYSE_HOLIDAYS, read from its source with ast: none of its imports needed), the tables its
        fallback clock and its half-day check read: the same day on every date from the later first entry to the end
        of the year both end in (the executor's tests/test_mirror_halfday.py E6 is the same check from its side)"""
        path = os.path.join(HERE, "..", "..", "..", "ibkr-executor", "app", "blend.py")
        if not os.path.isfile(path):
            self.skipTest("ibkr-executor is not in this checkout")
        with open(path) as f:
            tree = ast.parse(f.read())
        got = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id in ("NYSE_EARLY_CLOSES", "NYSE_HOLIDAYS")}
        early = {d: f"{h:02d}:{m:02d}" for d, (h, m) in got["NYSE_EARLY_CLOSES"].items()}
        closed = set(got["NYSE_HOLIDAYS"])
        ours, theirs = set(sr.HALF_DAYS) | set(sr.NYSE_HOLIDAYS), set(early) | closed
        self.assertEqual(sr.calendar_through(), min(max(int(d[:4]) for d in early), max(int(d[:4]) for d in closed)),
                         "the two calendars end in different years: extend both together")
        d, diff = datetime.date.fromisoformat(max(min(ours), min(theirs))), []
        while d.year <= sr.calendar_through():
            k = d.isoformat()
            mine = "closed" if k in sr.NYSE_HOLIDAYS else sr.session_close(k)
            exe = "closed" if k in closed else early.get(k, "16:00")
            if mine != exe:
                diff.append((k, mine, exe))
            d += datetime.timedelta(days=1)
        self.assertEqual(diff, [], "the brain's calendar (shadow_runner.py) and the executor's (blend.py) differ")
        self.assertEqual((sr.session_close("2026-11-27"), early.get("2026-11-27")), ("13:00", "13:00"))   # not vacuous

    def test_h10_the_executors_bound_on_spy_before_the_instant_is_the_brains_quiet_trade_max(self):
        """ibkr-executor/app/mirror.py HALF_DAY_SPY_MAX_S (read with ast by module_number, the executor's E11 evaluator)
        is this side's QUIET_TRADE_MAX_S (the preview's FRESH_MIN in seconds): the executor accepts SPY priced exactly as
        long before the instant as the brain leans on (the executor's E11 is the same check from its side; a drift
        guard, it passes before and after)"""
        path = os.path.join(HERE, "..", "..", "..", "ibkr-executor", "app", "mirror.py")
        if not os.path.isfile(path):
            self.skipTest("ibkr-executor is not in this checkout")
        with open(path) as f:
            tree = ast.parse(f.read())
        n = sum(1 for x in tree.body if isinstance(x, ast.Assign) and len(x.targets) == 1
                and isinstance(x.targets[0], ast.Name) and x.targets[0].id == "HALF_DAY_SPY_MAX_S")
        self.assertEqual(n, 1, "HALF_DAY_SPY_MAX_S is not assigned exactly once at module level in app/mirror.py")
        got = module_number(path, "HALF_DAY_SPY_MAX_S")
        self.assertEqual((float(got), mb.QUIET_TRADE_MAX_S), (float(pc.FRESH_MIN * 60), pc.FRESH_MIN * 60),
                         "the executor's HALF_DAY_SPY_MAX_S and the brain's QUIET_TRADE_MAX_S differ: change both together")

    def test_h10_the_bound_written_as_an_equivalent_expression_still_passes(self):
        """the drift guard above, run on app/mirror.py with the WHOLE right-hand side of HALF_DAY_SPY_MAX_S (found by its
        ast node's offsets, so the file's own form - 900.0, 15 * 60.0, 60 * 15, 1800 / 2 - does not matter) replaced
        by another expression, its source read through a stand-in of open() (nothing on disk changes). What it must
        equal is derived from this side's QUIET_TRADE_MAX_S (q), never written in: n * 60.0, 60 * n, 2q / 2, q and q.0
        (n = q / 60) pass, as the executor's E11 reads them; a minute more or less fails as drift. A change made on both
        sides (preclose.FRESH_MIN a minute up, QUIET_TRADE_MAX_S following it as a re-import would, and the executor's
        bound the same) passes; the same change on one side only, either one, fails (round 6's version rewrote only a
        plain-number literal and wrote 900 in: it failed on an equivalent form in mirror.py and on a correct two-sided
        change)"""
        path = os.path.normpath(os.path.join(HERE, "..", "..", "..", "ibkr-executor", "app", "mirror.py"))
        if not os.path.isfile(path):
            self.skipTest("ibkr-executor is not in this checkout")
        with open(path, "rb") as f:
            raw = f.read()
        node = next(n.value for n in ast.parse(raw).body if isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "HALF_DAY_SPY_MAX_S")
        lines = raw.splitlines(keepends=True)                    # ast's offsets: 1-based lines, UTF-8 byte columns

        def at(line, col):
            return sum(len(x) for x in lines[:line - 1]) + col
        lo, hi = at(node.lineno, node.col_offset), at(node.end_lineno, node.end_col_offset)

        def rhs(text):
            """mirror.py's source with HALF_DAY_SPY_MAX_S's right-hand side replaced by `text`"""
            return (raw[:lo] + text.encode() + raw[hi:]).decode()
        guard = self.test_h10_the_executors_bound_on_spy_before_the_instant_is_the_brains_quiet_trade_max
        real_open = open

        def run(edited):
            """the guard, mirror.py read as `edited`: True when it passes, False when it fails as drift"""
            def stand_in(p, *a, **k):
                if isinstance(p, str) and os.path.normpath(p) == path:
                    return io.StringIO(edited)
                return real_open(p, *a, **k)
            with unittest.mock.patch("builtins.open", stand_in):
                try:
                    guard()
                except AssertionError:
                    return False
            return True
        q = mb.QUIET_TRADE_MAX_S
        n = q // 60
        self.assertEqual((q % 60, rhs(raw[lo:hi].decode())), (0, raw.decode()))   # the offsets cut the whole value out
        for text, same in ((f"{n} * 60.0", True), (f"60 * {n}", True), (f"{2 * q} / 2", True), (f"{q}", True),
                           (f"{float(q)}", True), (f"{n + 1} * 60.0", False), (f"{float(q + 60)}", False),
                           (f"{q - 60}", False)):
            with self.subTest(text):
                self.assertEqual(run(rhs(text)), same)
        up = n + 1                                                # FRESH_MIN a minute up, as a re-import would see it
        for side, fresh, quiet, text, same in (("both sides", up, up * 60, f"{float(up * 60)}", True),
                                               ("both sides, an expression", up, up * 60, f"{up} * 60.0", True),
                                               ("the brain's side only", up, up * 60, f"{float(q)}", False),
                                               ("the executor's side only", n, q, f"{float(up * 60)}", False)):
            with self.subTest(side, text=text):
                with unittest.mock.patch.object(pc, "FRESH_MIN", fresh), \
                        unittest.mock.patch.object(mb, "QUIET_TRADE_MAX_S", quiet):
                    self.assertEqual(run(rhs(text)), same)


def module_number(path, name):
    """the module-level constant `name` of the python file `path`, read with ast (none of its imports run): a number,
    or a sum, difference, product or quotient of numbers and of `pc.<NAME>` (preclose.py's, beside it). The executor's
    E11 evaluator (ibkr-executor/tests/test_mirror_halfday.py _module_number), the same code on this side"""
    with open(path) as f:
        tree = ast.parse(f.read())
    node = next((n.value for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name), None)
    assert node is not None, f"{name} is not a module constant of {path}"

    def val(x):
        if isinstance(x, ast.Constant) and isinstance(x.value, (int, float)) and not isinstance(x.value, bool):
            return x.value
        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "pc":
            return module_number(os.path.join(os.path.dirname(path), "preclose.py"), x.attr)
        if isinstance(x, ast.BinOp) and isinstance(x.op, (ast.Mult, ast.Add, ast.Sub, ast.Div)):
            a, b = val(x.left), val(x.right)
            return {ast.Mult: a * b, ast.Add: a + b, ast.Sub: a - b, ast.Div: a / b if b else None}[type(x.op)]
        raise AssertionError(f"{name} in {path} is not a plain number: {ast.dump(x)}")
    return val(node)


if __name__ == "__main__":
    unittest.main()
