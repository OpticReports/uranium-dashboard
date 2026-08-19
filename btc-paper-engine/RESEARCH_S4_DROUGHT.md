# RESEARCH_S4_DROUGHT.md — S4 drought deep-dive: D1 measured + corrected pre-registration (2026-08-19)

**Status:** descriptive study **D1 executed (ZERO new trials — frozen config, no
parameter search, no rule changes)**; research memo corrected per the binding
counter-agent review (verdict log at the end); candidates H1–H3 pre-registered
in §5; **H1 + H2 (the 3 runnable configs) RUN 2026-08-19 — all three REJECTED
at G1 (§9)**; H3 remains §7-blocked, H4 deferred. Charts delivered with this study: `s4_drought_equity.png`,
`s4_drought_scatter.png`, `s4_s3_corr.png` (study scratchpad; equity + shaded
droughts, duration/depth scatter with "now", rolling S3/S4 correlation).

---

## 1. D1 RESULT — is the current flat stretch within historical norms? **NO.**

Full-history (2013-01 → 2026-08-19) replay of the frozen S4 config
(Donchian-20, 5×ATR chandelier trail, 1x, engine code path, research fees,
per-bar MTM equity). 346 trades, 292 underwater stretches measured.

**The current stretch is a historical outlier — the longest drought in the
strategy's measured life, by 2.5×:**

| rank | peak → recovery | duration | depth at trough | rolling-2y PF at trough | rolling-2y ret at trough |
|---|---|---|---|---|---|
| **NOW** | **2024-03-04 → ongoing** | **898 d (29.5 mo)** | **−50.3%** (2025-04-12; now −27.5%) | **1.00** | **−28.0%** |
| 1 | 2013-04-16 → 2014-04-10 | 360 d | −71.7% | 1.15 | (n/a, n=22) |
| 2 | 2019-05-14 → 2020-03-16 | 307 d | −46.8% | 1.42 | +239.6% |
| 3 | 2015-01-14 → 2015-08-25 | 222 d | −27.7% | 1.99 | +333.2% |
| 4 | 2022-06-18 → 2023-01-16 | 211 d | −34.0% | 1.33 | +108.4% |
| 5 | 2020-05-07 → 2020-11-20 | 197 d | −43.2% | 1.11 | +31.8% |
| 6 | 2017-11-29 → 2018-06-10 | 193 d | −53.8% | 1.42 | +222.9% |

- Duration: **0 of 291** completed historical stretches lasted as long as the
  current one (prior record 360 d, 2013). Small-N honesty, stated where the
  claim is read (correction C5): most of those 291 are trivial dips — only
  ~30 stretches ran ≥30 d/≥10% and ~7 ran ≥6 months, so "longest ever" is a
  record against roughly seven meaningful precedents, not 291. Basis
  robustness: on the trade-close basis the current drought is 632 d vs a
  267 d record (2.4×) — the record-length finding survives the basis choice.
  Depth: three completed stretches were deeper than the current trough —
  2013 (−71.7%), the April-2013 crash spike (−56.3%, a real 2-day market
  event, excluded from the duration ranking on duration grounds only —
  correction C2), and 2017-18 (−53.8%).
- **Every rolling-2y PF ≤ 1.0 month in 13.6 years sits inside the current
  stretch** (first occurrence 2025-05; none before). Historical droughts were
  drawdowns inside strong 2y windows (PF at trough 1.1–2.2); this one is a
  long PF≈1 bleed — **qualitatively different, not a repeat of a known shape**.
- Current trailing-2y window (research basis): PF 0.98, return +2.0%, n=60 —
  **6th percentile (PF) / 9th percentile (return)** of all rolling-2y windows
  since 2015. Only ~8% of history ever printed PF2y ≤ 1, all of it in this
  stretch.

