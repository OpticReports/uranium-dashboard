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
- PENDING (awaiting owner confirmation that the deposit landed): owner is
  selling TAIL (~$17k) + $30k BOXX at IBKR and wiring ~$47k to Composer.
  On arrival: top the sleeve up to the ~$53k family target (≈ +$31k), and
  invest the remainder (≈ $16k) into the most underweight engine
  (targets: HG 55% / P5 35% of the Composer account ex-sleeve overweight).
  Deploying the deposit itself requires the owner's "it landed" message —
  it is NOT auto-executed on cash detection.
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

## Standing exclusions

Never auto-executed under any circumstances: changes to symphony logic,
investing in new/unapproved symphonies, liquidations, go-to-cash, direct
single-asset trades, bank transfers, or any trade outside the two operations
above. During a suspected regime break (e.g., sleeve above 20% of book in a
crash), the band still executes its mechanical trim, but the owner is
notified prominently that discretionary harvesting beyond the band is their
call (results.md addendum 7).
