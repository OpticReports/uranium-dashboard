# Dollar watch — pre-registration SPEC v1 (FORWARD-ONLY), 2026-11-02

Status: **SPEC v1, answered, not yet frozen.** Casey answered on 2026-11-02 ("go with the defaults,
freeze it"): route `forward_only`, primary list C16, primary rule UNPATCHED (re-arm logged
alongside), the mechanical 2-of-5 onset rule, and a lamp licensed by D-3 only. It supersedes SPEC v0,
which was reviewed NOT_PASS twice (`review_stats_v0.md`, `review_data_v0.md`). Nothing about the
deceleration rule's outcomes is computed here.

## 0. Results first

| Item | Decision |
|---|---|
| What is clean | **Only data after the freeze date.** Every month of dollar history 1971–2026 has been examined (§1). |
| DECEL test | **D-3, forward only.** Units are unpatched firings merged when less than 250 index days apart. The hit is "≤ +3% further rise in 250 index days". The null is a frozen GARCH(1,1)-t martingale conditioned on the state at the firing (surrogate-calibrated, centred). The test is an exact Poisson-binomial with looks at 8 / 16 / 24 matured units. |
| Power | About 0.24 units a year (5 in sample over 20.5 y). **First look ~2060, last ~2125.** P(PASS by the last look): 0.02 with no edge, 0.43 at +0.20, 0.80–0.83 at +0.30, 0.97–0.99 at +0.40 (§3.6). |
| MOM | **Descriptive and logged; never tested.** The bar at the house convention is ~40 independent episodes, about 400 years. |
| Colour or lamp | **Only a D-3 PASS** licenses one neutral colour state on layer 3(a) and a lamp. The wording is always "dollar scramble peaking", never "subsided". |
| Onset rule | Mechanical 2-of-5 (§5), with its degeneracy check pre-committed in §5.4 before the count was run. The result is in §5.5. |
| D-1 / D-2 | Withdrawn (Appendix A). |

## 1. Contamination statement

**All dollar history is seen.** Specifically:
- ICE DXY 1971–2026, monthly and daily: band, momentum, speed, level, quadrant; 25-crisis metrics.
- The broad dollar 2006–2026: the rule was tuned on it (in-sample, 6 / 7 firings).
- The monthly analogue on 1973–2005: scored, null.
- Finder B's 8-pair EM basket: seen across 7 windows and 14 anchor spans (data review B1).

No history-based test of DECEL or MOM is out-of-sample, and frozen parameters cannot un-see paths.
Evidence counts only from rows whose data date falls **after the freeze date** (`freeze.json`
`freeze_date`). Everything before that is shown on the panel as IN-SAMPLE and never enters D-3.

## 2. DECEL — frozen definition (as `code/decel_realtime.py` = `dollar_watch.scramble_firings`)

**Calendar.** Days on which DTWEXBGS, DGS10 and VIXCLS are all published. This is the frozen
script's calendar and the panel's `rule_index`. It differs from DTWEXBGS ∩ DGS10 only on Good
Fridays, with identical historical firings (data review S5). A day missing VIXCLS is off the
calendar, as frozen.

**Rule.** k counts days on that calendar. The rule is evaluated on **every** k ≥ 80 through the
latest available day: the panel code does this. The frozen script's `len(B)−1` bound is an
outcome-code artefact (data review M1).

| Term | Definition |
|---|---|
| roc20[k] | B[k] / B[k−20] − 1 |
| mx, kmx | the max of roc20[k−60..k] and its first argmax |
| fire (UNPATCHED, **primary**) | mx ≥ 0.04 AND roc20[k] ≤ 0.5·mx AND B[k] ≥ 0.97·max B[k−60..k] AND Y[k] < Y[max(0, kmx−20)] AND k − last_fire > 120 |
| RE-ARM (logged, descriptive) | the same, or inside the cooling window if mx ≥ 1.5·mx at the last firing |

Parameter values are frozen in `freeze.json` and asserted equal to `RULE` by a gate test.

## 3. D-3 — the forward test (DECISION)

### 3.1 Units

A unit starts at an unpatched forward firing f₁ (index k₁). Any later unpatched firing with
k − k₁ < 250 belongs to the same unit, and the unit is scored on f₁ only. The next firing with
k − k₁ ≥ 250 starts a new unit.

This makes outcome windows disjoint, so units are the clusters (stats review S1).

