"""Merge-blocking gate tests for preclose.py (the pre-close preview, results.md addendum 49).

House rule: a gate that cannot fail is not a gate. Each behavioural test is paired with a
BROKEN-INPUT counterpart that must land on the other side. The counter-agent's surviving mutants
(add. 49) each have a test that now kills them.

  P1  session: 15:50 decision on a full day, 12:50 on a half-day (Yahoo's period or the static
      list), shut on weekends and holidays, a period dated another day ignored
  P2  sigma of the minutes left: 0.6 x sqrt(minutes / 390), floored at 5 minutes
  P3  freshness: today's bar and a trade within 15 minutes; otherwise stale, with reason and age
  P4  stale prices rebuilt from a fresh fund on the same index at its leverage (inverse, 2x/3x, VIX
      futures), never across different previous sessions or from a related index; the family table
      pinned
  P5  gate: the flip price is the average of the other 199 closes, and the shadow evaluator's own
      reading of HG's condition flips exactly there; yesterday's state on yesterday's window; the
      sign of the distance; sigma from yesterday back; gate_in reads ticker, window and comparator
  P6  outcome and one-ticker flip: KMLM's corridor on the largest gap at 10pp; the flip is the
      nearest move (bisected) that changes a quarter of the holdings, through the corridor, None
      beyond 3 sigma, the nearer of two tickers
  P7  market scenarios and labels: beta, every fund moved by its beta, either way, through the
      corridor, a correlated move that no single ticker makes, the label thresholds, stale decision
      tickers stress-tested both ways, alternatives that read a stale price flagged
  P8  engine rows and report: empty holdings, paused, caveats kept together, dollars from the
      outcome, KMLM's trigger on the line; alerts (gate flips with what HG holds on each side, gate
      on the line on either side, big day either way) and their absence
  P9  preview end to end on the frozen 2026-10-28 prices: the approved trees reproduce Composer's
      own decisions for that session, a stale SPY is rebuilt from IVV, a Composer outage leaves the
      logic, a Yahoo outage or a market with no trades alerts, drift caveats and failures shown,
      closed hours say so, the quotes' age widens every sigma, a stale SPY's own age widens the
      gate's, sigma and betas end yesterday
  P10 ledger appends; exit codes; a crashed preview still alerts
  P11 live prices from FMP's 1-minute bars (add. 50): the last bar ending at or before the run, SPY
      first or nothing; FMP's price unless Yahoo's last sale is over a minute newer; nothing from the
      run's future (replays), Yahoo's included; a stale Yahoo price rescued, siblings too; a market
      Yahoo shows shut but FMP shows trading is previewed; Yahoo's history must reach the previous
      session; disagreements only between prices of one moment; FMP down, problems, no key, switched
      off: said in the report; counts over priced tickers; the ledger's per-ticker record

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
import unittest.mock
import urllib.parse
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.pop("FMP_API_KEY", None)          # the suite never reaches FMP: quotes come from the tests
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "shadow-2026-10-28.json.gz")
NY = zoneinfo.ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
F35 = pc.sigma_factor(35)


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


def asset(t, w=None):
    n = {"step": "asset", "ticker": t}
    if w is not None:
        n["weight"] = {"num": round(w * 100), "den": 100}
    return n


def mix(**w):
    return {"step": "wt-cash-specified", "children": [asset(t, x) for t, x in w.items()]}


def cond(t, level, yes, no):
    """if current-price(t) > level -> yes else no (child lists)"""
    return {"step": "if", "children": [
        {"step": "if-child", "lhs-fn": "current-price", "lhs-val": t, "rhs-fixed-value?": True, "rhs-val": str(level),
         "comparator": "gt", "children": yes},
        {"step": "if-child", "is-else-condition?": True, "children": no}]}


def tree_of(node):
    return {"step": "root", "children": [node]}


def price_tree(level=100.0, yes=None, no=None):
    return tree_of(cond("A", level, yes or [asset("X")], no or [asset("Y")]))


def gate_tree(window=200, lhs="SPY", comparator="gt"):
    return tree_of({"step": "if", "children": [
        {"step": "if-child", "lhs-fn": "current-price", "lhs-val": lhs, "rhs-fn": "moving-average-price",
         "rhs-val": "SPY", "rhs-fn-params": {"window": window}, "comparator": comparator, "children": [asset("A")]},
        {"step": "if-child", "is-else-condition?": True, "children": [asset("B")]}]})


def walk_series(n, start=100.0, step=0.01, today=None):
    """alternating +-step returns (daily sigma = step), the last day set to `today` if given"""
    ds, p, out = days(n), start, {}
    for i, d in enumerate(ds):
        out[d] = p
        p *= 1 + (step if i % 2 == 0 else -step)
    if today is not None:
        out[ds[-1]] = today
    return out


def levered(base, lev, today):
    """a series whose daily returns are lev x base's, rescaled so its last close is `today`"""
    ds = sorted(base)
    out, p = {ds[0]: 1.0}, 1.0
    for a, b in zip(ds, ds[1:]):
        p *= 1 + lev * (base[b] / base[a] - 1)
        out[b] = p
    k = today / out[ds[-1]]
    return {d: v * k for d, v in out.items()}


def sim_of(prices, tree):
    d = max(prices["A"])
    sim, target, tr = sr.run_engine(prices, tree, d)
    return sim, target, tr, d, sorted(prices["A"])[-2]


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
        self.assertEqual(pc.SIGMA_SCALE, 0.6)                             # add. 49
        self.assertAlmostEqual(pc.sigma_factor(35), 0.6 * math.sqrt(35 / 390))
        self.assertAlmostEqual(pc.sigma_factor(140) / pc.sigma_factor(35), 2.0)   # sqrt(t)
        self.assertAlmostEqual(pc.sigma_factor(0), pc.sigma_factor(5))
        self.assertAlmostEqual(pc.sigma_factor(-20), 0.6 * math.sqrt(5 / 390))
        self.assertNotAlmostEqual(pc.sigma_factor(35), math.sqrt(35 / 390))      # broken: the plain random walk

    def test_daily_sd(self):
        s = walk_series(30, step=0.01)
        self.assertAlmostEqual(pc.daily_sd(s, max(s)), 0.01, delta=2e-4)
        short = walk_series(15)
        self.assertIsNone(pc.daily_sd(short, max(short)))


# ------------------------------------------------------------------ P3
class P3Fresh(unittest.TestCase):
    def test_fresh_and_stale(self):
        now = et(2026, 10, 28, 15, 15)
        s = {"2026-10-27": 10.0, "2026-10-28": 11.0}
        data = {"A": feed(s, now, 14), "B": feed(s, now, 16), "C": feed(s, now, 2, today=False), "D": (s, s, {}),
                "E": feed(s, now, 15)}
        fresh, stale = pc.freshness(data, "2026-10-28", now)
        self.assertEqual(fresh, {"A": 11.0, "E": 11.0})                       # 15 minutes exactly is still fresh
        self.assertEqual(stale["B"][0], "14:59")
        self.assertAlmostEqual(stale["B"][1], 16.0)
        self.assertEqual(stale["C"], ("no trade today", None))
        self.assertEqual(stale["D"], ("no trade time", None))


