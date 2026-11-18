# B.5 Enhanced: entry / exit / stop / profit-harvest overlays (2026-11-18)

Question (Casey): now that B.5 trades on IBKR ...3321, is there a rule for when to exit, re-enter, stop out or
harvest - on the book or on its legs, from price, RSI, volume, macro - that lifts Sharpe by cutting drawdown?
And which legs do not pull their weight?

Pre-registered (PREREG.md, commit e2e213c), amended once before any result (DEVIATIONS.md, commit 8373227).
Research only: nothing here changes the live book, a gate or a symphony. Charts: report.html and charts/*.png.

## Verdict: NOTHING SURVIVES. Keep the live rule (month-end check, +/-20% band).

| | CAGR | Sharpe | max drawdown |
|---|---|---|---|
| LIVE book, 2007-06..2026-11 (stand-ins before 2017) | 8.3% | 0.58 | -34.4% |
| LIVE book, 2017-04..2026-11 (real TAIL) | 10.5% | 0.71 | -23.0% |
| Walk-forward: each year-end run the rule with the best Sharpe since 2007 (upper bound), 2010-2026 | 5.6% | 0.46 | -21.7% |
| LIVE book, same 2010-2026 window | 9.5% | 0.72 | -23.0% |

Tape 2 (strong hedge) walk-forward: 5.4% / 0.42 / -27.0%. The walk-forward path ranks at percentile 1 (tape 2: 0)
of its own time-shifted placebos.

### Sharpe: 0 of 53 pass, on both tapes and with ETF proxies
- 43 of 53 rules are below a static book with the same average exposure (median -0.05). About -0.07 of that is
  structural: a switching rule with NO information loses that much to a steady book by construction. Against
  that no-information version the rules split 27 below / 26 above (median 0.00). 3 rules (tape 2: 4) rank in
  the top tenth of their own shuffled versions; about 5 would by chance. Read: no timing skill, plus a real
  structural cost of switching.
- Best raw gain +0.06 [-0.08, +0.18]: CAPE half-weight, which was switched on 87% of the time and had a
  drawdown 5.7 pts WORSE than its control. Lowest family-adjusted p: 0.95.
- Book-level rules: Sharpe 0.19-0.62 vs 0.58 live. Two sit at or above live, neither significant: 126-day
  return > bills (0.62) and the 10% stop (0.60). In the 2020 rebound the live book made +51%; the eight
  book-level stops made +8% to +39%.
- Profit harvesting (RSI > 70/80, stretch over the 200-day, top-decile run-up): nothing on the book
  (-0.06 to +0.01).
- Macro gates: credit and unemployment gates lifted first-half Sharpe (+0.20 to +0.22); SPY-trend and VIX gates
  helped 2008 drawdown only. Since 2017 every market, credit and labour gate is negative (-0.13 to -0.44); the
  dollar gate on the international legs is +0.10 (not significant). CAPE: no usable timing.
- Rebalance/harvest variants (10/15/30% bands, daily check, trim any leg above 1.25x target): all within noise.
- No mirror (inverted) rule exceeds +0.01: no inverted edge.

### Drawdown: 0 of 53 pass, but six per-leg rules come close (CANDIDATE, not proven)
All six cut max drawdown >= 2 pts in both halves vs a same-exposure static book and rank in the top 3% of their
own shuffled versions on that measure. All six fail because since 2017 they spent MORE time under water than
the static book (ulcer index): they shortened the deepest hole, not the time in holes.

| rule | max DD rule / static | 1st half | 2nd half | CAGR vs static / vs live | placebo p raw / studentised | fails |
|---|---|---|---|---|---|---|
| A2 each risk leg > own 10-month avg, monthly | -14.1% / -24.5% | +9.4 | +6.4 | +0.46 / -1.33 | 0.11 / 0.49 | ulcer (1st half 5.60 vs 5.53), p |
| A15 each risk leg vs 200-day, 2% buffer | -12.7% / -24.6% | +10.7 | +5.5 | -0.17 / -1.95 | 0.05 / 0.38 | ulcer |
| A6 per-leg 12% stop (primary) | -16.1% / -28.6% | +11.1 | +3.9 | -0.54 / -1.59 | 0.01 / 0.02 | ulcer; CAGR by 0.04 pt on tape 1 |
| A8 per-leg volatility stop | -19.3% / -28.9% | +8.4 | +6.8 | +0.16 / -0.92 | 0.16 / 0.35 | ulcer, p |
| A7 per-leg 16% stop | -19.0% / -30.3% | +10.3 | +5.2 | -0.71 / -1.45 | 0.06 / 0.16 | ulcer, CAGR |
| A10 equity legs > 200-day | -14.3% / -25.1% | +9.9 | +4.1 | -0.70 / -1.85 | 0.08 / 0.41 | ulcer, CAGR |

ETF-proxy rerun (SCZ/EFA, EEM for the mutual funds; d12_etf_proxy.json): same picture, still no pass (A2 then
fails only second-half ulcer, +0.16). A2 holds under +1, +2 and +5 days of lag and 4x costs (drawdown gain
+6.2 to +10.2 pts in each half). Max drawdown is one or two events per window; treat this as a lead to test,
not a result.

### Cheaper drawdown levers than timing (static, 2017+ window unless stated)
| change | drawdown (pts) [95%] | CAGR | Sharpe | drawdown pts per CAGR pt |
|---|---|---|---|---|
| 20% T-bills (80/20) | +5.4 [+2.1, +8.9] | -1.30 | +0.02 | 4.1 |
| 10% T-bills (90/10) | +2.2 [+1.0, +3.6] | -0.79 | 0.00 | 2.7 |
| KMLM 14% -> 20% | +1.8 [-0.3, +3.7] | -0.29 | +0.01 | 6.3 |
| KMLM 14% -> 25% | +3.2 [-0.6, +6.5] | -0.50 | +0.02 | 6.5 |
| TAIL 6% -> 10% | +1.9 [+0.2, +2.9] | -0.76 | -0.02 | 2.5 |
| TAIL 6% -> 15% | +4.3 [+0.5, +6.4] | -1.63 | -0.04 | 2.7 |
| TAIL 6% -> 0% | -2.7 [-4.1, -0.5] | +1.05 | +0.01 | - |
| TAIL -> T-bills | -1.3 [-2.2, +0.5] | +0.60 | +0.01 | - |

CANDIDATE (by-product): more KMLM bought drawdown at roughly twice the price-efficiency of T-bills or TAIL
(2007+: +4.5 pts [0.0, +8.4] for -0.44 pt/yr at 25%), but its 2017+ interval includes zero and KMLM is proxy
data before 2020-12. TAIL has bought drawdown at about the T-bill price. On CAGR vs max drawdown, 26 of 53
timing rules sit above the T-bill line over the full period, 17 since 2017, 9 in both halves (chance: ~13).

## Legs: none flagged
Sharpe change if the leg is dropped, 2017+ (95% bootstrap): AVUV +0.08 [-0.20, +0.35] (weakest point estimate,
widest interval); AVDV +0.04 (tape 2: +0.01; same data, rebalance-phase noise ~0.03); AVEM +0.02; TAIL +0.01;
KMLM -0.03; QUAL -0.04; PHYS -0.12 [-0.33, +0.10] (the leg the book can least afford to lose; without it the
2007+ drawdown is 12.6 pts deeper). Without KMLM the 2017+ drawdown is 3.5 pts deeper [-8.0, -0.3].

## Candidate edges (EDGE rule) - none clears multiplicity
120 conditional-return tests (about 105 independent); 6 exclude zero, 5-6 expected by chance.
- Oversold bounce: after RSI14 < 30 the next 21 days beat other days by +2.4 pts on the SPY/QUAL leg
  [+0.4, +4.6] (115 days, 58 spells) and +1.3 pts on gold [+0.0, +2.9] (183 days, 53 spells). Use: never sell
  a leg into an oversold reading; if a band rebalance is due then, do it.
- Strength persists on international legs: after RSI14 > 70 the AVDV / AVEM proxies beat other days by
  +1.4 / +1.3 pts over 21 days (both exclude zero). Trimming them on RSI > 70 cost -0.17 [-0.25, -0.08] and
  -0.13 [-0.21, -0.04] Sharpe over 30 years, but most of it is 1996-2006 (AVDV -0.48 then, -0.10 since 2017),
  the stale-NAV era.
- High-volume down day on the SPY/QUAL leg: next 5 days +0.5 pt better [+0.1, +1.0] (147 days).
- Gold after VIX > VIX3M: next 5 days +0.46 pt better [+0.07, +0.85] (555 days, 151 spells).
- Single-leg trend filters, long history vs same-exposure control: 200-day helped EM (+0.20) and international
  small value (+0.13), 10-month helped large-cap (+0.18); US small value mixed (-0.09 / +0.05); gold worse
  (-0.09, 21 years). No interval excludes zero.
To use any of these: one pre-registered single-hypothesis test on new data. None is tradeable as is.

## Honesty box
- Basis: daily closes, mark-to-market, BIL-excess Sharpe; signal at close t, trade at close t+1; costs 3-12 bps
  one-way per leg. All numbers are in-sample history, none is a forecast.
- Power: the smallest Sharpe gain this design can detect on 19 years is ~0.4-0.5 for rules that switch large
  parts of the book and ~0.13 for small trims. It rules out a big edge, not a small one.
- Stand-ins before 2017: TAIL earns bills (tape 1) or a fitted Treasuries+puts model that over-earns real TAIL
  by 4.6 pts/yr (tape 2); KMLM is RYMFX (2x on tape 2) before 2010-08 and ASFYX to 2020-12; QUAL is SPY before
  2013-07; Avantis legs are DFA mutual funds before 2019-10. Every verdict is the same on both tapes.
- The two halves (2007-2017, 2017-2026) are a consistency check, not a holdout.
- Flags: near-static rules B14, B18; rules that never fired in 2008: B16-B19 (harvest), M6. Same-close
  execution on 2017+ leaves A2 unchanged (drawdown gain +6.3).
- Registered prior, scored: trend/stops cut 2008 and gave it back in 2020 - yes. No rule clears the Sharpe bar -
  yes. CAPE will not time the book - yes. "Most of the drawdown gain is exposure, not timing" - too pessimistic
  for the per-leg rules (about 10 pts beyond same-exposure static). Hedge legs best in the leave-one-out
  drawdown column - KMLM yes, but gold protected most.
- Not modelled: intraday stops, partial fills, IBKR minimums, option hedges, UNRATE/CAPE revisions, taxes (none).
- Gate tests (10) cover the static engine vs an independent reference, no-look-ahead on all 53 rules and
  mirrors, trade timing, bootstrap and placebo identities. Not unit-tested: control solver, max-T, trim rules
  (covered by the counter-agents' independent replications instead).

## Counter-agent verdicts
1. Design review of PREREG.md, before the build: PASS WITH CORRECTIONS (1 blocking, 7 serious) - all adopted
   in DEVIATIONS.md amendment 1 before any result.
2. Independent from-scratch recomputation (own engine, raw data): PASS. LIVE exact in 2017+, +0.02 pt CAGR on
   2007+; A2 / B3 / M1 within 0.13 pt CAGR, 0.01 Sharpe, 0.22 pt drawdown; raw-data spot checks exact. Two
   engine conventions it surfaced are logged in DEVIATIONS.md (N1); both slightly handicap the overlays.
3. Adversarial code-and-claims audit: PASS WITH CORRECTIONS. No code defect; verdict reproduced; bootstrap
   replicated independently. Corrections applied: structural handicap of switching reported, drawdown
   near-misses listed in full, ETF-proxy rerun added, KMLM/TAIL weight arms reported, eight wording fixes,
   studentised placebo sensitivity added.

## Files
PREREG.md, DEVIATIONS.md, results.json (every number), d12_etf_proxy.json, data_meta.json (sources, hashes),
report.html (interactive charts), charts/*.png, code/ (prep, common, arms, engine, run, d12_etf_proxy, charts,
report_template.html, shots.js, test_engine). Raw price cache not committed (re-fetch with code/prep.py).
