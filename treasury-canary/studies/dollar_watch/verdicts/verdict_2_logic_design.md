# Adversarial logic-and-design review — "DXY as crisis predictor" scoping (2026-11-02)

Reviewer did not write any of the material. Scratch computations in `review2/checks.py`, `review2/paths.py`, `review2/sens.py` (run with `python3 -I`); they reuse the finders' and orchestrator's own data files, nothing new was fetched.

## TOP-LINE VERDICT: **NOT_PASS** (as the scoping conclusions and the intended panel now stand)

The three finder notes are mostly honest and already contain the counter-evidence. The failure is in the orchestrator's scoping layer and the proposed panel: one headline number is false, three others are single-episode artefacts presented as frequencies, the user's deceleration rule has been patched after seeing its worst miss and scored by a metric that flatters it, and the end-of-crisis layer as designed would have told an equity holder "crisis subsiding" in Oct–Nov 2008 with −25% still to come. Fix the BLOCKING items and adopt the required wording below and this becomes PASS_WITH_FIXES; nothing in the material supports a stronger verdict than "descriptive panel with base rates visible".

---

## Findings, ranked

### BLOCKING

**B1. "S&P higher 12m after the dollar's ex-post peak in all 12 fast-rise episodes" is false.**
`scoping/out/dollar_summary.json: speed_episodes.spx_fwd12_from_peak` is negative in 5 of 12 (1974-01 −24.5%, 1981-08 −15.4%, 1983-06 −8.0%, 1994-01 −1.6%, 2001-05 −15.0%). 7/12 positive. From the real-time turn 10/12 positive — against an unconditional P(S&P up 12m) of 76% over 1973–2026 (633 months), i.e. 83% vs 76%, nothing. Survives? **FALLS.** Rewording: "After a ≥10%/6m dollar rise the S&P was higher 12m after the dollar's eventual peak in 7 of 12 cases (ex post) and 10 of 12 after a real-time 3%-off-high turn, versus 76% of all months — no edge."

**B2. The "n=12 → 50% / 25%" speed statistics are one to three episodes, not twelve observations.**
The 12 months with a 6m rise ≥15% are five clusters (1974-01; 1981-05..08; 1993-02; 2008-10/11, 2009-01; 2015-01..03). The "P(recession start) 25%" = 3/12 months, **all three from 1981** (one recession). The "P(Baa spread +100bp) 50%" = 6/12 months from **three** clusters (1974, 1981, 2015); 2008-10 missed the +100bp cut (0.94) only by construction. Every monthly row carries a 12-month forward window, so 627 rows ≈ 52 independent observations and the conditional cells are 1–5. Survives? **FALLS as stated; SURVIVES WITH REWORDING** as "in 3 of the 5 episodes of a ≥15%/6m dollar rise since 1973 the Baa spread widened ≥100bp within a year (1974, 1981, 2015); one (1981) was followed by a recession start; 2008's rise began inside the crisis".

**B3. "DXY > 105 → P(S&P dd ≥20% in 12m) 20% vs 6% in band" is one episode.**
Of the 25 above-105 months followed by a ≥20% drawdown, 22 are 2000-03..2002-05 (the dotcom bear, during which the dollar was high for US-rate/growth reasons), 1 is 1974-01, 2 are 1986-11/12 (eve of the 1987 crash, during which the dollar FELL). The 59 straight above-105 months of 1982–86 produced none. Survives? **FALLS.** Rewording: "DXY above 105 coincided with one of the three ≥20% S&P bears of the sample (2000–02); the other two (1987, 2008) began with DXY at 98 and 72."

**B4. The band does not beat the base rate on ANY crisis list, including the one Casey cares about.**
On the 25-crisis list: 76% within 24m vs 69% base (finder A). On the 5-crisis dollar-funding list (1982-08, 1998-08, 2008-09, 2020-03, 2022-09): band excursions (merged ≤3m, n=17) are followed by an onset within 12m in **1/17 (6%) vs a 9% base**; within 24m 3/17 (18%) vs 19%. On a 7-list (+1974-06, +1997-07): 2/17 (12%) vs 13%; 4/17 (24%) vs 24%. The band is AT or BELOW base rate for dollar-funding crises specifically. The band claim and the "right crisis list" objection cut the same way: a narrow list lowers the base rate AND lowers the hit rate, because the big excursions (1981–86 above, 2010–14 below) contain no dollar-funding crisis. Survives? **FALLS.** Rewording: "No DXY band variant (85–105, 90–110, 83–102; raw or merged) beats the unconditional crisis frequency on any of three crisis lists (25, 7, 5 events)."

