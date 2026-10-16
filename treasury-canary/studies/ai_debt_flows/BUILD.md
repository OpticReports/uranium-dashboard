# AI-debt tab — phase 1 build spec (free data only)

Decided by Casey 2026-10-15: build phase 1 of `studies/ai-debt-flows.md` §6 on
treasury-canary as a tab of its own; full chain; defaults as proposed
(refinancings included and flagged, SPVs counted at pricing, converts included,
revolvers excluded). Casey's added emphasis: **the marginal buyer may be
pension funds and other large public funds, not sovereigns** — the tab gets a
dedicated panel for that and every buyer-side series says which investor
types it can and cannot see.

Everything here is CONTEXT, not a signal: nothing is pre-registered or graded,
no alert fires from this tab. Status language is "watch", never "warning".

## Repo conventions that apply

- Backend: FastAPI under `backend/app`; sources in `app/sources/` (httpx, disk
  cache under `settings.cache_dir`, graceful degradation: a failed fetch returns
  an empty/stale result and the panel shows STALE, never crashes); metrics in
  `app/metrics/`; one route module per tab in `app/api/` with the in-process
  TTL cache pattern of `routes_distress.py`; router included in `app/main.py`.
- Production deps are the explicit pins in `Dockerfile` + `pyproject.toml`
  (numpy, openpyxl, httpx; NO pandas). Adding a dependency means adding it to
  BOTH files; `xlrd==2.0.1` is pre-approved if the ACM .xls needs it.
- Tests: `backend/tests/test_ai_debt.py` (+ fixtures under
  `backend/tests/fixtures/ai_debt/`) must pass OFFLINE; the merge-blocking gate
  tests are listed below. Run: `cd backend && python3 -m pytest -q tests`.
- Frontend: React/TS + recharts + Tailwind in `frontend/src`; tab registry in
  `App.tsx` (`TABS`, `Tab` type, render block); panel chrome = `Panel`,
  `InlineError`, `Loading` from `components/ui.tsx`; types + fetch in
  `lib/api.ts` (`getJson`, `api.<name>`); `DistressPanel.tsx` and
  `SeverityTab.tsx` are the patterns to copy. `npx tsc --noEmit -p .` must pass.
- Text wears text tokens; status pills from `ui.tsx`; one y-axis per chart;
  legend for ≥2 series; every number on screen carries its basis.
- No model names or AI-product identifiers anywhere in code, comments, data
  or commits. Keyless fetches only (FRED via `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES`).
  EDGAR needs a User-Agent: `settings.edgar_user_agent`, env `EDGAR_USER_AGENT`,
  default `"treasury-canary/1.0 (research dashboard)"` — Casey sets a contact
  address on Render; never hard-code an email.

## Data (all free; URLs are the verified ones in studies/ai-debt-flows.md §9)

| Block | Source | Cadence | Module |
|---|---|---|---|
| Issuance tally (seed) | `studies/ai_debt_flows/data/deals.csv` → `app/sources/ai_debt_seed.json` via `studies/ai_debt_flows/export_seed.py` | frozen rev 1 | `sources/ai_debt_seed.py` |
| New filings | EDGAR submissions JSON per CIK (whitelist below), forms FWP / 424B2 / 424B5 / 8-K; best-effort extraction of size, coupon, maturity, spread from the primary document | daily poll | `sources/edgar_debt.py` |
| Share denominators | SIFMA quarterly US corporate issuance (frozen numbers + URL from the memo §3c); Z.1 nonfinancial net bond issuance BOGZ1FA103163005Q (FRED) | frozen / quarterly | `sources/ai_debt_seed.py` (frozen) + `sources/fred_csv.py` |
| Who holds US corporates | Z.1 via FRED keyless mirrors (levels + SAAR flows) for: rest of world, life insurers, private pension funds, state & local pension funds, mutual funds, ETFs, banks, households; the FU (unannualised) vs FA (SAAR) distinction is enforced | quarterly | `sources/z1.py` |
| Foreign bid by country | FRED TIC mirrors FORLT{TREAS,CORP}{NET,POS}<code> for Japan 42609, China, UK 13005, Taiwan, Korea, Cayman, Luxembourg, Ireland, Belgium, Switzerland, Norway, Grand Total 99996, Foreign Official 99990, Non-official 99991 (codes: take them from `studies/ai_debt_flows/data/tic_*.csv` headers and the memo); bills-inclusive Treasury flows for Japan and All Countries from the TIC CSLT zip | monthly | `sources/tic.py` |
| Japan | BoJ BoP zip `bp_m_en.zip` (series BPPI6D3N9US total US LT debt, BPPI6D3NAUS sovereign; residual = non-sovereign); MOF `monthb3.csv` (net purchases of foreign LT debt by investor type) and `week.csv`; MOF `jgbcm_all.csv` (JGB curve) | monthly / weekly | `sources/boj_mof.py` |
| Public funds | MOF trust accounts (pension money) from monthb3; Z.1 pension sectors; GPIF annual ISIN-level xlsx (AI issuers: Oracle, Amazon, Alphabet, Meta, Broadcom, Microsoft, Nvidia, CoreWeave, Blue Owl Technology Finance) with totals; TIC official vs non-official corporate purchases; IMF PIP Japan × US holder sectors if the SDMX call works (optional, flagged) | annual / monthly | `sources/public_funds.py` |
| Crowding | MSPD marketable outstanding by class (FiscalData `mspd_table_1`); Kim-Wright TP10 THREEFYTP10 (FRED) primary, ACM TP10 from the NY Fed xls if parseable; DGS10/DGS30/T10YIE/TREAST (FRED); auction high yield / bid-to-cover / indirect % from the existing `sources/treasury.py` | daily | `sources/treasury_supply.py` + existing |
| Breaking | FRED OAS BAMLC0A1CAAA, BAMLC0A2CAA, BAMLC0A3CA, BAMLC0A4CBBB, BAMLC0A0CM, BAMLH0A1HYBB, BAMLH0A2HYB, BAMLH0A3HYC, BAMLH0A0HYM2, effective yields BAMLC0A0CMEY/BAMLH0A0HYM2EY, BAA10Y; Fed EBP csv; OFR FSI csv; MOVE via existing `sources/yahoo.py` style; BDC prices (ARCC, OBDC, BXSL, FSK, MAIN, GBDC) via Yahoo + a frozen NAV table (value, as-of, 8-K URL) seeded from the scoping notes; frozen event log (CDS prints, rating actions, deal concessions) with a provenance badge primary / press / aggregator and the retrieval date | daily | `sources/breaking.py` |

