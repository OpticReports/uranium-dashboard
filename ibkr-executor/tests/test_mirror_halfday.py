"""Gate tests for app/mirror.py on an NYSE HALF-DAY (a 13:00 close; composer/IBKR_MIRROR.md). The next
are Fri 2026-11-27 and Thu 2026-12-24. The doubles are tests/test_mirror.py's.

  E1  the brain's clock drives the day: nothing before 12:54:25 (the bar ending 12:54:00 plus 25 s), the
      sells at 12:54:25, the cancel instant 12:59:00 (the close minus 60 s): a sell still resting then is
      cancelled and its partial booked at or after 12:59:00 and before 13:00, no buy is sent, and nothing
      is sent after the cancel instant
  E2  the FALLBACK clock (the brain's not read today: a /kill's flatten carried over from an earlier day
      never reads it) ends an early close at 13:00 by the service's own calendar: a flatten queued on the
      Wednesday before Thanksgiving sends nothing into the closed market at 13:05 on the half-day and
      waits for Monday's open. Twins: a regular Friday at 13:05 sells; without the calendar, so did the
      half-day (the defect)
  E3  an unreadable brain clock on a half-day: the loop is asked back at the late cadence from 12:30 (the
      window ends at 13:00), and the day's NO TRADE is recorded at 13:00, not 16:00. Twin: a regular day
      at 12:40 keeps the ordinary cadence and records nothing at 13:00
  E4  the service builds the books with its own early-close calendar (blend.session_close_et)
  E5  a decision bar whose SPY price is from BEFORE the instant (the brain's half-day rule: FMP's SPY bar at
      12:54 without volume, SPY at its own last trade) is traded only on an early close by the service's
      OWN calendar and at most 15 minutes before; a 16:00 day, no calendar, 16 minutes, a SPY time after
      the instant or none, or a bar not ending at the instant are refused. Twins: SPY at the instant trades
      on both days
  E6  the service's calendar (blend.NYSE_EARLY_CLOSES / NYSE_HOLIDAYS) and the brain's (shadow_runner.HALF_DAYS
      / NYSE_HOLIDAYS, read from its source) agree on every date both cover, and end in the same year
  E7  the brain's OWN half-day payload (built by its code on its fixture) trades only on the service's early close
  E8  SPY before the instant is traded only when the payload's close_et and the brain's clock give the service's
      early close too
  E9  the brain's own frozen-feed refusal, carried as any 503 into the recorded NO TRADE, keeps 'a frozen feed'
      and why
  E10 the brain-side build behind E7 / E9 skips only when composer/scripts is absent: any other failure fails
  E11 HALF_DAY_SPY_MAX_S is the brain's QUIET_TRADE_MAX_S (read with ast; the brain's H10 from its side)
"""
from __future__ import annotations

import ast
import os
from datetime import date, timedelta

import httpx
import pytest

from app import blend
from app import mirror as mm
from app.blend import session_close_et
from test_mirror import T1, Rig, at, decide_utc, payload, sound

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HALF = "2026-11-27"                       # the Friday after Thanksgiving: a 13:00 close
WED, THU, MON = "2026-11-25", "2026-11-26", "2026-11-30"
FRI = "2026-11-20"                        # a regular Friday


class HalfRig(Rig):
    """the shared rig, its manager given the service's early-close calendar (None: no calendar)"""

    def __init__(self, tmp_path, session_close=None, **kw):
        self.session_close = session_close
        super().__init__(tmp_path, **kw)

    def boot(self):
        m = super().boot()
        m._session_close = self.session_close
        return m


