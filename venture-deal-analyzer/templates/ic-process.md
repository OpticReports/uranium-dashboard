# IC process v1.0 — what happens after a deal lands

Standing protocol, adopted 2026-08-21. Two deal-specific sessions, two
recurring cadences. Total per deal: ~70 minutes of Casey's time spread
over ~10 days, plus 20 min/month and 30 min/quarter for the book.

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

**Output:** fact-pack skeleton + a sealed prior.
**Not produced:** any opinion.

## S2 · THE CASE — T+3, ~30 min

Adversarial by construction. Nobody decides anything in this session.

1. **Sponsor case, argued at its strongest** — as the person raising
   would put it, steelmanned, not strawmanned.
2. **Kill case** — red team, arguing the deal is a zero.
3. Casey **chairs**: asks questions, does not rule.
4. Both sides state, explicitly: *what evidence would move me?* Written
   down. This is what makes S3 honest.
5. The UNKNOWN list becomes an **ASK list** and goes to the sponsor,
   dated.

**Output:** the ask list, and two falsifiable positions.
**Rule:** no verdict may be issued in S2, even if it seems obvious.

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

The loop that is currently missing entirely. For every open position:

- **Tripwire check.** Did any kill criterion fire?
- **Ask aging.** Any outstanding ask older than 60 days is escalated or
  closed as refused. *An ask unanswered for two months has been
  answered.*
- **Resolution check.** Any resolution date reached → score it, write
  the outcome into `ledger.csv`.
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

## What this deliberately does NOT do

- **No new analysis step.** The rubric, panel and counter-agent rules
  are unchanged; this wraps them in a schedule.
- **No approval gate.** Casey decides. The process constrains *when*
  and *against what evidence*, never *what*.
- **No retroactive re-scoring.** Old verdicts stand as logged.
