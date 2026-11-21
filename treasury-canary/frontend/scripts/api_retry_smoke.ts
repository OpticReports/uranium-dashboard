// Smoke for getJson's retry policy (2026-11-21): gateway 502s are retried; an app 503 with its own JSON detail,
// and a POST that is not marked safe (/refresh), are not. Fake fetch, instant timers.
// Run: `npm run smoke:retry`.
(globalThis as { setTimeout: unknown }).setTimeout = (fn: () => void) => { fn(); return 0; };
type Reply = { status: number; json?: unknown; text?: string };
let calls: string[] = [];
let script: Reply[] = [];
(globalThis as { fetch: unknown }).fetch = async (url: string, init?: { method?: string }) => {
  calls.push(`${init?.method ?? "GET"} ${url}`);
  const r = script.length > 1 ? script.shift()! : script[0];
  const isJson = r.json !== undefined;
  return {
    ok: r.status >= 200 && r.status < 300, status: r.status,
    headers: { get: (k: string) => (k.toLowerCase() === "content-type" ? (isJson ? "application/json" : "text/html") : null) },
    json: async () => (isJson ? r.json : JSON.parse("<html>")),
  };
};
const fail = (m: string): never => { throw new Error(`retry smoke: ${m}`); };

(async () => {
  const { api } = await import("../src/lib/api");
  // a gateway 502 (HTML) is retried, then succeeds
  calls = []; script = [{ status: 502, text: "<html>502</html>" }, { status: 502 }, { status: 200, json: { ok: 1 } }];
  await api.pins();
  if (calls.length !== 3) fail(`GET retried ${calls.length - 1} times, wanted 2 then success`);
  // a persistent gateway 502 gives up after 1 + 7 tries
  calls = []; script = [{ status: 502 }];
  await api.pins().then(() => fail("persistent 502 resolved"), () => undefined);
  if (calls.length !== 8) fail(`persistent 502: ${calls.length} tries, wanted 8`);
  // an app 503 with its own JSON detail is an answer, not a blip: no retry, and the detail is shown
  calls = []; script = [{ status: 503, json: { detail: "cycle build failed; nothing cached" } }];
  const msg = await api.cycleAnalog().then(() => "", (e: Error) => e.message);
  if (calls.length !== 1 || !msg.includes("nothing cached")) fail(`app 503: ${calls.length} tries, message "${msg}"`);
  // POST /refresh is never repeated
  calls = []; script = [{ status: 502 }];
  await api.refresh().then(() => fail("refresh resolved"), () => undefined);
  if (calls.length !== 1) fail(`POST /refresh sent ${calls.length} times`);
  // POST /shock-sim/run is a pure computation: retried
  calls = []; script = [{ status: 502 }, { status: 200, json: { ok: 1 } }];
  await api.shockRun({ hikes: 0 });
  if (calls.length !== 2) fail(`POST /shock-sim/run sent ${calls.length} times, wanted 2`);
  console.log("retry smoke: OK");
})().catch((e) => { console.error(e); process.exit(1); });
