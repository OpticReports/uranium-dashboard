# DexMat / Galvorn — cost per kilogram, derived

Date: 2026-09-12 · Status: **DERIVED, not disclosed — reported as a band**
Counter-agent: reviewed, verdict FAIL-as-first-framed; rebuilt to its
required corrections (basis flipped, cross-check deleted, three
basis-independent findings added). Companion visual: `cost-per-kg.html`

## Why this is a band and not a number

Casey asked what Galvorn costs per kilogram today and as it scales.
**No DexMat or sponsor document states a $/kg anywhere.** The deck, the
Sept-2026 sponsor memo and the model workbook (SPC Unified Model tab) are
denominated entirely in metres and feet. `factpack.md` already records
the gap:

> Absolute capacity (kg/yr) and $/kg: [UNKNOWN] — never disclosed.

Converting their $/m roadmap to $/kg needs one number nobody has given
us: **the linear density (g/m) of the SKU the roadmap prices.** The
roadmap is tagged "26 AWG equivalent," and that phrase has two readings
whose answers differ by **8.92x**:

| Reading | What it means | Galvorn mass | $/kg effect |
|---|---|---|---|
| **Equal cross-section** | a fibre the same physical size as 26 AWG copper | 0.1674 g/m | **CENTRAL** |
| Equal DC resistance | a fibre that carries the same current: 8.92x the area, 1.29x copper's mass | 1.4936 g/m | lower bound, 8.92x lower $/kg |

26 AWG copper: d = 0.40489 mm, A = 0.12876 mm², 1.1537 g/m. Galvorn
properties are the shipping SKU (Galvorn 1000 tow, 6.5 MS/m, 1.30 g/cc).

### Which reading — the discriminating test

Take the deck's own by-plant revenue targets and the sponsor memo's own
stated markup ("at just 20% markup over production cost") and solve for
how many kilograms must be sold. Equal-cross-section fits inside the
plants; equal-resistance does not:

| Plant | Nameplate | Revenue target | Utilisation, EQUAL X-SECTION | Utilisation, EQUAL RESISTANCE |
|---|---|---|---|---|
| 3 t/yr pilot | 3,000 kg | $5M | 17% | **156%** |
| 30 t/yr demo | 30,000 kg | $44M | **97%** | **869%** |
| 3 kt/yr commercial | 3,000,000 kg | $330M | 38% | **342%** |

The equal-resistance reading requires DexMat to sell 1.6–8.7x more
product than its own plants can make. The 30 t row landing at 97% of
nameplate is a tight enough fit to suggest the sponsor's model is in fact
built on ~0.167 g/m.

Two further checks agree, and the second needs no markup assumption:

- **"2M+ metres produced" against "capacity 15 → 300 kg."**
  Equal-x-section → 335 kg cumulative ≈ 1.1 years at the new 300 kg/yr
  line. Equal-resistance → 2,987 kg ≈ **10 years** at a capacity that was
  15 kg until recently. Only the first is possible.
- **The sponsor's own weight claims are equal-volume claims.** Memo p.3:
  "less conductive per cross-section, but **6x lighter**." 8.96/1.30 =
  6.89 — that is the *density ratio*, true only at equal volume. At equal
  resistance Galvorn is **1.29x heavier** than copper and the entire
  Phase-1 weight-saving pitch reverses sign.

**So the central case is equal-cross-section, and the earlier
resistance-basis figures were 8.92x too low.** Neither reading is
established from the file; this is an unresolved fork, now P1 ask #1.

## THE TABLE

Cost is DexMat's stated production cost. Price applies the memo's own 20%
markup. Copper at $13,387/t = **$13.39/kg — the January 2026 LME record
high**, eight months stale and a high-water mark; the parity target
scales linearly, so use `0.772 x (copper $/kg)` to rescale.

| Scale step | Date | Cost $/m | **COST $/kg** (central, equal x-section) | PRICE $/kg (+20%) | Lower bound (equal resistance) | x copper per kg |
|---|---|---|---|---|---|---|
| **Today** — 15→300 kg/yr line | 2026 now | 5.11 | **~$30,500** | $36,600 | $3,421 | 2,280x |
| 3 t/yr pilot | 2026–27 | 1.33 | **~$7,950** | $9,535 | $890 | 594x |
| 30 t/yr demo ($2–5M capex) | 2028–29 | 0.21 | **~$1,255** | $1,506 | $141 | 94x |
| 3 kt/yr commercial (~$40M capex) | 2030–31 | 0.04 | **~$239** | $287 | $27 | 17.9x |
| "Long-term" deck claim [SELF-REFUTING] | n.d. | 0.001 | $5.97 | $7.17 | $0.67 | 0.45x |

Same roadmap in the units they actually publish, for reference:
$5.11/m → $1.33/m → $0.21/m → $0.04/m, i.e. $1.56/ft → $0.41/ft →
$0.064/ft → $0.012/ft. **A 128x cost decline in ~5 years.**

## What survives the 8.92x fork

