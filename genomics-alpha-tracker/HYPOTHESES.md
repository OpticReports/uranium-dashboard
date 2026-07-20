# HYPOTHESES.md — the research → observe → grade → promote backlog

Knowledge proposes; the market disposes. Reading (books, papers, base-rate
studies) is a **hypothesis generator**, never a shortcut into the live config.
Every candidate rule distilled from research lands here first, then must earn
its place through the same graded pipeline everything else goes through.

## The lifecycle of a hypothesis

```
 research pass → HYPOTHESES.md (backlog)
       → implement as an OBSERVE-ONLY flag (fires, forward-returns graded,
         NEVER generates a call)
       → accrues a track record in /flags/track-record
       → the tuner's promotion gate (evals/replay.py, TUNING.md matrix):
         n ≥ 20, Wilson 90% lower bound > 0.50, positive avg excess
       → PASS → PR to add it as a call trigger (human merges)
       → FAIL/insufficient → stays observe-only or is retired with its record
```

Rules:
- A hypothesis must be **specific and testable** — a condition the engine can
  evaluate on data it has, with a clear directional prediction. "Momentum
  matters" is not a hypothesis; "a >3×-ADV volume spike with a green close
  continues for 5+ trading days more often than base" is.
- Cite the source that motivated it (a `knowledge/` doc or a paper).
- New flags ship observe-only by DEFAULT. Promotion is never automatic and
  never skips the gate — no matter how good the source sounds.
- One hypothesis becomes one flag. Keep them separable so the track record
  attributes cleanly.

## Status legend

`proposed` → in the backlog, not yet built · `observing` → live as an
observe-only flag, accruing outcomes · `promoted` → passed the gate, now a
call trigger · `retired` → failed the gate or decayed; kept for the record.

## Backlog

> Seeded from the first research pass. Each entry: hypothesis, prediction,
> how to implement, source, status. These are CANDIDATES — none is in the
> live config until it earns promotion.

### H1 — Insider cluster buys ahead of a catalyst
- **Hypothesis:** open-market purchases by ≥2 distinct insiders within 60 days
  BEFORE a high-impact catalyst outperform the sector more than insider
  clusters without a nearby catalyst.
- **Prediction:** positive 1–3 month excess vs XBI; edge concentrated in the
  pre-catalyst subset.
- **Implement:** already have `insider_buying_cluster` (observe-only) and the
  catalyst calendar — add a catalyst-proximity variant and compare track
  records.
- **Source:** `knowledge/market_structure.md` (insider-signal literature),
  `knowledge/fda_catalyst_stats.md` (catalyst behavior).
- **Status:** proposed.

### H2 — High short interest is a HEADWIND, not squeeze fuel
- **Hypothesis:** consistent with the empirical short-interest literature, top
  short-interest-percentile names underperform on average — the naive squeeze
  thesis is negative-EV without a specific spark.
- **Prediction:** negative average forward excess for high-SI names absent a
  co-occurring catalyst/flow trigger.
- **Implement:** grade a `high_short_interest` observe-only flag; if the sign
  is negative (as the literature predicts), that's a REASON to down-weight the
  positioning component's squeeze reading — a demotion-style finding.
- **Source:** `knowledge/market_structure.md` (short-interest studies).
- **Status:** proposed.

### H3 — Pullback-into-catalyst still needs its own proof
- **Hypothesis:** the current `pullback_into_catalyst` flag (ATR-normalized dip
  + trend qualifier + tradeable catalyst window) beats the systematic baseline.
- **Prediction:** positive 1m excess; the backtest's price-only variant showed
  NO edge, so the catalyst-conditioning is the part on trial.
- **Implement:** already observe-only — just needs outcomes to accrue to n≥20.
- **Source:** `docs/BACKTEST_CALLS.md`, `knowledge/fda_catalyst_stats.md`.
- **Status:** observing.

### H4 — Post-CRL drift
- **Hypothesis:** after a Complete Response Letter, names drift (don't
  instantly fully price the setback), per the catalyst-behavior notes.
- **Prediction:** a tradeable drift window post-CRL in one direction.
- **Implement:** needs a CRL event type in the catalyst data (not currently
  ingested) — a data-collection prerequisite before it can be a flag.
- **Source:** `knowledge/fda_catalyst_stats.md`.
- **Status:** proposed (blocked on CRL event ingestion).

### H5 — Financing-pressure fade into strength
- **Hypothesis:** cash-poor names (short runway) that rally hard into a catalyst
  are dilution candidates; the run often precedes an offering.
- **Prediction:** negative forward excess for {short runway + big pre-catalyst
  run-up}; argues for taking profit before the event, not holding.
- **Implement:** combine `runway_quarters` + recent return + catalyst proximity
  into an observe-only `dilution_risk` flag.
- **Source:** `knowledge/fda_catalyst_stats.md` (financing behavior).
- **Status:** proposed.

---

_Add new hypotheses at the bottom of the backlog. When one changes status,
edit its entry — this file is the audit trail of what the research suggested
and whether the market agreed._
