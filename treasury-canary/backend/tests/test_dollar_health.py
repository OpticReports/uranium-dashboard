"""Merge-blocking gates for the Dollar tab's data-health pings (app/metrics/dollar_health.py).

Casey, 2026-11-16: "add the health pings" (offered: a ledger write failure, an unreadable ledger, CP data stale
over a week; plus the build itself). Data alarms only: a problem pings once when it opens and once when it is
resolved, never while it persists, never from a page view, never as a market signal, and a failed build never
resolves anything. Each gate below fails if the behaviour it names is removed (the first review's mutations).
"""
from __future__ import annotations

import gzip
import json
import os

import pytest

from app.metrics import dollar_health as dh
from app.metrics import dollar_watch as dw
from tests.test_dollar_watch import FORBIDDEN, HOLE, STATUS_WORDS, _cut

HERE = os.path.dirname(__file__)
FX = os.path.join(HERE, "fixtures", "dollar_watch", "inputs_2026-11-02.json.gz")
DISK_FULL = "scramble-rule rows not saved: OSError: No space left on device"
LEDGER_FAIL = {"ledger": {"status": "error", "problem": DISK_FULL}}


@pytest.fixture(scope="module")
def inputs():
    with gzip.open(FX, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def _fresh_memory():
    dh._MEMORY.clear()
    yield
    dh._MEMORY.clear()


def _run(payload, state, day="d", on=True):
    out: list[str] = []
    levels: list[str] = []

    def allowed(sev):
        levels.append(sev)
        return on and sev == "WARN"                 # the default TELEGRAM_MIN_SEVERITY: anything below WARN is dropped
    msgs = dh.notify(payload, state, day, out.append, allowed)
    assert all(lv == "WARN" for lv in levels)
    return msgs, out


def test_a_healthy_build_sends_nothing(inputs, tmp_path):
    p = dw.build_dollar_watch(inputs, today="2026-11-02", ledger_file=str(tmp_path / "dollar_ledger.json"))
    assert dh.problems(p) == {}
    assert _run(p, str(tmp_path / "s.json")) == ([], [])


def test_a_problem_pings_once_and_once_more_when_resolved(tmp_path):
    st = str(tmp_path / "s.json")
    out1 = _run(LEDGER_FAIL, st, "2026-11-16")[1]
    out2 = _run(LEDGER_FAIL, st, "2026-11-17")[1]          # persists: silent
    out3 = _run({}, st, "2026-11-18")[1]                   # resolved
    out4 = _run({}, st, "2026-11-19")[1]
    assert len(out1) == 1 and out2 == [] and len(out3) == 1 and out4 == []
    assert out1[0].startswith(dh.HEAD) and "No space left on device" in out1[0]
    assert out3[0].startswith(dh.DONE) and "• Was: Forward ledger:" in out3[0]
    assert json.load(open(st, encoding="utf-8")) == {"open": {}}


def test_problems_opening_together_send_one_message(tmp_path):
    p = {"ledger": {"status": "error", "problem": DISK_FULL},
         "funding": {"rows": [{"id": "cp_fin", "mean_5d_stale_why": "gap", "mean_5d_to": "2020-03-26"}]}}
    msgs, out = _run(p, str(tmp_path / "s.json"))
    assert len(out) == 1 and out[0].count("• ") == 2


def test_one_root_cause_is_one_problem(tmp_path):
    # disk full hits the scramble-rule rows and the onset rows; an unreadable ledger is reported twice by the build
    p = {"ledger": {"status": "error", "problem": DISK_FULL},
         "forward": {"problems": ["onset rows not saved: OSError: No space left on device",
                                  "inputs not archived for 2 rows (2026-11-02, 2026-11-03)",
                                  "1 months dated after their deadline, not point in time (2026-11)"]}}
    pr = dh.problems(p)
    assert list(pr) == ["ledger"] and "onset rows not saved" in pr["ledger"]
    assert "archived" not in pr["ledger"] and "deadline" not in pr["ledger"]   # not asked for: shown on the tab only
    unreadable = {"ledger": {"status": "error", "problem": "the ledger file is unreadable or wrongly shaped: nothing is being recorded"},
                  "forward": {"problems": ["the ledger file is unreadable or wrongly shaped: nothing is being recorded"]}}
    assert list(dh.problems(unreadable)) == ["ledger"] and dh.problems(unreadable)["ledger"].count("unreadable") == 1


def test_each_cp_cause_is_one_problem_whose_text_follows_the_cause(inputs, tmp_path):
    # the Fed published no CP rate from 2020-03-27 to 2020-05-06 (too few trades)
    gap = dw.build_dollar_watch(_cut(inputs, "2020-05-06"), today="2020-05-06", ledger_file=str(tmp_path / "a.json"))
    assert list(dh.problems(gap)) == ["cp"] and "since 2020-03-26" in dh.problems(gap)["cp"]
    # FRED itself more than a week behind the build day
    behind = dw.build_dollar_watch(inputs, today="2026-11-20", ledger_file=str(tmp_path / "b.json"))
    assert "FRED data end 2026-10-29" in dh.problems(behind)["cp"]
    # only the CP fetch failed (a stale cached copy ending 2026-10-06)
    x = _cut(inputs, "2026-11-02")
    x["fred"]["DCPF3M"] = {**x["fred"]["DCPF3M"], "status": "stale",
                           "dates": [d for d in x["fred"]["DCPF3M"]["dates"] if d <= "2026-10-06"]}
    x["fred"]["DCPF3M"]["values"] = inputs["fred"]["DCPF3M"]["values"][:len(x["fred"]["DCPF3M"]["dates"])]
    cpf = dw.build_dollar_watch(x, today="2026-11-02", ledger_file=str(tmp_path / "c.json"))
    assert dh.problems(cpf)["cp"] == "The CP fetch failed; the tab shows the last good copy (data end 2026-10-06)."
    # no CP data at all
    y = json.loads(json.dumps(inputs))
    y["fred"]["DCPF3M"] = {"dates": [], "values": [], "status": "error"}
    none = dw.build_dollar_watch(y, today="2026-11-02", ledger_file=str(tmp_path / "d.json"))
    assert dh.problems(none)["cp"].startswith("No CP data at all")
    # a month-long blank that has ended is not a problem: the data are flowing again
    back = dw.build_dollar_watch(_cut(inputs, "2020-05-08"), today="2020-05-08", ledger_file=str(tmp_path / "e.json"))
    assert dh.problems(back) == {}
    # one stale stretch whose cause flips (one flaky fetch) pings once, and its text follows the cause
    st = str(tmp_path / "s.json")
    assert len(_run(gap, st)[1]) == 1 and _run(cpf, st)[1] == [] and _run(gap, st)[1] == []
    assert "since 2020-03-26" in json.load(open(st, encoding="utf-8"))["open"]["cp"]["text"]


def test_a_failed_build_never_resolves_anything(tmp_path):
    st = str(tmp_path / "s.json")
    cp_gap = {"funding": {"rows": [{"id": "cp_fin", "mean_5d_stale_why": "gap", "mean_5d_to": "2020-03-26"}]}}
    assert len(_run({**LEDGER_FAIL, **cp_gap}, st)[1]) == 1
    # cold restart, rebuild fails, the empty-input build is served: no CP rows, no ledger write attempted
    cold = {"build_error": "RuntimeError: boom", "build_fallback": "empty", "funding": {"rows": []}, "ledger": {"status": "ok"}}
    msgs, out = _run(cold, st)
    assert len(out) == 1 and "the tab has no live data" in out[0] and "Was:" not in out[0]
    assert _run(cold, st)[1] == []                            # still broken: silent
    # recovery with both problems still there: only the build resolves
    out = _run({**LEDGER_FAIL, **cp_gap}, st)[1]
    assert len(out) == 1 and out[0].startswith(dh.DONE) and out[0].count("• Was:") == 1 and "rebuild failed" in out[0]


def test_nothing_builds_at_all_still_pings_once(monkeypatch, tmp_path):
    from app import alerts
    from app.api import routes_dollar as rd
    sent: list[str] = []
    monkeypatch.setattr(alerts, "send", sent.append)
    monkeypatch.setattr(alerts, "should_send", lambda sev: sev == "WARN")
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "build_dollar_watch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("REF unavailable")))
    for _ in range(2):
        with pytest.raises(Exception):
            rd.warm_dollar_watch(force=True)
    assert len(sent) == 1 and "no fallback build was possible; the tab is down" in sent[0]


def test_only_the_scheduler_pings(monkeypatch, tmp_path):
    from app import alerts
    from app.api import routes_dollar as rd
    calls: list[dict] = []
    real = dh.notify
    monkeypatch.setattr(dh, "notify", lambda p, *a, **k: calls.append(p) or real(p, *a, **k))
    monkeypatch.setattr(alerts, "send", lambda m: None)
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rd.dollar_watch_payload(force=True)                       # a page-path rebuild, forced
    rd.dollar_watch_payload()                                 # a page view
    assert calls == []
    rd.warm_dollar_watch(force=True)
    assert len(calls) == 1 and calls[0].get("build_fallback") in ("empty", "previous")
    assert os.path.exists(tmp_path / dh.STATE_NAME)            # beside the ledger, on the persistent disk


def test_a_refused_save_never_repeats_a_ping(monkeypatch, tmp_path):
    st = str(tmp_path / "s.json")
    monkeypatch.setattr(dh.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("No space left on device")))
    assert [len(_run(LEDGER_FAIL, st)[1]) for _ in range(3)] == [1, 0, 0]


