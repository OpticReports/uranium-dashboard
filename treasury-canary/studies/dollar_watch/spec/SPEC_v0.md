# Dollar watch — pre-registration of the two candidate signals (SPEC v0, 2026-11-02)

Status: **SPEC v0, nothing scored.** Gate between the DESCRIPTIVE "Dollar watch" panel
(`studies/dollar-watch.md` §5) and any colour or lamp on it. Order: two counter-agent reviews →
SPEC v1 → Casey's freeze answers (`freeze_template.json`) → blind count → ONE scored run → two
verifiers → RESULTS. No outcome statistic has been computed on any series this SPEC calls unseen;
the FRED probe (§2.2) read dates and row counts only, then deleted the raw files.

Signals under test:
- **DECEL**: Casey's deceleration rule, frozen as `decel_realtime.py`.
- **MOM**: the 12-month DXY change > +10%.

## 0. Results first — the recommendation

| # | Decision | Recommendation |
|---|---|---|
| 1 | Is "1973–2007 fit / 2008–2026 test" on the dollar index still out-of-sample? | **No. Withdrawn** (§1). The LOCO logit is withdrawn as well: it is contaminated and cannot change any decision. |
| 2 | Primary evidence for DECEL | **Cross-section (route b): D-1.** 15 floating non-USD currencies, each scored on its own depreciation scrambles against the dollar, using the frozen rule moved into volatility units. The unit of inference is the calendar cluster. It is the only route that can reach decision grade in 2026. The evidence is **indirect** (§3.5). |
| 3 | Secondary evidence for DECEL | **D-2: ICE DXY daily, 1973-03..2005-12.** This is SEMI-CLEAN: the rule was never tuned on these years, but the dollar path is known and the monthly analogue already scored null on them (3/10 vs 42%). It runs only in combination with D-1 (§4 table). |
| 4 | The clean test of the dollar-index signals | **D-3: forward ledger from the freeze date.** It is logged from day one. It reaches decision grade in **~40–80 years** for DECEL and **~180 years** for MOM (§2.1). It is a record, not a near-term test. |
| 5 | MOM | **No unseen evidence exists.** MOM stays DESCRIPTIVE, keeps its in-sample caveats and goes into the forward ledger. **No colour under this SPEC.** |
| 6 | Route (c): JPY/CHF safe-haven scrambles, pre-1971 data | **Not run** (§2.3). n ≤ 8, partly seen, and a different mechanism direction. Pre-1971 rates were pegged and are monthly. |
| 7 | Crisis list | **C's 16 (L-broad) primary** (P1 Q2). D-1, D-2 and D-3 do not use the list (by design); it only moves the base rates on MOM and on the panel. |

Cost: about one day of build plus the run, then two verifiers. The best case licenses **one neutral
colour state on layer 3(a)**. A lamp is licensed only by D-3 (§4).

## 1. Contamination ledger — what has already been seen

| Segment | Examined by | What was computed | Status |
|---|---|---|---|
| ICE DXY monthly 1973–2026 | finders A, C; scoping; both reviewers | band, 6/12m momentum (NSR 0.42), speed, level, quadrant, on 25/16/15/12/7/5 lists | **SEEN** |
| ICE DXY daily 1971–2026 | finder A, reviewer 1 | 25-crisis eve/peak metrics, excursions, 1998/2008/2020/2022 paths. The daily DECEL has **not** been run on it. | **SEMI** (rule unseen, path seen) |
| Fed broad DTWEXBGS daily 2006–2026 | scoping, reviewer 2 | DECEL tuned here; sweep optimum; 6 / 7 firings | **IN-SAMPLE** |
| Fed major-currencies index monthly 1973–2005 | scoping | monthly DECEL analogue: 10 firings, peak ±3m in 3 vs 42% base, S&P up 12m 6/10 vs 76% | **SEEN; the one clean prior test, and it was NULL** |
| EM FX basket (BRL, MXN, ZAR, INR, KRW, THB, CNY, MYR, equal weight) | finder B | trough dates in the 2008, 2015–16, 2018, 2020 and 2022 windows; current percentile | **SEEN in aggregate for those 5 windows** |
| Each DEX* pair, own scrambles, any rule | nobody | — | **UNSEEN** (except the aggregate above and CAD/SEK as DXY components) |
| JPY, CHF | finder A (USDJPY 1998), finder B (alarms in 5 windows) | event dates | **SEMI** |

