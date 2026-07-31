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

## Addendum 5 — 2026-07-06 — sleeve full profile + 12-month Monte Carlo (all positions)

Sleeve (real components, daily rebalance, 2022-01→2026-07): **CAGR +49.3%,
Sharpe 1.59, maxDD 14.8%** (15y deep-proxy: +47.6%/1.30/16.3%).
Correlations (804 common days): SLEEVE~HG **−0.124**, ~ORIG +0.054,
~P5 +0.057, **~target book (HG55/P5 45) −0.040**.

12-month Monte Carlo (block bootstrap of each position's own backtest
history, 5,000 sims; `monte-carlo-12mo-all.json`):

| Position | p05 | median | p95 | P(loss) | DD p50/p95 | P(DD>20%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SLEEVE | +4% | +47% | +130% | 3.0% | 10.5%/18.0% | 2.6% |
| HG | −16% | +70% | +258% | 10.8% | 26.4%/45.5% | 79.0% |
| ORIG | +136% | +601% | +2009% | 0.1% | 28.5%/43.5% | 94.2% |
| P5 | +49% | +228% | +637% | 0.6% | 22.3%/35.6% | 67.0% |
| BOOK 55/45 | +39% | +149% | +366% | 0.3% | 15.6%/25.5% | 19.8% |
| BOOK 50/40/10 (+sleeve) | +37% | +134% | +318% | 0.3% | 13.8%/22.5% | **10.6%** |

Reading: the sleeve is the only position whose downside tail is short (worst
5% of years still +4%; P(DD>20%) 2.6%). Adding 10% sleeve to the target book
halves P(DD>20%) (19.8→10.6%) for ~15pts of median return. Standing caveat:
MC resamples each position's own backtest regime — ORIG's +601% median is
"if its backtest regime persists," and its OOS Sharpe (~1.0) argues it won't.

## Addendum 6 — 2026-07-06 — 2008 credit-event simulation (two methods)

No true replay is possible: the sleeve's VIX-complex instruments (UVXY/SVXY,
first ETPs 2009-2011) did not exist in 2008. Two approximations:

**Method 1 — mechanism replay on real 2006-2010 data.** The InverseHold
mechanism rebuilt with 2006-era same-class instruments (LABD→QID, TMV→SDS,
KMLM→DBC, BIL→SHY) and run through actual GFC prices:
- GFC peak→trough (2007-10-09 → 2009-03-09, SPY −55.2%): **+61.2%**
- Calendar 2008: **+20.0%**
- BUT full-window (2006-2010) CAGR −1.9% with 33.9% maxDD — the mechanism
  gave back its crash gains in the 2009 V-recovery whipsaw (short through
  the rally). Crash protection real; exit discipline is the weakness.
  (FrontrunBonds is not replicable pre-2009 — too many young instruments.)

**Method 2 — conditional bootstrap** (walk the real sleeve through 2008's
actual 356-day SPY path, sampling sleeve returns from 2011-2026 days with
matching SPY return + 20d vol): median **+896%** (p05 +405%), maxDD ~8%.
Book (HG55/P5 45), same method: median +387%, maxDD p50 26%.

**⚠ Method 2 is an upper bound, not an estimate.** Its day-matching assumes
every high-vol 2008 day pays like the sleeve's observed high-vol days — but
those were short, sharp spikes (COVID: 25 days, +172%) that resolved
quickly. 2008 held vol elevated for ~a year: VIX-futures roll dynamics flip,
inverse ETFs decay in chop, and 356 compounded "spike days" is a regime the
sleeve's history simply does not contain. The book's number is worse-founded
still (its history's max 20d vol is 55% vs GFC's ~96%).

**Defensible conclusion:** both methods agree on *sign* — the sleeve is very
likely strongly positive through a 2008-style event, plausibly in the
+20% to +60%+ zone the real-data mechanism replay showed (vs the book's
engines, which would face deep drawdowns), with the main risk being giving
gains back in the recovery whipsaw. The +896% median is a methodological
ceiling, not a forecast; do not size anything off it.

## Addendum 7 — 2026-07-06 — sleeve monetization policy study

Question: build auto-sell/harvest logic for the sleeve, or judge event days
manually? Constraint: Composer conditions cannot reference a symphony's own
P&L, so "sell when I'm up X%" cannot live in-tree — only vol-indicator
proxies could, and signal overrides have failed OOS all week. Tested instead
at the **portfolio level** (10% sleeve target, rest = book):

| Policy | Real book 2023+ (CAGR/Shp/DD, rebals) | Notes |
| --- | --- | --- |
| Book alone | +150.7% / 2.49 / 16.3% | no hedge |
| Drift (never rebalance) | +143.5% / 2.49 / 15.8%, 0 | sleeve weight decays → hedge evaporates over time |
| Quarterly rebalance | +136.1% / 2.55 / 14.6%, 12 | fine |
| **Threshold band 7.5–15%** | **+136.2% / 2.56 / 14.6%, 7** | equal-best risk, fewest trades |
| Pop-harvest (+25%/20d cut to 5%, vol re-entry) | +136.0% / 2.56 / 14.5%, 33 | **zero edge over the band, 5× the trades** |

15-year SPY-proxy window: drift "wins" only because the sleeve out-compounds
SPY (+47.6% vs +15.6%/yr) so drift lets the sleeve take over the portfolio —
an artifact, not a harvest lesson; with a high-return book (the real case),
drift *under*-hedges instead.

