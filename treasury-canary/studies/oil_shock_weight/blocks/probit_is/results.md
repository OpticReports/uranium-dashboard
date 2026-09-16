# probit_is — in-sample probits, conditional cut, oil–curve correlation, Q3 effect-size-by-regime

Inputs: panel.csv (frozen), events.json; sample 1953-04+ (1955-07+ when FF pace enters); resolved months t+h ≤ 2025-08; curve = spread_gs (GS10−TB3MS). Estimator: statsmodels Probit, Newton, maxiter 100; z = Newey–West HAC, maxlags h−1 (naive z never shown). AUC = Mann–Whitney on fitted p (in-sample). All numbers in numbers.json.

## 1. Fits per horizon

### h = 6  (sample end 2025-02; HAC maxlags 5)

| target | spec | oil transform | curve coef (z) | oil coef (z) | FF pace coef (z) | AUC | McFadden R² | n | n_pos |
|---|---|---|---|---|---|---|---|---|---|
| A | (a) curve | — | -0.2839 (-3.25) | — | — | 0.664 | 0.055 | 863 | 166 |
| A | (b) curve+oil | 12m % chg winsorised ±100 | -0.2632 (-3.10) | +0.0065 (+1.90) | — | 0.677 | 0.074 | 863 | 166 |
| A | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.2238 (-2.59) | +0.0277 (+4.53) | — | 0.756 | 0.156 | 863 | 166 |
| A | (c) oil only | 12m % chg winsorised ±100 | — | +0.0076 (+2.26) | — | 0.580 | 0.029 | 863 | 166 |
| A | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0293 (+5.35) | — | 0.709 | 0.127 | 863 | 166 |
| A | (d) curve+FF | — | -0.5156 (-5.00) | — | -0.1791 (-2.61) | 0.725 | 0.100 | 836 | 153 |
| A | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.5238 (-4.91) | +0.0086 (+2.37) | -0.2078 (-2.70) | 0.746 | 0.133 | 836 | 153 |
| A | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.4947 (-4.55) | +0.0294 (+4.99) | -0.2059 (-2.53) | 0.793 | 0.217 | 836 | 153 |
| B | (a) curve | — | -0.6759 (-5.40) | — | — | 0.853 | 0.230 | 750 | 64 |
| B | (b) curve+oil | 12m % chg winsorised ±100 | -0.6812 (-5.66) | +0.0070 (+1.89) | — | 0.851 | 0.243 | 750 | 64 |
| B | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.6288 (-5.39) | +0.0156 (+2.02) | — | 0.859 | 0.246 | 750 | 64 |
| B | (c) oil only | 12m % chg winsorised ±100 | — | +0.0064 (+1.61) | — | 0.589 | 0.017 | 750 | 64 |
| B | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0245 (+3.16) | — | 0.686 | 0.059 | 750 | 64 |
| B | (d) curve+FF | — | -0.7476 (-4.93) | — | -0.0415 (-0.46) | 0.865 | 0.243 | 733 | 60 |
| B | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.7851 (-5.02) | +0.0080 (+2.06) | -0.0640 (-0.66) | 0.868 | 0.260 | 733 | 60 |
| B | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.7290 (-5.08) | +0.0178 (+2.15) | -0.0670 (-0.70) | 0.874 | 0.264 | 733 | 60 |

### h = 12  (sample end 2024-08; HAC maxlags 11)

