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

---

# PART 3 — THE SPONSOR'S SIX-STEP PLAN, TESTED (2026-09-13)

Casey supplied the plan. Four steps hold, two break — and testing it
**corrected two of this analysis's own findings**.

| Step | Verdict | Binding number |
|---|---|---|
| 1 · beachhead traction | holds, **not on price** | Galvorn is 1.11x the military tier copper-equivalent today. Traction must come from weight/flex/EMI. The price-led beachhead is **3.0% of SPC volume, 9.9% of value** (~$137M/yr) |
| 2 · Series A unlocks lower price | holds | $0.40/ft post-upgrade cost, per the roadmap |
| 3 · undercut beachhead 50%+, **and** compete in broad copper | **half breaks** | Military tier: $0.843/ft vs $0.40 cost = 2.1x markup, 53% GM ✓. **$0.73 tier (97% of volume): needs $0.234/ft = 58% of cost ✗.** Best available there is parity at $0.468/ft — exactly the memo's $0.48/ft target |
| 4 · domination → demand → bigger line | **inverts** | A 30 t line makes **102.8M ft/yr = 1.72x the entire military+space volume** (59.9M ft). 3 kt makes 172x it, **5.1x the whole SPC market**. Beachhead domination cannot fill the demo plant |
| 5 · upgrade from gross profit or raise | holds | Beachhead at 100% share = **$50M/yr at 53% GM = $27M/yr gross profit**. Funds the 30 t ($2–5M); the 3 kt (~$40M) is ~1.5 yrs of it or another raise |
| 6 · 300–500% markup, undercut copper **and aluminium** | **copper yes, aluminium no** | Copper-equivalent $0.076–0.114/ft: beats copper wire ($0.15) by 24–49% ✓, SPCW ✓. But **16–24x copper's metal content** and **173–260x aluminium's**. Aluminium fails by two orders of magnitude |

## Two of my own findings, corrected

Both assumed the memo's "purposefully 20% markup over production cost."
The plan — and the workbook, which holds price flat at **$0.48/ft through
2040** while cost falls to $0.012/ft — says that is not operative beyond
the first step.

- **557%/219% over-capacity — DISSOLVED.** At $0.48/ft the 30 t line runs
  at **89%** of nameplate and the 3 kt at **7%**.
- **"2034 needs 14.5x named CNT capacity" — DISSOLVED.** Used $0.048/m
  instead of $1.575/m: a 32.8x price error. Corrected: **~2,736 t/yr =
  0.44x** the named capacity.

## EV RE-RUN

| Branch | Net | Logged | Revised | Δ |
|---|---|---|---|---|
| Failure / sub-1x | 0.15x | .60 | **.64** | +.04 |
| Specialty niche (Zoltek-class) | 1.75x | .26 | **.24** | −.02 |
| Defense/industrial growth | 5.00x | .10 | **.08** | −.02 |
| Copper-adjacency tail | 15.0x | .04 | **.04** | — |

- **Panel EV 1.65x → 1.52x net** (−8%) · **Red team 2.76x → 2.50x** (−9%)
- P(lose money) 60% → **64%** · P(≥3x net) 14% → **12%** · P(≥10x) **4%**
- **Tail-dependence has flipped.** At tail p=0 the panel tree falls to
  **0.92x** (was 1.05x). Audit finding 9 — "DexMat's EV>1 is NOT
  tail-dependent" — no longer holds. It crosses 1.0x at tail p ≈ 0.5%.

Movement rests on four surviving findings: cost-parity-today refuted; the
price-led beachhead is 3.0% of volume; parity-not-undercut with the 97%
tier until 2028–29; step 3's broad-market leg and step 6's aluminium leg
both failing. The record's two misattributions widen uncertainty but do
not move the mean.

## EXIT SIZES — per $1M at $45M post (2.18% at close)

| Net multiple | model dilution (1.27%) | "realistic" 50–70% (0.87%) | EV tree's implied (~0.42%) |
|---|---|---|---|
| 1x (break even) | $87M | $128M | $265M |
| 1.75x — specialty | $153M | $223M | $461M |
| 3x | $276M | $402M | $833M |
| 5x — defense/industrial | $472M | $690M | $1,429M |
| 10x | $965M | $1,408M | $2,917M |
| 15x — tail | $1,457M | $2,126M | $4,405M |

**NEW P1:** the EV tree's own anchors imply ~**0.42%** exit ownership
(defense branch net 5x at its stated $1.2–1.5B; specialty net 1.75x at
its stated $400–585M Zoltek band) — **3x heavier dilution** than the
factpack's headline 1.27%. One of the two is wrong, and it moves every
exit threshold by 3x.

