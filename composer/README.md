# Composer Symphony Workspace

Tooling for **creating, editing, and backtesting** Composer symphonies through the
official Composer MCP server. This workspace is deliberately *additive* to the
rest of the repo — nothing here touches the uranium-dashboard site.

> **The one rule that matters:** this project may create, edit, and backtest
> symphonies. It may **NEVER move capital.** Funding, investing, withdrawing,
> rebalancing, and liquidating are **manual human actions in the Composer UI
> only.** The deny-list below is the enforcement mechanism, not a suggestion.

---

## 1. MCP server

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

## 2. Safety contract (capital cannot move)

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
├── CHANGELOG.md     # every symphony mutation logged here (what/why/stats)
├── fixtures/        # symphony JSON snapshots + human-readable logic summaries
└── results/         # backtest / sweep outputs (baseline.json, sweeps, …)
```

## 4. Workflow

1. Pull a symphony's definition (read-only) → snapshot into `fixtures/`.
2. Backtest it → save stats into `results/`.
3. Propose a change → copy/create a variant, backtest, compare.
4. Record the mutation in `CHANGELOG.md` with before/after stats and the reason.
5. Save via `save_symphony` / `update_saved_symphony`.
6. **Funding stays manual.** Nothing here ever invests real money.
