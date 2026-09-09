"""Data layer for the M&A cycle indicator: fetch, align, orient.

NO ANALYSIS HERE. This module fetches public series, aligns them to a
common quarterly grid, and applies sign orientation. Everything that
turns numbers into a reading lives in ma_cycle.py, so the two can be
audited separately.

QUARTERLY IS THE PUBLICATION FREQUENCY, and that is a deliberate
downgrade. Several inputs (SLOOS, the Z.1 flow-of-funds series) are
quarterly at source. Interpolating them up to monthly would manufacture
precision the data does not have and would make the composite look
smoother and more decisive than its slowest input justifies. If a
monthly read is ever wanted, publish the monthly COMPONENTS separately
- do not synthesize a monthly composite.

SIGN ORIENTATION. Every series is oriented so that HIGHER = LATER IN
THE CYCLE, so the composite has one direction. Four of the six are
inverted, and the inversions are the least obvious part of this file -
each carries its reasoning inline. Gate-tested against a stated
expectation so a silent sign flip cannot pass review.

LICENSE TIERS (binding, not advisory; verified 2026-09-09 against the
FRED series pages themselves):

  TIER 1 - PUBLIC DOMAIN. Publish values, charts, CSV exports freely;
    cite the source.
      FTC/DOJ HSR annual reports          (US Gov work)
      Fed Board GZ spread + EBP           (US Gov work, 1973-)
      SEC EDGAR form.idx / full-text      (US Gov work)
      FRED "Public Domain: Citation Requested" - e.g. DRTSCILM, and
        the Z.1 flow-of-funds series used here

  TIER 2 - COPYRIGHTED: CITATION REQUIRED. Internal computation only;
    publish at most a derived z-score or phase label, never the level
    series and never a CSV export.
      NFCI and its subindexes (Chicago Fed), VIXCLS (Cboe),
      BAA10Y, AAA10Y, T10Y2Y

  TIER 3 - PRE-APPROVAL REQUIRED. Never published, never exported,
    never charted.
      BAMLH0A0HYM2, BAMLC0A0CM and every ICE BofA OAS series:
      "Reproduction of this data in any form is prohibited except with
      the prior written permission of ICE Data Indices."

CREDIT COMPONENT - WHY GZ AND NOT THE OBVIOUS CHOICES. ICE HY OAS is
Tier 3 AND capped at a ~3-year rolling window without a key, so it
cannot carry a cycle indicator regardless. BAA10Y was the first
substitute considered and was WRONG: it is Tier 2, not public domain -
its FRED notes carry Moody's "may not be copied ... redistributed or
resold ... without Moody's prior written consent" - and on the only
window testable keylessly it tracks HY OAS at just r=+0.54 in levels.
The Gilchrist-Zakrajsek spread is a strict upgrade on both axes:
public domain, monthly from 1973-01 (thirteen years longer than
BAA10Y, twenty-three longer than ICE), and r=+0.937 with HY OAS in
levels.

We take the GZ SPREAD rather than its Excess Bond Premium companion,
though both ship in the same file. EBP is the better-known froth
measure, but it is a MODEL RESIDUAL - the part of the spread left
after the Fed's own expected-default model. Consuming it would import
that model's assumptions into an indicator whose entire defence is
that it has no fitted parameters. The raw spread is the direct
analogue of Harford's C&I rate spread and carries no such dependency.
EBP is cached alongside as a counter-check, and is not scored.
"""

import csv
import json
import os
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_HERE, "ma_cycle_cache")

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1970-01-01"

# Each entry: series id -> (label, aggregation, invert, why the sign)
# Fed Board, monthly, 1973-01 onward. US Government work.
EBP_CSV = "https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv"

