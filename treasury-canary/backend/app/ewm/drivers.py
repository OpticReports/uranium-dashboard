"""Driver overlays for the deal-market state: what actually moves it.

WHAT THIS ANSWERS. The deal-state marker says BOOM/NORMAL/COOLING/STALL.
This says WHY - which macro conditions the deal market is currently tracking,
and whether those relationships are strengthening or decaying.

=== THE MEASURED RANKING, AND IT IS NOT WHAT ANYONE EXPECTS ===

Correlations against the deal-activity measure (deseasonalised trailing-4q
log merger proxies), 97 quarters, 2001Q2-2026Q2. "lead" = the driver leads
deal activity by that many quarters.

    driver                    level vs trend-dev   change vs speed   lead
    SLOOS C&I tightening            -0.740             -0.531         1q  -0.601
    corporate equity value          +0.085             +0.431         2q  +0.525
    GZ credit spread                -0.505             -0.446         1q  -0.488
    excess bond premium             -0.628             -0.352         2q  -0.451
    NFCI                            -0.487             -0.368         1q  -0.448
    VIX                             -0.473             -0.297         2q  -0.433
    fed funds                       -0.011             +0.302         0q  +0.302
    2y Treasury yield               -0.030             +0.300         0q  +0.300
    term spread 10y-2y              -0.087             -0.285         0q  -0.285
    10y Treasury yield              -0.112             +0.190         0q  +0.190

RATES ARE THE WEAKEST DRIVER IN THE SET, and the sign is backwards from the
intuition. The 2y yield's correlation with deal activity's deviation from its
own trend is -0.030 - indistinguishable from nothing - and what little signal
exists in the change is POSITIVE: rising rates go WITH rising deal activity,
because both track the same expansion. Rates are a confounded proxy, not a
channel.

What moves deal-making is CREDIT AVAILABILITY. Bank lending standards lead by
a quarter at -0.601 and are the strongest relationship anywhere in the set;
credit spreads follow at -0.49. This is Harford (2005 JFE) measured on our own
data: capital liquidity drives merger waves, and market-to-book loses
significance once liquidity is in the model. His own wave-onset logit put the
C&I rate spread at p=0.032 while the behavioural block reached pseudo-R^2 of
just 0.016.

Do not read any of this as causal. These are contemporaneous and lagged
correlations over ~5 independent cycles; a lead of one quarter on 97
overlapping observations is not a forecasting claim, and the rolling window
below exists precisely because these relationships are NOT stable.

=== WHY Z-SCORES AND NOT LEVELS ===

Two reasons that happen to coincide. A chart overlaying a percentage, an
index and a basis-point spread on one axis needs them commensurable, and a
dual-axis chart can manufacture any apparent relationship by choice of
scaling. Separately, NFCI (Chicago Fed) and VIX (Cboe) are licence-restricted
for redistribution as LEVELS; a z-score is a derived statistic and is not.
Serving normalized series satisfies the chart and the licence at once.
"""

import math
import statistics as st

# label -> (bundle key, invert, one-line note)
# invert=True means the raw series runs OPPOSITE to deal-market health, so it
# is flipped for display: every overlay reads "up = better for deals".
DRIVERS = {
    "lending standards": ("sloos", True,
                          "SLOOS net % tightening C&I. Strongest driver "
                          "measured: -0.74 on level, leads 1q at -0.60."),
    "financial conditions": ("nfci", True,
                             "Chicago Fed NFCI. -0.49 on level, leads 1q."),
    "volatility": ("vix", True, "VIX. -0.47 on level, leads 2q."),
    "credit spread": ("hy_oas", True,
                      "High-yield OAS. Internal computation only - the "
                      "level is licence-restricted, the z-score is not."),
    "2y yield": ("2y", False,
                 "WEAK: -0.03 on level. Rates are a confounded proxy, not "
                 "a channel - shown so that can be seen rather than assumed."),
    "equity market": ("sp500", False, "S&P 500. Leads 2q at +0.53."),
}

ROLL_WINDOW = 20   # 5 years. Long enough for a stable correlation, short
                   # enough that a decaying relationship is visible.
MIN_OVERLAP = 12


