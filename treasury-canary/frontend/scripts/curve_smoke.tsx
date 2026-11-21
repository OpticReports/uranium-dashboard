// Render smoke for the yield-curve chart (2026-11-21: NBER bands not drawn, a silent static fallback).
// Run: `npm run smoke:curve`. Real recharts at a fixed size (scripts/recharts_shim.tsx), so marks are counted.
import { renderToStaticMarkup } from "react-dom/server";
import { CurveChart, ReadoutRow } from "../src/components/ReSteepenAlert";
import type { CurveCanary } from "../src/lib/api";
import live from "./fixtures/curve_canary_3m10y.json";

const LIVE = live as unknown as CurveCanary;
const fail = (m: string): never => { throw new Error(`curve smoke: ${m}`); };

// 1. every NBER recession is drawn and clipped to the plot (1980 and 1981-82 start before the 1981-09-01 series)
const a = renderToStaticMarkup(<CurveChart data={LIVE} />);
const bands = a.match(/<path[^>]*recharts-reference-area-rect[^>]*>/g) ?? [];
if (bands.length !== LIVE.recessions.length) fail(`${bands.length} bands drawn for ${LIVE.recessions.length} recessions`);
if (!/recharts-reference-area[^>]*clip-path|clip-path[^>]*recharts-reference-area/.test(a)) fail("bands not clipped to the plot");
if (a.includes("NBER recession dates are unavailable")) fail("no-dates note shown with dates present");
// 2. no recession dates: nothing drawn, and the chart says why
const b = renderToStaticMarkup(<CurveChart data={{ ...LIVE, recessions: [] }} />);
if (/recharts-reference-area-rect/.test(b)) fail("bands drawn without dates");
if (!b.includes("NBER recession dates are unavailable")) fail("no-dates note missing");
// 3. the probability tile names the static fallback, and only then
const s = renderToStaticMarkup(<ReadoutRow data={{ ...LIVE, recession_probability_pct: 16.4, recession_probability_basis: "static" }} />);
if (!s.includes("16.4% (static)")) fail("static fallback not labelled");
const f = renderToStaticMarkup(<ReadoutRow data={{ ...LIVE, recession_probability_basis: "fitted" }} />);
if (f.includes("(static)")) fail("fitted value labelled static");
console.log(`curve smoke: OK (${bands.length} bands, clipped; static label and no-dates note checked)`);