CIK whitelist (EDGAR poll): Meta 1326801, Alphabet 1652044, Amazon 1018724,
Oracle 1341439, Microsoft 789019, Nvidia 1045810, Broadcom 1730168, AMD 2488,
Intel 50863, Micron 723125, Equinix 1101239, Digital Realty 1297996, GE Vernova
1996810, Vistra 1692819, Constellation 1868275, CoreWeave 1769628, Core
Scientific 1839341, Cipher 1819989, Hut 8 1964789, Galaxy 1859392, TeraWulf
1083301, Applied Digital 1144879, IREN 1878848, Nebius 1513845. Verify each CIK
against the submissions JSON `name` field; a wrong CIK is a test failure.
(Corrected 2026-10-15 from the live `name` fields: the first draft's 1868941
is Fluence Energy and 1662684 is KULR Technology; the gate test asserts both.)

## Payload: GET /ai-debt (route `app/api/routes_ai_debt.py`, TTL 6h, warmed by the scheduler like severity)

```
{ asof, generated, basis: {issuance, holders, foreign, japan, breaking},
  issuance: { seed_rev, deals: [{date, issuer, bucket, instrument, size_bn, ccy, size_usd_bn,
              rating_bucket, rating_at_issue, tranches, pricing, verif: "P"|"R"|"S", src, included, flags: [refi|spv|convert|non_usd], note}],
              totals_by_year, by_bucket_year, by_rating_year, by_month: [{month, <bucket>: $bn}],
              share: {year: {hyperscaler_usd_bn, all_ai_usd_bn, sifma_us_corp_bn, pct_hyperscaler, pct_all, src}},
              vs_treasury: {fy: {ai_bn, net_marketable_ust_bn, pct, basis}},
              new_filings: [{filed, issuer, form, url, extracted: {size_bn?, coupons?, maturities?, spreads?}, status}] },
  holders: { asof, z1: {levels: {sector: $bn}, flows_saar_last4: {sector: [$bn]}, pensions: {...}}, note },
  foreign_bid: { asof, countries: [{name, code, treas_net_12m, corp_net_12m, treas_pos, corp_pos, corp_share_of_lt, custody_centre: bool}],
                 series: {months, grand_total: {treas, corp}, official: {...}, non_official: {...}, japan: {...}},
                 bills_inclusive: {japan_12m, all_12m, note} },
  japan: { boj: {months, total, sovereign, nonsovereign (JPY trn, 12m sums + monthly)}, mof_by_type: {months, banks, life, trust_accounts, inv_trusts, all},
           mof_weekly: {weeks, net}, jgb: {dates, y10, y30}, read: str },
  public_funds: { trust_accounts_12m_jpy_trn, z1_pensions: {private: {level, flow_saar}, state_local: {...}}, gpif: {asof, foreign_bonds_jpy_trn, ai_issuers: [{issuer, jpy_bn, lines}], ai_share_pct, ust_jpy_trn, src},
                  tic_official_corp: {net_12m, pos, share_of_foreign_held}, imf_pip_japan: {...}|null, can_see: [...], cannot_see: [...] },
  crowding: { ust: {fy: {net_marketable, coupons, bills}}, term_premium: {kw10: {latest, series}, acm10: {...}|null}, yields: {dgs10, dgs30, t10yie}, fed_treast,
              auctions: [{date, tenor, high_yield, btc, indirect_pct}] },
  breaking: { spreads: {bucket: {latest, asof, hi_2026, lo_2026, series}}, ccc_b_gap, yields: {ig, hy}, baa10y, ebp, ofr_fsi, move,
              bdc: [{ticker, price, asof, nav, nav_asof, p_nav, nav_src}], spread_at_issue_30y: [{issuer, date, bp, src}], events: [{date, text, provenance, src, retrieved}] },
  honesty: [str], sources: {tag: url}, status: {block: "ok"|"stale"|"error", ...} }
```
Every number carries a basis and a source tag; `status` says which blocks
came from cache or failed. Missing data is `null`, never 0.

