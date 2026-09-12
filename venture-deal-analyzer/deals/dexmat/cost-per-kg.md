# DexMat / Galvorn — cost per kilogram

Date: 2026-09-12 · **rev 2, ANCHORED** (rev 1 shipped an 8.92x band)
Companion visual: `cost-per-kg.html`

## The anchor

No DexMat or sponsor document states a $/kg; the deck, the Sept-2026 memo
and the model workbook are denominated entirely in metres and feet, and
`factpack.md` records `$/kg: [UNKNOWN] — never disclosed`. Rev 1
therefore shipped a band 8.92x wide, with the linear density as a P1 ask.

**Casey supplied it 2026-09-12: production cost after the new plant is
$1,389.20/kg.** That pins the density and collapses the band.

### It ties out exactly — which tells us what it is

The deck's 3 t/yr revenue target is $5M on 3,000 kg of nameplate. At the
memo's own 20% markup:

    $5,000,000 / 3,000 kg / 1.20 = $1,388.89/kg

against the supplied $1,389.20 — a **0.02%** match. So the anchor is the
**3 t/yr pilot** step ($1.33/m), and it is the sponsor's own model
arithmetic expressed in mass units, not an independent cost disclosure.
Internally consistent; not external corroboration. A cost figure that
falls out of a revenue target is a plan, not a measurement.

### What the anchor reveals about the product being priced

$1.33/m ÷ $1,389.20/kg = **0.9574 g/m**. Working backwards:

| Quantity | Value | Meaning |
|---|---|---|
| Linear density | 0.9574 g/m | **0.830x** copper's mass per metre — lighter than the copper it replaces |
| Cross-section (at 1.30 g/cc) | 0.7365 mm² | 5.72x the 26 AWG copper area |
| **Implied conductivity** | **10.14 MS/m** | **The deck's best single filament (10), not the shipping tow (6.5)** |

This is the fact pack's standing candor pattern, now located inside the
cost roadmap. The record already establishes that the deck quotes
best-filament performance as if it were the product. **If the real
shipping tow (6.5 MS/m) is used, the same electrical job needs 1.56x more
mass per metre** — so every figure below understates cost per delivered
function by about half as much again.

## THE TABLE

Converts the deck's $/m roadmap at the anchored 0.9574 g/m. Price applies
the memo's stated 20% markup. Copper at $13,387/t = **$13.39/kg, the
January 2026 LME record**; rescale the parity line with
`1.205 x (copper $/kg)`.

| Scale step | Date | Cost $/m | Cost $/ft | **COST $/kg** | Price $/kg (+20%) | x Cu per kg |
|---|---|---|---|---|---|---|
| **Today** — 15→300 kg/yr line | 2026 now | 5.11 | 1.56 | **$5,337** | $6,405 | 399x |
| **3 t/yr pilot — SUPPLIED ANCHOR** | 2026–27 | 1.33 | 0.41 | **$1,389** | $1,667 | 104x |
| 30 t/yr demo ($2–5M capex) | 2028–29 | 0.21 | 0.064 | **$219** | $263 | 16.4x |
| 3 kt/yr commercial (~$40M capex) | 2030–31 | 0.04 | 0.012 | **$41.78** | $50.14 | 3.1x |
| "Long-term" deck claim [SELF-REFUTING] | n.d. | 0.001 | 0.0003 | $1.04 | $1.25 | 0.08x |

A **128x** cost decline in ~5 years. Sanity: today's $5,337/kg is
2.7–10.7x the independent CNT-fibre cost class of $500–2,000/kg — high,
but that class describes established producers at volume and DexMat runs
a 300 kg/yr line. Far closer to it than rev 1's $30,529.

## The model is exact at the pilot and breaks at scale-up

Same test across all three plants, now with density known:

| Plant | Nameplate | Revenue target | Implied utilisation | |
|---|---|---|---|---|
| 3 t/yr pilot | 3,000 kg | $5M | **100.0%** | exact — the anchor's origin |
| 30 t/yr demo | 30,000 kg | $44M | **557%** | needs 5.6x more than the plant can make |
| 3 kt/yr | 3,000,000 kg | $330M | **219%** | needs 2.2x more |

The pilot year is fully specified and coherent. The two scale-up years
are not: at the roadmap's own costs and the memo's own markup their
revenue targets require selling 5.6x and 2.2x nameplate. Either the
capacities are understated, the prices assume a much fatter markup than
20%, or the targets are unanchored. **New P1** — it sits under the $44M
and $330M lines the whole ramp runs through.

## What the anchor changed, and what it didn't

### REVERSED — the per-kilogram parity finding
Rev 1 said Galvorn must reach **0.772x** copper's $/kg for per-metre
parity, because the equal-resistance tow is 1.29x *heavier* than copper.
On the anchored density this flips: at 0.9574 g/m the conductor is
**0.830x copper's mass**, so it may cost **1.205x copper's $/kg** —
**$16.13/kg** — and still tie per metre. A modest mass dividend, not a
penalty. The 2030–31 endpoint of $41.78/kg is still **2.6x** that
threshold, so parity with copper metal is still not reached; but the
direction of the argument was wrong in rev 1.

### SURVIVES — the "long-term $0.001/m" claim is below its feedstock floor
**$1.04/kg**: 479–1,915x below the independent CNT-fibre cost class, and
1/13th of copper metal. DexMat does not make its own CNT powder, so its
fibre cannot cost less per kg than the powder it buys, at any yield.

