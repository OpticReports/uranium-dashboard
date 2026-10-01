# PREREG — Sharpe study (2026-10-01)

Registered BEFORE any candidate below was run, per RESEARCH_PROTOCOL.md §5.
Nothing in this file is edited after the first candidate result; failures
are recorded in RESEARCH_SHARPE.md, not removed from here.

## Mandate (Casey)

"Meh Sharpe… need a better Sharpe than this" (2026-09-30), then "run the
better Sharpe study" (2026-10-01). Standing answers from the CAGR study
still apply: worst acceptable drawdown **−30%** on the $100k; scope
**anything that holds up**; go-live **brought to Casey for approval**.

§7 of RESEARCH_PROTOCOL.md keeps signal-space search closed and names
"vol-targeting the blend" and "cash yield on idle capital" as open
portfolio-layer work. H1 and H3 below are portfolio-layer. H2 is a
signal-layer filter; it runs under Casey's "anything that holds up"
scope, the same reopening recorded in research/cagr/PREREG.md.

## Objective (fixed now)

**Account Sharpe**: annualised Sharpe of DAILY account P&L on a FIXED
$100,000 base (UTC-day closes, mean/sd × √365, rf = 0). This is how live
sizes (SIZING_BASE_USD, no compounding), so it is the Sharpe of the money
Casey actually holds.

Baseline = **the live engine as deployed 2026-09-30**: S3 pullback + S4
donchian-20/trail-5 with the resting-stop trail, w_trend 0.30, blend lev
1.5, KELLY_M 0.30, fixed base $100k, fees 4.32 bp/side. Engine code path
for every trade (research/cagr/harness.py, gate-tested against run_replay).

## Data

- Bitstamp BTC/USD 4h, 2011-08 → latest (research/cagr/data).
- **BitMEX XBTUSD funding, 8-hourly, 2016-05-14 → now** (public API,
  fetched for this study). The only funding series reachable from here
  that spans a bear market (2018, 2022). Binance and Bybit refuse this
  location; OKX serves only recent history.
- Hyperliquid BTC funding, hourly, 2023-05-12 → now (sensitivity only).

## DISCLOSURE — what I already know

- From RESEARCH_CAGR.md: per-era Sharpe of the engine (E1–E4 at k=1:
  0.45/−0.04/1.10/1.45 for 75/25), and that the pullback leg lost money in
  2013, 2014, 2015, 2017 and 2018 and made ~14.5%/yr since 2019. That
  biases any pullback filter (H2) toward looking good on E1–E2. The H2
  rule is canonical and fixed below, and it must also hold up on E3–E4
  where the pullback works.
- From RESEARCH_CARRY.md (2026-08-26): on HL 2023-05..2026-08 a 30% carry
  sleeve beside S6 improved MAR, mostly through the funding LEVEL (HL
  15.1% 2023, 24.1% 2024, 10.6% 2025, 4.5% 2026 YTD); it was parked with
  an ARM ≥ 8% / DISARM < 5% monitor. Today (2026-10-01) the monitor reads
  HL 8.78% (ARMED), INTX 6.84%. **I have not looked at any BitMEX funding
  statistic** beyond two rows from 2016 used to confirm the endpoint works.
- I have not run vol targeting or a 200-day gate on this engine.

## Hypotheses (5 trials)

**H1 — vol-targeted entry size (portfolio layer).** Volatility clusters,
so scaling size inversely to current volatility raises Sharpe for
directional strategies (Moreira & Muir 2017; Barroso & Santa-Clara 2015).
At each leg's ENTRY bar T: σ_now = stdev of BTC 4h log returns over the
180 bars ending at bar T−1 (30 days); σ_ref = median of σ_now over the
2,190 bars ending at T−1 (1 year, walk-forward). Multiplier
m = clip(σ_ref / σ_now, 0.5, 1.33) on both legs' weight. The 1.33 cap is
60,000/45,000: the largest m the live MAX_NOTIONAL_USD rail can carry
with both legs open. Live-implementable: the engine has the bars.
Trials: **1**.