**Real-time admission.** A firing counts only if it fires on the first DTWEXBGS vintage that
contains its data date. That vintage is the one the panel archived at first sight (§6.1), or the one
reconstructed from ALFRED if the panel missed it. A firing that appears only after a revision is
logged and never scored.

### 3.2 Outcome (S1, primary)

hit_u = 1{ max B over index days (k₁, k₁+250] ≤ 1.03·B[k₁] }.

It is computed on the **maturity vintage**, the first one that contains k₁+250, with that vintage's
sha256 recorded. It is measured from the data date. The release-anchored version and S2–S4 / C1–C4
(§6.2) are DESCRIPTIVE. "Scramble peak" (S) and "crisis over" (C) are never merged: in 2008 the gap
was about 4 months and −25% for the S&P.

### 3.3 Null and statistic (stats review B1 fix)

**H0.** Given F_{k₁}, the daily log changes of B after k₁ follow the frozen GARCH(1,1) with
Student-t innovations and zero mean, i.e. the deceleration condition carries no information.

**The model.**
- (ω, α, β, ν) are fitted by MLE on 100·Δlog B over the rule calendar, 2006-01-03..freeze, on the
  freeze vintage.
- They are written into `freeze.json` **at the freeze, before any forward firing exists**.
- The fit uses returns only, never S1.

**p_u.**
- The Monte-Carlo probability of hit_u under H0: N = 100,000 paths of 250 steps.
- Each path starts from h_{k₁+1}, filtered with the frozen parameters through k₁ on the firing
  vintage. The seed is YYYYMMDD of k₁. MC SE ≤ 0.0016, recorded.
- It is computed **once, before the unit matures**, from the archived firing inputs only. A gate
  asserts that appending data after k₁ changes nothing.
- Conditioning on h_{k₁+1} prices the vol-timing effect (decel days sit at high conditional vol)
  that biased v0's random-rule benchmark to T < 0.

**Statistic.** At n matured units, S = Σ hit_u and T = (S − Σ p_u) / n (centred; E[T] = 0 under H0).
- p⁺ = P_PB(S′ ≥ S), exact Poisson-binomial over the recorded p_u.
- δ_U = the largest δ, on a 0.001 grid, with P_PB(S′ ≤ S | p_u + δ, clipped to [0,1]) ≥ 0.05. This
  is the one-sided 95% upper bound on the edge.

### 3.4 Looks and classes (no other look is valid)

| Look | Matured units n | PASS if p⁺ ≤ | FAIL if | Otherwise |
|---|---|---|---|---|
| 1 | 8 | 0.005 | δ_U < 0.10 | continue |
| 2 | 16 | 0.015 | δ_U < 0.10 | continue |
| 3 (final) | 24 | 0.030 | δ_U < 0.10 | **INCONCLUSIVE, final** |

- Alpha is Bonferroni-spent (0.05 in total). FAIL is a precision rule, not a bare cut, and stopping
  for futility does not inflate the type I error.
- Looks are computed at the R2 calibration after n is reached, by the harness, then checked by two
  independent verifiers.
- There is no absolute T bar and no share bar, so P(PASS) rises with n (stats review B2).

### 3.5 Consequences (what the panel may then display)

| Class | Layer 3(a) |
|---|---|
| PASS | One neutral colour state ("deceleration flag ON") **and** a lamp or notification are licensed. The text gives n, S, Σp_u, p⁺ and the look. Never "crisis subsided". The crisis-over (C) outcomes and their gap are printed beside it. |
| FAIL | Descriptive permanently, labelled "forward record: did not beat a no-information model (n, δ_U < 0.10)". No re-tuning and no new variant. The ledger continues as a record. |
| INCONCLUSIVE | Descriptive, with n, S, Σp_u and "undecided". At the final look this is permanent. |
| before look 1 | Descriptive (the status today), with the unit count shown. |

Layers 2, 3(b), 3(c), the quadrant and MOM stay DESCRIPTIVE under every outcome.

### 3.6 Power (exact; p_u assumed equal across units; the true p_u is unknown and not computed)

Years assume 0.24 units a year.

| True edge δ | p_u = 0.30: P(PASS) by look 1 / 2 / 3 | P(FAIL by 3) | p_u = 0.50: P(PASS) by look 3 | P(FAIL by 3) |
|---|---|---|---|---|
| 0 | 0.001 / 0.008 / 0.016 | 0.26 | 0.020 | 0.25 |
| +0.10 | 0.009 / 0.061 / 0.13 | 0.06 | 0.12 | 0.07 |
| +0.20 | 0.035 / 0.23 / 0.44 | 0.01 | 0.43 | 0.01 |
| +0.30 | 0.11 / 0.53 / 0.80 | 0.00 | 0.83 | 0.00 |
| +0.40 | 0.26 / 0.83 / 0.97 | 0.00 | 0.99 | 0.00 |

