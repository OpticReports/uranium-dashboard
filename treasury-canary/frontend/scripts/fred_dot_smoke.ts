// Smoke for the header's FRED dot (2026-11-21, re-check B round 3): a failing series turns it amber even
// when no copy is served (past the 72 h cap, or never cached), and the hover text says what each failing
// series is served from. Run: `npm run smoke:freddot`.
import type { Health } from "../src/lib/api";
import { fredDotTitle, fredDotWarn } from "../src/lib/fredDot";

const fail = (m: string): never => { throw new Error(`fred dot smoke: ${m}`); };
const base: Health = { status: "ok", service: "treasury-canary", fred_key_present: true, fred_key_error: null,
  fred_stale_series: {}, fred_failing_series: {}, scheduler: true, display_tz: "UTC" };

if (fredDotWarn(base) || fredDotTitle(base) !== undefined) fail("a healthy FRED must read green, no hover text");
const noCopy: Health = { ...base, fred_failing_series: { USREC: 0.5 } };           // past the cap: nothing served
if (!fredDotWarn(noCopy)) fail("a failing series with no usable copy left the dot green");
if (fredDotTitle(noCopy) !== "FRED calls failed in the last 6 h (1): USREC last failed 0.5 h ago: no usable copy, STALE") fail(`title: ${fredDotTitle(noCopy)}`);
const stale: Health = { ...base, fred_failing_series: { USREC: 2, T10Y3M: 0 }, fred_stale_series: { USREC: 30 } };
if (!fredDotWarn(stale)) fail("a stale-served series left the dot green");
if (fredDotTitle(stale) !== "FRED calls failed in the last 6 h (2): USREC last failed 2 h ago: last good copy (30 h old); T10Y3M last failed just now: no usable copy, STALE")
  fail(`title: ${fredDotTitle(stale)}`);
const older: Health = { ...base, fred_failing_series: undefined, fred_stale_series: { USREC: 30 } };   // pre-round-5 server
if (!fredDotWarn(older) || !fredDotTitle(older)?.includes("USREC: last good copy (30 h old)")) fail(`older server: ${fredDotTitle(older)}`);
const outage: Health = { ...base, fred_failing_series: Object.fromEntries(Array.from({ length: 88 }, (_, i) => [`S${String(i).padStart(2, "0")}`, 1])) };
const t = fredDotTitle(outage) ?? "";
if (!t.startsWith("FRED calls failed in the last 6 h (88): S00 last failed 1 h ago: no usable copy") || !t.endsWith("; and 83 more") || t.split("; ").length !== 6)
  fail(`an 88-series outage must name 5 and count the rest: ${t.slice(0, 120)}…`);
const key: Health = { ...base, fred_key_error: "api_key not registered", fred_failing_series: { USREC: 1 } };
if (!fredDotTitle(key)?.startsWith("FRED rejected the API key: api_key not registered")) fail(`key: ${fredDotTitle(key)}`);
console.log("fred dot smoke: ok (healthy green; failing with no copy amber; stale amber; outage capped at 5 rows; key error leads)");
