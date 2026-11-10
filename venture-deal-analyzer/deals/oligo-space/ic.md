# IC record — Oligo Space

Protocol: `templates/ic-process.md` (v1.1). Seventh vehicle in the
ledger. **First deal run through the IC process from S1.**

---

## S1 · INTAKE — 2026-08-25

### Blind prior — OPTIONAL, not blocking (process rev 1.2)

- Not supplied. Casey corrected the process at this deal (2026-08-25):
  S1 delivers the full report at intake; the blind prior is a
  30-second optional step, never a gate. Slot stays open until the
  report is opened, then closes: not-given, by design.

> Process note, recorded once: an unanchored prior can only be captured
> before analysis is read; if unused, the S3 prior-vs-panel comparison
> has no datapoint for this deal. Casey's call, cleanly made.

### The ask

| | |
|---|---|
| Round | $10,000,000 |
| Pre/post | **$100M — stated as "valuation", pre vs POST not specified** |
| Last round | $7M raised to date; last strategic round at $50M valuation |
| Step-up | 2x on the headline, over an unstated interval |
| Instrument | **UNKNOWN** — direct equity vs SPV not stated |
| Terms [LP-STATED] | "L1, 10/0/10" — **notation not defined; do not guess** |
| Close date | **UNKNOWN — not stated in the memo or the summary** |
| Source | LP-supplied; who is bringing it, and their economics, UNKNOWN |

### Documents

| document | supplied | read | notes |
|---|---|---|---|
| `Oligo_Memo.pdf` (`Oligo_Space_IC_Memo_V1`) | yes | **YES — in full** | 4pp, Google Docs export, text layer complete, nothing gated |
| LP summary text (in chat) | yes | yes | Contains material claims **absent from the PDF** — see below |
| Deck / data room | **not supplied** | — | none referenced |
| Cap table | **not supplied** | — | required |
| Customer contracts / LOIs | **not supplied** | — | required |
| Launch services agreement | **not supplied** | — | required |
| Financials, burn, runway | **not supplied** | — | required |
| SPV / LPA docs for "L1, 10/0/10" | **not supplied** | — | required |

**Nothing was unreadable.** The memo parsed cleanly and in full; no
silent gaps from this batch.

### CAPTURE — where the LP summary and the memo PDF diverge

Recorded as fact, not as judgement. The summary contains claims the memo
does not, which means a second source exists that has not been supplied.

**CORRECTED 2026-08-25 (verification §0): rows 1–2 of the original
table were WRONG.** The memo's page 3 is a full-page raster image that
the text extraction silently dropped — `pdfimages` shows one 2048×1045
image, and the text layer contains zero occurrences of "Shapiro". The
slide names NINE people including **Andrew Shapiro, PhD — CHIEF
TECHNOLOGIST — "…Division Chief Technologist… Former Proteus Space
Co-Founder/CTO"**, under the header "70+ YRS OF FLIGHT EXPERIENCE / 25+
FLAGSHIP MISSIONS", with Cal/UCLA/Caltech/NASA/JPL/USAF logos. So the
LP's summary items 1–2 came FROM the memo, not from a missing second
source. **The original claim that "the Team section names only Jacob
Rodriguez" was an artifact of reading a document without reading its
images — exactly the failure mode the standing rule names.** The
corrected divergence table:

| # | LP summary says | The memo PDF says (full read incl. p.3 image) |
|---|---|---|
| 1 | "former NASA JPL Chief Technologist" | Slide is MORE precise: "Manager of Technology Formulation and **Division** Chief Technologist" — the dropped word is the finding, and it is Oligo's own website (not the LP) that drops it |
| 2 | team from "NASA JPL, Caltech, UCLA, and defense programs" | Supported by the slide header + logos; NOTE Oligo's own job postings instead say "ex-MIT, Harvard, and NASA JPL" (Caltech 0, UCLA 0 across all 15) |
| 3 | "**signed** customers … yielding potential revenue" | "**Acquired** customers … **possible** revenue" — "signed" remains the one real upgrade; the LP kept "potential" |
| 4 | "an **MIT dropout**" | "studied at MIT" — and "MIT dropout" ALSO appears in the memo's own highlights (line 21); degree conferral unresolved either way |
| 5 | "Terms: L1, 10/0/10" | **Genuinely absent from the memo, in text AND image (re-verified).** This one still implies an unsupplied source. |

### UNKNOWN — REQUIRED (ask, do not analyze around)

Ordered by how much each would move the decision.

1. **Is the $100M pre or post?** On a $10M raise that is the difference
   between buying 9.1% and 10.0% — and it determines every multiple.
2. **What does "L1, 10/0/10" mean?** Layer/tier, and the three numbers —
   carry / management / something. Fees compound directly into the exit
   multiple and this is currently undecodable. Supply the SPV or LPA.
3. **The CHIMERA customers: named, and signed what?** Binding purchase
   agreement, LOI, or MOU? "Acquired" and "possible revenue" are not
   contract language. What is the *contracted* value versus the
   $15M–$37M "possible" range, and why is the range 2.5x wide? Is
   either customer an affiliate or an investor?
4. **Andrew Shapiro** — is he actually at Oligo, in what role, full or
   part time, and what was his *actual* title at JPL?
5. **The launch**: which provider, what was paid, is it on a published
   manifest, and is the slot transferable/refundable?
6. **Has Oligo ever built or flown a spacecraft?** The memo claims
   *capability* to produce 10+/yr. Any delivered hardware, any flight
   heritage, any qualified structure?
7. **Cash, burn, runway**, and what the $10M funds to. $7M raised
   against a 14,000 sq ft build-out, TVAC/vibe/cleanroom capital
   equipment, payroll, and a paid launch slot is a lot of uses.
8. **Cap table and the $50M round**: date, lead, instrument, and
   whether Lux led or merely participated. Alumni Ventures in the same
   line implies a mixed institutional/retail syndicate — which is it?
9. **Zenith**: any demonstrable artifact — demo, paper, patent, or
   customer using it — or is it roadmap?
10. **Who is bringing this deal, and what are their economics?**

### Process notes

- **Book-check flag, logged at intake:** this is the ledger's second
  satellite/EO-adjacent name. Matter Intelligence was passed at ask,
  and Bellwether (held twice) is in the same broad sector. Sector
  concentration is now a live R1 item, not a hypothetical.
- Verification workflow launched at intake: six independent sweeps
  (team, corporate/funding, commercial traction, market-stat audit,
  competition/comps, technical feasibility), each with an adversarial
  counter-agent pass. Under rev 1.2 the output feeds the FULL intake
  report (panel + red team + EV + exit odds) published to /deals as
  soon as it completes — no withholding.
- **Intake card published to /deals same day** (process step S1.5,
  added at Casey's direction 2026-08-25): captured facts and process
  state only, no scores/odds/verdict until S3.
- **No opinion is recorded in S1.** Per protocol.

---

## S2 · THE CASE — scheduled T+3 (2026-08-28)

*Not yet run. Dialogue in rounds; concessions logged live; output is the
cruxes.*

---

## S3 · THE DECISION — scheduled T+10 (2026-09-04)

*Not yet run.*

---

## Track

☐ HELD  ☑ LIVE  ☐ PASSED
