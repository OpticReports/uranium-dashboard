# Clone Robotics — grounded fact pack (2026-10-27, rev 2 — PRE-DD)

> **REV 2 (same day): the memo is now legible** (pages 1–5 and 7 at full resolution;
> transcript `source/memo-transcript.md`). Everything it changed, verified by a fourth
> workflow (3 passes, each adversarially checked), is in **§12** — read §12 first.
> Sections 1–11 are corrected where the memo overturned them. **Panel scores and
> forecasts are NOT yet re-run**: held for memo page 6 (Risks) per the house rule.
> Page 6 and the deck are still not supplied.

Provenance tags: [VERIFIED] primary source · [SECONDARY] third-party · [CLAIMED]
company or sponsor statement, unverified · [CONFLICT] · [REFUTED] contradicted by a
primary source · [NOT FOUND] searched, absent · [ANALYST] our own estimate.

Ninth ledger row; **third Delta4 vehicle** (after DexMat and Quaise). **Pipeline (process v1.2, cost-discipline rules):
13 agents in one workflow — 6 evidence sweeps, each adversarially verified (2
independent verifiers on Casey's tactile crux). Every verifier returned APPROVED
WITH CORRECTIONS; all 92 corrections are applied below** (2.54M tokens, 995 tool
calls, 0 agent errors). **Scoring: 5-scorer panel + red team + completeness critic**
(§8); the critic's 13 errors are corrected below and its gaps went to a third
workflow (§11). Sweep and verifier files with every source URL: `sweeps/`.

**Search-coverage caveat (critic):** the intake sweeps exhausted their web-search
budget partway, and the verifiers ran few searches. Where an absence below rests on
an incomplete search it is tagged NOT FOUND (incomplete); §11 records the re-run.

### Documents

| document | read | notes |
|---|---|---|
| Delta4 Capital memo "Clone Robotics — Bridge round", Alex Golding, dated 2026-10-27 | **YES — pages 1–5, 7 (rev 2)**; **page 6 NOT SUPPLIED** | First arrived as a 310 px screenshot (`source/legible-fragments.md`, rev 1); full-resolution pages supplied by Casey later the same day (`source/memo-p1..p5.webp`, transcript `source/memo-transcript.md`). Page 6 (end of "What could go right", start of Risks) known only from the rev-1 fragments. |
| Clone deck (same viewer) | **NOT READ** | 121 px wide; only some slide titles legible |
| **Valuation $200M post-money** | **YES — LP, 2026-10-27** | Supersedes our misread "$3?0M" — proof that the screenshot's numbers cannot be trusted |
| Raise size, committed, SPV fees, cash, burn, Series A size | **YES (rev 2)** | $9M target, $6.5M committed, close Nov 3; 2% one-time + 20% carry + pro-rata SPV fees; $2.5M cash, $750–900K/mo burn; Series A $70–100M. **Instrument still not stated.** |

---

## 0 · THE ONE-LINE READ

**A genuinely different actuator (water-hydraulic artificial muscles) attached to
a company that has not yet shown the things a $200M price assumes: no walking
robot, no autonomous grasp, no signed customer, no cycle-life data at working
pressure, no patents found, and three of its four co-founders gone — offered
through a sponsor with no SEC-visible close on any of its three 2026 pitches to
this LP (Quaise, DexMat, Clone).**
On Casey's crux: **partly right.** Clone has no touch sensing *by published design*
("only proprioceptive and visual feedback"), but it does have a grip-force channel
(muscle pressure). The bigger gap is that no autonomous grasp has ever been shown.

---

## 1 · THE ASK

| | |
|---|---|
| Round | Pre-Series A **bridge** (memo heading) |
| Price | **$200M post-money** (LP) |
| Check | ~$50K via **Delta4 Capital SPV** |
| SPV terms | "2% one-time fee, 20% carried interest, plus a pro-rata share of SPV fees" (memo p.1, CLAIMED; the SPV-fee share is uncapped as written). Delta4's three filed Form Ds instead disclose ~5% related-person fees ("1%/yr × 5") [VERIFIED] — CONFLICT |
| Raise / committed | **$9M target; $6.5M committed** (memo p.1, CLAIMED) |
| Instrument | **NOT STATED** — SAFE, note or priced? (G4) |
| Close | **November 3, 2026** (memo p.1); Series A investor demos from the week of Nov 9; Delta4's in-person visit Nov 12 — **after** the close |
| Next round | Series A, **$70–100M** target; Series B "$1–2B target" Q4 2027 (memo) |
| Entry ownership | $50K ÷ $200M = 0.025% gross; **~0.024% net** of the 2% fee and admin share |
| Filing of record | **None.** Clone has never filed a Form D (its SAFEs went under §4(a)(2)); no Delta4 Form D for any Clone series [VERIFIED, EDGAR] |

---

## 2 · CASEY'S CRUX — does the hand know how hard it is gripping?

**Verdict: PARTLY TRUE. No touch; yes force; and the decisive gap is elsewhere.**

**What Clone has [VERIFIED, first-party].** Clone's live android page (bundle
`/_nuxt/D8GOK2Ld.js` on https://clonerobotics.com/android/, prerendered 2026-07-02):
the robot is "designed for instantaneous neural control of the valves… **with only
proprioceptive and visual feedback**": **4 depth cameras** (in the skull), **70
inertial sensors** (joint angles/velocities) and **320 pressure sensors "for
muscle-level force feedback."** Zero hits for tactile / fingertip / touch sensor /
haptic / slip across 6 pages and 22 JS bundles, nor in the 2023 SEC Form C. **No
touch is a published design choice, not an omission.** The "pressure pads in the
palm" in Interesting Engineering (2025-11-24) trace to no first-party source → CONFLICT.

**Why "no feedback" is still wrong [VERIFIED / ANALYST].**
- A pressure-regulated McKibben muscle **commands and caps its own force** via
  its pressure setpoint — force control without touch, which stiff geared hands
  can't match (1X: at 100–200:1 gearing "friction swallows the contact forces",
  https://www.1x.tech/discover/neos-hands).
- The leaders' *primary* force channel is the same kind. Boston Dynamics' new
  Atlas hand relies "on proprioception for agile dexterous behaviors", with touch
  "complementary" (https://www.therobotreport.com/boston-dynamics-drops-pinkie-on-new-humanoid-hand/).
- The only clean ablation separating them (RDP, https://arxiv.org/abs/2503.02881):
  intrinsic force from joint-torque sensors **beat** GelSight fingertip touch on all
  three contact-rich tasks (peel 0.95 vs 0.90; wipe 0.87 vs 0.77; lift 0.70 vs 0.48).
  MoDE-VLA: removing proprioceptive force cost −11 pp, removing touch −8 pp
  (n = 20 per task, full-model success only 34% — the difference is within noise).

**Where Casey is right [VERIFIED].**
- **Accuracy at light grips is unproven.** Geometry-only force models for water
  McKibben muscles err ~9–10% (calibration could do better — pessimistic, not a
  floor). Clone has published **no** measured grip-force accuracy. Rivals' fingertips
  detect 3 g (Figure 03), 5 mN (Sanctuary, CEO claim), 0.005 N (Sharpa).
- **Touch measurably helps on the hard tasks:** like-for-like gains of **+14 to
  +35 pp** on fragile, slippery, occluded and insertion tasks (Calandra 2018 +24–31 pp
  averaged; 3D-ViTac +20–35 pp). It is not free: naive fusion can hurt (ResTacVLA −5;
  3D-ViTac hex-key 0.65 → 0.50).
- **Every leader now ships or announces touch:** Figure 03, 1X NEO, Atlas, Tesla,
  Sanctuary, Sharpa, Unitree Dex5-1P (the base Dex5-1 has none). **Clone is the
  outlier.** 1X: "vision alone is insufficient for many tasks."

**The bigger gaps nobody asked about [VERIFIED].**
1. **No autonomous learned grasp has ever been shown.** Public hand demos are
   teleoperated (Torso 3 hand, X 2026-10-01: "Teleoperation of the Hand of
   Torso 3" — "an older hand design") or scripted (Torso 2 "hardcoded sequences";
   V19 "manually preprogrammed").
2. **Shipped hardware carries far fewer sensors than the spec.** Torso 2 (Dec 2024):
   182 sensors for 910 fibres and 164 DoF. Protoclone (Feb 2025): "over 200 sensors"
   for ">1,000 Myofibers". Hand joint-angle feedback was re-added ~Apr 2026 (2022
   hands had 16 magnetic encoders; torso-era hands dropped them). The 4/70/320 is the
   **Alpha pre-order spec**, not demonstrated hardware.
3. **No close-range cameras.** The no-touch successes in the literature (ACT, Gemini
   Robotics) run on ALOHA with **wrist cameras**; Figure 03 added a palm camera per
   hand. Clone discloses only 4 depth cameras in the skull — it lacks both of the
   things that substitute for each other.

**Human evidence, read carefully.** Augurelle 2003: numbed fingertips → 36% drops,
but during 30 s of 1 Hz, 20 cm oscillation; in static holds subjects raised their
safety margin. The failure mode (a decaying human set-point) transfers only weakly
to a pressure-held robot grip.

**What would settle it (P1):** a per-hand Torso 4 sensor sheet; measured fingertip
force estimated from pressure vs a load cell (N, % FS, hysteresis, smallest
detectable contact); and a live **autonomous** demo — egg, paper cup, grape, plug
insertion, slip recovery, ≥20 trials each.

---

## 3 · THE COMPANY

| finding | tag |
|---|---|
| **Clone Inc.**, Delaware, incorporated 2021-10-12 (CIK 1958550); owns 100% of **CLONE sp. z o.o.**, KRS 0000947589, Wrocław. Mountain View office rests on CEO remarks. | VERIFIED / SECONDARY |
| **Co-founder Łukasz Koźlik** — credited in Clone's own Form C with designing the hydraulic valves and McKibben muscles; largest holder Feb 2023 (3.0M shares, 43.54% of issued voting stock). **KRS entry 16 (2026-03-18) removed him from the Polish subsidiary's board**; Radhakrishnan is now its sole member. Departure from Clone Inc. is ANALYST (consistent with the memo's "co-founder who has since left"). Caplight still lists him as CTO. | VERIFIED / ANALYST |
| **IP origin is not all his:** the same Form C credits **Michał Baran** (Chief Designer, since 2022) with "5X miniaturized fast valves" and mass-production technology for hands; Clone names its own "Aquajet valve technology". | VERIFIED (in their favour) |
| **Patents:** Form C (Feb 2023) "does not have any registered patents" — IP held as trade secrets under assignment agreements — yet its risk factors cite "our pending patents" (self-contradiction). **No Clone-owned patent under any team name** (rev 1.1: Google Patents for all six people and both entities; Espacenet/WIPO/UPRP direct blocked; filings after ~Apr 2025 would not yet be public). Memo: "Clone says its technology is patented" — **literally defensible only if it means licensed Adaract patents**; false for Clone-owned IP. The licence is also a **US freedom-to-operate dependency** if Clone practises those claims (no claim mapping done). | VERIFIED / NOT FOUND |
| **Financing record:** 2021–22 SAFEs $525K at a **$50M post cap**; 2023 Reg CF Crowd SAFE at a **$30M cap** (a down-cap) — **withdrawn**; $74,275 cash on 2023-01-31 (~3 months runway). Then a **2023 seed (~$6–6.5M, Initialized lead with Pioneer, Tango, Lux, Wikus, Access VC — SECONDARY)**, a Jan/Feb-2025 round and a 2026-03-10 VC round (Caplight) — instruments and caps unknown, so **the last mark is UNKNOWN (P1)**; rev 1.1: **no priced round found** (lean: none ever), the last *public* mark is the 2021–22 $50M SAFE cap (bought by angels), Initialized lists Clone on its own portfolio page (VERIFIED), and Pioneer, Tango and Wikus appear in the 2025 round (SECONDARY). Polish R&D spend ~$0.47M (2022), $0.69M (2023), $2.55M (2024) — consistent with the CEO's ~$17M; the subsidiary's "revenue" is cost-plus R&D billed to the parent (FY2023 zł2.9M, ~14% margin), not customers. Since then: "~$17M raised" (CEO, via Robozaps, Mar 2026) vs **$7.14M (Caplight)** — CONFLICT; a "$50M round" announced ~Apr 2026 with no reported close, now a bridge. An Echo-platform SPV, **Clone Red Beard Ventures Ltd** (BVI, CIK 2145276), sold $146,629 to 57 investors from 2026-03-12. | VERIFIED / CONFLICT |
| **Polish subsidiary's FY2025 statements not filed** with the KRS (deadline 2026-07-15; FY2022–24 were filed). No arrears, enforcement or insolvency entries. | VERIFIED |
| **Product timeline:** water-hydraulic hand 2022–23 (36 valves, 145 psi pump, 200 W peak); the Form C names lab "customers" (UC Berkeley, NYU, Stanford, ETH, Meta AI, Google AI) and press reports 16 AI labs pre-ordered — CLAIMED; **no delivery found**, and the hand page still invites requests for "access to a Clone Hand prototype"; Torso and Torso 2 (2024) **pneumatic**, off-the-shelf valves; Protoclone (Feb 2025) hung in a frame, "cannot yet walk"; Torso 3 (~Apr 2026) teleop; **Torso 4 promised Nov 2026** (X post). **No legs or biped hardware ever shown.** | VERIFIED |
| **Clone Alpha:** "279 units", no price, no checkout, **still says "Pre-orders available in 2025"** on 2026-10-27; the page claims "A robot that walks naturally". No deliveries found. | VERIFIED |
| **Pilots (Mercedes?, VW?, AST SpaceMobile, a hotel group, P&G?):** no public confirmation from either side; the memo itself says "no signed customers yet". Mercedes-Benz has invested in Apptronik ("low double-digit million") and runs <10 Apollos in Kecskemét and Berlin (SECONDARY) — and the memo's names are illegible anyway. | NOT FOUND / CLAIMED |
| **Licence + acquisition — Adaract Technologies (identified rev 1.1, CONFIRMED by the legible memo, rev 2):** "an exclusive license to Adaract's technology for $1.5M in **March 2026**, credited toward a **$4M acquisition**" (memo p.5; not closed). **Adaract Technologies, Ltd.** (Reno, NV; founded 2022; 5–9 staff), founded by **Joseph Daniel Hill** (UNR mechanical engineering). Adaract makes hydraulic artificial muscles, micro-hydraulic valves and pumps, holds **three granted US patents** (US11719263B2, US12378979B2, US12416318B2 — the last on the McKibben muscle termination itself, expiring 2044) plus a pending continuation, **no EP/DE coverage**, and won an Air Force SBIR Phase I (2024, $109,940) for an artificial-muscle **gripper**. Recorded assignments run inventors → Adaract only; no public Clone link. So Clone appears to be **licensing and buying outside muscle IP** after its own muscle inventor left. | ANALYST (identification) on VERIFIED Adaract facts |
| **Three of four co-founders are gone.** Amadeusz Świerk and Juliusz Tarnowski left in 2022 (2,930,000 founder shares repurchased at par; Form C Note 5, KRS entry 5); Koźlik left the Polish board in 2026. Only the CEO remains. | VERIFIED |
| CEO **Dhanush Radhakrishnan**: co-founded Symplex (YC S19, RL symptom checker, raised $1.5M per Form C, "acquired by Scale AI" — terms not public, possibly an acqui-hire). | VERIFIED |

---

## 4 · THE TECHNOLOGY — water-hydraulic artificial muscles

**Physics [VERIFIED].** Myofiber is a McKibben-type braided fluidic muscle. Force
falls toward zero at full contraction; Festo's datasheet puts the "most effective"
range below 9% of a 20–25% maximum. Friction hysteresis is high. Clone's headline
specs (1 kg from a 3 g fibre, <50 ms, >30% contraction) are spec-sheet ends, **none
is a working point**.

**Which fluid [VERIFIED].** Water hydraulics **was** shown at hand/forearm scale
(2022–23). The 2024 torsos were **pneumatic**; Clone calls that a stopgap ("our
biped brings back our hydraulic design with custom liquid valves"). Whole-body water
hydraulics has not been shown publicly. Pump spec on Clone's site: "500 W… 40 SLPM…
100 psi rating" (a maximum, not an operating point); 2022 press said 145 psi — CONFLICT.

**Durability — the binding constraint [VERIFIED arithmetic; ratings CLAIMED].**
A hand muscle at 8 grasps/min sees **0.96M cycles/yr on one shift, 1.92M on two,
4.03M at 24/7.**

| rating | source | life at 1 shift | at 2 shifts | at 24 h × 350 d |
|---|---|---|---|---|
| 100K cycles (?) | memo (illegible) | 26 working days | 13 working days | 9 days |
| 650K cycles | 2023 press (not on Clone's site) | 0.68 yr | 0.34 yr | 0.16 yr |
| >1M cycles | best public thin McKibben (s-muscle) — **air, 0.3 MPa, straight** | 1.04 yr | 0.52 yr | 0.25 yr |
| 10M cycles (?) | memo target (illegible) | 10.4 yr | 5.2 yr | 2.5 yr |

Against Clone: at **0.7 MPa** (≈ Clone's 100 psi rating), "all the normal artificial
muscles failed" when bent around a joint-like radius, and damage rises with pressure
(Kobayashi et al., IEEE RA-L 2024). Clone's pump ratings are 0.69–1.0 MPa (100–145 psi); its operating pressure is undisclosed (P1 #6). With hundreds of fibres
per robot, first failure arrives well before median life (Weibull) — though fibre
redundancy (~5.5 per DoF in Torso 2) may give graceful degradation, and a ruptured
*water* fibre leaks.

**Energy [VERIFIED / ANALYST].** No untethered shift has been shown. The only
measured Clone power figure is 200 W peak for a 2022 hand+forearm. Valve throttling
wastes ~43% of input in hydraulic servo systems (Meller 2017, general). Figure 03
runs ~5 h on 2.3 kWh.

**Precedent [VERIFIED].** Boston Dynamics retired hydraulic Atlas (Apr 2024) because
electric actuators had become "sufficient". Shadow moved from air muscles to motors;
Sarcos went electric then left hardware. **Sanctuary still develops hydraulic hands**
(RL and in-hand manipulation results) — what it scaled back was the humanoid and the
company (CEO reportedly ousted, ~30 jobs cut, Nov 2024): a commercial precedent, not
a technical retreat.

**The steelman [VERIFIED].** Compliance and backdrivability; strength-to-weight of
hydraulic McKibben actuators 5–10x motors (developer claim, oil at 5 MPa, actuator
only); force-by-pressure; very cheap muscle parts; working water hands in 2022–23;
in-house valves.

---

## 5 · COMPETITION — honestly

| | **Clone** | Tesla Optimus | Figure | Unitree | AgiBot | 1X | BD Atlas |
|---|---|---|---|---|---|---|---|
| Hand | 26 DoF "in the hand, wrist, and elbow" → **~20–23 hand-only (ANALYST): parity, not a lead**; water-hydraulic muscles | 22 DoF, tendon | 5-finger electric | Dex5-1 20 DoF (16 active) | n/f | 25 DoF incl. wrist, tendon | 13 DoF, backdrivable direct actuation |
| Touch | **none (published design)**; muscle-pressure force | all fingers | fingertip 3 g + palm camera | Dex5-1P: 94 sensors | n/f | normal, shear, contact | dense fingertip + palm |
| Walks | **never shown**; biped MVP Sept 2027 (memo) | yes | yes | yes | yes | yes | yes |
| Autonomy shown | **none** (teleop/scripted) | early | Helix VLA, BMW pilot | research buyers | thousands deployed | unproven | Gemini integration |
| Units | **0** | ~150 (2025) | ~150 (2025) | 5,500 (2025) | 5,168 (2025) | 0 to paying customers | 2026 fleet |
| Capital | ~$17M (claimed) / $7.1M (Caplight) | Tesla | ~$1.9B; $39B | public, ~$30B mkt cap | ~RMB 50B | ~$6B (talks) | Hyundai |

**The memo's two load-bearing competitive claims.**
1. **"~1/10 the cost": CONFLICT.** The CEO's own number is "<$20K" per android
   **"by producing Myofiber muscles at scale"** (Apr 2026). Against BofA's China BOM
   (<$17K by 2030) Clone's *at-scale* target is ~1.2x **above** it. The 1/10 ratio
   holds only against a sale price like Agility's ~$200K. Unitree's G1 at $13.5K has
   **no hand** and R1 has none either — not like-for-like, but the floor is the floor.
2. **"Price so competitors never reach scale": REFUTED as literal.** Unitree sold
   5,500 humanoids in 2025 at ~60% company gross margin (>70% to research/education);
   AgiBot ~5,168; Tesla's Fremont line is designed for ~1M/yr. Softening: rivals'
   volume is mostly research and low-DoF hands, so this does not prove Clone can't
   win a high-DoF enterprise niche.

**Capital gap:** Sanctuary ~$140M raised, Agility ~$641M, Apptronik ~$1B, Figure
~$1.9B — Clone's ~$17M is 1/8 to 1/110 of the field.

---

## 6 · WHERE CLONE CAN WIN — market and timing

**Demand is real, small, Chinese, and mostly not productive work [VERIFIED].**
13,317 humanoids shipped in 2025 (Omdia), 87% Chinese. H1 2026: 19,100 (SAG) vs
>22,000 (Counterpoint) — CONFLICT. **>60% of H1 2026 units went to entertainment &
performance and data production & research**; manufacturing + logistics ~17.7%.

**Paid humanoid work is tiny even for the US leader.** Agility (SEC S-4/A): FY2025
revenue $1.78M; H1 2026 $0.17M, unaudited, **all services, $0 robot sales**; a
$300M / 1,000-robot Digit 5 order from **one related-party customer**,
milestone-conditional. BMW–Figure "successfully completed a pilot" (logistics
sequencing, no count or commitment). And the work that pays today — moving totes —
does not need a dexterous hand.

**Clone's best honest shots (ANALYST, in order):**
1. **High-mix stationary bench assembly** (aerospace/electronics — AST SpaceMobile
   soldering is the named lead): rewards DoF and compliance, needs no legs, no walking
   race. Gated by autonomy and cycle life.
2. **Hands/muscles as a component** to other humanoid makers — if the BOM and cycle
   life hold. Hand volume leader Linkerbot (~$3B) shows the component market
   is real.
3. **Research and data-collection torsos** — the biggest current segment (27% of
   H1 2026 units), **but** Unitree is entrenched there at ~$23–25K average price and
   the segment is forecast to lose share to service/industrial.
4. Housekeeping/home: 2028+, contested, needs the biped, safety certification and
   battery life.

**The memo's data thesis is weaker than presented.** Physical Intelligence's
human-to-robot transfer works at arm/task level on a 1-D gripper and explicitly did
not transfer grasps; EgoScale pretrains in a 22-DoF human-like action space (modest
support). **No study shows a more anatomical hand transfers better.** The hand has to
win on measured performance per dollar.

**Policy cuts both ways [VERIFIED].** On 2026-07-28 the FCC Covered-Listed **all
foreign-produced mobile robots, humanoids included, "regardless of the nationality
of origin"** — the trigger is where it is made. Polish-built Clone robots need US
production or a Conditional Approval tied to an onshoring plan. **Rev 2 [VERIFIED, FCC
DA 26-786 App. C]:** "foreign-produced" = not a FAR "domestic end product" (US
manufacture **plus** domestic components >65% of cost for 2024–28 deliveries, 75% from
2029); the definition covers devices "capable of locomotion", and **(B)(vi) excludes "a
fixed, stationary, non-mobile robot… intended for industrial or medical use" — Clone's
first product, the stationary industrial torso, is outside the rule; the biped is
inside it.** Robot Conditional Approvals now number 7 (none a humanoid; 5 in 44 days) —
the onshoring route works. The memo's "US policy *may* require…" is the wrong tense.

**Timing.** By Clone's Sept 2027 biped MVP: Chinese vendors will have shipped tens of
thousands, Agility will be delivering its Digit 5 order, Figure's BotQ (12K/yr
initial capacity) and Tesla Fremont will be ramping.

---

## 7 · VEHICLE AND PRICE

**Sponsor — unchanged since Quaise [VERIFIED].** Delta4 Capital Master SPV LLC
(CIK 2113791): 3 Form Ds lifetime, **$886,861** from 13 investor slots, nothing filed
since 2026-05-27. **No Form D for the Quaise or DexMat SPVs, or any Clone series.**
Quaise's own filings: sold amount rose **$45.5M between July and September with the
investor count unchanged at 49** — no new holder appeared during Delta4's raising
window, so **no evidence the Quaise SPV ever invested**. No Form ADV or exempt-adviser
filing; domain registered 2025-10-10, site login-gated. Form Ds filed 7–11 days late
(two were first filings on new CIKs — hygiene, not pattern).
**In Golding's favour [VERIFIED]:** a real investor with his own money in robotics —
~$200K in Forward Industries' PIPE (424B5, 2025-11-03, same San Juan ZIP) and 10,000
RoboStrategy (BOT) shares. Platform SPVs (Echo, Sydecar) file under the platform's
name, so an EDGAR absence is not conclusive.

**Allocation: NOT FOUND.** No evidence Clone has allocated to Delta4; the memo says he
will "probably invest" **after** diligence he has not yet done (live Torso 4, IP
assignment, acquisition terms) — while the bridge "closes next week".

**Fees are not the problem [ANALYST, verified arithmetic].** On $50K: net invested
$44.8–48.8K. Net multiple 0.90–0.98x at 1x gross; 7.4–8.0x at 10x; 21.7–23.6x at 30x.
At Delta4's historical ~5% fee: 0.87 / 7.13 / 21.0x.

**Price [VERIFIED marks / ANALYST].** $200M post = **4.0x** the 2021–22 $50M SAFE cap,
**6.7x** the 2023 $30M crowd cap, **~11.8x** the ~$17M raised; **1.23x** Mentee's $162M
(the only other verified pre-product humanoid mark; Figure ~$400M on the other side).
In the sector's range; full for a robot that cannot walk and has no customer.

**Return math (ignores any liquidation-preference stack):**

| dilution to exit | 1x net needs | 3x net | **10x net** |
|---|---|---|---|
| 30% (best case: no rounds after the A) | $0.30B | $1.04B | $3.6B |
| 50% | $0.41B | $1.45B | **$5.1B** |
| **65%** | $0.59B | $2.07B | **$7.3B** |
| **80%** | $1.04B | $3.63B | **$12.7B** |

If the A is $75–100M (?): 27–33% dilution flat, 20–25% at a 1.5x step-up, 33–40%
in a down round, plus a 5–10% pool refresh — and a pre-revenue humanoid company will
need rounds after it, so **65–80% is the realistic band. 10x net needs $7.3–12.7B
of exit equity: above Apptronik's (~$5B) and 1X's (~$6B, in talks) current marks.**
An Agility-like $2.5B exit returns ~2.1x / 3.6x / 5.0x net at 80 / 65 / 50% dilution.

**Process flags.** Third Delta4 pitch on a fixed close clock; 2 of 3 with under a
week. Gating asks: countersigned allocation, SPV docs, bridge instrument, extension.

---

## 8 · GATES, SCORING, FORECASTS, EV — rev 1, pre-DD

### 8.0 · Gates first (rubric v1.1 §0)

| gate | status | why |
|---|---|---|
| **G1 Verification** | **PENDING — at risk** | Nothing queried yet, so it cannot trip at intake. Trips if any persists after query: "Clone says its technology is patented" vs Form C "no registered patents" and none Clone-owned found — the ask becomes *which patents, who owns them, exclusive or not* (true only via a licence, e.g. Adaract's); "~1/10 the cost" (CONFLICT); "walks naturally" and "Pre-orders available in 2025" still live on Clone's site; ~$17M raised (CEO) vs $7.14M (Caplight); 2% fee quoted vs ~5% on Delta4's Form Ds. |
| **G2 Vehicle math** | PASS | ~0.024% can return the vehicle in the evidenced tail (sector exits of $5B+ exist). |
| **G3 Horizon fit** | **AT RISK** | Pre-A humanoid: 7–10+ years to liquidity. SPV term unknown; Delta4's last Form D shows "1%/yr × 5". Ask who bears costs in years 6–10. |
| **G4 Price visibility** | **PENDING** | Price known ($200M post); class, instrument, raise, SPV documents and fee base unread or undisclosed. **If still undisclosed after request → automatically "conditional: pass until disclosed", never a buy.** |

### 8.1 · Panel (median · IQR · raw) — 5 independent scorers + red team

| dimension | median | IQR | raw | red |
|---|---|---|---|---|
| Market (30) | **3** | 0 | 2.5, 3, 3, 3, 3 | 2.5 |
| Team (30) | **2** | 0 | 2, 2, 2, 2, 2 | 1.5 |
| Moat (15) | **2** | 0 | 2, 2, 2, 2, 2 | 2 |
| Traction — demand (10) | **1.5** | 0 | 1, 1.5, 1.5, 1.5, 1.5 | 1 |
| Traction — delivery | **1.5** | 0 | 1.5 ×5 | 1.5 |
| Competition (10) | **1.5** | 0 | 1.5 ×5 | 1.5 |
| Deal & price (5) | **1.5** | 0.5 | 1.5, 2, 1.5, 1, 1 | 1.5 |
| **W** | **2.18** | | 2.00, 2.20, 2.17, 2.15, 2.15 | 1.85 |

**W = 2.18** (2.175; house formula; traction enters as the demand/delivery average —
both are 1.5, so min-vs-average does not matter). **Sensitivity band [1.92, 2.28]**
across unit weights and ±50% on each weight; ex-price 2.21. Second-lowest W in the
ledger (floor: Vernius 2.05). No band crosses a decision threshold; **no dimension
reaches 5, so there is no outlier thesis to underwrite.**

Reported separately, never averaged (rubric v1.1): **demand 1.5** — no signed
customer (memo), no confirmed pilot, Alpha's "279" is a production cap with no
price or checkout. **Delivery 1.5 — gap multiple not computable:** 0 robots
delivered, no autonomous grasp, no walking, no cycle-life data at working pressure;
real hardware has been built (hands, three torsos), which keeps it off a hard 1.

Score anchors, compressed:
- **Market 3 (one at 2.5):** a real, fast-growing category (13,317 units in 2025);
  Clone's addressable slice (paid dexterous work) is near zero today, and timing
  hurts (FCC, Sept 2027 biped).
- **Team 2, unanimous:** an RL CEO who kept the company alive from three months of
  cash to real prototypes; against it, no shipping history, three of four
  co-founders gone, the muscle inventor's status and IP unresolved, and claim hygiene
  (stale site, missed dates, unfiled FY2025 statements).
- **Moat 2, unanimous:** a real but feature-level edge — no patents, title through a
  departed inventor, DoF parity, the cost lead a CONFLICT; trade-secret know-how
  (braiding, valves) is the only cornered-resource candidate.
- **Competition 1.5, unanimous:** 0 units against thousands; 1/8–1/110 of rivals'
  capital; the only leader without touch or walking. The high-DoF stationary niche is
  less contested.
- **Deal 1.5 (IQR 0.5):** 4.0x the last verified cap, 11.8–28x paid-in, through a
  vehicle whose documents are unread; mitigated by sector comps ($200M ≈ 1.23x Mentee).

**Unanimity is itself a flag.** IQR 0 on six of seven dimensions and six identical
verdicts is the tightest panel this ledger has logged. It can mean the evidence is
doing the work — or that every scorer read one framing. Per the S2 rule, if we agree
inside ten minutes, swap sides and run it again.

### 8.2 · Forecasts — all six anchored to the SEED base (81.2% / 6.1%)

| forecast | panel median | raw | red team | seed base |
|---|---|---|---|---|
| P(priced round ≤24mo) | **0.45** | 0.45, 0.38, 0.45, 0.40, 0.45 | 0.40 | — |
| P(<1x) | **0.85** | 0.85, 0.86, 0.84, 0.85, 0.85 | 0.86 | 81.2% |
| P(≥10x) | **0.025** | 0.025, 0.025, 0.03, 0.025, 0.03 | 0.025 | 6.1% |

Why seed and not Series A (all six agree): the Series A base conditions on having
closed a priced A — exactly the hurdle Clone has not cleared; the bridge follows an
announced "$50M round" with no reported close. Adjusted for an A-level price: P(<1x)
above base, P(≥10x) cut to under half of base.

### 8.3 · EV at these terms (house exit-curve model, seed calibration, SPV 2/20)

| basis | EV net (capped @20x) | P(gross ≥1x) | ≥3x | ≥10x | ≥20x |
|---|---|---|---|---|---|
| panel (0.85 / 0.025) | **1.08x** | 15.0% | 8.7% | 2.50% | 1.41% |
| red team (0.86 / 0.025) | **1.05x** | 14.0% | 8.2% | 2.50% | 1.41% |
| *seed base, for reference* | *1.58x* | *18.8%* | *12.4%* | *6.10%* | *3.43%* |

Uncapped-tail premium: +0.65x riding on 1.41% of outcomes (disclosed, not headlined).
**Read it honestly:** ~1.05–1.08x over a 7–10 year hold is ~1%/yr before the time
value of money — below any hurdle — with ~85% of the probability mass a loss.
(Panelist 5's hand estimate was ~0.9x net or less.)

**Second forecast, logged separately — never averaged (rubric §4.5).** The hurdle
ledger (§11) implies **P(≥10x) ≈ 0.011** (band 0.007–0.022) against the panel's
0.025. At 0.011 the same model gives **EV ≈ 0.93x**; EV crosses 1.0x at P(≥10x) =
0.018. The hurdle verifier recommends the panel either name a path that supports
2.5% at S2 or cut it to ~0.015 (EV 0.97x). Either way **EV sits at or below 1x.**

### 8.4 · Verdicts: **5× PASS-REVISIT, red team PASS-REVISIT**

**Strongest pass reason (consensus):** $200M prices in what the record does not
show — walking, an autonomous grasp, a signed customer, cycle life at working
pressure — needs $7.3–12.7B for 10x at realistic dilution, and the money must move
"next week" through a vehicle whose documents and allocation are unseen.

**Strongest tail reason (consensus):** the one genuinely different actuator in a
field converging on near-identical electric tendon hands; force-by-pressure is the
channel the leaders call primary, and the clean ablation favours it over touch.
If Myofiber survives ≥2M cycles at working pressure and Torso 4 grasps autonomously,
Clone is a credible hand supplier or acquisition in a sector with $5–39B marks.

**Red team kill case (dated, rough probabilities):** Nov 2026 bridge closes; Torso 4
launches teleoperated (P(autonomous grasp with logged force by Q1 2027) ~0.30) →
Dec 2026–Q2 2027 the Series A lead diligences exactly the four holes (autonomy,
Myofiber life, a paying customer, Koźlik's title) plus the FCC onshoring cost; the
market already passed once when the "$50M round" became this bridge (P(priced A at
≥$200M by mid-2027) ~0.25) → Q2–Q3 2027 runway ends: insider recap or down-bridge
~0.30, acqui-hire under ~$150M ~0.25, wind-down ~0.45 → Sept 2027 biped date missed
(P(untethered biped) ~0.20). **P(<1x) ~0.86, of which this one chain carries ~0.57.**

**The red team's key structural point:** the hydraulics risk and the financing risk
are **common-mode** — the A lead tests the same durability and autonomy evidence,
the runway can't absorb a muscle redesign, and the FCC fix costs money only the A
supplies. One failure kills both. The flip side: if the evidence arrives, the A
likely follows — **so waiting for it is cheap.** The single datum that most cuts
P(<1x): a signed Series A term sheet from an institutional lead who has diligenced
Torso 4 and Myofiber cycle life. Fastest partial proxy before next week: Initialized
and Pioneer taking full pro rata in this bridge.

**Kill arguments that FAILED, recorded honestly (red team):** "no grip feedback"
(there is a force channel); "hydraulics is dead" (BD left because electric became
sufficient; Sanctuary still develops hydraulic hands); "price is outrageous"
($200M ≈ 1.23x Mentee); "fees eat it" (0.90–0.98x net at 1x gross); "the sponsor
is a shell" (Golding is a real investor). **None of these is the kill.**

### 8.5 · What would flip it — before money moves

**To CONDITIONAL (all needed):** (1) G4 cleared — native memo and deck, the bridge
instrument (cap/discount, MFN, preference seniority), SPV operating agreement with
the 2% vs ~5% fee base reconciled, a countersigned Clone→Delta4 allocation confirmed
by Clone, the entity/platform the Form D will file under; (2) a 2–3 week extension
so diligence precedes the wire; (3) at least one of: a live autonomous Torso 4 grasp
suite with logged force, cycle life ≥2M at working pressure and bent routing, or
Koźlik's exit and IP-assignment documents. **To INVEST** would need all three of (3).
**Otherwise:** re-enter at the priced Series A, where an institutional lead prices
the risk — a step-up costs less than a zero.

---

## 9 · WHAT THE BULLS GET RIGHT — recorded deliberately

- **A real, different actuator that has worked.** Water-hydraulic hands ran in
  2022–23 and drew top-lab interest; muscles are cheap to make; force-by-pressure is a
  genuine control advantage over stiff geared hands.
- **The leaders agree proprioceptive force is the primary channel**; touch is
  complementary. Clone's no-touch choice is defensible *if* its pressure estimate is
  accurate — a measurable, cheap-to-test claim.
- **Capital efficiency.** ~$17M against hundreds of millions for rivals, for a
  26-DoF arm-hand system.
- **IP depth beyond the departed founder** (Baran's valves, in-house Aquajet valves).
- **A stationary torso can be a product** without winning the walking race.

## 10 · PROCESS NOTES

- **Rev 1 process failure, owned:** the memo arrived as an unreadable screenshot and the
  pipeline ran anyway, with the ask buried in progress updates — against the house rule
  (missing key inputs: ask, don't analyze around them). Casey supplied the pages within
  hours of a clear ask. Rev 2 (§12) re-verifies everything they changed.
- **Privacy breach, disclosed:** a rev-2 research agent put Casey's email address in the
  HTTP User-Agent of 6 requests to sec.gov (SEC's fair-access policy asks for a contact
  string); an earlier verifier used a fragment of his name. No copy is stored anywhere.
  All future agent prompts specify a neutral contact string.
- The competition sweep priced comps at $300–360M; its verifier recomputed at $200M
  (multiples above).
- The tactile verifiers corrected 32 items, mostly in Clone's favour (the RDP and
  MoDE-VLA force-vs-touch evidence; ACT mean 74%, not 80–90%; geometry-only force
  error is pessimistic). The panel scores on the corrected record.
- **Book flags:** **third Delta4 vehicle in the ledger** (DexMat LIVE, Quaise PASS) —
  size any exposure as one manager bet; neither earlier SPV has a filed Form D. Sixth
  deep-tech/hardware exposure; first humanoid.

## 11 · GAP-CLOSING PASS (rev 1.1, same day) — founder sweep, records, hurdle ledger

Third workflow: three passes, each adversarially verified (all APPROVED WITH
CORRECTIONS, applied). **No panel score moves; the panel forecasts stand; one
separate forecast is logged.** Files: `sweeps/gap-*.md`.

**Founder sweep (templates/founder-sweep.md).** CEO's bio checks out (PPPL plasma
paper, *Nuclear Fusion* 2019; Symplex YC S19 "Acquired" — acquirer CLAIMED).
**Koźlik:** no new venture, dispute or statement found (weak: LinkedIn and US courts
blocked); Clone's YouTube channel dates to 2016 — his pre-company "Automaton
Robotics" channel, absorbed. **Świerk / Tarnowski** (left 2022): Tarnowski is an
inventor at an unrelated Wrocław crane-automation firm; no IP-claim signal from
either. **Baran and Wieczorek:** no 2024–26 evidence they are still at Clone. The
memo's team page appears to show three cards — Radhakrishnan, an unidentified
executive, and Joseph Hill (Adaract) — and none of Koźlik, Baran or Wieczorek (low
confidence, 310 px). Team stays 2 (band 1.5–2.5).

**Records pass.** No priced round found; no pilot confirmed by either side (AST is
hiring human soldering technicians for its Midland expansion); no grants found; the
"$50M round" did not close in H1 2026 on The Recursive's Poland arithmetic. Torso 4
launches in November after a "six-month ground-up redesign". **Data-integrity
hazards logged:** search summarisers repeatedly attributed Caplight's own $16M
Series A to Clone; Tracxn's "Clone" ($80M) is a different company; Robozaps' "$17M
round" is the cumulative figure re-entered.

**Duty cycle, reconciled.** Two bars, by segment:

| bar | segment | contractions/yr | 650K lasts | ≥1M lasts |
|---|---|---|---|---|
| A: 8 grasps/min, 8 h, 250 d | bench assembly, data factories | 0.96M (1 shift) – 1.92M (2) | 0.34–0.68 yr | 0.52–1.04 yr |
| B: 84 s line-rate cycle, 2×10 h | automotive line work | 214K | 3.0 yr (1 contraction/cycle) – 1.0 yr (3) | 1.6–4.7 yr |

**The durability bar is hardest exactly where Clone's best segment is** (bench
assembly). The 650K figure is a lower bound "with 1 kg load" at unknown pressure;
the >1M figure is a test capped at 1M — both censored, neither at a known working
pressure.

**Bottom-up SAM (ANALYST).** Research/data torsos ~11.9K/yr × $23–25K = $274–338M;
high-DoF hands ≤~75K/yr × $1.2–7K = $90–525M (Linkerbot: >80% share, ~5,000/month,
$3B Series B+, $6B target — Reuters 2026-05-04); Western bench assembly 500–2,000
torsos × ~$90K = $45–180M; home ~$0 before 2028. **Pools ~$0.4–1.0B/yr; Clone's band,
if the core pair passes, $3–46M/yr by 2027–28.** Market stays 3, re-anchored to this
SAM (anchor 3: "real market, bottom-up possible but thin").

**Hurdle ledger (templates/hurdle-ledger.md) — HYBRID, venture-binding (Quaise-type).**

| hurdle | type | resolves by | P |
|---|---|---|---|
| E4 autonomous Torso 4 grasp suite | execution | 2027-03-31 | 0.30 |
| V1a Myofiber ≥2M cycles at working pressure, bent | venture | 2027-06-30 | 0.35 given E4 |
| E5 clean IP chain of title | execution | 2027-06-30 | 0.80 |
| E3 priced Series A ≥$200M by mid-2027 | execution | 2027-06-30 | 0.22 |
| V2 paid demand ≥$10M ARR | venture | 2029-12-31 | 0.55 conditional |

**The core pair (E4 × V1a) = ~10.5%, resolving within ~8 months.** P(Series A by
mid-2027) is ~0.70 if both pass, ~0.25 if one, ~0.10 if neither — the red team's
common-mode point, quantified. Diligence should be a technical review plus a live
demo, not team meetings. Implied P(≥10x) ≈ 0.011 (§8.3); P(priced round ≤24mo)
≈ 0.39, inside the panel's spread. Methodology note for R2: the template has no term
for a venture hurdle driving an execution hurdle (here V1a and E4 drive E3); adding
one raises P(all pass) ~1.26x. Not applied mid-deal.

**Exit map.** Modal positive exit: a strategic sale at $0.3–1B after the core pair
passes (a humanoid OEM without a differentiated hand) → **~0.3–2.1x net** at 50–80%
dilution. Acqui-hire or IP sale under $150M (~0.2 unconditional) → ~0x after
preferences. Comps: SoftBank–ABB Robotics $5.375B (~2.4x revenue); Samsung 35% of
Rainbow for ~$181M; LG control of Bear via a call option; Sanctuary ~$140M raised,
$393–425M (2024), new CEO Jun 2026. **Mentee's $900M sale was related-party** (~51%
to two of the buyer's executives) — a ceiling, not an arm's-length comp, which
weakens the "$200M ≈ 1.23x Mentee" mitigation.

---

## 12 · REV 2 — WHAT THE LEGIBLE MEMO CHANGED (verified, same day)

Fourth workflow: three passes (people & money · technical & unit economics ·
customers & roadmap), each adversarially counter-checked; all APPROVED WITH
CORRECTIONS (61 corrections, applied). Files: `sweeps/rev2-*.md`. **No verifier
supports a panel score move on the corrected record; the technical verifier
recommends lowering three hurdle and forecast inputs (§12.6).** Panel re-run held for
page 6.

### 12.1 · In Clone's favour

- **A priced $150M mark, if documented.** Memo: Mar 2025, $10M at $150M post from
  Access Industries [CLAIMED; no public confirmation; Access's portfolio page lists
  mega-caps only, so its silence means little]. It sizes a 2025 round already in our
  record. **If documented, $200M is a 1.33x step-up, not the 4.0x we scored.** Ask for
  the instrument and documents.
- **The funding total reconciles.** $0.6M + $6M + $10M = $16.6M ≈ the CEO's ~$17M;
  the memo's "about $24M" counts the $6.5M of committed, unclosed bridge (a minor
  overstatement). Caplight's $7.14M is the outlier.
- **A named, real CTO.** Damian Lickindorf: a Wrocław legged-robot builder (GitHub,
  Hackaday since 2018; Politechnika Wrocławska; capstan quadruped "Stanley", 2021).
- **Adaract is real and active.** Datasheets re-issued 2025-08 and 2026-01; valves
  going into a prosthetics maker's products. **Its muscle datasheet rates the AM70 at
  "~1.5 million cycles to failure"** (2,750 psi, 20% contraction, 4 Hz; "life is strongly
  dependent on test conditions"), working pressure 150–3,000 psi, burst >9,000–10,000
  psi — ~15x Clone's own Torso 4 rating. [VERIFIED, adaract.com]
- **The FCC rule excludes Clone's first product** (stationary industrial robots, §6).
- **Capital is available for pre-customer manipulation stories:** Eka raised a $150M
  Series A at $1.45B (Oct 2026) with no named customers; Humanoid $152M at $1.35B (Jul
  2026). Counter-example: Cartwheel Robotics shut down after failing to raise a bridge.
- **The $9-muscle steelman partly survives:** at automotive line duty (~214K
  contractions/yr) 100K-cycle muscles with swaps of ≤7 minutes keep payback at
  12.6–14.9 months. A full re-muscle (182 muscles) is ~$1.6K of parts.
- **The paybacks re-derive exactly** (12.4 / 19.8 / 42.3 months).

### 12.2 · Against Clone

- **Runway.** $2.5M cash, $750–900K/month burn = **2.8–3.3 months standalone** (cash-out
  Jan–Feb 2027). The bridge gives 10–12 months on the $6.5M committed (Sep–Nov 2027)
  and 12.8–15.3 months on the full $9M. Adaract "in practice closes with the Series A"
  (p.6 fragment). **The Series A is binary for survival.**
- **The rated muscle life is now legible: Torso 4 = 100K cycles** (Q3 2026); production
  10M only in Q4 2028 (100x in ~2 years). 100K is 20x below the ≥2M bar. At bench duty
  it lasts **13–26 working days** per muscle; at line rate ~5.6 months. The steelman
  degrades at bench or pick duty with fast swaps (3PL payback 23–28 months) and breaks
  with slow ones (0.5 h swaps: 34–112 months).
- **A new, undemonstrated operating point.** Memo: 2 kW pump, water at **10–40 bar**,
  306 proportional valves. Clone's site (Dec 2024 spec): 500 W, 100 psi (6.9 bar). Fatigue
  scales with fibre load ∝ pressure; "survives 10x operating pressure" is burst
  strength, not life; no public cycle-life data for hydraulic McKibben muscles at 1–5
  MPa. **Adaract's patents and datasheet are for oil at ~3,000 psi — water appears in
  none of them**, so the durability does not transfer automatically. 40 bar is ~5.7x
  HSE's anecdotal injection threshold (leak: ~5–9 mL per 100 ms through a muscle's own
  valve).
- **Autonomy is a 2028 item on Clone's own roadmap.** Torso 4's milestone is "low-level
  joint control and teleoperation"; customer torsos ship Jan 2027; **"Clone's first VLA
  model" is Q4 2028** — 21–23 months later. 2027–28 deployments are teleoperated or
  scripted (sector-normal: 1X expert mode, Apptronik teleop), so pre-VLA the $178K torso
  competes with conventional automation, not with a human — and the 85%-capture
  paybacks are unsupported until then.
- **Customers: 0 of 7 confirmed** (memo: "Nothing is signed yet, but the inbound is
  real"). Mercedes and VW "reached out" (Mercedes invests in Apptronik — $935M Series A
  at ~$5.3B, Feb 2026 — and runs Apollos in Berlin and Kecskemét; VW's only humanoid
  activity found is FAW-VW with UBTech in China). **Moxy Hotels came through Greg Racz,
  a bridge investor and "a friend of Delta4 Capital's"** — a related-party channel; Racz
  is a private-credit financier (MGG founder, Volley Capital) with no hospitality role
  found, and NYC Moxys are owner-operated (Lightstone), so pilots are an owner decision.
  **"Ranpak, a key 3PL for Walmart and Amazon" is REFUTED:** Ranpak (NYSE: PACK) makes
  paper packaging and packing machines; it supplies Walmart and Amazon, it is not a 3PL.
  The Taiwanese bike maker is unidentified (Giant is the only Taiwanese Tour brand in 2026).
- **Price list vs the CEO's public price.** Memo: Industrial Torso $178K, biped $214K
  list. CEO in April 2026 (Humanoids Daily): Clone "aims to maintain a **mass-market price
  of $20,000**". 8.9x apart; at $20K on the memo's BOMs, margin is 20% / 4%, not 91%.
- **Competitor hand "BOMs" are Clone's own estimates and are inflated 2–4x:** Wuji at
  62–103% of its retail price; Sharpa ~90% of its ~$50K price; Tesla per-hand 2–4x
  Morgan Stanley's teardown (~$9.5K per pair); "Apptronik's $50K hand" NOT FOUND (Apollo
  has been shown with PSYONIC's 6-DoF hand). **Like for like, Clone's $1.1K hand is ~2–5x
  cheaper than $6–7K-retail 20–30 DoF hands — not 9–45x.** Hand DoF: 25 incl. wrist,
  same convention as 1X's 22 + 3 → parity.
- **The financing table contradicts the filing.** Pre-seed "Nov 2021, $0.6M at $20M
  post" is **REFUTED** by the Form C ($525K of SAFEs at a **$50M** post-money cap). The
  memo's ladder ($20M → $33.8M → $150M → $200M) omits that the $33.8M seed priced below
  the 2021–22 cap.
- **Bridge composition:** Early Game Ventures (European, Romania-based; broad thesis),
  will.i.am, Matt Bellamy (Muse), Greg Racz "and others" — **no existing institution
  named** (Initialized, Pioneer, Tango absent; Access "plans to take its pro-rata in the
  Series A"). $6.5M of $9M committed (72%).
- **CTO bio inflated:** "Stanley" was co-developed with Ahead, benchmarked against MIT's
  mini cheetah, not Spot; offered as a kit, **no units sold found**; it uses motors with
  a cable reduction (relevant to legs, not to fluidic muscles). His HYPR role (Zoox
  co-founder Kentley-Klay's startup) is NOT FOUND. Not a co-founder; no published patents.
- **Related-party acquisition.** Chief Engineer Joseph Hill founded the $4M target. The
  licence is dated **March 2026** — the same month Koźlik was struck from the Polish
  board (2026-03-18). Adaract's co-founders (Marcus D'Ambrosio, Clay Payson) and
  co-inventor (Budu-Manuel) also hold interests to clear. Hill's Clone employment has no
  public trace. **"Adaract's valves are rated for 100 million cycles": NOT FOUND** in any
  of Adaract's four datasheets (100M was Clone's own 2023 Form C target).
- **Clone is not a YC company** (the CEO card's "Y Combinator" refers to Symplex).
- **Wire before visit.** Bridge closes Nov 3; Series A demos from Nov 9; Delta4 visits
  Nov 12. Delta4's pre-close checks: Torso 4 over Zoom, IP assignment and patents,
  Adaract terms.
- **Execution record:** 3 public dated commitments missed (one on a single snippet), the
  internal Torso 4 date slipped ~1–2 months, and the "$50M round" became this bridge.
- **"$1B on 10,000 Clones by Q1 2030"** = $100K a robot (44–53% under list) and 1.8x
  Unitree's entire 2025 volume.

### 12.3 · Reconciled (no longer conflicts)

Torso 3's "164 DoF, 182 muscles, 251 sensors" = the Torso 2 architecture counted per
5-fibre muscle (910 / 182 = 5.0; 251 = 182 pressure + 69 other) — not new actuation,
but "182 sensors" was one per muscle. Headcount 65 vs Caplight's 46 is a time lag.

### 12.4 · Gates after rev 2

- **G1 — more at risk (no query yet).** New trip items: the pre-seed table vs the Form C;
  the CEO's public $20K price vs the $178K / $214K list; "Ranpak, a key 3PL" (REFUTED);
  "Adaract valves rated 100M cycles" (not in any datasheet); competitor figures presented
  as BOMs; the CTO's "Spot-comparable… sold" line. Plus the carried items ("patented",
  "1/10 the cost").
- **G4 — partly cleared:** raise, committed amount, close date, fees and cash now read;
  **instrument still undisclosed**.

### 12.5 · What it does to the record's numbers

| item | rev 1.1 | rev 2 |
|---|---|---|
| Last mark | $50M SAFE cap (public) → $200M = 4.0x | **$150M (Mar 2025, CLAIMED)** → 1.33x if documented; $33.8M seed (CLAIMED) → 5.9x |
| Cash / runway | unread | $2.5M; 2.8–3.3 months standalone; 10–15 months with the bridge |
| Muscle life | 650K (2023 press) / 100K (?) | **100K (Torso 4, memo)**; 10M target Q4 2028; Adaract AM70 ~1.5M on oil |
| Operating pressure | 0.69–1.0 MPa | **1–4 MPa (memo, undemonstrated)** |
| Autonomy timing | "no autonomous grasp shown" | **first VLA Q4 2028 on Clone's own roadmap** |
| Customers | none signed | 0/7 confirmed; 1 related-party; 1 refuted label |
| FCC | stationary "may" be exempt | **stationary industrial robots excluded (VERIFIED)** |
| Hand cost edge | "~1/10" CONFLICT | ~2–5x like for like |

### 12.6 · Recommended for the re-score (not applied — held for page 6)

From the technical verifier: E4 (autonomous grasp by Mar 2027) 0.30 → **0.22** (Clone's
roadmap sets no autonomy target before Q3 2027); V1a|E4 0.35 → **0.28**; core pair
10.5% → **~6%**; P(priced round ≤24mo) 0.45 → **0.42**; P(≥10x) 0.025 → **0.020**; EV
≈1.02x (interpolated). The people-and-money and customers verifiers see no score move:
the claimed $150M mark (better price) roughly offsets the refuted table, unnamed
insiders and related-party seller. **Deal IQR widens to 1.0–2.0.** Downside leans: Demand
1.0 if the 7-name ask returns no NDA or LOI; Delivery 1.0–1.25 if Torso 4 is teleop-only
in November with no life data at working pressure; Team 1.5 if the price and pre-seed
conflicts persist after query.

---

## PENDING DD QUESTIONS — RANKED (rev 2, 2026-10-27)

Statuses: ○ not yet asked · ● asked · ✓ answered · ✗ refused · ⌛ expired (60 days from
first ask). (S) = to the sponsor; (C) = to the company. Chosen so that answer quality
is itself the datapoint.

### P0 — from Casey himself (zero cost, today)

- ◐ (LP) **The native memo** — pages 1–5 and 7 ✓ (rev 2). **Page 6 and the deck still
  open.** Page 6 should carry the cash Clone must hold to close Adaract and the sponsor's
  full risk list.
- ◐ (LP) **Did the Delta4 DexMat SPV close, and did you wire?** ✓ Casey invested **$75K**
  (2026-10-27). **Deployment not yet visible on EDGAR:** Delta4 has filed nothing since
  2026-05-27, and DexMat's last Form D (2026-08-19) predates the close. Still open: the
  closing notice, a capital-account statement, the series' legal name and custodian,
  and DexMat's cap-table confirmation. **Get these before any Clone wire.** Book: Delta4
  exposure would be $125K across two SPVs.

### P1 — decision-gating

1. ◐ (S) **Native memo PDF + deck.** Raise, committed, fees, cash, burn, Series A size ✓
   (rev 2). **Still open: the bridge instrument, memo page 6, the deck.**
2. ○ (C) **A live AUTONOMOUS (not teleoperated) Torso 4 demo** — egg, paper cup,
   grape, plug insertion, slip recovery, ≥20 trials each, with logged grip force.
   *Moves:* Casey's crux, the "hand leads" thesis, pilot readiness. Decisive.
3. ○ (C) **Per-hand Torso 4 sensor sheet + measured grip-force accuracy** (pressure-
   estimated fingertip force vs load cell: N, % FS, hysteresis, smallest detectable
   contact, latency), and whether touch or wrist/palm cameras are on the BOM or
   roadmap. *Moves:* the crux, quantified.
4. ○ (C) **Koźlik:** has he left Clone Inc., on what terms, what happened to his ~3M
   shares, is he building anything competing? *Moves:* key-person, cap table, IP.
5. ○ (C) **IP chain of title:** Koźlik's signed assignment covering his 2014–21 muscle
   and valve work; the IP transfer between the Polish and US entities; assignments
   from Baran and the other inventors; patent schedule with numbers. *Moves:* whether
   the company owns its core technology.
6. ○ (C) **Cycle life at working pressure:** Myofiber and valve life (cycles) at
   stated load, stroke, pressure and bend radius; failure and leak modes; maintenance
   interval in hours. *Moves:* the binding technical risk (§4).
7. ○ (S+C) **Allocation proof:** a countersigned Clone→Delta4 allocation (amount,
   instrument, deadline), confirmed by Clone directly. *Moves:* whether the deal
   exists as offered.
8. ○ (S) **SPV documents before wiring:** operating agreement, fee base, carry basis,
   admin budget, what happens to wired funds if the SPV or bridge fails to close; why
   the Form Ds show ~5% fees vs 2% quoted; did the Quaise and DexMat SPVs close?
   *Moves:* vehicle verdict.
9. ○ (C) **Cash, burn, runway** with and without the Series A; how much of the bridge
   the acquisition's minimum-cash condition locks up; what happened to the "$50M round"
   of Mar–Apr 2026. *Moves:* P(survival), P(Series A).
10. ○ (S+C) **Timeline:** can Casey commit after Delta4's own pre-close checks, or get
    a 2–3 week extension? *Moves:* whether diligence precedes money.

**P1 — added by the completeness critic:**

- ○ (C) **Licence + acquisition, promoted from P2 and merged with #5 and #9:**
  counterparty; is it connected to Koźlik or his pre-2021 "Automaton Robotics" work
  (i.e. does closing it complete the chain of title)? IP covered, closing conditions,
  and how much bridge cash the minimum-cash condition locks up.
- ○ (C) **G1 test:** patent application numbers, jurisdictions and inventors behind
  "Clone says its technology is patented". No numbers = a material misstatement.
- ○ (C) **Insider signal:** are Initialized, Pioneer and the other seed investors
  taking pro rata in this bridge, how much is committed by insiders, and who set the
  $200M price?
- ○ (C) **Prior rounds:** cap/price and instrument of the 2023 seed, the Jan/Feb-2025
  round and the 2026-03-10 round (incl. the Echo "Clone Red Beard Ventures" SPV). Has
  Clone ever closed a priced round? What became of the "$50M round" — partial close or
  abandoned — and is there a Series A lead or term sheet now?
- ○ (S) **Vehicle mechanics:** the legal entity and platform/administrator the Clone
  series will file its Form D under (makes tripwire #6 checkable); bank/custodian; which
  Advisers Act exemption Delta4/Golding rely on (no ERA Form ADV); direct investment or
  SPV-of-SPV, and if the latter, the stacked fees; are the 2% and admin inside or on top
  of the $50K?
- ○ (C) **Adaract (rev 1.1):** is the licensor/target Adaract Technologies? Exclusivity,
  field of use, territory (no EP/DE coverage), term and termination; which claims
  Myofiber practises (a lapse would be a US freedom-to-operate problem); acquisition
  price, closing conditions and the minimum cash it locks up; is Joseph Hill joining,
  and in what role? Does the 2023 NIDILRR or 2024 Air Force SBIR create government
  rights in any licensed invention?
- ○ (C) **Polish-entity IP:** does the cost-plus R&D agreement between CLONE sp. z o.o.
  and Clone Inc. assign IP created in Wrocław to the parent? Without it, title sits in
  Poland — chain of title and the US onshoring plan both depend on it.
- ○ (C) **Who is on the leadership slide** shown to investors, and why are Koźlik, Baran
  and Wieczorek absent from it?
- ○ (C, rev 2) **The $150M round:** instrument, documents and lead for "Mar 2025, $10M at
  $150M, Access Industries". Were the 2021–22 SAFE caps amended (memo $20M vs Form C
  $50M)?
- ○ (C, rev 2) **Price:** the deck's $178K / $214K list vs the CEO's public "$20,000
  mass-market price" — which is the plan, and at what margin?
- ○ (C, rev 2) **Muscle life at the NEW operating point:** test logs for Torso 4 muscles
  at 10–40 bar on water (cycles, stroke, bend radius, failure mode), and the path from
  100K to 10M. Does Torso 4 use Adaract hardware, and on water or oil?
- ○ (C, rev 2) **Pre-VLA deployment model:** how do the Jan-2027 industrial torsos
  operate — scripted cells, teleop (what supervision ratio), or learned policies? Who
  pays for teleop labour?
- ○ (C, rev 2) **Prospects:** NDA, LOI or pilot terms for each of the 7 names; who at
  Moxy (owner/operator) is engaged; what the Ranpak relationship actually is.
- ○ (C, rev 2) **Adaract:** the $4M split (cash vs equity), Hill's and his co-founders'
  stakes, how much cash Clone must hold to close, and Hill's employment status today.

### P2 — score-moving

11. ○ (C) Licence + acquisition (promoted to P1 above).
12. ○ (C) Pilots: for each named site, status (LOI / signed / paid), scope, price,
    start; what exactly the Mercedes engagement is, given Apptronik.
13. ○ (C) Itemised BOM for hand and android at stated volume (pump, valves, reservoir,
    battery, compute); which competitor cost is the "1/10" denominator.
14. ○ (C) Fluid and power: is Torso 4 water or air; untethered runtime per charge;
    W per kg payload; leak data.
15. ○ (C) Fully diluted post-bridge cap table incl. all SAFEs, the Red Beard SPV,
    option pool, preference stack.
16. ○ (C) Torso-only go-to-market: price and BOM at 100 / 1K / 10K units; named
    research or bench-assembly buyers; any paid hand or torso orders since 2023.
17. ○ (C) Policy plan: US production vs FCC Conditional Approval; does a stationary
    torso fall outside the mobile-robot listing (counsel's view)?
18. ○ (C) Why are the Polish subsidiary's FY2025 statements unfiled; FY2022–25
    statements for both entities.
19. ○ (S) Golding's own commitment to this SPV; any compensation from Clone or the
    lead; information rights and Series A pro rata for the SPV.
- ○ (C) Are Baran and Wieczorek still at Clone? Current roster and headcount by site;
  who runs business and finance. Did Świerk and Tarnowski sign IP assignments?
- ○ (C) Design duty cycle for Torso 4 (grasps/min, contractions per grasp per muscle)
  and the cycle-life target that follows — reconciles the 8 grasps/min vs 84 s bars.
- ○ (C) Hand-level BOM and price vs Linkerbot's ~$1.2K O7 and ~$7K 25–30 DoF hands;
  which competitor price is the "1/10" denominator.
- ○ (C) Grants (NCBR/PARP/EU) and any revenue — do they explain $17M vs $7.14M?
- ○ (S) Is the "robotics OEM" on Golding's site Clone or a competitor? His RoboStrategy
  holding is ~28% of NAV in Figure and Apptronik — disclose.
- ○ (S) Did the Quaise SPV enter through a co-invest vehicle or a secondary? Name the
  holder of record (tests the ordinary explanation for the unchanged investor count).
20. ○ (C) Teleop operator feedback: are muscle-pressure channels logged and fed to
    the policy (can Clone learn force-aware behaviour)?

### P3 — completeness

21. ○ (C) Alpha's 279-unit run (a production cap, not a reservation count): how many
    reservations or deposits were received, refunds owed, deliveries; same for the
    2023 hand/torso pre-orders.
22. ○ (C) Reconcile sensor counts ("over 200" / 394 / "500") and hand DoF (26 incl.
    wrist and elbow vs 27 in the hand).
23. ○ (C) Was Protoclone pneumatic or water? Is the Alpha page's "walks naturally"
    current?
24. ○ (C) Safety certification path for work near people.
25. ○ (C) Why the 2023 Reg CF was withdrawn; why no Form D for later rounds.
26. ○ (S) SPV term and fees after year 5/7; who bears costs if the holding runs 8–10
    years (G3).

---

## TRIPWIRES / FALSIFIABLE CHECKS — written before any money moves

1. **Torso 4 live in November 2026**, and an **autonomous** grasp with logged force by
   Q1 2027. Teleop-only through Q1 2027 → the hand thesis is unproven at Series A.
2. **Series A closes by ~Q2 2027** at ≥ the bridge price. Slip past mid-2027 with
   short runway → distressed financing.
3. **A paid pilot** (not an LOI) from a named counterparty by mid-2027.
4. **Published cycle-life data ≥2M cycles at working pressure** before any fleet
   deployment; anything near 100–650K → a maintenance business, not a product.
5. **The biped walking untethered by Sept 2027** (Clone's own date).
6. **Delta4 files a Form D for the Clone series** within 15 days of first sale; no
   filing → treat the position as unverified.
7. **Koźlik:** any competing venture, or any IP claim from him.
