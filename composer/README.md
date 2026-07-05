# Composer Symphony Workspace

Tooling for **creating, editing, backtesting, and managing** Composer
symphonies. This workspace is deliberately *additive* to the rest of the
repo — nothing here touches the uranium-dashboard site.

> **The one rule that matters:** the agent may create, edit, search, and
> backtest symphonies freely. It may move capital (invest / withdraw /
> transfer between symphonies) **only** when the human explicitly requests
> that *specific* operation in-session, only through the guarded CLI
> ([`scripts/composer-api.py`](scripts/composer-api.py)), and always after a
> dry-run trade preview. **Never autonomously, never as a side effect of an
> optimization.** The guards below are the enforcement mechanism, not a
> suggestion.

---

## 1. MCP server — ⚠️ offline; REST API in use instead

> **Status 2026-07-05:** the MCP endpoint `ai.composer.trade/mcp` 404s for the
> whole host and the public `invest-composer/composer-trade-mcp` GitHub repo
> is gone (Composer is now "Composer by SoFi"). The workspace now talks to the
> documented **REST API** at `https://api.composer.trade` — same credentials,
> same two headers. See [`API.md`](API.md) for the verified route map and
> [`scripts/composer-api.py`](scripts/composer-api.py) for the helper CLI.
> The MCP registration below is kept in case the endpoint returns.

The Composer MCP server is registered at **project scope** in
[`../.mcp.json`](../.mcp.json):

```json
{
  "mcpServers": {
    "composer": {
      "type": "http",
      "url": "https://ai.composer.trade/mcp",
      "headers": {
        "x-api-key-id": "${COMPOSER_API_KEY_ID}",
        "authorization": "Bearer ${COMPOSER_SECRET}"
      }
    }
  }
}
```

Authentication is by API key. The server expects two HTTP headers on every
request — `x-api-key-id: <key id>` and `authorization: Bearer <secret>`. Those
values are injected at runtime from environment variables, so **no credential is
ever written to a tracked file**:

| Env var                | Header it fills            |
| ---------------------- | -------------------------- |
| `COMPOSER_API_KEY_ID`  | `x-api-key-id`             |
| `COMPOSER_SECRET`      | `authorization: Bearer …`  |

### Providing the credentials

Get a key from the Composer app → **Accounts & Funding → Request an API key**
(you receive a Key ID and a Secret). Export them into the session environment:

```bash
export COMPOSER_API_KEY_ID=...
export COMPOSER_SECRET=...
```

`.env` is git-ignored (see [`../.gitignore`](../.gitignore)); a placeholder-only
[`../.env.example`](../.env.example) documents the shape. **Never** paste real
values into any file that gets committed, logged, or echoed.

---

## 2. Safety contract (capital moves are guarded)

### REST API (the active path)

The MCP deny list does **not** apply to raw HTTP calls, so the REST path has
its own guards:

1. **Route discipline.** The agent may freely call the read / build /
   backtest / search routes in [`API.md`](API.md) §1–4 and §6-read. It must
   **never** hand-roll a `curl`/HTTP call to the `deploy/…` or
   `trading/…order-requests` (POST) routes.
2. **Guarded CLI only.** Capital moves go through
   `scripts/composer-api.py invest|withdraw|transfer`, which refuse unless
   **both** `COMPOSER_ALLOW_CAPITAL=1` is set in the environment **and**
   `--yes` is passed — and they print a dry-run trade preview first.
   `COMPOSER_ALLOW_CAPITAL` is deliberately **not** set in the environment
   config; it is set inline, per command, only for an operation the human
   explicitly requested that session.
3. **One human request = one operation.** "Optimize my symphony" never
   implies moving money. Only "move $X from A to B"-style instructions do,
   and the agent should confirm amount/source/destination before executing.
4. **Transfers are not atomic.** A symphony-to-symphony transfer is
   withdraw → settle → invest across up to two trading days (deploys queue
   for the next rebalance window). Expect to babysit it.

### MCP deny list (kept for if/when the MCP returns)

Capital-moving tools are **hard-denied** in
[`../.claude/settings.json`](../.claude/settings.json). Claude Code evaluates the
deny list first — a denied tool is never callable, in this session or any future
one, regardless of prompt.

**Denied — capital-moving (never callable):**

- `invest_in_symphony`
- `withdraw_from_symphony`
- `liquidate_symphony`
- `go_to_cash_for_symphony`
- `rebalance_symphony_now`
- `skip_automated_rebalance_for_symphony`
- `execute_single_trade`
- `cancel_invest_or_withdraw`

