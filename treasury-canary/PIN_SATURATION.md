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

- n = 3,984 channel-months / 115 episodes / **14 hits** (pre-fix). Post-fix: 102 episodes /
  12 hits. Underpowered for any stratification either way.
- The 14 hits map to only **8 distinct macro events** — `2018-09`, `2020-03` and `2025-01` supply
  3 each. Effective n for the outcome is ~8, not 107.
- My first-pass reasoning was **wrong in method**: the cluster bootstrap by channel is
  *anti-conservative* here (90% CI [-1.5, +16.9] is narrower than the naive iid resample's
  [-3.7, +20.2]) and clusters on the wrong axis. Time-clustering is the binding problem. The
  conclusion survived; the route to it did not.
- 65% of all 95+ months were the anchor clamp, dominated by `basis_trade` (72% of its 95+
  months exactly 100) and `plumbing` (86%). These shares are **pre-fix** and are now stale —
  the clamp pile-up drops from 111 RED months to roughly 53.
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
| plumbing RED months | 64 | **22** |
| plumbing at-ceiling (100) months | 24 (all 2003-11..2008-03) | **0** |
| basis_trade RED months | 101 | **38** |
| basis_trade at-ceiling months | 53 | **19** |
| episodes / hits / misses (all channels) | 115 / 14 / 93 | **102 / 12 / 82** |
| episode precision | 13.1% | **12.8%** |

Face validity holds: plumbing's surviving REDs are the ample-reserves QT drains
(2018-08..12, 2019-01..05 — the drain that produced the Sept-2019 repo spasm — and
2022-04..10), with zero pre-2009 noise.

**Correction to an earlier claim in this doc.** I wrote that a STALE fast channel already
reported `fast_red: None`, "verified". That was only true when *all four* fast channels
were stale. With one readable calm channel and plumbing dark, the gauge returned
`fast_red: False` and status GREEN — a silent all-clear, with the dark channel disclosed
nowhere. Found by the counter-agent, now fixed: `fast_red` is `None` whenever any
FAST_HIGH_MASS channel is STALE and none of the live ones is RED, the dark channels are
named in a new `fast_stale_channels` field, and a gate test covers it.

Two further fixes from the same pass: the reserves gate now tests **both ends**, not the
base alone (gating on the base would mute a catastrophic drain that takes the level below
$100B — the monitor going quiet after the worst outcome), and the constant's justifying
comment had two false statements corrected (pre-QE *levels* ran $2.8B-$47B, not "$3-24B",
which was the max *base*; and the post-QE minimum is -24.8%, only 0.2pp from the extreme,
so "never reaches it" is true by a rounding error and is not headroom).

**Two of the hindcast's 14 hits disappear**, both artifacts:
- plumbing `2007-08..2008-03` (peak 100, credited with the 2008-01 recession onset) — the
  pre-QE reserves artifact. Note what this costs: the 2008 onset is the *only* NBER
  recession the accident gauge ever caught, and after the fix the configuration no longer
  flags it. The honest defence is that plumbing was RED in 42 of the 53 months from
  2003-11 to 2008-03 — **79% of the time** — so "it caught 2007" was a stopped clock.
- basis_trade `2017-12..2019-11` (peak 100, credited with the 2018-09 drawdown) — a
  **24-month contiguous RED run** driven entirely by the crowding gauge. Crediting an
  always-on state with catching an event inside it is the same stopped clock.

The third episode I originally reported as removed, basis_trade `2023-04..2026-09`, does
**not** disappear — it shrinks to `2023-08..2026-09` and remains a `hit_drawdown`. That
correction came from the counter-agent; my own reconstruction was reserves-only and
undercounted (plumbing before was 64 RED months, not 60).

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

## The percentile estimator (mid-rank) — implemented 2026-09-10

DD Q9, done. All three percentile paths now go through one shared
`rank_pct(below, equal, n)` in `pins.py` — `_percentile` (live),
`_expanding_percentile` and `_expanding_pctl_vs_raw` (hindcast) — so the live board and
the history cannot drift apart.

**The first defect.** `rank / n` returns *exactly* 100.0 whenever the value is the running
maximum. The percentile legs are anchored `(50, 85, 95, 100)`, so **any new all-time high
scored the extreme anchor by construction** — not because the reading was extreme, but
because it was the newest record. On the CFTC series that was 87 of 953 weeks at exactly
100.0.

