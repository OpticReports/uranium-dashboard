# BARBELL-TIMER Amendment A17 — cross-equity internals (s15-s18, rules 9/10)

Produced by `rules_internals.py` -> `rules_internals_results.json` (monthly net
return series, lagged series, state series, signal series included). Chart:
`figs/fig9_internals_drawdowns.png` (rule 9/10 drawdown profiles vs B&H
GDE-synth and relmom_cash + the one-month-lag stress panel). GDE-synth is a
MODEL (±1%/yr carry band pre-2007); month-end curves are intramonth-blind
(~4pp deeper daily, BASELINES.md). Walk-forward history, NOT forecasts.

**GOVERNANCE FLAG — single-agent round.** Builder and first referee are the
same agent in this amendment (the referee battery below reuses the
referee-verified conventions of `qa_phase4.py` but was run by the builder on
its own results). Per the repo's counter-agent rule this is logged, not
hidden: an independent second-agent pass has NOT yet happened for A17.
Mitigants: parameters frozen in SPEC A17 before computation, zero tuning, the
truncation/perturbation battery hard-gates the pipeline, and every kill
finding below is AGAINST the new family (the direction a builder bias would
not produce).

## Discipline (verified in-code before results were read)

- Same standing convention: state decided at month-end t from data knowable
  at t, executed next month's open, earns month t+1 panel return; 5bp x
  one-way turnover; BOXX = bills - 5bp/yr.
- **QA battery**: truncation-invariance (french12 + Baa + panel cut at
  1990-12 / 2005-06 / 2019-12) and future-perturbation (violent shocks to
  post-cut inputs): **PASS at all three cuts, both tests** (hard-exit wired).
- Sharpe tripwire: max Sharpe anywhere in the A17 family = 0.51 (rule 10
  OOS) — nowhere near 1.2.
- Windows: FULL 1977-02 -> 2026-07 (identical to rules 1-5 — all four
  signals are live well before 1977), OOS 1990-02 -> 2026-07.
- Data: `research/fixtures/french12.json` (Ken French 12-industry VW monthly,
  percent units) + new frozen fixture `fixtures/fred_baa10ym.json` (verbatim
  copy of treasury-canary's cycle fixture BAA10YM, provenance in the file and
  PROVENANCE.md — nothing re-fetched) + the Phase-1 panel. Zero free
  parameters beyond the frozen lookbacks; the only estimated quantities are
  s18's expanding mean/std (walk-forward, 24-obs burn-in, repo convention).

## Amendments logged this round (fixed A-PRIORI, before computation)

- **A18** SPEC A17 says french12 "industries 1935->" but the fixture starts
  1926-07. The literal spec wins: signals use 1935-01 onward (only s18's
  expanding-z baseline is affected; the 12-1 momenta are trailing).
- **A19** Adverse (risk-off) side = the natural ZERO boundary, no threshold
  search: s15 defensive-basket 12-1 > cyclical-basket 12-1; s16 Utils 12-1 >
  market 12-1 (market = equal-weight of all 12, Utils included, per SPEC);
  s17 Baa spread 3m change > 0 (widening); s18 expanding z of trailing-12m
  mean pairwise industry correlation > 0. Isolation mapping (Phase-2
  precedent, cf. sma10_spy): risk-off -> pred +1 "GDE beats SPY next 12m".
- **A20** Availability: French month-t industry returns and the month-t Baa
  spread treated as knowable at month-end t (both derive from real-time
  public prices; the published French library lags — approximation flagged,
  bounded by the mandatory lag stress). 12-1 = compounded t-11..t-1 skip-t;
  baskets = equal-weight monthly-rebalanced means.
- **A21** With >1 survivor, "internals adverse" = **ANY surviving signal on
  its risk-off side** (union) — fixed before any hit rate or backtest was
  seen. This choice turned out to be decisive (autopsy below); it is
  reported, not re-litigated.

## Signal isolation — OOS hit rates (eval t = 1990-01..2025-07, N = 427)

Frozen kill bar: hit <= 50%. Base-rate honesty: always-GDE scores **54.8%**.

| # | signal | hit | p(overlap-adj) | frozen verdict | vs 54.8% base |
|---|--------|-----|------|---------|---------------|
| s15 | def_cyc_relmom | 50.1% | 0.49 | live | **BELOW base** (coin flip) |
| s16 | utils_mkt_relmom | **61.8%** | **0.08** | live | above base — the one real signal |
| s17 | baa_chg3 | 51.8% | 0.42 | live | **BELOW base** |
| s18 | corr12_z | 52.0% | 0.41 | live | **BELOW base** |