| target | spec | oil transform | curve coef (z) | oil coef (z) | FF pace coef (z) | AUC | McFadden R² | n | n_pos |
|---|---|---|---|---|---|---|---|---|---|
| A | (a) curve | — | -0.4561 (-3.82) | — | — | 0.746 | 0.124 | 857 | 226 |
| A | (b) curve+oil | 12m % chg winsorised ±100 | -0.4434 (-3.74) | +0.0061 (+1.64) | — | 0.749 | 0.138 | 857 | 226 |
| A | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.4302 (-3.52) | +0.0272 (+2.94) | — | 0.794 | 0.196 | 857 | 226 |
| A | (c) oil only | 12m % chg winsorised ±100 | — | +0.0074 (+2.07) | — | 0.576 | 0.025 | 857 | 226 |
| A | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0288 (+3.89) | — | 0.699 | 0.102 | 857 | 226 |
| A | (d) curve+FF | — | -0.6591 (-4.77) | — | -0.1581 (-2.24) | 0.770 | 0.156 | 830 | 213 |
| A | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.6710 (-4.76) | +0.0076 (+2.01) | -0.1807 (-2.42) | 0.781 | 0.178 | 830 | 213 |
| A | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.6597 (-4.55) | +0.0281 (+3.32) | -0.1749 (-2.27) | 0.809 | 0.234 | 830 | 213 |
| B | (a) curve | — | -0.8545 (-4.41) | — | — | 0.879 | 0.299 | 744 | 124 |
| B | (b) curve+oil | 12m % chg winsorised ±100 | -0.8822 (-4.57) | +0.0084 (+2.10) | — | 0.879 | 0.314 | 744 | 124 |
| B | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.8296 (-4.31) | +0.0166 (+1.31) | — | 0.882 | 0.311 | 744 | 124 |
| B | (c) oil only | 12m % chg winsorised ±100 | — | +0.0062 (+1.54) | — | 0.575 | 0.014 | 744 | 124 |
| B | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0251 (+2.30) | — | 0.672 | 0.048 | 744 | 124 |
| B | (d) curve+FF | — | -0.8337 (-3.63) | — | +0.0212 (+0.19) | 0.881 | 0.304 | 727 | 120 |
| B | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.8853 (-3.61) | +0.0085 (+1.95) | +0.0007 (+0.01) | 0.882 | 0.319 | 727 | 120 |
| B | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.8333 (-3.61) | +0.0167 (+1.29) | -0.0012 (-0.01) | 0.884 | 0.316 | 727 | 120 |

### h = 18  (sample end 2024-02; HAC maxlags 17)

| target | spec | oil transform | curve coef (z) | oil coef (z) | FF pace coef (z) | AUC | McFadden R² | n | n_pos |
|---|---|---|---|---|---|---|---|---|---|
| A | (a) curve | — | -0.5523 (-3.95) | — | — | 0.779 | 0.163 | 851 | 281 |
| A | (b) curve+oil | 12m % chg winsorised ±100 | -0.5451 (-3.90) | +0.0072 (+1.84) | — | 0.786 | 0.182 | 851 | 281 |
| A | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.5362 (-3.66) | +0.0236 (+2.18) | — | 0.808 | 0.211 | 851 | 281 |
| A | (c) oil only | 12m % chg winsorised ±100 | — | +0.0082 (+2.15) | — | 0.577 | 0.029 | 851 | 281 |
| A | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0258 (+3.11) | — | 0.666 | 0.075 | 851 | 281 |
| A | (d) curve+FF | — | -0.7065 (-4.73) | — | -0.1241 (-1.87) | 0.783 | 0.183 | 824 | 268 |
| A | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.7299 (-4.88) | +0.0085 (+2.17) | -0.1496 (-2.25) | 0.794 | 0.208 | 824 | 268 |
| A | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.7023 (-4.46) | +0.0236 (+2.38) | -0.1317 (-1.94) | 0.808 | 0.231 | 824 | 268 |
| B | (a) curve | — | -0.8756 (-3.90) | — | — | 0.874 | 0.305 | 738 | 178 |
| B | (b) curve+oil | 12m % chg winsorised ±100 | -0.9199 (-4.01) | +0.0105 (+2.05) | — | 0.878 | 0.329 | 738 | 178 |
| B | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.8630 (-3.86) | +0.0072 (+0.56) | — | 0.874 | 0.307 | 738 | 178 |
| B | (c) oil only | 12m % chg winsorised ±100 | — | +0.0072 (+1.61) | — | 0.569 | 0.018 | 738 | 178 |
| B | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0196 (+1.69) | — | 0.625 | 0.026 | 738 | 178 |
| B | (d) curve+FF | — | -0.7875 (-3.50) | — | +0.0817 (+0.78) | 0.878 | 0.311 | 721 | 174 |
| B | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.8577 (-3.57) | +0.0100 (+1.87) | +0.0533 (+0.49) | 0.880 | 0.332 | 721 | 174 |
| B | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.7848 (-3.48) | +0.0054 (+0.41) | +0.0742 (+0.71) | 0.878 | 0.312 | 721 | 174 |

