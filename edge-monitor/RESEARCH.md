# EDGE-MONITOR — Phase 1: Edge Decay Detection, State of the Art

*Prepared 2026-08-13. Counter-agent reviewed (see referee note at bottom).
Working assumption throughout: retail scale — daily NAV, tens-to-hundreds of
trades/year per strategy, no cross-sectional data. Every method is graded
against that reality, not against a fund's data.*

## Executive summary — the 5 highest-signal checks

1. **Per-trade slippage CUSUM** (realized fill vs model price, per trade).
   The highest signal-to-noise series you own: slippage shifts are *many
   sigma* per observation, so decay shows in 10–30 trades, not months.
   Execution rot is the most common real killer and the only one detectable
   fast at retail scale. (Category E.)
2. **Monte Carlo drawdown percentile** (live DD vs block-bootstrapped
   backtest DD distribution, length-matched). Answers the only DD question
   that matters — "is this normal *for this strategy at this track length*"
   — with ~5 live days minimum. Already proven in-house (BARBELL-TIMER QA).
3. **ARL-calibrated CUSUM on standardized daily returns**. The earliest
   *statistical* mean-decay detector with a controlled false-alarm rate.
   Honest headline from our gates + referee re-runs: at 1 false alarm/~2yrs,
   a *fully dead* edge (SR 1.2→0) takes median ~8 months of daily data to
   flag (~120–330d across calibration draws; p90 can reach ~2.5y).
   Nothing legitimate is faster on returns alone; distrust anything that
   claims to be.
4. **PSR/MinTRL discipline** (Bailey–López de Prado). Not a detector — a
   *license to conclude*. MinTRL tells you when a live Sharpe verdict is
   even possible (SR~1.2 daily strategy vs 0: 476 trading days ≈ 1.9y;
   monthly SR~0.8 book: ~53 months ≈ 4.4y — slow but NOT impossible, so
   relmom_cash-class systems get process-monitoring first and a real PSR
   verdict on a ~4–5y clock). [Corrected 2026-08-13: first draft said ~1y
   and 'decades' — a 2× and a 9× error the referee caught; the monthly
   policy was re-decided on the true figure.] PSR with skew/kurt corrections is the
   verdict itself; DSR deflates it by the trials actually run (our trials
   registry / family counts are the input — family=28 for BARBELL-TIMER).
5. **Regime attribution before verdict** (rolling beta/correlation drift +
   vol-regime bounds vs backtest range). Separates "edge gone" from "regime
   the backtest never saw" — the difference between retiring a strategy and
   riding out a state. Cheap: rolling 60d beta to venue benchmark, realized
   vol vs backtest MC band.

**What we deliberately do NOT run** (decorative at our scale): KS/AD
distributional tests on live-vs-backtest daily returns (need thousands of
live obs; iid assumption false; block-bootstrap versions still underpowered
at n<500); HMM/Markov-switching fit to a single strategy's returns
(overparameterized toy at retail n; we use the canary's macro regime stack
instead); White's Reality Check/SPA as a *live* monitor (they are selection-
time tools; we apply the same idea via DSR trial-count deflation); per-trade
SPRT on win rate for monthly-cadence books (arrives after everything else).

---

## A. Live vs backtest divergence

**PSR** (Bailey & LdP 2012, *Sharpe Ratio Efficient Frontier*):
`PSR(SR*) = Φ[ (SR_hat − SR*)·√(n−1) / √(1 − γ₃·SR_hat + (γ₄−1)/4·SR_hat²) ]`
with per-period SR, skew γ₃, raw kurtosis γ₄. The denominator is the
non-normality-corrected SR standard error (Mertens 2002). Negative skew and
fat tails *widen* it — a crypto strategy's PSR is materially lower than its
Gaussian look. Implementation: `src/edge_monitor/psr.py`; validated by null
calibration (PSR ~U(0,1) under H0) and skew-penalty direction gates.

**MinTRL**: invert PSR for n at a target confidence:
`n* = 1 + (1 − γ₃SR + (γ₄−1)/4·SR²)·(z_α/(SR−SR*))²`. Infinite when
SR_hat ≤ SR*. This is the small-sample honesty engine: it PRINTS when a
verdict is impossible. Examples (95%, vs SR*=0, Gaussian
moments, computed with this module's `min_trl`): daily SR 1.2 → 476
trading days; daily SR 0.7 → 1394 (~5.5y); monthly SR 0.8 → ~53 months.

**Backtest-as-null**: we frame H0 as "live returns drawn from the backtest
distribution" and test three moments separately (mean via CUSUM/PSR, vol via
MC bands, DD via MC percentile) rather than one omnibus distributional test —
omnibus tests have no power at our n and don't localize the failure.

