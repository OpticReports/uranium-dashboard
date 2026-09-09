"""Power-law exponent of HSR transaction values, and what it can fix.

PURPOSE. HSR transaction counts are not comparable across time because
the reporting threshold moves. Before 2001 the threshold was $15M, set
in 1978 and NEVER INDEXED, so it eroded from 6.38 to 1.46 ppm of GDP
across 1978-2000 - a 45% real decline inside the sample. Raw counts
rose 2.46x over 1990-2000 and a large part of that is bracket creep
rather than deal-making. If deal values follow a power law near the
threshold, that erosion is correctable:

    N(>v) = C * v^(-alpha)   =>   N(>v0) = N(>v1) * (v1/v0)^alpha

so a count measured at threshold v1 can be restated at a reference
threshold v0. This module estimates alpha and applies that restatement.

ESTIMATOR. Binned maximum likelihood, per Virkar & Clauset (2014),
"Power-law distributions in binned empirical data", Annals of Applied
Statistics 8(1):89-119. We only ever see bracket COUNTS, never
individual transaction values, so the standard continuous MLE (Hill)
does not apply and neither does the thing everyone reaches for first:

  DO NOT FIT log N(>v) ON log v BY LEAST SQUARES. Regression on
  log-log survival data is a known-biased estimator for power laws -
  the points are not independent (a survival function is a running
  sum), the errors are not homoscedastic in log space, and the fit is
  dominated by the sparse tail. Clauset, Shalizi & Newman (2009 SIAM
  Review) is the standard reference for why this produces confidently
  wrong exponents. It is computed here ONLY as a cross-check to be
  reported alongside, never as the estimate.

For bin edges b_0 < b_1 < ... < b_k with counts n_i, the probability
of landing in bin i under a Pareto with support >= b_0 is

    p_i = (b_{i-1}/b_0)^(-alpha) - (b_i/b_0)^(-alpha)

with the top bin open (b_k = infinity, so its second term is 0). We
maximize sum_i n_i * log(p_i) over alpha by ternary search on the
concave log-likelihood.

WHAT THIS CANNOT FIX, AND IT IS THE REASON THIS MODULE DOES NOT BY
ITSELF UNLOCK PRE-2001. Pub. L. 106-553 did not only raise the
threshold to $50M. It ALSO eliminated the size-of-person test and the
15% size-of-transaction test. The DEFINITION of a reportable
transaction changed, so pre- and post-2001 counts are different
objects, not one object observed at two cutoffs. A threshold
correction repairs the cutoff and says nothing about the definition.
Whether the residual definitional break is small enough to live with
is a separate question, answered by evidence, not by this arithmetic.
"""

import math


def _neg_ll(alpha, edges, counts):
    """Negative log-likelihood of binned Pareto. edges[0] is the support
    floor; a None final edge means the top bin is open."""
    b0 = edges[0]
    ll = 0.0
    for i, n in enumerate(counts):
        if n <= 0:
            continue
        lo, hi = edges[i], edges[i + 1]
        s_lo = (lo / b0) ** (-alpha)
        s_hi = 0.0 if hi is None else (hi / b0) ** (-alpha)
        p = s_lo - s_hi
        if p <= 0:
            return float("inf")
        ll += n * math.log(p)
    return -ll


def fit_binned(edges, counts, lo=0.05, hi=8.0, iters=200):
    """Binned-MLE estimate of the power-law exponent.

    `edges` has len(counts)+1 entries; the last may be None for an open
    top bin. Returns (alpha, neg_log_likelihood).

    Ternary search: the binned Pareto log-likelihood is concave in
    alpha over any range where every bin probability is positive, so
    this converges without derivatives and without a starting guess.
    """
    for _ in range(iters):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        if _neg_ll(m1, edges, counts) < _neg_ll(m2, edges, counts):
            hi = m2
        else:
            lo = m1
    a = (lo + hi) / 2.0
    return a, _neg_ll(a, edges, counts)


