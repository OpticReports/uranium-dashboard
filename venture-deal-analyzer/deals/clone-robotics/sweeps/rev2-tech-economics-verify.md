# Counter-agent review: rev2 tech and unit-economics sweep (Clone Robotics)

Date: 2026-10-27. Target: `scratchpad/clone/rev2-tech-economics.md` (read in full), tested against the memo transcript (pp.1–5 and 7, read in full), `factpack.md` rev 1.1, `sweeps/`, and primary sources.

**Verdict: APPROVED WITH CORRECTIONS.**
- The evidence is sound and every number reproduces.
- I made 17 corrections. Seven of them pull back overreach against Clone, four pull back overreach in Clone's favour, and six are arithmetic or tag fixes.
- **No panel score moves.** Three forecasts move slightly downward.
- The decision-relevant facts are unchanged by these corrections:
  - Clone's own current life rating is 100K cycles. That is 20x below the V1a bar and 100x below the company's own 10M target.
  - The company's roadmap shows no autonomy milestone before Q3 2027, and its first VLA is planned for Q4 2028.
  - The "1/10 cost" claim shrinks to a ~2–5x hand-level edge.

**How I checked**
- **Arithmetic.** Re-ran `calc/econ.py` and `calc/stress.py`; all tables match. My own checks are in `scratchpad/clone/cv2-calc/cv.py`.
- **Primary sources:**
  - Clone `D8GOK2Ld.js` (cached copy, quotes verbatim).
  - Adaract patents US12416318B2 and US11719263B2, fetched fresh into `cv2-dl/`. US12378979B2 from the cache.
  - Zhang 2024 and Kobayashi 2024 abstracts (OpenAlex cache).
  - Tokyo Tech press-release PDF and Redlarski 2012 PDF.
  - Fetched today: https://www.1x.tech/order, https://www.bls.gov/news.release/ecec.nr0.htm, the cnx-software Jetson article, and two Wuji resellers.
- **Searches:** 2, on Torso 4 pressure or life and on Adaract water, pressure or life data. Both NOT FOUND, consistent with rev2.
- **Prompt injection:** none seen. The patent text's "computer-readable instructions" is boilerplate, not an injection.

---

## 1 · Re-check of every material finding

