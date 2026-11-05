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


## Addendum 19b — Gate builds + three-agent adversarial panel: NEGATIVE result;
## addendum 19's conclusion is RETRACTED (2026-07-31)

Built 5 gated HG variants (trend leg wrapped in regime gates: SPY/QQQ
200d SMA, SPY 60d momentum, 150/250d sensitivity), backtested 2015-06..
2026-07 + 25y regime resample. Then a 3-agent hostile panel (statistical
critic, implementation auditor, market-logic critic) reviewed everything.
Artifacts: scratchpad gates/ (trees, curves, CASE_FILE.md, audit scripts).

RESULTS (CAGR by window; DD = max drawdown over window):
              1y     3y     5y    10y   11.1y  DD-11y  25y-model DDp95
  BASELINE  +65.3% +84.6% +68.8% +108.4% +104.9%  35.8%   66.5%
  best gate +62.8% +74.9% +59.4% +100.0%  +95.8%  32.0%   57.6%
  SMA gates +65.3% +72.9% +51.0%  +89.1%  +87.0%  35.8%   63.7%
Every gate reduces CAGR in every multi-year window; SMA gates RAISED 5y
DD (30.7->34.9%).

PANEL FINDINGS (all three reports preserved in session transcript):
- STATISTICAL (critical): addendum 19's "-79pp uncompensated bleed" was
  100% lookahead artifact — real-time labelings FLIP THE SIGN (+67 to
  +144pp: the trend leg EARNS in real-time-identifiable non-up periods).
  The leg's money is made in post-crash rebound days no causal trend
  signal can pre-identify (10 gate-off days = 89% of V1's 11y shortfall).
  V3's DD "improvement" is ONE knife-edge day (SPY 60d mom -0.78% on
  2020-02-26) that vanishes at 55d/65d lookbacks; best-of-5 selection
  noise. Episode attribution conditioned on outcome (peak-to-RECOVERY
  windows: TREND only -18.7pp, DIP +96.2pp).
- IMPLEMENTATION (pass): trees exact, engine honored every gate, all 42
  table cells verified — the negative result is a real measurement.
- MARKET-LOGIC (kill all designs): below-SMA days are the trend leg's
  BEST state (+0.81pp/day vs +0.12 above); gates are phase-inverted (ON
  in the decline, OFF in the V-recovery); every redesign family
  (dip-routing, single-branch, vol gates, hysteresis) killed by
  mechanism; book already pays for below-SMA protection (KMLM/sleeve/
  HARV positive there) and gating would delete HG's recovery convexity —
  the book's only rebound engine.

DECISIONS: (1) addendum 19's "uncompensated risk" conclusion RETRACTED —
the trend leg's chop/crash losses are the unavoidable price of its
rebound harvesting, which is where HG's edge lives; (2) NO gate ships;
none benched; drawdown management stays at book level (sleeve, cap,
allocation); (3) METHODOLOGY STANDARD adopted for all future attribution
work: real-time labels only, outcome-independent windows, compounded
counterfactuals — no same-period regime labels in any decision analysis;
(4) the one flagged curiosity (overextension trim, >+9% above SMA) is
parked in ideas-backlog as in-sample dredging unless it survives
pre-2021 out-of-window validation.


## Addendum 20 — Man/AHL corpus review: tests, QA panel, new-symphony verdict
## (2026-08-01)

Corpus (owner-provided): Strategic Rebalancing (Rattray/Granger/Harvey/
van Hemert), Best Strategies for Inflationary Times (Neville et al 2021),
vol-targeting + drawdowns + crisis-alpha papers, Strategic Risk Management
book. Two applications tested; each hostile-QA'd by a dedicated agent.

TEST 1 — Strategic rebalancing on the book (daily, 2023-04..2026-07):
trend-gated top-ups added nothing (+0.2pp; robust per QA block-bootstrap,
P(gate better)=10%). QA CORRECTIONS to my framing: (a) the full mechanism
is HUGE in return space on this book — never-rebalance beat monthly by
~52 CAGR pts (KMLM divergence = the paper's short-straddle cost) at 2x
maxDD; (b) cap-40 (Operation 5, already armed) captures most of the
less-rebalancing benefit ~8 CAGR pts cheaper than monthly at equal risk —
INDEPENDENTLY RE-VALIDATED; (c) my "internally-defended engines have no
falling knives" reasoning was false (25 episodes; gate misses 72% of
them; blocked engines mean-revert) — right verdict, wrong mechanism;
(d) whole window is one KMLM super-trend — regime caveat on everything.
Own-drawdown gate variant (+1.5 CAGR pts, +0.07 Sharpe) = within noise,
not shipped. NO CHANGES.

TEST 2 — TSMOM new-symphony candidate (SPY/TLT/GLD/DBC, 19y backtest):
my 200d-single-lag prototype STRAWMANNED the papers (QA): the
literature-faithful build (63/126/252d majority vote + inverse-vol
weights + SH/TBF short legs) doubles Sharpe, fixes 2008 (+26.5%) and
2022 (+3.7%), corr to blend 0.10. STILL CLOSED: its crisis lane is
already occupied — in both live-window stress events (Aug-24 vol spike,
Feb-Apr-25 crash) TSMOM lost money while KMLM/sleeve made +9..+30%; its
2022-regime role duplicates KMLM (2022 +24.2%, corr +0.44 to variant);
90/10 blend adds SR +0.03 for -12 CAGR pts. The corpus's trend
prescription is already embodied by KMLM 29% + sleeve 27%.
REOPEN CONDITIONS (recorded in ideas-backlog): KMLM removed from the
book, OR live-engine Sharpes decay toward ~1 while a 2022-style
multi-quarter inflation-trend regime develops. The shelf artifact is the
A+B+LS spec, NOT the naive prototype.

CORPUS VERDICT: no new symphony, no changes — the literature
independently validates the existing architecture: dedicated trend
allocation (KMLM), crisis convexity (sleeve), cash defense (2026-07-31
edits), vol-targeting rejected for CAGR goals (matches addendum 18),
rebalancing-as-insurance with a wide cap (Operation 5).


## Addendum 20b — HG evaluated against the Man/AHL corpus (2026-08-01)

Owner follow-up: the corpus review (add. 20) was KMLM/book-centric — HG
now evaluated against each applicable corpus lens:
1. Drawdowns paper (de-risking rules cost return): resolved by the gate
   study (19b) BEFORE the corpus was read — identical conclusion reached
   independently on HG. Aligned; no action.
2. Momentum speed (fast signals own crisis alpha): HG's 10d-RSI machinery
   is the fast end; attribution showed its edge IS fast rebound capture.
   Aligned; no action.
3. Volatility targeting (their strongest claim for leveraged equities):
   TESTED on HG with a pre-registered prediction of failure. Result:
   vol-target at median vol cuts CAGR 105.3->78.2% with Sharpe FLAT
   (1.74->1.72) — the literature's Sharpe improvement does not appear.
   Mechanism (measured): HG's P&L is MONOTONICALLY INCREASING in its own
   volatility — Q1 +145pp, Q2 +182pp, Q3 +259pp, Q4 (highest vol)
   +343pp. The papers' precondition (negative vol->return relation,
   leverage effect) is INVERTED for HG: it is a volatility-harvesting
   strategy. Vol targeting would amputate the edge, same mechanism as
   the gates. Corpus, correctly applied, says DO NOT vol-target HG.
CONCLUSION: all three HG-applicable corpus lenses close with one
structural finding: HG earns BECAUSE of turbulence, not despite it;
every within-strategy de-risking family (gates 19b, vol targets 20b,
drawdown rules) amputates the edge. HG risk management stays at book
level (sleeve, cap, weights) — now triply confirmed.


## Addendum 21 — Per-engine + ops-layer corpus evaluation, dual-agent QA
## (2026-08-01)

Owner commission: every engine individually vs the Man/AHL corpus, plus
the ops layer (band, earn-back, cap, monitor cadence), PhD-grade, with a
verifier agent and a counter-agent. Case file + scripts: scratchpad
lens_case.md, verify_lens.py, attack.py.

WHAT SURVIVED VERIFICATION (both agents):
- DD-exit rules destroy value on these curves (HG 82->45, KMLM 255->111
  CAGR; robust to re-entry design) — but REGIME-CONDITIONAL: at Sharpe 0
  the same rule wins 57-61% of paths. Restated as: no mechanical
  price-level exits WHILE live-vs-model health checks pass; breakage
  response is de-allocation at the ops layer.
- Alarm-fatigue math is robust across 4 bootstrap methods: the generic
  15% DD alert fires in 86-97% of ordinary years for HG/KMLM = noise.
- Vol-targeting degrades Sharpe on 3 of 4 engines (direct Moreira-Muir
  test: HG 1.59->1.25, SLEEVE 1.41->0.51, HARV 2.11->1.87, KMLM flat).
  NOTE my original rationale ("papers require negative vol-return
  relation") was a literature error — the true mechanism is that these
  are convexity-long engines that earn in high vol.
- Op3 earn-back gap measurement MUST be paired (live vs concurrent
  model, as divergence.py already does): unpaired it false-fails 47% of
  genuine years. POLICY wording clarified.
WHAT WAS STRUCK FROM MY DRAFT:
- L1 quartile "vol-harvester" patterns: not robust (window/tercile
  reshuffles); lagged vol->return relation is ~0.00 all engines.
- L3 "all engines positive in both stress windows": ENDPOINT ARTIFACT —
  peak-to-trough spring-2025, HG was -18.5%, KMLM +6.9%. Corrected.
- L4 autocorrs: only SLEEVE's +0.40 is significant (n=39).
- S1 (raise HG/KMLM DD alerts to ~31%): REJECTED by counter-agent — it
  trades breakage-detection latency for comfort (~$13-34k extra loss
  before alarm on a Sharpe-0 engine); p90 numbers carry +/-5pp method
  noise; thresholds calibrated on a golden regime stop meaning
  "anomaly" exactly when it matters.
- S5 "band corpus-endorsed": label rejected (n=2 in-sample windows
  endorse nothing); band retained on ex-ante rationale; band-vs-fixed
  study queued.

FINAL SUGGESTION SET (owner decision):
G1. TWO-TIER DD alerts: keep 15% (12% HARV) as an AUTOMATED tier — on
    breach, monitor auto-runs divergence diagnostics and logs, no page;
    HUMAN page only on DD>p90 (documented method sensitivity), failed
    diagnostics, or time-under-water >1.5x engine's historical max
    (~225d HG, ~165d KMLM; zero in-sample false positives).
G2. BOOK-LEVEL DD alert at ~12-14% (p90 of book bootstrap; ~3-6% ordinary
    -year false-positive rate) — closes the coincidence-risk blind spot
    (HG+KMLM corr +0.31, 58% of book; no book alarm exists today).
G3. Earn-back (Op3) criteria addition: live-vs-model beta in [0.9,1.1]
    AND live/model vol ratio <1.15 as fast fat-tail detectors; live
    maxDD<p90 as backstop; gap criterion explicitly paired. ~20% chance
    of a temporary false BLOCK over 2y (delays upshift only — cheap).
G4. Cap-drift protocol note: post-upshift KMLM at 39% sits 1pp under the
    40% cap; specify that a drift breach follows Op5 mechanics (full
    reset) — no ambiguity when it happens within days.


## Addendum 21b — Extended (full-history + 55y-synthetic) alert calibration
## (2026-08-01; owner challenge: "you've only tested in a bull regime" — correct)

Recalibrated G1/G2 thresholds using full real history where it exists and
the 55y conservative regime bootstrap where it doesn't:
- HG (11.1y real, incl. 2018/2020/2022): realized rolling 1y-maxDD p50
  27.9% / p90 35.4%; full-history bootstrap p90 39.7% / p99 53.3%; worst
  time-under-water 282td (golden-window calibration had said p90 32%,
  TUW 150td). The 15% alert is BELOW HG's ordinary p50 — even noisier
  than first measured.
- KMLM (55y conservative bootstrap, daily-adjusted x1.11): 12m-maxDD p90
  39.4% / p99 57.6% (golden-window: 31%).
- HARV: p90 7.9% / p99 13.1% — the existing 12% alert sits ~p98: well
  placed by design.
- BOOK (conservative): p50 7.7% / p90 17.1% / p99 28.2% (golden-window
  p90 was 12.6%).
IMPLICATION: bare DD thresholds are regime-dependent by +/-5-8pp — which
REINFORCES the counter-agent's G1 design (diagnostics + time-under-water
carry the detection load; thresholds are backstops, documented with both
golden and conservative values).

SIDE-DISCOVERY (material): the 2026-07-31 BOXX edit TRUNCATED the
sleeve's backtestable window to ~2023-01 (engine clamps to youngest
asset; BOXX inception Dec-2022). Sleeve full-history research backtests
(regime_boot buckets, divergence baselines beyond 2023) must use the
archived pre-BOXX tree (BIL version) via backtest_tree. regime_boot.py
quarterly run needs this fix BEFORE Oct 1 or its SLEEVE buckets silently
shrink from 15y to 3.5y.


## Addendum 22 — Iran-news force-run proposal: tested, counter-audited, NO-BUILD
## (2026-08-03)

Owner proposal: monitor news (weekend Trump Iran posts), use Composer's
immediate-rebalance to flip before the daily window. Tested on 8 dated
flips (Mar-Aug 2026, from the public record) with gap/drift decomposition;
hostile counter-agent audited (nt_attack/ in scratchpad).

MY STUDY'S FLAWS (caught by the counter-agent, for the record): Apr-8
event-time bookkeeping error (news broke overnight Apr 7-8; my t0 was a
day late — the error FLATTERED the proposal); convention-fragile gap
numbers; "no edge" overclaimed where honest phrasing is "cannot detect at
n=8" (MDE ~0.6%/event on SPY); my book event-day mean didn't reproduce
exactly (+0.22% corrected, still positive).

WHY NO-BUILD IS STRONGER THAN MY VERSION:
1. Post-actionable drift: ~0 in equities, NEGATIVE in the actual war
   trades (USO -1.0%, XLE -1.0% aligned) — oil FADES the announcements;
   multi-day drift negative everywhere (TQQQ -2.0%, UVXY -2.5% by t+2).
   The system would buy reaction tops.
2. The two worst book event-days (May-27 -0.9%, Jul-9 -1.3%) were
   DIRECTION-wrong, not timing-wrong: the book was already positioned
   war-on and the market shrugged; a news-triggered flip would have
   produced the same or deeper losses on both.
3. The 3:45 window ALREADY reacts same-day: KMLM rotated at 3:45 on 5 of
   8 event days — including Apr-8, capturing the overnight move my study
   had booked as "uncapturable." Hourly tape: intraday spikes complete in
   1-2h and partially reverse by 15:30 — the arrival->3:45 increment is
   ~zero or negative.
4. Composer's force-run re-executes the strategy's OWN logic — it cannot
   express "trade the news direction" at all.
5. Costs: ~8-12bp of engine NAV per forced flip, with an ex-ante trigger
   rule firing far more often than the 8 salient events.
6. Unreported positive: the book was cumulatively positive in 6 of 7
   event-to-event windows INCLUDING both escalation regimes — it profits
   through this news cycle without timing it.
DECISION: no news-trading job, no force-runs. The only defensible
recurring artifact would be an informational news-flag in the daily
report (no trades) — marginal value, built only if the owner wants it.


## Addendum 23 — Live KMLM switcher vs "Simons IMPROVED" draft (owner
## question, 2026-08-05)

Head-to-head over the max common window (2023-04-19..2026-08-03, 825d):
              CAGR     maxDD   Sharpe  Sortino
  LIVE 75/25  +247.9%  24.5%   2.53    4.28
  IMPROVED    +354.4%  32.0%   2.43    4.08
  ORIGINAL    +354.4%  32.0%   2.43    4.08
Findings:
1. IMPROVED == ORIGINAL in behavior (identical daily curves; tree diffs
   exist but only in branches never taken post-2023). The "IMPROVED"
   label carries no measurable improvement.
2. The live 75/25 wrapper WINS risk-adjusted on every measure: +0.10
   Sharpe, +0.20 Sortino, 7.5pp less maxDD. Its only "loss" is raw CAGR
   — the metric this family's overfit backtests inflate most (the
   unwrapped variant printed "+1667%" in its advertised 2022 window,
   which STARTS exactly at its advertised backtest date: curve-fit
   evidence, not hostile-regime skill).
3. Single-day comparisons (+17.4% vs +13.1% on 2026-08-04) are the 25%
   vol sleeve damping a monster day — the wrapper doing its designed job.
4. The live version carries accumulating live-vs-model validation
   (earn-back reads start 2026-08-07); swapping resets that record.
VERDICT REPORTED: keep the live 75/25. The unwrapped Simons variant is
the same engine with the seatbelt removed.


## Addendum 24 — CAGR-up-at-same-DD optimization sweep (owner ask, 2026-08-05)

Two untested levers from the quant literature, both run on house machinery:

A. GROWTH-OPTIMAL (Kelly-style) ALLOCATION under a DD constraint —
   grid-search of weight space on the 55y conservative bootstrap found
   101 allocations "dominating" 29/29/27/15 (up to +11.5pp CAGR at equal
   DD p95), ALL of them HG+SLEEVE barbells that gut KMLM/HARV. DUAL-LENS
   CHECK EXPOSED CIRCULARITY: under AS-MEASURED the same barbells lose
   -26pp CAGR at +15pp DD. The conservative lens strips KMLM's edge BY
   CONSTRUCTION, so optimizing under it just deletes KMLM. No allocation
   dominates in BOTH lenses. CONCLUSION: 29/29/27/15 remains the
   two-lens compromise; the frontier unlocks only as earn-back evidence
   (starts 2026-08-07) resolves which lens is real. (Footnote: SLV-UP
   27/27/31/15 improves DD in both lenses at ~equal CAGR — a defensive
   tilt candidate, not a CAGR lever.)

B. PARAMETER-ENSEMBLE TRANCHING of the KMLM switcher — the Simons design
   already ensembles entry WINDOWS (RSI 2..10 ladder); tested threshold
   tranching (all RSI thresholds ±3, equal-weight blend of 3 clones,
   2023-04..2026-08): ENSEMBLE +205.1%/DD 22.0%/Sharpe 2.49 vs BASE
   +247.9%/24.5%/2.53. Ensemble cuts DD 2.5pp at 43pp CAGR cost, Sharpe
   ~flat — NOT shipped. DIAGNOSTIC VALUE (important): the live
   thresholds sit on an in-sample performance PEAK (neighbors at -63 and
   -84pp CAGR) — textbook overfit signature; forward performance should
   be expected nearer the neighborhood mean than the peak. This is
   precisely what the earn-back's live-vs-model tracking measures.

REMAINING UNTESTED (queued, not run): sleeve-band monetization tuning
(band edges/aggressiveness in bootstrap); VRP-conditioned harvester
sizing (contango-depth scaling); options-based structures (not
expressible in Composer); IBKR-only ideas per backlog.
VERDICT REPORTED: no lens-robust free CAGR found; the highest-value
CAGR lever remains the evidence-gated KMLM upshift (earn-back), worth
~+8pp/yr model-CAGR if KMLM proves live.


## Addendum 25 — Queued studies run: sleeve-band tuning + VRP harvester
## sizing (2026-08-05)

STUDY 1 — Sleeve-band monetization tuning (55y conservative bootstrap,
book-share bands, shared 400-path panel): CURRENT band (~[15,33]% of
book = family [7,15]%) sits on the FLAT TOP of the frontier — all sane
variants within +/-0.4pp CAGR; tight [22,32] buys 2.4pp tail-DD for
-1.2pp CAGR at 2.6x the firing rate; deep-harvest (reset to 22) is
strictly worse (+0.4pp CAGR, +1.8pp DD). No-band drift bound re-confirmed
(DD p95 71%). VERDICT: keep the current band unchanged — it was
near-optimal as designed. Band study CLOSED.

STUDY 2 — VRP-conditioned harvester sizing (prior-day VIX3M/VIX contango,
814 live-era days, lagged conditioning only): the literature's
prescription INVERTS on this harvester — its BEST quartile is
LOW/NEGATIVE contango (Q1 +18.5bp/day vs Q2/Q3 ~+5bp): the strategy is
not naive short-vol; its ZVOL/VXZ switching already earns through
backwardation (long mid-term vol + rebound normalization). All sizing
gates tested reduce CAGR with maxDD unchanged (9.5% everywhere); the
one Sharpe bump (2.16->2.30, halve-if-backwardation) de-levers the
strategy's best state — vol-reduction artifact, not edge. VERDICT: no
VRP overlay; the harvester's internal switching is already the
conditioning layer. Study CLOSED.

Running theme now measured five ways (gates 19b, vol-target 20b, DD
rules 21, VRP 25, band 25): every engine in this book is convexity-
aware internally; external de-risking overlays systematically amputate
their best states. The ops layer's job is detection and allocation, not
signal overrides — now empirically settled across every overlay family
in the literature we could express.


## Addendum 26 — S&P valuation-conditioned allocation (CAPE / Buffett
## indicator), tested and CLOSED (2026-08-06)

Owner question: should bands/risk-on-off parameters condition on S&P
valuation (mktcap/GDP, CAPE, PE)? Design honored the settled no-overlay
rule (valuation tested at the ALLOCATION layer only), expanding-window
percentiles only (no full-sample lookahead), forward-PE excluded (no
honest long history). Data: Shiller CAPE 1871+, FRED corp-equities/GDP
1952+; spine 1971-2026.

T0 GATEKEEPER (mechanism): >p90 valuation raises 12m-forward crash
frequency ~1.5x (1.32 -> 1.99 crash-months/yr CAPE; Buffett similar) —
real but weak, and the signal's DUTY CYCLE is terrible: 300/642 months
since 1971 are ">p90" under expanding percentiles (the modern era is
near-permanently "extreme").

T1 TILT SCHEDULES (real CAPE sequence x 55y bootstrap, both lenses):
every tilt (mild/deep/graduated) trades CAGR for DD along the SAME line
as unconditional defensive blends — no dominance anywhere. THE KILL
EXHIBIT: the INVERSE schedule (tilt defensive when CHEAP) performs
IDENTICALLY to the direct schedule (72.2% vs 72.1% cons CAGR; 114.6% vs
114.7% meas) — the valuation signal cannot beat its own inverse. The
T0 crash-frequency lift is too weak and too diluted by the 45% duty
cycle to differentiate direction. T2/T3 (band/cap conditioning) mooted:
same signal, finer plumbing cannot rescue a direction-blind input.

VERDICT: NO valuation conditioning anywhere in the stack. Consistent
with the literature (valuation predicts 10y returns, ~nothing at <=1y).
Valuation stays what it already is here: a descriptive context metric
(canary dashboard candidate), never an allocation input. If the owner
wants more defense, the pre-validated unconditional 27/27/31/15 tilt
achieves the same frontier point without pretending a signal exists.


## Addendum 27 — Synthetic-history build (Phases A-D): pipeline delivered,
## GFC headline numbers KILLED by QA panel (2026-08-06)

BUILT AND VALIDATED (durable assets):
- Instrument reconstruction recipes: 11 leveraged ETFs at 0.995-0.999
  daily fidelity (unconditional); vol-complex regressions 0.91-0.97;
  VXZ->VIXM mapping verified sound by audit.
- research/synth/tree_sim.py: generic Composer-tree simulator validated
  at 1.000/1.000/0.999/0.999 daily corr vs Composer's own engine across
  all four live trees (Wilder RSI). An exact offline engine replica —
  permanently useful.
PANEL FINDINGS (two hostile agents; full reports in session transcript):
- MY BUG (critical): the splice builder FLAT-FILLED pre-inception series
  (VOOG/VOOV pop tickers) -> zero losses -> RSI=100 -> the KMLM engine
  "held" 75% UVXY every day 2007-10..2010-09 including the entire GFC.
  The with-KMLM GFC (+73%/DD 21.5%) is that accident's payoff, not
  strategy behavior. (tree_sim RSI al==0 branch + unpreserved builder.)
- Reconstruction biases ALL point one way (synthetic 2008 too kind):
  crisis-day tracking error 1.6-5.6x with positive return bias
  (~10-25%/3x-leg/crisis-yr); unmodeled 2008 borrow on inverse funds
  (6-26pp); ZVOL contango-beta unidentified in backwardation (41% of GFC
  days vs 6% of its fit era) -> HARV's 2008 +79% is artifact-grade;
  UVXY/SVXY splice seams are structural product changes (2x/-1x eras).
- 2022 "+240%" is in-sample by construction (switcher authored 4/13/22).
- The GFC-era HG~KMLM corr -0.55 was artifact-driven; real-era measured
  corr is +0.30 — the diversification exhibit does NOT survive.
- Auditor's substitute-KMLM table (the honest bottom line): synthetic
  GFC DD spans ~19% to ~39% depending entirely on the unmeasurable KMLM
  leg; under the SAME conservative lens the bootstrap uses, synthetic
  GFC DD = 38.8% — the bootstrap's p95, not its p50.
DECISION-GRADE RESIDUE: book arithmetic verified exact; simulator
semantics exact; SLEEVE's 2022 (+128%, real tickers) the most honest
large number; the qualitative claim "the book carries genuine
crash-convex legs" stands.
VERDICT: the synthetic study provides NO independent confirmation of
central drawdown estimates. THE BINDING RISK NUMBERS REMAIN THE
CONSERVATIVE BOOTSTRAP'S: 1y-DD p50 ~22-27%, p95 ~38%. Fix list for any
rebuild recorded (missing-data->condition-False never flat-fill; borrow
drag on inverse recon; short-vol termination rule; preserve builder;
dual-lens GFC reporting). Owner's planning numbers unchanged.


## Addendum 28 — Four exploration areas executed (2026-08-06)

1. BRANCH-LEVEL LIVE ATTRIBUTION (new diagnostic, via the validated tree
   simulator): KMLM's live P&L 2026-07-16..08-05 matches its model
   TICKER-FOR-TICKER (TECL +17.7pp live vs +17.8 model; SQQQ +13.6 vs
   +13.5; SOXL +5.3 vs +5.4), holdings exact-match 11/13 days. The
   engine earns exactly where its model says — the strongest
   pro-as-measured evidence to date, at branch resolution. HG/SLEEVE
   exact-set agreement lower (42%/40%) — knife-edge bottom-1-RSI filters
   + adjusted-price deltas; attribution deltas negligible. Preview for
   the earn-back: live fidelity currently looks HIGH.
2. 5TH-ENGINE PROFILE SCIENCE: archetype grid (crisis-alpha, chop-earner,
   all-weather, anti-trend, intl-trend at realistic vol) added at 10%:
   EVERY archetype trades ~7pp CAGR for 3-5pp DD — no dominance; the
   best DD-per-CAGR profile is crisis-alpha, i.e. "more sleeve", which
   the pre-validated 27/27/31/15 tilt already offers. CONCLUSION: the
   5th slot is closed to "diversifiers"; only a genuine alpha engine
   (community-sweep bar) earns entry.
3. OPS-TEMPO CONDITIONING (built): accident-gauge RED now escalates
   DIAGNOSTIC tempo — daily divergence sweep across all engines (never
   trades). Plus: backwardation-day logging (captures the first real
   ZVOL-in-backwardation episode for the add-27 evidence gap) and
   VIX contango recorded in every snapshot.
4. CRASH-DAY RUNBOOK: composer/RUNBOOK.md — pre-decided owner protocol
   assembled from adenda 7/19b/20b/21/21b/22/25/26.


## Addendum 29 — Operation 5 (cap-40) independently verified (2026-08-06)

Owner asked how far back the cap was tested and whether agents checked the
math. Answers: (a) the 55y test IS synthetic (regime-sequence replay
1971-2026, engine data 3-11y resampled — standing caveat); (b) a
from-scratch independent agent recomputation now CONFIRMS it: B&H rows
reproduce exactly; rebalanced/cap rows show a small uniform level offset
(~2-4pp, month-end convention) with EVERY comparative claim reproduced —
cap-40 beats monthly rebalancing with P(win)=99-100% per-path across
seeds and K=2000, at equal-to-lower DD p95 in the conservative lens
(+0.9pp DD in as-measured: nuance on the published "~equal" wording,
already visible in the original table). Ambiguity sweep (check timing,
DD sampling, lens reading, label boundaries): orderings survive all.
(c) NEW: daily-resolution cross-check on the 19y synthetic history —
cap-40 again beats monthly at equal DD (post-artifact era: +101.3%/25.9%
vs +98.3%/26.0%); live firing rate ~1.5x/yr (monthly grid understated).
DESIGN CODICIL (measured on the ex-KMLM 38%-target case, 5.4 fires/yr
thrash): the cap requires >=10pp headroom above the largest engine
target. POLICY Op 5 amended: any owner decision that raises a target
above 30% must reset the cap to target+10pp in the same decision.


## Addendum 30 — HG flat-stretch autopsy + cash-gate counterfactuals (owner question 2026-08-14)

Question: HG flat ~2 months in a "bullish" tape — what happened; was cash
right; would the original (pre-edit) HG or another structure have done
better?

Facts (model + live + tree): live BEATS model (+5.0pp cum since Dec,
corr 0.959) — flatness is the strategy, not execution. Apr 8-Jun 15
+43.6% (rebound harvested), Jun 15-Aug 13 +1.8%. Of 41 trading days, 27
(66%) in BIL via the cash route (TQQQ 10<20d MA, no RSI<30 dip, price
<20d MA). Tape during the stretch: SPY +2.0%, QQQ -3.9%, SMH -11.1% —
no bullish leadership existed in HG's universe; the bullish move is the
last ~2 weeks (HG re-entered Aug 4). One dip-buy day (Jul 29, QLD +6.5%)
= the period's whole profit; 4 UDOW whipsaw days -4.0%.

Counterfactual variants (tree surgery, engine backtests; NOTE: the API
silently ignores every version_id param on /score — "original" rebuilt
from addendum 16/17 documented basket composition {BSV,TLT,LQD,VBF,
SPAB,ANGL} bottom-1-RSI):

              May13-Aug13      Jun15-Aug13      11.2y full
  CURRENT     +0.9% / 22.2%    +1.8% /  5.2%    +104.9% / 35.8%  (19b)
  ORIGINAL    -0.6% / 22.2%    +0.3% /  6.9%    +103.2% / 36.4%  (17)
  NO-CASH     +2.4% / 22.2%    +3.4% / 14.6%    +67.6%  / 78.0%  (new)

FINDINGS: (1) owner's read confirmed — the pre-edit HG was break-even-
to-negative over 3mo; the Jul-31 BIL edit added ~+1.5pp and cut the
flat-window DD (bond legs lost while BIL held flat). The 22.2% 3-mo DD
(mid-May..June) lives in the shared equity legs — identical across all
variants. (2) YES, cash was right: staying invested (NO-CASH) picks up
only +1.6pp in this window — entirely from the final-days rally — at 3x
the in-window DD, and is catastrophic at full history: the cash route is
worth ~37 CAGR points and HALF the max DD over 11.2y (78% unmanaged).
(3) No superior rotation target existed: everything HG can buy was
flat-to-down during the stretch. The "HG is TQQQ-keyed and misses
non-Nasdaq leadership" hypothesis is NOT supported for this window
(SMH -11%). (4) Historical precedent (same session): 6 prior >=60%-BIL
2-mo stretches in 11y; forward 3mo positive 6/6 (+5% to +68%).
NO CHANGES; consistent with 19b/20b and the no-overlay rule.


## Addendum 31 — GARCH vol-regime forecasting on the harvester: NO-BUILD;
## the one promising variant was KILLED by counter-agent audit (2026-08-22)

Owner question (Engle/GARCH tweet): can vol-regime forecasting gate the VIX
Harvester's entries/exits or increase its size? Note this is adjacent to two
SETTLED items — the no-overlay rule and VRP sizing (add. 25) — but GARCH
*forecasting* and sizing UP were genuinely untested, so it was run.

MACHINERY BUILT (preserved, research/garch/): real-time GARCH(1,1) MLE with
rolling-10y monthly refit, 1-step-ahead forecast (garchlib.py; passed a
deliberate future-data corruption test BIT-IDENTICALLY — no lookahead);
harvester replica (harvsim.py, daily corr 0.9377 vs real engine); ZVOL proxy
from SVXY extending testable history 3.3y -> 14.8y; build_variants.py driver.
Tweet's factual core CONFIRMED: SPX GARCH alpha .113 / beta .870 / pers .983.

8 variants, 14.8y (2011-10..2026-08), expanding-window (real-time) thresholds:
              CAGR    maxDD  Sharpe        vs baseline
  BASELINE   +12.1%   17.5%   1.51
  G1 calm-only +6.9%  15.9%   1.08   -5.1pp CAGR
  G2 storm-only +10.6% 10.3%  1.49   -1.5pp CAGR / -7.2pp DD  <- the "finding"
  S1 inverse-vol +11.8% 21.8% 1.35   -0.2pp / +4.3pp DD
  S4 2x-in-calm +13.1% 19.8%  1.42   +1.0pp / +2.3pp DD
NO variant improves Sharpe. Gates trade return for DD; sizers trade DD for
return — the add.-18 no-free-lunch wall, reached from a new direction.

COUNTER-AGENT VERDICT: G2 REFUTED. My three robustness checks were WRONG:
1. "8+ episodes, not concentrated" — FALSE. Swapping ONE day (2018-02-05) out
   of the ungated baseline moves maxDD 17.46->11.59%: 82% of the entire 7.2pp.
   My "top-3 = 27%" counted only days the gate HELPED. Netted: +52.4pp over
   124 days vs -73.1pp over 237; G2 loses in 9 of 15 years.
2. "Stable plateau q=0.35-0.65" — FALSE. Stable because the binding drawdown
   in that range is an untouched 2012 episode. q=0.34 -> 15.19% (2019 episode
   binds). Decisive margin on 2018-02-05 is 0.6% RELATIVE on sigma. This is
   exactly the add.-19b knife-edge failure, which I cited as the standard met.
3. "GARCH beats naive vol" — FALSE. My comparators were all SHORT windows vs a
   40-day-half-life model. RV126 and RiskMetrics EWMA(0.94) hit the IDENTICAL
   10.26% DD at Sharpe 1.43 vs GARCH 1.49 — noise.
MECHANISM RUNS BACKWARDS: on days the harvester wants ZVOL, high-vol regimes
beat low by +0.11%/day at t=0.69 (no effect); 4 of the 5 worst ZVOL days fall
in the regime G2 calls TRADEABLE. It escaped them only because the EXISTING
UVXY credit guard was already flat — that guard, not GARCH, blocked the -31%
day (2018-02-06). And on 2018-02-05 GARCH put sigma at the 34th percentile:
it read the eve of Volmageddon as CALM. The save was a forecast FAILURE that
an inverted rule converted into a win.
OUT-OF-SAMPLE: train 2011-18 / test 2019-26 -> -3.01pp CAGR, -0.20 Sharpe
(strictly dominated). Ex-Volmageddon (2011-17): dDD exactly +0.00pp. On the
REAL-ZVOL-ONLY window (2023-04+, zero reconstruction): -3.36pp CAGR at
IDENTICAL DD, -0.22 Sharpe. 22nd percentile vs 400 random block-rate-matched
gates. Paired bootstrap P(edge>0)=0.065. ~56 designs tested, never charged.
DISCLOSED: ~43% of the 14.8y record synthetic in >=1 leg; ZVOL proxy beta
fitted on the SAME 828 days used to validate it (split-sample 0.787->0.711);
replica tracking error concentrates in the ZVOL leg (under-holds it ~21%).

BOOK LEVEL (HARV=15%): G2 -1.19pp book CAGR at ZERO DD benefit on the shared
828d window; a pure cost at the level actually held.

DECISIONS: (1) NO BUILD — not G2, not the sizers; no symphony changes.
(2) The DURABLE result is negative and robust: do NOT vol-scale this engine.
    Inverse-vol sizing costs return AND adds 4.3pp DD AND worsens Volmageddon
    (-9.9 vs -7.3%) — the only finding not single-day-driven. Sizing UP in calm
    fails identically: every such rule concentrates short vol exactly where vol
    GAPS. This is the SIXTH independent measurement of the no-overlay mechanism
    (gates 19b, vol-target 20b, DD-exit 21, VRP 25, band 25, now GARCH 31).
(3) NOT shelved for IBKR — the constraint is not buildability, it is that the
    signal has no edge on this engine.
(4) The harvester's existing UVXY RSI guard is validated as the thing that
    works: surgical (35/812 ZVOL days), and it caught the one catastrophe.
(5) PROCESS: builder script was missing from the working dir (my own add.-27
    fix-list item). Now preserved: research/garch/. Standing rule reaffirmed.


