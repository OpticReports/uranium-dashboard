# Clone Robotics: actuation sweep. Does water-hydraulic Myofiber hold up at production scale?

Sweep date 2026-10-27. Scope: Myofiber physics, durability, leaks/safety, the history of hydraulic and fluidic actuation, the cost claim, and the steelman.
Tags: VERIFIED (primary URL) / SECONDARY / CLAIMED (company or sponsor only) / CONFLICT / NOT FOUND / REFUTED / ANALYST.
Memo numbers marked (?) are UNREAD (see BRIEF.md). No conclusion below rests on them; they appear only as scenarios.
Prompt-injection log: none seen in any fetched page or search result.
Status: this is an evidence sweep and has not had its counter-agent review. A counter-agent must check it before anyone acts on it (house rule).

---

## 1. Executive read (8 lines)

1. **The physics works but is not new.** Myofiber is a McKibben-type braided fluidic muscle. The design is 60+ years old and well studied. Force falls toward zero at full contraction; Festo's datasheet says the "most effective" range is <9% contraction, out of a 20–25% maximum. Friction hysteresis is high: the fabric-muscle paper reports <1% for its own design and says that is >10x less than McKibben. Clone's headline numbers (1 kgf from a 3 g fibre, <50 ms, >30% contraction) are physically plausible, but they are **unloaded** peaks, not working-point figures.
2. **The biggest flag: water hydraulics looks like roadmap, not something shown.** Torso 2 (Dec 2024) and Protoclone (Feb 2025) ran on **compressed air**, according to Circuit Digest, Futura (11 Jun 2026) and humanoid.guide. Other outlets call them "water-powered" (CONFLICT). The quoted pump spec, "500 W, 40 SLPM at 100 psi", has two problems. SLPM is a gas-flow unit. And 40 L/min at 100 psi is 460 W of hydraulic power, which a 500 W pump could only deliver at ~92% wire-to-water efficiency. That is not credible as one operating point. Check on the Torso 4 Zoom call which fluid is actually in the robot.
3. **Durability is the binding constraint, and the arithmetic is unforgiving.** A hand muscle at 8 grasps/min sees 0.96M cycles/yr on one shift, 1.92M on two shifts, and 4.03M at 24/7. Against that:
   - the memo's 100k (?) rating lasts **26 single-shift days**;
   - the 650k figure from press lasts **0.34 yr on two shifts**;
   - the 10M target (?) would last **5.2 yr on two shifts, or 2.5 yr at 24/7**, which is enough if it is reached.
   The best public commercial thin-McKibben figure is **>1M cycles** (s-muscle Co.), and thin muscles run in a *bent* state fail far sooner (Kobayashi et al. 2024). With dozens to hundreds of fibres per robot, the *first* failure is expected at about 3–45% of characteristic life (Weibull arithmetic, β 2–5).
4. **Energy is the second constraint.** Valve throttling alone wastes on average 43% of input power (Meller 2017). Battery-to-work efficiency is about 18–27% for the hydraulic chain and about 5–8% for the pneumatic chain the demos appear to use (ANALYST). The 500 W pump on its own is more than Figure 03's *whole-robot* average of about 460 W (2.3 kWh over 5 h). At a 0.7–1.3 kW total draw, a 2.3 kWh pack runs **1.7–3.3 h**. Clone has shown no untethered full shift.
5. **Boston Dynamics' stated reasons for dropping hydraulics** were that electric actuators had become "sufficient" in responsiveness and strength, plus stronger joints, more range of motion and a "product". Leaks and maintenance are *secondary* commentary, not BD's own words. Fluidic actuators have a weak commercial record:
   - Shadow moved its hand to motors.
   - Sarcos had a hydraulic exoskeleton, went electric, then left hardware altogether (2023).
   - Sanctuary uses hydraulic hands and ousted its CEO and cut ~30 staff in Nov 2024.
   - Festo and Bridgestone fluidic muscles have stayed niche or pilot-scale.
6. **The cost thesis targets the right line item but overstates the moat.** Actuators are 40–60% of a humanoid bill of materials (secondary), so this is where savings would matter. But hydraulics adds a pump, a valve and pressure sensor per channel, manifolds, a reservoir and filtration. Competitors are already cheap: Chinese motor hands retail at about ¥2,999–8,800 (~$420–1,230, 6–7 DoF), and Unitree's R1 humanoid at ¥39,900 (~$5.6–5.9k). The memo's ~$1.1K (?) hand figure is a *bill of materials*, while the competitor figures are *prices*, so the comparison is not like for like.
7. **The steelman is real.** Advantages backed by evidence:
   - inherent compliance and backdrivability (Clone claims both);
   - power-to-weight of hydraulic McKibben muscles 5–10x that of motors (Tokyo Tech/Bridgestone, 5 MPa oil);
   - static holds that can cost near-zero energy with valves closed (ANALYST);
   - built-in force sensing from pressure;
   - very cheap muscle parts;
   - many human-like DoF (26–27 in the hand, claimed).
8. **Casey's crux, from the actuation side.** Clone *claims* muscle-level force feedback from 320 pressure sensors plus 70 inertial sensors (CLAIMED, via press). I found no evidence of fingertip tactile or slip sensing (NOT FOUND); for comparison, Figure 03 claims 3 g fingertip sensitivity. "No sensor feedback" therefore looks **wrong for grip force** (pending confirmation) but **unproven for touch**. Pressure-based force estimates also carry the McKibben friction error.

---

## 2. Evidence by question

### (a) Physics of McKibben / Myofiber muscles

**What Myofiber is**
- Clone's Myofiber works on the same principle as a braided fluidic (McKibben) muscle: a mesh tube that contracts when filled with pressurised fluid. — SECONDARY — https://humanoid.guide/?p=19391
- New Atlas (6 Oct 2022) calls it Clone's own development of a McKibben-type muscle. In an early version the bladder fluid was acetaldehyde, boiled by a heater (6.6x atmospheric pressure at 70 °C). — SECONDARY — https://newatlas.com/robotics/clone-robotics-realistic-hand/

