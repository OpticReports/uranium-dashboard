# SOXL short / constituent long — decomposition, backtest, verdict

Period 2010-03-12 (SOXL inception) → 2026-08-14. All numbers net of modelled
IBKR costs unless marked gross. **Sharpe is excess of the 3m bill** throughout.
Frozen in `fixtures/`; regenerate with `fetch_data.py` then the analysis scripts.

---

## 1. Executive summary

**There is a real edge here, and it is roughly 1.4%/yr on capital. Everything
else in the seed strategy's P&L is rebalancing luck and residual beta.**

| Question | Answer |
|---|---|
| Is the friend's book market-neutral? | Yes — measured net beta to SOXX **−0.07**, to SPY −0.06. Not disguised long beta. It is very slightly net *short*. |
| Where does the edge come from? | Shorting SOXL harvests the fund's fee+financing drag: **−5.39%/yr alpha vs SOXX** (t = −3.02). At 25% notional that is **+1.35%/yr on capital**. |
| Is "own the winners" alpha? | **No.** Top-8 vs SOXX alpha is +3.95%/yr but t = 1.47. Ex-NVDA it falls to +1.09%/yr, t = 0.49. It is one stock, not a factor. |
| Is variance drag harvestable? | **Not without selling convexity.** Beta-matched daily rebalancing captures the fee term *only*. The 28.5%/yr variance drag accrues solely to a position you let ride — and letting it ride wipes the book out. |
| Does the seed strategy work? | **No.** V0 as specified: **3.1% CAGR, 0.21 Sharpe, −41.5% maxDD.** In-sample (≤2019) it *lost* money: −0.7%/yr. |
| Best honest variant | Same book rebalanced **weekly**: 7.2% CAGR, 0.67 Sharpe, −23.3% maxDD, bootstrap 90% CI on CAGR **[3.6%, 10.9%]**. |
| Does it beat the trivial alternative? | **No.** 75% of the same basket + 25% cash returned **20.7% CAGR at 0.90 Sharpe** with a comparable −40.5% drawdown. |

**Verdict: repeatable alpha ≈ 1.4%/yr (the ETF fee harvest, structural and
durable); everything above that is regime rent.** The book is a *short-trend,
long-vol* position wearing market-neutral clothing. Probability the historical
record represents repeatable alpha rather than regime luck: **~20%** — and the
20% is small.

---

## 2. Decomposition (Step 1)

### 2.1 The decay is two different things, and only one is harvestable

`r_SOXL = α + β·r_SOXX` on daily data, n = 4,132:

| | value |
|---|---|
| β | **2.9625** (SE 0.0036; design 3.0) |
| α | **−5.39%/yr** (SE 1.78%, t = −3.02) |

That α is the whole harvestable edge: expense ratio plus the fund's financing
spread on its 2× borrowed notional. A beta-matched, **daily-rebalanced** short
of SOXL against long SOXX earns α and nothing else — deterministically.

The famous variance drag is a *different* term and it does not show up in daily
arithmetic returns at all:

```
log(SOXL_T) − 3·log(SOXX_T) = −(3²−3)/2 · σ² · T − fees·T
```

Realized over the full period: **−34.4%/yr** of log return. Theory at σ = 30.8%:
28.5% variance drag + 5.4% fees = **33.9%/yr**. The identity holds to 0.5pp.

**But you cannot bank it without letting the position drift**, and that is the
entire risk:

| reset cadence | CAGR | vol | Sharpe | maxDD | skew |
|---|---|---|---|---|---|
| daily | 6.2% | 7.3% | 0.86 | −13.5% | +10.4 |
| weekly | 9.0% | 10.6% | 0.87 | −13.4% | +4.6 |
| monthly | 9.3% | 16.8% | 0.61 | −25.8% | +2.6 |
| quarterly | — | — | **WIPED OUT** | −100% | — |
| never (static) | — | — | **WIPED OUT** | −100% | — |

*(short 1× SOXL / long 3× SOXX on 1× capital, gross of costs — 4× gross
exposure, portfolio margin only.)*

Variance drag is a **mean-vs-median** effect. Shorting it converts a
positive-skew payoff into a negative-skew one: win small often, lose enormously
rarely. That is a short-gamma position, not a carry trade.

### 2.2 Beta accounting — the book really is neutral

