# Clone Robotics — founder sweep (gap fill), 2026-10-27

Protocol: `templates/founder-sweep.md` v1 (11-point checklist), first run on this deal.
Builds on `sweeps/sweep-company.md` §(b) and `verify-company.md` and does not repeat them.
Tags: VERIFIED (primary URL) / SECONDARY / CLAIMED / CONFLICT / NOT FOUND (where searched) /
NOT SEARCHED / REFUTED / ANALYST. Template mapping: VERIFIED = CONFIRMED; NOT FOUND or
NOT SEARCHED = UNVERIFIABLE; **ADVERSE** is marked inline.
Budget: about 31 web searches plus direct primary-source calls. Several registries were
bot-walled. Each one is listed in §3 as NOT SEARCHED, never as NOT FOUND.
Prompt injection: none seen in any fetched page, feed or API response.

## 1 · Executive read (8 lines)

1. **The memo's illegible licence and acquisition counterparty ("Adlated?") is very likely Adaract, and its founder is the memo's "Joseph Hill".** Adaract Technologies, Ltd. is a Nevada company (Reno, founded 2022). It builds hydraulic artificial muscles, microhydraulic valves and compact pumps for prosthetics and robotics, and Joseph Daniel Hill is its founder and inventor. Hill sits on the memo's team page. The memo's text under the cards ("exclusive licence… $1.5M… March 2025… acquisition") reads as Adaract's (ANALYST, from a blurred memo; consistent with VERIFIED Adaract facts). No public source links Adaract to Clone.
2. **Adaract has patents and Clone does not.** Adaract holds two **granted US patents**, US11719263B2 and US12378979B2 (variable-recruitment fluidic actuators, expiring 2042), plus a pending McKibben-type "Muscle actuator system" (US20250389284A1; JP and CA national phases). The PCT application **did not enter Europe** (EP and DE non-entry, 2026) (VERIFIED, Google Patents). Every Clone-side name returns **0 patents**. "Clone says its technology is patented" most likely means *licensed Adaract patents* (ANALYST). That makes the G1 test answerable, and it means the licence does **not** cure Koźlik's chain of title. It is a second, separate IP chain.
3. **Koźlik: no new venture, no dispute, no patent and no public statement found.** "Automaton Robotics" is his **pre-Clone** project name (2014–21), not a new company. Clone's YouTube channel was created 2016-04-14, which fits his old channel having been absorbed by the company (ANALYST). His status at Clone Inc. is still unconfirmed. The memo's team page appears to show the CEO, an unidentified second executive and Hill, but not Koźlik (low-confidence read).
4. **The departed 2022 co-founders look clean.** In KRS, Tarnowski was Vice-President and Świerk was the sole commercial attorney (prokurent) of the Polish company until entry 5 (2022-07-19). Tarnowski is now an inventor at Unitem sp. z o.o. (Wrocław, crane sensing). That is non-competing, and he holds no Unitem board seat or shares. Świerk has no professional trace beyond a possible namesake. No IP claims, patents or disputes were found for either.
5. **Baran and Wieczorek: current status unknown.** No patents tie either name to Clone; the hits are namesakes in unrelated fields. LinkedIn is blocked. The valve inventor's continued presence is still an open question.
6. **CEO: clean on what we could search.** Courts: SAOS 0 hits; CourtListener ran 1 query (0 hits) before throttling. EDGAR shows only Clone's own Form C and C-W. A bio claim checks out: a 2019 *Nuclear Fusion* paper by A.H. Reiman (PPPL) and D. Radhakrishnan. Symplex (YC S19) was "Acquired by Scale AI" on undisclosed terms.
7. **Headcount: about 46 (SECONDARY), almost all in Wrocław.** The 2023 filing showed 1 US employee and 17 in Poland. Mountain View rests on the CEO's word (no address). The memo lead reads roughly "~3 in Mountain View, plan to relocate ~10 engineers, no business team". **Clone's own careers feed lists 0 open roles today** (VERIFIED). Known postings are Wrocław B2B contracts.
8. **Team score: no change (2), with a wider band.** Roles are now more unresolved, not less: the CTO seat is publicly vacant, the second executive is unidentified, and Baran's status is unknown. Hill would add domain fit only if the acquisition closes. Moat has a conditional upside from an exclusive licence to granted US patents, capped by the missing European coverage.