**Allowed — build & analyze only:**

- `create_symphony`, `backtest_symphony`, `backtest_symphony_by_id`
- `search_symphonies`, `get_saved_symphony`, `save_symphony`
- `copy_symphony`, `update_saved_symphony`
- read-only account / performance tools: `list_brokerage_accounts`,
  `get_brokerage_account_holdings`, `get_portfolio_aggregate_stats`,
  `get_all_symphony_stats`, `get_symphony_daily_performance`,
  `get_portfolio_daily_performance`

Defense in depth: even if the live server exposes a capital tool under a name
not on the deny list, it is **not** on the allow list either, so it cannot
auto-run — it would require an explicit human approval. The deny list is the
belt; the allow-list-only posture is the suspenders. When the server is first
connected (Step D), reconcile the deny list against the live tool manifest and
add any capital-moving identifier that differs from the names above.

---

## 3. Layout

```
composer/
├── README.md        # this file
├── API.md           # verified REST route map (replaces the MCP tool list)
├── CHANGELOG.md     # every symphony mutation logged here (what/why/stats)
├── fixtures/        # symphony JSON snapshots + human-readable logic summaries
├── results/         # backtest / sweep outputs (baseline.json, sweeps, …)
└── scripts/
    ├── composer-api.py  # helper CLI (auth from env; capital moves double-guarded)
    └── monte-carlo.py   # bootstrap Monte Carlo on a backtest's equity curve
```

## 4. Workflows (mapped to goals)

**Prompt-to-edit a symphony**
1. `composer-api.py get <id>` → snapshot into `fixtures/`.
2. Edit the tree (or build a `patch-nodes` update list for surgical changes).
3. `composer-api.py backtest-def -f edited.json` → compare against
   `results/baseline.json`.
4. Apply via `update` (full) or `patch-nodes` (surgical); log in `CHANGELOG.md`
   with before/after stats.

**Create a custom symphony from a prompt**
1. Write the logic tree JSON (grammar in `API.md` §2; example in `fixtures/`).
2. `backtest-def` until it's worth keeping → `create -f tree.json --name …
   --hashtag …` → log it.

**Find the best community symphonies**
- `composer-api.py search --min-sharpe 1.5 --min-days 504 --order
  oos_calmar_ratio --pages 4` — out-of-sample stats only (post-creation data,
  resistant to backtest overfitting). Then `get <sid>` to inspect,
  `backtest <sid>` to verify, `copy <sid>` to adopt.

**Move money between symphonies** (explicit human request only — see §2)
- `composer-api.py preview <id> --amount X` any time (read-only dry run).
- `COMPOSER_ALLOW_CAPITAL=1 composer-api.py transfer --from A --to B
  --amount X --yes` — withdraw then invest; not atomic; check
  `market-hours` and re-check `symphony-stats` after each leg.

**Monte Carlo a strategy** (read-only)
- `monte-carlo.py --id <symphony-id> --sims 5000 --horizon 252 -o
  results/mc-<name>.json` (or `-f` a saved backtest JSON). IID + stationary
  block bootstrap of the backtest's daily returns → CAGR / max-drawdown
  percentiles, P(loss), P(DD>20/30/50%), VaR/CVaR. Caveat: assumes the
  sampled regime persists — it resamples backtest history, it does not
  re-run the strategy logic on synthetic prices.

## 5. Roadmap candidates (not built yet)

- **Parameter sweep harness** — clone a tree, vary thresholds/windows
  (`patch-nodes` or in-memory), `backtest-def` each variant, write a grid to
  `results/sweeps/`; walk-forward split via `start_date`/`end_date` to catch
  overfitting.
- **Community verifier** — paginate `search`, fetch each `symphony_sid`'s
  tree, re-backtest independently, flag stats that don't reproduce.
- **Correlation / allocation report** — per-symphony daily curves
  (`portfolio/accounts/…/symphonies/{id}`) → correlation matrix and
  risk-parity / vol-target weights across our symphonies (report only;
  any resulting transfer stays human-gated).
- **Live-vs-backtest divergence** — `symphony-historical-holdings` +
  `portfolio-history` vs backtest curve → implementation-shortfall tracking.
- **Rebalance preview digest** — `dry-run` before the trading window,
  summarizing tomorrow's likely trades per symphony.
- **Scheduled monitoring** — daily stats snapshot + drawdown alert via a
  scheduled session/trigger.
