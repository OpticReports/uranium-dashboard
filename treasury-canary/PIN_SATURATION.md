# Pin-board severity legibility — spec (rev 2, pre-implementation)

**Status:** specced, NOT implemented. Two adversarial counter-agent passes complete; verdicts logged below.
**Origin:** Casey, 2026-09-10 — "why is Corporate & private credit not at critical? its scored at 99."
**Headline:** the proposed 95+ band is **rejected on the evidence**. What ships is a continuous
intensity ramp (no threshold, no claim) plus a measurement-ceiling marker.

## The problem, stated honestly

`_status_from_score` (`backend/app/metrics/pins.py:166`) tops out at RED:

```
>= 80 -> RED    50-79 -> YELLOW    < 50 -> GREEN    (None -> STALE)
```

RED is the ceiling, so private_credit at **98.8** and a channel at **80.1** paint the same
`#ef4444`. `ch.score` is already in the payload and already on screen as a numeric badge — the
gap is purely that the *colour* throws the gradient away. That is a real legibility defect and
it deserves a fix.

It does **not** license a fourth severity tier. The history says there is no defensible cut.

## What the history actually says

Hindcast: 3,984 channel-months across 12 channels, 396 RED (9.94%), 115 episodes, **14 hits**.

**1. A 95+ band is not selective.** 170 of 396 RED months (43%) score >= 95, because the score
saturates: 111 RED months (28%) sit at exactly 100.0.

**2. The proposed band's interior never hit.** Splitting the 95+ stratum:

| peak score | hits / resolved | rate |
|---|---|---|
| 80–94.9 | 7 / 69 | 10.1% |
| **95–99.9** | **0 / 12** | **0.0%** |
| exactly 100 | 7 / 26 | 26.9% |

Every hit in the 95+ stratum has a peak of *exactly 100*. **Casey's motivating example — 98.8 —
lands in the sub-band that went 0-for-12**, below the band beneath it. The apparent "95+ = 18.4%"
is a two-point mixture, not a gradient.

**3. The remaining gap is exposure time, not severity.** `_episodes()` anchors `window_end` to the
*last* red month, so longer episodes buy longer windows in which any event can count:

| | peak 80–95 | peak 95+ |
|---|---|---|
| mean episode length | 1.6 mo | 7.0 mo |
| mean damage window | 5.5 mo | 10.0 mo |
| hits per 1000 window-months | **18.6** | **18.4** |

Exposure-normalised the two strata are **identical** (exact binomial two-sided p = 1.000).
Mantel-Haenszel stratified by window-length tercile: +2.2pp, not +8.3pp.

**4. The evaluation is not reproducible in real time.** `window_end` depends on when the episode
*will* end — unknowable at the moment a channel prints 98. Recomputed with the only real-time
window (`peak+lag_lo .. peak+lag_hi`): 95+ = 13.2%, 80–95 = 10.0%, Fisher p = 0.750. Concretely,
`basis_trade` peak 2023-05 carries a **43-month** window off a documented 2-month lag, and is
credited with the 2025-01 drawdown.

**5. No threshold survives multiplicity.** Best raw cut is 90 (p = 0.047), not 95; `==100 vs <100`
gives p = 0.039. Permutation test on min-p across the whole 82–99 scan: **p = 0.175**. Nothing
survives. Anyone reporting 90 or 100 as "the" threshold is overfitting 14 events.

**6. The sample cannot speak.** MDE at 80% power with n = 38/69 and a 13.1% base rate is a 95+ rate
of **0.38 (2.9x base)**. The observed 18.4% was never detectable. "p = 0.243 therefore no effect"
would be an invalid reading — the correct statement is that the design has no resolution here,
*and* that what signal appears is fully explained by exposure and clamping.

**Therefore the marker carries NO predictive claim.** Any wording implying higher forecast
severity — "CRITICAL" above all — is blocked.

## Why not a fourth status value

The design counter-agent simulated it (patched `_status_from_score`, extended `RANK`, ran the
suites). Fed the two hottest readings the instrument can physically produce (oil +140% y/y,
HY OAS +380bps/20d, both scoring 100):

```
oil status = CRITICAL   credit status = CRITICAL
overall    = GREEN      <-- "No spark visible in monitored channels"
n_red      = 0          exposure red = $0.0T   ($44T of stressed mass left every bucket)
accident gauge: RED -> YELLOW, fast_red = False
transmission: active = False
```

Roughly 15 `== "RED"` comparisons silently miss a promoted channel, including
`composer/scripts/monitor.py:83-91`, which would fire a **false "accident composite RESET"
Telegram to Casey** and cancel the still-tripped reminder. A monitor that goes quiet as its
reading maxes out is the one bug class never worth a legibility win.

Naming it `CRITICAL` is the worst available option: `PinStatus` stays a subset of `MetricStatus`
so TypeScript compiles **clean**, `STATUS_COLOR` resolves `#dc2626` vs RED's `#ef4444` — two reds
one shade apart, i.e. the legibility win is ~zero — and it collides with `base.py:17`, which
reserves CRITICAL for override events. Without `RANK` extended it is worse still: a hard
`KeyError` at `pins.py:223` takes the whole board to a 500.

