"""Gates for the gateway-outage ledger and the supervisor contract."""
import json
import os
import subprocess
import time

from app.outages import OutageLog


def test_outage_recorded_with_blocked_calls(tmp_path):
    lg = OutageLog(str(tmp_path / "o.json"))
    t0 = time.time()
    lg.start(t0)
    lg.start(t0 + 1)                      # idempotent: one outage, not two
    for _ in range(4):
        lg.blocked_call()
    lg.mark_alerted()
    rec = lg.end(t0 + 120)
    assert rec["ended_by"] == "reconnect"
    assert rec["duration_s"] == 120.0
    assert rec["blocked_calls"] == 4
    assert rec["alerted"] is True
    assert len(lg.history) == 1 and lg.open is None


def test_outage_survives_restart_and_is_marked_not_self_healed(tmp_path):
    """THE distinction the in-memory flag could never make: an outage the
    process did not survive did NOT self-heal, and that is exactly what
    supervision is supposed to eliminate."""
    p = str(tmp_path / "o.json")
    lg = OutageLog(p)
    lg.start(time.time() - 600)
    lg.blocked_call()
    assert lg.open is not None
    lg2 = OutageLog(p)                    # process died mid-outage
    assert lg2.open is None
    assert lg2.history[-1]["ended_by"] == "process_restart"
    assert lg2.summary()["needed_a_restart"] == 1
    assert lg2.summary()["self_healed"] == 0


def test_summary_separates_self_healed_from_restarted(tmp_path):
    lg = OutageLog(str(tmp_path / "o.json"))
    now = time.time()
    for i in range(3):
        lg.start(now - 100 * (i + 1)); lg.blocked_call(); lg.end(now - 100 * i)
    lg.history.append({"start_ts": now - 50, "end_ts": now, "duration_s": 50.0,
                       "ended_by": "process_restart", "blocked_calls": 2,
                       "alerted": True})
    s = lg.summary()
    assert s["outages"] == 4
    assert s["self_healed"] == 3 and s["needed_a_restart"] == 1
    assert s["blocked_calls"] == 5
    assert s["alerted"] == 1


def test_ledger_never_breaks_trading_on_a_bad_path(tmp_path):
    """Observability must not be able to take the executor down."""
    lg = OutageLog("/nonexistent-dir/deny/o.json")
    lg.start(); lg.blocked_call(); lg.mark_alerted()
    assert lg.end() is not None           # in-memory still coherent
    bad = tmp_path / "corrupt.json"
    bad.write_text("{not json")
    lg2 = OutageLog(str(bad))             # unreadable -> fresh, no raise
    assert lg2.history == [] and lg2.open is None
    assert OutageLog(None).summary()["outages"] == 0


def test_supervisor_restarts_a_dying_gateway_with_backoff(tmp_path):
    """The whole point: an unsupervised `"$GW" &` left a dead gateway dead
    until a human redeployed, while /health stayed 200."""
    launches, recs = _run_sup(tmp_path, 7, {"MIN": "1", "MAX": "4",
                                            "MCF": "99"}, timeout="8")
    assert launches >= 2, "gateway was never restarted"
    assert launches <= 6, f"hot restart loop: {launches} launches in 8s"
    assert [r["next_delay_s"] for r in recs][:3] == [1, 2, 4], recs
    assert all(r["exit_code"] == 7 for r in recs)