**B5. The speed signal does not survive the narrow list either, and the two finders contradict each other on it.**
Narrow list, 6m ≥10% (n=15 triggers): hits 2/15 (13%) vs 9% base at 12m, 4/15 (27%) vs 19% at 24m; 12m ≥10%: 2/15, hits = 1982-01 and 2022-04; the 2008-10 trigger fired AFTER Lehman. Finder C's 48% vs 29% (synthetic DXY, 16-onset list, month-counting) and finder A's 28% vs 42% (real DXY, 25-list, event-counting, 6m window) have opposite signs; finder C itself says the 41 hit-months are ~5 clusters and that the list was fixed knowing the dollar history (2022-09 IS the dollar peak). A signal whose sign flips with the crisis list and counting convention is noise. Reverse causality: 10/18 fast rises start inside a crisis window (finder A). Survives? **FALLS as a predictor; SURVIVES WITH REWORDING** as "sustained 12m dollar momentum >+10% is the only dollar statistic with a KLR-grade in-sample noise-to-signal ratio (0.42), from ~5 episodes, half of which began inside the crisis they are credited with predicting; it is not a validated signal and must not be displayed as a probability."

**B6. The end-of-crisis layer (iii) as designed conflates "end of the dollar scramble" with "crisis subsided", and in 2008 that difference was −25% in equities.**
Finder B's own end-marker table: CP−bill 50% retrace 2008-10-17, gold trough 2008-11-12, deceleration rearm firing 2008-11-06 — all four months before the S&P low (2009-03-09). Paths (finder A daily files): from 2008-10-17 S&P 941→677 (−28%); from 2008-11-06 905→677 (−25%); from 2008-11-12 852→677 (−21%); the broad dollar rose a further 6.5% (DXY +3.6%) to 2009-03-03. The same markers were RIGHT for gold (718→918, +28%, from the trough). The funding scramble and the solvency/recession phase are different things with different ends; the panel must say which asset the "end" applies to. Survives? **SURVIVES WITH REWORDING** as a "dollar-scramble peak" flag — explicitly NOT a risk-asset bottom flag — with the 2008 four-month, −25% gap printed next to it.

### SERIOUS

**S1. The user's deceleration rule: real-time record on the three V-spikes that motivated it is 1 of 3.**
2008: base rule fired 2008-09-22 (first wave; dollar +17.7% more, VIX +13.5, S&P −44% to the low). 2020: fired 2020-04-09 — clean (dollar +1.4% more, S&P +13% in 60d). 2022: fired 2022-07-28 — dollar +6.6% more, S&P −12% to 2022-10-12, VIX +7.5. The "7 firings, 5 good" count (a) uses the `rearm` variant (`decel_realtime_rearm.json`), a re-fire clause added after the 2008-09-22 miss was observed — post-hoc patch, which is the overfitting objection in concrete form; the unpatched rule fires 6 times; (b) scores by VIX change, which marks 2008-11-06 a success while the dollar rose 6.5% more and the S&P fell 25%, and marks 2011-11-01 a success while the dollar rose 4.4% more and peaked seven months later; (c) three of the five "successes" (2010-06, 2011-11, 2012-06) are euro-crisis mini-episodes with VIX 22–35, not dollar scrambles. Parameter sweep (`review2/sens.py`, thresholds 3–5%, decay 40–60%, window 40–90d): firings range 3–11; the count of firings with dollar <+3% more AND VIX down stays at 3 (2010-06, 2012-06, 2020-04) while failures range 2–8; at a 5% threshold the rule fires only 3 times in 20 years (2008-11-06, 2011-11-01, 2020-04-09). The 4%/50%/60d/97% settings sit at the local optimum of that grid. Survives? **SURVIVES WITH REWORDING** — as a hypothesis under test, not a rule: "In the two true dollar scrambles with daily data (2008, 2020) the 20-day rate of climb peaked 0–19 trading days from the VIX peak; a real-time deceleration trigger caught 2020 cleanly and fired on the first wave in 2008 and 2022. Parameters chosen on these episodes; untested before 2006."