## 2 · Evidence by person

### 2.1 Dhanush Radhakrishnan — CEO, co-founder; sole board member of CLONE sp. z o.o.

| # | Checklist | Finding | Tag | Source |
|---|---|---|---|---|
| D1 | 1 Identity | CEO, co-founder and director of Clone Inc. (Form C). KRS entry 16 (2026-03-18) made D. R\*\*\* (born 27.09.1996) PREZES of the Polish company. He is now its only board member and can act alone. | VERIFIED | https://www.sec.gov/Archives/edgar/data/1958550/000195855023000003/cloneformc.pdf (printed p.20) ; https://api-krs.ms.gov.pl/api/krs/OdpisPelny/0000947589?rejestr=P&format=json |
| D2 | 2 Career | Bio claim "published plasma physics theory research conducted at the Princeton Plasma Physics Lab in IAEA, Nuclear Fusion" is **consistent**: A.H. Reiman and D. Radhakrishnan, "Near-singular equilibrium currents near magnetic islands with broken symmetry", *Nucl. Fusion* 59(5):056016, 2019-04-02. Reiman is a PPPL theorist. Crossref gives no affiliations, so the author match is ANALYST. | VERIFIED (paper) / ANALYST (identity) | https://doi.org/10.1088/1741-4326/ab0968 ; https://api.crossref.org/works/10.1088/1741-4326/ab0968 |
| D3 | 2 Career | The "~1 MW MPD thruster" claim has no public trace. | CLAIMED | Form C printed p.21 |
| D4 | 3 Prior venture | Symplex (YC S19): "Acquired by Scale AI", team of 8, NYC. Founders were Gokul Prabhakaran and Radhakrishnan. YC's slug `communion` resolves to Symplex. Terms are not public. The Form C says it raised $1.5M. | VERIFIED (status) / NOT FOUND (terms) | https://www.ycombinator.com/companies/communion ; Form C p.21 |
| D5 | 4 Litigation | SAOS (Polish published judgments, current: 21,431 judgments dated 2025 or later): **0** for "Clone sp. z o.o.", "CLONE SPÓŁKA Z OGRANICZONĄ", "Clone Robotics" and "Clone Incorporated". Web search for "Dhanush Radhakrishnan" lawsuit/fraud/dispute/sued returned only a namesake Tamil actor. CourtListener RECAP "Clone Robotics": **0**. Person-level CourtListener queries were throttled (see §3). | NOT FOUND (partial) | https://www.saos.org.pl/api/search/judgments?all=%22Clone%20sp.%20z%20o.o.%22 ; https://www.courtlistener.com/?type=r&q=%22Clone%20Robotics%22 |
| D6 | 6 Regulatory | EDGAR full-text: "Clone Inc" + Radhakrishnan → only Form C (2023-02-24) and C-W (2023-04-26). No other filings or bars. | VERIFIED (absence) | https://efts.sec.gov/LATEST/search-index?q=%22Clone%20Inc%22%20Radhakrishnan |
| D7 | 7 IP | Google Patents, inventor "Dhanush Radhakrishnan": **0**. | NOT FOUND | https://patents.google.com/?inventor=Dhanush+Radhakrishnan |
| D8 | 11 Adverse media | Nothing adverse found (searches above). | NOT FOUND | as D5 |

### 2.2 Łukasz Koźlik — co-founder, muscle/valve originator; off the Polish board 2026-03-18

