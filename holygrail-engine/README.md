# holygrail-engine: Dalio Holy Grail forward + backtest engine

> **Naming:** "Dalio Holy Grail" here is Ray Dalio's diversification framework; it is
> unrelated to Casey's **Composer HG symphony** (a 3x-momentum strategy that shares the name).

Library + CLI + tests. Not a Render service (no `render.yaml` entry, no web app).

## The framework, as engineered

Dalio (*Investment Principles: What Should...*, Substack, 2026-06-15): *"strive to have 15
good uncorrelated investments that are risk balanced"* and *"engineer the portfolio to the
desired risk level."* Four operations, each a module:

| Operation | Question | Where |
|---|---|---|
| 1. GOOD streams | expected excess return > 0, Sharpe above a threshold | `scorecard.py` screen |
| 2. UNCORRELATED | how many independent bets do we really hold? | `core.effective_bets`, `robustness.py` |
| 3. RISK-BALANCED | risk share vs dollar share | `core.risk_contributions`, `allocate.py` |
| 4. GEARED | lever the mix to the desired vol | `core.geared_return`, `allocate.target_vol_gearing` |

### Core identities (exact, tested)

- `sigma_p^2 = w' S w`. Equal vol `sigma`, equal pairwise `rho`, weights `1/N`:
  `sigma_p = sigma sqrt((1+(N-1)rho)/N)`, improvement `sqrt(N/(1+(N-1)rho))`, floor `sigma sqrt(rho)`.
  Dalio check (`sigma` 18%, `rho` 0): N=5 **8.050%**, N=10 **5.692%**, N=15 **4.648%**;
  return/risk 0.3333 -> **1.2910** = x**3.873** (= sqrt 15). Dalio's "4.3x" comes from rounding
  6/18 down to 0.3; the exact factor is sqrt(15).
- Euler risk contributions `RC_i = w_i (S w)_i / sigma_p` sum to `sigma_p`; `PRC_i` sum to 1.
- **Holy Grail multiplier = diversification ratio.** If every stream has Sharpe `s`,
  portfolio Sharpe = `s * DR`, `DR = w'sigma / sigma_p`. So `DR^2` is the headline N_eff:
  it equals `N/(1+(N-1)rho)` in Dalio's equal case and Dalio's improvement factor is `sqrt(N_eff)`.
- Gearing: `L = sigma*/sigma_p`; `r(L) = rf + L(mu_p - rf) - max(L-1, 0) spread` (spread on the
  borrowed part only); `g(L) = r(L) - L^2 sigma_p^2/2`; Kelly `L* = (mu_p - rf)/sigma_p^2`
  (kinked at L=1 when there is a spread); `P(losing year) = Phi(-mu/sigma)`.

### Effective number of bets: five measures, two families

| measure | family | perfectly correlated book | equal-weight equal-rho book |
|---|---|---|---|
| (e) `DR^2` **headline** | correlation-aware | 1 | `N/(1+(N-1)rho)` |
| (a) `N/(1+(N-1)rho_bar)` | correlation-aware | 1 | same |
| (c) Meucci 2009 PCA entropy | correlation-aware | 1 | 1 for every rho > 0 (N at rho = 0: discontinuous; flagged) |
| (b) `1/sum PRC^2` | risk-balance | inverse HHI of `w_i sigma_i` shares | **N at any rho** |
| (d) minimum torsion (MSD 2015) | risk-balance | (regularised) | **N at any rho** |

(b) and (d) measure *how evenly risk is spread*, not *how independent the bets are*: an
equal-risk book of nearly identical assets scores N on both. Dalio's claim needs both
properties, so read the families together. The scorecard leads with `DR^2`.

## Modules

