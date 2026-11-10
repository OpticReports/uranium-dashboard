# Distress bottoms — does SLOWING bankruptcy growth mark the bottom?

**Question (Casey, 2026-10-13):** bankruptcy spikes don't predict recessions
(`distress-signals.md`: filings rise with or after them), but once a downturn is
underway, does the *slowing* of bankruptcy growth — still rising, but less each
period ("8%, 7%, 6% … 2%") — mark the bottom? Two bottoms, scored separately: the
economy's (NBER trough) and the stock market's (the equity low).

## Research pass (2026-10-13; literature only, blind to our data)

Full report: scratchpad `bottoms_research.md`. Counter-agent check: PASS_WITH_FIXES
— every primary-source number re-read from the page images; the fixes are applied
below.

- **Failure counts turned roughly with the trough:** −0.5 months on average
  1879–1938 (7 leads, 8 lags; 15 of 16 troughs matched; Zarnowitz & Lerner 1961,
  "Cyclical Changes in Business Failures and Corporate Profits", Table 12.2).
  **Liabilities** led troughs by −7.5 (14 of 16 led) on Dun's basis, fading to
  about −3 in 1948–75 (Moore 1983, Table 24-5); dropped from the NBER short list
  in 1966.
- **Rises were long:** pre-1938 rises in failure counts averaged 26.8 months
  (declines 21.8; Zarnowitz & Lerner p.354); the postwar rises ran 47 and 68
  months (Dec-45 → Nov-49, Aug-52 → Apr-58).
- **Business filing levels** peaked in or at the trough year (1982, 1991, 2001,
  Q2-2009); consumer filings 1–2 years later (1992, 2003, 2010).
- **Equity lows** led troughs by a median ~4–5 months (17 of 23 troughs
  1873–1970, median −6 before 1945 and −4 after; Moore 1983 Table 9-2; daily
  closing lows 1949–2020 median −4.5), except 2002 (+11). 8 of 12 postwar
  recessions had a ≥ 20% decline.
- **Initial claims** peak at about the trough (median 0, BCD); stocks bottomed
  *before* claims peaked at every comparable trough 1949–82 (by 2–12 months,
  median 4), except 2001–02.
- **No study tests failure or filing growth roll-overs** against troughs or
  equity lows. Growth-rate recovery signals lag troughs (Zarnowitz & Moore 1982:
  first signal +1 month on average at 1949–80 troughs).
- **Mechanics (verified by simulation):** y/y growth of a rise lasting R months
  peaks somewhere in [−(R − 12), 0] months before the level peaks — −(R − 12)/2
  for a symmetric S-shape, earlier for front-loaded rises, at the peak for
  back-loaded ones; a level that plateaus instead of falling can roll over after
  its peak.
- **Prior (for this rule; corrected by the v1 review):** g itself peaks ~5
  months before the level peak for a 27-month rise, but a noise-free roll-over
  under SPEC v1 is *released ~4 months after* the level peak (+2 for a 36-month
  rise, 0 for 47; at the final θ_A = 15% a 68-month rise of 0.6 log points arms
  and fires ~4 months before the level peak). With count
  levels turning ~−0.5 at troughs, expect e ≈ +3 to +4 against the trough —
  the MARKS edge or CONFIRMS — and ~9–10 months after the pre-1945 median
  equity low. Postwar 4–6-year rises may never reach θ_A (MISS). Business
  filings (levels peak at the trough year): after the trough, later still
  against the equity low. Little room to beat claims after 1967.
- **Data caveats from the check:** the 1933 D&B reclassification is dated
  "1933" by NBER/HSUS but "available only from January 1934" by the Survey of
  Current Business (old-basis figures published through Apr-1936; step −3.8% in
  1934); the Jun-1934 Section 77-B inclusion and the 1939 coverage change are
  confirmed; the NUMBER series excludes banks; the 1894–1938 monthly file is a
  year-end (January annual issue) vintage, not first prints — monthly figures
  were published the following month in real time; Moore 1950's liabilities
  row is Bradstreet's basis (use Zarnowitz & Lerner's −7.5 for Dun's).

