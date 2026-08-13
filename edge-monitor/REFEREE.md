# Counter-agent verdict — edge-monitor (2026-08-13)

**Overall: SHIP-WITH-FIXES → all fixes applied same day (commit history).**
Referee executed the gate suite, re-derived every calibration with
independent code/seeds, audited formulas against source papers, and
attacked the blueprint's logic. Rerunnable attack scripts in session
scratchpad (`atk1_psr_null` … `atk6_bocd_stress`).

## DEFENDED (independently reproduced)
- PSR null uniformity: calibrated under Gaussian, t(4), t(3); extreme
  crash-skew miscalibrates CONSERVATIVELY (costs power, not false alarms).
- CUSUM MC-calibrated ARL holds on fresh t(3) draws (531–651 vs target 500,
  errs safe). Note: at SR-sized k, Gaussian closed-form h would also have
  been adequate — MC calibration is belt-and-braces, not load-bearing.
- DD percentile calibrated under AR(1) up to φ=0.4 (runs conservative).
- Formula audit CLEAN: PSR SE / MinTRL (Bailey–LdP 2012, Mertens 2002),
  E[maxSR] (DSR 2014), BOCD NIG updates + Student-t predictive
  (Adams–MacKay 2007) — sequential-vs-batch posterior equal to 1e-10.
- Citations: Page 1954, Wald 1945, White 2000, Hansen 2005 all check out.

## CONFIRMED and fixed
1. **MinTRL doc numbers wrong 2×/9×** (largest finding): daily SR 1.2 is
   476d (not ~230); daily 0.7 is 1394d (not ~700); monthly SR 0.8 is ~53
   MONTHS (not ~40 years — the error had driven a "monthly books never get
   verdicts" policy, re-decided to a ~4–5y clock). S5 PSR ETA → ~mid-2028.
2. **BOCD truncation bug**: plain tail truncation deleted the dominant
   longest-run bin → map_run_length garbage after ~r_max stable points.
   Fixed: tail mass collapses into the last bin; saturation gate added.
3. **standardize() lookahead**: EWMA vol seeded from var(r[:20]) leaked the
   warmup window. Fixed: seed from r[0]² only, first 10 values NaN
   (refused, not emitted); no-lookahead gate extended.
4. **McLean & Pontiff garbled**: correct figures are 26% lower post-sample,
   58% lower post-publication (32pp = publication increment).
5. **State machine holes**: blind feed could vacuously satisfy
   YELLOW→GREEN (now requires feeds fresh); restore-1.0 contradicted the
   Kelly clip (precedence rule added: state=cap, Kelly=level); RED
   "Bonferroni" was aspirational and ill-typed (restated as
   by-construction thresholds, no p-value correction claimed).
6. **YELLOW budget understated**: return-CUSUM+DD ≈1.5/yr measured, but
   all five triggers put the realistic rate at ~2–4/yr — restated.
7. **Honesty overclaim**: only dd_percentile implements `insufficient`
   natively; §6 restated as the layer-runner contract (to build). Dead-edge
   detection claim widened to the measured ~120–330d band; fragile
   single-seed gate replaced with a multi-seed band. PBO cite year fixed.

## Standing limitations (disclosed, not fixed)
- PSR assumes iid; N_eff adjustment is a layer-runner TODO.
- BOCD is blind to SR-sized mean shifts (pinned by an honesty gate —
  by design a corroborator, never first-line).
- Extreme-skew PSR loses power (conservative direction).