**S2. Is "peak rate of climb ≈ peak stress" a tautology?** Partly. In a safe-haven scramble the dollar's rate of climb is itself a stress measure (finder C: dollar-up/yield-down is one factor with VIX/spreads), so its coincidence with the VIX peak is expected, not discovered. The non-tautological content is the LEAD over the dollar's own LEVEL peak (86 days in 2008, 0 in 2020 and 2022, 134–211 days in 2015–16/2018). But the monthly table (`decel_test.json: monthly`) shows that outside V-spikes the ROC peak preceded the S&P trough by 5–21 months (1981, 2000) or FOLLOWED it by 6–24 months (1975, 1983, 1988, 1991, 1997, 2014) — the rate-of-climb peak has no stable relation to the stress peak across regimes. Survives? **SURVIVES WITH REWORDING**: "works only in the safe-haven scramble regime; in policy-driven grinds (1981, 2015, 2018) the climb peaked a year before the stress."

**S3. 2022 is not a dollar-funding scramble, and the user's hypothesis groups it with 2008.** SWPT peaked $11.3bn (vs $583bn 2008, $449bn 2020); finder B: "stress was mild"; CP−bill peaked 2022-07-01, three months before the dollar; finder C classifies 2022 as the policy quadrant (dollar up, yields up); the 2022 "V" is a 9-month rate-differential grind with a terminal spike. Casey's "scramble for dollars to pay debts" fits 2008 and 2020; 2022's gilt/JGB stress was leveraged DURATION, not dollar funding. The deceleration rule's 2022 firing passed the "10y fell over the scramble" test only because yields dipped in July 2022. Survives? **SURVIVES WITH REWORDING**: "the hypothesis is about dollar-funding scrambles; of the three V-spikes on the chart, two (2008, 2020) are scrambles; 2022 is a policy move and the rule failed there."

**S4. Finder B's "funding series LEAD" is a lead over the DOLLAR, not over the crisis.** The OFR funding alarm of 2007-08-09 and NFCI risk 2007-07-13 ARE the crisis onset (BNP Paribas week); CP−bill peaked 2008-10-15, after Lehman. They lead the dollar because the dollar is a lagging symptom (DXY low 2008-03-17, seven months into the crisis). Correct label: NOWCAST of funding stress; useful as the "volume" half of Casey's rule (it is the price of dollars, and it is free); useless as a six-month warning. Also: in 2015–16 and 2018 the funding gauges were silent and gave no lead at all. Survives? **SURVIVES WITH REWORDING.**

**S5. "Volume of dollar-seeking" is measurable only as price, and the end-marker "funding spread halves within days of the policy announcement" rests on two cases.** 2008-10-17 (4 days after unlimited swaps) and 2020-05-07 (seven weeks after the 03-15/19 announcements — not "days"). Swap usage lags 2–5 months; basis is paid. So the volume half of Casey's rule = CP−bill + OFR funding + swap-line announcements as events. Honest, but n=2 for the "halving" timing, and in 2020 the funding spread normalised AFTER the equity low. Survives? **SURVIVES WITH REWORDING** ("the policy announcement is the earliest end marker; funding spreads halved within 4 days in 2008 and 7 weeks in 2020").

**S6. Gold-trough-as-earliest-subsiding-flag is a 5-episode coincidence with two decision-relevant failures.** Leads over the dollar peak: 111d (2008), 34d (2015), 103d (2018), 4d (2020), 0d (2022). But leads over the EQUITY low: 2008 −117d with S&P −21% after; 2018 gold trough 2018-08-16, S&P fell a further 17% to 2018-12-24; 2015 trough 2015-12-17, S&P −10% more to 2016-02-11. Gold's trough marks the end of the LIQUIDATION of gold, which is what matters for a gold-cornerstone portfolio, and nothing else. Survives? **SURVIVES WITH REWORDING** for gold holders only.

**S7. The re-dollarisation sign test is consistent with Johnson but equally with the risk-barometer reading, and the lead runs the wrong way for his story.** corr −0.50 yoy, −0.55 with the DOLLAR leading one quarter: the dollar moves, then credit — i.e., dollar strength slows USD credit (Bruno-Shin), not "credit contraction drives the dollar". Contractions appear only AFTER spikes (2009, 2022H2–2023). The BIS USD-denominated series has no valuation artefact but both variables load on risk appetite. Survives? **SURVIVES WITH REWORDING**: "directionally consistent with Johnson's sign, causally unidentified, two-quarter not multi-year; the $15.1tn/$129tn stocks were at records before every crisis AND through every calm year since 2010 and have no predictive content as levels."

