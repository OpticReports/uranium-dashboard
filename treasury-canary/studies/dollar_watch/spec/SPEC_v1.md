# Dollar watch — pre-registration SPEC v1 (FORWARD-ONLY), frozen 2026-11-03

Status: **FROZEN 2026-11-03** (`freeze.json`, which carries this file's sha256). Casey answered on
2026-11-02 ("go with the defaults, freeze it"): route `forward_only`, primary list C16, primary rule
UNPATCHED (re-arm logged alongside), the mechanical 2-of-5 onset rule, and a colour or notification
licensed by D-3 only. Both reviews of the v1 draft returned PASS_WITH_FIXES (statistics; data and
point in time), and their fixes are folded in below (counter-agent log). Q17 and Q19 carry this SPEC's
defaults, not Casey's answers (§9). It supersedes SPEC v0 (NOT_PASS twice). Nothing about the
deceleration rule's outcomes is computed here.

## 0. Results first

| Item | Decision |
|---|---|
| What is clean | **Only data after the freeze date.** A row counts only if its data date is after 2026-11-03 **and** it fired on the first vintage that carried that date (`d3_eligible`). Every month of dollar history 1971–2026 has been examined (§1). |
| DECEL test | **D-3, forward only.** A unit starts at an admitted unpatched firing and takes in admitted firings less than 250 index days after its **first** firing (never chained). Hit: "≤ +3% further rise in 250 index days". Null: the frozen GARCH(1,1)-t, conditioned on the state at the firing, with the drift **bracketed**: a PASS is judged as if the dollar drifted −1%/yr, a FAIL as if +1%/yr. Exact Poisson-binomial; alpha spent 0.005 / 0.020 / 0.050 at 8 / 16 / 24 matured units. A **placebo** (the rule without its deceleration clause) is scored beside it. |
| Power | About 0.20 units a year under the model (0.24 in the tuned sample; 0.11–0.16 in calmer regimes). **Looks ~2060–2067 / ~2093–2107 / ~2126–2147.** P(PASS by look 3) with no edge: at most 0.03 inside the drift bracket **if the frozen volatility model holds**, and about 0.07 under the fit window's own latest decade (2016–26) plus a −1%/yr drift (G6; Q19). At +0.20: 0.24–0.44; at +0.30: 0.67–0.80. With no edge the record most likely ends INCONCLUSIVE (§3.6). |
| MOM | **Descriptive and logged; never tested.** The bar at the house convention is ~40 independent episodes, about 400 years. |
| Colour or notification | **Only a D-3 PASS** licenses one neutral colour state on layer 3(a) and a notification. A PASS reads **"dollar scramble peaking: beat a no-information model"**, with "deceleration-specific: not tested" and the placebo's numbers beside it (§3.5). It never says "subsided". |
| Onset rule | Mechanical 2-of-5 (§5), with its degeneracy check pre-committed in §5.4 before the count was run; the result is in §5.5. Forward, each month is dated once, at its close (§5.6). |
| Data succession | Pre-registered for the broad dollar and the 10-year (§2.1). With no successor the ledger ends and the last completed look stands. |
| D-1 / D-2 | Withdrawn and not run (Appendix A). |

## 1. Contamination statement

**All dollar history is seen.** Specifically:
- ICE DXY 1971–2026, monthly and daily: band, momentum, speed, level, quadrant; 25-crisis metrics.
- The broad dollar 2006–2026: the rule was tuned on it (in-sample, 6 / 7 firings).
- The monthly analogue on 1973–2005: scored, null.
- Finder B's 8-pair EM basket: seen across 7 windows and 14 anchor spans (data review v0 B1).
- **The basket's 3 / 6 / 12-month outcomes after the 14 historical anchors** have been published on the
  panel since 2026-11-02 23:35 UTC (`7f2a069e`), so Casey and every panel viewer can see them. Nothing
  open depends on them (D-3 uses the broad dollar only). If a cross-section test were ever revived,
  Casey would be a contaminated designer for those 8 currencies.
- **The onset rule's 2000–2026 history**, counted on 2026-11-02 (§5.5). This exposes all five marker
  histories at month level.
- The v1 statistics review fitted a GARCH on in-sample returns and simulated synthetic paths. No one
  computed a history-based DECEL outcome.

No history-based test of DECEL or MOM is out of sample, and frozen parameters cannot un-see paths.
Evidence counts only from rows that are `d3_eligible` (§3.1). Every other row is shown on the panel as
IN-SAMPLE, including live rows dated on or before the freeze date, and never starts, joins or scores a
unit (data review v1 S1).

## 2. DECEL — frozen definition (as `code/decel_realtime.py` = `dollar_watch.scramble_firings`)

**Calendar.** Days on which DTWEXBGS and DGS10 are both published: the panel's `rule_index` and the
harness's `rule_calendar` (stats review v1 S3).
- The frozen script's calendar also required VIXCLS, which the rule never uses.
- The two calendars differ on 7 Good Fridays in 2006–2026 and give identical firings, both variants
  (gate test).
- The in-sample record keeps the script's calendar.
- Dropping VIXCLS removes a licensed-data dependency from a ledger meant to run for a century.

**Rule.** k counts days on that calendar. The rule is evaluated on **every** k ≥ 80 through the
latest available day, which is what the panel code does. The frozen script's `len(B)−1` bound is an
outcome-code artefact (data review v0 M1).

| Term | Definition |
|---|---|
| roc20[k] | B[k] / B[k−20] − 1 |
| mx, kmx | the max of roc20[k−60..k] and its first argmax |
| fire (UNPATCHED, **primary**) | mx ≥ 0.04 AND roc20[k] ≤ 0.5·mx AND B[k] ≥ 0.97·max B[k−60..k] AND Y[k] < Y[max(0, kmx−20)] AND k − last_fire > 120 |
| RE-ARM (logged, descriptive) | the same, or inside the cooling window if mx ≥ 1.5·mx at the last firing |
| PLACEBO (scored beside D-3) | UNPATCHED without the deceleration clause roc20[k] ≤ 0.5·mx, so it fires on the first day of a ≥ 4% climb near the high with the 10-year falling |

`last_fire` is the last firing of the rule evaluated on the same vintage (stats review v1 minor 5).
Parameter values are frozen in `freeze.json` and asserted equal to `RULE` by a gate test.

### 2.1 Succession (stats review v1 S3)

| If this happens | Then |
|---|---|
| DTWEXBGS ends or is replaced | Continue on the Fed's designated successor nominal broad dollar index, ratio-spliced at the last common date. Units admitted before the change are scored on the spliced series. The null is not re-fitted. |
| DGS10 ends or is replaced | Use the successor 10-year constant-maturity Treasury yield (Fed H.15 or Treasury) as is from the last common date. |
| FRED drops a series its source still publishes | Read it from the source. It is the same series, not a succession. |
| There is no successor | The D-3 ledger ends and the last completed look stands. |
| An onset marker's series ends with no successor | The marker is recorded unavailable. The rule continues as 2 of the markers still available, and each month row records which were available. |

## 3. D-3 — the forward test (DECISION)

### 3.1 Admission and units

**Admission (`d3_eligible`).** A firing is evidence only if both hold:
- its data date is after the freeze date (2026-11-03);
- it fired on the first DTWEXBGS vintage that contains its data date.

That vintage is the one the panel archived at first sight (§6.1). First sight counts only when the panel
reads the release that added the date's week. The flag is unknown (null) in two cases:
- an outage spanned a release, so a later vintage is being read;
- no earlier rule state exists. At the freeze the state is seeded with the freeze vintage's last day,
  2026-10-30.

An unknown row is settled by `prereg/d3.py admit`.
- It re-runs the frozen rule on the first vintage from ALFRED, whose last day must fall in the date's
  H.10 week, and records the ALFRED vintage date.
- It archives those bytes and appends an admission record (data re-check M-A).
- `admit` also repairs an admitted row whose archived bytes are lost.
- Until a row is settled it is listed as unresolved. It is skipped, never fatal, and no p_u is computed
  for a later unit while it is open (confirm pass M-1).

A firing that appears only after a revision is logged and never scored.

**Units.**
- A unit starts at an admitted unpatched firing f₁ (index k₁).
- An admitted unpatched firing with k − k₁ < 250, measured from f₁, belongs to the same unit. Units are
  never chained. The unit is scored on f₁ only.
- Index gaps are counted on the vintage that first contains the later firing.
- Pre-freeze and revision-born rows never start or absorb a unit.

Outcome windows are therefore disjoint, so units are the clusters (stats review v0 S1). The panel's unit
fields are provisional. At each R1 and at each look, `prereg/d3.py units` rebuilds the units from the
rows and the admissions under this rule, counting each gap on the later firing's own archived vintage.
It lists every mismatch with the panel's fields, and two verifiers check the result at a look. If a
unit's first date is missing from a later firing's vintage, a new unit starts. The verifiers check such
cases for overlapping windows. Matured units are ordered by maturity date, k₁ + 250.

### 3.2 Outcome (S1, primary)

hit_u = 1{ max B over index days (k₁, k₁+250] ≤ 1.03·B[k₁] }.

It is computed on the **maturity vintage**, the first one that contains k₁+250, with that vintage's
sha256 recorded. It is measured from the data date. The release-anchored version and S2–S4 / C1–C4
(§6.2) are DESCRIPTIVE. "Scramble peak" (S) and "crisis over" (C) are never merged: in 2008 the gap
was about 4 months and −25% for the S&P.

### 3.3 Null and statistic

**H0.** Given F_{k₁}, the daily log changes of B after k₁ follow the frozen GARCH(1,1) with Student-t
innovations plus a constant drift μ. In other words, the deceleration condition carries no information.
μ is not known, so the test brackets it (stats review v1 S1).

**The model.** MLE on 100·Δlog B over the rule calendar, 2006-01-03..2026-10-30, on the freeze vintage.
The vintage's files and sha256s are in `prereg/freeze_vintage/` and `freeze.json`.

| Parameter | Frozen value |
|---|---|
| ω | 0.00063688 |
| α | 0.04371597 |
| β | 0.95134666 (persistence 0.9951) |
| ν | 7.0007 |
| log-likelihood | −1191.41 on 5,178 returns |
| parameter hash | `306ac2cd…` |

The fit uses returns only, never S1, and was written before any forward firing existed.

**p_u.** Three numbers per unit: the Monte-Carlo probability of hit_u under H0 at three drifts.

| Symbol | Drift | Used for |
|---|---|---|
| p⁻ | −1%/yr | PASS |
| p⁰ | 0 | reported |
| p⁺ | +1%/yr | FAIL |

- N = 100,000 paths of 250 steps, each starting from h_{k₁+1} filtered with the frozen parameters
  through k₁ on the firing vintage.
- The three drifts share the same random numbers, so p⁻ ≥ p⁰ ≥ p⁺. The seed is YYYYMMDD of k₁, and the
  MC SE is ≤ 0.0016 each.
- p_u is computed **once, before the unit matures**, by `prereg/d3.py pu-row`, for a unit start in the
  units it rebuilds itself, from the archived firing bytes only, each checked against its recorded
  sha256.
- The harness refuses on any of these (G7; data review v1 M5, re-check M-B):
  - a hash mismatch;
  - an index mismatch;
  - a row that is not a unit start, or one with an unresolved row before it;
  - a matured unit;
  - an existing record.
- The record goes into `backend/app/sources/dollar_pu_records.json` (append-only) and is checked by a
  second reader.
- Conditioning on h_{k₁+1} prices the vol-timing effect (decel days sit at high conditional vol) that
  biased v0's random-rule benchmark to T < 0.

**Statistic.** At n matured units:
- S = Σ hit_u.
- T_μ = (S − Σ p_u^μ) / n, reported at each drift.
- P_tail(μ) = P_PB(S′ ≥ S), the exact Poisson-binomial upper tail at each drift. This is not the p⁺ of
  the table above, which is the +1%/yr p_u (stats re-check minor 2).
- δ_U = the largest δ, on the 0.001 grid over [−1, 1], with P_PB(S′ ≤ S | p⁺_u + δ, clipped to
  [0, 1]) ≥ 0.05/3. This is the one-sided 98.3% upper bound on the edge, taken at the optimistic drift.

### 3.4 Looks and classes (no other look is valid)

| Look | Matured units n | PASS if S ≥ c_j, alpha spent cumulatively | FAIL if | Otherwise |
|---|---|---|---|---|
| 1 | 8 | 0.005 | δ_U < 0.10 | continue |
| 2 | 16 | 0.020 | δ_U < 0.10 | continue |
| 3 (final) | 24 | 0.050 | δ_U < 0.10 | **INCONCLUSIVE, final** |

- **Critical values.** c_j is the smallest count with P_H0(S_{n_l} ≥ c_l at some look l ≤ j) ≤ the
  cumulative alpha. It is computed by exact recursion on the recorded p⁻, with the earlier c's as
  recorded (stats review v1 minor 2). FAIL stops are ignored in the recursion (non-binding), so the type
  I error stays ≤ 0.05 whatever FAIL does.
- **FAIL** uses the 98.3% bound at +1%/yr (minor 3). A real +0.10 edge is FAILed less than 1% of the
  time.
- **The bracket.** A PASS has to beat the record even at a −1%/yr drift. A FAIL has to fall short of it
  even at +1%/yr. Anything in between is INCONCLUSIVE.
- Looks are computed at the R2 calibration after n is reached, by the harness, then checked by two
  independent verifiers. There is no absolute T bar and no share bar.

### 3.5 Consequences (what the panel may then display)

| Class | Layer 3(a) |
|---|---|
| PASS | One neutral colour state **and** a notification are licensed. The text reads **"dollar scramble peaking: beat a no-information model"**, with **"deceleration-specific: not tested"**. It gives n, S, Σp_u at each drift and the look. The **placebo's numbers sit beside it**: its n, S, T⁰, P_tail at −1%/yr, and whether it matches or beats the rule. They never change the wording. It never says "crisis subsided", and the crisis-over (C) outcomes and their gap are printed beside it. |
| FAIL | Descriptive permanently, labelled "forward record: did not beat a no-information model (n, δ_U < 0.10 at +1%/yr)". No re-tuning and no new variant. The ledger continues as a record. |
| INCONCLUSIVE | Descriptive, with n, S, Σp_u and "undecided". At the final look this is permanent. |
| before look 1 | Descriptive (the status today), with the unit count shown. |

The placebo counts its own units matured by the look date, under identical admission, units, p_u and
hits (stats review v1 S2). It cannot certify deceleration. A placebo comparison made after the rule has
passed is biased toward the rule: under a generic post-scramble reversal of +0.20, 65–71% of PASSes would
still have read "deceleration", a false claim in about a quarter of all records (stats re-check S2).
Deceleration-specific wording needs its own pre-registered test, a matched-scramble comparison, with G6
showing a false-"deceleration" rate ≤ 0.05. That test may be added as a new SPEC version before the first
unit is scored. Layers 2, 3(b), 3(c), the quadrant and MOM stay DESCRIPTIVE under every
outcome.

### 3.6 Power

**Exact, at equal p_u** (`prereg/d3_power_v1.py`). The true p_u is unknown and not computed. Two states
at the firing are pinned by p⁰:

| State | h vs unconditional | p⁻ | p⁰ | p⁺ | critical values |
|---|---|---|---|---|---|
| volatile | 4.6× | 0.325 | 0.30 | 0.275 | 7 / 10 / 13 |
| calm | 0.65× | 0.571 | 0.50 | 0.426 | 9 / 14 / 19 |

| True edge δ (true drift 0) | volatile: P(PASS) by look 1 / 2 / 3 | P(FAIL by 3) | calm: P(PASS) by look 3 | P(FAIL by 3) |
|---|---|---|---|---|
| 0 | 0.001 / 0.008 / 0.016 | 0.05 | 0.005 | 0.02 |
| +0.10 | 0.009 / 0.061 / 0.13 | 0.006 | 0.047 | 0.002 |
| +0.20 | 0.035 / 0.23 / 0.44 | 0.00 | 0.24 | 0.00 |
| +0.30 | 0.11 / 0.53 / 0.80 | 0.00 | 0.67 | 0.00 |
| +0.40 | 0.26 / 0.83 / 0.97 | 0.00 | 0.97 | 0.00 |

Sensitivity (stats review v1 S1), at no edge and P(PASS by look 3), volatile / calm:

| True drift | P(PASS by look 3) |
|---|---|
| −1%/yr | 0.029 / 0.025 |
| −2%/yr | 0.051 / **0.094** |
| +1%/yr | 0.008 / 0.001 |

Under the fit window's own +0.9%/yr drift, power at +0.20 is 0.36 / 0.09. The bracket costs power where
volatility is low.

**Volatility regime (stats re-check S1; G6, simulated).** The bracket covers drift, not a shift in the
volatility model. Under the fit window's own latest decade (2016–26 volatility), a false PASS with no edge
is:
- 0.019 with no drift;
- 0.055 ± 0.007 with a −1%/yr drift. The statistics re-check measured 0.066–0.079 in its own runs: about
  0.07.

The stronger option in Q19 (PASS judged on the larger p⁻ of two frozen fits) gives about 0.04 there, but
power at +0.20 falls from about 0.39 to 0.26. Without it, a −1%/yr trend roughly doubles the false-PASS rate (0.026 → 0.062 in the
statistics review's simulation). That trade is Q19.

**Simulated (G6, heterogeneous p_u; §3.7; `prereg/g6_out/`):**
| Scenario | units/yr | mean(hit − p⁰) | P(PASS) by look 1 / 2 / 3 | FAIL | INCONCLUSIVE | PASSes read "not specific" |
|---|---|---|---|---|---|---|
| **binding:** DGP = model (2,000 paths) | 0.200 | +0.000 ± 0.002 | 0.000 / 0.003 / 0.007 | 0.045 | 0.947 | 0.13 |
| **binding:** drift -1%/yr (2,000 paths) | 0.189 | +0.049 ± 0.002 | 0.002 / 0.012 / 0.030 | 0.023 | 0.947 | 0.18 |
| drift +1%/yr (1,000 paths) | 0.211 | -0.051 ± 0.003 | 0.000 / 0.000 / 0.001 | 0.107 | 0.892 | 0.00 |
| drift -2%/yr (1,000 paths) | 0.178 | +0.091 ± 0.003 | 0.005 / 0.040 / 0.081 | 0.008 | 0.911 | 0.27 |
| drift +0.9%/yr (the fit window's) (1,000 paths) | 0.210 | -0.039 ± 0.003 | 0.000 / 0.001 / 0.004 | 0.106 | 0.890 | 0.00 |
| unconditional vol x0.8 (1,000 paths) | 0.105 | +0.035 ± 0.003 | 0.002 / 0.012 / 0.027 | 0.024 | 0.949 | 0.26 |
| unconditional vol x1.2 (1,000 paths) | 0.303 | -0.023 ± 0.003 | 0.001 / 0.003 / 0.006 | 0.090 | 0.904 | 0.00 |
| half-life x0.5 (1,000 paths) | 0.230 | -0.004 ± 0.003 | 0.000 / 0.001 / 0.010 | 0.055 | 0.935 | 0.10 |
| half-life x2 (1,000 paths) | 0.162 | +0.000 ± 0.003 | 0.000 / 0.007 / 0.015 | 0.058 | 0.927 | 0.20 |
| constant-vol random walk (1,000 paths) | 0.246 | -0.038 ± 0.003 | 0.000 / 0.002 / 0.007 | 0.098 | 0.895 | 0.00 |
| edge +0.10 (deceleration-specific) (1,000 paths) | 0.200 | +0.105 ± 0.003 | 0.005 / 0.033 / 0.100 | 0.005 | 0.895 | 0.01 |
| edge +0.20 (deceleration-specific) (1,000 paths) | 0.200 | +0.198 ± 0.003 | 0.018 / 0.134 / 0.356 | 0.001 | 0.643 | 0.01 |
| edge +0.30 (deceleration-specific) (1,000 paths) | 0.200 | +0.302 ± 0.003 | 0.055 / 0.381 / 0.767 | 0.000 | 0.233 | 0.01 |
| generic reversal +0.20 (rule and placebo) (1,000 paths) | 0.200 | +0.198 ± 0.003 | 0.015 / 0.144 / 0.382 | 0.002 | 0.616 | 0.29 |
| drift +0.9%/yr, edge +0.20 (1,000 paths) | 0.210 | +0.166 ± 0.003 | 0.014 / 0.094 / 0.240 | 0.002 | 0.758 | 0.00 |

Binding rows: model_size_le_0.05 yes, model_calibration_within_0.01 yes, drift-1_size_le_0.05 yes → **G6 PASS**. Paths still pending at the 400-year cap: at most 0.000 of a scenario.

With heterogeneous p_u, power sits between the two exact states: 0.36 at +0.20 and 0.77 at +0.30. The placebo is a guard,
not a proof:
- It flags 29% of the PASSes a generic post-scramble reversal earns.
- It flags 1% of those a deceleration-specific edge earns.

**Calendar** (stats review v1 minor 4):

| Unit rate | Looks |
|---|---|
| 0.20 units/yr (the model) | ~2067 / 2107 / 2147 |
| 0.24 units/yr (the tuned sample) | ~2060 / 2093 / 2126 |
| 0.11–0.16 units/yr (calmer regimes) | look 3 after 2170 |

### 3.7 Gates (merge-blocking)

| Gate | Requirement |
|---|---|
| G1 | The rule reproduces the 6 unpatched and 7 re-arm frozen dates (done: data review v0 N1; gate test). |
| G1b | Run on data truncated at each historical firing, the rule fires on the last day (done; gate test). |
| G1c | On DTWEXBGS ∩ DGS10 and on the script's DTWEXBGS ∩ DGS10 ∩ VIXCLS, the firings are identical, both variants (done; gate test). |
| G6 | `prereg/g6.py` runs the full pipeline from the frozen model: the rule and the placebo, units, p_u from a log-h table per drift built with the harness's own Monte Carlo, hits and looks. Paths run until 24 rule units mature, capped at 400 years. The simulated 10-year yield is a random walk, sd 0.057pp per index day, independent of the dollar. **Binding:** cumulative P(PASS) ≤ 0.05 under the model and under a −1%/yr drift; \|mean(hit − p⁰)\| ≤ 0.01 under the model; \|mean(hit − p⁻)\| ≤ 0.01 under the −1%/yr drift. **Descriptive:** drift +1, −2 and +0.9%/yr; vol ×0.8 and ×1.2; half-life ×0.5 and ×2 at the same unconditional variance; a constant-vol random walk; the fit window's latest decade (2016–26), alone and with a −1%/yr drift; edges +0.10 / +0.20 / +0.30; a generic reversal on both rules. Each binding row also reports the **design size**: the exact P(PASS) under the pessimistic null given each path's own recorded p⁻ and p⁺, averaged over paths (stats re-check minor 1). Reduced run at the freeze (2,000 paths for the binding rows, 1,000 for the rest; `prereg/g6_out/`). It is re-run with 2,000 paths on every row before the first unit is scored. |
| G7 | The harness: the PB pmf, δ_U and the exact spending recursion match brute-force enumeration for n ≤ 12; p_u is ordered by drift and reproducible from its seed; `pu-row` refuses a hash, admission or index mismatch; appending data after k₁ changes nothing (done; gate tests). |

## 4. D-4 — momentum (DESCRIPTIVE only)

**Signal.** ICE DXY monthly average (the panel's `dxy_monthly`); a month with M[t] / M[t−12] − 1 >
+0.10.

**Episode.** A signal month after the reference cut-off whose previous signal month is more than 12
months earlier (as the panel's `ledger_block` does).

**Logged.** The month and the 12m change. Outcomes:
- S&P, Baa − 10y and the broad dollar at 3 / 6 / 12 months from the first S&P close of the following
  month (as the code does). Each field is frozen on its own when it matures (data review v1 M4).
- Whether a §5 onset falls in m+1..m+12, with its subtype. This is written once, when every month
  m+1..m+12 has been dated (§5.6) and every onset among them has its subtype (data review v1 M2).
- The EM FX basket's maximum rise over m+1..m+12 (forward rows only), written once the basket reaches
  past m+12's close.

**Never tested.** The panel line reads: "in-sample NSR 0.42 (monthly average; 0.51 on closes), ~5
clusters, list fixed knowing the dollar path, sign flips across lists; 0 out-of-sample episodes; a
test needs ~40 independent episodes ≈ 400 years." No colour or notification, ever, under this SPEC.

## 5. Forward onset rule (dates crises after the freeze; also the D-4 outcome)

### 5.1 Markers (evaluated per calendar month m; daily inputs)

| # | Marker | Series | Trips in m if |
|---|---|---|---|
| 1 | VIX | FRED VIXCLS close | ≥ 40 on any day in m |
| 2 | OFR FSI | OFR `fsi.csv`, column "OFR FSI" (as published) | 5 consecutive FSI observations, each above its own P95, with the 5th in m. P95(d) is the 95th percentile (linear interpolation) of FSI over [d − 5 calendar years, d), using all prior history when that is shorter, and needs ≥ 250 prior observations. |
| 3 | EM FX basket | equal-weight geometric mean of DEXBZUS, DEXMXUS, DEXSFUS, DEXINUS, DEXKOUS, DEXTHUS, DEXCHUS, DEXMAUS (local currency per USD; each leg as-of filled on the union of their days; all 8 present; from 1995-01-03) | basket(d) / basket(d−63 basket days) − 1 ≥ 0.10 for some d in m |
| 4 | S&P 500 | daily close (live: FRED SP500; history: Yahoo ^GSPC, `data/spx_daily.csv`) | close(d) ≤ 0.80·max(close over the 252 trading days ending at d) for some d in m |
| 5 | Fed emergency action | `fed_emergency_actions.json` | any listed action dated in m |

### 5.2 Fed emergency action (marker 5)

**Included:**
- an FOMC federal funds target cut announced outside a scheduled meeting;
- a new lending facility or loan under Section 13(3), or another new temporary emergency lending
  facility or authority (e.g. TAF, the 2008 GSE lending authority);
- a new or expanded central-bank liquidity swap line: a new counterparty, a larger limit, a lower
  price, a longer operation tenor or a higher operation frequency;
- the establishment of the FIMA repo facility.

**Excluded:**
- discount-rate-only changes (2007-08-17);
- open market and repo operations (Sept-2019);
- expansions, collateral changes, extensions or wind-downs of existing facilities;
- extensions of swap-line expiry;
- conversions to standing status without new terms (2013-10-31, 2021-07-28);
- asset purchases;
- cuts at scheduled meetings.

The list is append-only and must be updated at each R1 (monthly) with the press-release URL, fetched
and verified. It currently holds 48 actions in 18 months, 2001-01..2023-03.

### 5.3 Onset and subtype

- **Onset** = a month m with ≥ 2 distinct markers tripped in m and no onset in m−12..m−1 (the
  12-month exclusion).
- **Dollar-funding subtype**: within months m..m+2, either
  - FRED SWPT > 50,000 ($m) on any weekly observation, or
  - the trailing 5-observation mean of DCPF3M − DTB3 (days both are published) > 1.00 on any day.

  The subtype is recorded "pending" until m+2 closes, then frozen.
- Onsets added by judgment are logged as "judgment" and never scored.

### 5.4 Pre-committed degeneracy check (written before the count was run)

The rule is run as written on 2000-01..2026-10 (complete months), using fresh pulls on 2026-11-02
and the committed `spx_daily.csv`. Pre-committed outcome:
- **fewer than 3 or more than 13 onsets** → the rule is degenerate and goes back to Casey;
- **3–13** → the rule is frozen unchanged.

No threshold, window or marker is tuned to the count. Only dates, the markers tripped and subtype
flags are reported; no DECEL outcome is computed. Pre-commit hash: `work/precommit_onset.txt`.

### 5.5 Result

**8 onsets in 2000-01..2026-10. This is inside the pre-committed 3–13, so the rule is FROZEN UNCHANGED.**
Run by `work/onset_count.py` on fresh pulls from 2026-11-02 (`work/raw_manifest.txt`); full output in
`work/onset_count_2000_2026.json`. The data review v1 reproduced it independently, and with four other
readings of the text (N2). It also holds on OFR's pre-revision 2022–23 values (N3).

| Onset | Markers tripped (first date) | Dollar-funding subtype |
|---|---|---|
| 2001-04 | OFR, S&P −20%, Fed (04-18 cut) | no (SWPT not on FRED before 2002-12; CP − bill ≤ 1pp) |
| 2002-07 | VIX ≥ 40, OFR, S&P | no (SWPT n/a) |
| 2007-12 | OFR, Fed (TAF + swaps) | **yes** (CP − bill 5d 1.78 on 12-03) |
| 2009-01 | VIX, S&P, Fed | **yes** (SWPT $538bn; CP − bill 1.14) |
| 2010-05 | VIX, Fed (swaps) | no |
| 2011-09 | VIX, EM FX +10% | no |
| 2020-03 | all five | **yes** (SWPT $206bn on 03-25; CP − bill 1.12) |
| 2022-06 | OFR, S&P | no |

Months with ≥ 2 markers: 31. The 12-month exclusion leaves 8 onsets. With the Fed list's two 2026-11-03
additions (§5.7) the recount is unchanged: 8 onsets and the same 31 months
(`work/onset_recount_fed_list_2026-11-03.json`; only 2009-03 gains the Fed marker).

**A property, recorded and NOT fixed** (fixing it would be post-hoc). The exclusion runs from the last
*onset*, so a long crisis re-dates itself at month 13:
- 2009-01 is the GFC 13 months after 2007-12; Lehman (2008-09) falls inside the exclusion.
- 2002-07 is 15 months after 2001-04; 9/11 (2001-09) falls inside the exclusion.
- The 2022-06 onset's window also covers the 2022-09 dollar peak and SVB (2023-03).

Forward, this can label a crisis continuation as a new onset in the MOM outcome. Only Casey may change
it, in a new SPEC version labelled post-hoc (Q18). No DECEL outcome was computed.

### 5.6 Forward evaluation, point in time (data review v1 S2)

- **Once, in order.** Each month m from `freeze.json` `onset_first_month` (2026-11) is evaluated once,
  at the first panel build on or after its **close**. The close is the later of:
  - the day **after** the H.10 release carrying m's last business day (the release comes at 4:15pm ET,
    after the day's first builds: data re-check S-1);
  - m's end + 5 business days.
- **What it waits for.** The Fed list must be reviewed through m (`reviewed_through` ≥ m). Every input
  (VIXCLS, SP500, the 8 EM legs, the OFR FSI) must **not be served from a failed fetch's stale cache**
  (status "ok") and must **reach m's last business day**. The EM basket counts when its newest leg
  reaches that day and no leg is stale. It waits for these until a **deadline**, the end of m+1. At the
  deadline it is evaluated anyway, recording what was missing and whether the list was current.
- **One row per month, onset or not**, carrying:
  - the markers with their dates and values, and the OFR P95s;
  - `onset` and `excluded_by`;
  - the Fed list's sha256 and `reviewed_through`;
  - each input's sha256 and last observation;
  - the OFR FSI values marker 2 reads, archived (gzip) under their sha256 beside the downloaded file's
    sha256. These run from 5 years before m−1 to m's end, about 35 KB a month (data re-check M-E).
    "As published" means those values.
- **The 12-month exclusion** reads only the rows of earlier months.
- **Later revisions and list appends** go to the month row's `revision_checks` {checked_on,
  markers_now, list sha256}. They never create, remove or re-date an onset.
- **The subtype** is evaluated the same way at m+2's close. It waits for SWPT (through m+2's last
  Wednesday), DCPF3M and DTB3 (through m+2's last business day), all fetched fresh. The deadline is the
  end of m+3. Until then it is pending.
- **A month dated after its deadline** is flagged `late_evaluation` and reported as not point in time.
  That happens after a ledger reset or a long outage. The ledger is committed to the repository at each
  R1, so a reset can be detected (re-check M-C).
- **A withheld EM basket** trips nothing and is recorded as missing (data review v1 M4). The basket is
  withheld when a leg's last observation is more than 10 business days behind the newest leg.

### 5.7 The Fed list, v1.1 (2026-11-03; data review v1 M1)

- **Two 13(3) actions added after the check:** 2008-10-08 (the New York Fed borrowing AIG subsidiaries'
  securities against cash) and 2009-03-02 (new 13(3) loans to AIG's life-insurance SPVs). Both pages
  were fetched (HTTP 200), and their dates and titles checked. The recount is unchanged (§5.5).
- **List hashes.** The check's list keeps its recorded sha256 (`f24ab63f…`, in `freeze.json`
  `onset_check`). The shipped list is `f03ce7f5…`: 50 actions in 19 months.
- **Rulings.**
  - Reverse (foreign-currency) liquidity swap lines count as a new swap line. This decides only
    2009-04-06, which lies inside the 2009-01 exclusion.
  - One-firm 13(3) arrangements count when they are a new loan or facility. Extending an existing
    facility's terms to named firms is an expansion and is excluded (2008-09-21, re-check N-3).
- **Register.** 14 rejected candidates are listed, each with the exclusion clause applied, URL and fetch
  check.
- **Upkeep.** `reviewed_through` is 2026-10. At each R1 the list is reviewed through the previous month
  before that month is dated. Every forward addition or exclusion is checked by a second reader and
  logged with `added_on`. Rows are never removed; a correction is a new row plus a note.

## 6. The ledger — what must be recorded

### 6.1 At firing (rows of kind `scramble_rule` and `placebo_rule`; appended the first time the panel sees them)

- `kind`, `date` (the data date k), `variants`, `roc20_max_pct`, `roc20_max_date`, `roc20_now_pct`,
  `dollar`, `h10_release`, `h10_release_source` and `recorded_on`.
- `k` and the calendar label.
- The clause values: `y10_now`, `y10_ref`, `y10_ref_date` and the near-high ratio.
- `first_vintage_contains_date` (true / false / null when no earlier rule state exists), `d3_eligible`
  and `d3_note`.
- `unit_first` and `index_gap_to_unit_first`, set only on admitted unpatched rows (§3.1).
- `inputs`: the sha256 of the DTWEXBGS and DGS10 bytes, **archived** in the ledger directory under
  their hash.
- The p_u record is kept in `dollar_pu_records.json`, not in the row: the three drifts' p_u and MC SE,
  N, seed, h_next, the GARCH parameter hash, the input hashes and computed_on.

### 6.2 At maturity (written once, `outcomes_250d`)

**D-3:**
- S1 hit, max B and its date, and the further rise %;
- `maturity_date` (k₁ + 250) and the maturity vintage's sha256.

**Descriptive (rule rows only):**
- S1 anchored at the first index day after `h10_release`;
- S2, days to the 250-day max of B;
- S3, whether the 5-obs-mean CP − bill max over (k, k+60] is ≤ its value at k;
- S4, whether gold's min over (k, k+60] is ≥ 0.97·gold[k];
- C1, whether the S&P's 250-day forward min is ≥ −10%;
- C2, the first VIX close < 25, and whether VIX re-exceeds VIX[k] within 60 days;
- C3, the EM FX basket's 250-day extreme date;
- C4, days to the S&P's 250-day low.

The 3 / 6 / 12-month S&P, EM FX, Baa − 10y and broad-dollar outcomes from the code's anchor stay as
they are, frozen field by field.

### 6.3 Revision checks, month rows and momentum rows

- **Revision checks.** On every build, each rule and placebo row gets an entry in `revision_checks`
  {checked_on, still_fires} whenever its status changes. Rows are never deleted.
- **Month rows** (`kind: "onset_month"`): §5.6.
- **Momentum rows:** §4.

### 6.4 Transport

The panel serves `GET /dollar-watch/ledger` (the ledger as stored) and
`GET /dollar-watch/archive/<sha256>[.gz]` (only names that are a sha256). At each R1 the harness:
- downloads both, and commits the ledger snapshot;
- runs `admit` for any unknown row or lost archive, and `units` for the unit list;
- runs `pu-row` for any new unit start, and commits the record.

The payload reports the archive's size on disk, any row whose inputs failed to archive (those are retried
while the cached bytes still match), an unreadable ledger, and any late-dated month (re-check M-C, M-E).

## 7. The panel code (`backend/app/metrics/dollar_watch.py`) against this SPEC

**Matches and is adopted:**
- `scramble_firings`, including last-day evaluation;
- the append-only ledger keyed by (kind, date), with `recorded_on`;
- write-once outcome blocks;
- the anchor at the first S&P close strictly after max(H.10 release, recorded_on), for descriptive
  outcomes;
- the momentum gap > 12 months.

**Changes the SPEC requires (all implemented in the freeze commit, with gate tests):**

| # | Change |
|---|---|
| C1 | Unit assignment on admitted unpatched rows only (`unit_first`, `index_gap_to_unit_first`; k − k₁ < 250 from the first firing; never chained). |
| C2 | Archive the DTWEXBGS / DGS10 bytes at first sight, under their sha256. Record `inputs`, `k`, the calendar, the clause values, `first_vintage_contains_date`, `d3_eligible` and `d3_note`. |
| C3 | A `revision_checks` append when a rule or placebo row's fire status changes on a new vintage. Never delete. |
| C4 | A `250d` maturity block (§6.2), written once, with maturity on index days. |
| C5 | `h10_release`: when the Monday is a federal holiday, the release is the next business day. It matches all 403 ALFRED DTWEXBGS release dates (data review v1 N4). |
| C6 | The month rows (§5.6) and the shipped Fed list (§5.7), with gate tests on its URLs, order, hashes, rulings and register. |
| C7 | Archive the OFR `fsi.csv` bytes at every month's evaluation. P95 is computed on as-published history. |
| C8 | Momentum rows get the onset record and the EM basket's 12-month maximum rise, with the §4 maturity rules. |
| C9 | EM FX outcomes have been shown on all rows since `7f2a069e`. Historical rows are in-sample and data-date anchored (§1). |
| C10 | Text: PENDING carries the answers and the asked questions with their own 60-day expiry. HONESTY_LIVE carries the frozen line. Live-row anchoring is stated for live rows only (data review v1 M3). |
| C11 | `d3_eligible` reads `freeze.json` `freeze_date`. The reference cut-offs (`LAST_INDEX_DAY`, `LAST_FROZEN_MONTH`) only start the descriptive ledger. A gate test asserts that `RULE` equals the frozen rule parameters. |
| C12 | p_u: the offline harness `prereg/d3.py pu-row`, from hash-checked archived inputs only, before maturity (gate G7). The backend stores the record; it never computes it. |
| C13 | Repo housekeeping: `data/fred/` is committed. The GARCH fit inputs (the freeze-vintage DTWEXBGS and DGS10) are stored in `prereg/freeze_vintage/` with their sha256s in `freeze.json`. |
| C14 | The placebo rule logged forward beside the rule (`kind: "placebo_rule"`), with identical admission, units, inputs and maturity. |
| C15 | The rule calendar is DTWEXBGS ∩ DGS10 (§2). |
| C16 | The EM basket staleness guard, and field-by-field freezing of the 3 / 6 / 12-month outcomes. |
| C17 | The transport routes (§6.4). |
| C18 | Re-check fixes: the close the day after the release; fresh-and-complete inputs; late-dated months flagged; the OFR extract archive and the disk line; failure surfacing and archive retries; the first-vintage outage rule and the freeze seed; `onset_first_month` from `freeze.json`; `admit`, `units` and the hardened `pu-row` in the harness. |

## 8. Honesty box

- **The only clean evidence is the future.** It needs ~33–40 years to the first look and ~100–120 to
  the last. With no edge it most likely ends INCONCLUSIVE.
- **What a PASS would show:** "better than a no-information GARCH-t martingale even at a −1%/yr drift,
  if the volatility model holds". It would **not** show that deceleration is what works: the PASS
  wording says "deceleration-specific: not tested".
  - The placebo printed beside it is a diagnostic, not a certificate. It matches or beats the rule in
    only about 3 in 10 of the PASSes a generic reversal would earn (G6).
  - v1's draft claimed that no unbiased comparator exists on one series. The statistics review showed
    that a placebo logged forward against the same null matches the rule's nuisance bias within
    ±0.006. Its point comparison after a PASS is still biased toward the rule (stats re-check S2).
- **The model null** assumes a stable GARCH-t. Its drift is bracketed at ±1%/yr, but the volatility
  model is not.
  - Under the fit window's own latest decade (2016–26 volatility) plus a −1%/yr drift, a false PASS
    runs about 0.07 (G6).
  - Beyond the drift bracket, −2%/yr gives up to 0.09.
  - G6 also reports vol-level and persistence rows.
- **The 3% / 250-day hit** was inherited from the 2006+ sweep. It is frozen, but it was not chosen
  blind.
- **DTWEXBGS** is published at about T+5 and revised about annually. S1 is measured from the data
  date and scored on the maturity vintage; both vintages are recorded.
- **The onset rule** was designed by people who know 2000–2026, so its historical count (§5.5) is a
  degeneracy check, not validation. The check's OFR P95 used revised history. Forward, the rule uses
  as-published history at each month's close (§5.6).
- **The in-sample record** (1 clean, 2 first-wave misses; monthly null 3/10 vs 42%) stays on the panel
  permanently.

## 9. Pending questions (60-day expiry from each first ask)

| Pri | # | Question | Status |
|---|---|---|---|
| P1 | Q1 route | forward_only | **answered 2026-11-02** |
| P1 | Q2 list | C16 primary; A25 and strict-15 robustness; L5 reported only | **answered** |
| P1 | Q3 variant | UNPATCHED primary; re-arm logged | **answered** |
| P1 | Q5 onset rule | mechanical 2-of-5 | **answered**; the §5.4 check is done (§5.5) |
| P2 | Q6 colour / notification | D3_only | **answered** |
| P3 | Q14–Q16 | JPY/CHF not run; pre-1971 not run; C26 not in C16 | **answered** |
| — | Q4, Q7–Q13 | D-1 / D-2 design | **not applicable: route forward_only** |
| P1 | Q19 (new) | Keep the drift bracket as frozen (PASS judged at −1%/yr, FAIL at +1%/yr)? It costs power in calm markets (+0.20 edge: 0.43 → 0.24) and makes INCONCLUSIVE the likely end with no edge. Without it, a −1%/yr trend roughly doubles the false-PASS rate. It does not cover a volatility-regime shift: under 2016–26 volatility plus −1%/yr, a false PASS runs about 0.07. The stronger option judges PASS on the larger p⁻ of the full-window fit and a frozen 2016–26 fit: false PASS about 0.04 in that case, but power at +0.20 falls from about 0.39 to 0.26 (stats re-check S1). | asked 2026-11-03; **default: the bracket as frozen** |
| P2 | Q17 | Accept the redesigned D-3 (GARCH-t null; exact alpha spending at 8 / 16 / 24; FAIL at δ_U < 0.10, 98.3%; the placebo beside it)? | asked 2026-11-02; the default in this SPEC |
| P2 | Q18 | Keep the 12-month exclusion from the last onset (§5.5), or count it from the last month with ≥ 2 markers? | asked 2026-11-02; default keep (frozen) |

Any change to Q17–Q19 is post-hoc and needs a new SPEC version. No forward unit exists yet, so a change
made before the first admitted unit could not have been steered by forward outcomes. The new version
would say so.

## 10. Run order

1. SPEC v1 → two reviews (PASS_WITH_FIXES) → fixes → re-check → **freeze** (this commit; `freeze.json`
   carries this file's sha256).
2. **R1, monthly:**
   - review the Fed list through the previous month, with a second reader, and redeploy;
   - the panel dates the month at its close (§5.6);
   - download and commit the ledger snapshot; `admit` any unknown row; rebuild the `units`;
   - compute p_u for any new unit start (harness plus a second reader).
3. **R2, quarterly:** the unit count. A look happens only at 8 / 16 / 24 matured units.
4. **Before the first unit is scored:** re-run the full G6 (2,000 paths on every row).
5. **Each look:** the harness result plus two independent verifiers, then the consequence per §3.5 and
   a redeploy of **treasury-canary**.

## Appendix A — withdrawn (not run; examined only as listed in §1)

| Withdrawn | Reasons (reviews of SPEC v0 and the v1 draft) |
|---|---|
| D-1 currency cross-section | **The null is biased:** its random-rule benchmark scores T < 0 on martingales, and INVERSE appears 24–28% of the time with no information (stats v0 B1). **PASS is close to unreachable:** 0–6% at realistic edges, because the share bar, the T ≥ 0.15 bar and 52–56% zero-D firings combine (stats v0 B2). **Units overlap** (S1). **The transposition is not the frozen rule:** it loses 2010-06 and 2012-06 and adds 2015 policy rallies (S2). **"Floating" includes ~150–200 currency-years of pegs or crawls** (stats v0 S3, data v0 S3). **The clean subset is mostly seen**, through finder B's 7 windows, 14 anchor spans and DTWEXBGS components (data v0 B1). **Survivorship biases it toward PASS** (data v0 S4). |
| D-2 ICE DXY daily 1973–2005 | Its outcome already exists at monthly resolution (`decel_monthly_oos.json`, speed episodes, peak months), so it is pseudo-OOS (data v0 S2). Its gate scale was set from 2006–26 data (stats v0 S2). FAIL happens 86–95% of the time with no information (stats v0 B2). |
| v0 random-rule benchmark | E_f is a look-ahead set and omits the yield condition (stats v0 B1, M3a). Replaced by §3.3. |
| v0 D-3 (one look at n = 12, T ≥ 0.15) | P(PASS) falls as n grows. It had no FAIL or INCONCLUSIVE and no look schedule (stats v0 B2, M3e). Replaced by §3.4. |
| v1-draft D-3 (zero-drift null, Bonferroni looks, a 95% FAIL bound) | A ±1%/yr trend moves size and power by about as much as the edges it hopes to detect (false PASS 0.062 at −1%/yr); FAIL fired 0.40 of the time under the fit window's +0.9%/yr drift; Bonferroni spent only 0.016–0.027 (stats v1 S1, minors 2–3). Replaced by the bracket and exact spending (§3.3–3.4). |

### Counter-agent log

| Review | Verdict | Adopted |
|---|---|---|
| statistics and design, SPEC v0 | NOT_PASS (2 BLOCKING, 3 SERIOUS) | B1 (centred, surrogate-calibrated null), B2 (D-3 classes, looks, precision FAIL), S1 (merge < 250), M3a/e, M5; D-1/D-2 withdrawn |
| data, look-ahead and contamination, SPEC v0 | NOT_PASS (1 BLOCKING, 6 SERIOUS) | B1 and S2 (D-1/D-2 withdrawn), S5 (calendar stated), M1 (last-day evaluation, G1b), M2 (vintages, C2/C13), M4 (OFR as published, C7), N5 (C10) |
| statistics and design, SPEC v1 draft | PASS_WITH_FIXES (0 BLOCKING, 3 SERIOUS, 5 MINOR) | S1 (drift bracket, binding G6 rows, sensitivity table, Q19), S2 (placebo beside any result; §8 corrected), S3 (calendar DTWEXBGS ∩ DGS10, succession §2.1); minors 1–5 (G6 specified, exact spending, the 98.3% FAIL bound, the calendar range, definitions) |
| data, look-ahead and point in time, SPEC v1 draft | PASS_WITH_FIXES (0 BLOCKING, 3 SERIOUS, 5 MINOR) | S1 (`d3_eligible`), S2 (§5.6 month rows), S3 (§1, §7 and Appendix A amended); M1 (Fed list v1.1, §5.7), M2 (maturity after subtypes), M3 (live-only anchor wording), M4 (basket staleness, field-by-field freezing), M5 (hash-checked harness) |
| statistics re-check of the fixes | PASS_WITH_FIXES (0 BLOCKING, 2 SERIOUS, 2 MINOR) | S1 (the bracket holds only under the frozen volatility model: the 2016–26 rows in G6, qualifiers in §0, §3.6 and §8, the stronger option in Q19), S2 (the placebo cannot certify deceleration: a fixed PASS wording, the specific wording left to a future matched-scramble test); minors (G6's design size and the p⁻ calibration bound; P_tail notation). The spending recursion, the drift implementation, the FAIL bound and every §3.6 number were verified. |
| data re-check of the fixes | PASS_WITH_FIXES (0 BLOCKING, 1 SERIOUS, 5 MINOR) | S-1 (the close the day after the release; fresh-and-complete inputs), M-A (the first-vintage outage rule, the freeze seed, `admit`, `units`), M-B (`pu-row` once, before maturity), M-C (failure surfacing, late months), M-D (`onset_first_month`), M-E (the OFR extract), N-3, N-5 |
| data confirm pass | PASS (0 BLOCKING, 0 SERIOUS, 1 MINOR) | M-1 (a lost archive is repaired by `admit`; unresolved rows are listed, not fatal), N-a (wording), N-b (`pu-row` rebuilds the units itself), N-c (the ALFRED vintage date recorded), N-d (overlap cases for the verifiers) |
