# Distress signals — do bankruptcies warn before trouble?

**Question (Casey, 2026-10-12):** "US bankruptcy filings rise 11% in the first
9 months of 2026" (ZeroHedge, relaying Epiq AACER). Casey's hypothesis: people
and businesses going bankrupt are the precursor to others losing income and
blowing up, so rising bankruptcies — overall, by type, or in particular AREAS —
could be early ("pre-cog") signals of distress worth charting and alerting on.

## Research pass (2026-10-12; 3 strands, each adversarially verified)

Frozen data: `distress_signals/data/` (434 files, `MANIFEST.md` with sha256;
all re-verified). Full research + verification record:
`distress_signals/research_results.json`.

- **The 11% is real, from a very low base.** Epiq Jan–Sep 2026: total 469,719
  (+11.0%), individual +11.2% (the release misprints +7%), commercial +7.1%,
  commercial Ch11 +11.3%, Subchapter V +38% (first print vs first print; +46%
  as printed against a revised-down base). Per capita, filings (12m to Jun-2026:
  1.78 per 1,000) are about the 1985 level and below every year 1986–2019; the
  2022 trough (1.16) was the lowest since at least 1980. Q3 growth (+8.3% y/y)
  is the slowest since 2022Q4 (one quarter; a similar dip reversed in 2025).
- **Filing counts are coincident, not leading.** Total filings rose in every
  recession since 1980 except 2020 (policy support) — but fell 5% in 2000, the
  year before 2001's. Consumer filings peak after unemployment (2010Q2–Q3 vs
  Oct-2009). No study shows filings predicting equity drawdowns; the evidence
  runs the other way (markets and spreads forecast defaults).
- **One bankruptcy-type series did lead — then failed out of sample.** Dollar
  liabilities of business failures (inverted) led NBER peaks by 10.5 months on
  average 1879–1938 (11 of 14), counts by 5.0 months (unreliably). After 1948
  the leads became long and erratic (28 and 26 months before the 1953 and 1957
  peaks); dropped from the leading short list in 1966. Nobody has re-tested it
  on 1967–1983.
- **Casey's contagion channel is real but local and slow.** Employees of
  bankrupt firms lose ~13% of earnings in year one (Graham et al., JF 2023); a
  liquidation (vs reorganization) cuts employment at neighbouring
  establishments on the same Census block ~4%/yr for 5 years (Bernstein et
  al.); credit and supply-chain spillovers to rivals and suppliers exist but are
  modest. No study tests whether filings rising in an AREA precede that area's
  job losses; the state-panel evidence that exists runs from labour-market
  downturns to filings.
- **Current context (Oct 2026):** bank loan delinquency benign (all loans 1.42%,
  ~8th pct); NY Fed flows into 90+ delinquency elevated for AUTO (3.00%, highest
  since 2010Q1) but card flows back at pre-GFC norms and flat; initial claims
  197k (2nd pct, −15.5% y/y); Moody's US spec-grade default rate 5.3% (Aug,
  one-month uptick); large corporate filings elevated but flat (S&P GMI H1-2026
  372 vs 371). A real-income squeeze (oil shock; real wages negative y/y since
  Apr-2026) without a layoff channel so far.
- **Breaks any test must handle:** 1978 Code (effective Oct-1979); 1984/1986/
  1994 amendments; BAPCPA (Oct-2005 rush, 2006 collapse, mechanical 2006–08
  rebound in BOTH consumer and business counts); Subchapter V (Feb-2020) and its
  debt-limit changes (Mar-2020, Mar-2022 lapse, Jun-2022, Jun-2024 lapse,
  Apr-2025 indexation, H.R. 7730 passed both chambers Sep-2026, also raising the
  Ch13 limit); 2020–21 policy support; D&B methodology change 1984; Call Report
  2001 and card accounting 2010Q1; venue-shopping of large Ch11 cases (DE, SDNY,
  SDTX, NJ); Epiq Subchapter V prior-year bases revised down 5–11% (compare first
  print with first print); first-print court counts revised (2008Q2 business
  Ch11 first print ~20% low). NY Fed household-credit data and bank delinquency
  vintages did not exist in real time before ~2010–2012.
- **Side finding (dashboard):** the severity index's "CRE delinquency" input is
  FRED DRSREACBS = ALL real-estate-secured loans, residential included. True CRE
  is DRCRELEXFACBS (from 1991Q1; switching loses the 1987–90 run-up).

---

## SPEC v0 — pre-registered 2026-10-12, BEFORE any lead/lag rule is scored (SUPERSEDED by SPEC v1 below; kept for the record)

Four questions, each with its own ship rule. Prior, stated up front: the
literature expects national filing counts to be coincident and the classic
failure-liabilities lead to have faded; the AREA question is genuinely open and
is the only one with enough episodes for real statistical power.

### Shared definitions

- **Recession peaks (NBER):** 1980-01, 1981-07, 1990-07, 2001-03, 2007-12,
  2020-02 (exogenous: reported, never scored); pre-1980 peaks for Q-H below.
- **Onset:** the first period a rule is ON after a run of OFF periods
  (quarterly: ≥ 4 quarters; monthly: ≥ 6 months), counting only observed,
  unmasked periods.
