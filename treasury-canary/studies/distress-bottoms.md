# Distress bottoms — does SLOWING bankruptcy growth mark the bottom?

**Question (Casey, 2026-10-13):** bankruptcy spikes don't predict recessions
(`distress-signals.md`: filings rise with or after them), but once a downturn is
underway, does the *slowing* of bankruptcy growth — still rising, but less each
period ("8%, 7%, 6% … 2%") — mark the bottom? Two bottoms, scored separately: the
economy's (NBER trough) and the stock market's (the equity low).

## Research pass (2026-10-13; literature only, blind to our data)

Full report: scratchpad `bottoms_research.md` (summarised here; counter-agent
check in progress — numbers below are as reported, pending verification).

- **Failure counts turned roughly with the trough:** −0.5 months on average
  1879–1938 (7 leads, 8 lags at 16 troughs; Zarnowitz & Lerner 1961, Table
  12.2). **Liabilities** (dollar-weighted) led troughs by −7.5 (14 of 16 led),
  fading to about −3 in 1948–75 (Moore 1983, Table 24-5); dropped from the NBER
  short list in 1966.
- **Business filing levels** peaked in or at the trough year (1982, 1991, 2001,
  mid-2009); consumer filings 1–2 years later (1992, 2003, 2010).
- **Equity lows** led troughs by a median ~4–5 months (17 of 23 troughs
  1873–1970, Moore 1983 Table 9-2; daily closing lows 1949–2020 median −4.5),
  except 2002 (+11). Only 7 of 12 postwar recessions had a ≥ 20% bear market.
- **Initial claims** peak at about the trough (median 0, BCD); stocks bottomed
  *before* claims peaked at every comparable trough 1949–82 (by 2–12 months),
  except 2001–02.
- **No study tests failure or filing growth roll-overs** against troughs or
  equity lows. Growth-rate recovery signals lag troughs (Zarnowitz & Moore 1982:
  first signal +1 month on average at 1949–80 troughs).
- **Mechanics:** y/y growth of a smooth rise lasting R months peaks about
  (R − 12)/2 months before the level peaks.
- **Prior:** a release-dated roll-over in failure counts or business filings
  should land near the trough (roughly −6 to +2 months), *after* the typical
  equity low, with little room to beat claims.

**Already seen by the authors (the test is not fully blind):** the court
business-filing growth path 1981–2026 and the D&B real-liabilities growth path
1955–86 (charts in `distress-signals.md`); the D&B liabilities +25% alert timing
at PEAKS 1894–1938 and 1948–66; D&B count levels in the 1934–39 segment overlaps
(splice check only); annual court filing levels and ERP-2004 B-96 annual D&B
rows 1955–84 (research agent); and the literature's own count/liability turning
points at troughs 1879–1958. Not seen: any monthly D&B count growth path, any
roll-over date, any timing of our series against troughs or equity lows.

---

## SPEC v0 — pre-registered 2026-10-13, BEFORE any roll-over is scored

### 0. Shared definitions

- **Dates.** Month index m. NBER peaks p_r and troughs τ_r, current chronology
  (`study.NBER_PRE` 1895–1961 + `engine.PEAKS` 1969–2020).
- **Growth.** g(t) = S_w(t) / S_w(t−12) − 1, S_w = trailing w-month sum (never
  centred). Primary w = 6 months (the D&B counts' months-for-cyclical-dominance
  span, Moore 1961 Table 3.8); grid w ∈ {3, 6, 12}. Quarterly series: trailing
  2-quarter sums vs 4 quarters earlier (grid 1, 2, 4 quarters). g is computed
  only when all 12 + w input months lie inside one data segment and outside
  every mask; otherwise it is "uncomputable".
- **Release month.** D&B monthly counts: data month + 1 (available by the 20th
  of the following month; Moore & Shiskin 1967 currency score 80). Court
  quarterly filings: quarter end + 1 month (ABI 1980–2000 is a retrospective
  compilation: robustness at + 2). Claims: week end + 5 days. Equity prices:
  no lag.
