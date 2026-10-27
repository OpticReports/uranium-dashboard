# Clone Robotics — rev 2 sweep: technical and unit-economics claims in the full-resolution Delta4 memo

Date 2026-10-27. Input: `source/memo-transcript.md` (pp. 1–5, 7 read in full; p.6 NOT SUPPLIED, fragments only).
Baseline: `factpack.md` rev 1.1 + `sweeps/` (not redone; cited where reused).
Tags: VERIFIED (primary URL) / SECONDARY / CLAIMED / CONFLICT / NOT FOUND (where searched) / NOT SEARCHED / REFUTED / ANALYST.
Memo = `/home/user/uranium-dashboard/venture-deal-analyzer/deals/clone-robotics/source/memo-transcript.md` (every memo figure is
sponsor/company CLAIMED: "has not been independently verified", p.7).
Prompt-injection log: none seen in any fetched page, PDF or search result (patents, clonerobotics.com bundle, 1x.tech, BLS,
IEEE Spectrum, OpenAlex, resellers).
Status: evidence sweep — needs its counter-agent pass before anything here is acted on (house rule).
Arithmetic scripts: `scratchpad/clone/calc/econ.py`, `calc/stress.py`; chart-ready grid: `scratchpad/clone/rev2-payback-stress.csv`.

---

## EXECUTIVE READ (8 lines)

1. **Pressure is a new architecture, not the one on Clone's site — CONFLICT.** Memo: 2 kW pump, 10–40 bar (1–4 MPa), 306 proportional valves. Clone's live site: 500 W pump "100 psi" (6.9 bar) and an Aquajet valve rated "100 psi". The memo's range is 1.4–5.8x the site's pressure and 4x the pump power; nothing at 10–40 bar has been shown publicly.
2. **Durability got worse on the company's own numbers.** Torso 4 is "100K cycles" (memo p.3), against 650K claimed in 2023 ("at 1 kg load"; that system's pump ran ~10 bar, test pressure unstated). Water-muscle fatigue is driven mainly by fibre load, which scales with pressure (Zhang 2024). So the "10x burst margin" is the right lever, but it is not a life rating. No public hydraulic-McKibben fatigue data at 1–5 MPa was found. The "100M cycles" figure is Adaract's **valves**, not muscles.
3. **Adaract's patents describe a different muscle.** It runs on 3,000 psi (207 bar) **oil** ("synthetic fluid, mineral oil-based fluid"). ">1 million cycles" appears only as design intent. There is no burst figure and no water. Durability claims built on oil designs do not automatically carry over to Clone's water at 10–40 bar.
4. **The $9-muscle steelman holds at line rate but breaks at bench or pick rate.**
   - Automotive line, ~214K–642K contractions/yr: ~210–640 swaps per robot-year, $3.5–30K/yr, payback 12.6–14.9 months against the memo's 12.4.
   - Bench/pick, 0.96–1.92M/yr: ~950–1,900 swaps per robot-year, $16–160K/yr.
   - On 2-shift bench duty the hands need re-muscling every 13 working days. Labour costs more than the $9 part, so the steelman needs swaps of ≤~6 minutes.
5. **Energy only matters for the biped.**
   - Mains-powered torso: <$1.6K/yr of electricity.
   - Biped on a 2.3 kWh pack: runs 0.9–3.1 h at 0.75–2.5 kW. An 8-h shift needs 6–20 kWh (~30–100 kg of cells), and 1–2 kW of heat must leave a human-sized body.
   - "10 vs 0.5 kW/kg" compares the bare muscle with a motor. At system level the gap shrinks to roughly parity.
6. **Hand claims.**
   - "25 DoF in the hand" CONFLICTS with Clone's own "26 degrees of freedom in the hand, wrist, and elbow". That leaves ~22–23 for the hand alone, level with 1X's 22.
   - Torso 3's "182 muscles" is exactly Torso 2's 910 fibres ÷ 5. Its 251 sensors ≈ 182 pressure + ~69 inertial. This is a re-count of the same hardware, not new hardware.
7. **Competitor hand "BOMs" are inflated: the memo's 9–45x headline gap shrinks to ~2–3x like for like.**
   - Wuji's and Sharpa's "BOMs" are 77–100% and ~90% of their retail prices.
   - Two 1X hands at $10–16K each would cost 1.0–1.6x the whole $20K NEO.
   - Apptronik's "$50k hand" was NOT FOUND.
   - Like for like, Clone's $1.1K BOM is ~2–3x cheaper than $6–7K-retail hands with 20–30 DoF, not 9–45x.
8. **Paybacks re-derive exactly (12.4 / 19.8 / 42.3 months) but are fragile.**
   - Central stress (60% capture, central maintenance, $50K integration, 1:5 teleop supervision): 38–53 months for automotive; >10 years or never for 3PL and hotel.
   - The memo's own roadmap puts Clone's first VLA at Q4 2028, 21 months after the Jan 2027 industrial launch.
   - "$1B on 10,000 Clones" implies a $100K ASP, 44–53% below list.

---

## EVIDENCE BY ITEM

### (1) Pressure and durability at 1–4 MPa

**What the memo says (CLAIMED, memo p.2–5)**
- "A 2 kW pump in the abdomen pressurizes water to 10–40 bar, and 306 proportional microvalves meter every muscle stroke" — CLAIMED — memo p.2.
- "the muscles are engineered to survive 10x their operating pressure" — CLAIMED — memo p.2.
- Q3 2026 "Bimanual Torso 4 (100K cycles)"; Q4 2028 "Production Clone rated for 10M cycles" — CLAIMED (company targets) — memo p.3.
- "Adaract's valves are rated for 100 million cycles" — CLAIMED — memo p.5.
- p.6 fragment (low-res lead only): "today's muscles are rated for 100,000 contraction cycles … depends on Adaract's valves and on reaching the 10 million-cycle target" — CLAIMED (?) — memo p.6 fragment.

