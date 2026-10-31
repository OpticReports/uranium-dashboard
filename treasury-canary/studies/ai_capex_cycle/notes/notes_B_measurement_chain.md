# Finder B — measuring the AI capex cycle as a chain of free, machine-readable series

Date of work: 2026-10-31. Every endpoint below was probed from this container today; status, shape, latest value and date are
recorded. Raw fetches in `raw/` (158 files, 46 MB); probe/build scripts in `scripts/` (run with `python3 -I`, never from inside `raw/`).
Scope exclusion per brief: the bond-issuance tally and the existing AI-debt tab series (ICE OAS, EBP, OFR FSI, BDC P/NAV, term
premium) are NOT redone; they appear only as nodes in the chain.

Environment notes that affect the recommendations:
- `data.sec.gov` (XBRL companyfacts/companyconcept/frames, submissions) works with the UA header. `www.sec.gov` (Archives,
  company_tickers.json) returned **403 "Request Rate Threshold Exceeded"** from this proxy IP all session, so filing bodies
  could not be read here; the production box should be fine at <=10 req/s but needs a fallback.
- EDGAR full-text search: `https://efts.sec.gov/LatestSearch/index` -> 403; **`https://efts.sec.gov/LATEST/search-index?q=...` -> 200** (Elasticsearch JSON). Use the latter.
- TSMC IR (`investor.tsmc.com`) is behind Cloudflare JS challenge (403). Taiwan MOPS (`mops.twse.com.tw`) blocks non-browser
  clients. **TWSE OpenAPI works** (see 2b).
- FMP key present (`FMP_API_KEY`); legacy `/api/v3/*` returns 403 "Legacy Endpoint" — only `/stable/*` works. Tiingo key is NOT in this
  session's env (`TIINGO_API_KEY` is referenced in repo code but unset here); Tiingo endpoints answered 403 "Please supply a token", so Tiingo claims below are untested.

---------------------------------------------------------------------------------------------------------------------------------

## 1. THE CHAIN (nodes -> edges -> the series that measures each edge)

```
 (a) SPENDERS                         (b) RECIPIENTS                         (e) MACRO CHANNEL
 ┌──────────────────────────┐  capex  ┌──────────────────────────────┐       ┌──────────────────────────────────┐
 │ MSFT AMZN GOOGL META ORCL│ ──────► │ NVDA AMD AVGO MU TSM SK Hynix│ ────► │ BEA: info-processing equipment   │
 │ XBRL PaymentsToAcquire*  │  $231bn │ revenue, RPO, receivables,   │       │  Y034RC1Q027SBEA  $934bn SAAR Q3 │
 │ Q3-26, 5 cos combined    │  /qtr   │ inventory, DSO               │       │  contribution 0.86pp (Y034RY2)   │
 │ + CRWV NBIS (neoclouds)  │         │ TSMC monthly rev (TWSE API)  │       │ Census data-center construction  │
 │ + labs (commitments only)│         │ DRAM spot (DRAMeXchange)     │       │  $85.0bn SAAR Aug-26, +73% yoy   │
 └───────────┬──────────────┘         └──────────────┬───────────────┘       │ term premium, VXN, NDX conc.     │
             │ financed by                           │ paid with              └──────────────────────────────────┘
             ▼                                       ▼
 (c) FINANCING                                (d) DEMAND / MONETISATION
 ┌──────────────────────────────────┐        ┌──────────────────────────────────────────────┐
 │ OCF (XBRL)  capex/OCF = 1.17 Q3  │        │ RPO/backlog: MSFT 683, GOOGL 568, ORCL 664,   │
 │ bonds (EXISTING TAB, $682bn)     │        │  CRWV 104, AVGO 179, MU 134 ($bn, XBRL)       │
 │ finance leases (XBRL ROU added)  │        │ cloud rev growth (FMP segments / transcripts)│
 │ SPVs/JVs (text only, 8-K)        │        │ GPU rental spot (RunPod GraphQL, free)        │
 │ vendor finance & circular equity:│        │ depreciation vs capex (XBRL Depreciation)     │
 │  NVDA non-marketable equity      │        │ useful-life changes (EFTS text search)        │
 │  $47.9bn Jul-26 (XBRL)           │        └──────────────────────────────────────────────┘
 └──────────────────────────────────┘
             │
             ▼
 (f) PRICING-IN                                                      (g) LEADING THROTTLE INDICATORS
 ┌──────────────────────────────────────────────────────────┐       ┌────────────────────────────────────────────┐
 │ consensus capex: NOT in FMP; use transcript guidance     │       │ guidance language (EFTS), TSMC monthly rev,│
 │ NVDA fwd P/E 25.7x TTM vs FY28E rev +… (FMP estimates)    │       │ DRAM spot, Census DC permits/spend, ERCOT  │
 │ CBOE iv30: NVDA 44 ORCL 55 CRWV 107 MSFT 27 (free)        │       │ large-load queue (not machine-readable),   │
 │ ORCL 5.95% 2055 price 73.59 (Boerse Frankfurt, free)      │       │ NVDA DSO 59.6d / DIO 119d, neocloud bonds, │
 │ FINRA short interest NVDA 301.6m sh, CRWV 69.8m sh (free) │       │ spender/recipient equity dispersion        │
 │ spenders -7.7% YTD vs recipients +71% (FMP prices)        │       └────────────────────────────────────────────┘
 └──────────────────────────────────────────────────────────┘
```

### 1(c) Disclosed circular / vendor-financing deals (Nvidia–OpenAI–Oracle–AMD–CoreWeave ring)

