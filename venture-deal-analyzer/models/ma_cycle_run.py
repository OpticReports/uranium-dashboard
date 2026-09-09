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

    Two components carry a scoring floor and both would be corrupted by
    a lookback that reaches across it:

      HSR_COUNT     - a lookback from just after the 2001 threshold
                      change reads a legislative redefinition as a
                      collapse in deal activity
      EDGAR_PROXIES - a lookback from 1997 into the pre-mandate years
                      reads EDGAR ADOPTION as a surge in deal-making

    Momentum is only defined once BOTH endpoints sit above the floor.
    Generalized rather than special-cased on HSR so that adding a third
    floored component cannot silently skip this check.
    """
    j = i - h
    if j < 0:
        return False
    return md.scoreable(sid, quarters[j]) and md.scoreable(sid, quarters[i])


def _lfl_delta(prev, lv, components):
    """Level change vs the previous quarter on the COMMON component set.

    Why this is not optional. The composite averages over the
    components AVAILABLE in a quarter, so it moves when the panel
    changes even if nothing in the market did. Measured on real data at
    the 2026Q1->2026Q2 seam, where the Z.1 flow-of-funds series and HSR
    have not yet published:

        naive Q1 -> Q2          +0.017   (reads as strengthening)
        like-for-like Q1 -> Q2  -0.086   (actually weakening)

    The SIGN of the quarter-on-quarter move flips. Anyone comparing two
    published levels across a coverage change is reading composition,
    not the cycle. This field is the honest delta; the raw level
    difference is not.

    Parameter-free: it simply restricts both quarters to the components
    they both have.
    """
    if prev is None:
        return None
    cur = {c: v for c, v in zip(components, lv) if v is not None}
    old = prev.get("components") or {}
    common = [c for c in cur if old.get(c) is not None]
    if not common:
        return None
    a = sum(cur[c] for c in common) / len(common)
    b = sum(old[c] for c in common) / len(common)
    return a - b


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

    # Regime boundary = the 2001 definitional break, NOT simply "the
    # last unscoreable quarter" - that would also catch the pre-1994
    # window floor and put the regime start in the wrong place.
    hsr_regime_starts = [i for i, t in enumerate(quarters)
                         if t == "2001Q2"]

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
        prev = readings[-1] if readings else None
        readings.append({
            "quarter": t,
            "provisional": cov < 1.0,
            "delta_like_for_like": _lfl_delta(prev, lv, md.COMPONENTS),
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
