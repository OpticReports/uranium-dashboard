"""M&A cycle-phase indicator — a DESCRIPTIVE state variable.

WHAT THIS IS. A reading of where the M&A market is now: early, mid,
late, bust, or transitional. It is built the way the Chicago Fed builds
the NFCI and describes itself the same way — the NFCI FAQ says the
indexes "describe contemporary financial conditions," and its
forecasting claims are made and evidenced SEPARATELY. We copy that
posture exactly.

WHAT THIS IS NOT. A forecast. Not of recessions, not of deal volume,
not of exit windows. The question "so will deals fall next year?" gets
a separately-registered, separately-scored forecast or it gets nothing.

WHY NOT A FORECAST (the binding constraint). There are at most 4-5
aggregate US merger waves since 1980. A four-phase classifier over ~5
independent episodes has roughly ONE independent observation per phase
per cycle. Nothing can be cross-validated at that N. Harford (2005 JFE)
escapes it by moving to an industry-year panel (48 industries x 20
years = 960 obs, 35 waves) and even there wave-onset prediction tops
out at pseudo-R^2 0.154 / predicted-actual correlation 0.248. That is
the realistic ceiling for prediction, and it is low. Gaertner &
Halbheer (2009 IJIO) go further: under a Markov regime-switching model
estimated by Gibbs sampling, the canonical 1980s US merger wave is NOT
statistically significant. If wave EXISTENCE is fragile to method,
wave PHASE is more fragile still.

DESIGN RULE — ZERO FITTED PARAMETERS. Every constant in this module is
either published precedent or a prior declared before seeing results:

  * expanding-window percentile rank    (level; distribution-free)
  * Hamilton (2018) difference form     (momentum; h = 5y for credit-
                                         length cycles, his own
                                         recommendation)
  * Conference Board diffusion rule     (breadth; 0.05% dead band)
  * OECD 60% component-availability rule
  * NEUTRAL_BAND = 0.15                 (ARBITRARY, declared, and
                                         sensitivity-tested at 0.10 /
                                         0.20 by the gate tests)

Nothing here was chosen by looking at how the indicator performs on
history. That property is the entire defence of this construction and
it is destroyed the first time anyone tunes a constant to make a past
wave look better. If you are tempted: don't. Add a component or change
the prior, and say so in the commit.

WHY NOT HP / KALMAN / TWO-SIDED ANYTHING. Orphanides & van Norden
(2002 REStat) showed the damage in real-time cycle estimates comes from
the TREND BEING REDRAWN as the sample grows, not from data revisions.
Their real-time vs revised correlations run as low as 0.729 (HP) while
real-time vs quasi-real-time stays above 0.92 — i.e. clean, never-
revised data does not save you. Our inputs (deal counts, filing counts)
barely revise, which makes this trap easy to walk into. Hamilton (2018
REStat) on the HP end-point artifact: "that picture is just something
that their imagination has imposed on the data."

Hamilton's own footnote 16 concedes his FITTED regression filter still
uses future data through the OLS coefficients — the influence only
vanishes asymptotically. At ~5 cycles we are nowhere near asymptopia,
so we use his parameter-free DIFFERENCE form, which has zero look-ahead
at ANY sample size.

HARD INVARIANT: no statistic here may touch data dated after the
reading it produces. That includes means, standard deviations,
percentile breakpoints and thresholds — not just the filter. This is
where composite indicators leak most often. Gate-tested.
"""

# --- Declared priors. Change these only with a documented reason. ---

# Hamilton (2018) sec 4.3 recommends h = 5 YEARS for credit/debt-cycle
# work (vs h = 8 quarters for business cycles). Merger waves are credit
# cycles - Harford (2005): the C&I rate spread leads market-to-book at
# lag correlation -0.38 while the reverse is insignificant (-0.03).
MOMENTUM_H_QUARTERS = 20  # 5 years

# OECD CLI: compute a composite for a period only if >=60% of component
# series are available. Prevents a thin month masquerading as a reading.
MIN_COMPONENT_COVERAGE = 0.60

