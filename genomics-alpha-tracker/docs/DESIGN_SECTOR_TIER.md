# Design + pre-registration: a watched genomics SECTOR tier

_Status: DESIGN — no code until Casey approves this document. Pre-registered
measurements below are run before the build decision, and their results are
appended, never edited in._

## The ask

Casey, 2026-10-05: "we should be looking at the entire sector of genomics
right? not just a small list."

## What exists today, and why it is not that

| layer | what it is | size |
|---|---|---|
| Traded core | `watchlist.yaml` + promoted names: full ingestion (prices, analyst, social, insiders, short interest, science, news), scoring, flags, calls | 34 |
| Discovery funnel | daily Nasdaq census + rotating CT.gov sweep; a name is SEEN only if it trips a lane (10% day at the close, or a near phase-3 / phase-2+keyword on its 1-in-10 rotation day) | 1,068 health care + 23 supplement scanned; ~80 ever queued |

Everything that does not trip a lane is discarded unseen. Nothing persists the
census, nothing lists the sector, and "genomics" is a 17-word substring list.
The 2026-10-05 audit found Vertex ($128B, Casgevy co-owner) invisible for that
reason. The recall fixes merged alongside this doc narrow the funnel's misses;
they do not turn a funnel into a watched sector.

## Proposal: three tiers

**Tier 0 — Census (all ~1,100 names).** Persist the daily screener snapshot
(symbol, name, sector, industry, market cap, last, % change, date) instead of
discarding it. Cost: the two calls the sweep already makes. Gives a queryable
history of every name's daily move and size, which Tier 1 and the
measurements below need.

**Tier 1 — Genomics sector (target 150-300 names).** A classified, watched
set, visible on its own Sector screen, ranked daily. No calls are generated
from it.

- *Classification* (pre-registered rule, re-run weekly, every decision logged
  with its evidence): a census name is IN if any of —
  (a) a genomics keyword in the company name;
  (b) on CT.gov, a GENETIC intervention, or a genomics keyword in a trial
      title, or a genomics-modality universe partner (the recall-fix signals);
  (c) industry "Biotechnology: Laboratory Analytical Instruments" or a
      named tools/diagnostics allow-list (TMO, DHR, TEM, EXAS-successor and
      similar names the screener files elsewhere);
  (d) a manual include list; and NOT on a manual exclude list.
  Market cap ≥ $300M, as the funnel.
- *Watched with data we already pay for:* daily price/volume from the Tier 0
  snapshot (no per-name FMP call), relative strength vs XBI, a 10% / 20%
  move log, catalyst proximity from a weekly CT.gov refresh (≈45 queries a
  day at 300 names), and a weekly runway check from FMP fundamentals
  (≈3 calls per name per week; the provider is limited to 600 calls/minute).
- *Sector screen:* every Tier 1 name, sortable by move, relative strength,
  catalyst date, size, modality; why each name is in (its classification
  evidence); and a one-click Promote into Tier 2 that runs through the
  existing discovery gates and weekly cap.

**Tier 2 — Traded core (today's 34, growing slowly).** Unchanged: full
ingestion, scoring, flags, calls. Promotion from Tier 1 uses the existing
discovery gates, now fed by Tier 1 evidence instead of a single-day trigger.

What this deliberately does NOT do: generate calls on Tier 1 names (no
analyst, social, insider or short-interest history exists for them, and the
call engine's evidence was built on the full stack), or widen the call
engine's universe without a separate pre-registered study.

## Pre-registered measurements (run BEFORE the build decision)

1. **Retrospective recall.** Take every single-day move ≥ 20% between
   2025-10-01 and 2026-09-30 in names that the Tier 1 rule classifies as
   genomics TODAY (FMP daily history, ~1 call per name). For each move, was
   the name in (i) the traded core, (ii) the discovery queue, (iii) Tier 1,
   on the day before the move? The funnel's column (ii) can only be
   estimated (queue history lives in the production database); report it
   as an estimate with its method. Hindsight caveat stated: the Tier 1 rule
   is applied with today's classification.
2. **Classification precision.** A counter-agent who did not write the rule
   labels a random 50 Tier 1 names genomics / not genomics against the
   mandate below; report the share and every disagreement.
3. **Cost.** Added API calls per day by provider, added scoring runtime, and
   database growth, measured on a dry run over one week of census data.
4. **The two known misses.** On their miss dates, would MRNA (2026-08-19)
   and VRTX (2026-10-05) have been in Tier 1?

**Decision rule (frozen).** Build Tier 1 if measurement 1 shows Tier 1
recall of ≥ 20% moves at least 20 percentage points above the traded core's,
AND measurement 2 shows precision ≥ 80%, AND measurement 3 fits the existing
provider budgets with headroom. Otherwise report why and stop. Tier 0 is
cheap enough to ship regardless, because the measurements themselves need it.

## Decisions needed from Casey (P1, decision-gating)

| P | question | what it moves |
|---|---|---|
| P1 | **The mandate.** Strict genomics (gene editing, gene therapy, RNA/mRNA, sequencing and tools, genomic diagnostics) or genetic medicines broadly, including large companies with a genomics franchise (Vertex)? Kiniksa is out under both. | the classification rule and measurement 2's labels |
| P1 | Should Tier 1 names ever generate calls directly, or only after promotion to the core? This design says only after promotion. | scope of the build |
| P2 | Tools names the screener files outside health care (TMO, DHR, TEM): in the sector or not? | the allow-list in rule (c) |
| P3 | Target size: closer to 150 (tight) or 300 (broad)? | thresholds, cost |

## Counter-agent verdict

_Appended when the design review reports._
