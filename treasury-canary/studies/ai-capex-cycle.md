# AI capex cycle — scoping study and the recommended build (rev 1, pre-build)

Casey's question (2026-10-31, after Spectra's "Wobbling"): chart the interrelationships of
the AI capex spend and use them to predict when the slowdown becomes a problem and how much
is already priced in. The working hypothesis: new technology → over-investment → companies
throttle back → delayed ripple through over-valued markets → crash; the cycle recurs in every
technology boom; it shows in equities, rates and bonds; canary companies fail first;
corrections are small earthquakes relieving pressure, long uninterrupted runs are seismic
build-up.

Status: SCOPING ONLY — nothing pre-registered, built or graded. Three finders (A history of
capex booms, B the measurable chain today with every endpoint probed, C the predictive
literature and test design) plus the orchestrator's own scoping computations (Ken French 49
industries 1926–2026, Fed Z.1 credit, EDGAR XBRL), reviewed by two adversarial verifiers
(numbers and data integrity; logic and design). Only numbers that survived review appear as
fact (corrected values used); UNVERIFIED items are labelled; the wording constraints the
logic reviewer imposed are honoured throughout. Finder notes, reviewer verdicts, scripts, charts
and the small data files are committed under `studies/ai_capex_cycle/`.

## 1. Verdict

1. **The chain is real, but one link is in the wrong order, and it is the link the hypothesis
   leans on.** In every capex boom we can measure, the sector's own equity peaked 0–13 months
   BEFORE the capex peak; the capex throttle then preceded roughly two-thirds of the broad
   market's loss and, in the debt-financed cases, the recession and the canary failures by
   8–31 months. So capex throttling is not an early warning of the equity top; it is the
   mid-bust confirmer after which most of the damage, and the recession, arrived. Credit
   spreads bottomed AT the equity peak and widened 18–36 months later; Global Crossing,
   WorldCom, Insull, Penn Square and Lehman failed 11–31 months after the top. The one leading
   canary in the record is an equipment vendor's guidance cut (Lucent, two months before the
   Nasdaq peak), on one observation.
2. **What predicts "a problem" with evidence is small and already known.** After a two-year
   +100% net-of-market industry run-up, US history gives a 53% chance of a 40% drawdown
   within two years (Greenwood–Shleifer–You, n = 40 in ~6 clusters; 80% at +150%;
   unconditional 14%). On the free Ken French file, GSY's own rule and net-of-market definition
   give a 40% crash rate on n ≈ 47–50 (the 53% needs CRSP's re-formed industries, or a stricter
   ratio-net screen that gives 53% on n = 60): the free data reproduce the direction and the
   ladder's shape, not the exact level. Run-up SIZE is the only price-path feature whose link to subsequent crashes
   survives treating the ~27 historical calendar clusters as the unit of evidence; volatility,
   acceleration and the count of intermediate corrections do not. Economy-wide credit growth
   is the multiplier that turns a bust into a recession (Jordà–Schularick–Taylor; the
   Harvard R-zone, 45% vs 4%).
3. **The earthquake analogy is untested, not refuted and not confirmed.** On 100 years of US
   industry data, whether a +100% run-up had intermediate corrections does not reliably
   predict whether it crashed: the raw association runs against the analogy, the
   volatility-matched association runs with it, and neither has a determinate sign once the
   27 clusters are the unit (cluster-bootstrap 90% interval for the zero-correction effect
   −0.6 to +0.8 log-odds). The one published result structurally like the analogy is
   prolonged LOW volatility predicting banking crises (Danielsson–Valenzuela–Zer, AUROC 0.76),
   at the country level, not the industry level.
4. **Where the AI cluster sits today.** Hyperscaler capex equals operating cash flow on a
   trailing-four-quarter basis (0.96; 1.17 in 2026Q3 alone, before finance leases and
   buybacks; 1.24 once Oracle's $11.4bn of customer capex prepayments are taken out of its
   operating cash flow, where Oracle itself nets them — Oracle alone runs at 2.4x) — the group has reached the point at which it depends on external finance,
   which is the feature that separated the busts that caused recessions from those that did
   not. Every company still guides 2027 HIGHER: what Spectra calls peak growth is a
   deceleration from +118% yoy, not a throttle; the historical transition that mattered was
   the capex LEVEL turning down. On the Ken French data the AI industries have reached +84%
   (Hardware) and +41% (Semiconductors) net of market over two years and have NOT met the
   +100% rule behind the 53%. The economy-wide credit gauge (business credit/GDP, 3-year
   change −4.5pp vs the +9pp danger line) is not armed — but it also did not arm in 2000Q1
   (+8.3pp), and the AI cluster's own debt wave (~2.1% of GDP) is already telecom-2000 scale
   and only partly visible in aggregate credit (leases, SPVs, private credit, vendor equity).
