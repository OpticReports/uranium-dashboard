// Gate (2026-11-21): panels that load once re-read quietly on the page-wide 15-min refresh tick.
//
// Before, such a panel kept whatever it loaded until the page was reloaded, so a board built during a
// FRED outage outlived the outage in an open tab. This drives the BUILT app in Chromium with a fake
// clock: load each tab, jump 16 min, and require that
//   1. every endpoint the tab loaded is requested again (the refresh happened),
//   2. no spinner or error box appears (the refresh was quiet),
//   3. a refresh that fails (forced 404 on /labor/board) leaves the panel's data on screen,
//   4. a choice the user made (the recession dial's horizon) survives the refresh.
//
// Run: `npm run e2e:refresh` (builds dist/ first), optionally `-- <backend base URL>`; the default is
// the live service. The app is served from dist/ through Playwright's router; each API path is fetched
// ONCE from the backend with curl and cached, so the backend sees one page view's worth of GETs.
// Needs Playwright with Chromium (preinstalled in the agent environment).
const { chromium } = require("playwright");
const { execFile } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BACKEND = (process.argv[2] || "https://treasury-canary.onrender.com").replace(/\/$/, "");
const DIST = path.join(__dirname, "..", "dist");
const KEEP = process.env.REFRESH_E2E_CACHE;                 // reuse responses across runs (mutation testing)
const CACHE = KEEP ? (fs.mkdirSync(KEEP, { recursive: true }), KEEP) : fs.mkdtempSync(path.join(os.tmpdir(), "refresh-e2e-"));
const ORIGIN = "http://canary.test";
const FAIL_ON_REFRESH = "/labor/board";
const USER_DRIVEN = new Set(["POST /shock-sim/run"]);    // runs on input changes, not a load-once read
const TABS = ["Severity", "AI debt", "Dollar", "GDP", "Track record"];

const fail = (m) => { console.error(`refresh e2e: FAIL ${m}`); process.exitCode = 1; };
let phase = "initial";
const log = [];

function curl(method, url, body) {
  const args = ["-s", "-m", "150", "-X", method, "-w", "\n%{http_code}", url];
  if (body) args.push("-H", "content-type: application/json", "--data-binary", body);
  return new Promise((resolve) => execFile("curl", args, { maxBuffer: 64 << 20 }, (err, out) => {
    const cut = (out || "").lastIndexOf("\n");
    resolve({ status: Number((out || "").slice(cut + 1)) || 599, text: cut >= 0 ? out.slice(0, cut) : "" });
  }));
}

async function backend(method, pathAndQuery, body) {
  const key = crypto.createHash("sha1").update(`${method} ${pathAndQuery} ${body || ""}`).digest("hex");
  const file = path.join(CACHE, key + ".json");
  if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, "utf8"));
  let r;
  for (let i = 0; i < 3; i++) {               // the live service can 502 while it boots: retry in real time
    r = await curl(method, BACKEND + pathAndQuery, body);
    if (r.status < 500) break;
    await new Promise((ok) => setTimeout(ok, 5000));
  }
  fs.writeFileSync(file, JSON.stringify(r));
  return r;
}

async function handle(route) {
  const req = route.request();
  const url = new URL(req.url());
  if (url.origin !== ORIGIN) return route.abort();                                 // fonts etc.: offline
  if (url.pathname === "/canary" || url.pathname.startsWith("/canary/")) {       // the built app
    const rel = url.pathname.replace(/^\/canary\/?/, "") || "index.html";
    let file = path.join(DIST, rel);
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, "index.html");
    return route.fulfill({ path: file });
  }
  const entry = { phase, call: `${req.method()} ${url.pathname}`, status: 0 };
  log.push(entry);
  if (phase.startsWith("refresh") && url.pathname === FAIL_ON_REFRESH) {
    entry.status = 404;
    return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"forced refresh failure"}' });
  }
  const r = await backend(req.method(), url.pathname + url.search, req.postData());
  entry.status = r.status;
  return route.fulfill({ status: r.status, contentType: "application/json", body: r.text });
}

