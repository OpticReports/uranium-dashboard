# Pre-registration: is there a better time frame, signal form or macro input for the KMLM switcher? (2026-11-20)

Written before any analysis script in this folder was run. Frozen at the commit that adds this file.

## The owner's question (Casey, 2026-11-20)
"The KMLM switcher seems to revolve around 10 or two day moving averages or RSI ... is there a superior
time frame to be looking at when executing, flipping this bullish or bearish, that would improve
returns? ... improve the return on this symphony individually, and then weigh it against the collective
... it doesn't have any sort of macro outlook ... purely technical." Added the same afternoon: "check
around EMAs and SMAs, see if there is a superior window with these as well."

## What is being varied
The 75% "KMLM switcher" block of `YPTSJFJwD2ZKfAeYJUbW` (`symphonies/KMLM.md`; tree
`fixtures/approved/kmlm-MVfHI8Og.json`). The 25% VIX sleeve is never touched (addendum 56 covers it).
- the SWITCH: RSI(10) of XLK > RSI(10) of KMLM -> risk-on (bottom-2 by RSI(10) of TECL/SOXL/SVIX),
  else risk-off (top-1 by RSI(10) of SQQQ/TLT);
- the POPS: RSI(10) above 79-80 on eleven equity funds (75 for XLP) -> UVXY;
- the DIPS: RSI(10) under 30 on TQQQ/SOXL/SPXL (25 for LABU) -> that fund (TECL for TQQQ).

## Seen before this file was written (disclosed; counts as 27 trials)
The scouting pass ran 27 in-sample cells on 2023-04..2026-11-04 to check the simulator's mechanics, and
I have read them: switch-only N in {5,7,8,9,10,11,12,14,20} gave CAGR 140/152/162/192/212/213/231/234/
242% with max drawdown 41.5/34.3/34.3/34.3/24.5/32.1/32.1/32.1/34.1 (N=10 is the drawdown minimum, not
the CAGR maximum); changing every 10-day window in the block with thresholds fixed gave a jagged
surface (132..248%); switch plus both ranked picks at N=12: 253% / 26.9%. Also seen: add. 24 ("the live
thresholds sit on an in-sample performance PEAK"), add. 11b (a same-family symphony's switch windows:
out-of-sample plateau with in/out rank INVERSION, "parameter not tunable"), add. 33 (rate veto on the
switch: best dSharpe -0.02), add. 2 and 39 C1 (VIX-term overrides: no effect or worse), add. 42 (vol
and trend gates on KMLM, in sample only). Nothing below has been computed.