5. **Priced in.** None of the free measures is a measure of what is priced in; they are
   sentiment and positioning. The one honest statement the free data support: Nvidia trades
   at ~13x consensus FY28 earnings against ~26x trailing — a peak-cycle multiple; the equity
   market already discounts an earnings decline after FY28, its own version of "capex growth
   peaks in 2026–27". Whether the DECLINE's size is priced cannot be read from free data.
   Spenders are −7.7% YTD against recipients +71% and neoclouds +30% (−21% in three months);
   that is a fact about dispersion, not a phase label (n = 1 analogue, and our own finders
   disagree on the 2000 sequencing).
6. **Recommendation — build the option below**: an "AI capex cycle" tab on treasury-canary
   with three layers — (i) the descriptive chain (12 probed free series plus the existing
   $682bn issuance tally), (ii) a pre-registered PRESSURE GAUGE that places the AI industries
   as percentile ranks inside the historical run-up panel and shows that bin's realised crash
   rate with cluster-bootstrap bands — never a point probability for "AI" — with two scored
   features (run-up size, Δvolatility) and the earthquake variable DISPLAYED, not scored,
   until its pre-registered test passes, and (iii) dated, falsifiable THROTTLE-BACK TRIPWIRES
   with a forecast ledger. Plus the macro-transmission panel the dashboard is named for
   (capex's GDP contribution, the Treasury channel). What it cannot do: time the crash,
   separate the AI cluster from the market, or quote a crash probability.

## 2. What the record says about the chain (finder A; 7–10 heterogeneous episodes)

| Episode | Sector equity peak → capex peak | Spreads | First big failures vs equity peak | Market drawdown | Recession ≤ 24m |
|---|---|---|---|---|---|
| UK railways 1845–50 | shares Aug-1845 → capex 1847 (annual data) | n/a | 1847 banking crisis | FT-100 proxy −34% | yes (1847) |
| US railroads 1873 / 1893 | failure WAS the trigger (Jay Cooke Sep-1873; Reading Feb-1893) | n/a | 0 | severe | yes / yes |
| Electrification 1929 | Aug/Sep-1929 → utility construction 1929–30 (annual) | Baa–Aaa low 1.00pp Feb-1929, peak 5.64pp May-1932 | Insull +31m | −84% | yes (began Aug-1929) |
| Oil/gas drilling 1980–82 | Oil equity Nov-1980 → rig count Dec-1981 (weekly data, +13m) | low Jun-1980s… | Penn Square +20m | −16% (bank-failure wave 7 yrs) | yes (Jul-1981) |
| Japan 1989–93 | Nikkei Dec-1989 → business investment 1991 (annual) | no blow-out | banks 1995–97 | −63% in 32m, −80% in 13y | mild |
| Telecom/fiber 1996–2003 | Nasdaq telecom 10-Mar-2000 → real comm-equipment Q4-2000 (quarterly, +9m); structures Q4-1999 led (−3m) | Baa–Aaa low 0.55pp Jan-2000, peak 1.41pp Oct-2002 | Lucent warning −2m; Winstar +13m, Global Crossing +22m, WorldCom +28m (8 months after the recession ended) | −45% (KF) / Nasdaq −78% | yes (Mar-2001) |
| Shale 2010–16 | Oil equity Jun-2014 → capex FY2014 (coincident) | low 0.55pp Jun-2014, peak 1.49pp Dec-2015 | 2015–16 HY defaults | −6% | no |
| China 2009–16 | policy-managed glide path | — | deferred to 2021 | −43% equity in 10 weeks | no |

Telecom in depth: BEA communications-equipment investment $70.8bn (1996) → $123.3bn (2000; 1.20%
of GDP, 16.1% of all equipment) → $83.7bn (2002); the telephone industry's investment/capital ratio
hit 33% in 2000, the highest since 1948. Nonresidential fixed investment contributed +1.18pp to GDP
growth in 2000 and −0.99pp in 2001 (Q4-01: −1.56pp); communications equipment alone was a −3.9pp
drag on equipment growth in 2001. Financing: $192bn of HY issued by telecom and cable 1997–2000 (~1.9%
of 2000 GDP); vendor financing commitments Lucent ~$7bn, Cisco $2.5bn, Nortel $2.1bn; telecom and
media ~35% of the HY index at end-2000; 2001 HY defaults a record $78.2bn (12.9% rate vs 5.9%
ex-telecom). Share of the sector's peak-to-trough loss that came AFTER the capex peak: 44% (Telcm
2000), 40% (Chips 2000), 40% (Oil 1980–82), 55–61% (1929 utilities/electrical); share of the
MARKET's loss after the capex peak: 61–67% in every debt-financed episode.

