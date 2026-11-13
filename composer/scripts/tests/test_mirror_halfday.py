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
      over trades more than 15 minutes old (SPY's too); SPY's 12:54 minute not published yet; the
      15-minute boundary, to the bar
  H4  one brain: the composer-side paper book (mirror_dry.Minutes, its disk cache included) and the
      `--at` path reach the pinned path's decision on a half-day; fetch_minutes(quiet=True) lists exactly
      the bars without volume and changes nothing else
  H5  the paper book's half-day clock: a buy left unfilled at 12:54 can fill until the bar ending 12:59:00
      (the executor cancels at the close minus 60 s), never on the bar ending 13:00; its disk cache is final
      from 13:30; a Composer snapshot after 13:00 is the half-day's close for the parity record
  H6  the half-day preview routine's attestation (12:15 ET routine, ~12:16) counts at 12:54; one made over
      an hour before the instant does not

Run: python3 -m unittest composer.scripts.tests.test_mirror_halfday -v
"""
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
SEC = datetime.timedelta(seconds=1)


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
        # ... and not for lack of material: called a half-day, the same bars count five more tickers
        self.rows = copy.deepcopy(self.fx["minutes"])
        with unittest.mock.patch.dict(sr.HALF_DAYS, {REGULAR: "13:00"}):
            p3, _ = self.pinned(REGULAR)
        self.assertEqual((p1["quotes"]["breadth"]["recent"], p3["quotes"]["breadth"]["recent"]), (41, 46))


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
        self.assertIn("the feed looks dead", err.detail)
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

    def test_h3_the_fifteen_minute_boundary(self):
        d = "2025-07-03"
        # UDOW, an HG decision ticker: its last trade is the bar ending 12:46, and bars without volume follow
        self.assertEqual([r[0] for r in self.rows[d]["UDOW"] if r[0] >= "12:45" and r[2]], ["12:45"])
        p, _ = self.pinned(d)
        self.assertIn("UDOW 12:46", " ".join(p["problems"]))
        n = p["quotes"]["breadth"]["recent"]
        for last, counted in (("12:38", True), ("12:37", False)):              # its last trade 15 min / 16 min old
            with self.subTest(last=last):
                self.rows = copy.deepcopy(self.fx["minutes"])
                for r in self.rows[d]["UDOW"]:
                    if r[0] >= "12:20":
                        r[2] = 9184 if r[0] == last else 0
                p, err = self.pinned(d, waits=(30, 130))
                self.assertIsNone(err)
                said = " ".join(p["problems"])
                self.assertEqual(p["quotes"]["breadth"]["recent"], n if counted else n - 1)
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
            self.assertIn("12:53", json.load(f)["quiet"])
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
        self.assertEqual(quiet.pop("_quiet"), [hm for hm, _, v in rows if not v])
        self.assertEqual(quiet, plain)
        self.assertEqual(max(plain), "12:45")                                  # SPY's last bar WITH volume
        self.assertNotIn("_quiet", sr.fetch_minutes("SPY", d, "k", tries=1, traded=False, quiet=True))
        self.assertEqual(sr.fetch_minutes("SPY", d, "k", tries=1), sr.fetch_minutes("SPY", d, "k", tries=1, quiet=True))
        self.assertEqual(pc.minute_quotes({"SPY"}, self.instant(d), "k", fetch=lambda t, dd, k: dict(quiet, _quiet=["12:53"]))[0],
                         pc.minute_quotes({"SPY"}, self.instant(d), "k", fetch=lambda t, dd, k: dict(quiet))[0])


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


if __name__ == "__main__":
    unittest.main()