SERIES = {
    "DRTSCILM": (
        "SLOOS: net % of banks tightening C&I standards", "last", True,
        "INVERTED. Same logic one step closer to the source: Harford "
        "used the C&I rate spread precisely because the SLOOS was "
        "suspended 1984-1990. Loose standards (a negative net %) are "
        "late-cycle, so easing must score high."),
    "DRSDCILM": (
        "SLOOS: net % reporting stronger C&I loan demand", "last", False,
        "NOT inverted. Strong borrower demand is itself late-cycle "
        "appetite. Paired with DRTSCILM deliberately: supply and demand "
        "answer different questions and can diverge, which is exactly "
        "the kind of disagreement the diffusion index is there to "
        "surface rather than average away."),
    "NFCI": (
        "Chicago Fed National Financial Conditions Index", "mean", True,
        "INVERTED. NFCI is signed so POSITIVE = tighter than average. "
        "Loose conditions are late-cycle, so we flip it. Note this is a "
        "coincident financial-conditions read, not a leading one - the "
        "Chicago Fed says so itself."),
    "NCBEILQ027S": (
        "Nonfinancial corporate equities, market value", "last", False,
        "Numerator of equity Q only; never scored on its own."),
    "TNWMVBSNNCB": (
        "Nonfinancial corporate net worth, market value", "last", False,
        "Denominator of equity Q only; never scored on its own."),
    "NCBCEBQ027S": (
        "Nonfinancial corporate net equity issuance (Z.1 F.103)", "last", True,
        "INVERTED. This goes deeply NEGATIVE when corporates retire "
        "equity - which is what cash M&A and buybacks do. A large "
        "negative issuance IS the wave signature, so it must score "
        "high. Rhodes-Kropf/Robinson/Viswanathan (2005) put ~40% of "
        "total dollar volume inside waves, with up to 65% of wave "
        "activity from the most-overvalued bidder quintile."),
}

# HSR transaction counts are NOT comparable across 2001-02-01: Pub. L.
# 106-553 raised the size-of-transaction threshold $15M -> $50M AND
# eliminated the size-of-person test and the 15% test, so the very
# DEFINITION of a reportable transaction changed. Regime boundary, not
# a data glitch.
HSR_REGIME_BREAK = "2001Q1"

# HSR only SCORES from here. The pre-2001 level is unusable as cycle
# amplitude and this is the audit's sharpest finding: the $15M
# threshold was set in 1978 and never indexed, so as a share of GDP it
# eroded 6.38 ppm (1978) -> 2.66 (1989) -> 1.46 (2000), a 45% real
# decline INSIDE our window. Raw counts rose 2.46x over 1990-2000 and
# roughly 1.8x of that is bracket creep. The 1990s "merger boom" in the
# raw series is substantially threshold erosion.
#
# We therefore do NOT deflate it - deflating needs the Pareto exponent
# of deal values near the threshold, which is not measured (open P1).
# Assuming alpha=1 to manufacture a corrected 1990s level would be a
# fitted parameter smuggled in as a fix. Pre-2001 HSR is CHARTED and
# NOT SCORED; the other five components carry the 1990s, which still
# clears the 60% coverage rule.
# HSR now scores from 1994Q1, not 2001Q2. The 1990s threshold-erosion
# artifact is CORRECTED (see ma_hsr_threshold) rather than avoided:
# raw counts rose 2.18x over FY1990-2000 and 22.0% of that is bracket
# creep, leaving a real 1.70x rise. 1990-1993 remain unscored - not
# because of the correction but because the expanding percentile window
# is degenerate there (MIN_RANK_WINDOW = 16 quarters).
#
# The correction was BUILT TWICE. The first version fitted a Pareto
# exponent per year; adversarial review rejected the family outright
# (chi-square p < 1e-8 in all 11 years, lognormal preferred by AIC
# 40-134) and showed the full-range exponent was measured in the wrong
# place - the correction only traverses $15-25.8M, where the local
# slope is 0.46-0.64, not the fitted 0.57-0.77. It overcorrected by
# about half. The shipped correction is model-free: read N(>v) straight
# off each year's published bracket table by log-linear interpolation.
HSR_SCORE_FROM = "1994Q1"

