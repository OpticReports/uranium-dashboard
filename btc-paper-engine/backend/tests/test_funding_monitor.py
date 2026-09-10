"""Gate tests for the funding-regime monitor (RESEARCH_CARRY.md policy).

Merge-blocking semantics under test:
  - ARM at mean >= 8.0 (inclusive), DISARM at mean < 5.0 (strict);
    5-8 band HOLDS the current state; exactly one alert per crossing.
  - Insufficient coverage (<50%) or a failed fetch freezes the venue's
    state - no transition, no alert, engine unaffected.
  - State survives a restart: reload does not re-page an old crossing.
  - INTX crossings page ACTION wording; HL pages leading-indicator wording.
No network anywhere in this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.funding_monitor import (  # noqa: E402
    EXPECTED_STAMPS, FundingMonitor, trailing_mean_annualized,
)

NOW = 1_787_745_600.0            # fixed clock for every test
HOUR = 3600


def make_rates(mean_ann_pct: float, hours: int = EXPECTED_STAMPS,
               now: float = NOW) -> dict:
    """Hourly stamps ending at `now` whose mean annualizes to mean_ann_pct."""
    rate = mean_ann_pct / 100 / (24 * 365)
    return {int(now) - i * HOUR: rate for i in range(hours)}


class Harness:
    """Monitor wired to canned per-venue means + in-memory persistence."""

    def __init__(self, saved=None):
        self.alerts: list[str] = []
        self.saved = saved
        self.means = {"INTX": 6.0, "HL": 6.0}
        self.raise_for: set[str] = set()
        self.hours = {"INTX": EXPECTED_STAMPS, "HL": EXPECTED_STAMPS}

        def fetch(venue):
            def _f(now_s):
                if venue in self.raise_for:
                    raise RuntimeError("venue down")
                return make_rates(self.means[venue], self.hours[venue], now_s)
            return _f

        self.mon = FundingMonitor(
            fetchers={"INTX": fetch("INTX"), "HL": fetch("HL")},
            alert_fn=self.alerts.append,
            load_fn=lambda: self.saved,
            save_fn=self._save,
            clock=lambda: NOW,
        )

    def _save(self, state):
        self.saved = dict(state)

    def set(self, intx=None, hl=None):
        if intx is not None:
            self.means["INTX"] = intx
        if hl is not None:
            self.means["HL"] = hl

    def intx(self):
        return self.mon.state["venues"]["INTX"]


# ---------------------------------------------------------------- metric

def test_annualization_math():
    mean, cov = trailing_mean_annualized(make_rates(8.0), NOW)
    assert abs(mean - 8.0) < 1e-9
    assert cov == 1.0


def test_metric_ignores_stamps_outside_window():
    rates = make_rates(8.0)
    rates[int(NOW) - 31 * 86400] = 1.0        # absurd stale stamp, outside 30d
    mean, _ = trailing_mean_annualized(rates, NOW)
    assert abs(mean - 8.0) < 1e-9


def test_metric_empty_is_none():
    mean, cov = trailing_mean_annualized({}, NOW)
    assert mean is None and cov == 0.0


# ---------------------------------------------------------------- hysteresis

def test_arm_is_inclusive_disarm_is_strict():
    h = Harness()
    h.set(intx=8.0)                            # exactly the arm line -> ARM
    h.mon.check()
    assert h.intx()["armed"] is True
    assert len([a for a in h.alerts if "INTX" in a and "ARMED" in a]) == 1
    h.set(intx=5.0)                            # exactly the disarm line -> hold
    h.mon.check()
    assert h.intx()["armed"] is True
    h.set(intx=4.99)                           # strictly below -> DISARM
    h.mon.check()
    assert h.intx()["armed"] is False
    assert any("DISARMED" in a for a in h.alerts)


def test_band_holds_state_no_alert():
    h = Harness()
    h.set(intx=7.9)                            # below arm, disarmed -> hold
    h.mon.check()
    assert h.intx()["armed"] is False and h.alerts == []
    h.set(intx=8.5)
    h.mon.check()
    n = len(h.alerts)
    h.set(intx=6.5)                            # inside the band, armed -> hold
    h.mon.check()
    h.mon.check()                              # repeated checks stay silent
    assert h.intx()["armed"] is True and len(h.alerts) == n


def test_alert_once_per_crossing_and_rearm():
    h = Harness()
    for intx in (6.0, 8.1, 7.0, 4.9, 6.0, 9.0):
        h.set(intx=intx)
        h.mon.check()
    intx_alerts = [a for a in h.alerts if "INTX" in a]
    assert len([a for a in intx_alerts if "ARMED" in a and "DISARMED" not in a]) == 2
    assert len([a for a in intx_alerts if "DISARMED" in a]) == 1


def test_intx_is_action_hl_is_leading_indicator():
    h = Harness()
    h.set(intx=9.0, hl=12.0)
    h.mon.check()
    intx_alert = next(a for a in h.alerts if "INTX BTC perp" in a)
    hl_alert = next(a for a in h.alerts if "leading indicator" in a)
    assert "⚡" in intx_alert and "RESEARCH_CARRY.md" in intx_alert
    assert "HL" in hl_alert and "⚡" not in hl_alert
    # cross-venue context appears in the INTX page
    assert "HL 12.0%" in intx_alert


# ---------------------------------------------------------------- data guards

def test_insufficient_coverage_freezes_state():
    h = Harness()
    h.set(intx=9.0)
    h.hours["INTX"] = EXPECTED_STAMPS // 3     # 33% coverage < 50% floor
    h.mon.check()
    assert h.intx()["armed"] is False
    assert h.intx()["insufficient"] is True
    assert h.alerts == []
    h.hours["INTX"] = EXPECTED_STAMPS          # data recovers -> normal ARM
    h.mon.check()
    assert h.intx()["armed"] is True and h.intx()["insufficient"] is False


def test_fetch_failure_is_noop_for_that_venue():
    h = Harness()
    h.set(intx=9.0, hl=9.0)
    h.raise_for.add("INTX")
    snap = h.mon.check()                       # must not raise
    assert h.mon.state["venues"]["INTX"]["armed"] is False
    assert h.mon.state["venues"]["HL"]["armed"] is True
    assert not any("INTX BTC perp" in a for a in h.alerts)
    assert snap["venues"]["INTX"]["mean_ann_pct"] is None


# ---------------------------------------------------------------- persistence

def test_restart_does_not_repage_old_crossing():
    h = Harness()
    h.set(intx=9.0)
    h.mon.check()
    assert len(h.alerts) == 1                  # HL still at 6.0 -> only INTX
    h2 = Harness(saved=h.saved)                # "restart" from persisted state
    h2.set(intx=9.0)
    h2.mon.check()
    assert h2.intx()["armed"] is True
    assert h2.alerts == []                     # armed already - no re-page


def test_snapshot_shape_and_history():
    h = Harness()
    h.mon.check()
    h.mon.check()
    snap = h.mon.snapshot()
    assert snap["policy"]["arm_pct"] == 8.0
    assert snap["policy"]["disarm_pct"] == 5.0
    assert snap["policy"]["gate_venue"] == "INTX"
    assert snap["history_points"] == 2
    assert set(snap["history"][-1]) == {"ts", "INTX", "HL"}
    assert snap["venues"]["INTX"]["mean_ann_pct"] == 6.0


# ---------------------------------------------------------------- parsers

def test_hl_payload_parse(monkeypatch):
    import app.funding_monitor as fm

    class FakeResp:
        def __init__(self, data):
            self._d = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            return FakeResp([
                {"coin": "BTC", "fundingRate": "0.0000125",
                 "time": 1787504400049},          # jittered ms stamp
                {"coin": "BTC", "fundingRate": "0.0000200",
                 "time": 1787508000034},
            ])

    monkeypatch.setattr(fm.httpx, "Client", FakeClient)
    out = fm.fetch_hl_hourly(now_s=1787745600.0)
    assert out == {1787504400: 1.25e-5, 1787508000: 2e-5}  # hour-bucketed


def test_intx_payload_parse_descending_pages(monkeypatch):
    import app.funding_monitor as fm
    now = 1787745600.0
    calls = []

    class FakeResp:
        def __init__(self, data):
            self._d = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            calls.append(params["result_offset"])
            # newest-first; second page dips past the 31d cutoff
            if params["result_offset"] == 0:
                rows = [{"funding_rate": "0.000002", "mark_price": "1",
                         "event_time": "2026-08-26T16:00:00Z"}] * 100
            else:
                rows = [{"funding_rate": "0.000001", "mark_price": "1",
                         "event_time": "2026-06-01T00:00:00Z"}] * 100
            return FakeResp({"results": rows,
                             "pagination": {"result_offset":
                                            params["result_offset"]}})

    monkeypatch.setattr(fm.httpx, "Client", FakeClient)
    out = fm.fetch_intx_hourly(now_s=now)
    assert calls == [0, 100]                   # stopped once past the cutoff
    assert len(out) == 1                       # old rows filtered out
    assert list(out.values()) == [2e-6]