| leg | β vs SOXX |
|---|---|
| SOXL | 2.963 |
| top-8 cap-weighted basket | **0.895** |
| **V0 book** (0.75·basket − 0.25·SOXL) | **−0.069** measured, −0.069 implied |
| V0 vs SPY | −0.060 |

Rolling 126-day net beta: min −0.25, median −0.09, max +0.16; **positive only
16% of the time**. The basket's β is *below* 1 because SOXX's 8%/4% caps push
weight into smaller, higher-beta names — so 25% short SOXL over-hedges slightly.

Attribution of V0's gross return (sum of daily arithmetic): total +39.9%, of
which **beta contributed −31.0%** and residual/alpha +70.9%. The neutrality cost
it money in a semis bull market; the alpha did all the work.

### 2.3 "Own the winners" is one stock

| basket | CAGR | β | α/yr | t(α) | IR |
|---|---|---|---|---|---|
| top-3 cap | 27.1% | 0.87 | +5.13% | 1.33 | 0.33 |
| top-5 cap | 27.3% | 0.88 | +4.64% | 1.46 | 0.36 |
| top-8 cap | 27.1% | 0.90 | +3.95% | 1.47 | 0.36 |
| top-12 cap | 26.8% | 0.91 | +3.26% | 1.37 | 0.34 |
| top-8 equal-weight | 27.7% | 0.94 | +3.22% | **1.86** | 0.46 |
| top-8 6mo momentum | 27.4% | 1.08 | +1.10% | 0.35 | 0.09 |

Nothing clears t = 2. Two diagnostics kill the "concentration alpha" story:

- **Ex-NVDA: α +1.09%/yr, t = 0.49.** The alpha is NVDA.
- **Not the index caps.** Re-applying SOXX's own 8%/4% caps to the basket leaves
  α at +3.75% (t = 2.01) — so it is not "we let winners run", it is "we owned
  the eight biggest".
- **Unstable across subperiods:** 2010-14 +3.51% (t 1.00), 2015-19 **−1.95%**
  (t −0.67), 2020-26 +9.18% (t 1.63).

### 2.4 Cost stack

| item | size |
|---|---|
| gross edge from short leg | 5.39%/yr **of short notional** = 1.35%/yr on capital at 25% |
| **breakeven SOXL borrow** (short-leg carry edge → 0) | **5.39%/yr** |
| breakeven borrow for the whole V0.W book (CAGR → cash) | **23.5%/yr** |
| commissions + slippage assumed | 0.5bp commission, 2bp ETF / 3bp stock slippage |
| turnover (V0 monthly / V0.W weekly) | 1.68× / 4.53× capital per year |

Borrow is the study's **one unsourced input** (see §7). The sweep shows why that
turns out not to be fatal for the 25%-notional book: the short is mostly a
*hedge*, so the book tolerates borrow up to 23.5%/yr before underperforming
cash. The **decay-pure** variant is far more fragile — V4.d's Sharpe goes
negative between 2% and 3% borrow.

### 2.5 Negative convexity — which regime this is actually short

Static 25% short SOXL, never rebalanced, P&L on capital:

| year | SOXL | P&L | short grows to |
|---|---|---|---|
| 2019 | +231.6% | **−57.9%** | 83% of capital |
| 2023 | +227.1% | **−56.8%** | 82% |
| 2026 YTD | +242.8% | **−60.7%** | 86% |
| 2022 | −85.7% | +21.4% | 4% |

Conditional Sharpe of the short leg (daily, 25% notional):

| regime | days | annualized | Sharpe |
|---|---|---|---|
| SOXX > 200dma, vol < median | 1,824 | −15.2% | −0.98 |
| SOXX > 200dma, vol > median | 1,220 | **−61.1%** | **−2.41** |
| SOXX < 200dma, vol < median | 162 | +74.9% | +3.76 |
| SOXX < 200dma, vol > median | 726 | +21.0% | +0.64 |

**The short leg is a bearish trend bet, not a decay harvester.** It pays only
below the 200dma.

---

## 3. Variant table (Step 3)

Full period, net of all costs. `CAGRg` is gross of commissions, slippage, borrow
and financing spreads.

