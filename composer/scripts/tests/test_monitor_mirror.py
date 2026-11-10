"""Gate tests for the monitor's hook into the IBKR mirror's paper book (monitor.mirror_dry_step).

  W1  what the paper step reports reaches the monitor: its lines are printed, its alerts are raised
  W2  the paper step can never stop the monitor: an exception, a SystemExit, or a missing module is one
      printed line and no alert
  W3  it runs after the shadow runner (whose ledger explains a difference) and after today's snapshot is
      written (it compares against it), exactly once

Run: python3 -m unittest tests.test_monitor_mirror -v
"""
import contextlib
import datetime
import io
import os
import sys
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import monitor  # noqa: E402

NOW = datetime.datetime(2026, 11, 10, 21, 35, tzinfo=datetime.timezone.utc)


def run(daily):
    alerts, out = ["earlier"], io.StringIO()
    with contextlib.redirect_stdout(out):
        monitor.mirror_dry_step(alerts, NOW, daily=daily)
    return alerts, out.getvalue()


class W1Reports(unittest.TestCase):
    def test_lines_are_printed_and_alerts_raised(self):
        seen = {}

        def daily(now=None):
            seen["now"] = now
            return ["mirror dry 2026-11-10: 4 of 4 engines hold what Composer holds"], ["MIRROR DRY MISMATCH — HARV"]
        alerts, text = run(daily)
        self.assertEqual(alerts, ["earlier", "MIRROR DRY MISMATCH — HARV"])
        self.assertIn("4 of 4 engines", text)
        self.assertEqual(seen["now"], NOW)

    def test_a_quiet_day_adds_nothing(self):
        alerts, _ = run(lambda now=None: (["mirror dry 2026-11-10: already in the ledger; nothing done"], []))
        self.assertEqual(alerts, ["earlier"])                 # the twin


class W2NeverFatal(unittest.TestCase):
    def test_a_failure_is_one_line_and_no_alert(self):
        for boom in (RuntimeError("feed down"), SystemExit(3), ValueError("bad book"), OSError("disk")):
            def daily(now=None, boom=boom):
                raise boom
            alerts, text = run(daily)
            self.assertEqual(alerts, ["earlier"], boom)
            self.assertEqual(text.count("\n"), 1, boom)
            self.assertIn("mirror dry run unavailable", text)

    def test_a_missing_module_is_one_line(self):
        with unittest.mock.patch.dict(sys.modules, {"mirror_dry": None}):
            alerts, out = ["earlier"], io.StringIO()
            with contextlib.redirect_stdout(out):
                monitor.mirror_dry_step(alerts, NOW)
        self.assertEqual(alerts, ["earlier"])
        self.assertIn("mirror dry run unavailable", out.getvalue())


class W3Wiring(unittest.TestCase):
    def test_once_after_the_shadow_runner_and_before_the_snapshot(self):
        src = open(os.path.join(HERE, "..", "monitor.py")).read()
        body = src[src.index("def main():"):]
        self.assertEqual(body.count("mirror_dry_step(alerts, now)"), 1)
        self.assertLess(body.index("shadow_runner.check_shadow("), body.index("mirror_dry_step(alerts, now)"))
        self.assertLess(body.index("json.dump(snap, f, indent=2)"), body.index("mirror_dry_step(alerts, now)"))   # today's snapshot first


if __name__ == "__main__":
    unittest.main()