**Failure modes**: PSR assumes iid — positive autocorrelation (trend books)
overstates n; we report an N_eff = n/(1+2Σρ_k) alongside (BARBELL-TIMER
precedent: N/12 for overlapping windows). DSR is gameable by undercounting
trials — the trials registry is the source of truth, and any strategy
without a registry gets a declared penalty count (see BLUEPRINT).

## B. Sequential / online change detection

**CUSUM** (Page 1954): `S_t = max(0, S_{t−1} − z_t − k)` (downward chart on
standardized returns), alarm at `S_t > h`. Two design choices dominate:
- *k = half the shift you want to catch, in daily σ.* Textbook k=0.25–0.5 is
  tuned for process-control-sized shifts; an SR-1.2 edge **dying entirely**
  is only ~0.076σ/day, so k≈0.04. Using textbook k makes the chart
  near-blind to the thing we care about. (Pinned by a gate.)
- *Calibrate h by Monte Carlo on the strategy's own backtest* (circular
  block bootstrap → simulate null run lengths → bisect h to the target
  ARL). At SR-sized k the Gaussian closed form is often adequate even on t(3)
  returns (referee-verified); calibrating on the strategy's own distribution
  costs nothing and removes the assumption.
  Implementation: `cusum.py::calibrate_h`, with explicit censoring
  disclosure.

Honest speed limit (multi-seed gate pins it): target ARL 500d → dead edge
flagged at median ~120–330 trading days depending on the calibration draw
(median-of-medians ≈ 8 months). Detection speed and false-alarm rate trade
off directly; there is no free lunch on daily returns.

**SPRT** (Wald 1945): sequential test of H0: p=p₀ vs H1: p=p₁ on trade wins,
`log LR` random walk with thresholds `log((1−β)/α)`, `log(β/(1−α))`.
Fits per-trade venues (Coinbase executor: every trade logged). At 30-50
trades/year it delivers keep/kill verdicts in 1–3 years for hit-rate drops
of 10pp+ — useful as a slow confirmatory lane, not an early warning. Skipped
for monthly books.

**BOCD** (Adams & MacKay 2007): run-length posterior with NIG conjugate →
Student-t predictive; hazard 1/250. Run on *lag-standardized* returns (EWMA
vol through t−1) or it mostly detects vol clusters. Our gates pin both the
power (0.6σ break → posterior spike + MAP restart) and the blindness: an
SR-sized mean shift is **invisible** to BOCD at n=60 — encoded as an
honesty gate so nobody upgrades BOCD to first-line detector later.
Role: corroborator for CUSUM alarms + vol/level break detector.

**Drawdown vs MC**: see exec summary #2; implementation `dd_percentile.py`
computes both max-DD percentile and *current-underwater* percentile
(comparing a live in-progress DD to completed max-DD draws is biased calm —
the underwater statistic fixes that). Length-matching pinned by gate.

## C. Multiple testing & overfitting guards

