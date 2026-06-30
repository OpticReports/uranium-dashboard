// Plain-language definitions for every metric, written for a non-quant.
// Each: what it is, how it's computed, and how to read it. Used by <InfoTip/>.

export const GLOSSARY = {
  composite: {
    title: "Alpha Signal (0–100)",
    what: "The headline score — a single, peer-relative read on how attractive a name's forward-looking setup is right now.",
    calc: "A weighted blend of the five component columns (each first scaled 0–100), averaged using weights set in config. Missing components are excluded, not counted as zero.",
    read: "50 = middle of the universe. 70+ = strong setup, 100 = best-positioned name. It's a ranking of opportunity — not a price, target, or expected return.",
  },
  revision_velocity: {
    title: "Revision Velocity",
    what: "How fast — and which way — Wall Street analysts are changing their forecasts (EPS estimates and price targets).",
    calc: "Each recent revision is scored by direction (up = +, down = −) and weighted toward more recent ones, then ranked 0–100 vs. peers.",
    read: "High = analysts turning more bullish (a leading indicator that often precedes price). Low = estimates being cut.",
  },
  catalyst_score: {
    title: "Catalyst Score",
    what: "How much market-moving news is coming up soon for this name.",
    calc: "Sums upcoming catalysts (FDA decisions, trial readouts, earnings) weighted by their impact and how close they are — nearer events count more (time-decay) — then ranked 0–100.",
    read: "High = important, often binary events are imminent. That means bigger potential moves in both directions, so size positions with the event in mind.",
  },
  hype_divergence: {
    title: "Hype Divergence",
    what: "Whether social/retail chatter is building faster than the stock price has moved.",
    calc: "Z-score of the acceleration in mention volume (Reddit/StockTwits/X) minus the z-score of recent price change, ranked 0–100.",
    read: "High = buzz is ramping ahead of price (early-interest signal). Low = price moving with little chatter. The edge is chatter leading price.",
  },
  positioning: {
    title: "Positioning",
    what: "How crowded or squeezable the stock is, based on short interest and options.",
    calc: "Percentile of short interest plus options skew vs. the universe, scaled 0–100.",
    read: "High = heavily shorted / crowded — squeeze potential, but also a caution sign. Often n/a for thin-float names with no options data.",
  },
  runway_penalty: {
    title: "Cash Runway",
    what: "A balance-sheet safety check for cash-burning biotechs.",
    calc: "From cash ÷ quarterly burn = quarters of runway. Shown 0–100: high = ample runway, low = approaching a cash cliff (dilution risk).",
    read: "Low values drag the Alpha Signal down. n/a = profitable or no meaningful burn (e.g., large pharma).",
  },
  tags: {
    title: "Subsector Tags",
    what: "Free-form theme labels you assign to each name (e.g. gene-editing, liquid-biopsy).",
    calc: "Editable per row or in watchlist.yaml; signal can be rolled up by theme in the Sector Heatmap.",
    read: "Use them to group names into the themes you actually trade.",
  },
  momentum: {
    title: "Momentum (Δ7d)",
    what: "The change in a name's (or theme's) Alpha Signal over the last ~7 days.",
    calc: "Latest composite minus the composite from ~7 days ago, using saved score history.",
    read: "Positive = the setup is improving (inflecting up); negative = deteriorating. The alpha is often in the change, not the level.",
  },
  raw: {
    title: "Raw",
    what: "The driver's actual measured value, in its own native units — before any scaling.",
    calc: "Pulled straight from the data: e.g. quarters of cash runway, a sum of weighted upcoming catalysts, the net direction of analyst revisions.",
    read: "Not comparable across rows — each driver is measured differently, so a raw 0.62 and a raw 7.8q live on totally different scales. It answers 'what is the underlying number?', not 'is it good?'.",
  },
  normalized: {
    title: "Normalized (0–100)",
    what: "The raw value re-expressed on a common 0–100, peer-relative scale where 50 = the universe average.",
    calc: "Cross-sectional ranking (z-score / percentile) of this name's raw value against all other names in the universe for that one driver.",
    read: "This is the equalizer that makes drivers comparable. 70+ = ranks well above peers on that driver; below 50 = below average. A 'good' raw number only becomes obvious here (e.g. 7.8q runway → ~97).",
  },
  weight: {
    title: "Weight",
    what: "How much this driver counts toward the final Alpha Signal — your priorities.",
    calc: "Set in scoring.yaml (editable, then POST /scores/reload). The active weights sum to 1.0; a missing component's weight is dropped from the denominator.",
    read: "Higher weight = this driver moves the score more. It reflects what you've decided matters, not anything about this particular stock.",
  },
  weighted: {
    title: "Weighted",
    what: "The points this driver actually contributes to the Alpha Signal.",
    calc: "Normalized × Weight. The Alpha Signal is the sum of these divided by the sum of the non-missing weights (a weighted average).",
    read: "This is where you see which drivers are carrying — or dragging — the score. Add the Weighted column (over the used weights) and you get the headline number.",
  },
  na: {
    title: "“n/a” vs 0",
    what: "n/a means there's no data for that input — deliberately different from a real 0.",
    calc: "Missing components are dropped from the Alpha Signal's weighting rather than counted as zero, so a name isn't penalized for patchy data.",
    read: "Common for thin-float names (options/short interest) and profitable names (runway). Treat low-confidence rows with extra caution.",
  },
};
