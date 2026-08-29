# EVIDENCE — what the research established

Produced by a 32-agent recon (15 research tracks, each adversarially verified by a
second agent with its own independent data pull, then synthesised and critiqued).
Run `contrarian-swarm-recon` / wf_07a613af-bcb, 2026-08-29. 4.6M subagent tokens,
1,632 tool calls, 0 agent errors.

Read this before proposing anything. Twelve claims were **killed** on verification,
several of which would have put on losing trades — they are listed in full below so
that no later pass resurrects them.

---

## Verdict


Not buildable as described. "Find crowded trades → take the opposite side → get high conviction" fails on four independent axes, three of which are settled by verified evidence rather than opinion.

(1) DIRECTION. The published sign in Casey's exact universe runs the other way. Fan/Fernandez-Perez/Fuertes/Miffre earn 4.12%/2.51%/4.03% (commodities/FX/equity index) going LONG where speculators are net long; Brown-Howard-Lundblad find crowded institutional holdings earn HIGHER average returns; Sias-Turtle-Zykaj find hedge-fund demand shocks positively predict returns even in extreme stress; Moskowitz-Ooi-Pedersen find 12-month momentum predicts positively across 58 futures. Both named practitioners disavow the premise in their own words — Soros: "to bet against prevailing expectations is far from safe... I have become a confirmed anti-contrarian"; Druckenmiller: "I don't care if a trade is crowded, if I think the thesis is right and the trend is with me." A system that fades crowding is short three published premia to capture one.

(2) IDENTIFICATION. "The crowd" is not a well-defined object. Two CFTC trader categories from the same report on the same Tuesday produce opposite trades with comparable t-statistics (fading leveraged funds -0.256%/4wk, t -2.18; fading asset managers +0.321%, t +3.17). The primitive the whole architecture rests on is unidentified.

(3) MEASUREMENT. What crowding predicts is the SHAPE of the return distribution — crash probability, negative skew, drawdown severity — not the mean. The one exception matters and cuts the other way: above a ~125% two-year run-up, Greenwood-Shleifer-You DO find significantly negative excess returns (-28%), and say their Fama-is-right conclusion "must be substantially tempered." So the correct architecture emits hazards below that band and may emit a directional view only inside it.

(4) THE LLM LAYER IS THE WRONG INSTRUMENT FOR THE VARIANT PERCEPTION. On contamination-free future events four frontier models issued an identical top pick in 92% of cases, none beat the market's Brier, and fading the market was unprofitable for all four. Models carry a measured built-in CONTRARIAN and large-cap-tech prior that persona prompts, voting and debate do not remove — so a swarm asked to find contrarian trades will emit contrarian-sounding output regardless of the data, and the label is confounded with the model's prior.

THE FORM THAT IS BUILDABLE, and worth building:

A HAZARD-AND-EXPOSURE INSTRUMENT THAT MOVES NO CAPITAL IN V1. It emits three things and nothing else: (a) dated P(drawdown ≥ 40% within 24 months) forecasts scored by Brier against a published base rate; (b) a position-size and tail-hedge multiplier — crowding as sizing discipline, which is the one use Casey's own repo has already validated (the trim-to-75% rule on the crowded state improved MAR 0.156→0.164 and cut max drawdown 56.8%→53.6% while the same state's directional stats were p=0.84 with halves disagreeing); (c) a watchlist of instruments where a named forced-flow mechanism has a dated trigger.

Direction, when taken at all, comes from a MECHANISM WITH A PUBLIC PRECOMPUTABLE TRIGGER — mandate/regulatory constraint, margin or collateral trigger, index or roll rule, dealer balance-sheet date, or the Composer cohort's own published RSI levels — never from a positioning percentile. The Composer probe is the genuinely novel asset here: an exact, level-specific map of a fully-enumerable 2,659-strategy mechanical cohort's pre-committed rotations, which is the only place in the entire evidence base where mechanism, trigger level and timing are all knowable in advance from free data.

Escalation is P&L-confirmed and mechanically gated, defaults to half-Kelly or below with a drawdown-budget ceiling, and no LLM-emitted number ever touches the sizer. The swarm is a research logger that earns the right to size by accumulating calibration, not a trading system that earns trust by making money — because a monthly-marked, negatively-skewed book needs 35-67 months to establish merely that its Sharpe is positive, and a genuinely good system has a ~19% chance of looking broken for three straight years.

BLOCKER BEFORE ANY BUILD: no free price source for individual equities or ETFs was ever verified in the probes. FRED carries no single names and its SP500 is licence-truncated to ~10 years. Without that, the system can compute a crowding score and can never score whether it worked — no backtest, no calibration ledger, no honesty-box numbers. Close that first or nothing else matters.


---

## Design principles

Each is imperative and specific enough to constrain code.


### P1

**Never emit a position from a crowding reading alone. A candidate reaches the sizer only when its record carries (a) a named forced-flow mechanism from a closed enum {mandate/regulatory constraint, margin or collateral trigger, index or roll rule, dealer balance-sheet date, published mechanical trigger level}, each with a last_validated_date, AND (b) a dated, machine-checkable trigger. Merge-blocking test: reject any candidate whose only support is a positioning percentile.**

*Why:* Raw hedging pressure has zero predictive power (t=-0.43). The signal appears only after decomposing into a 52-week smoothed insurance component (t=3.35) and a short-horizon liquidity component with the OPPOSITE sign that fully decays within 20 trading days. A single 'positioning score' is a blend of two premia with opposing signs plus noise, and a level percentile has no timing content in any model reviewed.

*Citation:* Kang, Rouwenhorst & Tang, JF 75(1):377-417 — CONFIRMED verbatim independently in three tracks, including the 67bp/20-day liquidity spread and 'After 20 trading days, there is no significant difference'.


### P2

**Make the ledger's forecast primitive P(drawdown >= 40% within 24 months), with X and N declared at intake and scored by Brier at resolution. Forbid the crowding module from emitting an expected-return forecast unless the instrument's trailing 2-year run-up exceeds 125%. Print the unconditional base rate (14% two-year, 11% post-1970, 24% international) beside every conditional number, and use ~11-12% as the three-year macro denominator, never the 4.0% ANNUAL crisis rate.**

*Why:* A 100% two-year run-up lifts crash probability from ~20% to 53%, and 150% to 80%, while below ~100% a sharp price increase does NOT predict unusually low forward returns. But at >=125% the authors reverse themselves: 24-month raw returns fall below -13% and excess to -28%, significant at 10%, with 'our earlier conclusion that Fama is correct about average returns must be substantially tempered.' The base-rate horizon error is the other half: comparing a 45% THREE-year conditional to a 4.0% ANNUAL unconditional inflates the lift by ~3x and would miscalibrate every Brier score in R2.

*Citation:* Greenwood, Shleifer & You, 'Bubbles for Fama', JFE 131 (2019) — CONFIRMED in two tracks; the >=125% return result and the base-rate horizon both surfaced on adversarial verification.


### P3

**Compute every crowding score under at least three pre-registered trader definitions frozen in a config file BEFORE any backtest — TFF leveraged money, TFF asset manager, disaggregated managed money — plus a price-momentum control. If the definitions disagree on sign, force NO-TRADE and print the disagreement in the honesty box rather than letting an agent resolve it. Adding a definition after seeing results is logged as a registered trial.**

*Why:* Two equally defensible categories from the same report on the same date produce OPPOSITE trades with comparable t-statistics: fading leveraged funds -0.256% per 4 weeks (t -2.18) versus fading asset managers +0.321% (t +3.17), n=6,697 weekly observations across 9 macro futures. CFTC's own notes concede classification is judgment-based and that reportable positions cover only 70-90% of open interest.

*Citation:* Own COT computation, independently re-run and reproduced exactly by the counter-agent; CFTC Explanatory Notes (quotes verbatim, though scoped to the legacy commercial split rather than TFF).


