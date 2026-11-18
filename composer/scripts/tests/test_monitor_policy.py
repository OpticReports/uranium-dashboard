"""Gate tests for the monitor's POLICY checks after the owner's 2026-11-18 decision (HARV's capital moves
pro rata into the other three engines; the crash sleeve is one engine sized by its target weight).

  P1  the concentration cap is 44% of the whole book (symphonies + cash), strictly above
  P2  the breach line names the new targets, never 29/29/27/15
  P3  HARV (retiring) never raises a cap breach
  P4  the sleeve's recorded share is its share of the Composer symphonies; nothing outside is counted
  P5  the family-book band is off by default: --band-lo / --band-hi default to None and
      --ibkr-equities to 0, so no SLEEVE BAND BREACH is raised unless a band is passed explicitly

Run: python3 -m unittest composer.scripts.tests.test_monitor_policy -v
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import monitor  # noqa: E402

HG, KM, SL, HV = "mbkiXcuNDjueXpiox5Av", "YPTSJFJwD2ZKfAeYJUbW", "nNdBk7hc5NiBzeRvbI5T", "ORQNCfZnA18wmsMWVhf8"


def meta(hg, km, sl, hv):
    return [{"id": HG, "name": "HG", "value": hg}, {"id": KM, "name": "KMLM", "value": km},
            {"id": SL, "name": "SLEEVE", "value": sl}, {"id": HV, "name": "HARV", "value": hv}]


class Cap(unittest.TestCase):
    def test_p1_the_cap_is_44_percent_strictly(self):
        self.assertEqual(monitor.ENGINE_CAP, 0.44)
        self.assertEqual(monitor.cap_alerts(meta(43.9, 30, 26.1, 0), 100.0), [])
        self.assertEqual(monitor.cap_alerts(meta(44.0, 30, 26.0, 0), 100.0), [])          # at the cap: no breach
        got = monitor.cap_alerts(meta(44.1, 30, 25.9, 0), 100.0)
        self.assertEqual(len(got), 1)
        self.assertIn("CONCENTRATION CAP BREACH: HG", got[0])
        self.assertIn("44.1% of book (> 44%)", got[0])
        # the old 40% line no longer fires
        self.assertEqual(monitor.cap_alerts(meta(41, 33, 26, 0), 100.0), [])

    def test_p1_cash_counts_in_the_book(self):
        m = meta(45, 30, 25, 0)                                   # 45% of symphonies, 40.9% of the book with cash
        self.assertEqual(len(monitor.cap_alerts(m, 100.0)), 1)
        self.assertEqual(monitor.cap_alerts(m, 110.0), [])
        self.assertEqual(monitor.cap_alerts(m, 0.0), [])           # an empty book raises nothing

    def test_p2_the_line_names_the_new_targets(self):
        line = monitor.cap_alerts(meta(50, 30, 20, 0), 100.0)[0]
        self.assertIn("HG 34.1 / KMLM 34.1 / SLEEVE 31.8", line)
        self.assertIn("HARV retiring", line)
        self.assertNotIn("29/29/27/15", line)
        self.assertIn("operation 5", line)

    def test_p3_harv_never_breaches(self):
        self.assertEqual(monitor.cap_alerts(meta(10, 10, 10, 70), 100.0), [])
        self.assertEqual(monitor.RETIRING, (HV,))


class Sleeve(unittest.TestCase):
    def test_p4_share_of_the_composer_symphonies(self):
        band, w = monitor.sleeve_share(meta(104.9, 96.4, 81.8, 37.5), SL)
        self.assertEqual(band["id"], SL)
        self.assertAlmostEqual(w, 81.8 / 320.6, places=6)
        _, w2 = monitor.sleeve_share(meta(104.9, 96.4, 81.8, 37.5), SL, outside=346.0)
        self.assertAlmostEqual(w2, 81.8 / 666.6, places=6)        # an explicit outside figure still works
        self.assertEqual(monitor.sleeve_share(meta(1, 1, 1, 1), "missing"), (None, None))
        self.assertEqual(monitor.sleeve_share(meta(0, 0, 0, 0), SL), (None, None))

    def test_p5_the_band_is_off_by_default(self):
        src = open(os.path.join(HERE, "..", "monitor.py"), encoding="utf-8").read()
        self.assertRegex(src, r'add_argument\("--band-lo", type=float, default=None\)')
        self.assertRegex(src, r'add_argument\("--band-hi", type=float, default=None\)')
        self.assertRegex(src, r'add_argument\("--ibkr-equities", type=float, default=0\.0\)')
        # a breach line needs an explicit band: both comparisons are guarded by "is not None"
        self.assertEqual(len(re.findall(r"a\.band_(?:hi|lo) is not None and w [<>] a\.band_(?:hi|lo)", src)), 2)
        self.assertNotIn("29/29/27/15", src)
        self.assertNotIn("> 0.40", src)


if __name__ == "__main__":
    unittest.main()
