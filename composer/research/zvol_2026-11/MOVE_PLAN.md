# Closing HARV: its capital pro rata into HG / KMLM / SLEEVE, one session (owner decision 2026-11-18)

Owner: "treat it [the crash sleeve] as one engine, go ahead with full pro rata"; then "I'd prefer to be
out of it asap, just close it out ... just test and execute". Basis: results.md addendum 56 and
VERIFICATION.md. Rev 2 of this plan: rev 1 (two halving sessions) FAILED its review (the mirror legs
moved 61.7% where 50% was meant; the withdraw cutoff was too late) and is replaced by this.
Every dollar amount is recomputed from live values at execution.

## Outcome
| | Before | After Day B | After the retirement change (separate, reviewed) |
|---|---|---|---|
| HARV on Composer (~$36k) | full | a $100 stub | liquidated |
| HARV sleeve on the IBKR mirror (~$6.1k) | full | about $6 of cash, no shares, no orders | dropped from the live engines |
| Targets | 29 / 29 / 27 / 15 | HG 34.1 / KMLM 34.1 / SLEEVE 31.8 | same |

Why a $100 stub and not a liquidation on the day: (1) with HARV still listed, the monitor, the 15:15
preview, the shadow runner and the paper mirror all keep working unchanged (with HARV absent the
book-drawdown alarm would read 35.6% every day and SHADOW BLIND would fire from the third session:
empty-HARV check, 2026-11-18); (2) on 2026-07-06 Composer turned a full-exit request into a
liquidation that waited for the NEXT day's window, while a partial withdraw executed the same day.
99.7% of the money is out on Day A either way.

Why about $6 is left in the mirror sleeve: the executor refuses a leg WHOLE if the queued legs exceed
the sleeve's equity when the plan runs (mirror_core.py:336), and equity moves between the evening
the legs are sized and the next 15:54 (a cent of PULS is $0.49; selling PULS costs about $1 of
commission). A sleeve under about $10 holds no shares and sends no order (it cannot buy one ZVOL).

## Day A (a full NYSE session; planned Thu 2026-11-19)
1. 15:00-15:20 ET pre-checks. Any failure: skip the day, tell the owner, send nothing.
   - `composer-api.py symphony-stats`: four symphonies, none paused, no queued deploy on HARV, no
     value implying a >50% one-day change. `market-hours`: a regular session today.
   - Record: V0 = HARV's value; cash0 = `total-stats.total_unallocated_cash`; the other three's values.
   - Mirror feed (GET): a live book, no halt, last check clean, nothing in `pending_requests`, no
     queued operator credits. Record E = the HARV sleeve's equity and its holdings.
   - Parity baseline: today's `mirror_parity` lines for HARV and KMLM (both already read MISMATCH
     because IBKR discards the mirror's ZVOL buys).
   - W = floor(V0 - 100) dollars. Guards: W <= 25% of the book; W / V0 between 0.99 and 0.999.
2. Push the owner: "HARV exit: withdrawing $W now; reinvesting 29:29:27 tonight". Submit by 15:25 ET:
   `COMPOSER_ALLOW_CAPITAL=1 composer-api.py withdraw ORQNCfZnA18wmsMWVhf8 --amount W --yes -o <file>`.
   Read the response (`deploy_time` / `deploy_on_market_open` and the deploy id): it must be scheduled
   for TODAY's window. If Composer schedules it for the next open, or converts it to a liquidation
   that waits a day, tell the owner at once; the day it fills becomes Day A and the rest shifts.
3. After the 16:35 ET check: V1 = HARV's value, C = `total_unallocated_cash` - cash0, with
   `pending_withdrawals` (or the queued-deploy flag) clear. Require |C - W| <= max($50, 0.5% of W)
   and V1 <= $150. Outside tolerance: STOP. The cash sits, the mirror is untouched, the owner is told.
   (A ZVOL distribution paid to account cash on 11-19 would show as extra C: it is HARV's money and
   is invested with the rest, up to the tolerance; beyond it, stop and read the activity.)
4. Same evening, in pairs (invest i, then mirror leg i, only after invest i returned a deploy id):
   I1 = I2 = floor(C x 29/85 x 100)/100, I3 = C - I1 - I2.
   - `invest mbkiXcuNDjueXpiox5Av --amount I1`   then leg HARV -> HG
   - `invest YPTSJFJwD2ZKfAeYJUbW --amount I2`   then leg HARV -> KMLM
   - `invest nNdBk7hc5NiBzeRvbI5T --amount I3`   then leg HARV -> SLEEVE
   (each invest with COMPOSER_ALLOW_CAPITAL=1, --yes, -o; read when each is scheduled to execute.)