def test_e1_a_half_day_decides_at_12_54_25_and_cancels_at_12_59_before_the_close(tmp_path):
    r = HalfRig(tmp_path, session_close_et, live=True)
    r.tick("15:00")
    r.tick("15:55:05")                                         # invested on a full day
    assert r.m.state["last_run"]["outcome"] == "traded"
    held = r.m.book.sleeves["HG"].shares["BIL"]
    r.brain.close = "13:00"
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session=HALF, close="13:00")
    r.venue.hold.add("BIL")
    r.venue.partial["BIL"] = 100
    r.venue.fill_px["BIL"] = 91.40
    n = len(r.venue.placed)
    r.tick("12:54:24", day=HALF)
    assert r.venue.placed[n:] == [] and not [c for c in r.brain.calls if c[0] == "2026-11-27T17:54:00Z"]
    r.tick("12:54:25", day=HALF)
    run = r.m.state["run"]
    assert (run["session"], run["decide_utc"], run["cancel_utc"], run["close_utc"]) == \
        (HALF, "2026-11-27T17:54:00Z", "2026-11-27T17:59:00Z", "2026-11-27T18:00:00Z")
    assert [(s, q) for s, q, _ in r.venue.placed[n:]] == [("BIL", -held)]   # the sell first; it rests
    assert run["phase"] == "sells" and r.clock.now < at("12:59:00", HALF)
    r.tick("12:58:50", day=HALF)                               # ... and this tick waits into the cancel instant
    row = r.m.state["last_run"]
    bil = next(o for o in row["orders"] if o["symbol"] == "BIL")
    assert (bil["filled"], bil["price"]) == (100, 91.40) and "cancelled" in bil["how"]
    fill = next(x for x in r.journal() if x["event"] == "fill" and x["id"] == f"mirror-{HALF}-S-BIL")
    assert "2026-11-27T17:59:00Z" <= fill["utc"] < "2026-11-27T18:00:00Z"      # 12:59:00 <= booked < 13:00 ET
    assert not any(s == "TQQQ" for s, _, _ in r.venue.placed) and any("buys NOT sent" in x for x in row["notes"])
    m = len(r.venue.placed)
    for hms in ("12:59:30", "13:00:30", "15:55:05"):          # nothing after the cancel instant, nor at 15:54 + 25 s
        r.tick(hms, day=HALF)
    assert len(r.venue.placed) == m and r.m.state["last_session"] == HALF
    sound(r)


def _killed_on_wednesday(path, close):
    """invested on the Wednesday before Thanksgiving, /kill after its close: the flatten is queued"""
    os.makedirs(path, exist_ok=True)
    r = HalfRig(path, close, live=True, poll_s=1e9)
    r.trading_day = lambda d: d.weekday() < 5 and d.isoformat() != THU      # the service's holiday calendar
    r.boot()
    r.brain.make = lambda now: payload(now, session=now.astimezone(mm.ET).date().isoformat())
    r.tick("15:00", day=WED)
    r.tick("15:55:05", day=WED)
    assert r.m.state["last_run"]["outcome"] == "traded"
    r.m.halt("KILL", flatten=True)
    r.tick("17:00:00", day=WED)                                # queued: the session is shut
    assert r.m.book.positions() and not r.m.halt_state().get("flatten_done")
    return r


def test_e2_a_flatten_on_the_fallback_clock_sends_nothing_after_an_early_close(tmp_path):
    r = _killed_on_wednesday(tmp_path / "half", session_close_et)
    n = len(r.venue.placed)
    r.tick("13:05:00", day=HALF)                               # the brain's clock was last read on Wednesday
    assert r.m._today_info(r.clock.now) is None and r.m._rth(r.clock.now) is False
    assert r.venue.placed[n:] == [] and r.m.book.positions() != {}            # nothing into the closed market
    assert r.m.next_wait() == pytest.approx(min((at("09:30:00", MON) - at("13:05:00", HALF)).total_seconds(), 1e9))
    assert r.m._rth(at("12:59:59", HALF)) is True and r.m._rth(at("09:29:59", HALF)) is False
    r.tick("09:30:05", day=MON)                                # Monday's open: the sells go
    assert len(r.venue.placed) == n + 5 and r.m.book.positions() == {}
    sound(r)
    # twins: a REGULAR Friday at 13:05 is an open market; and with no calendar the half-day was one too
    f = _killed_on_wednesday(tmp_path / "fri", session_close_et)
    n = len(f.venue.placed)
    f.tick("13:05:00", day=FRI)
    assert len(f.venue.placed) == n + 5
    b = _killed_on_wednesday(tmp_path / "none", None)
    n = len(b.venue.placed)
    b.tick("13:05:00", day=HALF)
    assert len(b.venue.placed) == n + 5                        # the old fallback: orders after the 13:00 close


