# DexMat / Galvorn — price per foot, and cost per kilogram

Date: 2026-09-12 · **rev 3** · Companion visual: `cost-per-kg.html`
Counter-agent: three passes. Rev-1 framing FAIL (wrong mass basis, invalid
cross-check); arithmetic pass caught six errors; rev-2 FAIL on the
inference chain — its nine required corrections are carried here.

---

# PART 1 — PRICE PER FOOT (the unit wire is sold in)

Per foot is the documents' **native** unit: no mass conversion, no linear
density, no band. Firmest ground in the analysis, and where the sponsor's
framing is weakest.

## There is no single incumbent price

The memo quotes silver-plated copper wire at "$2.86–3.15/ft" and argues
against that. Its own workbook uses **two tiers** — **$2.63/ft** for
military aero, missiles and space; **$0.73/ft** for commercial airlines,
drones and the rest of the market. They reconcile *exactly* to the
workbook's own market size:

| Sector | 2028 volume | Incumbent $/ft | Revenue | % volume | % value |
|---|---|---|---|---|---|
| Military aero & missiles | 39.9 M ft | $2.63 | $104.9M | 2.0% | 6.6% |
| Space | 20.0 M ft | $2.63 | $52.6M | 1.0% | 3.3% |
| Commercial airlines & drones | 263.7 M ft | $0.73 | $192.5M | 13.0% | 12.1% |
| Rest of SPC market (non-aero) | 1,699.6 M ft | $0.73 | $1,240.7M | 84.0% | 78.0% |
| **Total** | **2,023.2 M ft** | blended **$0.786** | **$1,590.7M** | | |

Workbook states $1.59bn for 2028. Exact. **The tier the memo benchmarks
against is 3.0% of the market by volume, 9.9% by value.**

## THE TABLE

| Galvorn, per foot | Date | As quoted | Copper-equivalent (x1.56) | vs $2.63 | vs $0.73 | vs $0.0047 Cu metal |
|---|---|---|---|---|---|---|
| **Posted list today** (2-ply yarn) | now | **$8.49** | $13.245 | 5.04x | **18.1x** | 2,814x |
| Today — cost +20% | 2026 | $1.869 | $2.916 | 1.11x | 3.99x | 619x |
| 3 t/yr pilot / plant upgrade | 2026–27 | $0.486 | **$0.759** | 0.29x | **1.04x** | 161x |
| **30 t/yr demo — first real win** | 2028–29 | $0.077 | $0.120 | 0.05x | **0.16x** | 25.5x |
| 3 kt/yr commercial | 2030–31 | $0.015 | $0.023 | 0.01x | 0.03x | **4.8x** |

Copper ladder: metal content of 26 AWG **$0.0047/ft** (LME $13,387/t
Jan-2026 record; $0.0034 at a mid-cycle $9,750/t) · plain copper wire
**$0.15/ft** (memo's 2030–31 benchmark, gauge unstated — implies ~11 AWG
of metal, so likely finished/heavier) · SPCW **$0.73** and **$2.63**.

## Why 1.56x — and why it survives the basis question

$1.33/m ÷ $1,389.20/kg = 0.9574 g/m = **0.830x the mass of 26 AWG copper**
(1.15366 g/m). Two readings, one multiplier:

- **Nominal gauge (parsimonious, documented material).** 0.9574 g/m at
  1.30 g/cc = 0.73645 mm². At the shipping tow's 6.5 MS/m that carries
  **64.1% of 26 AWG copper's conductance at 83.0% of its mass** — fits
  the fact pack's standing note that buyers speccing ≤77% of copper's
  conductance already get Galvorn lighter than copper. Matching copper
  needs 1/0.641 = **1.5601x**.
- **Equal resistance.** Requires σ/ρ = **7,800 S·m²/kg** — 1.56x the tow
  (5,000), 1.25x the deck's best filament (6,250), **1.21x copper
  (6,473)**. No document claims such a material. Gap to the tow:
  **1.5601x**.

Identical. **The per-foot comparison is robust to the interpretation;
the $/kg table is not.**

## What the per-foot view changes

