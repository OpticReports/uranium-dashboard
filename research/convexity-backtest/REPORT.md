# Results — long-horizon reconstruction harness (v2, post-audit)

Purpose: test whether a strategy's leverage/convexity sleeves can be validated
across far more history than Composer's ~2021 ETF-inception floor, **without**
manufacturing a false positive. What follows is what the harness has actually
*proven*, and — just as important — what it has not.

## 1. The engine is validated against the real ETF

Synthetic TQQQ is rebuilt from the NASDAQ-100 index (daily reset, fees,
financing on the borrowed leg, dividend add-back) and compared to the **actual
TQQQ** over their 2010–2026 overlap:

| metric | value | pass criterion |
|---|---|---|
| daily-return correlation | **0.9986** | ≥ 0.95 |
| beta vs real TQQQ | **1.02** | \|β−1\| ≤ 0.15 |
| annualized tracking error | **3.55%** | — |
| sign-flipped negative control | **fails (as it must)** | corr < 0 |

The reconstruction tracks the real product tightly, and a deliberately
sign-flipped engine is caught. This is the credibility keystone for trusting the
pre-ETF extension.

## 2. What the longer window reveals (Tier 1, data-grounded to 1986)

Excess-return stats (over 3M T-bill), 40.5 years:

| series | CAGR | vol | Sharpe (excess) | max drawdown |
|---|---|---|---|---|
| NDX buy&hold (1×) | 14.2% | 26% | 0.52 | −83% |
| synthetic TQQQ (3×) | 13.7% | 78% | 0.52 | **−99.98%** |

The headline is the drawdown: **a 3× NDX sleeve was effectively wiped out
(−99.98%) in the 2000–02 dot-com bust** — 3× more CAGR-destroying leverage decay
than Composer's post-2021 window can show. On this history 3× buy&hold delivers
*less* CAGR than 1× at 3× the volatility. Any strategy leaning on 3× equity
beta has to earn its keep by getting *out* before those regimes, and the only way
to test that claim is on data that contains them.

## 3. The watchdog can tell a real edge from an artefact

Run on three example gates (NDX 200-day) purely to test discrimination:

| strategy | look-ahead violations | verdict |
|---|---|---|
| causal gate (uses t−1) | 0 | clean — no flags |
| same-bar gate (uses today) | 8 | **INVALID — look-ahead** |
| centered-average gate (uses future) | 11 | **INVALID — look-ahead** |

Plus: deflated Sharpe now deflates with trial count (n=1→1.00, n=50→0.85,
n=500→0.60) and returns ~0 for a losing series; Sharpe is risk-free-adjusted;
reconstruction Sharpe moves only 0.036 across the fee/financing/dividend
assumption grid.

## 4. What this does NOT prove (the honest ledger)

- **Not the crash-convexity sleeve.** No real symphony definition yet — Composer
  **Step D** hasn't run. The gates above are scaffolding to test the watchdog,
  not your strategy.
- **Not the vol sleeve's magnitudes.** This environment has VIX **spot**, not VIX
  **futures**/SPVXSTR. The UVXY-like series is **Tier-2 modelled / illustrative**
  and is never quoted as validated.
- **Unmodelled biases** (documented): NDX survivorship/reconstitution inside the
  Tier-1 index; no transaction costs/turnover/slippage on traded strategies.

## 5. To turn this into a real validation of your sleeve

1. Run **Step D** → capture the real symphony definition + tickers/weights/params.
2. Reproduce Composer's **2021+ backtest on the overlap** with this engine — if it
   matches, the extension is trustworthy; if not, we're measuring our own bugs.
3. Wire **real VIX-futures/SPVXSTR** for the convexity sleeve (removes Tier-2).
4. Run the strategy — not buy&hold — through the full watchdog, passing the
   **true `n_trials`** so the deflated Sharpe reflects the actual search, and add
   turnover-based costs.

See `AUDIT.md` for the adversarial review and the fixes that produced this v2.