# ------------------------------------------------------------------ P4
class P4Rebuild(unittest.TestCase):
    def setUp(self):
        self.now = et(2026, 10, 28, 15, 15)

    def data(self, **moves):
        """{ticker: feed} with a 100 -> 100 x (1 + move) day for each fresh ticker; stale ones at 50 -> 49"""
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
        self.check("SVXY", "VIXY", 0.04, 0.98)
        self.check("TMV", "TLT", 0.01, 0.97)
        self.check("SPY", "IVV", -0.02, 0.98)

    def test_no_cross_index_stand_in(self):
        d = self.data(SOXL=None, USD=0.02)                                     # USD: 2x a different index
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNone(pc.rebuild("SOXL", d, "2026-10-28", fresh))
        _, notes, carried = pc.live_prices(d, "2026-10-28", self.now)
        self.assertIn("last price used", notes["SOXL"])
        self.assertIn("SOXL", carried)
        d = self.data(SOXL=None, SOXX=0.01)                                    # broken: the same index is fresh
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertEqual(pc.rebuild("SOXL", d, "2026-10-28", fresh)[1], "SOXX")

    def test_no_sibling(self):
        d = self.data(ZVOL=None, IVV=0.01)
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNone(pc.rebuild("ZVOL", d, "2026-10-28", fresh))          # no family
        d = self.data(SSO=None, IVV=None)
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNone(pc.rebuild("SSO", d, "2026-10-28", fresh))           # the sibling is stale too

    def test_previous_sessions_must_match(self):
        d = self.data(SSO=None)
        d["IVV"] = feed({"2026-10-26": 100.0, "2026-10-28": 101.0}, self.now)   # IVV has no 10-27 close
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNone(pc.rebuild("SSO", d, "2026-10-28", fresh))
        d["IVV"] = feed({"2026-10-27": 100.0, "2026-10-28": 101.0}, self.now)   # broken: it has
        fresh, _ = pc.freshness(d, "2026-10-28", self.now)
        self.assertIsNotNone(pc.rebuild("SSO", d, "2026-10-28", fresh))

    def test_live_prices(self):
        d = self.data(SSO=None, IVV=0.01, ZVOL=None)
        p, notes, carried = pc.live_prices(d, "2026-10-28", self.now)
        self.assertAlmostEqual(p["SSO"]["2026-10-28"], 51.0)
        self.assertIn("via IVV", notes["SSO"])
        self.assertEqual(p["ZVOL"]["2026-10-28"], 49.0)                       # carried, and named
        self.assertIn("no fresh sibling", notes["ZVOL"])
        self.assertEqual(set(carried), {"ZVOL"})
        self.assertAlmostEqual(carried["ZVOL"], 60.0)
        d["PEJ"] = feed({"2026-10-27": 30.0}, self.now, 2)                    # no trade today at all
        _, _, carried = pc.live_prices(d, "2026-10-28", self.now)
        self.assertIn("PEJ", carried)
        self.assertIsNone(carried["PEJ"])
        self.assertNotIn("IVV", notes)

    def test_families_pinned(self):
        want = {"SPY": 1, "IVV": 1, "VOO": 1, "SSO": 2, "SPXL": 3, "UPRO": 3, "QQQ": 1, "QQQM": 1, "QLD": 2, "TQQQ": 3,
                "PSQ": -1, "SQQQ": -3, "SOXX": 1, "SOXL": 3, "SOXS": -3, "XLK": 1, "TECL": 3, "XLF": 1, "FAS": 3,
                "XBI": 1, "LABU": 3, "LABD": -3, "IWM": 1, "TNA": 3, "DIA": 1, "UDOW": 3, "VIXY": 1, "VXX": 1,
                "UVXY": 1.5, "SVIX": -1, "SVXY": -0.5, "VIXM": 1, "VXZ": 1, "TLT": 1, "TMF": 3, "TMV": -3}
        got = {t: lv for f in pc.FAMILIES.values() for t, lv in f.items()}
        self.assertEqual(got, want)
        self.assertEqual(pc.family("SQQQ"), pc.family("QQQ"))
        self.assertIsNone(pc.family("USD"))


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
        g = pc.gate(s, d, 0.3)
        self.assertAlmostEqual(g["flip_at"], round(thr, 2))
        self.assertAlmostEqual(g["flip_exact"], thr)
        for k, want in ((1 + 1e-6, "A"), (1 - 1e-6, "B")):
            s2 = dict(s)
            s2[d] = thr * k
            _, target, _ = sr.run_engine({"SPY": s2, "A": s2, "B": s2}, gate_tree(), d)
            self.assertEqual(target, {want: 1.0})
            self.assertEqual(pc.gate(s2, d, 0.3)["open"], want == "A")
        self.assertEqual(pc.gate_sides({"SPY": s, "A": s, "B": s}, gate_tree(), d, thr), [{"A": 1.0}, {"B": 1.0}])

    def test_exact_threshold_and_sign(self):
        s, d = self.series(100.0)
        ds = sorted(s)
        thr = sum(s[x] for x in ds[-200:-1]) / 199
        s[d] = thr * 1.01
        g = pc.gate(s, d, 0.3)
        self.assertTrue(g["open"])
        self.assertLess(g["dist"], 0)                                          # SPY must fall to close it
        s[d] = thr * 0.99
        self.assertGreater(pc.gate(s, d, 0.3)["dist"], 0)
        s[d] = thr
        self.assertFalse(pc.gate(s, d, 0.3)["open"])                          # at the line: closed (gt)
        for k in (1.2, 0.8):                                                   # far either side: a large positive sigma
            s[d] = thr * k
            self.assertGreater(pc.gate(s, d, 0.3)["sigma"], 10)

    def test_yesterday_on_yesterdays_window(self):
        s, d = self.series(130.0, yday=80.0)
        g = pc.gate(s, d, 0.3)
        self.assertTrue(g["open"])
        self.assertFalse(g["open_prev"])
        base = walk_series(230, step=0.01)
        bd = sorted(base)
        others = sum(base[x] for x in bd[-201:-2])                            # the 199 closes before yesterday
        base[bd[-2]] = others / 199 * 1.002                                   # yesterday just above its own line
        base[bd[-1]] = 400.0                                                  # a huge today must not move it
        self.assertTrue(pc.gate(base, bd[-1], 0.3)["open_prev"])
        base[bd[-2]] = others / 199 * 0.998                                   # broken: just below
        self.assertFalse(pc.gate(base, bd[-1], 0.3)["open_prev"])

    def test_sigma_from_yesterday(self):
        a, d = self.series(101.0)
        b, _ = self.series(140.0)
        ga, gb = pc.gate(a, d, 0.3), pc.gate(b, d, 0.3)
        sd_a, sd_b = abs(ga["dist"]) / ga["sigma"], abs(gb["dist"]) / gb["sigma"]
        self.assertAlmostEqual(sd_a, sd_b, places=3)
        self.assertAlmostEqual(sd_a, 0.01 * 0.3, delta=2e-4)

    def test_short_or_missing(self):
        s, d = self.series(100.0, n=215)
        self.assertIsNone(pc.gate(s, d, 0.3))
        s, d = self.series(100.0)
        s.pop(d)
        self.assertIsNone(pc.gate(s, d, 0.3))

    def test_gate_in(self):
        self.assertTrue(pc.gate_in(gate_tree()))
        self.assertFalse(pc.gate_in(gate_tree(window=100)))
        self.assertFalse(pc.gate_in(gate_tree(lhs="QQQ")))
        self.assertFalse(pc.gate_in(gate_tree(comparator="lt")))
        man = sr.load_manifest()
        self.assertTrue(pc.gate_in(sr.load_tree(man["HG"]["eras"][-1])))
        self.assertFalse(pc.gate_in(sr.load_tree(man["HG"]["eras"][-2])))    # the pre-gate era


