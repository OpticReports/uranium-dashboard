# Oil shocks and recession odds — how much weight does oil deserve? (spec v1, pre-registered)

**Status: RESULTS APPENDED 2026-09-16 (see "RESULTS" below the spec).** Spec v1 was amended
2026-09-15 from the counter-agent panel's review of v0, before any result was computed; §2–§5
are frozen as of that date and every later amendment is logged with its date and reason in §8
entry 2. v0 is preserved in git (commit 2f710ab). Headline: the pre-registered decision rule
for "oil adds weight to the recession odds" was NOT MET on both targets; the §5 rows executed
are listed at the end of the results.

## 0. Why this study

Casey (2026-09-15): we are in an oil shock / elevated-oil regime; the canary scores oil on
the pin board; how is oil's contribution to RECESSION ODDS weighted, have we backtested
prior oil-shock regimes, and what weight should it get given that "all indicators are not
equal — some are larger markets with larger effects" and "we're on a petrodollar system"?

## 1. What the canary does with oil today (audit of the deployed instrument)

| Where | What oil does | Weight in recession odds |
|---|---|---|
| Recession dial (`/recession-model`) | nothing — horizon probits on the 3m10y spread only (plus a term-premium-adjusted twin) | **0** |
| Pin board `oil_shock` channel (`pins.py`) | WTI 12-month % change (last daily print vs 252 trading days earlier); anchors 0 / +25 / +50 / +100 (benign / yellow / red / extreme — the +100 extreme was set by inspecting 1973/79/2022); mass $20T (household consumption), speed 3–12m, kill rate "preceded ~10 of 11 postwar recessions (Hamilton)" | none — static badges, "never fitted" by design |
| Pin history / damage windows (`pin_history.py`) | red episodes cast a 3–12 month window forward (Hamilton lag) | none |
| Accident composite hindcast (`studies/pin-rule-hindcast.md` v3) | measured an **oil-OR-policy window** rule bundled with `policy_shock`: +curve 45% / 5-of-6 on drawdowns, 37% / 4-of-4 on onsets | oil never isolated |
| Flow compass (`flows.py`) | oil's 20d return as a regime discriminator (supply shock vs demand fear) | none |
| Prior probit-augmentation test (glossary `transmission_note`, `pins.py` NFCI horse race) | a financial-conditions index added nothing walk-forward → "the calibrated probability is never adjusted" | oil was not tested |

So: **no standalone oil backtest has ever been run**, the deployed oil history starts in
1986 (FRED `DCOILWTICO`), so the 1973, 1979–80 and 1990 shocks — the whole basis of the
Hamilton kill-rate claim — have never been in-sample for this instrument, and oil's weight
in the recession odds is zero by construction.

## 2. Questions (fixed before measurement)

- Q1. Is an oil shock, on its own, a usable recession signal on the full postwar record —
  precision vs base rate, lead times, and named false positives?
- Q2. Does oil add information BEYOND the yield curve, out of sample (the weighting question)?
- Q3. Has the relationship changed by regime — regulated/OPEC era, market pricing, shale, US
  net-petroleum-exporter — and has oil's EFFECT SIZE shrunk with its share of spending (the
  "bigger market, bigger effect" claim, tested directly)? Supply- vs demand-driven shocks?
- Q4. Petrodollar thesis, as two falsifiable hypotheses: H4a recycling (oil up ⇒ oil-exporter
  Treasury demand up); H4b transmission (oil co-moves with the dollar and foreign-official
  custody with a regime-dependent sign).
- Q5. What does the instrument read RIGHT NOW under each definition?

**Primary tests (one per question; everything else is SECONDARY and cannot trigger a §5
action):** Q1 = D1, h = 12, NBER onsets, episode level, common window. Q2 = the decision
test in §4 (h = 12, 12m % change winsorised, both targets). Q3 = effect-size-by-regime line
in §4. Q4 = H4a and H4b sign tests as written. Q5 = the three dated readings.

## 3. Data (all public, keyless; frozen copies in the study's data folder)

| Series | Use | Coverage | Caveat |
|---|---|---|---|
| FRED `WTISPLC` monthly spot WTI | PRIMARY oil series for D1/D2/D3 | 1946-01+ | pre-1981 prices are posted/regulated (14 distinct levels 1947–73; unchanged in 93% of pre-1973 months). The October-1973 embargo appears only as the 1974-01 step (+184%) |
| FRED `WPU0561` PPI crude petroleum | Hamilton's own series; every pre-1983 statistic is re-run on it as a NAMED robustness row | 1947-01+ | shows the 1973 shock at 1973-12 (+27.5%) — one month earlier than WTISPLC; the 1979–81 run ends 1981-11 (post-decontrol) vs 1980-09 |
| FRED `DCOILWTICO` daily WTI | (i) monthly mean; (ii) the deployed construction — last print of the month vs the print 252 trading days earlier | 1986+ | WTISPLC monthly mean vs DCOILWTICO monthly mean: 12m-change diff mean 0.01pp, max 2.0pp, zero D1 grade disagreements 1987–2026 (data audit) — the source is interchangeable; the POINT-vs-MEAN construction is not (grades differ in 7.4% of month-ends) |
| FRED `DGS10`, `DGS3MO` daily | rebuild the deployed "curve flat" rule (min 3m10y over trailing 183 days < 0.25) at each month-end | 1982+ | agreement check vs the monthly rule; disagreement months named |
| FRED `GS10`−`TB3MS` = `spread_gs` | THE curve series for every fit, condition and episode rule, ONE basis 1953-04+ | 1953-04+ | bills on discount basis: understates bond-equivalent yield 20–40bp (BACKTEST.md). Never spliced |
| FRED `T10Y3M` (CMT) | Q5 live reading only + a 1982+ agreement footnote | 1982+ | CMT − (GS10−TB3MS) on 1982–2026: mean −0.12pp (1980s −0.29, min −0.80); the flat condition differs in 17 months |
| FRED `CPIAUCSL` | real oil (D3) | 1947+ | 2025-10 missing at source (shutdown) — log-linear interpolation, flagged in the panel |
| FRED `USREC` | NBER recession months → onsets | full | final dating; NBER announces peaks 4–12 months late (dates in §4) |
| FRED `FEDFUNDS`, `INDPRO`, `UNRATE`, `PAYEMS` | policy pace (sibling channel); context only | 1954+/1919+ | INDPRO revised; NOT used for the supply/demand split |
| Dallas Fed IGREA (Kilian index of global real economic activity) | cross-check for the supply/demand split | 1968+ | monthly xlsx, keyless |
| FRED `DNRGRC1M027SBEA` / `PCE` | energy share of consumer spending (%), for the effect-size-by-share test | 1959+ | nominal PCE energy goods & services ÷ total PCE; a consumption share, not GDP |
| Yahoo `^GSPC` daily → monthly close/low | ≥15% drawdown starts | 1927-12+ (pulled from 1950 for events) | B1 = running-peak construction (`pin_history._drawdown_spans`); B2 = local-peak construction: a span closes when the close regains the peak OR sits ≥15% above the trough having retraced ≥50% of the decline, and the next local peak restarts from there (adds 1976-12, 1980-01, 2011-04; bear-market rallies of 35–49% retracement in 2001–02 and 2008 do not open new spans). Both frozen in events.json before scoring |
| FRED `WMTSECL1` Fed custody (weekly → monthly) | H4b, named-episode series only | 2002-12+ | all foreign official; oil exporters are a small share — a null here is weak evidence |
| FRED `DTWEXM` (1973–2019) ratio-spliced onto `DTWEXBGS` (2006+) at the 2006 overlap | H4b broad dollar | 1973+ | index-base splice, documented in the panel |
| TIC Major Foreign Holders history (`mfhhis01.txt`) | H4a: seg1 "Oil Exporters" aggregate 2000-03..2011-12 (footnote basket; Norway NOT in it); seg2 Saudi + UAE + Kuwait 2012-01+ (basket3; +Iraq where listed as basket4). Norway reported separately, never summed. SHARE of grand total used, not $ | 2000-03+ | TIC = custodian country: Gulf holdings via Belgium/UK/Cayman/Luxembourg custodians are unobserved, so recycling is UNDER-stated. Benchmark breaks each June 2002–2011: revised June kept; 12m changes never straddle a segment break. Values at market price. Pre-2000 not available (`mfhhis02.txt` 404) — Q4 cannot see 1973/79/90 |
| Brent `DCOILBRENTEU` | footnote only: D1 on Brent 1987+ (2011–14 WTI–Brent dislocation) | 1987+ | not in any test |

