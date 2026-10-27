# Clone Robotics: tactile and grip-force sweep (the LP's crux)

Swept 2026-10-27. Scope: does Clone's hand have sensor feedback on how hard it grips, and does a fully autonomous hand need that feedback?
Tags: VERIFIED (primary source, URL) / SECONDARY / CLAIMED (company or sponsor only) / CONFLICT / NOT FOUND (where searched) / REFUTED / ANALYST.
The Delta4 memo and deck are mostly illegible (BRIEF.md). No (?) figure from them is used as fact here.

---

## 1. Executive read (8 lines)

1. **Clone's own site says it runs "with only proprioceptive and visual feedback."** The kit listed is 4 depth cameras, 70 inertial sensors (joint angles and velocities) and 320 pressure sensors "for muscle-level force feedback". No first-party page mentions any tactile, fingertip or skin sensor. [VERIFIED, clonerobotics.com/android, live 2026-10-27]
2. **Verdict on the LP's belief: PARTLY TRUE.**
   - True: Clone discloses no touch sensing, so the hand has no contact location, no slip sensing and no fingertip pressure.
   - False: the hand is not blind to force. Every muscle has a pressure sensor, and pressure plus joint angle gives an indirect estimate of muscle force, which bounds grip force.
3. **The indirect estimate is coarse at light grips.**
   - Force models for water-driven McKibben muscles (braided sleeve over a bladder) are off by 9.1–10.5% (absolute error) against measurements.
   - Hysteresis comes from strand-on-strand friction in the braid.
   - Tendon friction, opposing muscles pulling at once and an unknown contact point all add error.
   - Rough estimate (ANALYST): about ±1 N per finger, against 0.005–0.03 N detection floors in rivals' fingertip sensors. That is fine for firm power grips and weak for eggs, grapes, slip and insertion.
4. **Clone's hand feedback is recent and thin, and the public demos are teleoperated.**
   - Joint-angle feedback in the hands was only announced around April 2026 (LinkedIn).
   - Torso 2 ran "hand-written, hardcoded sequences" (Dec 2024).
   - Every public hand demo is teleoperated, including the Oct 1, 2026 Torso 3 demo. No autonomous grasping demo was found.