# ------------------------------------------------------------------ P6
class P6OutcomeFlip(unittest.TestCase):
    def test_after_corridor(self):
        live = {"A": 0.55, "B": 0.45}
        self.assertEqual(pc.after({"A": 0.5, "B": 0.5}, live, 0.1), live)        # inside the corridor
        self.assertEqual(pc.after({"A": 0.3, "B": 0.7}, live, 0.1), {"A": 0.3, "B": 0.7})
        self.assertEqual(pc.after({"A": 0.5, "B": 0.5}, live), {"A": 0.5, "B": 0.5})   # daily engine
        self.assertEqual(pc.after({"A": 1.0}, {}, 0.1), {"A": 1.0})
        # the largest single gap decides, not the total: 6pp each, 12pp half-L1 -> no trade
        live4 = {"P": 0.35, "Q": 0.35, "R": 0.15, "S": 0.15}
        self.assertEqual(pc.after({"P": 0.29, "Q": 0.29, "R": 0.21, "S": 0.21}, live4, 0.1), live4)
        self.assertEqual(pc.after({"Q": 1.0}, {"P": 0.1, "Q": 0.9}, 0.1), {"P": 0.1, "Q": 0.9})   # exactly 10pp: no trade
        # 10.5pp is past the 10pp trigger
        self.assertEqual(pc.after({"P": 0.395, "Q": 0.605}, {"P": 0.5, "Q": 0.5}, 0.1), {"P": 0.395, "Q": 0.605})

    def run_flip(self, a_today, tree=None, live=None, corridor=None):
        a = walk_series(60, step=0.01, today=a_today)
        prices = {"A": a, "X": a, "Y": a, "P": a, "Q": a, "R": a, "S": a}
        tree = tree or price_tree()
        sim, target, tr, d, prev = sim_of(prices, tree)
        end = (lambda w: pc.after(w, live, corridor)) if live else dict
        return pc.flip(sim, tree, d, prev, tr, end(target), end, F35), sim, prev

    def test_nearest_move_bisected(self):
        fl, sim, prev = self.run_flip(100.2)
        self.assertEqual((fl["ticker"], fl["instead"]), ("A", {"Y": 1.0}))
        exact = 100 / 100.2 - 1
        self.assertAlmostEqual(fl["move"], exact, delta=2e-5)                 # the threshold, not a grid step
        self.assertAlmostEqual(fl["sigma"], abs(exact) / (sim.sigma("A", prev) * F35), delta=0.02)
        far, *_ = self.run_flip(150.0)                                      # broken: far beyond 3 sigma
        self.assertIsNone(far)

    def test_radius_three_sigma(self):
        sl = 0.01 * F35
        fl, *_ = self.run_flip(100 / (1 - 2.5 * sl))                         # needs 2.5 sigma
        self.assertIsNotNone(fl)
        self.assertAlmostEqual(fl["sigma"], 2.5, delta=0.05)
        self.assertIsNone(self.run_flip(100 / (1 - 3.2 * sl))[0])             # 3.2 sigma: outside

    def test_materiality(self):
        small = price_tree(yes=[mix(X=0.6, Y=0.4)], no=[mix(X=0.5, Y=0.5)])
        self.assertIsNone(self.run_flip(100.2, small)[0])                   # a 10% change only
        thirty = price_tree(yes=[mix(X=0.7, Y=0.3)], no=[mix(X=0.4, Y=0.6)])
        self.assertIsNotNone(self.run_flip(100.2, thirty)[0])               # 30% counts
        self.assertIsNotNone(self.run_flip(100.2)[0])

    def test_through_the_corridor(self):
        live = {"P": 0.25, "Q": 0.25, "R": 0.25, "S": 0.25}
        swing = price_tree(yes=[mix(P=0.34, Q=0.34, R=0.16, S=0.16)], no=[mix(P=0.16, Q=0.16, R=0.34, S=0.34)])
        self.assertIsNone(self.run_flip(100.2, swing, live, 0.1)[0])          # both answers sit inside the corridor
        self.assertIsNotNone(self.run_flip(100.2, swing)[0])                  # broken: a daily engine would trade
        self.assertIsNotNone(self.run_flip(100.2, live={"Y": 1.0}, corridor=0.1)[0])

    def two(self, a_sig, b_sig):
        """A and B both on the path; A must move a_sig sigmas, B b_sig sigmas, to flip"""
        sl = 0.01 * F35
        a = walk_series(60, step=0.01, today=100 / (1 - a_sig * sl))
        b = walk_series(60, step=0.01, today=100 / (1 - b_sig * sl))
        tree = tree_of(cond("A", 100, [cond("B", 100, [asset("X")], [asset("Y")])], [asset("Y")]))
        sim, target, tr, d, prev = sim_of({"A": a, "B": b, "X": a, "Y": a}, tree)
        return pc.flip(sim, tree, d, prev, tr, target, dict, F35)

    def test_nearest_across_tickers(self):
        fl = self.two(1.3, 0.5)                                              # A is searched first, B is nearer
        self.assertEqual(fl["ticker"], "B")
        self.assertAlmostEqual(fl["sigma"], 0.5, delta=0.02)
        fl = self.two(1.0, 0.92)                                             # both flip at the same grid step
        self.assertEqual(fl["ticker"], "B")
        self.assertAlmostEqual(fl["sigma"], 0.92, delta=0.02)
        self.assertEqual(self.two(0.6, 1.4)["ticker"], "A")                  # broken: A nearer

    def test_nearer_ticker_one_grid_step_later(self):
        """B's threshold is nearer than A's but its first flipping grid step comes after A's: the search
        must look one step beyond the first flip"""
        sl_a = 0.01 * F35
        grid = [1e-4 * 1.25 ** k for k in range(40)]
        found = None
        for ka in range(12, 18):                                             # A's threshold just under a grid step
            a_x = grid[ka] * 0.999
            for step_b in (0.0105, 0.011, 0.0115, 0.012, 0.0125, 0.013):
                sl_b = step_b * F35
                b_ratio = a_x / sl_a * 0.97                                   # B 3% nearer, in its own sigmas
                b_x = b_ratio * sl_b
                ga = min(g for g in grid if g >= a_x) / sl_a
                gb = min(g for g in grid if g >= b_x) / sl_b
                if gb > ga * 1.0001 and b_ratio < a_x / sl_a:
                    found = (a_x, step_b, b_x, b_ratio)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        a_x, step_b, b_x, b_ratio = found
        a = walk_series(60, step=0.01, today=100 / (1 - a_x))
        b = walk_series(60, step=step_b, today=100 / (1 - b_x))
        tree = tree_of(cond("A", 100, [cond("B", 100, [asset("X")], [asset("Y")])], [asset("Y")]))
        sim, target, tr, d, prev = sim_of({"A": a, "B": b, "X": a, "Y": a}, tree)
        fl = pc.flip(sim, tree, d, prev, tr, target, dict, F35)
        self.assertEqual(fl["ticker"], "B")
        self.assertAlmostEqual(fl["sigma"], b_ratio * (step_b / sim.sigma("B", prev)), delta=0.02)

    def test_alternative_at_the_threshold(self):
        """the holdings shown are those just past the threshold, not at the grid step that found it"""
        a = walk_series(60, step=0.01, today=100.2)
        tree = tree_of(cond("A", 100, [asset("X")], [cond("A", 99.99, [asset("Y")], [asset("Z")])]))
        sim, target, tr, d, prev = sim_of({"A": a, "X": a, "Y": a, "Z": a}, tree)
        fl = pc.flip(sim, tree, d, prev, tr, target, dict, F35)
        self.assertEqual(fl["instead"], {"Y": 1.0})
        self.assertLess(100.2 * (1 + fl["move"]), 100.0)
        self.assertGreater(100.2 * (1 + fl["move"]), 99.99)

    def test_corridor_absorbs_a_wide_swing(self):
        live = {t: 1 / 6 for t in "PQRSTU"}
        hi, lo = 1 / 6 + 0.09, 1 / 6 - 0.09
        swing = price_tree(yes=[mix(P=hi, Q=hi, R=hi, S=lo, T=lo, U=lo)], no=[mix(P=lo, Q=lo, R=lo, S=hi, T=hi, U=hi)])
        a = walk_series(60, step=0.01, today=100.2)
        prices = {t: a for t in "AXYPQRSTU"}
        sim, target, tr, d, prev = sim_of(prices, swing)
        end = lambda w: pc.after(w, live, 0.1)                               # noqa: E731
        self.assertGreaterEqual(sr.distance(target, live)[0], pc.FLIP_MATERIAL)   # the raw targets differ by 27%
        self.assertIsNone(pc.flip(sim, swing, d, prev, tr, end(target), end, F35))  # but neither would trade
        self.assertIsNotNone(pc.flip(sim, swing, d, prev, tr, target, dict, F35))   # broken: no corridor

    def test_nearer_of_two_tickers(self):
        a = walk_series(60, step=0.01, today=100.4)                          # A needs -0.4%
        b = walk_series(60, step=0.01, today=100.2)                          # B needs -0.2%: nearer
        tree = tree_of(cond("A", 100, [cond("B", 100, [asset("X")], [asset("Y")])], [asset("Y")]))
        prices = {"A": a, "B": b, "X": a, "Y": a}
        sim, target, tr, d, prev = sim_of(prices, tree)
        fl = pc.flip(sim, tree, d, prev, tr, target, dict, F35)
        self.assertEqual(fl["ticker"], "B")
        self.assertAlmostEqual(fl["sigma"], (1 - 100 / 100.2) / (sim.sigma("B", prev) * F35), delta=0.03)