@pytest.mark.parametrize("live, before, now", [(True, mm.UNKNOWN_WAIT_S, mm.UNKNOWN_WAIT_LATE_S),
                                               (False, mm.PAPER_UNKNOWN_WAIT_S, mm.UNKNOWN_WAIT_S)])
def test_e3_an_unreadable_clock_on_a_half_day_runs_to_its_13_00_close(tmp_path, live, before, now):
    r = HalfRig(tmp_path / "half", session_close_et, live=live)
    r.brain.session_fail = "deadline"
    r.tick("12:20:00", day=HALF)
    assert r.m.next_wait() == before                           # half an hour before the window: the ordinary cadence
    r.tick("12:40:00", day=HALF)
    assert r.m.next_wait() == now                              # inside the half-day's last half hour: the late one
    r.tick("13:00:30", day=HALF)
    row = r.m.state["last_run"]
    assert (row["session"], row["outcome"]) == (HALF, "skipped") and "unreadable all session" in row["reason"]
    r.tick("13:05:00", day=HALF)
    assert r.m.next_wait() is None                             # five minutes past the close: the loop's own cadence
    assert len(r.m.state["history"]) == 1                      # recorded once
    t = HalfRig(tmp_path / "fri", session_close_et, live=live)                 # the twin: a regular Friday
    t.brain.session_fail = "deadline"
    t.tick("12:40:00", day=FRI)
    assert t.m.next_wait() == before
    t.tick("13:00:30", day=FRI)
    assert t.m.state.get("last_run") is None
    t.tick("16:00:30", day=FRI)
    assert t.m.state["last_run"]["outcome"] == "skipped"


def test_e4_the_service_builds_the_books_with_its_early_close_calendar(tmp_path, monkeypatch):
    from test_mirror_service import _boot, _ready
    client, service, _ = _boot(tmp_path, monkeypatch)
    with client:
        _ready(service)
        assert service.MIRROR and all(b._session_close is service._session_close_et for b in service.MIRROR.values())
    assert (service._session_close_et(date(2026, 11, 27)), service._session_close_et(date(2026, 12, 24)),
            service._session_close_et(date(2026, 11, 20))) == ((13, 0), (13, 0), (16, 0))


def _decided(path, day, close, calendar, bar):
    """a paper book on `day` (the brain's clock: a `close` close), asked at the close minus 3 minutes for a payload
    carrying `bar` as its decision bar"""
    os.makedirs(path, exist_ok=True)
    r = HalfRig(path, calendar)
    r.brain.close = close
    r.brain.make = lambda now: payload(now, session=day, close=close, decision_bar=bar)
    r.tick("12:57:00" if close == "13:00" else "15:57:00", day=day)
    return r


@pytest.mark.parametrize("day, close, calendar, spy_before, end_before, why", [
    (HALF, "13:00", session_close_et, 8, 0, None),                     # 2025-11-28's shape: SPY at its 12:46 trade
    (HALF, "13:00", session_close_et, 15, 0, None),                    # ... to the bound
    (HALF, "13:00", session_close_et, 0, 0, None),                     # twin: SPY at the instant, on a half-day
    (FRI, "16:00", session_close_et, 0, 0, None),                      # twin: ... and on a regular day
    (FRI, "16:00", session_close_et, 8, 0, "only an early close by this service's own calendar"),
    (HALF, "13:00", None, 8, 0, "only an early close by this service's own calendar"),     # no calendar: 16:00
    (HALF, "13:00", lambda d: (16, 0), 8, 0, "only an early close by this service's own calendar"),
    (HALF, "13:00", session_close_et, 16, 0, "SPY's price is from"),
    (HALF, "13:00", session_close_et, -1, 0, "SPY's price is from"),   # a SPY time after the instant
    (HALF, "13:00", session_close_et, None, 0, "SPY's price is from"),
    (HALF, "13:00", session_close_et, 1, 1, "the decision bar ends"),  # a bar that does not end at the instant
])
def test_e5_spy_before_the_instant_only_on_an_early_close_by_the_services_own_calendar(tmp_path, day, close, calendar,
                                                                                       spy_before, end_before, why):
    t = mm._parse(decide_utc(day, close))
    end = mm._iso(t - timedelta(minutes=end_before))
    spy = None if spy_before is None else mm._iso(t - timedelta(minutes=spy_before))
    r = _decided(tmp_path / "r", day, close, calendar, {"end_utc": end, "spy_utc": spy, "complete": True})
    if why is None:
        row = r.m.state["last_run"]
        assert (r.m.state["last_session"], row["outcome"]) == (day, "traded") and r.orders()
        assert row["decision_bar"] == {"end_utc": end, "spy_utc": spy, "complete": True}
        return
    assert r.orders() == [] and r.m.state.get("last_session") != day and why in r.m._why
    ok = _decided(tmp_path / "twin", day, close, calendar, {"end_utc": mm._iso(t), "spy_utc": mm._iso(t), "complete": True})
    assert ok.m.state["last_run"]["outcome"] == "traded"                      # the same day, SPY at the instant: traded


