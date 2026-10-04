# Re-basing the variant campaigns on a committed price cache (2026-10-04)

## Why

Rounds 1-3 (`BACKTEST_VARIANTS_10Y.md`, `_R2.md`, `_R3.md`) and the
executor-mirror backtest were produced on a bars cache fetched from the raw
Yahoo chart API on 2026-08-20. That cache was built in a cloud session, was
gitignored, and no longer exists anywhere. Every script that reproduces a
stored book (`backtest_variants_r2.py` against V2/V6b, `_r3.py` against
R2-A, `backtest_executor_mirror.py` against R2-A) therefore refused to run on
any refetched cache, and the Calls Log's "Run 10-year replay" button could
never publish. Casey chose to re-base on a cache that can be committed.

## The frozen cache

`backend/data/backtest_bars.json` (33 symbols, 2015-07-23 → 2026-08-19),
`spy_bars_raw.json`, and the sidecar `backtest_bars_basis.json`, built by
`scripts/refresh_backtest_bars.py` from FMP's dividend-adjusted endpoint and
now committed (gitignore exceptions). Three properties matter:

- **Truncated at the registered window end, 2026-08-19.** With later bars
  present, round 2 graded exits that fall outside the window (5,002 rows
  regraded vs 4,964) and R2-A moved a further 6%.
- **Segment-aware basis normalization.** FMP applied ATAI's August 2026 split
  factor to history only, so rows before 2026-08-10 sit at 0.0728x the frozen
  entry basis and rows from that day on sit at it. The first draft divided the
  whole series by the factor, put the post-break rows 13.7x too high, and V7,
  the one book holding ATAI that week, printed a +95% day and a −48% day, lost
  a fifth of its Sharpe and flipped its survival verdict. The factor now applies
  only to the segment the frozen entries sit in (a one-day jump of ~1/factor
  marks the break); a near-unity factor (ILMN, 0.999) applies to the whole
  series. Both are recorded in the sidecar.
- **One known bad print.** MRNA's 2023-05-30 bar in the dividend-adjusted lane
  sits 2.44% above FMP's unadjusted series for that day (all neighbouring
  days agree exactly; MRNA pays no dividend). One bar of 1,934; it cannot move
  a verdict and is left as delivered so the cache stays a verbatim record of
  the lane. Found by the independent verifier, 2026-10-04.
- **Reproducible by construction.** The mirror's machinery check now reads
  `cache_verified: true, cache_exact: true` (R2-A to $0.000003). On Render the
  script seeds the committed cache from the image before any refetch decision.

## What moved, and what did not

Every survival verdict in rounds 1-3 is unchanged. Books that re-grade
individual positions reproduce to the dollar (V0 $208,755 vs $208,760). Books
whose path depends on the exact OHLC - trailing exits (V10, R2-A), momentum
rankings (V6a/V6b, R2-E) and the blends built on R2-A - moved by 2% to 9%,
because sub-basis-point differences between FMP's adjustment and Yahoo's shift
a trailing exit or a rank by a day and the capped book is path-dependent from
there. No drawdown changed by more than 0.1 pp.

