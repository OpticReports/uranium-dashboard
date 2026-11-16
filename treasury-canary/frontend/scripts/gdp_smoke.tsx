// Render smoke for the GDP tab: server render, so a throw is a hard failure.
// Run: `npm run smoke:gdp` (esbuild bundle + node). Real recharts at a fixed size (scripts/recharts_shim.tsx),
// so the SVG marks are counted, not assumed.
import { renderToStaticMarkup } from "react-dom/server";
import { GdpView, type GdpInitial } from "../src/components/GdpTab";
import { GDP_FIXTURE } from "../src/lib/gdpFixture";
import type { GdpWatch } from "../src/lib/api";

const FORBIDDEN = ["will grow", "will be", "will fall", "will rise", "guarantee", "certain to", "imminent", "all clear"];
const count = (html: string, re: RegExp) => (html.match(re) ?? []).length;

function run(name: string, data: GdpWatch, initial?: GdpInitial): string {
  const html = renderToStaticMarkup(<GdpView data={data} initial={initial} />);
  for (const bad of ["NaN", "undefined", "[object Object]", "Infinity"]) {
    if (html.includes(bad)) throw new Error(`${name}: render contains '${bad}'`);
  }
  const low = html.toLowerCase();
  for (const p of FORBIDDEN) if (low.includes(p)) throw new Error(`${name}: forbidden phrase '${p}'`);
  console.log(`${name}: ${html.length} chars, ${count(html, /recharts-line-curve/g)} lines, ${count(html, /recharts-area-area/g)} areas`);
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
must("default", a, ["GDP GROWTH", "Economies: 6 of 22 shown", "United States", "China", "India", "frozen snapshot",
  "rule, 4 quarters on", "What this means", "Honesty box", "last value holds", "Bands hidden with more than 3"]);
eq("default", count(a, /recharts-line-curve/g), 12, "lines (6 published + 6 projected)");
eq("default", count(a, /recharts-area-area/g), 0, "band areas");
if (!a.includes('stroke-dasharray="6 4"')) throw new Error("default: the projection is not dashed");

// 2. two economies: both bands (80% and 50%) and end labels
const b = run("two", GDP_FIXTURE, { selected: ["USA", "CHN"] });
eq("two", count(b, /recharts-area-area/g), 4, "band areas");
must("two", b, [">USA</text>", ">CHN</text>", "80% band"]);

// 3. per person, menu open, 25 years, with an aggregate selected (no per-person series: hidden, slot kept)
const c = run("per-person", GDP_FIXTURE, { measure: "per_capita", menuOpen: true, range: "25y", selected: ["USA", "JPN", "G20"] });
must("per-person", c, ["Real GDP growth per person", "Aggregates have no per-person series", "G20 (OECD aggregate)", "Largest 8"]);
eq("per-person", count(c, /type="checkbox"/g), 23, "checkboxes (22 economies + projection)");
eq("per-person", count(c, /recharts-line-curve/g), 4, "lines (USA and Japan, published + projected)");

// 4. a custom range in the past: no projection, and the page says why
const d = run("custom-past", GDP_FIXTURE, { range: "custom", from: "2008-01-01", to: "2010-12-31", selected: ["USA"] });
must("custom-past", d, ["The projection shows when the range reaches the latest quarter.", 'type="date"', ">USA</text>"]);
eq("custom-past", count(d, /recharts-line-curve/g), 1, "lines (published only)");
eq("custom-past", count(d, /recharts-area-area/g), 0, "band areas");

// 5. never more than 8 lines at once
const e = run("nine", GDP_FIXTURE, { selected: ["USA", "CHN", "DEU", "JPN", "GBR", "IND", "FRA", "ITA", "CAN"] });
must("nine", e, ["Economies: 8 of 22 shown"]);

// 6. malformed payloads degrade, never throw
run("empty", {} as GdpWatch);
run("no-economies", { countries: [], aggregates: [] } as GdpWatch);
run("no-series", { countries: [{ code: "USA", name: "United States", share_world_pct: 26, aggregate: false, first: null, last: null,
  series: null, forecast: null, imf: null, record: null }] } as GdpWatch);
console.log("gdp smoke: OK");