def test_ledger_that_raises_cannot_escape_into_reconnect():
    """The change's own stated invariant. Tolerating None was never enough:
    a malformed persisted record made cycle_blocked/mark_alerted raise
    KeyError straight out of _reconnect(), and on the reconnect-SUCCESS path
    it left the adapter permanently believing it was mid-outage."""
    import types
    import app.ib_adapter as A

    class Exploding:
        def __getattr__(self, n):
            def boom(*a, **k):
                raise RuntimeError(f"exploded in {n}()")
            return boom

    class FakeIB:
        def __init__(self, ok):
            self.on, self.ok = False, ok
        def isConnected(self):
            return self.on
        def disconnect(self):
            pass
        def connect(self, *a, **k):
            if not self.ok:
                raise OSError("refused")
            self.on = True

    def mk(ok):
        ad = A.IBAdapter.__new__(A.IBAdapter)
        ad.ib = FakeIB(ok)
        ad.cfg = types.SimpleNamespace(trading_mode="paper", ib_host="h",
                                       ib_client_id=1)
        ad._reconnect_backoff = A.RECONNECT_BACKOFF_S
        ad._next_reconnect_ts = 0.0
        ad._disconnected_since = None
        ad._outage_alerted = False
        ad.outages = Exploding()
        return ad

    ok = mk(True)
    ok._reconnect()                       # must not raise
    # and must leave clean state: this is what silently broke before
    assert ok._disconnected_since is None
    assert ok._outage_alerted is False
    assert ok._reconnect_backoff == A.RECONNECT_BACKOFF_S
    down = mk(False)
    down._reconnect()
    assert down._disconnected_since is not None
    try:
        down._require_connected()
        raise AssertionError("should have failed closed")
    except A.ExecutorConnectionError:
        pass


def test_health_stays_200_for_every_hostile_ledger(tmp_path, monkeypatch):
    """healthCheckPath is /health: a 500 here makes Render restart the whole
    container, executor included, possibly mid-order - the exact outcome the
    design says it avoids."""
    import json as _json
    from fastapi.testclient import TestClient
    import app.service as svc

    class SummaryRaises:
        history: list = []
        def summary(self):
            raise RuntimeError("boom")

    cases = [SummaryRaises()]
    for bad in ({"history": [{"duration_s": None}]},
                {"history": [{"duration_s": "x", "start_ts": time.time()}]},
                {"history": ["notadict"]},
                {"open": {"no_start_ts": 1}},
                {"open": "string"}):
        p = tmp_path / f"{abs(hash(str(bad)))}.json"
        p.write_text(_json.dumps(bad))
        cases.append(OutageLog(str(p)))
    for lg in cases:
        monkeypatch.setattr(svc, "OUTAGES", lg)
        r = TestClient(svc.app).get("/health")
        assert r.status_code == 200, lg
        assert r.json()["status"] == "ok"