**S8. The 2022 chain argument.** Freeze 02-28 and first hike 03-16 are 16 days apart; the dollar had already risen 7.7% on hike expectations before the freeze; Evergrande RD was 2021-12-09; the DXY fell 10% Oct–Dec 2022 with sanctions intact; swap lines essentially undrawn. Survives? **FALLS** as a causal chain; "the freeze may have added precautionary demand; the path is indistinguishable from a hiking-cycle/terms-of-trade story and the reversal with sanctions intact favours the latter."

### MINOR

**M1. Quadrant counts are weaker than they look.** Safe-haven cell P(S&P dd≥20%) 14.6% vs 9.9% all, P(rec) 16.7% vs 12.3%; policy cell P(rec) 18.4%; n=48–49 overlapping months ≈ 4 independent episodes each. The quadrant is honest as a REGIME LABEL ("which kind of dollar rise is this"), not as a probability. Finder C's 9/2/3/2 of 16 is the form to show.

**M2. The daily rule runs on the Fed broad dollar (DTWEXBGS, EM-heavy, 2006+), Casey's chart is ICE DXY.** The V-spikes differ in amplitude (2022 broad peak 128.5 vs DXY 114.8 intraday). Say which index the rule uses.

**M3. Gold 2026: −30.6% (GC=F, 2026-01-29→10-30) / −27% (FMP XAUUSD) with DXY +5.7% and zero funding stress** falsifies "gold falls because of a dollar scramble" as a general mechanism for THIS move; the panel must not label the 2026 gold fall as dollar-scramble evidence. Also two numbers for one fact (−30.6% vs −27%): pick one source and state it.

**M4. Johnson's talk is unlocated; his band is self-described "ad hoc"; the 16/75% is unsourced.** Every "Johnson claims" line must carry "as relayed; source not found".

### NOTE

**N1.** Finder A's 25-crisis list has 48% of all months inside a crisis window — a list that dense makes any signal look uninformative (the caller's point) but also makes "the dollar rose in 16/25" uninformative; both sides of the argument must use the same list. Show results on 25 / 7 / 5 side by side.
**N2.** finder C's "AUROC SE ≈ 0.07 at 16 onsets; need ~18 independent alarms to separate 50% from 29%" is the single most important sentence in the material and should be on the panel.
**N3.** The Plaza 1985 fall (−40%, no crisis for 32 months) and 2025 (US-origin shock, dollar fell) are the two counter-examples that kill claims 1 and 5 respectively in one line each; use them.

---

## Attack list, item by item

1. **Band vs base rate.** Right list for Casey = dollar-funding crises (5–7). Base 9–13% at 12m, 19–24% at 24m. Band: 6–12% / 18–24% — at or below base. Speed: 13–27% / 27–33% — within noise of base on 15 triggers, 2 of which fired inside the crisis. Finder C's 48% vs 29%: FALLS to the cluster problem (~5), the list-knowing-the-dollar problem, reverse causality (10/18 inside a crisis), and the sign flip against finder A. **FALLS.**
2. **Reverse causality.** Nothing here separates them in the sense of identifying "dollar → crisis": Granger says dollar does not lead VIX/TED; quadrants say 9/16 onsets are safe-haven (symptom); funding series lead the dollar, not the crisis. The only causal result is Obstfeld-Zhou/Hofmann-Park: dollar shock → EM GROWTH over 4–8 quarters (10% → −1.5% EM GDP), in-sample LPs. Strongest honest statement: "A rising dollar is mostly the crisis showing up in prices; a sustained rise then weighs on EM growth and dollar-credit growth over the following 1–2 years; it has not been shown to lead crisis onset." **SURVIVES WITH REWORDING.**
3. **Deceleration rule.** Partly tautological in the scramble regime (S2); a plausible real-time top-marker for the dollar scramble in 2020 only; first-wave failures in 2008 and 2022 are the cases that matter; the 7-firing count uses a post-hoc rearm; scoring by VIX flatters; parameters at the grid optimum. To make it honest: freeze parameters now; score on 1973–2005 monthly (3m ROC) and on the 2006+ daily series WITHOUT the rearm; require CP−bill (or OFR funding) to be ≤50% of its 60-day max simultaneously; score outcomes on the dollar's further rise and the S&P/gold path, not VIX alone; print the two-wave failure mode and the 2008 four-month equity gap on the panel. Volume half: CP−bill + OFR funding + swap announcements (S4, S5). **SURVIVES WITH REWORDING** as an unvalidated hypothesis.
4. **Mechanism / BIS stocks.** Slow state variables at records in crisis and calm alike — no predictive content as levels; growth sign consistent with Johnson, causally unidentified, dollar leads credit (S7). 2022 chain **FALLS** (S8). Dual carry trade: not tested by anything here; label "mechanism asserted, untested".
5. **Gold.** Decision-relevant framing for a gold-cornerstone portfolio: "gold is liquidated for 2–8 weeks in a dollar-funding scramble (−15% to −33% peak-to-trough in 2008/2020/2022/2013) and its trough is at or before the dollar peak; it ended the episode higher in 10/25 crises; it rose with a FALLING dollar in 1974 and 1987." Gold-trough-as-end flag: real for gold, false for equities (S6). 2026: gold −27/−31% with a flat dollar and no funding stress — a different mechanism (oil/real-rate shock after a parabolic run); the panel must not read it through the Johnson lens. **SURVIVES WITH REWORDING.**
6. **The build.** See next section.
7. **Framing.** See below.

