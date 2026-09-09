"""Produce the M&A cycle reading series from the data layer.

Composes ma_data (fetch/align/orient) with ma_cycle (the parameter-free
scoring) and emits one reading per quarter. Kept separate from both so
the scoring can be gate-tested on synthetic inputs without a network,
and the data layer audited without running the model.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ma_cycle as mc      # noqa: E402
import ma_data as md       # noqa: E402

H = mc.MOMENTUM_LOOKBACK_QUARTERS   # clock momentum, NOT the 5y cycle horizon


def _regime_ok(sid, quarters, i, h):
    """Momentum may not straddle a definitional break.

    A lookback from just after the HSR threshold change reaches back
    across it and would read a legislative redefinition as a collapse
    in deal activity. Momentum is only defined once BOTH endpoints sit
    inside the same regime.
    """
    if sid != "HSR_COUNT":
        return True
    j = i - h
    if j < 0:
        return False
    return md.scoreable(sid, quarters[j]) and md.scoreable(sid, quarters[i])


def build_readings():
    _, q = md.build(refresh=False)
    oriented = {sid: md.oriented(q, sid) for sid in md.COMPONENTS}

    # Common quarterly spine: first quarter any component exists, to
    # the last quarter ANY component has data. Components that do not
    # reach a quarter simply score None there and the coverage rule
    # decides whether a reading is emitted at all.
    allq = sorted({k for s in oriented.values() for k in s},
                  key=lambda x: (int(x[:4]), int(x[5])))
    quarters = md.quarter_range(allq[0], allq[-1])

    # Dense per-component arrays on the spine.
    cols = {sid: [oriented[sid].get(t) for t in quarters]
            for sid in md.COMPONENTS}

    hsr_break = [i for i, t in enumerate(quarters)
                 if not md.scoreable("HSR_COUNT", t)]
    hsr_regime_starts = [max(hsr_break) + 1] if hsr_break else []

    readings = []
    for i, t in enumerate(quarters):
        lv, mo = [], []
        for sid in md.COMPONENTS:
            col = cols[sid]
            # LEVEL
            if col[i] is None or not md.scoreable(sid, t):
                lv.append(None)
            elif sid == "HSR_COUNT":
                lv.append(mc.percentile_rank_within_regime(
                    col, i, hsr_regime_starts))
            else:
                lv.append(mc.percentile_rank_expanding(col, i))
            # MOMENTUM: 5y difference, then ranked the same expanding way
            if not _regime_ok(sid, quarters, i, H):
                mo.append(None)
            else:
                d = [mc.momentum_change(col, k, H)
                     for k in range(i + 1)]
                mo.append(mc.percentile_rank_expanding(d, i)
                          if d[i] is not None else None)
        level, cov = mc.composite(lv, mo)
        momentum, _ = mc.composite(mo, mo)
        diff = mc.diffusion([cols[s] for s in md.COMPONENTS], i)
        readings.append({
            "quarter": t,
            "phase": mc.classify_phase(level, momentum),
            "level": level, "momentum": momentum,
            "diffusion": diff, "breadth": mc.breadth_qualifier(diff),
            "coverage": round(cov, 3),
            "components": {sid: lv[k]
                           for k, sid in enumerate(md.COMPONENTS)},
        })
    return quarters, readings


if __name__ == "__main__":
    quarters, readings = build_readings()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "ma_cycle_readings.json")
    with open(out, "w") as f:
        json.dump(readings, f, indent=1)

    live = [r for r in readings if r["phase"]]
    print(f"{len(readings)} quarters, {len(live)} with a phase reading")
    print(f"first scored: {live[0]['quarter']}   last: {live[-1]['quarter']}\n")
    print(f"{'quarter':<8} {'phase':<13} {'level':>7} {'mom':>7} "
          f"{'diff':>6} {'breadth':<8} cov")
    for r in live[-12:]:
        print(f"{r['quarter']:<8} {r['phase']:<13} {r['level']:>7.3f} "
              f"{r['momentum']:>7.3f} {r['diffusion']:>6.1f} "
              f"{r['breadth']:<8} {r['coverage']}")
    print("\nphase counts across scored history:")
    from collections import Counter
    for p, n in Counter(r["phase"] for r in live).most_common():
        print(f"  {p:<14} {n:>4}  ({100*n/len(live):.0f}%)")
