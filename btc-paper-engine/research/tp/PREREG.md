# PREREG — when should the S4 trend leg take profit? (registered 2026-11-14)

Owner request (Casey, 2026-11-14): "Run a study. Run on multiple variables …
don't stop until you find something that is gonna give us a good indicator
when to take these profits … at some point there needs to be an
intelligible time which you take profit."

This file is committed BEFORE any variant's performance is computed. The
harness (`harness.py`), the grid (`variants.py`) and the gate tests
(`test_harness.py`, 81/81 passing) are committed with it.

## 0. Protocol status (RESEARCH_PROTOCOL.md)

- **§7 (signal-space search closed until the live gate concludes) is
  overridden by the owner's explicit request.** Recorded in §9a as an
  owner-authorized exception, not a waiver of §7 for anything else.
- **§9a: the BTC single-touch holdout for S4 exit parameters is spent.** So
  every BTC bar up to 2026-07-31 is IN-SAMPLE here. Out-of-sample evidence
  comes only from data never used to choose an S4 exit:
  1. **Four other assets** — ETH, LTC, XRP, BCH (Bitstamp 4h, listing →
     2026-11-14), each candidate evaluated on them once with its BTC
     parameters frozen;
  2. **the BTC forward window** 2026-09-01 → 2026-11-14 — reported, never
     decisive (a handful of trades).

## 1. Hypotheses and who pays (§3: rationale before any backtest)

The trailing stop gives back up to 5 ATR from the best close. A take-profit
rule earns its keep only if price is *predictably* more likely to reverse at
the point it exits than at a random point of the same trade.

| Family | Rule | Who pays / why it could work |
|---|---|---|
| F1 full TP | resting limit at entry ± k·ATR | overshoot into forced liquidations; sell into the cascade's own flow |
| F2 partial TP | take f of the position at k·ATR, trail the rest | same, while keeping the fat-tail exposure that pays for the trend leg |
| F3 profit lock | after k·ATR of profit, trail 5 → m ATR | trends that have run far mean-revert harder; tighter give-back late |
| F4 breakeven | after k·ATR of profit, stop at entry | cuts round-trips from winner to loser (late-entrant reversals) |
| F5a overextension | exit when \|close − SMA50\| ≥ z·ATR in favor | statistical stretch; anchored traders fade extremes |
| F5b RSI extreme | exit when RSI14 ≤ l (short) / ≥ 100−l (long) | exhaustion; late momentum chasers are the counterparty |
| F6 time | exit after n bars | trend edge decays with age (information fully diffused) |
| F7 channel | Turtle exit: stop at prior n-bar high/low | reversal confirmation earlier than 5 ATR |
| F8 climax bar | exit after a ≥ k·ATR candle in favor | capitulation candles mark local ends |
| F9 ER fade (R3) | in profit and Kaufman ER20 < x | trend quality has died → chop ahead |
| F10 volume climax (R3) | big favorable bar on ≥ v× volume | blow-off / capitulation volume |

## 2. Data (Bitstamp 4h, fetched 2026-11-14 by `fetch.py`, zero gaps)

| file | first bar | sha256 of the CSV |
|---|---|---|
| btcusd_4h | 2012-01-01 | 292a581146ed7155c8a8e31635f75beab77b2e4c39fff052c61833c17c99b12a |
| ethusd_4h | 2017-08-16 | 9c6ca9dc8cebc58e48c3d8753b5b444785a5d495a5e92f8526e38beb0a475c73 |
| ltcusd_4h | 2017-06-16 | 10bc79f50e6f7cfa8d1e3dd257a7b82de62817f76d4335e100055dfafee922c3 |
| xrpusd_4h | 2017-01-01 | b45b9a7b6348b4882874339715f6f0ce265fc04cc7cacdd7304e3f5a7f950786 |
| bchusd_4h | 2017-12-04 | 127f7672a95ab74ab41e52eab586f7331731330b48562357d99f5121bdc7f2a4 |

