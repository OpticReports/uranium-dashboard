# Dollar watch pre-registration — SPEC v1, FROZEN 2026-11-03

`SPEC_v1.md` is the frozen protocol; `freeze.json` carries its sha256, the frozen GARCH fit and every
parameter (shipped byte-identical as `backend/app/sources/dollar_freeze.json`).

| File | What it is |
|---|---|
| `SPEC_v1.md` | the frozen SPEC: forward-only D-3 with a drift-bracketed GARCH-t null, the placebo beside it, the 2-of-5 onset rule dated month by month |
| `freeze.json` | Casey's answers (2026-11-02), the defaults carried for Q17–Q19, the fit, the hashes |
| `fed_emergency_actions.json` | marker 5's list v1.1: 50 actions, rulings, 14 rejected candidates, `reviewed_through` (shipped as `backend/app/sources/dollar_fed_actions.json`) |
| `v1_work/` | the pre-committed onset check (`precommit_onset.txt`, `onset_count.py`, its output and raw-pull manifest), the list-v1.1 recount, the v1 draft power script |
| `SPEC_v0.md`, `freeze_template.json`, `review_*_v0.md`, `review_*_scripts/` | the withdrawn v0 and its two NOT_PASS reviews |
| `../prereg/` | the offline harness `d3.py` (fit, p_u per unit from hash-checked archived bytes, looks), `d3_power_v1.py` (exact power), `g6.py` and `g6_out/` (gate G6), `freeze_vintage/` (the fit's input files) |

The v1 reviews (statistics; data and point in time) both returned PASS_WITH_FIXES; their findings and
what was adopted are in SPEC v1's counter-agent log. Neither review, nor anyone else, computed a
history-based DECEL outcome; raw downloads stay out of the repo except the freeze vintage the fit used.
