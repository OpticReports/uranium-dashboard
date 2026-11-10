# REVIEW.md - independent review of the crash stress study: findings, fixes, numbers moved

Study: `research/stress` (PREREG.md, 2026-10-07). Two independent verifiers (adversarial-method,
portfolio-guard; code under `verify/`) returned 16 findings: 1 BLOCKING, 2 SERIOUS, 4 MINOR, 9 NOTE.
This pass applied every BLOCKING/SERIOUS/MINOR item, applied the NOTEs that were cheap as code or
labels, and recorded the rest here and in the results' honesty box. PREREG.md is untouched; the
changes to the registration are in ADDENDUM.md. Nothing outside `research/stress` changed.

Tests: 15 -> 23 (8 new gate tests, one per fixed defect; all pass: `python3 -m pytest -q
test_stress.py test_carry_sleeve.py test_run_all.py`). Grid re-run: `python3 run_all.py`
(83 run files, 45 s) -> results.json, fig_COVID/2008/1999/summary.png (each read and checked).

**OPEN KEY INPUT (P1, decision-gating), narrowed to ONE datum: the S3 book's 2026-10-07 04:00Z bar
low as the live engine saw it.** The CSV fills the S3 long limit 84,121.28 on that bar (low
84,010.77); the live engine reported PENDING at the 08:00Z close. The engine's own /bars endpoint
shows the same low, 84,010.77, identical to the CSV - so this is not a data question: the live book
had a bar crossing its limit on its own feed and did not fill. Recorded as an open ENGINE-SIDE
question (why the S3 book did not fill). Until it is answered the headline runs the CSV and the live
snapshot runs as the `pending_live` seam variant, printed side by side (sensitivity: COVID K0.75 12m
115,070..129,231).

## Headline table after the fixes (offset 0, variant A, intrabar, start 100,000)

Carry funded by BitMEX XBTUSD (proxy for the live HL linear ETH perp); BTC perp funding on the
book's own positions modelled from the same series.

| scenario | K | 3m | 6m | 9m | 12m* | maxDD | worst day c2c / intrabar | daily rail used | DD rail used (min margin, date) | exec halts | engine-book halt (margin) | carry flips | BTC funding | hold-BTC 12m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| COVID-like | 0.75 | 96,887 | 96,458 | 103,666 | 115,987* | -21.0% | -8,921 / -8,884 | 59% | 90% (3,051, 05-27) | none | S3@11-30 (-1.0k, KNIFE-EDGE) | 4 | -2,820 | 457,416 |
| COVID-like | 0.30 | 98,889 | 99,282 | 102,339 | 108,900* | -8.3% | -3,568 / -3,554 | 59% | 34% (19,887, 05-27) | none | S3@11-30 (-1.0k, KNIFE-EDGE) | 4 | -1,128 | 457,416 |
| 2008-like | 0.75 | 112,697 | 120,880 | 130,078 | 125,924 | -8.2% | -4,512 / -5,026 | 34% | 44% (16,737, 10-07) | none | none (+19.9k) | 1 | -482 | 27,072 |
| 2008-like | 0.30 | 105,188 | 108,462 | 112,141 | 110,479 | -3.9% | -1,805 / -2,010 | 34% | 18% (24,695, 10-07) | none | none (+19.9k) | 1 | -193 | 27,072 |
| 1999/2000-like | 0.75 | 92,766 | 98,706 | 107,340 | 116,600 | -13.6% | -6,224 / -7,051 | 47% | 59% (12,313, 12-27) | none | S3@12-08 (-3.4k) | 9 | -5,008 | 16,753 |
| 1999/2000-like | 0.30 | 98,100 | 100,958 | 104,412 | 108,225 | -5.1% | -2,396 / -2,727 | 45% | 22% (23,329, 12-27) | none | S3@12-08 (-3.4k) | 9 | -2,003 | 16,753 |

