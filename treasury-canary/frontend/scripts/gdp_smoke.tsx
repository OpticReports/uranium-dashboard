// Render smoke for the GDP tab: server render, so a throw is a hard failure.
// Run: `npm run smoke:gdp` (esbuild bundle + node). Real recharts at a fixed size (scripts/recharts_shim.tsx),
// so the SVG marks are counted, not assumed.
import { renderToStaticMarkup } from "react-dom/server";
import { GdpView, toggleSlot, yearStep, type GdpInitial } from "../src/components/GdpTab";
import { GDP_FIXTURE } from "../src/lib/gdpFixture";
import type { GdpWatch } from "../src/lib/api";

const FORBIDDEN = ["will grow", "will be", "will fall", "will rise", "guarantee", "certain to", "imminent", "all clear"];
const count = (html: string, re: RegExp) => (html.match(re) ?? []).length;
// drawn marks only: a path with no points has an empty d, so structure alone cannot pass these counts
const LINES = /recharts-line-curve" d="M/g;
const AREAS = /recharts-area-area" d="M[^"]*L[^"]*L/g;   // a one-point area (M x,yL x,yZ) is not a band
const pct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const fx = (code: string) => GDP_FIXTURE.countries!.find((c) => c.code === code)!;

function run(name: string, data: GdpWatch, initial?: GdpInitial): string {
  const html = renderToStaticMarkup(<GdpView data={data} initial={initial} />);
  for (const bad of ["NaN", "undefined", "[object Object]", "Infinity"]) {
    if (html.includes(bad)) throw new Error(`${name}: render contains '${bad}'`);
  }
  const low = html.toLowerCase();
  for (const p of FORBIDDEN) if (low.includes(p)) throw new Error(`${name}: forbidden phrase '${p}'`);
  console.log(`${name}: ${html.length} chars, ${count(html, LINES)} lines, ${count(html, AREAS)} areas`);
  return html;
}
function must(name: string, html: string, xs: string[]) {
  for (const x of xs) if (!html.includes(x)) throw new Error(`${name}: missing '${x}'`);
}
function eq(name: string, got: number, want: number, what: string) {
  if (got !== want) throw new Error(`${name}: ${what} = ${got}, expected ${want}`);
}

// 1. default view: the 6 largest, 10 years, projection on, bands hidden (more than 3 shown)
const a = run("default", GDP_FIXTURE);
must("default", a, ["GDP GROWTH", "Economies: 6 of 22 selected", "United States", "China", "India", "frozen snapshot",
  "rule, 4 quarters on", "What this means", "Honesty box", "last value holds", "Bands hidden with more than 3",
  ">USA</text>", ">CHN</text>", ">DEU</text>", ">JPN</text>", ">GBR</text>", ">IND</text>",   // every line named at its end
  'aria-pressed="true"', 'role="img"', `rule: ${pct(fx("USA").forecast!.gdp[3]!)} in ${fx("USA").forecast!.quarters[3]}`]);
eq("default", count(a, LINES), 12, "drawn lines (6 published + 6 projected)");
eq("default", count(a, AREAS), 0, "band areas");
if (!a.includes('stroke-dasharray="6 4"')) throw new Error("default: the projection is not dashed");

// 2. two economies: both bands (80% and 50%) and end labels
const b = run("two", GDP_FIXTURE, { selected: ["USA", "CHN"] });
eq("two", count(b, AREAS), 4, "drawn band areas");
const usF = fx("USA").forecast!, cnB = fx("CHN").forecast!.band80.gdp![3]!;
must("two", b, [`${pct(usF.gdp[3]!)} (${usF.quarters[3]})`, `${pct(cnB[0])} to ${pct(cnB[1])}‡`]);   // the fixture's numbers
must("two", b, [">USA</text>", ">CHN</text>", "80% band", "(line above its 50% band at 4q*)", "* China: four quarters ahead, the line sits above its own 50% band",
  "in 31 of 32 backtests (median miss -1.2 points)", "‡ China: band in-sample only"]);
if (b.includes("United States: the line sits")) throw new Error("two: only China's line sits outside its band");

// 3. per person, menu open, 25 years, with an aggregate selected (no per-person series: hidden, slot kept)
const c = run("per-person", GDP_FIXTURE, { measure: "per_capita", menuOpen: true, range: "25y", selected: ["USA", "JPN", "G20"] });
must("per-person", c, ["Real GDP growth per person", "Aggregates have no per-person series", "G20 (OECD aggregate)", "Largest 8"]);
eq("per-person", count(c, /type="checkbox"/g), 23, "checkboxes (22 economies + projection)");
eq("per-person", count(c, LINES), 4, "drawn lines (USA and Japan, published + projected)");
must("per-person", c, ["1 with no per-person series not drawn", "trend (GDP)", "rule per person, 4 quarters on", "(per person)"]);
const agg = run("aggregates-only-pc", GDP_FIXTURE, { measure: "per_capita", selected: ["G20"] });
must("aggregates-only-pc", agg, ["The aggregates selected have no per-person series"]);

