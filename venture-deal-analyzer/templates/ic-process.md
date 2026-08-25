# IC process v1.1 — what happens after a deal lands

Standing protocol, adopted 2026-08-21 (rev 1.1 same day, after Casey's
feedback: S2 is a dialogue, and R1 is not investments-only). Two
deal-specific sessions, two recurring cadences. Total per deal: ~70
minutes of Casey's time spread over ~10 days, plus 20 min/month and 30
min/quarter for the book.

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

## S1 · INTAKE — same day, ~10 min

Capture, **not** analysis. The point is to record the deal before
anyone has been persuaded by it.

1. **Seal a blind prior.** Before any research, any deck, any call:
   Casey writes P(<1x), P(≥10x), and a one-line thesis. Sealed into
   `deals/<slug>/ic.md` and not revisited until S3.
2. Log the ask, the instrument, the close date, and every hard deadline.
3. Start the **UNKNOWN — REQUIRED** list (standing rule: ask, don't
   analyze around).
4. List every document supplied, and every document named but not
   supplied. A document that cannot be opened is logged as NOT READ, in
   the reply, that day.
5. **Publish the intake card to the /deals dashboard, same day**
   (Casey, 2026-08-25: deals populate the page ON INTAKE, not at
   decision). The card carries captured facts and process state only —
   the ask, the divergences, the UNKNOWN list, the sealed-prior status,
   the S2/S3 dates. **No scores, no odds, no verdict** — those appear
   at S3. Canonical `dashboard.html` + mirror regenerated in the same
   commit, per the sync rule.

**Output:** fact-pack skeleton + a sealed prior + a live intake card.
**Not produced:** any opinion.

## S2 · THE CASE — T+3, ~30 min

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
6. **Open the sealed prior.** Compare Casey's blind numbers to the
   panel's. Divergence is the interesting signal — record it, don't
   reconcile it.

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
