"""Per-position win-score table — implementation of WIN_SCORE_SPEC.md
(frozen b5d681b before this file produced a number).

Computes, from the frozen phase-barbell fixture, for each (phase, asset,
horizon): month-counted and episode-counted hit rates of beating cash,
Wilson 95% interval on episodes, and the unconditional base rate. The
serving layer (src/barbell/phase.py) carries the resulting constants; a
gate recomputes this table and asserts parity.
"""
from __future__ import annotations

import math

import phase_barbell as pb

HORIZONS = (6, 12)
ASSETS = ("stocks", "bonds", "gold")
GOLD_FROM = pb.GOLD_FROM


def _cum(rets, i, h):
    acc = 1.0
    for k in range(i + 1, i + 1 + h):
        if k >= len(rets) or rets[k] is None:
            return None
        acc *= 1 + rets[k]
    return acc


def wilson(w: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - hw) * 100, 1), round(min(1.0, c + hw) * 100, 1))


def compute() -> dict:
    F = pb.build_frames(pb.load())
    labs = pb.labels(F)
    months = F["months"]
    R = {"stocks": pb.stock_returns(F), "bonds": pb.bond_returns(F),
         "gold": pb.gold_returns(F), "cash": pb.cash_returns(F)}
    out: dict = {}
    for h in HORIZONS:
        # WIN at month i: asset cumulative (i, i+h] beats cash cumulative.
        # Only months whose window CLOSES inside the fixture count.
        def win(asset, i):
            a = _cum(R[asset], i, h)
            c = _cum(R["cash"], i, h)
            if a is None or c is None:
                return None
            return a > c

        for asset in ASSETS:
            # eligible months: labeled, asset live (gold post-1971)
            idx = [i for i in range(len(months))
                   if labs[i] is not None
                   and (asset != "gold" or months[i] >= GOLD_FROM)
                   and win(asset, i) is not None]
            base_w = sum(1 for i in idx if win(asset, i))
            base = {"months": len(idx),
                    "rate_pct": round(100 * base_w / len(idx), 1)
                    if idx else None}
            for phase in pb.MAPPING:
                mi = [i for i in idx if labs[i][1] == phase]
                m_w = sum(1 for i in mi if win(asset, i))
                # episodes: maximal runs of same-label months <=12m apart;
                # outcome = the FIRST month's outcome (spec convention)
                eps: list[list[int]] = []
                for i in mi:
                    if eps and i - eps[-1][-1] <= 12:
                        eps[-1].append(i)
                    else:
                        eps.append([i])
                e_w = sum(1 for ep in eps if win(asset, ep[0]))
                lo, hi = wilson(e_w, len(eps))
                out[f"{phase}|{asset}|{h}"] = {
                    "months": len(mi), "month_wins": m_w,
                    "month_pct": round(100 * m_w / len(mi), 1) if mi else None,
                    "episodes": len(eps), "episode_wins": e_w,
                    "episode_pct": round(100 * e_w / len(eps), 1)
                    if eps else None,
                    "wilson_lo": lo, "wilson_hi": hi,
                    "base_pct": base["rate_pct"],
                    "base_months": base["months"],
                }
    return out


if __name__ == "__main__":
    import json
    import sys
    t = compute()
    json.dump(t, open("fixtures/win_scores.json", "w"), indent=1)
    for h in HORIZONS:
        print(f"--- {h}m (episode-counted, [Wilson 95]) ---")
        for phase in pb.MAPPING:
            row = []
            for a in ASSETS:
                c = t[f"{phase}|{a}|{h}"]
                row.append(f"{a} {c['episode_wins']}/{c['episodes']}"
                           f"={c['episode_pct']}% [{c['wilson_lo']}-"
                           f"{c['wilson_hi']}] (mo {c['month_pct']}%, "
                           f"base {c['base_pct']}%)")
            print(f"{phase:>12}: " + " | ".join(row))
    sys.exit(0)