| # | variant | CAGRn | CAGRg | vol | Sharpe | Sortino | maxDD | Calmar | βSOXX | βSPY | trd/yr | turn | worst 12m | PM margin max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **V0** | 25/75 top-8, monthly | **3.1%** | 3.5% | 10.1% | **0.21** | 0.27 | −41.5% | 0.07 | −0.05 | 0.00 | 111 | 1.68 | −35.2% | 58% |
| V1 | beta-neutral hedge ratio | 5.8% | 6.2% | 9.3% | 0.50 | 0.65 | −32.3% | 0.18 | 0.01 | 0.08 | 111 | 1.92 | −26.1% | 48% |
| V2 | vol-targeted 15% | 2.8% | 3.8% | 18.1% | 0.16 | 0.23 | −58.5% | 0.05 | −0.08 | 0.02 | 111 | 4.30 | −40.4% | 94% |
| V3 | top-3 | 2.9% | 3.3% | 13.6% | 0.17 | 0.23 | −51.8% | 0.06 | −0.07 | −0.01 | 49 | 1.77 | −46.1% | 58% |
| V3 | top-5 | 3.0% | 3.5% | 11.6% | 0.19 | 0.25 | −45.7% | 0.07 | −0.06 | −0.01 | 74 | 1.73 | −39.5% | 58% |
| V3 | top-12 | 3.0% | 3.4% | 9.2% | 0.21 | 0.27 | −38.2% | 0.08 | −0.04 | 0.02 | 162 | 1.68 | −32.1% | 57% |
| V3 | top-8 equal-weight | 4.0% | 4.4% | 7.1% | 0.38 | 0.48 | −21.7% | 0.18 | −0.01 | 0.02 | 111 | 2.32 | −9.7% | 55% |
| V3 | top-8 6mo momentum | 4.5% | 5.1% | 10.9% | 0.32 | 0.42 | −27.1% | 0.16 | 0.09 | 0.14 | 138 | 9.50 | −20.3% | 54% |
| V4 | decay-pure, monthly | 2.9% | 3.3% | 4.4% | 0.35 | 0.43 | −12.4% | 0.23 | 0.03 | 0.07 | 24 | 1.52 | −8.4% | 52% |
| V4.d | decay-pure, **daily** | 1.8% | 2.3% | 1.8% | 0.19 | 0.28 | −3.6% | 0.49 | 0.01 | 0.01 | 504 | 5.69 | −0.6% | 23% |
| V5 | double decay (SOXL+SOXS short) | 20.0% | 21.6% | 20.5% | 0.92 | 1.30 | −28.1% | 0.71 | **0.51** | **0.84** | 123 | 9.44 | −16.2% | 50% |
| V6 | long puts instead of short | *modelled — see §5* | | | | | | | | | | | | |
| V7 | V0 gated (<200dma & vol>med) | 2.2% | 2.5% | 4.1% | 0.19 | 0.11 | −12.9% | 0.17 | −0.01 | 0.00 | 26 | 1.82 | −7.7% | 31% |
| V8 | drift-band ±5% | 4.1% | 4.6% | 8.7% | 0.34 | 0.49 | −27.6% | 0.15 | −0.06 | −0.05 | 166 | 2.46 | −20.3% | 26% |
| **V0.W** | **baseline, weekly rebalance** | **7.2%** | 7.7% | 8.9% | **0.67** | 0.97 | −23.3% | 0.31 | −0.06 | −0.05 | 476 | 4.53 | −15.6% | 33% |
| V0.D | baseline, daily rebalance | 6.7% | 7.4% | 8.6% | 0.64 | 0.93 | −24.1% | 0.28 | −0.07 | −0.06 | 2,271 | 9.47 | −17.0% | 23% |
| V0.Q | baseline, quarterly | 1.5% | 1.9% | 12.7% | 0.07 | 0.08 | −55.9% | 0.03 | −0.07 | 0.00 | 38 | 1.11 | −50.6% | **98%** ⚠ 1 margin call |
| — | **BM: SOXX long-only** | 25.2% | 25.2% | 30.8% | 0.84 | 1.16 | −45.8% | 0.55 | 1.00 | 1.45 | 0 | 0.06 | −35.1% | 15% |
| — | **BM: 75% basket + 25% cash** | **20.7%** | 20.8% | 22.2% | **0.90** | 1.23 | −40.5% | 0.51 | 0.67 | 1.01 | 99 | 1.48 | −28.7% | 12% |
| — | BM: SPY long-only | 14.2% | 14.2% | 17.1% | 0.78 | 0.96 | −33.7% | 0.42 | 0.45 | 1.00 | 0 | 0.06 | −18.2% | 15% |

