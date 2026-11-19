# Proposal: hold B.5's gold as GLDM instead of PHYS (2026-11-19, revision 2)

STATUS: PROPOSAL. Nothing has been traded or changed. Needs Casey's go-ahead on an option and answers to the two
questions at the end. Origin: by-product of the B.5 structure study (b5_structure_2026-11, "gold wrapper").
Revision 2 replaces a first draft that an independent check FAILED (see "Verification" below).

## Recommendation
Switch the whole gold leg (23.5% target, unchanged) from PHYS to GLDM, on a day when PHYS's discount is not
unusually wide (Option A).

| | Option A (recommended) | Option B | Option C |
|---|---|---|---|
| Rule | Switch on the first normal day PHYS's intraday discount is about -2.4% or narrower (its 1-year median). If that has not happened by the 2027-02-26 month-end check, re-decide. | Switch now. | Keep PHYS. |
| Yearly gain | $158 from fees; about $290 if PHYS keeps lagging as it has | same | none |
| Versus selling at today's -2.8% | about $225 better if sold at -2.4% | - | - |
| Cost of waiting | $13-24 per month | none | $158-290 per year |
| Main risk | the discount widens further while waiting | sells at a wider-than-usual discount | the lag continues |

## Facts (discount.json; PHYS figures are Sprott's own published daily series, as of 2026-11-18)
- Position: 1,872 PHYS on IBKR ...3321 (read 2026-11-18) = $52,453 at the $28.02 close; the gold behind it
  is worth $53,970 (NAV $28.83), about 14.5 oz. Unrealised loss about -$9,900.
- Fees: PHYS 0.39%, GLDM 0.10%. Fee saving $158/yr, about 0.07 pt/yr on the book. IAUM is 0.09% (about $5/yr
  less) with a quarter of the assets: not worth it.
- PHYS's NAV has lagged GLDM by MORE than the fee gap: 0.57 pt/yr since GLDM launched (2018-06, 8.4 years),
  0.54 over 5 years, 0.72 over 3, 0.36 over 1. Sprott's own table shows its NAV behind spot gold by 0.5-0.8 pt/yr
  over 1 to 15 years against a 0.39% fee. The cause of the extra lag is not identified. If it persists, the
  saving is about $290/yr, not $158.
- Discount to NAV: -2.81% on 2026-11-18. Last year: median -2.39%, range -1.15% to -4.36%, wider than today on
  about one day in six. Last three years: median -1.84%, wider than today on 7% of days. Yearly medians:
  2021 -1.2%, 2022 -1.6%, 2023 -1.5%, 2024 -1.5%, 2025 -1.7%, 2026 -2.4%: roughly flat for five years, then a
  step wider in 2026. Day-to-day it moves about 0.4 pt.
- Since GLDM launched, at market prices: GLDM +13.6%/yr, PHYS +12.8%/yr. Of the 0.88 gap, 0.57 is the NAV lag
  above and about 0.3 is the discount widening from -0.6% to -2.8%.
- GLDM: $28.8B in assets, 30-day median bid/ask spread 0.01%, gold held by JPMorgan, tracks the LBMA PM price.
- Same exposure: daily returns correlate 0.996 over the last year (0.97 since 2018).

## The economics
Selling today realises a price $1,516 below the gold PHYS holds ($540 per point of discount). That is only a
cost if the discount would have narrowed while you held it. Break-even, including about $52 of trading costs:

| if the discount... | switching now costs | break-even at $158/yr | at $290/yr |
|---|---|---|---|
| stays at -2.8% | $52 | 0.3 yrs | 0.2 yrs |
| returns to -2.4% (1-year median) | $279 | 1.8 yrs | 1.0 yrs |
| returns to -1.8% (3-year median) | $576 | 3.6 yrs | 2.0 yrs |
| closes to zero | $1,569 | 9.9 yrs | 5.4 yrs |

Why the patience rule: all 21 earlier times the discount closed at -2.7% or wider, it was back to -2.4% within
44 trading days (median 4). In-sample, and 11 of the 21 were in 2026, so treat it as "usually", not "always".
The threshold is a round number near the 1-year median, not a precise level: the whole rule is worth about $225.

## Execution (Casey enters the orders; nothing is automated)
1. Trigger: on Sprott's PHYS page, the INTRADAY indicative premium/discount at the time of the order is about
   -2.4% or narrower. (The published previous-close figure is too noisy to trigger on.)
