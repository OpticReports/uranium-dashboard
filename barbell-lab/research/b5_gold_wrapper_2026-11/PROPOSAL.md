# Proposal: hold B.5's gold as GLDM instead of PHYS (2026-11-19)

STATUS: DRAFT PROPOSAL - independent check in progress. Nothing has been traded or changed. Needs Casey's go-ahead on the option and answers to the
two questions at the end. Origin: by-product of the B.5 structure study (b5_structure_2026-11, "gold wrapper").

## Recommendation
Switch the whole gold leg (23.5% target, unchanged) from PHYS to GLDM, but not at any price: PHYS is trading
2.8% below the value of its gold, near the widest in a year. Use a patience rule (Option A).

| | Option A (recommended) | Option B | Option C |
|---|---|---|---|
| Rule | Switch on the first day PHYS's published discount is -2.4% or narrower (its 1-year median). If that has not happened by the 2027-02-26 month-end check, switch then anyway. | Switch now. | Keep PHYS. |
| Certain gain | $152/yr in fees | $152/yr | none |
| If the discount is at -2.4% when sold | about $210 more than selling today | - | - |
| Cost of waiting | about $13 of fees per month | none | $152/yr |
| Main risk | discount widens further while waiting | sells at an unusually wide discount | discount keeps widening (it has every year since 2021) |

## Facts (sources in discount.json)
- Position: 1,872 PHYS on IBKR ...3321 (positions read 2026-11-18), $52,453 at the 2026-11-18 close of $28.02.
- Fees: PHYS 0.39% (Sprott), GLDM 0.10% (State Street). Gap 0.29%/yr = $152/yr = about 0.07 pt/yr on the book.
  IAUM is 0.09%: $5/yr cheaper than GLDM, a quarter of the assets. Not worth it.
- GLDM: $28.8B in assets, 30-day median bid/ask spread 0.01%, gold held by JPMorgan, tracks the LBMA PM price.
- PHYS discount to net asset value, 2026-11-18: -2.81% (NAV $28.83, close $28.02; Sprott's own page).
  Reconstructed history: 1-year median -2.4% (range -1.4% to -3.4%; wider than today on 10% of days);
  3-year median -1.5% (wider than today on 4% of days). Yearly medians have widened every year:
  2021 -0.1%, 2022 -0.6%, 2023 -0.7%, 2024 -0.8%, 2025 -1.5%, 2026 -2.5%.
- Measured since GLDM launched (2018-06-26, 8.4 years): GLDM +13.6%/yr, GLD +13.3%/yr, PHYS +12.8%/yr. GLDM beat
  PHYS by 0.88 pt/yr: 0.30 is fees, the other 0.57 is PHYS's price sliding from a premium to a discount.
- Same exposure: PHYS and GLDM daily returns correlate 0.97; the rest is PHYS's premium/discount moving.

## The economics in one line
Selling PHYS today realises a price $1,474 below the gold it holds. That is only a cost if the discount would
have narrowed while you held. Break-even on the $152/yr fee saving (including about $31 of trading costs):
0.2 years if the discount stays at -2.8%; 1.6 years if it returns to -2.4%; 4.9 years if it returns to -1.5%;
9.9 years if it closes completely. Every further point of widening costs $525 to stay.

Why switch despite that: the discount has no mechanism that closes it for a holder this size (redemption for
metal needs roughly a full 400 oz bar) and it has widened for five straight years as 0.10% ETFs took share.
Holding PHYS is a bet on that reversing; B.5 is not paid for that bet. This is a judgement, not a measured edge.

## Execution (Casey enters the orders; nothing is automated)
1. Check the trigger: Sprott's PHYS page, "Premium / Discount" (previous close) at or narrower than -2.4%
   (Option A) - or any day (Option B).
2. Same session, 10:30-15:30 New York time, both legs within the same few minutes:
   SELL 1,872 PHYS, limit at the mid; BUY GLDM for the proceeds (about 712 shares at 2026-11-18 prices), limit at the mid.
3. Do not trade if: gold has moved more than 2% that day; GLDM's quoted spread is wider than 3 bps; or PHYS's
   intraday discount is wider than -3.4% (the widest of the last year).
4. Where a month-end band rebalance falls due first, do the swap in the same session so the gold leg trades once.
5. Same day, after the fills: the repo change set below, so the nightly monitor does not raise a false band alert.

## Repo change set (one commit, only after the trade; nothing is changed now)
- barbell-lab/config/data.yaml: add `GLDM: {proxy: GLD, splice_date: 2018-06-26}`; keep PHYS (history).
- barbell-lab/config/backtest.yaml: add `GLDM: 2` (bps, one-way).
- Portfolio register (the live source of truth): new version, PHYS 23.5% -> GLDM 23.5%, promoted to LIVE.
  config/portfolio.yaml is only the first-run seed (it still shows the v1.0 weights) and stays as is.
- barbell-lab/src/barbell/web/app.py (placeholder text), chat/agent.py (sleeve description),
  tests/test_monitors.py (fixture ticker): PHYS -> GLDM.
- Composer / IBKR mirror: B.5 is not referenced anywhere under composer/ (IBKR_MIRROR.md included), so there is
  no symphony to change and the two-broker parity check does not apply. The Composer connector was unreachable
  from this session, so this was checked in the repo only (question 2).
- Redeploy: barbell-lab.

## Kill and review criteria (fixed before any trade)
- No shadow run: the exposure is identical, so there is nothing a paper run could show.
- At 12 months: GLDM's total return should be within 0.20 pt of the LBMA gold price change less 0.10%. A wider
  shortfall is a review, not an automatic exit.
- No automatic switch back. Returning to PHYS would be a new, deliberate trade (for example at a discount
  beyond 5%), with its own write-up.
- If Option A's trigger has not fired by 2027-02-26 and the discount is then wider than -3.4%, stop and
  re-decide instead of forcing the sale.

## Caveats
- The discount history is reconstructed from the PHYS/GLD price ratio and anchored to Sprott's published NAV
  for one day; its error grows by roughly 0.1-0.2 pt per year going back. The 1- and 3-year figures are solid;
  nothing here leans on older ones.
- The break-even table values the discount against NAV; nobody knows where the discount goes next.
- Tax: under Act 60 no tax is assumed, and the PHYS lot showed an unrealised loss on 2026-11-18. Not tax advice;
  PHYS's usual US advantage (long-term rates instead of the 28% collectibles rate) is the one thing given up.
- Custody differs: PHYS holds allocated bars at the Royal Canadian Mint and large holders can redeem for metal;
  GLDM's bars are at JPMorgan in London with no redemption for metal.

## Questions for Casey
1. Why was PHYS chosen originally: tax treatment, or custody / redeemability? If custody, the 0.29%/yr is the
   price of that preference and Option C is the consistent choice.
2. Is there a B.5 symphony on Composer that this repo does not know about? If yes, it changes in the same step.
