# B.5 Enhanced: structural changes to raise Sharpe and Sortino - PRE-REGISTRATION (2026-11-19)

Frozen before any arm is run. Later changes go in DEVIATIONS.md, never silently. Research only: nothing here
changes the live book, a gate or a symphony. Approved by Casey 2026-11-19: the six ideas below; leverage up
to about 1.3x gross may be studied; no bot data (the whole-barbell idea is out); ETFs only as holdings
(mutual funds and factor series may stand in for history); 25% single-position cap stays.

## Base
Live book L: AVUV 23.5, PHYS 23.5, QUAL 15.3, KMLM 14.1, AVDV 11.8, AVEM 5.9, TAIL 5.9. Live rule, engine,
timing, costs, tapes T1/T2 and END = 2026-11-17 are the overlay study's (b5_overlay_2026-11/code, independently
verified), reused unchanged. Sleeves: EQUITY = AVUV, QUAL, AVDV, AVEM; GOLD = PHYS; TREND = KMLM; HEDGE = TAIL.

## Windows
EXT 2007-06-01..END; DISC = to 2017-04-06; CONF = 2017-04-07..END (real TAIL). An arm whose new instrument
starts later is judged on its own window (first real or gate-passing stand-in return..END), split at its
midpoint for the two-halves test, and that is printed beside its verdict. Books containing KMLM cannot go
before 2007 honestly; the separate 2000-02 test covers earlier history.

## Primary arms (one per approved idea; the max-T family is exactly these six)
P1 RISK-BALANCED WEIGHTS. Each year-end: sleeve targets = equal risk contribution across EQUITY, GOLD, TREND
   from the expanding-window daily covariance of T-bill-excess sleeve returns (tape start to that date);
   TAIL stays 5.9%; equity keeps live internal proportions; target = halfway between live and that answer;
   any position above 25% is cut to 25% and the excess goes to EQUITY. Held for the next calendar year.
P2 P1 SCALED TO THE LIVE BOOK'S VOLATILITY. Each year-end: gross = min(1.30, expanding volatility of L /
   expanding volatility of P1), both from realized returns to that date; every P1 weight times gross; the
   borrowed part pays T-bills + 0.50%/yr.
P3 TAIL -> BTAL, full swap (5.9%).
P4 TREND BLEND at the same 14.1%: half KMLM, half DBMF (each on its stand-in chain before it exists).
P5 DURATION: 10% IEF funded pro-rata from the four equity legs.
P6 LOWER-VOLATILITY EQUITY CORE: 8 points of AVUV moved to QUAL (AVUV 15.5, QUAL 23.3).

## Secondary arms (reported, never adjudicate, outside the family)
S1b full sleeve risk parity (no halfway shrink), trend held as the two-fund blend, gold capped at 25%.
S1c P1 with downside semi-covariance in place of covariance.
S2b L itself at 1.20x gross (shows what leverage alone does: it should NOT raise Sharpe).
S3b TAIL half into BTAL. S4b trend blend at 20%, funded 2.95 from TAIL and 2.95 from AVUV.
S5b 5% IEF + 5% TIP. S5c L plus 10% IEF on borrowed money (T-bills + 0.50%).
S6b the 8 points to USMV (from 2011-10). S6c the 8 points to large value (AVLV, DFLVX before 2021-09).
E7 5% UUP funded from TAIL. E9 QUAL replaced by the CBOE zero-cost collar index CLLZ, and by PPUT
   (indices, not funds: no fee or tracking cost; exploratory only).
COMBO (the only out-of-sample element): the book that combines every primary arm whose Sharpe AND Sortino
   differences vs L are both positive on DISC, evaluated on CONF only. Components chosen on DISC alone.
G13 arithmetic only: realized PHYS vs GLDM return gap since GLDM's start.

## Stand-ins and gates (run before any arm; a failed gate removes that history, it is never patched)
| instrument | before it exists | gate on the overlap |
|---|---|---|
| BTAL (2011-09) | a + b x AQR US betting-against-beta (daily) + c x market excess, fitted on BTAL | daily corr >= 0.70, monthly >= 0.80, else P3 starts 2011-09 |
| DBMF (2019-05) | AQMIX (2010-01), then RYMFX | monthly corr AQMIX vs DBMF >= 0.60 |
| IEF, TIP, UUP, USMV | none needed inside their windows | - |
| AVLV (2021-09) | DFLVX | monthly corr >= 0.90 |
| financing | T-bills + 0.50%/yr | GDE and RSST each within 1.5%/yr of their synthetic recipe (0.9 SPY + 0.9 gold; 1.0 SPY + 1.0 trend) at that spread, else the spread is raised to the fitted value |
Costs one-way: config values; new ETFs BTAL 10, DBMF 10, IEF 2, TIP 3, USMV 3, AVLV 5, UUP 5 bps.

## Comparators
1. L. For a static mix, adding T-bills changes neither Sharpe nor Sortino (both are measured over T-bills),
   so the Sharpe and Sortino difference vs L IS the same-volatility comparison.
2. For CAGR and drawdown: L scaled to the arm's realized volatility (with T-bills, or borrowed at T-bills + 0.50%).
3. SPY + T-bills at the arm's realized volatility (monthly rebalanced), the benchmark from spy_compare.json.

## Statistics
T-bill-excess Sharpe and Sortino (downside deviation of excess returns, target 0), CAGR, volatility, max
drawdown, ulcer, worst 252 days. Paired circular block bootstrap of arm minus L for Sharpe and for Sortino,
21- and 63-day blocks (the larger p decides), 4,000 draws, seed 20261119, same draws across arms. One-sided
single-step max-T over the six primary arms, separately for Sharpe and Sortino. Minimum detectable
difference printed beside every verdict. Stress: costs x2; financing at T-bills + 1.50% for P2; both tapes.

## Verdicts (fixed now)
IMPROVES: on EXT (or the arm's own window) Sharpe and Sortino differences vs L both > 0, max-T adjusted
  p < 0.10 on BOTH, both positive in both halves, both still positive at costs x2 (and at the financing
  stress for P2), on both tapes.
CANDIDATE: both differences positive on the full window and in both halves on tape 1, not significant.
NO: anything else.
P2 additionally reports CAGR vs L and vs SPY + T-bills at its volatility; it IMPROVES only if P1's ratio
gain survives financing (P2 Sharpe and Sortino > L) AND its max drawdown is no deeper than L's.
If any arm IMPROVES: stop and bring Casey a proposal (weights, Composer and IBKR-mirror changes, shadow run,
kill criteria) before anything else.

## Registered prior
The 25% cap makes P1 land near equity 46 / gold 24 / trend 24 / TAIL 6, close to the "KMLM 25%" arm the
overlay study already measured at +0.02 Sharpe. So: P1 +0.02 to +0.05 Sharpe, CANDIDATE at best (the Phase 1
list said +0.05 to +0.10; that ignored the cap). P2 turns it into about +0.5 pt/yr CAGR, not +1.0 to +1.5.
P3 is the most likely to help on 2017+ and the most likely to disappoint in the 2009 rebound. P4 small.
P5 negative since 2017 (2022). P6 small positive since 2017, negative on DISC. Nothing reaches IMPROVES.

## Not modelled
Taxes (none), intraday execution, margin calls or forced deleveraging inside a day, futures roll mechanics,
borrow availability, option-structure fees for E9, fund closures.