| # | Checklist | Finding | Tag | Source |
|---|---|---|---|---|
| K1 | 1/10 Role history | KRS: Koźlik on the board from entry 1 (24.01.2022), PREZES from entry 4 (12.05.2022), struck from all board roles in entry 16 (18.03.2026, WR.VI NS-REJ.KRS/11756/26/816). He held 40 of 120 Polish shares until entry 5, when Clone Inc. took 100%. | VERIFIED | KRS OdpisPelny (as D1) |
| K2 | 10 Departure | No announcement, interview, post or press item on his departure. All 2026 directories (Craft, aiwiki, Caplight) still list him as CTO, which is stale-looking. | NOT FOUND / SECONDARY (stale) | https://craft.co/clone-robotics ; https://aiwiki.ai/wiki/clone_robotics ; https://www.caplight.com/company/clonerobotics |
| K3 | 3 Ventures | **"Automaton Robotics" is not a new venture.** Pre-Clone sources (LinkedIn snippet; 2022 Research in Poland) describe it as the startup supporting his "Golem" water-hydraulic arm (200 W). Freethink calls Clone "formerly Automaton Robotics". | SECONDARY | https://pl.linkedin.com/in/soulkozak (snippet; page HTTP 999) ; https://researchinpoland.org/news/towards-the-future-engineers-from-wroclaw-have-designed-a-robot-based-on-human-anatomy/ ; https://www.freethink.com/robots-ai/humanoid-robots-clone-hand |
| K4 | 3/7 Assets | Clone's YouTube channel (UCd0xLOw6No5IAsq3Y2-b0eA, @CloneRobotics) was created **2016-04-14**, five years before Clone Inc. That fits the Form C's "112,000 YouTube subscribers" being his channel, now company-controlled. Last upload 2025-11-15 ("Musculoskeletal Clone Hand Joint Controller V2"). | VERIFIED (dates) / ANALYST (origin) | https://www.youtube.com/feeds/videos.xml?channel_id=UCd0xLOw6No5IAsq3Y2-b0eA |
| K5 | 3 Ventures | No new company found. The official KRS has no person index. A company-name search for "Koźlik" (krs-pobierz) returned only unrelated family-name firms (PHU Koźlik, Columbex R.Koźlik, Domy Koźlik, etc.), none in Wrocław robotics. Person-indexed aggregators were bot-walled (§3). | NOT FOUND (weak) | https://krs-pobierz.pl/szukaj?q=Ko%C5%BAlik |
| K6 | 2 Career | Form C prior roles: Ediom sp. z o.o. (2019–21; autonomous-submarine sampler) and Bartek PPH (2016–21). Ediom exists (KRS 0000636436, Białystok, software, PKD 62.01Z), but his role there is not verifiable. | VERIFIED (entity) / CLAIMED (role) | https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000636436?rejestr=P&format=json ; Form C p.20 |
| K7 | 7 IP | Google Patents: inventor "Lukasz Kozlik" **0**; "Łukasz Koźlik" **0**; "Kozlik" + muscle/actuator/valve/hand: 50 hits, all other Kozliks. EDGAR "Lukasz Kozlik": only the Form C and C-W. | NOT FOUND | https://patents.google.com/?inventor=Lukasz+Kozlik ; https://patents.google.com/?inventor=%C5%81ukasz+Ko%C5%BAlik ; https://efts.sec.gov/LATEST/search-index?q=%22Lukasz%20Kozlik%22 |
| K8 | 10 Equity | Feb 2023: 3,000,000 shares (43.54% of issued voting stock). Świerk's and Tarnowski's shares were repurchased at par "upon departure", which implies founder shares carried a repurchase right (ANALYST). A 4-year schedule from Oct 2021 would leave him **fully vested by Mar 2026**, so a departed founder plausibly still holds a large common block. | VERIFIED (2023) / ANALYST (2026) | Form C pp.24, 26, Note 5 |
| K9 | 4/11 Dispute | No dispute, claim or adverse item found (web, SAOS, EDGAR). | NOT FOUND | searches §4 |
| K10 | 1 Memo team page | The memo team page's three cards appear to read: Radhakrishnan; an unidentified second executive (two-word name, second word ~8–9 letters, *not* obviously "Koźlik"); "Joseph Hill". Read at 4x upscale of a 310 px screenshot, so low confidence. | ANALYST (lead only) | `source/delta4-memo-screenshot.webp`; crop `scratchpad/clone/fs-dl/memo4-team.png` |

### 2.3 Amadeusz Świerk and Juliusz Tarnowski — co-founders, left 2022

