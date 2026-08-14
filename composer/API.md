# Composer REST API — verified route map

Extracted from the OpenAPI 3.0 spec embedded in
<https://api.composer.trade/docs/index.html> on 2026-07-05, then **verified
live** (every ✅ below was actually called read-only with our credentials).
This replaces the MCP server (`ai.composer.trade/mcp`), which went offline —
whole host 404, public GitHub repo removed.

- **Base URL:** `https://api.composer.trade`
- **Auth headers (every request):**
  - `x-api-key-id: $COMPOSER_API_KEY_ID`
  - `authorization: Bearer $COMPOSER_SECRET`
- Helper CLI: [`scripts/composer-api.py`](scripts/composer-api.py)
- Our account UUID: `b4ee3fe9-fc12-4991-8df4-de29c857099c` (ALPACA_WHITE_LABEL,
  INDIVIDUAL, EQUITIES) — rediscoverable via `GET /accounts/list`.

All paths below are prefixed with `/api/v0.1` unless noted.

---

## 1. Accounts & portfolio (read-only)

| Route | Notes |
| --- | --- |
| ✅ `GET /accounts/list` | all brokerage accounts (`account_uuid` is the id used everywhere) |
| `GET /accounts/{account-id}/holdings` | raw positions |
| `GET /portfolio/accounts/{account-id}/holding-stats` | per-holding stats |
| ✅ `GET /portfolio/accounts/{account-id}/symphony-stats-meta` | **per-symphony stats** — the "list my symphonies" call (value, sharpe, max DD, holdings, next rebalance) |
| `GET /portfolio/accounts/{account-id}/symphonies/{symphony-id}` | one position's value over time |
| `GET /portfolio/accounts/{account-id}/portfolio-history` | whole-account value over time |
| `GET /portfolio/accounts/{account-id}/symphony-historical-holdings` | historical holdings per symphony |
| `GET /portfolio/accounts/{account-id}/total-stats` | aggregate portfolio stats |
| `GET /reports/{account-id}` | account report |
| `GET /accounts/{account-id}/info/investor-documents` | statements etc. |

## 2. Symphonies — read, create, edit (goal: *prompt-to-edit / create custom*)

| Route | Notes |
| --- | --- |
| ✅ `GET /symphonies/{symphony-id}/score` | full logic-tree JSON ("EDN") of a saved **or public** symphony |
| ✅ `GET /symphonies/{symphony-id}/versions` | version history (`version_id`, `created_at`) |
| `GET /symphonies/{symphony-id}/versions/{version-id}/score` | a specific version's tree |
| `POST /symphonies` | **create** — body `{name, asset_class, hashtag, symphony:{raw_value:<tree>}, color?, tags?, benchmarks?, share_with_everyone?}`; required: `name`, `asset_class`, `hashtag`, `symphony` |
| `PUT /symphonies/{symphony-id}` | **full update** (same body shape, all fields optional) |
| `PATCH /symphonies/{symphony-id}/versions/{version-id}/score/nodes` | **surgical node edit** — body `{updates:[{id:<node-uuid>, ...changed fields}]}`; only `id` required per update. Editable fields include `ticker`, `weight`, `comparator`, `lhs-fn/lhs-val/lhs-fn-params`, `rhs-*`, `window-days`, `select-fn/select-n`, `sort-by-*`, `step`, `is-else-condition?` |
| `POST /symphonies/{symphony-id}/copy` | copy (ours or public) into our account — the safe "edit a variant" path |
| `DELETE /symphonies/{symphony-id}` | delete a saved symphony (destructive to the *definition*, not to capital) |

