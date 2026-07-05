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

## (pending) — RSI rotation symphony — baseline capture

- Change: none yet — read-only baseline only (Step D).
- Why:    establish a reference point before any optimization is proposed.
- Before: —
- After:  see `results/baseline.json` once the backtest has run.
- Artifacts: `fixtures/` (raw JSON + logic-tree summary), `results/baseline.json`
