"""Exit-multiple distribution model for the deal analyzer.

Answers "what is the probability of >= Xx?" for a scored deal, with
every ingredient traceable to a proven source:

1. EMPIRICAL ANCHOR: the published Correlation Ventures bucket
   frequencies for US venture financing outcomes (n=21,640; buckets
   <1x, 1-5x, 5-10x, 10-20x, 20-50x, >50x). The base distribution is a
   lognormal body + Pareto tail fitted so its bucket masses reproduce
   the published frequencies (gate-tested tolerance below). Lognormal
   body: Cochrane (2005 JFE) / Korteweg-Sorensen (2010 RFS) lineage.
   Pareto tail: power-law behavior of venture returns per AngelList
   (Othman) alpha estimates; tail alpha is a fitted parameter that must
   land inside the literature range (gate-tested).
2. DEAL CONDITIONING: minimum-discrimination (KL-minimal) exponential
   tilt of the base distribution so it EXACTLY matches the deal's
   logged panel forecasts P(<1x) and P(>=10x). This adds no new
   judgment: it is the unique distribution closest to the empirical
   base that is consistent with numbers the panel already committed to
   the ledger (Kullback minimum discrimination information).
3. FEES: gross->net mapping net(g) = 1 + (1-carry)*(g-1) for g>1,
   0.95g below 1x (matches the audited EV-tree fee model).

What this model is NOT: a claim to deal-level foresight. The base rates
are proven; the tilt constraints are the panel's own Brier-scored
forecasts; accuracy of the COMBINATION is scored by the ledger over
time like every other forecast. Counter-agent audit required before
display (standing rule).

Calibration constants live in calibration.json next to this file so the
numbers are visible, cited, and swappable when better data lands.
"""

import json
import math
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# Multiple-axis grid: log-spaced 0.01x .. 1000x, dense enough that
# bucket integrals are stable.
GRID_N = 4000
GRID_LO, GRID_HI = 0.001, 1000.0


def _load_calibration():
    with open(os.path.join(_HERE, "calibration.json")) as f:
        return json.load(f)


def _grid():
    lo, hi = math.log(GRID_LO), math.log(GRID_HI)
    step = (hi - lo) / (GRID_N - 1)
    return [math.exp(lo + i * step) for i in range(GRID_N)]


def _base_density(x, mu, sigma, x_tail, alpha):
    """Lognormal(mu, sigma) body; Pareto(alpha) tail spliced at x_tail
    with density continuity. Returns unnormalized density."""
    if x <= 0:
        return 0.0
    ln_pdf = (
        math.exp(-((math.log(x) - mu) ** 2) / (2 * sigma**2))
        / (x * sigma * math.sqrt(2 * math.pi))
    )
    if x <= x_tail:
        return ln_pdf
    ln_at_splice = (
        math.exp(-((math.log(x_tail) - mu) ** 2) / (2 * sigma**2))
        / (x_tail * sigma * math.sqrt(2 * math.pi))
    )
    return ln_at_splice * (x / x_tail) ** (-(alpha + 1))


def base_distribution(stage):
    """Discretized base distribution for a stage ('seed' or 'series_b').
    Fitted parameters come from calibration.json; this function only
    evaluates them onto the grid and normalizes."""
    cal = _load_calibration()
    p = cal["stages"][stage]["fitted_params"]
    xs = _grid()
    ws = [_base_density(x, p["mu"], p["sigma"], p["x_tail"], p["alpha"]) * x
          for x in xs]  # *x: log-spaced grid Jacobian
    total = sum(ws)
    return xs, [w / total for w in ws]


def bucket_masses(xs, ps, edges):
    """Probability mass in [edges[i], edges[i+1]) buckets."""
    out = [0.0] * (len(edges) - 1)
    for x, p in zip(xs, ps):
        for i in range(len(edges) - 1):
            if edges[i] <= x < edges[i + 1]:
                out[i] += p
                break
    return out


def fit_check(stage, tol=0.015):
    """GATE: fitted base distribution must reproduce the published
    empirical bucket frequencies within tol (absolute mass per bucket).
    Returns (ok, details)."""
    cal = _load_calibration()
    target = cal["stages"][stage]["target_buckets"]  # {label: freq}
    edges = cal["bucket_edges"]
    xs, ps = base_distribution(stage)
    got = bucket_masses(xs, ps, edges)
    labels = list(target.keys())
    details = {}
    ok = True
    for lab, g in zip(labels, got):
        t = target[lab]
        details[lab] = {"target": t, "fitted": round(g, 4)}
        if abs(g - t) > tol:
            ok = False
    return ok, details


