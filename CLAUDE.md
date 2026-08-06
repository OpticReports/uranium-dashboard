# CLAUDE.md — working conventions for this repo

> SYNC RULE: this file is the CANONICAL copy. AGENTS.md and .cursorrules at
> the repo root are byte-for-byte mirrors (plus a provenance header) so
> Cursor/Composer and other AI tools load the same conventions. Whenever
> this file changes — including from Casey's feedback on the methodology —
> regenerate both mirrors IN THE SAME COMMIT:
>   `tail -n +2 CLAUDE.md | sed '1i # Working conventions for this repo (agent rules)'`
>   with the mirror header, written to AGENTS.md and copied to .cursorrules.

Monorepo of Casey's research dashboards (genomics-alpha-tracker,
treasury-canary, btc-paper-engine, btc-executor, barbell-lab), deployed on
Render via render.yaml. Commits go to main (autoDeploy); Casey redeploys
services manually when needed.

## Communication preference: visuals with every study (STANDING)

When presenting any trade optimization, backtest, simulation, or study
result — successful or not — accompany the succinct written summary with
**charts/visual simulations**, not just tables:

- equity curves (strategy vs benchmark, log scale for multi-year)
- drawdown profiles, before/after comparisons when a change was tested
- trade-level visuals where they illuminate (entries/exits on price,
  distribution of returns, worst-stretch windows)
- render as an image or HTML artifact/file sent alongside the summary;
  the dashboards' own panels count when they already show it
- keep the written summary tight; the visual carries the intuition.
  Formula renderings are lower priority than charts — prefer showing what
  the trades/equity DID over notation.

Rationale (Casey): "charts and visuals on top of succinct summaries help me
learn faster." Default to including a visual whenever a study produces a
time series, distribution, or comparison — ask only when a visual would be
genuinely meaningless.

## Standing engineering conventions

- Agent-governed pattern for studies/builds: research or counter-agent pass
  -> build with merge-blocking gate tests -> honesty box with frozen
  backtest numbers -> commit/push -> note which service to redeploy.
- Honesty rules: state measurement basis (trade-close vs MTM), in-sample
  caveats, and what was NOT modeled. Never present in-sample CAGR as a
  forecast.
- Live trading separation of powers: strategy engines are ALWAYS keyless
  decision brains; credentials live only in executor services — btc-executor
  (trade-only Coinbase key) and ibkr-executor (IBKR connection; ALL
  automated IBKR trading routes through it). DRY_RUN defaults + staged
  rollout gates (EXECUTOR.md / ibkr-executor/README.md) are the law.
  Model IDs never appear in commits, PRs, or code comments.
