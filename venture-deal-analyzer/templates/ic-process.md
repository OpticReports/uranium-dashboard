# IC process v1.2 — what happens after a deal lands

Standing protocol, adopted 2026-08-21. Rev 1.1 same day (S2 is a
dialogue; R1 is not investments-only). **Rev 1.2, 2026-08-25 (Casey):
S1 delivers the FULL analysis report at intake — no staged
withholding — every report carries a ranked PENDING DD QUESTIONS
section, and the flow is: full intake report → chase the missing data →
the dialogue (S2) → the decision (S3).**

## Why this shape

The front end of this pipeline is already heavy — fixed rubric,
5-scorer independent panel, red team, EV trees, mandatory counter-agent
verification. Adding more analysis at the top would buy little.

**The measured gap is the back end.** As of adoption: 5 deals logged,
**0 outcomes resolved**, and the nearest resolution date is 2026-12.
Every forecast in `ledger.csv` is write-only. The instrument makes
predictions and nothing ever scores them, which means it cannot yet be
known to work.

So: keep the sessions short, and put the weight on the loop that closes.

---

## S1 · INTAKE — same day: the FULL report

**Rev 1.2 (Casey, 2026-08-25): S1 produces the complete analysis at
intake, published to /deals the same day** — fact pack with provenance
tags, independent verification with counter-agent passes, panel scores,
red team, EV tree, exit odds. The same full treatment every prior deal
got, immediately. No staged withholding of analysis.

1. **(Optional, 30 seconds, before opening the report.)** Casey may
   text a blind prior — P(<1x), P(≥10x), one line — for the
   calibration record. Non-blocking: the report ships regardless.
   Recorded if given, skipped without ceremony if not.
2. Full pipeline runs at once: verification sweeps (team, corporate,
   traction, market stats, comps, technical), adversarial counter-agent
   on each, panel + red team scoring on the verified fact pack, EV and
   exit odds.
3. Every claim tagged VERIFIED / CLAIMED / CONFLICT / UNKNOWN; every
   document listed READ or NOT READ (never a silent gap).
4. **PENDING DD QUESTIONS — ranked.** See the standing section below.
5. Published to /deals same day: full card, canonical `dashboard.html`
   + mirror in the same commit.

**Output:** the complete intake report, live on /deals, with the ranked
DD list. **Scores at intake are stamped "rev 1 — pre-DD"**: they price
the deal as documented today and are re-run as DD answers land.

## THE GAP — between S1 and S2: chase the data

The ranked DD list goes to the sponsor/source the day the report ships.
Answers that arrive before S2 get folded in (report rev 2); the
DIALOGUE then argues the updated picture, not the stale one. Asks
still open at S2 become the cruxes' raw material; asks still open at
S3 are priced as non-response. 60-day expiry applies from the day the
list ships.

## STANDING: PENDING DD QUESTIONS — in EVERY report (Casey, 2026-08-25)

Every report this pipeline produces — intake reports, revisions, memos,
R1 diffs, R2 calibrations — carries a **PENDING DD QUESTIONS** section:
the open questions we need or want answered, **ranked by weight of
importance and priority**, not listed in discovery order.

Format per question:
| # | question | why it matters (what it moves) | priority | asked → status |

- **P1 — decision-gating:** the verdict or price cannot be settled
  without it. A P1 unanswered at decision time is priced as a negative
  signal, per the non-response rule.
- **P2 — score-moving:** would move a rubric dimension, a forecast, or
  an EV branch by a visible amount.
- **P3 — completeness:** worth having; would not change the decision
  alone.

Rules: ranked by expected decision impact; each question names what it
would move; statuses (asked / answered / refused / expired) are carried
forward report-to-report so the list is a living ledger, not a
rewritten one; the 60-day expiry clock runs per question from first
ask.

## S2 · THE CASE — T+3 (after the data chase), ~30 min

**A working session, not a presentation.** This is the one place in the
pipeline where the two of us actually argue the deal out. Everything
else in this repo is me producing artifacts and Casey reading them; S2
is deliberately the opposite. If it turns into me talking for 30
minutes, it has failed.

Run as rounds, roughly 5 minutes each:

1. **Bull, tight.** I put the sponsor's case at its strongest — the way
   the person raising would put it, steelmanned. Three minutes, not
   fifteen. Casey interrupts freely.
2. **Casey pushes on the bull case.** Real back-and-forth. I defend
   where I can and **concede out loud where I can't** — and every
   concession is written into `ic.md` at the moment it happens, so it
   cannot quietly un-concede itself by S3. Conceding is the point of
   the round, not a failure of it.
3. **Bear, tight.** Red team argues the deal is a zero.
4. **Casey pushes on the bear case too.** Both directions get
   steelmanned or neither does. A kill case that survives no pressure
   is not evidence of anything.
5. **Find the cruxes — together.** Not "here are the risks." The
   specific, small number of questions where we actually disagree, or
   where we agree we don't know, and where *evidence would settle it*.
   Usually two or three. This is the real output of the session.