# Conference Board diffusion dead band: a component moving less than
# this counts as 0.5 (unchanged) rather than up or down.
DIFFUSION_DEAD_BAND = 0.0005  # 0.05%

# Below this, the phase label is not meaningful and we say so rather
# than forcing a call. ARBITRARY - declared, not fitted. Sensitivity at
# 0.10 and 0.20 is published by the gate tests.
NEUTRAL_BAND = 0.15

# Diffusion breadth qualifiers - Conference Board convention.
BREADTH_BROAD = 70.0
BREADTH_NARROW_LO, BREADTH_NARROW_HI = 45.0, 55.0


def percentile_rank_expanding(series, i):
    """Percentile rank of series[i] within series[:i+1] ONLY, rescaled
    to [-1, +1].

    Expanding window, never full-sample: the reading at time i must be
    reproducible by someone standing at time i. Rank rather than
    z-score because our inputs are fat-tailed and carry level shifts
    (the OECD reaches the same conclusion in weaker form by using mean
    absolute deviation rather than standard deviation).

    Ties share the midrank, so a flat series reads 0.0 rather than
    drifting with the tie-break order.
    """
    window = [v for v in series[:i + 1] if v is not None]
    x = series[i]
    if x is None or len(window) < 2:
        return None
    below = sum(1 for v in window if v < x)
    equal = sum(1 for v in window if v == x)
    # midrank for ties, normalized to [0, 1]
    p = (below + 0.5 * equal) / len(window)
    return 2.0 * p - 1.0


def hamilton_difference(series, i, h=MOMENTUM_H_QUARTERS):
    """Hamilton (2018) parameter-free cyclical component: y_t - y_{t-h}.

    This is his equation (22), the random-walk special case toward
    which the fitted regression converges. He flags it explicitly as
    the variant that "allows zero inference of future observations for
    any sample size T" - which is why it, and not the regression, is
    what we ship. Returns None until h observations of history exist;
    we do not backfill, pad, or seed.
    """
    j = i - h
    if j < 0:
        return None
    a, b = series[i], series[j]
    if a is None or b is None:
        return None
    return a - b


def percentile_rank_within_regime(series, i, regime_starts):
    """Expanding percentile rank restricted to the CURRENT regime.

    Why this exists: the HSR size-of-transaction reporting threshold
    moved $15M -> $50M effective 2001-02-01 and has been indexed
    annually since 2005. Raw transaction counts are therefore NOT
    comparable across that seam - the 2000->2001 collapse in reported
    transactions is a definitional change, not a deal cycle. Ranking a
    2003 count against the 1990s distribution would read every
    post-2001 month as a historic collapse.

    Scoring within regime keeps the 1990s wave usable as an analog
    without pretending the levels are comparable. The cost is a
    documented seam and a shorter effective window at the start of each
    regime - which is exactly why `min_obs` refuses to emit a reading
    until the regime has enough history to rank against.

    `regime_starts` is a sorted list of indices at which a new regime
    begins (index 0 is implicit).
    """
    start = 0
    for s in regime_starts:
        if s <= i:
            start = s
        else:
            break
    window = [v for v in series[start:i + 1] if v is not None]
    x = series[i]
    if x is None or len(window) < 2:
        return None
    below = sum(1 for v in window if v < x)
    equal = sum(1 for v in window if v == x)
    return 2.0 * ((below + 0.5 * equal) / len(window)) - 1.0