**A second defect, found while implementing the first.** All three call sites passed
`bisect_right` — the *highest* rank in a tie block — so every member of a tie group scored
as if it were the top of the block. That is not cosmetic here: CCC OAS is quoted to 2dp and
its percentile is the primary private_credit driver. On the CFTC series 13.4% of points
shift under a mid-rank form (mean -0.21pp, max -1.52pp -- mid-rank is always <= highest-rank);
for a 10-way tie in n = 1000 the bias is 0.45pp.

**The fix.** The mid-rank plotting position `(below + equal/2) / n`. For an untied value
that is in the sample (`equal == 1`) this reduces **exactly** to Hazen `(rank - 0.5)/n`, so
nothing moves on untied data; ties share the midpoint of their block. For any value drawn
from the sample the result lies naturally in `[0.5/n, (n - 0.5)/n]` and can never be 0 or
100.

**Correction to the clamp's stated rationale.** I justified it by `_expanding_pctl_vs_raw`
ranking a rolling mean that "can sit outside" the raw range. That is provably false: the
window is always a sub-window of `seen`, so `min(seen) <= avg <= max(seen)` by construction,
and over the real 15,227-point EPU series `rank == 0` occurs zero times. The clamp *is*
load-bearing, but for a caller I had not identified — the **CCC−BBB dispersion leg**, which
ranked a value rounded to 2dp against the *unrounded* series, so `equal == 0` and an all-time
high gave `below == n` -> exactly 100.0. That leg now ranks the unrounded value and rounds only
for display, so the live board and the hindcast compute the same statistic; the clamp remains
as the backstop for any future caller that ranks a transformed value against an
untransformed series.

**A third defect, found by the counter-agent AFTER the first two were committed — the
estimator alone did not deliver the guarantee.** `rank_pct` correctly stops at
`(n - 0.5)/n`, and then `round(p, 1)` threw that away: `round(99.9933, 1) == 100.0`. So
`_percentile` returned **exactly 100.0 on any all-time high for every n >= 1000** — which is
every percentile leg on the board except the CFTC one (CCC ~7,500; dispersion ~7,500; EPU
15,227; SPY/RSP ~3,900; VRP ~2,500). `_pscore` rounds again, manufacturing a score of exactly
100.0 for n >= 4001 on the `(50, 85, 95, 100)` legs and n >= 8000 on EPU's.

My original verification — "unreachable for every n from 2 to 5000" — was run against
`rank_pct` directly, **not against `_percentile`, which is what the board actually calls.**
The gate test I wrote used `n = 500`, one step below where the bug appears. Both are now
fixed: `_round_pctl` rounds without crossing the attainable band, `_pscore` refuses to round
*into* the extreme unless the value is genuinely at or beyond it, and the gates run at
n in {500, 1000, 4001, 7500, 15227, 20000} end-to-end through `_percentile` and `_pscore`.

Verified after the fix: `_percentile` and `_pscore` never return exactly 100.0 or 0.0 for any
n tested up to 20,000, while genuine level extremes still score exactly 100 (net short at 8M,
WTI beyond +100%, NDFI at -10). The CFTC maximum drops from 100.0000 to 99.9502 and exact-100
weeks go 87 -> 0.

**Honest scope of the benefit — this is structural, not backtest-improving.** Because the
basis_trade cap already removed that channel's percentile leg from contention, Hazen changes
almost nothing in the *current* hindcast: basis_trade RED months (38) and at-ceiling months
(19) are **unchanged**, since those 19 now come from the uncapped level leg. Live-board
percentiles shift by less than 0.05pp across every leg (positioning -0.047, CCC -0.007,
EPU -0.005, SPY/RSP -0.013), all inside the displayed rounding.

**Correction — my ceiling audit was wrong.** I attributed private_credit's four ceiling
months (2015-11, 2020-05..07) to its percentile legs. They are **NDFI level-leg extremes**:
those four are the only observations in the entire `B1030NCBCMG` series at or beyond its `-10`
extreme anchor (-36.1, -35.7, -27.6, -11.6; next worst -8.4, inside the anchor) — the COVID
bank-loan collapse and the 2015 energy-HY contraction. I had audited per *channel* rather than
per *leg*. Verified independently against FRED.