`12m*`: exactness judged on the bar's CLOSE (re-verification: the first reading judged it on the
open and had it the wrong way round). The 2008 and 1999 12m cells ARE the exact day-365 close (365-day
windows, 2,190 bars: the last path bar closes on the instant); COVID's is the bar opening on day 365,
closing 4h after it (leap-year window, 2,196 bars). The 3m/6m/9m columns are the close 4h after day
91/182/273 in every scenario. No number moves. Daily rail = share of the daily-loss budget (15% of
base at K0.75, 6% at K0.30) consumed on the worst intrabar day; across all offsets the maximum is 64%
(COVID off-14, both K). DD rail = share of the 30,000 DRAWDOWN budget (HW - 30% of base) consumed at
the worst intrabar reading, with the minimum margin to the line and its date; the grid maximum is 90%
(COVID K0.75 offset 0). KNIFE-EDGE = the paper book crossed its line by less than 2% of its peak
(2,157 for S3's 107,860 peak).

Beside it, the BitMEX ETHUSD quanto column (NOT the live venue's instrument; no series for 1999):

| scenario | K | 12m headline | 12m quanto | maxDD headline | maxDD quanto | carry 12m headline / quanto |
|---|---|---|---|---|---|---|
| COVID-like | 0.75 | 115,987 | 135,840 | -21.0% | -15.9% | 34,221 / 54,079 |
| COVID-like | 0.30 | 108,900 | 128,754 | -8.3% | -6.1% | 34,221 / 54,079 |
| 2008-like | 0.75 | 125,924 | 137,205 | -8.2% | -7.4% | 30,183 / 41,465 |
| 2008-like | 0.30 | 110,479 | 121,761 | -3.9% | -3.3% | 30,183 / 41,465 |

12-month range across the five start offsets (headline): COVID K0.75 103,701 (off-28) .. 127,699
(off-14), maxDD -22.0% .. -15.7%; K0.30 104,312 .. 114,196. 2008 K0.75 119,573 (off+14) .. 125,924
(off+0), maxDD -10.2% .. -8.2%; K0.30 107,844 .. 110,479. 1999 K0.75 110,656 (off-28) .. 123,023
(off+28), maxDD -16.9% .. -13.4%; crash paths only (off-28 is not a crash path: BTC low -31% vs -84%,
12m -29%) 116,600 .. 123,023; K0.30 107,504 .. 112,473 (crash only 108,225 .. 112,473).

What did not change: no executor halt (DAILY_LOSS or DRAWDOWN) fires in any of the 83 runs; the
BTC-book arrays are identical whichever carry series is used; the engine trade lists are unchanged
(the review touched the carry series, a cost the executor did not book, and the reporting).

## Before -> after (offset 0; before = pre-review results.json, ETHUSD quanto carry where covered,
no BTC funding; after = XBTUSD proxy + BTC funding)

| scenario | K | 3m | 6m | 9m | 12m | maxDD | S3 halt (margin, new) |
|---|---|---|---|---|---|---|---|
| COVID | 0.75 | 101,596 -> 96,887 | 106,116 -> 96,458 | 116,330 -> 103,666 | 138,629 -> 115,987 | -15.6% -> -21.0% | 11-30 (-1,016) |
| COVID | 0.30 | 103,211 -> 98,889 | 108,278 -> 99,282 | 114,173 -> 102,339 | 129,870 -> 108,900 | -6.0% -> -8.3% | 11-30 (-1,016) |
| 2008 | 0.75 | 114,953 -> 112,697 | 125,147 -> 120,880 | 140,213 -> 130,078 | 137,688 -> 125,924 | -7.3% -> -8.2% | none (+19,864) |
| 2008 | 0.30 | 107,508 -> 105,188 | 112,744 -> 108,462 | 122,159 -> 112,141 | 121,954 -> 110,479 | -3.3% -> -3.9% | none (+19,864) |
| 1999 | 0.75 | 93,091 -> 92,766 | 100,264 -> 98,706 | 110,694 -> 107,340 | 121,608 -> 116,600 | -14.4% -> -13.6% | 12-08 (-3,416) |
| 1999 | 0.30 | 98,230 -> 98,100 | 101,581 -> 100,958 | 105,753 -> 104,412 | 110,228 -> 108,225 | -5.2% -> -5.1% | 12-08 (-3,416) |

Decomposition of the COVID K0.75 12m move (138,629 -> 115,987 = -22.6k): carry series quanto ->
XBTUSD proxy -19.9k (138,629 -> 118,776, the verifier's T10 cell reproduced to the dollar); BTC
perp funding -2.8k (118,776 -> 115,987; -2,789 at the 365-day bar, -2,820 at the path's end). 2008
K0.75: -11.3k carry, -0.5k funding. 1999 K0.75 (already XBTUSD-funded): -5.0k funding only.

The 1999 K0.75 maxDD NARROWS with BTC funding (-14.45% -> -13.61%) although every balance is lower:
funding lowered the Oct-21 peak (-845) more than the Dec-27 trough (+135), so the peak-to-trough
ratio shrinks. A narrower maxDD here is the cost landing on the peak, not an improvement.

12m ranges before -> after (K0.75): COVID 125,540..155,406 -> 103,701..127,699; 2008
131,562..137,688 -> 119,573..125,924; 1999 114,990..128,302 -> 110,656..123,023. maxDD ranges: COVID
-15.6%..-13.1% -> -22.0%..-15.7%; 2008 -10.0%..-7.3% -> -10.2%..-8.2%; 1999 -17.2%..-12.4% ->
-16.9%..-13.4%.

Sensitivities before -> after (K0.75 offset 0): no-engine-book-halts 12m COVID 151,023 -> 128,193,
2008 137,688 -> 125,924, 1999 111,261 -> 105,439. The old "XBTUSD proxy" sensitivity cell (118,776 /
126,406) is now the headline minus funding; the old headline (138,629 / 137,688) is now the quanto
column minus funding (135,840 / 137,205).

hw_end (COVID K0.75) 139,255 -> 121,393: the carry series changed, not the ratchet (NOTE below).

## Findings, verdicts, what changed, numbers moved

### BLOCKING - headline table and all figures used BitMEX ETHUSD QUANTO funding for the carry sleeve
Verdict: CONFIRMED and applied. The quanto's funding is structurally positive in every regime
(2022-06 +98.5%/yr while ETH fell 45%; 2020-03 +69%/yr vs XBTUSD -54%), so it is a different
instrument, not an upper bound. Change (`run_all.py`): `HEADLINE_FUNDING = "XBTUSD"` for every window
(`funding_for` defaults to it; the ETHUSD source is refused where its data does not cover the
window instead of silently proxied); the full grid is run on BOTH series; `S["runs"]` is the proxy
headline, `S["runs_quanto"]` the labelled quanto column; the table prints both side by side; the
scenario charts draw the quanto carry as a dotted line labelled "not the live instrument"; the summary
chart's fourth panel marks the quanto cell with a hollow marker; the honesty box states that no
linear-ETH funding history for 2020/2022 was reachable. Numbers moved: COVID K0.75 12m 138,629 ->
118,776 before funding (every offset -18k..-24k), maxDD -15.6% -> -20.2%; 2008 137,688 -> 126,406;
K0.30 COVID 129,870 -> 110,016. 1999 unchanged by this item (already XBTUSD). The 2008 XBTUSD gate is
ON 9.6% of bars (2.0% at off+28) vs 100% on the quanto; COVID 63% vs 100%. Gate test:
`test_run_all.py::test_headline_funding_is_xbtusd_even_where_ethusd_covers` (fails pre-review:
`funding_for` returned ETHUSD for the COVID anchor and `HEADLINE_FUNDING` did not exist).

### SERIOUS - BTC perp funding on the book's own positions was not modelled and not disclosed
Verdict: CONFIRMED and applied. Change (`stress.py`): `Executor(btc_funding={stamp_ts: rate_8h})`;
at every 8h stamp that lands on a bar close, each position still held pays `-sgn x qty x close x
rate` (a long pays a positive rate; entered-this-bar positions pay, exited-this-bar ones do not;
off-grid stamps map to the next close, `funding_by_close`). It is booked in cash, in the per-trade
record (`funding`, inside `pnl`) and in per-bar `btc_funding_cum`; `run_path` reports total, by leg
and position-stamps; `run_all.py` feeds the shifted XBTUSD window to every run. Numbers moved (K0.75
offset 0): COVID -2,820 (pullback -547, trend -2,273; 1,078 position-stamps), 2008 -482, 1999 -5,008
(trend -5,411 = 25% of that year's gain; the trend leg pays on both sides because funding follows the
trend) - the verifier's T7 figures reproduced to the cent. K0.30: -1,128 / -193 / -2,003. Across
offsets: COVID -3.6k..-4.2k, 2008 -0.5k..-1.1k, 1999 -4.3k..-6.5k. No halt changes. Gate test:
`test_stress.py::test_btc_funding_per_stamp` (fails pre-review: `btc_funding` was not a parameter;
also pins the COVID total to -2,820.12).

### SERIOUS - the COVID headline rides on the disputed seam input; the S3 paper-book halt is a knife-edge
Verdict: CONFIRMED; applied as far as this pass can - the key input itself needs Casey (P1 above).
Change (`stress.py`): `engine_trades(bars, seam_variant)` with `csv` (headline), `pending_live`
(production Book continued from the live snapshot: S3 flat, long limit resting at the 08:00Z close
83,706.22, signal_ts 08:00Z, ATR of that bar - `pullback_trades_pending_live`) and `drop_seam` (the
verifier's CF1: seam trade removed, later trades kept; a counterfactual, not an engine path); the
trend leg is identical in all three (its seam state equals the live one). `paper_book` now reports
`line_seed`, `line_at_halt`, `margin_at_halt`, `min_margin`, `min_margin_date`, `min_equity`.
`run_all.py` runs both variants at offset 0 for both K, prints the seam block and the halt margin in
the table, labels a halt within 2% of the book's peak a KNIFE-EDGE (charts and honesty box too).
Numbers (headline funding, 12m): COVID K0.75 csv 115,987 / live-pending 115,070 / seam-dropped
129,231 (S3 halt 11-30 on the first two at paper equity 74,486 / 74,423 vs line 75,502, i.e. -1,016 /
-1,079 = 0.9% / 1.0% of the 107,860 peak; no halt on seam-dropped, closest +805); K0.30 108,900 /
108,534 / 114,198. 2008 K0.75 125,924 / 126,286 / 126,281 (no halt, closest +19.9k). 1999 K0.75 116,600
/ 117,116 / 115,762 (S3 halt 12-08 on all three, -3,416 / -3,058 / -4,521 = 3.2% of peak: firm, not a
knife-edge). The verifier's pre-funding figures (137,713 / 152,024 / 122,126 / 138,089) are reproduced
to the dollar by the same code paths without funding. The improvement-candidate question on the S3
halt cannot be settled on this path and is not attempted. Gate tests:
`test_stress.py::test_seam_variants_pullback_only`, `test_paper_book_margin_to_line` (fail
pre-review: no `seam_variant`, no margin keys; the second pins the COVID margin to -1,015.55).

### MINOR - 'Worst UTC day' was close-to-close while the daily rail polls intrabar
Verdict: CONFIRMED and applied. Change (`stress.py`): the executor records per bar the day_start in
force, the worst intrabar equity's margin to each line and whether the rails were armed;
`worst_day_intrabar` (bar's worst equity vs the executor's own day_start) and `rail_use` (share of
the daily-loss / drawdown budget consumed) are reported next to the close-to-close day. Numbers
(offset 0, K0.75): worst intrabar day COVID -8,884 (2026-11-12), 2008 -5,026 (2027-08-07), 1999
-7,051 (2026-10-26) vs close-to-close -8,921 / -4,512 / -6,224; daily rail used 59% / 34% / 47%,
drawdown rail used 90% / 44% / 59% (one basis, the harness's own intrabar reading - COVID K0.75 offset
0: closest approach to the DRAWDOWN line 3,051 of 30,000 on 2027-05-27 20:00 with BTC funding; 4,458
(85%) without BTC funding; 8,581 (71%) with the seam trade dropped; 3,789 (87%) at offset -28). Across all offsets the
daily rail is at most 64% consumed (COVID off-14, 2027-08-04 20:00; margin 5,363 of 15,000 at K0.75,
2,152 of 6,000 at K0.30) - the verifier's 64% / $2,187 reproduced (the $35 difference is the
executor's day_start, marked at the 00:00 open, vs the verifier's previous close). No line crossed.
Gate test: `test_stress.py::test_worst_day_intrabar_and_rail_use` (fails pre-review: no
`worst_day_intrabar`, `rail_use`, `day_start_out`).

### MINOR - seam key-input discrepancy needs Casey's answer, not analysis
Verdict: CONFIRMED. Recorded as the P1 open question above and in results.json `meta.seam.s3` and the
honesty box; the +/-1k sensitivity sits in the seam block of the table (pending_live vs csv: COVID
-917, 1999 +516, 2008 +362 at K0.75). Not analysed around.

### MINOR - honesty caveat mislabelled the 2008 analogue as inside the trend leg's fit window
Verdict: CONFIRMED and applied in ADDENDUM.md item 1 and the honesty box (PREREG.md itself is
untouched). The in-sample sentence, corrected: COVID (2020) sits inside the trend leg's fit window
(2013-2021); the 2008-like window (2021-11..2022-11) sits mostly - 10 of 12 months - inside its
VALIDATION window (2022-24H1), not its fit window; 1999 (2017-18) inside the fit window; the
pullback (fitted 2024-26) is out-of-sample on all three. Gate test:
`test_run_all.py::test_honesty_box_names_the_review_items` ("validation window").

### NOTE - HW ratchets on the bar's favourable extreme before the adverse extreme is tested
Verdict: CONFIRMED; left as is (conservative, toward more halts, none fires) and stated in the
honesty box with the verifier's measurement (quanto-funded COVID K0.75: hw_end 139,255 vs 138,714
from closes; drawdown margin 9,681 vs 12,089). No number moved by this item.

### NOTE - 'S4 long stopped at the first open is a splice artefact' was mislabelled
Verdict: CONFIRMED and relabelled - the stop at t0 is not a caveat on the splice, it is what the live
book faces today. `run_all.seam_disclosure` reads the CSV: the real 2026-10-07 12:00Z bar (unclosed
at run time) printed a low of 82,733.94, which also breaks the trail 83,274.67, so the live S4 long
(80,702.77) is stopped on today's real path exactly as on every spliced path; only its FILL LEVEL
(the path's open vs the trail) is a splice choice (seam round trip -29 COVID/2008, -419 1999).
results.json `meta.seam.s4.stopped_on_real_path = true`; honesty box line. Gate test asserts the flag.

### NOTE - 12-month balance for 2008 and 1999 is the last path bar, 4h short of day 365
Verdict: CONFIRMED as a labelling item, but the reading was the WRONG WAY ROUND (re-verification,
2026-10-07): it judged exactness on the bar's OPEN. On the bar's CLOSE (exact = ts + 4h == t0 + 365 d)
the 2008 and 1999 day-365 balances ARE the exact day-365 close (365-day windows, 2,190 bars: the last
path bar closes on the instant), and it is COVID's (leap-year window, 2,196 bars) that is the bar
opening on the instant, closing 4h AFTER it; every 3m/6m/9m balance is likewise 4h after its instant.
`balances_at` now judges on the close (`shortfall_s` = target - close, negative = after); the `*`
moves from 2008/1999 to COVID; footnote, honesty line and ADDENDUM item 4 reworded. No number moved.
Gate test: `test_stress.py::test_balances_exact_flag` (updated to the close basis).

### NOTE - Variant B resume re-anchors HW/day_start to equity
Verdict: CONFIRMED; the assumption is now stated in the variant-B description (honesty box): a
plain /resume is refused while the breach is live (mirror.py L2026-2057), so after 7 days the
emulation applies /resume?reanchor=1 semantics. Never exercised: no DRAWDOWN halt fires.

### NOTE - the 'no DRAWDOWN halt' finding does not depend on the carry sleeve
Verdict: CONFIRMED and reworded (honesty box). Re-verification (SERIOUS): the first wording quoted
margins on mixed bases ($5.8k from a pre-review no-carry run, $7.0k from the pre-funding proxy run);
withdrawn. One basis, the harness's own intrabar rail reading: closest approach to the DRAWDOWN line
3,051 of 30,000 (90% used) on 2027-05-27 20:00 at COVID K0.75 offset 0 with BTC funding; 4,458 (85%)
without BTC funding; 8,581 (71%) with the seam trade dropped; 3,789 (87%) at offset -28. The 2.5/5-ATR
engine stops keep the book above the line with or without the carry sleeve; no halt fires.

### NOTE - the COVID S3 halt is a knife-edge but robust to the two perturbations tested
Verdict: CONFIRMED; the margin (-1,016 of 107,860, 0.9%) is printed next to every S3 halt (table,
charts, honesty box) and the seam variants confirm the halt survives the live PENDING state
(-1,079). No code change beyond the reporting.

### NOTE - seam volume-regime jump verified immaterial
Verdict: CONFIRMED; one line added to the splice disclosure (honesty box): rescaling the analogue
volume to today's level leaves COVID and 2008 identical to the cent and moves 1999 by -0.5k.

### NOTE - executor mechanics that make every number an upper bound are not all named
Verdict: CONFIRMED; the four items are listed in the honesty box with the direction of each bias:
(a) HALT_CONFIRM_POLLS = 3 (~60 s debounce) - the harness halts on any touch and fills at the line;
(b) post_only pullback limits rejected when they would cross - the harness fills every engine limit
(4/4 crossed live); (c) stop-market slippage in a cascade and HL mark-price vs Bitstamp last - not
modelled; (d) _reconcile_transfers can shift HW/day_start on a flat-book sleeve move - no effect here.

### NOTE - 1999 off-28 is not a crash path and sets the K0.75 12m minimum
Verdict: CONFIRMED and labelled by rule: an offset whose BTC low is shallower than half the
offset-0 low is "not a crash path" (1999 off-28: -31% vs -84%, 12m -29%; it carries an S3 halt on
01-05). The range is also printed without it (K0.75 116,600..123,023; K0.30 108,225..112,473). No
other offset is flagged (COVID offsets keep lows of -40%..-56%).

### NOTE - verified correct (recorded so no one re-runs them)
Splice returns exact on all 15 windows; first path close == today's close; unclosed bar excluded;
BTC/ETH on one anchor and grid; S4 seam state == live; paper_book == production core.Book from the
seam; bookkeeping replay |d| <= 0.04 and total == btc + carry; balances at t0+91/182/273/365d, maxDD
from start equity, worst UTC day, ranges recomputed; no look-ahead (truncation at 300/900/1500 bars
reproduces everything); daily/DD lines recomputed; DRAWDOWN-first ordering and first-cross fill
match _breach_for; caps never bind at K0.75; carry funding, sign, x1095, coverage, hysteresis, resize
rule, liq formula (8,836 today) and the margin post-check (worst ETH/liq 0.47 / 0.37 / 0.61)
recomputed; BTC arrays identical carry vs no-carry; funding CSVs clean; 15 gate tests pass (now 23).
This pass additionally reproduced, with the new code paths, the verifier's T7 funding totals, T10
proxy grid cells (118,776 / 126,406), T11 live-pending cells (137,713 / 122,126 / 138,089), CF1
seam-dropped cells (152,024 / 138,045 / 120,477) and the S3 margin (1,016) to the dollar.

## Gate tests added (each fails on the pre-review code)

| test | defect | why it fails pre-review |
|---|---|---|
| test_stress.py::test_btc_funding_per_stamp | SERIOUS BTC funding | `Executor(btc_funding=...)` was not a parameter (TypeError); COVID total -2,820.12 pinned |
| test_stress.py::test_seam_variants_pullback_only | SERIOUS/MINOR seam | `engine_trades(bars, "pending_live")` took one argument; no `seam_variant` |
| test_stress.py::test_paper_book_margin_to_line | SERIOUS knife-edge | `paper_book` info had no `min_margin` / `margin_at_halt` (KeyError); COVID margin -1,015.55 pinned |
| test_stress.py::test_worst_day_intrabar_and_rail_use | MINOR worst day | no `worst_day_intrabar`, `rail_use`, `day_start_out`, `armed_out` |
| test_stress.py::test_balances_exact_flag | NOTE 12m label | `balances_at` had no `exact` / `shortfall_s` |
| test_run_all.py::test_headline_funding_is_xbtusd_even_where_ethusd_covers | BLOCKING carry series | `funding_for` defaulted to ETHUSD for the COVID anchor; no `HEADLINE_FUNDING`, `funding_covers`, `btc_funding_from` |
| test_run_all.py::test_honesty_box_names_the_review_items | NOTEs / MINOR fit window | no `HONESTY_STATIC` |
| test_run_all.py::test_table_from_results_json | BLOCKING/SERIOUS reporting | pre-review results.json had no `headline_funding`, `runs_quanto`, `seam_range`, `rail_use`, `honesty` |

## Pending DD questions (ranked)

- P1 (decision-gating), one datum: the S3 book's 2026-10-07 04:00Z bar low AS THE LIVE ENGINE SAW
  IT. Its own /bars endpoint shows low 84,010.77, identical to the CSV and under the 84,121.28 limit,
  yet the live book reported PENDING - an open ENGINE-SIDE question (why no fill on a bar its own
  feed shows crossing the limit), not a data question. Moves: COVID K0.75 12m 115,070..129,231 and
  whether the S3 paper-book halt on 11-30 exists at all; decides whether the S3 halt is an
  improvement candidate. Status: asked (this report), 60-day expiry 2026-12-06.
- P2 (score-moving): a linear-ETH perp funding history covering 2020-03 and 2022-06 (HL launched
  2023; BitMEX ETHUSD is a quanto). Moves: the carry column by up to +20k (COVID K0.75) between the
  proxy and quanto readings. Status: not available from any reachable source; asked.
- P3 (completeness): HL BTC hourly funding for the same windows (the study uses BitMEX XBTUSD 8h as
  the proxy for the book's own funding, -2.8k / -0.5k / -5.0k at K0.75). Status: asked.

## Files

- `stress.py` - executor BTC funding, seam variants (`pullback_trades_pending_live`), paper-book
  margins, per-bar rail margins, `worst_day_intrabar`, `rail_use`, `balances_at(exact)`; run-file
  names now carry the carry source, funding flag and seam variant
  (e.g. `COVID_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv.json`), so the verify
  scripts' hard-coded old names no longer resolve (they are historical artefacts, not re-run).
- `run_all.py` - XBTUSD headline + quanto column, BTC funding fed to every run, seam / no-funding /
  no-engine-halt sensitivities, crash-path rule, honesty box, table, charts.
- `carry_sleeve.py` - unchanged (no finding against it).
- `test_stress.py` (+5 tests), `test_run_all.py` (new, 3 tests), `test_carry_sleeve.py` (unchanged).
- `ADDENDUM.md` (registration changes), `REVIEW.md` (this file), `results.json`, `fig_*.png`, `runs/`.
