> **Status (2026-10-06):** independently recomputed (25+ numbers) by a counter-agent; 2 blocking framing issues (repaid-loan location; Composer embedded leverage) repaired and re-checked. P1 open with Casey: which loan is out and where the repaid capital sits.

# No-leverage follow-up: corrected liquid book, proposal with no borrowing, $18M post-exit, private sleeves (2026-10-06, repair pass)

The files are in `holygrail-engine/results/casey-2026-10/no-leverage/`. `predeclared_params.json` was written before any result. All 15 charts have row CSVs. Two are new: `n1_boxx_basis_check.png` and `lookthrough_notional.png`.

## ASK CASEY FIRST (P1, decision-gating)
**Where is the repaid loan's principal and fee now?**
- (a) Already inside the sheet's Cash/Stables $381,066.
- (b) In a bank account that is not on the sheet.
- (c) Redeployed. If so, into what?

Also: which loan is still out?

Why it matters:
- The earlier premise was that the repaid capital is "already in IBKR BOXX live". IBKR's own numbers rule that out. BOXX shows 3,672 sh at a cost of $371,732, or $101.23 per share. A re-buy at about $118.36 would leave the other shares carrying $93.99 (D) or $86.64 (P). BOXX has never closed below $99.76, so at most about $34k of either repayment can be in BOXX.
- Casey's own words are future tense: "Then I'll return the capital to BOXX".
- The answer moves NAV by up to $232k and the overstatement by up to $232k.
- Vol, DR^2, BTC risk share and the N2/N3 structure stand either way.

## N1: corrected liquid book
Each cell reads **reading (a) -> reading (b2)**:
- (a) means the capital is already in Cash/Stables. These are the published numbers.
- (b2) means principal plus fee sit off-sheet and are counted nowhere.
- (b1), principal only, falls between the two. All readings are in `n1_conditional_range.csv`.

| | D: Dominion out | P: Plus One out |
|---|---|---|
| Outstanding loan | $200,000 | $129,166 |
| Repaid loan, principal + fee | Plus One $129,166 + $19,375 | Dominion $200,000 + $32,000 (expected, unbooked) |
| Whole book / investable | $19,454,530 / $19,364,470 -> $19,603,071 / $19,513,011 | $19,383,696 / $19,293,636 -> $19,615,696 / $19,525,636 |
| **Sheet overstatement, BOXX-loan correction alone** | **$310,876 -> $162,335** | **$381,710 -> $149,710** |
| Liquid NAV | $2,374,470 -> $2,523,011 | $2,303,636 -> $2,535,636 |
| Vol now | 10.9% -> 10.2% | 11.2% -> 10.1% |
| DR^2 now (same in every reading) | 3.92 | 3.87 |
| 1/sum PRC^2, min-torsion | 4.97, 12.8 | 4.95, 12.7 |
| BTC share of risk | 40.5% | 40.5% |
| Cash-like share | 44.9% -> 48.2% | 43.2% -> 48.4% |
| Net of $410.2k commitments | NAV $1.96M -> $2.11M; vol 13.1% -> 12.1%; cash-like 33.4% -> 38.1% | NAV $1.89M -> $2.13M; vol 13.5% -> 12.1%; cash-like 30.9% -> 38.5% |
| Net of sheet's $435.2k (reading a) | vol 13.2%, cash-like 32.6% | vol 13.7%, cash-like 30.0% |

- F17 is a separate open P2 and is not included above. The Series X uncalled $215,200 is carried both in the $400k venture line and in cash. If Casey confirms, the whole-view overstatement rises by up to $215,200.
- Environment boxes (same in every case): growth-up 44%, growth-down -1%, inflation-up 34%, inflation-down 22%. Balance score 0.61.
- The sheet points to D. Dominion is still on the outstanding list with no profit booked. TOTAL EARNINGS of $60,820 is MARX $3,000, KMD $18,445, Dustlands $10,000, Plus One $19,375 and Father of Us $10,000.