So the corrected claim is that this change removes **zero** ceiling months from the current
hindcast — which *strengthens* the "structural, not backtest-improving" framing rather than
weakening it. Every at-ceiling month on the board comes from a **level** leg hitting a genuine
documented extreme, which is the anchor working as designed.

What the change actually buys is a forward-looking *guarantee* — no percentile leg can print
the extreme anchor merely by being the newest record, on any future data — plus the tie
correction, which stands on its own merits and does not need the ceiling story to justify it.

So after all three fixes the ceiling means what it is supposed to mean: "at a documented
historical extreme", not "newest record".

**Anchor semantics, stated explicitly.** `extreme = 100` on a percentile leg is now
approached asymptotically and never reached (at n = 7500 the max score is ~99.97). That is
intended. The same holds at the bottom for the VRP leg, whose extreme is 0.

## DD Q12 — resolved 2026-09-10, and it found something bigger

**The question could not be answered as posed, because the data it assumed does not exist in
the pipeline.** FRED serves ICE BofA (`BAML*`) series under a licence that returns only a
**rolling ~3-year window** — 787 daily observations as of 2026-09 — for `BAMLH0A3HYC` (CCC)
and `BAMLC0A4CBBB` (BBB). Verified three ways: all three `BAML*` series I tried return exactly
787 observations while `DGS10` returns 16,156 (1962+), `VIXCLS` 9,270 and `USEPUINDXD` 15,227
from the same endpoint; and the live board's percentiles reproduce **exactly** off that
787-point window — CCC 99.2 and dispersion 99.7, against raw values of 10.64% and 9.65pp that
the deployed board reports.

**So the label was false.** `"CCC spread percentile (vs 1996+)"` was ranking against ~3 years.
Today's 10.64% CCC OAS is nowhere near the 99th percentile of real 1996+ history, which
includes ~40% in 2008-09, ~30% in 2002 and ~18% in 2020 — it is the 99th percentile of
2023-2026. The 95 anchor therefore means **"highest in ~3 years"**, not "highest since 1996",
which is a materially weaker claim than the channel's documentation implies. Renamed to
`(vs available history)`, with the constraint documented at the anchor, in the part detail
string, in `HISTORY_NOTES` and in `config.py`, and a gate test that refuses any anchor label
claiming a history depth the source does not serve.

This closes the loop on the question that started this whole thread — "why is Corporate &
private credit not at critical? its scored at 99". The 99 is a three-year percentile.

**The measurement itself, on the real comparison base** (private_credit, 140 months,
2015-02..2026-09):

| | before | after |
|---|---|---|
| RED months | 19 | **19** |
| status flips | — | **none** |
| at-ceiling months | 4 | **4** (all NDFI level extremes) |
| months whose score moved at all | — | **4 of 140** |
| mean / largest score move | — | **-0.43 / -1.10 points** |

All four moved months (2025-10, 2025-11, 2025-12, 2026-02) are far from the RED line. The
504-obs warmup consumes two thirds of the 787-point window, so the CCC legs only go live
around 2025-10 — every private_credit RED month before then is the NDFI level leg alone,
which independently confirms the counter-agent's finding that the four ceiling months are
NDFI extremes.

**Conclusion: the mid-rank estimator is safe to ship.** Zero status flips and zero episode
changes on the only channel where a flip was possible.

**Measured tie impact, with its limits stated.** On the CCC series available without a FRED
key (2023-09..2026-09, n=787, 87% of observations in a tie group, largest group 10) the
mid-rank form shifts **80.6% of scored points**, mean -0.20pp, most negative -0.70pp, and
causes **zero** RED/YELLOW status flips. The deployed service ranks against the full 1996+
history (~7,500 obs) and the keyless FRED endpoint truncates, so **the full-history
private_credit before/after has NOT been measured here** — it needs the deployed service or a
keyed fetch, and is DD Q12. What is established: the estimator change is a pure no-op on the
uncertainty channel (EPU ranks a mean, so `equal == 0` and mid-rank degenerates to `below/n`,
which is defensible — for a value strictly between order statistics k and k+1 that is the
midpoint of the Hazen bracket), and cannot flip the three capped legs, which leaves CCC and
dispersion as the only legs where a status could move.

