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

## 2026-07-16 — TAIL proceeds deployed to crash sleeve (owner-directed)

- Change (capital): invested $16,900 into sleeve `nNdBk7hc5NiBzeRvbI5T`
  (deploy d71a27c5, executes today 19:50Z window). Owner redirected from
  the engine plan: purpose = correlation hedge for the IBKR book. Data:
  sleeve~SPY corr −0.14 (15y) and +30.5% avg crash capture, vs P5~SPY
  +0.28 and −24.5% in the Jan–Feb 2025 episode. Sleeve lands ~$71k ≈
  11.8% of family crash-exposed assets (in-band). Monitor band alert
  also fixed today to use the POLICY.md family denominator.


## 2026-07-14 — residual cash swept to P5

- Change (capital, owner-directed): invested $140 residual cash into P5
  `YPTSJFJwD2ZKfAeYJUbW` (deploy 7a602c18) — most underweight engine
  (28.4% vs 35% target). ~$11 dust remains.


## 2026-07-10 — $30k deposit deployed to crash sleeve (per staged plan)

- Change (capital, owner-directed): invested $30,000 into the sleeve
  `nNdBk7hc5NiBzeRvbI5T` (deploy 427f1feb, executes 2026-07-10 19:50Z
  window). Sleeve lands at ~$52k ≈ the ~$53k family target (10% of
  crash-exposed assets per POLICY.md). PENDING DEPOSIT block removed.
- Next: TAIL sale proceeds (~$17k), when sent, go to the most underweight
  engine on the owner's confirmation.


## 2026-07-07 — reallocation COMPLETE — final leg executed

- Change (capital, per approved plan): final invest $41,463 into P5
  `YPTSJFJwD2ZKfAeYJUbW` (deploy 0bf3edd3, fills 2026-07-08 window) from
  ORIG liquidation proceeds. Tuesday window fills confirmed: sleeve
  `nNdBk7hc5NiBzeRvbI5T` live $21,825, P5 first tranche live $27,763,
  ORIG `rhZ9oDAUvN26v5Ra5qql` fully liquidated (definition kept in
  drafts).
- End state (at Wed fill, ~$209k book): HG ~$117.8k (56.4%) / P5 ~$69.2k
  (33.1%) / sleeve ~$21.8k (10.4%) — all within POLICY.md bands.
  Reallocation project complete; ongoing ops = lean daily band check
  (fresh-session trigger) + POLICY.md standing operations.
- Artifacts: deploy ids in this entry and the two prior entries.


## 2026-07-06 — reallocation executed (user-approved) + sleeve funded 10%

- Change (capital, explicitly approved in-session):
  - AM: withdrew $49,075.85 from HG `mbkiXcuNDjueXpiox5Av` (executed same
    day; HG now ~$118.8k = 55%) and requested full exit of ORIG
    `rhZ9oDAUvN26v5Ra5qql` $47,616.90 — Composer converted it to a full
    **liquidation**, pending tomorrow's window (~$46.0k).
  - PM (post-close, queued for 2026-07-07): invested **$21,424 into the
    crash sleeve** `nNdBk7hc5NiBzeRvbI5T` (10.0% of book, deploy 8cfad181)
    and **$27,870 into P5** `YPTSJFJwD2ZKfAeYJUbW` (deploy eab1bb62).
    Final leg (ORIG liquidation proceeds ~$46k -> P5) queues after landing.
- Why:    allocation study (addendum 3) + sleeve sizing frontier (addendum
  5/7): target HG 55 / P5 35 / sleeve 10; user chose 10% sleeve.
- Tooling: monitor.py now alerts on sleeve monetization-band breach
  (target 10%, band 7.5–15%); composer-api.py trade preview made
  best-effort (endpoint 402s on this account tier for new deploys).
- Artifacts: deploy ids above; policy in results.md addendum 7.


## 2026-07-06 — draft cleanup — two rejected variants deleted