**Clone's own numbers**
- Clone's spec target: "less than 50 ms with a bigger than 30% unloaded contraction and at least a kilogram of contraction force for a single, three gram muscle fiber". The page claims Myofiber meets it, but publishes no measured data. — CLAIMED (primary page) — http://www.clonerobotics.com/android/
- Clone's research page currently reads only "We are currently researching, page will be available soon". There is no datasheet, paper or test data. — VERIFIED (absence) — http://www.clonerobotics.com/research/

**Contraction limits and force–length**
- Festo DMSP is the most mature commercial braided muscle. Its datasheet (2022/04) gives:
  - max permissible contraction of 20% (5 mm size) and 25% (10/20/40 mm sizes);
  - "The most effective operating range is when the contraction is less than 9%";
  - operating medium "Compressed air to ISO 8573-1:2010"; it is not rated for water;
  - 0–6 or 0–8 bar, and –5 to +60 °C.
  — VERIFIED (Festo datasheet, mirror) — https://motionworld.com/assets/festo-dmsp-fluidic-muscle-datasheet.pdf
- A fluidic muscle's force "drops toward zero as it approaches full contraction", whereas an electric joint holds rated torque across its range. Mammalian muscle contracts 20–40%; Myofiber claims 30%; DMSP manages 25%. — SECONDARY — https://humanoid.guide/?p=19391
- ANALYST: Clone's ">30% unloaded contraction" is the zero-force end of the curve. Usable stroke under load is materially less: Festo's own advice is <9% for effective force.

**Plausibility of 1 kgf from a 3 g fibre**
- Standard McKibben statics (Chou & Hannaford 1996, IEEE T-RA 12(1):90–102): F = (πD²P/4)·(3cos²θ−1)/sin²θ.
- Worked example: a 4 mm fibre at 100 psi (0.69 MPa) with a 20° braid angle gives about 122 N (~12 kgf) at zero contraction.
- So 1 kgf from a ~1 mm-class fibre is plausible, not extraordinary.
- Equation from the standard literature; full text not fetched (DTIC 403). — ANALYST — https://apps.dtic.mil/sti/pdfs/ADA299458.pdf (citation only)

**Pressure range**
- Tokyo Tech/Bridgestone (press release, 26 Jan 2017): conventional McKibben muscles run at 0.3–0.6 MPa of air. Their hydraulic McKibben runs at 5 MPa: 15 mm OD, 7 kN maximum force, 30% maximum contraction. — VERIFIED — https://www.titech.ac.jp/english/news/pdf/tokyotechpr_en_suzumori_20170126.pdf
- Clone's reported pressure is 100 psi (6.9 bar; Interesting Engineering 6 Dec 2024) or 145 psi (10 bar; New Atlas 2022). — CONFLICT (secondary vs secondary) — https://interestingengineering.com/innovation/clone-alpha-humanoid-robot-unveiled-poland ; https://newatlas.com/robotics/clone-robotics-realistic-hand/
- ANALYST: that is roughly 1/5 to 1/7 of the Tokyo Tech hydraulic muscle's pressure, so Clone gives up much of the hydraulic force-density advantage in exchange for safety and thin walls.

**Hysteresis**
- Naclerio & Hawkes (IEEE RA-L 5(2), Apr 2020) report that their fabric muscle has "less than 1% hysteresis, over an order of magnitude less than that of McKibben muscles". They also say McKibben muscles are "limited by its hysteresis, stiffness, fatigue life [Klute & Hannaford 1998]". — VERIFIED — https://par.nsf.gov/servlets/purl/10221275
- Hosovsky et al. (MM Science Journal, Mar 2018, DOI 10.17973/MMSJ.2018_03_201746) measured Festo DMSP-5 (5 mm × 130 mm):
  - maximum hysteresis width 5.26 / 5.19 / 5.07 mm across the test frequencies, and rate-independent;
  - ANALYST: 5.26/130 = **4.0% of length, about 20% of the 20% stroke**.
  — VERIFIED — https://www.mmscience.eu/journal/issues/march-2018/articles/preliminary-investigation-of-static-and-dynamic-hysteresisof-dmsp-5-fluidic-muscle/download
- Hysteresis in PAMs is attributed mainly to bladder–braid and braid–braid friction and to bladder deformation (secondary summary of Chou & Hannaford). — SECONDARY — https://softroboticstoolkit.com/publications/measurement-and-modeling-mckibben-pneumatic-artificial-muscles

**Bandwidth and response time**
- Festo DMSP: "Frequency up to 150 Hz" for strokes <1 mm (vibration duty). — VERIFIED — Festo datasheet (above)
- The fabric muscle fully contracts in 0.03 s (30 ms) at lengths over 60 cm. — VERIFIED — https://par.nsf.gov/servlets/purl/10221275
- Kothera et al. (J. Mech. Des. 2009) note that "reducing the internal air volume can lead to higher bandwidth operation". — VERIFIED — https://sites.utexas.edu/sirohi/files/2017/07/014_kothera09_jmd.pdf
- Clone says air compresses and causes lag in fast balance corrections, which is why it plans to move from pneumatics to hydraulics. — CLAIMED (via secondary) — https://humanoid.guide/?p=19391
- ANALYST: the <50 ms claim is for an unloaded fibre. Response with real tubing, real valve flow and a real load has not been published. It is a DD item.

**Efficiency**
- Meller (Cornell PhD dissertation, 30 Jan 2017):
  - transduction efficiency rose "from 27% for a pneumatic latex bladder McKibben muscle" to 80% for a hydraulic LDPE-bladder muscle (fluid and bladder were changed together);
  - "on average 43% of the input power is lost to valve throttling" in hydraulic servo systems;
  - variable recruitment raised actuation efficiency from 39% to 57% compared with throttling only.
  — VERIFIED — https://ecommons.cornell.edu/entities/publication/3fff4a2b-07ad-49c8-95f8-dd33241afdff