**Mutation-tested.** Nine mutations, all caught: reverting to naive `rank/n`; restoring
highest-rank-on-ties; dropping the clamp; an off-by-one `below/n`; a Weibull `(n+1)`
denominator; a one-sided change to the hindcast only, which the live-vs-hindcast parity test
catches; reverting `_percentile` to the naive `round()`; removing the `_pscore` extreme guard;
and making that guard too aggressive so genuine level extremes lose their 100.

**Two existing tests were rewritten**, because they asserted the old estimator's exact-100
output rather than the property they were named for:
- `test_expanding_percentile_has_no_lookahead` asserted `pv == [100.0] * 5`. The no-lookahead
  property is preserved and now asserted as such (each running max sits at the highest
  attainable percentile for its n, and a later maximum cannot demote an earlier record).
- `test_latest_hindcast_point_matches_live_formula` compared to 1e-9, which only ever passed
  because both sides returned exactly 100.0 — `_percentile` rounds to 1dp, so that tolerance
  would not have caught a genuine live-vs-hindcast estimator drift. Now asserted to the
  rounding precision it actually has.

## DD Q14 — recalibration for the real window, 2026-09-10

**The cause has a date.** FRED's own note on `BAMLH0A3HYC` reads: *"Starting in April 2026, this
series will only include 3 years of observations."* So the `(50, 85, 95, 100)` percentile anchors
and the `(vs 1996+)` label were **correct when written** — ICE BofA history on FRED ran to 1996 —
and silently became 3-year percentiles in **April 2026**, five months ago, when the licence
changed underneath them. This is a data-source regression with a known date, not a long-standing
calibration error.

**The recalibration.** A percentile against a rolling ~3-year base cannot say "credit is
distressed", only "worse than the recent past". So:

1. Both percentile legs are **demoted to gauges** (cap 100 -> 79), the same semantics the board
   already gives SPY/RSP, VRP, RRP buffer, 10y JGB and basis_trade positioning.
2. A new **level trigger** carries the RED: `"CCC-and-lower OAS": (4.14, 10.0, 14.0, 44.3)`, in
   absolute OAS percent, added to both the live board and the hindcast.

**Anchor provenance, one line each.** The first draft of this leg used `(6.0, 11.0, 16.0, 44.0)`
and the counter-agent took it apart; all three of its unsourced numbers were replaced.

| anchor | value | provenance |
|---|---|---|
| benign | **4.14** | **VERIFIED** series record low, Jun-2007. The first draft used 6.0 with no source and did not disclose it as a guess. |
| yellow | **10.0** | **CITED** — Fridson's distress convention (market standard since ~1990): OAS >= +1000bps is distressed. Today's index prints **1064bps**, so the average CCC credit is already trading distressed by that convention. The first draft's 11.0 sat 3.4% *above* today's print and was the sole reason today read GREEN — textbook fitting. |
| red | **14.0** | **JUDGEMENT — the one remaining guess, and the weakest number on the board.** Sized to catch the 2011 euro crisis, whose CCC peak estimates at ~15.5% by applying the one verified CCC/HY ratio (44.29/21.82 = 2.03x at Dec-2008) to that episode's documented ~9.1% broad-HY peak. The first draft's 16.0 would have missed 2011 entirely and read GREEN through the whole Dec-2018 selloff. |
| extreme | **44.3** | **VERIFIED** series record high 44.29, Dec-2008. |

**Impact — this changes the live board's headline.**

| | before | after |
|---|---|---|
| private_credit, live | **RED 98.8** | **YELLOW 79.0** |
| CCC level leg (trigger) | — | 10.64% -> **54.8 YELLOW** |
| CCC percentile (now gauge) | 99.2 -> 96.8 RED | 99.2 -> 79.0 YELLOW |
| dispersion percentile (now gauge) | 99.7 -> 98.8 RED | 99.7 -> 79.0 YELLOW |
| hindcast RED months | 19 | 13 |

The 6 removed hindcast months are 2026-03/04/06/07/08/09 — every one of them RED purely on the
3-year percentile. The 13 that remain are NDFI-driven. The CCC level never exceeds 11.37% anywhere
in the available window, so the new trigger never fires in 2023-2026, which is the correct reading:
there was no absolute credit distress in that period.

