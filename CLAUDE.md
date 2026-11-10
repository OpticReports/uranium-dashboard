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

SUCCINCTNESS (Casey, 2026-08-13): "cut to the meat." Results first, minimal
prose, tables/bullets over paragraphs. Keep the honesty caveats but compress
them to one line each. No restating context Casey already has.

EDGE IS THE POINT (Casey, 2026-11-05): "if you run into edge in any study,
that isn't directly the original prompt, still bring it to my attention.
Edge is important." Any study that surfaces a conditional return, a
mispricing or a tradeable asymmetry — even as a by-product, even if the
original question was answered "no" — reports it explicitly as a candidate
edge, with its sample size, the mirrored/placebo check, and what it would
take to use it. Origin: add. 53 found that "bad overnight -> better session"
after oversold closes and first reported it only as "don't exit".

ONE BRAIN, TWO BROKERS (Casey, 2026-11-10): the Composer symphonies also run
on IBKR as a mirror (composer/IBKR_MIRROR.md), with Composer as the editor.
"Every time a thesis or test or report is made and that item changes or
updates the trading methodologies or gates or symphonies ... [it] should also
be transferred over ... double checking that the composer side and the
interactive brokers side is performing the same way." Any change to a
symphony, a gate, a POLICY operation or the methodology lands on BOTH sides
in the same change set, and the parity check (per engine: Composer's holdings
vs the mirror's, and the day's returns) is run and reported before the change
counts as done. Until the mirror trades, the rule binds the approved fixtures
(composer/fixtures/approved), which are the mirror's source.

## Standing engineering conventions

- Agent-governed pattern for studies/builds: research or counter-agent pass
  -> build with merge-blocking gate tests -> honesty box with frozen
  backtest numbers -> commit/push -> note which service to redeploy.
- MISSING KEY INPUTS: ASK, DON'T ANALYZE AROUND THEM (Casey, 2026-08-09).
  If a decision hinges on an input we don't have, STOP and ask for it —
  never record it as UNKNOWN and publish a verdict conditioned on it.
  If a supplied document can't be opened/parsed (PDF, DocSend, gated
  link), say so explicitly in the reply and request it another way;
  never let an unread document become a silent gap. Before any memo
  ships, re-read every artifact the LP provided and diff it against the
  fact pack's UNKNOWN list. Origin: the Quaise SPV terms (valuation,
  class, fees) sat on page 1 of the Delta4 teaser while the dashboard
  said "waiting on valuation" for two revisions.
- Counter-agent verification is MANDATORY (Casey, 2026-08-09): every
  research pass, dataset, scoring instrument, and analytical artifact gets
  an adversarial counter-agent review BEFORE its findings are acted on,
  merged, or presented — data-integrity checks, citation/number
  spot-checks, QA of computations. Log the counter-agent's verdict
  alongside the work (deal analyzer: templates/rubric-review-v1.md is the
  pattern). Applies to the venture-deal-analyzer pipeline and all research
  dashboards alike.
- Honesty rules: state measurement basis (trade-close vs MTM), in-sample
  caveats, and what was NOT modeled. Never present in-sample CAGR as a
  forecast.
- Live trading separation of powers: strategy engines are ALWAYS keyless
  decision brains; credentials live only in executor services — btc-executor
  (trade-only Coinbase key) and ibkr-executor (IBKR connection; ALL
  automated IBKR trading routes through it). DRY_RUN defaults + staged
  rollout gates (EXECUTOR.md / ibkr-executor/README.md) are the law.
  Model IDs never appear in commits, PRs, or code comments.
