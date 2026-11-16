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
    msgs = dh.notify(payload, state, day, lambda m: out.append(m) or True, allowed)      # delivered
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
    assert pr == {"ledger": "Forward ledger: a write failed (OSError: No space left on device)."}
    assert "archived" not in pr["ledger"] and "deadline" not in pr["ledger"]   # not asked for: shown on the tab only
    crashed = {"forward": {"problems": ["KeyError: 'ofr_fsi'"]}}       # a record-writing step crashed: no row gets written
    assert dh.problems(crashed) == {"ledger": "Forward ledger: a recording step failed (KeyError)."}


def test_a_real_unreadable_ledger_is_one_plain_line(inputs, tmp_path):
    led = tmp_path / "dollar_ledger.json"
    led.write_text("{not json", encoding="utf-8")
    p = dw.build_dollar_watch(inputs, today="2026-11-02", ledger_file=str(led))
    assert dh.problems(p) == {"ledger": dh.UNREADABLE}


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
    assert dh.problems(none)["cp"].startswith("No CP spread: the CP or bill series is empty")
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
    monkeypatch.setattr(alerts, "send_now", lambda m: sent.append(m) or True)
    monkeypatch.setattr(alerts, "should_send", lambda sev: sev == "WARN")
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "fetch_all", lambda: {})          # offline: the build itself is what fails
    monkeypatch.setattr(rd, "build_dollar_watch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("REF unavailable")))
    for _ in range(2):
        with pytest.raises(Exception):
            rd.warm_dollar_watch(force=True)
    assert len(sent) == 1 and "no fallback build was possible; the tab is down" in sent[0]
    assert "RuntimeError: REF unavailable" in sent[0] and "HTTPException" not in sent[0]   # the real error, not the wrapper


def test_a_cold_failure_says_there_is_no_live_data_end_to_end(monkeypatch, tmp_path):
    from app import alerts
    from app.api import routes_dollar as rd
    sent: list[str] = []
    monkeypatch.setattr(alerts, "send_now", lambda m: sent.append(m) or True)
    monkeypatch.setattr(alerts, "should_send", lambda sev: sev == "WARN")
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rd.warm_dollar_watch(force=True)
    rd.warm_dollar_watch(force=True)                          # still failing: the cached empty build stays "empty"
    assert len(sent) == 1 and "the tab has no live data" in sent[0]
    assert rd._cache["data"]["build_fallback"] == "empty"


def test_opened_and_resolved_in_one_run_are_one_message(tmp_path):
    st = str(tmp_path / "s.json")
    cp_gap = {"funding": {"rows": [{"id": "cp_fin", "mean_5d_stale_why": "gap", "mean_5d_to": "2020-03-26"}]}}
    _run(LEDGER_FAIL, st)
    out = _run(cp_gap, st)[1]
    assert len(out) == 1 and out[0].startswith(dh.HEAD) and "Resolved:" in out[0] and "• Was: Forward ledger" in out[0]


def test_only_the_scheduler_pings(monkeypatch, tmp_path):
    from app import alerts
    from app.api import routes_dollar as rd
    calls: list[dict] = []
    sent: list[str] = []
    real = dh.notify
    monkeypatch.setattr(dh, "notify", lambda p, *a, **k: calls.append(p) or real(p, *a, **k))
    monkeypatch.setattr(alerts, "send_now", lambda m: sent.append(m) or True)
    monkeypatch.setattr(alerts, "should_send", lambda sev: sev == "WARN")
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rd.dollar_watch_payload(force=True)                       # a page-path rebuild, forced
    rd.dollar_watch_payload()                                 # a page view
    assert calls == [] and sent == [] and not os.path.exists(tmp_path / dh.STATE_NAME)
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
    st = str(tmp_path / "s.json")
    msgs, out = _run(LEDGER_FAIL, st, on=False)
    assert len(msgs) == 1 and out == []                       # TELEGRAM_MIN_SEVERITY above WARN: nothing sent
    assert _run({}, st)[1] == []                              # never announced, so never "resolved"


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


# ---------------------------------------------------------------------------- the second review (2026-11-16)
def test_an_undelivered_ping_is_retried_never_recorded(tmp_path):
    """review: alerts.send was fire-and-forget, so an open was recorded even when Telegram never got it."""
    st = str(tmp_path / "s.json")
    failed: list[str] = []
    assert len(dh.notify(LEDGER_FAIL, st, "d", lambda m: failed.append(m) or False, lambda s: True)) == 1
    assert len(failed) == 1 and not os.path.exists(st)        # tried, refused: nothing recorded as announced
    out = _run(LEDGER_FAIL, st)[1]
    assert len(out) == 1 and out[0].startswith(dh.HEAD)        # the retry goes out as the open, never an orphan resolve
    dh.notify({}, st, "d", lambda m: False, lambda s: True)    # the resolve is refused: still open
    assert "ledger" in json.load(open(st, encoding="utf-8"))["open"]
    out = _run({}, st)[1]
    assert len(out) == 1 and out[0].startswith(dh.DONE)


def test_a_worse_fallback_pings_again_a_better_one_does_not(tmp_path):
    st = str(tmp_path / "s.json")
    fb = {k: {"build_error": "RuntimeError: boom", "build_fallback": k} for k in ("previous", "empty", "none")}
    assert len(_run(fb["previous"], st)[1]) == 1
    out = _run(fb["none"], st)[1]                              # a restart into nothing building at all
    assert len(out) == 1 and "• Worse: The last rebuild failed" in out[0] and "the tab is down" in out[0]
    assert _run(fb["none"], st)[1] == [] and _run(fb["empty"], st)[1] == []      # persisting, then better: silent
    assert _run(fb["none"], st)[1][0].count("• Worse:") == 1


def test_a_ping_never_names_the_row_or_step(tmp_path):
    """review: most ledger rows are written only when a firing appears, so naming the row would announce it (Q6)."""
    firing_day = {"ledger": {"status": "error",
                             "problem": "matured outcomes not saved: OSError: [Errno 28] No space left on device; "
                                        "scramble-rule rows not saved: OSError: [Errno 28] No space left on device"},
                  "forward": {"problems": ["OSError: momentum outcomes_250d not saved: OSError: [Errno 28] No space left on device",
                                           "KeyError: 'momentum'", "placebo maturity not saved: OSError: [Errno 28] No space left on device"]}}
    text = dh.problems(firing_day)["ledger"]
    assert text == "Forward ledger: a write failed (OSError: [Errno 28] No space left on device); a recording step failed (KeyError)."
    for word in ("scramble", "momentum", "placebo", "maturity", "matured", "onset", "firing", "rule"):
        assert word not in text.lower(), word


def test_the_disk_probe_raises_the_ledger_problem_without_waiting_for_a_row(tmp_path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    bad = str(blocker / "dollar_ledger.json")                  # its directory cannot exist: every write there fails
    assert dh.probe(bad) and "Error" in dh.probe(bad)
    st = str(tmp_path / "s.json")
    out: list[str] = []
    dh.notify({}, st, "d", lambda m: out.append(m) or True, lambda s: True, ledger_file=bad)
    assert len(out) == 1 and "Forward ledger: the disk refused a test write" in out[0] and dh.TAG in out[0]
    good = str(tmp_path / "dollar_ledger.json")
    assert dh.probe(good) is None and not os.path.exists(tmp_path / dh.PROBE_NAME)
    dh.notify({}, st, "d", lambda m: out.append(m) or True, lambda s: True, ledger_file=good)
    assert len(out) == 2 and out[1].startswith(dh.DONE)        # the disk takes writes again: resolved
    dh._MEMORY.clear()
    st2 = str(tmp_path / "s2.json")                           # during a failed build too, the disk alarm opens
    msgs = dh.notify({"build_error": "RuntimeError: boom", "build_fallback": "previous"}, st2, "d", lambda m: True,
                     lambda s: True, ledger_file=bad)
    assert "the disk refused a test write" in msgs[0] and "rebuild failed" in msgs[0]
    dh._MEMORY.clear()
    st3 = str(tmp_path / "s3.json")                           # a stale copy's old ledger problem never re-opens
    stale = {**LEDGER_FAIL, "build_error": "RuntimeError: boom", "build_fallback": "previous"}
    msgs = dh.notify(stale, st3, "d", lambda m: True, lambda s: True, ledger_file=good)
    assert len(msgs) == 1 and "Forward ledger" not in msgs[0]


def test_the_scheduler_sends_synchronously_and_probes_the_ledger_disk(monkeypatch, tmp_path):
    from app import alerts
    from app.api import routes_dollar as rd
    seen: dict = {}
    real = dh.notify
    monkeypatch.setattr(dh, "notify", lambda p, *a, **k: seen.update(k) or real(p, *a, **k))
    monkeypatch.setattr(alerts, "send_now", lambda m: True)
    monkeypatch.setenv("DOLLAR_LEDGER_PATH", str(tmp_path / "dollar_ledger.json"))
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    monkeypatch.setattr(rd, "fetch_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rd.warm_dollar_watch(force=True)
    assert seen["send"] is alerts.send_now and seen["ledger_file"] == str(tmp_path / "dollar_ledger.json")


# ---------------------------------------------------------------------------- the re-check (2026-11-16)
def test_a_disk_outage_reads_the_same_whether_or_not_a_write_was_pending(tmp_path):
    """re-check OPEN item: on a full disk a pass that tried a write (a firing) read differently from a quiet one, and
    the resolve quoted the last silently saved text."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    bad, ok = str(blocker / "dollar_ledger.json"), str(tmp_path / "dollar_ledger.json")
    firing = {"ledger": {"status": "error", "problem": "scramble-rule rows not saved: OSError: [Errno 28] No space left on device"},
              "forward": {"problems": ["OSError: momentum outcomes_250d not saved: OSError: [Errno 28] No space left on device"]}}
    assert dh.problems(firing, dh.probe(bad)) == dh.problems({}, dh.probe(bad))
    st, out = str(tmp_path / "s.json"), []

    def send(m):
        out.append(m)
        return True
    dh.notify({}, st, "d1", send, lambda s: True, ledger_file=bad)                         # opens on a quiet pass
    dh.notify({"forward": {"problems": ["KeyError: 'x'"]}}, st, "d2", send, lambda s: True, ledger_file=ok)  # text moves
    dh.notify({}, st, "d3", send, lambda s: True, ledger_file=ok)                            # resolves
    assert len(out) == 2 and "• Was: Forward ledger: the disk refused a test write" in out[1] and "KeyError" not in out[1]


def test_an_old_state_file_never_fakes_a_worsening(tmp_path):
    st = tmp_path / "s.json"
    st.write_text(json.dumps({"open": {"build": {"since": "d", "text": "The last rebuild failed (X); the tab is down."}}}),
                  encoding="utf-8")
    assert _run({"build_error": "RuntimeError: boom", "build_fallback": "empty"}, str(st))[1] == []


def test_the_probe_waits_for_the_ledger_lock_and_leaves_nothing(tmp_path):
    import threading
    import time
    done: list = []
    with dw._LEDGER_LOCK:
        th = threading.Thread(target=lambda: done.append(dh.probe(str(tmp_path / "dollar_ledger.json"))))
        th.start()
        time.sleep(0.2)
        assert done == []                                       # never writes alongside a real ledger rewrite
    th.join(5)
    assert done == [None] and sorted(os.listdir(tmp_path)) == []
