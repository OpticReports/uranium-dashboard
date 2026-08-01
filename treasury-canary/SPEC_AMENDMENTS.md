# SPEC_AMENDMENTS.md — DRAFT (counter-agent pass, 2026-08-01)

Adversarial-quant review per spec §9. All numbers below were re-derived empirically
(FRED + FMP, scripts in scratchpad `qa_spec/`). Two-stage architecture and validation
gates untouched per mandate. Data window caveats in §D at the end.

**Headline: the spec's §4.3 defaults fail its own gate G1 by a factor of ~15
(median SPX −1.4% vs required −18..−30% on the 2022 replay). Three parameters
(β_dur, ρ, logistic a/b) require amendment before any implementation; the amended
set passes G1 arithmetic. Details in A4/A7.**

---

## A1. κ = 0.45 front-to-long pass-through — **ACCEPT 0.45 as central value; AMEND to term-premium-state formula**

Cumulative Δ10y/Δ2y over the five hiking episodes (FRED DGS2/DGS10, daily):

| Episode | Δ2y | Δ10y | κ (total) | ΔTP (ACM, THREEFYTP10) |
|---|---|---|---|---|
| 1994-95 | +291bp | +172bp | 0.59 | +35bp |
| 1999-00 | +136bp | +62bp | 0.46 | +3bp |
| 2004-06 | +251bp | +60bp | 0.24 | −45bp |
| 2015-18 | +161bp | +47bp | 0.29 | −16bp |
| 2022-23 | +287bp | +167bp | 0.58 | −14bp |

Mean 0.43, range [0.24, 0.59] — **0.45 is exactly the right central value** for the
cumulative-surprise mapping the spec uses. (Note: 60-day rolling OLS betas run
0.67–1.30 because short-window co-movement is level-factor dominated; the episode-total
ratio is the correct analog of the spec's κ·S construct. Do not "fix" κ upward from
high-frequency regressions.)

Episode κ correlates with the term-premium path: κ_total = 0.46 + 0.42·ΔTP(pp),
R² = 0.58 (n = 5 — weak but economically sensible: Greenspan-conundrum episodes had
falling TP and κ≈0.25; 1994 had rising TP and κ≈0.6).

**Amended formula:** `κ_t = clip(0.45 + 0.40 · Δacm_tp10_6m, 0.25, 0.65)` where
Δacm_tp10_6m is the trailing 6-month change in the bundle's acm_tp10 (pp). Source tag:
estimated (n=5 episodes) — keep the ±[0.25, 0.65] plausible range in params.json and
surface κ in the tornado.

## A2. OAS sign, early-cycle hikes — **ACCEPT sign; AMEND magnitude −8 → −4bp/priced hike, tapering to 0 late-cycle**

FRED OAS is unusable for 2015-18 (see §D). Proxy: Moody's Baa−Aaa (BAA10Y−AAA10Y,
full history), scaled to HY OAS via the 2023-26 overlap: HY_OAS ≈ 149 + 2.43·BaaAaa
(R² = 0.71).

Per-hike 60-business-day spread changes across the nine 2015-18 hikes: mean +1.2bp
Baa−Aaa (median 0). But phase matters: early hikes tightened (Dec-15 −7, Dec-16 −13bp
≈ −17/−32bp HY-equivalent), late-2018 hikes widened (+13, +21bp). Cumulative
2016-06→2018-09 (7 hikes): −11bp Baa−Aaa ≈ **−3.8bp HY OAS per priced hike**.

Verdict: the spec's sign (priced hikes tighten spreads early-cycle) **verifies**; the
−8bp magnitude is ~2x too big as an average. Amend to **−4bp/priced hike (range −10..0)**
and taper linearly to 0 once cumulative hikes-delivered ≥ 4 in the episode. Judgment tag
on the taper; estimate tag on −4.

## A3. 2-state vs 3-state Markov — **ACCEPT 2-state; no third state**

2022 was a grind, not a gap: Baa−Aaa trough-to-peak +59bp over **212 business days**,
max 5-day move 27% of the total. Contrast 2020 (gap regime): +120bp in **31 days**,
60% of it in one 5-day window.

But the 2-state spec already generates the 2022 grind through the normal-state drift
term: 2022 ≈ 450bp surprise = 18 surprise-hikes × 15bp = **+270bp** — matching the
realized 2022 HY widening (~310→580 trough-to-peak) almost exactly. Stress state then
correctly represents the gap regime (2020-style). A third state would add ≥4 judgment
parameters with no data to pin them. Keep +15bp/surprise-hike as specced.

**One guard required:** in a 2022-replay the amended logistic (A7) puts P(stress)≈1,
so grind (+270) and jump (+120) both fire. Checked: HYG median = −3.2·2.02 −
3.5·(2.70+1.20) + carry 6.0 = **−14.2%**, inside G1's −8..−15%. No double-count fix
needed, but G1 must be re-checked if the jump size is ever raised.

## A4. β_dur — **AMEND upward: SPX 5.5→8, QQQ 7.5→11, SOXX 9.0→14 per 100bp real surprise**