| # | Checklist | Finding | Tag | Source |
|---|---|---|---|---|
| S1 | 10 Exit dating | KRS: **Tarnowski WICEPREZES ZARZĄDU** and **Świerk "prokura samoistna"** (sole commercial attorney) from entry 1; both roles and both 40-share stakes struck in **entry 5 (19.07.2022)**. Form C: 2,930,000 of their 3.0M Clone Inc. shares repurchased at par in 2022; 20,000 (Świerk) and 50,000 (Tarnowski) retained. | VERIFIED | KRS OdpisPelny ; Form C Note 5, Note 7 |
| S2 | 2/3 Now | **Tarnowski: inventor on PL446323A1** ("Environment detection system, especially for overhead cranes"), applicant **Unitem sp. z o.o.**, priority 2023-10-06, published 2025-04-07. Unitem: KRS 0000630936, Wrocław, PKD 28.99.Z (special-purpose machinery). Its current board and shareholders do **not** include him, which fits an employee-inventor. Crane perception does not compete with Clone. | VERIFIED (patent, KRS) / ANALYST (employee, same person) | https://patents.google.com/?inventor=Juliusz+Tarnowski ; https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000630936?rejestr=P&format=json |
| S3 | 2/3 Now | **Świerk:** the only same-name trace is a Wrocław documentary photographer born 1995. The KRS PESEL prefix (9…) is consistent with a 1990s birth, but the identity is unconfirmed and he has no engineering trace. Google Patents inventor "Amadeusz Swierk": **0**. | ANALYST / NOT FOUND | https://all-about-photo.com/photo-articles/photo-article/1317/the-miracle-district-by-amadeusz-swierk ; https://patents.google.com/?inventor=Amadeusz+Swierk |
| S4 | 7/10 IP claims | No patent, filing, suit or public claim by either touching muscles, valves or Clone. EDGAR "Juliusz Tarnowski" → only Clone's Form C. "Swierk" → unrelated IDT/FTD hits. | NOT FOUND | https://efts.sec.gov/LATEST/search-index?q=%22Juliusz%20Tarnowski%22 ; https://efts.sec.gov/LATEST/search-index?q=%22Swierk%22 |
| S5 | 10 Story | Interia credits the three Wrocław graduates as founders ("Głównym pomysłodawcą projektu jest Łukasz Koźlik"), with Radhakrishnan "z czasem dołączył" (joined over time). Undated. The CONFLICT with the Delaware record is already logged (sweep-company a7). | SECONDARY | https://geekweek.interia.pl/technologia/news-we-wroclawiu-powstal-syntetyczny-czlowiek-robot-imponuje,nId,21395575 |

### 2.4 Michał Baran (Chief Designer, valve inventor) and Mateusz Wieczorek (VP Engineering)

| # | Checklist | Finding | Tag | Source |
|---|---|---|---|---|
| B1 | 1 Role | Form C (Feb 2023): Baran is Chief Designer since 2022. He "invented 5X miniaturized fast valves" and "a new technology for mass production of Clone Hands", and was formerly a jeweller and watchmaker for 25+ years (AGH Kraków, Metallurgy). Wieczorek is VP Engineering since 2022 and owns all electronics and software (WUST). | VERIFIED (filing) | Form C pp.20–22 |
| B2 | 1 Current | **No 2024–26 evidence that either is still at Clone.** Searched web, LinkedIn (site:pl.linkedin.com snippet), Clone site/JS (no team page), Clone careers feed and Polish press. | NOT FOUND | searches §4 |
| B3 | 7 IP | Google Patents "Michal Baran": 1 (a 1928 US furnace). "Michał Baran": 3 PL patents (offset-printing powder, fruit sorting, plastics washer), most likely namesakes. "Baran" + valve/muscle/actuator/hydraulic/hand: top 10 of 1,280 all unrelated. "Mateusz Wieczorek": 19, mostly PL lamp designs (Kreatywny Kolektyw Mateusz Wieczorek) and a US imaging app, so namesakes. **No Clone-related filing by either.** | NOT FOUND (namesake-noisy) | https://patents.google.com/?inventor=Micha%C5%82+Baran ; https://patents.google.com/?inventor=Mateusz+Wieczorek |
| B4 | 6 | EDGAR: "Wieczorek" + "Clone Inc" → Form C only; "Michal Baran" Clone → 0. | VERIFIED (absence) | https://efts.sec.gov/LATEST/search-index?q=%22Wieczorek%22%20%22Clone%20Inc%22 |
| B5 | 7 IP hygiene | Clone's archived Wrocław "Valve Design Engineer" posting was a **B2B contract** (80–110 PLN/h). Under Polish law an invention made "z realizacji innej umowy" vests in the commissioning party unless agreed otherwise (Prawo własności przemysłowej art. 11(3)), and copyright transfer needs writing. Rights would therefore vest in whichever entity signed, likely the Polish subsidiary. That makes the Polish→US IP transfer load-bearing. | VERIFIED (posting) / ANALYST (legal reading, not counsel) | https://rocketjobs.pl/job-offer/clone-robotics-valve-design-engineer-wroclaw-inzynieria-mechanika ; https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20010490508 |

