# Standing Capital Policy — pre-authorized operations

Granted by the account owner in-session on **2026-07-06** ("For 2 and 3 can
you have those ready to execute without asking me for approvals"). These two
operations — and only these — may be executed by the agent **without
per-trade approval**. Everything else stays governed by README §2 (explicit
per-operation human request).

Every auto-execution must be reported to the owner immediately after, logged
in `CHANGELOG.md` with deploy IDs, and pushed.

## Pre-authorized operation 1 — sleeve monetization band

- Instrument: Crash Convexity Sleeve `nNdBk7hc5NiBzeRvbI5T`.
- Sizing denominator (updated 2026-07-07, owner decision): the sleeve is
  sized against the **family book's crash-exposed assets** — Composer
  engines + owner-reported IBKR equities — not the Composer account alone.
  - Current figures: IBKR equities ≈ $346k (owner-reported 2026-07-07;
    refresh whenever the owner reports new numbers) + Composer engines.
  - Target: **10% of crash-exposed assets** (≈ $53k at current figures).
    Band: **7% – 15%** of the same measure.
  - Operationally, monitor.py's band check runs on Composer-visible values;
    the dollar target is recorded here and updated on owner reports.
- 2026-07-16: TAIL proceeds ($17,011) arrived and were deployed to the
  SLEEVE on the owner's direction ("use this additional capital as a
  correlation hedge against my broader portfolio") — sleeve now ~11.8% of
  crash-exposed assets: above the 10% target, inside the 7–15% band, so no
  auto-trim fires. The Jan-2027 review still governs any further scale-up.
- Trigger: at the daily post-close check, sleeve outside the band (7–15% of
  crash-exposed assets; dollar equivalents recorded above).
- Action: rebalance the sleeve back to the 10% target:
  - Over the band → withdraw the excess from the sleeve; invest proceeds into
    whichever engine (HG `mbkiXcuNDjueXpiox5Av` or P5 `YPTSJFJwD2ZKfAeYJUbW`)
    is furthest **below** its target (HG 55% / P5 35%).
  - Under the band → withdraw the shortfall from whichever engine is furthest
    **above** its target; invest into the sleeve.
  - Two-leg timing: the withdraw executes at the next trading window; the
    invest is placed as soon as the proceeds appear as buying power
    (typically the same evening). Pending legs are completed at the next
    daily check.
- **Error guard (not a judgment gate):** if a single rebalance would move
  more than **25% of total portfolio value**, or the API values imply a
  >50% one-day change in any position, assume data problems — do NOT trade;
  alert the owner instead.

## Pre-authorized operation 2 — sleeve scale-up to 15%

- Review date: first daily check on or after **2027-01-06** (~2 trading
  quarters after the sleeve's first fill on 2026-07-07), and monthly
  thereafter until it passes or the owner cancels.
- Criterion (measured by `divergence.py` on the sleeve):
  - ≥120 trading days of live history, AND
  - live~backtest daily-return correlation ≥ **0.90**, AND
  - annualized live-vs-model gap ≥ **−10%/yr** (live may lag the model by up
    to 10 points annualized; worse than that = fail).
- Action on pass: raise sleeve target to **15%** (band 11% – 20%), execute
  the top-up per Operation 1 mechanics, and update this file + monitor
  defaults in the same commit.
- Action on fail: keep 10%, report the numbers, re-check monthly. A second
  consecutive fail with correlation < 0.75 = flag to the owner that the
  sleeve is not tracking and should be re-evaluated, not scaled.
- Scale-up beyond 15% (to 20%) requires a fresh owner decision — not
  pre-authorized.

## Pre-authorized operation 3 — KMLM earn-back monitor (rewritten 2026-07-22)

Owner moved the book to 29/29/27/15 after adversarial QA — the tripwire's
target allocation is now the DEFAULT, so this operation inverts: it now
monitors whether KMLM EARNS BACK the higher 19/39/27/15 weight.

- Check date: first daily check on or after **2026-08-07**, then MONTHLY.
- Measurement: `divergence.py YPTSJFJwD2ZKfAeYJUbW` (live vs backtest) plus
  the quarterly regime-bootstrap convergence read (Standing analysis cadence).
- On PASS (live corr >= 0.90 AND gap >= -15%/yr, sustained 2 consecutive
  monthly checks, AND at least one live hostile-regime month in the record):
  REPORT to the owner that the 19/39 upgrade is statistically earned — do
  NOT execute; the upshift is an owner decision.
- On FAIL: no action needed (the book already holds the defensive weight);
  note it in the daily summary.
- No auto-trades under this operation in either direction.

## Armed operation 4 — VBF->VCIT scale swap (owner-approved plan 2026-07-30)

Scale-prep for the ~12mo path to $1M+ (addenda 15/15b). VBF is the book's
binding liquidity constraint (HG's bond basket; $0.9M ADV; measured
+33bps/side at the current size). The validated fix is a two-node asset
swap VBF->VCIT in HG's tree (daily corr 0.9979 to baseline over 11.1y;
blueprint benched as draft symphony `5CbBgpP9T8KcnCCwBGno`).

- TRIGGER (either): (a) Composer book value >= $750,000 at a daily check,
  or (b) a quarterly slippage run measures VBF fills worse than 50bps/side.
- ACTION on trigger: REPORT to the owner ("VBF swap trigger fired — say
  go") — the tree edit is NOT auto-executed (standing exclusion applies).
  On the owner's go: apply the identical two-node edit to live HG
  `mbkiXcuNDjueXpiox5Av` in place via PUT (no capital switch, no
  liquidation; the draft stays as archive/rollback), CHANGELOG it, and
  verify the next window's rebalance.
- Until then: quarterly slippage runs report VBF's fill trend.

## Standing analysis cadence (not a capital operation)

- QUARTERLY (first daily check of Oct/Jan/Apr/Jul), and mandatorily at the
  Jan-2027 review: re-run `composer/research/regime_boot.py` (55y
  regime-bootstrap, addendum 13) with fresh live data. Report the allocation
  ranking and the AS-MEASURED vs CONSERVATIVE-KMLM gap vs the prior run —
  convergence as live hostile-regime months accumulate is the finding.
  Any reallocation it suggests requires owner approval (except where an
  existing pre-authorized operation already covers the move).
- QUARTERLY (same runs): `composer/scripts/slippage_measure.py` — realized
  fill slippage vs the 5bps engine assumption (addendum 14b; baseline
  2026-07-29: +2.9bps/side on $10.0M). Report the trend, especially the
  thin names (ZVOL/VBF/VXZ/VIXM), against the scale gates in
  research/ideas-backlog.md. Analysis only — no trades.

## Standing exclusions

Never auto-executed under any circumstances: changes to symphony logic,
investing in new/unapproved symphonies, liquidations, go-to-cash, direct
single-asset trades, bank transfers, or any trade outside the two operations
above. During a suspected regime break (e.g., sleeve above 20% of book in a
crash), the band still executes its mechanical trim, but the owner is
notified prominently that discretionary harvesting beyond the band is their
call (results.md addendum 7).