**V5 is mislabelled by tradition.** Shorting SOXL *and* SOXS does not produce a
neutral book — it produces β 0.51 to SOXX / 0.84 to SPY, because the long basket
overlay is unhedged once the two ETF shorts cancel. Its 20% CAGR is mostly beta,
and it carries the hardest-to-borrow leg in the study (SOXS).

### In-sample / out-of-sample split

| variant | IS ≤2019 CAGR | IS Sharpe | OOS 2020+ CAGR | OOS Sharpe |
|---|---|---|---|---|
| V0 | **−0.7%** | **−0.14** | 8.8% | 0.47 |
| V0.W | 1.5% | 0.19 | 16.4% | **1.11** |
| V1 | 1.9% | 0.27 | 11.6% | 0.70 |
| V5 | 12.3% | 0.91 | 32.6% | 1.04 |
| BM 75% basket + cash | 13.0% | 0.83 | 33.4% | 1.04 |

**Every version of this strategy is a post-2020 phenomenon.** The seed strategy
lost money for its first decade. This is not the classic overfit signature (good
IS, bad OOS) — it is regime dependence, which is worse in one specific way: it
cannot be diagnosed by the usual OOS test, and it *will* revert when the regime does.

---

## 4. Gate analysis (Step 4)

Conditional performance of the **ungated** V0 book, partitioned by gate state:

| gate | % on | ON ann | ON Sharpe | OFF ann | IS ON | OOS ON |
|---|---|---|---|---|---|---|
| SOXX < 200dma | 23% | +6.8% | 0.64 | +2.6% | −0.8% | +17.9% |
| SOXX < 100dma | 27% | +11.9% | 1.16 | +0.5% | +3.6% | +23.0% |
| 20d rvol > 1y median | 51% | +1.7% | 0.15 | +5.4% | −1.5% | +5.9% |
| 20d rvol > 1y 75th | 28% | +4.9% | 0.40 | +3.0% | +2.6% | +7.9% |
| VIX term structure inverted | 8% | +23.5% | 1.84 | +1.9% | +9.0% | +47.9% |
| dispersion > 1y median | 52% | +2.9% | 0.30 | +4.2% | −0.6% | +7.8% |
| SOX/SPX 6mo mom < 0 | 34% | +6.8% | 0.74 | +1.9% | +1.3% | +16.5% |
| **COMBO <200dma & rvol>med** | 18% | +8.2% | 0.75 | +2.6% | +1.5% | +17.8% |

**Applied** (engine, net of costs), with the overfit screen:

| gate | IS Sharpe | OOS Sharpe | verdict |
|---|---|---|---|
| (ungated V0) | −0.14 | 0.47 | NO IS EDGE |
| SOXX < 200dma | 0.01 | 0.16 | ok (but ~zero IS) |
| VIX term structure inverted | −0.18 | **−0.57** | NO IS EDGE |
| dispersion > 1y 75th | −0.34 | 0.44 | NO IS EDGE |
| SOX/SPX 6mo mom < 0 | −0.11 | 0.60 | NO IS EDGE |
| **COMBO <200dma & rvol>med** | **0.17** | **0.23** | **ok — the only gate positive in both halves** |

Three things worth stating plainly:

1. **The conditional view flatters rare gates.** VIX-inverted looks spectacular
   (ON Sharpe 1.84) but is on 8% of the time; *applied*, it delivers a −0.57 OOS
   Sharpe. Conditional-on tables are not strategies.
2. **Gating reduces total return in every case** (V7: 2.2% vs ungated 3.1%). The
   book is near-neutral and cheap to hold, so time out of the market is pure
   opportunity cost. Gates improve Sharpe-per-unit-exposure, not compounding.
3. **Exactly one gate survives both halves**, and only at Sharpe ~0.2.

---

## 5. V6 — puts instead of a short (MODELLED, not backtested)

No historical SOXL option chain was available. Premiums are Black-Scholes on
**trailing** realized vol × (1 + vrp), plus 150bp paid to the offer, quarterly
roll, 25% of NAV covered. Directional only.

| moneyness | vrp | premium/yr | payoff/yr | **net carry** | maxDD |
|---|---|---|---|---|---|
| ATM | 0% | 17.5% | 9.6% | **−7.8%** | −37.9% |
| ATM | 15% | 20.0% | 9.7% | −10.3% | −39.6% |
| 10% OTM | 5% | 12.8% | 6.1% | **−6.7%** | −40.4% |
| 20% OTM | 5% | 8.4% | 3.6% | **−4.8%** | −40.7% |

