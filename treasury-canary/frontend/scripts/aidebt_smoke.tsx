// Render smoke for the AI-debt tab — the frontend half of the BUILD.md gate
// ("the tab renders with an all-null payload without throwing"). Server
// render, so a throw is a hard failure instead of being swallowed by the
// panel error boundary. Run: `npm run smoke:aidebt` (esbuild bundle + node).
//
// Cases: the dev fixture; the all-null payload; a payload in the BACKEND's
// contract (lower-case spread keys, the seed's rating vocabulary, a dict
// `src`, snake_case Z.1 sectors); malformed shapes; and deal rows with a
// null bucket / issuer.
import { renderToStaticMarkup } from "react-dom/server";
import { AiDebtView } from "../src/components/AiDebtTab";
import { AI_DEBT_ALL_NULL, AI_DEBT_FIXTURE } from "../src/lib/aiDebtFixture";
import type { AiDebt } from "../src/lib/api";

function run(name: string, data: AiDebt): string {
  const html = renderToStaticMarkup(<AiDebtView data={data} />);
  const unavailable = (html.match(/unavailable/g) ?? []).length;
  const na = (html.match(/n\/a/g) ?? []).length;
  console.log(`${name}: ${html.length} chars, ${unavailable} 'unavailable', ${na} 'n/a'`);
  for (const bad of ["NaN", "undefined", "[object Object]"]) {
    if (html.includes(bad)) throw new Error(`${name}: render contains '${bad}'`);
  }
  if (/\b(warning|alert)\b/i.test(html)) throw new Error(`${name}: status language leak (warning/alert)`);
  return html;
}

// 1. the dev fixture
const a = run("fixture", AI_DEBT_FIXTURE);
for (const must of ["AI-trade issuance", "Who holds US corporates", "Foreign bid by country", "Japan", "Public funds", "Crowding", "Breaking", "Honesty box", "682", "12.82", "custody", "hyperscaler", "trust accounts"]) {
  if (!a.includes(must)) throw new Error(`fixture render missing '${must}'`);
}
if (a.includes("Spread series unavailable")) throw new Error("fixture: spread chart did not render");

// 2. the all-null payload (the spec's gate)
const b = run("all-null", AI_DEBT_ALL_NULL);
if (!b.includes("unavailable")) throw new Error("all-null render should show unavailable states");

