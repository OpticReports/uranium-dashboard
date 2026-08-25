# Duration-squeeze scorecard — spec v2 (counter-agent corrections applied)

Design principle from the analog record: **positioning is fuel, never ignition.**
In 22 episodes of ≥80bp/3m 30-yr yield drops since 1986, none was identified
where positioning was the sole cause (21 macro-triggered, 1 policy-triggered,
5 positioning-amplified) — with the stated caveat that the coding cannot rule
such episodes out, and the one canonical positioning-driven event (the Oct 15
2014 flash rally) sits below the 80bp threshold. Triggers are largely SCHEDULED
(QRA, CPI/PCE, FOMC, auctions): the early edge is state-tracking into known
dates, not detecting covering after the fact (2023, contracts basis: the
futures book covered ~10% Oct 31→Dec 12 and rebuilt by Jan 2; the ETF book
GREW 52→81M shares into Dec 15 and covered only in the final two weeks).

Measurement notes (honesty): TLT figures are PRICE returns (FMP closes,
no dividend adjustment; 6m total returns run ~1.5-2pp higher). The
crowded-short conditional edge (42% vs 38% ≥50bp; 14% vs 9% ≥100bp at 6m
best) is WITHIN NOISE (~22 independent episodes; block-bootstrap 95% CI on
both differences straddles zero). Signed 6m outcomes show NO directional
edge (P(30y down)=53% both arms). Legacy long-end COT has a composition
break (Ultra Bond added Mar 2010); COT report date (Tue) precedes release
(Fri) — a 3-day untradeable lag embedded in any conditional stat.

## FUEL (how far a rally travels if ignited) — now 2/4
| id | condition | registered threshold | source | 2026-08-25 |
|---|---|---|---|---|
| F1 | Lev-fund UST net short extreme | ≤10th pctile, 10y expanding window | CFTC TFF (canary cftc.py) | MET: -30.3%OI, 9.2th pctile (4.6th since 2006) |
| F2 | TLT SI % shares outstanding | ≥20% | FINRA consolidated SI + iShares SO | NOT MET: 95.3M / 571.3M = 16.7%, FALLING (peak ~26-28% Dec-25) |
| F3 | Term premium elevated | ACM 10y TP ≥75th pctile since 2015 | FRED THREEFYTP10 | MET: +0.84, 99.7th |
| F4 | Borrow stress | fee >1% or util >90% | IBKR/Fintel (UNVERIFIED today; GC ~30bp per S3) | NOT MET (DTC 3.6) |

## TRIGGERS (what ignites) — now 0.5/5
| id | condition | registered threshold | source | 2026-08-25 |
|---|---|---|---|---|
| T1 | Fed pivot | first cut after ≥6m hold, or >50bp cuts priced 6m | canary fed_futures.py | NOT MET: 0 cuts in 2026; ~42% Sept HIKE odds |
| T2 | Labor break | payrolls 3m avg <0 OR Sahm ≥0.50 | FRED PAYEMS / SAHMREALTIME | NOT MET: +20k 3m avg, Sahm -0.03 (decelerating: +214→+148→+63→+20→-23k) |
| T3 | Inflation clears path | core PCE 3m annualized <2.5% | FRED PCEPILFE | NOT MET: 2.89% (note: core CPI 3m ann 1.64% — the two gauges disagree; single-gauge fragility) |
| T4 | Supply pivot | QRA cuts 10y/30y coupons OR long-end buybacks >$25B/qtr | Treasury QRA/buyback anncs | PARTIAL: coupons frozen 2 yrs, buybacks doubled to ≥$4B/op (~$8B/qtr long-end) — intent without scale |
| T5 | Vol/dislocation state (renamed from flight-to-quality: fires on duration capitulation too) | MOVE >120 AND HY OAS widening | FMP ^MOVE + FRED BAMLH0A0HYM2 | NOT MET: MOVE 74 (41st pctile), HY OAS 2.70 flat |

## Point-in-time backtest: Oct 31, 2023 (the flagship analog) = FUEL 2/4, TRIGGERS 2/5
F1 MET (1st pctile PIT) · F2 NOT (SI ~11% SO) · F3 MET (TP 100th pctile since 2015) · F4 NOT
T1 NOT · T2 NOT (payrolls 3m avg +179k revised / ~+240k real-time, Sahm 0.2-0.33) ·
T3 MET (core PCE 3m ann 2.05-2.26%) · T4 NOT — but the QRA that met it was a SCHEDULED
date one day out · T5 MET (MOVE 127-135, HY OAS widening 3.77→4.42)

**Admission (counter-agent finding 5): the trigger side has near-zero anticipatory
power for scheduled-event ignition** — Oct 2023 scored 2/5 the day before a +21%
rally lit by three events no condition anticipated. The scorecard's real content:
FUEL + inflation runway (T3) + dislocation state (T5) + the trigger CALENDAR.
The two triggers lit in Oct 2023 (T3, T5) are exactly the two most absent today.

## Trigger calendar (the "get in earlier" mechanism)
QRA ~Feb/May/Aug/Nov (next: early Nov 2026) · FOMC Sep/Oct/Dec 2026 · CPI ~10-13th
monthly · PCE month-end · 30y auctions mid-month (TreasuryDirect API: tails,
bid-to-cover) · payrolls first Friday. Track state continuously; alert on condition
flips and T-minus-N days into each scheduled trigger with the live scorecard.
