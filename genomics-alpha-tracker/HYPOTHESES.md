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
- **Evidence (10y historical backtest, `docs/BACKTEST_SIGNALS.md`):** neither
  confirmed nor refuted — FINRA days-to-cover ≥ 10 fires earned +1.24%/1m vs
  XBI, statistically indistinguishable from the +1.08% survivorship baseline.
  In THIS (surviving) universe, high SI was neither headwind nor squeeze fuel.
  Keeps the positioning component's squeeze reading on a short leash.
- **Source:** `knowledge/market_structure.md` (short-interest studies).
- **Status:** tested-historical (no edge either way); revisit with live data.

### H3 — Pullback-into-catalyst still needs its own proof
- **Hypothesis:** the current `pullback_into_catalyst` flag (ATR-normalized dip
  + trend qualifier + tradeable catalyst window) beats the systematic baseline.
- **Prediction:** positive 1m excess; the catalyst-conditioning is on trial.
- **Evidence (10y historical backtest):** the PRICE half alone graded WEAK —
  +1.66%/1m, above the +1.08% baseline but CI-overlapping it (could be drift).
  The catalyst half remains untestable historically — live record decides.
- **Source:** `docs/BACKTEST_CALLS.md`, `docs/BACKTEST_SIGNALS.md`,
  `knowledge/fda_catalyst_stats.md`.
- **Status:** observing.

### H6 — Relative-strength leadership persists (SUPPORTED historically)
- **Hypothesis:** names beating XBI by ≥15 points over 60 trading days keep
  outperforming (sector-relative momentum).
- **Evidence (10y historical backtest):** the ONLY signal to clear the
  survivorship baseline decisively — +2.55%/1m vs XBI (n=2,819, 1,107
  clusters), +1.47% over baseline, CI90 low clears the baseline mean, and
  consistent across 1w/1m/3m horizons.
- **Implement:** `relative_strength_leader` observe-only flag is now LIVE
  (flags.yaml `min_rs_60d: 0.15`) — its live track record must confirm the
  backtest before the promotion gate can make it a call trigger.
- **Source:** `docs/BACKTEST_SIGNALS.md`, `knowledge/market_structure.md`
  (momentum literature).
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

### H7 — Quiet-into-catalyst is where convexity pays
- **Hypothesis:** names entering a high-impact binary window (impact ≥ 0.85,
  due in 5–45 days) with |drift_z| ≤ 0.75 — trailing 10-bar return small
  relative to the name's own 20d realized vol — produce larger absolute event
  moves relative to what the drift predicted; the quiet-into-catalyst subset
  is where convex (options) structures pay. The MRNA/INTerpath miss is the
  motivating case: +130% on the readout with no pre-event run.
- **Prediction:** larger |forward returns| (both tails) for the low-|drift_z|
  pre-binary subset vs the running-into-the-event subset; the flag's track
  record should show fat absolute excess even if signed excess is mixed.
- **Implement:** `quiet_before_catalyst` observe-only flag (flags.yaml),
  drift_z computed in the scoring engine from closes (None on insufficient
  data, never a silent zero).
- **Source:** `docs/PRE_CATALYST_ASYMMETRY_STUDY.md`,
  `knowledge/fda_catalyst_stats.md`.
- **Status:** observing.

### H8 — XBI 200dma regime gate on the calls book
- **Hypothesis:** suppressing call entries while XBI sits below its 200dma
  (prior trading day's close vs prior-day SMA — the level actionable at the
  open) improves the book's Sharpe AND Calmar without giving up CAGR.
- **Evidence (pre-registered 10y variant campaign, counter-agent PASS WITH
  CORRECTIONS 2026-08-20, prior-day-gate restated numbers):** V2 survived the
  registered bar — $261,677 / +9.48% CAGR / 33.7% maxDD / Sharpe 0.58 vs V0's
  $208,760 / +7.17% / 65.5% / 0.42; the 50dma sibling (V1) also survived at
  $261,417 / 0.57. Caveats: replay evidence on a survivor universe; rf=0
  understates gated books; XBI buy-and-hold itself cleared the same bar.
