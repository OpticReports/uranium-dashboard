# EXECUTOR.md — live S5 execution on Coinbase perps

A separate service that mirrors the paper engine's S5 blend (75% S3 pullback +
25% S4 trend @ 1.5x) onto a real Coinbase Advanced account, sized at the
Kelly-recommended multiplier. The paper engine stays the only decision-maker
and holds no exchange credentials; this service holds a **trade-only** key and
holds no strategy logic. Neither alone can lose money creatively.

## Architecture

```
btc-paper-engine (/exec/target, token-protected)
        |  desired state: pending limits, positions, stops, health flags
        v
btc-executor  --Coinbase Advanced API-->  BTC perp product
   mirror state machine + safety rails       (trade-only API key)
```

- **Pullback leg**: engine's one-bar limit entry -> post-only (maker, ~2bp)
  limit at the same price; cancelled when the engine cancels; ATR stop placed
  on fill as a venue stop-limit.
- **Trend leg**: engine channel-break pending -> market entry; chandelier
  trail mirrored as a venue stop, replaced when the trail ratchets >5bp.
- **Exits**: engine position vanishes -> cancel stop, close at market. If the
  venue stop fired first, the ledger reconciles without double-closing.
- **Sizing**: leg notional = KELLY_M x 1.5 x weight x account equity, read
  from the live account each cycle. Every order passes MAX_NOTIONAL_USD and
  MAX_ACCOUNT_LEV caps.

## Safety rails

| rail | behavior |
|---|---|
| DRY_RUN (default ON) | full state machine runs; orders only logged |
| daily-loss halt | equity < day-start x (1-6%) -> cancel all, flatten, halt |
| drawdown halt | equity < high-water x (1-25%) -> same |
| kill switch | POST /kill -> same; POST /resume to clear (manual only) |
| stale engine | feed stale/degraded -> new entries blocked, exits still run |
| drift check | venue vs ledger position mismatch > 2% equity -> RED event |
| orphan fills | our limit filled but paper cancelled -> unwound at market |
| restart | ledger + order map persisted; reboot re-places nothing |

## Setup

1. **Coinbase**: enable derivatives; fund with USDC. Create a CDP API key with
   **view + trade only** (no transfer/withdraw). Note the key name and private
   key PEM.
2. **Render**: deploy the `btc-executor` service from render.yaml. Enter
   secrets in the dashboard: `CB_API_KEY_NAME`, `CB_API_PRIVATE_KEY`,
   `EXEC_TOKEN` (same value as on btc-paper-engine).
3. **Product**: boot logs list every BTC futures product the key can trade
   (`BTC futures products visible to this key: [...]`). Set `CB_PRODUCT_ID`
   accordingly (INTX perp: `BTC-PERP-INTX`; US CFM contracts appear with a
   `-CDE` suffix and trade in 0.01-BTC contracts — the adapter handles both).

## Rollout gates (do not skip)

1. **Dry-run** (DRY_RUN=true, the default): watch `/status` for ~a week.
   Check `dry_run_intents` against the paper engine's trades: same entries,
   same stops, sane sizes, no drift/RED events.
2. **Token size**: DRY_RUN=false with KELLY_M=0.05 (~7% notional). Let 15-20
   trades complete; compare live fills vs paper (fees, slippage, funding).
3. **Kelly size**: raise KELLY_M to 0.56 (the deliberately-conservative 2y
   recommendation). The 5y out-of-sample study (RESEARCH_5Y.md) supports a
   post-validation ceiling of 0.80 — allowed only after 15-20 live trades
   with tracking error within model and zero halt events. Re-run the Kelly
   study quarterly and after any 15%+ drawdown.

## Expectations (measured, 2y window, dashboard basis)

S5 at KELLY_M=0.56 on Coinbase perps modeled at ~33.7% CAGR gross of funding
(paper dashboard 32.8%); at full size P(maxDD>30%) ~14%, at Kelly size ~10%
budget. These are in-sample numbers on the window the strategy was selected
on — treat as ceilings, not forecasts. Funding is unmodeled and measured
during the token-size phase.

## Operations

- `GET /status` — mode, halts, per-leg ledger, last 50 events, dry-run intents
- `POST /kill` / `POST /resume` — emergency stop / manual restart
- Executor state: `/app/data/executor_state.json` (persistent disk)
- The engine's `/exec/target` is token-protected; set EXEC_TOKEN on BOTH
  services or the feed 401s.
