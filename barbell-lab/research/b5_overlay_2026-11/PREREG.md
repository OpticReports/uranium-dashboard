# B.5 Enhanced: entry / exit / stop / profit-harvest overlays - PRE-REGISTRATION (2026-11-18)

Frozen before any overlay result exists. Additions after this commit are logged in DEVIATIONS.md, never silently.
Research only. Nothing here changes the live book, a gate or a symphony.

## Question (Casey, 2026-11-18)
B.5 Enhanced now trades on IBKR ...3321. Is there a rule for when to exit, re-enter, stop out or harvest
profit - on the book as one unit or on its individual legs - using price, RSI, volume, macro and other
indicators, that improves Sharpe by cutting drawdown? Also: which legs do not pull their weight?

## The book under test
Live targets (v1.2 without CAOS; verified against ...3321 positions 2026-11-18, all within 0.3pt):
AVUV 23.5, PHYS 23.5, QUAL 15.3, KMLM 14.1, AVDV 11.8, AVEM 5.9, TAIL 5.9. Cash leg for every overlay: BIL.
Live rule reproduced as the BASE: month-end check, +/-20% relative band, whole book back to target,
fill next trading day, 12-month calendar fallback, one-way costs from config/backtest.yaml (BIL 1 bp).
Groups: RISK = AVUV, AVDV, AVEM, QUAL, PHYS. EQ = AVUV, AVDV, AVEM, QUAL (56.5%). HEDGE = KMLM, TAIL (never timed).

## Data and windows
Yahoo v8 adjusted closes + volume (KMLM 2022-12-28 distribution corrected per config/data.yaml), FRED
(DTB3, BAA10Y, T10Y3M, DFII10, DTWEXBGS, UNRATE), CBOE/Yahoo VIX and VIX3M, Shiller CAPE (monthly).
END = 2026-11-17 (last completed close). Returns are chained, never levels.
- Config-declared proxies: AVUV<-DFSVX, AVDV<-DISVX, AVEM<-DFEMX (to 2019-10), PHYS<-GLD (to 2010-03), KMLM<-ASFYX (to 2020-12).
- Study stand-ins (declared here, flagged in every table that uses them): KMLM<-RYMFX before ASFYX has data;
  QUAL<-SPY before QUAL's first return; TAIL<-BIL before TAIL's first return (earns bills: omits both the bleed and the crisis payoff).
- EXT = 2007-06-01..END (includes the GFC). DISC = EXT start..2017-04-06 (stand-in era).
  CONF = 2017-04-07..END (real TAIL; config-declared proxies only). Reported: EXT, DISC, CONF.
