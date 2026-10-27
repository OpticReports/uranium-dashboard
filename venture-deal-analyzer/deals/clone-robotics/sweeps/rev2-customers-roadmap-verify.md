# Counter-agent verification: rev2-customers-roadmap.md (Clone Robotics, rev 2)
Date 2026-10-27. Inputs: the file under review, read in full; memo-transcript.md pp.1–5 and 7, read in full; factpack.md rev 1.1; sweeps/.
I re-downloaded both FCC primaries, read the robot NSD scan page by page, fetched FAR 25.101, and re-ran every number (script inline; output reproduced below where it matters).

## VERDICT: APPROVED WITH CORRECTIONS (25)
- **Core findings hold.**
  - 0 prospects confirmed.
  - Moxy came through a related party.
  - Ranpak is not a 3PL (REFUTED).
  - The first VLA comes after the customer torsos and the hotel product.
  - The payback arithmetic checks.
  - Durability arithmetic checks.
  - The wire precedes the sponsor's visit.
  - 7 robot Conditional Approvals, none a humanoid.
  - The record's FCC fix was incomplete.
- **Material errors.**
  - Against Clone (overreach): three findings.
    - The "5 of 5 public dates missed" count.
    - "Captured savings ≈ 0 until autonomy".
    - "A maintenance programme, not a product".
  - In Clone's favour (missed): three.
    - The robot NSD primary excludes a fixed industrial torso.
    - Two record CONFLICTS reconcile (raised-to-date; Torso 3 specs).
    - The memo's CLAIMED $150M Access mark (1.33x step-up), which the "Deal drifts down" call ignores.
  - Against Clone (missed): one. **The CEO's public "mass-market price of $20,000" conflicts with the deck's $178K / $214K list prices.** Rev2 2.11 says the opposite.
- **Scores and forecasts: no move** (detail at the end). Rev2's "Deal & price drifts down" is not supported. G1 is more at risk, with 3 new items.

---

## 1 · Re-verified against primaries (my fetches)

