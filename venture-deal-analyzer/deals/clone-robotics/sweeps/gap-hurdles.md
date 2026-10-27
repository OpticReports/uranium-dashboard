# Clone Robotics — GAP: hurdle ledger, duty-cycle reconciliation, SAM, exit map (rev 1, pre-DD)

Date 2026-10-27. Scope: process v1.2 S1 items that were missing (hurdle ledger, exit odds, market build).
Inputs read in full or in the relevant sections: `factpack.md`, `templates/hurdle-ledger.md`, `templates/rubric.md`,
`templates/ic-process.md`, `sweeps/sweep-market.md`, `sweeps/verify-market.md`, `sweeps/sweep-competition.md`,
`sweeps/sweep-actuation.md` (§1 and the durability section), `sweeps/verify-competition.md` (rows 14 and 16),
`sweeps/sweep-company.md` and `verify-company.md` (team and financing rows), `source/legible-fragments.md`,
`models/exit_curve.py` (run, not modified). The earlier deals' "hurdle ledgers" are one-paragraph classifications
(`deals/matter-intelligence/factpack.md` §Hurdle-ledger classification, `deals/series-x-capital/factpack.md` §EV);
this is the first full numeric ledger in the book, so it follows the template's structural rules directly.
Tags: VERIFIED (primary URL) / SECONDARY / CLAIMED / CONFLICT / NOT FOUND / NOT SEARCHED / REFUTED / ANALYST.
Web use: 8 searches + 2 fetches, plus a local re-read of the Agility S-4/A that the intake sweep had already saved
(sha256 `eefcf36c…`, same file verify-market checked). **Prompt-injection log: none.** Both fetches answered "no"
to text addressed to AI, and none of the search results contained any.

---

## EXECUTIVE READ (8 lines)

1. **P(all hurdles pass) is ~1.3% for the stationary-torso/hand path and ~0.5% for the full humanoid path** (central;
   band 0.4–4.2% and 0.1–2.1%). The template's own rule gives ~1.0% and ~0.4% (team 2 → w = 0.25).
2. **That implies P(≥10x) ≈ 0.7% (band 0.3–2.2%), against the panel's 2.5%.** Even the optimistic hurdle set is below
   the panel. At P(<1x) 0.85 the house model gives **EV 0.88x net (0.84–1.05x), not 1.08x.** Log it as a separate
   forecast; per the rubric it is never averaged with the panel.
3. **P(next priced round ≤24mo) ≈ 0.39 (0.34–0.44) against the panel's 0.45.** P(priced A at ≥$200M by mid-2027) ≈ 0.22,
   in line with the red team's ~0.25.
4. **Classification: HYBRID, venture-binding.** Two hurdles carry the file and resolve within about 8 months: V1a
   (Myofiber life at working pressure) and E4 (an autonomous Torso 4 grasp). Together they integrate E3, the Series A.
   This is Quaise-type, so diligence is a technical review plus a live demo. No team meeting moves it, and waiting is cheap.
5. **Duty-cycle bars, reconciled.** The two bars differ by **8.96x a year** (11.2x per minute × 16/20 h a day). The
   segment Clone ranks first, bench assembly, faces the **hardest** bar (0.96–1.92M/yr), where 650K lasts 0.34–0.68 yr.
   650K is enough only for research labs and the home (3.7–5.4 yr), which are the segments where Unitree is entrenched
   and where the biped is required.
6. **E1, the "10,000 Clones for a couple of million of capex" claim, is plausible as nameplate and worthless as evidence.**
   Agility's RoboFab is "designed" for 10,000 a year on $2.5–3.9M a year of capex, yet its H1 2026 robot sales were $0
   (S-4/A, VERIFIED). Clone also builds in-house what Agility buys: ~9M fibres and ~3M valve channels a year at 10,000 robots.
7. **Bottom-up SAM.** The three reachable pools total about **$0.4–1.0B a year** today: research/data $0.27–0.34B, hands
   $0.09–0.53B and Western bench $0.05–0.18B. Clone's band, *if the product works*, is **$3–46M a year by 2027–28**. The
   Market score should refer to this SAM, not to humanoid TAM. That supports 3 at most and makes a case for 2.5
   (W 2.18 → ~2.03).
8. **Exit map.** The likely exit is a strategic sale at $0.15–1B, which is 0.5–3.5x net. 10x needs a Linkerbot-doubling
   ($6B+) or a humanoid-platform outcome. Mentee's $900M is not an arm's-length comp: **51% of the price went to two
   sitting Mobileye executives** (DEF 14A, VERIFIED).

---

## (a) HURDLE LEDGER (template v1.0 rules)

### Probability conventions

- **p_marg** is the dated, unconditional forecast for the event. It goes to `ledger.csv` for hurdle-level Brier
  scoring (rule 4).
- **p_cond** is the probability *given every earlier hurdle in the chain has passed*.
- The product of the p_cond values is the exact joint probability (chain rule), so no independence is assumed.
- The template's rule-2 combination is shown alongside as a cross-check.
- Anchors marked ANALOGY are modelling assumptions (template caveat).

