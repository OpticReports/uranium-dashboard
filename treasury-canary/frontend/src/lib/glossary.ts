// In-depth explanations for every key metric and concept, written for careful
// interpretation — each entry: what it is, how it's calculated, how to read it,
// and (where it matters) the trap to avoid. Rendered by <InfoTip/>.

export interface GlossaryEntry {
  title: string;
  what: string;
  calc?: string;
  read?: string;
  read2?: string;
  caveat?: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  // ── Composite ─────────────────────────────────────────────────────────────
  composite_score: {
    title: "Treasury Stress Score (0–100)",
    what: "A single aggregate read on Treasury-market stress across nine metric families (curve, funding, volatility, cross-asset, labor…). 0 = calm, 100 = severe.",
    calc: "Each live metric maps its status to points (GREEN 0 · YELLOW 50 · RED 90 · CRITICAL 100). Points average within each category, then categories combine using configured weights (curve heaviest). If a category has no data it is dropped and the remaining weights renormalize — missing data never fakes calm or stress.",
    read: "Bands: <25 LOW · 25–50 ELEVATED · 50–75 HIGH · >75 SEVERE. Watch the change and which categories drive it (see contributions) more than the level itself.",
    caveat: "A score built from thresholds is a summary, not a prediction. Always check WHICH family is hot — 26 driven by volatility means something different than 26 driven by funding stress.",
  },
  weight_band: {
    title: "Weighting band — are the weights load-bearing?",
    what: "The composite's category weights (curve 30%, funding 15%, …) are literature-informed judgment calls, not fitted parameters — with only ~8 recessions of history, fitting them would be curve-fitting folklore. This band answers: how much would the score change under DIFFERENT reasonable weightings?",
    calc: "The composite is recomputed under 1,000 random plausible weightings (Dirichlet draws over the weight simplex, seeded so the band is stable between reloads) plus a naive equal-mix. The band shows the 5th–95th percentile of those scores. 'Driver' names the category whose weighting moves the score most (correlation of its weight with the score across draws).",
    read: "A narrow band (e.g. 21–27 around a headline of 24) means the weights barely matter — every reasonable mix tells the same story, so argue with the data, not the weights. A wide band means the reading genuinely depends on how much you trust one family — the driver tells you which one to go inspect.",
    caveat: "Robustness, never selection: nothing is ever picked from these draws — choosing the 'best' weighting against a handful of recessions would be pure data-snooping. The band widens mechanically when categories disagree; that is the point.",
  },
  coverage: {
    title: "Coverage",
    what: "The share of the composite's total category weight that currently has live data.",
    calc: "Sum of weights of categories with at least one non-STALE metric ÷ sum of all category weights.",
    read: "80% coverage means the score rests on 80% of the intended evidence. Low coverage = treat the score with proportionally less confidence.",
  },
  contributions: {
    title: "Component contributions",
    what: "How many points each category adds to the composite — the score's full audit trail.",
    calc: "Category average stress × its renormalized weight. The bars sum exactly to the headline score.",
    read: "This is where you see what's actually driving stress. A big B (volatility) bar with quiet A (curve) = rates-vol episode, not a recession signal.",
  },
  status_lights: {
    title: "Status lights",
    what: "Per-metric traffic light vs. historically grounded thresholds.",
    calc: "GREEN/YELLOW/RED cutoffs live in one config file (overridable without code). CRITICAL is reserved for regime events — currently curve re-steepening after a sustained inversion. STALE = no/late data; excluded from scoring entirely.",
    read: "One RED is information; several REDs in the same family is a pattern; REDs across families is a regime.",
  },
  percentile: {
    title: "Percentile (vs own history)",
    what: "Where today's value sits inside this metric's own full history.",
    calc: "Share of all historical observations at or below the current value (0–100).",
    read: "Context for the raw number: SOFR−EFFR at 8bps sounds small, but a 98th percentile says it's extreme for that series. Extremes in either tail deserve attention.",
  },
  deltas: {
    title: "Δ columns (1d / 20d)",
    what: "Change in the metric's value over the last observation and ~a trading month.",
    read: "Direction and speed matter more than level for most stress metrics — a spread doubling in 20 days is a story even if the level is still 'yellow'.",
  },

  // ── Recession model ───────────────────────────────────────────────────────
  recession_prob: {
    title: "Recession probability (probit model)",
    what: "The estimated probability that a U.S. recession BEGINS within the selected horizon, based on today's 3m10y yield-curve spread.",
    calc: "P = Φ(β₀ + β₁·spread), a probit regression in the Estrella–Mishkin tradition. The coefficients are fit by maximum likelihood on decades of monthly FRED data: 3m10y spread vs. whether an NBER recession started within the following h months. Each horizon (6/12/18/24mo) has its own fitted coefficients.",
    read: "Read it with its confidence band and AUC, never alone. ~15–20% is near the unconditional base rate; the signal is when it pushes above ~30–40% (historically deep inversions).",
    caveat: "It is a model estimate from ONE input (the curve), not a forecast. Post-2000 lead times have been longer and noisier — 2022–24 saw a deep inversion with a long delay.",
  },
  horizon: {
    title: "Horizon (6 / 12 / 18 / 24 months)",
    what: "The window the probability refers to: 'chance a recession starts within the next h months.'",
    calc: "Each horizon is a separately fitted probit — the same spread input, but the outcome variable is 'recession within h months', so coefficients (and reliability) differ by horizon.",
    read: "The curve's predictive power peaks around 12–18 months and fades at short horizons (recessions take time to arrive after inversions). Compare the AUC across horizons to see where the model is actually informative. Longer horizons mechanically show higher probabilities — more time for something to happen.",
  },
  confidence_band: {
    title: "Confidence band",
    what: "A 95% interval around the probability, reflecting statistical uncertainty in the fitted coefficients.",
    calc: "Standard errors come from the probit's information matrix; the interval is built on the linear index β₀+β₁·spread and mapped through Φ, so it stays inside 0–100% and is properly asymmetric.",
    read: "‘16% (11–22%)’ means the data pins the estimate reasonably well. A wide band = don't lean on the point estimate. The band covers coefficient uncertainty only — model misspecification is extra.",
  },
  auc: {
    title: "AUC (discrimination)",
    what: "How well the model has historically separated pre-recession months from calm months. 0.5 = coin flip, 1.0 = perfect ranking.",
    calc: "Mann–Whitney AUC over the model's fitted risk ranking across the full estimation sample (in-sample).",
    read: "0.85+ = strong historical discrimination for that horizon; below ~0.7, treat that horizon's probability as weak evidence.",
    caveat: "In-sample and computed on overlapping monthly windows, so it flatters the model somewhat. Use it to COMPARE horizons, not as a guarantee.",
  },

  // ── Yield curve ───────────────────────────────────────────────────────────
  curve_pair: {
    title: "Curve spread (tenor pair)",
    what: "Long-tenor yield minus short-tenor yield (e.g. 3m10y = 10-year − 3-month), in percentage points. The market's growth/policy expectations compressed into one number.",
    calc: "Daily constant-maturity Treasury yields from FRED, differenced. Negative = inverted.",
    read: "A positive, steep curve is normal (compensation for time). Inversion means the market expects future short rates well below today's — historically because a downturn forces cuts. 3m10y and 2s10s are the pairs with the strongest recession track record.",
  },
  inversion: {
    title: "Inversion",
    what: "The spread going below zero — short rates above long rates.",
    calc: "Tracked per pair as a state machine: NORMAL → INVERTED once the spread < 0, with depth (bps) and consecutive days counted. An inversion is 'sustained' after ~10 trading days (config).",
    read: "Inversion is the WARNING, not the event. Historically the economy keeps growing — and equities often rally — while the curve is inverted.",
  },
  resteepening: {
    title: "Re-steepening (the canary)",
    what: "The spread crossing back ABOVE zero after a sustained inversion — dis-inversion. This is the highest-severity signal on the dashboard.",
    calc: "State machine transition INVERTED → RE_STEEPENING on the day the spread returns ≥ 0 after a sustained episode. Each historical episode is annotated with the lag from dis-inversion to the next NBER recession start.",
    read: "Recessions have historically BEGUN after the curve re-steepens, not while it's inverted — typically because the front end collapses as the Fed cuts into weakness (a 'bull steepener'). The chart's per-episode '+N months' callouts show the actual historical lags — judge from those.",
    caveat: "Association, not causation. A curve can also re-steepen benignly (long rates rising on growth/supply — a 'bear steepener'). Check WHY it dis-inverted: front-end falling = worry; long-end rising = different story.",
  },
  days_inverted: {
    title: "Days inverted",
    what: "Consecutive trading days this pair has been below zero in the current episode.",
    read: "Longer, deeper inversions have historically carried more signal than brief dips, which are treated as noise (not eligible to trigger the re-steepening alert).",
  },