These four hold under **both** readings, which makes them more useful
than the table itself.

### 1. The "long-term $0.001/m" claim is below its own feedstock floor
DexMat does not make its own CNT powder (fact pack: upstream supplier
dependence), so its fibre cannot cost less per kg than the powder it
buys, at any yield. $0.001/m is **$5.97/kg** (central) or **$0.67/kg**
(lower bound) — 84x to 2,985x below the fact pack's independent
CNT-fibre cost class of $500–2,000/kg, and below copper metal. Not a
stretch target; arithmetically impossible. It is in the deck.

### 2. The sponsor's 2034 model needs more CNT than the world makes
At the memo's own Phase-3 cost + 20% markup ($0.048/m), Fig. 1's
**$4.501bn 2034 revenue** requires 93.8 billion metres/yr:

| | Fibre needed | vs world named CNT powder capacity (~6,200 t/yr: LG Chem 6,100 + OCSiAl 100) |
|---|---|---|
| Equal x-section | 15,700 t/yr | **2.5x the world's supply** |
| Equal resistance | 140,100 t/yr | **22.6x** |

The workbook's 2040 $67.2bn needs 234,500–2,092,500 t/yr — **38x to 338x**.
It is also 5.2x–46.4x the entire 3 kt plant, of which the model builds
one. This is the strongest single finding here and it is basis-independent.

### 3. The October price cut is mostly margin, not cost
$8.49/ft → $0.48/ft is a **17.7x price cut**, against a **3.84x cost
cut** ($5.11/m → $1.33/m) over the same step. Gross margin goes
**82% → 15.5%**. The "99% margins" in the DD notes cannot coexist with
the deck's own $5.11/m cost at the $8.49/ft list — that combination gives
82%, and for 99% to hold cost would have to be $0.28/m, 18x below the
deck's own figure. The only place the documents cohere is October 2026:
$0.48/ft price on $1.33/m cost = 18% markup ≈ the memo's stated 20%.

### 4. Our own record's copper-parity line is wrong — correct it
`factpack.md` L64 and `memo.md` both say the roadmap "only reaches
approximate copper parity ($0.04/m at 26 AWG)." That is wrong on both
available benchmarks: $0.04/m is **2.6x dearer** than 26 AWG copper metal
($0.01544/m) and **12.3x cheaper** than the memo's own "expected copper
wire" of $0.15/ft ($0.492/m). Neither is parity. This matters because the
line is load-bearing — it is the record's rebuttal of the sponsor's "3x
cheaper than copper by 2031." Separately, the sponsor's two copper
benchmarks contradict each other: $0.063/ft is called "copper price
parity" in 2028–29, then $0.15/ft is the "expected" copper wire price in
2030–31 — **2.38x apart in two years**, an unstated copper price rise.

## The per-kilogram framing cuts against DexMat

Because the shipping tow needs **1.29x copper's mass** to carry the same
current, matching copper's $/kg is **not** cost parity. Galvorn must
reach **0.772 x copper's price per kg** — $10.34/kg at the Jan-2026
record — before a metre of equal-resistance Galvorn costs what a metre of
copper costs. Even the optimistic lower-bound endpoint of $27/kg is 2.6x
that. (This is not an independent result: 0.772 is the gravimetric
conductivity ratio 5,000/6,473 already in the fact pack, restated in
dollars.) At equal resistance it also needs **8.92x the cross-section**
— ~3x the diameter, ~9.5 gauge sizes larger — which is a connector,
conduit and bend-radius problem, not a price problem.

What this does NOT touch: the beachhead. Silver-plated copper aerospace
wire wholesales at $2.86–3.15/ft against Galvorn's $1.56/ft today. Per
foot, in the market DexMat actually sells into, it is already cheaper.
The per-kilogram table is the right lens for the bulk-copper TAM story
and the wrong lens for the business that exists.

## HONESTY BOX

- **Nothing here is a DexMat disclosure.** $/kg has never been given by
  the company or any sponsor document. This is our conversion.
- **The band is 8.92x wide and the fork is unresolved.** We favour
  equal-cross-section on three independent tests, but "favour" is not
  "establish." Every headline figure could be the lower-bound column.
- **The $30/kg literature model is NOT corroboration** and an earlier
  draft of this analysis wrongly used it as such. It is a 144 t/yr plant
  vs a 3,000 t/yr plant — 21x the scale — and it is the same unbuilt-plant
  TEA the fact pack already cites. On the central basis the 3 kt endpoint
  ($239/kg) is **8x above** that model, which is a tension, not support.
- **Copper at $13.39/kg is the Jan-2026 record**, not spot on 2026-09-12.
  It flatters Galvorn by raising the parity target. Rescale with
  `0.772 x (copper $/kg)`.
- **The dates are the company's.** Standing view unchanged: carbon fibre
  took ~50 years to fall ~40x. A 128x decline in 5 years has no precedent
  in advanced fibres.