**⟹ D1 verdict: the research memo's §2 hypothesis ("current window is within
the already-measured shape") is REFUTED on duration and on the PF≤1 signature.
Per the memo's own pre-registered consequence ("if the current stretch sits in
the worst historical percentile, H0 weakens and the retirement trigger — not
the candidates — is the next conversation"), the retirement trigger is now the
first-order conversation (§3).** What still supports patience, honestly
stated: (a) the standalone weakness was pre-priced at adoption ("judge it ONLY
as a portfolio member"); (b) protocol §6 power analysis — PF 1.3 vs 1.0 takes
150–300 trades to distinguish, so n=59 at PF≈1.0 cannot statistically
separate "edge dormant" from "edge dead"; (c) on the research basis the
equity has already recovered from −50.3% to −27.5% below peak, and 2026ytd is
+28.8% — **a favorable slice, reported as such, carrying no inference that
the drought is resolving** (correction #3).

## 2. Measurement basis + fidelity (what was run, and one reconciliation finding)

- **Harness:** `backend/app/engine/{core,replay}.py` — the identical engine
  code path used by the live paper engine and `research_switch*.py`. Frozen
  `RESEARCH_BOOKS` S4 config, `SignalCfg`/`TradeCfg` defaults, cash_apy=0,
  donchian fees 12 bp round-trip on entry notional at exit. Equity curve =
  per-bar mark-to-market; drought durations/depths measured on it.
- **Data:** Bitstamp BTC/USD 4h, 2011-08-18 → 2026-08-19 (32,881 bars),
  refetched from the same keyless endpoint as `app/sources/bitstamp.py`.
  Verified against the repo fixture on all 10,002 overlapping bars: 1
  mismatch — the fixture's final bar (2026-07-25 20:00), captured while still
  forming. No gaps vs the fixture.
- **Fidelity — exact:** the harness reproduces **RESEARCH_5Y.md to the
  decimal** on all seven S4 rows (2021 +50.7 / 2022 +26.4 / 2023 +97.8 /
  2024 +13.6 / 2025 −10.8 / 2026ytd +28.8 / FULL 5y +239.8% with window
  2021-08-01→2026-08-04), and reproduces the live-paper trailing-2y panel
  (n=59, win 33.9%, total −1.4% MTM, maxDD −45.4% close-basis vs −45.3%
  live). Implementation fidelity is confirmed; per correction #2 this says
  nothing by itself about historical normality — §1 above is the historical
  answer.
- **RECONCILIATION FINDING (new, measured):** RESEARCH_S4.md's regime-matrix
  numbers are on the **price-ratio research basis** (`research_basis_stats`:
  ratio-compounded returns, 6 bp single fee), not the engine dollar/MTM
  basis. Same windows, both bases, this data:

  | window | price-ratio basis (6 bp) | engine MTM basis (12 bp RT) | doc figure |
  |---|---|---|---|
  | TRAIN 2013-2021 | +442k%, DD −46.8%, MAR≈3.3 | +62.3k%, DD −71.7% | "+390k%, MAR 3.2" |
  | VALIDATE 2022-2024H1 | +229% | +148.6%, DD −34.0% | "+205%" |
  | HOLDOUT 2024-07→2026-07 | +15.7% to +23.1% (boundary-dep.), DD −43.7% | −1.4% to +5.6%, DD −49.7% | "+12%, DD −44%" |

  So the ~13 pp "gap" between the RESEARCH_S4 holdout (+12%) and the live
  window (−1.4%) that the counter-agent flagged (B2/C3) is **an accounting
  basis + window-boundary difference, not a live-vs-model divergence** — the
  engine replay of the same bars matches live exactly. Residual differences
  vs the doc's exact figures (+442k vs +390k, +229 vs +205, +16/+23 vs +12)
  are consistent with the original lab's slightly different window boundaries
  and fetch date; the lab script itself is not in the repo, so
  decimal-exact reproduction of those three rows is not possible. All future
  S4 quotes should state basis explicitly.
- **dd_halt disclosure:** run verbatim, the continuous 2013→ replay halts at
  the trade exiting **2013-07-30** (equity 180,207 vs peak 364,645, close-DD
  −50.6% ≥ dd_halt 0.50; correction C1 — Nov 2013 is that stretch's trough
  date, a different event). No documented study ever
  ran S4 continuously (TRAIN/VALIDATE/HOLDOUT and the 5y study were separate
  window runs, none of which halt), so for the descriptive full-history curve
  dd_halt was disabled — disclosed here; nothing else touched. The halt's
  existence is itself a finding: a −50% trade-close drawdown is inside this
  strategy's historical behavior, and the live book's dd_halt=0.50 would have
  fired once in 13.6 years (2013).

## 3. Retirement trigger — status (counter-agent correction #10)

Pre-registered rule (RESEARCH_S4.md): *"if BTC enters a confirmed trend regime
(e.g. 26-week channel breakout) and S4 still isn't earning after 20+ trades,
retire it."* Measured, 26-week (1092-bar) close-channel breakouts:

- **Regime condition: MET, continuously since 2024-10-29.** Confirmed
  UP-breakouts 2024-10-29, 2025-01-20, 2025-05-21, 2025-07-09, 2025-08-13,
  2025-10-05; confirmed DOWN-breakouts 2025-11-13, 2026-01-31, 2026-06-04.
  Price is below the 200d SMA today (67.3k vs 69.0k, 2026-08-19).
  Disclosure (correction C4): the breakout data also contains an earlier UP
  episode **2023-10-23 → 2024-03-13** — the drought's 2024-03-04 peak sits
  inside it — followed by a 230-day quiet gap to 2024-10-29; "continuously
  met since 2024-10-29" rests on an unregistered persistence assumption
  (quiet gaps ≤121 d bridged, the 230 d gap treated as a regime break).
  Verified harmless to the conclusion: the first 20 trades after the
  2023-10-23 entry netted **+23.4%** (earning), so that anchor never arms
  and 2024-10-29 remains the first not-earning regime entry under any
  anchor choice.
- **Earning condition — anchor-dependent, and this matters:**
  - Anchored at the **first** confirmed regime entry (2024-10-29, plain
    reading): the first 20 trades netted **−22.2%** of equity (completed by
    2025-05-30); the full up-regime window 2024-10-29→2025-11-13 was 33
    trades, **−20.7%**. Correction C3: the rule itself was written **2026-07**
    — AFTER that regime entry and after the 20-trade completion — so "the
    trigger fired in mid-2025" is true only under RETROACTIVE application of
    a later-written rule; under forward-only application the trigger has
    never fired (at adoption the prevailing regime was the 2025-11-13
    down-regime, in which S4 is earning). Not a governance gap — a
    retroactivity question.
  - Anchored at the **current** regime (down-breakout 2025-11-13): 21 trades
    closed, net **+14.1%** (research basis; the engine is the live code path,
    so the live-basis dollar answer is the same replay: +14.1% closed-trade,
    +6.0% MTM). S4 **is earning** in the current confirmed regime → the
    trigger does **not** fire on this anchor. Since the 2026-06-04 re-break:
    7 trades, +4.6%.
- **Plain statement:** the trigger is not firing today on the
  current-regime anchor; under the first-entry anchor PLUS retroactive
  application it fired in mid-2025. The rule's text (verbatim above) is
  genuinely ambiguous on the anchor — the literal any-entry reading DOES
  satisfy the condition, so the no-fire reading is the one carrying an
  extra assumption — and silent on retroactivity.
  **ADJUDICATED (Casey, 2026-08-19): FORWARD-ONLY.** Rules govern from
  their adoption date; no retroactive application in either direction. The
  trigger has therefore never fired and S4 stays in the live blend. Anchor
  fixed precisely going forward: **each confirmed 26-week regime entry from
  2026-07 onward starts its own 20-trade clock; if any such regime entry
  sees ≥20 trades without earning (net trade-close P&L ≤ 0 on the leg),
  S4 retires.** Current status under the fixed rule: down-regime entered
  2025-11-13 predates adoption; the first post-adoption clock starts at the
  next confirmed breakout. Price 67.3k vs 200d SMA 69.0k (2026-08-19).

## 4. S3/S4 correlation — the G2 baseline (correction #5)

Estimator (fixed): Pearson correlation of **calendar-month returns from
month-end per-bar MTM equity**, both books 1x, research fees, engine code
path, window run starting fresh (no carry-in positions).

- **Full-window baseline (2021-01 → 2026-08): corr = −0.22, n=67 months,
  95% CI [−0.44, +0.02].** This replaces the holdout-only −0.15 as the G2
  baseline.
- Holdout window on this estimator: −0.27 (n=24, CI [−0.61, +0.15]);
  RESEARCH_S4's −0.15 was a different (undocumented) estimator — same sign
  and magnitude class.
- **Noise level, stated:** at n≈67, SE ≈ 0.12 — a hard "corr ≤ 0.0" gate is
  near coin-flip against a true corr around −0.1. G2 therefore reads: *corr
  not materially worse than the incumbent's full-window −0.22 (report with
  CI)*, plus the 2022-capture floor (candidate leg 2022 ≥ 0.6 × incumbent's
  +26.4% = **≥ +15.8%**), which is well-posed and unchanged.
- Rolling 24-mo corr has ranged ≈ −0.4…+0.15 with no drift toward
  co-movement; currently ≈ −0.26 (chart 3).

## 5. Corrected candidate pre-registration (none run; live gate still governs)

Protocol §7 unchanged: signal-space CLOSED until the live gate concludes.
Ranking unchanged by the counter-agent: **H0 > H1 > H2 > H3 > H4** — but D1
(§1) weakens H0's evidentiary basis from "within norms" to "pre-priced +
statistically indistinguishable (§6) + trigger conversation open (§3)".

**Gates (all candidates):**

- **G1 (primary, blend level):** adopt iff S5′ (75/25 @1.5x with candidate
  leg) MAR beats incumbent S5 on BOTH folds — fit/read on 2021-2023, validate
  untouched on 2024-2026, and vice versa (fold-internal metrics; the earlier
  "MAR over 2022→" wording is dropped as fold-inconsistent) — min 100 trades
  on the candidate leg, net of research fees. **Holdout = post-2026-08
  live-forward data only** (correction #4): no historical bars remain
  untouched, so the once-touched holdout is the accumulating live record,
  touched by at most ONE pre-registered champion across the whole batch,
  consistent with §7's live-gate spirit.
- **G2 (diversifier preservation):** as specified in §4 above (estimator,
  −0.22 baseline, CI reporting, +15.8% 2022 floor).
- **G3:** DSR reported against the corrected registry (~1,617 + this batch;
  see §7); ties break toward NOT adopting.
- Retirement rule if adopted: the candidate leg inherits S4's trigger, with
  the anchor fixed per Casey's §3 adjudication.

**H0 — do nothing (rank 1, 0 configs).** Stands on: pre-priced-at-adoption,
§6 power (n=59 uninformative on PF), and the blend doing its job (S5 2026ytd
+18.5%). D1 explicitly weakens it; the legitimate exit remains the §3 trigger,
never ad-hoc dissatisfaction.

**H1 — Donchian lookback ensemble (rank 2, construction, 1 config).** 50/50
inside the S4 sleeve: Donchian-20/trail-5 + Donchian-55/trail-4, both frozen
as tested in F1, monthly rebalance, no weight sweep. Correction #8 applied:
combining the top-2 of the 9-config family **dilutes** selection dependence,
it does not remove it — the ensemble's DSR accounting inherits the family's
N (=9-of-family, ~28 lab trials), not N=2. Honest risk: D-55 failed holdout
standalone (−20%); the ensemble may simply average in a loser — exactly what
G1 tests.

**H2 — constant-risk (ATR-scaled) entry sizing (rank 3, construction, 2
configs).** Corrections #6/#7 applied:

- **Stop geometry fixed:** sizing must use the donchian leg's actual initial
  risk — `stop_dist = trail_atr (5.0) × ATR14_entry / entry` — NOT
  `tcfg.stop_atr` (2.5, the pullback's stop). Requires a config-level change
  to `_size`'s inputs for donchian books; spec'd here before any run.
- **Two configs differ by cap VALUE (named now):** (i) cap = 1.0 (incumbent's
  cap) and (ii) cap = 3.0 (S1's existing cap value). The `_size` cap is
  unconditional, so there is no "uncapped" variant.
- Risk target set a priori so **median TRAIN-fold exposure = 1.0x**,
  **recalibrated per fold** in the vice-versa split (the calibration is a
  fitted degree of freedom and is treated as such).
- **Family adjacency recorded (prior strike):** the round-2 switch study's
  vol-target family (blend-leverage switching on realized-vol quantiles)
  FAILED; H2 is mechanically different (continuous per-trade sizing from
  entry-bar ATR and the strategy's own stop geometry, no signal, no
  switching) but shares the inverse-vol economic mechanism. H2 is registered
  as adjacent to that failed family and starts behind accordingly.
- Anti-shrinkage gate kept: reject if candidate leg total return over the
  folds < 0.8 × incumbent's (MAR-by-shrinking is cosmetics; the DD-shaping
  seat is taken by the bear-lever overlay in shadow).

**H3 — breakout confirmation entry (rank 4, SIGNAL-SPACE — §7-blocked; 2
configs frozen: ≥0.5×ATR(14) beyond the channel, or 2 consecutive closes;
exit machinery untouched).** Runnable only after the live gate concludes or
Casey amends §7. Skew-preservation gate: mean winner ≥ 0.9 × incumbent's on
both folds. Weakest-evidenced, regime-bet character acknowledged; the
min-100-trade gate may mechanically fail the 2-close variant (that is the
gate working).

**H4 — funding/basis regime filter: DEFERRED, 0 configs** (new dataset +
integrity pass required; §7-blocked; recorded so it is not re-invented).

**Rejected avenues** (unchanged from the memo, sources verified by the
counter-agent): win-rate maximization (33.9% is **at/just below the bottom
edge** of the measured 34–54% donchian range — correction #1 — and
structurally so); exit/trail tightening, profit targets, partial exits, time
stops (trade the right tail for smoothness; the tail IS the strategy); any F1
re-mine; long-only S4 (kills the 2022 short-side hero case; **D2** — a
zero-trial long/short P&L split of the existing trade log — remains
registered to convert this from inference to measurement, still pending);
regime/vol/efficiency switching overlays (~63 rules, two adversarial rounds,
nothing above selection noise except the shadow-logged bear-lever); F2/F3/F4
revival; ETH transfer; entry-gating chop filters on S4.

## 6. Trial budget and registry impact

| Item | Configs | Layer | Runnable when |
|---|---|---|---|
| D1 drought decomposition | 0 (descriptive — **done, this doc**) | — | — |
| D2 long/short split of S4 trade log | 0 (descriptive) | — | now |
| H0 do nothing | 0 | — | — |
| H1 lookback ensemble 50/50 | 1 | construction | now (counter-agent confirmed §7-compatible) |
| H2 constant-risk sizing (caps 1.0 / 3.0) | 2 | construction | now, after the §5 `_size` geometry spec is implemented and gate-tested |
| H3 breakout confirmation | 2 | signal-space | after live gate / §7 amendment |
| H4 funding filter | 0 | signal-space | not this cycle |
| **Total new configs** | **5** | | |

Registry: ~1,554 (previous §1 total) + ~41 (switch round 1, count inferred
from the panel's best-of-41 selection-noise bar) + 22 (switch round 2:
16 rules + 6 statics) ≈ **~1,617, recorded as an estimate** (round-2's own
statistical panel used burden 57 for its nulls) → **~1,622 after this batch
runs**. RESEARCH_PROTOCOL.md §1 updated in this same change, as required,
BEFORE any candidate runs.

## 7. Honesty box

- **Measurement basis:** engine dollar accounting, per-bar MTM equity curve,
  research fees (12 bp RT donchian), cash_apy=0, 1x, frozen config, fresh
  books per window (continuous 2013→ run for the drought curve, dd_halt
  disabled as disclosed in §2). Trade-level stats (PF, win rate) are
  trade-close. Correlations: calendar-month, month-end MTM, Pearson.
- Zero new trials were run; every number in §§1–4 is descriptive measurement
  of the frozen incumbent. The candidate sections ran nothing.
- The live-paper book itself is not in this sandbox; live-basis statements
  use the given live panel numbers (n=59, PF 0.99, −1.4%, maxDD −45.3%) plus
  the engine replay that reproduces them.
- In-sample caveats: all drought statistics are one non-stationary sample of
  13.6 years of one asset; 292 stretches are heavily overlapping/dependent
  observations, and "longest ever" on n≈dozens of independent droughts is a
  weaker statement than it sounds. NOT modeled: funding, slippage beyond
  fees, venue risk.
- The memo's original §2 "within norms" verdict was motivated in the
  do-nothing direction (its own honesty box said so); D1 was the
  pre-registered check and it came back against the memo. This doc reports
  that reversal rather than re-framing it.
- External literature figures (Hurst/Ooi/Pedersen, Man Group, Harvey et al.,
  Baltas–Kosowski, Zarattini et al.) remain **unverified quotes** — they
  carry no gate weight anywhere in this study (correction #9).

## 8. Counter-agent verdict log (repo convention)

- **2026-08-19 — adversarial counter-agent review of the S4 research memo:
  APPROVE-WITH-CORRECTIONS.** 10 binding corrections issued; none reversed
  the candidate ranking. **All 10 applied in this document:** (1) 33.9%
  below-range fix; (2) §2 circularity rewritten — holdout≈live proves
  implementation fidelity, not historical normality, D1 supplies the
  historical answer (and it refutes "within norms"); (3) "drought resolving"
  inference deleted, 2026ytd kept as labeled favorable slice; (4) G1 holdout
  defined as post-2026-08 live-forward; (5) G2 estimator/baseline/noise
  specified, full-window corr measured (−0.22); (6) H2 stop-geometry fix +
  named cap values + per-fold recalibration; (7) H2 registered
  family-adjacent to the failed vol-target family; (8) H1 selection-bias
  claim downgraded (dilutes, not removes; DSR inherits family N); (9)
  external figures marked unverified; (10) retirement-trigger status
  measured (§3) and §1 registry updated before any run.
- **D1 itself:** descriptive characterization of a frozen config, 0 trials
  added to the registry. Its data-integrity checks (fixture cross-verification,
  RESEARCH_5Y decimal-exact reproduction, live-panel reproduction) are
  documented in §2.
- **2026-08-19 — adversarial counter-agent verification of D1 (review
  appended below): APPROVE-WITH-CORRECTIONS.** Independent recomputation
  (own drought decomposition, own breakout detector) confirmed every
  load-bearing number; 5 binding corrections (C1 halt date, C2 April-2013
  crash spike mislabeled as data artifact / three-not-two deeper stretches,
  C3 "governance gap" reframed as retroactivity question, C4 2023-10 regime
  episode + persistence assumption disclosed, C5 small-N caveat moved to
  §1) — **all applied in this revision**. H1/H2 remain green-lit per §5.

---

## Counter-agent review (D1 verification)

**Reviewer: adversarial counter-agent, 2026-08-19. Method: independent
recomputation (own peak-to-recovery decomposition, own breakout detector, own
percentile/CI/trigger accounting — script `ca_verify.py` in the study
scratchpad) over the same engine code path and `bars_4h_full.csv` (which was
itself cross-checked: 32,881 bars, monotonic, zero 4h gaps, 10,002-bar overlap
with the repo fixture, 1 mismatch = the fixture's still-forming final bar,
confirmed). External re-fetch from Bitstamp was NOT repeated; the fixture
cross-check is the data anchor.**

### VERDICT: APPROVE-WITH-CORRECTIONS (5 binding, all wording/framing — no
### headline number changes; the D1 reversal of the memo's "within norms"
### hypothesis stands as measured)

### Claim-by-claim

1. **Longest-drought claim — CONFIRMED, recomputed independently.** My own
   running-max decomposition reproduces every number: 346 trades, 292
   stretches (291 completed); current stretch peak 2024-03-04, **898 d**
   elapsed, trough **−50.3%** on 2025-04-12, now **−27.5%**; prior record
   2013-04-16→2014-04-10, **360 d**, −71.7%; 0/291 completed stretches ≥ 898 d;
   ranks 2-6 of the table match to the digit, as do all PF2y/ret2y-at-trough
   values. Sensitivity (my additions): (a) recovery defined as ≥peak vs >peak —
   no change; (b) near-recovery: the MTM curve came within **1.2%** of the
   2024-03 peak in Nov–Dec 2024, and on the **trade-close basis equity made a
   new high on 2024-11-25** — trade-close drought is **632 d vs a 267 d
   trade-close record (2.4×)**. So "longest ever" is robust across bases and
   recovery thresholds; the specific "898 d / 2.5×" is MTM-basis-specific (the
   doc does state its basis). Base-rate honesty: see binding C5.
2. **PF≤1 signature — CONFIRMED.** First rolling-2y PF≤1.0 grid month
   2025-05; all 11 such months inside the current stretch; share of history
   7.7% (~8% as stated); current PF2y 0.976 / ret2y +2.0% / n=60 at the 6th /
   9th percentile. Robust to switching the 30-day grid to calendar months
   (7.9%, 5th pct).
3. **Fidelity + basis reconciliation — CONFIRMED with one clarification.**
   All RESEARCH_5Y rows I re-ran reproduce **to the decimal on the MTM basis**
   (2022 +26.4, 2023 +97.8, 2025 −10.8, FULL 5y +239.8; close-basis differs,
   e.g. 2022 +22.7 — the doc's "to the decimal" means MTM, which is
   RESEARCH_5Y's stated basis). Live panel reproduced: holdout window run gives
   n=59, win 33.9%, **−1.4% MTM**, maxDD −45.4% close / −49.7% MTM. Basis
   wedge is real and measured: same window, price-ratio basis (single 6 bp)
   **+15.7%** vs engine close **−5.7%** / MTM −1.4% — a ~17-21 pp accounting
   wedge, with boundary shifts of ±1 wk-1 mo moving the price-ratio figure
   15.7→27.9%. RESEARCH_S4's +12% sits just below the recomputed price-ratio
   range; the residual ~4 pp is plausibly lab boundary/fetch differences but is
   NOT provable (lab script absent) — the doc says exactly this, so the
   reconciliation is honestly labeled, not a convenient story.
4. **Retirement trigger — numbers CONFIRMED; framing corrected (C3, C4).**
   Rule verbatim (RESEARCH_S4.md, Recommendation): *"Revisit trigger: if BTC
   enters a confirmed trend regime (e.g. 26-week channel breakout) and S4
   still isn't earning after 20+ trades, retire it."* My independent 26-week
   detector reproduces every listed episode (UP 2024-10-29 / 2025-01-20 /
   05-21 / 07-09 / 08-13 / 10-05; DOWN 2025-11-13 / 2026-01-31 / 2026-06-04)
   and the accounting: first 20 trades after 2024-10-29 **−22.2%** (done
   2025-05-30); full up-window 33 trades **−20.7%**; current regime since
   2025-11-13, 21 trades **+14.1%** closed / +6.0% MTM; since 2026-06-04
   7 trades +4.6%; close 67,348 < 200d SMA 69,027. On the rule's text: the
   anchor ambiguity is GENUINE — "enters" is event-anchored but the rule
   specifies nothing about multiple sequential entries, regime end, reset, or
   the earnings basis; note the literal any-entry reading DOES satisfy the
   condition (2024-10-29 + 20 trades not earning), so the no-fire reading is
   the one that needs the extra assumption (only the current regime counts).
   Two things the doc missed are C3 and C4 below. Neither changes the bottom
   line: anchor adjudication is Casey's call and no verdict is published — the
   ask-don't-assume handling is correct.
5. **S3/S4 correlation — CONFIRMED.** Recomputed r = −0.219, n = 67 months,
   Fisher 95% CI [−0.437, +0.022]; holdout −0.271 (n=24, CI [−0.61, +0.15]);
   estimator (calendar-month, month-end MTM, Pearson) implemented as
   specified; SE ≈ 0.125 as stated. Observation (non-binding): Spearman rank
   corr on the same 67 months ≈ **−0.02** — the negative Pearson is carried by
   large-magnitude months. That is the economically relevant estimator for
   variance reduction, but it doubles the case for §4's CI-not-point-estimate
   discipline.
6. **Doc vs results, prior corrections, registry — CONFIRMED.** Every §1-§4
   number matches d1_results.json and my recomputation; all 10 binding
   corrections from the memo review are genuinely applied (spot-checked each,
   incl. the 33.9% below-range fix, deleted "resolving" inference, G2
   estimator/baseline, H2 trail-geometry + named caps 1.0/3.0, H1 downgrade,
   §3 trigger measurement); registry arithmetic 1,554+41+22=1,617 → ~1,622
   correct and landed in RESEARCH_PROTOCOL.md §1 in the same commit; charts
   match the claimed content. dd_halt disclosure verified (verbatim continuous
   run halts at −50.6% close-DD; date correction C1). "Longest drought" is
   presented as measured and the small-N caveat exists — but in §7, not §1
   (C5).

### Binding corrections

- **C1 — halt date.** §2 says the continuous replay "halts in Nov 2013"; the
  halt fires at the trade exiting **2013-07-30** (equity 180,207 vs peak
  364,645, −50.6%). Nov 2013 (2013-11-04) is the 2013 stretch's TROUGH date —
  different event.
- **C2 — "data artifact" mislabel.** The −56.3% 1-bar spike on 2013-04-10 is
  the real April-2013 crash (fetched bars: 2013-04-10 close ~225 →
  2013-04-12 low ~59 — verified in the data; a documented market event, not
  bad data). Exclude it from the drought ranking on DURATION grounds, and
  state that three completed stretches were deeper than the current trough
  (−71.7%, −56.3% 2-day crash spike, −53.8%), not two.
- **C3 — "governance gap" overstated.** The rule was pre-registered in
  RESEARCH_S4.md, dated **2026-07** — AFTER the 2024-10-29 regime entry and
  after the 20-trade completion (2025-05-30). Nothing existed in mid-2025 to
  be evaluated; "the trigger fired and was never evaluated" is only true under
  retroactive application of a later-written rule. Reframe: the open questions
  for Casey are (i) which anchor governs AND (ii) whether the rule applies
  retroactively to a regime entered before its adoption. (At adoption,
  2026-07, the prevailing regime was the 2025-11-13 down-regime, in which S4
  is earning — under forward-only application the trigger has never fired.)
- **C4 — missing pre-drought regime episode.** The study's own breakout data
  contains an UP episode **2023-10-23 → 2024-03-13** (the drought's 2024-03-04
  peak sits inside it), followed by a **230-day quiet gap** to 2024-10-29; the
  doc's episode list silently starts at 2024 (the script printed only episodes
  STARTING ≥2024). Disclose it, and note that "regime condition MET
  continuously since 2024-10-29" rests on an unregistered persistence
  assumption (it bridges quiet gaps of up to 121 d but treats the 230 d gap as
  a regime break). Materially verified harmless to the conclusion: first 20
  trades after the 2023-10-23 entry netted **+23.4%** (earning → that anchor
  never arms), so 2024-10-29 remains the first not-earning regime entry under
  any anchor choice.
- **C5 — small-N caveat belongs in §1.** "0 of 291" inflates the comparison
  set: most stretches are trivial dips; there are ~30 stretches ≥30 d/≥10%
  and only ~7 that ran ≥6 months. The §7 honesty-box line ("longest ever on
  n≈dozens is weaker than it sounds") must be echoed in one sentence next to
  the §1 headline, where the claim is actually read.

### Non-binding notes

- The trade-close-basis drought (632 d vs 267 d record) is worth one line in
  §1: it makes the record-length finding basis-robust, and 2024-11-25 (last
  trade-close equity high) is arguably the more conservative drought start.
- `research_basis_stats` charges 6 bp per trade while the engine charges
  12 bp RT on donchian — over 59 trades that alone is ~3.5 pp of the basis
  wedge; the doc's "6 bp basis" label is accurate.
- Claim intake note: the task brief attributed the retirement rule to
  RESEARCH_SWITCH.md; it lives in RESEARCH_S4.md (the doc cites it
  correctly).

**Bottom line: every load-bearing number in this study reproduced under
independent recomputation; the five corrections are framing/precision fixes,
none reverses the D1 verdict ("within historical norms" REFUTED on duration
and PF-signature) or the trigger status (anchor- and retroactivity-dependent,
correctly escalated to Casey as a missing key input). H1/H2 remain green-lit
per §5 once the C1-C5 edits land.**

---

## 9. Batch results (2026-08-19) — pre-registered H1/H2 run: **all three REJECTED**

Exactly the 3 §5 configs, nothing else, run 2026-08-19 (registry: +5 →
~1,622, counted in RESEARCH_PROTOCOL.md §1 before the runs; the 2 H3 configs
are counted-but-blocked, not run). Engine code path only, **zero engine-code
changes**; harness reproduced frozen RESEARCH_5Y S4 rows to the decimal
(2022 +26.4 / 2023 +97.8 / 2025 −10.8) before any candidate math. Scripts +
raw results: `s4_batch.py`, `s4_batch_results.json` (study scratchpad).

**Estimator (stated once, applies to every row):** folds F1 = 2021-01-01→
2024-01-01, F2 = 2024-01-01→2026-08-19, fresh books per fold, research fees,
cash_apy 0, per-bar MTM equity. Blend = per-bar MTM constant-mix 75/25
S3/leg re-levered 1.5x each bar, applied **identically** to incumbent S5 and
every S5′ (the repo's exit-step blend basis is ~1-4pp flattering on DD; the
G1 comparison is relative, so one estimator for both sides). MAR =
fold-internal CAGR/|maxDD|. Incumbent under this estimator: **S5 MAR 4.03
(F1) / 0.68 (F2)**; S4 leg +269.6% / +13.6%, 2022 +26.4%, stitched total
+319.9%.

**H2 sizing implementation (no engine edit):** engine `vol_target` sizing
divides by `tcfg.stop_atr·ATR/entry`, so setting `cfg.risk = R_tgt×(2.5/5.0)`
yields `notional = equity·R_tgt/(5.0·ATR14_entry/entry)` — the §5 chandelier
geometry — through the byte-identical engine (algebraic identity, plus a
per-trade assertion on every executed trade: exposure == min(cap,
R_tgt/stop_dist)). Calibration (fitted DoF, per fold as registered): R_tgt =
median TRAIN-fold chandelier stop_dist → fit-on-F1 **0.0860** (n=76 entries),
fit-on-F2 **0.0642** (n=79); median pre-cap exposure = 1.0x by construction.

### Per-config results (validate direction = sizing fitted on the OTHER fold; H1 has no fitted parameter)

| config | fold | leg ret | leg MAR | leg maxDD | trades | S5′ MAR | S5 MAR | beats? |
|---|---|---|---|---|---|---|---|---|
| H1 ensemble | F1 | +188.0% | 0.98 | −43.2% | 151 | **4.18** | 4.03 | yes |
| H1 ensemble | F2 | −3.1% | −0.02 | −49.0% | 158 | **0.52** | 0.68 | **NO** |
| H2 cap 1.0 | F1 | +190.5% | 1.75 | −24.4% | 75 | **4.16** | 4.03 | yes |
| H2 cap 1.0 | F2 | +13.0% | 0.10 | −47.7% | 79 | **0.6792** | 0.6839 | **NO** (unrounded) |
| H2 cap 3.0 | F1 | +342.2% | 2.22 | −28.9% | 75 | **4.76** | 4.03 | yes |
| H2 cap 3.0 | F2 | −28.0% | −0.21 | −56.5% | 44 (**halted**) | **0.32** | 0.68 | **NO** |

In-fold-fit direction (reported for completeness; G1 needs BOTH directions):
H2 cap 1.0 F2 in-fold S5′ MAR 0.73 vs 0.68 (beats), H2 cap 3.0 F2 in-fold
0.79 vs 0.68 (beats), F1 in-fold 4.62 / 5.37 (beat). So H2's F2 failures are
**created by the honest per-fold recalibration**: sizing fitted on the fat
2021-23 ATR distribution (R_tgt 0.0860), carried into the lean-ATR drought
fold, oversizes exactly there. H2 cap 3.0's validate-direction leg hit
**dd_halt 0.50** (close-basis) mid-2025 and stopped trading after 44 trades —
that is the config's real behavior, reported as such.

### Gates (G2 "materially worse" operationalized before reading results as r > −0.10 = baseline −0.22 + 1 SE 0.12)

| config | G1 both-folds-both-directions | ≥100 trades (folds combined) | G2 corr vs S3 (n=67) | 2022 leg (floor +15.8%) | H2 anti-shrinkage (≥0.8×inc = +255.9%) | **verdict** |
|---|---|---|---|---|---|---|
| H1 ensemble | **FAIL** (F2: 0.52 < 0.68) | 309 PASS | −0.198 CI [−0.42, +0.04] PASS | +33.1% PASS | n/a | **REJECTED** |
| H2 cap 1.0 | **FAIL** (F2 val: 0.6792 < 0.6839) | 154 PASS | −0.174 CI [−0.40, +0.07] PASS | +24.0% PASS | +228.3% **FAIL** | **REJECTED** |
| H2 cap 3.0 | **FAIL** (F2 val: 0.32 < 0.68) | 119 PASS | −0.111 CI [−0.34, +0.13] PASS | +25.3% PASS | +218.4% **FAIL** | **REJECTED** |

- Min-100 read as total across both folds (protocol §4's evaluation-period
  reading); per-fold counts are 75-79 for H2 — under a per-fold reading H2
  would fail mechanically as well, so the reading is immaterial to verdicts.
- H2 2022 floor uses out-of-fold sizing (fit-on-F2); in-fold sizing reads
  +31.5% / +32.2% — floor passes either way. H1 2022: +33.1%.
- **The common failure is G1 on the 2024-26 fold — the drought fold itself.**
  No candidate fixed the thing the batch was probing. H1: D-55 standalone F2
  = −22.2% (echoes its −20% holdout failure in RESEARCH_S4.md); the ensemble
  averaged in the loser, exactly the risk §5 named. Diversification was NOT
  the failure mode: every G2 gate passed.

### G3 — DSR context (registry N≈1,622; monthly stitched-fold returns, T=67; context only, no gate weight)

| book | SR (ann.) | hurdle SR0 | DSR |
|---|---|---|---|
| S5 incumbent | 1.69 | 1.45 | 0.73 |
| S5′ H1 | 1.51 | 1.45 | 0.57 |
| S5′ H2 cap 1.0 | 1.54 | 1.45 | 0.59 |
| S5′ H2 cap 3.0 | 1.36 | 1.45 | 0.41 |

(Estimator differs from protocol §2's 2022-2026 audit — window 2021→2026-08,
expected-max-of-N hurdle on monthly Sharpe; every candidate's DSR sits BELOW
the incumbent's, consistent with rejection; ties were never in play.)

**Charts (study scratchpad):** `s4_batch_equity.png` (S5 vs each S5′, log,
stitched folds), `s4_batch_drawdown.png` (blend drawdown profiles),
`s4_batch_gates.png` (gate matrix).

### Honesty box additions (this batch)

- Calibrated per fold: H2's R_tgt only (median TRAIN-fold chandelier
  stop_dist; a fitted degree of freedom, recalibrated per direction as
  registered). H1 had zero fitted parameters, so its two G1 directions are
  the same run reported once per fold.
- The blend estimator (per-bar MTM constant-mix, 1.5x re-levered per bar) was
  chosen for this batch and applied to BOTH incumbent and candidates; it is
  not the RESEARCH_5Y exit-step basis (which flatters DD ~1-4pp). Incumbent
  S5 numbers here therefore differ from RESEARCH_5Y's blend rows by basis,
  not by data.
- One 4h bar overlaps at the fold boundary (repo end-inclusive window
  convention), identical on both sides of every comparison.
- G2's "materially worse" threshold (r ≤ −0.10) and the min-100 fold-combined
  reading were fixed before results were read, but were operationalized in
  this batch, not in §5's text.
- NOT modeled: funding, slippage beyond research fees, venue risk; H2's
  dd_halt interaction with live capital (the cap-3.0 halt shows it binds).
- Holdout (post-2026-08 live-forward) untouched; verdicts are
  REJECTED/ADVANCES only — none advances, so nothing touches it.
- **Counter-agent verification of this batch: PENDING** (repo convention —
  required before these results are acted on further; log goes to §8).

**Bottom line: a clean 3-rejection batch. H0 (do nothing) remains the
standing position by default, with the §3 forward-only retirement trigger as
the only registered exit. Signal-space stays CLOSED (§7 protocol).**