Conclusion: **the threshold band IS the monetization logic.** Selling
whenever a crash pop pushes the sleeve above 15% of the book mechanically
sells high into panic (in tranches, if it keeps popping — the band re-fires),
re-buys the crashed engines low, and re-enters the sleeve after. No
top-ticking, no signals, 7 trades in 3 years, and the fancy pop rule added
nothing. Extreme events (2008-scale) still warrant human judgment on top —
the band handles tranching; the human decides if the regime broke.
Operational plan: once the sleeve is funded, monitor.py alerts on band
breach; execution stays human-approved via the guarded CLI.

---

# Addendum 8 — 2026-07-09 — BTC multi-timeframe MA scalping study (hourly)

Data: 65,925 hourly BTC/USD closes (Bitstamp, 2019-01-01 → 2026-07-09, no
gaps). MAs across the requested timeframes (1h/4h/12h/1d/1w → 13 SMAs from
20h to 8400h). Signal lagged one bar; fees applied per side on turnover.
IS = 2019-23, OOS = 2024-26. CAGR / Sharpe / maxDD:

| Strategy | 0 bps FULL | 0 bps OOS | 10 bps FULL | 10 bps OOS | turns/yr |
| --- | --- | --- | --- | --- | ---: |
| Buy & hold | +40%/0.85/77% | +17%/0.57/54% | ~same | ~same | 0 |
| Daily 200d filter | +39%/0.96/63% | +24%/0.77/30% | +34%/0.96 | +19%/0.77 | 35 |
| MA-ladder hourly (13 MAs) | **+50%/1.31/43%** | +23%/0.85/24% | +16% | **−5.9%** | 262 |
| MA touch/breakout scalp | +3.5%/0.50/16% | **+0.0%/0.04** | −13.5% | −16.4% | 180 |
| MA-ladder, daily-sampled | — | — | +27%/0.97/57% | +12%/0.73/30% | 55 |

At 25 bps/side every hourly strategy is deeply negative (−22% to −36% CAGR).

Findings:
1. **The literal scalp (MA touch/bounce/breakout with stops+targets) has no
   edge even with zero costs** — +3.5%/yr frictionless over 7.5 years and
   exactly 0.0% out-of-sample. It is a signal problem, not a cost problem.
2. **The MA-ladder (trend version) has a real frictionless signal**
   (Sharpe 1.31 vs 0.85 hold, maxDD 43% vs 77%) but hourly execution turns
   over ~262 units/yr → ~26%/yr cost drag at 10 bps → OOS negative. Break-
   even is ~4 bps/side — unattainable at retail.
3. **All the value lives in the slow component.** The daily-sampled ladder
   (55 turns/yr, fee-robust) ≈ the plain daily 200d filter: Sharpe ~0.96,
   maxDD 77%→~60% (OOS 54%→30%). Twelve extra MAs add ~nothing over one.
4. Conclusion: do NOT build the intraday bot (Hyperliquid/Bybit/IBKR venue
   question is moot). If BTC exposure is wanted, the buildable expression is
   an IBIT symphony with a daily 200d-MA trend filter — it captures the
   entire measurable benefit at 35 turns/yr. Consistent with this project's
   standing result: slow allocation structures survive; fast signals die.

---

# Addendum 9 — 2026-07-11 — Shiller CAPE as a sleeve-allocation signal

Data: monthly CAPE, S&P price, dividend yield, CPI (multpl.com), Feb 1871 →
May 2026 (1,864 months). Real total-return index built from price+dividends,
CPI-deflated. CAPE signal = expanding-window percentile (no lookahead).
Current CAPE: 42.2 = ~99th percentile of all history.

**Part 1 — does CAPE predict? Yes, at decade horizon:**

| CAPE pctile | fwd 1y real | fwd 10y real (ann) | P(−20% within 24m) |
| --- | ---: | ---: | ---: |
| 0–20% | +13.0% | +10.0% | 11.2% |
| 40–60% | +12.9% | +8.4% | 19.0% |
| 80–90% | +6.4% | +6.6% | 16.7% |
| 90–100% | +4.4% | **+3.6%** | **21.9%** |

Monotone at 10y; correction probability doubles cheap→dear. Thesis direction
confirmed. BUT: even at extreme valuations, 78% of 24-month windows contain
NO 20% correction — elevated risk ≠ imminent event.

**Part 2 — does CAPE time allocations? No, for 145 years:**

| Rule (real, cash=0% real) | CAGR | Sharpe | maxDD | since-1990 CAGR |
| --- | ---: | ---: | ---: | ---: |
| 100% equities | +6.69% | 0.52 | 77% | +8.09% |
| CAPE-tilt w=1−0.6·pctile | +4.56% | 0.48 | 62% | **+3.84%** |
| classic CAPE>25 → 50% | +6.28% | 0.52 | 72% | +6.04% |

Every CAPE rule lowers return without raising Sharpe. Cause: regime drift —
since 1990 the market has spent ~75 of every 120 months in the top CAPE
decile; "expensive" persisted for 35 years and the opportunity cost of
de-risking compounded. CAPE speaks in decades; allocations trade in months.

**Part 3 — applied to the sleeve (2011-2026, SPY book + deep-proxy sleeve,
monthly rebalance):** CAPE percentile ranged **0.79–0.99 the entire era** —
the signal has almost no variance where the sleeve is tradeable. Result:
CAPE-scaled 5–20% sleeve (avg 19%) ≈ fixed 20% sleeve (CAGR +22.5% vs
+22.7%, Sharpe 1.52 vs 1.51, maxDD identical). **The "signal" collapses to a
static sizing choice.** (Notable side-result: in this era a 20% fixed sleeve
dominated 10% on every metric — consistent with the earlier frontier — the
cap at 10% remains an evidence-quality decision, not a math one.)

