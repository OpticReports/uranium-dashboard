# Forecasting foundation models — pre-registration (2026-09-01)

Registered BEFORE any data is pulled, per RESEARCH_PROTOCOL.md §5. Nothing
in here may be edited once the first forecast is generated; failures get
recorded in §9 rather than removed.

Trigger: TimesFM-3 (Google, 2026-08) and Chronos-2 (Amazon). Both are
zero-shot multivariate forecasters emitting quantiles rather than point
estimates.

## 0. Scope, fixed by the standing stopping rule

RESEARCH_PROTOCOL.md §7 closes signal-space search until the live gate
concludes, and names **vol-targeting the blend** as open portfolio-layer
work. That decides the scope before any preference of ours does:

| Hypothesis | Lane | Status |
|---|---|---|
| H1 vol forecast → position sizing | portfolio layer (§7 names it) | **OPEN** |
| H2 expected-dispersion null model for edge-monitor | monitoring, no edge claimed | **OPEN** |
| H3 funding-rate forecast → carry | borderline: modifies holding, not entry | **DEFERRED** |
| H4 directional forecast of BTC returns | signal space | **CLOSED** until the gate concludes |

H4 is the one that would produce the most exciting backtest and it is the
one we are not allowed to run. That ordering is the point of §7.

## 1. Economic rationale (§3 requires this before any run)

**H1 — who pays us: nobody, and that is the honest claim.** A better
volatility forecast is not an edge; it is a sizing improvement. It raises
risk-adjusted return by taking less risk when the coming period is likely
to be violent and more when it is not, out of the SAME edge. Any result
here that looks like new alpha is a bug in the test, not a discovery.

**H2 — no counterparty at all.** A calibrated expected-dispersion band says
whether a live drawdown is inside the range a working strategy produces.
It is a measurement instrument, and it does not require the model to have
any predictive skill on price.

Vol is forecastable in a way returns are not — clustering is one of the
oldest and most replicated facts in the literature — which is why H1 has a
prior worth spending on and H4 does not.

## 2. Candidates and baselines

| Model | Params | Licence | Role |
|---|---|---|---|
| Chronos-2 | 120M | Apache 2.0 | candidate |
| TimesFM-3 | 330M | Non-Commercial v1.0 | candidate (see §8) |
| EWMA(λ=0.94) realized vol | — | — | **baseline to beat** |
| GARCH(1,1) | — | — | baseline |
| Random walk / last realized | — | — | floor |

Both vendors claim state of the art on the SAME three public benchmarks
(fev-bench, GIFT-Eval, Chronos Benchmark II). They cannot both be right and
neither is disinterested, so no published leaderboard is evidence here.
Only our own bake-off on our own series counts.

## 3. Primary metric: CALIBRATION, not accuracy

Adoption is judged on whether the interval is honest, not whether the
median is close. A sizer punished by an overconfident band does not care
that the point forecast was good.

- **Primary (gate):** empirical coverage of the 10–90 band over the test
  window, target 80% ± 5pp. Outside that range the model is rejected for
  sizing regardless of every other number.
- **Secondary:** mean pinball loss across the 9 quantiles, and CRPS, each
  against EWMA on the same windows.
- **Adoption metric (§4 objective, unchanged):** MAR of the vol-targeted
  blend versus fixed-fraction sizing, modern era (2022→), min 100 trades,
  net of 6 bps/side.

Forecast-quality numbers are DIAGNOSTIC GATES. They do not by themselves
adopt anything — the protocol's objective function is still MAR.

## 4. Decision rule (fixed now)

Adopt vol-targeted sizing iff ALL hold:

1. coverage of the 10–90 band within 80% ± 5pp on TRAIN and VALIDATE
2. pinball loss < EWMA's on both windows
3. MAR of the vol-targeted blend ≥ fixed-fraction MAR + 0.15 on both
4. HOLDOUT touched ONCE, after 1–3 pass, and confirms 1 and 3
5. forward shadow (§6) meets 1 and 2 for ≥ 8 consecutive weeks

Anything less is recorded as a failure in §9 and the idea is dropped, not
refitted. A refit is a new batch with its own registration.

## 5. Contamination — treated as unresolved, by default

The Chronos-2 and TimesFM-3 cards do not state an overall training cutoff,
and whether crypto price series appear in their pretraining corpora is
**"not specified"**. Unstated is not absent.

Consequence, and it is the load-bearing methodological decision here:

- **Backtests are context, never the verdict.** Every historical number in
  this study carries an unfalsifiable leakage caveat and must be reported
  with it.
- **The forward shadow (§6) is the primary evidence**, because it is the
  only window that provably post-dates every training corpus.
- Rule 4 above may be satisfied by backtest; **rule 5 may not**.

## 6. Stages

- **S1a frozen bake-off, baselines.** DONE — see section 9.
- **S1b same bake-off, foundation models.** Built, not yet run: needs
  torch and weights, which are deliberately not in any deployed service.

      python3 -m venv ~/.venvs/fmstudy
      ~/.venvs/fmstudy/bin/pip install -r \
          research/forecast_fm/requirements-research.txt
      cd btc-paper-engine/backend
      ~/.venvs/fmstudy/bin/python -m research.forecast_fm.run --with-fm

  Runs on CPU, 343 forecasts per model, minutes not hours. Absent models
  are NAMED and skipped, never silently dropped.
