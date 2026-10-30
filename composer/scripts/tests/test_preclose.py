"""Merge-blocking gate tests for preclose.py (the pre-close preview, results.md addendum 49).

House rule: a gate that cannot fail is not a gate. Each behavioural test is paired with a
BROKEN-INPUT counterpart that must land on the other side.

  P1  session: 15:50 decision on a full day, 12:50 on a half-day (Yahoo's period or the static
      list), shut on weekends and holidays, a period dated another day ignored
  P2  sigma of the minutes left: sqrt(minutes / 390), floored at 5 minutes
  P3  freshness: today's bar and a trade within 15 minutes; otherwise stale, with the reason
  P4  stale prices rebuilt from a fresh fund on the same index at its leverage (inverse, 2x/3x,
      VIX futures); nothing without a fresh sibling
  P5  gate: the flip price is the average of the other 199 closes, and the shadow evaluator's own
      reading of HG's condition flips exactly there; yesterday's state; sigma from yesterday back
  P6  outcome and flip: KMLM's corridor keeps the holdings inside 10pp; the flip is the nearest
      one-ticker move that changes a quarter of the holdings, None beyond 3 sigma; labels
  P7  engine rows and report: dollars, caveats (paused, stale attempt, drift), alerts (gate flips,
      gate on the line, big day) and their absence
  P8  preview end to end on the frozen 2026-10-28 prices: the approved trees reproduce Composer's
      own decisions for that session (no change anywhere), a stale SPY is rebuilt from IVV, a
      Composer outage leaves the logic, a Yahoo outage alerts, closed hours say so
  P9  ledger appends; exit codes

Run: python3 -m unittest composer.scripts.tests.test_preclose -v
"""
import contextlib
import datetime
import gzip
import io
import json
import math
import os
import sys
import tempfile
import unittest
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "shadow-2026-10-28.json.gz")
NY = zoneinfo.ZoneInfo("America/New_York")
UTC = datetime.timezone.utc


def et(y, m, d, hh, mm):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=NY).astimezone(UTC)


def ts(dt):
    return int(dt.timestamp())


def days(n, end="2026-10-28"):
    out, d = [], datetime.date.fromisoformat(end)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= datetime.timedelta(days=1)
    return sorted(out)


def feed(adj, now, age_min=2, today=True):
    """(adj, raw, meta) as fetch_live returns it"""
    a = dict(adj)
    if not today:
        a.pop(max(a))
    return a, dict(a), {"regularMarketTime": ts(now - datetime.timedelta(minutes=age_min))}


def asset(t):
    return {"step": "asset", "ticker": t}


def gate_tree(window=200, yes="A", no="B"):
    return {"step": "root", "children": [{"step": "if", "children": [
        {"step": "if-child", "lhs-fn": "current-price", "lhs-val": "SPY", "rhs-fn": "moving-average-price",
         "rhs-val": "SPY", "rhs-fn-params": {"window": window}, "comparator": "gt", "children": [asset(yes)]},
        {"step": "if-child", "is-else-condition?": True, "children": [asset(no)]}]}]}


def price_tree(level=100.0, yes=None, no=None):
    """if current-price(A) > level -> yes else no (each a child list)"""
    return {"step": "root", "children": [{"step": "if", "children": [
        {"step": "if-child", "lhs-fn": "current-price", "lhs-val": "A", "rhs-fixed-value?": True,
         "rhs-val": str(level), "comparator": "gt", "children": yes or [asset("X")]},
        {"step": "if-child", "is-else-condition?": True, "children": no or [asset("Y")]}]}]}


def walk_series(n, start=100.0, step=0.01, today=None):
    """alternating +-step returns (daily sigma = step), the last day set to `today` if given"""
    ds, p, out = days(n), start, {}
    for i, d in enumerate(ds):
        out[d] = p
        p *= 1 + (step if i % 2 == 0 else -step)
    if today is not None:
        out[ds[-1]] = today
    return out