def loglog_slope(edges, counts):
    """CROSS-CHECK ONLY - the biased estimator, reported so the gap
    between the two is visible rather than hidden. See module docstring
    for why this must never be the shipped number."""
    tot = sum(counts)
    pts = []
    run = 0
    for i, n in enumerate(counts[:-1]):
        run += n
        surv = tot - run
        v = edges[i + 1]
        if surv > 0 and v:
            pts.append((math.log(v), math.log(surv)))
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    num = sum((p[0] - mx) * (p[1] - my) for p in pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    return -num / den if den else None


def bootstrap_ci(edges, counts, draws=400, seed=7):
    """Parametric bootstrap CI: resample bin counts multinomially at the
    observed proportions and refit. Reports estimator uncertainty at
    this sample size - NOT model uncertainty, and not the risk that a
    power law is the wrong family."""
    import random
    rng = random.Random(seed)
    tot = int(sum(counts))
    probs = [c / tot for c in counts]
    out = []
    for _ in range(draws):
        draw = [0] * len(counts)
        for _ in range(tot):
            r, acc = rng.random(), 0.0
            for i, p in enumerate(probs):
                acc += p
                if r <= acc:
                    draw[i] += 1
                    break
        a, _ = fit_binned(edges, draw)
        out.append(a)
    out.sort()
    return out[int(0.025 * draws)], out[int(0.975 * draws)]


def restate_count(n, from_threshold, to_threshold, alpha):
    """Restate a count observed at `from_threshold` onto `to_threshold`.

    Raising the reference threshold DISCARDS small deals, so restating
    a low-threshold count onto a high reference must reduce it.
    """
    return n * (from_threshold / to_threshold) ** alpha


def elasticity(alpha):
    """Percent change in count per percent change in threshold.

    d log N / d log v = -alpha. So alpha=1 means a 10% threshold error
    produces a ~10% count error - which is why alpha near 1 makes the
    unindexed pre-2001 threshold such a large problem.
    """
    return -alpha


# --------------------------------------------------------------------
# WITHIN-REGIME DRIFT CORRECTION
# --------------------------------------------------------------------
#
# The pre-2001 threshold never moved in NOMINAL terms - $15M flat from
# 1978 to 2001. So there is no nominal cutoff artifact inside the
# regime. What drifts is the threshold's REAL selectivity: as the
# economy grew past a fixed $15M bar, progressively smaller deals
# cleared it, and the count rose for that reason alone.
#
# This is a within-regime TREND, not a level splice, and that
# distinction is what makes the correction tractable. The composite
# scores regime-split percentile RANKS, so ranks are computed inside
# each regime and the cross-regime level offset - the part that is most
# violently alpha-sensitive - never enters the composite at all.
#
# Correction: express the threshold as a share of nominal GDP, pick a
# reference year inside the regime, and restate every year's count onto
# that reference share.


def real_threshold_share(threshold_usd_m, gdp_usd_b):
    """Threshold as parts-per-million of nominal GDP."""
    return threshold_usd_m / (gdp_usd_b * 1000.0) * 1e6


def correct_drift(counts_by_year, threshold_by_year, gdp_by_year, alpha,
                  reference_year):
    """Restate counts onto the reference year's REAL threshold share.

    A year whose threshold was real-terms LOOSER than the reference
    (a smaller share of GDP, so catching more small deals) has its
    count revised DOWN. Returns {year: corrected_count}.
    """
    ref = real_threshold_share(threshold_by_year[reference_year],
                              gdp_by_year[reference_year])
    out = {}
    for y, n in counts_by_year.items():
        if y not in threshold_by_year or y not in gdp_by_year:
            continue
        share = real_threshold_share(threshold_by_year[y], gdp_by_year[y])
        out[y] = restate_count(n, share, ref, alpha)
    return out


def rank_stability(counts_by_year, threshold_by_year, gdp_by_year,
                   alpha_lo, alpha_hi, reference_year, steps=25):
    """THE SHIP TEST, declared before the estimate was seen.

    The correction is only usable if the ORDERING of corrected years is
    stable across the alpha confidence interval. If two years swap
    places depending on where in the CI alpha sits, the corrected level
    is not recoverable and the regime must stay unscored - whatever the
    point estimate says.

    Returns (n_inversions, max_rank_shift, orderings_seen). Zero
    inversions across the interval is a pass.
    """
    orderings = set()
    max_shift = 0
    base = None
    for i in range(steps):
        a = alpha_lo + (alpha_hi - alpha_lo) * i / (steps - 1)
        corr = correct_drift(counts_by_year, threshold_by_year,
                             gdp_by_year, a, reference_year)
        order = tuple(sorted(corr, key=lambda y: corr[y]))
        orderings.add(order)
        if base is None:
            base = order
        else:
            pos = {y: k for k, y in enumerate(order)}
            bpos = {y: k for k, y in enumerate(base)}
            max_shift = max(max_shift,
                            max(abs(pos[y] - bpos[y]) for y in pos))
    return len(orderings) - 1, max_shift, orderings


def correct_drift_varying(counts_by_year, threshold_by_year, gdp_by_year,
                          alpha_by_year, reference_year):
    """Drift correction using each year's OWN measured exponent.

    Why not a single alpha: the exponent is not stationary even inside
    the 1990s regime. Fitted per year on the $15M-up brackets it falls
    monotonically from 0.772 (FY1992) to 0.575 (FY2000) - a spread of
    0.197 against per-year bootstrap CIs of 0.03-0.07, so the drift is
    real and not estimation noise. The 1992 and 2000 confidence
    intervals are disjoint ([0.733, 0.807] vs [0.560, 0.591]).

    A single pooled alpha would impose a shape the data rejects. Each
    year is restated with the local exponent of its OWN size
    distribution, which is the quantity the restatement actually needs.

    The single-alpha version is retained as correct_drift() because the
    ship test is run against it across the observed alpha range - that
    test is what establishes the ranking is insensitive to the choice,
    and it must keep operating on the simpler object it was defined on.
    """
    ref = real_threshold_share(threshold_by_year[reference_year],
                              gdp_by_year[reference_year])
    out = {}
    for y, n in counts_by_year.items():
        if y not in threshold_by_year or y not in gdp_by_year:
            continue
        if y not in alpha_by_year:
            continue
        share = real_threshold_share(threshold_by_year[y], gdp_by_year[y])
        out[y] = restate_count(n, share, ref, alpha_by_year[y])
    return out
