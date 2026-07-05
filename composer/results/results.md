# Regime-gate experiment — KMLM switcher variants

Date: 2026-07-05 · Backtest window: **2022-04-13 → 2026-07-03** (1,057 trading
days; SVIX inception clamps the start) · Engine: v2, $10k, reg+TAF fees,
0.05% slippage · Backtest-only — **nothing was invested or deployed.**

## Symphonies

| Version | ID | What it is |
| --- | --- | --- |
| Original | `rhZ9oDAUvN26v5Ra5qql` | "Simons KMLM switcher (single pops) V2 (Buy Copy)" — untouched |
| Copy A | `gRwiDs9bEHhW3vjXrNdW` | "KMLM switcher — TREND GATE ONLY": whole tree wrapped in `IF SPY > 200d SMA`, else 100% BIL |
| Copy B | `F9yaDwptEh8MOnNy3CIl` | "KMLM switcher — FULL REGIME v1": trend gate + all 11 pop-leg UVXY allocations replaced with VIXY/VIXM term-structure switch (UVXY vs SVIX) + risk-off sleeve (VIX-term → UVXY25/BIL75; TQQQ RSI<20 → SPXL50/BIL50; else top-1 RSI of SQQQ/TLT/KMLM) |

App URLs: `https://app.composer.trade/symphony/<ID>`

Note: the spec estimated ~6 bare-UVXY pop legs; the actual tree has **11**
(QQQE, VTV, VOX, TECL, VOOG, VOOV, XLP@75, TQQQ, XLY, FAS, SPY — the TQQQ leg
wraps its UVXY in a `wt-cash-equal` container, handled). RSI<30/25 pop-bot
legs and the XLK/KMLM rotator were left untouched; all thresholds unchanged.

## Comparison

| Metric | Original | Copy A (gate only) | Copy B (full regime) |
| --- | ---: | ---: | ---: |
| CAGR | **+600.8%** | +180.9% | +65.7% |
| Max drawdown | 32.0% | 32.0% | **50.0%** |
| MAR (CAGR/maxDD) | **18.75** | 5.64 | 1.31 |
| Sharpe | **2.89** | 2.06 | 1.15 |
| 2022 return (from 4/13) | **+1,667%** | −12.3% | −30.1% |
| 2025 return | **+54.3%** | +1.7% | +26.0% |
| Worst 30-day return | −27.2% | −27.2% | −29.8% |
| Days in risk-off sleeve | 0% | 23.3% | 23.3% |

Copy B pop-trigger resolution: of **126** trading days where an RSI-overbought
pop fired (gate-on, 100% in the vol leg), **114 (90.5%) resolved to SVIX** and
only 12 (9.5%) to UVXY.

## Reading

- **The trend gate destroyed returns without reducing risk.** Copy A's max
  drawdown is *identical* to the original (32.0%) — the strategy's worst
  stretch happened **while SPY was above its 200d SMA**, so the gate never
  fired when it mattered. Meanwhile being in BIL 23% of days forfeited the
  2022 vol harvest (+1,667% → −12.3%), which is where most of the original's
  edge lives.
- **The VIXY/VIXM switch made the vol leg worse, not better.** 90% of
  overbought pops resolved to SVIX (short vol) — but the pop legs fire on
  *equity* overbought signals, which historically preceded the vol spikes the
  original was harvesting with UVXY. Copy B is effectively short vol at the
  exact moments the original was long vol; hence the 50% drawdown.
- Standing caveat from the sweep study (`sweeps/qqqe-uvxy-threshold.json`):
  the original's full-window stats are heavily in-sample; its own
  out-of-sample Sharpe (post-2025-07) is ~1.0. But these variants are worse
  in *both* regimes except Copy B's 2025 (+26% vs +54% original).

**Verdict: keep the original. Neither variant survives contact with the data.**
Both copies remain saved (uninvested) for further iteration — candidate next
steps: gate on the *vol leg only* rather than the whole tree, or invert the
VIXY/VIXM comparator (the current direction is empirically backwards for
these entry points).

Artifacts: `fixtures/original_symphony.json` (pre-experiment backup),
raw backtests in session scratchpad; summary JSON inline here.
