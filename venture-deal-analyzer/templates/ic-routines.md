# IC Routines — R1 and R2 scheduler payloads

The two recurring halves of the IC process (`ic-process.md` v1.1) run as
**Routines** — durable scheduled triggers that each fire a FRESH session.
Fresh, not bound to an existing conversation, so the prompts below are
deliberately self-contained: each firing starts from nothing.

Kept here so the schedule is version-controlled and reproducible rather
than living only in a scheduler UI.

**Status 2026-08-21: NOT YET CREATED.** `create_trigger` on the
claude-code-remote MCP server returned `requires approval` on three
attempts. Either grant that permission and ask Claude to retry, or
create both from `/routines` by pasting the payloads below.

**Do NOT substitute the in-session cron scheduler.** It is memory-only,
dies with the session, and auto-expires after 7 days — for a monthly
cadence it would appear scheduled and silently stop, which is worse
than having no schedule at all.

---

## Defaults chosen

| | value | why |
|---|---|---|
| Time | **15:00 UTC** (11am ET / 8am PT) | Timezone unknown; picked a both-coasts slot. |
| R1 cron | `0 15 1 * *` | 1st of every month. |
| R2 cron | `0 15 1 1,4,7,10 *` | 1st of Jan / Apr / Jul / Oct. Runs right after R1 that day — review positions, then calibrate. |
| Session mode | **new session per firing** | This session will be reclaimed; a durable cadence cannot depend on it. |

Cron is evaluated in **UTC and does not shift with DST**, so both drift
an hour later in local terms over the US winter. Adjust to `0 14 …` in
November if that matters.

---

## R1 · Monthly position review

- **Name:** `IC · R1 monthly position review`
- **Cron:** `0 15 1 * *`
- **New session on fire:** yes

```
Run the monthly IC position review (R1) for Casey's venture deal analyzer.

Repo: OpticReports/uranium-dashboard. Work on branch `claude/venture-deal-analyzer-wm043o` (create it from the default branch if it does not exist).

READ FIRST, in order:
1. `CLAUDE.md` — standing conventions. Two govern this session: MISSING KEY INPUTS → ASK, don't analyze around them; and counter-agent verification is MANDATORY before any finding is acted on or presented.
2. `venture-deal-analyzer/templates/ic-process.md` — the protocol. R1 is defined there. Follow it, don't improvise.
3. `venture-deal-analyzer/ledger.csv` — every row is in scope.
4. Each `venture-deal-analyzer/deals/<slug>/factpack.md` and, where present, `deals/<slug>/ic.md`.

SCOPE — every ledger row, in three tracks. This is NOT investments only:
- HELD (capital committed/called): tripwires, capital calls, third-party marks, follow-on decisions.
- LIVE (pipeline; decision pending or asks outstanding): ask aging, close dates, anything moving price or terms.
- PASSED (declined, forecast still live): news and resolution dates only. Passes stay in scope permanently — a pass IS a forecast, and reviewing only what was bought makes the calibration record survivorship-biased.
Non-venture rows are in scope with catalyst-based tripwires (argentina-gdp-warrants resolves on an SDNY ruling, not a financing).

THE FOUR CHECKS:
1. TRIPWIRE CHECK — did any kill criterion in any `ic.md` fire? (HELD and LIVE.)
2. ASK AGING — every open item in each factpack's "UNKNOWN — REQUIRED" list, reported with its age in days. Anything over 60 days is escalated or closed as REFUSED and priced as a negative signal. Say so plainly; never leave a stale ask sitting as "pending".
3. RESOLUTION CHECK — any `resolve_round_by` or `resolve_multiple_by` date reached? If so research the actual outcome and write it into `ledger.csv` (`outcome_next_round` / `outcome_multiple`). This is the loop the whole system exists for and it has never yet run.
4. BOOK CHECK — concentration and correlation ACROSS positions, not per-deal. Known live issue: Bellwether is held twice (via Series X Capital and directly) and is also the strongest competitor to Matter Intelligence.

Do fresh research where a check needs it — EDGAR, press, company sites. Verify anything material with an adversarial counter-agent before reporting it, per the standing rule.

OUTPUT — a DIFF, not a document. This session must stay cheap or it gets skipped. If nothing changed, say so in one line and stop. Where something DID change: append a dated entry to `venture-deal-analyzer/validation/r1-log.md` (create if absent), update the relevant factpack or ledger row, commit, and push to the branch. Do NOT open a pull request unless Casey asks.

Then report to Casey in chat: what changed, which asks are now overdue, anything that resolved, and any decision he needs to make. Lead with what is actionable. If nothing is actionable, say that in a sentence or two rather than padding.

Note: no forecast resolves before 2026-12, so until then check 3 is usually a no-op and this session mostly scores PROCESS — were asks answered, did tripwires fire, did anything drift.
```

