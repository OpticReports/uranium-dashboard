"""mf3-10: the measurement behind the `save()` snapshot fix.

Not a counter-agent attack suite and not a gate — the gate is
`test_gate_mf3_10_save_never_raises_while_the_book_is_mutated`. This is the
REPRODUCTION whose numbers the code comments and README cite, versioned so a
later reviewer can re-run them instead of taking the sentence on trust
(probes/README rule: an unversioned gate is not a gate).

What it shows: `Blend3070Manager.save()` walked LIVE dicts — mf2-9's
stand-in prune iterated `self.state.stand_in_rows` while the loop thread
inserted into it — under a comment arguing the state object is safe because
it is "mutated field-by-field under the GIL". A Python-level walk yields
between elements, so CPython raises
`RuntimeError: dictionary changed size during iteration`. Two API-thread
savers (which is what `/kill`'s `request_flatten` is) against three
mutators reproduce it.

The GIL switch interval is narrowed the way the mf-8 gate widens its own
window: the race is real at the default interval too (the reviewer measured
3 raises in 8s), just rarer per unit time.

    python tests/probes/mf3/save_race.py          # from ibkr-executor/

Measured at 0433d4a (before the fix):  1, 2, 4, 5, 8, 8, 9, 10 raises per
                                       8s run over 8 runs, every one at the
                                       mf2-9 prune comprehension.
Measured after the fix:                0 over 6 runs.
"""
import os
import sys
import tempfile
import threading
import time
import traceback

sys.path.insert(0, os.getcwd())
sys.setswitchinterval(1e-6)

from app.blend import Blend3070Manager          # noqa: E402
from app.config import settings                 # noqa: E402

DURATION_S = 8.0
ROWS = 400
PADDING = 20_000


def main() -> int:
    d = tempfile.mkdtemp()
    m = Blend3070Manager(settings, os.path.join(d, "b.json"))
    m.state.initialized = True
    m.state.sleeve_cash = 100_000.0
    for i in range(ROWS):
        m.on_entered({"call_id": i, "symbol": "AAA", "qty": 1,
                      "entry_ref": 1.0, "stop_level": 0.5}, 1.0,
                     f"ref-{i}", "2026-08-24")
        m.state.stand_in_rows[str(i)] = ["qty"]
    for i in range(PADDING):
        m.state.stand_in_rows[f"x{i}"] = ["qty"]

    stop = threading.Event()
    errs: list[str] = []

    def mutator():
        i = 1_000_000
        while not stop.is_set():
            k = str(i)
            m.state.stand_in_rows[k] = ["qty"]
            m.state.positions[k] = m.state.positions["0"]
            m.state.stand_in_rows[k + "b"] = ["qty"]
            del m.state.stand_in_rows[k]
            del m.state.stand_in_rows[k + "b"]
            m.state.positions.pop(k, None)
            i += 1

    def saver():
        while not stop.is_set():
            try:
                m.save()
            except Exception as exc:                    # noqa: BLE001
                tb = traceback.extract_tb(exc.__traceback__)[-1]
                errs.append(f"{type(exc).__name__}: {exc} "
                            f"@ {os.path.basename(tb.filename)}:{tb.lineno} "
                            f"`{(tb.line or '').strip()}`")

    threads = [threading.Thread(target=mutator, daemon=True) for _ in range(3)]
    threads += [threading.Thread(target=saver, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(DURATION_S)
    stop.set()
    for t in threads:
        t.join(timeout=5)

    for e in errs[:6]:
        print("  ", e)
    print(f"save() raises in {DURATION_S:.0f}s: {len(errs)} "
          f"({'LANDED — save() is not thread-safe' if errs else 'clean'})")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