**What Clone's own site says (VERIFIED, first-party bundle)**
- Pump: "a 500 watt electric pump … able to pump liquid at a 40 SLPM volumetric flow rate and 100 psi rating" — VERIFIED — https://clonerobotics.com/_nuxt/D8GOK2Ld.js
- Valve: "Clone's Aquajet valve technology combines a 100 psi water pressure with a 2.28 SLPM flow rate … under a watt of power consumption … three-way configuration in a miniaturized 12mm design" — VERIFIED — same URL.
- ANALYST:
  - 10–40 bar = 145–580 psi, which is **1.45–5.8x** the site's 100 psi.
  - 2 kW is **4x** the site's 500 W.
  - The Aquajet's 100 psi rating sits **below** the memo's minimum system pressure, so Torso 4's valves are either new, or Adaract's (CONFLICT).
- 2023 hand (prior record): pump "400 L/h at ~10 bar"; muscles "rated >650,000 cycles at 1 kg load" — SECONDARY — https://wevolver.com/article/could-this-lifelike-robotic-hand-be-the-start-of-a-humanoid-future
- ANALYST: on the company's own figures, rated life fell **6.5x**, from 650K to 100K, while the operating range rose from ~10 bar to 10–40 bar. That is consistent with pressure-driven fatigue.

**Adaract patents (VERIFIED, Google Patents full text)**
- US12416318B2 ("Muscle actuator system", the McKibben termination). Statements in the text:
  - the fitting supplies "a high-pressure fluid (3000 pounds per square inch)";
  - "a high-pressure fluid (e.g., synthetic fluid, mineral oil-based fluid)";
  - the intermediate sleeve prevents wear "during repeated (e.g., greater than one million cycles) retraction and expansion";
  - fluid "can leak (or 'seep') into the cavity … of the fitting", which "can result in failed operation";
  - materials are a 20–40 Shore A inner tube, liquid-crystal-polymer primary strands, and aramid/carbon/fibreglass secondary strands.
  - Claim 1 covers a fitting, needle, ferrule, outer sleeve and potting that transfers tensile load.
  - There is **no burst pressure, safety factor or cycle-test result**.
  — VERIFIED — https://patents.google.com/patent/US12416318B2/en