**KILL LIST: empty.** Nothing hit the frozen <=50% bar (s15 clears it by one
month: 50.1%), so per the pre-registration ALL FOUR feed the A21 union. Three
of the four are below the always-GDE base rate — under the frozen protocol
they are "live" but add nothing over a constant, and the union construction
lets them fire the gate anyway. That is the single most consequential fact of
this amendment. The direction of s16's information is worth noting: Utils
LEADING predicts GDE **out**performance (61.8%) — internals risk-off is
relatively GOOD for GDE vs SPY, because equity stress is when the gold leg
carries the stack. The pre-registered rules nonetheless EXIT to cash on
risk-off (absolute-crash protection, the owner's exit-engine framing) — so
the rules point the gate against the grain of the only informative signal's
relative message. Pre-registered as such; reported as found.

## Rules 9/10 — OOS master table (1990-02 -> 2026-07)

adverse (ANY-of-4) fires in **77.4%** of OOS decision months.

| portfolio | CAGR | Vol | Sharpe | Sortino | MaxDD | UW | Calmar | Ulcer | Worst12m | %GDE | %cash | gross |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B&H GDE-synth | 13.98% | 19.51% | 0.64 | 0.99 | -44.2% | 47m | 0.32 | 10.8 | -43.1% | 100% | 0 | 1.80x |
| B&H SPY | 11.03% | 14.67% | 0.61 | 0.91 | -50.8% | 74m | 0.22 | 13.5 | -43.4% | — | — | 1.00x |
| static_5050 (null) | 12.77% | 15.75% | 0.68 | 1.04 | -44.9% | 50m | 0.28 | 10.7 | -42.6% | — | — | 1.40x |
| relmom_cash (standing) | 15.23% | 15.82% | 0.81 | 1.38 | -22.7% | 44m | 0.67 | 8.0 | -18.5% | 46% | 17% | 1.20x |
| **9 internals_exit** | **3.84%** | 8.21% | 0.18 | 0.26 | **-15.3%** | 93m | 0.25 | **4.4** | -12.1% | 23% | 77% | 0.41x |
| **10 relmom_gated** | **7.53%** | 10.14% | 0.51 | 0.80 | **-16.4%** | 71m | 0.46 | 4.8 | -10.4% | 11% | 52% | 0.57x |

Full window 1977-02 -> 2026-07: rule 9 3.95%/-26.3%/Calmar 0.15/Sharpe 0.01;
rule 10 7.39%/-21.5%/0.34/0.35; relmom_cash 16.16%/-33.2%/0.49; null
13.50%/-44.9%/0.30. Rule 9's FULL-window Sharpe is 0.01 — five decades of
volatility for bills-level return (OOS CAGR 3.84% vs bills 2.69%).

## Owner criterion (A12/A17: DD materially reduced AND CAGR above B&H SPY) — OOS

| rule | dMaxDD vs GDE | dCAGR vs SPY | dSharpe vs SPY | gross | verdict |
|---|---|---|---|---|---|
| 9 internals_exit | **+28.9pp** | **-7.19pp** | -0.43 | 0.41x | **FAIL** (CAGR 3.8% << SPY) |
| 10 relmom_gated | **+27.8pp** | **-3.50pp** | -0.10 | 0.57x | **FAIL** (CAGR 7.5% < SPY) |

The drawdown half of the criterion is met more strongly than by anything else
tested in this project (-15/-16% maxDD, ulcer 4.4/4.8 — the shallowest
profiles of all 28 variants). The CAGR half fails by miles: both rules land
BELOW B&H SPY, rule 9 below the null by 8.9pp/yr. These are cash-heavy
portfolios (0.41x/0.57x gross), and leverage-aware they have no scale-free
edge either (Sharpe 0.18/0.51 vs SPY 0.61).

## Head-to-head vs relmom_cash (the standing candidate) — OOS

| rule | dCAGR | dMaxDD | dCalmar | dUlcer | dSortino | NW-t |
|---|---|---|---|---|---|---|
| 9 internals_exit | -11.39pp | +7.3pp | -0.42 | **-3.5** | -1.12 | **-5.07** |
| 10 relmom_gated | -7.70pp | +6.2pp | -0.21 | **-3.2** | -0.58 | **-3.53** |

Both rules lose to relmom_cash on CAGR, Calmar and Sortino with the most
significant NW-t deficits this project has produced (rule 9's -5.07 beats
even the A12 family's -2.3 for decisiveness — AGAINST the challenger). What
they win is ulcer/maxDD — by holding cash half to three-quarters of the time.

## ONE-MONTH LAG STRESS — the A17 headline question

Every decision executed one month late (t earns t+2), OOS:

| rule | on-time CAGR/maxDD/Calmar | lagged CAGR/maxDD/Calmar | delta Calmar |
|---|---|---|---|
| relmom_cash | 15.23% / -22.7% / 0.67 | 12.90% / **-49.3%** / **0.26** | -0.41 (the Phase-4 kill) |
| static_5050 | 12.77% / -44.9% / 0.28 | unchanged | 0 |
| 9 internals_exit | 3.84% / -15.3% / 0.25 | 3.78% / -23.9% / 0.16 | -0.09 |
| **10 relmom_gated** | 7.53% / -16.4% / 0.46 | **7.19% / -18.2% / 0.39** | **-0.06** |

**YES — the internals gate fixes the Oct-2008 one-month-lag kill,
mechanically and exactly as hypothesized.** Autopsy: at the AUG-2008
month-end (the decision that, lagged, is held through Oct-2008) s15, s16 and
s17 were ALL already adverse (Baa 3m change +0.21pp; defensives and Utils
leading) — only s18 was benign. Lagged relmom_cash holds GDE through Oct-08
(-31.6%, maxDD -49.3%, Calmar 0.26 < null 0.28); lagged rule 10 is in BOXX
for Oct-08, keeps maxDD at -18.2% and Calmar at 0.39 — still above the null
under the stress that killed the standing candidate. Rule 10 is the first
GDE-containing rule in this project that is BOTH shallow-drawdown AND
lag-robust. Credit-spread/internals deterioration is a slow, persistent
signal that was flashing for months before the crash — precisely the
property relmom's fast price signal lacks.

**But the cure costs more than the disease.** The same 77%-adverse union
that had rule 10 safely in cash for Oct-2008 ALSO had it in cash for most of
2001-11 (CAGR 1.9%/yr in GDE's best decade) and 2022-> (4.8% vs relmom's
22.8%). On-time, rule 10 gives up 7.7pp/yr vs relmom_cash to buy a 6pp maxDD
improvement; lagged-vs-lagged it beats relmom (7.19%/-18.2%/0.39 vs
12.90%/-49.3%/0.26 — better Calmar, far shallower, worse CAGR), which is a
real statement about execution-risk-adjusted robustness, but the owner's
frozen criterion (CAGR above SPY) fails in every version.

## Per-regime blocks (CAGR / MaxDD / Calmar)

| portfolio | 1980-99 | 2001-11 | 2012-18 | 2022-> |
|---|---|---|---|---|
| relmom_cash | 12.6% / -33.2% / 0.38 | 15.0% / -18.5% / 0.81 | 9.3% / -17.2% / 0.54 | 22.8% / -15.6% / 1.47 |
| 9 internals_exit | 3.9% / -26.3% / 0.15 | **1.4% / -12.7% / 0.11** | 3.8% / -15.3% / 0.25 | 5.6% / -14.5% / 0.38 |
| 10 relmom_gated | 11.0% / -21.5% / 0.51 | **1.9% / -13.9% / 0.14** | 7.0% / -16.4% / 0.42 | 4.8% / -14.5% / 0.33 |

The brief's bad-regime test inverts here: the rules survive the anti-gold
1980-99 era (rule 10 respectably: 11.0%, maxDD -21.5%) and instead DIE in
GDE's GOOD regimes — the union reads gold-friendly stress as danger and
exits the one asset that was winning. An internals gate on a gold-heavy
stack sells exactly when the insurance pays.

## Referee battery (single-agent; conventions of qa_phase4.py)

- **Start-date grid** (26 starts, Jan-1990..Jan-2015): rule 9 dCalmar vs
  null negative at **26/26** starts (min -0.36). Rule 10 vs null: positive
  at 16/26, negative at 10 (min -0.33, max +0.16) — sign-unstable. Both
  rules' dCalmar vs relmom_cash negative at **26/26** starts.
- **Drop-single-year** (37 years): rule 9 vs null negative in **37/37**.
  Rule 10 vs null positive in **37/37** (min +0.08, drop-2021) — the Calmar
  point edge over the null is not a single-episode artifact. Rule 10 vs
  relmom negative in **37/37** (min -0.40).
- **Block bootstrap** (circular, 24m blocks, 4000 draws, OOS). Family after
  A17: 26 tested variants + 2 rules = 28; adjustments x2 (A17 rules), x10
  (all rule-level candidates vs null), x28 (full logged family):

| comparison | point | 90% CI | p | p x2 | p x10 | p x28 |
|---|---|---|---|---|---|---|
| r10 dCalmar vs null | +0.17 | [-0.21, +0.37] | 0.260 | 0.52 | 1.0 | 1.0 |
| r10 dUlcer vs null | -5.98 | [-13.9, -0.08] | **0.048** | 0.096 | 0.478 | 1.0 |
| r10 dUlcer vs relmom | -3.21 | [-5.97, -0.21] | **0.037** | 0.075 | 0.375 | 1.0 |
| r10 dCAGR vs null | -5.23pp | — | 0.972 | 1.0 | 1.0 | 1.0 |
| r10 dCalmar vs relmom | -0.21 | [-0.56, +0.08] | 0.878 | 1.0 | 1.0 | 1.0 |
| r9 dCalmar vs null | -0.03 | [-0.40, +0.11] | 0.743 | 1.0 | 1.0 | 1.0 |
| r9 dUlcer vs null | -6.30 | [-13.9, +0.04] | 0.051 | 0.103 | 0.515 | 1.0 |

Nothing survives any multiplicity counting. The only sub-0.05 raw cells are
rule 10's ulcer improvements — real drawdown-comfort geometry, bought with a
CAGR deficit that is itself significant in the wrong direction (dCAGR vs
null p 0.972 means the null beats rule 10's CAGR in 97% of draws).

## vs the A12 failures (same OOS window)

| family | best variant | CAGR | MaxDD | verdict vs criterion |
|---|---|---|---|---|
| A12 vol/corr exits | 6b vol_exit_spy | 11.96% | -35.3% | FAIL (no scale-free edge, 1.59x gross) |
| A17 internals | 10 relmom_gated | 7.53% | -16.4% | FAIL (CAGR < SPY) |

A12 failed by exiting too little and at the wrong times (vol spikes on
melt-ups, corr lags crashes). A17 fails the opposite way: the signals DO
see stress early (Aug-2008 — the first family in this project to pass the
lag stress with a shallow drawdown), but the union fires so often that the
engine is barely ever in the market. A12 couldn't see; A17 sees but
can't stop flinching.

## Honest bottom line

1. **Isolation**: kill list empty under the frozen bar, but only
   s16_utils_mkt (61.8%, p~0.08) beats the always-GDE base rate; s15/s17/s18
   are noise by the base-rate test. Its message is DIRECTIONAL for GDE:
   internals risk-off predicts GDE beating SPY.
2. **Rule 9 is dead on arrival**: bills-plus-one-point CAGR (3.84%), Sharpe
   0.18, negative dCalmar vs the null at every start and every drop-year,
   NW-t -5.07 vs relmom_cash. The ANY-of-4 union (A21) held it in cash 77%
   of the time.
3. **Rule 10 answers the amendment's real question — YES, the internals
   gate fixes the Oct-2008 one-month-lag fragility** (lagged: -18.2% maxDD,
   Calmar 0.39 > null 0.28, holds BOXX through Oct-08 off the Aug-08
   signal). It is the only lag-robust shallow-drawdown GDE rule found in
   five families. But it fails the frozen success bar in every accounting:
   CAGR 7.53% < SPY 11.03%, dCalmar vs null insignificant (p 0.26,
   sign-unstable across starts), loses to relmom_cash on CAGR/Calmar/Sortino
   at all 26 starts and all 37 drop-years with NW-t -3.53.
4. **Verdict vs the standing candidate: relmom_cash survives its fifth
   challenger.** The A17 finding with forward value is narrow and honest:
   slow credit/defensive-leadership internals contain the lag-robust exit
   information that relmom lacks, and a LESS trigger-happy use of them
   (e.g. an s16-only or majority gate) is the natural next question — that
   is a NEW variant requiring a new amendment and a fresh multiplicity
   count. It was NOT run in this round; under the frozen A17/A21 spec the
   result is a clean double FAIL, and the null's boring supremacy plus
   relmom's fragile Calmar edge stand exactly where Phase 4 left them.

Caveats carried everywhere: GDE-synth is a model (±1%/yr carry band
pre-2007); month-end curves intramonth-blind (~4pp deeper daily); French
library publication lag treated as zero (A20, bounded by the lag stress);
BOXX = bills - 5bp; no taxes (Act 60); single-agent round (see governance
flag) — an independent counter-agent pass is owed before any A17 number is
acted on.
