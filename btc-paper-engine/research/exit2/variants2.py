"""EXIT2 registered grid (PREREG.md §3). Changing it after registration is a
logged amendment."""
from harness2 import X

V1 = [X(name=f"V1_volscale_{k}_b{int(b * 100)}", vs_band=b, vs_kind=k)
      for k in ("atr", "rv") for b in (0.10, 0.25)]
V2 = ([X(name=f"V2_tscale_{nm}_d{int(d)}", ts_set=hs, ts_div=d, ts_mode="scale")
       for nm, hs in (("fast", (30, 90, 270)), ("slow", (90, 270, 810))) for d in (1.0, 2.0)]
      + [X(name="V2_tscale_single270_d2", ts_set=(270,), ts_div=2.0, ts_mode="scale")]
      + [X(name=f"V2_tflip_{nm}", ts_set=hs, ts_div=2.0, ts_mode="flip")
         for nm, hs in (("fast", (30, 90, 270)), ("slow", (90, 270, 810)))])
V3 = [X(name=f"V3_regime_{m}", rg_map=m)
      for m in ("lowvol_tight", "highvol_wide", "vol_both", "vol_inverse",
                "align", "er", "vol_both_align")]
V4 = ([X(name=f"V4_acc_time_a{a}_min{mn}", acc_alpha=a, acc_min=mn)
       for a in (0.25, 0.5) for mn in (2.5, 3.5)]
      + [X(name=f"V4_acc_profit_b{b}", accp_beta=b) for b in (1.0, 2.0)]
      + [X(name=f"V4_psar_max{m}", psar_max=m) for m in (0.10, 0.20)])
V5 = [X(name=f"V5_logit_p{int(t * 100)}", lr_theta=t) for t in (0.6, 0.7)]
ALL = V1 + V2 + V3 + V4 + V5
assert len(ALL) == 28, len(ALL)


def family(x):
    return x.name.split("_")[0]
