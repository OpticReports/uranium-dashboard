"""Fidelity of the synthetic KMLM against the published index (before the fund) and the real fund (after):
bars F1-F3 of PREREG.md as amended by DEVIATIONS.md 1-2. Writes out/fidelity.json. F4 and F5 (the symphony
run on the synthetic) are in v2_symphony.py."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "kmlm_2026-11"))
import data as kdata  # noqa: E402
import ksim  # noqa: E402
import ksynth as ky  # noqa: E402
import sdata  # noqa: E402

V0, V1, V_MID = "2021-03-01", "2024-03-28", "2022-08-01"


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def ann(r):
    lvl = 1.0
    for x in r:
        lvl *= 1 + x
    m = sum(r) / len(r)
    return lvl ** (252 / len(r)) - 1, math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1) * 252)


def flags(px, xlk, lo, hi):
    ra, rb = ksim.rsi_series(xlk, 10), ksim.rsi_series(px, 10)
    return {d: ra[d] > rb[d] for d in sorted(px) if lo <= d <= hi and ra.get(d) is not None and rb.get(d) is not None}


def main():
    ix = sdata.index_monthly()
    # ---- the one scalar, from the published index before the fund (all 22 markets present)
    g, info = ky.build(1.0, start="2000-01-01", gross=True, detail=True)
    full = min(d for d, n in info.items() if sum(n.values()) == 22)
    gm = ky.monthly(g)
    tb = ky.monthly(sdata.tbill())
    cal_months = [m for m in sorted(gm) if full[:7] < m <= "2020-11" and m in ix]
    xs = [gm[m] for m in cal_months]
    ys = [ix[m] - tb.get(m, 0.0) for m in cal_months]
    exposure = sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs)
    out = {"exposure": exposure, "calibration": {"months": [cal_months[0], cal_months[-1]], "n": len(cal_months),
                                                 "all_22_markets_from": full}}
    # ---- before the fund: synthetic (gross of fund costs, with T-bills) vs the published index, monthly
    s = ky.build(exposure, start="1988-01-01")
    sm = ky.monthly({d: r + ky.COSTS / 252 for d, r in s.items()})
    for name, lo, hi in (("2008-2020 (all 22 markets, today's rules)", cal_months[0], "2020-11"),
                         ("2005-2007 (EV rules, markets missing)", "2005-01", cal_months[0]),
                         ("1988-2004 (the index used OLDER rules)", "1988-02", "2004-12")):
        ms = [m for m in sorted(sm) if lo <= m <= hi and m in ix]
        a, b = [sm[m] for m in ms], [ix[m] for m in ms]
        sa = math.sqrt(sum((x - sum(a) / len(a)) ** 2 for x in a) / (len(a) - 1) * 12)
        sb = math.sqrt(sum((x - sum(b) / len(b)) ** 2 for x in b) / (len(b) - 1) * 12)
        te = math.sqrt(sum((x - y - (sum(a) - sum(b)) / len(a)) ** 2 for x, y in zip(a, b)) / (len(a) - 1) * 12)
        out.setdefault("vs_index_monthly", {})[name] = {"months": len(ms), "corr": corr(a, b), "synthetic_vol": sa, "index_vol": sb,
                                                         "tracking_error": te, "mean_gap_per_yr": (sum(a) - sum(b)) / len(a) * 12}
    # ---- after: against the real fund (corrected total return), daily
    fund = sdata.fund_tr(V1)
    fr = kdata.rets(fund)
    xlk = kdata.series("XLK", V1)
    rym = kdata.series("RYMFX", V1)
    synth_px = ky.level(ky.build(exposure, start="2015-01-01"))
    out["vs_fund"] = {}
    for name, lo, hi in (("whole overlap", V0, V1), ("first part", V0, "2022-07-31"), ("second part", V_MID, V1),
                         ("pre-registered second half", "2023-12-01", V1)):
        days = [d for d in sorted(fr) if lo <= d <= hi and d in s]
        a, b = [s[d] for d in days], [fr[d] for d in days]
        fa, fs_ = flags(fund, xlk, lo, hi), flags(synth_px, xlk, lo, hi)
        fy = flags(rym, xlk, lo, hi)
        common = [d for d in fa if d in fs_]
        flips = [d1 for d0, d1 in zip(common, common[1:]) if fa[d0] != fa[d1]]
        ca, cb = ann(a), ann(b)
        fma, fmb = ky.monthly({d: s[d] for d in days}), ky.monthly({d: fr[d] for d in days})
        mm = sorted(fma)[1:-1] if len(fma) > 6 else sorted(fma)
        ry = kdata.rets(rym)
        dr = [d for d in days if d in ry]
        out["vs_fund"][name] = {
            "sessions": len(days), "daily_corr": corr(a, b), "monthly_corr": corr([fma[m] for m in mm], [fmb[m] for m in mm]),
            "flag_agreement": sum(fa[d] == fs_[d] for d in common) / len(common), "flag_days": len(common),
            "flips": len(flips), "flips_matched_same_day": sum(1 for d in flips if fs_[d] == fa[d] and fs_[common[common.index(d) - 1]] != fs_[d]),
            "synthetic": {"return": ca[0], "vol": ca[1]}, "fund": {"return": cb[0], "vol": cb[1]},
            "vol_ratio": ca[1] / cb[1], "return_gap": ca[0] - cb[0],
            "rymfx": {"daily_corr": corr([ry[d] for d in dr], [fr[d] for d in dr]),
                      "flag_agreement": sum(fa[d] == fy[d] for d in fa if d in fy) / sum(1 for d in fa if d in fy)},
            "constant_flag_agreement": max(sum(fa.values()), len(fa) - sum(fa.values())) / len(fa)}
    for part in ("whole overlap", "second part", "pre-registered second half"):
        v = out["vs_fund"][part]
        v["bars"] = {"F1_daily_corr>=0.90": v["daily_corr"] >= 0.90, "F2_flag>=0.95": v["flag_agreement"] >= 0.95,
                     "F3_vol_within_15pct": abs(v["vol_ratio"] - 1) <= 0.15, "F3_return_within_3pts": abs(v["return_gap"]) <= 0.03}
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "out", "fidelity.json"), "w"), indent=1)
    json.dump({"exposure": exposure, "ret": s}, open(sdata.CACHE + "/synth_v1.json", "w"))
    print(f"exposure {exposure:.3f} (index months {cal_months[0]}..{cal_months[-1]}, n {len(cal_months)}; all 22 markets from {full})")
    for k, v in out["vs_index_monthly"].items():
        print(f"  index {k}: n {v['months']} corr {v['corr']:.3f} vol {v['synthetic_vol']:.1%} vs {v['index_vol']:.1%} TE {v['tracking_error']:.1%} gap {v['mean_gap_per_yr']:+.1%}/yr")
    for k, v in out["vs_fund"].items():
        print(f"  fund {k}: n {v['sessions']} daily corr {v['daily_corr']:.3f} monthly {v['monthly_corr']:.3f} flag {v['flag_agreement']:.1%} "
              f"(flips {v['flips_matched_same_day']}/{v['flips']}; constant {v['constant_flag_agreement']:.1%}) vol {v['synthetic']['vol']:.1%} vs {v['fund']['vol']:.1%} "
              f"ret {v['synthetic']['return']:+.1%} vs {v['fund']['return']:+.1%} | RYMFX corr {v['rymfx']['daily_corr']:.3f} flag {v['rymfx']['flag_agreement']:.1%}"
              + (f" | bars {v['bars']}" if "bars" in v else ""))


if __name__ == "__main__":
    main()
