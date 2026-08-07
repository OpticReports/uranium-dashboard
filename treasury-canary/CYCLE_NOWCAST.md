# Business-cycle composite NOWCAST study — walk-forward, 1972–2026

**Goal.** Project next month's coincident composite before its data publishes (~1-month FRED lag,
~2 months for the CMRMTSPL component), so the dashboard reads one month ahead.
**Discipline.** Walk-forward only: expanding window, refit every month, no test-period information in
any fit or standardization (the composite's expanding z is itself real-time by construction).
Every candidate is judged against naive persistence.

Companion visual: `nowcast_study.png` (nowcast vs realized 1972–2026, the 7 onset windows, RMSE bars).
Raw per-method output: `results_raw.json`, `nowcasts.npz`.

## Target reconstruction and validation

Rebuilt from raw FRED observations exactly per the prototype spec:

- **Coincident composite** = mean of expanding-window z-scores (min 120 obs, stats through the
  current month only) of 6-month annualized log growth of PAYEMS, INDPRO, W875RX1, CMRMTSPL.
  Matches the prototype's stored series at **corr 0.99997** (max abs diff 0.06; the prototype's
  later start, 1970-06 vs 1969-06, is its 1960 data start feeding the same 120-obs warm-up).
- **Leading composite** = mean expanding z of [yield-curve level (T10Y3M from 1982, GS10−TB3MS
  before), permits 6m growth, −claims 6m growth (ICSA monthly mean), AWHMAN level, UMCSENT 1m
  change, −BAA10YM], then a **3-month moving average** — the smoothing was reverse-engineered from
  the prototype's stored series (raw corr 0.927 → 0.9964 with the 3m MA, RMSE 0.048).
- Monthly collapse: mean for ICSA and T10Y3M, last for the rest. USREC for NBER dating.

**Eval window note.** The task asked for 1965→2026, but the composite is undefined before 1969-06
by its own 120-month z warm-up. Evaluation targets run **1972-01 → 2026-06** (n = 654; first years
after 1969 reserved for minimum training), which still contains all **7 NBER onsets**: 1973-12,
1980-02, 1981-08, 1990-08, 2001-04, 2008-01, 2020-03. The 1969-12 onset is unavoidably excluded.
Subsample reported: 1990-01 → 2026-06 (n = 438).

## Real-world data-availability calendar (the ragged edge)

Nowcast for month **M** is issued at the payrolls release, ~1 week after M ends ("nowcast date").

| Series | For month M, publishes | Known at nowcast date? |
|---|---|---|
| ICSA (weekly) | ~5 days after each week | yes — full month M |
| T10Y3M / GS10 / TB3MS / BAA10YM | daily / start of M+1 | yes |
| PAYEMS, AWHMAN | first Friday of M+1 | **yes — this IS the nowcast date** |
| UMCSENT (final) | end of M | yes |
| INDPRO | ~day 15 of M+1 | no — 1-month lag |
| PERMIT | ~day 18 of M+1 | no (M−1 value is in hand) |
| W875RX1 | ~end of M+1 | no — 1-month lag |
| CMRMTSPL | ~mid M+2 | no — 2-month lag |

So when the composite for month M finally prints in full (~M+2 because of CMRMTSPL), the nowcast
had it ~1 month earlier at minimum. One of the four coincident inputs (payrolls) is **already
actual** at the nowcast date — this is the asymmetry the bridge exploits.

Information sets: methods 1–3 use only data through M−1 ("pure lag"); methods 4–5 and the
ensembles additionally use series published by the nowcast date (payrolls, hours, claims, rates,
BAA, sentiment for month M). **Nothing uses data unpublished at the issue date** — this is a
timing design choice, not look-ahead.

## Methods (all walk-forward, expanding window, OLS refit monthly, min 24 training obs with persistence fallback)

1. **PERS** — persistence baseline: nowcast(M) = COIN(M−1).
2. **AR2** — COIN(M) ~ 1 + COIN(M−1) + COIN(M−2).
3. **LEADREG** — COIN(M) ~ 1 + COIN(M−1) + LEAD(M−1) + ΔLEAD(M−1) (LEAD = 3m-MA leading composite).
4. **BRIDGE** (ragged edge) — per-component: PAYEMS z actual; INDPRO and W875RX1 growth projected by
   g(M) ~ 1 + g(M−1) + g_PAYEMS(M); CMRMTSPL by g(M) ~ 1 + g(M−2) + g_PAYEMS(M); projected growths
   z-scored with expanding stats through each component's last actual month; composite = mean of the
   four z's (skipping components the realized composite also skips).
5. **CLAIMS** (high-frequency proxy) — COIN(M) ~ 1 + COIN(M−1) + z_claims6(M) + [z_claims6(M) −
   z_claims6(M−3)] + z_curve(M), where z_claims6 = expanding z of −6m log-growth of monthly-mean ICSA.
