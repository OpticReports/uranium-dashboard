"""B6: the measurement behind the `status_summary()` / `feed()` snapshots.

Not a counter-agent attack suite and not a gate — the gate is
`test_gate_b6_status_and_feed_survive_threaded_load_during_a_flatten`. This
is the REPRODUCTION whose numbers the code comments and the executor README
cite, versioned so a later reviewer can re-run them instead of taking the
sentence on trust (probes/README rule: an unversioned gate is not a gate).

What it shows: mf3-10 proved that a Python-level walk of a dict another
thread inserts into raises `RuntimeError: dictionary changed size during
iteration`, and fixed `save()`. It fixed NOTHING ELSE. `status_summary()`
and `feed()` run on FastAPI WORKER threads and kept walking the same live
containers — `positions`, `stand_in_rows`, `unreconciled` — so `/status`
raised during exactly the window the operator is told to watch: a /kill
flatten. `/status` is also the ONLY surface carrying `flatten_pending`,
`unprotected`, `unverifiable` and `stand_in_rows`.

    python tests/probes/corrective/status_race.py     # from ibkr-executor/

Measured HERE at cc03347 (before the fix), 4 readers vs 3 mutators + 1
flatten thread, over 6s:
    reads 264  raises 48  (18.2%)
    reads 264  raises 48  (18.2%)
    reads 257  raises 48  (18.7%)
    every one `RuntimeError: dictionary changed size during iteration`
Measured after the fix, same load:
    reads 263  raises 0
    reads 236  raises 0
    reads 276  raises 0
(The judge's own figure for the deployed shape was 10-16% of /status
requests; this rig's readers do nothing but read, so its rate is higher.)

Exits non-zero when the race LANDS.
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.getcwd())
sys.setswitchinterval(1e-6)

from app.blend import (Blend3070Manager, BlendPosition,      # noqa: E402
                       execute_flatten)
from app.config import settings                              # noqa: E402
from app.ib_adapter import DryAdapter                        # noqa: E402

DURATION_S = 6.0
ROWS = 300
PADDING = 5_000
PRICES = {"SPY": 100.0, "BIL": 100.0, "AAA": 1.0, "BBB": 1.0}


def _pos(i, sym="AAA"):
    return BlendPosition(call_id=i, symbol=sym, qty=1, entry_ref=1.0,
                         fill_price=1.0, entry_date="2026-08-01",
                         time_stop="2026-11-01", stop_level=0.5)


def main() -> int:
    d = tempfile.mkdtemp()
    m = Blend3070Manager(settings, os.path.join(d, "b.json"))
    m.state.initialized = True
    m.state.sleeve_cash = 100_000.0
    for i in range(ROWS):
        m.state.positions[str(i)] = _pos(i)
        m.state.stand_in_rows[str(i)] = ["qty"]
        m.state.unreconciled[str(i)] = {"symbol": "AAA", "qty": 1}
    for i in range(PADDING):
        m.state.stand_in_rows[f"x{i}"] = ["qty"]
        m.state.unreconciled[f"x{i}"] = {"symbol": "AAA", "qty": 1}

    stop = threading.Event()
    reads = [0]
    raises: list[str] = []
    lock = threading.Lock()

    def reader():
        n = 0
        errs = []
        while not stop.is_set():
            try:
                m.status_summary(PRICES)
                m.feed(PRICES, "2026-08-21")
                n += 1
            except Exception as exc:                    # noqa: BLE001
                errs.append(f"{type(exc).__name__}: {exc}")
        with lock:
            reads[0] += n
            raises.extend(errs)

    def mutator():
        i = 1_000_000
        while not stop.is_set():
            k = str(i)
            m.state.positions[k] = _pos(i, "BBB")
            m.state.stand_in_rows[k] = ["qty"]
            m.state.unreconciled[k] = {"symbol": "BBB", "qty": 1}
            m.state.positions.pop(k, None)
            m.state.stand_in_rows.pop(k, None)
            m.state.unreconciled.pop(k, None)
            i += 1

    def flattener():
        a = DryAdapter()
        while not stop.is_set():
            m.state.flatten_request = {"ts": 0, "date": "2026-08-21"}
            try:
                execute_flatten(m, a, lambda _msg: None)
            except Exception:                           # noqa: BLE001
                pass

    threads = ([threading.Thread(target=reader, daemon=True)
                for _ in range(4)]
               + [threading.Thread(target=mutator, daemon=True)
                  for _ in range(3)]
               + [threading.Thread(target=flattener, daemon=True)])
    for t in threads:
        t.start()
    time.sleep(DURATION_S)
    stop.set()
    for t in threads:
        t.join(30)

    pct = (100.0 * len(raises) / reads[0]) if reads[0] else 0.0
    print(f"/status+/blend/feed reads in {DURATION_S:.0f}s: {reads[0]}  "
          f"raises: {len(raises)} ({pct:.1f}%)")
    for line in raises[:3]:
        print("  e.g.", line)
    return 1 if raises else 0


if __name__ == "__main__":
    raise SystemExit(main())
