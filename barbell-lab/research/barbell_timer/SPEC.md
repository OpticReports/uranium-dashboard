# BARBELL-TIMER — frozen research brief (owner-authored, 2026-08-12)

Owner's brief committed VERBATIM below as the pre-registration. The rule
set (5 candidates), signal library, QA battery, cost model, and verdict
criterion (Calmar/ulcer vs static 50/50 OOS, p<0.10 after multiple-testing
adjustment) are frozen before any data is pulled. Additions after this
commit are reported as amendments, never silently.

Execution notes (implementation choices that the brief leaves open, fixed
now): data via FMP (GDE/SPY/GLD/GCUSD dailies) + FRED (TB3MS, DFII10,
DTWEXM/DTWEXBGS, CPIAUCSL, FEDFUNDS) + repo Shiller/datahub fixtures
(SPX TR pre-1993 splice, gold monthly pre-futures). Gold futures excess
return pre-FMP-history is approximated as spot return minus a documented
carry/lease adjustment - FLAGGED per the guardrail, quantified by decade
per Phase 0. Signals monthly, computed on month-end data, executed at the
NEXT month's open (repo standing timing convention). All fixtures frozen
under research/barbell_timer/fixtures/.

---

[Owner brief follows verbatim]

EXPLORATORY: Gold/Equity Regime-Rotation Research Engine ("BARBELL-TIMER")
Research-grade exploration - NOT production, NOT live trading.
Three sleeves: GDE (stacked ~90/90 gold-futures + S&P) or synthetic
replication; SPY; BOXX (bills proxy, bills minus 5bp).
Primary objective: maximize drawdown reduction per unit of CAGR
sacrificed, vs buy-and-hold GDE and vs static 50/50 GDE/SPY. Alpha is NOT
the goal. Prior findings internalized: regime-dominated (lost 1980-1999,
won 2001-2011, rolling 10y win rate ~48%, Sharpe diff CI straddles zero);
B&H synthetic maxDD ~-47% annual (assume -55/-60 true); naive gold-trend
timing was the WORST rule tested; best simple rule = relative momentum
GDE/SPY + absolute cash filter (annual: DD -47->-30, underwater 6y->3y,
Sortino 1.0->1.7) - must revalidate monthly; static 50/50 captured most
available Sharpe improvement and is the null.

Phase 0: SPX TR to 1970 (splice SPY post-1993); gold spot AND front-month
futures; 3M bills (BOXX proxy pre-2022, actual BOXX after); GDE actual NAV
from 2022-03-17; 10Y TIPS real yield (2003->, spliced proxy before);
optional lease rates/DXY/term structure. VALIDATION GATE: replication =
0.90xSPX_TR + 0.10xbills + 0.90x(gold futures excess) - 20bp fee -
realistic roll cost must track actual GDE 2022-present within ~1.5%/yr TE
and match WisdomTree since-inception 26.57% ann. (as of 7/31/2026) - else
STOP and fix. Report TE explicitly. Compute realized gold carry drag by
decade - quantify, don't assume.

Phase 1: monthly 1975->: B&H GDE-synth, B&H SPY, static 25/75-50/50-75/25
(monthly + quarterly rebal). Full stats: CAGR, vol, Sharpe (excess bills),
Sortino (MAR=rf, conventions stated), monthly maxDD, longest underwater,
Calmar, ulcer, worst 12m, %positive. Rolling 10y spreads vs SPY and 50/50.
Report intramonth-blind bias; estimate daily where possible.

Phase 2 signals (isolation first, kill <coin-flip OOS): 10m SMA per
sleeve; 12-1 momentum abs+rel; gold/SPY ratio 10m SMA; TSMOM 3/6/12m;
TIPS real yield level/3m change/12m trend; real FFR; futures term
structure state+slope; DXY 12m trend.

Phase 3 rules (pre-registered, walk-forward only, expanding window, no
full-sample optimization; <=3 free params; 5bp/switch, BOXX=bills-5bp;
report turnover/decade; per-regime blocks 1980-99, 2001-11, 2012-18,
2022->; must be at worst mildly negative in bad regime):
 1. Static 50/50 (null)
 2. Rel momentum GDE/SPY + abs cash filter (monthly)
 3. Real-rate gate: GDE when TIPS trend down/flat, SPY rising, BOXX both neg
 4. Composite: momentum AND real-rate agree -> GDE; disagree -> 50/50;
    both neg -> BOXX
 5. Vol-targeted #4 (60d trailing, 15% target)

Phase 4 adversarial QA: start-date sensitivity (all years, min/max);
drop-single-year; signal noise 15%/30% flips x2000 trials; bootstrap CIs
vs 50/50; 1-month lag stress; oracle gap.

Deliverables: data-validation report (go/no-go), master stats table,
rolling 10y spread charts, drawdown overlay with switch dates, QA appendix
including failures, one-page honest verdict: does ANY rule improve
Calmar/ulcer vs 50/50 OOS with p<0.10 after multiple-testing adjustment?
"No" is a valid finding.

Guardrails: no live orders; flag all approximations/splices; Sharpe>1.2
on a timing rule = assume bug/leak first, audit timestamps; no tax
penalty (Act 60) but report turnover; prefer boring conclusions that
survive every check.

## AMENDMENT A5 (owner, 2026-08-12, logged before Phase 2-3 results seen)

Owner's underlying decision question: "find a way to make owning GDE
better than owning SPY." The verdict page must therefore answer TWO
questions, separately: (Q1, original) does any rule beat the static
50/50 null on Calmar/ulcer OOS after multiple-testing adjustment; (Q2,
owner) does any GDE-containing portfolio (static blend or rule) dominate
B&H SPY - defined as: >= SPY CAGR AND better maxDD/Calmar/Sortino, with
the comparison ALSO shown leverage-aware (GDE is ~180% notional; a
90/90 stack beating 100% SPY on raw CAGR is expected, not evidence).
Every rule table gains a vs-SPY column set. Phase 4's drop-single-year
test is decisive for Q2 (prior: the 51y CAGR edge may be 1979 alone).
