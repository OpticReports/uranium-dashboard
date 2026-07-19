# Adversarial audit & resolutions

An independent auditor agent re-ran the harness and tried to prove its results
were false positives. It reproduced every number, then found that **two of the
harness's own "proofs of correctness" were hollow** — the anti-overfitting metric
and the engine-correctness check. That is exactly the failure mode this project
exists to prevent, so the findings were fixed, not just noted. Below: each
confirmed finding, and what changed (`v1` → `v2`).

## Confirmed bugs (all fixed)

### 1. Deflated Sharpe was inert — returned 1.0 for *any* series, even losers
`v1` computed the expected-max-Sharpe benchmark as `norm.ppf(1 - 1/n_trials)`,
which at the configured `n_trials=1` is `norm.ppf(0) = -inf`, so the benchmark
was `-inf` and `DSR = Φ(+inf) = 1.0` for everything. The one check meant to catch
multiple-testing/overfitting could never fire.
**Fix:** `expected_max_sharpe_z()` returns 0 at `n_trials<=1` (no deflation when
nothing was searched) and the Bailey–López de Prado expected-max for `n>=2`; the
benchmark is scaled by the annualized Sharpe-estimate dispersion.
**Verified:** negative series now DSR `0.0001` (was 1.0); n=1→0.9995, n=50→0.85,
n=500→0.60.

### 2. `engine_sane` was a tautology a sign-flipped engine passed
`v1` "validated" the reconstruction with `3x Sharpe <= 1x Sharpe`, which merely
requires costs > 0 and says nothing about leverage sign, scale, or compounding —
a `leverage=-3.0` engine passed it.
**Fix:** replaced with `reconstruction_tracking()` against **real TQQQ** (Yahoo,
2010+ overlap): daily-return correlation, OLS beta vs the real ETF, tracking
error. A sign-flipped **negative control** is run every time and must fail.
**Verified:** synthetic vs real TQQQ corr **0.9986**, beta **1.02**, tracking
error **3.55%/yr**, pass=True; sign-flipped control pass=False.

### 3. Look-ahead probe was blind to same-bar peeking
`v1` corrupted only rows strictly *after* `t`, so a strategy trading on *today's*
close (unimplementable live) was certified causal.
**Fix:** probe now corrupts rows `>= t` and uses a large deterministic shift so
mean-dependent leaks can't average out.
**Verified:** a same-bar gate now yields 8 violations (was 0/"causal").

### 4. The causality probe wasn't wired into `evaluate()`
`v1` left `rep.lookahead` empty in the battery that produces the flags.
**Fix:** `evaluate()` takes `strategy_fn`/`strategy_inputs`, runs the probe, and
raises a `LOOK-AHEAD ... Result is INVALID` flag.
**Verified:** causal gate → 0 flags; same-bar & centered leaks → INVALID flags.

## Statistical concerns (addressed)

- **No risk-free subtraction.** Sharpe/PSR/DSR now run on **excess** returns over
  the 3M T-bill (NDX buy&hold Sharpe drops 0.64→0.52 once rf is removed).
- **Misleading "flags raised" note** removed; run notes now state facts only.
- **Documented, not hidden:** NDX survivorship/quarterly-reconstitution bias lives
  inside the Tier-1 index; no transaction-cost/turnover/slippage is modelled on
  traded strategies; `walk_forward_degradation` measures early-vs-late regime
  stability, not refit-per-fold (fine for fixed-parameter examples, insufficient
  for optimized strategies — flagged for when real optimization begins).

## Accepted limitations (watchdog gaps still open)

- Block-bootstrap block length isn't stress-tested (vol clustering may understate
  CI width).
- `assumption_sensitivity` reports the spread but can't stop a caller quoting the
  best cell — best-of-grid discipline is on the analyst.
- The battery is exercised on buy&hold + three toy gates; it has not yet been run
  against a *marginal* real strategy (that arrives with Step D).

## Verdict carried forward

Auditor verdict was **trust WITH-FIXES**; the two hollow proofs are now real and
verified. The data plumbing, tier quarantine, PSR and bootstrap were sound in v1
and are unchanged.
