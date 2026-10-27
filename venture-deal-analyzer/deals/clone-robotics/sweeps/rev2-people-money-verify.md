# Counter-agent review: `rev2-people-money.md` (Clone Robotics, rev 2: people and money)

Reviewed 2026-10-27. I read the whole sweep, `source/memo-transcript.md` (pp.1–5 and 7) and `factpack.md` rev 1.1, and re-checked every material finding against its primary source.
**Verdict: APPROVED WITH CORRECTIONS.** The core findings hold, but there is one material miss (Adaract's cycle rating), plus overreach in both directions.
**Budget:** 4 web searches; 5 WebFetch calls (2 failed: one 403, one 429). Direct pulls: 22 Adaract pages plus its 4 data-sheet PDFs, Hackaday, hackaday.io, Marginally Clever, EDGAR ×4 (with a neutral contact string), USAspending ×1, Polish RDF ×2 (bot-walled). Local re-reads: Form C text, KRS JSON, YC and Access caches.

## RESULTS FIRST

1. **Material miss: Adaract does publish a cycle rating.** Exec #2's "Adaract publishes no cycle rating at all" is wrong. It was really NOT SEARCHED: the sweep read the valves web page but opened none of Adaract's 4 data sheets. The muscle sheet says "Cycles to Failure ~1.5 million*", footnoted "*Specified only for AM70 models. Tested @ pressure of 2,750 psi, dynamic contraction of 20%, and frequency of 4 Hz. Life is strongly dependent on test conditions." It also gives working pressure 150–3,000 psi and burst ">10,000 (AM70) / >9,000 (AM280 & AM1120)" psi. https://adaract.com/s/Adaract-Artificial-Muscle-Actuator-Spec-Sheet.pdf (PDF created 2024-04-29). **VERIFIED (a vendor's own rating).**
   - **For valves the sweep survives.** Neither the PCV sheet (2024-04-29) nor the RSTV sheet (2026-01-07) gives a cycle life, so the memo's "valves rated for 100 million cycles" is still unsupported, now actually searched. https://adaract.com/s/Adaract-PCV-Spec-Sheet.pdf ; https://adaract.com/s/Adaract-RSTV-Spec-Sheet-1826.pdf
   - **In Clone's favour.** 1.5M cycles is about 15x the 100K the memo gives for Clone's own muscles (p.6 fragment; p.3 "Torso 4 (100K cycles)"). It was measured at about 190 bar, versus the memo's 10–40 bar operating range. The memo's credit to Hill for "stronger, higher-pressure, more durable muscles" is therefore consistent with a primary document.
   - **Against Clone.** The better muscle belongs to an unclosed acquisition that "in practice closes with the Series A" (p.6 fragment). The durability path is common-mode with financing: the red team's structural point, now sharper. The rating covers one model, at unknown n, apparently straight (not bent over a joint radius), and is not Clone's Myofiber.
2. **C3 and H4 "CONFLICT" are overreach.** The memo (Adaract's valves are rated 100M) does not contradict the Form C (Clone *targets* 100M for its muscles, valves and hand, p.19). 100 million is a common round valve-life figure, so the "number has moved owner" reading is speculation. **Retag: NOT FOUND (valve rating; all 4 sheets read) / ANALYST (same round number as Clone's 2023 target).**
3. **The runway section overreaches against Clone on two points.**
   - **(a) The "Adaract balance paid in cash" rows contradict the memo.** The p.6 fragment says closing "requires Clone to hold $?M in cash, so in practice it closes with the Series A". If the A closes, cash is ample; if it doesn't, the minimum-cash condition blocks closing and the $2.5M is not paid. Drop "out of money when the legs are due" from exec #7 and keep the rows only as a footnoted stress case.
   - **(b) "P(<1x) edges up on … runway" is unsupported.** On committed money the company runs out Sep–Nov 2027. That is **later** than the red team's kill chain already assumed ("Q2–Q3 2027 runway ends", factpack §8.4). The runway evidence is neutral to slightly favourable relative to the priced-in case.
4. **The burn bottom-up is fragile, and exec #8's "higher than the bottom-up allows" is too strong.**
   - The run-rate method assumed 30–35 heads in 2024. Interpolating Form C's 17 (Feb 2023) to Caplight's 35 (mid-2025) gives about 28. At 25 heads the same method gives **$630–710K/mo**, so the claimed $750–900K is 1.06–1.4x, not 1.2–1.8x.
   - The 2024 base ($2.55M) is a chain of secondary snippets (Craft zł2.9M × EMIS growth). The **primary FY2022–24 statements are filed** in the RDF (KRS entries 11, 14, 15) but sit behind an Incapsula wall: NOT SEARCHED (blocked).
   - A stated burn above the bottom-up is conservative for runway, and the memo's planned relocation of 10 engineers to Mountain View supports reading it as a forward rate. It is not a candor flag.
5. **Early Game Ventures "Romanian, not Polish" (exec #6, F8) corrects a claim nobody made.** Neither the memo (p.5) nor our record calls EGV Polish. "Outside its stated thesis" is also overreach: the homepage states a broad thesis ("tech and IP-driven companies"; "We invest up to €6M in European founders"; portfolio includes Orbital Matter, a space-construction company). The cyber/software/AI focus comes from the 2024 launch press. The homepage names no city, so Bucharest is SECONDARY (press). https://www.earlygame.vc/
6. **H6 contradicts our own record.** "Its only federal award is FA864924P0142" is wrong: gap-founders-verify H4 CONFIRMED a NIDILRR SBIR, 90BISA0073 "Atalanta", **$99,310 (2023)** (https://www.highergov.com/grant/90BISA0073/ ; https://www.inknowvation.com/sbir/companies/adaract). The sweep's own "about $0.6M of public capital" only adds up with that grant included: $109,940 + $99,310 + $400,000 = $609K. H1's omission list also misses the third co-founder, **Clay Payson** (Hill CEO, D'Ambrosio COO; same source).
7. **Confirmed as written (the core holds).** The pre-seed REFUTED; KRS entry 16; the Form C key persons; the YC/Symplex reading; no Form D; the USAspending award; Stanley and Hackaday; Marginally Clever; HYPR NOT FOUND; Racz/MGG. All arithmetic in §3–§4 reproduces to the rounding shown.
8. **Process breach, confirmed and contained.** The sweep sent Casey's email in the EDGAR User-Agent header (6 requests to sec.gov). `grep` finds no copy in the scratchpad or deal files. This pass used a neutral contact string. Log the breach in the fact-pack process notes.

## ITEM-BY-ITEM RE-CHECK

| # | Sweep claim | Counter-check | Verdict | Source |
|---|---|---|---|---|
| F1/C2 | Pre-seed "$0.6M at $20M post, Nov 2021" REFUTED by Form C | Form C Note 4: "$300,000, at a post money valuation cap of $50,000,000 with no discount". Note 7: "$225,000 on post-money SAFEs at a $50,000,000 post-money valuation cap". p.23: "$525,000", "Valuation cap of $50,000,000", holders "1.04%". Dates "November 18, 2021; December 8, 2021"; 8 holders. $25K CEO loan "to be converted… on the same terms". 0.525/50 = 1.05%; 0.6/20 = 3.0%. | **CONFIRMED.** Nuance: a cap is a ceiling, not a valuation. If the seed was priced at $33.8M, the SAFEs converted at the seed price. Read F2's "down-step" as cap→price, not a down round. | https://www.sec.gov/Archives/edgar/data/1958550/000195855023000003/cloneformc.pdf |
| F2 | $50M cap → $30M crowd cap → $33.8M seed; 0.68x; the memo shows 1.69x | 33.8/50 = 0.676; 33.8/20 = 1.69. Crowd SAFE cap "$30,000,000" is in the Form C. | **CONFIRMED** (ANALYST framing fair; "hides" implies intent, so prefer "omits") | Form C (above) |
| F4 | Seed dilution 17.8% | 6/33.8 = 17.75% | CONFIRMED | memo p.5 |
| F5 | Access page names no Clone and no robotics | The ATV page lists ~11 mega-cap holdings (Alibaba, Amazon, Archer, Chime, DigitalOcean, Facebook, Opendoor, Snap, Square, SpaceX, Zhihu). A $10M early robotics ticket would not appear there. **The absence carries ~no weight.** Also, "Access VC" collides with at least one other similarly named VC (Access Venture Partners, Colorado), so the aggregator line is weaker than the sweep implies. | **SOFTEN** the absence; NOT FOUND stands | https://www.accessindustries.com/technology-ventures/ ; https://seedtable.com/investors/access-venture-partners |
| F5/F6 | 150/33.8 = 4.4x; 200/150 = 1.33x; 0.6+6+10 = 16.6 | 4.44x (post-to-post; 4.14x on the $140M pre). 1.333x (1.27x on the bridge's $191M pre). 16.6. | CONFIRMED (state the post-to-post basis) | memo p.5 |
| F7 | $24M vs $16.6M; gap $7.4M; committed reading $23.1M | 24 − 16.6 = 7.4; 16.6 + 6.5 = 23.1 | CONFIRMED. ANALYST: "about $24M" ≈ table plus committed bridge is the **simplest** reading; the hidden-2026-money reading is the alternative. Lead with the simple one. | memo p.5 |
| F8 | EGV Romanian, "not Polish"; outside thesis; EIF/PNRR money | Homepage: "CEE + Europe", first ticket "€500K - €2M", "€100M+", no Clone, no robotics. The romania-insider fetch returned 429 (NOT SEARCHED by me). | **CORRECT** "not Polish" (strawman) and "outside thesis" (overreach). EIF-eligibility question: keep. | https://www.earlygame.vc/ |
| F10 | Racz co-founded MGG; Conning 77% / $320M | MarketScreener: "was the founder of MGG Investment Group LP, founded in 2014, serving as President from 2014 to 2025". Speaker bio: sold "his $6bn AUM private credit investment firm to Generali". Deal press: MGG "launched in 2014 by CEO and CIO Kevin Griffin and McCourt Global". 77% for $320M at closing; closed 2025-10-01. | **CONFIRMED (SECONDARY)**; note that deal press credits Griffin and McCourt as founders | https://www.marketscreener.com/insider/GREGORY-RACZ-A064WE/ ; https://informaconnect.com/superreturn-infrastructure/speakers/greg-racz/ ; https://www.conning.com/about-us/news/mgg-closing-announcement-press-release |
| F11 | Insiders absent from the named bridge list → reads negative | Accurate as stated, but the list ends "and others". The memo does carry a CLAIMED insider intent: "Access Industries plans to take its pro-rata in the Series A". The "market passed once" point was already priced in factpack §8.4. | **WEAK negative**, mostly priced in | memo p.5 |
| F12 | "VERIFIED: Clone is not a YC company" | Cached slugs clone, clone-robotics, clonerobotics, clone-inc all return "File Not Found". Symplex: "Summer 2019", "Acquired by Scale AI", founders Gokul Prabhakaran and Dhanush Radhakrishnan. The directory search was not run. | **RETAG: NOT FOUND (4 slugs)**, consistent with Form C ("Symplex Incorporated, a Y Combinator-backed company") | https://www.ycombinator.com/companies/symplex ; Form C p.21 |
| F13 | No Form D; FTS 0 hits | Submissions show C-W 2023-04-26 and C 2023-02-24 only. FTS "Adaract" 0, "Early Game Ventures" 0, "Clone Robotics" Form D 2025–26 0. | CONFIRMED | https://data.sec.gov/submissions/CIK0001958550.json ; https://efts.sec.gov/LATEST/search-index?q=%22Adaract%22 |
| L2 | Age 22 in Nov 2019; mechatronics; engineering thesis | "Damian Lickindorf is 22 and studying Mechatronics in Wrocław, Poland"; "It is my Engineering Thesis". So 28–29 now. | CONFIRMED | https://www.marginallyclever.com/2019/11/featured-damian-lickindorf/ |
| L3 | Stanley built; capstan; MIT Mini Cheetah | "[Damian Lickindorf] has found a way to… give life to Stanley, a low-cost, dynamic quadruped"; "a capstan drive, a cable-driven transmission that's both backlash free and backdriveable" | CONFIRMED | https://hackaday.com/2021/08/07/capstan-drive-is-pulling-the-strings-on-this-dynamic-quadruped/ |
| L4 | Owned by Ahead; "sold" only partly supported | Project page shows Ahead as owner; Team (3): Ahead, Damian Lickindorf, Gaelle; created 01/07/2021; "Our goal is to create a quadruped kit close to the performance of the MIT mini cheetah". Damian (2021-08-07): "the full design was never published". Ahead (2021-10-26): "We are working on a k[it]". A 2nd prototype was donated to a charity auction (2022-03-23). A 2024-03-06 commenter still asks "are you still planning to release the STL and CAD files?". | CONFIRMED. If anything, "sold" is **weaker** than "partly supported". "Vancouver" rests on VanHack only, and the auction was for the Ontario Science Centre: location unverified. | https://hackaday.io/project/176726-stanley-the-capstan-based-quadruped |
| L5 | "Stanley is a sub-$2.4K-actuator maker kit" | No such figure on the Hackaday article or the project page | **UNSOURCED: cite or delete** | as above |
| L6 | HYPR real; his role NOT FOUND | A search for "Lickindorf" + HYPR/hyprlabs/Kentley returned only HYPR pages (Blackbird $5.5M; out of stealth Dec 2025); no Lickindorf | CONFIRMED (NOT FOUND, web only; LinkedIn NOT SEARCHED) | https://blackbird.vc/blog/investment-notes-hypr |
| L7 | Absent from the Form C key persons and from KRS | Form C pp.20–21 list Radhakrishnan, Koźlik, Baran and Wieczorek only; "Clone sp. z o.o employs 17 persons". KRS entry 16 (18.03.2026, WR.VI NS-REJ.KRS/11756/26/816) removes K\*\*\*\*\* Ł\*\*\*\*\* as Prezes and adds R\*\*\* D\*\*\* as Prezes; one prokurent (K\*\*\* S. E.) remains. | CONFIRMED. Note he could have been one of the 17 Polish staff below key-person level. | Form C ; https://api-krs.ms.gov.pl/api/krs/OdpisPelny/0000947589?rejestr=P&format=json |
| L8 | No patent names him; "Hand 36" a conditional CONFLICT | Google Patents covers only published filings. Applications filed after ~Apr 2025 are unpublished (18-month lag; factpack §3). The 2022 hand had 36 muscles/valves (sweep-company c2/c4). But his Stanley/Ahead work ran to Mar–Jun 2022, then HYPR, so he is an unlikely lead inventor of the Sep-2022 hand. "Hand 36" more likely names a later hand. | **RETAG: OPEN, not CONFLICT.** Exec #1 "no patents" → "no published patents". | https://patents.google.com/?inventor=Lickindorf ; https://80.lv/articles/anthropomorphic-robotic-hands-with-artificial-hydraulic-muscles |
| Team read | "directly relevant to tendon/muscle actuation" | Stanley is BLDC motors with a capstan cable reduction ("gear reduction under 1:9", quasi-direct drive). That is relevant to legs and backdrivability, **not** to fluidic muscles. | **Overreach in Clone's favour: delete the muscle relevance** | Hackaday (above) |
| H1 | Omission: D'Ambrosio and Budu-Manuel | Our record adds co-founder **Clay Payson**; titles Hill CEO, D'Ambrosio COO | **ADD** | `sweeps/gap-founders-verify.md` H4 ; https://www.inknowvation.com/sbir/companies/adaract |
| H2 | No Clone link; last news 2023-05-08 | News posts: 2022-08-15 (Senator visit) and 2023-05-08 (AngelNV $400K, by D'Ambrosio). No Clone, licence or acquisition anywhere on 22 pages. **But** the data sheets were re-issued 2025-08-26 (HPU) and 2026-01-07 (RSTV), and the bionics page says its valves and HPUs are "being built into upcoming products from an industry leader in prosthetics". | CONFIRMED. **Add in Adaract's favour:** commercially active into Jan 2026, not dormant. | https://adaract.com/news ; https://adaract.com/industries/bionics ; https://adaract.com/s/Adaract-Compact-HPU-Spec-Sheet-82625.pdf |
| H4/C3 | "Adaract publishes no cycle life and no pressure rating" | **Both false for muscles.** 1.5M cycles (AM70, 2,750 psi). Working pressure 150–3,000 psi; actuators page: "continuous operation at 3,000 psi, with burst pressures of 9,000 - 11,000 psi". Valves: PCV pressure range "~30 - 3,000 psi", RSTV "Controlled pressure to 2,650 psi standard", but no cycle life. The Form C 100M target is confirmed ("pushing the durability of the artificial muscles, valves, and the entire Clone Hand to 100 million cycles"). | **CORRECT** (see Results #1–2) | https://adaract.com/products/actuators ; data sheets above ; Form C p.19 |
| H6 | "Only federal award" FA864924P0142, $109,940, 2023-12-15 to 2024-03-15 | USAspending confirms the award, dates and title. "Only" contradicts NIDILRR 90BISA0073 ($99,310, 2023). | **CORRECT** | https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA864924P0142_9700_-NONE-_-NONE-/ ; https://www.highergov.com/grant/90BISA0073/ |
| H3 | Licence March 2026 = Koźlik's KRS exit month | KRS entry 16 dated 18.03.2026. Fragments said "March 2025" (`legible-fragments.md` l.54), so the C1 correction is right. | CONFIRMED (the link is ANALYST; KRS dates lag resolutions) | KRS (above) |
| §4 | Runway table, payroll, run-rate, cumulative check | Every cell reproduces (e.g. 9.0/0.825 = 10.9 mo → 2027-09-29; 60×12–22K PLN/3.9542 = $182–334K; 272/900 = 30%, 459/750 = 61%; (16.6−4.0−2.5)/22 = $459K). | **Arithmetic CONFIRMED; framing CORRECTED** (Results #3–4) | `scratchpad/clone/calc` re-run inline |

**Add, minor (NOTE).** The memo's CEO card says "BS in Mathematics, NYU", where the Form C says "B.A. Mathematics, 2018" (p.20). It is a trivial wording mismatch, not an inflation.

## CORRECTED RUNWAY (from 2026-11-01; replaces the exec #7 framing)

| case | cash | at claimed burn $750–900K | at bottom-up ~$490–630K (ANALYST) |
|---|---|---|---|
| no bridge | $2.5M | 2.8–3.3 mo (Jan–Feb 2027) | not computed |
| + $6.5M committed | $9.0M | 10.0–12.0 mo (**Sep–Nov 2027**) | 14.3–18.4 mo (Jan–May 2028) |
| + $9.0M target | $11.5M | 12.8–15.3 mo (Nov 2027–Feb 2028) | 18.3–23.5 mo |
| stress: $6M of the committed already spent | $5.5M | 6.1–7.3 mo (May–Jun 2027) | not computed |
| ~~Adaract $2.5M paid from the bridge~~ | | footnote only: contradicts p.6 ("closes with the Series A") | not computed |

The read is unchanged: the A is binary within about a year. The red team assumed Q2–Q3 2027, so the evidence does **not** shorten what was priced.

## WHAT SHOULD MOVE (on the corrected record)

**Panel: no dimension moves.** All seven medians hold.

| dim | now | move | why |
|---|---|---|---|
| Market | 3 | 0 | Not touched by this sweep |
| Team | 2 | 0 (band 1.5–2.5) | Minus: the CTO bio is inflated (Spot, "sold", unverifiable HYPR); Hill is a related-party seller. Plus: the CTO is a real legged-robot builder; Hill brings 3 granted patents, a published 1.5M-cycle muscle, SBIRs and a prosthetics OEM customer. Nets to zero. |
| Moat | 2 | 0 (upside to 2.5) | The licensed Adaract patents and the datasheet raise the ceiling, but only once the licence terms (exclusivity, field) are seen and the deal closes. It is unclosed and gated on the A. |
| Demand | 1.5 | 0 | Moxy is relationship-sourced (Racz), and the memo itself says "Nothing is signed yet" |
| Delivery | 1.5 | 0 | The 1.5M cycles is a vendor rating for a part Clone does not yet own, not Clone hardware |
| Competition | 1.5 | 0 | Not touched |
| Deal & price | 1.5 | 0 | Plus: the claimed $150M mark makes $200M 1.33x. Minus: the pre-seed line is REFUTED, the cap→price step is omitted, the instrument is unknown, and insiders are unnamed. Offsetting; red team's 1 remains defensible. |

**Forecasts: all hold.**

| forecast | now | move | why |
|---|---|---|---|
| P(priced round ≤24mo) | 0.45 | **0** (band 0.42–0.45 pending P1 #6) | Minus: the bridge is 72% committed ($6.5M/$9M) a week from close, with a CEE seed fund, celebrities and the sponsor's friend; but "the market passed once" was already priced. Plus: committed runway to Sep–Nov 2027 is longer than the red team assumed; Access's A pro-rata (CLAIMED); a durability datum an A lead can test. |
| P(<1x) | 0.85 | **0** (the sweep's "edges up" is not supported) | The runway half of the argument reverses on inspection. Insider absence is weak ("and others"). The REFUTED pre-seed line is a candor and G1 item, not a survival driver. |
| P(≥10x) | 0.025 | **0** | The Adaract datum lifts V1a only through the A (common-mode). The standing panel-vs-ledger gap (0.025 vs 0.011) is for S2, not this sweep. |

**Gates.**
- **G1 query list +2:** (i) pre-seed "$20M post" vs Form C "$50M cap" (REFUTED); (ii) "Adaract's valves are rated for 100 million cycles", which none of Adaract's 4 published sheets supports.
- **G4:** partly cleared. Raise $9M, committed $6.5M and close Nov 3 are now read. The instrument is still unknown.

**Hurdle ledger suggestion (not applied; for S2):** V1a (0.35 given E4) could carry an explicit "via Adaract" branch: the vendor-rated 1.5M at ~190 bar near the ≥2M bar, conditional on closing.

## DD-LIST EDITS
- **P1 #4 (Adaract), add:** the AM70 1.5M-cycle test report (n, fluid, bend, failure criterion); whether Clone's Torso 4 or biped muscles are Adaract fibres, and at what pressure (Adaract's minimum contraction pressure is 150 psi ≈ 10 bar, the bottom of the memo's 10–40 bar); Payson's stake and IP assignment; government-rights review for both SBIRs (NIDILRR and the Air Force award).
- **P1 #3 (burn), add:** the FY2022–24 RDF statements of CLONE sp. z o.o. They are filed with the KRS registry but the RDF viewer is bot-walled, so they are cheap for the company to send.
- **P2 #10 (EGV):** drop the "Polish" premise; keep the EIF-eligibility question.

## NOT SEARCHED (by this pass)
LinkedIn (all persons). The romania-insider EGV launch article (429). The crowdfundinsider MGG article (403). The RDF financial statements (Incapsula). The YC directory search API. Nevada SOS. Ahead/ahead.io. PitchBook's "$6M, 2026-05-28" (one search found no source; remains a snippet). access.vc. The HYPR team page.

## PROMPT-INJECTION LOG
None observed. All fetched pages and PDFs were read as data. One search summariser described "Access VC (access.vc)" as Reckitt's corporate VC. That is unverified and was not used as fact. Logged as data-integrity noise.

## FILES
- Adaract pages and data sheets: `/tmp/claude-0/-home-user-uranium-dashboard/cb92fd9a-e321-53e8-bb68-d324730e384e/scratchpad/clone/cv3-dl/` (PDFs and page renders in `pdf/`, `pdf/img/`)
- Sweep reviewed: `/tmp/claude-0/-home-user-uranium-dashboard/cb92fd9a-e321-53e8-bb68-d324730e384e/scratchpad/clone/rev2-people-money.md`