- The underlying journal paper is Meller, Bryant & Garcia, "Reconsidering the McKibben muscle: energetics, operating fluid, and bladder material", JIMSS 25(18):2276–2293 (2014). Full text not fetched. — VERIFIED (citation) — same Cornell record
- System-level typical efficiency is 40–55% for hydraulics and 75–80% for electric actuation. Hydraulic power density once had about a 100x advantage over electric; that has narrowed to about 10x. — SECONDARY (humanoid.guide citing Hardware FYI) — https://humanoid.guide/?p=17842
- Electric is not loss-free. On the MIT Cheetah (6 m/s, 973 W), "76% of the total energy consumption is attributed to heat loss from the motor" (Seok et al., IEEE/ASME TMech 20(3):1117–1129, 2015). — SECONDARY (abstract via search; PDF rate-limited) — https://dspace.mit.edu/handle/1721.1/108096
- ANALYST, battery-to-work chain (assumptions stated, all unverified for Clone):

  | Stage | Hydraulic chain | Pneumatic chain |
  |---|---|---|
  | Pump or compressor (wire to fluid) | 0.40–0.60 | 0.30–0.50 |
  | Valve throttling (Meller average) | 0.57 | 0.57 |
  | Muscle transduction (Meller) | 0.80 | 0.27 |
  | **Product** | **~18–27%** | **~5–8%** |

  Electric motor plus gearbox reaches about 60–77% at its rated point, and much less at stall or low speed.

**Pump power check**
- Reported pump: "500-watt electric pump … delivering 40 SLPM at 100 psi". This is the article's own wording, not attributed to Clone. — SECONDARY — https://interestingengineering.com/innovation/clone-alpha-humanoid-robot-unveiled-poland
- Live Science (15 Apr 2025) cites Clone's website for "a 500 watt electric pump as compact as the human heart". — CLAIMED (via secondary) — https://tech.yahoo.com/science/articles/dangling-twitching-android-bionic-muscles-094727953.html
- ANALYST:
  - Hydraulic power = 100 psi × 40 L/min = 689.5 kPa × 6.667e-4 m³/s = **459.7 W** (666 W at 145 psi).
  - A 500 W electrical pump delivering both figures at once would need about 92% wire-to-water efficiency, which is implausible for a small pump.
  - Either the figures are maximum flow and maximum pressure that do not occur together, or the pump draws more than 500 W.
  - "SLPM" (standard litres per minute) is a gas-flow unit, consistent with the specs having been measured on air.

**Battery implications**
- Figure F.03 battery (17 Jul 2025): "2.3 kWh" and "5 hours of run time at peak performance". ANALYST: that is about 460 W whole-robot average. — CLAIMED (primary, Figure) — https://figure.ai/news/f-03-battery-development
- Tesla Optimus (AI Day 2022): 2.3 kWh pack; about 100 W seated and about 500 W walking. — SECONDARY — https://www.advancedbatteriesresearch.com/articles/27883/will-teslas-humanoid-robot-optimus-really-be-able-to-serve-people
- NVIDIA Jetson AGX Thor, which Clone reportedly uses, is configurable from 40 to 130 W. — SECONDARY — https://docs.edge-ai-sdk.advantech.com/docs/Hardware/AI_System/Nvidia/Jetson%20Thor/
- Clone's valves reportedly draw "<1 W" each. — SECONDARY — https://interestingengineering.com/innovation/clone-alpha-humanoid-robot-unveiled-poland
- ANALYST, runtime on a 2.3 kWh pack:

  | Case | Pump | Compute | Valves | Total draw | Runtime |
  |---|---|---|---|---|---|
  | Lean | 250 W | 100 W | 50 W | 400 W | 5.75 h |
  | As quoted | 500 W | 100 W | 100 W | 700 W | 3.29 h |
  | Biped | 1,000 W | 130 W | 200 W | 1,330 W | 1.73 h |

  An 8 h shift at 0.7–1.33 kW needs 5.6–10.6 kWh, i.e. 2.4–4.6 of today's 2.3 kWh packs. The pump size in the memo is illegible ("~?kW").

**Force, grip and sensing claims**
- Hand claims: "grip and hold up to 15 pounds" (6.8 kg); muscles "survive 650,000 contraction cycles"; 27 DoF hand; 124 torso muscles; 320 pressure sensors; 70 inertial sensors. All are unattributed in the article (New Equipment Digest, 30 May 2025). — SECONDARY — https://www.newequipment.com/technology-innovations/fun-innovations-friday/blog/55293390/clone-robotics-synthetic-human-is-as-fascinating-as-it-is-frightening

### (b) Durability: cycle life versus what deployment needs

**Clone's figures**
- Memo: "today's muscles are rated for 100,000(?) contraction cycles"; a 10-million-cycle target (?). — CLAIMED / UNREAD — BRIEF.md
- Press: hand muscles "can survive 650,000 contraction cycles" (unattributed). — SECONDARY — New Equipment Digest URL above
- The two figures may describe different things. If the memo really says 100k, it conflicts with the press figure. — CONFLICT (pending legible memo)
- Clone publishes no cycle-life data on its own site. — NOT FOUND — searched clonerobotics.com /, /hand/, /android/, /research/, /pre-order/
- A Ukrainian student thesis reports "<5% degradation after 10,000 cycles, 35% contraction, 1.2 kg per fibre". Not traced to Clone. — NOT VERIFIED (lead only) — https://timetable.knutd.edu.ua/bitstream/123456789/30867/1/Demchenko_Thesis.pdf