- US12378979B2: "the high-pressure fluid may have a pressure of approximately 1000 to 5000 pounds per square inch"; lower-pressure fluid "approximately 30 to 300 PSI". Claim 1 sets the second pressure "to prevent McKibben muscle buckling". No cycle or durability data. — VERIFIED — https://patents.google.com/patent/US12378979B2/en
- US11719263B2: the pump runs at peak efficiency "near 1000 psi"; "throttling valves may lead to low efficiencies, which impedes practical use of such systems in mobile applications". No fatigue or burst data. — VERIFIED — https://patents.google.com/patent/US11719263B2/en
- ANALYST:
  - Adaract designs for **69–345 bar oil**, while Clone runs **10–40 bar water**. Clone therefore operates at ~5–19% of Adaract's 3,000 psi design point (145–580 psi).
  - That is consistent with "10x margin" only if burst is ≥400 bar at 40 bar operation, a figure nowhere published.
  - Durability from an oil-lubricated design does not transfer automatically to water, which "does not provide the full-film lubrication of oil" (https://www.powermotiontech.com/hydraulics/hydraulic-fluids/article/21883098/water-hydraulics-benefits-and-limitations, SECONDARY, prior record).
  - The patents say nothing about valves, so the "100M cycles" is CLAIMED only.

**Fatigue literature at 1–5 MPa**
- Water-hydraulic artificial muscles (WHAMs) fail by "end of rubber tube breaking and fibre fracture" after redesign — VERIFIED (prior record) — https://iopscience.iop.org/article/10.1088/1361-665X/ac0671
- Zhang, Jia, Zhang, Guo & Gong, *Results in Engineering* 24:103020 (2024):
  - WHAM fatigue life "follows a normal distribution";
  - "the impact of fiber load on the fatigue life of WHAMs is approximately three times greater than that of frictional work";
  - swapping aramid 1414 for aramid 3 raised average life ">4 times";
  - life is captured by a power-law model in fibre load and friction work.
  - Abstract only: full text was 403, so cycle counts and pressures are NOT VERIFIED.
  — VERIFIED (abstract) — https://doi.org/10.1016/j.rineng.2024.103020 (via https://api.openalex.org/works/doi:10.1016/j.rineng.2024.103020)
- ANALYST:
  - Fibre load scales ~linearly with pressure at a given contraction (Chou–Hannaford statics, prior record). Going from 10 to 40 bar therefore raises fibre load ~4x.
  - Under a power law with exponent m, life falls by 4^m. The exponent is unknown from the abstract, so this gives direction, not magnitude.
  - The "headroom" argument ("raise pressure 50% → 50% stronger", memo p.2) trades directly against life.
  - In Clone's favour: a large burst margin is exactly what lowers *relative* fibre load, which is the factor Zhang finds dominant.
- Kobayashi et al., IEEE RA-L 2024: thin McKibbens are "easily broken in a bent state while … very durable in a straight state". Adhesive gave "up to 10,000-times" durability (best case) and "a 500-fold increase under an applied pressure of 0.5 MPa"; a robot test ran at 0.7 MPa. — VERIFIED (abstract) — https://doi.org/10.1109/lra.2024.3455890
- ANALYST:
  - These are thin, low-pressure air muscles, so they are not a direct proxy for Adaract-class construction at 1–4 MPa.
  - Our record's "0.7 MPa failure" anchor is therefore **weakened as a bound on Clone**, but not replaced: no public data exists at 1–4 MPa.
  - In Clone's favour: the 100x improvement needed to go from 100K to 10M has literature precedent in construction changes alone (adhesive 500–10,000x on bent thin muscles; aramid grade 4x).
- Tokyo Tech/Bridgestone 5 MPa hydraulic McKibben: press release gives force (7 kN, 15 mm OD) and "5 to 10 times" strength-to-weight, but **no cycle-life data** — VERIFIED (absence) — https://www.titech.ac.jp/english/news/pdf/tokyotechpr_en_suzumori_20170126.pdf
  - Searched twice for durability data on the Tokyo Tech/Bridgestone 5 MPa muscle: NOT FOUND (web search, 2026-10-27).
- Okayama PBO-sleeve hydraulic McKibben: 28 kN at 4 MPa. Force only, no life data. — SECONDARY (search snippet) — https://www.researchgate.net/publication/242674686_Very_High_Force_Hydraulic_McKibben_Artificial_Muscle_with_a_p-Phenylene-2_6-benzobisoxazole_Cord_Sleeve
- Lead, untraced: a search summary claimed one WHAM study reached ">56,000 cycles at 2 MPa", failing by fibre fracture then tube burst. The source paper was not identified — **NOT VERIFIED, not used**.
- **Burst vs fatigue (ANALYST):**
  - "Survives 10x operating pressure" is a single-load burst margin.
  - Cycle life at working pressure is governed by fibre-load fatigue, abrasion and end-fitting fatigue (Zhang 2021/2024; Adaract's own "seep" failure mode).
  - A 10x burst margin is necessary but tells you nothing about whether 100K, 1M or 10M cycles is achievable.
  - The only life number tied to the new architecture is the company's own **100K**.

**Verdict on (1):** the memo moves the operating point **up** and the rated life **down**. Every high-pressure durability datum public today is either oil (Adaract, Tokyo Tech) or force-only (Okayama). The binding risk, cycle life at working pressure (V1a), is **unchanged or slightly worse**; the record's 0.7 MPa anchor is replaced by a different and larger unknown.

### (2) The steelman: $9 muscles, scheduled swap-out

**Inputs**
- Muscle price: "$9 — per muscle" — CLAIMED — memo p.2
- Count: Torso 3 has 182 muscles — CLAIMED — memo p.3
- Rated life: 100K cycles (Torso 4) — CLAIMED — memo p.3
- Duty bars: 0.96M / 1.92M per hand muscle per year (8 grasps/min on 1 or 2 shifts); 214K/yr on the automotive line (84 s cycle, 2×10 h). Both are reconciled in our record — ANALYST (record) — factpack §4, §11
- Technician rate: $75/h loaded, ANALYST. The floor is BLS private-industry average total compensation of $46.89/h (June 2026) — VERIFIED — https://www.bls.gov/news.release/ecec.nr0.htm
- Swap time per muscle: 0.1 h (steelman: modular cartridge, depot refurbishment), 0.5 h (central), 1.0 h (embedded). All ANALYST; Clone has published no service procedure (NOT FOUND, prior record).
- Muscle mix (central case): 72 high-duty hand/forearm muscles (2 × 36, the 2022–23 hand count, https://wevolver.com/article/could-this-lifelike-robotic-hand-be-the-start-of-a-humanoid-future) plus 110 others at 25% duty. That is ~100 full-duty equivalents. Upper case: all 182 at full duty — ANALYST

**Replacements and cost per robot-year (replace at 100K; ANALYST arithmetic, calc/econ.py)**

| duty | swaps/yr (central – upper) | parts @ $9 | total @ 0.1 h | @ 0.5 h | @ 1.0 h |
|---|---|---|---|---|---|
| Auto line, 1 contraction/cycle (214K) | 213 – 389 | $1.9–3.5K | $3.5–6.4K | $9.9–18.1K | $17.9–32.7K |
| Auto line, 3 contractions/cycle (642K) | 639 – 1,168 | $5.7–10.5K | $10.5–19.3K | $29.7–54.3K | $53.7–98.1K |
| Bench/pick, 1 shift or 4 grasps/min on 2 shifts (0.96M) | 955 – 1,747 | $8.6–15.7K | $15.8–28.8K | $44.4–81.2K | $80.2–146.8K |
| Bench/pick, 8 grasps/min on 2 shifts (1.92M) | 1,910 – 3,494 | $17.2–31.5K | $31.5–57.7K | $88.8–162.5K | $160.5–293.5K |

- Interval: at 480 contractions/h, 100K cycles = **208 operating hours**. That is 26 working days on 1 shift, **13 on 2 shifts**. On the automotive line (42.8/h) it is 2,336 h, ~117 working days — ANALYST.
- Weibull caveat:
  - If "100K" is a characteristic or mean life rather than B10, then at β = 3, 63% of muscles fail **before** a 100K scheduled swap.
  - Holding unscheduled failures to 10% means swapping at 0.47 × 100K, which **doubles** the counts above.
  - Each unscheduled failure is a pressurised-water leak and an unplanned stop — ANALYST.
- Labour scales with swap time; parts are a minority of the cost at ≥0.1 h. The steelman therefore depends on **modular, minutes-scale swaps**, not on the $9 part — ANALYST.

**Payback impact (memo base 12.4 / 19.8 / 42.3 months; ANALYST, calc/stress.py)**
- Automotive line: 12.6 months (steelman) to 13.1 (central) at 1 contraction/cycle; 13.2–14.9 at 3. **The steelman survives.** Cheap replacement is a viable maintenance model at line-rate duty.
- 3PL pick at 4 grasps/min: 23.2 (steelman) to 33.6 (central). At 8 grasps/min: 27.9 to **111.7**. **It breaks** unless swaps are cartridge-fast.
- Hotel (hands only, legs excluded): 57.2 to 158.3. Legs add 1.8–7.2M contractions/yr (prior record, factpack §4/sweep-actuation (b)), so this is a floor.
- Industry service benchmark: Agility's direct-purchase model carries ~$36K/yr of service on a ~$200K robot (~18%/yr) — SECONDARY (prior record) — https://www.therobotreport.com/agility-robotics-reports-18m-revenue-ahead-of-humanoid-spac/
  - ANALYST: the same 18% on Clone's $178K is ~$32K/yr, giving an automotive payback of 178/(172.9 − 32) = **15.2 months**.
- Margin: if Clone carries service under warranty, the central bench case ($44–89K/yr) consumes 25–50% of a $178K list price every year. The memo's "91% gross margin before labor" (p.4) excludes it — ANALYST.

**Leaks (item 2b)**
- Injection injuries: serious cases "over 100 bar"; anecdotal "as low as 7 bar" — VERIFIED (prior record) — https://www.hse.gov.uk/safetybulletins/hydraulic-injection-injury.htm
  - ANALYST: 40 bar is ~5.7x the anecdotal threshold. The record assumed 7–10 bar, so the risk tier rises.
- Failure modes are "seep" at fittings (Adaract) and tube-end breakage and fibre fracture (Zhang 2021) — VERIFIED — https://patents.google.com/patent/US12416318B2/en ; https://iopscience.iop.org/article/10.1088/1361-665X/ac0671
- Release volume (ANALYST):
  - A 2 kW pump at 50–70% wire-to-water efficiency delivers 15–21 L/min at 40 bar, or up to 60–84 L/min at 10 bar if the pump can.
  - Until the leaking channel is isolated that is ~25–35 mL per 100 ms at 40 bar, and 0.25–0.35 L per second.
  - Steelman: a per-muscle valve plus pressure sensor (memo p.2, site's "320 pressure sensors") can detect a pressure drop and isolate in tens of ms, keeping a rupture to tens of mL.
  - Unknowns: IP rating of electronics, fluid additives, conductivity, detection latency — all NOT FOUND (prior record) and DD.

### (3) Energy

- Figure 03: 2.3 kWh, "5 hours of run time" — VERIFIED (prior record) — https://figure.ai/news/f-03-battery-development
- Jetson Thor "in the skull" — VERIFIED — https://clonerobotics.com/_nuxt/D8GOK2Ld.js. Configurable 40–130 W — SECONDARY (prior record) — https://docs.edge-ai-sdk.advantech.com/docs/Hardware/AI_System/Nvidia/Jetson%20Thor/
- Valves "under a watt" each — VERIFIED — same Clone bundle.
- Biped battery life "a couple of hours" (?) — CLAIMED (p.6 fragment, low-res) — memo p.6 fragment.
- **Runtime on 2.3 kWh (ANALYST):**

| case | pump | compute | valves | other | total | runtime | 8-h shift needs | cells @200 Wh/kg |
|---|---|---|---|---|---|---|---|---|
| light (25% pump duty) | 500 W | 100 | 100 | 50 | 750 W | 3.1 h | 6.0 kWh | 30 kg |
| mid (50%) | 1,000 W | 130 | 150 | 50 | 1,330 W | 1.7 h | 10.6 kWh | 53 kg |
| pump flat out | 2,000 W | 130 | 300 | 50 | 2,480 W | 0.93 h | 19.8 kWh | 99 kg |

  - This is consistent with the memo's own "a couple of hours".
  - A hotel shift needs 3–9 pack swaps or charges, or a pack larger than the robot's plausible payload.
  - The hotel payback assumes 1.23 FTEs of work per robot, which compounds the problem.
- **Heat (ANALYST):** in a valve-throttled system nearly all electrical input ends up as heat. Valve throttling alone wastes ~43% (Meller 2017, prior record, https://ecommons.cornell.edu/entities/publication/3fff4a2b-07ad-49c8-95f8-dd33241afdff).
  - 1 kW into 1 / 3 / 5 L of water with no cooling gives **+14 / +4.8 / +2.9 °C per minute**.
  - A kW-class radiator path is needed inside a human silhouette.
  - Festo derates muscle life above 60 °C — SECONDARY (prior record) — https://www.powermotiontech.com/other-technologies/it-looks-piece-hose-its-pneumatic-tensile-actuator
- **Stationary torso (ANALYST):** 1.33 kW × 4,160 h × $0.08–0.15/kWh = **$440–830/yr**; $1.6K at 2.5 kW. Energy is irrelevant to the industrial payback. Electricity price is an assumption — EIA NOT SEARCHED.
- **Power density "10 kW/kg vs 0.5 kW/kg"**
  - McKibben artificial muscles: "power to weight ratio … 1 W/g … five times higher than those offered by electric motors" (pneumatic; Redlarski et al., *Pomiary Automatyka Robotyka* 12/2012) — VERIFIED — https://bibliotekanauki.pl/articles/276425.pdf
  - Hydraulic McKibben "strength-to-weight … 5 to 10 times greater than conventional electric motors and hydraulic cylinders" (force, oil, 5 MPa) — VERIFIED (prior record) — https://www.titech.ac.jp/english/news/pdf/tokyotechpr_en_suzumori_20170126.pdf
  - ANALYST:
    - Scaling ~1 kW/kg from 0.5 MPa air to 4 MPa water gives **~8 kW/kg**, so 10 kW/kg is plausible as an **actuator-only peak at the top of the pressure range**.
    - The figure excludes the pump, its motor, the reservoir and fluid, 306 valves, manifolds, hoses and battery.
    - At the 2023 valve mass of 24 g (https://wevolver.com/article/could-this-lifelike-robotic-hand-be-the-start-of-a-humanoid-future), 306 valves alone are 7.3 kg.
    - Assuming a total hydraulic system of ~10–20 kg delivering ≤~1 kW mechanical, system specific power is **~0.05–0.2 kW/kg**, the same order as electric joints.
    - The 20x headline ratio does not survive at system level. Modern motor kW/kg benchmarks: NOT SEARCHED.
  - Pump flow implied (ANALYST): 2 kW at 40 bar and 50–70% efficiency is 15–21 L/min, below the site's 40 "SLPM". The site and memo specs describe different pumps.

### (4) Hand and torso claims

- "25 DoF — in the hand, matching the human hand" — CLAIMED — memo p.2.
- Clone's site: "With 26 degrees of freedom in the hand, wrist, and elbow" — VERIFIED — https://clonerobotics.com/_nuxt/D8GOK2Ld.js
  - **CONFLICT.** Taking off 1 elbow and 2–3 wrist DoF leaves **~22–23 hand-only** (ANALYST, as in the record).
- 1X NEO hands "22x2" DoF — VERIFIED — https://www.1x.tech/neo
  - The memo's "25" for 1X counts 3 wrist DoF (prior record). Like for like, the hands are at **parity**, so "matching the human hand" is unsupported.
- Torso 3 "164 degrees of freedom, 182 muscles and 251 sensors" — CLAIMED — memo p.3.
  - Torso 2: "910 muscle fibers … 164 degrees of freedom and includes 182 sensors" — VERIFIED (prior record) — https://www.youtube.com/watch?v=gl0GnzPIOl4
  - **Reconciliation (ANALYST):**
    - 910 ÷ 182 = **5.0 exactly**, so a "muscle" is very likely a 5-fibre bundle on one valve channel.
    - Torso 2's 182 sensors were one per channel.
    - Torso 3's 251 ≈ 182 pressure + **~69** inertial/angle sensors, close to the Alpha spec's "70 inertial sensors" (VERIFIED, same Clone bundle).
    - So Torso 3 has the same DoF and channel count as the pneumatic Torso 2, plus joint sensing re-added (the record's ~Apr 2026). It is not new actuation.
    - ~69 inertial/angle sensors for 164 DoF: fewer sensors than DoF, so many joints remain unsensed.
    - The memo's "306 proportional microvalves" (p.2) ≠ 182 channels, so 306 must describe Torso 4 or the biped — ask.
- "~45 N at 10 bar" fingertip — CLAIMED — memo p.2.
  - ANALYST: McKibben statics (θ = 20°, zero contraction) put 45 N at 1 MPa in a single ~2.0 mm-bore fibre. Fingertip force needs a multiple of that in tendon force, so several fibres per flexor are plausible.
  - Quoted at **10 bar**, the bottom of the range, it sits at parity with 1X's 45 N (memo's own table).
- "66 lb" grip = 29.9 kgf = **294 N** (arithmetic) — CLAIMED — memo p.2.
  - Clone's earlier claim was "grip and hold up to 15 pounds" — SECONDARY (prior record) — https://www.newequipment.com/technology-innovations/fun-innovations-friday/blog/55293390/clone-robotics-synthetic-human-is-as-fascinating-as-it-is-frightening
  - That is a different metric (held load vs squeeze force), so not a CONFLICT per se. Test protocol and pressure are unstated.
  - Human grip norms: NOT SEARCHED.
- "0.1 s contraction" — CLAIMED — memo p.2. The site spec is "<50 ms … unloaded" for a single fibre (VERIFIED, same bundle). The memo's figure is 2x slower, presumably loaded or hand-level. Not contradictory, but neither is a measured working point.
- "42 dB" — CLAIMED — memo p.2. Distance, weighting and whether the 2 kW pump was running are unstated. Benchmarks: NOT SEARCHED.
  - ANALYST: 42 dB with a 2 kW, 40-bar pump running would be unusually quiet. Ask for dB(A) at 1 m, pump on.

### (5) Competitor hand "BOMs" (memo: "Competitor bills of materials are Clone's estimates", p.2)

| hand | memo "BOM at 100 units" | best public number | tag / source | read (ANALYST) |
|---|---|---|---|---|
| 1X NEO | ~$10–16K | **whole robot $20,000** (Early Access ownership), $499/mo | VERIFIED — https://www.1x.tech/order | Two hands at $20–32K would be 1.0–1.6x the robot's sticker price. **Inflated**, unless "per pair" and 1X sells far below cost |
| Tesla Gen 3 | ~$11–20K; "24 DoF" | hand ~20% of >$60K Optimus V3 BOM ≈ $12K+ per robot; 22 DoF | SECONDARY (prior record) — https://counterpointresearch.com/jp/insights/blog-tesla-to-leverage-ev-experience-and-chinese-partners-to-ace-humanoids-market-unlock-huge-revenue-potential ; https://driveteslacanada.ca/news/new-tesla-patents-reveal-optimus-v3-hand-human-muscles-tendons/ | Matches only if the memo means per pair; per hand it is ~1.8–3.3x. DoF 24 vs 22: CONFLICT |
| Wuji 2 | ~$12–15K | **retail** $14.6K–19.5K (resellers) | SECONDARY — https://www.roboticscenter.ai/hi/store/product/wuji-hand-2 ; https://aifitlab.com/collections/robotic-hand/products/wuji-hand-2 ; https://www.mybotshop.de/Wuji-Robotic-Hand-v10_1 | "BOM" = 77–100% of reseller retail. **Inflated** |
| Sharpa | ~$45K | **price** ~$50K (LatePost) | SECONDARY (prior record) — https://www.innovaciondigital360.com/industria-4-0/linkerbot-manos-roboticas-china/ | "BOM" = 90% of price. **Inflated** |
| Apptronik | "$50k" (p.2 tile) | no hand price found. Apollo has been demonstrated with PSYONIC's 6-DoF Ability Hand. Apptronik's robot target was "well under US $100,000" (2023); other reports say "<$50,000" for the robot | NOT FOUND (2 searches) / SECONDARY — https://www.robotics.press/companies/psyonic/ ; VERIFIED — https://spectrum.ieee.org/humanoid-robot-apptronik-apollo | Likely a **conflation** of a robot-level target with the hand |
| Linkerbot 25–30 DoF | — | ~RMB 50,000 ≈ **$7K retail** | SECONDARY (prior record) — https://eu.36kr.com/en/p/3239621788565507 | The benchmark the memo omits |
| Unitree Dex5-S | — | $6,350 retail | VERIFIED (prior record) — https://shop.unitree.com/ | Same |

- ANALYST:
  - Clone's $1.1K is a **BOM at 100 units**, while the honest comparators are **retail prices** of $6–7K for 20–30 DoF hands.
  - At ~60% gross margin (Unitree company-level, prior record), competitor BOMs are ~$2.5–3.5K. **Clone's edge is ~2–3x, not 9–45x.**
  - Clone's own 2023 hand was "less than $2,800" in materials (SECONDARY, https://freethink.com/robots-ai/humanoid-robots-clone-hand), so $1.1K is a credible 2.5x step down if valves are included.
  - p.6 says "Clone's entire torso has a $16K BOM, which is about what a single competitor's hand costs". That is circular: $16K is the top of Clone's own 1X estimate.
- **BOM squeeze (ANALYST):**
  - The torso BOM of $16K has unstated volume.
  - Subtract 2 hands ($2.2K) and a Jetson T5000 module: $2,999 at launch, or $4,999 at 1KU after the July 2026 price rise (SECONDARY — https://www.hostzealot.com/blog/news/nvidia-unveils-jetson-agx-thor-a-3499-brain-for-robots ; https://www.cnx-software.com/2026/07/22/nvidia-increases-the-price-of-jetson-modules-and-devkits-by-up-to-101/).
  - That leaves **$8.8–10.8K** for 306 valves, the 2 kW pump unit, 251+ sensors, 4 depth cameras, skeleton, skin and wiring.
  - Even with nothing else, valves would have to cost **≤$29–35 each**. Plausible only at volume for in-house valves; not credible at 100 units.

### (6) Unit economics

**Re-derivation (ANALYST arithmetic; memo inputs CLAIMED, memo p.4)**
- Automotive: 2 × $101,700 = $203,400 × 0.85 = $172,890 → $178K / $172,890 = **12.4 months** ✓.
- 3PL: 2 × $63,500 × 0.85 = $107,950 → **19.8 months** ✓.
- Hotel: 1.23 × $58,000 × 0.85 = $60,639 → $214K → **42.3 months** ✓.
- Gross margin: (178 − 16)/178 = 91.0%; (214 − 19.25)/214 = 91.0% ✓.
- Loaded rates:
  - BLS private-industry multiplier = $46.89 / $32.82 = **1.43**; leisure & hospitality full-time total comp $27.95/h × 2,080 = **$58,136** — VERIFIED — https://www.bls.gov/news.release/ecec.nr0.htm
  - ANALYST: the hotel $58K matches BLS. But $22.62 × 2,080 × m = $58K implies m = **1.233**, the **same 1.23** as "FTEs replaced". This is either a coincidence or a double use.
  - If one robot replaces 1.0 FTE, the hotel payback is **52 months**.
- Autonomy: the memo's own roadmap lists "low-level joint control and teleoperation" for Q3 2026 and "Clone's first VLA model" for **Q4 2028**. The industrial torso is "available to customers" in **Jan 2027** — CLAIMED — memo p.3.
  - ANALYST: the 12-month payback assumes autonomous work ~21 months before the company's own VLA date, unless open backbones fill the gap, which is undemonstrated (no autonomous grasp, record §2).
- **Stress grid (months; ANALYST, calc/stress.py; CSV in scratchpad):**

| | memo | 60% capture | +$25K integ. | +$75K integ. | 1:5 teleop (onshore) | 1:1 teleop (onshore) | 1:1 offshore ($30K) | combined steelman¹ | combined central² | combined bear³ |
|---|---|---|---|---|---|---|---|---|---|---|
| Auto line (1 contr/cycle) | 12.4 | 17.5 | 14.1 | 17.6 | 16.2 | never | 18.9 | 18.9 | **38.3** | 90.8 |
| Auto line (3 contr/cycle) | 12.4 | 17.5 | 14.1 | 17.6 | 16.2 | never | 18.9 | 20.0 | **53.0** | never |
| 3PL pick (4/min) | 19.8 | 28.0 | 22.6 | 28.1 | 25.9 | never | 44.5 | 36.5 | **>120** | never |
| 3PL pick (8/min) | 19.8 | 28.0 | 22.6 | 28.1 | 25.9 | never | 44.5 | 47.7 | **never** | never |
| Hotel biped (hands only) | 42.3 | 60.0 | 47.3 | 57.2 | 55.4 | never | 108.2 | 93.7 | **never** | never |

  - ¹ 75% capture, steelman maintenance (0.1 h swaps), +$25K integration, 1:10 supervision.
  - ² 60% capture, central maintenance (0.5 h), +$50K, 1:5.
  - ³ 60%, central maintenance × 2.1 (B10 replacement), +$75K, 1:3.
  - Teleop operators are costed at the replaced worker's loaded rate unless marked offshore.
- **Benchmarks**
  - Agility RaaS: "$8,500 per robot per month", deployment fee ~$25,000, 5-year life; BOM $150K at launch, ~$75K at 1K/yr, ~$30K at 10K/yr (management illustrations) — VERIFIED (prior record, S-4/A) — https://www.sec.gov/Archives/edgar/data/2074973/000121390026105334/ea0297114-05.htm
    - ANALYST: that is $102K/yr = **$24.5 per robot-hour** on 2 shifts, and a 5-year TCO of $535K including service.
    - Clone's 5-year TCO is $228K (auto, central maintenance) to $400K (3PL, central).
    - **Clone's list price is not the problem**: if the robot works and lasts, it is cheaper per hour than Agility. The problems are productivity, autonomy and durability.
    - Clone's $16–19.25K BOM is ~0.53–0.64x Agility's own at-scale $30K target, not 1/10.
  - Cobot cell: UR5e-class arm $30–48K; complete machine-tending cell $58–97K; the arm is ~40–50% of deployed cost — SECONDARY (vendor/reseller guides) — https://grabarobot.com/blog/universal-robots-price-guide-2026/ ; https://standardbots.com/articles/universal-robot-price
    - ANALYST: on a bounded 2-shift 3PL-type task at 85% capture, a cobot cell pays back in **6.4–10.8 months**, beating the torso's 19.8.
    - Clone wins only on high-mix work a cobot cannot do, which is exactly where autonomy is undemonstrated.
- **Internal inconsistencies in the memo (ANALYST from memo p.1, p.4)**
  - "$1B in sales on 10,000 Clones" = **$100K/robot**, which is 44% below the $178K torso and 53% below the $214K biped. At $100K, gross margin is 84% / 81%, not 91%. The memo calls this "conservative"; it is a different price plan.
  - The TL;DR's "pricing strategy … prevent their competition from ever achieving economies of scale" sits against list prices of $178–214K at 91% margin. Those are 9–11x 1X NEO's $20K (VERIFIED, https://www.1x.tech/order) and ~13–16x Unitree G1's $13.5K (prior record). The memo prices at Agility's level, not below rivals.
  - The biped BOM of **$19,250** matches the CEO's earlier "<$20K" (record). That figure was a **cost**, not a price, consistent with the record's treatment. The sale price is ~11x it.

---

## CONFLICTS WITH OUR RECORD (factpack rev 1.1 / sweeps)

1. **Operating pressure.**
   - Record: Clone's pump/valve ratings 0.69–1.0 MPa (100–145 psi); 2023 "~10 bar"; site pump and Aquajet valve "100 psi" (VERIFIED today, https://clonerobotics.com/_nuxt/D8GOK2Ld.js).
   - Memo: **10–40 bar (1–4 MPa)**, p.2.
   - CONFLICT: the memo's floor is the record's ceiling.
2. **Pump power.** Record/site: 500 W. Memo: **2 kW**. CONFLICT. The memo's flow at 40 bar (15–21 L/min) is also below the site's 40 "SLPM".
3. **Cycle life.**
   - Record carried 650K (2023 press, "at 1 kg load") as Clone's best figure, with "100,000(?)" from an illegible fragment.
   - Full-res memo: Torso 4 = **100K** (p.3).
   - The company's current rating is 6.5x below the 2023 claim. CONFLICT (now legible).
4. **"100 million cycles" attribution.**
   - Record (gap-founders H5, blurred read): "muscles are rated for 100 million cycles".
   - Full-res memo: "Adaract's **valves** are rated for 100 million cycles" (p.5). Record CORRECTED.
5. **Fluid.** Memo: water. Adaract muscle patent: "synthetic fluid, mineral oil-based fluid" at 3,000 psi (https://patents.google.com/patent/US12416318B2/en). NEW CONFLICT between the memo's architecture and the licensed IP's design basis.
6. **Kobayashi anchor.**
   - Record used "bent McKibbens failed at 0.7 MPa" as the durability bound.
   - At 1–4 MPa with Adaract-class construction that anchor is not the right comparator, so it is **weakened**, not refuted.
   - No public 1–4 MPa life data exists. The new bound is the company's own 100K.
7. **Hand DoF.** Memo "25 DoF in the hand" vs site "26 degrees of freedom in the hand, wrist, and elbow" (VERIFIED). CONFLICT. Record's ANALYST ~20–23 hand-only stands.
8. **Torso counts.**
   - Record: Torso 2 = 910 fibres, 182 sensors, 164 DoF.
   - Memo: Torso 3 = 182 muscles, 251 sensors, 164 DoF.
   - Reconciled (ANALYST): 182 channels × 5 fibres = 910, and 251 ≈ 182 + 69. This is a unit change, not new actuation. Supports the record's "hardware lags spec" (182 of the Alpha's 320 pressure sensors).
9. **Tesla hand DoF.** Memo "24"; record 22 (+3 wrist/forearm). Minor CONFLICT.
10. **Key-facts tiles.**
    - Record's fragment read "88 lb (?)" and "89 (muscles?)".
    - Full-res memo: **66 lb** grip and **$9** per muscle; no "89".
    - Record items citing "88 lb" (sweep-actuation DD #12) are CORRECTED.
11. **Licence date (outside scope, flag only).** Record (blurred) "March 2025"; full-res "March **2026**" (p.5).
12. **Cash and Series A (outside scope, flag only).** Fragments "$2.3M(?)" and "$75–100M(?)"; full-res "$2.5M" and "$70–100M" (p.1, p.5).
13. **"~1/10 the cost".** Record CONFLICT **stands and is reinforced**:
    - the memo's own hand comparators sit at 77–100% of rivals' retail prices, and the 9–45x hand gap is ~2–3x like for like (item 5);
    - torso/biped BOMs of $16–19.25K vs Agility's $30K at-scale target is ~0.53–0.64x;
    - vs BofA's China 2030 <$17K it is ~0.94–1.13x (record).

## NOT SEARCHED / NOT REACHED (budget or access)

- Full text of Zhang et al. 2024 (*Results in Engineering*): 403 at ScienceDirect, so cycle counts and pressures are unread. Klute & Hannaford 1998 PDF: 503.
- Hydraulic McKibben fatigue at 1–5 MPa (Tokyo Tech/Bridgestone, ImPACT): searched twice, NOT FOUND. Not searched in Japanese-language or J-STAGE sources.
- Adaract product brochure ("Download Product Information"): not fetched. Adaract's robotics page has no pressure, life or HPU specs (VERIFIED absence, https://adaract.com/industries/robotics).
- Modern electric-motor or actuator power density (kW/kg): NOT SEARCHED.
- Human grip and fingertip-force norms: NOT SEARCHED.
- Hydraulic pump and valve noise benchmarks (for 42 dB): NOT SEARCHED.
- BLS OOH technician wage: 403. The technician rate is ANALYST.
- Industrial electricity price (EIA): NOT SEARCHED (ANALYST $0.08–0.15/kWh).
- Humanoid productivity vs human workers (for the capture or speed haircut): NOT SEARCHED. The 60–75% capture stress is ANALYST.
- Humanoid battery pack energy density: NOT SEARCHED (200 Wh/kg assumed).
- Sharpa official price: one search, no result (relies on record SECONDARY). Wuji price: resellers only. PSYONIC robotics price: NOT FOUND.
- Tesla Gen 3 hand cost: primary NOT SEARCHED beyond the record's Counterpoint estimate.
- Pressure-equipment and safety rules at 40 bar (EU PED, ISO 4413 applicability): NOT SEARCHED.
- Memo p.6 (Risks): NOT SUPPLIED. The battery-life and durability sentences rest on low-res fragments.

## NEW DD QUESTIONS — RANKED (rev 2; P1 decision-gating / P2 score-moving / P3 completeness)

### P1
1. ○ (C) **Myofiber life test at Torso 4 conditions.** Cycles-to-failure, n ≥ 10, at the actual working pressure (10 / 20 / 40 bar), load, stroke %, bend radius, water temperature. State whether "100K" is B10, mean or characteristic life (Weibull β), give the failure modes, and show how the 650K (2023) became 100K. *Moves:* V1a (≥2M at working pressure), the maintenance model, all paybacks; Traction-delivery.
2. ○ (C) **What runs in Torso 4 today**: fluid (water or air?), measured pressure setpoints, pump model and measured electrical draw. Are the 306 valves Aquajet (rated 100 psi) or Adaract's? *Moves:* the pressure CONFLICT, V1a, the energy case, G1 claim hygiene.
3. ○ (C) **Service model and warranty**:
   - minutes per muscle swap, and whether the hand/forearm is a hot-swap cartridge;
   - expected swaps per robot-year at the pilot's duty, and who pays;
   - spare-muscle price to the customer;
   - leak detection-to-isolation time (ms), and the IP rating of electronics near water.
   *Moves:* paybacks (3PL / bench break-even), gross margin, V2.
4. ○ (C) **Autonomy at the first pilot**: will the Jan-2027 Industrial Torso run tasks autonomously or under teleop? Operator:robot ratio? Which model runs it before Clone's own VLA (Q4 2028)? *Moves:* E4, the 12-month payback, Traction-demand.
5. ○ (C) **Source and basis for every competitor "BOM"** (1X, Tesla, Wuji, Sharpa, Apptronik "$50k"): per hand or per pair? Why do they sit at 77–100% of public retail prices? What is Clone's own hand BOM at 100 / 1K / 10K units, line by line (muscles, valves, sensors, share of pump)? *Moves:* Moat (cost-lead CONFLICT), G1.

### P2
6. ○ (C) **Adaract in the robot**: which Adaract components (muscle termination, valves, HPU) does Torso 4 or the biped use? Adaract's patents specify 3,000 psi oil. Is there water-service life data for those designs, and burst test data behind "10x operating pressure"? *Moves:* V1a, Moat / freedom to operate.
7. ○ (C) **Biped energy and heat**: pack kWh and mass, measured average W on a housekeeping task, runtime, swap or charge plan, the heat-rejection path for 1–2 kW, steady-state water temperature. *Moves:* hotel payback, the Sept-2027 biped hurdle.
8. ○ (C) **Pricing reconciliation**: is the 2030 target $100K ASP (from $1B / 10,000) or list $178–214K? What do "1.23 FTEs replaced" and the 1.233 loaded multiplier mean? Integration or deployment fee? A RaaS option? *Moves:* the EV revenue path, Deal & price narrative.
9. ○ (C) **DoF and channel accounting**:
   - hand-only DoF (memo 25 vs site 26 incl. wrist and elbow);
   - is a "muscle" a 5-fibre bundle;
   - valves and pressure sensors per hand on Torso 4;
   - which robot the "306 valves" describes.
   *Moves:* the "hand leads" thesis, G1.
10. ○ (C) **Torso BOM volume basis**: at what volume is "$16K"? Does it include the Jetson T5000 ($3–5K)? Valve unit cost? *Moves:* the 91% margin claim, cost moat.

### P3
11. ○ (C) Test protocols for "66 lb grip" (dynamometer? pressure?), "~45 N at 10 bar", "0.1 s contraction" (loaded?), "42 dB" (dB(A) at 1 m, pump on?). *Moves:* comparison table credibility.
12. ○ (C) Adaract valve "100 million cycles": test conditions, and is a proportional-valve "cycle" a full stroke? Independent test house? *Moves:* the valve-wear term in the maintenance model.
13. ○ (C) Injection-risk and pressure-safety assessment at 40 bar (HSE anecdotal threshold 7 bar); fluid additives and microbial control; freeze protection. *Moves:* certification timeline, hotel/home GTM.
