"""Does the 'bet the market is wrong on non-farm payrolls' trade exist?

Reproducible from the frozen dataset in data/nfp_surprises.json (FMP economic
calendar; consensus = Bloomberg-style survey median as captured at release,
actual = FIRST PRINT, which is what any pre-release bet resolves against).

Every rule below is a directional bet placed BEFORE the 08:30 ET release:
"will the print come in above or below consensus?"  Hit rate 50% = no edge.

Run:  python3 nfp_surprise_study.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import pathlib
from math import comb

DATA = pathlib.Path(__file__).parent / "data" / "nfp_surprises.json"

# The 2020-21 labour-market dislocation makes surprise magnitudes meaningless
# (single prints missed by millions). Excluded from magnitude stats, and the
# sensitivity of that choice is reported explicitly.
COVID_START, COVID_END = dt.date(2020, 3, 1), dt.date(2021, 12, 31)


def load():
    rows = json.loads(DATA.read_text())
    for r in rows:
        r["rel"] = dt.date.fromisoformat(r["release"])
        r["ref"] = dt.datetime.strptime(r["ref_month"], "%Y-%m").date()
    return sorted(rows, key=lambda r: r["rel"])


def binom_p(k: int, n: int, p: float = 0.5) -> float:
    """Exact two-sided binomial p-value."""
    probs = [comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(pr for pr in probs if pr <= probs[k] * (1 + 1e-9)))


def hit_rate(hits: int, tot: int) -> tuple[float, float]:
    return hits / tot, binom_p(hits, tot)


def moments(vals):
    n = len(vals)
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1))
    return n, mean, sd, mean / (sd / math.sqrt(n))


def directional(rows):
    """Hit rate of the rule 'always bet ABOVE consensus'."""
    up = sum(1 for r in rows if r["surprise"] > 0)
    dn = sum(1 for r in rows if r["surprise"] < 0)
    return up, up + dn


def week_of_12th(d: dt.date) -> dt.date:
    """Saturday ending the Sun-Sat week containing the 12th — the CES pay-period
    reference week. The gap between consecutive reference weeks is 4 or 5."""
    t = dt.date(d.year, d.month, 12)
    return t + dt.timedelta(days=(5 - t.weekday()) % 7)


def ref_gap_weeks(ref: dt.date) -> int:
    prev = (ref.replace(day=1) - dt.timedelta(days=1))
    return round((week_of_12th(ref) - week_of_12th(prev)).days / 7)


def walk_forward_month_rule(rows, min_history=5):
    """Pick each month's historical direction using ONLY prior data, then bet it."""
    hits = tot = 0
    for i, r in enumerate(rows):
        prior = [x["surprise"] for x in rows[:i] if x["ref"].month == r["ref"].month]
        if len(prior) < min_history or r["surprise"] == 0:
            continue
        share_up = sum(1 for x in prior if x > 0) / len(prior)
        if share_up == 0.5:
            continue
        hits += (r["surprise"] > 0) == (share_up > 0.5)
        tot += 1
    return hits, tot


def anchoring_rule(rows, lookback=3):
    """Consensus below the recent actual trend -> bet the print comes in above."""
    hits = tot = 0
    for i in range(lookback, len(rows)):
        r = rows[i]
        trend = sum(rows[j]["actual"] for j in range(i - lookback, i)) / lookback
        if r["consensus"] == trend or r["surprise"] == 0:
            continue
        hits += (r["surprise"] > 0) == (r["consensus"] < trend)
        tot += 1
    return hits, tot