**Proof criterion recorded:** a valuation-timing policy earns adoption only
if it beats a fixed-weight policy holding the SAME average sleeve weight
(isolating timing from sizing). Here it doesn't (22.5 vs 22.7). It cannot
currently, because CAPE hasn't left its top quintile since 2011 ex-2020's
weeks. Re-test if CAPE ever falls below its 60th percentile and re-rises —
i.e., after a full valuation cycle.

**Decision: no CAPE dial in POLICY.md.** CAPE=42 (99th pctile) is context
supporting the sleeve's existence and the eventual 15% scale-up — the gate
for which remains live tracking (Jan 2027 review), not valuation.

---

# Addendum 10 — 2026-07-14 — live transaction-cost analysis (TCA)

Source: Composer trade-activity report (fill-level, 2025-12-04 → 2026-07-14):
193 filled orders, 23 symbols, **$8.53M traded notional** (~7.3 months, avg
equity ~$180k → ~7.8× equity turned over per month across daily rebalances).

| Cost component | Total | Rate |
| --- | ---: | ---: |
| Commissions | **$0.00** | 0 bps |
| Regulatory fees (REG $82.46, TAF $17.20, CAT $0.71) | $100.37 | 0.12 bps of turnover |
| Slippage (fill vs same-day close, notional-weighted) | $2,807 | **+3.3 bps** per side |
| — window fills only (~3:45–3:53pm, n=177) | $4,640 | +6.1 bps |
| — off-window deploy fills (n=14) | −$1,834 | −22.3 bps (favorable timing noise) |

Annualized: ≈ $4,800/yr ≈ **2.6–2.8% of average equity** — dominated entirely
by turnover volume, not by per-trade inefficiency.

Method caveat: fill-vs-close includes 7–15 minutes of market drift (fills
print ~3:45–3:53, close at 4:00), so +6.1 bps is an UPPER bound on true
spread+impact; drift noise is visible in per-symbol dispersion (TNA +41 bps,
TQQQ −5 bps, UVXY −11 bps).

Verdict: execution is at or better than modeled — every backtest in this
project charged 5 bps/side + fees, i.e., live friction (≤3–6 bps) is inside
the assumption, and the earlier divergence study (HG live +13.4% ABOVE its
model over 142 days) independently confirms no alpha leak to execution. The
2.6%/yr aggregate cost is the price of strategies that turn over ~90×/yr and
is already priced into every net backtest number we've used for decisions.


---

## Addendum 11 — Community sweep for a CAGR-additive fourth engine (2026-07-20)

**Ask:** find a public symphony that raises book CAGR and complements HG /
KMLM-switcher / sleeve. Method: 3 ranked searches (41 unique candidates) ->
8 structurally distinct shortlisted -> independent re-backtests (ALL 8
reproduced claims; these are post-creation OOS records, 500-1300 td) ->
correlation vs live engines -> blend test on the book (45/27/27 base,
common 2y window 2024-07..2026-07).

| add @ best size | book CAGR | Sharpe | maxDD | corr (HG/KMLM/SLV) |
|---|---|---|---|---|
| CURRENT BOOK | +111.9% | 2.46 | 11.0% | — |
| WashSale3 WM74 @25% | **+117.2%** | **2.57** | 12.3% | .52/.68/.02 |
| Battleship III @15% | +108.7% | 2.45 | 11.2% | .49/.33/.03 |
| VIX midterm fut @25% | +87.3% | **2.62** | **9.6%** | .14/.08/.10 |

**Findings:**
1. **Correlation intuition INVERTED by the math.** Battleship III (global
   multi-asset momentum, 100+ tickers — the most genuinely different
   strategy found) DILUTES CAGR: its 78% < book's 112%, and 0.49 corr isn't
   low enough to compensate. Diversifying and accretive are different things.
2. **WashSale3 WM74 is the only CAGR-accretive add** (+5.3pp CAGR, +0.11
   Sharpe, +1.3pp DD) — but tree inspection shows it is KMLM-switcher FAMILY
   (74 RSI conditions incl. KMLM/PSQ/QQQE gates, wash-sale ticker variants).
   Adding it raises same-family exposure from 27% to ~45%: family-crowding
   risk in the regime where that signal breaks. Note our own KMLM variant
   out-earned it over the window (+181% vs +127%) — no swap case.
3. **VIX midterm fut** (VXZ/ZVOL/PULS on SPY-RSI): pure stabilizer — best
   Sharpe/DD, costs CAGR. Candidate for lower-vol capital, not this goal.
4. All figures are in-backtest over a favorable 2y window; live drag per our
   TCA runs ~2-4pp/yr on high-turnover symphonies.

**Decision path (loop-improve next):** WashSale3 copied to drafts as
"CANDIDATE: WashSale3 WM74 (loop base)" [LtwtYauWdTCO9kyO7edT]. Loop plan
per our OOS discipline: (a) walk-forward IS/OOS sweep of its key thresholds
(expect signal tweaks to die — verify robustness, not to tune); (b) test
family-neutral funding: add via trimming KMLM (not pro-rata) so family
exposure stays ~flat; (c) 30-day paper watch vs live divergence before any
capital. No investment without owner sign-off per POLICY.md.


### Addendum 11b — WS3 loop results + owner challenge resolution (2026-07-20)

