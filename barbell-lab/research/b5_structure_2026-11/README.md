# B.5 Enhanced: structural changes to raise Sharpe and Sortino (2026-11-19)

> DRAFT - independent recompute and code-and-claims audit in progress; numbers and wording are not final.

Question (Casey): untested, structural ways (weights, leg swaps, capital efficiency) to raise the Sharpe AND
Sortino of the live B.5 book. Timing was closed by the overlay study. Pre-registered (PREREG.md, commit 745e5c3),
amended once before any arm was run (DEVIATIONS.md, commit f559d16 + D15). Research only: nothing here changes
the live book, a gate or a symphony.

## Verdict: nothing IMPROVES. Two CANDIDATES, one worth a shadow track.

Calibration first: with these data IMPROVES had about a 45-55% chance of catching a true +0.05 Sharpe gain for
P3/P5 (98% for P6, 42% for P1). CANDIDATE fires for roughly one arm in four when there is no effect at all, so
it justifies watching, never trading.

Live book: 2007-06..2026-11 CAGR 8.3%, Sharpe 0.58, Sortino 0.95, max drawdown -34.4%;
2017-04..2026-11 10.5%, 0.71, 1.43, -23.0%. Sortino is on monthly returns; both ratios are over T-bills.

| idea | arm | window | Sharpe change [95%] | Sortino change [95%] | CAGR | verdict |
|---|---|---|---|---|---|---|
| 1 Risk-balanced weights | six-leg equal risk, halfway to live, 25% cap | 2007+ | -0.01 [-0.07, +0.04] | -0.03 [-0.17, +0.10] | -0.65 | NO |
| 2 Leverage back to live volatility | idea 1 at 1.09-1.13x | 2007+ | -0.01 (0.00 at cheap financing) | -0.02 | -0.15 | no verdict (translation) |
| 3 TAIL -> BTAL | full swap | 2017+ | +0.03 [-0.02, +0.08] | +0.11 [-0.03, +0.21] | +0.36 | CANDIDATE |
| 4 Trend blend | KMLM + DBMF at 14.1% | 2010-08+ | -0.01 | -0.01 | -0.06 | sign only: no |
| 5 Add Treasuries | 10% IEF from equity | 2007+ | +0.03 [-0.02, +0.08] | +0.07 [-0.04, +0.18] | -0.61 | NO |
| 6 Lower-volatility equity | 8 pts AVUV -> large value | 2007+ | +0.01 [-0.01, +0.03] | +0.02 [-0.03, +0.07] | 0.00 | CANDIDATE (tiny) |

- Idea 1, NO: negative in the first half (-0.05), positive in the second (+0.05), and it fails its kill test on
  the real-KMLM years. The solver wants KMLM at the 25% cap and AVUV near 10%; halfway to live that is AVUV 16.7,
  PHYS 22.8, QUAL 14.5, KMLM 19.6, AVDV 11.8, AVEM 8.8. More trend and less small value did not pay over 2009-2017.
- Idea 2: leverage cannot fix what idea 1 did not deliver. Leverage ALONE on the live book (1.2x) lowers Sharpe
  by 0.021 at T-bills + 1.5% (0.008 at + 0.5%), adds 0.9-1.1 pt/yr CAGR and deepens the 2008 drawdown from
  -34.4% to -40.5%.
- Idea 3, CANDIDATE: positive in both halves (+0.04, +0.02), same on tape 2 and at 2x costs, crash episodes no
  worse (2020 fall -21.8% vs -22.0%; 2022 -7.9% vs -9.2%; 2025 tariff drop -9.2% vs -8.8%). Adjusted p 0.35
  (Sharpe) and 0.12 (Sortino): not significant. Half swap: +0.025 [-0.005, +0.053]. Only 9.6 years of real
  data and no 2008; BTAL-type strategies lost heavily in the 2009 rebound, which this window does not contain.
- Idea 5, NO: all of the gain is 2007-2017 (+0.06); since 2017 it is -0.003 and on the real-KMLM years -0.06
  (2022). It did cut the 2008 drawdown by 6.3 pts, at -0.6 pt/yr.
- Idea 6, CANDIDATE but too small to matter. Variants: to QUAL +0.02 [-0.01, +0.06]; to minimum-volatility
  (USMV, 2011-10+) +0.03 [-0.02, +0.08] with a 2.2 pt shallower drawdown. Caution: 1993-2007 small value beat
  large value (Sharpe 0.87 vs 0.65), so this is partly chasing the last decade.

## Exploratory (outside the test family)
- 5% long dollar (UUP) in place of most of TAIL: Sharpe +0.02 [-0.002, +0.042], Sortino +0.05, CAGR +0.30,
  positive in both halves (tape 2: +0.008). CANDIDATE EDGE: same direction as the dollar gate and the TAIL-costs
  findings of the overlay study. To use: its own pre-registered test; note it offsets part of gold.
- Collar and put-protected wrappers on the QUAL leg: -0.02 and -0.01. Dead, as the literature says.
- DISC-selected combination (large value + Treasuries + BTAL, chosen on 2007-2017, shown on 2017+): Sharpe 0.78
  vs 0.71 (+0.07 [-0.04, +0.18]), Sortino 1.67 vs 1.43, volatility 9.5% vs 11.6%, drawdown -18.3% vs -23.0%,
  CAGR 9.9% vs 10.5% (live scaled to the same volatility: 9.1%). No verdict: the menu was chosen with sight of 2017+.
- Gold wrapper (arithmetic): GLDM beat PHYS by 0.85 pt/yr since 2018-06, about +0.20 pt/yr on the book.

## Against SPY + T-bills at the same volatility (2017+)
Live 0.71 / 1.43 (Sharpe / Sortino); SPY + T-bills 0.69 / 1.41; with BTAL 0.74 / 1.53; the combination 0.78 / 1.67.

## Honesty box
- Daily closes, mark-to-market, ratios over T-bills, Sortino on 21-day returns. In-sample history, not a forecast.
- Before 2017 TAIL is a stand-in, before 2020-12 KMLM is, before 2019-10 the Avantis legs are, before 2013-07 QUAL
  is SPY. The BTAL stand-in failed its gate, so idea 3 rests on 2017+ only.
- Leverage is modelled as constant gross reset daily; financing T-bills + 1.5% (margin) and + 0.5% (futures /
  stacked ETF). Not modelled: margin calls, forced deleveraging, futures rolls, taxes (none).
- One solver defect was found and fixed after the first results (DEVIATIONS N1); it had flattered idea 1.
- Minimum detectable Sharpe difference (80% power): idea 1 0.08, idea 3 0.07, idea 5 0.08, idea 6 0.035.

## Files
PREREG.md, DEVIATIONS.md, HYPOTHESES.md, gates.json, results2.json, risk_shares.json, charts/, code/ (prep2, lib2,
run2, test2 - 11 gate tests incl. no-look-ahead on the yearly weights and the leverage identities).
