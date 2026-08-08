# Investment memo — DexMat (Galvorn) SPV — rev 2

Run: 2026-08-08 (rev 2, full panel re-run after receipt of all four sponsor
documents) · Analyzer v1 · Sector overlay: materials/deep tech · Panel: 5
independent scorers + red team, fixed rubric v1. Rev 1 (public-source only)
retained in git history for the before/after record.

---

## Page 1 — synthesis

**Verdict: BORDERLINE PASS / WATCH — one verification call decides it.**
The documents materially improved traction (named customers, a $2M USAF
production-transition contract, one signed multi-year offtake) but the
price moved faster than the evidence: $45M post on a ~$800K–1M run rate
(~45–55x), a 55% step-up in three months, sold with a return model whose
"base case" is a $10B IPO and which contains no downside scenario at all.
The probability-weighted expected value at this entry is ≈2.5–3x net,
entirely tail-driven. **The flip trigger: confirm the signed multi-year
contract's counterparty and binding committed volumes (or an executed
Tokai Rika PO at ~$3M/yr). Binding + named → defensible tail bet.
Frame agreement / unnamed → pass.**

**Round (from documents):** $10M at $35M pre / $45M post ($15M interest;
oversubscribed case $50M post). Prior seed $6M at $23M pre/$29M post
closed ~Apr 2026, 2x oversubscribed. SPV: 2% one-time + 20% carry +
admin. $1M ⇒ 2.18% at close → ~1.27% at exit on the sponsor's own
dilution (50–70% dilution realistic ⇒ 10x net needs a $1.2–1.5B exit).

### Scorecard (5 independent scorers, median [IQR]) — rev 2 vs rev 1

| Dimension (weight) | Rev 1 | Rev 2 | IQR |
|---|---|---|---|
| Market & why-now (30) | 4 | **4** | 0 |
| Team (30) | 3 | **3** | 0 |
| Product & moat trajectory (15) | 3 | **3** | 1 (two scorers at 4) |
| Traction vs benchmarks (10) | 2 | **3** ↑ | 0 |
| Competition (10) | 3 | **3** | 0 |
| Deal & price (5) | 2 | **2** | 0 |
| **Weighted total** | 3.15 | **3.25** | |

### Probabilities (panel median vs base rate; red-team tree alongside)

| Event | Panel | Red team | Base rate |
|---|---|---|---|
| Raises next priced round ≤ 24 mo | 70% ↑ (was 40) | — | ~50–65% |
| Returns < 1x (net) | 60% ↓ (was 72) | 50% | ~65% |
| Returns 1–3x (net) | — | 25% | — |
| Returns 3–10x (net) | — | 15% | — |
| Returns ≥ 10x (net) | 4% | 10% | ~4% |

Panel–red-team disagreement on the tail (4% vs 10%) is the honest range;
both agree the EV is ~2–3x net and tail-driven.

### The sponsor model, autopsied

The Delta4 model's Base Case nets LPs **102x** ($10B IPO, yr 10); Bull
nets **1,091x** ($91.8B). Five compounding assumptions, no downside branch:

1. **Share ramp** 0.05% (2028) → **30% of global copper wire by 2040** —
   no advanced material has ever done anything like this (carbon fiber:
   50 years, never 30% of anything).
2. **"3x cheaper than copper by 2031"** — contradicted by the sponsor's
   own deck, whose roadmap reaches copper *parity* only at the 3kt plant
   in 2030–31.
3. **10x P/S at exit** — the sponsor's own comp set prices wire makers at
   1–2x; at 2x the "$10B base case" is ~$2B.
4. **0% option-pool refresh across 5 rounds** — realistic pools push
   dilution from the modeled 32–42% to 50–70%.
5. **Series A at $100M post within 1 year** of a $45M entry on ~$1M
   run rate.

The model's base case sits above the red team's 90th percentile.

### The aluminum ceiling (from the deck's own spec table)

Aluminum: specific conductivity 12,200 S·m²/kg — **2x Galvorn's 6,150 at
~1/100th the price**. Every bulk application where mass-per-conductance
is the buying criterion goes to Al/CCA (where incumbent lightweighting
dollars already flow). Galvorn's defensible ground: strength + flex +
high-frequency skin-effect + corrosion niches — aero signal cable
($1.9–2.9B), EMI ($7.4–9B), high-frequency DAC, defense cathodes,
medical. Success there ≈ a $1–3B-revenue company at maturity — a great
outcome that is still not "30% of copper wire."

### What the documents changed (honest ledger)

Better: named customers exist (AFRL $3.5M cumulative + $2M production
transition; Tokai Rika audited production, Q4 launch, $3M/yr PO in
negotiation; Safran testing; NeuroBionics $1M/yr PO in negotiation); one
multi-year offtake signed; capex far lighter than assumed (30t demo
$2–5M; 3kt ~$40M); beachhead cost parity today vs silver-plated aero
cable is credible; $30M non-dilutive; 2026 volume already = all of 2025.
Worse: price $45M post vs the ~$30M verbal; model quality (no downside
case) reflects on sponsor underwriting; candor pattern persists ("founded
3 years ago" in the DD call vs verifiable 2015–16 operations; 1,000x vs
100x flex inside their own materials; conductivity-basis elision).

### Top 3 risks (updated pre-mortem)

1. **Specialty-trap at a story price**: conductivity/cost ceilings confine
   Galvorn to niches; the entry price capitalized the copper story;
   outcome $400–585M ⇒ 1.5–3x net.
2. **Scale-up gap between the $2–5M demo plant and the ~$40M 3kt plant**
   plus 10x-heavier feedstock integration — the classic materials capex
   wall, with demand a decade late.
3. **Anchor evaporation**: the signed offtake proves to be a frame
   agreement, Tokai Rika PO slips, and the round's momentum narrative
   resets down.

## Required verifications (in priority order)

1. **The signed multi-year contract**: counterparty identity, committed
   minimum volumes, binding vs frame. This is the deal decider.
2. Executed status and volumes of Tokai Rika and NeuroBionics POs.
3. Whether "50% margins ad infinitum" is gross or EBITDA (sponsor's own
   comp doc flags this).
4. IP: Rice license scope/exclusivity; the "4 new licenses + 1 patent."
5. Reconcile founding-date narrative and flex-life figures directly with
   the CEO — the answer's quality is itself diligence data.

## Forecast ledger entry (rev 2, supersedes rev 1)

P(next priced round ≤24mo)=70% · P(<1x net)=60% · P(≥10x net)=4% (panel) /
10% (red team) · Predicted modal outcome: specialty-materials company,
niche success, exit below $600M. Resolve 2028-08 / 2033+. Rubric v1.

## Honesty box

- All traction figures are sponsor-document provenance ([DECK]/[DD-NOTES]),
  not independently verified; the two POs are negotiations, not contracts.
- DexMat is inside the model's training-data horizon; mitigated by
  re-sourcing, not eliminated.
- Panel consistency: IQR 0 on five of six dimensions, 1 on moat. Rev-1 →
  rev-2 movement (traction 2→3, P(<1x) 72→60, P(next round) 40→70) was
  driven by document evidence, which is the system behaving as designed.
- The red team's 10% tail vs panel's 4% is unresolved judgment, not error;
  both were logged.
- Not modeled: secondary opportunities, grant-pipeline continuation,
  methane-pyrolysis optionality, strategic-acquirer dynamics (Shell,
  metals/mining strategic on cap table).
