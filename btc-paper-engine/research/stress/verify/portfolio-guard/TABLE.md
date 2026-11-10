# Independent re-implementation of the portfolio + guard layer: mine vs stress.py (offset 0, variant A, intrabar, start 100,000)
Code: verify.py (replay), sens.py (sensitivities), engine_check.py (leg_trades re-run + seam), seam_cf.py (seam counterfactuals).
Inputs: run JSONs' engine_trades + anchor/scale; O/H/L/C rebuilt from bars_4h_btcusd.csv (closes match saved spliced_closes to 1e-9 rel);
carry from carry_sleeve.simulate_carry (ETH spliced with its own scale, funding shifted by t0-anchor, 31d pre-window).

| scenario | K | 3m mine / theirs | 6m | 9m | 12m | maxDD | intrabar DD | exec halts | S3 engine halt (eq) | final |
|---|---|---|---|---|---|---|---|---|---|---|
| COVID | 0.75 | 101,595.85 / = | 106,116.22 / = | 116,329.61 / = | 138,629.33 / = | -15.59% / = | -15.62% / = | none / none | 2026-11-30 04:00 @ 74,486.45 / = | 138,573.93 / = |
| COVID | 0.30 | 103,211.29 / = | 108,278.34 / = | 114,173.28 / = | 129,869.68 / = | -6.00% / = | -6.01% / = | none / none | 2026-11-30 04:00 @ 74,486.45 / = | 129,876.70 / 129,876.69 |
| 2008 | 0.75 | 114,953.42 / = | 125,146.70 / = | 140,213.13 / = | 137,687.54 (last bar) / = | -7.31% / = | -8.35% / = | none / none | none / none | 137,687.54 / = |
| 2008 | 0.30 | 107,508.13 / = | 112,744.17 / = | 122,158.88 / = | 121,953.72 (last bar) / = | -3.28% / = | -3.61% / = | none / none | none / none | 121,953.72 / = |
| 1999 | 0.75 | 93,091.31 / = | 100,263.63 / = | 110,694.05 / = | 121,607.69 (last bar) / = | -14.45% / = | -14.52% / = | none / none | 2026-12-08 16:00 @ 72,086.43 / = | 121,607.69 / = |
| 1999 | 0.30 | 98,230.42 / = | 101,580.97 / = | 105,753.40 / = | 110,227.70 (last bar) / = | -5.23% / = | -5.26% / = | none / none | 2026-12-08 16:00 @ 72,086.43 / = | 110,227.70 / = |

Full curves (total, BTC book, carry, worst-intrabar) agree within $0.01 on every bar; fees, entry/trade counts, S4 paper-book end equity identical.
Sensitivities reproduced exactly: XBTUSD-proxy funding 118,776 / 126,406; engine halts off 151,023 / 111,261; variant B and close-only identical to A.
Residual differences (both non-headline, both the builder's definitional choices): hw_end (theirs ratchets HW on the intrabar favourable extreme; my
HW-intrabar sensitivity reproduces 139,254.92) and worst_day (theirs close-to-close; mine intrabar worst vs day start).
Engine lists: harness.leg_trades on the rebuilt spliced bars (33,174 real + 2,196 path) reproduces pullback 33 / trend 26 trades IDENTICALLY;
trend seam position = live (L 2026-09-18 16:00 @ 80,702.77, trail 83,274.67). Pullback seam: CSV 04:00 low 84,010.77 < limit 84,121.28 -> LONG (live said PENDING).
