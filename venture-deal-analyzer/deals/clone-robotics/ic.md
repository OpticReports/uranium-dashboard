# IC record — Clone Robotics

Protocol: `templates/ic-process.md` (v1.2 — full report at intake).
Tenth vehicle in the ledger; second via Delta4 Capital (after Quaise).

---

## S1 · INTAKE — 2026-10-27

### Blind prior — optional, not blocking

Not supplied. Casey's framing: "run analysis on this company as potential
investment, exploring where it can win the market and how it honestly shapes up
to leading competition. Maybe $50k check." And his crux, verbatim: *"for a robot
to be full autonomous the hand must have sensor feedback to know how hard it's
gripping objects etc, but these guys, I believe don't have that in their system,
is that true?"* His stated prior is sceptical of the method ("struggling to see
how this method ultimately wins").

### The ask

| | |
|---|---|
| Round | Pre-Series A bridge |
| Valuation | **$200M post-money** (Casey, 2026-10-27) |
| Check | ~$50K via Delta4 Capital SPV |
| Fees | ~2% one-time + 20% carry + pro-rata SPV costs (illegible fragment; Delta4's Form Ds show ~5%) |
| Raise / committed / instrument | **UNREAD** |
| Close | "next week" per the memo |
| Source | Alex Golding, Delta4 Capital — the Quaise sponsor |

### Documents

| document | supplied | read | notes |
|---|---|---|---|
| Delta4 memo (DocSend/Dropbox PDF) | screenshot only | **PARTLY — fragments** | 310 px wide; numbers illegible; we misread $200M as "$3?0M" — fragments are leads only (`source/legible-fragments.md`) |
| Clone deck | screenshot only | **NO** | 121 px wide |
| Valuation | Casey, in chat | YES | $200M post |

Logged the same day per the standing rule; the native PDF is P1 #1.

### Pipeline run

Two workflows. **Intake: 13 agents, 0 errors, 2.54M tokens, 995 tool calls** —
6 evidence sweeps (tactile crux · company · competition · actuation · market ·
vehicle), each with an adversarial counter-agent; the tactile crux got two
independent verifiers (evidence lens and engineering steelman). All seven
returned APPROVED WITH CORRECTIONS; 92 corrections applied. **Scoring: 5-scorer
panel + red team + completeness critic** on the corrected fact pack (results in
`factpack.md` §8).

### Output

`factpack.md` (provenance-tagged, ranked DD ledger, tripwires) and
`exhibits.html` (four exhibits: the crux, force vs touch, muscle life, return
math; artifact https://claude.ai/artifact/XkMqzPuCNqC5TpaqWioK4a). Dashboard card,
tiles, ledger table row and mirror updated the same day; `ledger.csv` row logged.

**Headline (rev 1.1, pre-DD):** W **2.18** (band 1.92–2.28) — second-lowest in the
ledger. Panel **5× PASS-REVISIT**, red team PASS-REVISIT; IQR 0 on six of seven
dimensions (the tightest panel logged — an S2 flag in itself). Forecasts, all
seed-anchored: P(priced round ≤24mo) **0.45** · P(<1x) **0.85** · P(≥10x) **0.025**
(red team 0.40 / 0.86 / 0.025). House EV **1.08x** net capped@20x (red 1.05x).
**Separate forecast, never averaged:** the hurdle ledger implies P(≥10x) ≈ 0.011 →
EV ≈ 0.93x. Gates: G1 pending (at risk), G2 pass, G3 at risk, **G4 pending — if the
instrument and SPV documents stay undisclosed after request, the verdict is
automatically "conditional: pass until disclosed".**

**Rev 1.1 finding (gap pass):** the memo's licence/acquisition counterparty reads as
**Adaract Technologies** (Reno, NV; founder Joseph Hill; 3 granted US McKibben-muscle
patents). If confirmed, Clone's "patented" rests on licensed outside IP, bought after
its own muscle inventor left — and the licence becomes a US freedom-to-operate
dependency.

**The answer to Casey's question:** partly true. No touch sensing, by published
design ("only proprioceptive and visual feedback"). But there is a grip-force
channel: 320 muscle-pressure sensors in the Alpha spec, and the leaders treat
actuator proprioception as their primary force channel. The bigger gap is that
**no autonomous grasp has ever been shown**, shipped hardware carries far fewer
sensors than the spec, and there are no wrist or palm cameras.

**The three findings that carry the file:**
1. **Muscle life at working pressure is the binding technical risk** — industrial
   duty needs 1–4M cycles a year per muscle; the only public figures are 650K
   (press) and >1M on air at 0.3 MPa, and at ~0.7 MPa bent muscles failed in the
   literature.
2. **The cost moat is overstated** — the CEO's own "<$20K" is an at-scale target,
   about level with China's projected 2030 BOM; "deny rivals scale" is refuted by
   Unitree and AgiBot volumes.
3. **The vehicle repeats Quaise** — Delta4 has filed nothing since May; the Quaise
   SPV shows no sign of having invested; no evidence of a Clone allocation.

### Rev 2 — same day: the memo became legible

After a direct ask, Casey supplied memo pages 1–5 and 7 at full resolution (page 6 and
the deck still missing). **Process failure owned:** at intake the unreadable memo was
flagged but the pipeline ran anyway and the ask was buried in progress updates,
against the standing rule. A fourth workflow (3 passes, each counter-checked, 61
corrections) verified what the pages changed: `factpack.md` §12.

**Material changes:** terms now read ($9M bridge, $6.5M committed, close Nov 3; $2.5M
cash, $750–900K/month burn, so 2.8–3.3 months standalone); a CLAIMED $150M Mar-2025
mark (→ 1.33x if documented) alongside a financing table the Form C refutes; Adaract
confirmed as a related-party $4M acquisition; Torso 4 muscles rated 100K cycles; first
VLA Q4 2028 on Clone's own roadmap; 0/7 prospects confirmed, one related-party and one
refuted label; the CEO's public $20K price vs the deck's $178K list; the FCC rule
excludes the stationary industrial torso. **Scores and forecasts not yet re-run — held
for page 6.** Privacy breach logged (Casey's email in 6 EDGAR request headers).

---

## THE GAP — chase the data

25 ranked DD questions (10× P1, 10× P2, 5× P3), split sponsor/company. 60-day
clocks run from the day they ship. **The three that decide it:** an autonomous
Torso 4 grasp demo with logged force · cycle life at working pressure · a
countersigned allocation and the SPV documents (plus an extension past "next week").

## S2 · THE CASE — target T+3

*Not yet run.*

## S3 · THE DECISION — target T+10

*Not yet run.* The bridge "closes next week" — inside the S2/S3 window. Per the
guard table, a close date inside the window is itself a flag; the ask is an
extension, not a faster process.

---

## Track

☐ HELD  ☑ LIVE  ☐ PASSED