`core` math, pure functions · `estimate` calendars/alignment (crypto 7-day vs equity 5-day),
sample/EWMA/Ledoit-Wolf (identity and constant-correlation), pairwise + Higham repair,
Geltner de-smoothing, Dimson betas, lag-summed covariance · `streams` Market/Series/
Parametric/Cash/Composite streams and the joint moment model (every stream is a linear
exposure over leaves) · `data` Yahoo + FRED with cache and provenance · `book` YAML
schema, views, reconciliation · `allocate` EW, inverse vol, ERC/risk budgets (Spinu Newton
and CCD, verified to 1e-10), min variance, max diversification, HRP, quadrant balance,
caps, target-vol gearing · `backtest` walk-forward · `forward` MVN / Student-t / stationary
bootstrap MC, default jumps, correlation stress, scenario replay · `robustness` bootstrap CIs,
rho sensitivity, regime/rolling correlations, shrinkage comparison · `environments`
growth x inflation regimes from FRED and All Weather box balance · `scorecard` · `report`
charts + rows · `cli`.

## CLI

```bash
cd holygrail-engine
python -m holygrail curve                                   # Dalio curve (no data)
python -m holygrail score --book books/example.yaml --view investable
python -m holygrail backtest --tickers SPY,TLT,GLD,DBC,TIP --allocator erc --target-vol 0.10 \
    --max-leverage 2 --benchmark SPY                        # walk-forward, daily MTM
python -m holygrail forward --book books/example.yaml --target-vol 0.10 --method t
python -m holygrail stress --book books/example.yaml --corr-rho 0.6 --missing cash
python -m holygrail envs --tickers SPY,TLT,GLD,DBC
```

Every command prints a compact summary and writes PNG charts plus the CSV/JSON rows behind
them to `--out` (default `./results/<command>`, gitignored). `--offline` reads only the
cache (`data/cache`, gitignored); a failed feed raises, and there is never a stale fallback.

## Book schema

See `books/example.yaml` (illustrative numbers). Every assumption is
`{value, source, confidence}` (`high|medium|low|placeholder`); a bare number fails. Named
assumptions are referenced as `"@key"`. Positions carry `liquidity` (`liquid|semi|illiquid`),
`mark_basis` (`market|model|appraisal|cost|round`), `sleeve`, `tags`, `investable`.
`totals.total_usd` and `totals.sleeves` must reconcile within `tolerance_usd`.
Proxies are declared per stream with an explicit splice date (`proxies: [{symbol, until}]`).

## Timing and honesty

- Backtest: weights at estimation date t use returns up to and including t; they trade at
  t's close and earn from t+1. Enforced by a bit-for-bit mutation test.
- Measurement basis: daily mark-to-market. All backtest metrics are in-sample history.
  Historical means used as expected returns are labelled `historical_in_sample`; they are
  not forecasts.
- Selection bias: tickers and books are chosen today, so every backtest replays ex-post choices
  (survivorship / selection bias). `--allocator book` is a constant mix of today's weights
  (hindsight), not walk-forward, and is labelled so.
- Gearing: leverage L scales the NON-cash streams. The book's own cash funds the extra exposure
  first; only new borrowing, max(L(1 - cash) - 1, 0), pays rf + spread (scorecard, Kelly, forward
  and backtest use the same rule). `max_leverage` caps gross non-cash exposure.
- Calendars: daily data is annualised on the observed periods per year (~252 exchange days,
  ~365 for crypto-only), measured on the rows where every stream has data (a crypto-only stretch
  before a later business-day stream starts does not count), and constant rates, fees and spreads accrue by calendar days. A stream
  marked more coarsely than the analysis frequency (e.g. month-end NAVs at weekly) is refused
  rather than forward-filled into fake zero returns. Benchmarks are aligned as-of by level.
- Correlation stress (`stress --corr-rho`) floors every leaf correlation at rho; it never lowers
  one, and streams are rebuilt through look-through.
- Not modelled (also printed in every scorecard): taxes; liquidity and lock-ups; currency;
  correlation time-variation within one estimation window; stale-mark vol understatement
  unless de-smoothed; volatility decay of daily-reset composites in arithmetic moments.

## Tests (merge-blocking)

```bash
cd /home/user/uranium-dashboard && python -m pytest holygrail-engine/tests -q             # offline
cd /home/user/uranium-dashboard && python -m pytest holygrail-engine/tests -q --run-network  # + live feeds
```
