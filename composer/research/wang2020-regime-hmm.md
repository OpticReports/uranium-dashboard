# Wang, Lin & Mikhelson (2020) — Regime-Switching Factor Investing with HMMs

**Filed:** 2026-07-20 · **PDF:** `wang2020-regime-hmm.pdf` · *J. Risk and
Financial Management* 13(12):311.

## What it does

Gaussian HMM (hmmlearn), 3 hidden states, trained on S&P 500 **daily return +
10d rolling volatility**, re-fit daily on a ~2707-day sliding window. States
map to: steady bull (high ret / low vol), sideways "kangaroo" (flat / moderate
vol), bear (negative ret / extreme vol, ~13% of days). Detected state switches
which factor model trades (value factor in bull; Fama-French variants in
bear). OOS Sept-2017 → Apr-2020: beats each individual factor model on
Sharpe/IR/Treynor.

## Evidence quality (our read)

Modest. One 2.5-year OOS window that ENDS at the COVID crash — the exact
event regime-switching flatters. No 2022-style grind in OOS (HMMs keyed on
equity vol/return handled 2022 poorly in most replications because the bear
was low-kurtosis and bonds fell too). Their factor models mostly lag the S&P;
the win comes almost entirely from *going defensive in the high-vol state* —
functionally what a simple trend/vol filter does with far fewer parameters.
The paper's own Treynor-Mazuy timing coefficient is statistically
insignificant (they say so).

## Applicability to our symphonies

1. **Direct in-symphony HMM: impossible.** Composer logic is if/else on
   indicator comparisons — no state estimation. Any adoption is either a
   proxy (thresholds on realized vol + trend, which our symphonies already
   are, coarsely) or an off-platform overlay.
2. **The genuinely novel bit for us is the explicit THIRD state.** Our
   engines are all two-state machines (trend on/off, momentum long/short).
   The documented shared weakness of HG and the KMLM switcher is exactly the
   paper's "kangaroo" regime — trendless chop, where dip-buying knife-catches
   and L/S switching whipsaws. A chop *detector* that parks in
   BIL/PULS is the transferable idea.
3. **Where it fits our OOS discipline:** every SIGNAL overlay we have tested
   on these symphonies died out-of-sample (results.md addenda); only
   ALLOCATION-level changes survived. An HMM used *inside* a symphony proxy
   is a signal overlay (high prior of OOS failure). An HMM used to tilt
   allocation BETWEEN the three engines (via the guarded transfer CLI, at
   most monthly, within POLICY.md bands) is an allocation move — the class
   that has historically survived.

## Backtest plan (if/when commissioned)

- **B1 — validate the paper on OUR window:** re-fit their exact spec
  (3-state Gaussian HMM, ret+10d vol, sliding window) on SPY through 2026;
  walk-forward monthly. Does the bear state flag 2022? 2024-08? 2025?
  Or only 2020-style vol crashes? Fail here → stop.
- **B2 — chop-state proxy in-symphony (expected to fail, worth one panel):**
  HG copy with a top-level gate: realized-vol middle band + flat 50/100d
  trend → hold PULS instead of the dip-buy branch. Standard IS/OOS split via
  sweep.py. Kill unless OOS Sharpe improves with DD no worse.
- **B3 — allocation tilt between engines (the one with a real chance):**
  map HMM states → weights across HG / KMLM-switcher / sleeve (e.g. bull
  60/30/10, kangaroo 40/30/30→PULS, bear 25/45/30), rebalanced monthly max,
  backtested against the static allocation using the engines' own backtest
  curves. Compare OOS CAGR/Sharpe/maxDD + turnover cost at our measured
  slippage. Kill unless it beats static allocation net of costs.
- **Benchmark guard for all three:** a dumb 2-state trend/vol filter
  (SPY < 200d SMA or 21d vol > x) must be run alongside — if the HMM can't
  beat the dumb filter OOS, the extra machinery is not earning its
  complexity (the literature says it usually doesn't).

## Verdict

Keep the *third-state* idea and the allocation-tilt framing; distrust the
headline OOS result. Nothing here justifies touching live symphonies without
B1→B3 passing our standard walk-forward gates.