# ------------------------------------------------------------------ P1
class P1Session(unittest.TestCase):
    def test_full_day(self):
        s = pc.session(et(2026, 10, 28, 15, 15))
        self.assertEqual((s["close"], s["decide"], s["left"]), ("16:00", "15:50", 35))
        period = {"start": ts(et(2026, 10, 28, 9, 30)), "end": ts(et(2026, 10, 28, 13, 0))}
        s2 = pc.session(et(2026, 10, 28, 15, 15), period)              # broken: a 13:00 close that day
        self.assertEqual((s2["decide"], s2["left"]), ("12:50", -145))

    def test_shut_days(self):
        self.assertIsNone(pc.session(et(2026, 10, 31, 15, 15)))           # Saturday
        self.assertIsNone(pc.session(et(2026, 11, 26, 15, 15)))           # Thanksgiving
        self.assertIsNotNone(pc.session(et(2026, 11, 25, 15, 15)))        # the day before trades

    def test_half_day_static(self):
        s = pc.session(et(2026, 11, 27, 12, 15))
        self.assertEqual((s["close"], s["decide"], s["left"]), ("13:00", "12:50", 35))
        s2 = pc.session(et(2026, 11, 20, 12, 15))                         # broken: an ordinary Friday
        self.assertEqual((s2["close"], s2["left"]), ("16:00", 215))

    def test_period_of_another_day_ignored(self):
        old = {"start": ts(et(2026, 11, 25, 9, 30)), "end": ts(et(2026, 11, 25, 16, 0))}
        self.assertEqual(pc.session(et(2026, 11, 27, 12, 15), old)["close"], "13:00")
        today = {"start": ts(et(2026, 11, 27, 9, 30)), "end": ts(et(2026, 11, 27, 16, 0))}
        self.assertEqual(pc.session(et(2026, 11, 27, 12, 15), today)["close"], "16:00")   # Yahoo wins when dated today


# ------------------------------------------------------------------ P2
class P2Sigma(unittest.TestCase):
    def test_scaling(self):
        self.assertEqual(pc.SIGMA_SCALE, 0.52)                            # add. 49 measurement
        self.assertAlmostEqual(pc.sigma_factor(35), 0.52 * math.sqrt(35 / 390))
        self.assertAlmostEqual(pc.sigma_factor(390), 0.52)
        self.assertAlmostEqual(pc.sigma_factor(140) / pc.sigma_factor(35), 2.0)   # sqrt(t)
        self.assertAlmostEqual(pc.sigma_factor(0), pc.sigma_factor(5))
        self.assertAlmostEqual(pc.sigma_factor(-20), 0.52 * math.sqrt(5 / 390))
        self.assertNotAlmostEqual(pc.sigma_factor(35), math.sqrt(35 / 390))      # broken: the unscaled random walk


# ------------------------------------------------------------------ P3
class P3Fresh(unittest.TestCase):
    def setUp(self):
        self.now = et(2026, 10, 28, 15, 15)
        self.s = {"2026-10-27": 10.0, "2026-10-28": 11.0}

    def test_fresh_and_stale(self):
        data = {"A": feed(self.s, self.now, 14), "B": feed(self.s, self.now, 16),
                "C": feed(self.s, self.now, 2, today=False), "D": (self.s, self.s, {})}
        fresh, stale = pc.freshness(data, "2026-10-28", self.now)
        self.assertEqual(fresh, {"A": 11.0})
        self.assertEqual(stale["B"], "14:59")
        self.assertEqual(stale["C"], "no trade today")
        self.assertEqual(stale["D"], "no trade time")