def _brain_calendar():
    """shadow_runner's HALF_DAYS and NYSE_HOLIDAYS, read from its source (ast: none of its imports needed)"""
    path = os.path.join(REPO, "composer", "scripts", "shadow_runner.py")
    if not os.path.isfile(path):
        pytest.skip("composer/scripts is not in this checkout")
    with open(path) as f:
        tree = ast.parse(f.read())
    got = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
           and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("HALF_DAYS", "NYSE_HOLIDAYS")}
    return {d: tuple(map(int, hm.split(":"))) for d, hm in got["HALF_DAYS"].items()}, set(got["NYSE_HOLIDAYS"])


def calendar_disagreements(early, holidays, half, closed):
    """([(date, the service's day, the brain's day)] for every date both calendars cover where they differ, the
    last year each covers, as shadow_runner.calendar_through counts it: the year BOTH its tables reach): from the
    later of the two calendars' first entries to the end of the earlier last year"""
    ours, theirs = set(early) | set(holidays), set(half) | set(closed)
    last = lambda *tables: min(max(int(d[:4]) for d in t) for t in tables)   # noqa: E731
    years = (last(early, holidays), last(half, closed))
    d, hi = date.fromisoformat(max(min(ours), min(theirs))), date(min(years), 12, 31)
    out = []
    while d <= hi:
        k = d.isoformat()
        a = "closed" if k in holidays else early.get(k, (16, 0))
        b = "closed" if k in closed else half.get(k, (16, 0))
        if a != b:
            out.append((k, a, b))
        d += timedelta(days=1)
    return out, years


def test_e6_the_services_calendar_and_the_brains_agree_on_every_date_both_cover():
    half, closed = _brain_calendar()
    diff, years = calendar_disagreements(blend.NYSE_EARLY_CLOSES, blend.NYSE_HOLIDAYS, half, closed)
    assert diff == [], f"the service's calendar (app/blend.py) and the brain's (shadow_runner.py) differ: {diff}"
    assert years[0] == years[1], f"the calendars end in different years {years}: extend both together"
    assert "2026-11-27" in half and blend.session_close_et(date(2026, 11, 27)) == (13, 0)   # not vacuous: a half-day in range
    # the comparison itself catches a one-sided edit: a half-day the service lacks, a holiday the brain lacks
    missing = {k: v for k, v in blend.NYSE_EARLY_CLOSES.items() if k != "2026-12-24"}
    assert calendar_disagreements(missing, blend.NYSE_HOLIDAYS, half, closed)[0] == [("2026-12-24", (16, 0), (13, 0))]
    assert calendar_disagreements(blend.NYSE_EARLY_CLOSES, blend.NYSE_HOLIDAYS, half, closed - {"2026-11-26"})[0] == \
        [("2026-11-26", "closed", (16, 0))]