Where the hypothesis does not match: equity-financed booms ended without a credit crash or recession
(PC 1983–84: Comps −18%, no recession; internet pure-plays were 6% of market cap and almost debt-free —
the 2001 recession came from the debt-financed telecom leg); Japan and UK railways deflated over years
rather than crashing; monetary tightening preceded most peaks (Fed +175bp to May-2000; BoJ +350bp;
Fed 3.5→6% 1928–29; BoE 8% Oct-1847) and is the better-fitting proximate trigger. Recession followed
in 7 of 9 capex busts and in all 6 that were debt-financed with tightening into the peak — hand-tallied,
ex-post classification, UNVERIFIED as a statistic; in 1929 and 1981 the recession began before or with
the capex peak.

## 3. The AI capex chain as it can be measured today (finder B; every endpoint probed 2026-10-31)

```
SPENDERS ──capex──► RECIPIENTS ──► MACRO           FINANCING ◄── spenders        DEMAND / MONETISATION
MSFT AMZN GOOGL     NVDA AMD AVGO   BEA info-proc   OCF (XBRL) capex/OCF 0.96 TTM  RPO: MSFT 683 ORCL 664 GOOGL 568
META ORCL (XBRL)    MU TSM Hynix    equip $934bn    bonds: EXISTING TAB $682bn     CRWV 104 AVGO 179 ($bn, XBRL)
$231bn 2026Q3       TSMC monthly    SAAR, +41% yoy  finance leases (MSFT $71bn)    cloud revenue (FMP segments)
+118% yoy           rev +54.6% yoy  0.86pp of Q3    SPVs (8-K text), vendor equity GPU rental spot (RunPod, 1 vendor)
+ CRWV NBIS, labs   DRAM spot       GDP growth      NVDA non-marketable stakes     useful-life changes (EFTS)
(commitments only)  NVDA DSO 59.6d  Census DC       $1.3bn Jan-24 → $47.9bn Jul-26 depreciation vs capex
                    DIO 119d        $85bn SAAR +73%
PRICING-IN (free): CBOE iv30 NVDA 44 ORCL 55 CRWV 107 MSFT 27; VXN 28.5; FINRA short interest; ORCL 5.95% 2055
at 73.6 (Boerse Frankfurt; must be shown as a spread); dispersion spenders −7.7% / recipients +71% / neoclouds +30% YTD.
NOT free: consensus capex and its revisions (not in FMP), CRWV bonds/CDS, private-lab spend, SPV terms,
GPU utilisation, the power/permit pipeline (PDFs only).
```

Leading / coincident / lagging for a cash-capex throttle (reviewer-corrected): LEADING — guidance
language (8-K ex99.1 / calls; the detector must catch "moderate the pace", "more measured", "digest",
not only "reduce"), accrued capex (`CapitalExpendituresIncurredButNotYetPaid`, GOOGL $35.9bn) and
purchase commitments (META $355.7bn), one quarter ahead of cash. COINCIDENT — TSMC monthly revenue
(reporting lead of 1–2 months), RPO (a record of contracts signed; ORCL's $664bn is dominated by one
unfunded counterparty, so show RPO/revenue and the lab-backed share, not the level). LAGGING — Census
data-center construction (put in place, 2-month lag, 6–12 months behind orders), BEA equipment
contribution, useful-life changes. Single-name distress reads (CRWV iv30 107, short interest +27% in
a month) are tripwires, not cycle indicators.

