#!/usr/bin/env python3
"""DRIVER: reproduces variants_ext.json / variants_real.json end to end.

Preserved per the house rule on builder scripts (results.md add. 27 fix list;
re-flagged by the addendum-31 counter-agent as a reproducibility gap).

Pipeline:
  1. zvol_proxy.json  <- SVXY returns x beta, halved before the 2018-02-28
     -1x/-0.5x structural break, floored at -95%/day.  beta = 0.748 fitted
     through the origin on the 828-day real-ZVOL overlap.  NOTE (auditor):
     this beta is fitted on the SAME window used to validate it -- the CAGR
     match is near-tautological; a split-sample fit gives 0.787 -> 0.711.
  2. VXZ  <- VIXM x 0.866 before 2018-01-25   (post-2018 fit, applied pre)
     PULS <- BIL  x 1.0   before 2018-04-10   (near-cash; leg is "flat")
     => ~43% of the 14.8y record is synthetic in at least one leg.
  3. spy_sigma_rt.npy from run_rt.py (rolling 10y GARCH fit, monthly refit).
  4. study.build() applies the 8 variants.
Run:  python3 build_variants.py
"""
import json, numpy as np, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study as S
SC = os.path.dirname(HERE)

BREAK = "2018-02-28"
ZVOL_BETA = 0.748
SPLICES = [("VXZ", "VIXM", 0.866), ("PULS", "BIL", 1.0)]


def load(t):
    return json.load(open(f"{SC}/synth/{t}.json"))


def build_zvol_proxy():
    sx = load("SVXY"); k = sorted(sx); out = {}; v = 1.0
    for i in range(1, len(k)):
        d = k[i]
        r = sx[k[i]] / sx[k[i-1]] - 1
        scale = ZVOL_BETA if d > BREAK else ZVOL_BETA / 2.0
        v *= (1 + max(scale * r, -0.95))
        out[d] = v
    json.dump(out, open(f"{HERE}/zvol_proxy.json", "w"))
    return out


def splice(real, src, beta):
    rk = sorted(real); s0 = rk[0]; out = dict(real); pk = sorted(src); v = real[s0]
    for d in reversed([x for x in pk if x < s0]):
        n = pk[pk.index(d) + 1]
        v = v / (1 + beta * (src[n] / src[d] - 1))
        out[d] = v
    return out


def main():
    zvol = build_zvol_proxy()
    tk = {"SPY": load("SPY"), "UVXY": load("UVXY"), "ZVOL": zvol}
    for tgt, src, beta in SPLICES:
        tk[tgt] = splice(load(tgt), load(src), beta)
    sigma_full = np.load(f"{HERE}/spy_sigma_rt.npy")
    sbd = dict(zip(json.load(open(f"{SC}/spy_d.json")), sigma_full))
    for tag, lo in (("ext", "2011-10-05"), ("real", "2023-04-19")):
        D = sorted(d for d in set.intersection(*[set(s) for s in tk.values()]) if d >= lo)
        px = {t: np.array([s[d] for d in D]) for t, s in tk.items()}
        sig = np.array([sbd.get(d, np.nan) for d in D])
        V = S.build(D, px, sig)
        json.dump({k: [float(x) for x in np.nan_to_num(v)] for k, v in V.items()},
                  open(f"{HERE}/variants_{tag}.json", "w"))
        json.dump(D, open(f"{HERE}/dates_{tag}.json", "w"))
        print(f"{tag}: {D[0]}..{D[-1]} ({len(D)}d)  baseline "
              f"CAGR {S.stats(V['BASELINE'])['cagr']:+.1%} DD {S.stats(V['BASELINE'])['dd']:.1%}")


if __name__ == "__main__":
    main()