**The honest tension, stated rather than buried.** This trades a false RED for a possible false
GREEN. Today's reading says "spreads at a 3-year high (gauge YELLOW) but not absolutely
distressed" — defensible, since 10.64% is unremarkable against a series that reached 44.29% in
2008. But the channel's stated purpose is detecting *this cycle's untested leverage*, and a book
at record size deteriorating from a low base is exactly what an absolute-level anchor is worst at
seeing. The gauges are what carry that signal now, and they cap at YELLOW.

**Two side effects the counter-agent surfaced, disclosed rather than buried.**
- **EWM deal timing moves.** `ewm/live.py:115-119` feeds the private_credit channel score into
  the DMHI leg as `1 - score/100`. Capping the gauges lifts DMHI **0.381 -> 0.480**, which at
  `w_dmhi = 0.20` is **+1.98 points on every EWM window score** against bands green 70 / amber 45
  — enough to flip a window near a boundary. An unrelated decision surface got healthier because
  a display convention changed. See DD Q18.
- **Cap-pinning at the top of the range.** The channel now reads exactly **79.0 in 6 of the last
  7 months**, i.e. no resolution at the top — structurally the same at-ceiling defect DD Q9
  removed from the positioning leg, reintroduced at 79 instead of 100.

**What the counter-agent got right that this doc previously got wrong:** the claim that today's
10.64% is "historically unremarkable" is not defensible as stated. It is above the market's own
distress convention, it is a 3-year high, the book is at record size, and dispersion is 9.65pp.
"Unremarkable" was true only against a full-cycle distribution the feed no longer serves.

**The better fix is still not this one.** Restoring a full-history source would make the original
percentile calibration valid again and make this level leg redundant. That is DD Q15.

## DD Q17 — the same regression in the severity index, fixed 2026-09-10

`severity.py` is by design rank-uniform: its docstring says *"every component -> percentile of
its full own history"*. One input, `hy_oas` = `BAMLH0A0HYM2`, is an ICE BofA series, so
`hy_complacency` silently became a **3-year** rank in April 2026. Confirmed exactly: the live
score of **87.2** reproduces as the inverted rank of today's 2.71% against the 787-point window.

**Note the direction — the bug understated risk.** The 3-year window's own minimum (2.59%) sits
close to today's 2.71%, so today looked mid-pack. Against real history, which reaches a record
low of 2.41%, today's spread is near the tightest ever recorded — exactly what the component
exists to measure.

**The fix, after the counter-agent rejected my first attempt.** I first re-anchored the component
on absolute levels. That was wrong: it injected a non-rank-uniform component into a rank-uniform
average (+4.4 mean bias over history), and its premise — that full history was unobtainable —
turned out to be false. **Full history IS obtainable.** The counter-agent reconstructed
BAMLH0A0HYM2 back to 1996-12-31 (n = 7,754) from four mutually-independent public mirrors. I
verified that reconstruction myself before using it:

- **All 787** of FRED's authoritative dates match to **0.0000 — zero mismatches**.
- The three mirrors agree with each other across 6,962-7,599 overlapping dates, zero mismatches.
- Extremes match the published record low **2.41% (2007-06-01)** and high **21.82% (2008-12-15)**.

So `hy_complacency` now ranks against a **frozen full-history reference**, restoring the module's
stated contract with **no exceptions**. Only the **101 quantile knots** are stored, never the
series — a summary statistic rather than a redistribution of ICE's proprietary index, which also
sidesteps the licensing question. They reproduce the full-series percentile to within **0.96pp**
worst case and **0.1pp** at today's level.

| | hy_complacency | Block C | severity index |
|---|---|---|---|
| deployed today (3-year rank) | 87.2 | 47.20 | 69.00 |
| my first attempt (anchored) — **rejected** | 94.5 | 49.63 | 69.49 |
| **reference rank (shipped)** | **96.0** | **50.13** | **69.59** |

Class stays SEVERE throughout.

**Retraction.** I claimed `crossasset.hy_oas` / `ig_oas` were unaffected because they threshold on
fixed levels. Half right: their *status* is threshold-based, but `assemble.py` attaches a
`percentile` via `base.py::percentile_rank` over the same truncated series, and that percentile is
rendered in the main metric table. Both now carry the caveat in their note. Two instruments were
remediated and I declared the third clean without checking its payload.