The circular ring, from 8-K accession numbers (amounts after mid-2026 to be re-read from the filings
on the production box; www.sec.gov rate-limited this session): CoreWeave–OpenAI $22.4bn capacity;
Nvidia–CoreWeave $6.3bn backstop to 2032; AMD–OpenAI 6 GW with a 160m-share warrant; Oracle–OpenAI
~$300bn (counterparty never named by Oracle, UNVERIFIED); Nvidia–OpenAI LOI up to $100bn; Microsoft–
OpenAI $250bn Azure commitment; Amazon–OpenAI $38bn; Meta–Blue Owl Hyperion $27bn. The one free
quantitative aggregate of the ring is Nvidia's non-marketable equity line: $1.3bn (Jan-24) → $47.9bn
(Jul-26), to be read with Nvidia's DSO (59.6 days, from 45 a quarter earlier). Circularity is material
on the RECIPIENT side (Nvidia revenue from counterparties it finances); on the spender side lab
revenue is low-single-digit % of ~$740bn TTM OCF, so capex/OCF is a lower bound on external-finance
dependence, not an inflated ratio.

## 4. Predicting "when it becomes a problem": what has evidence (finder C + scoping)

| Method | Evidence | Free data | Verdict for the build |
|---|---|---|---|
| GSY industry run-ups (2019) | 40 US episodes 1928–2012 + 107 international OOS: P(40% drawdown ≤ 24m) 14% → 20% at +50% → 53% at +100% → 80% at +150% net of market; mean 24m return ≈ 0; discriminators: acceleration, rising volatility, issuance, young-firm tilt, high CAPE — NOT turnover, NOT sales growth | Ken French 49 industries (replicated: n = 60, 53%) | the backbone of the gauge; SIZE is the scored feature |
| GHSS "R-zone" (2022) | 3-yr business credit/GDP > +8.99pp AND equity > +26.6% → 3-yr crisis probability 45% vs 4%; real-time OOS R² 4.2% | Z.1 / BIS on FRED | display as a "2008-type multiplier" panel; did NOT fire in 2000Q1 (+8.3); not a scored input |
| Baron–Xiong / JST | +1 SD bank-credit expansion → +5.4pp 3-yr bank-equity crash probability; unleveraged equity bubbles cost ~0 GDP, leveraged −3.6 to −4.5% | JST macrohistory, free | the reason capex/OCF and the issuance tally sit at the centre |
| DVZ prolonged low volatility (2018) | predicts banking crises OOS, AUROC 0.76 | yes | the only published cousin of the earthquake claim; country level |
| Investment anomalies (Titman–Wei–Xie, Cooper–Gulen–Schill) | 2–8%/yr cross-sectional spreads; aggregate weak | XBRL from 2009 | firm-level screen, not a timing tool |
| LPPLS / Sornette, SOC, Minsky/Perez stages | no audited OOS record; descriptive; undated | open code | CUT |
| Earthquake (intermediate corrections) | no direct test in the literature; our scoping: undetermined (see §1.3 and the chart) | yes | DISPLAY months since the last 10%/20% correction; score only if H4 passes |