### 2.5 "Joseph Hill" — memo team page → Adaract founder

| # | Checklist | Finding | Tag | Source |
|---|---|---|---|---|
| H1 | 1 Identity | Joe Hill is "Adaract founder and lead engineer"; co-founder Marcus D'Ambrosio. The founders are "first-time entrepreneurs fresh out of the University of Nevada's engineering school". Adaract's soft muscles are "powered by hydraulic actuators… composed of individual fibers" and lift ">80 pounds" from a "<1 lb" thigh (Aug 2022, prototype stage). | SECONDARY | https://livingwithamplitude.com/synthetic-muscle-prosthetic-leg-adaract/ |
| H2 | 1/3 Company | Adaract's site today: "Ultra-Compact Fluid Power — Microhydraulic Valves, Hydraulic Power Units, Actuators". The robotics page sells "electrohydraulic artificial muscle actuator systems" for "High-Performance Legged motion" and "Appendage / Digit / Gripper control". Last news item: 2023-05-08, AngelNV first place, $400K. | VERIFIED (first-party) | https://adaract.com/ ; https://adaract.com/industries/robotics ; https://adaract.com/news |
| H3 | 7 IP | **Adaract patent family, current assignee Adaract** (inventors Joseph [Daniel] Hill, plus Francis Budu-Manuel on the first two):<br>• **US11719263B2**, variable-recruitment actuator systems: granted 2023-08-08, adj. expiry 2042-03-08.<br>• **US12378979B2**, dynamic recruitment modulation: granted 2025-08-05, adj. expiry 2042-06-20.<br>• **US20250389284A1**, "Muscle actuator system" (inner tube, braided outer sleeve, ferrule, potting: a McKibben end-fitting): pending, non-final action 2026-05-20.<br>• WO2025035028A1 (priority 2023-08-08): JP national phase JP2026528415A, CA3301107A1. **EP non-entry (2026-08-05) and DE non-entry.**<br>USPTO assignments recorded (reel/frame 059197/0092, 064295/0162) run only from the inventors to "ADARACT TECHNOLOGIES, LTD., NEVADA"; **none to Clone.** | VERIFIED (Google Patents index of USPTO/WIPO data) | https://patents.google.com/?assignee=Adaract ; https://patents.google.com/patent/US11719263B2/en ; https://patents.google.com/patent/US12378979B2/en ; https://patents.google.com/patent/US20250389284A1/en ; https://patents.google.com/patent/WO2025035028A1/en |
| H4 | 8 Grants | NIDILRR SBIR 90BISA0073, "The Atalanta: Artificial muscle powered above-knee prosthesis…". The amount (~$99.3K, complete) is from a search snippet; the page is paywalled. | VERIFIED (title) / SECONDARY (amount) | https://www.highergov.com/grant/90BISA0073/ |
| H5 | Link to Clone | **No public source links Adaract or Hill to Clone** (web: Adaract + Clone license/acquisition; "Joseph Hill" + Adaract + Clone; EDGAR "Adaract" = 0). The only link is the memo: team card plus "exclusive licence… $1.5M… March 2025… acquisition [unclosed]". Blurred reading: "Joe Hill… Clone signed an exclusive licence to Ada[ract]'s technology for $1.5M in March 2025… acquisition of the company… muscles are rated for 100 million cycles". | ANALYST (memo lead) / NOT FOUND (public) | `source/legible-fragments.md` ; crop `scratchpad/clone/fs-dl/memo4-below.png` ; https://efts.sec.gov/LATEST/search-index?q=%22Adaract%22 |
| H6 | 4/11 | No litigation or adverse-media search was run on Hill or Adaract (budget). | NOT SEARCHED | — |

