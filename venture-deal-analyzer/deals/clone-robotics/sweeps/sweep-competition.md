# Clone Robotics: how it compares with the leading competition (evidence sweep)

Swept 2026-10-27 by the competition sweep agent. Scope: (a) leading humanoid makers, (b) dexterous-hand specialists, (c) the memo's two cost and scale claims, (d) valuation comps, (e) a head-to-head table.
Tags: VERIFIED (primary URL) / SECONDARY / CLAIMED (company or sponsor only) / CONFLICT / NOT FOUND / REFUTED / ANALYST.
Memo numbers marked (?) are UNREAD (see BRIEF.md). Nothing below depends on them except where it is labelled.
Prompt-injection log: none seen in any fetched page.

---

## 1. Executive read (8 lines)

1. **Where Clone actually leads:** the number of hand DoF it claims (26–27, about human), a muscle-like compliant actuator and a claimed low materials cost. All three are CLAIMED by the company. Every public hand demo is **teleoperated** (latest 2026-10-01). Clone has never shown the robot walking.
2. **Commercial position:** Clone has shipped **0 units** and signed no customers. The global market shipped ~13,000 humanoids in 2025 (Omdia) and ~19,100 in H1 2026 (SAG). Every top-6 rival walks, has named customers or fleets, and is valued between ~$2.5B and $39B (Tesla aside).
3. **Casey's tactile point is largely correct.** Clone publishes 320 muscle-pressure sensors ("muscle force feedback"), 70 IMUs and palm pressure pads. It publishes **no fingertip tactile array**. Figure 03 (3 g fingertip sensing), 1X NEO (normal force, shear and contact location), Atlas (dense fingertip and palm sensing), Sharpa (more than 1,000 taxels per fingertip) and Unitree Dex5-1P (94 sensors) all publish one. Muscle pressure gives a rough grip-force estimate. It is not touch.
4. **Claim 1, "~1/10 the cost": CONFLICT.** The CEO's own figure is "under $20K" per android (2026-04). That is ~1/3–1/5 of Western motor-driven cost (Optimus V3 >$60k; Western pilot units $90–100k). It is about equal to Chinese cost (BofA: China BOM $35k in 2025, below $17k by 2030; Unitree G1 retails from $13,500). A 1/10 ratio holds only against a sale *price* such as Agility's ~$200k, never against a cost.
5. **Claim 2, "price so competitors never reach scale": REFUTED by timing.** Unitree and AgiBot each shipped ~5,000+ in 2025, Unitree at a ~60% gross margin. Tesla has a Fremont line designed for ~1M/yr. Clone's own roadmap puts its first commercial android in 2028.
6. **Hydraulic precedent is poor.** Boston Dynamics dropped hydraulic Atlas in 2024. Sanctuary has worked on a hydraulic hand since 2018 and raised ~$140M, yet still lists the hand as "In Development" and has pivoted to selling software. The volume leader in hands, Linkerbot (motor-driven, valued at $3B), ships thousands of hands a month.
7. **Valuation is rich for the stage.** The memo's $300M or $360M post (digit illegible) is for a robot that cannot walk yet, with ~$17M raised (CLAIMED). That is ~1.9–2.2x Mentee's last private mark ($162M) and ~1.4–1.7x 1X's 2023 Series A2 ($210M post). It is ~10–12x the 2023 Republic cap of $30M (SECONDARY).
8. **Where Clone could plausibly win:** niches that reward human kinematics, compliance and DoF more than walking, such as stationary two-handed work (Torso 4), teleoperated data collection and research hands. It could also supply hands or muscles to other makers if the BOM claim holds. The decision-gating ask is a live, **autonomous** Torso 4 grasp with logged grip force, plus BOM and cycle-life documents.

---

## 2. Evidence

### (a) Leading humanoid makers as of Oct 2026

