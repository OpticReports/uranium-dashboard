# Genomics Alpha Tracker — Goals & Requirements (from operator questionnaire, 2026-07)

Distilled from the completed goals questionnaire. This is the reference for all
usability / trade-decision work on the tracker.

## Users & usage pattern
- **3 users** (operator + 2 teammates), EST-based, trading NYSE-listed names.
- Checked **several times a day**: pre-open, at open, first hour, midday, close.
- **Desktop/laptop first**; phone secondary.
- Expectation on open: data is **current**, and the actionable items are presented
  immediately — no digging.

## Trades it must feed (all of these)
Pre/post-catalyst positioning, momentum & narrative swings, headline trades,
short-squeeze setups, long-term accumulation zones, and blowup-avoidance on holdings.
- Holding period: **mixed, majority short-term**; long-term only for ~10x upside.
- Position sizes **$10–25k and $50–100k** → liquidity/float warnings matter on
  thin names.
- **Spot equities** primarily; usually long, shorting infrastructure exists.
- **Rarely holds through binaries**, but wants explicit hold-vs-sell-before framing
  (implied vs historical move, event sizing).

## What a flag must show before it's actionable
1. Why it fired (catalyst + date)
2. Valuation + analyst context
3. Chart with technical levels
4. **Suggested entry / stop / target**
5. **Historical hit-rate of that flag type**
6. Social sentiment state

## Signal model decisions
- **Equal weights for now** — until the team can "see and feel" the data. Retune
  from evidence (see track record below), not intuition.
- Component scoring granularity: **0–10 feel preferred over 1–5** in UI copy.
- **Add new signals:** insider buying, fund flows/13F, relative strength vs
  benchmark, volume anomalies, competitor-readout-hits-peer.
- **Bias against false positives** — flags should fire conservatively; a flag that
  fires must be trustworthy.
- New composite entry idea confirmed: **flag = pullback + upcoming catalyst**.
- **Exits:** yes — the tracker should express exit signals (catalyst passed, signal
  decayed, take-profit-into-event).

## Universe
- Current 32 names: **keep**.
- **Auto-suggest** new theme entrants (IPOs, liquidity-threshold crossings) — still
  operator-approved before joining the universe.
- Grouping/filters: operator asked for a recommendation → adopt **liquidity tiers**
  (by avg daily dollar volume + market cap) as a first-class grouping:
  - Tier A: >$25M ADDV — full position sizes fine
  - Tier B: $5–25M ADDV — size warning at $50k+
  - Tier C: <$5M ADDV — thin-float badge, explicit slippage warning
- Subsector rotation views **matter** (gene-editing vs sequencing vs dx, etc).
- Long-term direction (6-month success criterion): live multi-indicator tracking for
  **any NYSE symbol the operator adds**, not only the genomics universe — the
  architecture already supports arbitrary tickers; keep it that way.

## Benchmarks & regime
- Show moves relative to **XBI, ARKG, and NBI** (multiple benchmarks, not one).
- Add a **macro/sector regime readout** (rates, biotech fund flows, XBI trend).

## Alerts & delivery
- Pull-only acceptable **today**; **Telegram** is the future push channel.
- Interrupt-worthy = anything **actionable within ~24h** (new flags, flags on held
  names, imminent catalysts).
- **Pre-market digest** wanted: overnight global markets + what changed while the
  team slept, framed for an EST/NYSE open.

## Analyst Chat
- Keep; make more robust: saveable memos as a **decision journal per name**
  ("what did I think at entry").

## Track record & self-improvement (highest-conviction ask)
- **Log every flag/score at fire-time**; compute forward 1w/1m/3m returns; surface
  per-flag-type hit rates. Signals that don't pay get down-weighted — this is how
  the "equal weights for now" evolves into evidence-based weights.
- Operator will report actual trades taken so they can be tracked against signals;
  signals are tracked **regardless** of whether a trade was taken.

## Biggest friction (verbatim intent)
> "If I wasn't the one who built this I wouldn't have a clue what is happening —
> it isn't very user friendly."

**A first-time viewer must understand the tracker's purpose within seconds of
opening it.** This is the top usability priority: an orientation-first home view
("what is this / what's actionable right now / why"), plain-language labels,
explanations on every number.

## Open items
- Monthly data-feed budget: **unanswered** — free-tier baseline until specified.
- Telegram alerts: deferred until requested.

---

## Build status (2026-07-14)

**Shipped:**
- Calls Log: exact auto-generated calls (entry / 3×ATR stop / 2R target /
  sell-before-binary time-stop), gap-aware self-grading, per-signal scorecard,
  manual call logging. Defaults set from `docs/BACKTEST_CALLS.md` evidence.
- Flag track record: EVERY flag graded at fire-time vs forward 1w/1m/3m returns
  (raw + XBI-excess) — `/flags/track-record`. This is the learning loop that
  retunes the equal starting weights.
- Flag re-fire suppression (7d per symbol+type) so state-like flags stay eventful.
- New flags: pullback-into-catalyst (ATR-normalized, depth-capped, above-50dma
  qualifier), volume anomaly (log-z + $1M floor), insider buying cluster
  (distinct insiders + $25k floor). Pullback & insider are OBSERVE-ONLY until
  their track record earns call-trigger status.
- Today landing tab (default): purpose statement, regime strip (XBI/ARKG/IBB),
  actionable cards (why it fired + that signal's honest hit rate + reference
  levels + liquidity tier + binary framing + implied move), open calls with
  signal-decay hints, 7-day catalysts, pre-market digest. NY-timezone aware,
  data-freshness stamped.
- Liquidity tiers (median ADDV): A/B/C badges, sizing warnings, Tier C excluded
  from auto-calls, tier stamped on calls at fire-time.
- Equal signal weights (4 × 0.225; runway penalty stays 0.10 as a risk drag,
  not an alpha term). Composite displayed 0–10 (render-only; storage stays 0–100).
- Benchmarks + relative strength vs XBI (20/60d, unadjusted) + regime label.
- Insider-transaction ingestion (yfinance, daily).
- Append-only decision journal (chat memos + desk notes, per name).
- Exit-mechanics backtest on ~2y real adjusted bars: genuinely paired grid
  (identical entries per cell), open-first gap-aware fills, cluster bootstrap,
  slippage-adjusted plateau selection. Key findings: tight stops' frictionless
  edge is a cost artifact; 3×ATR/3:1/45d is robust net-of-costs in both
  regimes (2:1 statistically indistinguishable). The pullback entry's
  price-half alone showed NO edge vs baseline (kept observe-only).
- Two adversarial review rounds applied: round 1 (design) forced the flag
  track record, dedup, binary-expiry refusal, and observe-only gating; round 2
  (code) caught open-first grading (gap-up-then-fade days were being scored as
  stop-losses), the Monday-binary time-stop hole, paired-entry claims, and
  track-record denominator honesty — all fixed and tested.

**Deferred (with reasons):**
- 13F/fund flows: needs a data feed decision (budget question unanswered).
- Auto-suggested universe entrants: needs a screening feed.
- Telegram alerts: operator said "at some point"; revisit when asked.
- Historical event-move (implied vs realized) framing: needs an event-history
  dataset; the diffusive implied move shipped with honest labeling instead.
- Subsector RS rotation rollup: cheap follow-up on the RS machinery.
