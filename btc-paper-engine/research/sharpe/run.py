"""Run the registered Sharpe-study candidates (PREREG.md). Writes results.json
and curves.json. Usage: python3 run.py [H4 <spec>]

H4 spec (after H1-H3 are judged): comma list of passers, e.g. "vol,carry_s".
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sharpe_lib as S                                             # noqa: E402

END = "2026-07-31"
ERAS = {"E1 2013-16": ("2013-01-01", "2016-12-31"),
        "E2 2017-19": ("2017-01-01", "2019-12-31"),
        "E3 2020-21": ("2020-01-01", "2021-12-31"),
        "E4 2022-24H1": ("2022-01-01", "2024-06-30"),
        "E5 2024H2-26 (spent)": ("2024-07-01", "2026-07-31"),
        "E6 2026-08+ (fresh)": ("2026-08-01", "2026-12-31")}
FULL_D = ("2013-01-01", END)
FULL_C = ("2016-06-01", END)


def build(spec):
    """spec: set of {'vol','gate','carry_s','carry_g'}"""
    return dict(vol="vol" in spec, gate="gate" in spec,
                carry=("s" if "carry_s" in spec else
                       "g" if "carry_g" in spec else None))


CONFIGS = {"baseline": set(), "H1 vol-target": {"vol"},
           "H2 200d gate": {"gate"}, "H3a carry static": {"carry_s"},
           "H3b carry gated": {"carry_g"}}


def account(W, spec, a, b, fund=None):
    t0, t1 = S.ts_of(a), S.ts_of(b) + 86399
    c = build(spec)
    ts, dpnl, r = S.directional(W, t0, t1, c["vol"], c["gate"])
    cpnl, meta = np.zeros(len(ts)), {}
    if c["carry"]:
        fts, fr = fund if fund is not None else W.funding
        cpnl, meta = S.carry(ts, W.closes["btcusd"], fts, fr,
                             gated=c["carry"] == "g")
    tot = dpnl + cpnl
    days, d = S.daily_pnl(ts, tot)
    _, dd_dir = S.daily_pnl(ts, dpnl)
    _, dd_car = S.daily_pnl(ts, cpnl)
    yrs = (ts[-1] - ts[0] + S.H.BAR_S) / (365.25 * 86400)
    peak_gross = float(np.nanmax(r.gross_lev * r.equity))
    return dict(ts=ts, tot=tot, d=d, d_dir=dd_dir, d_car=dd_car, days=days,
                sharpe=S.sharpe(d), per_yr=float(tot[-1] / yrs),
                maxdd=S.max_dd_usd(tot), peak_gross=peak_gross,
                carry=meta, years=float(yrs))


def row(x):
    return {k: v for k, v in x.items()
            if k not in ("ts", "tot", "d", "d_dir", "d_car", "days")}


def main():
    t = time.time()
    W = S.World()
    print(f"loaded {time.time() - t:.0f}s", flush=True)
    configs = dict(CONFIGS)
    if len(sys.argv) > 2 and sys.argv[1] == "H4":
        configs = {"baseline": set(), "H4 " + sys.argv[2]: set(sys.argv[2].split(","))}
    res, curves = {}, {}
    for name, spec in configs.items():
        is_c = any(s.startswith("carry") for s in spec)
        full = FULL_C if is_c else FULL_D
        out = {}
        a = account(W, spec, *full)
        base = account(W, set(), *full)
        lo, hi = S.boot_delta(base["d"], a["d"])
        out["FULL"] = dict(window=full, **row(a), d_sharpe=a["sharpe"] - base["sharpe"],
                           boot90=(lo, hi), base_sharpe=base["sharpe"],
                           base_maxdd=base["maxdd"], base_per_yr=base["per_yr"],
                           dsr=S.dsr(a["d"], 2538))
        if is_c:
            out["FULL"]["corr_carry_vs_dir"] = float(np.corrcoef(a["d_dir"], a["d_car"])[0, 1])
            out["FULL"]["sharpe_carry_alone"] = S.sharpe(a["d_car"])
        curves[name] = dict(days=a["days"].tolist(), cum=np.cumsum(a["d"]).tolist())
        for en, (ea, eb) in ERAS.items():
            if is_c and en.startswith("E1"):
                ea = FULL_C[0]
            x = account(W, spec, ea, eb)
            y = account(W, set(), ea, eb)
            out[en] = dict(window=(ea, eb), sharpe=x["sharpe"], base=y["sharpe"],
                           d_sharpe=x["sharpe"] - y["sharpe"], per_yr=x["per_yr"],
                           maxdd=x["maxdd"], base_maxdd=y["maxdd"])
        res[name] = out
        f = out["FULL"]
        eras = " ".join(f"{out[e]['d_sharpe']:+.2f}" for e in list(ERAS)[:4])
        print(f"{name:18s} {f['window'][0][:4]}+ Sharpe {f['sharpe']:.2f} vs "
              f"{f['base_sharpe']:.2f} (d {f['d_sharpe']:+.2f}, 90% [{lo:+.2f},{hi:+.2f}]) "
              f"${f['per_yr']:,.0f}/yr maxDD ${f['maxdd']:,.0f} (base ${f['base_maxdd']:,.0f}) "
              f"| dE1-E4 {eras} | E5 {out[list(ERAS)[4]]['d_sharpe']:+.2f} "
              f"E6 {out[list(ERAS)[5]]['d_sharpe']:+.2f}", flush=True)
    tag = "h4" if len(configs) == 2 and "H4" in "".join(configs) else "results"
    json.dump(res, open(os.path.join(HERE, f"{tag}.json"), "w"), indent=1, default=float)
    json.dump(curves, open(os.path.join(HERE, f"curves_{tag}.json"), "w"))


if __name__ == "__main__":
    main()
