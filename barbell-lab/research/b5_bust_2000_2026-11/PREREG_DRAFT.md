# B.5 Enhanced through a high-CAPE bust: the 2000-2002 test - DRAFT pre-registration (2026-11-19)

STATUS: DRAFT. Not frozen until (1) Casey answers the open decisions at the bottom and (2) the design
counter-agent has reviewed it. No data has been pulled into a backtest for this test; nothing below is a result.

## Why this test
The overlay study's SPY comparison (spy_compare.json) found B.5 beat a same-volatility SPY + T-bills mix only in
the window containing 2008; from 2010 the mix did slightly better. The 2010-2026 sample is one long US large-cap
bull market. B.5's thesis is protection when US large caps are expensive and mean-revert. The only comparable
setup in usable data is 1999-2000: CAPE peaked at 44.2 (Dec 1999); today's 38.8 has been exceeded only in
1998-2000 and 2025-2026.

## Questions (fixed now)
- Q1 thesis: across a high-CAPE bust and the full cycle after it, does B.5 deliver SPY-like returns with clearly
  less risk, and does it beat simply holding less SPY?
- Q2 out-of-sample: the overlay study's leading candidate, A2 (each risk leg held only above its own 10-month
  average, checked monthly), was found on 2007-2026. 1997-2006 was never used. Does its drawdown edge hold there?

## Windows
- W1 bust cycle (primary): 1999-12-31 (CAPE record) to the first close at which SPY total return regains its
  2000-03-24 high. The end is defined by rule, not chosen (computed from SPY alone: 2006-10-26).
- W2 bear only (descriptive, never adjudicates): 2000-03-24 to 2002-10-09.
- W3 full history: 1999-12-31 to 2026-11-17, joining this test's stand-ins to the overlay study's tape 1 from
  2005-01-03.
- Warm-up from 1997-01-02 (10-month signals for A2, band state).
- Q2 also uses 1997-01..2006-12, which is entirely outside the window A2 was found on.

## Book and rule
Live weights: AVUV 23.5, PHYS 23.5, QUAL 15.3, KMLM 14.1, AVDV 11.8, AVEM 5.9, TAIL 5.9. Live rule: month-end check,
+/-20% band, fill next day, 12-month fallback, costs as in barbell-lab/config/backtest.yaml. Engine, timing and
metrics are reused unchanged from b5_overlay_2026-11/code (independently verified).

## Leg stand-ins before the live ETFs, each with a validation gate on overlapping data
| leg | stand-in before live data | gate (must pass before any result is computed) |
|---|---|---|
| AVUV | DFSVX (1993) | already config-declared |
| AVDV | DISVX (1994) | already config-declared |
| AVEM | DFEMX (1994) | already config-declared |
| QUAL | French "Big / Robust profitability" portfolio (daily, value-weighted); bracket: SPY | daily corr >= 0.90 and annual tracking difference within 2 pts vs QUAL 2013-07..2026-09 |
| PHYS | COMEX gold front-month (repo fixture GCUSD) to 2004-11, then GLD | daily corr >= 0.95 vs GLD 2004-11..2026 |
| TAIL | b x Treasury (VFITX before IEF) + c x (CBOE PPUT - S&P 500 TR), fitted on real TAIL 2017+; bracket: T-bills | the existing fit (R-squared 0.53) refit with the VFITX/IEF splice; report its over-earning vs real TAIL |
| KMLM | see open decision 1; bracket: T-bills | monthly corr >= 0.60 vs KMLM 2020-12+ and vs ASFYX 2010-2020; positive in 2008 and 2022 |
| BIL | 3-month T-bill (FRED DTB3) | - |

Every verdict must hold under the brackets (QUAL = SPY, TAIL = bills, KMLM = bills) as well as under the
best stand-ins. A verdict that flips between brackets is reported as INCONCLUSIVE.

## Comparators
1. SPY (total return).
2. SPY + T-bills mixed monthly to B.5's own volatility in each window (the "just hold less SPY" book).
3. 60/40 SPY / intermediate Treasuries (VFITX), monthly rebalanced: the classic defensive book.

## Verdict rules (fixed now; one regime, so no p-values; reported as consistent or inconsistent with the thesis)
Q1 THESIS HOLDS if all of:
- W1: B.5 CAGR > SPY CAGR, and B.5 beats the same-volatility SPY/bills mix on both CAGR and max drawdown.
- W3: B.5 CAGR within 1.0 pt/yr of SPY's, max drawdown no more than two-thirds of SPY's, Sharpe >= SPY's.
- Both hold under every bracket.
Q1 THESIS FAILS if W1 B.5 loses to the same-volatility mix on CAGR. Anything else is MIXED, with the failing part named.

Q2 A2 CONFIRMED OUT OF SAMPLE if, on 1997-2006, against a static book at A2's own realized average exposure:
max drawdown >= 2 pts better, ulcer index lower, CAGR within 0.5 pt/yr; it still holds at +2 days lag; and it
is at or above the 90th percentile of its own circular-shift placebo. Otherwise NOT CONFIRMED. A2 stays research
either way; a pass would only justify a shadow run with kill criteria written first.

## Diagnostics (reported, not adjudicated)
Leave-one-leg-out on W1 (does one leg carry the result?); the W2 bear by leg; calendar-year table vs SPY;
the KMLM 25% variant from the overlay study on W1 and W3.

## Registered prior
B.5 loses far less than SPY in W2. Disclosure: while drafting, the W2 returns of four series were looked at
(SPY -47.2%, DFSVX -6.7%, DISVX -9.0%, DFEMX -44.5%, 2000-03-24..2002-10-09); no book or rule was run. W2 never
adjudicates. The informative parts are W1 against the same-volatility mix, W3, and Q2. Expected: W1 passes; W3 is close on
CAGR; most of the W1 edge comes from the DFA small-value proxies; A2 cuts the 2000-2002 drawdown but may fail
on time under water again.

## Honesty limits (stated before results)
- Hindsight: the B.5 weights were chosen in 2026, after the 2000s rewarded value, EM and gold. This is a regime
  stress test, not out-of-sample proof of the weights. Q2 is the only out-of-sample question.
- One bust is one observation. A pass is consistent with the thesis; it does not establish it.
- Pre-2005 KMLM and TAIL are modelled, not traded. DFA mutual-fund NAVs are stale-priced, which flatters
  smoothness.
- Not modelled: taxes (Act 60), intraday execution, partial fills.

## Process (repo rules)
Design counter-agent on this file, then freeze -> build the stand-ins and run the gates (STOP and report if a
gate fails) -> run -> independent recompute + code-and-claims audit -> honesty box and charts (equity vs SPY,
drawdowns, W2 by leg, A2 vs control) -> commit. Research only: no change to the live book, a gate or a symphony.
Rough cost: three to four agents.

## Open decisions (Casey)
1. KMLM before 2007 (no trend fund in free data). Options: (a) build a KMLM-style replica (price vs 12-month
   average on currencies from FRED FX, US Treasuries from DGS10/VUSTX, oil and gold), gated against KMLM and
   ASFYX; it has no foreign-bond or broad-commodity legs; (b) a CTA index (SG Trend or Barclay CTA, monthly) if
   you have a data source; (c) bills only.
2. Extend to 1973-74 as well (second high-valuation bust; equity legs from Ken French, gold from 1975, no EM leg)?