Frozen inputs: `panel.csv` (monthly macro, truncated at the last COMPLETE month of WTISPLC =
2026-08), `events.json`, `tic_oil_exporters.csv` (two unspliced segments). The panel's
spliced curve column is named `spread_spliced_do_not_fit` and is used by nothing.

## 4. Pre-specified definitions (no threshold search)

Oil-shock definitions (WTISPLC monthly mean; PPI companions for pre-1983):
- **D1 — monthly-mean analogue of the deployed rule.** 12-month % change ≥ +25 (YELLOW),
  ≥ +50 (RED). The live channel reads a daily 252-observation point change; on 1987–2026
  month-ends the grades differ in 7.4% of months (10 live-RED/panel-not, 7 reverse) — an
  instrument-agreement table is reported BEFORE any result, and if month-level on/off
  agreement is < 90% the daily construction replaces the monthly one for the overlap.
- **D2 — Hamilton net oil price increase, 12-month cumulative (NOPI12).**
  nopi_t = max(0, log P_t − max(log P_{t−36..t−1})) in log-pct (the monthly net increase over
  the prior 3-year max); S_t = Σ_{k=0..11} nopi_{t−k}. D2 is ON when S_t ≥ +10. S_t is also
  the probit regressor. The monthly spike is kept in the panel as a diagnostic only. The ≥10
  cut-off is this spec's choice (Hamilton never dichotomises); Q5 reports D2 at 8 / 10 / 12
  with 10 as headline.
- **D3 — real oil.** WTI/CPI 12-month % change ≥ +25 / ≥ +50 (same anchors as D1).
- **Curve flat** (fit series): min `spread_gs` over the trailing 6 months < +0.25pp. The
  deployed daily-183-day rule is rebuilt for 1982+ and agreement reported.
- **Regimes, by SIGNAL month:** R0 1947–1985 (regulated/OPEC; the boundary is the daily
  series' start and the 1986 OPEC price war, not decontrol — controls ended 1981-01 and
  1981–85 is a transition), R1 1986–2008, R2 2009–2019 (shale), R3 2020-01+ (EIA first
  net-petroleum-export year 2020; first monthly net-export print 2019-09). R3 contains NO
  scoreable onset (the 2020-03 lead window lies in R2); its rows report only false
  positives / pending episodes. **2022 is pre-declared a FALSE POSITIVE under D1, D2 and D3
  at both horizons** (all three fired; no recession within 18m).
- **Supply vs demand (descriptive, cannot trigger a §5 action):** supply-driven = episode
  starts within 3 months after a pre-listed exogenous disruption (Hamilton 2011 narrative
  list: 1973-10 embargo, 1978-11 Iran, 1980-09 Iran–Iraq, 1990-08 Kuwait, 2002-12 Venezuela /
  2003-03 Iraq, 2011-02 Libya, 2019-09 Abqaiq, 2022-02 Ukraine, and the 2026 event as
  named by Casey — P1 question in §7); demand-driven = every other episode; cross-checked
  against IGREA 12m change above its trailing-10-year median. INDPRO is context only.

Event sets: NBER onsets — 12 (1948-12 … 2020-03); curve-conditioned statistics score 10
(1957-09 onward; 1953-08 has 4 months of curve history and is listed NOT TESTABLE, never a
miss). Walk-forward OOS positives: 7 onsets 1973-12..2020-03 (1970-01 coincides with the
first prediction month and is excluded). Drawdowns: B1 running-peak from 1950 (headline), B2
local-peak (second). An event is evaluable for recall only if all h months before it lie
inside the data window; non-evaluable events are named and excluded from the denominator.

Horizons: 12 months (headline, matches the dial) and 18 months (Hamilton's 3–12m lag can
straddle the 12m cutoff; reported second, never used to rescue a miss).

Timing and episode rules (fixed now):
- A rule ON at month m claims events in m+1..m+h only (the hindcast/`build_dataset`
  convention). Recall counts an event as caught only if an ON month exists in [e−h, e−1].
- Month-level precision and episode hit rates use ON months with USREC_t = 0 only;
  in-recession ON months are listed but excluded from numerator and denominator.