**The fatigue literature**
- Klute & Hannaford 1998 ("Fatigue characteristics of McKibben artificial muscle actuators", IROS 1998, vol. 3, pp. 1776–1781) and Kingsley & Quinn 2002 (ICRA 2002, pp. 2830–2835) are the founding fatigue papers. Per Kothera et al. 2009, "latex bladders offer higher fatigue life than silicone bladders" and "the use of tighter weaved braids increases fatigue life". — VERIFIED (via Kothera 2009) — https://sites.utexas.edu/sirohi/files/2017/07/014_kothera09_jmd.pdf
- The original cycle counts in those two papers are NOT FOUND (paywalled; searched IEEE Xplore listings, Case Western, DBLP).
- Capps (Virginia Tech MS thesis, 2014): fatigue life depends on materials and geometry; latex is best; thicker walls and a polyurethane casing extend life. The abstract gives no cycle counts. — VERIFIED — https://vtechworks.lib.vt.edu/items/cce178ba-b7c5-4c72-952d-35f93b5fc9cd
- Depending on construction, McKibbens last "between a few hundred and a few million cycles". — SECONDARY (search snippet; page returned 403) — https://softroboticstoolkit.com/node/169436
- Naclerio & Hawkes 2020: the fabric muscle survived 100,000 cycles at 0–100 kPa (14.5 psi), 2 Hz, unloaded, with no measurable leakage, after which the test was stopped. That is a lab test at about 1/7 of Clone's reported pressure. — VERIFIED — https://par.nsf.gov/servlets/purl/10221275
- s-muscle Co. (Suzumori et al., JSME award 2020) commercialised 2–5 mm thin McKibben muscles with "a drive durability of more than 1 million times". Pressure is not stated; applications are power-assist suits and rehab. **This is the strongest public evidence in Clone's favour on durability.** — VERIFIED — https://jsme.or.jp/english/about/awards/2020-2/award2020-nt4
- Kobayashi, Nabae, Mao, Endo & Suzumori, IEEE RA-L 9(11):9685–9692 (Nov 2024), DOI 10.1109/LRA.2024.3455890:
  - thin McKibben muscles are "very durable in a straight state" but "easily broken in a bent state", because sleeve fibres shift and the tube protrudes and cracks;
  - adhesive bonding gave up to 10,000x durability (best case) and 500x at 0.5 MPa;
  - baseline cycle counts NOT FOUND.
  — SECONDARY (abstract via search index; the repository page now shows a shutdown notice) — https://t2r2.star.titech.ac.jp/rrws/file/CTT100925838/ATD100000413/
  - ANALYST: muscles routed over joints and bones in an anatomical skeleton are, at least in part, bent-state muscles.
- Zhang et al., Smart Mater. Struct. 30(8):085013 (2021), water-hydraulic artificial muscles:
  - initial failure modes were end-fitting slip-out, sleeve loosening, tube rupture and fibre fracture;
  - after redesign, "the end of rubber tube breaking and fibre fracture" remained;
  - no cycle data in the abstract.
  — VERIFIED — https://iopscience.iop.org/article/10.1088/1361-665X/ac0671
- Festo DMSP: the datasheet gives no cycle-life rating. A 2002 trade article sourced from Festo says the muscles "have difficulty dealing with static loads over a long period of time (500 hours or more), because the materials relax", and that service life falls above 60 °C. — VERIFIED (datasheet absence) / SECONDARY (2002 article) — Festo datasheet above; https://www.powermotiontech.com/other-technologies/it-looks-piece-hose-its-pneumatic-tensile-actuator

**Competitor baselines (motor hands are also immature)**
- Unitree Dex2/5: "The entire hand has passed over 100000 fatigue cycles". It is a 10-DOF, 2-actuated, gear-tendon hand. — CLAIMED (primary, Unitree) — https://www.unitree.com/Dex2-5
- The Aero Hand Open transmission survives >400,000 full-actuation cycles (arXiv). — SECONDARY (search summary) — https://arxiv.org/pdf/2608.28578
- Sanctuary's hydraulic hand valves were reportedly tested for >2 billion cycles. Sanctuary's own page says only "extensive endurance testing". — SECONDARY / CLAIMED — https://inspenet.com/en/noticias/sanctuary-ai-advances-with-21-degree-of-freedom-hydraulic-hands ; https://sanctuary.ai/?p=58

**Deployment arithmetic (ANALYST; 1 cycle per grasp per flexor muscle; 8 h shifts)**

Cycles per year per muscle:

| Grasps/min | 1 shift × 250 d | 2 shifts × 250 d | 24 h × 350 d |
|---|---|---|---|
| 4 | 480,000 | 960,000 | 2,016,000 |
| 8 | 960,000 | 1,920,000 | 4,032,000 |
| 12 | 1,440,000 | 2,880,000 | 6,048,000 |

Time to reach each rating at 8 grasps/min (480 cycles/h):

| Rating | Hours | 1-shift days | Years on 2 shifts | Years at 24/7 |
|---|---|---|---|---|
| 100k (?) | 208 | 26 | 0.05 | 8.7 days |
| 650k (press) | 1,354 | 169 | 0.34 | 0.16 (56 days) |
| 1M (s-muscle) | 2,083 | 260 | 0.52 | 0.25 |
| 10M target (?) | 20,833 | 2,604 | 5.2 | 2.5 |

Other duty profiles:
- A 3-year asset life at 8 grasps/min needs 5.76M cycles on 2 shifts and 12.1M at 24/7. The 10M target is roughly the right order of magnitude; 100k–1M is one to two orders short.
- Home use (2 h/day of manipulation at 4 grasps/min, 365 days) is 175,200 cycles/yr. A 100k rating lasts under 7 months; 650k lasts about 3.7 years.
- Leg muscles in a biped do about 1 major cycle per stride per leg (~1/s). That is 1.8M cycles/yr at 2 h/day of walking and 7.2M/yr at 8 h/day (250 days), before counting the small balance corrections.

The many-muscles problem:
- A robot with N wear-limited fibres fails at the *first* one, unless it degrades gracefully. For a Weibull life distribution, expected first failure ≈ η·Γ(1+1/β)·N^(−1/β), as a fraction of characteristic life η:

  | N | β = 2 | β = 3 | β = 5 |
  |---|---|---|---|
  | 36 | 0.148 | 0.270 | 0.448 |
  | 74 | 0.103 | 0.213 | 0.388 |
  | 300 | 0.051 | 0.133 | 0.293 |
  | 1,000 | 0.028 | 0.089 | 0.231 |

- Example: with η = 650k cycles, N = 74 and β = 3, the first fibre is expected to fail at about 138k cycles. At 8 grasps/min on 2 shifts, that is about 18 working days.
- Clone's fibre count per hand under full grasp duty is UNKNOWN. Torso 2 reportedly has 910 fibres and Protoclone >1,000 (secondary).

### (c) Leaks, water, freezing, contamination, maintenance, safety and certification

**Pressure and injection risk**
- UK HSE (bulletin FOD 4-2014, 23 Sep 2014): serious injection injuries occur "over 100 bar (1450 psi)", and anecdotal evidence suggests injuries "as low as 7 bar (101.5psi)". — VERIFIED — https://www.hse.gov.uk/safetybulletins/hydraulic-injection-injury.htm
- ANALYST: Clone's reported 100–145 psi (6.9–10 bar) sits at or just above that anecdotal threshold and far below the serious-case pressures. The risk is low but not zero, and a regulator will expect an assessment of pinhole-jet risk near faces in homes.