1. **The October milestone is parity, not a win.** $0.48/ft becomes
   $0.759/ft copper-equivalent against $0.73/ft for 97% of the market.
   The memo presents it as beating $2.86–3.15/ft — true only of the
   3%-of-volume military tier.
2. **First genuine price win is 2028–29** at the 30 t demo plant
   ($0.120/ft vs $0.73) — two years later and one plant further out.
3. **A buyer faces $8.49/ft today**, not $1.56/ft: 18x what 97% of the
   market pays, 5x the military tier. "At/below cost parity today" is a
   statement about DexMat's cost, not any price a customer can buy at.
4. **Galvorn never reaches copper's metal content** — 4.8x it in
   2030–31, and that floor *falls* 27% at a mid-cycle copper price.

## REFUTED — "at/below cost parity TODAY"

Prompted by Casey 2026-09-13: "it's def not cheaper now." He is right.

| Basis | $/ft | Copper-equivalent | vs $2.63 (3% of mkt) | vs $0.73 (97%) |
|---|---|---|---|---|
| What a customer actually pays | $8.490 | $13.245 | **5.04x** | **18.1x** |
| DexMat's own intended price (cost +20%) | $1.869 | $2.916 | **1.11x** | **3.99x** |
| DexMat's bare-fibre cost | $1.558 | $2.430 | 0.92x | **3.33x** |

**Even at DexMat's own planned markup it is dearer than both incumbent
tiers.** The parity claim survives on one basis only — bare-fibre *cost*
against finished-wire *price*, unadjusted for conductivity, against the
tier that is 3.0% of volume. Three thumbs, one direction.

**The cross-check cited to support it refutes it.** `factpack.md` L105
bracketed the claim as "consistent with independent beachhead pricing of
$100s–$1,000+/kg." Galvorn's cost today is **$5,337/kg** — **5.3x the top
of that range**. Corrected in the fact pack 2026-09-13.

Carried as a POSITIVE in three places; factpack now corrected, the other
two are frozen rev-2 artifacts awaiting Casey's call:
- `factpack.md` L105 — the bracketed endorsement ✓ **corrected**
- `memo.md` L92 — "beachhead cost parity today" under **What improved**
- `memo.html` L91 — "credible beachhead cost parity vs silver-plated aero
  cable today", in the memo's page-one synthesis

**Two things this still cannot settle**, both running in Galvorn's
favour. (1) Galvorn's figures are **bare fibre**; every copper comparator
is **finished insulated wire** — insulation, jacketing and qualification
are unquantified per-foot costs on the Galvorn side. (2) The workbook's
$2.63/ft is 9–20% below the memo's own $2.86–3.15/ft for the same
product, and neither states a gauge.

Workbook note: the tab's footnote says revenue = Galvorn feet x $0.72/ft,
but every computed cell uses $0.48/ft (2028: $17M/35.3 M ft = $0.4816;
2034: $566M/1,179 M ft = $0.4801). Stale footnote, not a live error.

---

# PART 2 — COST PER KILOGRAM

No document states a $/kg; `factpack.md` records `[UNKNOWN] — never
disclosed`. Rev 1 shipped an 8.92x band. Casey supplied **$1,389.20/kg
after the new plant**, pinning 0.9574 g/m.

**The anchor ties to the sponsor's own arithmetic:** $5M ÷ 3,000 kg ÷
1.20 = $1,388.89/kg — $0.31 from the supplied figure, a residual we
cannot account for. Independent corroboration: the memo's October
$0.48/ft converts at 0.9574 g/m to **$1,645/kg**, within 1.3% of this
table's $1,667/kg pilot price.

**Which plant? Pilot vs upgrade, not pilot vs 30 t.** The memo attributes
"$0.40/ft ($1.33/m)" to the **"current plant upgrade," October 2026** —
not to a 3 t/yr pilot. Same event or two? The 30 t reading is ruled out
($1,222.22 is 12% off). Also: the memo's own "$0.40/ft ($1.33/m)" is
internally inconsistent by 1.35%; off $0.40/ft, density is 0.9447 g/m
and every $/kg rises 1.35%.