# ------------------------------------------------------------------ P4
class P4Rebuild(unittest.TestCase):
    def setUp(self):
        self.now = et(2026, 10, 28, 15, 15)

    def data(self, **moves):
        """{ticker: feed} with a 100 -> 100 x (1 + move) day for each fresh ticker; stale ones at 50"""
        out = {}
        for t, m in moves.items():
            if m is None:
                out[t] = feed({"2026-10-27": 50.0, "2026-10-28": 49.0}, self.now, 60)
            else:
                out[t] = feed({"2026-10-27": 100.0, "2026-10-28": 100.0 * (1 + m)}, self.now)
        return out

    def check(self, stale, sib, move, expect_ratio):
        d = self.data(**{stale: None, sib: move})
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        p, s = pc.rebuild(stale, d, "2026-10-28", fresh)
        self.assertEqual(s, sib)
        self.assertAlmostEqual(p / 50.0, expect_ratio, places=9)

    def test_leverage(self):
        self.check("SSO", "IVV", 0.01, 1.02)
        self.check("SQQQ", "QQQ", -0.01, 1.03)
        self.check("QLD", "TQQQ", 0.03, 1.02)
        self.check("SVIX", "UVXY", 0.03, 0.98)
        self.check("SPY", "IVV", -0.02, 0.98)

    def test_no_sibling(self):
        d = self.data(ZVOL=None, IVV=0.01)
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNone(pc.rebuild("ZVOL", d, "2026-10-28", fresh))         # no family
        d = self.data(SSO=None, IVV=None)
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNone(pc.rebuild("SSO", d, "2026-10-28", fresh))          # the sibling is stale too

    def test_live_prices(self):
        d = self.data(SSO=None, IVV=0.01, ZVOL=None)
        p, notes = pc.live_prices(d, "2026-10-28", self.now)
        self.assertAlmostEqual(p["SSO"]["2026-10-28"], 51.0)
        self.assertIn("via IVV", notes["SSO"])
        self.assertEqual(p["ZVOL"]["2026-10-28"], 49.0)                       # carried, and named
        self.assertIn("no fresh sibling", notes["ZVOL"])
        self.assertNotIn("IVV", notes)
        self.assertAlmostEqual(p["IVV"]["2026-10-28"], 101.0)


# ------------------------------------------------------------------ P5
class P5Gate(unittest.TestCase):
    def series(self, today, yday=None, n=230):
        s = walk_series(n, step=0.01)
        ds = sorted(s)
        if yday is not None:
            s[ds[-2]] = yday
        s[ds[-1]] = today
        return s, ds[-1]

    def test_flip_price_is_the_evaluators(self):
        s, d = self.series(100.0)
        ds = sorted(s)
        thr = sum(s[x] for x in ds[-200:-1]) / 199
        self.assertAlmostEqual(pc.gate(s, d, 0.3)["flip_at"], round(thr, 2))
        for k, want in ((1 + 1e-6, "A"), (1 - 1e-6, "B")):
            s2 = dict(s)
            s2[d] = thr * k
            sim, target, _ = sr.run_engine({"SPY": s2, "A": s2, "B": s2}, gate_tree(), d)
            self.assertEqual(target, {want: 1.0})
            self.assertEqual(pc.gate(s2, d, 0.3)["open"], want == "A")

    def test_exact_threshold(self):
        s, d = self.series(100.0)
        ds = sorted(s)
        thr = sum(s[x] for x in ds[-200:-1]) / 199
        self.assertAlmostEqual(pc.gate(s, d, 0.3)["flip_at"], round(thr, 2))
        s[d] = thr
        self.assertFalse(pc.gate(s, d, 0.3)["open"])                          # at the line: closed (gt)

    def test_yesterday_and_sigma(self):
        s, d = self.series(130.0, yday=80.0)
        g = pc.gate(s, d, 0.3)
        self.assertTrue(g["open"])
        self.assertFalse(g["open_prev"])
        s2, _ = self.series(130.0, yday=120.0)
        self.assertTrue(pc.gate(s2, d, 0.3)["open_prev"])                    # broken: yesterday above
        # sigma: from the 20 sessions to yesterday; today's own jump is not in it
        a, _ = self.series(101.0)
        b, _ = self.series(140.0)
        ga, gb = pc.gate(a, d, 0.3), pc.gate(b, d, 0.3)
        sd_a, sd_b = abs(ga["dist"]) / ga["sigma"], abs(gb["dist"]) / gb["sigma"]
        self.assertAlmostEqual(sd_a, sd_b, places=3)
        self.assertAlmostEqual(sd_a, 0.01 * 0.3, delta=2e-4)                 # factor passed in: 0.3

    def test_short_or_missing(self):
        s, d = self.series(100.0, n=215)
        self.assertIsNone(pc.gate(s, d, 0.3))
        s, d = self.series(100.0)
        s.pop(d)
        self.assertIsNone(pc.gate(s, d, 0.3))

    def test_gate_in(self):
        self.assertTrue(pc.gate_in(gate_tree()))
        self.assertFalse(pc.gate_in(gate_tree(window=100)))
        man = sr.load_manifest()
        self.assertTrue(pc.gate_in(sr.load_tree(man["HG"]["eras"][-1])))
        self.assertFalse(pc.gate_in(sr.load_tree(man["HG"]["eras"][-2])))    # the pre-gate era