  // ── Volatility ────────────────────────────────────────────────────────────
  "vol.move": {
    title: "MOVE (proxy)",
    what: "Treasury-market volatility — the bond market's 'VIX'. The real MOVE index is licensed (ICE), so this is a clearly-labeled proxy.",
    calc: "PROXY: rolling 20-day annualized standard deviation of daily 10y yield changes, scaled toward MOVE-like units. It tracks the REGIME (calm/stressed), not the exact level.",
    read: "Rule of thumb in MOVE units: <100 calm, 100–140 elevated, >140 stressed. Rate-vol spikes tighten financial conditions on their own — they force deleveraging in bond portfolios.",
    caveat: "Realized vol lags implied vol at turning points. Treat threshold crossings as confirmation, not first warning.",
  },
  "vol.move_vix": {
    title: "MOVE / VIX ratio",
    what: "Rates volatility relative to equity volatility.",
    calc: "MOVE proxy ÷ VIX.",
    read: "A high ratio = stress originating in the RATES market (2022/2023-style) rather than equities. That regime is when Treasuries fail as the hedge and stock-bond correlation flips positive.",
  },
  "vol.vix": {
    title: "VIX",
    what: "30-day implied volatility on the S&P 500 — the equity market's fear gauge.",
    calc: "CBOE-published index via FRED (VIXCLS).",
    read: "<20 calm · 20–30 nervous · >30 stressed. Read it against MOVE: equity vol WITHOUT rate vol is an equity story; both together is systemic.",
  },

  // ── Term premium & real rates ─────────────────────────────────────────────
  "premium.acm_tp10": {
    title: "ACM 10y term premium",
    what: "The extra yield investors demand for holding a 10-year bond instead of rolling short bills — the 'risk compensation' slice of the 10y yield.",
    calc: "Adrian–Crump–Moench model estimate (NY Fed), pulled via FRED. 10y yield = expected path of short rates + this premium.",
    read: "Rising/positive = markets demanding compensation for duration risk (fiscal supply, inflation uncertainty) — long yields can rise WITHOUT growth optimism. Deeply negative premia marked the QE era and historically compressed near cycle tops.",
  },
  "premium.real_10y": {
    title: "Real 10y yield (TIPS)",
    what: "The 10-year yield after expected inflation — the true price of long-term money.",
    calc: "10-year TIPS yield (FRED DFII10).",
    read: "This is the discount rate that matters for valuations and housing. Sustained levels near/above ~2% are restrictive by post-GFC standards; financial conditions tighten with a lag.",
  },
  "premium.breakeven_5y5y": {
    title: "5y5y forward breakeven",
    what: "Market-implied AVERAGE inflation for the five-year window starting five years from now — the cleanest read on whether long-run inflation expectations are anchored.",
    calc: "Derived from nominal vs TIPS curves (FRED T5YIFR).",
    read: "Stable near ~2–2.5% = anchored (Fed credibility intact). The danger is movement in EITHER direction: >3% = de-anchoring inflation fear; <1.5% = deflation/stagnation fear.",
  },

  // ── Funding / plumbing ────────────────────────────────────────────────────
  "funding.sofr_effr": {
    title: "SOFR − EFFR",
    what: "Secured (repo) overnight rate minus unsecured fed funds — the pulse of Treasury-market plumbing.",
    calc: "SOFR minus EFFR, in basis points (both NY Fed rates via FRED).",
    read: "Normally ±a few bps. A sustained positive spike = dealers are charging more for cash against Treasury collateral — balance-sheet scarcity (Sept 2019 repo spasm was the extreme case). Quarter-end blips of a day or two are routine; persistence is what matters.",
  },
  "funding.sofr_iorb": {
    title: "SOFR − IORB",
    what: "The repo rate relative to the floor the Fed pays banks on reserves.",
    calc: "SOFR minus interest on reserve balances, bps.",
    read: "SOFR persistently ABOVE IORB signals reserves are getting scarce (money markets paying up for cash) — an early sign QT is draining too far. That's the indicator that forced the Fed to stop QT in 2019.",
  },

