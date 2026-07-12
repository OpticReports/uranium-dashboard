// In-depth explanations for every key metric and concept, written for careful
// interpretation — each entry: what it is, how it's calculated, how to read it,
// and (where it matters) the trap to avoid. Rendered by <InfoTip/>.

export interface GlossaryEntry {
  title: string;
  what: string;
  calc?: string;
  read?: string;
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