# ------------------------------------------------------------------ P6
class P6Flip(unittest.TestCase):
    def test_after(self):
        live = {"A": 0.55, "B": 0.45}
        self.assertEqual(pc.after({"A": 0.5, "B": 0.5}, live, 0.1), live)        # inside the corridor
        self.assertEqual(pc.after({"A": 0.3, "B": 0.7}, live, 0.1), {"A": 0.3, "B": 0.7})
        self.assertEqual(pc.after({"A": 0.5, "B": 0.5}, live), {"A": 0.5, "B": 0.5})   # daily engine
        self.assertEqual(pc.after({"A": 1.0}, {}, 0.1), {"A": 1.0})

    def run_flip(self, a_today, tree=None, live=None, corridor=None):
        s = walk_series(60, step=0.01, today=a_today)
        d = max(s)
        tree = tree or price_tree()
        sim, target, tr = sr.run_engine({"A": s, "X": s, "Y": s}, tree, d)
        out = pc.after(target, live or {}, corridor)
        prev = sorted(s)[-2]
        return pc.flip(sim, tree, d, prev, tr, out, live or {}, corridor, pc.sigma_factor(35)), sim, d, prev

    def test_nearest_move(self):
        fl, sim, d, prev = self.run_flip(100.2)
        self.assertEqual((fl["ticker"], fl["instead"]), ("A", {"Y": 1.0}))
        self.assertLess(fl["move"], 0)
        self.assertLessEqual(100.2 * (1 + fl["move"]), 100.0)                 # this step crosses the line
        self.assertGreater(100.2 * (1 + fl["move"] / 1.25), 100.0)            # the step before does not
        self.assertAlmostEqual(fl["sigma"], abs(fl["move"]) / (sim.sigma("A", prev) * pc.sigma_factor(35)), places=1)
        far, *_ = self.run_flip(150.0)                                      # broken: far beyond 3 sigma
        self.assertIsNone(far)

    def test_materiality(self):
        small = price_tree(yes=[{"step": "wt-cash-specified", "children": [
            dict(asset("X"), weight={"num": 60, "den": 100}), dict(asset("Y"), weight={"num": 40, "den": 100})]}],
            no=[{"step": "wt-cash-equal", "children": [asset("X"), asset("Y")]}])
        self.assertIsNone(self.run_flip(100.2, small)[0])                   # 10% change only
        self.assertIsNotNone(self.run_flip(100.2)[0])                       # the full switch counts

    def test_corridor(self):
        live = {"X": 0.5, "Y": 0.5}
        both = price_tree(yes=[{"step": "wt-cash-specified", "children": [
            dict(asset("X"), weight={"num": 55, "den": 100}), dict(asset("Y"), weight={"num": 45, "den": 100})]}],
            no=[{"step": "wt-cash-specified", "children": [
                dict(asset("X"), weight={"num": 45, "den": 100}), dict(asset("Y"), weight={"num": 55, "den": 100})]}])
        self.assertIsNone(self.run_flip(100.2, both, live, 0.1)[0])          # either answer: no trade
        self.assertIsNotNone(self.run_flip(100.2, live={"Y": 1.0}, corridor=0.1)[0])

    def test_labels(self):
        self.assertEqual(pc.label(None), "firm")
        self.assertEqual(pc.label({"sigma": 0.8}), "coin-flip")
        self.assertEqual(pc.label({"sigma": 1.0}), "coin-flip")
        self.assertEqual(pc.label({"sigma": 1.5}), "could flip")
        self.assertEqual(pc.label({"sigma": 2.5}), "firm")


