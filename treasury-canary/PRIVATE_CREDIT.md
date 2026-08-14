# Private Credit — research memo & proposed analytics suite (2026-08-01)

Context: the canary's private-credit pin channel is RED; operator is
considering a private credit fund investment. This memo grounds a monitoring
suite in what is actually observable. Core problem: private credit grades its
own homework (quarterly appraisal marks, no market prices) — every serious
analytic is either a LISTED PROXY that trades daily or an adjustment for the
smoothing in reported returns.

## Study 1 — the listed complex TODAY (FMP daily closes, 2026-07-31)

| proxy | what it is | off 52w high | 6m return | 1y vol |
|---|---|---|---|---|
| BIZD (BDC ETF) | listed direct-lending sector | **−23.4%** | −12.3% | 20% |
| ARCC | largest BDC (quality) | −17.3% | −6.9% | 20% |
| BXSL | Blackstone senior-loan BDC | −26.8% | −10.9% | 21% |
| TSLX | Sixth Street (quality) | −30.7% | −22.5% | 26% |
| FSK | FS/KKR (weak book) | **−49.5%** | −23.5% | 33% |
| OXLC / ECC | CLO equity funds | **−51% / −50%** | −36% / −33% | 36% |
| JBBB/JAAA ratio | CLO mezz vs AAA | 0.954 → 0.936 over 1y (grinding lower) | | |
| BKLN (lev loans) | liquid senior loans | −3.2% | −1.6% | 3% |
| HYG (liquid HY) | liquid high yield | −2.3% | −1.9% | 4% |

**The divergence is the finding**: liquid credit is CALM (HYG/BKLN within 3%
of highs) while every listed private-credit vehicle is in a 20-50% drawdown,
with the junior-most exposures (CLO equity, weak BDCs) down most. The listed
market is repricing private credit specifically — not credit generally.
Historically BDC prices lead NAV marks by 2-4 quarters (2008, 2015-16 energy,
2020). This corroborates the pin channel RED with market prices.

## Study 2 — what listing reveals about "low-vol" private credit

Same asset class, listed vs appraisal-marked: 2020 peak-to-trough BIZD
−55.6%, ARCC −58%, CLO equity −68..−75%, while appraisal-based private credit
indices (e.g. Cliffwater CDLI) reported roughly −5% and 2-3% annual vol
[literature; not API-verifiable]. Implied smoothing factor ~5-10x. BIZD's
1-year beta to HYG is **2.15** (corr 0.45): listed private credit behaves as
LEVERED liquid credit (BDCs run ~1.0-1.25x D/E on top of loan books —
arithmetic checks). De-smoothed, an unlevered direct-lending book is
plausibly ~8-12% vol with equity-like left tails, i.e. Sharpe ~0.6-0.9 — not
the ~3 the reported series implies.

## Proposed analytics suite ("Private Credit Health Monitor")

A. **BDC NAV-discount composite** (headline gauge). Daily price / last
   reported NAV for ~8 large BDCs (NAV = small quarterly-maintained config
   table; prices via FMP). Sector median discount + dispersion + z vs
   history. THE canonical market-implied health read; discounts >15% have
   historically marked capitulation/entry zones, premiums >5% froth.
B. **Listed-proxy stress index** (fully automatable now). Composite z of:
   BDC basket drawdown & 60d momentum, CLO-equity (OXLC/ECC) drawdown,
   JBBB/JAAA ratio, BKLN drawdown, BDC-HYG return gap (the divergence above,
   the single best early signal). Daily; feeds the pin channel.
C. **Financing-pipe monitor**: Fed H.8 bank loans to nondepository financial
   institutions (weekly growth — banks fund the funds), SLOOS C&I tightening
   (quarterly), HY OAS level/momentum. Deteriorating pipe + wide listed
   discounts = the refinancing-wall scenario.
D. **Smoothing-adjusted risk calculator**: Geltner/AR(1) de-smoothing of any
   reported fund return stream; "mark gap" estimate = BDC sector price TR
   minus NAV-implied TR (how much marking-down is queued); fee-stack
   netting (mgmt on invested + incentive over hurdle + leverage cost).
E. **Entry-timing gate (vintage discipline)**: deployment scored against
   spread-at-entry (HY OAS / BKLN yield) and the stress index. Literature +
   cycle logic: best net vintages form AFTER capitulation (2009, 2020);
   worst form late-cycle at tight spreads. Rule-of-thumb gate: commit slowly
   while discounts narrow & spreads tight; accelerate when module A shows
   >15% discounts AND liquid spreads have already widened.

## CIO read for the family office (2026-08)

1. Reported PC returns are not comparable to liquid returns until
   de-smoothed and fee-netted; realized illiquidity premium over liquid
   levered credit has been ~1-2pp net historically — real but thin vs a
   5-7y lockup [literature estimate].
2. TODAY: listed proxies are mid-repricing while liquid spreads are tight —
   historically the WORST configuration to commit into (you pay par for
   books about to be marked down). The attractive move is staged: wait for
   the NAV marks to catch down / discounts to peak, then deploy into the
   post-markdown vintage — or buy the listed proxies at capitulation
   (2009/2020 pattern) which monetizes the same premium with liquidity.
3. Manager diligence checklist the monitor should track per-fund:
   non-accruals %, PIK income share (earnings quality), leverage, sector
   concentration, incentive-fee hurdle & catch-up, vintage pacing.

Verification notes: all Study-1 numbers reproducible from
fast_study_cache/pc_proxies.json (FMP price-only; dividends excluded, which
overstates drawdowns by the yield — direction and divergence unaffected).
Smoothing-factor and premium literature figures are knowledge-based estimates
flagged [literature]; the de-smoothing module computes fund-specific numbers
when fed an actual track record.
