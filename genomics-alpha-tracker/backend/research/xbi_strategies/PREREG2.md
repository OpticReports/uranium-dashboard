# XBI study, round 2 — "need better CAGR" (pre-registered BEFORE any variant ran)

**Casey, 2026-10-01, on reading round 1:** "need better CAGR."

Round 1 judged on drawdown at near-equal CAGR and nothing passed. This
round judges on CAGR: the benchmark is still XBI buy & hold (11.9% /
64% DD, 2007-11 → 2026-10), and the question is what beats its CAGR
without a worse hole. Same engine (positions carried, costs on the full
move, cash at BIL, margin at BIL + 1.5%/yr, ETF 5 bps/side, LABU/LABD 10
bps + 8%/yr borrow), same calendar, same start.

**Judging rule (frozen).** A variant passes if, on the full window, (a)
CAGR ≥ XBI's + 2 pp, (b) max DD ≤ XBI's, and (c) CAGR > XBI's in at
least 2 of the 3 sub-periods (2007-11→2012, 2013→2018, 2019→2026-10).
Every passer then gets two sensitivity rows that must ALSO pass: margin
spread +1 pp (BIL + 2.5%) and all trading costs doubled. Sharpe, Calmar
and gross exposure are reported for every row.

**Variants (frozen; one idea each; no tuning after the first run):**

| id | idea | rule |
|---|---|---|
| L1 | constant 1.25× XBI | monthly re-level, margin on the excess |
| L2 | constant 1.5× XBI | same |
| L3 | constant 2.0× XBI | same |
| L4 | LABU buy & hold | the 3× daily-reset ETF, held (2015-06 →) — the decay check |
| L5 | 50/50 XBI/LABU, weekly rebalance | the rebalancing-premium idea (2015-06 →) |
| L6 | short LABD 33% | ≈ 1× long biotech with the inverse ETF's decay as a tailwind; monthly re-level; 8% borrow (2015-06 →) |
| L7 | short LABD 50% | ≈ 1.5× version |
| G1 | levered trend | 2× XBI when close > SMA200, else BIL; trade on flips |
| G2 | levered trend, soft | 1.5× above SMA200, 0.5× below |
| G3 | levered vol target | w = min(2.0, 0.35 / realized 20d vol), 5pp band |
| G4 | trend × levered vol target | G3 sizing only above SMA200, else BIL |
| X1 | buy dips in an uptrend | 1.0 base; 1.5× while close > SMA200 AND 1y drawdown > 10%; else 1.0 |
| X2 | contrarian lever | 1.0 base; 1.5× while 1y drawdown > 25%; back to 1.0 at a new 1y high |
| S3 | seasonal lever | 1.5× Nov–Mar, 0.75× Apr–Oct |
| M2 | cross-asset momentum, top-1 | best 12-1 momentum of {XBI, SPY, QQQ, IWM, GLD, TLT} if > 0, else BIL; monthly |
| M3 | cross-asset momentum, top-2 | equal-weight the best two (each must be > 0); monthly |
| M4 | XBI-anchored rotation | 50% XBI fixed + 50% in the top-1 momentum of {SPY, QQQ, IWM, GLD, TLT}; monthly |
| RP2 | levered inverse-vol XBI/TLT/GLD | round-1 R1 levered to a 30% vol target, cap 2.5×, margin |
| RP3 | levered inverse-vol XBI/QQQ/GLD/TLT | four-asset version, 25% target, cap 2.5× |

**Stated up front.** Leverage is the only reliable CAGR dial and it is
the same dial that deepens the hole; constant-leverage CAGR on one path
is a fact about that path's volatility, not an edge. LABU/LABD rows
depend on an assumed borrow rate that in practice spikes when the trade
hurts. Cross-asset rotation is no longer "trading XBI"; it is listed
because Casey asked for non-conventional ideas and it is the honest
alternative to leverage. All in-sample, one 19-year path, two major
drawdowns. **Never present any CAGR here as a forecast.**