2. Same session, 10:30-15:30 New York time, both legs within a few minutes: SELL 1,872 PHYS at a limit near
   the mid; BUY GLDM with the proceeds (about 712 shares at 2026-11-18 prices) at a limit near the mid.
3. Do not trade on a day gold has moved more than 2% (the discount widened 0.2 pt on average on such days;
   2026-11-18 itself was one) or if GLDM's quoted spread is wider than 3 bps.
4. If a month-end band rebalance falls due first, do the swap in the same session so the gold leg trades once.
5. Same day, after the fills: the repo change set below, so the nightly monitor does not error.

## Repo change set (one commit, only after the trade; nothing is changed now)
- barbell-lab/config/data.yaml: add `GLDM: {proxy: GLD, splice_date: 2018-06-26}`; keep PHYS for history.
  Run `barbell ingest` so GLDM has prices before the register is touched.
- barbell-lab/config/backtest.yaml: add `GLDM: 2` (bps, one-way).
- barbell-lab/config/portfolio.yaml: PHYS -> GLDM in `targets`. This file is NOT just a seed: the rebalance
  monitor, backtest, book, evaluation, questions, optimizers and tearsheet all read their targets from it.
- Portfolio register: new version with PHYS 23.5% -> GLDM 23.5%, promoted to LIVE.
- barbell-lab/src/barbell/web/app.py (placeholder text), chat/agent.py (sleeve description),
  tests/test_monitors.py (fixture ticker).
- Composer / IBKR mirror: nothing under composer/ refers to B.5, PHYS or GLDM, so there is no symphony to
  change and the two-broker parity check does not apply. The Composer connector was unreachable, so this is
  checked in the repo only (question 2).
- Redeploy: barbell-lab.

## Separate finding: the rebalance monitor is checking against old weights
config/portfolio.yaml still holds the v1.0 targets (PHYS 18, QUAL 9, AVDV 19, AVUV 25, AVEM 10, TAIL 5). The live
book is v1.2 without CAOS (PHYS 23.5, QUAL 15.3, AVDV 11.8, AVUV 23.5, AVEM 5.9, TAIL 5.9), and
monitor/rebalance.py takes its targets from that file. Against those targets the live book is permanently
"out of band" (QUAL +70%, PHYS +31%, AVDV -38%), so any band alert it raises is false, and a real breach
would be masked. Not verified: whether a positions snapshot is currently being fed to the monitor in production.
Fixing it is a config change to a live service, so it waits for your go-ahead; it can ride in the same commit.

## Kill and review criteria (fixed before any trade)
- No shadow run: the exposure is identical, so a paper run could show nothing.
- At 12 months: GLDM's NAV return should be within 0.20 pt of the LBMA PM gold price change less 0.10%.
  A wider shortfall is a review, not an automatic exit.
- No automatic switch back. Returning to PHYS would be a new, deliberate trade with its own write-up.
- Option A deadline 2027-02-26: if the trigger has not fired, re-decide with the discount history to that date.

## Caveats
- The break-even table values the discount against NAV; nobody knows where the discount goes next.
- The $290/yr figure assumes an unexplained historical lag continues. $158/yr is the part that is certain.
- Tax: under Act 60 no tax is assumed, and the lot shows a loss. Not tax advice. PHYS is a PFIC whose usual US
  advantage (long-term rates through a QEF election, instead of the 28% collectibles rate) is what is given up.
- Custody differs: PHYS's bars are at the Royal Canadian Mint and holders of a whole bar's worth can redeem
  for metal (this position is 14.5 oz; I could not load Sprott's redemption page to confirm the minimum).
  GLDM's bars are at JPMorgan in London with no redemption for metal.

## Verification
An independent counter-agent FAILED revision 1: its discount history was reconstructed from the PHYS/GLD price
ratio and was wrong (Sprott publishes the real daily series); it claimed the discount had widened every year
since 2021 (false); it mis-attributed the return gap; and it said config/portfolio.yaml was only a seed (false).
Revision 2 is rebuilt on Sprott's published series and adopts every correction. Confirmed unchanged by the
check: the 2026-11-18 NAV, close, discount and fee; GLDM's and IAUM's fees; position size; share count.

## Questions for Casey
1. Why was PHYS chosen originally: tax treatment, or custody / redeemability? If custody, the fee and lag are
   the price of that preference and Option C is the consistent choice.
2. Is there a B.5 symphony on Composer that this repo does not know about? If yes, it changes in the same step.