- **Episode** = maximal set of ON months (USREC_t = 0) in which consecutive ON months are
  separated by ≤ 6 OFF months (mirrors the channel's 3–12m damage window); start = first ON
  month; applied identically to D1, D2, D3. A hit = an event begins in (first ON, last ON + h].
  Each event is credited to at most ONE episode (the earliest). Expected episode lists per
  definition are printed BEFORE outcomes are attached.
- **Coincident** = an episode whose first ON month is the onset month or within 3 months after
  it: its own named category, counted as neither hit nor false positive in precision, and as
  NOT caught in recall. Pre-declared expectation: the 1973-12 onset is coincident/missed under
  every definition on WTISPLC (first ON month 1974-01) and on WPU0561 (first ON 1973-12), and
  1990-08 is coincident (shock month = onset month). The Hamilton "10 of 11" count is
  therefore not reproducible from this instrument for 1973 and the measured kill_rate will say so.
- **Double-dip:** 1981-08 is scored against ON months in 1980-08..1981-07 only (after the
  1980 recession ended) and named as such.
- **Resolved:** a month t is resolved for horizon h only if t + h ≤ 2025-08 (last USREC print
  minus 12). Unresolved months are excluded from precision denominators, OOS scoring and base
  rates; episodes containing them are PENDING and named.
- Common windows: NBER comparisons across D1/D2/D3 on 1953-04..last resolved; drawdowns on
  1950-01+ (B1). One base rate per window/horizon.

Probits (all monthly, sample 1953-04+, `spread_gs` as the curve):
- Target A (deployed): y_t = 1 if USREC = 1 in any month t+1..t+h — stated so numbers match
  `/recession-model`. Target B (onset-lead): identical, but every month with USREC_t = 1 is
  EXCLUDED from fitting and scoring; (a) is refit on the same restricted sample so (a) vs (b)
  is like-for-like. Both targets are reported for every row; the decision rule must be met on
  BOTH — meeting it only on Target A is recorded as "coincident information only", no weight.
- Specifications: (a) curve only; (b) curve + oil; (c) oil only; (d) curve + Fed-funds 12m
  change (the sibling slow-lethal channel); (e) curve + oil + Fed funds. Oil enters once as
  the 12m % change winsorised to [−100, +100] (the deployed anchor cap) — the DECISION
  specification — and once as NOPI12 (confirmatory).
- Horizons 6 / 12 / 18 / 24; report coefficient, Newey–West HAC z (lag h − 1; naive IRLS z
  not reported), in-sample AUC, McFadden pseudo-R². Estimator: statsmodels Probit (Newton,
  maxiter 100).
- Walk-forward: expanding window, refit every month, first prediction 1970-01 (primary
  window) and 1986-01 (pre-declared secondary, market pricing; shown beside, never decides).
  Training rows at origin T are those with t + h + L ≤ T, where L is the NBER announcement
  lag — actual announcement dates for peaks 1980-01 (1980-06-03), 1981-07 (1982-01-06),
  1990-07 (1991-04-25), 2001-03 (2001-11-26), 2007-12 (2008-12-01), 2020-02 (2020-06-08); L =
  12 months for pre-1979 peaks and for trough-side labels. ΔAUC is reported with and without
  L so the size of the leak is visible. A refit that fails to converge inherits the previous
  month's coefficients (logged); a refit with < 24 non-zero oil training months is
  NON-IDENTIFIED and (b) falls back to (a)'s forecast for that month (counted, never
  dropped). Probabilities clipped to [0.01, 0.99] for the log-score; (a) and (b) share every
  clip. Scores: OOS AUC, Brier (decision), log-score (descriptive).
- Uncertainty: moving-block bootstrap on the paired triples (p_a, p_b, y), block length 36
  months (≥ h + median recession length), 1,000 draws, seed 20260915 → 90% interval for ΔAUC
  and ΔBrier; reported beside a cycle bootstrap that resamples whole peak-to-peak business
  cycles (n ≈ 7), the honest effective sample.
- **Decision rule for "oil adds weight" (fixed now):** evaluated at h = 12 only, on the
  decision specification, on identical OOS months 1970-01..last resolved, on BOTH targets.
  MET iff ΔAUC ≥ +0.02 AND its 90% block-bootstrap interval excludes 0 AND ΔBrier < 0 with
  its 90% interval excluding 0 AND the oil coefficient is > 0 in ≥ 90% of refits from
  1986-01 onward and in the final refit. Point ΔAUC ≥ 0.02 with an interval including 0 =
  SUGGESTIVE, NOT MET. NOPI12 passing while the 12m % change fails triggers only the
  channel-trigger row, never the odds row. h ≠ 12 passing alone = descriptive note.
- Conditional cut (descriptive): oil's precision and (b)'s marginal effect separately on
  months with `spread_gs` > +0.25 (curve not flat) and ≤ +0.25, plus the oil–spread
  correlation within each regime block (full-sample correlation is only −0.13; the
  collinearity is local to 1974 and 1979–80).
- Marginal effects, reported regardless of the decision: ΔP(12m) for a +50% oil shock at
  spread = 0 and +1pp, from the LAST walk-forward refit (the model the decision was made on),
  next to ΔP for a +300bp hiking pace from (e). **Effect-size-by-regime (Q3 primary):** the
  (b) coefficient and ΔP for +50% oil fitted separately on R0+R1 and on R2+R3 (Target B),
  and an interaction oil_12m × energy_share_pct on 1959+. If the R2+R3 marginal effect is ≤
  half the R0+R1 effect, the honesty box states that the bigger-market argument currently
  cuts AGAINST oil's weight and `mass_trillions` is re-labelled to the petroleum bill.
- Petrodollar (Q4): H4a — sign(corr(12m Δoil %, 12m Δ share of grand total)) > 0 on
  non-overlapping annual observations in BOTH seg1 (2000–2011, n ≈ 11) and seg2 (2012+, n ≈
  13), and the 2022 spike shows a 12m rise in the seg2 share; any leg failing = recycling
  link NOT supported in the last shock. H4b — sign(corr(12m Δoil %, 12m Δusd_broad %)) and
  sign(corr(12m Δoil %, 12m Δcustody %)) by regime R1/R2/R3 with block-bootstrap (block 12)
  90% CIs; pre-stated supporting signs: net importer (R1, R2) oil↑ ⇒ USD↓ (negative);
  net exporter (R3) oil↑ ⇒ USD↑ (positive). A CI straddling zero in R3 = thesis not
  supported in the current regime. Custody: named episodes only (2014–16, 2022). Signs are
  findings; magnitudes are not.
- R3 descriptive tests: 12m-ahead response of INDPRO and PAYEMS to the 2022 episode vs the
  mean response to R0/R1 supply episodes (named-episode chart).
- Q5: three dated readings — live daily channel (252-obs), monthly-mean latest complete
  month (D1/D3), NOPI12 (D2 at 8/10/12) — plus named analog episodes. **If the decision rule
  is NOT met, no in-sample marginal effect is ever applied to today's spread.**

Figures (fixed now): (1) nominal and real oil 1947+ with NBER bands, each definition's
episodes marked hit / false positive / coincident / pending; (2) walk-forward rolling OOS
AUC (a) vs (b) with bootstrap band; (3) reliability diagram (a) vs (b), h = 12; (4)
per-episode lead-time strip, three definitions; (5) oil vs oil-exporter share and custody,
seg1 and seg2 panels, 2014–16 and 2022 shaded; (6) oil–USD 12m correlation by regime with CIs.

## 5. Pre-registered outcomes → actions