# ------------------------------------------------------------------ P7
class P7Market(unittest.TestCase):
    def setUp(self):
        self.spy = walk_series(80, step=0.01)
        self.d = max(self.spy)
        self.prev = sorted(self.spy)[-2]
        self.m1 = 0.01 * F35                                                 # SPY's 1-sigma move left

    def test_beta(self):
        m = self.spy
        self.assertAlmostEqual(pc.beta(levered(m, 2, 50.0), m, self.d), 2.0, places=6)
        self.assertAlmostEqual(pc.beta(levered(m, -3, 50.0), m, self.d), -3.0, places=6)
        self.assertAlmostEqual(pc.beta({d: 5.0 for d in m}, m, self.d), 0.0)
        self.assertIsNone(pc.beta(walk_series(20), m, self.d))               # too short

    def both(self, a_today=100.3, b_today=100.2):
        """X while A > 100, or while B > 100; Y once both are at or below 100: no single move flips it"""
        prices = {"SPY": self.spy, "A": levered(self.spy, 3, a_today), "B": levered(self.spy, 3, b_today),
                  "X": self.spy, "Y": self.spy}
        tree = tree_of(cond("A", 100, [asset("X")], [cond("B", 100, [asset("X")], [asset("Y")])]))
        return prices, tree

    def test_market_moves_by_beta(self):
        prices, tree = self.both()
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        self.assertAlmostEqual(betas["A"], 3.0, places=6)
        self.assertEqual(pc.market(prices, tree, self.d, -self.m1, betas)[0], {"Y": 1.0})   # -0.54% on A and B
        self.assertEqual(pc.market(prices, tree, self.d, self.m1, betas)[0], {"X": 1.0})
        self.assertEqual(pc.market(prices, tree, self.d, -self.m1, {})[0], {"X": 1.0})      # no betas: nothing moves
        self.assertEqual(set(sr.trace_tickers(pc.market(prices, tree, self.d, -self.m1, betas)[1], tree)), {"A", "B"})

    def test_correlated_move_only(self):
        prices, tree = self.both()
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        sim, target, tr = sr.run_engine(prices, tree, self.d)
        u = pc.uncertainty(sim, tree, self.d, self.prev, tr, target, prices, dict, 35, betas, 0.01)
        self.assertIsNone(u["flip"])                                         # no single ticker does it
        self.assertEqual(u["market"], {-2: {"Y": 1.0}, -1: {"Y": 1.0}})
        self.assertEqual(u["label"], "close call")
        u0 = pc.uncertainty(sim, tree, self.d, self.prev, tr, target, prices, dict, 35, {}, 0.01)
        self.assertEqual((u0["market"], u0["label"]), ({}, "firm"))          # broken: no betas, no market move
        prices2, _ = self.both(a_today=100.8, b_today=100.7)                 # -1 sigma is not enough, -2 is
        sim2, t2, tr2 = sr.run_engine(prices2, tree, self.d)
        u2 = pc.uncertainty(sim2, tree, self.d, self.prev, tr2, t2, prices2, dict, 35, betas, 0.01)
        self.assertEqual((list(u2["market"]), u2["label"]), ([-2], "could flip"))

    def test_stale_dependence(self):
        a = walk_series(60, step=0.01, today=100.7)                          # one-ticker flip at 3.9 sigma: none
        prices = {"A": a, "X": a, "Y": a}
        tree = price_tree()
        sim, target, tr, d, prev = sim_of(prices, tree)
        u = pc.uncertainty(sim, tree, d, prev, tr, target, prices, dict, 35, {}, None, {"A": 300.0})
        self.assertEqual((u["flip"], u["stale_dep"], u["label"]), (None, ["A"], "could flip"))
        u = pc.uncertainty(sim, tree, d, prev, tr, target, prices, dict, 35, {}, None, {"A": 5.0})
        self.assertEqual((u["stale_dep"], u["label"]), ([], "firm"))         # traded 5 minutes ago: no doubt

    def test_label_rule(self):
        self.assertEqual(pc.label({"sigma": 1.0}, {}, []), "close call")     # boundaries are inclusive
        self.assertEqual(pc.label({"sigma": 1.01}, {}, []), "could flip")
        self.assertEqual(pc.label({"sigma": 2.0}, {}, []), "could flip")
        self.assertEqual(pc.label({"sigma": 2.01}, {}, []), "firm")
        self.assertEqual(pc.label(None, {"-1": {}}, []), "close call")
        self.assertEqual(pc.label(None, {2: {}}, []), "could flip")
        self.assertEqual(pc.label(None, {}, ["A"]), "could flip")
        self.assertEqual(pc.label(None, {}, []), "firm")

    def test_market_materiality(self):
        prices, _ = self.both()
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        small = tree_of(cond("A", 100, [mix(X=0.55, Y=0.45)], [cond("B", 100, [mix(X=0.55, Y=0.45)], [mix(X=0.45, Y=0.55)])]))
        sim, target, tr = sr.run_engine(prices, small, self.d)
        u = pc.uncertainty(sim, small, self.d, self.prev, tr, target, prices, dict, 35, betas, 0.01)
        self.assertEqual(u["market"], {})                                    # a 10% change is not material

    def test_market_alternative_through_the_corridor(self):
        prices, _ = self.both()
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        for t in "PQRSTU":
            prices[t] = self.spy
        live = {t: 1 / 6 for t in "PQRSTU"}
        hi, lo = 1 / 6 + 0.09, 1 / 6 - 0.09
        near = [mix(P=hi, Q=hi, R=hi, S=lo, T=lo, U=lo)]
        far = [mix(P=lo, Q=lo, R=lo, S=hi, T=hi, U=hi)]
        end = lambda w: pc.after(w, live, 0.1)                               # noqa: E731
        # both answers sit inside the corridor: no trade either way, nothing to show
        tree = tree_of(cond("A", 100, near, [cond("B", 100, near, far)]))
        sim, target, tr = sr.run_engine(prices, tree, self.d)
        self.assertEqual(pc.uncertainty(sim, tree, self.d, self.prev, tr, end(target), prices, end, 35, betas, 0.01)["market"], {})
        # trade to X now; the market alternative would keep today's holdings, and that is what is shown
        tree = tree_of(cond("A", 100, [asset("X")], [cond("B", 100, [asset("X")], far)]))
        prices["X"] = self.spy
        sim, target, tr = sr.run_engine(prices, tree, self.d)
        u = pc.uncertainty(sim, tree, self.d, self.prev, tr, end(target), prices, end, 35, betas, 0.01)
        self.assertEqual(u["market"][-1], live)

    def test_label_thresholds(self):
        for need, label in ((0.9, "close call"), (1.1, "could flip"), (1.9, "could flip"), (2.1, "firm")):
            a = walk_series(60, step=0.01, today=100 / (1 - need * 0.01 * F35))
            prices = {"A": a, "X": a, "Y": a}
            sim, target, tr, d, prev = sim_of(prices, price_tree())
            u = pc.uncertainty(sim, price_tree(), d, prev, tr, target, prices, dict, 35, {}, None)
            self.assertEqual(u["label"], label, need)

    def test_market_either_way(self):
        prices, tree = self.both(a_today=99.7, b_today=99.8)                 # Y now; a rally makes it X
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        sim, target, tr = sr.run_engine(prices, tree, self.d)
        self.assertEqual(target, {"Y": 1.0})
        u = pc.uncertainty(sim, tree, self.d, self.prev, tr, target, prices, dict, 35, betas, 0.01)
        self.assertEqual(u["market"], {1: {"X": 1.0}, 2: {"X": 1.0}})

    def test_market_through_the_corridor(self):
        prices, tree = self.both()
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        sim, target, tr = sr.run_engine(prices, tree, self.d)
        live = {"X": 0.55, "Y": 0.45}                                        # X or Y both sit 45-55pp off: trade
        end = lambda w: pc.after(w, live, 0.1)                               # noqa: E731
        u = pc.uncertainty(sim, tree, self.d, self.prev, tr, target, prices, end, 35, betas, 0.01)
        self.assertEqual(u["market"], {-2: {"Y": 1.0}, -1: {"Y": 1.0}})
        live = {"X": 0.5, "Y": 0.5}
        swing = tree_of(cond("A", 100, [mix(X=0.55, Y=0.45)], [cond("B", 100, [mix(X=0.55, Y=0.45)], [mix(X=0.45, Y=0.55)])]))
        sim, target, tr = sr.run_engine(prices, swing, self.d)
        end = lambda w: pc.after(w, live, 0.1)                               # noqa: E731
        u = pc.uncertainty(sim, swing, self.d, self.prev, tr, end(target), prices, end, 35, betas, 0.01)
        self.assertEqual(u["market"], {})                                    # inside the corridor: no trade either way

    def test_stale_both_ways_and_no_age(self):
        a = walk_series(60, step=0.01, today=99.3)                           # below the line; only a rise flips it
        prices = {"A": a, "X": a, "Y": a}
        sim, target, tr, d, prev = sim_of(prices, price_tree())
        u = pc.uncertainty(sim, price_tree(), d, prev, tr, target, prices, dict, 35, {}, None, {"A": 300.0})
        self.assertEqual(u["stale_dep"], ["A"])
        u = pc.uncertainty(sim, price_tree(), d, prev, tr, target, prices, dict, 35, {}, None, {"A": None})
        self.assertEqual(u["stale_dep"], ["A"])                              # no trade today: sized as a whole session

    def test_alternatives_reading_stale(self):
        a = walk_series(60, step=0.01, today=100.2)                          # A near its line
        b = walk_series(60, step=0.01, today=150.0)                          # B decides the alternative only
        tree = tree_of(cond("A", 100, [asset("X")], [cond("B", 100, [asset("Y")], [asset("Z")])]))
        prices = {"A": a, "B": b, "X": a, "Y": a, "Z": a}
        sim, target, tr, d, prev = sim_of(prices, tree)
        u = pc.uncertainty(sim, tree, d, prev, tr, target, prices, dict, 35, {}, None, {"B": 60.0})
        self.assertEqual((u["flip"]["instead"], u["alt_stale"], u["stale_dep"]), ({"Y": 1.0}, ["B"], []))
        u = pc.uncertainty(sim, tree, d, prev, tr, target, prices, dict, 35, {}, None, {})
        self.assertEqual(u["alt_stale"], [])

    def test_market_alternative_reading_stale(self):
        prices, tree = self.both()                                           # today's path reads A only
        betas = {t: pc.beta(prices[t], self.spy, self.prev) for t in prices}
        sim, target, tr = sr.run_engine(prices, tree, self.d)
        self.assertEqual(set(sr.trace_tickers(tr, tree)), {"A"})
        u = pc.uncertainty(sim, tree, self.d, self.prev, tr, target, prices, dict, 35, betas, 0.01, {"B": 30.0})
        self.assertIsNone(u["flip"])
        self.assertEqual(u["alt_stale"], ["B"])                              # the market alternative reads B
        u = pc.uncertainty(sim, tree, self.d, self.prev, tr, target, prices, dict, 35, betas, 0.01, {"Q": 30.0})
        self.assertEqual(u["alt_stale"], [])

    def test_beta_on_shared_dates(self):
        m = self.spy
        s = levered(m, 2, 50.0)
        s["2026-10-24"] = 49.0                                               # a Saturday inside the window: no SPY close
        self.assertAlmostEqual(pc.beta(s, m, self.d), 2.0, places=6)

    def test_paused_has_no_flips(self):
        a = walk_series(60, step=0.01, today=100.05)
        prices = {"A": a, "X": a, "Y": a}
        sim, target, tr, d, prev = sim_of(prices, price_tree())
        u = pc.uncertainty(sim, price_tree(), d, prev, tr, target, prices, dict, 35, {}, None, paused=True)
        self.assertEqual(u, {"flip": None, "market": {}, "stale_dep": [], "alt_stale": [], "label": "firm"})