### SURVIVES, now pinned — 2034 needs more CNT than the world makes
Fig. 1's $4.501bn 2034 revenue at $0.048/m = 93.8bn metres =
**89,775 t/yr** of fibre against ~6,200 t/yr of world named CNT powder
capacity — **14.5x global supply**, and 30x the entire 3 kt plant, of
which the model builds one. Rev 1 could only bound this at 2.5–22.6x.

### UNCHANGED — the October price cut is mostly margin, not cost
All in $/m. $8.49/ft → $0.48/ft is a 17.7x price cut against a 3.84x cost
cut; gross margin 82% → 15.5%. "~99% margins" cannot coexist with the
deck's own $5.11/m at the $8.49/ft list.

### UNCHANGED — our own record's copper-parity line is still wrong
`factpack.md` L64 ("approximate copper parity ($0.04/m at 26 AWG)") and
`memo.md` (same claim, no figures): $0.04/m is **2.6x dearer** than
26 AWG copper metal ($0.01544/m) and **12.3x cheaper** than the memo's
own "expected copper wire" at $0.15/ft. Neither is parity.

## The beachhead, stated correctly

The deck's parity claim is a **cost** claim: $1.56/ft to make vs
silver-plated copper wire at $2.86–3.15/ft wholesale. At the price DexMat
actually posts, **$8.49/ft, it is 2.7–3.0x dearer than SPCW** — and even
a 20% markup on cost ($1.87/ft) is not what it charges. Price parity in
its own beachhead arrives only with the October $0.48/ft, which lands
*after* the 2026-09-28 close.

## HONESTY BOX

- **The anchor is the sponsor's own arithmetic**, matching $5M/3,000/1.2
  to 0.02%. It makes the model legible; it does not verify DexMat can
  produce at that cost.
- **Only the 3 t/yr row is supplied.** Every other row is derived from
  the $/m roadmap at the anchored density.
- **The density is 0.9574 g/m only if "the new plant" is the 3 t/yr
  pilot.** If it means the 30 t demo, density is 0.1512 g/m and every
  figure is 6.3x higher. The exact 100.0% tie makes the pilot reading
  near-certain, but it is an inference — confirm it.
- **The roadmap prices a 10 MS/m conductor**; the shipping tow is 6.5.
  Cost per delivered function is ~1.56x worse than every figure here.
- **Copper at $13.39/kg is the Jan-2026 record**, not spot.
- **The dates are the company's.** Carbon fibre took ~50 years to fall
  ~40x; 128x in 5 years has no precedent in advanced fibres.
- **SKU mixing remains live.** The "$22/m → $4/m" line is a third,
  inconsistent cost curve (4.31x and 3.01x the roadmap's steps,
  reduction rate 81.8% vs 74.0%).
- **Not modelled:** yield/scrap, insulation and cabling conversion,
  feedstock CNT price path, whether $5.11/m is fully-loaded or variable,
  and the annealing penalty (a high-purity space grade loses up to 4x
  conductivity, needing up to 4x the mass per equivalent metre).
- **Verification:** rev 1 was counter-agent reviewed twice (first framing
  returned FAIL — wrong mass basis, invalid cross-check; second pass
  caught six arithmetic errors). **Rev 2 has not yet had an independent
  adversarial pass** — one is running. The reversal above is the most
  likely thing to move.

## PENDING DD QUESTIONS

**P1 — decision-gating:**
1. ✓ **RESOLVED · Linear density** — supplied via the anchor, 0.9574 g/m.
   Residual: confirm directly, and confirm which plant "the new plant" is.
2. ● **NEW · Is the cost roadmap denominated at 10 MS/m or the shipping
   tow's 6.5?** The anchored density implies 10.14. *Moves:* cost per
   delivered function by 1.56x; the candor pattern inside the cost model.
3. ● **NEW · How do the 30 t and 3 kt revenue targets work at 557% and
   219% of nameplate?** *Moves:* the $44M and $330M lines.
4. ● **NEW · How does 2034 source 89,775 t/yr of CNT** against ~6,200
   t/yr world capacity? *Moves:* caps the tail branch.

**P2 — score-moving:**
5. ● Is $5.11/m fully-loaded or variable cost; reconcile "~99% margins."
6. ● Is the Oct-2026 $0.48/ft the same SKU as today's $8.49/ft?
7. ● Which SKU is the "$22/m → $4/m" line?
8. ● **CARRIED (Q8)** October $0.48/ft milestone — targeted for October,
   round closes 2026-09-28. Ask for commissioning status or a customer
   quote at the new price **before** the close.

**P3 — completeness:**
9. ● Feedstock CNT cost per kg and its path. At $41.78/kg finished,
   feedstock dominates.
10. ● $/kg for the annealed / high-purity space grade.

## Corrections owed to the existing record

- `factpack.md` L64 and `memo.md`: the copper-parity line is wrong on
  both benchmarks. Flagged, **not yet edited** — load-bearing inside a
  frozen memo, so Casey's call.

## Sources

`factpack.md` rev 3, `sponsor-memo-2026-09.md`,
`sponsor-docs-2026-09/model-workbook-spc-tab.png`, and the $1,389.20/kg
production cost supplied by Casey 2026-09-12.

Deal status unchanged: **borderline pass / watch**, S2 open.