  // ── Cross-asset ───────────────────────────────────────────────────────────
  "crossasset.stock_bond_corr": {
    title: "Stock–bond correlation (60d)",
    what: "Whether Treasuries are hedging equities right now — the foundation of every 60/40-style portfolio.",
    calc: "Rolling 60-day correlation of daily S&P 500 returns vs 10y Treasury PRICE returns (price moves inverse to yield).",
    read: "Negative = diversification intact: on bad equity days, bonds rally. A flip to positive — both falling together, 2022-style — is a regime break: usually means INFLATION/RATES are the threat rather than growth, and there's nowhere to hide.",
  },
  "crossasset.flight_to_quality": {
    title: "Flight-to-quality score (20d)",
    what: "On days stocks fall, is money actually rotating into Treasuries?",
    calc: "Over the last 20 sessions: share of equity down-days on which the 10y yield FELL (bond bid). 1.0 = bonds caught every equity selloff; 0 = none.",
    read: "≥0.6 = the classic risk-off reflex is working. Low readings alongside falling stocks = bonds are part of the problem (rates-driven selloff) — the dangerous configuration.",
  },
  "crossasset.hy_oas": {
    title: "High-yield OAS",
    what: "The extra spread over Treasuries on junk-rated corporate debt — the market's price of default risk.",
    calc: "ICE BofA HY option-adjusted spread, bps (FRED).",
    read: "<350 complacent/tight · 350–550 normal-to-wary · >550 stress. Its main job here is CROSS-CONFIRMATION: Treasury stress + widening HY = conviction; Treasury signal with tight credit = watch for false positive.",
  },
  "crossasset.ig_oas": {
    title: "Investment-grade OAS",
    what: "Spread on high-quality corporate debt.",
    calc: "ICE BofA IG option-adjusted spread, bps (FRED).",
    read: "Moves later and less than HY; IG widening means stress has reached the quality end — a later-cycle, more serious confirmation.",
  },
  "crossasset.margin_excess_yoy": {
    title: "Margin debt excess growth",
    what: "How much faster investors' margin debt is growing than the market itself — leverage building beyond what rising prices alone explain. The one margin-debt cut that actually backtests as a leading indicator.",
    calc: "FINRA margin-debt YoY % minus S&P 500 YoY %, in percentage points. Monthly FINRA data (~3–4 week lag); S&P leg from FRED.",
    read: "Above +25pp: in 1997–2026, 21 of 27 such months saw the S&P LOWER 12 months later (median −12%, worst −37%) — the 2000/2007/2021 pattern. Above +15pp: forward returns compress toward zero. Around 0: leverage merely tracking the market, no signal.",
    caveat: "A 12-MONTH-horizon signal from ~3 independent historical episodes. It has essentially no monthly timing power (only 39% of blowoff months were down 3 months later) — treat it as a regime dial, not a sell trigger. See the Leverage Cycle chart for the full state machine.",
  },
  "crossasset.margin_yoy": {
    title: "Margin debt growth (YoY)",
    what: "Raw year-over-year growth in FINRA margin debt — context for the excess-growth gauge.",
    calc: "Total debit balances in customers' margin accounts, YoY % (FINRA monthly).",
    read: "Peaks in margin debt led the S&P peak in all five major drawdowns since 1997 (by 1–9 months). CONTRACTION (negative YoY) is historically a BUY zone, not a warning: after contraction months, 12-month forward returns ran +9 to +12% with ~79% positive.",
    caveat: "Informational tile — the composite uses excess growth instead, because raw growth double-counts the market's own rise.",
  },
  "crossasset.margin_coverage": {
    title: "Investor cash coverage (credit/debit)",
    what: "Cash in brokerage accounts ÷ margin debt — the normalized version of the viral 'record negative net credit balance' chart.",
    calc: "FINRA free credit balances (cash + margin accounts) divided by margin debit balances.",
    read: "It is deliberately NOT scored. The ratio trends structurally lower (portfolio margin, cash swept outside brokerage free-credit), so it sets 'records' by construction: coverage at the 2000 top was 0.56, at the 2007 top 1.04, today ~0.29. Bottom-decile coverage months actually preceded ABOVE-baseline returns.",
    caveat: "When the scary net-credit-balance chart goes viral, this tile is the antidote: check the excess-growth gauge instead — that's the cut with signal.",
  },
  margin_leverage: {
    title: "Leverage Cycle (margin debt)",
    what: "Tracks where speculative leverage sits in its build → blowoff → crash → squeeze-out cycle, using FINRA margin debt vs the S&P. Its two jobs: warn when leverage builds dangerously fast, and show — in near-real-time after a crash — when the leverage has been SQUEEZED OUT and forced selling is spent.",
    calc: "States, checked in order: WASHOUT margin YoY ≤ −15% · SQUEEZE YoY < 0 · BLOWOFF excess ≥ +25pp (or YoY ≥ +40%) · ELEVATED excess ≥ +15pp (or YoY ≥ +30%) · else NEUTRAL. Historical stats: monthly states 1997–2026 vs forward SPY returns. Long view: margin is FINRA monthly from 1997 spliced onto quarterly Fed Z.1 security credit back to 1946 (they track near-1:1 at the splice); the S&P leg is the ^GSPC index back to ~1951. Price overlays re-index to 100 at the first month of whatever range is selected.",
    read: "BLOWOFF: 78% of months saw the S&P lower a year later (median −12%) — de-risk over quarters. NEUTRAL: best regime (88% higher a year later). WASHOUT: crash in progress — bottoms form here, scale in staged. SQUEEZE: the reset is done, forward returns back to baseline — historically the re-entry zone. The range chips (All/1971+/1997+/10y) just window the same series.",
    caveat: "Slow signal, overlapping windows, ~3 independent blowoff episodes in the sample. The playbook stats are validated on the FINRA era (1997+) only — the pre-1997 stretch is historical context, quarterly and from a different (spliced) source. BTC exists from 2014; no earlier price can be shown. Read jointly with stock-bond correlation: a blowoff unwinding while that correlation is positive (2022-style) has no Treasury shock absorber. USEFULNESS EVAL (2026-07, MARGIN_DEBT.md): NEUTRAL's best-regime claim is bootstrap-validated (p=0.007); BLOWOFF is suggestive only (p=0.058, 8 episodes) and mechanically de-risking on it did NOT improve risk-adjusted returns 1998-2026 (crash damage historically lands after BLOWOFF ends) — each state's banner now carries its evidence verdict.",
  },
  rate_shock_sim: {
    title: "Rate-Shock Simulator — scenario fan charts",
    what: "Forward-looking WHAT-IF panel: pick a Fed scenario (-2 cuts to +4 hikes at the next FOMC meetings) and see the simulated price distribution for SPX, QQQ, SOXX (the AI-capex proxy) and HYG out to Q2 2027. This is NOT a naive Monte Carlo cone: scenarios are measured as SURPRISE vs the market-implied path (a fully priced hike moves nothing), surprises pass through an estimated front-to-long kappa into 10y and real yields, then through duration betas and a regime-switching credit-stress state into asset drifts — the Monte Carlo only adds residual noise (Student-t, t-copula for realistic joint crashes).",
    calc: "Stage 1: surprise = scenario path - implied path (Oct-2026 ~70%, Dec ~45% priced; editable params). kappa_t = clip(0.45 + 0.40*(6m ACM term-premium change), 0.25, 0.65). Stage 2: equity dlog = drift/12 - beta*d(real yield); betas SPX 8, QQQ 11, SOXX 14 per 100bp (2020-26 estimates); HYG = -3.2*dy - 3.5*dOAS + carry, with a 2-state OAS Markov (normal theta 310bp; stress theta 500bp, +120bp entry jump; entry probability = logistic in lagged cumulative surprise + the live canary composite). Stress triggers a phased capex-crack (-12/-18/-25%) and 1.6x vol for 4 months. Stage 3: 10,000 antithetic paths, monthly to Jun-2027, t(4) shocks via shared-mixing t-copula, vols from live VIX (x0.8) and MOVE/realized blend.",
    read: "Compare scenarios, not levels: the difference between the '+4 hikes' and 'priced path' fans IS the model's estimate of what unpriced tightening costs. The stress sparkline shows when the credit regime is likely to break — calibrated so 0-1 hikes gives ~5-10% stress odds by Q2-27 and 3-4 hikes ~30-50%. P(dd>10/20%) chips quantify drawdown risk per scenario. The param drawer (amber dot = judgment-tagged) re-runs the engine live — it is the sensitivity surface, use it.",
    caveat: "Validation gates passed: 2022 replay lands SPX -20%/HYG -14% (in-band), telegraphed-hike replay does NOT crash, zero-surprise reproduces a plain cone. But: conditional betas rest on ~5 hiking cycles, regime probabilities are judgment encoded as parameters, and the market-implied path is manual config. Scenario visualization, not prediction. Full parameter provenance: /shock-sim/calibration; counter-agent amendments in SPEC_AMENDMENTS.md.",
  },
  rate_shock: {
    title: "Rate Shock — long-yield moves × hedge regime",
    what: "Answers 'the 20y/30y just moved — does that mean recession, and should I sell stocks?' The folk model says rising yields make investors sell stocks to buy bonds. Historically that's only half true, and WHICH half depends on the stock-bond correlation regime: when correlation is positive (2022-style), bonds aren't hedging stocks and yield moves transmit straight into equity valuations; when negative, yield swings largely reflect growth news and rotations.",
    calc: "Long yield = 30y Treasury (DGS30, spliced with DGS20 over the 2002-06 discontinuation). Shock = change over 60 trading days: SPIKE ≥ +75bp · PLUNGE ≤ −75bp · else NEUTRAL. Regime = rolling 60d correlation of daily S&P returns vs bond-price returns (same convention as the stock-bond correlation tile): POS ≥ +0.2 · NEG ≤ −0.2 · else MIXED. Backtest: pre-registered thresholds, 2,480 weekly obs 1977-2026, forward S&P at 1/3/12 months plus recession-within-12-months odds, episode-level bootstrap with FDR across the 9 cells.",
    read: "The two validated findings: (1) SPIKES are a RECESSION signal, not a stock signal — recession began within 12 months after 44% of spike weeks vs 21% baseline (47% in the no-hedge regime), yet 12-month stock returns after spikes ran near baseline with MILDER worst cases (−17% vs −46%), because crashes historically started from calm-rate weeks. Mechanically selling stocks on a yield spike was not supported. (2) PLUNGES are the validated equity BUY: yield relief in the no-hedge regime saw the S&P higher 12 months later in 102 of 102 weeks (13 episodes, p<0.001), and 97% in the hedge-intact regime (p=0.029). Caveat cell: a plunge in a MIXED regime carried 60% recession odds — sometimes the plunge IS the recession arriving; read it with the curve canary.",
    caveat: "Weekly observations overlap; episode counts are the honest n. SPIKE × NEG's spectacular numbers rest on 2 Volcker-era episodes — ignore them. The recession-odds column is descriptive conditioning, not the recession MODEL (that's the curve-based one, which remains the validated predictor). Frozen from one pre-registered evaluation; thresholds chosen by judgment, not swept.",
  },
  fast_leverage: {
    title: "Fast Leverage — Nowcast strip",
    what: "The monthly Leverage Cycle chart below answers 'where are we in the leverage CYCLE?' but publishes with a ~3-4 week lag. This strip answers 'is leverage being forced out RIGHT NOW?' using the three fastest leverage gauges that exist: hedge-fund S&P futures positioning (CFTC, weekly with a 3-day lag), the VIX 20-day change (daily), and BTC perpetual funding + open interest (hourly). HY credit spreads ride along as a daily confirmation leg. In a fast washout the sequence runs: crypto funding flips (hours) → futures positioning unwinds (weeks) → HY spreads widen (days) → the monthly FINRA line confirms 1-2 months later.",
    calc: "COT leg: leveraged funds' net E-mini S&P position as % of open interest, z-scored against the trailing 3 years (funds are STRUCTURALLY net short e-minis via the basis trade, so only the z-score means anything). Composite state, rules pre-registered before the backtest was run: FLUSH = VIX up ≥8pts in 20 days AND positioning z falling ≥0.5 in 4 weeks · WASHED_OUT = z ≤ −1 AND VIX 20d change ≤ 0 · RISK_BUILD = z ≥ +1 AND VIX 20d change ≤ +4 · else CALM. Evaluated ONCE on 2006-2026 weekly data (single variant, no tuning loop); the stats shown are frozen from that run.",
    read: "FLUSH is rare (3 episodes: Sep-2015, Mar-2022, Apr-2025) and LATE — all 5 historical weeks resolved higher a month later (median +7.4%): don't panic-sell a climax. WASHED_OUT is the fast re-entry zone: 95% of weeks saw the S&P higher 12 months later (median +15.6%). RISK_BUILD isn't a sell signal (78% positive 3m) but owns the worst left tail (−40% worst 12m): don't ADD leverage there. CALM = baseline. The × line at the bottom of the banner crosses the fast state with the monthly state — the dangerous combo is monthly BLOWOFF × fast RISK_BUILD; the constructive one is fast WASHED_OUT front-running the monthly SQUEEZE.",
    read2: "THE 75-YEAR LINE: positioning data can't exist before 2006 (COT leveraged-funds category) or 1982 (equity futures), but the STRESS leg extends to 1951 via realized 20-day vol of daily S&P closes. Four stress states (pre-registered mirroring the modern thresholds, evaluated once): SHOCK = vol up ≥8pts/20d · AFTERSHOCK = vol z ≥ +1 and fading · COMPLACENT = vol z ≤ −0.75 and quiet · NORMAL. Crossed with the monthly leverage state over 3,803 weekly obs, the matrix's headline cells: COMPLACENT × BLOWOFF (quiet vol on a blown-off cycle — the fragile combo): 49% of weeks higher 12m later, median −0.2% vs baseline 74%/+10.3%, across 30 episodes. COMPLACENT × WASHOUT (the bear-market lull): 11% higher, median −19.6% — calm during a washout historically meant the crash wasn't over. AFTERSHOCK × SQUEEZE (the re-entry cell): 89% higher, median +22.7%. SHOCK × BLOWOFF (climax weeks): 3 months later positive in all 18 weeks. The banner's 75y line shows today's live cell.",
    caveat: "Weekly observations overlap heavily — episode counts (3/22/16/23) are the honest sample sizes, and FLUSH's stats rest on 3 episodes. Tradeability gap: COT stats are computed from Tuesday DATA dates, but the report publishes Friday — each state's forward return includes ~3 days you couldn't have traded on it, so the stats modestly overstate the actionable edge (matters most for FLUSH's 1-month bounce). The banner shows both dates. USEFULNESS EVAL (2026-07): WASHED_OUT is the one fully-validated claim (bootstrap p=0.011, stable across halves); FLUSH is unprovable at 3 episodes; RISK_BUILD's stats are baseline-indistinguishable but its 75%-sizing rule improved MAR 0.156→0.164 and cut max drawdown 3.2pp; in the 75y matrix only COMPLACENT × WASHOUT survives FDR, COMPLACENT × BLOWOFF is suggestive-and-stable, and SHOCK × BLOWOFF plus today's NORMAL × BLOWOFF cell failed split-half replication — evidence verdicts render inline. These are mean-reversion signals at weeks-to-months horizons, NOT cycle calls: 2008 started from CALM. The 75y stress proxy agrees with the modern COT+VIX composite only ~53% of overlap weeks — it reads the stress half, not the positioning half; treat the two lines as complementary evidence, not the same gauge. BTC funding/OI and HY spreads are display legs with no backtested stats(FRED now caps ICE BofA spread history at ~3y — too short to backtest honestly). The combined chart plots every leg on one σ scale — each series z-scored against its own served history (positioning vs trailing 3y = the signal z; VIX/HY vs ~3y; funding vs ~6m) — because the native units (z, points, %/yr, bp) can't share an axis. Hover for native values. Deribit open-interest snapshots accrue daily from first deploy.",
  },
  leverage_corroboration: {
    title: "True bear vs false positive (corroboration flags)",
    what: "The blowoff signal's biggest weakness is false positives: across 1951–2026, only about half of margin blowoffs preceded a major bear — the rest fizzled (1955, 1983, 1997, 2013…). This panel checks WHICH KIND of blowoff today looks like, using six late-cycle conditions that separated the real bears from the fizzles in the historical record.",
    calc: "Six flags, each computed live from current data: flat yield curve (10y−3mo < 1.0pp) · Fed tightened (3mo rate up >0.5pp in 12 months) · late expansion (≥48 months since the last recession) · low unemployment (<5%) · extended market (S&P up >50% over 3 years) · high excess (margin excess ≥ +25pp). Flags with missing data are excluded from the denominator, not counted false.",
    read: "The historical split: every blowoff with ≥4 flags lit (1967, 1998, 2000, 2007) was followed by a major bear — 4 of 4, est. 65–85% forward odds given the tiny sample. Blowoffs with ≤2 flags — the early-cycle re-leveraging kind, coming off a fresh recession with a steep curve — fizzled two-thirds of the time (4 of 12 became bears, ~33%). Unconditional base rate: 8 of 16 (~50%).",
    caveat: "Only ~16 blowoff episodes in 75 years, so these are small-sample estimates, not calibrated probabilities — treat the flag count as a lean, not a forecast. The flags are descriptive of past cycles; a genuinely new regime (fiscal-dominance inflation, AI capex boom) can break the pattern in either direction.",
  },