**H2 — slow regime gate on the pullback.** The pullback already requires
close vs a 200-bar SMA on 4h bars (~33 days). Buying dips in a downtrend
(and shorting rips in an uptrend) at the slower, canonical 200-DAY horizon
(Faber 2007) is the textbook way such a strategy dies. Rule: a pullback
LONG signal at bar t stands only if close(t) > SMA of the last 1,200 4h
closes ending at t (200 days); a SHORT only if close(t) < it. The signal
is suppressed in the engine replay itself (not by deleting trades after
the fact), so the book is free to take the next valid signal. Donchian
leg untouched. Trials: **1**.

**H3 — funding-carry sleeve beside the engine (portfolio layer).** Long
spot BTC / short BTC perp, delta-neutral, collects funding; its return
stream is close to uncorrelated with the directional book's. Sleeve
notional **$30,000** (the 30% of RESEARCH_CARRY V6), on the same $100k
account. Mechanics: both legs marked at the same Bitstamp close (basis not
modelled — disclosed); short receives +rate × perp notional at each
BitMEX funding stamp, notional at the most recent 4h close; resized to
$30k at a UTC month start only if notional has drifted > 25%. Fees per
side: spot 7.0 bp, perp 4.32 bp, both legs on every open/resize/close.
(a) **static**: always on from 2016-06-01.
(b) **gated**: the parked policy as written in RESEARCH_CARRY.md —
on when the trailing 30-day mean annualised funding (8h rate × 3 × 365)
is ≥ 8%, off when < 5%, state held in between; evaluated once per UTC day
on funding stamps strictly before 00:00. This is a genuine out-of-sample
test of a policy fixed on 2023–26 HL data. Trials: **2**.

**H4 — the combination** of whichever of H1, H2, H3a/H3b pass (if both
H3 variants pass, the one with the higher full-window Sharpe; that choice
is recorded, not hidden). Evaluated once. Trials: **1**.

Batch total **5** → registry ~2,538.

## Decision rule (each candidate vs baseline)

Adopt-for-review iff ALL hold:
1. Full-window account Sharpe higher, AND the paired stationary block
   bootstrap (daily P&L pairs, mean block 30 days, 2,000 resamples, seed
   7) puts the 90% CI lower bound of ΔSharpe above 0. Full window:
   2013-01-01 → 2026-07-31 (H1/H2); 2016-06-01 → 2026-07-31 (H3, H4 if it
   contains H3).
2. ΔSharpe ≥ 0 in ≥ 3 of 4 eras E1–E4 (H3: ≥ 2 of 3, E2–E4; E1 has only
   seven months of funding).
3. No era E1–E4 with ΔSharpe < −0.15.
4. Max drawdown in dollars at live sizing no more than $3,000 worse than
   baseline's over the full window, and inside Casey's −30% ($30k).
5. Independent counter-agent review finds no fatal defect.

E5 (2024H2–26, spent) and E6 (2026-08+) are reported, never decide.
Ties break toward NOT changing the live engine (§8).

Eras as research/cagr/harness.py: E1 2013–16, E2 2017–19, E3 2020–21,
E4 2022–24H1, E5 2024H2–26, E6 2026-08+.

## Reported alongside (not deciding)

$/yr and max drawdown at live sizing; per-era Sharpe; DSR against the
registry count; for H3 the BitMEX-vs-HL funding overlap (2023-05+) and the
sleeve re-run on HL funding where it exists; the correlation of the sleeve
with the directional book.

## What a pass does NOT settle (implementation, asked before any money moves)

H3 needs a spot BTC long held beside the perp book. Whether HL's unified
account counts spot BTC as margin for a perp short, and whether the
executor nets a carry short against the directional legs or runs it in a
separate subaccount, are implementation questions — a pass makes them
worth answering, it does not answer them.

## Retirement rule (if adopted)

H1/H2: live realised drawdown past −20% within 90 days of the change →
revert. H3: sleeve off if 30-day realised funding underruns the model by
> 50% over 4 weeks, or on the DISARM condition (H3b).