Plain statement: **no dollar-index history is left on which DECEL or MOM can be tested out of
sample.** Frozen parameters limit researcher freedom, but they cannot un-see the 1985, 2001 or 2008
dollar paths. Finder C's full-sample NSR table already includes 2008–2026. A threshold "fit on
1973–2007" by people who have read that table is a pseudo-OOS exercise and is **withdrawn**. The
only evidence nobody here has looked at is (i) the future and (ii) single currencies' own scrambles.

## 2. Evidence routes evaluated

### 2.1 (a) Forward ledger — clean, slow

Assumptions: the frequency-matched benchmark hit rate is p0 ≈ 0.35 (unknown; deliberately not
computed). The test is one-sided, α = 0.05, power 0.8. One firing per episode, since the cooling
period is 120 days.

| Signal | Forward rate | True edge | Firings needed | Years to decision |
|---|---|---|---|---|
| DECEL unpatched | 6 per 20.8 y = 0.29/y | 0.70 vs 0.35 | ~12 | **~41** |
| DECEL unpatched | 0.29/y | 0.60 vs 0.35 | ~23 | **~79** |
| DECEL unpatched | 0.29/y | 0.50 vs 0.35 | ~65 | ~220 |
| DECEL, only firings in genuine dollar-funding scrambles | ~5 per 53 y = 0.09/y | 0.70 vs 0.35 | ~12 | ~130 |
| MOM (12m > +10%, independent episodes) | ~5 clusters per 53 y ≈ 0.1/y | finder C's bar: ~18 alarm episodes | ~18 | **~180** |

For any crisis list, doubling the onset count takes ~53 years. Verdict: log the ledger from the
freeze day. It decides nothing within a working life unless the edge is large.

### 2.2 (b) Cross-section of currencies — unseen, indirect, powered for a large effect

Probe on 2026-11-02 (fredgraph.csv; dates and row counts only; hashes are in `probe_manifest.txt`; raw
files deleted). All series run to 2026-10-23.

| Ccy | FRED id | From | Ccy | FRED id | From | Ccy | FRED id | From |
|---|---|---|---|---|---|---|---|---|
| BRL | DEXBZUS | 1995-01-02 | THB | DEXTHUS | 1981-01-02 | CAD* | DEXCAUS | 1971-01-04 |
| MXN | DEXMXUS | 1993-11-08 | MYR | DEXMAUS | 1971-01-04 | AUD | DEXUSAL (invert) | 1971-01-04 |
| KRW | DEXKOUS | 1981-04-13 | TWD | DEXTAUS | 1983-10-03 | NZD | DEXUSNZ (invert) | 1971-01-04 |
| ZAR | DEXSFUS | 1980-01-02 | SGD | DEXSIUS | 1981-01-02 | NOK | DEXNOUS | 1971-01-04 |
| INR | DEXINUS | 1973-01-02 | LKR | DEXSLUS | 1973-01-02 | SEK* | DEXSDUS | 1971-01-04 |

\* CAD and SEK are DXY components: partly seen, so they are excluded from the "clean" subset.

Excluded:
- CNY (DEXCHUS 1981+): managed or pegged.
- HKD (DEXHKUS): pegged since 1983.
- VEF (DEXVZUS 2000+): pegged.
- DKK: EUR peg.
- EUR and GBP: reserve currencies and DXY's core.
- JPY and CHF: route (c).

Not on FRED daily: TRY, IDR, ARS, RUB. The classic crisis currencies are missing, which biases the
sample toward milder episodes (honesty box).

Power from first principles (no outcome looked at):
- Sample: 1973-03 onward, minus a 3-year σ warm-up, minus pegged spans, minus the last 250-day
  outcome window. That leaves ~650 eligible currency-years out of ~734 raw.