## What ships

**Primary — a continuous intensity ramp. No threshold, no claim.** This is the honest answer to a
dataset with no defensible cut, and it fully solves the reported complaint.
1. `pinColor(status, score)` in `frontend/src/lib/format.ts` beside `STATUS_COLOR`: for RED,
   interpolate `#ef4444 -> #991b1b` across score 80->100. Apply to pill, severity bar, part dots,
   mass-map bar.
2. Scale the numeric score badge's weight/size with the score so it reads at a glance
   (`PinBoard.tsx:270`).

**Secondary — a measurement-ceiling marker at `score >= 99.95`, labelled "at anchor ceiling".**
Not a severity tier. It states a fact about the *instrument*: this reading is pinned at its
documented extreme anchor, so the score cannot distinguish worse from much-worse. That is
genuinely useful and makes no forecast. Icon + label, never colour alone.

**Additive backend fields** — subset-shaped, never replacements, so every existing invariant
survives untouched:
```python
board["n_at_ceiling"]            # count of RED channels with score >= 99.95; SUBSET of n_red
board["ceiling_channels"]        # list[str]
exposure["ceiling_trillions"]    # SUBSET of red_trillions
channel["at_ceiling"]            # bool, alongside status == "RED"
```
A ceiling channel **is still RED**. `RANK` gains no key. `PinStatus` and the persisted
`pins_overall` vocabulary are unchanged. `pin_history.RED_LINE` stays **80.0**.

### RED_LINE stays 80 — non-negotiable

`RED_LINE` is the episode-formation instrument, not a display threshold, and it is frozen into
published dated results. Moving it would collapse episode counts and damage windows, recompute
`_overlap_validation`, falsify shipped numbers ("44% vs 20% base, 5 of 11 clusters") hard-coded at
`pins.py:721-727`, `PinBoard.tsx:124` and `glossary.ts`, and desynchronise
`studies/pin_rule_hindcast.py:134` (independently hard-codes `>= 80`) from the deployment. That is
a re-run-and-refreeze-the-study change, not a UI tweak.

## Merge-blocking gate tests

```python
# no 4th status value ever creeps in
assert set(RANK) == {"GREEN", "YELLOW", "RED"}
assert {_status_from_score(s) for s in (0,49.9,50,79.9,80,94.9,95,100)} <= {"GREEN","YELLOW","RED"}
assert pin_history.RED_LINE == 80.0

# saturation NEVER demotes the headline or the mass buckets
board = build_pin_board(<oil +140% fixture>)
assert board["overall"] == "RED"
assert board["n_red"] >= 1
assert board["n_at_ceiling"] <= board["n_red"]            # subset invariant
e = board["exposure"]
assert e["ceiling_trillions"] <= e["red_trillions"]       # subset invariant
assert e["red_trillions"] >= 20.0                         # a ceiling channel is STILL red mass
assert e["red_trillions"] + e["yellow_trillions"] + e["green_trillions"] <= e["monitored_trillions"]

# fast-channel saturation still trips the gauge and the transmission note
g = build_pin_board(<hy +380bps + flat curve>)["accident_gauge"]
assert g["fast_red"] is True and g["status"] == "RED"
assert transmission_note(board_with("credit_event", 100.0), 35.0)["active"] is True
```

## Honesty box (frozen 2026-09-10)

- n = 3,984 channel-months / 115 episodes / **14 hits**. Underpowered for any stratification.
- The 14 hits map to only **8 distinct macro events** — `2018-09`, `2020-03` and `2025-01` supply
  3 each. Effective n for the outcome is ~8, not 107.
- My first-pass reasoning was **wrong in method**: the cluster bootstrap by channel is
  *anti-conservative* here (90% CI [-1.5, +16.9] is narrower than the naive iid resample's
  [-3.7, +20.2]) and clusters on the wrong axis. Time-clustering is the binding problem. The
  conclusion survived; the route to it did not.
- 65% of all 95+ months are the anchor clamp, dominated by `basis_trade` (72% of its 95+ months
  are exactly 100) and `plumbing` (86%).
- Four cushion legs cap at 79 (RRP buffer, 10y JGB, SPY/RSP, VRP) and can never reach the ceiling.
- Five channels (`credit_event`, `fiscal`, `uncertainty`, `demand_strike`, `concentration`) never
  reach 100 at all, so the marker is structurally a basis_trade / plumbing / oil badge.
- NOT modelled: whether saturation frequency has itself changed over time.

## Two source bugs found en route — FIXED 2026-09-10

Both are now fixed in `pins.py` / `pin_history.py` with merge-blocking gate tests in
`tests/test_pin_scoring.py`. **Today's live board is bit-for-bit unchanged** (positioning
percentile 62.6, net short 93.1, reserves 25.0 — all identical); only the hindcast moves.

| | before | after |
|---|---|---|
| plumbing RED months | 60 | **18** |
| plumbing at-ceiling (100) months | 24 (all 2003-11..2008-03) | **0** |
| basis_trade RED months | 101 | **38** |
| basis_trade at-ceiling months | 53 | **19** |

