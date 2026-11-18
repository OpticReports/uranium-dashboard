# Pre-registration: is the volatility harvester (ZVOL) worth its capital? (2026-11-18)

Written before any analysis in `analyze.py` was run. Frozen at the commit that adds this file.

## The owner's thesis (Casey, 2026-11-18)
"This ZVOL strat is really just not worth the returns and worth the risk ... it's been a dog this entire
time. It's either not flipped on right when volatility is around, and it just ends up being a cost
center." Proposed action: move the harvester's money into the KMLM switcher. Alternative: refine it if
it can improve CAGR or drawdowns.

## What "the volatility strategy" is
One rule held twice: HARV (`ORQNCfZnA18wmsMWVhf8`, ~$37.5k) and the 25% "VIX sleeve" inside the KMLM
symphony (`YPTSJFJwD2ZKfAeYJUbW`, ~$23k). Nine voters on Wilder RSI(SPY, 2..10), weights
36/16/8/8/8/8/8/4/4: RSI < 25 -> ZVOL (PULS if RSI(UVXY,14) > 70); RSI > 80 -> VXZ; else PULS. No HYG
condition exists in any saved version, despite the name.

## Seen before this file was written (disclosed)
- Live: Composer shows HARV time-weighted -1.0% from 2026-07-22 to 11-17 (84 sessions), KMLM symphony
  +30.8% from 07-07 with a 36% live drawdown.
- Backtest headline stats 2023-04-19..2026-11-17: HARV +23.2%/yr, Sharpe 1.97, maxDD 9.5%; pure switcher
  +538%/yr, maxDD 49% (2022-04+); KMLM symphony +214%/yr, maxDD 37.6%.
- ZVOL total return by calendar year (+52% in 2023 from 04-19, +8.5%, -11.4%, +5.0% YTD) and that its
  price return (-57%) differs from its total return (+56%) because of $0.485 monthly distributions.
- ZVOL tracks -1x my futures-built mid-term index (beta 0.93-1.00 by half-year).
- The digest of prior addenda (2, 11, 12, 13, 16, 23, 25, 27, 31, 34, 39, 47, 51, 54.4): every prior
  verdict was KEEP, several on a guarded synthetic history for a guard that was never live.
Nothing below has been computed yet: no leg attribution, no placebo, no counterfactual book, no
predictive regression, no refinement.

## Questions, tests and what counts as an answer

