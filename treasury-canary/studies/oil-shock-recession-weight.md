# Oil shocks and recession odds — how much weight does oil deserve? (spec v1, pre-registered)

**Status: SPEC v1 — amended 2026-09-15 from the counter-agent panel's review of v0, still BEFORE
any result was computed.** Results are appended below the spec once the pre-specified tests
run; nothing in §2–§5 may be edited after results exist except to log an amendment with its
date and reason. v0 is preserved in git (commit 2f710ab); §8 lists every amendment.

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
_Results appended below by the study run; counter-agent verdicts logged alongside._