  // ── Auctions (E) / Liquidity (G) / Foreign (F) ────────────────────────────
  "auctions.bid_to_cover": {
    title: "Bid-to-cover (coupon auctions)",
    what: "Total bids ÷ amount sold, averaged over the last 8 Note/Bond auctions — the headline gauge of demand for Treasury duration at auction.",
    calc: "Live from Treasury FiscalData auction results (no key). Trailing-8 average; the Δ column compares against the prior 8 auctions; percentile vs all rolling windows in recent history.",
    read: "2.5+ = comfortable demand. Below 2.4 = softening; below 2.2 = historically weak. The dangerous pattern is a fading TREND while deficits grow — structural demand eroding into rising supply (the slow-burn version of the fiscal pin).",
  },
  "auctions.dealer_takedown": {
    title: "Primary-dealer takedown",
    what: "The share of competitive auction supply absorbed by primary dealers — the buyers of LAST resort, obligated to bid.",
    calc: "Dealer accepted ÷ competitive accepted, averaged over the last 8 coupon auctions.",
    read: "The single best 'weak auction' tell: when real investors step back, dealers are forced to warehouse the supply. ~10% = healthy; >15% = investors hesitating; >20% = genuinely weak demand. Rising takedown + rising term premium = the market charging for fiscal risk.",
  },
  "auctions.indirect_share": {
    title: "Indirect (foreign proxy) share",
    what: "Indirect bidders — mostly foreign central banks and institutions bidding through dealers — as a share of competitive accepted.",
    calc: "Indirect accepted ÷ competitive accepted, trailing-8 average.",
    read: "The auction-level read on foreign appetite: 60–75% is normal for recent years. A sustained slide below ~60% (worse, 50%) = foreign buyers backing away — cross-check the custody holdings metric (category F) to confirm actual selling vs mere hesitancy.",
  },
  "liquidity.ofr_fsi": {
    title: "OFR Financial Stress Index",
    what: "The Office of Financial Research's daily, 33-variable stress index across credit, equity valuation, safe assets, funding, and volatility. Zero = average conditions.",
    calc: "Published daily by OFR (no key); pulled from their CSV feed.",
    read: "Its value here is INDEPENDENCE: it's built from different inputs than our composite. Both hot = broad-based stress (believe it). Our composite hot while FSI calm = stress localized to rates. Negative values = looser/calmer than average.",
  },
  "foreign.custody_26w": {
    title: "Foreign custody holdings (26-week change)",
    what: "Marketable Treasuries the New York Fed holds in custody for foreign central banks — the cleanest weekly read on whether foreign officials are net sellers.",
    calc: "26-week % change of the weekly custody level (FRED WMTSECL1).",
    read: "Sustained declines = official-sector selling: structural pressure on Treasury demand rather than a cyclical recession canary (hence its deliberately small composite weight). −2% = notable; −5% over six months = significant. Confirms or vetoes the auction indirect-share trend, and pairs with the flow compass's debasement regime.",
    caveat: "Foreigners can also move holdings to other custodians without selling — read the trend, not single weeks.",
  },