### h = 24  (sample end 2023-08; HAC maxlags 23)

| target | spec | oil transform | curve coef (z) | oil coef (z) | FF pace coef (z) | AUC | McFadden R² | n | n_pos |
|---|---|---|---|---|---|---|---|---|---|
| A | (a) curve | — | -0.5873 (-4.17) | — | — | 0.782 | 0.174 | 845 | 335 |
| A | (b) curve+oil | 12m % chg winsorised ±100 | -0.5829 (-4.13) | +0.0076 (+1.88) | — | 0.791 | 0.194 | 845 | 335 |
| A | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.5705 (-3.85) | +0.0201 (+1.79) | — | 0.803 | 0.206 | 845 | 335 |
| A | (c) oil only | 12m % chg winsorised ±100 | — | +0.0084 (+2.13) | — | 0.589 | 0.029 | 845 | 335 |
| A | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0234 (+2.70) | — | 0.655 | 0.059 | 845 | 335 |
| A | (d) curve+FF | — | -0.6803 (-4.51) | — | -0.0830 (-1.17) | 0.781 | 0.184 | 818 | 322 |
| A | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.7028 (-4.63) | +0.0084 (+2.08) | -0.1070 (-1.51) | 0.794 | 0.208 | 818 | 322 |
| A | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.6666 (-4.24) | +0.0196 (+1.87) | -0.0858 (-1.21) | 0.799 | 0.215 | 818 | 322 |
| B | (a) curve | — | -0.7964 (-4.20) | — | — | 0.845 | 0.269 | 732 | 232 |
| B | (b) curve+oil | 12m % chg winsorised ±100 | -0.8249 (-4.28) | +0.0101 (+1.83) | — | 0.853 | 0.292 | 732 | 232 |
| B | (b) curve+oil | NOPI12 = nopi36_sum12 | -0.7900 (-4.24) | +0.0034 (+0.26) | — | 0.846 | 0.269 | 732 | 232 |
| B | (c) oil only | 12m % chg winsorised ±100 | — | +0.0077 (+1.61) | — | 0.585 | 0.020 | 732 | 232 |
| B | (c) oil only | NOPI12 = nopi36_sum12 | — | +0.0172 (+1.42) | — | 0.617 | 0.018 | 732 | 232 |
| B | (d) curve+FF | — | -0.6868 (-3.59) | — | +0.1133 (+1.06) | 0.854 | 0.278 | 715 | 228 |
| B | (e) curve+oil+FF | 12m % chg winsorised ±100 | -0.7355 (-3.65) | +0.0092 (+1.64) | +0.0882 (+0.80) | 0.858 | 0.298 | 715 | 228 |
| B | (e) curve+oil+FF | NOPI12 = nopi36_sum12 | -0.6864 (-3.60) | +0.0005 (+0.04) | +0.1127 (+1.08) | 0.854 | 0.278 | 715 | 228 |

Oil coefficient units: per percentage point of 12m change (winsorised) or per log-pct of NOPI12; FF pace per pp of 12m change in the funds rate.

## 2. Deployed-model check (h = 12, Target A)

| fit | spread basis | sample | labels | b0 | b1 | AUC | n | n_pos |
|---|---|---|---|---|---|---|---|---|
| this block (a) | GS10−TB3MS | 1953-04..2024-08 | resolved | -0.0890 | -0.4561 | 0.746 | 857 | 226 |
| (a) 1982+ | GS10−TB3MS | 1982-01..2024-08 | resolved | -0.5012 | -0.2831 | 0.693 | 512 | 90 |
| (a) 1982+ | T10Y3M monthly mean (deployed basis) | 1982-01..2024-08 | resolved | -0.5217 | -0.2950 | 0.703 | 512 | 90 |
| (a) 1982+, deployed labels | T10Y3M monthly mean | 1982-01..2025-08 | t+12 ≤ last USREC print | -0.5813 | -0.2694 | 0.689 | 524 | 90 |
| LIVE /recession-model | DGS10−DGS3MO daily → monthly mean | 1981-09..2025-08 (inferred from n_obs) | t+12 ≤ last USREC print | -0.5595 | -0.2665 | 0.686 | 528 | 94 |

