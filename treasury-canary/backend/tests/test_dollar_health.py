"""Merge-blocking gates for the Dollar tab's data-health pings (app/metrics/dollar_health.py).

Casey, 2026-11-16: "add the health pings". Data alarms only: a problem pings once when it opens and once
when it is resolved, never while it persists, never from a page view, and never as a market signal.
"""
from __future__ import annotations

import gzip
import json
import os
import re

import pytest

from app.metrics import dollar_health as dh
from app.metrics import dollar_watch as dw
from tests.test_dollar_watch import FORBIDDEN, _cut

HERE = os.path.dirname(__file__)
FX = os.path.join(HERE, "fixtures", "dollar_watch", "inputs_2026-11-02.json.gz")
LEDGER_FAIL = {"ledger": {"status": "error", "problem": "scramble-rule rows not saved: OSError: No space left on device"}}


@pytest.fixture(scope="module")
def inputs():
    with gzip.open(FX, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _run(payload, state, day, on=True):
    out: list[str] = []
    msgs = dh.notify(payload, state, day, out.append, lambda sev: on)
    return msgs, out


def test_a_healthy_build_sends_nothing(inputs, tmp_path):
    p = dw.build_dollar_watch(inputs, today="2026-11-02", ledger_file=str(tmp_path / "dollar_ledger.json"))
    assert dh.problems(p) == {}
    assert _run(p, str(tmp_path / "s.json"), "2026-11-02") == ([], [])


def test_a_problem_pings_once_and_once_more_when_resolved(tmp_path):
    st = str(tmp_path / "s.json")
    m1, out1 = _run(LEDGER_FAIL, st, "2026-11-16")
    m2, out2 = _run(LEDGER_FAIL, st, "2026-11-17")             # persists: silent
    m3, out3 = _run({}, st, "2026-11-18")                      # resolved
    m4, out4 = _run({}, st, "2026-11-19")
    assert len(out1) == 1 and out2 == [] and len(out3) == 1 and out4 == []
    assert out1[0].startswith(dh.HEAD) and "No space left on device" in out1[0]
    assert out3[0].startswith(dh.DONE) and "No space left on device" in out3[0]
    assert json.load(open(st, encoding="utf-8")) == {"open": {}}


def test_changing_counts_and_dates_inside_a_problem_do_not_re_ping(tmp_path):
    st = str(tmp_path / "s.json")
    a = {"forward": {"problems": ["inputs not archived for 2 rows (2026-11-02, 2026-11-03)"]}}
    b = {"forward": {"problems": ["inputs not archived for 3 rows (2026-11-02, 2026-11-03, 2026-11-04)"]}}
    assert len(_run(a, st, "d1")[1]) == 1 and _run(b, st, "d2")[1] == []
    since = json.load(open(st, encoding="utf-8"))["open"]
    assert [v["since"] for v in since.values()] == ["d1"]       # the first sighting is kept


def test_each_cause_is_its_own_problem(inputs, tmp_path):
    # the Fed published no CP rate from 2020-03-27 to 2020-05-06 (too few trades)
    p = dw.build_dollar_watch(_cut(inputs, "2020-05-06"), today="2020-05-06", ledger_file=str(tmp_path / "a.json"))
    pr = dh.problems(p)
    assert list(pr) == ["cp:gap"] and "since 2020-03-26" in pr["cp:gap"]
    # FRED itself more than a week behind the build day
    p = dw.build_dollar_watch(inputs, today="2026-11-20", ledger_file=str(tmp_path / "b.json"))
    assert list(dh.problems(p)) == ["cp:fetch"] and "2026-10-29" in dh.problems(p)["cp:fetch"]
    # a month-long blank that has ended is not a health problem: the data are flowing again
    p = dw.build_dollar_watch(_cut(inputs, "2020-05-08"), today="2020-05-08", ledger_file=str(tmp_path / "c.json"))
    assert dh.problems(p) == {}
    assert "build" in dh.problems({"build_error": "RuntimeError: boom"})


def test_the_severity_filter_is_respected(tmp_path):
    msgs, out = _run(LEDGER_FAIL, str(tmp_path / "s.json"), "d1", on=False)
    assert len(msgs) == 1 and out == []                         # TELEGRAM_MIN_SEVERITY above WARN: nothing sent


def test_an_unreadable_state_file_costs_at_most_one_repeat(tmp_path):
    st = tmp_path / "s.json"
    st.write_text("{not json", encoding="utf-8")
    assert len(_run(LEDGER_FAIL, str(st), "d1")[1]) == 1 and _run(LEDGER_FAIL, str(st), "d2")[1] == []


def test_pings_are_data_alarms_in_plain_words(inputs, tmp_path):
    cases = [LEDGER_FAIL, {"build_error": "RuntimeError: boom"},
             {"forward": {"problems": ["the ledger file is unreadable or wrongly shaped: nothing is being recorded"]}},
             dw.build_dollar_watch(_cut(inputs, "2020-05-06"), today="2020-05-06", ledger_file=str(tmp_path / "x.json")),
             dw.build_dollar_watch(inputs, today="2026-11-20", ledger_file=str(tmp_path / "y.json"))]
    texts = []
    for i, c in enumerate(cases):
        st = str(tmp_path / f"s{i}.json")
        texts += _run(c, st, "d1")[1] + _run({}, st, "d2")[1]
    assert len(texts) == 2 * len(cases)
    for t in texts:
        assert "not a market signal" in t or t.startswith(dh.DONE)
        assert not re.search(r"\bNone\b|\{|\}", t), t
        for phrase in FORBIDDEN:
            assert phrase not in t.lower(), (phrase, t)


def test_only_the_scheduler_pings(monkeypatch, tmp_path):
    from app import alerts
    from app.api import routes_dollar as rd
    sent: list[str] = []
    monkeypatch.setattr(alerts, "send", sent.append)
    monkeypatch.setattr(alerts, "should_send", lambda sev: True)
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rd.warm_dollar_watch(force=True)
    assert len([m for m in sent if "rebuild failed (RuntimeError: boom)" in m]) == 1
    assert os.path.exists(tmp_path / dh.STATE_NAME)             # beside the ledger, on the persistent disk
    sent.clear()
    rd.dollar_watch_payload()                                   # a page view
    rd.warm_dollar_watch(force=True)                            # the next scheduled run, still failing: silent
    assert sent == []
    monkeypatch.setattr(alerts, "send", lambda m: (_ for _ in ()).throw(OSError("telegram down")))
    monkeypatch.setattr(rd, "fetch_all", lambda: {})
    assert rd.warm_dollar_watch(force=True) is not None         # a failing ping never breaks the warm-up
