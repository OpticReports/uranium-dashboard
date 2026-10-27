# Clone Robotics: counter-agent verification of `gap-hurdles.md` (rev 1, pre-DD)

Date 2026-10-27. Scope: adversarial re-check of the hurdle ledger, the duty-cycle reconciliation, the bottom-up SAM and the exit map.

**What was read**
- `gap-hurdles.md` in full.
- `factpack.md` in full.
- From the templates: `templates/hurdle-ledger.md` and `templates/rubric.md`, plus `models/exit_curve.py`, which was run but not modified.
- Targeted sections of `sweep-actuation`, `verify-actuation`, `sweep-market`, `verify-market`, `sweep-competition`, `verify-competition` and `verify-vehicle`, plus `vehicle-exit-needed.csv`.

**Primary sources re-opened**
- The Agility S-4/A, read locally. The sha256 `eefcf36c…` is the same file the gap pass used.
- The Mobileye DEF 14A, freshly downloaded (sha256 `9ef06ee9…`).
- The Clone Form C, read locally.
- The FCC fact sheet (DOC-423682A1), read locally.
- The IFR press release and the Wevolver 2023 article, both fetched.

**Web budget:** 3 searches, 2 fetches and 1 EDGAR download. **Prompt-injection log: none.** No fetched page, filing or search result contained text addressed to an AI.

Scripts, so the work is reproducible:
- `cv-hurdles/recheck.py`: every number in the ledger, duty, SAM, W and exit tables.
- `cv-hurdles/p10_alt.py`: the alternative P(≥10x) below.

---

## VERDICT: APPROVED WITH CORRECTIONS

- **Arithmetic is clean. The only slips are a range end ("4–65x" should read 4.3–68x) and the exit-map multiples (correction 2).** Every other number reproduces:
  - chain products 1.30% / 0.48% / 10.5%;
  - rule-2 cross-check 1.03% / 0.38%, and at team 1.5 and 2.5;
  - A marginal 0.2215;
  - duty bars and the 8.96x ratio;
  - Weibull 0.213, which is Γ(4/3)·74^(−1/3);
  - SAM pools $273–338M, $90–525M and $45–180M; Clone $2.9–46M;
  - W 2.175 → 2.025;
  - house-model EV 0.837 / 0.881 / 0.969 / 1.046x, and the tail premiums.
- **Primary facts hold:** the Agility capex and capacity quotes, the Mentee 37.83% and 13.07% shares, IFR 34,200 + 67,800, the Form C IP language, and UBTech (already hash-verified in `verify-competition`).
- **What does not hold is the headline P(≥10x) = 0.7%.**
  - The chain treats every dated, strict ledger hurdle as a *necessary* condition for a 10x outcome. That violates template rule 3 and contradicts the pass's own sector-marks point.
  - It also uses net-10x exit thresholds against a gross-basis panel number.
  - Corrected, the hurdle-implied value is **~1.1% (0.7–2.2%)**. That is still below the panel's 2.5%, so the direction survives and the size of the cut roughly halves.

## SCORE AND FORECAST IMPACT (plain statement)