# ------------------------------------------------------------------ P8
class P8EngineRender(unittest.TestCase):
    cfg = {"symphony": "S1", "eras": [{"version": "VERSION0001", "from": "2025-01-01", "tree": "x"}]}

    def row(self, s, drifted=False, corridor=None, a_today=101.0):
        a = walk_series(60, today=a_today)
        d = max(a)
        cfg = dict(self.cfg, corridor=corridor) if corridor else self.cfg
        prices = {"A": a, "X": a, "Y": a, "SPY": a}
        return pc.engine("HG", cfg, price_tree(), prices, d, s, 35, {}, {}, {}, 0.01, drifted), d

    def test_engine(self):
        s = {"holdings": [{"ticker": "Y", "allocation": 1.0}], "value": 1000.0, "last_rebalance_attempted_on": "2099-01-01"}
        r, d = self.row(s)
        self.assertEqual((r["after"], r["live"], r["turnover"], r["moves"]), ({"X": 1.0}, {"Y": 1.0}, 1.0, 1000))
        self.assertNotIn("caveats", r)
        r, _ = self.row(dict(s, last_rebalance_attempted_on="2020-01-01"))
        self.assertIn("2020-01-01", r["caveats"][0])
        r, _ = self.row(None)
        self.assertNotIn("live", r)

    def test_empty_holdings(self):
        r, _ = self.row({"holdings": [], "value": 0.0})
        self.assertEqual(r["status"], "ok")
        self.assertNotIn("live", r)
        self.assertIn("Composer reports no holdings", r["caveats"])
        lines, _ = pc.render(self.ss(), None, [r], {}, [])
        self.assertIn("Composer holdings unavailable", lines[1])

    def test_paused(self):
        s = {"holdings": [{"ticker": "Y", "allocation": 1.0}], "value": 1000.0, "is_paused": True,
             "last_rebalance_attempted_on": "2020-01-01"}
        r, _ = self.row(s, drifted=True)
        self.assertEqual((r["after"], r["moves"], r["label"]), ({"Y": 1.0}, 0, "firm"))
        self.assertEqual(len(r["caveats"]), 2)                               # paused and drift, both kept
        self.assertIn("paused", r["caveats"][0])
        self.assertFalse(any("attempt" in c for c in r["caveats"]))          # a paused symphony never attempts
        r, _ = self.row(dict(s, is_paused=False))                            # broken: not paused
        self.assertEqual(r["after"], {"X": 1.0})

    def test_sigma_ends_yesterday(self):
        a = walk_series(60, today=110.2)
        ds = sorted(a)
        a[ds[-2]] = 100.0                                                    # today's own move is +10%
        prices = {"A": a, "X": a, "Y": a, "SPY": a}
        r = pc.engine("HG", self.cfg, price_tree(110.0), prices, ds[-1], None, 35, {}, {}, {}, 0.01)
        sd_y = pc.daily_sd(a, ds[-2])
        self.assertAlmostEqual(r["flip"]["sigma"], abs(r["flip"]["move"]) / (sd_y * F35), delta=0.02)

    def test_stale_caveat(self):
        a = walk_series(60, today=100.7)
        prices = {"A": a, "X": a, "Y": a, "SPY": a}
        r = pc.engine("HG", self.cfg, price_tree(), prices, max(a), None, 35, {"A": "A 10:00 (no fresh sibling: last price used)"},
                      {"A": 330.0}, {}, 0.01)
        self.assertIn("depends on stale A", r["caveats"])
        self.assertEqual(r["stale"], ["A 10:00 (no fresh sibling: last price used)"])
        r = pc.engine("HG", self.cfg, price_tree(), prices, max(a), None, 35, {}, {}, {}, 0.01)
        self.assertNotIn("caveats", r)

    def test_moves_from_the_outcome(self):
        s = {"holdings": [{"ticker": "X", "allocation": 0.95}, {"ticker": "Y", "allocation": 0.05}], "value": 1000.0}
        r, _ = self.row(s, corridor=0.1)
        self.assertEqual((r["after"], r["moves"], r["max_gap"]), ({"X": 0.95, "Y": 0.05}, 0, 0.05))
        self.assertNotIn("caveats", r)
        s2 = dict(s, holdings=[{"ticker": "X", "allocation": 0.905}, {"ticker": "Y", "allocation": 0.095}])
        r, _ = self.row(s2, corridor=0.1)
        self.assertEqual(r["label"], "close call")                           # 9.5pp: the trigger is on the line
        self.assertIn("trigger is on the line", r["caveats"][0])
        line = pc.render(self.ss(), None, [dict(r, corridor=0.1)], {}, [])[0][1]
        self.assertEqual(line.count("9.5%"), 1)                               # said once, in the caveat
        self.assertNotIn("largest gap 9.5% vs", line)

    def ss(self):
        return {"date": "2026-10-28", "now": "15:15", "decide": "15:50", "left": 35, "open": "09:30", "close": "16:00"}

    def g(self, **kw):
        base = {"spy": 700.0, "sma": 650.0, "flip_at": 649.7, "open": True, "open_prev": True, "dist": -0.0719,
                "day": -0.005, "sigma": 25.0}
        return dict(base, **kw)

    def test_alerts(self):
        self.assertEqual(pc.render(self.ss(), self.g(), [], {}, [])[1], [])
        a = pc.render(self.ss(), self.g(open=True, open_prev=False), [], {}, [], sides=[{"QLD": 1.0}, {"BIL": 1.0}])[1]
        self.assertTrue(a[0].startswith("GATE REOPENS"))
        self.assertIn("HG holds QLD 100% above the line and BIL 100% below it", a[0])
        a = pc.render(self.ss(), self.g(open=False, open_prev=True), [], {}, [], sides=[{"QLD": 1.0}, {"QLD": 1.0}])[1]
        self.assertTrue(a[0].startswith("GATE CLOSES"))
        self.assertIn("QLD 100% on either side of the line", a[0])           # the dip-buy branch ignores the gate
        self.assertNotIn("moves to BIL", a[0])
        a = pc.render(self.ss(), self.g(sigma=1.5), [], {}, [], sides=[{"QLD": 1.0}, {"BIL": 1.0}])[1]
        self.assertTrue(a[0].startswith("GATE ON THE LINE") and "closes" in a[0])
        self.assertIn("HG holds QLD 100% above the line and BIL 100% below it", a[0])
        self.assertTrue(pc.render(self.ss(), self.g(sigma=2.0), [], {}, [])[1][0].startswith("GATE ON THE LINE"))   # inclusive
        self.assertTrue(pc.render(self.ss(), self.g(day=-0.02), [], {}, [])[1][0].startswith("BIG DAY"))          # inclusive
        a = pc.render(self.ss(), self.g(open=False, open_prev=False, dist=0.004, sigma=1.5), [], {}, [])[1]
        self.assertTrue(a[0].startswith("GATE ON THE LINE") and "reopens" in a[0])
        self.assertEqual(pc.render(self.ss(), self.g(sigma=2.5), [], {}, [])[1], [])
        self.assertEqual(pc.render(self.ss(), self.g(open=False, open_prev=False, dist=0.08, sigma=30.0), [], {}, [])[1], [])
        for day in (-0.021, 0.021):
            a = pc.render(self.ss(), self.g(day=day), [], {}, [])[1]
            self.assertTrue(a[0].startswith("BIG DAY"), day)
        self.assertEqual(pc.render(self.ss(), self.g(day=0.019), [], {}, [])[1], [])

    def test_lines(self):
        same = {"engine": "HG", "status": "ok", "live": {"X": 1.0}, "after": {"X": 1.0}, "value": 1000.0, "moves": 0,
                "flip": None, "market": {}, "label": "firm", "stale": []}
        move = dict(same, after={"Y": 1.0}, moves=1000, flip={"ticker": "A", "move": -0.01, "sigma": 0.7, "instead": {"X": 1.0}},
                    market={"-1": {"X": 1.0}, "-2": {"X": 1.0}, "2": {"Z": 1.0}}, label="close call",
                    stale=["A 14:25 (no fresh sibling: last price used)", "B 14:25 -> via IVV"])
        bad = {"engine": "KMLM", "status": "unavailable", "note": "no close"}
        notes = {"A": "A 14:25 (no fresh sibling: last price used)", "B": "B 14:25 -> via IVV", "C": "C 14:25 -> via IVV",
                 "D": "D 14:25 (no fresh sibling: last price used)"}
        lines, _ = pc.render(self.ss(), self.g(), [same, move, bad], notes, [], spy_move=0.002)
        self.assertIn("no change (X 100%)", lines[2])
        self.assertIn("firm: no 2-sigma market move", lines[2])
        self.assertIn("X 100% -> Y 100% ($1,000 moves). close call: market +2 sigma (SPY +0.40%) -> Z 100%; "
                      "market -1/-2 sigma (SPY -0.20/-0.40%) -> X 100%; A -1.00% (0.7 sigma) -> X 100%", lines[3])
        self.assertIn("stale: A 14:25 (no fresh sibling", lines[3])
        self.assertNotIn("B 14:25", lines[3])                                # exact rebuilds go to the footer
        self.assertIn("unavailable: no close", lines[4])
        self.assertIn("rebuilt from same-index funds: B, C via IVV", lines[5])
        self.assertIn("1 more stale price(s), on tickers no decision reads today: D", lines[6])   # C is in the line above
        self.assertEqual(len(lines), 7)


# ------------------------------------------------------------------ P9
class PreviewBase(unittest.TestCase):
    """the frozen 2026-10-28 closes as if they were 15:15 prices; no tests of its own"""
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE) as f:
            cls.fx = json.load(f)

    def setUp(self):
        self.now = et(2026, 10, 28, 15, 15)
        self.period = {"start": ts(et(2026, 10, 28, 9, 30)), "end": ts(et(2026, 10, 28, 16, 0))}
        self.stale, self.extra, self.down, self.no_today = {}, {}, False, False
        self.quotes = None                   # None: no FMP key (the suite pops it), Yahoo's prices alone
        self.cut = {}                        # {ticker: dates missing from Yahoo's history}

    def fetch(self, t):
        if self.down:
            raise RuntimeError("Yahoo down")
        s = self.fx["prices"].get(t) or self.extra.get(t)
        if s is None:
            raise RuntimeError("no such ticker")
        s = {d: v for d, v in s.items() if d not in self.cut.get(t, ())}
        a, r, meta = feed(s, self.now, 60 if t in self.stale else 2, today=not self.no_today)
        if t in self.stale:
            a[max(a)] = r[max(r)] = self.stale[t]
        meta["currentTradingPeriod"] = {"regular": self.period}
        return a, r, meta

    def meta(self, overrides=None, drop=None):
        man = sr.load_manifest()
        out = []
        for eng, cfg in man.items():
            if eng == drop:
                continue
            w = (overrides or {}).get(eng) or self.fx["expected"][eng]["2026-10-28"]
            out.append({"id": cfg["symphony"], "value": 10000.0, "last_rebalance_attempted_on": "2026-10-27",
                        "holdings": [{"ticker": t, "allocation": x} for t, x in w.items()]})
        return out

    def run_preview(self, now=None, meta=None, drift=None, drop=None):
        def get_meta():
            if meta == "down":
                raise SystemExit("error: HTTP 503\nService Unavailable")
            return self.meta(meta, drop)
        return pc.preview(now or self.now, get_meta, (lambda c: drift) if drift else None, fetch=self.fetch,
                          quotes=self.quotes)


