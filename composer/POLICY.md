# Standing Capital Policy — pre-authorized operations

Granted by the account owner in-session on **2026-07-06** ("For 2 and 3 can
you have those ready to execute without asking me for approvals"). As of
2026-11-18 the only operation that may trade **without per-trade approval**
is **Operation 5** (the engine concentration cap); Operations 1 and 2 are
retired and Operation 3 is report-only. Everything else stays governed by README §2 (explicit
per-operation human request).

Every auto-execution must be reported to the owner immediately after, logged
in `CHANGELOG.md` with deploy IDs, and pushed.

**IBKR mirror.** Every operation below that moves capital between two
symphonies is followed, in the same run, by
`scripts/mirror_transfer.py --from <giver> --to <taker> --composer-amount <the
Composer amount> --composer-from-value <the giving symphony's value before the
move> --composer-from-value-after <its value after the move>`, with the same
from/to as the Composer move. Pass BOTH values: with the second the script
refuses a "before" that is really the value after the move (it would move too
large a fraction). The mirror moves the same FRACTION of its own sleeve, not
the same dollars, and the script's summary line goes into the report. The leg
goes to the LIVE book only: with no live book on the executor there is no
mirror leg - the script exits 1 and the routine reports that line, nothing
else (it does not name a paper book instead, and does not retry). The mirror
applies a queued move at the mirror's next session - today's if the request
is queued before about 15:54 ET on a session day, otherwise the next trading
day's. The script sends a leg once: when a transfer for the same from/to is
already queued on the executor, or the script's own ledger
(`results/mirror/transfer-ledger.jsonl`) says one was sent or may have been
sent that day, it refuses as a duplicate (pass `--again` only when a second
move of the same pair is meant). A line saying UNKNOWN (the request left, the
answer did not say whether it was queued) is NOT resolved by simply running
the command again: read the executor's feed (the book's `pending_requests`
and today's session row) and re-send with `--again` only if the transfer is
in neither. The script writes its intent to that ledger before it sends and
exits 1 whenever the ledger cannot be written, so the ledger must be committed
with the day's snapshot. While operator credits (POST /mirror/credit, e.g. a
scale-up) are queued on the executor for either sleeve, the script refuses
the leg (exit 1, nothing sent): size the move after the session applies them;
re-run after that session. A leg below $1 even once those credits are applied
is below $1 at the mirror's size: nothing is sent, exit 0 (no re-run). An
operation that moves money to or from unallocated cash,
or outside the four mirrored engines (HG, KMLM, SLEEVE, HARV), has no mirror
leg and is reported as such. **One symphony giving to several** (a cap reset,
the HARV exit): run ONE leg per taker, each with `--composer-from-value` = the
giver's value before ANY of the legs and `--composer-from-value-after` = that
value minus THIS leg's amount. The script sizes every leg on the mirror
sleeve's equity as the feed shows it, which queued legs do not reduce, so
"before" values that shrink leg by leg would move too much (2026-11-18 review:
61.7% where 50% was meant). Before sending, the dry-run amounts must sum to
the intended fraction of the giving sleeve's equity.

## Allocation (owner decision 2026-11-18; results.md addendum 56)

- **HARV is closed as a separate engine** (owner, 2026-11-18: "close it out"). Its capital
  moves pro rata into the other three (29 : 29 : 27) in one owner-approved session on both brokers
  (`research/zvol_2026-11/MOVE_PLAN.md`; logged in CHANGELOG.md). A $100 stub on Composer and
  about $6 of cash in the mirror's sleeve stay until the engine-retirement change is reviewed (the
  daily tooling still reads HARV; the plan says why), then go too. The copy of the same rule inside
  the KMLM symphony (its 25% VIX sleeve) is unchanged.
- **Targets: HG 34.1 / KMLM 34.1 / SLEEVE 31.8** (29/85, 29/85, 27/85). HARV has no target: until
  its exit has filled, and for any dust left afterwards, every operation here leaves it alone.
- **The crash sleeve is one engine of the strategy, sized by its target weight** (owner, 2026-11-18:
  "treat it as one engine"). It is no longer sized against holdings outside this book: the IBKR
  equities figure the old band used ($346k, reported 2026-07-07) no longer exists (blend3070 was
  sold on 2026-11-11 and IBKR now runs the same strategy as a mirror).

## Operation 1 — sleeve monetization band: RETIRED 2026-11-18

