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
  H7  a FROZEN feed (bars without volume at the last trade's price, from 12:44 or 12:38) is refused: SPY
      alone, the whole book, all but SPY; the tickers the rule leans on frozen, the real trades untouched,
      are not counted; twin: half the book without volume from 12:44 with FMP's real, moving closes
      settles, the same bars frozen do not; any bar moved counts, not only the bar at the instant
  H8  the floor of REAL trades: no trade after 12:40 (or 12:44) anywhere, prices moving, is refused as the
      full-day rule refuses it, word for word; so is every ticker but SPY without a trade after 12:40 (the
      build's own floor; the `--at` path and the paper book too); a frozen tail; half the trees' tickers
      really trading settles, one fewer is refused; bars without volume 12 minutes before the instant are
      no evidence, with the floor held
  H9  quotes.breadth gives the real trades and the leaned ones apart, the leaned named in `problems`
  H10 the brain's calendar and the executor's (blend.py, read with ast) agree on every date both cover

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


if __name__ == "__main__":
    unittest.main()