### 2.6 Headcount by site

| when | figure | tag | source |
|---|---|---|---|
| Feb 2023 | Clone Inc. **1** employee (US); Clone sp. z o.o. **17** | VERIFIED (filing) | Form C XML `currentEmployees`; PDF pp.16–17 |
| Sep 2025 → now | 35 → 44; "current" 46 | SECONDARY | https://www.caplight.com/company/clonerobotics |
| now | LinkedIn band 51–200, HQ Wrocław | SECONDARY (snippet) | https://linkedin.com/company/clonerobotics |
| Mar 2026 | "recently opened its second office in Mountain View" (CEO); no street address found | SECONDARY | https://www.humanoidsdaily.com/news/the-synthetic-human-roadmap-clone-robotics-eyes-silicon-valley-and-20-000-price-points |
| memo (illegible) | roughly: most staff in Poland, ~3 in Mountain View, founder plans to move ~10 engineers there; HR, finance and legal outsourced; no business or GTM hires | ANALYST (lead) | memo p.4 crop `scratchpad/clone/fs-dl/memo4-teamtext.png` |
| 2026-10-27 | **Clone's own careers feed: 0 published roles.** Same call the site makes (`/_nuxt/DVdAbvUN.js`). Known postings (Valve Design, Senior Mechanical) are Wrocław, on-site, B2B, archived. | VERIFIED | https://clonerobotics.traffit.com/public/job_posts/published ; https://rocketjobs.pl/job-offer/clone-robotics-valve-design-engineer-wroclaw-inzynieria-mechanika |

## 3 · NOT SEARCHED (blocked or out of budget, so not evidence of absence)

- **KRS cross-holdings by person** for all six people. The official KRS API has no person index. rejestr.io (Cloudflare challenge), aleo.com and compabase (403) were unreachable. Only a company-name proxy ran (K5).
- **CEIDG** (sole-trader register) for all persons.
- **KRZ** (Krajowy Rejestr Zadłużonych, insolvency and debtors): krz.ms.gov.pl returned 403.
- **UPRP e-wyszukiwarka**: Incapsula bot wall. **Espacenet**: 403. Google Patents (which indexes PL A1/B1, WO, EP) was the proxy and found PL446323A1. Direct UPRP/EPO checks were not run.
- **USPTO assignment database** (direct): the egress proxy refused assignment-api.uspto.gov. Google Patents' mirror was used, and it can lag.
- **CourtListener**: only RECAP "Clone Robotics" ran (0). Person queries (Radhakrishnan, Symplex, Kozlik) were throttled (429/403). PACER, Delaware, California and Nevada state courts were not searched.
- **UCC / liens**: not searched for any person.
- **Polish grants** (NCBR, PARP, Fundusze Europejskie/mapadotacji beneficiary lists) for Clone sp. z o.o. (NIP 8982273079): the list files were unreachable. One web search was null, which is weak.
- **sbir.gov API**: 403.
- **LinkedIn** profiles (HTTP 999): snippets only. This is the main gap on Koźlik/Baran/Wieczorek current status.
- **eKRS financial statements** FY2022–24 (staff counts): RDF bot wall.
- **Nevada SOS** record for Adaract Technologies, Ltd. (status, officers).
- **Export-control/sanctions** screening (BIS, OFAC, EU) for all persons.
- **Adverse media / litigation for Joseph Hill and Adaract**; keyword adverse searches ("fraud/dispute/fired") for Baran, Wieczorek, Świerk and Tarnowski. Only name searches ran for those four.

