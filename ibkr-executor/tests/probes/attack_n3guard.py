"""Adversarial probes for commit 64c0275 (N3 fix + mode-transition guard).

Run from ibkr-executor/:  python <scratchpad>/attack_n3guard.py
Each probe prints PASS/FAIL; failures are attacks that LANDED.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.getcwd())

from app import blend as blend_mod                      # noqa: E402
from app.blend import Blend3070Manager, run_cycle       # noqa: E402
from app.ib_adapter import DryAdapter                   # noqa: E402


class Cfg:
    blend_budget = 0.0
    blend_book_usd = 10_000.0
    tracker_url = ""
    tracker_user = ""
    tracker_password = ""
    dry_run = True
    trading_mode = "paper"
    # what config.Settings really carries (tests' Cfg omits these):
    tws_userid = ""
    tws_password = ""


def mk(tmp, **over):
    cfg = Cfg()
    for k, v in over.items():
        setattr(cfg, k, v)
    return Blend3070Manager(cfg, os.path.join(tmp, "blend.json"))


def payload():
    return {
        "as_of": "2026-08-20",
        "gate": {"xbi_above_200dma_prior": True, "since": None},
        "entries": [], "exits": [], "stops": [],
        "rebalance": {"needed": None, "current_sleeve_weight": None,
                      "target": 0.30},
        "book_params": {"max_open": 10, "risk_frac": 0.01, "band": 0.05,
                        "cash_vehicle": "BIL", "core": "SPY"},
        "contract": "executor reconciles and sizes",
    }


RESULTS = []


def probe(name):
    def deco(fn):
        RESULTS.append((name, fn))
        return fn
    return deco


def tmpdir(tag):
    import tempfile
    return tempfile.mkdtemp(prefix=f"n3guard-{tag}-")


# ---------------------------------------------------------------------------
@probe("G1 OFFLINE bypass: DryAdapter fills mode-tagged 'real:paper' "
       "(creds absent + DRY_RUN=false) survive into a credentialed session")
def g1():
    tmp = tmpdir("g1")
    # Service _build: no TWS creds -> DryAdapter, REGARDLESS of dry_run.
    # But _current_mode derives from dry_run alone -> "real:paper".
    m = mk(tmp, dry_run=False)          # OFFLINE service with DRY_RUN=false
    # FIXED contract: creds absent -> tagged dry regardless of DRY_RUN
    assert m._current_mode() == "dry:paper", m._current_mode()
    run_cycle(m, DryAdapter(), payload(), "2026-08-20", alert=lambda _: None)
    assert m.state.spy_qty == 70        # $100-placeholder fills
    raw = json.load(open(m.state_path))
    assert raw["mode"] == "dry:paper"   # fiction tagged as fiction
    # Creds restored -> real gateway session: fiction must be archived.
    m2 = mk(tmp, dry_run=False, tws_userid="u", tws_password="p")
    kept = m2.archived_state is None and m2.state.spy_qty == 70
    return (not kept,
            f"placeholder book kept into real:paper session={kept} "
            f"(archived_state={m2.archived_state!r}, spy={m2.state.spy_qty}) "
            f"— the exact disaster the guard exists to stop, via the "
            f"missing-credentials OFFLINE path")


@probe("G1b reverse hole: creds pulled mid-PAPER (OFFLINE, DRY_RUN=false) "
       "keeps the REAL book and lets the DryAdapter trade it")
def g1b():
    tmp = tmpdir("g1b")
    m = mk(tmp, dry_run=False,          # genuine real:paper book
           tws_userid="u", tws_password="p")
    m.state.initialized = True
    m.state.spy_qty = 12                # real paper fills (pretend)
    m.state.core_cash = 0.0
    m.state.sleeve_cash = 3000.0
    m.save()
    # Ops pulls the TWS creds (gateway emergency); DRY_RUN stays false.
    # Service reboots OFFLINE -> DryAdapter. Mode still "real:paper":
    m2 = mk(tmp, dry_run=False)
    kept = m2.archived_state is None
    if kept:
        run_cycle(m2, DryAdapter(), payload(), "2026-08-21",
                  alert=lambda _: None)
    mutated = kept and (m2.state.trades or m2.state.spy_qty != 12
                        or m2.state.bil_qty != 0)
    return (not mutated,
            f"real book kept={kept}, mutated by DryAdapter cycle={bool(mutated)} "
            f"(trades={len(m2.state.trades)}, spy={m2.state.spy_qty}, "
            f"bil={m2.state.bil_qty}) — $100-placeholder fills booked into "
            f"a real:paper book")


@probe("G2 archive os.replace failure -> guard still starts fresh, but "
       "silently (no alert) and first save destroys the old book")
def g2():
    tmp = tmpdir("g2")
    m = mk(tmp)                          # dry:paper book with holdings
    m.state.initialized = True
    m.state.spy_qty = 700
    m.save()
    real_replace = blend_mod.os.replace

    def flaky(src, dst):
        if ".archived-" in str(dst):
            raise PermissionError("simulated: archive rename denied")
        return real_replace(src, dst)

    blend_mod.os.replace = flaky
    try:
        m2 = mk(tmp, dry_run=False)      # mode change -> archive attempt fails
    finally:
        blend_mod.os.replace = real_replace
    fresh = m2.state.spy_qty == 0
    silent = m2.archived_state is None
    m2.save()                            # first save clobbers the old file
    archives = [f for f in os.listdir(tmp) if ".archived-" in f]
    lost = not archives and json.load(open(m2.state_path))["spy_qty"] == 0
    # Fresh book (safe direction) but NO alert and old book unrecoverable.
    return (not (fresh and silent and lost),
            f"fresh={fresh} no_alert={silent} old_book_lost={lost} "
            f"(fails SAFE re trading, fails SILENT re alert/forensics)")


@probe("G3 corrupt state (matching mode / truncated json) still resolves "
       "to a fresh book SILENTLY — no archive, no archived_state alert")
def g3():
    tmp = tmpdir("g3")
    path = os.path.join(tmp, "blend.json")
    # (a) valid JSON, matching mode, position row with an unknown field
    json.dump({"mode": "dry:paper", "initialized": True, "spy_qty": 70,
               "positions": {"1": {"bogus_field": 1}}}, open(path, "w"))
    ma = mk(tmp)
    a_silent = ma.archived_state is None and ma.state.spy_qty == 0
    # (b) truncated file (external corruption — atomic save only protects
    #     against OUR writer)
    open(path, "w").write('{"mode": "dry:paper", "initialized": tru')
    mb = mk(tmp)
    b_silent = mb.archived_state is None and mb.state.spy_qty == 0
    return (not (a_silent or b_silent),
            f"schema-corrupt silent fresh={a_silent}, truncated silent "
            f"fresh={b_silent} — fresh-empty-book path still reachable "
            f"without any alert (N3 claim covers only OUR truncation)")


# G4 REWRITTEN for the x11 fix (the old assertion pinned the mechanic the
# fix legitimately changes: ONE shared "<state>.tmp" path). The new contract
# is STRICTLY HARDER — the old probe tolerated a stale scratch file being
# left behind and only checked it was not ACCUMULATED; this one demands zero
# leftovers, still demands the successful save + reload, AND additionally
# demands that _load ignores an injected stray tmp and that concurrent
# savers never collide on a temp name.
@probe("G4 .tmp hygiene: a failed save leaves NO scratch file at all; a "
       "stray tmp is inert; concurrent savers never share a temp name")
def g4():
    tmp = tmpdir("g4")
    m = mk(tmp)
    m.state.initialized = True
    m.state.spy_qty = 70
    m.save()
    real_dump = blend_mod.json.dump

    def bad_dump(obj, fh, **kw):
        fh.write('{"partial')
        raise IOError("disk full")

    for _ in range(3):                   # three failing saves
        blend_mod.json.dump = bad_dump
        try:
            m.save()
        except IOError:
            pass
        finally:
            blend_mod.json.dump = real_dump
    tmps = [f for f in os.listdir(tmp) if f.endswith(".tmp")]
    no_tmp = tmps == []
    # a stray tmp (e.g. from a SIGKILL between mkstemp and replace) is inert
    open(os.path.join(tmp, "blend.json.stray.tmp"), "w").write('{"partial')
    m.state.spy_qty = 71
    m.save()
    ok_after = json.load(open(m.state_path))["spy_qty"] == 71
    m2 = mk(tmp)                         # _load never touches the tmp
    # temp names must be unique per write, so racing writers cannot clobber
    seen = []
    real_replace = blend_mod.os.replace

    def spy_replace(src, dst):
        seen.append(src)
        return real_replace(src, dst)

    blend_mod.os.replace = spy_replace
    try:
        for _ in range(5):
            m.save()
    finally:
        blend_mod.os.replace = real_replace
    unique = len(set(seen)) == len(seen) == 5
    return (no_tmp and ok_after and m2.state.spy_qty == 71 and unique,
            f"tmps_after_3_failures={tmps} reload_spy={m2.state.spy_qty} "
            f"unique_temp_names={unique} ({len(set(seen))}/{len(seen)})")


@probe("G5 crash BETWEEN fsync and rename: state file stays last-good; "
       "reload is the old book, leftover tmp inert")
def g5():
    tmp = tmpdir("g5")
    m = mk(tmp)
    m.state.initialized = True
    m.state.spy_qty = 70
    m.save()
    real_replace = blend_mod.os.replace

    def crash(src, dst):
        raise OSError("simulated crash before rename")

    blend_mod.os.replace = crash
    m.state.spy_qty = 999
    try:
        m.save()
    except OSError:
        pass
    finally:
        blend_mod.os.replace = real_replace
    m2 = mk(tmp)
    return (m2.state.spy_qty == 70 and m2.state.initialized,
            f"reloaded spy={m2.state.spy_qty} (last good, not 999/fresh)")


@probe("G6 resume BEFORE loop pickup: request cleared, flatten never runs, "
       "book un-halted and intact (re-assert must NOT fire)")
def g6():
    tmp = tmpdir("g6")
    m = mk(tmp)
    m.state.initialized = True
    m.state.sleeve_cash = 2750.0
    m.on_entered({"call_id": 1, "symbol": "CRSP", "qty": 5,
                  "entry_ref": 50.0, "stop_level": 44.0},
                 50.0, "entry-ref", "2026-08-01")
    m.state.positions["1"].time_stop = "2026-10-30"
    m.state.positions["1"].stop_order_ref = "stp-1"
    m.request_flatten("2026-08-21")
    m.resume()                           # operator resumes before pickup
    ad = DryAdapter()
    run_cycle(m, ad, None, "2026-08-21", alert=lambda _: None)
    sells = [o for o in ad.log
             if o.get("symbol") == "CRSP" and o.get("qty", 0) < 0]
    ok = (m.state.flatten_request is None and m.state.halted is None
          and "1" in m.state.positions and not sells)
    return (ok, f"halted={m.state.halted!r} pos_kept={'1' in m.state.positions} "
                f"crsp_sells={len(sells)}")


@probe("G7 kill queued -> restart (same mode): flatten request survives "
       "the restart and executes; book re-halted")
def g7():
    tmp = tmpdir("g7")
    m = mk(tmp)
    m.state.initialized = True
    m.state.sleeve_cash = 2750.0
    m.on_entered({"call_id": 1, "symbol": "CRSP", "qty": 5,
                  "entry_ref": 50.0, "stop_level": 44.0},
                 50.0, "entry-ref", "2026-08-01")
    m.state.positions["1"].time_stop = "2026-10-30"
    m.request_flatten("2026-08-21")      # saves
    m2 = mk(tmp)                         # restart, same mode: NOT archived
    survived = (m2.archived_state is None
                and m2.state.flatten_request is not None
                and m2.state.halted == "KILL")
    run_cycle(m2, DryAdapter(), payload(), "2026-08-21",
              alert=lambda _: None)
    done = (m2.state.flatten_request is None and m2.state.halted == "KILL"
            and m2.state.positions == {})
    return (survived and done,
            f"request_survived_restart={survived} flattened_and_rehalted={done}")


@probe("G8 legacy untagged archived ONCE; subsequent same-mode restarts "
       "keep the book (OFFLINE<->DRY continuity)")
def g8():
    tmp = tmpdir("g8")
    path = os.path.join(tmp, "blend.json")
    json.dump({"initialized": True, "spy_qty": 700}, open(path, "w"))
    m = mk(tmp)                          # dry:paper — untagged: archive
    first = m.archived_state is not None and m.state.spy_qty == 0
    m.state.initialized = True
    m.state.spy_qty = 70
    m.save()
    m2 = mk(tmp)                         # OFFLINE->DRY: both dry:paper
    second = m2.archived_state is None and m2.state.spy_qty == 70
    return (first and second, f"untagged_archived={first} tagged_kept={second}")


@probe("G9 unlocked concurrent save() corrupts (shared constant tmp path) — "
       "lock discipline is load-bearing; verify current callers are locked")
def g9():
    # Informational: proves save() is NOT internally safe for concurrent
    # callers (shared blend.json.tmp), i.e. the BLEND_LOCK audit matters.
    tmp = tmpdir("g9")
    m = mk(tmp)
    m.state.initialized = True
    m.save()
    errors = []
    corrupt = [False]

    def hammer(n):
        for i in range(150):
            try:
                m.state.spy_qty = n * 1000 + i
                m.save()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

    ts = [threading.Thread(target=hammer, args=(k,)) for k in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    try:
        json.load(open(m.state_path))
    except Exception:  # noqa: BLE001
        corrupt[0] = True
    # PASS regardless — this is evidence for the audit, not a gate; but a
    # corrupt final file or FileNotFoundError storm shows the hazard is real.
    return (True, f"unlocked hammering: save_errors={len(errors)} "
                  f"final_file_corrupt={corrupt[0]} "
                  f"(all production callers verified under BLEND_LOCK "
                  f"or loop-thread-only — see verdict)")


def main():
    passed = failed = 0
    fails = []
    for name, fn in RESULTS:
        try:
            ok, detail = fn()
        except Exception:
            ok, detail = False, "EXCEPTION\n" + traceback.format_exc()
        tag = "PASS" if ok else "FAIL"
        print(f"{tag} {name}\n     | {detail}")
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append(name.split(" ")[0])
    print(f"\n{passed}/{passed + failed} probes passed; landed attacks: {fails}")


if __name__ == "__main__":
    main()