- **Classification** of each onset against the NEXT peak p (trough τ):
  LEAD if in [p − 18m, p − 1m]; COINCIDENT if in [p, p + 3m]; LATE if in
  [p + 4m, τ]; FALSE ALARM otherwise. A peak whose window is covered by a spell
  begun before p − 18m is LIT-THROUGH (not a lead). Quarterly data: a quarter's
  date is its last month.
- **Size test:** circularly rotate the ON/OFF series against the fixed
  recession calendar by every shift ≥ 24 months from 0; p = share of rotations
  with at least as many LEADs and no more false alarms.

### Q-N — do NATIONAL bankruptcy filings lead recessions?

Series (quarterly):
- N1 business filings, all chapters: ABI 1980Q1–2025Q4 + AO F-2 3-month
  national rows 2026Q1–Q2.
- N2 non-business filings: ABI quarterly 1994Q1+; ABI annual 1980–2025.
- N3 business Chapter 11: AO F-2 3-month national, 2001Q1+ (first prints).

Rule: s = 4-quarter moving sum; g = s / s(−4 quarters) − 1; ON when g ≥ θ.
θ primary 10%; robustness grid {5, 10, 15, 20%}.

Masks (periods neither ON nor OFF): BAPCPA 2005Q2–2008Q4 for N1–N3 (so the
2007 episode is UNSCORED for court counts — contaminated, not evidence either
way); policy 2020Q2–2021Q4. The 1981 episode is scored but flagged (1978 Code
effective Oct-1979 inflates the 1980–81 base).

Scored episodes: N1 → 1981, 1990, 2001 (1980 has no lead-in data). N2 annual →
1981, 1990, 2001 (annual resolution: LEAD if the onset year precedes the peak
year). N3 → 2001 only (descriptive).

Ship rule: ALERT-grade only if LEAD in every scored episode, ≤ 1 false alarm
per 10 years of unmasked history, size p ≤ 0.10, and LEAD in all scored
episodes for ≥ 2 of the 4 grid values. PANEL-grade (show as confirmation) if
LEAD or COINCIDENT in every scored episode with ≤ 1 false alarm per decade.
Stated now: with 2–3 scored episodes the size test cannot reach p ≤ 0.10 unless
the rule is near-perfect; national counts are expected to land at PANEL-grade
or below. Descriptive: cross-correlation of g with the 4-quarter change in
unemployment at leads −8…+8 quarters (unmasked periods only).

### Q-H — did DOLLAR-WEIGHTED business-failure liabilities lead out of sample?

The one bankruptcy-type series with a documented historical lead, re-tested on
data its classifiers never saw.

- Series: D&B current liabilities of business failures, monthly, from the
  Business Conditions Digest (series 14) table in BCD June 1987, Appendix C,
  1953-01 to 1986-12, extracted from the FRASER text layer and checked against
  FRED M0933CUSM144NNBR over 1953-01..1968-01 (every overlapping month must
  match at the printed precision, or the mismatch is resolved from the page
  image before the run). Deflated by CPI-U NSA (CPIAUCNS).
- Rule: s = 12-month sum of real liabilities; g = s / s(−12) − 1; ON when g ≥
  θ_H. θ_H primary 25%; grid {15, 25, 40, 60%}. Onset after ≥ 6 months OFF.
  Classification window LEAD = [p − 24m, p − 1m] (classic leads were long).