6. **Both sides state what would move them**, in writing. Then the
   cruxes plus the UNKNOWN list become a dated **ASK list** to the
   sponsor.

**Output:** the cruxes, the concessions log, and the ask list.
**Rule:** no verdict may be issued in S2, even if it seems obvious.
**Failure mode to watch:** agreement arriving too early. If we agree
inside ten minutes, the deal has not been tested — swap sides and run
it again.

## S3 · THE DECISION — T+10, ~30 min

Only after the asks come back — **or don't.**

1. **Non-response is data.** An unanswered ask is logged with its age
   and priced as a negative signal, not as a pending item.
2. Panel scores independently → gates → EV tree → verdict.
3. **Pre-mortem:** "It is three years on and this is a zero. What
   happened?" Answered before committing, when honesty is cheapest.
4. **Kill criteria / tripwires written NOW** — the specific, observable
   events that would make us not follow on, or exit. Written at the
   moment of maximum objectivity, never invented later to justify a
   decision already made.
5. Forecasts + **resolution dates** → `ledger.csv`.
6. **Open the sealed prior, if one was given** (optional under rev
   1.2). Compare Casey's blind numbers to the panel's. Divergence is
   the interesting signal — record it, don't reconcile it.

**Output:** verdict, forecasts with dates, tripwires, pre-mortem.

---

## R1 · POSITION REVIEW — monthly, ~20 min

The loop that is currently missing entirely.

### NOT investments only — and this matters

R1 covers **every row in the ledger**, in three tracks. Restricting it
to money-in positions would quietly corrupt the whole exercise:

**A · HELD** — capital committed or called.
Full monthly attention: tripwires, capital calls, third-party marks,
follow-on decisions, concentration.

**B · LIVE** — in the pipeline; decision pending or asks outstanding.
Full monthly attention: ask aging, close dates, decision deadlines,
anything that changes the price or the terms.

**C · PASSED** — we declined, **but the forecast is still live.**
Light touch monthly (news / resolution dates only), full sweep
quarterly.

**Why C is not optional.** A pass IS a forecast. `quaise` sits in the
ledger with `p_below_1x = 0.64` logged against it; if Quaise goes on to
return 10x, that is a scored miss and one of the most instructive data
points this system will ever generate. Review only what you bought and
the calibration record becomes survivorship-biased and systematically
flattering — you would be grading your own homework with the failures
removed. **The expensive lessons live in the passes.**

Non-venture rows belong here too, with catalyst-based tripwires rather
than round-based ones — `argentina-gdp-warrants` resolves on an SDNY
ruling, not on a financing.

### The four checks

- **Tripwire check.** Did any kill criterion fire? (Tracks A and B.)
- **Ask aging.** Any outstanding ask older than 60 days is escalated or
  closed as refused. *An ask unanswered for two months has been
  answered.*
- **Resolution check.** Any resolution date reached → score it, write
  the outcome into `ledger.csv`. **All three tracks.**
- **Book check.** Concentration and correlation across positions — not
  just per-deal. (Live example at adoption: Bellwether is held twice,
  once via Series X and once direct, and is also the strongest
  competitor to Matter, which is in the pipeline.)

**Output is a DIFF, not a document.** If nothing changed, the entry is
one line saying so. This session must stay cheap or it will be skipped.

**Note for the first ~4 months:** no outcome resolves before 2026-12,
so early sessions score *process* — were asks answered, did tripwires
fire, did anything drift — not outcomes.

## R2 · CALIBRATION — quarterly, ~30 min

Where the ledger earns its keep.

- **Brier-score** every resolved forecast against its logged
  probability, and against the stage base rate as a benchmark. Beating
  the base rate is the bar; a forecast that merely sounds thoughtful is
  not evidence.
- **Casey's sealed priors vs the panel.** Which is better calibrated?
  Genuinely unknown, and worth knowing.
- **Is the rubric predicting anything?** Pairwise c-statistic once n
  allows. It does not yet.
- Rubric changes are proposed **only here**, versioned, and **never
  applied retroactively** — every ledger row is stamped with the
  version it was scored under.

---

## What this guards against

| Failure mode | The guard |
|---|---|
| Anchoring on the sponsor's framing | Sealed prior, recorded before exposure |
| Deal heat / deadline pressure | S2 and S3 separated by days; a close date inside the window is itself a flag |
| Confirmation drift | Red-team seat is structural, not discretionary |
| "Still waiting on docs" forever | Asks age and expire; non-response is priced |
| Inventing kill criteria after the fact | Tripwires written before money moves |
| Never learning | Quarterly scoring against base rates |
| Per-deal tunnel vision | Monthly book-level concentration check |
| Grading only the deals we bought | R1 covers passes too - a pass is a forecast |
| S2 becoming a monologue | S2 is run as rounds, with logged concessions |

## What this deliberately does NOT do

- **No new analysis step.** The rubric, panel and counter-agent rules
  are unchanged; this wraps them in a schedule.
- **No approval gate.** Casey decides. The process constrains *when*
  and *against what evidence*, never *what*.
- **No retroactive re-scoring.** Old verdicts stand as logged.
