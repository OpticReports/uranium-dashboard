"""Statistical gates for tuning proposals (see TUNING.md).

Two gates, both deliberately conservative — in a small-n, correlated,
one-history domain, the burden of proof is on the CHANGE, not the status quo:

  ic         Weights gate. Recomputes every stored ScoreSnapshot's composite
             under proposed weights (component values are stored per
             snapshot, so no re-ingestion is needed), measures the daily
             cross-sectional rank correlation (Spearman IC) between composite
             and 1-month-forward XBI-excess return, and bootstrap-compares
             proposed vs baseline. PASS only if the improvement's 90% band
             excludes zero.

  promotion  Trigger gate. Reads the uncensored flag track record and applies
             a Wilson lower bound: a signal earns call-trigger status only if
             n >= 20 graded 1m outcomes AND the 90% lower confidence bound of
             its hit rate is above 0.50 AND its average excess return is
             positive. --demote inverts the test.

Exit codes: 0 = PASS, 1 = FAIL, 2 = insufficient data. The tuner may only
open a PR on exit 0.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BOOT_ITERS = 2000
MIN_NAMES_PER_DAY = 6
FWD_BARS = 21
BENCH = "XBI"


# --- shared math ---------------------------------------------------------------

def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties. Pure python."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def wilson_bounds(hits: int, n: int, z: float = 1.645) -> tuple[float, float]:
    """Wilson score interval (default z=1.645 -> 90% two-sided)."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


def recompute_composite(components: dict, weights: dict) -> float | None:
    """Composite under arbitrary weights from a snapshot's stored components.
    Mirrors the live engine: missing components drop out of the denominator."""
    num = den = 0.0
    for name, val in (components or {}).items():
        if val is None:
            continue
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        num += w * val
        den += w
    return (num / den) if den > 0 else None


# --- ic gate ---------------------------------------------------------------------

def run_ic(proposed_path: str, baseline_path: str) -> int:
    import yaml
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import PriceBar, ScoreSnapshot

    with open(baseline_path) as fh:
        base_w = (yaml.safe_load(fh) or {}).get("weights", {})
    with open(proposed_path) as fh:
        prop_w = (yaml.safe_load(fh) or {}).get("weights", {})
    if not base_w or not prop_w:
        print("insufficient: could not read weights from configs")
        return 2

    with Session(engine) as session:
        closes: dict[str, list[tuple[date, float]]] = {}
        for b in session.exec(
            select(PriceBar).where(PriceBar.close != None)  # noqa: E711
            .order_by(PriceBar.date.asc())
        ).all():
            closes.setdefault(b.symbol, []).append((b.date, b.close))

        def fwd_excess(symbol: str, d: date) -> float | None:
            def fwd(sym: str) -> float | None:
                series = closes.get(sym, [])
                idx = next((i for i, (bd, _) in enumerate(series) if bd >= d), None)
                if idx is None:
                    idx = len(series) - 1
                elif series[idx][0] > d:
                    idx -= 1
                if idx < 0 or idx + FWD_BARS >= len(series) or not series[idx][1]:
                    return None
                return (series[idx + FWD_BARS][1] - series[idx][1]) / series[idx][1]

            f, b = fwd(symbol), fwd(BENCH)
            return None if (f is None or b is None) else f - b

        # Last snapshot per (symbol, day).
        by_day: dict[date, dict[str, dict]] = {}
        for s in session.exec(select(ScoreSnapshot).order_by(ScoreSnapshot.asof.asc())).all():
            by_day.setdefault(s.asof.date(), {})[s.symbol] = s.components

    base_ics, prop_ics, used_days = [], [], []
    for d, comps_by_sym in sorted(by_day.items()):
        rows = []
        for sym, comps in comps_by_sym.items():
            fb = recompute_composite(comps, base_w)
            fp = recompute_composite(comps, prop_w)
            fe = fwd_excess(sym, d)
            if fb is not None and fp is not None and fe is not None:
                rows.append((fb, fp, fe))
        if len(rows) < MIN_NAMES_PER_DAY:
            continue
        ic_b = spearman([r[0] for r in rows], [r[2] for r in rows])
        ic_p = spearman([r[1] for r in rows], [r[2] for r in rows])
        if ic_b is None or ic_p is None:
            continue
        base_ics.append(ic_b)
        prop_ics.append(ic_p)
        used_days.append(d.isoformat())

    n_days = len(used_days)
    if n_days < 10:
        print(f"insufficient: only {n_days} evaluable days (need >= 10) — "
              "score history and 1m-forward bars must accrue first")
        return 2

    diffs = [p - b for p, b in zip(prop_ics, base_ics)]
    mean_b = sum(base_ics) / n_days
    mean_p = sum(prop_ics) / n_days
    rng = random.Random(42)
    boot = []
    for _ in range(BOOT_ITERS):
        sample = [diffs[rng.randrange(n_days)] for _ in range(n_days)]
        boot.append(sum(sample) / n_days)
    boot.sort()
    lo, hi = boot[int(0.05 * BOOT_ITERS)], boot[int(0.95 * BOOT_ITERS)]

    result = {
        "days": n_days, "mean_ic_baseline": round(mean_b, 4),
        "mean_ic_proposed": round(mean_p, 4),
        "mean_ic_diff": round(mean_p - mean_b, 4),
        "diff_ci90": [round(lo, 4), round(hi, 4)],
    }
    print(json.dumps(result, indent=2))
    if mean_p > mean_b and lo > 0:
        print("PASS: proposed weights improve rank-IC and the 90% band excludes zero")
        return 0
    print("FAIL: improvement not demonstrated (mean must rise AND ci90 low > 0)")
    return 1