Face validity holds: plumbing's surviving REDs are exactly the ample-reserves QT drains
(2018-08..12, 2019-01..05 — the drain that produced the Sept-2019 repo spasm — and
2022-04..10), with zero pre-2009 noise. The gate degrades to STALE, and a STALE fast
channel reports `fast_red: None` (unknown) with `unknown: ["fast channels"]`, never a
silent all-clear — verified.

**Three of the hindcast's 14 hits disappear**, all of them artifacts: plumbing 2007-10
(credited with the 2008-01 onset, from the pre-QE reserve artifact), and basis_trade
2017-12 and 2023-04/05 (credited with the 2018-09 and 2025-01 drawdowns, both driven
entirely by the crowding gauge, not the level leg). The 2023-05 episode is the same one
the statistics counter-agent flagged as the worst lookahead offender — a 43-month damage
window off a documented 2-month lag.

Consequence: `studies/pin-rule-hindcast.md`'s "44% vs a 20% base, 5 of 11 clusters" is
**no longer the measured result** — both fixed channels are in `FAST_HIGH_MASS`, the set
those rules key on. That doc is marked STALE; `pin_rule_hindcast.py` must be re-run after
the redeploy and the numbers re-frozen at every hard-coded site.

### The original diagnosis

1. **`plumbing` reserves anchor is meaningless pre-2008.** All 24 of plumbing's exactly-100 months
   fall in 2003-11..2008-03. `Reserves, 26-week change` anchors `(0,-8,-15,-25)`; pre-QE reserve
   balances were ~$10–40B, so <=-25% swings were routine noise. This artifact supplies 6 of the
   95+ episodes and one of the 14 hits (plumbing 2007-10, credited with the 2008-01 onset).
2. **`basis_trade` percentile part pins at 100 on every new expanding-window high.**
   `Positioning percentile (vs 2010+)` anchors `(50,85,95,100)`; `_expanding_percentile` returns
   exactly 100.0 whenever the current value is the running max, and leveraged-fund net short has a
   secular uptrend — so it has been pinned for long stretches since 2010.

## Pending DD questions

| # | P | Question | What it would move |
|---|---|---|---|
| 1 | P1 | Should the extreme anchors be re-calibrated so 100 is genuinely rare, rather than layering a marker on a saturating scale? | Would replace this spec. The real defect may be anchor calibration, not the colour map. |
| 2 | ~~P1~~ | ~~Fix the two source bugs before or after this change?~~ **RESOLVED 2026-09-10 — both fixed first.** | The ceiling marker will now light on genuine readings only; the clamp pile-up drops from 111 RED months to ~53. |
| 3 | P2 | Should `monitor.py` alert on `n_at_ceiling`, and at what cadence? | Decides whether the additive fields earn their place over a pure CSS ramp. |
| 4 | P2 | Should `_episodes` gain a real-time-computable window alongside the retrospective one? | Would make every hindcast hit-rate on this board prospectively honest. |
| 5 | P3 | Should `pins_overall` get a `pins_schema_rev` stamp for R2 calibration comparability? | Track-record continuity across deploys. |
| 6 | P1 | Re-run `pin_rule_hindcast.py` after redeploy and re-freeze "44% / 5 of 11" at all five hard-coded sites. | Those numbers are currently STALE and displayed as live truth in the UI. |
| 7 | P2 | Is the basis_trade level anchor `(2, 4, 5.5, 8)` M contracts still right for a book that grew ~2.5x since 2020? After the cap the level leg alone reaches RED only from 2023-08. | Decides whether the channel has any usable pre-2023 history at all. |
| 8 | P2 | The channel never flagged March 2020 — its own founding episode — peaking at 79.1, a tenth of a point under RED. Pre-existing, not caused by the fix. | Face validity of the basis_trade channel. |

## Counter-agent log (mandatory pass, CLAUDE.md)

**Counter-agent A — statistics/data integrity.** Verdict: conclusion CORRECT in direction,
**reasoning not defensible as first written**. Recomputed every headline number independently
(all confirmed, no arithmetic errors) and then found the fatal confound (exposure time), the
0-for-12 interior, the anti-conservative bootstrap, the real-time-window failure, and the
multiplicity problem. Recommended the marker be labelled "clamped at anchor", never "95+" or
"critical". Three of its load-bearing claims were re-verified independently by the parent before
adoption: the 0-for-12 interior, the 18.6-vs-18.4 exposure normalisation, and the 9-of-14-hits
concentration — all reproduced exactly.

**Counter-agent B — design/blast radius.** Verdict: **ship as presentation layer; do not introduce
a fourth `PinStatus` value.** Empirically simulated the change and produced the false-GREEN
demonstration above. Identified the `RANK` KeyError, the ~15-site `== "RED"` promotion class, the
cross-service false Telegram, the gray-render failures in `PinBoard.tsx`/`ui.tsx`, the
`RED_LINE`-is-frozen argument, and the persisted-`pins_overall` comparability break. Supplied the
additive-subset-field design adopted above.

Both verdicts were adopted. The 95+ threshold in rev 1 was **withdrawn** as a result of pass A.
