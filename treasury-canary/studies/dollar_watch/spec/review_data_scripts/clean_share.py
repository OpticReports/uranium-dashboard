"""CALENDAR ARITHMETIC ONLY: share of D-1-eligible currency-days (3y sigma warm-up from 1973-03, SPEC peg filter, last 250
obs dropped) whose candidate-firing span [k-60, k+250] (own index days) avoids already-seen spans.
Def SPEC = firing day outside the SPEC's five windows, not CAD/SEK. Def R1 = span avoids every seen span listed below.
Def R2 = R1 plus 2006-01-02.. treated as in-sample for the 11 DTWEXBGS components."""
import csv, datetime as dt, os, sys
REPO, DL = sys.argv[1:3]
def addm(d, m):
    y, mo = d.year, d.month + m; y += (mo - 1) // 12; mo = (mo - 1) % 12 + 1
    return dt.date(y, mo, min(d.day, 28))
D = dt.date.fromisoformat
SPEC5 = [("2007-06-01", "2009-06-30"), ("2015-06-01", "2016-03-31"), ("2018-03-01", "2019-01-31"), ("2020-02-01", "2020-06-30"), ("2022-01-01", "2022-12-31")]
CHART = [("2007-06-01", "2009-06-30"), ("2014-07-01", "2016-06-30"), ("2018-01-01", "2019-03-31"), ("2020-01-01", "2020-09-30"), ("2022-01-01", "2023-03-31")]
ANALYZE_EXTRA = [("2023-02-01", "2023-05-31"), ("2025-01-01", "2026-11-02")]
ANCHORS = ["1997-03-28", "2000-08-28", "2005-12-28", "2008-09-22", "2008-11-06", "2008-11-28", "2010-06-03", "2011-11-01",
           "2012-06-07", "2012-06-28", "2014-12-28", "2020-04-09", "2022-05-28", "2022-07-28"]
BASKET = {"DEXBZUS", "DEXMXUS", "DEXSFUS", "DEXINUS", "DEXKOUS", "DEXTHUS", "DEXMAUS"}
BROAD = {"DEXBZUS", "DEXMXUS", "DEXKOUS", "DEXINUS", "DEXTHUS", "DEXMAUS", "DEXTAUS", "DEXSIUS", "DEXCAUS", "DEXUSAL", "DEXSDUS"}
ALLSEEN = {"DEXCAUS", "DEXSDUS", "DEXUSAL"}          # DXY / TWEXMMTH components (monthly paths scored); AFE 2006+
seen_basket = [(D(a), D(b)) for a, b in CHART + ANALYZE_EXTRA] + [(D(a), addm(D(a), 12)) for a in ANCHORS]
IDS = ["DEXBZUS", "DEXMXUS", "DEXKOUS", "DEXSFUS", "DEXINUS", "DEXTHUS", "DEXMAUS", "DEXTAUS", "DEXSIUS", "DEXSLUS",
       "DEXCAUS", "DEXUSAL", "DEXUSNZ", "DEXNOUS", "DEXSDUS"]
tot = {"elig": 0, "spec": 0, "r1": 0, "r2": 0}
print(f"{'pair':8s} {'elig cy':>8s} {'SPEC-clean':>10s} {'R1-clean':>9s} {'R2-clean':>9s}  R2-clean year spans")
for sid in IDS:
    p = os.path.join(REPO, sid + ".csv")
    if not os.path.exists(p): p = os.path.join(DL, sid + ".csv")
    obs = [(r["observation_date"], r[sid]) for r in csv.DictReader(open(p)) if r[sid] not in ("", ".") and r["observation_date"] >= "1973-03-01"]
    dates = [D(o[0]) for o in obs]; vals = [o[1] for o in obs]
    zero = [vals[i] == vals[i - 1] for i in range(1, len(vals))]
    spans = []
    if sid in BASKET: spans += seen_basket
    if sid in ALLSEEN: spans.append((D("1971-01-01"), D("2026-12-31")))
    spans_r2 = spans + ([(D("2006-01-02"), D("2026-12-31"))] if sid in BROAD else [])
    e = s5 = r1 = r2 = 0; yrs = set()
    for k in range(817, len(dates) - 250):
        if sum(zero[k - 60:k]) >= 30: continue
        e += 1
        lo, hi = dates[k - 60], dates[k + 250]
        if sid not in ("DEXCAUS", "DEXSDUS") and not any(D(a) <= dates[k] <= D(b) for a, b in SPEC5): s5 += 1
        ok1 = not any(lo <= b and a <= hi for a, b in spans)
        ok2 = not any(lo <= b and a <= hi for a, b in spans_r2)
        r1 += ok1; r2 += ok2
        if ok2: yrs.add(dates[k].year)
    ys = sorted(yrs); runs = []
    for y in ys:
        if runs and y == runs[-1][1] + 1: runs[-1][1] = y
        else: runs.append([y, y])
    for k_, v in (("elig", e), ("spec", s5), ("r1", r1), ("r2", r2)): tot[k_] += v
    print(f"{sid:8s} {e/252:8.1f} {s5/252:10.1f} {r1/252:9.1f} {r2/252:9.1f}  {','.join(str(a) if a == b else f'{a}-{b}' for a, b in runs) or '-'}")
print(f"{'TOTAL':8s} {tot['elig']/252:8.1f} {tot['spec']/252:10.1f} {tot['r1']/252:9.1f} {tot['r2']/252:9.1f}")
print(f"post-2006 share of SPEC-clean days that R1 removes: computed above per pair; R2 leaves no 2006+ days for the 11 broad-index components")
