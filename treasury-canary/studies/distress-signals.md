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

## SPEC v0 — pre-registered 2026-10-12, BEFORE any lead/lag rule is scored

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