  // ── Severity tab ──────────────────────────────────────────────────────────
  severity_index: {
    title: "Recession Severity Index (the gun-size gauge)",
    what: "Answers a different question than the probability model: IF a recession arrives, how bad does the balance-sheet configuration say it would be — and where does the damage concentrate? Timing comes from the curve; triggers from the pin board; this measures the powder in the keg.",
    calc: "Six blocks, every component scored as a percentile of its own full history (higher = more severe conditions). Composite = 0.35·LeverageExcess + 0.25·WealthAtRisk + 0.20·Amplification + 0.20·BoomConcentration, adjusted +0.15·(PolicySpace−50) and −0.15·(Dampeners−50). Weights are literature-informed and fixed — with ~5 well-documented severe recessions, fitting weights would be fiction.",
    read: "Classes: <35 MILD (2001-like) · 35–60 MODERATE (1990-like) · >60 SEVERE (2008-like). Read the COMPOSITION alongside the score — it decides which markets bleed (see the Impact Map).",
    caveat: "A structured prior, not a prediction. Exogenous shocks (2020) bypass balance sheets and this index by design. Severity is partly endogenous to the policy response.",
  },
  sev_block_a: {
    title: "Block A — Private leverage excess",
    what: "The heaviest-weighted block, per the strongest result in empirical macro: recessions preceded by private credit booms are deeper and slower to heal.",
    calc: "3-year CHANGES in household/corporate/total-private debt-to-GDP (Mian-Sufi-Verner: the buildup rate predicts the bust), plus the debt-service ratio, saving rate (inverted — buffers), margin debt, and bottom-50% net worth (inverted — the marginal consumer's cushion).",
    read: "2007 would have scored this block near 100. A LOW read here is the single best argument the next recession is not a 2008 repeat.",
  },
  sev_block_b: {
    title: "Block B — Wealth at risk",
    what: "How much paper wealth is exposed to a de-rating: equity market cap/GDP (Buffett indicator) and house price/income.",
    read: "Wealth destruction scales with the starting valuation — but WHERE it lands depends on leverage (Block A): an unlevered equity bubble (2001) produced a mild recession with a huge drawdown; a levered housing bubble (2008) produced a depression-class event.",
  },
  sev_block_c: {
    title: "Block C — Amplification",
    what: "Whether a downturn becomes a credit crunch: delinquencies already forming (cards, CRE) and spread complacency (tight HY = maximal repricing room).",
    read: "Banking-crisis recessions are historically 2–3× deeper — this block watches the transmission machinery. Pairs with the live SLOOS/discount-window/basis-trade channels on the Monitor tab.",
  },
  sev_block_d: {
    title: "Block D — Policy space (the divisor)",
    what: "Government debt doesn't cause the recession — it caps the rescue. Fiscal room (debt/GDP, deficit), monetary room (distance to zero), and the inflation constraint (above-target inflation handcuffs cutting).",
    read: "High score = thin space = whatever hits, hits harder. This is where today's configuration is historically unusual — and it is Dalio's core concern quantified.",
  },
  sev_block_e: {
    title: "Block E — Structural dampeners",
    what: "The severity-REDUCERS, so the index can honestly find mildness: lean inventories, housing under-supply (low months' supply and vacancies — the anti-2006), and mortgage rate lock-in (outstanding stock financed below market → rate shocks transmit slowly).",
    read: "High dampener score subtracts from severity. These are the main reasons 2022–24's tightening didn't break households.",
  },
  sev_block_f: {
    title: "Block F — Boom concentration",
    what: "When one sector's capex IS the expansion, its stop IS the recession (telecom 2001; AI/data-centers now). Info-processing + software investment share of GDP, level and 3-year surge.",
    read: "High concentration doesn't predict the stop — it predicts the recession's SHAPE if the boom stops: capex-led, valuation-heavy, housing-light. 2001 is the template.",
  },
  impact_map: {
    title: "Impact Map — what each recession TYPE does to markets",
    what: "Severity doesn't hit markets uniformly; COMPOSITION decides which market bleeds. Computed from every NBER recession (equities 1957+, housing 1975+): peak-to-trough drawdowns, months-to-trough, months-to-recover, by recession type.",
    calc: "Types are hand-classified from each episode's balance-sheet configuration (documented in the generated data): household/credit-leverage busts (1990, 2008), valuation/corporate unwind (2001), inflation/rates-driven (six episodes 1957–81), exogenous (2020).",
    read: "The headline contrasts: 2001 — mildest recession, −33% equities, housing FLAT. Household busts — housing −9% nominal/−15% real with troughs YEARS later, duration returns +24%/12m. Inflation types — housing survives nominally but loses ~13% REAL. Equity drawdowns track pre-recession valuation; housing drawdowns track household leverage.",
    caveat: "1–6 episodes per type; every episode shown. Price-only equities; approximated bond returns. Medians are priors, not laws.",
  },
  todays_translation: {
    title: "Today's translation",
    what: "The live bridge: reads the current Severity composition and highlights the matching Impact-Map row — i.e., IF the gun fires with today's configuration, this is the historical damage pattern to study.",
    caveat: "If the matched type is fiscal-constrained, note that it has thin U.S. precedent — the nearest analogs are the 1970s (equity de-rating via multiple compression, housing holds nominally but falls in real terms, duration fails as the hedge). Analog-based, not sample-based.",
  },