| item | current | gap pass says | counter-agent | why |
|---|---|---|---|---|
| Market (30) | 3 | "case for 2.5" (W → 2.03) | **hold 3**; re-anchor the rationale on the SAM | The pass's own SAM ($0.4–1.0B/yr, bottom-up, ~2–3x/yr growth) is literally rubric v1.1's anchor 3 ("real market, bottom-up possible but thin"). The 2.5 case rests on Clone's capture share and Chinese incumbency, which Demand and Competition (1.5 / 1.5) already score, so using them here double-counts. |
| Team / Moat / Traction / Competition / Deal | 2 / 2 / 1.5·1.5 / 1.5 / 1.5 | no move (Deal "holds") | **no move** | No new company-level evidence. The Mentee related-party fact does not touch the 1.23x entry comp (correction 6). |
| P(≥10x) | 0.025 | hurdle-implied 0.007 (0.003–0.022) | **log the hurdle-implied value as ~0.011 (0.007–0.022). Recommend the panel move to ~0.015 (−1.0 pp) at S2 unless it names a path.** Never average (rubric §4.5). | See correction 1. Break-even for capped EV = 1.0x is P(≥10x) = **0.0178**. At 0.015, EV is 0.97x; at 0.011, 0.93x. |
| P(<1x) | 0.85 | consistent | **no move** (0.85–0.87 defensible) | At realistic dilution the modal strategic sale returns ≤2.1x and often <1x (correction 2). That is mild upward pressure only. |
| P(next priced round ≤24mo) | 0.45 | 0.39 (0.34–0.44) | **no move; log 0.39 separately once its derivation is shown** | It sits inside the panel's own raw spread (0.38–0.45) and the red team's 0.40. E3(ii)'s derivation is not in the file, and P(A \| neither) = 0.10 is an untested assumption. |
| EV net (capped) | 1.08x | 0.88x | **~0.93x (0.88–1.03x) on the hurdle basis** | Same house model. The verdict (PASS-REVISIT) is unchanged either way. |

---

## CORRECTIONS (ranked by severity)

### 1. SERIOUS: P(≥10x) is structurally biased low

The chain conditions a 10x outcome on all eight dated hurdles passing. Four of the eight steps are not necessary for that outcome:

- **(a) Basis mismatch.** `exit_curve.py` tilts on the GROSS multiple (`in_hi = x >= 10.0`).
  - At the panel's 0.025, P(net ≥10x) is only 0.0214 (re-run).
  - The pass priced "P(exit ≥$7.3–12.7B)", which are the *net*-10x thresholds (fact pack §7). Gross-10x needs only ~$5.7B / $10B at 65 / 80% dilution.
  - Book-level note for R2: rubric §3 says "P(≥10x net)", but the model and fact pack §8.3 treat the panel number as gross. The basis must be stated.
- **(b) Template rule 3 is violated.** "E failures cost time and money first — model E misses as delay/dilution before death" (`templates/hurdle-ledger.md`). The chain instead treats E1 (≥100 units with capex within 2x by 2028-12-31) and E2 (hires in seat ≥18 months by 2028-12-31) as absorbing.
- **(c) V2 (≥$10M ARR) and E1 are not necessary for a sector exit.** The pass itself says "Sector marks are not revenue-based anyway: Agility's $2.5B was struck on $1.78M of sales". 1X is at ~$6B in talks with no units shipped (`verify-competition` row 16). The only allowance for these paths is the 0.2–0.5% "windfall".
- **(d) V1a is modelled as absorbing at ≥2M cycles**, yet §(b) point 3 of the same file says a consumable-fibre model "can change the bar".

**Re-computation (ANALYST, `cv-hurdles/p10_alt.py`):**

| case | P(≥10x) | EV (capped) |
|---|---|---|
| Pass replica | 0.66% | 0.88x |
| Counter central: half of E1/E2 misses recover; gross thresholds (P\|humanoid 0.55, P\|torso 0.20); 3% pre-revenue-mark branch; windfall 0.3% | **1.12%** | 0.93x |
| Low | 0.71% | — |
| High | 1.82% | — |

The pass's own optimistic set (2.17%) is kept as the upper edge.

**Conclusion:** the direction (below 2.5%) is robust, and the cut is about 1.4 pp, not 1.8 pp.

### 2. MODERATE: the exit-map return arithmetic is wrong

**The pass says:**
- (d) Net read: "strategic sale at $0.3–1B … At 50–80% dilution that is ~1–3.5x net".
- Executive read #8: "$0.15–1B, which is 0.5–3.5x net".
- The humanoid-OEM row: "1–3.5x net".