- LEG tier (secondary, long history): each RISK leg alone, 1995-01-03..END (gold from GLD's first return, 2004-11),
  cash = DTB3 before BIL.

## Timing convention (no look-ahead)
A signal uses closes through day t and trades at the close of day t+1 (the live "fill next trading day").
Monthly rules evaluate on the last trading day of the month. Macro series are lagged by their publication
delay: FRED dailies 1 trading day; UNRATE and CAPE one full month (current-vintage data: revisions NOT modelled).
Percentile thresholds are expanding-window only. Book-level signals read the BASE book's own NAV.
Engine: weights drift daily; the whole book trades to the current target vector when (a) a rule changes the
target (continuous rules: when any leg's target moves >= 0.05 of book, or at month-end), (b) the month-end
band check breaches, (c) the calendar fallback fires.

## Arms (53 timing arms; every one also run MIRRORED as a diagnostic)
BOOK - whole book <-> BIL (exposure e):
- B1-B3 NAV > SMA 50/100/200 (daily). B4 NAV > 10-month SMA (monthly).
- B5-B6 trailing 126d / 252d return > BIL's (monthly).
- B7-B10 trailing stop 4/6/8/10% below the peak since entry; re-enter when NAV > SMA100.
- B11-B14 same stops; re-enter after 21 trading days out.
- B15 graded: e = 1 / 0.5 / 0 for drawdown from the 252d high above -4% / -4..-8% / below -8%.
- B16 harvest: e = 0.5 while NAV/SMA200-1 > its expanding 90th percentile (>= 504 obs).
- B17-B18 harvest: e = 0.5 from RSI14 > 70 (80) until RSI14 < 50.
- B19 harvest: e = 0.5 while trailing 126d return > its expanding 90th percentile.
- B20-B21 vol target 8% / 10% on 20d realized vol, cap 1.0.
ASSET - each RISK leg on its own signal, off-weight to BIL unless stated:
- A1 leg > SMA200 (daily). A2 leg > 10-month SMA (monthly). A3 leg 252d return > BIL's (monthly).
- A4 as A1 but off-weight redistributed pro-rata to the on RISK legs (each capped 1.5x target, rest BIL).
- A5-A7 per-leg trailing stop 8/12/16%; re-enter when leg > SMA100.
- A8 per-leg volatility stop: 2.5 monthly sigmas (60d vol) below the peak since entry; re-enter > SMA100.
- A9 per-leg harvest: half weight from RSI14 > 70 until < 50.
- A10 A1 on EQ legs only. A11 A1 on PHYS only.
- A12 volume distribution: leg off when 20d down-day volume / up-day volume > 1.5 AND leg < SMA50; on when either clears.
- A13 volume climax: leg off for 10 trading days after a down day with 60d volume z-score > 3.
  (Volume comes from the leg's ETF when live, else IWN / SCZ(EFA before SCZ) / EEM / SPY / GLD.)
- A14 relative momentum tilt (monthly): top-2 RISK legs by 12-1 momentum x1.25, bottom-2 x0.75, RISK total unchanged.
- A15 A1 with a +/-2% buffer around the SMA.
MACRO - EQ legs <-> BIL unless stated:
- M1 SPY < SMA200. M2 VIX > VIX3M. M3 VIX > 30 (back on < 25).
- M4 BAA10Y > its 252d SMA + 0.25pt. M5 HYG/IEF total-return ratio < SMA200. M6 T10Y3M < 0.
- M7-M8 EQ x0.5 while CAPE > its expanding 80th / 90th percentile (history from 1881).
- M9 EQ off when CAPE > expanding 80th percentile AND SPY < SMA200.
- M10 UNRATE > its 12-month SMA. M11 M10 AND SPY < 10-month SMA.
- M12 AVDV+AVEM off when DTWEXBGS > SMA200. M13 PHYS off when DFII10 > its 126d SMA + 0.25pt.
- M14 EQ off when >= 2 of {M1, M2, M4, M10} are on. M15 graded: 1 flag -> EQ x0.5, >= 2 -> off.
- M16 EQ off May-October (seasonal placebo). M17 M14 applied to the whole book.
STRUCTURAL (static, not timing, outside the timing family): book/BIL 90/10, 80/20, 70/30; TAIL 0/10/15%;
KMLM 0/20/25% (rest pro-rata); leave-one-leg-out x7.
LEG tier rules: SMA200, 10-month SMA, 252d TSMOM, 12% stop/SMA100, RSI70 half-trim.
SIGNAL ISOLATION (descriptive, LEG tier): forward 5/21/63d leg returns conditional on each signal state vs unconditional.

## Comparators
1. LIVE: the fully-invested BASE book.
2. MATCHED CONTROL (decides Sharpe, Calmar, drawdown): a static band-rebalanced book holding the arm's
   time-averaged target weight vector (BIL included). An overlay that only holds less risk must not be scored
   as skill (round-7/8 lesson). Residual exposure mismatch is printed.
3. TIMING PLACEBO: the arm's own target path circularly shifted by 200 random offsets (>= 63d): same exposure,
   same spell lengths, same switch count, no information. The arm's percentile in that distribution is its timing skill.
4. MIRROR: the opposite rule (EDGE rule: an inverted result is a finding too).

## Statistics
BIL-excess Sharpe decides (rf=0 never adjudicates). Also CAGR, vol, max drawdown, Calmar, ulcer, worst 252d,
average exposure, switches/yr, turnover, cost drag. Paired circular block bootstrap of the difference vs the
matched control: 21d blocks, 4,000 draws, seed 20261118, same block starts across all arms (63d blocks as sensitivity).
Multiplicity: single-step max-T across all 53 timing arms; DSR with N = 106 (arms + mirrors).
Stress on anything that passes or nearly passes: execution lag (same close, +1 primary, +2, +5), costs x2 and x4.
Walk-forward ("what optimizing would have paid"): each year-end from 2010, pick the arm with the best
expanding-window Sharpe (second run: best Calmar), hold it the next calendar year, stitch, compare with LIVE.

## Verdict rules (fixed now)
- SURVIVES (Sharpe edge): Sharpe difference vs matched control > 0 on EXT with max-T adjusted p < 0.10, positive in
  BOTH DISC and CONF, timing-placebo percentile >= 90, and still positive at +2 days lag and x2 costs.
- DRAWDOWN TOOL (weaker, labelled as such): max drawdown better than the matched control by >= 2 pts in BOTH DISC
  and CONF, CAGR within 0.5 pt/yr of the control on EXT, placebo percentile >= 90 on drawdown, holds at +2 days lag.
- Otherwise NOTHING SURVIVES. The walk-forward result is reported whatever it is.
- CANDIDATE EDGE: any conditional return, mirror result or by-product asymmetry with its n, placebo and what using it would take.

## Registered prior
Trend and stop rules will cut the 2008 drawdown and give some of it back in 2020 (V-shaped); most of the
drawdown gain will be exposure, not timing; no arm will clear the max-T Sharpe bar; CAPE will not time this
book; the hedge legs (KMLM, TAIL) will look worst stand-alone and best in the leave-one-out drawdown column.

## Not modelled
Taxes (Act 60: none), intraday stops (closes only), partial fills, IBKR minimums, PHYS premium/discount beyond
what its price already carries, option-based protection (no option data), data revisions to UNRATE/CAPE.