Walk-forward sweeps (IS 2022-06..2025-01 / OOS 2025-01..now):
- Core XLK/KMLM switch windows: OOS plateau (1.87-2.07 Sharpe across 9
  variants) with IS/OOS rank INVERSION (IS-best 14/14 is OOS mid-pack) —
  parameter not tunable, robustness acceptable.
- Pop threshold (75/79/83): dead parameter — zero OOS effect.
- **DD-sort window: fragile.** OOS CAGR 120% (w=8) vs 106% (w=5 baseline)
  vs 56% (w=3). One parameter swings OOS results 2x. The w=8 "improvement"
  is a single-split win — exactly the class that has died on re-splits in
  every prior panel; not actionable without multi-split confirmation.

**Owner challenge (correct):** "why add a same-family underperformer?"
Resolution: the blend-test +5.3pp CAGR came from shifting weight OUT of
lower-CAGR HG/sleeve INTO a high-CAGR family — an effect dominated by simply
upweighting our OWN switcher (+181% vs WS3's +127%). Family-neutral funding
(split KMLM 27% -> 13.5/13.5) BUYS implementation diversification but COSTS
~27pp of CAGR on that slice. Since the goal was CAGR, WS3 is dominated in
both framings. VERDICT: do not fund. Draft parked as bench candidate for
implementation-diversification only. The community sweep's real conclusion:
the highest verified public CAGR lives in the family we already own, and our
variant is the strongest member found; the CAGR lever is WEIGHTS among
existing engines (an owner risk decision), not a fourth engine.


## Addendum 12 — Vol-harvester loop: allocation, attribution, crash-hardening (2026-07-20)

**Window** 2023-04-19..2026-07-17 (814 td — ZVOL inception bound; sleeve fixed
27.4% per policy band). Engine CAGRs this window: HG +82% / KMLM +235% /
SLEEVE +36% / HARV +26%.

**Allocation grid (HG/KMLM/SLV/HARV):**
| allocation | CAGR | Sharpe | maxDD |
|---|---|---|---|
| current 45/27/27/0 | +108.8% | 2.68 | 11.0% |
| 19/39/27/15 | **+112.3%** | **2.98** | **10.8%** |
| 30/27/27/15 (HG-funded) | +97.5% | 2.95 | 10.0% |
| max-Sharpe 10/15/27/48 | +58.7% | 3.40 | 6.9% |

**Attribution (owner asked "is HG the one that suffers?"):** inverted — the
CAGR drop comes from whatever KMLM weight is trimmed (-30pp if funded from
KMLM vs -11pp from HG), because KMLM towers at +235% this window. 25 grid
points add HARV with NO CAGR loss — all work by shifting HG->KMLM weight
(family concentration 27->39%: the same lever as Addendum 11b, now paired
with uncorrelated ballast).

**Crash simulation (offline reconstruction, ZVOL = -1x VXZ - drag; validated
vs Composer backtest at 0.934 daily corr, CAGR 27.5% vs 26.3%):**
2018-01..2023-04: BASE +19.1%/1.62/maxDD 20.9%. Episodes: Volmageddon -1.5%,
Dec-2018 -4.0%, COVID crash -5.5%, 2022 +24.4%. The 20.9% maxDD is a SLOW
BLEED (Feb-2018 -> Feb-2019 echo-spike chop), not a crash gap — the honest
risk: its bad year is a 2018-style vol-chop year, and its 2023+ DD (9.5%)
understates true risk.

**Protection panel:** GUARD (block ZVOL when HYG 1d < -1%) cuts COVID crash
to -1.5% (from -5.5%), IMPROVES 2022 (+28.0%), costs 1.5pp sim-CAGR — and is
FREE in the 2023+ regime (guarded Composer backtest identical: +26.2%/2.16/
9.5%; the gate never fired). RIDER (stand-aside -> long VXZ) killed: COVID
-13%, worse Sharpe. Guarded symphony built + saved to drafts:
"CANDIDATE: VIX harvester + HYG credit guard (loop)" [ORQNCfZnA18wmsMWVhf8],
9 ZVOL legs wrapped.

**Open decisions (owner):** fund guarded HARV at ~15%? Funded via HG->KMLM
shift (all-metrics win, family concentration cost) or HG-only (conservative,
-11pp CAGR)? Nothing executed; POLICY.md sign-off required.


## Addendum 13 — 55-year synthetic blend test + low-return-decade Monte Carlo (2026-07-20)

**Method (owner-directed):** full-fidelity reconstruction to 1971 is not
honestly possible (no VIX before 1990, no vol futures before 2004, no KMLM
index before the late 80s). Instead: REGIME-BOOTSTRAP — real S&P dailies
1971-2026 classified monthly (TREND-UP 32% / CHOP 54% / CRASH 14% of 666
months); each engine's regime-conditional monthly return distribution taken
from its LONGEST real record (HG 2015+ incl. 2018/2020/2022; SLEEVE 2021+;
HARV guarded-sim 2018+ stitched to real; KMLM 2023+ only); joint月 sampling
preserves cross-correlations where data overlaps. CONSERVATIVE variant
replaces KMLM's CHOP/CRASH buckets with HG's (its 814td record contains no
hostile regime). All CAGRs are backtest-derived and inflated — RANKING tool,
not forecast.

**55y spine result:** chosen 19/39/27/15 ~ties current on median CAGR with
2-4pp better drawdowns (as-measured), but under CONSERVATIVE-KMLM the
ranking flips and HG-fund 30/27/27/15 dominates it — the 39% KMLM weight
rests on unverified hostile-regime behavior.

**Published forward projections (researched):** next-decade S&P annualized:
Shiller model -0.7% nominal (+1.3% w/ divs), Research Affiliates ~3.1%,
Vanguard ~5.3%, Goldman base 6.5% (27th pctile since 1900). CAPE 41.1.
Owner's ±2% thesis sits in the pessimistic half of the published cluster.

**Forward 10y MC calibrated to +2% SPX decade (TREND-UP share 32%->22%):**
| allocation | as-measured p05/med/dd95 | conservative p05/med/dd95 |
|---|---|---|
| current 45/27/27/0 | +91/+121/17% | +55/+78/29% |
| chosen 19/39/27/15 | **+101/+126/12%** | +48/+67/22% |
| HG-fund 30/27/27/15 | +85/+107/11% | +50/+68/21% |
| defensive 15/25/27/33 | +75/+90/7% | +44/+57/14% |

**Verdict:** in the low-return decade the chosen 19/39/27/15 is the BEST
allocation if KMLM's measured behavior holds, and statistically TIED with
HG-fund 30/27/27/15 in the conservative worst case (67.1 vs 67.6 med; 22.3
vs 20.8 dd95). Current 45/27/27/0 only beats them in the conservative case
by carrying 7-8pp more drawdown (it is simply more HG beta). DECISION:
phase 2 proceeds unchanged (19/39/27/15). RECOMMENDED TRIPWIRE (owner to
approve): if KMLM's August divergence check fails (live corr < 0.90 or gap
worse than -15%/yr), shift 10pp KMLM->HG — converting the KMLM-bucket
uncertainty into a monitored contingency instead of a pre-emptive haircut.


