# Catalyst event curation — drop log (as of 2026-08-19)

Candidates considered but NOT included in catalyst_events.json, and why.

## Dropped: price move too small / direction-inconsistent (price-verified against stockanalysis.com daily data)

- **SRPT accelerated approval of Elevidys (2023-06-22)** — stock FELL -7.9% on 2023-06-23 and kept sliding (narrow 4-5yo label disappointed). Move inconsistent with a "positive" label; the clean SRPT positive is the 2024-06-20 label expansion (+30.1% on 06-21), which is included.
- **AMLX Relyvrio FDA approval (2022-09-29)** — only +3.3% on 09-29 and -6.8% on 09-30; approval was fully priced in after the Sep 7 adcom (that adcom, +51.0% on 09-08, is included instead).
- **VRTX VX-548/suzetrigine Phase 3 acute-pain readout (2024-01-30)** — only +2.4% close-to-close; below the >5% mega-cap bar. The Dec 2024 suzetrigine LSR Phase 2 disappointment (-11.4%) is included instead.
- **RCKT Kresladi CRL (June 2024)** — no clean single-session print: -10.7% on 06-26 (pre-news drift), -11.3% open gap on 06-28 but +0.5% close-to-close. Ambiguous event-day attribution; dropped.
- **APLS Syfovre approval (2023-02-17 Fri)** — first post-news session 2023-02-21 shows +10.5% open gap but only +5.4% close-to-close (and +6.9% on 02-17 pre-announcement). Below the ~10% mid-cap bar and split across days; dropped as marginal.

## Dropped: no price data available (ticker delisted/acquired; stockanalysis.com and Stooq both return nothing in 2026)

- **ISEE (Iveric Bio) GATHER2 Zimura Ph3 (Sep 2022)** — acquired by Astellas 2023; series unavailable, cannot verify move.
- **RETA (Reata) Skyclarys/omaveloxolone approval (Feb 2023)** — acquired by Biogen 2023; series unavailable.
- **SAGE zuranolone MDD partial CRL (Aug 2023)** — acquired/delisted; series unavailable.
- **SAVA simufilam ReThink-ALZ Ph3 failure (2024-11-25)** — KEPT in the dataset but flagged `verified: false` with `day_move_pct: null`: announcement date confirmed via the company press release, but the ticker is gone from available price APIs so the ~-84% move could not be recomputed. Filter on `verified` for the quant study.

## Not pursued (weaker documentation or unclear single-day catalyst)

- NVAX 2022 events (adcom/EUA moves muddled by concurrent manufacturing news), BMRN Roctavian (muted reaction), NTLA/BEAM/ARWR/VERV (safety-hold or data events outside the five allowed event types or without clean moves), SLDB/TSHA/ELEV/MRUS/DVAX/ABOS/ANAB/FDMT/PTCT/EWTX/DYN (nothing clearly stronger than what was kept).

## Date corrections vs the candidate prompt list

- SRRK apitegromab SAPPHIRE: actual topline was **2024-10-07** (+362.0%), not Apr 2025.
- QURE AMT-130: the market-moving pivotal readout was **2025-09-24** (+247.7%), not July 2025 (July 2025 shows no outsized QURE move).
- KRTX EMERGENT-2: actual date **2022-08-08** (+71.8%), not Aug 2023.
- ABVX ABTECT: PR dated 2025-07-22 but the move printed **2025-07-23** (+586.0%) — after-hours/pre-market release.
- KROS TROPOS partial halt: **2024-12-12** (-73.2%); the full topline/discontinuation came May 2025.
- Substitutes added for the delisted negatives: AKRO SYMMETRY miss (2023-10-10, -62.6%), APLT govorestat CRL (2024-11-29, -76.3%), GOSS TORREY (2022-12-06, -74.6%), RARE + MREO setrusumab Orbit interim miss (2025-07-10).