# Pre-2001 quarterly HSR counts are multiplied by their fiscal year's
# measured drift factor before scoring. Post-2001 is left alone: the
# threshold has been GNP-indexed since FY2005 and its share of GDP is
# flat to within about +/-11%, so there is no comparable artifact to
# remove and inventing one would add noise.
HSR_DRIFT_FACTORS_FY = {
    1990: 1.000, 1991: 0.983, 1992: 0.951, 1993: 0.926, 1994: 0.903,
    1995: 0.882, 1996: 0.867, 1997: 0.847, 1998: 0.812, 1999: 0.795,
    2000: 0.780,
}
HSR_DRIFT_REFERENCE_FY = 1990
HSR_DRIFT_DEFLATOR = "nominal GDP (FRED GDPA)"

# THE TRANSITION QUARTERS ARE DROPPED, NOT SCORED. Pub. L. 106-553 took
# effect 2001-02-01, mid-quarter, so 2001Q1 is one month of the old
# regime and two of the new. FY2001 as a whole is blended - its own
# Table V splits it into 1,317 filings under old-regime thresholds and
# 920 under new. It is neither a pre- nor a post-break observation and
# the FTC's tables say so.
#
# 2000Q4 goes too, for a separate and less obvious reason: it falls in
# FISCAL 2001, which has no measured drift factor (the regime changed
# inside it), so it would be the one old-regime quarter carried through
# UNCORRECTED while every neighbour was corrected - a step artifact
# manufactured by the fix itself. Ending the corrected regime at 2000Q3
# keeps every corrected quarter wholly inside a fiscal year with a
# measured factor, and requires no extrapolation.
HSR_EXCLUDE_QUARTERS = {"2000Q4", "2001Q1"}

# EDGAR only SCORES from here. Electronic filing became mandatory in
# May 1996; before that a filing count measures EDGAR ADOPTION, not
# deal activity - DEFM14A per quarter runs 8 (1994Q1) -> 27 (1996Q1)
# -> 92 (2000Q1). Ingested from 1994 anyway so the ramp is visible on
# the chart and the cutoff is arguable from the data.
EDGAR_SCORE_FROM = "1997Q1"

# Derived, not fetched.
DERIVED = {
    "GZ_SPREAD": (
        "Gilchrist-Zakrajsek credit spread (Fed Board)", True,
        "INVERTED. Harford (2005 JFE): a FALLING credit spread precedes "
        "a merger wave and a RISING spread signals its end - the spread "
        "leads market-to-book at lag correlation -0.38 while the reverse "
        "is insignificant (-0.03). Cheap credit is late-cycle, so a "
        "tight spread must score high. Harford's own variable was the "
        "C&I rate spread over Fed Funds; GZ is its modern analogue and "
        "reaches back to 1973."),
    "EDGAR_PROXIES": (
        "Merger proxies filed (DEFM14A + PREM14A), quarterly (SEC)",
        False,
        "NOT inverted. High merger-proxy volume is late-cycle activity. "
        "THIS IS THE NOWCAST LAYER: HSR is the official count but runs "
        "a ~10-month publication lag, while EDGAR's form index is "
        "current to yesterday. Counts DISTINCT ACCESSIONS, not index "
        "rows - form.idx emits one row per filer, and counting rows "
        "inflates S-4 by up to 8.7x. DEFM14A/PREM14A are the only two "
        "forms that are 1:1 with filings. See ma_edgar."),
    "HSR_COUNT": (
        "HSR reportable transactions, quarterly (FTC/DOJ)", False,
        "NOT inverted. High deal count is late-cycle activity. Note the "
        "literature does NOT support treating count as a LEADING series "
        "- at annual frequency count and value are contemporaneous at "
        "r=+0.88 and neither leads the other. It enters as a coincident "
        "activity level, which is all the evidence supports."),
    "EQUITY_Q": (
        "Equity Q (corporate equities / net worth, market value)", False,
        "NOT inverted. High market value against net worth is the "
        "misvaluation channel Shleifer & Vishny (2003) and RKRV (2005) "
        "identify - overvalued acquirers rationally pay in stock, and "
        "that is late-cycle. Constructed here rather than fetched: "
        "FRED's ready-made MVEONWMVBSNNCB is DISCONTINUED (ends "
        "2017-Q4) and building on it would silently freeze the series."),
}


