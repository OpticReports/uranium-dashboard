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

---

# Addendum 3 — 2026-07-05 — portfolio allocation study

Common window 2023-04-19 → 2026-07-02 (804 days, P5-limited), backtest
curves, daily-rebalanced blends. HG = Holy Grail (`mbkiXcuNDjueXpiox5Av`),
ORIG = KMLM switcher, P5 = KMLM + VIX sleeve (`YPTSJFJwD2ZKfAeYJUbW`).

Correlations: HG~ORIG **+0.30**, HG~VIXstrat +0.12, ORIG~VIXstrat +0.06.
Crash complementarity: Jan–Feb 2025 episode HG −8.1% vs ORIG −32.0%.

Selected blend points (full window | OOS from 2025-07):

| Mix | CAGR | Sharpe | maxDD | OOS CAGR | OOS Sharpe | OOS DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current (HG 79 / ORIG 21) | +129% | 2.15 | 17.8% | +69.1% | 1.60 | 17.8% |
| HG 55 / P5 45 | +151% | 2.49 | 16.3% | +65.2% | 1.63 | 13.8% |
| HG 45 / ORIG 55 (max full Shp w/ ORIG) | +212% | 2.51 | 21.4% | +73.4% | 1.46 | 18.0% |
| HG 35 / P5 65 (max full Shp overall) | +181% | 2.59 | 18.7% | +62.8% | 1.46 | 14.8% |
| HG 40 / P5 60 (matches current DD) | +173% | 2.59 | 17.8% | +63.6% | 1.51 | 14.6% |

Recommendation recorded: swap ORIG exposure for P5 (dominates on risk at
similar OOS return), target the flat optimum band **HG 50–60 / P5 40–50**.
Study only — no capital was moved; execution is a human decision.

---

# Addendum 4 — 2026-07-06 — crash-convexity research

Question: best per-dollar upside/downside positions for a market crash —
max payout in a selloff, minimal bleed while waiting.

Method: identified SPY's four >8% drawdown episodes since 2022 (2022 bear
−24.5%; Aug-2024 spike −8.4%; Feb–Apr 2025 −18.8%; early-2026 −8.9%), then
measured 15 candidates on **crash capture** (return during those episodes)
vs **calm bleed** (annualized return on all other days). Full table in
session data; highlights:

| Candidate | avg crash | calm CAGR | maxDD | verdict |
| --- | ---: | ---: | ---: | --- |
| UVXY (static) | +109.2% | −86.3%/yr | 99.6% | biggest pop, ruinous bleed |
| SQQQ (static) | +77.8% | −72.0%/yr | 97.3% | same problem |
| TAIL / BTAL (tail ETFs) | +10–12% | −16–18%/yr | 36–48% | weak pop, real bleed |
| TLT | −5.9% | −1.5%/yr | 39.9% | failed 2022; broken hedge |
| KMLM | +12.1% | −5.9%/yr | 27.5% | best *static* score |
| GATE→UVXY (custom VIX-term gate) | +72.4% | −62.4%/yr | 90.9% | gating helps, not enough |
| InverseHold-PSQ (`sYcm9hgSipM4TkpFcuSj`) | +45.9% | **+21.8%/yr** | 21.1% | free hedge; slow-bear specialist |
| Frontrun-Bonds (`hA7nbIZL4cdRBzikH47U`) | +23.0% | **+30.3%/yr** | 17.5% | free hedge; fast-spike specialist (Aug-24 +58.4% OOS) |
| **Blend 50/50 of the above** | all 4 episodes positive (+90.7/+27.5/+1.7/+11.5%) | **+48.2%/yr overall** | 14.8% | **winner** |

Blend correlations vs our book: **HG −0.12**, ORIG +0.05, P5 +0.06.
Saved (uninvested) as **"Crash Convexity Sleeve — InverseHold + Bond
Frontrunner 50/50"** — id in CHANGELOG.

Honesty notes: (1) InverseHold's monster 2022 (+157.8%) is in-sample for it
(OOS starts ~2023-04); its OOS crash record is Aug-24 −2.6%, Feb-25 +5.0%,
2026 +23.3% — still net positive with +22%/yr carry. Frontrun-Bonds' Aug-24
+58.4% IS out-of-sample. (2) No static instrument is a free hedge — every
"always-long-vol/inverse" position pays heavy carry; per-dollar-of-bleed the
best static is KMLM, the biggest raw pop is UVXY. (3) The right sizing for a
sleeve like this is 5–15% of the book — it hedges; it shouldn't dominate.