def _brain_build(day="2025-11-28", edit=None):
    """(payload, the brain's NotPublished) of the brain's OWN pinned build at `day`'s 12:54 instant, by the brain's
    code on its fixture (composer/scripts/tests/test_mirror_halfday.py: FMP's archive), after `edit` (HalfDay -> None,
    an edit of FMP's rows). Skipped ONLY when composer/scripts is not in this checkout: anything else that goes wrong
    on the brain's side fails the test that asked, so a moved fixture or a changed helper can never turn a gate into a
    silent skip"""
    scripts = os.path.join(REPO, "composer", "scripts")
    if not os.path.isdir(scripts):
        pytest.skip("composer/scripts is not in this checkout")
    import importlib.util
    import sys
    added = [p for p in (scripts, os.path.join(scripts, "tests")) if p not in sys.path]
    sys.path[:0] = added
    try:                                       # the brain's test module shares this one's name: loaded under its own
        spec = importlib.util.spec_from_file_location("composer_test_mirror_halfday",
                                                      os.path.join(scripts, "tests", "test_mirror_halfday.py"))
        th = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(th)

        class Build(th.HalfDay):
            def runTest(self):
                pass
        b = Build()
        b.setUpClass()
        b.setUp()
        try:
            if edit is not None:
                edit(b)
            return b.pinned(day)
        finally:
            b.doCleanups()
    finally:
        for p_ in added:
            if p_ in sys.path:
                sys.path.remove(p_)


@pytest.fixture(scope="module")
def brain_half_day():
    """the brain's OWN pinned payload for the half-day 2025-11-28 (FMP's archive: SPY's bar at 12:54 without volume,
    SPY at its 12:46 trade)"""
    p, err = _brain_build()
    assert err is None and p["decision_bar"]["spy_utc"] != p["decision_bar"]["end_utc"]
    return p


@pytest.mark.parametrize("calendar, traded", [(lambda d: (13, 0) if d == date(2025, 11, 28) else (16, 0), True),
                                              (session_close_et, False)])      # blend's table: 2025 is not in it
def test_e7_the_brains_own_half_day_payload_trades_only_on_the_services_early_close(tmp_path, brain_half_day, calendar,
                                                                                   traded):
    p = brain_half_day
    r = _decided(tmp_path / "r", "2025-11-28", "13:00", calendar, p["decision_bar"])
    r.brain.make = lambda now: dict(p)
    r.tick("12:57:00", day="2025-11-28")
    if traded:
        row = r.m.state["last_run"]
        assert (row["session"], row["outcome"], row["decision_bar"]) == ("2025-11-28", "traded", p["decision_bar"])
        assert {n: s["action"] for n, s in row["sleeves"].items()} == dict.fromkeys(p["engines"], "trade")
    else:
        assert r.orders() == [] and "only an early close by this service's own calendar" in r.m._why


@pytest.mark.parametrize("clock, close_et, traded", [
    ("13:00", "13:00", True),            # twin: the service's calendar, the brain's clock and the payload agree: traded
    ("16:00", "16:00", False),           # the brain's clock and the payload a 16:00 close (decided 15:54): refused
    ("13:00", "16:00", False),           # the payload's close_et against the brain's clock and the service's calendar
    ("16:00", "13:00", False),           # the brain's clock against the payload and the service's calendar
    ("13:00", None, False),              # a payload that gives no close
])
def test_e8_spy_before_the_instant_needs_the_payloads_close_and_the_brains_clock_at_the_services_early_close(
        tmp_path, clock, close_et, traded):
    """defence in depth: SPY priced 8 minutes before the instant on Fri 11-27 (13:00 by the service's own calendar) is
    traded only when the payload's own close_et and the brain's clock close at 13:00 too"""
    t = mm._parse(decide_utc(HALF, clock))
    bar = {"end_utc": mm._iso(t), "spy_utc": mm._iso(t - timedelta(minutes=8)), "complete": True}
    os.makedirs(tmp_path / "r", exist_ok=True)
    r = HalfRig(tmp_path / "r", session_close_et)
    r.brain.close = clock
    r.brain.make = lambda now: payload(now, session=HALF, close=clock, decision_bar=bar, close_et=close_et)
    r.tick("12:57:00" if clock == "13:00" else "15:57:00", day=HALF)
    if traded:
        row = r.m.state["last_run"]
        assert (row["session"], row["outcome"], row["decision_bar"]) == (HALF, "traded", bar) and r.orders()
        return
    assert r.orders() == [] and r.m.state.get("last_session") != HALF
    assert "this service's calendar closes at 13:00, but" in r.m._why and "only an early close they agree on" in r.m._why


