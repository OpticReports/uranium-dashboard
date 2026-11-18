# Retiring HARV: moving its capital pro rata into HG / KMLM / SLEEVE (owner decision 2026-11-18)

Owner: "treat it [the crash sleeve] as one engine, go ahead with full pro rata". Basis: results.md
addendum 56 and VERIFICATION.md (second review). Nothing below runs without the owner's go for that
session; every dollar amount is recomputed from live values at execution.

## What changes, and where
| | Before | After the two sessions | After the retirement change |
|---|---|---|---|
| Targets (HG / KMLM / SLEEVE / HARV) | 29 / 29 / 27 / 15 | 34.1 / 34.1 / 31.8 / stub, no target | 34.1 / 34.1 / 31.8 / gone |
| Engine cap (POLICY operation 5) | 40%, resets all four | 44%, resets HG / KMLM / SLEEVE only | same |
| Sleeve band (operation 1), scale-up (operation 2) | armed | retired | retired |
| HARV on Composer (~$37.5k, 11.7% of the book) | full | ~25% of today (~$9k) | 0 |
| HARV sleeve on the IBKR mirror (~$6.1k) | full | ~25% of today (~$1.5k) | 0 |

The same rule inside the KMLM symphony (its 25% VIX sleeve) is not touched.

## Why two sessions and a stub
`mirror_transfer.py` moves the same FRACTION on the mirror as Composer moved, refuses a leg above 50%
of the giving sleeve, and the executor caps transfer-token moves at 25% of the book a day and 6
requests. Three sequential legs of a 50% move are 17.1%, 20.6% and 24.1% of the giving sleeve: all
inside the limits. A 100% move is not (its last leg is 100%). So each session halves HARV on both
brokers, and the last quarter waits for the engine-retirement change (below).

## One session (N = 1, then 2)
Day A (a full NYSE session; never a half-day, never the session before a market holiday):
1. 15:20-15:35 ET pre-checks, all must pass or the session is skipped and reported:
   - `composer-api.py symphony-stats`: all four symphonies present, none paused, no queued deploy on
     HARV, no value implying a >50% one-day change; `market-hours` shows a regular session.
   - Session 1 only: the 2026-11-19 ZVOL distribution shows as credited (HARV's cash or holdings
     reflect it; the 11-19 evening check records which).
   - The mirror feed (GET, read token): a live book, no halt, no unresolved requests, no queued
     operator credits, HARV sleeve not frozen.
   - W = 50% of HARV's Composer value V, rounded to cents. Guard: W <= 25% of the book (it is ~6%).
2. Before 15:45 ET: `COMPOSER_ALLOW_CAPITAL=1 composer-api.py withdraw ORQNCfZnA18wmsMWVhf8 --amount W --yes`.
   It executes in Composer's ~15:50 window, selling HARV's holdings pro rata.
3. 16:35 ET check (the daily monitor run): confirm the withdraw filled (HARV's value ~ V - W; account
   cash up by ~W). If it did not, stop: nothing else is sent.
4. Same evening, once the cash shows as buying power: three invests, sized on the cash actually
   received C (C ~ W): `invest mbkiXcuNDjueXpiox5Av --amount C*29/85`, `invest YPTSJFJwD2ZKfAeYJUbW
   --amount C*29/85`, `invest nNdBk7hc5NiBzeRvbI5T --amount C - the first two` (each with
   COMPOSER_ALLOW_CAPITAL=1 and --yes). They execute in Day B's window.
5. Same evening, the mirror legs, in this order, each once (never --again unless POLICY's UNKNOWN
   procedure says so), with V0 = HARV's Composer value before the withdraw and a1 = W*29/85,
   a2 = W*29/85, a3 = W - a1 - a2:
   - `mirror_transfer.py --from HARV --to HG     --composer-amount a1 --composer-from-value V0       --composer-from-value-after V0-a1       --note "HARV retirement N/2 2026-11-.."`
   - `mirror_transfer.py --from HARV --to KMLM   --composer-amount a2 --composer-from-value V0-a1    --composer-from-value-after V0-a1-a2`
   - `mirror_transfer.py --from HARV --to SLEEVE --composer-amount a3 --composer-from-value V0-a1-a2 --composer-from-value-after V0-W`
   (MIRROR_TRANSFER_TOKEN=via-network-secret, as in the daily routine.) Run each with `--dry-run`
   first and read its line. The executor applies them at Day B's 15:54 session, the same session in
   which Composer's invests execute.
Day B:
6. 16:35 ET check: the three invests filled; the mirror's session row lists the three transfers as
   applied and its account check is clean; `mirror_parity` holdings parity per engine. Day returns
   are not compared on a transfer day (the parity check says so).
7. CHANGELOG entry with the deploy IDs, amounts, before/after values on both brokers; commit the
   transfer ledger; report to the owner.

Schedule proposed: session 1 = Fri 2026-11-20 (Day A) / Mon 11-23 (Day B); session 2 = Tue 11-24 /
Wed 11-25. (Thu 11-26 is closed and Fri 11-27 is a half-day: no session then.)

Between Day A's window and Day B's window W sits in Composer account cash (one session out of the
market on ~6% of the book). The mirror moves sleeve to sleeve on Day B with no gap.

## Stop conditions (any one: stop, send nothing further, report)
A withdraw or invest that does not fill as expected; a mirror leg that answers refused, duplicate or
UNKNOWN; a mirror halt or account-check problem; Composer not rebalancing; an owner risk-off in
force; the book's drawdown alarm (17%) or any engine's anomaly tier firing that day; a CONCENTRATION
CAP BREACH (operation 5 then runs first, on the new targets).

## Not in these sessions: the engine-retirement change
Emptying the stub and removing HARV from the tooling touches the monitor (drawdown tiers, cap),
the 15:15 preview, the shadow runner, the paper mirror, the approved manifest, the mirror brain and
the executor's live-engine list (an operator change in Render), plus an operator-level move to empty
the mirror sleeve. It gets its own build, tests, independent review and owner approval.

## Known costs and risks of the move (addendum 56, second review)
- It runs the other three engines ~13% larger: every loss measure scales 16-20%.
- Expected gain depends on the engines keeping some of their backtest pace: about +7 points of book
  return a year at the study lens, +5 with all engines marked down alike, about +2 and not
  distinguishable from zero in a harsh case.
- Retiring the sleeve band removes the automatic trim after a crash pop below 44% of the book.
- The 44% cap over three engines has not been re-simulated.
