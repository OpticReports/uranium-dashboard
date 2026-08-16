# PAT_LESSONS.md — what Bridgewater's Pocket Analyst teaches Optic

**Provenance:** Bridgewater "Building Pat, the AI Pocket Analyst" (Interrupt 26),
https://www.youtube.com/watch?v=lXZb21CfeIY
Evidence on hand: `bridgewater_pat_transcript_cleaned.md` (Whisper large-v3, lightly
normalized — wording may contain ASR errors) + 20 slide frames
(`bridgewater_pat_frames.zip`, filenames = `MMSS_label_frame#.png`).
**Not on hand:** `bridgewater_pat_slide_frames.md`, `contact_sheet.jpg`, the 1080p mp4.
The raw frames are the primary evidence the missing files were derived from, so no
conclusion below depends on a missing input. Frame citations are given only where the
frame was actually inspected; otherwise citations are transcript timestamps only.

**Scope note (Casey, 2026-08-16):** applied first to *existing* Optic infra and trading
engines (see `EXISTING_SYSTEMS_AUDIT.md`). The research.optic agent/sub-agent build is
tabled; these lessons feed it later. Outside-agent token spend also tabled.

**Counter-agent review:** verdict logged at bottom (mandatory per CLAUDE.md).

---

## A. Directly reusable at Optic

