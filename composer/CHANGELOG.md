# Composer Symphony Changelog

Every symphony mutation gets an entry: **what** changed, **why**, and the
backtest stats **before / after**. Read-only baselines are logged too, so the
history is a complete audit trail. Newest first.

Format per entry:

```
## YYYY-MM-DD — <symphony name / id> — <short title>
- Change: <what changed in the logic tree>
- Why:    <rationale>
- Before: <key backtest stats — CAGR, Sharpe, max drawdown, period>
- After:  <key backtest stats>
- Artifacts: fixtures/<file>, results/<file>
```

---

<!-- New entries go below this line, newest first. -->

## 2026-07-05 — Simons KMLM switcher (`rhZ9oDAUvN26v5Ra5qql`) — baseline capture

- Change: none — read-only baseline only (Step D).
- Why:    establish a reference point before any optimization is proposed.
- Before: —
- After (baseline): CAGR **600.8%** (annualized_rate_of_return 6.008),
  Sharpe **2.89**, max drawdown **32.0%**, cumulative return **3548×**,
  period **2022-04-13 → 2026-07-03** (1,057 trading days; start clamped by
  SVIX inception). Params: $10k, v2 engine, reg+TAF fees, 0.05% slippage.
- Artifacts: `fixtures/rsi-rotation.raw.json`,
  `fixtures/rsi-rotation.summary.md`, `results/baseline.json`
- Notes:
  - The "RSI rotation" symphony is saved as *"Simons KMLM switcher (single
    pops) | BT 4/13/22 = A.R. 466% / D.D. 22% V2 (Buy Copy)"*. Its logic tree
    is **all 10-day RSI conditions** — there is **no SPY 200-day
    moving-average gate** in the saved definition (the SPY check is
    `RSI(10d) > 80` → UVXY).
  - Captured via the **Composer REST API** (`api.composer.trade`, same
    credentials/headers) because the MCP endpoint `ai.composer.trade/mcp`
    returned 404 for the whole host on 2026-07-05 and the public
    `invest-composer/composer-trade-mcp` GitHub repo is gone. The deny-list
    reconciliation against the live MCP tool manifest (README §2) is
    therefore still pending; no trading/deploy REST endpoint was called.