The leg being replaced earns **+1.35%/yr**. The cheapest put program costs
**−4.8%/yr**. Buying the convexity back costs ~6× the edge the whole strategy
generates, and it does not fix the drawdown (still ~−40%, because puts on SOXL
hedge the *short* leg's risk, not the basket's). **Rejected.**

---

## 6. Forward-looking assessment (Step 5)

Empirical forward 12-month outcomes for **V0.W**, conditioned on the regime
holding at entry (n = overlapping windows; the primary view — see §7 on why the
resampled version is not used for tails):

| regime | windows | median | 5th | worst | best | P(loss) |
|---|---|---|---|---|---|---|
| (a) semi bull / AI capex melt-up | 1,861 | **+1.1%** | −5.9% | −13.2% | +66.2% | **43%** |
| (b) sideways high-vol chop | 1,027 | +5.8% | −6.6% | −16.0% | +55.7% | 20% |
| (c) cyclical downturn | 956 | +6.0% | −6.8% | −16.0% | +53.9% | 22% |
| (d) vol spike (top-decile vol) | 336 | **+9.8%** | −0.3% | −6.7% | +46.4% | 5% |
| unconditional | 3,879 | +5.0% | −6.2% | −16.0% | +67.0% | 29% |

**The strategy is implicitly short the AI-capex melt-up and long volatility.**
In regime (a) — the one the semis market has actually been in — it is a coin
flip with a +1.1% median. It earns its keep in chop and vol spikes.

Note the seed V0 (monthly) is materially worse in the tail than V0.W: worst
rolling 12-month **−35.2%** vs −15.6%.

### Edge attribution and durability

| driver | contribution | durable? |
|---|---|---|
| ETF fee/financing harvest | **+1.35%/yr** | **Yes — structural.** It is the fund's expense ratio and financing spread. It shrinks only if Direxion cuts fees or rates collapse. |
| Concentration / "winners" | +2.96%/yr nominal | **No.** t = 1.47; ex-NVDA t = 0.49; negative 2015-19. |
| Residual beta | −1.7%/yr | n/a — a cost of neutrality, not an edge. |
| Rebalancing convexity control | +4.1%/yr (V0 → V0.W) | **Partly.** Mechanical, but it is buying gamma, and its payoff depends on realized vol staying high. |

**Honest probability this is repeatable alpha rather than disguised
regime exposure: ~20%.** The 1.35%/yr fee harvest is real and bankable. The
other ~5.8%/yr of V0.W's return is short-trend/long-vol rent that a sustained
semis melt-up will take back — as it did in 2026 (−31.4% for V0).

### Kill criteria

Shut the book down if any of these fire:

- Rolling 24-month Sharpe < 0.
- SOXL borrow > **5.4%/yr sustained** (short-leg carry edge gone) — hard stop at
  23.5%/yr (whole book underperforms cash).
- SOXL's measured α vs SOXX decays above −2%/yr on a trailing 2-year window
  (fee compression / financing spread collapse).
- Realized SOXX vol < 20% annualized for 6 consecutive months (no chop to harvest).
- Net beta drifts outside ±0.20 for 20 consecutive trading days.
- Drawdown > 25% from high-water mark.

---

## 7. Data, assumptions and what is NOT modelled

**Sources.** FMP `stable` endpoints, frozen 2026-08-14 to `fixtures/`. All
downstream scripts are offline. Dividend-adjusted closes on both legs, so the
short pays SOXL's distributions automatically.

**Point-in-time universe.** Reconstructed by ranking a 108-name candidate set —
**including 20 acquired/delisted names** (XLNX, BRCM, MXIM, CY, LLTC, ATML,
MSCC, PMCS, IPHI, CAVM, OVTI, …) — by market cap observed at each month end.
Validated against reality: correlation to actual SOXX **0.992**, tracking error
3.89%/yr, **26/30 membership overlap** today.

**Measured, not asserted:** rebuilding the universe survivorship-free changes
the answer by **+0.06pp of CAGR**. For a top-8 mega-cap basket, survivorship
bias is small — the rigour confirms that rather than rescuing the result.

### The one input I could not source — and what I need from you