| # | Principle | Evidence | What it means for Optic today |
|---|-----------|----------|-------------------------------|
| A1 | **Codified knowledge is the moat.** 50 years of written-down causal rules → machine+human readable expert system; "we didn't have to go back and write down every information. It was already there." | [01:10]–[02:46] | Our `knowledge/` dirs, SPEC/RULES/VERDICT docs, honesty boxes, and CLAUDE.md conventions ARE the moat. Treat every study's methodology doc as agent context, not prose. Keep writing rules down at trade/decision time, not retroactively. |
| A2 | **Narrow agents, benchmarked heavily — no generic agents.** "We take often very narrow workflows and then benchmark them very heavily. And then we hill climb those benchmarks." | [24:40]–[25:11] | Our chat analysts (genomics, canary Telegram, barbell) are currently generic Q&A. Convert each into named narrow workflows (e.g. "explain today's composite change") with a benchmark file per workflow. |
| A3 | **Agent scope = deep exploratory research, NOT how we trade.** "PAT is not about how we trade." | [04:22]–[04:52] | Matches our separation-of-powers law: keyless decision brains vs executor services. Research agents never touch btc-executor / ibkr-executor / composer capital ops. Already policy; make it a permission-leak test, not a convention. |
| A4 | **Five requirements:** search ALL data; use ALL analyst tools; fully **diagnosable** traces ("not just for humans, but also for agents… reading through the traces"); **knows our context**; **continual learning**. | [04:52]–[06:26]; frame `0501_requirements_0301.png` (pillars 1–5: SEARCH ALL DATA / USE ALL [TOOLS] / DIAGNOSABLE / KNOWS OUR CONTEXT / CONTINUAL LEARNING) | Use as the audit rubric for every existing system (done in EXISTING_SYSTEMS_AUDIT.md). Biggest current gaps: no unified data search across our per-service SQLite islands; no persisted agent traces. |
| A5 | **Plan-first: "the plan really is the analysis."** Clarifying questions taught via a context benchmark; plan enumerates every data frame, its schema, and how frames connect. | [12:09]–[13:10]; frame `1114_plan_0674.png` (step ladder: Demo Prompt → Dynamic Context → Unstructured Data Search → Structured Data Search → Constructing a Good Plan → Detailed Plan Generation, "Clarified 5 items") | We already do this informally (SPEC.md before build, frozen signatures in edge-monitor BLUEPRINT §7). Make it formal: every study starts with a plan artifact listing tables/schemas/joins; the plan is what gets reviewed, code is derived. |
| A6 | **Parallel codegen after plan lock.** Each sub-agent knows its input schemas + output schema, so a 20-task plan generates in ~the time of a 3-task plan; tasks "statistically compile" (two LLMs on the same task → mathematically equivalent code). | [13:10]–[13:42], [20:56]–[21:33]; frame `1249_parallel_codegen_0769.png` (task chips: Load Oil Data / Load Currency Data / Calc Asset Moves / Oil Price Chart / Asset Moves Table) | For our studies: schema-frozen task specs → fan out codegen → join. The frozen-signature pattern in `edge-monitor/BLUEPRINT.md` is exactly this; generalize it to study pipelines. |
| A7 | **Correctness enforced in architecture, not prompts.** Orchestration is ordinary Python control flow ("no agent orchestration"); static analysis derives the task DAG; validation agents run per-layer; "the agents cannot forget to validate. They are forced to validate." 95% output determinism on rerun. | [19:54]–[23:04]; frame `2237_validation_1357.png` (bullets: "Correctness is enforced in the agent's architecture", "95% output determinism in test suite", "Reproducible -> much higher accuracy"; Execute→Validate→Edit Code loop) | This is our merge-blocking gate-test pattern applied to agent output. Rule: any agent-produced number that reaches a dashboard or memo must pass through code-enforced validation (gates), never "the model checked itself in-prompt." Determinism-on-rerun becomes a measured metric. |
| A8 | **Run the code FOR the LLM.** Execution harness with static analysis + injected caching annotations → no double-execution; second-round tweaks are near-instant. | [23:38]–[24:40] | Our studies re-fetch and re-compute constantly. Standardize the fixtures-cache pattern (barbell_timer `fixtures/` + PROVENANCE.md) into a shared runner: cached inputs, hash-keyed intermediates, provenance recorded. |
| A9 | **Outputs write back into the same store as inputs.** "Any output from a Python analysis is indistinguishable from any of the human-uploaded series… any output can serve as an input to a subsequent one" → humans and agents compound each other's work. | [14:14]–[14:44]; frame `0933_security_0573.png` (landing page: "Write Analysis Outputs to → Personal_MichaelRan (TMA8841)") | Today our study outputs die as JSON fixtures + md files per service. Adopt a write-back convention: every study emits its result series into a queryable store with provenance, so the next study (or agent) can consume it. |
| A10 | **Self-review before returning.** "Just like you want your junior analysts to double-check their work" — inspect computed data + charts, diagnose, refine before the user sees it. | [14:14]–[15:15]; frame `1524_teach_0924.png` (step ladder includes Execution → Self Review → Interactive Report → The Flywheel) | Cheap to add to existing chat analysts and study scripts: a final sensibility pass (nulls, sign conventions, magnitude priors) that must pass before output ships. |
| A11 | **Explicit teach loop.** Miss → agent reproduces it as a benchmark ("this shows that we can reproduce this poor behavior") → iterate context/harness until benchmark passes → run full regression suite → reviewable change (their Slack/PR notice) → everyone gets the better agent. | [15:45]–[16:47]; frame `1524_teach_0924.png` | We already have the skeleton: genomics `evals/replay.py` (IC gate + Wilson promotion gate; "The tuner may only open a PR on exit 0"), surfaced via `scripts/tune_proposal.py`, is a teach loop for scoring weights. Generalize: every miss (bad call, bad answer, bad memo) becomes a regression case before the fix lands. The Quaise-valuation miss → CLAUDE.md rule is a manual instance of exactly this. |
| A12 | **Human-like inspection in data search.** Not just RAG/re-rank: check frequency, currency, and whether values match priors — took series-search accuracy "from roughly 15% … all the way to 90." | [11:37]–[12:09] | Any agent that picks a data series (FMP vs FRED vs Tiingo field) must validate units/frequency/magnitude against priors before use. Encode as a forced validation step (A7), not guidance. |
| A13 | **Chat/investment content separated from coding agent.** Investors aren't coders (paraphrase; ASR: "not broken by trade"); coding is a pure implementation detail (normalized from ASR "pure interpretation of detail"); separation gives cleaner context and specialization per agent. | [17:48]–[19:21] | Keep analyst-facing chat (Telegram canary, dashboard chat) free of implementation detail; route computation to a separate harness with its own context. Also the org lesson: Casey-facing conversation ≠ build session. |
| A14 | **Workflows over nebulous context.** "Instead we have step-by-step guides for the agent… it feels much more like a product. Dependable workflows." Users contribute context directly ("your user is better at writing context than you are"). | [19:21]–[20:24] | Convert our accumulated conventions into per-task step-by-step guides (skills), not one giant context blob. Casey edits them directly — his feedback IS the context repo (the CLAUDE.md sync rule already works this way). |
| A15 | **Small internal startup; investors + technologists + scientists side-by-side.** Multidisciplinary teams are "necessary if you're going to be building AI systems for expert users." Hundreds of expert users generate daily signal. | [06:57]–[08:31] | At Optic scale: Casey = investor+user, agents = technologists, counter-agents = scientists/rigor. The structural point: rigor must be a distinct role (referee/counter-agent), never the builder grading itself — already our mandatory counter-agent rule. |