Scoping results (not pre-registered; charts in `ai_capex_cycle/figs/`, reproduced exactly by the
number verifier's independent implementation): on 408 raw +100% two-year run-ups (27 clusters) the
crash rate is 25% vs a 14% base rate; by run-up size terciles 12/24/40%; by volatility 12/32/32%; by
corrections 23/21/35%. The corrections point estimate survives every cut (24- and 12-month cooling,
≥10 firms, net-of-market outcome, all three together: 7% vs 20%) — but corrections and volatility are
the same variable (rank-correlation +0.75), 60% of the "crashes" coincide with a ≥30% market fall,
under a cluster bootstrap only size keeps its sign, and in the small GSY-rule panels (n ≈ 47–60) the
sign flips with the net-of-market definition. Post-crash rebounds are the SAFE run-ups (7% vs 30%).
Under GSY's exact rule the free file gives n ≈ 47–50 and a 40% crash rate (GSY: 53%). Finder C's
positive control (GSY's acceleration spread) shows no effect on this panel under our proxy definition;
the study must pre-register what happens if it fails under GSY's exact definition (the gauge collapses
to size alone and GSY's characteristic results may not be quoted as applicable).

## 5. The recommended build — "AI capex cycle" tab on treasury-canary

**Layer 1 — the chain, descriptive (build first, ~1 week).** The 12 probed series: hyperscaler capex
and capex/OCF (TTM headline; quarterly and per-company; finance leases shown separately); the guidance
ledger (dated, by company, from FMP transcripts with the EFTS fallback); RPO stack with RPO/revenue and
lab-backed share; BEA information-processing equipment level and GDP contribution; Census data-center
construction; TSMC monthly revenue; Nvidia DSO/DIO/non-marketable equity; spender/recipient/neocloud
dispersion (displayed as dispersion); CBOE iv30 for the four names and VXN; ORCL long bond as a SPREAD
to Treasuries; FINRA short interest; GPU rental and DRAM spot (labelled single-vendor). Plus the
macro-transmission panel: capex's contribution to GDP growth with the 2000→2001 swing (+1.18 → −0.99pp)
as the overlay, and the Treasury channel (net UST supply vs the cluster's issuance, term premium) from
the existing tab. Historical overlays aligned on OBSERVABLE dates (capex peak quarter, guidance cut),
never on the ex-post equity peak. The AI-debt tab's $682bn tally and breaking indicators stay where
they are and are linked.

**Layer 2 — the pressure gauge, pre-registered (SPEC v0 → two reviews → one scored run → two
verifiers; ~2 weeks).** Panel: Ken French 49 industries 1926–2026 (+ market, CAPE, 10-year yield).
Episode rules frozen in the SPEC: GSY primary (raw and net +100%, 24-month merge, ≥10 firms) as
confirmatory; the 50%/50% secondary panel (n ≈ 180–250) as the powered primary. Scored features: run-up
size (net of market) and Δvolatility. Displayed-only features: acceleration (GSY's exact definition),
months since the last 10% / 20% correction, the correction count. Outcomes: 24-month max drawdown, raw
AND net of market; crash = 40%. Unit of evidence: calendar clusters (leave-one-cluster-out; cluster
bootstrap for every interval). Hypotheses: H3 the positive control (GSY ladder and acceleration spread
reproduce on the free file) with the H3-fails branch pre-registered; H1/H2/H4 the earthquake variable
(H4 = incremental over size, acceleration and Δvol is the one that matters; power at the primary
threshold ~0.2 for a 15pp effect, so a null is uninformative and is reported as such). Output on the
tab: for each AI industry (Chips, Hardw, Softw) its percentile rank of run-up size and Δvol in the panel,
the realised crash rate of that bin with the cluster-bootstrap band, the statement of whether the GSY
rule is met (today: no), and the panel's calibration curve so "wide" is visible. Forbidden on the tab:
"P(crash) = X%" for AI, a Wilson interval, the word out-of-sample next to a single number.

**Layer 3 — tripwires and the forecast ledger (with layer 1).** Dated, falsifiable, each with the
action it implies and a 60-day review: (a) any hyperscaler guides 2027 capex BELOW 2026 (level turn,
the historical transition that mattered); (b) guidance language shifts to "moderate / measured /
digest" at two of five; (c) accrued capex or purchase commitments fall quarter-on-quarter at two of
five; (d) TSMC monthly revenue growth below +20% yoy for two months; (e) Nvidia DSO above 60 days with
non-marketable equity still rising (vendor financing substituting for demand); (f) capex/OCF TTM above
1.0 while the cluster's bond issuance exceeds its OCF shortfall (external finance taking over); (g) an
AI industry crosses GSY's +100% net-of-market rule; (h) the R-zone arms (+8.99pp). Every tripwire
logged with the date it fired, the reading, and what the market did in the following 3/6/12 months —
the dashboard's own out-of-sample record, which is the only one that will ever exist for this cycle.

**What this cannot do**: time the crash; separate the AI cluster from a market-wide bear; see private
credit, SPV terms or GPU utilisation; measure consensus revisions (paid). **What to buy if it matters**:
consensus capex and revision history (Visible Alpha / Bloomberg), single-name CDS (S&P GMI), FINRA
TRACE registration (free) for neocloud bond prices.

## 6. Honesty box

- n is small: 7–10 historical capex episodes, heterogeneous in financing and monetary regime; GSY's
  40 run-ups cluster into ~6 periods; our 408 into 27. Any base rate has effective n < 10.
- The scoping numbers are not pre-registered; the gauge's numbers will come from one scored run on a
  frozen SPEC with independent verification, as the other studies here.
- "Equity leads capex" is partly the null (capex put in place lags orders by construction); it is a
  real lead only on the episodes with quarterly or weekly capex data (telecom +9m, drilling +13m).
- Capex/OCF 0.96 is TTM; 1.17 is one quarter (Amazon's OCF is Q4-heavy); it excludes finance leases
  (MSFT $5.2bn, AMZN $1.5bn in Q3) and buybacks, so the external-finance gap is larger than shown.
- The R-zone did not fire in 2000Q1 on Z.1 (+8.3pp; +8.5pp on the BIS series, marginally over);
  it is calibrated to banking crises, not tech-capex busts. GHSS use IMF total credit to nonfinancial
  businesses, so Z.1 total business debt is the closer analogue; today −4.5pp (Z.1), −6.7pp (BIS,
  2025Q4).
- Oracle's operating cash flow carries customer capex prepayments ($11.4bn in the latest quarter,
  $4.6bn the quarter before) that are not a us-gaap tag; the build must text-extract them from the
  8-K and show capex/OCF both ways.
- Finder C's drafted outcome ("drawdown from the trigger-month level") is stricter than GSY's
  running-peak crash; the SPEC must use the running-peak definition it cites.
- The Ken French file is CRSP vintage 202609 (sha256 633958bf… / factors a3894d74…), not committed
  (2.3 MB); re-downloadable from Ken French's library.
- The circular-deal amounts after mid-2026 are from announcements, not re-read filings (VERIFY on the
  production box); Oracle has never named its $300bn counterparty.
- Vendor guidance as "the leading canary" rests on one observation (Lucent −2m; Nortel was +11m).
- Priced-in: nothing here measures it; the Nvidia multiple statement assumes consensus is not stale.
- Monetary tightening preceded most historical peaks; the current Fed path is not established in
  this material and must be stated before that conditional is used.

## 7. Pending questions (ranked; 60-day expiry from first ask)

| P | question | would move | status |
|---|---|---|---|
| P1 | Does Casey want layer 2 pre-registered now (2 weeks, two verifiers) or layer 1 + tripwires first (1 week) with layer 2 after the first R1 review? | the build order | asked 2026-10-31 |
| P1 | Which AI industries define "the cluster" for the gauge (Chips, Hardw, Softw; ElcEq for power equipment?) and is a multi-industry episode one draw or several correlated ones? | the gauge's reading | asked |
| P2 | Re-read the post-mid-2026 8-Ks (NVDA 2026-08-17, CRWV 2026-09-17) for the circular-deal amounts | layer 1 ring table | asked |
| P2 | Is consensus capex worth buying (Visible Alpha / Bloomberg) — the only way to reproduce Spectra's "estimate cut" | priced-in layer | asked |
| P2 | FINRA TRACE free registration for neocloud bond prices | tripwire (e) quality | asked |
| P3 | ERCOT / Texas PUC permit pipeline: any machine-readable source | tripwire on the power leg | open |

## 8. Counter-agent verdicts

Reviewer 1 (numbers and data): finder A PASS (all 8 dated claims reproduce from fresh FRED/PDF
data); finder B PASS_WITH_FIXES (every number reproduces from a fresh EDGAR re-pull of six CIKs,
FMP and the press releases — Amazon's $77.3bn is a true 91-day figure; Oracle's $23.1bn OCF is
genuine but carries $11.4bn of customer capex prepayments, the S-1 fix above); finder C
PASS_WITH_FIXES (every quoted paper figure matches its extracts; its drafted crash outcome is not
GSY's definition); scoping PASS_WITH_FIXES (headline table reproduced exactly by an independent
implementation; correction counter verified on 12 hand-made sequences; no look-ahead; the "GSY-strict
53%" label used a ratio net-of-market definition GSY do not use — corrected to 40% on n ≈ 47–50).
No BLOCKING finding. Reviewer 2 (logic and design): PASS_WITH_FIXES — two
BLOCKING corrections to the orchestrator's own readings (the earthquake panel's outcome is mostly the
market's crash and has ~5 crash clusters, so neither reading was supported; a gauge quoting 53% next to
an AI cluster that has not met the rule would mislead), five SERIOUS rewordings (equity-before-capex
re-orders one link, does not refute the chain; the R-zone did not fire in 2000; the positive control
may fail; the chain's lead/lag labels and the dispersion "phase" claim; the 6-of-6 tally is ex post).
All applied above; the allowed and forbidden sentences are honoured.