- **Armed.** H(t) = max of computable g over the trailing 12 months (4
  quarters). The series is armed at t when H(t) ≥ θ_A = +10% (grid 5, 10, 20%).
- **Roll-over signal.** Condition C(t): armed, g(t) computable and
  g(t) ≤ H(t) − d(t), d(t) = max(5 pp, H(t)/3) (grid: H/4, H/3, H/2 with the 5 pp
  floor). The signal fires at the first t where C holds for k consecutive
  observations (k = 2 monthly, 1 quarterly; monthly grid 1, 2, 3); an
  uncomputable observation breaks the run.
- **Re-arming.** After a signal at t0, no further signal until the series sets a
  new 12-month high at or above θ_A after t0 (g(s) = H(s) ≥ θ_A for some
  s > t0): a re-acceleration. The earlier signal is then flagged "false start".
- **Targets per recession r.** Economy: τ_r. Equity: b_r = the month of the
  lowest monthly-average equity level in [p_r − 6, min(τ_r + 12, p_{r+1} − 1)]
  (Cowles/S&P all-stocks index to 1956-12, OECD US share prices from 1957-01; no
  window straddles the seam; missing months — NYSE closed Aug–Nov 1914 — are
  skipped).
- **Episode signal.** The first roll-over released in [p_r, min(τ_r + 24,
  p_{r+1} − 1)]. (Episode windows use NBER dates, known only after the fact —
  the test is "given we are in a recession, where does the first roll-over
  land", stated as look-ahead in the honesty box.)
- **Classification** vs target T, e = release − T (months): trough HIT if
  −6 ≤ e ≤ +3; equity HIT if −3 ≤ e ≤ +3; EARLY below the window, LATE above it,
  MISS when no signal is released in the episode window.
- **Excluded (context only):** 1945 (wartime, failures at record lows,
  demobilisation) and 2020 (policy support; filings fell). 1918–19 is scored and
  flagged (wartime).

### 1. Primary — D&B number of commercial failures, monthly, 1895–1965 (P)

- **Data.** Three never-spliced segments (`load.dnb_count_segments`): A
  1894-01..1938-08 for recessions through 1929–33; B 1934-06..1939-12 for
  1937–38; C 1939-01..1965-06 for 1948–61. Inside A, the 1933 definition change
  (real-estate and insurance brokers, holding and finance companies, shipping
  agents excluded) is a break: g whose inputs straddle it is uncomputable (month
  per the NBER m09029a note; if the note gives no month, every input window that
  contains both a pre-1933 month and a 1933 month is uncomputable).
- **Episodes (16):** 1895–97, 1899–1900, 1902–04, 1907–08, 1910–12, 1913–14,
  1918–19 (flag), 1920–21, 1923–24, 1926–27, 1929–33, 1937–38, 1948–49, 1953–54,
  1957–58, 1960–61.
- **Shots:** P/trough and P/equity. Holm across the two at 0.10.
- **Statistic:** HITS = number of HIT episodes.
- **Null (is the roll-over month better than any armed month?):** for each
  episode, draw a release month uniformly from the months in the episode window
  at which the series was armed; an episode with no armed month is a MISS in
  both. p = (1 + #{HITS_null ≥ HITS_obs}) / (1 + 9,999); seed 20261012.
- **Clock comparison (leave-one-out):** arm_r = first armed month at or after
  p_r − 12; clock signal = arm_r + c_r, c_r = median over the OTHER episodes of
  (T − arm). The roll-over must have the smaller median |e|.
- **Grade "MARKS THE BOTTOM"** (per target): HIT in ≥ 2/3 of scored episodes,
  EARLY in ≤ 1 per 6, Holm p ≤ 0.10, smaller median |e| than the leave-one-out
  clock, and HIT in ≥ 2/3 for at least 2 of the 3 w values. Anything else is
  described by its timing (median e, interquartile range, EARLY/LATE counts),
  e.g. "lands after the equity low (median +5 months)".
- **Reported by era:** 1895–1914 (6), 1918–38 (6), 1948–61 (4).

### 2. Replication — business bankruptcy filings (court), quarterly, 1981–2026 (R)

- Series and masks as in `distress-signals.md` SPEC v1 (ABI 1980–2025, AO first
  prints 2026; raw 2005Q2–2008Q4 and 2020Q2–2021Q4 masked). Scored: 1981–82,
  1990–91, 2001. 2007–09 is unscorable under the masks (reported, with a
  mask-to-2007Q4 sensitivity); 2020 excluded.
- The authors have seen this growth path, so R is descriptive: "consistent" if
  ≥ 2 of 3 HIT for the target P ships on.
- **A live dashboard readout** of "bottoming" requires P to grade MARKS THE
  BOTTOM and R to be consistent. Otherwise the panel shows the roll-over status
  as context with its measured timing.

### 3. Benchmarks — initial claims, 1967 onward (report-only)

- **C1 claims peak:** 4-week average of ICSA; armed when ≥ 1.2 × its level 52
  weeks earlier; signal at the first week when the 4-week average is ≤ 0.9 × its
  running maximum since arming and that maximum was set ≥ 8 weeks earlier;
  released week end + 5 days.
- **C2 claims roll-over:** monthly NSA claims (ICNSA, weeks assigned by their
  ending Saturday), the identical rule of §0.
- e vs trough and equity low at 1970, 1975, 1980, 1982, 1991, 2001, 2009 (2020
  context), side by side with R and the D&B liabilities series.

### 4. Secondary (report-only)

- D&B liabilities, 1894–1986 (`load.dnb_liability_segments`), w = 12 (its
  11-month smoothing span): the literature's trough leader. Noisy; the 1894–1933
  bank-failure inclusion question and the authors' sight of 1955–86 are flagged.
- Consumer filings (annual 1980+, quarterly 1994+): expected 1–2 years late.

### 5. Trader's view (report-only, the practical question)

For each episode and each entry rule — the roll-over (P, R, C1, C2), the first
armed month, the NBER peak + 6 months, the first month the equity index is
≥ 20% below its trailing 12-month high inside the window, and a random armed
month (median of 1,000 draws) — report: the equity return to + 6, + 12 and + 24
months; the worst further drawdown within 12 months; and, for entries after the
low, the share of the b_r → b_r + 12 rebound already missed. Medians by rule; no
test.

### 6. Multiplicity, power, seeds

- Shots: 2 (P/trough, P/equity), Holm at 0.10. Everything else is descriptive.
- Power (synthetic, before the run): 16 episodes of a smooth rise of length
  R ∈ [12, 30] months whose level peaks at τ + δ, δ ~ N(0, σ) with σ ∈ {2, 4, 8},
  plus multiplicative noise matching the counts' irregular/cyclical ratio
  (~4.9 monthly); report P(grade) and the null's size when the series is shifted
  at random against the troughs.
- Seed 20261012 for every draw.

### 7. Honesty, stated now

- 16 primary episodes; 3 court episodes; little power to separate "near the
  trough" from "a few months later".
- Episode windows use NBER dates (look-ahead): the test is conditional on being
  in a recession.
- Monthly averages date equity lows up to ~2 months differently from daily
  closes; most recessions had no 20% bear market.
- D&B definition breaks (1933, 1934–39, 1939/40) and wartime flags.
- A HIT on the trough is not a trading signal: the equity low usually comes
  ~4–5 months earlier.

### Run order

Spec reviews (statistics; data and measurement) → SPEC v1 → power → one run →
two independent verifiers → honesty box with frozen numbers → charts → panel
(only what ships; otherwise context) → commit/push → note the redeploy
(treasury-canary).
