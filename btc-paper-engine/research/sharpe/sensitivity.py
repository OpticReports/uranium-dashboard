"""PREREG 'reported alongside': BitMEX vs Hyperliquid funding over their
overlap, and the H3a sleeve / account re-run on HL funding. Never decides."""
import json, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sharpe_lib as S, run as R                                    # noqa: E402

W = S.World()
hl = S.load_funding("funding_hyperliquid_btc.csv")
bm = W.funding
out = {"per_year_ann_pct": {}}
for y in range(2023, 2027):
    a, b = S.ts_of(f"{max(y,2023)}-{'05-13' if y == 2023 else '01-01'}"), S.ts_of(f"{y}-12-31") + 86399
    b = min(b, S.ts_of("2026-09-16"))
    row = {}
    for n, (ts, r) in {"bitmex": bm, "hl": hl}.items():
        m = (ts >= a) & (ts <= b)
        row[n] = float(r[m].sum() / ((b - a) / 86400) * 365 * 100)
    out["per_year_ann_pct"][str(y)] = row
# daily funding correlation
def daily(ts, r, a, b):
    m = (ts >= a) & (ts < b); d = (ts[m] // 86400)
    s = {}
    for k, v in zip(d, r[m]): s[k] = s.get(k, 0.0) + v
    return s
a, b = S.ts_of("2023-05-13"), S.ts_of("2026-09-16")
db, dh = daily(*bm, a, b), daily(*hl, a, b)
ks = sorted(set(db) & set(dh))
out["daily_corr"] = float(np.corrcoef([db[k] for k in ks], [dh[k] for k in ks])[0, 1])
win = ("2023-05-13", "2026-07-31")
for n, f in {"bitmex": bm, "hl": hl}.items():
    x = R.account(W, {"carry_s"}, *win, fund=f)
    out[f"H3a_{n}"] = dict(sharpe=x["sharpe"], per_yr=x["per_yr"], maxdd=x["maxdd"],
                           sleeve_per_yr=float(np.sum(x["d_car"]) / x["years"]),
                           funding=x["carry"]["funding"], fees=x["carry"]["fees"])
base = R.account(W, set(), *win)
out["baseline_same_window"] = dict(sharpe=base["sharpe"], per_yr=base["per_yr"], maxdd=base["maxdd"])
# BitMEX funding level per calendar year over the full history (context)
out["bitmex_per_year_ann_pct"] = {}
for y in range(2016, 2027):
    a = S.ts_of(f"{y}-01-01") if y > 2016 else S.ts_of("2016-06-01"); b = min(S.ts_of(f"{y}-12-31") + 86399, S.ts_of("2026-09-16"))
    m = (bm[0] >= a) & (bm[0] <= b)
    out["bitmex_per_year_ann_pct"][str(y)] = float(bm[1][m].sum() / ((b - a) / 86400) * 365 * 100)
json.dump(out, open(os.path.join(HERE, "sensitivity.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