# --- promotion gate ---------------------------------------------------------------

def run_promotion(flag_type: str, source: str | None, demote: bool) -> int:
    if source:
        record = json.loads(Path(source).read_text())
        if "flag_track_record" in record:  # /tuning/evidence blob
            record = record["flag_track_record"]
    else:
        from sqlmodel import Session

        from app.db import engine
        from app.scoring.outcomes import flag_track_record

        with Session(engine) as session:
            record = flag_track_record(session)

    stats = record.get("by_flag_type", {}).get(flag_type)
    if not stats:
        print(f"insufficient: no graded outcomes for '{flag_type}'")
        return 2
    h1m = stats.get("horizons", {}).get("1m", {})
    n = h1m.get("n") or 0
    hit = h1m.get("hit_rate")
    avg_excess = h1m.get("avg_excess")
    if n < 20 or hit is None:
        print(f"insufficient: n={n} graded 1m outcomes (need >= 20)")
        return 2

    hits = round(hit * n)
    lo, hi = wilson_bounds(hits, n)
    result = {
        "flag_type": flag_type, "n_1m": n, "hit_rate": round(hit, 3),
        "wilson90": [round(lo, 3), round(hi, 3)],
        "avg_excess_1m": None if avg_excess is None else round(avg_excess, 4),
        "basis": h1m.get("basis"),
    }
    print(json.dumps(result, indent=2))

    if demote:
        if hi < 0.50 or (avg_excess is not None and avg_excess < 0 and n >= 30):
            print("PASS (demotion): the signal is demonstrably not paying")
            return 0
        print("FAIL (demotion): evidence does not condemn the signal yet")
        return 1

    if lo > 0.50 and avg_excess is not None and avg_excess > 0:
        print("PASS (promotion): hit-rate lower bound > 50% with positive excess")
        return 0
    print("FAIL (promotion): the record does not yet earn call-trigger status")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ic = sub.add_parser("ic", help="weights gate: rank-IC replay under proposed weights")
    ic.add_argument("--proposed", required=True, help="path to proposed scoring.yaml")
    ic.add_argument("--baseline", default=str(Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"))

    pr = sub.add_parser("promotion", help="trigger gate: Wilson-bound track-record test")
    pr.add_argument("--flag-type", required=True)
    pr.add_argument("--source", help="track-record or /tuning/evidence JSON file (default: local DB)")
    pr.add_argument("--demote", action="store_true")

    args = ap.parse_args()
    if args.cmd == "ic":
        sys.exit(run_ic(args.proposed, args.baseline))
    sys.exit(run_promotion(args.flag_type, args.source, args.demote))


if __name__ == "__main__":
    main()
