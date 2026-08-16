# EXISTING_SYSTEMS_AUDIT.md — Optic systems vs the PAT rubric

**Date:** 2026-08-16 · **Auditor:** agent-infra (this repo, branch `claude/optic-agent-architecture-v1p6h0`)
**Rubric:** PAT's five requirements + three architecture lessons (`PAT_LESSONS.md` A4, A7, A9, A11):
①search all data ②use all tools ③diagnosable ④knows our context ⑤continual learning
⑥correctness-in-architecture ⑦write-back/compounding ⑧teach loop.
**Ground rule:** in-repo systems were inspected file-by-file; outside systems are
inventory-only — **no changes to outside systems until Casey approves this audit.**

---

## 1. Inventory — inside this monorepo (all inspected)

| System | What it is | Deployed |
|---|---|---|
| genomics-alpha-tracker | Genomics sector scoring + paper calls + chat analyst | Render, serves research.optic.capital (login gate; proxies canary/barbell/btc) |
| treasury-canary | Treasury market health monitor, composite + MC simulators + Telegram analyst | Render (persistent disk after 2026-07 NO DATA incident) |
| barbell-lab | Quant research platform: ingest → backtest → edge monitors → nightly gates | Render, /portfolio-optimizer |
| btc-paper-engine | BTC pullback paper trader, 3 virtual books, replay-verified | Render, /btc |
| btc-executor | S5 live executor (Coinbase perps), mirrors paper engine | Render; DRY_RUN dashboard-owned |
| ibkr-executor | IBKR executor (El Niño options ladder), OFFLINE→paper→live | Render (standard plan) |
| edge-monitor | Edge-decay/risk-regime stats library (PSR/CUSUM/BOCD/DD) | Library; adapters not yet built |
| composer/ | Composer symphony workspace (REST API, guarded capital CLI) | Local scripts; MCP endpoint dead since 2026-07-05 |
| venture-deal-analyzer | Deal factpacks/memos/verification + rubrics + EV models | Repo-native (docs + models) |
| elnino-lab, ewm | Research studies (El Niño thesis; exit-window monitor spec) | Feed ibkr nino ladder / canary ewm module |
| uranium dashboards (root HTML) | Static sector + thesis-deployment pages | GitHub Pages; data frozen at 2024-05-04 |

## 2. Inventory — outside systems (inventory-only, pending audit approval)

| System | Known facts | Blockers / asks |
|---|---|---|
| Vibe-Trading server | 45.55.55.27:8080; Portfolio B.5; 7 Plotly chart tools | Need read access + tool list to audit. No changes until approved. |
| Crypto OHLCV via Coinbase | Feeds outside agents; in-repo parallel: `barbell/edge/adapter_coinbase.py`, btc engine uses Bitstamp | Confirm which systems consume it and rate limits/keys involved |
| ddgs search tool | Keyless DuckDuckGo search | Fine as-is (keyless, subscription-free) — matches cost policy |
| ClaimeAI | **Location unknown** | MISSING KEY INPUT: cannot audit or wire CI/CD until located. Casey: where does ClaimeAI live (host/repo/runtime)? |
| Custom 5-component AI investment system | Referenced in prior chats; not in this repo | Need component list + owners to audit. Ask before any mapping. |

---

## 3. Per-system audit (in-repo)

Legend: ✅ has it · 🟡 partial · ❌ missing. Numbers reference the 8-point rubric above.

### 3.1 genomics-alpha-tracker — **REUSE; closest thing we have to PAT**
- **Owner:** Casey · **Inputs:** FMP/Polygon/Tiingo/yfinance prices+fundamentals, Tiingo news, insiders, short interest, social · **Outputs:** scores, flags, paper calls + postmortems, chat answers · **Data:** SQLite on Render disk + cache
- **Tools:** scoring engine (`scoring/engine.py`, YAML weights), call rules, chat agent (`chat/agent.py`, Anthropic/OpenRouter)
- **Evals:** `evals/replay.py`, `scripts/backtest_calls.py`/`backtest_signals.py`, ~20 gate-test files, **`scripts/tune_proposal.py` — IC gate + Wilson promotion gate, "may only open a PR on exit 0"** — this is a real teach loop (⑧✅ for scoring weights)
- **Rubric:** ①🟡 (searches only its own DB) ②✅ ③🟡 (logs, no persisted agent traces) ④✅ (`knowledge/` dir: clinical base rates, FDA catalyst stats — codified-knowledge moat in miniature) ⑤🟡 (tuning gates yes; chat never learns) ⑥✅ (gates) ⑦🟡 (calls/postmortems persist; chat answers vanish) ⑧🟡
- **Failure modes:** provider rate limits (mitigated by FMP-on-cloud choice); chat quality unmeasured — **no benchmark exists for the chat analyst**
- **Verdict:** the template. Its tune-gate + knowledge-dir + postmortem trio is the pattern to replicate everywhere.