**SOXL borrow-rate history.** No vendor series (IBKR SLB / Markit) was
obtainable here, so borrow is a **swept parameter** with a solved breakeven, not
an assumed constant. Baseline 1.0%/yr on SOXL, 3.0%/yr on SOXS.

This turns out not to change the verdict — the book survives to 23.5%/yr borrow —
but **if you can pull your actual IBKR borrow rate on SOXL (and SOXS if you want
V5 taken seriously), I'll re-run the sweep against the real series.** SOXL is a
$4.9bn/day ETF and generally easy-to-borrow, so the 1% baseline is likely
conservative; the risk is episodic spikes, which a single current rate won't reveal.

### Not modelled

- **Intraday execution.** Daily closes only; slippage is a parametric 2–3bp.
- **Locate availability and forced buy-ins.** Modelled as always available.
  A buy-in during a squeeze is precisely when the short is largest.
- **Options market data** for V6 (§5 is a model).
- **Semi-cycle fundamentals** (global semi sales YoY, inventory) — no vendor
  series; the macro gate uses SOX/SPX ratio momentum as a proxy.
- **Tax.** Short dividends and the constructive-sale rules are ignored.

### Known method caveats

- **The block bootstrap understates tails.** It reassembles independent 21-day
  fragments, so it cannot produce a 2026-style twelve-month trend — it reported
  P(loss < −20%) = 0% in every regime *while the book was living through a −31%
  year*. §6 therefore uses empirical forward windows, and the resampled figures
  are kept only as a secondary column in `fixtures/validation.json`.
- **2026 is a partial year** (through 2026-08-14). Through 2025 only, V0.W shows
  8.1% CAGR / 0.98 Sharpe versus 7.2% / 0.83 including 2026 YTD. The verdict does
  not hinge on it, but the drawdown figures do.
- **Implementation delay costs real money.** Lagging selection 5 days cuts V0.W
  CAGR by 1.21pp (7.2% → 6.0%).
- **Reg-T is infeasible for several variants.** Short 3× ETFs carry 90%
  maintenance under Reg-T. V4/V4.d/V2 require Portfolio Margin.

---

## 8. Adversarial verification

Per the repo's counter-agent rule, findings were attacked before publication
(`verify.py`, results in `fixtures/verification.json`). Seven checks, all passed:

| check | result |
|---|---|
| look-ahead in selection | PASS — lagging selection 5d costs 1.21pp, no collapse |
| survivorship bias | PASS — measured at +0.06pp of fake CAGR |
| stale marks on dead names | PASS — max internal price gap 1 day |
| engine vs closed form | PASS — 4.08%/yr closed form vs 3.54%/yr engine |
| cost monotonicity | PASS — CAGR strictly decreasing in borrow |
| partial-year dependence | PASS — verdict holds through 2025 alone |
| reconstruction artifact | PASS — actual SOXX gives the same short-leg story |

Two engine bugs the adversarial pass caught and fixed before any number shipped:

1. **No margin model.** The engine happily ran a drifted quarterly book at 116×
   gross leverage on 5% equity and reported a Sharpe of 0.25 for it. Forced
   liquidation at maintenance-margin breach now applies; V0.Q's honest result is
   1.5% CAGR / −55.9% maxDD with one margin call.
2. **"Gross" silently meant "earns no interest".** The shadow gross book skipped
   financing entirely, making gross look *worse* than net for credit-balance
   variants. Gross is now a separate zero-friction re-run.

Merge-blocking gate tests freeze every headline number: `python3 -m pytest
soxl-dispersion-lab/tests -q` → **16 passed**.

---

## 9. What I would actually do

1. **Don't run the seed strategy.** 3.1% CAGR at a −41.5% drawdown is worse than
   cash-plus-basket on every axis.
2. **If the goal is neutral semis exposure**, run V0.W (weekly, top-12 slightly
   better) and size it as a ~7% CAGR / 0.67 Sharpe diversifier — not a core book,
   and with the explicit understanding that it is short the melt-up.
3. **If the goal is the decay harvest specifically**, V4.d is the honest
   expression: 1.8% CAGR, 1.8% vol, −3.6% maxDD, and it dies above ~2.5% borrow.
   It is a cash-plus strategy, and it needs Portfolio Margin.
4. **The friend's book is probably fine and about to stop being fine.** If they
   started it in 2023-2025 they have seen 17%, 66%, 12% — and 2026 YTD is −31%.
   That sequence is the strategy working exactly as designed.