**Logic-tree format** (same shape the MCP used; see
[`fixtures/rsi-rotation.raw.json`](fixtures/rsi-rotation.raw.json) for a real
example): nested nodes with `step` ∈ `root | group | wt-cash-equal |
wt-cash-specified | wt-inverse-vol | if | if-child | filter | asset`.
Indicator functions (for `lhs-fn`/`rhs-fn`/`sort-by-fn`/`fn`):
`relative-strength-index`, `moving-average-price`,
`exponential-moving-average-price`, `moving-average-return`, `current-price`,
`cumulative-return`, `max-drawdown`, `standard-deviation-price`,
`standard-deviation-return`, `percentage-price-oscillator(-signal)`,
`moving-average-convergence-divergence(-signal)`, `lower-bollinger`,
`upper-bollinger`. Windows live in `*-window-days` (older nodes) or
`*-fn-params: {window: N}` (newer nodes). `rebalance` ∈
`none | daily | weekly | monthly | quarterly | yearly` (+
`rebalance-corridor-width` for threshold rebalancing).

## 3. Backtesting (goal: *validate before saving/deploying*)

| Route | Notes |
| --- | --- |
| ✅ `POST /symphonies/{symphony-id}/backtest` | backtest a saved/public symphony by id |
| `POST /backtest` | backtest an **ad-hoc tree** without saving — body additionally takes `symphony:{raw_value:<tree>}` |

Body (both): required `capital`, `apply_reg_fee`, `apply_taf_fee`,
`slippage_percent` (fraction: `0.01` = 1%), `broker` (default
`ALPACA_WHITE_LABEL`); optional `backtest_version:"v2"`, `start_date`,
`end_date`, `apply_cat_fee`, `apply_subscription`, `spread_markup`,
`benchmark_symphonies`, `benchmark_tickers`, `abbreviate_days`.
Baseline params we use: `{"capital":10000,"apply_reg_fee":true,
"apply_taf_fee":true,"slippage_percent":0.0005,"broker":"ALPACA_WHITE_LABEL",
"backtest_version":"v2"}`. Response: `stats` (CAGR = `annualized_rate_of_return`,
`sharpe_ratio`, `max_drawdown`, `cumulative_return`, sortino/calmar/win-rate…),
`dvm_capital` (equity curve), `data_warnings` (ticker inception clamps),
`first_day`/`last_market_day` (days since 1970-01-01).

## 4. Discover community symphonies (goal: *search all of Composer*)

✅ `POST /search/symphonies` — searches **publicly shared** symphonies.
Body: `{"offset": <int>, "where": [...], "order_by": [["field","asc|desc"], ...]}`
— returns 5 rows per page; paginate with `offset`.

Verified grammar (learned by probing — the spec leaves `where` untyped):
- Single clause: `["<op>", "<field>", <value>]` with ops `>`, `<`, `>=`, `<=`, `=` …
- **Multiple clauses must nest under `["and", clause, clause, ...]`** —
  sibling triples cause a Postgres error, and `like` on text fields is
  rejected (`Unsupported WHERE field`): only the numeric stat fields below
  are filterable. No free-text search on this endpoint.
- Example (top out-of-sample Sharpe with ≥2y of live-ish data):

```json
{"offset": 0,
 "where": [["and", [">","oos_sharpe_ratio",1.0], [">","oos_num_backtest_days",504]]],
 "order_by": [["oos_sharpe_ratio","desc"]]}
```

Each row includes `symphony_sid` (feed it to `GET /symphonies/{sid}/score`,
`POST /symphonies/{sid}/backtest`, or `POST /symphonies/{sid}/copy`), `name`,
`description`, node-count fields (`num_node_*`), and **out-of-sample** stats
(computed on data *after* the symphony was created — far more honest than
in-sample backtests): `oos_sharpe_ratio`, `oos_annualized_rate_of_return`,
`oos_max_drawdown`, `oos_calmar_ratio`, `oos_sortino_ratio`,
`oos_cumulative_return`, `oos_num_backtest_days`, `oos_win_rate`,
`oos_spy_alpha`, `oos_spy_beta`, `oos_spy_pearson_r`, `oos_standard_deviation`,
`oos_tail_ratio`, `oos_annualized_turnover`, and SPY benchmarks (`oos_spy_*`).

## 5. Capital movement — ⚠️ GUARDED (goal: *transfer between symphonies*)