## N2: liquid book with no borrowing (variant D, reading a; P within 0.5 pp)
| | current | current, cash pro rata | **proposal, no borrowing** | metals held (post-hoc) |
|---|---|---|---|---|
| Vol | 10.8% | 15.0% | **4.9%** | 6.3% |
| DR^2 / 1/sum PRC^2 | 3.78 / 4.9 | 3.75 / 4.9 | **5.27 / 8.0** | 4.25 / 5.0 |
| Balance score | 0.61 | 0.61 | **0.83** | 0.61 |
| BTC / Composer share of risk | 41% / 16% | 41% / 16% | **12% / 16%** | 7% / 9% |
| Gross at face (no borrowing) | 0.55 | 0.76 | 0.80 | 0.80 |
| **Look-through notional, upper bound (Composer at 3x)** | 0.80x | **1.11x** | 0.91x | 0.90x |
| PRIOR-DRIVEN return, base / alpha haircut | 10.2% / 5.6% | 12.6% / 6.3% | 7.4% / 6.0% | 8.0% / 6.8% |
| Replay max drawdown, GFC / Covid / 2022 | -20.5 / -15.1 / -13.1% | -28.7 / -21.1 / -18.2% | -15.8 / -10.1 / -7.8% | -17.9 / -11.1 / -9.5% |
| Backtest B 2006-26: CAGR / vol / maxDD (IN-SAMPLE) | 13.1 / 10.3 / -23% | 17.5 / 14.4 / -31% | 5.7 / 4.8 / -17% | 6.2 / 5.8 / -18% |

- **Leverage scope:**
  - The "no leverage" rule here covers borrowing, margin and levered balanced funds (ALLW/UPAR/RSSB).
  - It does not cover the daily-reset 3x ETFs inside Casey's own Composer strategy (SPXL/TQQQ/SOXL/TECL/UPRO/LABU/TNA, TMF; UVXY). Composer is kept at its 16% risk budget, per his plan.
  - Measured over 3y (IN-SAMPLE, 73-93% backtest), the Composer policy mix had beta 0.78 to SPY and vol 1.6x SPY. The HG symphony alone had beta 2.0 and vol 2.9x SPY.
  - Judge this against "I generally don't like leverage".
- KMLM and DBC are fully collateralised futures funds, about 1x notional. NOTE only.
- Target holdings (reading a): TIP $693k, TLT $284k, KMLM $262k, DBC $226k, core equity $167k, Composer $137k as one sleeve, BTC $65k, single names $34k, gold $0.
  - Under (b2), every target is 1.08x and vol is 5.0%.
- Kept aside: $410.2k reserve in BOXX. Hyperliquid untouched.
- The pro-rata route is the only way to 15% vol without borrowing, and its look-through notional is up to 1.11x.
  - It deploys $499k of the $590k uncommitted cash under (a), or $610k of $739k under (b2).
  - The risk mix is unchanged.
- SPY over the same window: CAGR 11.2%, vol 19.2%, maxDD -55%. 60/40: 8.3%, 10.8%, -33%.

## N3: $18M with no borrowing (film return at 14.4% default-adjusted / 20% headline)
| | PLAN pre-trigger | PLAN post ($750k SPCX) | ALT-2 no borrowing | CASEY pre | CASEY post |
|---|---|---|---|---|---|
| Vol | 10.4% | 12.0% | 7.2% | 10.6% | 12.0% |
| DR^2 | 2.18 | 2.47 | 4.02 | 4.30 | 4.56 |
| Balance score | 0.33 | 0.32 | 0.73 | 0.41 | 0.39 |
| Gross at face / **look-through upper bound** | 0.64 / **1.12x** | 0.68 / **1.16x** | 1.00 / **1.16x** | 0.94 / **1.42x** | 0.99 / **1.47x** |
| Largest risk shares | SPY 51%, Composer 49% | SPY 43%, Composer 39%, SPCX 17% | core 70%, Composer 15%, basket 15% | Composer 41%, venture 31%, film 12%, core 16% | Composer 35%, venture 26%, SPCX 15%, film 10% |
| PRIOR-DRIVEN return | 6.7% | 7.1% | 7.4% | 9.2% / 10.0% | 9.7% / 10.4% |
| Worst replay | -$5.55M (2000-02) | -$6.32M (2000-02) | -$4.26M (2008) | -$4.94M (2008) | -$5.39M (2008) |
| Bootstrap 5th-percentile year | -$1.31M | -$1.92M | -$0.41M | -$1.26M / -$1.13M | -$1.75M / -$1.62M |

How the CASEY ROUTE is built:
- Film and private lending: $2.4M, from the sheet's Budget row for $20M.
- Venture: $1.75M, from the Venture footnote ("15-20 more ... $1.5-2m").
- Composer: $4.32M (24%, held in 3x ETFs when risk-on), from the post-exit plan row.
- SpaceX reserve: $1M, held until the trigger.
- Balanced core: the remaining $8.53M.