**What `vehicle-exit-needed.csv` gives** (linear interpolation between thresholds; it reproduces the fact pack's Agility $2.5B line exactly: 2.13 / 3.58 / 5.03x):

| exit | 30% dilution | 50% | 65% | 80% |
|---|---|---|---|---|
| $0.15B | 0.46x | 0.33x | 0.23x | 0.13x |
| $0.30B | 1.01x | 0.66x | 0.46x | 0.27x |
| $1.0B | 2.90x | 2.13x | 1.55x | 0.88x |

**Correct statement:** at 50–80% dilution, $0.3–1B returns **0.27–2.1x net**. "~1–2.9x" holds only for an early sale at ~30% dilution, straight after the A. 3.5x needs ≥$1.22B even at 30% dilution.

### 3. MODERATE: the cycle ratings are labelled "optimistic η" one-sidedly, and the pressure claim is unsupported

- **The 650K figure.** The source the pass cites says **"Over 650 000 cycles with 1kg load"** (Wevolver, Samir Jaber, 2023-01-17: https://wevolver.com/article/could-this-lifelike-robotic-hand-be-the-start-of-a-humanoid-future).
  - That is a lower bound, at the fibre's headline maximum load (fact pack §4: "1 kg from a 3 g fibre").
  - It comes from a system whose pump is rated "400L/h at 10 bar" (≈1.0 MPa, same article).
- **The pressure claim.** The test pressure is **UNKNOWN**, so "neither is at Clone's 0.69–1.0 MPa rating" is not established for the 650K figure.
- **The >1M figure.** The Kobayashi protocol was **capped at 1M cycles**, which makes it a censored floor (`verify-actuation` row 8: https://t2r2.star.titech.ac.jp/rrws/file/CTT100925838/ATD100000413/).
- **A logged correction was reversed.** The pass overturns `verify-actuation` row 10 ("If 650k is a B10 or a censored test cap … first failure comes later") without addressing it.
- **The net bias is ambiguous.** Censoring and maximum load push life up; bending and unknown pressure push it down.
- **The V1a grade is overstated.** "2x the best public figure" overstates the gap, because the best figure is a floor. A V1a p_marg of 0.30–0.40 is defensible (ANALYST).
- **The duty arithmetic itself is correct.**

### 4. MINOR: smaller fixes to the E1 box, Mentee, Market and reproducibility

**E1 box (Agility analogue).** The figures are VERIFIED in the S-4/A: purchases of PP&E $3.90M (FY2024), $2.55M (FY2025) and $2.32M (H1 2026); "approximately $8 million total between 2026 and 2028"; "designed production capacity of up to 10,000 robots"; inventories $12.87M; PP&E net $15.93M. The framing needs two fixes:
- **The capex is whole-company, not RoboFab's build cost.** That cost is not isolated, and the factory predates FY2024. Operating-lease right-of-use assets also rose by $11.5M in H1 2026, so facility cost sits partly in leases, not capex. "Same order of magnitude as Agility's" is unsupported.
- **"$0 robot sales" is a business-model artifact, not zero output.** Agility moved **$10.08M (FY2025) and $10.52M (H1 2026)** of internally made robots from inventory into its deployed RaaS fleet (S-4/A supplemental non-cash disclosures, same file). The conclusion that nameplate capacity is not output still stands, because output is tens of robots, not thousands.

**Mentee.** The 37.83% (~$341M) and 13.07% (~$118M) shares are VERIFIED (https://www.sec.gov/Archives/edgar/data/1910139/000110465926048118/tm261530-1_def14a.htm). Three fixes:
- **(a) The logged CONFLICT is not one.** "Paid evenly in cash and … Class A common stock" refers to *each executive's* consideration, so it does not contradict the deal-level $612M cash.
- **(b) A governance fact was omitted.** The same filing says a "Strategy Committee consisting of four disinterested directors (two of whom were independent)" evaluated the deal. Related-party status does not establish which way the price was biased, so calling it "a ceiling" is ANALYST.
- **(c) The Deal-score inference is a non sequitur.** The fact pack's "1.23x Mentee" compares against Mentee's **$162M Mar-2025 private mark** (`verify-competition` row 16), not the $900M sale. The related-party fact weakens only the $900M as an *exit* comp.

**Market 2.5.** See the score table above. The W of 2.025 is correct arithmetic, but W is a tiebreaker only (rubric §4.4). Note too that the house weights differ from rubric v1.1's Seed/A vector.

**The bands are not reproducible.** The pass says the "Pessimistic and optimistic sets … are in the companion python lines (reproducible)". No such lines exist, in the file or the scratchpad.
- This affects the headline bands 0.42–4.23%, 0.3–2.2%, EV 0.84–1.05x and P(round) 0.34–0.44.
- Shifting every p_cond by ±0.075 gives 0.39% / 3.65%, which is plausible.
- E3(ii) = 0.39 has no derivation shown. Show both before anything goes into `ledger.csv`.

**N = 74 fibres "(2 hands)" is unsourced.** `sweep-actuation` used 74 as an illustration and states that "Clone's fibre count per hand … is UNKNOWN". Tag it ANALYST.

### 5. NOTES: record and move on

- "$200M is 4–65x the band's revenue" should read **4.3–68x**.
- Executive read #5 says "650K is enough only for research labs and the home", but the pass's own table gives line-rate automotive at 1 contraction per cycle 3.03 years.
- The acquirer-map "~0.25 (red team)" acqui-hire is *conditional* on the runway-ends branch: the red team's 0.30 / 0.25 / 0.45 sum to 1. Unconditionally it is ~0.2.
- **Upgrade (Sanctuary):** Friedmann as CEO (June 2026) and "most recently CEO and Chairman of Carbon Engineering" are now VERIFIED first-party (https://sanctuary.ai/news/daniel-friedmann-appointed-ceo-of-sanctuary-ai/). The $1.1B Occidental sale is SECONDARY (https://thelogic.co/?p=2136150).
- **New (Sanctuary):** a July 2026 rebrand to a hardware-agnostic "Physical AI" platform (single third-party blog, low confidence: https://runtimewire.com/article/sanctuary-ai-physical-ai-factory-arms-humanoids).
- **IFR:** US 34,200 and EU 67,800 are VERIFIED (press release dated 2025-09-25: https://ifr.org/ifr-press-releases/news/global-robot-demand-in-factories-doubles-over-10-years). The release gives no cobot share. ~12% for 2024 is SECONDARY; 10.5% for 2023 is IFR's own figure (search summary).
- **SoftBank–ABB close:** NOT FOUND after a second search. The results show only the October 2025 announcement and a "mid-to-late 2026" expected close (https://www.techrepublic.com/article/news-softbank-acquires-abb-robotics/).
- **V3:** the FCC primary defines covered devices as "mobile robots, such as humanoids and quadrupeds" (DOC-423682A1, 2026-07-28). The "fixed/nonmobile" exclusion is Cooley only (SECONDARY), so the "such as humanoids" wording is a residual counsel risk. The p of 0.80 is ANALYST.
- **Research pool:** it uses Counterpoint's >22,000, whereas SAG's 19,100 (CONFLICT) gives a low end of ~$0.24B. RMB 167.6K ≈ $23.3K at 7.2 RMB/$; "$25K" needs ~6.7.

## NOT SEARCHED (carried; this pass did not close them)

- The MTM or bench grasp-rate standard. 8 grasps/min stays ANALYST. An economic bench robot likely runs faster, which would make the bar harder.
- The research-buyer geography and the high-DoF share filters.
- Linkerbot's unit mix.
- Fluid-power M&A prices.
- 1X's status after 2026-08-27.
- Clone's roster.
- Unitree "Dex5-S $6,350": the pass tags it VERIFIED; this pass did not re-check it.

## PENDING DD QUESTIONS (delta to the gap pass's list)

- **P2:** state whether "650K" and "100,000(?)" are a mean, a B10 or a censored cap, at what MPa, and whether bent. This replaces "test logs" as the sharpest ask.
- **P3 (internal):** fix the basis of P(≥10x) (gross vs net) in rubric §3 against `exit_curve.py` at R2.