const calls = (p) => new Set(log.filter((x) => x.phase === p).map((x) => x.call));
const SPIN = "span.h-2.w-2.animate-pulse.rounded-full.bg-slate-500";
const spinners = (page) => page.locator(SPIN).count();
const errors = (page) => page.locator("div.text-red-300", { hasText: "Error:" }).count();
// the most spinners / error boxes on screen at ANY moment from now on: a flash that clears before the
// page settles still counts
const watch = (page) => page.evaluate((spin) => {
  const w = window;
  const look = () => {
    const s = document.querySelectorAll(spin).length;
    const e = [...document.querySelectorAll("div.text-red-300")].filter((d) => d.textContent.includes("Error:")).length;
    w.__maxSpin = Math.max(w.__maxSpin ?? 0, s);
    w.__maxErr = Math.max(w.__maxErr ?? 0, e);
  };
  w.__maxSpin = 0; w.__maxErr = 0; look();
  w.__obs?.disconnect();
  w.__obs = new MutationObserver(look);
  w.__obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
}, SPIN);
const peak = (page) => page.evaluate(() => ({ spin: window.__maxSpin, err: window.__maxErr }));
async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 240_000 });
  await page.waitForTimeout(500);
}

async function refreshAndCheck(page, label, extra) {
  for (let waited = 0; waited < 120_000 && (await spinners(page)) > 0; waited += 500)
    await page.waitForTimeout(500);                         // let first loads finish: a flash must show
  const before = { spin: await spinners(page), err: await errors(page) };
  if (before.spin) {
    const waiting = await page.locator(SPIN).evaluateAll((els) => els.map((e) => e.parentElement.textContent.trim()));
    const odd = log.filter((x) => x.phase === phase && x.status !== 200).map((x) => `${x.call} ${x.status}`);
    console.log(`refresh e2e: ${label}: still loading before the refresh: ${waiting.join(" | ")}`
      + (odd.length ? `; non-200 replies: ${odd.join(", ")}` : ""));
  }
  const loaded = calls(phase);
  phase = `refresh ${label}`;
  await watch(page);
  await page.clock.fastForward("16:00");
  await settle(page);
  const again = calls(phase);
  const missing = [...loaded].filter((c) => !again.has(c) && !USER_DRIVEN.has(c));
  const after = { spin: await spinners(page), err: await errors(page) };
  const top = await peak(page);
  if (missing.length) fail(`${label}: not re-read on the refresh tick: ${missing.join(", ")}`);
  if (top.spin > before.spin) fail(`${label}: a refresh showed a spinner (${before.spin} -> peak ${top.spin})`);
  if (top.err > before.err) fail(`${label}: a refresh put up an error box (${before.err} -> peak ${top.err})`);
  if (extra) await extra();
  console.log(`refresh e2e: ${label}: ${loaded.size} endpoints loaded, all re-read quietly`
    + ` (spinners ${before.spin}->${after.spin}, error boxes ${before.err}->${after.err})`);
  return loaded;
}

(async () => {
  if (!fs.existsSync(path.join(DIST, "index.html"))) throw new Error("build dist/ first (npx vite build)");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  await page.route("**/*", handle);
  await page.clock.install({ time: new Date("2026-11-21T18:00:00Z") });
  await page.goto(`${ORIGIN}/canary/`);
  await settle(page);

  // the monitor tab: a horizon chosen by hand, and a panel whose refresh will fail
  const six = page.locator('div:has(> button:text-is("12")):has(> button:text-is("24")) > button:text-is("6")');
  await six.click();
  const chosen = async () => /border-sky-500/.test((await six.getAttribute("class")) || "");
  if (!(await chosen())) fail("could not choose the 6-month horizon");
  const labor = page.locator("section.rounded-lg", { hasText: "Labor Stress Board" }).last();   // the Panel
  const laborBefore = (await labor.innerText()).length;
  const monitor = await refreshAndCheck(page, "Monitor", async () => {
    if (!calls(phase).has(`GET ${FAIL_ON_REFRESH}`)) fail("the forced-failure refresh was never requested");
    const text = await labor.innerText();
    if (/Error:/.test(text) || text.length < laborBefore * 0.9)
      fail(`a failed refresh replaced the Labor Stress Board's data (${laborBefore} -> ${text.length} chars)`);
    if (!(await chosen())) fail("the refresh reset the chosen 6-month horizon");
  });
  for (const must of ["GET /recession-model", "GET /labor/board", "GET /cycle", "GET /pins/history", "GET /stat-regime"])
    if (!monitor.has(must)) fail(`the gate is vacuous: the monitor tab never loaded ${must}`);

  for (const tab of TABS) {
    phase = `initial ${tab}`;
    await page.getByRole("button", { name: tab, exact: true }).click();
    await settle(page);
    await refreshAndCheck(page, tab);
  }
  await browser.close();
  if (!KEEP) fs.rmSync(CACHE, { recursive: true, force: true });
  if (!process.exitCode) console.log("refresh e2e: OK");
})().catch((e) => { console.error(e); process.exit(1); });