## B. Reusable with adaptation (scale/context differences)

| # | PAT pattern | Adaptation for a 1-person family office |
|---|-------------|------------------------------------------|
| B1 | Per-user permissioned agent views — each person's PAT sees exactly what they can see ([09:34]–[10:34]; frame `0933_security_0573.png`) | We have one principal, but the boundary maps to **per-agent capability tiers**: research agents (keyless, read-only), monitor agents (read engine state via EXEC_TOKEN), executors (credentialed, human-gated). "Permission leak" test = research agent can never read executor credentials or move capital. Future: a second seat (analyst/partner) gets a scoped view. |
| B2 | Millions of unstructured docs, near-real-time ([10:34]–[11:06]) | We don't have broker-research firehoses; we have memos, factpacks, studies, specs, and subscription content. Small corpus → a simple indexed store beats RAG infrastructure. Prefer subscription/local sources (per standing rule) over per-token API calls. |
| B3 | Tens of billions of internal time series ([11:06]–[11:37]) | Ours is thousands of series across 5 SQLite islands. The lesson isn't scale, it's **one searchable namespace with provenance**. A single "Optic series store" (even one SQLite/Postgres with a `series` + `provenance` schema) delivers the compounding effect. |
| B4 | LangGraph for chat plumbing ([17:48]–[18:50]) | Transcript itself is ambivalent (ASR garbled, but plainly "we use it for system support… manage ourselves with much worse effects"). We don't need a framework; ordinary Python control flow (their own coding-agent choice, [20:24]) fits us better. |
| B5 | Interactive reports in their in-house charting library, send-to-tool ([14:44]–[15:15]) | Ours = Plotly + dashboard panels + HTML artifacts (standing visuals rule). The adaptation: reports should link data back to the store (A9), not embed dead JSON like the uranium dashboard does. |
| B6 | Background agents scanning all conversations for misses ([06:26]–[06:57], [15:15]–[15:45]) | Continuous background review is overkill for our volume; a **weekly review pass** over session logs + call postmortems (genomics `postmortem.py` already exists) achieves the flywheel at our scale. |

## C. Do not copy

- **Bridgewater proprietary content**: their frameworks, series names (e.g. internal
  "what we think in place will be 12 months out"), their numbers, their charting stack,
  team names. Lessons are structural only.
- **Their performance/accuracy claims as our baselines** (15%→90% search accuracy, 95%
  determinism, 4× codegen speed): motivating targets, not benchmarks. We measure our own.
- **Hundreds-of-users flywheel mechanics** (Slack-notified context PRs from user base):
  wrong shape for one principal; weekly review (B6) instead.
- **"Artificial investor" end-state framing** ([02:46]–[03:17]): their goal, not ours.
  Optic's end-state is Casey with compounding leverage, with capital actions always
  behind human gates (separation-of-powers law stands).

---

## Counter-agent verdict

Logged per CLAUDE.md mandatory-verification rule. See review at bottom of
`EXISTING_SYSTEMS_AUDIT.md` (single review covered both artifacts).

- Reviewer: adversarial counter-agent (independent subagent pass), 2026-08-16
- Checks: every timestamp citation opened against the transcript; frame-cited claims
  re-read against the frames (6 unique frames are cited in this doc); repo claims
  spot-checked against files.
- Verdict: **PASS-WITH-CORRECTIONS — all corrections applied in this revision.**
  Findings applied here: pre-filled verdict removed (HIGH); teach-loop gate code is
  `evals/replay.py`, not `tune_proposal.py` alone (MED); A13 quotes marked as
  normalized ASR (LOW); five citation ranges widened to the block containing the
  quote (LOW); frame count 19→20 (LOW). No citation pointed at materially wrong
  content; all direct quotes otherwise verified near-verbatim.
