"""B1 — validate Wang-2020's HMM regime spec on our full window, walk-forward.

Spec per paper: 3-state Gaussian HMM, features = daily return + 10d rolling
volatility, trailing 2707-trading-day window, full covariance. Deviations
(noted): monthly refit instead of daily (compute); vol = 10d stdev of returns
instead of price-level MSE-vs-MA10 (their raw-price MSE is level-dependent and
degenerates over a 55-year window).

Walk-forward: at each month-end, fit ONLY on the trailing window, label states
by in-window mean return (bear = lowest, bull = highest), record the posterior
state of the last observation. No lookahead: the label at month m uses data
through m only.

Output: state timeline vs known bear episodes + next-month SPY return
conditional on the prior month-end state.
"""
import json, datetime, warnings
import numpy as np
from hmmlearn.hmm import GaussianHMM

warnings.filterwarnings("ignore")
SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"

r = json.load(open(f"{SC}/gspc-daily.json"))["chart"]["result"][0]
q = r["indicators"]["quote"][0]
rows = [(datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date(), c)
        for ts, c in zip(r["timestamp"], q["close"]) if c is not None]
dates = [d for d, _ in rows]
close = np.array([c for _, c in rows])
ret = np.diff(close) / close[:-1]
dates = dates[1:]
vol = np.array([ret[max(0, i - 9):i + 1].std() for i in range(len(ret))])
X = np.column_stack([ret, vol])

WINDOW = 2707
month_ends = []
for i in range(WINDOW, len(dates) - 1):
    if dates[i].month != dates[i + 1].month:
        month_ends.append(i)
month_ends.append(len(dates) - 1)

results = []
for i in month_ends:
    Xi = X[i - WINDOW + 1:i + 1]
    best = None
    for seed in (1, 7):   # two inits; keep the higher-likelihood fit
        try:
            m = GaussianHMM(n_components=3, covariance_type="full",
                            n_iter=75, random_state=seed)
            m.fit(Xi)
            s = m.score(Xi)
            if best is None or s > best[0]:
                best = (s, m)
        except Exception:
            continue
    if best is None:
        continue
    m = best[1]
    post = m.predict_proba(Xi)[-1]
    state = int(np.argmax(post))
    means = m.means_[:, 0]
    order = np.argsort(means)          # [bear, mid, bull] by mean return
    label = {order[0]: "BEAR", order[1]: "CHOP", order[2]: "BULL"}[state]
    results.append((f"{dates[i].year:04d}-{dates[i].month:02d}", label,
                    round(float(post.max()), 2)))

out = {ym: lab for ym, lab, _ in results}
json.dump([{"month": a, "state": b, "conf": c} for a, b, c in results],
          open(f"{SC}/b1_states.json", "w"), indent=1)

# --- report ---------------------------------------------------------------
n = len(results)
frac = {s: sum(1 for _, l, _ in results if l == s) / n for s in ("BULL", "CHOP", "BEAR")}
print(f"walk-forward month-ends: {n} ({results[0][0]} .. {results[-1][0]})")
print("state shares:", {k: f"{v:.0%}" for k, v in frac.items()})

EPISODES = {
    "1987 crash":        ["1987-09", "1987-10", "1987-11"],
    "1990 bear":         ["1990-08", "1990-09", "1990-10"],
    "2000-02 bear":      ["2001-03", "2001-09", "2002-07", "2002-09"],
    "2008 GFC":          ["2008-01", "2008-06", "2008-10", "2009-02"],
    "2011 correction":   ["2011-08", "2011-09"],
    "2015-16 corr":      ["2015-09", "2016-01"],
    "2018 Q4":           ["2018-11", "2018-12"],
    "2020 COVID":        ["2020-03", "2020-04"],
    "2022 GRIND":        ["2022-02", "2022-05", "2022-07", "2022-09", "2022-12"],
    "Aug-2024 spike":    ["2024-08"],
    "2025 correction":   ["2025-02", "2025-03", "2025-04"],
}
print("\nknown bear episodes — month-end state readings:")
for name, months in EPISODES.items():
    reads = [f"{m}:{out.get(m, '—')}" for m in months]
    print(f"  {name:18} {'  '.join(reads)}")

# calm-period false alarms: BEAR readings in known strong bull years
calm = [ym for ym, l, _ in results
        if l == "BEAR" and ym[:4] in ("1996", "1997", "2013", "2014", "2017",
                                      "2019", "2021", "2023", "2024")]
print(f"\nBEAR month-ends inside strong bull years: {len(calm)} -> {calm[:14]}")

# utility: next-month SPY return conditional on prior month-end state
mret = {}
for k in range(len(month_ends) - 1):
    i, j = month_ends[k], month_ends[k + 1]
    ym = f"{dates[i].year:04d}-{dates[i].month:02d}"
    mret[ym] = close[j + 1] / close[i + 1] - 1.0
print("\nnext-month SPY return conditional on month-end state:")
for s in ("BULL", "CHOP", "BEAR"):
    sel = [mret[ym] for ym, l, _ in results if l == s and ym in mret]
    if sel:
        arr = np.array(sel)
        print(f"  {s:5} n={len(arr):3}  mean {arr.mean():+7.2%}  median {np.median(arr):+7.2%}  "
              f"worst {arr.min():+7.2%}  %neg {np.mean(arr < 0):.0%}")
