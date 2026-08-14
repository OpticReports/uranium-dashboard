"""B1-T — does a Treasury-feature HMM label BOND-market stress regimes well?
Features: daily change in 10y yield (bp) + 10d realized vol of changes.
3-state Gaussian HMM, walk-forward monthly refit on trailing 1890 trading
days, decode last-obs posterior. States sorted by vol: CALM/ELEVATED/STRESS.
Purely descriptive scoring: does STRESS cover known Treasury stress episodes,
and how often does it fire in known-calm years?"""
import json, datetime, warnings
import numpy as np
from hmmlearn.hmm import GaussianHMM
warnings.filterwarnings("ignore")
SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"

r = json.load(open(f"{SC}/tnx-daily.json"))["chart"]["result"][0]
rows = [(datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date(), c)
        for ts, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None]
dates = [d for d, _ in rows]
y = np.array([c for _, c in rows]) * 10.0          # ^TNX is yield*10? No: ^TNX 4.35 = 4.35%; *100 bp
chg = np.diff(np.array([c for _, c in rows])) * 100.0   # bp/day
dates = dates[1:]
vol = np.array([chg[max(0, i - 9):i + 1].std() for i in range(len(chg))])
X = np.column_stack([chg, vol])

W = 1890
mes = [i for i in range(W, len(dates) - 1) if dates[i].month != dates[i + 1].month]
mes.append(len(dates) - 1)
res = []
for i in mes:
    Xi = X[i - W + 1:i + 1]
    best = None
    for seed in (1, 7):
        try:
            m = GaussianHMM(n_components=3, covariance_type="full", n_iter=75, random_state=seed)
            m.fit(Xi); s = m.score(Xi)
            if best is None or s > best[0]:
                best = (s, m)
        except Exception:
            continue
    if best is None:
        continue
    m = best[1]
    post = m.predict_proba(Xi)[-1]
    st = int(np.argmax(post))
    vorder = np.argsort(m.means_[:, 1])           # sort by mean vol
    lab = {vorder[0]: "CALM", vorder[1]: "ELEV", vorder[2]: "STRESS"}[st]
    direction = "selloff" if m.means_[st, 0] > 0 else "rally"
    res.append((f"{dates[i].year:04d}-{dates[i].month:02d}", lab,
                direction if lab == "STRESS" else "", round(float(post.max()), 2)))

json.dump([{"month": a, "state": b, "dir": c, "conf": d} for a, b, c, d in res],
          open(f"{SC}/b1t_states.json", "w"), indent=1)
out = {a: (b, c) for a, b, c, _ in res}
n = len(res)
print(f"month-ends: {n} ({res[0][0]} .. {res[-1][0]})")
for s in ("CALM", "ELEV", "STRESS"):
    print(f"  {s}: {sum(1 for _, l, _, _ in res if l == s)/n:.0%}", end="")
print()

EP = {
    "1994 hike massacre":  ["1994-02", "1994-04", "1994-06", "1994-11"],
    "1998 LTCM":           ["1998-09", "1998-10"],
    "2003 convexity":      ["2003-07", "2003-08"],
    "2008 GFC":            ["2008-09", "2008-11", "2008-12"],
    "2013 taper":          ["2013-06", "2013-08"],
    "2020 COVID/basis":    ["2020-03", "2020-04"],
    "2022 bond bear":      ["2022-03", "2022-06", "2022-09", "2022-10"],
    "2023 termprem Q3":    ["2023-09", "2023-10"],
    "2025 April vol":      ["2025-04", "2025-05"],
}
print("\nknown TREASURY stress episodes — month-end state:")
for name, months in EP.items():
    reads = []
    for mth in months:
        s, d = out.get(mth, ("—", ""))
        reads.append(f"{mth}:{s}{('/' + d) if d else ''}")
    print(f"  {name:20} {'  '.join(reads)}")

calm_years = ("1993", "1996", "1997", "2005", "2006", "2014", "2017", "2019", "2021")
fa = [a for a, l, _, _ in res if l == "STRESS" and a[:4] in calm_years]
print(f"\nSTRESS month-ends inside calm bond years: {len(fa)} -> {fa}")
print("\nlast 8 readings:", [(a, b, c) for a, b, c, _ in res[-8:]])
