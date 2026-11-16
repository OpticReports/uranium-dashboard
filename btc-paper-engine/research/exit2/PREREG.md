# PREREG — EXIT2: adaptive, regime-conditional and multivariate exits for the S4 trend leg (registered 2026-11-16)

Owner request (Casey, 2026-11-16), on the live short whose 5×ATR trail locks
~$1,700 of ~$4,700 open profit: "that essentially gives up more than half
the current profit … what haven't you tested? … exit strategy research and
back testing it and potentially applying … multiple strategies that change
depending on the conditions … a multivariate style exiting."

Committed BEFORE any variant's performance is computed, with `harness2.py`,
`variants2.py`, `run2.py` and `test_exit2.py` (72/72 gates pass).

## 0. Protocol status

- §7 overridden by the owner for this study, recorded in §9a.
- **Selection set (in-sample): BTC + ETH, LTC, XRP, BCH.** BTC is in-sample end
  to end (§9a), and the four alts were the take-profit study's out-of-sample
  set, so they are now used for selection, not validation.
- **Holdout (single touch): 12 coins never used to choose an S4 exit** —
  SOL, LINK, ADA, XLM, DOGE, AVAX, DOT, UNI, AAVE, ALGO, NEAR, SHIB
  (Bitstamp 4h, 3.9–6.5 years each, zero gaps). Only the finalists (≤3) are
  run on them, once.
  - Disclosure: SOL, DOGE and LINK 2024-06 → 2026-09 bars appeared in
    RESEARCH_SCALE (a capacity study, not an exit study).

## 1. What the literature says, and the hypotheses

- Stops add value only when returns are serially correlated (Kaminski & Lo).
- On trend-following, simple stop overlays rarely beat the trend rule
  itself (Clare, Seaton, Smith & Thomas).
- The take-profit study agrees: 0 of 62 fixed and indicator exits beat the
  trail.

What is better supported, and untested here:

| Family | Rule | Evidence / who pays |
|---|---|---|
| V1 in-trade vol scaling | cut size as volatility rises vs entry (down-only, floor 25%) | volatility-managed momentum (Barroso & Santa-Clara 2015; Moreira & Muir 2017): crashes cluster in high vol; sell risk to vol-insensitive holders before the reversal |
| V2 trend-strength scaling | position = continuous trend signal (t-stat blend), scale down as the trend weakens, exit when it turns | continuous vs binary signals (Baltas & Kosowski): same return, far less whipsaw; exit as the diffusion that pays trend-following fades |
| V3 regime-conditional trail | trail multiple chosen by volatility regime, trend alignment or trend efficiency | Casey's "strategies that change with conditions"; adaptive ATR exits (MDPI 2019, mixed evidence) |
| V4 accelerating trail | the multiple tightens with time or profit; Parabolic SAR | late-trend reversals; classical (Wilder) |
| V5 multivariate exit | walk-forward logistic model on 11 trade/market features | "multivariate exiting"; the model must earn its keep out of sample |

## 2. Data (Bitstamp 4h; in-sample sha256 in ../tp/PREREG.md)

| holdout | first bar | sha256 of the CSV |
|---|---|---|
| aaveusd | 2021-04-16 | 613ec04ecb8081d2bfd03e793195224ab6d516f30efc171575322c7b088aa318 |
| adausd | 2021-11-17 | f3fd06f1b67aab0f679811a29e8ce740ae54823f28421c28b6a1ae8bffbbc2b5 |
| algousd | 2021-05-13 | 4cec6fa97dd1ff7812ce1ef731b2d9a576bb3f2d9ef9fd56cba7a84305e7d0ac |
| avaxusd | 2022-03-08 | 38667df6cc3732b4e4fc278c5d681ce641cf58b4d31e3aba1491b609759b74cf |
| dogeusd | 2022-12-21 | c7906a40f58518abcdb5911fe7c44f89335fb434486641b8b08639eec28eb17b |
| dotusd | 2022-08-18 | 898ba96ba900f1c992407b142e4315702a4409f4ab2ff1807b979d150bc2dee3 |
| linkusd | 2020-10-19 | a36a158dd67f01d79844c0ee0f3e4804fc2f21c3a8eea4fc8772c2b336604ae4 |
| nearusd | 2022-09-01 | 751987b0033e3e991c61e27b62ce3334e682c76c9464349374eed86ed031571d |
| shibusd | 2021-12-07 | 6861c3d16745a9508a6f852502cc102d86e2a03bf57cb2b3dd2acb8869f5c4f4 |
| solusd | 2022-08-18 | 233cc5fe6c8283aea5cdb000daf0037f101c8f5d108764777bc2e89c5c464bcc |
| uniusd | 2021-05-04 | 03f3103523b62699b990b72a1c6fcbceb5308b812e76c72fccbcc3e3080e563b |
| xlmusd | 2020-05-28 | 3b6688c69233974b8838cf1b72b98536d915f577961fd31c879397c1f83950ef |

All end 2026-11-16 08:00Z.