- **SKU mixing is a live risk.** At least seven distinct products appear
  across the file (26 AWG roadmap item; 2-ply yarn at $8.49/ft; Galvorn
  1000 tow; 6 MS/m median tape; single filament; film/braid/cathodes; the
  separate "$22/m → $4/m" cost series). The "$22/m → $4/m" line is a
  **third, inconsistent** cost curve — 4.31x and 3.01x the roadmap's
  corresponding steps, with a different reduction rate (81.8% vs 74.0%),
  so it is not the same series rescaled.
- **Within the equal-resistance family alone the answer still spans 1.7x**
  depending on which property table is used (deck filament 10 MS/m ·
  1.6 g/cc → $4,299/kg today; tow 6.5 · 1.30 → $3,421; memo's declared
  6 MS/m tape → $3,174; 800 tow 4.8 · 1.30 → $2,539).
- **Not modelled:** yield/scrap per plant step, insulation and cabling
  conversion cost, feedstock CNT price path, whether $5.11/m is
  fully-loaded or variable cost, and the annealing penalty — a
  high-purity space-qualified grade loses up to 4x conductivity, raising
  the mass needed and every equal-resistance $/kg figure by up to 4x again.

## PENDING DD QUESTIONS (from this analysis, 2026-09-12)

Ranked per protocol v1.2. Statuses: ● asked · ✓ answered · ◐ partial ·
✗ refused · ⌛ expired (60 days from first ask). **Round closes 2026-09-28.**

**P1 — decision-gating:**
1. ● **NEW · Linear density (g/m or tex) of the SKU the cost roadmap
   prices, and the definition of "26 AWG equivalent"** — same resistance
   or same cross-section? *Moves:* every $/kg figure by 8.92x, and with
   it the entire cost-parity conclusion that the phase-1 thesis rests on.
   One email, answerable before the close. **Note:** the Galvorn 1000
   datasheet and "Miralon Yarn TDS_2025" are both cited in our record but
   **neither document is archived in this deal folder** — only a
   one-line transcription of the annealing claim. Request both; fibre
   datasheets state tex or denier, so the number is very likely already
   sitting in a document we were shown and did not keep.
2. ● **NEW · DexMat's own $/kg for the current line and each roadmap
   step**, so we stop deriving it. *Moves:* collapses the band entirely.
3. ● **NEW · How does the 2034 revenue model obtain 15,700–140,000 t/yr
   of CNT fibre** when world named CNT powder capacity is ~6,200 t/yr?
   *Moves:* finding 2 above is basis-independent and, if unanswered, caps
   the copper-adjacency tail branch directly.

**P2 — score-moving:**
4. ● **SHARPENED (was Q9) · Is $5.11/m fully-loaded or variable cost**,
   and reconcile "~99% margins" with it at the $8.49/ft list — those give
   82%, not 99%. *Moves:* unit economics; an arithmetic candor probe now.
5. ● **NEW · Is the Oct-2026 $0.48/ft the same 2-ply yarn as today's
   $8.49/ft?** A 17.7x price cut against a 3.84x cost cut is not
   self-consistent on one SKU. *Moves:* whether the October milestone
   tests the cost curve at all, or just a repricing.
6. ● **NEW · Which SKU is the "$22/m → $4/m total Galvorn cost" line?**
   It is a third cost curve, 3.0–4.3x the roadmap. *Moves:* whether the
   deck's cost narratives are mutually consistent.
7. ● **CARRIED (Q8) · The October 2026 $0.48/ft milestone** — with a
   timing trap: it is targeted for **October** and the round closes
   **2026-09-28**, so the test lands *after* the money is committed.
   Residual ask: evidence the upgrade is on schedule — commissioning
   status, an updated price list, a customer quote at the new price —
   **before** 2026-09-28.

**P3 — completeness:**
8. ● **NEW · Feedstock CNT cost per kg and its assumed path.** At a
   $239/kg finished product, feedstock plausibly dominates. *Moves:*
   whether the 3 kt endpoint is reachable at all.
9. ● **NEW · $/kg for the annealed / high-purity space grade**, which
   carries the up-to-4x conductivity penalty on their own beachhead's
   qualification path. *Moves:* beachhead economics.

## Corrections owed to the existing record

- `factpack.md` L64 and `memo.md`: "$0.04/m at 26 AWG ≈ approximate
  copper parity" is wrong on both benchmarks (finding 4 above). Flagged,
  not yet edited — Casey's call, since it is load-bearing in a frozen memo.

## Sources

- `factpack.md` rev 3 (2026-09-08) — cost roadmap, specific-conductivity
  table, capacity and by-plant revenue targets, copper LME, CNT powder
  capacity, literature scale-up model
- `sponsor-memo-2026-09.md` — $8.49/ft list, $0.48/ft Oct-2026 target,
  phase costs in $/ft, 20% markup, Fig. 1 revenue path
- `sponsor-docs-2026-09/model-workbook-spc-tab.png` — $0.40/ft production
  cost, $0.48/ft price to wire maker; confirms no mass unit anywhere

Deal status unchanged by this analysis: **borderline pass / watch**, S2 open.