These move real money. **Policy:** only via `scripts/composer-api.py`, only
when the human explicitly requests that specific move in-session, always after
a dry-run preview. See README §2 for the full safety contract.

| Route | Notes |
| --- | --- |
| `POST /deploy/accounts/{acct}/symphonies/{sym}/invest` | body `{"amount": <dollars>}` |
| `POST /deploy/accounts/{acct}/symphonies/{sym}/withdraw` | body `{"amount": <dollars>}` |
| `POST /deploy/accounts/{acct}/symphonies/{sym}/go-to-cash` | sell all to cash; cancels queued deploys |
| `POST /deploy/accounts/{acct}/symphonies/{sym}/rebalance` | rebalance NOW |
| `POST /deploy/accounts/{acct}/symphonies/{sym}/liquidate` | liquidate entirely; cancels queued deploys |
| `POST /deploy/accounts/{acct}/symphonies/{sym}/skip-automated-rebalance` | skip next auto-rebalance |
| ✅ `GET /deploy/market-hours` | is the market open / next session |
| `POST /dry-run` | simulate rebalances (no orders) |
| `POST /dry-run/trade-preview/{symphony-id}` | body `{"amount", "broker_account_uuid"}` — preview the trades a deploy would make |

**"Transfer between symphonies" recipe** (no atomic transfer endpoint exists):
1. `GET /portfolio/accounts/{acct}/symphony-stats-meta` — confirm source value/cash.
2. `POST /dry-run/trade-preview/{source}` with negative intent → preview withdraw.
3. `POST .../withdraw {"amount": X}` on the source symphony.
4. Wait for the deploy to execute + settle (poll `symphony-stats-meta`; deploys
   queue for the next rebalance window — check `GET /deploy/market-hours`).
5. `POST .../invest {"amount": X}` on the destination symphony.

Cash from a withdraw is not instantly investable — brokerage settlement
applies. Treat a transfer as a 2-step operation across up to 2 trading days.

## 6. Market data & trading (bonus surface)

| Route | Notes |
| --- | --- |
| `GET /api/v1/market-data/options/chain` · `/contract` · `/overview` | options data (note `v1` prefix) |
| `GET /trading/accounts/{account-id}/order-requests` | list direct orders |
| `POST /trading/accounts/{account-id}/order-requests` | ⚠️ place a direct single-asset order — capital-moving, same policy as §5 |

---

## Mapping: old MCP tool → REST route

| MCP tool (deny/allow list) | REST equivalent |
| --- | --- |
| `list_brokerage_accounts` | `GET /accounts/list` |
| `get_all_symphony_stats` | `GET /portfolio/accounts/{a}/symphony-stats-meta` |
| `get_saved_symphony` | `GET /symphonies/{s}/score` |
| `search_symphonies` | `POST /search/symphonies` |
| `create_symphony` / `save_symphony` | `POST /symphonies` |
| `update_saved_symphony` / `update_symphony` | `PUT /symphonies/{s}` or `PATCH …/score/nodes` |
| `copy_symphony` | `POST /symphonies/{s}/copy` |
| `backtest_symphony(_by_id)` | `POST /backtest` / `POST /symphonies/{s}/backtest` |
| `invest_in_symphony` ⚠️ | `POST /deploy/…/invest` |
| `withdraw_from_symphony` ⚠️ | `POST /deploy/…/withdraw` |
| `liquidate_symphony` ⚠️ | `POST /deploy/…/liquidate` |
| `go_to_cash_for_symphony` ⚠️ | `POST /deploy/…/go-to-cash` |
| `rebalance_symphony_now` ⚠️ | `POST /deploy/…/rebalance` |
| `skip_automated_rebalance_for_symphony` ⚠️ | `POST /deploy/…/skip-automated-rebalance` |
| `execute_single_trade` ⚠️ | `POST /trading/accounts/{a}/order-requests` |
| `cancel_invest_or_withdraw` ⚠️ | no direct route found in the public spec (go-to-cash/liquidate note they cancel queued deploys) |