def test_a_wrongly_shaped_state_file_is_survived(tmp_path):
    for bad in ('{"open": {"ledger": "x"}}', '{"open": []}', "[]", "{not json"):
        st = tmp_path / f"s{abs(hash(bad))}.json"
        st.write_text(bad, encoding="utf-8")
        dh._MEMORY.clear()
        assert len(_run(LEDGER_FAIL, str(st))[1]) == 1 and _run(LEDGER_FAIL, str(st))[1] == []


def test_the_severity_filter_is_respected(tmp_path):
    msgs, out = _run(LEDGER_FAIL, str(tmp_path / "s.json"), on=False)
    assert len(msgs) == 1 and out == []                       # TELEGRAM_MIN_SEVERITY above WARN: nothing sent


def test_pings_are_data_alarms_in_plain_words(inputs, tmp_path):
    cases = [LEDGER_FAIL, {"build_error": "RuntimeError: boom", "build_fallback": "previous"},
             {"build_error": "RuntimeError: boom", "build_fallback": "empty"},
             {"build_error": "RuntimeError: boom", "build_fallback": "none"},
             dw.build_dollar_watch(_cut(inputs, "2020-05-06"), today="2020-05-06", ledger_file=str(tmp_path / "x.json")),
             dw.build_dollar_watch(inputs, today="2026-11-20", ledger_file=str(tmp_path / "y.json"))]
    texts = []
    for i, c in enumerate(cases):
        st = str(tmp_path / f"s{i}.json")
        texts += _run(c, st)[1] + _run({}, st)[1]
    assert len(texts) == 2 * len(cases)
    for t in texts:
        assert dh.TAG in t and t.startswith("🔧"), t
        assert not HOLE.search(t) and not STATUS_WORDS.search(t), t
        for phrase in FORBIDDEN:
            assert phrase not in t.lower(), (phrase, t)