**Status:** this re-weighting is one analyst's, pending the panel re-run
and a counter-agent pass (running). Not yet written to `ledger.csv`.

---

# PART 4 — EXIT MATH (2026-09-13, 10% carry)

Casey: *"if it's $1.5–4b valuation it's much more than 15x."* Correct. The
counter-agent reached the same conclusion independently and rates it **the
single largest error in the analysis — it swings EV ~10x harder than the
entire probability re-weighting.**

## Two exit-ownership regimes, both live in the record

The EV tree's branch multiples back-solve to **~0.42%** exit ownership
(≈81% cumulative dilution), which no document states. `factpack.md`
L68-70 says **2.18% at close → 1.27%** (model) or **0.65–1.09%**
(realistic 50–70%). **The same $1.2–1.5bn exit is 10x net in the fact
pack and 5x net in the EV tree.** The contradiction originates inside
`memo.md`, which states 50–70% dilution on page 1 and "$400–585M ⇒
1.5–3x net" in its risk section — figures requiring 81–87%.

## A $1.5–4bn exit, at 10% carry

| Exit | EV tree's 0.42% | realistic 0.87% | model's 1.27% |
|---|---|---|---|
| $1.50bn | 5.8x | **11.9x** | 17.2x |
| $2.75bn | 10.5x | **21.7x** | 31.5x |
| $4.00bn | 15.2x | **31.5x** | 45.8x |

The logged tree called the tail **15x**. At the record's own realistic
dilution a $1.5–4bn exit is **11.9–31.5x**.

## Panel EV, every combination (10% carry)

| Vector | 0.42% | 0.87% | 1.27% |
|---|---|---|---|
| logged .60/.26/.10/.04 | 1.54x | 3.05x | 4.39x |
| mine .64/.24/.08/.04 | 1.40x | 2.76x | 3.97x |
| **counter-agent .61/.27/.08/.04** | **1.45x** | **2.88x** | **4.13x** |

The entire probability argument moves EV **±0.14x**. The ownership
assumption nobody wrote down moves it **±2.7x**.

## What is worth negotiating

- Carry 20% → 10%: **+0.27x** EV
- Ownership 0.42% → 1.27% (pro-rata, anti-dilution, A/B participation):
  **+2.68x** EV
- **Pro-rata is worth ~10x the carry point.** Take the carry if free;
  never trade a pro-rata right for it.

## THREE CORRECTIONS I OWE (counter-agent, rev-3 pass)

1. **"The workbook implies a ~40x markup by 2030-31" — WRONG.** The
   workbook holds price *and* cost flat ($0.48 / $0.40 inputs) at a
   constant ~16.7% gross margin 2027→2040. It **is** the 20%-markup
   model at a frozen cost. My 40x spliced the workbook's price to the
   memo's cost roadmap — the same basis error twice over.
2. **The aluminium leg of step 6 — OVERSTATED by an order of
   magnitude.** I compared aluminium *metal content* ($0.00044/ft) to
   Galvorn's *finished price*. Copper's metal→wire conversion is ~32x;
   applying it, plain aluminium wire ≈ $0.014/ft and the gap is
   **5.4–8.1x**, not 173–260x. Still a real gap; not two orders.
3. **Finding 5 (CNT supply) does NOT fully dissolve.** I priced all of
   2034 at $0.48/ft, but the $4.576bn is two legs: SPC $0.566bn **plus
   bare copper wire $4.010bn**, which cannot sell at $0.48/ft when the
   memo's own copper benchmark is $0.15/ft. Correct range: **1.3–4.0x**
   the named CNT capacity, not 0.44x and not 14.5x.

Also: the 3 kt leg of the capacity finding **inverts** rather than
dissolving — the plant reaches only **44.7%** utilisation on the
sponsor's own SPC model in **2040**. Its justification lives entirely in
the unread `Copper Wire Facts` tab. $40M of capex underwritten by a tab
we have not read.

## GATE

**Nothing goes to `ledger.csv` until the dilution question is resolved.**
A re-score 15 days before close, on a pipeline with six same-class
attribution errors and a live 2x ownership contradiction, is the failure
mode the standing verification rule exists to prevent.

**New P1:** which dilution basis is operative — the EV tree's implicit
~81% or the fact pack's stated 50–70%? *Moves EV by 2.0x, every branch
multiple, and the 10x hurdle by $1.4–2.7bn.*

---

# PART 5 — THE ACTUAL POSITION: $100,000 at $35M pre / $42M post

