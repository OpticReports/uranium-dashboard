"""R9 pre-result gates (registered): the harness may not be read until these pass.
G1 alignment-by-construction on a synthetic panel; G2 planted-leak detector
sanity (a leaky signal must light up, a clean one must not); G3 size-shuffle
null; G4 census tables."""
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])

# G1: hand-checkable forward-return arithmetic on one symbol
import json
bars = json.load(open("/home/user/uranium-dashboard/genomics-alpha-tracker/backend/data/backtest_bars.json"))
crsp = pd.DataFrame(bars["CRSP"]).set_index("date")["adj_close"]
xbi = pd.DataFrame(bars["XBI"]).set_index("date")["adj_close"]
t = 100
d1, d6 = crsp.index[t + 1], crsp.index[t + 6]      # CRSP's own trading grid
hand = (crsp[d6] / crsp[d1] - 1) - (xbi[d6] / xbi[d1] - 1)
got = panel[(panel.symbol == "CRSP")].iloc[t]["fwd5"]
assert abs(hand - got) < 1e-12, (hand, got)
print(f"G1 PASS: fwd5 = close(t+1)->close(t+6) XBI-excess, hand-checked ({hand:+.5f})")

# G2: a deliberately LEAKY signal (uses fwd21 itself) must show |IC| ~ 0.9+;
# pure noise must show ~0. This proves the IC machinery can detect a leak.
def daily_ic(df, sig, fwd="fwd21"):
    ics = []
    for _, g in df.groupby("date"):
        v = g[[sig, fwd]].dropna()
        if len(v) >= 6:
            ics.append(v[sig].rank().corr(v[fwd].rank()))
    return np.nanmean(ics), len(ics)

rng = np.random.default_rng(20260827)
p = panel.copy()
p["leaky"] = p["fwd21"]
p["noise"] = rng.normal(size=len(p))
ic_leak, _ = daily_ic(p, "leaky")
ic_noise, n = daily_ic(p, "noise")
assert ic_leak > 0.95 and abs(ic_noise) < 0.02, (ic_leak, ic_noise)
print(f"G2 PASS: planted leak IC {ic_leak:.3f}, noise IC {ic_noise:+.4f} (n={n} days)")

# G3: shuffle sizes ACROSS SYMBOLS -> the size-interaction stat must be null.
# Interaction stat: IC(c_cat, fwd21) in small tercile minus large tercile.
def interaction(df, sizecol="z1_mktcap", sig="c_cat"):
    df = df.dropna(subset=[sizecol, sig, "fwd21"]).copy()
    ics = {"S": [], "L": []}
    for _, g in df.groupby("date"):
        if len(g) < 12:
            continue
        q = g[sizecol].rank(pct=True)
        for lab, m in (("S", q <= 1/3), ("L", q > 2/3)):
            v = g[m]
            if len(v) >= 5:
                ics[lab].append(v[sig].rank().corr(v["fwd21"].rank()))
    return np.nanmean(ics["S"]) - np.nanmean(ics["L"])

sh = panel.copy()
symmap = dict(zip(sorted(sh.symbol.unique()),
                  rng.permutation(sorted(sh.symbol.unique()))))
sizes = panel.set_index(["date", "symbol"])["z1_mktcap"]
sh["z1_shuf"] = [sizes.get((d, symmap[s]), np.nan)
                 for d, s in zip(sh.date, sh.symbol)]
stats = [interaction(sh.assign(z1_mktcap=sh["z1_shuf"]))]
print(f"G3: shuffled-size interaction stat {stats[0]:+.4f} (expect ~0; "
      f"formal null via bootstrap in stage 1)")

# G4: census — names per B1 bucket per year
panel["year"] = panel.date.dt.year
panel["b1"] = pd.cut(panel.z1_mktcap, [0, 1e9, 10e9, np.inf],
                     labels=["<1B", "1-10B", ">=10B"])
cen = panel.dropna(subset=["b1"]).groupby(["year", "b1"], observed=True)["symbol"] \
    .nunique().unstack()
print("G4 census (distinct names per B1 bucket per year):")
print(cen.to_string())