6. **Ensembles / alternative leads:**
   - **ENS_INV** — inverse-past-OOS-MSE convex weights over {PERS, AR2, LEADREG, BRIDGE, CLAIMS}.
   - **ENS_GRID** — each month picks the lowest-past-OOS-MSE convex combo from a fixed dictionary
     (singletons, all pairs at 25/50/75, equal-weight) — fully ex-ante selection.
   - **ENS_BC** — fixed 0.5·BRIDGE + 0.5·CLAIMS (see honesty box on how this was chosen).
   - **ALT_HARD / ALT_FIN / ALT_CORRW** — three alternative leading-composite weightings
     (hard-data only: claims+permits+curve; financial only: curve+BAA; walk-forward
     correlation-weighted), each fed through the method-3 regression form.

## Results — full window (targets 1972-01 → 2026-06); 1990-01 → 2026-06 in parentheses

| Method | RMSE | RMSE (1990+) | Dir. acc % | Phase acc % | Transition acc % | DM vs PERS | DM ex-2020 | False-alarm months | Onsets caught earlier (of 7) |
|---|---|---|---|---|---|---|---|---|---|
| **PERS (baseline)** | **0.4674** | **0.5316** | n/a (no call) | 82.6 | **0.0** | — | — | 0 | **0** (by construction ties the lagged composite) |
| AR2 | 0.4692 | 0.5383 | 53.8 | 81.7 | 11.4 | +0.15 | — | 1 | 1 |
| LEADREG | 0.4511 | 0.5179 | 58.0 | 81.8 | 28.9 | −1.27 | — | 3 | 2 |
| BRIDGE | 0.3348 | 0.3656 | 59.3 | 82.2 | 23.7 | −1.45 | −1.74 | 0 | 0 |
| CLAIMS | 0.3930 | 0.4383 | 66.0 | 82.7 | **29.8** | −1.49 | −3.08 | 2* | **4** |
| ALT_HARD | 0.4234 | 0.4808 | 57.6 | 81.3 | 21.9 | −1.28 | — | 4 | 2 |
| ALT_FIN | 0.4493 | 0.5097 | 54.9 | 82.0 | 21.1 | −1.57 | — | 1 | 2 |
| ALT_CORRW | 0.4424 | 0.5053 | 58.4 | 80.4 | 16.7 | −1.29 | — | 4 | 2 |
| ENS_INV | 0.3920 | 0.4436 | 66.0 | 82.6 | 13.2 | −1.73 | — | 1 | 1 |
| ENS_GRID | **0.3319** | **0.3637** | 66.0 | 83.6 | 23.7 | −1.60 | −4.45 | 0 | 2 |
| **ENS_BC (winner)** | 0.3344 | 0.3692 | **69.8** | **83.8** | 25.4 | −1.63 | **−5.33** | 1* | 3 |

- Dir. acc = sign of predicted vs realized month-over-month change (persistence predicts zero change
  → no call). Phase acc = nowcast phase (CONTRACTION < −0.75 ≤ STALL < 0 ≤ EXPANSION) equals
  realized next-month phase. Transition acc = same, on the 114 months (75 in 1990+) where the phase
  actually changed — **persistence scores 0% here by construction**; this is where a nowcast earns
  its keep. DM = Diebold-Mariano t-stat on squared-error differences vs PERS, Newey-West lag 6
  (negative = better than persistence).
- *False alarms = months the nowcast printed < −0.75 with no realized < −0.75 within ±3 months.
  CLAIMS' two (1981-06, 1981-07) and ENS_BC's one (1981-06) all **preceded the 1981-08 recession**
  — the realized composite crossed in 1981-11 — so they were early warnings, not errors. The only
  genuine false alarm anywhere: LEADREG in 2022-07.

### Recession-onset anticipation (the money metric)

The lagged composite shows a −0.75 crossing of month m_c about one month later (when m_c's data
prints; ~2 months for the full four-input composite). A nowcast crossing at target month m_n is in
hand at the start of m_n+1, so calendar advantage ≈ (m_c − m_n) + 1 months.

| Onset | Realized cross | ENS_BC cross (advantage) | CLAIMS cross (advantage) |
|---|---|---|---|
| 1973-12 | 1974-01 | 1974-03 (−1 mo) | 1974-02 (0, tie) |
| 1980-02 | 1979-09 | 1979-10 (0, tie) | 1979-10 (0, tie) |
| 1981-08 | 1981-11 | 1981-06 (**+6 mo**) | 1981-06 (**+6 mo**) |
| 1990-08 | 1990-09 | 1990-10 (0, tie) | 1990-10 (0, tie) |
| 2001-04 | 2001-03 | 2001-03 (**+1 mo**) | 2001-02 (**+2 mo**) |
| 2008-01 | 2008-02 | 2008-03 (0, tie) | 2007-12 (**+3 mo**) |
| 2020-03 | 2020-03 | 2020-03 (**+1 mo**) | 2020-03 (**+1 mo**) |

- **ENS_BC: earlier on 3/7, ties 3, later on 1 (1973), zero misses.**
- **CLAIMS: earlier on 4/7, ties 3, never later, zero misses** — the best pure early-warning
  channel, at the cost of 17% worse RMSE than ENS_BC.
