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

---

## B1 RESULT (run 2026-07-20): FAIL — thread closed

Walk-forward replication (their spec; monthly refit, 2707d window, states
labeled by in-window mean return, decision at month-end posterior; 547
month-ends 1980-09 → 2026-07; script in scratchpad `b1_hmm.py`, states in
`b1_states.json`):

**Detection (mixed, honest):** persistent BEAR flags through 2000-02 and
2008 (from Jan-2008), catches 1987 / 2011 / 2020-03; only 2 false-alarm BEAR
month-ends across nine strong bull years. BUT: **2022 never reads BEAR**
(CHOP all year — the orderly grind their vol-keyed spec cannot see, exactly
as predicted), 1990 missed, 2015-16 and 2018-Q4 only CHOP, Aug-2024 invisible
at month-end granularity, 2025 flagged late.

**The kill shot — no forward return edge at actionable granularity:**
next-month SPY return conditional on month-end state:
BULL +0.75% (n=282) · CHOP +0.95% (n=179) · BEAR +0.87% (n=85).
The states carry ZERO mean-return information one month ahead — BEAR's
next-month mean exceeds BULL's. Only the tails differ (BEAR worst month
-21.8% vs BULL -9.2%): the HMM is a *descriptive tail-risk labeler*, not a
return timer. Parking defensive on CHOP would have SACRIFICED the highest
conditional mean of the three states, killing B2's premise; tilting
allocation on states with no mean edge cannot beat static allocation after
turnover, killing B3's premise. (Caveat: daily-granularity switching might
time 2020-style crashes faster, but daily inter-symphony switching is not
executable in our world — monthly actionability is the relevant test.)

**Standing conclusion:** consistent with every prior experiment — regime
*description* is cheap, regime *prediction* is not, and our tail exposure is
already handled at the allocation level by the sleeve + band policy. The
kangaroo-state insight survives only as the qualitative caution already
documented in the engine summaries (chop is the shared weakness; no
tradeable detector found). Do not reopen without a materially different
method AND a plan that survives the dumb-filter benchmark.