## Data tiers (labelled on every number)
- A  2023-04-19 .. latest final close: every fund real. Partly seen (above).
- B  2020-12-02 .. 2023-04-18: the real KMLM fund drives the switch; SVIX is modelled before 2022-03-30
  and ZVOL throughout (repo's long panel). NOT seen by anyone. The original author fitted the rule on
  2022, so B favours the live rule: a challenger that wins here wins against the grain.
- C  2007-02-22 .. 2020-12-01: the switch reads RYMFX in place of KMLM (agrees with the real flag on
  about 84% of days). A different signal: used for the SHAPE of a surface only, never to select.
- D  before 2007: proxy flag "barely better than a constant" (add. 47). Not used.

## Simulator and its gates (no result is read until these pass)
`shadow_runner.Shadow` targets + the 10-point corridor path + cost 5.856 bps x turnover on the trade day.
G1 at the live parameters it reproduces Composer's own backtest (`research/zvol_2026-11/data/bt_KMLM.json`):
   holdings within 1.5% on every session and daily-return correlation >= 0.9999.
G2 a variant builder changes ONLY the nodes it names: at N=10 every variant's `tree_sha1` equals the
   approved tree's; the VIX sleeve's subtree hash is unchanged in every variant.
G3 both window encodings in the tree (`*-fn-params.window` and `*-window-days`) are edited together.
G4 three variants (one RSI window, one SMA form, one EMA form) are backtested on Composer itself
   (`composer-api.py backtest-def`, read-only) and must match the simulator: correlation >= 0.999 and
   the same holdings on >= 97% of sessions. If the EMA form fails G4, EMA results are reported as
   research-only and cannot be a candidate.

## The families (every cell is declared here; nothing is added after a look)
F1 switch lookback, RSI: N in {3,5,7,8,9,10,11,12,14,17,20,25,30,40,60}, the same N on both sides.
   F1a switch only; F1b switch and both ranked picks at N. (30 cells, one of them the live rule.)
F2 switch ensembles (no window is chosen: the flag is voted): majority of N in {8,10,12}; majority of
   {5,10,20}; majority of {7,10,14,20,30}. Research form (a vote is not one Composer condition); the
   Composer form is an equal-weight split of the block across the member windows, also run. (6 cells.)
F3 pops and dips at N in {5,7,14,20} with QUANTILE-MATCHED thresholds: for each fund the threshold at
   N is the one exceeded as often as the live threshold at N=10 over that fund's history to 2020-12-01.
   F3a pops only, F3b dips only, F3c both. (12 cells.)
F4 the switch as relative momentum: return of XLK over N days > return of KMLM over N days,
   N in {5,10,20,40,60,120}. (6 cells.)
F5 the switch as price against a moving average of XLK alone: price > SMA(N), and price > EMA(N),
   N in {10,20,50,100,200}. (10 cells.)
F6 the switch as a moving-average crossover of XLK alone: fast > slow for (5,20), (10,20), (10,50),
   (20,50), (50,200), SMA and EMA. (10 cells.)
Total 74 cells + the 27 seen = 101 trials for every multiplicity statement.
F4-F6 keep the ranked picks and everything else as live.

## What counts as "a superior time frame" (all five, fixed now)
1. On A and B pooled (real KMLM flag), its mean daily log-return minus the live rule's is positive with
   a family-wise p < 0.10 from a max-statistic stationary bootstrap over ALL 74 cells (mean block 10,
   5,000 draws, studentised).
2. It beats the live rule on point estimate in A and in B separately.
3. Plateau: both of its neighbours on its own grid also beat the live rule on A+B (an isolated best
   cell is a peak, not a time frame). Ensembles are exempt from 3 and must instead beat the median of
   their members.
4. Its max drawdown on A+B is not worse than the live rule's by more than 5 points.
5. At twice the cost (11.7 bps) conclusion 1's point estimate is still positive.
Reported beside it, not gating: the tier-C surface (same sign?), the share of decision days within one
unit of the flip (knife-edge exposure), turnover, probability of backtest overfitting (CSCV over the
74 x T matrix), and the deflated Sharpe at 101 trials.
If no cell passes: the answer is "no superior time frame is supported", and the report says how far the
live rule is from its neighbours (is N=10 special, or one point on a flat surface?).
"The live rule is fragile" is SUPPORTED, separately, if more than a third of F1a cells differ from it by
more than 50 points of CAGR on A in either direction (add. 24's finding, now for windows).

## Macro (beyond price technicals)
Mechanism first, then the test. Six pre-named daily, point-in-time inputs (lagged one session; OFR two):
 M1 credit appetite: HYG/IEF ratio above its 50-day average (credit leads equity stress);
 M2 financial stress: OFR Financial Stress Index below zero;
 M3 stock-bond regime: 60-day correlation of SPY and TLT daily returns below zero (when it is positive,
    TLT is not a refuge: it is one of the two risk-off funds the switch can pick);
 M4 dollar: broad dollar index below its 50-day average (a rising dollar is a risk-off impulse);
 M5 curve: 10y minus 3m above zero (inverted curves precede the regimes trend-followers lead);
 M6 real-rate shock: 10y TIPS yield 20-day change below +25 bp.
Not re-run (already answered): VIX term structure (add. 2, 39 C1), rate-hike vetoes (add. 33),
CAPE (add. 26, 40), vol/VIX gates on the long leg (add. 42, 54.1).
Step 1, on history far longer than the tree's (2010-2026 for the 3x funds): does the input's state
predict the next 1, 5 and 21 sessions of (a) the risk-on basket (equal TECL/SOXL) minus T-bills, and
(b) risk-on minus risk-off (SQQQ/TLT equal)? Newey-West regression of the forward return on the state,
plus walk-forward out-of-sample R2 against the expanding mean. An input "works" only if Holm-adjusted
p < 0.05 across the 6 x 3 x 2 tests AND out-of-sample R2 > 0. Mirror check: the same test with the
input circularly shifted (1,000 shifts).
Step 2, only for inputs that work: two tree variants each, declared now: CONFIRM (risk-on needs the
live flag AND the macro state) and, for M3 only, TLT-GUARD (when the state is off, risk-off picks SQQQ
or cash, not TLT). Judged by the same five conditions, added to the trial count. If no input works,
step 2 is not run and that is the finding.

## The collective
For the live rule, the three ensembles, and any cell that passes: the three-engine book at 34.1 / 34.1
/ 31.8 (HG and SLEEVE from Composer's own backtests, unchanged), daily-fixed weights and drift with the
44% cap, on 2023-04-19 onward. CAGR, volatility, Sharpe over T-bills, max drawdown, 5% daily CVaR, worst
month, each as a difference from the live book with a 90% paired interval (stationary bootstrap, mean
block 10, 2,000 draws). A symphony-level gain that does not show at the book is reported as such.

## Edge found on the way
Any conditional return or asymmetry that appears, asked for or not, is reported as a candidate edge with
its sample size, its mirrored or placebo check, and what it would take to use (CLAUDE.md, 2026-11-05).

## Honesty box (applies to every number)
In sample; none is a forecast. Three and a half years of all-real history, about 25 switch flips a
year, one bear market (2022, on which the author fitted the rule). Decisions are simulated at the
close; Composer decides about 15:51-15:54 and 8 of 83 live KMLM sessions were knife-edges. Modelled
funds in B and C. Not modelled: intraday paths, taxes, capacity, any fund closing. A change to the live
symphony is the owner's decision, lands on both brokers in one change set with the parity check, and
goes into the logic book (`symphonies/why/KMLM.md`) with a new approved version.