Monthly log returns on ΔDFII10 (FMP prices, FRED DFII10):

| Asset | pooled 2013-26 | 2022-only | 2013-19 | 2020-26 | rolling-36m range |
|---|---|---|---|---|---|
| ^GSPC | −8.1 (se 1.4) | −13.3 (se 2.9) | −0.9 (se 2.1) | −11.9 (se 1.8) | [−13.8, +0.4] |
| QQQ | −10.7 (se 1.7) | −15.7 (se 3.8) | −2.0 (se 2.6) | −15.1 (se 2.2) | [−18.7, −0.3] |
| SOXX | −13.2 (se 2.7) | −24.7 (se 5.3) | +0.9 (se 3.6) | −20.5 (se 3.8) | [−24.1, +5.0] |

The spec's worry was backwards: 2022 does overstate vs pooled, but the **spec defaults
understate vs every post-2020 estimate**. 2013-19 betas ≈ 0 because ΔDFII10 then was
growth-news-driven (yields up = good news), offsetting the discount-rate effect; the
simulator's scenarios are *pure policy surprises*, for which the post-2020 estimates
are the right identification. Recommend the 2020-26 column, rounded down slightly for
the 2022 multiple-compression confound:

- **SPX 8.0** (range 4–14), **QQQ 11.0** (range 5–19), **SOXX 14.0** (range 6–25),
  per 100bp real surprise. Source tag: estimated. All three must be in the tornado —
  the ranges are wide and R² ≤ 0.20.

## A5. AI-capex proxy: SOXX vs custom basket — **ACCEPT SOXX**

SOXX-QQQ monthly corr 0.83, SOXX-on-QQQ beta 1.29; SOXX real-rate beta 1.3–1.6× QQQ's
(A4). SOXX is a distinct, more rate/capex-levered exposure, resolves cleanly on FMP
(2006-, single symbol, no weight maintenance, no survivorship curation). A custom
basket adds maintenance burden and backfill bias for at most marginal fidelity.
(SMH also resolves as a fallback.)

## A6. Copula — **AMEND: t-copula (ν=4, shared mixing variable), per the spec's own >20% rule**

Simulated joint 5th-percentile co-crash probability, t(4) marginals, N=4M:

| ρ | Gaussian copula | t(4) copula | difference |
|---|---|---|---|
| 0.60 (normal) | 1.56% | 2.02% | **+29%** |
| 0.85 (stress) | 2.81% | 3.15% | +12% |

The normal regime — where the sim spends most of its time — breaches the 20% threshold.
Implementation cost is one line (divide the correlated normals by √(W/ν), W~χ²_ν shared
across assets). Switch.

## A7. Other §4 errors found

