# B.5 Enhanced: structural ways to raise Sharpe and Sortino - PHASE 1 hypothesis list (2026-11-19)

STATUS: ideas only. Nothing here has been backtested. Effect sizes are priors, not measurements.
Phase 2 (PREREG, design review, build) starts only after Casey approves the top 6 and answers the open questions.

## The one measured fact this list starts from (descriptive; risk_shares.json, charts/01_risk_shares.png)
Live book, 2017-04..2026-11 (2007-06+ in brackets): the four equity legs are 56.5% of capital but 86% (85%)
of volatility. AVUV alone is 43% (42%) of volatility with the lowest Sharpe of the equity legs, 0.44 (0.38).
KMLM is 14.1% of capital and 1.6% (1.7%) of volatility, correlation to the book 0.10. TAIL's stand-alone
Sharpe is -0.60. The book is an equity book with a gold slice; its diversifiers are too small to matter.

Why structure is better powered than timing: static changes stay highly correlated with the live book, so
the bootstrap interval on a Sharpe difference was +/-0.03 to +/-0.11 in the overlay study, against +/-0.3
for switching rules. Effects of 0.05-0.10 are detectable here.

Ranking score = expected effect x testability x distance from what has been tested (each 1-5).

## Ranked list

### 1. Risk-balanced weights (score 5x5x4 = 100) - TOP 6
- Mechanism: size legs by risk contribution (equal-risk-contribution; variant: by downside deviation), 25% cap kept,
  shrunk halfway to current weights. Cuts AVUV, raises KMLM and gold.
- Why Sharpe and Sortino: a zero-correlation leg with Sharpe 0.28 is under-used at 2% of risk; rebalancing risk away
  from the lowest-Sharpe, highest-volatility leg raises both, and trend's positive skew helps Sortino more.
- Data: all seven legs, both tapes, 2007+; long-history stand-ins from the 2000-02 draft.
- Expected: Sharpe +0.05 to +0.10, Sortino +0.08 to +0.15, at lower volatility (about 8-9%) and lower CAGR.
- Kill: not positive in both halves; gone on tape 2; or it depends on pre-2020 KMLM proxy data.

### 2. Capital-efficient ("stacked") implementation at the live book's volatility (5x3x5 = 75) - TOP 6, NEEDS A POLICY ANSWER
- Mechanism: hold the same exposures through 90/60 or 100/100-style funds (NTSX, GDE, RSST) or micro futures, freeing
  15-25% of capital for diversifiers; or scale the idea-1 book back up to 11.8% volatility.
- Why: it does not raise Sharpe by itself; it converts idea 1's higher Sharpe into CAGR, which is what the
  SPY + T-bills benchmark demands. Sortino improves only if the added exposure is the diversifiers.
- Data: live funds are short (NTSX 2018, GDE 2022, RSST 2023); synthetic replication with a validation gate
  (the barbell_timer GDE replica tracked within 1.5%/yr).
- Expected: +1.0 to +1.5 pt/yr CAGR at the live volatility, less 0.1-0.3 pt/yr financing and fees.
- Kill: financing and fees eat more than half the gain; drawdown at matched volatility is deeper than live;
  a 2022-style joint fall in stocks, bonds and gold breaks it.

### 3. Replace TAIL with an anti-beta / long-short quality hedge (4x4x4 = 64) - TOP 6
- Mechanism: BTAL (long low-beta, short high-beta) has TAIL-like negative equity correlation with roughly flat
  carry instead of about -7%/yr. Arms: full swap, half swap.
- Why: removes the book's one negative-Sharpe leg while keeping a crisis offset; less bleed lifts both ratios.
- Data: BTAL daily from 2011-09; AQR betting-against-beta and quality-minus-junk daily factors for 2000-02 and
  2008 context (paper factors, flagged). Earlier Question 1 looked at BTAL only on a post-2023 window with a modelled bot.
