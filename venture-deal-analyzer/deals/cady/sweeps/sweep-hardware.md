# CADY sweep: hardware and physical/commercial claims

Sweep date 2026-10-15. Scope: silicon identity, physical claims, comps. Tags: VERIFIED (primary or datasheet URL) / SECONDARY / CLAIMED / CONFLICT / NOT FOUND / REFUTED. "Derived" means arithmetic on verified numbers.
Prompt-injection log: no instructions or injection attempts found in any fetched page or PDF. All fetched content was treated as data.

## (a) Executive read (8 lines)

1. **Silicon is off-the-shelf class.** "~2.6M FPGA logic units" fits three commercial parts. Closest fit: **AMD Alveo V80**, which AMD's own datasheet lists as "2.6M LUTs" (2,574,208 exact). Next are VU9P-class cards (Alveo U200 / AWS F1: 2,586,150 "system logic cells") and Intel/Altera Agilex 7 AGF027 cards (2,692,760 LEs). None of the documents gives a part number, card photo or benchmark, and nothing points to custom silicon.
2. **Buying a card off the shelf costs far less.** V80: $9,495 MSRP. AGF027 PCIe card (Terasic): $5,491. Used U200: about $1.5-1.9k. So the $50k pilot is **5x-33x** the card price, and the $150k MSRP is **16x-100x**. The bank also supplies the server.
3. **"American Silicon" fails for the AMD candidates.** They are made by TSMC in Taiwan (7nm Versal, 16nm UltraScale+). Only an Intel/Altera part could qualify. Its core is made on Intel 10nm, but its transceiver tiles may be TSMC-made (SECONDARY).
4. **"No remote exploit / needs physical access" is refuted by vendor documents.** AMD's Alveo datasheet says the platform "remotely loads kernels". The FPGA user region is reprogrammed over PCIe from the host. The V80 itself runs Arm A72/R5F cores and firmware. AMD's Alveo host driver (XRT) had 5 CVEs in 2025, rated up to CVSS 8.0.
5. **"About 20 W" conflicts with the rest of the pitch.** Candidate cards are rated 150-225 W. Published readings on cards with unstated load are 21-58 W. So 20 W is about what an idle card draws, and cannot coexist with "ultra-high inference throughput".
6. **"Billionths of a second" is true only per clock cycle** (about 2-3 ns). A PCIe round trip alone takes about 1 µs. The best audited FPGA inference on a V80 has p99 latency of 1.95-2.88 µs, i.e. millionths of a second.
7. **The documents contradict each other:**
   - The June doc says CADY is not a neural net; the October flyer sells "AI inference acceleration".
   - "Data never leaves the chip / not stored" vs a "saved knowledge graph" and LLM tool calls.
   - The Milestone says the FPGA core was "untouched", so the reasoning it demonstrates did not run on the silicon.
8. **What can be said for the company:**
   - FPGAs are a reasonable platform for low-latency finance inference, with audited comps.
   - Card-to-card Ethernet and in-server PCIe deployment are real capabilities.
   - But both are AMD/Intel features: the "scale on standard networking, no proprietary hardware" text closely paraphrases AMD's U55C marketing.
   - No proprietary hardware is evidenced. Any IP would be in an unseen bitstream or software.

## (b) Silicon-match table

AMD "system logic cells" (SLC) = LUTs × 2.1875. VU9P: 1,182,240 × 2.1875 = 2,586,150 (derived). Intel LE = ALM × 2.95. AGF027: 912,800 × 2.95 = 2,692,760 (derived). So "2.6M" means **2.6M real LUTs** on a V80 but only **1.18M LUTs** on a VU9P, a 2.2x difference in real capacity. The deck's unit, "logic units", is not a vendor unit and hides which one it is.