**Already seen by the authors (the test is not fully blind):** the court
business-filing growth path 1981–2026 and the D&B real-liabilities growth path
1955–86 (charts in `distress-signals.md`); the D&B liabilities +25% alert timing
at PEAKS 1894–1938 and 1948–66; D&B count levels in the 1934–39 segment overlaps
(splice check only); annual court filing levels and ERP-2004 B-96 annual D&B
rows 1955–84 (research agent); and the literature's own count/liability turning
points at troughs 1879–1958. Not seen: any monthly D&B count growth path, any
roll-over date, any timing of our series against troughs or equity lows.

---

## SPEC v0 — pre-registered 2026-10-13, BEFORE any roll-over is scored (SUPERSEDED by SPEC v1 below; kept for the record)

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

---

## SPEC v1 — OPERATIVE. Amended 2026-10-13 after the statistics and data reviews (both BLOCK), before any roll-over is scored

What changed and why (one line each; details in the counter-agent log):
the rule fires 2–9 months after the level peak by construction, so "near the
bottom" may be unreachable — reachability is now decided before the run, and a
CONFIRMS window is added; the armed-month null is replaced by a lag permutation
(a clock beat the old one); arming is calibrated so noise alone gives ≤ 1
roll-over a decade; every roll-over is scored (false bottoms), not only those
inside recessions; the equity low needs a real decline and an unambiguous
month; edges, gaps and censoring are defined; the 1898-06 typo is corrected.

### 0. Definitions

- **Dates.** Month index m. NBER chronology as v0 (25 cycles, verified against
  FRED USREC). Excluded (context only): 1945 and 2020. War-flagged: 1918–19 and
  1948–49 (every grade also reported without them).
- **Growth.** g(t) = S_w(t) / S_w(t−12) − 1, S_w the trailing w-month sum (never
  centred); quarterly series use w quarters against 4 quarters earlier. Primary
  w = 6 months (a plain choice); grid w ∈ {3, 6, 12}. g is computable when all
  2w input months are present and unmasked and the whole span t − 12 − w + 1 … t
  lies inside one data segment.
- **Trailing high.** H(t) = max g over t − 11 … t (4 quarters) — defined only
  when every g in that window is computable; after a re-arm at s, the window is
  max(s, t − 11) … t.
- **Arming.** Armed when H(t) ≥ θ_A. θ_A and the floor are fixed by the §6
  calibration before the run: the smallest θ_A in {10, 15, 20, 25%}, then the
  smallest floor in {5, 7.5, 10 pp}, giving ≤ 1 roll-over per decade on
  synthetic no-recession series at the pre-1914 count noise.
- **Roll-over.** The first t with H(t) defined, armed, g(t) computable and
  g(t) ≤ H(t) − d(t), d(t) = max(floor, H(t)/3), for k consecutive periods
  (k = 2 monthly, 1 quarterly); an uncomputable period breaks the run; exact
  decimal ties count.
- **Re-arming.** After a signal at t0, no further signal until g has risen by
  d(t0) from its lowest value since the signal (a re-acceleration, at some
  s > t0); H then restarts at s. A signal is a "false start" when, after that
  re-arm, H ≥ θ_A again (growth back above the arming line) at a month released
  inside the same episode window. (Amended before the run: the
  reviewers' "g(s) ≥ g(t0) + d(t0)" blocked the next cycle whenever the previous
  roll-over fired while growth was still high — 10 of 16 synthetic episodes went
  MISS in the smoke test. The stale-high case they flagged still does not
  re-arm.)
- **Release.** D&B counts: data month + 1 (sensitivity + 2; a HIT present only
  at + 1 is "lag-sensitive"). Court quarterly: quarter end + 1 (sensitivity + 2,
  all years). Claims: last week-end of the month + 5 days. D&B liabilities: + 2.