### P4

**Define hedging pressure as commercials' NET SHORT divided by open interest and gate-test the sign against a frozen fixture. The significant positive loading on smoothed HP means BUY when smoothed commercial net-SHORT is high. Condition the fast liquidity leg on a hedger-drawdown state variable, not on the level of smoothed HP.**

*Why:* Commercials are net short in 71.3% of weeks and average HP is positive for 25 of 26 commodities, so coding the sign as 'positive on commercial net-LONG' puts the months-to-quarters leg on the wrong side of every contract — and it will look plausible on a dashboard because the fast leg is coded correctly. Separately, the 8.9bp-to-21.2bp amplification is conditioned on 'weeks following a large capital loss of hedgers', not on high hedging pressure; gating on the wrong variable will fail to reproduce the published effect in a way that resembles a data bug.

*Citation:* Kang, Rouwenhorst & Tang — the inversion was caught as a merge-fatal in the why-market-wrong verification pass; the conditioner error was caught independently in crowding-measurement.


### P5

**Key every COT ingest off the RELEASE timestamp (Friday 15:30 ET, holiday-shifted), never the as-of Tuesday. Stamp every crowding reading with report_date. Refuse to emit any recommendation whose only novel input is dated more than 2 trading days before the decision date.**

*Why:* The data-to-publication lag is exactly 3 days and was observed live during verification (rowsUpdatedAt 2026-08-28T19:30:08Z = Friday 15:30:08 EDT, with max report_date flipping 2026-08-18 to 2026-08-25 at that instant); a mid-day-Friday read is looking at 10-day-old positioning. 21bp of KRT's 67bp four-week spread (t=3.04) accrues in days 1-4, before publication, so roughly a third of the published edge is structurally unreachable. Do NOT justify this with the '~40% of the move already happened' figure — that is the sqrt(4/24)=40.8% random-walk identity, reproduced at 41.0% in simulation.

*Citation:* CFTC release schedule + live Socrata probe with the update event directly observed; KRT days-1-4 spread; random-walk null verified by 200,000-path simulation.


### P6

**Assert max(date) >= today - N_days on EVERY feed as a merge-blocking gate, and assert response-hash VARIATION across distinct date parameters. Treat a 200 response with well-formed content as no evidence of freshness whatsoever.**

*Why:* Cboe's put/call CSVs — the most commonly cited free positioning feed — return HTTP 200 with plausible headers and a last row of 2019-10-04, across all six files. OCC's volume-totals endpoint silently ignores its report_date parameter, returning byte-identical payloads (MD5 d7236ea764fa04ef03678fbbfbe96026) for 20260827, 20260731, 20250827 and 20200320, so any backtest passing a date would produce a flat constant series with no error.

*Citation:* Live free-feed probe; both traps independently re-verified by the counter-agent.


### P7

**Set the escalation ceiling from a drawdown budget, not a size multiple: c_max = 2/(1 + ln p / ln(1-d)) for Casey's chosen (p, d). Default to half-Kelly or below. Apply the same stationary-block-bootstrap shrinkage envelope and the >25%-of-resamples-non-positive kill rule to the ESCALATED size, not only the initial size — reuse btc-paper-engine/backend/app/engine/kelly.py verbatim (kill rule confirmed at line 155-158).**

*Why:* c=1.5 and c=0.5 give identical 75% of maximum growth but 0.794 versus 0.125 probability of ever drawing down 50%, so the asymmetry makes the cap non-negotiable. Full Kelly loses money on 12.4% of 700-bet paths even with a genuine 14% edge on every bet (skewness 35, kurtosis 1299). And for a log-utility sizer, error in the MEAN is 5.4x (RT 25) to 56.8x (RT 75) more damaging than covariance error — the escalation step is precisely where a plug-in mean estimate does the most damage.

*Citation:* MacLean/Thorp/Ziemba 'Good and Bad Properties of the Kelly Criterion' (fractional-Kelly laws re-derived independently); MacLean/Thorp/Zhao/Ziemba Table 2; Chopra-Ziemba as reproduced in MTZ Table 1 — column labels corrected on verification to means:variances:covariances = 5.38:1.67:1 at RT 25.


### P8

**Escalate size only on realized, marked P&L confirmation of the thesis, ANDed with the trigger having fired. Forbid any LLM-emitted confidence, probability, narrative-adoption score or 'conviction' number from entering the sizing function by ANY route; agent probabilities go to the ledger for calibration scoring only. Adopt barbell-lab/src/barbell/edge/statemachine.py's check contract so a blind or stale feed automatically halves size rather than being ignored.**

*Why:* The best-documented Soros escalation instruction came after the position was already working — confirmation by P&L, not by further analysis. On the model side, none of 11 frontier and open-weight models reaches the 90% interval-coverage target (top performers >=10pp short), calibration degrades sharply at extreme magnitudes, and more capable models make WORSE tail forecasts — the exact regime a slugging book lives in. Druckenmiller's own dominant failure was emotional re-entry, an execution failure a keyless machine avoids only if the sizer is mechanical.

*Citation:* Schwager, New Market Wizards, Druckenmiller chapter (CONFIRMED); QuantSightBench coverage failures and the inverse-scaling tail result (CONFIRMED); Lost Tree Club 2015, 'I didn't learn anything. I already knew that I wasn't supposed to do that' (CONFIRMED verbatim).


### P9

**Cap the crowding channel below the top severity band — a crowding reading alone can never reach RED or high-conviction; only a confirmed release/unwind event can. Wire crowding to position SIZE and tail-hedge budget, never to direction. Use the existing (benign, yellow, red, extreme, higher_is_worse, cap=79) anchor-tuple pattern in treasury-canary/backend/app/metrics/pins.py, and note that cap=79 is NOT a repo-wide rule today (2 of 4 crowding anchors carry cap=100) — make it a hard rule for the new channel.**

*Why:* Casey's own pre-registered, counter-agent-verified study says the crowded state is 'not distinguishable from baseline (p=0.84; halves disagree on direction)' and 'NOT a sell signal - momentum usually continues (78% positive 3m)' while owning the study's worst left tail (-40.3% worst 12m) — yet the mechanical trim-to-75% rule built on it improved MAR 0.156->0.164 and cut max drawdown 56.8%->53.6%. That is the whole evidence base in one line: crowding is sizing discipline, not prediction. The parallel leverage study is stronger: mechanically de-risking on BLOWOFF REDUCED risk-adjusted returns because 'historical crash damage lands after BLOWOFF ends, in SQUEEZE/WASHOUT months.'

*Citation:* treasury-canary/backend/app/api/routes_margin_fast.py FAST_PLAYBOOK; treasury-canary/backend/app/metrics/crossasset.py LEVERAGE_PLAYBOOK line 205 — both read directly from the repo during synthesis.


### P10

**Partition the evidence across agents into disjoint slices (COT/positioning; price/vol/term structure; supply-demand and physical fundamentals; narrative corpus) plus a small shared public set. Never give every agent the same open web search. Put the counter-agent ONLY on verification, with its own independent data pull and its own code execution, and forbid critic-to-generator narrative feedback.**

*Why:* With identical evidence, deliberation collapses into herding and the multi-agent system reduces to a single agent; designed information asymmetry buys 12-18% Brier improvement and 4-8pp accuracy on 375 real prediction-market questions. Self-verification with identical tools fails; a separate critic with code-execution grounding is the only debate configuration that significantly exceeded single-agent on a generative task. Critique improves error DETECTION (+27.4pp F1, d=1.0) and degrades GENERATION — the magnitudes come from a data-cleaning domain and must not be quoted, but the benefit CONDITION is what the authors claim generalizes, and it matches the repo's existing counter_agent_verdict pattern exactly.

*Citation:* InfoDelphi / PolyGym (CONFIRMED); the multi-agent-debate-for-data-cleaning factorial (CONFIRMED numbers, domain scope corrected on verification).


