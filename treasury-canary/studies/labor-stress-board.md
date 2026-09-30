# Labor Stress Board — seeing labor-market trouble beyond the headline rate

**Question (Casey, 2026-09-30):** the headline unemployment rate "looks too
good". Build a labor analytic that captures more than employed-vs-unemployed —
people leaving the labor force, hiring, layoffs — robust enough to flag
trouble ahead on the research dashboard. Look at Henrik Zeberg's work.

**Research pass** (workflow, 10 agents, every strand adversarially verified;
full record in the session scratchpad, summary here):
- Headline U-3 is **4.1%** (Aug 2026), not ~4.7%; peak 4.5% (Nov 2025).
- WORSE than the headline: hiring (CPS job-finding 24.3% vs 26.3% a year ago;
  JOLTS hires 3.3%, lowest pre-2020 print since 2013), duration (27.0% of the
  unemployed out 27+ weeks, above the pre-2009 max, with a 1994-redesign
  caveat), prime-age employment rate (June-2026 step down), a participation-
  adjusted unemployment rate ~4.6% (an upper bound).
- NOT worse: every layoff measure (claims 197K, continuing claims −9.5% y/y,
  insured unemployment 1.1%, SOS −0.004, JOLTS layoffs 1.0%, job losers −202K
  y/y); the want-a-job count and U-6 FELL; ~43% of the H1-2026 participation
  drop is the Jan-2026 population-control break, ~16% aging; the June drop is
  concentrated among the foreign-born (immigration / nonresponse, not demand).
- **Zeberg**: a useful checklist; his composite model is proprietary and
  unreplicable, his headline labor numbers lean on the population-control
  break (2.2M "left" → ~0.7M net; 5.6% counterfactual → ~4.6-5.0%), and his
  full-time-employment RSI signal fired AFTER the NBER peak in every recession
  it matched (median +7 months).
- Structural: labor data CONFIRM recessions more than they lead them; the
  layoff/separations channel is what historically turns a slowdown into one.

---

## SPEC v0 — pre-registered 2026-09-30, BEFORE the Sep-2026 jobs report (2026-10-02) and before any rule is scored

**Data** (keyless FRED, frozen in `labor_stress/data/`, CPS through Aug 2026,
claims through 2026-09-12): UNRATE, UNEMPLOY, CLF16OV, LNS11300060,
LNS12300060, LNU00000060, LNS13023621, IURSA, CCNSA, SAHMREALTIME, U6RATE,
NILFWJN, NEIM156SFRBRIC, LNS17100000, LNS17400000, CE16OV, JTSHIR, JTSQUR,
JTSLDR, LNS13025703, UEMPMED, USREC, LNU01373395/LNU01373413 (nativity).

**Conventions.** Monthly grid; a weekly series enters a month as its last
weekly value dated in that month. Missing months (Oct-2025 CPS; Oct-Nov 2025
flows) are skipped, never interpolated: 3-month averages need ≥ 2 values,
12-month windows use whatever months exist. Every comparison is made on values
rounded to 3 decimals (0.1pp-step data otherwise flip on float error).

### Rules scored (thresholds fixed now; ★ = external/published threshold)

Leg A — **separations** (the layoff channel):
- **A1 SOS ★** (Richmond Fed EB 25-07): m = 26-week average of IURSA;
  SOS = m − min(m over the prior 52 weeks); lit when SOS > 0.20.
- **A2 Job-loser Sahm**: j = 100·LNS13023621/CLF16OV; MA3(j) − min(MA3(j) over
  the prior 12 months) ≥ 0.30 (in-sample family; 0.27 and 0.35 reported).
- **A3 Continuing claims**: 4-week average of CCNSA (not seasonally adjusted —
  immune to seasonal-factor re-estimation) vs the same weeks a year earlier ≥
  +10% (+20% reported).

Leg B — **slack incl. labor-force exits**:
- **B1 Prime-age EPOP drawdown**: e = LNS12300060; max(MA3(e) over the prior 12
  months) − MA3(e) ≥ 0.50 (WATCH tier 0.30 displayed, not scored).
- **B2 Participation-adjusted unemployment (PAUR) Sahm**: gap = max(0,
  max(LNS11300060 over t−23..t) − LNS11300060_t)/100 × LNU00000060_t;
  PAUR = 100·(UNEMPLOY + gap)/(CLF16OV + gap); MA3(PAUR) − min(prior 12) ≥ 0.50.

Leg C — **the standard**:
- **C1 Sahm ★** (SAHMREALTIME ≥ 0.50) — the dashboard's existing rule and the
  baseline everything is compared against.

**Composite (the Board):** ALERT in a month when ≥ 1 Leg-A rule AND ≥ 1 Leg-B
or Leg-C rule are lit (layoffs CONFIRMED by slack). WATCH when any single rule
is lit. Rationale fixed now: every single rule false-alarmed at least once in
2021-2026; the 2024 Sahm false alarm was labor SUPPLY (entrants/immigration)
with no layoff leg, which the confirmation requirement is designed to reject.