- Episodes: the gate is 2.7σ of a 20-day move, one-sided, with fat tails and vol clustering. That
  gives ~0.2–0.5 episodes per currency-year, so **~130–325 episodes**.
- Firings: the rule fires in ~60–75% of episodes (ASSUMED: the dollar's gate-episode
  count was never tabulated), so **~80–240 firings**.
- Clusters: firings fall into **K ≈ 20–35** clusters. There are ~18–22 known global or regional
  stress windows 1976–2026 (1980–82, 1984–85, 1992, 1994–95, 1997–98, 2000–01, 2008, 2011, 2013,
  2014–15, 2018, 2020, 2022, 2024–25 …) plus idiosyncratic singletons.
- Detectable effect: the cluster difference D_c has sd ≈ 0.35–0.45. The minimum detectable mean
  edge (80% power, α 0.05 one-sided) is 2.49·sd/√K, which is **+0.15 to +0.25 hit rate over the
  matched random rule**. A smaller true edge will read INCONCLUSIVE.

### 2.3 (c) Other candidates

| Candidate | Verdict | Why |
|---|---|---|
| JPY / CHF safe-haven (appreciation) scrambles | **not run** | The yen carry unwind is the same mechanism with a different funding currency, but there are ~5–8 episodes each in two series, and they are partly seen (finder A 1998, finder B alarms). Even a sign is beyond reach at that n. Logged as a P3 question. |
| Pre-1971 (Bretton Woods, interwar sterling) | **not run** | Pegged regimes, monthly data, no free daily series, fewer than 5 funding scrambles |
| DTWEXM daily 1973–2005 or DTWEXB daily 1995–2005 (Fed indices) | **not run separately** | They carry the same information as D-2 (DTWEXM is the daily version of the monthly null). DTWEXM is the fallback if ICE DXY fails a gate. |
| DXY daily 1973–2005 | **run as D-2, SEMI-CLEAN** | It is the only dollar-side history the daily rule has not touched |

## 3. Frozen definitions

### 3.1 Crisis lists (committed as CSVs with sha256 at the freeze)

| List | n | Onsets (month) | Role | Base P(onset ≤ 12m) |
|---|---|---|---|---|
| **C-16 "L-broad"** (finder C §3.1) | 16 | 1974-06, 1982-08, 1987-10, 1992-09, 1994-12, 1997-07, 1998-08, 2001-02, 2008-09, 2010-05, 2013-05, 2015-08, 2018-08, 2020-03, 2022-09, 2023-03 | **PRIMARY (default, P1 Q2)** | 29% |
| A-25 (`data/crises.csv`, is_crisis = 1) | 25 | C01 1973-10, C02 1976-03, C03 1980-01, C04 1982-08, C05 1984-05, C07 1987-10, C08 1989-08, C09 1992-09, C10 1994-02, C11 1997-07, C12 1998-08, C13 2000-03, C14 2007-08, C15 2010-04, C16 2013-05, C17 2014-06, C18 2018-04, C19 2019-09, C20 2020-02, C21 2021-09, C22 2022-01, C23 2023-03, C24 2024-07, C25 2025-04, C26 2026-02 (open) | robustness | 42% |
| V1-strict-15 | 15 | A-25 minus C02, C05, C16, C18, C19, C21, C23, C24, C25, C26 | robustness | 27% |
| V1-strict-12 | 12 | strict-15 minus C09, C17, C22 | robustness | 22% |
| **L-narrow** (dollar-funding squeezes) | 5 | 1982-08, 1998-08, 2008-09, 2020-03, 2022-09 | **reported, never inferred on** | 9% |

What the choice moves:
- **Nothing in D-1, D-2 or D-3.** They score on the dollar's or the currency's own path.
- The base rates printed beside MOM and the quadrant counts. For MOM: 48% vs 29% (C-16, in-sample);
  28% vs 42% on A-25 (6m, real DXY); 2/15 vs 9% on L-narrow.
- Which list the forward onset rule (§3.6) emulates.

Choosing A-25 makes every signal look uninformative (48% of months sit inside a crisis window).
L-narrow supports no inference at any n we will see. C26 (the 2026 Hormuz shock) is not in C-16
because it has no dollar-funding stress (P3 Q16).

