# Claims under adversarial review — S4 trail robustness study (2026-09-05)

Repo: /home/user/uranium-dashboard/btc-paper-engine (branch
claude/s6-win-rate-study-nx5m1d). Pre-registration: research/trail/PREREG.md
(committed 5bb2214 BEFORE any cell was evaluated — verify this).
Scripts: research/trail/{sweep.py,null_boot.py,placebo.py,placebo_thin.py}
Frozen output: /tmp/trail/console.txt ; JSON: /tmp/trail/trail_sweep*.json
Bars: /tmp/claude-0/-home-user-uranium-dashboard/98a6cf63-599b-59a8-b758-40c71716fb29/scratchpad/bars_4h_btcusd_ext.csv

C1. HARNESS FIDELITY. sweep.py at trail=5.00 on the `hl` window reproduces
    backend/scripts/bench_blend.py's committed "3.3y-full-HL S6" numbers
    exactly (cagr 28.9%, mdd -28.3%, MAR 1.02) on the same CSV.

C2. PRE-REGISTERED VERDICT = INDETERMINATE. C1 pass (5.00 is 100% of grid
    max on `modern`), C2 fail (4.0-6.0 neighbourhood spans 62.3% of the full
    grid MAR range, bar was <25%), C3 fail (Spearman between modern_A and
    modern_B dose curves = -0.064, bar was >=0).

C3. THE REGISTERED CURVE IS CONFOUNDED BY A KILL SWITCH. S4's dd_halt=0.50
    fires in 13 of 21 grid cells on `modern` (SELF-CORRECTED from 16 on re-count from the JSON `halted` flags, which are authoritative); at the live trail=5.00 it does
    NOT fire (realized book DD stays inside -50% while MTM touches -50.3%).
    Cells 5.25-6.25 all die in April 2025 and stop trading for the rest of
    the sample. So the registered dose curve partly measures which cells got
    killed, not the trail.

C4. POST-HOC HALT-OFF CURVE IS A BROAD PLATEAU. Re-running with dd_halt=1.0
    (clearly labelled post-hoc, not pre-registered): S6 MAR rises from ~0.00
    at trail 2.00 to ~1.03 by 2.75 and then sits in a 1.02-1.54 band all the
    way to 7.00. The decision that matters is "wide enough", not "5.0".
    Cross-window Spearman(modern, hl) = +0.731 (windows OVERLAP - not
    independent).

C5. NULL 1 (30-day calendar block bootstrap, 2000 draws, all 21 cells share
    each draw): the incumbent's +0.419 MAR lift over the grid median is
    exceeded by a random best-of-21 lift 75% of the time. So "5.00 is the
    argmax" carries no evidential weight.

C6. NULL 1, second reading: 5.00 is nonetheless a reliably good plateau
    member - bootstrap argmax 23% of draws (uniform 4.8%), median rank 4 of
    21, top-5 in 64%, bottom-half in 14%.

C7. NULL 2a (time_stop_bars placebo) is DEGENERATE and reported as such:
    the pullback's time stop stops binding at 55 bars, so 13 of 21 cells are
    identical and lift is exactly 0. Incidental finding: time_stop_bars=60 is
    a dead parameter on the modern era.

C8. NULL 2b (matched random thinning of the S4 leg, 21 variants per rep, 500
    reps): best-of-21 random thinning beats the ENTIRE trail grid's max
    (1.537) in 100% of reps, median 2.012. Its best-of-21 lift exceeds the
    trail grid's in 80% of reps.

C9. CONCLUSION AS IT WILL BE PRESENTED: no change to trail_atr=5.0; the
    parameter is not a lever on this data; RESEARCH_PROTOCOL section 7 bars
    adoption anyway. The only forwardable items are (a) S4 came within ~0.3pp
    of tripping its own -50% dd_halt in April 2025 at the live setting, and
    (b) time_stop_bars is dead.

Your job is to REFUTE. Default to "refuted" when uncertain. Run the code.
