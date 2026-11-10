# Counter-agent verdict — Unicorn Edge replication (2026-08-26)

**VERDICT: PASS WITH CORRECTIONS** (all applied before presentation).
Every headline number recomputed with independently written code (numpy
row-loops, no shared idioms): L0 series matches elementwise to 1e-16;
alignment conventions proven leak-free by construction on a synthetic
hand-checkable panel; weights/NaN handling clean (3.0% flat-book days,
no Sharpe inflation); splits/dividends verified on AAPL/NVDA/TSLA/KO/JPM.

Corrections required and applied:
1. BLOCKER — L2o (open-fill) outputs had been generated mid-pull on an
   incomplete panel: corrected full-period Sharpe is −0.30 (was −1.98).
   Rule reaffirmed: outputs are never generated while a pull is running.
2. MAJOR — census denominator bug (boolean .notna() never NaN): correct
   census is 9.5% at the written >0.60 gate and 30.0% at 0.55 (was
   quoted 8.3%/26%). Binomial cross-check with empirical p=0.5131:
   P(≥38/63)=9.6%, P(≥35/63)=29.2% — theory matches measurement. The
   paper's claimed 35% needs an effective threshold ≈0.54.
3. MAJOR — "one-line bug" framing overreached: reproduction requires TWO
   one-line errors (same-day P&L + sign/sort inversion). Inside that
   branch the family is BROAD (Sharpe 9–17 across thresholds, regime
   conventions, weighting schemes, even RANDOM 30% gates → 12–14; no
   gate at all → 16.5). Closest fingerprint: momentum-z-only same-day =
   12.99 / 160.4% / 12.3% vs the paper's 13.19 / 158.6% / 12.0%.
4. MAJOR — we may NOT claim to have identified "the" bug: the leak family
   reproduces the paper's HEADLINE row but not its ancillary robustness
   tables (their regime-off 1.2, random-regime max 1.89, threshold-0.42
   → 3.2 are inconsistent with the leak family AND with the honest spec).
   Entitled language: "consistent with a look-ahead artifact; not
   consistent with the paper's own written specification; ancillary
   tables unexplained and internally inconsistent." Not entitled:
   "proven coding error", "fabricated", intent claims.
5-10. MINOR — turnover basis stated (two-sided); window-dating tested
   (honest −0.09..+0.46 across 4 interpretations; leak family +11.0..
   +15.4 — contrast is survivorship-robust, leak survives random gating);
   paper-internal inconsistencies verified and citable: median=mean to
   rounding despite claimed skew; 67% win-days inconsistent with claimed
   moments; 187+189 positions vs "35% active" in the same table; 42%
   turnover vs 8-day holding; train Sharpes 16.6–27.8 unreachable
   honestly (artifact predates the OOS windows); the 3:45pm/4:00 MOC
   schedule corresponds to the convention that yields 0.16, and no
   physically executable schedule earns day t's own close-to-close
   return — the only convention that produces 13.