**Water as a hydraulic fluid**
- Limitations (Power & Motion, Jan 2012):
  - water "can readily leak through the clearances found in non-packed valves for oil service";
  - it "does not provide the full-film lubrication of oil";
  - freezing is "one limitation";
  - systems are "more prone to pump cavitation";
  - bacteria are held in check by "sealing the system from atmosphere".
  — SECONDARY (trade press) — https://www.powermotiontech.com/hydraulics/hydraulic-fluids/article/21883098/water-hydraulics-benefits-and-limitations
- Water as a working fluid is fire-resistant, cheap and easy to dispose of. — SECONDARY — same

**Microbes and freezing**
- Legionella "grows best between 77°F–113°F (25°C–45°C)" and "may grow at temperatures as low as 68°F (20°C)" (CDC). — VERIFIED — https://www.cdc.gov/control-Legionella/php/guidance/monitor-water-guidance.html
- ANALYST:
  - Water warmed by a pump and electronics inside a body will likely sit in or near the 25–45 °C band.
  - A sealed loop limits the risk, but a burst fibre at 7–10 bar can aerosolise its contents.
  - Expect a biocide or glycol additive, at which point the fluid is "not just water" and needs a change interval.
  - Freezing (water expands about 9% when it freezes) is a shipping and storage hazard for thin-walled fibres and valves.

**Standards**
- ISO 4413:2010 (hydraulic fluid power: general rules and safety requirements) applies to hydraulic systems on machinery as defined by ISO 12100. It covers hazards, design rules, verification and testing, and information for use. — SECONDARY (standards catalogue listings) — https://scc-ccn.ca/standardsdb/standards/8145607
- ISO 25785-1 (safety of industrial mobile robots with actively controlled stability, including bipeds) was still at committee or working draft stage (ISS lists WD, June 2025). No published edition was found. — SECONDARY — https://www.iso.org/standard/91469.html (403 to fetch); https://iss.rs/en/project/show/iso:proj:91469
- ANALYST: Clone will need certification on two fronts: robot safety (ISO 10218, ISO 25785-1 once published) and hydraulic or pressure safety (ISO 4413; in the EU possibly pressure-equipment rules, applicability NOT VERIFIED). For homes, household-appliance rules apply to a water-filled, battery-powered device. Electric competitors face only the first front.

**Leaks in practice**
- Sanctuary markets its hydraulic hand as "low pressure, minimal fluid volume, and automatic fault protection". This shows a hydraulic-hand competitor treats leak and fault handling as a selling point. — CLAIMED (primary) — https://sanctuary.ai/?p=58
- BD's hydraulic Atlas farewell video showed burst hydraulic lines. — SECONDARY — https://humanoid.guide/?p=17842 ; https://hackster.io/news/atlas-is-dead-long-live-atlas-boston-dynamics-drops-hydraulics-as-it-targets-commercialization-4539d6c2e277
- Clone's leak detection, containment and muscle-replacement procedure: NOT FOUND (searched the Clone site and press coverage, 2022–2026).

### (d) Why Boston Dynamics left hydraulics, and how fluidic actuation has fared commercially

**Boston Dynamics**
- BD (blog, Apr 2024): "This week we announced the retirement of our hydraulic Atlas"; "The electric version of Atlas will be stronger, with a broader range of motion than any of our previous generations"; "This is the first look at a real product". — VERIFIED — https://bostondynamics.com/blog/electric-new-era-for-atlas/
- CEO Robert Playter (IEEE Spectrum, 17 Apr 2024), answering whether hydraulics were still the best route:
  - "We first experimented with that with the launch of Spot … discovered that we could build powerful lightweight electric motors that had the same kind of responsiveness and strength, or let's say sufficient responsiveness and strength";
  - "the electric Atlas is stronger".
  — VERIFIED — https://spectrum.ieee.org/atlas-humanoid-robot-ceo-interview
- BD did **not** publicly cite leaks, maintenance or cost as reasons. — VERIFIED (absence in both primary sources); "Boston Dynamics … never said why Atlas was being retired" — SECONDARY — https://gigazine.net/gsc_news/en/20240417-boston-dynamics-atlas-retires
- Commentators' reasons: hydraulics were "complex and costly to maintain and productise"; the pump holds pressure even at rest; noise; filters and fluid changes. — SECONDARY — https://humanoid.guide/?p=17842 ; https://singularityhub.com/2024/04/17/boston-dynamics-says-farewell-to-its-humanoid-atlas-robot-then-brings-it-back-fully-electric/
- No commercial humanoid in the 2026 lists (Optimus, Figure, Unitree, Apollo, Digit, electric Atlas) uses hydraulic limbs. Sanctuary (hydraulic hands) and Clone are the fluid holdouts. — SECONDARY — https://humanoid.guide/?p=17842

**Shadow Robot**
- The air-muscle hand used 36 air muscles and 72 valves. — SECONDARY — https://www.machinedesign.com/news/article/21815099/robotic-hand-has-that-human-touch
- The motor hand replaced the air-muscle hand around 2010. — SECONDARY — https://www.wevolver.com/article/dexterous-robotic-hands-part-1-unraveling-the-history-technology-and-applications-of-dexterous-robotic-hands/draft
- Shadow's current product page lists only "20 DC motors", tendon-driven, 24 DoF, 40 tendon load sensors and tactile fingertips. No pneumatic option is offered. — VERIFIED — https://shadowrobot.com/dexterous-hand-series/
- Wikipedia's undated claim that both versions are on sale is outdated relative to that page. — CONFLICT, resolved in favour of the primary page — https://en.wikipedia.org/wiki/Shadow_Hand

**Sarcos**
- The XOS 2 exoskeleton was hydraulic; the later Guardian XO was "all-electric". In 2023 Sarcos pivoted to AI software and ceased "all operations involving hardware", then renamed itself Palladyne AI in March 2024. — SECONDARY — https://Www.wikipedia.org/wiki/XOS_2 ; https://investor.palladyneai.com/node/6681/pdf

