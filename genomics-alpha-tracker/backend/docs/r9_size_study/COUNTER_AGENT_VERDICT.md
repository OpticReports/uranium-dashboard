# R9 counter-agent verdict (2026-09-04): PASS WITH CORRECTIONS — all applied

Independent reimplementation reproduced the Stage-2 baseline (IR 0.641) and
every headline number exactly; Stage-2 mechanics fully audited clean
(z-alignment elementwise-verified, composite hand-checked, no entry leak,
0 skipped months).

RULINGS:
- F1 STANDS (the campaign's promotable result): 0 of 108 tested arms beat
  the size-blind baseline after Westfall-Young (best raw p .036 → WY .98).
  Correction: "0 of 108" — the 3 registered monotone-interpolation arms were
  never run and the log's "folded into grid" claim was wrong.
- F2 KILLED → DIAGNOSTIC. The "runway works in large caps" interaction
  (IC +0.30, p_wy .0003) was significant only via a block-length deviation
  from the registered clustering: with 63d blocks fwd21 dies (p_wy .07) and
  fwd63 is marginal (.037); non-overlapping sampling p=.46/.18; sign was
  OPPOSITE in 2021-22 (+0.64); mechanism = a median of ONE penalized
  mega-cap per day (chiefly MRNA 2024-26). Entitled phrasing only:
  "single-name quality episode, not evidence of a size-conditional signal."
- F3 REDUCED to one diagnostic: catalyst-proximity long entries in <$1B
  names lost ~0.3R vs large (binary-event survives Holm p=.006; quiet and
  pullback-into-catalyst do NOT survive correction and are largely the same
  trades — union 50 symbol-months, 3 distinct small symbols ARCT/CERS/CMPS,
  sign consistent in every one). No p may be quoted as 0.000.
- F4 STANDS: the analyst/team half is UNTESTED (27% proxy coverage, 0-71
  qualifying days), not refuted.

REGISTRATION-FIDELITY LEDGER (disclosed): (1) Stage-1 inference used 21d
block bootstrap not the registered symbol|month clustering — HIGH, drove
F2's false significance; (2) flag tests sat outside the WY family — HIGH,
killed 2 of 3 flag findings when corrected; (3) flags tested as R-multiples
not registered fwd-excess; (4) monotone arms never run; (5) Z2 built but
orphaned by every bucket scheme, phase-weighted diagnostic never built;
(6) split-half at median month; Stage-2 2000 draws vs registered 4000;
(7) universe is 33 names + XBI, not 34.
