# Study — the check, the fund, and the angel: odds of making money

VERIFIED after adversarial review, 2026-09-05. Counter-agent verdict:
NOT SAFE AS-IS → SAFE AFTER MANDATORY CORRECTIONS; all six applied
below and marked. Prompted by Casey's thought experiment: "what are my
percentage chances of making money every time I write a check at any
different level" — and then "$2M, twenty $100K checks, which rounds?"

Three different statistics live in this file and MUST NOT be conflated:
per-COMPANY odds, per-FUND odds, per-INVESTOR-PORTFOLIO odds. Under a
power law these have mechanically different shapes. They are presented
in separate sections and belong on separate chart panels (counter-agent
ruling: shared axes here are misleading even with labels).

## 1 · Per check, by stage [MEASURED — in-house calibration]

PitchBook Part IV recovered values (two validation locks; see
series-a-buckets-2026-08-21.md). Count basis, gross, includes tracked
failures (6-years-no-round counted as failure, so the zombie mass is
largely inside `<1x`).

| stage | <1x | 1–5x | 5–10x | 10–50x | >50x | **≥1x (any profit)** |
|---|---|---|---|---|---|---|
| Seed | 81.2 | 8.9 | 3.8 | 4.7 | 1.4 | **18.8%** |
| Series A | 66.0 | 18.4 | 7.1 | 7.0 | 1.4 | **34.0%** |
| Series B | 55.4 | 31.0 | 7.5 | 5.2 | 0.9 | **44.6%** |
| Series C | 50.7 | 37.7 | 7.0 | 4.2 | 0.5 | **49.3%** |
| Series D+ | 48.4 | 44.1 | 5.2 | 1.9 | 0.5 | **51.6%** |

Readings: "break even" is not a state — within <1x, losses cluster near
zero (Hall & Woodward: ~70–75% of companies alive past year five end at
nothing). Series A, not seed, carries the fattest outlier tail (8.4%
≥10x vs 6.1%). Later stages trade tail for base hits.

## 2 · The portfolio bridge [ARITHMETIC, ours — labeled as such, not a source]

Binomial on the measured per-check odds, independent draws (real
portfolios are correlated; truth is somewhat worse):

| checks | P(≥1 ten-bagger) seed/A | P(≥1 profitable) seed/A |
|---|---|---|
| 1 | 6% / 8% | 19% / 34% |
| 10 | 47% / 58% | 88% / 98% |
| 25 | 79% / 89% | ~99% / ~100% |
| 50 | 96% / 99% | ~100% / ~100% |

Catching *a* winner is nearly guaranteed at fund scale; catching one
big enough to pay for the losers plus fees is the whole game — which is
why §3 looks the way it does.

## 3 · Per fund [VERIFIED, net of fees]

- **Kauffman Foundation (2012), the only public fund-by-fund bucket
  table** — 99 funds, vintages 1989–2011, NET, marks as of 12/31/2011
  (mixed realized/interim), ONE selected LP's portfolio:
  **<1x: 50.5% · 1–2x: 33.3% · 2–3x: 10.1% · 3x+: 6.1%.** Mean net
  1.31x. "The average VC fund fails to return investor capital after
  fees" (verbatim). 62 of 100 failed to beat public markets (Russell
  2000 PME) after fees. [CORRECTED scope: "no fund >$500M returned
  >2x" is a statement about *Kauffman's portfolio*, not the universe.]
- **HJKS (Burgiss, n=1,329 US VC funds, NET, marks June 2019; PME
  benchmark S&P 500 — a different benchmark than Kauffman's, flagged):**
  top-quartile average MOIC **4.53x** (IRR 45.3%, PME 2.60);
  bottom-quartile **0.70x** (−8.2%, 0.41). Second-quartile VC also
  beats public markets. Persistence: prior-top-quartile GPs repeat
  top-quartile ~45% of the time ex-post; at-fundraising persistence
  weakens post-2000; first-time funds average PME 1.24.
- **The cash reality (DPI):** 2021-vintage **average DPI 0.05x at ~5
  years** — lowest this century; LP net cash flow **−$202B since 2022**
  [PitchBook, Aug 2026; PitchBook itself later argued the 2021 figure
  is not the warning it looks like — dated citation carried].
  **Carta's own words: "less than 20% of [2017–2018 vintage] funds have
  yet reached a 1x DPI"** at ~7–9 years (platform skews to sub-$100M
  funds). Median 2017-vintage DPI 0.27x as of Q1 2025. Historical time
  to 1x DPI ≈ year 8; year-5 DPI predicts final outcomes weakly
  (corr. 0.22, VenCap).
- **[REFUTED — removed]:** a circulating "90th-percentile funds since
  2017 at ~0.5x DPI" figure is contradicted by Carta's own Q4 2025
  data (2018 vintage 90th-pct DPI = 1.3x) and does not appear here.
- Concentration: FLAG Capital (2005) [SECONDARY, original dead]: 29
  funds (14% of capital) ≈ 51% of industry distributions; the 500+
  others averaged 0.4–0.6x.

## 4 · Per angel [VERIFIED, gross, exited-only — biases run flattering]

Every measured angel universe is SELECTED (group members who chose to
respond; platform investors). No dataset of unselected individual
angels exists. Figures are gross of the angel's time, self-reported,
exits-only.

- **US (Wiltbank/AIPP 2007; 539 angels, 1,137 exits):** average **2.6x
  in 3.5 yrs (~27% gross IRR)**; **52% of exits lost money; ~35% total
  wipeouts**; median check $50K in → **$40K back**; failures resolve
  ~3 yrs, ≥10x exits ~5–6 yrs. **[CORRECTED to the primary]: the top
  10% of exits account for 75% of total cash returned** (NESTA's later
  "90%" is a paraphrase conflict; primary wins). **61% of portfolio
  angels were above 1x overall** — the measured "odds an angel is in
  the black."
- **UK (NESTA 2009; 158 angels, 406 exits):** 2.2x / 3.6 yrs / ~22%
  gross IRR; **56% of exits at a loss** (mostly total); **9% ≥10x
  producing ~80% of the cash returned**.
- **AngelList (Koh & Othman 2020 — MARKED, not realized; platform):**
  median IRR for ≤5-investment portfolios **0.0%** vs 9.1% for >5;
  <50% of ≤3-check investors above 1.0x vs ~90% of 90+-check
  investors; +9.0bp median IRR per additional company. Simulation
  (Othman blog, Dec 2019, labeled SIMULATION): "fewer than 10% of
  investors will beat the index, even if those investors have skill in
  picking deals." Moonfire simulation (their power-law assumptions,
  not empirical): P(fund <1x) → ~0 above ~200 companies; 2x-fund
  probability peaks near 40 companies under a 50x single-deal cap.

