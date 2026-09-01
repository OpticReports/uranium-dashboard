"""Stage 1 bake-off: baselines only. Run with
    python3 -m research.forecast_fm.run
from btc-paper-engine/backend.

WHAT THIS DOES AND DOES NOT SETTLE. It establishes the bar the foundation
models have to clear, using the estimator the live sizer uses today (ATR14)
as the incumbent. It cannot say anything about TimesFM-3 or Chronos-2 -
those need torch and weights, and the adapter interface they plug into is
`sigma_hat -> (n, 9) quantiles`, or their own nine quantiles directly.

HOLDOUT is not touched. Section 4 allows one touch AFTER rules 1-3 pass.
"""
from __future__ import annotations

import numpy as np

from . import data as D
from . import metrics as M
from . import models as Mod


def build() -> dict:
    bars = D.load_bars(D.bars_path())
    r = D.log_returns(bars["close"])
    y = D.forward_realized_vol(bars["close"], D.HORIZON_BARS)
    masks = D.split_masks(bars["ts"])

    sig = {
        "ATR14 (incumbent)": D.trailing_atr_frac(bars),
        "EWMA(0.94) close": Mod.ewma_sigma(r),
        # Same recursion, range input. Isolates estimator from model.
        "EWMA(0.94) range": Mod.ewma_sigma(Mod.parkinson_sigma(bars)),
        "RandomWalk(8)": Mod.trailing_sigma(r, D.HORIZON_BARS),
    }
    params = Mod.garch11_fit(r[masks["train"]])
    sig["GARCH(1,1)"] = Mod.garch11_sigma(r, params, D.HORIZON_BARS)
    return {"bars": bars, "y": y, "masks": masks, "sigma": sig,
            "garch": params}


def evaluate(built: dict) -> dict:
    y, masks, sig = built["y"], built["masks"], built["sigma"]
    out = {}
    for name, s in sig.items():
        valid = np.isfinite(y) & np.isfinite(s) & (s > 0)
        i_tr = D.eval_index(masks["train"], valid)
        i_va = D.eval_index(masks["validate"], valid)
        dress = Mod.QuantileDressing().fit(y[i_tr], s[i_tr])
        out[name] = {
            # TRAIN coverage is 80% by construction - reported only so the
            # comparison with VALIDATE is visible, never as evidence.
            "train": M.summary(y[i_tr], dress.apply(s[i_tr])),
            "validate": M.summary(y[i_va], dress.apply(s[i_va])),
            "curve": M.coverage_by_level(y[i_va], dress.apply(s[i_va])),
            "_dress": dress, "_sigma": s, "_iva": i_va,
        }
    return out


def _table(res: dict) -> str:
    hdr = (f"{'model':22} {'n':>5} {'coverage':>9} {'gate':>6} "
           f"{'pinball':>10} {'CRPS':>10}")
    lines = [hdr, "-" * len(hdr)]
    base = res["ATR14 (incumbent)"]["validate"]["pinball"]
    for name, r in sorted(res.items(),
                          key=lambda kv: kv[1]["validate"]["pinball"]):
        v = r["validate"]
        rel = 100.0 * (v["pinball"] / base - 1.0)
        lines.append(f"{name:22} {v['n']:5d} {v['coverage']:9.3f} "
                     f"{'PASS' if v['gate'] else 'FAIL':>6} "
                     f"{v['pinball']:10.3e} {v['crps']:10.3e}"
                     f"   {rel:+6.1f}% vs incumbent")
    return "\n".join(lines)


def charts(built: dict, res: dict, path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(16.5, 4.8))

    # 1. calibration curves on VALIDATE
    ax[0].plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    for name, r in res.items():
        ax[0].plot(M.LEVELS, r["curve"], marker="o", ms=3.5, label=name)
    ax[0].set_title("Calibration on VALIDATE\n(below the line = quantiles too low)")
    ax[0].set_xlabel("nominal level"); ax[0].set_ylabel("empirical P(y <= q)")
    ax[0].legend(fontsize=7); ax[0].grid(alpha=.3)

    # 2. coverage of the 10-90 band vs the gate
    names = list(res)
    cov = [res[n]["validate"]["coverage"] for n in names]
    ax[1].barh(names, cov, color=["#2a9d8f" if abs(c - .8) <= .05 else "#e76f51"
                                  for c in cov])
    ax[1].axvline(.80, color="k", lw=1)
    ax[1].axvspan(.75, .85, color="k", alpha=.08)
    ax[1].set_xlim(0, 1); ax[1].set_title("10-90 coverage (target 0.80 +/- 0.05)")
    ax[1].tick_params(labelsize=7); ax[1].grid(alpha=.3, axis="x")

    # 3. the incumbent's band against what actually happened
    inc = res["ATR14 (incumbent)"]
    i = inc["_iva"]; Q = inc["_dress"].apply(inc["_sigma"][i])
    t = built["bars"]["ts"][i].astype("datetime64[s]")
    ax[2].fill_between(t, Q[:, 0], Q[:, -1], alpha=.30, label="ATR14 10-90 band")
    ax[2].plot(t, Q[:, 4], lw=1, label="median")
    ax[2].plot(t, built["y"][i], lw=.9, color="k", label="realized")
    ax[2].set_title("Incumbent band vs realized fwd vol (VALIDATE)")
    ax[2].legend(fontsize=7); ax[2].grid(alpha=.3)
    ax[2].tick_params(axis="x", labelsize=7, rotation=30)

    fig.suptitle("Stage 1 bake-off - baselines only, non-overlapping 8-bar "
                 "windows. HOLDOUT untouched.", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    return path


def main() -> None:
    built = build()
    res = evaluate(built)
    o, a, b = built["garch"]
    print(f"\nGARCH(1,1) fitted on TRAIN: omega={o:.3e} alpha={a:.3f} "
          f"beta={b:.3f} persistence={a + b:.3f}\n")
    print(_table(res))
    print("\nTRAIN coverage is 80% by construction (the spread is fitted "
          "there); only the VALIDATE column is evidence.")
    print("HOLDOUT: sealed, not touched.")


if __name__ == "__main__":
    main()
