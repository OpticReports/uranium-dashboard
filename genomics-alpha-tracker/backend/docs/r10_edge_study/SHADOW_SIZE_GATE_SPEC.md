# Shadow size-gate — observe-only spec (pre-registered BEFORE deployment)

Registered 2026-09-04, per R10 counter-agent condition CF-8. H11 pattern:
observe-only; changes no trading behavior; earns or loses its promotion on
criteria fixed here, in advance.

RULE UNDER OBSERVATION: catalyst-flag entries (quiet_before_catalyst,
pullback_into_catalyst, binary_event_within_n_days) where PIT market cap
< $1B at fire time are TAGGED "shadow_size_gate: would_skip". The live book
still takes them. The shadow ledger accrues both branches.

EVIDENCE STATUS AT REGISTRATION (stated so the bar cannot drift): an
uncorroborated 4-symbol diagnostic (ARCT/CERS/CMPS/PSNL, -38.8R over 152
fires 2016-2026, p>=0.42 after correction, negative first half; capped-book
corroboration withdrawn). This shadow is the rule's THIRD look; it gets no
fourth without meeting the criteria below.

SUCCESS CRITERIA (promotion to a real gate):
- Evaluation window: 12 months from deployment OR >= 25 would-skip fires,
  whichever comes LATER.
- Promote iff: mean r_net of would-skip fires < 0 AND the would-skip set's
  total R <= -5R AND >= 5 distinct symbols contributed fires AND the
  live-window gap (would-skip mean minus taken-catalyst-large mean) < -0.15R.
KILL CRITERIA (retire the idea):
- would-skip fires' total R >= +3R at any point after 15 fires, OR
- the 12-month window closes with < 10 would-skip fires (universe too thin
  to ever promote; retire rather than extend silently).
No mid-window edits. Grading by the H11 shadow-grader conventions.
