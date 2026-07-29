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

1. **Stock-level (not market-level) regime gating.** Defining the regime
   per-instrument (e.g., fraction of up-days over a trailing window) lets
   different names be in different regimes simultaneously — a bigger
   opportunity set than market-wide VIX/trend gates. Our current gates
   (HYG guard, KMLM branches) are market-level; per-instrument gating is
   the genuinely new-to-us idea.
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

## Trigger to revisit

Owner starts building the IBKR execution project (or equivalent
higher-frequency capable stack). At that point: pick idea #1 (per-
instrument regime gating) first — it is the cheapest to falsify with a
survivorship-clean universe and honest costs.
