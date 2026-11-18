# Closing HARV: its capital pro rata into HG / KMLM / SLEEVE, one session (owner decision 2026-11-18)

Owner: "treat it [the crash sleeve] as one engine, go ahead with full pro rata"; then "I'd prefer to be
out of it asap, just close it out ... just test and execute". Basis: results.md addendum 56 and
VERIFICATION.md. Rev 3 of this plan. Rev 1 (two halving sessions) FAILED its review (the mirror legs
moved 61.7% where 50% was meant; the withdraw cutoff was too late). Rev 2 (one session) PASSED WITH
CORRECTIONS on 2026-11-18 (mirror mechanics confirmed by running the real script and the real executor
core); rev 3 applies them: a 1.5% stub in place of $100, the 11-19 ZVOL payout, an earlier submit time,
a recovery path the script will actually accept, the right completion signal.
Every dollar amount is recomputed from live values at execution.

## Outcome
| | Before | After Day B | After the retirement change (separate, reviewed) |
|---|---|---|---|
| HARV on Composer (~$36-38k) | full | a stub of about 1.5% (~$550) | liquidated |
| HARV sleeve on the IBKR mirror (~$6.1k) | full | about $6 of cash, no shares, no orders | dropped from the live engines |
| Targets | 29 / 29 / 27 / 15 | HG 34.1 / KMLM 34.1 / SLEEVE 31.8 | same |

Why a stub and not a liquidation on the day: (1) with HARV still listed, the monitor, the 15:15
preview, the shadow runner and the paper mirror all keep working unchanged (with HARV absent the
book-drawdown alarm would read 35.6% every day and SHADOW BLIND would fire from the third session:
empty-HARV check, 2026-11-18); (2) on 2026-07-06 Composer turned a full-exit request into a
liquidation that waited for the NEXT day's window, while a partial withdraw executed the same day.
Why 1.5% and not $100: the withdraw is a fixed dollar amount, so HARV's whole move between the reading
and the ~15:50 window lands on the stub. HARV is 60% ZVOL (-3.6% on 11-18): a $100 stub is 0.28% of it,
and a fall of more than that in an hour would ask Composer for more than the symphony holds (outcome
not known; the one precedent is the next-day liquidation). 98.5% of the money is out on Day A.

Why about $6 is left in the mirror sleeve: the executor refuses a leg WHOLE if the queued legs exceed
the sleeve's equity when the plan runs (mirror_core.py:336), and equity moves between the evening
the legs are sized and the next 15:54 (a cent of PULS is $0.49; selling PULS costs about $1 of
commission). A sleeve under about $10 holds no shares and sends no order (it cannot buy one ZVOL).