- Change: deleted saved symphonies `gRwiDs9bEHhW3vjXrNdW` "KMLM switcher —
  TREND GATE ONLY" and `F9yaDwptEh8MOnNy3CIl` "KMLM switcher — FULL REGIME
  v1" (both rejected by the safeguard study — worse than the original on
  every risk metric). Definitions archived first to `fixtures/rejected/`.
  Keepers untouched: crash sleeve `nNdBk7hc5NiBzeRvbI5T`, P5
  `YPTSJFJwD2ZKfAeYJUbW`, vol cap `tbm9SE57MoSeY7rOEhys`.
- Why:    user asked to prune underperformer drafts.
- Artifacts: `fixtures/rejected/trend-gate-only.json`,
  `fixtures/rejected/full-regime-v1.json`.


## 2026-07-06 — sleeve deep-history validation; rebalance set to daily

- Change: `nNdBk7hc5NiBzeRvbI5T` root rebalance `none`+corridor -> `daily`
  (wash on stats, matches components' native setting; old version
  `OT3P700PVT2iG95wnaLq` preserved). No other symphony changed; audit
  confirmed none of ours use monthly/quarterly.
- Why:    user asked for 20-30y validation. Deep-proxy sleeve (LABD->BIS,
  KMLM->DBC) reaches 2011: +47.6% CAGR / Sharpe 1.30 / maxDD 16.3% over
  15y, positive in 10/12 SPY crash episodes incl. COVID +172% and 2022
  +82%, calm carry +28.7%/yr. 20y Monte Carlo: median CAGR +47%,
  P(DD>30%) 0.2%.
- Artifacts: `results/results.md` addendum 4c,
  `results/monte-carlo-sleeve-20y.json`.


## 2026-07-06 — crash sleeve optimization pass — no change adopted

- Change: none — `nNdBk7hc5NiBzeRvbI5T` kept at 50/50 threshold-rebalance.
  10 variants tested (weight sweep, monthly/quarterly rebalance, +KMLM,
  +gated-VIXM, +VIXstrat legs).
- Finding: weights are flat (robust); third legs dilute; monthly/quarterly
  root rebalance destroys signal-driven trees (+48% -> -1%/-11% CAGR) since
  root frequency gates condition re-evaluation. Recorded as a hard rule.
- Artifacts: `results/results.md` addendum 4b.


## 2026-07-06 — crash-convexity research — sleeve saved (uninvested)

- Change: created saved symphony `nNdBk7hc5NiBzeRvbI5T` "Crash Convexity Sleeve —
  InverseHold + Bond Frontrunner 50/50" (50% `sYcm9hgSipM4TkpFcuSj` +
  50% `hA7nbIZL4cdRBzikH47U`). Nothing invested.
- Why:    user asked for best per-dollar crash payout with minimal bleed.
  15-candidate panel vs SPY's four >8% episodes since 2022: all static
  hedges bleed (UVXY -86%/yr); two community signal strategies are
  positive-carry hedges; their 50/50 blend is positive in all four
  episodes with +48%/yr calm carry, maxDD 14.8%, corr to HG -0.12.
- Artifacts: `results/results.md` addendum 4.


## 2026-07-05 — portfolio allocation study (no changes, analysis only)

- Change: none — analysis artifact only (`results/allocation-grid.json`,
  results.md addendum 3).
- Why:    quantify how the two invested symphonies interact and where P5
  fits. HG~ORIG corr +0.30; crash episodes complementary (Jan-Feb 2025:
  HG -8.1% vs ORIG -32%). Blend grid over 804 common days.
- Finding: current HG79/ORIG21 sits off the frontier. HG 50-60 / P5 40-50
  band improves full-window CAGR (+129%->+151..173%), Sharpe (2.15->2.5+),
  and cuts OOS drawdown (17.8%->~14%) at a ~4pt OOS CAGR give-up.
- Artifacts: `results/allocation-grid.json`, `results/results.md`.


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