def diffusion(components, i, lookback=4):
    """Conference Board diffusion rule: share of components rising.

    rises  -> 1.0    flat (within the dead band) -> 0.5    falls -> 0.0
    Averaged and scaled to 0-100.

    This is the single most useful thing a multi-component indicator
    publishes, and averaging destroys it. A composite at -1.5 driven by
    six components is a different world from one driven by credit
    spreads alone. It is also the specific instrument for the failure
    that embarrassed the Conference Board's own LEI, which called
    recession for 21 consecutive months (Jun 2022 - Feb 2024) while GDP
    grew 2.9% annualized: a narrow, goods-concentrated decline reading
    as a broad cycle turn. Published ALONGSIDE the phase, never folded
    into it.

    `components` is a list of series, each already sign-oriented so
    that HIGHER = LATER in the cycle.
    """
    scores = []
    for s in components:
        j = i - lookback
        if j < 0 or s[i] is None or s[j] is None:
            continue
        base = abs(s[j]) if s[j] else 1.0
        change = (s[i] - s[j]) / base if base else 0.0
        if change > DIFFUSION_DEAD_BAND:
            scores.append(1.0)
        elif change < -DIFFUSION_DEAD_BAND:
            scores.append(0.0)
        else:
            scores.append(0.5)
    if not scores:
        return None
    return 100.0 * sum(scores) / len(scores)


def composite(level_scores, momentum_scores):
    """Equal-weight average of available component scores.

    EQUAL WEIGHT IS A DELIBERATE REFUSAL, not laziness. The two
    alternatives both fail at our N:

      * PCA / dynamic factor (the NFCI's method) re-estimates the whole
        history every period and needs T >> N. The NFCI can afford it
        with 105 series; we cannot with 6.
      * Inverse-volatility (the Conference Board LEI's method) hands
        the LARGEST weights to the LEAST volatile components. That is
        not neutral - it is a bet that low-variance components carry
        the signal, and it is the mechanism behind the LEI's 21-month
        false recession call. We have no sample with which to test that
        bet, so we decline to make it.

    Returns (score, coverage) or (None, coverage) when coverage fails
    the OECD 60% rule.
    """
    present = [v for v in level_scores if v is not None]
    coverage = len(present) / len(level_scores) if level_scores else 0.0
    if coverage < MIN_COMPONENT_COVERAGE or not present:
        return None, coverage
    return sum(present) / len(present), coverage


def classify_phase(level, momentum, neutral_band=NEUTRAL_BAND):
    """Quadrant clock on (level, momentum) with an explicit neutral zone.

    The four-phase vocabulary (early / mid / late / bust) is the
    industry standard - the OECD and Eurostat business-cycle clocks and
    Fidelity's business-cycle roadmap all use it - so the labels land
    without explanation. The AXES here are ours and are parameter-free:
    expanding percentile rank for level, Hamilton difference for
    momentum.

        level < 0, momentum > 0  ->  EARLY    (below trend, rising)
        level > 0, momentum > 0  ->  MID      (above trend, rising)
        level > 0, momentum < 0  ->  LATE     (above trend, falling)
        level < 0, momentum < 0  ->  BUST     (below trend, falling)

    Near the origin the assignment is unstable and the label would
    flicker between readings. We publish TRANSITIONAL rather than force
    a call. Anyone who wants the forced label can read the raw
    coordinates, which are returned alongside.
    """
    if level is None or momentum is None:
        return None
    if abs(level) < neutral_band or abs(momentum) < neutral_band:
        return "transitional"
    if momentum > 0:
        return "mid" if level > 0 else "early"
    return "late" if level > 0 else "bust"


def breadth_qualifier(diffusion_value):
    """Turn the diffusion index into a plain-language confidence note.

    This is a BREADTH statement, not a fitted confidence interval. It
    says how many components agree, nothing about how right they are.
    """
    if diffusion_value is None:
        return None
    if diffusion_value >= BREADTH_BROAD or diffusion_value <= (100 - BREADTH_BROAD):
        return "broad"
    if BREADTH_NARROW_LO <= diffusion_value <= BREADTH_NARROW_HI:
        return "narrow"
    return "mixed"


