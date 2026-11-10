# IC record — Vernius Systems

Protocol: `templates/ic-process.md` (v1.2 — full report at intake).
Ninth vehicle in the ledger.

---

## S1 · INTAKE — 2026-09-10

### Blind prior — optional, not blocking

Not supplied. Casey's framing was "this is an early drone company i am looking
at," with three explicit asks: DD questions weighted to **ability to execute**,
**realistic demand numbers**, and a deep dive onto the dashboard.

### The ask

| | |
|---|---|
| Round | **UNKNOWN — no ask slide in the deck** |
| Valuation | **UNKNOWN** |
| Instrument | **UNKNOWN** |
| Use of funds | **UNKNOWN** |
| Close date | **UNKNOWN** |
| Known capital | YC standard deal ($125K post-money SAFE @ 7% + $375K uncapped MFN); Dealroom records a $125K YC micro-seed, June 2026 [SECONDARY] |
| Filing of record | **None — no SEC Form D exists for Vernius under any form type or date** |
| Context | **YC Summer 2026 Demo Day was 2026-09-10 — the day this deck arrived** |

**Per the house rule (missing key inputs: ask, don't analyze around them),
deal & price is NOT SCORED.** W is computed ex-price over 95 points.

### Documents

| document | supplied | read | notes |
|---|---|---|---|
| 8-slide seed deck (`Archive_2.zip`) | yes | **YES — all 8 slides, images included** | Oligo raster lesson applied; every slide rendered and visually read |
| `x.com/Arthur_NC_/status/2091903458748375240` | link only | **NO — HTTP 402 through the proxy; mirrors failed** | Logged NOT READ same day per standing rule. Contents not guessed. Casey can paste the text. |
| Terms / SAFE / cap table | **not supplied** | — | P1 |
| Any radar performance data | **not supplied** | — | The deck's only radar parameter is "24 GHz" |
| LOI documents | **not supplied** | — | P1; no counterparty named anywhere |

### Pipeline run

**23 agents, 0 errors, 2.6M tokens, 378 tool calls:** 10 evidence sweeps
(founders · YC/funding · deck-claims audit · radar physics · competition ·
Ukraine demand · procurement base rates · advisors · AI-hardware-automation ·
public footprint) → 2 domain-level adversarial counter-agents (technical /
commercial, tasked with cross-sweep contradictions) → 3 independent demand
models + reconciliation → 5-scorer panel → red team → completeness critic.

A first-principles radar link budget and demand arithmetic
(`independent-check-2026-09-10.md`) were written **before** the fleet reported
and used to audit it. Two independent derivations agreed on ~1 km detection
range; the fleet corrected our sceptical prior on the 24 GHz band choice.

### Output

Full report: `factpack.md` (provenance-tagged, with the ranked pending-DD
ledger). Published to /deals same day per v1.2.

**Headline:** W **2.00** ex-price — the lowest this ledger has logged.
Panel 4× PASS-REVISIT, 1× CONDITIONAL; red team PASS-REVISIT — **the red team
is no more negative on verdict than the panel**, which normally means the
evidence rather than the framing is doing the work. Forecasts (panel median):
P(next priced round ≤24mo) 0.55 · P(<1x) 0.85 · P(≥10x) 0.05.

**The three findings that carry the file:**
1. **"Ukraine's 100,000 interceptors produced every month" is REFUTED** — it is
   Ukraine's *annual* 2025 output (NSDC, 2026-01-26), off by ~12x. The 50,000
   units/month ramp target appears to have been sized off it.
2. **The $580M LOI book prices at ~4% of face** — 95/96/95% haircuts from three
   unrelated methods. Realistic demand: **~$4.8M (2027), $11.4M (2028), $15.0M
   (2029)** base, ~0.8% of the deck's own book.
3. **The binding operational constraint operators actually name is SPEED, not
   sensing** — and nobody has asked what the module's mass and drag do to the
   host's top speed.

### Process notes

- **Book flag:** fifth deep-tech exposure in the live book, and the **first
  defense/munitions** position — no direct sector collision, but it is the
  second consecutive deal (after Nutation) whose thesis is *"collect
  battlefield/proprietary data via a hardware wedge."* One line in R1.
- **Two of our own methodological errors were caught by the critic and
  corrected in the factpack** ("no patents found" ≠ no IP for a 2026-founded
  company; absence of public confirmation of cleared work is uninformative).
- **First prompt-injection attempt logged in this ledger** — an embedded
  instruction in a Dealroom search result, correctly treated as data.

---

## THE GAP — chase the data

28 ranked DD questions shipped with the report (9× P1, 12× P2, 7× P3), weighted
to ability-to-execute per Casey's brief. 60-day clocks run from 2026-09-10.

**The three that decide it:** what happened to the 45 units already in the field ·
the measured shots-per-kill delta with and without the seeker · the terms.

## S2 · THE CASE — target T+3

*Not yet run.*

## S3 · THE DECISION — target T+10

*Not yet run.* No verdict may be issued before S3, and none can be issued at
any time without terms.

---

## Track

☐ HELD  ☑ LIVE  ☐ PASSED
