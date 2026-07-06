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

---

# Addendum 2026-07-05 — three targeted safeguards, tested individually

Motivation: the original's 32% max DD (2025-01-02 → 2025-02-27) happened with
SPY above its 200d SMA on 100% of days, holding TECL/SOXL/SVIX from the
risk-on rotator. Three safeguards aimed at *that* failure mode, each applied
alone to the original (window 2022-04-13 → 2026-07-03; OOS = from 2025-07-01):

| Variant | CAGR | maxDD | MAR | Sharpe | Jan–Feb 25 | OOS CAGR | OOS DD | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original | +600.8% | 32.0% | 18.75 | 2.89 | −32.0% | +61.9% | 28.7% | 1.04 |
| V1 rotator XLK-200d gate | +433.9% | 32.0% | 13.54 | 2.71 | −32.0% | +65.5% | 28.7% | 1.07 |
| V1 @100d | +386.4% | 37.4% | 10.33 | 2.56 | −34.9% | +65.5% | 28.7% | 1.07 |
| V1 @50d | +434.3% | 33.3% | 13.03 | 2.66 | −33.3% | +51.4% | 32.3% | 0.95 |
| **V3 rotator vol cap 75/25** | **+461.6%** | **27.4%** | **16.87** | **2.82** | **−27.4%** | +42.4% | **27.0%** | 0.89 |
| V3 @50/50 | +343.2% | 25.5% | 13.44 | 2.67 | −22.7% | +23.6% | 25.5% | 0.66 |
| V2 TQQQ 60d-DD>20% breaker | +43.5% | **42.1%** | 1.03 | 1.22 | −32.1% | +21.2% | 24.4% | 0.68 |

Findings:

1. **Trend gates cannot see this strategy's crashes.** XLK stayed above its
   200d SMA through the whole Jan–Feb 2025 slide (episode return identical to
   original, −32.0%). Faster windows (100d/50d) only add whipsaw and make DD
   *worse*.
2. **Drawdown circuit-breakers fire too late.** V2 waits for TQQQ to be down
   20% in 60d — by then the loss is taken; it then sits in BIL through the
   V-shaped recovery. Result: worst maxDD of the whole panel (42.1%) at 1/14th
   the return.
3. **Only position sizing works — and it's linear, not free.** The 75/25 vol
   cap cut maxDD 32.0→27.4%, worst-30d −27.2→−22.9%, and the crash episode
   −32→−27.4%, keeping 77% of the CAGR and nearly all the Sharpe (2.82 vs
   2.89). Deeper caps cut DD further at proportional return cost. There is no
   signal here that dodges the drawdown while keeping the upside — the
   drawdown *is* the exposure that earns the returns.

Saved (uninvested): **V3 75/25 → `tbm9SE57MoSeY7rOEhys`**
("KMLM switcher — ROTATOR VOL CAP 75/25"). V1/V2 and the sub-variants were
backtest-only and not saved.

Practical takeaway: control this strategy's risk by *how much capital it
gets* (portfolio-level sizing; see `correlation-backtest.json` inverse-vol
weights) and/or the in-tree vol cap — not by market-timing overlays.

---

# Addendum 2 — 2026-07-05 — six improvement ideas, tested individually