## Frontend: tab "AI debt" (`components/AiDebtTab.tsx`, `TABS` entry after Severity)

1. Header strip: four stat tiles — 2026 YTD raised (and share of US corporate issuance), Japan 12m net Treasuries vs corporates (LT and incl. bills), CCC OAS vs 2026 high, 30y UST + 10y term premium — each with as-of and source.
2. Issuance: stacked monthly bars by bucket (toggle: by rating), a deal table (date, issuer, bucket, size, rating, 30y spread where known, provenance badge P/R/S, link), "new filings not yet in the tally" list.
3. Who holds US corporates: Z.1 holder sectors (levels, last 4 quarters of flows), pensions highlighted.
4. Foreign bid by country: table with 12m net Treasuries vs corporates and sparkline, custody centres grouped and labelled "unattributable"; official vs non-official.
5. Japan: BoJ sovereign vs non-sovereign 12m (line); MOF by investor type 12m (line); JGB 10y/30y; the verdict text (repatriation, not substitution).
6. Public funds & pensions: MOF trust accounts vs banks/lifers; Z.1 pension flows; GPIF AI-issuer holdings table + share; what each series can and cannot see.
7. Crowding: term premium + 30y; net UST supply vs the tally; auction indirect share by tenor.
8. Breaking: spreads by rating (log), CCC–B gap, spread-at-issue drift, BDC price/NAV table, event log with provenance badges.
9. Honesty box (static text from the payload) at the bottom.

## Merge-blocking gate tests (`backend/tests/test_ai_debt.py`, offline on fixtures + seed)

- Seed reproduces the frozen tally: total 682.5; by year 39.7 / 242.8 / 400.0; by bucket × year and by rating × year equal §3a/§3b of the memo (2025 "not captured" = 10.5); hyperscaler USD-leg share 0.85 / 4.2 / 7.2 %; every included deal has a non-empty `src`.
- Tranche sums re-derive the headline for the parsed FWP deals in the seed (Meta 30.0 and 25.0, Oracle 25.0, Nvidia 25.0, Amazon C$14.0 → USD at the stated FX).
- Non-USD legs converted at the FX recorded in the row; a USD-only share never uses an all-currency numerator.
- Z.1: FA (SAAR) and FU (unannualised) never mixed — the fixture ratio check (4–4.5×) is asserted; sector levels sum to within 1% of the "all sectors" total on the fixture.
- TIC: "All Countries" vs "Grand Total" labelled; LT-only AND bills-inclusive Japan Treasury flows both present and of the fixture's sign (12m to Jul-26: +4.0 vs −48.6).
- BoJ: sovereign + non-sovereign residual == total for every month; units JPY trn.
- MOF: trust accounts 12m to Sep-26 == +12.23 on the fixture; column mapping by header name, not position.
- MSPD: class sum equals total marketable for every month.
- EDGAR: the whitelist CIKs resolve to the expected names on the fixture submissions JSON; the extractor on the Meta 2026-04-30 FWP fixture returns 6 tranches summing to 25.0.
- Breaking: CCC−B gap computed from the same dates; BDC p_nav == price / nav; every event has a provenance tag and a URL.
- Payload: `json.dumps` succeeds; every block has `status`; no number without a source tag; no "0" where the fixture is missing (null instead).
- Frontend: tsc clean; the tab renders with an all-null payload without throwing
  (`cd frontend && npm run smoke:aidebt` — server-renders the fixture, the all-null
  payload, the backend's own key vocabulary, malformed shapes and null deal rows).

## Honesty box text (ship verbatim, edit only for accuracy)

Scoping rev 1, not a study: nothing pre-registered or graded. Tally = gross
issuance at pricing, not net of redemptions; non-USD legs at trade-date FX;
~20% of tally dollars rest on search snippets pending filings; new EDGAR
filings are auto-extracted and NOT in the tally until reviewed. TIC attributes
by custody country, not beneficial owner; no free source names the buyer of a
specific bond; GPIF/AP lists are annual; pension and public-fund buying is
visible only via MOF trust accounts, Z.1 pension sectors and annual fund lists.
FRED serves 3 years of ICE OAS history; CDS and single-name prices are dated
press prints, not a feed. Nothing here is a forecast.
