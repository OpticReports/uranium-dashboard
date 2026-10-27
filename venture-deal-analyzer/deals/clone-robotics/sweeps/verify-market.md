# Counter-agent: market sweep verification

Checked 2026-10-27 against `sweep-market.md`, which I read in full.
**Verdict: APPROVED WITH CORRECTIONS.** The sweep's direction holds:
- paid humanoid work is small;
- the FCC listing blocks a foreign-built mobile Clone;
- Clone discloses no touch sensing.

Ten of the 17 load-bearing claims need corrections. Four of them change the framing:
- **Touch-gain numbers (#17).** These are overstated.
- **Unitree price floor (#14).** The comparison is not like-for-like.
- **Agility's $300M order (#5).** It comes from a single related-party customer.
- **PI paper (#10).** It does not undercut the human-hand thesis at finger level.

How I checked:
- **FCC.** I re-downloaded both FCC PDFs. Their sha256 matches the sweep's copies (DOC-423682A1 `052e176e…5935`, DA-26-996A1 `3919ef72…0f83`), and I re-read them in full.
- **Agility.** I read the S-4/A financial statements and notes in the sweep's saved copy (sha256 `eefcf36c…1782`). I did not re-download it.
- **Web pages and papers.** I re-fetched every other cited page with WebFetch. I read the arXiv full-text HTML for MoDE-VLA and ResTacVLA, not search summaries.

Limits on what I could check:
- **Search.** The shared web-search budget was exhausted before my first query. I therefore ran **no searches** and used only direct fetches of known URLs.
- **Blocked fetches.** The FCC Covered List page (fcc.gov/supplychain/coveredlist) returned 403, and DA 26-786 returned 429. A curl retry of the Covered List page was blocked by the harness as bot-check circumvention, and I did not try to get around it.

**Prompt-injection log:** none. I asked about text addressed to AI on every fetch, and every fetch answered "no".

## 1. Claim-by-claim verdicts

| # | Claim (short) | Verdict | What I checked / correction |
|---|---|---|---|
| 1 | FCC Covered-Listed foreign-produced "advanced robotic devices" on 2026-07-28, "regardless of the nationality of origin". New models are barred; existing models, past purchases and federal use are unaffected | **CONFIRMED** (VERIFIED) | All verbatim in the fact sheet: https://docs.fcc.gov/public/attachments/DOC-423682A1.pdf<br>**Nuances:**<br>(a) The wording is "*generally* prohibited".<br>(b) The trigger is the place of production ("produced in a foreign country"), not the company's nationality. A US-built Clone is outside the listing.<br>(c) "Does not affect sales to, or use by, the federal government." |
| 2 | Only 2 robot Conditional Approvals exist as of 2026-09-18 (Husqvarna 2026-09-09, ANSCER 2026-09-18), both conditional on an onshoring plan | **CONFIRMED-WITH-CORRECTION** | **For 2026-09-18 it is exact** (DA 26-996, Appendix B). Footnote 7 says robot approvals "remain effective indefinitely, so long as the entity… abides by the onshoring plan". That is open-ended, whereas router approvals expire in 2027–28. https://docs.fcc.gov/public/attachments/DA-26-996A1.pdf<br>**Not reproduced for today (2026-10-27):** the live list returned 403 and no search budget was left. The exec summary's "so far" is therefore 39 days stale.<br>**ANALYST overreach:** "Sweden and India" is not stated in DA 26-996. |
| 3 | The robot definition excludes "fixed/nonmobile robots". Applications need a component country-of-origin BOM and a time-bound onshoring plan. A torso falling outside is ANALYST | **CONFIRMED** (SECONDARY) | **Cooley (dated 2026-07-31, updated 2026-08-27), verbatim:**<br>• exclusions: "fixed/nonmobile robots";<br>• application contents: "detailed bill of materials and country of origin for all components"; "verifiable US manufacturing and onshoring plan that is time-bound, including expected capital expenditures and workforce deployment, overseen by a dedicated officer"; "quarterly updates".<br>Source: https://www.cooley.com/news/insight/2026/2026-07-31-foreign-produced-power-inverters-and-advanced-robotic-devices-added-to-fcc-covered-list<br>**Not checked against the primary:** DA 26-786 returned 429.<br>**ANALYST additions:**<br>• Prong 1 requires "movement on the ground".<br>• Prong 4 requires network connectivity of at least 200 kbps.<br>• Both are counsel questions. |
| 4 | Agility FY2025 net sales $1,781,967 ($1,131,860 related parties); H1 2026 $174,362; cash $14.7M at 2026-06-30; deployed work is totes with modular end effectors | **CONFIRMED-WITH-CORRECTION** | **All numbers are exact** (S-4/A F-46, F-58, F-72). https://www.sec.gov/Archives/edgar/data/2074973/000121390026105334/ea0297114-05.htm<br>**Corrections:**<br>(a) H1 2026 figures are **unaudited**. The exec line calls them "audited".<br>(b) H1 2026 **robot sales were $0**. All of the $174,362 was services.<br>(c) The H1 net loss of $361.9M is inflated by non-cash charges. R&D alone rose about $130.8M on stock compensation tied to the award revaluation.<br>(d) Cash was $14.7M, but Agility then **received about $87.9M in SAFE proceeds in July 2026**. That is not a distress signal.<br>(e) "Modular, interchangeable end effectors" is a **Digit 5** feature (unveiled 2026-09-15), not the deployed fleet's.<br>The ANALYST point stands: deployed paid work uses no dexterous hand. |
| 5 | $300M of orders covering 1,000 Digit 5 robots on 3-year RaaS. $8,500/month. BOM $150K → $75K → $30K. Pipeline about 28,000 vs about 7,000 | **CONFIRMED-WITH-CORRECTION** | **All figures are verbatim** (S-4/A pp. 132–133 and 235), and the RaaS/BOM figures are "illustrative" management estimates.<br>**Missed:**<br>• The risk factors say "**one customer** that has committed to deploy $300 million".<br>• Note 9 says a May-2026 customer, "**also a related party**", gets 453 warrants per robot if it sources at least 1,000 robots (453,000 warrants).<br>• ANALYST, high confidence: this is the same order.<br>**Fix to the 75% line:** the 7,000 figure is the **valuation adviser's (Ocean Tomo)** schedule, limited to "goods movement via totes". It is not Agility "discounting its own pipeline". |
| 6 | Counterpoint H1 2026: >22,000 units (about +300%); AgiBot about 9,700 (43.1%); Unitree >7,000 (31.1%); research, education and entertainment >60%; 2026 forecast >50,000 | **CONFIRMED-WITH-CORRECTION** | Totals, units and the >50,000 (+210%) forecast match (Counterpoint, 2026-08-20, Qi and Wang). https://counterpointresearch.com/en/insights/global-humanoid-robot-shipments-soar-nearly-300-percent-yoy-in-h1-2026<br>**Corrections:**<br>• The >60% bucket is "**entertainment & performance and data production & research**", not "research, education and entertainment".<br>• The page gives "over 43%" and "31%". The decimals come from elsewhere.<br>**Missed:**<br>• Counterpoint expects service and industrial demand to **overtake** those two segments.<br>• It confirms UBTech raised its Walker S 2026 guidance to 5,000 units. That is now VERIFIED; the sweep had it as SECONDARY. |
| 7 | Use mix: Data & Research 27.0%, Manufacturing 12.8%, Logistics 4.9% | **CONFIRMED** (SECONDARY) | Exact on Humanoids Daily (2026-08-20, attributed to Counterpoint). It is consistent with Counterpoint's own rounded 13% and 5%. https://www.humanoidsdaily.com/news/global-humanoid-shipments-surpass-22-000-in-h1-2026-as-agibot-leads-and-form-factor-debates-intensify |
| 8 | Omdia 2025: about 13,000 total; AgiBot 5,168; Unitree 4,200; UBTech 1,000; conflicts with Unitree's >5,500 | **CONFIRMED-WITH-CORRECTION** | The units match TechNode (2026-01-09). The total is worded "**expected to reach** about 13,000", so it is an early-January estimate, not a final count. https://technode.com/2026/01/09/chinas-agibot-leads-global-humanoid-robot-shipments-in-2025-omdia-says/<br>Unitree's prospectus says "**sold 5,500**", not ">5,500", and "over 70%" went to research and education (Rest of World, 2026-03-31). https://restofworld.org/2026/unitree-china-humanoid-robot-shanghai-ipo/<br>The conflict is real: 5,500 vs 4,200, a 31% gap. |
| 9 | BMW: "successful pilot", 30,000+ X3s; Figure 03 "will now start", with no count or commitment | **CONFIRMED-WITH-CORRECTION** | The verbatim phrase is "**successfully completed a pilot**". BMW says "over ten months"; Figure says 11.<br>Figure 03's job is **logistics sequencing**: sorting loose parts into trolleys. It is not line assembly.<br>No unit count or purchase commitment is given. Adcock is quoted on "tactile sensors and palm cameras". https://www.press.bmwgroup.com/global/article/detail/T0458778EN (2026-06-25) |
| 10 | PI: human-to-robot transfer emerges on robots with parallel-jaw grippers; gripper actions come from robot data only | **CONFIRMED-WITH-CORRECTION** | The paper says "gripper" (a 1-D action per arm on ARX and mobile ARX). "Parallel-jaw" is the sweep's gloss; it is reasonable but not verbatim. https://arxiv.org/html/2512.22414v1<br>**Overreach in the ANALYST line:** PI explicitly did **not** transfer grasp actions from human video, because "it is challenging to estimate the openness of a human hand". It shows arm- and task-level transfer only.<br>It is **silent** on whether finger-level human data transfers better to a human-like hand. It does not "undercut" that thesis. |
| 11 | EgoScale: 20,854 h; +54% on a 22-DoF hand; >30% absolute on a G1 7-DoF tri-finger hand; "embodiment-agnostic motor prior" | **CONFIRMED** | All verbatim ("over 20,854 hours"). Authors are NVIDIA, UC Berkeley and UMD; arXiv 2602.16710v1, 2026-02-18. https://arxiv.org/html/2602.16710<br>**Context, in Clone's favour:**<br>• Pretraining uses a 22-DoF hand action space that "preserves human finger articulation".<br>• The G1 needed embodiment-specific adapters plus mid-training.<br>• No tactile input was used anywhere. |
| 12 | Clone's hand page claims only "accurate Myofiber proprioception": no DoF, force, price or cycle figures, no tactile claim | **CONFIRMED (strengthened)** | Re-fetched live: no numbers and no tactile claim. https://www.clonerobotics.com/hand/<br>**The stronger primary source, missed:** the android page's "Nervous System" tab (JS bundle `D8GOK2Ld.js`, sha256 `c9b3f543…715c`) says the Clone runs "with **only proprioceptive and visual feedback**… 4 depth cameras… 70 inertial sensors… and **320 pressure sensors for muscle-level force feedback**". https://www.clonerobotics.com/android/<br>Clone's homepage also displays a 2023 press headline: "lifelike robot hand can be made for just $2,800" (SECONDARY). |
| 13 | Figure 03 fingertip sensors detect "three grams"; palm camera; BotQ up to 12,000 a year | **CONFIRMED** (CLAIMED) | Verbatim: "forces as small as three grams of pressure"; "will **initially** be capable of producing up to 12,000". That is capacity, not output. https://www.figure.ai/news/introducing-figure-03 (2025-10-09) |
| 14 | Unitree G1 from $13.5K with optional tactile on Dex3-1; R1 from $4,900 with no dexterous hand | **CONFIRMED-WITH-CORRECTION** | The prices are exact.<br>**But the $13.5K G1 has no hand at all.** Its hand-DoF column reads "/". The Dex3-1 (7 DoF, tactile optional) is on the **G1 EDU, priced "Contact sales"**. https://www.unitree.com/g1<br>R1 AIR is $4,900 and R1 $5,900; on the R1 EDU a dexterous hand is "Optional". https://www.unitree.com/R1<br>The exec line's "price floor below Clone's <$20K" therefore compares **hand-less** bodies with a hand-centric product. |
| 15 | Clone's prototype is pneumatic, with hydraulics and a 500 W pump planned; about 500 sensors; this conflicts with "powered with only water" | **CONFIRMED-WITH-CORRECTION** | Futura (2026-06-11) states this **without a source**. https://www.futura-sciences.com/en/why-this-humanoid-robot-is-freaking-everyone-out-and-advancing-faster-than-ever_33815/<br>**Better primary:** Clone's own Torso 2 YouTube text (2024-12): "pneumatic actuation with off-the-shelf valves", 182 sensors (confirmed by verify-tactile-a and -b). https://www.youtube.com/feeds/videos.xml?channel_id=UCd0xLOw6No5IAsq3Y2-b0eA<br>**The 500 W pump is Clone's own spec**, not "planned": "500 watt electric pump… 40 SLPM… 100 psi". https://www.clonerobotics.com/android/<br>**"About 500 sensors" conflicts** with Clone's own 70 + 320 (+ 4 cameras) and with Torso 2's 182.<br>The conflict is between the demo and the product spec, not within one statement. Torso 4's fluid is unknown and is a DD item. |
| 16 | Tesla: early production on the Fremont line (Q3 2026 call); external deliveries around end-2027 | **CONFIRMED** (SECONDARY) | Verbatim quote; article dated 2026-10-22 citing the Q3 2026 call and deck. It adds a plan of 1M/yr and a 22-DoF hand. https://notateslaapp.com/news/4866/tesla-officially-begins-optimus-robot-production<br>The Tesla primary was not fetched. |
| 17 | MoDE-VLA loses about 8 points without tactile and about 11 without force; ResTacVLA +34.6 over vision-only π0.5 | **CONFIRMED-WITH-CORRECTION** (now VERIFIED from arXiv full text; the framing changes) | **MoDE-VLA** (Table II): full 34%, without tactile 26%, without force 23%. That is **4 tasks × 20 trials**. The baseline is **π0, not π0.5**. https://arxiv.org/html/2603.08122<br>• "Force" means **arm joint torques**, a proprioceptive channel. Tactile means fingertip 6-DoF sensors on 22-DoF Sharpa hands.<br>• So **the proprioceptive channel mattered more than touch**, though the 3-point difference is within noise at n = 20.<br>**ResTacVLA:** 62.8% vs 28.2% = +34.6, on a **Franka arm with a Robotiq 2F-85 parallel gripper** and one GelSight Mini. https://arxiv.org/html/2607.03387<br>• Naive touch (π0.5 w/ T-ResNet) scored **23.2%, below vision-only**. A pretrained tactile encoder scored 42.3% (+14.1).<br>• The +34.6 includes architecture changes.<br>The plain gain from adding touch is **−5 to +14 points**. The exec line "touch and force add about 8 to 35 points" overstates it. |

## 2. Wording fixes to the sweep's executive read

- **Item 2:** "audited revenue… $0.17M in H1 2026" should read **unaudited**. Add that H1 2026 robot sales were $0.
- **Item 6:** replace "about 8 to 35 points" with: arm-torque (proprioceptive) force −11 pp and fingertip touch −8 pp (MoDE, n = 20 per task); touch adds −5 to +14 pp, and up to +34.6 with a new architecture on a gripper.
- **Item 6, add the primary source:** Clone's own page says "only proprioceptive and visual feedback", with 320 muscle-pressure sensors.
- **Item 7:** change "Only 2 robot approvals exist so far" to "as of 2026-09-18". A post-09-18 check was not possible.
- **Item 8:** the G1 at $13.5K and the R1 at $4.9K have no dexterous hand. Remove the "below Clone's <$20K" comparison, or compare against the G1 EDU plus a hand (price undisclosed).
- **§(c), ANALYST line:** PI does not test finger-level transfer, so "undercuts" should read "does not address".
- **§(a), Agility:** the $300M order is from **one related-party customer** with warrants. The 7,000 vs 28,000 split is the adviser's tote-only schedule.
- **§(a), Counterpoint:** relabel the >60% bucket as "entertainment & performance plus data production & research".

## 3. What the sweep missed

**Strongest point missed in Clone's favour.** On Casey's literal crux ("know how hard it's gripping"), Clone does have a force channel. Two pieces of evidence:
- **Clone's disclosure.** Clone discloses **320 pressure sensors for "muscle-level force feedback"** (VERIFIED, https://www.clonerobotics.com/android/).
- **The only ablation that separates force from touch (MoDE-VLA).** Removing the proprioceptive force channel cost **more** (−11 pp) than removing fingertip touch (−8 pp) (https://arxiv.org/html/2603.08122). In ResTacVLA, naively added touch scored **5 points below** vision-only (https://arxiv.org/html/2607.03387).

What Clone lacks is touch: contact location, slip onset and light-contact detection. It does not lack grip-force sensing. How accurate its pressure-based force estimate is remains unmeasured; that is a DD item.

Second point in Clone's favour: the US leader's traction is thinner than the sweep's framing.
- Agility's headline backlog is a **single related-party, warrant-sweetened, milestone-conditional** order.
- Its H1 2026 robot sales were **$0** (S-4/A).

That narrows how far behind Clone really is commercially, though not technically.

**Strongest point missed against Clone.** The sweep's #1 "best honest shot", research and data-collection buyers, is the segment where low-cost Chinese incumbents are entrenched, and it is forecast to lose share:
- **Unitree's mix.** Over 70% of Unitree's 5,500 humanoids sold in 2025 went to research and education (Rest of World, from the prospectus; https://restofworld.org/2026/unitree-china-humanoid-robot-shanghai-ipo/).
- **Unitree's price.** Its average price fell to RMB 167.6k (about $23–25K; confirmed in verify-competition).
- **Counterpoint's outlook.** Counterpoint expects service and industrial uses to **overtake** entertainment and data/research as demand drivers (https://counterpointresearch.com/en/insights/global-humanoid-robot-shipments-soar-nearly-300-percent-yoy-in-h1-2026).
- **FCC grandfathering.** Chinese models authorized before 2026-07-28 stay sellable in the US (FCC fact sheet).

The torso-for-research niche is therefore real, but crowded, cheap and shrinking in share. It cannot carry a $200M post-money valuation on its own (ANALYST).

Also against Clone: Clone's own primary page confirms "**only** proprioceptive and visual feedback". The company itself says it has no touch sensing.

## 4. Other cross-checks

- **Durability bar arithmetic.** 36,000 s / 84 s = 428.6 cycles per shift. × 2 shifts × 250 days = 214,286 a year, and × 5 years = 1.07M. That is correct.
- **Durability conflict with sweep-actuation.** That sweep uses about 1.9M a year per hand muscle, because it assumes several firings per cycle. The two bars differ by about 9x per year. Reconcile them before the IC: they set the pass/fail line for Myofiber cycle life.
- **Goldman CAGR.** 1.4M / 50k = 28, and 28^(1/9) = 1.448. That is correct.
- **Manufacturing plus logistics share.** 17.7% × 22,000 = 3,894. That is correct.
- **Agility cash burn (VERIFIED, S-4/A cash-flow statement).** 2025 operating cash use was $99.8M against $1.78M revenue. That is a useful scale anchor for the $75–100M Series A Clone says it needs.

## 5. Could not verify

- Robot Conditional Approvals after 2026-09-18: the FCC page returned 403 and no search budget was left.
- The primary text of the DA 26-786 definition: HTTP 429.
- The Tesla primary deck.
- Any later Clone disclosure on Torso 4's actuation fluid.