# ------------------------------------------------------------------ P7
class P7EngineRender(unittest.TestCase):
    cfg = {"symphony": "S1", "eras": [{"version": "VERSION0001", "from": "2025-01-01", "tree": "x"}]}

    def row(self, s, drifted=False, corridor=None):
        a = walk_series(60, today=101.0)
        d = max(a)
        cfg = dict(self.cfg, corridor=corridor) if corridor else self.cfg
        prices = {"A": a, "X": a, "Y": a, "SPY": a}
        return pc.engine("HG", cfg, price_tree(), prices, d, s, pc.sigma_factor(35), {}, drifted), d

    def test_engine(self):
        s = {"holdings": [{"ticker": "Y", "allocation": 1.0}], "value": 1000.0, "last_rebalance_attempted_on": "2099-01-01"}
        r, d = self.row(s)
        self.assertEqual((r["after"], r["live"], r["turnover"], r["moves"]), ({"X": 1.0}, {"Y": 1.0}, 1.0, 1000))
        self.assertNotIn("caveat", r)
        r, _ = self.row(dict(s, is_paused=True))
        self.assertIn("paused", r["caveat"])
        r, _ = self.row(dict(s, last_rebalance_attempted_on="2020-01-01"))
        self.assertIn("2020-01-01", r["caveat"])
        r, _ = self.row(s, drifted=True)
        self.assertIn("live logic differs", r["caveat"])
        r, _ = self.row(None)
        self.assertNotIn("live", r)
        r, _ = self.row(dict(s, holdings=[{"ticker": "X", "allocation": 0.95}, {"ticker": "Y", "allocation": 0.05}]), corridor=0.1)
        self.assertEqual((r["after"], r["max_gap"]), ({"X": 0.95, "Y": 0.05}, 0.05))

    def ss(self):
        return {"date": "2026-10-28", "now": "15:15", "decide": "15:50", "left": 35, "open": "09:30", "close": "16:00"}

    def g(self, **kw):
        base = {"spy": 700.0, "sma": 650.0, "flip_at": 649.7, "open": True, "open_prev": True, "dist": -0.0719,
                "day": -0.005, "sigma": 25.0}
        return dict(base, **kw)

    def test_alerts(self):
        self.assertEqual(pc.render(self.ss(), self.g(), [], {}, [])[1], [])
        a = pc.render(self.ss(), self.g(open=True, open_prev=False), [], {}, [])[1]
        self.assertTrue(a[0].startswith("GATE REOPENS"))
        a = pc.render(self.ss(), self.g(open=False, open_prev=True), [], {}, [])[1]
        self.assertTrue(a[0].startswith("GATE CLOSES"))
        a = pc.render(self.ss(), self.g(sigma=1.5), [], {}, [])[1]
        self.assertTrue(a[0].startswith("GATE ON THE LINE"))
        self.assertEqual(pc.render(self.ss(), self.g(sigma=2.5), [], {}, [])[1], [])
        a = pc.render(self.ss(), self.g(day=-0.021), [], {}, [])[1]
        self.assertTrue(a[0].startswith("BIG DAY"))
        self.assertEqual(pc.render(self.ss(), self.g(day=-0.019), [], {}, [])[1], [])

    def test_lines(self):
        same = {"engine": "HG", "status": "ok", "live": {"X": 1.0}, "after": {"X": 1.0}, "value": 1000.0, "moves": 0,
                "flip": None, "label": "firm", "stale": []}
        move = dict(same, after={"Y": 1.0}, moves=1000, flip={"ticker": "A", "move": -0.01, "sigma": 0.7, "instead": {"X": 1.0}},
                    label="coin-flip", stale=["A 14:25 (no fresh sibling: last price used)"])
        bad = {"engine": "KMLM", "status": "unavailable", "note": "no close"}
        lines, _ = pc.render(self.ss(), self.g(), [same, move, bad], {}, [])
        self.assertIn("no change (X 100%)", lines[2])
        self.assertIn("X 100% -> Y 100% ($1,000 moves). coin-flip: A -1.00% (0.7 sigma) -> X 100%", lines[3])
        self.assertIn("stale: A 14:25", lines[3])
        self.assertIn("unavailable: no close", lines[4])