## Addendum 32 — Singha drift-regimes RE-REVIEW: mechanism tested on our own
## instruments; NO ALPHA, no changes (2026-08-27)

Owner re-sent arXiv:2511.12490 (Singha 2025) asking what is learnable and
whether the mechanism applies to our symphonies. The PAPER was already
rejected 2026-07-23 (research/singha2025-drift-regimes.md — survivorship:
their own equal-weight benchmark returns +79%/yr in all three test windows
vs real SPX +12..30% / ~0% / +14..39%). NEW here: the salvaged mechanism
(ideas-backlog #1, per-instrument regime gating) was actually TESTED.

Regime definition per paper: >60% up-days in trailing 63d, PER INSTRUMENT,
computed real-time (no lookahead).

T1 — does the regime LABEL predict? fwd-21d return in-regime vs out, 13 of
our tickers: mean spread -1.27% (in-regime does WORSE), 11/13 negative,
0/13 with |t|>2 (t deflated by sqrt(21) for overlapping windows).
T2 — the paper's ACTUAL claim (regime CONDITIONS a reversal signal; it says
this interaction is 53% of returns): corr(neg-10d-return, fwd-5d) IN-regime
-0.007 vs OUT +0.036; mean diff -0.043 (t=-1.23, 11 tickers); regime helps
on only 3/11. The interaction runs the WRONG WAY on our universe.
T3 — per-instrument gating on HG legs (restrict selection universe to names
in their own drift regime, else BIL): TREND CAGR +39.0%->+1.7%, Sharpe
0.89->0.22; DIP-BUY +13.2%->+3.4%, Sharpe 0.58->0.29.

COUNTER-AGENT (audit ran to completion; the agent died while publishing its
writeup — results recovered from its transcript and the headline
independently re-verified by me):
- T1 and T2 replicated EXACTLY. CONFIRMED.
- FAITHFULNESS ATTACK ANSWERED: my tests are time-series, the paper is
  cross-sectional — a real category-error risk I had flagged. The agent
  built the paper-faithful cross-sectional IC version; it gives the SAME
  answer: IN-regime IC negative across TREND/DIP/ALL13 (-0.01 to -0.12),
  OUT-regime IC positive (+0.011 to +0.057). The category error does not
  rescue the mechanism.
- MY T3 WAS FLAWED: comparing a gate that forces cash 55% of days against
  a fully-invested leg confounds the gate with the cash drag. Corrected
  with an excess-of-BIL measure.
- PLACEBO (the decisive test): against random gates matched to the real
  gate's participation rate, the real drift gate lands at the 10th
  percentile on my replication (agent got 0.0th on its excess-of-BIL
  measure); random gates beat it ~90% of the time. TREND leg ungated
  Sharpe 0.886 -> drift-gated 0.404, random-gate median 0.625.
  The gate is not merely useless, it is WORSE THAN RANDOM — it
  systematically selects names that have already run.
- STEELMAN (inverted gate — hold names OUT of drift regime, which T1
  implies should work): best variant over the full threshold/window sweep
  improves Sharpe by only +0.086, against a random-gate null whose MEDIAN
  improvement is +0.355 and 95th pct +0.703. The steelman also fails.

DECISIONS: (1) NO CHANGES; the existing rejection stands and is now
mechanism-tested on our own instruments rather than argued from the paper's
flaws alone. (2) ideas-backlog item #1 (per-instrument regime gating) is
CLOSED, not merely parked — it was the cheapest idea to falsify and it
falsified. Items #2 (binary activation) and #3 (kill-switch) remain, though
#2 is already how our trees are built and #3 is the monitor's alert layer.
(3) MECHANISM, consistent with the six no-overlay measurements: our engines
earn from mean reversion AFTER stress; a drift filter buys what has already
run, so it is phase-inverted for this book — the same reason the 19b trend
gates failed. (4) METHODOLOGY KEPT: the paper's randomization test (1000
random regime filters) is its one good idea, and we had already adopted it
independently — the counter-agent used exactly that to kill my GARCH gate
in add. 31, and used it again here. Now standard for any gate proposal.


## Addendum 33 — Rate-hike odds: are we factoring them, and would trading them
## have helped? NO and NO (owner question 2026-08-28)

Trigger: owner observed "rate hike odds spiked, that's why we got hit today"
(book -1.98%, KMLM -5.02%/-$4,894) and asked whether any symphony factors
rate expectations and whether trading them has historically helped.
Method: 4 parallel measurement lenses -> 3 backtested overlay families ->
adversarial placebo verification. 8 agents, ~895k tokens.

Q1 — ARE WE FACTORING RATE-HIKE ODDS? NO. Tree audit: HG reads TQQQ+SOXL
price/RSI only; KMLM 17 equity/vol tickers via RSI only; HARV SPY+UVXY RSI
only; SLEEVE reads bond-ETF PRICES (TLT/TMF/TMV/IEF/SHY/LQD/HYG) via
cumulative-return/stdev/RSI. No macro or rates input anywhere.
CONFIRMED BY MEASUREMENT, not just code reading — holdings pass-through
test (daily holdings reverse-engineered from each curve; replica tracking
R2 = HG 1.0000, SLEEVE 1.0000, KMLM 0.9974, HARV 0.9636):
  engine beta(dDGS2) vs ITS OWN HOLDINGS' beta, %/bp:
  HG +0.0140/+0.0141; KMLM +0.0511/+0.0516; SLEEVE -0.0047/-0.0046;
  HARV +0.0037/+0.0047. Residual (engine minus holdings) = -0.0001 to
  -0.0010, economically zero in every case. The logic contributes no rate
  view; all rate exposure is pass-through from what is held that day.
  SLEEVE's duration channel is real but holdings-determined: it holds
  TMF or TMV on 51.6% of days; in that state beta(dDGS10) +0.0421
  (t=+5.62) vs holdings' +0.0422; outside it -0.0021 (t=-0.14). The SIGN
  of its duration exposure is set by which of TMF/TMV it is long — price
  action, not a rate forecast.

Q2 — WAS 2026-08-28 A RATE EVENT? Transmission is EQUITY BETA, not a rate
channel. KMLM held SOXL 38% + TECL 37% + PULS/VXZ; that basket has SPY-beta
5.11 (R2 0.712) and vol 5.75%/day. Basket beta(dDGS2) = +0.0893 %/bp and
POSITIVE-signed; controlling for SPY it is +0.0283 (t=+1.59) — nothing
beyond equity beta. Producing -5% through rates alone needs dDGS2 = -58bp;
through ordinary equity beta it needs only a ~-1% SPY day. Book -1.98% is a
-1.28 sigma draw on 1.54% daily vol. Corroboration in-sample: KMLM's worst
recent day 2026-08-18 (-8.61%) had dDGS2 = 0bp, dDGS10 = -1bp; and
rate-quiet days (|dDGS2|<=2bp) are 25.8% of the sample but hold 26.2% of
KMLM's largest absolute moves. Rate news can drive the equity move; our
loss is levered-growth beta to that move, not a separate rate exposure.
MISSING INPUT (house rule — flagged, not worked around): 2026-08-28 SPY and
2y prints are in NO source yet (Composer engine data ends 08-27, FRED 08-26,
ticker files 08-06). The pre-registered decomposition test — does -5.02%
equal SPY-beta 5.11 x that day's SPY move, or is there a rate-aligned
residual — RUNS MONDAY. A large residual reopens this study immediately.

Q3 — IS RATE SENSITIVITY REAL? Contemporaneous: yes but trivial and
WRONG-SIGNED. R2 of daily engine return on dDGS2+dDGS10 jointly (n=822):
HG 1.94%, KMLM 0.84%, SLEEVE 0.99%, HARV 0.17%, BOOK 1.16%; SPY alone
explains 22.2% of the book. Every single-regressor beta is POSITIVE —
rising yields coincided with RISING engine returns. On the top 5% |dDGS2|
days KMLM earned +2.33% vs +0.45% on the rest (t=+2.67). Engines earn MORE
on big rate-move days. Scale-free: corr(return, dDGS2) KMLM 0.0883 vs SPY
0.0766, TECL 0.1038, XLK 0.1058 — vol-matched, TECL and XLK carry HIGHER
rate beta than KMLM. KMLM is not rate-exposed; it is levered tech.
FORWARD (the tradeable question): one cell of a pre-specified 160-cell grid
clears family-wise correction — HG x DGS2 60-day range-rank, h=1, spread
-77.2bp/day, deflated t=-3.78, FWE p=0.0040 vs 2000 circular rotations.
It does NOT convert: the gate it implies earns +2.4%/yr at t=0.39
(bootstrap p=0.71), gives ZERO drawdown benefit in all 24 configs, and is
absent in S&P data 1990-2014 (spread -2.6bp, t=-0.55, n=6241). Most of the
spread is Q1 being exceptionally GOOD (+68.5bp/day, t=+3.87) — the
actionable side is levering UP in HG's high-vol state, which is the
standing prior, vindicated again. SLEEVE loads OPPOSITE on the same signal
(Q5 is its best state); a book-wide rate gate costs the sleeve -19.9%/yr
(t=-3.01).
FOMC: grid-wide max |t| = 2.63 across 5 engines x 11 offsets, BELOW the
median of Wednesday-matched random date sets (3.00, p=0.841) — the engines
contain LESS FOMC structure than random dates. Lucca-Moench pre-FOMC drift
has died: SPY day-0 +34.2bp (t=+3.31) 1994-2011 -> +1.3bp (t=+0.10)
2015-2026.
KMLM WHIPSAWS: the price of a working signal, not a bug — 45 winners vs 19
losers on DEF->AGG switches, 2.73x gross gain/loss ratio; disabling the
switch takes CAGR from +258% to -9%.

Q4 — WOULD TRADING IT HAVE HELPED? NO. 92 backtested overlay cells:
  KMLM rate-confirmation veto (20+31 cells): best dSharpe -0.02; maxDD
    unchanged in all 10 primary cells; ex-largest-day every cell still
    trails baseline. Damage scales with PARTICIPATION, not wrongness.
  Book-level hawkish-shock de-risk (24 cells): 0/24 improve CAGR, 0/24
    Sharpe, 0/24 maxDD; 4 cells make maxDD materially WORSE (35.8->40.7%).
    Placebo: 2nd-23rd percentile of 3000 matched random gates. Even a
    CHEATING same-day version is worse than the honest t+1 version.
  Duration-aware allocation rotation (48 cells): briefed dSharpe -0.035;
    best-of-48 +0.043 fails permutation (p=0.971) and its single largest
    day is -126% of the whole cumulative edge. Also NOT IDENTIFIABLE in
    real time: split-half rate betas flip SIGN for 2 of 4 engines
    (KMLM -0.93 -> +15.56); rolling 252d beta ranges -2.7 to +24.7.
  0 of 92 cells improved CAGR/Sharpe/maxDD together; 0 improved maxDD at
  all. The verification queue was EMPTY because nothing reached it.

DECISIONS: (1) NO BUILD, no symphony or book changes. The failure is in the
PREMISE (the book is not weak after hawkish repricing — in this sample it is
stronger), not the parameterisation. Measurements #7-#9 of the no-overlay
mechanism. (2) NEVER a book-level rate gate: HG and SLEEVE load in opposite
directions on the same signal. (3) The book's risk is levered-growth equity
beta, not rates — if -2% days are unwelcome the lever is book weights or
notional, priced as an explicit return give-up, not a rate signal. (4)
PAPER-LOG ONLY, zero capital: HG->SLEEVE tilt on HG's Q5 days (in-sample
CAGR 71.1->86.7%, maxDD 15.9->10.8%, but excess t=1.32, positive in 3 of 6
years, chosen after seeing the grid). Revisit in >=3 years.
REOPEN TRIGGERS (pre-specified): (a) the 08-28 decomposition leaves a
rate-aligned residual; (b) rolling 252d corr(SPY return, dDGS2) turns
persistently NEGATIVE — the inflation-shock regime, absent from our sample,
where the whole sign inverts; (c) the HG signal clears t>2 on EXCESS RETURN
out of sample; (d) any engine is edited to read a macro input.
CAVEAT ON SAMPLE: KMLM/HARV/BOOK have only 838 days, all inside the
2023-2026 disinflation regime. There is NO 2022-style hiking shock
in-sample. The positive yields-up/engines-up sign is a growth-driven-yield
artifact; the regime-independent finding is the PASS-THROUGH result.
METHOD NOTE adopted as standing: never downsample a path you also quote a
statistic from (a 2x chart downsample dropped a drawdown trough, displaying
-8.0% against a stated maxDD of -9.9%).


## Addendum 33b — the pre-registered 2026-08-28 decomposition test, RUN (2026-08-31)

Addendum 33 deferred one test for want of data. Now run with the real tape.

MEASURED 2026-08-28: SPY -0.23%, QQQ -0.65%, SOXL -9.52%, TECL -4.67%,
TLT -0.30%; DGS2 4.20 -> 4.34 = +14bp (95th pct of |d2y| is 13bp, so the
hawkish repricing the owner flagged WAS real and top-5%-sized).

TEST 1 — holdings decomposition. KMLM held SOXL 38% + TECL 37% + PULS/VXZ.
  predicted 0.38(-9.52%) + 0.37(-4.67%) = -5.34%
  actual (live account)                 = -5.02%
  RESIDUAL = +0.32pp.
The loss is fully explained by the instruments held. NO hidden rate
exposure. Addendum 33's pass-through finding is CONFIRMED out of sample on
the very day that prompted the question.

TEST 2 — the SPY-beta form of the trigger FAILS, for an instructive reason.
SPY-beta 5.11 x SPY -0.23% predicts only -1.16% vs -5.02% actual, a -3.9pp
residual. But that residual is NOT rate-aligned: it is SECTOR dispersion.
SOXL fell -9.52% on a day SPY fell -0.23% and QQQ -0.65% — a semiconductor
rout, not a broad selloff. Single-factor SPY beta is simply the wrong model
for a day with that much dispersion; the holdings decomposition (Test 1) is
the correct one and it is near-exact. NOT a reopen.

TEST 3 — the sign, and this is the real finding. Historical basket beta to
d2y is POSITIVE (+0.0893 %/bp), so a +14bp hawkish move "should" have added
about +1.25%. Instead the basket fell hard. The historical positive
yields-up/equities-up relationship INVERTED that day — which is exactly the
regime addendum 33 pre-registered as reopen trigger (b), and which is
absent from the 2023-2026 sample.

TRIGGER (b) STATUS — rolling 252d corr(SPY return, d2y), computed 2021+:
  2025-04 +0.259 | 2025-07 +0.309 | 2025-10 +0.307 | 2026-01 +0.366
  2026-04 +0.018 | 2026-07 -0.156 | CURRENT 2026-08-28 -0.196
The correlation has fallen ~56 points from its Jan-2026 peak and has been
negative for roughly two months. This is the inflation-shock configuration
(bad-news-for-bonds is bad-news-for-stocks) in which addendum 33's
contemporaneous lens inverts. It is NOT yet "persistent" by the standard
the trigger set, and 2022-2024 shows the series oscillating through zero
repeatedly, so single readings are not decisive.
DECISION: no reopen, no changes. ADD to the daily monitor's standing watch:
report this rolling correlation monthly; if it holds below -0.20 through
two consecutive month-ends, RE-RUN addendum 33's contemporaneous and
overlay lenses in full, because their central sign assumption will no
longer hold. Note this changes the ATTRIBUTION lens only — it does not
resurrect the overlays, which failed on participation cost (0 of 92 cells
improved maxDD at all), not on sign.


## Addendum 34 — Q4 quarterly batch: regime bootstrap + slippage (2026-10-01)

Standing analysis cadence, run on schedule. Analysis only; no trades.

### A. 55-year regime bootstrap (regime_boot.py)
Spine now 1971-01..2026-09 (669 months). Engine records: HG 135mo,
SLEEVE 68mo, KMLM 41mo (CRASH bucket still only 3), HARV 41mo.

AS-MEASURED           CAGR med   DD p95       CONSERVATIVE-KMLM  CAGR med  DD p95
  19/39/27/15          +127.6%    14.0%                           +69.7%   37.7%
  29/29/27/15 (OURS)   +114.6%    13.7%                           +71.6%   36.9%
  45/27/27/0           +127.9%    19.7%                           +83.4%   46.3%
  25/25/27/23          +101.0%    11.5%                           +66.0%   31.6%
  15/25/27/33           +90.7%     9.0%                           +58.0%   25.3%

FINDINGS: (1) RANKING UNCHANGED. Under the conservative (decision) lens our
29/29/27/15 now dominates the 19/39 alternative on BOTH axes (+71.6% vs
+69.7% CAGR, 36.9% vs 37.7% DD p95). The defensive allocations buy lower DD
with materially lower CAGR, as always. (2) THE TRACKED NUMBER — the
AS-MEASURED vs CONSERVATIVE gap — is ESSENTIALLY UNCHANGED: ~43.0pp this
quarter vs ~44.1pp at the add.-18 run. That is NOT measurable convergence:
KMLM added one month of record (40->41) and ZERO new crash months (3->3), so
there is no new hostile-regime information for the conservative lens to
absorb. Caveat: the prior figure came from a slightly different script path
(rebal_boot.py), so a ~1pp move is inside method noise either way.
(3) CONSEQUENCE for Operation 3: the KMLM earn-back case remains unproven
for the same reason it was in August — the live record still contains no
hostile regime. No action; the monthly report-only check continues.