def _get(url, timeout=90, tries=4, ua=None):
    """Fetch with exponential backoff.

    Shells out to curl rather than using urllib. The agent proxy in
    front of this session closes urllib's connections mid-response
    (RemoteDisconnected) on FRED specifically, reproducibly, and
    through all four retries - while curl over HTTP/1.1 succeeds every
    time against the same URL. Not worth diagnosing further; curl is
    present everywhere this runs.

    `ua` DEFAULTS TO NONE ON PURPOSE. FRED returns an empty reply
    (curl rc=52) to a custom User-Agent and serves normally with
    curl's default - isolated by holding the URL fixed and varying
    only the header. Do not add a polite identifying UA here "for
    hygiene"; it silently breaks every FRED fetch. SEC EDGAR is the
    opposite and REQUIRES a contact UA, so pass one explicitly there.
    """
    import subprocess
    import time
    last = None
    for i in range(tries):
        try:
            cmd = ["curl", "-sS", "--http1.1", "--max-time", str(timeout)]
            if ua:
                cmd += ["-A", ua]
            cmd.append(url)
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout + 15)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
            last = RuntimeError(
                f"curl rc={r.returncode} stderr={r.stderr[:200]}")
        except Exception as e:          # noqa: BLE001 - retry anything
            last = e
        if i < tries - 1:
            time.sleep(2 ** (i + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url}") from last


def _fetch_gz():
    """Gilchrist-Zakrajsek credit spread, Fed Board, monthly 1973-.
    Dates arrive as M/D/YYYY. Returns (gz_obs, ebp_obs, url)."""
    text = _get(EBP_CSV)
    rows = list(csv.reader(text.splitlines()))
    hdr = rows[0]
    ig, ie = hdr.index("gz_spread"), hdr.index("ebp")
    gz, ebp = [], []
    for row in rows[1:]:
        if len(row) <= max(ig, ie) or not row[0]:
            continue
        m, d, y = row[0].split("/")
        iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        try:
            gz.append((iso, float(row[ig])))
            ebp.append((iso, float(row[ie])))
        except ValueError:
            continue
    return gz, ebp, EBP_CSV


def load_hsr(path=None):
    """Official monthly US deal count, FTC/DOJ HSR Appendix B Table 1.

    432 months, 1989-10 .. 2025-09, stitched from four report vintages.
    Counter-agent verified 2026-09-09: it is TRANSACTIONS (Table 1),
    not filings (Table 2, which sits on the next page and runs
    1.89-1.97x higher because each transaction generates a filing from
    both the acquiring and the acquired person); it sums EXACTLY to the
    reports' own published annual totals for all 36 fiscal years; and
    372 of 432 months are corroborated by at least two independently
    published report vintages with zero disagreements.

    Where vintages disagree, the chain prefers the NEWEST report. That
    is deliberate and load-bearing: the FTC restated FY2004 and FY2005
    after finding its own coding errors, and the newest vintage carries
    the corrections.

    PUBLICATION LAG ~10 MONTHS. FY2025 (ending Sep-2025) was published
    Jul-2026. This series cannot nowcast; it is the calibration
    backbone only.
    """
    path = path or os.path.join(_HERE, "hsr_monthly.csv")
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            out.append((row["month"] + "-01",
                        float(row["hsr_transactions_reported"])))
    return out


def load_edgar(path=None):
    """Monthly merger-proxy counts, built by ma_edgar.

    DISTINCT ACCESSIONS, not index rows. Current to within a day, which
    is the point - it covers the ~10 months HSR has not yet published.
    """
    path = path or os.path.join(_HERE, "edgar_monthly.csv")
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            out.append((row["month"] + "-01", float(row["merger_proxies"])))
    return out


def _fetch_fred(sid, timeout=90):
    url = FRED_CSV.format(sid=sid)
    text = _get(url, timeout=timeout)
    rows = list(csv.reader(text.splitlines()))
    out = []
    for row in rows[1:]:
        if len(row) < 2 or row[1] in (".", ""):
            continue
        try:
            out.append((row[0], float(row[1])))
        except ValueError:
            continue
    return out, url


def to_quarterly(obs, how="mean"):
    """Collapse dated observations onto calendar quarters.

    'mean' for daily/weekly series (a quarter's average condition).
    'last' for series already published quarterly - taking a mean of
    one observation is the same thing, but being explicit stops anyone
    later 'improving' it into an interpolation.
    """
    buckets = {}
    for date, val in obs:
        y, m = int(date[:4]), int(date[5:7])
        q = (m - 1) // 3 + 1
        buckets.setdefault(f"{y}Q{q}", []).append(val)
    out = {}
    for k, vals in buckets.items():
        out[k] = sum(vals) / len(vals) if how == "mean" else vals[-1]
    return out


def quarter_range(start, end):
    """Inclusive list of 'YYYYQn' labels."""
    sy, sq = int(start[:4]), int(start[5])
    ey, eq = int(end[:4]), int(end[5])
    out = []
    y, q = sy, sq
    while (y, q) <= (ey, eq):
        out.append(f"{y}Q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def build(refresh=True):
    """Fetch every series, align to quarters, construct equity Q.

    Writes a cache carrying the fetch date and the source URL for each
    series, so any published reading can be reproduced from the record
    rather than from a re-fetch that may have revised underneath it.
    """
    os.makedirs(CACHE, exist_ok=True)
    raw = {}
    for sid, (label, how, _inv, _why) in SERIES.items():
        path = os.path.join(CACHE, f"{sid}.json")
        if refresh or not os.path.exists(path):
            obs, url = _fetch_fred(sid)
            with open(path, "w") as f:
                json.dump({"series_id": sid, "label": label,
                           "source_url": url, "n_obs": len(obs),
                           "first": obs[0] if obs else None,
                           "last": obs[-1] if obs else None,
                           "obs": obs}, f)
        with open(path) as f:
            raw[sid] = json.load(f)
    # GZ spread (+ EBP counter-check) from the Fed Board
    gz_path = os.path.join(CACHE, "GZ.json")
    if refresh or not os.path.exists(gz_path):
        gz, ebp, url = _fetch_gz()
        with open(gz_path, "w") as f:
            json.dump({"series_id": "GZ_SPREAD", "source_url": url,
                       "n_obs": len(gz), "first": gz[0], "last": gz[-1],
                       "obs": gz, "ebp_obs": ebp}, f)
    with open(gz_path) as f:
        gzraw = json.load(f)
    raw["GZ_SPREAD"] = gzraw

    quarterly = {sid: to_quarterly(raw[sid]["obs"], SERIES[sid][1])
                 for sid in SERIES}
    quarterly["GZ_SPREAD"] = to_quarterly(gzraw["obs"], "mean")
    quarterly["EBP"] = to_quarterly(gzraw["ebp_obs"], "mean")

    # EDGAR merger proxies: also a flow, also summed.
    #
    # THE CURRENT QUARTER IS DROPPED, and a month-count guard is not
    # enough to do it. EDGAR is current to yesterday, so the quarter in
    # progress has all three month buckets present but the last one only
    # partly elapsed - 2026-09 read 12 filings on the 9th against a ~33
    # run rate. Summed as-is that lands as a 60% collapse in deal
    # activity that is purely the calendar. A quarter counts only once
    # its final month is fully behind us.
    try:
        eg = load_edgar()
        today = time.strftime("%Y-%m")
        cy, cm = int(today[:4]), int(today[5:7])
        current_q = (cy, (cm - 1) // 3 + 1)
        eq = {}
        for date, v in eg:
            y, m = int(date[:4]), int(date[5:7])
            eq.setdefault((y, (m - 1) // 3 + 1), []).append(v)
        quarterly["EDGAR_PROXIES"] = {
            f"{y}Q{q}": sum(v) for (y, q), v in eq.items()
            if len(v) == 3 and (y, q) < current_q}
        raw["EDGAR_PROXIES"] = {
            "series_id": "EDGAR_PROXIES", "n_obs": len(eg),
            "source_url": "https://www.sec.gov/Archives/edgar/full-index/",
            "first": eg[0], "last": eg[-1]}
    except FileNotFoundError:
        quarterly["EDGAR_PROXIES"] = {}
        raw["EDGAR_PROXIES"] = {"series_id": "EDGAR_PROXIES", "n_obs": 0,
                                "source_url": "not built", "first": None,
                                "last": None}

    # HSR: sum months into quarters (a count is a flow, not a level -
    # averaging it would silently rescale the series by 1/3)
    hsr = load_hsr()
    hq = {}
    for date, v in hsr:
        y, m = int(date[:4]), int(date[5:7])
        # Threshold-drift correction, applied on the FISCAL year the
        # bracket tables and the factors are both defined on (Oct-Sep).
        # Aligning these matters: FY1990 and CY1990 differ by 16% in
        # the base year of the headline ratio.
        fyr = y + 1 if m >= 10 else y
        v *= HSR_DRIFT_FACTORS_FY.get(fyr, 1.0)
        hq.setdefault(f"{y}Q{(m - 1) // 3 + 1}", []).append(v)
    # drop part-quarters at the seams so a 2-month quarter cannot read
    # as a collapse
    quarterly["HSR_COUNT"] = {k: sum(v) for k, v in hq.items() if len(v) == 3}
    raw["HSR_COUNT"] = {"series_id": "HSR_COUNT", "n_obs": len(hsr),
                        "source_url": "FTC/DOJ HSR annual reports "
                                      "(Appendix B Table 1)",
                        "first": hsr[0], "last": hsr[-1]}
    eq, nw = quarterly["NCBEILQ027S"], quarterly["TNWMVBSNNCB"]
    quarterly["EQUITY_Q"] = {k: eq[k] / nw[k] for k in eq
                             if k in nw and nw[k]}
    return raw, quarterly


def oriented(quarterly, sid):
    """Apply sign orientation: higher = later in the cycle."""
    invert = SERIES[sid][2] if sid in SERIES else DERIVED[sid][1]
    s = quarterly[sid]
    return {k: (-v if invert else v) for k, v in s.items()}


def scoreable(sid, quarter):
    """Whether a component may CONTRIBUTE to the composite at `quarter`.

    Only HSR is restricted, and only before 2001Q2 - see HSR_SCORE_FROM.
    Charting is unrestricted; this gates scoring alone.
    """
    if sid == "HSR_COUNT" and quarter in HSR_EXCLUDE_QUARTERS:
        return False
    floors = {"HSR_COUNT": HSR_SCORE_FROM,
              "EDGAR_PROXIES": EDGAR_SCORE_FROM}
    floor = floors.get(sid)
    if floor is None:
        return True
    qy, qq = int(quarter[:4]), int(quarter[5])
    fy, fq = int(floor[:4]), int(floor[5])
    return (qy, qq) >= (fy, fq)


# The six that actually score. NCBEILQ027S and TNWMVBSNNCB are inputs
# to EQUITY_Q and are deliberately absent - scoring a numerator and its
# own ratio would double-count the same information.
COMPONENTS = ["GZ_SPREAD", "DRTSCILM", "DRSDCILM", "NFCI",
              "NCBCEBQ027S", "EQUITY_Q", "HSR_COUNT", "EDGAR_PROXIES"]

if __name__ == "__main__":
    raw, q = build()
    print(f"{'series':<14} {'n_raw':>7}  {'quarters':>8}  first    last")
    for sid in SERIES:
        print(f"{sid:<14} {raw[sid]['n_obs']:>7}  {len(q[sid]):>8}  "
              f"{min(q[sid])}  {max(q[sid])}")
    for sid in ("GZ_SPREAD", "EBP", "EQUITY_Q", "HSR_COUNT"):
        print(f"{sid:<14} {'derived':>7}  {len(q[sid]):>8}  "
              f"{min(q[sid])}  {max(q[sid])}")
    print()
    for k in ("1985Q1", "2026Q1"):
        if k in q["EQUITY_Q"]:
            print(f"  equity Q {k} = {q['EQUITY_Q'][k]:.3f}")