## 4 · SEARCHED, NOTHING FOUND (exact queries, 2026-10-27)

- **Web:** "Łukasz Koźlik" OR "Lukasz Kozlik" 2026 · Lukasz Kozlik Clone Robotics left new startup artificial muscle · site:linkedin.com "Kozlik" Clone OR "Automaton" Wrocław muscles · "Automaton Robotics" Koźlik · "Łukasz Koźlik" KRS spółka Wrocław zarząd · Koźlik Clone Robotics Wrocław współzałożyciel 2026 · Clone Robotics co-founder departure OR "left the company" OR dispute Kozlik · "Lucas Kozlik" · "Michał Baran" Clone robotics OR "Self-Created Metal Composites" OR "Fabricable Fabric Formwork" · "Michał Baran" jubiler OR zegarmistrz robot OR Clone · "Mateusz Wieczorek" Clone Robotics OR "Clone" Wrocław engineering · site:pl.linkedin.com "Clone" Wieczorek OR Baran Wrocław · "Juliusz Tarnowski" Unitem OR robotics OR Wrocław · "Amadeusz Świerk" OR "Amadeusz Swierk" · "Dhanush Radhakrishnan" lawsuit OR fraud OR dispute OR sued OR complaint · Adaract "Clone Robotics" OR Clone license OR acquisition · "Joseph Hill" OR "Joe Hill" Adaract Clone · "Clone sp. z o.o." dofinansowanie/NCBR/PARP/Fundusze Europejskie.
- **Google Patents (xhr):** inventor Lukasz Kozlik 0 · Łukasz Koźlik 0 · Dhanush Radhakrishnan 0 · Amadeusz Swierk 0 · assignee Clone Incorporated 0 · Clone sp 0 · Clone Inc + muscle/valve/actuator/robot: 5 unrelated (EZ-Clone, Sci-Clone…) · q=Myofiber: biology only · Michał Baran / Mateusz Wieczorek: namesakes only (B3).
- **EDGAR full-text:** "Adaract" 0 · "Joseph Hill" Adaract 0 · "Michal Baran" Clone 0 · "Lukasz Kozlik" / "Juliusz Tarnowski" / "Wieczorek"+"Clone Inc" / "Clone Inc" Radhakrishnan → only Clone's own Form C and C-W.
- **SAOS:** 4 company-name queries, 0. (Polish judgments anonymise natural persons, so a person-level search is structurally impossible there.)

## 5 · New DD questions — ranked (statuses ○ not yet asked; 60-day clock from first ask)

**P1 — decision-gating**
1. ○ (C+S) **Adaract.** Confirm the counterparty is Adaract Technologies, Ltd. (NV).
   - Licence: date; exclusive in which fields and territories; sublicensing; termination triggers (change of control, non-payment, insolvency); how much of the $1.5M is paid.
   - Patents covered: US11719263B2, US12378979B2, US20250389284A1, JP2026528415A, CA3301107A1, and any others.
   - Acquisition: price, cash or stock, the minimum-cash condition, and the long-stop date.
   - Assignments from co-inventor F. Budu-Manuel and co-founder M. D'Ambrosio.
   - *Moves:* Moat, G1, runway (cash locked), key-person.
2. ○ (C) **"Clone says its technology is patented": which patents?** Are they Adaract's (licensed) or Clone-owned filings? Which Clone products practise them (Myofiber? valves? pumps?)?
   - *Moves:* G1. Licensed patents described as "its technology" is an overstatement, not a trip. No numbers at all trips G1.
3. ○ (C) **Joseph Hill's status.** Employee, officer or consultant of Clone today? Start date, agreement type, invention assignment, equity. What happens if the acquisition fails to close?
   - *Moves:* Team (fit), key-person.
4. ○ (C) **Koźlik, refined.** Current relationship with Clone Inc. (director? employee? consultant?); share count today and vesting/repurchase terms; any separation agreement or paid post-employment non-compete; who owns the 2014–21 work, the "Automaton Robotics" name and the 2016 YouTube channel/video archive.
   - *Moves:* cap-table overhang, chain of title, prior-art exposure.