## Addendum 4b — sleeve optimization pass (2026-07-06)

10 variants of the crash sleeve tested (weights, rebalance frequency, third
legs). Kept the original **50/50, threshold rebalance** (`nNdBk7hc5NiBzeRvbI5T`
unchanged). Key numbers (full 2022- window | post-Jun-2024 both-OOS slice):

- Weight sweep 30/70→70/30: performance is nearly flat (CAGR 47–48%, Sharpe
  1.40–1.58) — the blend is **robust to weights**, a good non-overfit sign.
  FB-heavy (30/70) has the best recent slice (+62.8% CAGR, 5.7% DD); IH-heavy
  hedges HG harder (corr −0.17) with more 2022 pop. 50/50 is a sane middle.
- **Rebalance-frequency trap:** switching the root from threshold ("none" +
  corridor) to monthly/quarterly *destroyed* the sleeve (+48% → −1%/−11%
  CAGR). Composer's root rebalance frequency controls how often the whole
  tree's conditions re-evaluate — monthly means the components' daily RSI
  logic only fires monthly. Never change rebalance frequency on
  signal-driven trees.
- Third legs (KMLM 20–34%, gated-VIXM 20%): dilution — lower carry, no
  drawdown improvement worth it.
- VIXstrat 20% leg (40/40/20): best post-Jun-24 risk-adjusted profile
  (Sharpe 1.82, DD 8.1%) but truncates testable history to 2023+ and cuts
  full CAGR to +30%. Optional future upgrade if its live record holds.

## Addendum 4c — deep-history validation + 20y simulation (2026-07-06)

**Rebalance audit (landmine follow-up):** every symphony we created uses
threshold rebalance (`none` + 0.1 corridor) — signals still evaluate daily,
so nothing was exposed to the monthly-rebalance trap. Direct test of `daily`
vs threshold on the sleeve: +49.2%/1.59/14.8% vs +48.2%/1.56/14.8% —
essentially a wash, `daily` marginally better and matches the components'
native setting, so the saved sleeve `nNdBk7hc5NiBzeRvbI5T` was updated to
`daily` (prior version preserved: `OT3P700PVT2iG95wnaLq`).

**Deep history (real limit + proxy):** the composite sleeve's hard data
limit is 2021-01 (KMLM inception, used as an RSI hurdle inside InverseHold;
LABD 2015 next). Two same-class substitutions unlock 15 years: LABD→BIS
(both 2x-inverse-biotech) and KMLM→DBC (broad futures proxy).
FrontrunBonds runs natively from 2011-10.

**Deep-proxy sleeve, 2011-10-05 → 2026-07-02 (3,706 days):**
CAGR +47.6%, Sharpe 1.30, maxDD 16.3%. Crash capture — positive in
**10 of 12** SPY >8% episodes: 2011 +22.3%, 2012 +3.7%, 2015-16 +19.2%,
Volmageddon 2018 +23.5%, Q4-2018 +4.8%, **COVID +172.3%**, Sep-2020 0.0%,
**2022 bear +82.3%**, Aug-2024 +29.4%, Feb-25 +1.3%, 2026 +7.6%.
Calm carry ex-episodes: **+28.7%/yr**. Every era profitable:
2011-15 +39.5%/yr (Shp 0.83), 2016-19 +36.0% (2.13), 2020-21 +127.8%
(2.44), 2022-26 +37.7% (1.54).

**20-year Monte Carlo** (block bootstrap of the 15y daily returns,
`monte-carlo-sleeve-20y.json`): CAGR p05 +31.8% / median +47.2% /
p95 +68.0%; median 20y max drawdown 14.6%, p95 22.2%; P(any 20y window
losing money) ≈ 0.

Caveats, in order of importance: (1) the components were authored
2023-2025 — pre-creation history is rule-replay, not live record, and the
authors may have (consciously or not) fitted rules that look good on this
history; (2) LABD/KMLM substitutions are same-class but not identical;
(3) VIX-complex ETFs don't exist before 2009/2011, so 2008 is untestable in
kind — the closest analogue tested is COVID (+172%); (4) MC resamples this
15y distribution — a genuinely new regime (rates, vol-market structure) is
outside it.