EDGAR full-text search `q=OpenAI, forms=8-K, ciks=ORCL,NVDA,AMD,CRWV,AVGO, 2025-01-01..2026-10-31` returned 32 hits
(`raw/efts_openai_8k.json`); the accession numbers below are from that result. Filing BODIES could not be read here
(www.sec.gov 403), so amounts are from the public announcements as of my knowledge (complete only to ~mid-2026) and are
marked VERIFY where the 8-K text should be re-read on the production box.

| Date | Parties | Disclosed terms | Primary source |
|---|---|---|---|
| 2025-01-21 | OpenAI / Oracle / SoftBank ("Stargate") | $500bn over 4 yrs announced; $100bn "immediately" | press (no 8-K) |
| 2025-03-10 | CoreWeave – OpenAI | $11.9bn 5-yr capacity contract + $350m OpenAI equity in CRWV | S-1/A; CRWV 8-K exhibits 2025-05 (0001769628-25-000003) |
| 2025-05 / 2025-09-25 | CoreWeave – OpenAI expansions | +$4.0bn (May) and +$6.5bn (Sep) -> $22.4bn total | CRWV 8-K 0001193125-25-216497 (2025-09-25) |
| 2025-07-22 | Oracle – OpenAI | +4.5 GW Stargate capacity | press; ORCL 8-K ex99.1 2025-09-09 (0001193125-25-199175) discloses RPO $455bn / "four multi-billion contracts" |
| 2025-09-10 | Oracle – OpenAI | ~$300bn cloud contract over ~5 yrs from 2027 (WSJ; not itemised by Oracle) | ORCL 10-Q Q1 FY26 RPO; VERIFY counterparty never named by Oracle |
| 2025-09-22 | Nvidia – OpenAI | LOI: 10 GW Nvidia systems; Nvidia to invest up to $100bn progressively per GW deployed | Nvidia newsroom; no 8-K found |
| 2025-09-25 | Nvidia – CoreWeave | Nvidia to buy any unsold CRWV capacity through Apr-2032, $6.3bn backstop | CRWV 8-K 0001193125-25-216497 + EX-10.1 |
| 2025-10-06 | AMD – OpenAI | 6 GW Instinct GPUs (1 GW MI450 from H2-26); warrant for up to 160m AMD shares vesting on deployment/price milestones | AMD 8-K 0001193125-25-230895 (EX-99.1, EX-4.1 warrant, EX-10.1) — verified titles |
| 2025-10-13 | Broadcom – OpenAI | 10 GW custom accelerators 2026-29; no $ disclosed | press |
| 2025-10-14 | AMD – Oracle | 50,000 MI450 GPUs from Q3-26 | press |
| 2025-10-28 | Microsoft – OpenAI | OpenAI commits incremental $250bn Azure; MSFT ~27% stake in OpenAI Group PBC | MSFT 8-K/blog; VERIFY |
| 2025-11-03 | Amazon – OpenAI | $38bn 7-yr AWS compute | press |
| 2025-11-18 | Nvidia / Microsoft – Anthropic | Nvidia up to $10bn, MSFT up to $5bn equity; Anthropic commits $30bn Azure | press |
| 2025-09-08 | Nebius – Microsoft | $17.4bn (up to $19.4bn) 5-yr capacity | NBIS 6-K |
| 2025-09-30 / 2025-11 | Meta – CoreWeave / Meta – Nebius | $14.2bn to 2031 / $3bn | CRWV 8-K; press |
| 2025-10-21 | Meta – Blue Owl (Hyperion SPV) | $27bn JV, Meta 20% equity; financing side already in AI-debt tab | META 8-K |
| 2026-01 | Nvidia – CoreWeave equity | ~$2bn additional Nvidia investment in CRWV (reported) | VERIFY via CRWV 8-K |
| 2026-08-17 | Nvidia (exhibit "sbeoainvidia…") | Nvidia 8-K + EX-99.1 — SoftBank/OpenAI/Nvidia announcement; **unread here, post-cutoff** | NVDA 8-K 0001045810-26-000069 |
| 2026-09-17 | CoreWeave convertible | EX-1.1 underwriting + investor presentation (EX-99.2) | CRWV 8-K 0001769628-26-000429 |

The one FREE quantitative aggregate of the circular ring: Nvidia's `us-gaap:EquitySecuritiesWithoutReadilyDeterminableFairValueAmount`
(non-marketable equity investments) — **$1.3bn (Jan-24) -> 3.8 (Jul-25) -> 8.2 (Oct-25) -> 22.3 (Jan-26) -> 42.3 (Apr-26) -> $47.9bn (Jul-26)**,
quarterly, in `raw/facts_NVDA.json`. Pair with Nvidia receivables (below) and the CRWV backstop. Nvidia's `PurchaseObligation`
tag stops at 2025-07-27 ($45.8bn); later supply commitments moved to `UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount`
($22.7bn at 2026-01-25, 10-K only) — tag drift to watch.

---------------------------------------------------------------------------------------------------------------------------------

## 2. Node-by-node: best FREE series, probed, with the paid alternative

### 2a. Spenders — hyperscaler capex and OCF from EDGAR XBRL (FREE, quarterly, lag ~30 days after quarter end, history to 2008+)

Endpoint probed: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (one call per company, 0.5–5 MB, 200 OK with UA
header) — preferred over `companyconcept` because it exposes every tag, which is how the variants below were found. `frames` was
also probed: `/api/xbrl/frames/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment/USD/CY2026Q2.json` -> 200 but only 199 filers and
NO hyperscalers (frames only carries facts whose duration is exactly one quarter; AMZN/GOOGL/META report 6M/9M YTD so their Q2/Q3
never get a frame). CY2026Q3 frame has 51 filers incl. MSFT 39.4 and ORCL 28.5. **Verdict: use companyfacts + YTD-differencing, not frames.**