## 3. Variants (`variants2.py`, 28)

**V1 (4):**
- vol measure ∈ {ATR14 vs the signal bar's ATR, 42-bar realized vol vs at
  the signal bar} × band ∈ {0.10, 0.25};
- target fraction = min(1, entry vol / current vol), floor 0.25;
- down-only (never adds back).

**V2 (7):**
- signal = mean over horizons of clip(t-stat / d, −1, 1), where the t-stat
  is of 4h log returns over L bars;
- scale mode: fraction = signal in the trade's direction, down-only, step
  ≥ 0.25; full exit when it reaches 0. Configs: {fast (30, 90, 270),
  slow (90, 270, 810)} × d ∈ {1, 2}, plus single-horizon 270 at d=2;
- flip mode: full exit when the signal turns against. Configs: fast, slow.

**V3 (7)** — trail multiple chosen at each 4h close by regime:
- vol regime vr = ATR14 ÷ mean ATR14 of the prior 2,190 bars (1 year);
- alignment with the 1,200-bar (200-day) SMA;
- ER60 (trend efficiency over 60 bars).

Mappings:
- lowvol_tight (3.5 if vr < 0.8)
- highvol_wide (6.5 if vr > 1.25)
- vol_both (both of the above)
- vol_inverse (6.5 / 3.5)
- align (6 aligned / 4 against)
- er (6 if ER60 > 0.3, else 4)
- vol_both_align (vol_both × 1.15 aligned, × 0.85 against)

**V4 (8):**
- time acceleration: m = max(m_min, 5 − α·bars/42), α ∈ {0.25, 0.5},
  m_min ∈ {2.5, 3.5};
- profit acceleration: m = max(3, 5 − β·MFE_ATR/10), β ∈ {1, 2};
- Parabolic SAR as an extra resting stop: starts at the trail, AF step 0.02,
  max AF ∈ {0.10, 0.20}, never inside the last two bars' range.

**V5 (2):** walk-forward L2 logistic regression (λ = 1, standardized
features) on 11 features:
- MFE, open profit and give-back in signal-bar ATR;
- bars held;
- ER20, ER60;
- vol regime;
- RSI, distance to SMA50 and SMA200 in ATR;
- 20-bar return z, all signed to the trade.

How it is trained and used:
- **Label:** exiting at the next open beats this trade's eventual
  (trail-only) exit.
- **Training data:** the model for year y is fitted only on in-sample
  trades (BTC 2013–2026-07, the four alts' full histories, kill switch off)
  that closed before Jan 1 of y, with at least 500 samples.
- **Rule:** exit at the next open when p > θ, θ ∈ {0.6, 0.7}.
- **On the holdout coins:** the same in-sample-trained models.

Every variant keeps the Donchian-20 entry and the 5×ATR trail unless its
rule changes the multiple. Rules never add to a position.

## 4. Metrics

- **A** — BTC 2022-01 → 2026-07, the deployed blend (30% trend, 1.5×, S4 halt
  0.50), MAR on the exit-step and MTM bases. As in the TP study.
- **B** — BTC 2013 → 2026-07, S4 alone, halt off, MTM MAR.
- **D** — ETH, LTC, XRP, BCH, S4 alone, halt off, MTM MAR.
- **H** — the 12 holdout coins, S4 alone, halt off, MTM MAR. Finalists only.
- **Reported, not gating:**
  - "kept": the median share of the peak favorable move kept, on trades
    whose peak move was ≥ 10% — the give-back Casey asked about;
  - the BTC forward window 2026-09 → now;
  - trade stats;
  - for context, the luck bar from the TP study's null (best-of-30
    random exits, q95 +0.587 on A exit-step).

## 5. Decision rule

- **Selected** iff A (≥ +10% MAR on both bases) ∧ B (not worse) ∧ D (≥ 3 of
  4 alts better and mean > 0).
- **Finalists:** the top 3 selected configs by A exit-step delta. If none is
  selected, the holdout is not touched and the answer is "no adaptive exit
  beat the trail".
- **H (single touch):** MTM MAR better on ≥ 8 of 12 holdout coins, mean delta
  > 0 and median delta > 0.
- **ADOPT-ELIGIBLE** = finalist ∧ H.

Adoption still needs, in order:
1. Casey's dated sign-off;
2. the engine change under gate tests, plus executor support for partial
   exits if the rule scales;
3. a paper shadow beside the live trail until 15 live S4 trades
   (≈6 months) agree.

## 6. Trials and disclosure

- **Trials:** 28, counted at registration (registry ~2,636). Holdout runs
  of finalists are not new trials.
- **What ran before this registration:**
  - variants only inside gates G4, G6 and G8 (pass/fail on trade-list
    identity and synthetic fills);
  - one smoke test printing trade-record counts, not performance, for 7
    configs on BTC;
  - BASE on every coin, including the holdout, for gate G1;
  - the V5 models trained (coefficients not inspected).

No variant performance figure had been computed or seen.