## 5 · The $2M / 20-check allocation [SIMULATION, ours — 100k runs per
## mix, calibrated stage curves, 50x single-deal cap, independence]

| allocation | E[mult] | median | P(<1x) | P(≥2x) | P(≥3x) |
|---|---|---|---|---|---|
| 20 seed (direct) | 2.44 | 2.04 | 21.2% | 50.8% | 33.1% |
| **20 Series A (via SPV, 20% carry)** | **2.87** | **2.63** | **4.6%** | **66.8%** | **40.8%** |
| 20 Series A (if direct) | 3.44 | 3.14 | 2.8% | 76.0% | 52.7% |
| 10 seed + 10 A(SPV) | 2.66 | 2.34 | 11.2% | 58.1% | 35.8% |
| 6 seed + 10 A(SPV) + 4 B(SPV) | 2.64 | 2.34 | 9.2% | 58.8% | 35.2% |
| 20 Series B (via SPV) | 2.35 | 2.07 | 8.7% | 52.1% | 26.2% |

Series A dominates seed on EVERY metric even after 20% carry — direct
consequence of the measured buckets (lower loss AND fatter tail).
Carry costs ~0.57x of E[mult] between direct and SPV A (~$1.1M on
$2M): access quality outweighs stage tinkering. Recommended: ~12 A
(cleanest access first) + ~6 seed (only with genuine information edge
— AngelList: index beats picking at seed absent edge) + ~2 reserved
follow-ons into own winners (the small check's one structural
information advantage). UNMODELED, honest: adverse selection — the A
rounds that want $100K angel checks skew toward those institutions
passed on; that is why access is the first-order variable. Even the
best row has p5 ≈ 1.0x: perfect construction buys the distribution,
never the outcome.

## Basis-mismatch disclosure (counter-agent item 9 — travels with any chart)

Net vs gross; marked vs realized; exited-only vs tracked-universe vs
everything; selected samples throughout; different vintages/regimes;
per-company vs per-fund vs per-investor units; two different PME
benchmarks (Russell 2000 / S&P 500); 3.5-yr angel holds vs 10–15-yr
fund lives make multiples non-comparable as rates. RULED MISLEADING
EVEN WITH LABELS (never on one axis): angel gross-exited 2.6x vs fund
net means; the three "% losing money" units on a shared axis;
simulations interleaved with empirical frequencies; marked
"in-the-money" shares vs realized DPI shares.

## The three-line answer to the thought experiment

1. **Per check:** ~1-in-5 profitable at seed, ~1-in-3 at A, coin-flip
   by C — and <1x mostly means zero.
2. **Per fund:** half lose money net; a quarter of professional funds
   return <0.70x; cash comes back around year 8, if ever.
3. **Per angel:** 61% of *portfolio* angels finish above water; below
   ~5 checks the median outcome is ~0% IRR; the asset class's profit
   lives in the ~1-in-10 exits producing 75–80% of all cash.