// 3. the backend's contract, as GET /ai-debt actually keys it
const bk = (latest: number, hi: number): NonNullable<AiDebt["breaking"]>["ccc_b_gap"] => ({
  latest, asof: "2026-10-14", hi_2026: hi, lo_2026: latest / 2, end_2025: latest * 0.7,
  series: { dates: ["2026-10-13", "2026-10-14"], values: [latest - 0.1, latest] },
  src: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=X", unit: "%",
});
const backend: AiDebt = {
  ...AI_DEBT_ALL_NULL,
  asof: "2026-10-14",
  issuance: {
    seed_rev: "rev 1", status: "ok",
    deals: [
      { date: "2026-04-30", issuer: "Meta Platforms", bucket: "hyperscaler", size_bn: 25, ccy: "USD", size_usd_bn: 25, rating_bucket: "AA", verif: "P", src: "https://www.sec.gov/x", included: true, flags: [] },
      { date: "2026-05-15", issuer: "CoreWeave Financing DDTL V", bucket: "off-balance-sheet", size_bn: 2.6, ccy: "USD", size_usd_bn: 2.6, rating_bucket: "unrated-private", verif: "R", src: "https://x", included: true, flags: ["spv"] },
      { date: "2026-06-01", issuer: "Switch", bucket: "data-center", size_bn: 1, ccy: "USD", size_usd_bn: 1, rating_bucket: "ABS-tranched", verif: "S", src: "https://x", included: true, flags: [] },
      { date: "2026-06-02", issuer: "Hut 8", bucket: "neocloud", size_bn: 1, ccy: "USD", size_usd_bn: 1, rating_bucket: "not-captured", verif: "S", src: "https://x", included: true, flags: [] },
    ],
    totals_by_year: { "2026": 29.6 },
    by_bucket_year: { hyperscaler: { "2026": 25 }, "off-balance-sheet": { "2026": 2.6 }, "data-center": { "2026": 1 }, neocloud: { "2026": 1 } },
    by_rating_year: { AA: { "2026": 25 }, "unrated-private": { "2026": 2.6 }, "ABS-tranched": { "2026": 1 }, "not-captured": { "2026": 1 }, AAA: { "2026": 0 }, B: { "2026": 0 } },
    by_month: [{ month: "2026-04", hyperscaler: 25, neocloud: 0 }, { month: "2026-05", "off-balance-sheet": 2.6, hyperscaler: 0 }, { month: "2026-06", "data-center": 1, neocloud: 1 }],
    by_month_rating: [{ month: "2026-04", AA: 25, AAA: 0, B: 0 }, { month: "2026-05", "unrated-private": 2.6, AAA: 0 }, { month: "2026-06", "ABS-tranched": 1, "not-captured": 1, AAA: 0 }],
    share: { "2026": { hyperscaler_usd_bn: 25, all_ai_usd_bn: 29.6, sifma_us_corp_bn: 2195.1, pct_hyperscaler: 1.14, pct_all: 1.35, src: "https://www.sifma.org/" } },
    vs_treasury: { FY2026: { ai_bn: 29.6, net_marketable_ust_bn: 2120.2, pct: 1.4, basis: "GROSS over NET" } },
    new_filings: [
      { filed: "2026-10-14", issuer: "Alphabet", form: "FWP", url: "https://www.sec.gov/y", status: "auto-extracted, not in tally",
        extracted: { size_bn: 8.5, ccy: "CAD", partial: false, coupons: [3.65, 5.0], maturities: [2031, 2056], spreads: [50, 110], tranches: [{ maturity: 2031, spread_bp: 50, benchmark: "GoC" }, { maturity: 2056, spread_bp: 110, benchmark: "GoC" }] } },
      { filed: "2026-10-13", issuer: "Vistra", form: "FWP", url: "https://www.sec.gov/z", status: "auto-extracted (partial), not in tally",
        extracted: { size_bn: 0.85, ccy: "USD", partial: true, coupons: [null, null], maturities: [2057, 2057], spreads: [null, null], tranches: [] } },
    ],
  },
  holders: {
    status: "ok", asof: "2026Q2", note: "Z.1 via FRED",
    z1: {
      levels: { all_sectors: 18115.7, rest_of_world: 5195.7, rest_of_world_ex_abs: 4714.3, life_insurers: 3944.2, private_pensions: 897.3, state_local_pensions: 634.6, federal_pensions: 15.7, banks_us_chartered: 900, money_market_funds: 50 },
      flows_saar_last4: { rest_of_world: [300, 310, 349, 435.4], rest_of_world_ex_abs: [280, 290, 300, 377], private_pensions: [10, 12, 20, 23.4] },
      flows_quarters: ["2025Q3", "2025Q4", "2026Q1", "2026Q2"],
      pensions: { private: { level: 897.3, flow_saar: 23.4 }, state_local: { level: 634.6, flow_saar: 5 } },
      labels: { rest_of_world: "Rest of the world (foreign holders)", banks_us_chartered: "US-chartered depository institutions (incl. IBFs)", federal_pensions: "Federal government retirement funds" },
      src: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BOGZ1FL893063005Q",
    },
  },
  public_funds: {
    status: "ok", trust_accounts_12m_jpy_trn: 12.2278, trust_accounts_asof: "2026-09", trust_accounts_src: "https://www.mof.go.jp/x",
    mof_by_type: { months: ["2026-08", "2026-09"], trust_accounts_12m: 12.2278, banks_12m: -12.83, life_12m: -2.11, inv_trusts_12m: -1.5, all_12m: -5.09 },
    z1_pensions: { private: { level: 897.3, flow_saar: 23.4, asof: "2026Q2" }, state_local: { level: 634.6, flow_saar: 5, asof: "2026Q2" }, src: "https://fred.stlouisfed.org/x" },
    gpif: { asof: "2026-03-31", foreign_bonds_jpy_trn: 72.821, ai_issuers: [{ issuer: "Oracle", jpy_bn: 11.06, lines: 53 }], ai_share_pct: 0.05, ust_jpy_trn: 36.841, src: "https://www.gpif.go.jp/x" },
    tic_official_corp: { net_12m: 5.1, pos: 316.0, share_of_foreign_held: 6.0, asof: "2026-07", src: "https://fred.stlouisfed.org/x" },
    imf_pip_japan: null, can_see: ["MOF trust accounts"], cannot_see: ["The buyer of any specific bond"],
  },
  breaking: {
    status: "ok", asof: "2026-10-14",
    spreads: { aaa: bk(0.4, 0.46), aa: bk(0.6, 0.61), a: bk(0.7, 0.79), bbb: bk(1.04, 1.16), ig: bk(0.84, 0.94), bb: bk(1.99, 2.22), b: bk(3.29, 3.77), ccc: bk(12.82, 12.82), hy: bk(3.25, 3.46) },
    ccc_b_gap: { ...bk(9.53, 9.53), src: { ccc: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A3HYC", b: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A2HYB" } },
    yields: { ig: bk(5.94, 6.03), hy: bk(8.2, 8.22) }, baa10y: bk(1.46, 1.6), ebp: bk(-0.39, 0.1), ofr_fsi: bk(-2.1, 0.5), move: bk(102.6, 115),
    bdc: [{ ticker: "ARCC", price: 18.9, asof: "2026-10-15", nav: 19.35, nav_asof: "2026-06-30", p_nav: 0.977, nav_src: "https://www.sec.gov/a" },
          { ticker: "OBDC", price: 10.3, asof: "2026-10-15", nav: null, nav_asof: null, p_nav: null, nav_src: null, nav_note: "no SEC filing fetched in the scoping pass; aggregator-only value not used" }],
    spread_at_issue_30y: [{ issuer: "Meta Platforms", date: "2026-04-30", bp: 132, maturity: 2056, src: "https://www.sec.gov/x" }],
    events: [{ date: "2026-10-14", text: "An event", provenance: "press", src: "https://example.com/", retrieved: "2026-10-15" }],
  },
  basis: { issuance: "b", holders: "b", foreign: "b", japan: "b", public_funds: "b", crowding: "b", breaking: "b" },
  status: { issuance: "ok", holders: "ok", foreign_bid: "error", japan: "error", public_funds: "ok", crowding: "error", breaking: "ok", overall: "error" },
};
const c = run("backend-contract", backend);
if (c.includes("Spread series unavailable")) throw new Error("backend-contract: lower-case spread keys did not render the spreads chart");
if (!c.includes("12.82 / 12.82")) throw new Error("backend-contract: the CCC tile did not read the lower-case key");
if (!c.includes("GoC+50")) throw new Error("backend-contract: a non-UST benchmark must not be printed as T+");
if (!c.includes("(partial)")) throw new Error("backend-contract: partial extraction is not flagged");
if (!c.includes("NAV not filing-sourced")) throw new Error("backend-contract: null NAV reason not shown");
if (!c.includes("US-chartered depository institutions")) throw new Error("backend-contract: z1.labels not used");
if (c.includes("rest_of_world_ex_abs") || c.includes("banks_us_chartered")) throw new Error("backend-contract: raw snake_case sector key on screen");
if (!c.includes("12m net buyers")) throw new Error("backend-contract: MOF net-buyer line not derived from the payload");
if (c.includes("the only Japanese investor type")) throw new Error("backend-contract: frozen factual claim on the trust-accounts tile");
if ((c.match(/not captured/g) ?? []).length < 2) throw new Error("backend-contract: 'not-captured' not normalised to the display vocabulary");