### P11

**Mandate cross-vendor model heterogeneity and instrument measured N_eff from pairwise error correlation on the dated forecast ledger; fail the build if N_eff < 2. Delete persona-based 'diversity' entirely — do not spend tokens on a momentum-agent / value-agent / macro-agent / skeptic-agent cast over one model. Default to independent-then-aggregate with a mechanical, non-LLM aggregation rule; any debate round must beat a self-consistency baseline at equal token spend in an A/B gate test or it does not ship.**

*Why:* Same-lineage agents produce pairwise error correlations of rho=0.70, collapsing ten agents to ~1.4 effective forecasters, and N_eff stays flat from N=5 to N=40; the 10-agent market (67.6%) failed to match a single standalone agent (70.2%). Prompt-level persona injection shows no significant advantage over a length-matched control and neither reduces ensemble error correlation nor improves Brier score. Multi-agent debate fails to outperform chain-of-thought and self-consistency across 5 methods, 9 benchmarks and 4 models, and majority voting alone accounts for most of the gain attributed to debate.

*Citation:* DPO-monoculture study; persona-injection null; MAD systematic evaluation + Debate-or-Vote — all CONFIRMED. Caveat to carry: the cross-vendor mitigation (rho 0.68->0.40) is measured on 8B/70B open models while the one frontier datapoint is r~0.77, i.e. worse.


### P12

**Blacklist three expression classes for any thesis with a resolution horizon beyond ~1 month: leveraged-inverse ETFs, long-volatility ETPs, and cash shorts on names with short interest >20% of float or days-to-cover >5 (force those to defined-loss structures). Compute bleed LIVE as -k*sigma^2 + (1-L)*rf - fee MINUS a per-fund empirically measured financing shortfall, with k=(L^2-L)/2, and report the MEDIAN path, never the mean.**

*Why:* k=(L^2-L)/2 means a -1x inverse carries the same drag coefficient as a +2x long. Measured 12-month flat-market medians: SOXS -34.4%, SQQQ -22.5%, SPXU -16.9%. VXX loses in 90.8% of 12-month windows (CAGR -51.9%), UVXY in 96.3% (-80.2%). The (1-L)*rf carry credit is NOT delivered in practice — measured intercept shortfalls run from SH -0.06 to SOXS -4.51 pp/yr, so -2x is not carry-positive on any tested underlying, and that shortfall is itself the borrow/financing cost the tracks declared unmeasurable. At L=-3, sigma=25% the Monte Carlo MEAN is ~0 while the MEDIAN is -24.7%, so quoting expected return hides the typical outcome. GME reached ~140% of float short; short sellers lost $6bn in a month and Melvin lost 53%.

*Citation:* Own computation on dividend-adjusted daily closes — every figure independently reproduced by the counter-agent; the closed-form drag kernel is our own derivation, NOT from the SEC bulletin it was originally cited to.


### P13

**Log every configuration the swarm evaluates — including agent-generated theses it discards — as a trial in a registry, and deflate every published Sharpe against that N using a MEASURED cross-trial Sharpe dispersion, never an assumed one. Apply a single named 0.42x constant to any published effect size entering EV, and no gentler than 0.42x to in-house mined signals. Log N_eff = 1/HHI over |P&L| shares alongside raw trade count in every study.**

*Why:* 45 independent model configurations on 5 years of data give an expected maximum in-sample Sharpe of 1.00 at a TRUE Sharpe of 0. The commonly quoted '~1.5 bar' is not a computed threshold — it collapses to 0.61 at sr_std 0.2 and rises to 1.63 at 0.5, and sr_std is a free parameter until measured. McLean & Pontiff find returns 26% lower out-of-sample and 58% lower post-publication, with larger declines for predictors with higher in-sample returns; their 26% is an UPPER BOUND on data-mining effects for PUBLISHED predictors, which is not a licence to haircut unreplicated in-house work more gently. And a 100-trade record where 5 trades made 70% of the money carries the statistical weight of ~10 observations.

*Citation:* Bailey-Borwein-Lopez de Prado-Zhu, AMS Notices May 2014 (verbatim, grid independently reproduced); McLean & Pontiff JF 71(1):5-32 (CONFIRMED); the proposed 0.74x-for-unpublished multiplier REFUTED on verification.


### P14

**Rank forced-flow mechanisms that publish their own trigger levels above every statistical crowding measure, and score them on the ANCESTOR-CHAIN-REACHABLE (ungated) share, not on total condition count. For the Composer cohort: parse each symphony tree, record every condition's parent chain, dedupe at the SYMPHONY level, quarantine parameter-sweep outliers (median 10 conditions, mean 86), normalize EQUITIES::X//USD tickers, read the window from fn-params then window-days, and publish the ungated share separately from the total with an explicit 'unweighted by dollars, n=2,659' stamp.**

*Why:* This is the only class in the entire evidence base where mechanism, trigger level and timing are all knowable in advance from free data: 2,659 fully enumerable public strategies, 10-day RSI dominant with thresholds piled at 79/80 and 30/31, 94% rebalancing daily or on corridor so cohort flow lands within one session of the trigger. But only 30.3% of RSI(TQQQ,10)>78-82 conditions sit at the top level and only 27.0% of symphonies carry an UNGATED instance, so '~34% of the cohort is 3 points from a synchronized flip' is a hard upper bound. A single 396-condition parameter-sweep symphony fabricates an entire fake threshold ladder if counted at the condition level, and the 52-column search schema contains no AUM, popularity, investor or author field anywhere.

*Citation:* Live Composer probe; corpus independently re-enumerated by the counter-agent (2,669 index slots, ~0.4%/pass offset-pagination drift, so nightly sid diffs carry ~10 phantom adds/drops).


---

## Killed on verification — do not rebuild these


**K1.** BALTAS COMETRIC AND THE DIVERGENT/CONVERGENT ROUTING RULE — UNSUPPORTED. Six of eight quotation-marked strings (the formula, the universe and sample dates, the value result, the size result, both mechanism sentences) are absent from the only fetchable source, which additionally says momentum returns are 'very similar' after crowded and uncrowded periods with -2.25% applying only when crowding is 'very high'. DO NOT BUILD: a Cartographer that tags theses divergent/convergent and inverts the trade on that tag, and above all do NOT extend any 'join the crowd' rule to CARRY — the verified evidence in the same track says crowded carry and value carry sudden-stop and gap risk, which is a short-volatility trade wearing an academic citation.


**K2.** UNSOURCED PRACTITIONER RULES PROPOSED AS HARD GATES — all UNSUPPORTED at their cited sources. Steinhardt's four-field intake schema {idea, consensus view, variant perception, trigger event} and his mirror-image exit rule: the cited page 403s and the accessible alternate explicitly contains neither passage. Paul Tudor Jones's 5:1 risk/reward floor, the implied ~20% hit rate and 'wrong 80% of the time': present in none of the reachable sources. The 1992 '20% of fund to 200%' 10x probe-to-full ratio: the cited article contains none of it and the standard published account is ~2x. DO NOT BUILD: an R:R admission gate whose input is authored by the same agent advocating the trade (it trains the swarm to inflate targets until they clear, corrupting the ledger), and do not let the escalation ladder's top rung 'substantially exceed the initial target' on the strength of a garbled anecdote.


**K3.** THE ROBERTSON 'RIGHT BUT EARLY' CASE — REFUTED on both timing and cause. The Nasdaq Composite peaked Friday 10 March 2000 at 5,048.62; Tiger's closure was announced in late March, roughly three weeks AFTER the thesis began paying off, not 'months before'. Tiger's documented large losses trace to the 1998 Russia/LTCM crisis, the one-day yen move and long positions such as US Airways — the long value book and a carry trade, not a correct-but-early short-tech view. The closing-letter quote could not be reproduced from any reachable source. DO NOT BUILD: a merge-blocking 'Robertson check' that force-sizes candidates to zero, and do not score being-right-early as a full LOSS — that mechanically penalises the exact second-inning entry the same track says to seek.


