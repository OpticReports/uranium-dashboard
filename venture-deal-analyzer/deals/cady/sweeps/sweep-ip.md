# CADY sweep: is anything proprietary? (IP / prior-art / hardware-reasoning)

Sweep date 2026-10-15. Tags: VERIFIED / SECONDARY / CLAIMED / CONFLICT / NOT FOUND / REFUTED.
Raw downloads: `scratchpad/cady/web-ip/`. Reproduction script: `scratchpad/ipscripts/cady_repro.py`.
Injection attempts in fetched content: **none seen** (ICH site, Trademarkia, Google Patents, KATO README, search results).

## (a) Executive read (8 lines)

1. The milestone's five "proven" tests are textbook 1969-1977 AI: inheritance in a semantic network (Quillian), frames (Minsky), most-specific-type classification (description logics), candidate elimination (Mitchell). **VERIFIED: we reproduced all 5 tests plus ladder rungs 1-3 in 56 lines of stdlib Python, on a CPU, in under 1 s.**
2. The sheet itself says the demo "ran live over her saved knowledge graph; her FPGA reasoning core was untouched". By its own account **the FPGA did no part of the demonstrated reasoning**. "Learned-pattern count held constant" is not a verification: it is exactly the reading you get if the FPGA does nothing.
3. Doc CONFLICT: "The intelligence IS the chip" and "these five abilities... live in the hardware" (Thinker) vs. reasoning done in a knowledge layer with the core untouched (Milestone). The Overview (Oct) instead pitches a generic "AI inference acceleration" card. That is two different products on one card.
4. Hardware reasoning is old and crowded: Prolog machines (PLM 1987), semantic-network hardware (SNAP, IXM2, ~1990), and Rete in FPGA for financial streams (Exegy US8374986, priority 2008). Recent FPGA knowledge-graph accelerators (KGAccel 2025, HDReason 2024) are a further layer of prior art. A new entrant would need specifics. None are disclosed.
5. Patents: **NOT FOUND**. No published patents or applications name ICH, Intelavation or WeSave as assignee. Stewart's only patent family is a 2005 Source, Inc. "Secure transaction system" (payments). Nothing turned up for Wilson/Hanson + FPGA/cognitive. The caveat is that filings after about Apr-2025, and all provisionals, are still unpublished, so absence is only weakly informative. Even so, "All IP... is owned by ICH" comes with zero visible filings.
6. Trademarks: no US filing for CADY, "A Sovereign Thought", "The Thinking Chip" or "Intelligence Where Performance Matters" (SECONDARY, via Trademarkia; USPTO search was unreachable). **"CADI" (the Milestone's own spelling) is already pending in Class 42 AI-as-a-service for an unrelated Cadi.me LLC (SN 99577584, filed 2026-01-05).** WeSave Inc. filed WESAVE itself twice, without a lawyer, and abandoned both.
7. Earlier identity: ICH's own site is a loyalty-rewards processor (Wix, (c)2024, Newhall CA). It never mentions CADY, FPGA, Wilson or RJ Stewart. The pilot "apply" URL lands on a Strategic Partners page with no form. A 2019 "Spectrum" page pitched a "virtually unhackable" smart-city radio network from an unnamed defense partner, using the same rhetoric. No AI or chip history was found for this team.
8. Bottom line: **nothing proprietary has been shown.** The only thing that could be proprietary is unseen RTL or a bitstream. The five demands in section (f) would settle that in one session.

## (b) Test-by-test prior art

| Test (as claimed) | What it is formally | Earliest prior art | Difficulty |
|---|---|---|---|
| T1 "Climbs the hierarchy": wheels + 4+ wheels + enclosed cabin → car; "wheels" inherited from vehicle | Instance classification against an IS-A hierarchy with inherited slots, i.e. DL "realization" (most-specific concept) | Quillian 1968 semantic memory; Collins & Quillian 1969 (canary→bird→animal) [1]; Minsky frames 1974 [2]; KL-ONE 1985; OWL reasoners such as HermiT do this automatically [3] | Intro-AI week 2-3. Our repro: a dict plus a parent walk |
| T2 Sibling discrimination (motor vs pedal) | Choosing the differentiating attribute between siblings; set difference of trait sets | Winston 1970 "near-miss" structural learning; ID3 attribute selection (Quinlan 1986); the 1970s "Animal" 20-questions program; biological dichotomous keys (Linnaeus) | Trivial: a set difference |
| T3 Spoon inherits "used for eating" | Property inheritance downward from the superclass (default inheritance) | Quillian 1968; Collins & Quillian 1969 (exact paradigm: "a canary has skin" via animal) [1]; Fahlman NETL 1979 | Trivial |
| T4 "Consistent with both, names the missing trait" | Version space with more than one surviving hypothesis; abstention; the next discriminating query | **Mitchell 1977, candidate elimination ("all rule versions consistent with...")** [4]; Chow 1957/1970 reject option; MYCIN asks the user for missing findings (Shortliffe 1976) | Trivial: filter, then a symmetric difference |
| T5 "has wheels" → vehicle, kind undetermined (the "headline") | Most-specific common ancestor of the consistent set (open-world DL answer); hierarchical back-off | DL realization under the open-world assumption [3]; **Deng et al. CVPR 2012 "Hedging your bets"** backs off to the parent class when unsure, which is the neural-net case the sheet says cannot do this; selective classification (El-Yaniv & Wiener 2010; Geifman & El-Yaniv 2017, arXiv:1705.08500) | Trivial |
| Ladder 1: learns a fact, keeps it after the source is removed, refines it, reasons across memories | Persistent KB plus assert/retract, forward chaining, belief revision | Prolog assert/retract (Colmerauer/Kowalski 1972-74); truth-maintenance systems (Doyle 1979); AGM belief revision 1985 | Trivial: a file write |
| Ladder 2: applies a rule, says which fired, refuses on insufficient evidence | Production system with an explanation trace | MYCIN WHY/HOW explanations (Shortliffe 1976; Davis, Buchanan & Shortliffe 1977); OPS5/Rete (Forgy 1982); CLIPS 1985 | Trivial |
| Ladder 3: a "real perception tool labeled 60 objects; she learned all 60; tool removed; recalled all 60" | Caching a detector's output labels in a store | Any database. The tool is unnamed; YOLO/COCO-class detectors emit labels off the shelf | Trivial: storing 60 strings |

- **Repro (VERIFIED):** `python3 ipscripts/cady_repro.py` produces T1-T5 with inheritance provenance and "it is a vehicle, but I cannot say which kind... Missing deciding trait(s)". It also stores and recalls 60 labels after the source is deleted, and reports which rule fired. 56 non-comment lines, stdlib only, CPU. Caveat: the CADY taxonomy is not disclosed, so this reproduces the described behaviour, not their outputs.
- **Beyond an undergraduate assignment?** No. As described, this is below a typical intro-AI homework (Russell & Norvig ch. on categories/objects; Prolog family-tree exercises). Nothing in it needs learning, uncertainty arithmetic, scale, or speed.
- **"FPGA reasoning core untouched":** the reasoning ran in a "knowledge layer" over a saved graph; a "standalone read-only verification" is a host script. So the FPGA's contribution to this milestone is zero by the issuer's own words. **CONFLICT:** the ladder says each rung was "proven live, on the same reasoning core", while this rung says the core was untouched. "Every step on owned silicon" is a weasel phrase, because the host CPU is also owned silicon.
- **"Learned-pattern count held constant":** a write counter that does not change during read-only queries cannot come out any other way (unfalsifiable). It shows nothing was written, not that anything was computed on-chip. It says nothing about correctness or provenance, and it would read the same if the card were unplugged. It is framed as a virtue ("without disturbing her cognition core"), which turns non-involvement into a selling point.

## (c) FPGA and hardware reasoning: the literature, and what a genuine architecture looks like

**Prior art (all predate CADY):**
- Dedicated logic-programming hardware: Berkeley PLM, a WAM in hardware, built and claimed 10x (Dobry 1987, UCB/CSD-87-352) [5]; Japan's ICOT PSI/PIM (Fifth Generation, 1982-92). These were abandoned because general CPUs caught up: "hardware implementations did not have much success due to the lack of market" [6]. VERIFIED (SECONDARY sources).
- Semantic-network / knowledge-graph hardware: Fahlman NETL (1979, marker-passing inheritance); **SNAP (Semantic Network Array Processor), USC, 144 DSPs, IEEE TPDS 1993** [7]; IXM2 associative-memory knowledge processor (ETL Japan, ~1991) [8]. This is exactly "inheritance reasoning in silicon", 30+ years ago.
- **Rule engines in FPGA for finance:** Exegy / IP Reservoir US8374986B2, "accelerated stream processing", priority 2008-05-15. A Rete network (alpha/beta nodes) is implemented in an FPGA coprocessor, with financial-market monitoring among the listed applications [9]. VERIFIED (Google Patents page). This overlaps directly with CADY's "watch bank streams in hardware" pitch.
- FPGA knowledge-graph reasoning: KGAccel (PMLR 2025, 65x over CPU) [10]; HDReason (hyperdimensional KG reasoning on FPGA, arXiv:2403.05763) [11]; survey Besta et al. arXiv:2408.12173 [12]. FPGA graph frameworks: GraphGen (FCCM 2014), ForeGraph (FPGA 2017).
- Interpretable logic-based learners in fabric: Tsetlin-machine FPGA with on-chip online learning (Prescott et al. 2023, arXiv:2306.01027) [13]; LogicNets (Xilinx, FPL 2020, arXiv:2004.03021, <15 ns inference) [14]. This is the closest real analogue to "designed logic, explainable, low-power, learns on chip", and it is published and open.
- Neuromorphic: IBM TrueNorth (Merolla et al., Science 2014, about 70 mW for 1M neurons); Intel Loihi (Davies et al., IEEE Micro 2018, on-chip learning). Both have public architecture papers, which CADY lacks.
- Open-source deterministic, traceable "pattern" engines already exist, e.g. KATO ("Knowledge Abstraction for Traceable Outcomes", Apache-2.0, CPU-only) [15]. Note: the phrase match "learned-pattern count" is generic and **no link to CADY is claimed**.

**Hardware claims checked:**
- "~2.6 million FPGA logic units" is consistent with a commodity part: Xilinx VU9P = 2,586K system logic cells (Alveo U200, AWS F1 "approx 2.5M logic elements") [16][17]; Intel Stratix 10 / Agilex parts are about 2.7M LEs. This is SECONDARY inference; ask for the part number. The Alveo U200 is rated **225 W max** [18], against the Thinker's "about 20 W". **CONFLICT (soft):** possible only at very low utilization.
- "No remote exploit for a wire / need physical access to change how she thinks": **REFUTED as a general claim.** PCIe FPGA cards are reprogrammed from host software (AMD XRT, AWS AFI load; SECONDARY, vendor docs not fetched). Remote power side-channels on FPGAs are published (Zhao & Suh, IEEE S&P 2018; Schellenberg et al., DATE 2018) [19]. Bitstream encryption has been broken on 7-series (Starbleed, USENIX Security 2020; UltraScale+ not shown affected) [20]. The demo's knowledge graph is host-saved data, which is a software attack surface.
- CONFLICT: "designed rather than trained" and "data not stored" vs. "she learns what normal looks like", "falls as she learns", "learned all 60". Learning requires writable state derived from data.

**What a genuine hardware-reasoning architecture would show (and a scripted KG demo cannot):**
1. The KB is compiled into on-chip structures: trait bitmasks or a CAM in BRAM/URAM, with parallel AND/compare per class. Classification then takes a fixed number of clocks, with measured ns-level on-card latency and µs end-to-end over PCIe.
2. Learning means writing on-chip memories through a defined datapath, not resynthesis and not a host DB. Counters change when it learns and stay constant on reads.
3. Vendor tool reports (utilization, timing closure) where the reasoning modules account for the logic, plus RTL with a dated history.
4. The behaviour survives killing the host KB process. It breaks when a stock or blank bitstream is loaded.
5. Line-rate streaming results (e.g., 10/100 GbE or PCIe DMA) on a defined workload against a CPU baseline.

## (d) Patents / trademarks / code / prior identity

| Item | Finding | Tag | Where searched |
|---|---|---|---|
| Patents, assignee ICH / "International Clearing House" / Intelavation / WeSave | 0 | NOT FOUND | Google Patents xhr endpoint (assignee=; full-text "WeSave"+FPGA/cognitive = 0). Intelavation full-text query stayed rate-limited (503, 3 tries); assignee query = 0 |
| Inventor Richard G. Stewart | One family: WO2006083825A2 / US20060191995A1 / EP1856674A2 / HK1111251A "Secure transaction system", Source, Inc., priority 2005-02-01. 0 with priority 2015-2026 | VERIFIED | Google Patents |
| Inventor John Wilson + FPGA + (knowledge graph / cognitive architecture / inference engine / reasoning core), priority ≥2018 | 0 (the broad "John Wilson"+FPGA query returns only a Qualcomm namesake) | NOT FOUND | Google Patents; arXiv API (au:"John Wilson" + FPGA/reasoning/cognitive: 1 irrelevant) |
| Inventor Brad C. Hanson | 0 | NOT FOUND | Google Patents |
| "Thinking chip" + FPGA, priority ≥2020 | 0 | NOT FOUND | Google Patents |
| Unpublished window | US applications publish about 18 months after priority, and provisionals never publish. Filings after about Apr-2025 would be invisible. Absence is weakly informative for a young company. **Flag:** an unqualified "All IP in CADY's cognitive architecture is owned by ICH" with no visible filing. Ask for serial numbers or provisional dates | — | — |
| TM: CADY | 18 US marks (hoists, cheese, photography, Motobecane motorcycles 1968...). None in Class 9/42, none by ICH/WeSave/Intelavation | NOT FOUND (SECONDARY) | Trademarkia (USPTO tmsearch blocked by AWS WAF challenge; API returned 405) |
| TM: **CADI** | **Cadi.me LLC (DE), SN 99577584, filed 2026-01-05, Class 42 "AI as a service", first use 2025-04-07, pending (suspension letter 2026-09-01).** Prior AI user of the Milestone's spelling | VERIFIED (SECONDARY source) | Trademarkia detail page |
| TM: "A Sovereign Thought", "The Thinking Chip", "Intelligence Where Performance Matters", "American Silicon", INTELAVATION | No exact-match filings | NOT FOUND (SECONDARY) | Trademarkia (fuzzy results reviewed, 2 pages each) |
| TM: WESAVE | WeSave Inc. filed it pro se from 24254 Main St, Newhall (the ICH HQ address): SN 97281587 (2022, abandoned 2023) and SN 98725387 (2024, abandoned 2025-07-01, failure to respond). Earlier SRC, Inc. WESAVE filings 2005/2008 were cancelled | VERIFIED (SECONDARY) | Trademarkia |
| Name collision | "CADY" is an Israeli AI EDA company (schematic copilot, Altium/Altair partner, raised $3M) | SECONDARY | Web search (cbinsights, calcalistech, altium) |
| ™ use | ™ needs no filing, so the marks are legal but unprotected beyond common law | — | — |
| Code | GitHub repo search for "cady fpga", "intelavation", "cady cognition knowledge graph": 0. No arXiv or conference papers by the CTO found | NOT FOUND | GitHub search API (via MCP); arXiv API; web |
| ICH website | Nevada corp. formed Mar-2019 by Source, Inc.; a loyalty-rewards SaaS processor. Leadership page: **Stewart "Founder & Chairman", Brad C. Hanson "CEO & Director"** (ex-Meta Financial, founded Meta Payment Systems 2004). The About page calls Stewart "President/CEO" (CONFLICT inside the site). No CADY, FPGA, Wilson or RJ Stewart anywhere. The pilot URL `/team-3-1` = "Strategic Partners" page, with no application form | VERIFIED | internationalclearinghouse.com (10 pages fetched 2026-10-15) |
| Earlier tech pitch | ICH "Spectrum" page: in 2019 it "contracted with a small defense company founded in 1994" (cognitive radio, multi-sensor fusion, ML) for a "virtually unhackable" smart-node radio network "already... used by our military". The partner is unnamed; the description fits ANDRO Computational Solutions (Rome NY, est. 1994), but **this is unconfirmed and no link to CADY or Wilson was found** | VERIFIED (page) / SECONDARY (partner ID) | ICH site; web search |
| "CADY AI", "Cady cognitive", "Intelavation", "FPGA-based mind", "A Sovereign Thought" | No prior incarnation found. Intelavation LLC has no web, patent or TM footprint | NOT FOUND | Web search (several queries), Trademarkia, Google Patents |

## (e) Steelman: the strongest honest case that something is proprietary

- **Trade-secret RTL could exist.** A working FPGA design is a real asset even when its concepts are 50 years old. Compiling a taxonomy or rule base into parallel bitmask/CAM matchers that classify in a few clock cycles, with learning by writing on-chip tables (not resynthesis), plus cross-stream correlation at line rate and card-to-card scale-out, is legitimate engineering. It could be protectable as trade secret, copyright, or narrow implementation patents. Exegy shows such implementations can be patented and monetised in finance.
- **The product property is genuinely useful.** Abstaining, naming the missing evidence, and full traceability are what bank model-risk regimes (SR 11-7-style explainability) want. Packaging old, sound symbolic AI into an on-prem card for banks could be a defensible *product* even if it is not novel *science*. In that case the moat is distribution (Hanson's payments/bank background), not IP.
- **Honest boundary-keeping.** The Milestone explicitly says what was *not* shown (perception from raw vision). That is better practice than most decks.
- **What would prove it:** (i) RTL plus a dated git history and vendor implementation reports showing the reasoning logic in fabric; (ii) a live run with the host KB killed and the PCIe traffic captured; (iii) a bitstream swap that breaks the behaviour; (iv) measured on-card latency and power; (v) invention disclosures, patent or provisional serials, and IP-assignment agreements putting title in ICH (or Intelavation; the documents disagree on who owns it).
- **What the steelman cannot rescue:** the milestone *as documented* contains no FPGA contribution, and every test in it is reproducible in an afternoon. Any proprietary element is unproven and currently undisclosed.

## (f) Five demands that separate real hardware reasoning from a scripted KG demo

1. **Host-kill plus bitstream-swap test (decisive).** Rerun T1-T5 live with the "saved knowledge graph" process stopped and its storage unmounted, PCIe/network traffic captured, and `ps` shown. Then load a stock or blank bitstream and rerun. If the answers survive the swap, or die when the host KB dies, the FPGA is not reasoning.
2. **Blind taxonomy on the day.** We supply a 200+ class, 5-level taxonomy with defaults and exceptions (penguin/ostrich override), multiple inheritance and contradictory evidence. Score accuracy and abstention against HermiT/OWL and our 56-line baseline. Measure on-card vs. CPU latency.
3. **Hardware artifacts.** Exact card and FPGA part number; Vivado/Quartus utilization and timing reports; the RTL module list showing where taxonomy, rules and "learned patterns" physically live (BRAM/URAM tables vs. host); slot power measured under load (claim: about 20 W); git history with authors and dates. Also the promised "verifiable appendix" (taxonomy, rules, classifier logic, exact outputs), which was promised but not supplied.
4. **The learning/security contradiction, demonstrated.** Show a new fact being learned on-card: which datapath writes which memory, and the counter moving. Then reconcile that with "no code to exploit / need physical access", given that the card is reprogrammable over PCIe by host tools and stores data-derived state. Name the 60-object "perception tool" and show its ingestion code.
5. **Chain of title.** Patent or provisional serial numbers and filing dates; Wilson's employment or contractor IP-assignment agreement; which entity owns the IP (ICH vs. Intelavation LLC vs. WeSave, since the documents disagree) and the licences between them; the CADY/CADI trademark plan given the pending Cadi.me Class 42 filing.

## Sources

[1] Collins & Quillian 1969, JVLVB 8:240-247: https://link.springer.com/article/10.3758/BF03332461 (secondary), https://poplog.fricas.org/bham/computers-and-thought/chap6/node5.html
[2] Minsky 1974, AIM-306: https://dspace.mit.edu/bitstream/handle/1721.1/6089/AIM-306.pdf
[3] HermiT: https://www.cs.ox.ac.uk/isg/people/boris.motik/pubs/ghmsw14HermiT.pdf ; Owlready2 reclassification: https://owlready2.readthedocs.io/en/v0.47/reasoning.html
[4] Mitchell 1977 IJCAI pp.305-310: https://mlanthology.org/ijcai/1977/mitchell1977ijcai-version
[5] Dobry 1987 PLM: https://www2.eecs.berkeley.edu/Pubs/TechRpts/1987/5991.html
[6] Porto course notes on WAM hardware: https://www.dcc.fc.up.pt/~ricroc/aulas/0304/ilpl/nativo.pdf
[7] SNAP: https://mlanthology.org/aaai/1990/lee1990aaai-design/ ; https://cal.ucf.edu/wp-content/uploads/2020/06/j_demara_moldovan_itpds_93-abs.txt
[8] IXM2: https://www.academia.edu/94318132/IXM2_A_parallel_associative_processor_for_knowledge_processing
[9] US8374986B2 (Exegy; Rete in FPGA; financial market monitoring): https://patents.google.com/patent/US8374986B2/en
[10] KGAccel: https://proceedings.mlr.press/v288/chen25a.html
[11] HDReason: https://arxiv.org/abs/2403.05763
[12] KG hardware survey: https://arxiv.org/abs/2408.12173
[13] Tsetlin FPGA online learning: https://arxiv.org/abs/2306.01027
[14] LogicNets: https://arxiv.org/abs/2004.03021
[15] KATO: https://github.com/sevakavakians/kato
[16] VU9P 2,586K logic cells: https://www.s2cinc.com/products/fpga-prototyping/logic-system-vu9p/
[17] AWS F1 VU9P "approx 2.5 million logic elements": https://aws.amazon.com/blogs/aws/developer-preview-ec2-instances-f1-with-programmable-hardware
[18] Alveo U200 225 W max: https://www.amd.com/en/products/accelerators/alveo/u200/a-u200-p64g-pq-g.html ; DS962: https://docs.amd.com/r/en-US/ds962-u200-u250
[19] Zhao & Suh S&P 2018: https://dblp.dagstuhl.de/rec/conf/sp/ZhaoS18.html ; Schellenberg et al. DATE 2018: https://eprint.iacr.org/2018/012
[20] Starbleed: https://hgi.rub.de/en/news/newsarchiv/hginews/critical-starbleed-vulnerability-in-fpga-chips-identified
[21] ICH site: https://www.internationalclearinghouse.com/ (/team-3, /about, /about-ich, /history-of-ich, /spectrum, /team-3-1)
[22] Trademarkia: https://www.trademarkia.com/cadi-99577584 ; https://www.trademarkia.com/owners/wesave-inc ; https://www.trademarkia.com/search/trademarks?q=CADY
[23] Stewart patent: https://patents.google.com/patent/WO2006083825A2/en
[24] CADY (Israel, EDA): https://www.calcalistech.com/ctech/articles/0,7340,L-3926875,00.html
[25] ANDRO profile (partner-ID inference only): https://rocketreach.co/andro-computational-solutions-llc-profile_b5cedf52f42e0981
Not fetched this session, cited from the literature: Deng et al. CVPR 2012 "Hedging your bets"; Chow 1970 IEEE T-IT; El-Yaniv & Wiener JMLR 2010; Shortliffe 1976 MYCIN; Davis/Buchanan/Shortliffe 1977 AIJ; Forgy 1982 AIJ; Merolla et al. Science 2014; Davies et al. IEEE Micro 2018; GraphGen FCCM 2014; ForeGraph FPGA 2017. A counter-agent should spot-check these.

Counter-agent spot-check priorities: (1) rerun `ipscripts/cady_repro.py`; (2) the Cadi.me SN 99577584 status on USPTO TSDR when it is reachable; (3) the US8374986B2 Rete/FPGA claim text (FIG. 25); (4) the ICH leadership pages (titles).
