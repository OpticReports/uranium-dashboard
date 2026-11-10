"""Selection-noise null (registered guard 5) + binomial-noise context.

Null: for each of the 12 real rules, take its per-leg trade-drop fraction on
half B; draw random 30-day-block gates with the same drop fraction on the
BASELINE trade list (trade-list basis — ignores path effects; the real rules
were full replays, this null is the cheap-but-standard block-random referee
the prior panels used). Per draw: best-of-12 WR gain and best-of-12 MAR.
200 draws -> q95.
"""
import os, sys, json
import numpy as np

# bars CSV: argv[1] or BARS_CSV env (regenerate with scripts/fetch_bars.py)
if len(sys.argv) > 1:
    os.environ["BARS_CSV"] = sys.argv[1]
if not os.environ.get("BARS_CSV"):
    sys.exit("usage: research_winrate_null.py <bars.csv>  "
             "(fetch with scripts/fetch_bars.py)")
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)
sys.argv = ["research_winrate_null.py", os.environ["BARS_CSV"]]
from research_winrate import run_gated, SPLIT  # noqa: E402  (loads bars once)

b3, b4 = run_gated()
# baseline blend step stream on half B
evs = sorted([(t.exit_ts, "P", t) for t in b3.trades] + [(t.exit_ts, "T", t) for t in b4.trades])
p3 = p4 = 1.0
steps = []
for ts, which, t in evs:
    ratio = t.equity_after / (b3 if which == "P" else b4).cfg.start_equity
    if which == "P":
        r = (ratio / p3 - 1) * 0.75; p3 = ratio
    else:
        r = (ratio / p4 - 1) * 0.25; p4 = ratio
    steps.append((ts, which, 2.0 * r))
B = [s for s in steps if s[0] >= SPLIT]
rets = np.array([s[2] for s in B])
legs = np.array([s[1] for s in B])
ts_b = np.array([s[0] for s in B])
nP, nT = int((legs == "P").sum()), int((legs == "T").sum())

def wr(mask):
    r = rets[mask]
    w = (r > 0).sum(); l = (r < 0).sum()
    return 100.0 * w / (w + l) if w + l else np.nan

def mar(mask):
    r = rets[mask]
    if len(r) < 5:
        return np.nan
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(eq)
    mdd = (eq / peak - 1).min()
    t = ts_b[mask]
    yrs = (t[-1] - t[0]) / (365.25 * 86400)
    if yrs <= 0.2 or mdd > -0.005:
        return np.nan
    return (eq[-1] ** (1 / yrs) - 1) / abs(mdd)

base_wr, base_mar = wr(np.ones(len(B), bool)), mar(np.ones(len(B), bool))
print(f"baseline half-B: WR={base_wr:.1f}% MAR={base_mar:.2f} nP={nP} nT={nT}")
print(f"binomial SE at n={len(B)}: {100*np.sqrt(0.5*0.5/len(B)):.1f}pp; "
      f"per-year n~78 SE: {100*np.sqrt(0.25/78):.1f}pp")

# per-rule (leg, keep fraction) on half B, from the real runs
RULE_DROPS = [  # (pull_keep, don_keep) on half B vs baseline nP=115, nT=78
    (89/115, 1.0), (87/115, 1.0), (55/115, 1.0), (67/115, 1.0),  # P1a-fA,P1a-fB,P1b-fA,P1b-fB
    (95/115, 1.0), (112/115, 1.0), (77/115, 1.0),                # P2,P3,P4
    (1.0, 43/78), (1.0, 68/78),                                  # D2a,D2b (D1/D3 drop ALL donchian - deterministic mix arithmetic, excluded)
    (109/115, 1.0),                                              # E1 (E2 adds trades; treat as keep-all)
]
BLOCK = 30 * 86400
blocks = ((ts_b - ts_b[0]) // BLOCK).astype(int)
uniq = np.unique(blocks)
rng = np.random.default_rng(7)
best_dwr, best_mar = [], []
for d in range(200):
    dwr_draw, mar_draw = -1e9, -1e9
    for pk, tk in RULE_DROPS:
        keep = np.ones(len(B), bool)
        for leg, frac in (("P", pk), ("T", tk)):
            if frac >= 1.0:
                continue
            # random 30d blocks off until leg-drop fraction reached
            leg_mask = legs == leg
            order = rng.permutation(uniq)
            target_drop = int(round((1 - frac) * leg_mask.sum()))
            dropped = 0
            for blk in order:
                if dropped >= target_drop:
                    break
                m = leg_mask & (blocks == blk) & keep
                keep[m] = False
                dropped += int(m.sum())
        dwr_draw = max(dwr_draw, wr(keep) - base_wr)
        m_ = mar(keep)
        if not np.isnan(m_):
            mar_draw = max(mar_draw, m_)
    best_dwr.append(dwr_draw)
    best_mar.append(mar_draw)
best_dwr, best_mar = np.array(best_dwr), np.array(best_mar)
print(f"\nbest-of-12 random block-gate null on half B (200 draws):")
print(f"  dWR: median={np.median(best_dwr):+.1f}pp q95={np.quantile(best_dwr,0.95):+.1f}pp")
print(f"  MAR: median={np.median(best_mar):.2f} q95={np.quantile(best_mar,0.95):.2f}")
print(f"\nobserved best real dWR on B: D2a +3.8pp | best real MAR on B: ER-q40 1.18")
