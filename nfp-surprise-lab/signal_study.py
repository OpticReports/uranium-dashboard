"""Do other pre-release indicators tilt the odds on the NFP surprise?

Casey's follow-up: consensus may be unbiased on average, but other signals
could still be tells. Each candidate is measured as ITS OWN surprise
(actual - estimate) from the last print strictly BEFORE the NFP release and
after the previous one -- so there is no lookahead by construction.

Pre-specified candidates only. Every p-value is reported raw AND Sidak-
corrected for the number of candidates tested, and every promising signal is
re-tested walk-forward before it is allowed to count.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import sys
from math import comb

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from nfp_surprise_study import COVID_END, COVID_START, load  # noqa: E402

RAW = HERE / "data" / "signals_raw.json"

# Pre-specified candidates: (label, event-name prefix, expected sign)
# expected sign +1 => a positive signal surprise should mean NFP beats consensus
CANDIDATES = [
    ("ADP employment change", "ADP Employment Change", +1),
    ("ISM manufacturing employment", "ISM Manufacturing Employment", +1),
    ("ISM non-mfg employment", "ISM Non-Manufacturing Employment", +1),
    ("Initial jobless claims", "Initial Jobless Claims", -1),
    ("Continuing jobless claims", "Continuing Jobless Claims", -1),
    ("Challenger job cuts", "Challenger Job Cuts", -1),
    ("ISM manufacturing PMI", "ISM Manufacturing PMI", +1),
    ("NFIB business optimism", "NFIB Business Optimism Index", +1),
]


def binom_p(k: int, n: int) -> float:
    probs = [comb(n, i) * 0.5**n for i in range(n + 1)]
    return min(1.0, sum(p for p in probs if p <= probs[k] * (1 + 1e-9)))


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0, 1.0
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
    if abs(r) >= 1:
        return r, 0.0
    t = r * math.sqrt((n - 2) / (1 - r * r))
    # two-sided normal approximation on t (n is 100+ here)
    p = math.erfc(abs(t) / math.sqrt(2))
    return r, p


def spearman(xs, ys):
    """Rank correlation -- a Pearson driven by two outliers will not survive it."""
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    return pearson(rank(xs), rank(ys))


def load_signals():
    raw = json.loads(RAW.read_text())
    out = []
    for x in raw:
        if x.get("estimate") is None or x.get("actual") is None:
            continue
        out.append(dict(
            when=dt.datetime.strptime(x["date"][:10], "%Y-%m-%d").date(),
            event=x["event"],
            surprise=float(x["actual"]) - float(x["estimate"])))
    return sorted(out, key=lambda r: r["when"])


def align(nfp, signals, prefix):
    """For each NFP release, the last matching signal print strictly before it
    and after the previous NFP release. Returns (signal_surprise, nfp_surprise)."""
    pool = [s for s in signals if s["event"].startswith(prefix)]
    pairs = []
    for i, r in enumerate(nfp):
        lo = nfp[i - 1]["rel"] if i else dt.date(1900, 1, 1)
        window = [s for s in pool if lo < s["when"] < r["rel"]]
        if not window or r["surprise"] == 0:
            continue
        pairs.append((window[-1]["surprise"], r["surprise"], r["rel"]))
    return pairs


def main():
    nfp = [r for r in load() if not (COVID_START <= r["rel"] <= COVID_END)]
    signals = load_signals()

    print(f"NFP releases (ex-COVID): {len(nfp)}   signal prints w/ estimates: {len(signals)}\n")
    print(f"{'candidate':<30}{'n':>5}{'pears':>8}{'p':>7}{'spear':>8}{'p':>7}"
          f"{'hit':>10}{'p_hit':>8}")
    print("-" * 84)

    results = []
    for label, prefix, sign in CANDIDATES:
        pairs = align(nfp, signals, prefix)
        if len(pairs) < 30:
            print(f"{label:<30}{len(pairs):>5}   (too few prints -- skipped)")
            continue
        xs = [sign * a for a, _, _ in pairs]
        ys = [b for _, b, _ in pairs]
        r, pr = pearson(xs, ys)
        rs, prs = spearman(xs, ys)
        hits = sum(1 for a, b, _ in pairs if a != 0 and (sign * a > 0) == (b > 0))
        tot = sum(1 for a, _, _ in pairs if a != 0)
        ph = binom_p(hits, tot)
        print(f"{label:<30}{len(pairs):>5}{r:>+8.3f}{pr:>7.3f}{rs:>+8.3f}{prs:>7.3f}"
              f"{hits:>6}/{tot:<3}{ph:>8.3f}")
        results.append(dict(label=label, prefix=prefix, sign=sign, n=len(pairs),
                            corr=round(r, 4), p_corr=round(pr, 4),
                            spearman=round(rs, 4), p_spearman=round(prs, 4),
                            hits=hits, tot=tot, p_hit=round(ph, 4)))

    if not results:
        print("\nno candidate had enough coverage")
        return results

    k = len(results)
    best = min(results, key=lambda d: min(d["p_corr"], d["p_hit"]))
    braw = min(best["p_corr"], best["p_hit"])
    print(f"\n{k} candidates tested. Best raw p = {braw:.4f} ({best['label']})")
    print(f"Sidak-corrected for {k} tests: p = {1-(1-braw)**k:.4f}")

    print("\n--- walk-forward (sign learned only from prior data) ---")
    for res in results:
        pairs = align(nfp, signals, res["prefix"])
        hits = tot = 0
        for i, (a, b, _) in enumerate(pairs):
            hist = pairs[:i]
            if len(hist) < 24 or a == 0:
                continue
            sg = res["sign"]
            agree = sum(1 for x, y, _ in hist if x != 0 and (sg * x > 0) == (y > 0))
            seen = sum(1 for x, _, _ in hist if x != 0)
            if seen == 0 or agree / seen == 0.5:
                continue
            follow = agree / seen > 0.5
            hits += ((sg * a > 0) == (b > 0)) == follow
            tot += 1
        if tot >= 30:
            print(f"  {res['label']:<30}{hits:>4}/{tot:<4} = {hits/tot*100:5.1f}%  "
                  f"p={binom_p(hits, tot):.3f}")
    return results


def misalignment(nfp, raw_path):
    """Casey's framing directly: when the survey sits far from the freshest hard
    read (ADP's actual), is the survey 'misaligned' in a tradeable direction?"""
    import datetime as _dt
    adp = {}
    for x in json.loads(pathlib.Path(raw_path).read_text()):
        if x["event"].startswith("ADP Employment Change") and x["actual"] is not None:
            adp[_dt.datetime.strptime(x["date"][:10], "%Y-%m-%d").date()] = float(x["actual"])
    pairs = []
    for i, r in enumerate(nfp):
        lo = nfp[i - 1]["rel"] if i else _dt.date(1900, 1, 1)
        window = [d for d in adp if lo < d < r["rel"]]
        if not window or r["surprise"] == 0:
            continue
        pairs.append((r["consensus"] - adp[max(window)], r["surprise"]))
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    rp, pp = pearson(xs, ys)
    rs, ps = spearman(xs, ys)
    hits = sum(1 for a, b in pairs if a != 0 and (a < 0) == (b > 0))
    tot = sum(1 for a, _ in pairs if a != 0)
    print("\n--- misalignment: consensus vs the freshest hard read (ADP actual) ---")
    print(f"  n={len(pairs)}  Pearson {rp:+.3f} (p={pp:.3f})  "
          f"Spearman {rs:+.3f} (p={ps:.3f})")
    print(f"  rule 'consensus below ADP -> bet NFP above': {hits}/{tot} = "
          f"{hits/tot*100:.1f}%  p={binom_p(hits, tot):.3f}")
    srt = sorted(pairs, key=lambda t: t[0])
    k = len(srt) // 3
    terciles = []
    for lab, seg in (("survey well BELOW ADP", srt[:k]), ("middle", srt[k:2*k]),
                     ("survey well ABOVE ADP", srt[2*k:])):
        up = sum(1 for _, b in seg if b > 0)
        terciles.append(dict(label=lab, n=len(seg), beat=up, rate=up / len(seg)))
        print(f"    {lab:<24} n={len(seg):3d}  NFP beat {up}/{len(seg)} = "
              f"{up/len(seg)*100:.0f}%")
    return dict(n=len(pairs), pearson=round(rp, 4), p_pearson=round(pp, 4),
                spearman=round(rs, 4), p_spearman=round(ps, 4),
                hits=hits, tot=tot, p_hit=round(binom_p(hits, tot), 4),
                terciles=terciles)


if __name__ == "__main__":
    out = main()
    _nfp = [r for r in load() if not (COVID_START <= r["rel"] <= COVID_END)]
    mis = misalignment(_nfp, HERE / "data" / "signals_raw.json")
    out = dict(candidates=out, misalignment=mis)
    (HERE / "data" / "signal_results.json").write_text(json.dumps(out, indent=1))
