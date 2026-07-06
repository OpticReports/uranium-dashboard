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

## 2026-07-05 — improvement panel — six ideas tested individually

- Change: created one new saved symphony `YPTSJFJwD2ZKfAeYJUbW`
  "KMLM switcher + VIX sleeve 75/25" (75% original / 25% verified public
  VIX strategy `2pOC3xJ0uBNHwrlPiQNh`, corr +0.06). P1 inverse-vol rotator,
  P2 KMLM ballast, P3 VIX-term pass-through, P4 defensive candidates,
  P6 pop confirmation: backtested ad-hoc only, NOT saved (all rejected).
  Original untouched; nothing invested.
- Why:    continue the safeguard study — improve risk without killing the
  return engine.
- Before (original, P5-matched window 2023-04-19..): CAGR 323.2%, maxDD
  32.0%, Sharpe 2.34; OOS Sharpe 1.04, OOS DD 28.7%.
- After  (P5 pair): CAGR 229.9%, maxDD 24.5%, Sharpe 2.44; OOS Sharpe 1.08,
  OOS DD 20.4%. Better on every risk metric in every window; only variant
  of 12 tested today that improves OOS risk-adjusted performance.
- Artifacts: `results/results.md` (addendum 2).


## 2026-07-05 — safeguard panel — three protections tested individually

- Change: created one new saved symphony `tbm9SE57MoSeY7rOEhys`
  "KMLM switcher — ROTATOR VOL CAP 75/25" (risk-on rotator filter blended
  75% / 25% BIL). V1 (XLK trend gates @200/100/50d) and V2 (TQQQ 60d-DD>20%
  circuit breaker) were backtested ad-hoc only and NOT saved. Original
  untouched; nothing invested.
- Why:    the original's 32% maxDD (Jan-Feb 2025) occurred fully above trend,
  holding rotator TECL/SOXL/SVIX — target that branch specifically.
- Before (original): CAGR 600.8%, maxDD 32.0%, MAR 18.75, Sharpe 2.89.
- After:  vol cap 75/25: CAGR 461.6%, maxDD 27.4%, MAR 16.87, Sharpe 2.82,
  crash episode -27.4% vs -32.0%. Trend gates: no DD change (XLK never broke
  200d SMA in the episode). DD breaker: worse (42.1% DD, fires after the
  loss). Full table in `results/results.md` addendum.
- Artifacts: `results/results.md` (addendum), backtests in session scratch.


## 2026-07-05 — regime-gate experiment — two variants created (backtest-only)

- Change: created two *new saved* symphonies (original untouched, nothing
  invested):
  - Copy A `gRwiDs9bEHhW3vjXrNdW` "KMLM switcher — TREND GATE ONLY" — whole
    tree inside `IF SPY > 200d SMA`, else 100% BIL.
  - Copy B `F9yaDwptEh8MOnNy3CIl` "KMLM switcher — FULL REGIME v1" — trend
    gate + all 11 pop-leg UVXY allocations swapped for a VIXY/VIXM 20d
    cum-return switch (UVXY/SVIX) + layered risk-off sleeve.
- Why:    test whether a trend gate and vol-term-structure awareness improve
  risk-adjusted returns.
- Before (original): CAGR 600.8%, Sharpe 2.89, maxDD 32.0%, MAR 18.75.
- After:  Copy A CAGR 180.9%, Sharpe 2.06, maxDD 32.0% (unchanged!), MAR 5.6.
          Copy B CAGR 65.7%, Sharpe 1.15, maxDD 50.0%, MAR 1.3. Both worse —
          gate never fired during the original's worst stretch; 90% of pops
          resolved to SVIX (short vol at long-vol moments). **Keep original.**
- Artifacts: `results/results.md`, `fixtures/original_symphony.json`.


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