Q1. LIVE: has it been a cost centre in real dollars?
- Dollar P&L and time-weighted return of HARV since 07-22 and of the VIX sleeve inside KMLM since 07-07
  (sleeve = the symphony's PULS/ZVOL/VXZ holdings from the daily snapshots), measured two ways:
  as Composer displays it, and with ZVOL/PULS distributions that were paid to account cash added back.
- Against: T-bills (BIL) on the same dollars; the same dollars in the switcher part of KMLM (live);
  the model (Composer backtest of the same tree over the same dates).
- Is the live window ordinary for the model? Percentile of the live-window return within all
  same-length windows of the real-era backtest.

Q2. WHERE DOES THE RETURN COME FROM? (real era 2023-04-19..2026-11-17, Composer backtest weights)
- By leg: ZVOL, VXZ, PULS contribution (sum of weight x total return), by calendar year.
- Excess over cash: the strategy's return minus PULS on the same days.
- Timing skill: strategy minus a STATIC mix holding each fund at the strategy's average weight
  (rebalanced daily). Placebo: 5,000 circular shifts of the weight path against returns (keeps run
  lengths and time in market); one-sided p-value for strategy > shifted.
- Carry vs curve: ZVOL-leg days decomposed into roll-down (curve unchanged) and curve change, from
  Cboe VIX futures settlements.

Q3. TIMING AROUND VOLATILITY ("not flipped on right when volatility is around")
- Event study on VIX spikes: sessions where VIX rises >= 15% in a day, or closes above its 1-year 90th
  percentile after being below it. Harvester weight in ZVOL/VXZ/PULS from day -5 to +10, and its
  cumulative return over the window, real era and the long history (Q5 path).
- ZVOL entries (weight rising from 0): next-1, 5, 10-day return of the leg; win rate; split by curve
  state at entry (contango vs inverted, VIX3M/VIX).

Q4. THE DECISION: counterfactual books (daily returns, weights rebalanced to target daily)
- Books: KEEP 29/29/27/15 (HG / KMLM symphony / SLEEVE / HARV); A: HARV -> KMLM symphony (29/44/27/0);
  B: HARV -> pure switcher (29 / 29 symphony + 15 switcher / 27); C: strip the VIX sleeve only
  (KMLM symphony -> switcher, HARV kept); D: no harvester anywhere (29 / 44 switcher / 27 / 0);
  E: HARV -> T-bills (placebo: is it better than cash?).
- Windows: (i) real era 2023-04-19..2026-11-17, Composer backtests; (ii) live 2026-07-22..11-17, actual
  symphony returns; (iii) the long synthetic path only as a stress annex, labelled as such.
- Two lenses for the switcher, because its backtest (+538%/yr) is not credible as a forecast:
  AS-MEASURED, and HAIRCUT: the switcher's daily return multiplied down so its real-era CAGR equals
  (a) its live annualised return since 07-07, and (b) half of that. Volatility and drawdown shape kept.
- Metrics: CAGR, volatility, Sharpe over T-bills, max drawdown, 5% daily CVaR, worst month, and the
  difference of each book from KEEP with a 90% interval from a stationary bootstrap of the joint daily
  returns (mean block 10 days, 2,000 draws; paired, same draws for every book).

Q5. BEYOND PRICE: what predicts the short mid-term-volatility return?
- Target: the inverse of the mid-term futures index built from Cboe settlements (as long as the
  archive allows; validated against VIXM and ZVOL), next 1, 5 and 21 sessions.
- Eight pre-named predictors, all known at the close: (1) mid-term roll yield (4th vs 7th month slope),
  (2) front slope VIX3M/VIX, (3) VIX6M/VIX3M, (4) variance risk premium = VIX^2 - 21-day realised
  variance of SPY, (5) VVIX, (6) VIX level percentile over 1 year, (7) HYG 5-day return,
  (8) SPY RSI(2) (the harvester's own trigger).
- Tests: univariate regression with Newey-West errors; top-minus-bottom quintile spread; walk-forward
  out-of-sample R2 against the expanding mean (first third as burn-in); Holm correction across the
  8 x 3 tests. A predictor "works" only if Holm-adjusted p < 0.05 AND out-of-sample R2 > 0.
- Then, on harvester ZVOL-entry days only: do the predictors that work separate good entries from bad?

Q6. REFINEMENTS (at most three, named now by mechanism, not found by search)
- R1 instrument: the same rule holding SVXY (-0.5x front-month) instead of ZVOL. Mechanism: the rule
  buys after sell-offs and holds days, so the vol crush it wants is at the front of the curve.
- R2 carry gate: enter ZVOL only when the gate variable from Q5 (if one "works") is favourable.
  If no predictor works, R2 is not run.
- R3 drop the long-vol leg (VXZ on RSI > 80) -> PULS. Mechanism: long mid-term futures bleed carry.
- Each is judged on the real era AND the futures-era long path, against the unchanged rule, with the
  same bootstrap intervals; a refinement that wins only in one window is reported as not robust.
  Prior no-builds are not re-run: HYG guard (12, 14), VRP sizing (25), GARCH gate (31), exit on
  inverted closes (39 C1, 54.4), vol targeting (21).

Q7. COSTS OUTSIDE THE BACKTEST: ZVOL fill slippage on record, distributions leaking out of the
symphony, capacity (share of ZVOL volume), the IBKR mirror's blocked ZVOL orders, duplication of one
rule in two symphonies.

## Decision rule (fixed now)
The thesis "move it to the KMLM switcher" is SUPPORTED if, in the real era under the HAIRCUT (a) lens,
book A or B has a higher CAGR than KEEP with the 90% interval for the CAGR difference above zero, AND
its max drawdown is not worse than KEEP's by more than 3 points at the interval's upper end.
It is REFUTED if KEEP has the higher Sharpe and lower max drawdown with both intervals excluding zero
under both lenses. Anything else is INCONCLUSIVE, reported as such with what would settle it.
Separately, "cost centre" is SUPPORTED if the harvester does not beat T-bills (book E >= KEEP on CAGR
within the interval) or its timing skill is indistinguishable from zero (placebo p > 0.10) AND its
static mix does not beat cash.
A refinement is recommended only if it beats the unchanged rule in both windows with intervals
excluding zero; otherwise it goes to the backlog.

## Honesty box (applies to every number)
All in-sample; none is a forecast. Real ZVOL history is 3.6 years with no crash deeper than -37% for
the fund. Composer backtests include 5 bps slippage; they are total return on adjusted closes, while
the live symphony curve excludes distributions paid to account cash. No taxes (Act 60). Not modelled:
intraday paths, ZVOL closure or a distribution cut, liquidity at larger size, the 15:50 decision vs
close price difference.
