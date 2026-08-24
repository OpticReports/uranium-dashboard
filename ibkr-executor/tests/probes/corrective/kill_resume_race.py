"""B7: the measurement behind LADDER_KILL_LOCK.

Not a counter-agent attack suite and not a gate — the gates are
`test_gate_b7_a_kill_racing_a_resume_never_leaves_a_split_record` (the
deterministic interleaving) and
`test_gate_b7_concurrent_kill_resume_pairs_stay_serialisable` (this shape,
in the suite). This is the REPRODUCTION whose numbers the code comments and
the executor README cite.

What it shows: the ladder kill RECORD has three halves — the book's
`halted`, the `LADDER_KILL` event, and the on-disk `<STATE_PATH>.kill`
sentinel. `/resume` wrote all three under MGR_LOCK. `/kill` wrote all three
under NO LOCK, deliberately (MGR_LOCK is held by a cycle across unbounded
gateway I/O, so the emergency stop may never wait on it) — but nothing
replaced the mutual exclusion it gave up. A concurrent pair can therefore
land on a state NEITHER serial order can reach, the worst being:

    halted=None, LADDER_KILL clear, sentinel PRESENT

i.e. /kill answered `close_queued`, the kill was silently dropped by the
loop, the leg stayed OPEN forever — and the surviving sentinel resurrected
the CANCELLED kill on the next restart.

    python tests/probes/corrective/kill_resume_race.py   # from ibkr-executor/

Measured HERE at cc03347 (before the fix), 1200 pairs per run:
    2/1200, 2/1200, 3/1200   (and 1/400, 0/400, 1/400 at 400 pairs)
    the split seen: (halted, LADDER_KILL, sentinel, kill_pending) =
      (False, False, True, True)  -> the resurrecting sentinel
      (True,  False, True, True)  -> halted, but the loop will DROP the kill
Measured after the fix, same rig:
    0/1200, 0/1200, 0/1200

HONESTY: the judge's report cites 143/400 for this defect. This rig, driving
the handler functions directly, lands it far less often — the window is the
few hundred microseconds between `LADDER_KILL.set()` and the sentinel
rename, and the two threads spend comparable time elsewhere. The rate is
NOT the finding; the reachability is, and the deterministic gate
(`test_gate_b7_a_kill_racing_a_resume_never_leaves_a_split_record`) forces
the interleaving rather than waiting for it.

Exits non-zero when the race LANDS.
"""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.getcwd())
sys.setswitchinterval(1e-6)

from app import service                          # noqa: E402
from app.config import settings                  # noqa: E402
from app.manager import LadderManager            # noqa: E402

PAIRS = int(os.environ.get("PAIRS", "1200"))


def main() -> int:
    d = tempfile.mkdtemp()
    settings.state_path = os.path.join(d, "s.json")
    settings.exec_token = "sekrit"
    settings.tws_userid = ""
    settings.blend_enabled = False
    mgr = LadderManager(settings, settings.state_path)
    service.MGR = mgr
    service.BLEND = None
    service.ADAPTER = None
    service.send = lambda *_a, **_k: None
    service.LOOP_WAKE = threading.Event()
    service.LADDER_KILL.clear()
    leg = list(mgr.state.legs)[0]
    mgr.on_opened(leg, 10_000, "ref-1", "2026-08-01")

    bad = []
    for _ in range(PAIRS):
        start = threading.Barrier(2)

        def do_kill():
            start.wait()
            service.kill(x_exec_token="sekrit", token=None)

        def do_resume():
            start.wait()
            service.resume(x_exec_token="sekrit", token=None)

        kt = threading.Thread(target=do_kill)
        rt = threading.Thread(target=do_resume)
        kt.start()
        rt.start()
        kt.join(10)
        rt.join(10)
        rec = (mgr.state.halted == "KILL", service.LADDER_KILL.is_set(),
               os.path.exists(mgr.kill_sentinel), mgr.kill_pending)
        if rec not in ((True, True, True, True), (False, False, False, False)):
            bad.append(rec)
        service.resume(x_exec_token="sekrit", token=None)
        mgr.on_opened(leg, 10_000, "ref-1", "2026-08-01")

    print(f"split kill records in {PAIRS} concurrent /kill+/resume pairs: "
          f"{len(bad)}")
    for rec in bad[:3]:
        print("  e.g. (halted, flag, sentinel, kill_pending) =", rec)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
