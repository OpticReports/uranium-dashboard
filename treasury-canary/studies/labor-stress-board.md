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