def test_e9_the_brains_frozen_feed_refusal_keeps_its_key_words_in_the_recorded_no_trade(tmp_path, monkeypatch):
    """the brain's OWN 503 for a frozen SPY (2025-11-28, SPY's bars after 12:44 at its last trade's price, without
    volume: built by the brain's code on its fixture), read through HttpBrain as any 503 is (_reason: its error and
    detail, each cut at 160 characters) and recorded at plan_by as the day's NO TRADE (_skip: cut at 400): 'a frozen
    feed', and why, survive both cuts"""
    p, err = _brain_build(edit=lambda b: b.freeze("2025-11-28", "12:44", {"SPY"}))
    assert p is None and err.error == "decision bar not published yet" and "a frozen feed" in err.detail
    body = err.body()

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url.endswith("/mirror/intents") and headers == {"X-API-Token": "tok"}
        return httpx.Response(503, json=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(mm.httpx, "get", fake_get)
    r = HalfRig(tmp_path, session_close_et)
    r.brain.close = "13:00"
    r.brain.intents = mm.HttpBrain("https://brain.invalid", "tok").intents      # the real client reads the brain's 503
    for hms in ("12:54:25", "12:57:00", "12:58:00"):
        r.tick(hms, day=HALF)
    row = r.m.state["last_run"]
    assert (row["session"], row["outcome"]) == (HALF, "skipped") and r.orders() == []
    assert "the brain is not ready (503: decision bar not published yet — SPY's last traded bar ends 12:45:00 ET" \
        in row["reason"], row["reason"]
    assert "(half-day, a frozen feed: none of SPY's bars without volume since that trade moved off its price" \
        in row["reason"], row["reason"]                                       # the key words, and why


def test_e10_a_brain_side_failure_fails_the_gate_it_feeds_and_never_skips_it():
    """_brain_build (the brain_half_day fixture's build) skips only when composer/scripts is not in the checkout: a
    failure on the brain's side (here an edit that raises, as a moved fixture or a renamed helper would) reaches the
    test as the error it is"""
    def broken(b):
        raise LookupError("the brain side changed under this gate")
    try:
        _brain_build(edit=broken)
    except LookupError:
        return
    except pytest.skip.Exception as exc:
        pytest.fail(f"a brain-side failure became a skip: {exc}")
    pytest.fail("the brain-side failure was swallowed")


def _module_number(path, name):
    """the module-level constant `name` of the python file `path`, read with ast (none of its imports run): a number,
    or a sum, product or quotient of numbers and of `pc.<NAME>` (preclose.py's, beside it)"""
    with open(path) as f:
        tree = ast.parse(f.read())
    node = next((n.value for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name), None)
    assert node is not None, f"{name} is not a module constant of {path}"

    def val(x):
        if isinstance(x, ast.Constant) and isinstance(x.value, (int, float)) and not isinstance(x.value, bool):
            return x.value
        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "pc":
            return _module_number(os.path.join(os.path.dirname(path), "preclose.py"), x.attr)
        if isinstance(x, ast.BinOp) and isinstance(x.op, (ast.Mult, ast.Add, ast.Sub, ast.Div)):
            a, b = val(x.left), val(x.right)
            return {ast.Mult: a * b, ast.Add: a + b, ast.Sub: a - b, ast.Div: a / b if b else None}[type(x.op)]
        raise AssertionError(f"{name} in {path} is not a plain number: {ast.dump(x)}")
    return val(node)


def test_e11_the_bound_on_spy_before_the_instant_is_the_brains_quiet_trade_max():
    """drift guard (passes before and after): HALF_DAY_SPY_MAX_S is the brain's QUIET_TRADE_MAX_S (composer/scripts/
    mirror_brain.py: the preview's FRESH_MIN in seconds, both read with ast); the brain's H10 is the same check from
    its side. A one-sided change of either fails here"""
    path = os.path.join(REPO, "composer", "scripts", "mirror_brain.py")
    if not os.path.isfile(path):
        pytest.skip("composer/scripts is not in this checkout")
    brain = _module_number(path, "QUIET_TRADE_MAX_S")
    assert brain == _module_number(os.path.join(REPO, "composer", "scripts", "preclose.py"), "FRESH_MIN") * 60
    assert mm.HALF_DAY_SPY_MAX_S == brain, (f"the executor's HALF_DAY_SPY_MAX_S {mm.HALF_DAY_SPY_MAX_S} and the brain's "
                                            f"QUIET_TRADE_MAX_S {brain} differ: change both together")