  // ── Recession model extras & labor ────────────────────────────────────────
  "recession.nfci": {
    title: "Chicago Fed NFCI",
    what: "A weekly composite of 100+ indicators of overall U.S. financial conditions — an independent cross-check on this dashboard's score.",
    calc: "Published by the Chicago Fed; 0 = historical average, positive = tighter than average.",
    read: "If our composite says stress but NFCI is loose (negative), the stress is likely localized to rates; both tight = broad-based tightening with real-economy bite.",
  },
  "labor.sahm": {
    title: "Sahm Rule",
    what: "The best real-time recession-ONSET detector: a small sustained rise in unemployment has, historically, only happened once a recession was already underway.",
    calc: "3-month average unemployment rate minus its LOW over the prior 12 months (percentage points). Triggers at ≥ 0.50. FRED's official real-time series when available.",
    read: "This is the confirmation leg of the framework: the yield curve leads by ~a year; Sahm tells you the downturn has actually arrived. 0.3–0.5 = deterioration worth watching; ≥0.5 has marked the start of every recession since the 1970s with essentially no false positives in-sample.",
    caveat: "It confirms, it does not predict — by trigger time, the recession has typically already begun. Labor-supply surges (immigration, participation) can nudge it up without collapsing demand; check claims for agreement.",
  },
  "labor.claims_yoy": {
    title: "Initial jobless claims (YoY, 4-wk MA)",
    what: "New unemployment filings — the fastest official labor signal, published weekly.",
    calc: "Year-over-year % change of the 4-week moving average (FRED IC4WSA). YoY removes seasonality; the MA removes week noise.",
    read: "Claims LEAD the unemployment rate: layoffs show up here first. Sustained +10–25% YoY = cracks forming; >25% = the labor cycle is turning. One of the earliest honest recession tells.",
  },
  // ── Flow compass ──────────────────────────────────────────────────────────
  flow_compass: {
    title: "Flow compass — where is the money going?",
    what: "When stocks and bonds sell off together, the DESTINATION of the haven bid identifies the regime. This panel measures ~20-day drifts in the candidate destinations and classifies the pattern.",
    calc: "Rule-based on 20-trading-day moves: stocks (S&P), 10y yield, broad dollar, gold, oil, BTC. Stocks down + bonds up = growth scare (hedge intact). Stocks & bonds down + dollar UP + no gold bid = rates/inflation shock → money hides in front-end cash. Stocks & bonds down + dollar DOWN + gold UP = debasement / sell-USD-assets → the haven bid is leaving the country. Everything down incl. gold + dollar spike = liquidity crunch (dash for cash).",
    read: "The debasement configuration is the most dangerous for Treasuries — it means the marginal safe-haven buyer is choosing gold/foreign assets over USTs (fiscal/credibility premium). The rules and thresholds are shown transparently; this is a drift classifier, not a prediction.",
    caveat: "20-day windows classify the prevailing regime, not turning points. Mixed readings are reported as mixed rather than forced into a bucket.",
  },
  flow_usd: {
    title: "Broad dollar index",
    what: "Trade-weighted USD vs major partners — the world's default haven currency.",
    read: "Dollar UP in a selloff = classic risk-off (foreigners buying US safety). Dollar DOWN while US stocks AND bonds fall = the 'sell America' tell — capital leaving USD assets altogether.",
  },
  flow_gold: {
    title: "Gold",
    what: "The anti-currency haven — the asset money chooses when it distrusts BOTH risk assets and paper claims.",
    read: "Gold bid while bonds sell = inflation/fiscal fear (bonds aren't trusted as the hedge). Gold SOLD in a crash = forced liquidation — even havens get sold for cash (Mar 2020).",
    caveat: "Pulled via FMP (GLD proxy) — requires the FMP key on the canary service; shows n/a without it.",
  },
  flow_btc: {
    title: "Bitcoin",
    what: "A hybrid: trades like levered risk most of the time, but corroborates gold in debasement episodes.",
    read: "Only meaningful in COMBINATION: BTC up + gold up + dollar down while bonds fall = confirms the debasement read. BTC down hard = it's behaving as risk, not haven.",
  },
  flow_bills: {
    title: "3-month T-bill",
    what: "The front end — the closest thing to cash that still yields.",
    read: "Bill yields FALLING while stocks fall = money crowding into cash-like safety even when it won't touch duration. The signature of a rates-shock regime.",
  },
  flow_oil: {
    title: "WTI crude",
    what: "The inflation impulse.",
    read: "Oil UP during an equity selloff = supply/inflation shock (stagflationary — bad for both stocks and bonds). Oil down = demand fear (recessionary — usually good for bonds).",
  },

  // ── Leading stack ─────────────────────────────────────────────────────────
  leading_stack: {
    title: "Leading stack (additive by design)",
    what: "Independent, individually-validated recession indicators — each with its own causal story and track record. You choose which to include; the readout is transparent breadth: 'X of N included are flashing.'",
    calc: "Deliberately NO joint model: with only ~8 recessions of usable history, fitting combined weights is guaranteed overfitting. Each indicator is scored against its OWN historically-grounded threshold. Nothing here enters the composite stress score or the probit.",
    read: "One indicator flashing is noise; a majority flashing across INDEPENDENT causal channels (housing, credit, labor, capex) is how real recessions announce themselves. Toggle indicators off if you distrust their current regime-validity — the breadth math updates honestly.",
  },
  "leading.permits_yoy": {
    title: "Building permits (YoY)",
    what: "New housing permits — the most interest-rate-sensitive, forward-committed sector in the economy.",
    calc: "Year-over-year % change of monthly permits (FRED PERMIT).",
    read: "'Housing IS the business cycle' (Leamer): rates → permits → construction jobs → durables → consumption. The strongest single leading indicator in Moody's backtests, leading by ~6–12 months. Below −10% = warning, below −20% = historically recessionary.",
    caveat: "False-positive mode: supply-constrained slowdowns (labor/materials shortages) can depress permits without a demand recession.",
  },
  "leading.sloos": {
    title: "SLOOS — banks tightening C&I standards",
    what: "The Fed's Senior Loan Officer survey: net % of banks tightening business-loan standards. Credit supply is genuinely causal — tightening chokes investment 2–3 quarters later.",
    calc: "Net percentage tightening minus easing, quarterly (FRED DRTSCILM).",
    read: "Net tightening above ~20% has accompanied every modern recession. Quarterly cadence means it's slow — but few series are more causally direct.",
  },
  "leading.temp_help_yoy": {
    title: "Temp-help employment (YoY)",
    what: "Firms cut temporary staff before permanent staff — the first crack in labor demand.",
    calc: "Year-over-year % change (FRED TEMPHELPS).",
    read: "Sustained declines have preceded prior recessions by ~6–12 months.",
    caveat: "LIVE false-positive: temp-help fell through 2023–25 with NO recession (structural post-COVID shrink of the temp industry). Weight this one lightly unless claims confirm.",
  },
  "leading.trucks_off_peak": {
    title: "Heavy truck sales (% off 12-month peak)",
    what: "Class-8 truck purchases — a pure read on freight demand and business capex confidence.",
    calc: "% below the trailing 12-month peak of the sales rate (FRED HTRUCKSSAAR).",
    read: "Turned down before all 7 recessions since 1973, ~13-month average lead. −10% off peak = warning; −20% = historically serious.",
    caveat: "Known false-positive mode: mid-cycle fleet-replacement pauses (e.g. 2015–16) that preceded no recession.",
  },
  "leading.core_capex_yoy": {
    title: "Core capex orders (YoY)",
    what: "Nondefense capital-goods orders excluding aircraft — business investment intentions in close to real time.",
    calc: "Year-over-year % change (FRED NEWORDER).",
    read: "Sustained negative YoY = firms pulling back spending before they pull back hiring. Confirms (or vetoes) what trucks and permits are saying.",
  },
  "leading.cfnai_ma3": {
    title: "CFNAI (3-month average)",
    what: "The Chicago Fed's weighted factor of 85 real-activity indicators — the broadest single read on whether growth is above or below trend.",
    calc: "3-month moving average of the monthly index (FRED CFNAI). Zero = trend growth.",
    read: "Official rule: MA3 below −0.70 following an expansion means a recession has LIKELY ALREADY BEGUN. This is coincident confirmation, not prediction — it pairs with the curve/probit the way Sahm does.",
  },
  "leading.gdpnow": {
    title: "Atlanta Fed GDPNow",
    what: "A model nowcast of the CURRENT quarter's real GDP growth, updated as source data lands.",
    calc: "Atlanta Fed's published nowcast (FRED GDPNOW), % SAAR.",
    read: "Where the economy already is, not where it's going. Noisy in the first weeks of each quarter; converges toward the official print as data accumulates.",
  },
  "leading.cp_prob": {
    title: "Chauvet–Piger recession probability",
    what: "A dynamic-factor Markov-switching model over the four coincident series NBER itself watches (payrolls, industrial production, real income, real sales) — the econometric gold standard for 'are we in a recession right now?'",
    calc: "Published monthly (FRED RECPROUSM156N), ~2-month data lag.",
    read: "Readings above 80% for three consecutive months have marked every recession start with essentially no false alarms. Complements our curve probit: the curve predicts, Chauvet–Piger confirms.",
    caveat: "The publication lag means it tells you 'yes it started ~2 months ago' — use for confirmation, never timing.",
  },
  "leading.wei": {
    title: "Weekly Economic Index (WEI)",
    what: "Ten weekly activity series — retail sales, unemployment claims, staffing-index, steel production, fuel sales, electricity output, rail traffic — distilled into a single factor by Lewis, Mertens & Stock (NY Fed, now maintained by the Dallas Fed).",
    calc: "The factor is SCALED so the number reads directly as the 4-quarter real GDP growth rate the weekly data implies. Published every week with roughly a 2-week lag (FRED: WEI, since 2008).",
    read: "The fastest broad read on the economy between monthly prints. Around 2%+ = normal expansion. Below ~1% = stall speed (yellow). Below 0 = the weekly data says contraction is already underway (red). If the monthly leading stack flashes and WEI then breaks lower, the slowdown is confirmed at weekly cadence instead of waiting a month.",
    caveat: "A nowcast of where activity IS, not a forecast — it turns with the recession, not ahead of it. Weekly data is noisy: read the trend over ~4 weeks, not single prints. History starts 2008, so its thresholds rest on two recessions (one a pandemic).",
  },

