# BARBELL-TIMER Phase 3 — the five pre-registered rules (per frozen SPEC)

Produced by `rules.py` -> `rules_results.json` (monthly net return series per
rule included for Phase 4). Charts: `figs/fig4_rules_equity_oos.png`,
`fig5_rules_drawdowns.png` (drawdown overlay + rule-2 holdings/switch band),
`fig6_rules_regimes.png`. GDE-synth is a MODEL (±1%/yr carry band pre-2007);
month-end curves are intramonth-blind (daily estimates ~4pp deeper,
BASELINES.md) — the planning number for a -45% month-end drawdown is ~-49%.
In-sample walk-forward history, NOT forecasts.

## Discipline (all verified in-code before results were read)

- Weights decided at month-end t from data knowable at t (CPI/DXY carry an
  extra availability-lag month — "t-1 data earns month t+1"), executed next
  month's open, earn the month t+1 panel return.
- **QA battery**: truncation-invariance (inputs cut at 1990-12 / 2005-06 /
  2019-12 -> identical decisions up to the cut) and future-perturbation
  (violent shocks to post-cut panel/macro/daily inputs -> decisions up to the
  cut unchanged): **PASS at all three cuts, both tests.** rules.py hard-exits
  if any leg fails.
- Costs: 5bp x one-way turnover (full switch = 5bp), charged in the traded
  month; BOXX = bills - 5bp/yr; initial buy-in uncharged (identical across
  rules). Walk-forward only; free parameters: ONE estimated quantity (the
  expanding median in rule 3), all other lookbacks/targets fixed a-priori.
- Sharpe tripwire: max observed timing-rule Sharpe = 0.81 (< 1.2) — no audit
  triggered beyond the standing QA battery.
- Windows: FULL = 1977-02 -> 2026-07 (first month every rule is live);
  OOS = 1990-02 -> 2026-07 (the Phase-2 15y warmup convention). The brief's
  verdict criterion is judged on OOS; full window shown for regime honesty.

## Rule definitions as implemented (ambiguities resolved a-priori)

1. **static_5050** — 50/50 GDE-synth/SPY, monthly rebalanced. THE NULL.
2. **relmom_cash** — 12-1 momentum (months t-11..t-1, skipping t) GDE vs
   SPY picks the sleeve; absolute filter = winner's own 12-1 return vs bills
   over the same window; filter fails -> BOXX.
