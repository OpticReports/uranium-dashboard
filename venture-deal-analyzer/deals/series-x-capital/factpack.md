# Fact pack — Series X Capital Fund I (X/Alphabet spinout fund)

Rev 1, 2026-08-15. Asset class: venture FUND position (10-ish Series A
deep-tech checks), not a single deal — fourth vehicle in the ledger.
LP (Casey) is INVESTED; analysis per standing blind convention where
verdict-relevant. Sources: LP-stated terms + independent verification
sweep (2026-08-15, all claims sourced/dated in session log).

## The fund [VERIFIED — strongest sponsor record of any vehicle in this ledger]

- **Series X Capital Fund I, L.P.**, Delaware, CIK 0002052270. Form D
  filed 2025-01-30; Form D/A 2026-03-10: **$541,684,649 fully sold to
  99 accredited investors**, Rule 506(b)/(c), $0 commissions, GP =
  Series X Capital Fund I GP, LLC, signed Gideon Yu, 601 California St
  Suite 700, SF. Related: Series X Capital Affiliates Fund I, L.P.
  (Form D 2025-12-12) and SXC Venus, LLC (CIK 0002097915, Form D
  2026-03-05 — deal-specific SPV, $32,000,000 offering, $0 sold at
  filing, first sale "yet to occur", GP = Series X Capital Fund I GP
  LLC, Gideon Yu director. **Probably the Anori vehicle** — filed two
  weeks before the 2026-03-19 Anori announcement. Codename SPVs do not
  name their target; this is inference, not a finding).
- Manager: Series X Capital Management LLC — SEC **exempt reporting
  adviser** (802-132474), not a registered RIA (normal for VC-only;
  noted). First-time fund; no prior funds.
- Founder/GP: **Gideon Yu** (ex-YouTube CFO through the Google
  acquisition, ex-Facebook CFO, ex-Khosla, SF 49ers co-owner) —
  verified, institutional-grade principal.
- Partnership with X CONFIRMED by X itself (x.company blog "Bringing
  Moonshots to Market", 2026-08-03). TechCrunch (2025-11-02): fund is
  "legally obligated to invest exclusively in companies that spin out
  of X"; **Alphabet deliberately a minority LP** (Teller: more than a
  small LP "would undo the thing we're trying to accomplish").

## LP-stated terms vs public record — THE GAP

- [LP-STATED] "10 Series A investments at a 20% discount to the
  Series A valuation."