**K4.** 'DRUCKENMILLER EXPLICITLY REFUSES A STOP-LOSS' — UNSUPPORTED. No primary source exists in which he addresses stop-losses at all; the actual quotes concern ignoring his own COST BASIS, a different proposition, and the same track's own gap list concedes 'no stated drawdown limit, stop-loss, or de-risking threshold anywhere in the primary sources.' Absence of evidence was silently converted into an explicit prohibition. DO NOT BUILD: a levered book (his sanctioned sizes run 25-350% of NAV) with the loss limiter deleted on a fabricated attribution.


**K5.** 'OFFICIAL PRICE DEFENCE IS THE HIGHEST-EV ESCALATION CLASS' — UNSUPPORTED as a ranking. Derived from a single op-ed sentence ('Governments defending prices against fundamentals always lose') that never mentions the pound, 1992, or any trade of his. No hit rate, expected return, average holding period or base rate is sourced anywhere in the track, and the evidence base is one survivor against the SNB EURCHF floor (held 3.5 years, bankrupted shorts), the HKMA peg (40+ years) and BoJ YCC. DO NOT BUILD: an EV ranking that puts this class above everything else, or a sizing rule that gives it the largest allocation. The price-vs-plumbing detector itself is fine as a candidate generator.


**K6.** 'A PASSED TEST IS A FORWARD-OBSERVABLE ESCALATION TRIGGER' — REFUTED by the model's own author, and compounded by a stage misidentification. Soros: 'It is characteristic of my boom-bust model that it cannot predict in advance whether a test will be successful or not... I thought that the emerging market crisis of 1997/8 would constitute the turning point for the super-bubble but I was wrong.' Separately, the proposed signature (price no longer shaken by a setback in the earnings trend) is stage DE, CONVICTION, not CD, the test — one stage before EF, 'Expectations become excessive' — so wiring a collapsed news-beta to 'escalate' adds size nearest the climax. Two further sub-claims fail: NCSKEW cannot estimate the Abreu-Brunnermeier hazard h (a dimensionless realized-skewness statistic against an instantaneous rate with units of 1/time), and 'a failed attack is a BUY signal' is refuted by AB's own price-event model, which prices the round-trip as a guaranteed loss and fixes the terminal burst regardless of how many attacks fail. DO NOT BUILD: a state machine that sizes up on a 'test passed' label.


**K7.** THE FAILURE-MODES TRACK'S TWO HEADLINE MEASUREMENTS — both REFUTED on their own data. Four of nine COT series (GBP, UST10y, UST30y, E-mini S&P) were silently truncated at 2022-02-01 with exactly 817 rows against a real 1,055, almost certainly a Socrata $limit=1000 hit; and the E-mini sample is 5.4 years (Dec 2016-Jan 2022, FRED's SP500 being a rolling 10-year window) presented as 17. On corrected data the split-half 'decay profile of a mined result' largely vanishes (-0.069 -> -0.086 at |z|>=1.5, i.e. slightly STRONGER out of sample) and the pooled fade is t~-1.3 after the researcher's own overlap correction, gross of all costs. The '~40% of the four-week move has already happened before COT is actionable' figure is separately REFUTED: it is the sqrt(4/24)=40.8% random-walk identity, reproduced at 41.0% in a 200,000-path simulation. PUBLISH NEITHER the FADE result nor the FOLLOW mirror; the honest statement is 'no reliable directional signal measured in either direction, 2009-2026.' The staleness case stands on the verified 3-day publication lag alone.


**K8.** THE INVERSE-ETF CROWDING RATIO AS A VOLATILITY-CONTROLLED VETO — control REFUTED. The claimed near-zero marginal volatility effect holding crowding fixed (+0.1/-4.3/-0.8pp) does not replicate; the correct figures are +14.3/+7.6/+4.4pp — and the effect MUST be large, because the same track models inverse-ETF bleed as -k*sigma^2, so a near-zero vol effect contradicts its own findings 1, 3 and 4. The pooled quintiles are compositionally rigged (Q1 is 43% SH, a -1x; Q5 is 71% SCO+SOXS, -2x and -3x), one of eight instruments reverses by -53.6pp on non-overlapping data, and n_independent is 30-39 per fund. DO NOT BUILD: a veto or sizing input on this ratio — it is largely a leverage and volatility proxy wearing a crowding label.


**K9.** 'IN CONTANGO, SHORTING THE FUTURES ETF EARNS THE ROLL, SO THE CONTRARIAN SIDE CAN BE CARRY-POSITIVE' — REFUTED. SCO (-2x USO) has returned -26.27%/yr, -99.6% cumulative since 2008, with 12-month windows negative 71% of the time (median -20.0%). USO's 37.6% annualized volatility gives a -2x fund a k*sigma^2 drag near 42%/yr, dwarfing the -4 to -8%/yr roll yield being harvested. Roll yield accrues to a futures short, never to a holder of a daily-reset inverse ETF. This is the single instruction in the whole evidence base that would actively put on a losing trade, and it lands directly on the uranium and energy nodes.


**K10.** 'BUY OPTIONALITY WHEN ABSOLUTE IMPLIED VOLATILITY IS LOW' — REFUTED by the same pipeline that proposed it. 5% OTM SPX puts returned -89.0% with a 1.9% win rate at VIX<13, against -56.8% with a 10.7% win rate at VIX 19-24; ATM straddles were WORST in the lowest VIX quintile (-29.5%). The related 'volatility risk premium WIDENS when volatility is already high' claim is an artifact of measuring a proportional premium in absolute vol points — IV/RV across the same buckets is 1.43/1.43/1.48/1.41/1.36, flat to shrinking. DO NOT BUILD: a low-absolute-IV cheap-optionality screen; it systematically times long-vol entries into the least profitable state.


**K11.** 'COMPOSER'S oos_* STATS ARE LOOKAHEAD-CONTAMINATED' — REFUTED. The claimed 135-229 trading-day pre-creation windows are a calendar-versus-trading-day unit error: the gaps are each 39-40% of implied trading days, precisely the 7/5 weekend factor, and across 40 stratified symphonies oos_num_backtest_days exceeded calendar days since creation in ZERO cases. Do not write a gate test asserting lookahead (it would fire on healthy data forever) and do not publish the claim about a third party. The DO-NOT-WEIGHT-BY-oos_* rule survives on two other grounds: selection bias, and a real defect found on verification — the OOS clock RESETS on semantic edits, so a user can refresh their track record by tweaking a node.


**K12.** 'PER-CONSTITUENT SHARES-HELD DELTAS IN AN ETF HOLDINGS CSV ARE CREATION/REDEMPTION FLOW' — REFUTED. Differencing Shares Held conflates unit creation with index rebalancing and weight drift, and the file contains no fund-level shares outstanding to separate them (CCO CN moved +0.38% in shares while its weight moved 22.14%->22.31% over one week — indistinguishable causes). DO NOT BUILD the free ETF-flow proxy this way: it would feed rebalance mechanics into the signal as investor demand, and would do so most strongly at quarterly rebalance dates, i.e. correlated with the calendar rather than random. The same CSV IS valid for basket definition and for indirect SPUT exposure.


---

## Contradictions found

These were arbitrated separately; see [`RULINGS.md`](RULINGS.md).