## Day A (a full NYSE session; planned Thu 2026-11-19)
1. 14:15-14:40 ET pre-checks. Any failure: skip the day, tell the owner, send nothing.
   - `composer-api.py symphony-stats`: four symphonies, none paused, no queued deploy on HARV, no
     value implying a >50% one-day change. `market-hours`: a regular session today.
   - Record: V0 = HARV's value; cash0 = `total-stats.total_unallocated_cash`; the other three's values.
   - The ZVOL payout (ex 11-18, paid 11-19; D = HARV's ZVOL shares x $0.485, about $1,690; KMLM's is
     about $870). Where is it? Inside HARV (its `cash` about D above the usual ~$36, V0 about D higher
     than last night's $36,267 adjusted for the day): the normal case, it leaves with W. In account cash
     (cash0 about D or D + KMLM's above last night's $102): it is in cash0, so it does not disturb C;
     it is NOT invested by this plan: report it to the owner for a separate instruction. Not posted
     anywhere yet: proceed; step 3 says how it is recognised.
   - Mirror feed (GET): a live book, no halt, last check clean, nothing in `pending_requests`, no
     queued operator credits. Record E = the HARV sleeve's equity and its holdings.
   - Parity baseline: today's `mirror_parity` lines for HARV and KMLM (both already read MISMATCH
     because IBKR discards the mirror's ZVOL buys).
   - W = floor(0.985 x V0) dollars. Guards: W <= 25% of the book; W / V0 between 0.98 and 0.99.
   - Owner, in Render (read only): MIRROR_TRANSFER_MAX_FRAC on ibkr-executor is unset (default 0.25)
     or at least 0.13. The three legs need 12% of the mirror book in one cap period; the feed does not
     show the cap. Unconfirmed is not a stop: a lower cap refuses leg 3 at send (see recovery).
2. Push the owner: "HARV exit: withdrawing $W now; reinvesting 29:29:27 tonight". Submit by 14:45 ET
   (the same-day cutoff is not verified live: RUNBOOK says "expected"; the one same-day partial
   withdraw on record was a morning request, and a 15:49 request went to the next open):
   `COMPOSER_ALLOW_CAPITAL=1 composer-api.py withdraw ORQNCfZnA18wmsMWVhf8 --amount W --yes -o <file>`.
   Read the response (`deploy_time` / `deploy_on_market_open` and the deploy id): it must be scheduled
   for TODAY's window. If Composer schedules it for the next open, or converts it to a liquidation
   that waits a day, tell the owner at once; the day it fills becomes Day A and the rest shifts.
   If it fills at an open, run steps 3-6 that day before 15:30 ET, not after 16:35.
   A liquidation makes HARV disappear from the symphony list: the monitor's book-drawdown line is then
   an expected artifact (empty-HARV check), not a stop.
3. After the 16:35 ET check: V1 = HARV's value, C = `total_unallocated_cash` - cash0, with
   `pending_deploys_cash` == 0 and HARV's `has_queued_deploy` false (`pending_withdrawals` stayed 0.0
   with HG's withdraw queued on 07-20: it is not the signal). Require |C - W| <= max($50, 0.5% of W)
   and V1 <= 3% of V0.
   The one recognised exception is the ZVOL payout arriving after step 1: C - W within $60 of D (or
   of D + KMLM's payout), or V1 - (V0 - W) between D - 1.5% of V0 and D + 1.5% of V0. Then proceed
   with W as C; the payout stays where it landed (account cash, or the stub) and is reported to the
   owner for a separate instruction. Any other gap: STOP. The cash sits, the mirror is untouched, the
   owner is told.
4. Same evening, before anything is sent, the mirror dry-runs.
   - Feed (GET): last session 2026-11-19, no run open, not halted, check clean, `pending_requests`
     empty, no queued operator credits (an open run would skip Day B's session).
   - E = the `sleeve_equity` the dry-run prints tonight (marks only change at a session, so it holds
     until Day B's plan), NOT step 1's reading. T = E - 6.00.
     m1 = m2 = floor(T x 29/85 x 100)/100, m3 = T - m1 - m2  (the mirror dollars, 29 : 29 : 27).
   - EVERY leg uses the same "before" (POLICY "One symphony giving to several"), and a composer
     amount scaled so the script's own formula (fraction = amount / V0, dollars = round(fraction x E, 2))
     gives m_i: a_i = round(V0 x m_i / E, 4), `--composer-from-value V0`,
     `--composer-from-value-after V0 - a_i`. a_i is about 1.4% above the Composer invest I_i: Composer
     keeps a 1.5% stub, the mirror keeps $6. The note says so.
     - leg 1: `--from HARV --to HG     --composer-amount a1`
     - leg 2: `--from HARV --to KMLM   --composer-amount a2`
     - leg 3: `--from HARV --to SLEEVE --composer-amount a3`
   - `--dry-run` all three: each printed amount equals its m_i, the three sum to T within $0.02, every
     fraction <= 50%. If the HARV sleeve holds anything but PULS and cash (IBKR let a ZVOL buy
     through), T = E - 150 instead and the rest is swept in a later session.
5. The Composer invests, all three, one after another (each with COMPOSER_ALLOW_CAPITAL=1, --yes, -o;
   read the deploy id and when each is scheduled to execute):
   I1 = I2 = floor(C x 29/85 x 100)/100, I3 = C - I1 - I2  (C is W in the payout exception).
   - `invest mbkiXcuNDjueXpiox5Av --amount I1`
   - `invest YPTSJFJwD2ZKfAeYJUbW --amount I2`
   - `invest nNdBk7hc5NiBzeRvbI5T --amount I3`
6. The mirror legs, only after all three invests returned a deploy id: send them one at a time
   (`MIRROR_TRANSFER_TOKEN=via-network-secret`,
   `--note "HARV exit 2026-11-19: mirror sized to leave $6 (29:29:27 of the sleeve); Composer invested I_i"`),
   each printed amount equal to its dry-run amount, waiting until each shows in the feed's
   `pending_requests`. All three queued before Day B 15:30 ET (they are applied at Day B's 15:54
   session, when Composer's invests also execute). Commit `results/mirror/transfer-ledger.jsonl`.

## Day B (planned Fri 2026-11-20)
7. After the 16:35 ET check: the three invests filled (account cash back to about cash0, plus a
   payout left there); the mirror's session row shows three transfers moved in full and its account
   check clean; the HARV sleeve holds no shares and under $10; HG and SLEEVE parity "same"; KMLM no
   gap beyond the ZVOL the mirror cannot buy; HARV reads MISMATCH (see expected lines).
8. CHANGELOG entry with deploy ids and both brokers' before/after; report to the owner.

## If something goes wrong
- Withdraw not filled, or outside tolerance: stop before any invest or leg.
- An invest refused: fix and re-send; no mirror leg goes before all three invests are in.
- A mirror leg refused at send (the script exits 1, "refused"): read the reason, fix, re-send before
  Day B 15:30; a refused row does not block a re-send. "duplicate": do not re-send.
- "unauthorized" on the first leg (first live use of the transfer key): nothing is queued. Tell the
  owner; the fallback is the owner posting m1, m2, m3 to the executor's transfer route with his own
  credential before Day B 15:30. This session never holds that credential.
- Leg 3 refused for the book's transfer cap (MIRROR_TRANSFER_MAX_FRAC below 13%): legs 1 and 2 stay;
  tell the owner; leg 3 goes when the cap period rolls or the owner raises the cap.
- UNKNOWN: POLICY's procedure (read the feed's `pending_requests` and today's row; `--again` only
  if the transfer is in neither).
- A leg partly applied by Day B's plan: the executor re-queues the remainder itself (up to 3 plans):
  do not re-send. (A partial leaves the sleeve's cash at 0, so the re-queued remainder is then refused
  whole with a red alert at the next plan: expected, do not re-send; sweep what is left as below.)
- A leg refused whole by Day B's plan (the sleeve fell more than the $6 of headroom: about 13 cents on
  PULS), or any later sweep: what is left is then more than 50% of the sleeve, which the script refuses
  as one leg. Tell the owner first, then send it as TWO legs to the same taker, both sized on the same
  feed equity E': the first at 50% of E', the second with `--again` (the script's "a second move of
  the same pair is meant") for the rest, the two summing to E' - 6. Dry-run both and check the sum
  first; the composer values passed are synthetic (V = E', amounts = the mirror dollars) and the note
  says so. This is the only use of `--again` outside POLICY's UNKNOWN procedure.
- The mirror session is skipped or halted: the legs stay queued; do not re-send; tell the owner.
- Invests do not fill on Day B: finish the Composer side; never reverse the mirror.
- There is no rollback: putting money back into HARV would be a new owner decision.
Stop and report on any of: an owner risk-off in force; Composer not rebalancing; the book drawdown
alarm; a CONCENTRATION CAP BREACH (operation 5 runs first, on the new targets).

## Expected lines on those days (not problems)
IDLE CASH of about $W on Day A's evening check and QUEUED DEPLOY lines for the three invests; the
routine's prompt tells it to report these and not act. "FIRST BUY ON IBKR - HARV is set to buy ZVOL"
keeps appearing in the 15:15 preview until HARV is dropped from the mirror's live engines (it fires
today already, for the same reason: IBKR discards the buy). From Day B until the retirement change:
"MIRROR LIVE MISMATCH - HARV" every day (the mirror's sleeve is empty, Composer's stub holds the
rule's funds). No cap breach is expected: HG / KMLM / SLEEVE are about 33.0 / 29.8 / 25.7% of the book
on Day A's evening and 36.9 / 33.7 / 29.4% after Day B, against 44%.

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
- ZVOL is sold the day after its ex-date while KMLM's own sleeve keeps trading it; tax is not modelled.
- An owner risk-off on a taker cancels its queued invest, but a queued mirror leg cannot be cancelled
  with the transfer key. The research-side and executor paper books are not moved.
- No automatic sleeve trim below 44% of the book, and no automatic top-up (the band is retired).
- First live use of the mirror's transfer key.
