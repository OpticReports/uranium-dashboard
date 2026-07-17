# ⚖️ Barbell Lab

Personal quant research platform for the barbell book:
**80% defensive sleeve ("B.5 Enhanced")** + **20% short-vol options bot**.

Priorities, in order: correctness, reproducibility, statistical honesty,
features. A wrong number presented confidently is the worst possible output —
when in doubt this platform fails loudly.

**Live URL:** `https://research.optic.capital/portfolio-optimizer` — served
behind the existing gate hub (the genomics service's login gate reverse-proxies
`/portfolio-optimizer/*` to this service, same pattern as `/canary/*`).

## Objective function (not Sharpe)

Maximize long-horizon **geometric CAGR** subject to hard constraints:

| constraint | value |
|---|---|
| CVaR(5%, annual) | ≥ −15% |
| 5th-percentile max drawdown | ≥ −20% |
| correlation to bot P&L | ≤ +0.10 |
| single position cap | 25% |

## Layout

```
barbell-lab/
  config/          # yaml: tickers+proxies, weights, constraints, costs, triggers
  data/            # sqlite + parquet + reports (gitignored; Render persistent disk)
  src/barbell/
    ingest/        # yahoo (keyless) / fmp / tiingo / fred adapters -> canonical schema
    validate/      # QA suite + the four ACCEPTANCE GATES
    backtest/      # walk-forward engine, cost model, metrics
    stats/         # DSR, PBO(CSCV), Holm-Bonferroni, trial registry
    portfolio/     # MC engines, geo-CAGR/HRP/NCO optimizers, combined-book sim, Q1/Q2
    monitor/       # rebalance bands, regime quadrants, trigger rules
    report/        # markdown reports with mandatory honesty block + verdict
    web/           # read-only FastAPI view (this is NOT the platform; the CLI is)
  tests/           # pytest; `-m network` marks live-data tests
```

## CLI (the primary interface)

```bash
pip install -e ".[dev]"
cp .env.example .env         # add keys; yahoo+public FRED work with none

barbell ingest               # fetch -> validate -> ACCEPTANCE GATES -> parquet snapshot
barbell acceptance           # re-run the 4 hard gates on stored data
barbell provenance           # live vs proxy rows per ticker
barbell backtest             # baseline sleeve walk (registers a trial)
barbell question1 --bot-model  # tail-sleeve adjudication (TAIL/CAOS/BTAL/none/splits)
barbell question2            # realized rebalancing bonus
barbell optimize --method all  # geo-CAGR (both MC engines) + HRP + NCO cross-checks
barbell monitor              # rebalance bands + regime + triggers (the nightly job)
barbell trials               # cumulative trial registry
barbell import-bot           # pull the bot's P&L from its SQLite
barbell walkforward          # M5: optimizer refit yearly vs current targets, OOS
barbell analyze [--bot-frac] # fund-grade tearsheet (sleeve alone or bot overlaid)
barbell book --sweep         # sleeve/bot fraction frontier — 80/20 is a variable, not an axiom
barbell chat                 # grounded quant analyst (Claude + platform tools; needs ANTHROPIC_API_KEY)
```

The web app serves the same analyst at `/portfolio-optimizer/chat` behind the
gate. Chat simulations run at exploratory path counts, register trials like
everything else, and point to the full-rigor CLI command before anything is
treated as a result.

## Trust chain

1. **Acceptance gates (hard):** KMLM 2022 = +30.4%±0.5, GLD 2022 = −0.8%±0.5,
   TAIL H1-2020 = +15.5%±1, QUAL/MTUM 3y corr = 0.84±0.05. `barbell ingest`
   refuses to snapshot data that fails any gate. **Currently: all 4 pass.**
   (Finding from gate #1: Yahoo drops the capital-gain component of KMLM's
   2022-12-28 distribution — $2.481 vs true $4.0377. Corrected via the
   citation-required `distribution_corrections` config; the corrected series
   matches FMP's independent adjustment to the cent.)
2. **Validation on every ingest:** missing days vs exchange calendar,
   >15% adjusted-close gaps (allowlist requires a documented explanation),
   cross-provider return comparison vs FMP where the key is present.
3. **Provenance:** proxy-extended rows are tagged `proxy:<TICKER>`; splices
   are config-declared with explicit dates (`config/data.yaml`), applied at
   read time only, chaining RETURNS never price levels. CAOS deliberately has
   no proxy until its mutual-fund predecessor is confirmed.
4. **Trial registry:** every evaluated variant is appended (config hash +
   timestamp); the registry has no delete API. Every report prints cumulative
   trial count, DSR, PBO (or why it doesn't apply), Holm-corrected p-value.
5. **Verdicts:** every research report ends IMPROVED / NO_CHANGE /
   INCONCLUSIVE with its statistical basis. The platform is designed to be
   able to say "no improvement found" — and it already has (see below).

## Current findings (as of first full run, 2026-07-17)

* **Q1 (tail sleeve), bot = parameterized model:** NO_CHANGE — no variant
  lifts the combined book's p5(1y) by >+0.5pp over NONE on the common window
  (post-2023-03, limited by CAOS inception); winner unstable across
  kill-switch scenarios; PBO 0.72. **Re-run with real bot P&L before acting**
  (`barbell import-bot`, set `bot.capital_base`, then `barbell question1`).
* **Q2 (rebalancing bonus):** threshold bands beat buy-and-hold by +0.51%/yr
  net of costs on realized history, but the 95% bootstrap CI includes zero →
  INCONCLUSIVE: keep the bands, don't credit the bonus in projections.
* **Optimizer suite:** MVT vs bootstrap geo-CAGR optima disagree materially
  (L1 1.25) → INCONCLUSIVE; treat point allocations as unstable. This
  disagreement is information: the bootstrap engine sees dependence
  structure (crisis co-movement) the elliptical-t engine can't.

## Deployment (Render blueprint)

`render.yaml` at the repo root now defines a third service `barbell-lab`
(Docker, starter plan, 1 GB persistent disk at `/app/data`). On the next
blueprint sync, Render will prompt for `FMP_API_KEY` (+ optional FRED/Tiingo).
The genomics gate-hub service gets `BARBELL_UPSTREAM` and now proxies
`/portfolio-optimizer/*` — same login gate, no separate credentials.
Nightly at 09:00 UTC (05:00 PR): ingest → validation → gates → monitors;
failures write a `job_failure` alert and log CRITICAL, never fail silent.

## Open items (need your input)

1. **Bot SQLite**: real path + schema mapping (`config/data.yaml: bot`) and
   `capital_base`. Until then, `question1` only runs with the explicit
   `--bot-model` flag and stamps every output with the model caveat.
2. **Alerting channel**: currently `log` only. Pick email/push and the
   channel gets implemented; a configured-but-unimplemented mode raises.
3. **CAOS predecessor**: confirm the pre-ETF mutual-fund ticker with Alpha
   Architect before allowing any splice.
4. **KMLM pre-2020 proxy**: ASFYX is an imperfect trend proxy — treat
   pre-2020 KMLM-dependent results as indicative only.

## Statistics implemented from the papers

* PSR/DSR — Bailey & López de Prado (2012 J. Risk; 2014 JPM 40(5)), formulas
  cited in `stats/dsr.py`; verified against analytic invariants and a Monte
  Carlo check of the False Strategy theorem.
* PBO — CSCV per Bailey, Borwein, López de Prado, Zhu (2015, J. Comp.
  Finance); calibrated on pure-noise (≈0.5) and true-signal (≈0) fixtures.
* Holm (1979) step-down correction across the cumulative trial registry.