class P9Preview(PreviewBase):
    """end to end on the frozen 2026-10-28 closes as if they were 15:15 prices (Yahoo's alone)"""
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
        self.assertEqual(len(g["sides"]), 2)
        lines, _, _ = self.run_preview(meta={"HG": {"QLD": 1.0}})            # broken: Composer in QLD
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

    def test_held_only_stale_not_on_the_engine_line(self):
        self.stale = {"PULS": self.fx["prices"]["PULS"][max(self.fx["prices"]["PULS"])]}
        lines, _, _ = self.run_preview()
        harv = next(x for x in lines if x.startswith("HARV"))
        self.assertNotIn("PULS 14", harv)                                    # held, never read by a condition
        self.assertTrue(any("on tickers no decision reads today: PULS" in x for x in lines), lines)
        self.stale = {"UVXY": self.fx["prices"]["UVXY"][max(self.fx["prices"]["UVXY"])]}   # a decision ticker
        rows = {r["engine"]: r for r in self.run_preview()[2]}
        self.assertTrue(any(n.startswith("UVXY") for n in rows["HARV"]["stale"]))

    def test_quote_age_widens_sigma(self):
        lines, _, led = self.run_preview()
        g = led[0]
        self.assertEqual(g["lag"], 2.0)                                      # the fixture's quotes are 2 minutes old
        self.assertIn("(35 min; quotes ~2 min old)", lines[0])
        thr, spy = g["flip_at"], g["spy"]
        sd = g["spy_sd"]
        self.assertAlmostEqual(g["sigma"], abs(thr / spy - 1) / (sd * pc.sigma_factor(37)), delta=0.05)
        self.assertEqual(g["sd_day"], "2026-10-27")                           # sigma and betas end yesterday
        self.extra["IVV"] = {d: p * 0.9 for d, p in self.fx["prices"]["SPY"].items()}
        self.stale = {"SPY": 700.0}                                          # today's SPY moved hard (rebuilt): same sigma
        g2 = self.run_preview()[2][0]
        self.assertEqual(g2["spy_sd"], sd)

    def test_market_move_and_betas_recorded(self):
        g = self.run_preview()[2][0]
        self.assertAlmostEqual(g["spy_move"], g["spy_sd"] * pc.sigma_factor(37), places=6)
        self.assertAlmostEqual(g["betas"]["SPY"], 1.0, places=3)
        self.assertLess(g["betas"]["SQQQ"], -2)
        beta0 = g["betas"]["UVXY"]
        self.stale = {"UVXY": self.fx["prices"]["UVXY"][max(self.fx["prices"]["UVXY"])] * 3}   # today's UVXY x3
        self.assertEqual(self.run_preview()[2][0]["betas"]["UVXY"], beta0)    # betas end yesterday

    def test_sibling_only_funds_not_reported(self):
        self.extra["IVV"] = {d: p * 0.9 for d, p in self.fx["prices"]["SPY"].items()}
        self.stale = {"SPY": 700.0, "IVV": 600.0}                             # IVV fetched only as a sibling, stale too
        lines = self.run_preview()[0]
        self.assertFalse(any("IVV" in x for x in lines), lines)
        self.assertTrue(any("SPY" in x and "via SSO" in x for x in lines), lines)

    def test_stale_spy_widens_the_gate(self):
        self.stale = {t: self.fx["prices"][t][max(self.fx["prices"][t])] for t in ("SPY", "SSO", "SPXL", "UPRO")}
        g = self.run_preview()[2][0]                                         # SPY carried, 60 minutes old
        self.assertAlmostEqual(g["sigma"], abs(g["flip_at"] / g["spy"] - 1) / (g["spy_sd"] * pc.sigma_factor(35 + 2 + 60)),
                               delta=0.05)

    def test_failure_lines(self):
        def fetch(t):
            if t == "VOOV":
                raise RuntimeError("Yahoo VOOV: timed out")
            return self.fetch(t)
        lines = pc.preview(self.now, lambda: self.meta(), fetch=fetch)[0]
        self.assertTrue(any("Yahoo VOOV: timed out" in x for x in lines), lines)
        self.assertFalse(any("Yahoo VOOV: Yahoo VOOV" in x for x in lines))
        self.extra["VIXY"] = {d: p for d, p in self.fx["prices"]["VIXM"].items()}
        self.stale = {"VXZ": 1.0}                                            # held only, rebuilt exactly from VIXM
        lines = self.run_preview()[0]
        self.assertTrue(any("VXZ via VIXM" in x for x in lines), lines)
        self.assertFalse(any("decision reads today: VXZ" in x for x in lines))

    def test_composer_down(self):
        lines, alerts, led = self.run_preview(meta="down")
        self.assertTrue(any("Composer holdings: error: HTTP 503 Service Unavailable" in x for x in lines), lines)
        self.assertFalse(any(x.strip() == "Service Unavailable" for x in lines))
        self.assertTrue(all(r.get("status") == "ok" and "live" not in r for r in led if r["engine"] != "GATE"))
        self.assertEqual(alerts, [])

    def test_symphony_missing(self):
        lines, _, _ = self.run_preview(drop="HARV")
        self.assertTrue(any("HARV is not in Composer's symphony list" in x for x in lines))

    def test_yahoo_down(self):
        self.down = True
        lines, alerts, led = self.run_preview()
        self.assertTrue(alerts and alerts[-1].startswith("PRE-CLOSE UNAVAILABLE"))
        self.assertEqual(led, [])
        self.down = False                                                    # broken: Yahoo up
        _, alerts, _ = self.run_preview()
        self.assertFalse(any(a.startswith("PRE-CLOSE UNAVAILABLE") for a in alerts))

    def test_no_trading_today(self):
        self.no_today = True
        lines, alerts, led = self.run_preview()
        self.assertTrue(alerts[-1].startswith("PRE-CLOSE UNAVAILABLE") and "show a trade today" in alerts[-1])
        self.assertEqual(led, [])

    def test_unavailable_gate_or_engines(self):
        saved = (pc.gate, sr.run_engine)
        try:
            pc.gate = lambda *a, **k: None                                   # no gate reading, engines fine
            self.assertTrue(self.run_preview()[1][-1].startswith("PRE-CLOSE UNAVAILABLE"))
            pc.gate = saved[0]
            sr.run_engine = lambda *a, **k: (None, None, "boom")             # gate fine, every engine down
            self.assertTrue(self.run_preview()[1][-1].startswith("PRE-CLOSE UNAVAILABLE"))
        finally:
            pc.gate, sr.run_engine = saved
        self.assertFalse(any(a.startswith("PRE-CLOSE UNAVAILABLE") for a in self.run_preview()[1]))

    def test_drift(self):
        lines, _, led = self.run_preview(drift=({"KMLM"}, ["logic-drift check for HG unavailable (timed out)"]))
        rows = {r["engine"]: r for r in led}
        self.assertTrue(any("live logic differs" in c for c in rows["KMLM"]["caveats"]))
        self.assertNotIn("caveats", rows["HG"])
        self.assertTrue(any("logic-drift check for HG unavailable" in x for x in lines))

    def test_holiday_list_end(self):
        saved = sr.NYSE_HOLIDAYS
        try:
            sr.NYSE_HOLIDAYS = {"2025-12-25"}
            self.assertTrue(any("holiday and half-day lists end" in x for x in self.run_preview()[0]))
        finally:
            sr.NYSE_HOLIDAYS = saved
        self.assertFalse(any("holiday and half-day lists end" in x for x in self.run_preview()[0]))

    def test_closed_hours(self):
        lines, alerts, led = self.run_preview(now=et(2026, 10, 28, 16, 5))
        self.assertIn("closed at 16:00", lines[0])
        self.assertIn("closed at 16:00", self.run_preview(now=et(2026, 10, 28, 16, 0))[0][0])   # 16:00 itself is closed
        self.assertEqual((alerts, led), ([], []))
        lines, _, _ = self.run_preview(now=et(2026, 10, 28, 9, 0))
        self.assertIn("opens at 09:30", lines[0])
        lines, _, _ = self.run_preview(now=et(2026, 10, 31, 15, 15))
        self.assertIn("no session today", lines[0])
        self.period = {"start": ts(et(2026, 10, 28, 9, 30)), "end": ts(et(2026, 10, 28, 13, 0))}   # a half-day
        lines, _, _ = self.run_preview()
        self.assertIn("closed at 13:00", lines[0])


# ------------------------------------------------------------------ P10
class P10LedgerExit(unittest.TestCase):
    def test_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "sub", "l.jsonl")
            pc.append_ledger([{"engine": "GATE"}, {"engine": "HG"}], p)
            pc.append_ledger([{"engine": "GATE"}], p)
            with open(p) as f:
                rows = [json.loads(x) for x in f]
            self.assertEqual([r["engine"] for r in rows], ["GATE", "HG", "GATE"])

    def run_main(self, fake):
        saved = pc.preview
        out = io.StringIO()
        try:
            pc.preview = fake
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
                pc.main()
        finally:
            pc.preview = saved
        return cm.exception.code, out.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self.run_main(lambda *a, **k: (["x"], [], []))[0], 0)
        self.assertEqual(self.run_main(lambda *a, **k: (["x"], ["GATE CLOSES"], []))[0], 2)

    def test_crash_alerts(self):
        def boom(*a, **k):
            raise KeyError("SPY")
        code, out = self.run_main(boom)
        self.assertEqual(code, 2)
        self.assertIn("PRE-CLOSE UNAVAILABLE — the preview failed: KeyError('SPY')", out)


