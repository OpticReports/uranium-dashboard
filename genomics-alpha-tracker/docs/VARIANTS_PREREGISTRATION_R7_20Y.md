# ROUND 7 — the 20-year core test: pre-registration, 2026-08-22

Registered BEFORE any round-7 code is written or run. Casey: "Need to test a
longer time frame than that, go for 20 years, make a synthetic if needed.
These are too short of time frames." Correct — 5.7 years of real data cannot
adjudicate a defensive book, because it contains no crisis.

## What this round can and cannot answer

**CAN**: the CORE question — B.5 Enhanced vs SPY — from 2006-10-05, which
includes the 2008 crisis, 2011, 2015-16, 2018, 2020 and 2022. That is the
whole point: a book whose claim is "shallower drawdown" must be judged on
the drawdowns the short window never contained.

**CANNOT**: anything involving the R2-A sleeve. R2-A's curve begins
2016-01-04 because that is where the tracker's signal replay begins.
Extending it to 2006 is not a data fetch — it requires re-running the replay
over a 20-year genomics universe including delisted and acquired names plus
a point-in-time catalyst calendar back to 2006. The survivorship problem
would be far worse than the one already caveated in the 10-year replay.
**No blend arm is registered this round.** If a 20-year blend is wanted, it
is a separate project that must start with a survivorship audit.

## Data lane (fixed in advance)

FMP `historical-price-eod/dividend-adjusted` (`adjClose`, total return),
2006-10-05 → 2026-08-19, capped at 5,000 rows by the plan.
**Cross-validation gate, run BEFORE any result is computed**: over the
overlap with the existing stockanalysis lane (2016-08-23 →), the two sources
must agree on daily returns for SPY, GLD, EEM, IWN, DLS and XBI to within
5 bps RMS. If any ticker fails, the round STOPS and reports the discrepancy
rather than picking the friendlier source.

## Proxy map (fixed in advance — this is where freedom to flatter lives)

| leg | w | 2006 source |
|---|---|---|
| AVUV | .25 | SLYV (overlap corr 0.976, TE 6.1%) |
| AVDV | .19 | DLS (0.960, 5.6%) |
| AVEM | .10 | EEM (0.984, 4.0%) |
| PHYS | .18 | GLD (same underlying metal) |
| QUAL | .09 | SPY before 2013-07-18 — a CRUDE stand-in, registered as such |
| KMLM | .14 | WTMF 2011-01-05+; **no instrument exists before that** |
| TAIL | .05 | **no instrument exists before 2017-04-06** |

Splice rule: real fund returns wherever they exist; before inception the
proxy's OWN returns, unadjusted — no alpha added, no beta scaling.
BIL is proxied by SHY before 2007-05-30.

## The unproxiable legs — three treatments, all reported

KMLM (14%) before 2011 and TAIL (5%) before 2017 have NO instrument. Rather
than pick one, run all three and report the spread as the answer:
- **T1** proxy-where-possible, cash (SHY/BIL) in the gap;
- **T2** reallocate the missing leg pro-rata to the others in the gap;
- **T3** cash for the whole leg across the whole window (the pessimistic
  corner for a book that claims crisis protection from them).
A conclusion that does not hold across T1-T3 is not a conclusion.
Sensitivity, additionally reported: QUAL reallocated instead of SPY-proxied.

## Judgment protocol

Carried from rounds 4-6: both Sharpe bases, standard Sortino, paired block
bootstrap (21d blocks, 4000 draws, seed 20260822) on the DIFFERENCE vs SPY,
sub-periods, and no post-hoc amendment. Sub-periods this round are NOT equal
thirds — they are named regimes fixed here: **GFC 2007-10-09→2009-03-09**,
recovery 2009-03-10→2019-12-31, COVID 2020-02-19→2020-03-23, 2022
2022-01-03→2022-10-12, and the round-4/5 real window 2020-12-03→2026-08-19.
Report max drawdown and recovery time for each, per treatment.

## The honest prior, recorded in advance

At the 2006 start, 19% of B.5 (KMLM + TAIL) has no stand-in and another 9%
(QUAL) is crude — 28% of the book is assumption. The 2006-2016 decade was
also a period in which US large-cap beat value, international and gold
decisively. The prior is therefore that B.5 LOSES on return over 20 years
and the open question is only whether it wins enough on drawdown to matter.
Nothing here may be promoted; a survivor becomes a HYPOTHESES.md entry
(TUNING.md law).
