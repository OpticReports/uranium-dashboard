# ADDENDUM to PREREG.md (2026-10-07, after the independent review)

PREREG.md is unchanged (registration rule). Each entry below corrects or
extends it and names the review finding it answers; REVIEW.md carries the
full list of findings, verdicts and the numbers that moved.

1. **Honesty / fit windows (MINOR).** PREREG says "the trend on 2013-21; the
   2020 and 2022 analogues are inside the trend's fit window". Correction per
   RESEARCH_S4.md (TRAIN 2013-2021 -> VALIDATE 2022-2024H1): the COVID (2020)
   analogue sits inside the trend leg's fit window; the 2008-like window
   (2021-11-09..2022-11-09) is 10 of 12 months inside the trend leg's
   VALIDATION window, quasi-out-of-sample; the 1999-like (2017-18) window is
   inside the fit window; the pullback (fitted 2024-26) is out-of-sample on
   all three. The original sentence erred in the conservative direction.

2. **Splice method / carry funding (BLOCKING).** PREREG: "ETHUSD where it
   exists; XBTUSD as the proxy before 2018-08-02". Changed: BitMEX XBTUSD is
   the HEADLINE funding series for every window, as the proxy for the live
   HL linear ETH perp. BitMEX ETHUSD is a quanto contract whose funding is
   structurally positive in every regime (2022-06 +98.5%/yr while ETH fell
   45%; 2020-03 +69%/yr; XBTUSD -6.2% / -54% in the same months), so it is a
   different instrument, not an upper bound; it is reported beside the
   headline as a labelled column ("BitMEX ETHUSD quanto - not the live
   venue's instrument"), never as the headline. No linear-ETH funding
   history for 2020 or 2022 was reachable (Hyperliquid launched in 2023).

3. **Portfolio emulation (SERIOUS).** Added to the executor layer: BTC perp
   funding on the book's own positions - at every 8h stamp of the XBTUSD
   series (shifted onto today's grid) each held position pays
   sgn x qty x close x rate (a long pays a positive rate; a short receives
   it); positions entered on the stamp's bar pay, positions exited on it do
   not. HL BTC funding is hourly and venue-specific; the proxy's sign and
   shape are what matter (funding follows the trend, so the trend leg pays
   on both sides).

4. **Outputs (MINOR / NOTEs).** Added: the intrabar worst UTC day (the bar's
   worst equity against the day_start in force, what mirror._breach_for
   reads at a 20 s poll) next to the close-to-close one; the share of the
   daily-loss and drawdown rails consumed; each engine paper-book halt's
   margin to its own line (a sub-1k margin is reported as a knife-edge);
   the S3 seam variants at offset 0 (live PENDING snapshot; seam trade
   dropped) and their 12m range; the 12m column labelled 12m* where the
   balance is not the exact day-365 close - exactness judged on the bar's
   CLOSE timestamp (re-verification, 2026-10-07: the first reading judged
   it on the open and had it the wrong way round): the 365-day windows
   (2008, 1999; 2,190 bars) end on a bar that closes ON day 365 and are
   exact, while the COVID window (leap year, 2,196 bars) returns the bar
   opening on day 365, closing 4h after it; every 3m/6m/9m balance is the
   close 4h after its instant. No number moves. Also the DD-rail column
   (share of the 30k DRAWDOWN budget consumed, minimum margin, date) beside
   the daily rail, with the rail's closest approach quoted on that one
   basis; the offset range restricted to crash paths (an offset whose BTC
   low is shallower than -50% is flagged, e.g. 1999 off-28).

5. **Start / seam (MINOR, OPEN KEY INPUT P1).** PREREG seeds "S3 pending a
   long limit" from the live snapshot; the CSV instead fills that limit on
   the 04:00Z bar (low 84,010.77 < 84,121.28). Which feed/bar the live S3
   evaluated is Casey's to answer before the memo ships (MISSING KEY INPUTS
   rule). Until then the headline runs the CSV, the live snapshot runs as
   the `pending_live` variant, and both are printed side by side with the
   S3 halt margin. The improvement-candidate question on the S3 halt cannot
   be settled on this path.

6. **Honesty box (NOTEs).** The results now carry an explicit honesty list
   (results.json `honesty`): the high-water ratchet on the favourable
   extreme before the adverse test (conservative, kept), the variant-B
   re-anchor assumption, the four executor mechanics not modelled and the
   direction of each bias, the seam volume-regime test, the S4 stop at t0
   being today's real path (not a splice artefact), and the re-worded role
   of the carry sleeve in the "no DRAWDOWN halt" result.

7. **Improvement candidates (PREREG "Improvement candidates - the rule").** Registered in
   CANDIDATES.md after the baseline and ATTRIBUTION.md, before any candidate run: C1 (pullback
   fast vol brake, ATR14/close vs its 1-year median, floor 0.25) and C2 (pullback post-stop damper,
   x0.5 / x0.25 within 5 days of a STOP), both pullback-leg only, both `stress.Options` switches
   (default off; production untouched; 5 gate tests in test_candidates.py). The decision test was
   registered STRICTER than PREREG's sentence: crash maxDD no worse on EVERY offset-0 path AND on
   the crash-path offset range, improved somewhere, and 2019+ fixed-base $/yr >= 90%. Grid: 60
   crash runs + 8 no-engine-halt sensitivities + 20 era runs (candidates.json, fig_candidates.png).
   Verdict: DO NOT PROPOSE all three (C1: 2008 offset 0 -8.2% -> -8.5%; C2: range-worst maxDD
   worse on 2008 and 1999; C1+C2: 2008 range -10.2% -> -10.3%). The softer aggregate reading would
   pass C1 and C1+C2 (COVID / 1999 maxDD -2.4pp each; 2019+ $/yr 96% / 97%), but the real-history
   and no-halt checks argue against it: C1 bound on 18 pullback entries 2019-26, 15 of them winners
   (-6,917 forgone) and 3 stops (+2,407 saved), net of fees and funding (gross -7,066 / +2,372;
   the first draft's -5.6k / +2.2k mixed bases), deepening the 2019+ maxDD -18.7% -> -20.7% and
   costing 12.3% of E5 $/yr (the leg's own fit era); C2 damped 14 trades in 2020-21, 13 of them
   winners (-14.1k, -21.7% of E3 $/yr); and WITHOUT the knife-edge S3 paper-book halt the COVID gain
   reverses (12m 128,193 -> C1 125,438 / C2 124,221 / C1+C2 122,425; C2's maxDD worse) while the
   1999 gain grows (105,439 -> 119,726 for C1+C2). The brakes help only where the pullback leg is
   structurally wrong (the 1999-like grind, 2017-18) and cost wherever it recovers. In-sample
   selection on three paths; parameters fixed from the leg's own statistics on 2017-26 history.

   Refuters' pass (2026-10-07, SERIOUS; the verdicts stand and are strengthened; full text in
   CANDIDATES.md "Post-run findings" and in candidates.json `meta.honesty`):
   (1) C1's floor 0.25 and any engine-side C2 cannot reach the venue as described - btc-executor
   clamps size_mult to [0.5, 1.0] (mirror.py SIZE_MULT_MIN), so either needs an executor code
   change; with the clamp emulated (floor 0.5) the crash cells are COVID 116,537 / -20.92%, 2008
   124,214 / -8.50%, 1999 119,158 / -13.28% and 2019+ 13,740 $/yr. (2) C2 'executor-side' is not
   implementable: /exec/target carries no exit reason and the executor cannot see engine STOPs it
   did not hold. (3) The registered 2019+ cost yardstick is trend-dominated: the S3 paper book
   (seeded 100k on 2019-01-01) halts 2020-03-20 and drops 266 pullback trades; with the pullback
   leg alive (engine_halts=False) the ratios are C1 91.6%, C2 88.9% (FAILS), C1+C2 81.7% (FAILS);
   pooled E3+E4+E5 against an exposure-matched uniform cut as control: C1 93.3% vs uniform 97.3%,
   C2 86.1% vs 94.9%, C1+C2 80.8% vs 92.4%. (4) That control - the baseline with the pullback
   weight scaled to the candidate's bar-weighted gross pullback exposure (C1 at offset 0: 0.749 /
   0.960 / 0.624 on COVID / 2008 / 1999) - reproduces the crash gain: 12m uniform vs C1 119,846 vs
   119,147 (COVID), 125,468 vs 124,214 (2008), 122,842 vs 123,092 (1999); maxDD -18.63% vs -18.62%,
   -8.09% vs -8.50%, -11.66% vs -11.23%. The candidates are a pullback size cut, not a logic
   improvement. (5) The +/-30% parameter sweep (8 variants) gives DO NOT PROPOSE for every variant;
   C2's window parameter is inert. (6) The 2019+ C1 decomposition is corrected above. (7) C1 text:
   the pullback stop uses the FILL bar's ATR14, not the signal bar's (corrected in CANDIDATES.md).
   (8) Post-stop re-entries on 2017-26 engine trades: within 1 day 60% won (37 of 62), 5-7 days
   after the stop 100% (7 of 7) - C2 damps the group that mostly wins. (9) Offsets worse / better
   than the baseline are counted next to each range-worst (C1 on 2008: close maxDD worse on 4/5,
   intrabar 5/5, 12m 5/5 although its range-worst improves; full table in CANDIDATES.md and in the
   DECISION block of candidates.json).
