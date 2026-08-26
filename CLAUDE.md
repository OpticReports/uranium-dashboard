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

## Model & token routing (STANDING, Casey 2026-08-26)

The main loop (Fable when so configured) is for: architecture, planning,
hard debugging, final review/synthesis, and anything ambiguous. Everything
else is delegated — set `model` EXPLICITLY on every Agent / Workflow agent
call instead of letting subagents inherit the main-loop model:

- **sonnet** — default for exploration and analysis: file/code search,
  exploration fan-outs (Explore agent type), codebase analysis and
  summarization, log scanning, data extraction, standard implementation
  from a clear spec, QA runs, doc updates. Do NOT use haiku for
  exploration: a subtly wrong exploration summary taken as given costs
  more than it saves — sonnet is the exploration floor.
- **opus** — complex implementation, tricky refactors, code-review
  passes, and the mandatory counter-agent verification passes.
- **omit model (inherit main loop)** — only for design decisions,
  adversarial verification of decision-critical findings, and synthesis
  across many agent results.

Effort: "low" for mechanical stages, session default for normal work,
"high"+ reserved for verify/judge/design stages. Ultracode/xhigh is
per-task opt-in (Casey says so explicitly), never a standing default.

Subagents return CONCLUSIONS with file:line references — never raw file
contents or dumps; state this in every subagent prompt. Verify a
load-bearing claim by reading the few cited lines, not by re-running the
search at main-loop rates.

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
- IC PROCESS runs on every deal (Casey, 2026-08-21; rev 1.2
  2026-08-25). Protocol: venture-deal-analyzer/templates/ic-process.md
  (v1.2); per-deal record into deals/<slug>/ic.md. Flow: **S1 intake
  same day = the FULL analysis report, published to /deals immediately**
  (fact pack, verification + counter-agents, panel, red team, EV, exit
  odds — stamped "rev 1, pre-DD"; blind prior optional and
  non-blocking), then CHASE THE DATA via the ranked DD list, then S2
  the case at T+3 (a DIALOGUE run in rounds, not a presentation;
  concessions logged live; output is the CRUXES), then S3 the decision
  at T+10 (pre-mortem, kill criteria written BEFORE money moves,
  forecasts dated into ledger.csv). Then the recurring half, which is
  the point: R1 monthly position review and R2 quarterly calibration,
  both scheduled as Routines. R1 covers EVERY ledger row in three
  tracks — HELD, LIVE and PASSED — because a pass is a forecast, and
  reviewing only what we bought makes the calibration record
  survivorship-biased. Asks unanswered for 60 days are closed as
  refused and priced as a negative signal.
- PENDING DD QUESTIONS in EVERY report (Casey, 2026-08-25): each
  report — intake, revision, memo, R1 diff, R2 calibration — carries a
  section listing the open questions we need/want answered, RANKED BY
  WEIGHT OF IMPORTANCE AND PRIORITY (P1 decision-gating / P2
  score-moving / P3 completeness), each naming what it would move, with
  asked/answered/refused/expired status carried forward as a living
  ledger. 60-day expiry per question from first ask.
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