What drives its return:
- Film at 20% headline, or 14.4% = 0.92 x 20% - 0.08 x 50%. The 8% default rate sits above Fitch's 6.3% TTM (Aug-2026), which counts maturity extensions as defaults.
- Venture at a neutral 19.8% (rf + 0.30 x 52.5% vol).
- Composer is held at zero alpha.

SPCX: beta 1.62 to QQQ, measured over only 75 days since listing; vol 86%.

## N4: private sleeves as Dalio streams
**Film, variant D**
- $1.482M in 7 loans. The largest, 12 Dates, is 37%.
- Effective number of loans: 4.6 by dollars, 2.2 at rho_D 0.3.
- Realised income is 19% of plan ($60,820 vs $318,400). The whole private-credit sleeve is at 29%. Total income is at 59% ($408,969 vs $698,400).
- Father of Us is past due: $10k collected of $50k expected.

**Private-credit sleeve**
- DR^2 1.71, because all film loans are modelled as one stream.
- Correlation to the rest of the book 0.12 (assumed). Prior Sharpe 0.56 (assumed).
- Dalio tests:
  - GOOD: fail (realised income below 50% of plan).
  - UNCORRELATED: fail (n_eff 2.2).
  - RISK-BALANCED: fail (largest position 36%).
- It would qualify once matured loans pay out near plan, no single loan exceeds about 10-15%, and the borrowers and distributors are independent.

**Venture**
- DR^2 1.22 with Organics Ocean and 1.35 without it. OO is 97% of the sleeve's risk.
- OO is 97.2% of the $12.25M paper gain and 83% of realised gains.
- It fails all three tests. Even 17.5 equal new deals give only 2.9 effective bets at rho 0.3. Budget venture as one stream.

## PENDING QUESTIONS (ranked)
| Rank | Question | What it moves | Status |
|---|---|---|---|
| P1 | Where is the repaid principal + fee: Cash/Stables, off-sheet bank, or redeployed? Which loan is still out? | NAV +$0-232k; overstatement $150k-$382k; vol 10.1-11.2%; deployable cash | open, asked 2026-10-06, re-asked now |
| P2 | F17: are Series X and "Google X Fund" the same $400k commitment, with $215,200 uncalled still in cash? | whole-view overstatement up to +$215,200 | open |
| P3 | Are the 15-16% loan rates flat per loan or annualised? The sheet's fees ($19,375 = 15.0% of $129,166; $32,000 = 16% of $200k) read as flat. | PRIOR-DRIVEN coupon of the outstanding loan only | open (flag kept) |
| closed | DexMat answers "1. Passes thru 2. ... too small on the SPV 3. ... yes to fees". Recorded in deals/dexmat/ic.md: the right passes through the SPV, the SPV is below the major-investor threshold, and fees continue as is ("I'm not sure"). | no number here; DexMat $75k stands | closed, do not re-ask |

## HONESTY
- Basis: daily mark-to-market on the trailing 3y window (2023-10 to 2026-09). Vol, DR^2, risk shares, boxes and look-through do not depend on any return assumption.
- Every return is PRIOR-DRIVEN (rf + 0.30 x vol; alpha at zero or haircut). None is a forecast.
- Backtests apply today's weights in hindsight. They are IN-SAMPLE: Composer uses in-sample backtests before its live start, and replicas use full-sample betas, which is look-ahead.
- "No leverage" means no borrowing. Embedded 3x ETF exposure in Composer remains, shown as an upper bound. Holdings rotate, so the true daily figure sits between gross at face and the bound.
- N1 NAV and overstatement are conditional on the P1 answer. Reading (c), redeployed, cannot be computed until Casey names the target.
- The private streams and SPCX are assumption-driven factor models: no idiosyncratic risk in replays, and no default jumps in the bootstrap.
- In the 2000-02 replay, the CASEY ROUTE's venture leg has no IWM data for 54 days. Those days count as 0%, which understates the loss.
- Not modelled: taxes, lock-ups and J-curve, bullion spreads, fees.
- Post-hoc changes, all logged:
  - the metals-held variant
  - a de-meaning fix in the bootstrap
  - a fix aligning the replay proxy with the declared rule
  - repair R1, the N1 conditional range
  - the look-through notional
- ALT-2 reproduces the earlier post-exit figures exactly: vol 7.18%, prior 7.42%, and all four replays.
- A counter-agent review was run: 2 blocking and 4 non-blocking items, all repaired here. No published number changed; the readings were added alongside. The repair was then independently re-checked (targeted recheck: both blocking items confirmed fixed, every touched number recomputed).