### 3.2 DECEL — the dollar rule, frozen as `code/decel_realtime.py`

Series and calendar: B = DTWEXBGS daily; Y = DGS10. The calendar is the days on which DTWEXBGS,
VIXCLS and DGS10 are all present (as the script has it; reviewer 1 N4: one day off decel_test's
calendar in 2008). k counts trading days on that calendar.

| Term | Definition |
|---|---|
| rate of climb | roc20[k] = B[k] / B[k−20] − 1 |
| scramble size | mx = max roc20[k−60 .. k]; kmx = its argmax |
| **gate (scramble exists)** | mx ≥ **0.04** |
| deceleration | roc20[k] ≤ **0.5** · mx |
| near the high | B[k] ≥ **0.97** · max B[k−60 .. k] |
| safe-haven type | Y[k] < Y[max(0, kmx − 20)] |
| eligibility | k ≥ 80 |
| **UNPATCHED** | fires if all of the above hold and k − last_fire > **120** |
| **RE-ARM** | the same, **or** inside the cooling window if mx ≥ **1.5** · mx at the last firing (added after the 2008-09-22 miss) |

Committed record, IN-SAMPLE (never decides anything):
- Unpatched, 6 firings: 2008-09-22, 2010-06-03, 2011-11-01, 2012-06-07, 2020-04-09, 2022-07-28.
- Re-arm adds 2008-11-06, for 7 firings.
- **Primary = UNPATCHED** (P1 Q3). RE-ARM is reported in every table and can never rescue a fail.
- Observability: H.10 publishes at ≈ T+5. The ledger stamps both the data date and the first
  observable date. Outcomes are measured from the data date, with a T+5 sensitivity row.

**Transposition to another series X** (D-1, D-2). The scale is s = σ_X / σ_B, where σ is the sd of
daily log changes.
- σ_B: DTWEXBGS, 2006-01-03..2026-10-23, a constant.
- σ_X for D-2: DXY over the same overlap.
- σ_X for D-1: currency i over the 756 trading days ending at k−61. This is backward-looking and
  excludes the scramble window, so a scramble cannot raise its own threshold.
- Clip s to [0.25, 8] and log every clip.
- Thresholds: the gate becomes 0.04·s, near-high becomes ≥ (1 − 0.03·s)·60-day max, and the hit
  tolerance becomes 0.03·s. The 0.5 decay, the 20/60/120 windows and the 1.5 re-arm factor are
  dimensionless and stay unchanged.
- **D-2 keeps the US-10y condition.**
- **D-1 drops it** (P2 Q7). It typed the dollar's rise as safe-haven. A currency's own fall has no
  US-yield analogue, and keeping it would select a global variable that tightens clustering. The
  with-yield variant is reported, DESCRIPTIVE only.
- X is quoted so that up = USD stronger, i.e. local currency per USD. AUD and NZD are inverted.
- Peg filter: a currency-day is eligible only if under 50% of its daily changes over the trailing 60
  days are exactly zero and σ_X > 0. Missing H.10 days are dropped, never filled.

### 3.3 MOM (descriptive only)

M = ICE DXY monthly average (finder C basis; month-end close as the robustness row). The signal
month is t with M[t] / M[t−12] − 1 > +0.10. A ledger episode is the first such month after at
least 6 months at or below +10%. Each episode is logged with outcomes at 12m:
- onset by the §3.6 rule;
- the EM FX basket's maximum drawdown;
- the change in Baa − 10y.

### 3.4 Outcomes — two tracks that are never merged

The reviewers' central point: in 2008 the trigger (11-06), funding spreads halving (10-17) and the
gold trough (11-12) were all ~4 months, and −21% to −28%, ahead of the equity low (2009-03-09).

