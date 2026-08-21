# Catalyst Options Engine

Awareness engine for **pre-catalyst asymmetric option setups** in biotech/pharma.

Born from the 2026-08-19 miss: Moderna rose **+130%** on a Phase 3 melanoma
interim readout (V940/intismeran, Merck-led with Moderna as collaborator) that
the genomics tracker's sponsor-name query didn't surface. The systematic
answer to: *"if news is about to break and the stock hasn't really moved,
that's an asymmetric gamble — build awareness + strategy for those events."*

The engine scans a wide radar of names for the coincidence of three things:

1. a **dated high-impact catalyst** close in time (or an undated phase-3
   "interim watch" — trials like V940-001 that can drop an interim at any
   time carry a watch flag, **never a fabricated date**);
2. a **quiet tape** (10-day drift small relative to realized vol — the move
   hasn't happened yet);
3. **cheap optionality** (ATM implied vol not already bloated vs. realized).

It scores those setups, proposes defined-risk long-premium structures on
paper, and grades itself.

## PAPER ONLY. KEYLESS. (separation of powers)

This service is a **decision brain**: it holds **no credentials** and has
**no execution path** — house law (CLAUDE.md): strategy engines are always
keyless; credentials live only in executor services. Any future live options
execution would route through **ibkr-executor**, never this service. There is
no order code here to arm.

## Data lanes (all keyless, all degrade gracefully)

| Lane | Source | When dark |
|---|---|---|
| Catalysts | ClinicalTrials.gov API v2, `query.spons` per **registered alias** (radar.yaml `ctgov_names` — "ModernaTX" works, "Moderna" doesn't; the alias union also catches collaborator-side trials like Merck-led V940). Manual PDUFA/AdComm/interim dates via `POST /catalysts`. | Logged warning; calendar keeps last known rows |
| Daily prices | stockanalysis.com history API (browser UA; `a` = adjusted close) | drift/realized-vol = None, setup flagged `price lane dark` |
| Option chains | api.nasdaq.com option-chain (browser UA; null-strike group rows skipped; expiry parsed from the drillDownURL yymmdd) | iv_ratio = None (score neutral + "IV unknown"); proposals priced by scenario-IV Black-Scholes, `pricing_basis="bs_scenario"` stamped on every affected row |

**Render caveat:** the Nasdaq chain lane is verified working from a dev
container; datacenter-IP blocking on Render is possible. The engine is built
to run indefinitely with the chain lane dark — every affected setup and
proposal says so explicitly rather than silently degrading.

## Scoring

```
score = clamp( 96 × impact_weight
                  × exp(−ln2 × days_to_event / 21)          # 21d half-life
                  × clamp(1.25 − |drift_z10|/2, 0.25, 1.25) # quiet tape
                  × clamp(2 − iv_ratio/2,       0.5,  1.5), # cheap vol
               0, 100 )
```

* `drift_z10` = 10d return / (20d realized vol scaled to 10d).
* `iv_ratio` = ATM IV at the expiry just after the event / 20d realized vol.
* Missing inputs are **neutral (1.0) and flagged**, never fabricated.
* Anchor (test-pinned): impact 1.0, 21 days out, drift 0, iv_ratio 2.0 → **60**.
* Proposals only above `min_score` 55 (engine.yaml).

Sanity check from launch day: MRNA **after** the +130% pop scored ~31
(iv_ratio 2.6, ATM IV 159%) — the engine correctly refuses to chase an event
that already resolved. The point is to be positioned in the quiet weeks
before, not the loud day after.

## Sizing & spread honesty

* Default structure **ATM straddle** (direction-agnostic; we bet the move is
  bigger than priced, not on its sign). `CALL_ONLY`/`PUT_ONLY` only when an
  operator attaches a `direction_lean` to a catalyst — never auto-inferred.
* Premium budget **50bps of paper equity** per setup; 1-contract minimum
  (flagged when the minimum exceeds the budget). **Max loss = premium paid,
  always** — long premium only, no short-vol structures exist here.
* **Entries pay the ASK, exits receive the BID** when real quotes exist; the
  paper book eats the spread. Marks use chain MID, else BS at entry IV
  (`mark_basis` recorded). Auto-close at min(expiry, event + 3 trading days),
  at chain bid else intrinsic (`close_basis` recorded).
* One-line caveats: `bs_scenario` premiums are scenario math (IV 1.0), not
  fills; quoted-size paper fills are optimistic vs. real biotech option
  liquidity; r=0 in all BS math; exchange holidays not modeled; daily bars
  lag intraday moves (drift is measured through the prior close).

## Staged rollout gates

1. **Observe** — radar + scores only; read the flags, tune the radar.
2. **Paper track record** — the book grades itself; **≥ 20 graded (closed)
   setups** before any conclusions are drawn.
3. Only then: discuss **human-executed** sizing for real events.
   **Never automated execution from this service** — if that day comes, it is
   a separate ibkr-executor project with its own gates.

## Evidence

Frozen numbers from the pre-catalyst asymmetry study
(`genomics-alpha-tracker/docs/PRE_CATALYST_ASYMMETRY_STUDY.md`, frozen
2026-08-19, 37 web-verified binary readouts 2022-2025, counter-agent verdict
PASS WITH CORRECTIONS — all applied):

- Median |event-day move| when a binary lands: **39.9%** (sample selected for
  sharp movers — every number below is an UPPER BOUND).
- ATM straddle bought 10 sessions pre-event, intrinsic exit, MEDIAN payoff
  multiple by entry IV: **3.57x @ 60% IV · 2.24x @ 100% · 1.50x @ 150% ·
  0.77x @ 300%** — the median crosses below breakeven between 150% and 200%.
- Median-based breakeven sharp-share (share of all real events that must land
  sharp, 8% fizzle assumed): **11% @ 60% IV · 32% @ 100% · 59% @ 150% ·
  100% @ 200%+**. Known-binary IV (150-300% [HEURISTIC]) does not pay;
  underpriced/undated events can.
- "Quiet tape -> bigger event move" was REJECTED (Spearman +0.25, n.s.);
  the quiet_factor in this engine's score is therefore justified ONLY by its
  IV form — quiet tape -> cheaper entry IV -> better payoff per premium
  dollar — which had no historical option data to test against and is exactly
  what this paper book exists to grade (tracker hypothesis H7).
- No historical option prices were used in the study; entries were BS at
  scenario IVs, exits at intrinsic. This engine's real-chain snapshots are the
  first honest measurement of the entry side.

## Running

```
cd catalyst-options-engine/backend
pip install -r requirements.txt
python -m pytest tests -q          # offline; fixtures are real captured shapes
uvicorn app.main:app --reload      # status page at http://localhost:8000/
```

API: `GET /health /radar /setups /paper/book /paper/positions /catalysts` ·
`POST /catalysts /scan /paper/close/{id}`. Status page at `/` (server-rendered,
no build step). Scheduler (`RUN_SCHEDULER`): daily scan + hourly market-hours
chain refresh for names with days_to_event ≤ 21.