**C1.** DOES CROWDING PREDICT RETURNS OR ONLY THE DISTRIBUTION? crowding-measurement and crowding-predictive-power say the published sign is WITH speculators (Fan et al. 0.47-0.61 Sharpes, Brown-Howard-Lundblad crowding pays, Sias et al. positive even in stress); reflexivity-formal and sizing-escalation say run-ups predict crash probability without predicting the mean; failure-modes' own computation says fading loses. EVIDENCE FAVOURS the distribution reading, with one boundary: crowding/run-up predicts crash probability across the whole range, and predicts significantly negative excess returns ONLY above a ~125% two-year run-up (-13% raw, -28% excess, 10% significance). Below that there is no reliable directional signal in EITHER direction — including the fade result, which does not survive its own data (see 'killed').


**C2.** PRICE MOMENTUM AS AN ESCALATION TRIGGER. sizing-escalation finding 5 says drift is unlearnable from price at a 6-24 month horizon and therefore price must not be the primary escalation trigger; the same track's finding 2 measures +132% log-growth from a Bayesian escalator whose ONLY input is price, at the same 25% vol and 24-month horizon. Druckenmiller's own words agree with finding 2 ('wait for price confirmation... when I get a technical signal, I go'). EVIDENCE FAVOURS permitting price/P&L confirmation as a NECESSARY gate — the prohibition would delete the only mechanism the track actually demonstrated — while accepting the author's own decay warning that technical analysis is 'about 20% as effective today as it was then.' Use price confirmation as a gate, never as the source of edge.


**C3.** DISCRETE EVIDENCE-RUNG ESCALATION VERSUS CONTINUOUS AVERAGING. druck-primary finding 2 specifies discrete doublings on named evidence classes and explicitly not price momentum; finding 4 specifies a 1/3 starter with no adds past inning five; finding 8 forbids escalating while cold. His largest documented position ever (350% ten-year equivalent, Q4 2000) was built by continuous averaging INTO adverse price, with no technical confirmation, while down ~18% on the year — violating all three simultaneously and producing his most-cited quarter. EVIDENCE FAVOURS the conclusion that these are post-hoc rationalizations of a discretionary process, not a consistent policy. Encode only the risk architecture (asymmetric sizing, fast invalidation, drawdown budget); do not hard-code any of the three as merge-blocking gates.


**C4.** JOIN THE CROWD ON 'CONVERGENT' PREMIA. crowding-measurement's declared core routing rule (fade divergent, join convergent) rests on Baltas/CoMetric, which is UNSUPPORTED — six of eight quoted strings absent from the only fetchable source. The same track's own VERIFIED Pojarliev-Levich finding says the opposite for carry: 'crowdedness in carry and value leaves investors in those strategies vulnerable to sudden stops... By comparison, a crowded trend style simply implies low future returns.' EVIDENCE FAVOURS restricting any join-the-crowd rule to equity-value-like anchors (Lou-Polk CoVAL, +1.17%, t=2.39, years 1-2) and explicitly EXCLUDING carry — adding to crowded carry is the configuration that produced August 2007, August 2008 and February 2018.


**C5.** IS THE CROWDED STATE ACTIONABLE AT ALL? Four tracks propose a CROWDED-to-contrarian trigger; Casey's own repo contains two pre-registered, counter-agent-verified studies saying it is not. RISK_BUILD: 'Stats not distinguishable from baseline (p=0.84; halves disagree on direction)... NOT a sell signal - momentum usually continues (78% positive 3m)'. BLOWOFF: 'the decision test failed: mechanically de-risking on this state REDUCED risk-adjusted returns vs holding - historical crash damage lands after BLOWOFF ends.' EVIDENCE FAVOURS THE REPO, decisively: it is pre-registered, on Casey's own instruments, and already through a counter-agent. The one validated return signal in either monitor is WASHED_OUT — a post-flush LONG re-entry (p=0.011, stable across split halves at 94%/95%) — i.e. buy after the crowd is flushed, not fade the crowd while it builds. The same source shows the correct use of the crowded state: sizing discipline (trim to 75%) improved MAR and cut max drawdown even though the directional stats were null.


**C6.** CONFIRMATION ENTRY DOMINATES FIRST-EXTREME ENTRY. unwind-mechanics reports a 30x improvement in return per unit of worst-case bleed. Verification found the MAE comparison is not like-for-like (per-sub-trade minimum against summed returns across 480 round-trips versus 73), zero transaction costs on a 480-round-trip strategy whose ranking REVERSES at 10bp and goes to -29.5% at 20bp, spot proxies presented as futures, carry omitted from 72 of 73 episodes when carry was 82% of the yen loss, and the study's own MEDIAN episode return favouring first-extreme (+1.62% vs +0.45%). EVIDENCE FAVOURS treating the two-module split (crowding = watchlist, momentum = timing) as a dated prior to be scored forward by R2 calibration, exactly as the track's own finding 3 honestly concluded at p=0.27 — not as a proven ranking, and never as the basis for a 6x notional sizing recommendation.


**C7.** OFFICIAL PRICE DEFENCE AS THE HIGHEST-EV SETUP. druck-primary ranks fading official actors defending a price above every other detector class and allocates it the largest size. The evidence base is one survivor (GBP 1992) generalized from a WSJ op-ed sentence that never mentions the pound or any trade; no hit rate, expected return, holding period or base rate exists anywhere in the track. EVIDENCE FAVOURS the counter-cases: the SNB EURCHF floor held 3.5 years and bankrupted shorts on the way, the HKMA peg has held 40+ years, BoJ YCC persisted for years while shorts bled carry. Keep the detector (the price-vs-plumbing test is genuinely implementable from free central-bank communications) as a CANDIDATE GENERATOR; strip the EV ranking and the size allocation entirely.


**C8.** CAN NARRATIVE BASKETS BE MEASURED AT ALL? probe-free-feeds and probe-repo-feeds establish there is no positioning feed of any kind for AI capex, dollar debasement, nuclear or GLP-1 — no COT, no forced-seller print, no mandate rule, and grep across the monorepo returns zero ETF-flow sources. crowding-predictive-power states flatly that zero evidence exists for any crowding signal on hand-constructed thematic baskets. reflexivity-formal proposes co-thesis correlation (comomentum ported to a basket) as the fix. EVIDENCE FAVOURS treating narrative baskets as a PRE-REGISTERED RESEARCH QUESTION with comomentum as the single keyless candidate, validated against an independent positioning anchor before it is trusted — because with 8-15 constituents and no external anchor, a within-basket correlation measure is far more likely to be measuring sector beta than crowding.


---

## Data layer as the recon left it


WHAT THE SWARM CAN SEE (all live-probed 2026-08-28, keyless unless noted).

BACKBONE — CFTC Socrata, 11 verified resource IDs, HTTP 200 with no auth: Legacy futures-only 6dca-aqww (288k rows, 1986-01-15+), Disaggregated futures-only 72hh-3qpy (184k, 2006-06-13+, energy/metals/ags), TFF futures-only gpe5-46if (46k, 2006+, rates/FX/equity index/crypto/credit), Supplemental-CIT 4zgm-a668. Weekly cadence. Lag exactly 3 days data-to-publication, observed live during verification (rowsUpdatedAt = Friday 15:30:08 EDT, max report_date flipping 08-18 to 08-25 at that instant); a mid-day-Friday read sees 10-day-old positioning. Field names are irregular — swap_positions_long_all versus swap__positions_short_all, a typo noncomm_postions_spread_all in legacy — so gate tests must assert exact names. CIT_All (j83k-qyrd) does NOT follow the _All stacking rule (no futonly_or_combined column, 57 cols, identical row count to its parent). Existing repo code (treasury-canary/backend/app/sources/cftc.py) covers TFF only; energy and metals need one new module against 72hh-3qpy with a field-name parameter, cloning the same 6h-TTL / double-checked-lock / stale-preferred pattern.