Same protocol: each idea applied alone to the original; full window
2022-04-13 → 2026-07-03; OOS = from 2025-07-01; episode = 2025-01-02 →
2025-02-27 (the original's max-DD window). P5's full window starts
**2023-04-19** (ZVOL inception inside the paired VIX sleeve) — matched
original stats shown for fairness.

| Variant | CAGR | maxDD | MAR | Sharpe | Jan–Feb 25 | OOS CAGR | OOS DD | OOS Shp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original | +600.8% | 32.0% | 18.75 | 2.89 | −32.0% | +61.9% | 28.7% | 1.04 |
| V3 vol cap 75/25 BIL (prior) | +461.6% | 27.4% | 16.87 | 2.82 | −27.4% | +42.4% | 27.0% | 0.89 |
| P1 inverse-vol rotator (21d) | +483.2% | 32.0% | 15.08 | 2.69 | −32.0% | +61.9% | 28.7% | 1.04 |
| P2 vol cap 75/25 KMLM | +461.7% | 27.4% | 16.88 | 2.83 | −27.4% | +42.7% | 26.5% | 0.89 |
| P3 VIX-term pass-through | +369.6% | 40.1% | 9.22 | 2.42 | −23.4% | +89.6% | 40.1% | 1.25 |
| P4 rotator + KMLM/GLD cands | +264.3% | 28.2% | 9.37 | 2.37 | −20.6% | −6.3% | 26.8% | 0.10 |
| **P5 pair w/ VIX strategy 75/25** | +229.9%* | **24.5%** | 9.40 | **2.44*** | −24.5% | +53.4% | **20.4%** | **1.08** |
| Original (P5-matched window*) | +323.2%* | 32.0% | 10.08 | 2.34* | −32.0% | — | — | — |
| P6 pop confirm RSI(5)>82 | +522.7% | 45.5% | 11.49 | 2.77 | −32.0% | +5.0% | 45.5% | 0.41 |

\* 2023-04-19 → 2026-07-03 (803 days).

Findings:

- **P5 is the winner — diversification beats modification.** The paired
  public VIX strategy (`2pOC3xJ0uBNHwrlPiQNh`, independently verified
  earlier) has **+0.06 daily correlation** with the original. The 75/25 pair
  is better on *every risk measure over every window tested*: maxDD 24.5% vs
  32.0% matched, OOS DD 20.4% vs 28.7%, higher Sharpe both full-matched
  (2.44 vs 2.34) and OOS (1.08 vs 1.04), and a softer crash episode. Cost:
  ~⅓ of matched-window CAGR. Saved as **`YPTSJFJwD2ZKfAeYJUbW`**
  ("KMLM switcher + VIX sleeve 75/25"), uninvested.
- **P1 (inverse-vol) was a no-op where it mattered**: the bottom-2 rotator
  picks had similar realized vols in the crash, so weights barely moved —
  identical DD and episode; it only shaved CAGR. Rejected.
- **P2 (KMLM ballast)** ≈ identical to the BIL vol cap; ballast choice is a
  wash at 25%. Keep V3-BIL if using an in-tree cap.
- **P3 (pass-through)** is a live grenade: better episode (−23.4%) and the
  best OOS CAGR/Sharpe of the panel (+89.6% / 1.25), but skipping UVXY pops
  left it long through a later vol event → 40.1% maxDD *in the OOS window*.
  The VIX-term filter direction is genuinely informative but unsafe as a
  hard skip. Possible hybrid for future work: pop → UVXY when stressed,
  pop → BIL when calm (tested as P6-style else already? no — P6 used RSI
  confirmation; the VIX-term else→BIL variant remains untested).
- **P4 (defensive candidates)** looked great in the crash (−20.6%) and then
  died OOS (−6.3% CAGR, Sharpe 0.10): bottom-RSI selection loves whatever is
  falling, so it systematically buys GLD/KMLM weakness during tech rallies.
  Rejected.
- **P6 (pop confirmation)** kept the CAGR but *increased* maxDD to 45.5% and
  collapsed OOS: the RSI(5)>82 filter rejects exactly the early entries that
  made UVXY pops profitable. Rejected.

Running conclusion across all 12 variants tested today: the only two levers
that improved this symphony's risk profile without destroying its engine are
**(a) sizing the rotator exposure** (V3 vol cap) and **(b) pairing with a
near-zero-correlation long-vol strategy** (P5) — both are allocation moves,
not signal moves. Every signal-based override (5 gate styles, breaker,
SVIX switch, candidate widening, entry confirmation) failed out-of-sample.