| Scale step | Date | Cost $/m | COST $/kg | Price $/kg | x Cu per kg |
|---|---|---|---|---|---|
| **Today — ACTUAL posted list** ($8.49/ft) | now | — | — | **$29,094** | 2,173x |
| Today — 15→300 kg/yr line | 2026 | 5.11 | **$5,337** | $6,405 (cost+20%) | 399x |
| **3 t/yr pilot / upgrade — ANCHOR** | 2026–27 | 1.33 | **$1,389** | $1,667 | 104x |
| 30 t/yr demo | 2028–29 | 0.21 | **$219** | $263 | 16.4x |
| 3 kt/yr commercial | 2030–31 | 0.04 | **$41.78** | $50.14 | 3.1x |
| "Long-term" deck claim [SELF-REFUTING] | n.d. | 0.001 | $1.04 | $1.25 | 0.08x |

The 128x decline is just the deck's own $/m ratio (5.11/0.04 = 127.75);
the $/kg conversion adds nothing to it. Copper at $13.39/kg is the
**Jan-2026 record and flatters Galvorn**: at a mid-cycle $9,500–10,000/t
every x-copper figure rises 34–41% and the parity threshold falls to
$11.45–12.05/kg. Basis: ρ_Cu = 8.96 (the deck uses 9.0, a 0.4% shift).

## TWO BASES for parity — not a reversal

An earlier revision called this a reversal of rev 1. **That was wrong**:
the two numbers answer different questions, and rev 1's stands for the
product DexMat actually ships.

| Basis | What it is | Parity threshold | 2030–31 step |
|---|---|---|---|
| **Shipping tow** (σ/ρ 5,000) | **Measured physical property** — rev 1 | **0.772x Cu = $10.34/kg** | **4.0x** cost · **4.85x** price |
| Sponsor-model-implied (σ/ρ 7,800) | Backed out of revenue arithmetic; not a measurement | 1.205x Cu = $16.13/kg | 2.59x cost · 3.11x price |

Both quoted like-for-like; mixing a DexMat cost against a copper price
inflates the apparent closeness.

## The capacity test — and what the anchor did NOT buy

| Plant | Nameplate | Revenue | Utilisation | |
|---|---|---|---|---|
| **Today** — only row with actuals | 300 kg | $400K | **20.8%** | real data; shows the test's natural range |
| 3 t/yr pilot | 3,000 kg | $5M | 100.0% | **circular** — this identity is how the plant was identified; cannot fail |
| 30 t/yr demo | 30,000 kg | $44M | **557%** | needs 5.6x more than the plant can make |
| 3 kt/yr | 3,000,000 kg | $330M | **219%** | needs 2.2x more |

**557% and 219% do not depend on the anchor** — density cancels in the
ratio to the pilot row, and both were computable in rev 1:
(44/5)/(30/3)/(0.21/1.33) = 5.573; (330/5)/(3,000/3)/(0.04/1.33) = 2.195.
The finding stands; the claim that the anchor produced it does not.

## Findings that survive every basis question

1. **"Long-term $0.001/m" = $1.04/kg** — 479–1,915x below the only
   CNT-*fibre* cost benchmark we hold ($500–2,000/kg), 1/12.8 of copper
   metal. The feedstock-floor intuition is sound but **we have no powder
   price in the record**, and the memo records a plan for an
   exclusive-offtake CNT plant with DexMat as shareholder.
2. **2034 needs 89,773 t/yr of fibre** = **14.5x the two producers named
   in our record** (LG Chem 6,100 + OCSiAl 100 — cited in `factpack.md`
   as evidence CNT powder is industrialised, *not* as a global total),
   and 29.9x the entire 3 kt plant, of which the model builds one.
3. **The October cut is mostly margin:** 17.7x on price vs 3.84x on cost;
   GM 82% → 15.5%. "~99% margins" cannot coexist with $5.11/m at $8.49/ft.