DAILY PARTNERS for the weekly COT stock: Cboe VIX/VIX9D/VIX3M/VIX6M/SKEW/VVIX (T+1) — but history depths differ sharply and were overstated in the source track: VIX and SKEW reach 1990, VVIX 2006, VIX6M 2008, VIX3M 2009, VIX9D 2011, so the term-structure SLOPE has ~15 years for percentile ranking, not 36. FINRA daily short-sale volume (T+1, pipe-delimited, ~538KB/day; volumes are FRACTIONAL so parse float; a not-yet-published date returns 403 with an S3 AccessDenied body, not 404 or 204, so retry-on-403 loops spin forever). FRED fredgraph.csv with no API key. Wikipedia pageviews (11 years monthly, T+1 daily; a descriptive User-Agent is MANDATORY — 403 without it).

SEMI-MONTHLY: FINRA consolidated short interest via api.finra.org, POST with settlementDate as an EQUAL compareFilter (GTE plus sortFields returns 400). MONTHLY: Cameco uranium spot 1988+ but LONG-TERM only from 1996-03, month-end and running ~1 month behind, so the term-vs-spot spread has ~30 years and no coverage of the 1988-1995 bear market; UMich tbmics.csv 1952+, fresher than FRED's UMCSENT mirror. DAILY BASKET: Global X URA full-holdings CSV, date-addressable back at least a year, valid for basket definition and indirect SPUT exposure (U-U CN line) but NOT for flow.

COMPOSER: 2,659 unique public symphonies, fully enumerable in ~30 minutes (25 search calls/min is the true bottleneck; 250/min on score). Full unredacted logic trees; 22,291 conditions parsed across a 259-symphony sample. 10-day RSI dominates with thresholds piled at 79/80 and 30/31; TQQQ reachable by 53%; 35% of symphony-ticker pairs are leveraged or inverse; 100% US-equities instruments (zero futures, FX or rates); 94% rebalance daily or on corridor so cohort flow lands within one session. is_public is an OWNER TOGGLE, not a curation gate, so the winners-only worry is dropped but author self-selection remains unmeasured. Offset pagination over a mutating index drops ~10 unique symphonies per full pass, so night-over-night sid diffs carry ~10 phantom adds and drops out of 2,659 — the same order as plausible real churn.

DEAD OR TRAPPED: Cboe put/call CSVs frozen at 2019-10-04 (all six files still return HTTP 200 with well-formed CSV — silent staleness, and there is NO free current put/call ratio anywhere). OCC volume-totals silently ignores report_date (byte-identical MD5 across 20260827/20260731/20250827/20200320). Google Trends 429s on a cold first call. GDELT failed 6 of 6 calls on re-verification. AAII, ICI, NAAIM and Conference Board have no free machine-readable series at all (403 or image-only). SEC 13F structured datasets run 2-5 months stale depending on where you sit in the quarterly cycle, and shorts, futures, swaps and FX forwards are definitionally invisible — drop 13F from the macro sleeve entirely.

THREE BLIND SPOTS, RANKED.
(1) NO FREE PRICE SOURCE FOR INDIVIDUAL EQUITIES OR ETFs WAS EVER VERIFIED. FRED carries no single names and its SP500 series is licence-truncated to ~10 years; Cboe carries indices only; the URA CSV's price column is a single snapshot with no history endpoint. CCO, NXE, UEC, OKLO, URA and every genomics name have no verified price source. Without this the system can compute a crowding score and can never score whether it worked — no backtest, no calibration ledger, no honesty-box numbers. This is the hard blocker.
(2) NO DOLLAR WEIGHT ANYWHERE. Composer's schema has no AUM/popularity/investor field; COT gives contracts not capital; 13F is stale and partial. Every crowding number is strategy-count- or contract-weighted and must be stamped 'unweighted by dollars, n=X'.
(3) STRUCTURALLY DARK CROWDING. The 2022 gilt/LDI unwind had zero public positioning warning — the sector had positive cumulative orderflow of ~GBP 4bn through 22 September, and the variable that predicted liquidation existed only in regulator-only MiFID II data. The Feb 2018 short-vol blowup read the 55th-71st percentile in COT the week before because the exposure sat in ETP structures on dealer books (XIV and SVXY were short ~280,000 VIX futures on the 2 February close). Any theme whose exposure lives in LDI/pension leverage, bank structured products, private credit or TRS books must display 'no positioning coverage', never a benign score — a silent zero here is exactly what CLAUDE.md's MISSING KEY INPUTS rule exists to prevent.

PERSISTENCE GAP: the monorepo persists exactly one series (deribit_btc_oi via SeriesObs). Every other series, including the CFTC positioning history that all z-scores are computed against, is re-fetched from the vendor each run — so a vendor revision silently rewrites past z-scores and every backtested threshold drifts underneath you. barbell-lab/src/barbell/edge/db.py already has the append-only plus revision-tripwire pattern and is not wired to any CFTC series. Wire it before anything is calibrated.


> **Superseded:** the recon named "no free price source for single names" its hard
> blocker. It is closed — the keyless Yahoo chart endpoint already wired at
> `treasury-canary/backend/app/sources/yahoo.py` serves single names and continuous
> futures (probed live: URA, CCJ, NXE, UEC, OKLO, TQQQ, ^GSPC, CL=F, GC=F all 200).
> See [`PROBES.md`](PROBES.md) P7 for what replaced it: a three-source keyless quorum,
> and the discovery that `=F` symbols are level-only and `adjclose` is not a storable
> primitive.

---

## Open questions the recon could not settle


**Q1.** Does the KRT slow/fast decomposition survive on TFF data and post-2014? Everything is estimated on 26 COMMODITIES under the legacy commercial/non-commercial split, 1994-2014, while Casey's universe is mostly financial futures reported under Traders in Financial Futures (dealer / asset manager / leveraged money, 2006+). No source establishes the transfer. Related and unresolved: the Marechal (2023) replication claiming the insurance premium fails post-2004 — its three load-bearing quotes could not be verified, so the proposed 'haircut the slow signal hard' instruction is currently unsupported. Settle by in-house replication on free CFTC TFF history before any TFF gate ships.


**Q2.** Does the Composer cohort's trigger map actually move price, and how big is the cohort in dollars? We have an exact, enumerable, level-specific map of 2,659 strategies' pre-committed rotations, but the 52-column search schema contains no AUM, popularity or investor field anywhere, and no event study exists of price behaviour around 10-day RSI(TQQQ) crossing 79-81. Without a size bound this is a precise map of a possibly irrelevant flow. Composer's platform AUM (SoFi filings) would bound it; an event study on the ungated-share crossings would settle the price impact.


**Q3.** Does ANY crowding measure work on hand-built narrative baskets (AI capex, dollar debasement, nuclear, GLP-1)? Zero published evidence exists; comomentum/co-thesis is the only keyless candidate and has never been validated on 8-15-constituent baskets where the fundamental leg is an aggregate and adverse-news response is diluted. Settle by constructing it and checking correlation against an independent positioning anchor (COT, 13F, ETF flows) — if it does not correlate with an external measure it is measuring sector beta, and that correlation check is the natural merge-blocking gate.


**Q4.** What is the realized cross-trial Sharpe dispersion (sr_std) for this swarm's own candidates? Every deflation threshold turns on it — the 'bar' is 0.61 at sr_std 0.2 and 1.63 at 0.5 — and it is currently a picked parameter, not a measurement. barbell-lab's own expected_max_sr docstring says it must come from the trials registry, which does not yet exist.


**Q5.** How many dated, resolvable forecasts does the design actually produce per year? If it is under ~50, no calibration layer can be fitted, the R2 quarterly calibration cannot mature, and conviction sizing has no empirical basis — which would force sizing to stay fully mechanical forever. Count this BEFORE designing the ledger grain, because the answer determines whether per-theme, per-leg or monthly-reaffirmation rows are required. Related: the venture-deal-analyzer ledger currently has 6 rows and 0 resolved outcomes, and the R1/R2 Routines that were supposed to close them were never created — the same write-only failure will hit the trade ledger unless they are created this time.