**PBO/CSCV** (Bailey, Borwein, LdP, Zhu; SSRN 2013, J. Comput. Finance 2017): split the trial matrix into
S combinatorial train/test halves; PBO = fraction of splits where the
in-sample winner falls in the out-of-sample bottom half. Requires the FULL
variant matrix from development — only computable where we kept every trial
(barbell trials registry; BARBELL-TIMER's 28-variant family qualifies).
For strategies whose development history is lost (Composer symphonies built
by iteration), PBO is *undefined* — the blueprint assigns a punitive default
trial count (N=20) in DSR instead of pretending.

**Reality Check / SPA** (White 2000; Hansen 2005): bootstrap tests of "best
of N variants beats benchmark" — selection-time tools. We inherit their
correction through DSR's expected-max-SR benchmark
`E[maxSR] ≈ σ_SR[(1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(Ne))]` (γ = Euler–Mascheroni).

**Alert-stream multiplicity**: monitoring 5 strategies × 6 metrics daily ≈
30 hypothesis streams. Corrections: per-detector budgets are set by ARL
design (not p-values), and the weekly digest applies Benjamini–Hochberg FDR
across the week's nominal p-values before anything escalates a state.
Bonferroni is reserved for RED (halt) decisions only — false halts are the
expensive error there, so conservatism is correct at that tier.

## D. Risk regime & distribution shift

- **Vol bands**: rolling 20d realized vol vs the backtest MC distribution of
  20d vols (same block bootstrap). Outside p1–p99 → "regime the backtest
  never saw" flag; this *contextualizes* return alarms rather than sizing
  down by itself.
- **Correlation/beta drift**: rolling 60d beta to the venue benchmark (SPY /
  BTC) and pairwise correlation across our own books vs backtest values.
  Drift toward beta ≈ crowding/factor decay (Category F literature: alpha
  decays into beta before it dies). Threshold: |Δβ| > 2×bootstrap SE
  sustained 20d → YELLOW contributor.
- **Distributional tests**: KS/AD rejected as primary (power + iid issues at
  our n; on autocorrelated data their nominal p-values are wrong). Kept only
  in the quarterly review as descriptive QQ plots + block-bootstrap KS
  p-value, labeled descriptive.
- **Markov/HMM**: not fit to strategy returns (overparameterized at our n).
  Regime state is imported from the canary (phase labels, analog layer,
  vol/curve dims) — attribution, not detection.

## E. Execution & microstructure decay — the real killer

The per-trade slippage series `slip_bps = side·(fill − model)/model` is the
only series where retail data is RICH: each observation is a direct edge
measurement with σ of a few bps and shifts of the same order. CUSUM with
k=0.5σ_slip on per-trade slippage detects a 1σ drift in ~15 trades.
- **Coinbase/BTC**: executor already logs `state.fills` with adverse-signed
  slip_bps (built this window) — wire directly. Watch: spread widening,
  post-only fallback rate (a regime of taker fills = structural cost bump),
  funding drift if perps ever enter.
- **IBKR**: fill vs decision-price benchmark per order; routing quality =
  fill-rate at limit + effective/quoted spread ratio.
- **Composer**: no fill control — monitor *rebalance timing drift* (NAV vs
  same-day-close replication of the symphony rules; divergence = timing
  slippage) — weekly, not per-trade.
- **Capacity**: regress slip_bps on trade notional (rolling); positive and
  significant slope that grows = capacity decay. At retail size this should
  be flat ≈ 0; its appearance is itself an alarm (venue liquidity change).

## F. What practitioners do

- **Carver** (*Systematic Trading*, *AFTS*): never single-strategy verdicts —
  diversify, size by long-run vol-targeted risk, shrink allocations slowly
  (his "no peeking then act" discipline); treat live-vs-backtest gap as
  expected (~30% Sharpe haircut rule of thumb from selection bias).
- **AQR** (Israel et al. on factor decay; "Craftsmanship Alpha"): published
  factor premia decay ~⅓–½ post-publication (McLean & Pontiff 2016: returns ~26%
  lower post-sample, ~58% lower post-publication; the ~32pp gap is the
  publication-attributable increment); crowding shows as correlation
  to known factors before Sharpe visibly dies → our beta-drift check.
- **Man AHL** (published process notes): capital scaling is graduated and
  rule-based; retirement is a committee decision *informed* by sequential
  stats, never automated cold. Matches our traffic-light + human-in-loop.
- **Half-life priors by style** (from the decay literature, for DSR priors
  and YELLOW patience): microstructure/arb edges: months–2y; cross-sectional
  equity anomalies: 3–5y post-publication to ~half strength; trend/managed
  futures: multi-decade persistence but with decade-length flat stretches
  (the patience case); vol-selling: persistent but tail-repricing risk.
  Implication: our BTC intraday-ish books get short-half-life priors (tight
  YELLOW patience), relmom/phase books get long priors (loose patience,
  process-monitoring only).
- **Guilty vs innocent**: consensus practice is *graduated Kelly-fraction
  scaling on posterior edge*, not binary kill — exactly the state machine in
  the blueprint. New/unproven → start at fraction and *earn* size (our
  executor ramp already does this); proven-then-decaying → shrink on YELLOW
  rather than debate.

## Comparison matrix

| Method | Data needed | Detection speed | False-alarm control | Small-sample fit | Verdict |
|---|---|---|---|---|---|
| Slippage CUSUM | per-trade fills | ~10–30 trades | ARL-calibrated | **excellent** | **Layer 1, first-line** |
| MC DD percentile | 5+ live days + backtest | immediate context | percentile by construction | **excellent** | **Layer 1, first-line** |
| Returns CUSUM | 60+ live days | months (dead edge) | ARL-calibrated | good | **Layer 1** |
| Vol/beta bands | 20–60 live days | weeks | bootstrap bands | good | Layer 1–2 (attribution) |
| BOCD | 100+ days | weeks (big breaks only) | hazard prior, uncalibrated | fair | Layer 2 corroborator |
| PSR/MinTRL | MinTRL days (~1y daily) | slow by design | exact (given iid) | honest by design | Layer 2 verdict |
| SPRT (hit rate) | 50+ trades | 1–3y | exact α/β | fair (per-trade venues) | Layer 3 confirmatory |
| DSR/PBO | full trials registry | pre-live | exact | n/a (design-time) | Baseline registration |
| KS/AD | 500+ live days | quarters | broken under autocorr | **poor** | Quarterly, descriptive only |
| HMM regimes | years | — | — | **poor** | rejected (canary instead) |

## Referee note

Counter-agent review (2026-08-13) executed the gates, re-derived the null
calibrations under t(3)/AR(1)/crash-skew, audited every formula against the
source papers (all clean), and falsified four doc claims — all corrected in
place and logged with the full verdict in `REFEREE.md`.
