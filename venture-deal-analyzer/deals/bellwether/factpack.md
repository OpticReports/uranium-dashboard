# Fact pack — Bellwether (X/Alphabet climate-intelligence spinout)

Rev 1, 2026-08-20. Sixth vehicle in the ledger, and the first deal where
the LP holds **two exposures to the same name at once**: an indirect
position via Series X Capital Fund I and a direct angel allocation.

## Headline finding

**There is no publicly documented Series A — because there is no
publicly documented spinout.** As of every primary source reachable on
2026-08-20, Bellwether is still an *internal project inside X*, not an
independent company. No Form D, no round, no investors, no valuation.
Casey's information that it is spinning out and going to the Series X
fund is **ahead of the public record**, which is normal pre-announcement
but means the valuation can only come from the sponsor. Per the standing
rule it is being ASKED FOR, not modelled around.

## LP-stated position [LP-STATED, 2026-08-20]

- Bellwether **is spinning out of X and going to the Series X fund** —
  Casey has confirmation. (This resolves the open question posed in the
  Matter fact pack: "is Bellwether in the pipeline?" → YES.)
- Casey will take a **direct angel check of ~$40,000 into the Series A
  at a 20–25% discount**, alongside the fund's position.

## Company [VERIFIED]

Climate-intelligence moonshot inside X. "The first prediction engine for
the Earth and everything on it" (X's own project page). Models Earth at
**100 x 100 m resolution across ~600 geodata layers** plus
building-level attributes (materials, roof type, age); wildfire,
hurricane and severe-weather risk. Built on Google geospatial data +
DeepMind models.

- **Sarah Russell — founder and CEO of Bellwether, concurrently a
  Managing Director at X.** The dual title is the tell that this is an
  internal project role, not an independent-company role. Rich Mazzola
  is Head of Product & Commercialization; an X job posting for the team
  is titled "Research Engineer, Bellwether, **X**" — i.e. hiring under
  the X legal entity. [x.company/projects/bellwether]
- **Hiscox** — first carrier to use the Bellwether wildfire modelling
  tool in California [Hiscox Group press release, 2025-06-20].
- **Swiss Re** — the "large reinsurer": Bellwether wildfire
  intelligence feeds Swiss Re's **CatNet** platform; Swiss Re describes
  Bellwether as "a team at Alphabet's innovation engine X."
- **Kansas City** emergency management; **National Guard / Defense
  Innovation Unit** [x.company/case-study/bellwether-diu].
- RBC Capital Markets Insights (June 2026) frames the target market as
  the ~$6T insurance sector, and still calls Bellwether "a moonshot from
  Alphabet's Google X lab." **The RBC piece contains zero funding,
  investor, valuation or capital-raising language** (fetched and
  confirmed).

Read against the rest of this ledger, Bellwether is the rare early-stage
story that is **named-customer live before the priced round** — the
opposite of Matter (LOIs and cost-plus codesigns) and of Quaise (no
commercial revenue at all). Caveat: Hiscox/Swiss Re/KC/DIU are publicly
confirmed as *deployments and partnerships*; none is publicly confirmed
as a **paid** contract at a disclosed ACV.

## Valuation — THE OPEN NUMBER [UNKNOWN — REQUIRED]

Sweep run 2026-08-20 (full audit trail in session log):

- EDGAR full-text, Form D, 2025-01-01 → 2026-08-20, `"Bellwether"`:
  **one hit** — *Bellwether Topco, L.P.* (CIK 0002063996), a New
  Mountain Capital PE holdco at 1633 Broadway, NY. Ruled out: wrong
  state, wrong industry, no Alphabet/X/Russell/Mazzola nexus.
- Zero hits for `"Bellwether Earth"`, `"Bellwether Climate"`,
  `"Bellwether Technologies"`, `"Mazzola" "Bellwether"`, `"Sarah
  Russell"` (Form D), `"Astro Teller"` (Form D), `"X Development LLC"`
  (Form D), `"XXVI Holdings"` (Form D), and `"Bellwether"` scoped to
  Alphabet CIK 0001652044 (so no "Other Bets" disclosure exists).
- **Negative evidence that matters:** X's own Series X Capital blog
  post names the fund's portfolio — Taara, Chorus, Anori, Verily Health
  ($300M led March 2026) — and **Bellwether is absent**. TechCrunch's
  2026-03-19 piece on Anori enumerates the spinout lineage (Taara March
  2025, Chorus, Anori March 2026 — $26M led by Prologis and Builders VC
  with Series X participating) and **does not mention Bellwether**.
  X spinouts get announced; this one has not been.

**Lead killed:** SXC Venus, LLC (CIK 0002097915 — $32M SPV, Form D
2026-03-05, $0 sold at filing, GP Series X Capital Fund I GP LLC, Gideon
Yu director) is **almost certainly the Anori vehicle**, not Bellwether:
it was filed two weeks before the 2026-03-19 Anori announcement. Logged
here so the coincidence is not rediscovered and mistaken for evidence.