- **Implement:** replay evidence only — needs live observe-only tracking of
  the gate state and its would-have-suppressed entries BEFORE any calls.yaml
  change (TUNING.md promotion gate applies as always).
- **Source:** `docs/BACKTEST_VARIANTS_10Y.md`,
  `docs/VARIANTS_PREREGISTRATION.md`.
- **Status:** observing (shadow-grader live as of 2026-08-20 — daily
  RegimeLog of both MAs on the prior-close convention, `GET /shadow/regime`).

### H9 — Cross-sectional momentum ranking adds selection value within the universe (RELATIVE claim only)
- **Hypothesis:** ranking universe names by trailing 60-bar return vs XBI and
  holding the top ranks selects better names than the unranked universe —
  a RELATIVE claim about ranking inside whatever universe the engine tracks.
- **Evidence (same campaign, V6a/V6b survived the registered bar):** the
  ABSOLUTE numbers are explicitly unusable — a 24-name survivor-only universe
  is the worst case of survivorship bias for momentum ("buy the recent winners
  among known eventual winners"), and V6a's 82.4% maxDD / 5-name concentration
  is untradeable as a standalone book. Counter-agent robustness: the result is
  not the tier filter (no-filter $2,177,355) or the costs (tier-true
  $1,529,190) — only the relative selection-value reading survives.
- **Implement:** as a ranking overlay/qualifier on existing fires (does the
  top tercile of 60-bar RS rank outperform the bottom within the live flag
  stream?), never as the standalone rank-portfolio book.
- **Source:** `docs/BACKTEST_VARIANTS_10Y.md`,
  `docs/VARIANTS_PREREGISTRATION.md`.
- **Status:** proposed.

### H10 — Trailing-stop exit engine (V10, EXPLORATORY)
- **Hypothesis:** replacing the fixed-stop/fixed-target exit with a
  3.0×ATR14 trailing stop from peak close (prior-bar levels, 90d time stop)
  improves risk-adjusted returns on rel_strength entries.
- **Evidence (same campaign, restated prior-day-gate numbers):** V10 survived
  the registered bar at $271,941 / +9.88% / 35.3% maxDD / Sharpe 0.55 vs V0's
  0.42 — but it is FLAGGED EXPLORATORY in the contract itself: a different
  exit engine carries the campaign's highest overfit risk, and the look-ahead
  correction cut its end value 22% ($349,081 → $271,941), showing how
  parameter-sensitive it is. A survival here is a hypothesis to re-derive,
  not a result.
- **Implement:** would need its own exit-grid registration round plus
  observe-only shadow grading of trailing exits alongside live exits; no
  engine change from this evidence alone.
- **Source:** `docs/BACKTEST_VARIANTS_10Y.md`,
  `docs/VARIANTS_PREREGISTRATION.md`.
- **Status:** proposed (exploratory).

### H11 — Gated trailing-exit call book (R2-A) is the engine's best construction
- **Hypothesis:** the combined-flag call book with a 200dma prior-close XBI
  regime gate and 3.0xATR trailing exits (no fixed target, 90d time stop)
  produces materially better risk-adjusted results than the live fixed
  3:1-target engine — replay: $469,242 / +15.67% CAGR / 35.6% maxDD /
  0.76 Sharpe vs V0's 0.42 and V2's 0.58 (double-baseline survivor).
  Re-based 2026-10-04 on the committed FMP cache; the Yahoo-basis replay
  read $430,406 / +14.73% / 0.73 and beat both baselines in 2/3
  sub-periods (its miss was 2023-2026 vs V2); on the re-based cache it
  beats them in 3/3, because the +9% move landed in that window. The
  full-period verdict is unchanged; that sub-period cell is the one place
  the re-basing flattered R2-A (docs/REBASE_FMP_LANE_2026-10-04.md).
- **Prediction:** live observe-only tracking of the same construction shows
  higher R expectancy and shallower book drawdown than the production
  engine's graded record over the same window.
- **Implement:** observe-only shadow grading (no calls.yaml change): grade
  each live auto-call under BOTH exit engines and log the gate state daily.
- **Source:** docs/BACKTEST_VARIANTS_R2.md + VARIANTS_PREREGISTRATION_R2.md
  (counter-agent PASS WITH CORRECTIONS both rounds).
- **Status:** observing (shadow-grader live as of 2026-08-20 — every live
  auto-call is re-graded under the R2-A trailing engine, observe-only;
  `GET /shadow/track-record`).
  ROUND-3 CAVEAT: the trail/time-stop robustness map is NOT a plateau
  (Sharpe 0.57-0.78; the registered cell's neighbor drops to 0.57) —
  exit-parameter sensitivity lowers prior confidence in the exact
  configuration; the live shadow record is the arbiter.

### H12 — On momentum books, the 200dma gate dominates the 50dma gate (relative claim only)
- **Hypothesis:** gate choice, not stock selection, drove the largest
  construction difference in the campaign: identical top-5 momentum books
  ended $2.05M (200dma) vs $733k (50dma), entirely from 2020-21 exposure.
  ABSOLUTE momentum-book numbers remain unusable (survivorship worst case).
- **Prediction:** any live momentum-style overlay should default to the
  slower gate; the faster gate's whipsaws are the measurable cost.
- **Implement:** carried with H8's observe-only gate tracking (log both MAs).
- **Source:** docs/BACKTEST_VARIANTS_R2.md (R2-E vs V6b), with the R2-E
  warning block's caveats.
- **Status:** proposed.

### H13 — R2-A as a diversifying sleeve on a core index holding
- **Hypothesis:** R2-A's low correlation to SPY (0.27 daily / 0.36 monthly,
  beta 0.34, driven by ~26% all-cash days and idiosyncratic biotech holdings)
  makes a 10-50% R2-A / SPY blend better than SPY alone on CAGR, max DD,
  Sharpe AND Calmar — a flat plateau across the whole weight range (daily
  granularity, optimum ~30-40%), holding in all three sub-periods. Known
  failure mode: crashes faster than the 200dma gate (Mar 2020: R2-A -11.7%
  alongside SPY).
- **Prediction:** with a live R2-A record (H11), the realized blend beats the
  same-period SPY on Sharpe and max DD.
- **Implement:** no action until H11's shadow-graded live record exists; then
  an allocation memo, not an engine change. Weights were swept post-hoc —
  the claim is the plateau, never a point weight.
- **Re-based 2026-10-04:** the 30/70 baseline on the committed FMP cache is
  +16.17% trading-day CAGR / 29.4% maxDD / 1.04 Sharpe (was +15.89% / 29.3%
  / 1.02 on the Yahoo basis); the correlation and blend numbers below were
  measured on the Yahoo-basis sleeve, which rounds 4-6 still read
  (archived as `r2a_daily_yahoo_2026-08.json`). Plateau claim unchanged.
- **Source:** docs/BACKTEST_VARIANTS_R2.md (R2-A) + correlation/blend
  analysis 2026-08-20 (this entry). Inherits every replay caveat.
- **Status:** proposed (blocked on H11). Round-3 notes: BIL-on-idle-cash is
  measurement realism worth ~+0.4pp (fold into the honest baseline); the
  flag-tilted sizing adds a thin +0.02 Sharpe (3/3 sub-periods); leverage,
  TSMOM overlay and vol-scaled weights all FAILED the registered bar — the
  plain 30/70 remains the construction.
- **Live-record honesty note (2026-09-04, standing):** the R2-A shadow
  record and the ibkr-executor's live book diverged from day one and the
  split is attributable, so no live-vs-replay comparison may be quoted
  without it. Sixteen auto-flag calls have fired (ids 1-16, all gate-on).
  Thirteen predate the 2026-08-28 go-live. Three were addressable and ALL
  THREE were lost: NTRA (14) and LLY (15), created 09:44 ET mid-session on
  08-28, were placed as MOO/OPG after the open and rejected 4x each, and
  BLEND_ENABLED was off that evening so the post-close retry never ran;
  MRK (16), created 21:27 ET on 09-02, fired into a 14-hour gateway
  outage. The executor's session guard (branch 5acccf0) closes the first
  mode; the gateway restart configuration closes the second. The shadow
  record is what the account WOULD have done had its entries reached the
  venue; it is not this account's track record.
  Two tracker-side findings from the same calls log: (a) `entry_price` on
  a call created MID-SESSION is the price at the moment the hourly calls
  job ran, not the fire-day close the R2-A convention names (12 of 16
  calls; NTRA 08-28 stamped 336.62 at 09:44, actual close 326.26; mean
  |drift| 0.16 ATR, worst 0.99 on NTRA 08-28) - it feeds the executor's sizing, the day-one trail
  seed and the replay comparison, so "entered at the fire-day close" is
  not what the shadow did on those twelve; (b) the tracker caps auto-call CREATION at `max_open_calls` (default
  10, tunable via /tuning; `calls/manager.py`), but the R2-A shadow engine
  grades every call independently with no portfolio constraint
  (`calls/shadow.py` has no cap) and holds them longer (90-day time stop vs
  the primary book's 45), so its open count can and does exceed 10 (12 on
  2026-09-03). The shadow is per-call grading, not a book; a replay
  comparison must apply the cap post-hoc.

---

_Add new hypotheses at the bottom of the backlog. When one changes status,
edit its entry — this file is the audit trail of what the research suggested
and whether the market agreed._

- **Allocation study, 0/100 sleeve (2026-09-30, counter-agent verified):**
  Casey asked whether to drop the SPY core and run the R2-A sleeve alone on
  a $100k line, since the other account (a factor/gold/managed-futures
  barbell, ~$824k) already carries the beta. Study: five lenses, 15 claims
  refuted by three skeptics each (7 survived, 8 corrected), synthesis.
  Verdict: the household framing holds (at 0/100 the sleeve is 10.8% of the
  total and 22.9% of equity-like, inside H13's 10-50% band numerically,
  with ~$41k in biotech names on an average day because the sleeve is 59%
  cash), BUT H13's band and the corr 0.27 / beta 0.34 were measured vs SPY
  only - R2-A's correlation to the barbell's holdings is measured nowhere
  in this repo; and $100k of sleeve is a 6.7x scale-up of the risk unit
  ($150 -> $1,000 per call) on an engine with no closed live calls, whose
  standalone replay is worse than SPY on every headline stat (Sharpe 0.73
  vs 0.89, maxDD 35.6% vs 33.7%) and whose deepest episode was a 28-month
  grind from the Jan-2021 peak into May 2023 (the 2020-22 sub-period's
  26.8% is boundary-truncated; >= 30.8% on the display curve). Recommended:
  flip the EXISTING $50k book to 0/100 only after the live record since
  09-04 shows clean fills, then let the +$50k in through pre-registered
  live gates (Wilson-90 hit-rate bands, avg R, sleeve DD < 25%, 28-day
  cooldowns); a deposit path (POST /blend/deposit) must exist first -
  BLEND_BOOK_USD is read once at seed and re-seeding on top of held
  positions is the double-deployment the bootstrap guard blocks. The
  sleeve weight is a tracker literal (routers/blend.py:292) read by the
  executor every poll; no executor code is needed for the weight flip.
  P1 inputs still owed: the live record (tracker /calls, /shadow/track-
  record; executor /blend/feed), Casey's drawdown budget on total NLV,
  whether the $100k is new money, and rho(R2-A, barbell) measured on the
  Render host where bars are cached. Standing: no money moves on this
  study; it is an allocation memo, not an engine change.
  KILL CRITERIA for the live book (2026-10-05, 38 days after go-live):
  ibkr-executor/ledger.csv — book-level REVIEW lines at 25% and 35%
  drawdown (the 35% is a SPY-regime event, P = 12.4% per decade under the
  replay) and at 30 months under water; a SLEEVE model-risk KILL at 45%
  transfer-adjusted sleeve drawdown, written but NOT ARMED until the
  executor can measure it; a process kill on an unreconciled position row.
  Basis = the committed executor-fidelity replay (book 28.3% realized,
  p50 26.3% / p95 40.1%; sleeve 29.4%, p50 33.4% / p95 52.2%).

### H14 — The ratchet-up-only trail, not execution, is the executor-vs-paper gap
- **Hypothesis:** the live stop rule (trail never lowered after an ATR
  expansion — the tracker's shadow grader AND the executor's guard) costs
  the R2-A book most of the 5.5 pp/yr gap the executor-fidelity replay
  measured against the paper engine, whose trail is recomputed from the
  peak and the prior-bar ATR every day and FALLS when ATR expands.
- **Evidence (round 9 exit-rule ablation, pre-registered, two counter-agent
  rounds, 2026-10-04):** flipping only the ratchet explains 1.02 of the gap
  forward and 0.76 backward (3/3 sub-periods both ways); paired Sharpe
  interval of record (10,000 draws) forward [−0.397, −0.019], backward
  [−0.009, +0.357] — the backward side spans zero by 0.009; removing the
  ratchet from the executor adds 2.8 pp of max DD (> the 2 pp bar).
  **Null under the contract: no proposal.** Mechanism: the ratchet pins the
  stop at the pre-expansion distance exactly as a catalyst approaches and
  the stock starts swinging; it trims the right tail, not the left (gap
  fills land wherever the stop sits), and earlier exits churn cap slots
  (658 vs 600 trades). Docs: BACKTEST_EXECUTOR_MIRROR.md (round 9),
  VARIANTS_PREREGISTRATION_R9_EXIT_ABLATION.md.
- **Implement:** observe-only. Every live auto-call is now ALSO graded under
  the identical trailing engine with the ratchet removed
  (`ShadowGrade.engine = trailing_3atr_noratchet`); the paired record is
  `h14_ratchet` on `GET /shadow/track-record`. Nothing reads those rows for
  a level (the executor intents filter on `trailing_3atr`); the live stop
  rule is unchanged, and so is its data-bug guard.
- **What the live record tests (pre-registered 2026-10-04):** the EXIT
  MECHANISM on the same calls, i.e. round 9's BACKWARD arm (executor minus
  the ratchet: share 0.76, Sharpe CI [−0.009, +0.357]) — not the 5.5 pp CAGR
  gap, whose slot-churn channel and counterfactual trade set are invisible
  to a per-call comparison. A positive paired ΔR is NECESSARY, not
  sufficient, for any rule change. The shadow engine reproduces only the
  campaign's ratchet convention; entry, entry-bar stop and time-stop anchor
  stay the shadow book's (shared by both engines, so they do not bias the
  pair).