## Addendum 13b — Adversarial QA of the allocation study (2026-07-22)

Owner-commissioned. Two independent agents: a hostile methodology QA and an
independent re-optimizer (124 allocations x 6 stress specs). Full outputs
preserved in scratchpad qa2/ and opt/; scripts reproducible.

**Both agents confirmed:** computations honest and reproducible; regime
classifier robust to threshold choices; KMLM above ~40% unjustified (its
apparent optimum collapses when the n=3 crash bucket is discounted); the
Aug tripwire is correctly constructed insurance.

**Hostile QA broke three things (all CONFIRMED by computation):**
1. The addendum-13 "conservative tie" that justified 19/39 was a
   construction artifact — replacing KMLM's hostile buckets with HG draws
   makes chosen and fallback ~identical by construction. Under HARSHER
   degradation modes (KMLM flat / SPX-beta / inverted in crashes), 19/39
   ranks LAST of the candidate books; inversion tail: median crash-year
   -14% to -34%, dd_p95 66% of book.
2. Phantom diversification in the conservative variant (independent HG
   draws) understated conservative dd_p95 by ~9pp (22 -> 31%). FIXED in
   regime_boot.py (same-month draws).
3. The T12 crash scenario's -28% acceptance filter RAISED KMLM's effective
   crash mean (its n=3 bucket contains no severe months) — the crash
   scenario contained no downside information for a 39%-KMLM book. The
   +179%/+74% crash-year medians in the prior chat table are unreliable
   for the KMLM leg.

**Re-optimizer's verdict:** incumbent 19/39/27/15 = rank 9/124, best
crash-tail book tested; dominated on all its specs by 25/40/27/8 (trim
HARV into HG, ~+7-10pp/yr in every world incl. KMLM-dead-flat). Note its
conservative lenses were milder than the hostile QA's (flat, not inverted).

**Where the agents disagree:** KMLM weight now. Re-optimizer (KMLM-dead =
flat) keeps 40%; hostile QA (KMLM adversely correlated/inverted in a crash)
favors 29% now with 19/39 as the EARNED upgrade after live hostile months
accumulate. The decision variable is the owner's prior on an unmeasured
engine's crash behavior + their explicit 2-year crash thesis. Escalated to
owner; no auto-action (Op 3 authorizes the 29/29 shift only on divergence
failure, not on QA findings).


## Addendum 14 — Composer vs IBKR execution study (2026-07-29)

Owner question: would the same strategies on IBKR (responsive, better fills)
beat Composer's once-daily 3:45-4:00 PM window over 5 years? Study in
`research/exec_study/` (scripts + full entry/exit ledgers trades-*.csv);
v1/v2 were BROKEN twice by the owner-requested hostile QA agent (double-
counted Composer slippage — dvm_capital is already net; guard "episodes" on
stale gap-day closes; split-adjusted phantom prices in commissions) and
v3 incorporates every finding. QA's independent recomputation matches v3.

Measured (trade ledger validated against Composer's engine at 4.99-5.03bps):
- Two-sided turnover/yr: HG 180x, KMLM 147x, SLEEVE 55x, HARV 135x —
  blended ~130x: the book trades its own value every ~2 days. Execution is
  a first-order cost for BOTH platforms (4-9%/yr), dwarfed only by strategy
  selection itself. Turnover, not venue, is the dominant lever.
- Drag/yr vs reconstructed true gross: Composer 705bps blended (their own
  5bps/side engine assumption + illiquid surcharge) vs IBKR 433bps
  (half-spread x 0.5 + $0.0065/sh all-in) -> IBKR edge 272bps/yr =
  ~$6.8k/yr on the $250k book (~$34k over 5y at current scale).
- SENSITIVITY (the honest headline): the gap is assumption-driven. If
  Composer's real fills are 2.5bps/side (live divergence suggests fills at
  or better than model: HG live beat its backtest), IBKR is WORSE by
  ~$1.3k/yr. Range: -$1.3k to +$15k/yr. Not decision-grade either way.
