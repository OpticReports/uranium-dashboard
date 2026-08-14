# RESEARCH_5Y.md — five-year out-of-sample study (2021-08 → 2026-08)

Run 2026-08-04 on Bitstamp 4h bars back to 2020-09 (12,987 bars; indicator
warmup satisfied before every window). Pure trading basis: cash_apy = 0,
research fees (6bp limit-entry pullback / 12bp round-trip donchian). Book
drawdowns are mark-to-market; blend rows are exit-step S5/S6 (blend MTM runs
~1-4pp deeper — same caveat as everywhere else in this repo).

**Why this matters:** the strategy rules were validated on 2024-2026.
Everything before 2024 is genuinely out-of-sample — a violent bull (2021),
a −64% bear (2022), and a recovery/chop year (2023) the rules never saw.

## Results by calendar year (S5 = 75/25 blend @1.5x)

| year | HOLD | S1 | S2 | S3 | S4 | **S5** | S5 maxDD |
|---|---|---|---|---|---|---|---|
| 2021 | +61.4% | +23.8% | +72.1% | +53.9% | +50.7% | **+95.5%** | −13.6% |
| 2022 | **−64.3%** | +32.9% | +51.8% | +27.1% | +26.4% | **+44.1%** | −13.3% |
| 2023 | +156.1% | +53.6% | +60.1% | +39.2% | +97.8% | **+94.2%** | −9.7% |
| 2024 | +121.6% | −7.9% | −14.4% | −7.1% | +13.6% | **−2.8%** | −19.1% |
| 2025 | −6.1% | +42.4% | +72.5% | +30.4% | −10.8% | **+31.0%** | −16.5% |
| 2026ytd | −27.2% | +9.9% | +4.9% | +5.7% | +28.8% | **+18.5%** | −10.2% |
| **FULL 5y** | +53.6% | +235.8% | +369.4% | +165.9% | +239.8% | **+434.7%** (~40%/yr) | −21.9% |

Win rates stable across all six windows (pullback 56-74%, donchian 34-54%).
No book hit its dd_halt in any window.

## Learnings

1. **The edge is real out-of-sample — and the OOS years were the BEST years.**
   2021/2022/2023 (never seen by the rules) delivered +95/+44/+94% on S5.
   The overfitting discount we have been applying to every number (rightly,
   a priori) turns out to be generous: the selected-on window (2024) is the
   WORST year in the sample.
2. **2022 is the headline.** BTC −64%; S5 +44% with a −13% drawdown. The
   short side of the pullback book and the trend leg both monetized the
   collapse. This system's best relative regime is a bear.
3. **The failure regime is directionless chop, not crashes.** Jan-Jul 2024
   (ETF-launch churn) is the only losing stretch: repeated pullback entries
   in tight ranges, bleeding stops. Worst year: −2.8%. That is the realistic
   bad-case shape: flat-to-slightly-down years, not blowups.
4. **S4's 2y kill verdict was cyclical, not structural.** On 2024-2026 alone
   the kill rule correctly zeroed it (34% of resamples non-positive). On 5y:
   +240% total, P(no edge) 1.7%, Kelly rec 0.45x. Trend-following bleeds for
   a year-plus, then pays for the whole wait (2023: +97.8%). Verdict
   unchanged in practice: never standalone, always as the blend diversifier
   — but the diversifier's long-run edge is now evidenced, not assumed.
5. **Sizing: the 5y sample materially firms up the Kelly picture.**

   | stream | n | m* | boot p10 | P(no edge) | c* | rec |
   |---|---|---|---|---|---|---|
   | S5 (2y) | 146 | 3.5 | 0.97 | 3.2% | 0.64 | 0.94 → venue-adj ~0.56 |
   | **S5 (5y)** | 350 | 4.0 (cap) | 2.77 | **0.0%** | 0.88 | **0.84** |
   | S6 (5y) | 350 | 3.2 | 2.08 | 0.0% | 0.88 | 0.63 |

   S5@0.84×1.5x and S6@0.63×2.0x both land on ~1.26x total blend leverage —
   two packagings of the same answer. The Kelly-safe operating point for the
   blend is ~1.25x, comfortably above the 0.56 multiplier chosen from 2y
   data alone.
6. **Consistency beats amplitude.** S5's worst year (−2.8%) vs HOLD's worst
   (−64.3%); S5 5y maxDD −21.9% vs HOLD −77% peak-to-trough. The compounding
   advantage (+435% vs +54%) comes almost entirely from not giving gains
   back.

## Changes adopted

- **Executor rollout sizing**: KELLY_M stays 0.56 for the live ramp
  (deliberately conservative while live-vs-paper tracking accumulates), with
  the post-validation ceiling raised from 0.56 to **0.80** on the strength
  of the 5y evidence. Raising past 0.56 requires: 15-20 live trades with
  tracking error within model, and no halt events.

## Research queue (hypotheses — NOT adopted; split-sample protocol required)

- **Chop filter for the pullback leg** (the 2024 failure mode): gate entries
  on a trend/participation measure. Must be fit on 2021-2023 and validated
  untouched on 2024-2026 (and vice versa) before any config change — the 5y
  dataset now makes an honest split possible.
- **Per-bar MTM blend accounting** for exact drawdown parity between blend
  and book rows (known ~1-4pp flattering on exit-step basis).
- Dashboard: surface this table via a 5y option on /replay/compare (needs
  the extended bar history server-side; the acceptance-test fixture must NOT
  be extended in place — earlier bars change indicator warmup at the pinned
  §6 start date and would invalidate those gates).