- OUT-OF-SAMPLE window 1967-01..1983-12 (after Moore-Shiskin's 1966 review;
  before D&B's 1984 methodology change): peaks 1969-12, 1973-11, 1980-01,
  1981-07. 1980/1981 flagged (1978 Code). Context runs (not decisive): the same
  rule on 1894–1938 (M0933A, Moore's sample) and 1948–1966.
- Replication of the NBER method (descriptive): specific-cycle troughs of the
  12-month real-liabilities sum (Bry–Boschan, minimum phase 15 months, cycle 15
  months) matched to each business peak.
- Ship rule: LEAD at ≥ 3 of 4 out-of-sample peaks, ≤ 2 false alarms in
  1967–1983, median lead ≥ 6 months, and ≥ 3/4 LEAD for ≥ 2 of 4 grid values →
  "dollar-weighted large-firm distress leads" survives; build its modern
  analogue (FJC IDB Chapter 11 scheduled liabilities, monthly, Oct-2007+) as a
  panel with a WARN-level alert carrying this record (its own modern record is
  untestable: the data start 2 months before the 2007 peak). Otherwise large-firm
  bankruptcies are shown as context only.

### Q-R — do bankruptcies rising in an AREA precede that area's job losses?

Units: 50 states + DC. Signals: state NON-BUSINESS filings and state BUSINESS
CHAPTER 7 filings (business Ch11 excluded: large cases file where they choose,
not where the jobs are), per 1,000 residents (state population, FRED {ST}POP,
July, linearly interpolated). g_s = growth of the state signal.

- Panel A — annual 1980–2000: state filings from the ABI-hosted AO
  district/state tables (to be downloaded and parsed before the run; national
  sums must equal ABI national totals exactly). Target: next-year change in the
  state's annual-average unemployment rate (FRED {ST}UR).
- Panel B — quarterly 2001Q1–2026Q2: AO F-2 3-month tables by district, summed
  to states (first prints). g = 4-quarter-sum growth. Target: change in the
  state's quarterly-average unemployment rate over the next 4 quarters.

Primary test (both panels): ΔUR(s, t→t+h) = state FE + time FE + β·g(s,t) +
γ·ΔUR(s, t−h→t) + ε (h = 1 year / 4 quarters). Time FE make β a REGIONAL
signal (a state worse than the nation), which is Casey's question. Inference by
permutation: shuffle g across states within each period (keeps the national
cycle, breaks the state link), 2,000 draws; one-sided p for β > 0; two-way
clustered (state, period) SEs reported alongside.

Secondary tests:
- Reverse direction: g(s, t→t+h) on ΔUR(s, t−h→t) with the same FEs (the
  literature expects unemployment to lead filings).
- Beyond claims (Panel B): add state initial-claims growth (FRED {ST}ICLAIMS,
  4-quarter sums, growth) as a control; β must survive.
- Event study (Panel B): state unemployment upturn onsets (state Sahm-style:
  3-month average UR minus its prior 12-month minimum ≥ 0.5pp; onset after ≥ 12
  months unlit); mean relative filing growth (state minus national) at quarters
  −8…+8, clustered by onset date; pre-trend test = mean over quarters −4…−1 > 0
  (one-sided, 5%). Reported for all onsets and separately for REGIONAL onsets
  (not within ±12 months of a national peak — e.g. oil-patch 2015–16).
- Out-of-sample (Panel B): fit through 2014Q4, forecast 2015Q1–2026Q2 relative
  ΔUR (each state minus the cross-state mean that quarter); compare with the same
  model without g: MSE ratio and a Diebold–Mariano test clustered by quarter.
- Masks (Panel B): BAPCPA 2005Q2–2008Q4 and 2020Q2–2021Q4 excluded in the
  primary run; included in a sensitivity.

Ship rule: REGIONAL ALERT if β > 0 with permutation p ≤ 0.05 in BOTH panels,
event-study pre-trend p ≤ 0.05 for regional onsets, out-of-sample MSE gain with
DM p ≤ 0.10, and β still positive with p ≤ 0.10 after the claims control → a
state heat map with WARN when a state's relative filing growth crosses the 90th
percentile of its historical distribution, carrying the measured hit and false-
alarm record. If the in-sample criteria pass but the OOS or claims checks fail →
display-only map with the record. If β is not positive and significant → map
labelled "confirms, does not lead".

### Q-C — comparison: bank delinquency and charge-offs

Same national rule and classification (θ grid as Q-N) on 4-quarter averages of
FRED bank delinquency rates DRALACBS, DRBLACBS (C&I), DRCLACBS (consumer),
DRCCLACBS (card), DRSFRMACBS (residential), DRCRELEXFACBS (CRE) and charge-off
rates CORALACBS, CORBLACBS, CORCCACBS. Scored peaks 1990 (where the series
exists), 2001, 2007 (bank rates are not BAPCPA-affected). ALERT-grade only if
LEAD 3 of 3 (or 2 of 2), ≤ 1 false alarm per decade, size p ≤ 0.10. Current
vintage only (no real-time vintages before 2012) — stated on any result. NY Fed
flows into 90+ delinquency (2003+): descriptive only (one non-exogenous
recession, reconstructed, not real-time).

### Secondary targets (report-only, never a ship criterion)

Equity bear markets (S&P composite monthly — Shiller through 2024-09, OECD
SPASTT01USM661N after — peaks of ≥ 20% declines since 1980) and Baa–10y spread
blowouts (BAA10YM 6-month rise ≥ 100bp, onset after ≥ 12 months below): the N1
and Q-C onsets classified against these events with a 12-month LEAD window.

### Data to complete before the run (mechanical; no scoring)

ABI district/state annual tables 1980–2000 (parse + national tie-out); FRED
{ST}POP, {ST}ICLAIMS, CPIAUCNS; BCD series 14 1953–1986 (text layer + FRED
overlap check + image check of mismatches); access audit, without creating any
account, of WARN advance-layoff notices (openICPSR E155161; Cleveland Fed) and
Challenger job cuts by reason (incl. "Bankruptcy") — if a usable monthly state
history exists openly, WARN joins Panel B as a candidate under the same tests;
if it needs a login, Casey is asked.

### What is built regardless of the scores

A Distress panel that shows, with each series labelled by its measured role
(leads / confirms / lags): national filings per capita vs history since 1980 and
y/y by type with law-change flags; large corporate bankruptcies (context); NY Fed
flows into 90+ delinquency by product (4-quarter-sum caveat); bank delinquency
and charge-offs; the state map. Alerts only for what passes its ship rule.

### Honesty, stated before the run

Few national episodes (2–3 scored); breaks remove 2007 from court-count tests;
current-vintage data except where stated; thresholds and windows chosen with
the literature in view (the grid shows sensitivity); the regional panel has
power but its effects may be small; multiple tests are reported in full, with the
primary specification fixed here.

---

## SPEC v1 — OPERATIVE. Amended 2026-10-12 after two counter-agent reviews, before any rule was scored

Both reviews BLOCKED v0 (log at the end). v1 adopts every blocking fix. Where the
reviews differed, the simulation-backed or stricter option is taken (noted). When
v1 was written no onset, lead/lag statistic, classification or regression had been
computed on real data; only structure, counts, ranges and tie-outs had been seen.
The ABI 1980–2000 state tables were still being parsed: the branches that depend
on what they contain are fixed below, before their content is known.

### 0. Shared definitions

- **NBER peaks/troughs:** 1969-12/1970-11, 1973-11/1975-03, 1980-01/1980-07,
  1981-07/1982-11, 1990-07/1991-03, 2001-03/2001-11, 2007-12/2009-06,
  2020-02/2020-04 (exogenous).
- **Release dating.** Every value is dated at the month it was first published;
  onsets, classification, leads and event times all use that date (last-month
  dating is a sensitivity only). AO/ABI quarterly filings, national and state:
  quarter end + 1 month. Annual filings: January of the next year (sensitivity
  +2; 1980–2000 release dates are undocumented). FRED bank delinquency/charge-off
  rates: quarter end + 2 months. BCD series 14: month + 2 (sensitivity +1). State
  and national UR and payrolls: month + 1. Claims: week-ending Saturday + 5 days.
  A LEAD requires release ≤ p − 1m.
- **Masks act on inputs.** Raw contaminated windows: BAPCPA 2005Q2–2008Q4 (all
  court counts); policy 2020Q2–2021Q4 (court counts, bank rates, and UR, claims
  and payrolls used as targets or controls); Q-C extras below. A derived value is
  masked if any raw period in its input footprint is masked or missing:
  4-quarter-sum/average growth reads t−7..t (court-count g masked 2005Q2–2010Q3
  and 2020Q2–2023Q3); 12-month-sum growth t−23..t; annual growth t−1..t (masked
  2005–2009 and 2020–2022).
- **Onsets.** First ON period after ≥ Q consecutive observed OFF periods
  (Q = 4 quarters / 6 months / 1 year). A spell ON at a series' first computable
  period is left-censored. A masked block RESETS the OFF counter (stats review;
  the carry-over rule of the data review is a sensitivity). Onsets suppressed by
  masks are listed in the honesty box.
- **Scorability.** A non-exogenous peak p is SCORED for a series only if the
  series has computable, unmasked values at every release month in
  [p − L − 12m, p − 1m] (L = 18m; Q-H 24m); PANEL grading also needs [p, p + 3m].
  A series with < 2 scored peaks cannot be ALERT or PANEL grade. The code derives
  each scored set from this rule; expected N1 and N2 = {1990-07, 2001-03}
  (1980/1981 have no lead-in; 2007 is masked), N3 = none.
- **Classification.** Each onset o is classified once, against the earliest
  peak p with trough τ ≥ o: LEAD if p − L ≤ o ≤ p − 1m; COINCIDENT if
  p ≤ o ≤ p + 3m; LATE if p + 4m ≤ o ≤ τ; FALSE ALARM if o < p − L. One LEAD per
  peak (its earliest). Onsets against an UNSCORED peak are listed, not counted.
  2020-02: a LEAD against it is a FALSE ALARM (sensitivity: excluded);
  COINCIDENT/LATE neutral. After the last trough (2020-04): FALSE ALARM if
  o + L ≤ T_N, else PENDING, with T_N = run month − 12 (Oct-2026 run: 2025-10, so
  18-month-window onsets after 2024-04 are PENDING — listed, never counted). No
  EARLY class: onsets in [p − L − 6m, p − L − 1m] are flagged "early" but scored
  FALSE ALARM. LIT-THROUGH(p): no LEAD/COINCIDENT onset for p, the last observed
  period before p − L is ON and every observed period in [p − L, p + 3m] is ON.
- **False-alarm rate:** per 10 years of unmasked, non-PENDING periods with
  computable values.
- **Size test.** O = the ordered computable, unmasked periods of the series'
  scoring support. Rotate the ON/OFF values circularly among the slots of O by
  k = q … |O| − q (q = 8 quarters / 24 months / 2 years); calendar, masks, scored
  set, PENDING cutoff and the 2020 convention stay fixed; identical scoring
  functions. Statistic (L, F) = (scored peaks with a LEAD, false alarms).
  p = (1 + #{k: L_k ≥ L_obs and F_k ≤ F_obs}) / (1 + R), R = |O| − 2q + 1.
- **Grades.** ALERT: LEAD at every scored peak, ≤ 1 false alarm per decade,
  Holm-adjusted rotation p ≤ 0.10 in its family, LEAD at every scored peak for
  ≥ 2 of the 4 grid values, plus each question's own conditions. PANEL
  ("confirms"): LEAD or COINCIDENT at every scored peak and ≤ 1 false alarm per
  decade; its rotation p is shown on the label. A series that LEADs every scored
  peak only under a robustness transform is capped at PANEL ("transform-sensitive",
  "trend-sensitive", "scale-sensitive"). An ALERT always shows its in-sample
  record: LEADs, false alarms, precision = LEADs / (LEADs + false alarms).
- **Multiplicity.** Shots at an ALERT/WARN: Q-N 2, Q-H 1, Q-R 2 (3 if WARN
  notices join), Q-C 9. Holm within families: Q-N at 0.10, Q-C at 0.10 (plus a
  descriptive Westfall–Young min-p on the common support), Q-R at 0.05. The
  honesty box lists every shot with raw and adjusted p and the simulated chance
  that at least one ships under the global null. Grids are robustness conditions,
  never searched.
- **Seeds:** every random draw uses seed 20261012, recorded in results.json.

### Q-N — national filings

- **N1** business filings: ABI quarterly 1980Q1–2025Q4 + AO F-2 3-month national
  first prints 2026Q1–Q2 (same vintage: Σ ABI quarters = Σ AO first prints in every
  year 2001–2025). Never ABI's annual table or the PDF's printed TOTAL column.
  1995 quarters sum 1,000 below the annual: unless a second source resolves it
  before the run, all four placements are scored and the grade uses the worst.
- **Chapter 12** (effective 1986-11-26): N1 is also scored as N1x (N1 minus
  calendar-year Ch 12 ÷ 4 in each quarter 1986Q4–2025Q4; 1986's 607 in 1986Q4)
  and N1s (N1x with 1987Q2 replaced by the mean of 1987Q1 and 1987Q3). 1990 is a
  LEAD only if it is a LEAD in all three.
- **N2** non-business, annual: ABI annual table 1980–2025 (a later vintage from
  2001 — acceptable at annual resolution). N2 quarterly (robustness): ABI
  1994Q1–2000Q4 + AO F-2 3-month first prints from 2001Q1 (removes ABI's 2010Q1
  and 2011Q1 typos).
- **N3** business Ch 11 (AO F-2): display only.
- **Rule:** g = s(t)/s(t−4) − 1 on 4-quarter sums; ON when g ≥ θ; θ = 10%, grid
  {5, 10, 15, 20%}.
- **Robustness (reported beside the primary):** single-quarter y/y; s(t) from the
  AO 12-month tables from 2001; N2 trend-adjusted e = g − median g of the prior
  20 unmasked quarters (5 years annual), ON when e ≥ θ.
- **Ship:** ALERT per §0, family {N1, N2}.
- **Stated now** (reviewer simulations, synthetic): the size test does not bind
  (perfect-rule min p 0.0078 N1, 0.029 N2); LEAD at both peaks with ≤ 3 false
  alarms does. ALERT passes 0.2–1.7% of nulls; power against a true 12-month lead
  (+35% in filings) is ~0.5 when g is smooth (SD ≈ 0.05), 0.14–0.20 at SD ≈ 0.09,
  < 0.05 at SD ≈ 0.18. The 4-quarter sum delays the signal 1–2 quarters, so a true
  lead of ≤ 6 months is expected to score COINCIDENT. A non-ALERT is not evidence
  that filings do not lead.
- **Descriptive:** cross-correlation of g with the 4-quarter change in UR at
  −8…+8 quarters, with a 90% band from the same rotations; no lead is described
  unless the peak correlation is outside the band.

### Q-H — D&B failure liabilities, out of sample 1967–1983

- **Data:** BCD series 14 (BCD June 1987, App. C p.97), monthly 1953-01..1986-12,
  NSA, $ millions, Dun & Bradstreet. Validation done before v1: all 408 months
  read from the page image; printed quarterly (136/136) and annual (34/34) totals
  tie; FRED M0933C overlap 181/181 within 0.05 (7 x.x5 ties print half-down);
  ERP-2004 B-96 annual totals: printed totals within ±0.1, monthly sums within
  ±0.2 in 1955–1984 (1985 −23 vintage, 1986 −1,575 preliminary; both outside
  the window). Independent verifier: PASS (408/408 months re-read). Real = deflated by CPI-U NSA;
  robustness PCEPI (1959+) and nominal. 1987 BCD vintage, not real-time.
- **Rule:** g = 12-month sum / its value 12 months earlier − 1; ON when g ≥ θ_H;
  θ_H = 25%, grid {15, 25, 40, 60%}; Q = 6 months; L = 24 months.
- **Single-month attribution:** for each onset o, recompute g(o) with the largest
  real month in [o−23, o] replaced by the median of the other 23; if it falls
  below θ_H the onset is SINGLE-MONTH DRIVEN — a FALSE ALARM if so classified,
  never a LEAD.
- **Winsorized variant (required):** each month capped at 3× the median of the
  prior 24 months before summing; the ship decision must also hold under it.
  Sensitivity: 2.5× cap.
- **OOS window** 1967-01..1983-12: peaks 1969-12 and 1973-11 (clean), 1980-01 and
  1981-07 (flagged: the 1978 Code took effect 1979-10).
- **Ship:** attribution-checked LEAD at BOTH clean peaks AND at ≥ 1 flagged peak;
  ≤ 2 false alarms in 1967–1983; median lead ≥ 6 months (release-dated); rotation
  p ≤ 0.10 (R = 157, min p 0.0063); the same LEAD pattern for ≥ 2 of 4 θ_H values;
  and the winsorized variant passes too.
- **Stated now:** LEAD windows cover 83 of the 204 OOS months; synthetic nulls
  pass ~5% with the size test; power against a strong 12-month lead is 0.11–0.21,
  so a fail is weak evidence of no lead.
- **Replication (descriptive):** Bry–Boschan on the centered 12-month moving
  average of real liabilities (min phase 6, min cycle 15; phase 15 as
  sensitivity); each business peak matched to the latest liabilities trough in the
  prior 36 months; lead = peak − trough; turns of the trailing sum alongside.
- **Context runs (not decisive):** the same rule on 1894–1938 (M0933A) and
  1948–1966, masking any g whose 24 input months touch a D&B break (1933
  redefinition, Jun-1934–1939 77-B segment, 1939–40 coverage expansion); 1907
  and 1930–33 flagged (bank failures included).
- **Modern analogue:** only if Q-H ships. FJC IDB Ch 11 scheduled liabilities,
  scored for false alarms (same rule, attribution check) from its first computable
  g (2009-09) to T_N − 24m with the 2020 convention: WARN only if ≤ 2 false alarms
  per decade, else context with the count shown.
- **Meaning:** trade and bank debt of failing commercial and industrial firms
  (excludes banks, railroads, real estate, insurance, finance, and publicly held
  long-term debt) — not a bond-market distress measure.

### Q-R — do filings rising in a STATE precede that state's job losses?

- **Units:** 50 states + DC = sum of districts by postal code (AR = ARE + ARW before
  2018Q3); PR, VI, GU, MP excluded. "National" = the sum of the 51. β reads: a
  state doing worse than the average state.
- **Signals:** S1 non-business filings (primary). S2 business filings (secondary):
  Panel B business Ch 7; Panel A business Ch 7 if the tables report it, otherwise
  all-chapter business filings, labelled so, with 1987 and 1988 masked (Ch 12
  ramp). DE is excluded from every S2 analysis (venue filings).
- **g:** log((S(t) + 0.5)/(S(t−4) + 0.5)) on case counts (S = 4-quarter or annual
  sum), winsorized at the 1st/99th percentile of each period's cross-section. S2
  regressions weighted by 1/(1/S(t) + 1/S(t−4) + v), v = cross-state median of
  within-state var(g) net of its Poisson part (floor 0.0025); S1 unweighted.
  Per-1,000 rates for display only (FRED {ST}POP, July-1 estimates placed at
  July 1, interpolated; extrapolated at the 2024–25 growth rate after 2025Q3).
- **Panel A — annual, origins 1981–2000.** Filings: ABI-hosted AO district tables
  (1980–99 five-year blocks; 2000 from the 1998–2000 quarterly consumer table and
  the 1990–2006 business table). Tie-out before use: Σ districts within 0.1% of
  ABI's annual table, business and non-business separately, every year. If the
  tables are years ending 30 June, predictors are dated June and targets and
  controls use Q2 averages instead of Q4. Targets: (a) ΔUR = mean UR Oct–Dec(t+1)
  − mean Oct–Dec(t) (FRED {ST}UR); (b) job losses = −[ln E Q4(t+1) − ln E Q4(t)],
  E = state nonfarm payrolls NSA (FRED {ST}NAN), Q4 averages; DC excluded from (b)
  (its payrolls count MD and VA residents). Controls: ΔUR Q4(t) − Q4(t−1) and
  Δln E Q4(t−1)→Q4(t) (the coincident labour-market control); claims growth added
  for 1988–2000 as a robustness (state claims start 1986).
- **Panel B — quarterly.** Filings: s(state, t) = the AO F-2 12-month table issued
  for quarter t (first-published 4-quarter sums, revisions to t−3…t−1 folded in),
  2001Q1–2026Q2. S1 extended back with ABI's quarterly non-business-by-district
  tables 1996Q1–2000Q4 (g from 1997Q4) only if their national sums tie to ABI
  quarterly non-business within 0.1% in every quarter; S2 g from 2002Q1.
  Robustness: summed 3-month first prints. Targets: (a) ΔUR(t → t+4) on quarterly
  averages; (b) −Δln E(t → t+4) (NSA payrolls, same-quarter differences).
  Controls (primary): ΔUR(t−4 → t), ΔUR(t−1 → t), UR(t), Δln E(t−4 → t), and state
  initial-claims growth (DOL ETA 539, column c3, state UI initial claims; mean
  weekly claims over the 4 quarters to t vs the 4 before, weeks assigned by their
  week-ending Saturday) plus latest-quarter claims y/y. Quarterly UR averages need
  ≥ 2 of 3 months (2025-10 is never interpolated). An origin (s, t) is dropped if
  g's footprint t−7..t meets a filings mask or the target (t, t+4] or LDV
  (t−4, t] meets 2020Q2–2021Q4.
- **Model (both panels):** y(s, t→t+h) = α_s + δ_t + β·g(s, t) + controls + ε.
- **Primary inference** (stats review; v0's per-period shuffle rejected a true null
  18–26% of the time, whole-history state permutation 13–14% under regional
  shocks): wild-cluster restricted bootstrap by Census division (9 clusters, DC in
  South Atlantic; Webb six-point weights; β = 0 imposed; t = β̂ / CR1
  division-clustered SE; 9,999 draws; one-sided p = (1 + #{t* ≥ t}) / 10,000).
  Required co-check: division × period FE model, Freedman–Lane permutation of
  whole residual histories WITHIN divisions (studentized, state-clustered, 9,999
  draws), p ≤ 0.10. Reported, not decisive: state-clustered, two-way clustered and
  Driscoll–Kraay (bandwidth 2h) SEs.
- **Bias and regional checks (β > 0 required in every one):** split-panel
  jackknife β_BC = 2β̂ − (β̂₁ + β̂₂)/2 (Panel A halves 1981–90 / 1991–2000; Panel B
  split at the median usable origin); leave one division out (9 refits); excluding
  origins within [p − 12m, τ + 12m] of national peaks; excluding AK, LA, ND, NM,
  OK, TX, WY in 2014Q3–2017Q4; adding state loadings on the national cycle
  λ_s·ΔUR_US(t → t+h). Sensitivity: no state FE.
- **Event study (Panel B).** Events: state Sahm-style onsets (3-month average UR
  minus the minimum of its prior 12 months ≥ 0.5pp; ≥ 12 months since the last
  onset), dated to the quarter of the onset month; REGIONAL = outside
  [p − 12m, τ + 12m] of every national peak. Outcome r(s, q) = log(S(q)/S(q−4))
  minus the mean of the same over the other 50 states. An event enters only if
  quarters −12..+4 are unmasked. D_F = mean over events of [mean r(−4..−1) −
  mean r(−12..−9)]; p from 9,999 placebo dates (same state, ≥ 8 quarters from all
  its onsets, complete window); cluster-robust t with episode clusters reported.
  Claims benchmark D_C computed identically for state initial claims, both in units
  of the state's own SD of r. Criterion: D_F p ≤ 0.05 AND D_F − D_C > 0 with
  p ≤ 0.10 (filings must warn earlier than claims). Testable only with ≥ 8
  regional events in ≥ 4 distinct onset years; otherwise not testable and a
  REGIONAL ALERT is unavailable. Descriptive only: the same plot anchored at the UR
  trough, and UR's own relative path.
- **Out-of-sample (Panel B, target a).** Expanding window: at each origin t from
  2015Q1 to 2025Q2 estimate on usable origins ≤ t − 4 and forecast the relative
  target (state minus cross-state mean; predictors demeaned); benchmark = the same
  model without g. Clark–West adjusted MSPE averaged across states per origin;
  one-sided t with Newey–West (4 lags) and the HLN correction, t(n−1) critical
  values; MSE ratio reported. ~24 usable origins: a non-rejection is labelled
  uninformative, not negative.
- **Reverse direction (reported):** g(s, t → t+h) on ΔUR(s, t−h → t), with
  g(s, t−h → t) and the same FEs.
- **Ship, per signal.** REGIONAL ALERT only if, in BOTH panels and for BOTH
  targets: β > 0 with the primary p passing Holm at 0.05 across signals (a
  signal's decisive p = its largest primary p over panels and targets), co-check
  p ≤ 0.10, and every bias/regional check β > 0; AND the event-study criterion is
  testable and met; AND Clark–West p ≤ 0.10. Then a state map whose WARN is itself
  scored before shipping: z(s, t) = (r − mean)/SD over the state's own history to
  t−1 (expanding, ≥ 20 usable quarters); WARN onset when z ≥ 1.28 after ≥ 4
  quarters below, only if the base 4-quarter count is ≥ 50 (S2) / 500 (S1); HIT if
  a state Sahm-style onset follows within 4 quarters, else FALSE ALARM; the map
  shows WARN only if the hit rate beats the unconditional 4-quarter onset rate with
  p ≤ 0.05 (within-division whole-history permutation of the WARN series, 9,999).
  If the in-sample criteria pass but the event study or OOS fails: display-only
  map with the record. If β is not significant the map reads "no evidence of a
  lead" (power stated); the label "confirms" needs the same-window relation
  (g vs ΔUR(t−h → t)) positive with p ≤ 0.05 under the primary inference.
- **WARN advance-layoff notices** (only if Casey authorizes the ICPSR login; the
  open alternatives are too thin before 2010): S3 in Panel B under the same tests,
  with a per-state coverage mask.
- **Stated now:** Panel B has ~51 usable origins (~13 non-overlapping years; more
  if the 1996 extension ties out), OOS ~24. A REGIONAL ALERT needs ≥ 5
  conjunctive criteria on that sample, so a display-only map is the likely outcome
  even if a moderate real lead exists.
- **Flags (not masks):** BAFJA (1984-10-08), 1994 Act (1994-10-22), Ch 12 lapse
  (2004), state exemption opt-outs 1979–83 (Panel A sensitivity dropping
  1981–83), H.R. 7730 (flag on the live map).

### Q-C — bank delinquency and charge-offs

- Series: DRALACBS, DRBLACBS, DRCLACBS, DRCCLACBS, DRSFRMACBS, DRCRELEXFACBS,
  CORALACBS, CORBLACBS, CORCCACBS. 4-quarter averages; g = avg/avg(−4) − 1; ON when
  g ≥ θ AND the average rose ≥ 0.10pp (delinquency) / 0.05pp (charge-offs) over the
  4 quarters (θ grid as Q-N). Release dating + 2 months.
- Masks (footprint rule): policy 2020Q2–2021Q4 (all); FAS 166/167 at 2010Q1 for
  DRCCLACBS, CORCCACBS, DRCLACBS, DRALACBS, CORALACBS; BAPCPA charge-off rush
  2005Q3–2006Q4 for CORCCACBS (so its 2007 is unscored). Flag: 2001Q1 Call Report
  reform — type-specific series' 2001 classification also reported without the g
  values for 2001Q1–2002Q3, and for C&I on DRBLT100S.
- Robustness: point-in-time y/y of the rate; a pure percentage-point rule
  (θ_pp ∈ {0.10, 0.25, 0.50, 1.00}); a series passing only in pp terms is capped
  at PANEL ("scale-sensitive").
- ALERT per §0, family = the 9 series. Current vintage only (no real-time
  vintages before 2012), stated on any result. NY Fed flows into 90+ delinquency:
  descriptive only.

### Secondary targets (report-only, never a ship criterion)

S&P 500 bear markets (≥ 20% close to close), pre-listed: peaks 1980-11, 1987-08,
2000-03, 2007-10, 2020-02, 2022-01 (1990-07 fell 19.9% — not counted). Baa–10y
blowouts: BAA10YM 6-month rise ≥ 100bp, onset after ≥ 12 months below (dated from
the data before any filing series is classified against them). N1 and Q-C onsets
classified against both with a 12-month LEAD window.

### Run order

1. Data: ABI district tables (agent, tie-out per Q-R) and an independent check of
   the BCD extraction; FRED {ST}POP, {ST}NAN, CPIAUCNS, PCEPI, DRBLT100S and DOL
   ETA 539 fetched 2026-10-12.
2. Power/size check of the v1 code on synthetic series: it must reproduce the
   reviewers' calibration (perfect-rule min p, ALERT null pass rate, Q-R inference
   size) within simulation error before the run.
3. One run: `distress_signals/study.py` → `results.json`.
4. Two independent verifiers, honesty box, charts; the Distress panel labels each
   series leads / confirms / lags per its grade; alerts only for what ships.

### v1.1 — errata and data branches, fixed 2026-10-12 BEFORE the run

- **Erratum (transcription):** the Q-R event-study onset rule reads "≥ 12 months
  since the last onset" in v1; the rule carried from v0 and intended by both
  reviews is "onset = first lit month after ≥ 12 unlit months". The code uses the
  v0 wording.
- **Panel B S1 extension not used:** ABI's quarterly non-business-by-district
  page for 1998–2000 is truncated at source (42–43 districts, no US row), so the
  pre-registered tie-out cannot pass; S1 g starts 2002Q1 like S2.
- **Panel A S2 = all-chapter business filings** (DE excluded, 1987–88 masked):
  no ABI-hosted table splits business filings by chapter before 2001 (data agent:
  132 ABI stats items scanned). The 1980–2000 district panel ties exactly to
  ABI's national totals after 38 transcription errors in the ABI pages were
  corrected from independent ABI printings (independent check pending).
- **Power/size of the v1 code** (`distress_signals/power.py`, synthetic only):
  engine identical to the reviewer's replica on 300/300 series;
  perfect-rule min p N1 0.0078 (R=128), N2 0.0286 (R=34),
  Q-H 0.0063 (R=157). N1 ALERT under the null 0.003 / 0.025 /
  0.018 (SD of g ≈ 0.05 / 0.10 / 0.20); power against a true 12-month lead
  (+30% log ramp) 0.27 / 0.16 / 0.05 — lower than the
  reviewer's 0.50 because release dating moves the last pre-peak quarter to
  COINCIDENT. Q-R: division wild-cluster bootstrap size 0.050 and
  within-division Freedman–Lane 0.050 with regional shocks; Panel A
  design when filings only track TRUE unemployment measured with 0.2/0.4pp
  noise: 0.075/0.065 with the coincident payroll control, 0.99/1.00
  without it — so Panel A p-values run slightly optimistic (≈ 7% at a nominal 5%).

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| statistics (2026-10-12) | BLOCK — 6 blocking, 17 should-fix, 7 notes; synthetic simulations: v0 Q-R shuffle size 17.7–26.3%, Panel A annual-average target passes a coincident series 92%, Q-H without a size test passes 8.7–14.5% of nulls | all; inference = division wild-cluster bootstrap + within-division Freedman–Lane; Q4-to-Q4 targets with coincident controls; Clark–West OOS; event study with claims benchmark; Holm families |
| data & measurement (2026-10-12) | BLOCK — 10 blocking, 10 should-fix, 5 notes: 1981 unscorable, masks miss g's 8-quarter footprint, no release dating, Ch 12 1987Q2 base effect, BAPCPA hits card charge-offs, Panel A business Ch 7 likely absent, BCD check covered 13 of 204 OOS months | all; its state-label permutation and trough-dated event study superseded by the stats review's (simulated) versions; its mask carry-over kept as a sensitivity |