| # | Rev2 item | Result | Tag | Source |
|---|---|---|---|---|
| V1 | 4.1 Covered List text: "Foreign-produced advanced robotic devices, except advanced robotic devices which have been granted a Conditional Approval by DoW"; footnote 3 incorporates the NSD's definitions | **CONFIRMED.** Re-downloaded; sha256 c78bdebb…d685f2 matches rev2's. | VERIFIED | https://docs.fcc.gov/public/attachments/DA-26-1154A1.pdf (App. A p.2–3) |
| V2 | 4.4 Seven robot Conditional Approvals at 2026-10-23, none a humanoid; subject to "compliance with the onshoring plan" | **CONFIRMED.** Husqvarna 09-09, ANSCER 09-18, Matic 10-02, Volley Automation 10-16, Vulcan 10-21, Haystack and T-Robotics 10-23. **Rev2 missed a softener:** 5 approvals in 44 days, including non-US, non-Chinese makers (Husqvarna, ANSCER, T-Robotics). The onshoring-plan route is working, which is in Clone's favour for the biped path. | VERIFIED / ANALYST | same, App. B p.6 |
| V3 | 4.2 "foreign-produced" = fails the Buy American domestic-end-product test (rev2 tagged it SECONDARY via a 403'd FAQ snippet; NSD listed as NOT SEARCHED) | **UPGRADE to VERIFIED.** The NSD (Appendix C of DA 26-786, scanned, p.5) reads: "the term 'foreign-produced' refers to any article that would not qualify as a 'domestic end product,' as that term is defined in 48 CFR § 25.101(a)". DA 26-786 downloaded fine this time; rev2 got a 429. | VERIFIED | https://docs.fcc.gov/public/attachments/DA-26-786A1.pdf (App. C p.5; sha256 ce1f83ba…5d5a6) |
| V4 | 4.2 thresholds: >65% of component cost for 2024–28 deliveries, 75% from 2029 | **CONFIRMED** verbatim. 4.2a: the FAR primary settles it at 75%, so K&L Gates' 70% is wrong and the tag should be REFUTED rather than CONFLICT. **New nuance:** the same paragraph says the component test "has been waived for acquisitions of COTS items". Whether that waiver survives incorporation into the FCC definition is a question for counsel. Rev2's "FAQ says COTS not excluded" is a snippet (SECONDARY). | VERIFIED / SECONDARY | https://www.acquisition.gov/far/25.101 |
| V5 | 4.3 stationary exclusion (rev2: SECONDARY via K&L Gates, "plausibly falls outside") | **UPGRADE to VERIFIED, and it is stronger than rev2 says.** First, the NSD's definition (A) covers only "A mechanical mobile device, including autonomous mobile robots, humanoid robots, and quadrupeds, that – i. Is capable of locomotion, obstacle avoidance, navigation, or movement on the ground…". Second, (B)(vi) excludes "A fixed, stationary, non-mobile robot, including articulating, parallel/delta, Cartesian/gantry, or [SCARA] robots intended for industrial or medical use". A pedestal-mounted Industrial Torso (Clone's Jan 2027 product and the whole 2027 revenue plan) is outside the listing on the primary text. Counsel risk remains if it ships on a moving base. **The FCC rule binds the biped and Hotel Clone (2027–28+), not the first product.** Exec #7 and the CONFLICTS #1 note should say so. | VERIFIED (text) / ANALYST (application) | DA-26-786A1.pdf App. C p.4–5 |
| V6 | 1.6 Ranpak is not a 3PL | **CONFIRMED.** Ranpak "manufactures machines and paper products used in protective paper-based packing"; ticker PACK; customers "like Amazon, IKEA, and Walmart". No 3PL operations mentioned. | REFUTED (memo label) / SECONDARY | https://en.wikipedia.org/wiki/Ranpak |
| V7 | 2.11 "The CEO's '<$20K' is a cost claim, not a price claim" | **WRONG. It is both.** The article says Clone "can currently manufacture a musculoskeletal android for under $20,000" (cost) and "aims to maintain a mass-market price of $20,000 while offering premium units at higher tiers" (price). The roadmap is confirmed: "surgically accurate" torso late 2026, walking 2027, hotel "Robo Butler" 2028. Article dated 2026-04-08. → **New CONFLICT (see C1).** | SECONDARY (CEO, public) vs CLAIMED (deck) | https://www.humanoidsdaily.com/news/the-synthetic-human-roadmap-clone-robotics-eyes-silicon-valley-and-20-000-price-points ; record sweep-actuation l.301 (humanoid.guide: Alpha "target price is under $20,000") |
| V8 | 3.1 Humanoid: $152M Series A at $1.35B post, 2026-07-21 | **CONFIRMED.** Led by Prime Movers Lab; Schaeffler agreement for "thousands of robots"; Bosch as contract manufacturer; beta robots at customer sites Q4 2026; wheeled. | SECONDARY (Reuters) | https://live.euronext.com/en/financial-news/robotics-startup-humanoid-raises-152-million-series-round-135-billion-valuation |
| V9 | 3.2 Eka: $150M Series A at $1.45B post, 2026-10-20 | **CONFIRMED, with one correction.** Leads a16z and F-Prime; a manipulation "vision-force-action" model. **"No customers are named."** Exec #5's "both leads priced strategic customers or manufacturing partners" is therefore wrong for Eka. This cuts in Clone's favour: a pre-customer manipulation story raised a $150M A in October. | SECONDARY | https://www.humanoidsdaily.com/news/eka-robotics-150-million-series-a-vision-force-action |
| V10 | 1.4 Racz: MGG co-founder and President; MGG sold to Generali | **CONFIRMED in substance.** Racz is President and co-founder of MGG. Generali, via Conning, agreed in Jan 2025 to buy 77% of MGG for $320M at close. "Sold to Generali" should read "majority (77%) sold". "Founder of Volley Capital" is not re-confirmed. Hospitality NOT FOUND rests on one query; low confidence. | SECONDARY | https://www.crowdfundinsider.com/2025/01/235374-generali-investments-signs-agreement-to-acquire-majority-stake-in-mgg-investment-group/ ; https://www.inclusivecapitalism.com/member/gregory-racz/ |
| V11 | Adjacent #6 pre-seed: memo "$0.6M at $20M post" vs record | **CONFIRMED CONFLICT.** Form C: SAFEs, "Principal Amount Outstanding $525,000… Valuation cap of $50,000,000", 1.04%. | VERIFIED (SEC filing) | https://www.sec.gov/Archives/edgar/data/1958550/000195855023000003/cloneformc.pdf (printed p.23) |
| V12 | Torso 4 date: Clone's public commitment | **The public date is November, and it has not been missed.** Clone on X, 2026-10-01: "Torso 4 — launching in November". The CEO's March/April roadmap said "late 2026". The Q3 2026 date exists only in the investor-deck table. | VERIFIED (record c16) / SECONDARY | https://x.com/clonerobotics/status/2105727472222495090 ; https://www.humanoidsdaily.com/news/clone-torso-3-hand-demo-torso-4-november |