---

## The recommended panel — what to cut, keep, add

Theatre (cut or demote): a "probability" or percentage on any cell with fewer than ~15 independent episodes; the band shading sold as a threshold (keep as a reference line labelled "Johnson's ad hoc band; no edge found on 3 crisis lists"); the fuel-gauge framing of the BIS stocks ("record" has been true for 15 years); a 12m-momentum PERCENTILE presented as a warning dial; the 2022 chain story in any form.

Would make the user believe an unwarranted call: (iii) as designed — a single "END OF CRISIS" lamp. In 2008 every component (deceleration, CP−bill under median, gold turning) was lit by mid-November with the equity low four months and −25% away. Split it into "dollar-scramble peak (dollar/funding/gold)" and never let it say "crisis subsided". Also the layer-(ii) label "leading": lead over the dollar, not over the crisis.

Missing and worth adding: EM FX basket / EME dollar index (finder B has it free; it is where the Obstfeld-Zhou channel shows); oil (Brent 99th pct is the live shock and a dollar-positive funding drain for importers — and finder C's pre-registration lists it); policy-rate differential and US 2y–funds spread (separates the policy quadrant in real time; US 2y 70bp above the funds ceiling now); the Treasury channel the dashboard is named for (10y, term premium, foreign official custody −6.6% yoy at a 10-year low, 2025's inverted safe-haven episode) — that is the de-dollarisation evidence that exists, and it argues AGAINST the milkshake, not for it; the counter-example list (1985–87, 1995, 1998, 2008 onset, 2011, 2023–25) on the panel itself.

Keep as is: layer (i) level + 6m/12m change with the regime quadrant as a LABEL; layer (ii) renamed "dollar-funding nowcast" with CP−bill, OFR funding, NFCI risk, SOFR tails, SWPT + announcement events; the BIS credit yoy as "re-/de-dollarising (Johnson's label), coincident"; the dated forecast ledger.

Pre-register or ship descriptive? Ship DESCRIPTIVE now with base rates and N on every number and nothing that says "probability", "warning" or "subsided". Pre-register finder C's minimal design (frozen 3 lists, 1973–2007 fit / 2008–26 test, LOCO logit, end-rule scoring) and the frozen deceleration parameters BEFORE any layer gets a colour or a lamp. Do not ship a scored rule that was tuned on 2008/2020/2022 and then tested on them.

---

## Framing: what the memo may say (5) and must not say (3)

MAY:
1. "The dollar's rise in a crisis is mostly the crisis itself: in 9 of 16 onsets it rose with US yields falling (flight to safety), it did not lead the VIX or TED spread in Granger tests, and it FELL at peak stress in 9 of 25 crises (1982, 1987, 1990, 1995, 1998, 2011, 2023, 2024, 2025)."
2. "What a sustained dollar rise does change is EM growth and dollar-credit growth over the following 1–2 years (literature: 10% → EM GDP −1.5% at ~8 quarters, in-sample); it has not been shown to lead crisis onset, and no DXY band or speed threshold beat the unconditional crisis frequency on any of three crisis lists."
3. "In the two dollar-funding scrambles with daily data (2008, 2020) the dollar's 20-day rate of climb peaked within 0–19 trading days of the VIX peak and 0–86 days before the dollar's own peak; a real-time deceleration trigger caught 2020 and fired on the first wave in 2008 and 2022 — it is a hypothesis to score, not a rule."
4. "The end of a dollar scramble is marked, in order, by the policy announcement, funding spreads halving (4 days in 2008, 7 weeks in 2020), gold's trough, the dollar's peak; in 2008 all of these came four months and −25% before the equity low. 'Scramble over' is not 'crisis over'."
5. "Current readings: DXY 101.7 inside the band, +3.3% 6m, zero funding stress on every free gauge, USD credit outside the US +8.1% yoy; the live shocks are oil (99th pct), gold −27% with a flat dollar, and foreign official custody at a 10-year low — a rates/oil picture, not a dollar squeeze."