**Sanctuary AI (the closest analogue: hydraulic hands on an electric body)**
- Patent US 12,435,813 B2, "Miniaturized hydraulic valve…" (filed 30 Nov 2023), covers more than about 700 psi at less than about 0.5 LPM. — VERIFIED — https://patentsgazette.uspto.gov/week40/OG/html/1539-1/US12435813-20251007.html
- Sanctuary's page lists 17 DOF with tactile sensing. — CLAIMED — https://sanctuary.ai/?p=58
- The board removed CEO Geordie Rose and about 30 staff were let go (Nov 2024). — SECONDARY — https://bnnbloomberg.ca/business/technology/2024/11/15/robotics-startup-sanctuary-ai-cuts-jobs-after-two-co-founders-leave
- Sanctuary has one claimed commercial deployment and no disclosed revenue. — SECONDARY — https://www.robotics.press/companies/sanctuary-ai/

**Festo**
- DMSP is a long-lived industrial catalogue product, running on air only (VERIFIED, datasheet above).
- The BionicSoftHand (2019) was a Bionic Learning Network "Future Concept" with pneumatic bellows. No evidence it was ever sold. — SECONDARY — https://www.festo.com/us/en/e/about-festo/research-and-development/bionic-learning-network/highlights-from-2015-to-2017/bionicsofthand-id_68106/ ; https://www.automation.com/article/festo-to-introduce-bionicsofthand-and-bionicsoftar

**Bridgestone**
- After the 2017 5 MPa hydraulic muscle (VERIFIED above), it launched the TETOTE rubber-muscle soft hand for piece-picking (Sep 2024). Bridgestone describes "small-scale commercialization" in its 2024–26 plan, and no sales figures have been published. — SECONDARY — https://european-rubber-journal.com/article/2096073/bridgestone-to-unveil-rubber-based-robotic-hand-for-objects-of-varying-shapes ; https://www.robotics247.com/article/bridgestone_begins_testing_soft_robot_piece_picking_logistics_sites

**Soft Robotics Inc. (mGrip)**
- 2024–25 status NOT FOUND. Searched trade press; results were from 2019 or earlier.

### (e) The cost claim

**Is the actuator the dominant cost? Directionally yes**
- Actuators are 40–60% of a humanoid bill of materials (BOM); sensing and perception 10–20%; compute 10–15%; structure 5–10%; battery 5–10%. — SECONDARY (McKinsey via search snippet; page returned 503) — https://www.mckinsey.com/br/en/our-insights/turning-humanoid-supply-chain-constraints-into-billion-dollar-wins
- Morgan Stanley's Optimus Gen 2 teardown, as reported: about $55k total, with hands about $9.5k (17.2%) and legs $21.3k (38.6%); actuators roughly half of cost. — SECONDARY (primary report not reached) — https://fourweekmba.com/what-does-it-cost-to-build-a-humanoid-robot/ ; https://xenospectrum.com/en/humanoid-robot-bom-actuator-cost/
- Dexterous hands are 14–18% of humanoid cost (iyiou data cited by 36Kr, 30 Jun 2025). — SECONDARY — https://eu.36kr.com/en/p/3358415098185730
- BofA Institute (Apr 2025) put the BOM at about $35k per unit by end-2025, falling to $13–17k by 2030–35. — SECONDARY — https://fourweekmba.com/where-the-money-goes-in-humanoid-robotics/

**Is a ~$1.1K hand BOM (memo tile, approximate) plausible, and is it 10x cheaper? Partly**

Prices of motor-driven hands:

| Hand | DoF | Price | Basis | Source |
|---|---|---|---|---|
| Huiling e-hand6 | 6 | ¥2,999 (~$420 at 7.15) | Retail | 36Kr 30 Jun 2025 (SECONDARY) |
| Lingxin/Linker O7 | 7 | ¥8,800 (~$1,230) | Retail | 36Kr 30 Jun 2025 (SECONDARY) |
| Qiangnao second-gen hand | — | ¥20,000 (~$2,800) | Retail | 36Kr 30 Jun 2025 (SECONDARY) |
| Qiangnao, with tactile | — | ¥35,000 (~$4,900) | Retail | 36Kr 30 Jun 2025 (SECONDARY) |
| High-DoF hands generally | high | from ¥400–500k down to the "10,000-yuan level" | Price trend | 36Kr 24 Aug 2026 (SECONDARY) |
| Inspire RH56H1 | — | $4,500 | US reseller listing | Knox Labs (VERIFIED as listing) |
| Inspire RH56 for Unitree H2 | — | $9,150–10,200 per hand | US listing, incl. tariffs | RobotShop (VERIFIED as listing) |
| Unitree Dex5-S | — | from $6,500 | Retail | Digg aggregator (SECONDARY) |

Sources: https://eu.36kr.com/en/p/3358415098185730 ; https://eu.36kr.com/en/p/3952926183554434 ; https://www.knoxlabs.com/products/inspire-robots-rh56h1-dexterous-hand ; https://www.robotshop.com/products/inspire-rh56dftp-dexterous-hand-for-unitree-h2-right ; https://digg.com/ai/ujswxfjm

- A full electric humanoid already sells cheaply: Unitree R1 launched 25 Jul 2025 at ¥39,900 (Bloomberg ~$5,900; Reuters $5,566). It is 25 kg, 26 joints, 121 cm. — SECONDARY — https://www.bloomberg.com/news/articles/2025-07-25/china-s-unitree-r1-is-a-humanoid-robot-costing-less-than-6-000
- Clone Alpha target price is under $20,000. — SECONDARY (humanoid.guide citing The Rundown) — https://humanoid.guide/?p=19391
- ANALYST:
  - **Like for like.** Clone's ~$1.1K (?) is a BOM; the competitor figures in the memo's table ($10–20K+) look like prices. Chinese 6–7 DoF motor hands already *retail* at roughly Clone's claimed BOM.
  - **Per DoF.** A 26–27 DoF hand at $1.1K BOM is cheap per DoF, about $41–42/DoF, if the BOM includes valves and sensors.
  - **At hand level, not 10x.** It is not 10x cheaper than the cheapest motor hands.
  - **Whole robot.** Electric humanoid BOMs are falling toward $13–17k (BofA) and retail prices are already at $5.6–5.9k (Unitree R1). That leaves Clone little room to "price to prevent competitors from ever achieving economies of scale".

