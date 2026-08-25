# TLT/duration squeeze scorecard — draft spec v1 (pre-registration candidate)

Design principle from the analog study: **positioning is fuel, never ignition.**
0 of 22 large (≥80bp/3m) long-bond rallies since 1986 were positioning-caused;
5 of 22 were positioning-AMPLIFIED. Triggers are largely SCHEDULED events
(QRA, CPI/PCE, FOMC, auctions), so the early edge is state-tracking into
known dates, not detecting covering after it starts (2023: peak covering was
~6% of the net short book and round-tripped; COT confirms after the fact).

## FUEL conditions (how far a rally travels if ignited)
| id | condition | threshold | source | now (2026-08-25) |
|---|---|---|---|---|
| F1 | Lev-fund UST net short extreme | ≤10th pctile, 10y expanding | CFTC TFF (in canary) | MET -30.3%OI, 5th pctile |
| F2 | TLT SI % shares outstanding | ≥20% | FINRA bi-monthly + iShares SO | MET (pending exact verify) |
| F3 | Term premium elevated | ACM 10y TP ≥75th pctile since 2015 | FRED THREEFYTP10 | MET +0.84, 100th |
| F4 | Borrow stress (true squeeze microstructure) | fee >1%/util >90% | IBKR/Fintel | expected NOT MET |

## TRIGGER conditions (what ignites)
| id | condition | threshold | source | now |
|---|---|---|---|---|
| T1 | Fed pivot | first cut after hold ≥6m, or >50bp cuts priced 6m | canary fed_futures | NOT MET (hike risk priced) |
| T2 | Labor break | payrolls 3m avg <0 OR Sahm ≥0.50 | FRED PAYEMS/SAHMREALTIME | PARTIAL (Jul -23k; 3m avg TBD) |
| T3 | Inflation clears the path | core PCE 3m ann. <2.5% | FRED PCEPILFE | NOT MET (3.3% y/y) |
| T4 | Supply pivot | QRA cuts 10y/30y coupon sizes OR long-end buybacks >$25B/qtr | Treasury QRA/buyback anncs | PARTIAL (frozen sizes; $4B/op buybacks) |
| T5 | Flight-to-quality | MOVE >120 AND spreads widening | FMP ^MOVE + FRED HY OAS | NOT MET (MOVE 74) |

Score now: FUEL 3/4, TRIGGERS ~1/5 (two partials).
Read: a loaded spring with nobody pulling the trigger — and the Fed is
actively pushing the other way (Warsh; ~42% Sept HIKE odds after 3.4% CPI).

## Early-warning calendar (the "get in earlier" mechanism)
QRA: ~Feb/May/Aug/Nov 1 (next: early Nov 2026) · FOMC: Sep 15-16, Oct 27-28, Dec 8-9 (verify)
CPI: monthly ~day 10-13 · PCE: month-end · 30y auctions: mid-month (TreasuryDirect API)
Sahm/payrolls: first Friday. State tracked continuously; alerts on condition flips
and on T-minus-N days before each scheduled trigger with the current scorecard.