| Card / part | Logic count (unit) | Power | Network ports | Price | Fab | Tag / source |
|---|---|---|---|---|---|---|
| **AMD Alveo V80** (XCV80 Versal HBM; A-V80-P64G-PQ-G) | **2.6M LUTs** (2,574,208); 5,631K SLC; 10,848 DSP; 32 GB HBM2e at 819 GB/s; on-chip PL memory 752 Mb (about 94 MB) | 190 W TDP, passive, needs 2× 8-pin AUX | 4× QSFP56 (AMD: "4x200G"; page: 2×100G or 4×10/25/40/50G per port) | **$9,495 MSRP**, 24-wk lead (AMD store, fetched today) | TSMC 7nm, Taiwan | VERIFIED: AMD DS1013 https://docs.amd.com/r/en-US/ds1013-v80/Adaptive-SoC-Resources ; https://docs.amd.com/r/en-US/ds1013-v80/Product-Details ; AMD store https://www.amd.com/en/products/accelerators/alveo/v80/a-v80-p64g-pq-g.html ; LUT exact: https://boards.fpgadeveloper.com/boards/Alveo-V80 (SECONDARY) ; TSMC 7nm: https://docs.amd.com/r/en-US/ug1442-vck190-base-trd/Versal-ACAP-Device-Architecture |
| **AMD Alveo U200** (VU9P-class; also VCU1525, AWS F1 VU9P) | 1,182K LUTs = **2,586,150 SLC**; 6,840 DSP; 64 GB DDR4; 35 MB on-chip SRAM | 215 W total card load (DS962); 225 W max (AMD page); passive cards need forced airflow and a 150 W AUX cable | 2× QSFP28 100GbE | AMD now "Contact Sales" and says new designs should target the V80. Distributor ref $6,608-$7,185 (SECONDARY). eBay used $1,500-$1,865 (SECONDARY) | TSMC 16FF+, Taiwan | VERIFIED: DS962 v1.7 https://docs.amd.com/r/en-US/ds962-u200-u250 (PDF mirror https://www.moderntech.com.hk/products/amd-xilinx/brochure/ds962-u200-u250.pdf) ; SLC: https://www.digikey.com/en/products/detail/amd/XCVU9P-2FLGC2104I/7203938 ; 16FF+: https://www.amd.com/en/products/adaptive-socs-and-fpgas/technologies/power-efficiency.html ; eBay: https://www.ebay.de/itm/306415736068 (snippet only) |
| **Intel/Altera Agilex 7 F AGF027** cards: BittWare IA-840F; Terasic P0728 (AGFB027) | **2,692,760 LEs** (912,800 ALMs); 8,528 DSP. BittWare markets it as "2.6M LEs" (SECONDARY) | IA-840F: NOT FOUND. P0728: NOT FOUND | IA-840F: 3× QSFP-DD per BittWare vs 2× QSFP-DD per Mouser (CONFLICT, SECONDARY) | **Terasic P0728 $5,491** (DigiKey US, 56-wk lead). IA-840F quote only | Intel 10nm SuperFin core. Transceiver tiles possibly TSMC (Stratix 10 precedent) | VERIFIED: https://ark.intel.com/content/www/us/en/ark/products/228838/intel-agilex-fseries-027-fpga-r31c.html ; https://www.intel.com/content/www/us/en/docs/programmable/683458/current/fpgas-and-socs-f-series.html ; https://www.digikey.com/en/products/detail/terasic-inc/P0728/22155630 ; SECONDARY: https://www.mouser.ca/new/bittware/bittware-ia-840f ; TSMC tiles: https://www.anandtech.com/show/12477 |
| Stratix 10 GX/SX 2800 (Intel PAC D5005; BittWare 520N) | 2,753,000 LEs (ARK rounds to 2.8M) | D5005 215 W TDP; 520N measured about 65 W in use | D5005 2× QSFP28; 520N 4 ports | D5005 discontinued; reseller $10,399 (SECONDARY) | Intel 14nm core + TSMC 16FF tiles (SECONDARY) | VERIFIED: https://cdrdv2-public.intel.com/652478/stratix-10-product-table.pdf ; https://ark.intel.com/content/www/us/en/ark/products/193921/intel-fpga-pac-d5005.html ; https://www.bittware.com/files/ds-520n.pdf |
| VU47P class (Alveo U55C/U280; AWS F2) | 1,304K LUTs = about 2.85M SLC (weaker fit) | U55C 150 W max / **115 W typical** | 2× QSFP28 | **U55C $4,747** (AMD store, 30-wk lead). AWS f2.6xlarge $1.98/hr, about $1,445/mo (SECONDARY) | TSMC 16FF+ | VERIFIED: https://www.amd.com/en/products/accelerators/alveo/u55c/a-u55c-p00g-pq-g.html ; https://aws.amazon.com/blogs/aws/now-available-second-generation-fpga-powered-amazon-ec2-instances-f2 ; price https://instances.vantage.sh/aws/ec2/f2.6xlarge |
| Achronix VectorPath S7t-VG6 (AC7t1500) | 692K 6-input LUTs (no 2.6M figure found: NOT FOUND) | NOT FOUND | 1× 400GbE + 2× 100GbE | $8,495 MSRP (vendor press release, dated) | TSMC 7nm (not verified here) | VERIFIED (vendor PR): https://achronix.com/press-releases/achronix-and-bittware-launch-vectorpath-accelerator-card-speedster7t-fpgas |