def truncation_mass(stage):
    """Audit gate: lognormal mass lying outside [GRID_LO, GRID_HI] that
    renormalization silently redistributes. Must stay < 0.5%."""
    cal = _load_calibration()
    p = cal["stages"][stage]["fitted_params"]
    def Phi(z):
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))
    below = Phi((math.log(GRID_LO) - p["mu"]) / p["sigma"])
    above = 1 - Phi((math.log(GRID_HI) - p["mu"]) / p["sigma"])
    return below + above


def tilt_to_forecasts(xs, ps, p_below_1x, p_ge_10x, iters=200):
    if not (0.0 < p_below_1x < 1.0 and 0.0 <= p_ge_10x < 1.0):
        raise ValueError("forecast probabilities out of range")
    if p_below_1x + p_ge_10x >= 1.0:
        raise ValueError("P(<1x) + P(>=10x) must be < 1")
    """KL-minimal exponential tilt: reweight ps with
    w(x) = exp(a*I[x<1] + b*I[x>=10]) choosing a, b so the tilted
    distribution matches the two logged constraints exactly.
    Solved by iterative proportional fitting (converges since the two
    indicator features are non-overlapping regions plus a free middle)."""
    in_lo = [x < 1.0 for x in xs]
    in_hi = [x >= 10.0 for x in xs]
    q = ps[:]
    for _ in range(iters):
        m_lo = sum(v for v, f in zip(q, in_lo) if f)
        s_lo = p_below_1x / m_lo if m_lo > 0 else 1.0
        r_lo = (1 - p_below_1x) / (1 - m_lo) if m_lo < 1 else 1.0
        q = [v * (s_lo if f else r_lo) for v, f in zip(q, in_lo)]
        m_hi = sum(v for v, f in zip(q, in_hi) if f)
        s_hi = p_ge_10x / m_hi if m_hi > 0 else 1.0
        r_hi = (1 - p_ge_10x) / (1 - m_hi) if m_hi < 1 else 1.0
        q = [v * (s_hi if f else r_hi) for v, f in zip(q, in_hi)]
        s = sum(q)
        q = [v / s for v in q]
    return q


def net_multiple(g, carry=0.20, sub1_drag=0.95):
    return 1 + (1 - carry) * (g - 1) if g > 1 else g * sub1_drag


def exceedance_curve(stage, p_below_1x, p_ge_10x, thresholds=(1, 2, 3, 5, 10, 20, 50, 100), carry=0.20):
    """The deliverable: P(gross >= X) and P(net >= X) for a deal."""
    xs, ps = base_distribution(stage)
    q = tilt_to_forecasts(xs, ps, p_below_1x, p_ge_10x)
    gross = {t: sum(p for x, p in zip(xs, q) if x >= t) for t in thresholds}
    net = {t: sum(p for x, p in zip(xs, q) if net_multiple(x, carry) >= t) for t in thresholds}
    ev_gross = sum(x * p for x, p in zip(xs, q))
    ev_net = sum(net_multiple(x, carry) * p for x, p in zip(xs, q))
    return {"gross_exceedance": gross, "net_exceedance": net,
            "ev_gross": ev_gross, "ev_net": ev_net}


if __name__ == "__main__":
    import sys
    stage = sys.argv[1] if len(sys.argv) > 1 else "seed"
    p1 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.60
    p10 = float(sys.argv[3]) if len(sys.argv) > 3 else 0.04
    ok, det = fit_check(stage)
    print(f"fit gate [{stage}]: {'PASS' if ok else 'FAIL'}")
    for k, v in det.items():
        print(f"  {k:8} target {v['target']:.3f}  fitted {v['fitted']:.3f}")
    out = exceedance_curve(stage, p1, p10)
    print(f"\nP(<1x)={p1} P(>=10x)={p10} tilt applied. EV gross {out['ev_gross']:.2f} net {out['ev_net']:.2f}")
    for t, p in out["gross_exceedance"].items():
        print(f"  P(gross >= {t:>3}x) = {p*100:6.2f}%   P(net >= {t}x) = {out['net_exceedance'][t]*100:6.2f}%")