**Q6.** Does the cross-vendor N_eff mitigation exist at frontier tier? The rho 0.68->0.40 result is measured on DPO-tuned 8B/70B open models; the single frontier datapoint cited is r~0.77, i.e. HIGHER than the 0.70 monoculture baseline, consistent with shared pretraining corpora and RLHF conventions. Measure pairwise error correlation across the actual planned vendor set on ~100 resolved questions before committing to any multi-agent architecture.


**Q7.** What is the borrow and financing cost per instrument? No free keyless source was found and it is a MISSING KEY INPUT for pricing any cash short. But the measured leveraged-ETF intercept shortfall against (1-L)*rf - fee (SH -0.06 through SOXS -4.51 pp/yr, with long-side controls UPRO -0.96 and TQQQ -0.45) IS a direct estimate of the swap financing spread plus short-leg borrow pass-through, and should be used rather than treating this as unresolvable.


**Q8.** Is the mandate/exclusion mechanism — the argument for uranium and nuclear — still live? Hong & Kacperczyk's sin-stock sample ends in 2006, entirely before the ESG mandate wave that supposedly strengthens it and before the 2022-2025 partial unwind that would weaken it; the Baker-Bradley-Wurgler 'it has strengthened in recent years' sentence could not be verified in any accessible version, and predates a decade of low-vol underperformance. Applied consistently, the design's own rule (a mechanism last validated before 2015 is amber and cannot pass the gate alone) fails the ESG-exclusion argument for uranium. Settle with a post-2006 exclusion-premium replication.


---

## Completeness critique

What the fifteen tracks did *not* cover, from a critic that read all of them.


**M1. Nothing measures WHAT IS ALREADY PRICED IN. Fifteen tracks debate how to detect crowded positioning, but no track specifies or probes a source for the consensus forecast or the market-implied path — the denominator of "a thesis no one else has built." other-traders explicitly concluded the admission test should be "how much of this outcome is already in the price / forward curve" and then nobody built or sourced that computation. The Mars-prior agent, the 18-24-month delta, the variant-perception field of the Steinhardt schema, and every EV calculation all require it and all currently have no input.**

*Why it matters:* Without a priced-in baseline the swarm cannot distinguish a variant perception from a restatement, and agentic-finance-evidence's World Cup result says exactly what happens when an LLM is asked to form a view on a priced bet with no independent anchor: four frontier models re-derive the market price 92% of the time and lose money when they deviate. Every EV number the design writes into ledger.csv would be measured against nothing.

*How to close:* Probe and wire four free, dated, keyless consensus sources before any agent design: Philadelphia Fed Survey of Professional Forecasters (quarterly, full historical panel with published forecast errors — the only auditable macro consensus with a track record), CME fed funds futures implied path, TIPS breakevens and forward rates from FRED, and futures forward curves (CME free daily settlements) for FX/energy/metals. Then specify the computation explicitly: thesis_delta = agent's stated 12-24m outcome minus the forward/consensus-implied outcome, in the instrument's own units, stored at intake and scored at resolution.


**M2. The detector druck-primary ranked highest — CATALYST-VS-CARRY DIVERGENCE (a policy event fires and the cost of the trade has not repriced; the "it's still a half percent, unbelievably" observation) — has no identified data source anywhere in the fifteen tracks. inversion-tradability established a hard gate that OTM options cannot be priced without a per-strike IV surface and then found none; probe-free-feeds found Cboe's put/call feed dead since 2019 and OCC's date parameter silently broken. No track probed CME's free daily settlement/volume/open-interest files (which include options-on-futures OI and settlement vols), Cboe delayed chains, Deribit (already implemented in treasury-canary/sources/deribit.py) for crypto, or any FX forward-points source.**

*Why it matters:* The single mechanism that both the Druckenmiller and Soros tracks identify as the actual escalation trigger is unbuildable as specified, and the inversion track's phase-dependent expression rule (probe cheap, escalate into convexity only after confirmation) also depends on strike-level pricing. Ship without it and the escalation trigger silently degrades to price momentum — the exact thing finding 5 of druck-primary says the author declared ~20% as effective and stat-arb flows fight.

*How to close:* Run a keyless probe pass on CME Group's public daily settlement and volume/OI files, Cboe's delayed-quote endpoints, OCC series-level OI, and FX forward points; for each, record availability, history depth, per-strike IV or the inputs to compute it, and release lag. If nothing free carries a usable surface, invoke the MISSING KEY INPUTS rule and ask Casey to buy one or to formally scope options and carry-divergence out of v1 — do not model around it.


**M3. The two highest-ranked trigger classes in the whole design — official price defense / official-actor capitulation (druck-primary F12, soros-reflexivity F8) and the SYNCHRONIZING-EVENT CALENDAR (reflexivity-formal F2, named a first-class agent) — were specified as agents and never given a corpus. No track probed BIS central bankers' speeches, Fed/ECB/BoJ/BoE speech and statement RSS, Treasury buyback and auction announcements, FX intervention disclosures, reserve statistics, or a scheduled-event calendar (FOMC/CPI/NFP/OPEC dates, index rebalances, futures and options expiries, COT release dates).**

*Why it matters:* These are the only detectors in the design that are non-price, dated, machine-checkable, and free — i.e. the only ones that survive both the price-signal-decay critique and the keyless constraint. Leaving them unsourced means the escalation layer falls back on the inputs the tracks measured as worthless.

*How to close:* Probe the BIS central bankers' speeches archive (complete, free, dated, downloadable), each central bank's speech/statement feed, TreasuryDirect auction and buyback announcements, and a deterministic calendar builder for FOMC/BLS/EIA/OPEC/expiry/rebalance dates; verify history depth and publication timestamps, then pre-register the scored event taxonomy (responds-to-a-price vs responds-to-plumbing) with the classification rule frozen before any backtest.


**M4. CASEY'S CAPITAL BASE, ACCOUNT TYPES AND INSTRUMENT ACCESS ARE NEVER STATED, yet every sizing conclusion in the design is a fraction of them. No track establishes account equity, whether he can trade futures at all, options approval level, margin availability, or which of the v1 instruments are reachable. A single ES contract is roughly $380k notional and CL roughly $60k; a 1/3 starter position in nine macro futures may not be expressible at his size even with micro contracts, and the Composer book probed at $276k total.**

*Why it matters:* This is a decision-gating input the house rules say must be asked for, not analysed around. Without it the entire sizing stack — Kelly caps, drawdown-budgeted c_max, the 1/3 starter, the 50-70% concentration finding, the 25-350% NAV leverage figures — is unanchored, and the design may be specifying trades that cannot be placed. It also determines whether the whole exercise is a research logger or a book.

*How to close:* Ask Casey directly for: total risk capital for this strategy, account/broker per sleeve, futures and options permissions, and acceptable peak-to-trough drawdown in dollars. Then compute, per instrument in the v1 universe, minimum viable position = 1 contract notional (standard and micro) and its initial margin as a share of that capital, and drop any instrument where a starter position exceeds the per-thesis risk budget.


**M5. NO EXECUTION PATH AND NO HOUSE-RULE COMPLIANCE AUDIT. The monorepo's separation-of-powers law routes all automated IBKR trading through ibkr-executor with DRY_RUN defaults and staged rollout gates, yet no track specifies how a swarm thesis becomes an order, what the swarm is allowed to emit, or where the DRY_RUN gate sits. Relatedly, no track audited the design end-to-end against the other standing rules: inversion-tradability's entire quantitative basis (every bleed, tracking, and crowding number) came from a keyed vendor (FMP), while probe-free-feeds established there is no free single-name price source — so the production keyless brain cannot reproduce or refresh the numbers the design would be sized on, and neither can a counter-agent.**

*Why it matters:* A keyless-brain violation or an un-gated order path is the one class of error that costs real money on the first live day, and an unreproducible input set means the honesty box's frozen numbers can never be re-verified. This is also the rule Casey wrote as law rather than preference.

