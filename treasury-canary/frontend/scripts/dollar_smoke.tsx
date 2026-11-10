// Render smoke for the Dollar watch tab: server render, so a throw is a hard
// failure instead of being swallowed by a section's error boundary.
// Run: `npm run smoke:dollar` (esbuild bundle + node).
//
// Cases: the dev fixture (the backend's 2026-11-02 payload); the all-null
// payload (every source down, the frozen record still ships); a payload with
// the scramble gate OPEN (indicators + confirmations rendered); malformed shapes.
import { renderToStaticMarkup } from "react-dom/server";
import { DollarView } from "../src/components/DollarTab";
import { DOLLAR_ALL_NULL, DOLLAR_FIXTURE } from "../src/lib/dollarFixture";
import type { DollarWatch } from "../src/lib/api";

// memo §5: never on the panel (the backend gate test scans the same list)
const FORBIDDEN = ["probability of", "p(crisis", "chance of a crisis", "% chance", "crisis subsided", "subsided", "crisis over",
  "crisis is over", "all clear", "countdown", "next crisis in", "every crisis", "will crash", "imminent", "band breach",
  "ends in crisis", "leads the vix", "lamp", "points below the top", "dates the end of"];

function run(name: string, data: DollarWatch): string {
  const html = renderToStaticMarkup(<DollarView data={data} />);
  const unavailable = (html.match(/unavailable/g) ?? []).length;
  const na = (html.match(/n\/a/g) ?? []).length;
  console.log(`${name}: ${html.length} chars, ${unavailable} 'unavailable', ${na} 'n/a'`);
  for (const bad of ["NaN", "undefined", "[object Object]", "render failed"]) {
    if (html.includes(bad)) throw new Error(`${name}: render contains '${bad}'`);
  }
  const low = html.toLowerCase();
  for (const p of FORBIDDEN) if (low.includes(p)) throw new Error(`${name}: forbidden phrase '${p}'`);
  if (/\b(warning|alert|danger)\b/i.test(html)) throw new Error(`${name}: status language leak`);
  // no rate on the momentum table: its cells are 11 clustered episodes (memo §5: none below ~15)
  const m = html.indexOf('data-testid="momentum-table"');
  if (m >= 0) {
    const table = html.slice(m, html.indexOf("</table>", m));
    if (/\(\d+%\)/.test(table)) throw new Error(`${name}: a rate is printed on the momentum table`);
  }
  return html;
}

// 1. the dev fixture
const a = run("fixture", DOLLAR_FIXTURE);
for (const must of ["Dollar state", "Dollar-funding nowcast", "Dollar-scramble peak gauge", "Slow state", "Forward ledger", "Honesty box",
  "101.72", "ad hoc 85-105 band (no edge found)", "Gate closed", "2008-09-22", "2022-07-28", "No edge", "re-dollarising", "129.3",
  "Pending questions", "C16", "calendar days", "no better than gold", "re-arm only", "expires 2027-01-01", "5 of 11", "41 of 85"]) {
  if (!a.includes(must)) throw new Error(`fixture render missing '${must}'`);
}

// 2. the all-null payload
const b = run("all-null", DOLLAR_ALL_NULL);
for (const must of ["unavailable", "2008-11-06", "No edge", "Honesty box"]) {
  if (!b.includes(must)) throw new Error(`all-null render missing '${must}'`);
}

// 3. the gate open: three separate readings, never a sum
const open: DollarWatch = JSON.parse(JSON.stringify(DOLLAR_FIXTURE));
if (open.scramble?.state) {
  open.scramble.gate_open = true;
  open.scramble.state.gate_open = true;
  open.scramble.indicators = {
    a_deceleration: { met: true, roc20_now_pct: 2.6, roc20_max_60d_pct: 12.9, dollar_vs_60d_high_pct: -0.4, rule: "20-day climb at or below half its 60-day maximum" },
    b_funding_easing: { met: false, cp_now: 2.1, cp_median_1y: 0.9, ofr_funding_now: 4.2, ofr_funding_median_1y: 1.0, rule: "both below 1-year medians" },
    c_risk_turn: { met: null, gold_now: null, gold_prior_20d_high: null, emb_now: 80.1, emb_prior_20d_high: 82.0, rule: "gold and EMB above prior 20-day highs" },
    note: "shown separately",
  };
  open.scramble.confirmations = { dollar_off_peak_pct: -0.4, dollar_3pct_off_peak: false, swap_now_bn: 450, swap_episode_peak_bn: 583, swap_below_10pct_of_peak: false, episode_start: "2008-09-29" };
}
const c = run("gate-open", open);
for (const must of ["Gate open", "(a) deceleration: met (dollar scramble peaking)", "(b) funding easing: not met", "(c) gold and EM bonds turning: n/a", "Confirmations since 2008-09-29"]) {
  if (!c.includes(must)) throw new Error(`gate-open render missing '${must}'`);
}

// 4. malformed shapes degrade, never throw
run("empty", {} as DollarWatch);
run("nulls", { state: null, funding: null, scramble: null, slow: null, ledger: null, honesty: null } as DollarWatch);
run("partial", { state: { dxy: { latest: 101.7, monthly: { months: ["2026-10"], close: [null] } }, quadrant: {} }, funding: { rows: [{ id: "x", label: "y" }] },
  scramble: { state: null, history: [{ date: "2008-09-22" }] }, slow: { usd_credit: { series: { quarters: ["2026-Q2"], credit_yoy_pct: [null] } } } } as unknown as DollarWatch);
console.log("dollar smoke: OK");