**Caveat on the negative:** absence of a Form D is strong but not
conclusive. Reg D allows 15 days after first sale to file; a round can
be done under §4(a)(2) with no Form D at all; and X spinouts **rebrand**
on graduation (Flux was formerly Vannevar Technologies), so a
Bellwether entity incorporated under a different name would be invisible
to a name-based sweep. **The entity's legal name is therefore the single
highest-value thing to ask for** — it makes everything else findable.

**NOT READ (403-blocked, flagged not guessed):** Fast Company feature
`91570542/x-moonshot-factory-google-astro-teller-materra-bellwether`
— the likeliest place a spinout hint sits; Crunchbase org page;
Latitude Media piece (quoted only via search index). Request from the
sponsor or supply directly.

## Why the discount is the whole question

A 20–25% entry discount is a **pure multiplicative uplift on every
gross outcome**: your effective post = (1 − d) x headline post, so
every multiple scales by 1/(1 − d).

| discount | gross uplift | EV effect |
|---|---|---|
| 20% | x1.2500 | +25.0% |
| 25% | x1.3333 | +33.3% |

Bracketed by our two calibrated anchors (there is no `series_a` stage in
calibration.json — Series A sits between `seed` and `series_b`; these
are BASE-CURVE figures, **not** a Bellwether-specific forecast, and no
panel has scored this deal yet):

| anchor | discount | EV mult | EV on $40k | P(<1x) | P(>=3x) | P(>=10x) |
|---|---|---|---|---|---|---|
| seed | 0% | 2.005 | $80,209 | 65.9% | 14.9% | 3.68% |
| seed | 20% | 2.507 | $100,262 | 61.1% | 18.2% | 5.07% |
| seed | 25% | 2.674 | $106,946 | 59.7% | 19.1% | 5.53% |
| series_b | 0% | 2.320 | $92,783 | 41.7% | 19.2% | 2.61% |
| series_b | 20% | 2.899 | $115,979 | 33.3% | 25.7% | 3.86% |
| series_b | 25% | 3.093 | $123,711 | 31.0% | 27.7% | 4.33% |

Two honest qualifications, both load-bearing:

1. **A discount off an unfair price is not alpha.** The uplift above is
   real only if the headline post is one an arm's-length investor would
   pay. This is exactly why the headline number is REQUIRED before the
   discount can be scored — the discount and the price are not
   separable facts.
2. **Circularity risk.** If Series X is the sole/lead investor AND the
   recipient of the discount, then no independent party sets the
   reference price, and "20–25% off" is not a discount — it IS the
   price. The Series X fact pack already flags that neither the 20%
   discount nor the 10-deal mandate appears in ANY public source. Note
   the one X spinout with an unaffiliated lead — Anori, led by Prologis
   and Builders VC — is the only round in the whole pipeline where an
   outside party set the price. ASK: who prices Bellwether, is there an
   unaffiliated co-lead, and what is the discount measured against?

## Structure note — the angel check is the better instrument

A direct angel check carries **no management fee and no carry**. The
same dollar through Fund I pays both. On identical underlying outcomes
the $40k direct is worth roughly `1/(1−carry)` more at the top end than
the fund route — the fund's compensating advantage is diversification
across ~10 spinouts, which a single check does not have.

## Portfolio note — double exposure and a live conflict

- **Concentration:** Casey is long Bellwether twice (fund + direct).
  Small in dollars; logged so it is not double-counted as
  diversification.
- **Conflict with the Matter evaluation:** Casey is now becoming an
  investor in the company this ledger identified as Matter's strongest
  competitor, while Matter is live in the pipeline via Burke. This does
  not change the Matter analysis — the competitor addendum was written
  before the allocation was confirmed — but it is a **disclosure item**
  if the Matter conversation continues.

## UNKNOWN — REQUIRED (ask, per standing rule)

1. **The spinout entity's legal name and state** — the unlock for every
   filing-based check.
2. Series A headline post-money, round size, lead, and close date.
3. Instrument and discount mechanics: priced equity vs SAFE/note; what
   the 20–25% is measured against; who certifies it; whether an
   unaffiliated party co-leads.
4. Whether the angel allocation is direct on the cap table or
   SPV-wrapped, and its fees.
5. **Alphabet/X retained stake, and the IP-license terms.** Bellwether
   runs on Google geospatial data and DeepMind models — that license is
   likely a material ongoing economic term and is entirely undisclosed.
   A post-money is close to meaningless to an angel without it. Also:
   any ROFR/buyback that could cap exit outcomes.
6. Which of Hiscox / Swiss Re / Kansas City / DIU are revenue-
   generating contracts, and at what ACV.