*How to close:* Write the interface contract explicitly: swarm emits a signed, dated intent record (instrument, direction, size fraction, reason predicate, invalidation) to a file/queue; ibkr-executor and btc-executor own all credentials and enforce DRY_RUN plus staged rollout; add gate tests asserting the swarm service declares zero `sync: false` secrets in render.yaml (note the catalyst-options-engine block carries an FMP_API_KEY stanza despite its comment) and that no model ID appears in commits. Separately, dual-source every load-bearing price series so a keyless path exists for anything used for sizing.


**M6. NOBODY COUNTED HOW MANY DECISIONS THE SYSTEM PRODUCES PER YEAR, so three independently-derived numbers sit in the design unreconciled: unwind-mechanics measured ~73 crowded episodes over ~9 years across 10 markets (~8/year), sizing-escalation computed that proving a trigger is 60% accurate needs ~194 dated verdicts (~330 if ten variants run concurrently), and druck-primary concluded the method budgets 1-2 full-escalation trades and 3-4 material winners per year. agentic-finance-evidence flagged the count as a gap and no track performed it.**

*Why it matters:* At ~8 episodes/year the calibration ledger reaches 194 verdicts in roughly 24 years, so the escalation gate can never be satisfied, the Platt/isotonic calibration layer cannot be fitted without overfitting a few dozen resolutions, and the R2 quarterly review has nothing to score. This single arithmetic result decides whether the swarm can ever be validated, and therefore whether conviction sizing has any empirical basis at all — it should be computed before any build work, not after.

*How to close:* Run the existing episode extractor across the full intended universe (all COT-covered contracts under each of the three pre-registered crowd definitions, plus the narrative baskets) and count distinct episodes per year, then divide the required verdict counts by it. If the answer is under ~50 resolvable forecasts/year, redesign the ledger grain (per-leg, monthly re-affirmation, or per-instrument rather than per-thesis) or accept explicitly in the honesty box that conviction sizing stays fully mechanical and the LLM layer never touches size.


**M7. NO TRACK OWNS ARBITRATION OF THE CONTRADICTIONS, AND THERE IS NO STOPPING RULE FOR THE PROJECT ITSELF. At least five direct, merge-blocking contradictions sit unresolved across tracks: fade-as-default (failure-modes gate) vs follow-as-default (crowding-measurement's three verified premia) vs no-directional-default; price confirmation forbidden (sizing F5, druck F5) vs price confirmation being the only mechanism either track actually measured working; escalate-on-P&L-confirmation (soros F7) vs the biggest documented trade being built averaging into adverse price; crowding as a return signal vs crowding as a tail/position-limit input; join-crowded-convergent vs the same track's evidence that crowded carry is where sudden stops happen. Separately, no track defines what the swarm must beat (a trend-following benchmark, 60/40, Casey's existing barbell) or under what measured condition the whole project is shut down.**

*Why it matters:* Each gate is individually defensible and several pairs cannot both be implemented; whoever builds first will silently pick a side, and the honesty box will state a rule the code contradicts. And a system with no benchmark and no kill criterion cannot fail — which, per the house IC discipline, means it will run indefinitely on a negative-expectancy prior.

*How to close:* Add an explicit integration pass whose only deliverable is a single frozen gate-test suite with each contradiction resolved in writing and the losing option recorded with the reason. Alongside it, write the project-level kill criteria BEFORE money moves, in the S3 format already in ic-process.md: named benchmark (follow-the-trend on the same instruments and horizon), the calibration threshold the forecast ledger must clear by a dated review, and the drawdown or Brier-vs-null condition that ends the project.


**M8. PROMPT INJECTION AND ADVERSARIAL INPUT ARE NOT ENUMERATED ANYWHERE. The design ingests open text — news, GDELT, narrative corpora, Composer symphony names and descriptions, possibly filings and social text — into LLM agents that produce trade theses, and no track treats that text as untrusted or models an adversary who plants content to steer a thesis, inflate a narrative-adoption metric, or trip an escalation trigger. Composer symphony names are user-authored; narrative-breadth counts are trivially gameable by whoever wants a crowded trade defended.**

*Why it matters:* It is the one failure mode where an outside party, not noise, chooses the loss, and it defeats every statistical control in the design because the input is corrupted before any measurement. It also interacts with the escalation ladder: the cheapest attack is to manufacture the confirming evidence class the ladder is gated on.

*How to close:* Write the threat model as a section of the spec: tag every retrieved text with source, publication timestamp and trust class; render retrieved content to agents as quoted data with an explicit no-instructions contract; forbid any escalation rung gated on a text-derived metric alone (require a numeric, non-text corroborant); and ship a gate test that runs the pipeline over a corpus with planted injection strings and asserts no thesis, size change, or ledger row results.


**M9. POSITIONING DATA LEFT ON THE TABLE, AND NO FEED-CONTINUITY FAILURE MODE. Every track that touched COT used net positions only. The same free reports also publish concentration ratios (net positions of the largest 4 and 8 traders), percent of open interest held by reportables, spreading positions, and the number of traders in each category — direct concentration measures that speak to "how few holders is this" rather than "how big is net," and none is mentioned once. Nor did any track look outside the CFTC: ICE publishes its own weekly COT for Brent, gasoil and UK products, which is where the v1 energy sleeve actually trades. And no track enumerates the historically realized failures of the primary feed: CFTC suspended COT publication for weeks during the 2018-19 government shutdown, and the CFTC has retroactively reclassified traders, which silently rewrites the z-score history every threshold is calibrated on.**

*Why it matters:* The design's core primitive is a single net-position z-score whose trader-category definition was shown to flip the sign of the trade; the concentration fields are an independent, definition-robust crowding measure that could arbitrate that, and they cost nothing. Meanwhile a multi-week outage or a silent reclassification of the primary feed is a realized, dated event that would produce confident wrong readings with no error.

*How to close:* Extend the ingester to store concentration ratios, %-of-OI reportable, spreading and trader counts alongside net positions, and test whether the crowd-definition sign flip survives conditioning on concentration. Probe ICE's public COT for Brent/gasoil/gilts. Add a continuity layer: persist an append-only local copy of every positioning series with revision detection (the pattern already exists in barbell-lab/src/barbell/edge/db.py), and a gate that fails on missing report weeks or on any retroactive change to a previously stored row.


**M10. NO PORTFOLIO-LEVEL NETTING AGAINST CASEY'S EXISTING BOOK. The swarm is specified to score theses one at a time; no track specifies the computation that nets a proposed position against what Casey already owns across uranium, genomics, treasury-canary, BTC, the barbell portfolio and the live $276k Composer book. Dalio's uncorrelated-streams point was noted once in passing and never turned into a computation. The self-collision case is concrete and measured: probe-composer found 19 of the cohort's top-25 tickers in Casey's own can-hold universe, and his symphonies rebalance daily on 10-day RSI triggers at 79/31 — so a swarm fade recommendation can be mechanically traded against by his own strategies within one session, at a trigger level the swarm can compute in advance.**

*Why it matters:* Several crowding signals firing on one macro factor (dollar debasement via gold, BTC and short USD; AI capex via semis, TECL and SOXL) is one bet, not four, and the Kelly and drawdown math in the design is all single-position. Combined with the self-collision case, the system can hand Casey a position his existing automation immediately fights, and neither the risk layer nor the honesty box would show it.

*How to close:* Specify and build a pre-trade netting step: compute the correlation matrix of the proposed thesis's return proxy against every live position across the monorepo and the Composer can-hold universe, net exposures at the factor level before sizing, and reject or shrink any thesis whose factor exposure duplicates an existing one. Add an "are we the crowd" check that runs the same tree extractor over Casey's own symphonies nightly and prints his overlap with the cohort trigger bands beside every contrarian recommendation.