- **S2 forward shadow.** Built: `shadow.py`. Append-only JSONL, the
  forecast written before the outcome exists, `ts_resolve` derived from the
  horizon so a caller cannot choose the window that flatters it, and a
  window that has not closed is refused rather than scored early.
  `score()` reports pending rows alongside resolved ones.

  **S1b gates S2.** A model that cannot beat ATR14 offline does not earn a
  forward shadow; running one anyway would just be a slower way to learn
  the same thing.
- **Where it runs.** In THIS repo, not the sandbox: if it improves the
  edge it belongs in the live stack, and research whose conclusions feed
  sizing does not live in a toy repo. Only the heavy compute goes
  elsewhere, into a separate virtualenv on a box with disk.
- **Nobody runs S2 by hand.** `systemd/fm-shadow.{service,timer}` fires
  every 4h at :07 past the bar boundary. Install:

      mkdir -p ~/fm-shadow
      cp research/forecast_fm/systemd/fm-shadow.* ~/.config/systemd/user/
      systemctl --user daemon-reload
      systemctl --user enable --now fm-shadow.timer
      loginctl enable-linger root      # survives logout
      systemctl --user list-timers fm-shadow.timer

  The unit runs read-only everywhere except its own log, holds no
  credentials, and reads only the public `/bars`. It does not retry: the
  timer fires again in four hours, and a job that silently retried a broken
  feed would fill the record with forecasts made from bad bars.
- **S3 shadow sizing.** Compute the `KELLY_M` the forecast WOULD have
  produced. Logged, never applied.
- **S4 gate.** Live only after §4.5. Executor sizing changes remain
  subject to the RAMP v4 coverage rules on top of this.

## 7. Trials this batch

5 model configs × 2 targets = **10 trials**, to be added to
RESEARCH_PROTOCOL.md §1 on completion. Recorded now so the count cannot be
quietly revised downward if the result is good.

## 8. Licence note

TimesFM 3.0 is under a Non-Commercial Licence prohibiting "any
revenue-generating activity" and use "in production systems". Casey's
decision, recorded here rather than argued: personal use, accepted risk.
Chronos-2 is Apache 2.0 and carries no such restriction, which is a reason
to prefer it on a tie regardless of the licence question.

## 9. Results

### S1a — baselines only, 2026-09-01. HOLDOUT untouched.

Target: forward realized vol over 8 bars (32h = median hold of the
reference pullback trades). VALIDATE = 2024-07-01..2025-09-30, scored on
343 NON-OVERLAPPING windows. Every model dressed with the same TRAIN-fitted
ratio spread, so this compares point forecasts on equal terms.

| model | coverage | gate | pinball | vs incumbent |
|---|---|---|---|---|
| **ATR14 (incumbent)** | 0.799 | PASS | 1.355e-03 | — |
| EWMA(0.94) **range** | 0.834 | PASS | 1.357e-03 | +0.1% |
| GARCH(1,1) | 0.845 | PASS | 1.390e-03 | +2.6% |
| EWMA(0.94) **close** | 0.834 | PASS | 1.406e-03 | +3.7% |
| RandomWalk(8) | 0.796 | PASS | 1.891e-03 | +39.5% |

GARCH(1,1) on TRAIN: omega 7.006e-06, alpha 0.130, beta 0.825,
persistence 0.955.

**Finding 1 — the incumbent is already the best of these, and is
essentially perfectly calibrated** (0.799 against a 0.800 target). Nothing
here justifies changing how the book is sized.

**Finding 2 — the ranking is about the INPUT, not the model.** The same
EWMA recursion fed a Parkinson range estimate instead of closes moves from
+3.7% to +0.1%. A bar that travelled 4% and returned is flat to a
close-to-close estimator and violent to a range one. That difference is an
order of magnitude larger than any difference between the models.

Consequence, and it is the actionable output of S1a: **a foundation model
handed a series of closes starts ~3.6% behind before it forecasts
anything.** Chronos-2 and TimesFM-3 must be given range-derived series, or
OHLC as covariates, or the test measures the input handicap and calls it a
model result.

**Finding 3 — every model fails in the same place, and it is the place
that costs money.** All five pass the aggregate coverage gate, but all five
sag in the upper-middle: at nominal 0.6 the empirical is 0.42-0.53 across
the board. The quantiles that should bound a violent period are too low, so
the sizer takes too much risk exactly when vol is about to spike. That
specific defect — not general accuracy — is where a better forecaster would
earn its place, and it is what S2 should be scored on.

**Prior update: DOWN on H1.** The bar is a well-calibrated incumbent, the
spread between credible models is ~3%, and the honest expectation of a
foundation model beating ATR14 enough to justify running 120M-330M
parameters in the sizing path is now low. Not abandoned — Finding 3 is a
real defect and a genuinely multivariate model is the kind of thing that
could fix it — but S2 should be cheap until it shows something.

Chart: `research/forecast_fm/stage1_baselines.png`.

**Not run:** Chronos-2 and TimesFM-3. torch is not installed in this
container. The adapter interface is `sigma_hat -> (n, 9)` via
QuantileDressing, or nine native quantiles scored directly.

Any figure added here must be dated and state its window and whether it is
TRAIN, VALIDATE, HOLDOUT or shadow. Failures are recorded, not deleted.