| Track | Code | Definition (from firing day k; h = trading days) | Role |
|---|---|---|---|
| **Scramble peak** | **S1 (PRIMARY hit)** | max X(k, k+250] ≤ X[k]·(1 + 0.03·s): at most +3% further rise in dollar units | decides D-1 to D-3 |
| | S2 | \|days from k to argmax X[k .. k+250]\| ≤ 20 | DESCRIPTIVE |
| | S3 | funding: 5-day-mean (DCPF3M − DTB3) max over (k, k+60] ≤ its value at k, i.e. the funding peak has passed (1997+) | DESCRIPTIVE |
| | S4 | gold: min over (k, k+60] ≥ 0.97·gold[k] (daily 2000+; monthly before, flagged) | DESCRIPTIVE |
| **Crisis over** | C1 | S&P 500 min over (k, k+250] ≥ −10% of S&P[k] | DESCRIPTIVE |
| | C2 | days to the first VIX close < 25 (1990+), and whether VIX re-exceeds VIX[k] within 60 days | DESCRIPTIVE |
| | C3 | days from k to the EM FX basket's 250-day extreme (1995+) | DESCRIPTIVE |
| | C4 | days from k to the S&P 250-day low, plus the GAP: C4 minus the S1/S2 timing, printed per firing | DESCRIPTIVE |

**No result on the crisis-over track licenses "crisis subsided", now or under any outcome.** It is
on the forbidden list.

### 3.5 Benchmark, episodes, clusters, test statistic

- **Episode** (per series): a maximal run of gate-on days, merging runs less than 20 trading days
  apart.
- **Benchmark = a random rule with the same firing frequency and the same scramble gate.** For each
  firing f there is an eligible set E_f: gate-on AND near-high days in f's episode, more than 120
  days after the previous firing (the same cooling), with the firing day included.
  - p_f is the mean of S1 over E_f. It is computed **exactly** by enumeration: no seed, no
    sampling.
  - The only thing the rule adds over p_f is the deceleration condition, so this isolates Casey's
    hypothesis.
  - A weaker benchmark (gate-on only, without near-high) is reported, DESCRIPTIVE.
- **Clusters** (D-1). Single linkage of firing dates across currencies with a gap of ≤ 126 US
  trading days.
  - If any cluster spans more than 24 months at the blind count (§5), calendar-year clusters become
    primary. That switch is mechanical and decided blind.
  - **Global cluster**: at least 5 distinct currencies fire.
  - **Clean firing**: outside the five windows finder B examined (2007-06..2009-06, 2015-06..2016-03,
    2018-03..2019-01, 2020-02..2020-06, 2022-01..2022-12) and not CAD or SEK.
- **Statistic.**
  - D_c = mean over the firings in cluster c of (S1_f − p_f).
  - T = mean over clusters of D_c.
  - p = exact one-sided sign-flip over the K cluster values. Full enumeration if K ≤ 26; otherwise
    10⁶ draws with seed 20261102, recorded.
  - Also reported: the leave-one-cluster-out min and max of T; the share of clusters with D_c > 0;
    T_global; T_clean.
  - In D-2 and D-3 each firing is its own cluster (≥ 120 days apart on one series).
- **How indirect D-1 is.**
  1. The bilaterals are the *components* of the broad dollar. Global clusters are the dollar
     scramble seen from the borrower side; singletons are local events with no dollar content.
  2. Vol-scaling and dropping the yield condition are two transposition choices made now by an
     author who has read finder B's aggregate EM-FX trough dates.
  3. A component's trough is not the index's peak (dispersion).

  A D-1 pass is therefore **direct evidence about EM currencies' own troughs and second-hand
  evidence about the dollar**. It licenses the dollar gauge only if T_global > 0 and T_clean > 0
  (§4).

### 3.6 Forward ledger and the forward onset rule (D-3, D-4)

**The ledger.** It is append-only from the freeze date: one row per firing and per MOM episode, each
row hashed. A row records:
- the data date, the observable date, the readings, and both variants;
- E_f and p_f, filled when the episode closes;
- S1–S4 and C1–C4 at h = 20/60/120/250.

Rows are scored only when their 250-day window closes. R1 (monthly) appends. R2 (quarterly) reports
counts only, until the D-3 threshold n is reached.