| Result | Canary change |
|---|---|
| Q2 decision rule MET (both targets, h = 12, 12m % spec) | add an **oil-augmented probit variant** to `/recession-model`, displayed beside the raw and TP-adjusted dials exactly as the TP-adjusted variant is — never blended into the headline (standing rule: the calibrated probability is never adjusted). Gate test: headline probability byte-identical before/after |
| Q2 SUGGESTIVE (point ≥ 0.02, interval includes 0) | record; no deploy; re-test after the next NBER onset (dated ledger entry) |
| Q2 NOT met | recession odds stay curve-only; the measured non-result is recorded in the oil channel's `certainty` text and in `pin_history.measured_roles` |
| MET only at h ≠ 12, or only on Target A | descriptive note in the study; no deploy |
| NOPI12 passes the Q2 rule while the 12m % spec fails; OR D2 beats D1 on episode precision by ≥ 1 episode with equal-or-better recall (Q1 primary window, h = 12, NBER) | switch the channel's trigger leg to NOPI12 with anchors 0 / +10 (Hamilton's published cumulative threshold) / +25 / extreme = the reading printed by the named worst postwar episode, cited in the ANCHORS comment like every other row — NO anchor chosen from hit rates. Ties or mixed (better precision, worse recall) → no change, recorded |
| D3 beats D1 and D2 on precision with ≥ recall | real-oil trigger leg, same +25/+50 anchors, documented |
| Always | `kill_rate` rewritten to the measured "n of m postwar onsets preceded, k named false positives, j coincident" per definition; `basis` keeps Hamilton's claim with its measured status |
| Effect-size-by-regime: R2+R3 ≤ half of R0+R1 | `mass_trillions`/`mass` re-labelled to the petroleum bill; honesty note that the bigger-market argument cuts against oil today |
| R3 measured tests (H4b sign in R3; 2022 response vs R0/R1) | regime note in the channel's `certainty` string and glossary — wording only, never a weight |
| H4a / H4b outcomes | `demand_strike` certainty string and glossary text only, never a weight |
| Always | split `studies/pin_rule_hindcast.py`'s oil-OR-policy rule into oil-alone and policy-alone and re-report; add the study script under `studies/` so it re-runs keyless |

Every deployable row ships with gate tests (frozen-number reproduction ±0.005 on OOS AUC;
NOPI anchors equal the cited episode readings; headline-probability invariant) and the
redeploy note "treasury-canary backend".

## 6. Honesty box (to be completed with results)

Basis: P(NBER recession within h) on final dating; labels lag reality 4–12m, so even the
L-lagged walk-forward is optimistic on label knowledge. Oil = monthly-mean spot; the channel
reads a daily point change. Sample: 12 onsets (10 curve-scoreable, 7 OOS) — episode-level
95% CIs are ±30pp wide. Prices are unrevised; INDPRO is revised (context only). The 1973 and
1979 shocks arrived with Fed tightening and price controls — oil and policy are confounded
in exactly the episodes that anchor the kill-rate claim, which is why (d)/(e) exist. The
+25/+50/+100 anchors were set by inspection of the 1973/79/2022 episodes when the channel
was built (`pins.py` ANCHORS comment) and the NOPI ≥ 10 cut-off is this spec's own choice
on 2026-09-15; neither was searched here, but neither is independent of the shocks being
scored. The current episode's monthly NOPI spike peaked within 1 log-pct of the cut-off. NOT
modeled: Brent–WTI 2011–14 dislocation (footnote only), retail gasoline, global activity
beyond IGREA, energy share of GDP (consumption share used), the Fed's endogenous response,
fiscal offsets, Gulf holdings via European custodians. Frozen numbers to be quoted: OOS
AUC(a), AUC(b), ΔAUC with interval, Brier(a)/(b), per-definition n/m/k/j, dated.

## 7. Pending DD questions (living ledger; 60-day expiry from first ask)