Calendar of looks: look 1 at ~33 y (~2060), look 2 at ~67 y, look 3 at ~100 y.

Hits needed at p_u = 0.30: 7/8, 10/16, 13/24. With no edge the record ends INCONCLUSIVE about 72% of
the time: 24 units cannot bound the edge below +0.10.

### 3.7 Gates (merge-blocking, before the first forward unit can be scored)

| Gate | Requirement |
|---|---|
| G1 | The rule reproduces the 6 unpatched and 7 re-arm frozen dates (done: data review N1). |
| G1b | Run on data truncated at each historical firing, the rule fires on the last day. |
| G6 | On 2,000 surrogate century-paths from the frozen GARCH-t, the full pipeline (rule, units, p_u at N = 20,000, looks) gives a mean of (hit − p_u) within ±0.01 and a cumulative P(PASS) ≤ 0.06. The same is reported for a constant-vol random walk and for α+β ± 0.02 (DESCRIPTIVE: robustness of the null). |
| G7 | p_u is unchanged when data after k₁ are appended. P_PB and δ_U match brute-force enumeration for n ≤ 12. |

## 4. D-4 — momentum (DESCRIPTIVE only)

**Signal.** ICE DXY monthly average (the panel's `dxy_monthly`); a month with M[t] / M[t−12] − 1 >
+0.10.

**Episode.** A signal month after the reference cut-off whose previous signal month is more than 12
months earlier (as the panel's `ledger_block` does).

**Logged.** The month and the 12m change. Outcomes:
- S&P, Baa − 10y and the broad dollar at 3 / 6 / 12 months from the first S&P close of the
  following month (as the code does);
- whether a §5 onset falls in m+1..m+12, with its subtype;
- the EM FX basket's maximum rise over 12 months (forward rows only).

**Never tested.** The panel line reads: "in-sample NSR 0.42 (monthly average; 0.51 on closes), ~5
clusters, list fixed knowing the dollar path, sign flips across lists; 0 out-of-sample episodes; a
test needs ~40 independent episodes ≈ 400 years." No colour or lamp, ever, under this SPEC.

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
`work/onset_count_2000_2026.json`.

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

Months with ≥ 2 markers: 31. The 12-month exclusion leaves 8 onsets.

**A property, recorded and NOT fixed** (it would be post-hoc). The exclusion runs from the last
*onset*, so a long crisis re-dates itself at month 13:
- 2009-01 is the GFC 13 months after 2007-12; Lehman (2008-09) falls inside the exclusion.
- 2002-07 is 15 months after 2001-04; 9/11 (2001-09) falls inside the exclusion.

Forward, that can label a crisis continuation as a new onset in the MOM outcome. Only Casey may
change it, in a new SPEC version, labelled post-hoc (Q18). No DECEL outcome was computed.

## 6. The ledger — what must be recorded

### 6.1 At firing (scramble_rule row; appended the first time the panel sees it)

**Already in the code:** `kind`, `date` (the data date k), `variants`, `roc20_max_pct`,
`roc20_max_date`, `roc20_now_pct`, `dollar`, `h10_release` and `recorded_on`.

**Added:**
- `k` and the calendar label;
- the clause values: `y10_now`, `y10_ref`, `y10_ref_date`, near-high ratio;
- `unit_first` and `index_gap_to_unit_first`;
- `inputs`: the sha256, last observation and fetch time of the DTWEXBGS, DGS10 and VIXCLS bytes,
  **archived** to the ledger directory under their hash;
- `first_vintage_contains_date` (true / false);
- later, the `p_u` record: value, N, seed, MC SE, GARCH parameter hash, computed_on.

### 6.2 At maturity (written once, `outcomes_frozen["250d"]`)

**D-3:**
- S1 hit; max B and its date; the further rise %;
- the maturity vintage sha256.

**Descriptive:**
- S1 anchored at the first index day after `h10_release`;
- S2, days to the 250-day max of B;
- S3, the 5-obs-mean CP − bill max over (k, k+60] ≤ its value at k;
- S4, gold's min over (k, k+60] ≥ 0.97·gold[k];
- C1, the S&P 250-day forward min ≥ −10%;
- C2, the first VIX close < 25, and whether VIX re-exceeds VIX[k] within 60 days;
- C3, the EM FX basket's 250-day extreme date;
- C4, days to the S&P 250-day low.

The existing 3 / 6 / 12-month S&P, Baa − 10y and broad-dollar outcomes from the code's anchor stay
as they are.

### 6.3 Revision checks, onset rows and momentum rows

**Revision checks.** On every build, each live row gets an entry in `revision_checks`
{checked_on, still_fires} when its status changes. Rows are never deleted.

**Onset rows** (`kind: "onset"`, monthly):
- the markers tripped, with their dates and values;
- the OFR P95 thresholds and the `fsi.csv` sha256 (as published, archived);
- the Fed action URLs;
- the subtype (pending, then frozen).

**Momentum rows** (§4): as the code, plus `onset_within_12m` and the EM FX field.

## 7. The panel code (`backend/app/metrics/dollar_watch.py`) against this SPEC

**Matches and is adopted:**
- `scramble_firings`, including last-day evaluation;
- the `rule_index` calendar;
- the append-only ledger keyed by (kind, date), with `recorded_on`;
- `freeze_matured`, write-once;
- the anchor at the first S&P close strictly after max(H.10 release, recorded_on), for descriptive
  outcomes;
- the momentum gap > 12 months;
- EM FX withheld on historical rows.

**Changes the SPEC requires:**

| # | Change |
|---|---|
| C1 | Unit assignment on scramble_rule rows (`unit_first`, `index_gap_to_unit_first`; < 250 index days merges; re-arm-only rows are never units). |
| C2 | Archive the DTWEXBGS / DGS10 / VIXCLS bytes at first sight, under their sha256. Record `inputs`, `k`, the calendar, the clause values and `first_vintage_contains_date`. |
| C3 | A `revision_checks` append when a live row's fire status changes on a new vintage. Never delete. |
| C4 | A `250d` maturity block (§6.2) frozen through `freeze_matured`, with maturity on index days, not calendar months. |
| C5 | `h10_release`: when the Monday is a federal holiday, the release is the next business day. Verify against the H.10 release page and record `h10_release_source`. |
| C6 | The onset evaluator (§5) and `kind: "onset"` rows. Ship `fed_emergency_actions.json` into `backend/app/sources/`, with a gate test that every URL is federalreserve.gov and the list is date-sorted and append-only. |
| C7 | Archive the OFR `fsi.csv` bytes per evaluation, and compute P95 on as-published history (data review M4). |
| C8 | Momentum rows get `onset_within_12m` (matured at m+12) and the EM basket 12-month max rise on forward rows only. |
| C9 | Allow EM FX outcomes on **forward** rows (post-freeze data). Historical rows and `dollar_reference.json` stay withheld. |
| C10 | Text: PENDING P1s become "answered 2026-11-02". The HONESTY_LIVE line "freeze waits on Casey's answers" becomes "frozen <date>; forward-only; first D-3 look at 8 matured units (~2060)". `variant_live` becomes "unpatched = frozen primary; re-arm logged". |
| C11 | Freeze constants: `FROZEN_ON` = `freeze.json` freeze_date; a gate test that `RULE` equals `freeze.json` rule params; carry the SPEC v1 sha256 and the GARCH parameter hash. |
| C12 | p_u: offline harness `studies/dollar_watch/prereg/d3.py`, computed from the C2-archived inputs only, before maturity (gate G7). The backend stores the value; it never computes it. |
| C13 | Repo housekeeping (data review M2): commit `studies/dollar_watch/data/fred/` with SPEC v1. Store the GARCH fit inputs (the freeze-vintage DTWEXBGS bytes) by sha256. |

## 8. Honesty box

- **The only clean evidence is the future.** It needs ~33 years to the first look and ~100 to the
  last, and with no edge it most likely ends INCONCLUSIVE.
- **What a PASS would show:** "better than a no-information GARCH-t martingale", **not** "better
  than any near-high day in a scramble". v0's random-day benchmark was biased (stats review B1) and
  has no unbiased replacement on one series.
- **The model null:** it assumes zero drift and a stable GARCH-t. G6 reports its size under a
  constant-vol random walk and under perturbed persistence.
- **The 3% / 250-day hit** was inherited from the 2006+ sweep. It is frozen, but it was not chosen
  blind.
- **DTWEXBGS** is published at about T+5 and revised about annually. S1 is measured from the data
  date and scored on the maturity vintage; both vintages are recorded.
- **The onset rule** was designed by people who know 2000–2026; its historical count (§5.5) is a
  degeneracy check, not validation. The OFR P95 may be computed on revised history in the check;
  forward it uses as-published history (C7).
- **The in-sample record** (1 clean, 2 first-wave misses; monthly null 3/10 vs 42%) stays on the
  panel permanently.

## 9. Pending questions (60-day expiry from 2026-11-02)

| Pri | # | Question | Status |
|---|---|---|---|
| P1 | Q1 route | forward_only | **answered 2026-11-02** |
| P1 | Q2 list | C16 primary; A25 and strict-15 robustness; L5 reported only | **answered** |
| P1 | Q3 variant | UNPATCHED primary; re-arm logged | **answered** |
| P1 | Q5 onset rule | mechanical 2-of-5 | **answered**; the §5.4 check is pending (§5.5) |
| P2 | Q6 lamp | D3_only | **answered** |
| P3 | Q14–Q16 | JPY/CHF not run; pre-1971 not run; C26 not in C16 | **answered** |
| — | Q4, Q7–Q13 | D-1 / D-2 design | **not applicable: route forward_only** |
| P2 | Q18 (new) | Keep the 12-month exclusion from the last onset (frozen; re-dates long crises at month 13, §5.5), or count it from the last month with ≥ 2 markers? Any change is post-hoc and needs a new SPEC version | asked 2026-11-02; default keep (frozen) |
| P2 | Q17 (new) | Accept the D-3 redesign (GARCH-t null; looks at 8 / 16 / 24; FAIL at δ_U < 0.10) in place of v0's D-3? | asked 2026-11-02; the default in this SPEC |

## 10. Run order

1. SPEC v1 → one reviewer on §3 and §5 (the D-3 null and the onset rule) → freeze.
2. Freeze: commit `freeze.json` with the SPEC v1 sha256, the GARCH fit and the hashes. Make the code
   changes C1–C13; gates G1, G1b, G6 and G7 green.
3. Forward ledger live: R1 monthly (Fed list update, onset evaluation, p_u for any new unit); R2
   quarterly (unit count; a look only when n reaches 8 / 16 / 24).
4. Each look: the harness result plus two independent verifiers, then the consequence per §3.5 and
   a redeploy of **treasury-canary**.

## Appendix A — withdrawn (not run; the data stay unexamined)

| Withdrawn | Reasons (reviews of SPEC v0) |
|---|---|
| D-1 currency cross-section | **The null is biased:** its random-rule benchmark scores T < 0 on martingales, and INVERSE appears 24–28% of the time with no information (stats B1). **PASS is close to unreachable:** 0–6% at realistic edges, because the share bar, the T ≥ 0.15 bar and 52–56% zero-D firings combine (stats B2). **Units overlap** (S1). **The transposition is not the frozen rule:** it loses 2010-06 and 2012-06 and adds 2015 policy rallies (S2). **"Floating" includes ~150–200 currency-years of pegs or crawls** (stats S3, data S3). **The clean subset is mostly seen**, through finder B's 7 windows, 14 anchor spans and DTWEXBGS components (data B1). **Survivorship biases it toward PASS** (data S4). |
| D-2 ICE DXY daily 1973–2005 | Its outcome already exists at monthly resolution (`decel_monthly_oos.json`, speed episodes, peak months), so it is pseudo-OOS (data S2). Its gate scale was set from 2006–26 data (stats S2). FAIL happens 86–95% of the time with no information (stats B2). |
| v0 random-rule benchmark | E_f is a look-ahead set and omits the yield condition (stats B1, M3a). Replaced by §3.3. |
| v0 D-3 (one look at n = 12, T ≥ 0.15) | P(PASS) falls as n grows; it had no FAIL or INCONCLUSIVE and no look schedule (stats B2, M3e). Replaced by §3.4. |

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| statistics and design, SPEC v0 | NOT_PASS (2 BLOCKING, 3 SERIOUS) | B1 (centred, surrogate-calibrated null), B2 (D-3 classes, looks, precision FAIL), S1 (merge < 250), M3a/e, M5; D-1/D-2 withdrawn |
| data, look-ahead and contamination, SPEC v0 | NOT_PASS (1 BLOCKING, 6 SERIOUS) | B1 and S2 (D-1/D-2 withdrawn), S5 (calendar stated), M1 (last-day evaluation, G1b), M2 (vintages, C2/C13), M4 (OFR as published, C7), N5 (C10) |
| SPEC v1 | pending: one reviewer on §3 and §5 | — |
