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

## Pre-authorized operation 3 — KMLM hostile-regime tripwire

Owner-approved 2026-07-20 (chat; analysis in results.md addendum 13). The
19/39/27/15 allocation's single fragile assumption is the KMLM switcher's
behavior in hostile regimes — untested in its 814-td record. This operation
converts that uncertainty into a monitored contingency.

- Check date: first daily check on or after **2026-08-07** (~30 live days for
  the current allocation), then MONTHLY through at least 2027-01.
- Measurement: `divergence.py YPTSJFJwD2ZKfAeYJUbW` (KMLM switcher,
  deposit-adjusted live vs same-window backtest).
- FAIL criteria (either):
  - live~backtest daily-return correlation **< 0.90**, OR
  - annualized live-vs-model gap worse than **−15%/yr**.
- Action on FAIL: shift **10 points of total book** from KMLM to HG
  (target allocation becomes 29/29/27/15). Execute via guarded CLI:
  withdraw from KMLM [YPTSJFJwD2ZKfAeYJUbW], invest proceeds into HG
  [mbkiXcuNDjueXpiox5Av]; recompute dollar amounts from live values;
  25% single-move guard applies; two trading windows as needed. Write a
  CHANGELOG entry and notify the owner prominently (this is a tripwire
  FIRING, not routine rebalancing). This operation authorizes ONLY this
  specific KMLM->HG shift, once; a second shift requires fresh owner
  approval.
- Action on PASS: keep 19/39/27/15, report the numbers in the daily
  summary, re-check monthly.
- Sunset: if passed every month through 2027-01, retire this operation at
  the Jan-2027 review alongside Operation 2.

## Standing analysis cadence (not a capital operation)

- QUARTERLY (first daily check of Oct/Jan/Apr/Jul), and mandatorily at the
  Jan-2027 review: re-run `composer/research/regime_boot.py` (55y
  regime-bootstrap, addendum 13) with fresh live data. Report the allocation
  ranking and the AS-MEASURED vs CONSERVATIVE-KMLM gap vs the prior run —
  convergence as live hostile-regime months accumulate is the finding.
  Any reallocation it suggests requires owner approval (except where an
  existing pre-authorized operation already covers the move).

## Standing exclusions

Never auto-executed under any circumstances: changes to symphony logic,
investing in new/unapproved symphonies, liquidations, go-to-cash, direct
single-asset trades, bank transfers, or any trade outside the two operations
above. During a suspected regime break (e.g., sleeve above 20% of book in a
crash), the band still executes its mechanical trim, but the owner is
notified prominently that discretionary harvesting beyond the band is their
call (results.md addendum 7).


## PENDING REALLOCATION TAIL — harvester top-up (last leg)

Phase 2 executed 2026-07-21: KMLM +$30,000 [6327f1d5], harvester (VIX
Harvester + HYG Credit Guard, ORQNCfZnA18wmsMWVhf8) +$34,900 [4ab9f0b2],
residual HG trim $2,570 [aea856ef] — all fill in the 2026-07-22 window.
LAST LEG: when the HG trim's cash settles (~$2,600 unallocated, expected
2026-07-22 evening), invest ALL remaining unallocated cash into the
harvester [ORQNCfZnA18wmsMWVhf8] via guarded CLI, then DELETE this block
and log in CHANGELOG. If not settled by 2026-07-24, alert the owner.

## Pre-authorized operation 3 — KMLM hostile-regime tripwire

Owner-approved 2026-07-20 (chat; analysis in results.md addendum 13). The
19/39/27/15 allocation's single fragile assumption is the KMLM switcher's
behavior in hostile regimes — untested in its 814-td record. This operation
converts that uncertainty into a monitored contingency.

- Check date: first daily check on or after **2026-08-07** (~30 live days for
  the current allocation), then MONTHLY through at least 2027-01.
- Measurement: `divergence.py YPTSJFJwD2ZKfAeYJUbW` (KMLM switcher,
  deposit-adjusted live vs same-window backtest).
- FAIL criteria (either):
  - live~backtest daily-return correlation **< 0.90**, OR
  - annualized live-vs-model gap worse than **−15%/yr**.
- Action on FAIL: shift **10 points of total book** from KMLM to HG
  (target allocation becomes 29/29/27/15). Execute via guarded CLI:
  withdraw from KMLM [YPTSJFJwD2ZKfAeYJUbW], invest proceeds into HG
  [mbkiXcuNDjueXpiox5Av]; recompute dollar amounts from live values;
  25% single-move guard applies; two trading windows as needed. Write a
  CHANGELOG entry and notify the owner prominently (this is a tripwire
  FIRING, not routine rebalancing). This operation authorizes ONLY this
  specific KMLM->HG shift, once; a second shift requires fresh owner
  approval.
- Action on PASS: keep 19/39/27/15, report the numbers in the daily
  summary, re-check monthly.
- Sunset: if passed every month through 2027-01, retire this operation at
  the Jan-2027 review alongside Operation 2.

## Standing analysis cadence (not a capital operation)

- QUARTERLY (first daily check of Oct/Jan/Apr/Jul), and mandatorily at the
  Jan-2027 review: re-run `composer/research/regime_boot.py` (55y
  regime-bootstrap, addendum 13) with fresh live data. Report the allocation
  ranking and the AS-MEASURED vs CONSERVATIVE-KMLM gap vs the prior run —
  convergence as live hostile-regime months accumulate is the finding.
  Any reallocation it suggests requires owner approval (except where an
  existing pre-authorized operation already covers the move).

## Standing exclusions

Never auto-executed under any circumstances: changes to symphony logic,
investing in new/unapproved symphonies, liquidations, go-to-cash, direct
single-asset trades, bank transfers, or any trade outside the two operations
above. During a suspected regime break (e.g., sleeve above 20% of book in a
crash), the band still executes its mechanical trim, but the owner is
notified prominently that discretionary harvesting beyond the band is their
call (results.md addendum 7).


## PENDING REALLOCATION — owner-directed 2026-07-20 (phase 2 of 2)

Owner approved target allocation **HG 19% / KMLM 39% / SLEEVE 27% / HARV 15%**
(chat, 2026-07-20; analysis in results.md addendum 12). Phase 1 executed
2026-07-20: withdraw $64,900 from HG [deploy c71227ac] (capped at the 25%
single-move guard; full HG trim need was $66,927).

Phase 2 — EXECUTE when unallocated cash ≥ $60,000 (proceeds settled):
1. Withdraw the RESIDUAL from HG to reach 19% of book (~$2,000; recompute
   from live values at execution).
2. Invest into KMLM switcher [YPTSJFJwD2ZKfAeYJUbW] up to 39% of book
   (~$28,600; recompute).
3. Invest remaining cash into the GUARDED harvester
   "CANDIDATE: VIX harvester + HYG credit guard (loop)"
   [ORQNCfZnA18wmsMWVhf8] to reach 15% of book (~$39,000; recompute) — this
   deploys it live; it is owner-approved (this block overrides the
   new-symphony standing exclusion for THIS symphony id only).
4. SLEEVE untouched (in band). All moves via guarded CLI; 25% single-move
   guard applies per move. Delete this block + write CHANGELOG entry when
   complete. If cash has not settled by 2026-07-23, alert the owner.

Renaming note: after deployment, rename the harvester to drop the
"CANDIDATE" prefix (e.g. "VIX Harvester + HYG guard 15%").
