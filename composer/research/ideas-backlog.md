# Research ideas backlog — parked for future infrastructure

Owner directive 2026-07-23: keep the good ideas from reviewed papers on
hand; revisit when the owner builds an IBKR (or similar) execution stack
capable of higher-frequency / cross-sectional trading. Nothing here is
actionable in Composer today. Each idea lists what it needs before any
capital discussion.

## From Singha 2025 (drift regimes — paper REJECTED, ideas salvaged)

The paper's empirics are survivorship artifacts (see
singha2025-drift-regimes.md), but three concepts are independently sound
and worth a clean test on real infrastructure:

1. ~~**Stock-level (not market-level) regime gating.**~~ **CLOSED
   2026-08-27, addendum 32 — TESTED AND FAILED.** Built and measured on our
   own instruments: the regime label predicts forward returns with the
   WRONG sign (-1.27% mean spread, 0/13 tickers significant); the paper's
   regime-conditions-reversal interaction also inverts (corr IN -0.007 vs
   OUT +0.036); applied to HG's legs it cuts TREND Sharpe 0.89->0.22 and
   DIP-BUY 0.58->0.29. Decisive: against random gates at matched
   participation the real gate lands at the 10th percentile — worse than
   random. The inverted steelman also fails its null. Mechanism: our
   engines earn from mean reversion after stress, so a drift filter buys
   what has already run. Do not revisit without new evidence.
2. **Binary on/off signal activation rather than continuous weighting.**
   Turning a weak unconditional signal fully OFF outside its regime beats
   scaling it down, IF the conditional edge is real. Cheap to test.
3. **Mechanical kill-switch layer** (absolute-DD + rolling-window-loss +
   vol-spike + correlation-break, no manual re-entry). We have pieces of
   this in monitor.py alerts; a hard systematic version belongs in any
   future self-executing IBKR stack.

Validation bar before ANY of these trade real money (the standing rule):
- Survivorship-clean universe (point-in-time index membership, delistings
  included) — the exact failure that sank the source paper.
- Realistic costs: ≥5bp all-in per side for liquid large caps, spread +
  impact modeled; reversal-flavored signals tested against next-day-open
  fills, never close-to-close (bid-ask bounce).
- Full-cycle OOS including 2008, 2018, 2022 — not cherry bull windows.
- Sanity ceiling: any result with Sharpe > ~3 is presumed broken until the
  pipeline is proven clean.

## From Wang 2020 (HMM regimes — adopted for the canary, benched for equities)

- Gaussian-HMM equity regime labels had no forward-return edge for our
  symphonies (B1 FAIL), but the descriptive labeling worked on Treasury
  features (B1-T PASS → canary stat-regime strip). On an IBKR stack with
  intraday data, re-test whether HMM states on higher-frequency features
  (realized vol, microstructure) have forward edge where daily bars had
  none.

## From the execution study (addendum 14, 2026-07-29)

- Composer-vs-IBKR execution gap measured at -$1.3k..+$15k/yr on $250k —
  assumption-bound, not decision-grade. Revisit the migration case when:
  (a) divergence.py shows live Composer slippage persistently >5bps/side,
  (b) the book approaches ~$1M+ (gap scales with AUM), or (c) strategies
  are redesigned for materially lower turnover. The intraday-guard
  "responsiveness" benefit tested at ~zero on daily data — retest with real
  intraday data if the IBKR stack gets built.

## Capacity at $1M+ (owner plans ~12mo scale-up; measured 2026-07-29)

p95 daily one-way trade at a $1M book vs 6-month avg daily $ volume:
ZVOL 32.6% of ADV (!), VBF 31.4% (!), VXZ 12.8%, VIXM 5.9%, ANGL 1.2%.
Composer batches MARKET orders into a 15-minute window and cannot work
orders — 30% of screen ADV in 15 minutes is 50-150bps impact territory on
those names, not the engine's 5bps (ETF create/redeem softens this — true
capacity is the underlying's depth — but batch market orders don't access
it well). ZVOL is already ~8% of ADV at the current $250k book: the
harvester's live divergence is the canary; watch its monthly numbers.
Scale path BEFORE any IBKR migration: swap thin tickers for deep
equivalents inside Composer (VBF->LQD/VCIT, VIXM/VXZ->VIXY-based mid-term
structures, ZVOL->deeper short-vol implementation) — same exposures,
penny-wide instruments; removes most of the capacity problem natively.
Migration gate at ~$500-750k: build the IBKR stack only if measured live
slippage trends >5bps/side or the ticker swaps prove unavailable.

## TSMOM shelf candidate (addendum 20, 2026-08-01 — CLOSED with reopen conditions)

Literature-faithful multi-asset trend engine (Man/AHL corpus), QA-validated
spec: sleeves SPY/TLT/GLD/DBC; signal = majority vote of 63/126/252d
cumulative returns; inverse-vol (63d) sleeve weights; long asset on
positive vote, else SH (for SPY) / TBF (for TLT) short legs, BIL for
GLD/DBC (no viable inverse). 19y frictionless: CAGR ~+6.5%, maxDD ~13%,
2008 +26.5%, 2022 +3.7%, corr to live blend 0.10. Composer-expressible
(nested ifs + wt-inverse-vol). DO NOT BUILD while: KMLM holds its ~29%
trend slot AND live-engine Sharpes stay >>1. REOPEN if KMLM is removed,
or engine Sharpes decay toward ~1 during a developing multi-quarter
inflation/trend regime. Prototype tree + QA data: session scratchpad
gates/tsmom_tree.json, agents' variant tables in session transcript.