### Ledger

| # | type | hurdle — dated resolution event | anchor (template) → deal adjustment | grade | p_marg | p_cond | control |
|---|---|---|---|---|---|---|---|
| **E4** | E (hybrid with V) | **Autonomous Torso 4 grasp suite with logged force**: egg, cup, grape, plug insertion, slip recovery; ≥20 trials each. **By 2027-03-31** (tripwire #1). Lead indicator: Torso 4 shown live by 2026-11-30, p 0.60; autonomous at launch, p 0.15. | Field feasibility is evidenced: ACT; EgoScale on a 22-DoF hand (https://arxiv.org/html/2602.16710). Against Clone: no autonomous grasp ever shown (https://www.humanoidsdaily.com/news/clone-torso-3-hand-demo-torso-4-november; https://blog.robozaps.com/b/clone-protoclone-review), no wrist or palm cameras, McKibben hysteresis (fact pack §2, §4). For Clone: an RL CEO (https://www.ycombinator.com/companies/symplex). Red-team estimate 0.30 (fact pack §8.4). | plausible (narrow) / heroic (robust suite) | 0.30 | 0.30 | high-med |
| **V1a** | V | **Myofiber ≥2M cycles at stated working pressure, load and bend radius**, with test logs given to us or the A lead. **By 2027-06-30** (tripwire #4). | TRL 4–6 ≈ 30–60% per step (BIO phase-transition, ANALOGY), mid 45%. −15 pp: at ~0.7 MPa, bent "normal" muscles all failed (Kobayashi, RA-L 2024; fact pack §4). The best public thin-McKibben figure is >1M on air at 0.3 MPa, straight. The memo has "100,000(?)" (`source/legible-fragments.md`). Clone's 650K is "at 1 kg load", pressure unstated (CLAIMED, https://wevolver.com/article/could-this-lifelike-robotic-hand-be-the-start-of-a-humanoid-future). For Clone: bonding gave up to 10,000x durability (https://t2r2.star.titech.ac.jp/rrws/file/CTT100925838/ATD100000413/), ~5.5 fibres per DoF of redundancy, cheap fibres. **P(V1a \| E4) = 0.35** (shared hand engineering). | heroic (2x the best public figure at ~2x pressure, bent) | 0.30 | 0.35 | low |
| **E5** | E | **IP chain of title clean**: Koźlik's assignment covering 2014–21, the PL↔US transfer, and assignments from Baran, Świerk and Tarnowski. No claim by Koźlik. **By 2027-06-30** (A diligence; checkable now as DD P1 #5). | Form C: IP protected "through intellectual assignment and confidentiality agreements" (https://www.sec.gov/Archives/edgar/data/1958550/000195855023000003/cloneformc.pdf). Baran's valves date from after incorporation (same filing). The memo itself says it is "confirming IP assignment". | evidenced pending docs | 0.80 | 0.80 | low (historical) |
| **E3** | E | **Priced Series A closed.** (i) ≥$200M post by **2027-06-30**; (ii) any priced round by **2028-10-27** (= panel's 24-mo window). | PitchBook IV seed failure 38.6% (strict US definition) / count-basis A 23.6% (template E3). Against: the "$50M round" became a bridge (https://www.humanoidsdaily.com/news/the-synthetic-human-roadmap-clone-robotics-eyes-silicon-valley-and-20-000-price-points), and the memo says the "runway is short". For: sector money (Apptronik >$935M A, https://www.trendingtopics.eu/apptronik-raises-520-million-for-humanoid-robots-valuation-climbs-to-around-5-billion/). **Conditional on E4∧V1a∧E5: 0.85.** | plausible with evidence / heroic without | (i) 0.22 · (ii) 0.39 | 0.85 | med |
| **V2** | V | **Paid demand for dexterous stationary torsos and hands.** Lead indicator: first PAID (not LOI) named order by **2027-06-30** (tripwire #3), p_marg 0.35. Hurdle: **≥$10M ARR from third parties by 2029-12-31.** | CB Insights no-market-need 35% (2021 list) → 0.65 that the market exists. Against: no signed customer (memo); 2023 lab pre-orders never delivered (fact pack §3); Agility H1 2026 robot sales $0 (https://www.sec.gov/Archives/edgar/data/2074973/000121390026105334/ea0297114-05.htm); research segment held by Unitree at ~$23–25K (https://restofworld.org/2026/unitree-china-humanoid-robot-shanghai-ipo/). For: labs pay $50–125K for dexterous hands (Sharpa ~$50K, Shadow $110–125K; https://eu.36kr.com/en/p/3239621788565507). | plausible | ~0.08 (scale) | 0.55 | low |
| **E1** | E | **Production ramp**: ≥100 sellable units shipped in a trailing 12 months, with documented yield and capex within 2x of plan. **By 2028-12-31.** The literal memo claim ("10,000 Clones… a couple of million capex") is tested separately below. | RAND 1981 (~2x cost; 50–75% of nameplate in year 1); Merrow 65% miss (template E1). Agility analogue (VERIFIED, S-4/A): 10,000/yr designed capacity on low-single-digit-millions capex, yet minimal output (see E1 box). The bar here is low (100/yr). | plausible | ~0.08 | 0.65 | high |
| **E2** | E | **Key talent**: a CTO or head of hardware replacing Koźlik's muscle know-how, a commercial lead, and the FCC onshoring "dedicated officer", all named, in seat and retained ≥18 months; Baran retained. **By 2028-12-31.** | 40–50% failure per critical external senior hire within 18 months (Heidrick; DDI 2021; template E2). 2–3 critical hires. Three of four co-founders have gone (fact pack §3); the memo says "thin business team". Team score 2. | plausible | 0.40 | 0.60 | high |
| **V3** | V | **US market access.** (fixed torso) counsel opinion that a fixed/nonmobile torso is outside the Covered List, plus a first US sale, **by 2028-06-30**. (mobile) DoW Conditional Approval or a US line **by 2029-06-30**. | Late formal gates ~90% (ANALOGY), graded down for policy. "Fixed/nonmobile robots" are excluded (SECONDARY, https://www.cooley.com/news/insight/2026/2026-07-31-foreign-produced-power-inverters-and-advanced-robotic-devices-added-to-fcc-covered-list). 2 robot approvals as of 2026-09-18, each tied to an onshoring plan (VERIFIED, https://docs.fcc.gov/public/attachments/DA-26-996A1.pdf). | evidenced (fixed) / plausible (mobile) | fixed (favourable counsel opinion) ~0.80 · mobile ~0.35 | fixed 0.85 · mobile 0.70 | med (capital-gated) |
| **V1b** | V | **Whole-body water hydraulics, untethered biped walking.** Lead indicator: Clone's own date **2027-09-30**, p_marg 0.20. Hurdle: **by 2028-12-31.** Checkpoint: is Torso 4 water or air (Nov 2026)? | Pre-TRL4 ≈ 50% per major step (ANALOGY) × 2–3 steps never shown (legs, whole-body water, untethered) → 12.5–25% on time. Missed public dates: hand kits 2022, legs 2024, Alpha 2025 (sweep-company). A 2.3 kWh pack lasts 1.7–3.3 h at 0.7–1.3 kW (sweep-actuation, ANALYST). Leg muscles see 1.8–7.2M cycles/yr, so V1b needs V1a. | heroic on time / plausible late | 0.20 (on time) | 0.45 | med-low |

### E1 box — the "10,000 Clones for a couple of million dollars of capex" claim

- **Memo, illegible fragment, CLAIMED:** "production capacity for 10,000(?) Clones at a couple of million dollars of
  capex" (`source/legible-fragments.md`).
- **Agility RoboFab, VERIFIED** (S-4/A,
  https://www.sec.gov/Archives/edgar/data/2074973/000121390026105334/ea0297114-05.htm):
  - RoboFab "has a designed production capacity of up to 10,000 robots annually and was built to enable production
    capacity to expand efficiently with relatively modest incremental capital investment."
  - Purchase of property and equipment: **$3.90M (FY2024), $2.55M (FY2025), $2.32M (H1 2026).**
  - PP&E net $15.9M at 2025-12-31. That figure is "primarily robots deployed under robot deployment arrangements,
    construction in progress, and manufacturing equipment", and includes $10.1M of inventory transferred in.
  - Management's projected capex is **"approximately $8 million total between 2026 and 2028"**.
  - H1 2026 robot sales were **$0** (verify-market #4).
- **ANALYST:** humanoid nameplate capacity is cheap to claim and says nothing about output. The binding constraints are
  demand, BOM, yield and working capital (Agility carried $12.9M of inventories). Clone's claim is the same order of
  magnitude as Agility's, so it is *not* REFUTED. It earns no Delivery credit either.
- **ANALYST, the difference:** Clone makes muscles and valves in-house. At Torso 2's 910 fibres
  (https://www.youtube.com/feeds/videos.xml?channel_id=UCd0xLOw6No5IAsq3Y2-b0eA) and the Alpha spec's 320 pressure
  channels (https://www.clonerobotics.com/android/), 10,000 robots a year means **~9.1M fibres and ~3.2M valve channels
  a year**. Precision valves, not braiding machines, are the likely capex sink.
- **P(literal claim holds: ≥10,000/yr output on ≤~$5M capex by 2029) < 0.05** (ANALYST).

### Correlation structure (stated, as the template requires)

| link | structure | how modelled |
|---|---|---|
| E4 ↔ V1a ("hand physics" cluster) | Mild positive: the same team and fibres, and hysteresis limits force control | P(V1a \| E4) 0.35 vs 0.30 marginal |
| **V1a, E4 → E3 (cross-family common mode — the red team's point)** | **Strong.** The A lead diligences exactly these two; the runway cannot absorb a muscle redesign | P(A ≥$200M by mid-2027 \| both) 0.70 · \| one 0.25 · \| neither 0.10 → marginal 0.22 |
| E1, E2, E3, E4 (organisational common cause) | Template rule 2: w = (team−1)/4 = 0.25 at team 2 | Cross-check below; sensitivity at team 1.5 / 2.5 |
| E3 → E1, E2, V3-mobile, V1b (capital gate) | Downstream hurdles need A money | Conditionals set given E3 passed |
| V2 ⟂ V1 (demand vs physics); V3 ⟂ others except via capital | ~independent mechanisms | multiply |
| Absorbing failures | V1a (the muscle is the moat; a redesign cannot be funded), E5 (a Koźlik claim) | modelled as terminal |

**The template has a gap.** Rule 2 multiplies V as independent and correlates only within E. It has no term for a V
hurdle that *drives* an E hurdle (V1a → E3). Here that coupling raises P(all pass) by ~1.26x over the rule-2
number (1.30% vs 1.03%; 0.48% vs 0.38%). The chain rule handles it. A rule change, if any, is proposed only at R2 (rubric §5).

### Combination

| path | chain (central) | pessimistic set | optimistic set | template rule 2 (w 0.25) | rule 2 at team 1.5 / 2.5 |
|---|---|---|---|---|---|
| Stationary torso / hand: E4 · V1a · E5 · E3 · V2 · E1 · E2 · V3-fixed | **1.30%** | 0.42% | 4.23% | 1.03% | 0.67% / 1.40% |
| Full humanoid: the same plus V1b, with V3-mobile | **0.48%** | 0.11% | 2.07% | 0.38% | 0.25% / 0.52% |
| Core pair only (E4 ∧ V1a), resolves ≤2027-06-30 | **10.5%** | 7.5% | 18% | — | — |

Notes on the inputs:
- **Pessimistic and optimistic sets** shift every p_cond by roughly ±0.05–0.10; the values are in the companion
  python lines (reproducible).
- **Rule-2 inputs:** V side (torso) = 0.30 × 0.55 × 0.85 = 0.140; V side (humanoid) = 0.30 × 0.55 × 0.45 × 0.70 = 0.052;
  E side = 0.75 × Π(0.65, 0.60, 0.23, 0.30, 0.80) + 0.25 × min = **0.074**.

**From P(all pass) to exit odds (ANALYST)**

- **P(≥10x) = P(torso path) × P(exit ≥$7.3–12.7B \| pass) + windfall.**
  - P(humanoid \| torso passes) = 0.37.
  - P(≥$7.3B \| humanoid pass) ≈ 0.5. Comparators: Apptronik ~$5B, 1X ~$6B in talks, Figure $39B (fact pack §5).
  - P(≥$7.3B \| torso-only pass) ≈ 0.15. Comparator: Linkerbot $3B, $6B target (see (d)).
  - So P(exit ≥$7.3B \| pass) ≈ 0.28, and the path term is 1.30% × 0.28 = **0.36%**.
  - Windfall: a strategic paying ≥$3.6–7.3B before the hurdles resolve, 0.2–0.5%.
  - **Total ≈ 0.66% central (0.27% pessimistic, 2.17% optimistic).**
- **The conjunction-bias caveat applies.** Chains of 8 judged conditionals tend to understate, because the omitted paths
  are missing. The windfall term is the explicit allowance. Even so, the optimistic set does not reach 2.5%.

**Comparison with the panel** (house model `models/exit_curve.py`, seed base, SPV 2/20, capped at 20x; run unmodified)

| forecast | panel | red team | hurdle-implied (central, band) | direction |
|---|---|---|---|---|
| P(≥10x) | 0.025 | 0.025 | **0.007 (0.003–0.022)** | **DOWN** |
| P(next priced round ≤24mo) | 0.45 | 0.40 | **0.39 (0.34–0.44)** | slightly DOWN |
| P(priced A ≥$200M by mid-2027) | — | ~0.25 | 0.22 | agrees with red team |
| P(<1x) | 0.85 | 0.86 | 0.85 is consistent: P(≥1x) ≈ core pair 10.5% × ~0.7 + other paths ~7.5% ≈ 15% | — |
| **EV net (capped 20x) at P(<1x) 0.85** | **1.08x** | 1.05x | **0.88x (0.84–1.05x)** | **DOWN, below 1x** |

House-model reproduction: (0.85, 0.025) → 1.079x, which matches the fact pack. At P(≥10x) of 0.003 / 0.007 / 0.015 /
0.022 the model gives 0.837x / 0.881x / 0.969x / 1.046x. The uncapped-tail premium is 0.08 / 0.18 / 0.39 / 0.57x.

**Read (ANALYST):**
- **The panel's 2.5% has no named path in the hurdle tree that supports it.** S2 should make the panel name the
  path or move the number. Per rubric §4.5, both are logged and never averaged.
- **Waiting is cheap.**
  - The core pair resolves inside ~8 months.
  - In the 10.5% world where it passes, an A is ~85% likely and Casey can enter there at a step-up.
  - In the ~89.5% world where it does not, the bridge is mostly a loss.

---

## (b) DUTY-CYCLE RECONCILIATION

**The two bars [VERIFIED arithmetic; assumptions ANALYST]**
- **Bar A** (sweep-actuation): 8 grasps/min, 1 contraction per grasp per flexor muscle, 8-h shifts, 250 d/yr.
  - 0.96M/yr on 1 shift, 1.92M on 2 shifts, **4.032M at 24 h × 350 d**.
  - **The fact pack's "24/7" column is 350 d, not 365.** A literal 24 × 365 gives **4.205M/yr (+4.3%)**. Life *in
    operating days* is unchanged; calendar life shortens by 4.1% (650K: 0.161 → 0.155 yr). Hygiene only.
  - Source: `sweeps/sweep-actuation.md` durability table, confirmed by `verify-actuation.md` row 10.
- **Bar B** (sweep-market): BMW 84 s cycle, 10-h shifts × 2 × 250 d, 1 contraction per cycle → **214,286/yr**; a
  5-year life needs 1.07M.
  - Cycle requirement CLAIMED by Figure: https://www.figure.ai/news/production-at-bmw.
  - Arithmetic confirmed by verify-market §4.
- **Ratio: 8.96x a year** = 11.2x per minute (8/min vs 0.714/min) × 16/20 h a day.

**Which bar applies where (ANALYST), and what 650K and >1M imply**

The two ratings:
- **650K** is CLAIMED, 2023 press, "at 1 kg load", pressure unstated
  (https://wevolver.com/article/could-this-lifelike-robotic-hand-be-the-start-of-a-humanoid-future).
- **>1M** is s-muscle, on **air at 0.3 MPa, straight**, not Clone (fact pack §4).

**Neither is at Clone's 0.69–1.0 MPa rating, and neither is bent.** Treat both as optimistic characteristic lives η.
The "first fibre" column uses Weibull with N = 74 fibres (2 hands) and β = 3: factor 0.213. Redundancy (~5.5 fibres
per DoF) may make that failure graceful rather than fatal.

| segment | duty assumption | contractions / yr | 650K life | >1M life | first fibre @650K | which bar |
|---|---|---|---|---|---|---|
| Line-rate automotive (Figure/BMW-type) | 84 s, 1 contraction/cycle, 2 × 10 h | 214K | 3.03 yr | 4.67 yr | 0.65 yr | **B** |
| — same, realistic finger use | 84 s, 3 contractions/cycle (pre-shape, grasp, regrasp) | 643K | 1.01 yr | 1.56 yr | 0.22 yr | B ×3 |
| **High-mix bench assembly (Clone's #1)** | 8/min, 1 shift | 960K | 0.68 yr | 1.04 yr | 0.14 yr | **A** |
| — two shifts | 8/min, 2 × 8 h | 1.92M | 0.34 yr | 0.52 yr | 0.07 yr | A |
| — 24 h × 350 d (fact pack "24/7") | 8/min | 4.03M | 0.16 yr | 0.25 yr | 0.03 yr | A |
| — 24 h × 365 d | 8/min | 4.20M | 0.155 yr | 0.24 yr | 0.03 yr | A |
| Research lab | 4/min, 2 h/day, 250 d | 120K | 5.42 yr | 8.33 yr | 1.15 yr | below B |
| Data factory (AgiBot-style) | 6/min, 2 × 8 h, 250 d | 1.44M | 0.45 yr | 0.69 yr | 0.10 yr | ≈A |
| Home | 4/min, 2 h/day, 365 d (sweep-actuation) | 175K | 3.71 yr | 5.71 yr | 0.79 yr | below B |

**What follows (ANALYST)**
1. **Neither sweep was wrong. They describe different jobs.** Bar B fits takt-paced line work, where one big grasp is
   made per cycle. Bar A fits bench and data-factory work, which is grasp-dense. Counterpoint's "Data Production &
   Research" bucket mixes low-duty labs with high-duty data factories.
2. **The durability bar is anti-correlated with Clone's segment ranking.**
   - Bench assembly, ranked #1, faces the hardest bar. It needs **≥2M at working pressure** (tripwire #4), or 5.8M for
     a 3-year asset life on 2 shifts.
   - The segments where 650K already suffices are research labs and the home. Research is Unitree-entrenched at
     ~$23–25K. Home needs the biped, safety certification and battery life.
3. **A consumable-fibre model can change the bar**, if fibres are cheap and hot-swappable. Replacing a few dollars of
   fibre every 0.3–0.7 yr on a bench robot is a service cost, not a product failure. Whether a fibre swap is a
   minutes-long field job or a teardown is the DD question.
4. **Data for an exhibit:** the table above as horizontal bars on a log scale, with vertical lines at 650K, 1M, 2M and
   10M (?). The intake `exhibits.html` "muscle life" exhibit can be re-cut by segment.

---

## (c) BOTTOM-UP SAM (units × price × reachable share, dated)

| segment (Clone rank) | units (dated) | price (dated) | pool $/yr | reachable filter (ANALYST) | Clone share if the product works (ANALYST) | Clone $/yr (2027–28) |
|---|---|---|---|---|---|---|
| **Research & data torsos** (#3 in fact pack; nearest-term) | 27.0% × >22,000 (H1 2026) = ~5,940 per half → **~11.9K/yr**; 13.5K if the mix held on the >50K 2026 forecast. SECONDARY/VERIFIED: https://www.humanoidsdaily.com/news/global-humanoid-shipments-surpass-22-000-in-h1-2026-as-agibot-leads-and-form-factor-debates-intensify ; https://counterpointresearch.com/en/insights/global-humanoid-robot-shipments-soar-nearly-300-percent-yoy-in-h1-2026 | Unitree average price **RMB 167.6K ≈ $23–25K** (2025, prospectus). SECONDARY: https://restofworld.org/2026/unitree-china-humanoid-robot-shanghai-ipo/ | **$274–338M** | Non-Chinese buyers 15–30% × needs a high-DoF hand 30–50% → **0.5–1.8K units** | 5–15% at $40–60K (no Clone price exists: https://clonerobotics.com/pre-order/) | **$1.1–16M** |
| **Hands / muscles as components** (#2) | Linkerbot "almost 5,000 units a month" with ">80%" of high-DoF volume (CEO, via Reuters, 2026-05-04) → high-DoF market **≤~75K hands/yr**. A ceiling, because the 5,000/mo may include low-DoF hands. SECONDARY: https://www.thestandard.com.hk/innovation/article/331016/China-robot-hand-building-unicorn-Linkerbot-targets-US6-billion-valuation | Linker O7 ~$1.2K; 25–30 DoF ~$7K (2025-04-08; SECONDARY, not re-fetched: https://eu.36kr.com/en/p/3239621788565507). Unitree Dex5-S $6,350 (VERIFIED: https://shop.unitree.com/) | **$90–525M** | Non-Chinese third-party buyers 10–20%. Western OEMs build in-house (Tesla 22-DoF; 1X; BD new hand), and Tesla litigated hand IP (SECONDARY: https://thenextweb.com/news/proception-robot-hand-tesla-trade-secret-settlement-seed-round) → **7.5–15K hands** | 5–20% at $5–7K. Components sit outside the FCC "mobile robot" listing (ANALYST) | **$1.9–21M** |
| **High-mix bench assembly** (#1) | Western industrial-robot installs 2024: **US 34,200 + EU 67,800 = 102K** (VERIFIED: https://ifr.org/ifr-press-releases/news/global-robot-demand-in-factories-doubles-over-10-years). Cobots ~11–12% (SECONDARY: https://inzonex.co.uk/ai/reports/state-of-industrial-automation-and-robotics-2026) → **~11–12K cobots/yr**. Humanoids to manufacturing: 12.8% × 22K ≈ 2.8K in H1 2026, mostly Chinese (SECONDARY, Humanoids Daily above) | UBTech ~**$90K** revenue per full-size unit (H1 2026: RMB 590.3M / 921 units; VERIFIED: https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0828/2026082801691.pdf). Agility RaaS $8,500/mo (S-4/A) | **$45–180M** (500–2,000 Western dexterous-bench torsos/yr by 2027–28, ANALYST: ~5–15% of the Western cobot flow being dexterity-limited) | Western, stationary, high-DoF | 0–5%, gated by E4 and the ≥2M-cycle bar (b) | **$0–9M** |
| Home / housekeeping (#4) | 1X NEO capacity 10K/yr; deliveries unverified (SECONDARY: https://blog.robozaps.com/b/1x-neo-release-date-rumors-news) | $20K or $499/mo (SECONDARY: https://en.wikipedia.org/wiki/1X_Technologies) | n/m before 2028 | Needs the biped (V1b), certification, battery | — | **~$0 before 2028** |
| **Total** | | | **~$0.4–1.0B/yr** (2026–27, growing ~2–3x/yr on Counterpoint's +210% 2026 forecast) | | | **$3–46M/yr if E4 ∧ V1a pass (p ≈ 0.105)** |

**Which market should the panel's Market score refer to? (ANALYST)**
- **The SAM above.** That is the market Clone can reach with the product it will have before its next round: a
  stationary torso plus hands, outside China. It decides the Series A.
- **Not the humanoid TAM.** The panel's stated anchor ("a real, fast-growing category, 13,317 units in 2025") is TAM.
  So is Goldman's $38B by 2035 (https://goldmansachs.com/insights/articles/the-global-market-for-robots-could-reach-38-billion-by-2035).
- **On rubric v1.1** ("3: real market, bottom-up possible but thin"; 5 requires demonstrated elasticity), the SAM
  supports **3 at most**:
  - the pool is real and buildable bottom-up;
  - Clone's reachable slice is $3–46M a year only if the core pair passes;
  - the largest pool (research) is Chinese-held and losing share (Counterpoint, above).
  - **Case for 2.5**, as one scorer and the red team already had it.
- At the house weights, Market 3 → 2.5 moves **W 2.18 → ~2.03**, below the Vernius floor of 2.05.
- **Elasticity:** none demonstrated. Unitree's price fell 72% between 2023 and 2025, and volume grew, but in
  research and entertainment, not dexterous work (verify-competition row 18).
- Clone's $200M post is **4–65x** the band's revenue. Sector marks are not revenue-based anyway: Agility's $2.5B was
  struck on $1.78M of sales (S-4/A).

---

## (d) EXIT-PATH / ACQUIRER MAP

**Price evidence**

| deal / mark | terms | tag / source | read for Clone (ANALYST) |
|---|---|---|---|
| **Mobileye ← Mentee** (pre-product humanoid) | **$900M, closed 2026-02-03.** Shashua (Mobileye CEO) **37.83%, ~$341M**; Shalev-Shwartz (Mobileye CTO) **13.07%, ~$118M** | VERIFIED: https://www.sec.gov/Archives/edgar/data/0001910139/000110465926048118/tm261530-1_def14a.htm. Split: $612M cash + 26.28M shares per the search summary of the filing and TechCrunch; the fetch summarised it as "evenly" — minor CONFLICT, not load-bearing | **~51% of the price went to two sitting executives of the buyer.** Related-party; a ceiling, not a comp. The fact pack's "$200M ≈ 1.23x Mentee" mitigation is weaker than stated (Deal 1.5 holds) |
| SoftBank ← ABB Robotics | **$5.375B** for a business with $2.28B revenue (2024) and ~7,000 staff. Agreed 2025-10-08; closing expected mid-to-late 2026; **close NOT FOUND** | SECONDARY via search of the primary: https://group.softbank/en/news/press/20251008 ; https://www.techrepublic.com/article/news-softbank-acquires-abb-robotics/ | Strategics pay ~2.4x revenue for scaled robot revenue. Clone has none |
| SoftBank → 1X majority (talks) | ~$6B, down from a $10B ask; no units shipped | SECONDARY: https://en.cryptonomist.ch/2026/08/27/softbank-1x-technologies-acquisition/ | The humanoid-platform ceiling for a company with a walking robot |
| Samsung → Rainbow Robotics | KRW 267B (~$181M) to reach 35%, largest holder (Dec 2024) | SECONDARY: https://ceomorningbrief.theedgemalaysia.com/article/2025/0889/World/17/739438 | Korean strategics buy control of robotics firms at sub-$1B scale |
| LG → Bear Robotics | stake raised to 51% via a call option attached to a $60M investment; price undisclosed | SECONDARY: https://www.kedglobal.com/robotics/newsView/ked202501240002 | Option-to-control structures. Watch for a ROFR in Clone's bridge or A |
| Linkerbot (hand volume leader) | $3B Series B+; $6B target; ~5,000 hands/month | SECONDARY (Reuters reprint): https://www.thestandard.com.hk/innovation/article/331016/China-robot-hand-building-unicorn-Linkerbot-targets-US6-billion-valuation | The best hand-company mark — and it rests on volume Clone does not have |
| Sanctuary AI (closest hydraulic-hand peer) | ~$140M raised; $393–425M (Jul 2024, CB Insights) vs Dealroom's $100–500M band (2026) — CONFLICT. CEO since Jun 2026 is Friedmann, who sold Carbon Engineering to Occidental for $1.1B | SECONDARY: https://thelogic.co/?p=2136150 ; https://www.cbinsights.com/company/sanctuary-1/financials ; https://dealroom.co/companies/sanctuary-ai/ | The hydraulic-hand precedent clears at ≤~$0.5B. A chair-to-CEO dealmaker suggests a sale (ANALYST) — and possibly a consolidation partner or rival bidder |
| Locus ← Nexera (grasping) | reported 2026-05-20; price n/a | SECONDARY: https://techcouver.com/tag/nexera-robotics/ | Grasping tech is bought as tuck-ins |
| Agility SPAC | $2.5B on $1.78M FY2025 sales | VERIFIED: https://www.sec.gov/Archives/edgar/data/2074973/000121390026105334/ea0297114-05.htm | The public-market route exists for a US-built, walking, revenue-bearing humanoid |

**Who could buy Clone, at what price, after what proof (ANALYST)**

| acquirer class | named candidates | why | price band | requires first | P(this exit) |
|---|---|---|---|---|---|
| Acqui-hire / IP sale (failure state) | humanoid OEMs, AI labs | team + braiding/valve know-how | <$150M (red team) | nothing | ~0.25 (red team, fact pack §8.4) → ~0x after preferences |
| Humanoid OEM without a differentiated hand | Mobileye/Mentee, SoftBank (1X, ABB), Hyundai/BD, Samsung/Rainbow, LG, Agility post-SPAC, Apptronik | buy a hand rather than build one | $0.3–1B (Mentee-class) | E4 + V1a (core pair) | ~0.06–0.08 → 1–3.5x net |
| Fluid-power / motion majors | Parker, Danfoss, Bosch Rexroth, Festo (already sells fluidic muscle DMSP), SMC | component line extension | revenue multiple, sub-$0.5B pre-revenue | V1a + component revenue | low; NOT SEARCHED |
| Big tech / foundation-model labs | Google DeepMind (Apptronik partner), Meta (a 2023 "customer", CLAIMED), Nvidia, Amazon | embodiment hardware | $0.2–1B | E4 | low |
| Chinese hand makers | Linkerbot, AgiBot spin-off AGILINK | consolidation | — | — | ~0: EU/US screening (ANALYST) |
| IPO or platform outcome | — | — | $7.3–12.7B needed for 10x | all hurdles + biped | ~0.2–0.5% (section a) |

**Net read (ANALYST):** the modal positive exit is a **strategic sale at $0.3–1B after the core pair passes**. At 50–80%
dilution that is ~1–3.5x net (fact pack §7 return table). 10x requires the Linkerbot path to double ($6B+ at ≤50%
dilution) or a humanoid-platform outcome. That supports the downward move on P(≥10x) in (a), and changes nothing for P(<1x).

---

## NOT SEARCHED (budget discipline; not NOT FOUND)

- Hand, actuator and gripper M&A prices beyond those above: Hyundai–BD terms, Amazon–Covariant terms, Teradyne–UR/MiR,
  and fluid-power deals (e.g. Danfoss–Eaton Hydraulics). The fluid-power acquirer row is therefore unpriced.
- The IFR primary figures for cobot share and the electronics/aerospace split of installations. The press release was
  fetched and has neither; the full report is paywalled. The cobot ~11–12% is SECONDARY.
- An industrial-engineering (MTM) grasp-rate standard for bench assembly. **8/min is ANALYST.**
- The research-buyer geography (non-Chinese share) and the share needing high-DoF hands. **Both SAM filters are ANALYST.**
- Linkerbot's unit mix (high- vs low-DoF within ~5,000/mo). The O7 $1.2K and $7K prices were not re-fetched; they are
  carried as SECONDARY from 36kr (2025-04-08).
- Figure BotQ and Tesla Optimus line capex (Agility's S-4/A was used as the E1 anchor instead).
- SoftBank–1X status after 2026-08-27. SoftBank–ABB close: searched once, **NOT FOUND**.
- Clone's current roster and hiring (LinkedIn was blocked at intake). Whether Baran and Wieczorek remain is unknown.
- A hardware-specific Series A failure base rate. Used the template's PitchBook brackets.

---

## NEW DD QUESTIONS — RANKED (append to the fact-pack ledger; all ○ not yet asked)

**P1 — decision-gating**
1. (C) **Design duty cycle per segment for Torso 4**: grasps per minute, contractions per grasp per muscle, hours per
   day. State the cycle-life spec that follows from them. Provide the test logs behind "650K at 1 kg" and "100,000(?)":
   pressure, stroke, bend radius, fluid, failure mode. *Moves:* V1a, and whether bench assembly or research/home leads.
2. (S+C) **Series A process**: the lead or leads in diligence and the stage reached (the memo says the process "begins
   week of November 9"). Which gates have they set (autonomy, cycle life, IP)? Runway in months if the A slips to
   Q4 2027. *Moves:* E3; P(priced round ≤24mo); the waiting decision.
3. (C) **Fibre field-replacement**: minutes per fibre swap, whether hot-swappable, cost per fibre, and the maintenance
   interval in hours. *Moves:* whether the ≥2M bar in (b) is binding, or a service cost instead.
4. (C) **The "10,000 Clones for a couple of million capex" build**: scope (braiding only, or valves and final assembly
   too); nameplate vs demonstrated output; units built to date; yield; valve-channel capacity per month. *Moves:* E1,
   Delivery score.

**P2 — score-moving**
5. (C) **Hiring plan after Koźlik**: a named CTO or head of hardware, a commercial lead, and the FCC onshoring "dedicated
   officer". Baran's status; the option-pool reserve. *Moves:* E2, Team.
6. (C) **Torso 4 list price and named buyers by segment** (research labs vs bench assembly vs data factories), priced
   against Unitree's ~$23–25K average. *Moves:* V2, Market (SAM share).
7. (C) **Hand-as-component**: any OEM talks to buy Clone hands or Myofibers; hand price at 1K and 10K units vs
   Linkerbot's ~$7K 25–30 DoF. *Moves:* V2 (component path), exit map.
8. (C) **Strategic interest and rights**: any inbound acquisition approach, strategic investor, ROFR/ROFN or
   option-to-control (the LG–Bear structure) in the bridge or A documents. *Moves:* the exit map; P(≥10x) windfall
   branch; the Deal terms.
9. (C) **Leg-muscle duty and life target** (about one cycle per stride: 1.8–7.2M a year) and the fluid in Torso 4.
   *Moves:* V1b.

**P3 — completeness / process**
10. (internal) **Log the hurdle p_marg values in `ledger.csv`** with their resolution dates for hurdle-level Brier
    scoring (template rule 4). First resolutions: E4 2027-03-31; V1a, E3(i) and E5 2027-06-30; V1b on-time 2027-09-30.
11. (internal, for R2) **Rule-2 cross-family coupling term** (V → E). Propose at R2 only; never retroactive.