**What hydraulics adds to the BOM (ANALYST, unverified unit costs; DD item)**
- One pump with motor and controller (reported 500 W).
- Reservoir or accumulator, filtration and plumbing.
- One valve per independently controlled channel. Reported counts: 36 valves for the 2022 hand and forearm (New Atlas); the current count is unknown.
- One pressure sensor per channel. Clone claims 320 "for muscle-level force feedback" (Live Science, citing Clone).
- Manifolds and fittings, plus leak detection.
- Illustrative arithmetic: N channels × (valve + sensor) at $10–30 per channel gives $3.6–10.8k at N = 360. The "1/10th cost" claim therefore depends on per-channel valve and sensor cost and on how many fibres share a valve. None of this is published.
- Hydraulics *removes* the motors, gearboxes, encoders, bearings and drivers from the joints. Muscle parts (rubber tube plus braid) are cheap. The net direction could favour Clone, but only if valve cost is driven very low.

### (f) The steelman: genuine advantages, with evidence

- **Power-to-weight.** The hydraulic McKibben muscle has a "strength-to-weight ratio that 5 to 10 times greater than conventional electric motors and hydraulic cylinders" (5 MPa, 7 kN from 15 mm OD). — VERIFIED (institutional claim) — https://www.titech.ac.jp/english/news/pdf/tokyotechpr_en_suzumori_20170126.pdf
- **Hydraulic beats pneumatic for this muscle type.** Hydraulic operation "increases actuator stiffness and allows for roughly double the efficiency" (Meller 2017). Clone's stated move from air to water is technically sound. — VERIFIED — https://ecommons.cornell.edu/entities/publication/3fff4a2b-07ad-49c8-95f8-dd33241afdff
- **Compliance and backdrivability.** Clone: "back-drivable, antagonistic muscles and tendons"; "Soft muscle, fat, and skin for a human-like interaction". Festo: the muscle "behaves like a spring", with stiffness that can be set via pressure. — CLAIMED (Clone primary) / VERIFIED (Festo) — http://www.clonerobotics.com/hand/ ; Festo datasheet above
- **Built-in force sensing.** Clone claims "320 pressure sensors for muscle-level force feedback" and "70 inertial sensors that provide joint-level proprioception". The hand page claims "accurate Myofiber proprioception". Futura (Jun 2026) reports 500 sensors covering joint position, localized torque, muscle length and structural force.
  - CLAIMED (via secondary) — https://tech.yahoo.com/science/articles/dangling-twitching-android-bionic-muscles-094727953.html ; http://www.clonerobotics.com/hand/ ; https://www.futura-sciences.com/en/?p=33815
  - ANALYST: pressure plus length gives tendon force (F = f(P, ε)) without a separate load cell. Accuracy is limited by McKibben friction hysteresis (>10x a low-hysteresis design, per Naclerio & Hawkes). It measures muscle tension, not fingertip contact location or slip.
- **Fingertip tactile sensing at Clone: NOT FOUND.** Searched the Clone site and 2022–2026 press. Comparators:
  - Figure 03: "Each fingertip sensor can detect forces as small as three grams of pressure" (9 Oct 2025). — CLAIMED (primary) — https://www.figure.ai/news/introducing-figure-03
  - Shadow: tactile fingertips (VERIFIED, product page above).
  - Sanctuary: tactile sensors (CLAIMED, page above).
- **Static holding energy (ANALYST).** A leak-tight muscle with closed valves holds force with near-zero flow. An electric joint pays I²R heat to hold torque unless the gearing is non-backdrivable. This only helps if the pump can idle (variable speed or accumulator) rather than hold constant pressure. Clone's architecture is unknown.
- **Human-like kinematics and dexterity.** Clone claims 26–27 hand/wrist/elbow DoF, 20 DoF in the shoulder and 164 DoF in the upper torso. The hand page claims "Human-level thumbs". — CLAIMED / SECONDARY — http://www.clonerobotics.com/hand/ ; https://interestingengineering.com/innovation/clone-alpha-humanoid-robot-unveiled-poland
- **Simple manufacturing of the muscle.** Clone claims braiding and moulding machines (memo). Commercial thin McKibben muscles exist at >1M cycles (s-muscle), so manufacturable and durable *fibres* are proven elsewhere. — VERIFIED (s-muscle) / CLAIMED (Clone) — https://jsme.or.jp/english/about/awards/2020-2/award2020-nt4
- **Speed.** <50 ms unloaded (CLAIMED). Water is nearly incompressible, so a hydraulic system avoids the compressibility lag that Clone itself cites for pneumatics. — CLAIMED / ANALYST — https://humanoid.guide/?p=19391

### Status of the water-hydraulic system (cross-cutting, decision-relevant)

Sources saying the demos ran on air:
- Torso 2 (Circuit Digest, 11 Dec 2024): "the robot seems to run on pneumatic actuation", with "off-the-shelf valves, which can be a bit noisy due to air exhaust", and "in later version it will be upgraded to a quieter hydraulic system". — SECONDARY — https://circuitdigest.com/news/clone-robotics-lifelike-robot-with-910-muscle-fibers-and-164-degrees-of-freedom
- Futura (11 Jun 2026): the current prototype uses "a pneumatic setup driven by pressurized air", and the production roadmap moves to "a closed loop hydraulic system" with a 500 W pump. — SECONDARY — https://www.futura-sciences.com/en/?p=33815 ; also https://humanoid.guide/?p=12355
- The Protoclone V1 demo unit "runs on pneumatics"; Clone says later versions will use hydraulics. — SECONDARY — https://humanoid.guide/?p=19391

Sources saying water:
- Interesting Engineering (11 Nov 2024): "battery-operated system of pumps and valves circulating water". — SECONDARY — https://interestingengineering.com/innovation/humanoid-torso-clone-water-powered
- Live Science (15 Apr 2025): "water-powered hydraulics". — SECONDARY — https://tech.yahoo.com/science/articles/dangling-twitching-android-bionic-muscles-094727953.html

Verdict and demo status:
- **CONFLICT.** The weight of the newer reporting (Jun 2026) says the demos were pneumatic. The memo (Oct 2026) describes water hydraulics as the product.
- No complete Alpha robot had been shown working in public as of Dec 2024. — SECONDARY — https://www.maginative.com/article/meet-clone-alpha-a-humanoid-robot-built-with-synthetic-organs-and-artificial-muscles/
- Protoclone was shown suspended from the ceiling. — SECONDARY — https://www.mobilissimo.ro/stiri-diverse/protoclone-robotul-cu-1-000-de-muschi-hidraulici-arata-impresionant-in-teste-dar-mai-e-mult-pana-la-un-prototip-functional