| # | P | Question | What it moves | Asked | Status |
|---|---|---|---|---|---|
| 1 | P1 | Which series adjudicates 1973 timing — WTISPLC (deployed analogue, first ON 1974-01) or WPU0561 (Hamilton's series, first ON 1973-12)? Both are scored; Casey's sign-off decides which one the kill_rate text cites. | the anchor episode of the kill-rate claim | 2026-09-15 | asked |
| 2 | P1 | Name/date of the current (2026) oil-supply event for the supply/demand narrative list. | supply-driven classification of the live episode | 2026-09-15 | asked |
| 3 | P2 | EIA petroleum expenditure share of GDP (SEDS, needs key) vs the PCE energy share used — accept the consumption share as the effect-size interaction? | Q3 effect-size test | 2026-09-15 | asked |
| 4 | P2 | Brent for 2011–14 and retail gasoline (Hamilton's later work) — add as a leg or leave not-modeled? | completeness | 2026-09-15 | asked |
| 5 | P3 | Real-time (ALFRED) vintages for a full vintage-correct walk-forward, beyond the announcement-lag L. | walk-forward optimism | 2026-09-15 | asked |
| 6 | P3 | Oil & gas extraction employment / IPMINE for the shale capex-offset leg of R3. | R3 regime note | 2026-09-15 | asked |

## 8. Counter-agent log

1. **Pre-result spec review, 2026-09-15** — three lenses (econometrics; data integrity; thesis
   + repo conventions), 45 findings. Adopted: NOPI as a 12-month cumulative (v0's monthly
   spike fragmented 1979 into four one-month episodes and never fired in 1999–2000); episode
   merge rule (≤ 6 off months), USREC_t = 0 filter, coincident category, one-event-one-episode,
   double-dip rule, resolved-month rule; one curve basis (`spread_gs`) for every fit — the v0
   splice put a −0.29pp (1980s) level step at the R0/R1 boundary; Target B (onset-lead)
   alongside the deployed target — v0's target let in-recession months (1974, 1980, 2008) hand
   oil coincident credit; NBER announcement lag L in the walk-forward; statsmodels estimator,
   winsorised regressor, non-identified fallback, clipping; decision rule made interval-based,
   pinned to h = 12 and one specification, sign criterion from 1986-01; HAC z; 36-month block
   + cycle bootstrap; SPX re-pulled from 1927 (v0's period1 = 0 started at 1970 and
   left-censored the 1968-11 peak) and a B2 local-peak event set (1976-09, 2011-04 were
   invisible to the running-peak rule); TIC revised-June fix (v0 kept the pre-benchmark June
   for ten years), share-of-total, basket3 for 2012+, Norway separate; usd_broad ratio-splice
   documented (v0 had an +8.5% index-base jump at 2020-01); CPI 2025-10 interpolation; panel
   truncated at the last complete month; INDPRO dropped from the supply/demand split in favour
   of Hamilton's narrative list + IGREA (which IS available keyless — v0 wrongly said it was
   not); H4a/H4b made falsifiable with pre-stated signs; (d)/(e) Fed-funds specs; effect-size-
   by-regime as Q3's primary test; §5 rows for every result that fell between rows; NOPI
   anchors from named episodes, never from hit rates; §7 and this log added; figures fixed.
   Rejected/modified: the "≥ 90% positive within each of four blocks" sign criterion (an
   expanding-window coefficient barely moves after 2009, so per-block counts are not
   independent evidence) → "≥ 90% from 1986-01 and positive in the final refit"; "WPU0561
   primary pre-1983" vs "WTISPLC primary" (the lenses disagreed) → WTISPLC primary because it
   is the deployed instrument's own series, WPU0561 a named robustness row, and the choice
   escalated to Casey as P1 #1; R0 boundary kept at 1985 with the reason stated.
2. **Post-result numbers review** — to be logged before any §5 action executes: data integrity,
   named-episode spot-checks, independent recomputation of the decision rule from panel.csv.

---

# RESULTS (2026-09-16) — measured, counter-agent verified, frozen

Five analysis blocks ran on the frozen v1 panel; each numeric block was independently
recomputed from the spec by one verifier and audited line-by-line by a second; the
literature memo was fact-checked citation by citation; a completeness critic closed the
loop. Scripts, numbers.json, results.md and figures: `studies/oil_shock_weight/blocks/`;
verifier code and notes: `studies/oil_shock_weight/verify/`. Every number below reproduced
to ≤ 1e-5 in independent code unless a caveat says otherwise.

## Q2 — the weighting question: oil adds NO out-of-sample skill to the curve. Decision rule NOT MET on both targets.

Walk-forward probit, expanding window refit monthly from 1953-04, first prediction 1970-01,
last scored 2024-08 (T + 12 ≤ 2025-08), NBER announcement lag applied, curve = GS10 − TB3MS,
oil = WTISPLC 12m % change winsorised ±100 (the deployed channel's cap).

| target | n | pos | AUC curve | AUC curve+oil | ΔAUC | block 90% | cycle 90% | Brier curve | Brier +oil | ΔBrier | block 90% | β_oil>0 (1986+) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A (deployed labels) | 656 | 161 | 0.738 | 0.703 | **−0.035** | [−0.102, +0.025] | [−0.112, +0.045] | 0.1609 | 0.1852 | **+0.024** | [−0.004, +0.053] | 464/464, final +0.0048 | **NOT MET** |
| B (onset-lead, in-recession months excluded) | 571 | 84 | 0.909 | 0.894 | **−0.015** | [−0.051, +0.011] | [−0.045, +0.022] | 0.0943 | 0.1099 | **+0.016** | [+0.001, +0.030] | 464/464, final +0.0070 | **NOT MET** |

Four of the six criteria fail on each target (only the sign criteria pass: the oil
coefficient is positive in every refit since 1986 — it just ranks nothing better). Not
SUGGESTIVE either (point ΔAUC < 0). Robustness, all NOT MET: no announcement lag (A −0.026,
B −0.012); the literal `t + h + L ≤ T` reading (A −0.031, B −0.015); h = 6 / 18 / 24 (A
−0.036 / −0.020 / −0.025; B −0.047 [−0.068, −0.012] / −0.007 / −0.031); bootstrap seed and
block length 24/36/48 and a stationary bootstrap (verifier) — only Target B's ΔBrier lower
bound is seed-fragile at the 4th decimal, and ΔBrier > 0 fails on the point anyway.
Confirmatory NOPI12 specification: A +0.011 [−0.071, +0.094], B −0.029 [−0.087, +0.015],
ΔBrier +0.028 / +0.041 — NOT MET, so leg (i) of the channel-trigger row is closed.
Secondary 1986+ window (can never decide): 12m % A +0.009 / B −0.022; NOPI12 A +0.088
[−0.035, +0.188] (suggestive-shaped) / B −0.023.

**Where oil hurt, by name.** 82% of Target A's Brier deterioration is the 1970s: the early
refits learned β_oil = 0.13–0.19 from regulated posted prices and then saw +184% in 1974.
1976-09..1978-07: mean p(curve+oil) 0.60 vs p(curve) 0.14, peaking 0.97 vs 0.09 in
1976-10..1977-01, no recession. 1980-07: 0.999 vs 0.076 (next onset 13 months later).
1999-05..2000-11: mean Δp +0.35 over 19 months, the onset arriving 13–16 months after the
+100% prints. 2021-03..2022-08: mean p 0.39 vs 0.25, no recession. Oil LOWERED the odds
ahead of the last two recessions: 2008-01 (Target A mean Δp −0.006; Target B +0.006) and
2020-03 (−0.066 on both). Oil "helped" only in the 1990-08..2001-03 and 2008-01..2020-02
cycles on Target A (+0.074 / +0.099 per-cycle ΔAUC) — on Target B those read −0.017 / +0.001.

**Marginal effects (never applied — the rule is not met).** Last refit, Target B, h = 12:
a +50% oil shock moves P(12m) by +13.0pp at spread 0 and +8.1pp at +1pp; a +300bp Fed-funds
pace by −0.9pp / −0.4pp (HAC z −0.05 — the pace is absorbed by the curve). In-sample (b):
oil coefficient +0.0084, HAC z +2.10, McFadden 0.314 vs 0.299 for the curve alone, but
in-sample AUC 0.8791 vs 0.8791 (Δ −0.00001): a coefficient that is "significant" and ranks
nothing better, which is exactly what the walk-forward then shows.

## Q1 — oil alone on the postwar record: at the base rate on recessions, useful on accidents

Common window 1953-04..2024-08, NBER onsets 1953-08..2020-03 (11), h = 12, WTISPLC, §4
episode rules. Instrument agreement first: monthly-mean D1 vs the deployed daily point
construction agrees on ON/OFF in 96.4% of 476 month-ends 1987+ (3-grade 92.4%; 10 months
live-RED/panel-not, 7 reverse) — the monthly construction stands; the monthly curve-flat rule
agrees with the deployed daily-183 rule in 91.0% (48 daily-flat-only months); CMT vs
GS10−TB3MS flat: 16 disagreement months, all CMT-flat-only, including 2026-04.

| definition | month precision | base | episodes hit / (hit+FP) | recall | false positives (named) | coincident |
|---|---|---|---|---|---|---|
| **D1-RED** (12m ≥ +50, the deployed trigger) | 9/49 = **18.4%** | 16.7% | **3/10 = 30%** | 3/11 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-06, 2021-03 | 1974-01, 1990-09 |
| D1-YELLOW (≥ +25) | 21.8% | 16.7% | 4/14 | 5/11 | 10 named | 1974-01 |
| **D2** (NOPI12 ≥ 10) | 38/129 = **29.5%** | 16.7% | **5/8 = 62.5%** | 6/11 | 1976-09, 1996-04, 2021-10 | 1990-08 |
| D3-RED (real ≥ +50) | 21.4% | 16.7% | 3/9 = 33% | 3/11 | 1987-07, 2003-01, 2004-09, 2009-12, 2017-01, 2021-03 | 1974-01, 1990-09 |
| PPI-RED (WPU0561, robustness) | 24.1% | 16.7% | 4/11 | 4/11 | 7 named | 1974-01, 1990-09 |
| PPI-D2 | 32.0% | 16.7% | 6/8 | 7/11 | 1996-04, 2022-01 | 1990-08 |

h = 18 (second, never a rescue): D1-RED 30.6% vs 24.1% base, still 3/10; D2 40.3%, 5/8.
Pending under every definition: 2026-04. D1-RED catches: 1980-02 (6m lead), 2001-04 (first
ON 1999-08, 20m; last ON 10m before), 2008-01 (2m). D2 leads: 1973-12 4m, 1980-02 9m,
1981-08 27m (via the pre-registered double-dip window), 2001-04 14m, 2008-01 44m (the
2004-05..2009-04 episode; D2 was also ON 2007-10..12), 2020-03 23m (last ON exactly e−12 at
NOPI12 10.82 — the one genuinely fragile credit; drop it and D2 is 4/8 = 50%, recall 5/11).
Strict episode membership (in-recession ON months count as OFF) gives D2 5/9 = 55.6% with
1991-04 a fourth false positive. **Under every reading D2 beats D1 by ≥ 1 episode with better
recall → the §5 NOPI12 trigger-leg row is triggered.** D3 does not beat D2 → no real-oil leg.

**Kill-rate recount** (the string that replaces "preceded ~10 of 11"): D1-RED "3 of 11
onsets 1953-08..2020-03 preceded, 7 named false positives, 2 coincident"; D2 "6 of 11, 3
false positives, 1 coincident"; D3-RED "3 of 11, 6, 2". On Hamilton's own set (1948-12..
2008-01) D1-RED is 4 of 11 (the 1948-01 posted-price step precedes 1948-12). Hamilton 2011's
exact wording — "All but one of the 11 postwar recessions were associated with an increase in
the price of oil, the single exception being the recession of 1960" — counts rises of +7–10%
and one coincident month, so it is not reproducible at the +25/+50 anchors by construction.

**Curve-conditioned (1953-09+, 10 onsets), h = 12.** Curve flat alone: 55.2% month
precision, 9/11 episodes, recall 10/10. D1-RED AND curve: 7/7 months, 2/2 episodes, recall
2/10 (1980-02, 2008-01 — both already in the curve's set: oil removes 8 of the curve's 10
catches and adds none). D2 AND curve: 68.6%, 5/6, recall 6/10. On ≥15% drawdown starts (B1,
15 events, base 22.6%): D1-RED alone **51.0%**, 5/9 episodes (1980-11, 1987-08, 2000-08,
2018-09, 2021-12; FP 2002-12, 2004-09, 2009-12, 2017-01); curve alone 31%. B2: D1-RED 59.2%,
6/9. Hindcast v4 on the deployed 1987+ instrument (`studies/pin-rule-hindcast.md`): the rule
reported in v3 as "oil/policy window + curve" (45%, 5/6) was the oil damage window alone —
48% / 4 of 5 on onsets (3 legitimate; the 2020 catch is the 2018 window meeting the 2019
inversion, and the onset was the pandemic), 42% / 4 of 5 on drawdowns; oil RED alone 14%,
17 of 20 clusters false positives.

Regimes by signal month: R0 D1-RED 2 episodes, 1 hit, 0 FP (base 24%); R1 6 episodes, 2
hits, FP 1987-07, 2002-12, 2004-09 (16.7%, base 14.5%); R2 3 episodes, 0 hits, FP 2009-12,
2017-01, 2018-06 (0%, base 7.9%); R3 FP 2021-03, pending 2026-04. D2: R0 3 ep 2 hits;
R1 4 ep 2 hits; R2 1 ep 1 hit (2018-04 → 2020-03); R3 FP 2021-10, pending 2026-04. **2022
false positive confirmed under D1, D2, D3 at h = 12 and 18. R3 has no scoreable onset.**

## Q3 — regime and effect size: the "bigger market" argument now cuts against oil

Effect-size-by-regime, (b) Target B h = 12: R0+R1 (1953-04..2008-12; n 564, 112 positives, 10
lead windows) oil coefficient +0.0105/pp, HAC z +1.80, ΔP(+50% oil, spread 0) = **+19.5pp**
[+2.7, +36.3]; R2+R3 (2009-01..2024-08; n 180, 12 positives) −0.0062, z −1.09, ΔP =
**−5.4pp** [−14.3, +3.5]; ratio −0.28 ≤ 0.5 → the §5 mass row is met on the letter of the
rule (180 non-zero oil months ≥ the 24 the spec requires; the fit converged). Honest reading:
all 12 R2+R3 positives are the single 2020-03 lead window, so the estimate is one episode's
oil path — "consistent with ≤ half", not a measured shrinkage. The share interaction on
1959+ points the same way: oil × (energy share − 5.8%) +0.0100, HAC z +2.25, identified by
the 1979–81 windows (dropping 1979-01..1981-12 cuts z to 1.03); implied ΔP for +50% oil at
today's 3.8% consumer-energy share −3.4pp [−18.6, +11.9], vs +35pp at the sample-mean share
and +66pp at the 1980 share (9.3%). Energy share of consumer spending > 7% in 1959–63 and
1974–86; 3.8% in 2026-07.

Supply vs demand (descriptive): by the narrative rule 3 episodes are supply-driven (1974-01
and 1990-09 in-recession/coincident, 2002-12 FP: 0 hits) and 9 demand-driven (3 hits, 6 FP);
IGREA agrees with the narrative class in 10 of 12; 1979-08 classifies as demand (WTISPLC
crossed +50 nine months after Iran) and 2021-03 as demand (11 months before Ukraine); n is too
small for any inference. 2022 response measured from the shock month 2022-02 → 2023-02:
INDPRO −0.2%, PAYEMS +2.8%, vs the R0/R1 supply-episode mean −2.8% (−9.1..+2.0) / −0.7%
(n = 3, two of which start inside recessions): INDPRO inside the historical range, payrolls
above it. (The block's first window, 2021-03 → 2022-03: +3.1% / +4.9%, measured the
reopening, not the shock — corrected by the audit.)

## Q4 — petrodollar: no measurable Treasury bid; oil–dollar co-movement straddles zero since 2020

H4a recycling (oil-exporter SHARE of foreign Treasury holdings, TIC): December-anchored
annual changes vs 12m oil change: seg1 2000–2011 r −0.12 (n 11), seg2 2012–2025 (Saudi + UAE
+ Kuwait) r −0.42 (n 13) — both sign legs FAIL; leg 3 passes (seg2 share 2.72% → 3.15%,
+0.43pp, over 2022). June-anchored the signs flip to +0.09 / +0.20 (all legs pass): **the sign
is anchor-month dependent at n = 11 / 13**, so the honest verdict is "no reliable recycling
link at this granularity", not "refuted". Named episodes: 2014–16 oil −71% while the seg2
share ROSE +0.52pp; 2022 Fed custody −4.8% while the share rose. Norway (GPFG, not in TIC's
oil-exporter basket) r −0.06 (n 20). Caveat: TIC attributes by custodian country — Gulf
holdings via Belgium/UK/Cayman/Luxembourg are unobserved, so recycling is under-stated.

H4b transmission (12m Δoil vs 12m Δbroad dollar, block-bootstrap 90%): R1 1986–2008 −0.08
[−0.42, +0.12] straddles; R2 2009–2019 **−0.79 [−0.87, −0.51] supported** (net importer:
oil↑ ⇒ USD↓); R3 2020+ −0.26 [−0.53, +0.36] straddles zero against the pre-stated positive
sign → **thesis not supported in the current regime** (the point sign turns +0.29 from
2022-01 once the COVID crash/rebound months are dropped; the interval still straddles).
Oil–custody: R2 +0.01 [−0.12, +0.59], R3 +0.43 [−0.17, +0.72], both straddle; R1 not
computable (FRED custody prints 0 before 2007-07).

## Q5 — what the instrument reads now (2026-09-16)

| reading | value | grade |
|---|---|---|
| Live channel, daily 252-obs point change (2026-09-09, $97.26 vs $63.81) | +52.4% | RED (score 81) — the reading that fired |
| Monthly-mean D1, last complete month 2026-08 | +29.4% (peak +64.3% in 2026-05) | YELLOW |
| Monthly-mean D3 (real) | +25.2% (peak +57.7%) | YELLOW |
| NOPI12 (D2), 2026-08 | 13.3 log-% → ON at 8 / 10 / 12 | YELLOW under the new anchors (score ≈ 57) |
| Curve | GS10−TB3MS +0.96, 6-month min +0.64: not flat; the deployed daily-183 and CMT rules read flat in 2026-04 | — |

Nearest analogs by peak reading with the curve not flat: on the 12m rule 2002-12, 2004-09,
2017-01, 2018-06 — all false positives; on NOPI12 2018-04 (hit, but the onset was the
pandemic), 1976-09 (FP), 1996-04 (FP), 2000-02 (hit). No in-sample or last-refit marginal
effect is applied to today's spread (rule not met). The dial stays 21.5% (12m, curve only).

## Literature and thesis (37 citations, fact-checked)

Improvements to the thesis "oil is a bigger market so deserves more weight; we are on a
petrodollar system" (`blocks/lit/results.md`): (1) weight oil by the exposed expenditure
share, not market size — oil ≈ 3% of GDP (8% in 1980), energy 2.7% of PCE (6% in 1980); (2)
the size argument now cuts the other way: US net petroleum exporter since 2020 (EIA), post-2010
IP response to +10% oil ≈ 0 to +1% (Känzig, Stock & Zanotti 2026), employment ≈ 0 (Boston Fed
2026), Dallas Fed 2026: a 15% supply loss → −0.3pp US growth vs −5.6pp in 1980; (3) score the
shock's source, not its size — supply shocks depress activity with a lag, demand-driven rises
coincide with expansions (Kilian 2009; Baumeister & Hamilton 2019); (4) use the 3-year NOPI as
the trigger but expect a 1979/2008 story (Kilian & Vigfusson 2017: the nonlinear fit is 59%
worse than linear across all episodes and gains only in 1979Q4 / 2007Q4); (5) demand
incremental value over the curve — Estrella & Mishkin 1998 found the curve alone beats
combinations beyond one quarter; Ravazzolo & Rothman 2013: real-time OOS gains ≤ 1% MSPE at
h = 4, none at h = 1 — our walk-forward is the same finding on recession classification; (6)
estimate oil jointly with the Fed channel — Bernanke, Gertler & Watson 1997 attribute 2/3–3/4
of the output effect to policy, Hamilton & Herrera 2004 and Kilian & Lewis 2011 dispute;
1973/1979/2022 all confounded with tightening; (7) relocate the petrodollar mechanism from
Treasury demand to dollar strength — identifiable oil-exporter Treasury buying was a minority
even in 2003–05 ($107bn of $224bn identifiable US inflows; Higgins, Klitgaard & Lerman 2006),
Saudi Treasuries fell ~41% from early 2020 to mid-2023 despite a ~$150bn 2022 surplus, Gulf
surpluses ≈ $200bn vs Asia ≈ $1.5T (Setser 2026); the oil→dollar sign flipped around 2021
(BIS 2023, contested by ECB 2024 as shock-mix); (8) test recycling on all US securities and
SWF flows, not Treasuries — Saudi bought $52.5bn and UAE $34.8bn of US securities in 2022
(Weiss 2023) while the Treasury lines fell.

Deployed-text verdicts: basis "10 of 11" — accurate 2011 quote, mis-scaled (rises this channel
cannot trip; 10 of 12 with 2020; 2003 and 2022 fired without recession); kill_rate — outdated,
replaced by the measured count; speed "3–12 months" — accurate, measured leads −1 to 15 months;
mass "$20T consumption base" — misattributed, replaced by the ~$0.9T petroleum bill;
detail "forces the Fed's hand" — contested; certainty "high historical association" —
in-sample only.

## §5 rows executed (2026-09-16, redeploy: treasury-canary)

| row | verdict | change shipped |
|---|---|---|
| Q2 NOT met | NOT MET both targets | recession odds stay curve-only; non-result in the oil channel's `certainty` and `pin_history.measured_roles`; gate test: `recession.py`/`recession_model.py` contain no oil, published-coefficient probabilities unchanged |
| NOPI12 trigger row (leg ii) | D2 beats D1 under every reading | `oil_shock` trigger leg = "Net oil price increase, 12m cumulative (vs 3-year high)", anchors 0 / +10 / +25 / **104.4** (= the 1974-01 reading of the 1973–74 embargo episode, the worst postwar print); the 12-month change stays as a context gauge capped at YELLOW (79); same helper feeds the live board and the hindcast; gate tests reproduce the frozen panel column and the anchor |
| D3 row | not triggered | — |
| kill_rate / basis | always | measured strings, naming the onset set 1953-08..2020-03 |
| effect-size row | met on the letter (one-episode caveat as prose) | `mass` = US petroleum bill ~$0.9T/yr (~3% of GDP vs ~8% in 1980), `mass_trillions` 20 → 0.9; exposure-map sums move accordingly |
| R3 measured tests | H4b R3 straddles; 2022 response from the shock month | regime sentence in `certainty` + glossary |
| H4a / H4b | anchor-dependent / R3 not supported | `demand_strike` certainty string carries the petrodollar finding (no glossary entry exists for that channel) |
| Always | done | hindcast v4 split (commit 41babbc); study scripts, frozen data, figures and verifier code under `studies/oil_shock_weight/` |

Live effect after deploy: the oil channel drops from RED (12-month rule, +52.4%) to YELLOW
(NOPI12 ≈ 13 on daily monthly means; the 12-month gauge reads +52% but caps at YELLOW); the
board's red-mass sum loses the $20T it was crediting to oil; the hindcast's oil line starts
1990 (48-month warm-up on the 1986+ daily series) and 1987–89 can only read yellow.

## Honesty box (completed)

Basis: P(NBER recession within h months) on final dating, monthly; labels lag reality 4–12
months, so even the announcement-lagged walk-forward is optimistic on label knowledge (no
ALFRED vintages; the literal `t+h+L` rule moves ΔAUC by ≤ 0.004). Oil = monthly-mean spot
(WTISPLC); the live channel reads a daily point change (96.4% ON/OFF agreement 1987+; the
grade today differs: RED daily, YELLOW monthly). Curve = GS10 − TB3MS on the discount basis
throughout (CMT flat-rule disagreement 16 months, incl. 2026-04). Sample: 12 onsets (10
curve-scoreable, 7 OOS); episode-level 95% CIs ±30pp; ΔAUC bootstrap intervals ±0.06 wide;
the cycle bootstrap resamples 8 segments. Target A's 161 positives include 77 in-recession
months (10 from the excluded 1970 recession) — Target B is the spec-consistent target and
gives the same verdict. D2's 62.5% is reading-dependent by 7pp (55.6% strict) and rests on
one fragile credit (2020-03); the +25/+50/+100 anchors were set by inspecting 1973/79/2022
when the channel was built and NOPI ≥ 10 is this spec's own cut-off; the current episode's
monthly NOPI spike peaked within 1 log-% of it. The 1973 and 1979 shocks arrived with Fed
tightening — (d)/(e) show the pace effect vanishes inside the curve, which does not resolve
the confound. The Q3 R2+R3 estimate is one episode's oil path. H4a's sign flips with the
anchor month. NOT modeled: Brent–WTI 2011–14 dislocation (footnote not delivered, §7 #4),
retail gasoline, global activity beyond IGREA, energy share of GDP (consumption share used),
the Fed's endogenous response, fiscal offsets, Gulf holdings via European custodians, TIC
2026 prints (file ends 2025-12). Frozen numbers to quote: OOS AUC 0.738 → 0.703 (A), 0.909 →
0.894 (B); ΔAUC −0.035 [−0.102, +0.025] / −0.015 [−0.051, +0.011]; Brier 0.1609 → 0.1852 /
0.0943 → 0.1099; D1-RED 3/11/7/2; D2 6/11/3/1; D1-RED drawdowns 51.0% vs 22.6%; oil window +
curve 48% 4/5 (1987+); R0+R1 +19.5pp vs R2+R3 −5.4pp; H4a −0.12 / −0.42 (Dec) vs +0.09 /
+0.20 (Jun); H4b R3 −0.26 [−0.53, +0.36]. All descriptive history, never calibration.

## §7 Pending DD questions — status after results

| # | P | Question | Status 2026-09-16 |
|---|---|---|---|
| 1 | P1 | WTISPLC vs WPU0561 for 1973 timing | asked — the CLASS no longer depends on it (1973-12 coincident under the 12m rule on both series; caught under NOPI on both, 4m vs 3m lead); the kill_rate string cites WTISPLC. Casey's sign-off still wanted for the record |
| 2 | P1 | Name/date of the 2026 oil-supply event | asked — the live 2026-04 episode is "unclassified" in the supply/demand table until answered |
| 3 | P2 | EIA petroleum share of GDP vs the PCE energy share used | asked — the consumption share was used for the interaction (z 2.25); a GDP share would only re-scale it |
| 4 | P2 | Brent 2011–14 and retail gasoline | asked — the Brent footnote was NOT delivered by the run; open |
| 5 | P3 | ALFRED vintages for the walk-forward | asked — not needed for the verdict (literal-L sensitivity ≤ 0.004) |
| 6 | P3 | Oil & gas employment / IPMINE for the shale-offset leg | asked — open |
| 7 | P3 | Extend the TIC file to the 2026 prints and re-read the 2026-04 episode | new 2026-09-16 — open |
| 8 | P2 | Re-run `studies/pin_rule_hindcast.py` (v5) against the deployed NOPI-leg history and re-freeze the oil-window+curve numbers (48% / 4-of-5 is pre-switch) | new 2026-09-16 — blocked on deploy |

## §8 Counter-agent log — entry 2 (post-result, 2026-09-16)

Verdicts: event CONFIRMED / CONFIRMED; probit_is CONFIRMED / PARTLY (Q3 override); walk
CONFIRMED / CONFIRMED (decision reproduced to 1e-16, invariant to seed, block length, the
literal L rule and the leak variant); regime_petro CONFIRMED / PARTLY (two material prose
findings, both corrected above); lit CONFIRMED (every load-bearing citation verified; six
secondary numbers marked unverified and dropped from the study text). Amendments logged:
(a) the pre-declared "1973-12 coincident under every definition" FAILED for NOPI12 (first ON
1973-08) and PPI-NOPI12 (1973-09); the §3 claim that WPU0561 first crosses +50 in 1973-12 was
wrong (that print is +27.5%, YELLOW; first RED 1974-01). (b) Episode membership: in-recession
ON months neither count nor break an episode and the raw first ON month drives the coincident
test — the only reading under which the spec's own 1973/1990 expectations are reachable;
strict-membership sensitivity reported (D2 5/9). (c) Walk-forward label knowledge implemented
as max(t + h, announcement) ≤ T rather than the literal formula; quantified ≤ 0.004 ΔAUC, no
verdict change. (d) Q3: the block applied an unregistered "≥ 2 positive-label regions"
identification rule; under the spec's own rule the row is met and it is executed, with the
one-episode caveat carried as prose, not as a verdict. (e) The 2020-03 lead window straddles
R2/R3 (2020-01/02 are positives); §4's parenthetical was wrong; no oil statistic affected.
(f) H4b's pre-stated R3 sign is contested in the literature (BIS 2023 vs ECB 2024) — recorded
after results, so it cannot have shaped them. (g) Figure 2 ships rolling-AUC lines with the
full-sample intervals as text, not a rolling band; a bootstrap-distribution figure was added;
Figure 5 draws the two TIC segments as separate lines in one panel. (h) The 2022 response was
first measured from the episode's first ON month (2021-03); the spec's "response to the 2022
episode" is measured from 2022-02 and both are reported. (i) CMT flat-rule disagreements are
16, not the 17 the v0 audit quoted. (j) Drawdown rows use ON months from 1953-09 (curve
convention) rather than 1950-01; no event lost. (k) After results, the data builders were
fixed to read FRED's pre-2007 custody zeros and TIC's Norway zeros as missing; the blocks had
already treated them as missing, so no number moved. (l) The oil-alone / policy-alone
hindcast split (v4) ran before the blocks; the event block's speculation that the bundled
rule was "carried by policy" is superseded by v4's measured opposite. (m) Post-commit code
review (2026-09-16, verdict PARTLY — code and numbers confirmed, seven wording defects fixed in
the follow-up commit): §5's phrase "+10 (Hamilton's published cumulative threshold)" is wrong
and contradicts §4 — the ≥ 10 cut-off is this spec's own; the shipped text now says so. (n)
Hindcast v4's 48% / 4-of-5 was measured on the 12-month rule's red episodes; after this commit
that leg can no longer open a damage window, so the figure is labelled "pre-switch" everywhere
it is quoted and a v5 re-run against the deployed NOPI history is ledger item §7 #8. (o) The
"energy ~4% vs ~6%" comparison mixed two series; corrected to the panel's own goods-and-services
share (~4% now vs ~9% in 1980). (p) "Measured leads −1 to 15 months" were Hamilton's narrative
lags, not this instrument's; the NOPI leg's measured first-ON leads are 4–44 months (last-ON
1–12). (q) The R2+R3 effect is worded "unidentified, consistent with at most half", and the
petrodollar sentence carries both anchor months and the 2022 share rise.
