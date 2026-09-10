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

## The percentile estimator (Hazen) — implemented 2026-09-10

DD Q9, done. All three percentile paths now go through one shared `hazen_pct(rank, n)` in
`pins.py` — `_percentile` (live), `_expanding_percentile` and `_expanding_pctl_vs_raw`
(hindcast) — so the live board and the history cannot drift apart.

**The defect.** `rank / n` returns *exactly* 100.0 whenever the value is the running
maximum. The percentile legs are anchored `(50, 85, 95, 100)`, so **any new all-time high
scored the extreme anchor by construction** — not because the reading was extreme, but
because it was the newest record. On the CFTC series that was 87 of 953 weeks at exactly
100.0.

**The fix.** Hazen's plotting position `(rank - 0.5) / n`, bounded `(0.5/n, 100 - 0.5/n)`.
Verified: exactly 100.0 is unreachable for every n from 2 to 5000; the CFTC maximum drops
from 100.0000 to 99.9502, and exact-100 weeks go 87 -> 0.

**Honest scope of the benefit — this is structural, not backtest-improving.** Because the
basis_trade cap already removed that channel's percentile leg from contention, Hazen changes
almost nothing in the *current* hindcast: basis_trade RED months (38) and at-ceiling months
(19) are **unchanged**, since those 19 now come from the uncapped level leg. Live-board
percentiles shift by less than 0.05pp across every leg (positioning -0.047, CCC -0.007,
EPU -0.005, SPY/RSP -0.013), all inside the displayed rounding.

What it actually buys is a *guarantee*: no percentile leg can ever again print the extreme
anchor merely by being the newest record, on any future data. Auditing the deployed pre-fix
hindcast, the only uncapped percentile-driven ceiling months were private_credit's four
(2015-11 and 2020-05..07 — the 2015 energy-HY and COVID credit blowouts). Every other
at-ceiling month — oil_shock 18, policy_shock 4, vol_supply 4, carry_unwind 4 — comes from a
**level** leg hitting a genuine documented extreme, which is the anchor working as designed.

So after all three fixes the ceiling means what it is supposed to mean: "at a documented
historical extreme", not "newest record".

**Anchor semantics, stated explicitly.** `extreme = 100` on a percentile leg is now
approached asymptotically and never reached (at n = 7500 the max score is ~99.97). That is
intended. The same holds at the bottom for the VRP leg, whose extreme is 0.

**Two existing tests were rewritten**, because they asserted the old estimator's exact-100
output rather than the property they were named for:
- `test_expanding_percentile_has_no_lookahead` asserted `pv == [100.0] * 5`. The no-lookahead
  property is preserved and now asserted as such (each running max sits at the highest
  attainable percentile for its n, and a later maximum cannot demote an earlier record).
- `test_latest_hindcast_point_matches_live_formula` compared to 1e-9, which only ever passed
  because both sides returned exactly 100.0 — `_percentile` rounds to 1dp, so that tolerance
  would not have caught a genuine live-vs-hindcast estimator drift. Now asserted to the
  rounding precision it actually has.

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

Both earlier verdicts were adopted. The 95+ threshold in rev 1 was **withdrawn** as a result of
pass A. All six of pass C's required changes are implemented; its one *recommended-separately*
item, the Hazen plotting position, is logged as DD Q9.
