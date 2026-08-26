# RESEARCH_CARRY.md — can a funding-carry sleeve (Flood framework) beat S6?

Question (Casey, 2026-08-26): test the "HYPE framework" carry structure —
long spot, short perp, collect funding, scale the hedge — against our live
BTC engine (S6 blend). Venue constraint from Casey: **Hyperliquid or
Coinbase only**. 2y + long-window backtests on pre-registered variants.
"4y" is honestly **3.3y**: Hyperliquid's BTC funding history starts
2023-05-12; there is no HL funding to backtest before that, and INTX 2023
prints are launch-period junk (excluded, shown in the funding chart).

Script: `backend/scripts/research_carry.py` (pre-registration in
docstring, post-audit corrections logged there). Data: Bitstamp 4h spot
bars (`fetch_bars.py`), HL + INTX hourly funding (`fetch_funding.py`),
S5/S6 bench curves (`bench_blend.py`, fresh replay per window so no
trade carries pre-window P&L across the boundary). Reproduce:
`python3 backend/scripts/fetch_bars.py <dir>/bars_4h_btcusd_ext.csv`,
`python3 backend/scripts/fetch_funding.py <dir>`,
`python3 backend/scripts/bench_blend.py <dir>/bars_4h_btcusd_ext.csv <dir>`,
then `python3 backend/scripts/research_carry.py <dir>`. Verified
2026-08-26: reruns to the identical table values; counter-agent
independently reproduced every headline number (V6 curves to 1.5e-5).

## Headline answer

1. **Pure carry does not compete with S6 on return.** Best pure variant
   on the 2y window (V4, funding-scaled hedge) made +36.6% total vs S6
   +72.8%. And the carry yield is less than it looks: V1's 2y CAGR of
   14.4% = **10.4% mean funding × 1.39 average notional growth** — the
   short rides the bull market up. At flat prices the same funding pays
   ~10.4%/yr (2y) / ~14.4%/yr (3.3y). 2026 YTD it is running at 4.5%.
2. **The framework's payload is the blend: V6 = 70% S6 + 30% pure carry
   (30d rebalance, registered up front) beat S6 on risk on both
   windows** — 2y MAR 1.51 vs 1.15 (CAGR 28.6% vs 32.6%, shallower DD),
   3.3y MAR 1.77 vs 1.02 with HIGHER CAGR (31.5% vs 28.9%). The ranking
   survives the exit-step→MTM correction (V6 MAR floor 1.32/1.53 vs S6
   MTM-corrected 0.99–1.11). **But the audit's decomposition shows what
   it is**: of the 3.3y MAR edge, +0.47 is simply the carry sleeve's
   return LEVEL, +0.12 is dilution/cash mechanics (70/30 S6+cash@4%
   already posts 1.20 — MAR mechanically rewards dilution), +0.10 is
   timing. At 2026 funding (~4.5%) the sleeve ≈ cash and the edge ≈ 0.
   **Verdict: a funding-regime option, not a standing upgrade to S6.**
3. **Hedge-timing dials are not worth their turnover.** Trend bands
   (V3a/b, 10–30x/yr turnover) land below static hedges on MAR. V4
   (funding-scaled) earns its fees only on the 2y window; on 3.3y the
   boring static-75% hedge beats it (MAR 1.56 vs 1.34). Same lesson as
   the win-rate study: the dumb version of the idea is the robust one.
4. **The subsidy is decaying — the study's biggest forward risk.** Mean
   annualized BTC funding (short receives): HL 15.1% (2023) → 24.1%
   (2024) → 10.6% (2025) → **4.5% (2026 YTD)**; INTX 12.9% → 6.0% →
   1.9%. The V6 backtest is built on 2023–25 funding that is not
   currently on offer.

| variant (h = hedge share) | 2y CAGR | 2y MAR | 3.3y CAGR | 3.3y MAR |
|---|---|---|---|---|
| V0 hold BTC | 10.9% | 0.20 | 38.6% | 0.72 |
| V1 carry 100% hedged | 14.4% | n/a* | 27.8% | n/a* |
| V2c static h=0.75 | 13.5% | 0.85 | 30.7% | **1.56** |
| V3a trend-band h | 10.7% | 0.33 | 32.1% | 0.87 |
| V4 funding-scaled h | 16.9% | 0.84 | 33.3% | 1.34 |
| V5 flush-cover h | 16.1% | 0.48 | 35.3% | 0.92 |
| **S6 blend (live engine)** † | **32.6%** | **1.15** | 28.9% | 1.02 |
| **V6 = 70% S6 + 30% V1** ‡ | 28.6% | **1.51** | **31.5%** | **1.77** |

\* V1's drawdown-based stats are model artifacts on BOTH windows (spot
and perp marked at the same price, so basis swings are invisible); its
CAGR is the honest number. No V6-vs-S6 Sharpe comparison is quoted
anywhere in this doc — the two are computed on different bases.
† S6 bench curves span first→last exit (1.94y / 3.25y), so CAGR — not
total — is the comparable column.
‡ V6 maxDD −18.9% (2y) / −17.7% (3.3y) are exit-step-sleeve figures;
true MTM runs up to ~2.8pp deeper → MAR floors 1.32 / 1.53. S6's own
MTM correction drops it to ~0.99–1.11 / ~0.89–0.99, so the ranking holds.

