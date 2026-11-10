# R10 counter-agent verdict (2026-09-04): PASS WITH CORRECTIONS — applied

THE NULL STANDS: 0 of 7 registered arms ship-qualified, surviving independent
ledger reproduction (exact to the cent), corrected shared-resample WY (A1a
p=0.42), the registered 2022 half-split, and the registered CAGR window.

Corrections applied to the harness in this commit:
- CF-1a ship-filter DD leg was SIGN-INVERTED (latent: would have rejected a
  DD-improving winner). Fixed.
- CF-4 dead WY placeholder deleted; Holm substitution disclosed.
- CF-7 docstring wording.

Rulings on the findings:
- A1 size-gate: removing 152 sub-$1B catalyst fires = -38.8R, LOSO
  sign-stable, PIT joins clean (0 flips without lag; borderline fires +2.1R)
  — BUT a 4-symbol result (CERS 75 / CMPS 60 / ARCT 14 / PSNL 3), the same
  names as R9's diagnostic, p >= 0.42 under every correction, negative first
  half, and the capped-book "+2.25pp corroboration" is WITHDRAWN: only 23 of
  152 gated calls ever entered the capped book, summing +0.1R — the capped
  improvement was slot-reshuffle lottery, not the gate. Status:
  UNCORROBORATED 4-SYMBOL DIAGNOSTIC.
- A2v slip-veto backfire (-14.5pp; vetoed fires averaged +0.067R), A4 ~0
  (543 exits verified moved correctly), A5 null (-0.5R/195 calls, matching
  the published RA Capital null): CLEAN NULLS.
- A2 post-slip drift +2.95% fwd63: sign-interesting, p 0.107 raw / 0.86
  Holm, robust-in-sign at >=3mo threshold (+2.22%, p 0.25): DIAGNOSTIC.
- A3 post-readout drift: UNRUNNABLE at registered breadth (13 events, 5
  symbols; month-precision PCDs are the binding constraint — verified twice
  including a boundary-inclusive recount).
- Registered metric defective twice over (uncapped leverage fiction + 32%
  double-count via pullback_price_half); its -99.6% "DD" is a metric
  artifact, not a property of any tradable book.
- CF-6 process finding: R10's gates ran AFTER results were read (the
  counter-agent executed them: both PASS). R11 rule: gates run and logged
  BEFORE any result is computed, no exceptions.
- CF-8: observe-only shadow deployment of the size-gate is PERMITTED only
  with success/kill criteria registered in advance (see
  SHADOW_SIZE_GATE_SPEC.md). No live sizing, flag, or engine change is
  entitled by anything in R10.
