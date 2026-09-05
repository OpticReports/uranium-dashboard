# research/trail — S4 chandelier-trail robustness diagnostic (2026-09-05)

Findings: `../../RESEARCH_TRAIL.md`. Pre-registration: `PREREG.md` (committed
before any cell was evaluated — `git log --diff-filter=A -- research/trail/`).

Reproduce (the bars CSV is not committed; regenerate it first):

    python3 backend/scripts/fetch_bars.py bars.csv
    python3 research/trail/sweep.py       bars.csv        out/          # registered
    python3 research/trail/sweep.py       bars.csv out/ 1.0             # post-hoc, halt off
    python3 research/trail/null_boot.py   out/trail_sweep.json 2000     # null 1
    python3 research/trail/placebo.py     bars.csv                      # null 2a (degenerate)
    python3 research/trail/placebo_thin.py out/trail_sweep.json 500     # null 2b
    python3 research/trail/charts.py      out/ out/trail_summary.png

Every random draw is seeded (`SEED = 20260905`), so the numbers in the
write-up are reproducible byte-for-byte.

Harness fidelity check, run first and required to pass: `sweep.py` at
trail=5.00 on the `hl` window must equal `backend/scripts/bench_blend.py`'s
`3.3y-full-HL S6` row on the same CSV.

**Nothing here changes a config.** RESEARCH_PROTOCOL.md §7 bars adopting an
exit-parameter change while the live gate is open, and the study's own nulls
say the parameter is not a lever regardless.