// 4. malformed shapes the backend might emit mid-build: wrong types everywhere
const bad = {
  asof: 7, generated: null, basis: "x",
  issuance: { status: "error", deals: "nope", by_month: [{ month: 3 }], share: { "2026": null }, totals_by_year: { "2026": "400" }, new_filings: [null, { filed: 1 }] },
  holders: { z1: { levels: { a: "1" }, flows_saar_last4: { a: "x" } }, note: 5 },
  foreign_bid: { countries: [{ name: "Japan", custody_centre: "yes", treas_spark: "x" }, null], series: { months: ["2026-01"], grand_total: { treas: "x" } }, bills_inclusive: { japan_12m: "a" } },
  japan: { boj: { months: ["2026-01", "2026-02"], total: [1], sovereign: null }, mof_by_type: {}, jgb: { dates: "x" }, read: 4 },
  public_funds: { gpif: { ai_issuers: [{ issuer: 1 }, "x"] }, can_see: "x", z1_pensions: { private: 3 } },
  crowding: { ust: { FY: "x" }, term_premium: { kw10: { series: { dates: ["a"], values: "x" } } }, auctions: [{ date: "2026-01-01", tenor: 9, indirect_pct: "x" }], yields: 3 },
  breaking: { spreads: { CCC: { series: [{ date: 1, value: "x" }] } }, ccc_b_gap: 5, bdc: [{ ticker: "A", price: "x" }], events: [{ date: "2026", text: 5 }], spread_at_issue_30y: [{ issuer: 3 }] },
  honesty: "x", sources: 3, status: { issuance: "weird" },
} as unknown as AiDebt;
run("malformed", bad);

// 5. one malformed deal row must not take the Issuance panel down
const nullRows = {
  ...backend,
  issuance: {
    ...backend.issuance,
    deals: [
      ...(backend.issuance?.deals ?? []),
      { date: "2026-07-01", issuer: null, bucket: null, size_bn: 1, ccy: "USD", size_usd_bn: 1, rating_bucket: null, verif: "S", src: null, included: true, flags: null },
    ],
  },
} as unknown as AiDebt;
const e = run("null-bucket-and-issuer", nullRows);
if (e.includes("render failed")) throw new Error("null bucket / issuer took a panel down");

console.log("SMOKE_OK");