# ------------------------------------------------------------------ P8
class P8Preview(unittest.TestCase):
    """end to end on the frozen 2026-10-28 closes as if they were 15:15 prices"""
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE) as f:
            cls.fx = json.load(f)

    def setUp(self):
        self.now = et(2026, 10, 28, 15, 15)
        self.period = {"start": ts(et(2026, 10, 28, 9, 30)), "end": ts(et(2026, 10, 28, 16, 0))}
        self.stale = {}
        self.extra = {}

    def fetch(self, t):
        if self.down:
            raise RuntimeError("Yahoo down")
        s = self.fx["prices"].get(t) or self.extra.get(t)
        if s is None:
            raise RuntimeError("no such ticker")
        a, r, meta = feed(s, self.now, 60 if t in self.stale else 2)
        if t in self.stale:
            a[max(a)] = r[max(r)] = self.stale[t]
        meta["currentTradingPeriod"] = {"regular": self.period}
        return a, r, meta

    def meta(self, overrides=None):
        man = sr.load_manifest()
        out = []
        for eng, cfg in man.items():
            w = (overrides or {}).get(eng) or self.fx["expected"][eng]["2026-10-28"]
            out.append({"id": cfg["symphony"], "value": 10000.0, "last_rebalance_attempted_on": "2026-10-27",
                        "holdings": [{"ticker": t, "allocation": x} for t, x in w.items()]})
        return out

    def run_preview(self, now=None, meta=None, fail=False, drift=None):
        self.down = fail

        def get_meta():
            if meta == "down":
                raise SystemExit("error: HTTP 503\nService Unavailable")
            return self.meta(meta)
        return pc.preview(now or self.now, get_meta, (lambda c: drift) if drift else None, fetch=self.fetch)

    def test_reproduces_composer(self):
        lines, alerts, led = self.run_preview()
        rows = {r["engine"]: r for r in led if r["engine"] != "GATE"}
        for eng in ("HG", "SLEEVE", "HARV"):
            self.assertTrue(pc.same(rows[eng]["target"], self.fx["expected"][eng]["2026-10-28"]), eng)
        self.assertTrue(pc.same(rows["KMLM"]["after"], self.fx["expected"]["KMLM"]["2026-10-28"]))   # corridor: no trade
        self.assertEqual(sum("no change" in x for x in lines), 4, lines)
        self.assertEqual(alerts, [])
        g = led[0]
        self.assertEqual((g["engine"], g["open"]), ("GATE", True))
        self.assertAlmostEqual(g["spy"], 772.31)
        # broken: Composer in QLD where the logic holds BIL
        lines, _, _ = self.run_preview(meta={"HG": {"QLD": 1.0}})
        self.assertTrue(any(x.startswith("HG") and "QLD 100% -> BIL 100%" in x for x in lines), lines)

    def test_stale_spy_rebuilt(self):
        self.extra["IVV"] = {d: p * 0.9 for d, p in self.fx["prices"]["SPY"].items()}
        self.stale = {"SPY": 700.0}
        _, _, led = self.run_preview()
        self.assertAlmostEqual(led[0]["spy"], 772.31, places=1)
        self.assertIn("via IVV", led[0]["stale"])
        del self.extra["IVV"]                                                # broken: every S&P sibling stale too
        self.stale.update({t: self.fx["prices"][t][max(self.fx["prices"][t])] * 0.9 for t in ("SSO", "SPXL", "UPRO")})
        _, _, led = self.run_preview()
        self.assertAlmostEqual(led[0]["spy"], 700.0)
        self.assertIn("no fresh sibling", led[0]["stale"])

    def test_composer_down(self):
        lines, alerts, led = self.run_preview(meta="down")
        self.assertTrue(any("Composer holdings: error: HTTP 503 Service Unavailable" in x for x in lines), lines)
        self.assertFalse(any(x.strip() == "Service Unavailable" for x in lines))   # one line, not the raw body
        self.assertTrue(all(r.get("status") == "ok" and "live" not in r for r in led if r["engine"] != "GATE"))
        self.assertEqual(alerts, [])

    def test_yahoo_down(self):
        lines, alerts, led = self.run_preview(fail=True)
        self.assertTrue(alerts and alerts[-1].startswith("PRE-CLOSE UNAVAILABLE"))
        self.assertEqual({r["status"] for r in led}, {"unavailable"})            # recorded, no gate row
        self.assertNotIn("GATE", [r["engine"] for r in led])
        _, alerts, _ = self.run_preview()                                    # broken: Yahoo up
        self.assertFalse(any(a.startswith("PRE-CLOSE UNAVAILABLE") for a in alerts))

    def test_drift_caveat(self):
        _, _, led = self.run_preview(drift={"KMLM"})
        rows = {r["engine"]: r for r in led}
        self.assertIn("live logic differs", rows["KMLM"]["caveat"])
        self.assertNotIn("caveat", rows["HG"])

    def test_closed_hours(self):
        lines, alerts, led = self.run_preview(now=et(2026, 10, 28, 16, 5))
        self.assertIn("closed at 16:00", lines[0])
        self.assertEqual((alerts, led), ([], []))
        lines, _, _ = self.run_preview(now=et(2026, 10, 28, 9, 0))
        self.assertIn("opens at 09:30", lines[0])
        lines, _, _ = self.run_preview(now=et(2026, 10, 31, 15, 15))
        self.assertIn("no session today", lines[0])
        self.period = {"start": ts(et(2026, 10, 28, 9, 30)), "end": ts(et(2026, 10, 28, 13, 0))}   # a half-day
        lines, _, _ = self.run_preview()
        self.assertIn("closed at 13:00", lines[0])


# ------------------------------------------------------------------ P9
class P9LedgerExit(unittest.TestCase):
    def test_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "sub", "l.jsonl")
            pc.append_ledger([{"engine": "GATE"}, {"engine": "HG"}], p)
            pc.append_ledger([{"engine": "GATE"}], p)
            with open(p) as f:
                rows = [json.loads(x) for x in f]
            self.assertEqual([r["engine"] for r in rows], ["GATE", "HG", "GATE"])

    def test_exit_codes(self):
        saved = pc.preview
        try:
            for alerts, code in (([], 0), (["GATE CLOSES"], 2)):
                pc.preview = lambda now, gm, gd=None, fetch=None, a=alerts: (["x"], a, [])
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
                    pc.main()
                self.assertEqual(cm.exception.code, code)
        finally:
            pc.preview = saved


if __name__ == "__main__":
    unittest.main()
