# Pre-registered replication — arXiv 2511.12490 "Unicorn Edge" (13-Sharpe claim)

Registered 2026-08-26, BEFORE any replication code was run. Casey's question:
what can we learn for how we build algos; what alpha is real; can the
regime-conditioning idea be applied to our strategies.

## The paper's exact spec (as published, §2)
- Universe: CURRENT S&P 500 constituents (survivorship admitted), 2004–2024.
- Signal: BASE = 0.7·rank(1/price) + 0.3·z(−r_{t−10..t}); cross-sectional.
- Gate: stock-level "drift regime" = >60% positive days in trailing 63d.
- EDGE = BASE × REGIME; z-scored across qualifying stocks; long/short split
  by z sign; each side normalized to 50% gross; daily rebalance at MOC
  (signal 3:45pm from near-close prices, fill at the 4:00 close).
- Costs 0.6bp per unit traded. OOS = three 1-year windows only
  (2010-11, 2015-16, 2020-21). Claimed: OOS Sharpe 13.19, +158.6%/yr @ 12%
  vol, maxDD −11.9%, median daily +0.63%.

## The sin ladder (each rung isolates one suspected artifact)
- R0 VERBATIM: their spec as written, same-close signal/execution (their MOC
  convention on daily data), 0.6bp, current constituents, adjusted closes.
- R1 EXECUTION: identical, but fills at close t+1 (signal frozen at close t).
  Also reported: fill at open t+1. Isolates the same-print/bid-ask-bounce
  artifact their own citation (Lo–MacKinlay 1990) warns about.
- R2 COSTS: R1 + realistic large-cap costs: 3.5bp per unit traded
  (2.5bp half-spread + 1bp impact) instead of 0.6bp.
- R3 WINDOWS: full-period 2006–2024 daily concatenation (not their three
  bull-year windows), per-year table. PIT universe if FMP historical
  constituents reconstruct cleanly; else survivors-only, LABELED, with the
  survivorship bound taken from literature and the paper's own 20–30%.

## Frozen expectations and kill language (written before running)
- E1: R0 reproduces a very large Sharpe (>5). If it does NOT, the paper is
  not even mechanically reproducible from its own spec — report that.
- E2 (the artifact test): if Sharpe(R1) < 0.5 × Sharpe(R0), the edge lives
  in the same-close print — microstructure noise harvesting, not
  cross-sectional alpha; VERDICT "artifact confirmed".
- E3 (deployability bar): a claim of real residual edge requires
  Sharpe(R2, full period) ≥ 1.5 AND positive years ≥ 70%. Below that:
  "no deployable edge"; any application to our strategies is OFF except as
  a separately pre-registered idea test.
- Nothing in this protocol may be retuned after results are seen. Additions
  (e.g. PIT universe if data allows) extend the ladder; they do not replace
  rungs.

## Metrics basis (frozen)
Daily returns; Sharpe = mean/std × √252, rf=0 (stated; BIL-excess would be
lower); ann return = 252·mean (arithmetic) AND CAGR both reported; maxDD on
compounded curve; turnover = Σ|Δw|/2 per day. Costs charged on units traded.
Adjusted closes throughout (split+dividend), FMP.

## Deliverables
Ladder table + per-year table + equity curves (log), drift-regime census
chart, counter-agent verdict logged beside results, memo + artifact. Study
code in this folder; data stays in scratchpad (not committed).