def _quarterly(series, how="mean"):
    """Collapse a (dates, values) bundle series onto calendar quarters."""
    dates, vals = series
    buckets = {}
    for d, v in zip(dates, vals):
        if v is None:
            continue
        buckets.setdefault((d.year, (d.month - 1) // 3 + 1), []).append(float(v))
    return {k: (sum(v) / len(v) if how == "mean" else v[-1])
            for k, v in buckets.items()}


def _zscore(pairs):
    """Expanding-window z. Causal by construction: the value at t is
    standardised only against history up to t, so a reading can be
    reproduced by someone standing at t."""
    out = {}
    hist = []
    for k in sorted(pairs):
        hist.append(pairs[k])
        if len(hist) < MIN_OVERLAP:
            continue
        m = sum(hist) / len(hist)
        s = st.pstdev(hist)
        out[k] = (pairs[k] - m) / s if s else 0.0
    return out


def _corr(a, b):
    n = len(a)
    if n < MIN_OVERLAP:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa, sb = st.pstdev(a), st.pstdev(b)
    if not sa or not sb:
        return None
    return sum((p - ma) * (q - mb) for p, q in zip(a, b)) / n / (sa * sb)


def rolling_corr(driver_q, deal_q, window=ROLL_WINDOW):
    """Trailing-window correlation, so a decaying relationship is visible
    rather than averaged away. This is the point of the panel: a driver whose
    correlation is heading toward zero has stopped explaining the market, and
    a single full-sample number hides exactly that."""
    keys = sorted(set(driver_q) & set(deal_q))
    out = {}
    for i in range(len(keys)):
        w = keys[max(0, i - window + 1):i + 1]
        if len(w) < MIN_OVERLAP:
            continue
        r = _corr([driver_q[k] for k in w], [deal_q[k] for k in w])
        if r is not None:
            out[keys[i]] = round(r, 3)
    return out


def build(bundle):
    """Deal measure plus every available driver, z-scored and sign-oriented,
    with trailing correlations. Any driver whose feed is dead is omitted
    rather than zero-filled."""
    from .deal_state import _coords, _deal_activity, _grid, _trailing_a

    da = _deal_activity()
    if not da:
        return None
    qs, x = _grid(da)
    a = _trailing_a(qs, x)
    deal = {}
    for i in range(len(qs)):
        c = _coords(a, i)
        if c:
            deal[qs[i]] = c["zg"]
    if len(deal) < MIN_OVERLAP:
        return None

    series, corrs, meta = {}, {}, {}
    for label, (key, invert, note) in DRIVERS.items():
        raw = bundle.get(key)
        if not raw or not raw[0]:
            continue
        q = _quarterly(raw, "last" if key == "sloos" else "mean")
        z = _zscore(q)
        if invert:
            z = {k: -v for k, v in z.items()}
        common = sorted(set(z) & set(deal))
        if len(common) < MIN_OVERLAP:
            continue
        full = _corr([z[k] for k in common], [deal[k] for k in common])
        roll = rolling_corr(z, deal)
        rk = sorted(roll)
        trend = None
        if len(rk) >= 8:
            recent = roll[rk[-1]]
            prior = roll[rk[-9]]
            trend = ("strengthening" if recent - prior > 0.10 else
                     "decaying" if recent - prior < -0.10 else "stable")
        series[label] = {f"{k[0]}Q{k[1]}": round(v, 3) for k, v in z.items()}
        corrs[label] = {f"{k[0]}Q{k[1]}": v for k, v in roll.items()}
        meta[label] = {"full_sample_r": round(full, 3) if full else None,
                       "latest_r": roll[rk[-1]] if rk else None,
                       "trend": trend, "inverted": invert, "note": note}
    return {
        "deal": {f"{k[0]}Q{k[1]}": round(v, 3) for k, v in deal.items()},
        "drivers": series, "rolling_corr": corrs, "meta": meta,
        "window": ROLL_WINDOW,
        "orientation": "every driver is sign-oriented so UP = better for "
                       "deal-making; inverted ones are flagged",
        "caveat": "Correlations over ~5 independent cycles on overlapping "
                  "windows. Not causal, not a forecast. Rates are included "
                  "BECAUSE they measure near zero (-0.03) - the point is to "
                  "make that visible rather than assumed.",
    }