5. **Touch is not strictly needed, but it pays on the hard tasks.**
   - Without touch: robot policies using only cameras and joint sensors (proprioception) reach 79–100% on lab dexterity tasks (ACT, pi0, Gemini Robotics, OpenAI Rubik's cube with touch sensors switched off).
   - With touch added on fragile, slippery, occluded or insertion tasks: +14 pp (Calandra 2017), +18–19 pp (Calandra 2018), +27.5 pp (ViSk), +25–45 pp (3D-ViTac), >35% (RDP) and up to +35% (VT-WM).
   - Humans with numbed fingertips dropped a 250 g object on 36% of trials, against 0% with feeling intact.
6. **Clone is now the outlier among the leaders.** Figure 03 (3 g), 1X NEO (Jul 2026), Atlas (Oct 2026), Sanctuary (5 mN), Sharpa (>1,000 taxels per fingertip, 0.005 N), Tesla and Unitree Dex5-1P all ship or announce tactile hands. 1X: "vision alone is insufficient for many tasks."
7. **Adding touch is feasible but not cheap or quick.** Magnetic or barometric skins exist off the shelf. A wet, soft-skinned, 27-DoF tendon hand makes integration, sealing and durability hard. It also needs new data and new policies, and it erodes the low-cost-hand story (memo hand-cost figure "$1.1K(?)" unread).
8. **Gate the cheque on two things.** A Torso 4 per-hand sensor sheet, including whether touch is on the BOM or roadmap. And a live, autonomous (not teleoperated) fragile-object and slip demo with trial counts. Both before the SPV closes.

---

## 2. Evidence

### (a) What sensing Clone actually has

**First-party disclosures**

- **[VERIFIED] Android page, "Nervous System" tab.** Live on 2026-10-27; site build timestamp 2026-07-02. The tab text sits in the JS bundle `/_nuxt/D8GOK2Ld.js` (sha256 c9b3f543…715c), not in the static HTML. Source: https://clonerobotics.com/android/ . Verbatim:
  > "The Clone's nervous system was designed for instantaneous neural control of the valves, and thereby the muscles, with only proprioceptive and visual feedback. The Clone is equipped with 4 depth cameras in the skull for vision, 70 inertial sensors that provide joint-level proprioception (angles and velocities) and 320 pressure sensors for muscle-level force feedback. The control boards for the valves and sensor fusion feedback are mounted along the vertebrae with lightning fast microcontrollers sending and receiving information to and from the NVIDIA Jetson Thor inference GPU in the skull running Cybernet, Clone's visuomotor foundation model."
- **[VERIFIED quote; CLAIMED performance] Same page, Vascular tab.** "500 watt electric pump … 40 SLPM volumetric flow rate and 100 psi rating". The Aquajet valve: "100 psi … 2.28 SLPM flow rate, under a watt of power consumption … three-way … 12mm". Source: https://clonerobotics.com/android/
- **[VERIFIED quote] Muscular tab.** Each fibre should give "at least a kilogram of contraction force for a single, three gram muscle fiber", with response "less than 50 ms" and ">30% unloaded contraction". Source: https://clonerobotics.com/android/
- **[VERIFIED quote] Skeletal tab.** "26 degrees of freedom in the hand, wrist, and elbow … upper torso … 164 degrees of freedom". This conflicts with the 27 DoF claimed for the hand alone (see the sensor-count conflict below). Source: https://clonerobotics.com/android/
- **[VERIFIED] Hand page.** Only sensing-adjacent wording:
  - "precision … thanks to accurate Myofiber proprioception"
  - "back-drivable, antagonistic muscles and tendons"
  - "Soft muscle, fat, and skin for a human-like interaction"

  No sensor counts and no tactile wording. Source: https://clonerobotics.com/hand/
- **[NOT FOUND] Tactile wording anywhere on the site.** I grepped the static HTML and all 13 JS bundles of clonerobotics.com (/, /hand, /android, /research, /company) for "tactile", "touch sensor", "fingertip" and "skin sensor". Zero hits; "skin" appears only as the cosmetic layer. The /research page reads "We are currently researching, page will be available soon". Source: https://clonerobotics.com/research/

**Clone YouTube channel** (video descriptions pulled from the channel RSS feed: https://www.youtube.com/feeds/videos.xml?channel_id=UCd0xLOw6No5IAsq3Y2-b0eA )

- **[VERIFIED] Torso 2 (2024-12-06), verbatim:**
  > "910 muscle fibers animating its 164 degrees of freedom and includes 182 sensors for feedback control … These Torsos use pneumatic actuation with off-the-shelf valves … These are hand-written, hardcoded sequences to pressure control each muscle"

  Source: https://www.youtube.com/watch?v=gl0GnzPIOl4
- **[VERIFIED] Protoclone V1 (2025-02-19):** "over 200 degrees of freedom, over 1,000 Myofibers, and over 200 sensors". Source: https://www.youtube.com/watch?v=H7dhwFcuUn0
- **[VERIFIED] Clone Hand Teleoperation V2 (2024-08-07):** "catching a ball with rules-based joint controller". Source: https://www.youtube.com/watch?v=FowJbzm92NA
- **[VERIFIED] 2023-02-25 demo:** "Oculus Quest 2 headset to estimate the human hand pose, which is then retargeted to the Clone Hand v19". Source: https://www.youtube.com/watch?v=PtRqzMCfqQA
- **[VERIFIED] Latest upload is 2025-11-15**, "Musculoskeletal Clone Hand Joint Controller V2" (empty description). No 2026 uploads appear in the feed. Source: https://www.youtube.com/watch?v=Uo9sKeVNbNs

**Other company statements and early hardware**

- **[SECONDARY] Clone LinkedIn post, about April 2026** (page shows "6 months"): "Torso 3 in the studio, now with joint angle feedback in the hands and in-house valves." Source: https://www.linkedin.com/company/clonerobotics/
  - [ANALYST] This implies the hands of the earlier Torso 3 build had no joint-angle feedback.
- **[SECONDARY] Clone Chief of Staff / research engineer Maciej Bakowicz, interview 2024-12-20:** "control a robot hand using proportional muscle actuation without needing feedback"; "a naive teleoperation system … that allowed for control without feedback". Source: https://hackernoon.com/training-musculoskeletal-androids-with-neural-control-systems-by-maciej-bakowicz
- **[SECONDARY] 2022 hand (V15/beta):**
  - New Atlas, 2022-10-06: "36 electro-hydraulic valves, each with its own pressure sensor. There are also magnetic sensors to feed back information on joint angles and velocities". Source: https://newatlas.com/robotics/clone-robotics-realistic-hand/
  - 80.lv, 2022-09-15: "16 magnetic encoders, which measure the joint angles and velocities, and 35 pressure sensors, one for each muscle/valve"; "36 total muscles for the full 27 degrees of freedom". Source: https://80.lv/articles/anthropomorphic-robotic-hands-with-artificial-hydraulic-muscles
  - [ANALYST] 16 encoders for 27 DoF means not every joint was instrumented in 2022.
- **[SECONDARY] Interesting Engineering, 2024-12-06 (Clone Alpha launch).** Same text as the site: "instantaneous control over the muscles with proprioceptive and visual feedback … 4 depth cameras, 70 inertial sensors … 320 pressure sensors for muscle force feedback". This dates the site wording to Dec 2024, and it is unchanged on 2026-10-27. Source: https://interestingengineering.com/innovation/clone-alpha-humanoid-robot-unveiled-poland
- **[SECONDARY] Clone X post, 2025-11-15** (as reported): 27 DoF, "human-level grip strength and speed". The hand was teleoperated by an operator "wearing a sensor glove", using the Neural Joint V2 controller.
  - https://www.humanoidsdaily.com/news/clone-robotics-demos-startlingly-fast-robotic-hand-touts-neural-controller
  - https://interestingengineering.com/ai-robotics/clone-demos-creepy-humanoid-hand

**Conflicts and press claims**

- **[CONFLICT] "Pressure pads" in the palm.**
  - Interesting Engineering, 2025-11-24: "With 70 inertial sensors tracking angle and speed, the pressure pads in the palm detect how firmly the hand grips an object." Source: https://interestingengineering.com/ai-robotics/clone-demos-creepy-humanoid-hand
  - The Rundown, 2025-12-01: "uses 70 inertial sensors and pressure pads … to track angle, speed, and grip force". Source: https://robotnews.therundown.ai/p/the-creepiest-robot-just-got-hands
  - No first-party source mentions palm pads. Three signs the press merged older specs:
    - Clone's site gives 70 IMUs for the *whole body*.
    - The same IE piece reuses the 2022 "500-watt pump and 36 valves".
    - The site says "only proprioceptive and visual feedback".
  - Treat it as unverified until Clone answers DD P1-2.
- **[CONFLICT] Total sensor count.**
  - YouTube (Feb 2025): "over 200 sensors".
  - Site (Alpha spec): 4 + 70 + 320 = 394.
  - Interesting Engineering (Nov 2025): "500 sensors".
  - [ANALYST] Most likely the site is the Alpha target spec, not the shipped prototype.
- **[SECONDARY] Oct 1, 2026 Torso 3 hand demo.** "Explicitly labeled as teleoperation". The hand was "built in April 2026 … the last of its legacy hand designs". Torso 4 is "scheduled to launch in November" and the redesign prioritises being "easier to simulate and control". Sources:
  - https://www.humanoidsdaily.com/news/clone-torso-3-hand-demo-torso-4-november
  - https://interestingengineering.com/ai-robotics/clone-robotics-demos-5-finger-robot-hand
- **[SECONDARY; content NOT REACHED] Podcast chapter "Removing Early Sensors".** The High Bit podcast (Initialized Capital, host Brett Gibson, guest CEO Dhanush Radhakrishnan, about Dec 2025) has a chapter with that title at 06:29. I could not reach the audio or a transcript. Listing: https://music.amazon.co.uk/podcasts/d75c5457-d42f-4144-842f-86dc01a7cf56/episodes/d5990fe1-a702-4837-ab43-7fb1c852266f/high-bit-clone-musculoskeletal-super-intelligent-androids-%E2%80%94-straight-out-of-sci-fi

**Leads that did not hold up, and gaps**

- **[NOT FOUND] Claimed "no tactile skin" statement.** A search-engine summary said Clone's own page says the hand reaches strong learning results "without high-resolution tactile skin" and plans "visuotactile world models" later.
  - The text is not on clonerobotics.com (full grep, zero hits).
  - Possible origins could not be opened: republic.com/clone (HTTP 403; an earlier Republic campaign was reportedly withdrawn) and aiwiki.ai (HTTP 429).
  - Do not rely on it. It is listed only as a lead for DD P2-6.
- **[NOT FOUND] Patents** (Google Patents query endpoint, 2026-10-27):
  - Inventor "Lukasz Kozlik" or "Koźlik": 0 results.
  - Assignee "Clone Inc", "Clone Incorporated", "Clone Robotics" or "Clone Sp": 0.
  - Inventor Radhakrishnan plus robot terms: no Dhanush.
  - Patents could still be unpublished (under 18 months), filed only in Poland (UPRP, not searched) or held by another entity or the departed co-founder. This ties into the memo's IP risk. Source: https://patents.google.com/
- **[SECONDARY] Jobs.** 3 roles, all in Wrocław and about 6 months old: Embedded Engineer, Software Engineer, Technician for Printing and Molding. No posting text mentions tactile or force sensing. Source: https://www.fastaijobs.com/companies/clone
- **[CLAIMED, partly legible] Delta4 memo software stack.** Reads roughly "whole-body pose controller, muscle force controller, valve pressure regulator(?)". That fits sensing force inside the actuators. Too illegible to rely on (BRIEF.md).

### (b) Three kinds of feedback: what Clone has and lacks

| Kind | Clone has? | Basis | Tag |
|---|---|---|---|
| (i) Internal force sensing (proprioceptive): muscle pressure + length → actuator force | **YES, indirect** | 320 pressure sensors "for muscle-level force feedback". Joint angles from IMUs (body) and magnetic encoders (2022 hand: 16 for 27 DoF); hand joint-angle feedback added about April 2026. No muscle-length sensor is disclosed, so length must be inferred from joint angles and moment arms. https://clonerobotics.com/android/ ; https://80.lv/articles/anthropomorphic-robotic-hands-with-artificial-hydraulic-muscles ; https://www.linkedin.com/company/clonerobotics/ | VERIFIED / SECONDARY |
| (ii) External touch sensing: fingertip pressure arrays, slip, contact location | **NOT DISCLOSED** (first-party says "only proprioceptive and visual") | https://clonerobotics.com/android/ . The only contrary items are the two press "pressure pads" lines (CONFLICT above). | VERIFIED (absence in first-party disclosure) |
| (iii) Vision | **YES**: 4 depth cameras in the skull (Alpha spec). No palm or wrist cameras disclosed; Figure 03 has palm cameras. | https://clonerobotics.com/android/ ; https://www.figure.ai/news/introducing-figure-03 | VERIFIED |

**How accurate can (i) be as a grip-force estimate?**

Published measurements:

- **[VERIFIED] Water-driven McKibben force models carry about 10% absolute error.** Twelve water-driven actuators; absolute error "9.1% for the new model … to 9.9%, 10.0%, and 10.5%" for three existing models (Thomalla & Van de Ven, IEEE T-RO 34(6), 2018, doi:10.1109/TRO.2018.2864780). Source: https://experts.umn.edu/en/publications/modeling-and-implementation-of-the-mckibben-actuator-in-hydraulic/
- **[VERIFIED] Hysteresis comes from braid friction.** Tondu (2012): hysteresis "is essentially due to strand-on-strand friction inside the weave"; friction modelling "is particularly hard". JIMSS, doi:10.1177/1045389X11435435. Source: https://api.crossref.org/works/10.1177/1045389X11435435
- **[VERIFIED] Tendon-sheath friction blocks direct force measurement.**
  - Estimating fingertip force from the proximal end only: "maximum full-scale error of approximately 7%", and only if the sheath shape stays fixed (Phee et al., Robotica 2010, doi:10.1017/S026357470999083X). Source: https://api.crossref.org/works/10.1017/s026357470999083x
  - [SECONDARY numbers] A learned estimator on a tendon-sheath glove reached RMSE <0.44 N and 12.7% mean absolute percentage error in force control (Kang et al., RA-L 2020, doi:10.1109/LRA.2020.2966391). Numbers come from a search snippet; the title was checked on Crossref.
- **[VERIFIED] Motor-side force sensing can work on a stiff, low-friction tendon hand.** DexHand 021 reports "force estimation errors below 0.2 N". Source: https://arxiv.org/abs/2511.03481
- **[VERIFIED] 1X on transmission friction.** "at the 100:1 and 200:1 gear ratios common in the field, friction swallows the contact forces". 1X's answer is near-direct-drive tendons (about 5:1–15:1), so "every joint a sensor", plus a tactile skin. Clone claims back-drivable muscles, a point in its favour. Source: https://www.1x.tech/discover/neos-hands
- **[VERIFIED] Joint torque sensing alone does not locate the contact.** Inferring contact location from internal force measurement ("intrinsic contact sensing") needs full force/torque sensing in the finger and a known surface geometry (Bicchi, Salisbury & Brock, IJRR 12(3), 1993; abstract via Crossref). Per-muscle tension alone gives joint torques, not where the contact is. Source: https://api.crossref.org/works?query.bibliographic=Contact+sensing+from+force+measurements+Bicchi+Salisbury+Brock

In Clone's favour:

- **[VERIFIED] Pressure alone can sense grasp force on soft fluid actuators.** Using only the control-loop pressure signal, Wang & Wang demonstrated "grasping force estimation, contact loss detection, object stiffness identification, and contour measurements" (Soft Robotics 2020, doi:10.1089/soro.2018.0135). Source: https://api.crossref.org/works/10.1089/soro.2018.0135
- **[VERIFIED] A 2026 soft gripper does the same.** Its pressure-sensing ring estimates interaction force with no added sensor. Source: https://arxiv.org/abs/2603.27808
- **[VERIFIED] A built-in torque signal can drive reactive force-aware policies.** RDP used the built-in joint torque sensors of a Flexiv arm as one of its force channels. Source: https://arxiv.org/abs/2503.02881

ANALYST worked estimate (assumptions stated; Clone's real muscle geometry and sensor class are unknown):

- **Pressure resolution is not the bottleneck.** Clone's 1 kgf (9.81 N) per fibre at 100 psi (689.5 kPa) implies about 14 mm² effective area. A 0.25%-of-full-scale sensor on 100 psi (±1.7 kPa) resolves about 0.02 N.
- **The model is the bottleneck.** 10% of a roughly 10 N muscle is about ±1 N (about 100 gf).
- **Opposing muscles make it worse.** Example: flexor 20 N against extensor 15 N gives 5 N net. With ±10% on each, the error is ±2.5 N (root-sum-square) to ±3.5 N (worst case), which is 50–70% of the net force.
- **Sensor placement adds error during motion.** Pressure appears to be read at valve boards "mounted along the vertebrae", so hose losses add error when water is flowing.
- **Net result:** the internal estimate is good enough to know "am I squeezing hard / near saturation". It is roughly 30–100x coarser than fingertip touch at light contact: Figure 03 0.03 N, Sanctuary 0.005 N, Sharpa 0.005 N, Meta Digit 360 0.001 N. It is also blind to where contact is and to the onset of slip.
- **Possible upside, untested.** Water is incompressible, so contact transients should show up quickly in line pressure. No Clone data on this was found.

### (c) Is touch actually necessary for autonomy?

**Human evidence**

- **[VERIFIED] Johansson & Westling 1984.** Grip-to-load ratio adapts to surface friction about 0.1 s after contact. "Experiments with local anaesthesia indicated that this adaptation was dependent on cutaneous afferent input". Slip-triggered corrections arrive in 0.06–0.08 s. Exp Brain Res, doi:10.1007/BF00237997. Source: https://europepmc.org/article/MED/6499981
- **[VERIFIED] Augurelle et al. 2003 — the closest human analogue to Clone.** 10 subjects, 250 g object, index and thumb numbed while forearm muscle sense stayed intact.
  - Object dropped on **36% of trials** after numbing, plus a significant slip on a further 12%. Intact: **never dropped**.
  - 7 of 10 subjects dropped it at least once.
  - Grip-force/load-force correlation fell from 0.71 to 0.48.
  - Grip force sagged during a 20 s hold.

  J Neurophysiol, doi:10.1152/jn.00249.2002. Source: https://europepmc.org/article/MED/12574444
- **[VERIFIED] Monzée et al. 2003.** 20 subjects. "All subjects applied significantly greater grip force after digital anesthesia". "Vision of the grasping hand did not significantly correct the finger misalignment". doi:10.1152/jn.00434.2001. Source: https://europepmc.org/article/MED/12574445
- **[VERIFIED] Nowak et al. 2001.** Only 2 subjects. Grip force rose "substantially" after numbing; anticipatory timing was preserved. doi:10.1046/j.0953-816x.2001.01697.x. Source: https://europepmc.org/article/MED/11556900
- **[VERIFIED] Rothwell et al. 1982.** One man with no touch and no joint sense. Lab force control was fine, but in daily life he was "unable to grasp a pen and write, to fasten his shirt buttons or to hold a cup in one hand". He could not hold a steady contraction without vision beyond 1–2 s. Brain, doi:10.1093/brain/105.3.515. Source: https://europepmc.org/article/MED/6286035
- **[ANALYST] Caveat.** A robot can run a larger grip safety margin and does not tire the way a human does. The human data shows touch matters for *economical* and *secure* grip, not that no grip is possible without it.

**Robots succeeding without touch** (in favour of Clone's approach)

- **[VERIFIED] ACT/ALOHA (2023).** Six fine bimanual tasks, including slotting a battery, at "80-90% success, with only 10 minutes" of demonstrations; no tactile sensors. Source: https://arxiv.org/abs/2304.13705
- **[VERIFIED] pi0 (2024).** Inputs are images, language and "proprioceptive state". Laundry folding and box assembly; the paper never mentions "tactile". Source: https://arxiv.org/abs/2410.24164
- **[VERIFIED] Gemini Robotics (2025).** Specialist models averaged 79% success on six long-horizon dexterous tasks, with 100% on lunch-box packing (ALOHA 2 robot). "Tactile" appears 0 times in the 166k-character report. Source: https://arxiv.org/abs/2503.20020
- **[VERIFIED] OpenAI Dactyl (2018).** "We do not use the touch sensors embedded in the hand and only use joint sensing". Source: https://arxiv.org/abs/1808.00177
- **[VERIFIED] OpenAI Rubik's cube (2019).** Solved 60% of the time at 15 face rotations and 20% at 26. Source: https://arxiv.org/abs/1910.07113
- **[VERIFIED] HORA (2022).** Rotated "dozens of objects" in hand "using only proprioception history". Source: https://arxiv.org/abs/2210.04887
- **[ANALYST] Limits of this evidence.** These are mostly parallel-jaw grippers or rigid objects in labs at 60–100%. None shows the 99%+ reliability that paid deployment needs.

**Robots where touch measurably helps** (against)

- **[VERIFIED] Calandra et al. 2017 (GelSight sensors).** Grasp success on 12 unseen objects: vision+touch **94%**, vision-only **80%**, data-collection baseline 43%. Source: https://arxiv.org/abs/1710.05512
- **[VERIFIED] Calandra et al. 2018.** Vision+touch policies 94–95% against "Vision only … 76%". Mean grasp force also dropped (minimum-force policy 10 N against 20 N). Source: https://arxiv.org/abs/1805.11085
- **[VERIFIED] ViSk (2024), magnetic skin.** "27.5% absolute improvement" over vision-only across card swipe, plug insertion, USB insertion and bookshelf retrieval. Source: https://arxiv.org/abs/2410.17246
- **[VERIFIED] AnySkin (2024).** Detects slip at 92% accuracy on unseen objects. Policies still beat camera-only after the skin is swapped (only 13% drop, against 43% for ReSkin). Source: https://arxiv.org/abs/2409.08276
- **[VERIFIED, table read via arXiv HTML] 3D-ViTac (2024).** Whole-task success, RGB-only against vision+touch, 20 episodes each:

  | Task | RGB only | Vision + touch |
  |---|---|---|
  | Egg steaming | 0.50 | 0.85 |
  | Fruit preparation | 0.45 | 0.80 |
  | Hex key | 0.45 | 0.90 |
  | Sandwich | 0.60 | 0.85 |

  Baseline failures included the egg falling from too little force and grapes damaged by too much. Source: https://arxiv.org/html/2410.24091v2
- **[VERIFIED] Reactive Diffusion Policy (2025).** ">35%" improvement over Diffusion Policy baselines in 3 tasks. Also: "Simply adding tactile signals into observation may NOT improve performance for complex contact-rich tasks". Architecture matters. Source: https://arxiv.org/abs/2503.02881
- **[VERIFIED] ForceVLA (2025).** +23.2% average over pi0 baselines, using a 6-axis wrist force/torque sensor rather than skin. Source: https://arxiv.org/abs/2505.22159
- **[VERIFIED] Meta FAIR and UW (2026), visuo-tactile world model.** "up to 35% higher success rates" zero-shot on real robots against vision-only. Source: https://arxiv.org/abs/2602.06001
- **[VERIFIED] RotateIt (2023).** With joint sense only, performance drops 41% on unseen object shapes; with vision and touch the drop is 15%. Source: https://arxiv.org/abs/2309.09979
- **[VERIFIED] Meta Digit 360 (2024), capability only.** About 8.3M taxels; normal and shear force resolution 1.01 and 1.27 mN; vibration up to 10 kHz. Source: https://arxiv.org/abs/2411.02479
- **[ANALYST] Read-across.** Touch is not a precondition for autonomy on rigid pick, place and fold work. It is a consistent **+14 to +45 pp** gain on fragile, slippery, occluded, insertion and in-hand tasks. Those are the tasks Clone markets: "surgical precision", a drill trigger, scalpel use by late 2026 (https://robotnews.therundown.ai/p/clone-20k-synthetic-human).

### (d) What competitors ship

| Company / hand | Touch sensing (type, resolution) | Date | Source | Tag |
|---|---|---|---|---|
| **Figure 03** | In-house first-gen fingertip tactile, "forces as small as three grams"; "distinguish between a secure grip and an impending slip"; palm camera in each hand | 2025-10-09 | https://www.figure.ai/news/introducing-figure-03 | VERIFIED |
| **1X NEO hands** | 25 DoF (22 in hand + 3 wrist), backdrivable tendons at about 5:1–15:1, "every joint a sensor", PLUS "high-resolution tactile sensing across the fingertips and surfaces": normal force, contact location, shear, slip. No taxel count published. "vision alone is insufficient for many tasks" | 2026-07-09 | https://www.1x.tech/discover/neos-hands | VERIFIED |
| **Boston Dynamics Atlas** | 4 fingers, 13 DoF; "dense pressure tactile sensors that cover the fingertips and palm" (no density number) | 2026-10-01 | https://www.therobotreport.com/boston-dynamics-drops-pinkie-on-new-humanoid-hand/ | SECONDARY |
| **Sanctuary Phoenix** | "seven-cell touch sensor with micro-barometers" per finger pad, "sensitive to 5 millinewtons"; blind picking and slip detection (CLAIMED) | 2025-02-26 | https://www.therobotreport.com/sanctuary-ai-integrates-tactile-sensors-into-phoenix-general-purpose-robots/ ; https://sanctuary.ai/blog/sanctuary-ai-equips-general-purpose-robots | SECONDARY / VERIFIED (claims) |
| **Tesla Optimus** | Gen 2 (Dec 2023): fingertip tactile sensing shown with force readouts. Nov 2024 hand: 22 DoF + 3 in wrist/forearm; Kovac said "extended tactile sensing integration (much more surface coverage…)" was still to finish. Gen 3 fingertip claims (Mar 2026 blog) unverified. | 2023-12 / 2024-11-29 | https://www.notateslaapp.com/news/1821/tesla-unveils-optimus-robot-gen-2-tesla-designed-fingertip-sensors-actuators-and-ten-other-improvements-video ; https://electrek.co/2024/11/29/tesla-unveils-upgraded-optimus-robot-hand-but-impressive-demo-is-again-teleoperated/ | SECONDARY |
| **Sharpa Wave** | 22 active DoF; each fingertip has a miniature camera and ">1,000 tactile pixels"; "0.005 newtons"; in mass production since Oct 2025. CONFLICT: 0.02 N quoted in the NVIDIA reference-design release. | 2025-12-19 | https://interestingengineering.com/ai-robotics/sharpas-advanced-robotic-hand-enters-mass-production | SECONDARY |
| **Unitree Dex5-1P** | 94 force sensors (10 palm, 6 per fingertip, 6 along each finger, 6 at finger roots), 10–2,500 g range. Tactile only on the "P" variant. | 2025-05-28 | https://www.robotics247.com/article/unitree-releases-new-dex5-1-humanoid-robot-hand | SECONDARY |
| **Shadow DEX-EE** (built with Google DeepMind) | Stereo-camera optical fingertips with "hundreds of taxels each"; "Multi-taxel, 3 DOF tactile sensors on middle and proximal phalanges" | page © 2026 | https://shadowrobot.com/DEX-EE | VERIFIED |
| **Apptronik Apollo** | No public hand touch spec. Weak lead: job postings mention modelling "tactile sensor response" | — | searched apptronik + "hand tactile"; https://job-boards.greenhouse.io/apptronik/jobs/5806320004 (not opened) | NOT FOUND |
| **Clone** | None disclosed: "only proprioceptive and visual feedback"; 320 muscle pressure sensors, 70 IMUs, 4 depth cameras | Dec 2024 → live 2026-10-27 | https://clonerobotics.com/android/ | VERIFIED |

[ANALYST] Since Feb 2025, four leading North American humanoid makers (Sanctuary, Figure, 1X, Boston Dynamics) have added or announced fingertip and palm touch. Clone's "proprioceptive + visual only" stance is now the outlier. It is not the industry default.

### (e) Verdict for the LP

**Partly true.**

- **What is right:** as far as anything public shows, Clone's hand has **no touch sensing**. That means no fingertip or palm pressure arrays, no contact-location sensing and no slip sensing. Clone's own site, live today, describes control "with only proprioceptive and visual feedback".
- **What is wrong:** it is not true that the system cannot sense how hard it grips. Each artificial muscle has a pressure sensor ("320 pressure sensors for muscle-level force feedback"). Pressure plus joint angle gives an **indirect estimate of muscle force**, the same principle 1X uses in its "every joint a sensor" motors.
- **How good that estimate is:** published hydraulic McKibben models are about 10% off. Braid hysteresis, tendon friction and opposing muscles pulling at once widen the error further. Our estimate is about ±1 N per finger. That is good enough for firm grips and about 30–100x coarser than rivals' fingertip touch at light contact. It also cannot tell where the contact is or when slip starts.
- **Is touch necessary?** Vision-plus-joint-sense policies already reach 80–100% on many lab tasks, so it is not strictly needed. But it measurably helps (+14 to +45 pp) on fragile, slippery, occluded and insertion work, which is where Clone pitches its hand. Humans with numbed fingertips drop objects on 36% of trials against 0% intact.
- **What Clone would need:** a fingertip and palm skin. Options exist (magnetic skins like AnySkin, barometric cells like Sanctuary's, resistive arrays like Unitree's). On a water-hydraulic hand with soft "fat and skin", 27 DoF and tendons it is moderately hard rather than impossible. The work is:
  - sealing electronics next to water;
  - keeping sensitivity through the soft layers (Tesla named this exact trade-off);
  - routing wires through ligament-jointed fingers;
  - wear and replacement;
  - re-collecting teleop data with touch (and ideally haptic feedback to the operator), then retraining Cybernet.

  Expect a hardware revision plus a data cycle, months not weeks. That cost is not reflected in the low-cost-hand pitch.
- **What decides it:** a measured grip-force accuracy number and an autonomous fragile-object demo from Clone.

---

## 3. What I could not reach

- **X / Twitter (HTTP 402).** Clone's 2025–2026 posts are seen only through press. The Oct 2026 Torso 3 posts and any Torso 4 sensor statements are unread.
- **republic.com/clone (HTTP 403, bot check).** A curl retry was blocked by the harness, and I did not try to get around it. This was the possible source of the "no high-res tactile skin / visuotactile world models" claim.
- **aiwiki.ai (HTTP 429)** and the Web Archive (blocked), so earlier versions of the Clone site could not be diffed.
- **Clone's YouTube interviews:** Anastasi In Tech (2025-09-12) and High Bit, "Removing Early Sensors" at 06:29. No transcript was available.
- **Clone's careers listing text.** The site loads it dynamically; only the aggregator was read.
- **Patent offices:** the Polish office (UPRP), EPO and WIPO were not searched; only Google Patents.
- **Primary pages:** Tesla's own Optimus pages, an Apptronik hand spec, and Torso 4 specs (launch due Nov 2026, not yet out).
- **PubMed** was blocked by a bot check; Europe PMC abstracts (same PMIDs) were used instead.
- **Prompt-injection log:** none detected in any fetched content.

---

## 4. Ranked DD questions for Clone

All status: **not yet asked**. The 60-day expiry clock starts on first send.

| # | Pri | Question | What it moves |
|---|---|---|---|
| 1 | P1 | Per-hand sensor sheet for Torso 4 and the shipping hand: pressure sensors per muscle (count, placement in-muscle or at the valve, range, accuracy, sample rate), joint encoders per DoF (how many of 27), and **any touch sensing**. | Crux verdict (partly true → true/false); "hand leads" thesis; hand BOM |
| 2 | P1 | Are the "pressure pads in the palm" reported by Interesting Engineering and The Rundown (Nov–Dec 2025) real? If so: count, location, sensitivity. If not, will Clone correct the record? | Resolves the CONFLICT; disclosure quality |
| 3 | P1 | Is fingertip or palm touch on the Torso 4 or Alpha BOM or roadmap? Technology, taxels, sensitivity, cost per hand, date. If not, Clone's evidence that pressure + vision is enough. | Competitive position vs Figure / 1X / Atlas; BOM and timeline |
| 4 | P1 | A live **autonomous** (not teleoperated) demo, on the Delta4 Torso 4 Zoom: egg, paper cup, grape, plug insertion and a slip recovery, with success rates over ≥20 trials each. | Whether pressure + vision works in practice; pilot readiness |
| 5 | P1 | Measured grip-force accuracy: muscle-pressure-based fingertip force against a load cell (N and % of full scale), hysteresis loop, smallest detectable contact force, latency. | Quantifies the crux directly; replaces our ANALYST ±1 N |
| 6 | P2 | What did "Removing Early Sensors" (High Bit podcast) refer to? Which sensors were removed and why (cost, durability, wiring near water)? Did Clone say the hand learns well "without high-resolution tactile skin"? | Roadmap credibility; reversibility of the sensing choice |
| 7 | P2 | Training data: does the teleop operator get force or haptic feedback? Are the pressure channels logged and fed into Cybernet? | Whether policies can learn force-aware behaviour |
| 8 | P2 | Pilot task specs (e.g. AST SpaceMobile soldering; logistics pick-and-pack): do they require light-contact or slip handling, and what success rate does the customer require? | Go-to-market fit of a hand without touch |
| 9 | P2 | Patents covering muscles, valves, sensing or force control: numbers, assignee, inventors (including the departed co-founder), jurisdictions. Google Patents returned 0. | IP risk (with the memo's IP-assignment item) |
| 10 | P2 | Sealing and durability of electronics next to the water system. How would a touch skin integrate with the "fat and skin" layers, and at what extra cost per hand? | Feasibility and cost of closing the gap |
| 11 | P3 | Reconcile sensor counts: "over 200" (YouTube, Feb 2025) vs 394 (site) vs "500" (press). | Disclosure hygiene |
| 12 | P3 | Reconcile hand DoF: 26 "in the hand, wrist, and elbow" (site) vs 27 in the hand (press and 2022). | Spec consistency |
| 13 | P3 | Do the 70 IMUs cover every finger joint, or only major segments? Encoder coverage per DoF in the 2026 hand. | Completeness of internal sensing |
