# BLOCK regime_petro — results (spec v1, run 2026-09-15)

Inputs: frozen `panel.csv`, `events.json`, `tic_oil_exporters.csv`. Everything here is DESCRIPTIVE under §4/§5 except the H4a/H4b sign tests, whose outcomes move certainty/glossary wording only (never a weight). Colour assignments in this block's figures: oil = orange, seg1 share = blue, seg2 share = magenta, Norway share = yellow, custody = aqua, oil–USD correlation = violet.

## 1. D1-RED episodes (§4 rule, matches the event block)

| start | raw span (all ON) | n ON (USREC=0) | peak | regime | outcome h=12 | event |
|---|---|---|---|---|---|---|
| 1948-01 | 1948-01..1948-03 | 3 | 58.6 | R0 | NOT SCORED (BEFORE COMMON WINDOW 1953-04) | — |
| 1974-01 (in-recession) | 1974-01..1974-12 | 0 | 184.0 | R0 | COINCIDENT | coincident with 1973-12 |
| 1979-08 | 1979-08..1980-07 | 6 | 149.2 | R0 | HIT | 1980-02 |
| 1987-07 | 1987-07..1987-07 | 1 | 84.5 | R1 | FALSE POSITIVE | — |
| 1990-09 (in-recession) | 1990-09..1990-11 | 0 | 78.8 | R1 | COINCIDENT | coincident with 1990-08 |
| 1999-08 | 1999-08..2000-06 | 10 | 144.4 | R1 | HIT | 2001-04 |
| 2002-12 | 2002-12..2003-02 | 3 | 73.0 | R1 | FALSE POSITIVE | — |
| 2004-09 | 2004-09..2004-11 | 3 | 75.2 | R1 | FALSE POSITIVE | — |
| 2007-11 | 2007-11..2008-08 | 1 | 98.5 | R1 | HIT | 2008-01 |
| 2009-12 | 2009-12..2010-04 | 5 | 95.1 | R2 | FALSE POSITIVE | — |
| 2017-01 | 2017-01..2017-02 | 2 | 76.4 | R2 | FALSE POSITIVE | — |
| 2018-06 | 2018-06..2018-07 | 2 | 52.2 | R2 | FALSE POSITIVE | — |
| 2021-03 | 2021-03..2022-06 | 16 | 272.9 | R3 | FALSE POSITIVE | — |
| 2026-04 | 2026-04..2026-05 | 2 | 64.3 | R3 | PENDING | — |

Two episodes (1974-01, 1990-09) have no USREC=0 ON month; they are kept in the classification table under their raw first ON month because they are the narrative anchor supply shocks, and carry the event block's COINCIDENT outcome. 1948-01 lies before the 1953-04 common window and is not scored.

## 2. Supply vs demand (descriptive; cannot trigger a §5 action)