### 3.2 treasury-canary — **REUSE**
- **Owner:** Casey · **Inputs:** FRED, Treasury auctions, OFR, CFTC, Deribit, FINRA/Schwab margin, Tiingo news, Yahoo · **Outputs:** composite + severity, pins, EWM exit-window state, Telegram alerts + two-way chat · **Data:** SQLite on persistent disk
- **Evals:** ~25 test files (wiring, scoring, recession model, EWM gates/live coupling); `backtest.py`, event/impact studies, vintage checks; hindcast studies in `studies/`
- **Rubric:** ①🟡 ②✅ ③🟡 ④🟡 (methodology in md docs, not wired into chat context systematically) ⑤❌ ⑥✅ ⑦🟡 (metrics persist; study outputs live as md/JSON, not queryable series) ⑧❌ (misses become SPEC_AMENDMENTS.md by hand — a manual teach loop with no regression reproduction)
- **Failure modes:** the 2026-07 ephemeral-disk wipe (fixed; lesson encoded in render.yaml comments — good written-down-rule practice); Telegram chat quality unmeasured
- **Verdict:** reuse; wire studies' outputs to write-back and give the Telegram analyst a benchmark file.

### 3.3 barbell-lab — **REUSE; best validation architecture**
- **Owner:** Casey · **Inputs:** FMP/FRED/Tiingo/Yahoo multi-provider (cross-validation by design), Coinbase edge adapter, btc-executor `/status` (EXEC_TOKEN, "BLIND, never crashes") · **Outputs:** portfolio books, optimizer runs, regime/rebalance monitors, nightly reports · **Data:** SQLite + parquet on disk
- **Evals:** nightly ingest → validation → **acceptance gates** → monitors; `research/barbell_timer/` is the model study: SPEC → SIGNALS/RULES → VALIDATION_REPORT → QA_APPENDIX → **VERDICT.md**, with `fixtures/PROVENANCE.md` cached inputs (PAT A8 pattern, already ours)
- **Rubric:** ①🟡 ②✅ ③🟡 ④🟡 ⑤❌ ⑥✅ ⑦🟡 (results JSONs are frozen but not queryable by other services) ⑧❌
- **Verdict:** reuse. Its fixtures+provenance cache and gate cascade become the shared study-runner standard.

### 3.4 btc-paper-engine / btc-executor / ibkr-executor — **REUSE; out of research-agent scope by law**
- **Owner:** Casey · These are the "how we trade" layer PAT explicitly excludes ([04:22]). Separation of powers already enforced: engine keyless; executors hold the only credentials; DRY_RUN defaults; staircase ramp; `sync:false` doctrine after the 2026-08-10 silent-unarm incident (written down in render.yaml — codified-knowledge practice at its best).
- **Evals:** replay verification vs research backtest, restart-resume tests, executor gate tests, paper→live rehearsal gates
- **Rubric relevance:** ⑥✅ exemplary. Research agents get **read-only** engine state (the EXEC_TOKEN status feed) and nothing else. Add a standing **permission-leak test**: any research/chat process attempting executor credentials or order endpoints must fail closed.
- **Verdict:** reuse untouched. The lesson flows FROM these systems TO the agent layer, not the reverse.

### 3.5 edge-monitor — **BUILD-OUT (finish adapters); it is our referee organ**
- Stats library complete + 13 honesty-gate tests (null calibration, power, BOCD blindness, no-lookahead); `REFEREE.md` = counter-agent verdict pattern. Missing: `db.py`, coinbase/composer/shadow adapters, state machine wiring (signatures frozen in BLUEPRINT §7 — plan-locked, PAT A5/A6 ready).
- **Verdict:** highest-leverage unfinished build. It is the "agents reading the traces and checking every calculation" ([05:55]) role for our live strategies.

### 3.6 composer/ — **REUSE with guard intact**
- Guarded capital CLI (explicit human request + dry-run preview only), POLICY/RUNBOOK docs, regime research. MCP endpoint dead → REST. Rubric: ⑥✅ (guards in code) ⑦🟡 ⑧❌.
- **Verdict:** reuse; fold its account/rebalance digests into the same write-back store.

### 3.7 venture-deal-analyzer — **REUSE; our teach-loop prototype for research**
- factpack → memo → **verification.md** per deal; `templates/rubric-review-v1.md` = the counter-agent pattern CLAUDE.md canonized; hurdle-ledger v1.0 just landed with verification-corrections cycle. The Quaise-SPV miss became a standing CLAUDE.md rule — a manual PAT teach loop ([15:45]) without the benchmark-reproduction step.
- **Rubric:** ③✅ (verification docs are traces) ④✅ ⑤🟡 ⑧🟡 — missing only: misses re-encoded as *executable* regression checks.
- **Verdict:** reuse; add "reproduce the miss as a check before the fix" to the pipeline.