Tag map (what each company actually files — verified in `facts_tag_survey.txt`):

| Co | CIK | FYE | Capex tag(s) | Notes / restatement quirks |
|---|---|---|---|---|
| MSFT | 789019 | Jun | `PaymentsToAcquirePropertyPlantAndEquipment` | Reported "capex incl. finance leases" ($45.2bn FQ1-27 per call) is NOT a single tag: add `RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability` (Q3-26 $5.2bn). Fiscal quarters map 1:1 to calendar. |
| AMZN | 1018724 | Dec | **`PaymentsToAcquireProductiveAssets`** (from 2017Q3) | `PaymentsToAcquirePropertyPlantAndEquipment` stops 2017-03-31. Amazon's "cash capex" in releases nets proceeds/incentives: Q3-26 XBRL gross 77.26 vs "$75.9bn" on the call. Finance-lease additions separate (`RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability`, Q3-26 $1.5bn). Files 3M+9M+TTM facts; TTM facts carry frame "CY2026" (misleading) — filter by duration, not frame. |
| GOOGL | 1652044 | Dec | `PaymentsToAcquirePropertyPlantAndEquipment` | YTD-only for Q2/Q3; `CapitalExpendituresIncurredButNotYetPaid` $35.9bn at Q3-26 (accrued capex — a leading indicator of next quarter's cash capex). |
| META | 1326801 | Dec | `PaymentsToAcquirePropertyPlantAndEquipment` + `FinanceLeasePrincipalPayments` | Meta's reported capex definition includes finance-lease principal; sum of the two reproduces $34.9bn Q3-26 exactly. |
| ORCL | 1341439 | May | `PaymentsToAcquirePropertyPlantAndEquipment` | Fiscal Q1 (Jun–Aug) maps to calendar Q3 by period end; Oracle guides "gross" ($90–95bn FY27) vs "net cash capex" (<=$70bn, net of prepayments/customer-funded) — XBRL is gross. |
| CRWV | 1769628 | Dec | `PaymentsToAcquirePropertyPlantAndEquipment` | XBRL cash capex Q2-26 $6.42bn vs "CapEx $9.4bn" on call (CoreWeave's definition adds financed/accrued equipment). Q3-26 10-Q not yet filed (due ~mid-Nov). |
| NBIS | 1513845 | Dec | 20-F filer; companyfacts carries only RUB-era Yandex facts + one USD RPO ($21.3bn FY25) | Useless for capex; use 6-K press releases / transcripts (Q2-26 capex ~$5.7bn, 2026 guide $20–25bn). |
| NVDA / AMD / AVGO / MU | 1045810 / 2488 / 1730168 / 723125 | Jan / Dec / Oct / Aug | NVDA uses `PaymentsToAcquireProductiveAssets`; others `…PropertyPlantAndEquipment` | Recipients' own capex (MU FY26 $30.7bn) is the second-order spend. |

**Built series** (deliverable): `raw/hyperscaler_capex_ocf_quarterly.csv` — calendar quarters 2018Q4–2026Q3, per-company end date,
capex, OCF, AMZN/MSFT finance-lease additions, combined capex, combined OCF, capex/OCF, n_cos (all 5 present in every row).
Method: dedupe facts by (start,end) keeping latest filing (captures restatements); single-quarter facts taken directly; Q4 and
YTD-only quarters derived by differencing same-start cumulative facts; fiscal period ends mapped to nearest calendar quarter.

Combined 5-co capex / OCF ($bn, calendar quarters):

| Qtr | Capex | OCF | Capex/OCF | MSFT | AMZN | GOOGL | META | ORCL |
|---|---|---|---|---|---|---|---|---|
| 2023Q4 | 44.3 | 99.8 | 0.44 | 9.7 | 14.6 | 11.0 | 7.9 | 1.1 |
| 2024Q4 | 76.7 | 136.3 | 0.56 | 15.8 | 27.8 | 14.3 | 14.8 | 4.0 |
| 2025Q2 | 97.8 | 134.6 | 0.73 | 17.1 | 32.2 | 22.4 | 17.0 | 9.1 |
| 2025Q3 | 106.3 | 167.1 | 0.64 | 19.4 | 35.1 | 24.0 | 19.4 | 8.5 |
| 2025Q4 | 131.4 | 180.9 | 0.73 | 29.9 | 39.5 | 27.9 | 22.1 | 12.0 |
| 2026Q1 | 149.2 | 157.9 | 0.95 | 30.9 | 44.2 | 35.7 | 19.8 | 18.6 |
| 2026Q2 | 182.5 | 186.4 | 0.98 | 35.8 | 54.2 | 44.9 | 31.1 | 16.5 |
| **2026Q3** | **231.4** | **198.6** | **1.17** | 39.4 | 77.3 | 51.4 | 34.9 | 28.5 |

- 2025 full year combined: **$414.1bn**. 2026 YTD (cal Q1–Q3): **$563.1bn capex vs $542.9bn OCF** — the group is cash-flow
  negative before buybacks/dividends; per-company 2026 YTD: MSFT 106.0, AMZN 175.7, GOOGL 132.0, META 85.8, ORCL 63.6.
- Q3-26 yoy growth +118%; q/q +27%. The "peak growth" question is whether 2027 yoy falls below this — guidance says 2027 is still
  up (AMZN "meaningfully more", GOOGL "increase significantly", MSFT "accelerate in H2 FY27"), so growth peaks in RATE not level.
- Checks: 2025 sums reconcile to 10-Ks (AMZN 131.8, GOOGL 91.5, META 72.2 incl. leases, MSFT FY25 64.5 excl. leases).

### 2b. Recipients

| Series | Endpoint (probed) | Status / shape | Latest | Freq / lag / history |
|---|---|---|---|---|
| TSMC monthly revenue | `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` (JSON, 1,088 listed cos; filter 公司代號=2330) | 200, fields: 資料年月 (ROC yyyMM), 當月營收 (NT$ thousands), 去年同月增減(%), 累計 | **Sep-2026 NT$511.9bn, +54.6% yoy; YTD +41.1%**; posted 2026-10-17 | Monthly, ~10th of next month; **only latest month per call — poll & store** (no history in API; TSMC IR history page is Cloudflare-blocked) |
| NVDA revenue, receivables, inventory | companyfacts NVDA: `Revenues`, `CostOfRevenue`, `AccountsReceivableNetCurrent`, `InventoryNet` | built `raw/nvda_dso_dio.csv` | FQ2-27 (2026-07-26): rev $96.2bn, AR **$63.1bn**, inventory **$31.6bn**, **DSO 59.6d (from 45.4 prior qtr; 42.8 in Jul-24), DIO 119d, AR/rev 0.655** | Quarterly, ~4 wks lag; FQ3 10-Q due ~late Nov |
| NVDA RPO | `RevenueRemainingPerformanceObligation` | $3.2bn (Jul-26) — small; Nvidia is book-and-ship | | |
| AVGO / MU / AMD | companyfacts | AVGO RPO **$179.2bn** (Aug-26, from 33.3 Nov-25); MU FY26 rev $133.2bn, capex $30.7bn, RPO $134bn (new tag FY26); AMD Q2-26 capex $1.2bn | | |
| DRAM spot | `https://www.dramexchange.com/` HTML table (free, scrape) | 200; row "DDR5 16Gb (2Gx8) 4800/5600  high 73.00 low 47.30 avg **61.50** +0.27%", DDR4 16Gb avg 82.80, dated Oct-30-2026 | daily | DXI index value is loaded by AJAX (`/Price…`), not in static HTML; contract prices are paid (TrendForce) |
| SK Hynix / Samsung | not probed (IR PDFs, quarterly) | — | — | Paid alternative: none needed; use quarterly IR releases manually |

### 2c. Financing (beyond the existing bond tally)
- OCF: `NetCashProvidedByUsedInOperatingActivities` (all five; in the CSV). Capex/OCF above.
- Finance leases: `RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability` (MSFT Q3-26 $5.2bn; AMZN $1.5bn) and stock
  `FinanceLeaseLiability` (MSFT **$71.0bn**, AMZN 14.5, ORCL 9.2, GOOGL 3.7, META 1.2 at latest quarter) — MSFT's lease book is the
  biggest off-bond financing line and is free.
- Accrued/unpaid capex: `CapitalExpendituresIncurredButNotYetPaid` — GOOGL $35.9bn, META 21.1, ORCL 6.2, AMZN 27.0 (FY25) — a
  free supplier-credit measure.
- Purchase commitments: `UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount` — **META $355.7bn** (Q3-26), ORCL 34.2, GOOGL 75.6 (Q1-26).
- SPVs/JVs: text only (8-K Item 1.01/2.03). Not machine-readable; EFTS query `"joint venture" AND "data center"` is the detector.
- Circular equity: NVDA non-marketable equity $47.9bn (above).
- Bond prices (free): Boerse Frankfurt `https://api.boerse-frankfurt.de/v1/data/quote_box/single?isin=US68389XDR35&mic=XFRA`
  -> 200, ORCL 5.95% 2055 **lastPrice 73.59 (2026-10-30 16:01Z), -1.64% d/d**. `price_history`, `bond_search`, `master_data_bond`
  all returned `{}` (need browser headers/trace-id) — quote_box with known ISINs is the only reliable call; **daily poll, no backfill**.
  CoreWeave ISIN candidates (US21873LAA68/AB42/AC25/AD08, USU2208WAA67/AB41) all 400 — CRWV 144A notes are not listed in Frankfurt;
  CRWV bond price has no free source found (FINRA TRACE `corporateBondsDaily` = 401 without API credentials).

### 2d. Demand / monetisation
- RPO (`RevenueRemainingPerformanceObligation`, instant, quarterly), built `raw/rpo_quarterly.csv`:
  MSFT 321 (Mar-25) -> **683** (Sep-26); GOOGL 92 -> **568**; ORCL 130 -> **664**; AVGO 22 -> **179**; CRWV 15 -> **104** (Jun-26); MU 134 (new);
  NBIS 21 (FY25). Sum of the three cloud RPOs ≈ **$1.9tn** (Nvidia's call: "cloud industry backlog > $2tn"). AMZN stopped tagging RPO in
  2020 — AWS backlog is text-only in the 10-Q ("$…bn, weighted-average remaining life …") -> EFTS/regex.
- Cloud revenue growth: FMP `/stable/revenue-product-segmentation?symbol=MSFT&period=quarter` -> 200 ("Server products and cloud
  services" $37.1bn FQ4-26); AWS/Google Cloud via same endpoint (paid). Free alternative: segment XBRL is dimensional and NOT in
  companyfacts — text/EFTS only.
- GPU rental spot (free): RunPod GraphQL `POST https://api.runpod.io/graphql {gpuTypes{displayName lowestPrice(input:{gpuCount:1}){uninterruptablePrice}}}`
  -> 200 unauth, 48 GPU types: **H100 SXM $2.69/h, H200 SXM $3.59, B300 $6.94, A100 SXM $1.39** (2026-10-31). Vast.ai bundles -> 403
  unauth; SFCompute `/v0/prices` -> 404; Lambda pricing page 301. **RunPod is the only free, keyless, structured GPU price feed found**
  — poll daily and store; it is a single-vendor list price, not a market index.
- Depreciation vs capex: `Depreciation` quarterly — MSFT 11.1, AMZN 15.1, GOOGL 8.4, META 6.8, ORCL 3.2 ($bn, latest qtr) = ~$45bn
  vs $231bn capex -> D&A/capex 0.19 (the "depreciation wall" is ~4–5 years out at current lives).
- Useful-life changes: `PropertyPlantAndEquipmentUsefulLife` is dimensional (not in companyfacts). EFTS `q="useful lives" servers,
  ciks=5 hyperscalers, 10-K/10-Q 2025–26` -> 36 hits (META 10-K 2026-01-29, AMZN 10-K 2026-02-06, ORCL 10-K 2025-06-18 …) — the detector
  works; the body must be read from Archives.

### 2e. Macro channel (FRED CSV, keyless: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=`; all 200; quarterly SAAR, latest 2026Q3 advance, lag ~30 days, history to 1947/2007)

| FRED ID | Title (verified from series page) | 2026Q3 | 2026Q2 | 2025Q3 |
|---|---|---|---|---|
| **Y034RC1Q027SBEA** | PFI nonres equipment: Information processing equipment, nominal $bn | **933.9** | 836.4 | 663.3 (+40.8% yoy) |
| **Y034RY2Q224SBEA** | Contribution to real GDP growth: information processing equipment, pp | **0.86** | 0.19 | 0.30 |
| Y034RX1Q020SBEA | Real info-processing equipment, 2017$ bn | 854.9 | 789.7 | 662.2 |
| B935RC1Q027SBEA | …Computers and peripheral equipment, nominal | **504.1** | 420.1 | 295.7 (+70% yoy) |
| B935RY2Q224SBEA | contribution, computers & peripherals, pp | 0.72 | -0.09 | 0.39 |
| B985RC1Q027SBEA / B985RY2Q224SBEA | Software nominal / contribution | 831.5 / 0.23 | 809.3 / 0.33 | 762.8 / 0.08 |
| A679RC1Q027SBEA | Info processing equipment AND software, nominal | 1765.4 | 1645.7 | 1426.0 |
| Y033RY2Q224SBEA | contribution, all nonres equipment | 1.16 | 0.74 | 0.47 |
| A006RY2Q224SBEA | contribution, gross private domestic investment | 3.27 | 0.82 | 0.15 |
| B009RC1Q027SBEA | PFI nonres structures (data-center bldgs sit here; not separable in BEA) | 966.0 | 935.3 | 951.7 |
| TLOFCONS (monthly) | Census construction spending: Office (total, SAAR $m) | Aug-26 **150,669** | Jul 145,057 | |
| THREEFYTP10 / VXNCLS / NASDAQ100 | term premium / Nasdaq-100 vol / NDX level | 0.936 (10-23) / 25.18 (10-29) / 29,402.5 | | |

Not on FRED: 404 for TLPRCONS, PNFICONS, A007RC1Q027SBEA, B009RY2Q224SBEA (don't use). BEA API itself needs a free registered key
(not probed); FRED mirrors suffice.

**Census data-center construction (the direct series):** Census VIP API (`api.census.gov/data/timeseries/eits/vip`) redirects to
"Missing Key" (free key required). The keyless route is the release xlsx:
- `https://www.census.gov/construction/c30/xlsx/privsa.xlsx` -> 200 (31 KB): row "Data center", SAAR $m: **Aug-26p 84,950**, Jul 79,007,
  Jun 72,695, May 65,688, Apr 61,859, Aug-25 49,052 -> **+73.2% yoy, +7.5% m/m**.
- `https://www.census.gov/construction/c30/xlsx/privtime.xlsx` -> 200 (175 KB): monthly NSA history Jan-1993.. (data-center column from 2014);
  extracted to `raw/census_datacenter_monthly.csv` (404 rows). Annual NSA: 2019 8.5bn, 2022 12.6, 2023 20.0, 2024 34.8, **2025 49.7**;
  Jan–Aug 2026 **45.2bn vs 31.9 (2025) = +41.7% yoy**. Monthly, released ~1st business day, 2-month lag, revised twice.

### 2f. Pricing-in — see §3.

---------------------------------------------------------------------------------------------------------------------------------

## 3. "Priced in": what is actually measurable

| Item | Free? | Probe result | Latest |
|---|---|---|---|
| (i) Sell-side consensus CAPEX 2026/27 and revision history | **No free source; FMP does NOT carry it** | FMP `/stable/analyst-estimates` -> 200 but fields are revenue/ebitda/ebit/netIncome/sga/eps only (keys dumped). Koyfin/Visible Alpha/Bloomberg (paid, no API in scope). | — |
| (i-b) Company capex GUIDANCE (the free substitute) | Yes via FMP transcripts (paid key) or EFTS -> 8-K ex99.1 (free) | FMP `/stable/earning-call-transcript?symbol=&year=&quarter=` -> 200 for all 8 tested; regex `capital expenditure|capex` + `$|billion` pulls the guidance sentence in every case | MSFT FQ1-27 capex $45.2bn incl leases, FQ2 ">$50bn", H2 "accelerate"; **AMZN 2026 ~$220bn, 2027 "meaningfully more"**; **GOOGL 2026 $195–205bn unchanged, 2027 "increase significantly"**; **META 2026 $135–145bn (narrowed from 130–145)**; **ORCL FY27 $90–95bn gross / <=$70bn net cash**; CRWV 2026 $35–39bn; NBIS 2026 $20–25bn; Nvidia (Aug-26): "top-5 hyperscaler capex ~$800bn 2026, $1.3tn 2027". Sum of 2026 guides ≈ $800bn+ ⇒ Q4-26 implied ≈ $240–250bn. FMP `/stable/earning-call-transcript-dates` gives the call calendar. |
| (ii) Equity-implied growth for recipients | FMP (paid) | `/stable/ratios-ttm?symbol=NVDA` P/E TTM **25.7x**, P/S 16.3x; `/stable/key-metrics-ttm` EV/Sales 16.3x, EV/EBITDA 21.2x; `/stable/analyst-estimates` NVDA FY28 (Jan-28) rev **$693.7bn** (42 analysts), FY29 925.2, FY30 1,106.5, FY31 1,211.5 (growth decelerating 33% -> 20% -> 9%); `/stable/price-target-consensus` 339 vs price 204.64; `/stable/quote` mcap $4.93tn. Fwd P/E on FY28E NI $380bn ≈ **13x** — the market is NOT pricing the consensus ramp; that gap is the "slowdown priced in" metric. | 2026-10-30 |
| (iii) Credit pricing of spenders | Partly free | Boerse Frankfurt quote_box ORCL 5.95% 2055 **73.59** (yield ≈ 8.3%+ vs par-ish at issue Sep-25; needs daily store); CRWV: no free price (144A, not Frankfurt-listed; FINRA TRACE API 401 w/o credentials; TRACE data via FINRA Developer Center needs a free registration + agreement). CDS = paid only. | 2026-10-30 |
| (iv) Spender vs recipient equity dispersion (cycle-phase) | FMP (paid) `/stable/historical-price-eod/light` | Equal-weight YTD-2026: **spenders (MSFT AMZN GOOGL META ORCL) -7.7%** vs **recipients (NVDA AMD AVGO MU TSM VRT) +71.1%** vs neoclouds (CRWV NBIS) +30.4%. Last 3m: -1.9% / -0.7% / **-21.3%** — neoclouds rolled first (CRWV -23.5%, NBIS -19.0%), classic late-cycle sequencing. ORCL -33% YTD, GOOGL -21% 3m. Free alternative: Yahoo `query1.finance.yahoo.com/v8/finance/chart/NVDA?range=…` -> 200 (undocumented); Stooq -> connection reset. | 2026-10-30 |
| (v) Options-implied vol / skew | **Free** | CBOE `https://cdn.cboe.com/api/global/delayed_quotes/options/{SYM}.json` (follow 307 to cdn-api) -> 200, full chain with per-option iv/delta/OI + `iv30`: **NVDA 44.1, ORCL 54.8, CRWV 106.9, MSFT 27.3** (2026-10-31). Skew computable from the chain (25-delta put–call iv). `VXN_History.csv` -> 200, close **28.50 (10-30)**. Yahoo options -> 401 (crumb). | daily, 15-min delay |
| (vi) Short interest | **Free** | FINRA `POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest` (no auth) with `compareFilters symbolCode` + `dateRangeFilters settlementDate` -> 200. **NVDA 301.6m sh (10-15), DTC 2.91 (from 2.14 in Aug); CRWV 69.8m sh (10-15, from 55m on 9-15), DTC 1.67**. Semi-monthly, ~9-day lag, history to 2020 in API. `sortFields` without partition filter -> 400. FMP `/stable/short-interest` -> 404. | 2026-10-15 |

---------------------------------------------------------------------------------------------------------------------------------

## 4. LEADING indicators of a capex throttle-back — ranked by how early they move, then by how free

| Rank | Indicator | Lead | Free? / status | Current reading |
|---|---|---|---|---|
| 1 | **Guidance language** in 8-K ex99.1 / calls | 1–2 qtrs before cash capex | Free detector: EFTS `LATEST/search-index?q="capital expenditures" AND (moderate OR "slow the pace" OR "reduce our capital")&forms=10-Q,8-K` -> 200, **0 hits last 60 days** (no hyperscaler softening language yet). Hyperscaler-CIK query returns the 6 latest ex99.1/10-Q docs (11 hits Oct-26). Body read needs Archives (403 here). FMP transcripts (paid) give the sentence directly. | all five still guiding UP for 2027 |
| 2 | **Neocloud equity + bond prices**, iv30, short interest | weeks | Free (CBOE iv30 CRWV 106.9; FINRA SI; Yahoo/FMP prices); CRWV bond price NOT free | CRWV -66% since Jun-25, SI +27% in a month |
| 3 | **Spender/recipient dispersion** | weeks–months | FMP prices (paid) or Yahoo (free, undocumented) | neoclouds -21% 3m vs recipients flat |
| 4 | **TSMC monthly revenue** (yoy and m/m) | 1–2 months vs. Nvidia quarter | Free: TWSE OpenAPI (latest month only -> poll) | Sep-26 +54.6% yoy, -0.6% m/m |
| 5 | **DRAM spot** (DDR5 16Gb) | 1–3 months vs contract | Free scrape of dramexchange.com table (daily); DXI via AJAX not captured | DDR5 16Gb avg $61.50 (10-30), flat |
| 6 | **GPU rental spot** (H100/H200/B300 $/h) | coincident with utilisation | Free: RunPod GraphQL (single vendor); Vast/SFCompute need keys/404 | H100 SXM $2.69/h |
| 7 | **Nvidia DSO, inventory, non-marketable equity** | 1 qtr | Free XBRL | DSO **59.6d** (record; 45 a quarter earlier), DIO 119d, equity stakes $47.9bn |
| 8 | **Accrued capex** (`CapitalExpendituresIncurredButNotYetPaid`) and purchase commitments | 1 qtr | Free XBRL | GOOGL $35.9bn, META commitments $355.7bn |
| 9 | **Census data-center construction** (SAAR, m/m) | lags orders ~6–12m but leads BEA structures | Free xlsx (monthly) | $85.0bn SAAR Aug-26, +7.5% m/m |
| 10 | **Power / interconnection queue** (ERCOT large-load, Texas PUC permits, FERC) | 12–24m | **Not machine-readable free**: ERCOT large-load page exists (`/services/rq/large-load-integration`, Batch Zero/PGRR145) but the monthly status report is a PDF/xlsx with unstable URLs; ERCOT public API needs free registration (connection dropped unauth); EIA API `API_KEY_MISSING` (free key); EIA-860M planned-generator xlsx monthly (free, keyless: `eia.gov/electricity/data/eia860m/xls/<month>_generator2026.xlsx`) | Texas permit pause (per Spectra) not yet visible in Census Aug data |
| 11 | **Hyperscaler useful-life changes** | reporting change, lagging economic reality | Free EFTS detector (36 hits 2025–26); body read required | META/AMZN 10-K Jan–Feb 2026 hits |
| 12 | **SK Hynix / Samsung quarterly** | quarterly | IR PDFs, not probed | — |

---------------------------------------------------------------------------------------------------------------------------------

## 5. What cannot be measured free (frankly), and what FMP + Tiingo add

Cannot be measured free at all:
- **Private labs' spend** (OpenAI, Anthropic, xAI): no filings. Only proxies: counterparties' RPO (ORCL/MSFT/GOOGL/CRWV), Nvidia's
  non-marketable equity, and announced commitments (table in §1c). Dollar commitments are headline figures without timing.
- **SPV / JV terms** (Hyperion, xAI–Nvidia $20bn SPV, Stargate Abilene leases): 8-K text at best; economics (rates, equity %, lease
  terms) often confidential. Detector only (EFTS).
- **GPU utilisation**: no issuer discloses it. Proxies: GPU rental spot (RunPod), neocloud revenue/backlog ratio (CRWV rev $2.58bn/qtr
  vs backlog $104bn), "backlog with delivery commenced >50%" (CRWV call), depreciation changes.
- **Private credit exposure to AI DCs**: BDC NAVs already on the tab; fund-level DC exposure is not disclosed in machine-readable form.
- **CDS** (CRWV "four digits"): paid only; no free proxy for CRWV (bonds unlisted in Frankfurt, TRACE gated).
- **Consensus capex and its revision history**: not in FMP, not free. Only guidance text, which we can time-stamp ourselves to build a
  revision ledger going forward (the Spectra "MSFT 2027 $170bn vs S&P $189bn" comparison cannot be reproduced from any free feed).
- **Segment revenue (AWS, Google Cloud, Azure)**: dimensional XBRL, absent from companyfacts -> text parsing or FMP.

What the paid keys add (all tested except Tiingo):
- **FMP /stable**: cash-flow statements with `capitalExpenditure`, `operatingCashFlow`, `freeCashFlow` (quarterly, matches XBRL exactly — MSFT
  FQ1-27 -39.367bn; useful as cross-check and for the fiscal-period metadata); `analyst-estimates` (revenue/EPS by FY, analyst counts);
  `earning-call-transcript` + `-dates` (THE capex-guidance source); `revenue-product-segmentation` (cloud segments); `ratios-ttm`,
  `key-metrics-ttm`, `enterprise-values`, `price-target-consensus`, `quote`, `industry-pe-snapshot`, `earnings` (next-report dates);
  `historical-price-eod/light` for baskets. No bond prices, no options, no short interest (404), no capex estimates.
- **Tiingo** (untested, key absent here): EOD prices as redundancy to FMP; fundamentals add-on would duplicate XBRL. Marginal for this panel.

---------------------------------------------------------------------------------------------------------------------------------

## Ranked list — the 12 series for a v1 "AI capex cycle" panel

| # | Series | Endpoint | Freq / lag / history | Reads now |
|---|---|---|---|---|
| 1 | Combined 5-hyperscaler quarterly capex and capex/OCF | data.sec.gov companyfacts x5, tags per §2a, YTD-differenced (`raw/hyperscaler_capex_ocf_quarterly.csv`) | Qtrly / ~30d / 2008+ (2018Q4+ for all five) | **$231.4bn Q3-26; capex/OCF 1.17; 2026 YTD $563bn** |
| 2 | Capex guidance ledger (2026/27, by company, dated) | FMP `/stable/earning-call-transcript` regex, fallback EFTS `LATEST/search-index` -> ex99.1 | Qtrly / same day / build forward | AMZN ~$220bn, GOOGL 195–205, META 135–145, MSFT FQ2 >$50bn, ORCL FY27 90–95 gross; all "up" for 2027 |
| 3 | Cloud RPO stack (MSFT+GOOGL+ORCL+CRWV+AVGO) | companyfacts `RevenueRemainingPerformanceObligation` (`raw/rpo_quarterly.csv`) | Qtrly / ~30d / 2018+ | MSFT 683, ORCL 664, GOOGL 568, AVGO 179, CRWV 104 ($bn) |
| 4 | BEA info-processing equipment: level and GDP contribution | FRED `Y034RC1Q027SBEA`, `Y034RY2Q224SBEA` (+ `B935RC1Q027SBEA`) | Qtrly / ~30d (advance) / 1947+ | $933.9bn SAAR, +40.8% yoy; **0.86pp of Q3 GDP growth** |
| 5 | Census private data-center construction (SAAR + NSA history) | `census.gov/construction/c30/xlsx/privsa.xlsx`, `privtime.xlsx` | Monthly / ~60d / 2014+ | **$84.95bn SAAR Aug-26, +73% yoy**; Jan–Aug NSA +41.7% |
| 6 | TSMC monthly revenue yoy | TWSE OpenAPI `t187ap05_L` (filter 2330) | Monthly / ~10d / poll-to-build | Sep-26 NT$511.9bn, +54.6% yoy |
| 7 | Nvidia DSO / inventory days / non-marketable equity | companyfacts NVDA (`raw/nvda_dso_dio.csv`) | Qtrly / ~30d / 2009+ | DSO 59.6d, DIO 119d, equity stakes $47.9bn |
| 8 | Spender vs recipient vs neocloud equity dispersion | FMP `/stable/historical-price-eod/light` (13 tickers) | Daily / 0 / 5y+ | YTD -7.7% / +71.1% / +30.4%; 3m neoclouds -21% |
| 9 | Options iv30 for NVDA, ORCL, CRWV, MSFT + VXN | CBOE `cdn.cboe.com/api/global/delayed_quotes/options/{SYM}.json`, `VXN_History.csv` | Daily / 15 min / VXN 2009+ (iv30 poll-to-build) | NVDA 44.1, ORCL 54.8, CRWV 106.9, MSFT 27.3; VXN 28.5 |
| 10 | Spender bond price proxy: ORCL 5.95% 2055 | Boerse Frankfurt `quote_box/single?isin=US68389XDR35&mic=XFRA` | Daily / 0 / poll-to-build (already in repo) | 73.59 (-1.64% d/d, 10-30) |
| 11 | Short interest NVDA, CRWV, ORCL | FINRA `consolidatedShortInterest` POST (no auth) | Semi-monthly / ~9d / 2020+ | NVDA 301.6m sh (DTC 2.91), CRWV 69.8m sh |
| 12 | GPU rental spot (H100/H200/B300) + DRAM DDR5 spot | RunPod GraphQL; dramexchange.com table scrape | Daily / 0 / poll-to-build | H100 SXM $2.69/h, B300 $6.94/h; DDR5 16Gb $61.50 |

Supporting (not in the 12, but one-liners already probed): finance-lease additions and `FinanceLeaseLiability` (MSFT $71bn);
`CapitalExpendituresIncurredButNotYetPaid` (GOOGL $35.9bn); META purchase commitments $355.7bn; CRWV quarterly capex $6.4bn (XBRL) vs
$9.4bn (company definition); NBIS backlog $40bn (call) / RPO $21.3bn (20-F).

## The 5 biggest measurement gaps

1. **Consensus capex and revisions** — not in FMP, no free feed; only a self-built guidance ledger from transcripts/8-Ks. The headline
   "2027 estimate cut" cannot be reproduced.
2. **Neocloud / private-credit pricing** — CRWV bond prices and CDS are not free (144A, not Frankfurt-listed; TRACE API gated); the tab's
   best stress read is CRWV iv30 (107) and short interest, which are equity, not credit.
3. **Private-lab spend and SPV economics** — OpenAI/Anthropic/xAI cash burn and the terms of Hyperion/Stargate/xAI vehicles are
   unobservable; proxies are counterparties' RPO and Nvidia's $47.9bn equity-stake line.
4. **Utilisation and unit economics** — no GPU utilisation disclosure; GPU rental is a single-vendor list price (RunPod), DXI index is AJAX-only,
   contract DRAM is paid.
5. **Power/permit pipeline** — ERCOT large-load queue, Texas PUC permits and FERC data exist only as PDFs/unstable xlsx or keyed APIs
   (ERCOT, EIA free keys); the Bloomberg "20% of pipeline at risk" claim has no free, machine-readable counterpart. Census construction
   spending is the closest (2-month lag, spend not permits).

## Files
- `notes_B.md` (this), `facts_tag_survey.txt` (full tag survey, 11 companies)
- `raw/hyperscaler_capex_ocf_quarterly.csv`, `raw/rpo_quarterly.csv`, `raw/nvda_dso_dio.csv`, `raw/census_datacenter_monthly.csv`
- `raw/facts_*.json` (companyfacts x11), `raw/sub_*.json`, `raw/frames_capex_CY2026Q*.json`, `raw/efts_*.json`
- `raw/fred_*.csv` (23 series), `raw/census_priv*.xlsx`, `raw/twse_t187ap05_L.json`, `raw/bf_orcl_quote.json`, `raw/finra_si_*.json`,
  `raw/cboe_*_opts.json`, `raw/cboe_vxn.csv`, `raw/yahoo_nvda.json`, `raw/runpod_gpu.json`, `raw/dramexchange.html`, `raw/fmp_*.json`
  (cash flow, estimates, transcripts x8, ratios, key metrics, price targets, prices x13), `raw/tiingo_notoken.json`, `raw/eia_nokey.json`
- `scripts/edgar_facts.py`, `scripts/build_series.py`, `scripts/local_metrics.py`, `scripts/fred_probe.py`