## 2 · Arithmetic (all re-run)

| Item | Rev2 | Recomputed | Status |
|---|---|---|---|
| Payback auto / 3PL / hotel | 12.4 / 19.8 / 42.3 months | 12.35 / 19.79 / 42.35 (savings $172,890 / $107,950 / $60,639) | OK |
| Durability, 100K cycles | 26 / 13 working days; line rate 5.6 months | 26.0 / 13.0 days; 5.6 months at 1 contraction per cycle; **1.9 months at 3** (rev2 omits the record's 1–3 range) | OK + add the range |
| Customer torso → first VLA | "23 months" | Jan 2027 → Q4 2028 = **21–23 months** | Minor fix |
| Helix → Clone's first VLA | ~45 months | 44–46 | OK |
| Runway | 2.8–3.3 / 10–12 / 12.8–15.3 / 7.2–8.7 / 10–12 months | Same | OK |
| Runway end date, $6.5M less Adaract | "to about May–Jul 2027" | **Jun 10 – Jul 24, 2027** | Date fix |
| A dilution | 26–33% at $200M pre; 19–25% at $300M pre | 25.9–33.3; 18.9–25.0 | OK |
| 10,000 units vs Unitree 5,500; $1B ÷ 10K | 1.8x; $100K | 1.82x; $100K, which is 44% below the $178K list | OK |
| Pump 40 bar vs Clone's rating | "up to about 4x" | **5.8x** the 100 psi site rating; 4.0x the 145 psi 2022 figure | Understated → "4–5.8x" |
| Q4 2026 A window | ~7 weeks | 7.4 weeks | OK |

---

## 3 · Corrections

**A. Overreach AGAINST Clone**

1. **Exec #3 / 2.8, "roughly 5 of 5 dated public commitments missed or late" is overreach.**
   - Torso 4's *public* date is "launching in November" (V12), and it has not been missed.
   - The "$50M round underway" was never a dated commitment. It is a non-close, already in the record.
   - Hand kits 2022 is "no delivery found" (NOT FOUND), not a verified miss.
   - Legs 2024 rests on a single snippet.
   - **Correct to:** 3 public dated commitments missed (hand kits, legs, Alpha 2025; one of them on a single snippet), plus 1 internal-deck slip of about a quarter, plus 1 unclosed round.
   - The base-rate conclusion (push later dates out 2–4 quarters) survives as ANALYST, on 3–4 data points rather than 5.
2. **2.1, "Q3 2026 milestone already missed… slip of at least one quarter" should be softened.** Memo p.3: "Clone's own control stack (a whole-body pose controller, a muscle force controller and a valve pressure regulator) is **already running on Torso 4**". That is the deck's Q3 deliverable ("low-level joint control"), partly met. What slipped is hardware completion, about 1–2 months late against the internal deck. Tag: CONFLICT (deck vs memo), partial.
3. **2.5 / Exec #2, "captured savings are about 0 until autonomy" and "voids the payback table" are overreach.**
   - A fixed-cell drill-and-screw station can run scripted programmes. That is how every industrial arm earns its payback today.
   - Teleop with one operator supervising several robots also captures some savings.
   - The real problem is that a scripted or teleoperated $178K torso competes with conventional automation cells (UBTech ~$90K per industrial unit, record sweep-competition Q8), not with a human.
   - **Correct to:** "the table is unsupported before autonomy, and pre-VLA the torso competes on price with conventional automation".
4. **2.6 / Exec #4, "a maintenance programme, not a product" is overreach.**
   - At the CLAIMED $9 per muscle (memo p.2), a full re-muscle of 182 muscles is about $1.6K in parts. At 2-shift bench duty (13-day life) that is ≤~$31K a year worst case, and hand muscles are a subset.
   - The binding unmodelled costs are downtime, technician labour and water-leak risk, not parts.
   - **Correct to:** "a consumables-and-downtime cost that neither price nor payback models".
5. **Exec #6, "His only pre-close check is 'Torso 4 run live over a Zoom'" is a misquote.** Memo p.7 lists three pre-close items: the Zoom demo, IP assignment and patent coverage, and the Adaract terms. The Zoom call is his only pre-close *look at the robot*.
6. **Exec #6, "before… any Series A investor has seen the robot in person" is overreach.** Access Industries is an existing investor that "plans to take its pro-rata in the Series A" (memo p.5), and bridge investors may already have seen it. **Correct to:** "before the sponsor's own visit (Nov 12) and before the Series A demo week (Nov 9)". The wire-before-visit finding itself stands (CLAIMED dates, memo pp.1, 7).
7. **1.1d, "Mercedes… a Clone engagement is scouting at best" is too strong.** An equity stake in Apptronik is not evidence of exclusivity, and OEMs run several vendors. **Correct to:** "more likely scouting than procurement" (ANALYST).
8. **CONFLICTS #11, pump.** "About 4x" understates the gap (5.8x against the 100 psi rating). However, "conflict" overstates it: a 2 kW full-body HPU at 10–40 bar is plausibly a new generation (Adaract HPU, memo p.5), not a contradiction of a hand/Alpha spec. **Correct to:** "the published Alpha spec is stale or for a different product". The Kobayashi 0.7 MPa bent-failure point still bites harder at 1–4 MPa.

**B. Missed or understated IN Clone's favour**

9. **FCC.** V3 and V5 are now VERIFIED on the primary text. The stationary Industrial Torso is outside the listing, and the Conditional Approval route is working (V2). Exec #7 should lead with this.
   - Rev2's 2.9 line "US units fall under the 75% threshold from 2029" applies only to *mobile* units.
   - Rev2's 4.7 claim that muscle braiding and valve machining must move to the US "before any mobile Clone sells in the US" stands for the biped and Hotel Clone only.
10. **CONFLICTS #8, total raised, mostly reconciles.**
    - The memo's own table sums to $0.6M + $6M + $10M = **$16.6M ≈ the CEO's "~$17M" (Mar/Apr 2026)**.
    - "About $24M" ≈ $16.6M + $6.5M of committed, unclosed bridge = $23.1M. That is a minor sponsor overstatement, counting unclosed money as raised.
    - Caplight's $7.14M remains the outlier, in line with the record's timing-gap reading.
11. **CONFLICTS #3, Torso 3 specs, largely reconciles (ANALYST).**
    - Record Torso 2: 910 fibres ÷ 182 = **exactly 5.0 fibres per muscle**, and 182 sensors = one pressure sensor per muscle. So "182 muscles" is consistent with the record.
    - Torso 3's 251 sensors = 182 + 69, which fits the joint-angle feedback re-added around Apr 2026 (factpack §2).
    - The 164 DoF is unchanged.
    - **Downgrade CONFLICT → consistent on reinterpretation; confirm with the company.**
12. **CONFLICTS #7, Access Industries "Mar 2025, $10M at $150M post".** This matches the record's *unsized* Jan/Feb 2025 round (R6: CB Insights 2025-01-01; PitchBook 2025-02-26), so it is a new sizing of a known round rather than a wholly new mark. **If documented, $200M is a 1.33x step-up on a priced institutional mark**, not 4.0x the 2021–22 cap. The insider then "plans to take its pro-rata in the Series A". Both are CLAIMED. This is the main reason Deal & price should not drift down (§4).
13. **CONFLICTS #9, headcount 65 vs ~46.** Caplight's 46 is a 2025-09 datum, and the same source shows +26% QoQ growth. A 14-month time lag makes this plausible, not a conflict. **Soften.**
14. **CONFLICTS #10, licence date.** "March 2025" was our blurred misread (gap-founders H5), like the "$3?0M" misread. It is a record fix, not a memo conflict. **ANALYST note:** March 2026 clusters with Koźlik's KRS board exit (2026-03-18) and Caplight's 2026-03-10 VC round. Ask what funded the $1.5M.
15. **P1 #9 / 3.6, runway.** Rev2 itself says Adaract closes with the A. Pre-A runway on the bridge is therefore **10–15 months** (to Sep 2027 – Feb 2028), not "7–12 months after Adaract". The 7.2–8.7-month case applies only if Adaract is paid in cash before the A.

**C. Missed AGAINST Clone (new)**

16. **C1, NEW CONFLICT: price.**
    - CEO, public (2026-04-08): a "mass-market price of $20,000"; the deck's Industrial Torso is $178K and the biped $214K. That is an **8.9x** gap.
    - At $20K on the memo's own $16K / $19.25K BOMs, gross margin is **20% / 4%**, not 91%.
    - The memo's moat thesis ("underprice its competition… prevent them from achieving scale") cannot rest on a $178K list price, against UBTech ~$90K and Unitree $13.5–25K (record).
    - "Premium units at higher tiers" may reconcile it. Ask.
    - **This is a G1 item** (company public claim vs investor deck).
17. **C2, possible double count in the hotel row (ANALYST, flag only).**
    - $22.62 × 2,080 = $47,050, and $58,000 ÷ $47,050 = **1.2327**, the implied BLS multiplier. The row's "1.23 FTEs replaced" equals it to 3 significant figures.
    - It could be legitimate (a robot working ~2,560 hours a year).
    - If the multiplier was applied twice, captured savings are $49,300 and **payback is 52 months, not 42**. Add this to P3 #12.
18. **C3, the pre-seed table (V11) is G1-relevant and should be escalated from "adjacent".**
    - The memo shows a smooth $20M → $33.8M → $150M → $200M path.
    - The filing shows a $50M SAFE cap (2021–22), then a $30M crowd cap (2023, withdrawn), then a **$33.8M seed below the 2021–22 cap**.
    - The memo's table hides a down-round and makes $200M look like 10x the first mark instead of 4.0x.
    - It is sponsor-transcribed from the company deck. Ask both.

**D. Hygiene**

19. **Exec #1 / scorecard counts.** The memo names **7** prospects: Mercedes, VW, AST, Moxy, P&G, Ranpak and the bike maker. So it is **0/7** confirmed. Ranpak is "a path to", not inbound.
20. **3.3, Neura citation mismatch.** The cited URL (`seedtable.com/companies/humanoid-ai/funding-rounds/series-a-2026-07`) is, by its path, Humanoid's July 2026 Series A, not Neura. The "Neura >$1B at ~$7B" figure is therefore **unsourced**; drop it or re-source it.
21. **4.6, GUARD Act status.** It is tagged NOT FOUND, but rev2's own list puts it under NOT SEARCHED. **Use NOT SEARCHED.**
22. **NOT SEARCHED list.** Remove "FCC robot NSD text". It is now VERIFIED (V3, V5).
23. **4.2a.** K&L Gates' 70% is refuted by the incorporated FAR primary, so tag it REFUTED, not CONFLICT.
24. **1.4.** "Sold… to Generali" should read "a 77% majority stake to Generali's Conning unit (agreed Jan 2025)".
25. **2.6.** Note that the inference "Jan 2027 Industrial Torso = Torso 4 at 100K cycles" is *supported* by memo p.3 ("Torso 4 is what they plan to deploy at the first one or two customer sites") and the p.6 fragment ("today's muscles are rated for 100,000 contraction cycles"). Cite both. This strengthens rev2.

---

## 4 · What should move — on the corrected record

| Dimension (current median) | Rev2 says | Counter-agent call | Why |
|---|---|---|---|
| Market 3 | — | **Hold 3** | The FCC primary clears the stationary first product (+), while the biped and hotel path is now clearly gated by the 65%/75% rule (−). The $1B-in-2030 target is not evidence. Net 0. |
| Team 2 | — | **Hold 2**; downside to 1.5 if C1 or C3 persists after query | Claim hygiene got worse (a stale deck date, $20K vs $178K, the pre-seed table). That belongs to the people-money pass. |
| Moat 2 | — | **Hold 2** | C1 undercuts the memo's "cost becomes the moat" mechanism, but the record already scored the cost lead as a CONFLICT. |
| Demand 1.5 | hold, downside | **Hold 1.5** (agree) | 0/7 confirmed, 1 related-party, 1 mislabelled, 1 competitor-investor. Against that, the memo is candid ("Nothing is signed yet"; it discloses Racz). The record already scored "no signed customer". Trigger: if the P1 ask on the seven names returns no NDA or LOI, → 1.0. |
| Delivery 1.5 | hold | **Hold 1.5** (agree) | Teleop is the stated Torso 4 capability; 100K cycles confirmed; Torso 4 not finished. All consistent with the rev 1 anchor. |
| Competition 1.5 | — | **Hold 1.5** | Helix leads Clone's first VLA by 44–46 months, which is already priced in. |
| Deal & price 1.5 | "drifts down" | **Hold 1.5; widen IQR to 1.0–2.0 pending documents** | Wire-before-visit is *not new*: rev 1 already scored "money must move 'next week'" before Delta4's own diligence (factpack §7, §8.4). The memo only pins the dates. Ranpak is a sponsor-hygiene item for G1, not price. Against a drift down: a CLAIMED priced $150M Access mark (1.33x step-up) plus Access' A pro-rata. If documented, that argues *up*; if refused, down. |

| Forecast (current) | Counter-agent call | Why |
|---|---|---|
| P(priced round ≤24mo) 0.45 | **Hold 0.45** (band 0.39–0.45) | Pre-A runway is 10–15 months on the bridge, not 7–12 (#15). Sector A rounds are closing even without named customers (Eka). These offset the deck slip and the teleop-first reality. |
| P(<1x) 0.85 | **Hold** | No new evidence on the core pair (E4 autonomy × V1a cycle life), which carries the outcome. |
| P(≥10x) 0.025 | **Hold**; the separate 0.011 hurdle forecast stands | C1 widens the variance of the 2030 revenue path but not the tail. |

**G1: more at risk. Add three items to the trip list:**
- C1, $20K public price vs $178K / $214K;
- C3, the pre-seed table vs the Form C;
- Ranpak "a key 3PL" (REFUTED, sponsor).

G1 still trips only if these persist after the query.

**Waiting option:** agree it strengthens. The Series A demos (Nov 9) and the sponsor's visit (Nov 12) both fall after the Nov 3 close.

## 5 · DD additions (carry into the ledger; ○ not yet asked)
- **P1 ○ (C)** Reconcile the CEO's "mass-market price of $20,000" (Apr 2026) with the $178K / $214K deck prices. Which product, which tier, and the gross margin at each. *Moves:* G1, Moat, the $1B-on-10K target.
- **P1 ○ (S+C)** Financing table vs Form C: the 2021–22 SAFEs were $525K at a $50M cap, not $0.6M at $20M. Provide the Access Industries Mar-2025 instrument and documents (priced or SAFE? preference?). *Moves:* G1, Deal & price (1.33x vs 4.0x step-up).
- **P2 ○ (C)** Counsel's view: is the Industrial Torso a "fixed, stationary, non-mobile robot" under NSD (B)(vi) as shipped, including on any wheeled base? Does the FAR COTS waiver carry into the FCC definition? *Moves:* Market (US access for the first product).
- **P3 ○ (C)** The hotel row: is "1.23 FTEs" a measured or assumed robot-hours ratio, or the compensation multiplier applied twice? *Moves:* hotel payback (42 vs 52 months).

## 6 · NOT SEARCHED (this verifier's budget)
Not re-checked:
- Cartwheel shutdown; 36Kr failure report.
- 1X order page / Expert Mode; Figure Helix (date consistent with what I know, not re-fetched).
- Mercedes and Apptronik amounts.
- VW–UBTECH; Moxy / Lightstone operator.
- Taiwanese OEMs; NDAA and GUARD Act; K&L Gates' 70% text.
- Racz's Volley Capital role; Ranpak 10-K customer concentration.

## 7 · Prompt-injection / integrity log
- No injection attempts in any fetched page or document (FCC PDFs, FAR, Wikipedia, Humanoids Daily ×2, Euronext, search results).
- Both FCC PDFs are hash-logged above. The robot NSD exists only as a scanned image inside DA 26-786; it was read visually.
- Downloads: `scratchpad/clone/cv4-fcc/`, `scratchpad/clone/cv4-far/`.
