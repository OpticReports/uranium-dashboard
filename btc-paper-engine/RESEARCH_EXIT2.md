# RESEARCH_EXIT2.md — research-backed adaptive exits for the S4 trend leg (2026-11-16)

Asked by Casey 2026-11-16, about the live short whose 5×ATR trail locks
~$1,700 of ~$4,700 open profit: "there must be a better strategy for
exits … research … backtesting … potentially applying … multiple
strategies that change depending on the conditions … multivariate."
Registration: `research/exit2/PREREG.md` (commit 6935c31d, before any
variant ran). Code, data, results, figures: `research/exit2/`.

## Verdict

**0 of 28 registered adaptive exits made the cut, so the 12 fresh holdout
coins were never run, as registered.** The 5×ATR trail stays. The holdout
is still unused, so it is available for one future registered candidate.

![map](research/exit2/exit2_fig1_map.png)

## What was tested (from the literature)

| Family | Idea | Source |
|---|---|---|
| V1 | cut size as volatility rises during the trade | Barroso & Santa-Clara 2015; Moreira & Muir 2017 |
| V2 | scale the position with a continuous trend-strength signal, exit when it turns | Baltas & Kosowski |
| V3 | trail width chosen by market regime (volatility, 200-day trend alignment, trend efficiency) | Casey's "strategies that change with conditions" |
| V4 | trail that tightens with time or profit; Parabolic SAR | Wilder; classical |
| V5 | walk-forward logistic model on 11 trade and market features | "multivariate exiting" |

The same literature warns that stop overlays rarely beat the trend rule
itself (Kaminski & Lo; Clare, Seaton, Smith & Thomas). The take-profit
study had already found that for 62 fixed and indicator exits.

## Results

Baseline:
- **BTC live mix, 2022–26:** MAR 1.39 on closed trades, 1.35 marked to
  market.
- **BTC trend leg, 2013–26:** MAR 1.05, ×2,045.
- **Share of the peak kept, on runs that went ≥10% in favor:** median
  **42%** (151 trades). That is the give-back Casey sees on the open trade.

| Best of each family | BTC live mix ΔMAR | BTC trend leg 2013–26 | Other 4 coins | Peak kept | Why it fails |
|---|---|---|---|---|---|
| V4 trail tightens 5→3.5 ATR over ~3 weeks (closest) | +0.18 / +0.19 | +0.04 (×1,010) | 3/4 better, mean −0.02 (ETH −0.59) | 47% | halves BTC growth; ETH ×115 → ×7.5 |
| V3 wider trail when volatility is high | +0.23 / +0.26 | +0.25 (×3,065) | 0/4 | 44% | BTC-only: worse on every other coin |
| V1 cut size as volatility rises | +0.04 / +0.06 | −0.05 (×1,066) | 1/4 | 41% | roughly neutral; misses the +10% bar |
| V2 trend-strength scaling | −0.27 to −0.84 | −0.66 to −0.88 | ≤ 1/4 | 15–20% | exits far too early |
| V4 Parabolic SAR | −0.22 / −0.04 | −1.89 | 1/4 | 45–54% | early-era wipeouts |
| V5 multivariate model | −0.44 / −0.47 | −0.27 | 1/4 | 45% | worse everywhere |

Selection needed A (+10% MAR on both bases) and B (not worse) and D (≥3 of
4 coins better, mean > 0). Of the 28:
- 3 passed A;
- 8 passed B;
- none passed D. Two rules improved 3 of 4 coins but lost on average.

Full rows: `research/exit2/results_sel.json`.

## Why the give-back is hard to remove

![keep vs growth](research/exit2/exit2_fig2_keep_vs_growth.png)

Some exits do keep more of each run. Six rules kept 44–47% of the peak and
grew BTC more over 2013–26 (×2,975–×6,619 vs ×2,045): four regime-based
trails and two slow time-tightening trails. But all six failed on the other
coins, and five of the six also missed the live-mix bar. No rule kept more
on BTC and held up on the other coins.
Across the 28 rules, the share kept and BTC growth are only weakly related
(Spearman +0.25). So the give-back is not itself the cost. Every way we
found to reduce it was BTC-specific.

![near miss](research/exit2/exit2_fig3_nearmiss.png)

## Honesty box

- **In-sample** for selection:
  - BTC to 2026-07;
  - ETH, LTC, XRP, BCH, which were already the take-profit study's
    out-of-sample set.

  The 12-coin holdout (SOL, LINK, ADA, XLM, DOGE, AVAX, DOT, UNI, AAVE,
  ALGO, NEAR, SHIB) was not used: no finalist existed.
- **Basis:** 6 bps/side on entry notional at every close, partials pro rata;
  no slippage or funding. MAR on closed-trade and marked bases. Criterion A
  runs the deployed 50% trend-leg kill switch; B and D run with it off.
- **Not tested:**
  - adding back to a position (all scaling is down-only);
  - combining families;
  - tree or other non-linear models;
  - exits for the pullback leg;
  - portfolio-level interactions beyond the deployed blend.
- **V5:** the model for each year was trained only on in-sample trades that
  closed before that year began; λ, features and thresholds were fixed in
  advance, not tuned.
- **"Peak kept"** is the median share of the best favorable price move
  realized, on trades whose peak move was ≥10% of entry; it includes the
  exit bar's extreme.
- **Trials:** 28, registry ~2,636. §7 overridden by the owner (§9a).

## Counter-agent log

- Verification pending.

## What to do

Nothing changes on the live executors; nothing to redeploy. On the open
short, the trail will lock in more as BTC makes new lows, and gives back up
to ~5 ATR if it reverses.
