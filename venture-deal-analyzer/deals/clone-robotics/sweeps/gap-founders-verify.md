# Clone Robotics: counter-agent review of `gap-founders.md` (2026-10-27)

**Verdict: APPROVED WITH CORRECTIONS. No panel score or forecast moves.**
I re-checked every material line against its primary source: the KRS JSON, Form C text, Google Patents pages, YC, Crossref, the YouTube feed, the careers feed, EDGAR FTS, Caplight and the memo crops.
- **Core findings hold.** The counterparty is Adaract, Hill is its founder, Clone has no published patents, the 2022 co-founders look clean, and headcount is about 46.
- **One factual miss (moat-relevant):** Adaract holds **three** granted US patents, not two.
- **One overreach:** the "patented means licensed" reading.
- Several NOT FOUND tags are really NOT FOUND (weak) or NOT SEARCHED.
- Prompt injection: none seen.

## 1 · Re-check of material findings

| gap ref | claim | verdict | primary check |
|---|---|---|---|
| H3 / §1.2 | Adaract holds **two** granted US patents | **CORRECTED → three.** The pending US20250389284A1 is a *continuation* of US 18/798,629, which issued as **US12416318B2** "Muscle actuator system": granted 2025-09-16, assignee Adaract, inventor J. D. Hill, anticipated expiry **2044-08-08**, Hill→Adaract assignment recorded 2024-10-23. It was missed because the Google Patents assignee listing collapses family members. | https://patents.google.com/patent/US12416318B2/en ; https://patents.google.com/patent/US20250389284A1/en ("This Application is a continuation… Ser. No. 18/798,629") |
| H3 | US11719263B2 (granted 2023-08-08, exp. 2042-03-08); US12378979B2 (granted 2025-08-05, exp. 2042-06-20); reel/frame 059197/0092 and 064295/0162, effective 2022-03-02; WO2025035028A1 EP non-entry 2026-08-05, DE non-entry 2026-03-10, JP national phase | **CONFIRMED.** Adds: the 2021 variable-recruitment family is **US-only** (no PCT or foreign member). Foreign coverage exists only in the 2023 family: JP and CA, pending. | https://patents.google.com/patent/US11719263B2/en ; https://patents.google.com/patent/US12378979B2/en ; https://patents.google.com/patent/WO2025035028A1/en |
| §1.1 / H5 | The memo's "Adlated?" is Adaract and its "Joseph Hill" is Adaract's founder | **CONFIRMED and stronger (still ANALYST).** My own read of the team-card crop: the third card's first bullet appears to read "…Mechanical Engineering, University of Nevada, Reno". That matches UNR's profile of Hill as a UNR mechanical-engineering graduate and Adaract founder (search snippet; the page returned 503). It also fits the 7-letter "Ad?ra?t's technology" in the paragraph crop. No public Clone–Adaract link exists; my re-search was also null. | crops `fs-dl/memo4-team.png`, `memo4-below.png` ; https://www.unr.edu/nevada-today/news/2022/innevation-center-member-highlight-joseph-hill (snippet) |
| §1.1 | Adaract "Nevada, Reno, founded 2022" | **Unsourced in the gap file → now SECONDARY.** Inknowvation SBIR profile: founded 2022, 1664 N Virginia St, Reno; 5–9 staff. This is consistent with the assignment effective 2022-03-02. Nevada SOS still NOT SEARCHED. | https://www.inknowvation.com/sbir/companies/adaract |
| H1 | Hill is "founder and lead engineer"; "first-time entrepreneurs"; hydraulic fibres; >80 lb; <1 lb (Aug 2022) | **CONFIRMED** (article dated 2022-08-12). | https://livingwithamplitude.com/synthetic-muscle-prosthetic-leg-adaract/ |
| H4 | NIDILRR SBIR "Atalanta", ~$99.3K | **CONFIRMED** ($99,310, 2023 Phase I; second source). **NEW:** Air Force SBIR Phase I 2024, **$109,940**, "Multipurpose Robotic Gripper Powered by… Artificial Muscle Technology". Adaract is moving into grippers, which overlaps Clone's hand. **NEW:** a third co-founder, **Clay Payson**; titles are Hill CEO and D'Ambrosio COO. | https://www.inknowvation.com/sbir/companies/adaract (SECONDARY) |
| S1 / §1.4 | Tarnowski "WICEPREZES from entry 1" | **CORRECTED.** Board member from entry 1 (24.01.2022). The **WICEPREZES title was entered in entry 4 (12.05.2022)**, the same entry that made Koźlik PREZES. Świerk's "prokura samoistna" from entry 1 and both removals in entry 5 (19.07.2022) are confirmed. | https://api-krs.ms.gov.pl/api/krs/OdpisPelny/0000947589?rejestr=P&format=json (`funkcjaWOrganie… nrWpisuWprow: "4"`) |
| K1 / D1 | Koźlik off the board in entry 16 (18.03.2026, WR.VI NS-REJ.KRS/11756/26/816); D. R. (b. 27.09.1996) is sole PREZES | **CONFIRMED.** | as above |
| S2 | Tarnowski is the inventor on PL446323A1 (Unitem; priority 2023-10-06; pub 2025-04-07). Unitem: KRS 0000630936, Wrocław, PKD 28.99.Z. Its board and shareholders do not include him. | **CONFIRMED.** The same-person link is **stronger:** Research in Poland (Feb 2022) calls him the "Golem programmer", and environment sensing is perception software. Still ANALYST. | Google Patents xhr log `fs-dl/gp-results.txt` ; https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000630936?rejestr=P&format=json ; https://researchinpoland.org/news/towards-the-future-engineers-from-wroclaw-have-designed-a-robot-based-on-human-anatomy/ |
| K3 | "Pre-Clone sources (… 2022 Research in Poland)" show Automaton Robotics is not a new venture | **Conclusion CONFIRMED; sourcing CORRECTED.** The article is dated **9 Feb 2022**, *after* Clone Inc.'s 2021-10-12 incorporation, so it is not pre-Clone. It says "Clone Incorporated start-up (Automaton Robotics)", calls Kozlik "founder and now CTO of Automaton Robotics", and cites the "Clone (Automaton Robotics) – YouTube" channel. Automaton Robotics is therefore Clone's earlier brand. | same URL |
| K4 | YouTube channel created 2016-04-14; last upload 2025-11-15 | **CONFIRMED.** The "his channel, now company-controlled" origin moves from ANALYST to **SECONDARY** via the article's "Clone (Automaton Robotics) – YouTube". Who holds the account is still unknown. | https://www.youtube.com/feeds/videos.xml?channel_id=UCd0xLOw6No5IAsq3Y2-b0eA |
| K6 | Ediom: KRS 0000636436, Białystok, PKD 62.01Z | **CONFIRMED (entity).** Matching it to the Form C's "Ediom" is a name match only (ANALYST). It is a software house wholly owned by Infortex sp. z o.o. | https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000636436?rejestr=P&format=json |
| K8 | Founder shares carried a repurchase right; "a 4-year schedule from Oct 2021 → fully vested by Mar 2026" | **SOFTENED.** The arithmetic is right (Oct 2021 + 4 yrs = Oct 2025). But the Form C discloses **no founder vesting**: the only vesting language covers 1,295,000 Stock Plan shares. The retained 20,000 and 50,000 shares (1.3% and 3.3% of 1.5M) **do not fit** a standard 4-yr/1-yr-cliff schedule at ~9 months' tenure, which would leave 0 vested. That suggests negotiated par repurchases. "Koźlik plausibly still holds a large block" stands as ANALYST, with an unknown schedule. | Form C pp.24–26, Note 5 (`formc/formc.txt` l.1546–1580, 1724–1728, 2292–2296) |
| D2 | Reiman & Radhakrishnan, *Nucl. Fusion* 59(5) 056016 | **CONFIRMED** (online 2019-04-02, print May 2019; no affiliations, so identity stays ANALYST). | https://api.crossref.org/works/10.1088/1741-4326/ab0968 |
| D4 | Symplex "Acquired by Scale AI" (VERIFIED) | **SOFTENED.** YC's structured field reads "Status: Acquired" (VERIFIED). "by Scale AI" appears only in the founder-editable long description, so the acquirer is **CLAIMED**. Team 8, NYC, S19 and both founders confirmed. | https://www.ycombinator.com/companies/symplex |
| D6 / K7 / B4 | EDGAR FTS: "Clone Inc" Radhakrishnan, "Lukasz Kozlik" → only Form C and C-W; "Adaract" 0 | **CONFIRMED.** Also "Clone Robotics" 0. | https://efts.sec.gov/LATEST/search-index?q=%22Adaract%22 |
| §2.6 | Careers feed 0 roles; Valve posting B2B 80–110 PLN/h, archived | **CONFIRMED.** The feed returns `[]` from the same endpoint the site JS calls. The posting is dated: published **2025-04-17**, expired **2025-05-09**. An empty Traffit feed is a weak hiring signal: Clone may recruit through other channels. | https://clonerobotics.traffit.com/public/job_posts/published ; https://rocketjobs.pl/job-offer/clone-robotics-valve-design-engineer-wroclaw-inzynieria-mechanika |
| §2.6 | Caplight 35→44 (Sep 2025), 46 "current" | **CONFIRMED.** 46 is an undated "Employee Range" field. Caplight still shows "Lucas Kozlik, Co-Founder & CTO". | https://www.caplight.com/company/clonerobotics |
| B5 | PWP art. 11(3): vests in the commissioning party "z realizacji innej umowy" | Matches my reading of the statute. **Not re-fetched** (ANALYST, not counsel). | https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20010490508 |

