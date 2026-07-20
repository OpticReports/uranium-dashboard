"""Evidence bundler + sufficiency check for the tuning loop (see TUNING.md).

Turns the /tuning/evidence blob (or the local DB) into a readable evidence
summary and a per-lane verdict: which kinds of proposal the record can
currently support. The tuner agent runs this FIRST; if every lane says
insufficient, the correct output of the cycle is "no proposal".

Usage:
  python -m scripts.tune_proposal --json evidence.json   # from a dump
  python -m scripts.tune_proposal --local                # where the DB lives
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_FLAG_N = 20      # graded 1m outcomes per signal before a trigger proposal
MIN_CALLS = 10       # newly closed calls before an exit-param proposal
MIN_BAND_N = 10      # closed calls per conviction band before a gate proposal


def load_local() -> dict:
    from sqlmodel import Session

    from app.db import engine
    from app.routers.tuning import tuning_evidence

    with Session(engine) as session:
        return tuning_evidence(session=session)


def lane_verdicts(ev: dict) -> dict[str, dict]:
    counts = ev.get("counts", {})
    track = ev.get("flag_track_record", {}).get("by_flag_type", {})
    bands = ev.get("conviction_bands", [])

    trigger_ready = {
        ftype: h["n"]
        for ftype, stats in track.items()
        if (h := stats.get("horizons", {}).get("1m", {})) and (h.get("n") or 0) >= MIN_FLAG_N
    }
    band_ready = [b for b in bands if (b.get("n") or 0) >= MIN_BAND_N]

    return {
        "trigger_promotion_demotion": {
            "sufficient": bool(trigger_ready),
            "detail": (f"signals at n>={MIN_FLAG_N}: {trigger_ready}" if trigger_ready
                       else f"no signal has {MIN_FLAG_N}+ graded 1m outcomes yet"),
            "gate": "python -m evals.replay promotion --flag-type <type> [--demote]",
        },
        "exit_params": {
            "sufficient": (counts.get("closed_calls") or 0) >= MIN_CALLS,
            "detail": f"closed calls: {counts.get('closed_calls', 0)} (need >= {MIN_CALLS})",
            "gate": "python -m scripts.backtest_calls --refresh (plateau + net-R rules in TUNING.md)",
        },
        "weights": {
            "sufficient": False,  # the ic gate self-reports data sufficiency at run time
            "detail": ("run the ic gate where score-snapshot history lives; it exits 2 "
                       "until >=10 evaluable days exist"),
            "gate": "python -m evals.replay ic --proposed <file>",
        },
        "conviction_gate": {
            "sufficient": len(band_ready) >= 2,
            "detail": (f"bands at n>={MIN_BAND_N}: {[b['band'] for b in band_ready]}"
                       if band_ready else "no conviction band has enough closed calls"),
            "gate": "band comparison in this bundle (TUNING.md matrix)",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--json", help="path to a /tuning/evidence JSON dump")
    src.add_argument("--local", action="store_true", help="read the local DB")
    args = ap.parse_args()

    ev = json.loads(Path(args.json).read_text()) if args.json else load_local()
    verdicts = lane_verdicts(ev)

    print("# Tuning evidence summary\n")
    print(f"generated_at: {ev.get('generated_at')}")
    print(f"counts: {json.dumps(ev.get('counts', {}))}\n")

    print("## Flag track record (1m horizon)")
    for ftype, stats in sorted(ev.get("flag_track_record", {}).get("by_flag_type", {}).items()):
        h = stats.get("horizons", {}).get("1m", {})
        print(f"- {ftype}: fired={stats.get('fired')} n_1m={h.get('n')} "
              f"hit={h.get('hit_rate')} avg_excess={h.get('avg_excess')} basis={h.get('basis')}")

    print("\n## Calls scorecard (overall)")
    print(json.dumps(ev.get("calls_scorecard", {}).get("overall", {}), indent=1))

    print("\n## Conviction bands (composite at call -> closed-call results)")
    for b in ev.get("conviction_bands", []):
        print(f"- {b['band']}: n={b['n']} win={b['win_rate']} avg_r={b['avg_r']}")

    print("\n## Monthly call cohorts")
    for m in ev.get("calls_performance", {}).get("monthly_cohorts", []):
        print(f"- {m['month']}: n={m['n']} win={m['win_rate']} avg_r={m['avg_r']}")

    print("\n## Current config (tunable surface)")
    print(json.dumps(ev.get("configs", {}), indent=1))

    print("\n## Lane verdicts")
    any_ok = False
    for lane, v in verdicts.items():
        mark = "READY" if v["sufficient"] else "insufficient"
        any_ok = any_ok or v["sufficient"]
        print(f"- {lane}: {mark} — {v['detail']}\n    gate: {v['gate']}")

    print(f"\nVERDICT: {'evidence available for at least one lane' if any_ok else 'INSUFFICIENT EVIDENCE — correct action is NO PROPOSAL this cycle'}")


if __name__ == "__main__":
    main()