**Market volume**
- E1. Omdia, 2025 global humanoid shipments: ~13,000 units. AgiBot 5,168 (39%, #1). — VERIFIED as relayed in AgiBot's own release (company-hosted, Omdia data), 2026-01-08: https://www.agibot.com/article/231/detail/33.html
- E2. Omdia 2025: Unitree ~4,200 (~32%), UBTech ~1,000. Tesla, Figure and Agility ~150 each. Chinese makers ~90% of the total. — SECONDARY: https://technode.com/2026/01/09/chinas-agibot-leads-global-humanoid-robot-shipments-in-2025-omdia-says/ ; https://e.vnexpress.net/news/tech/tech-news/china-s-agibot-tops-global-humanoid-robot-shipments-in-2025-5004681.html
- E3. Unitree's own prospectus says more than 5,500 humanoids were sold in 2025, against Omdia's 4,200 (E2). — CONFLICT (definitions differ): https://restofworld.org/2026/unitree-china-humanoid-robot-shanghai-ipo/
- E4. Smart Analytics Global, H1 2026: 19,100 shipped worldwide (+272% YoY from 5,100). AgiBot ~8,400, Unitree 5,900, Galbot 900, UBTech 700, Leju 600. More than 70% went to "industrial and commercial" uses. — SECONDARY (these are independent estimates): https://humanoidanalytics.com/2026/08/17/19100-humanoid-robots-shipped-in-six-months-where-are-they-working/

**Tesla Optimus**
- E5. Q3 2026 call (2026-10-21/22): "early Optimus production" has started on a Fremont line "designed for about 1 million robots a year". Reaching ~20,000/week will take "at least a year". Deliveries to outside companies start ~end of 2027, industrial customers first. — SECONDARY (call recap): https://www.notateslaapp.com/news/4867/tesla-q3-2026-earnings-call-recap-everything-you-need-to-know
- E6. Optimus V3 manufacturing cost is estimated at more than $60,000 per unit in H2 2026. The new 22-DoF hand is ~20% of BOM (~$12k+ per robot). — SECONDARY (Counterpoint estimate, 2026-06-10): https://counterpointresearch.com/jp/insights/blog-tesla-to-leverage-ev-experience-and-chinese-partners-to-ace-humanoids-market-unlock-huge-revenue-potential
- E7. V3 hand: 22 DoF, tendon-driven, actuators moved into the forearm. This comes from patents filed Oct 2024. — SECONDARY: https://driveteslacanada.ca/news/new-tesla-patents-reveal-optimus-v3-hand-human-muscles-tendons/
- E8. Gen 2 (Dec 2023): 11-DoF hands with "tactile sensing on all fingers" (egg-handling demo). — SECONDARY: https://www.yankodesign.com/2023/12/16/tesla-brings-scary-improvements-to-gen-2-of-optimus-humanoid-robot/amp/
- E9. The V3 public reveal had still not happened as of the Q3 2026 call. — SECONDARY: https://mikekalil.com/blog/tesla-optimus-mass-production/

**Figure AI**
- E10. Figure 03 (2025-10-09): "Each fingertip sensor can detect forces as small as three grams". Each palm has a camera. BotQ line capacity is up to 12,000/yr, with a goal of 100,000 robots over 4 years. — VERIFIED: https://www.figure.ai/news/introducing-figure-03
- E11. 1,000th Figure 03 off BotQ on 2026-07-23. ~350 had been built by late April 2026, at one robot per hour. The split between internal and customer units is not disclosed. — SECONDARY: https://theroboticsmedia.com/article/figure-ai-1000th-figure-03-humanoid-botq-manufacturing-milestone-july-23-2026
- E12. Series C of more than $1B at $39B post (Sep 2025). ~$1.9B raised in total. No 2026 priced round found. — SECONDARY: https://seekingalpha.com/news/4495255-figure-raises-1b-in-series-c-hits-39b-valuation-to-scale-humanoid-robot-deployment
- E13. BMW Spartanburg: an 11-month Figure 02 pilot (company-reported), then Figure 03 returned for logistics sequencing. Catalyst Brands distribution agreement in May 2026. — SECONDARY: https://komo.ai/directory/figure-ai ; https://blog.robozaps.com/b/figure-ai-review

**Agility Robotics (Digit)**
- E14. Proposed SPAC with Churchill Capital XI at $2.5B. 2025 net sales were **$1.8M** against a $140M operating loss. Digit runs at 9 customer sites with more than 65,000 operating hours. Orders of more than $300M come from **one** customer. Not closed as of 2026-09-07. — SECONDARY (citing the S-4): https://www.therobotreport.com/agility-robotics-reports-18m-revenue-ahead-of-humanoid-spac/
- E15. Digit pricing: RaaS ~$8,500/month plus a $25k deployment fee, or direct purchase at ~$200k plus a $20k fee plus ~$36k/yr. — SECONDARY (S-4 via the article): same URL as E14.

**Apptronik (Apollo)**
- E16. Raised $520M in Feb 2026 at a valuation above $5B, which is "three times" its first Series A. The Series A now totals more than $935M. Partners: Mercedes-Benz, GXO, Jabil, Google DeepMind. — SECONDARY: https://www.trendingtopics.eu/apptronik-raises-520-million-for-humanoid-robots-valuation-climbs-to-around-5-billion/
- E17. The Mercedes work is still described as a pilot. No unit counts are public. — SECONDARY: https://techcrunch.com/?p=2971261

**1X (NEO)**
- E18. NEO hand (2026-07-09): 25 DoF (22 in the fingers and palm plus 3 at the wrist). Tendons are driven by forearm motors at ~5:1–15:1. Tactile sensing covers "normal force, contact location, and shear". Fingertip flexion force up to 45 N. Wrist rated beyond 2M cycles. — VERIFIED: https://1x.tech/discover/neos-hands
- E19. NEO price is $20,000 or $499/month. Preorders opened 2025-10-28. — SECONDARY: https://en.wikipedia.org/wiki/1X_Technologies
- E20. SoftBank is in talks for majority control at ~$6B (The Information, 2026-08-26; Reuters could not confirm). In 2025 1X sought $1B at $10B and raised "less than half". "No units had shipped to customers". — SECONDARY: https://en.cryptonomist.ch/2026/08/27/softbank-1x-technologies-acquisition/

**Boston Dynamics (Atlas)**
- E21. Hydraulic Atlas was retired on 2024-04-16 and an all-electric successor launched the next day. — SECONDARY: https://singularityhub.com/2024/04/17/boston-dynamics-says-farewell-to-its-humanoid-atlas-robot-then-brings-it-back-fully-electric/
- E22. Production Atlas (CES, Jan 2026): 56 DoF. All 2026 units go to Hyundai RMAC and Google DeepMind. Outside customers from early 2027. Hyundai's Georgia plant from 2028. — SECONDARY: https://engadget.com/big-tech/boston-dynamics-unveils-production-ready-version-of-atlas-robot-at-ces-2026-234047882.html (the BD primary blog returned a bot-check page)
- E23. New hand (2026-10-02): 13 DoF, **four fingers**, "dense tactile pressure sensors across the fingertips and palm". BD says dropping the pinky "reduces cost, size, actuator count and potential failure points". — SECONDARY: https://roboticsandautomationnews.com/2026/10/02/boston-dynamics-unveils-new-four-finger-hand-for-atlas-humanoid-robot/105440/

**Unitree**
- E24. Official US shop (fetched 2026-10-27): G1 from **$13,500**, R1 from **$4,900**, R1-A from $4,290, H2 $29,900, H2 Plus $100,000, H1 $90,000, Dex5-S hand from $6,350. — VERIFIED: https://shop.unitree.com/
- E25. The brief's "R1 ~$5.9k" and "G1 ~$16k" are both higher than the official US list prices in E24. — CONFLICT (E24 governs): https://shop.unitree.com/
- E26. 2025 revenue RMB 1.71B ($250M). Adjusted net profit RMB 600M. Gross margin "nearly 60%". Average humanoid price fell from RMB 593,400 (~$85k, 2023) to RMB 167,600 (~$25k, 2025). — SECONDARY (prospectus via Rest of World, 2026-03-31): https://restofworld.org/2026/unitree-china-humanoid-robot-shanghai-ipo/
- E27. STAR Market IPO on 2026-08-19 at RMB 150.80/share (~RMB 61B, ~$9B). Market cap ~$30B on 2026-09-09 (~125x 2025 revenue). 2025 humanoid revenue was RMB 868M (51.78% of the total). — SECONDARY: https://www.therobotreport.com/unitree-shares-down-53-from-ipo-debut/

**AgiBot**
- E28. Near a RMB 1–1.5B round at ~RMB 50B (~$7B), per Caijing on 2026-10-14. 2025 revenue RMB 1.05B. The Hong Kong IPO has slipped past end-2026. — SECONDARY: https://technode.com/2026/10/14/robot-maker-agibot-nears-new-funding-round-at-rmb-50-billion-valuation/
- E29. 15,000 robots cumulative by June 2026. — SECONDARY: https://autonews.gasgoo.com/articles/news/agibot-launches-hong-kong-ipo-process-2082120389458100225

**UBTech**
- E30. H1 2026 interim results: full-size humanoid revenue RMB 590.3M (+1,445%) on **921 units**. Group revenue RMB 1,269.1M. Group gross margin 44.7%. Loss RMB 338.8M. Annual production target 10,000 units. — VERIFIED (HKEX filing): https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0828/2026082801691.pdf
- E31. ANALYST: E30 implies ~RMB 641k (~$90k) of revenue per full-size unit, services included. That is a Chinese *industrial* full-size price point roughly 4–7x Unitree's retail range. SAG's H1 estimate for UBTech (700, E4) is below the company's 921. — ANALYST/CONFLICT: E30 URL

**Galbot / Fourier / Sanctuary / others**
- E32. Galbot raised RMB 2.5B (~$350M) in Mar 2026. Valuation was above RMB 20B (~$2.8–3B) as of Dec 2025. Hong Kong IPO in preparation. — SECONDARY: https://technode.com/2026/03/02/humanoid-robot-maker-galbot-raises-rmb-2-5-billion/ ; https://autonews.gasgoo.com/articles/icv/raising-nearly-5-billion-in-3-months-valuation-topping-20-billion-what-makes-galbot-stand-2028720517496729601
- E33. Galbot G1 (wheeled, two arms) runs unmanned pharmacies in Beijing, claiming ~99.5% grasp success. — SECONDARY: https://news.cgtn.com/news/2026-03-13/China-s-first-pharmacy-robot-goes-into-service-in-Beijing-1LtZ7juLcZ2/share_amp.html. Its end-effector type: NOT FOUND (searched the Galbot pages on kr-asia, chozan and aiwiki).
- E34. Fourier 2026 valuation: NOT FOUND. Its 2025 figures conflict (a "¥8B vs ¥80B" typo). — CONFLICT: https://eu.36kr.com/en/newsflashes/3112357616225800 ; https://en.wikipedia.org/wiki/Fourier_(company)
- E35. Sanctuary AI: ~$140M raised by mid-2024. Founder-CEO left in Nov 2024 and ~30 staff were laid off. Daniel Friedmann became CEO on 2026-06-26. The company now sells "hardware-agnostic physical AI for existing robots". — SECONDARY: https://humanoid.observer/companies/sanctuary-ai/ ; https://betakit.com/robotics-startup-sanctuary-ai-appoints-former-mda-exec-as-ceo/
- E36. Sanctuary's own site lists the robotic hand under "In Development". It also says it "deploys Physical AI on commercially available robotic systems". — VERIFIED (company site, fetched 2026-10-27): https://sanctuary.ai/
- E37. Zeon invested in Sanctuary on 2026-05-26 to develop rugged elastomer parts for industrial robot hands. — VERIFIED: https://www.zeon.co.jp/en/news/assets/pdf/260526.pdf
- E38. Mobileye agreed to buy Mentee Robotics for ~$900M ($612M cash plus up to 26.2M shares) on 2026-01-06. Mentee targets series production in 2028. — SECONDARY: https://techcrunch.com/2026/01/06/mobileye-acquires-humanoid-robot-startup-mentee-robotics-for-900m
- E39. XPeng IRON is targeting mass production by end-2026, with retail deployments in early 2027. Not confirmed as started. — SECONDARY: https://autonews.gasgoo.com/articles/ev/70039692
- E40. Hexagon AEON was chosen for BMW's Leipzig pilot (test Dec 2025, aiming for production use from summer 2026). Status unconfirmed. — SECONDARY: https://www.all-about-industries.com/humanoid-robots-bmw-leipzig-series-production-aeon-summer-2026-battery-components-a-48cbcbdac063ce101f13738e2d527403/
- E41. Skild AI raised $1.4B at more than $14B (2026-01-14). This is the foundation-model layer the memo says Clone will rely on. — VERIFIED (company release): https://www.businesswire.com/news/home/20260114335623/en/Skild-AI-Raises-%241.4B-Now-Valued-Over-%2414B

### (b) Dexterous-hand specialists and approaches

**Clone's hand (for comparison)**
- E42. 2023 hand: 27 DoF, 37 hydraulic muscles, grips ~15 lb, "less than $2,800" in materials. "16 advanced AI labs have already pre-ordered" with shipping planned for 2023. — CLAIMED (company via Freethink, 2023-03-04): https://freethink.com/robots-ai/humanoid-robots-clone-hand
- E43. Clone Alpha spec (Dec 2024): 164 DoF in the upper torso. 26 DoF across "hand, wrist, and elbow". 4 depth cameras, 70 inertial sensors, and "320 pressure sensors for muscle force feedback". 500 W pump (40 SLPM at 100 psi). Jetson Thor. 279 preorder units. — CLAIMED (via Interesting Engineering): https://interestingengineering.com/innovation/clone-alpha-humanoid-robot-unveiled-poland
- E44. Hand demo (Nov 2025): 27 DoF. "Pressure pads in the palm detect how firmly the hand grips". 70 IMUs, 36 electro-hydraulic valves. Myofibers "survived 650,000 test cycles without fatigue". Operator wears a sensor glove (teleoperation). — CLAIMED (via IE, 2025-11-24): https://interestingengineering.com/ai-robotics/clone-demos-creepy-humanoid-hand
- E45. 2026-10-01: Torso 3 hand video is "labeled as teleoperation". Torso 4 launches in November and targets "stationary bimanual" enterprise tasks. No tactile sensing is mentioned. — SECONDARY: https://www.humanoidsdaily.com/news/clone-torso-3-hand-demo-torso-4-november
- E46. Fingertip tactile array on any Clone hand: NOT FOUND. Searched clonerobotics.com (home and /android/), Interesting Engineering (2024 and 2025), Freethink, humanoidsdaily, Robozaps and web search for "Clone Robotics tactile".
- E47. The company site's sensing language is "Human-level strength. Even in the fingers." It makes no touch or tactile claim. — VERIFIED (as a company claim): http://www.clonerobotics.com/android/
- E48. Memo tile values of "$1.1K" hand BOM and "25 DoF" — UNREAD (?). The public 2023 figure is "<$2,800 materials" (E42). — CONFLICT pending a legible memo.
- E49. Memo cycle life of "100,000(?) cycles" against the public "650,000 cycles" (E44). — CONFLICT pending a legible memo.

**Competitor hands**
- E50. Shadow Dexterous Hand: 24 joints, 20 DoF. Sold in an air-muscle version (20 antagonistic pairs, a pressure sensor per muscle) and an electric version (20 DC motors). Tactile options include the SynTouch BioTac. — SECONDARY: https://en.wikipedia.org/wiki/Shadow_Hand
- E51. Why the air-muscle Shadow hand was hard: 36 air muscles for 25 movements "results in the need for 72 valves for each Hand". Standard valves had to sit off-board, causing "significant cabling and control issues". — SECONDARY (2005 trade press): https://www.emeraldinsight.com/insight/content/doi/10.1108/ir.2005.04932bad.001/full/html
- E52. "Shadow abandoned air muscles for motors": not exactly true. Both versions remain listed (E50). Electric became the mainstream product for precision and self-containment (wiki-sourced only). No statement from Shadow itself was found. — CONFLICT/SECONDARY: https://www.aiwiki.ai/wiki/shadow_robot
- E53. Shadow Hand price is ~$110–125k (about RMB 1.5M). — SECONDARY: https://eu.36kr.com/en/p/3239621788565507 ; https://www.roboticscenter.ai/de/compare/wuji-hand-vs-shadow-hand
- E54. Sanctuary hydraulic hand (Dec 2024): 21 DoF. Miniaturised valves are "fast and inexpensive" and were "tested for more than two billion cycles". — CLAIMED (via Inspenet): https://inspenet.com/en/noticias/sanctuary-ai-advances-with-21-degree-of-freedom-hydraulic-hands
- E55. Sanctuary pairs its hydraulic actuation with "high-fidelity tactile sensing to enable a near-human sense of touch". So even the hydraulic-hand precedent treats touch as necessary. — CLAIMED (company): https://sanctuary.ai/?p=947
- E56. Sanctuary valve patent US 12,435,813 B2: 20 hoses to the hand to control 18 DoF, an example of the plumbing burden. — VERIFIED: https://patentsgazette.uspto.gov/week40/OG/html/1539-1/US12435813-20251007.html
- E57. Unitree Dex5-1: 20 DoF (16 active). The Dex5-1P variant carries 94 tactile sensors. — VERIFIED (product page): https://unitree.com/Dex5-1 . Dex5-S lists from $6,350 (E24).
- E58. SharpaWave: 22 active DoF, more than 1,000 tactile pixels per fingertip, 0.005 N sensitivity. Shipping since Oct 2025. ~$50,000 per LatePost. — SECONDARY: https://mikekalil.com/blog/sharpa-north-ces-2026/ ; https://www.innovaciondigital360.com/industria-4-0/linkerbot-manos-roboticas-china/
- E59. Linkerbot: Series B+ at $3B, now seeking $6B (Reuters, 2026-05-04). "More than 80 per cent share by volume" in high-DoF hands. Production of "roughly 5,000 units monthly" scaling to 10,000. Hands range from 6 to 42 DoF. — SECONDARY: https://thenextweb.com/news/linkerbot-china-robot-hand-6-billion-valuation
- E60. Linker Hand O7 is priced at RMB 8,800 (~$1.2k). The industrial Linker Hand reaches 25–30 DoF at ~RMB 50,000 (~$7k). — SECONDARY (2025-04-08): https://eu.36kr.com/en/p/3239621788565507
- E61. Inspire RH56 series (mostly 6 DoF) sells for $4,500–$12,199 through a reseller. Tactile variants are available. — SECONDARY: https://www.knoxlabs.com/collections/robotic-hands
- E62. Wuji Hand: 20 active DoF. Price $16k is listed only by a reseller (unverified). — SECONDARY: https://www.roboticscenter.ai/de/compare/wuji-hand-vs-shadow-hand
- E63. Mimic (Swiss, tendon hand with 21 joints) raised a $16M seed in Nov 2025. Valuation undisclosed. — SECONDARY: https://pulse2.com/mimic-16-million-raised-for-advancing-physical-ai-and-deploy-dexterous-robotics-across-global-industries
- E64. **Cost of a high-DoF hand today** (ANALYST synthesis of E6, E24, E53, E58–E62):

| Hand | Cost or price | Type |
|---|---|---|
| Linker O7 | ~$1.2k | low DoF |
| Inspire 6-DoF | $4.5–7k | |
| Unitree Dex5-S | $6.35k | 20 DoF |
| Linker industrial | ~$7k | 25–30 DoF |
| Wuji | ~$16k | |
| Optimus V3 hand | ~$12k+ per robot (cost) | |
| Sharpa | ~$50k | |
| Shadow | $110–125k | |

Clone's figure is a materials cost of $1.1k (?) to $2.8k, which is a BOM, not a price. That is cheap per DoF, but the absolute dollar gap to Chinese motor hands is now ~3–6x, not 10–20x.

### (c) The memo's two load-bearing competitive claims

- E65. BofA Institute (2026-03-12): a China-built humanoid's BOM was "$35,000 in 2025", expected to fall "below $17,000 by 2030". Western "pilot-stage development" units cost "$90,000 to 100,000". — VERIFIED: https://institute.bankofamerica.com/content/dam/transformation/physical-ai-part-2.pdf
- E66. BofA 2030 BOM split: linear actuators 27%, rotary actuators 24%, dexterous hands 19%, control 10%, vision and sensors 4%, energy 4%, other 12%. — VERIFIED: same PDF.
- E67. Morgan Stanley "Humanoid 100" (Feb 2025), Optimus Gen 2 class: upper body has 16 actuators at ~$26k (~47% of total), lower body 12 actuators at ~$26k (~48%). That implies a total of ~$55k. — SECONDARY (search-index excerpt of the MS PDF; direct fetch failed): https://advisor.morganstanley.com/john.howard/documents/field/j/jo/john-howard/The_Humanoid_100_-_Mapping_the_Humanoid_Robot_Value_Chain.pdf
- E68. Secondary write-ups of the MS figure give actuators "~56%" and hands ~$9.5k (17.2%). That does not reconcile with E67. — CONFLICT: https://humanoid.guide/humanoid-joint-actuator-cost/ ; https://www.grabarobot.com/blog/humanoid-robot-bill-of-materials-cost-2026/
- E69. Goldman Sachs (Feb 2024): manufacturing cost of $30k–$150k per unit, down ~40% from $50k–$250k. — SECONDARY (GS insights page): https://www.goldmansachs.com/intelligence/pages/the-global-market-for-robots-could-reach-38-billion-by-2035.html
- E70. Clone's own cost claim: "manufacture a full musculoskeletal android for under $20K" (CEO Dhanush Radhakrishnan, Mar/Apr 2026). — CLAIMED: https://robotnews.therundown.ai/p/clone-20k-synthetic-human
- E71. Clone roadmap: surgical-tool torso late 2026, walking 2027, hotel "robo butler" 2028. — CLAIMED: https://blog.robozaps.com/b/clone-protoclone-review ; https://robotnews.therundown.ai/p/clone-20k-synthetic-human
- E72. **Test of claim 1, "~1/10 cost of motor-driven competitors"** (ANALYST, from E5, E6, E24, E26, E65–E70):
  - **Against Western motor-driven units.** Clone's "<$20k" is 1/3 of Optimus V3 (>$60k), 1/4.5–1/5 of Western pilot units ($90–100k) and ~1/2.75 of MS Optimus Gen 2 (~$55k). It is never 1/10.
  - **Against Chinese units.** Clone's "<$20k" is 0.57x BofA's 2025 China BOM ($35k) and *above* BofA's 2030 China BOM (<$17k). It is also *above* Unitree G1 retail ($13,500), a price that includes margin. Unitree's company-level ~60% gross margin implies product cost well under $10k on the G1. That is an assumption, since humanoid-specific margin is not disclosed.
  - **Where 1/10 does appear.** Only against Agility's ~$200k direct *price* (E15), which compares a cost with a price.
  - **Structural ceiling.** Actuators plus hands are ~70% of BOM (E66). Even free actuation leaves ~30% of BOM (compute, sensors, battery, structure) untouched. A hydraulic system also adds a pump, valves and plumbing. So a whole-robot 1/10 against a cost-optimised rival is arithmetically implausible.
  - **Verdict:** CONFLICT. The true multiple is ~1/3–1/5 against Western prototypes and ~parity against Chinese units. Clone's figure is also an unaudited claim at an unstated volume, for a robot that does not yet walk.
- E73. **Test of claim 2, "price to prevent competitors from ever achieving economies of scale"** (ANALYST, from E1–E5, E10, E11, E26, E29, E30, E71):
  - Rivals are already at volume: AgiBot ~5,168 (2025) and ~8,400 (H1 2026), with 15,000 cumulative. Unitree 5,500 (2025, ~60% gross margin), 5,900 (H1 2026). UBTech 921 in H1 2026, target 10,000/yr. Figure 1,000 built, line capacity 12k/yr. Tesla's line is designed for 1M/yr.
  - Clone's first commercial product is targeted for 2028 (E71) and its biped MVP for Sept 2027 (memo, CLAIMED).
  - By then the leaders will have shipped tens of thousands of units cumulatively at $5k–$30k retail (Unitree) and RMB ~600k industrial (UBTech).
  - **Verdict:** REFUTED as a strategy for the market as it stands today. At most, Clone could avoid being *undercut* in a niche.
- E74. ANALYST: the cost claims, even if true, buy less than the memo implies. Unitree already sells at prices Clone targets for 2028, with a ~60% gross margin and ~$90M adjusted profit (E26). Clone's cost edge would therefore have to show up as **capability per dollar** (DoF, dexterity, compliance), not as the lowest price. That makes the hand's real-world autonomous performance, including touch (Casey's crux), decision-gating.

### (d) Valuation comps (pre-Series A / Series A humanoid and hand companies, 2023–26)

| Company | Date | Round | Raised | Post-money | Hardware status at the time | Tag / source |
|---|---|---|---|---|---|---|
| **Clone** | Nov 2026 (closing) | Pre-Series A bridge | $?M | **$300M or $360M (?)** | Upper torso only, teleoperated demos, no walking, 0 customers | UNREAD (memo) |
| Clone | 2023 | Republic Reg CF | — | $30M cap | Hand prototype; campaign later withdrawn and refunded | SECONDARY https://blog.robozaps.com/b/clone-protoclone-review |
| Clone | to Mar 2026 | cumulative | ~$17M | n/a | | CLAIMED (CEO) same URL |
| Mentee Robotics | Mar 2025 | last private | >$40M cumulative | ~$162M | Pre-revenue humanoid | SECONDARY (PitchBook via Globes) https://en.globes.co.il/en/article-1001531330 |
| Mentee (exit) | Jan 2026 | Acquired by Mobileye | — | ~$900M | Commercial production 2028 | SECONDARY https://techcrunch.com/2026/01/06/mobileye-acquires-humanoid-robot-startup-mentee-robotics-for-900m |
| 1X | Mar 2023 | Series A2 | $23.5M | $210M | | SECONDARY https://komo.ai/directory/1x-technologies-funding |
| 1X | Jan 2024 | Series B | $100M | ~$820M | | SECONDARY same |
| Figure | May 2023 | Series A | $70M | ~$400–500M | | CONFLICT https://multiples.vc/private-comps/figure ; https://lw.com/en/news/latham-watkins-advises-figure-in-us70-million-series-a-financing |
| The Bot Company | 2024 → Mar 2025 | A → B | $150M + $150M | $550M → $2B | Pre-product, non-humanoid | SECONDARY https://www.forbes.com.au/news/entrepreneurs/cruise-cofounder-raised-150m-for-household-robot-startup/ ; https://fidelity.com/news/article/top-news/202503211543RTRSNEWSCOMBINED_KBN3FY1XJ-OUSBS_1 |
| Dyna Robotics | Sep 2025 | Series A | $120M | >$600M | Commercial folding robots | SECONDARY https://sacra.com/c/dyna-robotics |
| Mimic (hand) | Nov 2025 | Seed | $16M | undisclosed | Hand pilots | SECONDARY https://pulse2.com/mimic-16-million-raised-for-advancing-physical-ai-and-deploy-dexterous-robotics-across-global-industries |
| Sanctuary (hydraulic hand) | Mar 2022 | Series A | CAD 75.5M | undisclosed | ~$140M total, since pivoted | SECONDARY https://humanoid.observer/companies/sanctuary-ai/ |

Later-stage marks (context only): Apptronik >$5B (E16). Agility $2.5B SPAC on $1.8M sales (E14). Galbot ~$3B (E32). Linkerbot $3B (hands, E59). AgiBot ~RMB 50B (E28). 1X ~$6B in talks, down from a $10B ask (E20). Unitree ~$30B public (E27). Figure $39B (E12). Skild $14B (E41).

- E75. ANALYST on valuation:
  - Clone's $300–360M post is above both Mentee's last private mark and 1X's Series A2. It sits below Dyna, which had commercial deployments.
  - The two credible "hand thesis" comps cut against the price. Sanctuary (hydraulic, dexterity-first) has pivoted. Linkerbot (motor-driven hands at volume) is valued at $3B, mostly on volume.
  - At ~$17M raised, a $300–360M post implies the bridge buys ~1–5% of the company, depending on the unread raise size. Series A pricing at $75–100M (memo, ?) will need ~3–5x more evidence than exists today.

### (e) Honest head-to-head: Clone vs the top 6

Cells cite the evidence lines above.

| | **Clone** | **Tesla Optimus** | **Figure** | **Unitree** | **AgiBot** | **1X** | **BD Atlas** |
|---|---|---|---|---|---|---|---|
| Hand DoF / actuation | 26–27 DoF, water-hydraulic muscles (CLAIMED, E42–E44) | 22 DoF, tendon, forearm motors (SECONDARY, E7) | not stated; 5-finger electric (E10) | Dex5-1: 20 DoF (16 active), motors (VERIFIED, E57) | NOT FOUND | 25 DoF incl. wrist, tendon, forearm motors (VERIFIED, E18) | 13 DoF, 4 fingers, direct drive (SECONDARY, E23) |
| Touch / force sensing in hand | 320 muscle-pressure sensors, palm pads; **no fingertip tactile found** (CLAIMED + NOT FOUND, E43, E44, E46) | tactile on all fingers since Gen 2 (SECONDARY, E8) | fingertip 3 g plus palm camera (VERIFIED, E10) | Dex5-1P: 94 tactile sensors (VERIFIED, E57) | NOT FOUND | normal force, shear and contact location (VERIFIED, E18) | dense fingertip and palm tactile (SECONDARY, E23) |
| Locomotion | **none shown**; biped MVP Sept 2027 (memo), walking demo 2027 (E71) | walking biped | walking biped | walking, running | biped and wheeled | walking biped | walking biped |
| Autonomy evidence | teleoperated only (E44, E45) | early production, autonomous demo video promised (E5) | Helix VLA, BMW logistics (E11, E13) | mostly research and education buyers (E26) | thousands deployed (E29) | autonomy unproven, no units shipped to customers (E20) | DeepMind Gemini integration (E22) |
| Units deployed / shipped | **0** | ~150 (2025, E2) | ~150 (2025), 1,000 built by Jul 2026 (E2, E11) | 5,500 (2025), 5,900 (H1 2026) (E3, E4) | 5,168 (2025), ~8,400 (H1 2026) (E1, E4) | 0 to paying customers (E20) | 2026 fleet to Hyundai and DeepMind (E22) |
| Named customers | pilots "being signed", none signed (memo) | internal | BMW, Catalyst (E13) | research and education plus retail | many (E1) | EQT framework (SECONDARY) | Hyundai, DeepMind |
| Funding / valuation | ~$17M raised; $300–360M (?) | Tesla balance sheet | ~$1.9B; $39B | public, ~$30B | ~RMB 50B | ~$6B in talks | Hyundai-owned |
| Cost / price | "<$20k" cost (CLAIMED, E70) | >$60k cost (E6) | not public | G1 $13.5k, R1 $4.9k retail (E24) | NOT FOUND | $20k price (E19) | not public |

**Where Clone genuinely leads (ANALYST, best case):**
- **Anthropomorphic DoF and muscle count in one integrated hand and arm.** 26–27 DoF against 20–25 for the best motor hands. Clone is not the overall DoF leader, though: Linkerbot's research hand reaches 42 DoF (E59).
- **Intrinsic compliance and back-drivability** from fluid muscles. This is potentially safer near people and may suit learning from human-motion data, but it is not demonstrated in autonomy.
- **Claimed materials cost per hand DoF** ($1.1k (?) to $2.8k for ~27 DoF), against ~$6–7k retail for comparable Chinese motor hands (E60, E24). This is plausible but unaudited.

**Where Clone trails:** locomotion, demonstrated autonomy, published tactile sensing, units, customers, capital, supply-chain scale, and durability evidence.

Capital, ANALYST: Clone has raised ~$17M (CLAIMED). Against that, Sanctuary raised ~$140M (~8x), Agility ~$641M (~38x, https://www.robotics247.com/article/agility-robotics-goes-public-merges-with-churchill-capital-corp-xi-at-2.5-billion-valuation), Apptronik ~$1B (~55x, E16) and Figure ~$1.9B (~110x, E12). On durability, Clone claims 650k cycles (E44), while 1X's wrist exceeds 2M cycles (E18) and Sanctuary's valves exceed 2B cycles (E54), all three CLAIMED.

---

## 3. What I could not reach

- **Morgan Stanley "Humanoid 100" PDF.** WebFetch timed out; curl returned an empty reply. A retry with different headers was denied by the auto-mode classifier as bot-check circumvention, so I did not pursue it. The MS figures rest on a search-index excerpt plus secondary write-ups (E67, E68).
- **Blocked pages:** SCMP (403), Visual Capitalist (403), Republic.com/clone (403), aiwiki Clone Alpha (429), and the Boston Dynamics blog (bot-check page). Secondary sources were used instead.
- **Primary filings not fetched:** Unitree's STAR prospectus (Chinese-language exchange filing; used Rest of World and Robot Report). Agility's S-4 on EDGAR (used The Robot Report). Tesla's Q3 2026 shareholder letter (used call recaps). Figure's own news post for the 1,000th unit.
- **NOT FOUND:**
  - AgiBot hand DoF and tactile specs, and AgiBot unit prices.
  - Galbot end-effector type.
  - Fourier's 2026 valuation.
  - A Figure hand DoF count.
  - Any Clone fingertip tactile sensor.
  - Any Clone signed customer or shipped hand. The 2023 claim of "16 AI labs pre-ordered" (E42) has no delivery evidence.
  - The Delta4 memo's legible hand-comparison table (illegible in our copy).
- I did not read the sibling sweeps (company, tactile), to keep this one independent for cross-checking.

---

## 4. Ranked DD questions for the company

Status for all: NOT YET ASKED. First ask 2026-10-27; expires 2026-12-26 (60-day rule).

**P1 (decision-gating)**
1. **Live autonomous demo.** Show Torso 4 running *autonomously* (not teleoperated), live: grasping a fragile and a heavy object, with logged grip force against ground truth. *Moves:* the "hand is where Clone leads" claim and Casey's tactile crux. Without it, the hand lead is only on paper.
2. **Sensing architecture.** Does any Clone hand have fingertip tactile sensing (taxels, shear)? If not, what is the plan, cost and date? What is the error of muscle-pressure-derived fingertip force, in N and % with hysteresis, across the contraction range? *Moves:* feasibility of autonomous manipulation, and parity with Figure, 1X, Atlas and Sharpa.
3. **Cost basis for "1/10".** Provide an itemised BOM for the hand ($1.1k?) and the full android (<$20k) at a stated volume, including pump, valves, reservoir, battery and compute. Which competitor cost is the denominator? *Moves:* claim 1 (CONFLICT in E72) and the unit economics in the memo.
4. **Myofiber cycle life.** Is it 100k (memo?) or 650k (2025 public), and under what load, stroke and pressure? What is the expected muscle-replacement interval, in hours, at industrial duty? *Moves:* the durability risk the memo itself flags, and service cost against motor rivals (1X >2M cycles, Sanctuary >2B).

**P2 (score-moving)**
5. **Pilots.** For each named pilot (AST SpaceMobile, the automotive OEMs, the hotel group, the logistics firm), give status (LOI, signed or paid), scope, price and start date. *Moves:* deployment column and revenue timing.
6. **Hydraulics in operation.** Give leakage and water-management data, system efficiency (W per kg payload), and torso and biped runtime on battery. *Moves:* competitiveness against electric rivals, and the BD and Sanctuary precedent (E21, E35).
7. **Why now?** Why will water-hydraulic muscles win where Boston Dynamics (hydraulic Atlas) and Sanctuary (hydraulic hand) moved away? What specifically differs? *Moves:* technical-risk score.
8. **Pricing.** What is the target ASP for Torso 4 and for the biped, against Unitree ($4.9k–$30k retail), UBTech (~$90k per industrial unit) and Agility (~$200k)? *Moves:* claim 2 (REFUTED in E73) and the go-to-market.
9. **Hand or muscle supply business.** Will Clone sell hands or Myofibers to other makers, as Linkerbot does with hands? Were any of the 2023 hand preorders from "16 AI labs" delivered? *Moves:* an alternative path to winning, and the company's delivery track record.

**P3 (completeness)**
10. **Valuation history.** Provide the full financing history with post-money at each round (2023 seed, Republic, 2025), and the basis for $3?0M against comps (E75). *Moves:* the valuation score.
11. **Data and models.** What are the teleoperation data volume, the foundation-model partner (if any), and compute? *Moves:* the autonomy-stack column.
12. **Manufacturing.** Provide supplier quotes or a line plan backing "10,000(?) Clones at a couple of million dollars of capex". *Moves:* scale credibility.
