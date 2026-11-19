# Deviations from PREREG.md

## Amendment 1 - 2026-11-19, BEFORE any arm was run
Sources: (i) the stand-in gates (gates.json), run before any arm; (ii) the independent design review of
PREREG.md (counter-agent, read-only: PASS WITH CORRECTIONS, 2 BLOCKING, 7 SERIOUS, 5 MINOR). At this point only
data loading, the gates and an exact reproduction of the verified live-book series existed.

Gate outcomes
G1 BTAL stand-in FAILED (daily corr 0.53 < 0.70, monthly 0.76 < 0.80). No BTAL history before 2011-09-14 is used.
G2 DBMF <- AQMIX passed (monthly corr 0.72). AVLV <- DFLVX passed (0.97).
G3 Financing: GDE within +0.13%/yr of its recipe at T-bills + 0.50%; NTSX (added check, 8.3 years, 0.9 SPY + 0.6 IEF)
   within +0.20%/yr. RSST failed (-4.6%/yr vs an SPY + DBMF recipe, +6.1%/yr vs SPY + KMLM): the gap is its own
   trend sleeve, not financing. Per D12 the gate is descriptive only; the "raise the spread" remedy is not applied.

Design-review corrections
D1 (BLOCKING) P3 and S3b are adjudicated on 2017-04-07..END only (real BTAL vs real TAIL), halves split at
   2022-01-03. 2011-09-14..2017-04-06 (real BTAL vs stand-in TAIL) is context, never a verdict.
D2 (BLOCKING) P2 has no confirmed vehicle (stacked ETFs only lever S&P 500, gold and their own trend; lifting
   every leg needs a margin loan). P2 is run at TWO costs: T-bills + 1.50% (IBKR margin, treated as the base;
   the exact tier is to be confirmed) and T-bills + 0.50% (futures / stacked-ETF lower bound). Casey is asked
   which vehicle; Composer cannot borrow, so any leverage also raises a two-broker parity question.
D3 P1 is redefined (the registered version collapsed to the already-measured "KMLM 25%"): each year-end, equal
   risk contribution across the SIX non-TAIL legs from the expanding covariance of weekly T-bill-excess returns
   since the first real KMLM-chain return (2007-02-23), minimum 52 weeks (the live weights are held before:
   first change 2009-01); 25% cap applied inside the solver; TAIL stays 5.9%; target = halfway between live
   and that answer. S1b = the same with no halfway shrink. S1c = P1 with downside semi-covariance.
D4 P2 leaves the max-T family: its ratios are P1's minus a financing drag, so it cannot be a separate
   hypothesis. It is reported as P1's translation into CAGR and drawdown, with no verdict. Gross = min(1.30,
   max(1, realized volatility of L / of P1 since P1 first differed, minimum 252 days)), set each year-end.
D5 P4 leaves the family (trend is 2% of book volatility; both chains are the same fund before 2010): window
   2010-08-04..END, reported as sign only.
D6 Idea 6's primary becomes the large-value swap (8 points of AVUV to AVLV, DFLVX before 2021-09): it isolates
   size and volatility and keeps the value thesis. The QUAL swap and USMV are secondary. Context table:
   DFSVX vs DFLVX vs SPY stand-alone, 1993-03..2007-05.
   => Max-T family = P1, P3, P5, P6 (four arms).
D7 Max-T is studentised by each arm's bootstrap SE; dates are resampled on EXT and each arm uses only the
   resampled days inside its own window.
D8 Sortino is computed on monthly returns (consecutive 21-trading-day compounded excess returns), in the
   observed statistic and in every bootstrap draw. Daily Sortino is about 1.4 x Sharpe and adds nothing.
D9 IMPROVES additionally requires the Phase 1 kill tests: the sign holds on the real-KMLM window 2020-12-03..END
   (P1); the 2020 fall and 2022 episode losses are not worse than L's by more than 1.5 pts (P3); 2017+ is not
   negative unless the 2020 fall was shallower (P5). Sharpe and Sortino vs SPY + T-bills at the arm's
   volatility are printed beside every verdict.
D10 Calibration, printed in the report header: the power of IMPROVES for a true +0.05 Sharpe, and the fact that
   CANDIDATE fires for roughly one arm in four with no effect at all. CANDIDATE can justify a shadow track
   only, never a proposal.
D11 COMBO is relabelled "DISC-selected; menu chosen with sight of CONF" and gets no verdict. Selection on tape 1
   among P1, P3, P4, P5, P6 (P3 on its 2011-09..2017-04 context window, flagged). Mechanics: start from L;
   add each selected static arm's weight change in the order P6, P5, P3, P4; if P1 is selected, scale the six
   legs' sleeve by P1's yearly leg ratios to live and renormalise.
D12 The financing gate is descriptive only and never sets the spread.
D13 "Same-volatility comparison" is restated: Sharpe and Sortino differences vs L are scale-free only when the
   comparison is made at the lower of the two volatilities (scaling up costs more than T-bills). CAGR and
   drawdown comparisons scale L DOWN to the arm's volatility with T-bills, or UP at T-bills + 1.50%.
D14 Leverage gate tests added: gross 1.0 reproduces P1 exactly; S2b's Sharpe equals L's minus the analytic
   financing drag within 0.005; years in which the 1.30 cap binds and the range of realized gross are reported.

D15 (found by the D14 gate test, before any arm result) Leverage is modelled as CONSTANT GROSS, reset daily:
   g x the unlevered book, the borrowed part pays T-bills + spread, the daily reset trade pays 5 bps. That is
   what a stacked ETF, a futures overlay or a managed loan does. Run through the band engine instead, a 1.2x
   loan is not rebalanced until a leg drifts 20%, so gross floats up in drawdowns; that unmanaged version is
   kept as a secondary (P2drift) to show the cost of not managing the loan. S5c uses the same constant-mix form.

Stated before results (reviewer notes)
- The leg ranking behind P1 and P6 comes from one regime; cutting small value after it lagged is
  performance-chasing unless the long history agrees.
- The bootstrap cannot see stand-in bias. Costs x2 is a near-empty test for static arms.
- P2's realized volatility will not equal L's in any given year.

## Post-result notes - 2026-11-19, AFTER the first results
N1 (solver defect, found by the author on first reading the results). The first risk-balance solver minimised the
   squared spread of risk contributions with the cap as a bound. With a negatively correlated leg (2008: the
   trend stand-in vs equity) that problem has more than one local answer and the solver returned a degenerate one
   for the 2009 targets (KMLM driven to about 0 before the halfway shrink). It was replaced by the unique convex
   form (log barrier; a leg above the cap is fixed at the cap and the rest re-solved) with a test for exactly that
   case. Effect on P1: Sharpe difference +0.005 -> -0.013, Sortino +0.010 -> -0.028; S1b -0.004 -> -0.023; P2
   +0.008 -> -0.008. The defect had FLATTERED P1 (less trend, more equity in the 2009 rebound). No verdict
   changed (P1 was NO before and after). First results kept in _cache/results2_prefix.json (not committed).
