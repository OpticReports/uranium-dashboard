# RESEARCH_S4_DROUGHT.md — S4 drought deep-dive: D1 measured + corrected pre-registration (2026-08-19)

**Status:** descriptive study **D1 executed (ZERO new trials — frozen config, no
parameter search, no rule changes)**; research memo corrected per the binding
counter-agent review (verdict log at the end); candidates H1–H3 **pre-registered,
NOT run**. Charts delivered with this study: `s4_drought_equity.png`,
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
  current one (prior record 360 d, 2013). Depth: only 2013 (−71.7%) and
  2017-18 (−53.8%) were deeper (a 1-day −56.3% spike on 2013-04-10 is the
  April-2013 flash crash, a data artifact, not a drought).
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
- **dd_halt disclosure:** run verbatim, the continuous 2013→ replay halts in
  Nov 2013 (trade-close DD −50.6% ≥ dd_halt 0.50). No documented study ever
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
- **Earning condition — anchor-dependent, and this matters:**
  - Anchored at the **first** confirmed regime entry (2024-10-29, plain
    reading): the first 20 trades netted **−22.2%** of equity (completed by
    2025-05-30); the full up-regime window 2024-10-29→2025-11-13 was 33
    trades, **−20.7%**. **The trigger's condition was satisfied around
    mid-2025 and was never evaluated** — a governance gap, found only by this
    check.
  - Anchored at the **current** regime (down-breakout 2025-11-13): 21 trades
    closed, net **+14.1%** (research basis; the engine is the live code path,
    so the live-basis dollar answer is the same replay: +14.1% closed-trade,
    +6.0% MTM). S4 **is earning** in the current confirmed regime → the
    trigger does **not** fire on this anchor. Since the 2026-06-04 re-break:
    7 trades, +4.6%.
- **Plain statement:** the trigger is not firing today on the
  current-regime anchor, but under the first-entry anchor it already fired in
  mid-2025. The rule's anchor was never pre-registered precisely.
  **DECISION NEEDED (Casey): which anchor governs — and does the 2025
  retroactive fire count?** Per repo convention this is a missing key input:
  no retirement/retention verdict is published here conditioned on an assumed
  anchor.

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
  documented in §2. Per protocol, this doc should receive its own
  counter-agent pass before any H1/H2 config runs are green-lit.
