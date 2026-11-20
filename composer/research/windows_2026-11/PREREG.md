# Pre-registration: windows and moving averages in Holy Grail and the crash sleeve, and the book (2026-11-20)

Owner, 2026-11-20: "We're all running the same sort of research around daily moving averages, EMAs, SMAs,
et cetera, on our holy grail instance. Run this report and investigation on the other symphonies and the
set to see if there's any improvement by variance of windows." Written before any variant of HG or SLEEVE
was simulated. No scouting cells were run. Frozen at the commit that adds this file.

Seen before: addenda 19b and 44 (HG trend gates at 150/200/250 days and others), 30 (HG cash route), 45 (the
gate on adjusted prices), 4/4b (sleeve weights), and addenda 57/58 on the KMLM switcher (no variant better;
9-12 days level; short windows and moving averages worse). HARV is not studied: it is being closed (stub
only since 2026-11-19).

## Engines and what is varied
Only windows and the simple/exponential form of an average. No ticker, threshold level, branch order or
weight is changed, except that a threshold is re-set to fire as often as the live one where a window
change would otherwise change how often the test fires ("matched", below).

**HG** (live: TQQQ 10d SMA > 20d SMA; TQQQ RSI10 > 80; TQQQ RSI10 < 30; SOXL RSI10 < 30; TQQQ price < 20d
SMA; SPY > 200d SMA on both trend baskets; four picks ranked by RSI10). 89 cells:
- HA the trend crossover pair: SMA (3,10) (5,10) (5,20) (8,21) (10,30) (10,50) (15,30) (20,50) (20,100)
  (50,200); EMA the same ten and (10,20). 21.
- HB the cash test "TQQQ below its N-day average": SMA 5, 10, 15, 30, 50, 100; EMA 5, 10, 15, 20, 30, 50,
  100. 13.
- HC both trend tests scaled together (10/20/20 times k): SMA k = 0.5, 1.5, 2, 3, 5; EMA k = 0.5, 1, 1.5,
  2, 3, 5. 11.
- HD the SPY gate: SMA 50, 100, 150, 250, 300; EMA 50, 100, 150, 200, 250, 300. 11.
- HE the RSI window of the three threshold tests together, N = 5, 7, 8, 9, 11, 12, 14, 17, 20: with
  matched thresholds (HEm, 9) and with the live 80/30/30 (HEr, 9). 18.
- HF the RSI window of the four ranked picks: 3, 5, 7, 8, 9, 11, 12, 14, 17, 20, 30. 11.
- HG every RSI window together (matched tests and picks): 5, 7, 14, 20. 4.

**SLEEVE** (live: RSI8 of IEF < RSI45 of PSQ; RSI20 of LABD and of TMV < RSI10 of KMLM; a ladder of 1-day
returns and RSI tests on CORP 15/16, PEJ 14, KIE 10/10/14, LQD 12/14; picks ranked by 1-day return). The
sleeve has no moving average, so only windows are varied. 45 cells:
- SA the IEF window: 4, 5, 6, 7, 9, 10, 12, 14, 20. 9.   SB the PSQ window: 20, 30, 40, 50, 60, 90. 6.
- SC both scaled: (4,22) (6,34) (10,56) (12,68) (16,90). 5.
- SD the LABD and TMV window: 10, 14, 17, 25, 30, 40. 6.   SE the KMLM window: 5, 7, 14, 20, 30. 5.
- SF every RSI window of the ladder times k = 0.5, 0.7, 1.4, 2 (rounded, at least 2): matched thresholds
  (SFm, 4) and live thresholds (SFr, 4). 8.
- SG the ladder's 1-day returns over N = 2, 3, 5 days with matched thresholds (3); the picks ranked by
  the 2, 3, 5-day return (3). 6.

**Matched thresholds** are set on the MODEL years only (below), so the verdict sample never sees them:
the threshold at the new window that was crossed as often as the live threshold at the live window.
A live threshold never crossed in those years stays unreachable at the new window.

## History (CLAUDE.md "SYNTHETIC HISTORY BEFORE SHORT SAMPLES")
Long panel `research/longrun/long_panel.build_long_prices()` (funds before launch rebuilt from their index
times leverage, bond funds from older mutual funds, sector funds from industry portfolios, VIX funds from
the VIX curve), with KMLM = the addendum-58 synthetic to 2020-12-01 chained to the real fund's corrected
total return; fresh Yahoo closes for the real years. Per engine, three stretches, never pooled across the
model line:

| | MODEL (shape only) | REPLICATION | REAL |
|---|---|---|---|
| HG | 1991-04-01..2006-07-17 | 2006-07-18..2015-08-31 | 2015-09-01..2026-11-19 |
| SLEEVE | 1994-06-01..2008-01-31 | 2008-02-01..2023-01-31 | 2023-02-01..2026-11-19 |

HG REAL: every fund trades (LABU, the last, from 2015-05). HG REPLICATION: VIX funds built from the real
VIX curve (from 2006-07-18), leveraged funds are index times leverage until launch. SLEEVE REAL: from BOXX's
launch, as Composer's own backtest. SLEEVE REPLICATION: BOXX is T-bills, KMLM is the synthetic to 2020-12,
LABD/CORP/SVXY/UVXY/SOXS are modelled until their launches (2010-2015). MODEL: VIX funds are a model of a
market that did not trade or of a fitted curve; several funds are proxies.
The addendum-58 synthetic is used in the sleeve only if its independent review clears it for 2008-2020; if
not, SLEEVE REPLICATION starts 2020-12-02 and the earlier years move to MODEL.

## Gates before any result is read
G1 the live HG and SLEEVE trees in this simulator against Composer's own stored backtests
   (`zvol_2026-11/data/bt_HG.json`, `bt_SLEEVE.json`): holdings the same on at least 98% of sessions and
   daily-return correlation at least 0.999.
G2 three variants per engine backtested on Composer itself (read-only ad-hoc backtest, nothing saved)
   against the simulator, same bars; one of HG's is an EMA form, which the simulator reads from an
   injected flag. If Composer cannot be reached the gate is reported as NOT RUN, not as passed.
G3 a tree-form and a flag-form of the same SMA variant agree on every session.
G4 no real series in a REAL stretch has more than 5 consecutive unchanged closes (stale data).

## Simulation
`kmlm_2026-11/ksim.simulate` (shadow_runner's evaluator), daily rebalance to target (both trees: no
corridor), 5.856 bps per unit of turnover on the trade day, decisions at the close.

## Verdict rule (per engine; the rule of addendum 58, DEVIATIONS item 12)
On REPLICATION + REAL joined, a variant passes only if all five hold: (1) ahead of the live rule with
family-wise p < 0.10 across that engine's cells (max-statistic stationary bootstrap, mean block 10, 5,000
draws, studentised, centred); (2) ahead in REPLICATION and in REAL separately; (3) its grid neighbours also
ahead; (4) max drawdown no more than 5 points worse than the live rule's in each stretch; (5) still ahead
at double cost. Beside it, not gating: the same t with each stretch standardised to equal variance; the
MODEL-years result; the smallest gain the test could see; group averages (shorter / longer / EMA vs SMA).
For the SLEEVE, a hedge, a passing variant must also not pay less than the live sleeve on the worst 5% of
days of HG and KMLM combined.

## The book
Daily-fixed weights 34.1 / 34.1 / 31.8 (HG / KMLM / SLEEVE, POLICY "Allocation") on the days all three
have a simulated return. Reported for the live book and with each engine's best-by-t variant and each
family's average swapped in: change in yearly return and max drawdown with a 90% bootstrap interval.
Nothing at book level is a verdict unless the variant passed on its own engine.

## What each outcome licenses
- A variant passes: reported as a CANDIDATE with its numbers, its failure cases and what a live change
  would involve (both brokers, the logic book). No live change without the owner.
- None passes: "no evidence for a change", with the smallest detectable gain stated.
- Any conditional return or asymmetry met on the way is listed as a candidate edge with its sample size.

## Honesty box
In sample throughout; none of it a forecast. HG's rules were chosen by its author on roughly 2015 on, so
REAL flatters the live rule and the earlier stretches are the fairer test. 134 cells across two engines;
each engine is corrected for its own count. Not modelled: intraday paths, taxes, capacity, the knife-edge
of ranked picks. Measurement basis: daily mark-to-market of the simulated symphony.