### Evaluation

- NBER peaks in sample: 1973-11, 1980-01, 1981-07, 1990-07, 2001-03, 2007-12,
  2020-02 (7). **Scoring period 1972-01 → 2020-12; HOLDOUT 2021-01 → 2026-08.**
- An **onset** = first lit month after ≥ 6 unlit months. **Hit** = an onset in
  [peak − 6, peak + 3]; timing = onset − peak (months). **False alarm** = an
  onset with no peak in [onset − 3, onset + 12].
- Reported per rule and for the composite: hits (of 7), median and range of
  timing, false-alarm onsets 1972-2020, holdout onsets 2021-2026, and the
  Aug-2026 reading.

### Decision rule (what reaches the phone)

The composite ALERT ships as a RED Telegram alert only if ALL hold:
1. ≥ 6 of 7 peaks hit;
2. false-alarm onsets 1972-2020 ≤ C1 Sahm's;
3. **zero** onsets in the 2021-2026 holdout (Sahm has one: 2024);
4. median timing no later than Sahm's + 1 month.
Otherwise the Board ships as a dashboard panel with WATCH/ALERT states and
threshold lines, and alerts reach the phone at WARN only, labelled with the
measured record. Individual rules are displayed with their threshold lines
either way; none is sent alone.

### Display-only "real slack" strip (answers "is 4.1% too good?"; no alerts)

U-3 (unrounded) vs PAUR · U-6 · U-3 + want-a-job (UNEMPLOY+NILFWJN)/(CLF16OV+
NILFWJN) · Non-Employment Index · prime-age EPOP · job-finding rate (3-month
average of LNS17100000/UNEMPLOY_{t−1}) · JOLTS hires, quits, layoffs · 27+
week share and median duration · foreign-born vs native-born participation.
Each shows its latest value, 12-month change and percentile; PAUR is labelled
an UPPER bound.

### Stated up front

- In-sample: A2, A3, B1, B2 thresholds come from a research pass that looked at
  history; only A1 and C1 are external. The HOLDOUT is the honest test, and it
  is 5.7 years with no recession — it can only count false alarms.
- Current-vintage data; CPS ratios are lightly revised (seasonal factors,
  January population controls), claims NSA are essentially unrevised.
- 7 recessions. Nothing here dates a recession ahead of the NBER with
  confidence; the Board is a confirmation instrument that aims to be early and
  quiet, not a forecast.

---

## SPEC v1 — amendments after two counter-agents, still BEFORE any rule is scored

Reviewer 1 raised four BLOCKING findings; per CLAUDE.md a second,
independent reviewer tried to refute each with its own computation. Where they
disagreed, the resolution below follows the one that measured it. Every item
SUPERSEDES the v0 text it names.

**A1 (B1, both confirmed) — the holdout was seen during design.** "Zero
holdout onsets" is demoted to a MUST-NOT-FAIL check with three tiers: FINAL
2021-01 → 2024-09 (peaks through onset+12 are knowable given NBER's ≤ 12-month
announcement lag) — zero onsets required; PROVISIONAL 2024-10 → 2025-08 —
reported, not gated; PENDING 2025-09 → — never counted. Out-of-sample starts
with data month **2026-09** (released 2026-10-02, after this spec): every
WATCH/ALERT onset from then is logged to `labor_stress/ledger.csv` when it
happens and scored at the quarterly calibration (R2).