Reading: the live fit (b0 -0.5595, b1 -0.2665) is reproduced to within |Δb1| = 0.0029 and |Δb0| = 0.0218 by the T10Y3M-basis fit on 1982+ with the deployed labelling (b0 -0.5813, b1 -0.2694); the residual is the 4 months 1981-09..1981-12 (n 524 vs 528, n_pos 90 vs 94: those four months lie inside the 1981-08..1982-11 recession, so under Target A they carry positive labels) that FRED's daily DGS3MO has and the panel's T10Y3M does not, plus daily-mean vs monthly-print rounding. The study's own (a) on GS10−TB3MS from 1953-04 gives a steeper slope (b1 -0.4561): the 1950s–70s add six recessions preceded by shallow inversions on the discount-basis bill series, and the discount basis sits 20–40bp below bond-equivalent, both of which push the slope down. Differences are expected; no agreement is forced.

## 3. Conditional cut (descriptive) and oil–curve correlation

Target B months 1953-04..2024-08, D1-RED ON = WTISPLC 12m % change ≥ +50 with usrec_t = 0.

| cut | n ON months | n with onset within 12 | P(onset within 12) | base rate on same cut (all months) | ON months |
|---|---|---|---|---|---|
| spread_gs > +0.25 (curve not flat) | 43 | 3 | 7.0% | 9.2% | 1987-07, 1999-08, 1999-09, 1999-10, 1999-11, 1999-12, 2000-01, 2000-02, 2000-03, 2000-05, 2000-06, 2002-12, 2003-01, 2003-02, 2004-09, 2004-10, 2004-11, 2007-11, 2009-12, 2010-01, 2010-02, 2010-03, 2010-04, 2017-01, 2017-02, 2018-06, 2018-07, 2021-03, 2021-04, 2021-05, 2021-06, 2021-07, 2021-08, 2021-09, 2021-10, 2021-11, 2021-12, 2022-01, 2022-02, 2022-03, 2022-04, 2022-05, 2022-06 |
| spread_gs ≤ +0.25 (flat/inverted) | 6 | 6 | 100.0% | 54.9% | 1979-08, 1979-09, 1979-10, 1979-11, 1979-12, 1980-01 |
| all D1-RED | 49 | 9 | 18.4% | 16.7% | |

(b) refit on each half (Target B, h = 12):

| cut | oil coef (HAC z) | ΔP +50% oil @ spread 0 | @ +1pp | AUC | n | n_pos |
|---|---|---|---|---|---|---|
| spread_gs > +0.25 | +0.0063 (+1.46) | +12.2pp | +7.3pp | 0.868 | 622 | 57 |
| spread_gs ≤ +0.25 | +0.0207 (+1.84) | +35.4pp | +36.0pp | 0.647 | 122 | 67 |

| regime (signal months) | window | n | corr(oil 12m % w, spread_gs) | corr(oil 12m % unwinsorised, spread_gs) | corr(NOPI12, spread_gs) |
|---|---|---|---|---|---|
| R0 | 1953-04..1985-12 | 393 | -0.362 | -0.351 | -0.343 |
| R1 | 1986-01..2008-12 | 276 | -0.113 | -0.115 | -0.129 |
| R2 | 2009-01..2019-12 | 132 | +0.133 | +0.133 | -0.212 |
| R3 | 2020-01..2026-08 | 80 | +0.625 | +0.584 | +0.285 |
| full | 1953-04..2026-08 | 881 | -0.100 | -0.131 | -0.220 |