- **Episode windows.** Trough shots: releases in [p_r, min(τ_r + 24, p_{r+1} − 1)].
  Equity shot: [min(p_r, b_r − 3), same end]. The episode signal is the first
  roll-over released in the window. CENSORED: no signal released before an
  uncomputable stretch inside the window (a non-HIT, listed). LEFT-CENSORED (also
  a non-HIT, listed): the window opens before H is defined and the first signal
  fires within k periods of H becoming defined — it may stand in for an earlier,
  unobservable roll-over (P 1895–97; R 1981–82). Flags:
  "pre-armed" (armed at p_r − 12), "carry-over" (its high was released before
  p_r − 12; sensitivity without these episodes).
- **Targets.** Trough τ_r. Equity low b_r: the month of the lowest Shiller S&P
  composite monthly price in [p_r − 6, min(τ_r + 12, p_{r+1} − 1)] (Aug–Nov 1914
  dropped; Cowles/OECD cross-check). b_r is valid only if it is not the window's
  first or last month and the price is ≥ 10% below its highest level of the
  prior 12 months; otherwise the episode has no equity low (excluded from the
  equity shot, listed). Low zone: months within 3% of the minimum; a zone month
  more than 3 months from b_r makes the episode AMBIGUOUS; 1913–14 is CENSORED
  (exchange closed). The equity grade must also hold without ambiguous and
  censored episodes.
- **Shots and windows** (e = release − T): **MARKS-trough** HIT −6 … +3;
  **CONFIRMS-trough** HIT 0 … +9 (the rule's mechanical lag after a level peak
  at the trough, from the reviewers' noise-free simulation; set before any real
  roll-over is seen); **MARKS-equity** HIT −3 … +3. Below the window EARLY,
  above LATE; MISS = no signal (a non-HIT with |e| = ∞). Window centre c (rounded
  half up): −1, 5, 0.

### 1. Primary — D&B failure counts, monthly, 1895–1965 (P)

- **Data.** Segments A/B/C, never spliced. 1898-06 corrected 1,449 → 1,149
  (HSUS V24 annual identity; sensitivity: month masked). Hard break at 1933-01
  inside A (sensitivity: straight across — the counts show no detectable step;
  1934–35 signals flagged as resting on the 1936 restatement). 1937–38 on B
  (primary) and on A (releases ≤ 1938-09, censored after; "basis-sensitive" if
  they classify differently). Gate test: annual sums against HSUS V24 within
  0.5% (exception 1909, +0.8%).
- **Episodes (16)** as v0. 1929–33: HIT window partly uncomputable (the break).
  1895–97: clocks start at the first month with H defined (flagged).
