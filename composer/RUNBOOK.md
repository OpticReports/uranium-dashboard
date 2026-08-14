# CRASH-DAY RUNBOOK — pre-decided protocol (written calm, 2026-08-06)

Purpose: on a violent market day, this page replaces improvisation.
Everything here was decided with data, in advance. Addenda cited.

## What the AUTOMATION already does (do not duplicate it)

- 3:45 PM ET: every symphony re-evaluates and rotates itself. The engines
  are internally convexity-aware — they EARN in turbulence (add. 20b/25);
  their defensive branches (BIL cash, PULS, HYG credit guard, vol legs)
  engage without anyone's help.
- 5:35 PM ET daily check: two-tier DD alerts (anomaly thresholds are
  conservative-calibrated), book-level 17% alarm, sleeve band, 40%
  concentration cap (full reset, pre-authorized), 25% single-move and
  >50% data-anomaly guards. Trades only what POLICY.md pre-authorizes.
- You get a push notification for anything that matters.

## What the OWNER does on a crash day

1. NOTHING intraday, by default. Measured five ways: every intervention
   family (news force-runs add. 22, gates 19b, vol targets 20b, DD exits
   21, valuation 26) amputates the engines' best states — which are
   crash-recovery states.
2. Read the evening report. It states: book DD vs the expected bands
   (ordinary year: 22-27%; tail: high-30s — add. 21b), which engines
   rotated defensive, gauge status, and any POLICY action taken.
3. The ONE discretionary decision that is yours (add. 7): if the crash
   sleeve has spiked above ~20% of book, the band will trim mechanically
   — but harvesting FURTHER (monetizing convexity beyond the band into
   crushed engines) is owner judgment. The runbook's guidance: do it in
   thirds across multiple windows, never all at once.
4. DO NOT: cancel pending automation mid-flight, force-run symphonies,
   liquidate to cash (the engines' recovery capture IS the edge — HG's
   rebound harvesting earns most after the worst days, add. 19b),
   or resize allocations mid-crash (the cap handles concentration).

## Expected numbers to hold in mind (so red screens read as data)

- A -10% book day: within ordinary engine behavior; KMLM/HG single-day
  swings of +/-4-14% are NORMAL (live record).
- Book DD 17%: the book-level alarm fires — diagnostics sweep runs; this
  is the "pay attention" line, not the "act" line.
- Book DD 25-30%: inside the conservative expected range for a bad year.
  The plan already priced this. Check the divergence diagnostics in the
  report: engines TRACKING their models while down = regime, not
  breakage. Engines DIVERGING from models = the alarm tier says so, and
  de-allocation decisions go through POLICY, not panic.
- Book DD 38%+: conservative p95. If diagnostics still pass, this is the
  tail we accepted; if they fail, the alert tier has already paged you
  with specifics.

## If Composer itself is down/unreachable on a crash day

- The book is long-only, no margin: positions cannot be liquidated out
  from under you. Worst case = positions ride until access returns.
- The daily check reports API failures rather than trading blind
  (>50% anomaly guard). Do not attempt manual workarounds under stress.

## After the storm

- The daily cadence auto-resumes; the quarterly regime_boot re-run and
  slippage measurement capture the episode into the evidence base.
- The first live crash is ALSO the evidence that resolves the lens
  question (as-measured vs conservative) — the earn-back and divergence
  records after the episode are the most valuable data this book will
  ever produce. Protect the experiment: let it run.