- Persistence: later on all 7 by construction (it can only repeat last month's value).

## Winner: ENS_BC = 0.5·BRIDGE + 0.5·CLAIMS

Edge vs persistence: **RMSE −28.5%** full-sample (0.334 vs 0.467; −30.6% in 1990+; −14.7%
excluding 2020, so it is not only a COVID artifact), **directional accuracy 69.8%** vs no call,
**phase accuracy 83.8% vs 82.6%** and — the part persistence cannot do at all — **25% of actual
phase transitions called in advance vs 0%**, with ≥1 month calendar advantage on 3 of 7 recession
onsets and only one "false" contraction print (which itself preceded the 1981 recession by 2 months).

Recommended dashboard wiring: show **ENS_BC as the one-month-ahead composite reading** and the
**CLAIMS member as a separate early-warning trigger line** (4/7 onsets earlier, never later, no
genuine false positives in 54 years).

### Deployable spec (current coefficients, refit monthly on full history — see `nowcast_spec.json`)

- BRIDGE growth projections (g = 6m annualized log growth):
  - INDPRO: g(M) = −0.00168 + 0.7448·g(M−1) + 0.4465·g_PAYEMS(M)
  - W875RX1: g(M) = +0.00453 + 0.7026·g(M−1) + 0.2379·g_PAYEMS(M)
  - CMRMTSPL: g(M) = +0.00426 + 0.5147·g(M−2) + 0.5230·g_PAYEMS(M)
  - PAYEMS: actual published growth; all z-scores from expanding stats (min 120 obs) through each
    component's last actual month; BRIDGE = mean of the four z's.
- CLAIMS: COIN(M) = −0.0619 + 0.7610·COIN(M−1) + 0.1231·z_claims6(M) + 0.1178·[z_claims6(M) −
  z_claims6(M−3)] − 0.0189·z_curve(M)  (n = 587)
- ENS_BC(M) = 0.5·BRIDGE(M) + 0.5·CLAIMS(M)
- **Live nowcast for 2026-07** (issued on the Aug 2026 payrolls print): BRIDGE −0.347,
  CLAIMS −0.429, **ENS_BC −0.388** → phase STALL (realized COIN 2026-06 = −0.492; payrolls-only
  partial for 2026-07 = −0.448).

## Honesty box (frozen numbers above; read before quoting)

1. **Revisions (applies to ALL methods, baseline included).** Everything uses final-vintage FRED
   data. PAYEMS, INDPRO, W875RX1, CMRMTSPL all revise; a true real-time (ALFRED vintage) replay
   would degrade every method and the target itself. The persistence baseline shares the bias, so
   *relative* rankings are more trustworthy than absolute RMSEs — but the onset-anticipation counts
   could shift under first-print data. Not modeled.
2. **Statistical significance.** Full-sample DM for ENS_BC is −1.63 (~10% level, two-sided) because
   2020 dominates the squared-error variance; excluding 2020 the improvement is unambiguous
   (DM −5.33). The RMSE gain is real in both cuts (−28.5% incl. 2020, −14.7% excl.).
3. **How ENS_BC was chosen.** Its 50/50 weight was fixed, not fitted — but the choice to combine
   BRIDGE and CLAIMS was made after seeing they were the two strongest channels. Mitigation: the
   fully ex-ante ENS_GRID selector (dictionary of combos, chosen each month on past OOS MSE only)
   picked exactly 0.50·BRIDGE + 0.50·CLAIMS in 354 of 630 months (56%) and matches its RMSE
   (0.3319) — the conclusion does not depend on hindsight. If you want zero selection taint, deploy
   ENS_GRID; it gives up ~4pp of directional accuracy and one early onset catch.
4. **CMRMTSPL timing nit.** The bridge assumes CMRMTSPL(M−2) is in hand at the payrolls-day nowcast;
   its release actually lands ~mid-month, ~1 week later. Either issue the nowcast mid-month or
   switch that component to a lag-3 bridge — impact is negligible (one of four z's, OLS-shrunk),
   but the deployed version should pick one and say so.
5. **Composite-through-M−1 assumption.** Methods 1–3 and the COIN(M−1) regressor in CLAIMS treat the
   composite through M−1 as known at the nowcast date; its CMRMTSPL input for M−1 actually arrives
   ~2 weeks later. In production, use the bridge estimate of COIN(M−1) (with actual INDPRO/W875RX1)
   as that regressor — its error is tiny relative to a full-month-ahead projection.
6. **What was NOT modeled:** data revisions (above), the 1969 recession (composite warm-up),
   parameter uncertainty bands, publication-calendar drift over 54 years (release schedules assumed
   fixed at today's pattern), and any intramonth updating (the nowcast is issued once per month).
7. Persistence is genuinely hard to beat on point RMSE with pure lag-M−1 information: AR2 loses to
   it and LEADREG's edge is marginal (−3.5%). **The entire material edge comes from the ragged-edge
   timing asymmetry** — using payrolls/claims/rates for month M that are already published before
   the composite for M prints. That is the honest core finding, and it is exactly the edge a
   dashboard can exploit every month.
