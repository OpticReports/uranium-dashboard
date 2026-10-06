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
3. **One human request = one operation** — with two standing exceptions
   pre-authorized by the owner on 2026-07-06 and codified in
   [`POLICY.md`](POLICY.md): the sleeve monetization band and the
   criterion-gated sleeve scale-up to 15%. Those execute without per-trade
   approval but are always reported and logged. Everything else: "move $X
   from A to B"-style instructions only, confirmed before executing.
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
    ├── composerlib.py       # shared helpers (auth, API calls, curve math)
    ├── composer-api.py      # general CLI (capital moves double-guarded)
    ├── monte-carlo.py       # bootstrap Monte Carlo on a backtest equity curve
    ├── sweep.py             # parameter sweep grid + walk-forward split
    ├── verify-community.py  # re-backtest public symphonies vs claimed stats
    ├── correlation.py       # correlation matrix + inverse-vol weights
    ├── divergence.py        # live vs backtest implementation shortfall
    ├── rebalance-digest.py  # market hours + dry-run + trade previews
    └── monitor.py           # snapshot + alerts (exit 2 = alert), cron-friendly
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

## 5. Analysis tools (all read-only)

All scripts live in `scripts/`, auth from the env vars, write JSON reports to
`results/`, and never touch the deploy/trading routes.

**`sweep.py` — parameter sweeps + walk-forward.** `--list-nodes` prints every
tweakable condition/filter/asset with its node id; each `--set
'node-id:field=v1,v2,…'` adds a dimension (cartesian product, baseline value
auto-included, in-memory only — nothing is saved to Composer). `--split
YYYY-MM-DD` reports in-sample vs out-of-sample separately so overfit settings
stand out. Grids land in `results/sweeps/`.

**`verify-community.py` — trust-but-verify search.** Pulls the top public
symphonies by OOS stats, re-backtests each over ~the same window with our
cost assumptions, and flags `SHARPE_NOT_REPRODUCED` / `DRAWDOWN_WORSE`.

**`correlation.py` — correlation & allocation report.** Live deposit-adjusted
curves for invested symphonies (default) or `--ids` backtest curves for any
symphonies. Correlation matrix, per-strategy stats, inverse-vol weights.
Report only — acting on it stays human-gated.

**`divergence.py` — implementation shortfall (distribution-aware, add. 38,
panel-revised 2026-10-05).** Live deposit-adjusted curve (a price path: it
drops by `w*D/P` on every ex-date) vs a fresh backtest (total return) over
the same dates. On each ex-date the distribution the backtest earned
(`w(t-1) x D/P_prev x (1+r_adj)`, Yahoo) is classified from the model's own
continuity against a per-fund pay lag L observed on the fund's OWN credit
in the add.-38 cash trail (`PAY_LAG`: ZVOL 1, PULS 2, BIL 3, TQQQ 4, SSO 4,
LABD 5, TMV 5 trading days — observed, not issuer documentation, never
inherited from an issuer family; a test finds each entry's event in the
fixtures): HELD_THROUGH (model holds the payer on ex..ex+L-1, so it is
re-credited inside the symphony at the ex+L open) stays in,
so the gap is not lenient by the pay-date recredits; LEAKED (model exited
before the credit — where live held the payer the cash was observed landing
in ACCOUNT unallocated cash and never reaching the live curve, 4/4
identified cases: ZVOL 08-19, BIL 08-03, TMV 09-22, SSO 2025-12-24; TNA
2026-06-23 was held live but its credit is masked by account flows) is
removed from the model. A payer with no observed lag (SOXL and TNA: held
live, credit not identified; QLD, UDOW, TECL, TLT, SQQQ, any new holding)
is never guessed: exited on the ex-date is LEAKED, held 5+ days HELD_THROUGH,
anything between AMBIGUOUS — kept in the model (strict, the lower gap), with
the lenient number in `*_ambiguous_lenient` and a loud CLI line to check the
account-cash residual before acting on a gate. A held row is "credit
pending" (CLI flag, `credit_pending`) while the window ends before model day
ex+L, the credit day: the gap still carries live's ex-date dip.
`--start YYYY-MM-DD` restricts the comparison window (POLICY Op2 reads the
sleeve with `--start 2026-08-01`): live and backtest are still fetched over
the full live window and sliced; the base is the last close BEFORE start, so
the first counted return is the first trading day >= start (Op2: base 07-31,
first return 08-03 — the 07-31 close holdings are already the edited
strategy). `n_trading_days` counts trading days on/after start (Op2's
">= 120": 08-03 = day 1) and equals `n_days`. A held-through payer whose
ex-date return is before the window but whose credit lands inside it biases
the gap UP; it is flagged, not modeled (`pre_window_credit_rows`, bound and
offset keys, a `!!` CLI line; HARV/KMLM from 08-01: PULS 07-31, +2.0 /
+0.5 %/yr; SLEEVE: none). A non-ISO `--start` is an error.
Corr/beta/vol-ratio are computed on live-plus-income vs model
total return so a fat payout (ZVOL, 6%/month) is neither a tracking failure
nor a manufactured shared outlier. The old total-return-basis numbers stay
under `*_total_return_basis` keys; `annualized_gap_all_exdates_stripped`
shows the (lenient) every-ex-date-stripped number and
`held_through_credit_bias_annualized` the bias it carries; the per-ex-date
ledger lists each term, its treatment and the MODEL's $ entitlement (live's
own only where live matched the model that morning — model-only rows such
as KMLM TLT 09-01 and three pre-edit HG rows read in live's favour). If
Yahoo is unreachable for a held ticker, returns no adjclose series (never a
price-only fall-back), or a model weight
is keyed off the backtest calendar, the result is flagged
`distribution_data: INCOMPLETE` and `monitor.py` treats it as "diagnostic
unavailable" — never a silent fall-back. Not modeled: pay dates themselves,
per-symphony live share counts, intraday fill timing. Pure math lives in
`analyze_series()` (63 gate tests incl. broken-input counterparts, a
model-reproduction gate at <1 bps, the mocked `analyze()` I/O path and the
Yahoo wire-format parser:
`python3 -m unittest composer.scripts.tests.test_divergence`); `--all`
covers every invested symphony. The add.-38 chart
(`results/divergence-distribution-fix-2026-10-05.html`) is rebuilt from the
fixtures alone by `python3 composer/research/divergence/make_fix_chart.py`,
which refuses to write if its numbers differ from the results JSONs.

**`rebalance-digest.py` — what would trade today.** Market hours, per-symphony
rebalance flags (`may_rebalance_today`, queued deploys, current holdings),
Composer's `/dry-run` simulation, and (with `--previews`, during market
hours) per-symphony trade previews.

**`monitor.py` — scheduled monitoring.** Snapshots per-symphony state to
`results/monitor/` (git-ignored), compares to the previous run, and alerts on
drawdown from tracked peak (`--dd-alert`), large moves (`--move-alert`),
holding rotations, and queued deploys. Exit code 2 when alerts fire, so a
scheduled session/cron can decide whether to notify.