# ------------------------------------------------------------------ P11
class P11Merge(unittest.TestCase):
    """FMP's 1-minute bar as today's price unless Yahoo's last sale is over a minute newer; Yahoo's
    history kept; nothing from the run's future; disagreements only between prices of one moment"""
    T = "2026-10-28"

    def setUp(self):
        self.now = et(2026, 10, 28, 15, 15)

    def at(self, minutes=0, seconds=0, days=0):
        return self.now - datetime.timedelta(minutes=minutes, seconds=seconds, days=days)

    def yahoo(self, when, today=True, price=100.0):
        adj = {"2026-10-26": 98.0, "2026-10-27": 99.0}
        if today:
            adj[self.T] = price
        return adj, dict(adj), {"regularMarketTime": ts(when)}

    def merge(self, y, q):
        return pc.merge_quotes({"SPY": y}, {"SPY": q} if q else {}, self.T, self.now)

    def test_fmp_unless_yahoo_a_minute_newer(self):
        y = self.yahoo(self.at(2))
        out, src, _ = self.merge(y, (100.1, self.at(1)))
        adj, raw, meta = out["SPY"]
        self.assertEqual((adj[self.T], raw[self.T], src["SPY"]), (100.1, 100.1, "fmp"))
        self.assertEqual(meta["regularMarketTime"], ts(self.at(1)))
        self.assertEqual((adj["2026-10-27"], y[0][self.T]), (99.0, 100.0))           # history kept, input untouched
        _, src, _ = self.merge(self.yahoo(self.at(1)), (100.1, self.at(1, 30)))
        self.assertEqual(src["SPY"], "fmp")                                         # 30 s older: the same moment
        out, src, _ = self.merge(self.yahoo(self.at(1)), (100.1, self.at(3)))       # broken: 2 minutes older
        self.assertEqual((out["SPY"][0][self.T], src["SPY"]), (100.0, "yahoo"))
        self.assertEqual(out["SPY"][2]["regularMarketTime"], ts(self.at(1)))

    def test_only_today_and_never_the_future(self):
        _, src, _ = self.merge(self.yahoo(self.at(30)), (101.0, self.at(1, days=1)))
        self.assertEqual(src["SPY"], "yahoo")                                       # yesterday's bar
        _, src, _ = self.merge(self.yahoo(self.at(30)), (101.0, self.at(-45)))
        self.assertEqual(src["SPY"], "yahoo")                                       # 45 minutes after the run: a replay
        _, src, _ = self.merge(self.yahoo(self.at(30)), (101.0, self.at(-1)))
        self.assertEqual(src["SPY"], "fmp")                                         # a minute of clock skew is tolerated
        _, src, _ = self.merge(self.yahoo(self.at(30)), (101.0, self.at(1)))
        self.assertEqual(src["SPY"], "fmp")                                         # broken: a past bar

    def test_yahoo_from_the_future_dropped(self):
        out, src, _ = self.merge(self.yahoo(self.at(-30)), None)                    # a replay: Yahoo shows the close
        self.assertNotIn(self.T, out["SPY"][0])
        out, src, _ = self.merge(self.yahoo(self.at(-30)), (100.2, self.at(1)))
        self.assertEqual((out["SPY"][0][self.T], src["SPY"]), (100.2, "fmp"))
        out, _, _ = self.merge(self.yahoo(self.at(2)), None)                        # broken: Yahoo's own past
        self.assertEqual(out["SPY"][0][self.T], 100.0)

    def test_today_injected_when_yahoo_has_none(self):
        out, src, _ = self.merge(self.yahoo(self.at(1), today=False), (100.3, self.at(1)))
        self.assertEqual((out["SPY"][0][self.T], src["SPY"]), (100.3, "fmp"))
        self.assertEqual(pc.freshness(out, self.T, self.now), ({"SPY": 100.3}, {}))
        out, _, _ = self.merge(self.yahoo(self.at(1), today=False), (100.3, self.at(1, days=1)))
        self.assertNotIn(self.T, out["SPY"][0])                                     # broken: yesterday's bar

    def test_disagreement_at_one_moment_only(self):
        _, _, diff = self.merge(self.yahoo(self.at(1, 30)), (100.5, self.at(1)))
        self.assertEqual(diff, [("SPY", 100.5, "15:14:00", 100.0, "15:13:30")])
        _, _, diff = self.merge(self.yahoo(self.at(1, 30)), (99.5, self.at(1)))
        self.assertEqual(len(diff), 1)                                              # either way
        _, _, diff = self.merge(self.yahoo(self.at(1, 30)), (100.25, self.at(1)))
        self.assertEqual(diff, [])                                                  # within 0.3%
        _, src, diff = self.merge(self.yahoo(self.at(6)), (100.5, self.at(1)))
        self.assertEqual((diff, src["SPY"]), ([], "fmp"))                           # 5 minutes apart: the market moved
        _, _, diff = self.merge(self.yahoo(self.at(20)), (100.5, self.at(1)))
        self.assertEqual(diff, [])                                                  # Yahoo stale


    def test_previous_session(self):
        self.assertEqual(pc.previous_session("2026-10-28"), "2026-10-27")
        self.assertEqual(pc.previous_session("2026-11-02"), "2026-10-30")             # over a weekend
        self.assertEqual(pc.previous_session("2026-11-27"), "2026-11-25")             # over Thanksgiving
        self.assertNotEqual(pc.previous_session("2026-11-27"), "2026-11-26")          # broken: the holiday itself