**P2 — score-moving**

5. ○ (C) **Who is the second executive on the memo's team page?** Role, start date, background.
   - *Moves:* Team ("roles unresolved").
6. ○ (C) **Are Michał Baran and Mateusz Wieczorek still at Clone?** If they left: when, and under which IP agreements. Are Polish engineers employees or B2B contractors? Do the B2B contracts carry IP-transfer clauses, and when did the Polish subsidiary transfer IP to Clone Inc.?
   - *Moves:* Moat (valve IP), Team.
7. ○ (C) **Headcount** by entity and site; employees vs B2B; the Mountain View address and staff count; relocation plan and cost; why the careers feed shows 0 roles.
   - *Moves:* burn, execution, FCC onshoring.
8. ○ (C) **Is Europe covered?** Adaract's PCT did not enter EP/DE. What protects the muscle/valve design where Clone builds (Poland)?
   - *Moves:* Moat.

**P3 — completeness**

9. ○ (C) Świerk and Tarnowski: 2022 repurchase and separation documents, IP assignments, and any residual rights attached to the 20,000 and 50,000 retained shares.
   - *Moves:* tail IP risk (low).
10. ○ (C) Identity and role of prokurent S. E. K\*\*\* (since entry 6).
    - *Moves:* governance completeness.
11. ○ (C) The memo's muscle-life figure: "100 million cycles" (team-page paragraph, possibly Adaract's) vs "100,000(?)" (risks section). Test data, fluid, pressure and owner.
    - *Moves:* the durability crux (fact pack §4).

## 6 · Material to the team score?

Rubric Team anchors (v1.1): **1** = no shipping history, roles unresolved, fit generic · **3** = competent, first-time-at-this-scale, partial fit · **5** = shipped at scale in the domain's hard part. Pedigree is capped: prior EXITS count; degrees and brand names alone do not.

| finding | anchor it touches | direction |
|---|---|---|
| CEO record clean on searched sources; PPPL/*Nuclear Fusion* bio claim consistent (D2, D5–D8) | candor | small +; no change to 2 |
| Symplex "acquired by Scale AI", terms unknown, 8-person team (D4) | prior exit, capped | ≤ +0 to +0.25; a likely acqui-hire earns little under the cap |
| CTO seat publicly vacant; second executive unidentified; Baran/Wieczorek status unknown (K2, K10, B2) | "roles unresolved" (anchor 1 language) | **−** pressure; supports the red team's 1.5 until answered |
| Hill/Adaract: hydraulic-muscle founder with granted patents (H1–H3) | "fit to the domain's hard part" | **+ only if the acquisition closes and Hill joins**; he is a first-time founder of a prototype company, so no scale credit |
| Memo discloses the licence and acquisition plus "a co-founder who has since left" | candor (sponsor) | small + for the sponsor; Clone's public silence while directories list Koźlik as CTO is mildly − |
| Departed 2022 founders clean; Tarnowski non-competing (S1–S4) | structure | neutral (removes a tail risk) |
| ~46 staff, Wrocław-heavy; 0 open roles; B2B contracting (§2.6, B5) | execution / structure | neutral to slightly − (burn, FCC onshoring, IP plumbing) |

**Net: Team stays at 2 (panel median). The band widens to [1.5, 2.5], and the DD answers decide which end.**
- Answers on #3/#5/#6 that show a staffed CTO-level owner and a closed Adaract deal → 2.5.
- Koźlik holding a large block while gone, or Baran also gone, → 1.5.

**Other dimensions:**
- **Moat (2):** conditional upside to ~2.5 if an exclusive, worldwide licence to the granted US family covers Clone's products. Capped by the EP non-entry and by the patents being Adaract's design, not Myofiber's.
- **G1:** now testable (DD #2).
- **Forecasts:** no change to P(<1x) / P(≥10x) on this sweep alone.
- **Tripwire 7** ("Koźlik: competing venture or IP claim"): nothing found; keep it live.