| # | rev2 finding | Check (source) | Verdict |
|---|---|---|---|
| 1 | Site specs: 500 W pump, "40 SLPM … 100 psi"; Aquajet valve "100 psi … 2.28 SLPM … under a watt … 12mm"; "26 degrees of freedom in the hand, wrist, and elbow"; Jetson Thor; 70 inertial / 320 pressure sensors | Verbatim in `D8GOK2Ld.js` (https://clonerobotics.com/_nuxt/D8GOK2Ld.js) | **CONFIRMED** |
| 2 | Pressure "CONFLICT": memo says 10–40 bar and 2 kW; site says 100 psi and 500 W | Numbers right: 1.45–5.8x the pressure, 4x the power. The site page is the Dec-2024 Alpha spec and is stale (still "Pre-orders available in 2025", factpack §3). The memo says Torso 4 is a "ground-up redesign" and credits Hill with "higher-pressure… muscles" (p.3, p.5). | **SOFTEN.** Retag as a CHANGE: claimed and undemonstrated, but not a contradiction. The memo also partly answers record P1 #6 (operating pressure), as CLAIMED. |
| 3 | "Durability got worse": rated life "fell 6.5x" | The 2023 source says "**Over** 650 000 cycles with 1kg load" (gap-hurdles-verify, Wevolver). That is a censored floor at light load, on the 2023 hand, at unknown test pressure. The 100K is a rating for a different muscle in a different robot at 10–40 bar. | **OVERREACH against Clone.** Say instead: "the operative rating is now 100K, 6.5x below the figure publicised since 2023; the two are not like for like." What matters for the decision is that the gap to V1a (≥2M) went from ~3x to **20x**, and the gap to the company's own 10M target is **100x**. |
| 4 | Adaract patents: "runs on 3,000 psi (207 bar) oil", "no water", ">1M cycles" as intent only, "seep", no burst data | Fresh full text. "3000 pounds per square inch" (12 hits) and "e.g., synthetic fluid, mineral oil-based fluid" are confirmed. The text also says "less than"/"greater than 3000 psi". '979 gives "approximately 1000 to 5000 PSI" and 30–300 PSI against "buckling". '263 says "near 1000 psi" and calls throttling valves inefficient. **"water": 0 hits in all three.** No burst, safety-factor or fatigue data. | **CONFIRMED, with a wording fix.** 3,000 psi and oil are "e.g." examples. "A different muscle" should read "same McKibben class, different design basis (1,000–5,000 psi, oil/synthetic examples, water never mentioned)". |
| 5 | Zhang 2024: normal distribution; fibre load ~3x friction; aramid swap >4x; power-law model | Abstract verbatim (https://doi.org/10.1016/j.rineng.2024.103020). The tests were **underwater**. | **CONFIRMED.** "Fibre load scales with pressure" is rev2's own Chou–Hannaford statics, not a finding from Zhang. Attribute it that way. |
| 6 | Kobayashi 2024: "easily broken in a bent state"; "up to 10,000-times"; "500-fold … 0.5 MPa"; robot test at 0.7 MPa | Abstract verbatim (https://doi.org/10.1109/lra.2024.3455890) | **CONFIRMED.** "Air" is not in the abstract; tag it ANALYST (it comes from the Suzumori lab context). |
| 7 | Tokyo Tech 5 MPa muscle: 7 kN, 15 mm, "5 to 10 times", no cycle data | PDF: "Outer diameter: 15 mm, Maximum contraction force: 7 kN"; 5 MPa; "oil-resistant rubber" | **CONFIRMED.** The release does claim "High durability against impact and vibration" in words, with no cycle data, so the absence of life data holds. |
| 8 | Maintenance table, swap interval (208 h → 26 or 13 days), Weibull | Reproduces exactly | **CONFIRMED, with 3 fixes** (§2, C1–C3) |
| 9 | Stress grid (12.4 / 19.8 / 42.3 → 38–53 months auto "central", >120 months or never for 3PL and hotel) | Reproduces exactly (428.6 months behind the ">120") | **Label overreach** (§2, C4) |
| 10 | Leak release of 25–35 mL per 100 ms at 40 bar | The pump-limited arithmetic is right, but a burst muscle is fed through its own valve | **OVERREACH against Clone** (§2, C5) |
| 11 | Energy: 2.3 kWh pack gives 0.9–3.1 h runtime; heat +14 / 4.8 / 2.9 °C per minute; torso electricity $440–830 per year | Reproduces | **CONFIRMED.** Minor: 2.6–8.6 packs per shift is ~2–8 swaps, not "3–9". The 2.3 kWh pack is Figure's, an assumption, so say so. |
| 12 | Power density: "1 W/g … five times" (Redlarski); system level ~0.05–0.2 kW/kg, "roughly parity" | The PDF quote is confirmed. The system number is wrong on rev2's own inputs (§2, C6). | **FIX** |
| 13 | 1X NEO is $20K; hands "22x2" | https://www.1x.tech/order: "$20,000" Early Access ownership, "$499/mo", "Hands: 22x2" | **CONFIRMED** |
| 14 | "25 DoF in the hand" CONFLICTS with the site | See §2, C7 | **SOFTEN** to a labelling error. Parity stands. |
| 15 | Torso 3 counts: 910 ÷ 182 = 5.0 and 251 − 182 = 69 | Arithmetic is exact | **Numbers CONFIRMED; two inferences overreach** (§2, C8) |
| 16 | Competitor "BOMs" inflated; Wuji at 77–100% of retail | Wuji Hand 2: $14,600 per hand (https://www.roboticscenter.ai/hi/store/product/wuji-hand-2), $19,500 (https://aifitlab.com/collections/robotic-hand/products/wuji-hand-2). **The third URL (mybotshop) now returns 404.** | **CONFIRMED that they are inflated; ratio and band fixed** (§2, C9–C10) |
| 17 | Jetson T5000 went from $2,999 to $4,999 at 1KU | cnx-software, 2026-07-22: "1KU+", $2,999 → $4,999 (+67%) | **CONFIRMED.** The valve-cost squeeze has an internal inconsistency (§2, C11). |
| 18 | BLS figures: $46.89 / $32.82 → 1.43; L&H full-time $27.95 × 2,080 = $58,136; the hotel multiplier is 1.233, the same as "1.23 FTEs" | ECEC June 2026, verbatim | **CONFIRMED.** Whether the 1.23 is used twice is correctly left as a question. |
| 19 | $1B ÷ 10,000 = $100K ASP, 44–53% below list, margins 84% / 81% | Arithmetic is exact | **CONFIRMED.** Soften the "pricing strategy contradiction" (§2, C12). |
| 20 | Autonomy: teleop in Q3 2026, own VLA in Q4 2028, product in Jan 2027 | Memo p.3 verbatim; the gap is 21–23 months | **CONFIRMED, and under-weighted.** It bears directly on hurdle E4 (§4). |
| 21 | Agility: $8,500/mo RaaS, $25K deployment fee, BOM $150K → $75K → $30K; $36K/yr service | VERIFIED in the prior record (sweep-market l.42, S-4/A); the service figure is SECONDARY (sweep-competition E15) | **CONFIRMED (record).** Cobot prices are SECONDARY and were not re-checked here. |
| 22 | Record corrections: 88 lb → 66 lb grip; licence March 2025 → **2026**; "100M cycles" refers to valves; cash $2.3M → $2.5M; Series A $75–100M → $70–100M | `legible-fragments.md` l.26/36/54/57; gap-founders H5 | **CONFIRMED** |

---

## 2 · Corrections (apply before the panel reads rev2)

**Against Clone: overreach to pull back**

- **C1 Parts vs labour.** "Parts are a minority of the cost at ≥0.1 h" is wrong. At 0.1 h, labour is $7.50 against the $9 part, so parts are **55%** of the cost. Labour exceeds parts only above **~7.2 minutes** per swap. Fix exec line 4 the same way.
- **C2 "Breaks at bench or pick rate" (exec line 4).** At the steelman's 0.1 h swaps, 3PL payback is **23.2–27.9 months** (+17–41% on 19.8). It breaks (33.6–111.7 months) only at 0.5 h swaps. Say "degrades with fast swaps, breaks with slow ones."
- **C4 "Combined central" is a stress case, not a central estimate.** It stacks four adverse assumptions:
  - 60% capture on top of the memo's own 85%;
  - 0.5 h per muscle swap;
  - +$50K integration;
  - 1:5 supervision.

  Relabel it "stacked stress." The fair single-factor reads are: auto **13–18 months**, 3PL (4/min) **22–34**, hotel **47–60**.
- **C5 Leak volume.** A ruptured muscle leaks through its own valve, not at full pump flow.
  - The site's Aquajet valve is 2.28 L/min at 6.9 bar. Orifice flow scales with √Δp, giving ~2.7–5.5 L/min at 10–40 bar, or **~5–9 mL per 100 ms**. That is 3–7x below rev2's 25–35 mL.
  - The pump-limited figure applies only to a manifold or hose failure.
  - The injection-risk tier still rises (40 bar = 5.7x HSE's 7 bar anecdotal floor; VERIFIED, record).
- **C7 DoF "CONFLICT".**
  - The memo's own table gives 1X "25", which is 22 + 3 wrist (record E18; 1X order page "22x2").
  - The site's 26 "hand, wrist, and elbow" minus 1 elbow is also 25, hand plus wrist.
  - So the memo uses the same hand-plus-wrist convention for both rows. Its "in the hand" is a **labelling error, not a substantive conflict**.
  - Rev2 also omits Clone's own earlier "**27 DoF** hand" claims (80.lv 2022, Wevolver 2023, Freethink 2023, IE Nov 2025; record c2/c4/E42/E44). Clone has used 25, 26 and 27.
  - The parity conclusion stands, and "matching the human hand" remains unsupported.
- **C8 Torso 3 inferences.**
  - (a) Matching counts show the same kinematic layout and channel count. They cannot show "not new actuation"; the fluid and valves may have changed. Say "same architecture" only.
  - (b) "~69 IMUs for 164 DoF, so many joints are unsensed" is invalid. A link-mounted IMU gives 3-axis orientation, and relative orientation between adjacent links can resolve multi-DoF joints; the site claims "joint-level proprioception (angles and velocities)". Drop it.
- **C12 Pricing-strategy "contradiction".** The memo frames underpricing as a future option at $100K, not as today's list price. Soften the wording. The substance stands: even $100K is 5x NEO's $20K and 7.4x the G1's $13.5K, so "competitors never reach scale" stays REFUTED as literal (record §5).

**In Clone's favour: overreach to pull back**

- **C13 "100x has literature precedent" (adhesive 500–10,000x, aramid 4x).** Kobayashi's multipliers are measured from a baseline that is "easily broken in a bent state". Gains from near zero do not transfer to a 100K → 10M step. Recast as "construction changes can move life by orders of magnitude from a poor base," with no inference about Clone. Also, Kobayashi's bend failure mechanism (fibres shift, the tube protrudes and cracks) is generic and worsens with pressure. Keep the anchor as directionally applicable at 1–4 MPa, numerically non-transferable, rather than "weakened."
- **C6 Power density, both directions.** With rev2's own inputs (≤1 kW mechanical over 10–20 kg), the system figure is **0.025–0.1 kW/kg**, not 0.05–0.2. "Roughly parity" is unsupported: only the hydraulic side was taken to system level, while the electric side stayed at the memo's 0.5 kW/kg actuator figure (motor benchmarks NOT SEARCHED). Recast: "10 kW/kg is actuator-only; no like-for-like system comparison is computable from public data."

**In-favour points rev2 should add (one line each)**

- **Burst claim is plausible.** Adaract-class construction is designed around ~207 bar ("e.g." 3,000 psi), so ≥400 bar burst (10x at 40 bar) is plausible *if* Torso 4 uses it. Running at 5–19% of design pressure would also cut relative fibre load, the factor Zhang finds dominant. This is still not evidence on fatigue life.
- **The durability bar depends on the segment.** At line rate, 100K muscles plus fast swaps leave automotive payback at 12.6–13.1 months. Record V1a (≥2M everywhere) is stricter than the automotive segment needs (§4).
- **Fibre redundancy.** A 5-fibre "muscle" may tolerate one fibre failure (record: ~5.5 fibres per DoF), so replacing at 100K may overstate swaps. This is unknown either way, so ask.

**Arithmetic and tag fixes**

- **C3 Weibull.** "63% fail before 100K" holds only if 100K is the characteristic life η. If it is a *mean*, the share is ~51% at β = 3, and a B10 swap falls at 0.53x the mean, multiplying counts by **1.9x**, not 2.1x. The direction is unchanged.
- **C9 Wuji ratio.** Memo $12–15K against retail $14.6–19.5K is **62–103%**, not 77–100%. Drop the dead mybotshop link.
- **C10 Hand-edge band.**
  - The 1X "two hands = 1.0–1.6x the $20K NEO" argument is price versus BOM (1X may sell below cost).
  - Lean instead on record evidence: Tesla's hand pair is ~20% of a >$60K BOM (~$6K per hand, Counterpoint), and the Morgan Stanley Gen-2 teardown puts hands at ~$9.5K per pair. Both put the memo's $10–20K per hand at ~2–4x too high.
  - Like for like, at $6–10K retail and 40–60% margin, Clone's edge is **~2–5x**, not "~2–3x". There is also a ≤1x tail if the Aug-2026 "high-DoF hands … down to the 10,000-yuan level" trend (record sweep-actuation, 36Kr) covers 20+ DoF hands.
  - The volume mismatch (Clone at 100 units, rivals at thousands) favours Clone. The excluded pump and HPU share disfavours it.
- **C11 BOM squeeze.** Rev2 applies the 306 valves to the $16K torso while itself saying 306 may describe the biped. At 182 channels the bound is ≤**$48–59 per valve**, not $29–35. Whether Thor is inside the $16K is also unknown. Keep it as a DD question.
- **C14 Site pump.** 40 SLPM *and* 100 psi on 500 W would need ~92% wire-to-water efficiency (460 W hydraulic), so these are endpoint ratings, not one operating point (SLPM is also a gas-flow unit). Comparing rev2's 15–21 L/min at 40 bar against it is apples to oranges; the 4x power gap alone carries the point.
- **C15 Leak unknowns tag.** "IP rating, fluid additives, conductivity, detection latency — all NOT FOUND (prior record)" is wrong. The record lists these as DD asks (sweep-actuation DD #6) and never searched them, so tag **NOT SEARCHED / DD**. The same applies to "no service procedure (NOT FOUND)".
- **C16 Minor.** "3–9 pack swaps" should read ~2–8 swaps. The 2.3 kWh pack is an assumption. The 21-month VLA gap is 21–23 months.
- **C17 Kobayashi "air".** Tag ANALYST, since the abstract does not state the fluid.

Rev2's §CONFLICTS list:
- **Keep as written:** #3 (reframed per C3 in §1 row 3), #4, #5, #9–#13.
- **Soften:** #1 and #2 to "CHANGE, undemonstrated"; #6 to "directional, non-numeric"; #7 to a labelling error; #8 to "same architecture".

---

## 3 · What survives (decision-relevant, post-correction)

1. **Life.** The operative rating is **100K** (memo p.3; p.6 fragment). It sits 20x below V1a (≥2M) and 100x below the company's own Q4-2028 10M target. No public 1–4 MPa water-McKibben life data exists (2 searches today, plus rev2's searches).
2. **Maintenance is viable only where duty is low.** It works at line rate with fast swaps, degrades at pick rate, and fails at bench rate with slow swaps. Clone's service design is the unknown that swings the result.
3. **Autonomy by the company's own plan.** Teleop in Q3 2026, the industrial product in Jan 2027, and the first VLA in Q4 2028. No autonomy milestone appears before Q3 2027.
4. **Cost.** The hand edge is ~2–5x, not 9–45x. The torso BOM is ~0.5x Agility's at-scale target, not 1/10. List prices sit at Agility's level, and the 91% margin excludes service.
5. **Energy.** The biped runs ~1–3 h on a Figure-size pack and must reject kW-class heat. The memo's own "a couple of hours" agrees.

---

## 4 · What should move

**Panel scores: none move.**

| Dimension | Current | Proposed | Why |
|---|---|---|---|
| Market | 3 | **3** | Unit economics do not shrink the category. The cobot comparison (6–11 month payback on bounded tasks) confirms the record's "high-mix only" slice. |
| Team | 2 | **2** | More claim-hygiene items (inflated competitor BOMs are "Clone's estimates"; the "25 DoF" label; the $1B / $100K plan inconsistency; the possible 1.23 double use). Offsets: Hill's hydraulics depth, and the memo discloses the 100K rating openly. The net change is not worth half a point. |
| Moat | 2 | **2** | The cost lead was already a CONFLICT. Quantified at ~2–5x on a component worth ~15–20% of BOM, it is real but feature-level. |
| Demand | 1.5 | **1.5** | "Nothing is signed yet" (memo p.4). Paybacks hold only at line rate. |
| Delivery | 1.5 | **1.5, downside lean** | A new, unshown 10–40 bar architecture with a 100K life, plus teleop on the company's own roadmap. Real hardware still exists. If Torso 4 is shown teleop-only in November with no life data at working pressure, take Delivery to **1–1.25 at S2**. |
| Competition | 1.5 | **1.5** | Price parity with Agility rather than undercutting it; cobots win bounded tasks. Already in the record. |
| Deal & price | 1.5 | **1.5** | Not in this sweep's scope. |

**Hurdle ledger (feeds the forecasts)**
- **E4** (autonomous Torso 4 grasp suite by 2027-03-31): **0.30 → 0.22**. The company's own roadmap sets no autonomy target before Q3 2027. Open-backbone post-training is a credible but undemonstrated route.
- **V1a | E4** (≥2M cycles at working pressure, bent): **0.35 → 0.28**. The 100K rating is now legible, the pressure rises to 1–4 MPa, and no public life data exists at those pressures. The 10M date is Q4 2028, eighteen months after the hurdle resolves.
- **Core pair (E4 × V1a):** **10.5% → ~6%**.
- **Proposed segment split (in Clone's favour):** add a commercially sufficient "V1a-line" bar, ≥~500K cycles at line-rate duty with swaps of ≤~7 minutes. This works for the automotive torso even at 100K. Score it at S2, not mid-deal (same rule as the record's methodology note).

**Forecasts**

| Forecast | Current | Proposed | Why |
|---|---|---|---|
| P(priced round ≤24 months) | 0.45 | **0.42** | A Series A lead will diligence exactly these items (100K vs 10M; teleop until 2028; unit economics). This sits inside the panel's raw spread of 0.38–0.45 and above the ledger's 0.39. It is a small shade because most of this was already priced as "(?)" fragments. |
| P(<1x) | 0.85 | **0.85 (hold; 0.86 acceptable)** | The technical news confirms known weaknesses more than it adds new ones. The line-rate steelman offsets slightly. |
| P(≥10x) | 0.025 | **0.020** | The memo's own thesis ("1/10 cost … prevent competitors from achieving scale") fails at its own numbers. 10x needs $7.3–12.7B of exit equity, which roughly requires the company's full 2030 plan ($1B revenue) plus a premium multiple. That plan in turn requires a 100x durability gain by Q4 2028. Interpolating the factpack's EV model gives **~1.02x** (between 0.018 → 1.00x and 0.025 → 1.08x); not re-run. The separate hurdle-ledger forecast (0.011, EV 0.93x) is logged, not averaged. |

**For S2.** The single datum that would reverse most of this: a Torso 4 myofiber life test, n ≥ 10, at the actual setpoint (rev2 P1 #1), together with the service design (P1 #3). Both are cheap for the company to produce, so how the company answers them is itself a datapoint.