### 3.8 Root uranium dashboards (index.html, thesis-deployment.html, methodology.html) — **STOP / QUARANTINE**
- Static HTML, embedded JSON frozen at **2024-05-04**, conviction scores "updated daily (manual tracking)" — i.e., not updated; DEPLOYMENT_SUMMARY's "validation" table has no reproducible basis (no code, no data lineage in repo).
- **Rubric:** fails ①③⑤⑥⑦⑧; violates the honesty rules (unfrozen provenance, in-sample claims presented as validated).
- **Verdict:** STOP presenting as live analysis. Either mark "ARCHIVED — snapshot 2024-05-04" on the pages, or rebuild uranium as a proper service (ingest → gates → panels) later. Do not cite its numbers anywhere.

---

## 4. Cross-cutting gaps (what PAT has and we don't — anywhere)

| Gap | PAT lesson | Today at Optic |
|---|---|---|
| G1. **No shared series store.** 5+ SQLite islands; studies emit dead JSON/md. Nothing compounds across services. | A9 write-back [14:14] | Highest-leverage single build. One store (start: one SQLite/Postgres, `series` + `provenance` tables) that every service and study can read/write. |
| G2. **No agent benchmarks.** 3 chat analysts + study agents, zero benchmark files, determinism never measured. | A2 [24:40], A7 (95% determinism) [22:33] | Every narrow workflow gets a benchmark file + rerun-determinism metric before further investment. |
| G3. **No persisted agent traces.** Chat answers and study runs leave no diagnosable record an agent could re-check. | A4-③ [05:55] | Log prompt, tools, data touched, output per run into G1's store. |
| G4. **Teach loop is manual.** Misses become md amendments/CLAUDE.md rules — good! — but are never reproduced as executable regressions. | A11 [15:45] | Genomics tune-gate is the exception; generalize its "PR only on exit 0" shape. |
| G5. **Validation is per-service convention, not shared harness.** Gates exist (excellent) but every service reinvents runner/fixtures/caching. | A7/A8 [22:33–24:08] | Extract barbell's fixtures+PROVENANCE pattern into one study-runner. |
| G6. **Context is codified but not loaded.** knowledge/, SPECs, honesty boxes exist; chat agents don't systematically consume them. | A1/A14 [01:10, 19:21] | Wire per-service knowledge dirs into their own chat analysts as step-by-step workflow guides. |

## 5. Recommendations (every one mapped to benchmark + owner)

Priority order; all confined to existing infra per Casey's steer. No new external spend.

| # | Recommendation | Benchmark that proves it | Owner |
|---|---|---|---|
| R1 | Stand up the **Optic series store** (one DB, `series`+`provenance`); first writers: canary composite history, barbell nightly results, btc book equity | % of study outputs written back (target: 100% of new studies); one cross-service query demo (e.g. canary severity vs btc book DD) | agent-infra builds; Casey approves schema |
| R2 | **Benchmark the three chat analysts** (genomics, canary Telegram, barbell): 10 frozen Q/A cases each from real usage, scored vs Casey's answer, rerun ×3 for determinism | accuracy vs human benchmark; determinism on rerun; latency; cost/run | agent-infra drafts cases; Casey grades gold answers |
| R3 | **Permission-leak test suite**: research/chat processes must fail closed on executor credentials, order endpoints, composer capital ops | permission-leak tests: 0 leaks, run in CI | agent-infra |
| R4 | **Finish edge-monitor adapters** (coinbase→executor_state first; signatures frozen) so live S5 gets automated referee checks | its own 13 gates + first daily-line over real executor data | agent-infra; Casey redeploys barbell/edge service |
| R5 | **Generalize the teach loop**: template = miss → executable regression case → fix context/harness → full suite green → PR. Apply first to venture-deal-analyzer and canary SPEC_AMENDMENTS backlog | # misses converted to regression cases; suite stays green | agent-infra; Casey supplies miss list |
| R6 | **Quarantine root uranium dashboards** (ARCHIVED banner + stop citing) | zero references to 2024-05-04 numbers in future memos | agent-infra (banner); Casey (decision to rebuild later) |
| R7 | **Shared study-runner** extracted from barbell fixtures/PROVENANCE pattern (cached inputs, hashed intermediates, forced final sensibility pass per A10) | rerun of an existing study is byte-identical & near-instant on 2nd run | agent-infra |

Deferred by Casey's instruction: research.optic agent/sub-agent build (OPTIC_AGENT_ARCHITECTURE.md, BENCHMARK_SUITE.md, IMPLEMENTATION_PLAN.md, AGENT_OPS_RUNBOOK.md) — R1–R3 are prerequisites for it anyway; outside-agent token programs.

---

## Counter-agent verdict (mandatory per CLAUDE.md)

- Reviewer: adversarial counter-agent, independent pass, 2026-08-16
- Scope: citation spot-checks vs transcript/frames; repo-claim spot-checks vs files;
  rubric-score challenges
- Verdict: **PENDING — filled after review runs; do not act on this audit until PASS**
