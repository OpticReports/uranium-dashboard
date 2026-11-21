## What it is for

The crisis hedge: "the only component with negative correlation to equities" (architecture doc).
Built 2026-07-06 as an equal blend of two community signal strategies, to the owner's brief of "best
per-dollar crash payout with minimal bleed" (CHANGELOG 07-06). Target weight 31.8% since 2026-11-18,
as one engine of the book: the old band and the scheduled scale-up are retired (POLICY operations 1
and 2). Before that 27% (from the 07-20 allocation), and 10% at funding.

How to read it (add. 54.3): "a bond/credit-and-sector-shock hedge, not a VIX or broad-index crash
hedge"; its return "arrives in the 5-20 sessions after the crash day".

## Why each block is there

| Block | What it does | The reason on record | Source |
|---|---|---|---|
| InverseHold (50%) | When RSI(8) of IEF is below RSI(45) of PSQ: both LABD-or-BOXX and TMV-or-BOXX, half each, LABD and TMV each held only while its RSI(20) is below RSI(10) of KMLM (the tree ranks the two by volatility but keeps both, so the ranking does nothing). Otherwise BOXX | "Free hedge; slow-bear specialist" | add. 4 |
| FrontrunBonds (50%) | A ladder of one-day shocks in HYG, TLT, SHY, TMF, KIE, LQD and RSI extremes in CORP, PEJ, KIE, LQD, each choosing among UVXY, SVXY, SOXL, SOXS, UGL, TQQQ, SPXL, KIE, TMF. Otherwise BOXX | "Free hedge; fast-spike specialist" | add. 4 |
| 50 / 50 blend | Half each | Positive in all four SPY falls of more than 8% since 2022; correlation to HG -0.12; "robust to weights" | add. 4, 4b |
| Daily rebalance | Rebalanced every session | "Essentially a wash ... matches the components' native setting" | add. 4c |
| BOXX as the resting fund | Cash-like leg | Tax: BOXX pays its return as price gain rather than taxable distributions (Act 60) | CHANGELOG 2026-07-31; add. 17 |

The individual thresholds (1.75%, 23, 78 and so on) were set by the community authors in 2023-2025.
No reason for any of them is recorded.

## What changed, and why

- **`GtCP9qyw`** (saved 2026-07-06): rebalance changed from threshold-with-corridor to daily, BIL as
  the resting fund. Backtest +49.2% / Sharpe 1.59 / max drawdown 14.8% against +48.2% / 1.56 / 14.8%
  (add. 4c).
- **`yHJkdePZ`** (live from 2026-07-31): the four BIL nodes became BOXX, "signal conditions
  untouched". Reason: about $590 a year of tax saved at that size (CHANGELOG 2026-07-31; add. 17
  for the tax-deferral case). "Identical behavior over
  the 2023+ window"; the accountant's confirmation of BOXX's treatment was left with the owner
  (CHANGELOG 07-31). Side effect: BOXX's short history truncates Composer's backtest to about
  2023-01, so research uses the BIL copy (`research/sleeve_tree_bil.json`).

## Studied and not built

| Idea | Verdict | Source |
|---|---|---|
| Other weights, a third leg | not better | add. 4b |
| A 20% VIX-strategy leg (40/40/20) | best recent risk-adjusted profile (Sharpe 1.82, drawdown 8.1% after 2024-06) but cut full-window CAGR to +30% and history to 2023 on; left as an "optional future upgrade if its live record holds" | add. 4b |
| Monthly or quarterly rebalance | "destroyed the sleeve": +48% to -1% and -11% | add. 4b |
| Pop-harvest rule | "zero edge over the band, 5x the trades" | add. 7 |
| CAPE-scaled sizing; valuation conditioning | not adopted | add. 9, 26 |
| Vol targeting | Sharpe 1.41 to 0.51 | add. 21 |
| Leverage gates | "nothing moves" | add. 42 |
| Book-wide rate gate | costs the sleeve -19.9% a year | add. 33 |
| A static VIXM leg | left as the owner's question | add. 54.3 |
| Other windows for the IEF-vs-PSQ test, the LABD/TMV and KMLM tests, the ladder's RSI tests | 0 of 45 pass; level with the live windows | add. 59 |
| The ladder's one-day returns and ranks over 2 to 5 days | behind on every stretch | add. 59 |
| Another weight for the sleeve, the shock ladder alone, or dropping the inverse-fund half | the sleeve beats cash as a third leg at any weight from 2015; the ladder carries it before 2021; the weight is the owner's risk budget, not built | add. 60 |
| Macro states as a risk-off switch or a tilt; this engine's own states as signals for the others | none passes; the ladder being out of cash says nothing consistent about the other engines; gold strong is a lead seen in this engine only | add. 61 |
| Sleeve weights from 0 to 50% drawn forward 1, 5 and 10 years under ten scenarios (backtest as it stands, half / a quarter / none of the edge, one close late) | more sleeve means less return and a smaller fall wherever an edge survives; with no edge the order flips; what the sleeve costs as a share of return depends on whose decay is assumed: not decided, not built | add. 62 |
| A sleeve weight that moves with the market: 50% or 15% by valuation, rates, oil, or SPY/QQQ stretched above or washed out below their 20-, 50- and 200-day averages (30 states, both directions) | none passes against a constant weight with the same average; the constant weight matters far more than timing it; less sleeve when washed out pays in drawn-out bear markets and failed in the 2020 crash: a lead, not built | add. 63 |

## Known quirks and limits

- Its pre-creation history is "rule-replay, not live record"; out of sample only from 2024-06 (add. 4c).
- The 2008 result rests on modelled VIX legs; "with those legs in cash it is -1% / -14% / -29%: read
  that as the floor" (add. 39).
- It paid in 4 of 8 crash episodes and sat out 2026-11-05 (0 of 21 triggers) (add. 54.3).
- The +896% bootstrap figure is "a methodological ceiling, not a forecast" (add. 6).
- No automatic harvest or top-up since 2026-11-18 (POLICY).

## Numbers on record (in sample; none is a forecast)

- Live vs model to 2026-10-02 (window as in add. 36's table): +18.0% vs +15.9%, correlation 0.969.
- Backtest 2022-01..2026-07: +49.3% a year, Sharpe 1.59, max drawdown 14.8% (add. 5).
- Synthetic path from 1995: +19.5% a year with a 51% drawdown (add. 54.3).

## Open items in the record

- The architecture doc (2026-08-31) describes the halves as "short equity/credit" and "duration (TMF
  long / TMV short)". The tree holds LABD, TMV or BOXX in one half and the fund list above in the
  other. The tree is right.
- The old band's lower edge is written 7.5% in CHANGELOG and 7% in POLICY. The band is retired.