Notes: the ≤ +0.25 cut's six D1-RED months are ONE episode (1979-08..1980-01, all inside the 1980-02 lead window) — 100% is one event, not six. The negative oil–curve correlation is concentrated in R0 (1974, 1979–80: oil up while the curve inverted); in R3 it flips to +0.63 (2021–22 oil rose while the curve was still steep, then oil fell as it inverted), which is why the 2022 episode cannot borrow the 1970s' curve confounding. The spec's quoted full-sample −0.13 is on a different window/transform; the frozen panel gives −0.10 winsorised on 1953-04..2026-08.

## 4. Marginal effects — IN-SAMPLE, descriptive (decision-relevant version comes from the walk-forward block)

Target B, h = 12, decision transform. ΔP = Φ(η + β·shock) − Φ(η); delta-method 90% CI from the HAC covariance.

| shock | spec | at spread 0 | at spread +1pp |
|---|---|---|---|
| oil 12m % 0 → +50 | (b) curve+oil | +16.6pp [+3.7, +29.5] | +10.6pp [+1.2, +20.0] |
| oil 12m % 0 → +50 | (e) curve+oil+FF (FF pace 0) | +16.7pp [+2.5, +31.0] | +10.5pp [+0.1, +20.8] |
| FF pace 0 → +300bp | (e) (oil 0) | +0.1pp [-22.4, +22.6] | +0.0pp [-11.6, +11.6] |

Base P at oil 0 from (b): spread 0 → 38.7%, spread +1pp → 12.1%.

## 5. Q3 PRIMARY — effect size by regime (Target B, h = 12, (b) curve + winsorised 12m oil)

| block | sample | n | n_pos | positive-label regions | curve coef (z) | oil coef (HAC z) | ΔP +50% oil @ spread 0 [90%] | @ +1pp | AUC |
|---|---|---|---|---|---|---|---|---|---|
| R0R1 | 1953-04..2007-12 | 564 | 112 | 9: 1953-04..1953-07; 1956-09..1957-08; 1959-05..1960-04; 1969-01..1969-12; 1972-12..1973-11; 1979-02..1981-07; 1989-08..1990-07; 2000-04..2001-03; 2007-01..2007-12 | -1.2177 (-6.39) | +0.0105 (+1.80) | +19.5pp [+2.7, +36.3] | +14.3pp [-0.6, +29.3] | 0.890 |
| R2R3 | 2009-07..2024-08 | 180 | 12 | 1: 2019-03..2020-02 | -0.4769 (-2.08) | -0.0062 (-1.09) | -5.4pp [-14.3, +3.5] | -2.6pp [-6.7, +1.5] | 0.856 |
| full | 1953-04..2024-08 | 744 | 124 | | | +0.0084 (+2.10) | +16.6pp [+3.7, +29.5] | +10.6pp [+1.2, +20.0] | 0.879 |

Sample columns show the first/last non-recession month in each block (Target B drops usrec_t = 1 rows: 2008-01..2009-06 are in recession, so R0+R1 ends 2007-12 and R2+R3 starts 2009-07). R0+R1's first region 1953-04..1953-07 is the 1953-08 onset's lead window truncated by the curve's start.

**Is the R2+R3 fit identified?** NOT IDENTIFIED as an oil effect. n_pos = 12 months, all in 1 contiguous region (2019-03..2020-02) = the 12-month lead window of the single 2020-03 onset. Converged: True; max |coef| 1.131; fitted p range [0.000, 0.433]; oil_12m_pct_w on the positive months ranged -23.7..+20.9; non-zero oil months 180. all positive labels come from a single contiguous 12-month lead window before the 2020-03 onset (one event); the oil coefficient is fitted on one episode's oil path, so its sign and size are that episode's accident, not an effect size.

**§4 test verdict:** R2+R3 point effect <= half of R0+R1 (ratio -0.28), BUT the R2+R3 fit is NOT identified (single 2020 lead window): report as 'unidentified / consistent with <= half', not as a measured shrinkage. Ratio R2+R3 / R0+R1 of ΔP(+50% oil, spread 0) = -0.28.

### Interaction: oil × (energy share − mean), 1959+

