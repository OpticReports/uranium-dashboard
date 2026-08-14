# knowledge/ — curated, cited base rates for the Analyst Chat

These Markdown notes are the chat analyst's reference library. The chat agent
reads them on demand via the `read_knowledge` tool so its probability and
expected-value reasoning is anchored to real, sourced base rates instead of
unmoored priors.

## Files

- `clinical_base_rates.md` — clinical-trial success probabilities by phase,
  indication, and modality (gene editing, gene therapy, RNAi/ASO, mRNA, cell
  therapy, diagnostics); what moves the odds.
- `fda_catalyst_stats.md` — FDA process (PDUFA, AdComm, CRL, review pathways),
  approval/concordance base rates, price behavior around catalysts, and the
  finance-into-strength / dilution pattern.
- `market_structure.md` — short interest & squeezes, insider-buying signal,
  analyst-revision drift, liquidity/float/slippage, sector beta & relative
  strength, volatility-based stops.

## Rules for these notes

1. **Every quantitative claim carries an inline source.** No uncited numbers.
2. **They are PRIORS, not verdicts.** The agent is instructed to anchor on the
   base rate, then adjust for the specific name and say how.
3. **Files are the source of truth** — git-versioned, human-editable. The
   loader (`app/chat/knowledge.py`) indexes them into sections and serves small
   relevant slices; it never dumps the whole corpus (token discipline).
4. **Refresh, don't accumulate cruft.** The periodic research pass updates the
   figures and their "Last researched" dates; stale numbers get replaced, not
   piled on.

## How this connects to the learning loop

Research here feeds two consumers:
- the **chat analyst** (calibrated memos, immediately), and
- the **hypothesis backlog** (`HYPOTHESES.md`): findings that suggest a tradeable
  rule become observe-only flags and must earn promotion through the graded
  gate in `TUNING.md`. Knowledge proposes; the market disposes.

To reload after editing (no redeploy needed): `POST /chat/reload-knowledge`.
