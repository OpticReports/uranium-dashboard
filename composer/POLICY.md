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
- On PASS (ALL criteria, sustained 2 consecutive monthly checks, AND at
  least one live hostile-regime month in the record — hardened 2026-08-01,
  results.md addendum 21):
  - live~model daily correlation >= 0.90;
  - annualized gap >= -15%/yr, measured PAIRED (live vs the concurrent
    same-window model run, as divergence.py computes it — an unpaired
    comparison false-fails ~47% of genuine years);
  - live beta to model in [0.9, 1.1] AND live/model vol ratio < 1.15
    (fast detectors for a live tail fatter than modeled);
  - live max drawdown within model expectation (backstop: < 39%, the 55y
    conservative p90; method sensitivity ±5pp documented in add. 21b).
  Then REPORT to the owner that the 19/39 upgrade is statistically
  earned — do NOT execute; the upshift is an owner decision. A criteria
  miss only delays the report (~20% false-block chance over 2y of
  monthly checks — acceptable; it never forces a downshift).
- On FAIL: no action needed (the book already holds the defensive weight);
  note it in the daily summary.
- No auto-trades under this operation in either direction.

## Pre-authorized operation 5 — engine concentration cap (armed 2026-07-31)

Owner-approved (chat, addendum 18). Purpose: delete the unmanaged-drift
tail where one engine's hot streak concentrates the book (bootstrapped
conservative DD p95 68.6% unmanaged vs 37.5% capped; expected CAGR
unchanged vs disciplined manual resets).

- Trigger: at the daily post-close check, ANY symphony's value exceeds
  **40% of total Composer book value** (symphonies + unallocated cash).
- Action: mechanically rebalance ALL FOUR symphonies back to target
  weights **HG 29 / KMLM 29 / SLEEVE 27 / HARV 15** via the guarded CLI:
  withdraw from overweights first; invest proceeds into underweights when
  the cash settles (typically next evening; complete pending legs at the
  next daily check). Recompute all amounts from live values at execution.
- Error guards (unchanged): 25% single-move cap per move (stage larger
  resets across windows), >50% one-day-change data-anomaly no-trade rule.
- Every firing: CHANGELOG entry with deploy IDs, push notification, and
  report to the owner. Expected frequency ~once every 1-2 years.
- The target weights above are the same allocation-B targets; if the
  owner changes the book's target allocation, update this block in the
  same decision.
- Drift-protocol note (2026-08-01, addendum 21): if a future owner
  decision raises any engine's TARGET near the cap (e.g., KMLM to 39%
  via the earn-back), a subsequent drift breach of 40% still triggers
  THIS operation's full reset to the then-current targets — no
  ambiguity, no special case.
- Headroom codicil (2026-08-06, addendum 29 — measured): the cap must
  keep >=10pp of headroom above the largest engine target (a 40% cap
  over a 38% target fired 5.4x/yr in simulation — thrash). Any decision
  raising a target above 30% must reset the cap to target+10pp in the
  same decision. Verification status: independently recomputed and
  CONFIRMED (P(cap-40 beats monthly)=99-100% per-path, conservative
  lens; daily-resolution cross-check consistent; expect ~1.5 fires/yr).

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