5. The mirror legs. EVERY leg uses the same "before": `--composer-from-value V0` and
   `--composer-from-value-after V0 - <this leg's amount>` (POLICY "One symphony giving to several").
   The script moves fraction = amount / V0 of the sleeve's equity E as the feed shows it:
   - leg 1: `--from HARV --to HG     --composer-amount I1`
   - leg 2: `--from HARV --to KMLM   --composer-amount I2`
   - leg 3: `--from HARV --to SLEEVE --composer-amount A3`, where A3 is chosen so the three dry-run
     amounts sum to E - 6.00 (A3 = V0 x (E - 6 - m1 - m2) / E with m1, m2 the first two dry-run
     amounts; it differs from I3 by a few dollars: the note says so).
   Run all three with `--dry-run` first: require m1 + m2 + m3 within $0.02 of E - 6.00 and every
   fraction <= 50%. Then send them one at a time (`MIRROR_TRANSFER_TOKEN=via-network-secret`,
   `--note "HARV exit 2026-11-19"`), waiting until each shows in the feed's `pending_requests`.
   If the HARV sleeve holds anything but PULS and cash that evening (IBKR let a ZVOL buy through),
   leave $150 instead of $6 and sweep the rest in a later session.
   The executor applies the legs at Day B's 15:54 session, when Composer's invests also execute.
6. All three legs queued before Day B 15:30 ET. Commit `results/mirror/transfer-ledger.jsonl`.

## Day B (planned Fri 2026-11-20)
7. After the 16:35 ET check: the three invests filled (account cash back to about cash0); the
   mirror's session row shows three transfers moved in full and its account check clean; the HARV
   sleeve holds no shares and under $10; HG and SLEEVE parity "same"; HARV and KMLM no gap beyond the
   ZVOL the mirror cannot buy.
8. CHANGELOG entry with deploy ids and both brokers' before/after; report to the owner.

## If something goes wrong
- Withdraw not filled, or outside tolerance: stop before any invest or leg.
- An invest refused: fix and re-send; never send its mirror leg first.
- A mirror leg refused at send (the script exits 1, "refused"): read the reason, fix, re-send before
  Day B 15:30; a refused row does not block a re-send. "duplicate": do not re-send.
- UNKNOWN: POLICY's procedure (read the feed's `pending_requests` and today's row; `--again` only
  if the transfer is in neither).
- A leg refused or partly applied by Day B's plan: the executor re-queues a partial itself (up to 3
  plans): do not re-send. A leg refused whole: re-send that evening, sized on the new equity.
- The mirror session is skipped or halted: the legs stay queued; do not re-send; tell the owner.
- Invests do not fill on Day B: finish the Composer side; never reverse the mirror.
- There is no rollback: putting money back into HARV would be a new owner decision.
Stop and report on any of: an owner risk-off in force; Composer not rebalancing; the book drawdown
alarm; a CONCENTRATION CAP BREACH (operation 5 runs first, on the new targets).

## Expected lines on those days (not problems)
IDLE CASH of about $W on Day A's evening check and QUEUED DEPLOY lines for the three invests; the
routine's prompt tells it to report these and not act. "FIRST BUY ON IBKR - HARV is set to buy ZVOL"
keeps appearing in the 15:15 preview until HARV is dropped from the mirror's live engines (it fires
today already, for the same reason: IBKR discards the buy).

## After the exit (separate change, own review, owner approval)
- Liquidate the $100 stub on Composer once the tooling can live without HARV: the monitor's
  book-drawdown base and peak (ex-HARV), a `retired_from` the shadow runner honours, the first-buy
  check, the paper mirror, mirror_scale's engine list.
- Executor (operator, in Render, one deploy outside 15:15-16:05 ET, only when the sleeve holds no
  shares): drop HARV from MIRROR_LIVE_ENGINES and from MIRROR_WEIGHTS re-summed to 1, and set
  MIRROR_MAX_BOOK_USD explicitly. The approved manifest and the attestation keep HARV until then:
  an engine the brain stops publishing is skipped and its transfers refused.

## Costs and risks of the move itself (addendum 56, second review)
- The other three engines run about 13% larger: every loss measure scales 16-20%.
- Expected gain: about +7 points of book return a year at the study lens, +5 with all engines marked
  down alike, about +2 and not distinguishable from zero in a harsh case.
- From Day A's window to Day B's window about $36k (11% of the book) sits in account cash.
- No automatic sleeve trim below 44% of the book, and no automatic top-up (the band is retired).
- First live use of the mirror's transfer key.