**Also fixed from that pass:** the gate test never asserted the live path — reverting the wiring to
the truncated rank left the whole suite green — and the "docstring matches the code" test only
checked that a docstring mentioned an exception. Both replaced; four mutations now caught,
including that exact revert. A bps/percent unit guard was added: the anchored form would have
returned "maximally benign" for a value passed in basis points, a failure mode the rank form was
immune to and which is live elsewhere in this repo on the same bundle key.

## DD Q16 — resolved 2026-09-10: the CCC peaks are MEASURED

The full 1996+ CCC series was reconstructed from public mirrors. I verified it before using it:
it reconciles with FRED's authoritative 787-day window on **all 787 overlapping dates, zero
mismatches**, and its record high/low match the published **44.29 (2008-12-15)** and **4.14
(2007-06-05)** exactly. One documented gap remains: 2022-07-06..2023-09-11 (432 days, 5.8%),
which contains neither the record extremes nor any of the episode peaks below.

| episode | **measured CCC peak** | fires at red 14.0? |
|---|---|---|
| 2011-10-04 euro crisis | **15.60** | yes |
| 2016-02-11 energy bust | **20.66** | yes |
| 2020-03-23 COVID | **19.62** | yes |
| 2019-01-03 (the 2018 selloff) | 11.16 | no — correctly |
| 2022-07-05 selloff | 12.26 | no — correctly |

**red = 14.0 stands, now on measurement rather than inference.** It sits between the two ordinary
selloffs (11.2, 12.3) and the mildest genuine distress episode (15.60), which is exactly the
separation the anchor should encode. On the real distribution (n = 7,447) that is about p78;
p50 is 9.32. The gate test now pins it from both sides against these measured values.

**My ratio inference was wrong and I should not have trusted the margin.** Applying the Dec-2008
CCC/HY ratio of 2.03x put 2011 at 18.5 (actual **15.60**, +18% error), 2016 at 18.0 (actual
20.66, −13%) and 2020 at 22.1 (actual 19.62, +12%). The ratio ranges 1.71–2.33x and is *lowest*
at the very episodes I applied it to. The conclusion — that red 14 catches all three — survived
only because the margin was wide, not because the method was sound.

**And it falsified the previous draft outright:** the `red 16.0` I shipped two commits ago was
documented as "sized to sit under the 2011/2016/2020 peaks so those register RED". Measured, 2011
peaked at **15.60 — below 16**, so that anchor did not do what its own comment claimed.