Not pre-authorized any more; nothing here is executed. The band (7% - 15% of "Composer engines +
IBKR equities", target 10%) trimmed the sleeve after a crash pop and topped it up when it lagged.
With the outside figure gone the measure no longer exists (against the Composer book alone the
sleeve is ~25%, which the old band would read as a breach).

What this takes away, stated plainly:
- **No automatic harvest of a sleeve pop.** The old band trimmed when the sleeve had gained about
  26% against a flat rest of book. Operation 5's cap is the only mechanical reset left and it is far
  away: from a 31.8% target the sleeve passes 44% only if (1 + sleeve return) / (1 + rest-of-book
  return) exceeds 1.69: +69% with the rest flat, +35% with the rest down 20%, +18% with the rest
  down 30%. In 2023-01..2026-10 the sleeve's best run against HG was x1.30 over 5 sessions and x1.55
  over 63, so in practice harvesting a crash pop is now entirely the owner's call (RUNBOOK.md).
- **No automatic top-up** when the sleeve lags (the band's lower edge).
- What the band was measured to add (results.md addendum 7, real book 2023+, band vs drift): Sharpe
  2.56 vs 2.49, max drawdown 14.6% vs 15.8%, CAGR -7.3 points, 7 trades; addendum 25: variants
  within +/-0.4pp of CAGR. "Band on top of the cap" was never measured.
`monitor.py` still records the sleeve's share of the Composer book each day (`sleeve_weight`) and
raises a band line only if `--band-lo` / `--band-hi` are passed.

## Operation 2 — sleeve scale-up to 15%: RETIRED 2026-11-18 (its tracking check stays, report-only)

The scale-up was defined on the retired band's measure (10% -> 15% of "Composer engines + IBKR
equities") and is superseded by the allocation above (SLEEVE target 31.8% of this book). No trade
is authorized under this operation.

- What stays, as a REPORT only: on the first daily check on or after **2027-01-22**, and monthly
  until the owner closes it, run `divergence.py nNdBk7hc5NiBzeRvbI5T --start 2026-08-01`
  (window from 2026-08-01: the sleeve was edited live on 2026-07-31, BIL -> BOXX) and report live
  days, live~backtest daily-return correlation (was required >= 0.90) and the annualized
  live-vs-model gap (was required >= -10%/yr). Two consecutive reads with correlation < 0.75 =
  flag to the owner that the sleeve is not tracking.

## Pre-authorized operation 3 — KMLM earn-back monitor (rewritten 2026-07-22)

Owner moved the book to 29/29/27/15 after adversarial QA — the tripwire's
target allocation is now the DEFAULT, so this operation inverts: it now
monitors whether KMLM EARNS BACK the higher 19/39/27/15 weight.
2026-11-18: with HARV retiring the default is HG 34.1 / KMLM 34.1 / SLEEVE 31.8
("Allocation" above); the earn-back question is unchanged in kind (KMLM +10
points funded from HG) and stays REPORT-ONLY. Any such upshift would put
KMLM's target near 44%, so it would need Operation 5's cap reset in the same
owner decision (headroom codicil).

- Check date: first daily check on or after **2026-08-07**, then MONTHLY.
- Measurement: `divergence.py YPTSJFJwD2ZKfAeYJUbW` (live vs backtest;
  distribution-aware since 2026-10-05 — add. 38) plus
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
  Then REPORT to the owner that the KMLM upgrade (+10 points from HG: 24.1 / 44.1 / 31.8 on the
  2026-11-18 targets; was 19/39) is statistically
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
unchanged vs disciplined manual resets). Those figures are the 40% cap over
four engines at 29/29/27/15. The 44% cap over three engines (2026-11-18) has
not been re-run through that bootstrap; addendum 18's only other point is a
50% cap (DD p95 47.1%, +3.6 points of CAGR), so expect the tail between the
two.

- Trigger: at the daily post-close check, ANY of HG / KMLM / SLEEVE exceeds
  **44% of total Composer book value** (symphonies + unallocated cash).
  (Was 40% over 29/29/27/15 until 2026-11-18. HARV, retiring, is not
  measured against the cap.)
- Action: mechanically rebalance **HG, KMLM and SLEEVE** back to target
  weights **HG 34.1 / KMLM 34.1 / SLEEVE 31.8** (29 : 29 : 27) of the base
  B = the three symphonies' values + this reset's withdrawn cash not yet
  reinvested, via the guarded CLI: withdraw from overweights first; invest
  the proceeds into underweights when the cash settles (typically next
  evening; complete pending legs at the next daily check). Recompute the
  amounts from live values at each step ON THAT BASE (without the withdrawn
  cash in it, a recompute on the invest day would leave the giver overweight
  and under-invest). **HARV is left out of the reset**: nothing is invested
  into it or withdrawn from it. Mirror legs: one per taker ("IBKR mirror"
  above, "One symphony giving to several").
- Error guards (unchanged): 25% single-move cap per move (stage larger
  resets across windows), >50% one-day-change data-anomaly no-trade rule.
- Every firing: CHANGELOG entry with deploy IDs, push notification, and
  report to the owner. Expected frequency: roughly 1.5-2 a year (a
  reviewer's replay of the documented engine returns, 2023-01..2026-10,
  backtest pace, in-sample: 1.45/yr under the old rule, 1.74/yr under this
  one, every firing KMLM-triggered; the sleeve triggers ~1% of years).
- The target weights above are the 2026-11-18 allocation; if the owner
  changes the book's target allocation, update this block in the same
  decision.
- Drift-protocol note (2026-08-01, addendum 21): if a future owner
  decision raises any engine's TARGET near the cap (e.g., KMLM to 39%
  via the earn-back), a subsequent drift breach of the cap still triggers
  THIS operation's full reset to the then-current targets — no
  ambiguity, no special case.