def test_supervisor_env_validation_rejects_hostile_values():
    """'abc' killed the supervisor silently (supervision off, /health still
    200); '-1' made delay diverge negative -> ~63 JVM launches/second."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "start.sh")).read()
    blk = src[src.index("RESTART_LOG="):src.index("log_restart()")]
    import tempfile
    for env, should_pass in [({"IBGW_BACKOFF_MIN_S": "abc"}, False),
                             ({"IBGW_BACKOFF_MIN_S": "-1"}, False),
                             ({"IBGW_HEALTHY_S": "5s"}, False),
                             ({"IBGW_MAX_CONSEC_FAIL": "0"}, False),
                             ({"IBGW_BACKOFF_MIN_S": "100",
                               "IBGW_BACKOFF_MAX_S": "10"}, False),
                             ({}, True)]:
        f = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
        f.write("#!/usr/bin/env bash\nset -u\n" + blk + "\necho ACCEPTED\n")
        f.close()
        e = dict(os.environ); e.update(env)
        r = subprocess.run(["bash", f.name], capture_output=True, text=True,
                           env=e)
        assert (r.returncode == 0) is should_pass, (env, r.returncode, r.stderr)


def _run_sup(tmp_path, gw_exit, env, timeout="12"):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gw = tmp_path / "gw.sh"
    gw.write_text("#!/usr/bin/env bash\necho x >> %s\nsleep ${UPTIME:-0}\n"
                  "exit %s\n" % (tmp_path / "count", gw_exit))
    gw.chmod(0o755)
    runner = tmp_path / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\nset -u\n"
        f"RESTART_LOG={tmp_path}/r.jsonl\n"
        "BACKOFF_MIN_S=${MIN:-1}; BACKOFF_MAX_S=${MAX:-4}\n"
        "HEALTHY_S=${HS:-99}; MAX_CONSEC_FAIL=${MCF:-8}\n"
        "LOG_MAX_LINES=${LML:-2000}\n"
        "eval \"$(sed -n '/^log_restart()/,/^}$/p;"
        "/^supervise_gateway()/,/^}$/p' %s/start.sh)\"\n"
        "supervise_gateway \"$1\"\n" % root)
    runner.chmod(0o755)
    e = dict(os.environ); e.update(env)
    subprocess.run(["timeout", timeout, str(runner), str(gw)],
                   capture_output=True, env=e)
    recs = []
    rp = tmp_path / "r.jsonl"
    if rp.exists():
        recs = [json.loads(l) for l in rp.read_text().splitlines() if l.strip()]
    cp = tmp_path / "count"
    return (len(cp.read_text().split()) if cp.exists() else 0), recs


def test_supervisor_circuit_breaker_stops_hammering_ibkr(tmp_path):
    """A permanently unstartable gateway (bad credentials) would attempt
    ~250-290 IBKR logins/day forever. IBKR locks accounts on repeated
    failures and LIVE attempts fire 2FA pushes."""
    launches, recs = _run_sup(tmp_path, 7, {"MCF": "4", "MIN": "1", "MAX": "1"})
    assert recs[-1]["reason"] == "circuit_open", recs[-1]
    assert launches <= 5, f"kept restarting past the breaker: {launches}"


def test_supervisor_backoff_caps(tmp_path):
    """Untested bound: removing the cap left the suite green."""
    _, recs = _run_sup(tmp_path, 7, {"MIN": "1", "MAX": "2", "MCF": "99"})
    delays = [r["next_delay_s"] for r in recs if r["reason"] == "exited"]
    assert delays[:4] == [1, 2, 2, 2], delays


def test_supervisor_healthy_uptime_resets_backoff(tmp_path):
    """Untested bound: removing the HEALTHY_S reset left the suite green.
    The gateway must actually STAY UP past HEALTHY_S for the reset to apply."""
    _, recs = _run_sup(tmp_path, 7, {"MIN": "1", "MAX": "8", "HS": "2",
                                     "MCF": "99", "UPTIME": "3"}, timeout="12")
    ex = [r for r in recs if r["reason"] == "exited"]
    assert ex, recs
    assert all(r["uptime_s"] >= 2 for r in ex), ex
    # every start was healthy -> backoff never escalates past the minimum
    assert all(r["next_delay_s"] == 1 for r in ex), ex


def test_supervisor_does_not_restart_on_shutdown_signal(tmp_path):
    """Behavioural, not a grep: the previous test greped for '-eq 143' and
    passed while the trap it also greped for was provably inert."""
    launches, recs = _run_sup(tmp_path, 143, {"MIN": "1", "MCF": "99"},
                              timeout="5")
    assert launches == 1, f"resurrected after a signal exit: {launches}"
    assert not recs, recs


def test_restart_log_rotates_and_counts_the_whole_tail(tmp_path):
    """last_24h applied `limit` BEFORE the 24h filter, so it saturated at 20
    in exactly the restart storm it exists to reveal."""
    import app.service as svc
    log = tmp_path / "r.jsonl"
    now = int(time.time())
    log.write_text("".join(
        json.dumps({"ts": now - i, "reason": "exited", "exit_code": 7,
                    "uptime_s": 0, "next_delay_s": 5}) + "\n"
        for i in range(250)))
    svc.settings.gateway_restart_log = str(log)
    rep = svc._gateway_restarts()
    assert rep["last_24h"] == 250, rep
    assert rep["recent_shown"] <= 20


def test_history_capped_in_memory_not_only_on_disk(tmp_path):
    lg = OutageLog(str(tmp_path / "o.json"))
    now = time.time()
    for i in range(520):
        lg.start(now); lg.end(now + 1)
    assert len(lg.history) <= 500, len(lg.history)


def test_summary_window_excludes_old_outages(tmp_path):
    lg = OutageLog(str(tmp_path / "o.json"))
    old = time.time() - 60 * 86400
    lg.history.append({"start_ts": old, "duration_s": 10.0,
                       "ended_by": "reconnect", "blocked_calls": 1})
    lg.start(time.time()); lg.end(time.time() + 5)
    assert lg.summary()["outages"] == 1


def test_clock_step_backwards_does_not_poison_totals(tmp_path):
    lg = OutageLog(str(tmp_path / "o.json"))
    t = time.time()
    lg.start(t)
    rec = lg.end(t - 600)                 # NTP stepped backwards
    assert rec["duration_s"] == 0.0 and rec["clock_step"] is True
    assert lg.summary()["total_downtime_s"] >= 0


def test_cleanup_runs_between_exit_and_relaunch_never_on_first(tmp_path):
    """The cleanup path had zero coverage by construction: the harness
    extracts supervise_gateway alone, so the declare-F guard no-op'd it in
    every test while the real container runs pkill. Extract BOTH functions,
    stub pkill via PATH shim (it must never really run in a test env), and
    assert cleanup fires between exit and relaunch - and not before the
    first launch."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bindir = tmp_path / "bin"; bindir.mkdir()
    for tool in ("pkill",):
        sh = bindir / tool
        sh.write_text("#!/usr/bin/env bash\necho \"$0 $@\" >> %s\nexit 0\n"
                      % (tmp_path / "pkill.log"))
        sh.chmod(0o755)
    gw = tmp_path / "gw.sh"
    gw.write_text("#!/usr/bin/env bash\necho launch >> %s\nexit 7\n"
                  % (tmp_path / "events"))
    gw.chmod(0o755)
    runner = tmp_path / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\nset -u\n"
        f"export PATH={bindir}:$PATH\n"
        f"RESTART_LOG={tmp_path}/r.jsonl\n"
        "BACKOFF_MIN_S=1; BACKOFF_MAX_S=1; HEALTHY_S=99; MAX_CONSEC_FAIL=99\n"
        "LOG_MAX_LINES=2000\n"
        "eval \"$(sed -n '/^cleanup_gateway_leftovers()/,/^}$/p;"
        "/^log_restart()/,/^}$/p;"
        "/^supervise_gateway()/,/^}$/p' %s/start.sh)\"\n"
        # wrap cleanup to also journal into the same event stream
        "eval \"orig_$(declare -f cleanup_gateway_leftovers)\"\n"
        "cleanup_gateway_leftovers() { echo cleanup >> %s; "
        "orig_cleanup_gateway_leftovers; }\n"
        "supervise_gateway \"$1\"\n" % (root, tmp_path / "events"))
    runner.chmod(0o755)
    subprocess.run(["timeout", "7", str(runner), str(gw)], capture_output=True)
    events = (tmp_path / "events").read_text().split()
    assert events[0] == "launch", events           # never before first launch
    assert "cleanup" in events, events             # ran on restarts
    # strict alternation after the first launch: every relaunch is preceded
    # by exactly one cleanup
    for i, e in enumerate(events):
        if e == "launch" and i > 0:
            assert events[i - 1] == "cleanup", events
    # the stubbed pkill actually executed (the path is exercised, not argued)
    pk = (tmp_path / "pkill.log").read_text()
    assert "Xvfb" in pk and "socat" in pk, pk


def test_ladder_is_opt_in_and_disabled_ladder_never_steps(monkeypatch):
    """Casey 2026-08-24: ladder off for now. Two properties: the flag
    defaults FALSE (fresh deploys are ladder-off), and a disabled ladder's
    step() is unreachable from the loop body's gate."""
    from app.config import Settings
    assert Settings().ladder_enabled is False
    import inspect
    import app.service as svc
    src = inspect.getsource(svc._loop)
    gate = src.index("if settings.ladder_enabled:")
    step = src.index("MGR.step(")
    save = src.index("MGR.save()")
    assert gate < step < save, "step/save not inside the enabled gate"
