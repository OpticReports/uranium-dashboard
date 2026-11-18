# Independent review (2026-11-18) of commit 6a67a612

Two reviewers that did not write the study. Both: PASS WITH CORRECTIONS. All corrections applied.

## Reviewer A - data integrity and numbers
Recomputed from the raw inputs with its own code: the weight/return alignment (weights at d earn d+1;
correlation with Composer's series 0.9993 at lag 1, 0.31 / 0.20 / 0.47 at lags 0, -1, 2: no look-ahead);
the simulator (899 of 899 sessions match Composer); the futures index (equal to lib's on 4,745 days);
attribution, placebo, long path, books and bootstrap, predictors, refinements. All reproduced except:
- SERIOUS: the live switcher part was understated. On 10-26..29 there were no snapshots and q1 used the
  backtest's weights; Composer had not rebalanced and the live book was still in SOXL. Parts did not sum
  to the symphony's P&L ($13,882 vs $22,781). Fixed: last snapshot carried forward, switcher taken as the
  residual, an assertion that parts sum. Switcher live +34.5% in 94 sessions (was +20.2%); its
  annualised pace +121% (was +64%); q4 and q7 re-run.
- SERIOUS: PULS distributions were counted as paid outside the symphony; they are credited inside when
  the fund is still held on the pay date. Only the 08-19 ZVOL payout left. HARV live +$830 (was +$1,312).
- MINOR: ZVOL calendar-year returns dropped each year's first session (2024 +9.3%, 2025 -10.7%, 2026
  +5.1%); "16 of 21 positive years" is 17 of 21; the 9%/yr "cost drag" is the gap between compounded
  returns (the charge on capital is ~7%/yr); the model-window percentile mixed bases.
- NOTES: unexpired futures contracts took the file's last row as expiry (fixed); with the 281
  approximated index days zeroed, 2006-07..2010 falls from +11.8% to +4.9%/yr and pre-ZVOL from +8.9% to
  +7.0%; VIX-based predictors are stamped 4:15pm against 4:00pm ETF closes (favours predictors that
  failed anyway); PREREG cites an analyze.py that became q1..q8.

## Reviewer B - method and inference
- BLOCKING: the same two live errors (PULS double count; the haircut anchor). Applied as above.
- SERIOUS S1: the switcher's 94-session live pace is noise; report a break-even instead, and the haircut
  keeps backtest volatility (76%) where live ran ~109%. Added: break-even pace, a live-volatility lens,
  and the statement that the pre-registered 3-point drawdown limit could never be met by this move.
- SERIOUS S2: only the switcher was haircut. Added: T-bills vs the harvester at its long-run and 2010-19
  paces, and dollars on HARV's actual $37.5k (11.7% of the book, not 15%).
- SERIOUS S3: "+9%/yr long-run" hid a flat decade (2010-2019: -1.8%/yr) and selection (best of 41
  candidates). Added: sub-period table, the selection note, trailing year in excess of bills.
- SERIOUS S4: execution timing is first-order. Added: one-close-late test (+8.9% -> -0.1%/yr before
  2023), cost ladder, live ZVOL fills against the official close (median +12.7 bps worse, n 22).
- SERIOUS S5: around spikes it is low average exposure, not timing. Section rewritten; added exposure on
  the 40 worst short-volatility days and the usual 10-session return as the comparison.
- MINOR: "beats every placebo" -> p < 0.01 in each era, gross of costs; the plain RSI(2) trigger earns
  the same per-day edge (added); Q5 wording -> "none clears the pre-registered bar"; live books B/C/D now
  use the live residual switcher; the volatility-matched annex is book E restated (dropped from the
  argument); book A leaves a quarter of the moved money in the same rule (stated).
- NOTES taken: other destinations and a half move (added, not pre-registered); kill criteria (offered to
  the owner); "harvester" is a misnomer (carry is 0.06 of the ZVOL leg's 0.64).

Every added analysis is in q8_robust.py, reproduced by the author from the reviewers' descriptions, and
labelled as not pre-registered.

# Second review (2026-11-18, commit 4d103d01): the "move it pro rata" recommendation

Two reviewers, both PASS WITH CORRECTIONS. Nothing was moved.

## Reviewer A - recomputation from the frozen backtests with its own code
- Engines, the switcher shift and every point estimate match to five decimals; intervals (5,000 draws,
  its own seed) within ~0.5 pt of the study's.
- SERIOUS: the headline figures describe a 15-point move out of 29/29/27/15; HARV is 11.7% of the real
  book. At actual weights, switcher at its live pace: pro rata +7.1%/yr [+2.0, +15.1], maxDD +1.5 pts
  [+1.1, +3.6]; all into KMLM +11.0% [+1.7, +24.7], +3.0 pts [+2.1, +7.4].
- Pro rata minus all-into-KMLM, paired: maxDD -2.6 pts [-5.8, -0.9] (P 0.99); return -4.8 pts
  [-14.2, +2.3] (not distinguishable). Pro rata vs KEEP: P(more return) 0.99, P(lower Sharpe) 0.995.
- The sample drawdown deltas sit low in their own bootstrap distributions (medians +2.7 and +5.5 pts on
  the 15-point move). "Two-thirds of the return for under half the drawdown" holds only at the live-
  pace lens on target weights; honest form: about half the extra drawdown, half to nine-tenths of the
  extra return depending on the switcher's pace.
- No bug in book_rets or the other-destinations block.

## Reviewer B - assumptions and what the comparison leaves out
- BLOCKING (execution): POLICY Operation 5 rebalances all four engines to 29/29/27/15 on a 40% breach
  and its headroom codicil ties the cap to the largest target + 10 pts. After a pro-rata move HG sits
  at 36.7% of the book: a breach is 27% likely within 21 sessions and 73% within 63, and it would
  re-fund HARV. All-into-KMLM (41.8%) breaches on day one. Targets are also hard-coded in monitor.py
  and mirror_dry.py. mirror_transfer.py refuses any leg above 50% of the giving sleeve, so the mirror
  cannot empty HARV in one change set.
- SERIOUS: with every engine marked down alike (40% of backtest excess, the switcher's own ratio), pro
  rata is +6.6%/yr [+1.1, +14.1] for +3.4 pts on the 15-point move (48% of all-into-KMLM's return for
  57% of its drawdown), and half-into-KMLM matches it. In a harsh case (HG and switcher +20%/yr, SLEEVE
  +10%) it is +1.3% [-2.5, +6.7] for +5.1 pts. "Shallower than all-into-KMLM" holds in every case;
  "better return per unit of drawdown" does not.
- SERIOUS: pro rata is the other three engines run about 13% larger at actual weights (18% on targets):
  volatility, CVaR and worst stretches all scale 16-20%, in the same episodes.
- SERIOUS: Operation 1's sleeve band reads 12.3% now and 14.1% after the SLEEVE leg (15% auto-trim), on
  an IBKR equities figure of $346k last reported 2026-07-07; Operations 2 and 3 reserve the SLEEVE and
  KMLM increases for their own evidence gates.
- Pro rata is not distinguishable from all-into-HG, half-into-KMLM or 65%-into-KMLM. Live window:
  pro rata +31.6% vs KEEP +27.0% (1.1 standard errors) and A +32.1%.
- Daily rebalancing is not manufacturing the result (+8.5 monthly, +8.2 quarterly, +5.7 buy-and-hold).
- Suggested: stage it - half pro rata after the 11-19 ZVOL credit, inside the mirror's 50% limit, the
  rest on a dated review; rewrite Operation 5 in the same change set; refresh the IBKR figure.

Outcome: the recommendation is restated as "any spread across the other engines is similar; the choice
is how much more engine risk to run", with the policy rewrite and staging as preconditions.

## The exit plan (MOVE_PLAN.md), 2026-11-18 evening

| Rev | Reviewer | Verdict | What it found |
|---|---|---|---|
| 1 (two halving sessions) | plan reviewer B | FAIL | mirror legs moved 61.7% where 50% was meant; withdraw cutoff too late; C undefined; impossible pass criterion |
| 2 (one session, $100 stub) | independent, ran the real transfer script and executor core | PASS WITH CORRECTIONS | 1 blocking (a $100 stub and "V1 <= $150" tighter than HARV's normal move in the hour: 6-29% false stop, over-withdraw tail), 2 serious (the 11-19 ZVOL payout larger than both tolerances; recovery re-sends above the script's 50% limit), 8 minor/notes. Mirror mechanics, caps, order of sells/transfers/buys, no automatic capital action, no cap breach: confirmed |
| 3 (1.5% stub; legs sized 29:29:27 of the sleeve) | independent narrow re-check, ran `mirror_transfer.run()` and `build_plan` offline | PASS WITH CORRECTIONS, no blocking | the new sizing gives the intended dollars on 8 named and 4,000 random (V0, E) pairs; queued legs do not change sizing; normal and payout cases never overlap. 8 wording fixes (the payout exception must replace one test, not both; half a sleeve floors, not rounds; same-day `--again`; a note in double quotes loses "$6"; POLICY says the scaled amount is not a Composer amount) |

Rev 3.1 applies the last eight. Not verified by anyone and settled only on the day: Composer's same-day
cutoff (read from the withdraw's response), whether Composer accepts a 98.5% withdraw without turning
it into a liquidation, the deployed transfer cap (owner reads it in Render), where the payout posts.