// 3b. India's IMF figures are fiscal years; the population breaks show in per-person mode only
const f = run("fiscal-pop", GDP_FIXTURE, { selected: ["IND", "SAU", "POL"] });
must("fiscal-pop", f, ["† India: IMF figures are fiscal years (April-March)", "‡ Saudi Arabia: band in-sample only"]);
if (f.includes("population series")) throw new Error("fiscal-pop: population notes belong to per-person mode");
const g = run("fiscal-pop-pc", GDP_FIXTURE, { selected: ["IND", "SAU", "POL"], measure: "per_capita" });
must("fiscal-pop-pc", g, ["Saudi Arabia: the IMF population series swings", "Poland: the IMF population series drops 2.3% in 2021"]);
const h = run("past-range", GDP_FIXTURE, { range: "custom", from: "2008-01-01", to: "2010-12-31", selected: ["CHN"] });
must("past-range", h, [")*</td>", "* China: four quarters ahead, the line sits above its own 50% band"]);  // the table keeps its marks

// 4. a custom range in the past: no projection, and the page says why
const d = run("custom-past", GDP_FIXTURE, { range: "custom", from: "2008-01-01", to: "2010-12-31", selected: ["USA"] });
must("custom-past", d, ["The projection shows when the range reaches the latest quarter.", 'type="date"', ">USA</text>"]);
eq("custom-past", count(d, LINES), 1, "drawn lines (published only)");
eq("custom-past", count(d, AREAS), 0, "band areas");
if (d.includes("rule: ")) throw new Error("custom-past: the legend quotes a projection the chart does not show");
const open = run("custom-open", GDP_FIXTURE, { range: "custom", from: "", to: "", selected: ["USA"] });
eq("custom-open", count(open, LINES), 2, "drawn lines (both ends open: all quarters plus the projection)");

// 5. never more than 8 lines at once
const e = run("nine", GDP_FIXTURE, { selected: ["USA", "CHN", "DEU", "JPN", "GBR", "IND", "FRA", "ITA", "CAN"] });
must("nine", e, ["Economies: 8 of 22 selected"]);

// 5b. colour slots follow the economy, never its rank; the cap holds; year labels thin out on a phone
let s: Record<string, number> = { USA: 0, CHN: 1, DEU: 2 };
s = toggleSlot(s, "CHN");
eq("slots", s.USA, 0, "USA keeps slot 0"); eq("slots", s.DEU, 2, "Germany keeps slot 2");
s = toggleSlot(s, "JPN");
eq("slots", s.JPN, 1, "a new economy takes the lowest free slot");
const full = Object.fromEntries(["A", "B", "C", "D", "E", "F", "G", "H"].map((k, i) => [k, i]));
if (toggleSlot(full, "Z") !== full) throw new Error("slots: a ninth economy was let in");
eq("ticks", yearStep(26, 1280), 1, "25Y at 1280px: every year");
eq("ticks", yearStep(26, 375), 3, "25Y at 375px: every third year");
if (yearStep(80, 375) < 9) throw new Error("ticks: Max at 375px still crowds its labels");

// snapshot fallback: the banner names the snapshot, never "the previous build"
const cold = run("cold-fallback", { ...GDP_FIXTURE, build_error: "RuntimeError: boom", build_fallback: "snapshot" } as GdpWatch);
must("cold-fallback", cold, ["showing the frozen snapshot of"]);
if (cold.includes("showing the previous build")) throw new Error("cold-fallback: a snapshot is called the previous build");

// partial fallback: only the IMF inputs are the snapshot (2026-11-21: IMF API 404/429 while OECD answered)
const part = run("partial-snapshot", { ...GDP_FIXTURE, status: { overall: "snapshot",
  inputs: { yoy: "ok", qoq: "ok", pop: "snapshot", ngdpd: "snapshot", weo_growth: "snapshot" } } } as GdpWatch);
must("partial-snapshot", part, ["IMF population, IMF GDP shares and IMF projections come from the frozen snapshot of 2026-11-16 (the live source did not answer); the rest is live."]);
if (part.includes("The live sources did not answer")) throw new Error("partial-snapshot: says every live source failed");
const mixed = run("mixed-inputs", { ...GDP_FIXTURE, status: { overall: "snapshot",
  inputs: { yoy: "stale", qoq: "stale", pop: "snapshot", ngdpd: "ok", weo_growth: "ok" } } } as GdpWatch);
must("mixed-inputs", mixed, ["IMF population comes from the frozen snapshot of 2026-11-16; OECD growth and OECD quarterly growth are cached copies (the live sources did not answer); the rest is live."]);
const missing = run("missing-input", { ...GDP_FIXTURE, status: { overall: "error",
  inputs: { yoy: "ok", qoq: "error", pop: "ok", ngdpd: "ok", weo_growth: "ok" } } } as GdpWatch);
must("missing-input", missing, ["OECD quarterly growth is unavailable (the live source did not answer); the rest is live."]);
const none = run("none-live", { ...GDP_FIXTURE, status: { overall: "error",
  inputs: { yoy: "snapshot", qoq: "snapshot", pop: "snapshot", ngdpd: "snapshot", weo_growth: "error" } } } as GdpWatch);
if (none.includes("the rest is live")) throw new Error("none-live: says the rest is live with nothing live");
const allSnap = run("all-snapshot", GDP_FIXTURE);
must("all-snapshot", allSnap, ["The live sources did not answer; showing the frozen snapshot of 2026-11-16."]);

// 6. malformed payloads degrade, never throw
run("empty", {} as GdpWatch);
run("no-economies", { countries: [], aggregates: [] } as GdpWatch);
run("no-series", { countries: [{ code: "USA", name: "United States", share_world_pct: 26, aggregate: false, first: null, last: null,
  series: null, forecast: null, imf: null, record: null }] } as GdpWatch);
console.log("gdp smoke: OK");