---

## 3. What I could not reach

**Clone primary data**
- Current clonerobotics.com pages carry no specs.
- Wayback Machine snapshots of the old spec pages: blocked (WebFetch refused, curl reset).
- Clone X/YouTube primary posts: not fetched.
- Clone patents: no patent records found by name search (Google Patents and USPTO not hit). The IP sweep should run assignee or inventor searches.

**Original fatigue papers**
- Klute & Hannaford 1998 (IROS) and Kingsley & Quinn 2002 (ICRA): cycle counts paywalled.
- Chou & Hannaford 1996: DTIC PDF returned 403.
- Meller et al. 2014 JIMSS full text: abstract only, via the 2017 dissertation.
- Kobayashi et al. 2024 RA-L baseline cycle counts: the repository is shut down; the abstract came via search index.

**Bank, consultancy and standards sources**
- Morgan Stanley, BofA and McKinsey primary reports: 503 or paywalled; only secondary write-ups reached.
- ISO 25785-1 catalogue page: 403. Status taken from the ISS and BSI listings via search.

**Commercial and benchmark data**
- Soft Robotics Inc. 2024–26 status.
- Festo DMSP cycle-life rating: not published in the datasheet.
- Sanctuary's 2B-cycle valve claim on a primary page.
- Seok et al. 2015 BigDog cost-of-transport figure: MIT PDF rate-limited (429).

**The memo**
- The memo itself is illegible: pump kW, cycle rating (100k?), 10M target, hand BOM ($1.1K?), muscle count (89?).

---

## 4. Ranked DD questions for Clone, each naming what it would move

**P1: decision-gating**
1. **Which fluid is in Torso 4 today, water or compressed air?** On the Zoom demo, show the pump, the reservoir, a pressure trace in bar, and the robot running untethered from its own pump. *Moves:* whether the core "water-hydraulic" thesis has been demonstrated or is still roadmap; which efficiency chain applies (~5–8% pneumatic vs ~18–27% hydraulic); credibility of the Sep 2027 untethered-biped milestone.
2. **Myofiber cycle-life test data.** Provide cycles-to-failure for n ≥ 10 fibres: Weibull η and β, pressure (bar), stroke %, load (N), straight vs bent routing, water temperature, and failure mode. Which figure is current: 100k (?), 650k (press) or 10M (target)? Is there an in-situ hand endurance test (cycles before the first fibre failure)? *Moves:* the durability and service-cost model, industrial viability (the 2-shift need is ~1.9M cycles/yr per hand muscle), and the warranty and uptime assumptions in the unit-economics table.
3. **Measured energy budget.** Provide average and peak electrical draw (W) of Torso 4 on a representative pick task, plus pump architecture: constant-pressure, variable-speed or accumulator. Give pump wire-to-water efficiency, measured flow at pressure, planned biped battery size (kWh) and runtime target. *Moves:* untethered viability, whether 8 h shifts need 2.4–4.6 battery packs or a tether or swap, and the leg-power feasibility for 2027.
4. **What is inside the ~$1.1K (?) hand BOM?** Muscles only, or also valves, pressure sensors, manifold, controller and a share of the pump/power unit? At what volume? How many valves per hand, and the cost per valve? *Moves:* the "1/10th cost" thesis and the pricing-moat argument against ¥3–9k motor hands and the ~$5.6–5.9k Unitree R1.

**P2: score-moving**
5. **Field service model.** Time and cost to replace one fibre. Are muscles modular cartridges? Failure mode on rupture (seep or jet)? Leak detection and containment? Projected robot-level time between muscle failures for N fibres? *Moves:* opex per robot-year and pilot-customer acceptance.
6. **Fluid specification.** Pure water or additives (glycol, biocide)? Freeze protection for shipping and storage? Microbial control (the 25–45 °C Legionella band)? Fluid change interval? IP rating isolating the water from the battery and compute? *Moves:* safety case, maintenance cost, and home-market feasibility.
7. **Force-sensing performance (Casey's crux).** Grip-force estimation error from pressure plus length versus load-cell ground truth (N and %). Measured hysteresis (%). Minimum controllable grip force (g). Is fingertip tactile or slip sensing present or planned, from which supplier, and on which roadmap date? *Moves:* the autonomy and dexterity score versus Figure 03 (3 g fingertip claim), Shadow and Sanctuary, and whether the hand "leads".
8. **Loaded bandwidth.** Step response to 90% force (ms) at operating pressure with the real tubing lengths in Torso 4, not an unloaded fibre. *Moves:* the balance and locomotion feasibility of the legs and the "superhuman speed" claim.
9. **Certification plan and pressure safety.** Maximum system pressure and burst margin (bar); which standards are targeted (ISO 4413, ISO 10218, ISO 25785-1, household rules); any third-party assessment; timeline. *Moves:* time to revenue in factories and homes, and the pilot contract terms.
10. **Valves.** Is "Aquajet" a custom valve in production, or are the valves off the shelf (the Torso 2 reports say off the shelf)? Valve cycle-life rating, supplier, and unit cost at 10k units. *Moves:* BOM, durability (valves are a second wear item), and supply-chain risk.

**P3: completeness**
11. Myofiber force–contraction curves at rated pressure (force at 0, 10, 20 and 30% contraction) and measured specific power (W/kg). *Moves:* payload and grip specs (e.g. the "15 lb grip" claim) and the comparison table.
12. Robot mass breakdown: fluid, pump/power unit and battery against the "88 lb" (?) tile. *Moves:* payload-to-weight and battery sizing.
13. Steady-state fluid temperature after 1 h of work, and thermal management. *Moves:* the fibre-life derating (Festo: life falls above 60 °C) and the microbial risk.
14. Noise in dB(A) at 1 m for the pump and valves. *Moves:* home and hospitality suitability.
15. Patent claims covering fibre construction and the valve, plus IP assignment from the departed co-founder (cross-reference the IP sweep). *Moves:* whether the actuation advantage is defensible.