**Forward onset rule** (mechanical, P1 Q5). An onset is the first month in which at least 2 of the
following 5 hold, with no onset in the prior 12 months:
1. VIXCLS ≥ 40 on any day;
2. OFR FSI total above its trailing-5-year 95th percentile for 5 consecutive days;
3. EM FX basket (finder B's 8 pairs, up = weaker) +10% over 63 trading days;
4. S&P 500 ≥ 20% below its 252-day high;
5. a Fed emergency action (a 13(3) facility, a new or expanded swap line, or an intermeeting cut),
   logged from federalreserve.gov.

It is marked *dollar-funding* (the L-narrow analogue) if SWPT exceeds $50bn within 3 months, or the
5-day CP − bill exceeds 1.00pp. Its agreement with the historical lists is **deliberately not
computed**; that would invite tuning. Onsets added by judgment are logged as "judgment" and never
scored.

## 4. Pre-registered decisions and their consequences

Every results column is tagged DECISION or DESCRIPTIVE. A descriptive number is never quoted as a
pass or a fail.

**D-1 Cross-section** (UNPATCHED, S1, all clusters; DECISION). Defaults are pending P1 Q4.

| Class | Condition | What the panel may display |
|---|---|---|
| UNDERPOWERED | K < 15 at the blind count | Nothing is scored, and **the data stay unseen** for a later run. Layer 3(a) stays descriptive. |
| **PASS** | T ≥ +0.15 AND p ≤ 0.05 AND every leave-one-out T > 0 AND ≥ 60% of clusters have D_c > 0 | **EM row:** per-currency "past its deceleration point" flags may carry one neutral colour state, with K, T and p beside them. **Dollar layer 3(a):** see the D-1 × D-2 table; requires T_global > 0 AND T_clean > 0. |
| INCONCLUSIVE | none of the other classes | Layer 3(a) stays descriptive with T, its leave-one-out range and "MDE ≈ +0.15–0.25; smaller edges undetectable". No colour. |
| FAIL | T < +0.05 (and not INVERSE) | Layer 3(a) stays descriptive **permanently on this route**, labelled "transposed rule did not beat a matched random rule on N currencies × K clusters". Only D-3 can reopen it. No re-tuning, no alternative transposition. |
| INVERSE | T ≤ −0.10 AND lower-tail p ≤ 0.05 | The gauge text becomes "deceleration has marked a FIRST wave more often than the extreme (K clusters)", printed beside the 2008-09-22 and 2022-07-28 misses. No colour. |

**D-2 DXY daily 1973-03-01..2005-12-30** (frozen rule with the 10y condition, s-scaled, UNPATCHED;
SEMI-CLEAN; DECISION only in combination with D-1).
- K_min = 6 firings; below that the result is UNDERPOWERED.
- PASS: T ≥ +0.15 AND p ≤ 0.10.
- FAIL: T < +0.05.
- INCONCLUSIVE otherwise.
- It is always printed beside the monthly null (3/10 vs 42%).

**D-1 × D-2 → dollar layer 3(a)** (only when D-1 is PASS with T_global > 0 and T_clean > 0;
otherwise the D-1 row above governs):

| | D-2 PASS | D-2 INCONCLUSIVE / UNDERPOWERED | D-2 FAIL |
|---|---|---|---|
| D-1 PASS + flags | **One neutral colour state** ("deceleration flag ON"), never green or red, never "subsided", **no lamp**. Shown with the D-1 and D-2 records and the in-sample 1-clean / 2-first-wave record. | Colour allowed, labelled "evidence from EM currencies; untested on the dollar before 2006". | **No colour on the dollar gauge.** Label: "works on EM currencies' own falls; on the dollar itself two pre-2006 nulls (monthly, daily)". The EM row keeps its colour. |

**D-0 In-sample** (DTWEXBGS 2006–2026, both variants, the same S1/p_f scoring): DESCRIPTIVE. It is
the panel's printed record in the frozen metric and never decides anything.

**D-3 Forward** (DTWEXBGS, UNPATCHED, from the freeze date). It is evaluated only once n_forward ≥
12 firings (expected around the 2060s).
- PASS: T ≥ +0.15 AND p ≤ 0.05. A PASS is **the only route to a lamp** on layer 3(a), and the lamp
  still never says "subsided".
- FAIL: the colour granted by D-1 is withdrawn.

**D-4 MOM.** There is no decision. It stays DESCRIPTIVE with "in-sample; ~5 clusters; list fixed
knowing the dollar path; sign flips across lists; NOT validated; 0 out-of-sample episodes". It is
logged in the ledger. **No colour or lamp under this SPEC**; a colour would need ~18 independent
forward episodes, ~180 years.

Not tested by this SPEC, and staying DESCRIPTIVE whatever happens: layer 3(b) funding easing,
layer 3(c) gold/EMB turning, layer 2, and the layer 1 quadrant.

## 5. Gates (merge-blocking), fixtures, freeze

| Gate | Requirement |
|---|---|
| G1 reproduction | The harness rule with s = 1 and the 10y condition on the committed DTWEXBGS raw reproduces the 6 unpatched and 7 re-arm firing dates **exactly**, along with their roc20 max, dollar further rise and VIX60 values (`data/decel_realtime*.json`). |
| G2 look-ahead | Perturbing any input after day k changes no firing at or before k. σ_X(k) uses no data after k−61. The peg filter and E_f use no forward data. |
| G3 transposition | On a synthetic V with a known peak, the firing day is as pre-computed at s = 1, 2 and 4. AUD and NZD inversion is tested. A clip of s is logged. |
| G4 blindness | The blind-count module cannot import the outcome functions. Its output is counts, spans, cluster membership and the global/clean flags only: no levels, no forward fields. |
| G5 enumeration | p_f equals a brute-force recount on fixtures. The sign-flip p equals full enumeration for K ≤ 12. |

Fixtures:
- F-XS: the 15 DEX* pairs, pulled on the run day.
- F-DXY: the committed `data/dxy_daily.csv` plus the run-day pull. They must agree on the overlap,
  per reviewer 1 item 1.1.
- F-US: DTWEXBGS, DGS10, VIXCLS, DCPF3M, DTB3, SP500 and ^GSPC daily, gold, OFR FSI.

`results.json` records the sha256 of SPEC v1, `freeze.json`, the five list CSVs, every fixture and
the code. A correction run that changes any hash is a new run.

## 6. Honesty box (stated now)

- **Contaminated:** no dollar-index history is unseen. D-2 is semi-clean. D-0 is in-sample. Only D-1
  (cross-section) and D-3 (the future) are unseen.
- **The one clean prior test was null:** the monthly analogue on 1973–2005 had the peak within ±3m in
  3 of 10 vs 42%. D-1 starts from that prior, not from the 2020 success.
- **D-1 is indirect** (§3.5). Its pass speaks first to EM currency troughs, and to the dollar only
  through global clusters.
- **Transposition freedom:** vol-scaling, dropping the yield condition, the 3-year σ window and the
  peg filter are new choices made by an author who has read the aggregate EM-FX trough dates for 5
  episodes. They are frozen before any outcome; the variants are DESCRIPTIVE.
- **Inherited tuning:** the 3% hit tolerance and the 250-day horizon came from the 2006+ sweep. They
  are frozen, but they were not chosen blind.
- **Power:** D-1 detects only a large edge (+0.15–0.25 over the random rule at the same stage of the
  scramble). D-2 has n of about 6–15. D-3 needs decades.
- **The sample misses the classic crisis currencies:** TRY, IDR, ARS and RUB are not on FRED daily.
  H.10 rates are the noon NY buying rate, not the close.
- **DTWEXBGS is published at T+5**, so "real-time" means the data date. The T+5 sensitivity row is
  shown.
- **"Scramble peak" ≠ "crisis over":** in 2008 the gap was 4 months and −25% for the S&P. No outcome
  licenses "subsided".
- **MOM has no unseen test** and stays in-sample: NSR 0.42 on the monthly average, 0.51 on closes.

## 7. Pending questions (living ledger; first asked 2026-11-02; expiry 2027-01-01)

| Pri | # | Question | Default (NOT an answer) | What it moves | Status |
|---|---|---|---|---|---|
| P1 | Q1 | Route: cross-section primary (D-1) plus DXY-daily secondary (D-2) plus a forward ledger (D-3), or the forward ledger only? | D-1 + D-2 + D-3 | whether any colour is reachable before ~2066 | asked |
| P1 | Q2 | Primary crisis list: C-16 L-broad, A-25, or strict-15? (L-narrow is reported only.) | C-16 | every base rate beside MOM and the quadrant; the onset rule's target | asked |
| P1 | Q3 | Primary DECEL variant: UNPATCHED or RE-ARM? | UNPATCHED (re-arm was post-hoc) | D-0 to D-3 decision rows | asked |
| P1 | Q4 | D-1 bars: T ≥ 0.15, p ≤ 0.05, FAIL below 0.05, INVERSE ≤ −0.10, K_min 15, leave-one-out > 0, ≥ 60% of clusters positive | as listed | the D-1 class | asked |
| P1 | Q5 | Forward onset rule: mechanical 2-of-5 (§3.6), or judgment with a log? | mechanical | every future MOM and onset ledger row | asked |
| P2 | Q6 | May D-1 PASS + D-2 PASS license a lamp, or only D-3? | only D-3 | layer 3(a) alerting | asked |
| P2 | Q7 | D-1: drop the US-10y condition (default) or keep it as primary? | drop; the kept variant is DESCRIPTIVE | D-1 episode set | asked |
| P2 | Q8 | D-1 scaling: vol-scaled with a trailing 3-year σ, or the raw 4% / 3%? | vol-scaled; raw DESCRIPTIVE | D-1 firing set | asked |
| P2 | Q9 | Currency set: the 15 in §2.2 (exclusions as listed)? | 15 | n and K | asked |
| P2 | Q10 | Clusters: single linkage at 126 trading days with a blind switch to calendar years if any span exceeds 24 months? | yes | the unit of inference | asked |
| P2 | Q11 | Global cluster at ≥ 5 currencies; clean = outside finder B's 5 windows and not CAD/SEK? | yes | the dollar-panel license flags | asked |
| P2 | Q12 | D-2 on ICE DXY (DTWEXM as the fallback), K_min 6, p ≤ 0.10? | yes | D-2 class | asked |
| P2 | Q13 | S1 horizon 250 trading days and tolerance 0.03·s? | yes | every hit | asked |
| P3 | Q14 | JPY/CHF appreciation scrambles: not run (default) or a descriptive appendix? | not run | completeness | asked |
| P3 | Q15 | Pre-1971 or interwar data: not run? | not run | completeness | asked |
| P3 | Q16 | C26 (Hormuz 2026) stays out of C-16 (no funding stress)? | out | C-16 base rate (marginal) | asked |

## 8. Run order

1. SPEC v0 (this) → **two counter-agent reviews**: statistics and design; data, look-ahead and a
   contamination audit (did anyone touch the DEX* pairs?). → SPEC v1. Nothing scored.
2. Build `studies/dollar_watch/prereg/` from pure functions, with no network in the tests. Gates G1
   to G5 are merge-blocking.
3. Casey answers `freeze_template.json`, which is committed as `freeze.json` with the hashes. Pull
   the fixtures on the run day.
4. **Blind count:** K, cluster spans, global/clean counts, D-2 firings. If D-1 is UNDERPOWERED it
   stops there, recorded, with the data still unseen.
5. **ONE scored run** (D-0, D-1, D-2); `results.json` is committed unedited.
6. Two independent verifiers: a recompute, and a check of claims and wording. A correction run is
   allowed only with logged reasons.
7. RESULTS, the honesty box with frozen numbers, and charts:
   - per-currency firing strips on price;
   - a cluster D_c forest plot;
   - DXY 1973–2005 with its firings;
   - the in-sample gap chart (S1 vs C4).

   Then panel wiring per §4, and a redeploy of **treasury-canary**.
8. D-3/D-4 ledger live from the freeze date: R1 monthly appends, R2 quarterly counts.

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| SPEC v0 (this draft) | not yet reviewed: two reviewers required before SPEC v1 | — |
