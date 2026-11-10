"""CANDIDATE D: is the shipped signal on a knife edge?

candD_instrument.py found the edge goes to zero on HL perp bars while spot bars
authorise $70,539, on series whose 4h close returns correlate 0.999123.  Either
the signal is fragile to tiny price differences, or my perp feed is wrong.  This
tests the first directly and cheaply: how often do the two series fire the SAME
signal on the SAME bar?  No Kelly, no bootstrap -- just the gate conditions.

Run: python3 research/scale/candD_signal_agree.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar, eval_signal, eval_donchian             # noqa: E402
from app.engine.replay import compute_indicators                        # noqa: E402
from app.config import RESEARCH_SIGNAL                                  # noqa: E402

SPOTB = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
PERPB = os.path.join(HERE, "candD_bars_4h_btcperp.csv")
OUT = os.path.join(HERE, "candD_signal_agree.json")


def bars_from(p):
    with open(p) as f:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(f)]


def sigs(bars, vf):
    scfg = dataclasses.replace(RESEARCH_SIGNAL, vol_filter=vf)
    inds = compute_indicators(bars)
    pb, dn = {}, {}
    for i, b in enumerate(bars):
        if i < 210:
            continue
        pb[b.ts] = eval_signal(b, inds[i], scfg)
        dn[b.ts] = eval_donchian(b, inds[i])
    return pb, dn


def main() -> None:
    spot, perp = bars_from(SPOTB), bars_from(PERPB)
    res = {}
    for vf in (True, False):
        sp, sd_ = sigs(spot, vf)
        pp, pd_ = sigs(perp, vf)
        common = sorted(set(sp) & set(pp))
        # pullback signal agreement
        fire_s = [t for t in common if sp[t]]
        fire_p = [t for t in common if pp[t]]
        both = [t for t in common if sp[t] and pp[t]]
        same = [t for t in both if sp[t] == pp[t]]
        union = sorted(set(fire_s) | set(fire_p))
        # donchian agreement (no volume term, so a pure price control)
        d_s = [t for t in common if sd_[t]]
        d_p = [t for t in common if pd_[t]]
        d_both = [t for t in common if sd_[t] and pd_[t]]
        d_same = [t for t in d_both if sd_[t] == pd_[t]]
        d_union = sorted(set(d_s) | set(d_p))
        res[f"vol_filter_{vf}"] = {
            "n_common_bars": len(common),
            "pullback": {
                "spot_fires": len(fire_s), "perp_fires": len(fire_p),
                "both_fire": len(both), "same_side": len(same),
                "union": len(union),
                "jaccard_agreement": len(both) / len(union) if union else None,
                "spot_only": len(set(fire_s) - set(fire_p)),
                "perp_only": len(set(fire_p) - set(fire_s))},
            "donchian_control": {
                "spot_fires": len(d_s), "perp_fires": len(d_p),
                "both_fire": len(d_both), "same_side": len(d_same),
                "jaccard_agreement": len(d_both) / len(d_union) if d_union else None},
        }
        r = res[f"vol_filter_{vf}"]
        print(f"\nvol_filter={vf}   ({len(common)} common bars)")
        print(f"  PULLBACK  spot fires {len(fire_s):4d}  perp fires {len(fire_p):4d}  "
              f"both {len(both):4d}  same side {len(same):4d}")
        print(f"            agreement (both/union) "
              f"{r['pullback']['jaccard_agreement']:.1%}   "
              f"spot-only {r['pullback']['spot_only']}, "
              f"perp-only {r['pullback']['perp_only']}")
        print(f"  DONCHIAN  spot {len(d_s):4d}  perp {len(d_p):4d}  both {len(d_both):4d}"
              f"  agreement {r['donchian_control']['jaccard_agreement']:.1%}"
              f"   (pure price control -- no volume term)")

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