| round | variant | end (Yahoo basis) | end (FMP basis) | Δ | max DD | Sharpe | survives |
|---|---|---|---|---|---|---|---|
| Round 1 | V0 | $208,760 | $208,755 | -0.0% | 65.5% → 65.5% | 0.42 → 0.42 | — |
| Round 1 | V1 | $261,417 | $261,404 | -0.0% | 34.6% → 34.6% | 0.57 → 0.57 | True → True |
| Round 1 | V2 | $261,677 | $261,671 | -0.0% | 33.7% → 33.7% | 0.58 → 0.58 | True → True |
| Round 1 | V3 | $142,413 | $142,456 | +0.0% | 43.2% → 43.2% | 0.28 → 0.28 | False → False |
| Round 1 | V4 | $200,231 | $200,252 | +0.0% | 29.2% → 29.2% | 0.51 → 0.51 | False → False |
| Round 1 | V5 | $160,457 | $160,456 | -0.0% | 39.0% → 39.0% | 0.34 → 0.34 | False → False |
| Round 1 | V6a | $1,707,763 | $1,638,484 | -4.1% | 82.4% → 82.4% | 0.80 → 0.80 | True → True |
| Round 1 | V6b | $733,261 | $703,698 | -4.0% | 50.1% → 50.1% | 0.73 → 0.72 | True → True |
| Round 1 | V7 | $255,160 | $255,160 | +0.0% | 55.2% → 55.2% | 0.51 → 0.51 | True → True |
| Round 1 | V8 | $119,924 | $119,924 | -0.0% | 45.7% → 45.7% | 0.20 → 0.20 | False → False |
| Round 1 | V9 | $157,334 | $157,147 | -0.1% | 67.3% → 67.3% | 0.30 → 0.30 | False → False |
| Round 1 | V10 | $271,941 | $286,702 | +5.4% | 35.3% → 35.4% | 0.55 → 0.57 | True → True |
| Round 1 | XBI | $254,101 | $254,046 | -0.0% | 63.9% → 63.9% | 0.43 → 0.43 | True → True |
| Round 1 | SPY | $454,114 | $453,801 | -0.1% | 33.7% → 33.7% | 0.89 → 0.89 | True → True |
| Round 2 | R2-A | $430,406 | $469,242 | +9.0% | 35.6% → 35.6% | 0.73 → 0.76 | True → True |
| Round 2 | R2-B | $421,473 | $430,140 | +2.1% | 43.6% → 43.6% | 0.62 → 0.62 | True → True |
| Round 2 | R2-C | $354,858 | $364,052 | +2.6% | 54.7% → 54.7% | 0.52 → 0.52 | False → False |
| Round 2 | R2-E | $2,047,374 | $1,964,314 | -4.1% | 47.8% → 47.8% | 0.94 → 0.93 | True → True |
| Round 2 | R2-D-V2 | $299,402 | $299,395 | -0.0% | 32.3% → 32.3% | 0.65 → 0.65 | — |
| Round 2 | R2-D-V6b | $805,017 | $772,561 | -4.0% | 50.0% → 50.0% | 0.76 → 0.75 | — |
| Round 3 | R3-A | $494,971 | $507,841 | +2.6% | 29.3% → 29.3% | 1.04 → 1.06 | True → True |
| Round 3 | R3-B | $416,865 | $422,283 | +1.3% | 30.2% → 30.2% | 0.98 → 0.98 | False → False |
| Round 3 | R3-C | $615,272 | $635,375 | +3.3% | 35.7% → 35.7% | 0.98 → 0.99 | False → False |
| Round 3 | R3-D | $378,937 | $408,942 | +7.9% | 30.5% → 30.6% | 0.94 → 0.98 | False → False |
| Round 3 | R3-E | $509,413 | $525,647 | +3.2% | 29.7% → 29.7% | 1.04 → 1.06 | True → True |

Round 3's H13 30/70 baseline: +16.17% trading-day CAGR / 29.4% maxDD / 1.04
Sharpe (was +15.89% / 29.3% / 1.02). The constants edited to the re-based
values, each with the superseded value kept beside it: `R2A_END` in
`backtest_variants_r3.py` (469,241.76, was 430,406.29) and the `H13` targets
there; `R2A_END_VALUE` in `backtest_core_variants.py` is deliberately NOT
changed (next section).

## What was not re-run, and why

Rounds 4-6 (`backtest_core_variants.py`: the sleeve, SPY-core and
correlation studies) read the R2-A sleeve as a frozen dollar curve and price
their core legs through stockanalysis.com, which the re-basing environment
could not reach (HTTP 403). They were not re-run. Their stored results stay
consistent with the inputs they were produced from: the Yahoo-basis sleeve
is archived as `r2a_daily_yahoo_2026-08.json` / `r2a_exposure_yahoo_2026-08.json`
and the harness now reads those files explicitly. Do not quote a round 4-6
number beside a re-based round 2-3 number without re-running rounds 4-6 on
the re-based sleeve first. Rounds 7-8 run on their own frozen 20-year lane
and are unaffected.

## Executor-mirror backtest (first publishable run)

With the committed cache the mirror's machinery checks pass and it publishes
for the first time. PRIMARY 0/100 book (`exec_t2_carry`): +11.5% CAGR /
29.4% maxDD / 0.64 Sharpe over the full window; 30/70 with the executor's
band rebalance (`blend3070_t2_carry`): +14.5% / 28.3% / 0.97. The paper R2-A
reference on the same cache: +15.7% / 35.6% / 0.76. Full tables and the
bootstrap cones are in `BACKTEST_EXECUTOR_MIRROR.md`.

## Verification

Counter-agent rounds on this re-basing are recorded at the foot of this
file.

## Counter-agent verdict

_Appended when the verification agents report._
