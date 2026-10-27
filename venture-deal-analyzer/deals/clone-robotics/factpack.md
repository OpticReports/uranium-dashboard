# Clone Robotics — grounded fact pack (2026-10-27, rev 1 — PRE-DD)

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
| Delta4 Capital memo "Clone Robotics — Bridge round", Alex Golding, dated 2026-10-27 | **PARTLY — fragments only** | Supplied as a 310 px-wide screenshot of a multi-page DocSend/Dropbox PDF. Headings and a few phrases legible at 4x upscale (`source/legible-fragments.md`); **body text and nearly every number UNREAD**. Never used as fact below except where marked (?) as a lead. |
| Clone deck (same viewer) | **NOT READ** | 121 px wide; only some slide titles legible |
| **Valuation $200M post-money** | **YES — LP, 2026-10-27** | Supersedes our misread "$3?0M" — proof that the screenshot's numbers cannot be trusted |
| Raise size, committed, instrument, exact SPV fees, cash, burn, Series A size | **NOT READ** | P1 asks; a native PDF closes most of them |

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
| SPV terms | "2% one-time fee, 20% carried interest, plus a pro-rata share of SPV fees" (approx., legible fragment). Delta4's three filed Form Ds instead disclose ~5% related-person fees ("1%/yr × 5") [VERIFIED] — CONFLICT |
| Raise / committed / instrument | **UNREAD** |
| Close | "The bridge closes next week" (memo) |
| Next round | Series A, "$75–100M" target (?) |
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
| **Licence + acquisition — likely Adaract Technologies (rev 1.1).** The memo's illegible "Adlated?" and team-card "Joseph Hill" read as **Adaract Technologies, Ltd.** (Reno, NV; founded 2022; 5–9 staff), founded by **Joseph Daniel Hill** (UNR mechanical engineering). Adaract makes hydraulic artificial muscles, micro-hydraulic valves and pumps, holds **three granted US patents** (US11719263B2, US12378979B2, US12416318B2 — the last on the McKibben muscle termination itself, expiring 2044) plus a pending continuation, **no EP/DE coverage**, and won an Air Force SBIR Phase I (2024, $109,940) for an artificial-muscle **gripper**. Recorded assignments run inventors → Adaract only; no public Clone link. So Clone appears to be **licensing and buying outside muscle IP** after its own muscle inventor left. | ANALYST (identification) on VERIFIED Adaract facts |
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
production or a Conditional Approval tied to an onshoring plan (2 robot approvals as
of 2026-09-18, open-ended while the plan holds). A **stationary** torso may sit
outside "mobile robot" (ANALYST — verify with counsel).

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

- **The memo is functionally unread.** Every number in §1 except the $200M (LP) is a
  fragment or UNREAD; a native PDF is the first ask. Our misread "$3?0M" vs Casey's
  $200M is the reason.
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

## PENDING DD QUESTIONS — RANKED (rev 1, 2026-10-27)

Statuses: ○ not yet asked · ● asked · ✓ answered · ✗ refused · ⌛ expired (60 days from
first ask). (S) = to the sponsor; (C) = to the company. Chosen so that answer quality
is itself the datapoint.

### P0 — from Casey himself (zero cost, today)

- ○ (LP) **The native memo.** You read "$200M post" where our screenshot read "$3?0M" —
  if you have the DocSend/PDF, forward or export it. It closes raise, committed,
  instrument, SPV fees, cash, burn and Series A size today.
- ○ (LP) **Did the Delta4 DexMat SPV close on 2026-09-28, and did you wire?** If so:
  what subscription documents, closing confirmation, custodian and Form D entity name
  did Delta4 provide? It is the best available test of this vehicle.

### P1 — decision-gating

1. ○ (S) **Native memo PDF + deck.** Closes raise size, committed, instrument, SPV
   fees, cash, burn, Series A size. *Moves:* every term in §1.
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
