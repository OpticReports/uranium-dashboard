# variant-lab

Keyless crowding-hazard and forced-flow instrument. Reads positioning, mechanical
cohort commitments and official-actor events; emits dated hazard forecasts, an
exposure multiplier and a watchlist. **Moves no capital in v1 and holds no
credentials**, per the separation-of-powers law in `CLAUDE.md`.

Docs: [`EVIDENCE.md`](EVIDENCE.md) (what the research established), [`RULINGS.md`](RULINGS.md)
(the arbitrated contradictions, binding), [`PROBES.md`](PROBES.md) (verified data
capability), [`BLUEPRINT.md`](BLUEPRINT.md) (system design), [`PENDING.md`](PENDING.md)
(ranked open questions).

---

## What Casey asked for, and what survived

The ask was an agent swarm that finds crowded trades, takes the opposite side, and
builds Druckenmiller-style conviction on it.

**The inversion step does not survive.** Measured fresh on a 54,813 market-week panel
built for this project — 5 pre-registered trader definitions × 16 markets, CFTC
legacy/disaggregated/TFF joined to keyless continuous futures, 1995–2026 — fading a
positioning extreme is worth **+0.031% per 4 weeks (t = 0.38, block-bootstrap
p = 0.74)**, gross of costs. Following is the arithmetic mirror. Neither is an edge.
Worse, the sign is not a property of the market but a choice of definition: on the
same reports, same dates, same gate, fading asset managers returns **+0.391%
(t = +3.90)** while fading leveraged funds returns **−0.277% (t = −2.58)**, and both
keep their opposite signs across split halves. At |z| ≥ 2.0, **85.6% of extremes have
two or more definitions disagreeing about which way the crowd is leaning.** Whoever
names the crowd picks the sign.

Both men Casey named disavow the premise in their own words — Soros: *"I have become
a confirmed anti-contrarian"*; Druckenmiller: *"I don't care if a trade is crowded, if
I think the thesis is right and the trend is with me."*

**What replaces it: crowding tells you how much and how hedged, never which way.**
Direction comes only from a named forced-flow mechanism that publishes its own trigger
level — an index or roll rule, a margin or collateral trigger, a mandate or regulatory
constraint, a dealer balance-sheet date, or a mechanical cohort's published threshold.
The intuition Casey is chasing survives in exactly one form, and it is his own: buy
*after* the crowd is flushed, not while it builds (treasury-canary's `WASHED_OUT`,
p = 0.011, stable at 94%/95% across split halves).

**The Druckenmiller escalation survives intact**, because it was never about crowds.
The probe → confirm → pile ladder is preserved as a mechanically-gated sizing stack
with an escalation ceiling set by a drawdown budget rather than a size multiple.
What is deleted is the idea that the LLM layer supplies the conviction.

## What this is not

- **Not a trade finder.** It emits hazards, exposure multipliers and a watchlist.
- **Not a fader.** There is no code path from any positioning value to a direction field.
- **Not a conviction engine.** No LLM-emitted confidence, probability or conviction
  number may enter the sizing function by any route. Agent probabilities go to the
  ledger to be scored, and nowhere else.
- **Not a source of direction on carry.** Any position whose payoff is short
  optionality or a funding spread is barred from receiving a join, add or scale-up
  from any crowding, positioning, momentum or narrative input, at every percentile.

## The two findings that most change what gets built

**1. Casey is the crowd, measured.** All four live Composer symphonies fire inside the
public cohort's pile bands. 18 of his 24 distinct 10-day-RSI triggers (75%) sit inside
78–82 or 29–32, including the corpus's #1 and #2 modal tuples verbatim
(`RSI(TQQQ,10) > 79`, `RSI(TQQQ,10) < 30`). On the cohort's modal oversold day his
book's median SPY beta-notional is **+201% of book**; on the modal overbought day it is
**−190%**. The one validated signal in the whole evidence base is the signal his
existing book already expresses at 2× notional, in the same session, at the same level.

The book is **unconditionally diversified** (max pairwise symphony ρ = 0.28, 3.76
effective bets of 4) and **conditionally concentrated**. Today's snapshot reads −6% SPY
beta and sits at the 30th percentile of its own history — a risk model reading the
unconditional correlation matrix would understate real exposure by ~144 percentage
points of book and size a new thesis several times too large.

**2. Episode supply is fine; effect size is what is missing.** 47.3 distinct
(contract × side) episodes per year across the 29-contract universe, 35.3 effectively
independent after a measured design effect of 1.34, flat at 35–59/yr for 17 straight
years. But on 705–773 resolved observations, entering the extreme band makes the
adverse move *less* likely than a random date at every threshold and horizon
(0.88× at P(dd ≥ 40% / 24m), 0.96× at 20% / 12m). There is no effect of the assumed
sign to power a study for. And 35.3 < 50, so conviction sizing stays fully mechanical.

## Status

Design frozen, nothing built. The research is complete and adversarially verified;
the build is gated on the P1 questions in [`PENDING.md`](PENDING.md) — chiefly Casey's
risk capital and account permissions, whether the uranium sleeve is actually held
anywhere this session can see, and which of two readings of the no-trade gate applies
(they differ by 26× in how often the system is allowed to act).