MUST NOT:
1. Any sentence of the form "X% of band breaches / fast rises end in a crisis" or "P(crisis in 12m) = N%" — 16 onsets cannot support it, and 75% ≈ base rate.
2. "The deceleration rule marks the top of the crisis" or any lamp/colour that says a crisis has subsided — it was 1 of 3 on the motivating episodes and 4 months early in 2008.
3. "Gold falls in every crisis", "the dollar rises in every crisis", or "the 2022 reserve freeze caused the dollar's rise and the gilt/China/Japan stress."

---

## Required wording — labels that must travel with each number

| number | mandatory label |
|---|---|
| **76%** (13/17 band excursions → crisis within 24m) | "vs 69% unconditional on the same 25-crisis list; 6% vs 9% base on the 5 dollar-funding crises; Johnson's 16/75% unsourced, band self-described ad hoc" |
| **9/25** dollar fell at peak stress | "monthly-close basis, eve → peak-stress month, 25-crisis list (dates: finder A crises.csv); includes 1982, 1987, 1990, 1995, 1998, 2011, 2023, 2024, 2025" |
| **48% vs 29%** (12m ΔDXY > +10%) | "in-sample; synthetic monthly-average DXY; 16-onset list fixed knowing the dollar path; ~5 clusters; finder A's real-DXY 6m test gives 28% vs 42%; 2/15 vs 9% on the dollar-funding list; NOT validated" |
| **7 firings** (deceleration rule) | "rearm variant added after the 2008-09-22 miss; unpatched rule fires 6; scored by VIX; on the three V-spikes 1 clean (2020), 2 first-wave misses (2008-09-22: dollar +17.7% more, S&P −44%; 2022-07-28: dollar +6.6%, S&P −12%); parameters 4%/50%/60d/97% chosen on these episodes; Fed broad index, 2006+" |
| **6m rise ≥15%: 50% / 25%** | "12 months = 5 clusters (1974, 1981, 1993, 2008–09, 2015); spread hits from 3 clusters; the 25% recession figure is 3 months of one episode (1981)" |
| **DXY>105 → 20% vs 6%** | "22 of 25 hit-months are the 2000–02 dotcom bear; 1987 and 2008 began with DXY at 98 and 72" |
| **"S&P higher 12m after the dollar peak"** | "7 of 12 ex post, 10 of 12 from a real-time turn, vs 76% of all months" |
| **−30.6% gold** (2026) | "GC=F front-month 2026-01-29 → 2026-10-30, roll artefacts possible, unverified vs LBMA; FMP XAUUSD says −27%; DXY +5.7% and no funding stress over the same span — not a dollar-scramble pattern" |
| **gold trough leads dollar peak 0–111d** | "5 episodes; leads the EQUITY low by months with −10% to −21% still to come in 2008/2015/2018; valid for gold holders only" |
| **CP−bill / OFR funding "LEADING"** | "leads the dollar's peak by 87–144d in 2008/2022; coincident with crisis onset (2007-08-09 alarm = BNP week); silent in 2015–16 and 2018" |
| **$15.1tn / $129tn** | "stock at a record before every crisis and every calm year since 2010; yoy growth −0.5 corr with dollar, dollar leads by 1q; no predictive content as a level" |
| **−1.5% EM GDP per 10% dollar** | "Obstfeld-Zhou 2022, 26 EMDEs, panel LP, in-sample, 1990s–2019; a growth channel, not an onset predictor" |
| **"2022: +15% in six months after the freeze"** | "+12.5% at 6m, +18% to the Sept peak; first hike 16 days after the freeze; Evergrande RD 2021-12-09 precedes the freeze; DXY −10% Oct–Dec 2022 with sanctions intact; SWPT peak $11bn" |
| every "Johnson claims" | "as relayed by the user; Oct-2026 talk not located; his published band statements differ (125/135/170 in 2024)" |