- [NOT FOUND] **Neither term appears in any public source** — no press,
  SEC filing, X blog, or fund profile mentions a 20% discount or a
  fixed 10-deal mandate. Arithmetic consistency: Teller expects ~2
  graduations/yr → ~10 deals over a 5-yr period; $541.7M / 10 ≈ $50M
  avg position (Series A leads + reserves — check split). A negotiated
  entry advantage is structurally plausible (fund is often sole/lead
  where X sets terms; YC-deal analogue; the discount would be borne by
  Alphabet's retained stake and spinout employees). **Treat both terms
  as marketing claims until located VERBATIM in the LPA/PPM.**
  **SHARPENED 2026-08-20:** "fund is often sole/lead" cuts BOTH ways and
  is now the stronger argument AGAINST taking the discount at face
  value — if Series X sets the price, there is no arm's-length
  reference for a discount to be measured against. See the
  pricing-role finding below and
  `validation/x-spinout-pricing-2026-08-20.md`.
- [UNKNOWN — REQUIRED, per standing rule ASK]: fees/carry/hurdle, GP
  commit, recycling, selection DISCRETION (may the fund pass on weak
  spinouts, or must it deploy?), what the 20% is contractually measured
  against and who certifies it, reserves-vs-initial split, Alphabet's
  retained rights (ROFR/buyback that could cap exits), allocation
  policy across Fund I / Affiliates Fund / SPVs.

## THIRD-PARTY AUDITED MARK — the first independent valuation of this
## fund we have ever located [VERIFIED + counter-agent CONFIRMED 2026-08-20]

**CAZ Strategic Opportunities Fund** (SEC-registered, CIK 0001984165,
FYE March 31) holds a **$10,000,000 commitment** to Series X Capital
Fund I, acquired **2025-07-03**: $3,575,000 called, $6,425,000 unfunded.
CAZ's $10M is **1.85% of the $541.7M fund**.

Audited fair value, N-CSR for FY ended 2026-03-31 (acc.
0001213900-26-066147): **$3,234,741 on $3,575,000 called = 0.9048x.**

| date | basis | value / called | multiple |
|---|---|---|---|
| 2025-09-30 | NPORT-P | 2,902,400 / 3,075,000 | 0.944x |
| 2025-12-31 | NPORT-P | 2,850,161 / 3,075,000 | 0.927x |
| 2026-03-31 | **N-CSR (audited)** | 3,234,741 / 3,575,000 | **0.905x** |

Counter-agent verification (adversarial, mandatory rule) CONFIRMED the
audited figures by column-footing: the parsed cost column sums exactly
to the printed IT subtotal 42,778,644 and the value column to
60,622,838 — a misaligned parse cannot foot. Corroborated twice more:
the separate Note 2 table repeats fair value 3,234,741 / unfunded
6,425,000, and cost + unfunded = exactly $10,000,000 at both dates.

**Corrections the counter-agent forced (logged so they are not
repeated):**
1. A fourth data point (0.937x from the 2026-03-31 NPORT-P) was
   DROPPED: `2,850,161 + 500,000 capital call = 3,350,161` exactly,
   with unrealized loss identical to 12/31 — it is a stale 12/31 NAV
   rolled forward, not a mark.
2. The NPORT `balance` field is `units=NS` (shares) and the fund "does
   not issue shares"; balance equals audited cost for only **57 of 87**
   CAZ positions. **val ÷ balance is not a valid "x cost" method** and
   is not used here except where the audit confirms it.
3. An apparent $115,420 NPORT-vs-audit discrepancy is a
   preliminary-vs-final artefact, not an anomaly: 68 of 87 positions
   differ, total divergence $32.0M, and fund net assets differ by
   $33.1M (5.0%) for the same date. Series X's gap ranks #35 of 68,
   below the median.

**WHAT THIS DOES AND DOES NOT SHOW — read this before citing it:**

- It does NOT show the portfolio is underperforming. Footnote (c) on
  the Series X row says the position is valued "using the Fund's pro
  rata net asset value... as a practical expedient" — i.e. a
  **pass-through of Series X's own GP-reported NAV.** CAZ expresses no
  independent view of the portfolio.
- The 0.905x is substantially **fee/expense drag ahead of called
  capital** — CAZ discloses exactly this pattern by footnote on three
  other positions. Series X's $340,259 shortfall is 3.40% of the $10M
  commitment over 272 days, annualizing to ~4.6% of committed. That is
  **above** a plain 2%-on-committed estimate, so it cannot honestly be
  called all fees either. **UNDETERMINED without the LPA fee terms and
  a capital account statement** — both non-public (Series X files only
  Form D). Added to the ask list.
- Base rate kills any alarm: of CAZ's 87 positions acquired within 12
  months, **55% are at or below cost and the median multiple is exactly
  1.000x**; only 12% of positions held >12 months are below cost.
  Series X ranks #9 of 87 in a crowded 0.68x–0.96x band. Two CAZ
  positions carry *negative* value.
- **A REFUTED INFERENCE, logged deliberately.** The first read of this
  data was: "no upward remark, therefore the advertised 20% entry
  discount is not producing paper alpha." That is WRONG and was struck
  by the counter-agent. **ASC 820 presumes transaction price = fair
  value at initial recognition** — CAZ's own policy says investments
  "may be valued at acquisition cost initially until the Valuation
  Designee determines acquisition cost no longer represents fair market
  value." **An entry discount is structurally invisible in a mark.**
  The discount claim CANNOT be tested this way, in either direction.
- **CAZ is the SOLE registered holder** of Series X Fund I (EDGAR FTS,
  all forms). No second mark exists to corroborate or break this one.
- Most recent mark available: 2026-03-31. CAZ's 6/30/2026 NPORT-P is
  due ~2026-08-29 — **watch for it.**

## Pipeline track record [VERIFIED, and the core risk]

External-capital X spinouts to date: Malta (alive, slow, "lags
rivals"; $26M Series A 2018 led by Breakthrough Energy Ventures),
Dandelion ($2M seed 2017 led by Collaborative Fund; $40M C led by GV
2024), 280 Earth ($50M B 2024 led by Builders VC + Gideon Yu +
Alphabet — **Yu invested personally pre-fund: conflict/allocation
question**; $40M Frontier offtake), Tidal (independent 2024, led by
Perry Creek Capital), iyO (chiefly an OpenAI-litigation story now),
**Taara + Chorus + Verily Health (Series-X-LED, ALL terms
undisclosed)**, Heritable (FTW/Mythos/SVG named as funders, NO lead
designated by X — do not cite as outside-led), Anori ($26M 2026,
Prologis/Builders VC; X's pages and TechCrunch disagree on whether
Series X co-led), Mineral (WOUND DOWN 2024; John Deere ACQUIRED a
technology suite, Driscoll's licensed).

CORRECTION 2026-08-20: an earlier revision of this file described
**Chorus as the ocean-health moonshot. It is not** — X's blog calls
Chorus "our moonshot for AI-powered supply chain orchestration." The
aquaculture/ocean moonshot is **Tidal**. Also corrected: Anori was NOT
"the ONLY outside-led round" — at least five preceded it. See
`validation/x-spinout-pricing-2026-08-20.md`.

**Pricing-role finding [VERIFIED]:** in the Series X era the fund
LEADS AND PRICES the initial round (Taara, Chorus, Verily Health), and
X says it "often acts as the sole investor in the initial funding
rounds." What X grants is **first look — an access right, not a price
right**; no pricing preference of any kind appears anywhere in the X or
Series X record. This bears directly on the LP-stated "20% discount":
in the base case there is no unaffiliated party setting a reference
price for the discount to be measured against. Pre-fund internal graduates Loon and Makani both shut down even
WITH Alphabet backing.

**Adverse-selection assessment:** historically unambiguous — Alphabet
kept its winners inside (Waymo/Wing/Verily/Intrinsic/Isomorphic; none
of that upside ever flowed to external spinout investors). Post-2023
mitigation is real (strategy change under cost pressure; founder-scale
employee equity; Alphabet minority stakes align incentives) but
UNPROVEN: **zero realized exits; zero marked-up follow-ons led by an
unaffiliated top-tier lead at a disclosed valuation** (Anori closest,
2026-03). X's ~2% internal survival rate pre-de-risks technical
feasibility — but Loon/Makani/Mineral died on unit economics, not
physics.

## EV (parametric, pending docs — hurdle-ledger classification:
## VENTURE-heavy pipeline + one shared E-factor)

Per-check Series A EV ~2.05x gross (bracketed ladder, study
2026-08-15). Portfolio n=10 but correlated via one origin (common
institution/culture/policy) → effective diversification < 10;
P(≥1 winner ≥10x) < the independent 34%.

| Scenario | Gross EV | ~Net (std fees) |
|---|---|---|
| Discount VERIFIED + pipeline ≈ average A | ~2.55x | ~2.1x |
| Discount verified + pipeline 20% worse (adverse selection) | ~2.05x | ~1.75x |
| Discount NOT in docs + average pipeline | ~2.05x | ~1.75x |
| No discount + deep-tech-adverse pipeline | ~1.6x | ~1.4x |

The spread is set by two facts Casey can check and one nobody can yet:
(1) the discount's contractual reality; (2) selection discretion;
(3) pipeline quality — resolves only as follow-ons/exits accrue.
Sponsor quality (Yu, $541.7M institutional close, X endorsement) is
the strongest of the four vehicles in this ledger; pipeline proof is
the weakest.

## Action items (LP)

1. Verify the ENTITY on subscription docs = Series X Capital Fund I,
   L.P. (CIK 2052270) — not a feeder/copycat/SPV; wire details vs
   601 California St. Brand-adjacent names are a classic fraud vector.
2. Locate "20% discount" and "10 Series A" verbatim in LPA/PPM; if
   only in the deck, ask who grants the discount and what Alphabet
   receives.
3. Fees/carry/hurdle/GP commit/recycling; selection discretion;
   Alphabet retained rights; Fund I vs Affiliates vs SPV allocation
   policy (Yu's personal 280 Earth position predates the fund).