- Headroom codicil (2026-08-06, addendum 29 — measured): the cap must
  keep >=10pp of headroom above the largest engine target (a 40% cap
  over a 38% target fired 5.4x/yr in simulation — thrash). Any decision
  raising a target above 30% must reset the cap to target+10pp in the
  same decision. Applied 2026-11-18: largest target 34.1%, cap **44%**
  (owner-approved; ~10pp of headroom: 44 against 44.1). The codicil's
  measurement and its "CONFIRMED" status below are for the 40% cap over
  four engines; the 44% cap over three has NOT been through the regime
  bootstrap (re-measure at the next quarterly run). Verification status: independently recomputed and
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
- EVENT-DRIVEN (every daily check, speaks rarely): the HG 200-day gate watch
  (`scripts/gate_watch.py`, addendum 46). GATE APPROACH / IMMINENT / CLOSED /
  STILL CLOSED / REOPENED / OVERRIDE lines are informational: relay the full
  description to the owner (it is written to be read), send the push, and do
  nothing else. The gate acts inside HG's own logic; no operation here.
- EVENT-DRIVEN (every daily check): the shadow decision runner
  (`scripts/shadow_runner.py`, addendum 48). SHADOW MISMATCH / SHADOW
  KNIFE-EDGE / COMPOSER DID NOT REBALANCE / COMPOSER STILL NOT REBALANCING /
  COMPOSER REBALANCING RESUMED / LOGIC DRIFT / SHADOW BLIND / SHADOW RUNNER
  DOWN / SHADOW FMP DOWN lines are informational: relay them as written, send the push, and do
  nothing else: no trade, no symphony edit. Only the owner resolves a LOGIC
  DRIFT (approve: a new era in `fixtures/approved/manifest.json` plus a
  CHANGELOG entry; or roll back).
- DAILY PRE-CLOSE (15:15 ET weekdays; 12:15 ET on NYSE half-days): the
  pre-close preview (`scripts/preclose.py`, addendum 49). It shows what
  Composer's ~15:50 rebalance is about to do: the gate on live SPY, and
  each symphony's expected holdings with the dollars that move and how
  close the call is. Relay the lines as written. Push only for GATE CLOSES
  / REOPENS AT TODAY'S REBALANCE, GATE ON THE LINE, BIG DAY, PRE-CLOSE
  UNAVAILABLE, any engine line that changes holdings ("current -> target";
  owner, 2026-11-02: "ping me if the 15:15 preview shows a flip") and
  FIRST BUY ON IBKR (both forms: a live IBKR
  mirror engine may buy a fund the account has never bought, which IBKR
  can hold for a one-time emailed verification; a firm call's flip and
  market alternatives are a line, not a push, but HG's gate sides push
  whenever the gate is within 3 sigma or flipping; composer/IBKR_MIRROR.md). Never trade, pause or edit a symphony on it: an override
  is the owner's call in the Composer app (RUNBOOK.md).

## Standing exclusions

Never auto-executed under any circumstances: changes to symphony logic,
investing in new/unapproved symphonies, liquidations, go-to-cash, direct
single-asset trades, bank transfers, or any trade outside Operation 5
above. Owner override requests (RUNBOOK.md "Owner override requests",
2026-11-06) are the one human-request path through that list: on an explicit
in-session instruction the assistant runs `risk-off` (go-to-cash) or
`risk-on` (rebalance-now) on the approved symphonies via the guarded CLI,
confirmed once, logged in results/monitor/override-ledger.jsonl. A request,
not automation. During a suspected regime break (e.g., the sleeve popping in a
crash), the only mechanical trim left is Operation 5's 44% cap (the sleeve band
was retired 2026-11-18); the owner is notified prominently that discretionary
harvesting beyond it is their call (results.md addendum 7).