3. **realrate_gate** (amendment A8: the brief's one-line spec parsed as) —
   real-10y 12m trend <= 0 (down/flat) -> GDE; trend rising & level <=
   expanding median -> SPY; trend rising & level high ("both negative for
   gold") -> BOXX.
4. **composite** (amendment A9) — M = rule-2 state, R = real-rate 12m-trend
   signal. M=GDE and R gold-favorable -> GDE; M=BOXX and R unfavorable
   ("both neg") -> BOXX; anything else -> 50/50.
5. **voltarget_15** (amendment A11) — rule-4 weights x lam,
   lam = min(1, 15%/sigma60); sigma60 = trailing 60-trading-day annualized
   vol of the rule-4 target portfolio from the DAILY fixtures (pre-1993
   equity leg = ^GSPC + smeared Shiller dividends — flagged); (1-lam) in
   BOXX; lam capped at 1 (no leverage). Realized: mean lam 0.86, scaled
   below 1 in 48% of months, min 0.21.

## Master table — OOS window 1990-02 -> 2026-07 (the verdict window)

| rule | CAGR | Vol | Sharpe | Sortino | MaxDD | UW | Calmar | Ulcer | Worst12m | NW-t vs null |
|---|---|---|---|---|---|---|---|---|---|---|
| static_5050 (null) | 12.77% | 15.75% | 0.68 | 1.04 | -44.9% | 50m | 0.28 | 10.7 | -42.6% | — |
| relmom_cash | 15.23% | 15.82% | 0.81 | 1.38 | **-22.7%** | 44m | **0.67** | 8.0 | -18.5% | +1.29 |
| realrate_gate | 10.07% | 17.33% | 0.49 | 0.73 | -57.1% | 47m | 0.18 | 13.3 | -57.1% | -1.48 |
| composite | 13.12% | 16.32% | 0.68 | 1.07 | -38.7% | 47m | 0.34 | 12.2 | -38.1% | +0.34 |
| voltarget_15 | 11.20% | 12.49% | 0.70 | 1.13 | -29.4% | **39m** | 0.38 | **8.5** | -23.7% | -1.40 |

Full window 1977-02 -> 2026-07 (same ordering of conclusions):
null 13.50%/-44.9%/Calmar 0.30; relmom_cash 16.16%/-33.2%/0.49;
realrate_gate 12.48%/-57.1%/0.22; composite 15.04%/-38.7%/0.39;
voltarget_15 12.96%/-29.4%/0.44 (ulcer 8.3 vs null 11.5).

Deltas vs null, OOS: relmom_cash dCAGR +2.46pp, dMaxDD +22.2pp, dCalmar
+0.39, dUlcer -2.8; voltarget_15 dCAGR -1.57pp, dMaxDD +15.5pp, dCalmar
+0.10, dUlcer -2.2; composite +0.35pp / +6.2pp / +0.05 / +1.5 (ulcer WORSE);
realrate_gate worse on every metric. NW t-stats on mean monthly return
difference are all |t| < 1.5 — none of the CAGR differences is
distinguishable from zero; the brief's verdict is about Calmar/ulcer and is
formally decided by Phase 4's bootstrap with the multiple-testing adjustment
(count: 4 active rules vs null on top of 14 Phase-2 signals; no unreported
variants were run).

## vs B&H SPY (owner amendment A5 — Q2 column set)

Q2: "does any GDE-containing portfolio dominate B&H SPY" (>= SPY CAGR AND
better maxDD/Calmar/Sortino), shown leverage-aware. B&H SPY OOS: CAGR 11.03%,
MaxDD -50.8%, Calmar 0.22, Sortino 0.91, Sharpe 0.61 (full window in JSON).

| rule (OOS) | dCAGR | dMaxDD | dCalmar | dSortino | avg gross risk notional | dominates? |
|---|---|---|---|---|---|---|
| static_5050 | +1.74pp | +5.9pp | +0.07 | +0.13 | 1.40x | yes (raw) |
| relmom_cash | **+4.20pp** | **+28.1pp** | **+0.46** | **+0.46** | **1.19x** | **yes** |
| realrate_gate | -0.96pp | -6.3pp | -0.04 | -0.18 | 1.24x | no |
| composite | +2.09pp | +12.1pp | +0.12 | +0.16 | 1.37x | yes (raw) |
| voltarget_15 | +0.17pp | +21.4pp | +0.16 | +0.22 | 1.14x | yes (raw) |

Leverage-aware reading (per the amendment: a 90/90 stack beating 100% SPY on
raw CAGR is expected, not evidence): static_5050 and composite run ~1.4x
gross risk notional, so their raw-CAGR edge over SPY is substantially
leverage; their scale-free edge is thinner (Sharpe +0.07 / +0.07 OOS).
**relmom_cash is the interesting Q2 case**: it dominates SPY on every raw
metric while averaging only ~1.19x gross notional (it holds the 1.8x GDE
stack less than half the time) AND wins scale-free (Sharpe 0.81 vs 0.61,
Sortino 1.38 vs 0.91). voltarget_15 at 1.14x gross also wins scale-free with
a fraction of SPY's drawdown. Per the amendment, Q2's verdict is decided by
Phase 4 (drop-single-year is decisive; the prior is that the GDE CAGR edge
may be 1979 alone — note this Phase-3 window starts 1977-02 and the OOS
window 1990-02 excludes 1979 entirely, and relmom_cash's OOS edge survives
without it).

## Per-regime blocks (CAGR / MaxDD / Calmar) — regime honesty

| rule | 1980-99 | 2001-11 | 2012-18 | 2022-> |
|---|---|---|---|---|
| static_5050 | 13.2% / -42.1% / 0.31 | 8.5% / -44.9% / 0.19 | 10.3% / -11.7% / 0.88 | 18.5% / -25.3% / 0.73 |
| relmom_cash | 12.6% / -33.2% / 0.38 | 15.0% / -18.5% / 0.81 | 9.3% / -17.2% / 0.54 | 22.8% / -15.6% / 1.47 |
| realrate_gate | 11.2% / -33.2% / 0.34 | **7.5% / -57.1% / 0.13** | 10.0% / -13.5% / 0.74 | 8.5% / -21.8% / 0.39 |
| composite | 14.0% / -33.2% / 0.42 | 9.1% / -38.4% / 0.24 | 9.8% / -11.8% / 0.83 | 20.3% / -14.7% / 1.38 |
| voltarget_15 | 12.9% / -21.5% / 0.60 | 9.6% / -24.0% / 0.40 | 7.8% / -10.9% / 0.72 | 18.2% / -9.5% / 1.91 |

- **relmom_cash** passes the bad-regime test: 1980-99 (the anti-gold regime)
  costs -0.6pp/yr vs null WITH a 9pp shallower maxDD — "at worst mildly
  negative". Its worst stretch anywhere is -33% (1980-82).
- **realrate_gate is DEAD** under the frozen criterion ("catastrophic in its
  bad regime is dead regardless of full-sample stats"): maxDD -57.1% inside
  2001-11 — WORSE than the null (-44.9%) and nearly as bad as B&H GDE-synth
  (-61%). Autopsy (from the state series): falling real yields kept it 100%
  GDE Feb..Sep-2008 through the crash, then the gate rotated it into SPY for
  Oct-08..Feb-09 — it caught both legs down with zero absolute-momentum
  defense. Its 12m real-rate input was already ~coin-flip in Phase 2 (50.4%).
- **composite** is dragged by the same input: real-rate disagreement forces
  50/50 during momentum-favorable stretches and its "both neg" BOXX state
  triggered in only 11% of months; 2001-11 maxDD -38.4% is better than null
  but far worse than pure relmom_cash (-18.5%). The composite DILUTES its
  good ingredient with its dead one.
- **voltarget_15** is the pure drawdown-per-CAGR play: worst regime maxDD
  -24.0%, best ulcer/underwater-time, no regime catastrophic — at the price
  of -1.6pp/yr OOS CAGR vs null. Judged on the brief's primary objective
  (drawdown reduction per unit CAGR sacrificed) it is the honest runner-up
  to relmom_cash, which sacrifices nothing.

## Turnover (one-way, x/yr) and state switches per decade

| rule | 1980s | 1990s | 2000s | 2010s | 2020s | switches/decade |
|---|---|---|---|---|---|---|
| static_5050 | 0.14 | 0.07 | 0.11 | 0.10 | 0.10 | rebalance drift only |
| relmom_cash | 1.6 | 1.9 | 1.8 | 1.5 | 1.5 | 16/19/18/15/10 |
| realrate_gate | 1.3 | 2.7 | 2.1 | 1.4 | 2.7 | 13/28/20/14/18 |
| composite | 1.3 | 1.5 | 1.8 | 1.1 | 1.3 | 19/18/27/16/15 |
| voltarget_15 | 1.6 | 1.8 | 1.9 | 1.5 | 1.6 | (rule-4 states) |

~1.5-1.9 full switches/yr for the live rules; at 5bp that is ~8-10bp/yr of
cost — not the driver of any conclusion. No tax modeled (Act 60 per brief);
turnover reported so that assumption is visible.

## Amendments logged this phase

- **A5** (owner, in SPEC.md, logged 2026-08-12 before Phase 2-3 results were
  computed) Q2 vs-SPY column set + leverage-aware comparison — implemented
  above; Q2 verdict deferred to Phase 4 drop-single-year.
- **A6** `fred_dgs10.json` fetched (FRED, 2026-08-12) for the pre-2003
  real-10y splice; proxy = DGS10 month-end minus trailing-12m CPI (CPI
  through t-1); overlap 2003-07 shows proxy ~0.51pp BELOW DFII10 — flagged.
- **A7** Futures term-structure signal infeasible with frozen fixtures
  (front-month-only continuous series) — logged, not faked.
- **A8/A9** One-line specs of rules 3/4 parsed into explicit gates (above)
  BEFORE any results were computed.
- **A10** Availability lags: CPI and DXY lagged one month inside signal
  construction ("t-1 data earns month t+1"); market prices use month-t.
- **A11** Vol-target lam capped at 1 (no leverage), sigma60 from daily
  fixtures (pre-1993 daily equity = ^GSPC + smeared dividends — flagged).

## Honest bottom line (subject to Phase 4 adversarial QA)

Only **relmom_cash** (the prior study's champion, revalidated monthly) beats
the null on the brief's own criteria — OOS Calmar 0.67 vs 0.28, ulcer 8.0 vs
10.7, maxDD -22.7% vs -44.9% — while ALSO adding CAGR; mean-return
difference is statistically indistinguishable (NW-t 1.29), so the case rests
on the drawdown geometry, exactly what Phase 4's bootstrap + start-date +
signal-noise batteries must now try to break. voltarget_15 is a defensible
lower-vol variant; composite adds little over the null; realrate_gate is
dead. "The null survives against 3 of 4 challengers" is the boring
conclusion so far — one challenger remains standing.