**A2 (B2: reviewer 1's numbers REFUTED by reviewer 2, the concern kept).**
With the ACTUAL slack leg (B1∨B2∨C1), an uninformative layoff leg passes the
6-of-7 criterion ~0% of the time (rotations: 0 of 541; random spells ≤ 2.8%),
not 1-50%. Kept anyway: **SIZE** — circularly rotate the monthly A-leg lit
series (A1∨A2∨A3) over 1972-01..2020-12 by every shift 24..N−24, rebuild the
composite, score it; statistic = hits, then fewest false alarms; P = (1 + #
rotations at least as good) / (1 + #rotations); gate P ≤ 0.10. Because its null
("layoffs unrelated to the cycle") is easy to reject, the evidence that the
layoff leg ADDS VALUE is a separate **PAIRED** check against the composite's
own slack leg B1∨B2∨C1 scored alone: the composite must lose no HIT and remove
≥ 1 of the slack leg's false alarms. Criterion 2 is evaluated under A3's
definitions.

**A3 (B3, both confirmed) — scoring definitions that run.** Onset = first lit
month preceded by ≥ 6 OBSERVED unlit months (missing months are neither; a
spell lit at a rule's first computable month is left-censored and unscored).
Peaks p and troughs τ: 1973-11/1975-03, 1980-01/1980-07, 1981-07/1982-11,
1990-07/1991-03, 2001-03/2001-11, 2007-12/2009-06, 2020-02/2020-04. Each onset
is classified HIT if in [p−6, p+3] of any peak, else LATE if in [p+4, τ] of any
peak, else EARLY if in [p−12, p−7] of any peak, else FALSE ALARM (precedence
HIT > LATE > EARLY; so 1980-07 is LATE for 1980, not EARLY for 1981). A peak
with no HIT whose window lies inside a spell begun before p−6 is LIT-THROUGH —
a miss, labelled the same way for every rule. Timing is PAIRED: the median of
(composite − Sahm) over peaks both HIT. 2020 is a free hit for every rule:
"x of 6 ex-2020" is reported, not gated.

**A4 (B4: reviewer 2's measurement adopted over reviewer 1's fix).** COVEMP
is exactly the IUR's denominator, but it picks up the 1972 and 1978 UI
coverage extensions 3-6 quarters late: normalizing claims by it fixes 1973-74
and BREAKS 1979-80 (normalized minus job losers −9 to −17pp). So A3 stays raw
CCNSA ≥ +10% y/y; the 1973-11 and 1980-01 peaks are flagged
COVERAGE-AFFECTED for A3; sensitivities: A3 masked across those two peaks'
[p−12, τ], and COVEMP-normalized A3 (which also removes ~1.9pp/yr of trend, so
+10% normalized ≈ +12% raw). A1 inherits COVEMP through the IUR — stated.

**A5 (S1) — one data vintage for every rule.** The study's C1 = Sahm
recomputed from current-vintage UNRATE (as `_sahm_from_unrate`), so the
challengers (current-vintage CPS) are not compared against a noisier
real-time baseline; SAHMREALTIME is a sensitivity (the two differ by up to
0.37pp and in 11 of 588 lit-months, at spell edges). The LIVE panel keeps
SAHMREALTIME.

**A6 (S2) — weekly series enter the month knowably.** A weekly series enters
month M as the week ending 7 days after the CPS reference week (the Sun-Sat
week containing the 12th) — released the Thursday before M's jobs report in
all 656 months checked (the v0 last-week-of-month mapping looked 1-2 weeks
ahead in 78% of months). The Board is evaluated on this monthly grid only.

**A7 (S3) — population-control sensitivity.** B1/B2 recomputed after removing
the EXCESS Dec→Jan step (Jan−Dec minus the median Jan−Dec of all other years)
in prime-age participation and employment rate for 2000, 2003, 2004, 2008,
2011, 2022, 2025, 2026 (years with ≥ 500k beyond-trend jumps in the 25-54
population), shifting pre-January levels. If the gate outcome differs, RED is
withheld.

**A8 (S4) — every threshold is in-sample, the ★ ones included** (Sahm's 0.50
and SOS's 0.20 were calibrated on these same recessions). Robustness grid A2 ∈
{0.27, 0.30, 0.35} × A3 ∈ {10, 15, 20%} × B1 ∈ {0.40, 0.50, 0.60} × B2 ∈ {0.40,
0.50, 0.60} (81 points), criteria 1-4 + paired at each; RED requires a pass at
the registered point AND at ≥ 2/3 of the grid. Nothing is out-of-sample before
data month 2026-09.

**A9 (S5/S6, NITs).** Display strip as built (c61cdc8): header "the Board
answers 'is a layoff-driven downturn confirmed?'; the strip answers 'is 4.1% too
good?' — they can disagree"; duration percentiles from 1994; long-term
unemployment rate beside the share; PAUR an upper bound with its gap in
persons; Jan-2026 NEI flagged; nativity 12-month change only. The "27+ week
share above the pre-2009 max" line is dropped from the summary (the long-term
unemployment RATE is at the 60th percentile since 1994). SOS window = weeks
t−52..t−1; A3 lag = exactly 52 observations; A2's 1994 redesign step (−0.16pp,
no peak nearby) stated; WATCH duty cycle reported (if > 33%, the panel shows a
count, not a state); USREC unused (it marks peak+1). NAMING FIX: the series
`LNU00000060` is the 25-54 population — PAUR's gap was always prime-age
shortfall × prime-age population; the code key `pop16` is renamed `pop_prime`.

### Decision rule v1 (supersedes v0's)

RED Telegram only if ALL: (1) ≥ 6 of 7 HIT; (2) false alarms 1972-2020 ≤
current-vintage Sahm's; (3) zero onsets in FINAL 2021-01..2024-09; (4) paired
median timing vs Sahm ≤ +1 month; (5) SIZE P ≤ 0.10; (6) PAIRED: no HIT lost
vs the slack leg alone and ≥ 1 of its false alarms removed; (7) ≥ 2/3 of the
robustness grid passes 1-4 + 6; (8) the population-control sensitivity does
not flip (1)-(6). Otherwise the Board ships at WARN, its alert text carrying
the measured record.

---

## RESULTS — frozen 2026-09-30 (`labor_stress/results.json`, one run)

**RED gate: FAIL** → the Board ships at WARN with its measured record.

| | recession starts HIT (of 7) | false alarms 1972-2020 | fired in FINAL 2021-24? | paired timing vs Sahm |
|---|---|---|---|---|
| **Board** (layoffs AND slack, same month) | **5** (4 of 6 ex-2020) | **0** | **yes — 2024-08** | **−2 months** (median, earlier) |
| slack leg alone (B1∨B2∨C1) | 4 | 0 | yes — 2024-07 | — |
| C1 Sahm (current vintage) | 5 | 1 (2003-07) | yes — 2024-07 | — |
| A1 SOS (insured unemployment) ★ | 5 | 0 | **no** | — |
| A2 job losers | 6 | 0 | yes — 2024-08 | — |
| A3 continuing claims | 5 | 0 | yes — 2023-04 | — |
| B1 prime-age EPOP drawdown | 4 | 0 | no | — |
| B2 participation-adjusted U | 5 | 0 | yes — 2024-08 | — |

Criteria: (1) ≥6 hits FAIL (5: 1973 came LATE, 1974-07; 1981 LIT-THROUGH from
the 1980 recession); (2) FAs ≤ Sahm PASS (0 vs 1); (3) zero FINAL-tier onsets
FAIL (2024-08); (4) paired timing PASS (−2: 1980 0, 1990 −2, 2001 −6, 2007
−2, 2020 −1); (5) size PASS (p = 0.0018, 0 of 541 rotations as good); (6)
paired value-added: no hit lost PASS, removes a slack-leg false alarm FAIL
(the slack leg had none 1972-2020; the layoff leg's contribution is TIMING —
it turned 2001 from LIT-THROUGH into a hit 3 months before the peak — not
false-alarm removal); (7) grid FAIL (0 of 81); (8) population-control
sensitivity unchanged.

- **The design aim failed where it mattered.** The AND was meant to reject
  the 2024 supply-driven Sahm alarm. It did not: job losers rose 0.309pp
  (just over A2's 0.30 line) in Aug-Sep 2024, exactly as the research pass
  had reported — a threshold choice that should have been caught at spec
  time. SOS alone (a published rule) stayed quiet through 2021-2026.
- **What it is good for:** a layoff-confirmed slack signal that, in 48 years,
  never lit without a recession nearby and led the Sahm rule by a median of 2
  months where both hit. It is a CONFIRMATION instrument (hits cluster in
  −3..+1 months of the peak), not a 12-month early warning.
- **WATCH duty cycle** (any rule lit): 32% of months 1972-2020, 40% since
  2021 → above the 33% ceiling, so the panel shows "N of 6 rules lit", not a
  WATCH state.
- **Today (data month 2026-08):** Board CLEAR; 0 of 6 rules lit; nearest is
  the prime-age employment drawdown at 0.40 (its 0.30 watch tier crossed, the
  0.50 rule not).

Honesty box: current-vintage CPS for every rule (real-time Sahm is a
sensitivity and gives the same 5 hits); thresholds in-sample, ★ ones included;
the 2021-2024 tier was seen during design; A1 inherits COVEMP through the
IUR; A3's 1973/1980 hits are coverage-affected (masking them leaves the Board
at 5 hits — its 1973 miss and 1980 hit come from other legs); 7 recessions.
Out-of-sample begins with data month 2026-09 (released 2026-10-02): onsets from
then are listed live by `/labor/board` (`ledger`) and scored at R2.

Figures (`labor_stress/charts.py` → `labor_stress/figs/`): `fig_board_timeline`
(every rule's lit months vs NBER recessions, Board row incl. Aug 2024),
`fig_hidden_slack` (U-3 vs U-6, unemployed + want-a-job, participation-
adjusted), `fig_hire_fire` (job-finding rate vs insured unemployment),
`fig_rate_spike_episodes` (the rate-spike re-test, 3 of 20 episodes).

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| spec v0, reviewer 1 (2026-09-30) | 4 BLOCKING: holdout seen in design; no size check; scoring undefined (1980/81, late onsets, timing); A3 carries 1972/1978 UI coverage breaks | all four addressed (A1-A4), plus S1-S6, NITs |
| spec v0, reviewer 2 — independent refutation | B1 and B3 confirmed; B2's 1-50% refuted (≈0% with the real slack leg) but the size test kept + a paired value-added check; B4 PARTLY — COVEMP normalization breaks 1979-80, raw A3 kept with flags; S1, S2 confirmed | A1-A6 follow reviewer 2 where the two disagreed, because it measured |