Sample 1959-01..2024-08, n 693, n_pos 108, energy-share sample mean 5.83%.

| model | curve (z) | oil (z) | share main (z) | oil×share (HAC z) | AUC |
|---|---|---|---|---|---|
| as written (spec §4) | -0.8516 (-4.29) | +0.0183 (+2.50) | — | +0.0100 (+2.25) | 0.892 |
| + share main effect (robustness, not in spec) | -0.9558 (-5.77) | +0.0174 (+2.32) | +0.2861 (+1.84) | +0.0076 (+1.63) | 0.895 |

Implied ΔP for +50% oil at spread 0 (as-written model): at the 1980-06 share (9.27%) +65.7pp [+48.9, +82.4]; at the sample-mean share (5.83%) +35.2pp [+13.7, +56.8]; at the latest share (3.82%, 2026-07) -3.4pp [-18.6, +11.9].

Caveat on the interaction: the energy share is above 7% only in 1973–85, so oil×share is identified mainly by the 1974 and 1979–80 episodes — the same episodes that carry the R0 oil effect. A positive interaction therefore says 'oil mattered when the share was high (the 1970s)', not that the share is the causal channel; the point estimate at today's share (−3pp) is an extrapolation below the share of every scored onset except 2020-03. Consumption share, not GDP share (§7 P2 #3 open).

### Energy share at each D1-RED episode start (plot-ready)

| episode start | last ON | ON months | oil 12m % at start | spread_gs at start | energy share % at start | next onset | months to it | pending |
|---|---|---|---|---|---|---|---|---|
| 1948-01 | 1948-03 | 3 | +58.6 | n/a | n/a (pre-1959) | 1948-12 | 11 |  |
| 1979-08 | 1980-01 | 6 | +78.5 | -0.49 | 8.28 | 1980-02 | 6 |  |
| 1987-07 | 1987-07 | 1 | +84.5 | +2.76 | 6.12 | 1990-08 | 37 |  |
| 1999-08 | 2000-06 | 10 | +59.1 | +1.22 | 4.47 | 2001-04 | 20 |  |
| 2002-12 | 2003-02 | 3 | +52.2 | +2.84 | 4.43 | 2008-01 | 61 |  |
| 2004-09 | 2004-11 | 3 | +62.4 | +2.48 | 4.84 | 2008-01 | 40 |  |
| 2007-11 | 2007-11 | 1 | +59.4 | +0.88 | 6.01 | 2008-01 | 2 |  |
| 2009-12 | 2010-04 | 5 | +81.1 | +3.54 | 5.61 | 2020-03 | 123 |  |
| 2017-01 | 2017-02 | 2 | +65.7 | +1.92 | 4.02 | 2020-03 | 38 |  |
| 2018-06 | 2018-07 | 2 | +50.2 | +1.01 | 4.43 | 2020-03 | 21 |  |
| 2021-03 | 2022-06 | 16 | +113.4 | +1.58 | 3.85 | — | — |  |
| 2026-04 | 2026-05 | 2 | +57.9 | +0.71 | 4.07 | — | — | yes |

D1-RED ON months inside recessions (excluded from episodes): 1974-01, 1974-02, 1974-03, 1974-04, 1974-05, 1974-06, 1974-07, 1974-08, 1974-09, 1974-10, 1974-11, 1974-12, 1980-02, 1980-03, 1980-04, 1980-05, 1980-06, 1980-07, 1990-09, 1990-10, 1990-11, 2008-01, 2008-02, 2008-03, 2008-04, 2008-05, 2008-06, 2008-07, 2008-08.

## Figures

- `fig_is_coefs.png` — oil coefficient with HAC 90% bars by horizon, (b) vs (e), four panels (transform × target): the oil coefficient is positive and its HAC z is shown next to each point; compare Target A vs B to see how much is coincident (in-recession) information.
- `fig_energy_share.png` — energy share of PCE 1959+ with NBER bands; D1-RED episode starts marked with the share at that month.
- `fig_regime_effect.png` — ΔP for +50% oil at spread 0 by regime block; the R2+R3 point is drawn as a grey X because it rests on one event.