class P11Minutes(unittest.TestCase):
    """the FMP source: each ticker's last 1-minute bar ending at or before the run"""
    def bars(self, base=100.0):
        return {f"15:{m:02d}": base + m for m in range(10, 21)}

    def test_last_bar_at_or_before_now(self):
        asked = []

        def fetch(t, d, key):
            asked.append((t, d, key))
            return self.bars(500.0 if t == "SPY" else 50.0)
        q, probs = pc.minute_quotes({"SPY", "QQQ"}, et(2026, 10, 28, 15, 15) + datetime.timedelta(seconds=30), "K", fetch)
        self.assertEqual(q["SPY"], (514.0, et(2026, 10, 28, 15, 15)))                # the 15:14 bar, ending 15:15
        self.assertEqual((q["QQQ"][0], probs), (64.0, {}))
        self.assertEqual(asked[0], ("SPY", "2026-10-28", "K"))                     # SPY first, today's ET date
        q, _ = pc.minute_quotes({"SPY"}, et(2026, 10, 28, 15, 20) + datetime.timedelta(seconds=30), "K", fetch)
        self.assertEqual(q["SPY"][0], 519.0)                                        # broken: a later run, a later bar
        asked.clear()
        pc.minute_quotes({"SPY"}, datetime.datetime(2026, 10, 29, 0, 30, tzinfo=UTC), "K", fetch)
        self.assertEqual(asked[0][1], "2026-10-28")                                 # 20:30 ET is still the 28th

    def test_spy_first_or_nothing(self):
        asked = []

        def none_for_spy(t, d, key):
            asked.append(t)
            return {} if t == "SPY" else self.bars()
        with self.assertRaises(RuntimeError) as cm:
            pc.minute_quotes({"SPY", "QQQ"}, et(2026, 10, 28, 15, 15), "K", none_for_spy)
        self.assertIn("no SPY 1-minute bar for 2026-10-28", str(cm.exception))
        self.assertEqual(asked, ["SPY"])                                            # nothing else asked

        def refused(t, d, key):
            asked.append(t)
            raise RuntimeError("FMP SPY 2026-10-28: unexpected answer {'Error Message': 'Limit Reach'}")
        asked.clear()
        with self.assertRaises(RuntimeError):
            pc.minute_quotes({"SPY", "QQQ"}, et(2026, 10, 28, 15, 15), "K", refused)
        self.assertEqual(asked, ["SPY"])
        asked.clear()                                                                # broken: SPY fine
        pc.minute_quotes({"SPY", "QQQ"}, et(2026, 10, 28, 15, 15), "K", lambda t, d, k: asked.append(t) or self.bars())
        self.assertEqual(sorted(asked), ["QQQ", "SPY"])

    def test_problems_and_odd_rows(self):
        def fetch(t, d, key):
            if t == "BAD":
                raise RuntimeError("FMP BAD 2026-10-28: timed out")
            if t == "THIN":
                return {}
            if t == "ODD":
                return {"15:11": 7, "_close": "16:00", "15:12": None, "15:13": True, "15:14": -1.0, "xx": 3.0,
                        "15:59": 9.0}                                                # an int close; junk; a later bar
            return self.bars()
        q, probs = pc.minute_quotes({"SPY", "BAD", "THIN", "ODD"}, et(2026, 10, 28, 15, 15), "K", fetch)
        self.assertEqual(probs, {"BAD": "FMP BAD 2026-10-28: timed out", "THIN": "no bar today"})
        self.assertEqual(q["ODD"], (7.0, et(2026, 10, 28, 15, 12)))                 # the int kept, junk and the future not
        self.assertIsInstance(q["ODD"][0], float)
        self.assertEqual(sorted(q), ["ODD", "SPY"])

    def test_fetch_reads_fmp_minutes(self):
        urls = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout=None):
            urls.append(req.full_url)
            return Resp(json.dumps([{"date": "2026-10-28 15:14:00", "close": 690.5}]).encode())
        with unittest.mock.patch.object(sr.urllib.request, "urlopen", urlopen), unittest.mock.patch.object(sr.time, "sleep"):
            q, _ = pc.minute_quotes({"SPY"}, et(2026, 10, 28, 15, 15) + datetime.timedelta(seconds=5), "SECRETKEY")
        self.assertEqual(q["SPY"][0], 690.5)
        u = urllib.parse.urlparse(urls[0])
        self.assertEqual((u.scheme, u.netloc, u.path), ("https", "financialmodelingprep.com", "/stable/historical-chart/1min"))
        args = urllib.parse.parse_qs(u.query)
        self.assertEqual((args["symbol"], args["from"], args["to"]), (["SPY"], ["2026-10-28"], ["2026-10-28"]))

    def test_key_from_the_environment(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FMP_API_KEY", None)
            self.assertIsNone(pc.fmp_quotes())
            os.environ["FMP_API_KEY"] = "ENVKEY"
            seen = []
            with unittest.mock.patch.object(pc, "minute_quotes", lambda t, now, k: seen.append(k) or ({}, {})):
                pc.fmp_quotes()({"SPY"}, et(2026, 10, 28, 15, 15))
            self.assertEqual(seen, ["ENVKEY"])


class P11Preview(PreviewBase):
    """the preview end to end with FMP minutes (the frozen 2026-10-28 closes as 15:15 prices)"""
    def setUp(self):
        super().setUp()
        self.asked = []

    def fmp(self, age=1, only=None, scale=None, days_back=0, fail=None, probs=None):
        def quotes(tickers, now):
            self.asked.append((set(tickers), now))
            if fail:
                raise RuntimeError(fail)
            out = {}
            for t in tickers:
                s = self.fx["prices"].get(t) or self.extra.get(t)
                if s is None or (only is not None and t not in only):
                    continue
                out[t] = (s[max(s)] * (scale or {}).get(t, 1.0), now - datetime.timedelta(minutes=age, days=days_back))
            return out, dict(probs or {})
        return quotes

    def test_stale_yahoo_rescued(self):
        self.stale = {t: self.fx["prices"][t][max(self.fx["prices"][t])] * 0.9 for t in ("SPY", "SSO", "SPXL", "UPRO")}
        self.quotes = self.fmp()
        lines, _, led = self.run_preview()
        g = led[0]
        self.assertAlmostEqual(g["spy"], 772.31, places=2)
        self.assertNotIn("stale", g)
        self.assertEqual(g["lag"], 1.0)                                             # FMP's bars end a minute ago
        self.assertEqual((g["quotes"]["failed"], g["quotes"]["yahoo"], g["quotes"]["source"]), (None, [], "fmp-1m"))
        self.assertTrue(any("SSO" in a for a in self.asked[0][0]))                   # one call, siblings included
        self.assertEqual((len(self.asked), self.asked[0][1]), (1, self.now))
        self.quotes = self.fmp(days_back=1)                                         # broken: yesterday's bars
        lines, _, led = self.run_preview()
        self.assertAlmostEqual(led[0]["spy"], 772.31 * 0.9, places=2)
        self.assertIn("no fresh sibling", led[0]["stale"])
        self.assertIn("SPY", led[0]["quotes"]["yahoo"])

    def test_sibling_bar_used(self):
        self.extra["IVV"] = {d: p * 0.9 for d, p in self.fx["prices"]["SPY"].items()}
        self.stale = {t: self.fx["prices"][t][max(self.fx["prices"][t])] * 0.9 for t in ("SPY", "SSO", "SPXL", "UPRO")}
        self.stale["IVV"] = 600.0
        self.quotes = self.fmp(only={"IVV"})
        g = self.run_preview()[2][0]
        self.assertAlmostEqual(g["spy"], 772.31, places=1)
        self.assertIn("via IVV", g["stale"])
        self.quotes = self.fmp(only=set())                                          # broken: no IVV bar
        self.assertIn("no fresh sibling", self.run_preview()[2][0]["stale"])

    def test_market_trading_on_fmp(self):
        self.no_today = True
        self.quotes = self.fmp()
        lines, alerts, led = self.run_preview()
        self.assertFalse(any(a.startswith("PRE-CLOSE UNAVAILABLE") for a in alerts), alerts)
        self.assertAlmostEqual(led[0]["spy"], 772.31, places=2)
        self.quotes = self.fmp(days_back=1)                                         # broken: no trade today on FMP either
        _, alerts, _ = self.run_preview()
        self.assertTrue(alerts[-1].startswith("PRE-CLOSE UNAVAILABLE") and "show a trade today" in alerts[-1])

    def test_yahoo_history_must_reach_the_previous_session(self):
        self.quotes = self.fmp()
        self.cut = {"SPY": {"2026-10-27"}}                                          # Yahoo's SPY stops at 10-26
        lines, alerts, led = self.run_preview()
        self.assertEqual(led, [])
        self.assertIn("Yahoo's SPY history ends 2026-10-26, not the previous session 2026-10-27", alerts[-1])
        self.cut = {"QLD": {"2026-10-27"}}                                          # one fund short: named, not fatal
        lines, alerts, led = self.run_preview()
        self.assertTrue(any("before the previous session 2026-10-27 for QLD" in x for x in lines), lines)
        self.assertEqual(led[0]["quotes"]["short"], ["QLD"])
        self.cut = {}                                                               # broken: complete history
        lines, alerts, led = self.run_preview()
        self.assertFalse(any("previous session" in x for x in lines + alerts))
        self.assertEqual(led[0]["quotes"]["short"], [])

    def test_disagreement_in_the_report(self):
        self.quotes = self.fmp(scale={"TQQQ": 1.01})                                # FMP 15:14, Yahoo 15:13: one moment
        lines, _, led = self.run_preview()
        dis = [x for x in lines if x.startswith("FMP and Yahoo disagree")]
        self.assertEqual(len(dis), 1, lines)
        self.assertIn("TQQQ", dis[0])
        self.assertEqual([d[0] for d in led[0]["quotes"]["disagree"]], ["TQQQ"])
        self.quotes = self.fmp()                                                    # broken: they agree
        lines, _, led = self.run_preview()
        self.assertFalse(any(x.startswith("FMP and Yahoo disagree") for x in lines))

    def test_fmp_down(self):
        self.quotes = self.fmp(fail="no SPY 1-minute bar for 2026-10-28 up to 15:15 ET")
        lines, alerts, led = self.run_preview()
        self.assertTrue(any("FMP 1-minute bars (no SPY 1-minute bar" in x and "Yahoo's prices used" in x for x in lines), lines)
        self.assertFalse(any(a.startswith("PRE-CLOSE UNAVAILABLE") for a in alerts))
        self.assertEqual(led[0]["lag"], 2.0)
        self.assertTrue(led[0]["quotes"]["failed"].startswith("no SPY 1-minute bar"))
        self.assertFalse(any(x.startswith("live prices: FMP") for x in lines))
        self.quotes = self.fmp()                                                    # broken: FMP up
        lines, _, led = self.run_preview()
        self.assertTrue(any(x.startswith("live prices: FMP 1-minute bars for") for x in lines))
        self.assertIsNone(led[0]["quotes"]["failed"])

    def test_problems_named(self):
        self.quotes = self.fmp(only=set(self.fx["prices"]) - {"UVXY"}, probs={"UVXY": "no bar today"})
        lines, _, led = self.run_preview()
        line = next(x for x in lines if x.startswith("live prices:"))
        self.assertIn("Yahoo's last sale for UVXY (FMP: UVXY no bar today;", line)
        self.assertEqual(led[0]["quotes"]["problems"], {"UVXY": "no bar today"})
        self.quotes = self.fmp()                                                    # broken: no problem
        line = next(x for x in self.run_preview()[0] if x.startswith("live prices:"))
        self.assertNotIn("FMP:", line)

    def test_no_key_off_and_default(self):
        lines, _, led = self.run_preview()                                          # the suite has no key
        self.assertIn("live prices: Yahoo's last sale (FMP_API_KEY not set)", lines)
        self.assertEqual((led[0]["quotes"]["failed"], led[0]["quotes"]["source"]), ("FMP_API_KEY not set", None))
        seen = []

        def fake(tickers, now, key):
            seen.append(key)
            return self.fmp()(tickers, now)
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "ENVKEY"}), \
                unittest.mock.patch.object(pc, "minute_quotes", fake):
            self.quotes = False                                                      # off, though a key is set
            lines, _, led = self.run_preview()
            self.assertEqual(seen, [])
            self.assertIn("live prices: Yahoo's last sale (FMP quotes off)", lines)
            self.quotes = None                                                       # broken: the default, as main() calls it
            lines, _, led = self.run_preview()
            self.assertEqual(seen, ["ENVKEY"])
            n = led[0]["quotes"]["fmp"]
            self.assertGreater(n, 20)
            self.assertIn(f"live prices: FMP 1-minute bars for {n} of {n}", lines)

    def test_counts_over_tickers_with_prices(self):
        def fetch(t):
            if t == "VOOV":
                raise RuntimeError("Yahoo VOOV: timed out")
            return self.fetch(t)
        self.quotes = self.fmp()
        lines, _, led = pc.preview(self.now, lambda: self.meta(), fetch=fetch, quotes=self.quotes)
        line = next(x for x in lines if x.startswith("live prices:"))
        n = led[0]["quotes"]["fmp"]
        self.assertTrue(line.startswith(f"live prices: FMP 1-minute bars for {n} of {n}"), line)
        self.assertIn("none for VOOV", line)
        self.assertEqual(led[0]["quotes"]["none"], ["VOOV"])
        line = next(x for x in self.run_preview()[0] if x.startswith("live prices:"))
        self.assertNotIn("none for", line)                                           # broken: every ticker priced

    def test_quotes_record(self):
        self.quotes = self.fmp()
        led = self.run_preview()[2]
        det = led[0]["quotes"]["detail"]
        self.assertEqual(det["SPY"]["used"], "fmp")
        self.assertEqual(det["SPY"]["fmp"][1], "15:14:00")
        self.assertEqual(det["SPY"]["yahoo"][1], "15:13:00")
        self.assertNotIn("PULS", det)                                               # held only: no decision reads it
        with unittest.mock.patch.object(pc, "gate", lambda *a, **k: None):           # no gate reading: first row
            led = self.run_preview()[2]
        self.assertNotEqual(led[0]["engine"], "GATE")
        self.assertEqual(led[0]["quotes"]["source"], "fmp-1m")

    def test_older_fmp_named(self):
        self.quotes = self.fmp(age=5)                                               # Yahoo's 2-minute sales are 3 newer
        lines, _, led = self.run_preview()
        self.assertEqual(led[0]["quotes"]["fmp"], 0)
        self.assertTrue(any(x.startswith("live prices: FMP 1-minute bars for 0 of") and "Yahoo's last sale for" in x
                            for x in lines), lines)
        self.assertEqual(led[0]["lag"], 2.0)
        self.quotes = self.fmp(age=1)                                               # broken: FMP's newer
        _, _, led = self.run_preview()
        self.assertEqual(led[0]["lag"], 1.0)


if __name__ == "__main__":
    unittest.main()
