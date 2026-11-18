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