Rule: supply-driven iff the episode start is within 3 months after a pre-listed disruption (d ≤ start ≤ d+3); otherwise demand-driven; 2026 unclassified pending Casey (P1 #2). IGREA cross-check: `igrea_12m_chg` at the start vs the median of the trailing 120 months (min 60) — above = demand-consistent.

| episode | regime | narrative class | basis | IGREA 12m chg | trailing-10y median (n) | IGREA class | agree? | outcome h=12 |
|---|---|---|---|---|---|---|---|---|
| 1948-01 | R0 | demand | no pre-listed disruption in the 3 months before | — | — | n/a (IGREA starts 1968) | n/a | NOT SCORED (BEFORE COMMON WINDOW 1953-04) |
| 1974-01 (in-recession) | R0 | supply | OPEC embargo 1973-10 (+3m) | +84.9 | +12.7 (61) | demand-consistent | no | COINCIDENT |
| 1979-08 | R0 | demand | no pre-listed disruption in the 3 months before; nearest prior = Iranian revolution 1978-11 (9m earlier) | +63.3 | +8.8 (120) | demand-consistent | yes | HIT 1980-02 |
| 1987-07 | R1 | demand | no pre-listed disruption in the 3 months before; nearest prior = Iran-Iraq war 1980-09 (82m earlier) | +47.3 | -5.0 (120) | demand-consistent | yes | FALSE POSITIVE |
| 1990-09 (in-recession) | R1 | supply | Kuwait invasion 1990-08 (+1m) | -22.6 | -5.8 (120) | supply-consistent | yes | COINCIDENT |
| 1999-08 | R1 | demand | no pre-listed disruption in the 3 months before; nearest prior = Kuwait invasion 1990-08 (108m earlier) | +26.7 | -7.6 (120) | demand-consistent | yes | HIT 2001-04 |
| 2002-12 | R1 | supply | Venezuela strike 2002-12 (+0m) | +64.5 | -5.8 (120) | demand-consistent | no | FALSE POSITIVE |
| 2004-09 | R1 | demand | no pre-listed disruption in the 3 months before; nearest prior = Iraq war 2003-03 (18m earlier) | +51.4 | +10.7 (120) | demand-consistent | yes | FALSE POSITIVE |
| 2007-11 | R1 | demand | no pre-listed disruption in the 3 months before; nearest prior = Iraq war 2003-03 (56m earlier) | +90.0 | +16.7 (120) | demand-consistent | yes | HIT 2008-01 |
| 2009-12 | R2 | demand | no pre-listed disruption in the 3 months before; nearest prior = Iraq war 2003-03 (81m earlier) | +156.2 | +26.1 (120) | demand-consistent | yes | FALSE POSITIVE |
| 2017-01 | R2 | demand | no pre-listed disruption in the 3 months before; nearest prior = Libya 2011-02 (71m earlier) | +84.9 | -20.4 (120) | demand-consistent | yes | FALSE POSITIVE |
| 2018-06 | R2 | demand | no pre-listed disruption in the 3 months before; nearest prior = Libya 2011-02 (88m earlier) | +44.4 | -20.4 (120) | demand-consistent | yes | FALSE POSITIVE |
| 2021-03 | R3 | demand | no pre-listed disruption in the 3 months before; nearest prior = Abqaiq attack 2019-09 (18m earlier) | +120.5 | -12.8 (120) | demand-consistent | yes | FALSE POSITIVE |
| 2026-04 | R3 | unclassified pending Casey | 2026 event not yet named (P1 #2) | +56.6 | +6.2 (120) | demand-consistent | n/a | PENDING |

**Hits by class (h = 12, common window):**

| class | n | hit | false positive | coincident | pending | episodes |
|---|---|---|---|---|---|---|
| supply | 3 | 0 | 1 | 2 | 0 | 1974-01 (in-recession), 1990-09 (in-recession), 2002-12 |
| demand | 9 | 3 | 6 | 0 | 0 | 1979-08, 1987-07, 1999-08, 2004-09, 2007-11, 2009-12, 2017-01, 2018-06, 2021-03 |
| unclassified pending Casey | 1 | 0 | 0 | 0 | 1 | 2026-04 |

Plainly: with 3 supply-classified and 9 demand-classified episodes in the window, n is far too small for any inference about supply vs demand shocks and recession odds; this table is a description, not a test. Note what the mechanical rule does: the 1979-08 episode is DEMAND by the rule (WTISPLC crossed +50 nine months after the 1978-11 Iranian revolution — the regulated series lags), and the 2021-03 episode is DEMAND by the rule (it began eleven months BEFORE the 2022-02 invasion, in the post-COVID demand recovery); the IGREA cross-check reads both the same way.

## 3. R3 descriptive tests

### 3(i) corr(oil 12m %, broad-USD 12m %) by regime — this IS H4b (transmission)

Months where both exist; Pearson and Spearman; moving-block bootstrap (block 12, 1,000 draws, seed 20260915) 90% CI. Pre-stated supporting signs: R1, R2 negative (net importer), R3 positive (net exporter).

| regime | months | n | Pearson [90% CI] | Spearman [90% CI] | pre-stated sign | verdict (Pearson) | verdict (Spearman) |
|---|---|---|---|---|---|---|---|
| R1 | 1986-01..2008-12 | 276 | -0.08 [-0.42, +0.12] | -0.17 [-0.43, +0.05] | negative | **CI straddles zero** | CI straddles zero |
| R2 | 2009-01..2019-12 | 132 | -0.79 [-0.87, -0.51] | -0.74 [-0.87, -0.46] | negative | **supported** | supported |
| R3 | 2020-01..2026-08 | 80 | -0.26 [-0.53, +0.36] | -0.08 [-0.41, +0.44] | positive | **CI straddles zero** | CI straddles zero |

### 3(ii) corr(oil 12m %, Fed custody 12m %) by regime — descriptive only (custody reported from 2007-07 in the frozen WMTSECL1 — earlier prints are 0 and treated as missing; finite 12m changes from 2008-07)

| regime | months | n | Pearson [90% CI] | Spearman [90% CI] | pre-stated sign | verdict (Pearson) | verdict (Spearman) |
|---|---|---|---|---|---|---|---|
| R2 | 2009-01..2019-12 | 132 | +0.01 [-0.12, +0.59] | +0.19 [-0.02, +0.60] | negative | CI straddles zero | CI straddles zero |
| R3 | 2020-01..2026-08 | 80 | +0.43 [-0.17, +0.72] | +0.19 [-0.18, +0.60] | positive | CI straddles zero | CI straddles zero |

Custody is ALL foreign official holdings (oil exporters are a small share, and Gulf holdings via European custodians are unobserved) — a null here is weak evidence either way.

**Named episode 2014-16 oil crash (2014-06..2016-02):** WTI -71%, custody 2973 → 2945 $bn (-1.0%), seg2 share 2.92 → 3.45%.

| month | WTI $ | oil 12m % | custody $bn | custody 12m % | seg2 share % | Norway share % |
|---|---|---|---|---|---|---|
| 2014-06 | 105.8 | +10 | 2973 | +0.4 | 2.92 | 1.45 |
| 2014-07 | 103.6 | -1 | 2976 | +1.4 | 2.95 | 1.41 |
| 2014-08 | 96.5 | -9 | 2997 | +2.5 | 3.04 | 1.43 |
| 2014-09 | 93.2 | -12 | 3018 | +3.1 | 3.25 | 1.35 |
| 2014-10 | 84.4 | -16 | 2979 | +1.0 | 3.36 | 1.27 |
| 2014-11 | 75.8 | -19 | 2979 | +0.2 | 3.28 | 1.22 |
| 2014-12 | 59.3 | -39 | 2974 | -1.3 | 3.33 | 1.33 |
| 2015-01 | 47.2 | -50 | 2954 | -1.3 | 3.38 | 1.18 |
| 2015-02 | 50.6 | -50 | 2935 | -1.1 | 3.49 | 1.19 |
| 2015-03 | 47.8 | -53 | 2908 | -0.1 | 3.47 | 1.16 |
| 2015-04 | 54.5 | -47 | 2963 | +0.2 | 3.43 | 1.09 |
| 2015-05 | 59.3 | -42 | 2992 | +1.8 | 3.43 | 1.06 |
| 2015-06 | 59.8 | -43 | 3025 | +1.7 | 3.44 | 1.09 |
| 2015-07 | 50.9 | -51 | 3009 | +1.1 | 3.50 | 1.09 |
| 2015-08 | 42.9 | -56 | 3019 | +0.7 | 3.52 | 1.14 |
| 2015-09 | 45.5 | -51 | 3008 | -0.3 | 3.50 | 1.14 |
| 2015-10 | 46.2 | -45 | 2981 | +0.1 | 3.55 | 1.16 |
| 2015-11 | 42.4 | -44 | 2984 | +0.2 | 3.50 | 1.14 |
| 2015-12 | 37.2 | -37 | 3000 | +0.8 | 3.58 | 1.12 |
| 2016-01 | 31.7 | -33 | 2960 | +0.2 | 3.58 | 1.10 |
| 2016-02 | 30.3 | -40 | 2945 | +0.4 | 3.45 | 1.12 |

**Named episode 2022 shock (2022-02..2022-12):** WTI -17%, custody 3050 → 2903 $bn (-4.8%), seg2 share 2.78 → 3.15%.

| month | WTI $ | oil 12m % | custody $bn | custody 12m % | seg2 share % | Norway share % |
|---|---|---|---|---|---|---|
| 2022-02 | 91.6 | +55 | 3050 | -1.4 | 2.78 | 1.56 |
| 2022-03 | 108.5 | +74 | 3035 | -2.8 | 2.74 | 1.53 |
| 2022-04 | 101.8 | +65 | 3036 | -2.4 | 2.74 | 1.55 |
| 2022-05 | 109.5 | +68 | 3012 | -2.6 | 2.69 | 1.47 |
| 2022-06 | 114.8 | +61 | 2992 | -3.4 | 2.77 | 1.52 |
| 2022-07 | 101.6 | +40 | 2964 | -4.0 | 2.84 | 1.50 |
| 2022-08 | 93.7 | +38 | 2985 | -2.6 | 2.95 | 1.48 |
| 2022-09 | 84.3 | +18 | 2972 | -2.7 | 3.02 | 1.37 |
| 2022-10 | 87.5 | +7 | 2919 | -4.8 | 3.15 | 1.34 |
| 2022-11 | 84.4 | +7 | 2901 | -5.2 | 3.23 | 1.36 |
| 2022-12 | 76.4 | +7 | 2903 | -4.2 | 3.15 | 1.28 |

### 3(iii) 12-month-ahead response of INDPRO and PAYEMS: the 2021–22 episode vs R0/R1 supply-classified episodes

% change from the episode's first ON month to +12 (INDPRO is revised data — context only).

| episode | regime | narrative class | window | INDPRO 12m % | PAYEMS 12m % | outcome h=12 |
|---|---|---|---|---|---|---|
| **1974-01 (in-recession)** | R0 | supply | 1974-01→1975-01 | -9.1 | -1.0 | COINCIDENT |
| **1990-09 (in-recession)** | R1 | supply | 1990-09→1991-09 | -1.2 | -1.1 | COINCIDENT |
| **2002-12** | R1 | supply | 2002-12→2003-12 | +2.0 | +0.1 | FALSE POSITIVE |
| **2021-03** | R3 | demand | 2021-03→2022-03 | +3.1 | +4.9 | FALSE POSITIVE |
| R0/R1 supply mean (range), n=3 | | | | -2.8 (-9.1 to +2.0) | -0.7 (-1.1 to +0.1) | |

Context — every other D1-RED episode (not part of the comparison):

| episode | regime | narrative class | window | INDPRO 12m % | PAYEMS 12m % | outcome h=12 |
|---|---|---|---|---|---|---|
| 1948-01 | R0 | demand | 1948-01→1949-01 | -1.3 | -0.0 | NOT SCORED (BEFORE COMMON WINDOW 1953-04) |
| 1979-08 | R0 | demand | 1979-08→1980-08 | -5.3 | -0.2 | HIT |
| 1987-07 | R1 | demand | 1987-07→1988-07 | +5.0 | +3.2 | FALSE POSITIVE |
| 1999-08 | R1 | demand | 1999-08→2000-08 | +3.1 | +2.1 | HIT |
| 2004-09 | R1 | demand | 2004-09→2005-09 | +1.7 | +1.9 | FALSE POSITIVE |
| 2007-11 | R1 | demand | 2007-11→2008-11 | -8.7 | -2.0 | HIT |
| 2009-12 | R2 | demand | 2009-12→2010-12 | +6.0 | +0.8 | FALSE POSITIVE |
| 2017-01 | R2 | demand | 2017-01→2018-01 | +2.7 | +1.4 | FALSE POSITIVE |
| 2018-06 | R2 | demand | 2018-06→2019-06 | -0.7 | +1.3 | FALSE POSITIVE |
| 2026-04 | R3 | unclassified pending Casey | 2026-04→2027-04 | — | — | PENDING |

Read: the 2021–22 episode's 12-month path (+3.1 INDPRO, +4.9 PAYEMS) sits at the top of the R0/R1 supply range (mean -2.8 / -0.7). Three comparison episodes; the 1974-01 and 1990-09 starts are already inside recessions, which mechanically depresses their 12m paths. Descriptive.

## 4. H4a — recycling (oil up ⇒ oil-exporter Treasury demand up)

Non-overlapping annual observations = last available month of each year (all Decembers); y = 12m change in share of the TIC grand total (pp), x = WTISPLC 12m % change over the same Dec→Dec window. seg1 = TIC 'Oil Exporters' aggregate 2000-03..2011-12; seg2 = Saudi+UAE+Kuwait 2012-01+; Norway separate, never summed. The pre-stated test is the SIGN only (p-values are shown for scale, not as a test).

| segment | obs | n | Pearson (p) | Spearman (p) | sign |
|---|---|---|---|---|---|
| seg1 | 2001-12..2011-12 | 11 | -0.12 (0.73) | -0.05 (0.87) | Pearson -, Spearman - |
| seg2 | 2013-12..2025-12 | 13 | -0.42 (0.15) | -0.39 (0.19) | Pearson -, Spearman - |
| norway | 2004-12..2025-12 | 20 | -0.06 (0.79) | -0.08 (0.73) | Pearson -, Spearman - |

- Leg 1 (seg1 sign > 0): Pearson -0.12 → **FAIL** (Spearman -0.05 → fail)
- Leg 2 (seg2 sign > 0): Pearson -0.42 → **FAIL** (Spearman -0.39 → fail)
- Leg 3 (seg2 share rose over the 12 months to 2022-12): 2.717% → 3.151% = +0.434pp → **PASS**
- **H4a verdict: recycling link NOT supported in the last shock** (Pearson legs); on Spearman legs: recycling link NOT supported in the last shock.
- Norway (separate): Pearson -0.06, Spearman -0.08, n = 20; Norway share 2021-12→2022-12 +0.009pp.
- 2014–16 named-episode read (oil -71% 2014-06→2016-02): seg2 share 2.92% → 3.45% (+0.52pp; peak 3.58% in 2015-12, trough 2.92% in 2014-06), Saudi+UAE+Kuwait $bn 176 → 215; Norway share 1.45% → 1.12%.

Annual observations (seg1 / seg2 / Norway):

| seg1 month | share % | Δshare 12m (pp) | oil 12m % |
|---|---|---|---|
| 2001-12 | 4.50 | -0.20 | -32 |
| 2002-12 | 4.01 | -0.48 | +52 |
| 2003-12 | 2.80 | -1.22 | +9 |
| 2004-12 | 3.36 | +0.56 | +35 |
| 2005-12 | 3.85 | +0.49 | +37 |
| 2006-12 | 5.24 | +1.40 | +4 |
| 2007-12 | 5.87 | +0.62 | +48 |
| 2008-12 | 6.05 | +0.19 | -55 |
| 2009-12 | 5.46 | -0.59 | +81 |
| 2010-12 | 4.80 | -0.66 | +20 |
| 2011-12 | 5.21 | +0.41 | +11 |

| seg2 month | share % | Δshare 12m (pp) | oil 12m % |
|---|---|---|---|
| 2013-12 | 2.53 | -0.15 | +11 |
| 2014-12 | 3.33 | +0.81 | -39 |
| 2015-12 | 3.58 | +0.24 | -37 |
| 2016-12 | 3.20 | -0.38 | +40 |
| 2017-12 | 3.90 | +0.69 | +11 |
| 2018-12 | 4.31 | +0.41 | -14 |
| 2019-12 | 3.85 | -0.45 | +21 |
| 2020-12 | 3.04 | -0.81 | -21 |
| 2021-12 | 2.72 | -0.33 | +53 |
| 2022-12 | 3.15 | +0.43 | +7 |
| 2023-12 | 3.05 | -0.10 | -6 |
| 2024-12 | 3.07 | +0.02 | -2 |
| 2025-12 | 3.36 | +0.28 | -17 |

| norway month | share % | Δshare 12m (pp) | oil 12m % |
|---|---|---|---|
| 2004-12 | 1.22 | +0.88 | +35 |
| 2007-12 | 1.11 | -0.39 | +48 |
| 2008-12 | 0.75 | -0.36 | -55 |
| 2009-12 | 0.33 | -0.42 | +81 |
| 2010-12 | 0.44 | +0.12 | +20 |
| 2011-12 | 1.13 | +0.69 | +11 |
| 2012-12 | 1.35 | +0.21 | -10 |
| 2013-12 | 1.51 | +0.16 | +11 |
| 2014-12 | 1.32 | -0.18 | -39 |
| 2015-12 | 1.12 | -0.20 | -37 |
| 2016-12 | 0.88 | -0.25 | +40 |
| 2017-12 | 0.82 | -0.05 | +11 |
| 2018-12 | 1.35 | +0.53 | -14 |
| 2019-12 | 1.32 | -0.04 | +21 |
| 2020-12 | 1.24 | -0.08 | -21 |
| 2021-12 | 1.27 | +0.03 | +53 |
| 2022-12 | 1.28 | +0.01 | +7 |
| 2023-12 | 1.75 | +0.48 | -6 |
| 2024-12 | 1.83 | +0.07 | -2 |
| 2025-12 | 2.25 | +0.42 | -17 |

## 5. H4b — transmission (verdict lines)

- H4b oil-USD R1: r = -0.08 [-0.42, +0.12] (pre-stated negative) -> CI straddles zero
- H4b oil-USD R2: r = -0.79 [-0.87, -0.51] (pre-stated negative) -> supported
- H4b oil-USD R3: r = -0.26 [-0.53, +0.36] (pre-stated positive) -> CI straddles zero
- H4b oil-custody R2 (descriptive): r = +0.01 [-0.12, +0.59] -> CI straddles zero vs sign negative
- H4b oil-custody R3 (descriptive): r = +0.43 [-0.17, +0.72] -> CI straddles zero vs sign positive
- **H4b headline (R3): thesis not supported in the current regime.** Signs are findings; magnitudes are not. §5 consequence: `demand_strike` certainty string and glossary wording only, never a weight.

## 6. Figures

- `fig5_petrodollar.png` — Fig 5: three stacked panels (oil 12m %, oil-exporter share seg1/seg2/Norway as three separate lines, Fed custody $bn) 2000–2026 with NBER bands and the 2014–16 / 2022 named episodes shaded; the seg2 share rises through 2022 while custody falls.
- `fig6_oil_usd_corr.png` — Fig 6: per-regime oil–USD (violet) and oil–custody (aqua) correlations with 90% block-bootstrap bars, Spearman as hollow diamonds, verdict by marker shape and label, pre-stated sign printed under each regime.

## 7. Caveats (one line each)

- Supply/demand split: mechanical narrative rule + IGREA; 12 scoreable episodes, 3 supply — description only.
- IGREA trailing-10-year median uses a 120-month window ending at the start month, min 60 months (1974-01 window has 61 months).
- H4a: TIC = custodian country; Gulf holdings via Belgium/UK/Cayman/Luxembourg unobserved, recycling under-stated; Dec→Dec share changes cross a June benchmark revision inside seg1 (2002–2011) because the spec's n≈11 annual design requires it; n = 11 / 13 / 20 (Norway: TIC does not list Norway in 2005, so the 2005-12 and 2006-12 annual observations do not exist).
- H4b: R3 has 80 months = ~7 independent 12-month blocks; custody is all-foreign-official; usd_broad is a ratio-splice at 2006.
- 3(iii): INDPRO is revised; the 1974-01 and 1990-09 supply starts are in-recession months.