**Most likely bill of materials:**
- **Best match:** a stock AMD Alveo V80 (wording identical to AMD's "2.6M LUTs"; current-generation; 4 network ports; AMD markets it for FinTech) plus a host-side software stack.
- **Cheaper alternative:** a used VU9P card (U200 / VCU1525 / ex-AWS F1 class) described in inflated SLC units.
- **Only part that could fit "American Silicon":** an Agilex 7 AGF027 board.
- **Cost:** one card new is about $5.5k-$9.5k; used VU9P-class about $1.5-1.9k.
- **Caveat:** the bare-chip catalog price is not what a card buyer pays (DigiKey lists a single XCVU9P chip at $80,252.48, 52-wk lead, VERIFIED at the DigiKey URL above). Some markup also legitimately covers services (installation, engineering, reporting).

## (c) Claim-by-claim audit

| # | Claim | Doc | Verdict | Evidence + URL |
|---|---|---|---|---|
| 1 | "Approximately 2.6 million FPGA logic units" | Overview p2 | **VERIFIED as COTS-consistent; no custom silicon evidenced** | Same figure as AMD V80 "2.6M LUTs" (DS1013). VU9P 2,586,150 SLC (DigiKey). AGF027 2,692,760 LE (Intel ARK). The unit is non-standard. URLs in table (b). |
| 2 | "American Silicon" | Thinker p8 | **REFUTED for AMD parts; CONFLICT/open otherwise** | Versal is TSMC 7nm (AMD UG1442). UltraScale+ is TSMC 16FF+ (AMD). Agilex core is Intel 10nm SuperFin (Intel doc 683458), but Intel FPGA transceiver tiles have been TSMC 16FF (AnandTech, SECONDARY). Could just mean "US-designed"; ask for the part number. |
| 3 | "About 20 watts" / "less than a light bulb" | Thinker p3-4 | **CONFLICT** (plausible only at idle; incompatible with claim 7) | Ratings: V80 190 W TDP; U200 215-225 W; U55C 115 W typical (AMD pages). Measured: PC2 cluster sample readings of 21-58 W on Alveo/Versal cards (U280 "33.79 W"; load state not stated) and about 65 W on a 520N (https://upb-pc2.atlassian.net/wiki/spaces/PC2DOK/pages/1902007/Power+and+Energy+Measurements+of+FPGAs). The host server's power draw is excluded from the 20 W figure. In the company's favour: a lightly used 2.6M part can sit near 20 W, but then most of the logic is idle. |
| 4 | "Speed measured in billionths of a second"; "Billionths of a second" vs LLM "network round-trip" | Thinker p3-4 | **Partly true per clock cycle; REFUTED end-to-end** | Derived: one clock cycle at 300-500 MHz is 2-3.3 ns. PCIe round trip for 128 B is about 1,000 ns, of which PCIe is about 900 ns; p99 is 5,707 ns (Neugebauer et al., SIGCOMM'18, https://www.cl.cam.ac.uk/teaching/1011/R02/papers/p327-neugebauer.pdf). Best audited FPGA ML inference on a V80: p99 ≤1.95 µs (models A/B), 2.88 µs (model C), max ≤12.3 µs (STAC, May 2026, https://stacresearch.com/news/stac-ml-with-xelera-silva-together-with-amd-alveo-v80-and-an-hpe-proliant-dl385-gen10-plus-v2/). Bank transaction and log streams reach the card through host software. |
| 5 | "No program in her reasoning layer... no remote exploit for a wire... need physical access to the chip" | Thinker p2, p4, p8 | **REFUTED** | (i) DS962: the Alveo platform "remotely loads kernels" (PDF above). (ii) XRT loads the user-partition bitstream over PCIe through ICAP (Dynamic Function Exchange) (https://lkml.iu.edu/hypermail/linux/kernel/2011.3/04938.html). AMD's XAPP1267 mentions "configuration over the PCIe interface"; `xbmgmt flash` rewrites the shell from the host (https://wiki.cosmos-lab.org/wiki/Tutorials/EdgeComputing/AlveoGettingStarted, SECONDARY). Intel documents Remote System Update. (iii) The V80 runs dual Cortex-A72, dual R5F and a platform management controller (PMC), i.e. software on the card (https://www.amd.com/en/products/adaptive-socs-and-fpgas/versal/hbm-series.html). (iv) AMD-SB-8014 (2025-11-11): 5 CVEs in the Alveo host driver stack, CVSS3.1 up to 8.0 (https://www.amd.com/en/resources/product-security/bulletin/amd-sb-8014.html). (v) Logic-level attacks without physical access have been published: remote power side channel (Zhao & Suh, IEEE S&P 2018, pp. 229-244, https://dblp.dagstuhl.de/rec/conf/sp/ZhaoS18.html) and FPGAhammer (TCHES 2018(3) 44-68, https://tches.iacr.org/index.php/TCHES/article/view/7268). Both assume shared/multi-tenant FPGAs. Starbleed (USENIX Sec'20) broke bitstream encryption through the configuration interface but applies to 7-series/Virtex-6, not V80/U200 (https://news.rub.de/english/press-releases/2020-04-16-it-security-critical-starbleed-vulnerability-fpga-chips-identified). No Starbleed CVE ID found. (vi) A system that "learns normal" from its inputs can be poisoned through those inputs (ANTIDOTE, IMC 2009, https://ptolemy.berkeley.edu/projects/truststc/pubs/725/IMC.2009.pdf). LLM tool outputs are another input channel. |
| 6 | "Never leaves the chip... not stored, not copied, not transmitted" | Thinker p4, p7 | **CONFLICT (internal) and physically implausible** | It "learns what normal looks like" and "relies on [LLM] tools". The Milestone says the demo "ran live over her saved knowledge graph"; she "retains it after the source is removed"; she "learned all 60" objects. On-chip RAM is volatile and finite (V80 752 Mb ≈ 94 MB; U200 35 MB). Anything that persists or is "saved" must live off-chip or on the host, and LLM calls move data off the chip. |
| 7 | "Designed for AI inference acceleration"; "Ultra-high inference throughput" | Overview p2 | **UNSUPPORTED (NOT FOUND) + CONFLICT** | No benchmark: "will be published following pilot validation". The June doc says CADY "does not predict", is "designed rather than trained" and is not an LLM. Market context: AMD positions the V80 for "memory-bound compute" (HPC, FinTech, database), not AI inference. AMD's AI inference card is the V70 (AI Engines) (https://www.amd.com/en/products/accelerators/alveo/v70.html). The FPGA LLM-inference startup Positron is moving to an ASIC (https://www.jonpeddie.com/news/positron-jumps-up-to-the-big-league-investment-circle/, SECONDARY). Microsoft Brainwave, Mipsology Zebra (acquired by AMD 2023, https://www.amd.com/en/blogs/2023/amd-acquires-mipsology-to-deepen-ai-inference-soft.html) and Xilinx's MLPerf entries (2020-21 only found) show that FPGA inference is real but niche. Comps that claim it publish audited numbers (STAC, row 4). |
| 8 | "Upgrade existing data centers. Don't build new ones." (one card, one server) | Overview p1 | **REFUTED as a mechanism** | An accelerator raises data-center capacity only by offloading that data center's own workloads, which have to be ported to it. Microsoft's AccelNet offloaded host networking to FPGA SmartNICs across more than 1M hosts and freed CPU cycles (NSDI'18, https://www.usenix.org/node/211250). A card running ICH's own reasoner adds a new workload plus 20-190 W. No integration API, ported workload or speedup is named. |
| 9 | "Connect directly to other cards through high-speed networking... standard networking, no proprietary equipment" | Thinker p7 | **VERIFIED feasible, but this is AMD's feature, not ICH's** | V80 has 4× QSFP56; U200/U55C have 2× QSFP28. AMD's U55C page: "1000+ node scale... using their existing data center infrastructure and network, with no proprietary hardware required" (https://www.amd.com/en/products/accelerators/alveo/u55c/a-u55c-p00g-pq-g.html). The CADY text is a near-paraphrase. |
| 10 | "No vendor lock-in" | Thinker p7 | **CONFLICT** | "ICH owns and licenses the thinker". Pilots sign IP agreements. The subscription rises from $200 to $500/mo. The bitstream is tied to a vendor toolchain (Vivado or Quartus). |
| 11 | "Same kind of slot a network card or storage controller uses" | Thinker p6 | **Partly true / overstated** | Candidate cards are full-height, ¾-length, dual-slot, 150-225 W. They need PCIe AUX power cables and forced airflow, and AMD lists qualified servers (DS962; DS1013). |
| 12 | "The intelligence IS the chip — built into its physical wiring"; "designed rather than trained" | Thinker p2-3 | **CLAIMED; mischaracterizes FPGAs** | FPGA "wiring" is a volatile configuration file loaded at each power-up. A VU9P bitstream is about 641 Mbit (UG570, https://docs.amd.com/r/en-US/ug570-ultrascale-configuration/Device-Resources-and-Configuration-Bitstream-Lengths, SECONDARY figure). A "learned-pattern count" (Milestone) implies writable state. |
| 13 | "Every step on owned silicon" / "proven live" | Milestone | **CONFLICT (self-admission)** | Same document: "standalone read-only verification over her knowledge graph; reasoning core untouched"; "FPGA reasoning core was untouched throughout". The taxonomy inference shown (is-a inheritance, missing-trait reporting) is standard symbolic/ontology reasoning (e.g. RDFS/OWL subclass entailment) that runs on any CPU. No FPGA is needed or shown. |
| 14 | "Cost over time: falls as she learns" | Thinker p4 | **CLAIMED; CONFLICT with own pricing** | No mechanism is given. The subscription MSRP rises 2.5x ($200 to $500/mo). |
| 15 | Price $50k pilot / $150k MSRP per card (+$200-500/mo) | Overview p1-2 | **Out of market range** (see d) | Derived multiples vs card cost: V80 5.3x / 15.8x; U55C 10.5x / 31.6x; Terasic AGF027 9.1x / 27.3x; used U200 26-33x / 79-100x. |
| 16 | Apply URL www.internationalclearinghouse.com/team-3-1 | Overview p2 | **CONFLICT** (flag for corporate sweep) | The page is "Strategic Partners \| ICH" (Wix), about loyalty-rewards affiliates (Source, HELP Worldwide, WeSave, Pathward), with zero FPGA/CADY content and only a generic contact form. ICH's home page calls ICH "a centralized cloud-based processing platform" (conflicts with "No Cloud"). The ICH leadership page (https://www.internationalclearinghouse.com/team-3) lists **Brad C Hanson, CEO & Director** and **Richard G Stewart Jr., Founder & Chairman**. That matches the Milestone and conflicts with the Thinker/Overview "Richard G. Stewart, CEO". It does not list John Wilson or RJ Stewart. The /spectrum page says ICH "contracted with a small defense company founded in 1994" (cognitive radio / AI), which may be the source of the technology; unnamed. Site © 2024. |

## (d) Comps

| Vendor / product | Hardware | Price | Published benchmark | Tag |
|---|---|---|---|---|
| AMD Alveo V80 (bare) | XCV80, 2.6M LUT | $9,495 MSRP | Vendor specs only | VERIFIED (AMD store) |
| Xelera Silva on Alveo V80 (finance ML inference) | V80 in an HPE DL385 | Licence not public | **STAC-ML audited:** p99 ≤1.95 µs (GBT A/B), 2.88 µs (GBT C), max ≤12.3 µs, >560K inf/s | VERIFIED https://stacresearch.com/news/stac-ml-with-xelera-silva-together-with-amd-alveo-v80-and-an-hpe-proliant-dl385-gen10-plus-v2/ |
| Myrtle.ai VOLLO | Alveo "V80LL" (variant name unverified) | Not public | STAC p99 <2 µs; 50M inf/s on the small model (Oct 2026) | SECONDARY https://runtimewire.com/article/myrtle-ai-vollo-stac-ml-gradient-boosted-tree-inference-records |
| Achronix VectorPath S7t-VG6 | AC7t1500 FPGA | $8,495 MSRP | Vendor ">80 TOPS int8" | VERIFIED (vendor PR, dated) |
| AMD Alveo U55C | VU47P class, HBM | $4,747 | Vendor | VERIFIED |
| Terasic P0728 | Agilex 7 AGFB027 | $5,491 | n/a | VERIFIED (DigiKey) |
| AWS EC2 f2.6xlarge (rent) | 1× VU47P + 24 vCPU host | $1.98/hr ≈ $1,445/mo | n/a | SECONDARY (aggregator) |
| Positron Atlas | Agilex 7 M-series FPGA appliance (LLM) | Not public | Vendor: 70% faster tokens/s vs Hopper; moving to Asimov ASIC | SECONDARY |
| NVIDIA RTX PRO 6000 Blackwell (GPU) | 96 GB GPU | $16,000 (NVIDIA Marketplace, Aug 2026; launched at $8,565) | MLPerf-class | SECONDARY https://techspot.com/news/113460-nvidia-raises-rtx-pro-6000-blackwell-price-staggering.html |
| NVIDIA H200 NVL (GPU) | 141 GB | about $31-32k (reseller) | MLPerf | SECONDARY https://www.trgdatacenters.com/resource/nvidia-h200-price-guide/ |
| NVIDIA Morpheus (+ BlueField DPU) | GPU/DPU anomaly and fraud detection across network, logs and transactions; the closest functional comp to "watch the whole bank" | Framework; DPU price not found | n/a | SECONDARY https://www.securityweek.com/nvidia-unveils-morpheus-cybersecurity-framework |
| BrainChip Akida AKD1000 PCIe | Neuromorphic "brain-like" chip | $499 (2022) | Vendor | SECONDARY https://cnx-software.com/2022/01/21/brainchip-akd1000-pcie-board-ai-inference-and-training-at-the-edge/ |
| GSI Gemini-I APU (Leda-E) | Associative "compute-in-memory" | Not public | Vendor: 1.2 POPs at 80 W | SECONDARY https://www.globenewswire.com/news-release/2024/04/02/2855997/0/en/GSI-Technology-Announces-Production-Release-of-Two-Gemini-I-APU-Servers.html |

**Is $50k-$150k per card plus $200-500/mo in any market's range?**
- **Card price: no.** The highest single-card price found is the H200 NVL at about $31-32k. Even after 2026 GPU price rises (RTX PRO 6000 at $16k), a 2.6M-logic FPGA card is $5-10k new. Only multi-GPU servers or large ASIC-prototyping FPGA systems reach $50k+, and no price for those was found (NOT FOUND).
- **Subscription:** no direct comparison found. $200-500/mo is below the cost of renting an FPGA instance on AWS ($1,445/mo), so the subscription is not the expensive part of the offer.
- **What comps do that CADY does not:** FPGA-inference companies that sell into finance (Xelera, Myrtle) publish third-party-audited latency and throughput. CADY publishes none.

## (e) Could not reach / not established

- **No CADY card photo, part number, PCI ID or board vendor anywhere in the supplied documents.** This is the decisive identifier, and the actual part therefore cannot be pinned down.
- The Milestone "verifiable technical appendix" was not supplied.
- Fetch failures:
  - BittWare datasheets redirect to bittware-molex.com.
  - Mouser and Farnell returned 503.
  - eBay item pages returned 403, so used U200 prices come from search snippets only (SECONDARY).
  - The full STAC reports are members-only.
- Prices and figures not found:
  - Current AMD price for the U200 (AMD says "Contact Sales").
  - Power for the IA-840F and Terasic P0728.
  - An Achronix "2.6M" figure.
  - A per-part fab site for Agilex.
  - A Starbleed CVE ID.
  - Current MLPerf FPGA entries (not queried directly; only 2020-21 entries found).
  - Prices for ASIC-prototyping systems.
- Physical-claim checks are bounded to the candidate parts. A different board (e.g. a low-power custom PCB) would change the power verdict, but not the reconfiguration or latency verdicts.

## (f) Five technical questions a real hardware team answers in minutes (a reseller cannot)

1. **Exact silicon and board.** We need:
   - The FPGA device part number with speed grade, and the card SKU or PCB maker. Is it a stock Alveo, BittWare or Terasic card, or a custom board?
   - The `lspci -nn` vendor:device ID.
   - Whether "2.6M logic units" means LUTs, LEs or system logic cells.

   *What it moves:* the BOM and markup, the "American Silicon" claim, and whether anything here is proprietary.
2. **The utilization and timing report for the shipped bitstream** (Vivado/Quartus: LUT/FF/BRAM/URAM/DSP %, achieved Fmax). We also need card power (xbutil/BMC) at idle and under the pilot workload, plus end-to-end latency p50/p99/max from event arrival on the host to verdict.

   *What it moves:* the 20 W, "ultra-high throughput" and "billionths of a second" claims, and whether the 2.6M logic is even used.
3. **Hardware/software partition.** We need:
   - Which functions run in FPGA fabric versus on the card's Arm cores versus the host CPU (knowledge graph, learning, LLM tool calls).
   - Where the "saved knowledge graph" and learned patterns physically live, and how they persist across a power cycle.
   - Which bytes cross PCIe and the network.
   - Why the Milestone demo left the FPGA core "untouched".

   *What it moves:* "data never leaves the chip" and "every step on owned silicon".
4. **Update and security model.** We need:
   - How the bitstream is loaded and updated at a pilot site (flash, PCIe, JTAG).
   - Whether it is encrypted and authenticated, and who holds the keys (eFUSE/BBRAM).
   - The XRT/AVED/OPAE version, and whether the AMD-SB-8014 CVEs are patched.
   - How learned baselines are protected from poisoning.
   - Any third-party penetration test.

   *What it moves:* "no remote exploit / physical access required", which is the core of the bank pitch.
5. **Evidence of IP and benefit.** We need:
   - Who wrote the RTL/HLS, with commit history.
   - A reproducible benchmark of CADY versus a CPU baseline (e.g. an OWL/Prolog reasoner or a standard anomaly detector) on the same data.
   - For "upgrade existing data centers": which existing workload is offloaded, through what driver/API, and the measured speedup and perf/W.

   *What it moves:* whether there is any proprietary value at all, and the $150k MSRP justification.