## What we learned from the framework

- **Tested:** the funding-capture leg (long spot / short perp at hedge
  ratio h) and the portfolio claim (carry as a sleeve beside a
  directional book) — the part implementable on our venues with real
  data. **Not tested:** cross-venue basis capture, dated-futures basis
  roll, the options overlay, inventory shuttling, discretionary sizing.
  No claim about those either way.
- **Implementation reality:** the short leg needs **INTX perps**
  (funding-paying) — CDE-style dated futures earn basis roll, not
  hourly funding, and would be a different study. The backtest assumes
  **unified collateral** (spot longs margin the short). Realistic on
  INTX portfolio margin; NOT how Hyperliquid works (isolated USDC
  margin), so HL execution would carry margin/liquidation risk on the
  short leg this model does not price.
- **Fees:** 6bp/side, rebalance band 5pp. Statics turn over ~0.5x/yr,
  V4 ~14–22x/yr, V3b ~30x/yr — the dial variants' edge dies in fees
  (fees verified = turnover × 6bp exactly).

## Counter-agent panel

Adversarial audit run before these findings were presented (house rule).
Overall verdict: **WEAKENED, not fatal** — mechanics clean, two headline
numbers corrected, framing reframed (all applied above).

| lens | verdict | key finding |
|---|---|---|
| Look-ahead | **PASS** | h decided at bar close from data ≤ t (grep + slice audit); lag-1 rerun IMPROVES funding-conditioned variants (V4 2y MAR 0.84→0.96) — no leaked timing edge; published numbers are the conservative side |
| Accrual/sign/marks | **PASS** | accrue→decide→adjust order verified; +rate credits the short (HL/INTX convention); hourly-vs-close marks move V1 CAGR by <0.01pp. Docstring missing-hours count corrected 88→570 (567 in HL's first 7 weeks; conservative) |
| Fees/cash accounting | **PASS** | fees == turnover×6bp exactly, all variants; first-bar residual +$0.04 benign; entry fees (~12bp one-time) excluded from curve base — flagged, sub-noise |
| V6 composition | **PASS w/ disclosures** | reproduced to 1.5e-5: causal ffill of S6 exit-step curve, 30d-rolling rebalance, 2×6bp fees (conservative). Exit-step DD label + MTM floors now mandatory (applied in table) |
| Selection / nulls | **MIXED — decisive** | V6 spec pre-registered (not tuned), but nulls decompose the 3.3y edge: carry LEVEL +0.47, dilution+cash +0.12, timing +0.10; shuffled-funding null 1.67 vs actual 1.77; S6+cash@4% 1.20 beats S6 too (MAR rewards dilution). At 2026 funding, edge ≈ 0 |
| Stats recompute | **PASS** | independent recompute matches to 3 decimals; V1 3.3y MAR now masked like 2y; S6 "2y" spans 1.94y → CAGR-based table |
| Headline (a) | **FAIL → replaced** | "V1 CAGR == mean funding" was a price-path coincidence (10.4% × 1.39 notional growth); replaced with the decomposition in headline 1 |
| Framing | **corrected** | positive-funding hours 87.0% (docstring said ~76%); "any hedged book beat S6 on 3.3y MAR" was near-inevitable in this window — what is carry-specific is the +0.47 level, which is decaying |

Panel's one-line verdict, quoted: "keep it as a funding-regime option,
not a standing upgrade to S6."

## Open questions (ranked)

- **P1 — funding persistence.** The V6 case needs funding ≥ ~8%/yr;
  2026 YTD is 4.5% (HL) / 1.9% (INTX). Decide: deploy small and meter
  realized funding vs park until it mean-reverts. Moves: whether V6 is
  worth implementing at all.
- **P2 — venue for the short leg.** INTX portfolio margin vs HL
  isolated USDC — changes collateral efficiency, liquidation topology,
  and whether the unified-collateral assumption holds. Moves: realized
  carry net of margin drag.
- **P3 — bear-regime behavior.** No 2022-analog in sample; in a deep
  bear funding goes negative (shorts PAY) exactly when the hedge
  matters. S6's leg has a 2022 record; the carry leg does not. Moves:
  tail sizing.

## Honesty box

- S6/V6 blend curves are exit-step (trade-close basis); MTM runs
  deeper — table carries the corrected floors. Carry variants are
  bar-close MTM. Curve timestamps are bar-open with close NAVs
  (uniform 4h cosmetic shift; noted for follow-ups).
- Bull-regime sample: 87.0% of HL funding hours positive, no bear year.
  Both the carry income and the diversifier claim are regime-conditional,
  and the null decomposition says the edge is mostly the funding level.
- Unified collateral assumed; no margin interest, liquidation, or basis
  MTM on the hedged pair. Entry fees (~12bp one-time) excluded from
  curve base.
- In-sample MAR/CAGR describe 2023–26; nothing here is a forecast.
- NOTHING from this study changes any config, sizing, or the live plan
  (S5 live, KELLY_M ramp per EXECUTOR.md). Parked pending P1/P2.