  // ── Pin board ─────────────────────────────────────────────────────────────
  accident_gauge: {
    title: "Accident composite — fast spark on a flat curve",
    what: "A two-condition tripwire for MARKET ACCIDENTS (fast, forced-selling dislocations like 1987, the 2019 repo spasm, or March 2020 — distinct from recessions). Condition 1: any fast-transmission channel (credit event, plumbing, basis trade, yen carry) is red. Condition 2: the yield curve is flat or inverted.",
    calc: "“Curve flat” uses the 3m10y spread — the 10-year Treasury yield minus the 3-month bill yield. Normally long rates sit well ABOVE short rates (lenders demand more for locking money up longer), so the spread is comfortably positive and the curve is called STEEP. When the Fed pushes short rates up, or investors rush into long bonds expecting trouble, the gap shrinks — the curve FLATTENS — and can go negative (INVERT: short rates above long rates). A flat/inverted curve means money is expensive TODAY relative to the future: levered players earn nothing for borrowing short to hold assets, funding cushions vanish, and the whole system runs with no shock absorber. The gauge trips condition 2 when the spread has touched below +0.25 percentage points within the trailing 6 months.",
    read: "GREEN = disarmed. YELLOW = armed (one condition met). RED = both — the configuration that, in the 1981–2026 hindcast, preceded the start of a ≥15% S&P drawdown within 12 months in 44% of months versus a 20% base rate; 5 of its 11 historical signal-clusters were followed by one, flagging LTCM 1998 four months early, 2007 up to twelve months early, 2019 eleven, and 2025 twelve. The meter shows where the spread sits now (solid dot) and its 6-month low (hollow dot) relative to the red trip zone — watch the dots drift toward the line as the curve flattens.",
    caveat: "A high-conviction tripwire, not a net: it missed 2018 (curve stayed steep) and 2021 (policy-driven grind, the slow channels' domain), and a sibling rule (oil/policy window + flat curve) scores the same within noise. Both conditions and the +0.25pp threshold come from the study's pre-specified design (studies/pin-rule-hindcast v2) — nothing is fitted, ~11 clusters is a small sample, and 44% is descriptive history, not a calibrated probability.",
  },
  pin_board: {
    title: "Pin board — the gun vs. the trigger",
    what: "Dalio's framing: debt buildup, rich valuations, and fragile plumbing are the LOADED GUN; some shock — the PIN — pricks the bubble. The gun is tracked across this dashboard; this board watches the pin channels.",
    calc: "Six channels through which historical pricks actually arrived (oil shocks, Fed overtightening, credit accidents, fiscal repricing, plumbing seizures, geopolitical shocks), each scored green/yellow/red from measurable daily/weekly proxies.",
    read: "Honest epistemics: pins are inherently unpredictable — that's Dalio's own point. This board does NOT forecast the prick; it makes a spark visible within DAYS of ignition instead of in hindsight. Multiple channels flashing simultaneously is the dangerous configuration.",
    caveat: "A green board doesn't mean no pin exists — it means no spark is visible in the monitored channels yet. Novel shocks (a pandemic) can arrive through unmonitored channels.",
  },
  pin_oil: {
    title: "Oil / energy shock",
    what: "Energy price spikes tax consumers and force central banks to tighten into weakness.",
    calc: "12-month % change in WTI crude.",
    read: "Hamilton's research: oil shocks preceded ~10 of 11 postwar recessions. +25% = squeeze forming; +50% = historically recessionary territory.",
  },
  pin_policy: {
    title: "Central-bank overtightening",
    what: "Fast hiking cycles break the weakest balance sheet in the system — the question is only which one.",
    calc: "12-month change in the effective fed funds rate, bps.",
    read: "+200bps in a year = something usually cracks; +300bps = 2022-class shock. Note: CUTTING into weakness is the curve panel's re-steepening signal — this channel only watches the tightening side.",
  },
  pin_credit: {
    title: "Credit / banking accident",
    what: "Credit events (2008 subprime, 1998 LTCM, 2023 SVB) announce themselves through spread GAPS and emergency borrowing — never through levels.",
    calc: "HY OAS 20-day change (a gap of +75–150bps = accident in progress) + primary-credit discount-window borrowing (banks pay its stigma price only under true duress — it lit up within days of SVB).",
    read: "This is a tripwire, not a forecast: it confirms an accident within days. $10B+ at the window = yellow; $50B+ = systemic event underway.",
  },
  pin_fiscal: {
    title: "Fiscal / debt-service pin",
    what: "Dalio's core scenario: Treasury supply overwhelms demand, the market starts charging for fiscal risk, and debt service compounds — the gun and the pin in one channel.",
    calc: "Federal interest outlays as % of GDP (the loaded gun — slow, structural) + the 60-day move in the ACM term premium (the spark — the market actively repricing fiscal risk).",
    read: "Interest/GDP above ~3% historically marks the crowding-out zone (the late-1980s/early-90s peak). A term-premium jump of +40–75bps in ~3 months alongside a falling dollar and bid gold (see the Flow Compass debasement regime) is the fiscal pin actually being pulled.",
  },
  pin_plumbing: {
    title: "Funding-plumbing seizure",
    what: "The repo/reserves machinery that broke in Sept 2019 (and the UK gilt/LDI blowup of 2022). Plumbing breaks FAST and forces central-bank intervention.",
    calc: "SOFR−IORB spread (repo above the reserves floor = scarcity) + 26-week change in reserve balances (QT drain) + the overnight RRP balance (the system's shock absorber).",
    read: "The dangerous sequence: RRP drained to ~zero → reserves falling → SOFR persistently above IORB. Each alone is context; all three together preceded the 2019 spasm.",
  },
  pin_basis: {
    title: "Basis-trade unwind",
    what: "Hedge funds run a massive arbitrage: long cash Treasuries, short Treasury futures, levered 20–50×. Their aggregate net-short futures book measures the trade's size — and its forced-unwind potential.",
    calc: "CFTC Traders-in-Financial-Futures (weekly): leveraged-fund net short summed across the UST futures complex (2y through ultra-bond), in millions of contracts, plus its percentile vs history since 2010.",
    read: "March 2020: this trade unwound violently and broke the Treasury market until the Fed stepped in with $1.6T of purchases. A bigger book = a bigger potential fire-sale. >4M contracts = crowded; >5.5M = record-zone crowding.",
    caveat: "Crowding is measurable; the trigger isn't — an unwind needs a vol/margin spike (watch the MOVE proxy and plumbing channels for the spark). Data lags ~3 business days.",
  },
  pin_private_credit: {
    title: "Corporate & private credit",
    what: "This cycle's leverage grew OUTSIDE the banking system: roughly $1.7T of private credit plus ~$1.3T of bank loans funding those vehicles, atop a record corporate maturity wall. No prior recession had this structure — a pin board built only on past bubbles would miss it entirely.",
    calc: "Three reads. (1) CCC-and-lower bond spread, as a percentile of its own history since 1996 — the tier where refinancing distress prices first. (2) The GAP between CCC and BBB spreads (percentile): investment grade priced for perfection while the distress tier cracks is a bifurcation the aggregate high-yield spread hides. (3) Bank lending to nondepository financial institutions (the Fed's H.8 breakout, added precisely to watch this) — month-over-month annualized growth.",
    read: "Private-credit marks are opaque and lag by quarters; public CCC bonds and the funding pipe are the real-time windows. Distress percentile high + dispersion extreme + NDFI loan growth stalling together = the private-credit margin call arriving. Any one alone is context.",
    caveat: "The NDFI series only starts 2015 — it has never seen a recession, so its thresholds are judgment, not history. And CCC is a proxy: private loans are floating-rate and covenant-lite in ways public bonds aren't.",
  },
  pin_carry: {
    title: "Yen-carry unwind",
    what: "Trillions of dollars of global positions are funded by borrowing cheap yen. When the yen appreciates sharply, those positions lose money on the funding leg and get force-unwound — selling whatever they own, including US assets. August 2024 demonstrated it: a BoJ hike → ~8% yen surge → days of global deleveraging.",
    calc: "USD/JPY 1-month % change (falling = yen appreciating = stress; yellow at −4%, red at −7%, calibrated to the Aug-2024 episode) plus the 12-month change in 10-year JGB yields — rising Japanese yields shrink the carry's profit cushion and pull Japanese capital home (they're also a structural buyer of Treasuries).",
    read: "The FX leg is the trigger and moves in days; the JGB leg is the slow pressure making the trigger easier to pull. Green FX + rising JGB = loaded but not firing.",
    caveat: "Carry unwinds have so far produced violent vol shocks, not recessions — this channel warns of market breakage, which matters here because forced selling transmits into Treasuries. JGB data is monthly with ~2-month lag.",
  },
  transmission_note: {
    title: "Transmission watch — spark meets storm conditions",
    what: "A caution that appears under the recession dial ONLY when two things are true at once: a fast, multi-trillion pin channel (credit accident, plumbing, basis trade, carry unwind) is flashing red, AND the 12-month curve model is already elevated (≥30%). History's lesson: market accidents on a calm macro backdrop stayed contained (LTCM 1998, repo 2019, yen unwind Aug 2024); the same accidents on a vulnerable backdrop became 2008.",
    calc: "A rule, not a model: any fast/high-mass channel RED + 12-month probability ≥ 30% → the note shows. Slow channels (private credit: weeks–months; fiscal: quarters) don't trip it — they give time, and speak through the composite instead.",
    read: "When you see this, the two independent warning systems agree — treat the dial's percentage as likely understating near-term risk, and go read WHICH channel is red and how it historically transmitted (the Playbook tab).",
    caveat: "Deliberately worded, never numbered. We tested the numeric version (augmenting the probit with financial-conditions data, 50 years, walk-forward): it added nothing to onset prediction — conditions indices confirm recessions, they don't predict them. With ~11 recessions on record, any 'pins add +X%' number would be invented. The calibrated probability is never adjusted.",
  },
  pin_attributes: {
    title: "Mass · speed · kill rate",
    what: "Not all pins are the same size. These badges size each channel on three researched attributes: MASS (the dollar exposure behind it), SPEED (how fast it transmits once it fires), and KILL RATE (its documented historical record as a recession trigger).",
    calc: "Static, sourced numbers — documented exposure sizes and episode counts from the literature (e.g. Hamilton's oil-shock count, the CFTC-measured basis book). Deliberately NOT fitted weights: with ~11 postwar recessions and nine channels, any statistically fitted 'probability contribution' would be curve-fitting noise.",
    read: "Use them to weigh a red: a RED on a fast, multi-trillion, high-kill-rate channel (credit accident) demands attention within days; a RED on a slow or historically benign channel (uncertainty) is context. Mass × speed tells you how big and how fast; kill rate tells you how often this gun has actually fired historically.",
    caveat: "A channel with a low historical kill rate isn't safe — the private-credit channel has NO kill-rate history precisely because it has never existed at this size. Unprecedented ≠ improbable.",
  },
  adjusted_prob: {
    title: "Term-premium-adjusted recession probability",
    what: "The same probit, but fed the 3m10y spread MINUS the ACM term premium — isolating the expectations component of the curve.",
    calc: "Adjusted spread = 3m10y − ACM TP10; horizon-specific probits refit on this input (sample from ~1990, so fewer recessions and wider confidence bands).",
    read: "The Bernanke critique: when QE pins the term premium negative, the raw curve inverts 'too easily' and overstates recession odds — arguably part of why 2022–24's inversion ran so long without a recession. When RAW and ADJUSTED agree, trust the signal more; when raw is alarmed and adjusted is calm, suspect term-premium distortion.",
  },
  effective_breadth: {
    title: "Effective breadth (causal families)",
    what: "The overfit-aware answer to 'are my 8 indicators really 8?' Permits, trucks, and capex are all downstream of interest rates — when they flash together that may be ONE cause, not three.",
    calc: "Indicators are grouped a priori (no fitted correlations) into causal families: Housing/Capex {permits, trucks, core capex} · Credit {SLOOS} · Labor {temp help} · Broad activity {CFNAI, GDPNow, Chauvet-Piger}. A family flashes when at least half its included, live members flash.",
    read: "Read \"X of 4 families flashing\" as the deduplicated signal: 3 indicators flashing inside one family is weaker evidence than 2 flashing across different families. Real recessions light up MULTIPLE families.",
  },
  alert_beacon: {
    title: "Alert beacon",
    what: "A single at-a-glance status light for the whole dashboard, in the header.",
    calc: "Worst of: composite band (HIGH/SEVERE), any CRITICAL metric (e.g. re-steepening), RED metric count, pin-board overall status, and logged high-severity events.",
    read: "Green dot = nothing flashing anywhere. Pulsing amber = warnings warming. Pulsing red = at least one critical/red condition — click it to jump to the event feed.",
    caveat: "On the free hosting tier the event LOG resets on redeploys; the beacon also derives from live metric state, so current conditions always show.",
  },
  pin_uncertainty: {
    title: "Uncertainty / geopolitical shock",
    what: "Exogenous pins — wars, embargoes, tariff shocks, debt-ceiling standoffs — show up in policy-uncertainty indices before they show up in earnings.",
    calc: "30-day average of the daily Economic Policy Uncertainty index, as a percentile of its full history since 1985.",
    read: ">90th percentile = elevated; >97.5th = crisis-grade uncertainty.",
    caveat: "The noisiest channel: elevated uncertainty usually resolves benignly. Treat as context that sharpens the other channels, never as confirmation by itself.",
  },

  "labor.unrate": {
    title: "Unemployment rate",
    what: "The headline U-3 rate — shown for context only.",
    calc: "BLS monthly rate (FRED UNRATE).",
    read: "It is a LAGGING indicator: it bottoms as recessions begin and keeps rising after they end. That's why it's excluded from the forward-looking stress score — its useful content is its rate of change, which is exactly what the Sahm Rule extracts.",
  },
};

// Direct metric_id lookups plus family fallbacks (e.g. any curve.* pair).
export function glossaryFor(metricId: string): GlossaryEntry | undefined {
  if (GLOSSARY[metricId]) return GLOSSARY[metricId];
  if (metricId.startsWith("curve.")) return GLOSSARY.curve_pair;
  if (metricId === "recession.prob") return GLOSSARY.recession_prob;
  return undefined;
}