- **Test.** HITS = number of HIT episodes. Null: hold each episode's observed
  release fixed and permute the lags L_r = T_r − p_r across the shot's episodes
  (10,000 permutations, seed 20261012); p = (1 + #{HITS_π ≥ HITS_obs}) / 10,001.
  Holm across the shots that are tested, at 0.10.
- **Clocks** (leave-one-out, aimed at T + c): arm clock = arm_r + median over the
  other episodes of (T + c − arm), arm_r = first armed release in
  [p_r − 12, window end] (none → MISS); peak clock = p_r + median over the other
  episodes of (T + c − p). Medians rounded half up.
- **Grade** for a shot: HITS ≥ 2/3 of its episodes, EARLY ≤ 1 per 6, Holm p ≤
  0.10, median |e − c| strictly smaller than both clocks' (MISS = ∞; ties fail),
  HITS ≥ 2/3 at ≥ 2 of the 3 w values (w = 3 and w = 12 scored against the window
  shifted by −2 and +3 months, their noise-free offsets), and HITS ≥ 2/3 without
  the war-flagged episodes. MARKS-trough / MARKS-equity passing → "MARKS THE
  BOTTOM"; CONFIRMS-trough passing → "CONFIRMS THE BOTTOM".
- **Reachability, decided in §6 before the run.** A shot whose P(grade) is < 0.2
  at σ = 4 for both μ = 0 and μ = −3 is declared out of reach and not tested;
  its deliverable is the timing estimate: median e with the order-statistic
  interval (≈ 92%; [e(5), e(12)] for 16 episodes, indices from the n used). A
  MISS enters as +∞ ("no roll-over by the window end"); CENSORED episodes are
  excluded and listed; n, n_MISS and n_CENSORED are reported; medians also by
  era (1895–1914, 1918–38, 1948–61).
- **Sensitivity (pre-registered):** θ_A = 10% for the episodes from 1918 (the
  post-1914 noise gives 0.78 noise roll-overs a decade at 10%, inside the bar;
  20% may leave slow postwar rises unarmed). 1895–97 is left-censored (H is
  undefined until 1896-05): its outcome is flagged, not only its clocks.
- **Hindsight diagnostic (report-only):** g-peak = the month of the highest g
  (w = 12) in the episode window; e_gpk = g-peak + 1 − T. It separates "growth
  starts slowing near the bottom" from the rule's detection lag. If the maximum
  sits at the window's first month and g was higher before it, the episode is
  reported as "g peaked before p_r" (the month found by searching back to
  p_r − 36 inside the span), with no timing value.
- **False bottoms:** every roll-over released 1895–1965 is a TRUE BOTTOM if
  −6 ≤ release − τ ≤ +9 for some trough τ (the union of the trough windows),
  else a FALSE BOTTOM; those released in [p_r − 12, p_r − 1] are listed.
  Precision and false bottoms per decade reported, also excluding the war years
  (1917–19, 1942–48). Timing is also reported without the war-flagged episodes
  and, for the equity shot, on valid lows only.

### 2. Context — business filings (court), quarterly, 1981–2026 (R)

- Masks as `distress-signals.md` SPEC v1. Scored: 1990–91 and 2001. 1981–82
  flagged (left-censored; its base includes the new-Code ramp — sensitivity with
  1980Q1 masked). ABI's missing 1,000 business filings of 1995 are placed in Q4,
  with Q1–Q3 placements as sensitivities. 2007–09 unscorable (no sensitivity). 2020 excluded. Context,
  not replication: ≥ 2 of 3 HITs happens 17–34% of the time with no information.
- **Live readout:** a "bottoming" line on the panel only if a P shot grades
  AND P's precision ≥ 1/2 with ≤ 1 false bottom per decade AND R has no false
  bottom 1981–2026. Otherwise the panel shows the current roll-over status as
  context with the measured timing.

### 3. Benchmarks — initial claims (report-only; they overlap R only)

- C1 as v0. C2: monthly value = mean weekly ICNSA of the weeks ending in the
  month; release = last week-end + 5 days; the identical rule. Flags: inputs
  straddling 1972-01 or 1978-01 (coverage), 1970 (GM strike). C1 uses
  current-vintage seasonal factors.

### 4. Secondary — D&B liabilities (report-only)

- Nominal (the 1920–21 and 1929–33 deflations flagged); banks not included
  (confirmed: annual sums equal HSUS V27, which excludes banks); segment A
  through 1938-08 (used for 1937–38) with a hard break at 1933-01 (the
  agents/brokers share of liabilities falls from 15–18% to ~10%), C 1939-01 …
  1983-12 (ends before the 1984 methodology change); w = 12; release + 2; θ_A and
  the floor were calibrated on the counts, a series 2–4 times less noisy.

### 5. Trader's view (report-only)

Shiller S&P composite total return (P plus D/12; Aug–Nov 1914 dropped), entered
the month after release, on a common episode set with "no entry" recorded. Rules:
the roll-over (P, R, C1, C2), the arm month, NBER peak + 6, the first month
≥ 20% below the trailing 12-month high, and a random armed month (median of
1,000 draws). Returns to + 6, + 12 and + 24 months, the worst further drawdown
within 12 months, and the share of the b_r → b_r + 12 rebound already missed.

### 6. Calibration and power (synthetic, before the run)

- Generator (log level): AR(1) background (ρ 0.98, innovation SD 0.012;
  sensitivity 0.008 and 0.016) + a raised-cosine rise of U[12, 30] months and
  decline of U[12, 30] months, amplitude U(0.3, 0.8) log points, level peak at
  τ_r + δ_r, δ_r ~ N(μ, σ) (rises may start before p_r) + iid irregular at the
  measured count noise (`bottoms_noise.py`: ±2-year local seasonal,
  method-matched — 0.085 for 1895–1913, range 0.083–0.098 across ±1–3-year
  seasonals, 0.056 for 1914–65; the superseded fixed-seasonal 0.116, which
  counted seasonal drift as noise, and Moore's 0.134 are sensitivities); real
  NBER chronology, real segments, the 1933 break, release + 1; equity lows at
  their real dates. The two reachability cells (σ = 4, μ ∈ {0, −3}) use 2,000
  replications (SE ≈ 0.009).
- Calibration of θ_A and the floor as §0. Power cells μ ∈ {−6, −3, 0, +3},
  σ ∈ {2, 4, 8}, 400 replications, the full grade per shot. Size under a broad
  clock (level peak at p_r + U(−6, 3) + U[12, 30], no trough information) and
  under a random circular shift.

### 6b. Calibration and power — results (bottoms_power.json, re-frozen 2026-10-13, synthetic only)

A first freeze (commit e825e53) used a pre-1914 noise of 0.116 that counted
seasonal drift as noise (data re-review, BLOCKING); it gave θ_A = 20% and no
reachable shot. Re-measured drift-robustly (`bottoms_noise.py`, 0.085) and
re-run with 2,000 replications in the deciding cells, before any real roll-over
was scored:

- **Arming:** θ_A = 15%, floor 5 pp — 0.54 noise roll-overs a decade at the
  pre-1914 noise (0.12 after 1914); 10% would give 2.1.
- **Mechanical lag:** a noise-free roll-over is released 9, 7, 5 and 4 months
  after the level peak for rises of 12, 18, 24 and 30 months.
- **Size:** P(grade) = 0 for every shot under the broad clock and the random
  shift; the lag-permutation p ≤ 0.10 in 1.3–8% of null replications.
- **Power, P(grade) at σ = 4** (2,000 replications at μ = 0 and −3, 400
  elsewhere; σ = 2 / 8 in the JSON):

  | shot | μ = −6 | μ = −3 | μ = 0 | μ = +3 |
  |---|---|---|---|---|
  | MARKS-trough | 0.36 | 0.047 | 0.0005 | 0.00 |
  | CONFIRMS-trough | 0.005 | 0.164 | **0.237** | 0.035 |
  | MARKS-equity | 0.00 | 0.00 | 0.00 | 0.00 |

  Noise sensitivities for CONFIRMS at μ = 0: 0.2225 at the top of the pre-1914
  range (0.0975), 0.21 at the superseded 0.116, 0.06 at Moore's 0.134 (the
  liabilities figure). At the literature's dispersion (σ ≈ 8) every shot is
  ≤ 0.01.
- **Reachability decision (final, frozen before the run): CONFIRMS-trough is
  tested** (0.237 ≥ 0.2 at μ = 0); MARKS-trough and MARKS-equity are out of
  reach and descriptive only. Holm runs over the one tested shot. Power is
  low (~0.24 at the plausible μ = 0, σ = 4), so a fail is weak evidence of no
  confirmation; a pass would mean the roll-over lands 0–9 months after each
  recession's own trough, tracking it beyond a clock, at least 2 times in 3.
  A "bottoming" line reaches the panel only if CONFIRMS passes AND the §2 live
  conditions hold.

### 7. Honesty, stated now (additions to v0 §7)

- Pre-1927 NBER dates were set on detrended data (Romer 1994): troughs too late,
  biasing e toward EARLY; e on Romer's dates reported where obtainable.
- The 1894–1938 monthly counts are a year-end vintage; real-time monthly
  publication before 1933 is unverified (+ 2 sensitivity).
- Pre-1914 counts are about 1.5 times as noisy as later ones (0.085 vs 0.056).
- Claims overlap only R (3 episodes); P ends in 1965.

---

## RESULTS — scored 2026-10-13 (`distress_signals/bottoms_results.json`, SPEC v1, one run)

Pre-registration frozen at f7be0cd; the run (59bfe06) committed unedited; one
correction run after verifier A fixed descriptive items only (the g-peak against
the equity window, labels, flags, the Cowles/OECD cross-check) — no tested or
headline number changed.

**Verdict: the slowing of bankruptcy growth does not mark the bottom in time to
use.** Failure growth itself turns at about the economic trough (6-month sums:
median 0 months; monthly data: ~2 months before) — and the stock market had
bottomed a median 8 months before the trough in these recessions. A rule that
waits to confirm the slowing fires later still: in 16 recessions 1895–1961 it
fired in 7, five of them 0–8 months after the trough, and none at a recession
stock low. The one tested grade (CONFIRMS-trough) fails. Jobless claims mark the
economic trough sooner.

| series | recessions | rolled over | vs the economic trough | vs the stock low | grade |
|---|---|---|---|---|---|
| D&B failure counts, monthly (primary) | 16 (1895–1961) | 7 (8 never; 1929–33 censored) | −22 (false start), −2, 0, +5, +5, +6, +8 | 0 of 13 recession lows; the 5 with a scorable low came +4 to +13 after it | CONFIRMS-trough: **fails** (5 of 16 in 0…+9, needs 11; lag-permutation p ≈ 0.06) |
| court business filings, quarterly (context) | 1982, 1991, 2001 (2008–09 masked) | 2 of 3 (1 of 2 with 1980Q1 masked) | +5, +5 | +9 (1982, an ambiguous low); −6 (2001, before the Oct-2002 low) | context |
| jobless claims (benchmark) | 7 (1970–2009) | 7 of 7 | claims-peak rule −4 to +3 (median +1); the same roll-over rule +3 to +7 (median +6) | claims-peak rule +1 to +7 after (2001: −10) | benchmark |

- **Bankruptcy growth turns at about the economic bottom — not before it.** On
  the rule's own 6-month sums, growth peaked a median 0 months from the trough
  (interval −3…+3); on monthly data −2 (−5…+1), on 3-month sums −2. The
  pre-registered hindsight diagnostic uses 12-month sums, which date the peak ~3
  months later by construction: +4 (+1…+7). (Post-hoc w-sensitivity:
  `bottoms_posthoc.py`.) Against the stock low the 12-month peak came +6 months
  after it (valid lows; +4…+11). So the slowing Casey described is real and
  roughly coincident with the economic bottom — but it arrives after the market
  has turned, and confirming it takes months more.
- **The roll-over rule then fires late, when it fires.** 5 of its 7 signals
  landed 0–8 months after the trough (median of the signals +5); two came early —
  Feb-1913, a month into the 1913–14 recession and 22 months before its trough (a
  false start), and 1897 by 2 months.
- **It often didn't fire — mostly because of its own re-arming.** 9 of 16
  recessions produced no scored roll-over (8 MISS, 1929–33 censored). Three are
  genuine: failures fell in WWI (1918–19), peaked near +10% in 1926–27, and
  rolled over after the window in 1910–12. Six were locked out by the
  pre-registered re-arm rule: the 1920–21 (+184%) and 1946–48 (+260%) surges set
  a drop of 61 and 87 points, and re-arming needed growth to climb that far above
  its later low, which never happened (1923–24 and 1929–33; all four postwar
  recessions). A +10% line from 1918 (the pre-registered sensitivity) cannot fix
  that: 7 of 10 still miss.
- **Post-hoc variant (`bottoms_posthoc.py`, not pre-registered, not graded):**
  re-arming once growth has turned negative lets the rule fire in 11 of 16. Of
  the six locked-out recessions, four then fire (three 6–9 months after the
  trough; Aug-1931, 19 months before the 1933 trough, a false dawn after which
  failures surged again) and two still miss (1948–49 and 1957–58 rolled over
  before their peaks). Overall 8 of 16 land 0–9 months after the trough (median
  of all 11 signals +5; of the 8 hits +6) — still short of the 11 the grade
  needed.
- **Against the stock market:** none of the primary-rule signals came within 3
  months of a recession stock low (0 of 13); the post-hoc signals do not either.
  (On 3-month sums, a grid row, the 1920–21 roll-over came 1 month after the
  Aug-1921 low; the deflation-flagged liabilities series also hit 1920–21.) The
  court filings' Oct-1987 roll-over — no recession — came 2 months before that
  year's December low, a non-recession low the study did not score.
- **The tested grade fails** on the hit count (the misses), the clocks (a
  leave-one-out "peak + median lag" clock has median |error| 5 months; the
  roll-over's is unbounded because of the misses) and robustness, and would
  still fail with the post-hoc variant (8 of 16). Its lag-permutation p (≈ 0.06;
  exactly 0.060 by enumeration) says that when it fires, its timing tracks each
  recession's own trough beyond a clock — but that p is fragile: 0.15 with the
  1898-06 month masked, 0.13 with 1937–38 on segment A.
- **False bottoms:** 9 roll-overs 1895–1965, 3 with no trough within −6…+9
  (1913, 1915, 1948): precision 2/3, 0.46 a decade (0.36 excluding the war
  years).
- **Modern filings:** 1982 and 2001 rolled over 5 months after the trough (2001
  six months *before* that cycle's late stock low); 1991 never; false bottoms in
  Oct-1987 and Oct-2024. Never earlier than the claims-peak rule; the same
  roll-over rule on claims tied it in 2001.
- **Liabilities (secondary, nominal, noisier):** in the 0…+9 window in 1899,
  1902, 1907, 1913 and 1920; early in 1910 (−9) and 1981–82 (−13); no postwar
  roll-over 1948–80.
- **Trader's view** (Shiller total return, entry the month after the signal).
  On the 7 recessions where the D&B roll-over fired: buying at the roll-over
  returned a median +16% over 12 months with a −2.5% worst further drop — better
  than at the first sign of distress (+13%, −6%) or 6 months after the recession
  began (+3%, −9%) — but ~75% of the first-year rebound from the low was already
  gone. Safe but late. (Over all recessions, different sets: "6 months after the
  start" +21%; 20% off the high +12%, +36% over 24 months, −9% worst drop. The two
  court roll-overs: −6% over 12 months, −11% worst drop.)

**Now (October 2026; court data through 2026Q2).** Business filings +19% on a
2-quarter sum vs a year earlier and at their 4-quarter high: armed, not rolling
over, with no recession. The last roll-over (Oct-2024) was a false bottom. In
past recessions, 5 of 7 D&B roll-overs and both scored court roll-overs came
0–8 months after the economic trough (two D&B signals came early), and none
marked a recession stock low. A roll-over now, without a recession, would be a
non-recession case the study did not score; the one precedent (Oct-1987) came 2
months before that year's low.

Figures: `distress_signals/figs/` — `fig_bottoms_timing.png`,
`fig_bottoms_series.png`, `fig_bottoms_trader.png`.

### Honesty box

- **Power.** The tested grade had ~24% power at plausible settings, so its
  failure alone is weak evidence. Most misses are a re-arming lockout (a rule
  defect found after the run; the synthetic generator never produced +184% or
  +260% surges). The timing evidence carries the conclusion: growth turns at
  about the trough (6-month sums, median 0), after the stock low, and the
  confirmed roll-over comes ~5 months after the trough.
- **Look-ahead.** Episode windows use NBER dates: the results are conditional on
  knowing a recession is under way.
- **What was blind.** The D&B counts' growth path and every roll-over were unseen
  before the run; the court filings were seen (context only).
- **Data.** 1894–1938 monthly counts are a year-end vintage (real-time monthly
  publication before 1933 unverified; + 2-month release changes no HIT count);
  definition breaks 1933, 1934, 1939 (straight across 1933: same 5 HITs; 1929–33
  is CENSORED by the break but a MISS in substance — unbroken, the series only
  re-arms in 1937-12). The 1898-06 typo is fixed; masking the month instead
  censors 1899–1900 by rule (its signal is unchanged at +5): the grade fails
  either way, but the hit count falls to 4 and p rises to 0.15. 1937–38 is
  basis-sensitive: a HIT on segment B, CENSORED on segment A (A ends 1938-08).
- **Dates.** Pre-1927 NBER troughs are set late (Romer 1994): on Romer's dates the
  hits rise from 5 to 6. Equity lows use Shiller monthly averages; flat bottoms
  flagged (1910 ambiguous, 1913 censored), lows < 10% excluded (1899, 1926,
  1960). On Cowles/OECD the low month agrees in 23 of 25 cycles; 1953, 1957 and
  1960 change validity, all MISS either way. The 1918–19 equity g-peak (+1) is
  the least-negative month of a falling series, not a failure wave.
- **Calibration.** θ_A = 15% was chosen on synthetic noise (≤ 1 noise roll-over a
  decade); the generator's raised-cosine rises are a simplification and never
  produced surges of +184% or +260%.
- **Trader's view.** Monthly-average prices, no costs or taxes; medians on
  matched recessions where stated, otherwise over each rule's own set (different
  sets). "Peak + 6" enters at p + 6; the −20% trigger is searched from p − 6, so
  1918 enters before the peak. The 75% rebound-missed figure covers 5 of the 7
  entries (those after a scorable low).
- **Not covered.** Monthly D&B counts after 1965 (none published monthly);
  WARN layoff notices (pending Casey's ICPSR decision); non-recession market
  lows.

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| research check (2026-10-13) | PASS_WITH_FIXES — primary sources re-read from page images; the pre-1938 count rise was 26.8 months (not 21.8), the y/y-peak rule is a band, 8 (not 7) of 12 postwar recessions had a 20% decline, the 1933 break month ambiguous | all, in the research section |
| statistics, SPEC v0 (2026-10-13) | BLOCK — the rule fires 2–9 months after the level peak (grade near-unreachable); the armed-month null loses to a clock; arming at 1.3 noise SDs; false bottoms unscored; equity-low edge cases | all: reachability rule, lag permutation, calibrated arming, false bottoms, equity validity, w-grid shifts, re-arm and carry-over rules |
| data, SPEC v0 (2026-10-13) | BLOCK — the 1898-06 typo (+300) inside a scored window; edges and gaps; noise figure from liabilities, not counts; flat equity bottoms; 1933/1937/1948/R/claims/liabilities details | all: HSUS gate test, censoring, era noise, low zone, segment and release sensitivities, bank-failure correction |
| statistics, SPEC v1 | PASS_WITH_FIXES — the prior described the g-peak, not the rule; MISS dropped from timing; false-start label; θ_A 10% sensitivity; g-peak edge | all |
| data, SPEC v1 | NOT PASS — the frozen pre-1914 noise (0.116) counted seasonal drift as noise | re-measured (0.085, `bottoms_noise.py`), re-frozen θ_A = 15% and reachability (CONFIRMS tested) before the run; left-censoring; liabilities 1933 break; exclusions |
| results A, independent recompute (2026-10-13) | PASS_WITH_FIXES — every number reproduced with exact arithmetic from the spec text; 5 MINOR (g-peak equity window, a label, basis flag, Cowles/OECD cross-check, mask-sensitivity wording), 3 NOTE; flagged that 6 of the 9 non-firing recessions are re-arm lockouts | all; correction run (no tested number changed); post-hoc re-arm diagnostic added and labelled |
| claims & wording B (2026-10-13) | PASS_WITH_FIXES — numbers match (exact lag-permutation p 0.05998); 2 SERIOUS: "slows AFTER the bottom" is a 12-month-smoothing artefact (6-month sums: median 0; monthly −2), and the trader comparison reverses on matched recessions (roll-over +16% vs peak + 6 +3%); minor scoping fixes ("never at the stock low" = recession lows on the primary rule; 1987 precedent; 6 of 9 lockouts; fragile p; chart and panel text; backend status edge) | all; w-sensitivity and matched trader medians computed in `bottoms_posthoc.py` and matching the verifier's own figures |