- Expected: Sharpe +0.03 to +0.05, Sortino +0.04 to +0.07, CAGR +0.4 to +0.6 pt/yr.
- Kill: 2020 or 2022 episode drawdown worse than with TAIL by more than 1.5 pts, or Sortino does not improve.

### 4. Managed-futures sleeve: blend, then size it properly (4x4x3 = 48) - TOP 6
- Mechanism: (a) replace single-fund KMLM with a blend (KMLM + DBMF + a mutual-fund trend composite) at the same
  14.1%; (b) the blend at 20%, funded from TAIL and AVUV.
- Why: manager dispersion in trend is 10-20 pts a year; a blend keeps the positive skew with less single-index luck.
- Data: DBMF 2019, KMLM 2020, AQMIX/ASFYX 2010, PQTIX 2014, RYMFX 2007.
- Expected: Sharpe +0.02 to +0.05, Sortino +0.04 to +0.08.
- Kill: the overlay study's KMLM drawdown lead disappears once KMLM is replaced by the blend (it was 2022 luck).

### 5. Add duration, capital-free or funded (3x5x4 = 60) - TOP 6
- Mechanism: B.5 holds almost no bonds. Arms: swap QUAL for a 90/60 stock/Treasury stack; or 10% intermediate
  Treasuries / TIPS funded pro-rata from equity.
- Why: flight-to-quality in equity crashes (Sortino); positive carry in most regimes (Sharpe). Fails when
  inflation drives both down (2022).
- Data: VFITX 1991, IEF 2002, TIP 2003.
- Expected: Sharpe +0.02 to +0.05 over the long history, likely negative since 2017.
- Kill: negative in the 2017+ half with no drawdown benefit in 2020.

### 6. Lower-volatility equity core: move part of AVUV to large value / quality / minimum-volatility (3x4x3 = 36) - TOP 6
- Mechanism: AVUV carries 43% of risk at the lowest equity Sharpe. Shift 5-10 pts of it to a lower-volatility
  equity leg, equity capital unchanged.
- Why: lower equity-block volatility and shallower crash losses at similar expected return.
- Data: DFLVX (large value, 1993), USMV 2011, CBOE LOVOL 2006, QUAL/SPY.
- Expected: Sharpe +0.02 to +0.04, Sortino +0.03 to +0.06.
- Kill: no gain against a control at the same volatility (it was only a beta cut). Note the tension with the
  thesis: 2000-02 is where small value protected.

### 7. Long US dollar as a positive-carry crisis hedge (3x4x5 = 60 on novelty; lower confidence) - EXPLORATORY
- Mechanism: 5% long USD (UUP) from TAIL, or FX-hedge the international legs. The dollar rose in 2008, March 2020
  and 2022; the dollar gate was the only positive macro gate since 2017.
- Why: crisis offset with positive carry while US rates exceed foreign rates.
- Data: UUP 2007, broad dollar index 2006.
- Expected: Sharpe +0.01 to +0.03. Offsets part of gold (correlation about -0.4).
- Kill: lowers Sharpe once gold's offset is counted.

### 8. Whole barbell: sleeve shape given the short-vol bot (4x1x5 = 20) - BLOCKED, needs bot P&L
- Mechanism: optimise the sleeve for the combined 80/20 book, where the bot's left tail changes which hedge is worth holding.
- Data: MISSING. config/data.yaml has capital_base null and no bot database in the repo.
- Kill: n/a until the data exists.

### 9. Option-structure wrappers on the equity legs (2x5x5 = 50) - EXPLORATORY, cheap to kill
- Mechanism: CBOE zero-cost collar (CLLZ, 1986), put-protection (PPUT), buy-write (BXMD), put-write (PUT) as
  stand-ins for a collared or buffered equity leg.
- Why: built for downside deviation. Prior is low: published evidence says collars lose to simply holding less equity.
- Expected: Sharpe -0.02 to +0.03; Sortino unclear.
- Kill: loses to the same-volatility equity + T-bills mix.