**Correcting a confusing presentation.** Earlier figures were quoted as
*exit* ownership *per $1M* at a $45M post. Casey's 0.25% is *entry*
ownership on a *$100K* cheque. Different quantity, different cheque —
both correct, neither comparable.

- **$100,000 at $42M post = 0.238% at close** (0.25% implies ~$40M post)
- Per dollar this is **~9% better** than the $45M-post terms modelled before
- SPV admin in the record is a flat **~$1,250/person** = 1.25% on a $100K
  cheque, not the 2% of commitment assumed earlier

**Entry ownership is not what pays out.** 0.238% becomes **0.138% /
0.095% / 0.071% / 0.045%** at exit under 42% / 60% / 70% / 81%
cumulative dilution.

## What $100,000 returns, net of 10% carry

| Exit | 42% dil. (0.138%) | 60% (0.095%) | 70% (0.071%) | 81% (0.045%) |
|---|---|---|---|---|
| Specialty $490M · p27% | $619K **6.2x** | $430K 4.3x | $325K 3.2x | $209K 2.1x |
| Defense $1.35bn · p8% | $1,688K **16.9x** | $1,167K 11.7x | $878K 8.8x | $560K 5.6x |
| Tail $1.5bn | $1,874K 18.7x | $1,296K 13.0x | $974K 9.7x | $621K 6.2x |
| **Tail $2.75bn · p4%** | **$3,428K 34.3x** | **$2,367K 23.7x** | $1,778K 17.8x | $1,130K 11.3x |
| Tail $4bn | $4,981K 49.8x | $3,439K 34.4x | $2,581K 25.8x | $1,639K 16.4x |
| **Prob-weighted EV** | **$448K 4.48x** | **$313K 3.13x** | $238K 2.38x | $156K 1.56x |

Branch probabilities .61/.27/.08/.04; failure recovery ≈ $15K.

**The whole position is worth $156K–$448K** depending on the dilution
path — a **2.9x spread** that has nothing to do with whether Galvorn
works. That is why the dilution question, not the probability argument,
is the one to resolve before the 28th.

---

# PART 6 — FOLLOW-ON: +$200K AT THE SERIES A

Modelled on the sponsor's own path: **A = $20M at $100M post**.

- Your $200K buys **0.200%** — against a pro-rata entitlement of **$47,619**
- **You would be buying up 4.2x, not defending**
- Combined after the A: 0.1905% (seed, diluted 20%) + 0.200% = **0.3905%**

**The follow-on is conditional, and that is what makes it work.** No A →
you keep the $200K and only $100K is at risk. At the ledger's own
`p_next_round = 70%`: 30% no A; conditional on reaching it the branches
renormalise to **44.3% fail / 38.6% specialty / 11.4% defense / 5.7%
tail**. Expected capital deployed: **$240K**, not $300K.

| Dilution | $100K only EV $ | EV x | +$200K EV $ | EV x (on $240K exp.) |
|---|---|---|---|---|
| 42% | $448K | **4.48x** | $923K | 3.84x |
| **60%** | $313K | **3.13x** | $646K | 2.69x |
| 70% | $238K | **2.38x** | $492K | 2.05x |
| 81% | $156K | **1.56x** | $323K | 1.34x |

**The re-up roughly doubles the dollars and cuts the multiple by 14%**,
identically at every dilution level. You pay 2.4x the seed price per
share; information is what you get for it.

## The decision threshold

The re-up becomes multiple-accretive once the conditional failure
probability at the A falls below **34.5%** — from the naive 44.3%
carry-forward, a **22% improvement**. That threshold is **34.3–34.6%
across all four dilution scenarios**, i.e. it does not move.

**So dilution decides the size of the prize; it does not decide whether
to re-up.** What decides that is whether reaching the A actually
improves the odds — the October $0.48/ft milestone landing, a converted
anchor-partner order, and a funded 30 t line would plausibly do it.

Marginal dollar: at 60% dilution the extra $140K of expected capital
returns **2.37x** against 3.13x on the seed — lower, still well above 1x.

## Two things that could take the decision away

1. **No right to $200K.** That is 4.2x pro-rata. A well-performing round
   is oversubscribed and the allocation becomes a favour.
2. **Good news raises the price.** At a $150M post your $200K buys
   0.133% not 0.200%, and the $2.75bn outcome falls from $4,862K to
   $3,910K on $300K. The scenario where you most want to re-up is the
   one where it costs most.

**Which makes the pro-rata right the thing to negotiate now**, not at
the A — and worth more than the carry point by a wide margin.
