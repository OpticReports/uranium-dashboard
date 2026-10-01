# RESEARCH_SHARPE.md — a better Sharpe for the $100k

Casey, 2026-10-01 ("need a better Sharpe… run the better Sharpe study").
Pre-registration: `research/sharpe/PREREG.md` (commit `78d87322`, before
any run). Code, tests, results: `research/sharpe/`. Figure:
`research/sharpe/sharpe_answer.png`.

## Answer

**One lever holds up: size down when BTC volatility is high (vol-targeting).**
It does not make more money; it makes the same money with about a third
less drawdown. Forward Sharpe gain is likely **+0.1 to +0.2**, not a
doubling. Nothing else survived.

| | Sharpe 2013+ | $/yr | worst DD | Sharpe 2019+ | DD 2019+ | verdict |
|---|---|---|---|---|---|---|
| live engine today | 0.73 | $9.6k | −$29.0k | 1.05 | −$12.4k | — |
| H1 vol-target (registered, m 0.5–1.33) | 1.00 (+0.27, CI +0.13..+0.39) | $11.3k | −$18.9k | 1.20 | — | **passes, but breaches live rails** |
| H1 **down-only** (m 0.5–1.0, diagnostic) | 0.92 (+0.20, CI +0.09..+0.29) | $9.4k | −$18.8k | 1.18 (CI +0.04..+0.23) | −$9.5k | **recommended for review** |
| H2 200-day gate on the pullback | 0.98 (+0.25) | $12.2k | −$21.7k | +0.01 vs live | — | **REFUTED — hindsight** |
| H3a/b $30k funding-carry sleeve | 1.19 / 1.15 on 2016+ (vs 0.83) | +$4.3k | better | ≈ T-bills since 2024-07 | — | **PARKED — ≈ cash, can't run on HL as is** |
| H4 combination | 1.69 on 2016+ | — | — | — | — | **void (contains H2)** |

Fixed $100k base (how live sizes), KELLY_M 0.30, 70/30, 4.32 bp/side,
daily Sharpe × √365, rf = 0, Bitstamp 4h, MTM, 2013-01 → 2026-07.

## H1 vol-targeting — what it is and why it is real

Each leg's entry size × m, m = σ(last year's median) / σ(last 30 days),
clipped. Calm market → normal size; turbulent → down to half.

- **Not a de-lever:** average m 0.98–1.00, average gross $18.69k vs $18.75k.
- **Timing is real:** the same m values shuffled across entries, 100 times:
  best Sharpe 0.89, none reached 1.00.
- **Robust:** +0.22 from 2014, +0.23 from 2016, +0.15 from 2019; 90- and
  360-bar vol windows both work; beats live in 11 of 14 years.
- **Most of it is the DOWN side.** m capped at 1.0 keeps ~75% of the Sharpe
  gain, all five eras positive (+0.18/+0.22/+0.12/+0.09/+0.08), and all of
  the drawdown cut.
- **As registered it cannot run live.** m up to 1.33 puts up to $66k gross
  against the $60k rail (`cap_clamp` on 4.3% of entries) and up to 60% of
  equity against the 45% Kelly exposure ceiling. The down-only form never
  exceeds today's sizes, so it trips nothing.

**Caveat:** the down-only form was first run by counter-agent A as a
diagnostic, after results were seen. It is a restriction of the registered
rule, not a new idea, but it was not pre-registered. Its first real test is
live.

## H2 — refuted

All of its gain is 2013–2018 — the exact years disclosed before registering
as the pullback's losing years. Since 2019: ΔSharpe +0.01 (CI −0.23..+0.21),
−$8.6k over 2025–26. ~90% of the gain is "don't short the bull runs". Today it
would block every pullback short (price above its 200-day average since
2026-08-19). Not adopted.

## H3 — the carry sleeve, parked again

- Real versus idle cash in-sample, but **60% of its dollars are 2016–17**
  (BitMEX funding 55%/27%). From 2018-06 it made ~$2.0k/yr vs T-bills $0.8k.
- **Versus the same $30k in T-bills since 2024-07: +0.05 Sharpe (CI −0.04..+0.15)
  static, −0.04 gated.** Today: HL 30-day funding 8.8% vs T-bill 4.1% →
  about +$1.4k/yr on $30k.
- **Blocked on Hyperliquid as the account is set up:** in Unified mode spot
  UBTC does not margin the USDC perp short (docs; only pre-alpha Portfolio
  Margin does); `hl.py equity()` counts USDC only, so the UBTC purchase
  alone reads as a −$30k loss and trips the daily-loss halt; HL nets one BTC
  position per account, so a carry short needs a subaccount.
- The ARM/DISARM funding monitor (`/funding`) stays the trigger for
  revisiting it. HL is ARMED today (8.78%); INTX is not (6.84%).

## Counter-agent panel (house rule)

| reviewer | scope | verdict |
|---|---|---|
| A0 code audit | mechanics, lookahead, carry accrual | **SOUND** — recomputed the E2 sleeve to the cent ($16,516.75). Found one latent SERIOUS bug: HL funding timestamps are milliseconds, read as seconds → zero funding. **Fixed** (`load_funding`) before the HL sensitivity ran; 4 vacuous tests strengthened (17 now). |
| A H1/H2 | overfitting, hindsight, feasibility | H1 **SURVIVES** (placebo 0/100), forward gain smaller, registered caps breach rails → down-only. H2 **REFUTED**. |
| B H3 | real money on HL | **WEAKENED / blocked** — ≈ cash since rates normalised; basis risk minor at account level; HL collateral + executor equity + netting block go-live. |

## Honesty box

- In-sample. DSR ≈ 0.01 for H1 and H2 against ~2,546 trials (baseline
  0.0004): the absolute Sharpe level is not evidence of skill. The paired
  bootstrap tests the *increment*; H1's P(Δ ≤ 0) = 0.0015 survives a ×5
  correction.
- H3: BitMEX XBTUSD funding is a proxy (HL runs ~2× it 2023–26, daily
  correlation 0.61); spot/perp basis not modelled (adds −$3.3k worst on
  BitMEX, ±15 bp on HL); UBTC custody/depeg not modelled. The code sums 30
  days of rates × 365/30 where PREREG said "8h rate × 3 × 365": identical on
  8h stamps, correct on BitMEX's daily stamps in May–June 2016, no gate
  decision changes.
- The 2013+ worst drawdown (−$29k) is set by thin 2013 Bitstamp markets;
  from 2019 it is −$12.4k.
- Not modelled: engine halts, the post-bar stop window, funding on the
  directional book.

## Pending questions (ranked)

- **P1** Build H1 down-only? This needs:
  - the engine to publish a per-leg multiplier m ≤ 1 in /exec/target;
  - the executor to apply it to the leg's target quantity;
  - gate tests and two reviewers, then your approval.
  
  It moves risk, not return: the same ~$9–11k/yr with roughly a third less drawdown.
- **P2** Revisit carry only if (a) funding stays ARMED and (b) you want a
  subaccount and executor work for roughly +$1.4k/yr over T-bills.
- **P3** The lower drawdown would make room for more size. The binding limit is
  still the daily-loss rule, which becomes manual-resume above KELLY_M 0.30.
  Changing size is that decision, unchanged from RESEARCH_CAGR.