### 10. Per-leg volatility scaling (2x5x2 = 20)
- Each leg scaled to a constant risk budget. Round 8 found no Sharpe gain for the book-level version; this is
  timing by another name. Expected 0.00 to +0.05. Kill: no gain vs its shuffled-timing placebo.

### 11. Conditional VIX-call hedge instead of always-on puts (3x3x4 = 36)
- CBOE VXTH (2006) overlay as a cheaper-carry convexity source. Not a fund: would need VIX options at IBKR.
  Expected Sharpe +0.01 to +0.03. Kill: carry no better than TAIL's.

### 12. Merger arbitrage as the cash-like ballast (2x4x4 = 32)
- MNA 2009, MERFX 1989. Low volatility, small equity beta. Expected +0.01 to +0.02. Kill: equity beta rises in crashes.

### 13. Gold wrapper: PHYS to a low-cost bullion ETF (1x5x5 = 25) - arithmetic, not a backtest
- PHYS costs about 0.4%/yr plus premium/discount noise; GLDM about 0.1%. Worth about 7 bps/yr on the book.
  PHYS's usual US tax rationale does not apply under Act 60. Check: PHYS premium/discount history.

### 14. Add cross-sectional momentum equity (2x4x3 = 24)
- Value and momentum diversify; long-only the effect is muted. MTUM 2013, French momentum portfolios. Expected +0.01 to +0.03.

### 15. Direct robust Sharpe/Sortino optimisation, walk-forward (3x3x2 = 18)
- Resampled, capped, shrunk to idea 1. Same lever as idea 1 with more overfitting risk; use as a ceiling check only.

### 16. TIPS in place of nominal Treasuries wherever a bond leg appears (2x4x3 = 24) - folded into idea 5.

### 17. Broad commodities leg (2x4x2 = 16)
- DBC 2006, PDBC 2014. Long-run Sharpe near zero and KMLM already trades them.

### 18. Trend-managed slice of each risk leg (3x4x1 = 12)
- The overlay study's drawdown near-miss, applied to 25-50% of each leg. Timing: wait for the 2000-02 out-of-sample test.

### 19. Oversold-conditional rebalance buys (1x4x3 = 12)
- Only buy a leg on a band breach once RSI14 < 30, with a time limit. Rebalance flow is about 15% of the book a
  year, so the ceiling is a few bps. Kill: inside the cadence study's noise band.

### 20. Delay trimming strong international legs (1x4x3 = 12) - same ceiling as 19.

### 21. Tranche rebalance dates (1x5x2 = 10) - cuts timing luck, not expected Sharpe.

### 22. Fold AVEM into AVDV or EM value (1x3x2 = 6) - leave-one-out was +0.02 [-0.02, +0.05].

### 23. Carry sleeve (2x1x5 = 10) - BLOCKED: no clean liquid fund (DBV delisted).

### 24. Futures implementation at IBKR instead of stacked ETFs (variant of idea 2) - cheaper financing; a build
question for the executor, not a research arm.

## Proposed Phase 2 family
Primary (max-T family of 6): ideas 1, 2, 3, 4, 5, 6. Exploratory, outside the family, cheap: 7 and 9.
Idea 13 is reported as arithmetic. Idea 8 waits for bot data. Idea 18 waits for the 2000-02 test.

## Open questions for Casey (Phase 2 does not start until answered)
1. Leverage: may the study consider about 1.2-1.3x gross exposure through stacked ETFs or micro futures (idea 2)?
   If no, idea 2 is dropped and idea 7 moves into the primary six.
2. Bot data: is there a daily P&L history and capital base for the short-vol bot? Without it idea 8 stays out.
3. Universe: ETFs tradable at IBKR only (mutual funds used as history stand-ins, never as holdings), and the
   25% single-position cap stays? Assumed yes unless told otherwise.
