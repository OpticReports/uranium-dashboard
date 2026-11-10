"""MECHANICAL ONLY: coverage, gaps, exact-zero daily changes, and what the SPEC's peg filter (>=50% exact zeros in
the trailing 60 changes) removes. No returns, no gates, no firings, no forward quantities are computed."""
import csv, datetime as dt, os, sys
REPO, DL = sys.argv[1], sys.argv[2]
IDS = ["DEXBZUS", "DEXMXUS", "DEXKOUS", "DEXSFUS", "DEXINUS", "DEXTHUS", "DEXMAUS", "DEXTAUS", "DEXSIUS", "DEXSLUS",
       "DEXCAUS", "DEXUSAL", "DEXUSNZ", "DEXNOUS", "DEXSDUS", "DEXCHUS"]
def load(s):
    p = os.path.join(REPO, s + ".csv")
    if not os.path.exists(p): p = os.path.join(DL, s + ".csv")
    rows = list(csv.DictReader(open(p))); out = []; miss = 0
    for r in rows:
        v = r[s]
        if v in ("", "."): miss += 1; continue
        out.append((r["observation_date"], float(v)))
    return out, miss
D = lambda s: dt.date.fromisoformat(s)
for s in IDS:
    obs, miss = load(s)
    obs = [o for o in obs if o[0] >= "1973-03-01"]
    gaps = [((D(b[0]) - D(a[0])).days, a[0], b[0]) for a, b in zip(obs, obs[1:])]
    big = sorted([g for g in gaps if g[0] > 10], reverse=True)
    zero = [obs[i][1] == obs[i - 1][1] for i in range(1, len(obs))]
    excl = []
    for i in range(len(zero)):
        w = zero[max(0, i - 59):i + 1]
        excl.append(len(w) == 60 and sum(w) >= 30)
    yrs = {}
    for i in range(len(zero)):
        y = obs[i + 1][0][:4]; a = yrs.setdefault(y, [0, 0, 0]); a[0] += 1; a[1] += zero[i]; a[2] += excl[i]
    def spans(pred):
        out, cur = [], None
        for y in sorted(yrs):
            if pred(yrs[y]):
                cur = [y, y] if cur is None else [cur[0], y]
            else:
                if cur: out.append(cur); cur = None
        if cur: out.append(cur)
        return ",".join(a if a == b else f"{a}-{b}" for a, b in out) or "-"
    tot = sum(v[0] for v in yrs.values()); ex = sum(v[2] for v in yrs.values())
    print(f"{s}: {obs[0][0]}..{obs[-1][0]} valid={len(obs)} missing_rows={miss} | gaps>10d: {len(big)}"
          f"{' max ' + str(big[0][0]) + 'd ' + big[0][1] + '->' + big[0][2] if big else ''}"
          f" | peg-filter removes {ex}/{tot} days ({100*ex/tot:.1f}%)")
    print(f"    years zero-share>=50%: {spans(lambda a: a[1] >= 0.5 * a[0])} | 20-50%: {spans(lambda a: 0.2 * a[0] <= a[1] < 0.5 * a[0])}"
          f" | 5-20%: {spans(lambda a: 0.05 * a[0] <= a[1] < 0.2 * a[0])} | filter removes >50% of yr: {spans(lambda a: a[2] > 0.5 * a[0])}")
    if big[:4]: print("    largest gaps:", [(g[0], g[1], g[2]) for g in big[:4]])
