"""HSR threshold-drift correction: making 1990s deal counts comparable.

THE PROBLEM. The HSR reporting threshold was $15M, set in 1978 and
never indexed. Across 1990-2000 it eroded from 2.516 to 1.463 parts-
per-million of nominal GDP - a 41.8% real decline over that window and
77.1% since 1978. Progressively smaller deals cleared a fixed bar, so
raw counts rose (1,952 in CY1990 to 4,810 in CY2000, 2.46x) for reasons
that are partly arithmetic rather than deal-making.

THE CORRECTION IS MEASURED, NOT MODELLED. For each year we ask: how
many transactions would have cleared a threshold with the SAME REAL
BITE as 1990's $15M? That equivalent threshold runs $15.00M (1990) to
$25.79M (2000), and - this is the point - every one of those values
lands INSIDE the published bracket table for its own year. So the
answer is read off the observed survival function by log-linear
interpolation within the containing bracket. No distributional family
is assumed, fitted, or required.

    factor_y = N_y(> v_y) / N_y(> 15)      v_y = the 1990-equivalent bar

WHY NOT A POWER LAW - a correction that was built, tested and REJECTED.
The first implementation fitted a Pareto exponent per year and restated
counts by (share_y/share_ref)^alpha. An adversarial review killed it,
correctly, on three grounds:

  1. THE FAMILY IS REJECTED BY THE DATA. Chi-square 51-140 on df=7 in
     all eleven years, p from 1e-8 to 4e-27, with structured residuals
     (a 15-30% mid-range excess and a 30-43% shortfall in the open
     >$1B bin) rather than noise. A lognormal beats it by AIC 40-134 in
     EVERY year and passes goodness-of-fit in 8 of 11.
  2. THE EXPONENT IS RANGE-DEPENDENT, so there is no single alpha to
     use. The local slope rises monotonically with deal size in every
     year - FY2000: 0.460 on [15,25] rising to 0.808 on [300,1000].
     A full-range fit returns 0.57-0.77, but the correction only ever
     traverses [$15M, $25.8M], where the true local value is 0.46-0.64.
     The fit was 0.11-0.17 too high in the only place it was used, and
     the gap is 3-5x the bootstrap CI width.
  3. IT THEREFORE OVERCORRECTED BY ABOUT HALF. Power law: creep
     explains 32.5% of the 1990s rise. Measured directly: 22.2%.

The power-law machinery is retained below as a REPORTED DIAGNOSTIC -
the exponent's drift is genuinely informative about distributional
change - but nothing in the shipped correction depends on it.

WHAT DOMINATES THE ANSWER, AND IT IS NOT THE EXPONENT. The deflator
choice moves the corrected 1990->2000 rise roughly NINE TIMES more than
the entire alpha confidence interval does:

    corporate-equity deflated   0.75x   (the 1990s becomes a DECLINE)
    nominal GDP  (shipped)      1.92x
    CPI                         2.02x
    whole alpha CI, for scale   1.59x - 1.82x

Nominal GDP is a judgement, not a measurement. It is the defensible
middle: equity values are endogenous to the M&A cycle being measured,
so deflating by them would erase the signal by construction, while CPI
understates the growth of transactable corporate assets. The range is
published in the honesty box because it, not alpha, is the load-bearing
assumption.

WHAT THIS STILL CANNOT FIX. Pub. L. 106-553 did not only raise the
threshold to $50M. It also abolished the size-of-person test above
$200M and the 15% size-of-transaction test. The DEFINITION of a
reportable transaction changed, so pre- and post-2001 counts are
different objects and nothing here licenses a cross-regime level
splice. Only within-regime ranks. No FTC report in any year quantifies
the size-of-person change; the agencies attribute the FY2001 drop to
the package "to a considerable extent" and never decompose it.

POPULATION CAVEAT, disclosed rather than smoothed. The bracket tables
total to ADJUSTED TRANSACTIONS (those in which a second request could
have been issued), while the monthly count series this correction is
applied to is TRANSACTIONS REPORTED. The two differ by roughly 14% in
FY1990. We apply a RATIO measured on the former to the latter, which
assumes the size distribution is similar across that gap. It is an
assumption, not a measurement.
"""