- **Statistic and reading rule:** matured, integrity-checked pairs only
  (`h14_ratchet` on `GET /shadow/track-record`: call_date + 97 days < as-of,
  ratchet grade reproduced from current bars). Primary statistic: mean
  paired ΔR on DIVERGENT pairs with a one-sided bootstrap interval, plus
  the sign count (no-ratchet better vs ratchet better). The record says
  NOTHING below ~30 divergent pairs (≈300 matured pairs at the replay's
  ≳10% exit-divergence rate; at 100 matured pairs it is a mechanism check,
  not a test). An early read is biased AGAINST the no-ratchet rule with a
  definite sign; never read `paired_delta_r` from an immature cohort.
- **Fire rate (host DB, 2026-10-05):** 27 auto-calls since the book went
  live — Jul 9, Aug 6, Sep 12 — about 9 a month. Horizon at that rate:
  ~100 matured pairs (a mechanism check) by about Sep 2027, ~300 matured
  pairs (the first real test, ~30 divergent) by about mid-2029. The 27
  existing calls mature between Oct 2026 and Jan 2027 and give the first
  look at whether live divergent pairs resemble the replay's (same-day lower
  fill vs a later, higher exit). A faster fire rate shortens this; nothing
  else does.
- **Prediction:** on matured divergent pairs the no-ratchet grade shows a
  higher mean R and wins the sign count; the live paired record, not the
  replay, decides whether the rule is ever changed (a change would land in
  BOTH the tracker's shadow grader and the executor, whose ratchet guard is
  also a data-bug safety).
- **Status:** observing (second shadow engine live as of 2026-10-04).