4. **Our own record's copper-parity line is wrong.** `factpack.md` L64
   ("approximate copper parity ($0.04/m at 26 AWG)"); `memo.md` same
   claim, no figures. vs copper **metal** $0.04/m is 2.59x dearer; vs the
   memo's copper **wire** ($0.15/ft) it is 12.3x cheaper. The two
   benchmarks differ 32x and neither is parity — and even the wire
   comparison is bare-conductor-cost vs finished-wire-price.

## HONESTY BOX

- **Part 1 is the solid part.** Native units, and its 1.56x adjustment is
  identical under both readings. Part 2 is not equally solid.
- **The anchor's provenance is unconfirmed on four axes**: which plant,
  cost or price, fully-loaded or variable, which SKU.
- **Only one row of the $/kg table is supplied**; the rest are derived.
- **Corrections carried:** the earlier "implied conductivity 10.14 MS/m"
  was a density-mixing artifact (density-invariant figure: 7,800
  S·m²/kg) — the same error `factpack.md` §TECHNOLOGY was rewritten
  2026-08-09 to stop. And the earlier "REVERSED" parity finding was
  itself wrong; rev 1's 0.772x / $10.34/kg stands.
- **Bare fibre vs finished wire** is unquantified throughout and runs in
  Galvorn's favour.
- **The 144 t/yr scale-up model is not like-for-like** — direct-spun, a
  different route from wet spinning, at 1/21st the scale of the 3 kt plant.
- **SKU mixing remains live.** "$22/m → $4/m" is a third, inconsistent
  cost curve (4.31x / 3.01x the roadmap's steps; 81.8% vs 74.0%).
- **Not modelled:** yield/scrap, insulation and cabling conversion,
  feedstock CNT price path, and the annealing penalty (up to 4x
  conductivity loss ⇒ up to 4x the conductor per equivalent foot).
- **Rev 2 was published before its adversarial pass completed** — a
  sequencing breach of the standing rule, and the reason a wrong parity
  finding was on the live link for a period.

## PENDING DD QUESTIONS

**P1 — decision-gating:**
1. ◐ **TO CASEY, not the sponsor · Where did $1,389.20/kg come from?**
   DexMat, the sponsor, or your own arithmetic — cost or price,
   fully-loaded or variable, which plant? Gates three conclusions here.
   *(Downgraded from ✓ RESOLVED: the value is supplied, not the provenance.)*
2. ● **Is "26 AWG equivalent" a size label or an electrical equivalence?**
   *Moves:* whether the roadmap prices a product that exists.
3. ● **Which gauge are the $2.63/ft and $2.86–3.15/ft SPCW figures, bare
   or finished?** *Moves:* the incumbent baseline directly.
4. ● **How do the 30 t and 3 kt revenue targets work at 557% and 219% of
   nameplate?** *Moves:* the $44M and $330M lines.
5. ● **How does 2034 source 89,773 t/yr of CNT?** *Moves:* the tail branch.

**P2 — score-moving:**
6. ● What do insulation, jacketing and qualification add per foot?
7. ● Is $5.11/m fully-loaded or variable; reconcile "~99% margins."
8. ● Is the Oct-2026 $0.48/ft the same SKU as today's $8.49/ft?
9. ● True global CNT powder capacity.
10. ● **CARRIED (Q8)** October $0.48/ft milestone — targeted for October,
    round closes 2026-09-28. Ask for commissioning status or a customer
    quote at the new price **before** the close.

**P3 — completeness:**
11. ● Feedstock CNT powder cost per kg.
12. ● $/kg and $/ft for the annealed / high-purity space grade.
13. ● Which SKU is the "$22/m → $4/m" line?

## Corrections owed to the existing record

- `factpack.md` L64 and `memo.md`: the copper-parity line is wrong on
  both benchmarks. Flagged, **not yet edited** — load-bearing inside a
  frozen memo, so Casey's call.

## Sources

`factpack.md` rev 3, `sponsor-memo-2026-09.md`,
`sponsor-docs-2026-09/model-workbook-spc-tab.png` (sector incumbent
prices, market volumes, $0.40/ft cost and $0.48/ft price inputs), and the
$1,389.20/kg figure supplied by Casey 2026-09-12.

Deal status unchanged: **borderline pass / watch**, S2 open.