---

## R2 · Quarterly calibration

- **Name:** `IC · R2 quarterly calibration`
- **Cron:** `0 15 1 1,4,7,10 *`
- **New session on fire:** yes

```
Run the quarterly IC calibration review (R2) for Casey's venture deal analyzer.

Repo: OpticReports/uranium-dashboard. Work on branch `claude/venture-deal-analyzer-wm043o` (create it from the default branch if it does not exist).

READ FIRST: `CLAUDE.md` (standing conventions — counter-agent verification is MANDATORY before any finding is presented), `venture-deal-analyzer/templates/ic-process.md` (R2 is defined there), `venture-deal-analyzer/ledger.csv`, `venture-deal-analyzer/models/calibration.json`, and `venture-deal-analyzer/validation/` (prior studies, including the measured stage base rates in series-a-buckets-2026-08-21.md and the realization rates in realization-rates-2026-08-20.md).

THE JOB — is this instrument predicting anything, or does it merely sound thoughtful?

1. BRIER SCORE every RESOLVED forecast in ledger.csv against its logged probability, AND against the measured stage base rate as the benchmark. Beating the base rate is the bar. A forecast that only sounds careful is not evidence. Report both numbers side by side; never report the Brier score alone, because without the benchmark it is uninterpretable.
2. SEALED PRIOR vs PANEL. For every deal whose `ic.md` has a sealed prior that has since been opened, compare Casey's blind numbers against the panel's scores. Which is better calibrated? Genuinely unknown and worth knowing. Report honestly even — especially — if the blind prior is winning.
3. IS THE RUBRIC PREDICTING ANYTHING? Compute the pairwise c-statistic of weighted_score against realized outcomes once n permits. If n is too small, say exactly that and state what n would be needed. Do not compute a statistic that the sample cannot support.
4. RUBRIC CHANGES are proposed ONLY in this session, are versioned, and are NEVER applied retroactively — every ledger row is stamped with the rubric version it was scored under. Propose; do not unilaterally apply.

HONESTY REQUIREMENTS: state measurement basis, sample size, and what was NOT modeled. If the honest answer is "too few resolutions to say anything yet", that IS the finding — write it plainly and stop. Do not manufacture signal from n=1. Run an adversarial counter-agent over any scoring computation before reporting it.

OUTPUT: write `venture-deal-analyzer/validation/calibration-<YYYY-MM>.md`, commit, push to the branch. Do NOT open a pull request unless Casey asks. Per the standing visuals rule, include a chart if there is a time series, distribution or comparison to show — a calibration plot or reliability diagram once n allows; if n does not allow it, say so rather than plotting noise.

Then report to Casey in chat: is the instrument working, what changed, and what (if anything) should change in the rubric.

Note: the first forecast does not resolve until 2026-12, so the 2026-10 firing will legitimately have nothing to score. In that case check that resolution dates and tripwires are still correctly recorded, say the calibration set is still empty, and stop — that is a complete and correct R2.
```

---

## Per-deal one-shots (S2, S3)

Not standing Routines. Created at S1 intake against that specific
deal's dates: **S2 at T+3, S3 at T+10**, both one-shot, both firing into
the session where the deal is being worked. If a close date compresses
the window, the compression itself is a flag worth logging in `ic.md` —
a deal that cannot survive ten days of process is telling you something.