## 2 · Overreach and tag corrections

1. **§1.2 "'patented' most likely means licensed Adaract patents"** is overreach and should be downgraded to "one plausible reading" (ANALYST). Reasons:
   - Any Clone application filed after about April 2025 is unpublished (18-month lag) and invisible.
   - US non-publication requests are invisible until grant.
   - The Google Patents full-text query `"Clone Robotics"` was **blocked and never completed**, both in `gp-results.txt` and on my retry (HTTP 503). That item is **NOT SEARCHED**, not 0.
   - UPRP and Espacenet were never queried directly.

   The G1 framing ("licensed-as-'its' = overstatement, not a trip; no numbers = trip") stands. The "0 patents" lines in D7, K7 and §4 are right only for published documents.
2. **D8, K9 ("no dispute or adverse item")** are **NOT FOUND (weak)**, not NOT FOUND. Each rests on 1–2 web queries, plus SAOS, which covers company names and published judgments only. Person-level US courts are **NOT SEARCHED**: CourtListener v4 still returned HTTP 429 for "Adaract", Kozlik, Radhakrishnan and "Clone Inc" on my retry, and PACER and state courts were never searched.
3. **B2 (Baran and Wieczorek current status)** is **NOT FOUND (weak)**. LinkedIn, the decisive source, is NOT SEARCHED (HTTP 999).
4. **H6 (Hill and Adaract adverse or litigation)** was NOT SEARCHED and is now **NOT FOUND (weak)**: one web query plus one docket-aggregator query (Justia, PACERMonitor, UniCourt, CourtListener index), both null. The only "Joseph Hill" 2026 docket is an unrelated Colorado prisoner case (https://dockets.justia.com/docket/colorado/codce/1:2026cv02519/255494). CourtListener is still NOT SEARCHED.
5. **§6 Moat line "patents being Adaract's design, not Myofiber's"** is unsupported because no claim comparison was done.
   - US12416318B2 claims a high-pressure McKibben termination (fitting, ferrule, needle, potting).
   - US11719263B2 claim 1 is a variable-recruitment system that switches subsets of McKibben actuators to the high-pressure line.
   - Either could read on a many-fibre water-muscle design, or not. Unknown (ANALYST).
   - **The licence is therefore both an upside and a dependency.** If Clone practises these claims and the licence terminates (for example, the acquisition fails or payments lapse), Clone carries US infringement exposure (ANALYST, not counsel).
6. **The DD #1 sub-ask "assignments from co-inventor F. Budu-Manuel and co-founder M. D'Ambrosio"** is partly answered already, and the remainder is mis-aimed:
   - Budu-Manuel→Adaract assignments are **recorded** (reel/frame 059197/0092 and 064295/0162: VERIFIED).
   - D'Ambrosio is not an inventor on any of the patents.
   - Replace it with the items in §3.

## 3 · DD edits (carry into the ledger)

- **P1 #1 (Adaract), amend the patent list:** add **US12416318B2**.
- **P1 #1, add:** any security interests or liens recorded against the Adaract patents.
- **P1 #1, add:** whether any licensed invention was conceived or reduced to practice under the 2023 NIDILRR or 2024 Air Force SBIR awards.
  - If so, 35 U.S.C. §204 requires an *exclusive US licensee* to manufacture substantially in the US.
  - That collides with Polish production. It compounds the FCC onshoring issue.
  - No federal-funding statement appears on the pages read, so the risk is low but unconfirmed. Counsel item.
- **P1 #1, add:** any equity or IP claims from co-founder **Clay Payson**.
- **P1 #2 (G1), add:** list any **unpublished** applications (filing dates, jurisdictions, applicant name), so that unpublished filings are not counted as absent.
- **P1 #1, add:** do Clone's current muscles practise Adaract's claims today? This sizes the dependency if the licence lapses.

## 4 · Score and forecast impact

| item | gap pass says | counter-agent | why |
|---|---|---|---|
| Team 30 (median 2) | no change; band [1.5, 2.5] | **No change (2). Band agreed.** | Nothing new is adverse. The firmer Adaract ID helps only if the deal closes and Hill joins. He is a first-time founder of a 5–9-person prototype firm, which earns no scale credit under the rubric cap. Vacant CTO seat and unknown Baran status keep the 1.5 tail live. |
| Moat 15 (median 2) | conditional upside to ~2.5 | **No change (2). The conditional upside is slightly better grounded but still conditional.** | Three granted US patents (the third covers the muscle termination itself, expiry 2044) vs two. Against that: identification is ANALYST from a blurred memo; licence terms, exclusivity, field and termination are unseen; there is no claim mapping to Myofiber; coverage is **US-only** (2021 family US-only; 2023 family has no EP or DE, so nothing where Clone builds); and the licence is also a dependency. Move to 2.5 only on documents. |
| Market / Traction / Competition / Deal | — | **No change.** | Nothing here touches them. |
| P(priced round ≤24mo) 0.45 | — | **No change.** | The acquisition's cash lock-up is already priced in the fact pack. |
| P(<1x) 0.85 / P(≥10x) 0.025 | no change | **No change.** | Founder-file items are either clean, ANALYST-conditional or DD-gated. None shifts the common-mode durability/autonomy/financing chain. |
| Tripwire 7 (Koźlik) | keep live | **Agree.** | Absence rests on weak searches. US courts and LinkedIn are NOT SEARCHED. |

## 5 · Still NOT SEARCHED after this pass

- CourtListener (HTTP 429 on retry), PACER, and DE, CA and NV state courts, for all persons and for Adaract.
- Google Patents full-text "Clone Robotics" and "Clone Incorporated" (HTTP 503 on retry).
- Direct UPRP, Espacenet and USPTO assignment database checks.
- Nevada SOS for Adaract.
- LinkedIn profiles for Koźlik, Baran, Wieczorek and Hill.
- KRS person index, CEIDG and KRZ.
- UCC and liens.
- Sanctions and export-control screening.
- Polish grants.
- Claim-by-claim mapping of the Adaract patents to Clone hardware.

## 6 · Process notes

- **Budget used:** 6 WebSearch calls (1 rejected for a blocked domain), 6 WebFetch calls (1 HTTP 503), and direct calls to Crossref, YC, YouTube, Traffit, Rocketjobs, CourtListener (429), EDGAR FTS ×4 and Google Patents xhr ×4.
- **Data error, not injection:** one search summary named a "CEO Janusz Jakubowski" for Clone. It came from an aggregator (xpert.digital) and was ignored. No prompt injection seen.
- **Disclosure:** my EDGAR FTS User-Agent string included a fragment of the account holder's name. No email was sent. It has not been repeated.
- **Downloads:** saved under `scratchpad/clone/cv-dl/`.
