"""Gates for the gateway-outage ledger and the supervisor contract."""
import json
import os
import subprocess
import time

from app.outages import OutageLog


def test_outage_recorded_with_blocked_cycles(tmp_path):
    lg = OutageLog(str(tmp_path / "o.json"))
    t0 = time.time()
    lg.start(t0)
    lg.start(t0 + 1)                      # idempotent: one outage, not two
    for _ in range(4):
        lg.cycle_blocked()
    lg.mark_alerted()
    rec = lg.end(t0 + 120)
    assert rec["ended_by"] == "reconnect"
    assert rec["duration_s"] == 120.0
    assert rec["cycles_blocked"] == 4
    assert rec["alerted"] is True
    assert len(lg.history) == 1 and lg.open is None


def test_outage_survives_restart_and_is_marked_not_self_healed(tmp_path):
    """THE distinction the in-memory flag could never make: an outage the
    process did not survive did NOT self-heal, and that is exactly what
    supervision is supposed to eliminate."""
    p = str(tmp_path / "o.json")
    lg = OutageLog(p)
    lg.start(time.time() - 600)
    lg.cycle_blocked()
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
        lg.start(now - 100 * (i + 1)); lg.cycle_blocked(); lg.end(now - 100 * i)
    lg.history.append({"start_ts": now - 50, "end_ts": now, "duration_s": 50.0,
                       "ended_by": "process_restart", "cycles_blocked": 2,
                       "alerted": True})
    s = lg.summary()
    assert s["outages"] == 4
    assert s["self_healed"] == 3 and s["needed_a_restart"] == 1
    assert s["cycles_blocked"] == 5
    assert s["alerted"] == 1


def test_ledger_never_breaks_trading_on_a_bad_path(tmp_path):
    """Observability must not be able to take the executor down."""
    lg = OutageLog("/nonexistent-dir/deny/o.json")
    lg.start(); lg.cycle_blocked(); lg.mark_alerted()
    assert lg.end() is not None           # in-memory still coherent
    bad = tmp_path / "corrupt.json"
    bad.write_text("{not json")
    lg2 = OutageLog(str(bad))             # unreadable -> fresh, no raise
    assert lg2.history == [] and lg2.open is None
    assert OutageLog(None).summary()["outages"] == 0


def test_adapter_tolerates_absent_ledger():
    """outage_log is optional everywhere it is touched."""
    import inspect
    from app.ib_adapter import IBAdapter
    sig = inspect.signature(IBAdapter.__init__)
    assert sig.parameters["outage_log"].default is None
    src = inspect.getsource(IBAdapter)
    for call in ("self.outages.start", "self.outages.end",
                 "self.outages.cycle_blocked", "self.outages.mark_alerted"):
        i = src.index(call)
        assert "if self.outages:" in src[max(0, i - 400):i], call


def test_supervisor_restarts_a_dying_gateway_with_backoff(tmp_path):
    """The whole point of the change: an unsupervised `"$GW" &` left a dead
    gateway dead until a human redeployed, while /health stayed 200."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gw = tmp_path / "gw.sh"
    gw.write_text("#!/usr/bin/env bash\necho x >> %s\nexit 7\n"
                  % (tmp_path / "count"))
    gw.chmod(0o755)
    runner = tmp_path / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\nset -u\n"
        f"RESTART_LOG={tmp_path}/r.jsonl\n"
        "BACKOFF_MIN_S=1; BACKOFF_MAX_S=4; HEALTHY_S=99\n"
        "eval \"$(sed -n '/^log_restart()/,/^}$/p;"
        "/^supervise_gateway()/,/^}$/p' %s/start.sh)\"\n"
        "supervise_gateway \"$1\"\n" % root)
    runner.chmod(0o755)
    subprocess.run(["timeout", "8", str(runner), str(gw)],
                   capture_output=True)
    launches = len(open(tmp_path / "count").read().split())
    assert launches >= 2, "gateway was never restarted"
    assert launches <= 6, f"hot restart loop: {launches} launches in 8s"
    recs = [json.loads(l) for l in open(tmp_path / "r.jsonl")]
    assert [r["next_delay_s"] for r in recs][:3] == [1, 2, 4], recs
    assert all(r["exit_code"] == 7 for r in recs)


def test_supervisor_does_not_resurrect_on_shutdown_signal(tmp_path):
    """A restart loop that fights container teardown would resurrect the
    gateway mid-shutdown."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "start.sh")).read()
    assert "-eq 143" in src and "-eq 130" in src, "no signal guard"
    assert "trap" in src, "supervisor is not stopped on TERM/INT"


def test_health_never_fails_on_gateway_state():
    """Wiring gateway health into `status` would make Render restart the
    whole container - executor included, possibly mid-order - on every
    routine gateway blip, including the mandatory daily restart."""
    import inspect
    import app.service as svc
    src = inspect.getsource(svc.health)
    assert '"status": "ok"' in src
    body = src[src.index('body = {'):]
    assert 'body["status"]' not in body, "gateway state must not gate health"