# --------------------------------------------------------------------
# LINK TO THE EXIT CALCULATOR
# --------------------------------------------------------------------
#
# The obvious move is to let the cycle phase tilt exit_curve.py's
# multiple distribution. WE DELIBERATELY DO NOT DO THAT, for two
# reasons, and the refusal is the most important design decision here.
#
# 1. THE CURVE'S INPUTS ARE ALREADY PINNED TO MEASURED THINGS. Its base
#    is PitchBook's measured stage MOIC buckets; its tilt is pinned by
#    minimum-KL update to the panel's OWN logged, Brier-scored
#    forecasts. Both are auditable and both get scored by the ledger.
#    Multiplying that by a cycle factor would silently overwrite a
#    measured base rate with a state reading that has never been scored
#    against anything, and would make the panel's forecasts
#    unfalsifiable - you could no longer tell a bad forecast from a bad
#    cycle adjustment.
#
# 2. THE HORIZONS DO NOT OVERLAP. A seed position underwritten today
#    resolves its multiple in the 2030s. Today's M&A phase says nothing
#    about the exit window a decade out - and there is no evidence
#    anywhere in the literature that it does. Applying a 2026 reading
#    to a 2033 exit would be the single most dishonest thing this
#    module could do.
#
# What the cycle reading legitimately bears on is REALIZATION, not
# multiple - whether a position resolves AT ALL, and when. That is a
# live question here: the measured PitchBook Part IV funnel (n=31,642
# US companies, first VC round 2009-2018) puts only 25.5% of companies
# at a liquidity event, against 31.1% dead and 39.6% in LIMBO - never
# raised again, no outcome. Limbo is the largest terminal state, and
# limbo is exactly what a shut M&A window produces. Exit share peaks
# around round 3 and then FALLS: later survivors are disproportionately
# unresolved, not resolved well.
#
# So the link is a DISCLOSURE, not a multiplier. We report which ledger
# positions are actually exposed to the current reading and which are
# not, and we let the reader do the rest.

# How far out a state reading can speak to. Declared prior, not fitted:
# the reading describes conditions NOW, and the shortest published
# forecast horizon anyone claims for a financial-conditions composite
# is the NFCI's 2-4 quarters (Brave & Butters 2011) - and that is a
# GDP claim, evidenced separately from the index itself. We take 2
# years as the outer bound of "exposed" and refuse to interpolate a
# decay curve we cannot evidence.
EXPOSURE_HORIZON_YEARS = 2.0


def exit_exposure(months_to_expected_exit):
    """Is a position's exit exposed to the CURRENT cycle reading?

    Three states, deliberately coarse - a continuous "relevance weight"
    would be a fitted parameter dressed up as precision, and there is
    no evidence base for its shape.

      exposed      - exit expected inside the horizon the reading can
                     speak to. The phase is decision-relevant now.
      unexposed    - exit expected beyond it. The current phase is NOT
                     information about this position, and saying
                     otherwise would be false precision.
      unknown      - no expected exit date logged.

    Note what this does NOT do: it never touches the position's
    probabilities. A position can be 'exposed' and its exit odds still
    come entirely from the measured base rates and the panel's logged
    forecasts. Exposure governs what the reading is ALLOWED to comment
    on, nothing more.
    """
    if months_to_expected_exit is None:
        return "unknown"
    return ("exposed" if months_to_expected_exit <= EXPOSURE_HORIZON_YEARS * 12
            else "unexposed")


def reading(level_scores, momentum_scores, components, i,
            neutral_band=NEUTRAL_BAND):
    """The full published reading for period i.

    Returns every number a reader needs to check the call, including
    the ones that undercut it: coverage, breadth, and the raw
    coordinates behind the phase label.
    """
    level, coverage = composite(level_scores, momentum_scores)
    momentum, _ = composite(momentum_scores, momentum_scores)
    diff = diffusion(components, i)
    return {
        "phase": classify_phase(level, momentum, neutral_band),
        "level": level,
        "momentum": momentum,
        "diffusion": diff,
        "breadth": breadth_qualifier(diff),
        "coverage": coverage,
        "neutral_band": neutral_band,
        "is_forecast": False,  # structural. see module docstring.
    }
