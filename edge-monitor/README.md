# edge-monitor

Venue-agnostic edge-decay & risk-regime monitoring (keyless — reads engine
data, never touches orders). Docs: `RESEARCH.md` (methods), `BLUEPRINT.md`
(system design), `REFEREE.md` (counter-agent verdict).

## Implemented (gate-tested)

- `psr.py` — `psr(returns, sr_benchmark)`, `dsr(returns, n_trials, sr_std)`,
  `min_trl(sr, sr*, skew, kurt, conf)`, `sharpe_stats`, `expected_max_sr`
- `cusum.py` — `CusumState(k, h).update(z)`, `calibrate_h(backtest_returns,
  target_arl, k, block, n_sims)` (MC block-bootstrap ARL)
- `dd_percentile.py` — `dd_percentiles(live, backtest, block, n_sims)` →
  length-matched max-DD + underwater percentiles, `insufficient` first-class
- `bocd.py` — `Bocd(hazard).update(x)` → `p_change_recent`, `map_run_length`;
  `standardize(returns)` (lagged EWMA vol, no lookahead)

## To build (signatures frozen in BLUEPRINT §7)

```python
db.connect(path) -> sqlite3.Connection                      # schema §2
adapters.coinbase.sync(con, executor_state_path) -> int     # trades+nav rows
adapters.composer.sync(con, api_or_csv) -> int
adapters.shadow.sync(con, barbell_db) -> int
baseline.register(con, strategy_id, backtest_returns,
                  n_trials, sr_std_across_trials) -> str    # freezes json, calibrates
layers.run_daily(con, date) -> list[Check]
layers.run_weekly(con, date) -> Digest                      # incl. BH-FDR
statemachine.step(con, strategy_id, checks) -> StateChange | None
report.daily_line(con) -> str; report.weekly_digest(con) -> str
```

Tests: `python -m pytest tests/` — 13 gates: null calibration (PSR uniform,
CUSUM ARL, DD false-alarm rate), power on injected decay, honesty gates
(BOCD blindness to SR-sized shifts, `insufficient` outputs, no-lookahead
standardization).