## SETTLED QUESTIONS — do not re-study without new evidence (2026-08-05)

External de-risking overlays on the current engines are REJECTED as a
class, measured SIX independent ways: trend gates (add. 19b), strategy
vol-targeting (20b), DD-exit rules (21), VRP sizing (25), band-edge
variants (25), GARCH vol-regime gating + sizing on the harvester (31 --
including sizing UP, which fails the same way: every 'size up when calm'
rule concentrates short vol exactly where vol gaps). Mechanism, replicated: every engine is internally
convexity-aware and earns disproportionately in its own high-vol/stress
state; overlays de-risk exactly those states. Any new overlay proposal
must first show the ENGINES' character changed (e.g., live divergence
shows an engine losing its stress-state earnings) — otherwise cite this
entry and decline. Allocation-layer detection (two-tier alerts, book DD
alarm, cap, earn-back) remains the sanctioned risk machinery.

## Trigger to revisit

Owner starts building the IBKR execution project (or equivalent
higher-frequency capable stack). At that point: pick idea #1 (per-
instrument regime gating) first — it is the cheapest to falsify with a
survivorship-clean universe and honest costs.

## From the crash simulations (addendum 39, 2026-10-07)

Measured, not adopted — each is an owner decision; the house rule on
overlays stands (nine failures), so only mechanical changes with a
deterministic rationale are listed.

1. **C1 — KMLM short-vol termination** (SVIX leg -> PULS when VIX > VIX3M
   at the decision close). Real era: no measurable effect (+1%, 48 gate
   days, inside the placebo band). COVID replay: better under every
   regime-flag stand-in (crash-window maxDD -10 to -22pp). Deterministic
   mechanism, not a signal. KILLED for HARV (its backwardation entries are
   the edge: real era -5%, COVID 12m -9%, placebo p03).
2. **C3 — HARV cash leg PULS -> BIL.** Costs ~0.5%/yr; PULS fell ~5% in
   March 2020, BIL did not (COVID crash maxDD 11.5% -> 6.0%). BOXX would do
   the same job (did not exist in 2020). KMLM's 12% PULS leg: negligible.
3. **C2 — HG bear gate (trend baskets -> BIL when SPY < 200d MA).** The
   measured price of HG's long-bear risk: ~-10%/yr in 2015-23, worse in
   2022 and in V-recoveries; +1.1x/+1.2x and DD 71% -> 60%/29% in the
   2000/2008 reconstructions. Not recommended as-is. Reopen only if the
   owner wants to pay bull-market return for grinding-bear protection.
4. **HG long-bear calibration.** Reconstructed HG draws down ~70% in both
   2000-02 and 2007-09 (36% in its real record; 40% anomaly alarm). The
   alarm will fire early and often in a multi-year bear; that is
   informational, not a trade. KMLM's crash behaviour is unresolvable
   (regime flag not reconstructible; results span -58% to +51% in the
   COVID window across six stand-ins) — the engine's edge is concentrated
   on exact flag timing, a fragility to keep in mind at any weight above
   the current 29%.

## From the gate study (addendum 40, 2026-10-08)

5. **HG 200d-family gate — the simplest member only.** In the 1990-2026
   proxy every 200d-family gate on HG's trend baskets raises Sharpe
   (1.00 -> 1.11-1.19), Sortino and Calmar and cuts max DD 72% -> 60-65%,
   beating 200 re-dated placebos and its own inverse; the return edge is
   five bear episodes and the cost is every V-recovery (2015-26: every
   gate costs 5-28pp/yr, nothing beats as-built). The members (binary,
   vote, hysteresis, G6) cannot be told apart (block-bootstrap P 0.45-0.80;
   best-of-7 edge = +0.03 Sharpe = selection effect). If the owner wants
   the insurance, build the binary 200d gate (or G6) as a draft and run
   the standard gate tests; do not tune the shape.
6. **CLOSED again: macro conditioning of the gate** (CAPE level, CAPE
   high-for-long, yield-curve inversion, credit-spread percentile, oil
   +50% yoy, and their count). None beats a level-matched placebo in both
   panels; CAPE and credit lose to their mirror inverses; the curve loses
   on all three metrics in the long panel; oil's four episodes are not
   evidence. Literature agrees (curve: 24/24 loser as an equity exit,
   Fama-French 2019; CAPE: Sharpe = buy-and-hold, AIM 2017). Reopen only
   with a refereed result showing a macro conditioner improving a trend
   rule out of sample — the one such hint (Neely et al. 2014) puts macro
   on the RE-ENTRY side.
7. **Reopen condition for a graded gate:** the state-conditional slow/fast
   blend of Goulding-Harvey-Mazzoleni (FAJ 2024; Sharpe 0.64 -> 0.80 after
   costs, weights shrunk to 0.5). HG already carries both legs (SPY vs
   200d = slow; TQQQ 10>20d = fast). Not built: it is a fitted blend with
   <=5 bear episodes to fit on; it would need the full placebo/inverse
   treatment and a pre-registered spec before any live test.