def report():
    rows = load()
    core = [r for r in rows if not (COVID_START <= r["rel"] <= COVID_END)]
    out = {}

    print(f"sample: n={len(rows)}  {rows[0]['release']} -> {rows[-1]['release']}")
    print(f"core (ex {COVID_START}..{COVID_END}): n={len(core)}\n")

    print("=== 1. IS CONSENSUS DIRECTIONALLY BIASED? ===")
    eras = [
        ("2013-2019 pre-COVID", dt.date(2013, 1, 1), dt.date(2020, 1, 1)),
        ("2022-2024 reopening", dt.date(2022, 1, 1), dt.date(2025, 1, 1)),
        ("2025-2026 recent", dt.date(2025, 1, 1), dt.date(2027, 1, 1)),
        ("core (all, ex-COVID)", dt.date(2013, 1, 1), dt.date(2027, 1, 1)),
    ]
    out["eras"] = []
    for lab, lo, hi in eras:
        sub = [r for r in core if lo <= r["rel"] < hi]
        n, mean, sd, t = moments([r["surprise"] for r in sub])
        up, tot = directional(sub)
        rate, p = hit_rate(up, tot)
        print(f"{lab:<22} n={n:3d}  mean {mean:+7.1f}k  t={t:+5.2f}  "
              f"bet-above {up}/{tot} = {rate*100:4.1f}%  p={p:.3f}")
        out["eras"].append(dict(label=lab, n=n, mean=round(mean, 1), t=round(t, 2),
                                hits=up, tot=tot, rate=round(rate, 4), p=round(p, 4)))

    print("\n=== 2. DOES LAST MONTH'S SURPRISE PREDICT THIS MONTH'S? ===")
    pairs = [(core[i - 1]["surprise"], core[i]["surprise"]) for i in range(1, len(core))]
    mx = sum(a for a, _ in pairs) / len(pairs)
    my = sum(b for _, b in pairs) / len(pairs)
    cov = sum((a - mx) * (b - my) for a, b in pairs) / len(pairs)
    sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs) / len(pairs))
    sy = math.sqrt(sum((b - my) ** 2 for _, b in pairs) / len(pairs))
    rho = cov / (sx * sy)
    print(f"lag-1 autocorrelation of surprise = {rho:+.3f}  (n={len(pairs)})")
    out["lag1_autocorr"] = round(rho, 4)

    print("\n=== 3. RESIDUAL SEASONALITY (the Clarium mechanism), 12 tests ===")
    by_month = collections.defaultdict(list)
    for r in core:
        by_month[r["ref"].month].append(r["surprise"])
    months = []
    for m in range(1, 13):
        v = by_month[m]
        up = sum(1 for x in v if x > 0)
        p = binom_p(up, len(v))
        months.append(dict(month=m, name=dt.date(2000, m, 1).strftime("%b"),
                           n=len(v), mean=round(sum(v) / len(v), 1), hits=up, p=round(p, 4)))
        print(f"  {months[-1]['name']}  n={len(v):3d}  mean {months[-1]['mean']:+7.1f}k  "
              f"above {up}/{len(v)}  p={p:.3f}")
    best = min(m["p"] for m in months)
    sidak = 1 - (1 - best) ** 12
    print(f"  best p={best:.3f} -> Sidak-corrected for 12 tests: {sidak:.3f}")
    out["months"] = months
    out["month_best_p"] = round(best, 4)
    out["month_sidak_p"] = round(sidak, 4)

    print("\n=== 4. CES 4-WEEK vs 5-WEEK REFERENCE GAP ===")
    gaps = collections.defaultdict(list)
    for r in core:
        gaps[ref_gap_weeks(r["ref"])].append(r["surprise"])
    for k in sorted(gaps):
        v = gaps[k]
        print(f"  gap={k}w  n={len(v):3d}  mean {sum(v)/len(v):+7.1f}k  "
              f"above {sum(1 for x in v if x>0)}/{len(v)}")
    if len(gaps) == 2:
        a, b = [gaps[k] for k in sorted(gaps)]
        na, ma, sa, _ = moments(a)
        nb, mb, sb, _ = moments(b)
        t = (mb - ma) / math.sqrt(sa**2 / na + sb**2 / nb)
        print(f"  diff(5w-4w) = {mb-ma:+.1f}k   Welch t={t:+.2f}")
        out["gap_diff_t"] = round(t, 2)

    print("\n=== 5. OUT-OF-SAMPLE RULES (no lookahead) ===")
    out["oos"] = []
    for lab, fn in [("month-of-year, walk-forward", walk_forward_month_rule),
                    ("consensus vs 3mo trend (anchoring)", anchoring_rule)]:
        hits, tot = fn(core)
        rate, p = hit_rate(hits, tot)
        print(f"  {lab:<38} {hits:3d}/{tot:3d} = {rate*100:4.1f}%  p={p:.3f}")
        out["oos"].append(dict(rule=lab, hits=hits, tot=tot,
                               rate=round(rate, 4), p=round(p, 4)))

    n, mean, sd, _ = moments([r["surprise"] for r in core])
    absol = sorted(abs(r["surprise"]) for r in core)
    out["mean_abs_surprise"] = round(sum(absol) / n, 1)
    out["median_abs_surprise"] = absol[n // 2]
    print(f"\nmean |surprise| (core) = {out['mean_abs_surprise']}k  "
          f"median = {out['median_abs_surprise']}k")
    return out


if __name__ == "__main__":
    result = report()
    (pathlib.Path(__file__).parent / "data" / "results.json").write_text(
        json.dumps(result, indent=1))
    print("\nwrote data/results.json")