- Responsiveness (intraday HYG guard vs 3:45 evaluation): NO meaningful
  edge — +1.09pp over 3.27y on the ZVOL sleeve, from ONE whipsaw episode,
  est-range 0..+2.2pp, worst-case negative. v1's +6.99pp was refuted by QA
  (8 of 9 episodes were gap-day artifacts).

Verdict: the data does NOT support migrating for execution reasons at
current scale. What WOULD change it: measured live Composer slippage
persistently >5bps/side (divergence.py tracks this), a 10x larger book
(the gap scales linearly with AUM), or strategies redesigned for lower
turnover where IBKR's fixed costs amortize differently. Parked in
research/ideas-backlog.md alongside the IBKR/HF build triggers.


## Addendum 14b — MEASURED Composer slippage from real fills (2026-07-29)

The addendum-14 sensitivity question ("what does Composer actually cost per
side?") is now measured, not assumed. The API's trade-activity report
exposes every real fill (avg fill price, qty, side, timestamp; fills run
~15:53 ET). Benchmarking all 253 account fills since inception ($10.0M
traded notional) against same-day official closes (the price the backtest
engine credits):

- REALIZED SLIPPAGE: +2.94 bps/side notional-weighted
  (equal-weighted -1.8 +/- 3.1 — statistically ~zero; median +0.9).
- vs the engine's 5.0bps assumption: Composer's live execution BEATS its
  own model at the current book size. Batch market orders on liquid ETFs
  minutes before the close are cheap.
- Platform verdict updated: at ~2.9bps measured, blended Composer drag
  ~380bps/yr vs modeled IBKR ~433bps/yr — IBKR is ~$1.3k/yr WORSE at
  $250k. The migration case at current scale is now CLOSED by measurement.
- The $1M question stays open: thin names carry small samples but point
  the expected direction (VBF +33bps/side n=7; ZVOL -24bps n=6 = noise),
  and today's fills say nothing about 5-30%-of-ADV orders. The quarterly
  re-measurement (scripts/slippage_measure.py, now in the standing
  cadence) builds the evidence curve as the book grows; sustained >5bps
  or deteriorating thin-name fills triggers the backlog's swap/migration
  gates.


## Addendum 15 — Portfolio capacity analysis (owner question, 2026-07-30)

"How big can the book get before slippage/liquidity hurts?" Analysis in
research/exec_study/capacity.py + capacity_results.json, from the actual
trade ledgers (p95 daily traded fraction of book per ticker) x 6-month
median daily $ volume, with participation caps set vs full-day ADV
(Composer's 15-min window carries only ~10-20% of a day's volume):
1% of ADV = invisible, 5% = tolerable, >10% = moving the market.

Screen-ADV ceilings (model-free) split the instruments into three tiers:
- UNCONSTRAINED (ceilings $3.5M-$2.7B): all leveraged index ETFs (TQQQ,
  SQQQ, SOXL, TECL, UPRO...), TLT, LQD, BIL, PULS, SVIX, SVXY, UVXY,
  LABD/LABU, TMV/TMF, ANGL, SPAB. Never the binding constraint.
- DERIVATIVE-BASED THIN NAMES (ZVOL, VXZ, VIXM): screen ceilings $20k-750k
  are ALREADY exceeded — but screen ADV understates VIX-futures ETFs,
  whose true depth is the futures curve ($200M+/day) via market-maker
  create/redeem; measured fills confirm no strain yet (ZVOL -24bps/side,
  n=6). Practical adjusted ceilings ~10-20x screen: ZVOL ~$0.8-1.6M,
  VXZ ~$1.5-3M, VIXM several $M. These bind SECOND.
- VBF — THE REAL CONSTRAINT. Corporate-bond ETF, $0.9M ADV, p95 trade
  29% of book, and no fast AP arbitrage for batch market orders. Already
  measured at +33bps/side (n=7) at the current $280k. Screen ceiling
  (tolerable) ~$150k — the book is PAST it. Swap candidate: LQD/VCIT
  (same exposure, 1000-4000x the volume). This is HG's safe-sector leg.

Impact scaling, calibrated to measurement (the naive sqrt model
overpredicts current-size impact ~100x vs our +2.9bps/side measured, so
model RATES are rejected; sqrt SCALING is kept): excess impact grows
~sqrt(book). Measured excess-over-spread today ~0-2bps/side -> ~0-4bps at
$1M, ~0-6bps at $2.25M — concentrated entirely in the thin tier.

CAPACITY VERDICT (current exact instruments):
- to ~$500k: no action needed; VBF the only name past its comfort zone
  (watch its fills in the quarterly slippage runs).
- $500k-$1M: swap VBF -> LQD/VCIT (removes the binding constraint);
  thin VIX-names fine on adjusted depth.
- $1M-$5M: ZVOL/VXZ/VIXM approach even adjusted ceilings at p95 trade
  sizes — re-implement those legs on deeper instruments (or accept
  measured-then-rising impact; quarterly slippage_measure.py is the gauge).
- ~$5-10M: practical ceiling of the CURRENT strategy set even with swaps
  (window-batched market orders in vol products at $1M+ single prints).
Escalation of the measured slippage trend past 5bps/side triggers the
backlog gates (swaps first, IBKR-with-worked-orders second).


## Addendum 15b — VBF->VCIT swap study (scale prep, 2026-07-30)

Follow-through on addendum 15's binding constraint. VBF appears in HG's
tree exactly twice, both as pure ASSET nodes inside two identical
bottom-1-RSI bond baskets {BSV, TLT, LQD, VBF, SPAB, ANGL} — never in a
condition, so a swap changes no signal logic. LQD is already in the
basket, so the replacement is VCIT (closest duration/credit profile,
~500x VBF's volume).

Backtests 2015-06-11..2026-07-30 (11.1y, same engine/settings):
- BASELINE   CAGR +105.5%, maxDD 36.2%
- VBF->VCIT  CAGR +103.2%, maxDD 36.4% — daily corr 0.9979 vs baseline,
  differs on 9.4% of days, modeled gap -1.17%/yr
- DROP-VBF   CAGR +101.1% — corr 0.9974, gap -2.13%/yr (VCIT swap is
  strictly better than dropping the slot)

Read: behavior preserved (0.998 corr); the modeled -1.2%/yr gap is what
VBF's oversold-bounce picks earn IN-MODEL at zero assumed impact. At a
$1M+ book VBF's real execution cost (measured +33bps/side already at
$280k; sqrt-scaling worse at size, on $290k+ p95 prints into $0.9M ADV)
erodes that edge; beyond ~$1-2M the swap dominates.

DECISION RULE (owner sign-off required to deploy — logic changes are
never auto-executed): swap when book >= ~$750k, OR earlier if VBF's
measured fills degrade past ~50bps/side in a quarterly slippage run.
BENCHED DRAFT ready: symphony 5CbBgpP9T8KcnCCwBGno ("BENCH: HG scale
variant (VBF->VCIT)") — deployment is: owner approves, invest switches
from HG to the variant (or HG's live tree is edited identically in-app).


## Addendum 16 — Harvester keep/kill/resize re-test (owner question, 2026-07-31)

Fresh 55y regime bootstrap + NEW 10y forward MC (block-bootstrap 120-month
regime windows) comparing KEEP 29/29/27/15, KILL->all-three 34/34/32/0,
KILL->engines 36.5/36.5/27/0, DOUBLE 25/25/27/23. Script:
scratchpad harv_decision.py (regime_boot method, QA-fixed draws).

CONSERVATIVE-KMLM lens (the decision lens; AS-MEASURED is dominated by
KMLM's overfit backtest — same distortion hostile QA flagged in 13b):
- 55y: KEEP CAGRmed +71.4% / DDp95 38.5%; KILL->all +80.4% / 45.6%;
  KILL->engines +81.7% / 49.9%; DOUBLE +65.8% / 32.0%.
- 10y fwd MC: KEEP DDp95 31.3%; KILL 37.3-41.5%; DOUBLE 25.8%.
(Levels are backtest-inflated; RATIOS are the finding.)

What HARV does, measured per regime (median monthly): CHOP (54% of all
months) +2.77% while HG does -0.20%; TREND-UP +1.64% (lags engines — its
cost); CRASH +1.46% guarded (only engine besides sleeve positive in all
three regimes). Role: chop-specialist stabilizer. Removing it re-opens
the third-regime gap and raises tail drawdown ~15-20% relative; keeping
it costs ~10-12% relative CAGR in model-world.

VERDICT REPORTED: KEEP at 15%. Killing it only "wins" in the world where
KMLM's untested backtest is real — the exact bet the owner already
declined at the 39%-KMLM decision. The honest CAGR lever is Operation
3's KMLM earn-back (live-data test), not deleting the chop engine.
DOUBLE not recommended (concentrates 2018-slow-bleed failure mode; the
12% bleed alert guards the current size). Decision remains the owner's.


## Addendum 17 — Cash/BOXX defensive legs vs bond baskets (2026-07-31)

Owner hypothesis: symphonies go risk-off into bonds; bonds get wrecked in
some downturns (2022) — would cash (BIL, or BOXX for tax) improve DD?
Mapping: duration risk lives ONLY in HG's two bottom-1-RSI bond baskets
(TLT/LQD/VCIT/BSV/SPAB/ANGL). KMLM + HARV already defend in PULS
(cash-like); sleeve base is 50% BIL with TMV short-bonds. Variants
backtested 2015-06..2026-07 then fed through the 55y regime bootstrap
(script: scratchpad cash_def.py):
- HG-CASH (baskets -> BIL): CAGR +105.3% vs +103.2%, maxDD 35.9 vs 36.4,
  daily corr 0.991. 2022: +45.2% vs +15.4% (+30pp in the bonds-wrecked
  year); 2022 maxDD identical 30.2% (HG's DD comes from its leveraged
  risk-ON legs, not the bond leg).
- HG-SHORTDUR (baskets -> bottom-1 RSI of BIL/BSV): between the two.
- Book-level 55y bootstrap (conservative lens): DD p95 36.2% (CASH) vs
  37.8% (CURRENT); DD med 26.0 vs 26.9; CAGR med +72.1 vs +71.4 — cash
  defense is uniformly (modestly) better at book level.
Structural read: the bond basket only pays in DEFLATIONARY crashes
(2008/2020, TLT rallies) and bleeds in inflationary ones (2022); cash is
regime-neutral. The book already has a dedicated deflation-crash engine
(sleeve, 27%), so HG's bond leg duplicates that role at duration risk.
Caveat: bootstrap buckets are 2015+ resampled — a 1970s-style inflation
decade would favor cash MORE than these numbers show.
BOXX note (taxable a/c): return-equivalent to BIL (box spreads ~T-bill);
edge is tax deferral (no distributions; LTCG if held >1y) — sensible for
the SLEEVE's standing 50% BIL base (months-long holds), NOT for
fast-rotating legs (short holds forfeit the tax edge; BOXX spread ~5-10bp
vs BIL ~1bp). RECOMMENDED to owner: adopt HG-CASH (BIL) in the two
baskets; consider sleeve BIL->BOXX separately. Logic changes — owner
approval required; nothing executed.


## Addendum 18 — DD-reduction levers, backtested (owner question 2026-07-31)

Question: cut max DD without giving up CAGR. Tested at daily resolution
(3.26y common window, all 4 engines) and in the 55y regime bootstrap
(both lenses; scripts: scratchpad rebal_boot.py, dd-*.json curves).

Daily window (as-measured): B&H CAGR +154.9%/DD 19.9%/Sharpe 2.42;
monthly rebal +101.7%/10.0%/2.98; threshold-10% +104.4%/10.3%/2.99;
vol-target 20/15/12% cut DD to 8.8/7.8/6.7% but CAGR to 85/68/56%
(Sharpe up to 3.16 — best risk-adjusted, worst for the stated goal).

55y bootstrap (CONSERVATIVE lens — decision lens):
  monthly-rebal   CAGR +70.1%  DDp95 38.5%
  annual-rebal    CAGR +71.7%  DDp95 37.6%
  CAP-40 (trim only when any engine >40% of book)
                  CAGR +71.9%  DDp95 37.5%   <- dominates monthly
  cap-50          CAGR +75.5%  DDp95 47.1%
  buy-and-hold    CAGR +91.6%  DDp95 68.6%   <- the unmanaged-drift bound
(As-measured ordering identical: cap-40 +122.1%/14.6% beats monthly
+114.2%/13.8% on CAGR at ~equal DD.)

FINDINGS: (1) no zero-cost lever exists — every DD cut works by trimming
the compounding winner; (2) the efficient point for the owner's goal is
the 40% CONCENTRATION CAP: vs unmanaged drift it roughly HALVES tail DD
(68.6->37.5 p95 conservative) while keeping more CAGR than
monthly/quarterly rebalancing; it fires rarely (only after ~40% relative
runs) so turnover cost is negligible; (3) vol-targeting rejected for this
goal (real CAGR cost); (4) canary-gated de-risking remains report-only
(~11 signal clusters — too few to validate as a trading rule).

PROPOSED to owner (needs approval — new capital operation): POLICY
"Operation 5 — engine concentration cap": at the daily check, if any
symphony exceeds 40% of Composer book value, rebalance all four to
29/29/27/15 targets via guarded CLI (25% single-move guard, staged
windows as needed). Mechanically identical in spirit to the sleeve band.


## Addendum 18b — With/without Holy Grail attribution (owner question 2026-07-31)

Daily 3.26y (all four): WITH +101.7%/DD 10.0%/Sh 2.98/So 5.64; WITHOUT-HG
(41/38/21) +104.9%/9.6%/2.94/5.44; HG alone +82.4%/27.9%/1.57/2.80.
10y daily (only HG+SLEEVE exist pre-2023): HG alone +108.8%/35.8%/1.75;
HG+SLEEVE 52/48 +62.9%/11.5%/2.13; SLEEVE alone +40.0%/14.9%/1.51.
55y bootstrap: AS-MEASURED with vs without HG: +114.2% vs +114.1% (wash;
KMLM's backtest is the CAGR machine in that lens). CONSERVATIVE: +70.1%
vs +57.6% — removing HG costs 12.5pp/yr; HG is the only VALIDATED trend
engine (6mo live beating model). HG-only in both lenses: ~+96% CAGR at
54% median / 69% p95 DD — it is simultaneously the largest validated
CAGR source AND the largest DD source; the other three engines are what
turn its 54% drawdowns into the book's ~27%.


## Addendum 19 — HG drawdown attribution by branch (2026-07-31)

Branch-level daily contribution decomposition, 2021-07..2026-07 (exec-study
ledger + adjcloses; branches: TREND = top-RSI {TQQQ,UPRO,UDOW,SSO,TNA},
DIP-BUY = bottom-RSI {TECL,QLD,LABU,USD,SMH}, VOL-SPIKE = {UVXY,VIXY,VIXM},
DEFENSIVE = bond baskets, now BIL).

FINDING — the drawdown engine is the TREND leg, not the dip-buy leg:
- TREND: +179.7pp total contribution, but -216.3pp inside the 12 >10%
  drawdown episodes — it loses more inside drawdowns than it contributes
  in total. Its value is entirely trend-up months (+258.4pp); it BLEEDS
  in chop (-32.6pp) and crash (-46.0pp). All 12 episodes are
  TREND-dominated.
- DIP-BUY (the leg both of us suspected): +131.1pp total, only -22.9pp
  inside episodes, and POSITIVE in all three regimes (+14.2 trend-up,
  +47.3 chop, +69.6 crash). It is the compensated all-weather alpha.
- VOL-SPIKE +25.3pp benign; DEFENSIVE ~flat (duration risk now removed).

Target identified: the TREND leg's -78.6pp of chop+crash bleed
(~12pp/yr) is the uncompensated risk. Candidate fix for the bench
pipeline: regime-gate the two top-RSI trend branches (e.g. allow only
when SPY > 200d SMA; else route to the BIL node) — a real-time gate will
capture only part of the label-based bound, and the whole idea must
survive backtest + adversarial QA before any live edit. NOT built yet.