All end 2026-11-14 12:00Z. BTC matches the engine's test fixture on all
10,001 closed overlapping bars (the fixture's last bar was still forming).

## 3. Variants (`variants.py`)

**Round 1 (30):** F1 k∈{3,5,8,12,16} · F2 f∈{⅓,½}×k∈{3,5,8} ·
F3 k∈{4,8}×m∈{2.5,3.5} · F4 k∈{2,4} · F5a z∈{4,6,8} · F5b l∈{15,20,25} ·
F6 n∈{30,60,120} · F7 n∈{10,20} · F8 k∈{2.5,3.5}.

**Round 2 (4), only if nothing in Round 1 is ADOPT-ELIGIBLE:** the best config
of each of the top-3 families by criterion A's exit-step delta; all three
pairs plus the triple (`variants.round2`).

**Round 3 (6), only if nothing in Rounds 1–2 is ADOPT-ELIGIBLE:**
F9 k∈{3,6}×x∈{0.15,0.30} · F10 v∈{2.5,4}.

**Stop after Round 3 whatever the result.** Maximum 40 trials.

## 4. Selection-bias null (criterion C)

Placebo rules exit at random: per bar after the fill bar, hazard q
(log-uniform on [0.003, 0.08]); half close the whole position, half close ⅓
or ½ (`variants.placebos`). For each of R = 200 repetitions, draw N placebo
rules and keep the best criterion-A exit-step delta; q95 of those 200 maxima
is the bar. N = cumulative trials at the round being judged (30 / 34 / 40).
Placebo runs are null draws, not trials.

## 5. Metrics and windows

- **A (primary, §4 objective):** BTC 2022-01-01 → 2026-07-31 20:00Z, the
  deployed blend — W_TREND 0.30, LEV 1.5, S3 and S4 exactly as configured
  (S4 dd_halt 0.50 included). MAR on two bases:
  - exit-step: bench_blend arithmetic, window start (t0, 1) kept (the bench
    drops the first trade, §9 item 6), end point carried to t1;
  - MTM: bar-rebalanced constant-weight blend of the two books' MTM equity.
- **B:** BTC 2013-01-01 → 2026-07-31, S4 alone, dd_halt OFF, MTM MAR. (With
  the deployed halt the book stops after 16 trades in the 2014 crash, which
  would turn this into a test of when the kill switch trips.)
- **D:** ETH, LTC, XRP, BCH, S4 alone, dd_halt OFF, full history, MTM MAR.
- **Reported, not gating:** BTC forward window; trade stats (win rate,
  average win/loss, profit factor, median share of the max favorable move
  captured); A and B per calendar year; DSR against the registry count.

## 6. Decision rule

A config is **ADOPT-ELIGIBLE** iff all four hold:

- **A:** MAR ≥ 1.10 × baseline MAR on BOTH bases.
- **B:** MAR ≥ baseline MAR.
- **C:** A's exit-step MAR delta > q95 of the best-of-N placebo deltas.
- **D:** MAR > baseline on ≥ 3 of the 4 alts AND the mean MAR delta > 0.

Several eligible: rank by A exit-step delta, report all. **Eligible is not
adopted:** adoption needs Casey's dated sign-off, an engine change under its
own gate tests, and does not bypass the §7 live gate; ties break toward not
deploying (§8). If nothing is eligible after Round 3, the registered answer
is: **no take-profit rule beat the trailing stop out of sample**, reported
with the diagnostics.

**Retirement rule if adopted:** keep the trail-only baseline running as a
shadow; revert if, after 15 live S4 trades, the rule's cumulative P&L trails
the shadow's by more than one standard error of the per-trade difference.

## 7. Conventions (also in `harness.py`)

Resting orders (trail, TP limits, breakeven and channel stops) are live from
the bar after the fill · a bar touching a stop and a TP fills the STOP ·
opening through a level fills at the open · close-based rules fill at the
next open · TP distances use the signal bar's ATR (known when the order is
placed) · 6 bps/side on entry notional at every close, partials pro rata ·
partial closes update equity and peak, the dd_halt check stays on the full
close as in the engine.

## 8. Trials and disclosure

Registered: 30, +4, +6 if escalated — counted in §1 from registration.
Before this file was committed, variants were executed only inside gate G4
(look-ahead: trade-list identity between truncated and full runs, pass/fail);
no performance figure for any variant had been computed or seen. The
baseline was run for the harness gates (G1–G3).