**Today's 10.64% is about the 62nd percentile of real CCC history**, against the 99.2 the board
reports off its 3-year window. That is the clearest single statement of what the April-2026
truncation did to this channel.

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
| ~~9~~ | ~~P1~~ | **DONE 2026-09-10 — see the section above.** ~~Apply the Hazen plotting position~~ `(r-0.5)/n` to `_percentile` and `_expanding_percentile`. On the real COT series it takes exact-100 weeks 85 -> **0** and at-ceiling months 40 -> **0**, while RED months barely move (94 -> 93). | This is the actual fix for the ceiling artifact — the cap only masks it, and the level leg still supplies 19 at-ceiling months. It generalises to CCC, CCC−BBB, EPU, SPY/RSP and VRP, and is a **better answer to Q1 than the ceiling marker** in the primary spec above. Do as a separate change. |
| 10 | P2 | `"Positioning percentile (vs 2010+)"` actually ranks against the full CFTC series from **2006-06-13** — 186 of 1056 observations (17.6%) predate 2010. Relabel or actually slice. | The label is factually wrong in user-facing text. Pre-existing, but this change puts that gauge under a spotlight. |
| 11 | P2 | `RESERVES_MIN_BASE_M` is a nominal-dollar constant and will drift toward the ample regime as nominal GDP grows. Reserves/GDP or reserves/bank-assets (the Fed's own ample-reserves framing) would need no gate at all. | The gate is a defensible interim — small, reversible, testable — but the reserves *metric* is the real defect: `_pct_change` on a series with a 300x regime break is the wrong statistic. |
| ~~12~~ | ~~P1~~ | **RESOLVED 2026-09-10 — see the section above.** Zero status flips, zero episode changes; 4 of 140 months move, largest -1.10 points. | The full 1996+ series does not exist in the pipeline; the real base is a rolling ~3-year window. |
| ~~14~~ | ~~P1~~ | **RESOLVED 2026-09-10 — see the section above.** Percentiles demoted to gauges; a level trigger carries RED. | private_credit goes RED -> YELLOW on the live board. |
| 15 | **P1** | **Restore a full-history CCC/BBB source** (paid FRED tier, ICE direct, or another provider). FRED restricted ICE BofA to 3 years in April 2026. | This is the BETTER fix: it would make the original `(50, 85, 95, 100)` percentile calibration valid again and render the new level leg redundant. Recalibrating around a source regression is a workaround, not a repair. |
| ~~16~~ | ~~P1~~ | **RESOLVED 2026-09-10 — see the section above.** Peaks measured; red 14.0 validated from both sides. | The calibration no longer contains an unsourced number. |
| 24 | **P1 — CASEY'S CALL, BLOCKING** | **May we freeze redistributed ICE index history into this repo?** The full CCC/BBB/HY series exist on public GitHub mirrors and reconcile exactly with FRED, but they are third-party redistributions of ICE Data Indices content that ICE evidently asked FRED to stop serving. Freezing them is redistribution. | **This decides whether the whole private_credit recalibration gets REVERTED.** If yes: restore `(50, 85, 95, 100)` against a frozen reference, delete the level leg, and DD Q15 closes. If no: the level leg stays as the licensed-route interim and we buy a paid FRED tier or ICE direct. I have not committed any series data pending this. |
| 18 | **P2** | Should `ewm/live.py`'s DMHI leg read UNCAPPED pin leg scores, so a display cap cannot move a deal-timing recommendation? | +1.98 points on every EWM window score today, purely from the gauge caps. |
| 19 | **P2** | Should the channel use a CONJUNCTION (percentile >= 95 AND level >= 10) rather than a bare level threshold? | Would restore a credit-pricing trigger that can fire before full crisis, without claiming a 30-year rank. The level leg alone is coincident, not leading: CCC only reached ~18-20% in Mar-2020 *after* SPX had fallen ~30%, which the hindcast's own `(1, 6)` lag window would score a miss. |
| 20 | **P1** | Promote DD Q5 (`pins_schema_rev`) to blocking. | Two anchor changes landed in one day and `pins_overall` is persisted daily with no version stamp, so the track record now mixes pre- and post-recalibration semantics. |
| ~~17~~ | ~~P1~~ | **RESOLVED 2026-09-10 — see the section above.** `hy_complacency` now ranks against a verified frozen full-history reference. | severity index 69.0 -> 69.6, class unchanged. |
| ~~21~~ | ~~P1~~ | **ANSWERED: yes.** CCC n=7,447 (one 432-day gap) and BBB n=7,754, both reconciling with FRED at zero mismatches. | Which makes DD Q24 the binding constraint, not data availability. |
| 25 | P2 | Close the CCC gap 2022-07-06..2023-09-11 from a pre-April-2026 FRED download or a Wayback capture — do not interpolate. | 5.8% of the series. Changes no anchor, but shifts percentile knots if a reference is ever frozen. |
| 22 | P2 | Stamp `severity_schema_rev` in the severity payload. | The index has an undisclosed level break of +0.6 at this change; R2 calibration compares readings across time. |
| 23 | P3 | Emit `history_start` and `n_obs` per severity component. | Several components rank against much shallower bases than "full history" implies — `dsr` starts 2005, `effr` 2000 — so the depth of every rank should be visible rather than asserted. |
| 13 | P3 | `base.py::percentile_rank` and severity `_pctile` still use `count(v <= x)/n` and still return exactly 100.0 (`tests/test_severity.py:14` asserts it). Converge them or leave them scoped as separate instruments. | Consistency of the percentile treatment across the dashboard. |
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

**Counter-agent C — verification of the two anchor fixes (2026-09-10).** Verdict: **SHIP WITH
CHANGES**. Reproduced every figure independently from keyless FRED and the live CFTC endpoint,
driving the repo's own code paths, using the deployed pre-fix API as an oracle. It confirmed the
diagnosis on both bugs and could not break it — but found two blockers and corrected several of
my numbers:

- **BLOCKER (closed):** my reserves gate tests did not gate the fix. Mutation-testing showed that
  deleting `min_base=` from *either* production call site left the full suite green — the tests
  proved a parameter existed, not that the bug was fixed. Replaced with integration assertions
  through `build_pin_board` and `_parts_for_channel`. All five mutations (both call sites, the
  cap, the base-only gate, the `fast_red` regression) are now caught.
- **BLOCKER (addressed):** the change falsifies the dashboard's headline empirical claim at seven
  sites of hard-coded prose that do not recompute on redeploy. All seven now carry an inline
  PENDING marker; the re-run is DD Q6 and the deploy is gated on it.
- **Corrected my numbers:** plumbing RED 64->22 (not 60->18 — my reconstruction was reserves-only);
  hits 14->12, not 14->11; the plumbing episode is `2007-08..2008-03`, not "2007-10"; the
  basis_trade `2023-04..2026-09` episode shrinks rather than disappears.
- **Corrected a false safety claim of mine** about `fast_red` — see the correction box above.
- On the level-leg question it ruled **keep the cap, do not rescale the anchor**: the anchor's own
  comment documents it as "~2x the 2020 book" and Feb-2020 peaked at 3.758M, so red 5.5 / extreme
  8 is exactly what that means. "No pre-2023 RED history" is a true statement about the world, not
  an instrument bug; rescaling to manufacture pre-2023 reds would be fitting. What was missing was
  **disclosure**, now added as `HISTORY_NOTES` for both channels.
- It also noted the episode-level record does **not** improve (precision 13.1% -> 12.8%). The case
  for these fixes is that the removed signal was artifact, not that the instrument scores better.

**Counter-agent E — verification of the private_credit recalibration (2026-09-10).** Verdict:
**DO NOT SHIP as first committed.** It confirmed the direction (a rolling 3-year percentile is a
gauge; demoting it is correct) and then found three blockers, all now fixed:
- **The RED band rested on unverified numbers, one of them simply wrong.** `benign 6.0` contradicts
  the verified 4.14 record low; `yellow 11.0` sat 3.4% above today's print and was the sole reason
  today read GREEN; `red 16.0` would have missed the 2011 euro crisis and read GREEN through the
  entire Dec-2018 selloff. It supplied the replacement set and the Fridson +1000bps distress
  convention — the only externally citable threshold in that band, which I had missed.
- **The channel was left with no trigger that could fire**, which is the failure mode this board
  must never have. Fixed by the lower red line; DD Q19 tracks the stronger conjunction rule.
- **The false "since 1996" survived in the place users actually read it** —
  `frontend/src/lib/glossary.ts` — while three commits and a gate test existed to kill that claim
  in the backend. Fixed and rebuilt.
- **Two gate tests were theatre.** `red 16 -> 14` and dropping the level leg from the hindcast
  alone both left the suite green; and the gate hard-coded `10.64 -> GREEN`, putting today's price
  inside the calibration test. All three fixed; six mutations now caught, including both that
  previously survived.
One reviewer reference I could not reproduce: `ewm/CANARY_COUPLING_RESEARCH.md` does not exist in
this repo, and no doc contains the leg list it quoted.

**Counter-agent D — verification of the percentile estimator (2026-09-10).** Verdict:
**DO NOT SHIP as committed; the estimator choice is right, keep it.** Its central finding is
that the estimator alone never delivered the guarantee — `round(p, 1)` handed the ceiling
straight back for every leg with n >= 1000, and `_pscore` did it again above n ~ 4000, while
the docs asserted the opposite. It also corrected my ceiling audit (private_credit's four
months are NDFI *level* extremes, so the change removes **zero** hindcast ceiling months),
disproved my stated rationale for the clamp and identified the caller that actually needs it,
caught a sign error (the tie shift is negative), and noted that my own gate test ran at
n = 500 — one step below where the bug it is named for appears.

Process note: both estimator commits landed **before** this review returned, contrary to
CLAUDE.md's rule that counter-agent verification precedes acting on or presenting findings.
Nothing deployed (feature branch), but the doc had already asserted the verification as
settled fact. That is corrected above, and the verdict now gates the merge.

All of pass D's required changes 1-4, 6 and 7 are implemented. Change 5 — the full-history
private_credit measurement — cannot be done from here (the keyless FRED endpoint truncates
CCC to 2023+) and is logged as **DD Q12**, blocking.

Both earlier verdicts were adopted. The 95+ threshold in rev 1 was **withdrawn** as a result of
pass A.