1. **Logistic stress-entry (a=−4.0, b=3.5) contradicts §4.2's own calibration targets —
   AMEND to a=−4.65, b=2.6.** With 11 monthly steps and priced path ≈ 29bp
   (0.70·25+0.45·25), spec defaults give P(stress by Q2'27): 1 hike 16% (target 8-12%),
   4 hikes **89%** (target 35-50%). Amended a=−4.65, b=2.6/100bp gives: 0h 4.8%,
   1h 9.1%, 2h 16.6%, 3h 29.2%, 4h 47.8% — inside both bands except 3h slightly low,
   which the canary term (c·composite > 0 in realistic states) closes. Note the targets
   themselves are near-inconsistent for a single logistic: 3h and 4h differ by only
   25bp of CS.
2. **Real share ρ=0.7 is wrong for hike surprises — AMEND ρ 0.7→0.9 (range 0.7–1.1).**
   2022 (Jan→Oct peak): nominal 10y +262bp, real 10y +263bp — real share **1.00**
   (full-year 1.13): tightening compresses breakevens, so real yields absorb ≥100% of
   the nominal move. ρ=0.7 belongs to inflation-shock episodes, not policy-surprise ones.
3. **G1 gate arithmetic (the headline).** Spec defaults: dreal = 0.7·0.45·450 = 142bp
   → SPX −5.5·1.42 + 7%·0.92 drift = **−1.4% median. G1 requires −18..−30%.** With
   amendments (ρ=0.9, β=8/11/14, logistic above → stress ≈ certain at CS=450bp):
   SPX −14.6 (rate) −12 (jump) +6.4 (drift) = **−20.1%** ✓; QQQ −28.8% ✓;
   HYG −14.2% ✓ (see A3). SOXX −41.3% vs actual 2022 ≈ −35%: acceptable (no SOXX gate),
   but flags that β_SOXX=14 + jump −25 is the aggressive edge; do not raise both.
4. **VIX×0.9 haircut — AMEND to ×0.8 (range 0.7–0.95).** Realized 21d vol / VIX,
   2010-26 (n=198 non-overlapping): mean 0.78, median 0.75, IQR [0.63, 0.90]. 0.9 sits
   at the 75th percentile — systematically over-widens the cones in normal states.
5. **Normal-state θ=310bp — ACCEPT, verified.** HY OAS 2023-08..2026-07: median 310,
   mean 317, last 284. (Caution: 3y window only; full-history HY median is ~430bp —
   θ_normal is regime-conditional, tag as such.)
6. **HYG D=3.2, SD=3.5, carry 6.5% — ACCEPT** (consistent with current fund stats;
   carry ≈ OAS 284 + 10y 4.68 less fees ⇒ dist yield ~6.5-7% plausible). Carry must use
   dt in years (author's known divisor risk — assert `carry_annual * months/12` in code).
7. **FOMC dates — ACCEPT** Sep 15-16, Oct 27-28, Dec 8-9 2026 (spec's "Sep 16" is the
   decision day, fine); Jan/Mar/Apr 2027 placeholders fine.
8. **Scenario span — AMEND 0..4 hikes → −2..+4 (add cut scenarios).** Data: Fed cut
   Sep/Oct/Dec 2025 (DFEDTARU 4.50→3.75), EFFR now 3.63, yet 2y = 4.23 (+60bp above
   funds) — the market prices *re-tightening*, so the spec's Oct-70%/Dec-45% hike
   pricing is coherent. But the Fed just ended an easing cycle and the model's own
   stress state is precisely the world where it resumes cutting; hike-only scenarios
   make the panel useless in its most-likely downside branch. All Stage-1 formulas are
   linear in S — negative hikes cost nothing. UI: segmented control −2..+4.
9. **Equity drift "+7%/yr earnings drift" conflates earnings growth with expected
   price drift — ACCEPT values, AMEND label.** 7%/10% are fine as expected-total-return
   baselines (tag: judgment); calling them "earnings" invites double-counting if anyone
   later adds a multiple term. Rename `drift_baseline_annual`.

---

## D. DATA-FEASIBILITY (verified by probe 2026-08-01)

**FRED (key works, full history unless noted):**
- DGS2 1976- / DGS10 1962- / DFII10 2003- / VIXCLS 1990- / EFFR 2000- /
  DFEDTARU 2008- / THREEFYTP10 1990- / T10Y2Y 1976- — all current through 2026-07-30.
- **BAMLH0A0HYM2: capped at 2023-08-01..2026-07-30 (~3y). Cannot calibrate OAS regimes
  or any pre-2023 replay from FRED OAS.**
- **BAA10Y (1986-) and AAA10Y (1983-) are NOT capped.** Use spread = BAA10Y−AAA10Y as
  the historical HY proxy with mapping HY_OAS(bp) ≈ 149 + 2.43·BaaAaa(bp), R²=0.71
  (fit on 2023-26 overlap). Limitation: IG-quality spread, ~70% co-movement, understates
  HY convexity in gaps; fine for regime dating and drift calibration, not for levels.
- BAA/AAA (monthly Moody's yields) also full history 1919- if ever needed.

**FMP (`/stable/historical-price-eod/light` — all resolved, but hard cap ≈ 5000 rows
→ nothing before ~2006-09 regardless of `from`):**
- HYG 2007-04- ✓, IEF/IEI 2006/2007- ✓, QQQ ✓, SOXX ✓, SMH ✓, SPY ✓, ^GSPC ✓,
  **^MOVE 2006-05- ✓ (MOVE-mapped HYG vol input is feasible — no fallback needed)**,
  ^VIX ✓, LQD ✓, JNK 2007-12- ✓. All current through 2026-07-31.
- Implication: pre-2006 hiking cycles (1994, 1999, 2004) must be studied via FRED
  yields/spreads only — no equity/ETF prices available for them from FMP.
- HYG dist-yield history is NOT on the light endpoint; carry param needs the existing
  dashboard feed or manual config.

## Verdict summary
| # | Item | Verdict |
|---|---|---|
| 1 | κ=0.45 | ACCEPT value; AMEND to κ_t = clip(0.45+0.40·ΔTP_6m, 0.25, 0.65) |
| 2 | OAS hike sign | ACCEPT sign; AMEND −8 → −4bp/priced hike + late-cycle taper |
| 3 | Markov states | ACCEPT 2-state (2022 grind = drift term; stress = gap regime) |
| 4 | β_dur | AMEND up: 8 / 11 / 14 (spec's 5.5/7.5/9.0 fail G1 by 15x) |
| 5 | AI-capex proxy | ACCEPT SOXX |
| 6 | Copula | AMEND to t-copula ν=4 (+29% co-crash at ρ=0.6 > 20% rule) |
| 7a | Logistic a,b | AMEND −4.0/3.5 → −4.65/2.6 (defaults violate own targets: 89% vs 35-50%) |
| 7b | Real share ρ | AMEND 0.7 → 0.9 (2022 realized share = 1.0) |
| 7c | VIX haircut | AMEND 0.9 → 0.8 (realized/VIX median 0.75) |
| 7d | θ_normal=310, HYG D/SD/carry, FOMC dates | ACCEPT (verified) |
| 7e | Scenario span | AMEND 0..4 → −2..+4 hikes |
| 7f | Drift label | ACCEPT values; rename earnings→total-return baseline |