import math


def _neg_ll(alpha, edges, counts):
    """Negative log-likelihood of binned Pareto.

    edges[0] is the support floor; a None final edge means the top bin
    is open. With a CLOSED final edge the bin probabilities do not sum
    to 1 (they sum to 1 - (b_K/b_0)^-alpha), so the expression is not a
    likelihood and the MLE is wrong - measured at alpha 1.221 against a
    correct truncated MLE of 0.335 on [15,25,50,100]. Caught by an
    adversarial review as a latent defect: no shipped number used that
    path, but a restricted-range refit would have been silently wrong.
    We now NORMALIZE by the truncation mass rather than let it pass.
    """
    b0 = edges[0]
    top = edges[-1]
    norm = 1.0 if top is None else 1.0 - (top / b0) ** (-alpha)
    if norm <= 0:
        return float("inf")
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
        ll += n * math.log(p / norm)
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
    """NONPARAMETRIC bootstrap CI: resample bin counts multinomially at
    the OBSERVED proportions and refit. (An earlier docstring called
    this parametric; it is not - a parametric bootstrap would resample
    under the FITTED model, and given that the model is rejected it
    would give different, narrower, and more misleading intervals.)

    Reports estimator uncertainty at this sample size only. It says
    NOTHING about model uncertainty, which here is the dominant term:
    the Pareto family is rejected at p < 1e-8 in every year."""
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


# --------------------------------------------------------------------
# THE SHIPPED CORRECTION - measured, model-free
# --------------------------------------------------------------------

def survival_at(brackets, v):
    """N(> v) read off a year's published bracket table.

    `brackets` is [(lo, hi_or_None, count), ...]. Within the bracket
    containing v the survival is interpolated LOG-LINEARLY, which is
    the weakest assumption that respects the multiplicative scale these
    distributions live on - and the only assumption in the whole
    correction. No family, no fit.
    """
    bl = sorted(brackets)
    total = sum(c for _, _, c in bl)
    cum = 0.0
    for lo, hi, c in bl:
        if hi is None or v < hi:
            inside = 0.0
            if v > lo and hi:
                inside = c * math.log(v / lo) / math.log(hi / lo)
            return total - cum - inside
        cum += c
    return 0.0


def equivalent_threshold(reference_share_ppm, gdp_usd_b):
    """The nominal $M bar with the same real bite as the reference."""
    return reference_share_ppm * gdp_usd_b / 1000.0


def drift_factors(brackets_by_fy, gdp_by_year, threshold_usd_m,
                  reference_fy):
    """Per-year multiplicative correction for real threshold erosion.

    THE REFERENCE MUST BE THE EARLIEST YEAR, and that is not a
    stylistic choice. With a LATE reference every earlier year requires
    N(> something well below $15M) - an extrapolation BELOW the data,
    into a region whose only observations are the censored sub-$15M
    subsample (deals reportable solely under the abolished 15% test).
    With reference = 1990 the equivalent bars run $15.00M to $25.79M,
    every one of them inside its own year's published brackets, so the
    correction is interpolation throughout and never extrapolation.
    """
    ref_share = real_threshold_share(threshold_usd_m,
                                     gdp_by_year[reference_fy])
    out = {}
    for fy, brackets in brackets_by_fy.items():
        if fy not in gdp_by_year:
            continue
        v = equivalent_threshold(ref_share, gdp_by_year[fy])
        base = survival_at(brackets, threshold_usd_m)
        if base <= 0:
            continue
        out[fy] = survival_at(brackets, v) / base
    return out


def correct_measured(counts_by_fy, factors):
    """Apply the measured factors. Years without a factor are DROPPED,
    never carried through uncorrected - an uncorrected year silently
    mixed among corrected ones is the artifact this module exists to
    remove."""
    return {fy: n * factors[fy] for fy, n in counts_by_fy.items()
            if fy in factors}