### B. Realized slippage (slippage_measure.py) — ALERT FIRED, THEN REFUTED
Headline as the script reports it: full window 2025-12-01..2026-10-01, 501
fills / $15.8M notional, +5.29 bps/side notional-weighted; new quarter alone
(07-30..10-01) +6.06 bps on 239 fills. Both ABOVE the 5.0bps engine
assumption, which trips the script's warning and nominally touches the
ideas-backlog migration gate ("build the IBKR stack if measured live
slippage trends >5bps/side").

INVESTIGATED BEFORE REPORTING — the gate is NOT tripped. The metric is
drift-dominated and unstable:
- Re-measuring the SAME baseline window today gives +4.90 bps, not the
  +2.94 bps recorded in add. 14b. Same window, different answer: the
  trade-activity report now returns 262 fills / $10.43M where it returned
  253 / $10.0M. Nine late-appearing fills move the aggregate by ~2bps.
- The estimator is dominated by a handful of fills with impossible
  "slippage": +321.6bps (TNA buy), -206.4 (UDOW sell), -115.3 (TQQQ sell),
  -91.9 (UGE sell). These are 7 minutes of 3x-ETF drift between the ~15:53
  fill and the 16:00 close benchmark, not execution cost. Dropping the top-5
  contributors moves the figure to +7.58 bps — HIGHER. A statistic that
  swings +2.94 / +4.90 / +7.58 on the same data is not measuring anything.
- DRIFT-ADJUSTED estimator (demean each day's fills by that day's common
  move, which cancels the fill-to-close drift): equal-weighted
  +0.59 +/- 1.83 bps/side over 472 fills — STATISTICALLY ZERO, and far
  below the 5bps assumption.
- Raw fill-vs-close by side: buys +2.33 +/- 3.24, sells -0.84 +/- 2.48 —
  each individually indistinguishable from zero.
- ZVOL, the thin-name canary: the quarter's headline +24.0 bps/side is
  noise. Over the full window ZVOL is +7.7 +/- 10.7 bps (n=22) — NOT
  significant. VBF's +20.5 bps is legacy: all 8 VBF fills predate the
  2026-07-30 VBF->VCIT swap, so that leg is already fixed.

VERDICT: no evidence slippage has risen. Composer execution remains at or
below its own 5bps model at this book size; the add.-14b conclusion (IBKR
migration case CLOSED at current scale) STANDS. What this quarter actually
found is a DEFECTIVE INSTRUMENT: the notional-weighted fill-vs-close
estimator has a noise floor far larger than the effect it is meant to
detect, because 3x ETFs move 50-300bps in the 7 minutes between fill and
close, and notional weighting concentrates that noise in a few large fills.
PROPOSED FIX (not yet implemented; needs counter-agent review before it
becomes the tripwire): make the within-day demeaned, equal-weighted
estimator with its standard error the headline and the alert condition, and
require the alert to clear 2 standard errors rather than a bare threshold.
Until that lands, treat the script's ">5bps" warning as advisory only and
read the equal-weighted SE line beside it.


## Addendum 35 — the add.-34 slippage fix FAILED counter-agent review; the
## script is now ADVISORY ONLY (2026-10-04)

Owner asked for the add.-34 instrument defect to be fixed. A replacement
estimator was built and then REJECTED by adversarial review. Recording the
failure because the negative result is the useful part.

WHAT WAS BUILT. raw = beta_i*m_day + c*side_i + e, fit over all fills with a
free drift term per day and betas from returns vs SPY; day effects profiled
out analytically (pure Python — numpy does not survive container restarts).
Rationale: drift hits buys and sells alike and scales with beta, while cost
is sign-dependent, so the two should separate. Alert required c-2se > 5.0.

WHAT VALIDATED. Algebra exact — counter-agent reproduced c to 2.2e-19 and se
to 1.6e-19 against a dense least-squares solve; dof/SE formulas correct for
the n_days nuisance parameters. Noise concentration genuinely FIXED: Kish
effective n = 331 of 505 fills (old statistic was dominated by a handful);
day-resample sd 1.14 vs legacy 1.97. Synthetic recovery of known 0/2/5/10bps
costs within 2 SE, bias +0.007bps, 2-SE false-positive rate 2.0% vs 2.5%.

WHY IT FAILED ANYWAY — the drift model is misspecified and LEAKS into c:
1. INVARIANCE TEST (my own, decisive): re-benchmark the SAME fills — identical
   true cost — against the PRIOR day's close instead of same-day. A correct
   drift model leaves c unchanged. c moves +2.03 -> -16.79 bps.
2. ZERO-COST PLACEBO (counter-agent): reprice every fill at a real intraday
   market price at its own fill minute, so true cost is 0.00 by construction.
   The estimator returns +7.36 +/- 2.86 bps (bar open +7.11, midpoint +6.74).
   Near-zero-beta/quiet names come back +0.42 +/- 0.44 (the model works
   there); levered names +18.31 +/- 7.06.
3. MECHANISM, measured: beta*m_day absorbs only ~50% of drift variance (my
   number; agent measured R^2=0.300 on its intraday subset) because the last
   minutes are NOT one-factor — semis, the vol complex and rates move
   separately from SPY. And side is NOT exogenous: Composer picks side
   conditional on the same day's move (corr = -0.16 over 58 days), so the
   surviving drift does not cancel between buys and sells. Residual drift
   full-window: buys +0.69 vs sells -2.27 bps -> +1.48 bps straight into c
   (agent measured +5.89 on the recent quarter).
The leak is the SAME ORDER as the 5bps effect being policed. My validation
missed it because the synthetic DGP WAS the model — drift exactly
proportional to beta, iid errors, one instant. It verified the algebra and
nothing about the identifying assumption. Lesson, adopted: a synthetic test
drawn from your own model is not a test; a construction-zero placebo is.

OTHER CONFIRMED DEFECTS: reported SE ~55% too narrow (day-clustered CR1 3.07
vs 1.98 shipped; group_cost used the POOLED sigma so ZVOL's SE was 8.44 vs
14.37 clustered); 14 of 510 fills execute 09:31-14:00, not the ~15:53 the
method assumes, biasing the headline down 1.0-1.5bps; one fill (2026-07-07
SOXL) moves c by 1.9bps; betas were estimated on SPLIT-UNADJUSTED prices, so
phantom +437%/+928%/+319% split-day returns corrupted SQQQ/UVXY/VXZ betas by
12-36%; two bare excepts allowed silent degeneration (SPY fetch failure sends
every beta to 1.0 and moves the headline 1.5bps with nothing printed).

ACTIONS TAKEN NOW: (1) the script NO LONGER FIRES AN ALERT under either
estimator — both print as ADVISORY with the leakage and SE caveats inline;
(2) betas now use a new yahoo_adjusted() split-adjusted series; (3) SPY and
per-ticker fetch failures print loudly instead of degrading silently.
POLICY's standing quarterly run stays, as analysis only.

P0 BEFORE THIS CAN EVER GATE A DECISION: (a) benchmark each fill against the
INTRADAY price at its own timestamp — eliminates the drift term instead of
modelling it, and is the real fix; (b) gate on a construction-zero placebo
(require |c_placebo| < 1bp) as a standing regression test; (c) day x
timestamp-bucket effects, or hard-filter to 15:45-16:00; (d) day-clustered
SEs, per-group sigma in group_cost; (e) pin the window / persist the order-ID
set so two runs are comparable.

STANDING CONCLUSION UNCHANGED AND UNDAMAGED: there is still no evidence
slippage has risen. Honest full-window estimate +2.1 bps with a clustered
+/-3.07, and the recent quarter is ~0 after debiasing. The add.-14b verdict
(IBKR migration case CLOSED at current scale) stands — but it stands on the
weakness of the evidence for a rise, not on this instrument.


## Addendum 36 — slippage v3 ALSO failed review; stop measuring fill-by-fill,
## the aggregate measure already answers the question (2026-10-04)

Third estimator, third failure. Recording because the conclusion is a change
of approach, not another patch.

V3 WHAT WAS BUILT: benchmark each fill against the market price in the 5-minute
bar containing it, eliminating the fill-to-close drift instead of modelling it.
Headline +1.09 +/- 0.80 bps/side, apparently BELOW the 5.0 assumption.

WHAT THE COUNTER-AGENT CONFIRMED AS SOUND: bars start-stamped, containing bar
selected for 218/218 fills, stored benchmarks reproduce bit-for-bit on refetch;
split adjustment structurally immune (same-instant price ratio, so any
multiplicative factor cancels — the v2 bug cannot recur by construction); DST
handled on the live path; CR1 clustering correct, verdict robust to t(39),
ticker clustering and wild bootstrap; dedup idempotent; the self-impact claim
(our print inside the bar biases cost DOWNWARD, i.e. conservative) verified.

WHY IT FAILED — the gates licensing the verdict were not tests:
1. GATE 1 WAS AN ALGEBRAIC IDENTITY. mean(slip_i * +/-1) has expectation zero
   for ANY input, and its tolerance GREW with the bias. Verified myself:
   injecting +1000 bps of side-correlated artifact gives headline +1001 bps and
   the gate still PASSES. It could never fail. This is the second time I built
   a gate that cannot fail (add. 35's placebo was tautological for the same
   underlying reason) — a gate must be shown to fail on a broken input BEFORE
   it is trusted, and neither was.
2. GATE 2 WAS BLIND BY CONSTRUCTION. It perturbed only the lookup TIME, so any
   timestamp-independent benchmark (a daily close — exactly the v2 defect)
   returns shift == 0 and passes trivially. Its tolerance also scaled with the
   lagged estimate's noise, so a NOISIER wrong benchmark passed more easily.
   (On the 218-fill ledger the agent computed tolerance 54.59 vs v2's 18.82
   shift = PASS; on the expanded 328-fill ledger tolerance tightens to 7.71 and
   v2 would fail — so the specific "would have passed v2" claim is
   ledger-size-dependent, but the structural blindness is not.)
3. MEASUREMENT CEILING, the finding that flips the verdict. Our own print lies
   inside its bar, so a fill can only ever register |slip| <= half the bar
   range. 39% of fills cannot express 5 bps at all — concentrated in the cash
   sleeve (BOXX/PULS/BIL, median ceiling 0.4-1.0 bps). They drag the pooled
   mean toward zero. Restricted to fills that CAN register 5 bps: +1.98 +/-
   1.61, 95% hi +5.20 -> INDISTINGUISHABLE, not BELOW.
4. BENCHMARK CHOICE FLIPS IT: (H+L)/2 +1.09, open +1.91 [hi +5.12], close
   -0.81, OHLC/4 +0.82. Bar-open crosses 5.0. (H+L)/2 is the lowest-variance
   choice, not a neutral one.
5. THIN NAMES ARE UNMEASURED, NOT CHEAP. We trade 5.6% of VXZ ADV and 8.5% of
   ZVOL per clip; sqrt-law impact ~10 and ~22 bps against reported +4.8/+1.5 and
   a 13-14 bps ceiling. VXZ has no covering bar on 19 of 59 days — the illiquid,
   expensive days are silently excluded.
6. DATA-DESTRUCTION BUG: a bare except plus an unconditional write turned a
   218-fill ledger into 0 while printing "ledger 0 -> 0". Bars expire in ~60
   days, so a lost ledger is lost permanently.
7. COVERAGE: 181 fills ($7.99M, through 2026-07-09) are permanently
   unmeasurable; 111 more ($3.50M) were measurable but uncollected because
   --since defaulted to 60 CALENDAR days while Yahoo serves 60 TRADING days.

FIXED NOW: ledger load refuses to run on a corrupt file and never overwrites
it; atomic write plus a refuse-on-shrink guard; collection window widened to 95
days (recovered 110 of the 111 expiring fills — ledger 218 -> 328, $7.9M);
unmeasured fills printed loudly instead of dropped silently; both worthless
gates replaced (unsigned-bias with a real SE; time-perturbation with an
ABSOLUTE 1.5bps bound) plus a new resolution gate requiring >=50% of fills to
be able to register 5 bps; stratified headline reporting the resolved subset
beside the pooled one. WITH HONEST GATES, GATE 2 NOW FAILS (shift 2.55 vs
bound 1.50) AND NO VERDICT IS ISSUED. That is the correct behaviour: at this
sample size the benchmark cannot be validated to the precision the question
needs.

DECISION — STOP TUNING THIS. Three estimators have failed, each differently,
and the pattern is that the measurement noise exceeds the ~5bps effect at our
trade count and data resolution. Continuing to adjust gates until one passes is
how overfitting happens.
THE AGGREGATE MEASURE ALREADY ANSWERS THE QUESTION, with far more statistical
power, because it uses every DAY rather than every FILL and captures total
implementation shortfall (slippage + timing + fees + anything else):
  divergence.py, live vs model, deposit-adjusted, as of 2026-10-02 --
    HG     live +89.23% vs model +78.86%   gap +10.37%   corr 0.960
    KMLM   live +31.30% vs model +31.63%   gap  -0.33%   corr 0.989
    SLEEVE live +17.97% vs model +15.92%   gap  +2.05%   corr 0.969
    HARV   live  -1.52% vs model  +1.16%   gap  -2.69%   corr 0.118  <- see below
Three of four engines are at or ABOVE their model. Whatever execution costs,
it is not visibly eating returns. That is the decision-grade answer; the
fill-level number is not, and may not be obtainable with free data.
STANDING CHANGE: the slippage script stays as an ADVISORY diagnostic with
honest gates (it will refuse a verdict until one is warranted); the migration
gate in ideas-backlog.md is re-anchored to the DIVERGENCE measure — a
sustained negative live-vs-model gap on liquid engines is the signal that
execution has degraded, not a fill-level bps figure.

NEW FLAG — HARV IS NOT TRACKING ITS MODEL. corr 0.118 (others 0.96-0.99), beta
0.18, vol-ratio 1.54, gap -2.69% over 51 days. NOT a cash artifact: restricting
to days the model actually moved (>20bps) gives corr +0.125, essentially
unchanged. No POLICY tier fires (its drawdown is 4.0% vs a 12% tripwire), so
this is report-only. Caveat: 51-day window, only 13 model-moving days — too
thin to act on, but it is the first time any engine has shown this signature
and it is now on the monthly watch list alongside the KMLM earn-back check.


## Addendum 37 — HARV divergence diagnosed: ONE distribution ex-date, not a
## tracking failure. One unresolved question for the owner. (2026-10-05)

The add.-36 flag (HARV live-vs-model corr 0.118, gap -2.69%) is NOT an engine
or execution problem. Diagnosis, in order:

1. THE GAP IS ONE DAY. 2026-08-19 alone: live -2.78% vs model +1.11%, a -389bps
   divergence that moved cumulative from +0.60% to -3.44%. Every other day is
   noise; top-5 days are 63% of total |gap| and this one dominates them.
2. THAT DAY ZVOL WENT EX-DISTRIBUTION: $0.4850/share, paid MONTHLY, on a ~$7.87
   share — a 6.2% payout. We held 4,062.52 shares => $1,970.
3. THE MODEL CAPTURES IT, THE LIVE CURVE DOES NOT. Composer's backtest uses
   ADJUSTED closes: ZVOL adjclose 6.9498 -> 7.1051 = +2.23%, and 0.52 x 2.23%
   = +1.16% ~ the model's +1.11%. The live series follows the PRICE path: raw
   close 7.87 -> 7.55 = -4.07%. The entire divergence is the distribution.
4. EXECUTION IS INNOCENT. The two fills around it measured +0.0 bps (buy
   2026-08-18) and +3.2 bps (sell 2026-08-19) against the intraday benchmark —
   clean. This was never a slippage problem.
5. NOT SYSTEMATIC. Across 33 ZVOL ex-dates since 2023-12, we held a position on
   exactly ONE. The harvester holds ZVOL ~6% of days, so overlap is rare. HARV
   is not broken and no POLICY tier fires (live maxDD 4.0% vs a 12% tripwire).
6. THE LOW CORRELATION IS A CONSEQUENCE, NOT A SECOND PROBLEM: one -389bps day
   inside a 51-day window of near-cash returns destroys the correlation.

MISSING KEY INPUT — NOT ANALYSED AROUND (CLAUDE.md rule). Whether the $1,970
was actually CREDITED cannot be settled from the API: the symphony series shows
$0 flow on the ex-date, the account series shows no external inflow that week,
and the arithmetic does not close — the live position lost $1,037 while the raw
round trip (bought $32,013 on 08-18, sold $30,267 on 08-19) lost $1,747, so
roughly $710 arrived from somewhere, not $1,970. Composer may book
distributions inside the position without exposing them as a flow. OWNER ACTION
REQUESTED: check the Composer account activity/statement for a ZVOL
distribution around 2026-08-19 to 2026-08-26 and report the amount and date.
Until then the $1,970 is UNVERIFIED, and no verdict is recorded on whether it
was received.

INSTRUMENT DEFECT FOUND (third in this family, same shape as add. 34/35/36):
divergence.py compares a live PRICE path against a model built on ADJUSTED
closes, so ANY distribution-paying holding produces a spurious negative gap.
This matters beyond HARV — divergence.py is the measurement behind POLICY
Operation 3 (the KMLM earn-back) and behind the newly re-anchored migration
gate (add. 36). A fat distribution could false-fail an engine. Holdings in the
current window carry ZVOL (~6%/month!) and PULS (~0.35%/month) distributions.
FIX SHIPPED (deliberately minimal, informational only — it computes no new
number and so cannot produce a wrong one): divergence.py now lists every
ex-date for held tickers inside the window and labels any nearby gap a
distribution artifact until proven otherwise. A full distribution-aware
live-curve reconstruction is NOT attempted here; after three failed estimators
in this family, the right move is to flag rather than to rebuild in a hurry.

STANDING CORRECTION to add. 36: the HARV watch item is CLOSED as a tracking
concern. What replaces it is the narrower question above (was the cash
received) plus the divergence.py distribution defect.


## Addendum 38 — divergence.py rebuilt distribution-aware; HARV false alarm
## resolved; add.-37 owner question CLOSED; instrument RATIFIED (2026-10-05)

RESULTS (frozen 2026-10-05 panel; a live CLI run reproduces it bit-for-bit):

engine | gap old -> new    | corr old -> new | beta | vol  | ann gap new | $ leaked/entitled
HG     | +10.37% -> +13.09% | 0.960 -> 0.960 | 0.98 | 1.02 | +9.1%/yr   |   514 /   905
KMLM   |  -0.33% ->  +1.12% | 0.989 -> 0.988 | 0.99 | 1.00 | +3.5%/yr   | 1,042 / 1,280
SLEEVE |  +2.05% ->  +2.20% | 0.969 -> 0.969 | 1.04 | 1.07 | +7.9%/yr   |    97 /   282
HARV   |  -2.69% ->  +0.59% | 0.118 -> 0.857 | 0.83 | 0.97 | +3.1%/yr   | 1,195 / 1,539

Op2 (SLEEVE) / Op3 (KMLM): no criterion flips; ~18 pp/yr margin vs the gates.
HARV corr 0.857 (<0.90) is now the honest read: worst day -61 bps on 08-19 =
ZVOL sold 7.4502 vs the 7.55 close — a genuine fill, not a distribution.
Chart: results/divergence-distribution-fix-2026-10-05.html.

MEASUREMENT BASIS. Live deposit-adjusted curve is a PRICE path (drops w*D/P on
ex-date; <=0.3 bps on the clean cases). Model = Composer backtest = total return
on Yahoo adjclose. Each ex-date term w(t-1) x D/P_prev x (1+r_adj) is classified
from the model's own continuity: LEAKED (model exits within 4 days) is removed
from the model; HELD_THROUGH stays (live is credited inside the symphony on pay
date, so the mean gap is unbiased). Corr/beta/vol on live+terms vs model total
return — stripping from the model made ZVOL 08-19 a shared manufactured outlier
(HARV corr 0.946, beta 1.14). Add.-36 numbers kept under *_total_return_basis.

CONVENTION: multiplicative (Yahoo adjclose), not additive (P+D)/P_prev. Separated
on the one high-yield case (ZVOL y 6.16%, r_adj +2.23%): residual -0.24 bps vs
+6.91 additive against a 0.01-0.14 bps floor; low-yield cases cannot tell them
apart (<0.5 bps) — n=1 at high yield. Weights lag one day (w(t-1) earns r(t)):
fit SD 0.01-0.14 bps vs 34-372 bps for w(t). The backtest is NOT frictionless: it
charges itself 10.27 bps x one-way turnover (fit SD 0.1 bps, n=157; 7-8%/yr on
HG/KMLM/HARV), so the gap nets live fill shortfall against a modeled cost.

ADD.-37 OWNER QUESTION — CLOSED. The $1,970 WAS credited: to ACCOUNT unallocated
cash on 08-20 (ex+1), not inside HARV. Evidence: account value minus sum of
symphony values jumped +1,969.44 on 08-20; fills 4,062.519 sh x 0.485 = 1,970.32;
API unallocated 1,970.41 on 08-24 (CHANGELOG); redeployed 08-25 as +859/+502/+611
"deposits" that deposit_adjusted strips. The "$710 from somewhere" was arithmetic:
-320 bps distribution + -69 bps fill on $37.3k = -389 bps. Rule (9/9 cases): payer
still held on pay date -> credited in-symphony (PULS ex+2, BIL ex+3, ProShares
ex+4, Direxion ex+5); sold before -> account cash (ZVOL 08-19, BIL 08-03 $231,
TMV 09-22 $97). Permanent live-curve leaks: HARV -3.2%, KMLM -0.8%, HG -0.3%,
SLEEVE -0.13%. A Composer statement line would make this independent of the
residual inference (optional; not needed for the verdict).

COUNTER-AGENT PANEL (four lenses, final round) — none refuted, none blocking:
- Math & conventions: NOT REFUTED; independent stdlib recompute reproduces every
  consumer key on all four engines to the printed digit.
- Gate power: NOT REFUTED; 46/50 core mutants killed (4 survivors equivalent),
  every mandated break caught by physical gates, not pins. Gap: Yahoo wire
  parser success path untested (5/5 parser mutants survive).
- Consumers & impact: CONFIRMED; monitor.py behaviour unchanged except HARV
  vol-ratio 1.54 -> 0.97; INCOMPLETE -> "diagnostic unavailable".
- Cash trail & claims: CONFIRMED; forward defect named: classifier is
  fund-agnostic (ex..ex+4), so a ZVOL ex-date inside a 1-2 day model hold would
  be mislabelled LEAKED (lenient, ~3%/yr on Op3). No such case on this panel.
Fixed after the panel: second moments off the artefact pair; HELD/LEAKED
classifier; 36 gate tests; missing deposit_adjusted_series is now an ERROR (the
silent raw fall-back read HARV corr 0.22 / +46%/yr as COMPLETE); "credit
pending" flag on rows classified inside the last 4 model days; README/show()
no longer claim every LEAKED row reached account cash (3/3 observed; the
model-only rows — KMLM TLT 09-01, four pre-edit HG rows, 91 bps — had none).

BROKEN-INPUT DEMO (suite predicates): ex-dates +1 day -> -389 bps returns; w(t)
for w(t-1) -> -389; amounts zeroed -> clean cases -30 bps; ZVOL unfetched ->
INCOMPLETE; raw $ as live -> 30 pins blown; model edited to hold ZVOL -> label
flips, T1 fails; additive -> 6.8 bps on the 1.0 bps reproduction gate; no cost
-> SD 2.6 bps; off-calendar weight -> INCOMPLETE. 13/13 broken inputs fail.

NOT MODELED: pay dates (held-through +w*y recredit stays in the daily series; a
read within 5 days of a fat ex-date is provisional — the CLI now says so); live
per-symphony share counts (model-only rows read in live's favour); intraday
fill timing; the 10.3 bps turnover friction; decision-divergence days (HG
08-17/18 +254 bps, KMLM 08-31/09-01 +324 bps dominate the residual gap);
HG/SLEEVE live edits 07-30/31 (full-window numbers mix two strategies pre-08-01).

VERDICT: divergence.py RATIFIED as the Op2/Op3 and migration-gate instrument
(fourth in a family where three failed), on three standing conditions: (1) a
verdict with a "credit pending" row is provisional — re-read after 5 trading
days; (2) a LEAKED row for ZVOL/PULS/BIL with model hold <5 days is checked
against the account-cash residual before acting, until a per-fund lag table
ships with its gate test; (3) Yahoo wire-format test + INCOMPLETE on the
adjclose fall-back before the next Yahoo shape change. Conditions (2) and (3)
are code work, scheduled as add. 38b. No threshold changed; owner to confirm.


## Addendum 38b — divergence.py: add.-38 conditions closed; Op 2 reads the
## sleeve from 2026-08-01 (2026-10-06)

RESULTS (frozen 2026-10-05 fixtures):
  Op 2 SLEEVE, --start 2026-08-01 (owner decision 2026-10-05):
    base close 07-31, first return 08-03, 44 of 120 trading days
    ann gap +6.71%/yr | cum +1.25% (live +9.38% vs model +8.13%)
    corr 0.992 | beta 1.017 | vol-ratio 1.025 | live maxDD 4.81%
    -> every criterion met except length; day 120 = 2027-01-22 (POLICY).
  Full window vs add. 38: KMLM / SLEEVE / HARV primary keys unchanged.
    HG ann gap +9.1% -> +8.7%/yr, cum +13.09% -> +12.58%: one pre-edit row
    (BIL 2026-04-01, model-only, held ex..ex+3) is now HELD_THROUGH under
    BIL's observed lag of 3 — the stricter read. HG is not gated.

WHAT CHANGED
- Per-fund pay lags, OBSERVED only (cash-trail event, ex -> credit day):
  ZVOL ex+1 (1), PULS ex+2 (3; identified on 08-31 in HARV and KMLM), BIL
  ex+3 (2), TQQQ ex+4 (1; pay-date reinvest buy $161.83 vs $162.63), SSO
  ex+4 (1; account cash +$2.00 vs $2.02 across Christmas, 50x the noise
  floor), LABD ex+5 (1), TMV ex+5 (1). HELD_THROUGH iff the model holds the
  payer on ex..ex+L-1 (credit lands at the pay-date open, before the
  rebalance — pay-date 15:53 reinvestment fills).
- No guessed lags: SOXL, TNA, QLD, UDOW, TECL, SQQQ, TLT and any new holding
  take the unknown-lag path — LEAKED if the model exited on the ex-date,
  HELD_THROUGH if it held ex..ex+4, otherwise AMBIGUOUS: the primary keeps the
  income (strict, gap reads lower) and show() prints the lenient number with
  a check-the-cash-residual line. None on the frozen panel.
- credit_pending until the credit day ex+L is INSIDE the window (part 1 was
  one day early: HARV PULS 08-31 read on 09-01 = -3.66%/yr unflagged vs
  -0.61%/yr once 09-02 is in).
- Yahoo parser refuses a response without adjclose (INCOMPLETE, was a silent
  fall-back to close). Wire-format gate runs the real parser: dropped or
  mis-dated dividends (the add.-36 false alarm, corr 0.118) now fail.
- --start: live and backtest fetched over the full live window, comparison
  sliced; base = last close BEFORE start. Pre-window held-through credits
  landing inside the window are flagged (HARV/KMLM from 08-01: PULS 07-31,
  credit 08-04, gap high by <= 2.0 / 0.5 pp/yr; SLEEVE none).
- Chart generator moved into the repo (research/divergence/make_fix_chart.py)
  and cross-checks every number against the results JSONs.
- Tests 36 -> 63, each gate paired with a broken input that fails it.

COUNTER-AGENT LOG
- Part 1 (2 lenses): gate power CONFIRMED (17/17 mutants killed); math/cash
  REFUTED on two narrow points — pending off by one, family-inherited lags
  are guesses (SOXL's own event not identifiable; SSO's real event missed).
  Both fixed in part 2.
- Part 2 round 1 (3 lenses): Op-2-window lens BLOCKING — the first build
  based the window on 08-03 and dropped the 07-31 -> 08-03 return (lenient
  by 0.70 pp/yr). Fixed (base = 07-31; that day's -9.3 bps is mostly LABD
  fill timing, ~-12 bps).
- Part 2 round 2: gate power, math/cash, Op-2 window all CONFIRMED, none
  refuted. Independent stdlib recompute of the sleeve read matches to the
  printed digit. Low items closed by the orchestrator: KMLM PULS 08-31 added
  as evidence, SOXL comment corrected, unknown-lag pre-window branch now
  tested (its surviving mutant is killed).

ADD.-38 STANDING CONDITIONS: (1) provisional reads — now flagged by the code,
correctly; (2) fast-payer hand-check — superseded by the observed-lag table;
for unknown-lag funds the AMBIGUOUS line does it; (3) parser test — done.
NOT MODELED: lags rest on 1-3 events each; a lag over 5 business days or a
holiday-shifted pay date; a real Composer backtest started at --start (we
slice the full-window run instead — a fresh start would buy in from cash).


## Addendum 39 — Crash simulations: COVID-type, 2008-type, 2000-type applied to
## the live book; what the gates did; three candidate changes measured (2026-10-07)

Owner question: run a COVID-like, a 2008 and a 1999/2000 crash against the
book as built (trees, guards, live split), from today's $303,140: balances at
3/6/9/12 months, drawdowns, and what to learn or change for a meltdown.
Chart: results/crash-sim-2026-10-07.html (+ .json); code research/crash/.
Counter-agent reviewed (two blocking defects fixed before these numbers).

RESULTS (start $303,140 at the live split 29/32/26/12; Composer-equivalent
costs; guards on; day 0 = onset; "crash" = first 23 sessions)

  scenario                                +3m      +6m        +9m        +12m       maxDD  worst 5d
  COVID-type, today's holdings (6 stand-ins
    for KMLM's regime flag)                $424-544k $739k-1.02M $883k-1.36M $898k-1.52M 15-21% -14..-19%
    same, guards OFF                       $505-585k $716-982k  $845k-1.32M $935k-1.43M 15-21% -14..-19%
  2008-type, Oct-07 peak, CONSERVATIVE
    (KMLM=HG, HARV=T-bill, sleeve recon)   $291k    $289k      $281k      $265k      44%    -16%
    same, sleeve vol legs set to cash      $291k    $275k      $268k      $241k      47%    -16%
    same, guards OFF                       $291k    $288k      $282k      $273k      39%
  2008-type, from Lehman, conservative     $321k    $253k      $308k      $353k      47%    -16%
    same, sleeve vol legs set to cash      $306k    $238k      $289k      $333k      47%    -14%
  2000-type, NDX peak (HG recon; KMLM=HG;
    sleeve/HARV = T-bill)                  $273k    $218k      $247k      $287k      49%    -22%
  2000-type, from Sep-2000 (acute)         $335k    $505k      $372k      $332k      46%    -20%
  House lens (55y regime bootstrap, CONSERVATIVE, 12m p05 / p50 / p95):
    COVID $337k/$624k/$1.37M; GFC-peak $289k/$477k/$964k; Lehman $306k/
    $606k/$1.57M; dotcom-peak $307k/$539k/$1.14M; monthly maxDD p95 23-34%.
  Mechanism exhibits (KMLM/HARV vol legs modelled before they existed —
    artefact-grade, appendix of the chart): 2008 from peak $240k (DD 32%),
    from Lehman $422k (DD 24%).

READ IT THIS WAY
- COVID-type (in-kind: real tickers, validated simulator). The book loses
  15% in the first six sessions: HG -$31.6k (100% TQQQ into the gap), KMLM
  -$13.4k (37% SOXL / 38% SVIX), HARV -$2.1k, sleeve +$0.3k. HG is in BIL
  by session three and re-enters on dips (-6% over the crash); the sleeve's
  UVXY leg pays +80pp of its +144..+180% crash gain and the band sells that
  pop into the engines; HARV loses 10% (ZVOL entries, and PULS -5%). The
  12-month multiples (3-5x) are the engines' IN-SAMPLE reaction to the 2020
  melt-up (HG and the sleeve were authored after 2020); the first 3-6 weeks
  are the stress test, the rest is the easiest tape these rules ever saw.
- KMLM in a sharp crash is UNRESOLVED. Its risk-on/off flag (RSI10 XLK vs
  RSI10 KMLM) cannot be reconstructed for 2020: five managed-futures funds
  and one commodity index (DBC, wrong-sign stress case) agree with the real
  flag on 78-84% of days, and give KMLM crash-window results of +51% (AQMIX),
  +14% (WTMF), -13% (DBMF), -36% (FMF), -48% (RYMFX), -58% (DBC). Mechanism:
  with the flag risk-on, the "lowest-2-RSI of TECL/SOXL/SVIX" leg buys a -1x
  VIX product while VIX explodes (SVIX -50pp of KMLM under DBC). With a proxy
  flag the real-era engine drops from 61x to 9-23x: its edge is concentrated
  on exact flag timing. The flag is a coin-flip in a crash; the range is the
  honest answer and the fragility is a design fact, not a modelling artefact.
- 2008-type and 2000-type (reconstructed). The book goes nowhere to -20%
  over a year and sits in a 44-49% drawdown doing it. HG takes ~70% peak-
  to-trough in BOTH long bears (vs 36% in its 2015-26 record and a 40%
  anomaly alarm) and the losses come from the TREND baskets (10d>20d MA
  and the price>20d else-branch whipsaw into 3x longs on every failed rally:
  TQQQ -68pp/-85pp of HG in 2008/2000-02; trend days -66%/-69%), NOT the
  dip-buys (TECL/QLD/USD/LABU net +79pp/+195pp). The sleeve's 2008 (+36%
  peak-to-trough, +24% calendar, -13% in the 12 months after Lehman, maxDD
  43%) is carried by its UVXY/SVXY legs, which are a VIX term-structure
  MODEL in 2008 — with those legs in cash it is -1% / -14% / -29%: read
  that as the floor. Its SOXS/LABD whipsaws in the 2009 V-rebound are real
  mechanism on real indices. The guards made 2008 slightly WORSE (DD 44%
  vs 39%: band re-entries into a falling sleeve) and 2000-acute better
  (46% vs 54%): they are not a crash tool, they are a drift tool.
- Alerts: every engine's tier-2 and the book-17% alarm fire in all three
  scenarios; in a long bear HG's 40% anomaly alarm fires early and often.

INSTRUMENTS AND THEIR FIDELITY (each verified against something real)
- Tree simulator vs Composer's engine, 2023-26, real tickers: daily corr
  .9999/.9997/.9985/.9992 (HG/KMLM/SLEEVE/HARV); counter-agent's own HG
  implementation vs a no-fee Composer backtest: corr 1.00000, holdings
  869/869. COVID window: HG 1.000, sleeve .999 (BOXX->BIL, KMLM->DBMF run
  through Composer too).
- Composer's cost is its 5-bps slippage SETTING: 5.1 bps per unit sum|dw|
  charged on the trade day (10.2 bps per full switch), intercept 0.000,
  residual 0.2 bps (HG; KMLM 5.9, HARV 5.2, SLEEVE 2.2) — ADDENDUM 38
  CONFIRMED. (My first pass in this study put the cost on the wrong day,
  read a 2.6 bps/day "no-trade drag" into the intercept and drafted a
  retraction of add. 38; the counter-agent caught it. Nothing in add. 38
  changes.) Live has run above the model on every engine, so Composer-
  equivalent is the conservative level.
- Synthetic SVIX = 0.953 x 2 x SVXY - 3.6bp/d (corr .993 vs real 2022-26);
  ZVOL = 0.971 x (-VXZ) (corr .973; backwardation-day beta .98-1.00, n=48).
- Leveraged-ETF reconstructions on their own indices: 0.995-0.999 daily
  (LABU/LABD on XBI .998, FAS on XLF .989); crisis-day bias within +-10 bps/d
  for the 3x names. HG with EVERY leg reconstructed vs real tickers 2015-26:
  corr .964, maxDD 41.8% vs 35.8%, 2022 DD identical, level ~10%/yr
  PESSIMISTIC on average but +-15pp in single windows (COVID window +12%
  vs -5%). The 2000/2008 HG drawdown conclusion survives either sign.
- VIX-ETP term-structure models (dVIX, dVIX3M, prior-close slope; fit
  <2019): OOS 2019-26 corr .96-.97 short-term, .89-.90 mid-term; COVID spike
  captured 77% (plain dVIX regression 41%). In 2008 they run mostly in
  backwardation (74% of Lehman-to-trough days vs 7% of fit days) — used only
  where the ETPs did not exist, and bounded by the vol-legs-to-cash rows.
- Regime bootstrap: the house method (add. 13) along each crash's ACTUAL
  month sequence (labels, buckets, HARV stitching and quantiles reproduced
  by the counter-agent within MC noise). It is kinder than the daily
  replays because months are drawn independently from the engines' measured
  crash buckets (short spikes that mean-reverted within weeks, so a 12-18
  month crash compounds spikes with no give-back) and monthly resolution
  hides intra-month DD (COVID replay 14-21% vs monthly p95 6% as-measured /
  23% conservative). Ranking lens, not the stress number.
- HG "+22% twelve months from 2000-03-10" is window-fragile: one session
  later a biotech dip-buy lost 28% and the read is -12%. Quote the path, not
  the point.

CANDIDATE CHANGES, MEASURED THE HOUSE WAY (real era + replays + placebo of
60 matched random gates — a weak null for a clustered gate)
  C1 short-vol termination: SVIX (KMLM) / ZVOL (HARV) -> PULS when VIX >
     VIX3M at the decision close.
     KMLM: real era 60.7x -> 61.3x (+1%, 48 gate days, placebo pct .82 =
     NO MEASURABLE EFFECT); COVID crash window improves under every stand-in
     (DBC 0.45 -> 0.72x, FMF 0.68 -> 0.99x, DBMF 0.93 -> 1.16x, AQMIX 1.62 ->
     1.69x), maxDD -10 to -22pp, 12m up in all. Deterministic mechanism (do
     not hold a -1x VIX product while the curve is inverted). OWNER DECISION.
     HARV: real era 2.11x -> 2.00x (-5%, pct .25); COVID crash 0.89 -> 0.93x
     but 12m 1.36 -> 1.24x (pct .03): its backwardation entries ARE the
     edge. KILLED.
  C2 HG trend-long baskets -> BIL when SPY < 200d MA (dip-buys untouched):
     real era 7.73x -> 6.36x (pct .33); 2015-23 418x -> 183x (~-10%/yr);
     2022 bear 1.48x -> 1.17x (WORSE: HG's 2022 gains were bear rallies);
     COVID 12m 6.0x -> 4.4x; dotcom 0.76x -> 1.86x (DD 71 -> 60%); GFC
     0.40x -> 1.65x (DD 71 -> 29%). A pure trade: ~10%/yr of bull-market
     return for 2000/2008-style protection, worse in V-recoveries. NOT
     recommended as-is; recorded as the measured price of HG's bear risk.
     (TQQQ<200d variant mis-built pre-2010 — 0 gate days — not reported.)
  C3 HARV cash leg PULS -> BIL: real era 2.113x -> 2.082x (-0.5%/yr); COVID
     crash 0.89x -> 0.94x, maxDD 11.5% -> 6.0% (PULS, an ultra-short IG
     fund, fell ~5% in March 2020; BIL did not). Cheap, mechanical; KMLM's
     12% PULS leg negligible either way. OWNER DECISION.

NOT MODELED: IBKR equities held at $346k in the band denominator (they fall
too, so the band trims earlier in reality); execution at the open of a
limit-down day; KMLM's true 2020/2008 flag; HARV/KMLM vol legs before 2018
(exhibits only); inverse-fund borrow in 2008 (makes the sleeve's whipsaws
worse); the engines' rules are in-sample for 2015-26 and out-of-sample for
2000/2008 — the ~70% HG drawdown is the honest OOS evidence.

COUNTER-AGENT (one hostile reviewer, full report in the session transcript;
verification scripts under scratchpad/crash/verify/): sixteen findings.
BLOCKING, fixed: (F1) the from-today variant cold-started the sleeve's
filter sub-trees, dropping its InverseHold branch for 20 sessions (sleeve
crash +219..+263% -> +144..+180%; book 3m +55..+91% -> +40..+79%); (F2) the
cost model was aligned one day off (see above). MEDIUM, fixed: (F3) the
"conservative" 2008 row used the HARV exhibit -> HARV = T-bill; (F4) the KMLM
exhibit ran SVIX at half leverage (era default) -> fixed and moved to the
appendix; (F5) the sleeve's 2008 gain is model-driven -> labelled, vol-legs-
to-cash rows added. LOW, fixed in text: F6 window fragility, F7 DBC label,
F8 "free" -> "no measurable effect", F11 live split, F14 bootstrap p95
lens. CONFIRMED independently: simulator (corr 1.00000), SVIX/ZVOL fits,
leveraged fits and splices, VIX-model build, bootstrap, book arithmetic to
4 decimals, attribution, gate counts, no signal look-ahead. Reviewer's
verdict after edits: the headline table can be shown with the caveats
above; qualitative conclusions unchanged.


## Addendum 40 — HG bear gate revisited: risk-adjusted, graded shapes, macro
## conditioning (CAPE / curve / credit / oil), 1990-2026 (2026-10-08)

Owner question (after add. 39): is "a tenth of the upside for a 70% -> 30%
drawdown" a good trade on Sharpe/Sortino; can the gate tighten gradually as
CAPE stays high (or as oil, yields, credit deteriorate) and widen as they
improve; deep-research it.
Chart: results/hg-gate-variants-2026-10-08.html; code research/crash/
gate_study.py, gate_extra.py, placebo2.py, boot_gate.py; macro data under
research/crash/macro/. Counter-agent reviewed; its edits are applied below.

METHOD. The HG tree is run once per panel (its decisions never depend on
the gate); each gate is a per-day allow in [0,1] applied at the decision
close to the TREND baskets only (TQQQ/UPRO/UDOW/SSO/TNA x allow, rest to
BIL); dip-buys, long-vol and cash defaults untouched; Composer-equivalent
cost on each variant's own turnover; Sharpe/Sortino over T-bills. Panels:
A = real tickers 2015-06..2026-10 (in sample for HG's rules); B = 1990-01..
2026-10 proxy (leveraged legs reconstructed from their indices, within
1.2%/yr of the real ETFs over their overlap; pre-1999 bases are index
proxies with the S&P dividend yield accrued; VIX ETPs modelled) — out of
sample for the rules. Tests: every gate vs its INVERSE (trend: 1-allow;
macro: flag ON -> 200d, OFF -> the variant's own level) and vs 200
PLACEBOS (the variant's monthly pattern randomly re-dated); block
bootstrap for the within-family ranking. Book level: the 55y regime
bootstrap with HG swapped for the variant (boot_scen method: drift +
cap-40; raw monthly Sharpe).

RESULTS — HG alone, full windows (CAGR / Sharpe / Sortino / Calmar / maxDD)
  Panel B 1990-2026 (proxy, OOS for the rules)       vs placebo (200)
    as built              +49.6% / 1.00 / 1.55 / 0.69 / 72%   worst yr -42% (1994)
    B1 binary SPY<200d    +55.5% / 1.16 / 1.88 / 0.93 / 60%   p100 CAGR / p100 Sharpe / DD better than 100%
    G2 vote 50/100/200d   +55.4% / 1.17 / 1.92 / 0.85 / 65%   p100 / p100 / 97%
    G6 off<200d, vote>    +55.2% / 1.19 / 1.95 / 0.92 / 60%
    G4 drawdown ramp      +51.9% / 1.11 / 1.80 / 0.86 / 60%   p94 / p99 / 100%
    G3 persistence ramp   +51.7% / 1.09 / 1.72 / 0.79 / 65%   p93 / p97 / 98%
    G7 slow re-entry      +52.3% / 1.14 / 1.86 / 0.86 / 61%
    M4 oil +50% yoy       +56.2% / 1.17 / 1.90 / 0.94 / 60%   p62 / p69 / 77%; mirror inverse +55.0% / 1.15 / 74%
    M1b CAPE high-long    +53.8% / 1.15 / 1.85 / 0.82 / 66%   p38 / p53 / 28%; mirror inverse +54.1% / 1.12 / 60%
    inverse of B1         +24.6% / 0.70 / 1.17 / 0.34 / 72%
  Panel A 2015-2026 (real tickers, in sample)
    as built              +104.1% / 1.69 / 2.93 / 2.90 / 36%
    B1 binary             +86.5% / 1.57 / 2.80 / 2.41 / 36%   p14 / p17 / 11%
    G2 vote               +92.5% / 1.67 / 3.04 / 2.76 / 34%   p50 / p47 / 74%
    G6 off<200d, vote>    +89.1% / 1.64 / 3.00 / 2.66 / 34%
    G3 persistence ramp   +89.2% / 1.59 / 2.82 / 2.49 / 36%
    G7 slow re-entry      +77.9% / 1.50 / 2.69 / 2.17 / 36%
    M1 CAPE level         +91.0% / 1.65 / 2.99 / 2.67 / 34%   p56 / p71 / 86%; mirror inverse +85.3% / 1.55 / 36%
    M5 macro count        +95.6% / 1.68 / 3.04 / 2.76 / 35%   p60 / p57 / 47% (flagged 112/137 months — a near-permanent 50d gate, not a macro signal)
  Panel B by window, as built -> B1 (CAGR/yr): 1990-99 +38 -> +45 (77% of
  the gain is ONE session, 1998-08-31, NDX -9.9% with the gate in cash;
  ex-1998 the gate COST 2.4pp/yr); 2000-02 -10 -> +28; 2003-07 +34 -> +39;
  2007-09 -47 -> +43; 2009-19 +55 -> +52 (a cost); 2020-26 +128 -> +100.

READ IT THIS WAY
1. ON RISK-ADJUSTED TERMS THE 200d FAMILY IS ROBUST IN THE LONG HISTORY.
   Over 36 years every member raises Sharpe (1.00 -> 1.11-1.19), Sortino
   (1.55 -> 1.72-1.95) and Calmar (0.69 -> 0.79-0.94), cuts the worst
   drawdown from 72% to 60-65%, beats 200 randomly re-dated versions of
   itself (p93-p100 on CAGR and Sharpe, DD better than 97-100% of them) and beats its inverse by ~30pp of CAGR; block
   bootstrap: B1-vs-as-built Sharpe +0.16 [+0.04, +0.29], P(>0) 0.98. The
   return edge is five bear episodes (1998 one session, 2000-01, 2003 Q1,
   2008-09, 2011); the cost is every V-shaped recovery. In 2015-26 — the
   tape HG's rules were selected on — every gate costs 5-28pp/yr, nothing
   beats as-built, and the trend gates sit at placebo p05-p40: the days
   they skip (the first weeks after a 200d break) were HG's best days in
   that regime. Both statements are true; they describe different regimes.
   The bull-market cost is 2-5pp/yr in the long history and 10-28pp/yr in
   the post-2015 regime.
2. SHAPE: THE FAMILY IS INDISTINGUISHABLE; ONLY SLOW RE-ENTRY IS WORSE
   EVERYWHERE. Block bootstrap (panel B, 400 resamples): G2 - B1 CAGR -0.1pp
   median [-3.8, +3.4], P 0.48; G6 - B1 -0.3pp, Sharpe +0.02 (P 0.80); the
   best-of-7 trend shapes beat B1 by +0.03 Sharpe on median — exactly the
   printed G2/G6 edge, i.e. a selection effect. G2's edge over B1 exists
   only in 2015-26 (+5.5pp, P 0.96), where no gate beats as-built; G2 is
   worse than B1 in both long bears (2000-02 +21 vs +28; 2007-09 +34 vs +43)
   and on maxDD (65 vs 60%). Where the damage sits is panel-specific: in
   1990-2009 the trend basket lost 0.76 in the first 10 sessions below the
   average (fast exit paid) and MADE 0.67 in sessions 21-80 (bear rallies);
   in 2015-26 the first 10 sessions contributed nothing (HG's own 10/20
   cross is already out) and sessions 21-80 made 0.98 (V-recoveries) — so
   the owner's "tighten slowly with persistence" (G3) is the worst trend
   shape in the long history and the best in 2015-26. Slow RE-ENTRY (G7)
   is worse than binary in both panels: HG earns +5.6% (B) / +13.4% (A) in
   the 20 sessions after a recross. Decision rule from the data: pick the
   simplest member (binary 200d, or G6 which equals it in the long history
   and gives back ~3pp of panel A's cost); the data cannot rank them.
3. MACRO CONDITIONING: NOTHING MEASURABLE. Under the rebuilt placebo (the
   variant's own flag-level pattern randomly re-dated, 200 draws) no macro
   conditioner is significant in either panel (panel B: CAPE p19-p38, curve p37, credit p06, oil p62-p69, count p81; panel A: p45-p76 for all of them). CAPE level and
   "high for long" sit near placebo median in the long panel and lose to or
   tie their mirror inverse there; credit spreads lose to their inverse in
   both panels; the yield curve loses on all three metrics in the long
   panel (its tighter 100d gate whipsaws inside 2000-02: maxDD 74%); oil
   (+50% yoy -> 100d) beats its mirror in the long panel (56.2/1.17/60 vs
   55.0/1.15/74) on four bears with an oil spike in front of them (1990,
   2000, 2008, 2022) and loses in 2015-26 (the 2021 rebound was a false
   alarm) — four episodes, not evidence. Add. 26's verdict on CAPE stands,
   now at the gate level over 36 years.
4. BOOK LEVEL (55y bootstrap, HG swapped, conservative lens): as built CAGR
   p50 +73.6% / DD p95 36% / Sharpe 1.81; binary +70.2% / 34% / 1.79; vote
   +72.0% / 32% / 1.84; drawdown ramp +69.5% / 33% / 1.88 (constant-mix
   variant: -2pp CAGR, same order). The bootstrap only knows HG's 2015-26
   months, so this is panel A's cost (1.5-4pp CAGR for 2-4pp of tail DD);
   the 2000/2008-type benefit lives outside its buckets. In the daily 2008
   hybrid (add. 39 method, KMLM = ungated HG) the binary gate moved the
   book's 12 months from -12.7% to -1.0% and its max DD from 44% to 24%.

NOT MODELED / CAVEATS: panel B is a proxy (index-based legs before 1999,
VIX ETPs modelled); the 200d rule reads a total-return SPY series — on the
price-only close B1 is 80.0%/1.50 in A and 53.8%/1.14 in B (6pp of
convention sensitivity); CAPE enters with a two-month lag; "worst year"
includes partial years; the gate made 1990 worse (-37 -> -49%); 15
variants plus inverses were examined and the family is reported whole; a
200d gate does nothing for a gap crash (COVID-type DD unchanged); Composer
cannot express a fractional allow directly — a vote gate is three nested
conditions with three sub-baskets (buildable).

LITERATURE (agent pass with citations, research/crash/macro/literature.md):
- 200-day filters on the S&P: Sharpe ~0.3 -> ~0.6 and max DD -85% -> -50%
  over a century, but the CAGR edge is small, not significant net of costs
  (Zakamulin 2014/15), concentrated in 4-5 deep bears, and the rule loses
  in ~80% of exit-to-re-entry intervals and throughout 1975-99. On a
  simulated daily-3x S&P the 200d rotation still carries a -92% max DD and
  a LOWER Sharpe than the unlevered filter (Gayed & Bilello 2016). Our
  panel-B result (Sharpe 1.00 -> 1.16, five episodes, V-recoveries as the
  cost) is the textbook shape.
- Graded rules: the only refereed graded rule that beats binary after
  costs is STATE-conditional — blend slow and fast signals only when they
  disagree, weights shrunk to 0.5 (Goulding-Harvey-Mazzoleni "Breaking Bad
  Trends", FAJ 2024: Sharpe 0.64 -> 0.80). A fixed average of lookbacks is
  WORSE than the single slow rule (0.59 vs 0.64) — consistent with our vote
  gate being indistinguishable from binary; ramps by depth or duration have
  no support; slow models only pay for >=20%, >=6-month declines.
- CAPE timing: same Sharpe as buy-and-hold 1900-2015 and 1958-2015, -32%
  relative drawdown, fights momentum (Asness-Ilmanen-Maloney 2017); the
  10-year R^2 collapses under effective-sample arithmetic (Boudoukh-
  Israel-Richardson 2019); no primary evidence that "high for longer" adds
  to the level. Our inverse tests agree.
- Macro: the yield curve is the best recession predictor (4-6 quarter
  lead, no false positives on 10y-3m) and a 24/24 LOSER as an equity-exit
  trigger (Fama & French 2019); oil preceded 10 of 11 recessions with a
  1-15 month lead and one false positive (Hamilton 2011); credit spreads
  forecast activity, untested as a trend conditioner; the one refereed
  complementarity (Neely et al. 2014) is that technical signals catch
  PEAKS and macro signals catch TROUGHS — i.e. macro, if used at all,
  belongs on the re-entry side, not the tightening side the owner asked
  about.
- Volatility: scaling a daily-3x sleeve by realized variance is the one
  graded rule with mechanical (not statistical) support (variance drag is
  arithmetic; Moreira-Muir 2017 Sharpe +25%, but 72/103 strategies fail in
  real time, Cederburg et al. 2020). The house already measured vol
  targeting on HG (add. 20b: CAGR 105 -> 78%, Sharpe flat) — it stays shut.
- Multiple testing: best-of-7,846 rules fell from 17.2%/yr to 2.8%/yr in a
  10-year holdout (Sullivan-Timmermann-White 1999); published predictors
  lose 26% OOS (McLean-Pontiff 2016); t>3 is the hurdle (Harvey-Liu-Zhu
  2016). Every conditioner here is fitted to <=5 bears; read the family
  table that way.

COUNTER-AGENT (one hostile reviewer, 17 findings, scripts under
scratchpad/crash/verify2/): every printed metric, the proxy build (splice
seams exact; synthetic legs within 1.2%/yr of the real ETFs; dividend
accrual reproduces SPY total return within 0.06%/yr), the macro flags (0
mismatches, real-time), the trend placebos and the bootstrap reproduced
independently. REFUTED and fixed in this text: "adds return in every
sub-window 1990-2019" (2009-19 is a cost; the 1990s edge is one session);
the first macro placebo (tightened at the wrong level, under-counted flag
months — all panel-A macro percentiles collapsed from p90-p100 to p45-p73)
and the macro inverses (were 50d gates, not mirrors; two verdict words
changed: CAPE level beats its mirror in A, the curve loses on all three in
B); "G2/G6 are the best shapes" (selection effect); "damage in the first
weeks" (panel B only). Verdict after edits: showable; the long-history
family effect survives three nulls, inverses and block bootstrap.

DECISION (owner): the only live candidate is the simplest 200d-family gate
(binary, or G6) as a draft symphony for the standard gate tests; CAPE,
credit and curve conditioning are closed again; oil is noted, not adopted.

## Addendum 41 — How much of YTD 2026 came from leverage (2026-10-16)

Owner question: share of this year's return that is leverage; YTD return, Sharpe,
Sortino and max drawdown without it, against actual.
Method: the SAME signals, trades and days; every |L|>1 ETF swapped at the holding
step for its same-direction 1x version (TQQQ->QQQ, UDOW->DIA, TNA->IWM, TECL->XLK,
SOXL->SOXX, SQQQ->PSQ, TMV->TBF, UVXY->VIXY; USD/LABD/SOXS self-de-levered). Account
view = Composer's own time-weighted return minus each day's leverage contribution
from the holdings of the version live that day, weighted on Composer's start-of-day
base (deposit days included); HG's live holding read from its return where it
differs from the model (14 days), 22 days unresolved -> range. Window 2025-12-31 ->
2026-10-15 close, 198 sessions. Code research/leverage/ (lev_study.py, infer_live.py,
sharpe_boot.py, make_chart.py); exhibit results/leverage-ytd-2026-10-16.html.

RESULTS (live account)
                     TW return  money-wtd  $ gain   Sharpe  Sortino  maxDD   vol
  actual              +76.8%     +35.0%    $46.0k    2.01    3.22    20.1%  37.8%
  same trades, 1x     +27.2%     +10.1%    $13.2k    1.85    2.98     7.9%  15.2%
    range             +24.2 .. +27.2% (model holdings on unresolved days 25.5; best-fit
                      leaf 26.5; no deposit intraday effect 24.2; all self-de-levered 26.4)
  SPY / QQQ / UPRO    +14.1 / +18.9 / +31.7%; $18.8k / $19.6k / $44.0k; Sharpe 1.07 /
                      1.00 / 1.00; DD 8.9 / 11.7 / 26.8%
  since the money arrived (04-07): account +43.4% (Sh 1.90, DD 20.1) | 1x +13.0 (1.40,
                      7.9) | SPY +17.7 (2.25, 4.5) | QQQ +24.0 (1.83, 11.2) | UPRO +51.0 (2.19, 13.4)
- Leverage = ~50 pts of the 76.8 (two-thirds; 63% in logs); $32.8k of the $46.0k gain
  (71%). By engine (sum of daily, not compounded): HG 33.7 pts, KMLM 4.2, SLEEVE 2.5,
  ORIG -2.7, HARV 0. H1 (HG only) +57.9 vs +20.7; Jul-Oct15 +12.0 vs +5.4.
- Risk vs placement: the 1x path scaled to the account's vol (a constant 2.48x) makes
  +68.3% with a 19.4% drawdown -> ~41 pts from running more risk, ~9 from the leverage
  sitting on the better days.
- Sharpe 2.01 vs 1.85: paired block bootstrap gap +0.17 [-0.47, +0.93], P(>0) 0.65 ->
  about the same, not firm. In the Composer model (HG, current version) costed Sharpe
  2.04 -> 1.44 but frictionless 2.23 -> 1.96: half the model's drop is the same
  slippage dollars on a smaller return; the rest is placement (3x days carry 86% of
  HG's variance and +85%/yr of excess return levered, 71% and +26.5%/yr unlevered;
  the hedge/bond days' variance share rises 14 -> 29%).
- Engines (Composer backtest, current versions, full YTD, partly in sample; levered ->
  1x): HG +82.5 -> +20.7 (Sh 2.04 -> 1.44, DD 22 -> 9); KMLM +88.8 -> +30.6 (1.58 ->
  1.25, DD 21 -> 8); SLEEVE +23.8 -> +8.6 (1.48 -> 1.23, DD 10 -> 3); HARV +5.2 (no
  leverage); book 29/29/27/15 cap-40 +60.9 -> +18.0 (2.52 -> 1.87, DD 8.8 -> 2.8).

NOT MODELED / CAVEATS: signals not re-run on 1x prices (a different strategy); costs
held equal (1x spreads tighter, +1-2 pts to the 1x side); the 1x path still holds 1x
VIX-futures funds (VIXY/SVIX/ZVOL, 50-55% vol); Composer's TWR counts a deposit at the
start of its day, so the 04-28 deposit's intraday -7.5% is in the return (the other
convention reads +84.7%, same leverage share); 9.5 months -> actual Sharpe 90% band
0.3-3.8; Composer account only, no IBKR; pre-tax = after-tax (Act 60); 10-16's +3.2%
intraday excluded.

FINDINGS WORTH KEEPING: (1) HG's 06-30 edit was never deployed: on 07-02 live HG
earned XLV's return to 1 bp, a leaf only the original version has; the original ran
until the 07-30/31 update (lev_study.py SCHEDULE corrected). (2) Composer's costed
backtest at live weights reads +62.5% vs live +76.8% because of 13 flow-day artifacts
in the live series and the 5 bp slippage charged on HG's 162x turnover (HG frictionless
+94.6% / costed +79.2% / live +89.3%), not leverage. (3) ORIG was cash at the 06-30
close and held SOXL/TECL through the 07-07 liquidation window.

COUNTER-AGENT (three reviewers: numerical reproduction from scratch, instrument audit,
method/claims). Instrument map PASS (every L, direction and index verified against
issuer documents; ZVOL is -1x, VBF has no structural leverage). The reproduction
matched the draft to the decimal, then REFUTED four pieces of the estimator: deposit
days weighted on the wrong base (Composer's base includes the day's deposit; 04-06
subtracted UGE leverage at 99% weight on a 96%-cash account), ORIG off by one session,
the 06-30 HG withdrawal treated as invested all day, and a dollar replay that credited
deposits at the levered day return; plus one disclosure gap (unresolved HG days
hard-coded to the model holding; 07-02 UDOW accepted at 41 bp over XLV at 1 bp). The
method review added: the benchmark comparison reverses on money-weighted terms (UPRO
$44.0k vs the account's $46.0k; 1x $13.2k vs SPY $18.8k), "because" -> "partly
because" on the Sharpe mechanism, the cost wording, in-sample labels. All applied:
unlevered +23.7 -> +27.2 (range 24-27), Sharpe gap +0.45 -> +0.17, leverage 53 -> 50
pts, dollars $35.0k -> $32.8k. Verdict after edits: showable.

## Addendum 42 — Leverage gate lab: timing leveraged vs 1x legs (2026-10-17)

Owner question (10-16): is there a factor, or a few, that gate WHEN a leg is held
leveraged and when as its 1x version (same trades, only the leverage switches), and
how should such a gate be blended and applied across the engines? Research pass;
nothing changes live.
Method (research/leverage/levgate.py): every leveraged leg has a 1x twin (TQQQ->QQQ,
UDOW->DIA, SQQQ->PSQ, UVXY->VIXY ...); a gate is a per-day allowance in [0,1] read at
the prior close; switching is costed at the engine's measured bps on the effective
holdings. Leg roles: HG trend baskets {TQQQ,UPRO,UDOW,SSO,TNA} (add. 40's set), HG
dip-buys {QLD,TECL,USD,LABU}, inverse, long-vol. Panel B = HG on the 1990-2026 proxy
panel (out of sample for the rules); panel A = four engines 2015-06..2026-10 (in
sample for all four). ~50 factor shapes x {every leveraged long, trend baskets only},
plus application rows (dip only / all legs / long-vol only) and three fallbacks (1x,
half 1x half cash, cash). Nulls: inverse, 100 re-dated placebos, paired 20d-block
bootstrap vs as built. Book: 29/29/27/15 drift, cap-40 at the next close. Literature
and forward-dynamics brief: research/leverage/literature.md. Exhibit:
results/leverage-gate-2026-10-17.html. Counter-agent reviewed; fixes applied.

RESULTS — HG, panel B 1990-2026 (CAGR / Sharpe / Sortino / maxDD)
  as built                            +49.5 / 1.00 / 1.55 / 72%
  never levered (all longs -> 1x)     +22.9 / 0.89 / 1.58 / 38%   constant blends between: Sharpe 0.89-1.00
  200d gate, trend baskets only       +53.6 / 1.12 / 1.80 / 65%   inverse +30.9/0.81; placebo p1.00 (CAGR, Sharpe, DD);
                                                                  bootstrap Sharpe gap +0.04..+0.20, P(>0) 0.99
  200d gate, every leveraged long     +43.2 / 1.04 / 1.59 / 58%   with a 2% band +44.7 / 1.07 / 52% (P 0.85)
  200d gate, dip-buys only            +39.4 / 0.91 / 1.34 / 78%   dip-buys never levered: +36.1 / 0.86 / 78%
  fallback below the 200d (trend baskets): 1x +53.6/1.12/65 | half 1x half cash +54.6/1.14/62 |
                                           cash +55.5/1.16/60 (= add. 40's B1, reproduced exactly)
  by window (CAGR/yr) as built | 1x | half | cash: 1990-99 +38 | +43 | +44 | +45; 2000-02 -10 | +12 |
    +20 | +28; 2003-07 +34 | +37 | +38 | +39; 2007-09 -47 | +2 | +21 | +43; 2009-19 +55 | +54 | +53 |
    +52; 2020-26 +127 | +109 | +105 | +100.
  dip-buys alone (trend baskets always in cash, dip-buys at 3x): +30.2 / 0.94 / 60%; 2000-02 +77%/yr
    (in-window DD 60%), 2007-09 +84%/yr.
  factor ranking on the trend baskets (B Sharpe / A Sharpe / B 2007-09 CAGR): 200d 1.12 / 1.63 / +2;
    vol<25% 1.10 / 1.67 / -13; vol-rank 1.09 / 1.78 / -23; own-vol target 1.06 / 1.72 / -20; VIX<50d
    MA 1.06 / 1.88 / -22; VIX term 1.04 / 1.76 / -28; CAPE 1.03 / 1.88 / -47; credit 1.03 / 1.59 / +1;
    curve 1.03 / 1.59 / -23; fixed 1/3..2/3 1.03 / 1.72 / -7..-29. Several trend-only families clear
    the CAGR/Sharpe nulls; only the 200d family also cuts the long-bear drawdown (DD-better 1.00; the
    vol families ~0).
Panel A 2015-26 (in sample): HG as built +103.9 / 1.69 / 36; 200d trend-only +92.4 / 1.63 / 36 (half
  +89.4 / 1.61; cash +86.4 / 1.57); fixed 1/2 trend-only +86.1 / 1.72 / 26; trend baskets never
  levered +67.4 / 1.66 / 22; VIX<50d trend-only +107.2 / 1.88 / 28 (B: 1.06, no 2008 protection).
  HG's 36% DD (the 2020 gap) is cut only by vol/VIX/CAPE gates (28-33%), never by trend gates. KMLM:
  vol gates +186-188 / 2.21 / DD 45-48 vs as built +198.8 / 2.15 / 55; trend gate +165.7 / 2.15 / 52;
  inverse-leg panic gate neutral. SLEEVE: nothing moves. Book (as built +111.9 / 2.77 / 22.3): 200d
  trend-only on HG +107.7 / 2.76 / 20.5; on HG+KMLM +97.3 / 2.77 / 17.0; vol-target trend-only on
  HG+KMLM +105.0 / 2.79 / 19.9; cash gate on HG +104.9 / 2.72 / 19.8; never levered everywhere
  +62.0 / 2.52 / 10.7.

READ IT THIS WAY
1. WHERE the gate applies matters more than WHICH factor drives it. The trend baskets are
   what lose in long bears; the RSI dip-buys at 3x are HG's bear-market engine. Gate the
   baskets; never de-lever the dip-buys (worse on every metric in both panels).
2. The factor is the 200d, as in add. 40. Vol, VIX and CAPE gates look better in 2015-26 and
   worse over 36 years; the 200d is the only family with both the long-history edge and the
   2008 drawdown cut. Macro (credit, curve, T-bill, CAPE) adds nothing robust.
3. 1x vs cash below the 200d is a regime call: cash wins the long bears (2007-09 +43 vs
   +2%/yr), 1x wins the post-2015 whipsaw regime (+109 vs +100/yr; panel A +92 vs +86);
   over 36 years cash leads by 2pp CAGR, 0.04 Sharpe and 5pp DD, not significant. Half
   and half sits between them on every number.
4. Blends: running the baskets at a constant 2x buys Sharpe in 2015-26 (1.72 vs 1.69) and
   cuts DD (26 vs 36%) for 18pp of CAGR; over 36 years it is a wash (1.03 vs 1.00).
5. Book level, live-era regime: a gate trims 2-6pp of book DD for 4-15pp of CAGR at an
   unchanged Sharpe; the payoff lives in 2000/2008-type regimes (HG 2007-09: -47 -> +2%/yr
   at 1x, +43%/yr in cash).
6. Forward dynamics (brief): leveraged-ETF decay scales with variance (3x at 30% vol ~
   27%/yr; -3x decays twice as fast as 3x), so a gate's job is to predict variance and
   chop, not direction; financing at today's rates (~2x SOFR ~ 8%/yr on a 3x) lowers the
   cost of sitting in 1x; V-shaped recoveries since 2015 make re-entry lag the dominant
   cost; gap days (Aug 2024, Apr 2025, Mar 2026) are not avoidable at a daily cadence.
   Opinion, flagged as such: the post-2015 regime favours the 1x fallback; a 2000/2008-type
   bear favours cash.

NOT MODELED / CAVEATS: ~50 shapes x 2 leg sets, all shown (the best of a hundred reads
better than it is; the TREND set and the 200d shape were fixed in add. 40 before this
study); panel B legs are synthetic before the ETFs exist; signals read at the prior close
vs Composer's 15:50; hysteresis needs state Composer lacks (the plain 200d gives the same
numbers); FRED read same-day; KMLM's flag via RYMFX before 2020-12; per-leg gates skip
the placebo; the trend-only gate's 65% max DD is the 2001 dip-buy episode, which no basket
gate touches; costs equal for 1x and 3x trades plus the switching turnover.

COUNTER-AGENT (one hostile reviewer): reproduced every headline row to the decimal;
REFUTED the cash-fallback costing (BIL->BIL rotations charged as trades: fixed, cash rows
+1 to +8pp, add. 40's B1 now reproduces exactly), the cap-40 reset timing (a day early:
fixed), "only the 200d improves both panels' Sharpe" (false in 2015-26: reworded), "a 0.5
blend is the middle" (the true middle is the half-cash fallback: added), hysteresis as a
Composer-buildable rule (dropped), and the undisclosed in-window drawdown of the dip-buy
engine (added). Verdict after edits: showable; the core result is unchanged.

DECISION (owner): nothing changes live. If a leverage gate is wanted it is the plain
SPY>200d gate on HG's five trend baskets only, with the fallback (1x, half, or cash) as
the owner's regime call; KMLM's long legs would take a vol gate on in-sample evidence
only. Build path as add. 40: draft symphony -> fidelity gate -> counter-agent -> owner
approval of the swap.

## Addendum 43 — Canary signals as a leverage gate (2026-10-17)

Owner question: EMAs, CAPE levels, bond yields, retail leverage — the things the
treasury-canary tracks — is any of them an EV+ gate for when to turn leverage off?
Method (research/leverage/canary_gates.py on the add.-42 engine): each signal switches
HG's five trend baskets between 3x and 1x (dip-buys stay levered), used four ways: alone,
together with the 200d gate, as a condition on when the 200d applies, and its mirror.
Signals (24): SPY vs EMA50/100/200 and the EMA50/200 cross; CAPE < 25/30/35; 10y yield
< 5%/6%; 10y and 2y 12-month change; real 10y < 2%; ACM term premium 6-month change; the
canary's re-steepening window (its own GS10-TB3MS series, 12 months after a dis-inversion
that follows 3+ inverted months) with and without the inversion itself; FINRA margin debt
YoY > 40%, excess growth over the S&P > 25pp / > 15pp, excess with positive stock-bond
correlation, deleveraging; OFR stress > 0 / > 1; the canary's seven-indicator leading
stack in alarm. Publication lags: Treasury/ACM one session, OFR two, FINRA and the
leading stack month m from m+2, CAPE two months. Data: Treasury par and real curves,
NY Fed ACM, FINRA workbook, OFR FSI, FRED/ALFRED (keyless; canary_fetch.py). Margin
numbers reproduce the canary's (June 2026 +49.0% YoY, +28.2pp excess); leading-stack
alarm onsets reproduce its BACKTEST.md replay (2001-01, 2007-10, 2023-11, 2025-11).
Panel B HG 1990-2026; nulls: inverse, 100 re-dated placebos, paired 20d-block bootstrap
of the Sharpe gap vs as built and vs the 200d. Exhibit:
results/leverage-gate-canary-2026-10-17.html.

RESULTS (HG trend baskets, 1990-2026; as built +49.5 / Sharpe 1.00 / DD 72%; 200d gate
+53.6 / 1.12 / 65%)
- Alone, nothing beats the 200d. Best: EMA50/100/200 (+52.5..52.8 / 1.10 / DD 66-72),
  CAPE<35 (+52.6 / 1.09 / 71), OFR stress<1 (+51.8 / 1.10 / 66). Yields, the curve
  window, margin growth, the leading stack: ~as built (Sharpe 0.95-1.03) and worse than
  the 200d (P(gap>0) 0.00-0.05).
- On top of the 200d, four lift Sharpe by 0.03 or more: CAPE<35 +54.4 / 1.19 (gap
  +0.01..+0.13, P 0.97), CAPE<30 +51.2 / 1.17 (P 0.83, but -44% wealth vs the 200d),
  EMA100 +54.8 / 1.15 (P 0.89), margin excess<25pp +54.8 / 1.15 (P 0.94).
- Episodes vs the 200d alone: CAPE<35 +38% (1998-05..2000-09), +3% (2021-04..2022-04),
  +14% (2024-09..2025-03), -25% (2025-07..now, running); net +22%, peak lead +68% on
  2025-08-01. Margin excess: +32% (2000), then -3%, -3%, +5%. EMA100: many small
  stretches, net +33%.
- Conditioning the 200d on any canary regime never beats the plain 200d (P <= 0.35);
  the mirrors do as well or better. Same verdict as add. 40.
- Today: 200d and EMAs leveraged; CAPE 41.1 (Aug, the gate's input) -> every CAPE gate
  de-levered; 10y 5.09% and +1.1pp in 12m -> de-lever; real 10y 2.74% -> de-lever;
  margin +37% YoY / +18pp excess (Aug input) -> leveraged at 25pp, de-lever at 15pp;
  OFR stress, curve window, leading stack -> leveraged.

READ IT THIS WAY: no canary signal is an EV+ gate by itself. CAPE >= 35 on top of the
200d is the one combination that clears its band, and its timing beats 209 of 210
re-datings of itself, so it is not noise; but it is four valuation episodes with a
threshold chosen in hindsight (any cut from 30 to 42 gives a similar result from the
same 1998-2001 / 2021+ regime), its result depends on the end date, and it is 25%
behind the 200d in the stretch it is running now. Margin excess is "the powder, not the
pin" (the canary's own phrase): one winning episode. Watch, not gate.

COUNTER-AGENT (one hostile reviewer, before the leading stack was added): every number
reproduced; no look-ahead (0 mismatches on the lagged lookups, monthly lags and the curve
window). REFUTED: "the add-ons differ from the 200d only in 2000-02" (CAPE differs in
four episodes and is losing the current one), "best P 0.97 is what chance produces"
(the real CAPE flag beats 209 of 210 re-datings; the right caution is too few episodes
and a hindsight threshold), the quoted current values (the gate reads August's CAPE and
margin, not October's and September's), the curve series (now the canary's own GS10-
TB3MS), and the untested leading stack (now tested; its alarm months reproduce the
canary's replay). All applied. Verdict after edits: showable; no change from add. 42.

DECISION (owner): no change. The 200d gate on the trend baskets (add. 42) remains the
only gate with robust evidence. Optional: a pre-registered forward watch on
"CAPE >= 35 with the 200d" (log its live stretches against the 200d; revisit after a
completed episode).

## Addendum 44 — How far the HG 200-day gate was backtested (2026-10-17)

Owner question: how far was this strategy backtested? Exhibit:
results/hg-gate-backtest-coverage-2026-10-17.html (research/leverage/make_coverage_chart.py on the
add. 42 gate lab).

SPANS. Panel B 1990-01-03..2026-10-07, 9,228 sessions (36.6 yrs; the start is bound by the VIX
index, 1990-01-02, which HG's volatility legs are modelled from). The five gated legs are actual
fund prices from 2010-02-11 (16.6 yrs); every HG leg from 2015-06-01 (11.3 yrs; LABU the last
launch; = panel A, the stretch HG's rules were built on). HG live since 2025-12-05 (0.8 yrs); the
backtested version since 2026-07-31 (0.2 yrs; the December version differed in its defensive
branch, not in the trend or dip-buy logic); the gate: never live.

THE GATE BY DATA ERA (HG, panel B; CAGR / Sharpe / maxDD; x = ending wealth vs as built, 1x / cash)
  1990-99    rebuilt from indices          as built +36.9/0.84/66   1x +41.7/0.95/59   cash +43.9/0.99/59   x1.36 / x1.57
  1999-2010  rebuilt from QQQ/SPY/DIA/IWM  +21.8/0.58/72            +35.8/0.80/65      +43.7/0.93/60        x3.29 / x6.06
  2010-15    actual, rules not fitted      +36.4/0.94/55            +40.2/1.05/51      +41.6/1.08/49        x1.16 / x1.22
  2015-26    actual, in sample             +104.0/1.69/36           +92.5/1.64/36      +86.5/1.57/36        x0.52 / x0.36
  whole      1990-2026                     +49.5/1.00/72            +53.6/1.12/65      +55.5/1.16/60        x2.68 / x4.18

READ IT THIS WAY: the 36-year edge was earned in 1999-2010 (121-126% of the whole-panel log edge;
the dot-com and 2008 windows each give 53-62% of that era's edge; ~95% of it on days the held leg
was rebuilt from a 1x ETF, mostly QQQ x3). The 1990s gain is one session (1998-08-31: 78-80% of
the era's edge; without it x1.06 / x1.10 in nine years). On actual fund prices the gate helped in
2010-15 (5.3 yrs, the only stretch that is both actual and out of sample for HG's rules) and cost
11.5-17.5pp a year in 2015-26. The gate itself is in sample everywhere on this panel (add. 40
chose it after 15 shapes). It is insurance against a 2000/2008-type bear, about two episodes deep.

CAVEATS: rebuilt layers of the gated legs track the funds within 1.2%/yr where both exist (looser
for USD, LABU and the VIX models, each held <=2% of sessions and identically in both runs); 30
bond-market holidays skipped before 2007 lift pre-2007 CAGRs ~0.4pp/yr for every variant alike;
signal and trade at the same close vs Composer's 15:50.

COUNTER-AGENT (one hostile reviewer; scratchpad/verify_cov/): panel prices and the three variants'
daily returns rebuilt independently from base_B.json holdings (max diff 3e-16); every era number
reproduced. REFUTED and fixed: era-1 as-built CAGR +37.0 -> +36.9 (double rounding); "HG live 0.8
yrs" (these exact rules: 0.2); the fee-drag wording (USD's SOX rebuild carries a fitted premium;
the IWM and XBI layers use the fixed 1.8%); "within 1.2%/yr" as a blanket claim (holds for the
gated legs); "the 200d was fixed from the literature" (chosen on this panel); LABU's NBI layer is a
stand-in, not its index; SOXL (a signal input) was missing; three layout defects. The exhibit was
committed (5037b81) before the review finished; the fixes are in the next commit. Verdict after
fixes: showable.

DECISION: none; answers a question. The draft build still waits on the owner.

Follow-up (2026-10-18), owner: "did you test as if the 3x ETFs existed?" Yes: before each fund
launched, panel B prices it as L x its 1x ETF's or index's daily return minus T-bill financing and
a fee term, and HG's rules run on those prices as if the fund were tradable (2x ETFs from 2006, 3x
from late 2008). Fidelity where both exist (exhibit results/leverage-sim-vs-actual-2026-10-18.html,
research/leverage/make_fidelity_chart.py): 1x-ETF simulations drift +0.02..+0.77%/yr (fee term
fitted on those years except TNA's), index simulations -1.16..+0.35%/yr (not fitted); daily
correlation 0.995-0.999. All ten pairs match the add. 44 counter-agent's independent tracking
script exactly. Worst index day since 1990: -14.3% (Russell 2000, 2020-03-16); a 3x fund needs
about -33% to be wiped out. Not modeled: closures and halts.

## Addendum 45 — HG 200-day gate: draft built and checked against Composer (2026-10-18)

Owner instruction: "build the draft" (after add. 42-44). Built, saved uninvested, fidelity-
checked, counter-agent reviewed. Nothing live changed; the swap waits on the owner.

DRAFT. Composer symphony hZ6NSYPMQi3N0otU6lY6 "HG + SPY 200d gate (cash below) | DRAFT, do
not invest" (version NyvFccHtb3Bc1mikyuNk, 14:46 ET) = live HG (bP4mvRy6) with one condition
in front of each of its two trend-basket filters (top-1 RSI of TQQQ/UPRO/UDOW/SSO/TNA): SPY
current price > SPY 200-day moving average -> the basket; else -> BIL. 51 -> 63 nodes; every
original node keeps its id; dip-buys (still 3x), the long-vol branch, both BIL defaults and
the daily rebalance untouched. Builder research/leverage/build_gate_draft.py; snapshot
fixtures/hg-200d-gate-draft.raw.json (+ .summary.md); exhibit
results/hg-200d-gate-draft-2026-10-18.html.

FIDELITY (research/leverage/fidelity_check.py; Composer v2, reg+TAF fees, 5 bp slippage,
$10k, 2015-06-11 (LABU clamp)..2026-10-16, against the gate lab's panel-A model on 2,847
common days 2015-06-12..2026-10-07; CAGR / Sharpe / maxDD):
  live HG  Composer +104.4 / 1.69 / 35.8  model +104.0 / 1.69 / 35.9  corr 0.9999  drift +0.20%/yr  same holding 2,845/2,847
  draft    Composer  +86.7 / 1.58 / 35.8  model  +86.3 / 1.57 / 35.9  corr 0.9999  drift +0.20%/yr  same holding 2,845/2,847
  Composer's own stats fields: live 103.3% / 1.73 / 35.8%; draft 85.8% / 1.62 / 35.8%
  (Sortino 2.88, Calmar 2.39). Gate days: the draft holds BIL instead of a trend basket on
  204 of 2,004 trend days, in 25 runs; the model's 204 days are the same set (Composer reads
  adjusted prices; an unadjusted-close gate would give 234). The two holding misses
  (2017-05-10/12) are an exact RSI tie (29.50 / 29.50) between VIXY and UVXY in the long-vol
  filter, present in both trees. The +0.20%/yr drift is the engine's, identical with and
  without the gate. Saved-symphony backtest == ad-hoc backtest == exhibit.

READ IT THIS WAY: the draft does in Composer exactly what add. 42 modelled. The decision is
the one already on the table: the 2015-26 cost (CAGR 103 -> 86, Sharpe 1.73 -> 1.62, DD
unchanged) against the long-history case (add. 42/44: 1990-2026 +49.5 -> +55.5%, 1.00 -> 1.16,
DD 72 -> 60%, earned in 2000-02 and 2008). Live-era costs, in cash days: 34 after the April
2020 bottom, 36 in Jul-Aug 2022, 24 in Oct-Nov 2022, 12 in Apr-May 2025.

THE SWAP (not done): edit HG's own logic in place to the gated version — PUT on
mbkiXcuNDjueXpiox5Av with the gated logic and HG's own root id/name/description, verified
after the edit as on 2026-07-30 (VBF->VCIT). HG keeps its id and capital; applies at the
next rebalance; no capital moves. Today HG holds USD (a dip-buy, untouched by the gate) and
SPY is +5.7% above its 200d (10-16 close; +8.1% on 10-07), so the edit would trade nothing. In 2026 SPY sat at or below the
line on 12 days (03-20..04-07) while HG held BIL/QLD: no holding would have changed this year.

COUNTER-AGENT (one hostile reviewer, read-only; scratchpad/verify_draft/): live HG unchanged
(score byte-equal, versions head bP4mvRy6); draft absent from invested stats and holdings;
tree diff, gate semantics, the 204 days, every fidelity number, the RSI tie and the page's
numbers reproduced independently; rendering clean at 1100/390 px. REFUTED and fixed: "the gate
fired on no day in 2026" (SPY was below the line on 12 days; it changed no holding), the swap
wording ("a PUT of this tree" would carry the draft's id and name; cite the 07-30 edit), the
stretch count (22 merged -> 25 strict runs), a dangling add. 45 reference (this addendum).
Verdict after fixes: showable.

DECISION (owner, 2026-10-18, after the trade-off tables): "okay, deploy this." EXECUTED the
same day: live HG edited in place to the gated logic by PUT, new version 2oyXahw1VWpFtV15dhIi
(15:35 ET; previous bP4mvRy6); id, name, description, daily rebalance unchanged; no capital
moved. Verified: saved tree == swap tree; HG value $83,933 / holdings USD 99.9% identical
before and after (Sunday, nothing traded); Composer backtest of HG now == the draft's to the
last digit. First evaluation under the new logic Monday 2026-10-19. Rollback = PUT
fixtures/hg-live-pre-gate-2026-10-18.raw.json back onto HG. The draft symphony is kept
uninvested as the archive copy (renamed ARCHIVE...). Details: CHANGELOG 2026-10-18 EXECUTED.

POST-DEPLOY COUNTER-CHECK (second hostile reviewer, read-only, scratchpad/verify_deploy/): all
eight claims reproduced from the API — version head and root fields, own tree diff (51 -> 63,
the twelve gate nodes and nothing else), HG value/cash/holdings and the other three engines
unchanged (no queued deploy), fresh backtest by id identical to the draft's, archive copy
uninvested, monitor.py/divergence.py read the live symphony's current backtest (no stored
tree or version; the gated and pre-gate models hold identical positions on all 217 live-
window days, so the live-vs-model record does not shift), rollback fixture content-identical
to the pre-swap tree. Fixed on its report: this paragraph's SPY distance (was quoted from
10-07) and lev_study.CURRENT (was still the July version). Verdict: deploy verified clean.

## Addendum 46 — Gate watch: event-driven reports on HG's 200-day gate (2026-10-18)

Owner: not a daily line; reports when the gate is getting close to switching, with description.
Built: scripts/gate_watch.py, called by monitor.py after the accident gauge; 23 gate tests
(scripts/tests/test_gate_watch.py), each paired with a broken-input counterpart. Reporting only.

MECHANICS. distance = SPY close / 200-day SMA - 1 on Composer's adjusted data (one ad-hoc
single-asset backtest per run; the convention HG's condition reads). Zones: far > 3%, near
(0, 3%], tight (0, 1.5%], closed <= 0 (equality is cash, as Composer's "gt"). Hysteresis: near
re-arms only above 4%, tight only above 2.5%. Events: APPROACH, IMMINENT, CLOSED, STILL CLOSED
(Mondays while closed), REOPENED (with sessions below), APPROACH ENDED, OVERRIDE START/END
(live HG in BIL where the archived pre-gate tree, fixtures/hg-live-pre-gate-2026-10-18,
backtested ad hoc, holds a trend basket). Each report: distance and five-session change, the
one-day move that would cross, the line's 20-session slope, the base rate for the band, and
HG's branch (what a cross would do to its holding). Failures degrade to notes.

BASE RATES (SPY adjusted closes, 200-day SMA, 1993-11-11..2026-10-07, 8,281 sessions, 22.6%
at or below the line): closing within 1.5% above -> at/below within 10 / 20 sessions 62% /
69%; 1.5-3% above 28% / 41%; 3-5% above 11% / 20%; 5-8% above 3% / 9%. Within 1.5% below ->
back above within 10 / 20 sessions 78% / 85%; 1.5-3% below 46% / 66%; 3-5% below 26% / 47%.
107 stretches at/below the line: median 3 sessions, mean 18, 52% last <= 3, longest 313
(2000-09..2002-01; 2008-09 was 257). Daily sd of the distance 1.1%, five-session 2.3%; the line itself moves ~1%/20d.

CADENCE (watch logic replayed on SPY history): 1993-2026 ~2.6 APPROACH, 2.0 IMMINENT, 3.3
CLOSED/REOPENED and ~10 Monday notes a year; 2015-26 2.4 / 2.1 / 2.7 / 7.9; 2023-26 1.4 /
1.4 / 1.2 / 3.2. About two report-days a month on average, clustered in corrections, silent
in trends. Today: +5.7% (10-16), zone far, HG in its dip-buy (USD) -> no report.

NOT MODELED / CAVEATS: base rates are unconditional (no regime split) and descriptive; the
routine fires 17:35 ET, and if Composer's same-day close is not yet in, the report carries
the prior session's date (labelled); a run that sees no session newer than the last one assessed
(holiday, or the close not yet in Composer) skips, so a Monday holiday defers that week's STILL
CLOSED note; a watch started while already below the line initialises silently (no CLOSED event
for a pre-existing closure, closed-day counts start at the watch).

COUNTER-AGENT (one hostile reviewer, 35 mutants; scratchpad/verify_watch/): base rates and edge
conventions, the Composer SPY path (equal to Yahoo adjclose to 1e-7 over 310 days), every
transition, the monitor integration (temp-dir runs, alert path, state persistence) and the API
surface (GET + POST /backtest only) reproduced. REFUTED and fixed before the first run: an HTTP
error inside the watch would have exited the whole monitor run (composerlib raises SystemExit,
which 'except Exception' misses; now caught in both guards); a data outage during an override
produced a false OVERRIDE END (missing data now keeps the prior state); a re-served session was
assessed twice, double-counting closed days and repeating the Monday note (same-date runs now
skip); the longest closure is 2000-02 (313), not 2008-09 (257); 'without crossing' wording;
13 surviving mutants covered by 8 new tests (31 in all). Resolved on the first
run (Mon 2026-10-19, 21:36 UTC): Composer's ad-hoc backtest still ended at the prior session
(10-16), so the watch runs one session late and each line carries its data date; the override
check now requires the pre-gate model's date to equal HG's last rebalance date, else it keeps
the prior state (a live holding must not be compared with yesterday's model). Verdict after
fixes: enable.

## Addendum 47 — $100k in today's four-engine book from 1997 (2026-10-20)

Owner: "if I invested $100k in 1997 in the Composer set-up I have now, how much would I have today?
... just make proxies/synthetics of these ETFs." Research only. Exhibit:
results/book-since-1997-2026-10-20.html; code research/longrun/ (long_panel.py, book1997.py,
fidelity1997.py, sens1997.py, make_book1997_chart.py).

METHOD. The four live trees (HG with the 200-day gate = live 2oyXahw1; switcher, sleeve, harvester =
live scores) simulated daily from 1995-06 (warm-up) to 2026-10-07 on a long proxy panel: panel B for
HG's legs (add. 40/42/44); other funds rebuilt before launch from Vanguard bond funds (excess-return beta
on the overlap), Ken French CRSP industry/style portfolios, 1x bases x2/x3 financed at T-bills; the
switcher's managed-futures signal from RYMFX (2007) and before that an unfitted MLM-style trend proxy
(Treasuries / dollar index / GSCI); VIX funds from the term-structure model on the real VIX3M/VIX6M from
2006-07 and, before that, on a synthetic curve fitted from the VIX (main case). Composer-equivalent costs;
book 29/29/27/15 drifting with the 40% cap (Op 5); $100k at the 1996-12-31 close.

RESULTS (main case; CAGR on calendar time; Sharpe/Sortino over T-bills)
  book     ~$49.5B on paper, +55.4%/yr, Sharpe 1.63, Sortino 2.77, max DD 33.4% (2010-04..2011-08),
           worst year -8.8% (2011); $1M 2002-03, $10M 2014-01, $1B 2021-10
  1997-2014 $13.3M at end-2014 (+31.2%/yr); 2015-2026 x3,715 (+101%/yr; in sample)
  engines  HG +64.7% (DD 60%, 2001); switcher +79.0% (DD 83%, 2006-08); sleeve +21.2% (DD 51%);
           harvester +5.6% (DD 68%, 14.6 yrs underwater from 2009)
  SPY $1.73M (+10.1%, DD 55%); QQQ $4.05M (+13.2%, DD 83%)
SENSITIVITY (one change each; end-2014 / 1997-2014 per yr / final): HG without its gate $5.7M / +25.2% /
$27.2B; switcher signal pinned at RSI 50 pre-2007 $9.4M / +28.7% / $34.9B; trend proxy instead of RYMFX
2007-20 $25.0M / +35.9% / $145B; UVXY at today's 1.5x pre-launch $9.2M / +28.6% / $34.3B, through 2018
$7.6M / +27.2% / $26.0B; VIX carry constant / level-linear $50.3B / $36.9B; cap timing (next-but-one
close, 39.5%, 41%) $39-56B; no cap $1.1T (DD 48%); daily rebalance $30.9B. Max DD 26-36% throughout.
FIDELITY: daily correlation with Composer's own backtests 0.9999 (HG 2015-26), 0.9998 / 0.9992 / 0.9993
(switcher / sleeve / harvester, 2023-26); HG with the constant-carry VIX legs equals the reviewed panel-B
gate series exactly. The switcher's pre-2007 signal proxy is barely better than a constant (77-80% vs
72-79% decision agreement; below a constant against KMLM itself, 2021-26).

READ IT THIS WAY: the paper figure (~$26-145B, ~$50B central) is not an answer to "how much would I
have": everything above ~$10M (passed in 2014) exceeds the strategy set's capacity (add. 15), and the
2015-26 multiple is the years the rules were built on. What survives: before 2015, on rebuilt prices,
the book's rules compound at ~25-36% a year (25% without HG's in-sample gate) with a ~33% worst
drawdown, against SPY's 10%. The harvester earns little alone but lowers the book's risk (its 15% in
T-bills ends lower, $36.5B, Sharpe 1.61 vs 1.63).

COUNTER-AGENT (one hostile reviewer; scratchpad/verify_1997/): rebuilt the book, metrics, every year
cell, crossings, VIX modes and fidelity from primitives (all match); no look-ahead in any series; the
first ~57% proxy score was an inverted trend sign. REFUTED and fixed: headline precision (cap timing
moves it $39-56B: now a range), undisclosed UVXY 2x pre-launch, the switcher-signal stand-in missing
from the sensitivity, "all rules built on 2015-26" (HG's gate was chosen on 1990-2026: ~6 of the 31
points), "harvester is a drag" (it lowers risk), page formatting. Its sensitivity numbers reproduced
exactly by sens1997.py. Verdict after fixes: showable.

DECISION: none; answers a question.


## Addendum 48 — Shadow decision runner: Composer's holdings vs the approved logic, every session (2026-10-29)

Owner: "define shadow decision runner" -> "ok build the shadow runner". Built: scripts/shadow_runner.py,
called by monitor.py after the gate watch; approved-logic registry fixtures/approved/ (manifest + 7 trees,
one per approved version, by era); 98 merge-blocking tests (scripts/tests/test_shadow_runner.py, each
paired with a broken input; frozen fixtures shadow-2026-10-28.json.gz and shadow-warmup-2026-04-07.json);
research/shadow/ (backfill.py, calibrate.py, make_chart.py); exhibit results/shadow-runner-baseline-
2026-10-29.html; ledger results/monitor/shadow-ledger.jsonl (seeded with the 276 backfill rows). Keyless;
the daily path calls Composer with GET only (calibrate.py also runs POST /backtest simulations); never trades.

WHAT IT CHECKS, per engine, for session D (the latest final Yahoo close):
- NO REBALANCE: symphony-stats-meta last_rebalance_attempted_on < D, or the symphony paused in Composer;
  read from Composer's record alone (with Yahoo down, the session is dated from the exchange calendar), and
  a missing attempt date never ends it. Alert on the first session, daily while it lasts (Mondays only for
  a paused symphony), RESUMED once.
- The approved tree for D's era on Yahoo adjusted closes: add. 27 semantics, Wilder RSI over the whole
  2-year history (>= 60 closes), windows from fn-params or window-days (conflicting fields refused).
  Anything the evaluator has not been validated on is "unavailable", never guessed.
- AGREE: daily engines within 3% (half-L1). KMLM on its corridor path: the previous session's holdings
  drifted to the close; the target if any holding is more than 10pp off it, else the drifted holdings
  (both accepted within 1pp of the trigger); within 1.5%. Lenient (every holding within 11pp) without a
  previous session, or while a deposit may be in flight (net deposits moved on either day, a queued
  deploy, or more than 2% uninvested cash).
- KNIFE-EDGE (logged, no alert): not agree on closes, but agree when every decision ticker's close is
  replaced by its price 15, 10 or 5 minutes before the session's own close (15:45/15:50/15:55; 12:45.. on a
  half-day; Yahoo 5-minute bars, none older than 30 minutes). Without bars: a one-ticker move of at most
  0.3 sigma; two such sessions in a row on one engine alert.
- MISMATCH: alert, with the closest calls on the decision path.
- LOGIC DRIFT, every run, prices or not: the live tree (GET /score) vs the last approved era, compared on
  every field except display ones (numbers normalised). Alert when first seen or changed and on Mondays,
  naming the node; a new version with identical logic is a note.
- SHADOW BLIND (an engine unchecked 3 sessions running, a symphony missing from Composer's list included;
  likewise 3 days of failed drift checks) and SHADOW RUNNER DOWN (3 failed runs). A failed run leaves the
  state as it was; the ledger is read strictly before a write, written atomically, and a malformed line
  is skipped.

FIDELITY (calibrate.py; Composer's own backtests decide on closes like the runner). All 7 approved trees,
2026-04-01..10-28: 1,022 of 1,022 sessions identical (same tickers within 0.5%; KMLM's drifted backtest
holdings on the absolute-corridor path). In the six daily-rebalanced trees the runner follows all 276
allocation changes in Composer's backtests; compared one day off, agreement falls to 63%.

LIVE BASELINE (backfill.py: 74 snapshot commits -> 67 sessions, 07-15..10-23). 243 agree (92%), 21
knife-edge (8%), 0 mismatch. By engine (agree / knife-edge / mismatch): HG 65/2/0, KMLM 61/6/0 (63 of 67
sessions on the strict corridor path), SLEEVE 63/4/0, HARV 54/9/0. Of the knife-edges, 13 fall inside
the 5-minute-bar window (08-06 onward), and the logic on Composer's decision-time prices reproduces every
one (15:45: 9, 15:50: 1, 15:55: 3). The other 8 predate the window; the fallback confirms them at <= 0.14
sigma. The snapshots do not record attempt dates, so a past skipped session with unchanged logic would
read as agree.
2026-10-26..28: no rebalance attempt on all four (meta on 10-29: last attempt 10-23); the runner would
have alerted on 10-26. The logic wanted different holdings for KMLM (TLT 75% / PULS 25% on 10-26, then
SOXL + SVIX) and HARV (PULS 100%, then PULS / VXZ) while Composer held its ZVOL-heavy 10-23 positions; HG
(BIL) and SLEEVE (BOXX) were unaffected. Composer rebalanced again on 10-29: first live check, 4 of 4 agree.

CALIBRATION. Move from Composer's decision time to the official close, in 20-session daily sigmas (13
decisive tickers x ~60 sessions of 5-minute bars, 2026-08-06..10-29): from 15:45 median 0.08, p95 0.30,
p99 0.49; from 15:50 p95 0.27; from 15:55 p95 0.19. Fallback radius 0.3 sigma = the 15:45 p95. Placebo
(the logic at D against Composer's holdings from D-1, D+1, D+5 where those differ): with bars 2 of 271
excused (mismatch 257, agree 12); fallback only, 9 of 88 (mismatch 73, agree 6). KMLM's placebo used
the lenient check (an overstatement for KMLM).

SIDE FINDINGS (nothing changed):
- HARV, "VIX Harvester + HYG Credit Guard", has no HYG condition in any saved version (J6evkY1V,
  uQf3HrDb, XVtsDTV1, all logically identical to the community copy). Add. 12's "guarded symphony built +
  saved ... 9 ZVOL legs wrapped" is true of none of them. Its only guard is the UVXY RSI(14) > 70 switch
  to PULS, which add. 31 already treats as the guard. RUNBOOK.md corrected. Owner decision: rename it, or
  add the guard add. 12 approved.
- Composer made no rebalance attempt 2026-10-26..28 (confirmed from meta) and resumed 10-29.

NOT MODELED / LIMITS:
- Not checked: fill prices and timing, and cash. While a deposit may be in flight, KMLM falls back to the
  lenient check; how Composer invests a deposit into a threshold symphony is not verified.
- Composer does not publish its decision time; 15, 10 and 5 minutes before the close is what is tried.
- With Yahoo down, sessions are dated from NYSE's 2026-27 holiday list (extend it for 2028).
- Yahoo is the price source. A dividend or split it books before adjusting its series is repaired; one it
  never books is not.
- The corridor's absolute reading is inferred from Composer's backtests.

COUNTER-AGENT (one hostile reviewer; scratchpad/shadow/review/):
- Reproduced: the first build's numbers (1,020/1,022; 245/19/0/12), the calibration, the placebo, the
  registry (live trees byte-identical to the fixtures) and the HARV finding.
- REFUTED and fixed, blockers:
  - D1: no-rebalance detection depended on Yahoo, so a data gap could drop an engine from the alert or
    fire a false RESUMED.
  - D2: one malformed ledger line silenced the runner and left its state half-updated.
- REFUTED and fixed, should-fix:
  - D3: the 0.5-sigma one-ticker knife-edge excused 21% of wrong pairs. Replaced by decision-time prices:
    13 of 13 real cases, 2 of 271 wrong pairs.
  - D4: the 250-close RSI warm-up was the cause of the SLEEVE 04-07 miss, not a price tie.
  - D5: the drift check saw only new version ids, and only after Yahoo.
  - D6: canonical() missed select?, sort-by?, weight-method and window-days edits, and flagged ignored
    weights and number formats.
  - D7: data failures were silent.
  - D8: the lenient KMLM check missed wrong legs of 11pp or less.
- Nits fixed: the knife-edge streak across unavailable sessions; a "path" showing non-decisive checks;
  per-engine error isolation; dividend/split lag; daily repeats for a paused symphony; the UTC weekday; the
  ledger path; HARV's start date; the snapshot cut-off (now 16:00 ET).
- Tests: 25 of its 37 mutants survived the first suite; the rewritten 70-test suite kills 55 of 55
  re-expressed mutants.
- Round 2 (the fixes, hostile again; scratchpad/shadow/review2/):
  - Confirmed: D2, D4, D6 and D7 fixed; no false alarm on a normal day; the backfill reproduced exactly.
  - Three gaps remained, now fixed:
    - A knife-edge on a half-day (13:00 close) would have alerted as a mismatch. The decision minutes now
      follow the session's own close.
    - A Composer freeze during a Yahoo outage went unreported for two runs. The session is now dated from
      the calendar.
    - 25 of its 52 new mutants survived, including the daily wiring of D3, D5 and D8.
  - Also fixed: deposit timing on KMLM's path; silent gaps (a symphony missing from Composer's list,
    failing drift checks); canonical() defaults for select? and sort-by?, window re-encodings and
    sibling-weight shares; strict ledger reads before writes; typed rows; file mode; manifest failures.
- Round 3 was not a third review. The reviewer's half-day, deposit-flow and outage demonstrations now pass,
  and its 52 mutants (re-expressed where the code moved) plus 6 more all fail the 98 tests.

DECISION: none on symphonies. The runner joins the daily routine (POLICY standing cadence: its lines are
relayed and pushed, never traded on).

## Addendum 49 — Pre-close preview: what today's rebalance will do, before it does it (2026-10-30)

Owner, 10-30 (SPY -2.2%, KMLM levered long): "Shouldn't we be doing gate checks before market close? In
the event we need to make changes in more real time? So it's not gate checking in arrears?" Yes. Composer
decides at ~15:50 ET on live prices; the gate watch (add. 46) and the shadow runner (add. 48) read the
close at 17:35, after the fact. Built:
- scripts/preclose.py: its own scheduled run at 15:15 ET on weekdays (12:15 on NYSE half-days).
- 50 merge-blocking tests (scripts/tests/test_preclose.py).
- research/preclose/: leadtime.py, replay_1030.py, make_chart.py.
- Exhibit: results/preclose-leadtime-2026-10-30.html.
- Ledger: results/monitor/preclose-ledger.jsonl.
GET-only and keyless; it never trades, pauses or edits a symphony.

WHAT IT PRINTS (approved trees, the shadow runner's evaluator, Yahoo's latest trades as today's close):
- GATE: SPY live vs its 200-day average, and the SPY price that flips it. The average includes today's
  price, so that price is the mean of the other 199 closes; the evaluator flips exactly there (tested).
  Also yesterday's state, and what HG holds on each side of the line: HG's dip-buy branch does not read
  the gate.
- Per symphony: holdings now -> after the ~15:50 rebalance (KMLM: the target only past 10pp; a paused
  symphony: nothing), and the dollars that move.
- How close each call is, in sigmas of the move left (daily sigma x 0.6 x sqrt(minutes / 390)), from two
  probes, each naming the holdings it would lead to:
  - the whole market moving 1 or 2 sigma either way, every fund by its 60-session beta to SPY;
  - the nearest one-ticker move (bisected).
  Labels, for a change of 25% or more of the holdings:
  - close call: a 1-sigma move of either kind causes it, or KMLM's trigger is within 1pp;
  - could flip: a 2-sigma move does, or a stale input might;
  - firm: neither.
- Stale quotes (last trade more than 15 minutes old) are rebuilt from a fresh fund on the same index at
  its daily leverage, or from a related index (semiconductors from USD, tagged approx). Otherwise they are
  used as they are, named, and stress-tested at 2 sigma since they last traded.
- Alerts (exit 2, pushed):
  - GATE CLOSES / REOPENS AT TODAY'S REBALANCE
  - GATE ON THE LINE (within 2 sigma)
  - BIG DAY (SPY 2% or more off yesterday's close)
  - PRE-CLOSE UNAVAILABLE (no prices, no trading today, or a failed run)

FIRST LIVE DAY (10-30). The first version, read at 15:27 on the live feed, said:
- HG: BIL -> QLD 100%, "could flip" (QLD +0.44% -> USD).
- KMLM: -> TECL 75 / ZVOL 15 / PULS 10, "could flip" (TQQQ +0.87% -> SOXL 75).

Composer ended at:
- HG: BIL 100%.
- KMLM: SQQQ 75 / ZVOL 13 / PULS 12.
- HARV: ZVOL 52 / PULS 48 (preview ZVOL 60 / PULS 40, under the 25% line).
- SLEEVE: BOXX 100%, as previewed.

Cause: TQQQ's 10-day RSI sat at 29.6-29.8 until 15:45. An ordinary Nasdaq-led move (TQQQ +0.6% by 15:45,
about 1 sigma, while IVV moved +0.1%) lifted it to 30.05 at 15:50. That switched off both engines'
"RSI(TQQQ,10) < 30" dip-buy branches: HG fell through to BIL, and KMLM to a top-RSI pick, SQQQ. Re-run on
15:50 prices, the logic reproduces Composer exactly; at 15:45 it still said QLD / TECL. The first
version's alternatives were wrong: USD for HG, and SOXL 75 for KMLM, from a SOXL quote frozen since
14:41.

Also that afternoon:
- Yahoo froze 11 quotes, including SPY, SOXL, SQQQ and SPXL, at 14:25-14:55, while IVV, VOO and QQQ
  stayed live.
- Composer's API answered HTTP 503 once, at 15:33, and was back by 15:35.

The revised preview, replayed (replay_1030.py; results/preclose-replay-2026-10-30.txt) at 15:15 and 15:27,
with no quote lag and with the live feed's 5-minute lag. The replay uses bars Yahoo backfilled after the
close, so the frozen quotes are filled in: it shows what a healthy feed would have given.
- Main call: still QLD / TECL 75 in every variant. It is the logic on the read's prices, and the call
  flipped after 15:45.
- Labels:
  - HG: close call (15:15, both lags; 15:27 with no lag), could flip (15:27 lagged).
  - KMLM: close call (15:15, no lag), could flip otherwise.
  - Round 2's live 15:30 snapshot gives "could flip" for both, the same label the first version gave.
- Alternatives:
  - KMLM: SQQQ 75 in all four variants.
  - HG: BIL in three of four; the lagged 15:27 read shows QLD +0.41% -> USD instead.
- So the revision's gain on 10-30 is the alternatives it names, not the label, and on one day.

LEAD-TIME STUDY (leadtime.py; 59 sessions 2026-08-07..10-29, Yahoo 5-minute bars). Each engine's logic is
run at each minute and compared with its answer at 15:50:

  read at   same holdings (<= 3%)   no material change (< 25%)
  15:00     217 / 227  (95.6%)      221  (97.4%)
  15:15     221 / 228  (96.9%)      225  (98.7%)
  15:30     228 / 232  (98.3%)      229  (98.7%)
  15:40     229 / 234  (97.9%)      230  (98.3%)

- 15:15 labels:
  - close call: 39, of which 3 changed materially by 15:50. In all 3 the 15:15 alternatives named the
    answer (HG 09-08, KMLM 09-29, HARV 10-21).
  - could flip: 35, none changed.
  - firm: 154, none changed materially (4 changed by less than 25%).
- The move to 15:50 in daily sigmas (liquid tickers, ~2,200 per horizon): RMS 0.52-0.56 x sqrt(t / 390)
  for t = 10-50 minutes; p95 about 2 x RMS, p99 3-3.4 x RMS. A daily sigma carries the overnight gap and
  the open. The preview uses 0.6: round 1's 2-year hourly check put this window about 13% below the
  2-year level.
- Gate: open at 15:50 on all 59 sessions; no crossing in the window.

HONESTY BOX:
- One live day, and it went wrong. The revision was built after seeing it; the replay uses backfilled
  bars.
- On 10-30 the flip came after 15:45, on an ordinary ~1-sigma Nasdaq move. No read at 15:15 could have
  called it; the preview can only say the call is near a line and what lies across it.
- Labels change from minute to minute around 15:15, and with quote lag. Treat close call and could flip
  alike: the logic is near a line.
- The study compares the logic only, with no corridor and no feed problems. The label rules and the 0.6
  scale were set with this window in view. The label result rests on 3 events: indicative, not a rate.
- The window was calm: no 2% SPY day (largest 1.55%).
- 0.6 rests on one proxy (round 1's 10 tickers on the 14:30-15:30 bar); other cuts give 0.565-0.74, and
  quarters range 0.52-0.86.
- The market probe: in the window it changed 7 of 228 labels, none of which then moved; all 3 material
  events came from the one-ticker probe alone. It moves funds by 60-session daily betas, which overstate
  late-session moves of TQQQ, QLD and SQQQ by about 40%, and correlations that break on the day are not
  in it. It has one live day.
- 15:50 stands in for Composer's decision minute (15:45-15:55). Gate timing within the session is
  untested: there was no crossing.
- The rebuild assumes daily reset and ignores fees and intraday premium or discount. A cross-index
  stand-in (SOXL from USD) was tried and dropped: 3.4% RMS error a day, 8.9% on 10-30, worse than the
  stale price.
- The preview is not a recommendation. The RUNBOOK default, no intraday intervention (measured five
  ways), stands.

COUNTER-AGENT, round 1 (one hostile reviewer, scratchpad/preclose-review/): ship-with-fixes.
- Reproduced: every headline number; the gate math; the rebuild arithmetic; the family table and the
  NYSE calendar (official 2026-28 release).
- Blockers, both fixed:
  - The gate alert claimed "HG moves to BIL" even where HG's dip-buy branch ignores the gate.
  - An empty-holdings symphony crashed the report.
- Should-fixes, all fixed:
  - Stale inputs off the traced path were not flagged; today's KMLM alternative is the case.
  - An unscheduled closure previewed yesterday's prices.
  - A paused symphony showed a trade.
  - Failed drift checks were silent.
  - The 25% grid overstated sigma.
  - "Coin-flip" meant a 13-50% chance; it is now "close call".
  - KMLM's trigger had no ambiguity band.
- Tests: 23 of its 54 mutants survived the 30-test suite. The 50-test suite pins each of the 17 real gaps
  (the nearer of two tickers, corridor max gap and 10pp, materiality, radius, corridor-aware flips,
  yesterday's window, distance sign, gate_in, family table, up-day BIG DAY, the UNAVAILABLE conditions,
  closed-side ON THE LINE, stale filtering, dollars from the outcome). It also caught a grid that never
  reached the 3-sigma edge.
- It also graded today independently and reached the same root cause.

COUNTER-AGENT, round 2 (one hostile reviewer, scratchpad/preclose-review2/): ship-with-fixes.
- Confirmed:
  - All round-1 fixes except D6 (gate sigma with a stale SPY).
  - No regression: targets, outcomes, dollars and gate values identical to 039a354 on five inputs.
  - About 3 s a run.
  - One alert in 60 sessions at 15:15 (10-30's BIG DAY); the gate never came within 30 sigma.
  - The study JSON reproduced row by row.
- REFUTED and fixed:
  - The SOXL-from-USD stand-in was 8.9% off on 10-30 and was never stress-tested. Removed. Carried
    tickers are stress-tested, and alternatives that read one are flagged.
  - The replay claims (both close calls; "4 sigma"; "IVV +0.45%", which used a bar running past 15:50)
    were overstated. The live-day section above is rewritten.
  - Unpinned headline outputs: the close-call threshold, upside scenarios, and a signed gate distance.
  - Quote age was left out of sigma. Now added: the median age of the fresh quotes, plus a stale SPY's
    own age on the gate (D6).
  - Nits: a repeated error prefix, and rebuilt tickers listed twice.
- Tests: 33 of its 112 mutants survived the 50-test suite. Against the 71-test suite:
  - 98 of the 99 that still apply now die. The survivor, F7 (a coarser grid), is near-equivalent:
    bisection recovers the threshold.
  - 8 re-expressed where the code moved also die; 5 are moot (the stand-in is gone).
  - So do 8 new mutants on the round-2 code (label thresholds, quote age, stale SPY, alternatives reading
    stale).
- Its D1-D8 demonstrations, re-run on the fixed code, pass. D6 is fixed in how preview() sizes the gate's
  sigma, which the demo calls around.
- Kept as caveats, not changed: the beta overstatement, the 0.6 proxy, and minute-to-minute labels.

DECISION: none on symphonies. A new 15:15 ET weekday routine, report-only (POLICY standing cadence; half-
day runs at 12:15). RUNBOOK updated: what the preview is for, and what a pause or a liquidation does.

## Addendum 50 — Shadow runner: Composer's decision window checked minute by minute (2026-11-01)

Owner, 11-01: "is yahoo the best source here? what about our FMP API?", then "build it", then "use FMP for
the 15:15 preview quotes too".

Friday 10-30's two SHADOW MISMATCH alerts (KMLM and HARV holding ZVOL/PULS 52/48 against the logic's
60/40) were a knife-edge the old check could not see. The split flips on RSI(SPY,4) against 25, at SPY
756.13. In the decision window only one minute's price was above it: 15:54 (756.28). At the snapshot
times FMP's minutes read 753.25 (15:45), 754.27 (15:50) and 756.07 (15:55); Yahoo's own snapshots are a
few cents off (754.30 at 15:50, 756.10 at 15:55). The gap was the time grid, not the source: FMP's
minutes and Yahoo's 5-minute bars agree to 3 cents on 92% of 16,853 pairs (counter-agent).

CHANGE (scripts/shadow_runner.py):
- The decision-time check reads FMP 1-minute prices (/stable/historical-chart/1min, key FMP_API_KEY) at
  every minute from 10 to 5 minutes before the close: 15:50-15:55 ET, 12:50-12:55 on a half-day.
  - The price at a minute is the close of the 1-minute bar ending then.
  - A fund with no trade that minute keeps its last trade, none older than 30 minutes.
  - A minute missing a decision ticker's price is skipped.
- FMP's day is used only when it passes vet_minutes (the close from the exchange calendar):
  - SPY has a bar in the session's last minute and in every minute the window reads (bars starting
    15:49-15:54);
  - no fund that traded in 20 of the 30 minutes before its last bar stops more than 5 minutes before
    the close.
  Otherwise the older checks decide, and the row and any MISMATCH alert say why ("FMP minutes not used:
  ...", naming only that engine's tickers; with no key, that the key is not set). SPY is fetched first,
  so a dead or lagging feed costs one call.
  - On real data the rule flags nothing: 0 of 343 full FMP ticker-days (counter-agent; VBF peaks at 19
    of 30, one under), and 0 of the 3,773 cached ones (only 2 of which end before 15:55).
  - Not caught: a gap inside a dense fund's window (none in those 343 days) and a thin fund cut early
    (indistinguishable from its last trade).
- Without usable FMP bars the old checks follow: Yahoo 5-minute snapshots (15:45/15:50/15:55), then the
  0.3-sigma one-ticker search.
- A knife-edge records its source (fmp-1m / yahoo-5m), every matching minute (`times`) and, as `time`,
  the one nearest 15:54.
- New alert SHADOW FMP DOWN: each run that checks a session reads SPY's FMP minutes for it. Unusable
  (refused, no key, incomplete) is noted every such run. It counts once per new session, never on a
  re-check; 3 sessions in a row alert, then Mondays while it lasts.

THE WINDOW, MEASURED (the counter-agent's finding, reproduced by minutes_calib.py): the logic on each
minute's prices against Composer's holdings, 272 engine-sessions.

  minute       15:40-15:50  15:51  15:52  15:53  15:54  15:55  15:56  15:57-16:00  official close
  contradicts  9-13         3      5      6      1      9      13     12-21        23

  Composer's decision prices sit at ~15:54. 15:51-15:54 alone explains all 23 disagreements; the shipped
  window adds a minute either side. The first draft's 15:44-15:56 bracketed an assumed 15:45-15:55 that
  had never been measured.

FMP facts found while building:
- One session per call: a range returns only the last 3 calendar days up to `to`, so a weekend inside
  it drops sessions. (This silently thinned the first prefetch; caught and fixed.)
- A date FMP lacks returns the latest day it has, so bars are filtered to the session asked.
- A refusal (any non-list answer) is an error, never read as "no bars".
- 1-minute history goes back to at least 2023. Timestamps mark the bar's start, New York time, in summer
  and winter time; half-days end at 12:59 (counter-agent).
- Bars are unadjusted (checked on 62 ex-dividend days). FMP's last bar vs Yahoo's raw close: median 2 bp,
  p99 34 bp, max 110 bp (VBF).
- Thin funds are sparse: VBF (a decision ticker in an earlier era) trades in 40% of the minutes 15:25-
  16:00, CORP in 67%, every other decision ticker in 92% or more.

MEASURED (research/shadow/minutes_calib.py, old rule vs new on the same inputs; results/shadow-minutes-
2026-11-01.json, exhibit .html; 69 sessions with a committed holdings snapshot, 2026-07-15..10-30):
- 272 engine-sessions: 249 agree under both rules. The 23 disagreements:

  rule  knife-edge, FMP minutes  knife-edge, Yahoo snapshots  knife-edge, one-ticker search  mismatch
  old              -                       13                            8                      2
  new             23                        -                            -                      -

  Matched minutes per case: median 6 of 6. Fewest: 10-30 KMLM and HARV (15:54 only), 10-08 HG
  (15:50-15:51). `time` is 15:54 for 22 of 23.
- Control: 370 pairs, the logic at D against Composer's holdings from D-1, D+1 or D+5 where they differ.
  18 are not wrong pairs: 14 equal the logic's own answer at D, 4 sit inside KMLM's corridor. Of the
  other 352:
  - The old rule excused 16: 14 by the search, 2 on snapshots.
  - The new rule excuses 3, all on FMP minutes. HG 07-27/07-28 is one genuine knife-edge between those
    two days' holdings, seen from each side. SLEEVE 10-12 was excused by the old snapshots too.
  - Across windows the excused count moves by one or two (15:44-15:56: 4; 15:45-15:55: 4; 15:50-15:55:
    3; 15:51-15:54: 2). The 16 -> 3 comes from real prices replacing the search, not from the window.
- Harder controls (counter-agent, its own code; first draft / shipped / old rule):
  - One decision condition flipped, 1,650 alternatives: 19 / 16 / 25 excused.
  - Other-day holdings at lags +-1, 2, 3, 5, 979 pairs: 11 / 10 / 33.
  - On the sessions with Yahoo bars, the shipped window excuses 11 of 1,313 flipped conditions vs 13 for
    the snapshots, and 1 of 326 weight-shifted targets vs 0.
- Ledger:
  - The 10-30 KMLM and HARV live rows were reclassified mismatch -> knife-edge at 15:54 (fmp-1m) by
    research/shadow/reclassify_live.py. Their 'reclassified' field records on, from, by, and `was` (the
    original why/checked). They hold under the final window: 15:54 is inside it.
  - state.json and last-snapshot.json say mismatch for 10-30 until the next run overwrites them.
  - The backfill rows keep add. 48's classification; minutes_calib.py records theirs under the new rule.
  - backfill.py now classifies with the same chain.
- Tests: 128 shadow tests (19 new: S18, S19 and S17's time rule).
  - Mutants of the new code: 36 of 36 killed after round 1, 30 of 30 after round 2, run on a copy. They
    include every real gap either counter-agent found.
  - Round 1's six other survivors are equivalent. at_times now labels its own source, so round 1's L3
    (a mislabelled old-rule column) is moot.

HONESTY BOX:
- In-sample: the window was read off the per-minute profile of the same 69 sessions it is scored on.
  All are summer-time full days; half-days and winter time are checked on FMP's data, not end to end.
- A wrong holding one minute's price away from the logic is excused by design: a knife-edge and a
  one-minute error look alike. A one-condition difference within 1% of its threshold is excused 7 of 16
  times by the shipped window, 8 by the old rule (counter-agent). Minute-based knife-edges never alert.
- Composer does not publish its decision time; 15:54 is measured, not documented. If it moves outside
  15:50-15:55, disagreements show as mismatches (alerts), not hidden ones.
- FMP is one more data dependency. Unusable data now falls back with the reason in the row, and SHADOW
  FMP DOWN fires after 3 sessions. Whether FMP's same-day minutes are complete by the 16:35 ET run is
  unmeasured until Monday 11-02; the per-run SPY check measures it.
- Minute prices are raw, scaled onto the adjusted series by Yahoo's adjusted/raw factor for the day.
- The preview (add. 49) still times Composer's decision at 15:50. The measured ~15:54 adds ~4 minutes
  to its horizon at 15:15: sigma ~6% narrow, inside the headroom of its 0.6 scale (measured 0.52-0.57).
  Re-baseline at the next preview study.

COUNTER-AGENT (minute check): SHIP WITH FIXES. It rebuilt the study with its own code and reproduced
every row.
- Should-fix failure modes, both fixed:
  - No completeness check: a lagging SPY series shifted the window, raising false MISMATCHes or
    excusing wrong pairs, and a cut feed passed. Fixed by vet_minutes and the fallback note.
  - FMP failures were silent. Fixed: the note on every fallback and SHADOW FMP DOWN.
- Two production paths untested, 16 of its 49 mutants surviving (10 real gaps): 12 tests added.
- Wrong or overstated claims, all corrected here and in the exhibit:
  - the 18 control pairs;
  - "brackets the 15:45-15:55 it is observed to use";
  - "the control measures that directly";
  - the 10-30 minute narrative;
  - ZVOL named as the thin decision ticker;
  - the test count.
  Its per-minute profile is now the window's basis.
- Nits fixed:
  - `time` / `times`;
  - the reclassified rows keep their original text;
  - the calibration cache path;
  - the CHANGELOG wording;
  - one call for a dead feed.
- Outside this change: the FMP key sat as a literal default in barbell-lab/research/barbell_timer/
  fetch_data.py in this public repo since 2026-08-12 (with a FRED key). Removed in 528f6d6. The leaked
  values must be rotated (owner).

COUNTER-AGENT, round 2 (minute check): SHIP WITH FIXES. The production path works end to end on 10-30
as monitor.py calls it: key set, no key, FMP down, no disagreement. All fixed:
- Untested paths: SHADOW FMP DOWN reaching the alerts, its once-a-day guard, the vetting thresholds, a
  lagging SPY's call count, the search path's note, a raising fetcher. 31 of its 58 mutants survived; 7
  tests (S19) and boundary cases added.
- The alert fired again when a session was re-checked on a later day, and a date going backwards
  counted twice. It now counts and alerts once per new session.
- Notes blamed other engines' tickers (the day's problems were not filtered). They are now the engine's
  own plus SPY, and a lacking ticker is always named.
- A gap inside SPY's window minutes passed the check. SPY must now have every window minute.
- Stale docstring and overstated claims, corrected:
  - "including the counter-agent's surviving ones";
  - "settled" for "explained";
  - "no feed cut short";
  - the 15:50 snapshot price;
  - "vetted as the daily check vets them";
  - "each run reads".
- Silent no-key rows: they now say so.
- In-place mutation of the shared tree: mutants now run on a copy.
- The fetcher truncated an error before redacting the key, and one bad row could fail a ticker. Both
  fixed (round 1 of the preview's review).

ALSO — the 15:15 preview's live prices (owner, 11-01: "use FMP for the 15:15 preview quotes too"):
- scripts/preclose.py prices each ticker from FMP's last traded minute: the last 1-minute bar WITH VOLUME
  ending at or before the run. Its close is the price and its end the time: a trade, of any size (FMP counts
  fractional shares), fell in that minute.
  - Bars with no volume are skipped. For thin funds FMP fills quiet minutes with quote-based bars: share
    of bars with no volume over 10-19..10-30, counter-agent: PEJ 85.6%, VXZ 85.1%, VIXM 60.7%, CORP 36.7%,
    KMLM 35.2%. Of 12,365 such bars, 82 fall in a minute where Yahoo shows a trade. Read as prices, they
    made a stale fund look fresh: PEJ read stale in 0 of 240 checks with them, 57 without.
  - FMP's price is used unless Yahoo's last sale is more than a minute newer, or FMP has no traded bar
    today.
  - SPY is asked first. No SPY bar, or a refusal (its reason kept), makes FMP unusable: the report says so
    and uses Yahoo's prices. The rest have 90 s, then fall back to Yahoo, named.
  - A replay (the run's clock more than 5 minutes behind the wall clock) reads nothing stamped after its
    own time, FMP's or Yahoo's. A live run cuts nothing: a slow fetch, a late sibling or a lagging clock is
    not the future.
  - Yahoo's 2-year adjusted history is unchanged. SPY's must reach the previous session or the preview
    stops (PRE-CLOSE UNAVAILABLE). Other funds short of it are named, with a caveat on their engines.
- Reporting:
  - The report names the source and FMP's per-ticker problems.
  - A Yahoo sale inside FMP's last traded minute and more than 0.3% from FMP's close is listed (FMP's is
    used). A later sale is the market's move, not the feeds', and is not compared.
  - The ledger's `quotes` record keeps, for every decision ticker, both prices with their times and which
    was used (`fmp`, `yahoo`, `via <sibling>` for a rebuilt price, `carried` for a stale one): the feed
    comparison at ~15:15 from Monday on.
- How well the feeds agree (counter-agent, 10 sessions):
  - At 15:15 on the shipped read (traded bars), the 40 liquid decision tickers are within 0.05% of Yahoo
    in 92.5% of cases and within 0.1% in 98.0%; the 7 thin funds in 74.3% and 80.0%.
  - Two gaps over 0.3% remain, both VXZ (0.95% on 10-22, 0.67% on 10-26): traded FMP bars on a fund
    Yahoo prints sparsely. (On the all-bars read every gap over 0.3% was a no-volume bar.)
  - Neither feed is shown to be the consolidated last sale: Yahoo's prices match Nasdaq's NLS; FMP's
    per-minute volume matches the consolidated figure for liquid funds, not thin ones (its minute sums
    are 55% of KMLM's daily volume, 191% of PEJ's). Which feed Composer prices on is not known. The
    ledger compares them at ~15:15; the decision-time comparison (~15:54) belongs to the minute study.
- FMP's batch quote, the first draft, was dropped (round 1): it is not the last sale for thin funds.
  - At Friday's close: PEJ 66.49 at 15:59:42 vs 66.39 (Nasdaq's last sale and FMP's own end-of-day
    close). FMP's 10-30 minute bars changed between two 11-01 fetches (the 15:59 bar now reads 66.49 with
    no volume; the last traded bar 15:58 at 66.40): FMP-derived minute figures here are snapshots of
    their fetch time.
  - ZVOL 7.08 vs Yahoo's 7.0847 at 15:57:43. FMP's ZVOL bar at 15:59 has no volume and carries 7.08, as
    does its last traded bar, at 15:57.
  - Its timestamp is not always a trade: 55 of 222 thin ETFs carried a ~10:00 time with the previous
    close.
- Checked:
  - Friday 10-30 replayed at 15:15 on FMP's traded minutes gives add. 49's replay on Yahoo's 5-minute
    bars: SPY 753.23, the gate's distance, and the calls and labels of all four engines (TQQQ's flip
    +0.57% vs +0.56%).
  - At 15:27, FMP's minute grid reads SPY two minutes fresher than the 5-minute bars (753.39 vs 753.05),
    so KMLM is a close call instead of could flip. PEJ reads stale since 15:04, as Yahoo's bars have it
    at 15:05.
  - Over 10 sessions at 15:15, the gate, targets and labels match the 5-minute replay on 10 of 10; the
    stale notes differ on 4 (10-20: FMP's traded PEJ bar is newer than Yahoo's sale). From 14:30 to
    15:45 the feeds differ somewhere in 10 of 130 runs: in a label in 5, in a target once (SLEEVE, 10-22
    15:10).
  - The committed Yahoo-only replay (results/preclose-replay-2026-10-30.txt) was regenerated with FMP
    off: identical apart from the new "live prices" line.
  - Tests: P11, 35 tests; 106 in the suite. Mutants, on copies: round one, 36 (34 killed at first, the 2
    survivors closed by tests and re-killed); round two, 30 (likewise 2 closed); round three's lens ran
    57 of its own and 31 survived, 25 behavioural: the constants' exact values and boundaries, which are
    not pinned, plus the live/replay split, whole-minute replays and the budget's return, which now are.
- Not measurable on a Sunday:
  - whether FMP serves the 15:14 bar by 15:15;
  - whether live minutes carry the no-volume fills;
  - Yahoo's live lag;
  - Composer's own price source.
  Monday 11-02's 15:15 run is the first live one.

COUNTER-AGENT (preview quotes):
- Round 1 (one reviewer): SHIP WITH FIXES, 8 findings.
  - The batch quote is not the last sale for thin funds (high).
  - Replays read the future.
  - A stalled Yahoo history passed the trading guard.
  - The disagreement check was one-sided and unbounded.
  - The key leaked before redaction.
  - Empty answers read as no quotes.
  - One bad row failed a batch.
  - Accounting gaps.
  Addressed by the redesign on FMP minutes; round 2 found two of them back in new forms.
- Round 2 (a four-lens workflow: correctness, data, tests and claims, each serious finding re-checked by
  a refuter): SHIP WITH FIXES / BLOCK on one finding, now fixed.
  - Bars with no volume were read as fresh trades (high, three lenses agreed). Now skipped.
  - The disagreement line flagged ordinary one-minute moves (medium; about 1 run in 8, refuter's
    estimate). Now only a sale inside FMP's minute is compared.
  - FUTURE_SLACK failed both ways (a 15:58:30 replay read the close; a slow live fetch dropped good
    Yahoo prices). Now: replays cut at their time, live runs drop nothing.
  - 29 of the tests lens's 35 mutants survived, including: the last bar by price or arrival rather than
    time, the constants, the ledger record, a swallowed SPY refusal, a stale FMP bar, a missing Yahoo SPY,
    a sale with no time. The behavioural ones now have tests; 11 boundary or equivalent ones survive,
    listed in its log.
  - Lows fixed:
    - a 90 s budget for FMP's calls;
    - an engine caveat for funds short of the previous session;
    - the ledger's Yahoo entry no longer shows a replay's future close;
    - the regenerated replay exhibit;
    - wording (partly; round 3 lists the rest).
  - Fourteen claims were wrong or overstated and are corrected above: "consolidated-tape minutes",
    "replays exact", the ZVOL example, "PEJ no longer stale", the history guard's reach, the pairing and
    tally claims, the monitor's time and the ledger line count.
  - Still open: after an unscheduled closure missing from NYSE_HOLIDAYS, the previous-session guard stops
    the preview, and its message says to add the date. The shadow runner's window check still reads the
    no-volume bars (in the window over 10 sessions: PEJ 32, VOOV 10, CORP 8, LABU 3, QQQE 3, VIXM 3,
    KMLM 2), as its 271-of-272 study did. Whether trades alone fit Composer better is a follow-up for the
    minute study.
  - Mutants of the round-2 code, on a copy: 30 of 30 killed (the first pass's two survivors, a replay
    with FMP off and the siblings' horizon, closed by tests).
- Round 3 (three lenses on the round-2 delta, refuters on the serious ones): SHIP WITH FIXES; nothing
  above low after refutation, and no call in the normal path changes. Applied:
  - live runs cut nothing (a lagging clock or a late sibling fetch no longer drops Yahoo's prices);
  - the live/replay split, whole-minute replays and the budget's return pinned by tests;
  - the CLI exits without waiting for FMP threads past the budget;
  - the SPY-first message names volume; the short-history caveat reads as a sentence;
  - the ledger's `used` says via <sibling> or carried where the price was rebuilt or carried;
  - the record's numbers restated on the shipped read (above), the ZVOL/PEJ examples and the tallies.
  Not done, by choice: pinning each constant's exact value. No fourth round: the changes are one horizon
  rule, wording and tests, each with a paired test.

DECISION: none on symphonies. monitor.py and the 15:15 preview pick it up on their next runs; no
redeploy. Routine prompt: the daily check relays SHADOW FMP DOWN (POLICY lists it).

## Addendum 51 — "Value and Momentum Everywhere" (Asness, Moskowitz, Pedersen 2013) read against this book (2026-11-01)

Owner, 11-01: does the paper (1) improve or change our symphonies, alone or together; (2) argue for a new
symphony; (3) have other uses, e.g. liquidity as a gate; (4) mean we should build a value engine (Buffett,
Graham, the academic papers) for IBKR or Composer. Research only. Exhibit results/vme-2026-11-01.html;
code research/vme/vme_study.py (every number below) and make_vme_chart.py; data in the scratchpad (AQR's
updated VME factors, Ken French, Yahoo monthly ETF closes, FRED TED and VIX, add. 47's daily engine paths).

WHAT THE PAPER SAYS (the parts that bear on us; page numbers are the journal's):
- Value and momentum earn premia in all eight markets, 1972-2011, gross, long-short, monthly rebalanced,
  in the most liquid names (the largest ~17-26% of each market). Value is book/market for stocks and the
  previous month's book/market of the MSCI index for countries; for currencies the 5-year change in
  purchasing-power parity (CPI-adjusted), for commodities the negative 5-year spot return, for bonds the
  5-year change in the 10-year yield. Momentum is the 12-1 month return everywhere (pp. 8-9).
- Table I, global all asset classes: value Sharpe 0.73 (rank-weighted factor 0.72), momentum 0.67
  (0.74), the 50/50 1.42 (1.59). US stocks alone: value 0.29 (0.26), momentum 0.33 (0.45), 50/50 0.63
  (0.86) (pp. 12, 15).
- The engine of the result is a correlation: value and momentum are negatively correlated within and
  across markets (US stocks -0.53 for the sorts, -0.65 for the factors; global -0.53 / -0.60), so each
  alone is modest and the pair is strong (pp. 12, 15, 17, 20).
- Funding-liquidity shocks (TED and like spreads, monthly averages, AR(2) residuals): momentum loads
  positively, value negatively; the 50/50 is immune (Table IV, pp. 30-34). Split at the median of the
  global liquidity-shock index, after 1998: value Sharpe 0.85 when liquidity worsens vs 0.28 when it
  improves; momentum 0.19 vs 0.77 (Table VII, p. 52; the text on p. 51 says 0.99).
- The authors' reading of the sign pattern, momentum as the crowded trade and value the contrarian one,
  is offered as "one simple and intuitive story", not a finding (p. 34).
- Their caveats: gross returns; shorting; long-only versions still earn (Israel and Moskowitz 2012);
  bonds weak on the simple measure; the simplest signals chosen to avoid data mining (pp. 19, 48-50).

SINCE PUBLICATION (AQR's updated factor series, the paper's own construction; the asset-allocation legs
end 2025-01, after which "everywhere" is the stock legs alone, so every everywhere window ends there):
  Sharpe                     paper's dates   2011-08..2025-01   1972-01..2025-01   max drawdown
  value everywhere               0.50             0.00               0.41            -32%
  momentum everywhere            0.63             0.21               0.55            -31%
  50/50                          1.25             0.25               1.05            -12%
  stock-selection value          0.47            -0.16                                -63%
  stock-selection momentum       0.59             0.35
  US stock value                 0.27            -0.29               0.16            -70% (1998-05..2000-02)
  US stock momentum              0.46             0.36               0.44            -53%
  asset-class value              0.32             0.26               0.29            -59%
  asset-class momentum           0.43            -0.09               0.36            -47%
  corr(value, momentum) everywhere -0.59 on the paper's dates, -0.65 since: the diversification held;
  value's premium went to zero, momentum's fell by two-thirds, the 50/50's by four-fifths. (The stock
  legs run to 2026-08: value -0.04, momentum 0.41 since 2011-08.) AQR's everywhere 50/50 gives 1.25 on
  the paper's dates where Table I gives 1.42/1.59; AQR says the update "can differ in data sources and
  methodology". The comparison across time uses one construction throughout.

MEASURED ON OUR BOOK (calendar months 1997-01..2025-12 compounded from add. 47's DAILY engine returns;
the book is a daily 29/29/27/15 constant mix of the engines (the live book drifts between rebalances;
the shape is the same, the level and drawdown are not); prices before each fund's launch are proxies and
the rules were built on 2015-26, so the book's own Sharpe there is in sample. The regressions ask only
what its returns covary with. Newey-West t, 3 lags; plain-OLS t's are larger, the returns have heavy
tails):
1. Factor exposure, excess returns on Mkt-RF + value + momentum everywhere:
     series   beta value [t]  95% CI           beta momentum [t]  95% CI          corr val / mom    R2
     book       -0.41 [-0.8]  [-1.48, +0.66]      -0.25 [-0.7]    [-0.97, +0.47]   -0.05 / -0.05    0.06
     HG         -1.19 [-1.4]  [-2.84, +0.46]      -0.19 [-0.3]    [-1.26, +0.88]   -0.13 /  0.00    0.10
     KMLM       +1.40 [+2.2]  [+0.14, +2.66]      +0.40 [+0.7]    [-0.76, +1.56]   +0.12 / -0.10    0.06
     SLEEVE     -2.14 [-1.3]  [-5.33, +1.05]      -1.31 [-1.7]    [-2.86, +0.24]   -0.15 / +0.03    0.07
     HARV       +0.03 [+0.2]  [-0.27, +0.34]      +0.07 [+0.6]    [-0.18, +0.33]   -0.02 / +0.02    0.01
     controls: SPY market beta 0.95 [119], R2 0.98 (value +0.13 [2.1]); QQQ value -1.36 [-7.1], R2 0.83
   In 2015-25: KMLM value +2.56 [+2.4] (corr +0.21); HG value -2.32 [-1.5], momentum -1.90 [-1.6]; SLEEVE
   value -4.22 [-1.2]; the book value -0.78 [-0.7]. The US HML/UMD version agrees (book: HML -0.27 [-1.1],
   UMD -0.06 [-0.5]). Plain OLS puts SLEEVE's value beta at t -3.7 and the 2015-25 book at -2.1; the
   robust numbers are the honest ones for these tails, but the reading rests on them.
   Meaning: no measurable value or momentum loading in the book, within wide intervals (a correlation
   anywhere between about -0.3 and +0.15 is consistent with the data). One engine shows a loading: KMLM
   co-moves mildly with value everywhere (corr 0.12), stronger in its own years. The paper's hedge (value
   against momentum) has little to hedge here; what a value sleeve offers us is an uncorrelated,
   low-Sharpe addition.
2. Diversification. The factor itself at equal risk (not buyable, a bound): 20% value turns the book
   proxy's 1.52 into 1.53; 50%, 1.24; 20% momentum, 1.59. Buyable long-only value ETFs: correlation with
   the book 0.05-0.12 (IWD, VTV, VLUE, QVAL, IVAL), their own Sharpe 0.3-0.7; 30% VTV (2004-26): 1.66 ->
   1.71, max drawdown -15% -> -14%, CAGR 54% -> 40%; 30% VLUE (2013-26): 2.17 -> 2.25. A long-short proxy
   (IWD - IWF) correlates 0.75 with AQR's US value and -0.10 with the book.
3. Liquidity as a gate. TED shocks as the paper builds them, 1997-2022, excess returns; the shocks are
   skewed, so 89 months count as worsening and 211 as improving; next month's Sharpe, then the same with
   an AR(2) fitted only on past data (no look-ahead), then a level gate (spread above its own 12-month
   mean, 143/157 months); Welch t between the two legs in brackets:
                         worsening / improving        no-look-ahead      level: tight / easy
     book                 1.55 / 1.24  [t 0.7]        1.45 / 1.29  [0.4]    1.35 / 1.33
     HG                   1.16 / 1.15  [-0.2]         1.06 / 1.19           1.01 / 1.28
     KMLM                 1.29 / 0.86  [1.3]          1.21 / 0.91           1.10 / 0.91
     SLEEVE               0.68 / 0.34  [-0.1]         0.61 / 0.36           0.55 / 0.39
     HARV                 0.04 / 0.16  [-0.3]        -0.03 / 0.18          -0.09 / 0.31
     value everywhere     0.56 / 0.03  [1.2]          0.25 / 0.17          -0.37 / 0.57  [-2.4]
     momentum everywhere -0.16 / 0.64  [-1.8]         0.03 / 0.53           0.89 / 0.04  [1.9]
   VIX shocks (145/202 months): book 1.64 / 1.46 [1.0]; HG 1.34 / 1.01; KMLM 1.23 / 1.27; SLEEVE 0.58 /
   0.57; HARV 0.22 / 0.49; value 0.19 / 0.20; momentum 0.23 / 0.60. Contemporaneous betas: every book
   series |t| < 1.8; SPY +2.8.
   Reading: the factors show the paper's signs on the TED shock split, and lose most of it without
   look-ahead. For the book, nothing: the point estimates sit on the side a de-risking gate would hurt
   (the book earns slightly more after liquidity worsens), every difference is inside noise, and the VIX
   and level versions are flat. No evidence a liquidity gate would help; some that it would not.
4. A buyable value-and-momentum symphony. Nine asset-class ETFs (SPY EFA EEM IEF TLT GLD DBC VNQ UUP),
   month-end, long the top 3 by 12-1 momentum and the top 3 by the paper's value signal (worst 60-month
   return), 50/50; nothing tuned; 2012-04..2026-09, 173 months, before costs:
     series           CAGR   vol   Sharpe  max DD   corr book  corr SPY
     momentum sleeve    9%   10%    0.73    -14%      0.07       0.52
     value sleeve       4%   10%    0.30    -18%      0.08       0.56
     50/50              7%    8%    0.64    -10%      0.09       0.66
     equal weight       6%    8%    0.55    -16%      0.08       0.79
     60/40              9%    9%    0.84    -21%      0.12       0.96
     SPY               15%   14%    0.92    -24%      0.10       1.00
   Sensitivity: on one common window (2013-05 on) the value sleeve's Sharpe is 0.12 / 0.16 / 0.28 / 0.15
   / 0.32 for 48 / 54 / 60 / 66 / 72-month lookbacks and the 50/50's 0.47 / 0.48 / 0.56 / 0.48 / 0.58;
   without UUP (not one of the paper's asset classes; it sets the 2012 start) and from 2011-05: value
   0.16, momentum 0.61, 50/50 0.44, SPY 0.87. Momentum alone from 2008-04: 0.56, drawdown -27%. AQR's
   own asset-allocation factors 2012-2024: value 0.29, momentum -0.08. 20% of the 50/50 in the book
   proxy (2012-26: Sharpe 2.19, drawdown -11%): 2.21, -10%, CAGR 82% -> 65%.

ANSWERS:
1. Symphonies, alone or together: nothing to change on this evidence. The book carries no measurable
   value or momentum factor risk; KMLM's mild positive value loading is what a trend-following
   symphony that sometimes stands against crowded momentum looks like, not a defect, and too small to be
   a hedge. The paper's pairing logic does not apply to a book built from short-horizon rules. The
   transferable point is about verification: the book's return is rule alpha, not a documented
   premium, so it has to keep proving itself (the shadow runner, add. 48/50) in a way a factor sleeve
   would not.
2. A new symphony: no. The long-only version earns a Sharpe of 0.4-0.6 across its variants against SPY's
   0.9 and a 60/40's 0.85 in the one period the ETFs allow; its value leg earns 0.1-0.3 (AQR's own
   asset-class value since 2012: 0.29); its momentum leg (0.6-0.75) is a diversified trend sleeve,
   which KMLM already is. Blended at 20% it adds 0.02 of Sharpe and gives up a fifth of the return.
3. Liquidity as a gate: no evidence for one on this book (3 above), and the direction of the point
   estimates argues against de-risking into stress. The paper's liquidity result is about the factors:
   a value sleeve would be, like the book, a stress beneficiary; momentum factors are the ones that need
   protection. HARV's HYG guard is already a credit-stress gate on the one engine where it was shown to
   help. A TED-type shock is worth showing on the dashboard as context, not trading.
4. A value engine: not now, and never a value-only one. The paper is the strongest case against it: US
   stock value alone earned 0.27 gross and long-short in the paper's sample, -0.29 since, with a -70%
   drawdown; value everywhere has earned nothing since 2011; value is the weak leg that momentum rescues.
   "Load up Buffett's writings" is the wrong input: Buffett's record has been decomposed into quality,
   low-beta and value with about 1.6-1.7x leverage (Frazzini, Kabiller, Pedersen, "Buffett's Alpha";
   external, not checked here), and rules distilled from prose cannot be tested. If a stock engine is
   wanted, it is a documented value + momentum + quality composite on a liquid US universe, built from
   the papers' definitions (the owner can supply them), on point-in-time fundamentals, gated and
   shadowed like everything else, and run only through ibkr-executor (Composer reads prices, not
   fundamentals). On the premia above, a long-only sleeve of that kind might earn a Sharpe around 0.5
   before costs (my reading, not a sourced figure); at 20% of this ~$300k book that is a few thousand
   dollars a year of expected edge against a multi-week build. Prerequisite to ask for before any build:
   a point-in-time fundamentals source (FMP's as-reported data needs a survivorship check). Decision:
   park it; revisit if the IBKR executor is live and a stock sleeve is wanted for capacity (add. 15)
   rather than return.

HONESTY BOX:
- The book series is add. 47's reconstruction: rebuilt prices before each fund's launch, the rules' own
  years after 2015, and here a constant-mix proxy of the engines rather than the drifting live book.
- Monthly returns of a 29%-vol proxy against factors of 6-10% vol: the intervals above are the honest
  width; "no measurable loading" is not "no loading".
- AQR's series are not the paper's tables; the across-time comparison is construction-consistent.
- The buyable test is one universe, one rule, one US-equity-led period, long-only, before costs; its
  sleeves carry market beta the paper's factors do not; the lookback sweep shows the value leg's
  number is fragile.
- The liquidity test is predictive (next month), not the paper's contemporaneous regression; TED ends
  2022-01; 89 months in the worsening leg; FRED's HY credit spread was served for 2023-10 on only and
  is left out.
- Yahoo serves monthly bars for the long-range ETF pulls (month-end adjusted closes), as used.

COUNTER-AGENT (one hostile reviewer, scratchpad/review51/): SHOWABLE WITH FIXES; no decision flips. It
re-derived every headline from the raw files (its numbers match the study's to the decimal where the
series are the same) and found:
- The book and engine months were built from add. 47's weekly path, ending up to 7 days before month
  end; rebuilt from the daily returns. KMLM's value loading went from t 1.2 to 2.2; the book's did not
  move.
- "~150 months a leg" was false (89/211); "a gate would remove the months the book earns" and "VIX gives
  the same picture" were not supported; the gate test mixed raw and excess returns; the AR(2) used the
  full sample. All rewritten above, with the counts, Welch t's and the no-look-ahead version.
- The value signal was 59 months, not 60 (value sleeve 0.16 -> 0.30, the 50/50 0.56 -> 0.64); the
  lookback sweep and the no-UUP variant were added.
- AQR's everywhere series is stocks-only after 2025-01; the "since" window now ends there (50/50 0.45 ->
  0.25).
- Overclaims softened ("orthogonal", "no factor risk", "halved"); betas and t's no longer confused; the
  vol-weighting attribution dropped for AQR's own caveat; the country-index and currency value measures,
  the correlation bases and Table VII's 0.77 corrected; the external attributions flagged; the backlog
  entry reworded (the momentum sleeve is not cash-like: 0.52 correlation with SPY, -27% drawdown).
- Confirmed: the Newey-West implementation, the AQR parse (22 columns, 0 mismatches), the Yahoo
  month-end alignment, the exhibit (no overflow, no console errors, legend matches series).

DECISION: none on symphonies; no new symphony; no value engine now. ideas-backlog entry 12 keeps the one
lead (a 12-1 cross-asset momentum sleeve), with its caveats.

---

## Addendum 52 — A long-only value / momentum stock sleeve in IBKR: what it has earned (2026-11-03)

Owner, 11-03: "What about making a momentum vs value sleeve strategy within IBKR, outside of Composer?
What could returns look like? Can we make a better performing strategy than our current IBKR SPY and
Genomics sleeve?" Research only. Exhibit results/vm-ibkr-2026-11-03.html; code research/vme/vm_ibkr.py
(every number below) and make_vm_ibkr_chart.py; data in the scratchpad (Ken French's library CSVs
downloaded 2026-11-03, CRSP vintage 202609; Yahoo monthly adjusted closes). The owner's IBKR genomics
sleeve has NO record in this repo (POLICY.md carries only "IBKR equities ~$346k, owner-reported
2026-07-07"); it is a missing key input and is asked for below, not analyzed around.

WHAT WAS MEASURED
- A. Ken French's long-only portfolios (CRSP/Compustat; survivorship-free; point-in-time; value-weighted;
  monthly; GROSS of costs; through 2026-09). The SLEEVE rows are the big side of the 2x3 sorts: stocks
  above the NYSE size median in the top 30% (NYSE breakpoints) on the prior 12-2 month return
  (momentum, monthly rebalance; 141-308 names since 1963, median 298), on book-to-market (value, June
  rebalance; 80-143 names, median 143) and on operating profitability (quality, June; median 310).
  "BIG V+M" is a monthly-rebalanced 50/50 of the value and momentum rows; "thirds" adds profitability.
  CONCENTRATED rows are the 5x5 corner cells (largest size quintile x top signal quintile): the value
  corner holds 6-31 names (median 23, 9 in 2026-09) and loads ~1.15x on large financials — a bank
  basket, shown as a sensitivity, not as the sleeve (counter-agent). The all-cap top deciles (hundreds of
  names, microcaps included) are kept for the long record; not holdable at this size.
  Costs: an ASSUMED drag — a monthly 12-2 sort keeps a top-30% name with p ~0.8 a month, ~250% one-way
  turnover a year, at 10-20 bps a round trip in mega caps ~0.5%/yr at $150k (more at $50k); the June
  sorts 0.2%/yr. "Net" rows subtract it. Taxes not modeled (Act 60).
- B. The live ETFs that implement the same ideas, NET of fees, as they traded: MTUM / VLUE (2013-), SPMO
  (2016-), QVAL / QMOM (2015 / 2016-), VFMO / VFVA (2018-), VTV / IWD; QQQ / RSP / IWF for contrast;
  ARKG / XBI / IBB / GNOM as genomics CONTEXT only. Each fund from its first full return month.
- Benchmark: the CRSP market (Mkt-RF + RF) for the French rows; SPY for the ETFs. SPY vs the market,
  1993-03..2026-09: 10.81% vs 10.95% CAGR, correlation 0.987 — the same thing. Sharpe on excess returns
  (French RF). "10y" = rolling 120-month excess CAGR vs the benchmark (overlapping): share ahead / worst.
  French's series end 2026-09 and every window stops there; the ETFs' complete October 2026 is reported
  separately (it matters: MTUM and SPMO fell ~10% in it).

RESULTS
1. The long record, 1963-07..2026-09 (759 months), gross unless "net":
     portfolio                 CAGR   vol  Sharpe  maxDD  vs mkt    TE  beta  yrs ahead  10y ahead / worst
     market                   10.9%  15.4%  0.47   -50%
     big momentum (top 30%)   13.4%  16.7%  0.58   -48%   +2.6%   6.6%  1.00   40/62      86% / -1.4%
     big value (top 30%)      13.0%  17.5%  0.54   -62%   +2.2%   8.8%  0.98   34/62      70% / -5.6%
     big profitability        12.1%  15.1%  0.54   -48%   +1.2%   3.7%  0.95   36/62      82% / -2.9%
     BIG V+M 50/50            13.4%  16.0%  0.60   -54%   +2.6%   4.9%  0.99   41/62      77% / -2.5%
       net of assumed costs   13.0%                       +2.2%                 40/62      73% / -2.8%
     thirds (V+M+Q)           13.0%  15.4%  0.59   -50%   +2.2%   3.3%  0.98   48/62      88% / -1.0%
       net                    12.7%                       +1.8%                 46/62      82% / -1.3%
     concentrated 50/50       13.5%  17.1%  0.57   -50%   +2.6%   7.2%  1.01   38/62      83% / -2.9%
     concentrated value cell  12.5%  19.8%  0.48   -62%   +1.7%  12.4%  1.00   32/62      61% / -7.6%
     all-cap momentum decile  17.2%  21.7%  0.65   -51%   +6.4%  12.3%  1.17   41/62      94% / -1.4%
     all-cap value decile     14.4%  21.7%  0.53   -70%   +3.5%  12.7%  1.15   37/62      71% / -11.0%
     the other side: big bottom-30% momentum 7.7% (-3.2%/yr), all-cap bottom momentum decile -0.1%.
   1927-2026: BIG V+M +2.9%/yr (86% of 10y windows ahead), big momentum +3.2% (91%), big value +2.1%
   (76%); drawdowns -77% to -89% in the 1930s, the market's -84%. 1993-2026: market 10.9% / Sharpe
   0.60; BIG V+M 12.3% (+1.3) / 0.65, 47% of 10y windows; thirds 12.4% (+1.5) / 0.69, TE 3.7%, 74%; big
   momentum +1.5%; big value +0.6% (38%); big profitability +1.6% (100%). 2010-2026: market 14.1% /
   0.87 / -25%; BIG V+M 14.4% (+0.3) / 0.82 / -28%, net -0.1%; thirds 14.9% (+0.7) / 0.89 / -24%, net
   +0.4%; big momentum +0.3%; big value -0.3% at Sharpe 0.70 and -38% DD; the concentrated 50/50 +2.0%.
2. By decade, excess CAGR vs the market (gross; the 2020s are 81 months):
                        1930s  1940s  1950s  1960s  1970s  1980s  1990s  2000s  2010s  2020s
     big momentum       +2.9   +3.5   +4.9   +5.8   +4.3   +1.7   +5.1   +0.8   +0.5   +0.2
     big value          -4.3   +6.6   +4.0   +2.4   +6.2   +3.5   -1.5   +3.9   -2.5   +3.0
     big profitability                       +2.1   -0.9   +0.7   +1.7   +2.3   +1.1   +1.9
     BIG V+M 50/50      +0.2   +5.1   +4.6   +4.2   +5.3   +2.8   +1.9   +2.7   -0.9   +2.0
     thirds                                  +3.6   +3.3   +2.1   +1.9   +2.6   -0.2   +2.1
     concentrated value -5.5   +7.2   +1.4   -0.3   +2.7   +5.3   -0.6   +1.7   -4.1  +10.9
   Momentum has not had a losing decade; its edge has faded to +0.2-0.8%/yr since 2000. Value lost
   the 1930s, 1990s and 2010s. The 50/50 lost one decade of ten (the 2010s, -0.9%/yr).
3. The last 21 months carry the modern-era numbers. Excess CAGR, recent windows stopped at 2024-12 vs
   run through 2026-09, and the rally months alone (French rows vs the market, ETFs vs SPY; 2025-01..
   2026-09 is 21 months, annualized):
                     2010..2024-12  2010..2026-09  2016-02..2024-12  2016-02..2026-09  2025-01..2026-09
     market CAGR         13.8%          14.1%           15.3%             15.6%            16.9%
     SPY CAGR            13.8%          14.2%           15.2%             15.6%            17.5%
     big momentum        +0.2%          +0.3%           -0.7%             -0.4%            +1.1%
     big value           -1.9%          -0.3%           -0.9%             +1.5%           +14.8%
     BIG V+M             -0.6%          +0.3%           -0.4%             +0.9%            +8.1%
     thirds              +0.2%          +0.7%           +0.7%             +1.4%            +4.9%
     concentrated value  -2.6%          +1.6%           -0.2%             +6.3%           +46.4%
     MTUM (2013-07-)     +0.3%          +1.7%           -0.9%             +0.9%           +11.1%
     VLUE                -5.0%          -1.1%           -5.2%             -0.3%           +28.7%
     MTUM+VLUE           -2.2%          +0.5%           -2.9%             +0.6%           +20.1%
     SPMO (2016-01-)     +2.6%          +4.4%           +2.5%             +4.3%           +14.1%
     QVAL                -5.7%          -4.8%           -4.3%             -3.5%            +0.8%
   Calendar 2025: concentrated value cell +51.1%, VLUE +32.7%, IWD +15.7%, market +17.5%; 2026 through
   September: +56.3%, +46.6%, +19.1%, +11.9%. Real, not a data problem: the equal-weighted version of
   the cell did +41.8% / +35.6%, VLUE has the same shape (0.83 correlation over the 21 months), French's
   HML +6.6% / +6.7%, and the zips match fresh downloads (counter-agent). Through 2024 the big-cap 50/50
   had lost 0.6%/yr to the market since 2010 and MTUM+VLUE had lagged SPY by 2.2%/yr; the rally put
   them back to about even. The concentrated cell's +46%/yr is 9-13 names at beta 1.8.
4. The buyable versions, net of fees, each from its first full month to 2026-09, vs SPY:
     fund                   window      CAGR    SPY   vs SPY  Sharpe/SPY  maxDD/SPY   TE   beta  yrs ahead
     MTUM                   2013-07-   16.1%  14.4%   +1.7%  0.87/0.84   -30%/-24%  8.9%  0.98   7/12
     VLUE                   2013-07-   13.3%  14.4%   -1.1%  0.70/0.84   -29%/-24%  8.6%  1.08   5/12
     MTUM+VLUE 50/50        2013-07-   14.9%  14.4%   +0.5%  0.84/0.84   -25%/-24%  6.2%  1.03   5/12
     SPMO                   2016-01-   19.3%  14.9%   +4.4%  0.98/0.86   -21%/-24%  9.3%  0.99   6/10
     SPMO+VLUE 50/50        2016-01-   16.9%  14.9%   +2.0%  0.88/0.86   -22%/-24%  6.8%  1.04   4/10
     QVAL                   2015-01-    8.8%  13.7%   -4.8%  0.41/0.78   -42%/-24% 12.5%  1.16   5/11
     QMOM                   2016-03-   12.5%  15.7%   -3.2%  0.55/0.90   -28%/-24% 13.9%  1.12   3/9
     QVAL+QMOM 50/50        2016-03-   12.4%  15.7%   -3.3%  0.58/0.90   -32%/-24% 10.4%  1.16   2/9
     VFMO+VFVA 50/50        2018-04-   13.2%  15.1%   -1.8%  0.56/0.79   -36%/-24% 12.7%  1.12   1/7
     VTV                    2004-04-    9.6%  10.9%   -1.3%  0.59/0.65   -55%/-51%  5.1%  0.93   6/21
     IWD                    2000-08-    8.3%   8.5%   -0.2%  0.49/0.45   -55%/-51%  5.4%  0.94  11/25
     QQQ                    1999-06-   10.9%   8.6%   +2.3%  0.48/0.46   -81%/-51% 13.4%  1.30  16/26
   October 2026 (complete; outside French's window): MTUM -10.5%, SPMO -10.1%, QQQ -6.7%, VLUE -1.8%,
   SPY -0.9%, QVAL +10.6%. With it: MTUM +0.8%/yr vs SPY (was +1.7), SPMO +3.3% (was +4.4), MTUM+VLUE
   +0.0% (was +0.5), SPMO+VLUE +1.5%, QVAL+QMOM -2.7%.
   On one window, 2016-02..2026-09 (SPY 15.6% / 0.90 / -24%): QQQ +5.5%; SPMO +4.3%; MTUM +0.9%;
   MTUM+VLUE +0.6%; VLUE -0.3%; QVAL+QMOM -2.9%; VTV -2.7%; IWD -3.5%; RSP -3.3%. The French rows on
   that window, gross: big momentum -0.4%, big value +1.5%, big profitability +2.0%, BIG V+M +0.9%;
   concentrated value cell +6.3%, concentrated 50/50 +4.0%, all-cap momentum decile +4.2%. Read: the
   momentum funds show NO implementation gap (MTUM +0.9 and SPMO +4.3 against the sort's -0.4); the
   value funds sit between the broad French value row (+1.5) and nothing — definition (sector-neutral,
   multi-metric, diluted index value), not trading cost; QVAL/QMOM and VFMO/VFVA (50-stock and all-cap
   products, 8-10 year records) did lag.
5. SPY with a sleeve bolted on (net rows, monthly rebalanced; CAGR / Sharpe / max DD). 2010-2026: SPY
   14.2% / 0.90 / -24%; 100% BIG V+M 14.0 / 0.80 / -28%; 100% thirds 14.5 / 0.87 / -24%; +20% of either
   leaves SPY's numbers unchanged to the decimal. 1993-2026: SPY 10.8 / 0.61 / -51%; 100% BIG V+M 11.8 /
   0.63 / -54%; 100% thirds 12.1 / 0.67 / -50%. A different way to hold stocks (correlation with the
   market 0.91-0.96; MTUM+VLUE with SPY 0.92), not a diversifier.
6. Genomics, context only: ARKG 2015-01..2026-09 9.0% vs SPY 13.7% (-4.6%/yr), max DD -80% vs -24%,
   TE 30%, beta 1.6; GNOM 2019-06.. 3.9% vs 16.6% (-12.7%/yr), -71% DD; XBI 2006-05.. 12.2% vs 11.0%
   (+1.2%/yr), max DD -57% vs SPY's -51% (both 2007-09), 55% of 10y windows ahead; IBB 2001-05.. 8.1%
   vs 9.3%. On 2016-02..2026-09: ARKG -3.0%/yr, XBI -4.1% (DD -57% vs -24%), IBB -6.9% vs SPY.

ANSWERS
1. What returns could look like. A big-cap long-only value + momentum sleeve (top-30% rows, 140-300
   names each) has earned the market plus 2.6%/yr gross over 63 years (2.2% net of assumed costs),
   beta 1, 5% tracking error, the market's drawdowns (-54% in 2007-09), ahead in 41 of 62 calendar
   years and 77% of ten-year windows, worst decade -2.5%/yr. Since 2010 it has earned the market plus
   0.3%/yr gross, -0.1% net, and that is WITH the 2025-26 rally (-0.6%/yr through 2024). The thirds
   version with profitability is the tamer shape: TE 3.3%, 88% of ten-year windows ahead, worst
   -1.0%/yr, +0.7%/yr since 2010. Momentum alone: +2.6%/yr long run, 86% of windows, but +0.2-0.8%/yr
   per decade since 2000. The forward reading (mine, from these records, not a forecast): market +0 to
   +2%/yr for a diversified sleeve, with ten-year stretches behind; the +4-6%/yr numbers belong to a
   9-30 stock bank basket and to the last 21 months. The live funds: MTUM+VLUE +0.5%/yr over SPY since
   2013 (+0.0 with October 2026; -2.2%/yr through 2024), SPMO +4.4% (+3.3 with October; one fund, one
   mega-cap-led decade), QVAL+QMOM -3.3%, VFMO+VFVA -1.8%.
2. Better than SPY in IBKR? Over long horizons, probably, by 1-2%/yr gross at the same risk, with
   multi-year lags; over the last 16 years, no — the sleeve matched the market (+0.3%/yr) and its Sharpe
   was lower (0.82 vs 0.87; thirds 0.89). It replaces SPY; it does not diversify it, and it adds nothing
   to the Composer book (add. 51: the book has no value or momentum loading to hedge).
3. Better than the genomics sleeve? Unknown until the sleeve's record is in hand — see MISSING INPUT.
   If that sleeve behaves like its ETF proxies (ARKG -4.6%/yr vs SPY with a -80% drawdown, GNOM
   -12.7%/yr, XBI -4.1%/yr since 2016 with a -57% drawdown), SPY alone dominates it, and so does any
   value/momentum sleeve.
4. How it would be built, if wanted. (a) ETF pair, zero build: SPMO (or MTUM) + VLUE in IBKR, 50/50,
   rebalanced quarterly; SPMO+VLUE earned 16.9% vs SPY 14.9% since 2016 (+2.0%/yr; +1.5 with October
   2026; Sharpe 0.88 vs 0.86; -22% DD); the realized, net-of-fee version, two tickers. (b) Stock sleeve,
   the French construction: top-30% 12-2 momentum among large caps rebalanced monthly (~300 names, or a
   100-name cut) plus top-30% book-to-market (or a value composite) rebalanced annually, equal halves;
   needs point-in-time fundamentals (FMP's as-reported statements with a survivorship check, the
   prerequisite add. 51 set), a keyless engine emitting intents to ibkr-executor (DRY_RUN, paper first),
   and a shadow runner; weeks of build. Its measured edge over (a): momentum none; value +1.5 vs -0.3
   on 2016-26, gross, from a definition the funds do not use. Recommendation: if the exposure is
   wanted, hold (a) in IBKR and measure it against SPY; build (b) only for a reason beyond return
   (capacity, tax lots, owning the rules). On the evidence, neither is a return engine: the honest
   expectation is SPY-like with a tilt.

MISSING INPUT (ask, do not analyze around): the IBKR genomics sleeve — holdings or rules, start date,
dollar size, and its return to date (or a statement export). Without it question 3 has no answer. The
SPY half of the IBKR account needs nothing: SPY is the benchmark here.

HONESTY BOX
- French rows are gross, value-weighted within each cell, rebalanced monthly (momentum) or each June
  (value, profitability); the net rows subtract an assumed drag, not a measured one; taxes are not
  modeled. The all-cap deciles and the 5x5 corner cells are not what a sleeve would hold; the sleeve
  numbers are the 2x3 rows, and the 2x3 value row is still 80-143 names, value-weighted.
- Rolling 10-year shares count overlapping windows (640 since 1963); 62 years hold six independent
  decades. Calendar-year counts are the independent tally.
- The 2025-26 value rally (21 months) moves every recent window: section 3 is the sensitivity and
  should be read before any modern-era number. French's 2026-09 cut discards October 2026, a -10%
  month for the momentum funds; section 4 carries it.
- ETF records are short (7-13 years), one US-equity-led regime, and the funds implement different
  definitions from the sorts. Yahoo monthly adjusted closes, month-end, dividends included, first return
  month dropped.
- No look-ahead in the French construction (June formation on prior-December size and prior-fiscal-year
  book; momentum skips the last month); no survivorship (CRSP carries delisting returns). Nothing here
  is a forecast.

COUNTER-AGENT (one hostile reviewer, scratchpad/review52/): SHOWABLE WITH FIXES, all applied. It
re-derived every number in the JSON, console and exhibit from the raw zips and Yahoo file with its own
parser and stats (agreement to the third decimal; no parse, alignment, unit or timestamp bug; Yahoo
month-ends verified against daily closes, dividends present, no lag vs CRSP; zips match fresh
downloads) and found:
- MAJOR: the first draft's "big value" row was the 5x5 corner cell — 6-31 names, ~1.15x large
  financials (industry regression R² 0.87-0.94) — presented as "the names an IBKR sleeve would trade";
  that one fact produced the draft's +6.3%/yr-vs-SPY value row and its "implementation gap". Fixed: the
  2x3 rows (80-308 names) are now the sleeve; the corner cells are labelled concentrated and carry their
  firm counts; every headline number above is on the 2x3 rows.
- MAJOR: the draft's claim that "the academic sorts beat SPY where the funds lagged" was wrong for
  momentum (MTUM +0.9 / SPMO +4.3 vs the sort's +0.6, now -0.4 on the 2x3 row) and mis-attributed for
  value (definition, not cost). Rewritten (result 4).
- MAJOR: the since-2010 edge is the last 21 months; the KPIs and answers now say so, with the
  through-2024 numbers beside them.
- MAJOR: "XBI matched SPY with double its drawdown" mixed two windows; corrected (result 6).
- MINOR: momentum turnover is ~250% one-way a year, not "~100%+" (cost text rewritten; 0.5%/yr fair at
  $150k, light at $50k); the rally table's 21-month column is labelled and SPY's CAGR added; the
  October 2026 month is reported; partial decades carry their month counts; IVAL/IMOM and the ETF
  "10y windows" column dropped; phone view scrolls to the recent end; "-0%" tick; wording nits.
- Beta: 1.0 on average, 1.06 since 2010, 1.08 in the rally months for the 50/50; 1.8 for the
  concentrated value cell and 1.4 for VLUE in those months.

DECISION: research only; nothing traded, no engine built. Backlog item 13 records the two versions and
the prerequisite. Awaiting the owner's genomics sleeve record for question 3.

---

## Addendum 53 — Overnight / pre-open overlays on the engines' leveraged legs, and the edge on the other side (2026-11-05)

Owner, 11-05, after KMLM's SOXL buy at the 11-04 close opened -14.6% and fell another 15% by 11:30
("TA on futures was off a cliff"): "what if we had all our same logic + this new futures overnight
logic on IBKR — could we have caught this move properly? ... see if there are overnight indicators like
semis etc. or others, run large study, to see if there are a series or individual ones we can run;
think second order; trying to see if it makes sense to switch all this logic over on IBKR." Then: "i
thought you said the indicator shows mid day bounce tho? we are looking for any edge/alpha, if you run
into edge in any study, that isn't directly the original prompt, still bring it to my attention."
Research only. Exhibit results/overnight-2026-11-05.html; code research/overnight/ (overnight_study.py:
the engine-path harness; dipbuy_events.py: the panel; edge_study.py: the other side;
make_overnight_chart.py); data in the scratchpad (overnight/daily.json, premarket_bridge.json; the add.
47 pipeline re-run for the engine paths, long1997/engines_ts_synth.json). The "edge is the point"
instruction is now a standing convention in CLAUDE.md (mirrors regenerated).

WHAT WAS MEASURED
- The engines' 15:50 decisions are left as they are. The overlay acts BETWEEN decisions: on the
  morning after a leveraged entry it reads what is known before 09:30 — the fund's own pre-open gap,
  the sector ETF's gap (SMH/XLK/QQQ/SPY/IWM/XBI), the mean of the Nikkei, Kospi and Taiwan closes that
  day (all before 04:00 ET; Korea+Taiwan as "Asia semis"), the DAX open (03:00 ET) vs its prior close,
  VIX's prior close, its change on the prior session, VIX vs VIX3M, and the prior session's own move
  ("entry day") — and EXITS at the 09:30 open (cash until the next 15:50 decision), or FLIPS into the
  inverse fund for the session. The mirror for the short legs (SQQQ mornings) on overnight rallies.
  Plus a flip BREAKER (after N long<->short changes in M sessions, cash for K sessions). Thresholds
  swept; AND combinations; the mirrored ("INVERSE") signals as controls; 2,000-draw placebos of the
  same number of random same-side mornings. 47 exit rules per engine, 11 flip variants, 10 short-leg
  rules, 5 breakers.
- Test bed: the KMLM switcher's and HG's daily paths from the add. 47 pipeline (live trees, Composer-
  equivalent costs; KMLM's dominant leg matches Composer's ledger on 59 of 64 sessions since 2026-08-01,
  the misses being two knife-edge days and three Composer no-rebalance days), 2015-06-01..2026-11-04,
  overlays on the real funds' raw opens and closes; costs 15 bps at the open and 10 bps when the engine
  re-holds the fund at the next close (conservative by 3-5x for $60-90k MOO/MOC orders; signs hold
  gross).
- Panel: every morning after SOXL, TECL, TQQQ, SPXL or LABU closed with Wilder RSI(10) < 30 (the
  engines' dip-buy trigger), from each fund's launch: 893 mornings on 416 distinct days (180 of them are
  KMLM long mornings: path-free, not independent of the engine).
- Data limits: no historical 04:00-08:00 prints exist in our sources (FMP's 1-minute bars are
  09:30-15:59; Yahoo keeps 60 days of pre-market), so the exit print is the open; a 60-day bridge
  measures the pre-market prints against it. Index futures intraday history: 60 days only.

RESULTS
1. The night of 11-04 -> 11-05, as % of the 16:00 close: ES -0.3% at midnight, -0.2% at 09:25; NQ -1.1%
   / -1.3%; SPY -0.1% at 09:25; Asia's closes -3.4% (Nikkei -1.8, Kospi -5.3, Taiwan -3.2); DAX open
   +0.1%; VIX prior close 16.6. SMH pre-market -2.5% at 04:00, -4.5% at 09:25; SOXL pre-market -8.7% at
   04:00, -13.3% at 09:25, open -14.6%, -35% at the 11:00 low. Index futures were flat; the warning was
   semis pre-market and Asia; most of the damage was the regular session (SPY -3.6% by 11:00).
2. Panel, 893 dip-buy mornings (pooled; "up" = open-to-close positive):
     signal before 09:30             n    open->close   up        signal                 n    open->close   up
     all mornings                  893      +0.88%     55%       Asia <= -1%            322     +1.67%     55%
     fund gap <= -2%               161      +3.15%     64%       Asia <= -2%            149     +3.45%     60%
     fund gap <= -5%                72      +4.49%     64%       DAX open <= -1%        151     +2.76%     58%
     fund gap <= -8%                38      +6.17%     66%       DAX open <= -2%         44    +11.56%     86%
     fund gap <= -10%               23      +5.83%     65%       VIX > 30               247     +2.14%     56%
     sector gap <= -2%              87      +4.78%     69%       VIX > 40                97     +3.48%     66%
     sector gap <= -3%              54      +5.62%     69%       prior session <= -10%  166     +2.05%     57%
   By decile of the fund's gap: the worst decile (mean gap -8.8%) -> +4.72% open-to-close, 70% up (t
   4.2; +5.2% without 2020); deciles 2-9 are flat (-0.3% to +1.2%): a tail effect, not a gradient. It is
   conditional on the oversold close: unconditionally, SOXL gap-downs of 5%+ since 2015 (n 197) show no
   rebound (mean -0.01%, median -0.5%, 46% up); SPXL shows none even in the panel (n 12, -1.6%).
   Correlation of each pre-open signal with the subsequent open-to-close move: fund gap -0.14, sector gap
   -0.14, Asia -0.16, DAX open -0.17, VIX +0.15, prior session -0.11. Per fund, gap <= -5%: SOXL n18
   +5.7%, TECL n11 +6.3%, TQQQ n11 +4.9%, LABU n20 +5.9%, SPXL n12 -1.6%. The eight prior SOXL gap-downs of
   10%+ averaged +8.4% open-to-close; 11-05's -15% open-to-close is the worst in the panel's bottom decile
   (1 of 89 at -15% or worse; the worst engine fire -11.8%).
3. The rules on KMLM's own path (as built 2015-06..2026-11-04: CAGR 193.8%, Sharpe 2.16, max DD -54.4%,
   in sample; 2,187 leveraged-long mornings: SOXL 1,144, TECL 1,004, SPXL 21, LABU 18; long legs' mean
   gap +0.33%, mean open-to-close +0.39%; after a 5%+ gap-down, n100, +1.52%, median +1.61%). Exit at
   the open; dCAGR in points off 194; "t" is the per-fire t-statistic of the engine's gain from exiting:
     rule                           fires  helped  per fire    t     dCAGR    dSharpe  dMaxDD   placebo pct (p05..p95)
     fund gap <= -2%                 362    42%    -0.48%   -3.7   -39.2pp   -0.23    -1.5pp    3%  (-36.8..-8.4)
     fund gap <= -5%                 100    44%    -0.98%   -2.8   -23.7     -0.14    +0.6      0%  (-14.8..+1.2)
     fund gap <= -8%                  36    56%    -1.25%          -10.8     -0.06    +0.6      0%  (-7.2..+2.4)
     fund gap <= -10%                 25    64%    -1.13%   -1.0    -6.6     -0.03    -0.9      3%  (-5.8..+2.2)
     sector gap <= -1% / -2%     206 / 67  43/52%  -0.6/-1.0      -28.5 / -15.2                   1% / 1%
     Asia <= -1% / -2%           226 / 74  38/42%  -0.8/-1.5 -3.3 -40.1 / -24.8  -0.21  -10.3     0% / 0%
     Asia semis <= -1% / -2%     208 / 73  39/34%                 -34.8 / -28.4                   0% / 0%
     DAX open <= -1% / -2%       111 / 25  40/28%  -1.2/-3.8      -29.7 / -22.6                   0% / 0%
     VIX > 20 / 25 / 30      611/294/104  42-44%                 -70.8 / -41.4 / -29.3  -11.8..-13.2   0%
     VIX backwardation               153    41%    -0.90%         -29.0     -0.10   -12.2        0%
     prior session <= -5% / -8% / -10%  256/109/67  39-43%      -55.0 / -27.8 / -23.3  -13..-15   0%
     combos (gap&Asia, gap&sector, Asia&DAX, gap&VIX, crash&gap)   17-96  29-45%   -12.4 .. -22.9      0%
     INVERSE gap >= +2% / +5%    500 / 124  41/42%                -36.7 / -4.5                    26% / 73%
     INVERSE Asia >= +1%             255    42%                   -14.9                           54%
     INVERSE Asia >= +2% / +3%    47 / 22  43/59%          +0.4/+1.3  +3.4 / +6.9                97% / 100%
     INVERSE gap >= +8% / +10%    36 / 22  42/36%          +0.0/-0.1  +1.6 / +0.4                92% / 80%
   43 of 47 exit rules cost CAGR; the four that did not are mirrored "good overnight" signals, t <= 1.3
   (the +6.9pp is 60% one fire, 2020-03-20 SOXL; without it +0.44% per fire). 6 of 47 raised Sharpe (the
   same mirrors); 12 improved the max drawdown by 0.1-0.7pp; the "bad news" rules sit at the 0-3rd
   placebo percentile (sector gap <= -0.5% at the 18th). Flip into the inverse fund instead of cash:
   gap <= -2% -71.4pp, <= -5% -46.1 (Sharpe -0.33), <= -10% -15.3; every combination -24.9 to -44.7.
   Short legs (416 SQQQ mornings), exit at the open on an overnight rally: short fund gap <= -2% n90
   -7.1pp (57th pct); <= -3% n42, 60% helped, +1.6pp, +0.01 Sharpe, t +0.2 (88th pct); Asia >= +1% n68
   -4.0. Breaker (long<->short changes): 2 in 3 -> cash 3: 55 trips, 163 cash days, -18.9pp; cash 5:
   -42.3; 3 in 5 -> cash 5: 22 trips, 105 days, -21.0 (-0.10 Sharpe); cash 10: -36.6; 4 in 10 -> 10:
   -23.3 (counting every change of state: 114 trips, -50.9).
   Reading: random same-count exits already cost (-6.6pp at 100 fires, because the legs earn intraday on
   average); of fund gap <= -5%'s -23.7, -6.6 is "any 100 exits" and -17.1 is selection — the rule
   picks the mornings on which exiting hurts most. Gross of costs it is -0.89% per fire, -21.3pp, and
   would need a +197 bps rebate per fire to break even. Sub-windows: the sign is negative in 2015-19,
   2020-26, 2015-18, 2019-22 and 2023-26 on both engines for the seven key rules (per fire -0.95% /
   -0.99% / -0.51% in 2015-19 / 2020-26 / 2023-26; in 2023-26 the gap rules sit inside the placebo band,
   i.e. no worse than random); leave-one-year-out never flips a sign (worst -12.2pp without 2022). The
   day after a 5%+ gap-down the engine averaged +0.83% (median +1.29%); exiting at that close instead
   costs -16.9pp. Drawdowns deepen under the Asia, VIX and crash rules (-9 to -15pp) because the bounce
   days are inside the drawdown episodes.
4. HG's legs (as built 86.1% / 1.62 / -35.9%; 1,909 long mornings: TQQQ 716, UDOW 452, TNA 320, SSO 278,
   others 143; after a 5%+ gap-down, n17, +4.03%): fund gap <= -2% n122, 39% helped, t -2.7, -19.8pp, DD
   -5.2pp; <= -5% n17, 29%, t -2.5, -10.6 (half of it three 2016 fires; -5.5 without 2016), DD -7.2pp (one
   fire: 2016-01-20 LABU, +21.8% intraday); sector gap <= -1% n67 -22.9, DD -11.2; Asia <= -1% n187
   -24.8; <= -2% n45 -15.5; DAX <= -1% n75 -24.3, DD -10.7; VIX > 25 n149 -17.6; > 30 n53 -14.9, DD -7.5;
   prior session <= -8% n33, 24% helped, -13.6; combos -6.6 to -12.4; flips -20.8 to -36.6 with DD -15 to
   -22pp. 44 of 47 cost CAGR; the three that did not: INVERSE gap >= +3% +0.8 (n83, t -0.1), >= +8%
   +1.7 (n7), >= +10% +2.6 (n3). Same signs in every row that has a sample.
5. Flip rate (long<->short changes, the breaker's definition). KMLM, 2015-26 path, per 25 sessions: mean
   1.7, p90 4, p99 8, max 11, 0.7% of windows at 10 or more (196 changes in 2,876 sessions). Live,
   last 25 sessions to 11-04: 8 (10 counting moves into the vol/bond legs, against the path's any-change
   mean 5.7, p90 9, p99 12, max 13). The path itself has 7 long<->short changes in the same window, the
   ledger 7, and the direction agrees on 24 of 25 sessions (the miss is 10-27, a Composer no-rebalance
   day): the run is the rules meeting a daily-reversal tape, not a Composer defect, and it sits at the
   top of the rules' own range. The breakers that would have sat it out cost 19-51pp a year because the
   flip-heavy regimes are where the engine earns.
6. Pre-market vs the open (60 sessions of 5-minute prints): the 09:25 print is the open to within 0.1%
   (SOXL sd 0.11%, TECL 0.12%, TQQQ 0.02%); the 08:00 print sits within 3.2% / 2.0% / 1.3% (sd) of the
   open and shows 72% (mean; median 79%) / 77% / 82% of gap-downs of 4%+ (15 / 8 / 3 cases). An
   04:00-08:00 exit would have sold a little higher than the open on the big gap-downs and lower on
   the rest; nothing in it changes the sign of 3-4. A live layer must use ADJUSTED prior closes: on raw
   closes every December distribution fires the gap rules (TECL 2025-12-10 -6.5% phantom gap; FAS, SOXL,
   SPXL likewise in other years).
7. THE OTHER SIDE — the morning bounce as an edge (edge_study.py; counter-agent review53b applied:
   sample-sd t, a family-wise permutation test over the 13 "bad overnight" rules, the mean without the
   best three trades, the rule on seven leveraged funds it was not found on, the own-state
   intersection, and a capped, placebo-tested E2). E1, a standalone trade: on a morning when a 3x fund
   closed with RSI(10) < 30 and the signal fires before 09:30, buy the fund at the 09:30 open, sell at
   the 16:00 close; one trade per day, qualifying funds equal-weighted; 30 bps round trip; 2008-2026
   (893 oversold mornings on 416 days):
     rule                                    days  /yr    mean   median   win    t   w/o best 3 (t)  total  worst run  p_fw  Bonf x16  worst trades
     fund gap <= -3%                           65  3.6   +2.01%  +2.85%   60%  1.6   +0.93% (0.8)   +161%    -36%     0.45   1.00    2022-05-09 -21, 2015-09-28 -20
     fund gap <= -5%                           40  2.2   +3.63%  +5.27%   65%  2.0   +1.94% (1.2)   +230%    -23%     0.32   0.66    2022-05-09 -21, 2020-03-16 -13
     fund gap <= -8%                           16  1.0   +4.69%  +7.72%   62%  1.5   +1.14% (0.4)    +88%    -23%     0.52   1.00
     sector gap <= -1% / -2%              66 / 32  3.7/1.8  +2.29 / +6.28%   59/72%  1.9/3.1  +1.23 (1.1) / +4.34 (2.3)  +226/+484%  -36/-23%  0.30/0.04  1.00/0.03
     gap <= -5% AND sector gap <= -2%          31  1.7   +5.96%  +6.76%   71%  2.9   +3.93% (2.1)   +403%    -23%     0.07   0.06
     DAX open <= -1% / -2%                59 / 14  3.5/0.9  +1.69 / +8.59%   54/79%  1.6/2.6  +0.50 (0.6) / +4.41 (1.5)  +124/+191%  -23%  0.44/0.07  1.00/0.16
     Asia <= -1% / -2%                  130 / 54  6.8/3.0  +0.75 / +2.01%   52/56%  1.2/1.6  +0.18 (0.3) / +0.68 (0.6)   +91/+136%  -45/-26%  0.67/0.44  1.00
     VIX > 30                                  88  4.6   +1.24%  +0.57%   53%  1.3   +0.39% (0.4)   +106%    -37%     0.62   1.00
     gap <= -5% OR DAX <= -2%                  44  2.4   +4.06%  +5.87%   66%  2.4   +2.39% (1.6)   +346%    -23%     0.16   0.29
     gap <= -3% AND (Asia <= -1% OR DAX <= -1%) 39  2.2   +3.25%  +3.32%   62%  1.9   +1.63% (1.1)   +184%    -23%     0.27   0.91
     any oversold morning (the base rate)     416 21.9   +0.29%  +0.12%   51%  0.9   +0.10% (0.3)    +43%    -51%
     MIRROR: fund gap >= +5%                   59  3.1   +0.62%  +0.82%   59%  0.7   +0.04% (0.1)    +25%    -34%
     MIRROR: DAX open >= +1%                   42  2.5   +0.25%  +0.86%   60%  0.2   -1.02% (-0.9)    -5%    -29%
   p_fw: the share of 4,000 shuffles of the day returns in which the best of the 13 rules reaches the
   rule's observed t (null max t: median 1.47, 95th pct 2.69 — the best of 13 overlapping rules reaches
   t 2.7 by chance one time in twenty). The one rule that survives family-wise, sector gap <= -2%, is
   the primary rule's 40 days minus 9 losing ones plus one (31 of 32 overlap): an in-sample refinement,
   not a second signal. Splits of the primary rule: LABU-only days 11, +4.96% (t 1.1); days without
   LABU 20, +2.64% (t 1.2); tech rows only (SOXL/TECL/TQQQ) 24, +4.56% (t 2.4). Year by year: 2009 n2
   -7.4%, 2010 n3 +5.9, 2011 n2 -8.5, 2014 n2 +5.7, 2015 n3 +13.5, 2016 n6 +2.2, 2018 n2 +3.6, 2019 n2
   -1.6, 2020 n5 -2.4, 2021 n1 +15.1, 2022 n6 +6.4, 2024 n1 +18.3, 2025 n3 +9.8, 2026 n2 +0.6; none in
   four of eighteen years. Excluding 2020-03: +4.41% (t 2.4); excluding 2025-04: +3.13% (t 1.8); the
   best three trades (2025-04-09 LABU +29%, 2015-10-02 LABU +24%, 2022-10-13 +20%) carry half the mean.
   The mirrors show nothing. Costs: t falls to 2.0 at 37 bps round trip; break-even 393 bps; TECL and
   LABU trade $100-130M a day, so 50-80 bps on a -10% open is the fairer assumption for them.
   Intersection (SOXL/TECL/TQQQ, one trade per day, 2010-26): gap <= -5% with no RSI condition n245
   -0.30% (t -0.7, 46% up); AND own RSI < 30 (the E1 trade) n24 +4.56% (t +2.4, 67%); own RSI >= 30
   n231 -0.64% (t -1.6); own RSI >= 30 but another fund oversold n23 +1.96% (t 1.1); no fund oversold
   n208 -0.92% (t -2.5); own RSI < 30 with a gap > -5% n264 +0.48% (t 1.4); own RSI < 30 and -5% < gap
   <= -3% n22 +2.13% (t 1.6). The condition is the fund's OWN oversold close AND its OWN gap.
   Out of sample, the seven leveraged funds the hypothesis was not built on (own RSI < 30, own gap <=
   -5%, 2008-26): all seven pooled n43 +0.28% (t 0.2, 58% up; -0.93% without the best three); TNA+FAS,
   the sector-distinct pair, n32 -2.21% (t -1.1; TNA alone -3.02%, FAS -1.94%); UDOW / UPRO / SSO +0.1 /
   +0.8 / +1.3% (t <= 0.6); QLD+USD, the 2x copies of TQQQ and SOXL on the same dates, n14 +5.36% (t
   2.7). The sector-gap variant pooled: -0.02% (t 0.0). The effect transfers only to the funds that
   are the same bet on the same dates: a tech/semis-on-these-dates result, not a property of leveraged
   funds after an oversold gap-down.
   The engine already held a leveraged leg on 27 of the primary rule's 31 days since 2015-06 (0.75 on
   most): the standalone trade would have 1.3-2x'd the book's exposure on its worst mornings; on the
   4 mornings it was not long the trade did -11.2%, +15.1%, -20.8%, -7.7%.
   E2, inside the KMLM engine (top the leveraged exposure up to 100% of the symphony at the open when
   the signal fires, capped at 1 - the day's total leveraged weight, sell the extra at the close;
   placebo = random long mornings, same count, 300 draws): fund gap <= -5%: 86 days (23% of them
   oversold mornings), +2.2pp, Sharpe -0.03, max DD -7.1pp, 76th placebo percentile (band -9.1..+5.8);
   gap <= -8%: 33 days, -3.6pp (12th); sector gap <= -2%: 61, -3.3 (27th); gap AND sector: 59, -2.1
   (38th); VIX > 30: 104, -1.2 (44th); DAX open <= -1%: 96 (33% oversold), +7.9, -0.01, DD -3.9pp, 97th
   (band -8.6..+6.7); DAX <= -2%: 23 (43%), +7.7, +0.01, DD -2.1pp, 100th (band -4.6..+3.4); Asia <=
   -1%: 188 (36%), +9.7, -0.02, DD -3.5pp, 95th; Asia <= -2%: 63, +5.1, 92nd; gap OR DAX: 96, +6.5,
   -0.03, DD -7.1pp, 95th. Worst extra day -7.6% (2025-04-10) / -7.1% (2020-03-16). The engine's long
   legs are mostly not fresh dip-buys (16-49% of the fired days), so E2 is largely a different trade
   from E1; the gap-based top-ups sit inside the random band; the DAX/Asia top-ups sit at the 95-100th
   percentile on 23-188 mornings, every one with a deeper max drawdown and no Sharpe gain — more of
   the engine's own mechanism, with the tail that comes with it.
8. Second order, for the IBKR question:
   - Execution: Composer's measured fills 2.9 bps a side (add. 14b); IBKR modeled ~$1.3k/yr worse at
     $250k; closed by measurement. Decision time: the logic at 15:54 contradicts Composer on 1 of 272
     sessions (add. 50), so a 15:59 decision buys nothing. Overnight / pre-market action: this addendum —
     every "bad news" rule subtracts. Futures as the instrument instead of 3x ETFs: a different strategy
     (no daily reset, different path dependence), untested, not an overlay. Operational: ibkr-executor
     is OFFLINE with one strategy (the El Nino ladder); a Composer-equivalent runner for four trees, the
     corridor logic and the RSI semantics, with its own shadowing, is weeks of work and a new failure
     surface (gateway, order handling) in exchange for nothing measured. The backlog's migration gate
     ($500-750k, thin-name fills) is unchanged.
   - What a day like 11-05 is about: KMLM put 75% of the symphony (29% of the book) in one 3x sector
     fund, 2.25x semis notional on ~22% of the book; the -27% SOXL day took -20% off the symphony,
     -6.5% off the book, with the other three engines flat. That is a sizing question — the KMLM
     weight (Op 3's earn-back read on 11-09) or the leg size inside the symphony (add. 42 item 9: a
     long-leg vol gate cut DD 55 -> 45-48 for -11pp CAGR, in sample) — not a venue question (inference,
     not tested here). And the exit that looks obvious this morning has been the losing trade on 56% of
     the engine's own gap-down mornings and 64% of the panel's.

ANSWERS
1. Overnight indicators (semis, Asia, Europe, VIX, the fund's own pre-open print): all of them carried
   information, and all of it pointed the wrong way for an exit — after an oversold close, a bad
   overnight predicted a better session, not a worse one. Individually and in series, 43 of 47 exit
   rules lowered CAGR on KMLM (44 of 47 on HG), by 7-71pp off 194 (2-32pp off 86), with per-fire t of
   -2.5 to -3.7 on the main rules; flips were worse; breakers worse still. The four exceptions are
   mirrored "good overnight" signals with t <= 1.3; the short-leg rally exit is +1.6pp at t +0.2.
2. Could IBKR have "caught" 11-05? A pre-market stop on the position would have sold SOXL at -9 to -13%
   instead of riding to -27%: ~$10k on the day. The same stop, applied every time it fired since 2015,
   would have cost 11-24pp of CAGR a year on KMLM (break-even needs a +197 bps rebate per fire) and
   deepened its drawdowns. Index futures carried no signal at all (ES -0.2% at the open).
3. Switch the logic to IBKR? No, on this evidence: the overnight capability subtracts, the fill and
   decision-time cases were closed earlier, and the operational cost is real. Reopen only with a
   mechanism that is not "de-risk the stress state" — the house rule (ideas-backlog, settled questions)
   holds a tenth time.
4. The edge (owner's follow-up): what survives review is an in-sample conditional mean on three tech
   3x funds plus LABU — after an oversold close, a 5%+ gap-down bounced +3.6% open-to-close on 40 days
   in 18 years (+1.9% without the best three trades), nominal t 2.0, family-wise p 0.32 across the 13
   rules tried; the same rule on seven other leveraged funds returns +0.3% (TNA/FAS negative); the
   best variant (sector gap <= -2%, t 3.1, family-wise p 0.04) is the same 40 days minus 9 losing ones.
   It needs the fund's own oversold close and its own gap (gap-downs without the oversold close: -0.6%,
   t -1.6), which is why the engines already capture most of it by holding through the session — the
   engine was long on 27 of the 31 qualifying days. Inside the engine the gap-based top-up is inside the
   random band; the DAX/Asia top-ups add 5-10 points of CAGR at the 95-100th placebo percentile with a
   2-4 point deeper drawdown and no Sharpe gain. Verdict: a tech-gap-after-oversold-close anomaly
   worth logging, not an edge to trade. If logged: one pre-registered rule (own gap <= -5% after an own
   RSI(10) < 30 close on SOXL/TECL/TQQQ; LABU separately), the 09:25 indicative and the auction prints,
   as an execution record — 2-3 trades a year cannot validate it (38 trades at the in-sample mean for
   t 2). The first message to the owner on this ("t 2-3", "+4 to +11 points inside KMLM") overstated
   it; this paragraph is the corrected statement.

HONESTY BOX
- The 2015-26 KMLM path is in sample (the rules were built on these years) and runs on proxies before
  each fund's launch; the overlay results are differences against that path, on the real funds' prices
  from launch, so the in-sample level does not favour "hold" by construction — but a 194%/yr base
  magnifies every delta in CAGR points, and any exit costs about -0.07pp per fire mechanically; read the
  per-fire t and the placebo columns alongside.
- The exit print is the 09:30 open; a pre-market exit (04:00-08:00) is not testable beyond 60 days. No
  intraday stops (09:30-15:50) were tested: no history.
- Costs assumed (15 + 10 bps; 30 bps round trip for E1); the signs hold before costs. Yahoo raw opens
  for leveraged ETFs; ex-dividend days differ from the engine's adjusted returns by the dividend (one
  phantom gap among 100 fires).
- Asia/Europe stamps are local session dates (Yahoo); VIX is the prior close; no look-ahead in the
  signals. The placebo draws from the same side's mornings. The panel conditions on the engines' own
  trigger, so it is not independent evidence about the engines.
- The edge numbers: 40 trades, 13 rules in the family (16 tested), the family-wise p and the
  without-best-three mean are the honest statistics; LABU supplies the best and the worst trades; the
  seven-fund out-of-sample test is the one that fails.
- The direction-change count treats cash/vol legs as neutral (HG has no counted flips; the any-change
  figures are given beside it).

COUNTER-AGENT, main study (one hostile reviewer, scratchpad/review53/): SHOWABLE WITH FIXES, all
applied. Every headline number re-derived to the digit from the raw files (alignment, look-ahead, window,
placebo side, Wilder RSI, breaker counting, costs, data stamps all verified); it added the sub-window,
leave-one-year-out, gross-of-cost, day-after and unconditional-gap tests reported above. Its findings:
- MAJOR: the exhibit's 11-05 row carried the 11-04 morning's Asia/VIX values and a post-gap weight
  (fixed: Asia -3.4%, VIX 16.6, SOXL 75%).
- MAJOR: "every rule" / "21 of 21" / "the only non-negative candidate" contradicted the study's own
  JSON — 4 of 47 KMLM and 3 of 47 HG rules (all mirrors, t <= 1.3) are positive, and the exhibit had
  listed only the two negative mirrors (fixed: counts over all 47, the positives named with t).
- MAJOR: the live "10 flips" mixed the any-change count with the path's long<->short distribution
  (fixed: 8 vs p99 8 / max 11; 10 vs 5.7 / 12 / 13).
- MINOR: claim (a)'s drawdown and percentile sub-clauses (17 rules improved DD slightly; one rule at the
  18th pct; 2023-26 inside the band), "two in three" (56% of engine fires; 70% is the panel's bottom
  decile), "model-free" (path-free), the short-leg label (all SQQQ), "entry day" (prior session), the
  ledger match (59/64 since 08-01, not 56/58), the phantom distribution gap, HG's dependence on 2016,
  the "-0%" tick and a double negative. All rewritten above and in the exhibit.
COUNTER-AGENT, edge study (scratchpad/review53b/): SHOWABLE WITH FIXES, all applied. Every E1 number
reproduced to the digit; no look-ahead; no phantom-gap trade in E1. Its findings: MAJOR multiplicity
(family-wise p 0.31 for the primary rule, 0.77 Bonferroni; only the sector rule survives, an in-sample
refinement of the same days); MAJOR three trades carry half the mean; MAJOR no transfer to the seven
other leveraged funds; MAJOR E2 as first built topped two-leg days to 137-200% exposure, had no
placebo, and 80% of its fires were not oversold mornings (fixed: capped per day, 300-draw band, the
share of oversold mornings shown; the gap rule falls inside the band); MAJOR a one-year paper track
cannot validate (reframed as an execution log); MINOR LABU heterogeneity, the pstdev t, costs (t 2.0 at
37 bps; TECL/LABU fills 50-80 bps), "17 years" (18). The intersection test (own state AND own gap)
verified; the claim "inside the engine it adds CAGR at a lower Sharpe" removed as first phrased.

DECISION: none on symphonies; no IBKR build; the overnight-overlay question joins the settled list
(ideas-backlog 14). New standing convention (CLAUDE.md): edge found in any study is reported as a
candidate edge — with its family-wise test, its out-of-sample check and what it would take to use it.
Open: the KMLM weight / leg size (Op 3 on 11-09; owner); the morning-bounce execution log (owner's
call to start it).

## Addendum 54 — The 11-05 batch: KMLM leg sizing, conditioned exits, the sleeve on a crash day, HARV's short-vol entries, and the futures tape (2026-11-05)

Owner, 2026-11-05, after KMLM lost 26.7% in one session (SOXL 75% into a −38.7% SOXL day): "Did you look
at volume of futures? Not just price, and look at other signals on futures" and "Run studies 1-4" (the
four areas proposed after add. 53). Five studies, each with its own script, frozen JSON, exhibit and
counter-agent review. Report-only; nothing traded, paused or edited. Scripts: research/leverage/
leg_sizing.py, research/overnight/conditioned_exits.py, research/crash/sleeve_audit.py,
research/harv_backwardation.py, research/overnight/futures_signals.py; exhibits results/
leg-sizing-, conditioned-exits-, sleeve-audit-, harv-backwardation-, futures-signals-2026-11-05.html.
Shared basis: the add. 47 daily engine paths (live trees, 1995-06..2026-11-04, synthetic pre-launch
legs, Composer-equivalent costs); daily data from Yahoo (its 11-05 rows were an 11:45 ET print until
22:55 UTC and are now the closes: SPY −4.41%, SOXL −38.7%, VIX 28.18, VIX3M/VIX −9.3%); t with the
sample sd; permutation and placebo tests as add. 53.

### 54.1 KMLM leg sizing — what a cap or a vol-target costs per point of drawdown saved (study 1)

WHAT WAS MEASURED. The KMLM path rebuilt from holdings × per-ticker returns (gate: max |diff| vs the
path 5.6e-17). The 75% leg = {TECL, SOXL, SPXL, LABU, SQQQ, UVXY, SVIX}: 75% on 6,279 of 7,894 sessions
(pairs at 37.5+37.5 on 3,631, single dip-buys 713), never above 75%. Variants decided at the prior
close, released weight in PULS (the tree's own cash leg), costed on their own turnover: caps 60 / 50 /
37.5 / 25; vol-target k/(0.75·σ20) with k matched to each cap's mean weight; halve the leg at prior
VIX > 25 / > 30; 2x and 1x substitutions. Metrics 1995-2026 and 2015-06..2026-11-04; the 11-05
session from the live holding at the ~15:50 prints (SOXL 44.50) and the 16:00 close (40.87).

RESULTS (CAGR / max DD / Sharpe; ratio = pp of CAGR given up per pp of max DD saved):
  variant                         1995-26               ratio   2015-26               ratio   11-05
  as built (mean leg 60%)         80.5 / 83.5 / 1.30      –     193.3 / 54.4 / 2.16     –     −24.4
  cap 60 → PULS                   65.4 / 74.3 / 1.30     1.6    143.8 / 44.8 / 2.16    5.2    −19.4
  cap 50                          54.8 / 65.9 / 1.30     1.5    113.8 / 37.9 / 2.16    4.8    −16.0
  cap 37.5                        41.2 / 52.6 / 1.31     1.3     80.1 / 28.8 / 2.16    4.4    −11.9
  cap 25                          27.7 / 36.1 / 1.30     1.1     50.3 / 19.2 / 2.15    4.1     −7.7
  vol-target k .43 (≈ cap 60)     49.1 / 81.6 / 1.23    16.3    125.4 / 34.1 / 2.21    3.4     −8.7
  vol-target k .22 (≈ cap 37.5)   27.1 / 64.9 / 1.15     2.9     62.3 / 25.4 / 2.10    4.5     −4.3
  halve the leg at VIX > 30       74.2 / 81.0 / 1.30     2.5    179.1 / 40.1 / 2.20    1.0    −24.4
  2x substitution                 60.5 / 75.7 / 1.27     2.6    137.8 / 49.7 / 2.10   11.9    −15.2
  1x reference                    31.8 / 70.9 / 1.16     3.9     75.8 / 42.0 / 2.05    9.5     −7.1
Caps are a pure sizing trade: Sharpe flat (1.30 → 1.31 / 2.16), each point of drawdown costs 1.1-1.6
points of CAGR over 31 years and 4-5 points since 2015. The since-2015 ratios are one episode: max DD
there is COVID (2020-01-24 → 03-20) by definition, so leave-one-year-out moves cap 37.5 from 4.4 to
2.9 (no 2022) .. 5.6 (no 2020), the vol-target k .43 from 3.4 to 2.0 .. 7.8, the VIX > 30 gate from 1.0
to 0.1 .. 9.0; "vol-targeting beats caps since 2015" and "the VIX gate is the cheapest" are statements
about February-March 2020 only, and without it the vol-target costs more per point than the cap. Over
31 years the vol-target is the dearest (16 pp/pp at the 60% mean weight, ill-conditioned: 6..138
leave-one-year-out): it cuts the leg after every shock, which on a dip-buying engine is when the
recovery is earned (time under water 1,826 sessions, 2006-02 → 2013-05, becomes 2,600-2,740). The VIX
gates were blind on 11-05 (VIX closed 16.6 on 11-04). 2022 is 20% of the 2015-26 log growth.
Book level (HG/KMLM/SLEEVE/HARV at 31/26/29/14): cap 50 gives up 22 pp of CAGR for 2.2 pp of max DD;
the book's 11-05: −8.1% as built → −4.1% at cap 37.5 → −3.1% at vol-target k .43.
Episodes: COVID −43.6% as built → −21.0% (cap 37.5) / −9.7% (vt k .22); 2025-04 −13.2 → −6.9 / −3.8;
2022 +1,112% → +270 / +146 (the in-sample peak year).

BY-PRODUCTS, after the counter-agent. (1) The leg earns most when its own vol is highest (+0.16%/day in
the lowest prior-vol quartile → +1.05% in the highest, t 5.0, n 1,569) — but the 1x twins show the same
gradient on the same days (+0.08 → +0.41%/day, t 4.7), within-branch it is weak (Welch t 0.2-2.3), and
53% of the top bucket's sum is pre-2010 synthetic: the engine is vol-timed by construction (its dip-buy
and pop branches fire in high vol), which is why a vol-target costs so much; a book-level size-up with
vol would be a post-shock-reversal bet, not a new conditional return. Not a candidate edge. (2) The
SOXL dip-buy branch (RSI10(SOXL) < 30 → SOXL 75%, the one that fired into 11-05) has no measured
return (n 212, +0.14%/day, t 0.2; 63% of its days synthetic, the real era n 79 +0.88%, t 1.3) — but a
14th-percentile placebo for the worst of nine branches is expected three times in four, and the real
fall-through if the branch is removed is TLT 75 (80 days) / SQQQ 75 (67) / SPXL or LABU dip-buys (44),
a SOXL pair on only 21 of 212: that edited tree is WORSE in the rules' own years (2015-26 CAGR 187.9 /
DD 61.3 vs 193.3 / 54.4; 2020-03-23 and 2022-01-31 flip to SQQQ losses; real era −0.41%/day vs +0.66%).
Not a candidate edge; the branch stays as built. The first draft's "DD 83.5 → 72.6, 11-05 +0.6" bound
was the 2006-08 synthetic era and is withdrawn.

HONESTY. In-sample re-sizings of a live rule on its own path (2015-26 are the rules' own years; 2022
alone is +1,112%); synthetic legs before launch (SOXL 2010-03, TECL 2008-12, LABU 2015-05, SVIX
2022-03; PULS = BIL on the whole path, so released weight earns T-bills throughout; the 83.5%
full-window drawdown is the 2006-08 synthetic era); costs = the engine's own (5.856 bps per unit
turnover) on each variant's turnover, no financing or tax; Composer's 10pp corridor, the sleeve's
rebalancing and taxes not modeled; 11-05 is off-path (the engine's own 11-04 close decision was SOXL
37.5 / TECL 37.5; Composer dip-bought SOXL 75 on the 15:54 price, a knife-edge); the "cap 37.5, half in
the 1x twin" row's leveraged weight is 36%, not 30% (the SVIX halves stay in SVIX).

COUNTER-AGENT (scratchpad/review1/): SHOWABLE WITH FIXES, applied. The sizing curve reproduced from
the raw path to four decimals (gate 5.55e-17; every CAGR / DD / Sharpe / ratio; the matched k; the 11-05
day; the book). Its findings: MAJOR candidate edge 2's "bounds" were not bounds (the real fall-through
is SQQQ/TLT and the edited tree is worse since 2015; the DD "cut" was synthetic) — withdrawn, the
fall-through table carried instead; MAJOR the since-2015 ratios are the COVID episode (leave-one-year-out
ranges added; the "cheapest" claims qualified); MINOR four exhibit sentences with wrong numbers (the
2006-13 under-water stretch, SOXL's 10-30 day −24.7%, "3-16" → 1.7-18, "the only branch" → not the only
one), the 36% leg weight, PULS = BIL throughout; edge 1 reframed as vol-timing by construction.

### 54.2 Oversold-conditioned overnight exits — add. 53's untested cell on the engines' paths (study 2)

WHAT WAS MEASURED. The add. 53 harness unchanged (15 + 10 bps, 2,000-draw same-side placebo, Wilder
RSI(10) on adjusted closes, family-wise permutation). Rules: own gap ≤ −3 / −5 / −8% and sector gap ≤
−1 / −2% × gates {ungated; held fund RSI ≥ 30 / 40 / 50; the converse RSI < 30; no dip-buy trigger
oversold; none of the five 3x funds oversold; switcher leg only} + gap-up mirrors = 51 rules per
engine, p_fw over all 51; ex-distribution mornings excluded (16 KMLM, 20 HG). Leg type from the
holdings (KMLM 0.75 = dip-buy branch, 0.375 = switcher pick; agrees with the trees' triggers on
2171/2171 KMLM legs). Panel: 12 long + 4 inverse funds 2010-26, own gap × own RSI state; add. 53's
cell reproduced to the digit (n 208, −0.92%, t −2.45).

RESULTS (KMLM as built 193.8% / 2.16 / −54%; dCAGR in pp over 2015-06..2026-11-04):
  rule                                       n    leg O→C    t     helped  dCAGR  placebo pct  p_fw
  gap ≤ −5% ungated (add. 53)                98   +1.53%    2.2    44%    −23.5     0%        1.00
  gap ≤ −5% & RSI ≥ 30 (= switcher leg)      78   +0.56%    0.9    46%     −5.2    48%        1.00
  gap ≤ −5% & RSI ≥ 50                       43   −0.12%   −0.2    56%     −0.1    80%        1.00
  gap ≤ −5% & RSI < 30 (converse)            20   +5.35%    2.4    35%    −18.6     0%          –
  gap ≤ −8% & RSI ≥ 30                       22   −2.33%   −1.9    64%     +4.4    99%        0.13
  gap ≤ −8% & RSI ≥ 40                       15   −3.36%   −2.7    80%     +4.5    99%        0.02
  gap ≤ −8% & RSI < 30 (converse)            13   +6.76%    2.1    38%    −15.0     0%          –
  sector gap ≤ −2% & RSI ≥ 50                26   −1.39%   −1.3    69%     +3.1    97%        0.35
  MIRROR gap ≥ +8% & RSI ≤ 70 (control)      36   −0.07%   −0.1    42%     +1.6    91%        0.87
HG: every rule with n ≥ 5 is negative (gap ≤ −5% ungated −10.3 pp; gated −1.4 to −2.0). The gate does
what add. 53 predicted: it removes the dip-buy mornings (the converse costs 15-19 pp on 13-20 fires)
and leaves a residual inside the placebo band. Only the ≤ −8% tail and its sector-gap cousin are
positive: +4.4 pp on a 194%/yr engine, 22 fires on 19 days in 11 years, three episodes (2020, 2025,
2026; the live year alone is 62% of the per-fire sum; without those three years n 3, all losers);
+4.1 at 25 + 15 bps, +4.9 gross, +3.0 at 50 + 50 (t 1.05). The t on the leg's open→close is −1.9; on the
engine's per-fire gain, the number the edge is claimed on, 1.60 (≥ 40: 2.44). Row-level p_fw 0.13 / 0.02
becomes 0.14 / 0.07 when the unit is the day (three two-leg days). Ex-2026 (n 17) the rule sits inside
the placebo band (per-fire t 0.65, helped 53%); leave-one-year-out never flips the sign. Panel, 12
funds one-per-day, the matching cell (≤ −8% & RSI ≥ 30): −0.30%, t −0.4 (the 30-50 column where 14 of
the 22 fires sit: +0.33%); the ≥ 50 column −1.60% (t −1.3) supports the ≥ 50 gate (n 8 on the engine,
p_fw 0.24), not the candidate. The engine's own −5..−8% not-oversold mornings bounce (+3.73%, n 21, t
4.0), which is why the ≤ −5% gate loses on the path where the panel is flat. Add. 53's cell (n 208,
−0.92%, t −2.45) included the 11-05 morning itself (ex 11-05: n 207, −0.86%, t −2.31).
11-05 under the path's own 16:00 logic (SOXL 0.375 + TECL 0.375): the ≤ −8% & ≥ 30 rule fires on SOXL
(gap −14.6%, open→close −28.2%, +9.0 pp of the symphony, the largest fire in the sample) and TECL fires
the ≤ −5% rule (+6.3 pp); it prompted the study, so it is fire #1 of an execution log, not evidence.
Live, the gate is a knife-edge of a different kind: the 16:00-close target was SOXL 0.375 / TECL 0.375
but at 15:50-15:55 on FMP minutes it was SOXL 0.75 (the shadow ledger's "knife-edge"); Composer
dip-bought on the 15:54 price and the close read RSI 30.2 (RSI 30 sits 0.87% below the actual close).
A switcher-leg gate on the live 0.755 holding would not have fired (rode −38.7% close-to-close); an
RSI ≥ 30 gate on the close read would have exited at −14.6%, +18.0 pp. The live rule must be keyed to
the engine's actual leg weight (0.375 = switcher pick), not an RSI read.

CANDIDATE EDGE (weak; a log line, not a build): KMLM, exit a switcher leg (weight 0.375) at the open on
own gap ≤ −8% — n 22 on 19 days, leg −2.3%, +4.4 pp/yr, 99th placebo pct, p_fw 0.13 by rows / 0.14 by
days (≥ 40: 0.02 / 0.07); the mirror (gap ≥ +8%, p_fw 0.87) does not refute it. To use: pre-register it
in the add. 53 morning-bounce execution log (09:25 print ≤ −8% vs the adjusted prior close, leg weight
0.375, cash to the next 15:50); ~34 fires for t 2 on the engine's gain ≈ 18 years at 1.9 a year. +4 pp
on a 194%/yr engine does not move the IBKR decision. Not an edge: the add. 53 cell as a ≤ −5% exit
(−5.2 pp, 48th pct); every HG rule; sector-gap variants (p_fw ≥ 0.35).

HONESTY. An in-sample refinement of an in-sample cell (same data, funds, years); the surviving cell is
the deepest tail of the hypothesis (≤ −8% of a ≤ −5% idea, ≥ 40 of a ≥ 30 gate) and p_fw covers this
study's 51 rules, not add. 53's 63 nor the choice of the cell; day-level p 0.14 / 0.07; three episodes;
the 30-50 panel column is flat; costs assumed, stressed-open fills not applied (50 + 50 bps: +3.0 pp);
the 09:25 ≈ open proxy; the first run's panel carried the 11:45 ET 11-05 print (now excluded; signs
unchanged).

COUNTER-AGENT (scratchpad/review2/): SHOWABLE WITH FIXES, applied. Every engine-path number reproduced
to the digit (n 22, −2.33%, +4.42 pp, p_fw 0.135; n 15, −3.36%, +4.48; n 98, +1.53%, −23.47); leg typing
confirmed against the tree on 28/28 dates; exhibit matched its JSON. Its findings: MAJOR the panel ran
on the stale half-day 11-05 row and the hypothesis cell contained the 11-05 morning (excluded; add. 53's
cell restated ex 11-05); MAJOR the wrong panel cell was quoted for the ≥ 30 gate (the matching cell is
flat); MAJOR p_fw 0.02 is row-level — by days 0.14 / 0.07; MAJOR the knife-edge paragraph misstated the
mechanism (15:54 vs 16:00, not a data-source gap; live rule keyed to leg weight); MINOR "~25 fires ≈ 13
years" (34 ≈ 18 on the engine-gain t), "the one cell" (five rules in the same tail), the ex-2026 band.

### 54.3 The Crash Convexity Sleeve on a −4.4% day: what it needs, what it has done (study 3)

WHAT WAS MEASURED. The approved tree (era yHJkdePZ) read condition by condition with shadow_runner on
the 11-05 closes; the add. 47 SLEEVE path 1995-06..11-04 plus the live 11-05 row; every SPY ≤ −3% day,
the eight episodes, down-day vs up-day betas, calm-year carry, parked share; a static VIXM / VXZ sleeve
as the comparator; path vs Composer's ledger 67 / 75 sessions since 07-15.

RESULTS. (a) The tree reads no VIX, VIX3M or broad index. Its conditions (24 nodes, 21 on the 11-05
path) are one-day shocks in HYG / TLT / SHY / TMF / LQD and RSI extremes in CORP / PEJ / KIE / LQD
(FrontrunBonds, 50%) plus the gate RSI(IEF,8) < RSI(PSQ,45) (InverseHold, 50%): bond and credit shocks
AND insurance / leisure-sector extremes. On 11-05 bonds were calm (HYG −0.31%, TLT +0.21%, SHY +0.21%,
LQD +0.15%) and the sector reads were mid-range: 0 of 21 true; closest SHY > +0.5% (0.29 pp away →
UVXY 50%), SHY < −0.33% (0.54 pp → UVXY 50%), LQD > +1.5% (1.35 pp → SOXL 50%), HYG < −1.75% (1.44 pp →
SVXY 50%). A flight-to-quality crash pushes IEF's RSI away from the gate. Most Frontrun branches, had
they fired at the 11-05 close, buy the worst one-day name of their list = SOXL: a dip-buy for 11-06,
not a hedge. "Firm: no change" was right; the sleeve is by construction a bond/credit-and-sector-shock
hedge, not a VIX or broad-index crash hedge.
(b) SPY ≤ −3% days since 2015-06 (n 36, in 20 runs): sleeve +3.90% mean on the day, median +0.0%, up
58%, parked at the open on 19 of 36; ≤ −4% (n 17) +5.37%, up 71%; ex-2020 +3.05%. The money comes after
the day: next 5 sessions +10.7% mean / +6.7% median / 89% positive over the 36 days, which are
clustered; one per run (first day) n 19, +2.8% mean / +1.2% median, 84% positive, t 1.9; per run,
first day to five after the last, +16.6% mean / +3.4% median; circular-shift placebo p 0.002. Since
1995 (n 104) +1.49%, up 53% — +0.21% on the 67 days before UVXY/SVXY existed (modeled legs) and +3.80%
on the 37 real-fund days. Episodes: 2015-08 −0.7% (entered on RSI(KIE,10) < 21; +6.7% one session
later), 2018-02 +24.5% (entered 01-26 on RSI(PEJ,14) > 75.6; the bond selloff opened the gate only on
01-30), 2018-12 −5.0% (KIE), COVID +179% (first entry 02-27 on RSI(KIE,10) < 21 → TQQQ, first vol leg
03-02 on KIE +5.5% → UVXY + SOXS, then the TMF / TLT / HYG shocks), 2022 +99% to the trough (+123% full
year; TMF −7.5% then SHY < −0.33%), 2024-08 +29.2% (SHY > +0.5% fired 08-02 → UVXY into 08-05), 2025-04
−1.0% (BOXX on 04-03 and 04-04, KIE −7.45% on 04-04), 11-05 0.0%. Four of eight paid: two entered on
sector triggers (2018-02, COVID), two on rates shocks (2022, 2024-08); the three equity-only selloffs
cost 1-5% to their troughs (a window statement; the next-20 column covers the rest). The per-run
after-crash effect is absent on the 1995+ path (+0.12%, n 62, p 0.74): it is a real-fund-era result.
(c) Convex: β to SPY −0.93 on down days (t −16.3) vs +0.06 on up days (2015-06+; −1.14 / −0.33 with all
legs real, 2020-12+); parked 72% of days; calm years (no ≤ −3% day) +37.1% mean since 2015 (in sample),
+2.2% median since 1995; CAGR 2015+ +57.9% (SPY +13.4%), max DD 19.8%; 1995+ +19.5%, max DD 51% (all of
it modeled-era: CAGR +0.8% to 2011-09, +43.6% from 2011-10). Comparator: a static VIXM leg on the same
crash days +7.31% mean, up 100% (sleeve +3.42%, up 52%) but CAGR −18% and −34% in calm years; on 11-05
VIXM +6.8% = +0.7% of the book at a 10% weight vs the sleeve's 0.

COMPONENT RECORDS (the sleeve's own rules read on their own in-sample history; not edges): UVXY while
held +5.28%/day vs −0.45% otherwise (n 101, t 4.6; OOS 2023-04+ n 19, +6.4%, hit 47%); SOXL as the
"worst one-day name" after a shock +3.13%/day, up 73% (n 70, t 4.5; OOS n 9); LABD when the gate selects
it +0.69%/day vs −0.33% (n 601, t 3.5; OOS n 205, t 3.3). Shift placebo p ≈ 0 for all (the rule times
its own legs); held one session later the same legs give +0.86 / +0.65 / +0.39%/day: a same-session
timing effect, not an overlay. Dead out of sample: TMV, SVXY. Reading rule: the sleeve's crash return
arrives in the 5-20 sessions after the crash day; judge it then, and the Op 1 band sells it then.

HONESTY. Legs before launch are models (VIX funds from a term-structure fit, synthetic VIX3M before
2006-07, leveraged copies for LABD / TMV / TMF / SOXS; BOXX = BIL on every path day; KMLM = RYMFX to
2020-12); both halves were authored 2023-25 on this history, so only 2024-06+ (4 crash days) and the
live log are out of sample; forward returns use overlapping windows dominated by 2020-03 and 2022
(per-run figures given); costs = the path's fitted 2.25 bps per unit turnover for this symphony (not
5.1, which is HG's; at 5.12 bps the 2015+ CAGR would read +55.6%), no limit-down fills; the five
early-October ledger misses are a data artefact (Yahoo's LQD / HYG / SHY / IEF / TLT series book no
ex-dividend after 2026-09-01; with LQD's 10-01 ex-div the RSI reads 29.9, not 24.5, and all five
October days re-decide to Composer's holdings; the path's return over those sessions is not overstated —
Composer held the same SOXL 50% from the 09-30 close, +5.67% on the path vs +5.79% on its actual
holdings): an unbooked monthly ex-dividend moves the one-day reads by 0.3-0.5 pp, the size of the SHY
thresholds (11-05 is not an ex-date); fire counts ignore cascade order; at run time
the daily dataset's 11-05 row was an 11:45 ET print, so this study read Yahoo's 16:00 closes directly;
the sleeve is a conditional hedge by design and the owner's sizing (Op 1; Op 2 review 2027-01) governs.

COUNTER-AGENT (scratchpad/review3/): SHOWABLE WITH FIXES, applied. Every number reproduced (own tree
walk, own Yahoo fetch, own path recompute: the 11-05 reads and distances, 36 crash days +3.90% / +0.01%
/ 58%, the betas, CAGR / DD, VIXM, the 67/75 ledger match). Its findings: MAJOR the cost level (2.25
bps, not 5.1); MAJOR the October ledger misses misdiagnosed as RSI seeding (an unbooked ex-dividend);
MAJOR "leaves BOXX when bonds move, not stocks" and "all four paid episodes were credit/rates shocks"
wrong (KIE / PEJ sector triggers entered two of the four); MAJOR clustered forward returns quoted as 36
independent observations (per-run line added, "t 3.6" dropped); MINOR the held-leg "edges" lacked
placebos (shift and lag-1 added; relabeled component records), the 1995+ mean split by era, the
trough-dated episode windows, the stale 11:45 note.

### 54.4 HARV's short-vol entries on inverted closes (study 4)

WHAT WAS MEASURED. The approved HARV tree read with shadow_runner; the "harvester 0.0202" line traced
in monitor.py; ZVOL's next 1 / 5 / 20 sessions by the VIX3M/VIX regime at the close (real 2023-04+,
VXZ-based proxy 2018+, modeled before); every engine entry into ZVOL on an inverted close with HARV's
subsequent return; the counterfactual ZVOL → PULS on inverted decision closes; the live record.

RESULTS. The rule has no backwardation input: nine voters on Wilder RSI(SPY, 2..10) weighted 36 / 16 /
8 / 8 / 8 / 8 / 8 / 4 / 4, RSI < 25 → ZVOL (unless RSI(UVXY,14) > 70 → PULS), RSI > 80 → VXZ, else
PULS; no HYG condition exists in any saved version (add. 48). On 11-05 RSI(2) 16.4, RSI(3) 20.9, RSI(4)
23.3 fired → 60% ZVOL; RSI(5) 25.07 missed by 0.07; the UVXY guard read 66.7 (3.3 points from
blocking). Backwardation is simply what an oversold SPY close looks like. "harvester 0.0202" is
Composer's last_percent_change for the symphony: HARV's own +2.02% on 11-05, earned by the VXZ 36% leg
(VXZ +6.64%); the 98th percentile of its daily returns and no signal (corr with ZVOL's next 20
sessions −0.03).
ZVOL after an inverted close: real era (48 closes in 17 episodes with outcomes; 49 / 18 counting 11-05)
next-20 +3.28% (t 2.3 on overlapping windows; iid placebo 95th pct but a block placebo with the same
17 episode lengths puts it at the 77th, band −2.5..+6.0%; leave-one-episode-out +1.7..+6.0%, the
2025-04-02 run is 66% of the sum) vs +1.47% after contango; on the proxy record since 2006 (553 closes,
2018 re-priced) −3.55% (t −6.9), −12.3% when the inversion is deeper than 8%. The filter: the inverted
closes HARV shorts into are followed by +0.54% next session since 2018 (n 68) vs −0.83% for the ones
it sits out (n 116; Welch t 2.3); real era +0.62% vs −0.59% (n 19 / 29, Welch t 1.1). Engine entries on
inverted closes: real era n 19, HARV next-20 +1.80% (t 2.2, 63% up), median hold one session; ZVOL
trades entered on inverted closes real era n 15, +0.61% mean, 80% win, +9.1 pp in all (t 1.0,
leave-one-out min +0.37%); 2018+ n 33, +0.97%, 82% win (t 2.3). Counterfactual ZVOL → PULS on every
inverted decision close: ×2.09 → ×1.94 real era, ×1.04 without 2025-03-14 (add. 39 C1 measured ×2.11
→ ×2.00 and killed the idea); 2018+ ×3.77 → ×3.01. Deep inversions (< −8%): both real-era deep trades
lost (−4.0% 2024-12-18, −5.2% 2025-04-03), but the full record of 29 deep entries has HARV +2.6% over
the next 20 sessions, 72% positive (23 modeled, 4 on the VXZ proxy, 2 real), and the deep-only
counterfactual hurts on 2006+; 11-05 (−9.3%) is deep entry number three, outcome pending (the live
record's first inverted close in 77 sessions). The engine path is the model, not Composer: 13 of 72
ledger sessions differ by more than 2 pp (10 knife-edge, 3 no-rebalance days).
Answer: one-session entries have paid, in sample, because of the SPY-oversold selection and the hold
length; short vol bought on any inverted close and held 20 sessions bleeds, the closes HARV picks do
not, on 15-33 real trades; "paying" is thin (t 1.0 real era), "not bleeding" is solid.

BY-PRODUCTS. E1 is HARV's own rule read on its own in-sample history, conditioned on a regime the rule
does not read: "the selection survives inversion" (Welch t 1.1 real era, 2.3 since 2018 re-priced),
not an edge; its contango comparison is not a placebo and its VXZ "mirror" is an identity before 2023.
E2 (avoid deep entries) is n 2 against 29 the other way: a watch item, not a candidate. To use either
beyond HARV: a log of ≥ 30 inverted-close entries (now 1).

HONESTY. ZVOL's real history is 892 closes, 48 inverted, 9 deep (3 episodes), 2 deep trades; pre-2023
= proxies (ZVOL = −0.971 × VXZ; VXZ modeled before 2018, 2008 artifact-grade per add. 27); Yahoo's VXZ
prints are STALE for 2018-01-26..2019-01-31 (flat 67.80 at zero volume for 169 sessions, 178 of 234
sessions at 0.00%, the Feb-2018 episode included): re-priced with VIXM inside this study (every 2018+
number changed, no sign flipped) and logged as an upstream defect of the add. 47 panel (the KMLM
sleeve's and HARV's 2018 path days rest on the same prints; fix pending); RSI windows chosen on 2015-26;
t on overlapping windows overstated (episode-start rows and block placebo given); the engine path is
the model, not Composer (10-30: model ZVOL 0.60 vs live 0.52, a ledger knife-edge); the UVXY guard
was a close call; "the gap is 15:50 fills" is plausible, not measured; the monitor's "harvester" label
should read "HARV day return".

COUNTER-AGENT (scratchpad/review4/): SHOWABLE WITH FIXES, applied. The rule description, the 11-05
vote (16.36 / 20.87 / 23.32 / 25.07; UVXY 66.66 → ZVOL 60%), the "harvester" number, every real-era
number, the live record and the exhibit's arithmetic reproduced. Its findings: MAJOR the "real VXZ
2018+" column was built on stale Yahoo prints for all of 2018 (re-priced with VIXM; 2018-23 ZVOL
after inverted closes 20d −5.2% → −3.0%, filter effect +0.65/−1.07% → +0.54/−0.83%, 2018+ trades +0.88%
→ +0.97%, counterfactual ×3.64→×2.68 → ×3.77→×3.01; verdict unchanged); MAJOR the "bleeding when deep"
title rested on 2 trades against a record of 29 the other way (retitled; E2 demoted to a watch item);
MAJOR clustering absent from the headline numbers (block placebo 77th pct, leave-one-episode-out and
Welch t added); MINOR the add. 47 / add. 39 citation, mixed count bases, the mirror identity, the
15:50-fill attribution, the stale 11:45-print note.

### 54.5 Futures volume and the overnight Globex session (study F)

WHAT WAS MEASURED. Add. 53 was price-only and used no futures. Added: (B) the Globex overnight session
itself from hourly ES / NQ / ZN / GC / 6J bars with volume (Yahoo, 582 nights 2024-06-17..2026-11-05,
the only free intraday futures history): the move to 09:00 ET, overnight volume and range vs their
20-night medians, position in the range, recovery from the low, Asia vs Europe hours, late (06-09)
volume share, note / gold / yen as risk-off confirmation; outcomes = the next session's open→close of
SPY, QQQ, SMH and the three tech 3x funds, and the KMLM leg when held. (A) The prior session's volume
(ES, NQ, the fund's own, SPY, each vs its 20-session median) back to 2015 on the mornings add. 53
studied, model-free and on the engines' legs (exit at the open, 25 bps, same-count placebo). (C) The
11-04 → 11-05 night hour by hour. (D) Opening 5-minute volume of SOXL / TECL for 30 sessions
(illustration). Every split permutation-tested with a family-wise p over all splits on a sample.

RESULTS. (C) The crash was not an overnight event: ES at 09:00 on 11-05 was +0.04% vs the prior cash
close on 1.01× its median overnight volume (48th pct) and 0.94× its median range; NQ −0.9% (11th pct),
gold +1.5%, the note −0.1%. The −4.4% came between 09:00 and 16:00, three quarters of it by 11:00,
on 476k and 832k contracts an hour against 10-35k overnight. SPY's session −4.24% is the worst of the
582; no pre-open read of the futures, price or volume, had it.
(B) The overnight tape predicts the SIZE of the session, not its direction, and the size read is the
RANGE: mean |SPY open→close| 0.41% / 0.51% / 0.72% by tercile of the overnight range (t 6.5); by
overnight volume 0.46% / 0.51% / 0.67% (t 5.6), but the two ratios move together (r 0.78) and jointly
volume adds nothing (t 1.0, range t 3.3; within range terciles the above-median-volume half differs
by −0.04 / −0.09 / +0.11%). The overnight move itself reverses on average (slope of the session on the
overnight ES move −0.13, t −2.2; tech 3x −0.68, t −2.4), the same on high-volume nights (t −1.8). Down
nights (ES ≤ −0.5%, n 73): the session continued down 51% of the time, mean SPY +0.13%, tech 3x
+0.64%; split by overnight volume ≥ 1.5× median +0.27% vs +0.02% (p 0.59); by range, late volume, yen,
gold, tech-led: p 0.3-0.9; nothing survives family-wise over the splits with 8+ nights a side (p 0.26
/ 0.59 at −0.5%, 0.28 / 0.45 at −1%; the 2-6-night splits that drove the first run's "p 0.04" are a V
already under way, and the n 6 cell is one night, 2025-04-09). The note up overnight at ES ≤ −1% (15 vs
15: SPY −0.31% vs +1.17%, p 0.05 single-test) is logged, not a candidate. KMLM held a leg on 32 of the
73 nights: +2.01% (t 1.2), the same on high- and low-volume nights. Up-night mirror (ES ≥ +0.5%, n 89):
SPY −0.07% (t −0.8), continued up 47% of the time.
(A) 2015-26: on the oversold-close sample the bounce does not depend on volume (E1 sample, 31 days,
+5.1%; family-wise p 0.81 over 12 splits). On all 3%+ gap-downs (490 days) the one split that survives
is SPY climax volume (≥ 2× its median) the session before: +3.2% (n 26) vs −0.4% (n 464), p 0.00,
family-wise 0.04; median +2.4%, 54% up, +1.2% without the best three days, 18 distinct months,
leave-one-month-out +2.5..+4.1%, SPY itself +0.8% (t 1.6) vs −0.0%. The gap-up mirror (n 35, −1.3% vs
+0.4%, p 0.05) is a mean made by six days of −10% or worse: median +1.1%, 63% of those days closed up.
Its complement, found by the counter-agent in the same table: a 5%+ gap-down on the fund's OWN climax
volume when the fund was NOT oversold (RSI(10) ≥ 30) continues down — 12 days in 12 months, −5.0%
mean, −4.9% median, 17% up, −7.2% without the best three, vs +0.2% on the other 200 (p 0.003,
family-wise 0.06); SPY itself −1.07% (t −2.5); at 3%+ 17 days, −3.3% (p 0.02, family-wise 0.10); the
mirror (5%+ gap-up on climax volume, not overbought) −0.8% vs +0.8% (p 0.17): no continuation up. On the
engines' own legs the climax-volume exit rules lose on any or oversold legs (KMLM gap ≤ −3% AND fund
volume ≥ 2×: 15 fires, leg +2.06%, exit value −31 pp, 1st placebo pct; the legs bounce on exactly
those mornings) and pay on the few NOT-oversold legs (KMLM 4 fires +29 pp, 21 of it 11-05, +8 without;
3 fires +26 pp; HG 3 fires −18 pp): the one rule that would have exited 11-05 (SOXL traded 2.5× its
median volume on 11-04 and closed with RSI 30.2). (D) SOXL's opening five minutes on 11-05 traded 1.0×
their 30-session median (TECL 2.5×); 30 sessions say nothing.

CANDIDATE EDGES (to log, not to trade; both found while searching 12 splits on 10 conditions): (1)
SPY climax volume the session before a 3%+ gap-down → bounce (26 days, +3.2%, family-wise 0.04, no
clean mirror); (2) the fund's own climax volume before a 5%+ gap-down on a fund NOT oversold →
continuation (12 days, −5.0%, family-wise 0.06, mirror none). They are add. 53's "oversold → bounce"
and its complement seen through volume. Pre-register the next ten occurrences of each. The size read
(range) is a sizing input, not a trade.

HONESTY. Yahoo continuous front-month contracts (roll weeks distort daily volume: the Tuesday-Thursday
before expiry print 0.3-0.7×, 14% of "quiet" flags are roll days; Yahoo repeats the prior session's
volume on four ES days since 2015, 2026-11-04 among them — patched from the hourly bars where they
exist, dropped otherwise; before the patch the 11-05 morning sat in "ES volume < 1x" and alone made two
rules positive); hourly history is 730 days (582 nights, 18 dropped where the bars do not frame the
night; ~70 down nights, 30 at ≤ −1%); the first bar of each weeknight session prints zero volume; the
overnight read is 09:00 ET, 30 minutes before the open (add. 53's bridge covers 09:25); outcomes on raw
opens and closes (11-04/05 refreshed to the closes; SPY's volume matches FMP on 2,833 days); the 11-05
engine leg is the live holding, off-path; the engine "exit value" is summed, not compounded; VIX
futures intraday, open interest, basis and order flow are not free and were not tested; FMP 1-minute
bars run back to 2016 with volume but cost one call per fund-day, so the opening-volume read is 30
sessions.

COUNTER-AGENT (scratchpad/reviewF/): SHOWABLE WITH FIXES, applied. The session construction and every
headline number reproduced to the digit (582 nights, the 11-05 night by hand, the carry slopes, the
terciles, the down-night splits, the climax split and its mirror, the engine rules). Its findings: MAJOR
"volume predicts size" is the overnight range (jointly volume t 1.0, range t 3.3; headline rewritten);
MAJOR section E's "every volume-conditioned rule is negative" was false by its own table and the
NOT-oversold climax cell was never called out (now the second candidate, with its mirror); MAJOR a Yahoo
duplicate volume print on 11-04 misfiled the 11-05 morning (patched; two KMLM rules flip back negative);
MAJOR the section C family-wise p was the 2-6-night splits (restricted to 8+ a side: nothing survives);
MINOR the "clustered in the crash months" claim (18 months; leave-one-month-out given), the mirror's
median / win line, SPY's own return beside the pooled funds, a stale t, "recovered 185%", the summed
exit value and the placebo direction stated.

### DECISION

None on symphonies: no trade, no symphony edit, no IBKR build. The five studies change what is known,
not what is held. (1) KMLM's leg size is the owner's call with the curve in hand (54.1): a cap buys
drawdown at 1.1-1.6 points of CAGR per point over 31 years and 4-5 in the rules' own years, Sharpe
unchanged; nothing in the data says to resize, and the SOXL dip-buy branch stays as built. Operation 3's
earn-back read lands 11-09. (2) The add. 53 execution log (ideas-backlog 14) gains two pre-registered
lines: the ≤ −8% switcher-leg exit (54.2) and the climax-volume pair (54.5: SPY climax → bounce on a
3%+ gap-down; own climax + not oversold + 5%+ gap-down → continuation). Ten occurrences of each before
anything is a rule. (3) The sleeve is what it was sized to be (54.3): a bond/credit-and-sector-shock
hedge that pays in the 5-20 sessions after a crash day and sat out 11-05 correctly; a static vol leg is
the Op 2 question for 2027-01. (4) HARV's inverted-close entries have paid on one-session holds in
sample (54.4); 11-05 is the live record's first inverted close and its third deep entry; revisit at 30.
(5) The futures tape carries no direction into the session, price or volume; its range sizes the day.
Two data defects go upstream: Yahoo's VXZ 2018 prints in the add. 47 panel (HARV's and the KMLM
sleeve's 2018 path days) and bond-ETF ex-dividends missing from Yahoo's series (the sleeve's October
path/ledger misses; a 0.3-0.5 pp read error at the SHY thresholds). The monitor's "harvester" label
becomes "HARV day return". Open for the owner: the leg size; the sleeve's static vol leg; the IBKR
genomics sleeve record (add. 52, still missing).
